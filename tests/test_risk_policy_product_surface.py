"""Slice 4 through the real projection: workspace in, dashboard page out.

Every scenario below runs the production composition — `build_swing_workspace`,
`swing_view`, `_symbol_page` — over hand-built domain objects, with no network,
no store and no clock. The fixture geometry is the helper's own and is fixed:

    entry 100 · stop 90 · target 130   ->  risk per unit = 10

so with declared capital 10,000 USDT at 0.5 %:

    risk amount = 10000 × 0.005 = 50 USDT
    quantity    = 50 ÷ 10       = 5
    notional    = 5 × 100       = 500 USDT

Each of those is hand-calculated and written as a literal.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from risk_policy_helpers import declaration
from swing_workspace_helpers import REFERENCE, assessment, result, run_of

from fmis.operator_dashboard.compose import build_snapshot
from fmis.operator_dashboard.render import render_page
from fmis.operator_dashboard.sections import swing_view
from fmis.swing_setup import SetupState
from fmis.swing_workspace import build_swing_workspace


def _workspace(*results, declared=True, fraction="0.005"):
    return build_swing_workspace(
        run_of(*results),
        risk_declaration=(
            declaration(fraction=fraction) if declared else None
        ),
    )


def _page(*results, declared=True, fraction="0.005", symbol="BTCUSDT"):
    workspace = _workspace(*results, declared=declared, fraction=fraction)
    snapshot = build_snapshot(
        refreshed_at=REFERENCE, reference_time=REFERENCE, workspace=workspace
    )
    return render_page(snapshot, "/swing", symbol=symbol)


def _overview(*results, declared=True, fraction="0.005"):
    """The `/swing` page itself, rather than one symbol's detail."""
    workspace = _workspace(*results, declared=declared, fraction=fraction)
    snapshot = build_snapshot(
        refreshed_at=REFERENCE, reference_time=REFERENCE, workspace=workspace
    )
    return render_page(snapshot, "/swing")


def _risk_panel(page: str) -> str:
    """Just the planning panel, so an assertion about it cannot be satisfied —
    or defeated — by text from another section of the same page."""
    after = page.split("risk and trade planning", 1)[1]
    return after.split("</section>", 1)[0]


# ---------------------------------------------------------------------------
# A. WAIT + no trade geometry -> no misleading position size
# ---------------------------------------------------------------------------


def test_a_waiting_symbol_gets_no_position_size_on_the_page() -> None:
    page = _page(result(assessment("BTCUSDT", direction=None)))
    assert "risk and trade planning" in page
    assert "NO TRADE PLAN" in page
    assert "maximum quantity" not in page
    assert "capital at risk" not in page


def test_a_waiting_symbol_says_there_is_no_trade_rather_than_saying_nothing() -> None:
    page = _page(result(assessment("BTCUSDT", direction=None)))
    assert "No trade plan is available for risk evaluation" in page


# ---------------------------------------------------------------------------
# B. A candidate with a missing input -> NOT EVALUABLE with the exact reason
# ---------------------------------------------------------------------------


def test_a_candidate_with_no_declared_fraction_is_not_evaluable_on_the_page() -> None:
    page = _page(
        result(assessment("BTCUSDT", state=SetupState.CANDIDATE)), fraction=None
    )
    assert "NOT EVALUABLE" in page
    assert "missing before a size can be produced" in page
    assert "per_trade_fraction" in page


def test_a_missing_input_is_never_rendered_as_a_zero() -> None:
    page = _page(
        result(assessment("BTCUSDT", state=SetupState.CANDIDATE)), fraction=None
    )
    panel = _risk_panel(page)
    assert "unavailable" in panel
    # Scoped to the panel deliberately: the evidence section legitimately prints
    # `0 supporting`, and a page-wide assertion would be satisfied by counting
    # that rather than by the risk figures actually being absent.
    assert ">0<" not in panel
    assert ">0 " not in panel


# ---------------------------------------------------------------------------
# C / D. Valid geometry, long and short, with the hand-calculated figures
# ---------------------------------------------------------------------------


def test_a_confirmed_long_shows_the_hand_calculated_figures() -> None:
    page = _page(result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))
    assert "WITHIN DECLARED RISK BUDGET" in page
    assert "50 USDT" in page
    assert "500 USDT" in page
    assert "5 BTC" in page


def test_the_page_prints_the_ceiling_and_names_where_it_comes_from() -> None:
    page = _page(result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))
    assert "hard ceiling" in page
    assert "0.02" in page
    assert "PROJECT_SPECIFICATION_V1 §8.1" in page
    assert "not a default target" in page


def test_the_entry_is_labelled_as_a_close_and_not_as_an_order_price() -> None:
    """§11's rule, on the page. A size derived from a close must not read as an
    order at that close."""
    page = _page(result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))
    assert "not an order price" in page
    assert "fabricates no exact entry" in page


