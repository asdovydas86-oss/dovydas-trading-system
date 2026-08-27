"""Milestone BZ's four exit mechanics. **The control must reproduce BY, or nothing counts.**

`bz_exit_control` is `exit_full_target` under a BZ id, and the first test asserts
it reproduces `fmis.swing_lab.trades.simulate_trade` trade-for-trade over the
same awkward paths BY's own control suite uses. Every other family in this file
is a difference *from* a control that has been shown to hold; a family measured
against a drifting control measures its own machinery.

The second load-bearing group is `TestNoLookahead`. Each of the four mechanics
decides at a bar's **close** and executes at the next bar's **open**, and each
is asserted invariant to arbitrary mutation of every bar after its decision —
with the non-vacuity control that mutating the deciding bar itself DOES move the
result. A close-decided rule whose causality is only described is a rule that
has not been tested.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.paper.models import PriceBar
from fmis.swing_lab.exits import (
    BZ_EXIT_POLICIES,
    ExitMechanic,
    ExitPolicy,
    exit_policy_by_id,
    simulate_managed_trade,
)
from fmis.swing_lab.models import LabExitReason, SwingLabError
from fmis.swing_lab.persistence import ThesisObservation, ThesisTimeline
from fmis.swing_lab.trades import FRICTIONLESS_COSTS, simulate_trade
from fmis.swing_setup.models import Direction

_UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=_UTC)
FOUR_HOURS = timedelta(hours=4)

STOP = Decimal("90")
TARGET = Decimal("200")

CONTROL = exit_policy_by_id("bz_exit_control")
THESIS = exit_policy_by_id("bz_exit_thesis_failure")
STAGNATION = exit_policy_by_id("bz_exit_stagnation_12")
GIVEBACK = exit_policy_by_id("bz_exit_giveback_half")
TRAIL = exit_policy_by_id("bz_exit_structural_trail")


def _bar(index: int, o: str, h: str, low: str, c: str) -> PriceBar:
    return PriceBar(
        symbol="BTCUSDT", interval="4h", open_time=T0 + FOUR_HOURS * index,
        open=Decimal(o), high=Decimal(h), low=Decimal(low), close=Decimal(c),
    )


def _observation(
    index: int,
    *,
    setup: str = "sustained_higher",
    execution: str = "sustained_higher",
    lower: tuple[float, ...] = (),
    upper: tuple[float, ...] = (),
    close: float = 100.0,
) -> ThesisObservation:
    from fmis.level_crossing import LevelSide
    from fmis.swing_lab.geometry import LevelRef

    return ThesisObservation(
        symbol="BTCUSDT", as_of=T0 + FOUR_HOURS * index, bar_index=index,
        context_structural_trend="sustained_higher",
        setup_structural_trend=setup,
        execution_structural_trend=execution,
        context_regime_structure="trending",
        evidence_state=None, evidence_dominant_alignment=None,
        decision_context_state="sufficient", setup_state="confirmed",
        setup_direction="long", execution_close=close,
        upper_levels=tuple(
            LevelRef(price=p, side=LevelSide.UPPER, interval="4h",
                     origin_index=i, origin_label="swing_high")
            for i, p in enumerate(upper)
        ),
        lower_levels=tuple(
            LevelRef(price=p, side=LevelSide.LOWER, interval="4h",
                     origin_index=i, origin_label="swing_low")
            for i, p in enumerate(lower)
        ),
    )


def _timeline(**observations: ThesisObservation) -> ThesisTimeline:
    mapping = {value.bar_index: value for value in observations.values()}
    return ThesisTimeline(symbol="BTCUSDT", observations=mapping)


def _managed(bars, policy, *, timeline=None, window=30, stop=STOP, target=TARGET,
             direction=Direction.LONG, entry_index=1):
    return simulate_managed_trade(
        bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
        direction=direction, entry_index=entry_index,
        entry_price=bars[entry_index].open, entry_at=bars[entry_index].open_time,
        signal_at=bars[entry_index - 1].open_time,
        reference_price=bars[entry_index - 1].close,
        stop_price=stop, target_price=target, planned_risk_reward=3.0,
        window_bars=window, costs=FRICTIONLESS_COSTS, policy=policy,
        timeline=timeline,
    )


def _reference(bars, *, window=30, stop=STOP, target=TARGET, direction=Direction.LONG):
    return simulate_trade(
        bars, variant_id="v", symbol="BTCUSDT", setup_id="s",
        direction=direction, signal_index=0, signal_at=bars[0].open_time,
        reference_price=bars[0].close, stop_price=stop, target_price=target,
        planned_risk_reward=3.0, window_bars=window, costs=FRICTIONLESS_COSTS,
    )


#: Entry fills at bar 1's open of 100; stop 90 so risk is 10.
#: Runs to +2R on bar 2, then drifts sideways well inside the stop.
DRIFT = (
    _bar(0, "100", "101", "99", "100"),
    _bar(1, "100", "108", "99", "106"),
    _bar(2, "106", "120", "105", "118"),
    _bar(3, "118", "119", "112", "114"),
    _bar(4, "114", "116", "110", "112"),
    _bar(5, "112", "114", "108", "110"),
)


class TestTheControlReproducesTheSimulator:
    """`bz_exit_control` is BY's control under a BZ id. It must not drift."""

    @pytest.mark.parametrize(
        "bars",
        [
            pytest.param(DRIFT, id="drift"),
            pytest.param(
                (_bar(0, "100", "101", "99", "100"), _bar(1, "100", "101", "80", "85")),
                id="stops-out",
            ),
            pytest.param(
                (_bar(0, "100", "101", "99", "100"), _bar(1, "100", "210", "99", "205")),
                id="gaps-through-target",
            ),
            pytest.param(
                (_bar(0, "100", "101", "99", "100"), _bar(1, "100", "205", "85", "150")),
                id="same-bar-collision",
            ),
            pytest.param(
                (_bar(0, "100", "101", "99", "100"), _bar(1, "85", "95", "80", "90")),
                id="entry-opens-through-stop",
            ),
        ],
    )
    def test_the_control_matches_simulate_trade(self, bars) -> None:
        managed = _managed(bars, CONTROL).trade
        reference = _reference(bars)
        assert managed.exit_reason is reference.exit_reason
        assert managed.exit_price == reference.exit_price
        assert managed.net_r == reference.net_r
        assert managed.gross_r == reference.gross_r
        assert managed.bars_held == reference.bars_held
        assert managed.mfe_r == reference.mfe_r
        assert managed.mae_r == reference.mae_r

    def test_the_control_reads_no_timeline(self) -> None:
        assert not CONTROL.needs_timeline
        assert _managed(DRIFT, CONTROL, timeline=None).trade.is_measurable


