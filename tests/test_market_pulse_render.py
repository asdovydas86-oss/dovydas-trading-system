"""Milestone BT — the page: width, absence, determinism, and what it may not say.

Three claims. **No line exceeds the page width**, for any input including a
pathologically long name or provider error. **Absence is human-readable and
never omitted** — a market that could not be read has a row saying so. And the
page **says nothing directional or interpretive**: no side, no view, and no
adjective attached to a volatility figure.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from fmis.market_pulse import (
    CO_MOVEMENT_CAVEAT,
    NO_STALENESS_BOUND,
    PULSE_ORIENTATION_NOTE,
    PULSE_PAGE_WIDTH,
    SCHEDULE_LIMITATION,
    VOLATILITY_CLASSIFICATION_NOTE,
    CoMovement,
    Horizon,
    HorizonMove,
    MarketCategory,
    MarketReading,
    MarketUnavailable,
    TradingSchedule,
    VolatilityReading,
    build_market_pulse,
    render_market_pulse,
)
from tests.market_pulse_helpers import (
    crypto_benchmark,
    dark_benchmark,
    instant,
    observations,
    universe_of,
)

ONE = Horizon(
    horizon_id="h1",
    bars=1,
    description="one bar",
    wall_clock_equivalent="1 hour",
    # The `move` helper below spans exactly this, so the phrase is legitimately
    # printable — which is what makes the gapped-window tests a real contrast.
    wall_clock_span=timedelta(hours=1),
)
FOUR = Horizon(horizon_id="h4", bars=4, description="four bars")


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


def volatility(value: float | None = 0.0123, reason: str = "short"):
    measured = value is not None
    return VolatilityReading(
        value=value,
        unavailable_reason=None if measured else reason,
        metric="realized_volatility",
        observation_count=5 if measured else 0,
        window_start=instant(0) if measured else None,
        window_end=instant(4) if measured else None,
    )


def reading(
    benchmark_id="BTC",
    value=0.0321,
    *,
    display_name=None,
    schedule=TradingSchedule.CONTINUOUS,
    vol=0.0123,
    horizons=(ONE,),
):
    benchmark = crypto_benchmark(
        benchmark_id,
        symbol=f"{benchmark_id}USDT",
        display_name=display_name,
        schedule=schedule,
    )
    return MarketReading(
        benchmark=benchmark,
        source="binance-spot",
        interval="1h",
        last_bar_open=instant(5),
        closed_bar_count=6,
        moves=tuple(move(value, horizon=h) for h in horizons),
        volatility=volatility(vol),
    )


def page(*readings, universe=None, unavailable=(), horizons=(ONE,), **extra):
    scope = universe or universe_of(
        *(item.benchmark for item in readings),
        *(item.benchmark for item in unavailable),
    )
    return build_market_pulse(
        as_of=instant(10),
        universe=scope,
        readings=readings,
        unavailable=unavailable,
        horizons=horizons,
        **extra,
    )


def render(*args, **kwargs) -> str:
    return render_market_pulse(page(*args, **kwargs))


def flat(text: str) -> str:
    """The page with every run of whitespace collapsed to one space.

    The page wraps at 78 columns, so a sentence it prints is almost never one
    line of the output. Asserting a phrase *appears* is a statement about the
    page's content and not about where the wrapper happened to break it, and
    this is how those two are kept apart. Width itself is asserted separately,
    on the unflattened lines, by `assert_within_width`.
    """
    return " ".join(text.split())


# --------------------------------------------------------------------------
# Width — the invariant that must hold for every input
# --------------------------------------------------------------------------


def assert_within_width(text: str) -> None:
    for line in text.splitlines():
        assert len(line) <= PULSE_PAGE_WIDTH, (len(line), line)


def test_a_full_page_stays_inside_the_page_width() -> None:
    assert_within_width(render(reading("BTC"), reading("ETH", -0.02)))


def test_an_empty_page_stays_inside_the_page_width() -> None:
    failed = crypto_benchmark("BTC", symbol="BTCUSDT")
    assert_within_width(
        render(
            universe=universe_of(failed),
            unavailable=(MarketUnavailable(benchmark=failed, reason="down"),),
        )
    )


def test_a_page_of_only_unsupported_markets_stays_inside_the_page_width() -> None:
    assert_within_width(
        render(universe=universe_of(dark_benchmark("DXY"), dark_benchmark("VIX")))
    )


def test_an_extremely_long_display_name_wraps_rather_than_overflows() -> None:
    long_name = "A market with " + "an extraordinarily descriptive name " * 8
    assert_within_width(render(reading("BTC", display_name=long_name)))


def test_an_extremely_long_provider_error_wraps_rather_than_overflows() -> None:
    """*A reason cut off at column 78 is a reason the owner cannot act on.*"""
    failed = crypto_benchmark("BTC", symbol="BTCUSDT")
    long_reason = "connection reset by peer while reading /api/v3/klines " * 12
    text = render(
        universe=universe_of(failed),
        unavailable=(MarketUnavailable(benchmark=failed, reason=long_reason),),
    )
    assert_within_width(text)
    assert "connection reset by peer" in flat(text)


def test_a_hundred_markets_stay_inside_the_page_width() -> None:
    many = tuple(
        reading(f"M{index:03d}", value=index / 1000) for index in range(100)
    )
    assert_within_width(render(*many))


def test_a_long_horizon_id_wraps_rather_than_overflows() -> None:
    long_horizon = Horizon(
        horizon_id="a_horizon_identifier_of_quite_remarkable_and_unwieldy_length",
        bars=4,
        description="long",
    )
    assert_within_width(
        render(
            reading("BTC", horizons=(long_horizon,)), horizons=(long_horizon,)
        )
    )


# --------------------------------------------------------------------------
# Absence is printed, and reads as absence
# --------------------------------------------------------------------------


def test_a_provider_failure_gets_a_row_with_its_reason() -> None:
    failed = crypto_benchmark("ETH", symbol="ETHUSDT")
    text = render(
        reading("BTC"),
        universe=universe_of(
            crypto_benchmark("BTC", symbol="BTCUSDT"), failed
        ),
        unavailable=(MarketUnavailable(benchmark=failed, reason="HTTP 503"),),
    )
    assert "asked for and not delivered" in flat(text)
    assert "HTTP 503" in flat(text)


def test_an_unsupported_market_is_printed_separately_from_a_failure() -> None:
    """*A page collapsing them would teach the owner to ignore both.*"""
    text = render(
        reading("BTC"),
        universe=universe_of(
            crypto_benchmark("BTC", symbol="BTCUSDT"), dark_benchmark("DXY")
        ),
    )
    text = flat(text)
    assert "asked for and not delivered" not in text
    assert "never asked for — no provider is configured" in text
    assert "DXY" in text


def test_an_unmeasured_move_prints_its_reason_in_place_of_a_number() -> None:
    unmeasured = MarketReading(
        benchmark=crypto_benchmark("BTC", symbol="BTCUSDT"),
        source="binance-spot",
        interval="1h",
        last_bar_open=instant(5),
        closed_bar_count=2,
        moves=(move(None, reason="only 2 closed bars were available"),),
        volatility=volatility(),
    )
    text = flat(render(unmeasured))
    assert "only 2 closed bars were available" in text


def test_an_unmeasured_volatility_prints_its_reason() -> None:
    text = flat(render(reading("BTC", vol=None)))
    assert "h1 (1 hour): +3.21%" in text  # the move is still shown
    assert "BTC: short" in text


def test_a_zero_move_prints_as_a_number_and_not_as_an_absence() -> None:
    """The distinction the whole page is built around, on the page itself."""
    text = flat(render(reading("BTC", value=0.0)))
    assert "+0.00%" in text
    assert "not available" not in text.split("NOT AVAILABLE")[0]


def test_a_page_that_read_nothing_says_so_and_forbids_the_calm_reading() -> None:
    failed = crypto_benchmark("BTC", symbol="BTCUSDT")
    text = render(
        universe=universe_of(failed),
        unavailable=(MarketUnavailable(benchmark=failed, reason="down"),),
    )
    assert "No market could be read" in flat(text)
    assert "not about the markets" in flat(text)
    assert "calm, quiet or unchanged" in flat(text)


def test_a_fully_read_universe_says_nothing_is_missing() -> None:
    text = flat(render(reading("BTC")))
    assert "No reading is missing from this page" in text


# --------------------------------------------------------------------------
# Vocabulary the page may not use
# --------------------------------------------------------------------------


def test_the_page_names_no_direction_and_no_market_view() -> None:
    """ADR-0028's boundary and the milestone's own prohibition, on real output."""
    text = flat(render(reading("BTC", 0.05), reading("ETH", -0.05))).lower()
    banned = (
        "buy", "sell", "long", "short", "bullish", "bearish",
        "risk-on", "risk-off", "risk on", "risk off",
    )
    for token in banned:
        assert token not in text, token


def test_the_page_attaches_no_adjective_to_a_volatility_figure() -> None:
    """*Elevated without a baseline is a word, not a measurement.*

    **The standing note is excluded from the scan, and only it.** The note's
    whole job is to name the adjectives this page refuses — *"calling a reading
    low, normal or elevated requires a baseline"* — so scanning it would flag
    the refusal as the violation. That is the identical carve-out
    `test_directional_vocabulary_boundary.py` documents for the denial sentences
    in every engine's docstring. What is scanned is the part that varies with
    the data: the rows.
    """
    text = flat(render(reading("BTC", vol=0.9)))
    block = text.split("VOLATILITY")[1].split("CROSS-ASSET")[0]
    rows = block.replace(flat(VOLATILITY_CLASSIFICATION_NOTE), "").lower()
    assert "0.9000" in rows, "the scan must still cover the figure itself"
    for token in ("elevated", "high", "low", "normal", "calm", "spike", "quiet"):
        assert token not in rows, token


def test_the_page_prints_the_reason_it_refuses_to_classify_volatility() -> None:
    assert VOLATILITY_CLASSIFICATION_NOTE.split(".")[0] in flat(
        render(reading("BTC"))
    )


def test_the_page_prints_its_own_orientation_note_before_any_number() -> None:
    text = flat(render(reading("BTC")))
    assert PULSE_ORIENTATION_NOTE.split(".")[0] in text
    assert text.index("orientation, not a recommendation") < text.index("MARKET MOVES")


def test_the_page_prints_the_co_movement_caveat_above_any_correlation() -> None:
    subject = reading("BTC")
    other = reading("ETH")
    text = render_market_pulse(
        page(
            subject,
            other,
            observations={
                "BTC": observations([1.0, 2.0, 3.0, 5.0, 8.0]),
                "ETH": observations([2.0, 3.0, 5.0, 8.0, 14.0]),
            },
            co_movement_horizon=FOUR,
        )
    )
    text = flat(text)
    assert CO_MOVEMENT_CAVEAT.split(".")[0] in text
    assert text.index("not causation") < text.index("measured against")


def test_every_market_prints_its_asset_class_beside_its_schedule() -> None:
    """Release-gate finding R-1: `MarketCategory` was validated and never read.

    `SeriesIdentity`'s own docstring states this repository's rule — *"a field
    earns inclusion only if something in the repository today would be wrong
    without it"* — and a category that no surface printed and no calculation
    branched on failed it. It now earns inclusion: a reader can see what kind of
    market each row is, which is what makes the dark list legible as *asset
    classes* rather than five unrelated names. This test fails against the
    unfixed renderer.
    """
    text = flat(render(reading("BTC")))
    assert "market: crypto · continuous" in text


def test_every_unsupported_market_prints_the_asset_class_that_is_dark() -> None:
    """The stronger half of R-1: five dark rows naming five different asset
    classes says *"equities, the dollar, gold, rates and volatility are all
    unreadable"* — a statement five bare names cannot make."""
    text = flat(
        render(
            reading("BTC"),
            universe=universe_of(
                crypto_benchmark("BTC", symbol="BTCUSDT"),
                dark_benchmark(
                    "DXY", display_name="US Dollar Index",
                    category=MarketCategory.CURRENCY,
                ),
                dark_benchmark(
                    "SPX", display_name="S&P 500",
                    category=MarketCategory.EQUITY_INDEX,
                ),
            ),
        )
    )
    assert "US Dollar Index [DXY] · currency:" in text
    assert "S&P 500 [SPX] · equity_index:" in text


