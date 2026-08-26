"""Exit management. **The control must reproduce BX exactly, or nothing else counts.**

`exit_full_target` run without a ladder is the same measurement
`fmis.swing_lab.trades.simulate_trade` makes, and the first test here asserts it
trade-for-trade over a set of deliberately awkward paths — gaps, same-bar
collisions, time stops and an entry that opened through its own stop. Everything
after that is a difference *from* a control that has been shown to hold.

The second load-bearing test is the partial-exit arithmetic. Recording a
two-legged exit as one notional-weighted average price is what lets a managed
trade be a plain `LabTrade` and be re-priced by the existing cost model; the
identity is asserted leg by leg rather than trusted to the algebra in a docstring.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.paper.models import PriceBar
from fmis.swing_lab.exits import (
    ARMING_R,
    DEFAULT_PARTIAL_FRACTION,
    PRE_DECLARED_EXIT_POLICIES,
    ExitMechanic,
    ExitPolicy,
    exit_policy_by_id,
    simulate_managed_trade,
)
from fmis.swing_lab.intrabar import BarLadder
from fmis.swing_lab.models import LabExitReason, SwingLabError
from fmis.swing_lab.trades import CONSERVATIVE_COSTS, FRICTIONLESS_COSTS, simulate_trade
from fmis.swing_setup.models import Direction

_UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=_UTC)
FOUR_HOURS = timedelta(hours=4)

FULL = exit_policy_by_id("exit_full_target")
PARTIAL = exit_policy_by_id("exit_partial_1r")
BREAK_EVEN = exit_policy_by_id("exit_break_even_1r")
TRAIL = exit_policy_by_id("exit_trail_prior_bar")

STOP = Decimal("90")
TARGET = Decimal("120")


def _bar(index: int, o: str, h: str, low: str, c: str, *, interval: str = "4h") -> PriceBar:
    step = FOUR_HOURS if interval == "4h" else timedelta(hours=1)
    return PriceBar(
        symbol="BTCUSDT", interval=interval, open_time=T0 + step * index,
        open=Decimal(o), high=Decimal(h), low=Decimal(low), close=Decimal(c),
    )


def _managed(bars, policy, *, ladder=None, costs=FRICTIONLESS_COSTS, window=10,
             stop=STOP, target=TARGET, direction=Direction.LONG):
    return simulate_managed_trade(
        bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
        direction=direction, entry_index=1, entry_price=bars[1].open,
        entry_at=bars[1].open_time, signal_at=bars[0].open_time,
        reference_price=bars[0].close, stop_price=stop, target_price=target,
        planned_risk_reward=3.0, window_bars=window, costs=costs,
        policy=policy, ladder=ladder,
    )


def _reference(bars, *, costs=FRICTIONLESS_COSTS, window=10, stop=STOP, target=TARGET,
               direction=Direction.LONG):
    return simulate_trade(
        bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
        direction=direction, signal_index=0, signal_at=bars[0].open_time,
        reference_price=bars[0].close, stop_price=stop, target_price=target,
        planned_risk_reward=3.0, window_bars=window, costs=costs,
    )


#: Paths chosen to exercise every terminal state `simulate_trade` can produce.
_PATHS = {
    "target": [
        _bar(0, "100", "101", "99", "100"), _bar(1, "100", "105", "99", "104"),
        _bar(2, "104", "121", "103", "120"),
    ],
    "stop": [
        _bar(0, "100", "101", "99", "100"), _bar(1, "100", "105", "99", "104"),
        _bar(2, "104", "105", "89", "91"),
    ],
    "time_stop": [
        _bar(0, "100", "101", "99", "100"), _bar(1, "100", "105", "99", "104"),
        _bar(2, "104", "106", "103", "105"),
    ],
    "same_bar": [
        _bar(0, "100", "101", "99", "100"), _bar(1, "100", "105", "99", "104"),
        _bar(2, "104", "121", "89", "100"),
    ],
    "gap_through_target": [
        _bar(0, "100", "101", "99", "100"), _bar(1, "100", "105", "99", "104"),
        _bar(2, "130", "135", "129", "134"),
    ],
    "entry_through_stop": [
        _bar(0, "100", "101", "99", "100"), _bar(1, "85", "88", "84", "86"),
    ],
}


@pytest.mark.parametrize("name", sorted(_PATHS))
@pytest.mark.parametrize("costs", [FRICTIONLESS_COSTS, CONSERVATIVE_COSTS])
def test_the_no_ladder_control_reproduces_simulate_trade_exactly(name, costs) -> None:
    """**The control.** If this drifts, every exit comparison in the milestone is void."""
    bars = _PATHS[name]
    managed = _managed(bars, FULL, costs=costs).trade
    expected = _reference(bars, costs=costs)
    for field in (
        "entry_at", "entry_price", "initial_stop", "target", "exit_at",
        "exit_price", "exit_reason", "bars_held", "gross_r", "net_r",
        "mfe_r", "mae_r", "cost_policy_id",
    ):
        assert getattr(managed, field) == getattr(expected, field), field


@pytest.mark.parametrize("name", sorted(_PATHS))
def test_the_control_reproduces_simulate_trade_for_a_short_too(name) -> None:
    """A side-swap mutation survives a long-only fixture; this closes that door."""
    bars = _PATHS[name]
    stop, target = Decimal("120"), Decimal("90")
    managed = _managed(bars, FULL, stop=stop, target=target, direction=Direction.SHORT)
    expected = _reference(bars, stop=stop, target=target, direction=Direction.SHORT)
    assert managed.trade.exit_reason == expected.exit_reason
    assert managed.trade.net_r == expected.net_r


# --------------------------------------------------------------- partials ---


def test_the_partial_exit_books_half_at_one_r_and_the_rest_at_the_target() -> None:
    bars = [
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "105", "99", "104"),      # entry at 100, risk 10
        _bar(2, "104", "112", "103", "111"),     # +1R at 110 → half off
        _bar(3, "111", "121", "110", "120"),     # target
    ]
    result = _managed(bars, PARTIAL)
    assert [leg.fraction for leg in result.legs] == [
        DEFAULT_PARTIAL_FRACTION, Decimal(1) - DEFAULT_PARTIAL_FRACTION
    ]
    assert [leg.price for leg in result.legs] == [Decimal("110"), Decimal("120")]
    # (0.5×110 + 0.5×120 − 100) / 10 = 1.5R, not the 2.0R a full runner would pay.
    assert result.trade.gross_r == Decimal("1.5")


def test_the_weighted_average_exit_reproduces_the_leg_arithmetic_exactly() -> None:
    """The identity that lets a two-legged trade be an ordinary `LabTrade`."""
    bars = [
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "105", "99", "104"),
        _bar(2, "104", "112", "103", "111"),
        _bar(3, "111", "121", "110", "120"),
    ]
    result = _managed(bars, PARTIAL, costs=CONSERVATIVE_COSTS)
    entry, risk = Decimal("100"), Decimal("10")
    gross = sum(
        leg.fraction * (leg.price - entry) for leg in result.legs
    ) / risk
    fees = CONSERVATIVE_COSTS.fee_rate * (
        entry + sum(leg.fraction * leg.price for leg in result.legs)
    )
    assert result.trade.gross_r == gross
    assert result.trade.net_r == gross - fees / risk


def test_a_partial_that_never_arms_is_the_baseline_trade() -> None:
    bars = [
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "105", "99", "104"),
        _bar(2, "104", "105", "89", "91"),       # straight to the stop
    ]
    assert _managed(bars, PARTIAL).trade.net_r == _reference(bars).net_r


def test_the_arming_level_is_dropped_when_it_coincides_with_the_target() -> None:
    """Two watched levels at one price would be permanent invented ambiguity."""
    bars = [
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "105", "99", "104"),
        _bar(2, "104", "111", "103", "110"),
    ]
    result = _managed(bars, PARTIAL, target=Decimal("110"))
    assert result.trade.exit_reason is LabExitReason.TARGET
    assert len(result.legs) == 1


# ------------------------------------------------------------ break-even ---


def test_break_even_converts_a_full_loss_into_a_scratch() -> None:
    bars = [
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "105", "99", "104"),
        _bar(2, "104", "112", "103", "111"),     # arms at 110
        _bar(3, "111", "112", "89", "90"),       # would have been −1R
    ]
    assert _reference(bars).net_r == Decimal("-1")
    assert _managed(bars, BREAK_EVEN).trade.net_r == Decimal("0")


def test_break_even_arms_from_the_bar_AFTER_the_trigger() -> None:
    """The stated convention, asserted. Four prices cannot order a high against a low."""
    bars = [
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "105", "99", "104"),
        _bar(2, "104", "112", "99", "100"),      # armed at 110 AND traded to 99
        _bar(3, "101", "121", "101", "120"),     # never revisits 100
    ]
    # 99 is below the break-even stop of 100, but it is on the arming bar, so it
    # is not tested against it. The trade survives to the target.
    assert _managed(bars, BREAK_EVEN).trade.exit_reason is LabExitReason.TARGET


def test_break_even_does_not_change_a_trade_that_never_reached_one_r() -> None:
    bars = [
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "105", "99", "104"),
        _bar(2, "104", "109", "89", "90"),       # peaked below 110
    ]
    assert _managed(bars, BREAK_EVEN).trade.net_r == _reference(bars).net_r


# ----------------------------------------------------------------- trail ---


def test_the_trail_follows_the_prior_bar_extreme_once_armed() -> None:
    bars = [
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "105", "99", "104"),
        _bar(2, "104", "112", "103", "111"),     # arms; its low is 103
        _bar(3, "111", "115", "102", "103"),     # stop now 103, and it is hit
    ]
    result = _managed(bars, TRAIL)
    assert result.trade.exit_reason is LabExitReason.STOP
    assert result.trade.exit_price == Decimal("103")
    assert result.trade.net_r == Decimal("0.3")


def test_the_trail_never_loosens() -> None:
    """A prior bar whose low is below the current stop must be ignored, not obeyed."""
    bars = [
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "105", "99", "104"),
        _bar(2, "104", "112", "103", "111"),     # arms, stop → 103
        _bar(3, "111", "114", "104", "113"),     # low 104 > 103 → stop → 104
        _bar(4, "113", "114", "95", "96"),       # a wide bar; stop stays 104
    ]
    result = _managed(bars, TRAIL)
    assert result.trade.exit_price == Decimal("104")


def test_a_mechanic_may_never_widen_the_stop() -> None:
    """Asserted in the engine, not left to each mechanic to remember."""
    from fmis.swing_lab.exits import _State
    from fmis.snapshotting import TradeDirection

    state = _State(
        side=TradeDirection.LONG, entry=Decimal("100"), risk=Decimal("10"),
        stop=Decimal("95"), target=Decimal("120"), policy=FULL,
    )
    with pytest.raises(SwingLabError, match="further from the entry"):
        state.tighten(Decimal("90"))


# ---------------------------------------------------- ladder interaction ---


def test_a_ladder_resolves_an_exit_the_coarse_walk_refused() -> None:
    """§8 and §9 meeting: BX's NOT MEASURABLE becomes a measured trade."""
    bars = _PATHS["same_bar"]
    assert _managed(bars, FULL).trade.exit_reason is LabExitReason.AMBIGUOUS_SAME_BAR

    fine = tuple(
        _bar(index, *values, interval="1h")
        for index, values in enumerate(
            [
                ("104", "121", "103", "120"),   # target first
                ("120", "120", "89", "90"),
                ("90", "100", "89", "100"),
                ("100", "101", "99", "100"),
            ],
            start=8,
        )
    )
    ladder = BarLadder("BTCUSDT", (("4h", tuple(bars)), ("1h", fine)))
    result = _managed(bars, FULL, ladder=ladder)
    assert result.trade.exit_reason is LabExitReason.TARGET
    assert result.trade.exit_price == Decimal("120")
    assert result.descents == 1


