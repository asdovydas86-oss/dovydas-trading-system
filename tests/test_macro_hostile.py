"""Milestone BU — the hostile review, kept as tests.

*A plausible but misleading macro page is a failed milestone.* These are the
attacks the brief names, written as permanent tests rather than run once: each
looks for **semantic dishonesty** rather than for a crash, and several of them
would pass a page that never raised anything.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from fmis.macro import (
    ComparabilityKey,
    MacroReportError,
    build_macro_context,
    compare_for_correlation,
    compare_keys,
    macro_level,
    rate_change,
    relate_markets,
    render_macro_context,
)
from fmis.data.observation import ObservationSeries
from fmis.market_pulse import (
    DEFAULT_PULSE_UNIVERSE,
    Benchmark,
    Horizon,
    MarketCategory,
    MarketReading,
    MarketUnavailable,
    MarketUniverse,
    ProviderInstrument,
    PulseUniverseError,
    QuantityKind,
    TradingSchedule,
    VolatilityReading,
    horizons_for,
)
from fmis.pipeline.macro import macro_universe, run_macro_context
from fmis.pipeline.market_data import MarketDataSources
from tests.macro_helpers import (
    day,
    fred_transport_for,
    macro_benchmark,
    not_found,
    series_ending,
    yield_benchmark,
)
from tests.market_pulse_helpers import (
    instant,
    linear_klines,
    ok_response,
    transport_for,
)

AS_OF = instant(500)
H5 = Horizon(horizon_id="h5", bars=5, description="five observations")


def obs(values, *, series_id="s", unit="index points", step_days=1):
    return ObservationSeries(
        series_id=series_id,
        unit=unit,
        frequency="1d",
        timestamps=tuple(day(i * step_days) for i in range(len(values))),
        values=tuple(values),
    )


def key(**kwargs) -> ComparabilityKey:
    base = dict(
        quantity_kind=QuantityKind.PRICE_LIKE,
        quote_unit="index points",
        observation_interval="1d",
        horizon_id="h5",
        metric="pearson_correlation",
    )
    base.update(kwargs)
    return ComparabilityKey(**base)


# --------------------------------------------------------------------------
# The registry cannot be made to lie
# --------------------------------------------------------------------------


def test_two_markets_cannot_share_one_display_name() -> None:
    """*DXY and gold with the same display name.*

    A reader has only the name, so two markets sharing one are two facts nobody
    can tell apart — and on a macro page one of them would be the dollar.
    """
    with pytest.raises(PulseUniverseError, match="appears twice"):
        MarketUniverse(
            name="hostile",
            benchmarks=(
                macro_benchmark("DXY", series_id="DTWEXBGS", display_name="Dollar"),
                macro_benchmark("XAU", series_id="GOLD", display_name="Dollar"),
            ),
        )


def test_one_source_series_cannot_be_mapped_to_two_markets() -> None:
    """*The same provider symbol mapped to two benchmarks.*

    Two benchmarks over one series are one fact printed twice, and a comparison
    between them is a rigged tie.
    """
    with pytest.raises(PulseUniverseError, match="printed twice"):
        MarketUniverse(
            name="hostile",
            benchmarks=(
                macro_benchmark("SPX", series_id="SP500", display_name="A"),
                macro_benchmark("SPX2", series_id="SP500", display_name="B"),
            ),
        )


def test_one_benchmark_id_cannot_appear_twice() -> None:
    with pytest.raises(PulseUniverseError, match="appears twice"):
        MarketUniverse(
            name="hostile",
            benchmarks=(
                macro_benchmark("SPX", series_id="SP500", display_name="A"),
                macro_benchmark("SPX", series_id="NASDAQ100", display_name="B"),
            ),
        )


def test_a_market_cannot_be_both_wired_up_and_declared_unreadable() -> None:
    with pytest.raises(PulseUniverseError, match="wired up or it is not"):
        Benchmark(
            benchmark_id="SPX",
            display_name="S&P 500",
            category=MarketCategory.EQUITY_INDEX,
            schedule=TradingSchedule.SESSION_BOUND,
            quote_unit="index points",
            instrument=ProviderInstrument(
                provider="fred", symbol="SP500", interval="1d"
            ),
            unsupported_reason="also unsupported",
        )


def test_a_market_sampled_at_an_unknown_cadence_is_refused_loudly() -> None:
    """*A market measured over a window nobody chose for it produces figures
    under a label that does not describe them.*"""
    weird = macro_benchmark("X", series_id="X", interval="17m")
    with pytest.raises(PulseUniverseError, match="defines horizons for"):
        horizons_for(weird)


def test_the_shipped_registry_holds_no_duplicate_of_any_kind() -> None:
    universe = DEFAULT_PULSE_UNIVERSE
    ids = [entry.benchmark_id for entry in universe.benchmarks]
    names = [entry.display_name for entry in universe.benchmarks]
    instruments = [
        entry.instrument.label
        for entry in universe.benchmarks
        if entry.instrument is not None
    ]
    assert len(ids) == len(set(ids))
    assert len(names) == len(set(names))
    assert len(instruments) == len(set(instruments))


# --------------------------------------------------------------------------
# A yield can never be read as a price
# --------------------------------------------------------------------------


def test_a_yield_and_a_price_share_no_ordering_however_the_units_are_written() -> None:
    """Even if someone gave a yield the same quote unit as an index, the
    quantity kind refuses the comparison on its own."""
    same_unit_yield = key(
        quantity_kind=QuantityKind.RATE_LIKE, quote_unit="index points"
    )
    assert not compare_keys(key(), same_unit_yield).is_comparable
    assert not compare_for_correlation(key(), same_unit_yield).is_comparable


def test_a_yield_level_cannot_be_used_to_build_a_price_like_level_check() -> None:
    """A rate fact refuses a price-like level and vice versa — there is no path
    by which a basis-point figure describes an index."""
    with pytest.raises(MacroReportError):
        from fmis.macro import build_rate_fact

        build_rate_fact(
            macro_benchmark(), obs([1.0, 2.0, 3.0]), horizons=(H5,), source="fred"
        )


def test_the_shipped_yields_are_declared_rate_like() -> None:
    for benchmark_id in ("US2Y", "US10Y"):
        entry = DEFAULT_PULSE_UNIVERSE.benchmark_for(benchmark_id)
        assert entry.quantity_kind is QuantityKind.RATE_LIKE


def test_no_shipped_price_like_market_is_quoted_in_percent_per_annum() -> None:
    """A price-like market wearing a yield's unit would be the mirror of the
    error this milestone exists to prevent."""
    for entry in DEFAULT_PULSE_UNIVERSE.benchmarks:
        if entry.quantity_kind is QuantityKind.PRICE_LIKE:
            assert entry.quote_unit != "percent per annum", entry.benchmark_id


# --------------------------------------------------------------------------
# Units, scales and absurd values
# --------------------------------------------------------------------------


def test_a_thousand_digit_level_is_measured_or_refused_but_never_silently_wrong() -> None:
    """Hostile review: *a 1,000-digit Decimal.*

    A number beyond float range becomes infinite, and an infinite level is
    refused rather than propagated as a figure on a page.
    """
    from decimal import Decimal

    enormous = Decimal("9" * 1000)
    with pytest.raises(Exception):
        rate_change(float(enormous), 1.0)


def test_a_level_that_overflows_to_infinity_is_refused() -> None:
    with pytest.raises(Exception):
        macro_level(macro_benchmark(), obs([1.0, math.inf]), source="fred")


def test_a_correlation_can_never_be_printed_outside_its_own_bounds() -> None:
    left = obs([100.0, 110.0, 105.0, 118.0, 112.0, 125.0, 120.0])
    right = obs(
        [3.0 * v for v in (100.0, 110.0, 105.0, 118.0, 112.0, 125.0, 120.0)],
        series_id="r",
    )
    result = relate_markets("A", left, key(), "B", right, key(), H5)
    assert -1.0 <= result.value <= 1.0


def test_a_two_hundred_market_universe_still_renders_within_the_width() -> None:
    """Hostile review: *200 benchmarks.* Scale must not break the page."""
    members = tuple(
        macro_benchmark(
            f"M{index:03d}",
            series_id=f"S{index:03d}",
            display_name=f"Market number {index:03d}",
        )
        for index in range(200)
    )
    universe = MarketUniverse(name="big", benchmarks=members)
    readings = tuple(
        MarketReading(
            benchmark=member,
            source="fred",
            interval="1d",
            last_bar_open=day(35),
            closed_bar_count=30,
            moves=(),
            volatility=VolatilityReading(
                value=0.01,
                unavailable_reason=None,
                metric="realized_volatility",
                observation_count=22,
                window_start=day(10),
                window_end=day(35),
            ),
        )
        for member in members
    )
    report = build_macro_context(
        as_of=day(40),
        universe=universe,
        readings=readings,
        unavailable=(),
        levels=tuple(
            macro_level(member, obs([1.0, 2.0]), source="fred") for member in members
        ),
        rate_facts=(),
        horizons=(H5,),
    )
    text = render_macro_context(report)
    for line in text.splitlines():
        assert len(line) <= 78


# --------------------------------------------------------------------------
# Absences cannot be hidden
# --------------------------------------------------------------------------


def test_a_market_that_vanished_between_the_scope_and_the_page_is_refused() -> None:
    """*An absence the page cannot disclose.*"""
    spx = macro_benchmark()
    vix = macro_benchmark("VIX", series_id="VIXCLS", display_name="VIX")
    with pytest.raises(MacroReportError, match="neither a reading nor a reason"):
        build_macro_context(
            as_of=day(40),
            universe=MarketUniverse(name="m", benchmarks=(spx, vix)),
            readings=(),
            unavailable=(),
            levels=(),
            rate_facts=(),
            horizons=(H5,),
        )


def test_a_market_reported_twice_on_one_page_is_refused() -> None:
    spx = macro_benchmark()
    reading = MarketReading(
        benchmark=spx,
        source="fred",
        interval="1d",
        last_bar_open=day(35),
        closed_bar_count=30,
        moves=(),
        volatility=VolatilityReading(
            value=0.01,
            unavailable_reason=None,
            metric="realized_volatility",
            observation_count=22,
            window_start=day(10),
            window_end=day(35),
        ),
    )
    with pytest.raises(MacroReportError, match="appears twice"):
        build_macro_context(
            as_of=day(40),
            universe=MarketUniverse(name="m", benchmarks=(spx,)),
            readings=(reading,),
            unavailable=(MarketUnavailable(benchmark=spx, reason="down"),),
            levels=(),
            rate_facts=(),
            horizons=(H5,),
        )


def test_a_reading_from_the_future_is_a_clock_defect_and_is_refused() -> None:
    """Hostile review: *a future observation.*"""
    spx = macro_benchmark()
    future = MarketReading(
        benchmark=spx,
        source="fred",
        interval="1d",
        last_bar_open=day(90),
        closed_bar_count=30,
        moves=(),
        volatility=VolatilityReading(
            value=0.01,
            unavailable_reason=None,
            metric="realized_volatility",
            observation_count=22,
            window_start=day(10),
            window_end=day(35),
        ),
    )
    with pytest.raises(MacroReportError, match="clock problem"):
        build_macro_context(
            as_of=day(40),
            universe=MarketUniverse(name="m", benchmarks=(spx,)),
            readings=(future,),
            unavailable=(),
            levels=(),
            rate_facts=(),
            horizons=(H5,),
        )


def test_a_level_for_a_market_the_page_did_not_read_is_refused() -> None:
    """*A number with no reading behind it has no provenance.*"""
    spx = macro_benchmark()
    other = macro_benchmark("VIX", series_id="VIXCLS", display_name="VIX")
    reading = MarketReading(
        benchmark=spx,
        source="fred",
        interval="1d",
        last_bar_open=day(35),
        closed_bar_count=30,
        moves=(),
        volatility=VolatilityReading(
            value=0.01,
            unavailable_reason=None,
            metric="realized_volatility",
            observation_count=22,
            window_start=day(10),
            window_end=day(35),
        ),
    )
    with pytest.raises(MacroReportError, match="no reading behind it"):
        build_macro_context(
            as_of=day(40),
            universe=MarketUniverse(name="m", benchmarks=(spx,)),
            readings=(reading,),
            unavailable=(),
            levels=(macro_level(other, obs([1.0, 2.0]), source="fred"),),
            rate_facts=(),
            horizons=(H5,),
        )


# --------------------------------------------------------------------------
# The whole page under adversarial source conditions
# --------------------------------------------------------------------------


def sources(macro_overrides=None, crypto_overrides=None) -> MarketDataSources:
    from fmis.market_pulse import MACRO_PROVIDER

    macro, crypto = {}, {}
    for index, entry in enumerate(DEFAULT_PULSE_UNIVERSE.supported):
        symbol = entry.instrument.symbol
        if entry.instrument.provider == MACRO_PROVIDER:
            macro[symbol] = series_ending(
                symbol, AS_OF, base=100.0 + index, step=0.5 + index, count=60
            )
        else:
            crypto[symbol] = ok_response(linear_klines(100.0, float(index + 1), 200))
    macro.update(macro_overrides or {})
    crypto.update(crypto_overrides or {})
    return MarketDataSources(
        binance_transport=transport_for(crypto),
        fred_transport=fred_transport_for(macro),
        clock=lambda: AS_OF,
    )


def test_every_source_call_failing_still_produces_an_honest_page() -> None:
    from fmis.market_pulse import MACRO_PROVIDER

    dead = {
        entry.instrument.symbol: not_found()
        for entry in DEFAULT_PULSE_UNIVERSE.supported
        if entry.instrument.provider == MACRO_PROVIDER
    }
    report = run_macro_context(as_of=AS_OF, sources=sources(dead))
    assert report.is_empty
    text = render_macro_context(report)
    assert "it is a page with no data" in " ".join(text.split())
    # Not one figure is printed, and no zero stands in for a market.
    assert "0.0000" not in text


def test_one_failure_never_hides_a_later_success() -> None:
    """*One failure hiding later successes.* The first market fails; every one
    after it must still be read."""
    report = run_macro_context(as_of=AS_OF, sources=sources({"SP500": not_found()}))
    assert report.reading_for("SPX") is None
    for benchmark_id in ("USDBROAD", "US2Y", "US10Y", "VIX"):
        assert report.reading_for(benchmark_id) is not None


def test_a_source_returning_an_empty_series_is_a_reason_not_a_move_of_zero() -> None:
    empty = b"observation_date,SP500\n"
    report = run_macro_context(as_of=AS_OF, sources=sources({"SP500": empty}))
    assert report.reading_for("SPX") is None
    assert any(entry.benchmark_id == "SPX" for entry in report.unavailable)
    text = render_macro_context(report)
    assert "S&P 500" in text


def test_a_source_answering_with_another_series_is_refused_not_relabelled() -> None:
    """The most dangerous malformed body: a body that parses cleanly and is
    about a different market."""
    wrong = b"observation_date,NASDAQ100\n2026-08-20,100.0\n2026-08-21,101.0\n"
    report = run_macro_context(as_of=AS_OF, sources=sources({"SP500": wrong}))
    assert report.reading_for("SPX") is None
    reason = next(e for e in report.unavailable if e.benchmark_id == "SPX").reason
    assert "never relabelled" in reason


def test_a_very_long_source_message_reaches_the_page_intact() -> None:
    """*A very long provider message.* Wrapped, never truncated."""
    from fmis.providers.fred import HttpResponse

    long_body = ("x" * 5000).encode()
    report = run_macro_context(
        as_of=AS_OF,
        sources=sources({"SP500": HttpResponse(status=503, body=long_body)}),
    )
    text = render_macro_context(report)
    assert "503" in text
    for line in text.splitlines():
        assert len(line) <= 78


def test_a_weekend_gap_is_not_treated_as_missing_data() -> None:
    """*Weekend equity data treated as missing.*

    The macro fixtures observe business days only, so every window here spans
    weekends. Nothing reports a gap, because a business-day series having no
    Saturday is the series being correct.
    """
    report = run_macro_context(as_of=AS_OF, sources=sources())
    price_like = [
        reading
        for reading in report.readings
        if reading.benchmark.quantity_kind is QuantityKind.PRICE_LIKE
    ]
    assert price_like, "the fixture must read at least one price-like market"
    for reading in price_like:
        for move in reading.moves:
            assert move.is_measured, (reading.benchmark_id, move.horizon_id)
    # The yields are unavailable for a *stated* reason that is not a gap in the
    # data — a yield's move is a basis-point difference, and the rates section
    # of `fmits macro` carries it.
    for fact in report.rate_facts:
        assert fact.changes, fact.benchmark_id


def test_a_daily_series_is_never_reported_behind_schedule_by_an_hourly_bound() -> None:
    """*Stale daily data marked stale by an hourly threshold.*"""
    from fmis.market_pulse import FreshnessState

    report = run_macro_context(as_of=AS_OF, sources=sources())
    for reading in report.readings:
        assert reading.freshness_at(report.as_of) is FreshnessState.ON_SCHEDULE


def test_the_page_never_prints_a_market_it_could_not_read_as_a_number() -> None:
    report = run_macro_context(as_of=AS_OF, sources=sources({"DGS10": not_found()}))
    text = " ".join(render_macro_context(report).split())
    assert "US 10-year Treasury yield: source failure" in text
    # No level, no basis-point figure and no volatility for the failed market.
    assert report.level_for("US10Y") is None
    assert report.rate_fact_for("US10Y") is None


def test_the_unsupported_markets_are_never_silently_omitted() -> None:
    """*Unsupported benchmark silently omitted.*"""
    report = run_macro_context(as_of=AS_OF, sources=sources())
    text = " ".join(render_macro_context(report).split())
    for name in ("ICE US Dollar Index (DXY)", "Gold (spot)"):
        assert name in text


def test_the_broad_dollar_index_is_never_printed_as_dxy() -> None:
    """The single most plausible-looking lie this page could tell."""
    report = run_macro_context(as_of=AS_OF, sources=sources())
    text = " ".join(render_macro_context(report).split())
    broad_level = report.level_for("USDBROAD")
    assert broad_level is not None
    assert "DXY" not in broad_level.display_name
    assert "Jan 2006 = 100" in broad_level.unit
    # DXY appears exactly once, in the unavailable section, with its reason.
    assert text.count("DXY") == 1
    assert "licensed index" in text


# --------------------------------------------------------------------------
# The defect the live demonstration caught
# --------------------------------------------------------------------------


def test_a_yield_never_produces_a_percentage_move_anywhere() -> None:
    """**Found by the live run, not by a test.** The brief's exact prohibition:
    *"10Y shown as +0.10% instead of +10 bp"*.

    Excluding yields from the *orderings* was not enough — the figure still
    reached the market's own row on `fmits pulse`, unlabelled, where a reader
    would take it for the move. The number is now not produced at all, so no
    consumer of a `MarketReading` can print one by accident.
    """
    report = run_macro_context(as_of=AS_OF, sources=sources())
    for benchmark_id in ("US2Y", "US10Y"):
        reading = report.reading_for(benchmark_id)
        assert reading is not None
        assert reading.moves, "the windows are still named"
        for move in reading.moves:
            assert not move.is_measured, (benchmark_id, move.horizon_id)
            assert "not a price" in move.unavailable_reason
            assert "basis points" in move.unavailable_reason
        # Realized volatility rests on the same ratio construction and is
        # refused with it.
        assert not reading.volatility.is_measured


def test_no_percentage_figure_appears_on_a_yield_s_row_of_the_pulse_page() -> None:
    """The same defect, asserted at the surface a reader actually sees."""
    from fmis.market_pulse import render_market_pulse
    from fmis.pipeline.pulse import run_market_pulse

    page = run_market_pulse(as_of=AS_OF, sources=sources())
    text = render_market_pulse(page)
    block = text.split("US 10-year Treasury yield")[1].split("\n\n")[0]
    assert "%" not in block, block
    assert "basis points" in " ".join(block.split())


def test_a_yield_still_reports_its_move_in_basis_points_on_the_macro_page() -> None:
    """Refusing the wrong quantity must not lose the right one."""
    report = run_macro_context(as_of=AS_OF, sources=sources())
    fact = report.rate_fact_for("US10Y")
    assert fact is not None
    assert fact.changes
    text = " ".join(render_macro_context(report).split())
    assert " bp" in text


def test_the_ordering_refuses_a_yield_even_if_one_arrives_with_a_measured_move() -> None:
    """Defence in depth, pinned.

    After the fix above, a yield reaches an ordering with no measured move and
    would be excluded anyway — so `rank_by_horizon`'s own rate-like exclusion
    became redundant against the composition root, and a mutation removing it
    survived the suite. It is not redundant against a **hand-built** reading,
    which the models permit, and that is the path this test walks: a
    `MarketReading` carrying a measured percentage move for a rate-like
    benchmark must still never be placed in a return ordering.
    """
    from fmis.market_pulse import (
        HorizonMove,
        RATE_LIKE_EXCLUSION,
        build_market_pulse,
        rank_by_horizon,
    )

    ten_year = yield_benchmark()
    two_year = yield_benchmark("US2Y", series_id="DGS2")
    horizon = Horizon(horizon_id="h1", bars=1, description="one observation")

    def hand_made(benchmark, value):
        return MarketReading(
            benchmark=benchmark,
            source="fred",
            interval="1d",
            last_bar_open=day(35),
            closed_bar_count=30,
            moves=(
                HorizonMove(
                    horizon_id="h1",
                    bars=1,
                    value=value,
                    unavailable_reason=None,
                    metric="period_return",
                    observation_count=2,
                    window_start=day(34),
                    window_end=day(35),
                ),
            ),
            volatility=VolatilityReading(
                value=0.01,
                unavailable_reason=None,
                metric="realized_volatility",
                observation_count=22,
                window_start=day(10),
                window_end=day(35),
            ),
        )

    readings = (hand_made(ten_year, 0.0086), hand_made(two_year, 0.0))
    universe = MarketUniverse(name="rates", benchmarks=(ten_year, two_year))

    ranking = rank_by_horizon(
        universe, readings, horizon, quote_unit="percent per annum"
    )
    assert ranking.ordered == ()
    assert dict(ranking.excluded) == {
        "US10Y": RATE_LIKE_EXCLUSION,
        "US2Y": RATE_LIKE_EXCLUSION,
    }

    page = build_market_pulse(
        as_of=day(40),
        universe=universe,
        readings=readings,
        unavailable=(),
        horizons=(horizon,),
    )
    assert page.rankings == ()
