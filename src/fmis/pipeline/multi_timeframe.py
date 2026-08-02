"""Multi-Timeframe Fact Sheet — one symbol, several role-labelled timeframes.

The third composition root in the application layer, beside `market_analysis` and
`structural_facts`. It composes **N role-labelled views** of one symbol into one
immutable sheet, and does nothing else:

    structural_facts_for_symbol(symbol, "1w", ...)   -> CONTEXT view
    structural_facts_for_symbol(symbol, "1d", ...)   -> SETUP view
    structural_facts_for_symbol(symbol, "4h", ...)   -> EXECUTION view

**No engine is added and no calculation is defined here.** Every number on every
view was produced by `structural_facts_for_symbol`, which this module calls once
per timeframe and never reaches past. A test asserts the module contains **no
arithmetic operator at all**, matching `structural_facts`.

**Why a role and not just an interval.** `PROJECT_SPECIFICATION_V1.md` §5 assigns
timeframes *roles* — a higher timeframe for structural context, a middle one for
setup development, a lower one for entry timing — and requires that the system
"avoid mixing timeframe signals without explaining their role". A view therefore
carries its role explicitly. The role is **never inferred from the interval**,
for the reason ADR-0009 gives about trading objectives: guessing would silently
decide the very thing the caller is stating. A caller wanting 1D as context and
4H as setup says so.

**No cross-timeframe synthesis. This is the load-bearing decision.**
The sheet reports each view's facts side by side and derives *nothing* from their
combination — no "aligned", no "conflicting", no agreement flag, no score, no
count of how many trends match. Classifying the *combination* of timeframes is a
statement about market state, which belongs to the Market Regime Engine. Emitting
it here would put the first interpretation into the application layer and
pre-empt a layer that does not exist yet.

`SPEC` §5 states the case this protects, and live data reproduces it: a weekly
`sustained_higher` with a daily `neutral` and a 4H `sustained_lower` "is different
from simply calling the asset bullish". The reader sees three facts and draws the
conclusion; the system does not draw it for them.

**Views are not aligned in time, and must not be.** Each view is fetched
independently and has its own ``as_of`` — a weekly view's newest closed bar can be
days old because the week has not closed, while a 4H view's is hours old. Every
view therefore keeps and reports its own timestamp. A single sheet-level instant
would imply a synchronisation that does not exist. `fmis.alignment` is not used:
it exists to make series comparable for *arithmetic*, and nothing here computes
across timeframes.

**Nothing partial.** If any requested timeframe cannot be analysed, the error
propagates and no sheet is returned. A sheet missing its context view would look
complete while answering a different question.

**The confirmation delay still has exactly one source.** One `DetectionSettings`
is built or accepted once and passed to every view, so the ADR-0020 D1 containment
established by `structural_facts` extends across all of them unchanged — this root
adds no second way to set the delay.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable

from fmis.features.indicators.ema import ExponentialMovingAverage
from fmis.features.types import Feature
from fmis.pipeline.market_analysis import default_features
from fmis.pipeline.structural_facts import (
    LIMITATIONS,
    BINANCE_SPOT,
    DetectionSettings,
    Limitation,
    StructuralFactSheet,
    structural_facts_for_symbol,
)
from fmis.providers.binance import Transport

__all__ = [
    "TimeframeRole",
    "TimeframeView",
    "MultiTimeframeFactSheet",
    "DEFAULT_TIMEFRAMES",
    "MULTI_TIMEFRAME_LIMITATIONS",
    "swing_features",
    "build_multi_timeframe_facts",
    "multi_timeframe_facts_for_symbol",
]


class TimeframeRole(Enum):
    """The job a timeframe does in one analysis — stated, never inferred.

    The three roles are `PROJECT_SPECIFICATION_V1.md` §5's framework: a higher
    timeframe for structural context, a middle one for setup development, and a
    lower one for entry timing. The typical crypto swing mapping is 1W/1D/4H, and
    §5 is explicit that this "is not a permanent universal rule" — which is why
    the role and the interval are two separate fields rather than one.

    Ordering is defined by `_ROLE_ORDER` rather than by definition order, so a
    member can be renamed without silently changing how a sheet is laid out.
    """

    CONTEXT = "context"
    SETUP = "setup"
    EXECUTION = "execution"


#: Canonical presentation order, highest timeframe first. Explicit rather than
#: derived from enum definition order, following `_SIDE_RANK` in
#: `fmis.level_crossing.models`: an ordering contract that rests on definition
#: order changes silently when a member is moved.
_ROLE_ORDER: Mapping[TimeframeRole, int] = MappingProxyType(
    {TimeframeRole.CONTEXT: 0, TimeframeRole.SETUP: 1, TimeframeRole.EXECUTION: 2}
)

#: The typical crypto swing mapping from `SPEC` §5. A default, not a rule — every
#: entry point accepts an explicit mapping.
DEFAULT_TIMEFRAMES: Mapping[TimeframeRole, str] = MappingProxyType(
    {
        TimeframeRole.CONTEXT: "1w",
        TimeframeRole.SETUP: "1d",
        TimeframeRole.EXECUTION: "4h",
    }
)

#: Limitations specific to reading several timeframes at once. Added to the six
#: inherited from `structural_facts`, never replacing them.
MULTI_TIMEFRAME_LIMITATIONS: tuple[Limitation, ...] = (
    Limitation(
        "AG-1",
        "Views are fetched at different instants and are not aligned; a higher "
        "timeframe's newest closed bar may be days old because its period has "
        "not closed. Each view reports its own as-of.",
    ),
    Limitation(
        "AG-2",
        "No cross-timeframe synthesis is performed. The views are reported side "
        "by side and nothing is derived from their combination; reconciling "
        "disagreement between them is a later layer's decision.",
    ),
    Limitation(
        "AG-3",
        "ema_200 needs 200 closed bars, which on a weekly view is roughly four "
        "years of history; where that is unavailable it reports as warming up "
        "rather than as a value.",
    ),
)


@dataclass(frozen=True, slots=True)
class TimeframeView:
    """One timeframe's fact sheet, plus the role it was asked to play.

    ``interval`` is carried alongside ``sheet.interval`` deliberately: it records
    what the *caller requested*, which a future provider could normalise
    (``"4h"`` vs ``"4H"``). Today they are equal and a test pins that; keeping
    both means a divergence would be visible rather than silent.
    """

    role: TimeframeRole
    interval: str
    sheet: StructuralFactSheet

    def __post_init__(self) -> None:
        if not isinstance(self.role, TimeframeRole):
            raise TypeError(
                f"role must be a TimeframeRole, got {type(self.role).__name__}"
            )
        if not isinstance(self.interval, str) or not self.interval:
            raise TypeError("interval must be a non-empty string")
        if not isinstance(self.sheet, StructuralFactSheet):
            raise TypeError(
                "sheet must be a StructuralFactSheet, got "
                f"{type(self.sheet).__name__}"
            )


@dataclass(frozen=True, slots=True)
class MultiTimeframeFactSheet:
    """Several role-labelled views of one symbol, reported side by side.

    ``newest_as_of`` is the **most recent** ``as_of`` across the views. It is a
    convenience for a reader asking "how fresh is any of this", explicitly **not**
    a shared observation instant: the views are not synchronised and each one
    carries its own timestamp. A field named ``as_of`` was rejected for exactly
    that reason — it would read as a property of the sheet.

    Deliberately absent: any agreement, alignment, conflict or consensus field.
    See the module docstring.
    """

    symbol: str
    source: str
    views: tuple[TimeframeView, ...]
    newest_as_of: datetime
    limitations: tuple[Limitation, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.views:
            raise ValueError("a multi-timeframe sheet needs at least one view")
        roles = [view.role for view in self.views]
        if len(set(roles)) != len(roles):
            raise ValueError(f"each role may appear once, got {[r.value for r in roles]}")
        if roles != sorted(roles, key=_ROLE_ORDER.__getitem__):
            raise ValueError("views must be ordered context, setup, execution")
        # Written as a comprehension rather than a set difference so the module
        # holds no arithmetic operator at all — set subtraction is `ast.Sub`, and
        # the invariant is easier to trust when it admits no exceptions.
        mismatched = sorted(
            {v.sheet.symbol for v in self.views if v.sheet.symbol != self.symbol}
        )
        if mismatched:
            raise ValueError(
                f"every view must be for {self.symbol!r}; found {mismatched}"
            )
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def by_role(self) -> Mapping[TimeframeRole, TimeframeView]:
        """The views keyed by role, for a caller that wants one of them."""
        return MappingProxyType({view.role: view for view in self.views})

    @property
    def intervals(self) -> tuple[str, ...]:
        """The requested intervals, in role order."""
        return tuple(view.interval for view in self.views)


def swing_features() -> tuple[Feature, ...]:
    """`default_features()` plus EMA(200) — the swing analyst's trend reference.

    EMA(200) is the most widely used long-horizon trend reference and the one a
    swing workflow reads first, so a multi-timeframe swing sheet without it is
    missing its headline number.

    It is added **here** rather than to `default_features()` on purpose.
    `default_features()` serves `analyze_symbol`, a general-purpose snapshot whose
    warm-up budget is small; EMA(200) needs 200 closed bars and would change what
    that function returns for every existing caller. Two named sets with stated
    purposes are clearer than one set meaning "whatever the last milestone
    needed".

    A fresh tuple is returned per call, so no feature instance is shared between
    analyses — the same contract `default_features()` holds.
    """
    return (*default_features(), ExponentialMovingAverage(200))


def build_multi_timeframe_facts(
    views: Mapping[TimeframeRole, StructuralFactSheet],
    *,
    intervals: Mapping[TimeframeRole, str] | None = None,
    source: str = "unknown",
    metadata: Mapping[str, Any] | None = None,
) -> MultiTimeframeFactSheet:
    """Assemble already-computed sheets into one role-ordered multi-timeframe sheet.

    Args:
        views: one `StructuralFactSheet` per role. At least one; roles are unique
            by construction of the mapping.
        intervals: the interval originally *requested* per role. Defaults to each
            sheet's own ``interval``.
        source: provenance for where the candles came from.
        metadata: extra request provenance, defensively copied.

    Returns:
        A `MultiTimeframeFactSheet` with views in canonical role order and
        ``newest_as_of`` set to the most recent view timestamp.

    Raises:
        TypeError: a key is not a `TimeframeRole`, or a value is not a
            `StructuralFactSheet`.
        ValueError: no views, or the views disagree about the symbol.

    Pure: no clock, no network, no randomness. Equal inputs give equal sheets.
    """
    if not views:
        raise ValueError("a multi-timeframe sheet needs at least one view")
    for role, sheet in views.items():
        if not isinstance(role, TimeframeRole):
            raise TypeError(
                f"view keys must be TimeframeRole, got {type(role).__name__}"
            )
        if not isinstance(sheet, StructuralFactSheet):
            raise TypeError(
                f"view for {role.value} must be a StructuralFactSheet, got "
                f"{type(sheet).__name__}"
            )

    requested = dict(intervals or {})
    ordered = tuple(
        TimeframeView(
            role=role,
            interval=requested.get(role, views[role].interval),
            sheet=views[role],
        )
        for role in sorted(views, key=_ROLE_ORDER.__getitem__)
    )
    symbols = {view.sheet.symbol for view in ordered}
    if len(symbols) != 1:
        raise ValueError(
            f"every view must describe one symbol, found {sorted(symbols)}"
        )

    return MultiTimeframeFactSheet(
        symbol=ordered[0].sheet.symbol,
        source=source,
        views=ordered,
        newest_as_of=max(view.sheet.as_of for view in ordered),
        limitations=(*LIMITATIONS, *MULTI_TIMEFRAME_LIMITATIONS),
        metadata=dict(metadata or {}),
    )


def multi_timeframe_facts_for_symbol(
    symbol: str,
    *,
    timeframes: Mapping[TimeframeRole, str] | None = None,
    limit: int | None = None,
    features: Sequence[Feature] | None = None,
    detection: DetectionSettings | None = None,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
    base_url: str | None = None,
) -> MultiTimeframeFactSheet:
    """Fetch and analyse one symbol across several role-labelled timeframes.

    The network edge. Each view delegates wholly to `structural_facts_for_symbol`,
    so the fetch policy, the closed-candle rule, the feature computation and the
    whole structural chain keep exactly one implementation.

    Args:
        symbol: exact provider symbol, e.g. ``"BTCUSDT"``.
        timeframes: role → interval. `DEFAULT_TIMEFRAMES` when omitted.
        limit: candles to request per view; the provider default when omitted.
        features: features to run; `swing_features()` when omitted — a swing
            sheet's default differs from a general snapshot's.
        detection: swing window and confirmation delay. **One instance is used for
            every view**, so the ADR-0020 D1 containment holds across the sheet.
        transport, clock, base_url: forwarded to the provider, for tests.

    Returns:
        A `MultiTimeframeFactSheet`.

    Raises:
        InsufficientDataError: any requested timeframe has too few closed candles.
            Raised rather than skipped — **nothing partial**.
        BinanceError and subclasses: transport or request failures, unwrapped.

    Views are fetched **sequentially and independently**. No alignment is applied
    and none should be: nothing here computes across timeframes.
    """
    requested = dict(DEFAULT_TIMEFRAMES if timeframes is None else timeframes)
    if not requested:
        raise ValueError("at least one role → interval mapping is required")
    for role in requested:
        if not isinstance(role, TimeframeRole):
            raise TypeError(
                f"timeframe keys must be TimeframeRole, got {type(role).__name__}"
            )

    settings = DetectionSettings() if detection is None else detection
    chosen = swing_features() if features is None else features

    sheets: dict[TimeframeRole, StructuralFactSheet] = {}
    for role in sorted(requested, key=_ROLE_ORDER.__getitem__):
        sheets[role] = structural_facts_for_symbol(
            symbol,
            requested[role],
            limit=limit,
            features=chosen,
            detection=settings,
            transport=transport,
            clock=clock,
            base_url=base_url,
        )

    return build_multi_timeframe_facts(
        sheets,
        intervals=requested,
        source=BINANCE_SPOT,
        metadata={
            "requested_limit": limit,
            "requested_timeframes": tuple(
                (role.value, requested[role])
                for role in sorted(requested, key=_ROLE_ORDER.__getitem__)
            ),
        },
    )
