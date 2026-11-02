"""Fix-it Kit: explanation, counter-clause and a ready-to-send email.

All copy is templated from ``rules.yaml`` and formatted deterministically, so the
output is reproducible and reviewable by a lawyer. An optional LLM polish step can
rewrite the prose in the tenant's voice, but it is off by default and never
touches the counter-clause text (which must stay legally precise).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings, get_settings
from app.models.analysis import EmailDraft, FixItKit
from app.models.clause import Clause
from app.models.enums import ClauseCategory
from app.models.rules import RuleBase, RuleDefinition, RuleEvaluation
from app.rules.loader import get_rule_base

logger = logging.getLogger(__name__)

CATEGORY_LABELS: dict[ClauseCategory, str] = {
    ClauseCategory.DEPOSIT: "security deposit",
    ClauseCategory.LOCK_IN: "lock-in period",
    ClauseCategory.EVICTION: "eviction and notice",
    ClauseCategory.RENT_HIKE: "rent revision",
    ClauseCategory.ENTRY_RIGHTS: "landlord entry rights",
    ClauseCategory.MAINTENANCE: "repairs and maintenance",
    ClauseCategory.GENERAL: "formal requirements",
}

_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


@dataclass
class PartyContext:
    """Optional names used only to personalise the email draft.

    Deliberately not persisted anywhere: it is request-scoped and never logged.
    """

    tenant_name: str | None = None
    landlord_name: str | None = None
    premises: str | None = None
    monthly_rent_inr: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class FixItKitBuilder:
    """Builds remediation kits from rule evaluations."""

    def __init__(self, rule_base: RuleBase | None = None, settings: Settings | None = None) -> None:
        self.rule_base = rule_base or get_rule_base()
        self.settings = settings or get_settings()

    # -- public API ---------------------------------------------------------
    def build(
        self,
        clause: Clause,
        evaluations: Iterable[RuleEvaluation],
        parties: PartyContext | None = None,
    ) -> FixItKit | None:
        violations = [evaluation for evaluation in evaluations if evaluation.is_violation]
        if not violations:
            return None

        rules = [self._rule(evaluation.rule_id) for evaluation in violations]
        ordered_rules = [rule for rule in rules if rule is not None]
        if not ordered_rules:
            return None
        ordered_rules.sort(key=lambda rule: rule.severity.rank, reverse=True)
        primary = ordered_rules[0]

        context = self._context(clause, primary, parties)
        explanation_en = self._format(primary.explanation, context).strip()
        explanation_ta = self._format(primary.tamil, context).strip()
        counter_clause = self._format(primary.counter_clause, context).strip()

        extra_notes_en: list[str] = []
        extra_notes_ta: list[str] = []
        extra_counter: list[str] = []
        tips: list[str] = []

        seen_ids = {primary.id}
        for rule in ordered_rules[1:]:
            if rule.id in seen_ids:
                continue
            seen_ids.add(rule.id)
            extra_notes_en.append(f"{rule.title}: {self._format(rule.explanation, context).strip()}")
            extra_notes_ta.append(self._format(rule.tamil, context).strip())
            extra_counter.append(self._format(rule.counter_clause, context).strip())

        for rule in ordered_rules:
            if rule.negotiation_tip and rule.negotiation_tip not in tips:
                tips.append(rule.negotiation_tip)

        if extra_notes_en:
            explanation_en = explanation_en + "\n\n" + "\n\n".join(extra_notes_en)
        if extra_notes_ta:
            explanation_ta = explanation_ta + "\n\n" + "\n\n".join(extra_notes_ta)
        if extra_counter:
            counter_clause = counter_clause + "\n\nAlso requested:\n" + "\n\n".join(extra_counter)

        subject, body = self._email(clause, primary, counter_clause, context, parties)

        return FixItKit(
            explanation_en=explanation_en,
            explanation_ta=explanation_ta,
            counter_clause=counter_clause,
            email_subject=subject,
            email_body=body,
            negotiation_tips=tips[:4],
        )

    def build_summary_email(
        self,
        findings: list[tuple[Clause, RuleEvaluation]],
        parties: PartyContext | None = None,
    ) -> EmailDraft | None:
        """One consolidated email covering every flagged clause."""
        if not findings:
            return None
        ranked = sorted(findings, key=lambda item: item[1].penalty_points, reverse=True)[:5]
        tenant = parties.tenant_name if parties and parties.tenant_name else "[Your name]"
        landlord = parties.landlord_name if parties and parties.landlord_name else "Sir/Madam"
        premises = (
            parties.premises
            if parties and parties.premises
            else "the premises described in the draft agreement"
        )

        lines = [
            f"Dear {landlord},",
            "",
            (
                f"Thank you for sharing the draft tenancy agreement for {premises}. "
                "I have reviewed it and would like to request a few changes before signing."
            ),
            "",
            f"There are {len(ranked)} terms I would like to discuss:",
            "",
        ]
        for index, (clause, evaluation) in enumerate(ranked, start=1):
            rule = self._rule(evaluation.rule_id)
            category = CATEGORY_LABELS[clause.category]
            lines.append(f"{index}. {clause.heading} ({category}) - {evaluation.message}")
            if rule is not None:
                wording = self._format(
                    rule.counter_clause, self._context(clause, rule, parties)
                )
                lines.append(f"   Proposed wording: {_one_line(wording, limit=300)}")
            lines.append("")

        lines.extend(
            [
                (
                    "Each of these requests is grounded in the Tamil Nadu Regulation of Rights "
                    "and Responsibilities of Landlords and Tenants Act, 2017, and I am happy to "
                    "discuss wording that works for both of us."
                ),
                "",
                "Could we agree on these points and then complete the registration formalities "
                "with the Rent Authority together? I am keen to move ahead quickly.",
                "",
                "Warm regards,",
                tenant,
            ]
        )
        return EmailDraft(
            subject="Requested revisions to the draft tenancy agreement",
            body="\n".join(lines),
        )

    # -- internals ----------------------------------------------------------
    def _rule(self, rule_id: str) -> RuleDefinition | None:
        return self.rule_base.by_id(rule_id)

    @staticmethod
    def _context(
        clause: Clause,
        rule: RuleDefinition,
        parties: PartyContext | None,
    ) -> dict[str, str]:
        observed = _format_value(rule, getattr(clause.entities, rule.field, None))
        deposit_amount = clause.entities.deposit_amount_inr
        if deposit_amount is None and clause.entities.deposit_months and parties and parties.monthly_rent_inr:
            deposit_amount = clause.entities.deposit_months * parties.monthly_rent_inr
        return {
            "observed": observed,
            "threshold": "" if rule.value is None else str(rule.value),
            "unit": rule.unit or "",
            "deposit_amount": _format_inr(deposit_amount) if deposit_amount else "[amount]",
            "increase_amount": "[amount]",
            "heading": clause.heading,
            "clause_id": clause.clause_id,
            "section": rule.statute.section,
        }

    @staticmethod
    def _format(template: str, context: dict[str, str]) -> str:
        """Fill ``{placeholders}`` and leave unknown ones untouched."""

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return context.get(key, match.group(0))

        return _PLACEHOLDER_RE.sub(replace, template)

    def _email(
        self,
        clause: Clause,
        rule: RuleDefinition,
        counter_clause: str,
        context: dict[str, str],
        parties: PartyContext | None,
    ) -> tuple[str, str]:
        tenant = parties.tenant_name if parties and parties.tenant_name else "[Your name]"
        landlord = parties.landlord_name if parties and parties.landlord_name else "Sir/Madam"
        premises = (
            parties.premises
            if parties and parties.premises
            else "the premises described in the draft agreement"
        )
        category = CATEGORY_LABELS[clause.category]
        subject = (
            f"Requested change to clause {clause.order} ({category}) in the "
            f"tenancy agreement for {premises}"
        )
        excerpt = _one_line(clause.raw_text, limit=280)
        body = "\n".join(
            [
                f"Dear {landlord},",
                "",
                (
                    f"Thank you for sharing the draft tenancy agreement for {premises}. "
                    f"Before signing, I would like to request a revision to clause {clause.order} "
                    f"(\"{clause.heading}\")."
                ),
                "",
                f"The clause currently reads: \"{excerpt}\"",
                "",
                (
                    f"Under Section {rule.statute.section} of the {rule.statute.act} "
                    f"({rule.statute.heading}), the position is that {_lower_first(rule.statute.quote).rstrip('.')}. "
                    f"As drafted, the clause asks for {context['observed']}, which goes beyond that "
                    "benchmark and would leave me exposed to a term I cannot realistically accept."
                ),
                "",
                "I would be grateful if the clause could be revised as follows:",
                "",
                counter_clause,
                "",
                (
                    "The rest of the agreement would remain unchanged. I am happy to consider "
                    "alternative wording that gives you the protection you are looking for, and "
                    "I would also suggest that we register the agreement with the Rent Authority "
                    "so that both of us have a clear record."
                ),
                "",
                "Thank you for your consideration. I look forward to hearing from you.",
                "",
                "Warm regards,",
                tenant,
            ]
        )
        return subject, body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _format_value(rule: RuleDefinition, value: Any) -> str:
    if value is None:
        return "not specified"
    if isinstance(value, bool):
        return "yes" if value else "no"
    rendered = f"{value:g}" if isinstance(value, float) else str(value)
    if rule.unit and rule.unit not in {"percent"}:
        return f"{rendered} {rule.unit}"
    if rule.unit == "percent":
        return f"{rendered}%"
    return rendered


def _format_inr(value: float) -> str:
    """Format a number using Indian digit grouping (1,50,000)."""
    digits = str(int(round(value)))
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join([*groups, tail])


def _one_line(text: str, limit: int = 220) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip(' ,.;')}..."


def _lower_first(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    if text[0].isupper() and not text[:2].isupper():
        return text[0].lower() + text[1:]
    return text
