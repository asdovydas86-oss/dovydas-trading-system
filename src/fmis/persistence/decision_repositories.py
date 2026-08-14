"""The decision chain's storage: proposals, plans, their events, snapshots, citations.

Four repositories, and all four hold captured artifacts — records frozen at a
named moment with their inputs, which the store refuses to edit under any verb. The
one exception inside them is `ProposalLifecycleEvent`, which is a source of truth:
events are appended and a wrong one is superseded by a later one carrying
`supersedes`, using the identical mechanism the ledger uses for a `Correction`
rather than a second one.

**A proposal's state is never stored.** `OpportunityRepository.state()` folds the
event stream every time it is asked. A stored state would be a second answer to
*"was this accepted"*, and the fold is the only one that stays correct when a
superseding event arrives.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fmis.plan import TradePlan
from fmis.proposal import (
    OpportunityProposal,
    ProposalAdmission,
    ProposalLifecycleEvent,
    ProposalState,
    ProposalStateView,
    admit,
    fold_proposal_state,
)
from fmis.provenance import Absent
from fmis.records import require_member, require_text, require_utc
from fmis.snapshotting import DecisionWindow, MarketSnapshot

from fmis.persistence.base import Repository
from fmis.persistence.criteria import SearchCriteria
from fmis.persistence.errors import (
    FrozenRecordError,
    PersistenceError,
    RecordMissingError,
)
from fmis.persistence.kinds import RecordKind
from fmis.persistence.store import WriteReceipt, WriteRequest

__all__ = [
    "OpportunityRepository",
    "PlanRepository",
    "SnapshotRepository",
    "AnalysisRecordRepository",
]


class OpportunityRepository(Repository):
    """`OpportunityProposal` and its append-only lifecycle stream."""

    kinds = (RecordKind.PROPOSAL, RecordKind.LIFECYCLE_EVENT)

    # -- writing -------------------------------------------------------------

    def create(self, record: Any, *, request: WriteRequest) -> WriteReceipt:
        """Store a proposal, or append a lifecycle event to one already stored.

        An event whose `proposal_id` is not in the store is refused. The domain
        cannot check that — a `ProposalLifecycleEvent` validates the *shape* of the
        id it names, and only a store knows whether the proposal exists. An event
        about a proposal nobody wrote is a fold input that will never resolve.
        """
        if isinstance(record, ProposalLifecycleEvent):
            if not self._store.exists(record.proposal_id):
                raise RecordMissingError(
                    f"lifecycle event names proposal {record.proposal_id!r}, which "
                    "is not in this store. An event whose subject does not exist "
                    "can never be folded into a state"
                )
            return self._store.publish(record, request=request.appending())
        return super().create(record, request=request)

    def append_event(
        self, event: ProposalLifecycleEvent, *, request: WriteRequest
    ) -> WriteReceipt:
        """Named alias for `create` on an event, because that is what it is."""
        if not isinstance(event, ProposalLifecycleEvent):
            raise TypeError("event must be a ProposalLifecycleEvent")
        return self.create(event, request=request)

    def replace(
        self,
        record_id: str,
        superseding: ProposalLifecycleEvent | None = None,
        *,
        request: WriteRequest | None = None,
        **_: Any,
    ) -> WriteReceipt:
        """Supersede a lifecycle event with a later one. Proposals are frozen.

        A proposal is a captured artifact: what it said, its evidence, its opposing
        case and the confidence its author stated are frozen at generation. Nothing
        supersedes it — a changed view of the same market is a *new* proposal, and
        creation rule 4 decides whether that is even allowed.
        """
        target = require_text(record_id, "record_id")
        entry = self._store.index.get(target)
        if entry is None:
            raise RecordMissingError(f"no record {target!r} is in this store")
        if entry.kind is RecordKind.PROPOSAL:
            raise FrozenRecordError(self._no_edit_path(target))
        if superseding is None or request is None:
            raise PersistenceError(
                "superseding a lifecycle event needs the replacement event and a "
                "WriteRequest saying who is superseding it and why"
            )
        if not isinstance(superseding, ProposalLifecycleEvent):
            raise TypeError("superseding must be a ProposalLifecycleEvent")
        if superseding.supersedes != target:
            raise PersistenceError(
                f"this event supersedes {superseding.supersedes!r}, not the event "
                f"{target!r} it was asked to replace"
            )
        return self._store.publish(superseding, request=request.superseding())

    # -- reading -------------------------------------------------------------

    def proposals(
        self, criteria: SearchCriteria | None = None
    ) -> tuple[OpportunityProposal, ...]:
        return tuple(
            self._store.load(entry.record_id)
            for entry in self.entries(kind=RecordKind.PROPOSAL, criteria=criteria)
        )

    def events_for(self, proposal_id: str) -> tuple[ProposalLifecycleEvent, ...]:
        """Every stored event naming one proposal, in the order the fold wants.

        Ordered by `ordering_key` — the causing candle's close for a measured event,
        the moment it occurred for an assertion — because that is the order the
        domain folds in. Ordering by when a scan happened to run would recreate
        ADR-0021's intrabar problem one layer up.
        """
        wanted = require_text(proposal_id, "proposal_id")
        events = [
            self._store.load(entry.record_id)
            for entry in self.entries(kind=RecordKind.LIFECYCLE_EVENT)
            if entry.lineage_key == wanted
        ]
        events.sort(key=lambda event: (event.ordering_key, event.event_id))
        return tuple(events)

    def live_events_for(self, proposal_id: str) -> tuple[ProposalLifecycleEvent, ...]:
        """The same stream with superseded events dropped — what the fold reads."""
        superseded = set(self._store.successors())
        return tuple(
            event
            for event in self.events_for(proposal_id)
            if event.event_id not in superseded
        )

    def state(self, proposal_id: str) -> ProposalStateView:
        """Fold the live event stream. Computed on every call, stored never."""
        proposal = self._store.load(require_text(proposal_id, "proposal_id"))
        if not isinstance(proposal, OpportunityProposal):
            raise PersistenceError(f"{proposal_id!r} is not a proposal")
        return fold_proposal_state(proposal, self.live_events_for(proposal_id))

    def state_as_known_at(
        self, proposal_id: str, moment: datetime
    ) -> ProposalStateView:
        """The state the store would have reported at a past instant."""
        when = require_utc(moment, "moment")
        wanted = require_text(proposal_id, "proposal_id")
        proposal = self._store.load(wanted)
        superseded = set(self._store.successors())
        events = [
            self._store.load(entry.record_id)
            for entry in self.entries(
                kind=RecordKind.LIFECYCLE_EVENT, criteria=SearchCriteria(known_until=when)
            )
            if entry.lineage_key == wanted and entry.record_id not in superseded
        ]
        events.sort(key=lambda event: (event.ordering_key, event.event_id))
        return fold_proposal_state(proposal, tuple(events))

    def live_proposals(
        self, criteria: SearchCriteria | None = None
    ) -> tuple[tuple[OpportunityProposal, ProposalStateView], ...]:
        """Every proposal whose folded state is not terminal, with that state."""
        found = []
        for proposal in self.proposals(criteria):
            view = self.state(proposal.proposal_id)
            if view.state is ProposalState.LIVE:
                found.append((proposal, view))
        return tuple(found)

    def admit(
        self,
        candidate: OpportunityProposal,
        *,
        request: WriteRequest,
        occurred_at: datetime,
        recorded_at: datetime,
        causing_close_time: datetime,
        note: str | Absent = Absent("no note"),
    ) -> ProposalAdmission:
        """Creation rule 4, applied against what this store actually holds.

        A second proposal may not be created while a live one shares its anchor; a
        re-run that would produce a duplicate appends a `REAFFIRMED` event to the
        existing proposal instead. **This rule is what stops one idea becoming
        forty proposals**, and it only works against the real live set — which is
        why it lives here rather than being left to each caller to remember.

        Whichever the domain decides, the result is published before it is returned:
        an admission that was computed and not stored is a deduplication that did
        not happen.
        """
        admission = admit(
            candidate,
            self.live_proposals(),
            occurred_at=occurred_at,
            recorded_at=recorded_at,
            causing_close_time=causing_close_time,
            note=note,
        )
        if isinstance(admission.reaffirmation, ProposalLifecycleEvent):
            self.create(admission.reaffirmation, request=request)
        else:
            self.create(admission.proposal, request=request)
        return admission


class PlanRepository(Repository):
    """`TradePlan` — what the owner committed to, frozen at the moment of commitment.

    A captured artifact with no edit path, and the refusal is the point rather than
    a side effect of the classification: *"did I honour my stop?"* is answerable
    only if the stop cannot be changed after the trade moved. `update` and
    `replace` both raise, inherited from the base, and the amendment stream that
    would legitimately move the *other* fields (§10.4) is not built.

    **This repository does not know what filled a plan.** `Trade.plan_id` points
    from the fill to the commitment, never the reverse, so a plan does not change
    when a fill is recorded against it. Assembling the two is
    `fmis.trade_capture`'s work, and keeping it out of here is what stops a
    "plan" from quietly becoming a position.
    """

    kinds = (RecordKind.TRADE_PLAN,)

    def plans(self, criteria: SearchCriteria | None = None) -> tuple[TradePlan, ...]:
        """Every stored commitment, ordered by when it was committed to."""
        return self.search(criteria)

    def for_market(self, market: str) -> tuple[TradePlan, ...]:
        """Every commitment in one market, oldest first."""
        return self.search(
            SearchCriteria(market=require_text(market, "market"))
        )

    def latest_for_market(self, market: str) -> TradePlan | None:
        """The most recent commitment in one market, or `None` if there is none.

        `None` rather than a raise: having never planned a trade in a market is an
        ordinary state, not an error.
        """
        rows = self.entries(
            criteria=SearchCriteria(market=require_text(market, "market"))
        )
        return None if not rows else self._store.load(rows[-1].record_id)

    def plan_ids(self) -> tuple[str, ...]:
        """Every stored plan id, in the same deterministic order `entries` uses."""
        return tuple(entry.record_id for entry in self.entries())

    def live_at(self, moment: datetime) -> tuple[TradePlan, ...]:
        """Commitments already made and not yet expired at an instant.

        A **filter over two stored instants**, not a state: whether a plan was ever
        filled is the ledger's answer and this repository does not hold it. A plan
        that expired unfilled and a plan that expired mid-position are both absent
        from this result, and neither absence means the same thing.
        """
        when = require_utc(moment, "moment")
        return tuple(
            plan
            for plan in self.search(SearchCriteria(until=when))
            if not plan.is_expired_at(when)
        )


class SnapshotRepository(Repository):
    """`MarketSnapshot` and `DecisionWindow` — the frozen market facts.

    Both are captured artifacts and neither has an edit path. A snapshot of the
    same market a minute later is a *different* snapshot with a different id, not a
    new version of this one, because what it froze was different.
    """

    kinds = (RecordKind.MARKET_SNAPSHOT, RecordKind.DECISION_WINDOW)

    def snapshots(
        self, criteria: SearchCriteria | None = None
    ) -> tuple[MarketSnapshot, ...]:
        return tuple(
            self._store.load(entry.record_id)
            for entry in self.entries(
                kind=RecordKind.MARKET_SNAPSHOT, criteria=criteria
            )
        )

    def windows(
        self, criteria: SearchCriteria | None = None
    ) -> tuple[DecisionWindow, ...]:
        return tuple(
            self._store.load(entry.record_id)
            for entry in self.entries(
                kind=RecordKind.DECISION_WINDOW, criteria=criteria
            )
        )

    def for_market(
        self, market: str, *, kind: RecordKind | None = None
    ) -> tuple[Any, ...]:
        """Every frozen artifact about one market, oldest first."""
        wanted = require_text(market, "market")
        if kind is not None:
            require_member(kind, RecordKind, "kind")
        return tuple(
            self._store.load(entry.record_id)
            for entry in self.entries(
                kind=kind, criteria=SearchCriteria(market=wanted)
            )
        )

    def latest_for_market(self, market: str) -> MarketSnapshot | None:
        """The most recently *built* snapshot of one market, or `None`.

        `None` rather than a raise: "there is no snapshot yet" is an ordinary state
        on the first day of a market, not an error.
        """
        rows = self.entries(
            kind=RecordKind.MARKET_SNAPSHOT,
            criteria=SearchCriteria(market=require_text(market, "market")),
        )
        return None if not rows else self._store.load(rows[-1].record_id)

    def window_of(self, snapshot: MarketSnapshot) -> DecisionWindow | None:
        """The window a snapshot cites, if it cited one and this store holds it."""
        if not isinstance(snapshot, MarketSnapshot):
            raise TypeError("snapshot must be a MarketSnapshot")
        if isinstance(snapshot.decision_window_id, Absent):
            return None
        entry = self._store.index.get(snapshot.decision_window_id)
        return None if entry is None else self._store.load(entry.record_id)


class AnalysisRecordRepository(Repository):
    """Citations of archived analysis pages, by id and digest.

    The page itself stays owned by `fmis.archive`, unmodified and unduplicated.
    What is stored here is the **edge** — which analysis a proposal, a snapshot or a
    journal entry actually read — because today the only bridge is the owner copying
    a record id into notes outside the system.

    The digest is what makes the edge more than a foreign key: an id says *which*
    page was read, and the digest says whether it still says what it said.
    """

    kinds = (RecordKind.ANALYSIS_RECORD,)

    def for_subject(self, subject: str) -> tuple[Any, ...]:
        """Every citation whose first subject component matches, oldest first."""
        return self.search(
            SearchCriteria(lineage_key=require_text(subject, "subject"))
        )

    def is_current(self, record_id: str, *, content_digest: str) -> bool:
        """Whether a citation still describes the page it points at.

        The caller supplies the archive's *current* digest for that page; this
        compares it against what the citation froze. A mismatch is not repaired and
        the citation is not rewritten — staleness is derived and rendered, which is
        the whole of the adopted answer to what a correction owes a frozen artifact.
        """
        citation = self.load(record_id)
        return citation.content_digest == require_text(
            content_digest, "content_digest"
        )
