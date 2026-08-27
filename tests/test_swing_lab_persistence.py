"""Post-entry path observation. **Every checkpoint must be blind to its own future.**

The load-bearing test in this file is `TestNoLookahead`: a checkpoint at bar *n*
is asserted byte-identical when every bar after *n* is replaced with arbitrary
prices, and — the control that stops that passing vacuously — asserted to
**change** when a bar at or before *n* is replaced. A causal-observation module
whose first property is not proven that way is a module that has merely been
described as causal.

The second is the descriptive/causal split. `PersistenceTrack` deliberately
carries both kinds of field, because the milestone needs both; the tests assert
that the causal half (`checkpoints`) never moves under a future mutation and the
descriptive half (`peak_r`, `bars_to_peak_r`, …) **does**, which is what makes
the labelling something a reader can check rather than take on trust.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.paper.models import PriceBar
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.persistence import (
    ADVERSE_THRESHOLD,
    CHECKPOINT_BARS,
    EXCURSION_THRESHOLDS,
    LEVELS_PER_SIDE,
    PostEntryCheckpoint,
    ThesisObservation,
    ThesisState,
    ThesisTimeline,
    observe_path,
    thesis_state,
)
from fmis.swing_setup.models import Direction

_UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=_UTC)
FOUR_HOURS = timedelta(hours=4)

ENTRY = Decimal("100")
STOP = Decimal("90")
TARGET = Decimal("130")


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
    context: str = "sustained_higher",
    regime: str = "trending",
    symbol: str = "BTCUSDT",
) -> ThesisObservation:
    return ThesisObservation(
        symbol=symbol,
        as_of=T0 + FOUR_HOURS * index,
        bar_index=index,
        context_structural_trend=context,
        setup_structural_trend=setup,
        execution_structural_trend=execution,
        context_regime_structure=regime,
        evidence_state=None,
        evidence_dominant_alignment=None,
        decision_context_state="sufficient",
        setup_state="confirmed",
        setup_direction="long",
        execution_close=100.0,
        upper_levels=(),
        lower_levels=(),
    )


def _track(bars, *, timeline=None, direction=Direction.LONG, window=10, stop=STOP):
    return observe_path(
        bars, symbol="BTCUSDT", setup_id="s", direction=direction,
        sample="development", signal_at=bars[0].open_time, signal_index=0,
        entry_price=bars[1].open, initial_stop=stop, target=TARGET,
        evaluation_window_bars=window, timeline=timeline,
        checkpoints=(1, 2, 3),
    )


#: A path that runs +2R in favour, then gives it all back and closes below entry.
#: Entry fills at bar 1's open of 100, so risk is 10.
GIVEBACK_PATH = (
    _bar(0, "100", "101", "99", "100"),
    _bar(1, "100", "108", "99", "107"),   # bar 1: MFE +0.8R
    _bar(2, "107", "120", "106", "118"),  # bar 2: MFE +2.0R, close +1.8R
    _bar(3, "118", "119", "95", "96"),    # bar 3: gives it back, close -0.4R
)


class TestThesisState:
    """The six-member partition, and the precedence that decides between them."""

    def test_an_unchanged_supporting_structure_is_intact(self) -> None:
        entry = _observation(0)
        assert thesis_state(entry, _observation(3), Direction.LONG) is ThesisState.INTACT

    def test_a_reversed_setup_timeframe_is_invalidated(self) -> None:
        entry = _observation(0)
        current = _observation(3, setup="sustained_lower", execution="sustained_lower")
        assert thesis_state(entry, current, Direction.LONG) is ThesisState.INVALIDATED

    def test_invalidation_outranks_conflict(self) -> None:
        """A fully reversed setup timeframe is invalidation whatever 4H says.

        Both conditions hold here — the setup timeframe opposes the direction AND
        the two timeframes disagree — and the documented precedence requires the
        stronger statement. Reporting this as a mere disagreement would understate
        a thesis whose own structure now says the opposite.
        """
        entry = _observation(0)
        current = _observation(3, setup="sustained_lower", execution="sustained_higher")
        assert thesis_state(entry, current, Direction.LONG) is ThesisState.INVALIDATED

    def test_opposed_timeframes_conflict(self) -> None:
        entry = _observation(0)
        current = _observation(3, setup="sustained_higher", execution="sustained_lower")
        assert thesis_state(entry, current, Direction.LONG) is ThesisState.CONFLICTED

    def test_decayed_support_weakens(self) -> None:
        entry = _observation(0)
        current = _observation(3, setup="neutral", execution="neutral")
        assert thesis_state(entry, current, Direction.LONG) is ThesisState.WEAKENED

    def test_leaving_a_trending_regime_weakens(self) -> None:
        entry = _observation(0)
        current = _observation(3, regime="ranging")
        assert thesis_state(entry, current, Direction.LONG) is ThesisState.WEAKENED

    def test_appearing_support_strengthens(self) -> None:
        entry = _observation(0, setup="neutral", execution="neutral")
        current = _observation(3, setup="sustained_higher", execution="neutral")
        assert thesis_state(entry, current, Direction.LONG) is ThesisState.STRENGTHENED

    def test_the_execution_timeframe_joining_strengthens(self) -> None:
        entry = _observation(0, execution="neutral")
        current = _observation(3, execution="sustained_higher")
        assert thesis_state(entry, current, Direction.LONG) is ThesisState.STRENGTHENED

    def test_a_missing_instant_is_unavailable_never_agreement(self) -> None:
        """Absence is stated, never read as a market fact."""
        assert thesis_state(_observation(0), None, Direction.LONG) is ThesisState.UNAVAILABLE
        assert thesis_state(None, _observation(3), Direction.LONG) is ThesisState.UNAVAILABLE

    def test_the_sign_convention_is_mirrored_for_shorts(self) -> None:
        """A SHORT reads the same structures with the opposite sign, not the same one."""
        entry = _observation(0, setup="sustained_lower", execution="sustained_lower")
        held = _observation(3, setup="sustained_lower", execution="sustained_lower")
        assert thesis_state(entry, held, Direction.SHORT) is ThesisState.INTACT
        reversed_ = _observation(3, setup="sustained_higher", execution="sustained_higher")
        assert thesis_state(entry, reversed_, Direction.SHORT) is ThesisState.INVALIDATED
        # ...and the identical pair read as a LONG says the opposite of both.
        assert thesis_state(entry, held, Direction.LONG) is ThesisState.INVALIDATED

    def test_only_invalidation_and_conflict_are_actionable(self) -> None:
        """`WEAKENED` is excluded from `is_adverse`, and that exclusion is the rule."""
        assert ThesisState.INVALIDATED.is_adverse
        assert ThesisState.CONFLICTED.is_adverse
        assert not ThesisState.WEAKENED.is_adverse
        assert not ThesisState.INTACT.is_adverse
        assert not ThesisState.UNAVAILABLE.is_adverse

    def test_a_bad_direction_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="LONG or SHORT"):
            thesis_state(_observation(0), _observation(1), "up")  # type: ignore[arg-type]


class TestTimeline:
    def test_the_lookup_is_exact_never_nearest(self) -> None:
        """A bar with no instant returns None rather than a neighbour's structure."""
        timeline = ThesisTimeline(
            symbol="BTCUSDT", observations={0: _observation(0), 5: _observation(5)}
        )
        assert timeline.at(0) is not None
        assert timeline.at(5) is not None
        assert timeline.at(3) is None
        assert timeline.at(4) is None

    def test_a_miskeyed_observation_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="own bar_index"):
            ThesisTimeline(symbol="BTCUSDT", observations={7: _observation(0)})

    def test_a_foreign_symbol_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="holds a ETHUSDT observation"):
            ThesisTimeline(
                symbol="BTCUSDT",
                observations={0: _observation(0, symbol="ETHUSDT")},
            )


