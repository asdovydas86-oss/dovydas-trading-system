"""Milestone BU — the macro page, and what it must never be readable as.

A macro page fails by being *plausible*, not by crashing. So the assertions here
are mostly about what is absent: no causal claim, no regime, no adjective on a
volatility reading, no yield move wearing a percentage sign, no window described
in days. The width contract and the absence-is-printed rule are asserted too,
because a page that truncates a reason is a page whose reasons nobody can act on.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fmis.macro import (
    COMPARABILITY_RULE,
    CORRELATION_COMPARABILITY_RULE,
    MACRO_FRESHNESS_NOTE,
    MACRO_ORIENTATION_NOTE,
    MACRO_PAGE_WIDTH,
    MACRO_RATE_NOTE,
    MACRO_RELATIONSHIP_CAVEAT,
    MACRO_SESSION_LIMITATION,
    CrossAssetRelationship,
    MacroContextReport,
    MacroLevel,
    RateFact,
    build_macro_context,
    rate_change,
    render_macro_context,
)
from fmis.market_pulse import (
    Benchmark,
    Horizon,
    MarketCategory,
    MarketReading,
    MarketUnavailable,
    MarketUniverse,
    QuantityKind,
    TradingSchedule,
    VOLATILITY_CLASSIFICATION_NOTE,
    VolatilityReading,
)
from fmis.market_pulse import HorizonMove
from tests.macro_helpers import DAILY_FRESHNESS, day, macro_benchmark, yield_benchmark

H5 = Horizon(horizon_id="h5", bars=5, description="five completed observations")
AS_OF = day(40)


def flat(text: str) -> str:
    return " ".join(text.split())


#: The standing notes the page prints verbatim. Every one of them *names* the
#: vocabulary this page refuses — the orientation note says the page will not
#: tell you markets are risk-on, the volatility note says a reading is not
#: called elevated, the freshness note says no verdict is given. A naive scan
#: for those words therefore finds the page's own denials and reports the
#: opposite of the truth. Stripping the notes first is what makes the scan a
#: statement about the *facts* the page prints.
_STANDING_NOTES = (
    MACRO_ORIENTATION_NOTE,
    MACRO_SESSION_LIMITATION,
    MACRO_RELATIONSHIP_CAVEAT,
    MACRO_FRESHNESS_NOTE,
    MACRO_RATE_NOTE,
    VOLATILITY_CLASSIFICATION_NOTE,
    COMPARABILITY_RULE,
    CORRELATION_COMPARABILITY_RULE,
)


def without_notes(text: str) -> str:
    """The page's own facts, with every standing caveat removed."""
    stripped = flat(text)
    for note in _STANDING_NOTES:
        stripped = stripped.replace(flat(note), " ")
    return stripped


def volatility(value: float | None = 0.01) -> VolatilityReading:
    if value is None:
        return VolatilityReading(
            value=None,
            unavailable_reason="not enough observations",
            metric="realized_volatility",
            observation_count=2,
        )
    return VolatilityReading(
        value=value,
        unavailable_reason=None,
        metric="realized_volatility",
        observation_count=6,
        window_start=day(0),
        window_end=day(5),
    )


def move(value: float | None = 0.01) -> HorizonMove:
    if value is None:
        return HorizonMove(
            horizon_id="h5",
            bars=5,
            value=None,
            unavailable_reason="this series supplied 3 observations",
            metric="period_return",
            observation_count=3,
        )
    return HorizonMove(
        horizon_id="h5",
        bars=5,
        value=value,
        metric="period_return",
        unavailable_reason=None,
        observation_count=6,
        window_start=day(0),
        window_end=day(5),
    )


def reading(benchmark: Benchmark, *, vol=0.01, mv=0.01) -> MarketReading:
    return MarketReading(
        benchmark=benchmark,
        source="fred",
        interval="1d",
        last_bar_open=day(35),
        closed_bar_count=30,
        moves=(move(mv),),
        volatility=volatility(vol),
    )


def level(benchmark: Benchmark, value: float) -> MacroLevel:
    return MacroLevel(
        benchmark_id=benchmark.benchmark_id,
        display_name=benchmark.display_name,
        value=value,
        unit=benchmark.quote_unit,
        quantity_kind=benchmark.quantity_kind,
        observed_at=day(35),
        source=benchmark.instrument.label,
    )


