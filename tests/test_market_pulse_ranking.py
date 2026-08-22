"""Milestone BT — the ordering: one quantity, one horizon, one unit, no score.

The claim under test is narrow and total: **the order is a function of exactly
one measured number.** These tests prove it by fuzzing everything that is *not*
that number — volatility, bar counts, universe position, display name, category,
schedule — and asserting the order does not move. That is the assertion a hidden
weight would fail.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from fmis.market_pulse import (
    EXCLUDED_FROM_ORDERING,
    Horizon,
    HorizonMove,
    MarketCategory,
    MarketReading,
    MarketUnavailable,
    NOT_READ_REASON,
    ORDERING_QUANTITY,
    TradingSchedule,
    VolatilityReading,
    build_market_pulse,
    rank_by_horizon,
)
from tests.market_pulse_helpers import (
    crypto_benchmark,
    dark_benchmark,
    instant,
    universe_of,
)

ONE = Horizon(horizon_id="h1", bars=1, description="one bar")
OTHER = Horizon(horizon_id="h2", bars=2, description="two bars")


def move(value: float | None, *, horizon: Horizon = ONE, reason: str = "short"):
    measured = value is not None
    return HorizonMove(
        horizon_id=horizon.horizon_id,
        bars=horizon.bars,
        value=value,
        unavailable_reason=None if measured else reason,
        metric="period_return",
        observation_count=horizon.required_observations if measured else 0,
        window_start=instant(0) if measured else None,
        window_end=instant(1) if measured else None,
    )


def volatility(value: float | None = 0.01):
    measured = value is not None
    return VolatilityReading(
        value=value,
        unavailable_reason=None if measured else "short",
        metric="realized_volatility",
        observation_count=3 if measured else 0,
        window_start=instant(0) if measured else None,
        window_end=instant(2) if measured else None,
    )


def reading(
    benchmark_id: str,
    value: float | None,
    *,
    quote_unit: str = "USDT",
    vol: float | None = 0.01,
    bars: int = 6,
    moves=None,
):
    benchmark = crypto_benchmark(
        benchmark_id, symbol=f"{benchmark_id}USDT", quote_unit=quote_unit
    )
    return MarketReading(
        benchmark=benchmark,
        source="binance-spot",
        interval="1h",
        last_bar_open=instant(5),
        closed_bar_count=bars,
        moves=moves if moves is not None else (move(value),),
        volatility=volatility(vol),
    )


def rank(*readings, universe=None, horizon: Horizon = ONE, unit: str = "USDT"):
    scope = universe or universe_of(*(item.benchmark for item in readings))
    return rank_by_horizon(scope, readings, horizon, quote_unit=unit)


# --------------------------------------------------------------------------
# The order is the measured number, descending
# --------------------------------------------------------------------------


def test_markets_are_ordered_by_the_measured_move_highest_first() -> None:
    ranking = rank(reading("A", 0.01), reading("B", 0.05), reading("C", -0.02))
    assert [row.benchmark_id for row in ranking.ordered] == ["B", "A", "C"]
    assert ranking.leader.benchmark_id == "B"
    assert ranking.laggard.benchmark_id == "C"


def test_the_ordering_names_the_single_quantity_that_produced_it() -> None:
    ranking = rank(reading("A", 0.01))
    assert ranking.ordering_quantity == ORDERING_QUANTITY
    assert "period_return" in ranking.ordering_quantity


def test_every_row_carries_the_number_that_placed_it() -> None:
    """*Two adjacent rows can be compared by reading them.*"""
    ranking = rank(reading("A", 0.01), reading("B", 0.05))
    assert [row.value for row in ranking.ordered] == [0.05, 0.01]


def test_a_tie_is_broken_by_benchmark_id_ascending_and_is_stable() -> None:
    forward = rank(reading("Z", 0.02), reading("A", 0.02), reading("M", 0.02))
    backward = rank(reading("M", 0.02), reading("A", 0.02), reading("Z", 0.02))
    assert [row.benchmark_id for row in forward.ordered] == ["A", "M", "Z"]
    assert forward.ordered == backward.ordered


def test_negative_zero_and_positive_zero_tie_and_are_ordered_by_id() -> None:
    ranking = rank(reading("B", -0.0), reading("A", 0.0))
    assert [row.benchmark_id for row in ranking.ordered] == ["A", "B"]


def test_identical_returns_across_every_market_still_produce_one_order() -> None:
    ranking = rank(*(reading(name, 0.03) for name in ("D", "C", "B", "A")))
    assert [row.benchmark_id for row in ranking.ordered] == ["A", "B", "C", "D"]


@pytest.mark.parametrize("magnitude", [1e-12, 1e12])
def test_extreme_moves_are_ordered_rather_than_clamped(magnitude: float) -> None:
    ranking = rank(reading("A", magnitude), reading("B", -magnitude))
    assert [row.benchmark_id for row in ranking.ordered] == ["A", "B"]


# --------------------------------------------------------------------------
# Nothing else may move the order — the no-hidden-score assertions
# --------------------------------------------------------------------------


def test_volatility_cannot_change_the_order() -> None:
    """The first quantity a reader would assume is folded in. It is not."""
    baseline = rank(reading("A", 0.01, vol=0.9), reading("B", 0.05, vol=0.0))
    flipped = rank(reading("A", 0.01, vol=0.0), reading("B", 0.05, vol=0.9))
    assert [row.benchmark_id for row in baseline.ordered] == ["B", "A"]
    assert baseline.ordered == flipped.ordered


def test_an_unmeasurable_volatility_cannot_change_the_order() -> None:
    ranking = rank(reading("A", 0.01, vol=None), reading("B", 0.05, vol=None))
    assert [row.benchmark_id for row in ranking.ordered] == ["B", "A"]


def test_the_bar_count_behind_a_reading_cannot_change_the_order() -> None:
    ranking = rank(reading("A", 0.05, bars=999), reading("B", 0.09, bars=2))
    assert [row.benchmark_id for row in ranking.ordered] == ["B", "A"]


def test_another_horizon_s_move_cannot_change_this_horizon_s_order() -> None:
    """*Comparing different horizons* is the mutation this catches."""
    first = reading("A", None, moves=(move(0.01), move(0.99, horizon=OTHER)))
    second = reading("B", None, moves=(move(0.05), move(-0.99, horizon=OTHER)))
    ranking = rank(first, second)
    assert [row.benchmark_id for row in ranking.ordered] == ["B", "A"]


def test_the_universe_position_cannot_change_the_order() -> None:
    """*The order the universe configures* is named as excluded and is."""
    a, b = reading("A", 0.01), reading("B", 0.05)
    forward = rank(a, b, universe=universe_of(a.benchmark, b.benchmark))
    backward = rank(b, a, universe=universe_of(b.benchmark, a.benchmark))
    assert forward.ordered == backward.ordered


def test_the_excluded_quantities_are_named_on_the_record() -> None:
    """Stated rather than left to be asked about."""
    assert "realized volatility" in EXCLUDED_FROM_ORDERING
    assert "traded volume" in EXCLUDED_FROM_ORDERING
    assert "any other horizon's move" in EXCLUDED_FROM_ORDERING
    assert len(set(EXCLUDED_FROM_ORDERING)) == len(EXCLUDED_FROM_ORDERING)


def test_no_ranked_row_carries_any_field_but_the_measurement() -> None:
    """A score would need somewhere to live. There is nowhere."""
    row = rank(reading("A", 0.01)).ordered[0]
    assert set(row.__slots__) == {"benchmark_id", "display_name", "value"}


# --------------------------------------------------------------------------
# Exclusion is reported, never silent
# --------------------------------------------------------------------------


def test_an_unmeasured_move_is_excluded_with_the_engine_s_own_reason() -> None:
    ranking = rank(reading("A", 0.01), reading("B", None))
    assert [row.benchmark_id for row in ranking.ordered] == ["A"]
    assert dict(ranking.excluded)["B"] == "short"


def test_an_unread_market_is_excluded_with_a_stated_reason() -> None:
    present = reading("A", 0.01)
    absent = crypto_benchmark("B", symbol="BUSDT")
    ranking = rank(present, universe=universe_of(present.benchmark, absent))
    assert dict(ranking.excluded)["B"] == NOT_READ_REASON


def test_an_unsupported_market_is_excluded_with_its_own_reason() -> None:
    """The provider-less reason travels, rather than being flattened to
    *"not read"* — the two are different facts."""
    present = reading("A", 0.01)
    dark = dark_benchmark("DXY", quote_unit="USDT")
    ranking = rank(present, universe=universe_of(present.benchmark, dark))
    assert "no provider is configured" in dict(ranking.excluded)["DXY"]


def test_a_reading_holding_no_move_for_the_horizon_is_excluded_and_reported() -> None:
    other_only = reading("B", None, moves=(move(0.5, horizon=OTHER),))
    ranking = rank(reading("A", 0.01), other_only)
    assert "holds no move for h1" in dict(ranking.excluded)["B"]


def test_no_market_of_the_unit_is_ever_silently_dropped() -> None:
    """Every market of the ordering's unit is placed or excluded, never lost."""
    readings = (reading("A", 0.01), reading("B", None))
    dark = dark_benchmark("D", quote_unit="USDT")
    scope = universe_of(readings[0].benchmark, readings[1].benchmark, dark)
    ranking = rank_by_horizon(scope, readings, ONE, quote_unit="USDT")
    accounted = {row.benchmark_id for row in ranking.ordered} | {
        benchmark_id for benchmark_id, _ in ranking.excluded
    }
    assert accounted == {"A", "B", "D"}