class TestThesisFailure:
    def test_it_exits_at_the_next_bars_open_after_invalidation(self) -> None:
        """Bar 2's close says INVALIDATED; the fill is bar 3's OPEN of 118."""
        timeline = _timeline(
            a=_observation(0),
            b=_observation(1),
            c=_observation(2, setup="sustained_lower", execution="sustained_lower"),
            d=_observation(3),
        )
        result = _managed(DRIFT, THESIS, timeline=timeline)
        assert result.trade.exit_reason is LabExitReason.THESIS_INVALIDATED
        assert result.trade.exit_price == Decimal("118")
        assert result.trade.exit_at == DRIFT[3].open_time
        assert result.trade.bars_held == 3
        assert result.trade.net_r == Decimal("1.8")

    def test_it_fires_on_conflict_too(self) -> None:
        timeline = _timeline(
            a=_observation(0), b=_observation(1),
            c=_observation(2, setup="sustained_higher", execution="sustained_lower"),
            d=_observation(3),
        )
        assert (
            _managed(DRIFT, THESIS, timeline=timeline).trade.exit_reason
            is LabExitReason.THESIS_INVALIDATED
        )

    def test_it_does_not_fire_on_weakening(self) -> None:
        """The documented exclusion, asserted rather than described."""
        timeline = _timeline(
            a=_observation(0), b=_observation(1),
            c=_observation(2, setup="neutral", execution="neutral"),
            d=_observation(3, setup="neutral", execution="neutral"),
            e=_observation(4, setup="neutral", execution="neutral"),
            f=_observation(5, setup="neutral", execution="neutral"),
        )
        result = _managed(DRIFT, THESIS, timeline=timeline)
        assert result.trade.exit_reason is LabExitReason.TIME_STOP

    def test_a_gap_in_the_timeline_does_not_fire_it(self) -> None:
        """UNAVAILABLE is not adverse: absent evidence never closes a position."""
        timeline = _timeline(a=_observation(0), b=_observation(1))
        result = _managed(DRIFT, THESIS, timeline=timeline)
        assert result.trade.exit_reason is LabExitReason.TIME_STOP

    def test_it_refuses_to_run_without_a_timeline(self) -> None:
        with pytest.raises(SwingLabError, match="reads the structural timeline"):
            _managed(DRIFT, THESIS, timeline=None)

    def test_a_foreign_timeline_is_refused(self) -> None:
        other = ThesisTimeline(symbol="ETHUSDT", observations={})
        with pytest.raises(SwingLabError, match="cannot manage another"):
            _managed(DRIFT, THESIS, timeline=other)

    def test_the_stop_still_wins_when_it_is_hit_first(self) -> None:
        """A mechanic may add an exit; it may never remove the stop."""
        bars = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "101", "85", "88"),
            _bar(2, "88", "89", "80", "82"),
        )
        timeline = _timeline(
            a=_observation(0),
            b=_observation(1, setup="sustained_lower", execution="sustained_lower"),
        )
        result = _managed(bars, THESIS, timeline=timeline)
        assert result.trade.exit_reason is LabExitReason.STOP
        assert result.trade.net_r == Decimal("-1")


