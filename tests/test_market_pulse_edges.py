"""Milestone BT — the edges: every rejection path, and the defensive ones.

The paths a normal run never takes. Each one exists because something upstream
could hand this package the wrong shape, and a type error surfacing as a
mis-rendered page rather than a raise is how a wrong number gets printed
confidently. They are exercised here so *"the constructor refuses it"* is a
measured claim rather than a hoped-for one.
"""

from __future__ import annotations

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
    TradingSchedule,
    VolatilityReading,
    build_market_pulse,
    co_movements_against,
    measure_from_observations,
    render_market_pulse,
)
from fmis.market_pulse import render as render_module
from tests.market_pulse_helpers import (
    crypto_benchmark,
    instant,
    observations,
    universe_of,
)

ONE = Horizon(horizon_id="h1", bars=1, description="one bar")
TWO = Horizon(horizon_id="h2", bars=2, description="two bars")
THREE = Horizon(horizon_id="h3", bars=3, description="three bars")


def move(value=0.05, horizon: Horizon = ONE) -> HorizonMove:
    return HorizonMove(
        horizon_id=horizon.horizon_id,
        bars=horizon.bars,
        value=value,
        unavailable_reason=None,
        metric="period_return",
        observation_count=horizon.required_observations,
        window_start=instant(0),
        window_end=instant(1),
    )


def volatility() -> VolatilityReading:
    return VolatilityReading(
        value=0.01,
        unavailable_reason=None,
        metric="realized_volatility",
        observation_count=4,
        window_start=instant(0),
        window_end=instant(3),
    )


def reading(benchmark=None, *, moves=None) -> MarketReading:
    return MarketReading(
        benchmark=benchmark or crypto_benchmark(),
        source="binance-spot",
        interval="1h",
        last_bar_open=instant(5),
        closed_bar_count=6,
        moves=moves if moves is not None else (move(),),
        volatility=volatility(),
    )


# --------------------------------------------------------------------------
# Primitive validators
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, 42, b"bytes", ["a"]])
def test_a_text_field_refuses_a_non_string(value) -> None:
    with pytest.raises(TypeError, match="must be a str"):
        ProviderInstrument(provider=value, symbol="X", interval="1h")


@pytest.mark.parametrize("value", ["2026-08-01", 1754006400, None])
def test_an_instant_field_refuses_a_non_datetime(value) -> None:
    with pytest.raises(TypeError, match="must be a datetime"):
        MarketReading(
            benchmark=crypto_benchmark(),
            source="s",
            interval="1h",
            last_bar_open=value,
            closed_bar_count=1,
            moves=(),
            volatility=volatility(),
        )


@pytest.mark.parametrize("value", ["6", 6.0, True, None])
def test_a_count_field_refuses_a_non_int(value) -> None:
    with pytest.raises(TypeError, match="must be an int"):
        MarketReading(
            benchmark=crypto_benchmark(),
            source="s",
            interval="1h",
            last_bar_open=instant(5),
            closed_bar_count=value,
            moves=(),
            volatility=volatility(),
        )


def test_a_count_field_refuses_a_value_below_its_minimum() -> None:
    with pytest.raises(ValueError, match="must be at least 1"):
        MarketReading(
            benchmark=crypto_benchmark(),
            source="s",
            interval="1h",
            last_bar_open=instant(5),
            closed_bar_count=0,
            moves=(),
            volatility=volatility(),
        )


def test_a_negative_observation_count_is_refused() -> None:
    with pytest.raises(ValueError, match="must be at least 0"):
        HorizonMove(
            horizon_id="h1",
            bars=1,
            value=None,
            unavailable_reason="short",
            metric="period_return",
            observation_count=-1,
        )


@pytest.mark.parametrize("value", ["not iterable", 42, None])
def test_a_collection_field_refuses_a_non_iterable(value) -> None:
    with pytest.raises(TypeError, match="must be an iterable"):
        MarketUniverse(name="u", benchmarks=value)


def test_a_collection_field_refuses_the_wrong_element_type() -> None:
    with pytest.raises(TypeError, match="must hold Benchmark values"):
        MarketUniverse(name="u", benchmarks=("BTC",))


def test_a_reading_refuses_a_non_horizon_move() -> None:
    with pytest.raises(TypeError, match="must hold HorizonMove values"):
        reading(moves=("a move",))


# --------------------------------------------------------------------------
# Enum and record type rejections
# --------------------------------------------------------------------------


def test_a_benchmark_refuses_a_non_category() -> None:
    with pytest.raises(TypeError, match="must be a MarketCategory"):
        Benchmark(
            benchmark_id="B",
            display_name="B",
            category="crypto",
            schedule=TradingSchedule.CONTINUOUS,
            quote_unit="USDT",
            unsupported_reason="none",
        )


