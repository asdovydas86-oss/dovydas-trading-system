"""Slice 1 — the per-symbol swing decision surface.

**The seam this milestone closes.** The engine produces, for every scanned
symbol, a `SetupAssessment` carrying a state, a sufficiency verdict, a thesis,
the directional families it tallied and the regime lines it read — and
`fmis.setup_evidence` will project a complete evidence report off any of them,
`WAIT` included. Before Slice 1 the workspace kept that only for *actionable*
symbols: every `WAIT` collapsed into a `NoTradeGroup(reason, classification,
symbols)`, so a waiting BTCUSDT had no row of its own anywhere and its detail
route answered *not on this page*.

Every test here is **offline and deterministic**: assessments come either from
hand-built fixtures or from `archive_helpers.multi`, which builds a three-view
fact sheet from seeded synthetic candles. No provider, no clock, no filesystem
and no network appears in any call graph below.

The two live `WAIT` paths are exercised through the *real* composition root
rather than through hand-written assessments, so the paths under test are the
ones the product actually reaches. `swing_decision_helpers` names the seed
triples and explains which exit of `evaluate_setup` each one reaches.

Those are the *shapes* the audit named for BTCUSDT and BNBUSDT. No live value is
asserted anywhere and no symbol is named after a real one — the fixtures stand
in for the shapes, so a change in what the market did cannot break these tests.
"""

from __future__ import annotations

import dataclasses
import re

import pytest

from fmis.operator_dashboard import render_page
from fmis.operator_dashboard.models import SymbolDecisionRow
from fmis.setup_evidence import project_setup_evidence
from fmis.swing_setup import SetupState
from fmis.swing_workspace import (
    SymbolDecision,
    no_trade_groups,
    symbol_decisions,
)

from tests.swing_decision_helpers import (
    CANDIDATE,
    FAMILIES_SPLIT,
    GATE_REJECTED,
    live,
    snapshot_of,
    two_wait_paths,
    workspace_of,
)
from tests.swing_workspace_helpers import assessment, failed_result, result

# ===========================================================================
# 1. The projection carries what the seam used to drop
# ===========================================================================


def test_every_assessed_symbol_gets_a_decision_record_whatever_its_state() -> None:
    """The population is the scan, not the actionable subset."""
    decisions = symbol_decisions(
        [
            live(GATE_REJECTED, "AAAUSDT"),
            live(CANDIDATE, "BBBUSDT"),
            failed_result("CCCUSDT"),
        ]
    )
    assert [d.symbol for d in decisions] == ["AAAUSDT", "BBBUSDT"]
    assert {d.state for d in decisions} == {"wait", "candidate"}


def test_a_symbol_that_produced_no_assessment_gets_no_decision() -> None:
    """A provider outage is not a decision. It is stated as an outage."""
    assert symbol_decisions([failed_result("AAAUSDT")]) == ()


def test_a_wait_symbol_keeps_its_evidence_report_item_by_item() -> None:
    """The capability the audit found already working, now reaching the surface.

    `project_setup_evidence` accepts a `WAIT` assessment and always did. The
    decision record must carry the *items* it produced, not counts of them.
    """
    waiting = live(GATE_REJECTED, "AAAUSDT")
    expected = project_setup_evidence(waiting.assessment)
    assert expected.supporting or expected.conflicting

    decision = symbol_decisions([waiting])[0]
    assert decision.state == SetupState.WAIT.value
    assert decision.evidence_available
    for group in ("supporting", "conflicting", "missing", "unavailable"):
        carried = getattr(decision, group)
        projected = getattr(expected, group)
        assert [item.key for item in carried] == [item.key for item in projected]
        assert [item.statement for item in carried] == [
            item.statement for item in projected
        ]
        assert [item.observed for item in carried] == [
            item.observed for item in projected
        ]


def test_a_wait_symbol_keeps_the_families_the_policy_tallied() -> None:
    """The lean of each family, including the members that cast no vote."""
    decision = symbol_decisions([live(GATE_REJECTED, "AAAUSDT")])[0]
    source = live(GATE_REJECTED, "AAAUSDT").assessment
    assert [f.family for f in decision.factors] == [
        f.family for f in source.directional_factors
    ]
    assert [f.lean for f in decision.factors] == [
        f.lean.value for f in source.directional_factors
    ]
    # The source/timeframe survives, which is how a reader tells a weekly
    # reading from a daily one without consulting the code.
    assert any("1w" in factor.source for factor in decision.factors)
    assert any("1d" in factor.source for factor in decision.factors)


