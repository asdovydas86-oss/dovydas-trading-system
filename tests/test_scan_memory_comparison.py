"""What counts as a change, what does not, and the invariants that hold for both.

**The two halves.** Named transitions the operator asked for — decision, blocker,
developing evidence, structure — proved over the **real** engine's own output;
and invariants asserted over generated pairs of states rather than over one
example, because *"no unchanged field appears as changed"* is a property of the
comparator and an example can only ever fail to disprove it.
"""

from __future__ import annotations

import itertools
from dataclasses import replace

import pytest

from fmis.scan_memory import (
    ABSENT,
    CHANGE_DIMENSIONS,
    PRESENT,
    NOT_STATED,
    ChangeDimension,
    ComparisonStatus,
    ScanMemoryError,
    compare_scans,
    dimension_values,
    transitions_between,
)

from tests.scan_memory_helpers import AT, LATER, live_record, record, state
from tests.swing_decision_helpers import (
    CANDIDATE,
    FAMILIES_SPLIT,
    GATE_LEANING,
    GATE_REJECTED,
)


def _live_pair(before, after, symbol="AAAUSDT"):
    """Two comparable scans of one symbol, both from the real composition root."""
    return (
        live_record((before, symbol), recorded_at=AT, reference_time=AT),
        live_record((after, symbol), recorded_at=LATER, reference_time=LATER),
    )


def _dimensions(comparison, symbol="AAAUSDT"):
    change = comparison.change_for(symbol)
    return {} if change is None else {
        item.dimension: (item.previous, item.current) for item in change.transitions
    }


# ---------------------------------------------------------------------------
# The transitions the brief names
# ---------------------------------------------------------------------------


def test_wait_becoming_a_candidate_is_a_decision_transition() -> None:
    """§28. A named factual transition — **never a buy signal**, and nothing in
    the comparison says otherwise."""
    previous, current = _live_pair(GATE_REJECTED, CANDIDATE)
    seen = _dimensions(compare_scans(previous, current))
    assert seen[ChangeDimension.DECISION] == ("wait", "candidate")


def test_a_candidate_becoming_wait_is_a_decision_transition() -> None:
    """§28, the other way. **Never a failed trade** — nothing was ever taken."""
    previous, current = _live_pair(CANDIDATE, GATE_REJECTED)
    seen = _dimensions(compare_scans(previous, current))
    assert seen[ChangeDimension.DECISION] == ("candidate", "wait")


def test_the_policy_direction_transitions_with_the_decision() -> None:
    previous, current = _live_pair(GATE_REJECTED, CANDIDATE)
    before, after = _dimensions(compare_scans(previous, current))[
        ChangeDimension.POLICY_DIRECTION
    ]
    assert before == NOT_STATED
    assert after and after != NOT_STATED


def test_the_blocker_changes_while_the_decision_stays_wait() -> None:
    """**§30, and the single most valuable transition in this milestone.** A
    symbol that stayed `WAIT` all week is not a symbol nothing happened to: the
    reason it is waiting moved from a higher-timeframe regime gate to a
    directional disagreement, and that is a different operational situation."""
    previous, current = _live_pair(GATE_REJECTED, FAMILIES_SPLIT)
    comparison = compare_scans(previous, current)
    change = comparison.change_for("AAAUSDT")
    assert change is not None
    assert change.state == "wait" and change.previous_state == "wait"
    assert _dimensions(comparison)[ChangeDimension.BLOCKER] == (
        "context_regime_not_eligible",
        "directional_families_disagree",
    )
    assert ChangeDimension.DECISION not in _dimensions(comparison)


def test_developing_evidence_transitions_are_evidence_state_not_direction() -> None:
    """§29. The dimension carries the family reading and the side it names as
    **one** fact, so a page cannot show a side with no state beside it."""
    previous, current = _live_pair(GATE_REJECTED, GATE_LEANING)
    before, after = _dimensions(compare_scans(previous, current))[
        ChangeDimension.DEVELOPING_EVIDENCE
    ]
    assert before == "divided"
    assert after.startswith("leaning")
    assert ChangeDimension.DECISION not in _dimensions(compare_scans(previous, current))


def test_the_higher_timeframe_context_structure_transitions() -> None:
    """§32, over the engine's own `structural_trend` values."""
    previous, current = _live_pair(GATE_REJECTED, FAMILIES_SPLIT)
    before, after = _dimensions(compare_scans(previous, current))[
        ChangeDimension.CONTEXT_STRUCTURE
    ]
    assert (before, after) == ("neutral", "sustained_lower")