def report(
    *,
    readings=None,
    levels=None,
    rate_facts=(),
    relationships=(),
    reference=None,
    unavailable=(),
    universe=None,
) -> MacroContextReport:
    spx = macro_benchmark()
    readings = (reading(spx),) if readings is None else readings
    levels = (level(spx, 7674.37),) if levels is None else levels
    members = [item.benchmark for item in readings]
    members.extend(item.benchmark for item in unavailable)
    scope = universe or MarketUniverse(name="macro", benchmarks=tuple(members))
    return build_macro_context(
        as_of=AS_OF,
        universe=scope,
        readings=readings,
        unavailable=unavailable,
        levels=levels,
        rate_facts=rate_facts,
        horizons=(H5,),
        relationships=relationships,
        relationship_reference=reference,
    )


def render(**kwargs) -> str:
    return render_macro_context(report(**kwargs))


# --------------------------------------------------------------------------
# Width
# --------------------------------------------------------------------------


def test_the_page_shares_the_pulse_page_s_width() -> None:
    from fmis.market_pulse import PULSE_PAGE_WIDTH

    assert MACRO_PAGE_WIDTH == PULSE_PAGE_WIDTH


def test_no_line_exceeds_the_page_width() -> None:
    for line in render().splitlines():
        assert len(line) <= MACRO_PAGE_WIDTH, line


def test_a_very_long_display_name_does_not_overflow_the_width() -> None:
    """Hostile review: an unbreakable identifier is chopped, never overflowed."""
    long_name = "A" * 300
    benchmark = macro_benchmark(display_name=long_name)
    text = render(readings=(reading(benchmark),), levels=(level(benchmark, 1.0),))
    for line in text.splitlines():
        assert len(line) <= MACRO_PAGE_WIDTH


def test_a_very_long_source_error_is_wrapped_and_never_truncated() -> None:
    """*A reason cut off at column 78 is a reason the owner cannot act on.*"""
    benchmark = macro_benchmark("VIX", series_id="VIXCLS")
    reason = "the source said: " + "detail " * 60
    text = render(
        readings=(),
        levels=(),
        unavailable=(MarketUnavailable(benchmark=benchmark, reason=reason),),
    )
    assert "detail" in text
    # Every word of the reason survives, wrapped rather than cut.
    assert flat(text).count("detail") == 60
    for line in text.splitlines():
        assert len(line) <= MACRO_PAGE_WIDTH


def test_the_page_has_no_trailing_newline() -> None:
    assert not render().endswith("\n")


# --------------------------------------------------------------------------
# The sections a macro page must have
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "heading",
    [
        "MACRO & CROSS-ASSET CONTEXT",
        "MARKET LEVELS",
        "MOVES",
        "RATES",
        "VOLATILITY",
        "CROSS-ASSET RELATIONSHIPS",
        "DATA QUALITY",
        "UNAVAILABLE",
    ],
)
def test_every_named_section_is_present(heading: str) -> None:
    assert heading in render()


def test_a_level_is_printed_with_its_unit_and_never_bare() -> None:
    """*`7674.37` is not a fact; "7674.37 index points" is.*"""
    text = flat(render())
    assert "7674.3700 index points" in text


def test_a_level_names_when_it_was_observed_and_where_it_came_from() -> None:
    text = flat(render())
    assert day(35).isoformat() in text
    assert "fred SP500 1d" in text


# --------------------------------------------------------------------------
# Rates — the milestone's central formatting rule
# --------------------------------------------------------------------------


def yield_report(from_value: float, to_value: float) -> str:
    benchmark = yield_benchmark()
    fact = RateFact(
        benchmark_id=benchmark.benchmark_id,
        display_name=benchmark.display_name,
        level=level(benchmark, to_value),
        changes=(("h5", rate_change(from_value, to_value)),),
    )
    return render(
        readings=(reading(benchmark),),
        levels=(level(benchmark, to_value),),
        rate_facts=(fact,),
    )


def test_a_yield_move_is_printed_in_basis_points() -> None:
    """*A move from 4.20% to 4.30% is +10 basis points.*"""
    text = flat(yield_report(4.20, 4.30))
    assert "+10.0 bp" in text


