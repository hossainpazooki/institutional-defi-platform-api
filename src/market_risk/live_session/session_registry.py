"""Per-intent Session lifecycle + per-symbol ingestor refcount.

Production-shaped lifecycle owner for `/v2/ws/trade/{intent_id}`. Two
independent refcount layers, deliberately separate:

1. **Session refcount per `intent_id`.** Repeated `acquire(intent_id)` returns
   the same `Session`; the last `release(intent_id)` stops it and removes the
   entry. This keeps detector state, pipeline state, and persistence calls
   coherent across reconnects.

2. **Ingestor refcount per `symbol`.** The first acquire for a symbol starts
   the symbol's ingestor (Binance in prod, fixture in tests); the last
   release on that symbol stops it. Two intents on the same symbol share one
   ingestor.

The registry returns a `SessionLease` from `acquire`. The lease has the
session plus a one-shot `release()`. The WS handler owns one lease per
connection and calls `release()` on teardown — it doesn't need to know about
the registry.

Phase 1 deliberate non-goal: there is no fan-out of envelopes to multiple
WS connections on one shared session. If two connections to the same
intent_id are ever expected to *each* see a full envelope stream, the
Session queues would need a multi-consumer adapter. For the current demo
shape (one viewer per intent at a time) the shared-session refcount is
sufficient and avoids duplicated detector work on reconnect.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, TypeAlias

from .pipeline import build_pipeline
from .session_manager import Session

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from src.market_risk.ws_schemas import TradeIntent

    from .intent_repository import IntentRepository
    from .market_bus import MarketBus
    from .persistence import SessionPersistence
    from .pipeline import PipelineConfig
    from .rationale_streamer import RationaleStreamer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class IngestorLike(Protocol):
    """Minimum protocol the registry needs to manage an ingestor's lifetime.

    Both `Ingestor` (live Binance) and `FixtureIngestor` (deterministic test)
    satisfy this.
    """

    def start(self) -> None: ...

    async def stop(self) -> None: ...


IngestorFactory: TypeAlias = "Callable[[str], IngestorLike]"
IntentResolver: TypeAlias = "Callable[[str], Awaitable[TradeIntent | None]]"
StreamerFactory: TypeAlias = "Callable[[], RationaleStreamer]"


@dataclass
class SessionLease:
    """A one-shot handle to a Session.

    The lease owns *exactly one* unit of refcount on the registry. Calling
    `release()` more than once is a no-op; this lets the WS handler safely
    invoke `release()` on every error path.
    """

    session: Session
    _release: Callable[[], Awaitable[None]]
    _released: bool = False

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._release()


class IntentTerminalError(LookupError):
    """Raised by `SessionRegistry.acquire` when the intent has reached a terminal
    status (`closed` or `failed`).

    Subclasses `LookupError` so callers that broadly handle "intent not
    acquireable" still match; the WS handler catches this specifically to emit
    a typed `intent_terminal` error envelope and a 1008 close.
    """

    def __init__(self, *, intent_id: str, status: str) -> None:
        self.intent_id = intent_id
        self.status = status
        super().__init__(f"intent is terminal: {status} ({intent_id!r})")


# ---------------------------------------------------------------------------
# Internal registry entries
# ---------------------------------------------------------------------------


@dataclass
class _SessionEntry:
    session: Session
    refcount: int


@dataclass
class _IngestorEntry:
    ingestor: IngestorLike
    refcount: int


# ---------------------------------------------------------------------------
# SessionRegistry
# ---------------------------------------------------------------------------


@dataclass
class SessionRegistry:
    """Owns active Sessions and symbol-level Ingestors for the live-session demo.

    Construction does no I/O. Backends (`MarketBus`, `SessionPersistence`,
    `RationaleStreamer` factory, `IngestorFactory`, `IntentResolver`) are
    injected so tests and production share the same lifecycle code.
    """

    bus: MarketBus
    config: PipelineConfig
    persistence: SessionPersistence
    streamer_factory: StreamerFactory
    ingestor_factory: IngestorFactory
    intent_resolver: IntentResolver
    # Optional lifecycle sink — when set, the registry calls
    # mark_active / mark_closed / mark_failed at the right points. Tests that
    # don't care about persisted status can omit it.
    intent_repository: IntentRepository | None = None

    _sessions: dict[str, _SessionEntry] = field(default_factory=dict)
    _ingestors: dict[str, _IngestorEntry] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _shutdown: bool = False

    # ── public API ──────────────────────────────────────────────────────

    async def acquire(self, intent_id: str) -> SessionLease:
        """Resolve intent_id → Session, incrementing both refcounts.

        On first successful acquire for an intent, persists `status=active`
        via the optional `intent_repository`. If session construction raises
        after intent lookup, persists `status=failed` and re-raises.

        Raises `LookupError` if the intent_resolver returns None for this id.
        Returns a lease that the caller must `release()` exactly once.
        """
        if self._shutdown:
            raise RuntimeError("session registry is shut down")

        # Reject terminal intents before any Session construction or refcount
        # bump. Only enforced when a repository is wired — unit tests that
        # build a registry with a bare resolver and no repo retain their
        # previous behavior (resolver-only LookupError on unknown ids).
        if self.intent_repository is not None:
            record = self.intent_repository.get_record(intent_id)
            if record is not None and record.status in {"closed", "failed"}:
                raise IntentTerminalError(
                    intent_id=intent_id, status=record.status
                )

        intent = await self.intent_resolver(intent_id)
        if intent is None:
            raise LookupError(f"unknown intent_id {intent_id!r}")

        is_first_acquire = False
        async with self._lock:
            existing = self._sessions.get(intent_id)
            if existing is not None:
                existing.refcount += 1
                await self._acquire_symbol_locked(intent.asset)
                session = existing.session
            else:
                try:
                    session = self._build_session(intent)
                except Exception as exc:  # noqa: BLE001
                    if self.intent_repository is not None:
                        self.intent_repository.mark_failed(intent_id, str(exc))
                    raise
                self._sessions[intent_id] = _SessionEntry(session=session, refcount=1)
                await self._acquire_symbol_locked(intent.asset)
                session.start()
                is_first_acquire = True

        if is_first_acquire and self.intent_repository is not None:
            # mark_active is idempotent and stamps activated_at only on the
            # first transition out of "created". Held outside the registry
            # lock — the repo has its own consistency story.
            self.intent_repository.mark_active(intent_id)

        async def _release_one() -> None:
            await self._release(intent_id, intent.asset)

        return SessionLease(session=session, _release=_release_one)

    async def shutdown(self) -> None:
        """Stop all active sessions and ingestors. Idempotent."""
        async with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
            sessions = list(self._sessions.values())
            ingestors = list(self._ingestors.values())
            self._sessions.clear()
            self._ingestors.clear()

        for entry in sessions:
            with contextlib.suppress(Exception):
                await entry.session.stop()
        for ing in ingestors:
            with contextlib.suppress(Exception):
                await ing.ingestor.stop()

    # ── introspection (for tests / debugging) ───────────────────────────

    def session_refcount(self, intent_id: str) -> int:
        entry = self._sessions.get(intent_id)
        return entry.refcount if entry is not None else 0

    def ingestor_refcount(self, symbol: str) -> int:
        entry = self._ingestors.get(symbol)
        return entry.refcount if entry is not None else 0

    def active_intent_ids(self) -> list[str]:
        return list(self._sessions.keys())

    # ── internal ────────────────────────────────────────────────────────

    async def _release(self, intent_id: str, symbol: str) -> None:
        session_to_stop: Session | None = None
        ingestor_to_stop: IngestorLike | None = None
        is_final_release = False

        async with self._lock:
            entry = self._sessions.get(intent_id)
            if entry is not None:
                entry.refcount -= 1
                if entry.refcount <= 0:
                    session_to_stop = entry.session
                    self._sessions.pop(intent_id, None)
                    is_final_release = True

            ing_entry = self._ingestors.get(symbol)
            if ing_entry is not None:
                ing_entry.refcount -= 1
                if ing_entry.refcount <= 0:
                    ingestor_to_stop = ing_entry.ingestor
                    self._ingestors.pop(symbol, None)

        # Stop outside the lock — `Session.stop()` awaits the consume task and
        # rationale tasks, which may take a beat; we don't want to block other
        # acquires meanwhile.
        if session_to_stop is not None:
            with contextlib.suppress(Exception):
                await session_to_stop.stop()
        if ingestor_to_stop is not None:
            with contextlib.suppress(Exception):
                await ingestor_to_stop.stop()

        # Persist `closed` after the session has actually stopped. If
        # session.stop() raised, the audit trail still gets a `closed` row —
        # we don't have a richer "stopped-with-errors" status this slice.
        if is_final_release and self.intent_repository is not None:
            self.intent_repository.mark_closed(intent_id)

    async def _acquire_symbol_locked(self, symbol: str) -> None:
        """Caller must already hold self._lock."""
        ing_entry = self._ingestors.get(symbol)
        if ing_entry is not None:
            ing_entry.refcount += 1
            return
        ingestor = self.ingestor_factory(symbol)
        ingestor.start()
        self._ingestors[symbol] = _IngestorEntry(ingestor=ingestor, refcount=1)

    def _build_session(self, intent: TradeIntent) -> Session:
        session = Session(intent=intent, bus=self.bus)

        async def emit_tick(b: bytes) -> None:
            await session.emit_tick(b)

        async def emit_audit(b: bytes) -> None:
            await session.emit_audit(b)

        streamer = self.streamer_factory()
        pipeline = build_pipeline(
            intent=intent,
            config=self.config,
            persistence=self.persistence,
            streamer=streamer,
            next_seq=session.next_seq,
            emit_tick=emit_tick,
            emit_audit=emit_audit,
        )
        session.pipeline = pipeline
        return session


# ---------------------------------------------------------------------------
# Provider helper
# ---------------------------------------------------------------------------


def make_session_provider(
    registry: SessionRegistry,
) -> Callable[[str], Awaitable[SessionLease]]:
    """Build a SessionProvider callable bound to this registry."""

    async def _provider(intent_id: str) -> SessionLease:
        return await registry.acquire(intent_id)

    return _provider


__all__ = [
    "IngestorFactory",
    "IngestorLike",
    "IntentResolver",
    "IntentTerminalError",
    "SessionLease",
    "SessionRegistry",
    "StreamerFactory",
    "make_session_provider",
]
