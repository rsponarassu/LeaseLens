"""Deterministic, regex-based clause classification and entity extraction.

Two jobs:

1. **Offline mode** - when no LLM key is configured, this is the whole
   classifier. A demo must never fail because an API key is missing.
2. **Verification** - when an LLM is available it still runs, and the classifier
   prefers its values when a regex matched a literal number *with an explicit
   unit* in the clause text. Numbers that a model paraphrased or normalised
   incorrectly can therefore never reach the rule engine unchecked.

Everything here is pure and synchronous: same input, same output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.clause import Clause, ClauseEntities
from app.models.enums import ClauseCategory

# ---------------------------------------------------------------------------
# Number handling
# ---------------------------------------------------------------------------
_NUMBER_WORDS: dict[str, float] = {
    "half": 0.5,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "ninety": 90,
    "a": 1,
    "an": 1,
}

_COMPOUND_ONES = "one|two|three|four|five|six|seven|eight|nine"
_WORD_NUM = (
    rf"(?:twenty[-\s](?:{_COMPOUND_ONES})"
    rf"|thirty[-\s](?:{_COMPOUND_ONES})"
    rf"|forty[-\s](?:{_COMPOUND_ONES})"
    rf"|fifty[-\s](?:{_COMPOUND_ONES})"
    rf"|sixty[-\s](?:{_COMPOUND_ONES})"
    rf"|ninety[-\s](?:{_COMPOUND_ONES})"
    r"|nineteen|eighteen|seventeen|sixteen|fifteen|fourteen|thirteen|twelve|eleven"
    r"|twenty|thirty|forty|fifty|sixty|ninety"
    r"|ten|nine|eight|seven|six|five|four|three|two|one|half"
    r"|an|a)"
)
_NUM = rf"(?:\d{{1,3}}(?:\.\d+)?|{_WORD_NUM})"


def _to_number(token: str) -> float | None:
    """Convert ``"10"``, ``"ten"`` or ``"twenty-four"`` to a number."""
    token = token.strip().lower()
    if not token:
        return None
    try:
        return float(token)
    except ValueError:
        pass
    token = token.replace("-", " ")
    if token in _NUMBER_WORDS:
        return _NUMBER_WORDS[token]
    parts = token.split()
    if (
        len(parts) == 2
        and parts[0] in _NUMBER_WORDS
        and parts[1] in _NUMBER_WORDS
        and _NUMBER_WORDS[parts[0]] >= 20
    ):
        return _NUMBER_WORDS[parts[0]] + _NUMBER_WORDS[parts[1]]
    return None


_UNIT_DAYS = {
    "day": 1,
    "days": 1,
    "week": 7,
    "weeks": 7,
    "fortnight": 14,
    "month": 30,
    "months": 30,
    "year": 365,
    "years": 365,
}
_UNIT_MONTHS = {
    "month": 1,
    "months": 1,
    "year": 12,
    "years": 12,
    "week": 0.25,
    "weeks": 0.25,
    "day": 1 / 30,
    "days": 1 / 30,
}

_PERIOD_RE = re.compile(
    rf"(?P<num>{_NUM})\s*(?:\(\s*[a-z]+\s*\)\s*)?(?P<unit>days?|weeks?|fortnights?|months?|years?)\b"
)
_HOURS_RE = re.compile(rf"(?P<num>{_NUM})\s*hours?\b")
_PERCENT_RE = re.compile(rf"(?P<pct>{_NUM})\s*(?:%|per\s?cent\b|percent\b)")
_AMOUNT_RE = re.compile(r"(?:rs\.?|inr|₹)\s*(?P<amt>\d[\d,]{2,14})")

# A landlord notice period must follow the *subject* "landlord"/"lessor" within the
# same sentence: "The Landlord shall give 30 days notice". A sentence such as
# "The Tenant shall give 7 days notice to the Landlord" must not be attributed to
# the landlord, which is why the subject preceding the keyword is checked.
_LANDLORD_NOTICE_RE = re.compile(
    rf"(?:landlord|lessor)[^.;]{{0,90}}?(?P<num>{_NUM})\s*"
    r"(?:\(\s*[a-z]+\s*\)\s*)?(?P<unit>days?|weeks?|fortnights?|months?)\b"
)
_SUBJECT_RE = re.compile(r"(?:landlord|lessor|tenant|lessee)")

# A notice period is anchored on the word "notice" itself. Anchoring matters: in
# "refund the deposit within 21 days after the tenant vacates", 21 days is a refund
# window, not a notice period, and must not be read as one.
_NOTICE_RE = re.compile(r"notic\w*")
_REFUND_KEYWORDS = ("refund", "return", "repay", "reimburse")
_RENT_INCREASE_KEYWORDS = ("increase", "revise", "revision", "hike", "enhance", "escalat")
_DEPOSIT_CONTEXT_RE = re.compile(r"deposit|advance|token")
_PERIOD_SPAN = 55

# ---------------------------------------------------------------------------
# Category keyword model
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS: dict[ClauseCategory, tuple[tuple[str, float], ...]] = {
    ClauseCategory.DEPOSIT: (
        ("security deposit", 4.0),
        ("advance deposit", 3.0),
        ("advance rent", 3.0),
        ("deposit", 2.0),
        ("token advance", 2.0),
        ("refund", 1.0),
    ),
    ClauseCategory.LOCK_IN: (
        ("lock-in", 5.0),
        ("lock in", 5.0),
        ("early termination", 3.0),
        ("early exit", 2.5),
        ("penalty", 1.5),
        ("liquidated damages", 2.0),
        ("notice period", 1.0),
    ),
    ClauseCategory.EVICTION: (
        ("evict", 4.0),
        ("eviction", 4.0),
        ("recovery of possession", 4.0),
        ("vacate", 2.5),
        ("terminate the tenancy", 3.0),
        ("possession", 1.5),
        ("notice to quit", 3.0),
        ("re-enter", 2.0),
    ),
    ClauseCategory.RENT_HIKE: (
        ("rent increase", 5.0),
        ("increase in rent", 5.0),
        ("revision of rent", 5.0),
        ("revise the rent", 4.0),
        ("escalation", 2.5),
        ("hike", 2.5),
        ("enhance the rent", 3.0),
        ("increase the rent", 4.0),
        ("per cent", 1.0),
    ),
    ClauseCategory.ENTRY_RIGHTS: (
        ("right to enter", 5.0),
        ("enter the premises", 4.5),
        ("entry", 3.0),
        ("inspect", 3.0),
        ("inspection", 3.0),
        ("keys", 2.5),
        ("access to the premises", 3.0),
        ("at any time", 2.0),
    ),
    ClauseCategory.MAINTENANCE: (
        ("repairs", 3.0),
        ("repair and maintenance", 4.0),
        ("maintenance", 2.5),
        ("structural", 3.0),
        ("whitewash", 3.0),
        ("plumbing", 2.5),
        ("electrical wiring", 2.5),
        ("painting", 2.0),
        ("essential services", 3.0),
    ),
    ClauseCategory.GENERAL: (
        ("rent authority", 3.0),
        ("rent court", 2.5),
        ("registration", 2.0),
        ("stamp duty", 1.5),
        ("jurisdiction", 1.5),
    ),
}

MIN_CATEGORY_SCORE = 1.5


@dataclass
class HeuristicResult:
    """Output of the deterministic extractor."""

    category: ClauseCategory = ClauseCategory.GENERAL
    confidence: float = 0.0
    entities: ClauseEntities = field(default_factory=ClauseEntities)
    notes: list[str] = field(default_factory=list)


class HeuristicExtractor:
    """Regex-based classification used standalone or as an LLM cross-check."""

    # -- public API ---------------------------------------------------------
    def extract(self, clause: Clause) -> HeuristicResult:
        text = _normalise(clause.raw_text)
        heading = _normalise(clause.heading)
        entities = ClauseEntities()
        notes: list[str] = []

        self._extract_deposit(text, entities)
        self._extract_lock_in(text, entities)
        self._extract_notice(text, entities)
        self._extract_rent(text, entities)
        self._extract_entry(text, entities)
        self._extract_maintenance(text, entities)
        self._extract_formalities(text, entities)

        category, confidence = self._category(text, heading, entities)
        if category is ClauseCategory.GENERAL and not entities.field_sources:
            notes.append("No statutory domain matched; treated as a general term.")
        entities.field_sources = {
            name: "heuristic" for name in entities.field_sources
        }
        return HeuristicResult(
            category=category,
            confidence=confidence,
            entities=entities,
            notes=notes,
        )

    # -- category -----------------------------------------------------------
    def _category(
        self,
        text: str,
        heading: str,
        entities: ClauseEntities,
    ) -> tuple[ClauseCategory, float]:
        scores: dict[ClauseCategory, float] = {
            category: 0.0 for category in CATEGORY_KEYWORDS
        }
        for category, keywords in CATEGORY_KEYWORDS.items():
            for keyword, weight in keywords:
                if keyword in text:
                    scores[category] += weight
                if keyword in heading:
                    scores[category] += weight  # the heading is the strongest signal

        # Entity evidence: an extracted fact is direct evidence of its domain.
        if entities.deposit_months is not None or entities.deposit_amount_inr is not None:
            scores[ClauseCategory.DEPOSIT] += 5.0
        if entities.lock_in_months is not None or entities.lock_in_penalty_months is not None:
            scores[ClauseCategory.LOCK_IN] += 5.0
        if entities.allows_immediate_eviction or entities.eviction_grounds:
            scores[ClauseCategory.EVICTION] += 4.0
        if entities.rent_increase_percent is not None:
            scores[ClauseCategory.RENT_HIKE] += 5.0
        if entities.entry_notice_hours is not None or entities.unrestricted_entry:
            scores[ClauseCategory.ENTRY_RIGHTS] += 4.0
        if entities.tenant_pays_structural_repairs:
            scores[ClauseCategory.MAINTENANCE] += 4.0

        best_category, best_score = max(scores.items(), key=lambda item: item[1])
        if best_score < MIN_CATEGORY_SCORE:
            return ClauseCategory.GENERAL, 0.35
        runner_up = max(
            (score for category, score in scores.items() if category is not best_category),
            default=0.0,
        )
        confidence = min(0.92, 0.42 + 0.06 * best_score + 0.03 * (best_score - runner_up))
        return best_category, round(confidence, 2)

    # -- extractors ---------------------------------------------------------
    def _extract_deposit(self, text: str, entities: ClauseEntities) -> None:
        # Deposit facts only live in deposit clauses. Running these patterns over a
        # lock-in clause turns "one months rent in lieu of notice" into a deposit.
        if not _DEPOSIT_CONTEXT_RE.search(text):
            return
        months_patterns = (
            rf"(?P<num>{_NUM})\s*(?:\(\s*[a-z]+\s*\)\s*)?months?'?\s*"
            r"(?:rent|rental|advance|of\s+rent|equivalent)",
            rf"(?:security\s+deposit|advance|deposit)[^.;]{{0,40}}?"
            rf"(?P<num>{_NUM})\s*(?:\(\s*[a-z]+\s*\)\s*)?months?",
            rf"(?P<num>{_NUM})\s*(?:\(\s*[a-z]+\s*\)\s*)?months?[^.;]{{0,30}}?"
            r"(?:security\s+deposit|advance\s+rent|as\s+deposit)",
        )
        for pattern in months_patterns:
            match = re.search(pattern, text)
            if match:
                value = _to_number(match.group("num"))
                if value is not None:
                    entities.deposit_months = min(value, 120)
                    entities.field_sources["deposit_months"] = "heuristic"
                break

        amount = _AMOUNT_RE.search(text)
        if amount:
            digits = amount.group("amt").replace(",", "")
            if digits.isdigit() and len(digits) >= 3:
                entities.deposit_amount_inr = float(digits)
                entities.field_sources["deposit_amount_inr"] = "heuristic"

        refund = _find_refund_window_days(text)
        if refund is not None:
            entities.deposit_refund_days = refund
            entities.field_sources["deposit_refund_days"] = "heuristic"

        normalised = text.replace("-", " ")
        if re.search(r"non\s*refundable|not\s+refundable|no\s+refund", normalised):
            entities.deposit_non_refundable = True
            entities.field_sources["deposit_non_refundable"] = "heuristic"
        elif re.search(r"fully\s+refundable|refundable\s+subject\s+to", normalised):
            entities.deposit_non_refundable = False
            entities.field_sources["deposit_non_refundable"] = "heuristic"

        forfeiture = re.search(
            r"(?:forfeit\w*|appropriat\w*|retain\w*|withhold\w*|adjust\w*)"
            r"[^.;]{0,50}?(?:security\s+)?deposit|"
            r"deposit[^.;]{0,50}?(?:forfeit\w*|appropriat\w*|withhold\w*)",
            normalised,
        )
        early_exit = re.search(
            r"(?:early|premature|before\s+the\s+(?:expiry|end)|prior\s+to\s+(?:the\s+)?expiry|"
            r"(?:leav|vacat|terminat)\w*[^.;]{0,40}(?:before|prior))",
            normalised,
        )
        negated_forfeiture = re.search(
            r"(?:not|never)\s+(?:be\s+)?(?:forfeit\w*|appropriat\w*|withhold\w*|withheld)",
            normalised,
        )
        if forfeiture and early_exit and not negated_forfeiture:
            entities.deposit_forfeiture_on_early_exit = True
            entities.field_sources["deposit_forfeiture_on_early_exit"] = "heuristic"

    def _extract_lock_in(self, text: str, entities: ClauseEntities) -> None:
        normalised = text.replace("-", " ")
        lock = re.search(
            rf"lock\s?in(?:\s+period)?[^.;\d]{{0,30}}(?P<num>{_NUM})\s*(?P<unit>months?|years?)",
            normalised,
        )
        if not lock:
            lock = re.search(
                rf"(?P<num>{_NUM})\s*(?P<unit>months?|years?)[^.;\d]{{0,30}}lock\s?in",
                normalised,
            )
        if lock:
            value = _to_number(lock.group("num"))
            if value is not None:
                multiplier = _UNIT_MONTHS.get(lock.group("unit").lower(), 1)
                entities.lock_in_months = round(min(value * multiplier, 120), 2)
                entities.field_sources["lock_in_months"] = "heuristic"

        penalty = _find_period_months(
            normalised, ("penalty", "liquidated", "damages", "compensation", "forfeit")
        )
        if penalty is not None:
            entities.lock_in_penalty_months = penalty
            entities.field_sources["lock_in_penalty_months"] = "heuristic"

        penalty_amount = re.search(
            r"(?:penalty|liquidated\s+damages|compensation)[^.;]{0,30}?"
            r"(?:rs\.?|inr|₹)\s*(?P<amt>\d[\d,]{2,14})",
            normalised,
        )
        if penalty_amount:
            digits = penalty_amount.group("amt").replace(",", "")
            if digits.isdigit():
                entities.lock_in_penalty_inr = float(digits)
                entities.field_sources["lock_in_penalty_inr"] = "heuristic"

    def _extract_notice(self, text: str, entities: ClauseEntities) -> None:
        normalised = text.replace("-", " ")
        tenant_notice = _notice_period_days(normalised)
        if tenant_notice is not None:
            entities.notice_period_days = tenant_notice
            entities.field_sources["notice_period_days"] = "heuristic"

        landlord_notice = _find_landlord_notice_days(normalised)
        if (
            landlord_notice is None
            and tenant_notice is not None
            and ("either party" in normalised or "both parties" in normalised)
        ):
            # "Either party may terminate on 60 days' notice" binds both sides.
            landlord_notice = tenant_notice
        if landlord_notice is not None:
            entities.landlord_eviction_notice_days = landlord_notice
            entities.field_sources["landlord_eviction_notice_days"] = "heuristic"

        if re.search(
            r"(?:immediate\w*|forthwith|instantly)[^.;]{0,40}"
            r"(?:evict|vacat|terminat|re\s?enter|take\s+possession)|"
            r"(?:evict|vacat|terminat|re\s?enter|take\s+possession)[^.;]{0,40}"
            r"(?:immediately|forthwith|without\s+(?:any\s+)?(?:prior\s+)?notice)|"
            r"without\s+(?:any\s+)?(?:prior\s+)?notice[^.;]{0,40}(?:evict|vacat|terminat)|"
            r"forcibl[ey][^.;]{0,30}(?:evict|remove|enter)",
            normalised,
        ):
            entities.allows_immediate_eviction = True
            entities.field_sources["allows_immediate_eviction"] = "heuristic"

        grounds: list[str] = []
        # "arrears of rent" is mentioned in deposit clauses too; grounds only mean
        # something when the clause is actually about repossession.
        if re.search(r"evict|vacat|possession|terminat|re-?enter|quit", normalised):
            for label, pattern in (
                ("non-payment of rent", r"non[\s-]?payment|arrears|default\s+in\s+payment"),
                (
                    "owner occupation",
                    r"own\s+(?:use|occupation)|personal\s+use|family\s+occupation",
                ),
                ("sub-letting", r"sub[\s-]?let|sub[\s-]?tenan"),
                ("misuse of premises", r"misuse|nuisance|illegal\s+(?:use|activity)"),
                (
                    "demolition or rebuilding",
                    r"demoli|rebuild|reconstruction|repairs?\s+requiring",
                ),
            ):
                if re.search(pattern, normalised):
                    grounds.append(label)
        if grounds:
            entities.eviction_grounds = grounds
            entities.field_sources["eviction_grounds"] = "heuristic"

        if re.search(r"(?:double|twice)\s+the\s+(?:monthly\s+)?rent", normalised):
            entities.double_rent_penalty = True
            entities.field_sources["double_rent_penalty"] = "heuristic"

    def _extract_rent(self, text: str, entities: ClauseEntities) -> None:
        percent = _PERCENT_RE.search(text)
        if percent:
            value = _to_number(percent.group("pct"))
            if value is not None and 0 < value <= 1000:
                entities.rent_increase_percent = value
                entities.field_sources["rent_increase_percent"] = "heuristic"

        frequency = re.search(
            rf"(?:every|each|once\s+in|once\s+every|after)\s+(?P<num>{_NUM})\s*"
            r"(?P<unit>months?|years?)",
            text,
        )
        if frequency:
            value = _to_number(frequency.group("num"))
            if value is not None:
                multiplier = 12 if frequency.group("unit").lower().startswith("year") else 1
                entities.rent_increase_frequency_months = int(min(value * multiplier, 600))
                entities.field_sources["rent_increase_frequency_months"] = "heuristic"

        notice = (
            _notice_period_days(text)
            if any(keyword in text for keyword in _RENT_INCREASE_KEYWORDS)
            else None
        )
        if notice is not None:
            entities.rent_increase_notice_days = notice
            entities.field_sources["rent_increase_notice_days"] = "heuristic"

        normalised = text.replace("-", " ")
        if re.search(
            r"(?:landlord|lessor)[^.;]{0,80}(?:may|can|shall\s+be\s+entitled|reserves?\s+(?:the\s+)?right)"
            r"[^.;]{0,60}(?:increase|revise|enhance|raise)[^.;]{0,60}"
            r"(?:at\s+(?:his|her|their|its)\s+(?:sole\s+)?discretion|unilater|"
            r"without\s+(?:the\s+)?(?:prior\s+)?(?:consent|agreement)\s+of\s+the\s+tenant)",
            normalised,
        ) or re.search(r"(?:sole\s+discretion|unilateral\w*)[^.;]{0,40}(?:increase|revision)", normalised):
            entities.rent_increase_unilateral = True
            entities.field_sources["rent_increase_unilateral"] = "heuristic"

        if re.search(
            r"(?:during|within)\s+the\s+(?:term|tenancy\s+period|currency)[^.;]{0,50}"
            r"(?:increase|revis|hike)|"
            r"(?:increase|revis\w*)[^.;]{0,40}(?:during|mid\s?term|in\s+the\s+middle)",
            normalised,
        ):
            entities.rent_increase_during_fixed_term = True
            entities.field_sources["rent_increase_during_fixed_term"] = "heuristic"

    def _extract_entry(self, text: str, entities: ClauseEntities) -> None:
        normalised = text.replace("-", " ")
        hours: float | None = None
        for match in _HOURS_RE.finditer(normalised):
            window = normalised[max(0, match.start() - 80) : match.end() + 80]
            if "notice" in window or "prior" in window or "before" in window:
                value = _to_number(match.group("num"))
                if value is not None:
                    hours = value
                    break
        if hours is None:
            days = _find_period_days(normalised, ("enter", "entry", "notice"))
            if days is not None and days <= 2:
                hours = float(days * 24)
        if hours is not None:
            entities.entry_notice_hours = min(hours, 8760)
            entities.field_sources["entry_notice_hours"] = "heuristic"

        if re.search(
            r"at\s+(?:any|all)\s+times?|without\s+(?:any\s+|prior\s+)?notice|"
            r"(?:free|unrestricted|unlimited)\s+(?:access|entry)|"
            r"right\s+to\s+enter\s+at\s+any|"
            r"(?:enter|access)[^.;]{0,30}(?:at\s+any\s+time|whenever)",
            normalised,
        ):
            entities.unrestricted_entry = True
            entities.field_sources["unrestricted_entry"] = "heuristic"

        if re.search(
            r"(?:retain|keep|hold|duplicate|spare|extra|set\s+of)\w*[^.;]{0,30}keys?",
            normalised,
        ):
            entities.landlord_retains_keys = True
            entities.field_sources["landlord_retains_keys"] = "heuristic"

        if re.search(
            r"(?:before\s+[6-8]\s*(?:a\.?m)|after\s+[89]\s*(?:p\.?m)|night|midnight)",
            normalised,
        ):
            entities.entry_outside_allowed_hours = True
            entities.field_sources["entry_outside_allowed_hours"] = "heuristic"

    def _extract_maintenance(self, text: str, entities: ClauseEntities) -> None:
        normalised = text.replace("-", " ")

        if re.search(
            r"(?:tenant|lessee)\s+(?:shall|will|must|is\s+(?:required|responsible|liable)|agrees?)"
            r"[^.;]{0,110}?(?:structural\s+repairs?|major\s+repairs?|capital\s+repairs?|"
            r"repairs?\s+to\s+the\s+(?:roof|foundation|walls?|wiring|plumbing))|"
            r"(?:structural|major|capital)\s+repairs?[^.;]{0,40}"
            r"(?:borne\s+by|at\s+the\s+(?:cost|expense)\s+of|responsibility\s+of)\s+"
            r"(?:the\s+)?(?:tenant|lessee)",
            normalised,
        ):
            entities.tenant_pays_structural_repairs = True
            entities.field_sources["tenant_pays_structural_repairs"] = "heuristic"

        if re.search(
            r"(?:tenant|lessee)[^.;]{0,70}(?:all|every|any|entire)\s+(?:the\s+)?"
            r"(?:repairs?|maintenance|upkeep)|"
            r"(?:all|entire)\s+(?:repairs?|maintenance)[^.;]{0,50}"
            r"(?:by|at\s+the\s+cost\s+of|borne\s+by)\s+(?:the\s+)?tenant",
            normalised,
        ):
            entities.tenant_pays_all_repairs = True
            entities.field_sources["tenant_pays_all_repairs"] = "heuristic"

        if re.search(
            r"(?:landlord|lessor)[^.;]{0,70}(?:shall\s+)?not\s+be\s+(?:responsible|liable)"
            r"[^.;]{0,40}(?:repairs?|maintenance|habitable)|"
            r"(?:no|without)\s+(?:obligation|liability)[^.;]{0,50}(?:repairs?|maintenance)|"
            r"(?:waive|waiver|relieve)[^.;]{0,50}(?:repair|maintenance|habitable)",
            normalised,
        ):
            entities.landlord_repair_duty_waived = True
            entities.field_sources["landlord_repair_duty_waived"] = "heuristic"

        cutoff = re.search(
            r"(?:disconnect|cut\s?off|withhold|stop|discontinue|suspend)[^.;]{0,60}"
            r"(?:water|electricity|power|supply|essential\s+services?|services?)",
            normalised,
        )
        # "The Landlord shall not disconnect water" is the opposite of a violation.
        if cutoff and not _is_negated(normalised, cutoff.start()):
            entities.essential_services_cutoff_allowed = True
            entities.field_sources["essential_services_cutoff_allowed"] = "heuristic"

        if re.search(
            r"(?:deduct|set\s?off|adjust)[^.;]{0,60}(?:repair|maintenance)|"
            r"(?:repair|maintenance)[^.;]{0,50}deduct[^.;]{0,30}rent",
            normalised,
        ):
            entities.repair_deduction_allowed = True
            entities.field_sources["repair_deduction_allowed"] = "heuristic"

    def _extract_formalities(self, text: str, entities: ClauseEntities) -> None:
        normalised = text.replace("-", " ")
        if re.search(r"rent\s+(?:authority|court|tribunal)", normalised):
            entities.mentions_rent_authority = True
            entities.field_sources["mentions_rent_authority"] = "heuristic"
        if re.search(
            r"not\s+(?:be\s+)?regist\w*|unregist\w*|without\s+(?:being\s+)?regist\w*|"
            r"no\s+registration|regist\w*\s+(?:is\s+)?not\s+(?:required|necessary)",
            normalised,
        ):
            entities.agreement_unregistered = True
            entities.field_sources["agreement_unregistered"] = "heuristic"
        if re.search(
            r"original[^.;]{0,50}(?:retain\w*|with\s+the\s+landlord|sole\s+copy)|"
            r"(?:landlord|lessor)[^.;]{0,50}retain\w*[^.;]{0,25}original",
            normalised,
        ):
            entities.original_agreement_withheld = True
            entities.field_sources["original_agreement_withheld"] = "heuristic"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalise(text: str) -> str:
    """Collapse whitespace so regexes can span line breaks."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _find_period_days(
    text: str,
    keywords: tuple[str, ...],
    *,
    max_window: int = 120,
    require_any: tuple[str, ...] = (),
) -> int | None:
    """Find the nearest ``<n> days/months`` mention to a keyword."""
    for match in _PERIOD_RE.finditer(text):
        window = text[max(0, match.start() - max_window) : match.end() + 40]
        if keywords and not any(keyword in window for keyword in keywords):
            continue
        if require_any and not any(token in window for token in require_any):
            continue
        value = _to_number(match.group("num"))
        if value is None:
            continue
        unit = match.group("unit").lower()
        days = _UNIT_DAYS.get(unit)
        if days is None:
            continue
        return int(round(min(value * days, 3650)))
    return None


