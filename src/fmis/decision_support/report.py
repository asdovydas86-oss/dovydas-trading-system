"""Build a structured evidence report from an `AnalysisSnapshot`.

Consumes a snapshot and nothing else: no fetching, no indicator math, no metric
math. Every number here was produced by an engine and is passed through; the one
derived value, ATR as a percentage of price, comes from `derived.py`, and every
classification comes from `classification.py`.

What the report is for: giving a human — or, later, an interpretation layer — the
facts already organised, so the reasoning step starts from structure instead of
from a bag of numbers. Organising evidence is not the same as forming a view, and
this layer stops firmly at the first.

What it will never contain: a direction to trade, a price target, a stop, a
position size, a confidence number, or a ranking. `OverallState` is deliberately
undirectional — `WATCH` says the available evidence agrees with itself, not that
anything should be bought or sold.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

from fmis.decision_support.classification import (
    Alignment,
    Comparison,
    RsiZone,
    Sign,
    alignment_of_comparison,
    alignment_of_sign,
    classify_comparison,
    classify_rsi_zone,
    classify_sign,
)
from fmis.decision_support.derived import atr_percent_of_close
from fmis.pipeline import AnalysisSnapshot

__all__ = [
    "build_evidence_report",
    "EvidenceReport",
    "MarketContext",
    "TrendEvidence",
    "MomentumEvidence",
    "VolatilityEvidence",
    "RelativeValueEvidence",
    "EvidenceGroups",
    "Observation",
    "Scenario",
    "OverallState",
    "EMA_FAST_FEATURE",
    "EMA_SLOW_FEATURE",
    "RSI_FEATURE",
    "ATR_FEATURE",
    "MACD_FEATURE",
    "MIN_DIRECTIONAL_OBSERVATIONS",
]

#: Feature names this report reads. They are the names `default_features()`
#: produces. A snapshot built from a different selection simply yields
#: `UNAVAILABLE` observations — a missing feature is reported, never inferred.
EMA_FAST_FEATURE = "ema_20"
EMA_SLOW_FEATURE = "ema_50"
RSI_FEATURE = "rsi_close_14"
ATR_FEATURE = "atr_14"
MACD_FEATURE = "macd_close_12_26_9"

#: Directional observations required before a state other than
#: `INSUFFICIENT_DATA` is reported. Three of five means a majority of the
#: directional evidence is actually present.
MIN_DIRECTIONAL_OBSERVATIONS = 3


class OverallState(str, Enum):
    """The report's only summary value. Carries no direction.

    * `WATCH` — enough directional evidence is available and it does not
      disagree with itself. It says "this is coherent enough to follow", not
      "this is going up".
    * `WAIT` — evidence is available but mixed, conflicting, or entirely neutral.
    * `INSUFFICIENT_DATA` — too few directional observations to say anything.
    """

    WATCH = "watch"
    WAIT = "wait"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True, slots=True)
class Observation:
    """One classified comparison, with the inputs that produced it.

    ``inverse`` is the classification this observation would carry if it flipped;
    it is what makes a deterioration condition mechanical rather than authored.
    It is ``None`` for observations that are not directional.
    """

    key: str
    classification: str
    alignment: Alignment
    inverse: str | None = None
    inputs: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.inputs, MappingProxyType):
            object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))

    @property
    def available(self) -> bool:
        return self.alignment is not Alignment.UNAVAILABLE

    @property
    def directional(self) -> bool:
        return self.alignment in (
            Alignment.UPWARD,
            Alignment.DOWNWARD,
            Alignment.NEUTRAL,
        )


@dataclass(frozen=True, slots=True)
class MarketContext:
    """What was analysed."""

    symbol: str
    interval: str
    as_of: datetime
    analysed_candle_count: int
    benchmark_symbol: str | None = None


@dataclass(frozen=True, slots=True)
class TrendEvidence:
    """Price and moving-average relationships. Classifications only, no verdict."""

    price_vs_ema_fast: Observation
    price_vs_ema_slow: Observation
    ema_fast_vs_ema_slow: Observation

    @property
    def observations(self) -> tuple[Observation, ...]:
        return (
            self.price_vs_ema_fast,
            self.price_vs_ema_slow,
            self.ema_fast_vs_ema_slow,
        )


@dataclass(frozen=True, slots=True)
class MomentumEvidence:
    """RSI band plus MACD relationships.

    ``rsi_zone`` is reported but never counted as directional evidence — see the
    `classification` module on why an oscillator band is not a direction.
    """

    rsi_value: float | None
    rsi_zone: Observation
    macd_vs_signal: Observation
    macd_histogram: Observation
    macd_line: float | None = None
    macd_signal_line: float | None = None

    @property
    def observations(self) -> tuple[Observation, ...]:
        return (self.rsi_zone, self.macd_vs_signal, self.macd_histogram)


@dataclass(frozen=True, slots=True)
class VolatilityEvidence:
    """ATR and its share of price. Magnitude only — never a direction."""

    atr_value: float | None
    last_close: float | None
    atr_percent_of_close: float | None

    @property
    def available(self) -> bool:
        return self.atr_percent_of_close is not None


@dataclass(frozen=True, slots=True)
class RelativeValueEvidence:
    """Benchmark comparison, restated from the snapshot's RVE results.

    Every value is copied from a `RelativeValueResult` the RVE already produced.
    Nothing here is recomputed. ``undefined_reasons`` maps a metric key to the
    reason the RVE gave for an UNDEFINED result, so an absent number always says
    why it is absent.
    """

    benchmark_symbol: str
    primary_return: float | None
    benchmark_return: float | None
    relative_return: float | None
    volatility_ratio: float | None
    correlation: float | None
    undefined_reasons: Mapping[str, str] = field(default_factory=dict)
    aligned_observation_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.undefined_reasons, MappingProxyType):
            object.__setattr__(
                self,
                "undefined_reasons",
                MappingProxyType(dict(self.undefined_reasons)),
            )


@dataclass(frozen=True, slots=True)
class EvidenceGroups:
    """Observations grouped by whether they agree with the dominant alignment."""

    supporting: tuple[Observation, ...]
    conflicting: tuple[Observation, ...]
    unavailable: tuple[Observation, ...]
    dominant_alignment: Alignment


@dataclass(frozen=True, slots=True)
class Scenario:
    """A named set of currently observable conditions. Not a prediction.

    ``conditions`` are mechanical restatements of observations — what would have
    to hold, or to change, for the scenario to remain describable. They contain
    no price level, no timing, and no likelihood.
    """

    name: str
    conditions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceReport:
    """The complete structured evidence for one snapshot."""

    context: MarketContext
    trend: TrendEvidence
    momentum: MomentumEvidence
    volatility: VolatilityEvidence
    groups: EvidenceGroups
    scenarios: Mapping[str, Scenario]
    state: OverallState
    relative_value: RelativeValueEvidence | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.scenarios, MappingProxyType):
            object.__setattr__(
                self, "scenarios", MappingProxyType(dict(self.scenarios))
            )
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


# ------------------------------------------------------------- observations ---


def _feature_value(snapshot: AnalysisSnapshot, name: str) -> Any:
    """The feature's value, or ``None`` when absent or still warming up.

    Both cases are genuinely "no value available", and the report says so the
    same way; the distinction is preserved in the report metadata.
    """
    result = snapshot.features.get(name)
    return None if result is None else result.value


def _comparison_observation(
    key: str,
    left: float | None,
    right: float | None,
    *,
    left_name: str,
    right_name: str,
) -> Observation:
    comparison = classify_comparison(left, right)
    inverse = {
        Comparison.ABOVE: Comparison.BELOW.value,
        Comparison.BELOW: Comparison.ABOVE.value,
    }.get(comparison)
    return Observation(
        key=key,
        classification=comparison.value,
        alignment=alignment_of_comparison(comparison),
        inverse=inverse,
        inputs={left_name: left, right_name: right},
    )


def _sign_observation(key: str, value: float | None, *, value_name: str) -> Observation:
    sign = classify_sign(value)
    inverse = {
        Sign.POSITIVE: Sign.NEGATIVE.value,
        Sign.NEGATIVE: Sign.POSITIVE.value,
    }.get(sign)
    return Observation(
        key=key,
        classification=sign.value,
        alignment=alignment_of_sign(sign),
        inverse=inverse,
        inputs={value_name: value},
    )


def _rsi_observation(rsi: float | None) -> Observation:
    zone = classify_rsi_zone(rsi)
    return Observation(
        key="rsi_zone",
        classification=zone.value,
        # Deliberately never directional: a band is not a direction.
        alignment=(
            Alignment.UNAVAILABLE
            if zone is RsiZone.UNAVAILABLE
            else Alignment.NOT_DIRECTIONAL
        ),
        inverse=None,
        inputs={"rsi": rsi},
    )


# ------------------------------------------------------------------ grouping ---


def _group(observations: Sequence[Observation]) -> EvidenceGroups:
    """Split observations into supporting, conflicting, and unavailable.

    The dominant alignment is whichever of UPWARD/DOWNWARD has more observations.
    On a tie there is no dominant alignment, so every directional observation is
    reported as conflicting and none as supporting — a deadlock is a real result,
    not something to break arbitrarily.

    NEUTRAL observations (an exact equality) support nothing and conflict with
    nothing; they are counted as available but stay out of both groups.
    NOT_DIRECTIONAL observations are excluded from grouping by design.
    """
    upward = [o for o in observations if o.alignment is Alignment.UPWARD]
    downward = [o for o in observations if o.alignment is Alignment.DOWNWARD]
    unavailable = tuple(o for o in observations if not o.available)

    if len(upward) > len(downward):
        return EvidenceGroups(
            tuple(upward), tuple(downward), unavailable, Alignment.UPWARD
        )
    if len(downward) > len(upward):
        return EvidenceGroups(
            tuple(downward), tuple(upward), unavailable, Alignment.DOWNWARD
        )
    return EvidenceGroups((), tuple(upward + downward), unavailable, Alignment.NEUTRAL)


def _scenarios(groups: EvidenceGroups) -> dict[str, Scenario]:
    """Turn grouped observations into observable conditions, mechanically.

    Continuation lists what currently holds and would have to persist.
    Deterioration lists the same observations flipped — the conditions that would
    contradict the current picture. Neutral lists what is already unresolved.
    Nothing here forecasts; each line restates an observation.
    """
    continuation = tuple(
        f"{o.key} remains {o.classification}" for o in groups.supporting
    )
    deterioration = tuple(
        f"{o.key} becomes {o.inverse}"
        for o in groups.supporting
        if o.inverse is not None
    )
    neutral = tuple(
        f"{o.key} is {o.classification}" for o in groups.conflicting
    ) + tuple(f"{o.key} is unavailable" for o in groups.unavailable)

    return {
        "continuation": Scenario("continuation", continuation),
        "deterioration": Scenario("deterioration", deterioration),
        "neutral": Scenario("neutral", neutral),
    }


def _state(observations: Sequence[Observation], groups: EvidenceGroups) -> OverallState:
    """Select the overall state. Never directional.

    Fewer than `MIN_DIRECTIONAL_OBSERVATIONS` available directional observations
    means there is not enough to characterise anything: INSUFFICIENT_DATA.
    Otherwise WATCH requires both that nothing conflicts and that at least one
    observation actually leans somewhere — all-neutral evidence is coherent but
    says nothing, which is WAIT, not WATCH.
    """
    available = [o for o in observations if o.directional]
    if len(available) < MIN_DIRECTIONAL_OBSERVATIONS:
        return OverallState.INSUFFICIENT_DATA
    if groups.conflicting or not groups.supporting:
        return OverallState.WAIT
    return OverallState.WATCH


# -------------------------------------------------------------------- build ---


def _relative_value(snapshot: AnalysisSnapshot) -> RelativeValueEvidence | None:
    """Restate the snapshot's RVE results. Nothing is recomputed."""
    section = snapshot.relative_value
    if section is None:
        return None

    def value_of(key: str) -> float | None:
        result = section.metrics.get(key)
        return None if result is None else result.value

    reasons = {
        key: result.reason.value
        for key, result in section.metrics.items()
        if result.reason is not None
    }
    return RelativeValueEvidence(
        benchmark_symbol=section.benchmark_symbol,
        primary_return=value_of("period_return_primary"),
        benchmark_return=value_of("period_return_benchmark"),
        relative_return=value_of("relative_return"),
        volatility_ratio=value_of("volatility_ratio"),
        correlation=value_of("pearson_correlation"),
        undefined_reasons=reasons,
        aligned_observation_count=section.alignment.aligned_observation_count,
    )


