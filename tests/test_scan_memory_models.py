"""The domain of scan memory: identity, comparability, and the projection.

**What these tests defend.** That a scan is identified by what it *is* and not by
what it *found*; that two scans are compared only when comparing them means
something; that the projection keeps the states an operator asks change questions
about and drops everything else.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from fmis.scan_memory import (
    CHANGE_DIMENSIONS,
    SCAN_MEMORY_SCHEMA_VERSION,
    ChangeDimension,
    ScanMemoryError,
    ScanRecord,
    dimension_values,
    incomparable_reason,
    scan_record_from,
)

from tests.scan_memory_helpers import AT, LATER, TIMEFRAMES, identity, live_record, live_workspace, record, state


# ---------------------------------------------------------------------------
# Scan identity
# ---------------------------------------------------------------------------


def test_two_refreshes_at_different_instants_are_two_scans() -> None:
    assert identity(reference_time=AT).scan_id != identity(reference_time=LATER).scan_id


def test_the_scan_id_is_a_pure_function_of_the_identity() -> None:
    """Deterministic across processes: the same identity always names the same
    scan, which is what makes recording one twice an idempotent no-op."""
    assert identity().scan_id == identity().scan_id


def test_the_scan_id_does_not_depend_on_what_the_scan_found() -> None:
    """**The failure this prevents.** A digest over the results would give two
    scans that observed identical state one id, so the second could never be
    recorded — and *nothing changed* would become indistinguishable from
    *nothing ran*."""
    quiet = record(state(state="wait"))
    busy = record(state(state="candidate", direction="sideA"))
    assert quiet.scan_id == busy.scan_id


def test_a_different_watchlist_is_a_different_identity() -> None:
    assert identity(universe=("AAAUSDT",)).scan_id != identity(
        universe=("AAAUSDT", "BBBUSDT")
    ).scan_id


def test_a_universe_that_lists_a_symbol_twice_is_refused() -> None:
    with pytest.raises(ScanMemoryError, match="lists a symbol twice"):
        identity(universe=("AAAUSDT", "AAAUSDT"))


def test_an_empty_universe_is_refused() -> None:
    with pytest.raises(ScanMemoryError, match="non-empty"):
        identity(universe=())


def test_a_naive_instant_is_refused() -> None:
    from datetime import datetime

    with pytest.raises(ScanMemoryError, match="timezone-aware"):
        identity(reference_time=datetime(2026, 8, 24, 12, 0))


# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------


def test_a_scan_covering_every_requested_symbol_is_complete() -> None:
    assert record(state("AAAUSDT"), state("BBBUSDT")).complete


def test_a_scan_missing_one_requested_symbol_is_not_complete() -> None:
    """§20: a partial scan is recorded honestly and never becomes a baseline."""
    partial = record(state("AAAUSDT"), universe=("AAAUSDT", "BBBUSDT"))
    assert not partial.complete
    assert partial.unreadable == ("BBBUSDT",)


def test_a_scan_that_read_nothing_is_not_complete() -> None:
    empty = ScanRecord(identity=identity(), recorded_at=AT)
    assert not empty.complete


def test_a_symbol_recorded_as_both_assessed_and_unreadable_is_refused() -> None:
    with pytest.raises(ScanMemoryError, match="both assessed and unreadable"):
        ScanRecord(
            identity=identity(),
            recorded_at=AT,
            symbols=(state("AAAUSDT"),),
            unreadable=("AAAUSDT",),
        )


def test_two_states_for_one_symbol_are_refused() -> None:
    with pytest.raises(ScanMemoryError, match="two states on one scan"):
        ScanRecord(
            identity=identity(),
            recorded_at=AT,
            symbols=(state("AAAUSDT"), state("AAAUSDT", state="candidate")),
        )


# ---------------------------------------------------------------------------
# Comparability
# ---------------------------------------------------------------------------


def test_two_scans_over_the_same_request_at_different_instants_are_comparable() -> None:
    assert incomparable_reason(record(state(), reference_time=AT), record(state(), reference_time=LATER)) == ""


def test_a_different_watchlist_makes_two_scans_incomparable() -> None:
    previous = record(state("AAAUSDT"), reference_time=AT)
    current = record(state("AAAUSDT"), state("BBBUSDT"), reference_time=LATER)
    assert "different watchlist" in incomparable_reason(previous, current)


def test_different_timeframe_roles_make_two_scans_incomparable() -> None:
    previous = record(state(), reference_time=AT)
    current = record(
        state(),
        reference_time=LATER,
        timeframes=(("context", "1d"), ("execution", "1h"), ("setup", "4h")),
    )
    assert "different timeframe roles" in incomparable_reason(previous, current)


def test_an_older_schema_makes_two_scans_incomparable() -> None:
    previous = record(state(), reference_time=AT, schema_version=SCAN_MEMORY_SCHEMA_VERSION - 1)
    current = record(state(), reference_time=LATER)
    assert "schema" in incomparable_reason(previous, current)


def test_an_incomplete_previous_scan_is_not_a_baseline() -> None:
    previous = record(state("AAAUSDT"), universe=("AAAUSDT", "BBBUSDT"), reference_time=AT)
    current = record(state("AAAUSDT"), state("BBBUSDT"), reference_time=LATER)
    assert "did not cover every symbol" in incomparable_reason(previous, current)


def test_a_scan_is_never_comparable_with_itself() -> None:
    """The guard behind §23: a duplicated observation cannot become `A → A`."""
    one = record(state())
    assert incomparable_reason(one, one) == "the previous record is this same scan"


# ---------------------------------------------------------------------------
# The projection
# ---------------------------------------------------------------------------


def test_the_projection_keeps_the_states_a_change_question_is_asked_about() -> None:
    projected = live_record(((1, 5, 9), "AAAUSDT")).symbols[0]
    assert projected.state == "wait"
    assert projected.blocker_kind == "context_regime_not_eligible"
    assert projected.developing_state
    assert dict(projected.structural_trends).keys() == {"context", "setup", "execution"}
    assert projected.sufficiency


def test_the_projection_stores_no_prose_and_no_evidence_item() -> None:
    """**§10 and §11 together.** A thesis line, a blocker sentence or an
    evidence item stored here is a sentence something could later diff."""
    projected = live_record(((1, 5, 9), "AAAUSDT")).symbols[0]
    fields = set(type(projected).__slots__)
    for forbidden in ("thesis", "regime_context", "confirmation", "invalidation",
                      "supporting_items", "factors", "reason", "statement", "requirement"):
        assert forbidden not in fields, forbidden
    # The four evidence groups survive as counts, which is what §11 permits.
    for kept in ("supporting", "conflicting", "missing", "unavailable"):
        assert isinstance(getattr(projected, kept), int)


def test_the_projection_stores_no_timeframe_instant_age_or_bar_count() -> None:
    """**§12's structural guarantee.** The comparator cannot report a routine
    observation update as a change, because it cannot see one."""
    projected = live_record(((1, 5, 9), "AAAUSDT")).symbols[0]
    fields = set(type(projected).__slots__)
    for forbidden in ("age", "closed_count", "interval", "timeframes"):
        assert forbidden not in fields, forbidden


def test_the_per_symbol_instant_is_stored_and_is_not_a_dimension() -> None:
    """Provenance, so a surface can print what the previous scan saw. Never a
    difference, so the clock advancing is not an event."""
    projected = live_record(((1, 5, 9), "AAAUSDT")).symbols[0]
    assert projected.as_of is not None
    later = replace(projected, as_of=projected.as_of + timedelta(hours=9))
    assert later.as_of != projected.as_of
    assert dimension_values(projected) == dimension_values(later)


def test_the_blocker_observed_value_is_stored_and_is_not_a_dimension() -> None:
    """§30: the *category* is compared, never the sentence or the value that
    failed the condition."""
    projected = live_record(((1, 5, 9), "AAAUSDT")).symbols[0]
    moved = replace(projected, blocker_observed="something else entirely")
    assert dimension_values(projected) == dimension_values(moved)


def test_the_projection_refuses_a_symbol_the_universe_never_asked_for() -> None:
    workspace = live_workspace(((1, 5, 9), "AAAUSDT"))
    with pytest.raises(ScanMemoryError, match="never asked for"):
        scan_record_from(
            workspace, recorded_at=AT, universe=("BBBUSDT",), timeframes=dict(TIMEFRAMES)
        )


def test_two_projections_over_the_same_workspace_are_equal() -> None:
    """**Pure.** No clock and no filesystem: the record is a function of its
    inputs, which is what makes every history assertion in this suite
    reproducible."""
    workspace = live_workspace(((1, 5, 9), "AAAUSDT"))
    first = scan_record_from(workspace, recorded_at=AT, universe=("AAAUSDT",), timeframes=dict(TIMEFRAMES))
    second = scan_record_from(workspace, recorded_at=AT, universe=("AAAUSDT",), timeframes=dict(TIMEFRAMES))
    assert first == second


def test_every_dimension_but_presence_is_read_from_a_symbol_state() -> None:
    """**Non-vacuity for the enum.** A dimension added and never read here would
    silently never fire; this fails instead."""
    read = set(dimension_values(state()))
    assert read == set(CHANGE_DIMENSIONS) - {ChangeDimension.PRESENCE}
