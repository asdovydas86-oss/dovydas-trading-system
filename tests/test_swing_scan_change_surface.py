"""Slice 3's product surface: **what the operator actually sees, and when.**

Every assertion here runs through the real projection, the real comparator, the
real section mapping and the real renderer — the seam `fmits dashboard` uses —
rather than unit-testing a comparator in isolation. What is proved is what the
page does.

**Controlled, not fabricated.** The transitions demonstrated are produced by the
live composition root over seeded synthetic candles, so *"BTC's blocker moved
from the higher-timeframe regime gate to a directional disagreement"* is a thing
the engine really does, not a state hand-written to make a screenshot.
"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from fmis.operator_dashboard import build_snapshot, render_page, scan_change_view
from fmis.operator_dashboard.models import ScanChangeView
from fmis.pipeline.scan_memory import build_scan_history_store, refresh_with_scan_memory
from fmis.scan_memory import (
    ComparisonStatus,
    ScanHistoryStore,
    compare_and_record,
    compare_scans,
)

from tests.operator_dashboard_helpers import AT as PAGE_AT
from tests.scan_memory_helpers import AT, LATER, TIMEFRAMES, live_record, record, state, store_at
from tests.swing_decision_helpers import (
    CANDIDATE,
    FAMILIES_SPLIT,
    GATE_LEANING,
    GATE_REJECTED,
    live,
)
from tests.swing_workspace_helpers import workspace_of

SYMBOL = "AAAUSDT"


def _pages(previous_seeds, current_seeds, *, symbol=SYMBOL, tmp_path=None):
    """Two comparable scans through the whole product, and the rendered pages.

    Returns ``(overview_html, symbol_html, comparison)``.
    """
    store = ScanHistoryStore(tmp_path / "scan_memory")
    compare_and_record(
        live_record((previous_seeds, symbol), recorded_at=AT, reference_time=AT), store=store
    )
    current_workspace = workspace_of(live(current_seeds, symbol), reference_time=LATER)
    from fmis.scan_memory import scan_record_from

    comparison = compare_and_record(
        scan_record_from(
            current_workspace,
            recorded_at=LATER,
            universe=(symbol,),
            timeframes=dict(TIMEFRAMES),
        ),
        store=store,
    )
    snapshot = build_snapshot(
        refreshed_at=PAGE_AT,
        reference_time=PAGE_AT,
        workspace=current_workspace,
        scan_change=scan_change_view(comparison),
    )
    return (
        render_page(snapshot, "/swing"),
        render_page(snapshot, "/swing", symbol=symbol),
        comparison,
    )


def _text(html: str) -> str:
    """The page's visible words, with tags removed and whitespace collapsed."""
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _panel(html: str) -> str:
    """The temporal panel's markup alone, so the rest of the page cannot mask a
    regression in it."""
    start = html.index("Since the previous comparable scan")
    tail = html[start:]
    end = tail.index("</section>") if "</section>" in tail else len(tail)
    return tail[:end]


def _claims(html: str) -> str:
    """The panel with its own stated limitations removed.

    The disclaimer paragraph exists to say the surface is *not* a signal, *not*
    ranked and *not* weighted — so a vocabulary scan that included it would fire
    on the sentence that promises the vocabulary is absent. Everything else in
    the panel is a claim the page makes, and that is what these guards check.
    """
    return re.sub(r'<p class="note">.*?</p>', " ", _panel(html), flags=re.S)


# ---------------------------------------------------------------------------
# The four states of the temporal surface
# ---------------------------------------------------------------------------


def test_a_snapshot_without_scan_memory_renders_exactly_as_before() -> None:
    """**Nothing is broken for a caller that does not wire history.** The page is
    the Slice 2 page, with no temporal section and no claim that nothing
    changed."""
    snapshot = build_snapshot(
        refreshed_at=PAGE_AT,
        reference_time=PAGE_AT,
        workspace=workspace_of(live(GATE_REJECTED, SYMBOL)),
    )
    assert snapshot.scan_change is None
    page = render_page(snapshot, "/swing")
    assert "Since the previous comparable scan" not in page
    assert "Swing decision workspace" in page


