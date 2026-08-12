"""The one table naming every persisted record type and how to handle it.

Ten kinds, one row each. Every other module in this package reads this table and
none of them special-cases a type by name: the store does not know what a trade
is, the index does not know what a snapshot is, and the version engine does not
know which records can be superseded. They ask the spec.

**Why a table rather than a method on each record.** Putting `durability_class`
or `storage_shape` on the domain types would push an infrastructure concern into
the pure layer, and the data model's whole reason for keeping those two apart is
that the domain must stay describable without reference to where it is kept. The
cost of the table is that adding a record type is an edit here; that is the
intended cost, because a record type that nobody deliberately filed is a record
type whose durability class nobody chose.

**The four durability classes are the architecture's §24.3, unchanged.** They are
not decoration: `SOURCE_OF_TRUTH` and `CAPTURED_ARTIFACT` refuse `update` and
`replace` for different reasons, `REBUILDABLE_PROJECTION` refuses to be stored at
all, and a test deletes every projection, recomputes it and asserts the answer is
identical.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

from fmis.analysis_record import (
    ANALYSIS_RECORD_KIND,
    SUPPORTED_ANALYSIS_RECORD_VERSIONS,
    AnalysisRecord,
)
from fmis.archive.identity import validate_record_id as validate_archive_record_id
from fmis.journal import (
    JOURNAL_ENTRY_KIND,
    JOURNAL_ENTRY_TYPE_SLUG,
    SUPPORTED_JOURNAL_ENTRY_VERSIONS,
    JournalEntry,
)
from fmis.ledger import (
    CORRECTION_KIND,
    CORRECTION_TYPE_SLUG,
    SUPPORTED_CORRECTION_VERSIONS,
    SUPPORTED_TRADE_VERSIONS,
    TRADE_KIND,
    TRADE_TYPE_SLUG,
    Correction,
    Trade,
)
from fmis.portfolio import (
    PORTFOLIO_SNAPSHOT_KIND,
    PORTFOLIO_SNAPSHOT_TYPE_SLUG,
    SUPPORTED_PORTFOLIO_SNAPSHOT_VERSIONS,
    PortfolioSnapshot,
)
from fmis.proposal import (
    LIFECYCLE_EVENT_TYPE_SLUG,
    PROPOSAL_KIND,
    PROPOSAL_TYPE_SLUG,
    SUPPORTED_LIFECYCLE_EVENT_VERSIONS,
    SUPPORTED_PROPOSAL_VERSIONS,
    OpportunityProposal,
    ProposalLifecycleEvent,
)
from fmis.provenance import Absent
from fmis.records import content_digest_over, validate_domain_record_id
from fmis.risk import (
    RISK_BUDGET_KIND,
    RISK_BUDGET_TYPE_SLUG,
    SUPPORTED_RISK_BUDGET_VERSIONS,
    RiskBudget,
)
from fmis.snapshotting import (
    DECISION_WINDOW_KIND,
    DECISION_WINDOW_TYPE_SLUG,
    MARKET_SNAPSHOT_KIND,
    MARKET_SNAPSHOT_TYPE_SLUG,
    SUPPORTED_DECISION_WINDOW_VERSIONS,
    SUPPORTED_MARKET_SNAPSHOT_VERSIONS,
    DecisionWindow,
    MarketSnapshot,
)

from fmis.persistence.errors import UnknownRecordKindError

__all__ = [
    "DurabilityClass",
    "StorageShape",
    "RecordKind",
    "OwnerScope",
    "RecordSpec",
    "SPECS",
    "spec_for_kind",
    "spec_for_record",
    "kind_of",
    "LIFECYCLE_EVENT_KIND",
]

#: `fmis.proposal` exports a type slug for its lifecycle event but no `…_KIND`
#: constant, because nothing in the domain cites one inside a `ConsumedSource`.
#: The store needs a kind string for every row, so this one is defined here and
#: is deliberately equal to the slug, exactly as every other kind is.
LIFECYCLE_EVENT_KIND = LIFECYCLE_EVENT_TYPE_SLUG


class DurabilityClass(Enum):
    """Architecture §24.3, as an enum the store enforces rather than documents."""

    #: Append-only, corrected by supersession, never rewritten.
    SOURCE_OF_TRUTH = "source_of_truth"
    #: Written once at a defined moment, frozen with its inputs, never regenerated.
    CAPTURED_ARTIFACT = "captured_artifact"
    #: A pure fold over sources — identical every time, and therefore never stored.
    REBUILDABLE_PROJECTION = "rebuildable_projection"
    #: Arithmetic over frozen artifacts; deletable.
    DISPOSABLE_AGGREGATE = "disposable_aggregate"


class StorageShape(Enum):
    """Architecture §24.1's two file shapes, and nothing else.

    A record file is reached at random by id. A log line is one of many in a
    calendar year, always read as an ordered sequence — *"the ledger is its own
    index"*. Nothing is stored in both shapes, and the shape is a property of the
    kind rather than a caller's choice.
    """

    RECORD_FILE = "record_file"
    EVENT_LOG = "event_log"


class RecordKind(Enum):
    """Every type this store persists. A closed vocabulary.

    An unknown member read from disk is a clean rejection: a store file naming a
    kind this build does not know was written by a newer build, and reading it
    while ignoring the kind is how a "successful" load silently drops a record.
    """

    TRADE = TRADE_KIND
    CORRECTION = CORRECTION_KIND
    LIFECYCLE_EVENT = LIFECYCLE_EVENT_KIND
    PROPOSAL = PROPOSAL_KIND
    MARKET_SNAPSHOT = MARKET_SNAPSHOT_KIND
    DECISION_WINDOW = DECISION_WINDOW_KIND
    PORTFOLIO_SNAPSHOT = PORTFOLIO_SNAPSHOT_KIND
    JOURNAL_ENTRY = JOURNAL_ENTRY_KIND
    RISK_BUDGET = RISK_BUDGET_KIND
    ANALYSIS_RECORD = ANALYSIS_RECORD_KIND


@dataclass(frozen=True, slots=True)
class OwnerScope:
    """Whose capacity a record belongs to — the axes `load_by_owner` filters on.

    FMITS has exactly one owner, so "by owner" cannot mean a user id and pretending
    otherwise would add a column that is the same value on every row forever. What
    the owner actually partitions their own activity by is the triple the domain
    already refuses to infer: the **book** (capacity pools never share), the
    **account** (where the assets are), and the **market** (what was traded).

    Every component is optional because not every record has one — a journal entry
    about the owner's own state belongs to no market, and inventing one would make
    a filter silently exclude it.
    """

    book: str | None = None
    market: str | None = None
    account: str | None = None

    def __post_init__(self) -> None:
        for name in ("book", "market", "account"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise TypeError(f"{name} must be a non-empty str or None")


def _no_scope(_: Any) -> OwnerScope:
    return OwnerScope()


def _maybe(value: Any) -> str | None:
    """A domain `T | Absent[T]` field as an optional index column.

    `None` in the index means *"this record has no such edge"*, which is exactly
    what `Absent` says. The reason text is not carried into the index: the index
    is a lookup table, and the record itself keeps the reason forever.
    """
    return None if isinstance(value, Absent) else str(value)


def _digest_of_basis(record: Any) -> str:
    return content_digest_over(record.digest_basis)


@dataclass(frozen=True, slots=True)
class RecordSpec:
    """Everything the store needs to know about one record type.

    Assembled from callables rather than attribute names so a record type that
    renames a field breaks here, at import time, instead of at the first write.
    """

    kind: RecordKind
    type_slug: str
    durability: DurabilityClass
    shape: StorageShape
    record_type: type
    supported_versions: frozenset[int]
    #: The record's own content-derived id.
    identity: Callable[[Any], str]
    #: The instant the id is stamped with, and the calendar the record files under.
    moment: Callable[[Any], datetime]
    #: The stable label a lineage or a series groups on.
    lineage_key: Callable[[Any], str]
    #: `sha256:<hex>` over the record's own digest basis.
    digest: Callable[[Any], str]
    #: The id this record supersedes, or `None`.
    supersedes: Callable[[Any], str | None]
    owner_scope: Callable[[Any], OwnerScope]
    encode: Callable[[Any], dict[str, Any]]
    decode: Callable[[Any], Any]
    #: Raises unless the text is a well-formed id *for this kind*.
    validate_id: Callable[[Any], Any]
    #: Whether `moment` may legitimately lie after the instant the record is
    #: filed. True for exactly one kind: a risk budget is the owner scheduling a
    #: limit change to take effect later, and refusing that would make "raise my
    #: per-trade risk from Monday" unrepresentable. Every other record describes
    #: something that has already happened.
    moment_may_be_future: bool = False
    #: Which kinds a record of this kind may claim to supersede. Empty for every
    #: kind that has no supersession mechanism, which is most of them.
    #:
    #: **A chain never crosses kinds**, and this is what says so. Without it a
    #: journal entry could name a trade in its `supersedes` — both are
    #: well-formed domain record ids, and neither the domain nor the id pattern
    #: can tell them apart — and the trade would then resolve to a note as its
    #: current version. The domain cannot check this: only a store knows what a
    #: given id turned out to be.
    supersedes_kinds: frozenset[RecordKind] = frozenset()

    @property
    def is_frozen(self) -> bool:
        """Whether a later record may never claim to replace this one.

        A captured artifact is frozen with its inputs; a source of truth is
        append-only but *correctable*, which is a different rule and a different
        error message.
        """
        return self.durability is DurabilityClass.CAPTURED_ARTIFACT


_SPEC_LIST: tuple[RecordSpec, ...] = (
    RecordSpec(
        kind=RecordKind.TRADE,
        type_slug=TRADE_TYPE_SLUG,
        durability=DurabilityClass.SOURCE_OF_TRUTH,
        shape=StorageShape.EVENT_LOG,
        record_type=Trade,
        supported_versions=SUPPORTED_TRADE_VERSIONS,
        identity=lambda record: record.event_id,
        moment=lambda record: record.occurred_at,
        lineage_key=lambda record: record.market.value,
        digest=lambda record: record.content_digest,
        supersedes=lambda _: None,
        owner_scope=lambda record: OwnerScope(
            book=record.book.value,
            market=record.market.value,
            account=record.account.value,
        ),
        encode=lambda record: record.to_payload(),
        decode=Trade.from_payload,
        validate_id=validate_domain_record_id,
    ),
    RecordSpec(
        kind=RecordKind.CORRECTION,
        type_slug=CORRECTION_TYPE_SLUG,
        durability=DurabilityClass.SOURCE_OF_TRUTH,
        shape=StorageShape.EVENT_LOG,
        record_type=Correction,
        supported_versions=SUPPORTED_CORRECTION_VERSIONS,
        identity=lambda record: record.event_id,
        moment=lambda record: record.occurred_at,
        lineage_key=lambda record: record.replacement.market.value,
        digest=lambda record: record.content_digest,
        supersedes=lambda record: record.supersedes,
        # A correction supersedes the trade it replaces, or the correction before
        # it in the chain. Both, because a chain of corrections is legal.
        supersedes_kinds=frozenset({RecordKind.TRADE, RecordKind.CORRECTION}),
        owner_scope=lambda record: OwnerScope(
            book=record.replacement.book.value,
            market=record.replacement.market.value,
            account=record.replacement.account.value,
        ),
        encode=lambda record: record.to_payload(),
        decode=Correction.from_payload,
        validate_id=validate_domain_record_id,
    ),
    RecordSpec(
        kind=RecordKind.LIFECYCLE_EVENT,
        type_slug=LIFECYCLE_EVENT_TYPE_SLUG,
        durability=DurabilityClass.SOURCE_OF_TRUTH,
        shape=StorageShape.EVENT_LOG,
        record_type=ProposalLifecycleEvent,
        supported_versions=SUPPORTED_LIFECYCLE_EVENT_VERSIONS,
        identity=lambda record: record.event_id,
        moment=lambda record: record.occurred_at,
        lineage_key=lambda record: record.proposal_id,
        digest=_digest_of_basis,
        supersedes=lambda record: _maybe(record.supersedes),
        supersedes_kinds=frozenset({RecordKind.LIFECYCLE_EVENT}),
        owner_scope=_no_scope,
        encode=lambda record: record.to_payload(),
        decode=ProposalLifecycleEvent.from_payload,
        validate_id=validate_domain_record_id,
    ),
    RecordSpec(
        kind=RecordKind.PROPOSAL,
        type_slug=PROPOSAL_TYPE_SLUG,
        durability=DurabilityClass.CAPTURED_ARTIFACT,
        shape=StorageShape.RECORD_FILE,
        record_type=OpportunityProposal,
        supported_versions=SUPPORTED_PROPOSAL_VERSIONS,
        identity=lambda record: record.proposal_id,
        moment=lambda record: record.created_at,
        lineage_key=lambda record: record.market.value,
        digest=lambda record: record.content_digest,
        supersedes=lambda _: None,
        owner_scope=lambda record: OwnerScope(
            book=record.book.value, market=record.market.value
        ),
        encode=lambda record: record.to_payload(),
        decode=OpportunityProposal.from_payload,
        validate_id=validate_domain_record_id,
    ),
    RecordSpec(
        kind=RecordKind.MARKET_SNAPSHOT,
        type_slug=MARKET_SNAPSHOT_TYPE_SLUG,
        durability=DurabilityClass.CAPTURED_ARTIFACT,
        shape=StorageShape.RECORD_FILE,
        record_type=MarketSnapshot,
        supported_versions=SUPPORTED_MARKET_SNAPSHOT_VERSIONS,
        identity=lambda record: record.snapshot_id,
        moment=lambda record: record.built_at,
        lineage_key=lambda record: record.market.value,
        digest=lambda record: record.content_digest,
        supersedes=lambda _: None,
        owner_scope=lambda record: OwnerScope(market=record.market.value),
        encode=lambda record: record.to_payload(),
        decode=MarketSnapshot.from_payload,
        validate_id=validate_domain_record_id,
    ),
    RecordSpec(
        kind=RecordKind.DECISION_WINDOW,
        type_slug=DECISION_WINDOW_TYPE_SLUG,
        durability=DurabilityClass.CAPTURED_ARTIFACT,
        shape=StorageShape.RECORD_FILE,
        record_type=DecisionWindow,
        supported_versions=SUPPORTED_DECISION_WINDOW_VERSIONS,
        identity=lambda record: record.window_id,
        moment=lambda record: record.last_close_time,
        lineage_key=lambda record: record.market.value,
        # A window's id covers its *reference* fields only, so its content digest
        # is taken over the identity basis too. The rows are already covered:
        # `series_digest` is one of those fields and is validated against them at
        # construction. See `store.py` on why pruning is refused rather than
        # published in place.
        digest=lambda record: content_digest_over(record.identity_basis),
        supersedes=lambda _: None,
        owner_scope=lambda record: OwnerScope(market=record.market.value),
        encode=lambda record: record.to_payload(),
        decode=DecisionWindow.from_payload,
        validate_id=validate_domain_record_id,
    ),
    RecordSpec(
        kind=RecordKind.PORTFOLIO_SNAPSHOT,
        type_slug=PORTFOLIO_SNAPSHOT_TYPE_SLUG,
        durability=DurabilityClass.CAPTURED_ARTIFACT,
        shape=StorageShape.RECORD_FILE,
        record_type=PortfolioSnapshot,
        supported_versions=SUPPORTED_PORTFOLIO_SNAPSHOT_VERSIONS,
        identity=lambda record: record.snapshot_id,
        moment=lambda record: record.as_of,
        lineage_key=lambda record: record.portfolio_id,
        digest=lambda record: record.content_digest,
        supersedes=lambda _: None,
        owner_scope=_no_scope,
        encode=lambda record: record.to_payload(),
        decode=PortfolioSnapshot.from_payload,
        validate_id=validate_domain_record_id,
    ),
    RecordSpec(
        kind=RecordKind.JOURNAL_ENTRY,
        type_slug=JOURNAL_ENTRY_TYPE_SLUG,
        durability=DurabilityClass.SOURCE_OF_TRUTH,
        shape=StorageShape.RECORD_FILE,
        record_type=JournalEntry,
        supported_versions=SUPPORTED_JOURNAL_ENTRY_VERSIONS,
        identity=lambda record: record.entry_id,
        moment=lambda record: record.recorded_at,
        lineage_key=lambda record: record.kind.value,
        digest=_digest_of_basis,
        supersedes=lambda record: _maybe(record.supersedes),
        supersedes_kinds=frozenset({RecordKind.JOURNAL_ENTRY}),
        owner_scope=_no_scope,
        encode=lambda record: record.to_payload(),
        decode=JournalEntry.from_payload,
        validate_id=validate_domain_record_id,
    ),
    RecordSpec(
        kind=RecordKind.RISK_BUDGET,
        type_slug=RISK_BUDGET_TYPE_SLUG,
        durability=DurabilityClass.SOURCE_OF_TRUTH,
        shape=StorageShape.RECORD_FILE,
        record_type=RiskBudget,
        supported_versions=SUPPORTED_RISK_BUDGET_VERSIONS,
        identity=lambda record: record.budget_record_id,
        moment=lambda record: record.effective_from,
        lineage_key=lambda record: record.budget_id,
        digest=_digest_of_basis,
        # A budget version supersedes nothing: every past version stays
        # resolvable and a later `effective_from` is what makes it current.
        # Recording supersession here would make an old budget unreadable at the
        # exact moment a frozen check needs to cite it.
        supersedes=lambda _: None,
        owner_scope=_no_scope,
        encode=lambda record: record.to_payload(),
        decode=RiskBudget.from_payload,
        validate_id=validate_domain_record_id,
        moment_may_be_future=True,
    ),
    RecordSpec(
        kind=RecordKind.ANALYSIS_RECORD,
        type_slug=ANALYSIS_RECORD_KIND,
        durability=DurabilityClass.CAPTURED_ARTIFACT,
        shape=StorageShape.RECORD_FILE,
        record_type=AnalysisRecord,
        supported_versions=SUPPORTED_ANALYSIS_RECORD_VERSIONS,
        # The one kind whose id is not a *domain* record id: an analysis citation
        # names a page `fmis.archive` wrote, under that package's id scheme, and
        # re-deriving it here would create a second identity for one page.
        identity=lambda record: record.record_id,
        moment=lambda record: record.analysis_as_of,
        lineage_key=lambda record: record.subject[0],
        digest=lambda record: record.content_digest,
        supersedes=lambda _: None,
        owner_scope=_no_scope,
        encode=lambda record: record.to_payload(),
        decode=AnalysisRecord.from_payload,
        validate_id=validate_archive_record_id,
    ),
)

#: The table, keyed by kind. A mapping proxy so no caller can add a row at
#: runtime — a store whose spec table depends on import order is a store whose
#: layout depends on import order.
SPECS: Mapping[RecordKind, RecordSpec] = MappingProxyType(
    {spec.kind: spec for spec in _SPEC_LIST}
)

_BY_TYPE: Mapping[type, RecordSpec] = MappingProxyType(
    {spec.record_type: spec for spec in _SPEC_LIST}
)


def spec_for_kind(kind: RecordKind) -> RecordSpec:
    if not isinstance(kind, RecordKind):
        raise UnknownRecordKindError(
            f"kind must be a RecordKind, got {type(kind).__name__}"
        )
    return SPECS[kind]


def spec_for_record(record: Any) -> RecordSpec:
    """The spec for a record instance, by exact type.

    Exact type rather than `isinstance`: a subclass of `Trade` is not a trade as
    far as storage is concerned, because its extra fields would be silently
    dropped by `Trade.to_payload` and the round-trip claim would be false.
    """
    spec = _BY_TYPE.get(type(record))
    if spec is None:
        raise UnknownRecordKindError(
            f"{type(record).__name__} is not a persisted record type; this store "
            f"holds {sorted(kind.value for kind in SPECS)}"
        )
    return spec


def kind_of(value: Any) -> RecordKind:
    """Read a kind string from a payload, rejecting one this build does not know."""
    try:
        return RecordKind(value)
    except ValueError as error:
        raise UnknownRecordKindError(
            f"record kind {value!r} is not known to this build; it was written by "
            f"a newer one and reading it would file it as the wrong kind"
        ) from error