class TestExcursionArithmetic:
    def test_giveback_is_peak_minus_close_and_never_negative(self) -> None:
        track = _track(GIVEBACK_PATH)
        third = track.checkpoint(3)
        assert third is not None
        assert third.peak_r == Decimal("2")
        assert third.close_r == Decimal("-0.4")
        assert third.giveback_r == Decimal("2.4")
        for checkpoint in track.checkpoints:
            assert checkpoint.giveback_r >= 0

    def test_a_monotone_winner_gives_nothing_back(self) -> None:
        rising = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "105", "100", "105"),
            _bar(2, "105", "110", "105", "110"),
            _bar(3, "110", "115", "110", "115"),
        )
        track = _track(rising)
        assert track.total_giveback_r == 0
        assert not track.gave_back_a_full_r
        for checkpoint in track.checkpoints:
            assert checkpoint.giveback_r == 0

    def test_the_full_r_giveback_flag_is_bxs_statistic(self) -> None:
        assert _track(GIVEBACK_PATH).gave_back_a_full_r

    def test_excursion_timings_are_first_arrivals(self) -> None:
        track = _track(GIVEBACK_PATH)
        # +0.5R first reached on bar 1 (high 108 = +0.8R); +1R, +1.5R and +2R all
        # first reached on bar 2 (high 120 = +2.0R).
        assert track.bars_to_excursion["0.5"] == 1
        assert track.bars_to_excursion["1.0"] == 2
        assert track.bars_to_excursion["1.5"] == 2
        assert track.bars_to_excursion["2.0"] == 2
        assert track.bars_to_peak_r == 2
        assert track.peak_r == Decimal("2")

    def test_an_unreached_threshold_is_absent_never_zero(self) -> None:
        flat = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "101", "99", "100"),
            _bar(2, "100", "101", "99", "100"),
            _bar(3, "100", "101", "99", "100"),
        )
        track = _track(flat)
        assert track.bars_to_excursion == {}
        assert track.excursions_reached == ()
        assert track.bars_to_adverse is None

    def test_the_adverse_timing_uses_the_declared_threshold(self) -> None:
        adverse = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "101", "99", "100"),     # -0.1R, not yet
            _bar(2, "100", "101", "94", "95"),      # -0.6R, crosses -0.5R
            _bar(3, "95", "96", "94", "95"),
        )
        track = _track(adverse)
        assert ADVERSE_THRESHOLD == Decimal("0.5")
        assert track.bars_to_adverse == 2

    def test_short_excursions_are_mirrored(self) -> None:
        """A SHORT's favourable extreme is the low, and the R signs follow."""
        falling = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "101", "92", "93"),
            _bar(2, "93", "94", "80", "82"),
            _bar(3, "82", "83", "80", "81"),
        )
        # Entry 100, stop 110 for a short: risk 10.
        track = _track(falling, direction=Direction.SHORT, stop=Decimal("110"))
        assert track.risk == Decimal("10")
        assert track.peak_r == Decimal("2")          # low 80 = +2R for a short
        assert track.checkpoint(1).close_r == Decimal("0.7")

    def test_the_path_is_not_truncated_by_any_exit(self) -> None:
        """The walk holds the position for the whole window. **The shared input.**

        A path stopped at the control's own exit could not answer whether a
        different rule would have done better afterwards, which is the entire
        question the milestone asks.
        """
        # This path stops out (low 85 < stop 90) on bar 2 and then recovers to a
        # new high on bar 3. The observation must still see bar 3.
        through_stop = (
            _bar(0, "100", "101", "99", "100"),
            _bar(1, "100", "104", "99", "103"),
            _bar(2, "103", "104", "85", "88"),
            _bar(3, "88", "125", "88", "124"),
        )
        track = _track(through_stop)
        assert track.checkpoint(3) is not None
        assert track.peak_r == Decimal("2.5")
        assert track.checkpoint(2).mae_r == Decimal("-1.5")


