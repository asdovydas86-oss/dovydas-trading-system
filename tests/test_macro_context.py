"""Milestone BU — measured macro facts: levels, yield moves, relationships.

Three properties are load-bearing here and each has its own section:

  * **A rate fact is built from the same window a price return would use**, so a
    yield's basis-point move and an index's percentage move describe the same
    span of observations and neither is quietly measured over more history.
  * **A relationship is refused before any arithmetic runs** when the two sides
    are not comparable, so no plausible-but-wrong number exists anywhere for a
    later change to surface.
  * **Alignment is explicit, named and reported.** A market trading seven days a
    week and one trading five do not observe the same dates; the shared dates
    are used and what each side lost is stated.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fmis.data.observation import ObservationSeries
from fmis.macro import (
    RELATIONSHIP_METRIC,
    ComparabilityKey,
    MacroReportError,
    build_rate_fact,
    comparability_key,
    macro_level,
    observations_reference,
    relate_markets,
)
from fmis.market_pulse import Horizon, QuantityKind
from tests.macro_helpers import day, macro_benchmark, yield_benchmark

H1 = Horizon(horizon_id="h1", bars=1, description="one observation")
H5 = Horizon(horizon_id="h5", bars=5, description="five observations")
H21 = Horizon(horizon_id="h21", bars=21, description="twenty-one observations")


def series(
    values: list[float],
    *,
    series_id: str = "fred SP500 1d",
    unit: str = "index points",
    start: int = 0,
    step_days: int = 1,
) -> ObservationSeries:
    return ObservationSeries(
        series_id=series_id,
        unit=unit,
        frequency="1d",
        timestamps=tuple(
            day(start + index * step_days) for index in range(len(values))
        ),
        values=tuple(values),
    )


def key(**kwargs) -> ComparabilityKey:
    base = dict(
        quantity_kind=QuantityKind.PRICE_LIKE,
        quote_unit="index points",
        observation_interval="1d",
        horizon_id="h5",
        metric=RELATIONSHIP_METRIC,
    )
    base.update(kwargs)
    return ComparabilityKey(**base)


# --------------------------------------------------------------------------
# Levels
# --------------------------------------------------------------------------


def test_a_level_is_the_last_observation_with_its_unit_and_instant() -> None:
    level = macro_level(macro_benchmark(), series([1.0, 2.0, 3.0]), source="fred SP500")
    assert level.value == 3.0
    assert level.unit == "index points"
    assert level.observed_at == day(2)
    assert level.source == "fred SP500"
    assert level.quantity_kind is QuantityKind.PRICE_LIKE


def test_an_empty_series_has_no_level_rather_than_a_level_of_zero() -> None:
    with pytest.raises(MacroReportError, match="rather than a level of zero"):
        macro_level(macro_benchmark(), series([]), source="fred")


def test_a_level_carries_the_benchmark_s_unit_and_not_the_series_unit() -> None:
    """The registry decides what a market is quoted in; a source's own label is
    prose this build does not parse."""
    level = macro_level(
        macro_benchmark(quote_unit="volatility points"),
        series([1.0, 2.0], unit="whatever the source said"),
        source="fred",
    )
    assert level.unit == "volatility points"


def test_a_level_refuses_something_that_is_not_a_benchmark() -> None:
    with pytest.raises(TypeError, match="must be a Benchmark"):
        macro_level("SPX", series([1.0]), source="fred")


# --------------------------------------------------------------------------
# Rate facts
# --------------------------------------------------------------------------


def test_a_rate_fact_measures_each_horizon_from_the_same_window_a_return_uses() -> None:
    """A one-observation horizon compares the last value with the one before it,
    exactly as `period_return` does — so the two are the same span."""
    values = [4.10, 4.20, 4.30, 4.40, 4.50, 4.60, 4.70]
    fact = build_rate_fact(
        yield_benchmark(),
        series(values, unit="percent per annum"),
        horizons=(H1, H5),
        source="fred DGS10",
    )
    assert round(fact.change_for("h1").basis_points, 6) == 10.0
    # Six observations back from 4.70 is 4.20: five moves, +50 bp.
    assert round(fact.change_for("h5").basis_points, 6) == 50.0
    assert fact.level.value == 4.70


def test_a_rate_fact_reports_a_window_it_cannot_fill_rather_than_shortening_it() -> None:
    """*A 21-observation move computed from nine is a different measurement
    wearing the same label.*"""
    fact = build_rate_fact(
        yield_benchmark(),
        series([4.1, 4.2, 4.3], unit="percent per annum"),
        horizons=(H1, H21),
        source="fred",
    )
    assert fact.change_for("h1") is not None
    assert fact.change_for("h21") is None
    reasons = dict(fact.unavailable_horizons)
    assert "h21" in reasons
    assert "different measurement" in reasons["h21"]


def test_a_price_like_market_has_no_rate_fact() -> None:
    """*A rate fact describes a rate.* The type refuses the wrong quantity."""
    with pytest.raises(MacroReportError, match="a rate fact describes a rate"):
        build_rate_fact(
            macro_benchmark(), series([1.0, 2.0]), horizons=(H1,), source="fred"
        )


def test_a_rate_fact_cannot_be_assembled_around_a_price_like_level() -> None:
    """The model's own guard, independent of the builder's."""
    from fmis.macro import MacroLevel, RateFact, rate_change

    price_level = MacroLevel(
        benchmark_id="SPX",
        display_name="S&P 500",
        value=1.0,
        unit="index points",
        quantity_kind=QuantityKind.PRICE_LIKE,
        observed_at=day(0),
        source="fred",
    )
    with pytest.raises(MacroReportError, match="basis-point change of a"):
        RateFact(
            benchmark_id="SPX",
            display_name="S&P 500",
            level=price_level,
            changes=(("h1", rate_change(1.0, 2.0)),),
        )


def test_a_rate_fact_refuses_one_horizon_reported_twice() -> None:
    from fmis.macro import MacroLevel, RateFact, rate_change

    level = MacroLevel(
        benchmark_id="US10Y",
        display_name="US 10-year",
        value=4.7,
        unit="percent per annum",
        quantity_kind=QuantityKind.RATE_LIKE,
        observed_at=day(0),
        source="fred",
    )
    with pytest.raises(MacroReportError, match="reports horizon 'h1' twice"):
        RateFact(
            benchmark_id="US10Y",
            display_name="US 10-year",
            level=level,
            changes=(("h1", rate_change(1.0, 2.0)), ("h1", rate_change(2.0, 3.0))),
        )


def test_a_horizon_cannot_be_both_measured_and_unavailable() -> None:
    from fmis.macro import MacroLevel, RateFact, rate_change

    level = MacroLevel(
        benchmark_id="US10Y",
        display_name="US 10-year",
        value=4.7,
        unit="percent per annum",
        quantity_kind=QuantityKind.RATE_LIKE,
        observed_at=day(0),
        source="fred",
    )
    with pytest.raises(MacroReportError, match="one window has one outcome"):
        RateFact(
            benchmark_id="US10Y",
            display_name="US 10-year",
            level=level,
            changes=(("h1", rate_change(1.0, 2.0)),),
            unavailable_horizons=(("h1", "too short"),),
        )


# --------------------------------------------------------------------------
# Comparability keys are built from the registry, not from a label
# --------------------------------------------------------------------------


def test_a_key_takes_its_cadence_from_the_benchmark_s_own_instrument() -> None:
    """*A market's declared cadence and the cadence its comparability is judged
    on cannot diverge.*"""
    built = comparability_key(macro_benchmark(), H5, metric="period_return")
    assert built.observation_interval == "1d"
    assert built.quote_unit == "index points"
    assert built.horizon_id == "h5"
    assert built.quantity_kind is QuantityKind.PRICE_LIKE


def test_an_unsupported_market_has_no_key_because_it_produced_no_measurement() -> None:
    from fmis.market_pulse import Benchmark, MarketCategory, TradingSchedule

    dark = Benchmark(
        benchmark_id="XAU",
        display_name="Gold",
        category=MarketCategory.COMMODITY,
        schedule=TradingSchedule.SESSION_BOUND,
        quote_unit="USD",
        unsupported_reason="no source",
    )
    with pytest.raises(MacroReportError, match="nothing to compare"):
        comparability_key(dark, H5, metric="period_return")


# --------------------------------------------------------------------------
# Relationships — refused before any arithmetic
# --------------------------------------------------------------------------


def test_an_incomparable_pair_is_refused_and_no_number_is_computed() -> None:
    left = series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
    right = series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0], series_id="other")
    result = relate_markets(
        "US10Y",
        left,
        key(quantity_kind=QuantityKind.RATE_LIKE),
        "BTC",
        right,
        key(),
        H5,
    )
    assert not result.is_measured
    assert result.is_refused
    assert result.value is None
    assert "different quantity kind" in result.unavailable_reason
    assert result.observation_count == 0


def test_a_refusal_is_a_different_outcome_from_a_short_window() -> None:
    """*Collapsing the two would tell the owner to wait for more data about a
    comparison that will never become valid.*"""
    short_left = series([1.0, 2.0])
    short_right = series([1.0, 2.0], series_id="other")
    short = relate_markets(
        "SPX", short_left, key(), "BTC", short_right, key(), H5
    )
    assert not short.is_measured
    assert not short.is_refused
    assert "share" in short.unavailable_reason

    refused = relate_markets(
        "US10Y",
        series([1.0] * 10),
        key(quantity_kind=QuantityKind.RATE_LIKE),
        "BTC",
        series([1.0] * 10, series_id="other"),
        key(),
        H5,
    )
    assert refused.is_refused


def test_a_horizon_shorter_than_the_metric_allows_is_a_configuration_fault() -> None:
    """Worded so it cannot be mistaken for a market outage: no pair could
    satisfy it."""
    tiny = Horizon(horizon_id="tiny", bars=1, description="one")
    result = relate_markets(
        "SPX",
        series([1.0, 2.0, 3.0]),
        key(horizon_id="tiny"),
        "BTC",
        series([1.0, 2.0, 3.0], series_id="other"),
        key(horizon_id="tiny"),
        tiny,
    )
    assert not result.is_measured
    assert "configuration fault" in result.unavailable_reason


# --------------------------------------------------------------------------
# Relationships — alignment
# --------------------------------------------------------------------------


def rising(count: int, *, series_id: str, step: float = 1.0, every: int = 1):
    return series(
        [100.0 + step * i for i in range(count)],
        series_id=series_id,
        step_days=every,
    )


def test_two_perfectly_aligned_series_correlate_over_the_named_window() -> None:
    left = rising(12, series_id="left")
    right = rising(12, series_id="right", step=2.0)
    result = relate_markets("SPX", left, key(), "BTC", right, key(), H5)
    assert result.is_measured
    assert result.observation_count == H5.required_observations
    assert result.subject_dropped == 0
    assert result.reference_dropped == 0
    assert result.aligned_count == 12
    assert result.window_start == left.timestamps[-6]
    assert result.window_end == left.timestamps[-1]


def test_a_perfect_positive_relationship_is_one() -> None:
    """Two markets whose returns are identical, at different price scales.

    The returns must *vary*: a constant-return pair has zero variance and is
    mathematically undefined rather than perfectly correlated, which the test
    below pins separately.
    """
    values = [100.0, 110.0, 105.0, 118.0, 112.0, 125.0, 120.0]
    left = series(values)
    right = series([value * 3.0 for value in values], series_id="right")
    result = relate_markets("A", left, key(), "B", right, key(), H5)
    assert result.value == pytest.approx(1.0)


def test_a_pair_whose_returns_never_vary_is_undefined_not_perfectly_correlated() -> None:
    """Two series each doubling every step have a constant return sequence, so
    the correlation has a zero denominator. That is not a reading of one."""
    left = series([1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0])
    right = series([5.0, 10.0, 20.0, 40.0, 80.0, 160.0, 320.0], series_id="right")
    result = relate_markets("A", left, key(), "B", right, key(), H5)
    assert not result.is_measured
    assert "undefined" in result.unavailable_reason


def test_a_perfect_negative_relationship_is_minus_one() -> None:
    left = series([100.0, 110.0, 100.0, 110.0, 100.0, 110.0, 100.0])
    right = series([100.0, 90.0, 100.0, 90.0, 100.0, 90.0, 100.0], series_id="right")
    result = relate_markets("A", left, key(), "B", right, key(), H5)
    assert result.value == pytest.approx(-1.0)


def test_a_value_can_never_fall_outside_the_bounds_a_correlation_has() -> None:
    left = rising(30, series_id="left")
    right = rising(30, series_id="right", step=-0.5)
    result = relate_markets("A", left, key(), "B", right, key(), H21)
    assert -1.0 <= result.value <= 1.0


def test_a_constant_series_makes_the_relationship_undefined_and_not_zero() -> None:
    left = series([100.0] * 8)
    right = rising(8, series_id="right")
    result = relate_markets("A", left, key(), "B", right, key(), H5)
    assert not result.is_measured
    assert "undefined" in result.unavailable_reason
    assert "not a reading of zero" in result.unavailable_reason


def test_only_shared_dates_are_used_and_what_each_side_lost_is_stated() -> None:
    """The five-day/seven-day problem, which is the normal case for this page.

    ``right`` observes every day; ``left`` observes every second day. They share
    exactly ``left``'s dates, and the report says how many observations that
    cost each side.
    """
    left = series([100.0 + i for i in range(10)], step_days=2)
    right = series(
        [100.0 + i * 0.5 for i in range(20)], series_id="right", step_days=1
    )
    result = relate_markets("SPX", left, key(), "BTC", right, key(), H5)
    assert result.is_measured
    assert result.aligned_count == 10
    assert result.subject_dropped == 0
    assert result.reference_dropped == 10
    assert result.observation_count == 6


def test_a_pair_sharing_too_few_dates_reports_the_shortfall_not_a_number() -> None:
    left = series([1.0, 2.0, 3.0], step_days=5)
    right = series([1.0] * 20, series_id="right", step_days=1)
    result = relate_markets("SPX", left, key(), "BTC", right, key(), H21)
    assert not result.is_measured
    assert "share" in result.unavailable_reason
    assert result.aligned_count < H21.required_observations


def test_two_series_sharing_no_date_at_all_are_reported_rather_than_crashing() -> None:
    left = series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0], start=0, step_days=2)
    right = series(
        [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0], series_id="right", start=1, step_days=2
    )
    result = relate_markets("SPX", left, key(), "BTC", right, key(), H5)
    assert not result.is_measured
    assert result.aligned_count == 0


def test_the_window_is_taken_after_alignment_and_not_before() -> None:
    """Tailing first would take the last N of each series and then find few in
    common; aligning first finds every shared date and then takes the last N."""
    left = series([100.0 + i for i in range(10)], step_days=2)
    right = series([100.0 + i for i in range(20)], series_id="right", step_days=1)
    result = relate_markets("SPX", left, key(), "BTC", right, key(), H5)
    assert result.is_measured
    assert result.window_end == left.timestamps[-1]


def test_the_reported_window_cannot_exceed_the_shared_dates() -> None:
    """The model refuses the contradiction outright."""
    from fmis.macro import CrossAssetRelationship

    with pytest.raises(MacroReportError, match="cannot use more observations"):
        CrossAssetRelationship(
            subject_id="A",
            reference_id="B",
            metric=RELATIONSHIP_METRIC,
            value=0.5,
            unavailable_reason=None,
            observation_count=10,
            aligned_count=3,
            window_start=day(0),
            window_end=day(9),
        )


def test_a_relationship_never_names_one_market_on_both_sides() -> None:
    from fmis.macro import CrossAssetRelationship

    with pytest.raises(MacroReportError, match="cannot be related to itself"):
        CrossAssetRelationship(
            subject_id="BTC",
            reference_id="BTC",
            metric=RELATIONSHIP_METRIC,
            value=1.0,
            unavailable_reason=None,
            observation_count=3,
            aligned_count=3,
            window_start=day(0),
            window_end=day(2),
        )


def test_a_measured_relationship_must_name_the_window_it_spanned() -> None:
    from fmis.macro import CrossAssetRelationship

    with pytest.raises(MacroReportError, match="names no window"):
        CrossAssetRelationship(
            subject_id="A",
            reference_id="B",
            metric=RELATIONSHIP_METRIC,
            value=0.5,
            unavailable_reason=None,
            observation_count=3,
            aligned_count=3,
        )


def test_an_unmeasured_relationship_may_not_claim_a_window() -> None:
    from fmis.macro import CrossAssetRelationship

    with pytest.raises(MacroReportError, match="spans nothing"):
        CrossAssetRelationship(
            subject_id="A",
            reference_id="B",
            metric=RELATIONSHIP_METRIC,
            value=None,
            unavailable_reason="too short",
            observation_count=0,
            aligned_count=0,
            window_start=day(0),
            window_end=day(2),
        )


def test_a_correlation_outside_its_own_bounds_is_a_broken_reading() -> None:
    from fmis.macro import CrossAssetRelationship

    with pytest.raises(MacroReportError, match=r"outside \[-1, 1\]"):
        CrossAssetRelationship(
            subject_id="A",
            reference_id="B",
            metric=RELATIONSHIP_METRIC,
            value=1.5,
            unavailable_reason=None,
            observation_count=3,
            aligned_count=3,
            window_start=day(0),
            window_end=day(2),
        )


def test_a_relationship_carries_no_causal_field() -> None:
    """*Display the number. Interpret later.* There is nowhere for a causal
    claim, a lead/lag or a significance flag to live."""
    from fmis.macro import CrossAssetRelationship

    fields = set(CrossAssetRelationship.__dataclass_fields__)
    for banned in (
        "cause",
        "causes",
        "driver",
        "lead",
        "lag",
        "significance",
        "p_value",
        "direction",
        "influence",
        "regime",
    ):
        assert banned not in fields


def test_the_relationship_is_symmetric_in_value_but_records_the_order_given() -> None:
    left = rising(12, series_id="left")
    right = rising(12, series_id="right", step=-0.4)
    forward = relate_markets("A", left, key(), "B", right, key(), H5)
    backward = relate_markets("B", right, key(), "A", left, key(), H5)
    assert forward.value == pytest.approx(backward.value)
    assert forward.subject_id == "A" and backward.subject_id == "B"


def test_relate_refuses_a_horizon_that_is_not_one() -> None:
    with pytest.raises(TypeError, match="must be a Horizon"):
        relate_markets(
            "A", series([1.0]), key(), "B", series([1.0], series_id="r"), key(), "h5"
        )


# --------------------------------------------------------------------------
# The reference choice is stated, not emergent
# --------------------------------------------------------------------------


def test_the_reference_is_the_first_market_in_the_stated_order_that_has_data() -> None:
    available = {"ETH": series([1.0]), "SOL": series([2.0])}
    assert observations_reference(available, ("BTC", "ETH", "SOL")) == "ETH"


def test_no_reference_is_named_when_nothing_was_read() -> None:
    assert observations_reference({}, ("BTC", "ETH")) is None


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_two_runs_over_one_pair_produce_one_relationship() -> None:
    left = rising(30, series_id="left")
    right = rising(30, series_id="right", step=0.3)
    first = relate_markets("A", left, key(), "B", right, key(), H21)
    second = relate_markets("A", left, key(), "B", right, key(), H21)
    assert first == second
