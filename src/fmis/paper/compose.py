"""The write path: activate, amend, cancel, simulate. The composition root.

**Nothing here reaches disk except through `TradingStore`.** Every write is a
repository call, so the store's hash-chained write journal stays a *complete*
account of what happened, and a guard asserts this module names no path, no file
and no atomic write.

**Everything is validated before anything is published.** A run builds every
record it intends to write, and only then does the first byte move. A simulation
that had written three fills and then refused the fourth would leave the owner
with a position the engine never decided to take.

**Re-running writes nothing.** Every id in this domain is a digest of the
record's own content, and every value the engine derives is a function of the
bars alone — a fill's price and instant, an event's note and bar sequence, an
amendment's before and after. So `fmits simulate` replays each activation from
the beginning every time, and the second run publishes nothing. That is what
makes resume trivial: there is no partially-rebuilt state to get wrong, and a
test asserts the store's bytes are unchanged by a second identical run.

**Every lifecycle transition writes a journal entry.** No silent state change —
the milestone brief's §11, taken literally. They are `NOTE` entries authored by
the simulator and never `IDEA`: an idea is the owner's, and a simulator that
could author one would pollute the discipline metric that counts whether the
owner wrote anything at all.

**A simulated fill is a real ledger `Trade` under `Book.PAPER`.** `AP` §5.5
already says what the book means, so the position fold, the exposure engine, the
constraint engine, the valuation and `fmits today` all work on a paper trade with
no new code. That is the milestone brief's *"reuse the existing architecture"*
satisfied by construction rather than by a parallel implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from fmis.accounts import AccountId, Book
from fmis.journal import (
    JournalEntry,
    JournalKind,
    JournalLink,
    JournalTag,
    LinkKind,
    TagOrigin,
)
from fmis.ledger import LedgerSource, Trade
from fmis.money import DustPolicy, Money, Quantity, canonical_decimal_text
from fmis.persistence import (
    TradingStore,
    WriteRequest,
    WriteSource,
    spec_for_record,
)
from fmis.plan import TradePlan
from fmis.positions import POSITION_CALCULATION_VERSION
from fmis.proposal import (
    IllegalTransitionError as ProposalIllegalTransitionError,
    LifecycleKind as ProposalLifecycleKind,
    ProposalLifecycleEvent,
    ProposalState,
    fold_proposal_state,
)
from fmis.provenance import Absent, ValueOrigin, VersionedTerm
from fmis.records import (
    DomainValidationError,
    RecordAudit,
    require_text,
    require_utc,
)
from fmis.snapshotting import TradeDirection
from fmis.trade_capture import entry_side, exit_side
from fmis.trade_lifecycle import (
    STOP_AMENDMENT_REASON_VOCABULARY,
    STOP_POLICY_VOCABULARY,
    EntryType,
    ExitLadder,
    ExitLeg,
    ExitReason,
    StopAmendment,
    StopManagement,
    TradeActivation,
    TradeLifecycleEvent,
    TradeLifecycleKind,
    TradeLifecycleState,
    TradeOutcome,
    fold_stop_history,
    fold_trade_lifecycle,
)
from fmis.versioning import VersionAxis, VersionSet
from fmis.paper.bars import bars_from_series
from fmis.paper.models import (
    PAPER_AUTHOR_LABEL,
    PAPER_FILL_POLICY_ID,
    PAPER_FILL_POLICY_VERSION,
    PAPER_ZERO_COST_POLICY,
    Fill,
    FillTrigger,
    PaperRefusedError,
    PriceBar,
)
from fmis.paper.replay import ReplayResult, replay_bars
from fmis.paper.views import (
    ACTIVATION_SUBJECT_KIND,
    PLAN_SUBJECT_KIND,
    TRADE_SUBJECT_KIND,
    owner_stop_moves,
    run_state_for,
)

__all__ = [
    "PAPER_DUST_POLICY",
    "PAPER_TAXONOMY_VERSION",
    "PAPER_FX_RATE",
    "PAPER_FX_SOURCE",
    "PAPER_AUTHOR",
    "LIFECYCLE_TAG_VOCABULARY",
    "ACTIVATE_REASON",
    "AMEND_REASON",
    "SIMULATE_REASON",
    "ActivateRequest",
    "AmendStopRequest",
    "CancelRequest",
    "ActivationOutcome",
    "TradeRunReport",
    "SimulationReport",
    "bars_for_run",
    "activate_trade",
    "amend_stop",
    "cancel_activation",
    "simulate_activation",
    "run_simulation",
]

#: Exact zero, with no configured threshold — the identical choice
#: `fmis.trade_capture` and `fmis.today` both make, for the identical reason: zero
#: is the only tolerance that is not a policy decision, and a simulator that chose
#: a different one would draw the boundary between two round trips somewhere the
#: page that reports them does not.
PAPER_DUST_POLICY = DustPolicy(policy_id="fmits-paper-exact-zero", version=1)

#: The generation every vocabulary term this package mints is stamped with.
PAPER_TAXONOMY_VERSION = 1

#: The placeholder rate a simulated fill carries.
#:
#: `Trade` requires an FX rate to the tax currency because it is unrecoverable
#: later, and a paper fill has **no tax consequence at all**: `Book.PAPER` is in
#: `DEFAULT_EXCLUDED_BOOKS` and no tax engine exists yet. So the rate is `1` and
#: the *source* says in words that it is a placeholder, which is the only version
#: of this that a future tax engine cannot mistake for a real rate. When that
#: engine arrives it must exclude `Book.PAPER`, and this constant is where a
#: reader finds out why.
PAPER_FX_RATE = Decimal(1)
PAPER_FX_SOURCE = "fmits-paper-simulation: no tax event, placeholder rate"

#: Who a simulated record is asserted by. Defined in `models` so the read path
#: can tell an engine-authored note from the owner's without importing this one.
PAPER_AUTHOR = PAPER_AUTHOR_LABEL

#: This code path's own tag vocabulary — the same footing
#: `fmis.trade_capture.WRITE_REASON_VOCABULARY` holds. Naming the transitions
#: this package records is not this layer choosing a trading policy.
LIFECYCLE_TAG_VOCABULARY = "lifecycle_event"

_WRITE_REASON_VOCABULARY = "write_reason"


def _write_reason(term_id: str) -> VersionedTerm:
    return VersionedTerm(
        vocabulary_id=_WRITE_REASON_VOCABULARY,
        term_id=term_id,
        taxonomy_version=PAPER_TAXONOMY_VERSION,
    )


ACTIVATE_REASON = _write_reason("paper_trade_activation")
AMEND_REASON = _write_reason("paper_stop_amendment")
SIMULATE_REASON = _write_reason("paper_simulation_step")

#: Which frozen ending each terminal state produces. A table rather than a chain
#: of conditionals, so a state added later fails here loudly instead of silently
#: producing whichever branch happened to come last.
_TERMINAL_REASONS: dict[TradeLifecycleState, ExitReason] = {
    TradeLifecycleState.EXPIRED: ExitReason.EXPIRED,
    TradeLifecycleState.CANCELLED: ExitReason.CANCELLED,
    TradeLifecycleState.SUPERSEDED: ExitReason.SUPERSEDED,
}

_EXIT_TRIGGER_REASONS: dict[FillTrigger, ExitReason] = {
    FillTrigger.TARGET_LEVEL: ExitReason.TARGET_HIT,
    FillTrigger.STOP_LEVEL: ExitReason.STOP_HIT,
}


def _require_store(store: Any) -> TradingStore:
    if not isinstance(store, TradingStore):
        raise TypeError(f"store must be a TradingStore, got {type(store).__name__}")
    return store


def paper_version_set(*, code_version: str) -> VersionSet:
    """The version axes a simulated record is stamped with.

    Five known and five `Absent` with a reason, which is `VersionSet`'s own
    contract: *"a reader can always tell 'we did not record it' from 'it did not
    apply'."* A simulated fill **is** policy-derived, so `POLICY_VERSION` names
    the fill policy — unlike a manually captured trade, where stamping one would
    make an assertion indistinguishable from a generated proposal.
    """
    return VersionSet.of(
        {
            VersionAxis.CODE_VERSION: require_text(code_version, "code_version"),
            VersionAxis.CAPTURE_SCHEMA_VERSION: str(PAPER_FILL_POLICY_VERSION),
            VersionAxis.CALCULATION_VERSION: POSITION_CALCULATION_VERSION,
            VersionAxis.TAXONOMY_VERSION: str(PAPER_TAXONOMY_VERSION),
            VersionAxis.POLICY_VERSION: PAPER_AUTHOR,
        },
        absent_reason=(
            "no classifier, model or counterfactual assumption produced this "
            "record; a deterministic fill policy did"
        ),
    )


def _write(
    *,
    written_at: datetime,
    author: str,
    reason: VersionedTerm,
    versions: VersionSet,
    source: WriteSource = WriteSource.POLICY_ENGINE,
) -> WriteRequest:
    """The store's own audit line for one write.

    `POLICY_ENGINE` by default and `OWNER` where the owner acted, because the
    write journal is the only place *"the simulator did this"* and *"I did this"*
    are distinguishable after the fact — and a stop the owner moved and a stop a
    trailing rule moved are the two records the discipline metric is built on.
    """
    return WriteRequest(
        written_at=written_at,
        source=source,
        author=author,
        reason=reason,
        version_set=versions,
    )


def _require_legal(
    store: TradingStore, activation_id: str, event: TradeLifecycleEvent
) -> None:
    """Fold the stream **with** this event before a byte of it is written.

    The lifecycle table decides what may follow what, and this is where a write
    path asks it. Without the question, a cancellation of an open position would
    reach disk and only fail the next time somebody read the trade — leaving a
    store whose own fold refuses to resolve, which is the one failure an
    append-only design cannot undo.
    """
    fold_trade_lifecycle(
        activation_id,
        store.activations.live_events_for(activation_id) + (event,),
    )


def _activation_link(activation_id: str) -> JournalLink:
    return JournalLink(LinkKind.ABOUT, ACTIVATION_SUBJECT_KIND, activation_id)


def _plan_link(plan_id: str) -> JournalLink:
    return JournalLink(LinkKind.ABOUT, PLAN_SUBJECT_KIND, plan_id)


def _trade_link(event_id: str) -> JournalLink:
    return JournalLink(LinkKind.CAUSED_BY, TRADE_SUBJECT_KIND, event_id)


def _lifecycle_tag(kind: TradeLifecycleKind, at: datetime) -> JournalTag:
    return JournalTag(
        term=VersionedTerm(
            vocabulary_id=LIFECYCLE_TAG_VOCABULARY,
            term_id=kind.value,
            taxonomy_version=PAPER_TAXONOMY_VERSION,
        ),
        origin=TagOrigin.IMPORTED,
        applied_at=at,
    )


# --------------------------------------------------------------------------
# Activating a commitment.
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ActivateRequest:
    """Everything `fmits trade activate` needs, validated as one object."""

    plan_id: str
    account: AccountId
    quantity: Quantity
    entry_type: EntryType
    interval: str
    activated_at: datetime
    written_at: datetime
    code_version: str
    entry_price: Decimal | Absent = field(
        default_factory=lambda: Absent("a market entry names no level")
    )
    fractions: tuple[Decimal, ...] = ()
    stop_management: StopManagement = field(default_factory=StopManagement)
    expires_at: datetime | Absent = field(
        default_factory=lambda: Absent("this activation does not expire")
    )
    note: str | Absent = field(default_factory=lambda: Absent("no note"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", require_text(self.plan_id, "plan_id"))
        if not isinstance(self.account, AccountId):
            raise TypeError("account must be an AccountId")
        if not isinstance(self.quantity, Quantity):
            raise TypeError("quantity must be a Quantity")
        object.__setattr__(
            self, "activated_at", require_utc(self.activated_at, "activated_at")
        )
        object.__setattr__(
            self, "written_at", require_utc(self.written_at, "written_at")
        )
        if self.written_at < self.activated_at:
            raise PaperRefusedError(
                f"this activation is being filed at {self.written_at.isoformat()}, "
                f"before the {self.activated_at.isoformat()} it says it was "
                "activated. FMITS cannot learn of something before it happens"
            )
        object.__setattr__(
            self, "code_version", require_text(self.code_version, "code_version")
        )
        object.__setattr__(self, "interval", require_text(self.interval, "interval"))

    def ladder_for(self, plan: TradePlan) -> ExitLadder:
        """The exit ladder, from the plan's targets and the owner's shares.

        **When the owner states no share, the whole position exits at the first
        target** — and the record says so explicitly rather than the code applying
        a default silently. A plan with no target produces an empty ladder, which
        means the position runs to the stop, which is also a real answer.
        """
        if not plan.targets:
            return ExitLadder()
        shares = self.fractions or (Decimal(1),)
        if len(shares) > len(plan.targets):
            raise PaperRefusedError(
                f"{len(shares)} share(s) were stated for a plan naming "
                f"{len(plan.targets)} target(s); a share with no target has "
                "nothing to exit at"
            )
        return ExitLadder(
            legs=tuple(
                ExitLeg(target=plan.targets[index], fraction=share)
                for index, share in enumerate(shares)
            )
        )

    def build(self, plan: TradePlan) -> TradeActivation:
        return TradeActivation(
            activated_at=self.activated_at,
            plan_id=plan.plan_id,
            market=plan.market,
            book=Book.PAPER,
            account=self.account,
            direction=plan.direction,
            entry_type=self.entry_type,
            quantity=self.quantity,
            ladder=self.ladder_for(plan),
            stop_management=self.stop_management,
            cost_policy=PAPER_ZERO_COST_POLICY,
            fill_policy_id=PAPER_FILL_POLICY_ID,
            fill_policy_version=PAPER_FILL_POLICY_VERSION,
            interval=self.interval,
            version_set=paper_version_set(code_version=self.code_version),
            audit=RecordAudit.frozen_at(self.activated_at),
            entry_price=self.entry_price,
            expires_at=self.expires_at,
            proposal_id=plan.proposal_id,
            note=self.note,
        )


@dataclass(frozen=True, slots=True)
class ActivationOutcome:
    """What one write path produced: the records, and whether they were new."""

    action: str
    activation: TradeActivation
    written: tuple[tuple[str, str, bool], ...] = ()

    @property
    def created_any(self) -> bool:
        return any(created for _, _, created in self.written)


def _written(kind: str, receipt: Any) -> tuple[str, str, bool]:
    return (kind, receipt.record_id, receipt.created)


def _publish_once(
    store: TradingStore,
    repository: Any,
    record: Any,
    *,
    kind: str,
    request: WriteRequest,
) -> tuple[str, str, bool]:
    """Write a record, or report the one already there and write nothing.

    **This is what makes replaying from the beginning free.** Every id in this
    domain is a digest of the record's *economic* content, and `recorded_at` is
    excluded from it on purpose — a crashed run restarted an hour later must not
    produce a second event. But the stored *payload* keeps `recorded_at`, because
    when FMITS learned of something is a real fact, so re-publishing an event the
    store already holds would be a byte-level conflict rather than a no-op.

    Asking first resolves both: the second run writes nothing, and the first
    run's `recorded_at` stands — which is correct, because that is when this
    system actually learned of it.
    """
    identity = spec_for_record(record).identity(record)
    if store.store.exists(identity):
        return (kind, identity, False)
    return _written(kind, repository.create(record, request=request))


def activate_trade(store: TradingStore, request: ActivateRequest) -> ActivationOutcome:
    """Hand one recorded commitment to the simulator.

    Writes one `TradeActivation` and one journal entry. **No lifecycle event**:
    an activation's stream begins at `PENDING`, which is the fold's starting state
    and not something an event has to assert — the identical choice
    `fmis.proposal` makes for `LIVE`.

    Re-running the identical command is an idempotent success, not a second
    instruction.
    """
    _require_store(store)
    if not isinstance(request, ActivateRequest):
        raise TypeError("request must be an ActivateRequest")
    plan = store.plans.load(request.plan_id)
    if not isinstance(plan, TradePlan):  # pragma: no cover - PlanRepository owns
        # one kind and refuses any other id before this line is reached. Kept as
        # the message a caller would need if a second kind is ever added to it.
        raise PaperRefusedError(
            f"{request.plan_id!r} is not a recorded commitment; `fmits trade "
            "activate` takes the plan id `fmits trade list` prints"
        )
    activation = request.build(plan)
    versions = paper_version_set(code_version=request.code_version)
    write = _write(
        written_at=request.written_at,
        author=PAPER_AUTHOR,
        reason=ACTIVATE_REASON,
        versions=versions,
        source=WriteSource.OWNER,
    )
    written = [
        _publish_once(
            store, store.activations, activation, kind="trade_activation", request=write
        )
    ]
    entry = JournalEntry(
        kind=JournalKind.NOTE,
        recorded_at=request.activated_at,
        author=PAPER_AUTHOR,
        audit=RecordAudit.frozen_at(request.activated_at),
        title=(
            f"activated: {plan.market.pair_symbol} "
            f"{activation.entry_type.value} on {activation.interval}"
        ),
        body=(
            f"{activation.quantity} activated for paper simulation against plan "
            f"{plan.plan_id}. Stop {canonical_decimal_text(plan.initial_invalidation)}; "
            f"{len(activation.ladder.legs)} ladder rung(s). "
            f"{activation.cost_policy.basis}"
        ),
        links=(_activation_link(activation.activation_id), _plan_link(plan.plan_id)),
    )
    written.append(
        _publish_once(
            store, store.journals, entry, kind="journal_entry", request=write
        )
    )
    return ActivationOutcome(
        action="activated", activation=activation, written=tuple(written)
    )


# --------------------------------------------------------------------------
# Moving a stop by hand, and cancelling.
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AmendStopRequest:
    """One owner-stated stop move. Append-only; the plan is never touched."""

    activation_id: str
    new_stop: Decimal
    reason: str
    author: str
    occurred_at: datetime
    written_at: datetime
    code_version: str
    note: str | Absent = field(default_factory=lambda: Absent("no note"))

    def __post_init__(self) -> None:
        for name in ("activation_id", "reason", "author", "code_version"):
            object.__setattr__(self, name, require_text(getattr(self, name), name))
        object.__setattr__(
            self, "occurred_at", require_utc(self.occurred_at, "occurred_at")
        )
        object.__setattr__(
            self, "written_at", require_utc(self.written_at, "written_at")
        )
        if self.written_at < self.occurred_at:
            raise PaperRefusedError(
                "a stop move cannot be filed before the instant it was made"
            )

    @property
    def term(self) -> VersionedTerm:
        """The owner's own term, carried verbatim into a counted vocabulary."""
        return VersionedTerm(
            vocabulary_id=STOP_AMENDMENT_REASON_VOCABULARY,
            term_id=self.reason,
            taxonomy_version=PAPER_TAXONOMY_VERSION,
        )


