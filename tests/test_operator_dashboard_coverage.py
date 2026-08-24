"""The branches the other files' fixtures never reach.

Co-movement, cross-asset relationships, populated books and limits, paper
positions, and the failure paths. Each uses the **real** domain object it maps —
a `PaperPosition`, a `BookExposure`, a `CoMovement` — inside a minimal stand-in
for the container, because the mapping functions take the container by duck
type and building a whole workspace to reach one field is fixture cost with no
assertion value.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from operator_dashboard_helpers import AT, Boom, benchmark, dark, pulse_of, reading_for

from fmis.macro import CrossAssetRelationship
from fmis.market_pulse import (
    Benchmark,
    CoMovement,
    MarketCategory,
    MarketPulse,
    MarketUnavailable,
    MarketUniverse,
    TradingSchedule,
)
from fmis.operator_dashboard import (
    PAGES,
    SourceState,
    build_snapshot,
    page_titles,
    paper_view,
    portfolio_view,
    pulse_view,
    render_page,
)
from fmis.operator_dashboard.models import DashboardSectionStatus
from fmis.operator_dashboard.sections import _text_or_reason, _unavailable_state
from fmis.swing_workspace import BookExposure, PaperPosition
from fmis.today import LimitLine, NotAvailable, PortfolioOverview


def _absent(reason: str) -> NotAvailable:
    return NotAvailable(
        reason=reason, owned_by="fixture", forbidden_inference="do not read as zero"
    )


# ---------------------------------------------------------------------------
# Freshness with no policy
# ---------------------------------------------------------------------------


def test_a_series_with_no_publication_schedule_gets_no_verdict_on_its_age() -> None:
    """**The age is still stated; only the verdict is not.** A build that
    invented a bound for a series whose cadence it does not know would be
    inventing exactly the threshold the pulse refuses to choose."""
    subject = Benchmark(
        benchmark_id="NOPOLICY",
        display_name="A series with no declared cadence",
        category=MarketCategory.CRYPTO,
        schedule=TradingSchedule.CONTINUOUS,
        quote_unit="USDT",
        instrument=benchmark("X").instrument,
    )
    view = pulse_view(pulse_of([reading_for(subject)]))
    assert view.rows[0].state is SourceState.SCHEDULE_UNKNOWN
    assert view.rows[0].age is not None


def test_the_engine_makes_an_unsupported_failure_unconstructible() -> None:
    """**Why `_unavailable_state` has no second branch.** The two facts are kept
    apart one layer down: a `MarketUnavailable` refuses a benchmark with no
    provider, so an unsupported market can never arrive through that tuple. A
    defensive branch here would be one that can never be taken."""
    with pytest.raises(ValueError, match="unsupported, which is a different fact"):
        MarketUnavailable(benchmark=dark("DXY"), reason="never asked for")


def test_a_delivered_failure_is_always_unavailable_and_never_unsupported() -> None:
    entry = MarketUnavailable(
        benchmark=benchmark("SOL"), reason="the venue returned 503"
    )
    assert _unavailable_state(entry) is SourceState.UNAVAILABLE


# ---------------------------------------------------------------------------
# Co-movement
# ---------------------------------------------------------------------------


def _pulse_with_co_movement():
    btc = benchmark("BTC")
    eth = benchmark("ETH")
    sol = benchmark("SOL")
    readings = [reading_for(btc), reading_for(eth), reading_for(sol)]
    return MarketPulse(
        as_of=AT,
        universe=MarketUniverse(name="test", benchmarks=(btc, eth, sol)),
        readings=tuple(readings),
        unavailable=(),
        rankings=(),
        horizons=(),
        co_movements=(
            CoMovement(
                subject_id="ETH",
                reference_id="BTC",
                value=0.8049,
                unavailable_reason=None,
                metric="Pearson correlation of bar returns",
                observation_count=168,
                window_start=AT,
                window_end=AT,
            ),
            CoMovement(
                subject_id="SOL",
                reference_id="BTC",
                value=None,
                unavailable_reason="too few aligned observations",
                metric="Pearson correlation of bar returns",
                observation_count=3,
            ),
        ),
        co_movement_reference="BTC",
    )


def test_a_co_movement_crosses_with_its_reference_and_its_absence_reason() -> None:
    view = pulse_view(_pulse_with_co_movement())
    rows = {row.benchmark_id: row for row in view.rows}
    assert rows["ETH"].co_movement == 0.8049
    assert rows["ETH"].co_movement_reference == "BTC"
    assert rows["SOL"].co_movement is None
    assert rows["SOL"].co_movement_reason == "too few aligned observations"


def test_the_co_movement_section_renders_with_the_named_reference() -> None:
    html = render_page(
        build_snapshot(
            refreshed_at=AT, reference_time=AT, pulse=_pulse_with_co_movement()
        ),
        "/markets",
    )
    assert "co-movement against BTC" in html
    assert "0.8049" in html
    assert "too few aligned observations" in html


# ---------------------------------------------------------------------------
# Cross-asset relationships
# ---------------------------------------------------------------------------


def _macro_with_relationships():
    subject = benchmark("SPX")
    return SimpleNamespace(
        as_of=AT,
        universe=MarketUniverse(name="macro", benchmarks=(subject,)),
        levels=(),
        readings=(reading_for(subject),),
        unavailable=(),
        rate_facts=(),
        horizons=(),
        relationship_reference="BTC",
        relationships=(
            CrossAssetRelationship(
                subject_id="SPX",
                reference_id="BTC",
                metric="Pearson correlation",
                value=0.31,
                unavailable_reason=None,
                # `observation_count` is the window used; `aligned_count` is
                # how many dates the two series share. The engine refuses a
                # window larger than the overlap it was drawn from.
                observation_count=62,
                aligned_count=90,
                # A measured value must name the window it was measured over —
                # "a number over an unnamed window is a number nobody can
                # reconstruct".
                window_start=AT,
                window_end=AT,
            ),
            CrossAssetRelationship(
                subject_id="VIX",
                reference_id="BTC",
                metric="Pearson correlation",
                value=None,
                unavailable_reason="the two series share no aligned observations",
                observation_count=0,
                aligned_count=0,
            ),
        ),
    )


def test_a_relationship_carries_the_alignment_it_required() -> None:
    """**A correlation measured over 62 of the 90 dates two series share is a
    different claim from one over all 90,** and a page showing only the number
    hides that."""
    from fmis.operator_dashboard import macro_view

    view = macro_view(_macro_with_relationships())
    assert view.relationships[0].aligned_count == 90
    assert view.relationships[0].observation_count == 62


def test_the_relationships_section_renders_both_counts() -> None:
    html = render_page(
        build_snapshot(
            refreshed_at=AT, reference_time=AT, macro=_macro_with_relationships()
        ),
        "/markets",
    )
    assert "90 / 62" in html
    assert "cross-asset relationships against BTC" in html
    assert "different claims" in html
    assert "the two series share no aligned observations" in html


# ---------------------------------------------------------------------------
# Books, limits and paper
# ---------------------------------------------------------------------------


def _workspace_with_books():
    overview = PortfolioOverview(
        store_root="/tmp/store",
        store_present=True,
        open_positions=(),
        limits=(
            LimitLine(
                limit_id="open-risk",
                scope="account:main",
                stated_limit="2%",
                severity="BLOCKING",
                current="1.4%",
                status="within",
            ),
            LimitLine(
                limit_id="concentration",
                scope="book:live",
                stated_limit="25%",
                severity="ATTENTION",
                current=_absent("no mark was read, so exposure is not stateable"),
                status=_absent("no current value, so no status"),
            ),
        ),
        budget_note="the budget was read from the recorded snapshot",
        committed_risk="1.4%",
        available_risk="0.6%",
        cash="10000",
        exposure="4200",
    )
    return SimpleNamespace(
        portfolio=overview,
        books=(
            BookExposure(label="live", open_positions=2, market_value="4200"),
            BookExposure(
                label="paper",
                open_positions=1,
                market_value=_absent("no mark was read for this book"),
            ),
        ),
    )


def test_a_populated_book_and_limit_cross_with_their_absences_intact() -> None:
    view = portfolio_view(_workspace_with_books())
    assert [book.label for book in view.books] == ["live", "paper"]
    assert view.books[0].market_value == "4200"
    assert view.books[1].market_value is None
    assert view.books[1].market_value_reason == "no mark was read for this book"

    assert view.limits[1].current is None
    assert view.limits[1].current_reason.startswith("no mark was read")
    assert view.limits[1].status is None


def test_the_portfolio_page_renders_books_limits_and_notes() -> None:
    from fmis.operator_dashboard.render import _portfolio_body

    html = _portfolio_body(portfolio_view(_workspace_with_books()))
    assert "books" in html
    assert "risk limits" in html
    assert "open-risk" in html
    assert "the budget was read from the recorded snapshot" in html
    assert "no mark was read for this book" in html


def test_a_book_labelled_paper_still_carries_no_paper_trade_metric() -> None:
    """A *book* named paper is a recorded book. It is not the simulator, and
    the portfolio view holds none of the simulator's fields."""
    view = portfolio_view(_workspace_with_books())
    assert not any(hasattr(book, "total_r") for book in view.books)