def test_a_falling_yield_prints_a_negative_basis_point_figure() -> None:
    assert "-10.0 bp" in flat(yield_report(4.30, 4.20))


def test_the_basis_point_figure_comes_before_the_relative_change() -> None:
    """*The basis-point figure is what a rates column asks for, so it leads.*

    Measured on the row itself rather than on the page: the standing rates note
    above the section mentions the relative change while explaining why it is
    not the answer, and that mention is not the row's ordering.
    """
    row = without_notes(yield_report(4.20, 4.30))
    assert row.index("+10.0 bp") < row.index("relative change")


def test_the_relative_change_is_always_labelled_as_such() -> None:
    """*It can never be read as the answer to the same question.*"""
    text = flat(yield_report(4.20, 4.30))
    assert "relative change +2.38%" in text


def test_a_yield_move_is_never_printed_as_a_bare_percentage() -> None:
    """The exact mutation the brief names: `+0.10%` where `+10 bp` belongs."""
    text = flat(yield_report(4.20, 4.30))
    rates = text.split("RATES")[1].split("VOLATILITY")[0]
    # Every percentage in the rates section is either a level or is explicitly
    # labelled a relative change; none stands alone as "the move".
    assert "+0.10%" not in rates
    assert "+10.0 bp" in rates


def test_the_two_levels_of_the_move_are_printed_beside_the_basis_points() -> None:
    text = flat(yield_report(4.20, 4.30))
    assert "4.20% → 4.30%" in text


def test_the_rates_note_states_the_rule_the_section_follows() -> None:
    text = flat(render())
    assert "A yield is a rate, not a price" in text
    assert "4.20% to 4.30% is +10 basis points" in text


def test_a_yield_appears_in_the_rates_section_and_not_in_the_moves_section() -> None:
    """A rate has no percentage-return row to be confused with."""
    benchmark = yield_benchmark()
    fact = RateFact(
        benchmark_id="US10Y",
        display_name=benchmark.display_name,
        level=level(benchmark, 4.7),
        changes=(("h5", rate_change(4.6, 4.7)),),
    )
    text = render(
        readings=(reading(benchmark),),
        levels=(level(benchmark, 4.7),),
        rate_facts=(fact,),
    )
    moves = text.split("MOVES")[1].split("RATES")[0]
    assert "US 10-year" not in moves
    assert "No price-like market was read" in moves


def test_a_horizon_a_yield_cannot_fill_prints_the_reason_not_a_zero() -> None:
    benchmark = yield_benchmark()
    fact = RateFact(
        benchmark_id="US10Y",
        display_name=benchmark.display_name,
        level=level(benchmark, 4.7),
        changes=(),
        unavailable_horizons=(("h5", "this series supplied 3 observations"),),
    )
    text = flat(
        render(
            readings=(reading(benchmark),),
            levels=(level(benchmark, 4.7),),
            rate_facts=(fact,),
        )
    )
    assert "not available" in text
    assert "supplied 3 observations" in text
    assert "0.0 bp" not in text


# --------------------------------------------------------------------------
# Windows are never described in days
# --------------------------------------------------------------------------


def test_no_window_is_described_in_days_or_weeks() -> None:
    """*Five completed observations span seven calendar days in an ordinary
    week and nine across a holiday weekend, and this build cannot tell which.*"""
    text = flat(render())
    moves = text.split("MOVES")[1].split("RATES")[0]
    for phrase in ("5 days", "five days", "one week", "1 week", "5 sessions"):
        assert phrase not in moves


def test_a_window_is_named_by_its_observation_count() -> None:
    assert "h5 (5 observations)" in flat(render())


def test_a_one_observation_window_is_singular() -> None:
    single = Horizon(horizon_id="h1", bars=1, description="one")
    spx = macro_benchmark()
    built = build_macro_context(
        as_of=AS_OF,
        universe=MarketUniverse(name="macro", benchmarks=(spx,)),
        readings=(
            MarketReading(
                benchmark=spx,
                source="fred",
                interval="1d",
                last_bar_open=day(35),
                closed_bar_count=30,
                moves=(
                    HorizonMove(
                        horizon_id="h1",
                        bars=1,
                        value=0.01,
                        unavailable_reason=None,
                        metric="period_return",
                        observation_count=2,
                        window_start=day(34),
                        window_end=day(35),
                    ),
                ),
                volatility=volatility(),
            ),
        ),
        unavailable=(),
        levels=(level(spx, 1.0),),
        rate_facts=(),
        horizons=(single,),
    )
    text = flat(render_macro_context(built))
    assert "h1 (1 observation)" in text
    assert "(1 observations)" not in text