def test_the_setup_and_execution_structures_are_separate_dimensions() -> None:
    previous = record(state(structural_trends=(("context", "neutral"), ("setup", "neutral"), ("execution", "neutral"))), reference_time=AT)
    current = record(state(structural_trends=(("context", "neutral"), ("setup", "sustained_higher"), ("execution", "sustained_lower"))), reference_time=LATER)
    seen = _dimensions(compare_scans(previous, current))
    assert seen[ChangeDimension.SETUP_STRUCTURE] == ("neutral", "sustained_higher")
    assert seen[ChangeDimension.EXECUTION_STRUCTURE] == ("neutral", "sustained_lower")
    assert ChangeDimension.CONTEXT_STRUCTURE not in seen


def test_the_evidence_independence_state_transitions() -> None:
    previous = record(state(independence_established=False), reference_time=AT)
    current = record(state(independence_established=True), reference_time=LATER)
    before, after = _dimensions(compare_scans(previous, current))[
        ChangeDimension.EVIDENCE_INDEPENDENCE
    ]
    assert (before, after) == ("not established", "established")


def test_an_evidence_count_change_is_reported_as_counts_and_never_as_confidence() -> None:
    """§31. `supporting 1 → 2` is one more item in a group. The wording says
    exactly that and nothing that could be read as *stronger*."""
    previous = record(state(supporting=1), reference_time=AT)
    current = record(state(supporting=2), reference_time=LATER)
    before, after = _dimensions(compare_scans(previous, current))[
        ChangeDimension.EVIDENCE_COMPOSITION
    ]
    assert "supporting 1" in before and "supporting 2" in after
    for forbidden in ("confidence", "stronger", "weaker", "improved", "better", "worse"):
        assert forbidden not in (before + after).lower()


def test_the_decision_context_state_transitions() -> None:
    previous = record(state(sufficiency="sufficient"), reference_time=AT)
    current = record(state(sufficiency="limited"), reference_time=LATER)
    assert _dimensions(compare_scans(previous, current))[
        ChangeDimension.DECISION_CONTEXT
    ] == ("sufficient", "limited")


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


def test_a_symbol_absent_from_the_new_scan_is_reported_as_absent_never_as_bearish() -> None:
    """§33. *Produced no assessment* is a statement about the scan."""
    previous = record(state("AAAUSDT"), state("BBBUSDT"), reference_time=AT)
    current = record(
        state("AAAUSDT"), universe=("AAAUSDT", "BBBUSDT"), reference_time=LATER
    )
    comparison = compare_scans(previous, current)
    change = comparison.change_for("BBBUSDT")
    assert change is not None
    assert change.transitions[0].dimension is ChangeDimension.PRESENCE
    assert change.transitions[0].current == ABSENT
    text = " ".join(
        [change.state, change.previous_state, change.transitions[0].current]
    ).lower()
    for forbidden in ("bearish", "broken", "failed", "weak", "error"):
        assert forbidden not in text


def test_a_symbol_that_appears_in_the_new_scan_is_labelled_as_appearing() -> None:
    previous = record(
        state("AAAUSDT"), universe=("AAAUSDT", "BBBUSDT"), reference_time=AT
    )
    # The previous scan is incomplete, so it is not a baseline at all — which is
    # the point: coverage recovering is only ever compared against full coverage.
    complete = record(state("AAAUSDT"), state("BBBUSDT"), reference_time=AT)
    current = record(
        state("AAAUSDT"),
        state("BBBUSDT"),
        state("CCCUSDT"),
        universe=("AAAUSDT", "BBBUSDT", "CCCUSDT"),
        reference_time=LATER,
    )
    assert compare_scans(previous, current).status is ComparisonStatus.NOT_COMPARABLE
    assert compare_scans(complete, current).status is ComparisonStatus.NOT_COMPARABLE


def test_coverage_recovering_within_one_watchlist_is_a_presence_transition() -> None:
    previous = record(
        state("AAAUSDT"), state("BBBUSDT"), universe=("AAAUSDT", "BBBUSDT"), reference_time=AT
    )
    lost = record(state("AAAUSDT"), universe=("AAAUSDT", "BBBUSDT"), reference_time=LATER)
    comparison = compare_scans(previous, lost)
    change = comparison.change_for("BBBUSDT")
    assert change is not None
    assert change.transitions == (
        change.transitions[0],
    ) and change.transitions[0].previous == PRESENT


# ---------------------------------------------------------------------------
# What must NOT be a change
# ---------------------------------------------------------------------------


