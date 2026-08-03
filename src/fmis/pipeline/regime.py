"""Market Regime — the fourth composition root, adapting facts into a classification.

Beside `market_analysis`, `structural_facts` and `multi_timeframe` in the
application layer ADR-0007 §1 already defines. It adds **no engine**: it fetches
candles through the existing structural root, adapts the resulting sheet into a
`RegimeInput`, and hands it to `fmis.market_regime`.

    structural_facts_for_symbol(...)   ──►  StructuralFactSheet
            │  regime_input_from_sheet — the adapter, and the whole boundary
            ▼
    RegimeInput  ──►  classify_regime  ──►  MarketRegime

**The adapter exists so the engine never sees a fact sheet.** ADR-0007 puts this
layer at the top of the graph and forbids anything below importing it. An engine
that read `StructuralFactSheet` to pull six numbers off it would invert that for
no gain, so the narrow model is what crosses the boundary — and it is narrow
enough to build in a test from seven floats.

**No arithmetic here.** A test asserts this module contains no arithmetic
operator at all, the same rule `structural_facts` follows. Every comparison the
regime needs — bars since a change of character, the true-range ratio — is the
engine's to compute, which is why `RegimeInput` carries indices rather than a
distance.

**Multi-timeframe regime is per view, never across views.** ADR-0023 fixed that
nothing may be derived from the combination of timeframes, and a regime that
reconciled three views would be exactly the synthesis that ADR forbids. Each view
is classified alone and keeps its own identity, `as_of` and evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

from fmis.features.indicators.atr import AverageTrueRange
from fmis.features.indicators.ema import ExponentialMovingAverage
from fmis.features.volume import RelativeVolume
from fmis.features.types import Feature
from fmis.market_regime import (
    MarketRegime,
    RegimeInput,
    RegimePolicy,
    classify_regime,
)
from fmis.pipeline.multi_timeframe import (
    DEFAULT_TIMEFRAMES,
    TimeframeRole,
    multi_timeframe_facts_for_symbol,
    swing_features,
)
from fmis.pipeline.structural_facts import (
    DetectionSettings,
    Limitation,
    StructuralFactSheet,
    structural_facts_for_symbol,
)
from fmis.providers.binance import Transport

__all__ = [
    "regime_features",
    "regime_input_from_sheet",
    "regime_for_sheet",
    "regime_for_symbol",
    "RegimeView",
    "MultiTimeframeRegime",
    "multi_timeframe_regime_for_symbol",
    "REGIME_LIMITATIONS",
    "FAST_ATR_PERIOD",
    "SLOW_ATR_PERIOD",
]

#: The two true-range windows the volatility dimension compares. The fast one is
#: the repository's existing default; the slow one is its baseline. Both are the
#: **same indicator at two periods**, following AG's precedent when it added
#: EMA(200) to `swing_features()` — a second instance of a shipped feature, never
#: a new one invented to make the model look richer.
FAST_ATR_PERIOD = 14
SLOW_ATR_PERIOD = 50

#: The feature keys the adapter reads, taken from the feature objects themselves
#: rather than written out as strings. A hard-coded ``"ema_20"`` would survive a
#: rename in `fmis.features` and silently leave a dimension unavailable forever;
#: asking the feature for its own name makes that a collection error instead.
#: It also keeps this module from restating a name another package owns, which is
#: what the "no other package recomputes relative volume" guard is protecting.
_EMA_FAST = ExponentialMovingAverage(20).name
_EMA_SLOW = ExponentialMovingAverage(50).name
_ATR_FAST = AverageTrueRange(FAST_ATR_PERIOD).name
_ATR_SLOW = AverageTrueRange(SLOW_ATR_PERIOD).name
_PARTICIPATION_FEATURE = RelativeVolume(20).name

REGIME_LIMITATIONS: tuple[Limitation, ...] = (
    Limitation(
        "AI-1",
        "A regime describes the environment, never a direction. Trending does not "
        "mean rising, and which way structure points is a separate fact this "
        "classification deliberately does not restate.",
    ),
    Limitation(
        "AI-2",
        "Volatility and participation each rest on a single evidence family, so "
        "neither can be corroborated or contradicted within its own dimension; "
        "only structure requires two families to agree.",
    ),
    Limitation(
        "AI-3",
        "The thresholds are stated policy, not measurements. No backtest "
        "justifies them, because none exists yet; the policy is the object to "
        "sweep when one does.",
    ),
    Limitation(
        "AI-4",
        "Each timeframe is classified alone. Nothing is derived from the "
        "combination of views, so the three regimes are reported side by side "
        "and never reconciled.",
    ),
)


def regime_features() -> tuple[Feature, ...]:
    """`swing_features()` plus the slow true-range baseline the regime compares against.

    A second `AverageTrueRange` at a longer period, exactly as AG added a second
    `ExponentialMovingAverage`. Without it the volatility dimension has no
    baseline and reports `INSUFFICIENT` forever, which is why the regime surface
    computes its own set rather than reusing one that cannot answer the question.

    `default_features()` and `swing_features()` are both **unchanged**: adding a
    feature to either would change what `fmits facts` and `fmits mtf` compute and
    print, and neither command asked for it.
    """
    return (*swing_features(), AverageTrueRange(SLOW_ATR_PERIOD))


def _value(sheet: StructuralFactSheet, name: str) -> float | None:
    """One feature's value, or ``None`` when it is absent or still warming up.

    A missing feature and a warming-up feature are the same fact to this layer —
    the number is not available — and both must stay `None` rather than becoming
    a zero that a comparison would happily treat as real.
    """
    result = sheet.features.features.get(name)
    if result is None:
        return None
    value = result.value
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def regime_input_from_sheet(sheet: StructuralFactSheet) -> RegimeInput:
    """Adapt a structural fact sheet into the engine's narrow input model.

    Reads only what the three dimensions need, and reads each number exactly
    once. Nothing is recomputed: every value here was produced by an engine and
    is copied, not derived.

    Raises:
        TypeError: ``sheet`` is not a `StructuralFactSheet`.
    """
    if not isinstance(sheet, StructuralFactSheet):
        raise TypeError(
            f"sheet must be a StructuralFactSheet, got {type(sheet).__name__}"
        )
    structure = sheet.structure
    latest_change = structure.latest_change
    swings = structure.swings
    return RegimeInput(
        symbol=sheet.symbol,
        timeframe=sheet.interval,
        as_of=sheet.as_of,
        structural_trend=structure.trend,
        last_index=swings[-1].index if swings else None,
        latest_change_index=latest_change.index if latest_change is not None else None,
        close=sheet.window.last_close,
        ema_fast=_value(sheet, _EMA_FAST),
        ema_slow=_value(sheet, _EMA_SLOW),
        atr_fast=_value(sheet, _ATR_FAST),
        atr_slow=_value(sheet, _ATR_SLOW),
        participation_ratio=_value(sheet, _PARTICIPATION_FEATURE),
        metadata={"source": sheet.source, "interval": sheet.interval},
    )


def regime_for_sheet(
    sheet: StructuralFactSheet, *, policy: RegimePolicy | None = None
) -> MarketRegime:
    """Classify one already-built fact sheet. Pure — no network, no clock."""
    return classify_regime(regime_input_from_sheet(sheet), policy)


def regime_for_symbol(
    symbol: str,
    interval: str = "4h",
    *,
    limit: int | None = None,
    policy: RegimePolicy | None = None,
    detection: DetectionSettings | None = None,
    transport: Transport | None = None,
    clock: Any = None,
    base_url: str | None = None,
) -> tuple[StructuralFactSheet, MarketRegime]:
    """Fetch one timeframe and classify it, returning both the facts and the regime.

    The sheet is returned beside the regime deliberately: a classification the
    reader cannot check against the facts behind it is the opaque call `ARCH` §9
    exists to replace.
    """
    sheet = structural_facts_for_symbol(
        symbol,
        interval,
        limit=limit,
        features=regime_features(),
        detection=detection,
        transport=transport,
        clock=clock,
        base_url=base_url,
    )
    return sheet, regime_for_sheet(sheet, policy=policy)


@dataclass(frozen=True, slots=True)
class RegimeView:
    """One role, its interval, and that timeframe's regime — never a combination."""

    role: TimeframeRole
    interval: str
    regime: MarketRegime


