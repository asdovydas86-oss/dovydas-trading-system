"""Milestone CA's measurement vocabulary: the gate ladder and the forward outcome.

Every claim CA makes about *where an instant stopped* and *what happened next*
rests on the two functions tested here. They are the two places a sign error or
an off-by-one would silently reverse the milestone's conclusion.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.paper.models import PriceBar
from fmis.swing_lab.admission import (
    EXCURSION_RACE_ATR,
    FORWARD_HORIZONS,
    AdmissionStage,
    DecisionInstant,
    RaceOutcome,
    atr_series,
    forward_outcome,
    payload_of_stage_counts,
    stage_of,
)
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.persistence import ThesisObservation
from fmis.swing_setup.models import Direction

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _bar(index: int, open_: str, high: str, low: str, close: str) -> PriceBar:
    return PriceBar(
        symbol="BTCUSDT",
        interval="4h",
        open_time=T0 + timedelta(hours=4 * index),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
    )


def _flat(count: int, price: str = "100") -> list[PriceBar]:
    return [_bar(i, price, price, price, price) for i in range(count)]


def _observation(**overrides) -> ThesisObservation:
    payload = dict(
        symbol="BTCUSDT",
        as_of=T0,
        bar_index=10,
        context_structural_trend="sustained_higher",
        setup_structural_trend="sustained_higher",
        execution_structural_trend="sustained_higher",
        context_regime_structure="trending",
        evidence_state="proceed",
        evidence_dominant_alignment="upward",
        decision_context_state="sufficient",
        setup_state="confirmed",
        setup_direction="long",
        execution_close=100.0,
        upper_levels=(),
        lower_levels=(),
    )
    payload.update(overrides)
    return ThesisObservation(**payload)


class TestTheGateLadderIsProductionsOwnPrecedence:
    def test_an_insufficient_context_outranks_everything_below_it(self) -> None:
        """Production checks sufficiency FIRST, so a non-trending regime beneath
        an insufficient context must NOT be blamed on the regime gate."""
        stage = stage_of(
            _observation(
                decision_context_state="insufficient",
                context_regime_structure="ranging",
                setup_state="wait",
                setup_direction=None,
            ),
            is_first_confirmation=False,
        )
        assert stage is AdmissionStage.CONTEXT_INSUFFICIENT

    def test_a_non_trending_regime_blocks_before_the_tally(self) -> None:
        stage = stage_of(
            _observation(
                context_regime_structure="transitioning",
                setup_state="wait",
                setup_direction=None,
            ),
            is_first_confirmation=False,
        )
        assert stage is AdmissionStage.REGIME_BLOCKED

    def test_a_wait_past_the_gate_is_the_tally_disagreeing(self) -> None:
        stage = stage_of(
            _observation(setup_state="wait", setup_direction=None),
            is_first_confirmation=False,
        )
        assert stage is AdmissionStage.TALLY_DISAGREED

    def test_a_candidate_is_the_eligible_but_rejected_population(self) -> None:
        stage = stage_of(
            _observation(setup_state="candidate"), is_first_confirmation=False
        )
        assert stage is AdmissionStage.UNCONFIRMED

    def test_a_first_confirmation_is_admitted(self) -> None:
        assert (
            stage_of(_observation(), is_first_confirmation=True)
            is AdmissionStage.ADMITTED
        )

    def test_a_later_confirmation_of_the_same_opportunity_is_not(self) -> None:
        """One opportunity admitted twice would measure one thesis twice."""
        assert (
            stage_of(_observation(), is_first_confirmation=False)
            is AdmissionStage.CONFIRMED_REPEAT
        )

    def test_an_unknown_setup_state_is_refused_rather_than_guessed(self) -> None:
        with pytest.raises(SwingLabError, match="does not define"):
            stage_of(
                _observation(setup_state="probably_fine"), is_first_confirmation=False
            )

    def test_it_refuses_a_foreign_type(self) -> None:
        with pytest.raises(TypeError):
            stage_of(object(), is_first_confirmation=False)  # type: ignore[arg-type]

    def test_exactly_the_three_top_rungs_carry_a_direction(self) -> None:
        directional = {item for item in AdmissionStage if item.has_direction}
        assert directional == {
            AdmissionStage.UNCONFIRMED,
            AdmissionStage.CONFIRMED_REPEAT,
            AdmissionStage.ADMITTED,
        }

    def test_the_census_covers_every_stage(self) -> None:
        counts = payload_of_stage_counts(())
        assert set(counts) == {item.value for item in AdmissionStage}


class TestDecisionInstantRefusesAnImpossibleOne:
    def _instant(self, **overrides) -> DecisionInstant:
        payload = dict(
            symbol="BTCUSDT",
            sample="development",
            as_of=T0,
            bar_index=10,
            stage=AdmissionStage.ADMITTED,
            direction=Direction.LONG,
            close=100.0,
            atr=1.0,
            context_regime_structure="trending",
            context_regime_volatility="steady",
            context_structural_trend="sustained_higher",
            setup_structural_trend="sustained_higher",
            evidence_state="proceed",
        )
        payload.update(overrides)
        return DecisionInstant(**payload)

    def test_a_non_positive_atr_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="broken measurement"):
            self._instant(atr=0.0)

    def test_a_directional_stage_without_a_direction_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="carries no direction"):
            self._instant(direction=None)

    def test_a_non_directional_stage_carrying_one_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="had formed none"):
            self._instant(stage=AdmissionStage.REGIME_BLOCKED)

    def test_identity_addresses_it_within_its_universe(self) -> None:
        assert self._instant().identity == ("BTCUSDT", 10)


class TestTheForwardOutcome:
    def test_the_entry_is_the_open_of_the_bar_after_the_signal(self) -> None:
        """`simulate_trade`'s own rule, reproduced rather than reinvented."""
        bars = _flat(80)
        bars[11] = _bar(11, "200", "200", "200", "200")
        outcome = forward_outcome(
            bars, signal_index=10, direction=Direction.LONG, atr=1.0
        )
        assert outcome.entry == Decimal("200")

    def test_a_horizon_reads_the_bar_at_signal_plus_horizon(self) -> None:
        """BZ's checkpoint semantics: checkpoint n observes bars[signal + n]."""
        bars = _flat(80)
        bars[13] = _bar(13, "100", "103", "100", "103")
        outcome = forward_outcome(
            bars, signal_index=10, direction=Direction.LONG, atr=1.0, horizons=(3,)
        )
        assert outcome.at(3) == Decimal("3")

    def test_a_short_is_the_exact_negative_of_a_long(self) -> None:
        """Antisymmetry in direction. The declared degeneracy depends on it."""
        bars = _flat(80)
        for index in range(11, 80):
            bars[index] = _bar(index, "100", "104", "97", "102")
        long = forward_outcome(bars, signal_index=10, direction=Direction.LONG, atr=2.0)
        short = forward_outcome(bars, signal_index=10, direction=Direction.SHORT, atr=2.0)
        for horizon in FORWARD_HORIZONS:
            assert long.forward[horizon] == -short.forward[horizon]
            # A long's favourable extreme is a short's adverse one, exactly.
            assert long.mfe[horizon] == -short.mae[horizon]
            assert long.mae[horizon] == -short.mfe[horizon]

    def test_the_favourable_excursion_is_never_negative(self) -> None:
        bars = _flat(80)
        for index in range(11, 80):
            bars[index] = _bar(index, "100", "100", "80", "80")
        outcome = forward_outcome(
            bars, signal_index=10, direction=Direction.LONG, atr=1.0
        )
        for horizon in FORWARD_HORIZONS:
            assert outcome.mfe[horizon] >= 0

    def test_the_adverse_excursion_is_never_positive(self) -> None:
        bars = _flat(80)
        for index in range(11, 80):
            bars[index] = _bar(index, "100", "130", "100", "130")
        outcome = forward_outcome(
            bars, signal_index=10, direction=Direction.LONG, atr=1.0
        )
        for horizon in FORWARD_HORIZONS:
            assert outcome.mae[horizon] <= 0

    def test_the_atr_is_the_denominator(self) -> None:
        bars = _flat(80)
        bars[34] = _bar(34, "100", "110", "100", "110")
        outcome = forward_outcome(
            bars, signal_index=10, direction=Direction.LONG, atr=4.0, horizons=(24,)
        )
        assert outcome.at(24) == Decimal("10") / Decimal("4")

    def test_a_truncated_horizon_is_refused_not_shortened(self) -> None:
        """Silently shortening a horizon is a different measurement, same name."""
        with pytest.raises(SwingLabError, match="refused rather than silently"):
            forward_outcome(
                _flat(40), signal_index=10, direction=Direction.LONG, atr=1.0
            )

    def test_a_non_positive_atr_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="ATR must be positive"):
            forward_outcome(
                _flat(80), signal_index=10, direction=Direction.LONG, atr=0.0
            )

    def test_a_bad_direction_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="must be LONG or SHORT"):
            forward_outcome(
                _flat(80), signal_index=10, direction="up", atr=1.0  # type: ignore[arg-type]
            )

    def test_a_non_positive_horizon_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="positive int"):
            forward_outcome(
                _flat(80), signal_index=10, direction=Direction.LONG, atr=1.0,
                horizons=(0,),
            )

    def test_an_empty_horizon_set_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="at least one horizon"):
            forward_outcome(
                _flat(80), signal_index=10, direction=Direction.LONG, atr=1.0,
                horizons=(),
            )

    def test_asking_for_an_unmeasured_horizon_is_refused(self) -> None:
        outcome = forward_outcome(
            _flat(80), signal_index=10, direction=Direction.LONG, atr=1.0, horizons=(3,)
        )
        with pytest.raises(SwingLabError, match="was not measured"):
            outcome.at(24)

    def test_an_eighteen_digit_price_keeps_its_precision(self) -> None:
        """A Decimal that went through a float would lose this exactly."""
        bars = [
            _bar(i, "1.000000000000000001", "1.000000000000000001",
                 "1.000000000000000001", "1.000000000000000001")
            for i in range(80)
        ]
        bars[34] = _bar(
            34, "1.000000000000000001", "1.000000000000000002",
            "1.000000000000000001", "1.000000000000000002",
        )
        outcome = forward_outcome(
            bars, signal_index=10, direction=Direction.LONG, atr=1.0, horizons=(24,)
        )
        assert outcome.at(24) == Decimal("0.000000000000000001")