def amend_stop(store: TradingStore, request: AmendStopRequest) -> ActivationOutcome:
    """Record that the owner moved this trade's stop, and by how much.

    **The `TradePlan` is untouched.** `initial_invalidation` never changes, by
    construction, and what moves is the fold. A widening is recorded as a widening
    and counted as one — `AP` §9.3's whole point, and the reason a reason tag is
    required rather than optional.
    """
    _require_store(store)
    if not isinstance(request, AmendStopRequest):
        raise TypeError("request must be an AmendStopRequest")
    activation = store.activations.load(request.activation_id)
    if not isinstance(activation, TradeActivation):
        raise PaperRefusedError(
            f"{request.activation_id!r} is not an activation; a stop belongs to a "
            "trade the simulator is running"
        )
    plan = store.plans.load(activation.plan_id)
    history = store.activations.stop_history(
        activation.activation_id,
        initial_stop=plan.initial_invalidation,
        direction=plan.direction,
    )
    if history.moves and request.occurred_at < history.moves[-1].at:
        raise PaperRefusedError(
            f"this move is dated {request.occurred_at.isoformat()}, before the "
            f"last one at {history.moves[-1].at.isoformat()}. A stop history is a "
            "chain, and inserting a move behind its own successor would leave the "
            "effective stop with two answers"
        )
    amendment = StopAmendment(
        activation_id=activation.activation_id,
        previous_stop=history.effective,
        new_stop=request.new_stop,
        reason=request.term,
        origin=ValueOrigin.ASSERTED,
        author=request.author,
        occurred_at=request.occurred_at,
        recorded_at=request.written_at,
        audit=RecordAudit.frozen_at(request.occurred_at),
        note=request.note,
    )
    event = TradeLifecycleEvent(
        activation_id=activation.activation_id,
        kind=TradeLifecycleKind.STOP_AMENDED,
        occurred_at=request.occurred_at,
        recorded_at=request.written_at,
        audit=RecordAudit.frozen_at(request.occurred_at),
        reference=amendment.amendment_id,
        note=(
            f"{request.reason}: {canonical_decimal_text(history.effective)} → "
            f"{canonical_decimal_text(request.new_stop)}, stated by the owner"
        ),
    )
    _require_legal(store, activation.activation_id, event)
    write = _write(
        written_at=request.written_at,
        author=request.author,
        reason=AMEND_REASON,
        versions=paper_version_set(code_version=request.code_version),
        source=WriteSource.OWNER,
    )
    written = [
        _publish_once(
            store, store.activations, amendment, kind="stop_amendment", request=write
        ),
        _publish_once(
            store, store.activations, event, kind="lifecycle_step", request=write
        ),
    ]
    entry = JournalEntry(
        kind=JournalKind.NOTE,
        recorded_at=request.occurred_at,
        author=request.author,
        audit=RecordAudit.frozen_at(request.occurred_at),
        title=f"stop moved: {plan.market.pair_symbol} — {request.reason}",
        body=request.note,
        tags=(_lifecycle_tag(TradeLifecycleKind.STOP_AMENDED, request.occurred_at),),
        links=(
            _activation_link(activation.activation_id),
            _plan_link(plan.plan_id),
        ),
    )
    written.append(
        _publish_once(
            store, store.journals, entry, kind="journal_entry", request=write
        )
    )
    return ActivationOutcome(
        action="stop amended", activation=activation, written=tuple(written)
    )