def _workspace_with_paper():
    return SimpleNamespace(
        paper=(
            PaperPosition(
                activation_id="act-1",
                market="BTCUSDT",
                state="OPEN",
                open_size="0.5",
                bars_in_trade=12,
                stop_widenings=1,
                entry="100",
                initial_risk="50",
                total_r="2",
                max_favourable_r="3",
                max_adverse_r="-0.5",
                stop="95",
                initial_stop="90",
            ),
            PaperPosition(
                activation_id="act-2",
                market="ETHUSDT",
                state="PENDING",
                open_size="0",
                bars_in_trade=0,
                stop_widenings=0,
                entry=_absent("the activation has not filled"),
                initial_risk=_absent("no entry, so no risk"),
                total_r=_absent("no entry, so no R"),
                max_favourable_r=_absent("no entry, so no excursion"),
                max_adverse_r=_absent("no entry, so no excursion"),
                stop="0",
                initial_stop="0",
            ),
        ),
        paper_note="two activations were read",
    )


def test_a_paper_position_crosses_field_for_field_with_its_absences() -> None:
    view = paper_view(_workspace_with_paper())
    assert view.note == "two activations were read"
    assert view.rows[0].total_r == "2"
    assert view.rows[0].max_adverse_r == "-0.5"
    assert view.rows[1].total_r is None
    assert view.rows[1].total_r_reason == "no entry, so no R"
    assert view.rows[1].entry_reason == "the activation has not filled"


