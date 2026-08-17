"""Milestone BO — the fill arithmetic and the two stop rules, in isolation.

The engine's scenarios exercise these through a replay; these exercise them
directly, so a failure names the rule rather than the scenario. Every case is
run on both sides where a side exists: an asymmetry between them is the failure
mode that makes a portfolio's worst-managed trade look like its best-sized one.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fmis.provenance import Absent
from fmis.snapshotting import TradeDirection
from fmis.trade_lifecycle import BreakEvenRule, EntryType, StopManagement, TrailingRule
from fmis.paper import (
    ENTRY_IS_FAVOURABLE,
    Excursion,
    PaperRefusedError,
    break_even_stop,
    derive_stop_move,
    entry_fill,
    entry_level_of,
    entry_reached,
    entry_resolves_the_bar,
    fill_at_level,
    reached_legs,
    stop_fill,
    stop_reached,
    target_fill,
    trailing_stop,
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

LONG = TradeDirection.LONG
SHORT = TradeDirection.SHORT


# --------------------------------------------------------------------------
# The level rule
# --------------------------------------------------------------------------


def test_a_level_the_bar_did_not_reach_has_no_fill_price() -> None:
    """Producing a price for a level price never touched is the one failure
    this module exists to prevent."""
    with pytest.raises(PaperRefusedError, match="did not reach the level"):
        fill_at_level(LONG, bar(0, "99", "100", "98", "99"), Decimal("110"), favourable=True)


def test_a_level_reached_intrabar_fills_at_the_level() -> None:
    price, gapped = fill_at_level(
        LONG, bar(0, "99", "111", "98", "110"), Decimal("110"), favourable=True
    )
    assert price == Decimal("110")
    assert not gapped


def test_a_level_the_bar_opened_beyond_fills_at_the_open() -> None:
    price, gapped = fill_at_level(
        LONG, bar(0, "112", "115", "111", "114"), Decimal("110"), favourable=True
    )
    assert price == Decimal("112")
    assert gapped


def test_the_gap_rule_is_the_same_two_lines_on_both_sides() -> None:
    favourable = fill_at_level(
        LONG, bar(0, "112", "115", "111", "114"), Decimal("110"), favourable=True
    )
    adverse = fill_at_level(
        LONG, bar(0, "90", "92", "88", "89"), Decimal("95"), favourable=False
    )
    assert favourable[1] is adverse[1] is True
    assert favourable[0] == Decimal("112")
    assert adverse[0] == Decimal("90")


def test_the_level_rule_is_mirrored_for_the_other_side() -> None:
    price, gapped = fill_at_level(
        SHORT, bar(0, "88", "89", "85", "86"), Decimal("90"), favourable=True
    )
    assert price == Decimal("88")
    assert gapped


# --------------------------------------------------------------------------
# Entries
# --------------------------------------------------------------------------


def test_which_side_each_entry_type_waits_on_is_stated_in_one_table() -> None:
    assert ENTRY_IS_FAVOURABLE == {
        EntryType.LIMIT: False,
        EntryType.STOP_ENTRY: True,
    }


def test_a_market_entry_names_no_level_and_a_stop_entry_does() -> None:
    assert isinstance(entry_level_of(market_activation()), Absent)
    assert entry_level_of(activation()) == Decimal("100")


def test_a_market_entry_is_met_by_the_first_bar_at_or_after_the_activation() -> None:
    subject = market_activation(activated_at=at(2))
    assert not entry_reached(subject, LONG, bar(1, "99", "101", "98", "100"))
    assert entry_reached(subject, LONG, bar(2, "99", "101", "98", "100"))


def test_a_stop_entry_is_met_by_a_bar_that_reached_its_level() -> None:
    subject = activation()
    assert not entry_reached(subject, LONG, bar(0, "97", "99", "96", "98"))
    assert entry_reached(subject, LONG, bar(0, "99", "101", "98", "100"))


def test_a_limit_entry_is_met_from_the_other_side() -> None:
    subject = activation(entry_type=EntryType.LIMIT, entry_price=Decimal("100"))
    assert not entry_reached(subject, LONG, bar(0, "101", "103", "101", "102"))
    assert entry_reached(subject, LONG, bar(0, "101", "103", "99", "102"))


def test_an_entry_the_bar_did_not_meet_has_no_fill() -> None:
    with pytest.raises(PaperRefusedError, match="did not meet the entry"):
        entry_fill(activation(), LONG, bar(0, "97", "99", "96", "98"))


def test_an_entry_at_the_open_leaves_the_rest_of_the_bar_usable() -> None:
    candle = bar(0, "104", "106", "103", "105")
    price, _ = entry_fill(activation(), LONG, candle)
    assert entry_resolves_the_bar(price, candle)
    inside = bar(0, "99", "101", "98", "100")
    price, _ = entry_fill(activation(), LONG, inside)
    assert not entry_resolves_the_bar(price, inside)


# --------------------------------------------------------------------------
# Exits
# --------------------------------------------------------------------------


def test_a_stop_is_reached_on_the_adverse_side_and_fills_worse_on_a_gap() -> None:
    assert stop_reached(LONG, bar(0, "100", "101", "94", "96"), Decimal("95"))
    assert not stop_reached(LONG, bar(0, "100", "101", "96", "97"), Decimal("95"))
    assert stop_fill(LONG, bar(0, "90", "92", "88", "89"), Decimal("95")) == (
        Decimal("90"),
        True,
    )


def test_the_stop_rule_is_mirrored_for_the_other_side() -> None:
    assert stop_reached(SHORT, bar(0, "100", "106", "99", "104"), Decimal("105"))
    assert stop_fill(SHORT, bar(0, "110", "112", "108", "109"), Decimal("105")) == (
        Decimal("110"),
        True,
    )


def test_the_rungs_a_bar_reached_come_back_nearest_first() -> None:
    subject = activation()
    assert reached_legs(
        subject, LONG, bar(0, "100", "125", "99", "124"), already_filled=()
    ) == (0, 1)
    assert reached_legs(
        subject, LONG, bar(0, "100", "125", "99", "124"), already_filled=(0,)
    ) == (1,)
    assert reached_legs(
        subject, LONG, bar(0, "100", "101", "99", "100"), already_filled=()
    ) == ()


def test_a_rung_that_is_not_on_the_ladder_is_refused() -> None:
    with pytest.raises(PaperRefusedError, match="no rung 3"):
        target_fill(
            activation(), LONG, bar(0, "100", "125", "99", "124"), leg_index=2
        )


def test_a_rung_fills_at_its_target_or_at_the_open_it_gapped_through() -> None:
    subject = activation()
    assert target_fill(
        subject, LONG, bar(0, "100", "112", "99", "111"), leg_index=0
    ) == (Decimal("110"), False)
    assert target_fill(
        subject, LONG, bar(0, "112", "115", "111", "114"), leg_index=0
    ) == (Decimal("112"), True)


# --------------------------------------------------------------------------
# The stop rules
# --------------------------------------------------------------------------


def _excursion(favourable: str, adverse: str = "99", bars: int = 1) -> Excursion:
    return Excursion(
        favourable=Decimal(favourable), adverse=Decimal(adverse), bars=bars
    )


def test_break_even_does_not_apply_until_the_trade_has_been_that_far_in_front() -> None:
    rules = break_even("1")
    assert isinstance(
        break_even_stop(
            rules,
            LONG,
            entry_price=Decimal("100"),
            risk_distance=Decimal("5"),
            excursion=_excursion("104"),
        ),
        Absent,
    )
    assert break_even_stop(
        rules,
        LONG,
        entry_price=Decimal("100"),
        risk_distance=Decimal("5"),
        excursion=_excursion("105"),
    ) == Decimal("100")


def test_break_even_is_measured_against_the_excursion_not_the_latest_close() -> None:
    """A trade that reached the trigger and came back has already been that far
    in front; re-testing against the current price would move the stop back and
    forth as a function of where each bar happened to close."""
    assert break_even_stop(
        break_even("1"),
        LONG,
        entry_price=Decimal("100"),
        risk_distance=Decimal("5"),
        excursion=Excursion(
            favourable=Decimal("108"), adverse=Decimal("99"), bars=3
        ),
    ) == Decimal("100")


def test_a_break_even_offset_moves_the_stop_past_the_entry() -> None:
    assert break_even_stop(
        break_even("1", "0.2"),
        LONG,
        entry_price=Decimal("100"),
        risk_distance=Decimal("5"),
        excursion=_excursion("105"),
    ) == Decimal("101")


def test_break_even_is_mirrored_for_the_other_side() -> None:
    assert break_even_stop(
        break_even("1", "0.2"),
        SHORT,
        entry_price=Decimal("100"),
        risk_distance=Decimal("5"),
        excursion=Excursion(
            favourable=Decimal("95"), adverse=Decimal("101"), bars=1
        ),
    ) == Decimal("99")


def test_a_rule_the_owner_did_not_state_produces_no_level() -> None:
    for rules in (StopManagement(), break_even()):
        assert isinstance(
            trailing_stop(
                rules,
                LONG,
                entry_price=Decimal("100"),
                risk_distance=Decimal("5"),
                excursion=_excursion("120"),
            ),
            Absent,
        )


def test_a_trail_holds_off_until_the_level_the_owner_named() -> None:
    rules = trailing("1", start="2")
    assert isinstance(
        trailing_stop(
            rules,
            LONG,
            entry_price=Decimal("100"),
            risk_distance=Decimal("5"),
            excursion=_excursion("105"),
        ),
        Absent,
    )
    assert trailing_stop(
        rules,
        LONG,
        entry_price=Decimal("100"),
        risk_distance=Decimal("5"),
        excursion=_excursion("112"),
    ) == Decimal("107")


def test_an_excursion_with_no_bar_yet_produces_no_level() -> None:
    for rule in (break_even_stop, trailing_stop):
        assert isinstance(
            rule(
                break_even("1") if rule is break_even_stop else trailing("1"),
                LONG,
                entry_price=Decimal("100"),
                risk_distance=Decimal("5"),
                excursion=Excursion(),
            ),
            Absent,
        )


def test_a_stop_rule_stated_in_r_needs_a_positive_risk_distance() -> None:
    with pytest.raises(PaperRefusedError, match="positive risk distance"):
        break_even_stop(
            break_even("1"),
            LONG,
            entry_price=Decimal("100"),
            risk_distance=Decimal("0"),
            excursion=_excursion("120"),
        )


def test_the_tighter_of_the_two_rules_wins_and_only_one_move_comes_back() -> None:
    both = StopManagement(
        break_even=BreakEvenRule(trigger_r=Decimal("1")),
        trailing=TrailingRule(distance_r=Decimal("1")),
    )
    move = derive_stop_move(
        both,
        LONG,
        entry_price=Decimal("100"),
        risk_distance=Decimal("5"),
        effective_stop=Decimal("95"),
        excursion=_excursion("112"),
    )
    # break-even → 100, trail → 107. The trail is tighter.
    assert move.new_stop == Decimal("107")
    assert move.term_id == "trailing"


def test_a_move_that_would_loosen_the_stop_is_discarded() -> None:
    """A `POLICY_DERIVED` amendment that widened would be a widened stop with no
    owner behind it."""
    move = derive_stop_move(
        trailing("1"),
        LONG,
        entry_price=Decimal("100"),
        risk_distance=Decimal("5"),
        effective_stop=Decimal("104"),
        excursion=_excursion("106"),
    )
    assert isinstance(move, Absent)
    assert "tighten" in move.reason


def test_a_manual_activation_derives_no_move_at_all() -> None:
    move = derive_stop_move(
        StopManagement(),
        LONG,
        entry_price=Decimal("100"),
        risk_distance=Decimal("5"),
        effective_stop=Decimal("95"),
        excursion=_excursion("120"),
    )
    assert isinstance(move, Absent)


def test_the_rules_refuse_something_that_is_not_a_stop_management_record() -> None:
    for rule in (break_even_stop, trailing_stop):
        with pytest.raises(TypeError, match="StopManagement"):
            rule(
                "break even",
                LONG,
                entry_price=Decimal("100"),
                risk_distance=Decimal("5"),
                excursion=_excursion("120"),
            )
