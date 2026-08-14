"""The durable store: the only write path into the trading domain, and its journal.

`fmis.persistence` is **infrastructure**. The domain packages below it are pure —
they hold no path, open no file and read no clock — and nothing in them imports
this package. The direction is one-way and a guard test asserts it, because the
day it reverses is the day a `Trade` cannot be constructed without a store to put
it in.

Architecture §24, implemented rather than restated:

* **One durable store, two file shapes.** Record files reached at random by id;
  ledger year files appended to and scanned in order. Both use ADR-0027's
  machinery unchanged — canonical encoding, content digests, atomic publication,
  typed errors, explicit schema versions, no silent repair.
* **Projections are in memory.** Positions are folded on demand and stored never.
  `PositionRepository` refuses to write, which is §24.3's classification enforced
  instead of documented.
* **Nothing is deleted and nothing is rewritten.** Corrections supersede;
  observations accumulate; the write journal is hash-chained so a removed or
  altered event is detectable rather than merely unlikely.

Ten repositories, one composition root:

| Repository | Owns | Update path |
|---|---|---|
| `TradeRepository` | `Trade` | `replace` appends a `Correction` |
| `PlanRepository` | `TradePlan` | frozen — a stop that can be edited is not a stop |
| `LedgerRepository` | the whole event stream | read-only; resolves supersession |
| `PositionRepository` | nothing | refuses every write |
| `PortfolioRepository` | `PortfolioSnapshot` | frozen |
| `JournalRepository` | `JournalEntry` | `replace` appends a superseding entry |
| `RiskRepository` | `RiskBudget` | `revise` appends the next generation |
| `SnapshotRepository` | `MarketSnapshot`, `DecisionWindow` | frozen |
| `AnalysisRecordRepository` | `AnalysisRecord` | frozen |
| `OpportunityRepository` | `OpportunityProposal`, its events | events supersede; proposals frozen |

**`update` raises everywhere.** It is a method so that callers find a message
naming the legal path rather than an `AttributeError` they have to guess past.

**Nothing here reads a clock.** Every instant — a record's own, and the moment it
was filed — is supplied by the caller, exactly as the domain requires of itself. A
store that stamps itself cannot be replayed, and a test that has to freeze a clock
becomes flaky rather than wrong.
"""

from __future__ import annotations

from fmis.persistence.appendonly import append_lines, line_count, read_lines
from fmis.persistence.base import Repository
from fmis.persistence.capital_repositories import (
    JournalRepository,
    PortfolioRepository,
    RiskRepository,
)
from fmis.persistence.composition import TradingStore
from fmis.persistence.criteria import SearchCriteria
from fmis.persistence.decision_repositories import (
    AnalysisRecordRepository,
    OpportunityRepository,
    PlanRepository,
    SnapshotRepository,
)
from fmis.persistence.envelope import (
    STORE_SCHEMA_VERSION,
    SUPPORTED_STORE_VERSIONS,
    StoredEnvelope,
)
from fmis.persistence.errors import (
    AppendOnlyViolationError,
    FrozenRecordError,
    LineageError,
    PersistenceError,
    ProjectionError,
    RecordConflictError,
    RecordMissingError,
    StoreIntegrityError,
    StoreIOError,
    StorePathError,
    UnknownRecordKindError,
)
from fmis.persistence.index import (
    INDEX_SCHEMA_VERSION,
    SUPPORTED_INDEX_VERSIONS,
    IndexEntry,
    RecordIndex,
)
from fmis.persistence.journal_engine import (
    JOURNAL_EVENT_SCHEMA_VERSION,
    JOURNAL_EVENT_TYPE_SLUG,
    SUPPORTED_JOURNAL_EVENT_VERSIONS,
    JournalEngine,
    JournalEvent,
    JournalVerification,
    WriteOperation,
    WriteSource,
)
from fmis.persistence.kinds import (
    SPECS,
    DurabilityClass,
    OwnerScope,
    RecordKind,
    RecordSpec,
    StorageShape,
    kind_of,
    spec_for_kind,
    spec_for_record,
)
from fmis.persistence.layout import (
    DEFAULT_STORE_ROOT,
    StoreLayout,
    default_store_root,
)
from fmis.persistence.ledger_repositories import (
    LedgerRepository,
    PositionRepository,
    TradeRepository,
)
from fmis.persistence.lineage import Lineage, VersionEngine
from fmis.persistence.store import (
    RecordCheck,
    RecordStore,
    StoreVerification,
    WriteReceipt,
    WriteRequest,
)

__all__ = [
    # errors
    "PersistenceError",
    "RecordMissingError",
    "RecordConflictError",
    "FrozenRecordError",
    "ProjectionError",
    "UnknownRecordKindError",
    "StoreIntegrityError",
    "AppendOnlyViolationError",
    "LineageError",
    "StorePathError",
    "StoreIOError",
    # the record table
    "RecordKind",
    "RecordSpec",
    "SPECS",
    "DurabilityClass",
    "StorageShape",
    "OwnerScope",
    "spec_for_kind",
    "spec_for_record",
    "kind_of",
    # layout and files
    "StoreLayout",
    "DEFAULT_STORE_ROOT",
    "default_store_root",
    "read_lines",
    "append_lines",
    "line_count",
    # the envelope
    "StoredEnvelope",
    "STORE_SCHEMA_VERSION",
    "SUPPORTED_STORE_VERSIONS",
    # the index
    "IndexEntry",
    "RecordIndex",
    "INDEX_SCHEMA_VERSION",
    "SUPPORTED_INDEX_VERSIONS",
    # the journal engine
    "JournalEngine",
    "JournalEvent",
    "JournalVerification",
    "WriteSource",
    "WriteOperation",
    "JOURNAL_EVENT_SCHEMA_VERSION",
    "SUPPORTED_JOURNAL_EVENT_VERSIONS",
    "JOURNAL_EVENT_TYPE_SLUG",
    # the store
    "RecordStore",
    "WriteRequest",
    "WriteReceipt",
    "RecordCheck",
    "StoreVerification",
    # the version engine
    "Lineage",
    "VersionEngine",
    "SearchCriteria",
    # the repositories
    "Repository",
    "TradeRepository",
    "PlanRepository",
    "LedgerRepository",
    "PositionRepository",
    "PortfolioRepository",
    "JournalRepository",
    "RiskRepository",
    "SnapshotRepository",
    "AnalysisRecordRepository",
    "OpportunityRepository",
    "TradingStore",
]
