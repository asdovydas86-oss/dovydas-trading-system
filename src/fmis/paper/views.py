"""Reading a simulated trade back out of the store. **Nothing here writes.**

A guard asserts this module names no write verb on any repository, because the
read path is where a "convenience" write would be least visible and most
damaging: a `trade status` that repaired something would make the store's
contents depend on who looked at them.

**The fills are found through the lifecycle stream, not by guessing.** A `Trade`
names its `plan_id`, and one commitment can be activated more than once — a first
attempt cancelled, a second superseding it — so filtering fills by plan would
fold two runs into one answer. Every fill this engine wrote is referenced by the
event that recorded it, and that reference is the join.

**The fills are read through the resolver, never raw.** `LedgerRepository`
returns `ResolvedTrade`, a token this layer cannot construct, so a corrected fill
is reported as it now stands and a superseded one is not counted twice.

**Every figure is folded, and the two quotients are computed here.** `AP` §25.2
classes realized P&L, average entry and position quantity as projections, so this
module recomputes them from the ledger and the frozen outcome contributes only
what cannot be recomputed — the excursions, the bar count, the exit reason and the
stop that was in force when it ended.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fmis.journal import TradeJournal
from fmis.ledger import ResolvedTrade
from fmis.money import DustPolicy, Money, Quantity, canonical_decimal_text
from fmis.persistence import TradingStore
from fmis.plan import TradePlan
from fmis.portfolio_risk import direction_of, stop_distance
from fmis.positions import Position, PositionState, fold_positions
from fmis.provenance import Absent, ValueOrigin
from fmis.records import DomainValidationError, require_text, require_utc
from fmis.snapshotting import TradeDirection
from fmis.trade_lifecycle import (
    StopHistory,
    TradeActivation,
    TradeLifecycleKind,
    TradeLifecycleState,
    TradeLifecycleView,
    TradeOutcome,
)
from fmis.paper.engine import initial_run_state
from fmis.paper.models import PAPER_AUTHOR_LABEL as PAPER_AUTHOR
from fmis.paper.models import Excursion, PaperError, PriceBar
from fmis.paper.monitor import TradeMonitor, monitor_trade
from fmis.paper.replay import replay_bars

__all__ = [
    "ACTIVATION_SUBJECT_KIND",
    "PLAN_SUBJECT_KIND",
    "TRADE_SUBJECT_KIND",
    "FILL_EVENT_KINDS",
    "PaperTradeNotFoundError",
    "OutcomeReading",
    "PaperWarning",
    "PaperTradeView",
    "fill_references",
    "fills_for_activation",
    "owner_stop_moves",
    "run_state_for",
    "read_outcome",
    "load_paper_trade",
    "list_paper_trades",
]

#: The `JournalLink.target_kind` an entry about a simulated trade carries. Equal
#: to the persisted record kinds on purpose: a link whose target kind did not name
#: a real kind would be a foreign key into nothing.
ACTIVATION_SUBJECT_KIND = "trade_activation"
PLAN_SUBJECT_KIND = "trade_plan"
TRADE_SUBJECT_KIND = "trade"

#: The lifecycle kinds that reference a ledger fill. The join between the two
#: halves of a simulated trade, named once.
FILL_EVENT_KINDS: frozenset[TradeLifecycleKind] = frozenset(
    {
        TradeLifecycleKind.ENTRY_FILLED,
        TradeLifecycleKind.PARTIAL_EXIT_FILLED,
        TradeLifecycleKind.EXIT_FILLED,
    }
)

_SECONDS_PER_DAY = Decimal(60 * 60 * 24)


class PaperTradeNotFoundError(PaperError, LookupError):
    """The id named is not a trade this store holds.

    Its own class because at this layer *"you mistyped an id"* and *"the store is
    missing a record it should hold"* are different problems with different
    remedies — the same distinction `fmis.trade_capture` already draws.
    """


def _require_store(store: Any) -> TradingStore:
    if not isinstance(store, TradingStore):
        raise TypeError(f"store must be a TradingStore, got {type(store).__name__}")
    return store


def _require_dust(dust: Any) -> DustPolicy:
    if not isinstance(dust, DustPolicy):
        raise TypeError(
            "a position fold needs a DustPolicy: what counts as flat is the "
            "owner's threshold, and this layer invents none"
        )
    return dust


def fill_references(events: Iterable[Any]) -> tuple[str, ...]:
    """Every ledger fill one lifecycle stream points at, in stream order."""
    found: list[str] = []
    for event in events:
        if event.kind not in FILL_EVENT_KINDS:
            continue
        if isinstance(event.reference, Absent):
            raise DomainValidationError(
                f"lifecycle event {event.event_id} records a fill and names none; "
                "the reference is the only join between a simulated trade and the "
                "money it moved"
            )
        if event.reference not in found:
            found.append(event.reference)
    return tuple(found)


def fills_for_activation(
    store: TradingStore, activation_id: str
) -> tuple[ResolvedTrade, ...]:
    """The resolved ledger fills one activation produced, oldest first."""
    _require_store(store)
    wanted = set(
        fill_references(store.activations.live_events_for(
            require_text(activation_id, "activation_id")
        ))
    )
    if not wanted:
        return ()
    return tuple(
        entry for entry in store.ledger.resolved() if entry.event_id in wanted
    )


def owner_stop_moves(
    store: TradingStore, activation_id: str
) -> tuple[tuple[datetime, Decimal], ...]:
    """The stop moves the owner made themselves, as a replay applies them.

    **Only the owner's.** A `POLICY_DERIVED` move is one this engine derives, and
    feeding a stored one back into the replay that produces it would either
    duplicate the record or make the run depend on whether it had been run before.
    """
    _require_store(store)
    return tuple(
        (amendment.ordering_key, amendment.new_stop)
        for amendment in store.activations.live_amendments_for(
            require_text(activation_id, "activation_id")
        )
        if amendment.origin is ValueOrigin.ASSERTED
    )


def run_state_for(
    activation: TradeActivation, plan: TradePlan
) -> Any:
    """The state a replay of this activation starts from.

    Always the beginning. A run is replayed from the activation every time, and
    the writes it produces are content-addressed — so the second run publishes
    nothing, and there is no partially-rebuilt state to get wrong.
    """
    if not isinstance(activation, TradeActivation):
        raise TypeError("activation must be a TradeActivation")
    if not isinstance(plan, TradePlan):
        raise TypeError("plan must be a TradePlan")
    if activation.plan_id != plan.plan_id:
        raise DomainValidationError(
            f"activation {activation.activation_id} names plan "
            f"{activation.plan_id}, not {plan.plan_id}"
        )
    return initial_run_state(
        activation,
        direction=plan.direction,
        initial_stop=plan.initial_invalidation,
    )


@dataclass(frozen=True, slots=True)
class OutcomeReading:
    """The frozen outcome folded together with the ledger, at read time.

    Every figure the milestone brief's outcome list names, and **not one of them
    is a stored field**. The record froze what candle history alone could answer;
    everything below is arithmetic over that plus the fills, recomputed on every
    read so a `Correction` to a fill changes the answer instead of contradicting
    it.
    """

    outcome: TradeOutcome
    entry_price: Decimal | Absent
    exit_price: Decimal | Absent
    realized_pnl_gross: Money | Absent
    realized_pnl_net: Money | Absent
    fees: tuple[Money, ...]
    initial_risk: Money | Absent
    final_r: Decimal | Absent
    pnl_percent: Decimal | Absent
    max_favourable_r: Decimal | Absent
    max_adverse_r: Decimal | Absent

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, TradeOutcome):
            raise TypeError("outcome must be a TradeOutcome")

    @property
    def exit_reason(self) -> str:
        return self.outcome.exit_reason.value

    @property
    def bars_held(self) -> int | Absent:
        return self.outcome.bars_held

    @property
    def holding_time(self) -> timedelta | Absent:
        return self.outcome.holding_time()

    @property
    def days_held(self) -> Decimal | Absent:
        elapsed = self.holding_time
        if isinstance(elapsed, Absent):
            return elapsed
        return Decimal(str(elapsed.total_seconds())) / _SECONDS_PER_DAY

    @property
    def target_hit(self) -> bool:
        from fmis.trade_lifecycle import ExitReason

        return self.outcome.exit_reason is ExitReason.TARGET_HIT

    @property
    def stop_hit(self) -> bool:
        from fmis.trade_lifecycle import ExitReason

        return self.outcome.exit_reason is ExitReason.STOP_HIT

    def to_payload(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome.outcome_id,
            "exit_reason": self.exit_reason,
            "entry_price": _text_or_none(self.entry_price),
            "exit_price": _text_or_none(self.exit_price),
            "realized_pnl_gross": _money_or_none(self.realized_pnl_gross),
            "realized_pnl_net": _money_or_none(self.realized_pnl_net),
            "fees": [fee.to_payload() for fee in self.fees],
            "initial_risk": _money_or_none(self.initial_risk),
            "final_r": _text_or_none(self.final_r),
            "pnl_percent": _text_or_none(self.pnl_percent),
            "max_favourable_r": _text_or_none(self.max_favourable_r),
            "max_adverse_r": _text_or_none(self.max_adverse_r),
            "bars_held": None if isinstance(self.bars_held, Absent) else self.bars_held,
        }


def _text_or_none(value: Decimal | Absent) -> str | None:
    return None if isinstance(value, Absent) else canonical_decimal_text(value)


def _money_or_none(value: Money | Absent) -> dict[str, Any] | None:
    return None if isinstance(value, Absent) else value.to_payload()


def read_outcome(
    outcome: TradeOutcome,
    *,
    activation: TradeActivation,
    direction: TradeDirection,
    position: Position | Absent,
) -> OutcomeReading:
    """Fold one frozen outcome against the fills it names."""
    if not isinstance(outcome, TradeOutcome):
        raise TypeError("outcome must be a TradeOutcome")
    quote = activation.market.quote_asset
    entry = (
        Absent("this trade never held a position")
        if isinstance(position, Absent)
        else position.average_entry.per_unit
    )
    exit_price = (
        Absent("this trade never held a position")
        if isinstance(position, Absent) or isinstance(position.average_exit, Absent)
        else position.average_exit.per_unit
    )
    gross = (
        Absent("this trade never held a position")
        if isinstance(position, Absent)
        else position.realized_pnl_gross
    )
    net = (
        Absent("this trade never held a position")
        if isinstance(position, Absent)
        else position.realized_pnl_net
    )
    fees = () if isinstance(position, Absent) else position.fees
    distance, risk = _risk_from(outcome, activation, direction, entry, quote)
    return OutcomeReading(
        outcome=outcome,
        entry_price=entry,
        exit_price=exit_price,
        realized_pnl_gross=gross,
        realized_pnl_net=net,
        fees=fees,
        initial_risk=risk,
        final_r=_ratio(net, risk),
        pnl_percent=_percent(net, entry, activation.quantity, quote),
        max_favourable_r=_excursion_r(
            direction, entry, outcome.max_favourable_price, distance
        ),
        max_adverse_r=_excursion_r(
            direction, entry, outcome.max_adverse_price, distance
        ),
    )


def _risk_from(
    outcome: TradeOutcome,
    activation: TradeActivation,
    direction: TradeDirection,
    entry: Decimal | Absent,
    quote: Any,
) -> tuple[Decimal | Absent, Money | Absent]:
    if isinstance(entry, Absent):
        return entry, Absent(entry.reason)
    try:
        distance = stop_distance(
            direction_of(direction), entry=entry, stop=outcome.initial_stop
        )
    except DomainValidationError as error:
        reason = Absent(str(error))
        return reason, reason
    return distance, activation.quantity.value_at(distance, quote)


def _ratio(value: Money | Absent, basis: Money | Absent) -> Decimal | Absent:
    """One quotient, computed here and stored nowhere."""
    if isinstance(value, Absent):
        return Absent(value.reason)
    if isinstance(basis, Absent):
        return Absent(basis.reason)
    if value.asset != basis.asset:
        return Absent(
            f"the figures are stated in {value.asset} and {basis.asset}; a ratio "
            "over two currencies needs a dated rate this reading does not carry"
        )
    if basis.amount == 0:
        return Absent("the basis is zero, so the ratio is undefined rather than large")
    return value.amount / basis.amount


def _percent(
    net: Money | Absent, entry: Decimal | Absent, quantity: Quantity, quote: Any
) -> Decimal | Absent:
    """`net ÷ (entry × activated size)` — profit as a share of what was committed.

    A **fraction**, not a number multiplied by a hundred: `fmis.portfolio_risk`
    already states the convention once and a second unit here would be the one
    figure two surfaces render differently.
    """
    if isinstance(entry, Absent):
        return Absent(entry.reason)
    return _ratio(net, quantity.value_at(entry, quote))


def _excursion_r(
    direction: TradeDirection,
    entry: Decimal | Absent,
    extreme: Decimal | Absent,
    distance: Decimal | Absent,
) -> Decimal | Absent:
    for value in (entry, extreme, distance):
        if isinstance(value, Absent):
            return Absent(value.reason)
    return direction.sign * (extreme - entry) / distance  # type: ignore[operator]


@dataclass(frozen=True, slots=True)
class PaperWarning:
    """One thing qualifying a paper trade, with a stable code."""

    code: str
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", require_text(self.code, "code"))
        object.__setattr__(self, "text", require_text(self.text, "text"))


@dataclass(frozen=True, slots=True)
class PaperTradeView:
    """One simulated trade, assembled from every record that describes it."""

    activation: TradeActivation
    plan: TradePlan
    lifecycle: TradeLifecycleView
    stop_history: StopHistory
    monitor: TradeMonitor
    position: Position | Absent
    journal: TradeJournal
    fills: tuple[ResolvedTrade, ...] = ()
    outcome: OutcomeReading | Absent = field(
        default_factory=lambda: Absent("this trade has not finished")
    )
    warnings: tuple[PaperWarning, ...] = ()

    @property
    def activation_id(self) -> str:
        return self.activation.activation_id

    @property
    def state(self) -> TradeLifecycleState:
        return self.lifecycle.state

    @property
    def is_finished(self) -> bool:
        return not isinstance(self.outcome, Absent)


def _warnings_for(
    activation: TradeActivation,
    lifecycle: TradeLifecycleView,
    stop_history: StopHistory,
    position: Position | Absent,
    journal: TradeJournal,
    *,
    at: datetime,
) -> tuple[PaperWarning, ...]:
    """Everything qualifying this view, in a fixed order.

    Fixed rather than severity-sorted: ordering by severity would make the list
    read as ranked by importance, and this package ranks nothing.
    """
    found: list[PaperWarning] = []
    if lifecycle.is_halted:
        found.append(
            PaperWarning(
                "PT-W1",
                "This trade is halted. One candle reached both the stop and a "
                "target and opened between them, so no fill was invented. Record "
                "the exit you judge you would have taken to resolve it.",
            )
        )
    if stop_history.widening_count:
        found.append(
            PaperWarning(
                "PT-W2",
                f"The stop has been widened {stop_history.widening_count} time(s) "
                "away from the commitment. Widening a stop under pressure is the "
                "single strongest warning sign of an outsized loss, and it is recorded "
                "here rather than absorbed into the result.",
            )
        )
    if activation.is_expired_at(at) and lifecycle.has_exposure:
        found.append(
            PaperWarning(
                "PT-W3",
                "The activation's window closed while the position was still "
                "open. FMITS records the expiry and takes no action on it.",
            )
        )
    if not isinstance(position, Absent) and position.state is PositionState.OPEN:
        if position.net_quantity != position.max_exposure:
            found.append(
                PaperWarning(
                    "PT-W4",
                    f"The position has been reduced: {position.net_quantity} is "
                    f"open against a maximum exposure of {position.max_exposure}. "
                    "Risk figures describe the size that was activated, not what "
                    "is open now.",
                )
            )
    if activation.ladder.is_empty:
        found.append(
            PaperWarning(
                "PT-W5",
                "This activation states no target ladder, so the whole position "
                "runs to the stop. That is an absence, not a target of zero.",
            )
        )
    if not _owner_authored(journal):
        found.append(
            PaperWarning(
                "PT-W6",
                "Nothing the owner wrote is attached to this trade. What the "
                "simulator recorded does not count: whether the owner wrote "
                "anything at all is the cheapest discipline metric in this "
                "system, and a simulator's own notes would make it read 100 % "
                "forever.",
            )
        )
    return tuple(found)


def _owner_authored(journal: TradeJournal) -> bool:
    """Whether anything on this trade was written by someone other than the engine.

    `journal.is_empty` was the first draft and was always false: activating a
    trade writes a note, so the discipline metric would have read *"the owner
    wrote something"* about every trade in the store from the moment it existed.
    """
    return any(entry.author != PAPER_AUTHOR for entry in journal.entries)


def load_paper_trade(
    store: TradingStore,
    activation_id: str,
    *,
    dust: DustPolicy,
    at: datetime,
    bars: tuple[PriceBar, ...] = (),
) -> PaperTradeView:
    """Assemble one simulated trade from every record that describes it.

    `bars` is optional and changes exactly one thing: with candles the excursion
    and the rungs already filled are re-derived, and without them they come from
    the frozen outcome if the trade has finished and are `Absent` if it has not.
    A reading that invented a zero excursion for an open trade would make every
    page look like a trade that never went against the owner.
    """
    _require_store(store)
    _require_dust(dust)
    moment = require_utc(at, "at")
    wanted = require_text(activation_id, "activation_id")
    if not store.activations.exists(wanted):
        raise PaperTradeNotFoundError(
            f"no simulated trade {wanted!r} is in this store. `fmits trade status` "
            "lists every activation it holds"
        )
    activation = store.activations.load(wanted)
    if not isinstance(activation, TradeActivation):
        raise PaperTradeNotFoundError(
            f"{wanted!r} is not an activation; `fmits trade lifecycle` takes the "
            "id of one"
        )
    plan = store.plans.load(activation.plan_id)
    lifecycle = store.activations.state(wanted)
    history = store.activations.stop_history(
        wanted, initial_stop=plan.initial_invalidation, direction=plan.direction
    )
    fills = fills_for_activation(store, wanted)
    positions = fold_positions(fills, dust=dust)
    position: Position | Absent = (
        positions[-1] if positions else Absent("nothing has filled against this activation")
    )
    excursion, filled_legs, last_bar = _replayed(activation, plan, store, bars)
    outcome = store.activations.outcome_for(wanted)
    if outcome is not None and excursion.is_empty:
        excursion = _excursion_from(outcome)
    monitor = monitor_trade(
        activation=activation,
        direction=plan.direction,
        stop_history=history,
        view=lifecycle,
        position=position,
        excursion=excursion,
        last_bar=last_bar,
        filled_legs=filled_legs,
        at=moment,
    )
    journal = store.journals.trade_journal(ACTIVATION_SUBJECT_KIND, wanted)
    return PaperTradeView(
        activation=activation,
        plan=plan,
        lifecycle=lifecycle,
        stop_history=history,
        monitor=monitor,
        position=position,
        journal=journal,
        fills=fills,
        outcome=(
            Absent("this trade has not finished")
            if outcome is None
            else read_outcome(
                outcome,
                activation=activation,
                direction=plan.direction,
                position=position,
            )
        ),
        warnings=_warnings_for(
            activation, lifecycle, history, position, journal, at=moment
        ),
    )


def _replayed(
    activation: TradeActivation,
    plan: TradePlan,
    store: TradingStore,
    bars: tuple[PriceBar, ...],
) -> tuple[Excursion, tuple[int, ...], PriceBar | Absent]:
    """Re-derive the excursion and the rungs filled, when candles are available."""
    if not bars:
        return (
            Excursion(),
            (),
            Absent("no candles were read for this view"),
        )
    window = tuple(
        bar for bar in bars if bar.open_time >= activation.activated_at
    )
    if not window:
        return (
            Excursion(),
            (),
            Absent("no candle at or after this activation was read"),
        )
    result = replay_bars(
        run_state_for(activation, plan),
        window,
        owner_moves=owner_stop_moves(store, activation.activation_id),
    )
    return (
        result.final_state.excursion,
        result.final_state.filled_legs,
        result.last_bar,
    )


def _excursion_from(outcome: TradeOutcome) -> Excursion:
    """The frozen excursion, read back into the shape the monitor reads."""
    if isinstance(outcome.max_favourable_price, Absent):
        return Excursion()
    assert not isinstance(outcome.max_adverse_price, Absent)  # the record pairs them
    assert not isinstance(outcome.bars_held, Absent)  # and pairs both with the count
    return Excursion(
        favourable=outcome.max_favourable_price,
        adverse=outcome.max_adverse_price,
        bars=outcome.bars_held,
    )


def list_paper_trades(
    store: TradingStore,
    *,
    dust: DustPolicy,
    at: datetime,
    states: tuple[TradeLifecycleState, ...] = (),
    market: str | None = None,
    bars_by_symbol: Mapping[str, tuple[PriceBar, ...]] | None = None,
) -> tuple[PaperTradeView, ...]:
    """Every simulated trade, optionally narrowed to some states or one market.

    An empty `states` matches everything, deliberately: a filter whose default
    excludes rows is a filter that silently truncates the first listing anybody
    writes — `SearchCriteria`'s own rule, applied one layer up.

    `bars_by_symbol` is optional and changes exactly what it does on one trade:
    with candles the excursion, the mark and the bar count are re-derived, and
    without them they are `Absent` with the reason.
    """
    _require_store(store)
    views: list[PaperTradeView] = []
    for activation in store.activations.activations():
        if market is not None and market.upper() not in (
            activation.market.pair_symbol.upper(),
            activation.market.value.upper(),
        ):
            continue
        view = load_paper_trade(
            store,
            activation.activation_id,
            dust=dust,
            at=at,
            bars=(bars_by_symbol or {}).get(activation.market.pair_symbol, ()),
        )
        if states and view.state not in states:
            continue
        views.append(view)
    return tuple(views)
