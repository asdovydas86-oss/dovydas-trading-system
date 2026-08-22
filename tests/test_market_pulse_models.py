"""Milestone BT — the market-pulse model, and every rule it refuses to break.

The organizing claim of `fmis.market_pulse.models` is that **absence is a value,
never a gap**. These tests attack that claim from both sides: a measurement may
not exist without a number *or* a reason, and it may not carry both. Everything
else here follows from the same principle — a duplicate market, a reading from
the future, a page missing a market its own scope names.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fmis.market_pulse import (
    Benchmark,
    CoMovement,
    Horizon,
    HorizonMove,
    HorizonRanking,
    MarketCategory,
    MarketPulse,
    MarketReading,
    MarketUnavailable,
    MarketUniverse,
    ProviderInstrument,
    PulseUniverseError,
    RankedMove,
    TradingSchedule,
    VolatilityReading,
)
from tests.market_pulse_helpers import (
    crypto_benchmark,
    dark_benchmark,
    instant,
    universe_of,
)

HOUR = Horizon(horizon_id="h1", bars=1, description="one bar")
DAY = Horizon(horizon_id="h24", bars=24, description="a day")


def move(
    value: float | None = 0.05,
    *,
    horizon_id: str = "h1",
    bars: int = 1,
    reason: str | None = None,
    count: int = 2,
) -> HorizonMove:
    measured = value is not None
    return HorizonMove(
        horizon_id=horizon_id,
        bars=bars,
        value=value,
        unavailable_reason=reason,
        metric="period_return",
        observation_count=count,
        window_start=instant(0) if measured else None,
        window_end=instant(1) if measured else None,
    )


def volatility(value: float | None = 0.01, reason: str | None = None):
    measured = value is not None
    return VolatilityReading(
        value=value,
        unavailable_reason=reason,
        metric="realized_volatility",
        observation_count=3 if measured else 0,
        window_start=instant(0) if measured else None,
        window_end=instant(2) if measured else None,
    )


def reading(
    benchmark: Benchmark | None = None,
    *,
    moves: tuple[HorizonMove, ...] = (),
    last_bar: int = 5,
) -> MarketReading:
    return MarketReading(
        benchmark=benchmark or crypto_benchmark(),
        source="binance-spot",
        interval="1h",
        last_bar_open=instant(last_bar),
        closed_bar_count=6,
        moves=moves or (move(),),
        volatility=volatility(),
    )


# --------------------------------------------------------------------------
# Exactly one of a value and a reason — the module's load-bearing rule
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "build",
    [
        lambda v, r: HorizonMove(
            horizon_id="h1",
            bars=1,
            value=v,
            unavailable_reason=r,
            metric="period_return",
            observation_count=2,
            window_start=instant(0) if v is not None else None,
            window_end=instant(1) if v is not None else None,
        ),
        lambda v, r: VolatilityReading(
            value=v,
            unavailable_reason=r,
            metric="realized_volatility",
            observation_count=3,
            window_start=instant(0) if v is not None else None,
            window_end=instant(2) if v is not None else None,
        ),
        lambda v, r: CoMovement(
            subject_id="ETH",
            reference_id="BTC",
            value=v,
            unavailable_reason=r,
            metric="pearson_correlation",
            observation_count=3,
            window_start=instant(0) if v is not None else None,
            window_end=instant(2) if v is not None else None,
        ),
    ],
    ids=["move", "volatility", "co_movement"],
)
def test_a_measurement_holds_a_value_or_a_reason_and_never_both(build) -> None:
    """*A figure beside the sentence explaining why there is no figure.*"""
    with pytest.raises(ValueError, match="neither a value nor a reason"):
        build(None, None)
    with pytest.raises(ValueError, match="both a value and the reason"):
        build(0.5, "a reason")


@pytest.mark.parametrize("value", [0.0, -0.0])
def test_a_zero_move_is_a_measurement_and_not_an_absence(value: float) -> None:
    """The distinction the whole module exists for: a market that did not move
    is not a market that could not be read."""
    measured = move(value)
    assert measured.is_measured is True
    assert measured.value == 0.0
    assert measured.unavailable_reason is None


def test_a_measured_value_must_be_finite() -> None:
    with pytest.raises(ValueError, match="must be finite"):
        move(float("inf"))
    with pytest.raises(ValueError, match="must be finite"):
        move(float("nan"))


def test_a_measured_value_may_not_be_a_bool() -> None:
    """`bool` subclasses `int`; `True` must never read as a move of one."""
    with pytest.raises(TypeError, match="must be a number"):
        move(True)


def test_a_blank_reason_is_refused() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        move(None, reason="   ")


# --------------------------------------------------------------------------
# Windows travel with values, and only with values
# --------------------------------------------------------------------------


def test_a_measured_value_without_a_window_is_refused() -> None:
    """*A number over an unnamed window is a number nobody can reconstruct.*"""
    with pytest.raises(ValueError, match="names no window"):
        HorizonMove(
            horizon_id="h1",
            bars=1,
            value=0.1,
            unavailable_reason=None,
            metric="period_return",
            observation_count=2,
        )


def test_an_unmeasured_quantity_may_not_state_a_window() -> None:
    with pytest.raises(ValueError, match="states a window but produced no value"):
        HorizonMove(
            horizon_id="h1",
            bars=1,
            value=None,
            unavailable_reason="short window",
            metric="period_return",
            observation_count=0,
            window_start=instant(0),
            window_end=instant(1),
        )


def test_a_window_may_not_end_before_it_starts() -> None:
    with pytest.raises(ValueError, match="ends .* before it starts"):
        HorizonMove(
            horizon_id="h1",
            bars=1,
            value=0.1,
            unavailable_reason=None,
            metric="period_return",
            observation_count=2,
            window_start=instant(5),
            window_end=instant(1),
        )


def test_a_move_may_not_claim_a_value_from_too_few_observations() -> None:
    """*A shorter window is a different measurement, not a smaller one.*"""
    with pytest.raises(ValueError, match="24-bar horizon needs 25"):
        move(0.1, horizon_id="h24", bars=24, count=10)


def test_a_move_measured_from_exactly_enough_observations_is_accepted() -> None:
    assert move(0.1, horizon_id="h24", bars=24, count=25).is_measured


# --------------------------------------------------------------------------
# Canonical time
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "moment, match",
    [
        (datetime(2026, 8, 1, 12), "must be timezone-aware"),
        (
            datetime(2026, 8, 1, 12, tzinfo=timezone(timedelta(hours=2))),
            "must represent UTC",
        ),
    ],
    ids=["naive", "offset"],
)
def test_every_instant_must_be_utc(moment: datetime, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        MarketReading(
            benchmark=crypto_benchmark(),
            source="binance-spot",
            interval="1h",
            last_bar_open=moment,
            closed_bar_count=6,
            moves=(move(),),
            volatility=volatility(),
        )


# --------------------------------------------------------------------------
# Volatility and co-movement bounds
# --------------------------------------------------------------------------


def test_a_negative_volatility_is_refused() -> None:
    """*A standard deviation is not signed.*"""
    with pytest.raises(ValueError, match="not signed"):
        volatility(-0.01)


def test_a_zero_volatility_is_accepted_because_a_constant_series_has_one() -> None:
    assert volatility(0.0).is_measured is True


@pytest.mark.parametrize("value", [1.0000001, -1.0000001, 5.0])
def test_a_correlation_outside_the_unit_interval_is_refused(value: float) -> None:
    with pytest.raises(ValueError, match=r"outside \[-1, 1\]"):
        CoMovement(
            subject_id="ETH",
            reference_id="BTC",
            value=value,
            unavailable_reason=None,
            metric="pearson_correlation",
            observation_count=3,
            window_start=instant(0),
            window_end=instant(2),
        )


def test_a_market_may_not_co_move_with_itself() -> None:
    """*Arithmetic, not information.*"""
    with pytest.raises(ValueError, match="cannot co-move with itself"):
        CoMovement(
            subject_id="BTC",
            reference_id="BTC",
            value=1.0,
            unavailable_reason=None,
            metric="pearson_correlation",
            observation_count=3,
            window_start=instant(0),
            window_end=instant(2),
        )


# --------------------------------------------------------------------------
# Benchmark: wired up, or carrying the reason it is not
# --------------------------------------------------------------------------


def test_a_benchmark_with_no_instrument_and_no_reason_is_refused() -> None:
    with pytest.raises(PulseUniverseError, match="states no reason"):
        Benchmark(
            benchmark_id="DXY",
            display_name="Dollar",
            category=MarketCategory.CURRENCY,
            schedule=TradingSchedule.SESSION_BOUND,
            quote_unit="index points",
        )


def test_a_benchmark_with_both_an_instrument_and_a_reason_is_refused() -> None:
    with pytest.raises(PulseUniverseError, match="wired up or it is not"):
        Benchmark(
            benchmark_id="BTC",
            display_name="Bitcoin",
            category=MarketCategory.CRYPTO,
            schedule=TradingSchedule.CONTINUOUS,
            quote_unit="USDT",
            instrument=ProviderInstrument(
                provider="binance-spot", symbol="BTCUSDT", interval="1h"
            ),
            unsupported_reason="also unsupported",
        )


@pytest.mark.parametrize(
    "schedule, claims",
    [
        (TradingSchedule.CONTINUOUS, True),
        (TradingSchedule.SESSION_BOUND, False),
        (TradingSchedule.UNKNOWN, False),
    ],
)
def test_only_a_continuous_market_may_claim_wall_clock_horizons(
    schedule: TradingSchedule, claims: bool
) -> None:
    """*A schedule nobody established is not a schedule that happens to be 24/7.*"""
    assert crypto_benchmark(schedule=schedule).claims_wall_clock_horizons is claims


def test_a_provider_symbol_is_never_normalized() -> None:
    """*A symbol is an identifier, not a search term.*"""
    lower = ProviderInstrument(provider="p", symbol="btcusdt", interval="1h")
    upper = ProviderInstrument(provider="p", symbol="BTCUSDT", interval="1h")
    assert lower != upper


# --------------------------------------------------------------------------
# Universe distinctness — three ways a page could lie
# --------------------------------------------------------------------------


def test_a_duplicate_benchmark_id_is_refused() -> None:
    with pytest.raises(PulseUniverseError, match="appears twice"):
        universe_of(
            crypto_benchmark("BTC", symbol="BTCUSDT"),
            crypto_benchmark("BTC", symbol="ETHUSDT", display_name="other"),
        )


def test_a_duplicate_display_name_is_refused() -> None:
    """*A reader has only the name.*"""
    with pytest.raises(PulseUniverseError, match="display name"):
        universe_of(
            crypto_benchmark("BTC", symbol="BTCUSDT", display_name="Same"),
            crypto_benchmark("ETH", symbol="ETHUSDT", display_name="Same"),
        )


def test_two_benchmarks_over_one_instrument_are_refused() -> None:
    """*One reading printed twice, and ranking them against each other is a
    rigged tie.*"""
    with pytest.raises(PulseUniverseError, match="rigged tie"):
        universe_of(
            crypto_benchmark("BTC", symbol="BTCUSDT"),
            crypto_benchmark("BTC2", symbol="BTCUSDT", display_name="Bitcoin again"),
        )


def test_two_unsupported_benchmarks_do_not_collide_on_a_missing_instrument() -> None:
    """`None` is not an instrument, so two dark markets are not duplicates."""
    built = universe_of(dark_benchmark("DXY"), dark_benchmark("VIX"))
    assert len(built.unsupported) == 2


def test_the_same_symbol_on_two_venues_is_two_markets() -> None:
    """Venue is part of a provider instrument, so it distinguishes them."""
    built = MarketUniverse(
        name="venues",
        benchmarks=(
            Benchmark(
                benchmark_id="BTC-A",
                display_name="Bitcoin on A",
                category=MarketCategory.CRYPTO,
                schedule=TradingSchedule.CONTINUOUS,
                quote_unit="USDT",
                instrument=ProviderInstrument(
                    provider="venue-a", symbol="BTCUSDT", interval="1h"
                ),
            ),
            Benchmark(
                benchmark_id="BTC-B",
                display_name="Bitcoin on B",
                category=MarketCategory.CRYPTO,
                schedule=TradingSchedule.CONTINUOUS,
                quote_unit="USDT",
                instrument=ProviderInstrument(
                    provider="venue-b", symbol="BTCUSDT", interval="1h"
                ),
            ),
        ),
    )
    assert len(built.supported) == 2


def test_an_empty_universe_is_refused() -> None:
    with pytest.raises(PulseUniverseError, match="holds no benchmark"):
        MarketUniverse(name="empty", benchmarks=())


def test_universe_order_is_preserved_exactly() -> None:
    """*A universe that reordered itself would make "which market is listed
    first" an accidental signal.*"""
    built = universe_of(
        crypto_benchmark("ZZZ", symbol="ZZZUSDT"),
        crypto_benchmark("AAA", symbol="AAAUSDT"),
    )
    assert [entry.benchmark_id for entry in built.benchmarks] == ["ZZZ", "AAA"]


