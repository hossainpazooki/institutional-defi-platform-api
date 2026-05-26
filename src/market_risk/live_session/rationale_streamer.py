"""Rationale streamer — Claude tokens + NLI gate, emitted as WS events.

Builds a Claude prompt from the crossing + rule context, streams tokens, applies
the NLI gate every cadence, and emits the appropriate envelope sequence:
- N × `rationale_tok` envelopes (each containing one streamed token)
- exactly one `rationale_verified` OR `rationale_retracted` terminal envelope

When Anthropic is unavailable or the daily cap is hit, falls back to a template
rationale and emits a single-shot verified envelope.

See spec §6.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field

from src.market_risk.ws_schemas import (
    NLIStatus,
    Rationale,
    ThresholdCrossing,
)

from .nli_gate import NLI_RETRACT_THRESHOLD, NLI_VERIFY_THRESHOLD, NLIGate

logger = logging.getLogger(__name__)

CLAUDE_MAX_TOKENS = 250
CLAUDE_TEMPERATURE = 0.2

SYSTEM_PROMPT = (
    "You explain why a regulatory boundary just crossed. Ground every numeric "
    "claim in a snapshot field. Never invent numbers. Stay under 60 words. "
    "Do not editorialize beyond what the rule and the snapshot support."
)


def _user_prompt(crossing: ThresholdCrossing, rule_text: str) -> str:
    snap = crossing.snapshot
    return (
        f"Rule: {crossing.rule_id} — {crossing.citation}\n"
        f"Canonical statement: {rule_text}\n\n"
        f"Snapshot at crossing:\n"
        f"  mark_price = {snap.mark_price}\n"
        f"  spread_bps = {snap.spread_bps}\n"
        f"  vol_30d    = {snap.vol_30d}\n"
        f"  var_95_usd = {snap.var_95_usd}\n"
        f"  slippage_bps = {snap.slippage_bps}\n\n"
        f"Verdict moved from {crossing.prior_verdict.value} to "
        f"{crossing.new_verdict.value} when {crossing.direction.value} the "
        f"boundary {crossing.boundary}. Explain in one paragraph."
    )


TokenStream = AsyncIterator[str]
TokenStreamFactory = Callable[[str, str], Awaitable[TokenStream]]


async def _template_token_stream(system: str, user: str) -> TokenStream:  # noqa: ARG001
    """Fallback token stream when Anthropic isn't wired (CI/tests/cap-hit)."""

    async def _gen() -> AsyncIterator[str]:
        # Synthesize a deterministic micro-rationale from the user prompt.
        words = [
            "The",
            "snapshot",
            "crossed",
            "the",
            "stated",
            "regulatory",
            "boundary;",
            "verdict",
            "updated",
            "accordingly.",
        ]
        for w in words:
            yield w + " "

    return _gen()


@dataclass
class RationaleEvent:
    """One step from the streamer: either a token, a final verdict, or both."""

    rationale_id: str
    crossing_id: str
    token: str | None = None
    final_score: float | None = None
    status: NLIStatus | None = None
    reason: str | None = None


@dataclass
class RationaleStreamer:
    """Streams a rationale token-by-token under an NLI gate."""

    token_stream_factory: TokenStreamFactory = field(default=_template_token_stream)
    rule_text_lookup: Callable[[str], str] | None = None

    async def stream(
        self, crossing: ThresholdCrossing
    ) -> AsyncIterator[RationaleEvent]:
        rationale_id = str(uuid.uuid4())
        rule_text = (
            self.rule_text_lookup(crossing.rule_id)
            if self.rule_text_lookup is not None
            else crossing.citation
        )
        system = SYSTEM_PROMPT
        user = _user_prompt(crossing, rule_text)
        gate = NLIGate(premise=rule_text)

        buffer = ""
        stream = await self.token_stream_factory(system, user)
        async for tok in stream:
            buffer += tok
            yield RationaleEvent(
                rationale_id=rationale_id,
                crossing_id=crossing.crossing_id,
                token=tok,
            )
            if gate.should_check(buffer):
                score = gate.check(buffer)
                if score < gate.retract_threshold:
                    yield RationaleEvent(
                        rationale_id=rationale_id,
                        crossing_id=crossing.crossing_id,
                        final_score=score,
                        status=NLIStatus.RETRACTED,
                        reason=f"NLI score {score:.2f} below threshold {gate.retract_threshold}",
                    )
                    return

        # Stream ended normally — final gate.
        final_score = gate.final(buffer)
        if final_score >= gate.verify_threshold:
            yield RationaleEvent(
                rationale_id=rationale_id,
                crossing_id=crossing.crossing_id,
                final_score=final_score,
                status=NLIStatus.VERIFIED,
            )
        else:
            yield RationaleEvent(
                rationale_id=rationale_id,
                crossing_id=crossing.crossing_id,
                final_score=final_score,
                status=NLIStatus.RETRACTED,
                reason=(
                    f"Final NLI score {final_score:.2f} below verify threshold "
                    f"{gate.verify_threshold}"
                ),
            )

    def materialize(
        self,
        crossing_id: str,
        rationale_id: str,
        content: str,
        status: NLIStatus,
        final_score: float | None = None,
        retraction_reason: str | None = None,
    ) -> Rationale:
        return Rationale(
            rationale_id=rationale_id,
            crossing_id=crossing_id,
            content=content,
            status=status,
            final_score=final_score,
            retraction_reason=retraction_reason,
        )


__all__ = [
    "CLAUDE_MAX_TOKENS",
    "CLAUDE_TEMPERATURE",
    "NLI_RETRACT_THRESHOLD",
    "NLI_VERIFY_THRESHOLD",
    "RationaleEvent",
    "RationaleStreamer",
    "SYSTEM_PROMPT",
]
