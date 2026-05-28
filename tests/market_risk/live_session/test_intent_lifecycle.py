"""Intent lifecycle status transitions — repository + registry + REST integration.

Locked semantics (this slice):

- `created → active → closed` is the happy path. `closed` is **terminal**:
  this slice does not enforce re-acquire rejection at the registry layer, but
  the repo refuses to flip `closed → active` via `mark_active`, so attempting
  to acquire a closed intent would either no-op the active mark (test below)
  or be rejected by the registry in a follow-up auth slice.
- `activated_at` stamps on the **first** transition into `active`; concurrent
  acquires never rewrite it.
- `mark_*` methods are idempotent: subsequent calls in the same status return
  `False` and leave the row alone.

Run with `--noconftest` (Py 3.14 / FastAPI conftest bug).
"""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Feature flag + offline modes before settings consumers import.
os.environ["LIVE_THRESHOLD_RATIONALE_ENABLED"] = "true"
os.environ["LIVE_SESSION_PERSISTENCE"] = "memory"
os.environ["LIVE_SESSION_INGEST"] = "fixture"

from src.config import get_settings  # noqa: E402

get_settings.cache_clear()

from src.market_risk.live_session.bootstrap import (  # noqa: E402
    shutdown_live_session_registry,
    start_live_session_registry,
)
from src.market_risk.live_session.intent_repository import (  # noqa: E402
    CreateIntentParams,
    InMemoryIntentRepository,
)
from src.market_risk.live_session.intents_router import router as intents_router  # noqa: E402
from src.market_risk.live_session.session_manager import (  # noqa: E402
    reset_session_provider,
)
from src.market_risk.live_session.ws_handler import router as ws_router  # noqa: E402
from src.market_risk.ws_schemas import (  # noqa: E402
    InvestorType,
    TradeDirection,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    """Mini app with intents + WS routers + bootstrap-wired registry/repo."""
    app = FastAPI()
    app.include_router(intents_router)
    app.include_router(ws_router)
    start_live_session_registry(app)
    return app


def _create_intent_params(asset: str = "ETHUSDT") -> CreateIntentParams:
    return CreateIntentParams(
        asset=asset,
        direction=TradeDirection.BUY,
        notional_usd=Decimal("100000"),
        venue_jurisdiction="EU",
        investor_type=InvestorType.PROFESSIONAL,
        target_jurisdictions=["EU"],
        holding_period_days=1,
    )


# ---------------------------------------------------------------------------
# 1. GET returns persisted created_at and status (no response-time stamping)
# ---------------------------------------------------------------------------


def test_get_intent_returns_persisted_created_at_and_status() -> None:
    app = _make_app()
    try:
        with TestClient(app) as client:
            post_resp = client.post(
                "/v2/intents",
                json={
                    "asset": "ETHUSDT",
                    "direction": "buy",
                    "notional_usd": "100000",
                    "venue_jurisdiction": "EU",
                    "investor_type": "professional",
                    "target_jurisdictions": ["EU"],
                    "holding_period_days": 1,
                },
            )
            assert post_resp.status_code == 201, post_resp.text
            created_at_from_post = post_resp.json()["created_at"]
            intent_id = post_resp.json()["intent_id"]
            assert post_resp.json()["status"] == "created"

            # GET returns the same `created_at` — proves it came from the row,
            # not from a fresh `datetime.now()` call.
            get_resp = client.get(f"/v2/intents/{intent_id}")
            assert get_resp.status_code == 200
            body = get_resp.json()
            assert body["created_at"] == created_at_from_post
            assert body["status"] == "created"
            assert body["activated_at"] is None
            assert body["closed_at"] is None
            assert body["last_error"] is None
    finally:
        asyncio.run(shutdown_live_session_registry(app.state.live_session_registry))


# ---------------------------------------------------------------------------
# 2. Registry marks intent active on first acquire
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registry_marks_intent_active_on_first_acquire() -> None:
    app = _make_app()
    try:
        repo: InMemoryIntentRepository = app.state.intent_repository
        registry = app.state.live_session_registry

        record = repo.create(_create_intent_params())
        assert record.status == "created"
        assert record.activated_at is None

        lease = await registry.acquire(record.intent_id)
        try:
            current = repo.get_record(record.intent_id)
            assert current is not None
            assert current.status == "active"
            assert current.activated_at is not None
            # First activation stamp is after creation.
            assert current.activated_at >= current.created_at
        finally:
            await lease.release()
    finally:
        await shutdown_live_session_registry(app.state.live_session_registry)


# ---------------------------------------------------------------------------
# 3. Registry does not close until the final release
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registry_does_not_close_until_final_release() -> None:
    app = _make_app()
    try:
        repo: InMemoryIntentRepository = app.state.intent_repository
        registry = app.state.live_session_registry

        record = repo.create(_create_intent_params())

        lease_a = await registry.acquire(record.intent_id)
        lease_b = await registry.acquire(record.intent_id)
        # Both refs share one Session — status active, not closed.
        active_record = repo.get_record(record.intent_id)
        assert active_record is not None
        assert active_record.status == "active"

        await lease_a.release()
        # One reference still alive — intent must remain active, not closed.
        still_active = repo.get_record(record.intent_id)
        assert still_active is not None
        assert still_active.status == "active"
        assert still_active.closed_at is None

        await lease_b.release()
        # Final release stops the session; intent moves to closed.
        closed = repo.get_record(record.intent_id)
        assert closed is not None
        assert closed.status == "closed"
        assert closed.closed_at is not None
        assert closed.closed_at >= (closed.activated_at or closed.created_at)
    finally:
        await shutdown_live_session_registry(app.state.live_session_registry)


# ---------------------------------------------------------------------------
# 4. Reconnect doesn't rewrite first activated_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconnect_does_not_rewrite_first_activated_at() -> None:
    """Closed-is-terminal; this test exercises "acquire twice while active".

    Two simultaneous acquires must NOT advance `activated_at`. The repository's
    `mark_active` is idempotent — subsequent calls when already-active are no-ops.
    """
    app = _make_app()
    try:
        repo: InMemoryIntentRepository = app.state.intent_repository
        registry = app.state.live_session_registry

        record = repo.create(_create_intent_params())
        lease_a = await registry.acquire(record.intent_id)
        first = repo.get_record(record.intent_id)
        assert first is not None
        first_activated = first.activated_at
        assert first_activated is not None

        # Sleep just enough to ensure any (incorrect) re-stamp would tick.
        await asyncio.sleep(0.005)

        lease_b = await registry.acquire(record.intent_id)
        second = repo.get_record(record.intent_id)
        assert second is not None
        # activated_at is unchanged — first activation wins.
        assert second.activated_at == first_activated

        await lease_a.release()
        await lease_b.release()
    finally:
        await shutdown_live_session_registry(app.state.live_session_registry)


# ---------------------------------------------------------------------------
# 5. REST reflects active and closed status across the lifecycle
# ---------------------------------------------------------------------------


def test_get_intent_reflects_active_and_closed_status() -> None:
    app = _make_app()
    try:
        with TestClient(app) as client:
            post_resp = client.post(
                "/v2/intents",
                json={
                    "asset": "ETHUSDT",
                    "direction": "buy",
                    "notional_usd": "100000",
                    "venue_jurisdiction": "EU",
                    "investor_type": "professional",
                    "target_jurisdictions": ["EU"],
                    "holding_period_days": 1,
                },
            )
            intent_id = post_resp.json()["intent_id"]
            assert client.get(f"/v2/intents/{intent_id}").json()["status"] == "created"

            with client.websocket_connect(f"/v2/ws/trade/{intent_id}") as ws:
                # Receive at least one envelope to ensure the session is up.
                ws.receive_bytes()
                mid = client.get(f"/v2/intents/{intent_id}").json()
                assert mid["status"] == "active"
                assert mid["activated_at"] is not None
                assert mid["closed_at"] is None

            # Disconnect → final lease release → status moves to closed.
            # Allow the server-side teardown a beat.
            import time

            for _ in range(40):
                body = client.get(f"/v2/intents/{intent_id}").json()
                if body["status"] == "closed":
                    break
                time.sleep(0.025)
            assert body["status"] == "closed"
            assert body["closed_at"] is not None
    finally:
        asyncio.run(shutdown_live_session_registry(app.state.live_session_registry))


# ---------------------------------------------------------------------------
# 6. mark_failed runs when session build raises during acquire
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_failed_when_session_build_raises() -> None:
    """If `_build_session` raises, status flips to `failed` and `last_error` is set."""
    app = _make_app()
    try:
        repo: InMemoryIntentRepository = app.state.intent_repository
        record = repo.create(_create_intent_params())

        registry = app.state.live_session_registry

        # Force a build failure by monkeypatching the registry's _build_session.
        def _boom(_intent: Any) -> Any:
            msg = "synthetic build failure"
            raise RuntimeError(msg)

        registry._build_session = _boom

        with pytest.raises(RuntimeError, match="synthetic build failure"):
            await registry.acquire(record.intent_id)

        failed = repo.get_record(record.intent_id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.last_error == "synthetic build failure"
    finally:
        await shutdown_live_session_registry(app.state.live_session_registry)


# ---------------------------------------------------------------------------
# Direct repo tests — idempotency and unknown-id behavior
# ---------------------------------------------------------------------------


def test_mark_active_idempotent_and_rejects_unknown() -> None:
    repo = InMemoryIntentRepository()
    record = repo.create(_create_intent_params())
    # First call: changes state.
    assert repo.mark_active(record.intent_id) is True
    first = repo.get_record(record.intent_id)
    assert first is not None
    assert first.status == "active"
    activated = first.activated_at
    # Second call: no-op, activated_at unchanged.
    assert repo.mark_active(record.intent_id) is False
    second = repo.get_record(record.intent_id)
    assert second is not None
    assert second.activated_at == activated
    # Unknown id: False.
    assert repo.mark_active("int_does_not_exist") is False


def test_mark_closed_idempotent_and_terminal() -> None:
    repo = InMemoryIntentRepository()
    record = repo.create(_create_intent_params())
    repo.mark_active(record.intent_id)
    assert repo.mark_closed(record.intent_id) is True
    closed = repo.get_record(record.intent_id)
    assert closed is not None
    assert closed.status == "closed"
    # Second close: no-op.
    assert repo.mark_closed(record.intent_id) is False
    # Cannot reactivate.
    assert repo.mark_active(record.intent_id) is False
    still_closed = repo.get_record(record.intent_id)
    assert still_closed is not None
    assert still_closed.status == "closed"


def test_mark_failed_records_reason() -> None:
    repo = InMemoryIntentRepository()
    record = repo.create(_create_intent_params())
    assert repo.mark_failed(record.intent_id, "binance unreachable") is True
    failed = repo.get_record(record.intent_id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.last_error == "binance unreachable"
    # Cannot mark active after failed.
    assert repo.mark_active(record.intent_id) is False


# ---------------------------------------------------------------------------
# Migration test — guarded same as the existing one.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    True,  # See test_intents.py for the detailed explanation.
    reason=(
        "Migration tests are blocked on Python 3.14 (a) by the repo-root "
        "alembic/ directory shadowing the installed package, and (b) by "
        "SQLModel table=True classes hitting `issubclass(<string>, Enum)` "
        "regression. CI on Python 3.13 runs `alembic upgrade head` directly."
    ),
)
def test_alembic_004_adds_lifecycle_columns() -> None:  # pragma: no cover
    pass


# ---------------------------------------------------------------------------
# Module cleanup
# ---------------------------------------------------------------------------


def teardown_module(_module: Any) -> None:
    reset_session_provider()