class TestStagnation:
    def test_it_fires_only_after_the_declared_bar_count(self) -> None:
        flat = tuple(
            [_bar(0, "100", "101", "99", "100")]
            + [_bar(i, "100", "101", "99", "100") for i in range(1, 20)]
        )
        result = _managed(flat, STAGNATION)
        assert result.trade.exit_reason is LabExitReason.STAGNATION
        # Bar 12's close is the first that satisfies `position >= 12`, and the
        # fill is bar 13's open.
        assert result.trade.bars_held == 13

    def test_a_position_that_made_progress_is_left_alone(self) -> None:
        """+0.5R by bar 12 is progress, so the mechanic never arms."""
        moving = tuple(
            [_bar(0, "100", "101", "99", "100")]
            + [_bar(i, "100", "106", "99", "105") for i in range(1, 20)]
        )
        result = _managed(moving, STAGNATION)
        assert result.trade.exit_reason is LabExitReason.TIME_STOP

    def test_progress_is_measured_from_the_peak_not_the_close(self) -> None:
        """A bar that ran +0.5R and closed back at entry HAS made progress."""
        spiked = tuple(
            [_bar(0, "100", "101", "99", "100")]
            + [_bar(1, "100", "106", "99", "100")]
            + [_bar(i, "100", "101", "99", "100") for i in range(2, 20)]
        )
        assert _managed(spiked, STAGNATION).trade.exit_reason is LabExitReason.TIME_STOP

    def test_the_declared_parameters_are_the_ones_measured(self) -> None:
        assert STAGNATION.stagnation_bars == 12
        assert STAGNATION.stagnation_progress_r == Decimal("0.5")