@dataclass(frozen=True, slots=True)
class CancelRequest:
    """Withdrawing an activation before anything filled."""

    activation_id: str
    reason: str
    author: str
    occurred_at: datetime
    written_at: datetime
    code_version: str
    note: str | Absent = field(default_factory=lambda: Absent("no note"))

    def __post_init__(self) -> None:
        for name in ("activation_id", "reason", "author", "code_version"):
            object.__setattr__(self, name, require_text(getattr(self, name), name))
        object.__setattr__(
            self, "occurred_at", require_utc(self.occurred_at, "occurred_at")
        )
        object.__setattr__(
            self, "written_at", require_utc(self.written_at, "written_at")
        )
        if self.written_at < self.occurred_at:
            raise PaperRefusedError(
                "a cancellation cannot be filed before the instant it was made"
            )


def cancel_activation(store: TradingStore, request: CancelRequest) -> ActivationOutcome:
    """Withdraw an activation. Legal only while nothing has filled against it.

    The lifecycle table decides that, not this function: `CANCELLED` follows
    `PENDING`, `TRIGGERED` and `AMBIGUOUS` and nothing else, so an attempt to
    cancel an open position raises rather than quietly abandoning a fill the
    ledger already holds.
    """
    _require_store(store)
    if not isinstance(request, CancelRequest):
        raise TypeError("request must be a CancelRequest")
    activation = store.activations.load(request.activation_id)
    if not isinstance(activation, TradeActivation):
        raise PaperRefusedError(f"{request.activation_id!r} is not an activation")
    event = TradeLifecycleEvent(
        activation_id=activation.activation_id,
        kind=TradeLifecycleKind.CANCELLED,
        occurred_at=request.occurred_at,
        recorded_at=request.written_at,
        audit=RecordAudit.frozen_at(request.occurred_at),
        reason=VersionedTerm(
            vocabulary_id=STOP_AMENDMENT_REASON_VOCABULARY,
            term_id=request.reason,
            taxonomy_version=PAPER_TAXONOMY_VERSION,
        ),
        note=request.note,
    )
    _require_legal(store, activation.activation_id, event)
    write = _write(
        written_at=request.written_at,
        author=request.author,
        reason=ACTIVATE_REASON,
        versions=paper_version_set(code_version=request.code_version),
        source=WriteSource.OWNER,
    )
    written = [
        _publish_once(
            store, store.activations, event, kind="lifecycle_step", request=write
        )
    ]
    entry = JournalEntry(
        kind=JournalKind.NOTE,
        recorded_at=request.occurred_at,
        author=request.author,
        audit=RecordAudit.frozen_at(request.occurred_at),
        title=f"cancelled: {activation.market.pair_symbol}",
        body=request.note,
        tags=(_lifecycle_tag(TradeLifecycleKind.CANCELLED, request.occurred_at),),
        links=(_activation_link(activation.activation_id),),
    )
    written.append(
        _publish_once(
            store, store.journals, entry, kind="journal_entry", request=write
        )
    )
    return ActivationOutcome(
        action="cancelled", activation=activation, written=tuple(written)
    )