# --------------------------------------------------------------------------
# Readings and unavailability are kept apart
# --------------------------------------------------------------------------


def test_an_unsupported_market_cannot_have_a_reading() -> None:
    with pytest.raises(ValueError, match="never as read"):
        MarketReading(
            benchmark=dark_benchmark(),
            source="binance-spot",
            interval="1h",
            last_bar_open=instant(1),
            closed_bar_count=2,
            moves=(move(),),
            volatility=volatility(),
        )


def test_an_unsupported_market_cannot_be_a_provider_failure() -> None:
    """*A market with no provider is unsupported, which is a different fact.*"""
    with pytest.raises(ValueError, match="no provider can have failed"):
        MarketUnavailable(benchmark=dark_benchmark(), reason="timeout")


def test_a_reading_may_not_report_one_horizon_twice() -> None:
    with pytest.raises(ValueError, match="twice"):
        reading(moves=(move(0.1), move(0.2)))


def test_a_reading_states_its_own_provenance_in_one_line() -> None:
    line = reading().provenance
    assert "binance-spot" in line and "1h" in line and "6 closed bars" in line


def test_a_reading_age_is_computed_against_a_supplied_instant() -> None:
    assert reading(last_bar=5).age_at(instant(8)) == timedelta(hours=3)


# --------------------------------------------------------------------------
# Ranking: one outcome per market, no market twice
# --------------------------------------------------------------------------