class TestGiveback:
    def test_it_fires_when_half_a_peak_of_at_least_1r_is_surrendered(self) -> None:
        """Peak +2R on bar 2; bar 3 closes at +1.4R, so 0.6R < 1.0R — not yet.

        Bar 4 closes at 112 = +1.2R, giveback 0.8R, still under half of 2R.
        Bar 5 closes at 110 = +1.0R, giveback 1.0R, which is exactly half.
        """
        result = _managed(DRIFT, GIVEBACK)
        assert result.trade.exit_reason is LabExitReason.TIME_STOP
        # The window ends before the rule arms on this path; extend it.
        extended = DRIFT + (_bar(6, "110", "111", "104", "105"),)
        result = _managed(extended, GIVEBACK)
        assert result.trade.exit_reason is LabExitReason.GIVEBACK

    def test_a_peak_below_the_arming_threshold_never_arms(self) -> None:
        small = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "105", "99", "104"),   # peak +0.5R only
            _bar(2, "104", "105", "99", "100"),   # gives it all back
            _bar(3, "100", "101", "99", "100"),
        )
        result = _managed(small, GIVEBACK)
        assert result.trade.exit_reason is LabExitReason.TIME_STOP

    def test_a_monotone_winner_is_never_closed_by_it(self) -> None:
        rising = tuple(
            [_bar(0, "100", "101", "99", "100")]
            + [_bar(i, str(99 + i * 5), str(101 + i * 5), str(98 + i * 5),
                    str(100 + i * 5)) for i in range(1, 8)]
        )
        result = _managed(rising, GIVEBACK)
        assert result.trade.exit_reason is not LabExitReason.GIVEBACK

    def test_the_declared_parameters_are_the_ones_measured(self) -> None:
        assert GIVEBACK.giveback_arm_r == Decimal("1")
        assert GIVEBACK.giveback_fraction == Decimal("0.5")