def build_evidence_report(snapshot: AnalysisSnapshot) -> EvidenceReport:
    """Organise an `AnalysisSnapshot` into structured, deterministic evidence.

    Reads the snapshot only — no fetching, no indicator math, no metric math. A
    feature that is absent or still warming up produces an `UNAVAILABLE`
    observation rather than an omission or a guess.

    The snapshot is not mutated, and the report holds no reference into its
    mutable state.
    """
    close = snapshot.window.last_close

    ema_fast = _feature_value(snapshot, EMA_FAST_FEATURE)
    ema_slow = _feature_value(snapshot, EMA_SLOW_FEATURE)
    trend = TrendEvidence(
        price_vs_ema_fast=_comparison_observation(
            "price_vs_ema_fast", close, ema_fast,
            left_name="close", right_name=EMA_FAST_FEATURE,
        ),
        price_vs_ema_slow=_comparison_observation(
            "price_vs_ema_slow", close, ema_slow,
            left_name="close", right_name=EMA_SLOW_FEATURE,
        ),
        ema_fast_vs_ema_slow=_comparison_observation(
            "ema_fast_vs_ema_slow", ema_fast, ema_slow,
            left_name=EMA_FAST_FEATURE, right_name=EMA_SLOW_FEATURE,
        ),
    )

    rsi = _feature_value(snapshot, RSI_FEATURE)
    macd = _feature_value(snapshot, MACD_FEATURE)
    macd_line = None if macd is None else macd.get("macd_line")
    macd_signal = None if macd is None else macd.get("signal_line")
    histogram = None if macd is None else macd.get("histogram")
    momentum = MomentumEvidence(
        rsi_value=rsi,
        rsi_zone=_rsi_observation(rsi),
        macd_vs_signal=_comparison_observation(
            "macd_vs_signal", macd_line, macd_signal,
            left_name="macd_line", right_name="signal_line",
        ),
        macd_histogram=_sign_observation(
            "macd_histogram", histogram, value_name="histogram"
        ),
        macd_line=macd_line,
        macd_signal_line=macd_signal,
    )

    atr = _feature_value(snapshot, ATR_FEATURE)
    volatility = VolatilityEvidence(
        atr_value=atr,
        last_close=close,
        atr_percent_of_close=atr_percent_of_close(atr, close),
    )

    observations = trend.observations + momentum.observations
    groups = _group(observations)

    return EvidenceReport(
        context=MarketContext(
            symbol=snapshot.symbol,
            interval=snapshot.interval,
            as_of=snapshot.as_of,
            analysed_candle_count=snapshot.window.closed_count,
            benchmark_symbol=snapshot.benchmark_symbol,
        ),
        trend=trend,
        momentum=momentum,
        volatility=volatility,
        groups=groups,
        scenarios=_scenarios(groups),
        state=_state(observations, groups),
        relative_value=_relative_value(snapshot),
        metadata={
            "feature_names": (
                EMA_FAST_FEATURE, EMA_SLOW_FEATURE, RSI_FEATURE,
                ATR_FEATURE, MACD_FEATURE,
            ),
            "missing_features": tuple(
                name
                for name in (EMA_FAST_FEATURE, EMA_SLOW_FEATURE, RSI_FEATURE,
                             ATR_FEATURE, MACD_FEATURE)
                if snapshot.features.get(name) is None
            ),
            "warming_up_features": tuple(
                name
                for name in (EMA_FAST_FEATURE, EMA_SLOW_FEATURE, RSI_FEATURE,
                             ATR_FEATURE, MACD_FEATURE)
                if (r := snapshot.features.get(name)) is not None and r.value is None
            ),
            "min_directional_observations": MIN_DIRECTIONAL_OBSERVATIONS,
            "rsi_excluded_from_directional_grouping": True,
        },
    )