def test_a_wait_symbol_keeps_its_regime_and_sufficiency() -> None:
    decision = symbol_decisions([live(GATE_REJECTED, "AAAUSDT")])[0]
    assert decision.regime_context
    assert "structure=" in decision.regime_context[0]
    assert decision.sufficiency
    assert decision.as_of == live(GATE_REJECTED, "AAAUSDT").assessment.as_of


def test_the_grouped_section_and_the_per_symbol_row_cannot_disagree() -> None:
    """One rule produces the reason and the classification for both sections."""
    results = list(two_wait_paths())
    groups = no_trade_groups(results)
    decisions = symbol_decisions(results)
    grouped = {
        symbol: (group.reason, group.classification)
        for group in groups
        for symbol in group.symbols
    }
    assert grouped
    for decision in decisions:
        assert grouped[decision.symbol] == (
            decision.reason,
            decision.classification,
        )


# ===========================================================================
# 2. Two WAIT symbols stay different
# ===========================================================================


def test_two_wait_symbols_sharing_a_classification_keep_different_detail() -> None:
    """Both are `WAIT`, both *read and declined* — and they are not the same case."""
    gate, split = two_wait_paths()
    left, right = symbol_decisions([gate, split])

    assert left.state == right.state == "wait"
    assert left.classification == right.classification

    # …and everything that matters differs.
    assert left.reason != right.reason
    assert left.regime_context != right.regime_context
    assert [f.lean for f in left.factors] != [f.lean for f in right.factors]


def test_a_regime_gate_rejection_is_distinguishable_from_a_family_conflict() -> None:
    """The BTC-shaped path and the BNB-shaped path, told apart structurally.

    Not by parsing prose: the *gate* case is the one whose context-role regime
    structure is not trending, and the *conflict* case is the one that passed
    that gate and then split. Both facts are carried on the record.
    """
    gate, split = two_wait_paths()
    rejected, conflicted = symbol_decisions([gate, split])

    # The gate case never reached the tally: its context regime is not trending.
    assert "structure=trending" not in rejected.regime_context[0]
    # The conflict case cleared the same gate…
    assert "structure=trending" in conflicted.regime_context[0]
    # …and failed on a genuine split between the timeframes: the context-role
    # (weekly) family and the setup-role (daily) family lean opposite ways.
    leans = {factor.family: factor.lean for factor in conflicted.factors}
    assert leans["context_structural_trend"] != leans["setup_structural_trend"]
    assert {"long", "short"} <= set(leans.values())

    # The two never collapse into one message.
    assert rejected.reason != conflicted.reason


def test_the_two_paths_stay_distinguishable_on_the_rendered_page() -> None:
    """The distinction has to survive all the way to HTML, not just the model."""
    gate, split = two_wait_paths()
    snapshot = snapshot_of(gate, split)
    left = render_page(snapshot, "/swing", symbol="AAAUSDT")
    right = render_page(snapshot, "/swing", symbol="BBBUSDT")

    assert "not trending" in left
    assert "not trending" not in right
    assert "do not agree" in right
    assert "do not agree" not in left


# ===========================================================================
# 3. Independence disclosure survives the seam
# ===========================================================================


def test_correlated_evidence_is_carried_with_its_correlation() -> None:
    """Three views of one reading must not arrive looking like three readings."""
    decision = symbol_decisions([live(GATE_REJECTED, "AAAUSDT")])[0]
    assert decision.correlated_keys, "the fixture must exercise a real correlation"
    carried = {
        item.key: item
        for group in (decision.supporting, decision.conflicting)
        for item in group
    }
    dependent = [item for item in carried.values() if item.correlated_with]
    assert dependent, "at least one carried item declares a correlation"
    for item in dependent:
        assert item.independence_note


def test_non_independence_is_stated_on_the_rendered_evidence_row() -> None:
    gate, _ = two_wait_paths()
    snapshot = snapshot_of(gate)
    html = render_page(snapshot, "/swing", symbol="AAAUSDT")
    assert "not independent" in html
    assert "shares inputs with:" in html


def test_agreement_without_established_independence_says_so() -> None:
    decision = symbol_decisions([live(FAMILIES_SPLIT, "BBBUSDT")])[0]
    assert decision.independence_established is False
    assert decision.independence_caveats


def test_a_decision_cannot_claim_independence_and_caveat_it_at_once() -> None:
    with pytest.raises(Exception) as caught:
        SymbolDecision(
            symbol="AAAUSDT",
            state="wait",
            classification="read and declined",
            reason="a reason",
            sufficiency="sufficient",
            as_of=assessment("AAAUSDT", direction=None).as_of,
            decision_ready_reason="stated",
            independence_established=True,
            independence_caveats=("but these inputs are shared",),
        )
    assert "independence" in str(caught.value)