def test_the_session_limitation_is_stated_in_full() -> None:
    text = flat(render())
    assert "holds no trading calendar" in text
    assert "no holiday table" in text


# --------------------------------------------------------------------------
# Relationships
# --------------------------------------------------------------------------


def relationship(**kwargs) -> CrossAssetRelationship:
    base = dict(
        subject_id="SPX",
        reference_id="BTC",
        metric="pearson_correlation",
        value=-0.42,
        unavailable_reason=None,
        observation_count=22,
        aligned_count=137,
        window_start=day(10),
        window_end=day(35),
        subject_dropped=123,
        reference_dropped=62,
    )
    base.update(kwargs)
    return CrossAssetRelationship(**base)


def test_a_relationship_prints_its_value_window_and_alignment_cost() -> None:
    text = flat(render(relationships=(relationship(),), reference="BTC"))
    assert "-0.4200" in text
    assert "22 observations" in text
    assert "aligned on 137 shared date(s)" in text
    assert "dropping 123 from SPX and 62 from BTC" in text


def test_the_window_count_and_the_shared_count_are_never_one_number() -> None:
    """*A reader could not tell a pair with barely enough overlap from a pair
    with years of it.*"""
    text = flat(render(relationships=(relationship(),), reference="BTC"))
    assert "22" in text and "137" in text


def test_the_reference_market_is_named_on_the_page() -> None:
    text = flat(render(relationships=(relationship(),), reference="BTC"))
    assert "measured against: BTC" in text


def test_a_refused_relationship_prints_the_refusal_and_no_number() -> None:
    ten_year = yield_benchmark()
    refused = relationship(
        value=None,
        unavailable_reason="US10Y and BTC were not compared: not comparable: "
        "different quantity kind",
        observation_count=0,
        aligned_count=0,
        window_start=None,
        window_end=None,
        subject_dropped=0,
        reference_dropped=0,
        subject_id="US10Y",
        not_comparable_detail="not comparable: different quantity kind",
    )
    text = flat(
        render(
            readings=(reading(ten_year),),
            levels=(level(ten_year, 4.69),),
            relationships=(refused,),
            reference="BTC",
        )
    )
    assert "not available" in text
    assert "different quantity kind" in text


def test_a_relationship_naming_a_market_the_report_did_not_read_is_refused() -> None:
    """*A correlation of a market the page did not read cannot be traced to
    anything.* The report refuses to hold one at all."""
    from fmis.macro import MacroReportError

    stray = relationship(subject_id="NIKKEI")
    with pytest.raises(MacroReportError, match="holds no reading for it"):
        render(relationships=(stray,), reference="BTC")


def test_the_relationship_caveat_refuses_every_causal_reading() -> None:
    text = flat(render(relationships=(relationship(),), reference="BTC"))
    assert "not causation" in text
    assert "not a prediction" in text
    assert "not evidence that one market moved the other" in text


def test_the_caveat_states_that_a_shared_date_is_not_a_shared_hour() -> None:
    text = flat(render(relationships=(relationship(),), reference="BTC"))
    assert "same day rather than the same hours" in text


def test_a_page_with_no_relationship_says_so_rather_than_omitting_the_section() -> None:
    text = flat(render())
    assert "No relationship was measured" in text


# --------------------------------------------------------------------------
# Volatility stays unclassified
# --------------------------------------------------------------------------


def test_volatility_is_printed_as_a_number_and_never_as_an_adjective() -> None:
    assert "0.0100" in flat(render())
    assert "deliberately not classified" in flat(render())
    facts = without_notes(render()).lower()
    for banned in ("elevated", "low volatility", "high volatility", "calm", "spiking"):
        assert banned not in facts