def test_the_page_prints_the_session_limitation() -> None:
    assert SCHEDULE_LIMITATION.split(".")[0] in flat(render(reading("BTC")))


# --------------------------------------------------------------------------
# Horizons: wall clock only where it is earned
# --------------------------------------------------------------------------


def test_a_continuous_market_may_print_the_wall_clock_equivalent() -> None:
    text = flat(render(reading("BTC", schedule=TradingSchedule.CONTINUOUS)))
    assert "h1 (1 hour)" in text


@pytest.mark.parametrize(
    "schedule", [TradingSchedule.SESSION_BOUND, TradingSchedule.UNKNOWN]
)
def test_a_non_continuous_market_prints_bars_and_claims_no_elapsed_time(
    schedule: TradingSchedule,
) -> None:
    """*Twenty-four hourly bars are not twenty-four hours and this package will
    not say they are.*"""
    text = flat(render(reading("BTC", schedule=schedule)))
    assert "h1 (1 bar)" in text
    assert "h1 (1 hour)" not in text


def test_an_ordering_names_a_horizon_by_bars_because_it_may_span_schedules() -> None:
    text = flat(render(reading("BTC")))
    ordering = text.split("RELATIVE ORDERING")[1].split("VOLATILITY")[0]
    assert "h1 (1 bar)" in ordering
    assert "1 hour" not in ordering


