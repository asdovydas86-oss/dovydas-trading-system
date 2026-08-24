"""Milestone BU — the macro composition root and the pulse integration.

Two contracts are proved here.

**The macro root**: one read per market, per-market failure isolation for source
conditions only, an unsupported market never reached, and a programmer defect
that propagates rather than being rendered as a market that could not be read.

**The pulse integration**: BT's dark rows became measured rows, no market is
read twice across the two pages, the yields never enter a return ordering, and
nothing about the crypto half of the page changed.

Nothing here touches the network.
"""

from __future__ import annotations

import pytest

from fmis.macro import MacroContextReport
from fmis.market_pulse import (
    DEFAULT_PULSE_UNIVERSE,
    MACRO_BENCHMARK_IDS,
    MACRO_PROVIDER,
    QuantityKind,
    render_market_pulse,
)
from fmis.pipeline.macro import (
    CROSS_ASSET_REFERENCE_ID,
    macro_universe,
    run_macro_context,
)
from fmis.pipeline.market_data import (
    MarketDataSources,
    UnknownProviderError,
    observations_for_benchmark,
)
from fmis.pipeline.pulse import run_market_pulse
from tests.macro_helpers import fred_transport_for, not_found, series_ending
from tests.market_pulse_helpers import (
    error_response,
    instant,
    linear_klines,
    ok_response,
    transport_for,
)

AS_OF = instant(500)


def macro_bodies(**overrides):
    """A CSV for every macro series in the default registry, ending near AS_OF."""
    bodies = {}
    for index, benchmark in enumerate(DEFAULT_PULSE_UNIVERSE.supported):
        if benchmark.instrument.provider != MACRO_PROVIDER:
            continue
        bodies[benchmark.instrument.symbol] = series_ending(
            benchmark.instrument.symbol,
            AS_OF,
            base=100.0 + index,
            step=float(index + 1) * 0.5,
            count=60,
        )
    bodies.update(overrides)
    return bodies


def crypto_bodies():
    return {
        benchmark.instrument.symbol: ok_response(
            linear_klines(100.0, float(index + 1), 200)
        )
        for index, benchmark in enumerate(DEFAULT_PULSE_UNIVERSE.supported)
        if benchmark.instrument.provider != MACRO_PROVIDER
    }


def sources_for(bodies=None, crypto=None) -> MarketDataSources:
    return MarketDataSources(
        binance_transport=transport_for(crypto_bodies() if crypto is None else crypto),
        fred_transport=fred_transport_for(macro_bodies() if bodies is None else bodies),
        clock=lambda: AS_OF,
    )


def run(**extra) -> MacroContextReport:
    defaults = dict(as_of=AS_OF, sources=sources_for())
    defaults.update(extra)
    return run_macro_context(**defaults)


# --------------------------------------------------------------------------
# Scope
# --------------------------------------------------------------------------


def test_the_macro_scope_is_a_projection_of_the_one_registry() -> None:
    scope = macro_universe()
    assert [entry.benchmark_id for entry in scope.benchmarks] == list(
        MACRO_BENCHMARK_IDS
    )
    for entry in scope.benchmarks:
        assert DEFAULT_PULSE_UNIVERSE.benchmark_for(entry.benchmark_id) is entry


def test_the_dark_markets_are_members_of_the_macro_scope() -> None:
    """*"Which of these can this system not tell me about" is one of the
    questions this page answers.*"""
    scope = macro_universe()
    dark = {entry.benchmark_id for entry in scope.unsupported}
    assert dark == {"DXY", "XAU"}


def test_no_crypto_market_is_in_the_macro_scope() -> None:
    scope = macro_universe()
    assert "BTC" not in {entry.benchmark_id for entry in scope.benchmarks}


def test_the_cross_asset_reference_is_not_a_member_of_the_scope() -> None:
    """*Putting it in the scope would make it a macro market.*"""
    scope = macro_universe()
    assert scope.benchmark_for(CROSS_ASSET_REFERENCE_ID) is None


# --------------------------------------------------------------------------
# The ordinary run
# --------------------------------------------------------------------------


def test_every_supported_macro_market_is_read_and_the_report_assembles() -> None:
    report = run()
    assert report.read_count == 5
    assert report.unavailable == ()
    assert report.unsupported_count == 2
    assert not report.is_empty
    for benchmark_id in ("SPX", "USDBROAD", "US2Y", "US10Y", "VIX"):
        assert report.reading_for(benchmark_id) is not None
        assert report.level_for(benchmark_id) is not None


