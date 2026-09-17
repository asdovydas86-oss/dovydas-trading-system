"""Slice 2 — the operator decision layer.

Slice 1 made every scanned symbol's evidence reachable. The operator then used
it, and reported the next problem: the page answered an **audit** question
before it answered a **trading** one. Understanding BTCUSDT meant reading a long
technical record to recover four facts — what was decided, which way the
readable evidence points, what is holding it, and how old the data is.

Slice 2 puts those four above the audit. It removes nothing.

**The distinction these tests exist to protect.** A `WAIT` result means the
policy formed no directional candidate, and that is final for the reading. The
three families it tallies can still all lean one way — because the gate before
the tally rejected the symbol. Reporting only *"WAIT, direction unavailable"*
discards a computed fact; reporting *"LONG"* contradicts the policy. So the
product reports **developing evidence**, in its own vocabulary, always beside
the decision, and never as a signal. Several tests below do nothing but hold
that line.

Offline and deterministic throughout: assessments come from the real
composition root over `archive_helpers.multi`'s seeded synthetic candles. No
provider, no clock, no filesystem, no network.
"""

from __future__ import annotations

import dataclasses
import html as html_module
import re
from datetime import datetime, timedelta, timezone

import pytest

from fmis.operator_dashboard import render_page
from fmis.operator_dashboard.render import _IndependenceNotes
from fmis.operator_dashboard.models import (
    BlockerRow,
    DevelopingEvidenceRow,
    SwingSnapshot,
    TimeframeRow,
)
from fmis.swing_setup import (
    BlockerKind,
    DevelopingEvidenceState,
    SetupState,
    summarise_decision,
)
from fmis.swing_setup.policy import CONTEXT_ROLE_STRUCTURE_REQUIREMENT
from fmis.swing_workspace import symbol_decisions

from tests.swing_decision_helpers import (
    CANDIDATE,
    FAMILIES_SPLIT,
    GATE_LEANING,
    GATE_REJECTED,
    live,
    snapshot_of,
    workspace_of,
)
from tests.swing_workspace_helpers import REFERENCE, failed_result

BTC_SHAPED = GATE_LEANING
BNB_SHAPED = FAMILIES_SPLIT


def summary_of(seeds: tuple[int, int, int], symbol: str = "AAAUSDT"):
    """The decision summary for one fixture, through the real projection."""
    result = live(seeds, symbol)
    return summarise_decision(result.assessment, result.readings)


def decision_of(seeds: tuple[int, int, int], symbol: str = "AAAUSDT"):
    """One workspace decision record, with per-role ages measured at REFERENCE."""
    return symbol_decisions([live(seeds, symbol)], reference_time=REFERENCE)[0]


# ===========================================================================
# 1. Developing evidence — a reading, never a decision
# ===========================================================================


def test_a_waiting_symbol_whose_families_all_lean_one_way_is_reported_as_leaning() -> None:
    """The BTC-shaped case. Evidence is developing; the policy still says WAIT."""
    summary = summary_of(BTC_SHAPED)
    assert summary.state is SetupState.WAIT
    assert summary.direction is None
    assert summary.developing.state is DevelopingEvidenceState.LEANING
    assert summary.developing.lean is not None
    # And it names the families that produced that description.
    assert summary.developing.agreeing
    assert not summary.developing.opposing


def test_a_leaning_summary_never_promotes_the_decision() -> None:
    """**The central invariant of this milestone.**

    Developing evidence and the policy's state are different dimensions, and no
    value of the first may change the second.
    """
    summary = summary_of(BTC_SHAPED)
    assert summary.state is SetupState.WAIT
    assert summary.state is not SetupState.CANDIDATE
    assert summary.state is not SetupState.CONFIRMED
    # The assessment itself is untouched by having been summarised.
    assert live(BTC_SHAPED, "AAAUSDT").assessment.state is SetupState.WAIT


def test_the_summary_cannot_represent_a_leaning_wait_as_a_stated_direction() -> None:
    """`DIRECTION_STATED` is reserved for a direction the policy actually stated.

    Enforced on the type, not merely by the function that builds it, so a second
    producer cannot assemble the contradiction.
    """
    summary = summary_of(BTC_SHAPED)
    with pytest.raises(Exception) as caught:
        dataclasses.replace(
            summary,
            developing=dataclasses.replace(
                summary.developing,
                state=DevelopingEvidenceState.DIRECTION_STATED,
            ),
        )
    assert "DIRECTION_STATED" in str(caught.value)


