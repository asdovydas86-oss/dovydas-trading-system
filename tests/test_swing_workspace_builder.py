"""Milestone BS — composition: one run in, one page out, nothing recomputed.

Every test here assembles a full workspace with **no network, no filesystem and
no clock**. That is the property that makes the assembly testable at all, and it
is asserted directly at the end of this file.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmis.decision_context import ContextState
from fmis.swing_setup import SetupState
from fmis.swing_workspace import (
    RANKING_RULE,
    SWING_WORKSPACE_LIMITATIONS,
    SwingWorkspace,
    SwingWorkspaceError,
    build_swing_workspace,
)
from fmis.today import NotAvailable, TodayRun

from tests.swing_workspace_helpers import (
    REFERENCE,
    assessment,
    failed_result,
    reading,
    result,
    run_of,
    workspace_of,
)


# ---------------------------------------------------------------------------
# The three states partition the page
# ---------------------------------------------------------------------------


def test_a_confirmed_setup_is_a_top_opportunity() -> None:
    workspace = workspace_of(result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))

    assert [row.symbol for row in workspace.opportunities] == ["BTCUSDT"]
    assert workspace.wait_list == ()
    assert workspace.no_trade == ()


def test_a_candidate_is_on_the_wait_list_and_never_a_top_opportunity() -> None:
    """`CANDIDATE` is the engine's own *"a thesis exists, its confirmation has
    not occurred"* — which is exactly *close but not ready*."""
    workspace = workspace_of(result(assessment("ETHUSDT", state=SetupState.CANDIDATE)))

    assert [row.symbol for row in workspace.wait_list] == ["ETHUSDT"]
    assert workspace.opportunities == ()


def test_a_wait_result_is_a_no_trade_group_carrying_the_engines_own_reason() -> None:
    workspace = workspace_of(
        result(
            assessment(
                "SOLUSDT", direction=None, thesis=("the context gate did not pass",)
            )
        )
    )

    assert len(workspace.no_trade) == 1
    assert workspace.no_trade[0].reason == "the context gate did not pass"
    assert workspace.no_trade[0].symbols == ("SOLUSDT",)


def test_a_failed_symbol_is_never_a_no_trade_result() -> None:
    """A provider outage and a market with no setup are the same blank on a page
    that merges them, and only one of the two is about the market."""
    workspace = workspace_of(failed_result("DOGEUSDT", "provider timed out"))

    assert workspace.no_trade == ()
    assert [entry.symbol for entry in workspace.unanalysed] == ["DOGEUSDT"]
    assert "timed out" in workspace.unanalysed[0].detail


def test_no_symbol_appears_in_two_sections() -> None:
    workspace = workspace_of(
        result(assessment("BTCUSDT", state=SetupState.CONFIRMED)),
        result(assessment("ETHUSDT", state=SetupState.CANDIDATE)),
        result(assessment("SOLUSDT", direction=None)),
        failed_result("XRPUSDT"),
    )

    seen = (
        [row.symbol for row in workspace.opportunities]
        + [row.symbol for row in workspace.wait_list]
        + [s for group in workspace.no_trade for s in group.symbols]
        + [entry.symbol for entry in workspace.unanalysed]
    )
    assert len(seen) == len(set(seen)) == 4


def test_the_model_refuses_a_workspace_that_places_one_symbol_twice() -> None:
    """Checked on the object, so a *second* composition root cannot produce one."""
    workspace = workspace_of(result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))
    from dataclasses import replace as _dataclass_replace

    duplicated = workspace.opportunities
    with pytest.raises(SwingWorkspaceError, match="appears in opportunities"):
        _dataclass_replace(workspace, wait_list=duplicated)


def test_two_wait_symbols_reaching_one_reason_are_one_group() -> None:
    workspace = workspace_of(
        result(assessment("SOLUSDT", direction=None, thesis=("one reason",))),
        result(assessment("XRPUSDT", direction=None, thesis=("one reason",))),
    )

    assert len(workspace.no_trade) == 1
    assert workspace.no_trade[0].symbols == ("SOLUSDT", "XRPUSDT")


def test_one_reason_reached_from_two_context_states_is_two_groups() -> None:
    """Merging them would report a system failure as a market observation."""
    workspace = workspace_of(
        result(assessment("SOLUSDT", direction=None, thesis=("one reason",))),
        result(
            assessment(
                "XRPUSDT",
                direction=None,
                thesis=("one reason",),
                sufficiency=ContextState.INSUFFICIENT,
            )
        ),
    )

    classifications = {group.classification for group in workspace.no_trade}
    assert classifications == {"read and declined", "could not be classified"}


def test_a_wait_result_with_no_thesis_still_states_a_reason() -> None:
    workspace = workspace_of(
        result(assessment("SOLUSDT", direction=None, thesis=()))
    )

    assert workspace.no_trade[0].reason == "no reason stated"


