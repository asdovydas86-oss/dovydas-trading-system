"""Portfolio snapshots, risk budgets and the owner's journal.

Three repositories with three different answers to *"what does 'the latest one'
mean"*, and the differences are the reason they are not one class:

* **`PortfolioRepository`** holds *observations*. Three snapshots of one portfolio
  are three valued readings at three instants; none supersedes another, and the
  "latest" is simply the most recent one taken.
* **`RiskRepository`** holds *generations*. Three budgets with one `budget_id` are
  three versions of one policy, and only the one whose `effective_from` has passed
  is in force. Resolving that is a fold, and a check dated before a change resolves
  to the older version — which is what keeps a frozen constraint check meaningful
  after the owner tightens a limit.
* **`JournalRepository`** holds *entries*, which are the only records here with a
  genuine supersession chain: an entry the owner rewrote names the one it replaces,
  and both stay readable forever.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fmis.journal import JournalEntry, JournalKind, LinkKind, TradeJournal
from fmis.portfolio import PortfolioSnapshot
from fmis.provenance import Absent
from fmis.records import require_member, require_text, require_utc
from fmis.risk import RiskBudget, RiskBudgetState, effective_budget, evaluate_budget

from fmis.persistence.base import Repository
from fmis.persistence.criteria import SearchCriteria
from fmis.persistence.errors import PersistenceError, RecordMissingError
from fmis.persistence.kinds import RecordKind
from fmis.persistence.store import WriteReceipt, WriteRequest

__all__ = ["PortfolioRepository", "RiskRepository", "JournalRepository"]


class PortfolioRepository(Repository):
    """`PortfolioSnapshot` — frozen, valued observations of one portfolio."""

    kinds = (RecordKind.PORTFOLIO_SNAPSHOT,)

    def snapshots(
        self, portfolio_id: str | None = None, *, criteria: SearchCriteria | None = None
    ) -> tuple[PortfolioSnapshot, ...]:
        """Every snapshot, oldest first, optionally for one portfolio."""
        base = criteria or SearchCriteria()
        if portfolio_id is None:
            return self.search(base)
        return self.search(
            base.narrowed(lineage_key=require_text(portfolio_id, "portfolio_id"))
        )

    def latest(self, portfolio_id: str) -> PortfolioSnapshot | None:
        """The most recent observation of one portfolio, or `None` if there is none."""
        rows = self.entries(
            criteria=SearchCriteria(
                lineage_key=require_text(portfolio_id, "portfolio_id")
            )
        )
        return None if not rows else self._store.load(rows[-1].record_id)

    def as_of(self, portfolio_id: str, moment: datetime) -> PortfolioSnapshot | None:
        """The latest observation taken at or before `moment`.

        On the `as_of` axis, not the `written_at` axis: this answers *"what was the
        portfolio worth then"*, and `at()` on any repository answers *"what did the
        store say then"*. Both are legitimate and they are not the same question.
        """
        entry = self._versions.series_at(
            RecordKind.PORTFOLIO_SNAPSHOT,
            require_text(portfolio_id, "portfolio_id"),
            require_utc(moment, "moment"),
        )
        return None if entry is None else self._store.load(entry.record_id)

    def portfolio_ids(self) -> tuple[str, ...]:
        return tuple(sorted({entry.lineage_key for entry in self.entries()}))


class RiskRepository(Repository):
    """`RiskBudget` config events, resolved by `effective_from`.

    Every past version stays readable and resolvable, and a change **never**
    re-evaluates a frozen check: that check cited the version it ran against, and
    re-running it later answers a different question because both the limits and
    the portfolio have moved.

    **This repository invents no threshold.** Every value is the owner's, and the
    only thing here is arithmetic over which of their versions applies when.
    """

    kinds = (RecordKind.RISK_BUDGET,)

    def revise(self, budget: RiskBudget, *, request: WriteRequest) -> WriteReceipt:
        """Append the next generation of a budget the store already holds.

        Refuses a version that does not move forward. Two versions of one budget
        sharing an `effective_from` makes "which limits applied" depend on a tie
        the fold breaks by policy version — a resolvable but invisible decision,
        and an owner who meant to schedule a change would rather be told.
        """
        if not isinstance(budget, RiskBudget):
            raise TypeError("budget must be a RiskBudget")
        existing = self.versions_of(budget.budget_id)
        if not existing:
            raise RecordMissingError(
                f"no budget {budget.budget_id!r} is stored; the first version is "
                "created, not revised"
            )
        latest = existing[-1]
        if budget.effective_from <= latest.effective_from:
            raise PersistenceError(
                f"this version takes effect at "
                f"{budget.effective_from.isoformat()}, at or before the stored "
                f"version at {latest.effective_from.isoformat()}. A budget "
                "generation moves forward; back-dating one would change which "
                "limits a already-frozen check is deemed to have run against"
            )
        # Appended, not superseded. A new generation does not supersede the old
        # one: the old one stays in force for every instant before the change, and
        # recording it as superseded would make it unresolvable at exactly the
        # moment a frozen check needs to cite it.
        return self.create(budget, request=request.appending())

    def versions_of(self, budget_id: str) -> tuple[RiskBudget, ...]:
        """Every generation of one budget, oldest `effective_from` first."""
        return tuple(
            self._store.load(entry.record_id)
            for entry in self._versions.series(
                RecordKind.RISK_BUDGET, require_text(budget_id, "budget_id")
            )
        )

    def in_force_at(self, budget_id: str, moment: datetime) -> RiskBudget | Absent:
        """The generation in force at an instant — the domain's own fold, applied.

        Returns `Absent(reason)` when nothing was in force yet, never `None` and
        never the earliest version: *"no budget existed"* and *"the first budget
        applied"* are different facts, and a caller that cannot tell them apart will
        evaluate a trade against limits nobody had set.
        """
        return effective_budget(
            self.versions_of(budget_id), require_utc(moment, "moment")
        )

    def budget_ids(self) -> tuple[str, ...]:
        return tuple(sorted({entry.lineage_key for entry in self.entries()}))

    def evaluate(
        self,
        budget_id: str,
        *,
        moment: datetime,
        measurements: dict[str, Any],
    ) -> RiskBudgetState:
        """Evaluate supplied measurements against the generation in force.

        **This computes no measurement.** Deriving open risk, drawdown and cluster
        exposure needs positions, marks and a portfolio snapshot wired together; the
        domain's `RiskBudgetState` evaluates values it is given, and so does this.
        Passing measurements in stops the one place a limit is judged from also
        becoming the place exposure is defined.
        """
        when = require_utc(moment, "moment")
        budget = self.in_force_at(budget_id, when)
        if isinstance(budget, Absent):
            raise PersistenceError(
                f"no risk budget {budget_id!r} was in force at "
                f"{when.isoformat()}: {budget.reason}"
            )
        return evaluate_budget(budget, measurements, evaluated_at=when)


class JournalRepository(Repository):
    """`JournalEntry` — the owner's own words, and the only place their state lives.

    **Not the write journal.** `fmis.persistence.JournalEvent` records what the
    store did; this holds what the owner wrote. The two never mix, and a single
    class over both would put an audit trail and a diary in one table.
    """

    kinds = (RecordKind.JOURNAL_ENTRY,)

    def replace(
        self,
        record_id: str,
        superseding: JournalEntry | None = None,
        *,
        request: WriteRequest | None = None,
        **_: Any,
    ) -> WriteReceipt:
        """Append an entry that supersedes an earlier one. Both stay readable.

        The owner rewriting a note is not the owner deleting one. What they first
        wrote is frequently the more interesting record — *"I felt uneasy about that
        one"*, written before a loss, is signal; written after it, it is hindsight —
        and a store that let the second overwrite the first would destroy the only
        evidence of which it was.
        """
        target = require_text(record_id, "record_id")
        if superseding is None or request is None:
            raise PersistenceError(
                "superseding a journal entry needs the replacement entry and a "
                "WriteRequest saying who is superseding it and why"
            )
        if not isinstance(superseding, JournalEntry):
            raise TypeError("superseding must be a JournalEntry")
        if isinstance(superseding.supersedes, Absent):
            raise PersistenceError(
                "the replacement entry names nothing it supersedes; set its "
                "`supersedes` field, so the link survives in the record itself and "
                "not only in this store's index"
            )
        if superseding.supersedes != target:
            raise PersistenceError(
                f"this entry supersedes {superseding.supersedes!r}, not the entry "
                f"{target!r} it was asked to replace"
            )
        if not self._store.exists(target):
            raise RecordMissingError(f"journal entry {target!r} is not in this store")
        return self._store.publish(superseding, request=request.superseding())

    def entries_of_kind(self, kind: JournalKind) -> tuple[JournalEntry, ...]:
        require_member(kind, JournalKind, "kind")
        return self.search(SearchCriteria(lineage_key=kind.value))

    def linked_to(
        self, target_kind: str, target_id: str
    ) -> tuple[JournalEntry, ...]:
        """Every entry carrying a link to one subject, oldest first."""
        wanted_kind = require_text(target_kind, "target_kind")
        wanted_id = require_text(target_id, "target_id")
        return tuple(
            entry
            for entry in self.search()
            if any(
                link.target_kind == wanted_kind and link.target_id == wanted_id
                for link in entry.links
            )
        )

    def trade_journal(self, target_kind: str, target_id: str) -> TradeJournal:
        """The brief's *TradeJournal*: the read-time view over one subject's entries.

        A projection, built on every call and stored nowhere — which is what keeps
        it from becoming a second place an entry can live.
        """
        return TradeJournal.gather(
            require_text(target_kind, "target_kind"),
            require_text(target_id, "target_id"),
            self.search(),
        )

    def for_market(self, market_id: str) -> TradeJournal:
        """The journal view over one market, by the link kind the domain defines."""
        return self.trade_journal(
            "market", require_text(market_id, "market_id")
        )

    def live_entries(self) -> tuple[JournalEntry, ...]:
        """Entries nothing supersedes — what a surface shows by default."""
        return self.search(SearchCriteria(superseded=False))

    def link_kinds_used(self) -> tuple[LinkKind, ...]:
        """Which of the six typed links the owner actually uses."""
        used = {link.kind for entry in self.search() for link in entry.links}
        return tuple(kind for kind in LinkKind if kind in used)