def test_a_summary_cannot_carry_a_direction_the_assessment_does_not() -> None:
    summary = summary_of(BTC_SHAPED)
    with pytest.raises(Exception) as caught:
        dataclasses.replace(summary, direction=summary.developing.lean)
    assert "direction is None if and only if state is WAIT" in str(caught.value)


def test_divided_families_produce_no_lean_at_all() -> None:
    """The BNB-shaped case. Neither side is named, because neither won."""
    summary = summary_of(BNB_SHAPED)
    assert summary.developing.state is DevelopingEvidenceState.DIVIDED
    assert summary.developing.lean is None
    assert summary.developing.opposing


def test_a_stated_direction_is_the_policys_own_and_is_never_re_derived() -> None:
    result = live(CANDIDATE, "AAAUSDT")
    summary = summarise_decision(result.assessment, result.readings)
    assert summary.developing.state is DevelopingEvidenceState.DIRECTION_STATED
    assert summary.developing.lean is result.assessment.direction


def test_a_family_that_cast_no_vote_is_reported_as_non_voting_not_as_a_side() -> None:
    """`CONFLICTING` and `UNAVAILABLE` are not votes, for different reasons."""
    summary = summary_of(BTC_SHAPED)
    voting = set(summary.developing.agreeing) | set(summary.developing.opposing)
    non_voting = set(summary.developing.non_voting)
    assert not voting & non_voting
    families = {
        factor.family
        for factor in live(BTC_SHAPED, "AAAUSDT").assessment.directional_factors
    }
    assert voting | non_voting == families


def test_every_summarised_family_is_traceable_to_a_factor_on_the_assessment() -> None:
    """§18: no summarised conclusion without a path to the evidence behind it."""
    for seeds in (BTC_SHAPED, BNB_SHAPED, CANDIDATE, GATE_REJECTED):
        result = live(seeds, "AAAUSDT")
        summary = summarise_decision(result.assessment, result.readings)
        named = (
            set(summary.developing.agreeing)
            | set(summary.developing.opposing)
            | set(summary.developing.non_voting)
        )
        actual = {f.family for f in result.assessment.directional_factors}
        assert named <= actual, (seeds, named - actual)


# ===========================================================================
# 2. The named blocker — the policy's own path
# ===========================================================================


def test_the_regime_gate_and_the_family_split_are_different_named_blockers() -> None:
    assert (
        summary_of(BTC_SHAPED).blocker.kind
        is BlockerKind.CONTEXT_REGIME_NOT_ELIGIBLE
    )
    assert (
        summary_of(BNB_SHAPED).blocker.kind
        is BlockerKind.DIRECTIONAL_FAMILIES_DISAGREE
    )
    assert summary_of(CANDIDATE).blocker.kind is BlockerKind.AWAITING_CONFIRMATION


def test_the_blocker_states_the_requirement_the_existing_gate_already_demands() -> None:
    """§12: restate the policy's own condition, never invent a price."""
    blocker = summary_of(BTC_SHAPED).blocker
    assert CONTEXT_ROLE_STRUCTURE_REQUIREMENT.value in blocker.requirement
    assert blocker.observed  # the value that failed it, in the engine's words
    assert blocker.observed != CONTEXT_ROLE_STRUCTURE_REQUIREMENT.value


def test_the_blocker_requirement_never_invents_a_price_or_a_date() -> None:
    """No level, no target, no deadline — for any fixture, on any exit."""
    money = re.compile(r"[$€£]|\b\d+[.,]\d{2}\b")
    for seeds in (BTC_SHAPED, BNB_SHAPED, GATE_REJECTED):
        blocker = summary_of(seeds).blocker
        for text in (blocker.statement, blocker.requirement):
            assert not money.search(text), (seeds, text)
            for word in ("will ", "expect", "likely", "soon", "predict"):
                assert word not in text.lower(), (seeds, word)


def test_a_result_without_readings_says_so_rather_than_guessing_the_exit() -> None:
    """§18 again: no inference from prose when the structured fact is absent.

    Two of the three `WAIT` exits are told apart by the context-role regime
    state. A result carrying none reports `UNDETERMINED` — it does not recover
    the answer by reading the thesis sentence the policy wrote.
    """
    bare = live(BTC_SHAPED, "AAAUSDT", readings=False)
    assert bare.readings is None
    summary = summarise_decision(bare.assessment, bare.readings)
    assert summary.blocker.kind is BlockerKind.UNDETERMINED
    # …while the same assessment with its readings names the real exit.
    assert (
        summary_of(BTC_SHAPED).blocker.kind
        is BlockerKind.CONTEXT_REGIME_NOT_ELIGIBLE
    )