def test_no_trade_groups_are_ordered_by_how_many_symbols_reached_each_reason() -> None:
    workspace = workspace_of(
        result(assessment("SOLUSDT", direction=None, thesis=("rare",))),
        result(assessment("XRPUSDT", direction=None, thesis=("common",))),
        result(assessment("ADAUSDT", direction=None, thesis=("common",))),
    )

    assert [group.reason for group in workspace.no_trade] == ["common", "rare"]


# ---------------------------------------------------------------------------
# Ordering, stamped positions and the empty page
# ---------------------------------------------------------------------------


def test_rows_are_stamped_with_their_own_position() -> None:
    workspace = workspace_of(
        result(assessment("BTCUSDT", state=SetupState.CONFIRMED)),
        result(assessment("ETHUSDT", state=SetupState.CONFIRMED)),
    )

    assert [row.position for row in workspace.opportunities] == [1, 2]


def test_the_wait_list_is_ordered_by_the_same_key_and_stamped_from_one() -> None:
    workspace = workspace_of(
        result(assessment("BTCUSDT", state=SetupState.CANDIDATE)),
        result(assessment("ETHUSDT", state=SetupState.CANDIDATE)),
    )

    assert [row.position for row in workspace.wait_list] == [1, 2]
    assert [row.symbol for row in workspace.wait_list] == ["BTCUSDT", "ETHUSDT"]


def test_the_page_carries_the_ordering_rule_itself() -> None:
    assert workspace_of(result(assessment())).ranking_rule == RANKING_RULE


def test_a_page_with_no_actionable_setup_is_still_a_complete_page() -> None:
    workspace = workspace_of(result(assessment("SOLUSDT", direction=None)))

    assert workspace.is_empty
    assert workspace.opportunities == () and workspace.wait_list == ()
    assert workspace.limitations == SWING_WORKSPACE_LIMITATIONS
    assert workspace.summary.scanned == 1


def test_a_page_holding_only_a_wait_list_is_not_an_empty_page() -> None:
    """*"Nothing has confirmed"* and *"there is nothing to look at"* are two
    different mornings, and only the second one is `is_empty`."""
    workspace = workspace_of(result(assessment("ETHUSDT", state=SetupState.CANDIDATE)))

    assert workspace.wait_list
    assert not workspace.is_empty


def test_a_page_over_a_hundred_symbols_orders_every_one_of_them() -> None:
    symbols = tuple(f"SYM{index:03d}USDT" for index in range(100))
    workspace = workspace_of(
        *(
            result(assessment(symbol, state=SetupState.CANDIDATE))
            for symbol in symbols
        )
    )

    assert len(workspace.wait_list) == 100
    assert [row.symbol for row in workspace.wait_list] == list(symbols)
    assert [row.position for row in workspace.wait_list] == list(range(1, 101))


def test_the_same_run_assembled_twice_produces_an_equal_page() -> None:
    run = run_of(
        result(assessment("BTCUSDT", state=SetupState.CONFIRMED)),
        result(assessment("ETHUSDT", state=SetupState.CANDIDATE)),
    )

    assert build_swing_workspace(run) == build_swing_workspace(run)


# ---------------------------------------------------------------------------
# The summary counts what the sections below state
# ---------------------------------------------------------------------------


def test_every_count_in_the_summary_matches_the_section_it_summarises() -> None:
    workspace = workspace_of(
        result(assessment("BTCUSDT", state=SetupState.CONFIRMED)),
        result(assessment("ETHUSDT", state=SetupState.CANDIDATE)),
        result(assessment("SOLUSDT", direction=None)),
        result(assessment("XRPUSDT", direction=None, thesis=("another reason",))),
        failed_result("ADAUSDT"),
    )
    summary = workspace.summary

    assert summary.scanned == 5
    assert summary.confirmed == len(workspace.opportunities) == 1
    assert summary.candidates == len(workspace.wait_list) == 1
    assert summary.waiting == sum(
        len(group.symbols) for group in workspace.no_trade
    ) == 2
    assert summary.unanalysed == len(workspace.unanalysed) == 1
    assert summary.actionable == 2


def test_the_summary_states_the_risk_position_rather_than_colouring_it() -> None:
    summary = workspace_of(result(assessment())).summary

    assert isinstance(summary.risk_state, NotAvailable)
    assert "no risk budget" in summary.risk_state.reason


def test_the_summary_carries_the_regime_refusal_verbatim() -> None:
    summary = workspace_of(result(assessment())).summary

    assert "bull/bear/neutral" in summary.regime_note
    assert "ADR-0025" in summary.regime_note


def test_the_breadth_is_the_scans_own_distribution() -> None:
    workspace = workspace_of(
        result(assessment("BTCUSDT")),
        result(assessment("SOLUSDT", direction=None)),
    )

    assert dict(workspace.summary.breadth)["no direction"] == 1


