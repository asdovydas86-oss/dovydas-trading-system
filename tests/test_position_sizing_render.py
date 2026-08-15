"""Rendering an approval as a page a reader cannot misread.

Three properties are asserted here and they are the whole point of the module:
the **status always prints what it does not mean**, the **three registers are
three sections with three counts**, and **an absent figure prints its reason
where the figure would have been** — a blank where a size belongs reads as a size
of nothing.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from decimal import Decimal

import pytest
from portfolio_risk_helpers import line, state, usdt
from position_sizing_helpers import (
    budget_with,
    ceiling,
    engine,
    evaluate,
    proposal,
    total_risk_limit,
)
from trade_domain_helpers import USDT

from fmis.money import Money
from fmis.position_sizing import (
    APPROVAL_LIMITATIONS,
    STATUS_MEANING,
    ApprovalStatus,
    render_approval,
)
from fmis.provenance import Absent

WIDTH = 78


def page(**kwargs: object) -> str:
    return render_approval(evaluate(**kwargs))  # type: ignore[arg-type]


# ==========================================================================
# 1. Shape
# ==========================================================================


def test_the_page_holds_every_section_the_brief_asks_for() -> None:
    text = page()
    for heading in (
        "TRADE APPROVAL",
        "STATUS",
        "SIZE",
        "GEOMETRY",
        "OPEN RISK",
        "BLOCKING REASONS",
        "WARNINGS",
        "INDETERMINATE",
        "SCOPE",
        "LIMITATIONS",
    ):
        assert heading in text, heading


def test_no_line_exceeds_the_page_width() -> None:
    """A terminal cuts an overflowing line at a position the window decides."""
    for text in (
        page(),
        page(candidate=proposal(stop=Decimal("61000"))),
        page(portfolio=state(line(mark=Absent("no mark was supplied")))),
    ):
        assert [row for row in text.splitlines() if len(row) > WIDTH] == []


def test_the_page_ends_with_a_blank_line_like_every_other_surface() -> None:
    assert page().endswith("\n")


def test_rendering_refuses_anything_that_is_not_a_result() -> None:
    with pytest.raises(TypeError, match="ApprovalResult"):
        render_approval("approved")  # type: ignore[arg-type]


# ==========================================================================
# 2. The status, and what it does not mean
# ==========================================================================


def test_every_status_has_a_sentence_saying_what_it_is_not() -> None:
    assert set(STATUS_MEANING) == set(ApprovalStatus)
    assert "not about the idea" in STATUS_MEANING[ApprovalStatus.APPROVED]
    assert "cannot prevent the owner" in STATUS_MEANING[ApprovalStatus.BLOCKED]
    assert "not a milder approval" in STATUS_MEANING[ApprovalStatus.INDETERMINATE]


def test_the_status_and_its_meaning_are_both_on_the_page() -> None:
    result = evaluate()
    text = render_approval(result)
    assert f"STATUS · {result.status.value.upper()}" in text
    assert STATUS_MEANING[result.status].split(".")[0][:40] in text


# ==========================================================================
# 3. Figures, and the reasons that stand in for them
# ==========================================================================


def test_a_produced_size_prints_with_every_figure_derived_from_it() -> None:
    text = page(
        budget=budget_with(ceiling("0.02"), total_risk_limit(Money(Decimal("6000"), USDT))),
        portfolio=state(line(), equity=usdt("100000")),
    )
    assert "recommended size" in text
    assert "0.625 BTC" in text
    assert "money at risk" in text
    assert "1000 USDT" in text
    assert "planned R multiple" in text
    assert "2.5" in text


def test_an_absent_figure_prints_its_reason_where_the_figure_would_have_been() -> None:
    text = page(candidate=proposal(stop=Decimal("61000")))
    assert "unavailable — " in text
    assert "no risk distance" in text


def test_open_risk_is_printed_before_and_after() -> None:
    text = page()
    assert "before this trade" in text
    assert "after this trade" in text


def test_the_risk_basis_is_printed_beside_the_risk_figures() -> None:
    assert "pre-cost and pre-funding" in page()


def test_a_candidate_with_no_target_says_so_rather_than_printing_nothing() -> None:
    assert "none stated" in page(candidate=proposal(targets=()))


def test_the_caps_that_reduced_a_size_are_printed() -> None:
    text = render_approval(
        evaluate(approval_engine=engine(risk_fraction=Decimal("0.05")))
    )
    assert "cap: " in text
    assert "reduced to the per-trade ceiling" in text


# ==========================================================================
# 4. The three registers stay three registers
# ==========================================================================


def test_each_register_prints_its_own_count() -> None:
    result = evaluate()
    text = render_approval(result)
    assert f"BLOCKING REASONS ({len(result.blocking)})" in text
    assert f"WARNINGS ({len(result.warnings)})" in text
    assert f"INDETERMINATE ({len(result.indeterminate)})" in text


def test_an_empty_register_says_so_rather_than_leaving_a_blank() -> None:
    """A heading with nothing under it reads as *'none found'* only if it says so."""
    text = page()
    assert "no hard limit the owner set is breached" in text


def test_a_blocked_result_prints_the_blocking_reason_and_its_source() -> None:
    text = page(candidate=proposal(stop=Decimal("61000")))
    assert "[TR-STOP]" in text
    assert "source: fmis.portfolio_risk.stop_distance" in text


def test_an_indeterminate_result_prints_under_its_own_heading() -> None:
    text = page(portfolio=state(line(mark=Absent("no mark was supplied"))))
    assert "[TR-MARKS]" in text


def test_the_scope_summary_counts_both_evaluations_separately() -> None:
    text = page()
    assert "portfolio: " in text
    assert "trade: " in text


# ==========================================================================
# 5. Limitations
# ==========================================================================


def test_every_limitation_is_printed_at_the_foot_of_the_page() -> None:
    text = page()
    for code, _ in APPROVAL_LIMITATIONS:
        assert f"{code} · " in text


def test_the_limitations_state_what_this_engine_never_does() -> None:
    joined = " ".join(statement for _, statement in APPROVAL_LIMITATIONS)
    assert "never executes" in joined
    assert "Nothing is stored" in joined
    assert "Round DOWN" in joined
    assert "Correlation between markets is never measured" in joined
    assert "No probability is calibrated" in joined


# ==========================================================================
# 6. The renderer computes nothing
# ==========================================================================


def test_the_renderer_constructs_no_money_and_sums_nothing() -> None:
    """A figure cannot appear on this page that no engine can be held to."""
    source = pathlib.Path(inspect.getfile(render_approval)).read_text(encoding="utf-8")
    called = {
        node.func.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not called & {"Money", "Quantity", "sum", "sum_money", "Decimal"}


def test_the_renderer_names_no_side_of_its_own() -> None:
    """ADR-0028's boundary: the direction is read off the enum at runtime."""
    source = pathlib.Path(inspect.getfile(render_approval)).read_text(encoding="utf-8")
    banned = {"long", "short", "buy", "sell", "bullish", "bearish"}
    tokens: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            tokens.add(node.value.lower())
        elif isinstance(node, ast.Attribute):
            tokens.add(node.attr.lower())
        elif isinstance(node, ast.Name):
            tokens.add(node.id.lower())
    assert not tokens & banned


def test_a_direction_still_reaches_the_page_because_it_is_read_at_runtime() -> None:
    assert "· long ·" in page()