def test_a_gapped_window_never_prints_the_wall_clock_equivalent() -> None:
    """Hostile-review finding: a bar count is a duration only without gaps.

    168 hourly bars are seven days **if the provider returned every bar**. A
    `CandleSeries` permits forward gaps, so a maintenance window makes the same
    168 bars span eleven days — and the page used to print *"(7 days)"* over it.
    Now the phrase is printed only when the measured span equals the duration it
    asserts. This test fails against the unfixed renderer.
    """
    from fmis.market_pulse import HORIZON_24_BARS

    gapped = HorizonMove(
        horizon_id=HORIZON_24_BARS.horizon_id,
        bars=HORIZON_24_BARS.bars,
        value=0.05,
        unavailable_reason=None,
        metric="period_return",
        observation_count=HORIZON_24_BARS.required_observations,
        window_start=instant(0),
        window_end=instant(200),  # 24 bars, but 200 hours of calendar time
    )
    benchmark = crypto_benchmark("BTC", symbol="BTCUSDT")
    built = build_market_pulse(
        as_of=instant(500),
        universe=universe_of(benchmark),
        readings=(
            MarketReading(
                benchmark=benchmark,
                source="binance-spot",
                interval="1h",
                last_bar_open=instant(200),
                closed_bar_count=25,
                moves=(gapped,),
                volatility=volatility(),
            ),
        ),
        unavailable=(),
        horizons=(HORIZON_24_BARS,),
    )
    text = flat(render_market_pulse(built))
    assert "24_bars (24 bars): +5.00%" in text
    assert "24 hours" not in text


