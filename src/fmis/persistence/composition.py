"""`TradingStore` — the ten repositories over one root, wired once.

A composition root, and nothing more. It constructs; it does not decide. No method
here computes a value, resolves a policy or interprets a record: every one of those
lives in the repository that owns the kind, and a convenience method here would
become the eleventh place a question is answered.

**One store, one journal, one index.** The repositories share a single
`RecordStore`, which is what makes the write journal a complete account of the
store rather than nine partial ones. Constructing two `TradingStore`s over one root
is legal and safe — they hold no state between calls — but they are still one
writer, and the layout's exclusive lock is what makes that true rather than hoped.
"""

from __future__ import annotations

from pathlib import Path

from fmis.money import DustPolicy

from fmis.persistence.capital_repositories import (
    JournalRepository,
    PortfolioRepository,
    RiskRepository,
)
from fmis.persistence.decision_repositories import (
    AnalysisRecordRepository,
    OpportunityRepository,
    PlanRepository,
    SnapshotRepository,
)
from fmis.persistence.journal_engine import JournalEngine
from fmis.persistence.ledger_repositories import (
    LedgerRepository,
    PositionRepository,
    TradeRepository,
)
from fmis.persistence.lineage import VersionEngine
from fmis.persistence.store import RecordStore, StoreVerification

__all__ = ["TradingStore"]


class TradingStore:
    """Every repository FMITS has, over one durable store root."""

    def __init__(self, root: Path | str, *, dust: DustPolicy) -> None:
        """`dust` is required because `PositionRepository` cannot fold without it.

        What counts as flat is the owner's threshold. Defaulting it here would put
        a policy number in a composition root, and the position where one round trip
        ends and the next begins would silently become this file's decision.
        """
        if not isinstance(dust, DustPolicy):
            raise TypeError("dust must be a DustPolicy")
        self._store = RecordStore(root)
        self._dust = dust
        self.trades = TradeRepository(self._store)
        self.plans = PlanRepository(self._store)
        self.ledger = LedgerRepository(self._store)
        self.positions = PositionRepository(self._store, dust=dust)
        self.portfolios = PortfolioRepository(self._store)
        self.journals = JournalRepository(self._store)
        self.risk = RiskRepository(self._store)
        self.snapshots = SnapshotRepository(self._store)
        self.analyses = AnalysisRecordRepository(self._store)
        self.opportunities = OpportunityRepository(self._store)

    @property
    def root(self) -> Path:
        return self._store.root

    @property
    def dust(self) -> DustPolicy:
        return self._dust

    @property
    def store(self) -> RecordStore:
        return self._store

    @property
    def write_journal(self) -> JournalEngine:
        """The store's own audit trail — not `journals`, which holds the owner's."""
        return self._store.journal

    @property
    def versions(self) -> VersionEngine:
        return VersionEngine(self._store)

    def verify(self) -> StoreVerification:
        """One sweep over everything: chain, payloads, index, orphans, lineage."""
        return self._store.verify()

    def repositories(self) -> tuple[object, ...]:
        """All ten, in a stable order — for sweeps that must cover every one."""
        return (
            self.trades,
            self.plans,
            self.ledger,
            self.positions,
            self.portfolios,
            self.journals,
            self.risk,
            self.snapshots,
            self.analyses,
            self.opportunities,
        )
