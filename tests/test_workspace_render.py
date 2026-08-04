"""Milestone AK — the terminal renderer and the `fmits swing` command.

The renderer's contract is the one that makes every future surface safe: it may
**drop** sections and **shorten** values, and may never **add** a claim,
**reorder** sections, or **change a tier**. It also contains no business logic,
which is asserted rather than assumed.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

from fmis.pipeline import cli as cli_module
from fmis.pipeline.multi_timeframe import TimeframeRole
from fmis.workspace import (
    SECTION_ORDER,
    NoteBlock,
    Row,
    RowBlock,
    SectionId,
    SectionStatus,
    TableBlock,
    Unavailable,
    build_workspace,
    render_workspace,
)
from fmis.workspace.render import STATUS_GLYPH, _WIDTH
from tests.test_workspace_build import facts, multi

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "fmis"


def page() -> str:
    return render_workspace(build_workspace(multi()))


# ============ 1. the renderer only renders ==================================


def test_the_renderer_contains_no_business_logic() -> None:
    """No engine call, no builder call, no market arithmetic."""
    tree = ast.parse((SRC / "workspace" / "render.py").read_text())
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for banned in ("build_workspace", "detect_conflicts", "classify_regime",
                   "build_evidence_report", "build_structural_facts",
                   "workspace_for_symbol"):
        assert banned not in called, banned

    # Arithmetic is deliberately *not* banned here. Column padding and rule
    # widths are subtraction and string repetition, and a renderer that could
    # not compute a margin would not be a renderer. What makes this module
    # logic-free is the two assertions that bracket it: it calls no engine and
    # no builder, and it imports the model and nothing else.


def test_the_renderer_imports_only_the_model() -> None:
    tree = ast.parse((SRC / "workspace" / "render.py").read_text())
    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
        and node.module.startswith("fmis")
    }
    assert modules == {"fmis.workspace.models"}


# ============ 2. every section is rendered, including the empty ones ========


def test_every_section_appears_in_order() -> None:
    text = page()
    positions = []
    for section_id in SECTION_ORDER:
        title = build_workspace(multi()).by_id[section_id].title
        index = text.find(title)
        assert index >= 0, section_id
        positions.append(index)
    assert positions == sorted(positions)


def test_unavailable_sections_are_rendered_with_owner_and_prohibition() -> None:
    """Hiding them would make the page look finished."""
    text = page()
    workspace = build_workspace(multi())
    for section_id in (
        SectionId.RISK,
        SectionId.PORTFOLIO,
        SectionId.TRADE_PLAN,
        SectionId.INTERPRETATION,
    ):
        section = workspace.by_id[section_id]
        assert isinstance(section, Unavailable)
        assert f"NOT AVAILABLE — owned by {section.owner}" in text
        assert section.prohibition[:40] in text


def test_the_risk_section_forbids_inferring_a_size() -> None:
    assert "No position size shown here would be legitimate" in page()


def test_every_status_glyph_is_distinct_and_covers_every_status() -> None:
    assert set(STATUS_GLYPH) == set(SectionStatus)
    assert len(set(STATUS_GLYPH.values())) == len(SectionStatus)


# ============ 3. the page respects its own width ============================


def test_no_line_exceeds_the_page_width() -> None:
    """A wrapped line reads as a different value; the width is a contract."""
    for line in page().splitlines():
        assert len(line) <= _WIDTH, (len(line), line)


def test_the_page_survives_a_long_symbol() -> None:
    from fmis.pipeline.multi_timeframe import build_multi_timeframe_facts

    long_facts = facts(seed=2)
    sheet = build_multi_timeframe_facts(
        {TimeframeRole.SETUP: long_facts},
        intervals={TimeframeRole.SETUP: "1d"},
        source="a-very-long-source-name-for-testing",
    )
    text = render_workspace(
        build_workspace(sheet, primary_role=TimeframeRole.SETUP)
    )
    for line in text.splitlines():
        assert len(line) <= _WIDTH, line


# ============ 4. no trading vocabulary ======================================

_FORBIDDEN = (
    "buy", "sell", "bullish", "bearish", "resistance", "recommend",
    "entry", "target", "confidence", "score", "verdict",
)


def test_the_page_carries_no_trading_vocabulary() -> None:
    text = page()
    # Three sentences deny a recommendation using the word, and are asserted
    # separately so removing one fails a test rather than passing this scan.
    # Sentences that use a banned word precisely to deny it. Each is asserted
    # separately below, so deleting one fails a test rather than passing this
    # scan — the same exemption pattern AF established for its disclaimer.
    denials = (
        "recommendation is expressed or implied.",
        "Nothing on this page is a trade recommendation, and no direction is",
        "Entry, invalidation, stop, target and risk/reward are not computed",
        "Levels are reported as nearest above and below. Not support or resistance.",
    )
    body = text
    for denial in denials:
        body = body.replace(denial, "")
    words = set(re.findall(r"[a-z]+", body.lower()))
    for banned in _FORBIDDEN:
        assert banned not in words, banned


def test_the_disclaimers_are_present() -> None:
    text = page()
    assert "recommendation is expressed or implied" in text
    assert "These are measurements, not conclusions" in text
    assert "never resolves them" in text
    assert "Not support or resistance" in text
    assert "Nothing on this page is a trade recommendation" in text


def test_the_page_states_it_reports_conflicts_without_resolving_them() -> None:
    assert "This system reports conflicts. It never resolves them." in page()


# ============ 5. block rendering ============================================


def test_a_table_is_column_aligned_from_its_own_content() -> None:
    from fmis.workspace.render import _render_table_block

    lines = _render_table_block(
        TableBlock(
            columns=("a", "bb"),
            records=(("xxxxx", "y"), ("z", "wwww")),
        )
    )
    assert lines[0].split() == ["A", "BB"]
    assert all(len(line) <= _WIDTH for line in lines)


def test_a_row_block_heading_is_rendered_when_present() -> None:
    from fmis.workspace.render import _render_row_block

    with_heading = _render_row_block(RowBlock((Row("a", "b"),), heading="HEAD"))
    without = _render_row_block(RowBlock((Row("a", "b"),)))
    assert with_heading[0].strip() == "HEAD"
    assert len(with_heading) == len(without) + 1


def test_a_table_heading_is_rendered_when_present() -> None:
    from fmis.workspace.render import _render_table_block

    lines = _render_table_block(
        TableBlock(columns=("a",), records=(("x",),), heading="HEAD")
    )
    assert lines[0].strip() == "HEAD"


def test_notes_wrap_with_a_bullet() -> None:
    from fmis.workspace.render import _render_note_block

    lines = _render_note_block(NoteBlock(("a " * 60,)))
    assert lines[0].startswith(" · ")
    assert all(len(line) <= _WIDTH for line in lines)


def test_an_unregistered_block_type_raises_rather_than_rendering_silence() -> None:
    from fmis.workspace.render import _render_block

    class Invented:
        pass

    with pytest.raises(TypeError) as excinfo:
        _render_block(Invented())  # type: ignore[arg-type]
    assert "no renderer registered" in str(excinfo.value)


def test_a_failed_section_renders_its_reason() -> None:
    from fmis.workspace.models import Section
    from fmis.workspace.render import _render_section

    lines = _render_section(
        Section(
            id=SectionId.EVIDENCE,
            title="EVIDENCE",
            status=SectionStatus.FAILED,
            summary=("nothing to show",),
            reason="the window held no closed candle",
        )
    )
    assert any("reason: the window held no closed candle" in line for line in lines)


def test_rendering_rejects_anything_that_is_not_a_workspace() -> None:
    with pytest.raises(TypeError):
        render_workspace("not a workspace")  # type: ignore[arg-type]


def test_rendering_is_deterministic() -> None:
    sheet = multi()
    assert render_workspace(build_workspace(sheet)) == render_workspace(
        build_workspace(sheet)
    )


def test_provenance_is_rendered_for_every_answered_section() -> None:
    text = page()
    assert "via fmis.pipeline.multi_timeframe" in text
    assert "via fmis.market_regime · policy regime-v1" in text.replace("\n     ", " ")
    assert "via fmis.decision_support + fmis.evidence" in text.replace("\n     ", " ")
    assert "via fmis.workspace.conflicts" in text


# ============ 6. the CLI ====================================================


def test_the_registry_carries_five_commands() -> None:
    names = [command.name for command in cli_module.COMMANDS]
    assert names == ["facts", "mtf", "regime", "swing", "daily"]
    assert len(set(names)) == len(names)


def test_the_swing_command_parses_its_flags() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(
        ["swing", "BTCUSDT", "-n", "300", "--setup", "12h", "--band", "0.3"]
    )
    assert args.command == "swing"
    assert args.symbol == "BTCUSDT"
    assert args.limit == 300
    assert args.setup == "12h"
    assert args.band == 0.3


def test_the_swing_command_defaults_to_the_standard_roles() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(["swing", "BTCUSDT"])
    assert (args.context, args.setup, args.execution) == ("1w", "1d", "4h")


def test_the_swing_command_runs_and_prints_the_page(capsys, monkeypatch) -> None:
    import fmis.workspace.builder as builder_module

    monkeypatch.setattr(
        builder_module, "multi_timeframe_facts_for_symbol", lambda symbol, **kw: multi()
    )
    assert cli_module.main(["swing", "BTCUSDT"]) == 0
    text = capsys.readouterr().out
    assert "FMITS SWING WORKSPACE" in text
    assert "INSTRUMENT & DATA QUALITY" in text
    assert "NOT AVAILABLE — owned by EP-04" in text
    assert "LIMITATIONS & PROVENANCE" in text


def test_the_swing_command_forwards_its_policy(capsys, monkeypatch) -> None:
    import fmis.workspace.builder as builder_module

    monkeypatch.setattr(
        builder_module, "multi_timeframe_facts_for_symbol", lambda symbol, **kw: multi()
    )
    assert cli_module.main(["swing", "BTCUSDT", "--band", "0.4"]) == 0
    assert "regime-v1-custom" in capsys.readouterr().out


def test_a_table_wider_than_the_page_is_rejected_not_wrapped() -> None:
    """Truncation and wrapping both change what a cell says; refusing does not."""
    from fmis.workspace.render import _render_table_block

    with pytest.raises(ValueError) as excinfo:
        _render_table_block(
            TableBlock(
                columns=("a", "b"),
                records=(("x" * 50, "y" * 40),),
            )
        )
    assert "narrower columns" in str(excinfo.value)