def test_an_unfilled_paper_trade_never_renders_a_zero_r() -> None:
    from fmis.operator_dashboard.render import _paper_body

    html = _paper_body(paper_view(_workspace_with_paper()))
    pending = html[html.index("act-2") :]
    assert "no entry, so no R" in pending


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_a_statistics_failure_becomes_an_unavailable_performance_section() -> None:
    from fmis.statistics import CorpusUnreadableError

    class _Boom:
        def __call__(self, *args, **kwargs):
            raise CorpusUnreadableError("the corpus is not readable")

    from fmis.operator_dashboard import refresh

    snapshot = refresh(
        refreshed_at=AT,
        workspace_runner=lambda *a, **k: None,
        pulse_runner=lambda **k: None,
        macro_runner=lambda **k: None,
        statistics_runner=_Boom(),
    )
    assert snapshot.performance.failed
    assert "CorpusUnreadableError" in snapshot.performance.unavailable_reason


def test_a_watchlist_is_forwarded_to_the_workspace_runner() -> None:
    from fmis.operator_dashboard import refresh

    seen: dict = {}

    def runner(symbols=None, **kwargs):
        seen["symbols"] = symbols
        return None

    refresh(
        refreshed_at=AT,
        symbols=("BTCUSDT", "ETHUSDT"),
        workspace_runner=runner,
        pulse_runner=lambda **k: None,
        macro_runner=lambda **k: None,
        statistics_runner=lambda *a, **k: None,
    )
    assert seen["symbols"] == ("BTCUSDT", "ETHUSDT")


def test_a_benchmark_subset_is_forwarded_to_the_pulse_runner() -> None:
    from fmis.operator_dashboard import refresh

    seen: dict = {}

    def runner(**kwargs):
        seen["universe"] = kwargs["universe"]
        return None

    refresh(
        refreshed_at=AT,
        benchmarks=("BTC",),
        workspace_runner=lambda *a, **k: None,
        pulse_runner=runner,
        macro_runner=lambda **k: None,
        statistics_runner=lambda *a, **k: None,
    )
    assert [b.benchmark_id for b in seen["universe"].benchmarks] == ["BTC"]


# ---------------------------------------------------------------------------
# Small surfaces
# ---------------------------------------------------------------------------


def test_a_section_status_must_be_the_enum_and_not_its_text() -> None:
    from fmis.operator_dashboard import DashboardError, DashboardSection

    with pytest.raises(DashboardError, match="must be a DashboardSectionStatus"):
        DashboardSection(name="pulse", status="available")


def test_page_titles_matches_the_route_table() -> None:
    assert page_titles() == tuple(title for _, title in PAGES)


def test_an_absence_with_no_reason_still_renders_the_word() -> None:
    """Better a bare *unavailable* than a blank; a blank reads as a zero."""
    from fmis.operator_dashboard.render import _absent

    assert _absent(None) == '<span class="absent">unavailable</span>'
    assert _absent("") == '<span class="absent">unavailable</span>'


def test_a_footnote_with_no_reason_falls_back_to_the_plain_marker() -> None:
    from fmis.operator_dashboard.render import _Footnotes

    notes = _Footnotes()
    assert notes.mark(None) == '<span class="absent">unavailable</span>'
    assert notes.render() == ""


