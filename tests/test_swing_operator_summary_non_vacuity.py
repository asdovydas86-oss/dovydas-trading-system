"""Slice 2 — proof that the new tests would have failed before the change.

A test that passes both before and after a change measures nothing. This module
demonstrates, against **code paths that still exist and are still reachable**,
that each thing Slice 2 adds was genuinely absent before it.

The "before" state is reproduced exactly, not approximated. Every carrier Slice
2 widened is optional and defaulted, so the pre-Slice-2 shape is still
constructible and is what these tests construct:

  * a `SetupRunResult` with **no** `readings` — which is what every caller
    produced before this milestone, because `run_setup_for_symbols` discarded
    the fact sheet with ``_, assessment = setup_for_symbol(...)``;
  * a `symbol_decisions` call with **no** `reference_time` — the Slice 1
    signature;
  * a `SwingView` with its **default** snapshot — the Slice 1 shape.

Each test asserts what that state could not answer, then asserts Slice 2
answers it.
"""

from __future__ import annotations

import dataclasses
import re

from fmis.operator_dashboard import render_page
from fmis.operator_dashboard.models import SwingView
from fmis.swing_setup import BlockerKind, DevelopingEvidenceState, summarise_decision
from fmis.swing_workspace import symbol_decisions

from tests.swing_decision_helpers import (
    FAMILIES_SPLIT,
    GATE_LEANING,
    live,
    snapshot_of,
)
from tests.swing_workspace_helpers import REFERENCE

BTC_SHAPED = GATE_LEANING
BNB_SHAPED = FAMILIES_SPLIT


# ===========================================================================
# 1. There was no per-role freshness, because the sheet was discarded
# ===========================================================================


def test_the_pre_slice_2_result_shape_carries_no_reading_instant_at_all() -> None:
    """`SetupRunResult` had three fields, and none of them was a timestamp.

    `run_setup_for_symbols` called `setup_for_symbol`, which returns the fact
    sheet, and threw the sheet away — so the per-role `as_of` values the sheet
    carries could not reach any surface above the scan.
    """
    before = live(BTC_SHAPED, "AAAUSDT", readings=False)
    assert before.readings is None

    decision = symbol_decisions([before], reference_time=REFERENCE)[0]
    assert decision.timeframes == ()

    # Slice 2 carries all three roles, each with its own instant and age.
    after = symbol_decisions([live(BTC_SHAPED, "AAAUSDT")], reference_time=REFERENCE)[0]
    assert [line.role for line in after.timeframes] == [
        "context",
        "setup",
        "execution",
    ]
    assert all(line.age is not None for line in after.timeframes)


def test_the_slice_1_call_signature_could_not_produce_an_age() -> None:
    """`symbol_decisions` took no reference instant, so no age was derivable."""
    decision = symbol_decisions([live(BTC_SHAPED, "AAAUSDT")])[0]
    assert decision.timeframes  # the instants are carried…
    assert all(line.age is None for line in decision.timeframes)  # …ages are not

    with_reference = symbol_decisions(
        [live(BTC_SHAPED, "AAAUSDT")], reference_time=REFERENCE
    )[0]
    assert all(line.age is not None for line in with_reference.timeframes)


def test_the_page_showed_one_instant_where_three_roles_were_read() -> None:
    """One `as_of` for three unsynchronised timeframes was the whole story.

    The assessment's own instant is still shown — it is a real fact — but it is
    a single value for three views that close at different rates, and before
    Slice 2 it was the only time on the page.
    """
    before = render_page(
        snapshot_of(live(BTC_SHAPED, "AAAUSDT", readings=False)),
        "/swing",
        symbol="AAAUSDT",
    )
    assert "Last closed candle" not in before
    assert "No per-role reading instant was carried" in before

    after = render_page(
        snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing", symbol="AAAUSDT"
    )
    assert "Last closed candle" in after
    for interval in ("1w", "1d", "4h"):
        assert interval in after, interval


# ===========================================================================
# 2. There was no developing-evidence summary
# ===========================================================================


def test_the_pre_slice_2_decision_record_had_no_developing_evidence_field() -> None:
    """A `WAIT` row said *direction: unavailable* and stopped there.

    The leans were on the record — Slice 1 carried every factor — but nothing
    reduced them to the one line a reader needs, and a surface doing it itself
    would have been a renderer inferring a side.
    """
    decision = symbol_decisions([live(BTC_SHAPED, "AAAUSDT")], reference_time=REFERENCE)[0]
    # The Slice 1 shape: the field exists but is unset.
    bare = dataclasses.replace(decision, developing=None, blocker=None)
    assert bare.developing is None
    assert bare.direction is None  # all the old surface could say

    # Slice 2 says which way the readable families point, and names them.
    assert decision.developing.state is DevelopingEvidenceState.LEANING
    assert decision.developing.lean is not None
    assert decision.developing.agreeing