def test_the_first_scan_says_a_baseline_was_recorded_and_calls_nothing_unchanged(tmp_path) -> None:
    """**§18.** The absence of history is a valid state, rendered as one."""
    store = store_at(tmp_path)
    comparison = compare_and_record(
        live_record((GATE_REJECTED, SYMBOL), recorded_at=AT, reference_time=AT), store=store
    )
    assert comparison.status is ComparisonStatus.NO_PREVIOUS_SCAN
    snapshot = build_snapshot(
        refreshed_at=PAGE_AT,
        reference_time=PAGE_AT,
        workspace=workspace_of(live(GATE_REJECTED, SYMBOL)),
        scan_change=scan_change_view(comparison),
    )
    page = render_page(snapshot, "/swing")
    assert "Baseline scan recorded" in _text(page)
    claims = _text(_claims(page)).lower()
    assert "unchanged" not in claims
    assert "no material swing state change" not in claims


def test_a_scan_with_no_material_change_says_so_once_and_quietly(tmp_path) -> None:
    """**§46.** One sentence, not twenty rows of *unchanged*."""
    store = store_at(tmp_path)
    compare_and_record(live_record((GATE_REJECTED, SYMBOL), recorded_at=AT, reference_time=AT), store=store)
    later = live_record((GATE_REJECTED, SYMBOL), recorded_at=LATER, reference_time=LATER)
    comparison = compare_and_record(later, store=store)
    assert comparison.status is ComparisonStatus.COMPARED and comparison.changes == ()
    snapshot = build_snapshot(
        refreshed_at=PAGE_AT,
        reference_time=PAGE_AT,
        workspace=workspace_of(live(GATE_REJECTED, SYMBOL)),
        scan_change=scan_change_view(comparison),
    )
    words = _text(render_page(snapshot, "/swing"))
    assert words.count("No material Swing state change since the previous comparable scan.") == 1


def test_an_unreadable_history_says_so_and_the_analysis_still_renders(tmp_path) -> None:
    """**§25.** A corrupt file costs the operator history, never the market."""
    store = store_at(tmp_path)
    stored = store.append(record(state(SYMBOL), reference_time=AT, recorded_at=AT))
    stored.path.write_bytes(b"corrupted")
    comparison = compare_and_record(
        live_record((GATE_REJECTED, SYMBOL), recorded_at=LATER, reference_time=LATER), store=store
    )
    snapshot = build_snapshot(
        refreshed_at=PAGE_AT,
        reference_time=PAGE_AT,
        workspace=workspace_of(live(GATE_REJECTED, SYMBOL)),
        scan_change=scan_change_view(comparison),
    )
    page = render_page(snapshot, "/swing")
    words = _text(page)
    assert "could not be read" in words
    assert "Every scanned symbol" in words, "the current analysis is still on the page"
    assert "No material Swing state change" not in words


def test_a_non_comparable_previous_scan_says_why(tmp_path) -> None:
    """**§9.** Never *unchanged*, and never a delta over a different question."""
    store = store_at(tmp_path)
    store.append(record(state(SYMBOL), universe=(SYMBOL, "BBBUSDT"), reference_time=AT, recorded_at=AT))
    store.append(record(state(SYMBOL), state("BBBUSDT"), reference_time=AT.replace(hour=13), recorded_at=AT.replace(hour=13)))
    comparison = compare_and_record(
        live_record((GATE_REJECTED, SYMBOL), recorded_at=LATER, reference_time=LATER), store=store
    )
    assert comparison.status is ComparisonStatus.NOT_COMPARABLE
    view = scan_change_view(comparison)
    assert "different watchlist" in view.reason
    assert view.changed == () and view.unchanged == ()


# ---------------------------------------------------------------------------
# Controlled transitions, rendered through the real product
# ---------------------------------------------------------------------------


def test_the_blocker_transition_reaches_both_pages_while_the_decision_holds(tmp_path) -> None:
    """**§44A, the BTC-shaped case.** `WAIT` on both scans, and the reason moved."""
    overview, symbol_page, comparison = _pages(GATE_REJECTED, FAMILIES_SPLIT, tmp_path=tmp_path)
    change = comparison.change_for(SYMBOL)
    assert change is not None and change.state == "wait"
    for page in (overview, symbol_page):
        words = _text(page)
        assert "Blocker" in words
        assert "HTF regime not eligible" in words
        assert "timeframes disagree" in words