# ---------------------------------------------------------------------------
# G. Unknown portfolio context is never silently zero
# ---------------------------------------------------------------------------


def test_the_page_states_that_portfolio_impact_was_not_evaluated() -> None:
    page = _page(result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))
    assert "portfolio impact" in page
    assert "not the same as their being zero" in page


def test_the_page_never_claims_the_computed_loss_is_the_maximum_possible() -> None:
    """§38. A stop does not guarantee an exact loss, and the page says so.

    The phrase *"maximum possible loss"* does appear — as a **denial**. So this
    asserts the claim is absent rather than the substring: every occurrence must
    be negated, and the gap and slippage caveats must be present beside it.
    """
    panel = _risk_panel(_page(result(assessment("BTCUSDT", state=SetupState.CONFIRMED))))
    assert "gap" in panel
    assert "slippage" in panel
    assert "not maximum possible loss" in panel
    # No un-negated occurrence anywhere on the panel.
    assert panel.count("maximum possible loss") == panel.count(
        "not maximum possible loss"
    )
    for claim in ("guaranteed loss", "worst case is", "maximum loss is"):
        assert claim not in panel, claim


# ---------------------------------------------------------------------------
# The decision is authoritative: risk never rewrites it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state,direction",
    [
        (SetupState.CONFIRMED, "long"),
        (SetupState.CANDIDATE, "long"),
        (SetupState.WAIT, None),
    ],
)
def test_the_decision_is_identical_with_and_without_a_declared_policy(
    state: SetupState, direction: str | None
) -> None:
    """**§40, asserted structurally.** Every field of every decision record is
    compared, with only the plan excluded — so a change that let a risk figure
    reach the assessment, the thesis, the blocker, the evidence or the ordering
    fails here rather than being noticed by a reader."""
    subject = result(
        assessment("BTCUSDT", state=state, direction=None if direction is None else None)
        if direction is None
        else assessment("BTCUSDT", state=state)
    )
    without = _workspace(subject, declared=False)
    with_policy = _workspace(subject)

    assert len(without.decisions) == len(with_policy.decisions) == 1
    bare, planned = without.decisions[0], with_policy.decisions[0]
    for field in bare.__dataclass_fields__:
        if field == "plan":
            continue
        assert getattr(bare, field) == getattr(planned, field), field


def test_every_other_section_of_the_page_is_unchanged_by_a_declared_policy() -> None:
    """Opportunities, wait list, no-trade groups, ranking and the summary are
    compared whole. Risk observes the decision; it never participates in it."""
    subject = result(assessment("BTCUSDT", state=SetupState.CONFIRMED))
    without = _workspace(subject, declared=False)
    with_policy = _workspace(subject)

    assert without.opportunities == with_policy.opportunities
    assert without.wait_list == with_policy.wait_list
    assert without.no_trade == with_policy.no_trade
    assert without.summary == with_policy.summary
    assert without.ranking_rule == with_policy.ranking_rule


def test_the_scan_order_is_unchanged_by_a_declared_policy() -> None:
    """Nothing is reordered by whether a size could be produced."""
    subjects = [
        result(assessment("BTCUSDT", state=SetupState.CONFIRMED)),
        result(assessment("ETHUSDT", direction=None)),
        result(assessment("SOLUSDT", state=SetupState.CANDIDATE)),
    ]
    without = [d.symbol for d in _workspace(*subjects, declared=False).decisions]
    with_policy = [d.symbol for d in _workspace(*subjects).decisions]
    assert without == with_policy == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


# ---------------------------------------------------------------------------
# J. Repeated rendering mutates nothing
# ---------------------------------------------------------------------------


def test_rendering_the_same_page_twice_produces_the_same_bytes() -> None:
    subject = result(assessment("BTCUSDT", state=SetupState.CONFIRMED))
    assert _page(subject) == _page(subject)


def test_rendering_does_not_change_the_plan_it_rendered() -> None:
    workspace = _workspace(result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))
    plan = workspace.decisions[0].plan
    before = (plan.status, plan.quantity, plan.money_at_risk)
    view = swing_view(workspace)
    snapshot = build_snapshot(
        refreshed_at=REFERENCE, reference_time=REFERENCE, workspace=workspace
    )
    render_page(snapshot, "/swing", symbol="BTCUSDT")
    render_page(snapshot, "/swing", symbol="BTCUSDT")
    assert (plan.status, plan.quantity, plan.money_at_risk) == before
    assert view.decisions[0].plan is not None


# ---------------------------------------------------------------------------
# The note the dashboard used to drop
# ---------------------------------------------------------------------------