class TestStructuralTrail:
    def test_it_moves_the_stop_to_a_confirmed_level(self) -> None:
        """Bar 2 confirms a level at 105; the stop moves there from bar 3."""
        timeline = _timeline(
            a=_observation(0, lower=(95.0,), close=100.0),
            b=_observation(1, lower=(95.0,), close=106.0),
            c=_observation(2, lower=(105.0,), close=118.0),
            d=_observation(3, lower=(105.0,), close=114.0),
            e=_observation(4, lower=(105.0,), close=112.0),
            f=_observation(5, lower=(105.0,), close=110.0),
        )
        bars = DRIFT + (_bar(6, "110", "111", "100", "102"),)
        result = _managed(bars, TRAIL, timeline=timeline)
        assert result.trade.exit_reason is LabExitReason.STOP
        assert result.trade.exit_price == Decimal("105")
        assert result.trade.net_r == Decimal("0.5")

    def test_it_never_loosens(self) -> None:
        """A level further from the entry than the current stop is ignored.

        **The path is built so the loosening level is actually reached.** An
        earlier version of this test used a path whose stop was hit on the very
        bar that offered the loosening level, so the trade ended before the rule
        was ever consulted and the test passed without exercising it — a mutant
        replacing the only-tighten comparison survived it. Here the stop at 105
        is never touched until bar 6, so bar 2's level at 60 IS offered to the
        trail, and accepting it would raise from `_State.tighten`.
        """
        climbing = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "108", "99", "106"),
            _bar(2, "106", "120", "106", "118"),   # never reaches the 105 stop
            _bar(3, "118", "119", "112", "114"),
            _bar(4, "114", "116", "111", "112"),
            _bar(5, "112", "114", "110", "111"),
            _bar(6, "111", "112", "100", "102"),   # finally takes out 105
        )
        timeline = _timeline(
            a=_observation(0, lower=(95.0,), close=100.0),
            b=_observation(1, lower=(105.0,), close=106.0),   # tightens to 105
            c=_observation(2, lower=(60.0,), close=118.0),    # would LOOSEN
            d=_observation(3, lower=(60.0,), close=114.0),
            e=_observation(4, lower=(60.0,), close=112.0),
            f=_observation(5, lower=(60.0,), close=111.0),
        )
        result = _managed(climbing, TRAIL, timeline=timeline)
        # The stop stayed at the tightened 105 and never fell back to 60 or 90.
        assert result.trade.exit_reason is LabExitReason.STOP
        assert result.trade.exit_price == Decimal("105")
        assert result.trade.net_r == Decimal("0.5")

    def test_no_confirmed_structure_moves_nothing(self) -> None:
        """It never falls back to a price when the engines confirmed nothing."""
        timeline = _timeline(
            **{f"o{i}": _observation(i, lower=(), close=100.0) for i in range(6)}
        )
        result = _managed(DRIFT, TRAIL, timeline=timeline)
        assert result.trade.exit_reason is LabExitReason.TIME_STOP
        assert result.trade.initial_stop == STOP

    def test_a_level_above_the_close_is_not_a_stop(self) -> None:
        """A 'protective' level on the wrong side of price is refused."""
        timeline = _timeline(
            **{f"o{i}": _observation(i, lower=(500.0,), close=100.0) for i in range(6)}
        )
        result = _managed(DRIFT, TRAIL, timeline=timeline)
        assert result.trade.exit_reason is LabExitReason.TIME_STOP

    def test_it_refuses_to_run_without_a_timeline(self) -> None:
        with pytest.raises(SwingLabError, match="reads the structural timeline"):
            _managed(DRIFT, TRAIL, timeline=None)

    def test_a_short_trails_upper_levels(self) -> None:
        """The mirror: a SHORT is protected by levels ABOVE it."""
        falling = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "101", "92", "94"),
            _bar(2, "94", "95", "84", "86"),
            _bar(3, "86", "97", "85", "96"),
        )
        timeline = _timeline(
            a=_observation(0, upper=(110.0,), close=100.0),
            b=_observation(1, upper=(110.0,), close=94.0),
            c=_observation(2, upper=(95.0,), close=86.0),
            d=_observation(3, upper=(95.0,), close=96.0),
        )
        result = _managed(
            falling, TRAIL, timeline=timeline,
            direction=Direction.SHORT, stop=Decimal("110"), target=Decimal("50"),
        )
        assert result.trade.exit_reason is LabExitReason.STOP
        assert result.trade.exit_price == Decimal("95")