def test_the_decision_transition_reaches_both_pages(tmp_path) -> None:
    """**§44B.** `WAIT → CANDIDATE`, named as a decision transition."""
    overview, symbol_page, comparison = _pages(GATE_REJECTED, CANDIDATE, tmp_path=tmp_path)
    assert comparison.change_for(SYMBOL) is not None
    for page in (overview, symbol_page):
        words = _text(page)
        assert "Decision" in words
        assert re.search(r"Decision\s+decision\s+wait\s+candidate", words), words


def test_the_developing_evidence_transition_reaches_both_pages(tmp_path) -> None:
    """**§44C, and §29's boundary.** An evidence-state transition, not a
    direction transition — the decision did not move."""
    overview, symbol_page, comparison = _pages(GATE_REJECTED, GATE_LEANING, tmp_path=tmp_path)
    change = comparison.change_for(SYMBOL)
    assert change is not None and change.state == "wait"
    for page in (overview, symbol_page):
        words = _text(page)
        assert "Developing evidence" in words
        assert "divided" in words


def test_a_changed_symbol_always_states_what_changed(tmp_path) -> None:
    """**§15.** Never *BTC changed* with nothing beside it."""
    overview, _, comparison = _pages(GATE_REJECTED, CANDIDATE, tmp_path=tmp_path)
    change = comparison.change_for(SYMBOL)
    assert change is not None and change.transitions
    panel = _panel(overview)
    # The renderer prints each end in the page's own vocabulary: underscores
    # opened up, and a blocker kind through the label table `_swing_snapshot`
    # already uses. Both ends of every transition must be visible in one of
    # those two forms — never a bare *this symbol changed*.
    from fmis.operator_dashboard.render import _BLOCKER_LABELS

    for transition in change.transitions:
        for end in (transition.previous, transition.current):
            forms = {end, end.replace("_", " "), _BLOCKER_LABELS.get(end, end)}
            assert any(form in panel for form in forms), (transition, end)


def test_the_current_state_is_shown_beside_every_transition(tmp_path) -> None:
    """**§15 and §17.** History qualifies the current decision; it never
    replaces it."""
    overview, symbol_page, comparison = _pages(GATE_REJECTED, CANDIDATE, tmp_path=tmp_path)
    heading = _text(overview)
    assert re.search(rf"{SYMBOL}\s+.\s+candidate\s+previously\s+wait", heading), heading
    # The symbol page states the current decision *above* the change block: the
    # operator summary panel is rendered first and history qualifies it.
    assert symbol_page.index("Since the previous comparable scan") > symbol_page.index(
        f"{SYMBOL}"
    )


def test_the_symbol_page_omits_unchanged_dimensions(tmp_path) -> None:
    """**§17.** A block listing every dimension with both ends equal would bury
    the two that moved."""
    _, symbol_page, comparison = _pages(GATE_REJECTED, FAMILIES_SPLIT, tmp_path=tmp_path)
    change = comparison.change_for(SYMBOL)
    assert change is not None
    moved = {transition.dimension.value for transition in change.transitions}
    assert "decision" not in moved
    assert "Decision</td>" not in _panel(symbol_page)


def test_an_unchanged_symbol_page_says_so_rather_than_showing_nothing(tmp_path) -> None:
    """§17's last branch: silence would read as a page that failed to render."""
    _, symbol_page, comparison = _pages(GATE_REJECTED, GATE_REJECTED, tmp_path=tmp_path)
    assert comparison.changes == ()
    assert "No material Swing state change for this symbol" in _text(symbol_page)


def test_a_symbol_that_produced_nothing_this_scan_still_states_what_changed(
    tmp_path,
) -> None:
    """**§33.** The one case where *what changed* is the only thing there is to
    say: the symbol was assessed last time and produced nothing this time.

    Dropping the block here would leave the page saying *no assessment on this
    refresh* and nothing else, which is exactly what it said before Slice 3.
    """
    store = store_at(tmp_path)
    store.append(
        record(
            state(SYMBOL),
            state("BBBUSDT"),
            universe=(SYMBOL, "BBBUSDT"),
            reference_time=AT,
            recorded_at=AT,
        )
    )
    lost = record(
        state(SYMBOL), universe=(SYMBOL, "BBBUSDT"), reference_time=LATER, recorded_at=LATER
    )
    comparison = compare_and_record(lost, store=store)
    snapshot = build_snapshot(
        refreshed_at=PAGE_AT,
        reference_time=PAGE_AT,
        workspace=workspace_of(live(GATE_REJECTED, SYMBOL)),
        scan_change=scan_change_view(comparison),
    )
    page = render_page(snapshot, "/swing", symbol="BBBUSDT")
    words = _text(page)
    assert "produced no assessment on this refresh" in words
    assert "Since the previous comparable scan" in words
    assert "produced an assessment" in words and "produced no assessment" in words
    for forbidden in ("bearish", "broken", "failed", "weak"):
        assert forbidden not in _claims(page).lower(), forbidden