def test_the_named_blocker_agrees_with_the_policys_own_sentence_everywhere() -> None:
    """**The anti-drift guard.**

    `_blocker` walks the same three exits `evaluate_setup` walks. If the policy
    ever changes one and this projection does not, the two describe different
    things — so every fixture in the matrix is checked against the sentence the
    policy itself wrote for it.
    """
    marker = {
        BlockerKind.DECISION_CONTEXT_INSUFFICIENT: "Decision context is INSUFFICIENT",
        BlockerKind.CONTEXT_REGIME_NOT_ELIGIBLE: "not trending",
        BlockerKind.DIRECTIONAL_FAMILIES_DISAGREE: "do not agree",
    }
    checked: list[BlockerKind] = []
    for context in (1, 2, 3):
        for setup in (4, 5, 6):
            for execution in (7, 8, 9):
                result = live((context, setup, execution), "AAAUSDT")
                summary = summarise_decision(result.assessment, result.readings)
                expected = marker.get(summary.blocker.kind)
                if expected is None:
                    continue
                thesis = result.assessment.thesis[0]
                assert expected in thesis, (
                    (context, setup, execution),
                    summary.blocker.kind,
                    thesis[:80],
                )
                checked.append(summary.blocker.kind)
    # 27 seed triples: 24 reach a WAIT exit and 3 reach a candidate. The guard
    # is worth nothing if the matrix stops covering both WAIT exits, so the
    # *kinds* are asserted rather than only the count.
    assert len(checked) == 24, len(checked)
    assert set(checked) == {
        BlockerKind.CONTEXT_REGIME_NOT_ELIGIBLE,
        BlockerKind.DIRECTIONAL_FAMILIES_DISAGREE,
    }


# ===========================================================================
# 3. Per-role freshness — instants and ages, and no verdict
# ===========================================================================


def test_each_timeframe_role_keeps_its_own_reading_instant() -> None:
    decision = decision_of(BTC_SHAPED)
    assert [line.role for line in decision.timeframes] == [
        "context",
        "setup",
        "execution",
    ]
    assert [line.interval for line in decision.timeframes] == ["1w", "1d", "4h"]
    for line in decision.timeframes:
        assert line.as_of.tzinfo is not None
        assert line.closed_count > 0


def test_the_age_is_measured_against_the_pages_own_instant() -> None:
    decision = decision_of(BTC_SHAPED)
    for line in decision.timeframes:
        assert line.age == REFERENCE - line.as_of


def test_a_missing_reference_yields_instants_with_no_age_rather_than_no_instants() -> None:
    decision = symbol_decisions([live(BTC_SHAPED, "AAAUSDT")], reference_time=None)[0]
    assert decision.timeframes
    assert all(line.age is None for line in decision.timeframes)


def test_a_result_with_no_readings_carries_no_invented_instant() -> None:
    decision = symbol_decisions(
        [live(BTC_SHAPED, "AAAUSDT", readings=False)], reference_time=REFERENCE
    )[0]
    assert decision.timeframes == ()


def test_no_freshness_verdict_exists_anywhere_in_the_model() -> None:
    """§15: without a validated threshold, the product states no verdict.

    Asserted on the field names, so a later change cannot add one quietly.
    """
    from fmis.swing_setup.models import TimeframeReading
    from fmis.swing_workspace.models import TimeframeLine

    banned = re.compile(r"fresh|stale|expired|verdict|ok|healthy", re.IGNORECASE)
    for model in (TimeframeReading, TimeframeLine, TimeframeRow):
        for field in dataclasses.fields(model):
            assert not banned.search(field.name), (model.__name__, field.name)


