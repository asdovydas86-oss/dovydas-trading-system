"""Value types for the Swing Trading Workspace.

A `Workspace` is a **first-class object**, not the output of a print statement.
The terminal renderer, and every future Telegram, dashboard or JSON renderer,
consume this model and nothing else. A renderer may drop sections and shorten
values; it may never add a claim, reorder sections, or change a value's tier.

**The frame is fixed and its empty slots are rendered.** `SECTION_ORDER` lists
every section this system will ever show in the order it shows them, including
the ones no milestone has built yet. An omitted section is invisible, and an
invisible gap is indistinguishable from a gap that does not exist — which is how
a reader learns, over months, that risk was considered when it was not.
`SPEC` §6 requires *missing data* as a first-class output and `SPEC` §7 names
"excessive confidence from incomplete data" as a bias to guard against, so an
unbuilt section renders an `Unavailable` carrying the milestone that owns it and
the inference it forbids.

**Tiers are a property of the data, not of the renderer.** Every value states
whether it is a measured fact, a state derived under a stated policy, an
interpretation, or an absence — so no renderer can promote one accidentally, and
a future interpretation layer cannot leak into a fact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Union

__all__ = [
    "WORKSPACE_SCHEMA_VERSION",
    "SECTION_ORDER",
    "SectionId",
    "SectionStatus",
    "Tier",
    "Provenance",
    "Row",
    "RowBlock",
    "TableBlock",
    "NoteBlock",
    "Block",
    "Section",
    "Unavailable",
    "WorkspaceSection",
    "Workspace",
    "WorkspaceError",
]

#: Bumped when the serialized shape changes in a way a consumer must notice.
#: Carried on every `Workspace` so a stored artifact can be read years later —
#: which is what Memory (`AL`) will need and what a schema-less model cannot give.
WORKSPACE_SCHEMA_VERSION = 1


class WorkspaceError(Exception):
    """Base class for every workspace failure.

    Follows the package-error convention `IngestError`, `LevelCrossingError` and
    `MarketRegimeError` established below, so a caller can catch this layer's
    failures as a group.
    """


class SectionId(str, Enum):
    """Every section the workspace will ever show, built or not.

    Members exist for sections no milestone has implemented. That is deliberate:
    the identifier is what a future provider registers against, and reserving it
    now is what makes that milestone a registration rather than a redesign.
    """

    INSTRUMENT = "instrument"
    REGIME = "regime"
    STRUCTURE = "structure"
    LEVELS = "levels"
    EVIDENCE = "evidence"
    CONFLICTS = "conflicts"
    CONTEXT = "context"
    RISK = "risk"
    PORTFOLIO = "portfolio"
    TRADE_PLAN = "trade_plan"
    INTERPRETATION = "interpretation"
    LIMITATIONS = "limitations"


#: The one authoritative page order. **Never** enum definition order — an
#: ordering contract resting on that changes silently when a member is renamed,
#: the same rule `_SIDE_RANK`, `_ROLE_ORDER` and `_EVIDENCE_ORDER` follow.
#:
#: The order is the argument. Data quality first, because a stale or short window
#: invalidates everything under it. Regime second, because `SPEC` §5 puts the
#: higher timeframe's environment before the setup and because the v3 prompt's
#: own first correction was "regime classification first". Structure third, so a
#: reader learns the environment before forming a directional impression of it.
#: Conflicts before risk, so nothing is planned around evidence that disagrees,
#: and the decision context immediately after them — it is the page's gate, and
#: a gate belongs after everything it judges and before everything it guards.
#: Interpretation last, so a model's narrative cannot anchor the facts above it.
SECTION_ORDER: tuple[SectionId, ...] = (
    SectionId.INSTRUMENT,
    SectionId.REGIME,
    SectionId.STRUCTURE,
    SectionId.LEVELS,
    SectionId.EVIDENCE,
    SectionId.CONFLICTS,
    SectionId.CONTEXT,
    SectionId.RISK,
    SectionId.PORTFOLIO,
    SectionId.TRADE_PLAN,
    SectionId.INTERPRETATION,
    SectionId.LIMITATIONS,
)

_ORDER_RANK: Mapping[SectionId, int] = MappingProxyType(
    {section: rank for rank, section in enumerate(SECTION_ORDER)}
)


class SectionStatus(str, Enum):
    """What a section managed to say.

    `PARTIAL` is distinct from `AVAILABLE` on purpose: a section that reported
    what it could while some input was missing has not answered its question, and
    collapsing the two would hide exactly the gap `SPEC` §6 asks to be shown.

    `UNAVAILABLE` means no engine owns this yet. `FAILED` means one does and it
    could not run — a different fact, and the reader's response differs.
    """

    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class Tier(str, Enum):
    """Where a value came from, and therefore what may be done with it.

    * `FACT` — measured or computed by an engine, reproducibly.
    * `DERIVED` — a state produced from facts under a **stated policy**, which
      travels with it. Regime dimensions and evidence groupings are this.
    * `INTERPRETATION` — written by a model or a human. **Never** counted as
      evidence, never read by a computation, always visually separated.
    * `ABSENCE` — a value that is not there. Never negative evidence: a
      warming-up indicator says nothing, and counting silence as disagreement is
      how a system manufactures confidence it has not earned.
    """

    FACT = "fact"
    DERIVED = "derived"
    INTERPRETATION = "interpretation"
    ABSENCE = "absence"


@dataclass(frozen=True, slots=True)
class Provenance:
    """Which engine produced a section, under which policy, as of when.

    A section without provenance is not reproducible, and `ARCH` §9 requires a
    classification to be checkable against history. ``policy_id`` is ``None`` for
    sections that apply no threshold — stating that plainly is better than an
    empty string a reader must interpret.
    """

    engine: str
    policy_id: str | None = None
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.engine, str) or not self.engine.strip():
            raise WorkspaceError("engine must be a non-empty str")
        if self.policy_id is not None and not isinstance(self.policy_id, str):
            raise TypeError("policy_id must be a str or None")
        if self.as_of is not None and not isinstance(self.as_of, datetime):
            raise TypeError("as_of must be a datetime or None")


@dataclass(frozen=True, slots=True)
class Row:
    """One labelled value, with an optional note and an explicit tier.

    ``value`` is already a string. Formatting a number is presentation, but
    *choosing* how many decimals a price carries is a judgement about
    significance, and making each provider state it keeps that judgement beside
    the data rather than inside a renderer that cannot know the instrument.
    """

    label: str
    value: str
    note: str = ""
    tier: Tier = Tier.FACT

    def __post_init__(self) -> None:
        for name in ("label", "value", "note"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be a str")
        if not self.label.strip():
            raise WorkspaceError("label must not be blank")
        if not isinstance(self.tier, Tier):
            raise TypeError(f"tier must be a Tier, got {type(self.tier).__name__}")


@dataclass(frozen=True, slots=True)
class RowBlock:
    """A run of label/value rows under an optional heading."""

    rows: tuple[Row, ...]
    heading: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.rows, tuple):
            raise TypeError("rows must be a tuple of Row")
        for position, row in enumerate(self.rows):
            if not isinstance(row, Row):
                raise TypeError(f"rows[{position}] must be a Row")
        if not isinstance(self.heading, str):
            raise TypeError("heading must be a str")


@dataclass(frozen=True, slots=True)
class TableBlock:
    """A column-aligned table. Every record must match the column count.

    Validated rather than padded: a short record means a provider lost a value,
    and silently filling it would put a blank where a fact was expected.
    """

    columns: tuple[str, ...]
    records: tuple[tuple[str, ...], ...]
    heading: str = ""

    def __post_init__(self) -> None:
        # A wrong type and an empty tuple are different mistakes: one is a
        # caller passing the wrong thing, the other a provider producing nothing.
        if not isinstance(self.columns, tuple):
            raise TypeError(
                f"columns must be a tuple, got {type(self.columns).__name__}"
            )
        if not self.columns:
            raise WorkspaceError("columns must not be empty")
        for column in self.columns:
            if not isinstance(column, str):
                raise TypeError("every column must be a str")
        if not isinstance(self.records, tuple):
            raise TypeError("records must be a tuple of tuples")
        width = len(self.columns)
        for position, record in enumerate(self.records):
            if not isinstance(record, tuple):
                raise TypeError(f"records[{position}] must be a tuple")
            if len(record) != width:
                raise WorkspaceError(
                    f"records[{position}] has {len(record)} values but the table "
                    f"declares {width} columns"
                )
            for cell in record:
                if not isinstance(cell, str):
                    raise TypeError(f"records[{position}] cells must be str")
        if not isinstance(self.heading, str):
            raise TypeError("heading must be a str")


@dataclass(frozen=True, slots=True)
class NoteBlock:
    """Free-standing lines that qualify what a section showed.

    Separate from `Section.caveats`, which qualify the section as a whole: a note
    sits with the block it belongs to, so a reader meets it beside the numbers it
    is about rather than at the end.
    """

    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.notes, tuple):
            raise TypeError(f"notes must be a tuple, got {type(self.notes).__name__}")
        if not self.notes:
            raise WorkspaceError("notes must not be empty")
        for note in self.notes:
            if not isinstance(note, str) or not note.strip():
                raise WorkspaceError("every note must be a non-empty str")


#: The three block shapes a section body may contain. A closed union rather than
#: one fat type with optional fields: the renderer dispatches on type through an
#: explicit mapping, so adding a fourth shape fails loudly at that mapping
#: instead of rendering as blank.
Block = Union[RowBlock, TableBlock, NoteBlock]

_BLOCK_TYPES = (RowBlock, TableBlock, NoteBlock)


@dataclass(frozen=True, slots=True)
class Section:
    """One answered section of the workspace.

    Every section exposes the same six things — ``id``, ``title``, ``status``,
    ``summary``, ``body``, ``provenance`` — which is what lets one renderer walk
    a page it was not written against.

    ``summary`` is the section's answer in at most a few lines, so a reader
    scanning only summaries still meets every section's conclusion. ``caveats``
    say what this section specifically does not claim.
    """

    id: SectionId
    title: str
    status: SectionStatus
    summary: tuple[str, ...] = ()
    body: tuple[Block, ...] = ()
    caveats: tuple[str, ...] = ()
    provenance: Provenance | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, SectionId):
            raise TypeError(f"id must be a SectionId, got {type(self.id).__name__}")
        if not isinstance(self.title, str) or not self.title.strip():
            raise WorkspaceError("title must be a non-empty str")
        if not isinstance(self.status, SectionStatus):
            raise TypeError("status must be a SectionStatus")
        if self.status is SectionStatus.UNAVAILABLE:
            raise WorkspaceError(
                "an unavailable section must be an Unavailable, not a Section "
                "with an unavailable status; the two carry different obligations"
            )
        for name in ("summary", "caveats"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple of str")
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    raise WorkspaceError(f"every {name} line must be a non-empty str")
        if not isinstance(self.body, tuple):
            raise TypeError("body must be a tuple of blocks")
        for position, block in enumerate(self.body):
            if not isinstance(block, _BLOCK_TYPES):
                raise TypeError(
                    f"body[{position}] must be a RowBlock, TableBlock or NoteBlock, "
                    f"got {type(block).__name__}"
                )
        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            raise TypeError("provenance must be a Provenance or None")
        if self.status is SectionStatus.FAILED and not self.reason:
            raise WorkspaceError(
                "a failed section must say why; a failure without a reason is "
                "indistinguishable from an empty one"
            )
        if self.reason is not None and not isinstance(self.reason, str):
            raise TypeError("reason must be a str or None")


@dataclass(frozen=True, slots=True)
class Unavailable:
    """A section no milestone has built yet — rendered, never hidden.

    ``owner`` names the milestone or epic that will fill this slot, so a reader
    meets a plan rather than a blank. ``prohibition`` states the inference the
    absence forbids, which is the part that actually protects the reader: an
    empty risk section that says nothing is read as "risk is fine", and one that
    says *"no position size shown here would be legitimate"* is not.

    It exposes the same surface as `Section` — ``status`` is always
    `UNAVAILABLE`, ``body`` is always empty, ``provenance`` is always ``None`` —
    so a renderer treats the two alike without a special case.
    """

    id: SectionId
    title: str
    owner: str
    reason: str
    prohibition: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, SectionId):
            raise TypeError(f"id must be a SectionId, got {type(self.id).__name__}")
        for name in ("title", "owner", "reason", "prohibition"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise WorkspaceError(f"{name} must be a non-empty str")

    @property
    def status(self) -> SectionStatus:
        """Always `UNAVAILABLE` — a projection, so it cannot be set otherwise."""
        return SectionStatus.UNAVAILABLE

    @property
    def summary(self) -> tuple[str, ...]:
        """The reason and the prohibition, which is the whole answer here."""
        return (self.reason, self.prohibition)

    @property
    def body(self) -> tuple[Block, ...]:
        """Always empty. There is nothing to show, and nothing is shown."""
        return ()

    @property
    def caveats(self) -> tuple[str, ...]:
        return ()

    @property
    def provenance(self) -> Provenance | None:
        """Always ``None``: no engine produced this, which is the point."""
        return None

    @property
    def reason_text(self) -> str:
        return self.reason


#: Either kind of section. Both expose id, title, status, summary, body,
#: caveats and provenance, which is the whole contract a renderer needs.
WorkspaceSection = Union[Section, Unavailable]

_SECTION_TYPES = (Section, Unavailable)


@dataclass(frozen=True, slots=True)
class Workspace:
    """One instrument, one objective, one instant — every section, in one object.

    This is the artifact. The CLI renders it, a future Telegram renderer renders
    a subset of it, Memory will store it, and an interpretation layer will read
    its serialized form. None of those consumers re-derives anything, which is
    what keeps one page consistent across four surfaces.

    ``sections`` must contain **every** id in `SECTION_ORDER`, exactly once, in
    that order. Completeness is validated rather than assumed: a page that
    silently dropped its risk section would look finished.
    """

    symbol: str
    objective: str
    as_of: datetime
    source: str
    sections: tuple[WorkspaceSection, ...]
    schema_version: int = WORKSPACE_SCHEMA_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("symbol", "objective", "source"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise WorkspaceError(f"{name} must be a non-empty str")
        if not isinstance(self.as_of, datetime):
            raise TypeError(
                f"as_of must be a datetime, got {type(self.as_of).__name__}"
            )
        if not isinstance(self.sections, tuple):
            raise TypeError("sections must be a tuple")
        for position, section in enumerate(self.sections):
            if not isinstance(section, _SECTION_TYPES):
                raise TypeError(
                    f"sections[{position}] must be a Section or Unavailable, got "
                    f"{type(section).__name__}"
                )
        ids = [section.id for section in self.sections]
        if len(set(ids)) != len(ids):
            raise WorkspaceError(
                "a workspace must not repeat a section; two answers to one "
                "question let a reader pick the one they prefer"
            )
        if set(ids) != set(SECTION_ORDER):
            missing = [s.value for s in SECTION_ORDER if s not in set(ids)]
            raise WorkspaceError(
                f"every section must be present, including unavailable ones; "
                f"missing: {missing}"
            )
        if ids != sorted(ids, key=_ORDER_RANK.__getitem__):
            raise WorkspaceError(
                "sections must follow SECTION_ORDER; the order is part of the "
                "contract because it is what a reader is anchored by"
            )
        if not isinstance(self.schema_version, int) or isinstance(
            self.schema_version, bool
        ):
            raise TypeError("schema_version must be an int")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def by_id(self) -> Mapping[SectionId, WorkspaceSection]:
        """Lookup by id — a projection over ``sections``, never a second store."""
        return MappingProxyType({section.id: section for section in self.sections})

    @property
    def available(self) -> tuple[WorkspaceSection, ...]:
        """Sections that answered, fully or partially."""
        return tuple(
            section
            for section in self.sections
            if section.status in (SectionStatus.AVAILABLE, SectionStatus.PARTIAL)
        )

    @property
    def unavailable(self) -> tuple[WorkspaceSection, ...]:
        """Sections no milestone has built. Rendered, never hidden."""
        return tuple(
            section
            for section in self.sections
            if section.status is SectionStatus.UNAVAILABLE
        )


def require_sections(sections: Sequence[WorkspaceSection]) -> tuple[WorkspaceSection, ...]:
    """Order a section sequence canonically, rejecting anything unrecognised.

    Providers may be registered in any order; the page order is this module's to
    decide, and deciding it here means no builder can accidentally publish a
    different one.
    """
    if isinstance(sections, (str, bytes)) or not isinstance(sections, Sequence):
        raise TypeError("sections must be a non-string sequence")
    for position, section in enumerate(sections):
        if not isinstance(section, _SECTION_TYPES):
            raise TypeError(
                f"sections[{position}] must be a Section or Unavailable, got "
                f"{type(section).__name__}"
            )
    return tuple(sorted(sections, key=lambda s: _ORDER_RANK[s.id]))