def test_a_market_may_not_be_placed_twice_in_one_ordering() -> None:
    with pytest.raises(ValueError, match="placed twice"):
        HorizonRanking(
            horizon_id="h1",
            quote_unit="USDT",
            ordering_quantity="period_return",
            ordered=(
                RankedMove(benchmark_id="BTC", display_name="Bitcoin", value=0.1),
                RankedMove(benchmark_id="BTC", display_name="Bitcoin", value=0.2),
            ),
        )


def test_a_market_may_not_be_both_placed_and_excluded() -> None:
    """*One market has one outcome.*"""
    with pytest.raises(ValueError, match="both placed in and excluded"):
        HorizonRanking(
            horizon_id="h1",
            quote_unit="USDT",
            ordering_quantity="period_return",
            ordered=(
                RankedMove(benchmark_id="BTC", display_name="Bitcoin", value=0.1),
            ),
            excluded=(("BTC", "also excluded"),),
        )


def test_an_excluded_entry_must_be_a_pair() -> None:
    with pytest.raises(TypeError, match=r"\(benchmark_id, reason\) pairs"):
        HorizonRanking(
            horizon_id="h1",
            quote_unit="USDT",
            ordering_quantity="period_return",
            ordered=(),
            excluded=("BTC",),
        )


def test_an_empty_ordering_reports_no_leader_and_no_laggard() -> None:
    empty = HorizonRanking(
        horizon_id="h1",
        quote_unit="USDT",
        ordering_quantity="period_return",
        ordered=(),
    )
    assert empty.is_empty and empty.leader is None and empty.laggard is None