def test_an_unresolvable_bar_stays_ambiguous_and_carries_no_r() -> None:
    bars = _PATHS["same_bar"]
    result = _managed(bars, FULL)
    assert result.trade.net_r is None
    assert result.trade.mfe_r is not None      # excursions are still measured
    assert result.ambiguous_bar_at == bars[2].open_time


# ---------------------------------------------------------------- policy ---


def test_exactly_one_exit_policy_is_the_baseline_control() -> None:
    baselines = [item for item in PRE_DECLARED_EXIT_POLICIES if item.is_baseline]
    assert len(baselines) == 1
    assert baselines[0].mechanic is ExitMechanic.FULL_TARGET


def test_every_managed_mechanic_arms_at_the_same_r() -> None:
    """Three rules differing only in WHAT they do at +1R is a comparison; else a sweep."""
    assert ARMING_R == Decimal("1")
    arming = [item for item in PRE_DECLARED_EXIT_POLICIES if item.mechanic.arms]
    assert len(arming) == 3


def test_the_trail_is_labelled_as_not_structural() -> None:
    assert "NOT a structural trail" in TRAIL.hypothesis


def test_a_partial_fraction_must_lie_strictly_inside_zero_and_one() -> None:
    for value in (Decimal("0"), Decimal("1"), Decimal("1.5")):
        with pytest.raises(SwingLabError, match="strictly between 0 and 1"):
            ExitPolicy(
                policy_id="x", title="t", mechanic=ExitMechanic.PARTIAL_AT_1R,
                hypothesis="h", partial_fraction=value,
            )


