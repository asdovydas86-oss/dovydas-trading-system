"""`advance(state, bar)` — one closed candle, one trade, one deterministic answer.

The whole simulator is this function. No clock, no store, no network, no model, no
prediction, no randomness: the same state and the same bar produce the same
`StepResult` forever, and a replay over a series is a fold of it.

**The order within a bar, and why it is that order.**

1. **Expiry first.** An activation whose window closed cannot be entered by the
   bar that closed it.
2. **Entry.** The condition is tested against the bar; a fill at the bar's **open**
   leaves the rest of the bar usable, and a fill at a level inside it does not.
3. **Exits, against the stop that was in force when the bar opened.** Deriving a
   trailing stop from this bar's own high and then stopping out on this bar's own
   low would be a lookahead inside a single candle — the subtlest kind, and the
   one that makes a trailing strategy look better than it was.
4. **The stop move, derived at the close and effective from the next bar.** Which
   is what a stop the owner moves at the close of a candle actually does.

**Nothing on the entry bar is inferred.** When a `LIMIT` or `STOP_ENTRY` fills at
its level rather than at the open, where price went through the remainder of that
bar is unknowable from four numbers. Two cases follow, and the second was a real
defect found by an adversarial review of the first draft:

* the bar reached **no** exit level — the exit tests are deferred by one bar and
  the step says so, which delays an answer and invents nothing;
* the bar reached the stop or a target — the trade **halts**. Deferring here
  looked symmetric, because it withheld a stop and a target alike, and it is
  not: a breakout entry fills near the top of its bar, so the level the
  remainder of that bar is most likely to reach is the stop. Skipping it
  silently would have made every stopped-out breakout survive one bar longer
  than it did, which is the flattering asymmetry this whole module is written
  against. A halt says the order is unknowable, which is what it is.

**Ambiguity halts, and is never resolved.** A bar that opens between the stop and
a target and reaches both cannot be ordered without sub-bar data this repository
does not ingest. ADR-0021 refused the identical guess for a two-sided break bar
and `AV`'s shipped `AMBIGUOUS_SAME_BAR` refused it again; this refuses it a third
time, records what could not be ordered, and stops. The owner resolves it through
the path that already exists — recording the exit they judge they would have
taken — and that exit is `ASSERTED` beside `MEASURED` fills.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from fmis.money import Quantity, canonical_decimal_text
from fmis.provenance import Absent
from fmis.snapshotting import TradeDirection
from fmis.trade_lifecycle import (
    EntryType,
    TradeActivation,
    TradeLifecycleKind,
    TradeLifecycleState,
)
from fmis.paper.fills import (
    entry_fill,
    entry_reached,
    entry_resolves_the_bar,
    reached_legs,
    stop_fill,
    stop_reached,
    target_fill,
)
from fmis.paper.models import (
    Excursion,
    Fill,
    FillKind,
    FillTrigger,
    LifecycleStep,
    PaperRefusedError,
    PriceBar,
    StepResult,
    TradeRunState,
)
from fmis.paper.stopping import derive_stop_move

__all__ = ["initial_run_state", "advance"]

_DEFERRED_NOTE = (
    "the entry filled at its level rather than at the bar's open, so where price "
    "went through the remainder of this bar is unknowable from four numbers; "
    "every exit test — the stop and every target alike — is deferred to the next "
    "bar"
)


def initial_run_state(
    activation: TradeActivation,
    *,
    direction: TradeDirection,
    initial_stop: Decimal,
    effective_stop: Decimal | None = None,
) -> TradeRunState:
    """The state a freshly activated trade starts a run in.

    A separate constructor rather than defaults on the record, so that *"a run
    begins pending, flat, with the plan's own stop and no excursion"* is written
    once and cannot be assembled differently by two callers.

    `effective_stop` differs from `initial_stop` only when a run is resumed after
    the owner has already moved the stop by hand. Both are carried because every
    R figure is measured against the **initial** one: an R multiple that shrank
    each time the stop was tightened would make good management read as a smaller
    trade.
    """
    if not isinstance(activation, TradeActivation):
        raise TypeError(
            f"activation must be a TradeActivation, got {type(activation).__name__}"
        )
    return TradeRunState(
        activation=activation,
        direction=direction,
        initial_stop=initial_stop,
        effective_stop=initial_stop if effective_stop is None else effective_stop,
        state=TradeLifecycleState.PENDING,
        remaining=Quantity.zero(activation.quantity.asset),
        excursion=Excursion(),
    )


def _require_matching_series(state: TradeRunState, bar: PriceBar) -> None:
    """A bar from the wrong series is a refusal, never a silent simulation.

    Checked here rather than trusted of the caller: a replay driving several
    activations from one cache is exactly where one symbol's candles reach
    another's run, and the failure is invisible in the result — it just produces a
    trade that behaved oddly.
    """
    expected_symbol = state.activation.market.pair_symbol
    if bar.symbol != expected_symbol:
        raise PaperRefusedError(
            f"this run simulates {expected_symbol} and was handed a bar for "
            f"{bar.symbol}"
        )
    if bar.interval != state.activation.interval:
        raise PaperRefusedError(
            f"this activation states the {state.activation.interval} interval and "
            f"was handed a {bar.interval} bar; excursions and bar counts measured "
            "across two intervals are not comparable"
        )


def advance(state: TradeRunState, bar: PriceBar) -> StepResult:
    """Advance one trade by one closed candle."""
    if not isinstance(state, TradeRunState):
        raise TypeError(f"state must be a TradeRunState, got {type(state).__name__}")
    if not isinstance(bar, PriceBar):
        raise TypeError(f"bar must be a PriceBar, got {type(bar).__name__}")
    _require_matching_series(state, bar)
    if state.state not in {
        TradeLifecycleState.PENDING,
        TradeLifecycleState.TRIGGERED,
        TradeLifecycleState.OPEN,
        TradeLifecycleState.PARTIALLY_EXITED,
    }:
        raise PaperRefusedError(
            f"a trade in state {state.state.value} is not waiting for a bar; "
            "advancing it would append an event the lifecycle table forbids"
        )
    if not isinstance(state.last_bar_time, Absent) and (
        bar.open_time <= state.last_bar_time
    ):
        raise PaperRefusedError(
            f"the bar opening {bar.open_time.isoformat()} does not follow the last "
            f"one advanced ({state.last_bar_time.isoformat()}); a run replays "
            "history forwards, and re-reading a bar would double-count its "
            "excursion"
        )

    steps: list[LifecycleStep] = []
    working = replace(state, last_bar_time=bar.open_time)

    expired = _apply_expiry(working, bar, steps)
    if expired is not None:
        return StepResult(bar=bar, next_state=expired, steps=tuple(steps))

    working, entered_this_bar, exits_available = _apply_entry(working, bar, steps)

    if working.state in {
        TradeLifecycleState.OPEN,
        TradeLifecycleState.PARTIALLY_EXITED,
    }:
        if not entered_this_bar:
            working = replace(
                working, excursion=working.excursion.extended(bar, working.direction)
            )
        if exits_available:
            working = _apply_exits(working, bar, steps)
        elif _reaches_an_exit(working, bar):
            steps.append(
                LifecycleStep(
                    kind=TradeLifecycleKind.AMBIGUOUS_BAR,
                    bar_sequence=len(steps),
                    note=_entry_bar_ambiguity_note(working, bar),
                )
            )
            working = replace(working, state=TradeLifecycleState.AMBIGUOUS)

    stop_move: object = Absent("no rule moved the stop on this bar")
    if working.state in {
        TradeLifecycleState.OPEN,
        TradeLifecycleState.PARTIALLY_EXITED,
    }:
        working, stop_move = _apply_stop_rules(working, steps)

    return StepResult(
        bar=bar,
        next_state=working,
        steps=tuple(steps),
        stop_move=stop_move,  # type: ignore[arg-type]
    )


def _apply_expiry(
    state: TradeRunState, bar: PriceBar, steps: list[LifecycleStep]
) -> TradeRunState | None:
    """`None` when nothing expired, so the caller's happy path stays unindented."""
    if state.state not in {
        TradeLifecycleState.PENDING,
        TradeLifecycleState.TRIGGERED,
    }:
        return None
    if not state.activation.is_expired_at(bar.open_time):
        return None
    steps.append(
        LifecycleStep(
            kind=TradeLifecycleKind.EXPIRED,
            bar_sequence=len(steps),
            note=(
                "the activation's window closed before this bar opened, so no "
                "entry on it could have been taken"
            ),
        )
    )
    return replace(state, state=TradeLifecycleState.EXPIRED)