class TestGeometryRefusals:
    def test_a_zero_risk_geometry_is_refused_not_measured(self) -> None:
        with pytest.raises(SwingLabError, match="no risk denominator"):
            _track(GIVEBACK_PATH, stop=Decimal("100"))

    def test_an_inverted_stop_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="no risk denominator"):
            _track(GIVEBACK_PATH, stop=Decimal("110"))

    def test_a_path_with_no_entry_bar_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="no bar after signal index"):
            observe_path(
                GIVEBACK_PATH[:1], symbol="BTCUSDT", setup_id="s",
                direction=Direction.LONG, sample="development",
                signal_at=T0, signal_index=0, entry_price=ENTRY,
                initial_stop=STOP, target=TARGET, evaluation_window_bars=10,
            )

    @pytest.mark.parametrize("bad", [0, -1, True])
    def test_a_non_positive_checkpoint_is_refused(self, bad: object) -> None:
        with pytest.raises(SwingLabError, match="positive int"):
            observe_path(
                GIVEBACK_PATH, symbol="BTCUSDT", setup_id="s",
                direction=Direction.LONG, sample="development",
                signal_at=T0, signal_index=0, entry_price=ENTRY,
                initial_stop=STOP, target=TARGET, evaluation_window_bars=10,
                checkpoints=(bad,),  # type: ignore[arg-type]
            )

    def test_a_negative_giveback_cannot_be_constructed(self) -> None:
        with pytest.raises(SwingLabError, match="cannot be below the close"):
            PostEntryCheckpoint(
                bar=1, at=T0, close_r=Decimal("2"), mfe_r=Decimal("2"),
                mae_r=Decimal("0"), peak_r=Decimal("1"),
                giveback_r=Decimal("-1"), thesis=ThesisState.INTACT,
            )