# --------------------------------------------------------------------------
# The page accounts for every market in its own scope
# --------------------------------------------------------------------------


def pulse_of(**overrides) -> MarketPulse:
    benchmark = overrides.pop("benchmark", crypto_benchmark())
    universe = overrides.pop("universe", universe_of(benchmark))
    defaults = dict(
        as_of=instant(10),
        universe=universe,
        readings=(reading(benchmark),),
        unavailable=(),
        rankings=(),
        horizons=(HOUR,),
    )
    defaults.update(overrides)
    return MarketPulse(**defaults)


def test_a_supported_market_missing_from_the_page_is_refused() -> None:
    """*A market that disappears between the scope and the page is an absence
    the page cannot disclose.*"""
    with pytest.raises(ValueError, match="neither a reading nor a reason"):
        pulse_of(
            universe=universe_of(
                crypto_benchmark("BTC", symbol="BTCUSDT"),
                crypto_benchmark("ETH", symbol="ETHUSDT"),
            ),
            readings=(reading(crypto_benchmark("BTC", symbol="BTCUSDT")),),
        )


def test_a_market_outside_the_stated_scope_is_refused() -> None:
    with pytest.raises(ValueError, match="not a supported member"):
        pulse_of(
            universe=universe_of(crypto_benchmark("BTC", symbol="BTCUSDT")),
            readings=(
                reading(crypto_benchmark("BTC", symbol="BTCUSDT")),
                reading(crypto_benchmark("ETH", symbol="ETHUSDT")),
            ),
        )


