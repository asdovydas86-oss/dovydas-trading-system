"""Running a whole experiment: window, warm-up, fetch, replay, measure, digest.

    run_lab_study(...)  ──►  LabStudy
                              ├── manifest      (what was run, exactly)
                              ├── variants      (per-variant trades + metrics)
                              ├── gate          (what the 1W gate did)
                              └── robustness    (train/validation, segments)

**The manifest is written from the run, never typed alongside it.** Every field
— symbols, window, intervals, bar counts, cost policy, warm-up, code version —
is read off the objects the run actually used. A manifest a human maintains
beside a run is a manifest that eventually describes a different run.

**The digest covers results, not inputs.** Two runs of the same experiment over
the same history must produce the same digest, and any change to a policy, a
window or a fill rule must change it. It is computed over the trade records in a
canonical order, so it is invariant to symbol iteration order and to
`PYTHONHASHSEED`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Final

from fmis.decision_context import ContextPolicy
from fmis.market_regime import RegimePolicy
from fmis.pipeline.multi_timeframe import TimeframeRole
from fmis.pipeline.structural_facts import DetectionSettings
from fmis.providers.binance import Transport
from fmis.swing_lab.gate import GateImpact, measure_gate_impact
from fmis.swing_lab.metrics import VariantMetrics, compute_lab_metrics
from fmis.swing_lab.models import (
    LAB_SCHEMA_VERSION,
    GateObservation,
    LabTrade,
    LabVariant,
    SwingLabError,
)
from fmis.swing_lab.replay import (
    VariantReplay,
    dataset_for_group,
    group_variants,
    replay_variant_group,
)
from fmis.swing_lab.trades import FRICTIONLESS_COSTS, LAB_TRADE_BASIS
from fmis.swing_lab.variants import PRE_SPECIFIED_VARIANTS, CONTEXT_ONLY_VARIANT
from fmis.swing_setup.backtest_harness import DEFAULT_BACKTEST_LIMIT, DEFAULT_EVALUATION_WINDOW_BARS
from fmis.swing_setup.backtest_models import DataBoundary
from fmis.swing_setup.policy import CONFIRMATION_LOOKBACK_BARS, MINIMUM_AGREEING_FAMILIES
from fmis.swing_setup.research_harness import (
    DEFAULT_IDENTITY_PRIMING_BARS,
    build_segments,
)
from fmis.swing_setup.research_models import (
    ResearchWindow,
    TemporalSegment,
    interval_duration,
)
from fmis.swing_setup.research_warmup import (
    derive_warmup,
    probe_availability,
    required_from_by_interval,
)
from fmis.trade_lifecycle import PaperCostPolicy

__all__ = [
    "LAB_LIMITATIONS",
    "LabManifest",
    "VariantResult",
    "LabStudy",
    "run_lab_study",
]

LAB_LIMITATIONS: Final[tuple[str, ...]] = (
    "BW-1: Every limitation Milestone BC's research harness carries (BC-1 to "
    "BC-8, and AV-1 to AV-9 beneath them) applies unchanged. This milestone "
    "adds trade simulation, R-based metrics and policy variants; it does not "
    "add order-book depth, spread, partial fills, funding, borrow cost or "
    "position sizing.",
    "BW-2: The measurement window is bounded by the CONTEXT role's own warm-up, "
    "which at the production 1w mapping is 250 weekly candles — about 4.8 "
    "years of history that must exist BEFORE the window opens. This is not an "
    "arbitrary choice: it is the analysis window production itself uses. It "
    "excludes younger symbols entirely and is the single largest constraint on "
    "sample size in this study.",
    "BW-3: A variant that changes the role→interval mapping has a different "
    "warm-up requirement and therefore could be measured over a longer window "
    "and more symbols than the 1w variants. Every headline comparison in this "
    "study is nevertheless run over the SAME window and the SAME symbols, "
    "because a variant compared over more history is not being compared.",
    "BW-4: Trades are simulated one at a time with no portfolio, no position "
    "sizing, no capital constraint and no limit on concurrent exposure. "
    "Expectancy in R is therefore a per-trade statistic and NOT a claim about "
    "what an account would have returned.",
    "BW-5: Outcomes overlap. Setups on co-moving symbols confirm within hours "
    "of each other and their evaluation windows intersect, so trades are not "
    "independent observations and every interval implied by an average here is "
    "narrower than the true one.",
    "BW-6: An evaluation window that ends before the stop or the target is "
    "reached exits at that bar's close (TIME_STOP). This is a stated "
    "measurement policy, not a trading rule the owner would follow, and the "
    "count of such exits is reported for every variant.",
    "BW-7: No result here is a forward test. Every figure is in-sample with "
    "respect to the repository's own development history: the policy was "
    "written by people who had already lived through this price history.",
)


@dataclass(frozen=True, slots=True)
class LabManifest:
    """What was run, exactly — enough to rebuild the study from scratch."""

    experiment_id: str
    schema_version: int
    generated_at: datetime
    symbols: tuple[str, ...]
    variant_ids: tuple[str, ...]
    measurement_start: datetime
    measurement_end: datetime
    warmup_start: datetime
    outcome_tail_end: datetime
    interval_groups: tuple[tuple[str, str, str], ...]
    candle_limit: int
    evaluation_window_bars: int
    identity_priming_bars: int
    cost_policy: Mapping[str, Any]
    setup_policy_id: str
    confirmation_lookback_bars: int
    minimum_agreeing_families: int
    data_boundaries: tuple[DataBoundary, ...]
    trade_basis: str
    limitations: tuple[str, ...]
    result_digest: str

    def to_payload(self) -> dict[str, Any]:
        """A JSON-safe mapping. Sorted keys, ISO instants, decimal text."""
        return {
            "experiment_id": self.experiment_id,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at.isoformat(),
            "symbols": list(self.symbols),
            "variant_ids": list(self.variant_ids),
            "measurement_start": self.measurement_start.isoformat(),
            "measurement_end": self.measurement_end.isoformat(),
            "warmup_start": self.warmup_start.isoformat(),
            "outcome_tail_end": self.outcome_tail_end.isoformat(),
            "interval_groups": [list(group) for group in self.interval_groups],
            "candle_limit": self.candle_limit,
            "evaluation_window_bars": self.evaluation_window_bars,
            "identity_priming_bars": self.identity_priming_bars,
            "cost_policy": dict(self.cost_policy),
            "setup_policy_id": self.setup_policy_id,
            "confirmation_lookback_bars": self.confirmation_lookback_bars,
            "minimum_agreeing_families": self.minimum_agreeing_families,
            "bar_counts": {
                f"{boundary.symbol}:{boundary.interval}": boundary.candle_count
                for boundary in self.data_boundaries
            },
            "trade_basis": self.trade_basis,
            "limitations": list(self.limitations),
            "result_digest": self.result_digest,
        }


@dataclass(frozen=True, slots=True)
class VariantResult:
    """One variant's replay, its headline metrics, and its trades."""

    variant: LabVariant
    replay: VariantReplay
    metrics: VariantMetrics

    @property
    def trades(self) -> tuple[LabTrade, ...]:
        return self.replay.trades


