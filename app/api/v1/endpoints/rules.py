"""Rule base transparency endpoints.

Every verdict the engine returns cites a rule id. These endpoints expose the rule
that sits behind that id - threshold, operator, statute section, tenant-facing copy -
so a disagreement about an analysis can be traced to a line in ``rules.yaml``
rather than to an opaque model output.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import PipelineDep
from app.core.errors import RuleNotFoundError
from app.models.api import ErrorResponse, RuleCatalogue
from app.models.enums import ClauseCategory
from app.models.rules import RuleBase, RuleDefinition

router = APIRouter(tags=["rules"])

RuleId = Annotated[
    str,
    Path(
        description="Rule id as cited in a finding, e.g. ``DEP-001``.",
        examples=["DEP-001"],
    ),
]


@router.get(
    "/rules",
    response_model=RuleCatalogue,
    summary="The benchmark catalogue and the scoring model",
    description=(
        "The complete, machine-readable rule base: every threshold, the statutory "
        "citation behind it, the severity weights and the score bands.\n\n"
        "Useful for auditing an analysis, for showing a tenant *why* a clause was "
        "flagged, and for spotting an outdated benchmark. Filter with "
        "`?category=deposit`."
    ),
)
async def list_rules(
    pipeline: PipelineDep,
    category: Annotated[
        ClauseCategory | None,
        Query(description="Only return rules that apply to this tenancy domain."),
    ] = None,
) -> RuleCatalogue:
    base = pipeline.rule_base
    rules = base.rules if category is None else base.by_category(category)
    return _catalogue(base, rules)


@router.get(
    "/rules/{rule_id}",
    response_model=RuleDefinition,
    summary="One rule, with its statutory quote",
    responses={404: {"model": ErrorResponse, "description": "Unknown rule id"}},
)
async def get_rule(rule_id: RuleId, pipeline: PipelineDep) -> RuleDefinition:
    rule = pipeline.rule_base.by_id(rule_id)
    if rule is None:
        raise RuleNotFoundError(
            details={"rule_id": rule_id, "available": pipeline.rule_base.rule_ids()}
        )
    return rule


def _catalogue(base: RuleBase, rules: list[RuleDefinition]) -> RuleCatalogue:
    scoring = base.scoring
    return RuleCatalogue(
        statute=base.statute,
        scoring_version=scoring.version,
        severity_points={severity.value: points for severity, points in scoring.severity_points.items()},
        category_importance={
            category.value: weight for category, weight in scoring.category_importance.items()
        },
        breadth_bonus_per_violation=scoring.breadth_bonus_per_violation,
        breadth_bonus_cap=scoring.breadth_bonus_cap,
        risk_bands=sorted(scoring.risk_bands, key=lambda band: band.min_score),
        rule_count=len(rules),
        rules=rules,
    )
