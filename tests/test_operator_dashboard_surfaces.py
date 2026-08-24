"""The three sections whose populated form the other files never build.

Rate facts, paper trades and statistics all need heavier fixtures than a swing
workspace does, and every one of them carries a rule worth asserting: yields
move in basis points, paper is never real exposure, and a rate below the sample
floor is refused rather than printed.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import statistics_helpers as S
from operator_dashboard_helpers import AT, benchmark, level_for, macro_of, reading_for

from fmis.macro import RateFact
from fmis.macro.rates import RateChange
from fmis.market_pulse import QuantityKind
from fmis.operator_dashboard import (
    build_snapshot,
    macro_view,
    paper_view,
    performance_views,
    render_page,
)
from fmis.operator_dashboard.models import PaperRow, PaperView
from fmis.statistics import DEFAULT_SAMPLE_POLICY, SamplePolicy
from fmis.statistics.collect import CollectedTrades
from fmis.statistics.report import build_report

LOW = SamplePolicy(minimum_sample=2)


def _report(*trades, policy: SamplePolicy = LOW, **kwargs):
    return build_report(
        CollectedTrades(
            trades=trades, refused=(), store_root="/tmp/statistics", present=True
        ),
        at=S.at(10),
        policy=policy,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Macro rate facts
# ---------------------------------------------------------------------------


def _rate_report():
    subject = benchmark("US10Y", quantity_kind=QuantityKind.RATE_LIKE)
    fact = RateFact(
        benchmark_id="US10Y",
        display_name=subject.display_name,
        level=level_for(subject, value=4.69),
        changes=(
            (
                "latest_observation",
                RateChange(
                    from_value=4.65,
                    to_value=4.69,
                    basis_points=4.0,
                    percentage_points=0.04,
                    relative_change=0.0086,
                    relative_unavailable_reason=None,
                ),
            ),
        ),
        unavailable_horizons=(("21_observations", "too few observations"),),
    )
    report = macro_of([reading_for(subject)], levels=[level_for(subject, value=4.69)])
    return type(report)(
        as_of=report.as_of,
        universe=report.universe,
        levels=report.levels,
        readings=report.readings,
        unavailable=report.unavailable,
        rate_facts=(fact,),
        relationships=report.relationships,
        horizons=report.horizons,
    )


def test_a_yields_move_crosses_as_basis_points_never_as_a_percentage() -> None:
    """**A yield that went from 4.65 to 4.69 moved 4 basis points.** Calling
    that a 0.86% return describes a different quantity in a unit that invites
    comparison with an equity move."""
    view = macro_view(_rate_report())
    row = next(row for row in view.rows if row.benchmark_id == "US10Y")
    assert row.change_unit == "basis points"
    measured = next(cell for cell in row.moves if cell.value is not None)
    assert measured.value == 4.0
    assert measured.metric == "basis points"


def test_an_unavailable_rate_window_keeps_its_reason() -> None:
    view = macro_view(_rate_report())
    row = next(row for row in view.rows if row.benchmark_id == "US10Y")
    absent = next(cell for cell in row.moves if cell.value is None)
    assert absent.unavailable_reason == "too few observations"


def test_a_rate_move_renders_with_its_basis_point_unit() -> None:
    html = render_page(
        build_snapshot(refreshed_at=AT, reference_time=AT, macro=_rate_report()),
        "/markets",
    )
    assert "+4.0 bp" in html
    assert "Yields move in basis points" in html


# ---------------------------------------------------------------------------
# Paper
# ---------------------------------------------------------------------------


def _paper_rows():
    return PaperView(
        rows=(
            PaperRow(
                activation_id="act-1",
                market="BTCUSDT",
                state="OPEN",
                open_size="0.5",
                bars_in_trade=12,
                stop_widenings=1,
                entry="100",
                stop="95",
                initial_stop="90",
                initial_risk="50",
                total_r="2",
                max_favourable_r="3",
                max_adverse_r="-0.5",
            ),
            PaperRow(
                activation_id="act-2",
                market="ETHUSDT",
                state="PENDING",
                open_size="0",
                stop="0",
                initial_stop="0",
                entry_reason="the activation has not filled, so there is no entry",
                total_r_reason="no entry, so no R is stateable",
            ),
        )
    )


def test_every_paper_metric_reaches_the_page_or_states_its_absence() -> None:
    from fmis.operator_dashboard.render import _paper_body

    html = _paper_body(_paper_rows())
    for value in ("act-1", "BTCUSDT", "0.5", "100", "95", "90", "50", "2", "3", "-0.5", "12"):
        assert value in html
    assert "the activation has not filled" in html
    assert "no entry, so no R is stateable" in html


def test_a_pending_paper_trade_shows_absence_not_a_zero_r() -> None:
    """**Absence remains absence.** A pending activation has no R, and printing
    zero would claim the trade is flat rather than that it has not started."""
    from fmis.operator_dashboard.render import _paper_body

    html = _paper_body(_paper_rows())
    pending = html[html.index("act-2") :]
    assert "no entry, so no R is stateable" in pending


def test_the_paper_note_reaches_the_page() -> None:
    from fmis.operator_dashboard.render import _paper_body

    html = _paper_body(PaperView(rows=(), note="the simulator read 0 activations"))
    assert "the simulator read 0 activations" in html


def test_a_workspace_with_no_paper_produces_an_empty_view_not_a_failure() -> None:
    import swing_workspace_helpers as W

    view = paper_view(W.workspace_of(W.result(W.assessment("BTCUSDT"))))
    assert view.rows == ()


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


def test_a_populated_corpus_produces_one_view_per_quote_asset() -> None:
    """**Figures are never summed across quote assets.** A profit in USDT and
    one in BTC do not add to a number that is money."""
    report = _report(
        S.stat("a", quote="USDT"),
        S.stat("b", quote="USDT", net="-40"),
        # A different base, because a market exchanges one asset for another.
        S.stat("c", symbol="ETH", quote="BTC", net="0.01", risk="0.005", r_multiple="2"),
    )
    views = performance_views(report)
    assert {view.quote_asset for view in views} == {"USDT", "BTC"}


def test_the_headline_figures_are_the_engines_own() -> None:
    report = _report(S.stat("a"), S.stat("b", net="-40"))
    view = next(view for view in performance_views(report) if view.quote_asset == "USDT")
    asset = next(a for a in report.assets if str(a.quote_asset.code) == "USDT")
    assert view.net == asset.performance.net_profit.text
    assert view.trades == asset.general.total
    assert view.sample_floor == report.policy.minimum_sample


def test_a_rate_below_the_sample_floor_is_refused_with_its_reason() -> None:
    """A blank cell would read as a zero win rate rather than as a refusal to
    state one."""
    report = _report(S.stat("a"), policy=DEFAULT_SAMPLE_POLICY)
    view = performance_views(report)[0]
    assert view.win_rate is None
    assert view.win_rate_reason
    assert "30" in view.win_rate_reason or "sample" in view.win_rate_reason.lower()


def test_a_sufficient_sample_states_the_rate() -> None:
    report = _report(S.stat("a"), S.stat("b", net="-40"), policy=LOW)
    view = performance_views(report)[0]
    assert view.win_rate is not None
    assert view.win_rate_reason is None


def test_the_equity_curve_crosses_step_for_step_with_exact_decimals() -> None:
    report = _report(S.stat("a", net="100"), S.stat("b", net="-40", closed_day=2))
    view = next(view for view in performance_views(report) if view.quote_asset == "USDT")
    asset = next(a for a in report.assets if str(a.quote_asset.code) == "USDT")
    assert len(view.equity) == len(asset.equity.points)
    assert [step.cumulative for step in view.equity] == [
        point.cumulative.text for point in asset.equity.points
    ]
    assert Decimal(view.equity[-1].cumulative) == Decimal("60")


def test_the_drawdown_maximum_crosses_or_states_its_absence() -> None:
    report = _report(S.stat("a", net="100"), S.stat("b", net="-40", closed_day=2))
    view = next(view for view in performance_views(report) if view.quote_asset == "USDT")
    assert view.max_drawdown is not None or view.max_drawdown_reason is not None


def test_the_performance_page_renders_the_curve_and_the_tiles() -> None:
    report = _report(S.stat("a", net="100"), S.stat("b", net="-40", closed_day=2))
    html = render_page(
        build_snapshot(refreshed_at=AT, reference_time=AT, statistics=report),
        "/performance",
    )
    assert "<svg" in html
    assert "drawn, not observed" in html
    assert "never summed across quote assets" in html
    assert "USDT" in html


def test_the_overview_shows_the_performance_headline() -> None:
    report = _report(S.stat("a", net="100"), S.stat("b", net="-40", closed_day=2))
    html = render_page(
        build_snapshot(refreshed_at=AT, reference_time=AT, statistics=report), "/"
    )
    assert "Performance" in html
    assert "Sample n" in html


def test_an_empty_corpus_renders_the_empty_message_not_a_failure() -> None:
    html = render_page(
        build_snapshot(refreshed_at=AT, reference_time=AT, statistics=_report()),
        "/performance",
    )
    assert "No closed trade is recorded" in html
    assert "Nothing failed" in html


def test_the_equity_basis_is_printed_so_the_curve_cannot_be_misread() -> None:
    """Open positions are excluded and no mark-to-market value is included —
    the page must say so beside the chart."""
    report = _report(S.stat("a", net="100"), S.stat("b", net="-40", closed_day=2))
    view = performance_views(report)[0]
    assert "Realized profit and loss" in view.equity_basis
    assert "open positions are excluded" in view.equity_basis