def test_an_unknown_exit_id_names_the_alternatives() -> None:
    with pytest.raises(SwingLabError, match="no pre-declared exit policy"):
        exit_policy_by_id("exit_trail_atr")


def test_simulate_refuses_an_entry_index_outside_the_series() -> None:
    bars = _PATHS["target"]
    with pytest.raises(SwingLabError, match="must address a bar"):
        simulate_managed_trade(
            bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
            direction=Direction.LONG, entry_index=99, entry_price=Decimal("100"),
            entry_at=T0, signal_at=T0, reference_price=Decimal("100"),
            stop_price=STOP, target_price=TARGET, planned_risk_reward=3.0,
            window_bars=10, costs=FRICTIONLESS_COSTS, policy=FULL,
        )


def test_simulate_refuses_a_non_policy() -> None:
    bars = _PATHS["target"]
    with pytest.raises(TypeError, match="must be an ExitPolicy"):
        simulate_managed_trade(
            bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
            direction=Direction.LONG, entry_index=1, entry_price=Decimal("100"),
            entry_at=T0, signal_at=T0, reference_price=Decimal("100"),
            stop_price=STOP, target_price=TARGET, planned_risk_reward=3.0,
            window_bars=10, costs=FRICTIONLESS_COSTS, policy=object(),
        )