def test_only_the_yields_produce_a_rate_fact() -> None:
    report = run()
    assert {fact.benchmark_id for fact in report.rate_facts} == {"US2Y", "US10Y"}
    for fact in report.rate_facts:
        assert fact.level.quantity_kind is QuantityKind.RATE_LIKE


def test_each_market_is_read_exactly_once() -> None:
    """*The page costs exactly one request per market plus one for the
    reference.* The level, the rate fact and the relationship all reuse the one
    series rather than asking again."""
    fred = fred_transport_for(macro_bodies())
    binance = transport_for(crypto_bodies())
    run_macro_context(
        as_of=AS_OF,
        sources=MarketDataSources(
            binance_transport=binance, fred_transport=fred, clock=lambda: AS_OF
        ),
    )
    assert sorted(fred.calls) == sorted(set(fred.calls))
    assert len(fred.calls) == 5
    # Exactly one crypto request, for the cross-asset reference.
    assert binance.calls == ["BTCUSDT"]


def test_omitting_the_relationships_omits_the_reference_request_too() -> None:
    binance = transport_for(crypto_bodies())
    report = run_macro_context(
        as_of=AS_OF,
        sources=MarketDataSources(
            binance_transport=binance,
            fred_transport=fred_transport_for(macro_bodies()),
            clock=lambda: AS_OF,
        ),
        with_relationships=False,
    )
    assert report.relationships == ()
    assert report.relationship_reference is None
    assert binance.calls == []


def test_an_unsupported_market_is_never_asked_for() -> None:
    fred = fred_transport_for(macro_bodies())
    run_macro_context(
        as_of=AS_OF,
        sources=MarketDataSources(
            binance_transport=transport_for(crypto_bodies()),
            fred_transport=fred,
            clock=lambda: AS_OF,
        ),
    )
    assert "DXY" not in fred.calls
    assert "XAU" not in fred.calls


def test_the_report_is_measured_against_the_supplied_instant_not_a_clock() -> None:
    early = run(as_of=instant(200))
    late = run(as_of=AS_OF)
    assert early.as_of != late.as_of
    assert early.level_for("SPX").observed_at <= instant(200)


def test_two_runs_over_one_snapshot_produce_one_report() -> None:
    bodies = macro_bodies()
    crypto = crypto_bodies()
    first = run(sources=sources_for(bodies, crypto))
    second = run(sources=sources_for(bodies, crypto))
    assert first == second


# --------------------------------------------------------------------------
# Failure isolation
# --------------------------------------------------------------------------


def test_one_failing_market_does_not_cost_the_others() -> None:
    report = run(sources=sources_for(macro_bodies(DGS10=not_found())))
    assert report.read_count == 4
    assert [entry.benchmark_id for entry in report.unavailable] == ["US10Y"]
    assert report.reading_for("SPX") is not None


def test_a_failure_between_two_successes_is_isolated() -> None:
    report = run(sources=sources_for(macro_bodies(DTWEXBGS=not_found())))
    assert report.reading_for("SPX") is not None
    assert report.reading_for("VIX") is not None
    assert [entry.benchmark_id for entry in report.unavailable] == ["USDBROAD"]


def test_a_failed_market_carries_the_source_s_own_words() -> None:
    report = run(sources=sources_for(macro_bodies(VIXCLS=not_found())))
    reason = report.unavailable[0].reason
    assert "fred VIXCLS 1d" in reason
    assert "FredAPIError" in reason
    assert "404" in reason


def test_every_market_failing_still_produces_a_report() -> None:
    bodies = {series_id: not_found() for series_id in macro_bodies()}
    report = run(sources=sources_for(bodies))
    assert report.is_empty
    assert len(report.unavailable) == 5
    assert report.levels == ()
    assert report.relationships == ()


def test_a_failed_market_gets_no_level_and_no_rate_fact() -> None:
    report = run(sources=sources_for(macro_bodies(DGS10=not_found())))
    assert report.level_for("US10Y") is None
    assert report.rate_fact_for("US10Y") is None
    assert report.rate_fact_for("US2Y") is not None