def test_an_unmeasurable_volatility_prints_its_reason() -> None:
    spx = macro_benchmark()
    text = flat(render(readings=(reading(spx, vol=None),), levels=(level(spx, 1.0),)))
    assert "not available" in text
    assert "not enough observations" in text


# --------------------------------------------------------------------------
# Absence is printed
# --------------------------------------------------------------------------


def test_a_market_with_no_source_is_printed_with_its_reason() -> None:
    dark = Benchmark(
        benchmark_id="XAU",
        display_name="Gold (spot)",
        category=MarketCategory.COMMODITY,
        schedule=TradingSchedule.SESSION_BOUND,
        quote_unit="USD per troy ounce",
        unsupported_reason="no source configured in this build publishes gold",
    )
    spx = macro_benchmark()
    scope = MarketUniverse(name="macro", benchmarks=(spx, dark))
    text = flat(render(universe=scope))
    assert "Gold (spot)" in text
    assert "no configured source" in text
    assert "publishes gold" in text


def test_a_source_failure_and_a_missing_source_are_printed_differently() -> None:
    """*"There is no source for gold" and "FRED refused this request" are
    different facts; a page collapsing them would teach the owner to ignore
    both.*"""
    failed = macro_benchmark("VIX", series_id="VIXCLS")
    dark = Benchmark(
        benchmark_id="XAU",
        display_name="Gold (spot)",
        category=MarketCategory.COMMODITY,
        schedule=TradingSchedule.SESSION_BOUND,
        quote_unit="USD",
        unsupported_reason="no configured source publishes spot gold",
    )
    spx = macro_benchmark()
    scope = MarketUniverse(name="macro", benchmarks=(spx, failed, dark))
    text = flat(
        render(
            universe=scope,
            unavailable=(
                MarketUnavailable(benchmark=failed, reason="FredAPIError: HTTP 500"),
            ),
        )
    )
    assert "source failure" in text
    assert "no configured source" in text
    assert text.index("source failure") != text.index("no configured source")


def test_a_page_that_read_nothing_says_so_rather_than_printing_zeros() -> None:
    dark = Benchmark(
        benchmark_id="XAU",
        display_name="Gold (spot)",
        category=MarketCategory.COMMODITY,
        schedule=TradingSchedule.SESSION_BOUND,
        quote_unit="USD",
        unsupported_reason="no configured source",
    )
    scope = MarketUniverse(name="macro", benchmarks=(dark,))
    text = flat(render(readings=(), levels=(), universe=scope))
    assert "it is a page with no data" in text
    assert "0.0000" not in text


# --------------------------------------------------------------------------
# Data quality
# --------------------------------------------------------------------------


def test_freshness_is_reported_against_the_source_s_own_schedule() -> None:
    text = flat(render())
    assert "on schedule" in text
    assert "published every" in text
    assert "tolerance" in text


def test_the_freshness_note_states_why_one_bound_is_not_used() -> None:
    text = flat(render())
    assert "not against one bound applied to everything" in text
    assert "not late because it did not update in an hour" in text


def test_a_reading_older_than_its_schedule_is_reported_behind_schedule() -> None:
    spx = macro_benchmark()
    stale = MarketReading(
        benchmark=spx,
        source="fred",
        interval="1d",
        last_bar_open=day(0),
        closed_bar_count=30,
        moves=(move(),),
        volatility=volatility(),
    )
    text = flat(render(readings=(stale,), levels=(level(spx, 1.0),)))
    assert "behind schedule" in text


def test_the_word_stale_is_never_printed() -> None:
    """The page states a source's schedule, not a judgement about usability."""
    assert "stale" not in flat(render()).lower()


def test_the_comparability_rule_is_printed_rather_than_implied() -> None:
    text = flat(render())
    assert "same kind of quantity" in text
    assert "same unit" in text


# --------------------------------------------------------------------------
# Nothing interpretive reaches the page
# --------------------------------------------------------------------------


def test_the_page_contains_no_interpretive_or_causal_vocabulary() -> None:
    text = without_notes(
        render(relationships=(relationship(),), reference="BTC")
    ).lower()
    for banned in (
        "risk-on",
        "risk on",
        "risk-off",
        "risk off",
        "tightening",
        "easing",
        "hawkish",
        "dovish",
        "bullish",
        "bearish",
        "safe haven",
        "flight to quality",
        "confirms fear",
        "is hurting",
        "is pressuring",
        "should fall",
        "will fall",
        "expect",
        "forecast",
    ):
        assert banned not in text, banned