class TestTheExcursionRace:
    def test_reaching_the_favourable_threshold_first_settles_favourable(self) -> None:
        bars = _flat(80)
        bars[12] = _bar(12, "100", "102", "100", "102")
        outcome = forward_outcome(
            bars, signal_index=10, direction=Direction.LONG, atr=1.0, horizons=(6,)
        )
        assert outcome.race[6] is RaceOutcome.FAVOURABLE

    def test_reaching_the_adverse_threshold_first_settles_adverse(self) -> None:
        bars = _flat(80)
        bars[12] = _bar(12, "100", "100", "98", "98")
        outcome = forward_outcome(
            bars, signal_index=10, direction=Direction.LONG, atr=1.0, horizons=(6,)
        )
        assert outcome.race[6] is RaceOutcome.ADVERSE

    def test_one_bar_spanning_both_is_refused_not_ordered(self) -> None:
        """The execution timeframe cannot say which was touched first, so CA
        records the ambiguity rather than guessing an intrabar path."""
        bars = _flat(80)
        bars[12] = _bar(12, "100", "102", "98", "100")
        outcome = forward_outcome(
            bars, signal_index=10, direction=Direction.LONG, atr=1.0, horizons=(6,)
        )
        assert outcome.race[6] is RaceOutcome.AMBIGUOUS

    def test_neither_threshold_reached_is_a_first_class_answer(self) -> None:
        outcome = forward_outcome(
            _flat(80), signal_index=10, direction=Direction.LONG, atr=1.0, horizons=(6,)
        )
        assert outcome.race[6] is RaceOutcome.NEITHER

    def test_the_race_settles_once_and_stays_settled(self) -> None:
        bars = _flat(80)
        bars[12] = _bar(12, "100", "102", "100", "102")
        bars[20] = _bar(20, "100", "100", "90", "90")
        outcome = forward_outcome(
            bars, signal_index=10, direction=Direction.LONG, atr=1.0,
            horizons=(6, 12, 24),
        )
        assert outcome.race[6] is RaceOutcome.FAVOURABLE
        assert outcome.race[24] is RaceOutcome.FAVOURABLE

    def test_the_race_threshold_is_one_atr_not_one_price_unit(self) -> None:
        """A 2-unit move at ATR 4 is half an ATR and must NOT settle the race."""
        bars = _flat(80)
        bars[12] = _bar(12, "100", "102", "100", "102")
        outcome = forward_outcome(
            bars, signal_index=10, direction=Direction.LONG, atr=4.0, horizons=(6,)
        )
        assert outcome.race[6] is RaceOutcome.NEITHER
        assert EXCURSION_RACE_ATR == Decimal("1.0")