@dataclass(frozen=True, slots=True)
class MultiTimeframeRegime:
    """Three role-labelled regimes, reported side by side.

    Carries no agreement, alignment, consensus or dominant view, for the reason
    ADR-0023 fixed for the multi-timeframe fact sheet: reconciling timeframes
    that disagree is a decision no layer in this repository has been asked to
    make, and emitting one here would make it silently.
    """

    symbol: str
    source: str
    views: tuple[RegimeView, ...]
    policy: RegimePolicy
    limitations: tuple[Limitation, ...]
    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not self.views:
            raise ValueError("a multi-timeframe regime needs at least one view")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def by_role(self) -> Mapping[TimeframeRole, RegimeView]:
        """Lookup by role — a projection over ``views``, never a second store."""
        return MappingProxyType({view.role: view for view in self.views})

    @property
    def newest_as_of(self) -> datetime:
        """The newest ``as_of`` across the views. **Not a shared instant.**"""
        return max(view.regime.as_of for view in self.views)


def multi_timeframe_regime_for_symbol(
    symbol: str,
    *,
    timeframes: Mapping[TimeframeRole, str] | None = None,
    limit: int | None = None,
    policy: RegimePolicy | None = None,
    detection: DetectionSettings | None = None,
    transport: Transport | None = None,
    clock: Any = None,
    base_url: str | None = None,
) -> tuple[Any, MultiTimeframeRegime]:
    """One regime per role, classified independently, reported side by side.

    Delegates the fetching and composition to `multi_timeframe_facts_for_symbol`
    so there is exactly one multi-timeframe root, then classifies each view on
    its own. Returns the fact sheet beside the regimes for the same reason
    `regime_for_symbol` does.
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
    views = tuple(
        RegimeView(
            role=view.role,
            interval=view.interval,
            regime=regime_for_sheet(view.sheet, policy=policy),
        )
        for view in sheet.views
    )
    return sheet, MultiTimeframeRegime(
        symbol=sheet.symbol,
        source=sheet.source,
        views=views,
        policy=views[0].regime.policy,
        limitations=REGIME_LIMITATIONS,
        metadata={"intervals": sheet.intervals},
    )

