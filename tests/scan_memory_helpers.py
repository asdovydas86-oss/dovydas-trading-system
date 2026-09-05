"""Builders for the Slice 3 scan-memory tests. **Offline, clock-free, network-free.**

Two kinds of fixture, and the difference matters:

  * `record(...)` builds a `ScanRecord` from hand-written states. Cheap, exact,
    and the right tool for the store, the codec and the comparator's edges.
  * `live_record(...)` runs the **real** composition root — `setup_assessment_for_sheet`
    over seeded synthetic candles — through the **real** workspace builder and the
    **real** projection. Every controlled transition demonstrated in the Slice 3
    report goes through this path, so what is proved is what the product does
    rather than what a hand-built state made convenient.

The seed triples are `tests.swing_decision_helpers`' own, which is the point:
they are already known to reach four different exits of `evaluate_setup`, so a
transition between two of them is a transition the live engine really produces.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from fmis.scan_memory import (
    SCAN_MEMORY_SCHEMA_VERSION,
    ScanHistoryStore,
    ScanIdentity,
    ScanRecord,
    SymbolState,
    scan_record_from,
)

from tests.swing_decision_helpers import live
from tests.swing_workspace_helpers import workspace_of

__all__ = [
    "AT",
    "LATER",
    "TIMEFRAMES",
    "identity",
    "state",
    "record",
    "store_at",
    "live_record",
    "live_workspace",
]

AT = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
LATER = AT + timedelta(hours=4)

#: The role→interval mapping the fixtures declare they were run under. Written
#: out rather than imported so a change to the product default is a visible
#: comparability change in these tests rather than a silent one.
TIMEFRAMES: tuple[tuple[str, str], ...] = (
    ("context", "1w"),
    ("execution", "4h"),
    ("setup", "1d"),
)


def identity(
    *,
    universe: Sequence[str] = ("AAAUSDT",),
    reference_time: datetime = AT,
    timeframes: Sequence[tuple[str, str]] = TIMEFRAMES,
    schema_version: int = SCAN_MEMORY_SCHEMA_VERSION,
    analysis_as_of: datetime | None = None,
) -> ScanIdentity:
    return ScanIdentity(
        schema_version=schema_version,
        universe=tuple(universe),
        timeframes=tuple(timeframes),
        reference_time=reference_time,
        analysis_as_of=analysis_as_of,
    )


def state(symbol: str = "AAAUSDT", **overrides: Any) -> SymbolState:
    """One symbol state, with every field defaulted to something valid."""
    values: dict[str, Any] = {
        "symbol": symbol,
        "state": "wait",
        "classification": "read and declined",
        "sufficiency": "sufficient",
        "as_of": AT,
        "direction": None,
        "developing_state": "leaning",
        "developing_lean": "sideA",
        "blocker_kind": "context_regime_not_eligible",
        "blocker_observed": "ranging",
        "structural_trends": (("context", "ranging"), ("setup", "neutral")),
        "independence_established": False,
        "evidence_available": True,
        "supporting": 1,
        "conflicting": 0,
        "missing": 2,
        "unavailable": 0,
    }
    values.update(overrides)
    return SymbolState(**values)


def record(
    *states: SymbolState,
    universe: Sequence[str] | None = None,
    reference_time: datetime = AT,
    recorded_at: datetime | None = None,
    **identity_overrides: Any,
) -> ScanRecord:
    """A scan record over the supplied states.

    ``universe`` defaults to exactly the symbols supplied, which makes the
    record complete. Passing a wider one is how a test builds the incomplete
    scan that must never become a baseline.
    """
    covered = tuple(item.symbol for item in states)
    return ScanRecord(
        identity=identity(
            universe=covered if universe is None else universe,
            reference_time=reference_time,
            **identity_overrides,
        ),
        recorded_at=reference_time if recorded_at is None else recorded_at,
        symbols=states,
        unreadable=tuple(
            symbol
            for symbol in (covered if universe is None else universe)
            if symbol not in covered
        ),
    )


def store_at(tmp_path: Any, **options: Any) -> ScanHistoryStore:
    """A store rooted under a test's own tmp_path. **Never the owner's."""
    return ScanHistoryStore(tmp_path / "scan_memory", **options)


def live_workspace(*pairs: tuple[tuple[int, int, int], str], **options: Any) -> Any:
    """A real `SwingWorkspace` over the real composition root, offline."""
    return workspace_of(*(live(seeds, symbol) for seeds, symbol in pairs), **options)


def live_record(
    *pairs: tuple[tuple[int, int, int], str],
    recorded_at: datetime = AT,
    universe: Sequence[str] | None = None,
    timeframes: dict[str, str] | None = None,
    **options: Any,
) -> ScanRecord:
    """A record produced by the real projection over a real workspace."""
    workspace = live_workspace(*pairs, **options)
    return scan_record_from(
        workspace,
        recorded_at=recorded_at,
        universe=tuple(symbol for _, symbol in pairs) if universe is None else universe,
        timeframes=dict(TIMEFRAMES) if timeframes is None else timeframes,
    )
