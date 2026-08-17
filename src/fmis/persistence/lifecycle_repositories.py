"""The execution half's storage: activations, their events, their stops, their ends.

One repository over four kinds, because they are one subject read four ways and a
caller that had to hold four repositories to answer *"what happened to this
trade"* would join them differently each time.

**A trade's state is never stored.** `ActivationRepository.state()` folds the
event stream every time it is asked, and `stop_history()` folds the amendment
stream over the plan's immutable invalidation. A stored state would be a second
answer to *"is this still open"*, and the fold is the only one that stays correct
when a superseding event arrives.

**An event about an activation nobody wrote is refused.** The domain can validate
the *shape* of the id an event names; only a store knows whether the activation
exists. An orphan event is a fold input that will never resolve, and it is cheaper
to refuse it at the write than to explain it three years later.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from fmis.provenance import Absent
from fmis.records import require_text, require_utc
from fmis.snapshotting import TradeDirection
from fmis.trade_lifecycle import (
    StopAmendment,
    StopHistory,
    TradeActivation,
    TradeLifecycleEvent,
    TradeLifecycleState,
    TradeLifecycleView,
    TradeOutcome,
    fold_stop_history,
    fold_trade_lifecycle,
)

from fmis.persistence.base import Repository
from fmis.persistence.criteria import SearchCriteria
from fmis.persistence.errors import (
    FrozenRecordError,
    PersistenceError,
    RecordConflictError,
    RecordMissingError,
)
from fmis.persistence.kinds import RecordKind
from fmis.persistence.store import WriteReceipt, WriteRequest

__all__ = ["ActivationRepository"]

#: The two kinds a later record of the same kind may supersede. The other two are
#: captured artifacts and have no supersession mechanism at all.
_SUPERSEDABLE = (RecordKind.TRADE_LIFECYCLE_EVENT, RecordKind.STOP_AMENDMENT)


class ActivationRepository(Repository):
    """`TradeActivation`, its lifecycle stream, its stop moves and its outcome."""

    kinds = (
        RecordKind.TRADE_ACTIVATION,
        RecordKind.TRADE_LIFECYCLE_EVENT,
        RecordKind.STOP_AMENDMENT,
        RecordKind.TRADE_OUTCOME,
    )

    # -- writing -------------------------------------------------------------

    def create(self, record: Any, *, request: WriteRequest) -> WriteReceipt:
        """Store an activation, or append something that happened to one."""
        if isinstance(record, (TradeLifecycleEvent, StopAmendment)):
            self._require_activation(record.activation_id)
            return self._store.publish(record, request=request.appending())
        if isinstance(record, TradeOutcome):
            self._require_activation(record.activation_id)
            existing = self.outcome_for(record.activation_id)
            if existing is not None and existing.outcome_id != record.outcome_id:
                raise RecordConflictError(
                    f"activation {record.activation_id} already has outcome "
                    f"{existing.outcome_id}. An outcome is frozen at the instant a "
                    "trade ended; a second one would be a different answer to how "
                    "it ended, and this store keeps one"
                )
            return self._store.publish(record, request=request)
        return super().create(record, request=request)

    def append_event(
        self, event: TradeLifecycleEvent, *, request: WriteRequest
    ) -> WriteReceipt:
        """Named alias for `create` on an event, because that is what it is."""
        if not isinstance(event, TradeLifecycleEvent):
            raise TypeError("event must be a TradeLifecycleEvent")
        return self.create(event, request=request)

    def append_amendment(
        self, amendment: StopAmendment, *, request: WriteRequest
    ) -> WriteReceipt:
        if not isinstance(amendment, StopAmendment):
            raise TypeError("amendment must be a StopAmendment")
        return self.create(amendment, request=request)

    def replace(
        self,
        record_id: str,
        superseding: Any = None,
        *,
        request: WriteRequest | None = None,
        **_: Any,
    ) -> WriteReceipt:
        """Supersede an event or an amendment. Activations and outcomes are frozen.

        An activation is a captured artifact: what was activated, at what size and
        through which ladder is frozen at the moment the owner activated it. A
        changed instruction is a **new** activation, and the old one records that
        it was superseded through its own lifecycle stream — so both stay readable
        and *"what did I originally intend"* keeps an answer.
        """
        target = require_text(record_id, "record_id")
        entry = self._store.index.get(target)
        if entry is None:
            raise RecordMissingError(f"no record {target!r} is in this store")
        if entry.kind not in _SUPERSEDABLE:
            raise FrozenRecordError(self._no_edit_path(target))
        if superseding is None or request is None:
            raise PersistenceError(
                "superseding an appended record needs the replacement and a "
                "WriteRequest saying who is superseding it and why"
            )
        expected = (
            TradeLifecycleEvent
            if entry.kind is RecordKind.TRADE_LIFECYCLE_EVENT
            else StopAmendment
        )
        if not isinstance(superseding, expected):
            raise TypeError(f"superseding must be a {expected.__name__}")
        if superseding.supersedes != target:
            raise PersistenceError(
                f"this record supersedes {superseding.supersedes!r}, not the "
                f"record {target!r} it was asked to replace"
            )
        self._require_activation(superseding.activation_id)
        return self._store.publish(superseding, request=request.superseding())

    # -- reading -------------------------------------------------------------

    def activations(
        self, criteria: SearchCriteria | None = None
    ) -> tuple[TradeActivation, ...]:
        return tuple(
            self._store.load(entry.record_id)
            for entry in self.entries(
                kind=RecordKind.TRADE_ACTIVATION, criteria=criteria
            )
        )

    def activations_for_plan(self, plan_id: str) -> tuple[TradeActivation, ...]:
        """Every activation of one commitment, oldest first.

        Including the ones that were cancelled or superseded: *"I activated this
        twice and cancelled the first"* is a behaviour, and a listing that hid it
        would make the second attempt look like the only one.
        """
        return self.activations(
            SearchCriteria(lineage_key=require_text(plan_id, "plan_id"))
        )

    def events_for(self, activation_id: str) -> tuple[TradeLifecycleEvent, ...]:
        """Every stored event naming one activation, in the order the fold wants."""
        wanted = require_text(activation_id, "activation_id")
        events = [
            self._store.load(entry.record_id)
            for entry in self.entries(
                kind=RecordKind.TRADE_LIFECYCLE_EVENT,
                criteria=SearchCriteria(lineage_key=wanted),
            )
        ]
        events.sort(key=lambda event: (event.sort_key, event.event_id))
        return tuple(events)

    def live_events_for(self, activation_id: str) -> tuple[TradeLifecycleEvent, ...]:
        """The same stream with superseded events dropped — what the fold reads."""
        superseded = set(self._store.successors())
        return tuple(
            event
            for event in self.events_for(activation_id)
            if event.event_id not in superseded
        )

    def state(self, activation_id: str) -> TradeLifecycleView:
        """Fold the live event stream. Computed on every call, stored never."""
        wanted = require_text(activation_id, "activation_id")
        self._require_activation(wanted)
        return fold_trade_lifecycle(wanted, self.live_events_for(wanted))

    def state_as_known_at(
        self, activation_id: str, moment: datetime
    ) -> TradeLifecycleView:
        """The state this store would have reported at a past instant."""
        when = require_utc(moment, "moment")
        wanted = require_text(activation_id, "activation_id")
        self._require_activation(wanted)
        superseded = set(self._store.successors())
        events = [
            self._store.load(entry.record_id)
            for entry in self.entries(
                kind=RecordKind.TRADE_LIFECYCLE_EVENT,
                criteria=SearchCriteria(lineage_key=wanted, known_until=when),
            )
            if entry.record_id not in superseded
        ]
        events.sort(key=lambda event: (event.sort_key, event.event_id))
        return fold_trade_lifecycle(wanted, tuple(events))

    def amendments_for(self, activation_id: str) -> tuple[StopAmendment, ...]:
        wanted = require_text(activation_id, "activation_id")
        amendments = [
            self._store.load(entry.record_id)
            for entry in self.entries(
                kind=RecordKind.STOP_AMENDMENT,
                criteria=SearchCriteria(lineage_key=wanted),
            )
        ]
        amendments.sort(
            key=lambda amendment: (amendment.ordering_key, amendment.amendment_id)
        )
        return tuple(amendments)

    def live_amendments_for(self, activation_id: str) -> tuple[StopAmendment, ...]:
        superseded = set(self._store.successors())
        return tuple(
            amendment
            for amendment in self.amendments_for(activation_id)
            if amendment.amendment_id not in superseded
        )

    def stop_history(
        self,
        activation_id: str,
        *,
        initial_stop: Decimal,
        direction: TradeDirection,
        at: datetime | None = None,
    ) -> StopHistory:
        """Fold this run's stop moves over the plan's immutable invalidation.

        `initial_stop` and `direction` are arguments rather than lookups because
        they belong to the `TradePlan`, which `PlanRepository` owns. A repository
        that reached across to read another kind's record to answer its own
        question is how one fact acquires two readers.
        """
        wanted = require_text(activation_id, "activation_id")
        return fold_stop_history(
            initial_stop=initial_stop,
            direction=direction,
            amendments=self.live_amendments_for(wanted),
            at=at,
        )

    def outcome_for(self, activation_id: str) -> TradeOutcome | None:
        """The frozen outcome of one trade, or `None` while it has not finished.

        `None` rather than a raise: a trade that has not ended yet is the ordinary
        state of every open position, not an error.
        """
        rows = self.entries(
            kind=RecordKind.TRADE_OUTCOME,
            criteria=SearchCriteria(
                lineage_key=require_text(activation_id, "activation_id")
            ),
        )
        return None if not rows else self._store.load(rows[-1].record_id)

    def outcomes(
        self, criteria: SearchCriteria | None = None
    ) -> tuple[TradeOutcome, ...]:
        return tuple(
            self._store.load(entry.record_id)
            for entry in self.entries(
                kind=RecordKind.TRADE_OUTCOME, criteria=criteria
            )
        )

    def live_activations(
        self, criteria: SearchCriteria | None = None
    ) -> tuple[tuple[TradeActivation, TradeLifecycleView], ...]:
        """Every activation a simulation run still has work to do on, with its state.

        **`AMBIGUOUS` is not live.** A halted trade is not waiting for the next
        bar; it is waiting for the owner, and including it here would make every
        run re-read a candle it has already refused to interpret.
        """
        return tuple(
            (activation, view)
            for activation, view in self.states(criteria)
            if view.is_live
        )

    def halted_activations(
        self, criteria: SearchCriteria | None = None
    ) -> tuple[tuple[TradeActivation, TradeLifecycleView], ...]:
        """Every activation the engine stopped on rather than finished."""
        return tuple(
            (activation, view)
            for activation, view in self.states(criteria)
            if view.is_halted
        )

    def states(
        self, criteria: SearchCriteria | None = None
    ) -> tuple[tuple[TradeActivation, TradeLifecycleView], ...]:
        """Every activation with its folded state, in index order."""
        return tuple(
            (activation, self.state(activation.activation_id))
            for activation in self.activations(criteria)
        )

    def finished(
        self, criteria: SearchCriteria | None = None
    ) -> tuple[tuple[TradeActivation, TradeLifecycleView], ...]:
        """Every activation whose stream has reached a terminal state."""
        return tuple(
            (activation, view)
            for activation, view in self.states(criteria)
            if view.state is TradeLifecycleState.RESOLVED
        )

    # -- internals -----------------------------------------------------------

    def _require_activation(self, activation_id: str | Absent) -> str:
        wanted = require_text(activation_id, "activation_id")
        entry = self._store.index.get(wanted)
        if entry is None or entry.kind is not RecordKind.TRADE_ACTIVATION:
            raise RecordMissingError(
                f"this record names activation {wanted!r}, which is not in this "
                "store. Something that happened to an activation nobody wrote can "
                "never be folded into a state"
            )
        return wanted