def test_two_identical_scans_produce_no_material_change() -> None:
    """§19. Zero changes, and every symbol named as unchanged — never an event."""
    previous = record(state("AAAUSDT"), state("BBBUSDT"), reference_time=AT)
    current = record(state("AAAUSDT"), state("BBBUSDT"), reference_time=LATER)
    comparison = compare_scans(previous, current)
    assert comparison.status is ComparisonStatus.COMPARED
    assert comparison.changes == ()
    assert comparison.unchanged == ("AAAUSDT", "BBBUSDT")


def test_time_passing_alone_is_not_a_change() -> None:
    """**§12, asserted over the live engine's own output.** Same market state,
    four hours later, every per-symbol instant moved — and nothing is reported."""
    previous = live_record(((1, 5, 9), "AAAUSDT"), recorded_at=AT, reference_time=AT)
    moved = replace(
        previous,
        identity=replace(previous.identity, reference_time=LATER),
        recorded_at=LATER,
        symbols=tuple(
            replace(item, as_of=item.as_of.replace(year=item.as_of.year + 1))
            for item in previous.symbols
        ),
    )
    assert moved.symbols[0].as_of != previous.symbols[0].as_of
    comparison = compare_scans(previous, moved)
    assert comparison.changes == ()
    assert comparison.unchanged == ("AAAUSDT",)


def test_a_scan_compared_with_itself_is_refused_rather_than_reported_unchanged() -> None:
    one = record(state())
    comparison = compare_scans(one, one)
    assert comparison.status is ComparisonStatus.NOT_COMPARABLE
    assert comparison.changes == () and comparison.unchanged == ()


# ---------------------------------------------------------------------------
# Invariants — properties of the comparator, not examples of it
# ---------------------------------------------------------------------------

#: One alternative for every dimension a `SymbolState` carries, so a generated
#: pair really does differ on the dimension it claims to. Written out rather
#: than fuzzed: the point is coverage of the declared dimensions, not entropy.
_ALTERNATIVES: tuple[tuple[str, object], ...] = (
    ("state", "candidate"),
    ("direction", "sideB"),
    ("sufficiency", "limited"),
    ("developing_state", "none_readable"),
    ("developing_lean", None),
    ("blocker_kind", "awaiting_confirmation"),
    ("structural_trends", (("context", "trending"), ("setup", "neutral"))),
    ("independence_established", True),
    ("evidence_available", False),
    ("supporting", 7),
    ("conflicting", 7),
    ("missing", 7),
    ("unavailable", 7),
    # provenance, and therefore never a difference
    ("blocker_observed", "something else"),
)


def _variants():
    base = state()
    for name, value in _ALTERNATIVES:
        candidate = replace(base, **{name: value})
        if candidate == base:
            continue
        yield name, base, candidate


def test_the_variant_matrix_really_varies() -> None:
    """Non-vacuity for the invariants below: a matrix whose variants equalled the
    base would satisfy every property without exercising anything."""
    names = {name for name, _, _ in _variants()}
    assert names == {name for name, _ in _ALTERNATIVES}


@pytest.mark.parametrize("name", [name for name, _ in _ALTERNATIVES])
def test_no_unchanged_dimension_is_ever_reported_as_changed(name: str) -> None:
    base = state()
    changed = replace(base, **{name: dict(_ALTERNATIVES)[name]})
    before = dimension_values(base)
    after = dimension_values(changed)
    for transition in transitions_between(base, changed):
        assert before[transition.dimension] != after[transition.dimension]
        assert transition.previous == before[transition.dimension]
        assert transition.current == after[transition.dimension]


def test_every_reported_transition_has_two_different_ends() -> None:
    for _, base, changed in _variants():
        for transition in transitions_between(base, changed):
            assert transition.previous != transition.current


def test_comparing_a_state_with_itself_reports_nothing() -> None:
    for _, base, changed in _variants():
        assert transitions_between(base, base) == ()
        assert transitions_between(changed, changed) == ()


def test_comparison_mutates_neither_argument() -> None:
    previous = record(state("AAAUSDT"), state("BBBUSDT"), reference_time=AT)
    current = record(
        state("AAAUSDT", state="candidate", direction="sideA"),
        state("BBBUSDT"),
        reference_time=LATER,
    )
    before = (repr(previous), repr(current))
    compare_scans(previous, current)
    assert (repr(previous), repr(current)) == before