def test_the_page_states_that_it_makes_no_interpretation() -> None:
    text = flat(render())
    assert "contains no interpretation, no causal claim and no view" in text
    assert "risk-on or risk-off" in text


def test_the_page_states_it_reads_and_changes_no_trading_decision() -> None:
    text = flat(render())
    assert "no setup, plan, position or approval is read or changed" in text


def test_the_page_carries_no_overall_score_or_summary_state() -> None:
    text = without_notes(render()).lower()
    for banned in ("overall score", "macro score", "regime:", "composite", "verdict"):
        assert banned not in text


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_two_renders_of_one_report_produce_one_string() -> None:
    built = report()
    assert render_macro_context(built) == render_macro_context(built)


def test_the_renderer_refuses_something_that_is_not_a_report() -> None:
    with pytest.raises(TypeError, match="must be a MacroContextReport"):
        render_macro_context({"as_of": AS_OF})


# --------------------------------------------------------------------------
# The remaining absence branches
# --------------------------------------------------------------------------


def test_a_market_with_no_publication_schedule_says_so_rather_than_passing() -> None:
    """*The age is stated; only the verdict is not.*"""
    benchmark = macro_benchmark(freshness=None)
    text = flat(
        render(readings=(reading(benchmark),), levels=(level(benchmark, 1.0),))
    )
    assert "no schedule established" in text
    assert "on schedule ·" not in text


def test_a_reading_holding_no_move_for_a_declared_horizon_says_so() -> None:
    """A declared window a reading simply has no entry for — distinct from one
    it could not measure, which carries the engine's own reason."""
    benchmark = macro_benchmark()
    silent = MarketReading(
        benchmark=benchmark,
        source="fred",
        interval="1d",
        last_bar_open=day(35),
        closed_bar_count=30,
        moves=(),
        volatility=volatility(),
    )
    text = flat(render(readings=(silent,), levels=(level(benchmark, 1.0),)))
    assert "this reading holds no move for this horizon" in text


def test_a_yield_from_a_zero_base_prints_the_basis_points_and_names_the_absence() -> None:
    """*A yield going from 0.00% to 0.25% moved 25 bp.* The ratio is undefined
    and the page says so rather than printing a zero beside a real move."""
    benchmark = yield_benchmark()
    fact = RateFact(
        benchmark_id="US10Y",
        display_name=benchmark.display_name,
        level=level(benchmark, 0.25),
        changes=(("h5", rate_change(0.0, 0.25)),),
    )
    text = flat(
        render(
            readings=(reading(benchmark),),
            levels=(level(benchmark, 0.25),),
            rate_facts=(fact,),
        )
    )
    assert "+25.0 bp" in text
    assert "relative change not available" in text
    assert "earlier level is zero" in text


def test_a_macro_reading_holding_no_move_for_a_declared_window_says_so() -> None:
    """The macro renderer's own missing-window branch.

    `fmits macro` declares the horizons it measured and prints a row per
    declared window, so a reading that holds no entry for one states that
    rather than leaving a gap where a number belongs.
    """
    benchmark = macro_benchmark()
    silent = MarketReading(
        benchmark=benchmark,
        source="fred",
        interval="1d",
        last_bar_open=day(35),
        closed_bar_count=30,
        moves=(),
        volatility=volatility(),
    )
    text = flat(render(readings=(silent,), levels=(level(benchmark, 1.0),)))
    assert "h5 (5 observations): this reading holds no move for this horizon" in text


def test_a_macro_move_that_could_not_be_measured_prints_its_reason() -> None:
    """A window the market *has* an entry for but could not fill.

    Distinct from the missing-window case above: here the measurement was
    attempted and the engine or the history refused it, so the row carries the
    reason rather than a number — and never a zero.
    """
    benchmark = macro_benchmark()
    short = reading(benchmark, mv=None)
    text = flat(render(readings=(short,), levels=(level(benchmark, 1.0),)))
    assert "h5 (5 observations): not available — this series supplied 3 observations" in text
    assert "0.00%" not in text.split("MOVES")[1].split("RATES")[0]
