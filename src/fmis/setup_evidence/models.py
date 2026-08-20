"""Value types for the setup evidence projection.

Every type here is frozen and slotted. The omissions are the design, and they
are the same omissions `fmis.evidence.EvidenceDescriptor` already makes for the
same stated reason (ADR-0011 §3): **no strength, no weight, no score, no
confidence, no probability, no rank.** A field is an invitation to supply a
number with no basis, and slots make the omission enforceable rather than
merely conventional — a "just this once" attribute cannot be attached later.

An earlier draft of this milestone carried a four-level ``strength`` enum
(STRONG / MEDIUM / WEAK / NEUTRAL). It was dropped before implementation: a
monotone ordinal with no deterministic rule behind each level is a score wearing
an enum's clothes, and nothing in this repository computes one. What survives is
the part that is actually deterministic — which family an item belongs to, what
status it holds, and what produced it.

Nothing here is computed from market data. Every value is copied from a
`SetupAssessment` the Swing Setup Engine already produced.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

from fmis.decision_context import ContextState
from fmis.evidence import EvidenceFamily

__all__ = [
    "SETUP_EVIDENCE_PROJECTION_VERSION",
    "SetupEvidenceError",
    "SetupEvidenceStatus",
    "EvidenceItem",
    "SetupIdentityRef",
    "FamilySummary",
    "ConfluenceSummary",
    "SetupEvidenceReport",
]

#: Bumped when the projection's shape or grouping rules change in a way a reader
#: must notice. Distinct from `SETUP_SCHEMA_VERSION`, which versions the
#: assessment this projects *from* — two different things that drift apart.
SETUP_EVIDENCE_PROJECTION_VERSION = 1


class SetupEvidenceError(Exception):
    """Base class for every setup-evidence failure.

    Follows the package-error convention `SwingSetupError`, `MarketRegimeError`
    and `DecisionContextError` established elsewhere.
    """


class SetupEvidenceStatus(str, Enum):
    """What one evidence item currently is, relative to the assessment it explains.

    * `SUPPORTING` — a fact the assessment rests on, present and agreeing.
    * `CONFLICTING` — a fact that presently disagrees, either with the
      assessment's own direction or with itself.
    * `MISSING` — a condition the policy named and that has not occurred yet.
      Awaited, not absent: the system knows exactly what it is waiting for.
    * `UNAVAILABLE` — nothing could be read. Different from `MISSING`, which
      names something readable that has not happened.

    The four are mutually exclusive by construction: an item holds exactly one
    status and appears in exactly one group of the report.

    Deliberately absent: any member naming a direction, a recommendation, a
    magnitude or a rank. The status says what *kind* of relationship an item has
    to the assessment, never how much it is worth.
    """

    SUPPORTING = "supporting"
    CONFLICTING = "conflicting"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """One deterministic evidence item, with everything needed to check it by hand.

    ``families`` is the shared vocabulary from `fmis.evidence` — ADR-0011 §7's
    "shared vocabulary, separate interpretation", used here by its first real
    consumer. It is a **tuple, not a single family**, because one item can
    genuinely draw on more than one: `setup_evidence_alignment` reduces three
    TREND observations and two MOMENTUM observations to one alignment, and
    claiming it is purely one or the other would be a fabricated attribution.
    An empty tuple is honest too — risk geometry and calibration belong to no
    family in the ADR-0011 taxonomy, and inventing a catch-all family for them
    was explicitly ruled out.

    ``correlated_with`` names the keys of items this one is **not independent
    of**. It is what stops the report presenting one underlying fact, seen from
    three angles, as three-fold corroboration.

    Frozen and slotted. No strength, no weight, no score, no confidence — see
    the module docstring.
    """

    key: str
    families: tuple[EvidenceFamily, ...]
    status: SetupEvidenceStatus
    statement: str
    observed: str
    source: str
    scope: str | None = None
    as_of: datetime | None = None
    inputs: Mapping[str, Any] = field(default_factory=dict)
    correlated_with: tuple[str, ...] = ()
    independence_note: str | None = None

    def __post_init__(self) -> None:
        for name in ("key", "statement", "observed", "source"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SetupEvidenceError(f"{name} must be a non-empty str")
        if not isinstance(self.families, tuple):
            raise TypeError("families must be a tuple of EvidenceFamily")
        for position, family in enumerate(self.families):
            if not isinstance(family, EvidenceFamily):
                raise TypeError(
                    f"families[{position}] must be an EvidenceFamily, "
                    f"got {type(family).__name__}"
                )
        if len(set(self.families)) != len(self.families):
            raise SetupEvidenceError(
                f"families must not repeat, got {[f.value for f in self.families]}"
            )
        if not isinstance(self.status, SetupEvidenceStatus):
            raise TypeError(
                f"status must be a SetupEvidenceStatus, got {type(self.status).__name__}"
            )
        if self.scope is not None and (
            not isinstance(self.scope, str) or not self.scope.strip()
        ):
            raise SetupEvidenceError("scope must be a non-empty str or None")
        if self.as_of is not None and not isinstance(self.as_of, datetime):
            raise TypeError("as_of must be a datetime or None")
        if not isinstance(self.correlated_with, tuple):
            raise TypeError("correlated_with must be a tuple of str")
        for item in self.correlated_with:
            if not isinstance(item, str) or not item.strip():
                raise SetupEvidenceError("every correlated_with key must be a non-empty str")
        if self.key in self.correlated_with:
            raise SetupEvidenceError(
                f"{self.key!r} cannot be correlated with itself"
            )
        if self.independence_note is not None and (
            not isinstance(self.independence_note, str)
            or not self.independence_note.strip()
        ):
            raise SetupEvidenceError("independence_note must be a non-empty str or None")
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))


@dataclass(frozen=True, slots=True)
class SetupIdentityRef:
    """A reference to the setup's stable identity, supplied by the caller.

    **This package derives no identity.** `fmis.proposal.setup_identity` owns
    that rule, and re-deriving it here would be a second spelling of the same
    vocabulary — the exact failure that module's own docstring warns about. The
    composition root passes what it already built, or passes nothing.

    **Only the identity string is carried, deliberately.** An earlier draft also
    held the vocabulary id and the identity version, which would have obliged
    the CLI to import `fmis.proposal` — a trading-domain root the outermost edge
    is not permitted to name (`tests/test_trade_capture_architecture.py`). The
    two values are provenance `fmits setup`'s own identity block already prints
    from the package that owns them, so carrying them a second time here bought
    a boundary violation for a duplicated line.
    """

    setup_id: str
    occurrence_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.setup_id, str) or not self.setup_id.strip():
            raise SetupEvidenceError("setup_id must be a non-empty str")
        if self.occurrence_id is not None and (
            not isinstance(self.occurrence_id, str) or not self.occurrence_id.strip()
        ):
            raise SetupEvidenceError("occurrence_id must be a non-empty str or None")


@dataclass(frozen=True, slots=True)
class FamilySummary:
    """How one `EvidenceFamily` is represented in this report. Counts only.

    Four counts and no total judgement. A family with two supporting items is
    not "twice as good" as one with a single item, and this type deliberately
    offers no field in which that reading could be recorded.
    """

    family: EvidenceFamily
    supporting: int
    conflicting: int
    missing: int
    unavailable: int

    def __post_init__(self) -> None:
        if not isinstance(self.family, EvidenceFamily):
            raise TypeError(
                f"family must be an EvidenceFamily, got {type(self.family).__name__}"
            )
        for name in ("supporting", "conflicting", "missing", "unavailable"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an int")
            if value < 0:
                raise SetupEvidenceError(f"{name} cannot be negative, got {value}")


@dataclass(frozen=True, slots=True)
class ConfluenceSummary:
    """Family-level agreement, derived — never stored, never a score.

    **Confluence is not an evidence family and not an evidence item.** It is a
    relationship *across* families, computed from the items each time and held
    nowhere else. `derived_from` names the item keys it was computed over, so a
    reader can redo the arithmetic by hand.

    ``independent_agreeing_families`` counts **distinct families**, not items.
    Three items that all draw on TREND are one family's worth of agreement, not
    three — which is the entire reason this type reports families rather than a
    tally of items.

    The converse also holds, and bounding this count by ``agreeing_item_count``
    was a defect: `FACTOR_FAMILIES` deliberately maps `setup_evidence_alignment`
    onto **two** families, so a single agreeing item can legitimately contribute
    two. One such item is `1` item and `2` families, and the count is bounded by
    the families actually listed in ``agreeing_families`` — never by how many
    items happened to carry them.

    ``independence_established`` is `True` only when at least two agreeing items
    are **family-disjoint**. It is the honest answer to "is this corroboration
    or an echo", and it is `False` far more often than a naive item count would
    suggest. ``caveats`` states, in words, every correlation that made it so.
    """

    agreeing_families: tuple[EvidenceFamily, ...]
    conflicting_families: tuple[EvidenceFamily, ...]
    agreeing_item_count: int
    independent_agreeing_families: int
    independence_established: bool
    derived_from: tuple[str, ...]
    caveats: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("agreeing_families", "conflicting_families"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple of EvidenceFamily")
            for family in value:
                if not isinstance(family, EvidenceFamily):
                    raise TypeError(f"every {name} entry must be an EvidenceFamily")
            if len(set(value)) != len(value):
                raise SetupEvidenceError(f"{name} must not repeat")
        for name in ("agreeing_item_count", "independent_agreeing_families"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an int")
            if value < 0:
                raise SetupEvidenceError(f"{name} cannot be negative, got {value}")
        if self.independent_agreeing_families > len(self.agreeing_families):
            raise SetupEvidenceError(
                "independent_agreeing_families cannot exceed the number of "
                "agreeing_families; it counts those families and inventing one "
                "that is not listed would overstate the agreement"
            )
        if self.agreeing_item_count == 0 and (
            self.agreeing_families or self.independent_agreeing_families
        ):
            raise SetupEvidenceError(
                "agreeing families were reported with no agreeing items; a "
                "family is only present because some item carried it"
            )
        if not isinstance(self.independence_established, bool):
            raise TypeError("independence_established must be a bool")
        for name in ("derived_from", "caveats"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple of str")
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    raise SetupEvidenceError(f"every {name} line must be a non-empty str")


@dataclass(frozen=True, slots=True)
class SetupEvidenceReport:
    """The complete deterministic explanation of one `SetupAssessment`.

    A **projection**, not a second opinion. Every field is copied from the
    assessment or grouped from what it already said; nothing here re-decides
    anything. In particular `decision_ready` is a function of
    `sufficiency` **alone** — see `project.decision_ready_for`.

    ``state_text`` and ``direction_text`` carry the assessment's own enum values
    as plain strings. They are strings rather than the enums because this
    package sits outside the one package ADR-0028 permits to *name* a direction;
    it may faithfully carry the value the Swing Setup Engine produced, and does,
    but it does not import the vocabulary.
    """

    symbol: str
    as_of: datetime
    state_text: str
    direction_text: str | None
    thesis: tuple[str, ...]
    supporting: tuple[EvidenceItem, ...]
    conflicting: tuple[EvidenceItem, ...]
    missing: tuple[EvidenceItem, ...]
    unavailable: tuple[EvidenceItem, ...]
    invalidation: tuple[str, ...]
    regime_context: tuple[str, ...]
    family_summary: tuple[FamilySummary, ...]
    confluence: ConfluenceSummary
    sufficiency: ContextState
    decision_ready: bool
    decision_ready_reason: str
    warnings: tuple[str, ...]
    open_questions: tuple[str, ...]
    setup_identity: SetupIdentityRef | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("symbol", "state_text", "decision_ready_reason"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SetupEvidenceError(f"{name} must be a non-empty str")
        if not isinstance(self.as_of, datetime):
            raise TypeError(f"as_of must be a datetime, got {type(self.as_of).__name__}")
        if self.direction_text is not None and (
            not isinstance(self.direction_text, str) or not self.direction_text.strip()
        ):
            raise SetupEvidenceError("direction_text must be a non-empty str or None")
        for name in (
            "thesis", "invalidation", "regime_context", "warnings", "open_questions",
        ):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple of str")
            for line in value:
                if not isinstance(line, str) or not line.strip():
                    raise SetupEvidenceError(f"every {name} line must be a non-empty str")
        for name in ("supporting", "conflicting", "missing", "unavailable"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple of EvidenceItem")
            for item in value:
                if not isinstance(item, EvidenceItem):
                    raise TypeError(f"every {name} entry must be an EvidenceItem")

        # An item in two groups at once would be a contradictory report — the
        # thing a reader is least able to detect and most likely to be misled
        # by. Checked here so no builder, present or future, can emit one.
        expected = {
            "supporting": SetupEvidenceStatus.SUPPORTING,
            "conflicting": SetupEvidenceStatus.CONFLICTING,
            "missing": SetupEvidenceStatus.MISSING,
            "unavailable": SetupEvidenceStatus.UNAVAILABLE,
        }
        seen: dict[str, str] = {}
        for name, status in expected.items():
            for item in getattr(self, name):
                if item.status is not status:
                    raise SetupEvidenceError(
                        f"{item.key!r} is in {name} but its status is "
                        f"{item.status.value}; group and status must agree"
                    )
                if item.key in seen:
                    raise SetupEvidenceError(
                        f"{item.key!r} appears twice — in {seen[item.key]} and in "
                        f"{name}. An evidence key identifies one item exactly once"
                    )
                seen[item.key] = name

        for item in self.all_items:
            for other in item.correlated_with:
                if other not in seen:
                    raise SetupEvidenceError(
                        f"{item.key!r} is correlated with {other!r}, which is not "
                        "an item in this report"
                    )

        if not isinstance(self.family_summary, tuple):
            raise TypeError("family_summary must be a tuple of FamilySummary")
        families_seen = []
        for summary in self.family_summary:
            if not isinstance(summary, FamilySummary):
                raise TypeError("every family_summary entry must be a FamilySummary")
            families_seen.append(summary.family)
        if len(set(families_seen)) != len(families_seen):
            raise SetupEvidenceError("family_summary must hold each family at most once")
        if not isinstance(self.confluence, ConfluenceSummary):
            raise TypeError(
                f"confluence must be a ConfluenceSummary, "
                f"got {type(self.confluence).__name__}"
            )
        if not isinstance(self.sufficiency, ContextState):
            raise TypeError(
                f"sufficiency must be a ContextState, got {type(self.sufficiency).__name__}"
            )
        if not isinstance(self.decision_ready, bool):
            raise TypeError("decision_ready must be a bool")
        if self.setup_identity is not None and not isinstance(
            self.setup_identity, SetupIdentityRef
        ):
            raise TypeError("setup_identity must be a SetupIdentityRef or None")
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))

    @property
    def all_items(self) -> tuple[EvidenceItem, ...]:
        """Every item in the report, in group order. Derived, never stored."""
        return self.supporting + self.conflicting + self.missing + self.unavailable