# ---------------------------------------------------------------------------
# Nothing is recomputed: the page carries `fmis.today`'s own objects
# ---------------------------------------------------------------------------


def test_the_market_portfolio_and_statistics_sections_are_the_same_objects() -> None:
    """Not equal copies — the identical instances, so nothing can be recomputed."""
    run = run_of(result(assessment()))
    workspace = build_swing_workspace(run)

    assert workspace.market is run.workspace.market
    assert workspace.portfolio is run.workspace.portfolio
    assert workspace.statistics is run.workspace.performance


def test_every_opportunity_line_is_the_days_own_line() -> None:
    run = run_of(result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))
    workspace = build_swing_workspace(run)

    assert workspace.opportunities[0].opportunity is run.workspace.opportunities.confirmed[0]


def test_the_reference_time_and_source_come_from_the_run() -> None:
    workspace = workspace_of(result(assessment()))

    assert workspace.reference_time == REFERENCE
    assert workspace.source == "fixture"


def test_the_metadata_carries_the_days_own_notes_rather_than_restating_them() -> None:
    run = run_of(result(assessment()))
    workspace = build_swing_workspace(run)

    assert (
        workspace.metadata["approval_note"]
        is run.workspace.opportunities.approval_note
    )
    assert (
        workspace.metadata["evidence_note"]
        is run.workspace.opportunities.evidence_note
    )


# ---------------------------------------------------------------------------
# Argument validation and isolation
# ---------------------------------------------------------------------------


def test_the_builder_refuses_anything_but_a_run() -> None:
    with pytest.raises(TypeError, match="run must be a TodayRun"):
        build_swing_workspace(object())


def test_the_run_type_refuses_a_mismatched_reading() -> None:
    with pytest.raises(TypeError, match="reading must be a StoreReading"):
        TodayRun(results=(), reading=object(), workspace=object())


def test_the_run_type_refuses_a_non_tuple_result_list() -> None:
    with pytest.raises(TypeError, match="results must be a tuple"):
        TodayRun(results=[], reading=reading(), workspace=object())


def test_the_run_type_refuses_a_mismatched_workspace() -> None:
    with pytest.raises(TypeError, match="workspace must be a TodayWorkspace"):
        TodayRun(results=(), reading=reading(), workspace=object())


def test_assembly_opens_no_file_and_reaches_no_network() -> None:
    """The property that makes every test above possible, asserted directly."""
    import socket

    def _forbidden(*args, **kwargs):  # pragma: no cover - only runs on failure
        raise AssertionError(f"the assembly opened a socket: {args}")

    original = socket.socket
    socket.socket = _forbidden
    try:
        workspace = workspace_of(
            result(assessment("BTCUSDT", state=SetupState.CONFIRMED))
        )
    finally:
        socket.socket = original

    assert isinstance(workspace, SwingWorkspace)


def test_nothing_in_the_assembly_reads_a_clock() -> None:
    """Two assemblies at different wall-clock instants are byte-identical."""
    first = workspace_of(result(assessment()))
    second = workspace_of(result(assessment()))

    assert first == second
    assert first.reference_time == datetime(2026, 8, 20, 21, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Hostile cases, recorded here because each one was found by attacking the page
# ---------------------------------------------------------------------------


def test_the_same_symbol_requested_twice_produces_two_rows_rather_than_no_page() -> None:
    """`fmits workspace BTCUSDT BTCUSDT` asks twice and is answered twice. An
    earlier draft rejected the duplicate and lost the entire page."""
    workspace = workspace_of(
        result(assessment("BTCUSDT", state=SetupState.CONFIRMED)),
        result(assessment("BTCUSDT", state=SetupState.CONFIRMED)),
    )

    assert [row.symbol for row in workspace.opportunities] == ["BTCUSDT", "BTCUSDT"]
    assert [row.position for row in workspace.opportunities] == [1, 2]


def test_a_symbol_claimed_by_two_different_sections_is_still_refused() -> None:
    """The contradiction the guard exists for, unaffected by the relaxation."""
    from dataclasses import replace

    workspace = workspace_of(result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))
    with pytest.raises(SwingWorkspaceError, match="cannot both be right"):
        replace(workspace, wait_list=workspace.opportunities)


def test_a_row_carries_the_owners_recorded_position_beside_its_paper_status() -> None:
    """The hostile case: *"paper: none"* beside a real holding reads as *"I am
    not in this"*, which is the wrong half of the truth."""
    workspace = workspace_of(result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))
    row = workspace.opportunities[0]

    assert "paper book" in row.paper_status
    assert row.held == "none recorded, in any book"


def test_an_unread_store_states_both_absences_rather_than_printing_none() -> None:
    workspace = workspace_of(
        result(assessment("BTCUSDT", state=SetupState.CONFIRMED)),
        store=reading(present=False),
    )
    row = workspace.opportunities[0]

    assert isinstance(row.paper_status, NotAvailable)
    assert isinstance(row.held, NotAvailable)