def _apply_entry(
    state: TradeRunState, bar: PriceBar, steps: list[LifecycleStep]
) -> tuple[TradeRunState, bool, bool]:
    """`(state, entered_on_this_bar, exits_may_be_tested_on_this_bar)`."""
    if state.state is TradeLifecycleState.PENDING:
        if not entry_reached(state.activation, state.direction, bar):
            return state, False, False
        steps.append(
            LifecycleStep(
                kind=TradeLifecycleKind.ENTRY_TRIGGERED, bar_sequence=len(steps)
            )
        )
        price, gapped = entry_fill(state.activation, state.direction, bar)
        resolves = entry_resolves_the_bar(price, bar)
        trigger = (
            FillTrigger.MARKET_OPEN
            if state.activation.entry_type is EntryType.MARKET
            else FillTrigger.ENTRY_LEVEL
        )
        return (
            _record_entry(state, bar, steps, price, gapped, trigger, resolves),
            True,
            resolves,
        )
    if state.state is TradeLifecycleState.TRIGGERED:
        # The engine emits the trigger and the fill on one bar, so this state is
        # only reachable when a run was interrupted between the two writes. The
        # earliest price available after a recorded trigger is this bar's open,
        # and filling there is the honest recovery rather than a re-test of a
        # condition the stream already says was met.
        return (
            _record_entry(
                state, bar, steps, bar.open, False, FillTrigger.MARKET_OPEN, True
            ),
            True,
            True,
        )
    return state, False, True