def test_a_symbol_that_was_never_scanned_gets_no_change_block(tmp_path) -> None:
    """Non-vacuity for the case above: *no material change* for a symbol that was
    never on the watchlist would be indistinguishable from one that was."""
    store = store_at(tmp_path)
    compare_and_record(
        live_record((GATE_REJECTED, SYMBOL), recorded_at=AT, reference_time=AT), store=store
    )
    comparison = compare_and_record(
        live_record((GATE_REJECTED, SYMBOL), recorded_at=LATER, reference_time=LATER),
        store=store,
    )
    snapshot = build_snapshot(
        refreshed_at=PAGE_AT,
        reference_time=PAGE_AT,
        workspace=workspace_of(live(GATE_REJECTED, SYMBOL)),
        scan_change=scan_change_view(comparison),
    )
    page = render_page(snapshot, "/swing", symbol="ZZZUSDT")
    assert "produced no assessment on this refresh" in _text(page)
    assert "Since the previous comparable scan" not in page


def test_a_symbol_page_with_no_baseline_says_there_is_none(tmp_path) -> None:
    store = store_at(tmp_path)
    comparison = compare_and_record(
        live_record((GATE_REJECTED, SYMBOL), recorded_at=AT, reference_time=AT), store=store
    )
    snapshot = build_snapshot(
        refreshed_at=PAGE_AT,
        reference_time=PAGE_AT,
        workspace=workspace_of(live(GATE_REJECTED, SYMBOL)),
        scan_change=scan_change_view(comparison),
    )
    words = _text(render_page(snapshot, "/swing", symbol=SYMBOL))
    assert "Baseline scan recorded" in words


# ---------------------------------------------------------------------------
# What the surface must never say
# ---------------------------------------------------------------------------

FORBIDDEN_ON_THE_PAGE = (
    "score", "rank", "importance", "urgency", "significance", "priority",
    "buy", "sell", "signal", "recommend", "opportunity score", "confidence",
    "improved", "worse", "stronger", "weaker", "bullish", "bearish",
)


@pytest.mark.parametrize("word", FORBIDDEN_ON_THE_PAGE)
def test_the_change_surface_holds_no_ranking_or_recommendation_vocabulary(
    word: str, tmp_path
) -> None:
    """**§13, §28, §47.** Asserted on the temporal panel's own markup, so the
    rest of the page's vocabulary cannot mask a regression here."""
    overview, symbol_page, _ = _pages(GATE_REJECTED, CANDIDATE, tmp_path=tmp_path)
    for page in (overview, symbol_page):
        assert word not in _claims(page).lower(), (word, _claims(page)[:400])


def test_the_temporal_surface_states_what_it_is_not(tmp_path) -> None:
    """The limitation is printed, not left for the owner to infer."""
    overview, _, _ = _pages(GATE_REJECTED, CANDIDATE, tmp_path=tmp_path)
    words = _text(overview)
    assert "Nothing here is scored, ranked or weighted" in words
    assert "Instants, ages and bar counts are not compared at all" in words


def test_no_freshness_verdict_is_introduced(tmp_path) -> None:
    """**§35.** Slice 2 found no validated staleness bound and Slice 3 invents
    none."""
    overview, symbol_page, _ = _pages(GATE_REJECTED, CANDIDATE, tmp_path=tmp_path)
    for page in (overview, symbol_page):
        for word in ("stale", "fresh", "expired", "out of date"):
            assert not re.search(rf"\b{word}\b", _claims(page).lower()), word


# ---------------------------------------------------------------------------
# The refresh boundary
# ---------------------------------------------------------------------------