def _find_landlord_notice_days(text: str) -> int | None:
    """Return a notice period that the *landlord* must give, if stated."""
    for match in _LANDLORD_NOTICE_RE.finditer(text):
        tail = text[match.end() : match.end() + 70]
        segment = f"{match.group(0)} {tail}"
        if "notice" not in segment and not any(
            token in tail for token in ("evict", "possession", "vacat")
        ):
            continue
        # "refund the deposit within 21 days" is not an eviction notice.
        if any(keyword in segment for keyword in _REFUND_KEYWORDS) or "repair" in segment:
            continue
        # If the nearest preceding party is the tenant, the landlord is the object
        # of the sentence ("notice to the Landlord") - not the party giving notice.
        preceding = _SUBJECT_RE.findall(text[max(0, match.start() - 100) : match.start()])
        if preceding and preceding[-1] in ("tenant", "lessee"):
            continue
        value = _to_number(match.group("num"))
        if value is None:
            continue
        multiplier = _UNIT_DAYS.get(match.group("unit").lower())
        if multiplier is None:
            continue
        return int(round(min(value * multiplier, 3650)))
    return None


def _notice_period_days(text: str, span: int = _PERIOD_SPAN) -> int | None:
    """Return the period stated next to the word "notice".

    The anchor matters. "Refund within 21 days after the tenant vacates" contains a
    period and a vacating verb but no notice period at all, so looking for a period
    near *any* termination keyword produced false high-risk findings.
    """
    best_distance: int | None = None
    best_days: int | None = None
    for anchor in _NOTICE_RE.finditer(text):
        start = max(0, anchor.start() - span)
        window = text[start : anchor.end() + span]
        for match in _PERIOD_RE.finditer(window):
            value = _to_number(match.group("num"))
            if value is None:
                continue
            multiplier = _UNIT_DAYS.get(match.group("unit").lower())
            if multiplier is None:
                continue
            distance = abs((start + match.start()) - anchor.start())
            if best_distance is not None and distance >= best_distance:
                continue
            best_distance = distance
            best_days = int(round(min(value * multiplier, 3650)))
    return best_days