def _record_entry(
    state: TradeRunState,
    bar: PriceBar,
    steps: list[LifecycleStep],
    price: Decimal,
    gapped: bool,
    trigger: FillTrigger,
    resolves: bool,
) -> TradeRunState:
    quantity = state.activation.quantity
    steps.append(
        LifecycleStep(
            kind=TradeLifecycleKind.ENTRY_FILLED,
            bar_sequence=len(steps),
            fill=Fill(
                kind=FillKind.ENTRY,
                trigger=trigger,
                at=bar.open_time,
                price=price,
                quantity=quantity,
                gapped=gapped,
            ),
            note=Absent("no note") if resolves else _DEFERRED_NOTE,
        )
    )
    return replace(
        state,
        state=TradeLifecycleState.OPEN,
        remaining=quantity,
        entry_price=price,
        opened_at=bar.open_time,
        excursion=state.excursion.extended(bar, state.direction),
    )


def _reaches_an_exit(state: TradeRunState, bar: PriceBar) -> bool:
    """Whether this bar reached the stop or any unfilled rung of the ladder."""
    if stop_reached(state.direction, bar, state.effective_stop):
        return True
    return bool(
        reached_legs(
            state.activation, state.direction, bar, already_filled=state.filled_legs
        )
    )


def _entry_bar_ambiguity_note(state: TradeRunState, bar: PriceBar) -> str:
    return (
        f"the entry filled at its level inside the bar opening "
        f"{bar.open_time.isoformat()}, and that same bar reached an exit level. "
        "Whether price passed the entry before or after the exit is unknowable "
        "without sub-bar data this system does not ingest, so no fill is "
        "invented and this trade stops here. Record the exit you judge you "
        "would have taken to resolve it"
    )


def _apply_exits(
    state: TradeRunState, bar: PriceBar, steps: list[LifecycleStep]
) -> TradeRunState:
    direction = state.direction
    stop = state.effective_stop

    if bar.opened_beyond(direction, stop, favourable=False):
        # The stop was reached at the first price of the bar. Nothing inside the
        # bar can have preceded it, so this is determined rather than assumed —
        # and no target on the far side can have filled first.
        return _record_exit(state, bar, steps, *stop_fill(direction, bar, stop))

    reached = reached_legs(
        state.activation, direction, bar, already_filled=state.filled_legs
    )
    at_open = tuple(
        index
        for index in reached
        if bar.opened_beyond(
            direction, state.activation.ladder.legs[index].target, favourable=True
        )
    )
    intrabar = tuple(index for index in reached if index not in at_open)

    working = state
    for index in at_open:
        working = _record_leg(working, bar, steps, index)
        if working.state is TradeLifecycleState.CLOSED:
            return working

    hit_stop = stop_reached(direction, bar, stop)
    if hit_stop and intrabar:
        steps.append(
            LifecycleStep(
                kind=TradeLifecycleKind.AMBIGUOUS_BAR,
                bar_sequence=len(steps),
                note=_ambiguity_note(working, bar, intrabar),
            )
        )
        return replace(working, state=TradeLifecycleState.AMBIGUOUS)
    if hit_stop:
        return _record_exit(working, bar, steps, *stop_fill(direction, bar, stop))
    for index in intrabar:
        working = _record_leg(working, bar, steps, index)
        if working.state is TradeLifecycleState.CLOSED:
            return working
    return working


