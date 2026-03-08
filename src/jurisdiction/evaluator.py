"""Jurisdiction evaluator for parallel multi-jurisdiction assessment.

Implements parallel evaluation pattern with rule engine integration.
From Workbench rules/jurisdiction/evaluator.py and jurisdiction/service.py.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from src.ontology.jurisdiction import JurisdictionCode
from src.rules.service import RuleLoader

_rule_loader: RuleLoader | None = None


def _get_rule_loader() -> RuleLoader:
    """Get or create the global rule loader."""
    global _rule_loader
    if _rule_loader is None:
        from src.config import get_settings

        settings = get_settings()
        _rule_loader = RuleLoader(settings.rules_dir)
        with contextlib.suppress(FileNotFoundError):
            _rule_loader.load_directory()
    return _rule_loader


async def evaluate_jurisdiction(
    jurisdiction: str | JurisdictionCode,
    regime_id: str,
    facts: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate facts against all applicable rules in a jurisdiction."""
    from src.ontology.scenario import Scenario
    from src.rules.service import DecisionEngine

    jurisdiction_code = jurisdiction.value if isinstance(jurisdiction, JurisdictionCode) else jurisdiction

    loader = _get_rule_loader()
    engine = DecisionEngine(loader=loader)

    all_rules = loader.get_all_rules()
    jurisdiction_rules = [r for r in all_rules if r.jurisdiction.value == jurisdiction_code]

    if not jurisdiction_rules:
        return {
            "jurisdiction": jurisdiction_code,
            "regime_id": regime_id,
            "applicable_rules": 0,
            "rules_evaluated": 0,
            "decisions": [],
            "obligations": [],
            "status": "no_applicable_rules",
        }

    # Create scenario from facts — skip complex types
    safe_facts = {}
    for key, value in facts.items():
        if isinstance(value, (list, dict)):
            continue
        safe_facts[key] = value

    scenario = Scenario(**safe_facts)

    decisions = []
    all_obligations = []
    rules_evaluated = 0

    for rule in jurisdiction_rules:
        result = engine.evaluate(scenario, rule.rule_id)
        rules_evaluated += 1

        if result.applicable:
            decisions.append(
                {
                    "rule_id": rule.rule_id,
                    "decision": result.decision,
                    "trace": [
                        {
                            "node": step.node,
                            "condition": step.condition,
                            "result": step.result,
                            "value_checked": step.value_checked,
                        }
                        for step in result.trace
                    ],
                    "source": {
                        "document": rule.source.document_id if rule.source else None,
                        "article": rule.source.article if rule.source else None,
                    },
                }
            )

            for obl in result.obligations:
                all_obligations.append(
                    {
                        "id": obl.id,
                        "description": obl.description,
                        "deadline": obl.deadline,
                        "rule_id": rule.rule_id,
                        "jurisdiction": jurisdiction_code,
                    }
                )

    decision_results = [d["decision"] for d in decisions]

    if "prohibited" in decision_results or "not_authorized" in decision_results:
        status = "blocked"
    elif "non_compliant" in decision_results:
        status = "requires_action"
    elif not decisions:
        status = "no_applicable_rules"
    else:
        status = "compliant"

    return {
        "jurisdiction": jurisdiction_code,
        "regime_id": regime_id,
        "applicable_rules": len(jurisdiction_rules),
        "rules_evaluated": rules_evaluated,
        "decisions": decisions,
        "obligations": all_obligations,
        "status": status,
    }


async def evaluate_multiple_jurisdictions(
    jurisdictions: list[tuple[str, str]],
    facts: dict[str, Any],
) -> list[dict[str, Any]]:
    """Evaluate facts across multiple jurisdictions in parallel."""
    tasks = [evaluate_jurisdiction(jurisdiction, regime_id, facts) for jurisdiction, regime_id in jurisdictions]

    return await asyncio.gather(*tasks)


def evaluate_jurisdiction_sync(
    jurisdiction: str | JurisdictionCode,
    regime_id: str,
    facts: dict[str, Any],
) -> dict[str, Any]:
    """Synchronous wrapper for evaluate_jurisdiction."""
    return asyncio.run(evaluate_jurisdiction(jurisdiction, regime_id, facts))