def test_a_none_value_splits_into_two_nones() -> None:
    assert _text_or_reason(None) == (None, None)


def test_an_evidence_digest_that_could_not_be_built_carries_its_reason() -> None:
    """`RankedSetup.evidence` is a digest **or** a stated absence, and the
    absence is what a symbol whose evidence projection failed carries."""
    from fmis.operator_dashboard.sections import _evidence_view

    view, reason = _evidence_view(
        _absent("the evidence projection could not be built for this symbol")
    )
    assert view is None
    assert reason == "the evidence projection could not be built for this symbol"


def test_the_evidence_splitter_is_total_like_its_siblings() -> None:
    """`None` in, two `None`s out — the same shape every `_or_reason` helper
    holds, so a caller never has to special-case one of them."""
    from fmis.operator_dashboard.sections import _evidence_view

    assert _evidence_view(None) == (None, None)


def test_excluded_equity_steps_are_listed_rather_than_dropped() -> None:
    """**No silent truncation.** A curve that quietly omitted trades would read
    as a complete one."""
    from fmis.operator_dashboard.models import EquityStep, PerformanceView
    from fmis.operator_dashboard.render import _performance_body

    view = PerformanceView(
        quote_asset="USDT",
        equity=(
            EquityStep(at=AT, trade_ref="t1", delta="10", cumulative="10"),
            EquityStep(at=AT, trade_ref="t2", delta="5", cumulative="15"),
        ),
        equity_excluded=("act-9: no closing price was recorded",),
    )
    html = _performance_body((view,))
    assert "excluded from the curve" in html
    assert "act-9: no closing price was recorded" in html


def test_an_empty_section_name_falls_back_to_a_generic_message() -> None:
    from fmis.operator_dashboard.render import _empty_message

    assert _empty_message("unknown-section") == "Nothing was read for this section."


def test_an_empty_request_path_resolves_to_the_overview() -> None:
    from fmis.operator_dashboard import resolve_route

    assert resolve_route("") == ("/", None)
    assert resolve_route("/") == ("/", None)


def test_a_setup_with_no_evidence_shows_the_reason_not_an_empty_panel() -> None:
    """An empty evidence panel reads as *no evidence supports this*, which is a
    different claim from *no digest could be produced*."""
    from fmis.operator_dashboard.models import SetupRow
    from fmis.operator_dashboard.render import _swing_detail

    html = _swing_detail(
        SetupRow(
            symbol="BTCUSDT",
            state="CONFIRMED",
            sufficiency="sufficient",
            position=0,
            evidence=None,
            evidence_reason="the evidence projection could not be built",
        )
    )
    assert "the evidence projection could not be built" in html


def test_a_swing_view_with_no_ranking_rule_omits_the_ordering_note() -> None:
    from fmis.operator_dashboard.models import SwingView
    from fmis.operator_dashboard.render import _swing_body

    assert "Ordering:" not in _swing_body(SwingView(reference_time=AT))


def test_a_performance_view_with_no_steps_lists_no_step_table() -> None:
    from fmis.operator_dashboard.models import PerformanceView
    from fmis.operator_dashboard.render import _performance_body

    html = _performance_body((PerformanceView(quote_asset="USDT"),))
    assert "every closed-trade step" not in html


def test_the_server_logs_requests_when_it_is_not_quiet(capsys) -> None:
    """`quiet=True` is what the CLI passes; the other branch must still work."""
    import threading
    from http.client import HTTPConnection

    from fmis.operator_dashboard import SnapshotHolder, build_server

    holder = SnapshotHolder(
        refresher=lambda *, refreshed_at, **kwargs: build_snapshot(
            refreshed_at=refreshed_at, reference_time=refreshed_at
        ),
        clock=lambda: AT,
    )
    server, _ = build_server(port=0, holder=holder, quiet=False)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        host, port = server.server_address[:2]
        connection = HTTPConnection(host, port, timeout=10)
        connection.request("GET", "/")
        assert connection.getresponse().status == 200
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert "GET /" in capsys.readouterr().err


def test_serve_returns_cleanly_on_a_keyboard_interrupt() -> None:
    """Ctrl-C is how the owner stops it, and it must not print a traceback."""
    from fmis.operator_dashboard import serve

    class _Interrupting:
        def serve_forever(self, *args, **kwargs):
            raise KeyboardInterrupt

        def shutdown(self):
            self.shut = True

        def server_close(self):
            self.closed = True

        server_address = ("127.0.0.1", 1234)

    fake = _Interrupting()
    import fmis.operator_dashboard.server as module

    original = module.build_server
    module.build_server = lambda **kwargs: (fake, None)
    try:
        serve(port=0, quiet=True)
    finally:
        module.build_server = original
    assert fake.shut and fake.closed