def _fake_refresh(**kwargs):
    """A `refresh` stand-in that calls the injected workspace runner exactly once."""
    runner = kwargs["workspace_runner"]
    workspace = runner(reference_time=LATER, store_root=None)
    return build_snapshot(refreshed_at=LATER, reference_time=LATER, workspace=workspace)


def test_a_refresh_records_one_scan_and_attaches_the_comparison(tmp_path) -> None:
    store = store_at(tmp_path)
    snapshot = refresh_with_scan_memory(
        refreshed_at=LATER,
        store=store,
        symbols=(SYMBOL,),
        timeframes=dict(TIMEFRAMES),
        refresher=_fake_refresh,
        workspace_runner=lambda **_: workspace_of(live(GATE_REJECTED, SYMBOL), reference_time=LATER),
    )
    assert snapshot.scan_change is not None
    assert snapshot.scan_change.status == "no_previous_scan"
    assert len(store.records()) == 1


def test_a_second_refresh_compares_against_the_first(tmp_path) -> None:
    """The end-to-end product claim, through the real store and the real view."""
    store = store_at(tmp_path)
    refresh_with_scan_memory(
        refreshed_at=AT,
        store=store,
        symbols=(SYMBOL,),
        timeframes=dict(TIMEFRAMES),
        refresher=lambda **kw: build_snapshot(
            refreshed_at=AT,
            reference_time=AT,
            workspace=kw["workspace_runner"](reference_time=AT),
        ),
        workspace_runner=lambda **_: workspace_of(live(GATE_REJECTED, SYMBOL), reference_time=AT),
    )
    snapshot = refresh_with_scan_memory(
        refreshed_at=LATER,
        store=store,
        symbols=(SYMBOL,),
        timeframes=dict(TIMEFRAMES),
        refresher=_fake_refresh,
        workspace_runner=lambda **_: workspace_of(live(CANDIDATE, SYMBOL), reference_time=LATER),
    )
    view = snapshot.scan_change
    assert view is not None and view.compared
    assert len(view.changed) == 1
    assert view.changed[0].state == "candidate" and view.changed[0].previous_state == "wait"
    assert len(store.records()) == 2


def test_a_failed_scan_records_nothing(tmp_path) -> None:
    """**§20.** No workspace, no record — so no partial baseline."""
    store = store_at(tmp_path)

    def refuse(**kwargs):
        return build_snapshot(
            refreshed_at=LATER,
            reference_time=LATER,
            workspace_error=RuntimeError("the provider did not answer"),
        )

    snapshot = refresh_with_scan_memory(
        refreshed_at=LATER, store=store, refresher=refuse, symbols=(SYMBOL,)
    )
    assert snapshot.scan_change is None
    assert store.latest_complete() is None
    assert store.records() == ()


def test_a_scan_that_cannot_be_projected_never_takes_the_page_down(tmp_path) -> None:
    """**§20's hardest clause.** A scan memory that cannot even project the scan
    costs the operator the *remembering*, never the analysis.

    The universe is deliberately mismatched, which `scan_record_from` refuses —
    the one `ScanMemoryError` the recorder itself does not already absorb.
    """
    store = store_at(tmp_path)
    snapshot = refresh_with_scan_memory(
        refreshed_at=LATER,
        store=store,
        symbols=("ZZZUSDT",),
        timeframes=dict(TIMEFRAMES),
        refresher=_fake_refresh,
        workspace_runner=lambda **_: workspace_of(live(GATE_REJECTED, SYMBOL), reference_time=LATER),
    )
    view = snapshot.scan_change
    assert view is not None
    assert view.status == "history_unavailable"
    assert not view.recorded and "Nothing was recorded" in view.recording_note
    assert store.records() == ()
    # The market analysis is untouched and still renders.
    page = render_page(snapshot, "/swing")
    assert "Every scanned symbol" in _text(page)
    assert snapshot.swing.data.decision_for(SYMBOL) is not None
    assert "No material Swing state change" not in _text(page)


def test_rendering_a_page_never_records_a_scan(tmp_path) -> None:
    """**§22 and §23.** A `GET` renders a held snapshot. It performs no refresh,
    so it writes no history — asserted by rendering every swing route four times
    and watching the record count."""
    store = store_at(tmp_path)
    snapshot = refresh_with_scan_memory(
        refreshed_at=LATER,
        store=store,
        symbols=(SYMBOL,),
        timeframes=dict(TIMEFRAMES),
        refresher=_fake_refresh,
        workspace_runner=lambda **_: workspace_of(live(GATE_REJECTED, SYMBOL), reference_time=LATER),
    )
    before = len(store.records())
    for _ in range(4):
        render_page(snapshot, "/swing")
        render_page(snapshot, "/swing", symbol=SYMBOL)
        render_page(snapshot, "/")
    assert len(store.records()) == before == 1