def test_an_ungapped_window_still_prints_the_wall_clock_equivalent() -> None:
    """The fix must not cost the normal case, which is every live page."""
    from fmis.market_pulse import HORIZON_24_BARS

    clean = HorizonMove(
        horizon_id=HORIZON_24_BARS.horizon_id,
        bars=HORIZON_24_BARS.bars,
        value=0.05,
        unavailable_reason=None,
        metric="period_return",
        observation_count=HORIZON_24_BARS.required_observations,
        window_start=instant(0),
        window_end=instant(24),
    )
    benchmark = crypto_benchmark("BTC", symbol="BTCUSDT")
    built = build_market_pulse(
        as_of=instant(500),
        universe=universe_of(benchmark),
        readings=(
            MarketReading(
                benchmark=benchmark,
                source="binance-spot",
                interval="1h",
                last_bar_open=instant(24),
                closed_bar_count=25,
                moves=(clean,),
                volatility=volatility(),
            ),
        ),
        unavailable=(),
        horizons=(HORIZON_24_BARS,),
    )
    assert "24_bars (24 hours): +5.00%" in flat(render_market_pulse(built))


def test_an_unmeasured_move_never_claims_a_wall_clock_window() -> None:
    """No window means no span to verify, so no duration may be asserted."""
    from fmis.market_pulse import HORIZON_24_BARS

    benchmark = crypto_benchmark("BTC", symbol="BTCUSDT")
    built = build_market_pulse(
        as_of=instant(500),
        universe=universe_of(benchmark),
        readings=(
            MarketReading(
                benchmark=benchmark,
                source="binance-spot",
                interval="1h",
                last_bar_open=instant(5),
                closed_bar_count=2,
                moves=(
                    HorizonMove(
                        horizon_id=HORIZON_24_BARS.horizon_id,
                        bars=HORIZON_24_BARS.bars,
                        value=None,
                        unavailable_reason="only 2 bars",
                        metric="period_return",
                        observation_count=2,
                    ),
                ),
                volatility=volatility(),
            ),
        ),
        unavailable=(),
        horizons=(HORIZON_24_BARS,),
    )
    text = flat(render_market_pulse(built))
    assert "24_bars (24 bars): only 2 bars" in text
    assert "24 hours" not in text