def _ambiguity_note(
    state: TradeRunState, bar: PriceBar, legs: tuple[int, ...]
) -> str:
    targets = ", ".join(
        canonical_decimal_text(state.activation.ladder.legs[index].target)
        for index in legs
    )
    return (
        f"the bar opening {bar.open_time.isoformat()} reached both the stop at "
        f"{canonical_decimal_text(state.effective_stop)} and the target(s) at "
        f"{targets}, and opened between them. Which came first is unknowable "
        "without sub-bar data this system does not ingest, so no fill is invented "
        "and this trade stops here. Record the exit you judge you would have taken "
        "to resolve it"
    )


def _record_leg(
    state: TradeRunState, bar: PriceBar, steps: list[LifecycleStep], index: int
) -> TradeRunState:
    price, gapped = target_fill(
        state.activation, state.direction, bar, leg_index=index
    )
    taking = state.activation.leg_quantity(index)
    if taking > state.remaining:
        raise PaperRefusedError(
            f"rung {index + 1} takes {taking} and only {state.remaining} is open; "
            "a ladder's shares are of the activated size and cannot exceed it"
        )
    left = state.remaining - taking
    closing = left.is_zero
    steps.append(
        LifecycleStep(
            kind=(
                TradeLifecycleKind.EXIT_FILLED
                if closing
                else TradeLifecycleKind.PARTIAL_EXIT_FILLED
            ),
            bar_sequence=len(steps),
            fill=Fill(
                kind=FillKind.EXIT if closing else FillKind.PARTIAL_EXIT,
                trigger=FillTrigger.TARGET_LEVEL,
                at=bar.open_time,
                price=price,
                quantity=taking,
                gapped=gapped,
                leg_index=index,
            ),
        )
    )
    return replace(
        state,
        state=(
            TradeLifecycleState.CLOSED
            if closing
            else TradeLifecycleState.PARTIALLY_EXITED
        ),
        remaining=left,
        filled_legs=state.filled_legs + (index,),
    )


def _record_exit(
    state: TradeRunState,
    bar: PriceBar,
    steps: list[LifecycleStep],
    price: Decimal,
    gapped: bool,
) -> TradeRunState:
    steps.append(
        LifecycleStep(
            kind=TradeLifecycleKind.EXIT_FILLED,
            bar_sequence=len(steps),
            fill=Fill(
                kind=FillKind.EXIT,
                trigger=FillTrigger.STOP_LEVEL,
                at=bar.open_time,
                price=price,
                quantity=state.remaining,
                gapped=gapped,
            ),
        )
    )
    return replace(
        state,
        state=TradeLifecycleState.CLOSED,
        remaining=Quantity.zero(state.remaining.asset),
    )


def _apply_stop_rules(
    state: TradeRunState, steps: list[LifecycleStep]
) -> tuple[TradeRunState, object]:
    """Derive at most one stop move, effective from the **next** bar."""
    if state.activation.stop_management.is_manual:
        return state, Absent("this activation enabled no automatic stop rule")
    distance = state.risk_distance
    if isinstance(distance, Absent):
        return state, distance
    entry = state.entry_price
    assert not isinstance(entry, Absent)  # a positive risk distance proved it
    move = derive_stop_move(
        state.activation.stop_management,
        state.direction,
        entry_price=entry,
        risk_distance=distance,
        effective_stop=state.effective_stop,
        excursion=state.excursion,
    )
    if isinstance(move, Absent):
        return state, move
    steps.append(
        LifecycleStep(
            kind=TradeLifecycleKind.STOP_AMENDED,
            bar_sequence=len(steps),
            note=(
                f"{move.term_id}: {canonical_decimal_text(move.previous_stop)} → "
                f"{canonical_decimal_text(move.new_stop)}, effective from the next "
                "bar"
            ),
        )
    )
    return replace(state, effective_stop=move.new_stop), move
