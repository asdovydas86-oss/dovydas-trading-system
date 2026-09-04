"""Slice 1 — proof that the new tests would have failed before the change.

A test that passes both before and after a change measures nothing. This module
demonstrates, against code that is **still in the repository and still
unmodified**, that the information Slice 1 carries was genuinely destroyed
before it — so the assertions in `test_swing_symbol_decision` could not have
passed against the pre-Slice-1 surface.

The demonstration is direct rather than historical. Three pre-Slice-1 carriers
survive untouched and are exercised here as the "before" state:

  * `no_trade_groups` — the **only** place a `WAIT` symbol reached the workspace
    before Slice 1. Still present, still producing exactly what it produced.
  * `evidence_digest_for` — the evidence attachment, which was built for
    *actionable* rows only and reduces a report to four integers either way.
  * `SwingView.row_for` — the lookup the symbol detail route used, which
    consults `opportunities` and `wait_list` and nothing else.

Each test below asserts what those three could and could not answer, then
asserts that the Slice 1 surface answers it. Offline and deterministic
throughout.
"""

from __future__ import annotations

import dataclasses

from fmis.operator_dashboard import render_page
from fmis.swing_workspace import (
    evidence_digest_for,
    no_trade_groups,
    symbol_decisions,
)

from tests.swing_decision_helpers import (
    GATE_REJECTED,
    live,
    snapshot_of,
    two_wait_paths,
)


def _pre_slice_1_no_trade_fields(results) -> set[str]:
    """Every distinct fact about a `WAIT` symbol the old carrier could state."""
    return {
        value
        for group in no_trade_groups(results)
        for value in (group.reason, group.classification, *group.symbols)
    }


# ===========================================================================
# 1. The old grouping lost per-symbol detail
# ===========================================================================


def test_the_old_grouping_carried_a_symbol_as_a_bare_name_and_nothing_else() -> None:
    """`NoTradeGroup` has three fields, and one of them is a list of strings.

    The symbol arrives as text inside a group. Its regime reading, its
    directional families, its sufficiency, its `as_of` and its entire evidence
    report reach the workspace nowhere at all.
    """
    gate, split = two_wait_paths()
    groups = no_trade_groups([gate, split])
    # Three fields, and that is the whole vocabulary the old seam had.
    assert [f.name for f in dataclasses.fields(groups[0])] == [
        "reason",
        "classification",
        "symbols",
    ]

    carried = _pre_slice_1_no_trade_fields([gate, split])
    # The symbols are there — as names.
    assert "AAAUSDT" in carried and "BBBUSDT" in carried

    # And nothing else about either of them is. Every one of these is a fact the
    # engine produced and the old seam dropped.
    decision = symbol_decisions([gate])[0]
    assert decision.regime_context[0] not in carried
    assert decision.sufficiency not in carried
    for factor in decision.factors:
        assert factor.observed not in carried
        assert factor.source not in carried
    for item in decision.supporting + decision.conflicting:
        assert item.statement not in carried
        assert item.observed not in carried


def test_the_old_grouping_could_not_answer_which_symbol_had_which_factors() -> None:
    """Two symbols in one group are indistinguishable inside it. By construction."""
    left = live(GATE_REJECTED, "AAAUSDT")
    right = live(GATE_REJECTED, "BBBUSDT")
    groups = no_trade_groups([left, right])

    # One group, two symbols, one reason: the old surface says the same sentence
    # about both and has nowhere to record that they differ.
    assert len(groups) == 1
    assert set(groups[0].symbols) == {"AAAUSDT", "BBBUSDT"}

    # Slice 1 gives each its own record, and each carries its own evidence.
    records = symbol_decisions([left, right])
    assert len(records) == 2
    assert {r.symbol for r in records} == {"AAAUSDT", "BBBUSDT"}
    assert all(r.evidence_available for r in records)


# ===========================================================================
# 2. The old evidence attachment was counts, and reached actionable rows only
# ===========================================================================