def test_bar_counts_are_pluralised() -> None:
    text = flat(render(reading("BTC", horizons=(ONE, FOUR)), horizons=(ONE, FOUR)))
    assert "(1 bar)" in text and "(4 bars)" in text
    assert "(1 bars)" not in text


# --------------------------------------------------------------------------
# Ordering section
# --------------------------------------------------------------------------


def test_the_ordering_prints_the_quantity_that_produced_it() -> None:
    text = flat(render(reading("BTC", 0.05), reading("ETH", 0.01)))
    assert "ordered by: period_return over the stated horizon" in text


def test_the_ordering_prints_what_it_excluded_from_itself() -> None:
    text = flat(render(reading("BTC", 0.05)))
    assert "not part of any ordering above" in text
    assert "realized volatility" in text
    assert "traded volume" in text


def test_the_highest_and_lowest_are_named_beside_their_numbers() -> None:
    """*Printed beside that number, never alone.*"""
    text = flat(render(reading("BTC", 0.05), reading("ETH", -0.01)))
    assert "highest measured move: BTC +5.00%" in text
    assert "lowest measured move: ETH -1.00%" in text


def test_a_single_market_ordering_names_no_highest_and_lowest() -> None:
    """One market is not a leader and not a laggard; it is the only reading."""
    text = render(reading("BTC", 0.05))
    assert "highest measured move" not in text


def test_an_ordering_with_nothing_to_place_says_so() -> None:
    failed = crypto_benchmark("BTC", symbol="BTCUSDT")
    text = render(
        universe=universe_of(failed),
        unavailable=(MarketUnavailable(benchmark=failed, reason="down"),),
    )
    assert "no market in this unit could be ordered" in flat(text)


# --------------------------------------------------------------------------
# Freshness and the owner's bound
# --------------------------------------------------------------------------


def test_with_no_bound_no_reading_is_called_stale() -> None:
    """*A bound this system chose for you would be a threshold it invented.*"""
    text = flat(render(reading("BTC")))
    assert NO_STALENESS_BOUND.split(".")[0] in text
    assert "stale ·" not in text


def test_with_a_bound_an_older_reading_is_marked_stale() -> None:
    text = render_market_pulse(page(reading("BTC")), max_age=timedelta(hours=1))
    assert "staleness bound: 1:00:00 (yours)" in flat(text)
    assert "stale · BTC" in flat(text)


def test_with_a_bound_a_fresh_reading_is_not_marked() -> None:
    text = render_market_pulse(page(reading("BTC")), max_age=timedelta(hours=99))
    assert "no reading exceeds it" in flat(text)
    assert "stale · BTC" not in flat(text)


