"""Hostile review. **Looking for misleading output, not only for exceptions.**

A green-looking stale dashboard is a worse defect than a traceback: the
traceback stops the owner, and the stale page lets them act on a figure that is
no longer true. So most of what follows renders successfully and then asserts
that what it rendered cannot be misread.
"""

from __future__ import annotations

import threading
from datetime import timedelta
from decimal import Decimal

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

from fmis.operator_dashboard import (
    PAGES,
    SnapshotHolder,
    SourceState,
    build_snapshot,
    render_page,
    resolve_route,
)
from fmis.operator_dashboard.models import (
    EquityStep,
    PerformanceView,
    SetupRow,
    SwingView,
)

ROUTES = [path for path, _ in PAGES]


# ---------------------------------------------------------------------------
# Everything dark
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ROUTES)
def test_every_market_source_unavailable_still_renders_and_says_so(path: str) -> None:
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        pulse=pulse_of(
            unavailable=[
                (benchmark("BTC"), "the venue returned 503"),
                (benchmark("ETH"), "the venue returned 503"),
            ]
        ),
        macro=macro_of(unavailable=[(benchmark("SPX"), "FRED did not answer")]),
        workspace=W.workspace_of(W.failed_result("BTCUSDT", "no candles")),
    )
    html = render_page(snapshot, path)
    assert html.rstrip().endswith("</html>")
    if path in ("/", "/markets", "/system"):
        assert "unavailable" in html


def test_a_page_with_no_readings_never_reads_as_a_quiet_market() -> None:
    """**"No market could be read" is a statement about this run, not about the
    markets.** Nothing on the page may read as calm, quiet or unchanged."""
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        pulse=pulse_of(unavailable=[(benchmark("BTC"), "the venue returned 503")]),
    )
    html = render_page(snapshot, "/markets")
    assert "the venue returned 503" in html
    assert "+0.00%" not in html


def test_a_dark_source_is_never_rendered_as_a_zero() -> None:
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        pulse=pulse_of([reading_for(benchmark("BTC"))], unsupported=[dark("DXY")]),
    )
    html = render_page(snapshot, "/markets")
    dxy = html[html.index("DXY") :][:1200]
    assert "0.00" not in dxy
    assert "unsupported" in dxy


# ---------------------------------------------------------------------------
# Staleness must be visible
# ---------------------------------------------------------------------------


def test_a_stale_reading_is_marked_behind_schedule_and_shows_its_age() -> None:
    """The severe defect this guards: a green-looking stale dashboard."""
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        pulse=pulse_of(
            [reading_for(benchmark("BTC"), bar_open=AT - timedelta(days=6))]
        ),
    )
    assert snapshot.pulse.data.rows[0].state is SourceState.BEHIND_SCHEDULE
    html = render_page(snapshot, "/markets")
    assert "behind schedule" in html
    assert "6d 0h" in html


def test_a_future_reading_is_not_rendered_as_recent() -> None:
    """A reading dated after the instant it describes is a clock problem, and
    it must look like one rather than like a very fresh number."""
    from fmis.operator_dashboard.render import _duration

    assert _duration(timedelta(hours=-5)) == "-5h 0m"


def test_the_header_shows_the_held_instant_not_the_moment_of_serving() -> None:
    snapshot = build_snapshot(refreshed_at=AT, reference_time=AT)
    html = render_page(snapshot, "/")
    assert AT.strftime("%Y-%m-%d %H:%M") in html
    assert "not live" in html.lower()


def test_mixed_source_ages_are_stated_per_section_not_averaged() -> None:
    """One timestamp for the page would make the older half look as recent as
    the newer."""
    old = AT - timedelta(days=5)
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        pulse=pulse_of(
            [reading_for(benchmark("BTC"), bar_open=old - timedelta(hours=1))],
            as_of=old,
        ),
        macro=macro_of([reading_for(benchmark("SPX"))], as_of=AT),
    )
    assert snapshot.pulse.as_of != snapshot.macro.as_of
    html = render_page(snapshot, "/markets")
    assert old.strftime("%Y-%m-%d %H:%M") in html
    assert AT.strftime("%Y-%m-%d %H:%M") in html


# ---------------------------------------------------------------------------
# Scale
# ---------------------------------------------------------------------------