def test_the_old_evidence_digest_carries_counts_and_no_item() -> None:
    """Four integers cannot tell two WAIT symbols apart, and cannot be checked."""
    gate, _ = two_wait_paths()
    digest = evidence_digest_for(gate.assessment)
    decision = symbol_decisions([gate])[0]

    # The counts agree — Slice 1 changed no number.
    assert digest.supporting == len(decision.supporting)
    assert digest.conflicting == len(decision.conflicting)

    # But the digest has no item on it at all: no statement, no observed value,
    # no source, no scope, no correlation, no independence note.
    for absent in ("statement", "observed", "source", "scope", "correlated_with"):
        assert not hasattr(digest, absent), absent

    # Slice 1 carries every one of them.
    item = (decision.supporting + decision.conflicting)[0]
    assert item.statement and item.observed and item.source


def test_two_wait_symbols_are_indistinguishable_by_the_old_counts_alone() -> None:
    """The concrete failure mode: same numbers, materially different cases.

    Whether or not a particular pair happens to share counts, the counts are
    the *only* thing the old attachment offered, and they carry none of the
    facts that make the two cases different. This asserts that directly.
    """
    gate, split = two_wait_paths()
    left, right = evidence_digest_for(gate.assessment), evidence_digest_for(
        split.assessment
    )
    for field in ("agreeing_families", "conflicting_families"):
        assert isinstance(getattr(left, field), tuple)

    # Nothing on either digest names the regime, the gate, the timeframes or
    # which family leaned which way — the four things that distinguish an
    # early regime rejection from a weekly-versus-daily structural conflict.
    for digest in (left, right):
        text = repr(digest)
        assert "structure=" not in text
        assert "1w" not in text and "1d" not in text
        assert "sustained_higher" not in text and "sustained_lower" not in text

    # Slice 1 carries all four, and the two records differ on them.
    a, b = symbol_decisions([gate, split])
    assert a.regime_context != b.regime_context
    assert [f.lean for f in a.factors] != [f.lean for f in b.factors]
    assert any("1w" in f.source for f in a.factors)


# ===========================================================================
# 3. The old detail route refused every WAIT symbol
# ===========================================================================


def test_the_old_lookup_returns_nothing_for_a_waiting_symbol() -> None:
    """`row_for` is the pre-Slice-1 lookup, unmodified, and it still says no."""
    gate, split = two_wait_paths()
    snapshot = snapshot_of(gate, split)
    view = snapshot.swing.data

    # The old route consulted this and nothing else.
    assert view.row_for("AAAUSDT") is None
    assert view.row_for("BBBUSDT") is None

    # Which is why the page could only say "not on this page". Slice 1's lookup
    # answers for the same two symbols.
    assert view.decision_for("AAAUSDT") is not None
    assert view.decision_for("BBBUSDT") is not None


def test_the_detail_page_for_a_waiting_symbol_grew_from_a_refusal_to_a_page() -> None:
    """The product change, measured on the rendered output.

    The pre-Slice-1 page for a `WAIT` symbol was one sentence saying the symbol
    was not on it. This asserts that what renders now is a real page — the four
    decision panels — and that the refusal is gone.
    """
    gate, _ = two_wait_paths()
    snapshot = snapshot_of(gate)
    html = render_page(snapshot, "/swing", symbol="AAAUSDT")

    assert "produced no assessment on this refresh" not in html
    for panel in (
        "AAAUSDT — decision",
        "AAAUSDT — timeframe context and data times",
        "AAAUSDT — directional families",
        "AAAUSDT — evidence and independence audit",
    ):
        assert panel in html, panel


def test_the_swing_page_gained_a_per_symbol_surface_it_did_not_have() -> None:
    """The list route: symbols were only ever inside a grouped cell before."""
    gate, split = two_wait_paths()
    snapshot = snapshot_of(gate, split)
    html = render_page(snapshot, "/swing")

    assert "Every scanned symbol" in html
    # Each waiting symbol is now its own linked row, not a comma-joined cell.
    assert '<a href="/swing/AAAUSDT">' in html
    assert '<a href="/swing/BBBUSDT">' in html
    # And each row states its own condition, in the engine's words.
    assert "not trending" in html
    assert "do not agree" in html
