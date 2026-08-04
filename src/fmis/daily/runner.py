"""Running the existing swing analysis across a requested universe.

    require_symbols(symbols)
            │  one call to workspace_for_symbol per symbol, in input order
            ▼
    SymbolResult per symbol  ──►  DailyRun

**This module adds no engine and computes no market quantity.** It calls
`fmis.workspace.workspace_for_symbol` once per symbol — the same root
`fmits swing` uses — so a daily row and a full page are produced by identical
code and cannot disagree.

**Every symbol produces exactly one result.** An expected, user-actionable
failure becomes a `SymbolResult` carrying its reason; the run continues. One
instrument's outage is not a reason to discard the other nineteen, and a daily
routine that aborts on the first bad symbol is a routine nobody runs twice.

**An unexpected exception is not caught.** Only the provider, ingestion and
insufficient-data failures listed in `_FAILURE_KINDS` are converted. A
`KeyError` from a bug in this repository propagates and stops the run, because a
report that renders an internal defect as an ordinary market failure teaches the
owner to ignore both.

**Sequential, deliberately.** Three provider calls per symbol at up to fifty
symbols is a hundred and fifty requests; running them concurrently would buy
wall-clock at the cost of provider rate-limit exposure, non-deterministic
interleaving of failures, and a much harder error-isolation story — for a
universe a human reads in one sitting. The cost is measured in the design
record, and it is dominated by the network either way.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from types import MappingProxyType
from typing import Any, Callable

from fmis.daily.models import (
    DailyRun,
    FailureKind,
    ResultCategory,
    SymbolFailure,
    SymbolResult,
    require_symbols,
)
from fmis.decision_context import ContextPolicy, ContextState
from fmis.ingest import IngestError
from fmis.market_regime import RegimePolicy
from fmis.pipeline.multi_timeframe import DEFAULT_TIMEFRAMES, TimeframeRole
from fmis.pipeline.structural_facts import DetectionSettings
from fmis.pipeline.market_analysis import InsufficientDataError
from fmis.providers.binance import (
    BinanceAPIError,
    BinanceRequestError,
    BinanceResponseError,
    BinanceTransportError,
    Transport,
)
from fmis.trading_context import TradingObjective
from fmis.workspace import SectionId, workspace_for_symbol

__all__ = ["run_daily", "DAILY_LIMITATIONS", "analyse_symbol"]

#: Which exceptions are *expected* and therefore become results, and what each
#: means to the caller. Written as an ordered tuple rather than a mapping,
#: because `BinanceRequestError` and `BinanceResponseError` are both
#: `ValueError`s and the first match must be the specific one.
#:
#: Anything absent from this list is a defect, not a market condition, and is
#: allowed to propagate.
_FAILURE_KINDS: tuple[tuple[type[Exception], FailureKind], ...] = (
    (BinanceRequestError, FailureKind.INVALID_SYMBOL),
    (BinanceAPIError, FailureKind.INVALID_SYMBOL),
    (BinanceResponseError, FailureKind.MALFORMED_DATA),
    (IngestError, FailureKind.MALFORMED_DATA),
    (BinanceTransportError, FailureKind.PROVIDER_FAILURE),
    (InsufficientDataError, FailureKind.INSUFFICIENT_DATA),
)

#: Which `ContextState` produces which category. A mapping rather than a chain
#: of comparisons, so a new state added to `fmis.decision_context` fails here
#: loudly instead of being silently binned as one of the existing three.
_CATEGORY_OF: Mapping[ContextState, ResultCategory] = MappingProxyType({
    ContextState.SUFFICIENT: ResultCategory.SUFFICIENT,
    ContextState.LIMITED: ResultCategory.LIMITED,
    ContextState.INSUFFICIENT: ResultCategory.INSUFFICIENT,
})

DAILY_LIMITATIONS: tuple[tuple[str, str], ...] = (
    (
        "AN-1",
        "This is a readiness index, not a ranking. Symbols appear in the order "
        "they were requested, and nothing here says which is worth attention.",
    ),
    (
        "AN-2",
        "A decision-context state describes whether an analysis rests on enough "
        "data. It is not an opportunity, a direction or a recommendation.",
    ),
    (
        "AN-3",
        "Each symbol is fetched and analysed independently at a different "
        "instant. The run has no shared as-of, and rows are not comparable in "
        "time.",
    ),
    (
        "AN-4",
        "A failed symbol reports why it failed and nothing more. No cached or "
        "previous analysis is substituted for it.",
    ),
)


def _regime_line(workspace: Any) -> str | None:
    """The primary view's regime dimensions, read from the page's own summary.

    Read rather than recomputed, so a daily row and the full page cannot
    disagree about what the regime was. Returns ``None`` when the section
    produced no summary, which the renderer shows as an absence.
    """
    section = workspace.by_id[SectionId.REGIME]
    if not section.summary:
        return None
    primary = workspace.metadata.get("primary_role")
    if primary:
        for line in section.summary:
            if line.startswith(primary):
                return line.split(": ", 1)[-1]
    return section.summary[0].split(": ", 1)[-1]


def _classify(error: Exception) -> FailureKind | None:
    """Which expected failure this is, or ``None`` when it is a defect."""
    for exception_type, kind in _FAILURE_KINDS:
        if isinstance(error, exception_type):
            return kind
    return None


def analyse_symbol(
    symbol: str,
    *,
    timeframes: Mapping[TimeframeRole, str] | None = None,
    limit: int | None = None,
    objective: TradingObjective = TradingObjective.SWING_TRADE,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
    detection: DetectionSettings | None = None,
    transport: Transport | None = None,
    clock: Any = None,
    base_url: str | None = None,
    timer: Callable[[], float] = time.perf_counter,
) -> SymbolResult:
    """Analyse one symbol, converting an expected failure into a result.

    The single place the try/except lives, so every symbol is isolated the same
    way and the run loop contains no error handling of its own.

    ``timer`` is injected rather than read, so a test can produce a deterministic
    duration without patching a module.

    Raises:
        Exception: anything not listed in `_FAILURE_KINDS`. A defect must stay a
            defect.
    """
    started = timer()
    try:
        _, workspace = workspace_for_symbol(
            symbol,
            timeframes=timeframes,
            limit=limit,
            objective=objective,
            policy=policy,
            context_policy=context_policy,
            detection=detection,
            transport=transport,
            clock=clock,
            base_url=base_url,
        )
    except Exception as error:  # noqa: BLE001 - re-raised unless expected
        kind = _classify(error)
        if kind is None:
            raise
        return SymbolResult(
            requested_symbol=symbol,
            category=ResultCategory.FAILED,
            failure=SymbolFailure(
                kind=kind,
                detail=str(error),
                exception_type=type(error).__name__,
            ),
            duration_seconds=timer() - started,
        )

    context = workspace.by_id[SectionId.CONTEXT]
    state = ContextState(workspace.metadata["context_state"])
    regime_summary = _regime_line(workspace)
    return SymbolResult(
        requested_symbol=symbol,
        category=_CATEGORY_OF[state],
        resolved_symbol=workspace.symbol,
        workspace=workspace,
        context=context,
        regime_summary=regime_summary,
        duration_seconds=timer() - started,
    )


def run_daily(
    symbols: Sequence[str],
    *,
    reference_time: datetime,
    timeframes: Mapping[TimeframeRole, str] | None = None,
    limit: int | None = None,
    objective: TradingObjective = TradingObjective.SWING_TRADE,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
    detection: DetectionSettings | None = None,
    transport: Transport | None = None,
    clock: Any = None,
    base_url: str | None = None,
    timer: Callable[[], float] = time.perf_counter,
) -> DailyRun:
    """Analyse every requested symbol and return one run.

    Args:
        symbols: the universe, in the order it should be reported. Validated by
            `require_symbols`: no blanks, no repeats, at most `MAXIMUM_SYMBOLS`.
        reference_time: supplied by the outer boundary. This module reads no
            clock, so two runs over the same stored candles are identical.
        timeframes, limit, objective, policy, context_policy, detection: applied
            **identically to every symbol**. There is deliberately no per-symbol
            override: a run whose members were analysed under different settings
            is a run whose rows cannot be compared, and the comparison is the
            product.

    Returns:
        A `DailyRun` with exactly one result per requested symbol, in input order.

    Raises:
        TypeError, DailyRunError: the universe is invalid — a caller error, and
            the only kind of failure that stops a run before it starts.
    """
    if not isinstance(reference_time, datetime):
        raise TypeError(
            f"reference_time must be a datetime, got {type(reference_time).__name__}"
        )
    requested = require_symbols(symbols)
    # Resolved once, here, rather than left to each call's own default. The run
    # records the intervals it used, and recording `("", "", "")` for a run that
    # in fact read 1w/1d/4h is a provenance claim that is simply false.
    intervals = dict(timeframes) if timeframes else dict(DEFAULT_TIMEFRAMES)

    results = tuple(
        analyse_symbol(
            symbol,
            timeframes=intervals,
            limit=limit,
            objective=objective,
            policy=policy,
            context_policy=context_policy,
            detection=detection,
            transport=transport,
            clock=clock,
            base_url=base_url,
            timer=timer,
        )
        for symbol in requested
    )

    return DailyRun(
        reference_time=reference_time,
        results=results,
        objective=objective.value,
        source="binance-spot",
        limitations=DAILY_LIMITATIONS,
        metadata={
            "requested": requested,
            "intervals": tuple(intervals[role] for role in TimeframeRole),
        },
    )
