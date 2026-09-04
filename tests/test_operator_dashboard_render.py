"""The HTML: what it must show, and what it must never imply.

Most of these assert against *misleading* output rather than against crashes. A
page that renders without error and shows a stale figure as live, an absence as
a zero, or a legitimate refusal as a fault is a worse defect than a traceback.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import swing_workspace_helpers as W
from operator_dashboard_helpers import (
    AT,
    Boom,
    benchmark,
    dark,
    level_for,
    macro_of,
    pulse_of,
    reading_for,
)

from fmis.operator_dashboard import PAGES, build_snapshot, render_page
from fmis.operator_dashboard.render import _duration, _percent, _sign_class

ROUTES = [path for path, _ in PAGES]


def _full():
    """A snapshot with every domain populated from real engine outputs."""
    return build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        workspace=W.workspace_of(
            W.result(W.assessment("BTCUSDT")),
            W.result(W.assessment("ETHUSDT", state=W.SetupState.CANDIDATE)),
            W.failed_result("SOLUSDT", "the venue returned 503"),
        ),
        pulse=pulse_of(
            [reading_for(benchmark("BTC")), reading_for(benchmark("ETH"))],
            unsupported=[dark("DXY"), dark("XAU")],
        ),
        macro=macro_of(
            [reading_for(benchmark("SPX"))],
            levels=[level_for(benchmark("SPX"), value=7674.37)],
            unsupported=[dark("XAU")],
        ),
    )


def _broken():
    return build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        workspace_error=Boom("the store could not be read"),
        pulse_error=Boom("the venue returned 503"),
        macro_error=Boom("FRED did not answer"),
        statistics_error=Boom("the corpus is unreadable"),
    )


# ---------------------------------------------------------------------------
# Every route renders
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ROUTES)
def test_every_route_renders_a_complete_document(path: str) -> None:
    html = render_page(_full(), path)
    assert html.startswith("<!DOCTYPE html>")
    assert html.rstrip().endswith("</html>")
    assert "<title>" in html


@pytest.mark.parametrize("path", ROUTES)
def test_every_route_renders_when_every_section_failed(path: str) -> None:
    """Failure isolation, end to end: no route may become unrenderable."""
    html = render_page(_broken(), path)
    assert html.startswith("<!DOCTYPE html>")
    assert "unavailable" in html


@pytest.mark.parametrize("path", ROUTES)
def test_every_route_carries_both_instants(path: str) -> None:
    """**A page that showed only one would let an hour-old snapshot look
    live.** The refresh instant says when the HTML was built; each panel's own
    as_of says what moment its figures describe."""
    html = render_page(_full(), path)
    assert "last refresh" in html
    assert "data as of" in html


@pytest.mark.parametrize("path", ROUTES)
def test_every_route_offers_the_whole_navigation(path: str) -> None:
    html = render_page(_full(), path)
    for route, title in PAGES:
        assert f'href="{route}"' in html
        assert title in html


# ---------------------------------------------------------------------------
# No write controls, anywhere
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ROUTES)
@pytest.mark.parametrize(
    "element", ["<form", "<button", "<input", "<textarea", "<select", "<script"]
)
def test_no_page_holds_an_element_that_could_submit_or_execute(
    path: str, element: str
) -> None:
    """Every interactive element is a link to another read-only view."""
    assert element not in render_page(_full(), path).lower()


@pytest.mark.parametrize("path", ROUTES)
@pytest.mark.parametrize(
    "verb",
    ["buy", "sell", "place order", "submit order", "activate", "close position"],
)
def test_no_page_offers_a_trading_action(path: str, verb: str) -> None:
    """No BUY/SELL button, and no vocabulary that reads as one."""
    html = render_page(_full(), path).lower()
    # `activate` legitimately appears as a paper-trade *state* the engine
    # produced; what must not appear is an offer to perform one.
    assert f">{verb}<" not in html
    assert f'href="/{verb.replace(" ", "-")}"' not in html


def test_the_footer_states_the_read_only_boundary_on_every_page() -> None:
    for path in ROUTES:
        html = render_page(_full(), path)
        assert "places no order" in html
        assert "no write method is reachable" in html.lower()


# ---------------------------------------------------------------------------
# Absence is never a blank and never a zero
# ---------------------------------------------------------------------------


def test_an_absent_figure_renders_the_word_and_its_reason_not_a_dash() -> None:
    """A blank cell where a risk figure belongs is read as *no risk* rather
    than as *not measured*.

    The store is **present** here: an absent store renders the whole panel as
    empty, and what this asserts is the other case — a store that was read, in
    which individual figures could not be produced.
    """
    workspace = W.workspace_of(
        W.result(W.assessment("BTCUSDT")), store=W.reading(present=True)
    )
    html = render_page(
        build_snapshot(refreshed_at=AT, reference_time=AT, workspace=workspace),
        "/portfolio",
    )
    assert "unavailable" in html
    assert 'class="absent"' in html
    assert 'class="why"' in html, "an absence must carry its reason, not just a word"


def test_a_measured_zero_is_not_rendered_as_an_absence() -> None:
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        pulse=pulse_of([reading_for(benchmark("BTC"), move=0.0)]),
    )
    html = render_page(snapshot, "/markets")
    assert "+0.00%" in html


def test_zero_gets_its_own_class_and_is_not_tinted_as_a_gain() -> None:
    """A move of exactly nothing is a real observation."""
    assert _sign_class(0.0) == "zero"
    assert _sign_class(0.01) == "pos"
    assert _sign_class(-0.01) == "neg"


def test_a_move_keeps_its_sign_explicitly() -> None:
    assert _percent(0.0231) == "+2.31%"
    assert _percent(-0.0231) == "-2.31%"
    assert _percent(0.0) == "+0.00%"


# ---------------------------------------------------------------------------
# Colour semantics
# ---------------------------------------------------------------------------


def test_wait_and_no_trade_do_not_reach_a_fault_style() -> None:
    """**WAIT must not look like failure.** Both are conclusions this system
    reached on purpose, and painting a correct refusal in the colour of an
    error teaches the owner to distrust it."""
    from fmis.operator_dashboard.theme import STYLESHEET

    for chip in ("state-wait", "state-no-trade"):
        rule = STYLESHEET.split(f".chip.{chip}")[1].split("}")[0]
        assert "--problem" not in rule
        assert "--negative" not in rule


def test_a_confirmed_setup_is_not_painted_as_a_recommendation() -> None:
    """*Confirmed* is a state the engines reached, not an instruction. It must
    not borrow the positive-number colour."""
    from fmis.operator_dashboard.theme import STYLESHEET

    rule = STYLESHEET.split(".chip.state-confirmed")[1].split("}")[0]
    assert "--positive" not in rule


# ---------------------------------------------------------------------------
# Markets
# ---------------------------------------------------------------------------


def test_markets_with_different_cadences_get_different_tables() -> None:
    """**The regression this guards.** A daily series has no twenty-four-hourly
    -bar window and never will, so a single table spanning both cadences puts
    *unavailable* where no measurement was ever attempted."""
    from fmis.market_pulse import Horizon

    daily = Horizon(horizon_id="latest_observation", bars=1, description="one day")
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        pulse=pulse_of(
            [
                reading_for(benchmark("BTC")),
                reading_for(benchmark("SPX"), horizon=daily),
            ],
            horizons=(
                Horizon(horizon_id="latest_bar", bars=1, description="one bar"),
                daily,
            ),
        ),
    )
    html = render_page(snapshot, "/markets")
    assert html.count("<table>") >= 2


def test_an_unsupported_market_is_shown_with_its_reason() -> None:
    """DXY and XAU are the live cases, and a page that omitted them would
    answer *what can this system not tell me?* with silence."""
    html = render_page(_full(), "/markets")
    assert "DXY" in html
    assert "XAU" in html
    assert "unsupported" in html
    assert "no provider is configured" in html


def test_one_repeated_reason_is_printed_once_as_a_footnote() -> None:
    """A yield holds no percentage move over any of its windows for the same
    long reason; repeating it per column buries the page."""
    reason = "this market is a rate, not a price, so no percentage return is computed"
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        pulse=pulse_of(
            [
                reading_for(benchmark("US2Y"), move=None, move_reason=reason,
                            volatility=None, volatility_reason=reason),
                reading_for(benchmark("US10Y"), move=None, move_reason=reason,
                            volatility=None, volatility_reason=reason),
            ]
        ),
    )
    html = render_page(snapshot, "/markets")
    # Once in the footnote list, and once per cell's hover title — never once
    # per cell as visible body text.
    assert html.count(f"<li><sup>1</sup> {reason}") == 1


# ---------------------------------------------------------------------------
# Swing
# ---------------------------------------------------------------------------


def test_the_swing_page_shows_all_four_groups_by_name() -> None:
    html = render_page(_full(), "/swing")
    for heading in ("Top opportunities", "Wait list", "No trade", "Could not be read"):
        assert heading in html


def test_no_trade_is_presented_as_a_conclusion_not_a_failure() -> None:
    workspace = W.workspace_of(
        W.result(W.assessment("BTCUSDT", direction=None)),
    )
    html = render_page(
        build_snapshot(refreshed_at=AT, reference_time=AT, workspace=workspace),
        "/swing",
    )
    assert "conclusion, not a failure" in html or "No trade" in html


def test_an_empty_watchlist_says_a_quiet_market_is_legitimate() -> None:
    """*"No setup confirmed"* must not read as *"the scan broke"*."""
    workspace = W.workspace_of(W.result(W.assessment("BTCUSDT", direction=None)))
    html = render_page(
        build_snapshot(refreshed_at=AT, reference_time=AT, workspace=workspace), "/"
    )
    assert "legitimate result" in html


def test_the_rows_render_in_the_workspaces_order() -> None:
    workspace = W.workspace_of(
        W.result(W.assessment("BTCUSDT")),
        W.result(W.assessment("ETHUSDT")),
        W.result(W.assessment("SOLUSDT")),
    )
    html = render_page(
        build_snapshot(refreshed_at=AT, reference_time=AT, workspace=workspace),
        "/swing",
    )
    order = [ranked.opportunity.symbol for ranked in workspace.opportunities]
    positions = [html.index(f">{symbol}<") for symbol in order]
    assert positions == sorted(positions)


def test_the_ordering_rule_is_printed_so_it_need_not_be_inferred() -> None:
    html = render_page(_full(), "/swing")
    assert "Ordering:" in html
    assert "does not reorder anything" in html


def test_a_symbol_detail_page_shows_the_engines_own_sections() -> None:
    html = render_page(_full(), "/swing", symbol="BTCUSDT")
    for heading in ("setup", "evidence", "identity", "ordering and warnings"):
        assert heading in html.lower()


def test_an_unknown_symbol_says_so_rather_than_rendering_an_empty_setup() -> None:
    """An empty detail page reads as a setup with no evidence, which is a very
    different claim from *this symbol is not on this page*.

    The wording narrowed with Slice 1 and the assertion narrowed with it. The
    page used to refuse every symbol that was not *actionable or waiting*,
    which included every `WAIT` symbol the engine had fully assessed; it now
    refuses only a symbol that produced **no assessment at all**, which is the
    honest statement and the smaller set.
    """
    html = render_page(_full(), "/swing", symbol="NOSUCHUSDT")
    assert "produced no assessment on this refresh" in html


def test_a_symbol_detail_page_offers_no_trading_action() -> None:
    html = render_page(_full(), "/swing", symbol="BTCUSDT").lower()
    assert "<button" not in html
    assert "<form" not in html


# ---------------------------------------------------------------------------
# Paper and portfolio stay apart
# ---------------------------------------------------------------------------


def test_the_portfolio_page_says_paper_is_excluded_from_its_figures() -> None:
    """**And it says so when no store is present too.** A separation that only
    appears once there is data to separate teaches the reader it is a property
    of the data rather than of the page — the same rule the paper page holds."""
    populated = render_page(
        build_snapshot(
            refreshed_at=AT,
            reference_time=AT,
            workspace=W.workspace_of(
                W.result(W.assessment("BTCUSDT")), store=W.reading(present=True)
            ),
        ),
        "/portfolio",
    )
    assert "never added into any figure" in populated

    absent = render_page(
        build_snapshot(
            refreshed_at=AT,
            reference_time=AT,
            workspace=W.workspace_of(
                W.result(W.assessment("BTCUSDT")), store=W.reading(present=False)
            ),
        ),
        "/portfolio",
    )
    assert "No durable store is present" in absent
    assert "never added into any figure on this page" in absent


def test_the_paper_page_says_none_of_it_is_real_exposure() -> None:
    """**And it says so when the page is empty too.** A framing that appears
    only alongside data teaches the reader it is a property of the data rather
    than of the page."""
    from fmis.operator_dashboard.models import PaperRow, PaperView
    from fmis.operator_dashboard.render import _paper_body

    populated = _paper_body(
        PaperView(
            rows=(
                PaperRow(
                    activation_id="pa-1",
                    market="BTCUSDT",
                    state="OPEN",
                    open_size="0.5",
                    stop="90",
                    initial_stop="90",
                ),
            )
        )
    ).lower()
    assert "none of it is real exposure" in populated

    empty = render_page(
        build_snapshot(
            refreshed_at=AT,
            reference_time=AT,
            workspace=W.workspace_of(W.result(W.assessment("BTCUSDT"))),
        ),
        "/paper",
    ).lower()
    assert "no paper trade is recorded" in empty
    assert "none of them is real exposure" in empty


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


def test_a_curve_of_fewer_than_two_points_is_not_interpolated_into_one() -> None:
    from fmis.operator_dashboard.models import PerformanceView
    from fmis.operator_dashboard.render import _equity_chart

    html = _equity_chart(PerformanceView(quote_asset="USDT"))
    assert "at least two closed trades" in html
    assert "<svg" not in html


def test_the_chart_states_that_the_line_is_drawn_and_not_observed() -> None:
    from datetime import datetime, timezone

    from fmis.operator_dashboard.models import EquityStep, PerformanceView
    from fmis.operator_dashboard.render import _equity_chart

    view = PerformanceView(
        quote_asset="USDT",
        equity=(
            EquityStep(at=AT, trade_ref="t1", delta="10", cumulative="10"),
            EquityStep(at=AT, trade_ref="t2", delta="-4", cumulative="6"),
        ),
    )
    html = _equity_chart(view)
    assert "<svg" in html
    assert "drawn, not observed" in html


def test_a_flat_curve_does_not_divide_by_a_zero_span() -> None:
    from fmis.operator_dashboard.models import EquityStep, PerformanceView
    from fmis.operator_dashboard.render import _equity_chart

    view = PerformanceView(
        quote_asset="USDT",
        equity=tuple(
            EquityStep(at=AT, trade_ref=f"t{i}", delta="0", cumulative="0")
            for i in range(4)
        ),
    )
    assert "<svg" in _equity_chart(view)


# ---------------------------------------------------------------------------
# Escaping
# ---------------------------------------------------------------------------


def test_a_hostile_symbol_is_escaped_rather_than_rendered() -> None:
    workspace = W.workspace_of(
        W.result(W.assessment("<script>alert(1)</script>"))
    )
    html = render_page(
        build_snapshot(refreshed_at=AT, reference_time=AT, workspace=workspace),
        "/swing",
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_a_hostile_failure_message_is_escaped() -> None:
    """A provider's error text is text this repository did not write."""
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        macro_error=Boom("<img src=x onerror=alert(1)>"),
    )
    html = render_page(snapshot, "/markets")
    assert "<img src=x" not in html
    assert "&lt;img" in html


def test_a_very_long_message_does_not_break_the_document() -> None:
    snapshot = build_snapshot(
        refreshed_at=AT, reference_time=AT, macro_error=Boom("x" * 40000)
    )
    html = render_page(snapshot, "/markets")
    assert html.rstrip().endswith("</html>")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "span,expected",
    [
        (timedelta(seconds=45), "45s"),
        (timedelta(minutes=3, seconds=7), "3m 7s"),
        (timedelta(hours=2, minutes=5), "2h 5m"),
        (timedelta(days=4, hours=15), "4d 15h"),
    ],
)
def test_an_age_is_rendered_compactly(span: timedelta, expected: str) -> None:
    assert _duration(span) == expected


def test_a_future_timestamp_renders_a_negative_age_rather_than_a_plausible_one() -> None:
    """**A clock problem must look like one.** Silently rendering a negative age
    as a positive duration would make a future reading look recent."""
    assert _duration(timedelta(hours=-3)).startswith("-")
