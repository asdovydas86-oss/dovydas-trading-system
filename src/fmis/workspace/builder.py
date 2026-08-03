"""Assembling one `Workspace` from the composition roots that already exist.

    multi_timeframe_facts_for_symbol   ──►  three StructuralFactSheets  (AF/AG/AH)
              │                                     │
              │                                     ├──►  classify_regime      (AI)
              │                                     └──►  build_evidence_report
              ▼                                              (decision_support)
    detect_conflicts  ──►  WorkspaceInputs  ──►  build_sections  ──►  Workspace

**This module adds no engine and computes no market quantity.** It fetches once
per timeframe through the existing multi-timeframe root, adapts what came back,
and hands the result to providers. Every number on the page was produced by a
layer below.

**The evidence adapter is the milestone's one genuinely new join.**
`build_evidence_report` needs an `AnalysisSnapshot`, and a `StructuralFactSheet`
already carries every field one requires — symbol, interval, `as_of`, window and
features. Building the snapshot from the sheet therefore costs **no additional
fetch and no recomputation**; it is the same adapter pattern `regime_input_from_sheet`
established in Milestone AI, and it is what finally makes `fmis.decision_support`
reachable from a product surface.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fmis.decision_support import EvidenceReport, build_evidence_report
from fmis.market_regime import MarketRegime, RegimePolicy
from fmis.pipeline.market_analysis import AnalysisSnapshot
from fmis.pipeline.multi_timeframe import (
    DEFAULT_TIMEFRAMES,
    MultiTimeframeFactSheet,
    TimeframeRole,
    multi_timeframe_facts_for_symbol,
)
from fmis.pipeline.regime import REGIME_LIMITATIONS, regime_features, regime_for_sheet
from fmis.pipeline.structural_facts import (
    LIMITATIONS,
    DetectionSettings,
    Limitation,
    StructuralFactSheet,
)
from fmis.providers.binance import Transport
from fmis.trading_context import TradingObjective
from fmis.workspace.conflicts import detect_conflicts
from fmis.workspace.models import Workspace
from fmis.workspace.sections import WorkspaceInputs, build_sections

__all__ = [
    "WORKSPACE_LIMITATIONS",
    "PRIMARY_ROLE",
    "snapshot_from_sheet",
    "build_workspace",
    "workspace_for_symbol",
]

#: The role whose timeframe the objective treats as primary. `SPEC` §5 assigns
#: the setup timeframe that job for swing trading — 1D by default — and
#: `TradingAnalysisContext` already models the same distinction. Levels and
#: evidence are reported for this view; every view's regime and structure is
#: shown regardless, so nothing is hidden by the choice.
PRIMARY_ROLE = TimeframeRole.SETUP

WORKSPACE_LIMITATIONS: tuple[Limitation, ...] = (
    Limitation(
        "AK-1",
        "Evidence covers price-derived families only. Macro, news, sentiment and "
        "liquidity are catalogued concepts with no engine in this repository, so "
        "their absence is a gap in coverage rather than an absence of the thing.",
    ),
    Limitation(
        "AK-2",
        "Conflicts are reported and never resolved. No rule here outranks "
        "another, and no timeframe is weighted above another.",
    ),
    Limitation(
        "AK-3",
        "Risk, portfolio, trade plan and interpretation are not computed. Those "
        "sections render as unavailable and nothing on this page substitutes for "
        "them.",
    ),
    Limitation(
        "AK-4",
        "Evidence and levels describe the primary timeframe only. The other "
        "views contribute regime and structure, not evidence.",
    ),
)


def snapshot_from_sheet(sheet: StructuralFactSheet) -> AnalysisSnapshot:
    """Adapt a structural fact sheet into the snapshot the evidence layer reads.

    A copy, never a computation: `AnalysisSnapshot` and `StructuralFactSheet`
    already agree on symbol, interval, ``as_of``, window and features, because
    both are built by the same application layer over the same fetch. Calling
    `analyze_symbol` instead would fetch the same candles a second time and could
    return a *different* window if a candle closed between the two calls — which
    would put two different `as_of` values on one page.

    Raises:
        TypeError: ``sheet`` is not a `StructuralFactSheet`.
    """
    if not isinstance(sheet, StructuralFactSheet):
        raise TypeError(
            f"sheet must be a StructuralFactSheet, got {type(sheet).__name__}"
        )
    return AnalysisSnapshot(
        symbol=sheet.symbol,
        interval=sheet.interval,
        as_of=sheet.as_of,
        window=sheet.window,
        features=sheet.features,
        metadata={"source": sheet.source, "adapted_from": "StructuralFactSheet"},
    )


def _evidence_for(sheet: StructuralFactSheet) -> EvidenceReport | None:
    """The evidence report for one view, or ``None`` when it cannot be built.

    `build_evidence_report` reads `window.last_close`, which is absent when a
    window held no closed candle. Returning ``None`` lets the section report a
    failure with a reason instead of raising and losing the whole page — every
    other section on it is still true.
    """
    if sheet.window.last_close is None:
        return None
    return build_evidence_report(snapshot_from_sheet(sheet))


def build_workspace(
    sheet: MultiTimeframeFactSheet,
    *,
    objective: TradingObjective = TradingObjective.SWING_TRADE,
    policy: RegimePolicy | None = None,
    primary_role: TimeframeRole = PRIMARY_ROLE,
    metadata: Mapping[str, Any] | None = None,
) -> Workspace:
    """Compose one workspace from an already-built multi-timeframe fact sheet.

    Pure — no network and no clock. Every input was fetched by the caller, which
    is what makes a workspace reproducible from stored candles and testable
    without a transport.

    Args:
        sheet: the multi-timeframe facts, as `multi_timeframe_facts_for_symbol`
            returns. Its views supply structure, levels, regime and evidence.
        objective: what kind of trading is in view. Recorded, never inferred —
            the same rule ADR-0009 applies to `TradingAnalysisContext`.
        policy: the regime policy to classify under; the engine's default when
            omitted. One policy classifies every view, so the three regimes are
            comparable.
        primary_role: whose timeframe supplies levels and evidence.
        metadata: recorded on the workspace unchanged.

    Raises:
        TypeError: an argument has the wrong type.
        ValueError: ``primary_role`` names a role the sheet does not carry.
    """
    if not isinstance(sheet, MultiTimeframeFactSheet):
        raise TypeError(
            f"sheet must be a MultiTimeframeFactSheet, got {type(sheet).__name__}"
        )
    if not isinstance(objective, TradingObjective):
        raise TypeError(
            f"objective must be a TradingObjective, got {type(objective).__name__}"
        )
    if not isinstance(primary_role, TimeframeRole):
        raise TypeError(
            f"primary_role must be a TimeframeRole, got {type(primary_role).__name__}"
        )
    if primary_role not in sheet.by_role:
        raise ValueError(
            f"primary_role {primary_role.value!r} is not among the sheet's views "
            f"({', '.join(role.value for role in sheet.by_role)})"
        )

    regimes: dict[TimeframeRole, MarketRegime] = {
        view.role: regime_for_sheet(view.sheet, policy=policy)
        for view in sheet.views
    }
    primary_sheet = sheet.by_role[primary_role].sheet
    evidence = _evidence_for(primary_sheet)
    primary_label = (
        f"{primary_role.value} · {sheet.by_role[primary_role].interval}"
    )

    conflicts = detect_conflicts(
        trends=[
            (view.role, view.interval, view.sheet.structure.trend)
            for view in sheet.views
        ],
        regimes=[
            (view.role, view.interval, regimes[view.role]) for view in sheet.views
        ],
        evidence=None if evidence is None else (primary_label, evidence),
    )

    inputs = WorkspaceInputs(
        symbol=sheet.symbol,
        objective=objective.value,
        source=sheet.source,
        sheet=sheet,
        regimes=regimes,
        primary_role=primary_role,
        conflicts=conflicts,
        evidence=evidence,
        limitations=(*sheet.limitations, *REGIME_LIMITATIONS, *WORKSPACE_LIMITATIONS),
    )

    return Workspace(
        symbol=sheet.symbol,
        objective=objective.value,
        as_of=sheet.newest_as_of,
        source=sheet.source,
        sections=build_sections(inputs),
        metadata={
            "primary_role": primary_role.value,
            "intervals": sheet.intervals,
            "conflict_count": len(conflicts),
            **dict(metadata or {}),
        },
    )


def workspace_for_symbol(
    symbol: str,
    *,
    timeframes: Mapping[TimeframeRole, str] | None = None,
    limit: int | None = None,
    objective: TradingObjective = TradingObjective.SWING_TRADE,
    policy: RegimePolicy | None = None,
    primary_role: TimeframeRole = PRIMARY_ROLE,
    detection: DetectionSettings | None = None,
    transport: Transport | None = None,
    clock: Any = None,
    base_url: str | None = None,
) -> tuple[MultiTimeframeFactSheet, Workspace]:
    """Fetch every timeframe once and compose the workspace over them.

    Returns the fact sheet beside the workspace for the reason AI's root does:
    a page a reader cannot check against the facts beneath it is the opaque
    output this system exists to replace.

    The fetch is delegated to `multi_timeframe_facts_for_symbol`, so there is
    exactly one multi-timeframe root and this module adds no second one.
    """
    sheet = multi_timeframe_facts_for_symbol(
        symbol,
        timeframes=timeframes or DEFAULT_TIMEFRAMES,
        limit=limit,
        features=regime_features(),
        detection=detection,
        transport=transport,
        clock=clock,
        base_url=base_url,
    )
    return sheet, build_workspace(
        sheet, objective=objective, policy=policy, primary_role=primary_role
    )


#: Kept so a reader of this module sees which limitations the page inherits
#: without following two imports. Not re-exported: `LIMITATIONS` belongs to AF.
_INHERITED = LIMITATIONS
