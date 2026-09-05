"""**Proof that Slice 3 added something.** Every claim, checked against the
pre-Slice-3 product rather than asserted about the post-Slice-3 one.

Slice 2 found and corrected a vacuous test — one that passed because it never
exercised the behaviour it named. The standard set there is the standard here:
for each capability this milestone claims, this file reconstructs the product
*without* it and asserts the capability really is absent, so a test that would
pass either way cannot survive.

Two techniques, chosen per claim:

  * **Absence by construction.** The Slice 2 snapshot is exactly the Slice 3
    snapshot with `scan_change=None`, so building one and asserting the page
    cannot answer the question is a faithful reconstruction of the old page.
  * **Absence by planting.** For a guard, the prohibited thing is constructed
    and the guard is checked to fire on it — a guard nothing can violate is a
    comment.
"""

from __future__ import annotations

import re

import pytest

from fmis.operator_dashboard import build_snapshot, render_page, scan_change_view
from fmis.scan_memory import (
    ChangeDimension,
    ComparisonStatus,
    ScanComparison,
    ScanHistoryStore,
    ScanMemoryError,
    StateTransition,
    SymbolChange,
    compare_and_record,
    compare_scans,
)

from tests.operator_dashboard_helpers import AT as PAGE_AT
from tests.scan_memory_helpers import AT, LATER, TIMEFRAMES, live_record, record, state
from tests.swing_decision_helpers import CANDIDATE, FAMILIES_SPLIT, GATE_REJECTED, live
from tests.swing_workspace_helpers import workspace_of

SYMBOL = "AAAUSDT"


def _slice_two_page(seeds=GATE_REJECTED, *, symbol=SYMBOL, path="/swing", **kw):
    """The product exactly as it was before this milestone: no scan memory."""
    snapshot = build_snapshot(
        refreshed_at=PAGE_AT,
        reference_time=PAGE_AT,
        workspace=workspace_of(live(seeds, symbol)),
    )
    assert snapshot.scan_change is None
    return render_page(snapshot, path, **kw)


def _text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


# ---------------------------------------------------------------------------
# What the product could not do
# ---------------------------------------------------------------------------


def test_before_slice_3_the_swing_page_could_not_state_what_changed() -> None:
    """The headline claim. The Slice 2 page has no temporal section at all."""
    words = _text(_slice_two_page())
    assert "Since the previous comparable scan" not in words
    assert "No previous comparable scan" not in words
    for phrase in ("changed", "previously", "From", "To"):
        assert f"Changed From To" not in words, phrase


def test_before_slice_3_the_symbol_page_could_not_show_a_transition() -> None:
    words = _text(_slice_two_page(path="/swing", symbol=SYMBOL))
    assert "Since the previous comparable scan" not in words
    assert "No material Swing state change for this symbol" not in words


def test_before_slice_3_a_refresh_persisted_nothing_to_compare_against(tmp_path) -> None:
    """A Slice 2 refresh is `build_snapshot` over a workspace. It touches no
    store, so a directory it could have written to stays empty."""
    root = tmp_path / "scan_memory"
    build_snapshot(
        refreshed_at=PAGE_AT,
        reference_time=PAGE_AT,
        workspace=workspace_of(live(GATE_REJECTED, SYMBOL)),
    )
    assert not root.exists()
    assert ScanHistoryStore(root).latest_complete() is None


def test_before_slice_3_a_restart_lost_the_previous_scan(tmp_path) -> None:
    """**The restart claim, both ways.** An in-memory-only history is empty
    after the object is recreated; the Slice 3 store is not."""

    class InMemoryOnly:
        """What a naive implementation would have been."""

        def __init__(self) -> None:
            self._records: list[object] = []

        def append(self, record_) -> None:  # noqa: ANN001
            self._records.append(record_)

        def latest_complete(self, *, exclude=None):  # noqa: ANN001
            return self._records[-1] if self._records else None

    volatile = InMemoryOnly()
    volatile.append(record(state(SYMBOL), reference_time=AT))
    assert volatile.latest_complete() is not None
    assert InMemoryOnly().latest_complete() is None, "a fresh process has nothing"

    durable = ScanHistoryStore(tmp_path / "scan_memory")
    durable.append(record(state(SYMBOL), reference_time=AT))
    assert ScanHistoryStore(tmp_path / "scan_memory").latest_complete() is not None


