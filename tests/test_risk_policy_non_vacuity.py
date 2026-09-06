"""Proof that this milestone connected something that was genuinely unreachable.

**Product First requires connection, not more unused code.** The audit that
opened Slice 4 found ~8,000 lines of correct, tested risk and sizing
implementation with no product consumer, and found the precise reason: the chain
had no first link. This file pins that finding so it cannot silently come back.

The claim, stated exactly:

    Before this milestone, `RiskBudget` and `RiskLimit` were constructed
    **nowhere in `src/`** — only in tests. `per_trade_ceiling` was therefore
    never consulted with a real budget, `SizingPolicy.fraction_for` never
    resolved, and no surface could reach any of it.

Two of the tests below would have failed before this milestone and pass now;
the rest assert the properties that make the connection honest rather than
merely present.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from risk_policy_helpers import assessment, declaration

import fmis
from fmis.risk import RiskBudget
from fmis.risk_policy import PlanningStatus, budget_from, plan_for

SOURCE_ROOT = pathlib.Path(fmis.__file__).resolve().parent


def _constructions_of(name: str) -> dict[str, int]:
    """Every `name(...)` call in `src/fmis`, by module path."""
    found: dict[str, int] = {}
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        count = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        )
        if count:
            found[str(path.relative_to(SOURCE_ROOT))] = count
    return found


# ---------------------------------------------------------------------------
# The break the audit found, and where it is now closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["RiskBudget", "RiskLimit"])
def test_the_only_producer_in_the_source_tree_is_the_risk_policy_package(
    name: str,
) -> None:
    """**This is the milestone, in one assertion.**

    Before Slice 4 this returned `{}` — the type existed, was persisted, was
    versioned and was evaluated against, and nothing in `src/` ever built one.
    It now returns exactly one module, and if a second appears it is a second
    place the specification's ceiling could be spelled differently.
    """
    assert _constructions_of(name) == {"risk_policy/planning.py": 1}


def test_a_risk_budget_can_now_be_produced_from_a_declaration_alone() -> None:
    """No store, no account, no recorded fill, no network. Before this
    milestone there was no call anywhere that returned one of these."""
    budget = budget_from(declaration())
    assert isinstance(budget, RiskBudget)
    assert budget.limits


def test_a_deterministic_size_is_now_reachable_without_a_portfolio() -> None:
    """The capability the product did not have: the whole sizing chain, from a
    declared capital figure and an assessment, with nothing else configured."""
    plan = plan_for(assessment(), declaration=declaration())
    assert plan.status is PlanningStatus.PLANNED
    assert plan.quantity.text == "0.025"


# ---------------------------------------------------------------------------
# The connection is a real one: the arithmetic is the existing engine's
# ---------------------------------------------------------------------------


def test_the_size_is_produced_by_the_existing_engine_not_by_a_second_one() -> None:
    """The point of connecting rather than rebuilding. If `PositionSizer.size`
    stops being called, this fails — which is what stops a future change from
    quietly growing a parallel implementation in the projection layer."""
    import fmis.risk_policy.planning as planning

    calls: list[str] = []
    original = planning.PositionSizer.size

    def _spy(self, proposal, **kwargs):  # type: ignore[no-untyped-def]
        calls.append("size")
        return original(self, proposal, **kwargs)

    planning.PositionSizer.size = _spy  # type: ignore[method-assign]
    try:
        plan_for(assessment(), declaration=declaration())
    finally:
        planning.PositionSizer.size = original  # type: ignore[method-assign]
    assert calls == ["size"]


def test_sizing_is_done_in_isolation_and_states_that_it_was() -> None:
    """`remaining_open_risk=None` means *"no portfolio was read"*, which is a
    different fact from `Absent` — *"a portfolio was read and could not be
    measured"*. Passing `Absent` would claim a portfolio had been consulted."""
    import fmis.risk_policy.planning as planning

    seen: dict[str, object] = {}
    original = planning.PositionSizer.size

    def _spy(self, proposal, **kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)
        return original(self, proposal, **kwargs)

    planning.PositionSizer.size = _spy  # type: ignore[method-assign]
    try:
        plan_for(assessment(), declaration=declaration())
    finally:
        planning.PositionSizer.size = original  # type: ignore[method-assign]
    assert seen["remaining_open_risk"] is None


# ---------------------------------------------------------------------------
# The product surface actually consumes it
# ---------------------------------------------------------------------------


def test_the_dashboard_symbol_page_renders_the_figures() -> None:
    """*"A unit test can call `RiskBudget`"* is not product value. This asserts
    the deterministic result reaches the page the owner actually opens."""
    from datetime import UTC, datetime

    from fmis.operator_dashboard.models import SymbolDecisionRow
    from fmis.operator_dashboard.render import _decision_detail
    from fmis.operator_dashboard.sections import _trade_plan_row

    plan = plan_for(assessment(), declaration=declaration())
    row = SymbolDecisionRow(
        symbol="BTCUSDT",
        state="candidate",
        classification="read and declined",
        reason="r",
        sufficiency="sufficient",
        as_of=datetime(2026, 9, 6, tzinfo=UTC),
        plan=_trade_plan_row(plan),
    )
    page = _decision_detail(row, "note")
    assert "risk and trade planning" in page
    assert "0.025 BTC" in page
    assert "50 USDT" in page
    assert "0.02" in page


def test_the_dashboard_page_without_a_declaration_shows_no_figure_at_all() -> None:
    """The other half of the proof: with nothing declared the page states the
    absence rather than rendering a zero, and no number appears."""
    from datetime import UTC, datetime

    from fmis.operator_dashboard.models import SymbolDecisionRow
    from fmis.operator_dashboard.render import _decision_detail

    row = SymbolDecisionRow(
        symbol="BTCUSDT",
        state="candidate",
        classification="read and declined",
        reason="r",
        sufficiency="sufficient",
        as_of=datetime(2026, 9, 6, tzinfo=UTC),
        plan=None,
    )
    page = _decision_detail(row, "no risk policy is declared")
    assert "risk and trade planning" in page
    assert "no risk policy is declared" in page
    assert "0.025" not in page
