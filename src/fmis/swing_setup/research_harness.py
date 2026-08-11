"""The corrected research harness (Milestone BC) — warm-up, windows, and true replay.

    fetch_research_dataset(...)   ──►  ResearchDataset      (one fetch, reused by every variant)
    run_research_variant(...)     ──►  ResearchBacktestRun  (one policy variant, replayed in full)
    run_research_study(...)       ──►  ResearchStudy        (a baseline plus its counterfactuals)

**What is corrected, precisely.** Milestone AV's harness is not wrong about what
it computes; it is wrong about what it *claims*. It fetched ``[start, end]``,
called all of it the research window, and reported statistics over observations
whose first ~350 days could not reach `CONFIRMED` because the context-role
weekly EMA(50) had no value yet. This module keeps AV's replay mechanism
unchanged — the same production composition path, the same closed-candle replay
transport, the same two independent no-lookahead checks — and changes only the
bookkeeping around it:

* history is fetched from a **derived** warm-up start, per interval
  (`fmis.swing_setup.research_warmup`);
* observations before ``measurement_start`` may prime state and are excluded
  from every reported count;
* observations at or after ``measurement_end`` are never produced at all, while
  candles after it remain readable so an outcome can resolve;
* the confirmation-staleness bound is **replayed**, not post-filtered.

**Why a replay and not a filter.** Under a stricter staleness bound a stale
break does not delete a setup: `evaluate_setup` returns `CANDIDATE` instead of
`CONFIRMED`, the candidate keeps watching, and a later break on the confirming
side can confirm it at a different bar, price, stop and target. Deleting
already-observed confirmations (Milestone BA's method) cannot produce that
lifecycle, and BB named it as the second thing this milestone must fix.
`fmis.swing_setup.research_compare.post_filter_comparison` quantifies the gap
rather than asserting it.

**Production behaviour is untouched.** The one production seam used here is
`setup_inputs_and_assessment_for_sheet`'s ``research_confirmation_max_age``
keyword, which the baseline variant does not supply at all — so the baseline is
the production policy running production code with no override in the call.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Final

from fmis.data import CandleSeries
from fmis.decision_context import ContextPolicy
from fmis.ingest import decode_candle_series
from fmis.market_regime import RegimePolicy
from fmis.pipeline.market_analysis import InsufficientDataError
from fmis.pipeline.multi_timeframe import (
    DEFAULT_TIMEFRAMES,
    TimeframeRole,
    multi_timeframe_facts_for_symbol,
)
from fmis.pipeline.regime import regime_features
from fmis.pipeline.structural_facts import DetectionSettings
from fmis.providers.binance import Transport, map_kline
from fmis.swing_setup.backtest_harness import (
    DEFAULT_BACKTEST_LIMIT,
    DEFAULT_BACKTEST_SYMBOLS,
    DEFAULT_EVALUATION_WINDOW_BARS,
)
from fmis.swing_setup.backtest_models import (
    DataBoundary,
    FamilyLean,
    HistoricalObservation,
    SetupOutcome,
)
from fmis.swing_setup.backtest_outcomes import evaluate_outcome
from fmis.swing_setup.backtest_replay import (
    CLOSE_TIME_INDEX,
    OPEN_TIME_INDEX,
    RawKlineCache,
    ReplayIndex,
    build_replay_transport,
    fetch_raw_klines,
    from_epoch_ms,
    prepare_replay_index,
)
from fmis.swing_setup.compose import setup_inputs_and_assessment_for_sheet
from fmis.swing_setup.models import SetupState, TriggerKind
from fmis.swing_setup.research_identity import OpportunityTracker
from fmis.swing_setup.research_models import (
    RESEARCH_SCHEMA_VERSION,
    AvailabilityReport,
    ResearchBacktestRun,
    ResearchError,
    ResearchObservation,
    ResearchPolicyVariant,
    ResearchWindow,
    TemporalSegment,
    WarmupRequirement,
    interval_duration,
    PRODUCTION_BASELINE_VARIANT,
)
from fmis.swing_setup.research_warmup import (
    derive_warmup,
    probe_availability,
    required_from_by_interval,
)

__all__ = [
    "DEFAULT_RESEARCH_SYMBOLS",
    "DEFAULT_IDENTITY_PRIMING_BARS",
    "DEFAULT_VARIANT_MAX_AGES",
    "SEGMENT_LADDER",
    "RESEARCH_LIMITATIONS",
    "build_segments",
    "ResearchDataset",
    "ResearchStudy",
    "fetch_research_dataset",
    "run_research_variant",
    "run_research_study",
]

#: The same ten liquid pairs Milestone AV measured. Deliberately unchanged: this
#: milestone corrects how a window is measured, and swapping the universe at the
#: same time would make the corrected baseline incomparable to the one it is
#: supposed to correct.
DEFAULT_RESEARCH_SYMBOLS: Final[tuple[str, ...]] = DEFAULT_BACKTEST_SYMBOLS

#: Execution-role bars replayed immediately before ``measurement_start`` purely
#: to prime `OpportunityTracker`. Without them an opportunity already running
#: when the window opens would be counted as beginning there, inflating "new
#: opportunities" at exactly one boundary. 60 bars — ten days on the 4H
#: execution role, the same span as the outcome window — is a stated
#: measurement policy fixed before any result was seen, not a tuned value.
#: These observations carry ``in_measurement=False`` and enter no denominator.
DEFAULT_IDENTITY_PRIMING_BARS: Final[int] = 60

#: The staleness bounds the milestone brief names, in the order it names them.
#: ``10`` is included even though it equals `CONFIRMATION_LOOKBACK_BARS`, and
#: that is the point: replaying it through the *override* must reproduce the
#: production baseline exactly, so its presence turns "the override mechanism is
#: faithful" from a claim into a measurement. The production baseline itself is
#: still run separately, with no override supplied at all.
DEFAULT_VARIANT_MAX_AGES: Final[tuple[int, ...]] = (10, 5, 3, 2, 1, 0)

#: How a measurement window is cut into chronological segments, longest unit
#: first, exactly as the brief prefers: yearly when two or more years exist,
#: half-yearly when at least two halves do, quarterly otherwise. Segments are
#: equal-length slices of the measurement window; boundaries come from this
#: ladder and the window's own length, never from where outcomes happened to
#: fall.
SEGMENT_LADDER: Final[tuple[tuple[str, int], ...]] = (
    ("year", 365),
    ("half_year", 182),
    ("quarter", 91),
)

_MINIMUM_SEGMENTS: Final[int] = 2

#: A UTC instant after any real historical candle this harness will replay,
#: used only to decode the full execution series for outcome evaluation. Copied
#: in spirit from `fmis.swing_setup.backtest_harness`, whose reasoning applies
#: unchanged: a series already entirely in the past is unconditionally closed.
_FAR_FUTURE: Final[datetime] = datetime(2100, 1, 1, tzinfo=timezone.utc)

RESEARCH_LIMITATIONS: tuple[str, ...] = (
    "BC-1: Every limitation Milestone AV's harness carries (AV-1 to AV-9) "
    "applies unchanged. This milestone corrects window semantics and adds a "
    "replayable policy override; it does not model fees, slippage, spread, "
    "execution delay or position sizing, and reports no realized PnL.",
    "BC-2: The warm-up prefix is derived from the production dependencies this "
    "repository declares today. A future feature with a longer warm-up changes "
    "the requirement automatically, but a dependency that declares no warm-up "
    "at all would still be missed — the derivation raises rather than assuming "
    "zero, which converts that risk into a failure rather than a silent one.",
    "BC-3: The measurement window is the longest one every requested symbol can "
    "satisfy. It is therefore bounded by the youngest symbol's weekly history, "
    "and is much shorter than the oldest symbol's. A per-symbol window would be "
    "longer and would make symbols incomparable; that trade was made "
    "deliberately in favour of comparability.",
    "BC-4: An opportunity is a maximal run of same-direction observations "
    "(`fmis.swing_setup.research_identity`). It is stable across policy "
    "variants by construction, but it is a research lineage device and not a "
    "claim that one run of directional bars is one trade.",
    "BC-5: Counterfactual variants replay the confirmation-staleness bound and "
    "nothing else. No other constant, threshold, timeframe or universe was "
    "varied, so nothing here measures the policy's sensitivity to anything but "
    "that one number.",
    "BC-6: NEITHER_WITHIN_WINDOW still does not distinguish 'price never "
    "reached either level' from 'the outcome tail ended first'. The tail is "
    "sized to the evaluation window so the second case is rare rather than "
    "impossible, and the count of outcomes resolved against a truncated tail is "
    "reported in run metadata.",
    "BC-7: Statistics are reported over measured observations only. Warm-up and "
    "identity-priming observations are recorded so a reader can see them, and "
    "are excluded from every denominator.",
    "BC-8: Symbols in one asset class over one common window remain highly "
    "co-moving, and outcome evaluation windows overlap. A larger, better-warmed "
    "sample reduces concentration; it does not make the observations "
    "independent.",
)


def build_segments(
    window: ResearchWindow, *, ladder: Sequence[tuple[str, int]] = SEGMENT_LADDER
) -> tuple[TemporalSegment, ...]:
    """Cut a measurement window into equal-length chronological segments.

    The unit is the first entry in ``ladder`` the window can fit at least
    `_MINIMUM_SEGMENTS` of; the count is how many whole units fit. Segments are
    then equal slices of the *whole* window, so they tile it exactly with no
    remainder left unattributed — a trailing stub segment shorter than the rest
    would silently host fewer observations and read as a weak period.

    Pure and independent of any result: the only inputs are two dates.
    """
    if not isinstance(window, ResearchWindow):
        raise TypeError("window must be a ResearchWindow")
    span = window.measurement_duration
    unit, count = "segment", _MINIMUM_SEGMENTS
    for name, days in ladder:
        fits = span // timedelta(days=days)
        if fits >= _MINIMUM_SEGMENTS:
            unit, count = name, int(fits)
            break

    step = span / count
    segments = []
    for position in range(count):
        start = window.measurement_start + step * position
        end = (
            window.measurement_end
            if position == count - 1
            else window.measurement_start + step * (position + 1)
        )
        segments.append(
            TemporalSegment(
                label=f"{unit}_{position + 1}_of_{count}", start=start, end=end
            )
        )
    return tuple(segments)


def _segment_of(segments: Sequence[TemporalSegment], instant: datetime) -> str | None:
    for segment in segments:
        if segment.contains(instant):
            return segment.label
    return None


@dataclass(frozen=True, slots=True)
class ResearchDataset:
    """One fetch of real history, reusable by every policy variant in a study.

    Fetching once and replaying many times is not only cheaper — it is what
    makes a variant comparison honest. Two variants fetched separately could
    differ because the provider's answer changed between calls, and every
    difference would then be ambiguous between "the policy did that" and "the
    data did".
    """

    cache: RawKlineCache
    index: ReplayIndex
    boundaries: tuple[DataBoundary, ...]
    fetch_starts: Mapping[str, datetime]
    fetched_at: datetime


@dataclass(frozen=True, slots=True)
class ResearchStudy:
    """A production baseline and its counterfactual replays over one dataset."""

    window: ResearchWindow
    warmup: WarmupRequirement
    segments: tuple[TemporalSegment, ...]
    availability: AvailabilityReport
    baseline: ResearchBacktestRun
    variants: tuple[ResearchBacktestRun, ...]

    @property
    def runs(self) -> tuple[ResearchBacktestRun, ...]:
        return (self.baseline, *self.variants)


def _decode_full_series(
    symbol: str, interval: str, rows: Sequence[Sequence[Any]]
) -> CandleSeries:
    """Decode a raw historical kline cache into its full closed `CandleSeries`."""
    now_ms = round(_FAR_FUTURE.timestamp() * 1000)
    records = [
        map_kline(raw, symbol=symbol, interval=interval, now_ms=now_ms, index=index)
        for index, raw in enumerate(rows)
    ]
    return decode_candle_series(records, symbol=symbol, timeframe=interval).closed()


def fetch_research_dataset(
    symbols: Sequence[str],
    intervals: Sequence[str],
    *,
    window: ResearchWindow,
    warmup: WarmupRequirement,
    fetched_at: datetime,
    transport: Transport | None = None,
    base_url: str | None = None,
) -> ResearchDataset:
    """Fetch every (symbol, interval) from its **own** warm-up start through the tail.

    Each interval starts at ``measurement_start - warmup.for_interval(interval)``
    and ends at ``outcome_tail_end``. Per-interval rather than global, because
    the weekly role's 250-week requirement would otherwise drag tens of
    thousands of unusable 4H rows along with it.

    Raises:
        ResearchError: a fetch failed, or an interval has no fixed duration.
    """
    if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence) or not symbols:
        raise ResearchError("symbols must be a non-empty, non-string sequence")
    if isinstance(intervals, (str, bytes)) or not isinstance(intervals, Sequence) or not intervals:
        raise ResearchError("intervals must be a non-empty, non-string sequence")

    starts = required_from_by_interval(window, warmup, intervals)
    cache = RawKlineCache()
    boundaries: list[DataBoundary] = []
    for symbol in symbols:
        for interval in intervals:
            rows = fetch_raw_klines(
                symbol,
                interval,
                start_time=starts[interval],
                end_time=window.outcome_tail_end,
                transport=transport,
                base_url=base_url,
            )
            cache[(symbol, interval)] = rows
            boundaries.append(
                DataBoundary(
                    symbol=symbol,
                    interval=interval,
                    source="binance-spot",
                    first_candle=from_epoch_ms(rows[0][OPEN_TIME_INDEX]) if rows else None,
                    last_candle=from_epoch_ms(rows[-1][OPEN_TIME_INDEX]) if rows else None,
                    candle_count=len(rows),
                    fetched_at=fetched_at,
                )
            )
    return ResearchDataset(
        cache=cache,
        index=prepare_replay_index(cache),
        boundaries=tuple(boundaries),
        fetch_starts=dict(starts),
        fetched_at=fetched_at,
    )


def _break_age(inputs: Any, assessment: Any) -> int | None:
    """How many bars old the confirming break was, from two already-recorded facts.

    ``execution_closed_count`` and the trigger's own ``bar_index`` are both on
    the objects the production path returned; subtracting them restates a number
    `evaluate_setup` already reasoned with rather than re-deriving which break
    confirmed. Milestone BB noted this value was never persisted, which is why
    the post-filter it criticised could not be checked against a real replay.
    """
    trigger = assessment.trigger
    if trigger is None or trigger.kind is not TriggerKind.CONFIRMED_STRUCTURE_BREAK:
        return None
    if trigger.bar_index is None:
        return None
    return inputs.execution_closed_count - 1 - trigger.bar_index


def run_research_variant(
    symbols: Sequence[str],
    *,
    window: ResearchWindow,
    warmup: WarmupRequirement,
    segments: Sequence[TemporalSegment],
    availability: AvailabilityReport,
    variant: ResearchPolicyVariant,
    dataset: ResearchDataset,
    run_at: datetime,
    timeframes: Mapping[TimeframeRole, str] | None = None,
    limit: int | None = None,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
    detection: DetectionSettings | None = None,
    evaluation_window_bars: int = DEFAULT_EVALUATION_WINDOW_BARS,
    identity_priming_bars: int = DEFAULT_IDENTITY_PRIMING_BARS,
) -> ResearchBacktestRun:
    """Replay every measured execution-role close under exactly one policy variant.

    Deterministic: two calls with equal arguments over an equal dataset return
    an equal `ResearchBacktestRun`, ``run_at`` aside.

    The three boundaries are enforced here and nowhere else:

    * instants earlier than ``measurement_start`` are replayed only within
      ``identity_priming_bars`` and recorded with ``in_measurement=False``;
    * instants at or after ``measurement_end`` are **never replayed**, so no
      setup can be created from tail data;
    * the outcome series is the full decoded execution series, tail included,
      because resolving what happened after a frozen decision is the one place
      looking forward is correct.

    Raises:
        ResearchError: bad arguments, or a role is missing from ``timeframes``.
    """
    if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence) or not symbols:
        raise ResearchError("symbols must be a non-empty, non-string sequence")
    for symbol in symbols:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ResearchError("every symbol must be a non-empty str")
    if not isinstance(window, ResearchWindow):
        raise TypeError("window must be a ResearchWindow")
    if not isinstance(variant, ResearchPolicyVariant):
        raise TypeError("variant must be a ResearchPolicyVariant")
    if not isinstance(dataset, ResearchDataset):
        raise TypeError("dataset must be a ResearchDataset")
    if not isinstance(run_at, datetime) or run_at.utcoffset() is None:
        raise ResearchError("run_at must be a timezone-aware datetime")
    if isinstance(evaluation_window_bars, bool) or not isinstance(evaluation_window_bars, int):
        raise TypeError("evaluation_window_bars must be an int")
    if evaluation_window_bars <= 0:
        raise ResearchError("evaluation_window_bars must be positive")
    if isinstance(identity_priming_bars, bool) or not isinstance(identity_priming_bars, int):
        raise TypeError("identity_priming_bars must be an int")
    if identity_priming_bars < 0:
        raise ResearchError("identity_priming_bars cannot be negative")

    requested = dict(DEFAULT_TIMEFRAMES if timeframes is None else timeframes)
    missing = [role.value for role in TimeframeRole if role not in requested]
    if missing:
        raise ResearchError(f"timeframes must map every role; missing {missing}")
    execution_interval = requested[TimeframeRole.EXECUTION]
    chosen_limit = DEFAULT_BACKTEST_LIMIT if limit is None else limit
    settings = DetectionSettings() if detection is None else detection
    ordered_segments = tuple(segments)
    if not ordered_segments:
        raise ResearchError("segments must be a non-empty sequence")

    priming_start = window.measurement_start - identity_priming_bars * interval_duration(
        execution_interval
    )
    override = variant.max_confirmation_age

    observations: list[ResearchObservation] = []
    outcomes: list[SetupOutcome] = []
    insufficient_measured = 0
    insufficient_priming = 0
    truncated_tail_outcomes = 0
    confirmations_first_seen_while_priming = 0
    # The warm-up claim, checked rather than asserted. A derived prefix that is
    # right in theory and wrong in practice looks exactly like AV's: every
    # number reconciles and the window is silently unusable. These three
    # counters make the claim falsifiable at every single measured instant.
    warming_feature_instants = 0
    short_window_instants = 0
    minimum_closed: dict[str, int] = {}

    for symbol in symbols:
        rows = dataset.cache.get((symbol, execution_interval))
        if rows is None:
            raise ResearchError(
                f"the dataset holds no {execution_interval} series for {symbol}"
            )
        full_execution_series = _decode_full_series(symbol, execution_interval, rows)
        instants = sorted(
            instant
            for instant in {from_epoch_ms(row[CLOSE_TIME_INDEX] + 1) for row in rows}
            if priming_start <= instant < window.measurement_end
        )
        tracker = OpportunityTracker()

        for instant in instants:
            measured = window.is_measured(instant)
            replay_transport = build_replay_transport(
                dataset.cache, now=instant, index=dataset.index
            )
            try:
                sheet = multi_timeframe_facts_for_symbol(
                    symbol,
                    timeframes=requested,
                    limit=chosen_limit,
                    features=regime_features(),
                    detection=settings,
                    transport=replay_transport,
                    clock=lambda moment=instant: moment,
                )
                inputs, assessment = setup_inputs_and_assessment_for_sheet(
                    sheet,
                    policy=policy,
                    context_policy=context_policy,
                    research_confirmation_max_age=override,
                )
            except InsufficientDataError:
                # Counted, never swallowed: an insufficiency inside the measured
                # window means the derived warm-up did not actually hold, which
                # is the exact failure this milestone exists to detect.
                if measured:
                    insufficient_measured += 1
                else:
                    insufficient_priming += 1
                continue

            if measured:
                for view in sheet.views:
                    closed = view.sheet.window.closed_count
                    role_name = view.role.value
                    previous = minimum_closed.get(role_name)
                    if previous is None or closed < previous:
                        minimum_closed[role_name] = closed
                    if view.sheet.warming_up:
                        warming_feature_instants += 1
                    if closed < chosen_limit:
                        short_window_instants += 1

            execution_view = sheet.by_role[TimeframeRole.EXECUTION]
            key, is_new, is_first_confirmation = tracker.observe(
                symbol, assessment.direction, assessment.state, instant
            )
            historical = HistoricalObservation(
                symbol=symbol,
                as_of=assessment.as_of,
                status=assessment.state,
                direction=assessment.direction,
                setup_id=key,
                is_new_setup=is_new,
                directional_factors=tuple(
                    FamilyLean(family=factor.family, lean=factor.lean.value)
                    for factor in assessment.directional_factors
                ),
                thesis=assessment.thesis,
                confirmation=assessment.confirmation,
                trigger_kind=(
                    None if assessment.trigger is None else assessment.trigger.kind.value
                ),
                trigger_price=(
                    None
                    if assessment.trigger is None or assessment.trigger.level is None
                    else assessment.trigger.level.price
                ),
                reference_price=assessment.reference_price,
                stop_price=None if assessment.stop is None else assessment.stop.price,
                target_price=(
                    None if not assessment.targets else assessment.targets[0].price
                ),
                risk_reward_ratio=(
                    None
                    if assessment.risk_reward is None
                    else assessment.risk_reward.ratio
                ),
                sufficiency=assessment.sufficiency.value,
                context_regime_structure=inputs.context_regime_structure.value,
                context_regime_volatility=inputs.context_regime_volatility.value,
                context_regime_participation=inputs.context_regime_participation.value,
                execution_last_timestamp=execution_view.sheet.window.last_timestamp,
                policy_id=assessment.policy_id,
            )
            observations.append(
                ResearchObservation(
                    observation=historical,
                    in_measurement=measured,
                    opportunity_key=key,
                    is_new_opportunity=is_new,
                    is_first_confirmation=is_first_confirmation,
                    confirmation_break_age_bars=_break_age(inputs, assessment),
                    segment=_segment_of(ordered_segments, instant) if measured else None,
                )
            )

            if is_first_confirmation and not measured:
                confirmations_first_seen_while_priming += 1

            if (
                measured
                and is_first_confirmation
                and assessment.risk_reward is not None
                and assessment.stop is not None
                and assessment.targets
                and assessment.reference_price is not None
                and execution_view.sheet.window.last_timestamp is not None
            ):
                outcome = evaluate_outcome(
                    full_execution_series,
                    setup_id=key,
                    symbol=symbol,
                    direction=assessment.direction,
                    confirmed_at=execution_view.sheet.window.last_timestamp,
                    reference_price=assessment.reference_price,
                    stop_price=assessment.stop.price,
                    target_price=assessment.targets[0].price,
                    risk_reward_ratio=assessment.risk_reward.ratio,
                    window_bars=evaluation_window_bars,
                )
                outcomes.append(outcome)
                confirmed_index = next(
                    (
                        position
                        for position, candle in enumerate(full_execution_series.candles)
                        if candle.timestamp == outcome.confirmed_at
                    ),
                    None,
                )
                available_after = (
                    0
                    if confirmed_index is None
                    else len(full_execution_series.candles) - confirmed_index - 1
                )
                if available_after < evaluation_window_bars:
                    truncated_tail_outcomes += 1

    return ResearchBacktestRun(
        schema_version=RESEARCH_SCHEMA_VERSION,
        created_at=run_at,
        symbols=tuple(symbols),
        timeframes={role.value: interval for role, interval in requested.items()},
        window=window,
        warmup=warmup,
        segments=ordered_segments,
        availability=availability,
        variant=variant,
        evaluation_window_bars=evaluation_window_bars,
        identity_priming_bars=identity_priming_bars,
        data_boundaries=dataset.boundaries,
        context_policy_id=(
            ContextPolicy().policy_id if context_policy is None else context_policy.policy_id
        ),
        observations=tuple(observations),
        outcomes=tuple(outcomes),
        limitations=RESEARCH_LIMITATIONS,
        metadata={
            "candle_limit": chosen_limit,
            "insufficient_data_measured_instants": insufficient_measured,
            "insufficient_data_priming_instants": insufficient_priming,
            "outcomes_against_truncated_tail": truncated_tail_outcomes,
            "confirmations_first_seen_while_priming": (
                confirmations_first_seen_while_priming
            ),
            "measured_role_views_with_warming_features": warming_feature_instants,
            "measured_role_views_below_requested_window": short_window_instants,
            "minimum_closed_candles_by_role": dict(sorted(minimum_closed.items())),
        },
    )


def run_research_study(
    symbols: Sequence[str] = DEFAULT_RESEARCH_SYMBOLS,
    *,
    measurement_start: datetime,
    measurement_end: datetime,
    run_at: datetime,
    outcome_tail_end: datetime | None = None,
    variant_max_ages: Sequence[int] = DEFAULT_VARIANT_MAX_AGES,
    timeframes: Mapping[TimeframeRole, str] | None = None,
    limit: int | None = None,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
    detection: DetectionSettings | None = None,
    evaluation_window_bars: int = DEFAULT_EVALUATION_WINDOW_BARS,
    identity_priming_bars: int = DEFAULT_IDENTITY_PRIMING_BARS,
    transport: Transport | None = None,
    base_url: str | None = None,
    require_availability: bool = True,
) -> ResearchStudy:
    """Derive the window, measure availability, fetch once, and replay every variant.

    ``outcome_tail_end`` defaults to ``measurement_end`` plus the evaluation
    window scaled by the execution interval — exactly enough for a setup
    confirmed on the last measured bar to resolve, and no more.

    ``require_availability`` is the honesty switch the brief asks for. Left
    ``True``, a window the provider cannot satisfy raises with the measured
    shortfall rather than quietly measuring a shorter period and reporting it
    under the requested dates. Set ``False`` only to inspect an insufficient
    window deliberately; the resulting run still carries the unsatisfied
    availability report.

    Raises:
        ResearchError: the requested window is not satisfiable and
            ``require_availability`` is set.
    """
    requested = dict(DEFAULT_TIMEFRAMES if timeframes is None else timeframes)
    missing = [role.value for role in TimeframeRole if role not in requested]
    if missing:
        raise ResearchError(f"timeframes must map every role; missing {missing}")
    chosen_limit = DEFAULT_BACKTEST_LIMIT if limit is None else limit
    warmup = derive_warmup(
        requested, limit=chosen_limit, detection=detection, policy=policy
    )
    execution_interval = requested[TimeframeRole.EXECUTION]
    tail_end = (
        measurement_end + evaluation_window_bars * interval_duration(execution_interval)
        if outcome_tail_end is None
        else outcome_tail_end
    )
    # The warm-up prefix must also cover the identity-priming replay: those
    # instants are not counted, but the tracker they prime decides how the
    # measured window's first opportunity is attributed, so they must be as
    # warm as any measured instant.
    priming_prefix = identity_priming_bars * interval_duration(execution_interval)
    window = ResearchWindow(
        warmup_start=measurement_start - warmup.prefix - priming_prefix,
        measurement_start=measurement_start,
        measurement_end=measurement_end,
        outcome_tail_end=tail_end,
    )
    segments = build_segments(window)
    intervals = tuple(sorted(set(requested.values())))
    availability = probe_availability(
        symbols,
        intervals,
        required_from=required_from_by_interval(window, warmup, intervals),
        probed_at=run_at,
        transport=transport,
        base_url=base_url,
    )
    if require_availability and not availability.is_satisfiable:
        worst = availability.unsatisfied[0]
        raise ResearchError(
            "the requested measurement window is not satisfiable: "
            f"{worst.symbol} {worst.interval} begins "
            f"{'never' if worst.earliest_open is None else worst.earliest_open.date()}, "
            f"{worst.required_from.date()} is required, short by {worst.shortfall}. "
            f"{len(availability.unsatisfied)} of {len(availability.series)} series "
            "are short. Move measurement_start later, or drop the symbol."
        )

    dataset = fetch_research_dataset(
        symbols,
        intervals,
        window=window,
        warmup=warmup,
        fetched_at=run_at,
        transport=transport,
        base_url=base_url,
    )

    shared = dict(
        window=window,
        warmup=warmup,
        segments=segments,
        availability=availability,
        dataset=dataset,
        run_at=run_at,
        timeframes=requested,
        limit=chosen_limit,
        policy=policy,
        context_policy=context_policy,
        detection=detection,
        evaluation_window_bars=evaluation_window_bars,
        identity_priming_bars=identity_priming_bars,
    )
    baseline = run_research_variant(
        symbols, variant=PRODUCTION_BASELINE_VARIANT, **shared
    )
    variants = tuple(
        run_research_variant(
            symbols,
            variant=ResearchPolicyVariant.counterfactual(max_age),
            **shared,
        )
        for max_age in variant_max_ages
    )
    return ResearchStudy(
        window=window,
        warmup=warmup,
        segments=segments,
        availability=availability,
        baseline=baseline,
        variants=variants,
    )
