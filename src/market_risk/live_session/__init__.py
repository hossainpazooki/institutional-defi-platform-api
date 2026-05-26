"""Live trading session pipeline — Binance ingest → snapshot → threshold detection
→ (verdict ‖ rationale) → WebSocket fanout.

See `dev/briefs/unified-plan.md` Phase B and `live-threshold-rationale-spec.md`.
"""

from __future__ import annotations
