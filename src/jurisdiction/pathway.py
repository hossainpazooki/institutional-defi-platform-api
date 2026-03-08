"""Pathway synthesis for cross-border compliance.

Generates ordered compliance pathways with step dependencies and timeline estimates.
From Workbench rules/jurisdiction/pathway.py.
"""

from __future__ import annotations

from typing import Any

from .constants import STEP_DEPENDENCIES, STEP_TIMELINES


def synthesize_pathway(
    results: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    equivalences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Synthesize ordered compliance pathway from evaluation results.

    Generates step-by-step authorization roadmap:
    1. Order by dependencies (prerequisites first)
    2. Order by jurisdiction (issuer home before targets)
    3. Apply equivalence waivers where applicable
    """
    steps: list[dict[str, Any]] = []
    step_id = 1

    sorted_results = sorted(
        results,
        key=lambda r: (0 if "issuer" in r.get("role", "") else 1, r["jurisdiction"]),
    )

    for result in sorted_results:
        jurisdiction = result["jurisdiction"]
        regime_id = result.get("regime_id", "unknown")

        for obligation in result.get("obligations", []):
            obl_id = obligation.get("id", "")

            step = {
                "step_id": step_id,
                "jurisdiction": jurisdiction,
                "regime": regime_id,
                "obligation_id": obl_id,
                "action": obligation.get("description", obl_id),
                "source": obligation.get("source_ref") or obligation.get("source"),
                "prerequisites": [],
                "timeline": STEP_TIMELINES.get(
                    obl_id,
                    {"min_days": 30, "max_days": 90, "description": "Compliance step"},
                ),
                "status": "pending",
                "waiver_reason": None,
            }

            if obl_id in STEP_DEPENDENCIES:
                for prereq_id in STEP_DEPENDENCIES[obl_id]:
                    prereq_step = next(
                        (s for s in steps if s["obligation_id"] == prereq_id),
                        None,
                    )
                    if prereq_step:
                        step["prerequisites"].append(prereq_step["step_id"])

            steps.append(step)
            step_id += 1

    for equiv in equivalences:
        if equiv.get("status") == "equivalent":
            for step in steps:
                if step["jurisdiction"] == equiv.get("to") and step["obligation_id"] in [
                    "obtain_authorization",
                    "submit_whitepaper",
                ]:
                    step["status"] = "waived"
                    step["waiver_reason"] = f"Equivalent recognition from {equiv.get('from')} ({equiv.get('scope')})"

    return steps


def aggregate_obligations(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate and deduplicate obligations across all jurisdictions."""
    seen: set[tuple[str, str]] = set()
    obligations = []

    for result in results:
        for obl in result.get("obligations", []):
            key = (obl.get("id", ""), result.get("jurisdiction", ""))
            if key not in seen:
                seen.add(key)
                obligations.append(
                    {
                        **obl,
                        "jurisdiction": result.get("jurisdiction"),
                        "regime": result.get("regime_id"),
                    }
                )

    return sorted(obligations, key=lambda o: (o.get("jurisdiction", ""), o.get("id", "")))


def estimate_timeline(pathway: list[dict[str, Any]]) -> str:
    """Calculate overall timeline estimate from pathway."""
    if not pathway:
        return "N/A"

    total_max_days = sum(
        step.get("timeline", {}).get("max_days", 30) for step in pathway if step.get("status") != "waived"
    )

    estimated_days = int(total_max_days * 0.6)

    if estimated_days < 30:
        return "< 1 month"
    elif estimated_days < 90:
        return "1-3 months"
    elif estimated_days < 180:
        return "3-6 months"
    else:
        return "6-12 months"


def get_critical_path(pathway: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Identify the critical path through the compliance pathway."""
    if not pathway:
        return []

    step_by_id: dict[int, dict[str, Any]] = {s["step_id"]: s for s in pathway}
    path_lengths: dict[int, int] = {}

    def get_path_length(step_id: int) -> int:
        if step_id in path_lengths:
            return path_lengths[step_id]

        step = step_by_id.get(step_id)
        if not step:
            return 0

        prereqs: list[int] = step.get("prerequisites", [])
        timeline_days: int = int(step.get("timeline", {}).get("max_days", 30))
        if not prereqs:
            length = timeline_days
        else:
            max_prereq = max(get_path_length(p) for p in prereqs)
            length = max_prereq + timeline_days

        path_lengths[step_id] = length
        return length

    for step in pathway:
        get_path_length(step["step_id"])

    if not path_lengths:
        return []

    critical_end: int = max(path_lengths, key=lambda k: path_lengths[k])

    critical_path: list[dict[str, Any]] = []
    current: int | None = critical_end

    while current is not None:
        current_step = step_by_id.get(current)
        if not current_step:
            break
        critical_path.append(current_step)
        prereqs_list: list[int] = current_step.get("prerequisites", [])
        current = max(prereqs_list, key=lambda p: path_lengths.get(p, 0)) if prereqs_list else None

    return list(reversed(critical_path))
