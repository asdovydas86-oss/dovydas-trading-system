"""Composition, the five pages, the text boundary, and the workspace section.

The renderer tests assert two things a page can get wrong in opposite
directions: printing a figure the guard refused, and printing a dash where a
refusal belongs. The second is the one that reads as zero.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from fmis.accounts import Book
from fmis.money import AssetCode, Money
from fmis.provenance import Absent
from fmis.statistics import (
    STATISTICS_LIMITATIONS,
    StatisticsRefusedError,
    CollectedTrades,
    LifecyclePhase,
    SamplePolicy,
    StatSource,
    build_report,
    closed_between,
    equity_from_text,
    policy_from_text,
    recent_trades,
    render_equity,
    render_expectancy,
    render_performance,
    render_statistics,
    render_trades_summary,
    report_for_store,
    statistics_store_root,
)
from statistics_helpers import at, money, stat

USDT = AssetCode("USDT")
LOW = SamplePolicy(minimum_sample=2)
HIGH = SamplePolicy(minimum_sample=1000)
WIDTH = 78

CORPUS = (
    stat("a", net="100", risk="50", r_multiple="2", closed_day=1),
    stat("b", net="-50", risk="50", r_multiple="-1", closed_day=2, mfe="0.4", mae="-1"),
    stat("c", net="200", risk="100", r_multiple="2", closed_day=3),
    stat("d", phase=LifecyclePhase.OPEN, closed_day=None, net=None, r_multiple=None,
         mfe=None, mae=None, bars=None, exit_reason=None),
)


#: Sentinel for "use `CORPUS`". `*trades or CORPUS` would be wrong: an
#: intentionally **empty** corpus is a case these tests need, and `or` cannot
#: tell it from "none supplied".
_DEFAULT = object()


def collected(*trades, refused: tuple[str, ...] = (), present: bool = True,
              default=_DEFAULT):
    return CollectedTrades(
        trades=CORPUS if (default is _DEFAULT and not trades) else trades,
        refused=refused,
        store_root="/tmp/statistics",
        present=present,
    )


def flat(page: str) -> str:
    """The page with its wrapping removed.

    Assertions about *sentences* must not depend on where the 78-column
    renderer folded them; assertions about *layout* use the raw page.
    """
    return " ".join(page.split())


def report(*trades, policy: SamplePolicy = LOW, **kwargs):
    return build_report(collected(*trades), at=at(10), policy=policy, **kwargs)


# --------------------------------------------------------------------------
# Composition
# --------------------------------------------------------------------------


def test_a_report_is_split_by_quote_asset_and_never_summed_across_it() -> None:
    """`ST-5`: no rate in this system crosses two settlement assets."""
    built = report(
        stat("a", quote="USDT", net="100"),
        stat("b", symbol="SOL", quote="BTC", net="1"),
    )
    assert [entry.quote_asset.code for entry in built.assets] == ["BTC", "USDT"]
    assert built.total_trades == 2


def test_the_primary_asset_is_the_first_by_code_and_not_by_size() -> None:
    """Ordering by trade count would make the headline figures change asset as
    the corpus grew, and an owner comparing two weeks would be comparing two
    populations without being told."""
    built = report(
        stat("a", quote="USDT"), stat("b", quote="USDT"),
        stat("c", symbol="SOL", quote="BTC"),
    )
    assert built.primary.quote_asset.code == "BTC"


def test_an_empty_store_produces_an_empty_report_with_a_reason() -> None:
    built = build_report(collected(present=False, default=None), at=at(1))
    assert built.is_empty
    assert isinstance(built.primary, Absent)
    assert built.total_trades == 0


def test_a_baseline_applies_only_to_the_asset_it_is_denominated_in() -> None:
    """One supplied baseline must not silently do duty for both."""
    built = report(
        stat("a", quote="USDT", net="100"),
        stat("b", symbol="SOL", quote="BTC", net="1"),
        starting_equity=money("1000"),
    )
    usdt = built.for_asset(AssetCode("USDT"))
    btc = built.for_asset(AssetCode("BTC"))
    assert usdt.equity.starting_equity == money("1000")
    assert isinstance(btc.equity.starting_equity, Absent)


def test_an_asset_the_store_does_not_settle_in_is_an_absence() -> None:
    absent = report().for_asset(AssetCode("EUR"))
    assert isinstance(absent, Absent)
    assert "records no trade settled in EUR" in absent.reason


def test_utilization_is_filled_in_from_the_reports_own_open_risk_total() -> None:
    built = report(
        stat("a", phase=LifecyclePhase.OPEN, closed_day=None, net=None, risk="250"),
        open_risk_ceiling=money("1000"),
    )
    assert built.primary.risk.risk_utilization == Decimal("0.25")


def test_the_report_is_recomputable_and_identical_from_the_same_inputs() -> None:
    """`AP` §25.2: `Aggregate` — recomputable, disposable."""
    first = report()
    second = report()
    assert first.to_payload() == second.to_payload()


def test_the_report_names_the_limitations_and_the_floor_it_used() -> None:
    built = report(policy=SamplePolicy(minimum_sample=7))
    payload = built.to_payload()
    assert payload["minimum_sample"] == 7
    assert len(payload["limitations"]) == len(STATISTICS_LIMITATIONS)


def test_refused_trades_travel_to_the_report_rather_than_vanishing() -> None:
    built = build_report(collected(refused=("act-9: unmappable",)), at=at(10))
    assert built.refused == ("act-9: unmappable",)


def test_recent_trades_are_newest_first_and_exclude_the_unfinished() -> None:
    latest = recent_trades(CORPUS, 10)
    assert [entry.trade_ref for entry in latest] == ["c", "b", "a"]


def test_recent_trades_break_a_tie_stably_by_reference() -> None:
    trades = (stat("zzz", closed_day=1), stat("aaa", closed_day=1))
    assert [entry.trade_ref for entry in recent_trades(trades, 2)] == ["zzz", "aaa"]
    assert [
        entry.trade_ref for entry in recent_trades(tuple(reversed(trades)), 2)
    ] == ["zzz", "aaa"]


def test_recent_trades_honours_its_limit_and_refuses_a_negative_one() -> None:
    assert len(recent_trades(CORPUS, 1)) == 1
    assert recent_trades(CORPUS, 0) == ()
    with pytest.raises(ValueError, match="non-negative"):
        recent_trades(CORPUS, -1)


def test_closed_between_is_half_open_so_days_partition_exactly_once() -> None:
    """A trade closing at midnight belongs to the day that is starting."""
    trades = (stat("a", closed_day=1), stat("b", closed_day=2))
    first = closed_between(trades, start=at(1), end=at(2))
    assert [entry.trade_ref for entry in first] == ["a"]
    second = closed_between(trades, start=at(2), end=at(3))
    assert [entry.trade_ref for entry in second] == ["b"]


def test_closed_between_refuses_a_window_that_ends_before_it_starts() -> None:
    with pytest.raises(ValueError, match="end precedes start"):
        closed_between(CORPUS, start=at(5), end=at(1))


@pytest.mark.parametrize(
    "call",
    [
        lambda: build_report("not collected", at=at(1)),
        lambda: build_report(collected(), at=at(1), policy="no"),
        lambda: build_report(collected(), at=at(1), starting_equity="1000"),
        lambda: recent_trades("no", 1),
        lambda: closed_between("no", start=at(1), end=at(2)),
    ],
)
def test_composition_refuses_wrong_types(call) -> None:
    with pytest.raises(TypeError):
        call()


# --------------------------------------------------------------------------
# Rendering — the five pages
# --------------------------------------------------------------------------


RENDERERS = (
    render_statistics,
    render_performance,
    render_expectancy,
    render_equity,
    render_trades_summary,
)


@pytest.mark.parametrize("render", RENDERERS)
def test_every_page_renders_a_populated_report(render) -> None:
    page = render(report(starting_equity=money("1000")))
    assert "FMITS" in page
    assert "LIMITATIONS" in page


@pytest.mark.parametrize("render", RENDERERS)
def test_every_page_renders_an_empty_store_without_failing(render) -> None:
    page = render(build_report(collected(present=False, default=None), at=at(1)))
    assert "NO TRADES" in page
    assert "empty corpus rather than a result of zero" in flat(page)


@pytest.mark.parametrize("render", RENDERERS)
def test_every_page_states_the_sample_floor_it_used(render) -> None:
    """A rate rendered without its floor is a rate the guard cannot defend."""
    page = render(report(policy=SamplePolicy(minimum_sample=17)))
    assert "17 trades" in page


@pytest.mark.parametrize("render", RENDERERS)
def test_every_page_refuses_a_non_report(render) -> None:
    with pytest.raises(TypeError, match="StatisticsReport"):
        render("not a report")


def test_a_refused_rate_prints_its_reason_and_never_a_bare_dash() -> None:
    """On a statistics page a dash is read as zero more often than as unknown."""
    page = flat(render_statistics(report(policy=HIGH)))
    assert "below the stated floor" in page
    assert "establishes nothing" in page


def test_a_stated_rate_prints_with_the_population_it_rests_on() -> None:
    page = render_statistics(report(policy=LOW))
    assert "Win rate" in page
    assert "(2 of 3)" in page


def test_the_cells_examined_count_is_on_the_page_beside_the_breakdowns() -> None:
    """`TRADER_WORKSPACE` §3.4.12 — the mechanism, not the paragraph."""
    page = render_statistics(report())
    assert "Cells examined" in page
    assert "No multiplicity correction" in page


def test_the_breakdown_table_shows_counts_rather_than_a_truncated_rate() -> None:
    """An exact quotient frequently does not terminate; a fixed-width column can
    only hold it by truncating, which turns a number into a different number."""
    page = render_statistics(report())
    assert "won" in page
    assert "2/3" in page


def test_the_last_trades_table_prints_every_digit_of_an_r_multiple() -> None:
    """A truncated number is a false figure; an over-long row is merely untidy."""
    long_r = stat("x", r_multiple="0.333333333333333333333333333", closed_day=1)
    page = render_trades_summary(build_report(collected(long_r), at=at(9)))
    assert "0.333333333333333333333333333" in page


def test_the_equity_page_lists_the_most_recent_steps_and_says_what_it_omitted() -> None:
    trades = tuple(stat(f"t{i}", net="10", closed_day=i + 1) for i in range(5))
    page = render_equity(build_report(collected(*trades), at=at(9)), points=2)
    assert "LAST 2 CLOSED-TRADE STEPS" in page
    assert "3 earlier step(s) are not shown" in flat(page)


def test_the_equity_page_refuses_a_negative_point_count() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        render_equity(report(), points=-1)


def test_the_trades_summary_refuses_a_negative_limit() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        render_trades_summary(report(), limit=-1)


def test_the_trades_summary_says_so_when_nothing_has_closed() -> None:
    running = stat("a", phase=LifecyclePhase.OPEN, closed_day=None, net=None)
    page = render_trades_summary(build_report(collected(running), at=at(9)))
    assert "no result to list" in flat(page)


def test_the_expectancy_page_puts_the_sample_before_the_numbers() -> None:
    """The narrowest page and the one most likely to be over-read."""
    page = render_expectancy(report())
    assert page.index("WHAT THIS RESTS ON") < page.index("Expectancy per trade")


def test_a_corpus_with_no_excursion_states_it_once_rather_than_nine_times() -> None:
    """Collapsing is safe because it is all-or-nothing: one stateable figure
    prints the full list, absences and all."""
    bare = tuple(
        stat(f"r{i}", source=StatSource.RECORDED, mae=None, mfe=None, r_multiple=None,
             closed_day=i + 1)
        for i in range(3)
    )
    page = flat(render_statistics(build_report(collected(*bare), at=at(9))))
    assert page.count("No excursion figure exists for this corpus") == 1
    assert "Average MAE" not in page


def test_one_stateable_excursion_brings_the_whole_list_back() -> None:
    trades = (
        stat("a", mae="-1", mfe="2", closed_day=1),
        stat("b", source=StatSource.RECORDED, mae=None, mfe=None, closed_day=2),
    )
    page = flat(render_statistics(build_report(collected(*trades), at=at(9))))
    assert "Average MAE" in page
    assert "No excursion figure exists for this corpus" not in page


def test_a_partly_stateable_excursion_set_prints_the_absences_too() -> None:
    """The collapse is **all**-or-nothing, and this is the case that proves it.

    Found by a mutation probe: turning the `all` into an `any` survived, because
    the only mixed fixture happened to leave every one of the nine figures
    stateable. Here capture efficiency is absent while the excursions are not,
    so an `any` would swallow six figures that exist.
    """
    trades = (
        stat("a", mae="-1", mfe="0", r_multiple="-1", closed_day=1),
        stat("b", mae="-2", mfe="0", r_multiple="-1", closed_day=2),
    )
    report = build_report(collected(*trades), at=at(9))
    quality = report.primary.quality
    assert isinstance(quality.average_capture_efficiency, Absent)
    assert not isinstance(quality.average_adverse_r, Absent)
    page = flat(render_statistics(report))
    assert "No excursion figure exists for this corpus" not in page
    assert "Average MAE" in page
    assert "Average capture" in page


def test_a_multi_asset_report_says_the_others_exist_rather_than_dropping_them() -> None:
    page = render_statistics(
        report(stat("a", quote="USDT"), stat("b", symbol="SOL", quote="BTC"))
    )
    assert "SETTLED IN USDT" in page
    assert "SETTLED IN BTC" in page
    assert "never summed across quote assets" in flat(page)


def test_a_refused_trade_is_printed_rather_than_silently_missing() -> None:
    page = render_statistics(
        build_report(collected(refused=("act-9: could not be mapped",)), at=at(9))
    )
    assert "NOT COUNTED" in page
    assert "could not be mapped" in flat(page)


def test_the_histogram_draws_every_bucket_including_the_empty_ones() -> None:
    page = render_statistics(report())
    assert "DISTRIBUTION OF R" in page
    assert "< -2" in page and ">= 3" in page


# --------------------------------------------------------------------------
# The text boundary
# --------------------------------------------------------------------------


def test_the_store_root_falls_back_to_the_persistence_default() -> None:
    assert statistics_store_root(None).is_absolute() or statistics_store_root(None).parts


def test_an_empty_store_root_flag_is_refused() -> None:
    with pytest.raises(ValueError, match="no path"):
        statistics_store_root("   ")


def test_the_policy_defaults_and_parses_a_whole_number() -> None:
    assert policy_from_text(None).minimum_sample == 30
    assert policy_from_text("12").minimum_sample == 12


def test_a_floor_of_zero_is_refused_because_it_is_no_floor_at_all() -> None:
    with pytest.raises(ValueError, match="no floor at all"):
        policy_from_text("0")


def test_a_non_numeric_floor_is_refused_with_a_sentence() -> None:
    with pytest.raises(ValueError, match="whole number"):
        policy_from_text("many")


def test_an_amount_becomes_money_in_the_named_asset() -> None:
    amount = equity_from_text("1000.5", asset="USDT", flag="--starting-equity")
    assert amount == Money(Decimal("1000.5"), USDT)


def test_no_amount_is_none_so_the_root_can_word_the_absence_once() -> None:
    assert equity_from_text(None, asset="USDT", flag="--starting-equity") is None


@pytest.mark.parametrize("raw", ["", "   ", "abc", "0", "-5"])
def test_a_bad_amount_is_refused_with_the_flags_own_name(raw: str) -> None:
    with pytest.raises(ValueError, match="--starting-equity"):
        equity_from_text(raw, asset="USDT", flag="--starting-equity")


# --------------------------------------------------------------------------
# The outer edge, over a real store
# --------------------------------------------------------------------------


def test_report_for_store_reads_a_missing_store_as_an_empty_page(tmp_path: Path) -> None:
    built = report_for_store(tmp_path / "nowhere", at=at(1))
    assert built.is_empty
    assert built.present is False


def test_report_for_store_is_byte_identical_on_a_second_run(tmp_path: Path) -> None:
    """Nothing is written, so nothing can drift between two reads."""
    from test_statistics_collect import write_trade, close, at as store_at_day

    root = tmp_path / "store"
    plan_id = write_trade(root)
    close(root, plan_id, price="120", day=3)
    first = report_for_store(root, at=store_at_day(9))
    second = report_for_store(root, at=store_at_day(9))
    assert first.to_payload() == second.to_payload()


def test_report_for_store_threads_the_point_in_time_cut(tmp_path: Path) -> None:
    from test_statistics_collect import write_trade, at as store_at_day

    root = tmp_path / "store"
    write_trade(root, day=0)
    write_trade(root, symbol="ETH", day=10)
    built = report_for_store(root, at=store_at_day(20), as_of=store_at_day(5))
    assert built.total_trades == 1
    assert not isinstance(built.as_of, Absent)


# --------------------------------------------------------------------------
# The page width — 78 columns, enforced rather than claimed
# --------------------------------------------------------------------------
#
# Added by the release gate, which found a 145-column line: the store path was
# printed on one row and nothing checked. `fmis.today.render` has had this guard
# since BJ; these pages claimed the same geometry and had none.

WIDTH = 78

LONG_ROOT = (
    "/private/var/folders/p6/q1r6rp5d6l5220m5g5kxz7040000gn/T/"
    "a-deliberately-preposterous-store-path/that-nobody-would-type/but-argparse-"
    "will-happily-accept/store"
)


def wide_report(policy: SamplePolicy = LOW, **kwargs):
    """A report whose every unbounded value is at its ugliest."""
    trades = (
        stat("a", net="100", closed_day=1,
             r_multiple="0.333333333333333333333333333"),
        stat("b", net="-50", closed_day=2, symbol="VERYLONGTICKER",
             setup_type="a-setup-name-nobody-would-choose-but-nothing-forbids",
             account="an-account-identifier-of-immoderate-length"),
        stat("c", net="200", closed_day=3),
    )
    return build_report(
        CollectedTrades(
            trades=trades, refused=("act-1: " + "x" * 200,),
            store_root=LONG_ROOT, present=True,
        ),
        at=at(10), policy=policy, **kwargs,
    )


@pytest.mark.parametrize("render", RENDERERS)
def test_no_rendered_line_exceeds_the_page_width(render) -> None:
    """Measured in **characters**. An em-dash is three bytes and one column, so
    a byte-counting check reports every line of prose as over-wide — which is
    how the gate's first pass mis-read this."""
    for line in render(wide_report(starting_equity=money("1000"))).splitlines():
        assert len(line) <= WIDTH, f"{len(line)}: {line!r}"