# ===========================================================================
# 4. No ranking. The architectural guard.
# ===========================================================================

#: Field names that would turn this projection into the unvalidated opportunity
#: ranking the research record (CA/CB/CC/CD) gives no basis for.
_RANKING_VOCABULARY = re.compile(
    r"score|rank|closeness|confidence|probabilit|weight|strength|percentile"
    r"|priority|opportunity_|likelihood|conviction",
    re.IGNORECASE,
)


@pytest.mark.parametrize("model", [SymbolDecision, SymbolDecisionRow])
def test_the_decision_models_hold_no_ranking_field(model: type) -> None:
    """A guard, so a later change cannot quietly add one."""
    for field in dataclasses.fields(model):
        assert not _RANKING_VOCABULARY.search(field.name), field.name


def test_decisions_are_in_scan_order_and_no_property_of_the_analysis_moves_them() -> None:
    """Reverse the request and the rows reverse with it. Nothing else reorders."""
    gate, split = two_wait_paths()
    candidate = live(CANDIDATE, "CCCUSDT")
    forward = symbol_decisions([gate, split, candidate])
    backward = symbol_decisions([candidate, split, gate])
    assert [d.symbol for d in forward] == ["AAAUSDT", "BBBUSDT", "CCCUSDT"]
    assert [d.symbol for d in backward] == ["CCCUSDT", "BBBUSDT", "AAAUSDT"]


def test_a_richer_evidence_report_does_not_move_a_row_up_the_page() -> None:
    """The one property most likely to be mistaken for a ranking signal."""
    gate, split = two_wait_paths()
    candidate = live(CANDIDATE, "CCCUSDT")
    decisions = symbol_decisions([gate, split, candidate])
    counts = [len(d.supporting) for d in decisions]
    assert counts != sorted(counts, reverse=True) or len(set(counts)) == 1, (
        "the fixture must not accidentally already be in descending evidence "
        "order, or this test would pass without asserting anything"
    )


def test_the_rendered_symbol_table_carries_no_ordering_column() -> None:
    gate, split = two_wait_paths()
    snapshot = snapshot_of(gate, split)
    html = render_page(snapshot, "/swing")
    table = html.split("Every scanned symbol")[1].split("Top opportunities")[0]
    for word in ("score", "rank", "closeness", "confidence"):
        assert word not in table.lower(), word
    assert "order carries no meaning" in table


def test_the_page_states_that_scan_order_means_nothing() -> None:
    gate, _ = two_wait_paths()
    workspace = workspace_of(gate)
    codes = {code for code, _ in workspace.limitations}
    assert "WS-11" in codes
    text = dict(workspace.limitations)["WS-11"]
    assert "carries no meaning" in text


# ===========================================================================
# 5. Routing and the detail surface
# ===========================================================================


def test_a_waiting_symbol_now_has_a_detail_page() -> None:
    """The product outcome, asserted directly."""
    gate, _ = two_wait_paths()
    snapshot = snapshot_of(gate)
    view = snapshot.swing.data
    # Not actionable, and not waiting on a confirmation: it has no `SetupRow`.
    assert view.row_for("AAAUSDT") is None
    assert view.decision_for("AAAUSDT") is not None

    html = render_page(snapshot, "/swing", symbol="AAAUSDT")
    for heading in (
        "AAAUSDT — decision",
        "AAAUSDT — timeframe and regime context",
        "AAAUSDT — directional families",
        "AAAUSDT — evidence",
    ):
        assert heading in html, heading


def test_the_symbol_list_links_every_scanned_symbol_to_its_detail() -> None:
    gate, split = two_wait_paths()
    html = render_page(snapshot_of(gate, split), "/swing")
    assert "/swing/AAAUSDT" in html
    assert "/swing/BBBUSDT" in html


def test_a_symbol_that_produced_no_assessment_still_says_so() -> None:
    html = render_page(
        snapshot_of(failed_result("AAAUSDT")), "/swing", symbol="AAAUSDT"
    )
    assert "produced no assessment on this refresh" in html


def test_an_actionable_symbol_keeps_its_setup_panels_and_gains_the_decision_ones() -> None:
    """Slice 1 adds a surface. It removes none."""
    snapshot = snapshot_of(result(assessment("AAAUSDT", state=SetupState.CONFIRMED)))
    html = render_page(snapshot, "/swing", symbol="AAAUSDT")
    assert "AAAUSDT — setup" in html
    assert "AAAUSDT — identity, paper and holdings" in html
    assert "AAAUSDT — decision" in html
    assert "AAAUSDT — directional families" in html