# --------------------------------------------------------------------------
# Running the simulation.
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TradeRunReport:
    """What one activation's run did, and what it left behind."""

    activation: TradeActivation
    state: TradeLifecycleState
    bars_advanced: int
    written: tuple[tuple[str, str, bool], ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def created_any(self) -> bool:
        return any(created for _, _, created in self.written)

    @property
    def market(self) -> str:
        return self.activation.market.pair_symbol


@dataclass(frozen=True, slots=True)
class SimulationReport:
    """Every activation one run touched, and every market it could not reach."""

    ran_at: datetime
    interval: str
    runs: tuple[TradeRunReport, ...] = ()
    unreachable: tuple[tuple[str, str], ...] = ()
    skipped: tuple[tuple[str, str], ...] = ()

    @property
    def advanced(self) -> int:
        return sum(1 for run in self.runs if run.bars_advanced)

    @property
    def created_any(self) -> bool:
        return any(run.created_any for run in self.runs)


def simulate_activation(
    store: TradingStore,
    activation: TradeActivation,
    bars: tuple[PriceBar, ...],
    *,
    written_at: datetime,
    code_version: str,
) -> TradeRunReport:
    """Replay one activation over the bars supplied and record what happened.

    **Bars that opened before the activation are dropped before the replay sees
    them.** They cannot change anything — every entry condition requires a bar
    at or after the instruction — but a provider page reaches back further than
    any activation, and counting them would make *"bars advanced"* a figure
    about the fetch rather than about the trade. A run that says it advanced 999
    bars over a two-day-old activation is a run nobody can check.
    """
    _require_store(store)
    plan = store.plans.load(activation.plan_id)
    result = replay_bars(
        run_state_for(activation, plan),
        bars_for_run(activation, bars, ran_at=written_at),
        owner_moves=owner_stop_moves(store, activation.activation_id),
    )
    versions = paper_version_set(code_version=code_version)
    write = _write(
        written_at=written_at,
        author=PAPER_AUTHOR,
        reason=SIMULATE_REASON,
        versions=versions,
    )
    written: list[tuple[str, str, bool]] = []
    fill_ids: list[str] = []
    for step_result in result.results:
        for step in step_result.steps:
            written.extend(
                _publish_step(
                    store,
                    activation=activation,
                    plan=plan,
                    step=step,
                    bar=step_result.bar,
                    stop_move=step_result.stop_move,
                    written_at=written_at,
                    write=write,
                    fill_ids=fill_ids,
                )
            )
    notes = _bridge_proposal(
        store, activation, result, written_at=written_at, write=write, written=written
    )
    written.extend(
        _freeze_outcome(
            store,
            activation=activation,
            plan=plan,
            result=result,
            fill_ids=tuple(fill_ids),
            written_at=written_at,
            write=write,
            versions=versions,
        )
    )
    return TradeRunReport(
        activation=activation,
        state=result.final_state.state,
        bars_advanced=result.bars_advanced,
        written=tuple(written),
        notes=notes,
    )


def bars_for_run(
    activation: TradeActivation,
    bars: tuple[PriceBar, ...],
    *,
    ran_at: datetime,
) -> tuple[PriceBar, ...]:
    """The bars this run may advance, oldest first — bounded at both ends.

    **Before the activation**, because a bar that opened before the instruction
    cannot be affected by it. A provider page reaches back further than any
    activation, and counting those bars would make *"bars advanced"* a figure
    about the fetch rather than about the trade.

    **After the run's own instant**, because FMITS cannot learn of a candle
    before the moment it is filing. This is the no-lookahead rule applied to the
    *filing* clock rather than to the decision clock, and it is what makes
    `--reference-time` a real replay clock instead of a label: without it a
    past-dated run reads live candles that closed after it, and the events it
    would write carry an `occurred_at` later than their own `recorded_at` — a
    refusal the domain raises correctly and cryptically, two layers down.
    """
    boundary = require_utc(ran_at, "ran_at")
    return tuple(
        bar
        for bar in bars
        if activation.activated_at <= bar.open_time <= boundary
    )


def _publish_step(
    store: TradingStore,
    *,
    activation: TradeActivation,
    plan: TradePlan,
    step: Any,
    bar: PriceBar,
    stop_move: Any,
    written_at: datetime,
    write: WriteRequest,
    fill_ids: list[str],
) -> list[tuple[str, str, bool]]:
    """One derived transition → a fill, an amendment, an event and a journal note.

    The fill is published **before** the event that references it: an event
    pointing at a fill the store does not hold is a dangling reference no reader
    can resolve, while a fill with no event yet is simply a fill the next run
    re-derives and re-references identically.
    """
    written: list[tuple[str, str, bool]] = []
    reference: str | Absent = Absent("no reference")
    if not isinstance(step.fill, Absent):
        trade = _trade_from(activation, plan, step.fill, written_at=written_at)
        written.append(
            _publish_once(store, store.trades, trade, kind="trade", request=write)
        )
        reference = trade.event_id
        fill_ids.append(trade.event_id)
    if step.kind is TradeLifecycleKind.STOP_AMENDED:
        amendment = StopAmendment(
            activation_id=activation.activation_id,
            previous_stop=stop_move.previous_stop,
            new_stop=stop_move.new_stop,
            reason=VersionedTerm(
                vocabulary_id=STOP_POLICY_VOCABULARY,
                term_id=stop_move.term_id,
                taxonomy_version=PAPER_TAXONOMY_VERSION,
            ),
            origin=ValueOrigin.POLICY_DERIVED,
            author=PAPER_AUTHOR,
            occurred_at=bar.open_time,
            recorded_at=written_at,
            audit=RecordAudit.frozen_at(bar.open_time),
            policy_id=PAPER_FILL_POLICY_ID,
            policy_version=PAPER_FILL_POLICY_VERSION,
            causing_close_time=bar.open_time,
        )
        written.append(
            _publish_once(
                store,
                store.activations,
                amendment,
                kind="stop_amendment",
                request=write,
            )
        )
        reference = amendment.amendment_id
    event = TradeLifecycleEvent(
        activation_id=activation.activation_id,
        kind=step.kind,
        occurred_at=bar.open_time,
        recorded_at=written_at,
        audit=RecordAudit.frozen_at(bar.open_time),
        causing_close_time=bar.open_time,
        reference=reference,
        note=step.note,
        bar_sequence=step.bar_sequence,
    )
    written.append(
        _publish_once(
            store, store.activations, event, kind="lifecycle_step", request=write
        )
    )
    written.append(
        _publish_once(
            store,
            store.journals,
            _step_journal(activation, plan, step, bar, reference),
            kind="journal_entry",
            request=write,
        )
    )
    return written


def _trade_from(
    activation: TradeActivation, plan: TradePlan, fill: Fill, *, written_at: datetime
) -> Trade:
    """One simulated fill, as the ledger event it is.

    `LedgerSource.PAPER_SIMULATION` rather than `MANUAL`, because a fill the owner
    did not type is not their assertion — and a surface that could not tell the
    two apart would be rendering a lie of omission.
    """
    side = entry_side(plan.direction) if fill.is_entry else exit_side(plan.direction)
    return Trade(
        occurred_at=fill.at,
        recorded_at=written_at,
        account=activation.account,
        book=activation.book,
        market=activation.market,
        side=side,
        quantity=fill.quantity,
        price=fill.price,
        fee=Money.zero(activation.market.quote_asset),
        fx_rate_to_tax_currency=PAPER_FX_RATE,
        fx_source=PAPER_FX_SOURCE,
        fx_timestamp=fill.at,
        source=LedgerSource.PAPER_SIMULATION,
        asserted_by=PAPER_AUTHOR,
        audit=RecordAudit.frozen_at(fill.at),
        plan_id=plan.plan_id,
        proposal_id=plan.proposal_id,
    )


def _step_journal(
    activation: TradeActivation,
    plan: TradePlan,
    step: Any,
    bar: PriceBar,
    reference: str | Absent,
) -> JournalEntry:
    """One entry per transition. **No silent state change**, taken literally."""
    detail = (
        ""
        if isinstance(step.fill, Absent)
        else (
            f" {step.fill.quantity} at {canonical_decimal_text(step.fill.price)}"
            + (" (gapped through the level)" if step.fill.gapped else "")
        )
    )
    return JournalEntry(
        kind=JournalKind.NOTE,
        recorded_at=bar.open_time,
        author=PAPER_AUTHOR,
        audit=RecordAudit.frozen_at(bar.open_time),
        title=(
            f"{step.kind.value}: {plan.market.pair_symbol} on the "
            f"{bar.interval} bar opening {bar.open_time.isoformat()}"
        ),
        body=(
            step.note
            if not isinstance(step.note, Absent)
            else f"{step.kind.value}{detail}. {activation.cost_policy.basis}"
        ),
        tags=(_lifecycle_tag(step.kind, bar.open_time),),
        links=(
            (_activation_link(activation.activation_id), _plan_link(plan.plan_id))
            if isinstance(reference, Absent)
            else (
                _activation_link(activation.activation_id),
                _plan_link(plan.plan_id),
                _trade_link(reference),
            )
        ),
    )


def _bridge_proposal(
    store: TradingStore,
    activation: TradeActivation,
    result: ReplayResult,
    *,
    written_at: datetime,
    write: WriteRequest,
    written: list[tuple[str, str, bool]],
) -> tuple[str, ...]:
    """Carry an entry through to the proposal that suggested it.

    `PROPOSED → PENDING → TRIGGERED → OPEN` becomes one chain across two objects
    rather than two disconnected ones: when an activation names a proposal, the
    entry trigger is appended to **that proposal's own stream**, so the setup the
    system suggested and the trade it became are one readable history.

    **`ENTRY_TRIGGERED` and nothing more.** `AP` §8.4 defines `EXECUTED` as *"a
    Trade referencing this proposal landed"*, and a **paper** fill is not that: it
    is excluded from every real-money aggregate by `DEFAULT_EXCLUDED_BOOKS`, and
    recording it as an execution would put simulated activity into the acceptance
    rate, the invalid-entry rate and every other §20.5 behavioural metric computed
    over the proposal corpus. The proposal reaches `TRIGGERED`, which is true and
    measurable; `EXECUTED` stays for money.

    **And only when the proposal's own fold makes it legal.** `ENTRY_TRIGGERED`
    requires `DECIDED`, so a proposal the owner never decided on is left untouched
    and the skip is reported on the page. Forcing the event would mean loosening
    `fmis.proposal`'s transition table for the convenience of a simulator, which
    is the wrong direction for a boundary to move.
    """
    proposal_id = activation.proposal_id
    if isinstance(proposal_id, Absent):
        return ()
    entry_bar = _first_entry_bar(result)
    if entry_bar is None:
        return ()
    if not store.opportunities.exists(proposal_id):
        return (
            f"activation names proposal {proposal_id}, which this store does not "
            "hold; its lifecycle was not advanced",
        )
    view = store.opportunities.state(proposal_id)
    if view.state is not ProposalState.DECIDED:
        return (
            f"proposal {proposal_id} is {view.state.value}; ENTRY_TRIGGERED is "
            "legal only from decided, so its lifecycle was not advanced. Record "
            "the decision and re-run to link the two",
        )
    event = ProposalLifecycleEvent(
        proposal_id=proposal_id,
        kind=ProposalLifecycleKind.ENTRY_TRIGGERED,
        occurred_at=entry_bar,
        recorded_at=written_at,
        reason_tag=Absent("a measured lifecycle fact carries no reason tag"),
        causing_close_time=entry_bar,
        audit=RecordAudit.frozen_at(entry_bar),
        reference=activation.activation_id,
    )
    try:
        fold_proposal_state(
            store.opportunities.load(proposal_id),
            store.opportunities.live_events_for(proposal_id) + (event,),
        )
    except (ProposalIllegalTransitionError, DomainValidationError) as error:
        # The state was legal a moment ago and the *combined* stream is not: the
        # commonest cause is a decision and an entry bar sharing an instant,
        # where the proposal's own fold cannot order them. Reported rather than
        # forced, for the same reason the engine halts on an ambiguous candle —
        # and checked here rather than trusted, because a read that succeeded
        # before the write is not a promise that the write is legal.
        return (
            f"proposal {proposal_id} was not advanced: {error}",
        )
    written.append(
        _publish_once(
            store,
            store.opportunities,
            event,
            kind="lifecycle_event",
            request=write,
        )
    )
    return (
        f"proposal {proposal_id} advanced to triggered. A paper fill is not an "
        "execution: it is excluded from every real-money aggregate, and recording "
        "one as EXECUTED would put simulated activity into the behavioural metrics "
        "computed over the proposal corpus",
    )


def _first_entry_bar(result: ReplayResult) -> datetime | None:
    for step_result in result.results:
        for step in step_result.steps:
            if step.kind is TradeLifecycleKind.ENTRY_FILLED:
                return step_result.bar.open_time
    return None


def _freeze_outcome(
    store: TradingStore,
    *,
    activation: TradeActivation,
    plan: TradePlan,
    result: ReplayResult,
    fill_ids: tuple[str, ...],
    written_at: datetime,
    write: WriteRequest,
    versions: VersionSet,
) -> list[tuple[str, str, bool]]:
    """Freeze the excursions the moment the trade ends, and never later.

    `AP` §25.2's rule, applied where it was written for: *"kline history is not
    permanent and instruments get delisted; a lazily-computed excursion metric can
    quietly become uncomputable."*
    """
    final = result.final_state
    if final.state not in {
        TradeLifecycleState.CLOSED,
        TradeLifecycleState.EXPIRED,
        TradeLifecycleState.CANCELLED,
        TradeLifecycleState.SUPERSEDED,
    }:
        return []
    if store.activations.outcome_for(activation.activation_id) is not None:
        # pragma: no cover - freezing an outcome also appends OUTCOME_RECORDED,
        # which resolves the activation and removes it from `live_activations`,
        # so a second run never reaches a terminal-but-unresolved trade. Kept
        # because a hand-written store could hold one.
        return []  # pragma: no cover
    reason = _exit_reason_of(result, final.state)
    exposed = reason in {ExitReason.TARGET_HIT, ExitReason.STOP_HIT}
    absent = Absent("no fill ever opened this trade")
    closed_at = result.results[-1].bar.open_time if result.results else written_at
    outcome = TradeOutcome(
        activation_id=activation.activation_id,
        plan_id=plan.plan_id,
        market=activation.market,
        exit_reason=reason,
        frozen_at=written_at,
        interval=activation.interval,
        cost_policy=activation.cost_policy,
        fill_policy_id=activation.fill_policy_id,
        fill_policy_version=activation.fill_policy_version,
        initial_stop=plan.initial_invalidation,
        version_set=versions,
        audit=RecordAudit.frozen_at(written_at),
        opened_at=final.opened_at if exposed else absent,
        closed_at=closed_at if exposed else absent,
        bars_held=final.excursion.bars if exposed else absent,
        max_favourable_price=final.excursion.favourable if exposed else absent,
        max_adverse_price=final.excursion.adverse if exposed else absent,
        effective_stop_at_exit=final.effective_stop if exposed else absent,
        fill_event_ids=fill_ids if exposed else (),
    )
    written = [
        _publish_once(
            store, store.activations, outcome, kind="trade_outcome", request=write
        )
    ]
    note = (
        f"outcome frozen: {reason.value}. Excursions are measured on "
        f"{activation.interval} closed bars and are not recomputable once "
        "candle history is gone"
    )
    event = TradeLifecycleEvent(
        activation_id=activation.activation_id,
        kind=TradeLifecycleKind.OUTCOME_RECORDED,
        occurred_at=written_at,
        recorded_at=written_at,
        audit=RecordAudit.frozen_at(written_at),
        reference=outcome.outcome_id,
        note=note,
    )
    written.append(
        _publish_once(
            store, store.activations, event, kind="lifecycle_step", request=write
        )
    )
    # The brief's §11, taken literally: **no silent state change.** The first
    # draft wrote this transition to the lifecycle stream and not to the
    # journal, so the one event that says a trade is over was the only one the
    # owner's own history did not record. Found by an adversarial review.
    written.append(
        _publish_once(
            store,
            store.journals,
            JournalEntry(
                kind=JournalKind.NOTE,
                recorded_at=written_at,
                author=PAPER_AUTHOR,
                audit=RecordAudit.frozen_at(written_at),
                title=(
                    f"outcome_recorded: {plan.market.pair_symbol} — {reason.value}"
                ),
                body=f"{note}. {activation.cost_policy.basis}",
                tags=(
                    _lifecycle_tag(
                        TradeLifecycleKind.OUTCOME_RECORDED, written_at
                    ),
                ),
                links=(
                    _activation_link(activation.activation_id),
                    _plan_link(plan.plan_id),
                ),
            ),
            kind="journal_entry",
            request=write,
        )
    )
    return written


def _exit_reason_of(
    result: ReplayResult, state: TradeLifecycleState
) -> ExitReason:
    if state in _TERMINAL_REASONS:
        return _TERMINAL_REASONS[state]
    for step_result in reversed(result.results):
        for step in reversed(step_result.steps):
            if step.kind is not TradeLifecycleKind.EXIT_FILLED:  # pragma: no cover
                # A replay stops on the bar that closed the trade, so the exit is
                # always the last step of the last bar and the scan finds it
                # first. Kept so the search is a search rather than an index.
                continue
            assert not isinstance(step.fill, Absent)  # an exit always carries one
            return _EXIT_TRIGGER_REASONS[step.fill.trigger]
    raise PaperRefusedError(  # pragma: no cover - a closed run always has an exit
        "a closed run recorded no exit fill; there is no ending to freeze"
    )


def run_simulation(
    store: TradingStore,
    *,
    ran_at: datetime,
    code_version: str,
    interval: str,
    bars_by_symbol: dict[str, tuple[PriceBar, ...]],
    failures: dict[str, str] | None = None,
    markets: tuple[str, ...] = (),
) -> SimulationReport:
    """Advance every live activation the store holds, one market at a time.

    Per-activation failure isolation is deliberately **not** applied: a run that
    swallowed an exception would leave a trade half-written and report success.
    What is isolated is the *fetch*, one layer out, where a symbol the provider
    could not serve becomes a row in `unreachable` rather than an aborted morning.
    """
    _require_store(store)
    moment = require_utc(ran_at, "ran_at")
    runs: list[TradeRunReport] = []
    skipped: list[tuple[str, str]] = []
    for activation, view in store.activations.live_activations():
        symbol = activation.market.pair_symbol
        if markets and symbol.upper() not in {name.upper() for name in markets}:
            continue
        if activation.interval != interval:
            skipped.append(
                (
                    activation.activation_id,
                    f"this activation runs on {activation.interval} and the run "
                    f"fetched {interval} bars; excursions measured across two "
                    "intervals are not comparable",
                )
            )
            continue
        bars = bars_by_symbol.get(symbol)
        if bars is None:
            skipped.append(
                (activation.activation_id, f"no {interval} candles for {symbol}")
            )
            continue
        runs.append(
            simulate_activation(
                store,
                activation,
                bars,
                written_at=moment,
                code_version=code_version,
            )
        )
    return SimulationReport(
        ran_at=moment,
        interval=interval,
        runs=tuple(runs),
        unreachable=tuple(sorted((failures or {}).items())),
        skipped=tuple(skipped),
    )