class TestTheAtrIsProductions:
    def test_it_matches_the_production_feature_bar_for_bar(self) -> None:
        from fmis.data.models import Candle, CandleSeries
        from fmis.features.indicators.atr import AverageTrueRange
        from fmis.features.types import FeatureContext
        from fmis.pipeline.regime import FAST_ATR_PERIOD

        bars = [
            _bar(i, "100", str(100 + (i % 7)), str(95 - (i % 5)), str(98 + (i % 3)))
            for i in range(60)
        ]
        series = atr_series(bars, limit=30)
        feature = AverageTrueRange(FAST_ATR_PERIOD)
        for index in (20, 35, 59):
            window = bars[max(0, index - 29) : index + 1]
            expected = feature.compute(
                FeatureContext(
                    primary=CandleSeries(
                        symbol="BTCUSDT",
                        timeframe="4h",
                        candles=tuple(
                            Candle(
                                timestamp=b.open_time, symbol=b.symbol,
                                timeframe=b.interval, open=float(b.open),
                                high=float(b.high), low=float(b.low),
                                close=float(b.close), volume=0.0, is_closed=True,
                            )
                            for b in window
                        ),
                    )
                )
            ).value
            assert series[index] == expected

    def test_a_warming_up_window_reports_absence_not_zero(self) -> None:
        series = atr_series(_flat(60), limit=250)
        assert series[0] is None
        assert series[5] is None

    def test_a_flat_series_has_no_usable_atr(self) -> None:
        """Zero true range is a broken denominator, reported as absent."""
        assert atr_series(_flat(60), limit=30)[59] is None

    def test_an_empty_series_is_empty(self) -> None:
        assert atr_series([], limit=30) == ()

    def test_a_non_positive_limit_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="positive int"):
            atr_series(_flat(60), limit=0)
