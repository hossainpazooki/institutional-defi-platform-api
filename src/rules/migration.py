"""Migration utilities for loading YAML rules into the database."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import yaml

from src.rules.service import ConditionGroupSpec, ConditionSpec, Rule, RuleLoader

if TYPE_CHECKING:
    from pathlib import Path


def extract_premise_keys(condition_group: ConditionGroupSpec | None) -> list[str]:
    """Extract premise keys from a condition group for O(1) lookup index."""
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


def migrate_yaml_rules(
    rules_dir: str | Path,
    clear_existing: bool = False,
) -> dict[str, Any]:
    """Migrate YAML rules from directory to database."""
    from sqlalchemy import text

    from src.database import get_db
    from src.rules.repository import RuleRepository

    rule_repo = RuleRepository()

    if clear_existing:
        with get_db() as conn:
            conn.execute(text("DELETE FROM rule_premise_index"))
            conn.execute(text("DELETE FROM rules"))
            conn.commit()

    loader = RuleLoader(rules_dir)
    try:
        rules = loader.load_directory()
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to load rules directory: {e}",
            "rules_migrated": 0,
            "errors": [str(e)],
        }

    result: dict[str, Any] = {
        "success": True,
        "rules_migrated": 0,
        "rules_updated": 0,
        "premise_keys_indexed": 0,
        "errors": [],
    }

    for rule in rules:
        try:
            yaml_content = _rule_to_yaml(rule)
            existing = rule_repo.get_rule(rule.rule_id)

            rule_repo.save_rule(
                rule_id=rule.rule_id,
                content_yaml=yaml_content,
                source_document_id=rule.source.document_id if rule.source else None,
                source_article=rule.source.article if rule.source else None,
            )

            if existing:
                result["rules_updated"] += 1
            else:
                result["rules_migrated"] += 1

            premise_keys = extract_premise_keys(rule.applies_if)
            if premise_keys:
                rule_repo.update_premise_index(rule.rule_id, premise_keys)
                result["premise_keys_indexed"] += len(premise_keys)

        except Exception as e:
            result["errors"].append(f"{rule.rule_id}: {e}")

    if result["errors"]:
        result["success"] = len(result["errors"]) < len(rules)

    return result


def _rule_to_yaml(rule: Rule) -> str:
    """Convert a Rule object back to YAML string."""
    data = rule.model_dump(mode="json", exclude_none=True, exclude_unset=True)
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)


def sync_rule_to_db(rule: Rule, rule_repo=None) -> bool:
    """Sync a single rule to the database."""
    from src.rules.repository import RuleRepository

    if rule_repo is None:
        rule_repo = RuleRepository()

    yaml_content = _rule_to_yaml(rule)

    rule_repo.save_rule(
        rule_id=rule.rule_id,
        content_yaml=yaml_content,
        source_document_id=rule.source.document_id if rule.source else None,
        source_article=rule.source.article if rule.source else None,
    )

    premise_keys = extract_premise_keys(rule.applies_if)
    if premise_keys:
        rule_repo.update_premise_index(rule.rule_id, premise_keys)

    return True
