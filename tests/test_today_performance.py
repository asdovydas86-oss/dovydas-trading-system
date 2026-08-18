"""The day's page's ninth section — `fmits today`'s performance block.

The section's whole job is to carry the sample guard across a boundary without
softening it. Two failures are possible and opposite: printing a rate the guard
refused, and printing a refusal as a blank the owner reads as zero.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.accounts import Book
from fmis.money import AssetCode
from fmis.provenance import Absent
from fmis.statistics import (
    CollectedTrades,
    LifecyclePhase,
    SamplePolicy,
    StatSource,
    build_report,
)
from fmis.today import (
    PERFORMANCE_RECENT_LIMIT,
    BookPerformance,
    NotAvailable,
    PerformanceLine,
    PerformanceSummary,
    performance_summary,
)
from statistics_helpers import at, money, stat

LOW = SamplePolicy(minimum_sample=2)
HIGH = SamplePolicy(minimum_sample=500)

CORPUS = (
    stat("a", net="100", risk="50", r_multiple="2", closed_day=1),
    stat("b", net="-50", risk="50", r_multiple="-1", closed_day=2),
    stat("c", net="200", risk="50", r_multiple="4", closed_day=3),
    stat("d", phase=LifecyclePhase.OPEN, closed_day=None, net=None, r_multiple=None,
         mfe=None, mae=None, bars=None, exit_reason=None),
)


def summary(*trades, policy: SamplePolicy = LOW, when: int = 10, **kwargs):
    report = build_report(
        CollectedTrades(
            trades=trades or CORPUS, refused=(), store_root="/tmp/s", present=True
        ),
        at=at(when),
        policy=policy,
        **kwargs,
    )
    return performance_summary(report, at=at(when))


# --------------------------------------------------------------------------
# What the section says
# --------------------------------------------------------------------------


def test_the_section_reports_the_counts_and_the_floor_it_used() -> None:
    section = summary(policy=SamplePolicy(minimum_sample=9))
    assert section.trades == 4
    assert section.resolved == 3
    assert section.open_trades == 1
    assert section.sample_floor == 9
    assert not section.is_empty


def test_the_floor_policy_is_stated_once_for_the_whole_section() -> None:
    """Repeated against four figures it makes the page unreadable, which makes
    the guard easier to ignore rather than harder."""
    section = summary()
    assert "establishes nothing" in section.floor_note
    assert str(section.sample_floor) in section.floor_note


def test_the_figures_that_are_stateable_are_stated() -> None:
    section = summary()
    assert section.expectancy == "83.33333333333333333333333333 USDT"
    assert section.win_rate == "0.6666666666666666666666666667"
    assert section.quote_asset == "USDT"


def test_a_rate_below_the_floor_is_refused_in_the_short_form() -> None:
    """The full basis lives in `floor_note`; the refusal carries its two numbers."""
    section = summary(policy=HIGH)
    assert isinstance(section.win_rate, NotAvailable)
    assert section.win_rate.reason == "refused: 3 resolved trade(s), below the floor of 500"
    assert "not a rate yet" in section.win_rate.forbidden_inference


def test_a_mean_is_not_labelled_a_floor_refusal_because_it_is_not_floored() -> None:
    """Expectancy is a mean over a stated `n`, so a small corpus states it. A
    section that called its absence a floor refusal would misdirect the reader
    to the sample when the problem is elsewhere."""
    section = summary(policy=HIGH)
    assert section.expectancy == "83.33333333333333333333333333 USDT"
    assert section.average_r == "1.666666666666666666666666667"


def test_an_absent_mean_is_never_labelled_a_floor_refusal() -> None:
    """The mutation this closes passed `floored=` to expectancy, which only
    shows when expectancy is **absent** — so a corpus with a stateable one
    could not tell the difference. Here the population is empty and the floor
    is high, which is exactly where the two wordings diverge."""
    running = stat("x", phase=LifecyclePhase.OPEN, closed_day=None, net=None,
                   r_multiple=None, mfe=None, mae=None, bars=None, exit_reason=None)
    section = summary(running, policy=HIGH)
    assert isinstance(section.expectancy, NotAvailable)
    assert "floor" not in section.expectancy.reason
    assert "stateable realized profit and loss" in section.expectancy.reason
    # ...and the rate beside it *is* the guard's, so the two are distinguishable.
    assert section.win_rate.reason == "no resolved trade to state this from"


def test_an_empty_population_says_so_rather_than_below_the_floor() -> None:
    """Both are true; *"no resolved trade"* is the one that says what to do."""
    running = stat("x", phase=LifecyclePhase.OPEN, closed_day=None, net=None,
                   r_multiple=None, mfe=None, mae=None, bars=None, exit_reason=None)
    section = summary(running)
    assert isinstance(section.win_rate, NotAvailable)
    assert section.win_rate.reason == "no resolved trade to state this from"


def test_an_absence_that_is_not_the_guards_keeps_its_own_reason() -> None:
    section = summary()
    assert isinstance(section.current_equity, NotAvailable)
    assert "opening capital nowhere" in section.current_equity.reason
    assert "that the account is empty" in section.current_equity.forbidden_inference


def test_a_supplied_baseline_turns_the_equity_figure_into_money() -> None:
    section = summary(starting_equity=money("1000"))
    assert section.current_equity == "1250 USDT"
    assert section.realized == "250 USDT"


def test_closed_today_counts_the_utc_day_containing_the_reference_time() -> None:
    trades = (
        stat("a", closed_day=3, net="10"),
        stat("b", closed_day=4, net="10"),
    )
    assert summary(*trades, when=3).closed_today == 1
    assert summary(*trades, when=9).closed_today == 0


def test_the_recent_list_is_newest_first_and_bounded() -> None:
    section = summary()
    assert [line.trade_ref for line in section.recent] == ["c", "b", "a"]
    assert len(section.recent) <= PERFORMANCE_RECENT_LIMIT
    assert PERFORMANCE_RECENT_LIMIT == 10


def test_a_recent_line_carries_the_result_and_the_figures_as_text() -> None:
    line = summary().recent[0]
    assert isinstance(line, PerformanceLine)
    assert line.result == "win"
    assert line.net == "200 USDT"
    assert line.r_multiple == "4"


def test_a_single_trades_figures_are_never_labelled_a_floor_refusal() -> None:
    """The guard governs rates over a population, not a fact about one trade."""
    lonely = stat("x", net="5", r_multiple=None, closed_day=1)
    line = summary(lonely, policy=HIGH).recent[0]
    assert isinstance(line.r_multiple, NotAvailable)
    assert "floor" not in line.r_multiple.reason


# --------------------------------------------------------------------------
# Paper versus everything else
# --------------------------------------------------------------------------


def test_both_book_rows_are_always_present_even_when_one_is_empty() -> None:
    """A store holding only paper trades must not read as a statement about the
    owner's money."""
    section = summary(stat("a", book=Book.PAPER, net="10"))
    assert [row.label for row in section.books] == ["paper", "other books"]
    assert [row.trades for row in section.books] == [1, 0]