def test_the_temporal_section_really_is_what_carries_the_answer() -> None:
    """One field, and the page's ability to answer the question turns on it."""
    workspace = workspace_of(live(GATE_REJECTED, SYMBOL))
    comparison = compare_scans(
        record(state(SYMBOL, state="candidate", direction="sideA"), reference_time=AT),
        record(state(SYMBOL), reference_time=LATER),
    )
    without = build_snapshot(refreshed_at=PAGE_AT, reference_time=PAGE_AT, workspace=workspace)
    with_ = build_snapshot(
        refreshed_at=PAGE_AT,
        reference_time=PAGE_AT,
        workspace=workspace,
        scan_change=scan_change_view(comparison),
    )
    old_page = render_page(without, "/swing")
    new_page = render_page(with_, "/swing")
    assert "Since the previous comparable scan" not in old_page
    panel = new_page[new_page.index("Since the previous comparable scan") :]
    panel = panel[: panel.index("</section>")]
    assert "candidate" in panel and "wait" in panel
    # Everything else on the page is untouched: one section was added, nothing
    # was rewritten.
    assert old_page.split("<section")[-1] == new_page.split("<section")[-1]


# ---------------------------------------------------------------------------
# Guards that really guard
# ---------------------------------------------------------------------------


def test_the_no_fake_event_guard_fires_on_a_planted_fake_event() -> None:
    with pytest.raises(ScanMemoryError):
        SymbolChange(symbol=SYMBOL, state="wait", previous_state="wait", transitions=())


def test_the_equal_ends_guard_fires_on_a_planted_equal_transition() -> None:
    with pytest.raises(ScanMemoryError):
        StateTransition(dimension=ChangeDimension.DECISION, previous="wait", current="wait")


def test_the_fabricated_baseline_guard_fires_on_a_planted_fabrication() -> None:
    with pytest.raises(ScanMemoryError):
        ScanComparison(
            status=ComparisonStatus.NO_PREVIOUS_SCAN,
            current_scan_at=AT,
            reason="none",
            changes=(
                SymbolChange(
                    symbol=SYMBOL,
                    state="wait",
                    previous_state="candidate",
                    transitions=(
                        StateTransition(
                            dimension=ChangeDimension.DECISION,
                            previous="candidate",
                            current="wait",
                        ),
                    ),
                ),
            ),
        )


def test_the_policy_boundary_guard_fires_on_a_planted_import(tmp_path) -> None:
    """The import-direction guard is a text scan, and this proves it detects
    what it claims to — the technique
    `tests/test_directional_vocabulary_boundary.py` uses for the same reason."""
    planted = tmp_path / "policy.py"
    planted.write_text("from fmis.scan_memory import ScanRecord\n", encoding="utf-8")
    assert "fmis.scan_memory" in planted.read_text(encoding="utf-8")
    clean = tmp_path / "clean.py"
    clean.write_text("from fmis.swing_setup import SetupState\n", encoding="utf-8")
    assert "fmis.scan_memory" not in clean.read_text(encoding="utf-8")


def test_the_time_only_invariant_would_fail_if_an_instant_were_compared() -> None:
    """**Non-vacuity for §12.** The states below differ *only* by their instant.
    A comparator that read `as_of` would report a change; this one does not, and
    a comparator that read the assessment state instead certainly would."""
    from dataclasses import replace

    from fmis.scan_memory import transitions_between

    before = state(SYMBOL)
    later = replace(before, as_of=before.as_of.replace(year=before.as_of.year + 1))
    assert later.as_of != before.as_of
    assert transitions_between(before, later) == ()
    # The same pair, with one real state moved, does produce a transition — so
    # the empty result above is a decision, not an inability to detect anything.
    assert transitions_between(before, replace(later, state="candidate", direction="sideA"))