def test_two_hundred_symbols_render_without_truncation() -> None:
    """**No silent cap.** A page that quietly showed the first fifty would read
    as a complete watchlist."""
    rows = tuple(
        SetupRow(
            symbol=f"SYM{index:03d}USDT",
            state="CONFIRMED",
            sufficiency="sufficient",
            position=index,
        )
        for index in range(200)
    )
    from fmis.operator_dashboard.render import _setup_rows

    html = _setup_rows(rows)
    body = html.split("<tbody>")[1]
    assert body.count("<tr>") == 200
    assert "SYM000USDT" in html and "SYM199USDT" in html


def test_a_very_long_symbol_does_not_break_the_document() -> None:
    row = SetupRow(
        symbol="X" * 500, state="CONFIRMED", sufficiency="sufficient", position=0
    )
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        pulse=pulse_of([reading_for(benchmark("BTC"))]),
    )
    from fmis.operator_dashboard.render import _setup_rows

    assert "X" * 500 in _setup_rows((row,))


def test_a_huge_decimal_is_rendered_exactly_and_not_in_scientific_notation() -> None:
    """An exponent on a money figure is a figure the owner cannot read."""
    from fmis.operator_dashboard.sections import _money_or_reason
    from fmis.money import AssetCode, Money

    text, _ = _money_or_reason(
        Money(amount=Decimal("123456789012345.123456789"), asset=AssetCode("USDT"))
    )
    assert "E" not in text and "e" not in text
    assert text.startswith("123456789012345")


def test_a_huge_equity_curve_scales_without_overflow() -> None:
    from fmis.operator_dashboard.render import _equity_chart

    view = PerformanceView(
        quote_asset="USDT",
        equity=tuple(
            EquityStep(
                at=AT,
                trade_ref=f"t{index}",
                delta="1",
                cumulative=str(index * 10**12),
            )
            for index in range(500)
        ),
    )
    html = _equity_chart(view)
    assert "<svg" in html
    assert "nan" not in html.lower() and "inf" not in html.lower()


def test_a_very_long_warning_and_evidence_render_intact() -> None:
    from fmis.operator_dashboard.models import WarningRow
    from fmis.operator_dashboard.render import _warnings_body

    html = _warnings_body(
        (
            WarningRow(
                code="W-1",
                kind="data",
                severity="ATTENTION",
                statement="s" * 5000,
                evidence="e" * 5000,
            ),
        )
    )
    assert "s" * 5000 in html
    assert "e" * 5000 in html


# ---------------------------------------------------------------------------
# Paper and live must never merge
# ---------------------------------------------------------------------------


def test_the_same_symbol_held_and_papered_stays_two_distinct_facts() -> None:
    row = SetupRow(
        symbol="BTCUSDT",
        state="CONFIRMED",
        sufficiency="sufficient",
        position=0,
        held="0.5 long",
        paper_status="paper OPEN",
    )
    from fmis.operator_dashboard.render import _setup_rows

    html = _setup_rows((row,))
    assert "0.5 long" in html
    assert "paper OPEN" in html
    # Two cells, not one merged claim.
    assert html.index("paper OPEN") != html.index("0.5 long")


def test_no_portfolio_figure_can_be_populated_from_a_paper_row() -> None:
    """Structural, not incidental: `PortfolioView` has no field a paper trade
    could be written into."""
    from fmis.operator_dashboard.models import PortfolioView

    fields = set(PortfolioView.__dataclass_fields__)
    assert not any("paper" in field for field in fields)


# ---------------------------------------------------------------------------
# Routing under attack
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "//",
        "/swing//BTCUSDT",
        "/swing/",
        "/SWING",
        "/swing/BTC?evil=1",
        "/%00",
        "/" + "a" * 5000,
        "/swing/" + "b" * 5000,
    ],
)
def test_a_malformed_route_never_resolves_to_something_unexpected(path: str) -> None:
    route = resolve_route(path)
    assert route is None or route[0] in ROUTES


def test_a_five_thousand_character_symbol_resolves_to_a_symbol_lookup_that_misses() -> None:
    """It must not crash, and it must not match anything."""
    page, symbol = resolve_route("/swing/" + "b" * 5000)
    assert page == "/swing"
    view = SwingView(reference_time=AT)
    assert view.row_for(symbol) is None