def test_a_market_may_not_be_both_read_and_unavailable() -> None:
    benchmark = crypto_benchmark()
    with pytest.raises(ValueError, match="appears twice on one pulse"):
        pulse_of(
            benchmark=benchmark,
            readings=(reading(benchmark),),
            unavailable=(MarketUnavailable(benchmark=benchmark, reason="x"),),
        )


def test_a_reading_dated_after_the_page_is_refused() -> None:
    """*A reading from the future is a clock problem, not a reading.*"""
    with pytest.raises(ValueError, match="clock problem"):
        pulse_of(as_of=instant(1), readings=(reading(last_bar=9),))


def test_an_ordering_over_an_undeclared_horizon_is_refused() -> None:
    with pytest.raises(ValueError, match="does not declare"):
        pulse_of(
            rankings=(
                HorizonRanking(
                    horizon_id="h999",
                    quote_unit="USDT",
                    ordering_quantity="period_return",
                    ordered=(),
                ),
            )
        )


def test_a_horizon_may_not_be_declared_twice() -> None:
    with pytest.raises(ValueError, match="declared twice"):
        pulse_of(horizons=(HOUR, HOUR))


def test_co_movements_without_a_named_reference_are_refused() -> None:
    """*A correlation against an unnamed series is not interpretable.*"""
    benchmark = crypto_benchmark()
    with pytest.raises(ValueError, match="no reference market named"):
        pulse_of(
            benchmark=benchmark,
            co_movements=(
                CoMovement(
                    subject_id="ETH",
                    reference_id="BTC",
                    value=0.5,
                    unavailable_reason=None,
                    metric="pearson_correlation",
                    observation_count=3,
                    window_start=instant(0),
                    window_end=instant(2),
                ),
            ),
        )