def test_a_benchmark_refuses_a_non_schedule() -> None:
    with pytest.raises(TypeError, match="must be a TradingSchedule"):
        Benchmark(
            benchmark_id="B",
            display_name="B",
            category=MarketCategory.CRYPTO,
            schedule="continuous",
            quote_unit="USDT",
            unsupported_reason="none",
        )


def test_a_benchmark_refuses_a_non_instrument() -> None:
    with pytest.raises(TypeError, match="must be a ProviderInstrument"):
        Benchmark(
            benchmark_id="B",
            display_name="B",
            category=MarketCategory.CRYPTO,
            schedule=TradingSchedule.CONTINUOUS,
            quote_unit="USDT",
            instrument="binance BTCUSDT 1h",
        )


def test_a_reading_refuses_a_non_benchmark() -> None:
    with pytest.raises(TypeError, match="must be a Benchmark"):
        MarketReading(
            benchmark="BTC",
            source="s",
            interval="1h",
            last_bar_open=instant(5),
            closed_bar_count=1,
            moves=(),
            volatility=volatility(),
        )


def test_a_reading_refuses_a_non_volatility_reading() -> None:
    with pytest.raises(TypeError, match="must be a VolatilityReading"):
        MarketReading(
            benchmark=crypto_benchmark(),
            source="s",
            interval="1h",
            last_bar_open=instant(5),
            closed_bar_count=1,
            moves=(),
            volatility=0.01,
        )


def test_an_unavailable_entry_refuses_a_non_benchmark() -> None:
    with pytest.raises(TypeError, match="must be a Benchmark"):
        MarketUnavailable(benchmark="BTC", reason="down")


def test_a_pulse_refuses_a_non_universe() -> None:
    with pytest.raises(TypeError, match="must be a MarketUniverse"):
        MarketPulse(
            as_of=instant(10),
            universe="default",
            readings=(),
            unavailable=(),
            rankings=(),
            horizons=(),
        )


def test_a_move_refuses_a_non_ranked_move_in_an_ordering() -> None:
    with pytest.raises(TypeError, match="must hold RankedMove values"):
        HorizonRanking(
            horizon_id="h1",
            quote_unit="USDT",
            ordering_quantity="q",
            ordered=("BTC",),
        )


# --------------------------------------------------------------------------
# Lookups that find something
# --------------------------------------------------------------------------


def test_a_lookup_returns_the_reading_it_finds() -> None:
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(crypto_benchmark()),
        readings=(reading(),),
        unavailable=(),
        horizons=(ONE,),
    )
    assert page.reading_for("BTC").benchmark_id == "BTC"


def test_a_lookup_returns_the_ordering_it_finds() -> None:
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(crypto_benchmark()),
        readings=(reading(),),
        unavailable=(),
        horizons=(ONE,),
    )
    assert page.ranking_for("h1").horizon_id == "h1"


def test_an_ordering_lookup_walks_past_the_ones_that_do_not_match() -> None:
    """Two horizons produce two orderings; asking for the second must not
    return the first. The loop's continue branch, exercised."""
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(crypto_benchmark()),
        readings=(reading(moves=(move(0.05, ONE), move(0.09, TWO))),),
        unavailable=(),
        horizons=(ONE, TWO),
    )
    assert [ranking.horizon_id for ranking in page.rankings] == ["h1", "h2"]
    assert page.ranking_for("h2").ordered[0].value == 0.09


def test_a_reading_lookup_walks_past_the_ones_that_do_not_match() -> None:
    first = crypto_benchmark("BTC", symbol="BTCUSDT")
    second = crypto_benchmark("ETH", symbol="ETHUSDT")
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(first, second),
        readings=(reading(first), reading(second)),
        unavailable=(),
        horizons=(ONE,),
    )
    assert page.reading_for("ETH").benchmark_id == "ETH"


def test_a_universe_lookup_returns_the_benchmark_it_finds() -> None:
    scope = universe_of(crypto_benchmark("BTC", symbol="BTCUSDT"))
    assert scope.benchmark_for("BTC").benchmark_id == "BTC"


# --------------------------------------------------------------------------
# Co-movement assembly edges
# --------------------------------------------------------------------------


def test_a_missing_reference_series_yields_no_co_movements() -> None:
    """The reference itself was not reduced, so there is nothing to measure
    against — and no absence is invented for a comparison never attempted."""
    assert co_movements_against("BTC", {}, ("BTC", "ETH"), TWO) == ()


def test_a_market_with_no_observations_is_skipped_rather_than_reported() -> None:
    """*It already appears on the page as unavailable, and a second absence for
    it would be the same fact twice.*"""
    found = co_movements_against(
        "BTC",
        {"BTC": observations([1.0, 2.0, 4.0, 8.0])},
        ("BTC", "ETH", "SOL"),
        TWO,
    )
    assert found == ()