def test_a_failing_reference_omits_the_section_rather_than_repeating_one_reason() -> None:
    """*The same fact repeated five times is not five facts.*"""
    report = run(
        sources=MarketDataSources(
            binance_transport=transport_for({"BTCUSDT": error_response()}),
            fred_transport=fred_transport_for(macro_bodies()),
            clock=lambda: AS_OF,
        )
    )
    assert report.read_count == 5
    assert report.relationships == ()
    assert report.relationship_reference is None


def test_a_programming_defect_inside_a_transport_propagates() -> None:
    """*A `KeyError` rendered as "this market could not be read" teaches the
    owner to ignore both.*"""

    def broken(url: str):
        raise KeyError("a defect inside FMITS")

    with pytest.raises(KeyError):
        run(
            sources=MarketDataSources(
                binance_transport=transport_for(crypto_bodies()),
                fred_transport=broken,
                clock=lambda: AS_OF,
            )
        )


def test_an_attribute_error_inside_a_transport_propagates() -> None:
    def broken(url: str):
        raise AttributeError("a defect inside FMITS")

    with pytest.raises(AttributeError):
        run(
            sources=MarketDataSources(
                binance_transport=transport_for(crypto_bodies()),
                fred_transport=broken,
                clock=lambda: AS_OF,
            )
        )


# --------------------------------------------------------------------------
# Provider dispatch
# --------------------------------------------------------------------------


def test_a_benchmark_naming_an_unknown_provider_is_a_registry_defect() -> None:
    """*The market will not become readable by retrying*, so this is raised
    rather than reported as a source outage."""
    from fmis.market_pulse import (
        Benchmark,
        MarketCategory,
        ProviderInstrument,
        TradingSchedule,
    )

    stray = Benchmark(
        benchmark_id="X",
        display_name="X",
        category=MarketCategory.EQUITY_INDEX,
        schedule=TradingSchedule.SESSION_BOUND,
        quote_unit="index points",
        instrument=ProviderInstrument(
            provider="bloomberg", symbol="SPX", interval="1d"
        ),
    )
    with pytest.raises(UnknownProviderError, match="no adapter for"):
        observations_for_benchmark(
            stray, as_of=AS_OF, sources=MarketDataSources()
        )


def test_an_unsupported_benchmark_is_refused_before_any_adapter_is_chosen() -> None:
    dark = DEFAULT_PULSE_UNIVERSE.benchmark_for("XAU")
    with pytest.raises(ValueError, match="never fetched"):
        observations_for_benchmark(dark, as_of=AS_OF, sources=MarketDataSources())


def test_the_series_identity_names_the_provider_and_symbol_it_came_from() -> None:
    spx = DEFAULT_PULSE_UNIVERSE.benchmark_for("SPX")
    observations = observations_for_benchmark(
        spx, as_of=AS_OF, sources=sources_for()
    )
    assert observations.series_id == "fred SP500 1d"
    assert observations.frequency == "1d"


def test_observations_after_the_instant_are_excluded() -> None:
    spx = DEFAULT_PULSE_UNIVERSE.benchmark_for("SPX")
    observations = observations_for_benchmark(
        spx, as_of=instant(200), sources=sources_for()
    )
    assert all(moment <= instant(200) for moment in observations.timestamps)


# --------------------------------------------------------------------------
# Pulse integration
# --------------------------------------------------------------------------


def pulse(**extra):
    defaults = dict(as_of=AS_OF, sources=sources_for())
    defaults.update(extra)
    return run_market_pulse(**defaults)


def test_the_dark_rows_became_measured_rows() -> None:
    """The milestone's stated product outcome, on the pulse page."""
    page = pulse()
    for benchmark_id in ("SPX", "USDBROAD", "US2Y", "US10Y", "VIX"):
        reading = page.reading_for(benchmark_id)
        assert reading is not None, benchmark_id
        assert reading.source == MACRO_PROVIDER


def test_the_markets_with_no_source_stay_dark() -> None:
    page = pulse()
    assert {entry.benchmark_id for entry in page.universe.unsupported} == {
        "DXY",
        "XAU",
    }
    assert page.reading_for("DXY") is None
    assert page.reading_for("XAU") is None