class TestNoLookahead:
    """Each mechanic decides at a bar's close. **Prove it cannot see past that.**"""

    @staticmethod
    def _mutate_from(bars, first: int):
        return tuple(
            bar
            if index < first
            else PriceBar(
                symbol=bar.symbol, interval=bar.interval, open_time=bar.open_time,
                open=bar.open * 1000, high=bar.high * 1000,
                low=bar.low * 1000, close=bar.close * 1000,
            )
            for index, bar in enumerate(bars)
        )

    def test_a_thesis_exit_is_blind_to_bars_after_its_fill(self) -> None:
        timeline = _timeline(
            a=_observation(0), b=_observation(1),
            c=_observation(2, setup="sustained_lower", execution="sustained_lower"),
            d=_observation(3), e=_observation(4), f=_observation(5),
        )
        base = _managed(DRIFT, THESIS, timeline=timeline).trade
        # The exit fills at bar index 3's open, so bars 4+ cannot matter.
        mutated = _managed(self._mutate_from(DRIFT, 4), THESIS, timeline=timeline).trade
        assert base.exit_price == mutated.exit_price
        assert base.net_r == mutated.net_r
        assert base.exit_reason is mutated.exit_reason

    def test_the_control_changes_when_the_deciding_bar_moves(self) -> None:
        """Non-vacuity. Mutating the bar the rule DOES read must move the result."""
        timeline = _timeline(
            a=_observation(0), b=_observation(1),
            c=_observation(2, setup="sustained_lower", execution="sustained_lower"),
            d=_observation(3), e=_observation(4), f=_observation(5),
        )
        base = _managed(DRIFT, THESIS, timeline=timeline).trade
        mutated = _managed(self._mutate_from(DRIFT, 3), THESIS, timeline=timeline).trade
        assert base.exit_price != mutated.exit_price

    def test_a_stagnation_exit_is_blind_to_bars_after_its_fill(self) -> None:
        flat = tuple(
            [_bar(0, "100", "101", "99", "100")]
            + [_bar(i, "100", "101", "99", "100") for i in range(1, 20)]
        )
        base = _managed(flat, STAGNATION).trade
        mutated = _managed(self._mutate_from(flat, 14), STAGNATION).trade
        assert base.exit_price == mutated.exit_price
        assert base.net_r == mutated.net_r

    def test_the_stagnation_control_changes_on_its_own_bar(self) -> None:
        flat = tuple(
            [_bar(0, "100", "101", "99", "100")]
            + [_bar(i, "100", "101", "99", "100") for i in range(1, 20)]
        )
        base = _managed(flat, STAGNATION).trade
        # Bar 13 is the fill bar; mutating it must move the fill.
        mutated = _managed(self._mutate_from(flat, 13), STAGNATION).trade
        assert base.exit_price != mutated.exit_price

    def test_a_giveback_exit_is_blind_to_bars_after_its_fill(self) -> None:
        extended = DRIFT + (
            _bar(6, "110", "111", "104", "105"),
            _bar(7, "105", "106", "100", "101"),
            _bar(8, "101", "102", "99", "100"),
        )
        base = _managed(extended, GIVEBACK).trade
        assert base.exit_reason is LabExitReason.GIVEBACK
        mutated = _managed(self._mutate_from(extended, 7), GIVEBACK).trade
        assert base.exit_price == mutated.exit_price
        assert base.net_r == mutated.net_r

    def test_when_a_level_is_confirmed_changes_the_outcome(self) -> None:
        """**The discriminating test.** One bar's difference in confirmation decides.

        The path dips to 104 on bar 3 and recovers. A level at 105 confirmed by
        bar 2's close is in force for bar 3 and stops the trade out; the same
        level confirmed one bar later is not, and the position survives. If the
        trail could read a level before the engines confirmed it, these two would
        be equal — which is exactly the lookahead this asserts is absent.
        """
        dip = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "108", "99", "106"),
            _bar(2, "106", "120", "105", "118"),
            _bar(3, "118", "119", "104", "116"),   # the dip through 105
            _bar(4, "116", "130", "115", "128"),
            _bar(5, "128", "132", "126", "130"),
        )
        confirmed_at_2 = _timeline(
            a=_observation(0, lower=(95.0,), close=100.0),
            b=_observation(1, lower=(95.0,), close=106.0),
            c=_observation(2, lower=(105.0,), close=118.0),   # in force for bar 3
            d=_observation(3, lower=(105.0,), close=116.0),
            e=_observation(4, lower=(105.0,), close=128.0),
            f=_observation(5, lower=(105.0,), close=130.0),
        )
        confirmed_at_3 = _timeline(
            a=_observation(0, lower=(95.0,), close=100.0),
            b=_observation(1, lower=(95.0,), close=106.0),
            c=_observation(2, lower=(95.0,), close=118.0),
            d=_observation(3, lower=(105.0,), close=116.0),   # too late for bar 3
            e=_observation(4, lower=(105.0,), close=128.0),
            f=_observation(5, lower=(105.0,), close=130.0),
        )
        early = _managed(dip, TRAIL, timeline=confirmed_at_2).trade
        late = _managed(dip, TRAIL, timeline=confirmed_at_3).trade

        assert early.exit_reason is LabExitReason.STOP
        assert early.exit_price == Decimal("105")
        assert late.exit_reason is not LabExitReason.STOP
        assert late.net_r > early.net_r

    def test_a_level_never_confirmed_is_never_trailed_to(self) -> None:
        bars = DRIFT + (_bar(6, "110", "111", "100", "102"),)
        never = _timeline(
            **{f"o{i}": _observation(i, lower=(95.0,), close=100.0) for i in range(7)}
        )
        result = _managed(bars, TRAIL, timeline=never).trade
        # It trailed to the only level it ever saw — 95 — and never to 105.
        assert result.exit_reason is LabExitReason.TIME_STOP
        assert result.exit_price == Decimal("102")