@pytest.mark.parametrize("render", RENDERERS)
def test_no_rendered_line_exceeds_the_width_on_an_empty_store(render) -> None:
    empty = build_report(
        CollectedTrades(trades=(), refused=(), store_root=LONG_ROOT, present=False),
        at=at(1),
    )
    for line in render(empty).splitlines():
        assert len(line) <= WIDTH, f"{len(line)}: {line!r}"


def test_an_unbounded_store_path_wraps_rather_than_running_over() -> None:
    """The defect the gate found, pinned. A truncated path is one the owner
    copies and cannot open, so it wraps — including mid-token."""
    page = render_statistics(wide_report())
    assert LONG_ROOT in flat(page).replace(" ", "") or LONG_ROOT.replace(
        "/", ""
    ) in flat(page).replace(" ", "").replace("/", "")
    assert all(len(line) <= WIDTH for line in page.splitlines())


def test_a_long_r_multiple_is_printed_in_full_across_two_lines() -> None:
    """Never truncated: a shortened number is a different number."""
    page = flat(render_trades_summary(wide_report()))
    assert "0.333333333333333333333333333" in page


def test_a_trade_reference_on_the_equity_page_is_never_shortened() -> None:
    long_ref = "trade_plan-binance_BTCUSDT_spot-20260601T100000Z-0fd5a53d14fa1a2d"
    report = build_report(
        CollectedTrades(
            trades=(stat(long_ref, net="10", closed_day=1),),
            refused=(), store_root="/tmp/s", present=True,
        ),
        at=at(9), policy=LOW,
    )
    page = flat(render_equity(report)).replace(" ", "")
    assert long_ref in page
    assert all(len(line) <= WIDTH for line in render_equity(report).splitlines())


def test_the_guard_refuses_a_line_this_module_could_not_fit() -> None:
    """Unreachable through the renderers, because every unbounded value wraps
    before it arrives — and the guard is what makes that a property rather than
    an assumption."""
    from fmis.statistics.render import _fitted

    with pytest.raises(StatisticsRefusedError, match="exceeds the 78-column page"):
        _fitted(["x" * 79])
    assert _fitted(["short", "lines"]) == "short\nlines"
