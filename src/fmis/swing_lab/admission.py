"""What the swing **admission** decision is, and how a decision instant is measured.

Milestone CA's vocabulary. Four milestones have now searched what happens
*around* an admitted setup — BW the timeframe roles, BX thirteen geometries, BY
one geometry's neighbourhood, BZ five exit mechanisms — and all four rejected
everything they tested. None of them asked the question underneath:

    Does the FMITS admission rule select instants and directions whose forward
    outcomes are better than matched instants it did NOT select?

That question needs a unit BW–BZ never had. Their unit is a *trade*: an entry, a
stop, a target and an exit, so every one of their measurements is a joint
statement about admission **and** geometry. BZ established that the geometry is
the losing half, which makes "the strategy loses" and "there is no signal to
shape" indistinguishable from a trade alone.

So CA's unit is a `DecisionInstant` — a symbol, a bar, a direction and a
volatility scale — and its outcome is a **fixed-horizon, direction-normalised,
ATR-normalised forward excursion**. No stop, no target, no exit rule, no cost.
That is not a simplification for convenience; it is the only way to measure
admission separately from the management BW–BZ already refuted.

**The gate ladder is production's own precedence, read rather than restated.**
`fmis.swing_setup.policy.evaluate_setup` refuses an instant in a fixed order —
decision context, then the context-role regime gate, then the family tally, then
the execution confirmation — and `stage_of` reproduces exactly that order from
the values a `ThesisObservation` already carries. It re-derives nothing: a stage
is a *reading* of the production assessment, and a test asserts that replaying
the ladder over a captured timeline reproduces the captured admitted set
candidate for candidate.

**Nothing here plans a trade, and nothing here is random.** Matching and
randomisation live in `fmis.swing_lab.admission_matching`; the experiment lives
in `fmis.swing_lab.admission_study`. This module holds the vocabulary and the
arithmetic, so a rule can never be built from a measurement by accident.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Final

from fmis.data.models import Candle, CandleSeries
from fmis.features.indicators.atr import AverageTrueRange
from fmis.features.types import FeatureContext
from fmis.paper.models import PriceBar
from fmis.pipeline.regime import FAST_ATR_PERIOD
from fmis.snapshotting import TradeDirection
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.persistence import ThesisObservation, ThesisTimeline
from fmis.swing_setup.models import Direction, SetupState
from fmis.swing_setup.research_identity import OpportunityTracker

__all__ = [
    "FORWARD_HORIZONS",
    "EXCURSION_RACE_ATR",
    "RaceOutcome",
    "AdmissionStage",
    "DecisionInstant",
    "ForwardOutcome",
    "atr_at",
    "atr_series",
    "forward_outcome",
    "payload_of_stage_counts",
    "stage_of",
    "walk_decision_instants",
]

#: The forward horizons, in execution-timeframe bars, at which every decision is
#: observed. **A subset of Milestone BZ's `CHECKPOINT_BARS`, never a new set** —
#: so a CA horizon and a BZ checkpoint describe the same bar of the same window —
#: and bounded by BW's inherited 60-bar evaluation window, because a horizon past
#: that bound would observe bars no trade in this series was ever given.
#:
#: On a 4H execution timeframe these are 4 hours, 12 hours, 1 day, 2 days,
#: 4 days and 10 days.
FORWARD_HORIZONS: Final[tuple[int, ...]] = (1, 3, 6, 12, 24, 60)

#: The symmetric excursion whose race is timed: does the instant reach **+1 ATR
#: favourable before 1 ATR adverse**? One ATR is chosen because it is the scale
#: the outcome is already expressed in, so the race needs no second threshold
#: nobody declared, and because a symmetric race has a 50 % base rate under a
#: driftless random walk — which is exactly the null a selection claim must beat.
EXCURSION_RACE_ATR: Final[Decimal] = Decimal("1.0")


class RaceOutcome(str, Enum):
    """Which side of a symmetric ±1 ATR race arrived first, within a horizon.

    `AMBIGUOUS` is a **refusal, never a guess**. When one bar's range spans both
    thresholds, the execution-timeframe data cannot say which was touched first,
    and `fmis.swing_lab.intrabar` is the only layer in this repository entitled
    to descend to a finer rung. CA does not descend: it records the ambiguity,
    excludes it from the rate, and counts it beside the rate — the identical
    discipline `fmis.swing_lab.trades` applies to a stop and a target colliding
    inside one bar, and the reason a CA race rate is never quietly rounded up by
    the cases it could not resolve.
    """

    FAVOURABLE = "favourable"
    ADVERSE = "adverse"
    NEITHER = "neither"
    AMBIGUOUS = "ambiguous"

_DIRECTION_TO_TRADE: Final[dict[Direction, TradeDirection]] = {
    Direction.LONG: TradeDirection.LONG,
    Direction.SHORT: TradeDirection.SHORT,
}

_STATES: Final[dict[str, SetupState]] = {item.value: item for item in SetupState}
_DIRECTIONS: Final[dict[str, Direction]] = {item.value: item for item in Direction}

#: The decision-context value at which production refuses before reaching any
#: gate. Read from the production enum's own vocabulary rather than retyped.
_INSUFFICIENT: Final[str] = "insufficient"

#: The context-role regime the production gate requires. Same discipline.
_TRENDING: Final[str] = "trending"


class AdmissionStage(str, Enum):
    """How far one instant travelled through the production admission ladder.

    The order is `evaluate_setup`'s own and the partition is **total**: every
    analysable instant lands in exactly one member, and the members are read in
    the order below because production refuses in that order. Attributing an
    instant to a gate that was never reached would blame that gate for a refusal
    it had no part in — the mistake `fmis.swing_lab.replay._gate_verdict` already
    names for the context-role gate, applied here to the whole ladder.

    * `CONTEXT_INSUFFICIENT` — the decision-context engine declared the data
      inadequate. No gate below was consulted.
    * `REGIME_BLOCKED` — the context-role (1W) regime structure was not
      `TRENDING`. No direction was formed.
    * `TALLY_DISAGREED` — the gate passed and the family tally produced no
      direction: fewer than `MINIMUM_AGREEING_FAMILIES` agreed, or one opposed.
    * `UNCONFIRMED` — a directional thesis exists (`SetupState.CANDIDATE`) and
      the execution-timeframe confirmation this policy requires has not
      occurred. **This is the eligible-but-rejected population**, and it is
      production's own vocabulary rather than an "almost setup" invented for a
      control.
    * `CONFIRMED_REPEAT` — confirmed, but not the first confirmation of its
      opportunity. The setup identity already admitted this thesis; a second
      admission would measure one opportunity twice.
    * `ADMITTED` — the first confirmation of an opportunity, inside the
      measurement window. **This is what the live product would have traded.**
    """

    CONTEXT_INSUFFICIENT = "context_insufficient"
    REGIME_BLOCKED = "regime_blocked"
    TALLY_DISAGREED = "tally_disagreed"
    UNCONFIRMED = "unconfirmed"
    CONFIRMED_REPEAT = "confirmed_repeat"
    ADMITTED = "admitted"

    @property
    def has_direction(self) -> bool:
        """Whether production had formed a direction by the time it stopped here.

        The three stages below the tally carry no direction — a control drawn
        from them must therefore be given one, which is precisely what makes a
        direction-neutral null different from an eligible-but-rejected one.
        """
        return self in _DIRECTIONAL_STAGES


_DIRECTIONAL_STAGES: Final[frozenset[AdmissionStage]] = frozenset(
    {
        AdmissionStage.UNCONFIRMED,
        AdmissionStage.CONFIRMED_REPEAT,
        AdmissionStage.ADMITTED,
    }
)


def stage_of(
    observation: ThesisObservation, *, is_first_confirmation: bool
) -> AdmissionStage:
    """Which rung of the production ladder this instant reached. **A reading.**

    Every value consulted is one `fmis.swing_setup.models.SetupInputs` already
    held at that instant and `fmis.swing_lab.persistence_replay.observation_from`
    already copied. This function evaluates no policy, forms no thesis and
    derives no structure — it reports where production stopped, in production's
    own order.

    ``is_first_confirmation`` is `OpportunityTracker`'s flag, not a recomputation
    of it: the identity rule lives in `fmis.swing_setup.research_identity` and
    this module imports it rather than restating what "the same opportunity"
    means.

    Raises:
        SwingLabError: the observation carries a setup state this build does not
            know, which would silently mis-attribute every instant like it.
    """
    if not isinstance(observation, ThesisObservation):
        raise TypeError(
            f"observation must be a ThesisObservation, got {type(observation).__name__}"
        )
    state = _STATES.get(observation.setup_state)
    if state is None:
        raise SwingLabError(
            f"{observation.symbol} at {observation.as_of.isoformat()} carries "
            f"setup state {observation.setup_state!r}, which this build does not "
            "define; attributing it to a gate would be a guess"
        )
    # Production's precedence, in production's order. The first two rungs are
    # read from the inputs rather than from the state, because `WAIT` collapses
    # three distinct refusals into one value and reporting them as one would
    # lose the whole point of a gate attribution.
    if observation.decision_context_state == _INSUFFICIENT:
        return AdmissionStage.CONTEXT_INSUFFICIENT
    if observation.context_regime_structure != _TRENDING:
        return AdmissionStage.REGIME_BLOCKED
    if state is SetupState.WAIT:
        return AdmissionStage.TALLY_DISAGREED
    if state is SetupState.CANDIDATE:
        return AdmissionStage.UNCONFIRMED
    if is_first_confirmation:
        return AdmissionStage.ADMITTED
    return AdmissionStage.CONFIRMED_REPEAT


@dataclass(frozen=True, slots=True)
class DecisionInstant:
    """One symbol at one execution bar, as the admission engine saw it. **Causal.**

    Holds no bar, no future timestamp and no outcome — the same discipline
    `fmis.swing_lab.geometry.GeometryCandidate` and
    `fmis.swing_lab.persistence.ThesisObservation` keep, and for the same reason:
    a null-matching rule handed one of these *cannot* read forward, not by
    discipline but by what exists. Bars are held beside these instants and are
    handed only to `forward_outcome`, whose output can never flow back into a
    match.

    ``direction`` is production's own, and is ``None`` for every stage below the
    family tally. ``atr`` is `fmis.features.indicators.atr.AverageTrueRange` at
    this bar — the production feature, called — and is the denominator every
    forward excursion is expressed in.
    """

    symbol: str
    sample: str
    as_of: datetime
    bar_index: int
    stage: AdmissionStage
    direction: Direction | None
    close: float
    atr: float
    context_regime_structure: str
    context_regime_volatility: str
    context_structural_trend: str
    setup_structural_trend: str
    evidence_state: str | None
    segment: str | None = None

    def __post_init__(self) -> None:
        if self.atr <= 0:
            raise SwingLabError(
                f"{self.symbol} at {self.as_of.isoformat()} has ATR {self.atr}; "
                "a non-positive volatility scale is a broken measurement rather "
                "than a calm market, and there is no denominator to normalise by"
            )
        if self.stage.has_direction and self.direction is None:
            raise SwingLabError(
                f"{self.symbol} at {self.as_of.isoformat()} reached "
                f"{self.stage.value} but carries no direction; production forms a "
                "direction before that rung and an instant that lost it would "
                "silently become a direction-neutral control"
            )
        if not self.stage.has_direction and self.direction is not None:
            raise SwingLabError(
                f"{self.symbol} at {self.as_of.isoformat()} stopped at "
                f"{self.stage.value} but carries direction {self.direction}; "
                "production had formed none by that rung"
            )

    @property
    def identity(self) -> tuple[str, int]:
        """What addresses this instant inside its universe. Symbol and bar."""
        return (self.symbol, self.bar_index)


@dataclass(frozen=True, slots=True)
class ForwardOutcome:
    """One instant's forward excursions, in ATR units, direction-normalised.

    **Deliberately not a trade.** There is no stop, no target, no exit rule and
    no cost, because BW–BZ established that the geometry is the losing half of
    this strategy and a measurement that carried it could not separate a bad
    entry from a bad exit. Costs are reported once, at the study level, as the
    magnitude an effect must clear — never subtracted from an excursion that has
    not committed to an exit.

    ``forward`` is close-to-entry at each horizon; ``mfe`` is the favourable
    extreme and is never negative; ``mae`` is the adverse extreme and is never
    positive. The signs are `fmis.swing_lab.trades.simulate_trade`'s own —
    ``side.sign * (extreme - entry)`` — with the ATR standing where the risk
    denominator stands there, so a CA excursion and a BZ excursion differ only in
    what they are divided by.
    """

    entry: Decimal
    horizons: tuple[int, ...]
    forward: Mapping[int, Decimal]
    mfe: Mapping[int, Decimal]
    mae: Mapping[int, Decimal]
    race: Mapping[int, RaceOutcome]

    def at(self, horizon: int) -> Decimal:
        """The direction-normalised ATR return at ``horizon``.

        Raises:
            SwingLabError: this outcome was not measured at that horizon.
        """
        value = self.forward.get(horizon)
        if value is None:
            raise SwingLabError(
                f"this outcome holds horizons {self.horizons}, not {horizon}; a "
                "horizon that was not measured cannot be reported as one that was"
            )
        return value


def _decimal_atr(atr: float) -> Decimal:
    """The ATR as an exact decimal denominator.

    ``str`` rather than ``Decimal(atr)``: the float is the production feature's
    own output and its shortest round-tripping representation is what every other
    layer of this repository prints and persists. Constructing from the binary
    expansion instead would make the denominator depend on a representation no
    reader ever sees.
    """
    value = Decimal(str(atr))
    if value <= 0:
        raise SwingLabError(f"ATR must be positive, got {atr}")
    return value


def forward_outcome(
    bars: Sequence[PriceBar],
    *,
    signal_index: int,
    direction: Direction,
    atr: float,
    horizons: Sequence[int] = FORWARD_HORIZONS,
) -> ForwardOutcome:
    """Measure one decision's forward excursions. **Deterministic and pure.**

    ``signal_index`` is the bar whose **close** produced the decision. The entry
    is the open of ``signal_index + 1`` and a horizon ``h`` observes
    ``bars[signal_index + h]`` — `fmis.swing_lab.trades.simulate_trade`'s rule
    and `fmis.swing_lab.persistence.observe_path`'s checkpoint semantics
    respectively, reproduced rather than reinvented so a CA horizon and a BZ
    checkpoint address the same bar.

    Future bars change this outcome and may never change the decision: the
    instant is already frozen by the time it arrives here, and nothing this
    function returns is readable by `stage_of` or by any matching rule.

    Raises:
        SwingLabError: the direction is not LONG/SHORT, a horizon is not
            positive, the ATR is not positive, or the series is too short to
            reach the furthest horizon. A truncated window is refused rather
            than reported at whatever horizon happened to fit, because a
            silently shortened horizon is a different measurement wearing the
            same name.
    """
    if direction not in _DIRECTION_TO_TRADE:
        raise SwingLabError(f"direction must be LONG or SHORT, got {direction!r}")
    wanted = tuple(horizons)
    if not wanted:
        raise SwingLabError("at least one horizon is required")
    for value in wanted:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise SwingLabError(f"every horizon must be a positive int, got {value!r}")
    if isinstance(signal_index, bool) or not isinstance(signal_index, int):
        raise SwingLabError("signal_index must be an int")
    denominator = _decimal_atr(atr)
    side = _DIRECTION_TO_TRADE[direction]
    furthest = max(wanted)
    if signal_index < 0 or signal_index + furthest >= len(bars):
        raise SwingLabError(
            f"a horizon of {furthest} bars from index {signal_index} needs bar "
            f"{signal_index + furthest}, but only {len(bars)} bars exist; a "
            "truncated horizon is refused rather than silently shortened"
        )

    entry = bars[signal_index + 1].open
    favourable = adverse = entry
    forward: dict[int, Decimal] = {}
    mfe: dict[int, Decimal] = {}
    mae: dict[int, Decimal] = {}
    race: dict[int, RaceOutcome] = {}
    settled: RaceOutcome | None = None
    wanted_set = set(wanted)
    for step in range(1, furthest + 1):
        bar = bars[signal_index + step]
        if side is TradeDirection.LONG:
            bar_favourable, bar_adverse = bar.high, bar.low
        else:
            bar_favourable, bar_adverse = bar.low, bar.high
        favourable = (
            max(favourable, bar_favourable)
            if side is TradeDirection.LONG
            else min(favourable, bar_favourable)
        )
        adverse = (
            min(adverse, bar_adverse)
            if side is TradeDirection.LONG
            else max(adverse, bar_adverse)
        )
        if settled is None:
            # Read from THIS bar's own extremes rather than the running ones, so
            # the race resolves on the bar that first crossed a threshold. A bar
            # spanning both is refused, not ordered — see `RaceOutcome`.
            reached_favourable = (
                side.sign * (bar_favourable - entry) / denominator
                >= EXCURSION_RACE_ATR
            )
            reached_adverse = (
                side.sign * (bar_adverse - entry) / denominator
                <= -EXCURSION_RACE_ATR
            )
            if reached_favourable and reached_adverse:
                settled = RaceOutcome.AMBIGUOUS
            elif reached_favourable:
                settled = RaceOutcome.FAVOURABLE
            elif reached_adverse:
                settled = RaceOutcome.ADVERSE
        if step in wanted_set:
            forward[step] = side.sign * (bar.close - entry) / denominator
            mfe[step] = side.sign * (favourable - entry) / denominator
            mae[step] = side.sign * (adverse - entry) / denominator
            race[step] = RaceOutcome.NEITHER if settled is None else settled
    return ForwardOutcome(
        entry=entry,
        horizons=wanted,
        forward=forward,
        mfe=mfe,
        mae=mae,
        race=race,
    )


def atr_at(
    candles: Sequence[Candle], index: int, *, limit: int, symbol: str, interval: str
) -> float | None:
    """The production ATR at one bar, over the window the replay view held there.

    **The production feature, called.** `AverageTrueRange` is Wilder-smoothed
    from a seed taken at the start of the series it is handed, so its value at a
    bar depends on the window it is computed over. The replay view holds at most
    ``limit`` closed candles, so reproducing production's reading means handing
    the feature exactly that window and nothing longer. A regression asserts this
    reproduces every captured candidate's own `execution_atr` bit for bit.

    ``None`` while the window is too short to yield ``period`` true ranges — the
    same absence `fmis.swing_lab.geometry_replay._atr_of` reports, never a zero a
    comparison would treat as real.
    """
    if index < 0 or index >= len(candles):
        raise SwingLabError(f"bar {index} is outside a {len(candles)}-candle series")
    window = candles[max(0, index - limit + 1) : index + 1]
    series = CandleSeries(symbol=symbol, timeframe=interval, candles=tuple(window))
    result = _ATR_FEATURE.compute(FeatureContext(primary=series))
    value = result.value
    if value is None:
        return None
    return float(value) if value > 0 else None


#: One instance, because `AverageTrueRange` is stateless and constructing one per
#: bar would allocate a quarter of a million identical objects.
_ATR_FEATURE: Final[AverageTrueRange] = AverageTrueRange(FAST_ATR_PERIOD)


def _candles_of(bars: Sequence[PriceBar]) -> tuple[Candle, ...]:
    """Bars as the candles the feature engine reads. **A conversion, not a copy.**

    Volume is absent from a `PriceBar` and is passed as zero: `AverageTrueRange`
    reads high, low and close and nothing else, so a substituted volume cannot
    reach the value. Prices go through ``float`` because that is what the view
    held — the `Decimal` in a captured bar was decoded *from* that float's own
    shortest representation, so the conversion is exact rather than lossy.
    """
    return tuple(
        Candle(
            timestamp=bar.open_time,
            symbol=bar.symbol,
            timeframe=bar.interval,
            open=float(bar.open),
            high=float(bar.high),
            low=float(bar.low),
            close=float(bar.close),
            volume=0.0,
            is_closed=True,
        )
        for bar in bars
    )


def atr_series(bars: Sequence[PriceBar], *, limit: int) -> tuple[float | None, ...]:
    """The production ATR at every bar of one symbol.

    Computed once per symbol and shared by every instant of it, because a
    matching rule needs the ATR of hundreds of control bars per admission and
    recomputing one per lookup would dominate the run.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise SwingLabError("limit must be a positive int")
    if not bars:
        return ()
    candles = _candles_of(bars)
    symbol = bars[0].symbol
    interval = bars[0].interval
    return tuple(
        atr_at(candles, index, limit=limit, symbol=symbol, interval=interval)
        for index in range(len(bars))
    )