def test_the_two_book_rows_partition_the_corpus() -> None:
    section = summary(
        stat("a", book=Book.PAPER), stat("b", book=Book.SWING), stat("c", book=Book.DAY)
    )
    assert sum(row.trades for row in section.books) == section.trades


def test_a_books_own_rate_is_floored_against_that_books_population() -> None:
    trades = tuple(stat(f"p{i}", book=Book.PAPER, net="10") for i in range(4)) + (
        stat("s0", book=Book.SWING, net="10"),
    )
    section = summary(*trades, policy=SamplePolicy(minimum_sample=3))
    paper, other = section.books
    assert not isinstance(paper.win_rate, NotAvailable)
    assert isinstance(other.win_rate, NotAvailable)


def test_an_empty_books_expectancy_is_an_empty_population_not_a_floor_refusal() -> None:
    section = summary(stat("a", book=Book.SWING, net="10"), policy=LOW)
    paper, _ = section.books
    assert isinstance(paper.expectancy, NotAvailable)
    assert "floor" not in paper.expectancy.reason


# --------------------------------------------------------------------------
# The empty and unread cases
# --------------------------------------------------------------------------


def test_a_run_that_did_not_read_the_store_says_so_and_claims_nothing() -> None:
    """*"This page did not look"* and *"the owner has recorded nothing"* are
    different facts and only the second is about the owner."""
    section = performance_summary(None, at=at(1))
    assert section.is_empty
    assert isinstance(section.note, NotAvailable)
    assert "did not read the store" in section.note.reason
    assert "recorded no trade" in section.note.forbidden_inference


def test_a_store_with_no_trade_produces_an_empty_section_with_its_reason() -> None:
    report = build_report(
        CollectedTrades(trades=(), refused=(), store_root="/tmp/s", present=True),
        at=at(1),
        policy=LOW,
    )
    section = performance_summary(report, at=at(1))
    assert section.is_empty
    assert "no trade to compute statistics over" in section.note


def test_the_section_refuses_a_bad_instant_or_limit() -> None:
    report = build_report(
        CollectedTrades(trades=CORPUS, refused=(), store_root="/tmp/s", present=True),
        at=at(1), policy=LOW,
    )
    with pytest.raises(TypeError, match="at must be a datetime"):
        performance_summary(report, at="today")
    with pytest.raises(Exception):
        performance_summary(report, at=at(1), limit=-1)


def test_has_stateable_rate_is_derived_and_agrees_with_the_field() -> None:
    """Two fields that could disagree about whether a number exists is the shape
    that produced BO's invisible finished trades."""
    assert summary(policy=LOW).has_stateable_rate is True
    assert summary(policy=HIGH).has_stateable_rate is False