class TestPolicyValidation:
    def test_a_mechanic_without_its_parameters_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="requires stagnation_bars"):
            ExitPolicy(
                policy_id="x", title="t", mechanic=ExitMechanic.STAGNATION,
                hypothesis="h",
            )

    def test_a_parameter_the_mechanic_ignores_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="does not read"):
            ExitPolicy(
                policy_id="x", title="t", mechanic=ExitMechanic.FULL_TARGET,
                hypothesis="h", stagnation_bars=5,
            )

    @pytest.mark.parametrize("bad", [Decimal("0"), Decimal("-0.5"), Decimal("1.5")])
    def test_an_out_of_range_giveback_fraction_is_refused(self, bad: Decimal) -> None:
        with pytest.raises(SwingLabError, match="giveback_fraction"):
            ExitPolicy(
                policy_id="x", title="t", mechanic=ExitMechanic.GIVEBACK_FRACTION,
                hypothesis="h", giveback_arm_r=Decimal("1"), giveback_fraction=bad,
            )

    def test_a_non_positive_stagnation_count_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="at least 1"):
            ExitPolicy(
                policy_id="x", title="t", mechanic=ExitMechanic.STAGNATION,
                hypothesis="h", stagnation_bars=0,
                stagnation_progress_r=Decimal("0.5"),
            )


class TestTheSealIsUnaffected:
    def test_bys_pinned_digest_is_byte_identical(self) -> None:
        """BZ grew `ExitPolicy`. BY's published seal must not have moved."""
        from fmis.swing_lab.preregistration import (
            PREREGISTRATION_DIGEST,
            preregistration_digest,
        )

        assert preregistration_digest() == PREREGISTRATION_DIGEST

    def test_bys_four_policies_emit_no_bz_keys(self) -> None:
        from fmis.swing_lab.exits import PRE_DECLARED_EXIT_POLICIES

        for policy in PRE_DECLARED_EXIT_POLICIES:
            assert set(policy.payload()) == {
                "policy_id", "title", "mechanic", "hypothesis", "partial_fraction",
            }

    def test_every_bz_family_has_a_prediction_and_a_refutation(self) -> None:
        """A rule with no stated refutation cannot fail."""
        for policy in BZ_EXIT_POLICIES:
            if policy.is_baseline:
                assert "CONTROL" in policy.hypothesis
                continue
            assert "PREDICTION:" in policy.hypothesis
            assert "REFUTED BY:" in policy.hypothesis


class TestArmingBookkeeping:
    """`armed` and `armed_at` must describe the same event, or neither reports."""

    def test_a_giveback_that_arms_and_never_fires_still_reports_arming(self) -> None:
        rising = tuple(
            [_bar(0, "100", "101", "99", "100")]
            + [
                _bar(i, str(99 + i * 5), str(101 + i * 5), str(98 + i * 5),
                     str(100 + i * 5))
                for i in range(1, 8)
            ]
        )
        result = _managed(rising, GIVEBACK)
        assert result.trade.exit_reason is not LabExitReason.GIVEBACK
        # It ran well past +1R, so it armed — and must say when.
        assert result.armed_at is not None

    def test_a_position_that_never_reaches_the_arm_never_arms(self) -> None:
        flat = tuple(
            [_bar(0, "100", "101", "99", "100")]
            + [_bar(i, "100", "101", "99", "100") for i in range(1, 8)]
        )
        assert _managed(flat, GIVEBACK).armed_at is None