@dataclass(frozen=True, slots=True)
class LabStudy:
    """Everything one experiment produced."""

    manifest: LabManifest
    window: ResearchWindow
    segments: tuple[TemporalSegment, ...]
    results: tuple[VariantResult, ...]
    gate: GateImpact
    costs: PaperCostPolicy

    def result_for(self, variant_id: str) -> VariantResult:
        for result in self.results:
            if result.variant.variant_id == variant_id:
                return result
        raise SwingLabError(
            f"this study holds no variant {variant_id!r}; it holds "
            f"{', '.join(r.variant.variant_id for r in self.results)}"
        )


def _canonical_trade(trade: LabTrade) -> list[Any]:
    """One trade as a canonically ordered, JSON-safe row for digesting."""

    def text(value: Decimal | None) -> str | None:
        return None if value is None else format(value.normalize(), "f")

    return [
        trade.variant_id,
        trade.symbol,
        trade.setup_id,
        trade.direction.value,
        trade.signal_at.isoformat(),
        None if trade.entry_at is None else trade.entry_at.isoformat(),
        text(trade.entry_price),
        text(trade.initial_stop),
        text(trade.target),
        None if trade.exit_at is None else trade.exit_at.isoformat(),
        text(trade.exit_price),
        trade.exit_reason.value,
        trade.bars_held,
        text(trade.net_r),
        text(trade.mfe_r),
        text(trade.mae_r),
        trade.cost_policy_id,
    ]


