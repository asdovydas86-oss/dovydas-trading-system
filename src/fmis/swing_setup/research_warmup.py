"""Deriving the warm-up prefix, and measuring whether the provider can supply it.

    derive_warmup(timeframes, limit=..., detection=..., policy=...)  ──►  WarmupRequirement
    probe_availability(symbols, window, warmup, ...)                 ──►  AvailabilityReport

**Why this module exists.** Milestone AV picked its 400-day default by hand,
reasoning that weekly EMA(50) needs ~350 days. The reasoning was right and the
number was wrong in the way hand-derived numbers usually are: it covered the
one dependency someone thought of and none of the others, and — the part that
actually broke the research — it was spent *inside* the measurement window
rather than before it. Milestone BB then showed the consequence: a 400-day
window in which the policy could reach `CONFIRMED` on 43 of those days.

So nothing here is hand-derived. Every contributing number is read out of the
production object that owns it:

* **Feature warm-up** — each `Feature` in `fmis.pipeline.regime.regime_features`
  is *asked*, by computing it against a series too short to satisfy it and
  reading the ``warmup_bars``/``warmup_candles`` its own metadata declares. A
  feature that changes period, or a feature added to the set, changes this
  number automatically. Nothing is written down twice.
* **Structural detection** — `fmis.market_structure.required_candles`, called
  with the run's own `DetectionSettings`.
* **Regime transition lookback** — `RegimePolicy.transition_lookback_bars`.
* **Confirmation staleness** — `fmis.swing_setup.policy.CONFIRMATION_LOOKBACK_BARS`;
  a confirming break may be that many bars old, so that many bars must exist
  behind the first measured instant for the same break to be visible.
* **The requested analysis window** — the ``limit`` the harness passes to
  `multi_timeframe_facts_for_symbol`. This one is easy to miss and is usually
  the binding constraint: the composition path asks for ``limit`` candles at
  every role and reads whatever it gets, so a role holding fewer than ``limit``
  closed candles is analysed over a *shorter window than production uses*. That
  is warm-up truncation even when every indicator has a value, which is why it
  is counted as a warm-up component rather than assumed harmless.

The per-role requirement is the largest of those, and the prefix is the largest
per-role **duration** — the same bar count costs 250 days at ``1d`` and 250
weeks at ``1w``, and it is the weekly role that dominates every real crypto
window, because weekly history is the shortest history there is.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any, Final

from fmis.data import Candle, CandleSeries
from fmis.features.types import Feature, FeatureContext
from fmis.market_regime import RegimePolicy
from fmis.market_structure import required_candles
from fmis.pipeline.multi_timeframe import TimeframeRole
from fmis.pipeline.regime import regime_features
from fmis.pipeline.structural_facts import DetectionSettings
from fmis.providers.binance import Transport, build_klines_url
from fmis.swing_setup.backtest_replay import OPEN_TIME_INDEX, from_epoch_ms
from fmis.swing_setup.policy import CONFIRMATION_LOOKBACK_BARS
from fmis.swing_setup.research_models import (
    AvailabilityReport,
    ResearchError,
    ResearchWindow,
    RoleWarmup,
    SeriesAvailability,
    WarmupComponent,
    WarmupRequirement,
    interval_duration,
)

__all__ = [
    "WARMUP_METADATA_KEYS",
    "feature_warmup_bars",
    "derive_warmup",
    "probe_availability",
    "required_from_by_interval",
]

#: The two keys the shipped features use to declare their own warm-up. Both are
#: read, because the repository genuinely uses both — `ExponentialMovingAverage`
#: says ``warmup_bars`` while `AverageTrueRange`, `RelativeStrengthIndex`,
#: `MovingAverageConvergenceDivergence` and `RelativeVolume` say
#: ``warmup_candles``. Reading both is honest; picking one and silently scoring
#: the other family as zero would under-state the prefix.
WARMUP_METADATA_KEYS: Final[tuple[str, ...]] = ("warmup_bars", "warmup_candles")

#: A series short enough that no shipped feature can satisfy it, used only to
#: make each feature state its own requirement. Two candles rather than zero:
#: a true-range family needs a previous close to exist before it can report how
#: many it wants, and an empty series is a degenerate input this probe has no
#: reason to rely on.
_PROBE_CANDLES: Final[int] = 2
_PROBE_EPOCH: Final[datetime] = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _probe_series(interval: str) -> CandleSeries:
    """A minimal, fully closed series used only to ask features what they need."""
    step = interval_duration(interval)
    candles = tuple(
        Candle(
            symbol="WARMUPPROBE",
            timeframe=interval,
            timestamp=_PROBE_EPOCH + step * index,
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1.0,
            is_closed=True,
        )
        for index in range(_PROBE_CANDLES)
    )
    return CandleSeries(symbol="WARMUPPROBE", timeframe=interval, candles=candles)


def feature_warmup_bars(feature: Feature, interval: str) -> int:
    """How many closed candles ``feature`` says it needs before it yields a value.

    Read from the feature's own result metadata rather than from a table kept
    here, so a period change anywhere in `fmis.features` reaches the warm-up
    prefix without this module being edited.

    Raises:
        ResearchError: the feature declares no warm-up under any key in
            `WARMUP_METADATA_KEYS`. Silently scoring it zero would mean a
            feature could warm up *inside* the measurement window without
            anything noticing, which is the exact failure BB found.
    """
    result = feature.compute(FeatureContext(primary=_probe_series(interval)))
    for key in WARMUP_METADATA_KEYS:
        declared = result.metadata.get(key)
        if isinstance(declared, int) and not isinstance(declared, bool):
            return declared
    raise ResearchError(
        f"feature {feature.name!r} declares no warm-up under any of "
        f"{', '.join(WARMUP_METADATA_KEYS)}; the research warm-up prefix cannot "
        "be derived while a computed feature's requirement is unknown"
    )


def _role_components(
    interval: str,
    *,
    role: TimeframeRole,
    limit: int,
    detection: DetectionSettings,
    policy: RegimePolicy,
    features: Sequence[Feature],
) -> tuple[WarmupComponent, ...]:
    """Every production dependency that must be warm at ``role``, with its own number."""
    components = [
        WarmupComponent(
            name=feature.name,
            bars=feature_warmup_bars(feature, interval),
            source="fmis.features (the feature's own warm-up metadata)",
        )
        for feature in features
    ]
    components.append(
        WarmupComponent(
            name="structural_detection",
            bars=required_candles(detection.left_bars, detection.right_bars),
            source="fmis.market_structure.required_candles",
        )
    )
    components.append(
        WarmupComponent(
            name="regime_transition_lookback",
            bars=policy.transition_lookback_bars,
            source="fmis.market_regime.RegimePolicy.transition_lookback_bars",
        )
    )
    components.append(
        WarmupComponent(
            name="analysis_window",
            bars=limit,
            source=(
                "the candle limit the harness requests per role; a role holding "
                "fewer closed candles than this is analysed over a shorter "
                "window than production uses"
            ),
        )
    )
    if role is TimeframeRole.EXECUTION:
        components.append(
            WarmupComponent(
                name="confirmation_staleness_window",
                bars=CONFIRMATION_LOOKBACK_BARS,
                source="fmis.swing_setup.policy.CONFIRMATION_LOOKBACK_BARS",
            )
        )
    return tuple(components)


def derive_warmup(
    timeframes: Mapping[TimeframeRole, str],
    *,
    limit: int,
    detection: DetectionSettings | None = None,
    policy: RegimePolicy | None = None,
    features: Sequence[Feature] | None = None,
) -> WarmupRequirement:
    """Derive how much history must precede ``measurement_start``, role by role.

    Pure: no network, no clock, no randomness. Two calls with equal arguments
    return an equal `WarmupRequirement`.

    ``features`` defaults to `fmis.pipeline.regime.regime_features()` — the
    exact set the harness computes — so the derivation tracks what the run
    actually does rather than what this module assumes it does.

    Raises:
        ResearchError: a role is missing, an interval has no fixed duration, or
            a computed feature declares no warm-up.
    """
    missing = [role.value for role in TimeframeRole if role not in timeframes]
    if missing:
        raise ResearchError(f"timeframes must map every role; missing {missing}")
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an int")
    if limit <= 0:
        raise ResearchError("limit must be positive")

    settings = DetectionSettings() if detection is None else detection
    regime_policy = RegimePolicy() if policy is None else policy
    feature_set = tuple(regime_features()) if features is None else tuple(features)
    if not feature_set:
        raise ResearchError("features must be a non-empty sequence")

    by_role = []
    for role in TimeframeRole:
        interval = timeframes[role]
        components = _role_components(
            interval,
            role=role,
            limit=limit,
            detection=settings,
            policy=regime_policy,
            features=feature_set,
        )
        required = max(item.bars for item in components)
        by_role.append(
            RoleWarmup(
                role=role.value,
                interval=interval,
                required_bars=required,
                duration=required * interval_duration(interval),
                components=components,
            )
        )
    ordered = tuple(by_role)
    return WarmupRequirement(by_role=ordered, prefix=max(r.duration for r in ordered))


def _single_row(
    symbol: str,
    interval: str,
    *,
    start_time: datetime | None,
    transport: Transport,
    base_url: str,
) -> list[Any] | None:
    """One raw kline: the earliest available when ``start_time`` is the epoch, else the latest.

    Asks the provider exactly the question being measured rather than paging a
    whole series to look at its ends — `Part 3`'s requirement is "measure, do
    not assume", not "download everything twice".
    """
    import json

    url = build_klines_url(
        symbol=symbol,
        interval=interval,
        start_time=start_time,
        limit=1,
        base_url=base_url,
    )
    response = transport(url)
    payload = json.loads(response.body)
    if not (200 <= response.status < 300) or isinstance(payload, Mapping):
        raise ResearchError(
            f"{symbol} {interval}: provider error probing availability: {payload!r}"
        )
    if not isinstance(payload, list) or not payload:
        return None
    return payload[0]


def probe_availability(
    symbols: Sequence[str],
    intervals: Sequence[str],
    *,
    required_from: Mapping[str, datetime],
    probed_at: datetime,
    transport: Transport | None = None,
    base_url: str | None = None,
) -> AvailabilityReport:
    """Measure the real history each (symbol, interval) holds, and whether it suffices.

    ``required_from`` names, per interval, the instant history must reach back
    to — the interval's own warm-up start, not the global one, since each
    interval is fetched from its own requirement.

    Returns a report rather than raising: an unsatisfiable window is a
    **result** of this milestone, not an error in it, and the caller decides
    whether to shorten the request (explicitly) or stop.
    """
    from fmis.providers.binance import BINANCE_API_BASE, urlopen_transport

    if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence) or not symbols:
        raise ResearchError("symbols must be a non-empty, non-string sequence")
    if isinstance(intervals, (str, bytes)) or not isinstance(intervals, Sequence) or not intervals:
        raise ResearchError("intervals must be a non-empty, non-string sequence")
    for interval in intervals:
        if interval not in required_from:
            raise ResearchError(f"required_from has no entry for interval {interval!r}")

    send = urlopen_transport if transport is None else transport
    base = BINANCE_API_BASE if base_url is None else base_url

    series: list[SeriesAvailability] = []
    for symbol in symbols:
        for interval in intervals:
            earliest_row = _single_row(
                symbol, interval, start_time=_PROBE_EPOCH, transport=send, base_url=base
            )
            latest_row = _single_row(
                symbol, interval, start_time=None, transport=send, base_url=base
            )
            needed = required_from[interval]
            if earliest_row is None or latest_row is None:
                series.append(
                    SeriesAvailability(
                        symbol=symbol,
                        interval=interval,
                        earliest_open=None,
                        latest_open=None,
                        implied_candle_count=0,
                        required_from=needed,
                        satisfies_window=False,
                        # An empty series is short by the whole requirement; there
                        # is no first candle to measure a partial shortfall from.
                        shortfall=timedelta.max,
                    )
                )
                continue
            earliest = from_epoch_ms(earliest_row[OPEN_TIME_INDEX])
            latest = from_epoch_ms(latest_row[OPEN_TIME_INDEX])
            step = interval_duration(interval)
            count = int((latest - earliest) / step) + 1
            shortfall = max(timedelta(0), earliest - needed)
            series.append(
                SeriesAvailability(
                    symbol=symbol,
                    interval=interval,
                    earliest_open=earliest,
                    latest_open=latest,
                    implied_candle_count=count,
                    required_from=needed,
                    satisfies_window=shortfall == timedelta(0),
                    shortfall=shortfall,
                )
            )
    return AvailabilityReport(series=tuple(series), probed_at=probed_at)


def required_from_by_interval(
    window: ResearchWindow, warmup: WarmupRequirement, intervals: Sequence[str]
) -> dict[str, datetime]:
    """Per-interval instant that history must reach back to, for a fetch or a probe.

    Each interval starts from its own warm-up duration rather than the global
    prefix: a weekly role needing 250 weeks does not oblige the 4H role to
    fetch 250 weeks of 4H candles, tens of thousands of rows no execution
    decision can read.

    **Any warm-up the window carries beyond the derived prefix is added to every
    interval.** The harness replays a short identity-priming run *before*
    ``measurement_start``, and those instants must be as warm as the measured
    ones — a priming instant analysed over a slightly short window could read a
    different direction, and the tracker it primes is what decides whether an
    opportunity at the boundary counts as beginning inside the window. Priming
    on an under-warmed prefix would reintroduce, one bar outside the window,
    exactly the defect this milestone removes inside it.
    """
    beyond_prefix = max(timedelta(0), window.warmup_duration - warmup.prefix)
    return {
        interval: window.measurement_start - warmup.for_interval(interval) - beyond_prefix
        for interval in intervals
    }