def test_the_trade_records_which_mechanic_produced_it() -> None:
    """Two mechanics' trades must never be summable by accident."""
    result = _managed(_PATHS["target"], PARTIAL)
    assert result.trade.metadata["exit_policy_id"] == "exit_partial_1r"
    assert result.trade.metadata["exit_mechanic"] == "partial_at_1r"


# --------------------------------------------------------------- Milestone BY ---
#
# Two invariants the first pass left unguarded, found by mutation probes
# `exits:partial-average-unweighted` and `exits:trail-loosens`. Both survived
# because the original fixtures were SYMMETRIC — a half-and-half split makes the
# weighted and unweighted averages identical, and a monotonically rising path
# makes a loosening trail indistinguishable from a tightening one. Asymmetry is
# what turns each of them into a test.


def test_the_weighted_average_is_weighted_and_not_a_plain_mean() -> None:
    """With an UNEVEN split the two arithmetics differ; with 50/50 they cannot."""
    uneven = ExitPolicy(
        policy_id="exit_partial_quarter",
        title="A quarter off at +1R",
        mechanic=ExitMechanic.PARTIAL_AT_1R,
        hypothesis="probe",
        partial_fraction=Decimal("0.25"),
    )
    bars = [
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "105", "99", "104"),      # entry 100, risk 10
        _bar(2, "104", "112", "103", "111"),     # +1R at 110 → a quarter off
        _bar(3, "111", "121", "110", "120"),     # target at 120
    ]
    result = _managed(bars, uneven)
    # 0.25×110 + 0.75×120 = 117.5, and (117.5 − 100)/10 = 1.75R.
    # A plain mean would be (110 + 120)/2 = 115 and would report 1.50R.
    assert result.trade.exit_price == Decimal("117.50")
    assert result.trade.gross_r == Decimal("1.75")


