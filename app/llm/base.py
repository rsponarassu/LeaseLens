"""Provider-agnostic LLM contract, prompt and JSON schema.

The model is given a small, closed task: label the clause and fill typed fields.
It is explicitly forbidden from producing verdicts, severities or scores - those
belong to :mod:`app.services.rule_engine`.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.models.clause import Clause
from app.models.enums import ClauseCategory

MAX_CLAUSE_CHARS_IN_PROMPT = 1800

CATEGORY_DEFINITIONS: dict[ClauseCategory, str] = {
    ClauseCategory.DEPOSIT: (
        "Money paid up front as security: amount, number of months, refund window, "
        "forfeiture, deductions."
    ),
    ClauseCategory.LOCK_IN: (
        "A minimum term the tenant cannot exit, or a penalty for leaving early, or a "
        "penalty for early termination."
    ),
    ClauseCategory.EVICTION: (
        "Termination, eviction, recovery of possession, notice to quit, or grounds on "
        "which the tenant must vacate."
    ),
    ClauseCategory.RENT_HIKE: (
        "Rent revision, escalation, increase percentage, frequency of increase, notice "
        "of increase."
    ),
    ClauseCategory.ENTRY_RIGHTS: (
        "Landlord's right to enter, inspect, show the premises, retain keys, or access "
        "at any time."
    ),
    ClauseCategory.MAINTENANCE: (
        "Repairs, maintenance, structural work, painting, plumbing, electrical work, "
        "essential services such as water and electricity."
    ),
    ClauseCategory.GENERAL: (
        "Formal or administrative terms that do not affect the six substantive domains "
        "above: registration, stamp duty, notices, jurisdiction, furnishing inventory."
    ),
}


class LLMClauseResult(BaseModel):
    """One clause classification as returned by a model."""

    model_config = {"extra": "ignore"}

    clause_id: str
    category: ClauseCategory
    confidence: float = Field(default=0.5, ge=0, le=1)
    entities: dict[str, Any] = Field(default_factory=dict)
    evidence_quote: str | None = None
    notes: list[str] = Field(default_factory=list)

    @field_validator("clause_id")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class LLMResponse(BaseModel):
    """Envelope returned by every provider adapter."""

    model_config = {"extra": "ignore"}

    clauses: list[LLMClauseResult] = Field(default_factory=list)


@dataclass
class LLMUsage:
    """Token / latency accounting for a single request."""

    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    model: str = ""


@dataclass
class LLMBatchResult:
    """Parsed results plus usage for a batch of clauses."""

    results: list[LLMClauseResult] = Field(default_factory=list)
    usage: LLMUsage = Field(default_factory=LLMUsage)
    raw: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# JSON schema for structured output
# ---------------------------------------------------------------------------
_ENTITY_SPECS: dict[str, dict[str, Any]] = {
    "deposit_months": {
        "type": "number",
        "description": "Security deposit expressed in months of rent. Convert 'ten months' to 10.",
    },
    "deposit_amount_inr": {
        "type": "number",
        "description": "Security deposit as a rupee amount, digits only (no commas).",
    },
    "deposit_refund_days": {
        "type": "integer",
        "description": "Days allowed to refund the deposit after the tenant vacates. Convert months to 30 per month.",
    },
    "deposit_non_refundable": {
        "type": "boolean",
        "description": "True only if the text states the deposit will not be returned.",
    },
    "deposit_forfeiture_on_early_exit": {
        "type": "boolean",
        "description": "True if the deposit is forfeited when the tenant leaves before the term ends.",
    },
    "lock_in_months": {
        "type": "number",
        "description": "Lock-in period in months.",
    },
    "lock_in_penalty_months": {
        "type": "number",
        "description": "Early-exit penalty expressed in months of rent.",
    },
    "lock_in_penalty_inr": {
        "type": "number",
        "description": "Early-exit penalty expressed in rupees.",
    },
    "notice_period_days": {
        "type": "integer",
        "description": "Notice the TENANT must give before vacating, in days. Convert months to 30 per month.",
    },
    "landlord_eviction_notice_days": {
        "type": "integer",
        "description": "Notice the LANDLORD must give before requiring the tenant to vacate, in days.",
    },
    "allows_immediate_eviction": {
        "type": "boolean",
        "description": "True if the landlord may evict or lock out immediately, or without notice or court order.",
    },
    "eviction_grounds": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Short labels of the stated grounds for eviction, e.g. 'non-payment', 'owner occupation'.",
    },
    "double_rent_penalty": {
        "type": "boolean",
        "description": "True if double rent or penal rent is charged for overstaying.",
    },
    "rent_increase_percent": {
        "type": "number",
        "description": "Percentage of the periodic rent increase.",
    },
    "rent_increase_frequency_months": {
        "type": "integer",
        "description": "How often rent may be increased, in months. Convert years to 12 per year.",
    },
    "rent_increase_notice_days": {
        "type": "integer",
        "description": "Notice given before a rent increase takes effect, in days.",
    },
    "rent_increase_unilateral": {
        "type": "boolean",
        "description": "True if the landlord may increase rent at their own discretion without the tenant's agreement.",
    },
    "rent_increase_during_fixed_term": {
        "type": "boolean",
        "description": "True if rent can increase during a fixed-term tenancy.",
    },
    "entry_notice_hours": {
        "type": "number",
        "description": "Hours of notice required before the landlord enters. Convert days to 24 per day.",
    },
    "unrestricted_entry": {
        "type": "boolean",
        "description": "True if the landlord may enter at any time or without notice.",
    },
    "landlord_retains_keys": {
        "type": "boolean",
        "description": "True if the landlord keeps a duplicate set of keys.",
    },
    "entry_outside_allowed_hours": {
        "type": "boolean",
        "description": "True if entry is permitted outside normal daytime hours.",
    },
    "tenant_pays_structural_repairs": {
        "type": "boolean",
        "description": "True if the tenant must pay for structural repairs.",
    },
    "tenant_pays_all_repairs": {
        "type": "boolean",
        "description": "True if the tenant must bear all repairs or maintenance.",
    },
    "landlord_repair_duty_waived": {
        "type": "boolean",
        "description": "True if the agreement waives the landlord's duty to repair or keep the premises habitable.",
    },
    "repair_deduction_allowed": {
        "type": "boolean",
        "description": "True if the tenant may deduct repair costs from rent.",
    },
    "essential_services_cutoff_allowed": {
        "type": "boolean",
        "description": "True if water, electricity or other essential services may be cut off.",
    },
    "mentions_rent_authority": {
        "type": "boolean",
        "description": "True if the Rent Authority, Rent Court or Rent Tribunal is mentioned.",
    },
    "agreement_unregistered": {
        "type": "boolean",
        "description": "True if the agreement is stated not to be registered.",
    },
    "original_agreement_withheld": {
        "type": "boolean",
        "description": "True if the landlord keeps the only original signed agreement.",
    },
}

ENTITY_FIELDS: tuple[str, ...] = tuple(_ENTITY_SPECS)


def _entities_schema(provider: str) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for name, spec in _ENTITY_SPECS.items():
        if provider == "gemini":
            properties[name] = {**spec, "nullable": True}
        else:
            if spec["type"] == "array":
                properties[name] = spec
            else:
                properties[name] = {**spec, "type": [spec["type"], "null"]}
    return {
        "type": "object",
        "properties": properties,
        "description": (
            "Extracted facts. Use null when the clause does not state the fact. "
            "Never guess, never infer from law, never copy a value that is not in the text."
        ),
    }


def build_response_schema(provider: str) -> dict[str, Any]:
    """JSON schema for the whole response, adapted per provider."""
    return {
        "type": "object",
        "properties": {
            "clauses": {
                "type": "array",
                "description": "One entry for every input clause, in the same order.",
                "items": {
                    "type": "object",
                    "properties": {
                        "clause_id": {"type": "string", "description": "The input clause_id."},
                        "category": {
                            "type": "string",
                            "enum": [category.value for category in ClauseCategory],
                        },
                        "confidence": {
                            "type": "number",
                            "description": "0 to 1 confidence in the category label.",
                        },
                        "entities": _entities_schema(provider),
                        "evidence_quote": {
                            "type": "string",
                            "nullable": provider == "gemini",
                            "description": "Short verbatim fragment supporting the extraction.",
                        },
                        "notes": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["clause_id", "category", "entities"],
                },
            }
        },
        "required": ["clauses"],
    }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
def build_system_prompt() -> str:
    categories = "\n".join(
        f"- {category.value}: {definition}"
        for category, definition in CATEGORY_DEFINITIONS.items()
    )
    fields = "\n".join(f"- {name}: {spec['description']}" for name, spec in _ENTITY_SPECS.items())
    return f"""You are a tenancy-agreement analyst for Tamil Nadu, India. You label clauses and extract facts. You do not give legal opinions.