# --------------------------------------------------------------------------
# The model's own guards
# --------------------------------------------------------------------------


def test_a_book_row_rejects_a_negative_count() -> None:
    with pytest.raises(Exception):
        BookPerformance(label="paper", trades=-1, closed=0,
                        expectancy="x", win_rate="y")


def test_a_summary_rejects_a_recent_list_of_the_wrong_type() -> None:
    with pytest.raises(Exception):
        PerformanceSummary(recent=("not a line",))


def test_a_summary_rejects_a_books_list_of_the_wrong_type() -> None:
    with pytest.raises(Exception):
        PerformanceSummary(books=("not a book",))


def test_a_corpus_holding_something_that_is_not_a_trade_is_refused_at_the_door() -> None:
    """Found by a fixture typo that reached `quote_assets_of` as an
    `AttributeError` three layers down. A collection that cannot say what is
    wrong with it makes every consumer's failure a puzzle."""
    with pytest.raises(TypeError, match="TradeStat"):
        CollectedTrades(
            trades=((),), refused=(), store_root="/tmp/s", present=True
        )


def test_the_default_summary_is_empty_and_states_every_absence() -> None:
    section = PerformanceSummary()
    assert section.is_empty
    for value in (
        section.expectancy, section.win_rate, section.profit_factor,
        section.average_r, section.current_equity, section.current_drawdown,
    ):
        assert isinstance(value, NotAvailable)
        assert value.reason and value.owned_by and value.forbidden_inference


# --------------------------------------------------------------------------
# The rendered block's remaining branches
# --------------------------------------------------------------------------
#
# Reached by the release gate's coverage re-measurement. Each is a shape the
# builder can produce and no earlier test happened to build.


def rendered(section) -> list[str]:
    from fmis.today.render import _performance_block

    return _performance_block(section)


def test_a_long_figure_wraps_rather_than_overflowing_the_day_page() -> None:
    """The day's page raises on any line over 78 columns, and an exact quotient
    can run to thirty digits — so the label/value pair folds. Shortening the
    number would be a rounding policy this system does not set."""
    from fmis.today import PerformanceSummary

    # 3 (indent) + 22 (label) + 1 + the value must exceed 78, so the value has
    # to be longer than 52 characters. An exact 1/3 to thirty digits plus its
    # asset code is 34, which fits — the first draft of this test used one and
    # never reached the branch it was written for.
    long_value = "0." + "3" * 60 + " USDT"
    assert 3 + 22 + 1 + len(long_value) > 78
    section = PerformanceSummary(
        trades=1,
        quote_asset="USDT",
        expectancy=long_value,
        floor_note="rates are refused below 1 resolved trade",
    )
    lines = rendered(section)
    joined = "".join(" ".join(lines).split())
    assert "0." + "3" * 60 in joined, "the value was shortened"
    for line in lines:
        assert len(line) <= 78, f"{len(line)}: {line!r}"


def test_a_section_with_no_book_rows_renders_without_them() -> None:
    """`performance_summary` always supplies two, and a caller assembling the
    model need not — so the block must not assume they are there."""
    from fmis.today import PerformanceSummary

    section = PerformanceSummary(trades=2, books=(), floor_note="floor 1")
    lines = rendered(section)
    assert not any("PAPER vs OTHER BOOKS" in line for line in lines)


def test_a_section_with_no_recent_trades_renders_without_the_list() -> None:
    from fmis.today import PerformanceSummary

    section = PerformanceSummary(trades=2, recent=(), floor_note="floor 1")
    assert not any("LAST" in line for line in rendered(section))


def test_a_section_whose_note_is_unavailable_prints_no_trailing_prose() -> None:
    """The note is a `NotAvailable` only when the store was not read, and then
    the block has already returned — but the model permits the pairing, so the
    branch exists and is exercised here rather than assumed unreachable."""
    from fmis.today import NotAvailable, PerformanceSummary

    section = PerformanceSummary(
        trades=1,
        floor_note="floor 1",
        note=NotAvailable(
            reason="no note was produced",
            owned_by="fmis.statistics",
            forbidden_inference="that there was nothing to say",
        ),
    )
    lines = rendered(section)
    assert not any("no note was produced" in line for line in lines)


def test_a_populated_section_renders_both_book_rows_and_the_recent_list() -> None:
    """The other side of both branches, so neither is only ever seen empty."""
    section = summary(starting_equity=money("1000"))
    lines = rendered(section)
    joined = " ".join(" ".join(lines).split())
    assert "PAPER vs OTHER BOOKS" in joined
    assert "LAST 3 CLOSED" in joined
    assert "every rate here is refused" in joined
    for line in lines:
        assert len(line) <= 78, f"{len(line)}: {line!r}"