def test_the_reference_skips_a_read_market_that_has_no_series() -> None:
    """The first *read* market is the reference only if its series survived. A
    caller that supplies observations for some readings and not others must not
    get a reference nothing was reduced for."""
    first = crypto_benchmark("BTC", symbol="BTCUSDT")
    second = crypto_benchmark("ETH", symbol="ETHUSDT")
    third = crypto_benchmark("SOL", symbol="SOLUSDT")
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(first, second, third),
        readings=(reading(first), reading(second), reading(third)),
        unavailable=(),
        horizons=(ONE,),
        observations={
            "ETH": observations([1.0, 2.0, 4.0, 8.0]),
            "SOL": observations([2.0, 3.0, 7.0, 12.0]),
        },
        co_movement_horizon=TWO,
    )
    assert page.co_movement_reference == "ETH"
    assert [item.subject_id for item in page.co_movements] == ["SOL"]


def test_the_reference_is_never_correlated_with_itself() -> None:
    found = co_movements_against(
        "BTC",
        {
            "BTC": observations([1.0, 2.0, 4.0, 8.0]),
            "ETH": observations([2.0, 3.0, 6.0, 11.0]),
        },
        ("BTC", "ETH"),
        TWO,
    )
    assert [item.subject_id for item in found] == ["ETH"]


# --------------------------------------------------------------------------
# Measurement edges
# --------------------------------------------------------------------------


def test_measuring_from_observations_refuses_a_non_benchmark() -> None:
    with pytest.raises(TypeError, match="must be a Benchmark"):
        measure_from_observations(
            "BTC",
            observations([1.0, 2.0]),
            source="s",
            horizons=(ONE,),
            volatility_horizon=THREE,
        )


def test_measuring_from_observations_refuses_an_unsupported_market() -> None:
    from tests.market_pulse_helpers import dark_benchmark

    with pytest.raises(ValueError, match="no provider instrument"):
        measure_from_observations(
            dark_benchmark(),
            observations([1.0, 2.0]),
            source="s",
            horizons=(ONE,),
            volatility_horizon=THREE,
        )


# --------------------------------------------------------------------------
# Rendering edges
# --------------------------------------------------------------------------


def test_a_reading_missing_a_horizon_prints_that_it_was_not_measured() -> None:
    """The page declares a horizon the reading has no row for. It says so
    rather than leaving a gap where a number belongs."""
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(crypto_benchmark()),
        readings=(reading(moves=(move(0.05, ONE),)),),
        unavailable=(),
        horizons=(ONE, TWO),
    )
    text = " ".join(render_market_pulse(page).split())
    assert "h2 (2 bars): not measured on this run" in text


def test_an_unmeasured_co_movement_prints_its_reason() -> None:
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(
            crypto_benchmark("BTC", symbol="BTCUSDT"),
            crypto_benchmark("ETH", symbol="ETHUSDT"),
        ),
        readings=(
            reading(crypto_benchmark("BTC", symbol="BTCUSDT")),
            reading(crypto_benchmark("ETH", symbol="ETHUSDT")),
        ),
        unavailable=(),
        horizons=(ONE,),
        observations={
            "BTC": observations([1.0, 2.0, 4.0, 8.0]),
            "ETH": observations([5.0, 5.0, 5.0, 5.0]),  # constant: zero variance
        },
        co_movement_horizon=TWO,
    )
    text = " ".join(render_market_pulse(page).split())
    assert "zero_variance" in text
    assert "not a reading of zero" in text


def test_an_unbreakable_identifier_is_chopped_rather_than_overflowing() -> None:
    """`textwrap` breaks a word longer than the width, so a pathological id
    cannot push a line past column 78. The first line of defence, measured."""
    unbreakable = "X" * (render_module.PULSE_PAGE_WIDTH * 2)
    benchmark = crypto_benchmark(
        unbreakable, symbol="XUSDT", display_name=unbreakable
    )
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(benchmark),
        readings=(reading(benchmark),),
        unavailable=(),
        horizons=(ONE,),
    )
    for line in render_market_pulse(page).splitlines():
        assert len(line) <= render_module.PULSE_PAGE_WIDTH


def test_a_section_that_forgot_to_wrap_is_refused_rather_than_printed(
    monkeypatch,
) -> None:
    """The renderer's last line of defence, exercised the only way it can fire.

    Every section wraps, so no input reaches the check — which is exactly why it
    is worth having: it catches the *future* section that interpolates a value
    straight into a line. Disabling the wrapper is the faithful simulation of
    that mistake, and the page is refused rather than silently breaking the
    width discipline every other FMITS surface holds to.
    """
    monkeypatch.setattr(
        render_module, "_wrap", lambda text, *, indent="": [indent + text]
    )
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(crypto_benchmark()),
        readings=(reading(),),
        unavailable=(),
        horizons=(ONE,),
    )
    with pytest.raises(ValueError, match="exceeds the 78-column page width"):
        render_market_pulse(page)