def test_the_page_never_calls_an_age_fresh_or_stale() -> None:
    html = render_page(snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing").lower()
    for word in (">fresh<", ">stale<", "up to date", "data is current"):
        assert word not in html, word
    assert "no age here is called fresh or stale" in render_page(
        snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing", symbol="AAAUSDT"
    ).lower()


def test_a_role_read_at_a_different_instant_keeps_its_own_age() -> None:
    """The whole point of per-role instants: they are not synchronised."""
    line = TimeframeRow(
        role="context",
        interval="1w",
        as_of=datetime(2026, 9, 1, tzinfo=timezone.utc),
        closed_count=260,
        age=timedelta(days=3),
    )
    other = dataclasses.replace(line, role="setup", interval="1d", age=timedelta(hours=4))
    assert line.age != other.age


# ===========================================================================
# 4. The swing snapshot — descriptive, never predictive
# ===========================================================================


def test_the_snapshot_counts_the_scan_over_the_engines_own_conditions() -> None:
    view = snapshot_of(
        live(BTC_SHAPED, "AAAUSDT"),
        live(BNB_SHAPED, "BBBUSDT"),
        live(CANDIDATE, "CCCUSDT"),
        failed_result("DDDUSDT"),
    ).swing.data
    snapshot = view.snapshot
    assert snapshot.scanned == 3
    assert snapshot.waiting == 2
    assert snapshot.candidates == 1
    assert snapshot.unreadable == 1
    assert dict(snapshot.blockers)["context_regime_not_eligible"] == 1
    assert dict(snapshot.blockers)["directional_families_disagree"] == 1
    assert dict(snapshot.developing)["leaning"] == 1


def test_the_snapshot_categories_are_the_engines_enums_and_nothing_else() -> None:
    """No category invented for the page, and none merged."""
    view = snapshot_of(live(BTC_SHAPED, "AAAUSDT"), live(BNB_SHAPED, "BBBUSDT")).swing.data
    kinds = {kind.value for kind in BlockerKind}
    states = {state.value for state in DevelopingEvidenceState}
    assert {name for name, _ in view.snapshot.blockers} <= kinds
    assert {name for name, _ in view.snapshot.developing} <= states


def test_the_snapshot_distributions_are_in_enum_order_not_frequency_order() -> None:
    """A distribution sorted by size reads as a ranking of importance."""
    view = snapshot_of(
        live(BNB_SHAPED, "AAAUSDT"),
        live(BNB_SHAPED, "BBBUSDT"),
        live(BTC_SHAPED, "CCCUSDT"),
    ).swing.data
    order = [kind.value for kind in BlockerKind]
    listed = [name for name, _ in view.snapshot.blockers]
    assert listed == [name for name in order if name in listed]
    # …and the larger group is not first, which frequency order would put there.
    assert dict(view.snapshot.blockers)["context_regime_not_eligible"] == 1
    assert listed[0] == "context_regime_not_eligible"


def test_the_snapshot_holds_no_market_verdict_field() -> None:
    banned = re.compile(
        r"bull|bear|risk_on|risk_off|breadth|score|rank|sentiment|outlook",
        re.IGNORECASE,
    )
    for field in dataclasses.fields(SwingSnapshot):
        assert not banned.search(field.name), field.name


def test_the_snapshot_tiles_and_the_table_cannot_disagree() -> None:
    """Both are built from one traversal of the same rows."""
    view = snapshot_of(
        live(BTC_SHAPED, "AAAUSDT"), live(BNB_SHAPED, "BBBUSDT")
    ).swing.data
    assert view.snapshot.scanned == len(view.decisions)
    waiting = [row for row in view.decisions if row.state == "wait"]
    assert view.snapshot.waiting == len(waiting)


# ===========================================================================
# 5. No ranking, and no promotion, on the rendered page
# ===========================================================================

_RANKING_VOCABULARY = re.compile(
    r"score|rank|closeness|confidence|probabilit|weight|strength|percentile"
    r"|priority|opportunity_|likelihood|conviction",
    re.IGNORECASE,
)


@pytest.mark.parametrize(
    "model", [SwingSnapshot, DevelopingEvidenceRow, BlockerRow, TimeframeRow]
)
def test_no_slice_2_model_holds_a_ranking_field(model: type) -> None:
    for field in dataclasses.fields(model):
        assert not _RANKING_VOCABULARY.search(field.name), field.name


def test_the_overview_never_says_a_symbol_is_close_to_a_trade() -> None:
    """§19: WATCH means a named unresolved condition, never proximity."""
    html = render_page(
        snapshot_of(live(BTC_SHAPED, "AAAUSDT"), live(BNB_SHAPED, "BBBUSDT")),
        "/swing",
    ).lower()
    for phrase in (
        "almost ready",
        "strong opportunity",
        "high potential",
        "near entry",
        "close to a trade",
        "ready to trade",
    ):
        assert phrase not in html, phrase


def test_a_leaning_row_still_shows_its_decision_beside_the_lean() -> None:
    """The rendered guarantee behind the model-level invariant."""
    html = render_page(snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing")
    row = html.split('/swing/AAAUSDT')[1].split("</tr>")[0]
    assert "leaning" in row
    assert "not confirmed" in row
    assert "state-wait" in row


def test_developing_evidence_is_never_worded_as_a_signal_or_a_candidate() -> None:
    """The word *signal* exists in the evidence as an engine term
    (`macd_vs_signal`), so a bare substring check would forbid a legitimate
    indicator name. What must never appear is the *claim*: a signal, a
    candidate, an entry or a readiness attached to the developing evidence.
    """
    for kwargs in ({}, {"symbol": "AAAUSDT"}):
        html = render_page(
            snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing", **kwargs
        ).lower()
        for phrase in (
            "long signal",
            "short signal",
            "buy signal",
            "sell signal",
            "signal:",
            "is a candidate",
            "entry signal",
        ):
            assert phrase not in html, phrase
    # And the one place the vocabulary is used, it is used as a denial.
    detail = render_page(
        snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing", symbol="AAAUSDT"
    )
    assert "never a direction the policy stated" in detail


# ===========================================================================
# 6. The rendered operator surfaces
# ===========================================================================


def test_the_overview_answers_the_six_questions_without_opening_a_symbol() -> None:
    html = render_page(
        snapshot_of(live(BTC_SHAPED, "AAAUSDT"), live(BNB_SHAPED, "BBBUSDT")),
        "/swing",
    )
    for column in (
        "Decision",
        "Developing evidence",
        "HTF context",
        "Setup state",
        "What is holding it",
        "Data age",
    ):
        assert f">{column}</th>" in html, column


def test_two_symbols_show_visibly_different_blockers_on_the_overview() -> None:
    html = render_page(
        snapshot_of(live(BTC_SHAPED, "AAAUSDT"), live(BNB_SHAPED, "BBBUSDT")),
        "/swing",
    )
    left = html.split("/swing/AAAUSDT")[1].split("</tr>")[0]
    right = html.split("/swing/BBBUSDT")[1].split("</tr>")[0]
    assert "HTF regime not eligible" in left
    assert "HTF regime not eligible" not in right
    assert "timeframes disagree" in right
    assert "timeframes disagree" not in left


def test_the_symbol_page_puts_the_summary_above_the_audit() -> None:
    """§16's hierarchy, asserted as an order rather than as a presence.

    **Stated as a relation, not as a fixed list.** This test previously pinned
    the first four panel titles exactly, which made it fail when Slice 4 inserted
    the risk and trade-planning panel — a change that does not touch the
    invariant it exists to protect. The invariant is that the decision comes
    first and the audit comes last, and a milestone that adds a trading panel
    between them should not have to relitigate it.

    **TA Slice 5A made the same point a second time**, inserting the technical
    context panel between the timeframe panel and the families table, and the
    last positional assertion — ``panels[2]`` — failed on it. It is now stated
    as an order too, which is what the paragraph above already said this test
    should be. The relation asserted is the whole hierarchy: decision, then the
    environment, then the recovered facts about it, then the families, then
    trade planning, then the audit.
    """
    html = render_page(snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing", symbol="AAAUSDT")
    panels = re.findall(r"<h2>([^<]+)", html)
    assert panels[0] == "AAAUSDT — decision"
    assert panels[1] == "AAAUSDT — timeframe context and data times"
    assert panels.index("AAAUSDT — timeframe context and data times") < panels.index(
        "AAAUSDT — technical context"
    ) < panels.index("AAAUSDT — directional families")
    # Last of this symbol's panels. Anything after it belongs to another section
    # of the page (the scan-change block), not to the decision.
    audit = panels.index("AAAUSDT — evidence and independence audit")
    assert audit == max(
        index for index, title in enumerate(panels) if title.startswith("AAAUSDT")
    )
    # And every trading question is answered above it.
    assert audit > panels.index("AAAUSDT — risk and trade planning")


def test_the_summary_panel_answers_the_operator_questions() -> None:
    html = render_page(snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing", symbol="AAAUSDT")
    panel = html.split("AAAUSDT — decision")[1].split("</section>")[0]
    for label in (
        "developing evidence",
        "what is holding it",
        "HTF context",
        "setup state",
        "evidence quality",
        "data age",
    ):
        assert f"<dt>{label}</dt>" in panel, label


def test_the_independence_warning_survives_into_the_summary() -> None:
    html = render_page(snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing", symbol="AAAUSDT")
    panel = html.split("AAAUSDT — decision")[1].split("</section>")[0]
    assert "independent corroboration not established" in panel


def test_the_full_evidence_audit_is_still_present_and_complete() -> None:
    """Slice 2 reorganises. It removes nothing Slice 1 built."""
    decision = decision_of(BTC_SHAPED)
    # Unescaped, because the page escapes every string it prints and an
    # apostrophe in an engine sentence becomes `&#x27;` on the way out.
    html = html_module.unescape(
        render_page(snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing", symbol="AAAUSDT")
    )
    seen = 0
    for group in (
        decision.supporting,
        decision.conflicting,
        decision.missing,
        decision.unavailable,
    ):
        for item in group:
            assert item.key in html, item.key
            assert item.statement in html, item.statement[:60]
            assert item.observed in html, item.observed[:60]
            seen += 1
    assert seen >= 20, "the fixture must carry a real evidence report"


def test_a_shared_independence_explanation_is_printed_once_and_still_referenced() -> None:
    """§16: remove the repetition without losing auditability.

    Tested on the mechanism directly. Whether any *particular* fixture happens
    to contain a repeated explanation depends on what the projection produced
    for it, so a test that only inspected a fixture's rendering would pass
    vacuously the day the fixture stopped repeating one — which is exactly what
    the current fixture does: its four explanations are four distinct strings.
    """
    notes = _IndependenceNotes()
    shared = "Both readings come from the same upstream series."
    other = "These two share no input."
    # Three rows, two of them citing the same explanation.
    assert notes.mark(shared) == "<sup>1</sup>"
    assert notes.mark(other) == "<sup>2</sup>"
    assert notes.mark(shared) == "<sup>1</sup>"  # numbered once, referenced twice
    assert notes.mark(None) == ""

    rendered = notes.render()
    assert rendered.count(shared) == 1
    assert rendered.count(other) == 1
    assert rendered.startswith('<ul class="footnotes">')


def test_every_non_independent_row_still_reaches_its_own_explanation() -> None:
    """The auditability half: the markers are on the rows, the text is below.

    Asserted against the real page, so the numbering the mechanism produces is
    actually wired into the evidence table rather than merely available.
    """
    decision = decision_of(BTC_SHAPED)
    marked = [
        item
        for group in (
            decision.supporting,
            decision.conflicting,
            decision.missing,
            decision.unavailable,
        )
        for item in group
        if item.independence_note
    ]
    assert marked, "the fixture must carry real independence notes"

    html = render_page(snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing", symbol="AAAUSDT")
    assert "not independent" in html
    assert '<ul class="footnotes">' in html
    # One numbered entry per distinct explanation, and every one is reachable.
    numbered = re.findall(r"<li><sup>(\d+)</sup>", html)
    assert len(numbered) == len({item.independence_note for item in marked})
    for index in numbered:
        assert f"<sup>{index}</sup></span>" in html, index


def test_no_invalidation_is_stated_rather_than_left_blank_or_invented() -> None:
    """§13: no stop-loss is derived here to fill an empty section."""
    decision = decision_of(BTC_SHAPED)
    assert decision.invalidation == ()
    html = render_page(snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing", symbol="AAAUSDT")
    assert "The engine produced no structural invalidation" in html
    assert "None is derived here" in html


def test_engine_keys_stay_visible_beside_their_readable_labels() -> None:
    """§17: presentation, not semantic rewriting. Provenance is never hidden."""
    html = render_page(snapshot_of(live(BTC_SHAPED, "AAAUSDT")), "/swing", symbol="AAAUSDT")
    assert "HTF structural trend" in html
    assert "context_structural_trend" in html
    assert "fmis.structural_trend (1w)" in html


def test_existing_dashboard_routes_still_answer() -> None:
    snapshot = snapshot_of(live(BTC_SHAPED, "AAAUSDT"), live(BNB_SHAPED, "BBBUSDT"))
    from fmis.operator_dashboard import PAGES

    for path, _title in PAGES:
        assert render_page(snapshot, path)
    assert render_page(snapshot, "/swing", symbol="AAAUSDT")
    assert render_page(snapshot, "/swing", symbol="NOSUCHUSDT")