def test_the_oldest_reading_bounds_the_page_and_is_named() -> None:
    text = flat(render(reading("BTC"), reading("ETH")))
    assert "oldest reading:" in text
    assert "overstated by up to one interval and is never understated" in text


def test_an_age_is_stated_for_every_reading() -> None:
    text = flat(render(reading("BTC")))
    assert "age 5:00:00" in text


def test_an_age_is_printed_to_whole_seconds() -> None:
    """A default run takes `as_of` from the wall clock, so without this every
    row carries six digits of microseconds. Truncation shortens the stated age
    by under a second against a bar-open overstatement of up to a full hour, so
    the page's *never understated* claim still holds."""
    built = build_market_pulse(
        as_of=instant(10).replace(microsecond=529724),
        universe=universe_of(crypto_benchmark("BTC", symbol="BTCUSDT")),
        readings=(reading("BTC"),),
        unavailable=(),
        horizons=(ONE,),
    )
    text = flat(render_market_pulse(built))
    assert "age 5:00:00" in text
    assert "age 5:00:00.529724" not in text
    # The `as_of` instant keeps its full precision: it is an exact moment, not
    # a duration, and rounding the thing every window is measured against would
    # be a different and much worse change.
    assert "T10:00:00.529724+00:00" in text


def test_a_non_positive_bound_is_refused() -> None:
    """*It marks every reading stale, including one taken this second.*"""
    with pytest.raises(ValueError, match="must be positive"):
        render_market_pulse(page(reading("BTC")), max_age=timedelta(0))
    with pytest.raises(ValueError, match="must be positive"):
        render_market_pulse(page(reading("BTC")), max_age=timedelta(hours=-1))


def test_a_bound_of_the_wrong_type_is_refused() -> None:
    with pytest.raises(TypeError, match="must be a timedelta"):
        render_market_pulse(page(reading("BTC")), max_age=3600)


def test_rendering_refuses_a_non_pulse() -> None:
    with pytest.raises(TypeError, match="must be a MarketPulse"):
        render_market_pulse({"as_of": "now"})


# --------------------------------------------------------------------------
# Provenance and determinism
# --------------------------------------------------------------------------


def test_every_reading_prints_its_source_interval_and_bar_open() -> None:
    text = flat(render(reading("BTC")))
    assert "binance-spot · 1h · 6 closed bars" in text
    assert "2026-08-01T05:00:00+00:00" in text


def test_the_page_prints_the_instant_it_describes() -> None:
    assert "as of: 2026-08-01T10:00:00+00:00" in flat(render(reading("BTC")))


def test_the_page_prints_its_scope_counts() -> None:
    text = render(
        reading("BTC"),
        universe=universe_of(
            crypto_benchmark("BTC", symbol="BTCUSDT"), dark_benchmark("DXY")
        ),
    )
    text = flat(text)
    assert "1 market(s) read" in text
    assert "0 provider failure(s)" in text
    assert "1 market(s) with no configured provider" in text


def test_the_same_page_rendered_twice_is_byte_identical() -> None:
    built = page(reading("BTC"), reading("ETH", -0.02))
    assert render_market_pulse(built) == render_market_pulse(built)


def test_two_pages_from_equal_inputs_are_byte_identical() -> None:
    def build():
        return render_market_pulse(page(reading("BTC"), reading("ETH", -0.02)))

    assert build() == build()


def test_the_page_ends_without_a_trailing_newline() -> None:
    text = render(reading("BTC"))
    assert not text.endswith("\n")


def test_a_co_movement_prints_its_window_and_observation_count() -> None:
    text = render_market_pulse(
        page(
            reading("BTC"),
            reading("ETH"),
            observations={
                "BTC": observations([1.0, 2.0, 3.0, 5.0, 8.0]),
                "ETH": observations([2.0, 3.0, 5.0, 8.0, 14.0]),
            },
            co_movement_horizon=FOUR,
        )
    )
    assert "measured against: BTC" in flat(text)
    assert "over 5 bars" in flat(text)


def test_a_page_with_no_reference_says_no_co_movement_was_measured() -> None:
    text = flat(render(reading("BTC")))
    assert "established no reference market" in text
