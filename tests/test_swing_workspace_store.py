"""Milestone BS — the page over a store that actually holds something.

Everything here runs against a **real** durable store, built through the
product's own commands: a recorded plan, an activation, a simulation over real
bars, and therefore a real position, a real `TradeMonitor` and real statistics.
The claim these tests check is the one the milestone rests on — that every figure
on the page is the figure the engine below produced, not a second calculation
that happens to agree.

The `assemble_today` seam is checked here too: `fmits today` must be unchanged
by the arrival of a second consumer above it.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fmis.accounts import AccountId, Book
from fmis.money import AssetCode, Quantity
from fmis.paper import (
    PAPER_DUST_POLICY,
    ActivateRequest,
    activate_trade,
    run_simulation,
)
from fmis.persistence import TradingStore
from fmis.snapshotting import TradeDirection
from fmis.swing_setup import SetupState
from fmis.swing_workspace import (
    build_swing_workspace,
    render_swing_workspace,
)
from fmis.today import (
    DUST_POLICY,
    NotAvailable,
    TodayRun,
    build_today,
    read_store,
    render_today,
)
from fmis.trade_capture import PlanRequest, record_plan
from fmis.trade_lifecycle import EntryType

from paper_helpers import MARKET, START, at, bar
from tests.swing_workspace_helpers import assessment, result


@pytest.fixture()
def populated(tmp_path: Path):
    """A store holding one simulated trade that has filled and part-exited."""
    root = tmp_path / "store"
    store = TradingStore(root, dust=PAPER_DUST_POLICY)
    plan = record_plan(
        store,
        PlanRequest(
            market=MARKET,
            book=Book.PAPER,
            direction=TradeDirection.LONG,
            stop=Decimal("95"),
            targets=(Decimal("110"), Decimal("120")),
            committed_at=START,
            written_at=START,
            author="owner",
            confidence="medium",
            code_version="test",
        ),
    ).view.plan
    activate_trade(
        store,
        ActivateRequest(
            plan_id=plan.plan_id,
            account=AccountId("paper"),
            quantity=Quantity(Decimal("1"), AssetCode("BTC")),
            entry_type=EntryType.STOP_ENTRY,
            entry_price=Decimal("100"),
            interval="1h",
            activated_at=START,
            written_at=START,
            code_version="test",
            fractions=(Decimal("0.5"), Decimal("0.5")),
        ),
    )
    run_simulation(
        store,
        ran_at=at(8),
        code_version="test",
        interval="1h",
        bars_by_symbol={
            "BTCUSDT": (
                bar(0, "99", "101", "98", "100"),
                bar(1, "100", "112", "99", "111"),
            )
        },
    )
    return root


def _run(root: Path, *results) -> TodayRun:
    reading = read_store(root, at=at(8), archive_root=root / "archive")
    return TodayRun(
        results=tuple(results),
        reading=reading,
        workspace=build_today(
            results, reading, reference_time=at(8), source=f"offline · store {root}"
        ),
    )


# ---------------------------------------------------------------------------
# The paper section
# ---------------------------------------------------------------------------


def test_the_paper_section_shows_the_trade_with_the_simulators_own_figures(
    populated,
) -> None:
    run = _run(populated, result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))
    workspace = build_swing_workspace(run)

    assert len(workspace.paper) == 1
    position = workspace.paper[0]
    monitor = run.reading.paper_trades[0].monitor

    assert position.market == "BTCUSDT"
    assert position.bars_in_trade == monitor.bars_in_trade
    assert position.stop == str(monitor.effective_stop)
    assert position.initial_stop == str(monitor.initial_stop)


def test_the_seven_figures_the_brief_names_are_all_on_the_page(populated) -> None:
    text = render_swing_workspace(
        build_swing_workspace(_run(populated, result(assessment("BTCUSDT"))))
    )

    assert "ACTIVE PAPER TRADES" in text
    for label in ("entry", "risk", "R ", "MFE", "MAE", "bars", "stop"):
        assert label in text


def test_a_setup_on_a_market_already_running_says_so_on_its_row(populated) -> None:
    """The question a page showing setups and a paper book separately cannot
    answer: *am I already in this?*"""
    run = _run(populated, result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))
    workspace = build_swing_workspace(run)
    row = workspace.opportunities[0]

    assert not isinstance(row.paper_status, NotAvailable)
    assert workspace.paper[0].activation_id in row.paper_status


def test_the_summary_counts_the_running_trade(populated) -> None:
    workspace = build_swing_workspace(_run(populated, result(assessment("BTCUSDT"))))

    assert workspace.summary.paper_positions == 1


# ---------------------------------------------------------------------------
# Books, positions and statistics
# ---------------------------------------------------------------------------


def test_a_finished_paper_trade_is_not_counted_as_a_running_one(populated) -> None:
    """The header counts what is still running; a resolved trade is history."""
    from dataclasses import replace

    from fmis.swing_workspace import global_summary

    run = _run(populated, result(assessment("BTCUSDT")))
    workspace = build_swing_workspace(run)
    finished = tuple(replace(row, state="resolved") for row in workspace.paper)

    assert workspace.summary.paper_positions == 1
    assert (
        global_summary(
            market=run.workspace.market,
            confirmed=0,
            candidates=0,
            waiting=0,
            unanalysed=0,
            portfolio=run.workspace.portfolio,
            paper=finished,
            store_read=True,
        ).paper_positions
        == 0
    )


def test_the_paper_book_is_shown_separately_from_every_other(populated) -> None:
    workspace = build_swing_workspace(_run(populated, result(assessment("BTCUSDT"))))

    assert [book.label for book in workspace.books] == ["paper"]
    assert workspace.books[0].open_positions == workspace.portfolio.open_count


def test_the_statistics_section_is_the_days_own_report(populated) -> None:
    run = _run(populated, result(assessment("BTCUSDT")))
    workspace = build_swing_workspace(run)

    assert workspace.statistics is run.workspace.performance
    assert workspace.statistics.trades >= 1


def test_the_whole_page_renders_and_fits(populated) -> None:
    text = render_swing_workspace(
        build_swing_workspace(
            _run(
                populated,
                result(assessment("BTCUSDT", state=SetupState.CONFIRMED)),
                result(assessment("ETHUSDT", state=SetupState.CANDIDATE)),
                result(assessment("SOLUSDT", direction=None)),
            )
        )
    )

    for line in text.splitlines():
        assert len(line) <= 78, line
    assert "STATISTICS SNAPSHOT" in text
    assert "PORTFOLIO SUMMARY" in text
    assert "books" in text


def test_the_simulators_warnings_reach_the_pages_warning_section(populated) -> None:
    run = _run(populated, result(assessment("BTCUSDT")))
    workspace = build_swing_workspace(run)

    expected = {
        warning.code
        for view in run.reading.paper_trades
        for warning in view.warnings
    }
    assert expected <= {warning.code for warning in workspace.warnings}


# ---------------------------------------------------------------------------
# The `assemble_today` seam: `fmits today` is unchanged
# ---------------------------------------------------------------------------


def test_the_seam_returns_the_page_run_today_would_have_returned(populated) -> None:
    """`run_today` is now one line over `assemble_today`; the page must be equal."""
    from fmis.today import assemble_today

    calls: list[tuple] = []

    def _scan(symbols, **options):
        calls.append(tuple(symbols))
        return (result(assessment("BTCUSDT")),)

    import fmis.today.builder as builder

    original = builder.run_market_scan
    builder.run_market_scan = _scan
    try:
        run = assemble_today(
            ["BTCUSDT"],
            reference_time=at(8),
            store_root=populated,
            archive_root=populated / "archive",
        )
        page = builder.run_today(
            ["BTCUSDT"],
            reference_time=at(8),
            store_root=populated,
            archive_root=populated / "archive",
        )
    finally:
        builder.run_market_scan = original

    assert render_today(run.workspace) == render_today(page)
    assert calls == [("BTCUSDT",), ("BTCUSDT",)]


def test_the_seam_hands_back_the_inputs_the_page_was_built_from(populated) -> None:
    run = _run(populated, result(assessment("BTCUSDT")))

    assert run.results[0].assessment is not None
    assert run.reading.present is True
    assert run.workspace.market.scanned == 1


def test_the_seam_returns_the_very_results_the_scan_produced(monkeypatch, populated) -> None:
    """`TodayRun.results` must be the scan, not an empty tuple that renders as a
    page with no no-trade section and no per-row evidence. A mutant emptying it
    left every existing assertion green, because the page inside the run was
    still built from the real results."""
    import fmis.today.builder as builder
    from fmis.today import assemble_today

    scanned = (
        result(assessment("BTCUSDT", state=SetupState.CONFIRMED)),
        result(assessment("SOLUSDT", direction=None, thesis=("the gate did not pass",))),
    )
    monkeypatch.setattr(builder, "run_market_scan", lambda *a, **k: scanned)
    run = assemble_today(
        ["BTCUSDT", "SOLUSDT"], reference_time=at(8), store_root=populated,
        archive_root=populated / "archive", read_marks=False,
    )

    assert run.results == scanned
    # ...and the workspace built from it therefore still has its no-trade group
    assert build_swing_workspace(run).no_trade[0].symbols == ("SOLUSDT",)


def test_the_seam_returns_the_very_reading_the_page_was_assembled_from(
    monkeypatch, populated
) -> None:
    """`TodayRun.reading` must be the reading `build_today` saw. A mutant
    substituting an empty one left the day's page correct while every figure the
    workspace derives from the reading — paper trades, books, whether the store
    was read at all — silently became an absence."""
    import fmis.today.builder as builder
    from fmis.today import assemble_today

    monkeypatch.setattr(
        builder, "run_market_scan", lambda *a, **k: (result(assessment("BTCUSDT")),)
    )
    run = assemble_today(
        ["BTCUSDT"], reference_time=at(8), store_root=populated,
        archive_root=populated / "archive", read_marks=False,
    )

    assert run.reading.present is True
    assert run.reading.paper_trades, "the reading must carry the store's paper trades"
    assert run.reading.root == str(populated)
    # the page and the reading agree about how many positions exist
    assert run.workspace.portfolio.open_count == len(run.reading.positions)
    assert build_swing_workspace(run).paper


def test_the_workspace_scans_once_rather_than_twice(monkeypatch, populated) -> None:
    """The whole reason the seam exists: a second scan would be sixty fetches."""
    import fmis.today.builder as builder
    from fmis.swing_workspace import run_swing_workspace

    calls: list[tuple] = []

    def _scan(symbols, **options):
        calls.append(tuple(symbols))
        return (result(assessment("BTCUSDT")),)

    monkeypatch.setattr(builder, "run_market_scan", _scan)
    workspace = run_swing_workspace(
        ["BTCUSDT"],
        reference_time=at(8),
        store_root=populated,
        archive_root=populated / "archive",
        read_marks=False,
    )

    assert calls == [("BTCUSDT",)]
    assert workspace.summary.scanned == 1


def test_the_dust_policy_the_page_folded_under_is_recorded(populated) -> None:
    workspace = build_swing_workspace(_run(populated, result(assessment("BTCUSDT"))))

    assert workspace.metadata["dust_policy"] == DUST_POLICY.policy_id
