"""`EvidenceDescriptor` — the definition of an evidence concept.

A descriptor says *that a kind of evidence exists and what it is about*. It is
not an observation: it holds no value, no reading, no timestamp, and no state.
Two analyses of two different instruments on two different days refer to the
same descriptor; only their observations differ.

That separation is the whole point. `fmis.decision_support.Observation` already
owns the observed side — a classification, an alignment, the inputs that produced
it. This module owns the vocabulary side, and deliberately duplicates none of it:
no direction, no supporting/conflicting relationship, no availability state, and
nothing resembling a score, weight, or confidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from fmis.evidence.families import EvidenceFamily

__all__ = ["EvidenceDescriptor"]


def _require_name(value: object) -> str:
    """A name that is already normalized — never one this code normalizes for you.

    Required form: a non-empty lower-case token with no surrounding or internal
    whitespace (``price_vs_ema_fast``). A name that merely *could* be normalized
    into that form is rejected rather than silently rewritten, matching the
    project-wide rule that nothing is coerced (ADR-0005, ADR-0009).

    The reason is specific to identity: silently trimming or lower-casing would
    let ``"Trend "`` and ``"trend"`` be entered as two descriptors that collapse
    into one, so a duplicate check would pass while the catalog held a collision.
    """
    if not isinstance(value, str):
        raise TypeError(f"name must be a str, got {type(value).__name__}")
    if not value or not value.strip():
        raise ValueError("name cannot be empty")
    if value != value.strip():
        raise ValueError(f"name {value!r} must not have leading/trailing whitespace")
    if any(character.isspace() for character in value):
        raise ValueError(f"name {value!r} must not contain whitespace")
    if value != value.lower():
        raise ValueError(f"name {value!r} must be lower-case")
    return value


@dataclass(frozen=True, slots=True)
class EvidenceDescriptor:
    """One evidence concept: which family it belongs to, its name, what it means.

    Frozen and slotted, so a descriptor cannot drift after definition and cannot
    grow an attribute that was never declared — which is how a "just this once"
    score or weight would otherwise arrive.

    The three fields are the whole type, and the omissions are deliberate:

      * **no value or reading** — that is an observation, not a definition;
      * **no score, weight, or confidence** — nothing in the system estimates
        any of them, and a field invites a number with no basis;
      * **no direction** — a family is a subject, not a stance;
      * **no supporting/conflicting relationship** — that is a relationship to a
        hypothesis, and `fmis.decision_support.EvidenceGroups` already owns it;
      * **no availability state** — that belongs to a specific observation of
        specific data, and `Alignment.UNAVAILABLE` and the feature metadata key
        ``insufficient_data`` already own it.

    Validation is explicit: the family must be an `EvidenceFamily`, the name must
    already be normalized, and the description must be present and non-blank.
    """

    family: EvidenceFamily
    name: str
    description: str

    def __post_init__(self) -> None:
        if not isinstance(self.family, EvidenceFamily):
            raise TypeError(
                f"family must be an EvidenceFamily, got {type(self.family).__name__}"
            )
        _require_name(self.name)
        if not isinstance(self.description, str):
            raise TypeError(
                f"description must be a str, got {type(self.description).__name__}"
            )
        if not self.description or not self.description.strip():
            raise ValueError("description cannot be empty")