def test_the_trail_ignores_a_prior_bar_whose_extreme_is_behind_the_stop() -> None:
    """A loosening trail gives back exactly the R the rule exists to protect."""
    bars = [
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "105", "99", "104"),
        _bar(2, "104", "112", "103", "111"),     # arms; its low 103 becomes the stop
        _bar(3, "111", "114", "100", "113"),     # low 100 is BEHIND the stop of 103
        _bar(4, "113", "114", "101", "102"),     # dips to 101
    ]
    result = _managed(bars, TRAIL)
    # The stop must still be 103 on bar 4 — never relaxed to bar 3's low of 100 —
    # so the dip to 101 takes it out at 103 rather than running on.
    assert result.trade.exit_reason is LabExitReason.STOP
    assert result.trade.exit_price == Decimal("103")


def test_the_no_ladder_control_refuses_a_bar_that_OPENED_beyond_one_level() -> None:
    """The case the original `_PATHS` fixtures did not contain.

    `exit_full_target`'s **sealed** hypothesis says the no-ladder run "must
    reproduce simulate_trade exactly". `opened_beyond` is a genuine extra fact —
    a bar that opened past a level reached it at its first price — but
    `simulate_trade` does not use it, so consulting it without a ladder made the
    control resolve a bar the coarse simulator refuses. The seal is the
    contract, so the code was fixed rather than the claim.
    """
    bars = [
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "105", "99", "104"),
        _bar(2, "85", "121", "84", "110"),   # opens below the stop AND reaches the target
    ]
    control = _managed(bars, FULL, ladder=None).trade
    expected = _reference(bars)
    assert expected.exit_reason is LabExitReason.AMBIGUOUS_SAME_BAR
    assert control.exit_reason == expected.exit_reason
    assert control.net_r == expected.net_r


def test_a_ladder_DOES_use_the_open_to_order_the_same_bar() -> None:
    """The extra fact belongs to the laddered run, where it is reported as resolution."""
    bars = [
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "100", "105", "99", "104"),
        _bar(2, "85", "121", "84", "110"),
    ]
    fine = tuple(
        _bar(index, "85", "121", "84", "110", interval="1h")
        for index in range(8, 12)
    )
    ladder = BarLadder("BTCUSDT", (("4h", tuple(bars)), ("1h", fine)))
    result = _managed(bars, FULL, ladder=ladder).trade
    assert result.exit_reason is LabExitReason.STOP
    assert result.exit_price == Decimal("85")   # the open, which came first


def test_a_gap_past_the_target_records_no_position_at_all() -> None:
    """`simulate_trade._unentered` leaves entry_at and entry_price ABSENT; so must this.

    A record that carries a fill while claiming no position was opened makes
    `entry_price is not None` an unreliable test for "this setup traded".
    """
    bars = [
        _bar(0, "100", "101", "99", "100"),
        _bar(1, "130", "135", "129", "134"),   # opens beyond the target of 120
    ]
    result = _managed(bars, FULL).trade
    expected = _reference(bars)
    assert result.exit_reason is LabExitReason.NO_ENTRY_BAR
    assert result.exit_reason == expected.exit_reason
    assert result.entry_at is None and expected.entry_at is None
    assert result.entry_price is None and expected.entry_price is None
