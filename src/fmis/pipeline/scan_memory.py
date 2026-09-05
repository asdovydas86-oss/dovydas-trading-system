"""Wiring scan memory into a dashboard refresh. **The one place that writes it.**

    refresh_with_scan_memory(...)  ──►  OperatorDashboardSnapshot with `scan_change`

**Why the wiring lives here and not in `fmis.operator_dashboard`.** That package
writes nothing, anywhere, by any means, and three guard tests assert it — no
store verb, no `open`, no filesystem call. Scan memory has to write, so the seam
that writes is placed one layer up, in the application layer that is allowed to
orchestrate: the refresh is performed, the workspace it produced is captured, the
scan is recorded, and the comparison is handed to the snapshot as an already-
computed view. That is the same discipline `--lab-artifact`, `--geometry-artifact`
and `--validation-artifact` already follow — decoded by the caller, handed to the
dashboard already parsed — applied to the one input that is produced per refresh
rather than once at startup.

**A page GET can never reach this function.** `SnapshotHolder` calls its refresher
on a warm-up, on `?refresh=1` and on the first request of an unwarmed server, and
returns the held snapshot for everything else. Rendering does not refresh, so it
does not record — asserted twice: offline, by rendering three routes four times
and watching the record count; and in a real process, by the startup smoke test
loading three routes over a real socket.

**A failed scan records nothing.** When the workspace read raised, `refresh`
returns a snapshot whose swing section carries the failure and this function has
no workspace to project — so there is no partial record, and the last complete
scan stays the baseline it was.

**A failure to remember never costs the analysis.** `record_scan` already absorbs
a corrupt history and a refused write. The one thing that could still escape is a
scan this package cannot *project* at all, and that is caught here and rendered
as *history unavailable* rather than allowed to take a working page down. The
type caught is named — `ScanMemoryError`, never `Exception` — so a defect
anywhere else still surfaces as one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fmis.operator_dashboard.compose import (
    DEFAULT_WORKSPACE_RUNNER,
    refresh as refresh_snapshot,
)
from fmis.operator_dashboard.models import OperatorDashboardSnapshot
from fmis.operator_dashboard.sections import scan_change_view
from fmis.pipeline.multi_timeframe import DEFAULT_TIMEFRAMES
from fmis.scan_memory import (
    DEFAULT_RETAINED_SCANS,
    ComparisonStatus,
    ScanComparison,
    ScanHistoryStore,
    ScanMemoryError,
    default_scan_memory_root,
    record_scan,
)
from fmis.swing_setup import SCAN_UNIVERSE

__all__ = ["build_scan_history_store", "refresh_with_scan_memory"]


def build_scan_history_store(
    root: Path | str | None = None, *, retain: int = DEFAULT_RETAINED_SCANS
) -> ScanHistoryStore:
    """The owner's scan history, or an explicit root.

    ``None`` resolves the owner-level default — outside the git checkout, beside
    the archive and the durable store. Resolving it *here* rather than inside
    `ScanHistoryStore` is deliberate: the store never falls back to a default on
    its own, so no test can reach the owner's real history by omission.
    """
    return ScanHistoryStore(
        default_scan_memory_root() if root is None else root, retain=retain
    )


def refresh_with_scan_memory(
    *,
    refreshed_at: datetime,
    store: ScanHistoryStore,
    symbols: Sequence[str] | None = None,
    timeframes: Mapping[Any, str] | None = None,
    refresher: Callable[..., OperatorDashboardSnapshot] = refresh_snapshot,
    workspace_runner: Callable[..., Any] = DEFAULT_WORKSPACE_RUNNER,
    recorder: Callable[..., Any] = record_scan,
    **options: Any,
) -> OperatorDashboardSnapshot:
    """One refresh, remembered. **Read, compare, write, then render.**

    The workspace is captured through the injection seam `refresh` already has
    for it, so this function performs **no extra engine read**: the scan the
    dashboard renders and the scan that is remembered are one call, and a page
    and its history cannot disagree about what the market did.

    Args:
        refreshed_at: when this refresh happened, and when the record is written.
        store: where history lives. Always explicit — see
            `build_scan_history_store`.
        symbols: the watchlist. `None` means the scanner's own `SCAN_UNIVERSE`,
            which is also what `refresh` passes on; the universe recorded is the
            one actually scanned.
        timeframes: the role→interval mapping the scan ran under. `None` means
            `DEFAULT_TIMEFRAMES`, which is what the scan uses.
        refresher / workspace_runner / recorder: injected for tests. Production
            passes the real composition roots — and ``workspace_runner``
            defaults to `refresh`'s **own** default rather than naming
            `fmis.swing_workspace` again, so the scan that is remembered is by
            construction the scan the dashboard renders.

    Every remaining keyword is forwarded to `refresh` unchanged.
    """
    captured: list[Any] = []

    def capture(*args: Any, **kwargs: Any) -> Any:
        workspace = workspace_runner(*args, **kwargs)
        captured.append(workspace)
        return workspace

    snapshot = refresher(
        refreshed_at=refreshed_at,
        symbols=symbols,
        workspace_runner=capture,
        **options,
    )
    if not captured:
        # The scan failed. Its section says so, and nothing is recorded: a
        # partial history is worse than none, because it becomes a baseline.
        return snapshot

    try:
        comparison = recorder(
            captured[0],
            store=store,
            recorded_at=refreshed_at,
            universe=tuple(symbols) if symbols else SCAN_UNIVERSE,
            timeframes=DEFAULT_TIMEFRAMES if timeframes is None else timeframes,
        )
    except ScanMemoryError as error:
        # **The analysis is true; only the remembering failed.** `record_scan`
        # already absorbs a corrupt history and a refused write; what reaches
        # here is a scan this package could not even *project* — a universe that
        # does not match what was scanned, say. Letting it propagate would take
        # a working page down for a subsystem that only annotates it, which is
        # precisely what §20 forbids. The type is named, never `Exception`, so a
        # defect anywhere else still surfaces as one.
        comparison = ScanComparison(
            status=ComparisonStatus.HISTORY_UNAVAILABLE,
            current_scan_at=captured[0].reference_time,
            reason=(
                f"This scan could not be recorded: {error} The analysis on this "
                "page is unaffected."
            ),
            recorded=False,
            recording_note=(
                "Scan memory is unavailable for this refresh. Nothing was "
                "recorded, so the next refresh has nothing to compare against."
            ),
        )
    return replace(snapshot, scan_change=scan_change_view(comparison))