def test_the_detail_page_offers_no_trading_action() -> None:
    gate, _ = two_wait_paths()
    html = render_page(snapshot_of(gate), "/swing", symbol="AAAUSDT").lower()
    assert "<button" not in html
    assert "<form" not in html


#: An *affirmative* quantified claim about an edge. Each pattern pairs the
#: vocabulary with a number or a verb of assertion, because the page is
#: **required** to use several of these words in denials — "no probability,
#: confidence or expected return is computed anywhere on this page" must not
#: read as a violation of the rule it states.
_EDGE_CLAIM = re.compile(
    r"(expected return|win rate|hit rate|edge|probability|confidence)\s*"
    r"(of|is|was|:)?\s*[-+]?\d",
    re.IGNORECASE,
)


def test_the_detail_page_claims_no_validated_edge() -> None:
    """The research boundary (CA/CB/CC/CD), asserted on the surface.

    CA found NO_EDGE, CB was underpowered, CC infeasible and CD rejected the
    independent-cluster assumption. None of that stops this page explaining a
    deterministic conclusion; all of it stops the page quantifying one.
    """
    gate, split = two_wait_paths()
    snapshot = snapshot_of(gate, split)
    pages = [
        render_page(snapshot, "/swing"),
        render_page(snapshot, "/swing", symbol="AAAUSDT"),
        render_page(snapshot, "/swing", symbol="BBBUSDT"),
    ]
    for html in pages:
        found = _EDGE_CLAIM.search(html)
        assert found is None, found.group(0) if found else ""
        lowered = html.lower()
        # Only phrasings that cannot occur inside a denial. The engine's own
        # limitation lines legitimately say "no backtested statistical model
        # exists", so the bare word "backtested" is not evidence of a claim.
        for claim in ("profitable", "validated edge", "proven edge"):
            assert claim not in lowered, claim


def test_the_detail_page_states_that_it_computes_no_probability() -> None:
    """The denial has to be present, not merely the absence of a claim."""
    gate, _ = two_wait_paths()
    html = render_page(snapshot_of(gate), "/swing", symbol="AAAUSDT")
    assert "No probability, confidence or expected return is computed" in html
    assert "not a score" in html


# ===========================================================================
# 6. One symbol, one decision
# ===========================================================================


def test_a_symbol_requested_twice_produces_one_decision_and_keeps_the_page() -> None:
    """`fmits workspace BTCUSDT BTCUSDT` is answered twice and decided once."""
    twice = [
        result(assessment("AAAUSDT", state=SetupState.CONFIRMED)),
        result(assessment("AAAUSDT", state=SetupState.CONFIRMED)),
    ]
    workspace = workspace_of(*twice)
    assert len(workspace.opportunities) == 2
    assert [d.symbol for d in workspace.decisions] == ["AAAUSDT"]
    assert workspace.decision("AAAUSDT") is not None


def test_the_workspace_refuses_two_decision_records_for_one_symbol() -> None:
    """Checked on the object, so a second composition root cannot assemble it."""
    gate, _ = two_wait_paths()
    workspace = workspace_of(gate)
    only = workspace.decisions[0]
    with pytest.raises(Exception) as caught:
        dataclasses.replace(workspace, decisions=(only, only))
    assert "two decision records" in str(caught.value)


def test_the_decision_lookup_is_a_lookup_and_not_a_nearest_match() -> None:
    gate, _ = two_wait_paths()
    workspace = workspace_of(gate)
    assert workspace.decision("AAAUSDT") is not None
    assert workspace.decision("AAA") is None
    assert workspace.decision("AAAUSDTX") is None


def test_a_decision_with_no_directional_family_says_so_rather_than_explaining_nothing() -> None:
    """An empty families table must not render its own explanatory footnote.

    The panel body was built by concatenating the table with a note describing
    it, and falling back to an empty-state message *only if the whole thing was
    falsy* — which it never is, because the note alone is truthy. The result
    would have been a paragraph explaining how to read a table that is not
    there.
    """
    # A `WAIT` assessment with no factors at all: the helper's `direction=None`
    # shape, which the engine's own validation permits.
    snapshot = snapshot_of(result(assessment("AAAUSDT", direction=None)))
    decision = snapshot.swing.data.decision_for("AAAUSDT")
    assert decision is not None and decision.factors == ()

    html = render_page(snapshot, "/swing", symbol="AAAUSDT")
    assert "No directional family was recorded for this assessment." in html
    assert "The families the policy tallies" not in html
