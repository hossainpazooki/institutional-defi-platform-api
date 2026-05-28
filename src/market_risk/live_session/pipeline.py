"""Live-session pipeline composition — the working vertical slice.

Composes the building blocks (`SnapshotBuilder` + `ThresholdDetector` +
`VerdictService` + `RationaleStreamer` + persistence + envelope sinks) into
a single async loop that turns a raw bus message into the canonical envelope
sequence:

1. The frame updates pipeline state (rolling vol from kline closes, latest
   book state from bookTicker, depth from depth frames). Tick envelopes flow
   to a drop-newest "market" lane (1.).
2. When a snapshot is built, the detector runs.
3. On a crossing the verdict is resolved BEFORE any rationale token is emitted.
   The verdict + threshold envelopes flow to an "audit" lane that does NOT
   drop. The crossing and its snapshot are persisted before the rationale
   stream starts.
4. The rationale stream runs concurrently, emitting `rationale_tok` envelopes
   into the audit lane, then a terminal `rationale_verified` /
   `rationale_retracted` envelope.

Frame format consumed off the bus:

    Real Binance combined-stream frames are heterogeneous (`@bookTicker`,
    `@kline_1m`, `@markPrice@1s`, `@aggTrade`). Mapping each to pipeline state
    is straightforward but verbose. This module also accepts a normalized
    "synthetic" frame shape used by the fixture ingestor so the vertical
    slice has an easy deterministic path:

        {"type": "kline_close", "close": 1850.0}
        {"type": "snapshot_inputs", "mark": "1850", "bid": "1849.50",
         "ask": "1850.50", "depth_bid": [["1849.50","10"], ...],
         "depth_ask": [["1850.50","10"], ...], "funding_rate": null}

    Real Binance parsing is a follow-up (see report at end of session).

See spec §1 (overall flow), §3 (snapshot), §4 (threshold), §5 (verdict), §6 (rationale).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from src.market_risk.ws_schemas import (
    ComplianceEnvelope,
    CompliancePayload,
    NLIStatus,
    Rationale,
    RationaleRetractedEnvelope,
    RationaleRetractedPayload,
    RationaleTokEnvelope,
    RationaleTokPayload,
    RationaleVerifiedEnvelope,
    RationaleVerifiedPayload,
    ThresholdEnvelope,
    TickEnvelope,
    TradeSnapshot,
)

from .snapshot_builder import SnapshotBuilder
from .threshold_detector import RuleBoundary, ThresholdDetector
from .verdict_service import VerdictService
from .zone_hash import BucketWidths

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from src.market_risk.ws_schemas import (
        ThresholdCrossing,
        TradeIntent,
    )

    from .persistence import SessionPersistence
    from .rationale_streamer import RationaleStreamer

logger = logging.getLogger(__name__)

# Wall-clock budget for crossing-to-verdict on the single-jurisdiction path.
# Spec §10 says P99 < 500 ms end-to-end; the in-process path should be far below
# that. We use this only as an observability target.
SYNC_VERDICT_BUDGET_MS = 100.0


SeqProvider = "Callable[[], int]"
EnvelopeEmitter = "Callable[[bytes], Awaitable[None]]"


@dataclass
class PipelineConfig:
    """Static configuration for a session — rules, widths, paths."""

    boundaries: list[RuleBoundary]
    rule_texts: dict[str, str]
    cross_border_rule_ids: set[str] = field(default_factory=set)
    widths: BucketWidths = field(default_factory=BucketWidths)


@dataclass
class LiveSessionPipeline:
    """Stateful per-intent pipeline. One instance per `Session`."""

    intent: TradeIntent
    builder: SnapshotBuilder
    detector: ThresholdDetector
    verdicts: VerdictService
    streamer: RationaleStreamer
    persistence: SessionPersistence
    next_seq: Callable[[], int]
    emit_tick: Callable[[bytes], Awaitable[None]]
    emit_audit: Callable[[bytes], Awaitable[None]]

    # Last known book state — needed because real Binance ships bid/ask in one
    # frame and depth in another. The vertical-slice fixture coalesces them.
    _last_mark: Decimal = Decimal("0")
    _last_bid: Decimal = Decimal("0")
    _last_ask: Decimal = Decimal("0")
    _last_depth_bid: list[tuple[Decimal, Decimal]] = field(default_factory=list)
    _last_depth_ask: list[tuple[Decimal, Decimal]] = field(default_factory=list)
    _last_funding: float | None = None

    # Spawned rationale tasks; we await them on shutdown so nothing leaks.
    _rationale_tasks: set[asyncio.Task[None]] = field(default_factory=set)

    # Latency observability — wall-clock per crossing.
    last_verdict_latency_ms: float | None = None

    async def handle_frame(self, frame: dict[str, Any]) -> None:
        """Dispatch one bus message through the pipeline.

        Unknown frame types are ignored so an ingestor can publish a mixed
        stream without the pipeline knowing every Binance feed name.
        """
        ftype = frame.get("type")
        if ftype == "kline_close":
            close = float(frame["close"])
            self.builder.update_kline(close)
            return
        if ftype == "snapshot_inputs":
            self._absorb_snapshot_inputs(frame)
            await self._on_book_update()
            return
        # Real-Binance frame names — best-effort, not exhaustive in this slice.
        if frame.get("e") == "kline":
            k = frame.get("k", {})
            with contextlib.suppress(KeyError, ValueError, TypeError):
                self.builder.update_kline(float(k["c"]))
            return

    def _absorb_snapshot_inputs(self, frame: dict[str, Any]) -> None:
        self._last_mark = Decimal(str(frame["mark"]))
        self._last_bid = Decimal(str(frame["bid"]))
        self._last_ask = Decimal(str(frame["ask"]))
        self._last_depth_bid = [
            (Decimal(str(p)), Decimal(str(s))) for p, s in frame.get("depth_bid", [])
        ]
        self._last_depth_ask = [
            (Decimal(str(p)), Decimal(str(s))) for p, s in frame.get("depth_ask", [])
        ]
        funding = frame.get("funding_rate")
        self._last_funding = float(funding) if funding is not None else None

    async def _on_book_update(self) -> None:
        if self._last_mark <= 0 or self._last_bid <= 0 or self._last_ask <= 0:
            return
        size = self.intent.notional_usd / self._last_mark if self._last_mark > 0 else Decimal("0")
        snapshot = self.builder.build(
            mark_price=self._last_mark,
            bid=self._last_bid,
            ask=self._last_ask,
            size=size,
            depth_bid_levels=self._last_depth_bid,
            depth_ask_levels=self._last_depth_ask,
            funding_rate=self._last_funding,
        )

        # 1. Emit market-data tick envelope — drop-newest lane (rate-limited
        #    upstream by the ingestor; not safety-critical).
        tick = TickEnvelope(seq=self.next_seq(), ts=snapshot.ts, payload=snapshot)
        await self.emit_tick(tick.model_dump_json().encode())

        # 2. Detect crossings.
        notional = float(self.intent.notional_usd)
        crossings = self.detector.detect(
            snapshot,
            notional_usd=notional,
            position_pct=self._position_pct(snapshot, notional),
        )
        if not crossings:
            return

        # 3. For each crossing: persist + emit verdict envelopes (audit lane,
        #    no drop), then dispatch the rationale stream concurrently.
        for crossing in crossings:
            await self._handle_crossing(snapshot, crossing)

    def _position_pct(self, snapshot: TradeSnapshot, notional: float) -> float:
        # Position-as-fraction-of-notional is a placeholder for the real
        # position-pct (which requires portfolio context). For Phase 1 we
        # surface 0 so the bucket is stable; a real position model lands later.
        del snapshot, notional  # noqa: F841 - documented intentionally unused
        return 0.0

    async def _handle_crossing(
        self, snapshot: TradeSnapshot, crossing: ThresholdCrossing
    ) -> None:
        verdict_start = time.perf_counter()

        # Persist the snapshot first so the audit trail has the inputs that
        # produced the crossing.
        try:
            self.persistence.record_snapshot(snapshot)
            self.persistence.record_crossing(crossing)
        except Exception as exc:  # noqa: BLE001
            logger.warning("persistence_failed", extra={"error": str(exc)})

        # Resolve the verdict via the dual-path service. For single-juris this
        # is in-process and sub-millisecond; for cross-border it dispatches to
        # Temporal. The verdict is already encoded on `crossing` because the
        # detector computed it — but for safety on the audit path we re-resolve.
        rule_b = next(
            (b for b in self.detector.boundaries if b.rule_id == crossing.rule_id),
            None,
        )
        if rule_b is not None:
            verified_verdict = await self.verdicts.resolve(snapshot, rule_b)
            if verified_verdict != crossing.new_verdict:
                # Detector and verdict service disagreed; trust the service.
                crossing = crossing.model_copy(update={"new_verdict": verified_verdict})

        # 3a. Verdict envelopes — audit lane, MUST appear before any rationale.
        compliance_env = ComplianceEnvelope(
            seq=self.next_seq(),
            ts=crossing.ts,
            payload=CompliancePayload(
                crossing_id=crossing.crossing_id,
                prior_verdict=crossing.prior_verdict,
                new_verdict=crossing.new_verdict,
                citation=crossing.citation,
            ),
        )
        threshold_env = ThresholdEnvelope(
            seq=self.next_seq(),
            ts=crossing.ts,
            payload=crossing,
        )
        await self.emit_audit(compliance_env.model_dump_json().encode())
        await self.emit_audit(threshold_env.model_dump_json().encode())

        self.last_verdict_latency_ms = (time.perf_counter() - verdict_start) * 1000.0
        if self.last_verdict_latency_ms > SYNC_VERDICT_BUDGET_MS:
            logger.warning(
                "verdict_latency_over_budget",
                extra={
                    "crossing_id": crossing.crossing_id,
                    "latency_ms": self.last_verdict_latency_ms,
                    "budget_ms": SYNC_VERDICT_BUDGET_MS,
                },
            )

        # 4. Dispatch rationale stream concurrently — must NOT block the next
        #    tick or another crossing.
        task = asyncio.create_task(
            self._run_rationale(crossing),
            name=f"rationale-{crossing.crossing_id[:8]}",
        )
        self._rationale_tasks.add(task)
        task.add_done_callback(self._rationale_tasks.discard)

    async def _run_rationale(self, crossing: ThresholdCrossing) -> None:
        buffer = ""
        rationale_id: str | None = None
        final_status: NLIStatus = NLIStatus.STREAMING
        final_score: float | None = None
        retraction_reason: str | None = None

        try:
            async for event in self.streamer.stream(crossing):
                rationale_id = event.rationale_id
                if event.token is not None:
                    buffer += event.token
                    env = RationaleTokEnvelope(
                        seq=self.next_seq(),
                        ts=datetime.now(tz=UTC),
                        payload=RationaleTokPayload(
                            rationale_id=event.rationale_id,
                            crossing_id=event.crossing_id,
                            token=event.token,
                        ),
                    )
                    await self.emit_audit(env.model_dump_json().encode())
                    continue
                if event.status == NLIStatus.VERIFIED and event.final_score is not None:
                    final_status = NLIStatus.VERIFIED
                    final_score = event.final_score
                    v_env = RationaleVerifiedEnvelope(
                        seq=self.next_seq(),
                        ts=datetime.now(tz=UTC),
                        payload=RationaleVerifiedPayload(
                            rationale_id=event.rationale_id,
                            crossing_id=event.crossing_id,
                            final_score=event.final_score,
                        ),
                    )
                    await self.emit_audit(v_env.model_dump_json().encode())
                elif event.status == NLIStatus.RETRACTED and event.final_score is not None:
                    final_status = NLIStatus.RETRACTED
                    final_score = event.final_score
                    retraction_reason = event.reason
                    r_env = RationaleRetractedEnvelope(
                        seq=self.next_seq(),
                        ts=datetime.now(tz=UTC),
                        payload=RationaleRetractedPayload(
                            rationale_id=event.rationale_id,
                            crossing_id=event.crossing_id,
                            final_score=event.final_score,
                            reason=event.reason or "unknown",
                        ),
                    )
                    await self.emit_audit(r_env.model_dump_json().encode())
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "rationale_stream_failed",
                extra={"crossing_id": crossing.crossing_id, "error": str(exc)},
            )

        if rationale_id is None:
            return
        try:
            self.persistence.record_rationale(
                Rationale(
                    rationale_id=rationale_id,
                    crossing_id=crossing.crossing_id,
                    content=buffer,
                    status=final_status,
                    final_score=final_score,
                    retraction_reason=retraction_reason,
                    completed_at=datetime.now(tz=UTC),
                ),
                intent_id=crossing.intent_id,
            )
            if final_score is not None:
                self.persistence.record_nli_check(
                    nli_check_id=str(uuid.uuid4()),
                    rationale_id=rationale_id,
                    intent_id=crossing.intent_id,
                    ts=datetime.now(tz=UTC),
                    token_offset=len(buffer),
                    entailment_score=final_score,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "rationale_persistence_failed",
                extra={"crossing_id": crossing.crossing_id, "error": str(exc)},
            )

    async def join(self) -> None:
        """Await all in-flight rationale tasks. Call from Session.stop()."""
        tasks = list(self._rationale_tasks)
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t


def build_pipeline(
    *,
    intent: TradeIntent,
    config: PipelineConfig,
    persistence: SessionPersistence,
    streamer: RationaleStreamer,
    next_seq: Callable[[], int],
    emit_tick: Callable[[bytes], Awaitable[None]],
    emit_audit: Callable[[bytes], Awaitable[None]],
    temporal_executor: object | None = None,
) -> LiveSessionPipeline:
    """Assemble the pipeline for one intent. The verdict predicate used by the
    detector is the in-process sync path (sub-millisecond); the multi-jurisdiction
    Temporal path runs inside `verdicts.resolve` and never on the verdict
    critical path of the detector itself.
    """
    builder = SnapshotBuilder(intent=intent)
    verdicts = VerdictService(
        cross_border_rule_ids=set(config.cross_border_rule_ids),
        temporal_executor=temporal_executor,  # type: ignore[arg-type]
    )
    detector = ThresholdDetector(
        boundaries=list(config.boundaries),
        verdict_for=verdicts.sync_verdict,
        widths=config.widths,
    )

    return LiveSessionPipeline(
        intent=intent,
        builder=builder,
        detector=detector,
        verdicts=verdicts,
        streamer=streamer,
        persistence=persistence,
        next_seq=next_seq,
        emit_tick=emit_tick,
        emit_audit=emit_audit,
    )


__all__ = [
    "SYNC_VERDICT_BUDGET_MS",
    "LiveSessionPipeline",
    "PipelineConfig",
    "build_pipeline",
]
