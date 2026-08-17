"""Milestone BO — the simulator itself: entries, exits, gaps, and the refusals.

Every test here is a scenario over hand-built bars. There is no network, no
store, no clock and no randomness, and the assertions are about **what the engine
refused to decide** at least as often as about what it decided.

Four refusals carry the milestone, and each has its own test:

1. no intrabar path is invented;
2. the bar's **open** resolves what it genuinely can, and nothing more;
3. everything still ambiguous **halts** rather than resolving to a side;
4. a level that filled inside a bar defers every exit test — the stop and the
   target **equally**, which is what makes the deferral honest rather than
   merely cautious.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fmis.money import AssetCode, Quantity
from fmis.provenance import Absent
from fmis.trade_lifecycle import EntryType, ExitLadder, ExitLeg, TradeLifecycleKind, TradeLifecycleState
from fmis.paper import (
    Excursion,
    FillKind,
    FillTrigger,
    PaperRefusedError,
    PriceBar,
    advance,
    initial_run_state,
    replay_bars,
)
from paper_helpers import (
    activation,
    at,
    bar,
    break_even,
    market_activation,
    plan,
    short_plan,
    trailing,
)


def run(subject, committed, bars, **kwargs):
    return replay_bars(
        initial_run_state(
            subject,
            direction=committed.direction,
            initial_stop=committed.initial_invalidation,
        ),
        bars,
        **kwargs,
    )


def kinds(result):
    return [step.kind for step in result.steps]


# --------------------------------------------------------------------------
# Entries
# --------------------------------------------------------------------------


def test_a_market_entry_fills_at_the_next_bars_open_and_never_at_a_past_close() -> None:
    """That close had already happened when the decision was made; filling at it
    would be a lookahead of exactly one bar dressed up as realism."""
    committed = plan()
    result = run(market_activation(committed), committed, [bar(0, "98", "99", "97", "98")])
    fill = result.fills[0]
    assert fill.trigger is FillTrigger.MARKET_OPEN
    assert fill.price == Decimal("98")
    assert not fill.gapped


def test_a_bar_that_opened_before_the_activation_does_not_fill_it() -> None:
    committed = plan()
    subject = market_activation(committed, activated_at=at(2))
    result = run(subject, committed, [bar(1, "98", "99", "97", "98")])
    assert result.final_state.state is TradeLifecycleState.PENDING
    assert not result.changed


def test_a_stop_entry_fills_at_its_level_when_the_bar_reached_it_intrabar() -> None:
    committed = plan()
    result = run(activation(committed), committed, [bar(0, "99", "101", "98", "100")])
    fill = result.fills[0]
    assert fill.price == Decimal("100")
    assert not fill.gapped
    assert fill.trigger is FillTrigger.ENTRY_LEVEL


def test_a_stop_entry_that_gapped_through_fills_worse_at_the_open() -> None:
    committed = plan()
    result = run(activation(committed), committed, [bar(0, "104", "106", "103", "105")])
    fill = result.fills[0]
    assert fill.price == Decimal("104")
    assert fill.gapped


def test_a_limit_entry_that_gapped_through_fills_better_at_the_open() -> None:
    """The same two lines produce the favourable gap and the unfavourable one.
    Rounding the asymmetry toward the owner is how a paper record flatters
    itself, and writing the rule once makes it impossible here."""
    committed = plan()
    subject = activation(
        committed,
        entry_type=EntryType.LIMIT,
        entry_price=Decimal("100"),
    )
    result = run(subject, committed, [bar(0, "97", "99", "96", "98")])
    fill = result.fills[0]
    assert fill.price == Decimal("97")
    assert fill.gapped


def test_the_entry_is_mirrored_for_the_other_side() -> None:
    committed = short_plan()
    subject = activation(committed, entry_price=Decimal("100"))
    result = run(subject, committed, [bar(0, "101", "102", "99", "100")])
    assert result.fills[0].price == Decimal("100")
    assert result.final_state.state is TradeLifecycleState.OPEN


def test_the_trigger_and_the_fill_are_two_events_on_one_bar() -> None:
    """*The condition was met* and *the fill happened* are different facts, and
    merging them makes the delay between them unmeasurable."""
    committed = plan()
    result = run(activation(committed), committed, [bar(0, "99", "101", "98", "100")])
    assert kinds(result) == [
        TradeLifecycleKind.ENTRY_TRIGGERED,
        TradeLifecycleKind.ENTRY_FILLED,
    ]
    assert [step.bar_sequence for step in result.steps] == [0, 1]


# --------------------------------------------------------------------------
# Exits
# --------------------------------------------------------------------------


def test_the_ladder_takes_shares_of_the_activated_size_in_order() -> None:
    committed = plan()
    result = run(
        activation(committed),
        committed,
        [
            bar(0, "100", "100", "100", "100"),
            bar(1, "100", "112", "99", "111"),
            bar(2, "111", "121", "110", "120"),
        ],
    )
    exits = [fill for fill in result.fills if not fill.is_entry]
    assert [fill.kind for fill in exits] == [FillKind.PARTIAL_EXIT, FillKind.EXIT]
    assert [fill.price for fill in exits] == [Decimal("110"), Decimal("120")]
    assert result.final_state.state is TradeLifecycleState.CLOSED
    assert result.final_state.remaining.is_zero


def test_two_rungs_on_one_bar_fill_nearest_first() -> None:
    """Price cannot pass the further rung without passing the nearer one, so the
    sequence is derived from geometry rather than assumed."""
    committed = plan()
    result = run(
        activation(committed),
        committed,
        [bar(0, "100", "100", "100", "100"), bar(1, "100", "125", "99", "124")],
    )
    exits = [fill for fill in result.fills if not fill.is_entry]
    assert [fill.leg_index for fill in exits] == [0, 1]
    assert [fill.price for fill in exits] == [Decimal("110"), Decimal("120")]


def test_a_runner_is_left_when_the_ladder_takes_less_than_the_whole_position() -> None:
    committed = plan()
    subject = activation(
        committed,
        ladder=ExitLadder(
            legs=(ExitLeg(target=Decimal("110"), fraction=Decimal("0.5")),)
        ),
    )
    result = run(
        subject,
        committed,
        [bar(0, "100", "100", "100", "100"), bar(1, "100", "112", "99", "111")],
    )
    assert result.final_state.state is TradeLifecycleState.PARTIALLY_EXITED
    assert result.final_state.remaining == Quantity(Decimal("0.5"), AssetCode("BTC"))


def test_a_stop_closes_the_whole_remaining_position() -> None:
    committed = plan()
    result = run(
        activation(committed),
        committed,
        [
            bar(0, "100", "100", "100", "100"),
            bar(1, "100", "112", "99", "111"),
            bar(2, "111", "112", "94", "95"),
        ],
    )
    last = result.fills[-1]
    assert last.trigger is FillTrigger.STOP_LEVEL
    assert last.price == Decimal("95")
    assert result.final_state.state is TradeLifecycleState.CLOSED


def test_a_stop_that_gapped_through_fills_worse_at_the_open() -> None:
    committed = plan()
    result = run(
        activation(committed),
        committed,
        [bar(0, "100", "100", "100", "100"), bar(1, "90", "92", "88", "89")],
    )
    last = result.fills[-1]
    assert last.price == Decimal("90")
    assert last.gapped


# --------------------------------------------------------------------------
# The four refusals
# --------------------------------------------------------------------------


def test_a_bar_that_opens_beyond_the_stop_resolves_it_without_a_guess() -> None:
    """The one piece of intrabar ordering four numbers actually contain: the
    open is the first price of the bar, so no target inside it can have come
    first."""
    committed = plan()
    result = run(
        activation(committed),
        committed,
        [bar(0, "100", "100", "100", "100"), bar(1, "94", "125", "93", "124")],
    )
    assert result.final_state.state is TradeLifecycleState.CLOSED
    assert result.fills[-1].trigger is FillTrigger.STOP_LEVEL
    assert result.fills[-1].price == Decimal("94")


def test_a_bar_that_opens_beyond_a_target_fills_that_rung_at_the_open() -> None:
    committed = plan()
    result = run(
        activation(committed),
        committed,
        [bar(0, "100", "100", "100", "100"), bar(1, "112", "115", "111", "114")],
    )
    partial = result.fills[-1]
    assert partial.price == Decimal("112")
    assert partial.gapped


def test_a_bar_reaching_both_levels_from_between_them_halts_the_trade() -> None:
    committed = plan()
    result = run(
        activation(committed),
        committed,
        [bar(0, "100", "100", "100", "100"), bar(1, "100", "115", "94", "96")],
    )
    assert result.halted
    assert result.final_state.state is TradeLifecycleState.AMBIGUOUS
    assert kinds(result.results[-1])[-1] is TradeLifecycleKind.AMBIGUOUS_BAR
    note = result.results[-1].steps[-1].note
    assert "unknowable" in note
    assert "95" in note and "110" in note


def test_a_halted_trade_invents_no_fill_and_keeps_its_exposure() -> None:
    committed = plan()
    result = run(
        activation(committed),
        committed,
        [bar(0, "100", "100", "100", "100"), bar(1, "100", "115", "94", "96")],
    )
    assert [fill.kind for fill in result.fills] == [FillKind.ENTRY]
    assert result.final_state.remaining == Quantity(Decimal("1"), AssetCode("BTC"))


def test_a_replay_stops_rather_than_advancing_past_a_halt() -> None:
    committed = plan()
    result = run(
        activation(committed),
        committed,
        [
            bar(0, "100", "100", "100", "100"),
            bar(1, "100", "115", "94", "96"),
            bar(2, "96", "130", "95", "129"),
        ],
    )
    assert result.bars_advanced == 2


def test_an_entry_that_filled_inside_a_quiet_bar_defers_its_exit_tests() -> None:
    """No exit level was reached, so deferring delays an answer and invents
    nothing."""
    committed = plan()
    result = run(
        activation(committed),
        committed,
        [bar(0, "99", "105", "97", "104")],
    )
    assert kinds(result.results[0]) == [
        TradeLifecycleKind.ENTRY_TRIGGERED,
        TradeLifecycleKind.ENTRY_FILLED,
    ]
    assert result.final_state.state is TradeLifecycleState.OPEN
    assert "deferred to the next bar" in result.results[0].steps[1].note


def test_an_entry_bar_that_also_reached_an_exit_level_halts_the_trade() -> None:
    """Found by an adversarial review of the first draft, which deferred here.

    Deferring looked symmetric — it withheld a stop and a target alike — and is
    not: a breakout entry fills near the top of its bar, so the level the rest
    of that bar is most likely to reach is the **stop**. Skipping it silently
    made every stopped-out breakout survive a bar longer than it did.
    """
    committed = plan()
    result = run(
        activation(committed),
        committed,
        [bar(0, "99", "125", "94", "124")],
    )
    assert kinds(result.results[0]) == [
        TradeLifecycleKind.ENTRY_TRIGGERED,
        TradeLifecycleKind.ENTRY_FILLED,
        TradeLifecycleKind.AMBIGUOUS_BAR,
    ]
    assert result.final_state.state is TradeLifecycleState.AMBIGUOUS
    assert "before or after the exit" in result.results[0].steps[2].note


def test_the_entry_bar_halt_fires_for_a_target_as_readily_as_for_a_stop() -> None:
    """Symmetric by construction: one test for both levels, one code path."""
    committed = plan()
    stopped = run(
        activation(committed), committed, [bar(0, "99", "101", "94", "96")]
    )
    reached = run(
        activation(committed), committed, [bar(0, "99", "112", "98", "111")]
    )
    assert stopped.final_state.state is TradeLifecycleState.AMBIGUOUS
    assert reached.final_state.state is TradeLifecycleState.AMBIGUOUS


def test_an_entry_that_filled_at_the_open_leaves_the_rest_of_the_bar_usable() -> None:
    committed = plan()
    result = run(
        market_activation(committed),
        committed,
        [bar(0, "100", "112", "99", "111")],
    )
    assert TradeLifecycleKind.PARTIAL_EXIT_FILLED in kinds(result.results[0])


# --------------------------------------------------------------------------
# Expiry and cancellation
# --------------------------------------------------------------------------


def test_an_activation_whose_window_closed_cannot_be_entered_by_the_bar_that_closed_it() -> None:
    committed = plan()
    subject = activation(committed, expires_at=at(1))
    result = run(subject, committed, [bar(1, "99", "101", "98", "100")])
    assert kinds(result.results[0]) == [TradeLifecycleKind.EXPIRED]
    assert result.final_state.state is TradeLifecycleState.EXPIRED
    assert not result.fills


def test_an_open_position_is_not_expired_by_its_activations_window() -> None:
    committed = plan()
    subject = activation(committed, expires_at=at(3))
    result = run(
        subject,
        committed,
        [bar(0, "99", "101", "98", "100"), bar(4, "100", "101", "99", "100")],
    )
    assert result.final_state.state is TradeLifecycleState.OPEN


# --------------------------------------------------------------------------
# Stop rules
# --------------------------------------------------------------------------


def test_break_even_moves_the_stop_to_the_entry_and_only_from_the_next_bar() -> None:
    """Deriving a stop from this bar's high and then stopping out on this bar's
    low would be a lookahead inside one candle."""
    committed = plan()
    subject = activation(committed, stop_management=break_even())
    result = run(
        subject,
        committed,
        [bar(0, "100", "100", "100", "100"), bar(1, "100", "106", "94", "105")],
    )
    # The stop was still 95 when this bar's exits were tested, so a low of 94
    # closed the trade — and the amendment is not recorded on a closed trade.
    assert result.final_state.state is TradeLifecycleState.CLOSED
    assert result.final_state.effective_stop == Decimal("95")


def test_break_even_takes_effect_on_the_bar_after_it_fires() -> None:
    committed = plan()
    subject = activation(committed, stop_management=break_even())
    result = run(
        subject,
        committed,
        [
            bar(0, "100", "100", "100", "100"),
            bar(1, "100", "106", "99", "105"),
            bar(2, "105", "106", "99", "100"),
        ],
    )
    assert result.results[1].next_state.effective_stop == Decimal("100")
    assert result.final_state.state is TradeLifecycleState.CLOSED
    assert result.fills[-1].price == Decimal("100")


def test_a_trail_follows_the_excursion_the_outcome_will_freeze() -> None:
    committed = plan()
    subject = activation(committed, stop_management=trailing("1"))
    result = run(
        subject,
        committed,
        [bar(0, "100", "100", "100", "100"), bar(1, "100", "108", "99", "107")],
    )
    # MFE 108, risk distance 5, trail 1R behind → 103.
    assert result.results[1].next_state.effective_stop == Decimal("103")


def test_at_most_one_stop_move_is_recorded_per_bar() -> None:
    """Two amendments on one candle would give the history two entries for one
    decision, and the widening counter would start counting rules."""
    from fmis.trade_lifecycle import BreakEvenRule, StopManagement, TrailingRule

    committed = plan()
    subject = activation(
        committed,
        stop_management=StopManagement(
            break_even=BreakEvenRule(trigger_r=Decimal("1")),
            trailing=TrailingRule(distance_r=Decimal("1")),
        ),
    )
    result = run(
        subject,
        committed,
        [bar(0, "100", "100", "100", "100"), bar(1, "100", "108", "99", "107")],
    )
    moves = [
        step for step in result.steps if step.kind is TradeLifecycleKind.STOP_AMENDED
    ]
    assert len(moves) == 1


def test_a_manual_activation_derives_no_stop_move_at_all() -> None:
    committed = plan()
    result = run(
        activation(committed),
        committed,
        [bar(0, "100", "100", "100", "100"), bar(1, "100", "125", "99", "124")],
    )
    assert not [
        step for step in result.steps if step.kind is TradeLifecycleKind.STOP_AMENDED
    ]


def test_an_owner_move_is_applied_to_the_run_and_emits_nothing() -> None:
    """The record exists; a replay that wrote it again would count one decision
    twice in the widening metric."""
    committed = plan()
    result = run(
        activation(committed),
        committed,
        [
            bar(0, "100", "100", "100", "100"),
            bar(1, "100", "101", "99", "100"),
            bar(2, "100", "101", "97", "98"),
        ],
        owner_moves=((at(2), Decimal("98")),),
    )
    assert result.final_state.state is TradeLifecycleState.CLOSED
    assert result.fills[-1].price == Decimal("98")
    assert not [
        step for step in result.steps if step.kind is TradeLifecycleKind.STOP_AMENDED
    ]


# --------------------------------------------------------------------------
# Determinism and refusals of the engine itself
# --------------------------------------------------------------------------


def test_the_same_bars_produce_the_same_answer_twice() -> None:
    committed = plan()
    bars = [
        bar(0, "99", "101", "98", "100"),
        bar(1, "100", "112", "99", "111"),
        bar(2, "111", "121", "110", "120"),
    ]
    first = run(activation(committed), committed, bars)
    second = run(activation(committed), committed, bars)
    assert [
        (fill.kind, fill.price, fill.quantity, fill.at) for fill in first.fills
    ] == [(fill.kind, fill.price, fill.quantity, fill.at) for fill in second.fills]
    assert first.final_state.state is second.final_state.state


def test_a_bar_from_another_market_is_refused() -> None:
    committed = plan()
    state = initial_run_state(
        activation(committed),
        direction=committed.direction,
        initial_stop=committed.initial_invalidation,
    )
    with pytest.raises(PaperRefusedError, match="handed a bar for"):
        advance(state, bar(0, "99", "101", "98", "100", symbol="ETHUSDT"))


def test_a_bar_on_another_interval_is_refused() -> None:
    committed = plan()
    state = initial_run_state(
        activation(committed),
        direction=committed.direction,
        initial_stop=committed.initial_invalidation,
    )
    with pytest.raises(PaperRefusedError, match="not comparable"):
        advance(state, bar(0, "99", "101", "98", "100", interval="4h"))


def test_a_bar_that_does_not_follow_the_last_one_is_refused() -> None:
    committed = plan()
    result = run(activation(committed), committed, [bar(1, "99", "101", "98", "100")])
    with pytest.raises(PaperRefusedError, match="does not follow"):
        advance(result.final_state, bar(0, "99", "101", "98", "100"))


def test_the_same_bar_advanced_twice_is_refused() -> None:
    """Found by a mutation probe. Re-reading one candle would double-count its
    excursion, and an MFE inflated by a re-run is a figure nobody could
    reconcile against the candles it came from."""
    committed = plan()
    result = run(activation(committed), committed, [bar(1, "99", "101", "98", "100")])
    with pytest.raises(PaperRefusedError, match="does not follow"):
        advance(result.final_state, bar(1, "99", "101", "98", "100"))


def test_a_finished_trade_is_not_waiting_for_a_bar() -> None:
    committed = plan()
    result = run(
        activation(committed),
        committed,
        [bar(0, "100", "100", "100", "100"), bar(1, "100", "125", "99", "124")],
    )
    with pytest.raises(PaperRefusedError, match="not waiting for a bar"):
        advance(result.final_state, bar(2, "124", "125", "123", "124"))


def test_a_bar_that_changes_nothing_still_costs_a_step() -> None:
    """*'The engine looked and had nothing to say'* and *'the engine never saw
    it'* stay different facts."""
    committed = plan()
    result = run(activation(committed), committed, [bar(0, "98", "99", "97", "98")])
    assert result.bars_advanced == 1
    assert not result.changed
    assert result.results[0].steps == ()