def test_a_reference_that_is_not_on_the_page_is_refused() -> None:
    with pytest.raises(ValueError, match="not a market this pulse reports"):
        pulse_of(co_movement_reference="GOLD")


def test_the_page_counts_read_failed_and_unconfigured_separately() -> None:
    """The three counts a reader needs to know how complete the page is."""
    supported = crypto_benchmark("BTC", symbol="BTCUSDT")
    failed = crypto_benchmark("ETH", symbol="ETHUSDT")
    page = pulse_of(
        universe=universe_of(supported, failed, dark_benchmark("DXY")),
        readings=(reading(supported),),
        unavailable=(MarketUnavailable(benchmark=failed, reason="timeout"),),
    )
    assert page.read_count == 1
    assert page.requested_count == 2
    assert page.unsupported_count == 1
    assert page.is_empty is False


def test_the_oldest_reading_bounds_the_page_rather_than_an_average() -> None:
    """*An average age makes one six-hour-old reading disappear behind nine
    fresh ones.*"""
    old = crypto_benchmark("OLD", symbol="OLDUSDT")
    new = crypto_benchmark("NEW", symbol="NEWUSDT")
    page = pulse_of(
        universe=universe_of(old, new),
        readings=(reading(new, last_bar=9), reading(old, last_bar=2)),
        as_of=instant(10),
    )
    assert page.oldest_reading().benchmark_id == "OLD"


def test_an_empty_page_reports_no_oldest_reading() -> None:
    failed = crypto_benchmark("ETH", symbol="ETHUSDT")
    page = pulse_of(
        universe=universe_of(failed),
        readings=(),
        unavailable=(MarketUnavailable(benchmark=failed, reason="down"),),
    )
    assert page.is_empty is True and page.oldest_reading() is None


def test_lookups_return_none_rather_than_raising_for_an_unknown_market() -> None:
    page = pulse_of()
    assert page.reading_for("NOPE") is None
    assert page.ranking_for("nope") is None
    assert page.universe.benchmark_for("NOPE") is None
    assert reading().move_for("nope") is None


def test_a_horizon_needs_one_more_observation_than_it_has_bars() -> None:
    assert DAY.required_observations == 25
    assert HOUR.required_observations == 2


def test_a_move_reports_the_span_its_window_actually_covered() -> None:
    """The projection that stops a bar count being printed as a duration."""
    measured = HorizonMove(
        horizon_id="h24",
        bars=24,
        value=0.05,
        unavailable_reason=None,
        metric="period_return",
        observation_count=25,
        window_start=instant(0),
        window_end=instant(200),
    )
    assert measured.measured_span == timedelta(hours=200)


def test_an_unmeasured_move_reports_no_span() -> None:
    assert move(None, reason="short").measured_span is None


@pytest.mark.parametrize(
    "equivalent, span",
    [("7 days", None), (None, timedelta(days=7))],
    ids=["phrase_without_span", "span_without_phrase"],
)
def test_a_wall_clock_phrase_and_its_span_travel_together(equivalent, span) -> None:
    """*A phrase with nothing to check it against is a claim nobody can
    falsify.*"""
    with pytest.raises(ValueError, match="nobody can falsify"):
        Horizon(
            horizon_id="h",
            bars=1,
            description="d",
            wall_clock_equivalent=equivalent,
            wall_clock_span=span,
        )


def test_a_wall_clock_span_must_be_a_positive_duration() -> None:
    with pytest.raises(TypeError, match="must be a timedelta"):
        Horizon(
            horizon_id="h",
            bars=1,
            description="d",
            wall_clock_equivalent="1 hour",
            wall_clock_span=3600,
        )
    with pytest.raises(ValueError, match="spans forward"):
        Horizon(
            horizon_id="h",
            bars=1,
            description="d",
            wall_clock_equivalent="1 hour",
            wall_clock_span=timedelta(0),
        )