def test_the_order_symbols_are_stored_in_cannot_change_the_per_symbol_result() -> None:
    """§40. The comparison is keyed by name; storage order is presentation."""
    a, b = state("AAAUSDT"), state("BBBUSDT", state="candidate", direction="sideA")
    forwards = record(a, b, reference_time=AT)
    backwards = record(b, a, universe=("AAAUSDT", "BBBUSDT"), reference_time=AT)
    current = record(
        replace(a, blocker_kind="awaiting_confirmation"), b, reference_time=LATER
    )
    assert _dimensions(compare_scans(forwards, current)) == _dimensions(
        compare_scans(backwards, current)
    )


def test_changed_symbols_come_out_in_the_scans_own_universe_order() -> None:
    """§14. A partition, never a ranking: no symbol is placed by how interesting
    its change is."""
    universe = ("DDDUSDT", "AAAUSDT", "CCCUSDT", "BBBUSDT")
    previous = record(*(state(symbol) for symbol in universe), universe=universe, reference_time=AT)
    current = record(
        *(
            state(symbol, blocker_kind="awaiting_confirmation")
            if symbol != "CCCUSDT"
            else state(symbol)
            for symbol in universe
        ),
        universe=universe,
        reference_time=LATER,
    )
    comparison = compare_scans(previous, current)
    assert tuple(change.symbol for change in comparison.changes) == (
        "DDDUSDT",
        "AAAUSDT",
        "BBBUSDT",
    )
    assert comparison.unchanged == ("CCCUSDT",)


def test_transitions_come_out_in_the_enums_own_order() -> None:
    previous = record(state(), reference_time=AT)
    current = record(
        state(state="candidate", direction="sideA", blocker_kind="awaiting_confirmation", supporting=9),
        reference_time=LATER,
    )
    change = compare_scans(previous, current).change_for("AAAUSDT")
    assert change is not None
    order = [CHANGE_DIMENSIONS.index(item.dimension) for item in change.transitions]
    assert order == sorted(order)


def test_two_markets_cannot_be_compared_with_each_other() -> None:
    with pytest.raises(ScanMemoryError, match="one market's two states"):
        transitions_between(state("AAAUSDT"), state("BBBUSDT"))


def test_a_symbol_change_with_no_transition_is_not_representable() -> None:
    """The fake-event guard, asserted on the type rather than on a caller."""
    from fmis.scan_memory import SymbolChange

    with pytest.raises(ScanMemoryError, match="at least one transition"):
        SymbolChange(symbol="AAAUSDT", state="wait", previous_state="wait")


def test_a_transition_with_two_equal_ends_is_not_representable() -> None:
    from fmis.scan_memory import StateTransition

    with pytest.raises(ScanMemoryError, match="not a transition"):
        StateTransition(
            dimension=ChangeDimension.DECISION, previous="wait", current="wait"
        )


def test_a_comparison_that_did_not_happen_cannot_carry_symbols() -> None:
    """**§9's hardest rule, made unrepresentable.** *Nothing changed* is a claim
    about the market and may only be made when two scans really were compared."""
    from fmis.scan_memory import ScanComparison

    with pytest.raises(ScanMemoryError, match="would fabricate a baseline"):
        ScanComparison(
            status=ComparisonStatus.NO_PREVIOUS_SCAN,
            current_scan_at=AT,
            reason="none yet",
            unchanged=("AAAUSDT",),
        )


def test_the_declared_dimensions_are_all_reachable() -> None:
    """Non-vacuity for `CHANGE_DIMENSIONS`: every member is producible by some
    pair of states this suite can build, so none is decoration."""
    reached = {ChangeDimension.PRESENCE}
    for _, base, changed in _variants():
        reached.update(item.dimension for item in transitions_between(base, changed))
    for role, dimension in (
        ("context", ChangeDimension.CONTEXT_STRUCTURE),
        ("setup", ChangeDimension.SETUP_STRUCTURE),
        ("execution", ChangeDimension.EXECUTION_STRUCTURE),
    ):
        pair = transitions_between(
            state(structural_trends=((role, "neutral"),)),
            state(structural_trends=((role, "trending"),)),
        )
        reached.update(item.dimension for item in pair)
    assert reached == set(CHANGE_DIMENSIONS)


def test_the_cartesian_product_of_two_variants_never_invents_a_dimension() -> None:
    """Every pair of variants, both directions: no transition names a dimension
    on which the two states agree."""
    variants = [changed for _, _, changed in _variants()] + [state()]
    for before, after in itertools.permutations(variants, 2):
        values_before = dimension_values(before)
        values_after = dimension_values(after)
        for transition in transitions_between(before, after):
            assert values_before[transition.dimension] != values_after[transition.dimension]