def _find_refund_window_days(text: str) -> int | None:
    """Find a refund window such as "refund within 21 days".

    A period only counts when it follows a scheduling word ("within", "after",
    "not later than") and a refund keyword is nearby, so "equivalent to two months
    rent" in a deposit clause cannot be mistaken for a 60-day refund window.
    """
    for match in _PERIOD_RE.finditer(text):
        window = text[max(0, match.start() - 110) : match.end() + 40]
        if not any(keyword in window for keyword in _REFUND_KEYWORDS):
            continue
        prefix = text[max(0, match.start() - 34) : match.start()]
        if not re.search(
            r"\b(?:within|after|before|not\s+later\s+than|no\s+later\s+than|latest\s+by)\s*$",
            prefix,
        ):
            continue
        value = _to_number(match.group("num"))
        if value is None:
            continue
        multiplier = _UNIT_DAYS.get(match.group("unit").lower())
        if multiplier is None:
            continue
        return int(round(min(value * multiplier, 3650)))
    return None


def _is_negated(text: str, index: int, window: int = 34) -> bool:
    """True when a negation directly precedes ``index`` ("shall not ...")."""
    prefix = text[max(0, index - window) : index]
    return bool(re.search(r"\b(?:not|never|no|none|nor|without)\b[\w\s,'-]{0,14}$", prefix))


def _find_period_months(text: str, keywords: tuple[str, ...]) -> float | None:
    """Find a ``<n> months`` mention that sits near a penalty keyword."""
    for match in _PERIOD_RE.finditer(text):
        window = text[max(0, match.start() - 100) : match.end() + 40]
        if not any(keyword in window for keyword in keywords):
            continue
        value = _to_number(match.group("num"))
        if value is None:
            continue
        unit = match.group("unit").lower()
        multiplier = _UNIT_MONTHS.get(unit)
        if multiplier is None:
            continue
        return round(min(value * multiplier, 120), 2)
    return None