def walk_decision_instants(
    timeline: ThesisTimeline,
    *,
    symbol: str,
    bars: Sequence[PriceBar],
    atrs: Sequence[float | None],
    sample_holds,
    sample_name: str,
    furthest_horizon: int,
    segment_of=None,
    volatility_of: Mapping[int, str] | None = None,
) -> tuple[DecisionInstant, ...]:
    """Replay one symbol's captured timeline into `DecisionInstant`s.

    **The opportunity tracker is production's own, walked in bar order.** The
    admitted set this produces is asserted, by regression, to equal the capture's
    own candidate list symbol for symbol and bar for bar — which is what entitles
    CA to say that its `ADMITTED` stage is the live product's decision rather
    than a reconstruction of it.

    ``sample_holds`` is `fmis.swing_lab.preregistration.SampleSpec.holds`, passed
    rather than reimplemented, so CA's sample boundaries are BY's and BZ's by
    construction and cannot drift from them.

    Instants without a usable close, without an ATR, or without enough series
    left to reach ``furthest_horizon`` are **excluded and countable** rather than
    measured at whatever horizon fitted.
    """
    tracker = OpportunityTracker()
    found: list[DecisionInstant] = []
    for bar_index in sorted(timeline.observations):
        observation = timeline.observations[bar_index]
        direction = (
            None
            if observation.setup_direction is None
            else _DIRECTIONS[observation.setup_direction]
        )
        state = _STATES.get(observation.setup_state)
        if state is None:
            raise SwingLabError(
                f"{symbol} at {observation.as_of.isoformat()} carries unknown "
                f"setup state {observation.setup_state!r}"
            )
        # Called on EVERY observation, admitted or not, and before any filter:
        # the tracker is a running state machine and skipping an instant would
        # silently re-key every opportunity after it.
        _key, _is_new, is_first = tracker.observe(
            symbol, direction, state, observation.as_of
        )
        if not sample_holds(symbol, observation.as_of):
            continue
        atr = atrs[bar_index] if bar_index < len(atrs) else None
        if (
            observation.execution_close is None
            or atr is None
            or bar_index + furthest_horizon >= len(bars)
        ):
            continue
        stage = stage_of(observation, is_first_confirmation=is_first)
        found.append(
            DecisionInstant(
                symbol=symbol,
                sample=sample_name,
                as_of=observation.as_of,
                bar_index=bar_index,
                stage=stage,
                direction=direction if stage.has_direction else None,
                close=observation.execution_close,
                atr=atr,
                context_regime_structure=observation.context_regime_structure,
                context_regime_volatility=(
                    "" if volatility_of is None else volatility_of.get(bar_index, "")
                ),
                context_structural_trend=observation.context_structural_trend,
                setup_structural_trend=observation.setup_structural_trend,
                evidence_state=observation.evidence_state,
                segment=None if segment_of is None else segment_of(observation.as_of),
            )
        )
    return tuple(found)


def payload_of_stage_counts(instants: Sequence[DecisionInstant]) -> dict[str, Any]:
    """How many instants stopped at each rung. The gate ladder, as a census."""
    counts = {stage.value: 0 for stage in AdmissionStage}
    for instant in instants:
        counts[instant.stage.value] += 1
    return counts