def test_the_excursion_accumulates_only_while_exposure_exists() -> None:
    committed = plan()
    result = run(
        activation(committed),
        committed,
        [
            bar(0, "98", "99", "90", "98"),
            bar(1, "99", "101", "98", "100"),
            bar(2, "100", "106", "99", "105"),
        ],
    )
    excursion = result.final_state.excursion
    assert excursion.bars == 2
    assert excursion.favourable == Decimal("106")
    assert excursion.adverse == Decimal("98")


def test_an_excursion_states_both_extremes_or_neither() -> None:
    with pytest.raises(PaperRefusedError, match="both extremes or neither"):
        Excursion(favourable=Decimal("110"), bars=1)


def test_a_run_state_refuses_a_negative_remaining_size() -> None:
    from fmis.paper import TradeRunState

    committed = plan()
    with pytest.raises(PaperRefusedError, match="cannot be negative"):
        TradeRunState(
            activation=activation(committed),
            direction=committed.direction,
            initial_stop=Decimal("95"),
            effective_stop=Decimal("95"),
            state=TradeLifecycleState.OPEN,
            remaining=Quantity(Decimal("-1"), AssetCode("BTC")),
            excursion=Excursion(),
        )


def test_the_risk_distance_is_measured_against_the_initial_stop() -> None:
    """An R multiple that shrank each time the stop was tightened would make
    good management read as a smaller trade."""
    committed = plan()
    result = run(
        activation(committed, stop_management=break_even()),
        committed,
        [
            bar(0, "100", "100", "100", "100"),
            bar(1, "100", "106", "99", "105"),
            bar(2, "105", "107", "104", "106"),
        ],
    )
    assert result.final_state.effective_stop == Decimal("100")
    assert result.final_state.risk_distance == Decimal("5")


def test_a_transposed_entry_leaves_no_risk_distance_rather_than_a_magnitude() -> None:
    committed = plan(initial_invalidation=Decimal("105"), targets=(Decimal("120"),))
    subject = activation(
        committed,
        entry_price=Decimal("100"),
        ladder=ExitLadder(
            legs=(ExitLeg(target=Decimal("120"), fraction=Decimal("1")),)
        ),
    )
    result = run(subject, committed, [bar(0, "99", "101", "98", "100")])
    distance = result.final_state.risk_distance
    assert isinstance(distance, Absent)
    assert "far side of the initial stop" in distance.reason


def test_a_replay_over_no_bars_is_a_result_and_not_a_failure() -> None:
    committed = plan()
    result = run(activation(committed), committed, [])
    assert result.bars_advanced == 0
    assert isinstance(result.last_bar, Absent)
    assert result.final_state.state is TradeLifecycleState.PENDING
