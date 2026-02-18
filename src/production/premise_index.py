"""Premise index builder for O(1) rule lookup.

The premise index is an inverted index mapping fact patterns to rule IDs,
enabling constant-time lookup of potentially applicable rules.

From Workbench storage/retrieval/compiler/premise_index.py.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.ontology.jurisdiction import JurisdictionCode
from src.rules.service import ConditionGroupSpec, ConditionSpec, Rule

from .schemas import RuleIR


class PremiseIndexBuilder:
    """Builds and manages the premise index for rule lookup.

    Supports both in-memory and database-backed operations.
    Extended with jurisdiction support for v4 architecture.
    """

    def __init__(self) -> None:
        self._index: dict[str, set[str]] = defaultdict(set)
        self._rule_jurisdictions: dict[str, str] = {}
        self._rule_regimes: dict[str, str] = {}

    def build(self, rules: list[Rule] | list[RuleIR]) -> dict[str, list[str]]:
        """Build premise index from a list of rules."""
        self._index.clear()
        self._rule_jurisdictions.clear()
        self._rule_regimes.clear()

        for rule in rules:
            if isinstance(rule, RuleIR):
                for key in rule.premise_keys:
                    self._index[key].add(rule.rule_id)
                if rule.jurisdiction_code:
                    self._rule_jurisdictions[rule.rule_id] = (
                        rule.jurisdiction_code.value
                        if isinstance(rule.jurisdiction_code, JurisdictionCode)
                        else rule.jurisdiction_code
                    )
                self._rule_regimes[rule.rule_id] = rule.regime_id
            else:
                keys = self._extract_premise_keys(rule.applies_if)
                for key in keys:
                    self._index[key].add(rule.rule_id)
                jurisdiction = getattr(rule, "jurisdiction", JurisdictionCode.EU)
                if isinstance(jurisdiction, JurisdictionCode):
                    self._rule_jurisdictions[rule.rule_id] = jurisdiction.value
                else:
                    self._rule_jurisdictions[rule.rule_id] = str(jurisdiction)
                self._rule_regimes[rule.rule_id] = getattr(rule, "regime_id", "mica_2023")

        return {k: list(v) for k, v in self._index.items()}

    def add_rule(self, rule: Rule | RuleIR) -> list[str]:
        """Add a single rule to the index."""
        rule_id = rule.rule_id

        if isinstance(rule, RuleIR):
            keys = rule.premise_keys
            if rule.jurisdiction_code:
                self._rule_jurisdictions[rule_id] = (
                    rule.jurisdiction_code.value
                    if isinstance(rule.jurisdiction_code, JurisdictionCode)
                    else rule.jurisdiction_code
                )
            self._rule_regimes[rule_id] = rule.regime_id
        else:
            keys = self._extract_premise_keys(rule.applies_if)
            jurisdiction = getattr(rule, "jurisdiction", JurisdictionCode.EU)
            if isinstance(jurisdiction, JurisdictionCode):
                self._rule_jurisdictions[rule_id] = jurisdiction.value
            else:
                self._rule_jurisdictions[rule_id] = str(jurisdiction)
            self._rule_regimes[rule_id] = getattr(rule, "regime_id", "mica_2023")

        for key in keys:
            self._index[key].add(rule_id)

        return keys

    def remove_rule(self, rule_id: str) -> None:
        """Remove a rule from the index."""
        for key in list(self._index.keys()):
            self._index[key].discard(rule_id)
            if not self._index[key]:
                del self._index[key]

        self._rule_jurisdictions.pop(rule_id, None)
        self._rule_regimes.pop(rule_id, None)

    def lookup(self, facts: dict[str, Any]) -> set[str]:
        """Find all rules that might apply to given facts."""
        fact_keys = self._facts_to_keys(facts)

        if not fact_keys:
            return set()

        candidates: set[str] = set()
        for key in fact_keys:
            if key in self._index:
                candidates.update(self._index[key])

        return candidates

    def lookup_intersection(self, facts: dict[str, Any]) -> set[str]:
        """Find rules that match ALL applicable fact patterns."""
        fact_keys = self._facts_to_keys(facts)

        if not fact_keys:
            return set()

        matching_keys = [k for k in fact_keys if k in self._index]
        if not matching_keys:
            return set()

        result = self._index[matching_keys[0]].copy()
        for key in matching_keys[1:]:
            result &= self._index[key]

        return result

    def lookup_by_jurisdiction(
        self,
        facts: dict[str, Any],
        jurisdiction: str | JurisdictionCode,
    ) -> set[str]:
        """Find rules matching facts filtered by jurisdiction.

        O(1) lookup via premise index + jurisdiction filter.
        Primary lookup method for v4 multi-jurisdiction queries.
        """
        candidates = self.lookup(facts)

        if isinstance(jurisdiction, JurisdictionCode):
            jurisdiction = jurisdiction.value

        return {rule_id for rule_id in candidates if self._rule_jurisdictions.get(rule_id) == jurisdiction}

    def lookup_by_regime(
        self,
        facts: dict[str, Any],
        regime_id: str,
    ) -> set[str]:
        """Find rules matching facts filtered by regulatory regime."""
        candidates = self.lookup(facts)

        return {rule_id for rule_id in candidates if self._rule_regimes.get(rule_id) == regime_id}

    def lookup_by_jurisdiction_key(
        self,
        jurisdiction: str | JurisdictionCode,
    ) -> set[str]:
        """Find all rules for a specific jurisdiction using premise key."""
        if isinstance(jurisdiction, JurisdictionCode):
            jurisdiction = jurisdiction.value

        key = f"jurisdiction:{jurisdiction}"
        return self._index.get(key, set()).copy()

    def lookup_intersection_by_jurisdiction(
        self,
        premise_keys: list[str],
        jurisdiction: str | JurisdictionCode,
    ) -> set[str]:
        """Find rules matching ALL premise keys filtered by jurisdiction."""
        if not premise_keys:
            return self.lookup_by_jurisdiction_key(jurisdiction)

        if isinstance(jurisdiction, JurisdictionCode):
            jurisdiction = jurisdiction.value

        keys_with_jurisdiction = premise_keys + [f"jurisdiction:{jurisdiction}"]

        first_key = keys_with_jurisdiction[0]
        if first_key not in self._index:
            return set()

        result = self._index[first_key].copy()
        for key in keys_with_jurisdiction[1:]:
            if key in self._index:
                result &= self._index[key]
            else:
                return set()

        return result

    def get_jurisdictions(self) -> set[str]:
        """Get all unique jurisdictions in the index."""
        return set(self._rule_jurisdictions.values())

    def get_rules_by_jurisdiction(self) -> dict[str, list[str]]:
        """Get rules grouped by jurisdiction."""
        result: dict[str, list[str]] = defaultdict(list)
        for rule_id, jurisdiction in self._rule_jurisdictions.items():
            result[jurisdiction].append(rule_id)
        return dict(result)

    def get_all_keys(self) -> list[str]:
        """Get all premise keys in the index."""
        return list(self._index.keys())

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the index."""
        if not self._index:
            return {
                "total_keys": 0,
                "total_rules": 0,
                "avg_rules_per_key": 0,
                "max_rules_per_key": 0,
            }

        rule_counts = [len(v) for v in self._index.values()]
        all_rules = set()
        for rules in self._index.values():
            all_rules.update(rules)

        return {
            "total_keys": len(self._index),
            "total_rules": len(all_rules),
            "avg_rules_per_key": sum(rule_counts) / len(rule_counts),
            "max_rules_per_key": max(rule_counts),
            "keys_by_field": self._group_keys_by_field(),
        }

    def _group_keys_by_field(self) -> dict[str, int]:
        """Group premise keys by field name."""
        fields: dict[str, int] = defaultdict(int)
        for key in self._index:
            if ":" in key:
                field = key.split(":")[0]
                fields[field] += 1
        return dict(fields)

    def _facts_to_keys(self, facts: dict[str, Any]) -> list[str]:
        """Convert facts dict to premise keys."""
        keys = []
        for field, value in facts.items():
            if value is not None:
                keys.append(f"{field}:{value}")
                keys.append(f"{field}:*")
        return keys

    def _extract_premise_keys(self, condition_group: ConditionGroupSpec | None) -> list[str]:
        """Extract premise keys from a condition group."""
        if not condition_group:
            return []

        keys: list[str] = []

        def process_condition(cond: ConditionSpec) -> None:
            field = cond.field
            value = cond.value
            operator = cond.operator

            if operator in ("==", "="):
                keys.append(f"{field}:{value}")
            elif operator == "in" and isinstance(value, list):
                for v in value:
                    keys.append(f"{field}:{v}")
            elif operator == "exists":
                keys.append(f"{field}:*")

        def process_group(group: ConditionGroupSpec) -> None:
            conditions = group.all or group.any or []
            for item in conditions:
                if isinstance(item, ConditionSpec):
                    process_condition(item)
                elif isinstance(item, ConditionGroupSpec):
                    process_group(item)

        process_group(condition_group)
        return list(set(keys))


# Singleton instance for application-wide use
_global_index: PremiseIndexBuilder | None = None


def get_premise_index() -> PremiseIndexBuilder:
    """Get or create the global premise index."""
    global _global_index
    if _global_index is None:
        _global_index = PremiseIndexBuilder()
    return _global_index


def reset_premise_index() -> None:
    """Reset the global premise index."""
    global _global_index
    _global_index = None