CONTEXT
The governing statute is the Tamil Nadu Regulation of Rights and Responsibilities of Landlords and Tenants Act, 2017. You are used only for extraction; a separate deterministic engine compares your numbers with the statute. Therefore accuracy of the numbers matters far more than interpretation.

TASK
For each clause you receive:
1. Choose exactly one category from the list below. Choose the category that the clause is mainly about. Use "general" for notices, registration, jurisdiction or inventory that do not affect the six substantive domains.
{categories}

2. Fill the entity fields. Rules:
   - Return null for any fact the clause does not state. Do not infer, do not default, do not carry values across clauses.
   - Quote the numbers that literally appear. Convert words to numbers ("ten months" -> 10).
   - Convert everything to the stated unit: months for periods, days for notice periods, hours for entry notice.
   - "3 months" notice -> 90 days. "24 hours" -> 24.
   - If the clause says the deposit is 10 months of rent, set deposit_months=10 and leave deposit_amount_inr null unless a rupee figure is printed.
   - Booleans are true only when the text clearly says so; false when the text clearly negates it; null when silent.
   - Never state whether a clause is legal, illegal, risky or fair. Never suggest changes. Never assign a score.
   - If a clause contains no extractable fact, return all nulls.

ENTITY FIELDS
{fields}

OUTPUT
Return JSON matching the provided schema, with one entry per input clause, preserving clause_id exactly."""


def build_user_prompt(clauses: Sequence[Clause]) -> str:
    payload = [
        {
            "clause_id": clause.clause_id,
            "heading": clause.heading,
            "text": clause.text_for_prompt[:MAX_CLAUSE_CHARS_IN_PROMPT],
        }
        for clause in clauses
    ]
    return (
        "Classify each clause and extract the entity fields. Return JSON only.\n\n"
        f"CLAUSES:\n{json.dumps(payload, ensure_ascii=False, indent=1)}"
    )


def parse_llm_json(raw: str) -> LLMResponse:
    """Parse (and lightly repair) a JSON response from a model."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        text = text.removeprefix("json").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("response contains no JSON object")
    payload = json.loads(text[start : end + 1])
    if isinstance(payload, list):  # tolerate a bare array
        payload = {"clauses": payload}
    return LLMResponse.model_validate(payload)


# ---------------------------------------------------------------------------
# Client contract
# ---------------------------------------------------------------------------
class LLMClient(ABC):
    """Minimal async interface every provider adapter implements."""

    name: str = "unknown"
    model: str = ""

    @abstractmethod
    async def classify_batch(self, clauses: Sequence[Clause]) -> LLMBatchResult:
        """Classify a batch of clauses, raising a domain error on failure."""

    async def aclose(self) -> None:
        """Release any underlying HTTP resources."""
        return None


__all__ = [
    "ENTITY_FIELDS",
    "LLMBatchResult",
    "LLMClauseResult",
    "LLMClient",
    "LLMResponse",
    "LLMUsage",
    "build_response_schema",
    "build_system_prompt",
    "build_user_prompt",
    "parse_llm_json",
    "ValidationError",
]