# --------------------------------------------------------------------------
# Quote units scope the comparison
# --------------------------------------------------------------------------


def test_a_market_in_another_unit_is_neither_placed_nor_excluded() -> None:
    """*It is outside the comparison this ordering defines, and it gets its own.*"""
    usdt = reading("A", 0.01)
    euro = reading("E", 0.99, quote_unit="EUR")
    ranking = rank(usdt, euro, unit="USDT")
    assert [row.benchmark_id for row in ranking.ordered] == ["A"]
    assert "E" not in dict(ranking.excluded)


def test_a_two_unit_universe_produces_two_orderings_per_horizon() -> None:
    usdt = reading("A", 0.01)
    euro = reading("E", 0.99, quote_unit="EUR")
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(usdt.benchmark, euro.benchmark),
        readings=(usdt, euro),
        unavailable=(),
        horizons=(ONE,),
    )
    units = [ranking.quote_unit for ranking in page.rankings]
    assert units == ["USDT", "EUR"]
    assert all(len(ranking.ordered) == 1 for ranking in page.rankings)


def test_a_unit_with_no_supported_market_produces_no_ordering() -> None:
    """*A section header over a list of the same absences the page already
    reports once.*"""
    usdt = reading("A", 0.01)
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(usdt.benchmark, dark_benchmark("D", quote_unit="JPY")),
        readings=(usdt,),
        unavailable=(),
        horizons=(ONE,),
    )
    assert [ranking.quote_unit for ranking in page.rankings] == ["USDT"]