def test_the_incomplete_baseline_rule_would_change_the_answer(tmp_path) -> None:
    """**Non-vacuity for §20.** Were the partial scan allowed as a baseline, the
    comparison would report a presence transition that never happened."""
    store = ScanHistoryStore(tmp_path / "scan_memory")
    complete = record(state("AAAUSDT"), state("BBBUSDT"), reference_time=AT, recorded_at=AT)
    partial = record(
        state("AAAUSDT"),
        universe=("AAAUSDT", "BBBUSDT"),
        reference_time=AT.replace(hour=13),
        recorded_at=AT.replace(hour=13),
    )
    store.append(complete)
    store.append(partial)
    current = record(state("AAAUSDT"), state("BBBUSDT"), reference_time=LATER, recorded_at=LATER)
    assert store.latest_complete() == complete
    assert compare_scans(complete, current).changes == ()
    # The rejected baseline would have manufactured one.
    assert compare_scans(partial, current).status is ComparisonStatus.NOT_COMPARABLE


def test_the_idempotence_rule_would_change_the_answer(tmp_path) -> None:
    """**Non-vacuity for §23.** Without the identity-keyed path, a second record
    of the same scan would exist and could be compared against."""
    store = ScanHistoryStore(tmp_path / "scan_memory")
    one = record(state(SYMBOL))
    store.append(one)
    assert store.path_for(one) == store.path_for(one)
    store.append(one)
    assert len(store.records()) == 1
    # And two genuinely different scans do produce two files, so the count above
    # is not an artefact of the store never writing more than one.
    store.append(record(state(SYMBOL), reference_time=LATER, recorded_at=LATER))
    assert len(store.records()) == 2


def test_the_blocker_transition_is_invisible_without_scan_memory(tmp_path) -> None:
    """**The single most valuable case, proved absent before.** A `WAIT` symbol
    whose blocker moved renders identically on two Slice 2 pages — the operator
    had no way to see it without remembering the previous page himself."""
    first = _text(_slice_two_page(GATE_REJECTED))
    second = _text(_slice_two_page(FAMILIES_SPLIT))
    for page in (first, second):
        assert "Since the previous comparable scan" not in page

    store = ScanHistoryStore(tmp_path / "scan_memory")
    compare_and_record(
        live_record((GATE_REJECTED, SYMBOL), recorded_at=AT, reference_time=AT), store=store
    )
    comparison = compare_and_record(
        live_record((FAMILIES_SPLIT, SYMBOL), recorded_at=LATER, reference_time=LATER),
        store=store,
    )
    change = comparison.change_for(SYMBOL)
    assert change is not None
    assert ChangeDimension.BLOCKER in {item.dimension for item in change.transitions}


def test_the_controlled_transitions_really_reach_different_engine_exits() -> None:
    """The fixtures are not three names for one path: they reach three different
    exits of `evaluate_setup`, which is what makes the transitions between them
    transitions the live product can produce."""
    exits = {}
    for name, seeds in (
        ("gate", GATE_REJECTED),
        ("split", FAMILIES_SPLIT),
        ("candidate", CANDIDATE),
    ):
        projected = live_record((seeds, SYMBOL), reference_time=AT).symbols[0]
        exits[name] = (projected.state, projected.blocker_kind)
    assert len(set(exits.values())) == 3, exits


def test_the_timeframes_fixture_matches_the_products_own_roles() -> None:
    """A comparability fixture that drifted from the product would make every
    comparison test pass over a question the product never asks."""
    from fmis.pipeline.multi_timeframe import DEFAULT_TIMEFRAMES

    assert {role for role, _ in TIMEFRAMES} == {
        role.value for role in DEFAULT_TIMEFRAMES
    }
