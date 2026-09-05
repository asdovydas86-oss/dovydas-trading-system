"""`SwingWorkspace` → `ScanRecord`. **The narrowest projection that answers the
operator's change questions, and not one field wider.**

**What is deliberately not persisted.** Evidence items, thesis lines, regime
prose, directional factors, confirmation and invalidation text, provider
payloads, candles and rendered HTML. Every one of them exists on the workspace
and every one of them is either prose (which §11 forbids comparing) or a copy of
the market-data archive (which §10 forbids duplicating). What is kept is the
handful of named states an engine already decided.

**Timestamps are carried and never compared.** ``as_of`` is the assessment
instant the surfaces print beside a previous state; the comparator does not read
it. Per-role reading instants, ages and closed-bar counts are not persisted at
all — they advance because time advances, and the cheapest way to guarantee they
never become a *change* is to make them invisible to the thing that computes
changes.

**Duck-typed on purpose.** ``developing`` and ``blocker`` arrive as `Any` on
`SymbolDecision`, because ADR-0028 makes `fmis.swing_setup` the one package
permitted to spell a side. Their enum members are read at runtime — the same
arrangement, and the same reason, as `fmis.operator_dashboard.sections`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from fmis.scan_memory.models import (
    SCAN_MEMORY_SCHEMA_VERSION,
    ScanIdentity,
    ScanMemoryError,
    ScanRecord,
    SymbolState,
)

__all__ = ["scan_identity_for", "symbol_state_of", "scan_record_from"]


def _value(member: Any) -> str | None:
    """An enum member's own value, read at runtime. `None` stays `None`."""
    if member is None:
        return None
    return getattr(member, "value", None) or str(member)


def scan_identity_for(
    workspace: Any,
    *,
    universe: Sequence[str],
    timeframes: Mapping[Any, str],
) -> ScanIdentity:
    """The identity of the scan that produced ``workspace``.

    ``universe`` is the watchlist the scan was **asked** for and ``timeframes``
    the role→interval mapping it was run under. Both are supplied by the caller
    rather than recovered from the workspace, because the workspace carries what
    was *read* and comparability is a property of what was *requested*: a scan
    that lost a symbol to an outage is the same experiment as the one before it,
    and a scan of a different watchlist is not.
    """
    roles = tuple(
        sorted((_value(role) or str(role), interval) for role, interval in timeframes.items())
    )
    return ScanIdentity(
        schema_version=SCAN_MEMORY_SCHEMA_VERSION,
        universe=tuple(universe),
        timeframes=roles,
        reference_time=workspace.reference_time,
        analysis_as_of=workspace.summary.analysis_as_of,
    )


def symbol_state_of(decision: Any) -> SymbolState:
    """One `SymbolDecision`, reduced to the states a change can be reported on."""
    developing = decision.developing
    blocker = decision.blocker
    return SymbolState(
        symbol=decision.symbol,
        state=decision.state,
        classification=decision.classification,
        sufficiency=decision.sufficiency,
        as_of=decision.as_of,
        direction=decision.direction,
        developing_state=None if developing is None else _value(developing.state),
        developing_lean=None if developing is None else _value(developing.lean),
        blocker_kind=None if blocker is None else _value(blocker.kind),
        blocker_observed="" if blocker is None else blocker.observed,
        structural_trends=tuple(
            (line.role, line.structural_trend) for line in decision.timeframes
        ),
        independence_established=decision.independence_established,
        evidence_available=decision.evidence_available,
        supporting=len(decision.supporting),
        conflicting=len(decision.conflicting),
        missing=len(decision.missing),
        unavailable=len(decision.unavailable),
    )


def scan_record_from(
    workspace: Any,
    *,
    recorded_at: datetime,
    universe: Sequence[str],
    timeframes: Mapping[Any, str],
) -> ScanRecord:
    """One completed scan, ready to be remembered.

    **Pure.** No clock, no filesystem, no provider: ``recorded_at`` is supplied,
    exactly as every composition root in this repository requires, so two
    projections over the same workspace and the same instant are equal.

    Raises:
        ScanMemoryError: the workspace carries a decision for a symbol its
            universe never asked for. That is a defect in the caller's universe
            argument, and recording it would make the record's own coverage
            check meaningless.
    """
    identity = scan_identity_for(workspace, universe=universe, timeframes=timeframes)
    symbols = tuple(symbol_state_of(decision) for decision in workspace.decisions)
    requested = set(identity.universe)
    unknown = sorted({state.symbol for state in symbols} - requested)
    if unknown:
        raise ScanMemoryError(
            f"the scan produced decisions for {unknown}, which its universe "
            f"{identity.universe} never asked for; the universe passed here must "
            "be the watchlist the scan was run with"
        )
    covered = {state.symbol for state in symbols}
    unreadable = tuple(
        symbol for symbol in identity.universe if symbol not in covered
    )
    return ScanRecord(
        identity=identity,
        recorded_at=recorded_at,
        symbols=symbols,
        unreadable=unreadable,
    )
