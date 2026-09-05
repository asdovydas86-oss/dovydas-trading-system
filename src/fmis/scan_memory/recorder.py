"""The one composition that remembers a scan. **Read, compare, then write.**

**The order is the design.** The previous scan is read *before* the current one
is published, so the current scan can never be compared with itself and a
duplicated observation can never produce an `A → A` transition. Comparison
happens *before* the write, so a filesystem failure costs the operator the
remembering and not the answer.

**What each failure costs, stated exactly:**

| what failed | current analysis | change surface |
|---|---|---|
| the scan itself | not produced — the swing section says so | not rendered |
| reading history | unaffected | *history unavailable*, with the reason |
| the two scans are not comparable | unaffected | *no previous comparable scan*, with the reason |
| publishing this scan | unaffected | still compared; **states that this scan was not recorded** |

Not one of those paths falsifies the market analysis, and none of them reports
*nothing changed* — which is a claim about the market and is only ever made when
two comparable scans really were compared.

**This module is the only writer, and nothing that decides anything calls it.**
The dependency arrow runs `swing_workspace → scan_memory`; a guard test asserts
no policy, engine or assessment module imports this package, so a remembered
state cannot become an input to current trade admission.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from fmis.scan_memory.comparison import compare_scans
from fmis.scan_memory.models import (
    ComparisonStatus,
    ScanComparison,
    ScanRecord,
)
from fmis.scan_memory.projection import scan_record_from
from fmis.scan_memory.store import HISTORY_ERRORS, ScanHistoryStore

__all__ = ["NO_PREVIOUS_SCAN_REASON", "record_scan", "compare_and_record"]

#: What the product says on its very first comparable scan. **Not an error.**
NO_PREVIOUS_SCAN_REASON = (
    "Baseline scan recorded. Changes appear after the next comparable refresh."
)

_INCOMPLETE_BASELINE = (
    "This scan did not produce an assessment for every symbol on its watchlist, "
    "so it is recorded but is not used as a baseline."
)


def compare_and_record(
    current: ScanRecord, *, store: ScanHistoryStore
) -> ScanComparison:
    """Compare ``current`` with the previous comparable completed scan, then keep it.

    **Pure of clocks and providers.** ``current`` is already built; this function
    reads the store, compares, writes and returns. Given the same store contents
    and the same record it returns an equal comparison.
    """
    previous: ScanRecord | None = None
    read_failure = ""
    try:
        previous = store.latest_complete(exclude=current.scan_id)
    except HISTORY_ERRORS as error:
        read_failure = str(error)

    if read_failure:
        comparison = ScanComparison(
            status=ComparisonStatus.HISTORY_UNAVAILABLE,
            current_scan_at=current.identity.reference_time,
            reason=(
                f"Previous scan history could not be read: {read_failure} This "
                "scan's own analysis is unaffected."
            ),
        )
    elif previous is None:
        comparison = ScanComparison(
            status=ComparisonStatus.NO_PREVIOUS_SCAN,
            current_scan_at=current.identity.reference_time,
            reason=NO_PREVIOUS_SCAN_REASON,
        )
    else:
        comparison = compare_scans(previous, current)

    recorded = True
    note = ""
    try:
        store.append(current)
    except HISTORY_ERRORS as error:
        recorded = False
        note = (
            f"This scan was not recorded: {error} The analysis on this page is "
            "unaffected; the next refresh has nothing to compare against."
        )

    if recorded and not current.complete:
        note = _INCOMPLETE_BASELINE

    if comparison.status is ComparisonStatus.NO_PREVIOUS_SCAN and not recorded:
        # The baseline sentence promises a comparison next time. It must not be
        # printed beside a failure to record the very scan it promises.
        comparison = ScanComparison(
            status=ComparisonStatus.NO_PREVIOUS_SCAN,
            current_scan_at=current.identity.reference_time,
            reason="No previous comparable scan is available.",
            recorded=False,
            recording_note=note,
        )
        return comparison

    return ScanComparison(
        status=comparison.status,
        current_scan_at=comparison.current_scan_at,
        previous_scan_at=comparison.previous_scan_at,
        reason=comparison.reason,
        changes=comparison.changes,
        unchanged=comparison.unchanged,
        recorded=recorded,
        recording_note=note,
    )


def record_scan(
    workspace: Any,
    *,
    store: ScanHistoryStore,
    recorded_at: datetime,
    universe: Sequence[str],
    timeframes: Mapping[Any, str],
) -> ScanComparison:
    """Project one completed workspace into a scan, remember it, and say what changed.

    Args:
        workspace: a `SwingWorkspace` that was produced successfully. A refresh
            whose scan failed never reaches here — there is no scan to remember,
            and inventing an empty one would put a fabricated baseline in the
            store.
        store: where history lives. Always explicit.
        recorded_at: when this record is being written. Supplied, never read
            from a clock here, so a test's history is deterministic.
        universe: the watchlist the scan was asked for, in scan order.
        timeframes: the role→interval mapping it was run under.
    """
    current = scan_record_from(
        workspace,
        recorded_at=recorded_at,
        universe=universe,
        timeframes=timeframes,
    )
    return compare_and_record(current, store=store)