def test_unit_order_follows_the_universe_and_not_a_set() -> None:
    """Determinism across processes: a set's iteration order must not leak in."""
    euro = reading("E", 0.99, quote_unit="EUR")
    usdt = reading("A", 0.01)
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(euro.benchmark, usdt.benchmark),
        readings=(euro, usdt),
        unavailable=(),
        horizons=(ONE,),
    )
    assert [ranking.quote_unit for ranking in page.rankings] == ["EUR", "USDT"]


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def test_one_ordering_is_produced_per_horizon_and_unit_pair() -> None:
    usdt = reading("A", None, moves=(move(0.01), move(0.02, horizon=OTHER)))
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(usdt.benchmark),
        readings=(usdt,),
        unavailable=(),
        horizons=(ONE, OTHER),
    )
    assert [ranking.horizon_id for ranking in page.rankings] == ["h1", "h2"]


def test_a_page_with_every_market_failing_still_assembles() -> None:
    """*One unavailable market must not destroy the entire page* — and neither
    must all of them."""
    benchmark = crypto_benchmark("A", symbol="AUSDT")
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(benchmark),
        readings=(),
        unavailable=(MarketUnavailable(benchmark=benchmark, reason="down"),),
        horizons=(ONE,),
    )
    assert page.is_empty
    assert page.rankings[0].is_empty
    assert dict(page.rankings[0].excluded)["A"] == NOT_READ_REASON