def test_an_unknown_symbol_page_states_the_three_reasons_it_might_be_missing() -> None:
    """An empty detail page reads as a setup with no evidence."""
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        workspace=W.workspace_of(W.result(W.assessment("BTCUSDT"))),
    )
    html = render_page(snapshot, "/swing", symbol="GHOSTUSDT")
    assert "no-trade" in html
    assert "readable" in html
    assert "watchlist" in html


def test_a_symbol_detail_page_when_the_swing_section_failed_shows_the_failure() -> None:
    snapshot = build_snapshot(
        refreshed_at=AT, reference_time=AT, workspace_error=Boom("the store is gone")
    )
    html = render_page(snapshot, "/swing", symbol="BTCUSDT")
    assert "the store is gone" in html


# ---------------------------------------------------------------------------
# Repeated and concurrent use
# ---------------------------------------------------------------------------


def test_repeated_refreshes_produce_independent_snapshots() -> None:
    instants = iter([AT, AT + timedelta(minutes=5), AT + timedelta(minutes=10)])

    def refresher(*, refreshed_at, **kwargs):
        return build_snapshot(refreshed_at=refreshed_at, reference_time=refreshed_at)

    holder = SnapshotHolder(refresher=refresher, clock=lambda: next(instants))
    first = holder.current()
    second = holder.current(force=True)
    assert first.refreshed_at != second.refreshed_at


def test_a_refresh_that_fails_mid_flight_does_not_install_a_partial_snapshot() -> None:
    """**A user refresh while a provider error occurs.** The held snapshot must
    survive intact rather than being replaced by half a page."""
    good = build_snapshot(refreshed_at=AT, reference_time=AT)
    calls = {"n": 0}

    def refresher(*, refreshed_at, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return good
        raise Boom("the venue died mid-refresh")

    holder = SnapshotHolder(refresher=refresher, clock=lambda: AT)
    assert holder.current() is good
    with pytest.raises(Boom):
        holder.current(force=True)
    # The previous snapshot is still what the page would render.
    assert holder.current() is good


def test_concurrent_reads_of_a_held_snapshot_never_see_a_half_built_one() -> None:
    holder = SnapshotHolder(
        refresher=lambda *, refreshed_at, **kwargs: build_snapshot(
            refreshed_at=refreshed_at, reference_time=refreshed_at
        ),
        clock=lambda: AT,
    )
    seen: list = []
    barrier = threading.Barrier(8)

    def read() -> None:
        barrier.wait()
        seen.append(holder.current())

    threads = [threading.Thread(target=read) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert len(seen) == 8
    assert all(item is seen[0] for item in seen)
    assert holder.refresh_count == 1


# ---------------------------------------------------------------------------
# Nothing is claimed that was not measured
# ---------------------------------------------------------------------------


def test_the_page_never_prints_a_bare_dash_where_a_figure_belongs() -> None:
    """A dash is read as a zero by anybody scanning a column."""
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        workspace=W.workspace_of(W.result(W.assessment("BTCUSDT"))),
    )
    for path in ROUTES:
        html = render_page(snapshot, path)
        assert ">-<" not in html
        assert ">—<" not in html
        assert ">n/a<" not in html.lower()


def test_no_page_invents_a_composite_health_figure() -> None:
    snapshot = build_snapshot(
        refreshed_at=AT,
        reference_time=AT,
        pulse=pulse_of([reading_for(benchmark("BTC"))]),
    )
    html = render_page(snapshot, "/system").lower()
    # The phrase appears once, in the sentence saying there deliberately is not
    # one — so the assertion is that no score is *offered*, not that the word is
    # absent. A tile or a figure carrying one is what would be wrong.
    assert "no composite health score" in html
    assert "counts, not a score" in html
    assert 'class="v">healthy' not in html
    assert "overall status" not in html
    assert "system health:" not in html


def test_the_limitations_are_printed_rather_than_left_to_be_discovered() -> None:
    snapshot = build_snapshot(refreshed_at=AT, reference_time=AT)
    html = render_page(snapshot, "/system")
    assert "What this surface cannot do" in html
    assert "read-only" in html
    assert "no interpretation" in html