def test_the_old_page_showed_only_that_no_direction_was_stated() -> None:
    before = _row_of(
        render_page(_with_swing(_slice_1_shape(live(BTC_SHAPED, "AAAUSDT"))), "/swing")
    )
    after = _row_of(render_page(snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing"))

    assert "leaning" not in before
    assert "leaning" in after
    assert "no developing-evidence summary was produced" in before


# ===========================================================================
# 3. There was no named, operator-facing blocker
# ===========================================================================


def test_the_old_surface_had_only_the_engines_full_sentence() -> None:
    """A 200-character paragraph per row is not a column you can scan.

    The sentence was — and still is — on the page. What did not exist was the
    **named condition** behind it: a value from a closed vocabulary that a
    snapshot can count and two symbols can be compared on.
    """
    decision = symbol_decisions([live(BTC_SHAPED, "AAAUSDT")], reference_time=REFERENCE)[0]
    bare = dataclasses.replace(decision, blocker=None)
    assert bare.blocker is None
    assert len(bare.reason) > 120  # the only thing the old row could show

    assert decision.blocker.kind is BlockerKind.CONTEXT_REGIME_NOT_ELIGIBLE
    assert decision.blocker.requirement  # what must become different
    assert decision.blocker.observed  # the value that failed it


def test_the_two_wait_cases_could_not_be_compared_on_a_named_condition() -> None:
    left = summarise_decision(*_parts(BTC_SHAPED))
    right = summarise_decision(*_parts(BNB_SHAPED))
    assert left.blocker.kind is not right.blocker.kind
    # Before, the only difference available was two long and different
    # sentences — true, but not a value anything could group or count on.
    assert left.blocker.kind.value in {kind.value for kind in BlockerKind}


# ===========================================================================
# 4. There was no scan snapshot
# ===========================================================================


def test_the_swing_view_had_no_snapshot_and_the_page_had_no_tiles() -> None:
    empty = _slice_1_shape(live(BTC_SHAPED, "AAAUSDT"), live(BNB_SHAPED, "BBBUSDT"))
    assert empty.snapshot.scanned == 0

    before = render_page(_with_swing(empty), "/swing")
    after = render_page(
        snapshot_of(live(BTC_SHAPED, "AAAUSDT"), live(BNB_SHAPED, "BBBUSDT")), "/swing"
    )
    assert "What is holding it</th>" in after
    # The tiles report the scan; with the default snapshot they report nothing.
    assert re.search(r"Scanned</div><div class=\"v\">2<", after)
    assert re.search(r"Scanned</div><div class=\"v\">0<", before)


# ===========================================================================
# 5. The overview could not be read without opening every symbol
# ===========================================================================


def test_the_old_overview_had_three_columns_and_no_operator_state() -> None:
    """Symbol, status, direction, classification, reason — and nothing else.

    None of the four questions Slice 2's columns answer — which way evidence is
    developing, what the two timeframes say, which condition is holding it, how
    old the data is — had a column before this milestone.
    """
    before = _row_of(
        render_page(_with_swing(_slice_1_shape(live(BTC_SHAPED, "AAAUSDT"))), "/swing")
    )
    for missing in ("1w ", "HTF regime not eligible", "leaning"):
        assert missing not in before, missing
    assert "no per-role reading instant was carried" in before.lower()

    after = _row_of(render_page(snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing"))
    for present in ("1w ", "HTF regime not eligible", "leaning"):
        assert present in after, present


def test_the_symbol_page_opened_with_the_audit_rather_than_the_decision() -> None:
    """Slice 1's panel order put the evidence audit second of four.

    Slice 2's first panel answers the trading question; the audit is fourth and
    behind a disclosure. The audit itself is unchanged and still complete —
    `test_the_full_evidence_audit_is_still_present_and_complete` asserts that.
    """
    html = render_page(
        snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing", symbol="AAAUSDT"
    )
    panels = re.findall(r"<h2>([^<]+)", html)
    assert panels[0] == "AAAUSDT — decision"
    assert panels.index("AAAUSDT — evidence and independence audit") == 3
    # The summary answers before the audit is reached, in the first panel.
    first = html.split("</section>")[0]
    assert "what is holding it" in first
    assert "developing evidence" in first
    assert "data age" in first


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _row_of(html: str, symbol: str = "AAAUSDT") -> str:
    """One symbol's row in the per-symbol table.

    Scoped to the row rather than the page, because the page's own explanatory
    notes legitimately use the same vocabulary in denials — *"a leaning row is
    still whatever its decision says it is"* is a sentence Slice 2 added, and a
    whole-page substring check would read it as the row's content.
    """
    return html.split(f"/swing/{symbol}")[1].split("</tr>")[0]


def _parts(seeds: tuple[int, int, int]):
    result = live(seeds, "AAAUSDT")
    return result.assessment, result.readings


def _with_swing(view: SwingView):
    """The full snapshot with one swing view swapped in, to render an old shape."""
    snapshot = snapshot_of(live(BTC_SHAPED, "AAAUSDT"))
    return dataclasses.replace(
        snapshot, swing=dataclasses.replace(snapshot.swing, data=view)
    )


def _slice_1_shape(*results):
    """A view in the exact pre-Slice-2 shape: no summaries, no snapshot, no times.

    Both halves must be removed together. Stripping only the rows leaves the
    scan snapshot still counting blockers and developing states, which is itself
    a Slice 2 surface — a "before" that still showed it would understate what
    the milestone added.
    """
    view = snapshot_of(*results).swing.data
    return dataclasses.replace(
        view,
        snapshot=SwingView(reference_time=view.reference_time).snapshot,
        decisions=tuple(
            dataclasses.replace(row, developing=None, blocker=None, timeframes=())
            for row in view.decisions
        ),
    )