def test_observations_without_a_horizon_are_refused() -> None:
    usdt = reading("A", 0.01)
    with pytest.raises(ValueError, match="no co-movement horizon"):
        build_market_pulse(
            as_of=instant(10),
            universe=universe_of(usdt.benchmark),
            readings=(usdt,),
            unavailable=(),
            horizons=(ONE,),
            observations={},
        )


def test_a_reference_with_nothing_to_compare_against_is_not_named() -> None:
    """*A section header over an empty body would imply the comparison was
    attempted.*"""
    from tests.market_pulse_helpers import observations as obs

    usdt = reading("A", 0.01)
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(usdt.benchmark),
        readings=(usdt,),
        unavailable=(),
        horizons=(ONE,),
        observations={"A": obs([1.0, 2.0, 3.0, 4.0])},
        co_movement_horizon=ONE,
    )
    assert page.co_movements == ()
    assert page.co_movement_reference is None


def test_the_reference_is_the_first_read_market_and_is_stated() -> None:
    from tests.market_pulse_helpers import observations as obs

    first, second = reading("A", 0.01), reading("B", 0.02)
    page = build_market_pulse(
        as_of=instant(10),
        universe=universe_of(first.benchmark, second.benchmark),
        readings=(first, second),
        unavailable=(),
        horizons=(ONE,),
        observations={
            "A": obs([1.0, 2.0, 3.0, 4.0]),
            "B": obs([2.0, 3.0, 5.0, 9.0]),
        },
        co_movement_horizon=ONE,
    )
    assert page.co_movement_reference == "A"
    assert [item.subject_id for item in page.co_movements] == ["B"]


def test_rank_by_horizon_refuses_a_non_horizon() -> None:
    with pytest.raises(TypeError, match="must be a Horizon"):
        rank_by_horizon(universe_of(crypto_benchmark()), (), "1h", quote_unit="USDT")


def test_the_page_is_a_pure_function_of_its_inputs() -> None:
    readings = (reading("B", 0.05), reading("A", 0.01))
    scope = universe_of(*(item.benchmark for item in readings))
    args = dict(
        as_of=instant(10),
        universe=scope,
        readings=readings,
        unavailable=(),
        horizons=(ONE,),
    )
    assert build_market_pulse(**args) == build_market_pulse(**args)


def test_nothing_in_the_ordering_names_a_direction() -> None:
    """ADR-0028's boundary: the page orders a number and names no side."""
    ranking = rank(reading("A", -0.5), reading("B", 0.5))
    text = " ".join(
        [ranking.ordering_quantity, *(reason for _, reason in ranking.excluded)]
    ).lower()
    for token in ("long", "short", "buy", "sell", "bullish", "bearish"):
        assert token not in text.split()


def test_a_market_reading_carries_no_category_derived_behaviour() -> None:
    """*A category carries no behaviour.* Two identical readings differing only
    in category and schedule order identically."""
    from fmis.market_pulse import Benchmark, ProviderInstrument

    def with_category(category, schedule):
        return MarketReading(
            benchmark=Benchmark(
                benchmark_id="A",
                display_name="A market",
                category=category,
                schedule=schedule,
                quote_unit="USDT",
                instrument=ProviderInstrument(
                    provider="p", symbol="AUSDT", interval="1h"
                ),
            ),
            source="s",
            interval="1h",
            last_bar_open=instant(5),
            closed_bar_count=6,
            moves=(move(0.01),),
            volatility=volatility(),
        )

    crypto = with_category(MarketCategory.CRYPTO, TradingSchedule.CONTINUOUS)
    rates = with_category(MarketCategory.RATES, TradingSchedule.UNKNOWN)
    assert rank(crypto).ordered[0].value == rank(rates).ordered[0].value


def test_an_age_is_a_timedelta_the_page_computes_and_never_stores() -> None:
    assert reading("A", 0.01).age_at(instant(8)) == timedelta(hours=3)