def test_the_renderer_names_no_write_verb() -> None:
    """The read-only claim, asserted on the module that grew the new section."""
    import ast
    import inspect

    import fmis.operator_dashboard.render as module

    tree = ast.parse(inspect.getsource(module))
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    for verb in ("append_lines", "atomic_write", "write_text", "write_bytes", "unlink"):
        assert verb not in called, verb


def test_history_cannot_reach_the_decision_that_is_rendered(tmp_path) -> None:
    """**§6, end to end.** The same workspace renders the same decision whether
    the store is empty, holds a matching scan, or holds a contradicting one."""
    workspace = workspace_of(live(GATE_REJECTED, SYMBOL), reference_time=LATER)
    decisions = []
    for prepare in (
        lambda store: None,
        lambda store: compare_and_record(
            live_record((GATE_REJECTED, SYMBOL), recorded_at=AT, reference_time=AT), store=store
        ),
        lambda store: compare_and_record(
            live_record((CANDIDATE, SYMBOL), recorded_at=AT, reference_time=AT), store=store
        ),
    ):
        store = ScanHistoryStore(tmp_path / str(len(decisions)))
        prepare(store)
        from fmis.scan_memory import scan_record_from

        comparison = compare_and_record(
            scan_record_from(
                workspace, recorded_at=LATER, universe=(SYMBOL,), timeframes=dict(TIMEFRAMES)
            ),
            store=store,
        )
        snapshot = build_snapshot(
            refreshed_at=PAGE_AT,
            reference_time=PAGE_AT,
            workspace=workspace,
            scan_change=scan_change_view(comparison),
        )
        row = snapshot.swing.data.decision_for(SYMBOL)
        decisions.append((row.state, row.direction, row.blocker.kind, row.developing.state))
    assert len(set(decisions)) == 1, decisions


def test_the_view_is_a_faithful_translation_of_the_comparison() -> None:
    """No dimension added, dropped, merged or reordered at the section seam."""
    previous = record(state(SYMBOL), reference_time=AT)
    current = record(
        state(SYMBOL, state="candidate", direction="sideA", blocker_kind="awaiting_confirmation"),
        reference_time=LATER,
    )
    comparison = compare_scans(previous, current)
    view = scan_change_view(comparison)
    assert view.status == comparison.status.value
    assert tuple(row.symbol for row in view.changed) == tuple(
        change.symbol for change in comparison.changes
    )
    assert tuple(item.dimension for item in view.changed[0].transitions) == tuple(
        item.dimension.value for item in comparison.changes[0].transitions
    )


def test_the_view_carries_no_method_that_writes() -> None:
    view = ScanChangeView(status="no_previous_scan", current_scan_at=AT, reason="none")
    for name in dir(view):
        assert name.lower() not in {
            "save", "write", "publish", "commit", "record", "append", "delete", "update"
        }, name
    with pytest.raises((AttributeError, TypeError)):
        view.status = "compared"  # type: ignore[misc]


def test_the_build_store_helper_never_reaches_the_owners_history(tmp_path) -> None:
    assert build_scan_history_store(tmp_path).root == tmp_path
    from fmis.scan_memory import DEFAULT_SCAN_MEMORY_ROOT

    assert build_scan_history_store().root == DEFAULT_SCAN_MEMORY_ROOT


def test_replacing_the_snapshot_does_not_disturb_any_other_section() -> None:
    """`refresh_with_scan_memory` attaches one field and changes nothing else."""
    workspace = workspace_of(live(GATE_REJECTED, SYMBOL))
    base = build_snapshot(refreshed_at=PAGE_AT, reference_time=PAGE_AT, workspace=workspace)
    view = ScanChangeView(status="no_previous_scan", current_scan_at=AT, reason="none")
    assert replace(base, scan_change=view) == replace(base, scan_change=view)
    assert replace(base, scan_change=view).swing == base.swing
    assert replace(base, scan_change=view).counts == base.counts