def test_the_crypto_half_of_the_page_is_unchanged() -> None:
    page = pulse()
    for benchmark_id in ("BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"):
        reading = page.reading_for(benchmark_id)
        assert reading is not None
        assert reading.interval == "1h"
        assert {move.horizon_id for move in reading.moves} == {
            "latest_bar",
            "24_bars",
            "168_bars",
        }


def test_a_macro_market_is_measured_over_its_own_cadence_s_horizons() -> None:
    """*A market never holds a move for the other family's window at all.*"""
    page = pulse()
    spx = page.reading_for("SPX")
    assert {move.horizon_id for move in spx.moves} == {
        "latest_observation",
        "5_observations",
        "21_observations",
    }
    assert spx.move_for("24_bars") is None


def test_no_ordering_ever_places_a_yield() -> None:
    """*A yield's move is a difference in basis points, not a return.*"""
    page = pulse()
    for ranking in page.rankings:
        placed = {row.benchmark_id for row in ranking.ordered}
        assert "US2Y" not in placed
        assert "US10Y" not in placed


def test_no_ordering_mixes_two_observation_cadences() -> None:
    """The comparison the brief calls potentially invalid, made unreachable."""
    page = pulse()
    for ranking in page.rankings:
        intervals = {
            page.reading_for(row.benchmark_id).interval for row in ranking.ordered
        }
        assert len(intervals) == 1, (ranking.horizon_id, intervals)


def test_no_ordering_mixes_two_quote_units() -> None:
    page = pulse()
    for ranking in page.rankings:
        for row in ranking.ordered:
            benchmark = page.universe.benchmark_for(row.benchmark_id)
            assert benchmark.quote_unit == ranking.quote_unit


def test_co_movement_stays_within_one_cadence() -> None:
    """A daily series and an hourly one share no bar opens, so every such pair
    would be an unavailable row for a fact about two calendars. `fmits macro`
    measures those pairs properly, over shared dates."""
    page = pulse()
    measured = {entry.subject_id for entry in page.co_movements}
    assert measured <= {"ETH", "SOL", "BNB", "XRP", "DOGE"}
    assert page.co_movement_reference == "BTC"


def test_the_two_pages_read_each_market_once_each_and_never_twice_within_one() -> None:
    """*Do not duplicate fetches between `fmits pulse` and `fmits macro`.*

    They are separate invocations, so each reads what it needs; what is asserted
    is that neither reads one market twice, and that they share one dispatch
    layer rather than each carrying its own provider logic.
    """
    fred = fred_transport_for(macro_bodies())
    binance = transport_for(crypto_bodies())
    shared = MarketDataSources(
        binance_transport=binance, fred_transport=fred, clock=lambda: AS_OF
    )
    run_market_pulse(as_of=AS_OF, sources=shared)
    assert sorted(binance.calls) == sorted(set(binance.calls))
    assert sorted(fred.calls) == sorted(set(fred.calls))
    assert len(binance.calls) == 6
    assert len(fred.calls) == 5


def test_the_pulse_page_gains_no_macro_narrative() -> None:
    text = render_market_pulse(pulse())
    lowered = text.lower()
    for banned in (
        "risk-on",
        "risk off",
        "risk-off",
        "tightening",
        "easing",
        "hawkish",
        "dovish",
        "safe haven",
        "flight to",
        "pressuring",
    ):
        assert banned not in lowered


def test_supplying_both_a_sources_record_and_a_legacy_argument_is_refused() -> None:
    """*Which of the two won would not be visible in the page that came out.*"""
    with pytest.raises(ValueError, match="supply one or the other"):
        run_market_pulse(
            as_of=AS_OF, sources=sources_for(), transport=transport_for({})
        )


def test_a_registry_with_no_cross_asset_reference_omits_the_section() -> None:
    """*Returns `None` when the registry holds no such market, which makes the
    relationships section absent rather than fatal.*"""
    from fmis.market_pulse import MarketUniverse

    without_btc = MarketUniverse(
        name="no-reference",
        benchmarks=tuple(
            entry
            for entry in DEFAULT_PULSE_UNIVERSE.benchmarks
            if entry.benchmark_id != CROSS_ASSET_REFERENCE_ID
        ),
    )
    report = run_macro_context(
        as_of=AS_OF, sources=sources_for(), reference_universe=without_btc
    )
    assert report.read_count == 5
    assert report.relationships == ()
    assert report.relationship_reference is None