class TestNoLookahead:
    """A checkpoint at bar *n* must be blind to every bar after *n*. **With a control.**"""

    @staticmethod
    def _mutate_from(bars, first: int):
        """Replace every bar from ``first`` onward with arbitrary distant prices."""
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

    def test_a_checkpoint_cannot_see_a_later_bar(self) -> None:
        original = _track(GIVEBACK_PATH)
        # Bar index 3 is checkpoint bar 3's own bar, so mutating from index 4
        # onward leaves every checkpoint's inputs untouched.
        mutated = _track(self._mutate_from(GIVEBACK_PATH + (_bar(4, "96", "97", "95", "96"),), 4))
        assert original.checkpoints == mutated.checkpoints

    def test_the_control_changes_when_the_decision_bar_is_mutated(self) -> None:
        """Non-vacuity: mutating a bar a checkpoint DOES read must move it."""
        original = _track(GIVEBACK_PATH)
        mutated = _track(self._mutate_from(GIVEBACK_PATH, 2))
        assert original.checkpoints != mutated.checkpoints
        # ...and specifically the checkpoint that reads bar index 2.
        assert original.checkpoint(1) == mutated.checkpoint(1)
        assert original.checkpoint(2) != mutated.checkpoint(2)

    def test_the_descriptive_half_does_move_under_a_future_mutation(self) -> None:
        """The labelling is checkable, not merely asserted in a docstring.

        `peak_r` is DESCRIPTIVE — a statement about the whole path — so a bar
        after the last checkpoint MUST be able to change it. If it could not,
        the field would be causal and mislabelled.
        """
        longer = GIVEBACK_PATH + (_bar(4, "96", "300", "95", "290"),)
        base = _track(longer)
        blunted = _track(
            longer[:4] + (_bar(4, "96", "97", "95", "96"),)
        )
        assert base.checkpoints == blunted.checkpoints      # causal half: frozen
        assert base.peak_r != blunted.peak_r                # descriptive half: moves
        assert base.bars_to_peak_r != blunted.bars_to_peak_r

    def test_a_checkpoint_reads_the_timeline_at_its_own_bar(self) -> None:
        """The observation consulted at checkpoint *n* is bar ``signal_index + n``."""
        timeline = ThesisTimeline(
            symbol="BTCUSDT",
            observations={
                0: _observation(0),
                1: _observation(1),
                2: _observation(2, setup="sustained_lower", execution="sustained_lower"),
                3: _observation(3),
            },
        )
        track = _track(GIVEBACK_PATH, timeline=timeline)
        assert track.checkpoint(1).thesis is ThesisState.INTACT
        # Bar 2's observation is the reversed one, and it lands on checkpoint 2.
        assert track.checkpoint(2).thesis is ThesisState.INVALIDATED
        assert track.checkpoint(3).thesis is ThesisState.INTACT

    def test_a_gap_in_the_timeline_is_unavailable_not_carried_forward(self) -> None:
        timeline = ThesisTimeline(
            symbol="BTCUSDT", observations={0: _observation(0), 1: _observation(1)}
        )
        track = _track(GIVEBACK_PATH, timeline=timeline)
        assert track.checkpoint(1).thesis is ThesisState.INTACT
        assert track.checkpoint(2).thesis is ThesisState.UNAVAILABLE
        assert track.checkpoint(3).thesis is ThesisState.UNAVAILABLE

    def test_no_timeline_at_all_leaves_every_state_unavailable(self) -> None:
        track = _track(GIVEBACK_PATH)
        assert {c.thesis for c in track.checkpoints} == {ThesisState.UNAVAILABLE}
        assert not track.entry_thesis_known


class TestDeclaredConstants:
    def test_the_checkpoints_end_at_the_evaluation_window_bound(self) -> None:
        """A checkpoint past the bound would observe bars no trade was given."""
        assert CHECKPOINT_BARS[-1] == 60
        assert CHECKPOINT_BARS == tuple(sorted(set(CHECKPOINT_BARS)))
        assert all(value >= 1 for value in CHECKPOINT_BARS)

    def test_the_excursion_rungs_match_the_geometry_outcome_layer(self) -> None:
        """BZ's rungs are BX's, so the two milestones' counts can be read together."""
        from fmis.swing_lab.geometry_outcome import R_THRESHOLDS

        assert EXCURSION_THRESHOLDS == R_THRESHOLDS

    def test_the_level_cap_is_declared(self) -> None:
        assert LEVELS_PER_SIDE == 5

    def test_a_checkpoint_beyond_the_window_is_simply_never_reached(self) -> None:
        """A window shorter than a checkpoint yields fewer checkpoints, not an error."""
        track = observe_path(
            GIVEBACK_PATH, symbol="BTCUSDT", setup_id="s",
            direction=Direction.LONG, sample="development",
            signal_at=T0, signal_index=0, entry_price=ENTRY,
            initial_stop=STOP, target=TARGET, evaluation_window_bars=2,
            checkpoints=(1, 2, 3, 60),
        )
        assert [c.bar for c in track.checkpoints] == [1, 2]
