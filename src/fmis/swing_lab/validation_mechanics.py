"""Entry timing, exit management and the lower-timeframe evidence that enables both.

Three studies share one module because they share one prerequisite. Milestone BX
could measure neither entry refinement nor exit management, and in both cases the
obstacle was the same: **a 4H bar cannot be ordered from four prices.** An entry
that fills partway through a bar cannot have its outcome measured against that
whole bar, and a partial exit adds a third level to bars the simulator already
refused. `fmis.swing_lab.intrabar` removes the obstacle with real 1H and 15m
candles, and these three studies are what it buys.

    §8  ambiguity     how many 4H refusals does 1H resolve? how many need 15m?
    §7  entry         does a different fill rule produce different geometry?
    §9  exit          does a simple management rule keep the R that BX saw given back?

**The one rule that makes this honest, restated because it is the whole thing:**
lower-timeframe candles resolve **outcome ordering** and never reach a planning
decision. The geometry plan for every trade in every study here is the *same*
plan, produced by the *same* policy from the *same* frozen `GeometryCandidate`,
which holds no bar of any resolution. What varies is when the position opened and
how it was managed afterwards. `test_swing_lab_validation_nolookahead` mutates
the 1H series and requires every plan to be byte-identical.

**Every study carries a control that must reproduce a known number.** The entry
family's control is `entry_immediate`, which must fill exactly where
`fmis.swing_lab.trades.simulate_trade` fills; the exit family's is
`exit_full_target` **run without a ladder**, which must reproduce that simulator
trade-for-trade. A study whose control drifts is a study measuring its own
machinery, and both controls are asserted rather than assumed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from fmis.paper.models import PriceBar
from fmis.swing_lab.entry import (
    PRE_DECLARED_ENTRY_POLICIES,
    EntryFill,
    EntryMiss,
    EntryPolicy,
    MissReason,
    PathRole,
    resolve_entry,
)
from fmis.swing_lab.exits import (
    PRE_DECLARED_EXIT_POLICIES,
    ExitPolicy,
    ManagedResult,
    simulate_managed_trade,
)
from fmis.swing_lab.geometry import GeometryCandidate, GeometryPlan, GeometrySkip, PlansGeometry
from fmis.swing_lab.geometry_replay import GeometryCapture
from fmis.swing_lab.intrabar import BarLadder
from fmis.swing_lab.metrics import VariantMetrics, compute_lab_metrics
from fmis.swing_lab.models import LabExitReason, LabTrade, SwingLabError
from fmis.swing_setup.research_models import interval_duration
from fmis.trade_lifecycle import PaperCostPolicy

__all__ = [
    "LadderSet",
    "EntryMeasurement",
    "ExitMeasurement",
    "AmbiguityReading",
    "MechanicsStudy",
    "window_bars_for",
    "run_entry_study",
    "run_exit_study",
    "unresolved_spans",
    "ambiguity_reading",
    "fetch_refinement_bars",
    "ladder_set",
]


@dataclass(frozen=True, slots=True)
class LadderSet:
    """Every symbol's resolution ladder, plus the intervals it actually holds.

    Held as one object rather than three mappings so a study cannot be handed a
    1H series for one symbol and a 15m series for another and quietly produce a
    result whose resolution varies by instrument.
    """

    execution_interval: str
    refinement_interval: str
    fine_interval: str | None
    ladders: Mapping[str, BarLadder]
    refinement_bars: Mapping[str, tuple[PriceBar, ...]]

    def ladder(self, symbol: str, *, from_interval: str) -> BarLadder | None:
        """The ladder for one symbol, rooted at ``from_interval``.

        Returns ``None`` when the requested rung is not in the ladder — which
        happens for a 1H-path study on a symbol whose refinement series is
        missing — so a caller walks unresolved rather than walking a ladder
        whose top rung is a different timeframe from its bars.
        """
        found = self.ladders.get(symbol)
        if found is None:
            return None
        if from_interval not in found.intervals:
            return None
        position = found.intervals.index(from_interval)
        return BarLadder(symbol=symbol, rungs=found.rungs[position:])


def window_bars_for(interval: str, *, execution_interval: str, execution_bars: int) -> int:
    """The same wall-clock evaluation window, counted in a different bar size.

    A 1H walk over "180 bars" would cover 7.5 days where the 4H walk covers 30,
    and the two results would differ mostly because one gave price four times
    less room to reach a target. Scaling by the intervals' own durations keeps
    the *window* fixed and lets the resolution be the only thing that changed.

    Raises:
        SwingLabError: the finer interval does not divide the coarse one, so no
            whole number of bars covers the same span.
    """
    coarse = interval_duration(execution_interval)
    fine = interval_duration(interval)
    span = coarse * execution_bars
    if span % fine:
        raise SwingLabError(
            f"{execution_bars} × {execution_interval} is not a whole number of "
            f"{interval} bars; the two walks would cover different windows"
        )
    return int(span // fine)


def _unentered(
    plan: GeometryPlan,
    *,
    policy_id: str,
    reason: LabExitReason,
    costs: PaperCostPolicy,
    note: str,
) -> LabTrade:
    """A setup that produced no position. **Counted, never dropped.**"""
    candidate = plan.candidate
    return LabTrade(
        variant_id=policy_id, symbol=candidate.symbol, setup_id=candidate.setup_id,
        direction=candidate.direction, signal_at=candidate.signal_at,
        entry_at=None, entry_price=None,
        initial_stop=Decimal(str(plan.stop.price)), target=Decimal(str(plan.target.price)),
        planned_reference_price=Decimal(str(plan.entry)),
        exit_at=None, exit_price=None, exit_reason=reason, bars_held=0,
        gross_r=None, net_r=None, mfe_r=None, mae_r=None,
        cost_policy_id=costs.policy_id, planned_risk_reward=plan.planned_rr,
        segment=candidate.segment,
        context_regime_structure=candidate.context_regime_structure,
        context_structural_trend=candidate.context_structural_trend,
        setup_structural_trend=candidate.setup_structural_trend,
        metadata={"note": note},
    )


@dataclass(frozen=True, slots=True)
class EntryMeasurement:
    """One entry rule, applied to every plan the geometry policy produced."""

    policy: EntryPolicy
    trades: tuple[LabTrade, ...]
    filled: int
    missed: int
    miss_reasons: tuple[tuple[str, int], ...]
    metrics: VariantMetrics
    median_bars_waited: float | None
    gapped_fills: int

    @property
    def fill_rate(self) -> float | None:
        total = self.filled + self.missed
        return None if total == 0 else self.filled / total

    def payload(self) -> dict[str, Any]:
        value = self.metrics.expectancy_r.value
        return {
            "policy": self.policy.payload(),
            "filled": self.filled,
            "missed": self.missed,
            "fill_rate": self.fill_rate,
            "miss_reasons": [list(item) for item in self.miss_reasons],
            "measurable_trades": self.metrics.measurable_trades,
            "ambiguous_trades": self.metrics.ambiguous_trades,
            "expectancy_r": None if value is None else str(value),
            "total_r": str(self.metrics.total_r),
            "median_bars_waited": self.median_bars_waited,
            "gapped_fills": self.gapped_fills,
        }


@dataclass(frozen=True, slots=True)
class ExitMeasurement:
    """One exit mechanic, applied to every position the baseline entry opened."""

    policy: ExitPolicy
    used_ladder: bool
    trades: tuple[LabTrade, ...]
    metrics: VariantMetrics
    armed: int
    ambiguous: int
    resolved_by_descent: int
    mean_mfe_captured: Decimal | None

    def payload(self) -> dict[str, Any]:
        value = self.metrics.expectancy_r.value
        return {
            "policy": self.policy.payload(),
            "used_ladder": self.used_ladder,
            "measurable_trades": self.metrics.measurable_trades,
            "ambiguous_trades": self.ambiguous,
            "resolved_by_descent": self.resolved_by_descent,
            "armed": self.armed,
            "expectancy_r": None if value is None else str(value),
            "total_r": str(self.metrics.total_r),
            "average_win_r": (
                None if self.metrics.average_win_r.value is None
                else str(self.metrics.average_win_r.value)
            ),
            "average_loss_r": (
                None if self.metrics.average_loss_r.value is None
                else str(self.metrics.average_loss_r.value)
            ),
            "max_drawdown_r": str(self.metrics.max_drawdown.max_drawdown_r),
            "mean_mfe_captured": (
                None if self.mean_mfe_captured is None else str(self.mean_mfe_captured)
            ),
        }


@dataclass(frozen=True, slots=True)
class AmbiguityReading:
    """§8's answer: how much of BX's NOT MEASURABLE the ladder actually removed."""

    without_ladder: int
    with_ladder: int
    resolved: int
    still_ambiguous: int
    unresolved_spans: tuple[tuple[str, str], ...]

    @property
    def resolution_rate(self) -> float | None:
        return None if self.without_ladder == 0 else self.resolved / self.without_ladder

    def payload(self) -> dict[str, Any]:
        return {
            "ambiguous_without_ladder": self.without_ladder,
            "ambiguous_with_ladder": self.with_ladder,
            "resolved": self.resolved,
            "still_ambiguous": self.still_ambiguous,
            "resolution_rate": self.resolution_rate,
            "unresolved_spans": [list(item) for item in self.unresolved_spans],
        }


@dataclass(frozen=True, slots=True)
class MechanicsStudy:
    """The three studies together, with the geometry policy they all share."""

    geometry_policy_id: str
    sample: str
    entries: tuple[EntryMeasurement, ...]
    exits: tuple[ExitMeasurement, ...]
    ambiguity: AmbiguityReading

    def payload(self) -> dict[str, Any]:
        return {
            "geometry_policy_id": self.geometry_policy_id,
            "sample": self.sample,
            "entries": [item.payload() for item in self.entries],
            "exits": [item.payload() for item in self.exits],
            "ambiguity": self.ambiguity.payload(),
        }


def _plans(capture: GeometryCapture, policy: PlansGeometry) -> tuple[GeometryPlan, ...]:
    """Every plan this geometry produced over the capture. **The shared input.**

    Both studies below start here, which is what makes them comparable: the entry
    family and the exit family measure the *same* geometry on the *same* setups,
    so a difference between two entry rules cannot be a difference in which
    trades were planned.
    """
    plans = []
    for candidate in capture.candidates:
        outcome = policy.plan(candidate)
        if not isinstance(outcome, GeometrySkip):
            plans.append(outcome)
    return tuple(plans)


def _median(values: Sequence[int]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def run_entry_study(
    capture: GeometryCapture,
    *,
    geometry: PlansGeometry,
    ladders: LadderSet,
    costs: PaperCostPolicy,
    execution_window_bars: int,
    sample: str,
    entry_policies: Sequence[EntryPolicy] = PRE_DECLARED_ENTRY_POLICIES,
    exit_policy: ExitPolicy | None = None,
) -> tuple[EntryMeasurement, ...]:
    """§7: the same geometry, opened four different ways.

    Every rule is walked under the **same** exit mechanic — the full-target
    control — so the family measures entry timing and nothing else. Each rule
    walks the series it declared (`PathRole`), with the evaluation window scaled
    by `window_bars_for` so all four cover the same thirty days.

    Raises:
        SwingLabError: a policy declares a path this ladder set does not hold.
    """
    baseline_exit = exit_policy or next(
        item for item in PRE_DECLARED_EXIT_POLICIES if item.is_baseline
    )
    plans = _plans(capture, geometry)
    results: list[EntryMeasurement] = []

    for policy in entry_policies:
        interval = (
            ladders.execution_interval
            if policy.path is PathRole.EXECUTION
            else ladders.refinement_interval
        )
        bars_in_window = window_bars_for(
            interval,
            execution_interval=ladders.execution_interval,
            execution_bars=execution_window_bars,
        )
        trades: list[LabTrade] = []
        misses: dict[str, int] = {}
        filled = gapped = 0
        waits: list[int] = []

        for plan in plans:
            candidate = plan.candidate
            symbol = candidate.symbol
            path = (
                capture.bars_by_symbol[symbol]
                if policy.path is PathRole.EXECUTION
                else ladders.refinement_bars.get(symbol, ())
            )
            if not path:
                trades.append(
                    _unentered(
                        plan, policy_id=policy.policy_id,
                        reason=LabExitReason.ENTRY_NOT_TRIGGERED, costs=costs,
                        note=MissReason.REFINEMENT_UNAVAILABLE.statement,
                    )
                )
                misses[MissReason.REFINEMENT_UNAVAILABLE.value] = (
                    misses.get(MissReason.REFINEMENT_UNAVAILABLE.value, 0) + 1
                )
                continue

            signal_close = candidate.signal_at + interval_duration(
                ladders.execution_interval
            )
            fill = resolve_entry(
                policy,
                path=path,
                signal_at=candidate.signal_at,
                signal_close_at=signal_close,
                reference_price=Decimal(str(plan.entry)),
                direction=candidate.direction,
            )
            if isinstance(fill, EntryMiss):
                misses[fill.reason.value] = misses.get(fill.reason.value, 0) + 1
                trades.append(
                    _unentered(
                        plan, policy_id=policy.policy_id,
                        reason=LabExitReason.ENTRY_NOT_TRIGGERED, costs=costs,
                        note=fill.statement,
                    )
                )
                continue

            filled += 1
            waits.append(fill.bars_waited)
            if fill.gapped:
                gapped += 1
            managed = simulate_managed_trade(
                path,
                variant_id=policy.policy_id,
                symbol=symbol,
                setup_id=candidate.setup_id,
                direction=candidate.direction,
                entry_index=fill.index,
                entry_price=fill.price,
                entry_at=fill.at,
                signal_at=candidate.signal_at,
                reference_price=Decimal(str(plan.entry)),
                stop_price=Decimal(str(plan.stop.price)),
                target_price=Decimal(str(plan.target.price)),
                planned_risk_reward=plan.planned_rr,
                window_bars=bars_in_window,
                costs=costs,
                policy=baseline_exit,
                ladder=ladders.ladder(symbol, from_interval=interval),
                segment=candidate.segment,
                context_regime_structure=candidate.context_regime_structure,
                context_structural_trend=candidate.context_structural_trend,
                setup_structural_trend=candidate.setup_structural_trend,
            )
            trades.append(managed.trade)

        frozen = tuple(trades)
        results.append(
            EntryMeasurement(
                policy=policy,
                trades=frozen,
                filled=filled,
                missed=len(plans) - filled,
                miss_reasons=tuple(sorted(misses.items())),
                metrics=compute_lab_metrics(frozen, label=f"{policy.policy_id}:{sample}"),
                median_bars_waited=_median(waits),
                gapped_fills=gapped,
            )
        )
    return tuple(results)


def run_exit_study(
    capture: GeometryCapture,
    *,
    geometry: PlansGeometry,
    ladders: LadderSet,
    costs: PaperCostPolicy,
    execution_window_bars: int,
    sample: str,
    exit_policies: Sequence[ExitPolicy] = PRE_DECLARED_EXIT_POLICIES,
) -> tuple[ExitMeasurement, ...]:
    """§9: the same geometry and the same entry, managed four different ways.

    The baseline entry is used throughout — the open of the bar after the signal —
    so the family measures management and nothing else. `exit_full_target` is
    measured **twice**: once with the ladder and once without it, and the
    no-ladder run is the control that must reproduce
    `fmis.swing_lab.trades.simulate_trade`. The pair is what separates *the
    management rule helped* from *the finer data resolved trades the coarse
    simulator had refused*, which are different claims and would otherwise be
    reported as one number.
    """
    plans = _plans(capture, geometry)
    interval = ladders.execution_interval
    bars_in_window = execution_window_bars
    results: list[ExitMeasurement] = []

    variants: list[tuple[ExitPolicy, bool]] = []
    for policy in exit_policies:
        variants.append((policy, True))
        if policy.is_baseline:
            variants.append((policy, False))

    for policy, use_ladder in variants:
        trades: list[LabTrade] = []
        armed = ambiguous = descents = 0
        captured: list[Decimal] = []
        suffix = "" if use_ladder else "_no_ladder"

        for plan in plans:
            candidate = plan.candidate
            symbol = candidate.symbol
            path = capture.bars_by_symbol[symbol]
            if len(path) <= candidate.signal_index + 1:
                trades.append(
                    _unentered(
                        plan, policy_id=policy.policy_id + suffix,
                        reason=LabExitReason.NO_ENTRY_BAR, costs=costs,
                        note="history ended before an entry bar existed",
                    )
                )
                continue
            entry_bar = path[candidate.signal_index + 1]
            managed: ManagedResult = simulate_managed_trade(
                path,
                variant_id=policy.policy_id + suffix,
                symbol=symbol,
                setup_id=candidate.setup_id,
                direction=candidate.direction,
                entry_index=candidate.signal_index + 1,
                entry_price=entry_bar.open,
                entry_at=entry_bar.open_time,
                signal_at=candidate.signal_at,
                reference_price=Decimal(str(plan.entry)),
                stop_price=Decimal(str(plan.stop.price)),
                target_price=Decimal(str(plan.target.price)),
                planned_risk_reward=plan.planned_rr,
                window_bars=bars_in_window,
                costs=costs,
                policy=policy,
                ladder=(
                    ladders.ladder(symbol, from_interval=interval) if use_ladder else None
                ),
                segment=candidate.segment,
                context_regime_structure=candidate.context_regime_structure,
                context_structural_trend=candidate.context_structural_trend,
                setup_structural_trend=candidate.setup_structural_trend,
            )
            trades.append(managed.trade)
            if managed.armed_at is not None:
                armed += 1
            if managed.trade.exit_reason is LabExitReason.AMBIGUOUS_SAME_BAR:
                ambiguous += 1
            if managed.descents:
                descents += 1
            net, mfe = managed.trade.net_r, managed.trade.mfe_r
            if net is not None and mfe is not None and mfe > 0:
                captured.append(net / mfe)

        frozen = tuple(trades)
        results.append(
            ExitMeasurement(
                policy=policy,
                used_ladder=use_ladder,
                trades=frozen,
                metrics=compute_lab_metrics(
                    frozen, label=f"{policy.policy_id}{suffix}:{sample}"
                ),
                armed=armed,
                ambiguous=ambiguous,
                resolved_by_descent=descents,
                mean_mfe_captured=(
                    None if not captured else sum(captured) / len(captured)
                ),
            )
        )
    return tuple(results)


def unresolved_spans(measurements: Sequence[ExitMeasurement]) -> tuple[tuple[str, str], ...]:
    """Every (symbol, bar-open) still ambiguous at the finest rung available.

    This is what a second 15m pass fetches for. Returned as data rather than
    fetched here, because a module that reached the network from inside a walk
    would make the walk non-deterministic — and determinism is the property every
    reproducibility claim in this milestone rests on.
    """
    spans: set[tuple[str, str]] = set()
    for measurement in measurements:
        for trade in measurement.trades:
            if trade.exit_reason is LabExitReason.AMBIGUOUS_SAME_BAR and trade.exit_at:
                spans.add((trade.symbol, trade.exit_at.isoformat()))
    return tuple(sorted(spans))


def fetch_refinement_bars(
    symbols: Sequence[str],
    interval: str,
    *,
    start: datetime,
    end: datetime,
    spans: Sequence[tuple[str, datetime, datetime]] | None = None,
    transport: Any = None,
    base_url: str | None = None,
) -> dict[str, tuple[PriceBar, ...]]:
    """Fetch one lower-timeframe series per symbol. **The only network call here.**

    Reuses the replay transport (`fmis.swing_setup.backtest_replay.fetch_raw_klines`)
    and the decoder the research harness already uses, so a 1H bar reaching this
    package went through the identical ingestion boundary as every 4H bar. No new
    provider path exists.

    ``spans`` fetches **only the named windows** rather than a continuous series,
    which is how the 15m rung is populated: descending to 15m is needed for a
    handful of bars out of tens of thousands, and fetching years of 15m candles
    for all of them would cost two orders of magnitude more rows for the same
    answer. A ladder whose finest rung covers only some spans is safe by
    construction — `fmis.swing_lab.intrabar.BarLadder.refine` requires a
    **complete** cover of the bar it is refining and returns ``None`` otherwise,
    so a missing span leaves the event ambiguous rather than partially walked.
    """
    from fmis.swing_setup.backtest_replay import fetch_raw_klines
    from fmis.swing_setup.research_harness import decode_full_series
    from fmis.swing_lab.trades import to_price_bars

    requests: list[tuple[str, datetime, datetime]] = (
        [(symbol, start, end) for symbol in symbols]
        if spans is None
        else list(spans)
    )
    collected: dict[str, list[PriceBar]] = {}
    for symbol, window_start, window_end in requests:
        rows = fetch_raw_klines(
            symbol, interval,
            start_time=window_start, end_time=window_end,
            transport=transport, base_url=base_url,
        )
        if not rows:
            continue
        series = decode_full_series(symbol, interval, rows)
        collected.setdefault(symbol, []).extend(to_price_bars(series))
    return {
        symbol: tuple(
            # De-duplicated and re-ordered, because span fetches can overlap and
            # `bars_within` binary-searches on a sorted, unique sequence.
            sorted({bar.open_time: bar for bar in bars}.values(), key=lambda b: b.open_time)
        )
        for symbol, bars in collected.items()
    }


def ladder_set(
    capture: GeometryCapture,
    *,
    execution_interval: str,
    refinement: Mapping[str, tuple[PriceBar, ...]],
    refinement_interval: str,
    fine: Mapping[str, tuple[PriceBar, ...]] | None = None,
    fine_interval: str | None = None,
) -> LadderSet:
    """Assemble one ladder per symbol, coarsest rung first.

    A symbol with no refinement series gets a **one-rung ladder**, so its trades
    behave exactly as BX's did — ambiguous where the 4H bar is ambiguous — rather
    than silently borrowing another symbol's resolution.
    """
    if (fine is None) != (fine_interval is None):
        raise SwingLabError(
            "a fine rung needs both its bars and its interval, or neither"
        )
    ladders: dict[str, BarLadder] = {}
    for symbol, bars in capture.bars_by_symbol.items():
        rungs: list[tuple[str, tuple[PriceBar, ...]]] = [(execution_interval, bars)]
        below = refinement.get(symbol, ())
        if below:
            rungs.append((refinement_interval, below))
            finest = () if fine is None else fine.get(symbol, ())
            if finest and fine_interval is not None:
                rungs.append((fine_interval, finest))
        ladders[symbol] = BarLadder(symbol=symbol, rungs=tuple(rungs))
    return LadderSet(
        execution_interval=execution_interval,
        refinement_interval=refinement_interval,
        fine_interval=fine_interval,
        ladders=ladders,
        refinement_bars=dict(refinement),
    )


def ambiguity_reading(
    measurements: Sequence[ExitMeasurement],
) -> AmbiguityReading:
    """§8's headline, computed from the baseline pair rather than asserted.

    The comparison is `exit_full_target` **with** the ladder against the same
    policy **without** it — the identical geometry, entry, window and cost, so
    the only difference between the two counts is the lower-timeframe evidence.
    """
    with_ladder = next(
        (m for m in measurements if m.policy.is_baseline and m.used_ladder), None
    )
    without = next(
        (m for m in measurements if m.policy.is_baseline and not m.used_ladder), None
    )
    if with_ladder is None or without is None:
        raise SwingLabError(
            "an ambiguity reading needs the baseline exit measured both with and "
            "without a ladder; run_exit_study emits the pair"
        )
    return AmbiguityReading(
        without_ladder=without.ambiguous,
        with_ladder=with_ladder.ambiguous,
        resolved=without.ambiguous - with_ladder.ambiguous,
        still_ambiguous=with_ladder.ambiguous,
        unresolved_spans=unresolved_spans((with_ladder,)),
    )