def test_the_swing_page_states_whether_a_size_was_computed_at_all() -> None:
    """The audit's second break. `workspace.metadata['risk_note']` existed and
    `swing_view` dropped it, so the page could not say why no figure appeared."""
    workspace = _workspace(
        result(assessment("BTCUSDT", state=SetupState.CONFIRMED)), declared=False
    )
    assert "no risk policy is declared" in swing_view(workspace).risk_note


def test_the_note_names_the_declared_capital_when_there_is_one() -> None:
    workspace = _workspace(result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))
    note = swing_view(workspace).risk_note
    assert "10000 USDT" in note
    assert "0.005" in note
    assert "not the same as its being zero" in note


def test_the_overview_risk_column_carries_a_state_and_never_a_number() -> None:
    """§30. A column of position sizes is a column the eye ranks."""
    page = _overview(result(assessment("BTCUSDT", state=SetupState.CONFIRMED)))
    table = page.split("Every scanned symbol")[1].split("Top opportunities")[0]
    assert "WITHIN DECLARED RISK BUDGET" in table
    assert "50 USDT" not in table
    assert "5 BTC" not in table


def test_every_stated_limitation_reaches_the_page() -> None:
    """`PLANNING_LIMITATIONS` has a consumer, and this is it.

    A constant defined, exported and rendered nowhere is exactly the *capacity
    without a consumer* this milestone exists to correct, so its arrival on the
    page is asserted rather than assumed. The instrument-scope entry matters most:
    it is the only place the page says the arithmetic is **not** correct for
    inverse contracts, dated futures or options, and that no leverage is modelled.
    """
    from fmis.risk_policy import PLANNING_LIMITATIONS

    panel = _risk_panel(_page(result(assessment("BTCUSDT", state=SetupState.CONFIRMED))))
    assert PLANNING_LIMITATIONS
    for title, _detail in PLANNING_LIMITATIONS:
        assert title in panel, title
    assert "inverse contracts" in panel
    assert "no leverage is modelled" in panel


def test_a_symbol_with_no_trade_to_plan_carries_no_limitations_block() -> None:
    """Nothing was computed, so there is nothing to caveat. A page that listed
    what a figure is not, beside no figure, is noise."""
    panel = _risk_panel(_page(result(assessment("BTCUSDT", direction=None))))
    assert "what these figures are not" not in panel


def test_the_page_names_the_policy_contract_the_figures_were_computed_under() -> None:
    """Provenance: *which policy produced this number?* Risk limits will evolve,
    and a figure a future reader cannot attribute to a contract version is a
    figure they cannot reconstruct."""
    from fmis.risk_policy.models import RISK_POLICY_CONTRACT_VERSION

    panel = _risk_panel(_page(result(assessment("BTCUSDT", state=SetupState.CONFIRMED))))
    assert f"risk policy contract v{RISK_POLICY_CONTRACT_VERSION}" in panel


def test_the_no_trade_sentence_reads_as_prose_and_not_as_two_fragments() -> None:
    """The panel's one sentence for a `WAIT` symbol, asserted as written text.

    It is assembled from three pieces — a fixed opening, the engine's own reason,
    and a fixed closing — and a punctuation slip at either seam is invisible to
    every other test here while being the only thing most of the watchlist ever
    shows. An earlier fix to this landed on one side of the seam and not the
    other, producing *"risk evaluation: The engine states…"*, which is why the
    joined result is pinned rather than the pieces.
    """
    panel = _risk_panel(_page(result(assessment("BTCUSDT", direction=None))))
    text = " ".join(re.sub(r"<[^>]+>", " ", panel).split())
    assert "risk evaluation. The engine states no direction" in text
    assert "risk evaluation:" not in text
    # No fragment runs into the next without a stop between them.
    assert "nothing is wrong. No entry" in text
    assert "symbol No entry" not in text


def test_the_fallback_sentence_is_also_complete_prose() -> None:
    """The branch taken when a plan carries no reason of its own. Unreachable
    today — a `NO_TRADE_PLAN` always states one — and asserted anyway, because a
    fallback nobody exercises is a fallback nobody notices is malformed."""
    from fmis.operator_dashboard.models import SymbolDecisionRow, TradeRiskPlanRow
    from fmis.operator_dashboard.render import _decision_detail

    row = SymbolDecisionRow(
        symbol="BTCUSDT",
        state="wait",
        classification="read and declined",
        reason="r",
        sufficiency="sufficient",
        as_of=datetime(2026, 9, 6, tzinfo=UTC),
        plan=TradeRiskPlanRow(symbol="BTCUSDT", status="no_trade_plan"),
    )
    text = " ".join(re.sub(r"<[^>]+>", " ", _decision_detail(row, "note")).split())
    assert "The engine states no direction for this symbol. No entry" in text
