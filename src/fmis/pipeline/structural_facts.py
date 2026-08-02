"""Structural Fact Sheet — real candles to every deterministic fact, in one place.

The second composition root in the application layer, beside `market_analysis`.
Where `analyze_symbol` composes the *measurement* engines, this composes the
**structural chain** as well, so that for the first time a single call reaches
every deterministic layer the repository has built:

    fmis.providers.binance.fetch_klines        public candles -> CandleSeries
    CandleSeries.closed()                      explicit closed-candle selection
    fmis.features.FeatureEngine                EMA · RSI · MACD · ATR · volume
    fmis.market_structure.detect_swings        swing points
    ...compare_swing_sequence                  relationships
    ...label_swing_sequence                    HH / HL / LH / LL / EQUAL
    ...derive_structural_sequence_state_history  sequence state
    fmis.structural_trend.derive_structural_trend  trend
    fmis.level_crossing.structural_levels      price levels
    ...derive_level_crossings                  crossing events
    fmis.structure_break.derive_structure_breaks   break of structure
    fmis.change_of_character.derive_changes_of_character   change of character

**No calculation is defined here.** Every number in a `StructuralFactSheet` is
produced by one of the modules above. This module decides only what to call, in
what order, and how to report what happened — the discipline ADR-0007 §2 fixed
for `market_analysis`, applied unchanged. A test asserts this module contains
**no arithmetic operator at all**, which is one stricter than its sibling: the
single bookkeeping subtraction lives in `_window_of`, which is reused rather than
restated.

**The confirmation delay has exactly one source (ADR-0020 D1 containment).**
`derive_structure_breaks` requires a ``confirmation_bars`` that must equal the
``right_bars`` used for detection, and ADR-0020 records that a mismatch is
*undetectable*: it silently changes which level is the reference at every bar,
and so which breaks and which changes of character exist. Carrying the delay on
`LevelOrigin` is a separate milestone because it changes a shipped model.

Until then, this module closes the hazard **for itself, structurally**:
`DetectionSettings.right_bars` is read once and passed to both consumers, so the
two cannot be given different values through this root. A test asserts the module
contains exactly one ``right_bars`` read site feeding both calls. That is
containment, not a fix — every *other* caller of `derive_structure_breaks` remains
exposed, and this module is deliberately not that fix.

Data policy, inherited unchanged from ADR-0007:
  * **Closed candles only, always.** The forming candle is excluded before any
    calculation, unconditionally, because a sheet computed over a forming bar is
    not reproducible. `DataWindow` reports fetched / closed / excluded counts.
  * **Warm-up is a result, not a failure.** An indicator without enough history
    carries ``value=None`` plus warm-up metadata; the sheet names it in
    ``warming_up`` rather than hiding or erroring on it.
  * **No wall clock.** Nothing here reads the time. A sheet is a pure function of
    its inputs, so two runs over the same candles are byte-identical. Freshness is
    reported as the last closed timestamp; turning that into an *age* requires a
    reference instant, which only the presentation edge supplies.

**Fact-only.** A sheet restates measurements, structure and provenance. It
contains no direction, score, ranking, confidence, recommendation, or the words
support / resistance — naming a `PriceLevel` "support" is an interpretation
ADR-0019 §I explicitly reserves for a later layer. What this module reports is the
**nearest level above and below the last close**, which is the underlying fact
that such an interpretation would rest on.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Callable

from fmis.change_of_character import ChangeOfCharacter, derive_changes_of_character
from fmis.data import CandleSeries
from fmis.features import FeatureRegistry, FeatureSet
from fmis.features.feature_engine import FeatureEngine
from fmis.features.types import Feature
from fmis.level_crossing import (
    LevelCrossingEvent,
    LevelSide,
    PriceLevel,
    derive_level_crossings,
    structural_levels,
)
from fmis.market_structure import (
    DEFAULT_LEFT_BARS,
    DEFAULT_RIGHT_BARS,
    StructuralSequenceStateSnapshot,
    StructuralSwing,
    SwingPoint,
    compare_swing_sequence,
    derive_structural_sequence_state_history,
    detect_swings,
    label_swing_sequence,
    required_candles,
)
from fmis.pipeline.market_analysis import (
    DataWindow,
    InsufficientDataError,
    _fetch_closed,
    _window_of,
    default_features,
)
from fmis.providers.binance import Transport
from fmis.structural_trend import StructuralTrendType, derive_structural_trend
from fmis.structure_break import StructureBreak, derive_structure_breaks

__all__ = [
    "build_structural_facts",
    "structural_facts_for_symbol",
    "StructuralFactSheet",
    "StructureFacts",
    "NearestLevels",
    "DetectionSettings",
    "Limitation",
    "LIMITATIONS",
]

#: Provenance string for the one provider this root can fetch from. Recorded on
#: the sheet so a stored fact sheet names its source rather than implying one.
BINANCE_SPOT = "binance-spot"


@dataclass(frozen=True, slots=True)
class DetectionSettings:
    """The swing-detection window, and **the one source of the confirmation delay**.

    ``left_bars`` and ``right_bars`` are the neighbours `detect_swings` requires on
    each side of a pivot. ``right_bars`` additionally *is* the confirmation delay:
    a pivot at bar ``o`` is knowable only once ``right_bars`` further candles have
    closed, which is exactly what `derive_structure_breaks` needs as
    ``confirmation_bars``.

    Holding both in one frozen object is the ADR-0020 D1 containment described in
    the module docstring: `build_structural_facts` reads ``right_bars`` from here
    and hands the *same* value to both consumers, so they cannot disagree.
    Passing two separate integers would have reproduced the exact hazard this
    exists to close.

    Validation is delegated, not restated: `required_candles` already rejects a
    non-int or negative bar count, and calling it in `__post_init__` means this
    type cannot accept a pair `detect_swings` would reject.
    """

    left_bars: int = DEFAULT_LEFT_BARS
    right_bars: int = DEFAULT_RIGHT_BARS

    def __post_init__(self) -> None:
        # Delegated validation: raises TypeError/ValueError for bad bar counts,
        # with fmis.market_structure's wording rather than a second vocabulary.
        required_candles(self.left_bars, self.right_bars)

    @property
    def required_candles(self) -> int:
        """Closed candles needed before any swing can be detected."""
        return required_candles(self.left_bars, self.right_bars)


@dataclass(frozen=True, slots=True)
class Limitation:
    """One named, sourced limitation of the facts on this sheet.

    ``code`` is the identifier the owning ADR uses (e.g. ``"ADR-0020 D1"``), so a
    reader can go to the decision record rather than trust this restatement.
    """

    code: str
    text: str


#: Limitations every sheet inherits from the layers it composes. Stated on the
#: sheet rather than left in the ADRs, because a fact sheet that omits what it
#: cannot see reads as more complete than it is.
LIMITATIONS: tuple[Limitation, ...] = (
    Limitation(
        "ADR-0019 D2",
        "The first swing high and first swing low have no label and therefore no "
        "price level; the earliest reference on each side is missing.",
    ),
    Limitation(
        "ADR-0020 D1",
        "The confirmation delay is carried on no derived fact. This sheet passes "
        "one value to both detection and break derivation, so they cannot "
        "disagree here, but a level object read outside this sheet does not know "
        "the delay it was confirmed under.",
    ),
    Limitation(
        "ADR-0020 D3",
        "A break is never invalidated; 'failed break' is a later reading over the "
        "break sequence.",
    ),
    Limitation(
        "ADR-0020 D5",
        "The reference level is the most recent, not the most extreme: a run of "
        "lower highs makes each successive lower high the reference.",
    ),
    Limitation(
        "ADR-0021 E1",
        "A two-sided break bar leaves character indeterminate, so no change is "
        "claimed at the next break bar.",
    ),
    Limitation(
        "ADR-0019 D1",
        "Level crossings have no activation policy: a crossing of a level whose "
        "origin is later is reported, and filtering is the break layer's decision.",
    ),
)


@dataclass(frozen=True, slots=True)
class StructureFacts:
    """Every derived structural fact, in the order the chain produced it.

    Full runs are carried rather than only their latest elements, because the
    chain's own guarantee is *prefix stability*: a consumer that keeps the run can
    verify that guarantee, and one that keeps only the tail cannot. The ``latest_``
    projections exist so a reader does not index a tuple by hand.
    """

    swings: tuple[SwingPoint, ...]
    labelled: tuple[StructuralSwing, ...]
    state_history: tuple[StructuralSequenceStateSnapshot, ...]
    trend: StructuralTrendType
    levels: tuple[PriceLevel, ...]
    crossings: tuple[LevelCrossingEvent, ...]
    breaks: tuple[StructureBreak, ...]
    changes: tuple[ChangeOfCharacter, ...]

    @property
    def latest_break(self) -> StructureBreak | None:
        """The most recent break of structure, or ``None`` if none occurred."""
        return self.breaks[-1] if self.breaks else None

    @property
    def latest_change(self) -> ChangeOfCharacter | None:
        """The most recent change of character, or ``None`` if none occurred."""
        return self.changes[-1] if self.changes else None


@dataclass(frozen=True, slots=True)
class NearestLevels:
    """The structural levels immediately above and below the last close.

    **Deliberately not named support and resistance.** A `PriceLevel` records
    where a confirmed swing sat; calling the one below "support" asserts that
    price is expected to hold there, which is an interpretation ADR-0019 §I
    reserves for a later layer. What is reported is the fact such an
    interpretation would rest on, with the level's own side and origin label
    intact so the reader can weigh it.

    ``None`` on either side means no level lies that way — usually because the run
    is short, or because price is beyond every level detected so far.
    """

    above: PriceLevel | None
    below: PriceLevel | None
    upper_count: int
    lower_count: int


@dataclass(frozen=True, slots=True)
class StructuralFactSheet:
    """One deterministic, fact-only sheet for one symbol at one point in time.

    ``as_of`` is the timestamp of the last closed candle — never the wall clock.
    Two sheets built from the same candles are equal, which is what makes a stored
    sheet re-derivable.

    ``warming_up`` names the features that returned ``value=None`` because they
    lack history. It is a first-class field rather than something a reader infers
    from a null, because "not enough data yet" and "computed to be nothing" must
    never look alike.
    """

    symbol: str
    interval: str
    source: str
    as_of: datetime
    window: DataWindow
    detection: DetectionSettings
    features: FeatureSet
    warming_up: tuple[str, ...]
    structure: StructureFacts
    nearest_levels: NearestLevels
    limitations: tuple[Limitation, ...] = LIMITATIONS
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


def _level_sort_key(level: PriceLevel) -> tuple[float, int, int, str, str]:
    """A total order over levels by price, for choosing the nearest one.

    Total rather than merely by price, so two levels at exactly the same price
    resolve identically on every run and in every input order. Ties break on
    has-origin, then origin index, then side, then label — the same shape as
    `fmis.level_crossing.models._level_key`, which cannot be imported because it
    is private to the package that owns level ordering.

    Deliberately **not** distance-based: a distance would require subtracting the
    close from the price, and this module performs no arithmetic. Choosing the
    smallest price above the close, and the largest below it, gives the same
    answer using comparison alone.
    """
    origin = level.origin
    if origin is None:
        return (level.price, 0, 0, level.side.value, "")
    return (level.price, 1, origin.index, level.side.value, origin.label.value)


def _nearest_levels(levels: Sequence[PriceLevel], close: float | None) -> NearestLevels:
    """The closest level each side of ``close``, chosen by comparison only."""
    uppers = tuple(lv for lv in levels if lv.side is LevelSide.UPPER)
    lowers = tuple(lv for lv in levels if lv.side is LevelSide.LOWER)
    if close is None:
        return NearestLevels(
            above=None, below=None, upper_count=len(uppers), lower_count=len(lowers)
        )
    above_candidates = tuple(lv for lv in levels if lv.price > close)
    below_candidates = tuple(lv for lv in levels if lv.price < close)
    return NearestLevels(
        above=min(above_candidates, key=_level_sort_key, default=None),
        below=max(below_candidates, key=_level_sort_key, default=None),
        upper_count=len(uppers),
        lower_count=len(lowers),
    )


def _structure_of(
    series: CandleSeries, detection: DetectionSettings
) -> StructureFacts:
    """Run the complete structural chain over one closed series.

    Every stage delegates in full. The only decision made here is that
    ``detection.right_bars`` is read **once** and reaches both `detect_swings` and
    `derive_structure_breaks`, so the ADR-0020 D1 mismatch is unrepresentable
    through this root.
    """
    confirmation_bars = detection.right_bars

    swings = detect_swings(
        series, left_bars=detection.left_bars, right_bars=confirmation_bars
    )
    labelled = label_swing_sequence(compare_swing_sequence(swings))
    state_history = derive_structural_sequence_state_history(labelled)
    trend = derive_structural_trend(state_history)

    levels = structural_levels(labelled)
    crossings = derive_level_crossings(series, levels)
    breaks = derive_structure_breaks(
        levels, crossings, confirmation_bars=confirmation_bars
    )
    changes = derive_changes_of_character(breaks)

    return StructureFacts(
        swings=swings,
        labelled=labelled,
        state_history=state_history,
        trend=trend,
        levels=levels,
        crossings=crossings,
        breaks=breaks,
        changes=changes,
    )


def build_structural_facts(
    series: CandleSeries,
    *,
    features: Sequence[Feature] | None = None,
    detection: DetectionSettings | None = None,
    source: str = "unknown",
    window: DataWindow | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> StructuralFactSheet:
    """Compose every deterministic engine over one candle series.

    Args:
        series: candles to analyse. The forming candle is dropped unconditionally
            before anything is computed.
        features: features to run; `default_features()` when omitted.
        detection: swing-detection window and confirmation delay;
            `DetectionSettings()` when omitted.
        source: provenance for where the candles came from, recorded on the sheet.
        window: the window to *report*, when the caller already dropped the
            forming candle. `structural_facts_for_symbol` supplies it because
            `_fetch_closed` returns an already-closed series: without it the sheet
            would report ``excluded_forming_count=0`` and silently lose the fact
            that the provider returned a forming bar. Computed from ``series``
            when omitted. It changes **what is reported, never what is computed** —
            the candles analysed are always ``series.closed()``.
        metadata: extra request provenance, defensively copied.

    Returns:
        A `StructuralFactSheet` carrying the feature set, the full structural
        chain, the nearest level each side of the last close, and the inherited
        limitations.

    Raises:
        InsufficientDataError: fewer closed candles than swing detection needs.
            Warm-up of an *indicator* is not an error — it is reported in
            ``warming_up`` — but a series too short to detect any swing at all
            cannot answer the question that was asked.
        TypeError, ValueError: from the delegate that rejected its input. Not
            wrapped: the delegates' messages already name the stage that failed.

    Pure: no clock, no network, no randomness, no state. Two calls with equal
    inputs return equal sheets.
    """
    settings = DetectionSettings() if detection is None else detection
    if not isinstance(settings, DetectionSettings):
        raise TypeError(
            "detection must be a DetectionSettings, got "
            f"{type(settings).__name__}"
        )

    closed = series.closed()
    reported_window = _window_of(series, closed) if window is None else window
    needed = settings.required_candles
    if reported_window.closed_count < needed:
        raise InsufficientDataError(
            subject=f"{series.symbol} {series.timeframe}",
            required=needed,
            fetched=reported_window.fetched_count,
            closed=reported_window.closed_count,
        )

    chosen = tuple(default_features() if features is None else features)
    registry = FeatureRegistry()
    for feature in chosen:
        registry.register(feature)
    feature_set = FeatureEngine(registry).compute(
        closed, [feature.name for feature in chosen]
    )
    warming_up = tuple(
        name
        for name, result in feature_set.features.items()
        if result.value is None
    )

    structure = _structure_of(closed, settings)

    return StructuralFactSheet(
        symbol=series.symbol,
        interval=series.timeframe,
        source=source,
        as_of=feature_set.as_of,
        window=reported_window,
        detection=settings,
        features=feature_set,
        warming_up=warming_up,
        structure=structure,
        nearest_levels=_nearest_levels(
            structure.levels, reported_window.last_close
        ),
        metadata=dict(metadata or {}),
    )


def structural_facts_for_symbol(
    symbol: str,
    interval: str,
    *,
    limit: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    features: Sequence[Feature] | None = None,
    detection: DetectionSettings | None = None,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
    base_url: str | None = None,
) -> StructuralFactSheet:
    """Fetch public candles for one symbol and build its fact sheet.

    The network edge. Fetching is delegated to `fmis.providers.binance` through
    the same private helper `analyze_symbol` uses, so the closed-candle policy and
    the insufficient-data message have one implementation rather than two.

    Args:
        symbol: exact provider symbol, e.g. ``"BTCUSDT"``.
        interval: provider interval, e.g. ``"4h"``.
        limit: candles to request; the provider default when omitted.
        start_time, end_time: optional explicit window.
        features: features to run; `default_features()` when omitted.
        detection: swing-detection window and confirmation delay.
        transport: injected HTTP transport, for tests.
        clock: injected clock, forwarded to the provider for closed-candle
            determination. **Not** used to stamp the sheet.
        base_url: override the provider base URL.

    Returns:
        A `StructuralFactSheet` with ``source`` recorded as the provider.

    Raises:
        InsufficientDataError: too few closed candles for swing detection.
        BinanceError and subclasses: transport or request failures, unwrapped.
    """
    settings = DetectionSettings() if detection is None else detection
    closed, window = _fetch_closed(
        symbol,
        interval,
        limit=limit,
        start_time=start_time,
        end_time=end_time,
        transport=transport,
        clock=clock,
        base_url=base_url,
        required=settings.required_candles,
    )
    return build_structural_facts(
        closed,
        features=features,
        detection=settings,
        source=BINANCE_SPOT,
        window=window,
        metadata={
            "requested_limit": limit,
            "requested_start_time": start_time,
            "requested_end_time": end_time,
            "fetched_count": window.fetched_count,
        },
    )
