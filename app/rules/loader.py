"""Loads and validates the YAML rule base.

Validation is strict on purpose: a malformed rule base must fail at startup (or
on first use) with a clear message rather than silently producing wrong verdicts
about a tenant's lease.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core.config import get_settings
from app.core.errors import RuleConfigurationError
from app.models.clause import ClauseEntities
from app.models.enums import ClauseCategory, RuleOperator, Severity
from app.models.rules import RuleBase, RuleDefinition

logger = logging.getLogger(__name__)

_COMPARISON_OPERATORS = {
    RuleOperator.GREATER_THAN,
    RuleOperator.GREATER_OR_EQUAL,
    RuleOperator.LESS_THAN,
    RuleOperator.LESS_OR_EQUAL,
    RuleOperator.EQUALS,
    RuleOperator.NOT_EQUALS,
}


def load_rule_base(path: Path | None = None) -> RuleBase:
    """Parse and validate ``rules.yaml`` into a :class:`RuleBase`."""
    rules_path = path or get_settings().rules_file
    try:
        raw_text = rules_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuleConfigurationError(
            f"Rule file could not be read: {rules_path.name}",
            details={"path": str(rules_path)},
        ) from exc

    try:
        payload = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise RuleConfigurationError(
            f"Rule file is not valid YAML: {exc}",
            details={"path": str(rules_path)},
        ) from exc

    if not isinstance(payload, dict):
        raise RuleConfigurationError("Rule file must contain a mapping at the top level.")

    meta = payload.get("meta") or {}
    try:
        rule_base = RuleBase(
            statute=meta["statute"],
            scoring=meta["scoring"],
            rules=payload.get("rules") or [],
        )
    except KeyError as exc:
        raise RuleConfigurationError(
            f"Rule file is missing required key: {exc}", details={"path": str(rules_path)}
        ) from exc
    except Exception as exc:  # pydantic ValidationError
        raise RuleConfigurationError(
            "Rule file failed validation.",
            details={"error": str(exc).splitlines()[:12]},
        ) from exc

    _validate_rule_base(rule_base)
    logger.info(
        "loaded %s rules for %s", len(rule_base.rules), rule_base.statute.short_name
    )
    return rule_base


def _validate_rule_base(rule_base: RuleBase) -> None:
    """Cross-rule invariants that pydantic cannot express per field."""
    seen: dict[str, RuleDefinition] = {}
    entity_fields = set(ClauseEntities.model_fields)
    problems: list[str] = []

    for rule in rule_base.rules:
        if rule.id in seen:
            problems.append(f"{rule.id}: duplicate rule id")
        seen[rule.id] = rule

        if rule.field not in entity_fields:
            problems.append(f"{rule.id}: unknown entity field '{rule.field}'")

        if rule.operator in _COMPARISON_OPERATORS and rule.value is None:
            problems.append(f"{rule.id}: operator '{rule.operator.value}' needs a value")
        if rule.operator is RuleOperator.WITHIN_RANGE and rule.value_max is None:
            problems.append(f"{rule.id}: 'within_range' needs value_max")
        if rule.severity is Severity.INFO and rule.penalty_group is None:
            problems.append(f"{rule.id}: informational rules should set penalty_group")

        if not rule.tamil.strip():
            problems.append(f"{rule.id}: missing Tamil explanation")
        if len(rule.statute.quote.strip()) < 20:
            problems.append(f"{rule.id}: statute quote looks empty")

        for category in rule.categories:
            if not isinstance(category, ClauseCategory):
                problems.append(f"{rule.id}: invalid category '{category}'")

    missing_weights = [
        category.value
        for category in ClauseCategory
        if category not in rule_base.scoring.category_importance
    ]
    if missing_weights:
        problems.append(f"scoring.category_importance missing: {', '.join(missing_weights)}")

    bands = rule_base.scoring.risk_bands
    if not bands:
        problems.append("scoring.risk_bands is empty")
    else:
        ordered = sorted(bands, key=lambda band: band.min_score)
        if ordered[0].min_score != 0 or ordered[-1].max_score < 100:
            problems.append("scoring.risk_bands must cover 0..100")

    if problems:
        raise RuleConfigurationError(
            "Rule base failed semantic validation.",
            details={"problems": problems[:20], "count": len(problems)},
        )


@lru_cache(maxsize=1)
def get_rule_base() -> RuleBase:
    """Process-wide cached rule base."""
    return load_rule_base()


def clear_rule_base_cache() -> None:
    get_rule_base.cache_clear()


def export_rule_catalogue(rule_base: RuleBase | None = None) -> dict[str, Any]:
    """Serialise the rule base for the ``/rules`` transparency endpoint."""
    base = rule_base or get_rule_base()
    return {
        "statute": base.statute.model_dump(),
        "scoring": {
            "version": base.scoring.version,
            "severity_points": {k.value: v for k, v in base.scoring.severity_points.items()},
            "category_importance": {
                k.value: v for k, v in base.scoring.category_importance.items()
            },
            "breadth_bonus_per_violation": base.scoring.breadth_bonus_per_violation,
            "breadth_bonus_cap": base.scoring.breadth_bonus_cap,
            "risk_bands": [band.model_dump(mode="json") for band in base.scoring.risk_bands],
        },
        "rule_count": len(base.rules),
        "rules": [rule.model_dump(mode="json") for rule in base.rules],
    }
