"""Milestone BS — the page itself.

Three properties are asserted over and over here, because each of them is a way
the page could quietly mislead: every line fits the terminal, every absence is
printed with what it forbids, and the ordering key is on the row it placed.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from fmis.swing_setup import SetupState
from fmis.swing_workspace import (
    EXCLUDED_FROM_RANKING,
    WORKSPACE_PAGE_WIDTH,
    SwingWorkspaceError,
    render_swing_workspace,
)

from tests.swing_workspace_helpers import (
    assessment,
    failed_result,
    reading,
    result,
    workspace_of,
)


def page(*results, **options) -> str:
    return render_swing_workspace(workspace_of(*results, **options))


FULL = (
    result(assessment("BTCUSDT", state=SetupState.CONFIRMED)),
    result(assessment("ETHUSDT", state=SetupState.CANDIDATE)),
    result(assessment("SOLUSDT", direction=None, thesis=("the gate did not pass",))),
    failed_result("DOGEUSDT", "BinanceError: 451"),
)


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_every_required_section_is_present_in_the_briefs_own_order() -> None:
    text = page(*FULL)
    headings = [
        "GLOBAL MARKET SUMMARY",
        "TOP OPPORTUNITIES",
        "WAIT LIST",
        "NO TRADE",
        "ACTIVE PAPER TRADES",
        "PORTFOLIO SUMMARY",
        "STATISTICS SNAPSHOT",
        "WARNINGS",
    ]
    positions = [text.index(heading) for heading in headings]

    assert positions == sorted(positions)


def test_every_line_fits_the_page() -> None:
    for line in page(*FULL).splitlines():
        assert len(line) <= WORKSPACE_PAGE_WIDTH, line


def test_a_long_symbol_and_a_long_store_path_still_fit() -> None:
    text = page(
        result(assessment("X" * 60 + "USDT", state=SetupState.CONFIRMED)),
        store=reading(root="/" + "d" * 200),
    )

    for line in text.splitlines():
        assert len(line) <= WORKSPACE_PAGE_WIDTH, line


def test_the_width_contract_raises_rather_than_printing_an_overflow() -> None:
    from fmis.swing_workspace.render import _require_fits

    assert _require_fits(["x" * WORKSPACE_PAGE_WIDTH]) is None
    with pytest.raises(SwingWorkspaceError, match="exceeds the"):
        _require_fits(["x" * (WORKSPACE_PAGE_WIDTH + 1)])


def test_the_page_uses_no_colour_and_no_unicode_box_drawing() -> None:
    text = page(*FULL)

    assert "\x1b[" not in text
    for forbidden in "─│┌┐└┘━┃":
        assert forbidden not in text


def test_the_page_renders_from_a_workspace_and_refuses_anything_else() -> None:
    with pytest.raises(TypeError, match="must be a SwingWorkspace"):
        render_swing_workspace({"opportunities": []})


def test_rendering_is_deterministic() -> None:
    assert page(*FULL) == page(*FULL)


# ---------------------------------------------------------------------------
# The ordering is visible on the page
# ---------------------------------------------------------------------------


def test_each_ranked_row_prints_its_own_key() -> None:
    text = page(*FULL)

    assert "rank key" in text
    assert "readiness=confirmed(0)" in text
    assert "readiness=candidate(1)" in text
    # Both positions, because a watchlist component that printed `#1` on every
    # row would be a component carrying no information — and one mutant that
    # dropped the watchlist entirely produced exactly that.
    assert "watchlist=#1(0)" in text
    assert "watchlist=#2(1)" in text


def test_the_ordering_rule_and_the_exclusions_are_printed() -> None:
    text = page(*FULL)

    assert "HOW THIS PAGE IS ORDERED" in text
    assert "not desirability" in text
    for excluded in EXCLUDED_FROM_RANKING:
        assert excluded in text


def test_a_wrapped_rank_key_does_not_repeat_its_label() -> None:
    """A label printed twice reads as two values — the exact defect this page
    exists to prevent, found by reading the first rendered page."""
    text = page(*FULL)

    assert text.count("rank key") == 2


def test_a_wrapped_value_continues_under_the_value_not_at_the_margin() -> None:
    """A continuation flush to column 0 reads as a new top-level line. The width
    contract alone does not catch it — shorter lines always fit — so the column
    is asserted directly."""
    text = page(*FULL)
    lines = text.splitlines()
    index = next(i for i, l in enumerate(lines) if "rank key" in l)
    head, cont = lines[index], lines[index + 1]

    assert cont.startswith(" " * (head.index("readiness")))
    assert cont.strip().startswith("sufficiency=")


def test_the_positions_are_printed_and_start_at_one() -> None:
    text = page(
        result(assessment("BTCUSDT", state=SetupState.CONFIRMED)),
        result(assessment("ETHUSDT", state=SetupState.CONFIRMED)),
    )

    assert "#1  BTCUSDT" in text
    assert "#2  ETHUSDT" in text


# ---------------------------------------------------------------------------
# Absence, and what it forbids
# ---------------------------------------------------------------------------


def test_an_empty_page_says_what_is_absent_rather_than_showing_nothing() -> None:
    text = page(result(assessment("SOLUSDT", direction=None)))

    assert "No setup has confirmed under this policy" in text
    assert "No symbol reached a directional thesis short of confirmation" in text
    assert "No simulated trade is recorded" in text


def test_a_scan_in_which_everything_confirmed_still_prints_the_empty_sections() -> None:
    text = page(result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))

    assert "Every symbol scanned reached a directional thesis" in text


def test_every_absence_prints_its_reason_and_its_forbidden_inference() -> None:
    text = page(*FULL)

    assert "not available" in text
    assert "owned by:" in text
    assert text.count("!") >= 1


def test_a_failed_symbol_is_never_printed_as_a_no_trade_result() -> None:
    text = page(*FULL)
    marker = text.index("could not be read — never a no-trade result")

    assert "DOGEUSDT" in text[marker:]
    assert "BinanceError: 451" in text


def test_the_evidence_caveats_are_printed_once_rather_than_per_row() -> None:
    text = page(*FULL)

    headings = [
        line for line in text.splitlines() if line.strip() == "EVIDENCE INDEPENDENCE"
    ]

    assert len(headings) == 1
    assert text.count("The regime STRUCTURE gate and the context") == 1


def test_a_page_with_no_stated_caveat_prints_no_independence_section() -> None:
    text = page(result(assessment("SOLUSDT", direction=None)))

    assert "EVIDENCE INDEPENDENCE" not in text


def test_the_warnings_section_states_that_silence_is_not_reassurance() -> None:
    from fmis.swing_workspace import render_swing_workspace
    from dataclasses import replace

    workspace = replace(workspace_of(*FULL), warnings=())
    text = render_swing_workspace(workspace)

    assert "not a statement that nothing is wrong" in text


def test_the_limitations_are_printed_at_the_foot_and_name_the_ordering() -> None:
    text = page(*FULL)

    assert "LIMITATIONS" in text
    assert "WS-2:" in text
    assert "WS-3:" in text
    assert text.index("WS-1:") > text.index("WARNINGS")


# ---------------------------------------------------------------------------
# The renderer only renders
# ---------------------------------------------------------------------------


def test_the_renderer_imports_no_engine_and_no_builder() -> None:
    import fmis.swing_workspace.render as module

    source = pathlib.Path(inspect.getfile(module)).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert imported == {
        "__future__",
        "textwrap",
        "types",
        "fmis.swing_workspace.models",
        "fmis.swing_workspace.ranking",
        "fmis.today",
    }


def test_the_renderer_calls_no_section_adapter() -> None:
    import fmis.swing_workspace.render as module
    import fmis.swing_workspace.sections as sections

    source = pathlib.Path(inspect.getfile(module)).read_text(encoding="utf-8")
    called = {
        node.func.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert called & set(sections.__all__) == set()


# ---------------------------------------------------------------------------
# The branches a plain fixture does not reach
# ---------------------------------------------------------------------------


def _with_row(workspace, **overrides):
    """The same page with its first opportunity row altered. Presentation only."""
    from dataclasses import replace

    row = workspace.opportunities[0]
    opportunity = replace(row.opportunity, **overrides)
    return replace(workspace, opportunities=(replace(row, opportunity=opportunity),))


def test_an_approved_row_prints_its_size_its_risk_and_its_objections() -> None:
    from fmis.swing_workspace import render_swing_workspace

    workspace = _with_row(
        workspace_of(result(assessment("BTCUSDT", state=SetupState.CONFIRMED))),
        approval_status="approved",
        recommended_size="0.12 BTC",
        open_risk_after="120.00 USDT",
        blocking_reasons=("the portfolio is at its per-market cap",),
        approval_warnings=("the recorded equity is four days old",),
    )
    text = render_swing_workspace(workspace)

    assert "approval   approved" in text
    assert "size 0.12 BTC" in text
    assert "open risk after entry 120.00 USDT" in text
    assert "BLOCKING: the portfolio is at its per-market cap" in text
    assert "warning: the recorded equity is four days old" in text


def test_a_row_whose_evidence_could_not_be_projected_prints_the_absence() -> None:
    from dataclasses import replace

    from fmis.swing_workspace import render_swing_workspace
    from fmis.today import NotAvailable

    workspace = workspace_of(result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))
    absent = NotAvailable(
        reason="the evidence projection refused this setup",
        owned_by="fmis.setup_evidence",
        forbidden_inference="Do not read this as a setup with no evidence behind it.",
    )
    row = replace(workspace.opportunities[0], evidence=absent)
    text = render_swing_workspace(replace(workspace, opportunities=(row,)))

    assert "evidence   not available" in text
    assert "no evidence behind it" in text
    assert "EVIDENCE INDEPENDENCE" not in text


def test_two_rows_in_one_section_are_separated_by_a_blank_line() -> None:
    text = page(
        result(assessment("BTCUSDT", state=SetupState.CANDIDATE)),
        result(assessment("ETHUSDT", state=SetupState.CANDIDATE)),
    )
    body = text[text.index("WAIT LIST") :]

    assert "\n\n   #2  ETHUSDT" in body


def test_a_page_that_never_read_the_store_says_so_in_the_portfolio_section() -> None:
    text = page(result(assessment("BTCUSDT")), store=reading(present=False))

    assert "this run did not read a durable store" in text


def test_a_warning_carrying_a_measured_figure_prints_its_detail() -> None:
    from dataclasses import replace

    from fmis.swing_workspace import render_swing_workspace
    from fmis.today import WarningClass, WarningSeverity, WorkspaceWarning

    workspace = workspace_of(result(assessment("BTCUSDT")))
    warning = WorkspaceWarning(
        code="X-1",
        kind=WarningClass.CORRELATION,
        severity=WarningSeverity.INFORMATION,
        statement="a stated observation",
        evidence="report 0012 section 9",
        subjects=("BTCUSDT",),
        detail=("n = 44 · the corrected research harness", "the sample is superseded"),
    )
    text = render_swing_workspace(replace(workspace, warnings=(warning,)))

    assert "[NOTE] X-1: a stated observation" in text
    assert "n = 44" in text
    assert "the sample is superseded" in text


def test_an_approved_row_with_no_size_prints_the_status_alone() -> None:
    """An approval can exist with no size — a candidate the engine could measure
    against the limits but not denominate. The row must not invent one."""
    from fmis.swing_workspace import render_swing_workspace

    workspace = _with_row(
        workspace_of(result(assessment("BTCUSDT", state=SetupState.CONFIRMED))),
        approval_status="indeterminate",
        recommended_size=None,
        open_risk_after=None,
    )
    text = render_swing_workspace(workspace)

    row = text[text.index("#1  BTCUSDT") : text.index("WAIT LIST")]

    assert "approval   indeterminate" in row
    assert "size " not in row
    assert "open risk after entry" not in row


def test_two_paper_trades_are_separated_by_a_blank_line() -> None:
    from dataclasses import replace

    from fmis.swing_workspace import PaperPosition, render_swing_workspace

    def _position(activation: str) -> PaperPosition:
        return PaperPosition(
            activation_id=activation,
            market="BTCUSDT",
            state="open",
            open_size="1 BTC",
            bars_in_trade=2,
            stop_widenings=1,
            entry="100",
            initial_risk="10 USDT",
            total_r="0.5",
            max_favourable_r="1.1",
            max_adverse_r="-0.2",
            stop="99",
            initial_stop="95",
        )

    workspace = workspace_of(result(assessment("BTCUSDT")))
    text = render_swing_workspace(
        replace(workspace, paper=(_position("ACT-1"), _position("ACT-2")))
    )
    body = text[text.index("ACTIVE PAPER TRADES") :]

    assert body.count("BTCUSDT  [open]") == 2
    assert "widened 1 time(s)" in text
    assert "\n\n   BTCUSDT  [open]" in body