def result_digest(results: Sequence[VariantResult]) -> str:
    """A stable digest over every trade in the study.

    Sorted by the trade's own identity rather than by the order symbols were
    iterated, so the digest is invariant to symbol ordering and to
    `PYTHONHASHSEED`. Two runs of the same experiment agree; any change to a
    policy, a window, a cost or a fill rule disagrees.
    """
    rows = sorted(
        (_canonical_trade(trade) for result in results for trade in result.trades),
        key=lambda row: (row[0], row[1], row[4], row[2]),
    )
    payload = json.dumps(rows, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_lab_study(
    symbols: Sequence[str],
    *,
    measurement_start: datetime,
    measurement_end: datetime,
    run_at: datetime,
    experiment_id: str,
    variants: Sequence[LabVariant] = PRE_SPECIFIED_VARIANTS,
    costs: PaperCostPolicy = FRICTIONLESS_COSTS,
    gate_counterfactual_id: str = CONTEXT_ONLY_VARIANT.variant_id,
    limit: int = DEFAULT_BACKTEST_LIMIT,
    evaluation_window_bars: int = DEFAULT_EVALUATION_WINDOW_BARS,
    identity_priming_bars: int = DEFAULT_IDENTITY_PRIMING_BARS,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
    detection: DetectionSettings | None = None,
    transport: Transport | None = None,
    base_url: str | None = None,
    require_availability: bool = True,
) -> LabStudy:
    """Run one complete experiment over real history and measure every variant.

    The window is derived exactly as Milestone BC derives it — a warm-up prefix
    computed from the production dependencies, an identity-priming prefix before
    the measurement window, and an outcome tail after it — but **per interval
    group**, because a variant on 1d/4h/1h needs a different prefix from one on
    1w/1d/4h. The *measurement* window is identical across groups regardless, so
    every variant is judged over the same calendar period.

    Raises:
        SwingLabError: the requested window is not satisfiable for some symbol
            and ``require_availability`` is set, or the arguments are invalid.
    """
    if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence) or not symbols:
        raise SwingLabError("symbols must be a non-empty, non-string sequence")
    if not isinstance(run_at, datetime) or run_at.utcoffset() is None:
        raise SwingLabError("run_at must be a timezone-aware datetime")
    if measurement_end <= measurement_start:
        raise SwingLabError("measurement_end must be after measurement_start")
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise SwingLabError("experiment_id must be a non-empty str")
    if not isinstance(costs, PaperCostPolicy):
        raise TypeError("costs must be a PaperCostPolicy")

    groups = group_variants(variants)
    results: list[VariantResult] = []
    gate_observations: list[GateObservation] = []
    boundaries: list[DataBoundary] = []
    window_for_manifest: ResearchWindow | None = None
    segments: tuple[TemporalSegment, ...] = ()

    for signature, members in groups:
        timeframes = dict(members[0].timeframes)
        warmup = derive_warmup(
            timeframes, limit=limit, detection=detection, policy=policy
        )
        execution_interval = timeframes[TimeframeRole.EXECUTION]
        priming_prefix = identity_priming_bars * interval_duration(execution_interval)
        window = ResearchWindow(
            warmup_start=measurement_start - warmup.prefix - priming_prefix,
            measurement_start=measurement_start,
            measurement_end=measurement_end,
            outcome_tail_end=measurement_end
            + evaluation_window_bars * interval_duration(execution_interval),
        )
        if window_for_manifest is None:
            window_for_manifest = window
            segments = build_segments(window)
        intervals = tuple(sorted(set(timeframes.values())))
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
            raise SwingLabError(
                "the requested measurement window is not satisfiable for "
                f"{'/'.join(signature)}: {worst.symbol} {worst.interval} begins "
                f"{'never' if worst.earliest_open is None else worst.earliest_open.date()}, "
                f"{worst.required_from.date()} is required, short by "
                f"{worst.shortfall}. {len(availability.unsatisfied)} of "
                f"{len(availability.series)} series are short. Move "
                "measurement_start later, or drop the symbol."
            )
        dataset = dataset_for_group(
            symbols,
            intervals,
            window=window,
            warmup=warmup,
            fetched_at=run_at,
            transport=transport,
            base_url=base_url,
        )
        boundaries.extend(dataset.boundaries)
        counterfactual = (
            gate_counterfactual_id
            if any(m.variant_id == gate_counterfactual_id for m in members)
            else None
        )
        replays, gates = replay_variant_group(
            symbols,
            members,
            window=window,
            warmup=warmup,
            segments=segments,
            dataset=dataset,
            costs=costs,
            evaluation_window_bars=evaluation_window_bars,
            limit=limit,
            identity_priming_bars=identity_priming_bars,
            policy=policy,
            context_policy=context_policy,
            detection=detection,
            gate_counterfactual_id=counterfactual,
        )
        gate_observations.extend(gates)
        for replay in replays:
            results.append(
                VariantResult(
                    variant=replay.variant,
                    replay=replay,
                    metrics=compute_lab_metrics(
                        replay.trades, label=replay.variant.variant_id
                    ),
                )
            )

    if window_for_manifest is None:  # pragma: no cover - groups is non-empty
        raise SwingLabError("no variant group produced a window")

    ordered = tuple(results)
    manifest = LabManifest(
        experiment_id=experiment_id,
        schema_version=LAB_SCHEMA_VERSION,
        generated_at=run_at,
        symbols=tuple(symbols),
        variant_ids=tuple(result.variant.variant_id for result in ordered),
        measurement_start=measurement_start,
        measurement_end=measurement_end,
        warmup_start=window_for_manifest.warmup_start,
        outcome_tail_end=window_for_manifest.outcome_tail_end,
        interval_groups=tuple(signature for signature, _ in groups),
        candle_limit=limit,
        evaluation_window_bars=evaluation_window_bars,
        identity_priming_bars=identity_priming_bars,
        cost_policy=costs.to_payload(),
        setup_policy_id=ordered[0].variant.policy_id if ordered else "",
        confirmation_lookback_bars=CONFIRMATION_LOOKBACK_BARS,
        minimum_agreeing_families=MINIMUM_AGREEING_FAMILIES,
        data_boundaries=tuple(boundaries),
        trade_basis=LAB_TRADE_BASIS,
        limitations=LAB_LIMITATIONS,
        result_digest=result_digest(ordered),
    )
    return LabStudy(
        manifest=manifest,
        window=window_for_manifest,
        segments=segments,
        results=ordered,
        gate=measure_gate_impact(tuple(gate_observations), ordered),
        costs=costs,
    )
