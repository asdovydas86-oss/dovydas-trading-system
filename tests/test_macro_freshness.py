"""Milestone BU — freshness by publication schedule, not by one global bound.

The brief's rule, and the two failures it names:

    Do not call a daily macro series stale because it did not update in an hour.
    Do not call a 1h crypto series fresh after 2 days.

One threshold cannot satisfy both, so a threshold is not what this build uses. A
policy states how often a source publishes and how late it is allowed to be, and
a reading is *behind schedule* only when its age exceeds what those two explain.
Every policy must carry the basis its figures came from, so that the result is a
derived fact about a source rather than an invented judgement about a market.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fmis.market_pulse import (
    CRYPTO_FRESHNESS,
    FRED_DAILY_FRESHNESS,
    FRED_LAGGED_WEEKLY_FRESHNESS,
    DEFAULT_PULSE_UNIVERSE,
    FreshnessPolicy,
    FreshnessState,
    MACRO_PROVIDER,
    PULSE_PROVIDER,
)

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)


def policy(period: timedelta = DAY, tolerance: timedelta = DAY) -> FreshnessPolicy:
    return FreshnessPolicy(
        publication_period=period, tolerance=tolerance, basis="a test policy"
    )


# --------------------------------------------------------------------------
# The bound is derived, never stored
# --------------------------------------------------------------------------


def test_the_bound_is_the_period_plus_the_tolerance() -> None:
    assert policy(DAY, timedelta(days=4)).behind_schedule_after == timedelta(days=5)


def test_the_bound_is_computed_so_it_cannot_drift_from_its_parts() -> None:
    """Computed, never stored — the rule `HorizonMove.measured_span` follows."""
    assert "behind_schedule_after" not in FreshnessPolicy.__dataclass_fields__


def test_a_policy_must_state_the_basis_of_its_figures() -> None:
    """*A policy with no basis would be an invented threshold wearing a
    respectable name.*"""
    assert "basis" in FreshnessPolicy.__dataclass_fields__
    with pytest.raises(ValueError, match="must not be blank"):
        FreshnessPolicy(publication_period=DAY, tolerance=DAY, basis="  ")


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(0), FreshnessState.ON_SCHEDULE),
        (timedelta(days=1), FreshnessState.ON_SCHEDULE),
        (timedelta(days=4, hours=23), FreshnessState.ON_SCHEDULE),
        (timedelta(days=5), FreshnessState.ON_SCHEDULE),
        (timedelta(days=5, seconds=1), FreshnessState.BEHIND_SCHEDULE),
        (timedelta(days=30), FreshnessState.BEHIND_SCHEDULE),
    ],
)
def test_an_age_is_classified_against_the_bound(
    age: timedelta, expected: FreshnessState
) -> None:
    assert policy(DAY, timedelta(days=4)).classify(age) is expected


def test_an_age_exactly_at_the_bound_is_on_schedule() -> None:
    """The boundary is inclusive, and it is pinned so a `>=` mutation fails."""
    rule = policy(DAY, timedelta(days=4))
    assert rule.classify(rule.behind_schedule_after) is FreshnessState.ON_SCHEDULE


def test_a_reading_from_the_future_is_a_clock_defect_and_not_a_fresh_one() -> None:
    """*Calling it on-schedule would hide the defect behind a reassuring word.*"""
    with pytest.raises(ValueError, match="clock problem"):
        policy().classify(timedelta(seconds=-1))


def test_an_age_that_is_not_a_duration_is_refused() -> None:
    with pytest.raises(TypeError, match="must be a timedelta"):
        policy().classify(3600)


def test_a_policy_always_classifies_and_never_answers_unknown() -> None:
    """`UNKNOWN` means *no policy exists*; a policy that returned it would be
    claiming to have no opinion while holding one."""
    for hours in (0, 1, 10, 1000):
        assert policy().classify(timedelta(hours=hours)) is not FreshnessState.UNKNOWN


# --------------------------------------------------------------------------
# A policy must be a schedule
# --------------------------------------------------------------------------


@pytest.mark.parametrize("period", [timedelta(0), timedelta(seconds=-1)])
def test_a_non_positive_publication_period_is_refused(period: timedelta) -> None:
    with pytest.raises(ValueError, match="not a schedule"):
        FreshnessPolicy(publication_period=period, tolerance=DAY, basis="x")


def test_a_negative_tolerance_is_refused() -> None:
    with pytest.raises(ValueError, match="late by a negative amount"):
        FreshnessPolicy(
            publication_period=DAY, tolerance=timedelta(seconds=-1), basis="x"
        )


def test_a_zero_tolerance_is_permitted() -> None:
    """A source with no slack is a real schedule, just an unforgiving one."""
    rule = FreshnessPolicy(publication_period=HOUR, tolerance=timedelta(0), basis="x")
    assert rule.behind_schedule_after == HOUR


@pytest.mark.parametrize("field", ["publication_period", "tolerance"])
def test_a_duration_that_is_not_one_is_refused(field: str) -> None:
    kwargs = {"publication_period": DAY, "tolerance": DAY, "basis": "x", field: 3600}
    with pytest.raises(TypeError, match="must be a timedelta"):
        FreshnessPolicy(**kwargs)


# --------------------------------------------------------------------------
# The two failures the brief names, on the shipped policies
# --------------------------------------------------------------------------


def test_a_daily_macro_series_is_not_behind_schedule_after_an_hour() -> None:
    """*Do not call a daily macro series stale because it did not update in an
    hour.* Against the hourly policy it would be; against its own it is not."""
    age = timedelta(hours=1)
    assert FRED_DAILY_FRESHNESS.classify(age) is FreshnessState.ON_SCHEDULE


def test_a_daily_macro_series_read_over_a_long_weekend_is_on_schedule() -> None:
    """The tolerance is where the missing trading calendar is paid for: a
    business-day series read on a Sunday after a Monday holiday is four days
    old and nothing is wrong."""
    assert FRED_DAILY_FRESHNESS.classify(timedelta(days=4)) is (
        FreshnessState.ON_SCHEDULE
    )


def test_a_daily_macro_series_a_fortnight_old_is_behind_schedule() -> None:
    """The tolerance is generous, not infinite. A source that stopped
    publishing must eventually be reported."""
    assert FRED_DAILY_FRESHNESS.classify(timedelta(days=14)) is (
        FreshnessState.BEHIND_SCHEDULE
    )


def test_an_hourly_crypto_series_is_behind_schedule_after_two_days() -> None:
    """*Do not call a 1h crypto series fresh after 2 days.*"""
    assert CRYPTO_FRESHNESS.classify(timedelta(days=2)) is (
        FreshnessState.BEHIND_SCHEDULE
    )


def test_an_hourly_crypto_series_is_on_schedule_within_its_own_cadence() -> None:
    assert CRYPTO_FRESHNESS.classify(timedelta(hours=2)) is FreshnessState.ON_SCHEDULE


def test_the_lagged_dollar_index_is_judged_by_its_own_release_delay() -> None:
    """The Fed's broad dollar index is released about a week behind the market
    prints. Judged by the daily policy it would read behind schedule almost
    permanently — the exact failure a single universal threshold produces."""
    week_old = timedelta(days=9)
    assert FRED_DAILY_FRESHNESS.classify(week_old) is FreshnessState.BEHIND_SCHEDULE
    assert FRED_LAGGED_WEEKLY_FRESHNESS.classify(week_old) is (
        FreshnessState.ON_SCHEDULE
    )


def test_no_two_shipped_policies_are_interchangeable() -> None:
    bounds = {
        CRYPTO_FRESHNESS.behind_schedule_after,
        FRED_DAILY_FRESHNESS.behind_schedule_after,
        FRED_LAGGED_WEEKLY_FRESHNESS.behind_schedule_after,
    }
    assert len(bounds) == 3


def test_every_shipped_policy_states_where_its_figures_came_from() -> None:
    for rule in (CRYPTO_FRESHNESS, FRED_DAILY_FRESHNESS, FRED_LAGGED_WEEKLY_FRESHNESS):
        assert len(rule.basis) > 40, rule.basis


# --------------------------------------------------------------------------
# The registry wires a policy to every readable market
# --------------------------------------------------------------------------


def test_every_readable_market_states_how_often_its_source_publishes() -> None:
    for benchmark in DEFAULT_PULSE_UNIVERSE.supported:
        assert benchmark.freshness_policy is not None, benchmark.benchmark_id


def test_the_policy_matches_the_provider_that_serves_the_market() -> None:
    for benchmark in DEFAULT_PULSE_UNIVERSE.supported:
        provider = benchmark.instrument.provider
        if provider == PULSE_PROVIDER:
            assert benchmark.freshness_policy is CRYPTO_FRESHNESS
        else:
            assert provider == MACRO_PROVIDER
            assert benchmark.freshness_policy in {
                FRED_DAILY_FRESHNESS,
                FRED_LAGGED_WEEKLY_FRESHNESS,
            }


def test_an_unreadable_market_carries_no_schedule() -> None:
    """*A publication schedule describes a source, and a market with no source
    has no schedule to be judged against.*"""
    for benchmark in DEFAULT_PULSE_UNIVERSE.unsupported:
        assert benchmark.freshness_policy is None


def test_a_market_with_a_schedule_and_no_source_is_refused_at_construction() -> None:
    from fmis.market_pulse import (
        Benchmark,
        MarketCategory,
        PulseUniverseError,
        TradingSchedule,
    )

    with pytest.raises(PulseUniverseError, match="no provider instrument"):
        Benchmark(
            benchmark_id="X",
            display_name="X",
            category=MarketCategory.RATES,
            schedule=TradingSchedule.SESSION_BOUND,
            quote_unit="percent per annum",
            unsupported_reason="none configured",
            freshness_policy=FRED_DAILY_FRESHNESS,
        )


# --------------------------------------------------------------------------
# A reading classifies itself, in one place
# --------------------------------------------------------------------------


def reading_with(rule: FreshnessPolicy | None):
    from tests.macro_helpers import macro_benchmark
    from fmis.market_pulse import MarketReading, VolatilityReading

    return MarketReading(
        benchmark=macro_benchmark(freshness=rule),
        source="fred",
        interval="1d",
        last_bar_open=datetime(2026, 8, 20, tzinfo=timezone.utc),
        closed_bar_count=30,
        moves=(),
        volatility=VolatilityReading(
            value=0.01,
            unavailable_reason=None,
            metric="realized_volatility",
            observation_count=22,
            window_start=datetime(2026, 7, 20, tzinfo=timezone.utc),
            window_end=datetime(2026, 8, 20, tzinfo=timezone.utc),
        ),
    )


def test_a_reading_with_no_policy_states_its_age_and_gives_no_verdict() -> None:
    """*The age is still stated; only the verdict is not.* A market with no
    established schedule is never quietly passed."""
    reading = reading_with(None)
    moment = datetime(2026, 9, 20, tzinfo=timezone.utc)
    assert reading.freshness_at(moment) is FreshnessState.UNKNOWN
    assert reading.age_at(moment) == timedelta(days=31)


def test_a_reading_classifies_itself_against_its_own_benchmark_s_policy() -> None:
    reading = reading_with(FRED_DAILY_FRESHNESS)
    assert reading.freshness_at(
        datetime(2026, 8, 21, tzinfo=timezone.utc)
    ) is FreshnessState.ON_SCHEDULE
    assert reading.freshness_at(
        datetime(2026, 9, 20, tzinfo=timezone.utc)
    ) is FreshnessState.BEHIND_SCHEDULE


def test_the_state_vocabulary_says_schedule_and_never_fresh_or_stale() -> None:
    """*"Stale" is a judgement about whether a number is still usable, and that
    depends on what the reader is doing with it.*"""
    values = {state.value for state in FreshnessState}
    assert values == {"on_schedule", "behind_schedule", "unknown"}
    for value in values:
        assert "stale" not in value
        assert "fresh" not in value
