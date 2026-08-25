"""Diagnosing the geometry before proposing an alternative. **Evidence, then reading.**

§2 of the milestone brief asks a specific discipline of this milestone: *diagnose
the baseline before testing alternatives*, and *separate evidence from
interpretation*. This module is built around that separation.

* `Distribution` and the bucket breakdowns are **evidence**: counts and
  quantiles, each welded to its sample size, none of them asserting a cause.
* `Finding` is **interpretation**, and every one of them carries the measurement
  it was read from, so a reader can disagree with the reading without having to
  doubt the number.

A `Finding` never states a conclusion the counts do not support. When a cohort is
too small the finding says so and its ``supported`` is ``None`` — which is not a
negative answer, it is the absence of one.

**The GeometryRecord is a projection, never a record kind.** §1 of the brief asks
for a per-trade geometry record and §19 forbids persisting recomputable
aggregates. `GeometryRecord` is therefore a join of a plan, a trade and an
outcome computed on demand; nothing here is written to the trading store, and no
`RecordKind` was added.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from fmis.swing_lab.geometry import BASIS_POINT, GeometryPlan, GeometrySkip
from fmis.swing_lab.geometry_outcome import GeometryOutcome
from fmis.swing_lab.metrics import SAMPLE_FLOOR, VariantMetrics, lab_breakdown_by
from fmis.swing_lab.models import LabExitReason, LabTrade, SwingLabError, TradeVerdict

__all__ = [
    "Distribution",
    "GeometryRecord",
    "Finding",
    "Share",
    "GeometryDiagnosis",
    "describe",
    "diagnose_geometry",
]


@dataclass(frozen=True, slots=True)
class Share:
    """A count out of a total, which refuses to become a rate below the floor.

    The same discipline `LabMeasure` applies to averages. ``fraction`` is
    ``None`` when the denominator is below `SAMPLE_FLOOR`, and the two counts
    stay visible either way — a count is a fact at any sample size, a rate is
    not.
    """

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if self.numerator < 0 or self.denominator < 0:
            raise SwingLabError("a share cannot have a negative count")
        if self.numerator > self.denominator:
            raise SwingLabError(
                f"share numerator {self.numerator} exceeds denominator {self.denominator}"
            )

    @property
    def fraction(self) -> Decimal | None:
        if self.denominator < SAMPLE_FLOOR or self.denominator == 0:
            return None
        return Decimal(self.numerator) / Decimal(self.denominator)

    @property
    def text(self) -> str:
        value = self.fraction
        rendered = "—" if value is None else f"{value:.1%}"
        return f"{self.numerator}/{self.denominator} ({rendered})"


@dataclass(frozen=True, slots=True)
class Distribution:
    """One measured quantity's shape. Quantiles by linear interpolation.

    The quantile convention is stated rather than inherited from a library so two
    readers computing it by hand agree: values are sorted ascending, the rank of
    quantile *q* over *n* values is ``q * (n - 1)``, and a fractional rank
    interpolates linearly between its neighbours. This is NumPy's default
    ``linear`` method, spelled out because this repository computes it itself.
    """

    label: str
    n: int
    minimum: float | None
    p25: float | None
    median: float | None
    p75: float | None
    maximum: float | None
    mean: float | None

    @property
    def is_present(self) -> bool:
        return self.n > 0


def _quantile(ordered: Sequence[float], q: float) -> float:
    rank = q * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def describe(values: Sequence[float], *, label: str) -> Distribution:
    """Summarise a sample. Empty is a distribution with ``n=0``, never an error."""
    numbers = [float(value) for value in values]
    if not numbers:
        return Distribution(
            label=label, n=0, minimum=None, p25=None, median=None,
            p75=None, maximum=None, mean=None,
        )
    ordered = sorted(numbers)
    return Distribution(
        label=label,
        n=len(ordered),
        minimum=ordered[0],
        p25=_quantile(ordered, 0.25),
        median=_quantile(ordered, 0.5),
        p75=_quantile(ordered, 0.75),
        maximum=ordered[-1],
        mean=sum(ordered) / len(ordered),
    )


@dataclass(frozen=True, slots=True)
class GeometryRecord:
    """One trade's plan, result and after-the-fact measurements, joined.

    §1 of the brief's *GeometryRecord*. **Computed, never persisted**: every
    field is reconstructible from the plan and the trade, so storing it would
    duplicate facts the artifact already holds and create a second thing to keep
    in step.
    """

    plan: GeometryPlan
    trade: LabTrade
    outcome: GeometryOutcome

    @property
    def symbol(self) -> str:
        return self.trade.symbol

    @property
    def realized_r(self) -> Decimal | None:
        return self.trade.net_r

    @property
    def reached_target(self) -> bool:
        return self.trade.exit_reason is LabExitReason.TARGET

    @property
    def reached_stop(self) -> bool:
        return self.trade.exit_reason in (
            LabExitReason.STOP, LabExitReason.ENTRY_GAPPED_THROUGH_STOP
        )

    @property
    def is_winner(self) -> bool:
        return self.trade.verdict is TradeVerdict.WIN

    @property
    def is_loser(self) -> bool:
        return self.trade.verdict is TradeVerdict.LOSS

    @property
    def rr_bucket(self) -> str:
        """The planned R:R, bucketed on boundaries fixed before any result."""
        value = self.plan.planned_rr
        for edge, label in _RR_BUCKETS:
            if value < edge:
                return label
        return "rr>=3.0"

    @property
    def stop_atr_bucket(self) -> str:
        """The volatility-normalised stop distance, bucketed. Absent ATR is its own bucket."""
        value = self.plan.stop_atr_multiple
        if value is None:
            return "atr_unavailable"
        for edge, label in _ATR_BUCKETS:
            if value < edge:
                return label
        return "stop>=2.0atr"

    @property
    def stop_bps_bucket(self) -> str:
        value = self.plan.stop_bps
        for edge, label in _BPS_BUCKETS:
            if value < edge:
                return label
        return "stop>=500bp"


#: Bucket boundaries, fixed before any result was seen. They are round numbers
#: chosen against the *question* — 1.0 is where reward stops covering risk — and
#: never against an observed distribution, which would be a threshold chosen to
#: make a story.
_RR_BUCKETS: Final[tuple[tuple[float, str], ...]] = (
    (0.5, "rr<0.5"), (1.0, "rr_0.5-1.0"), (1.5, "rr_1.0-1.5"),
    (2.0, "rr_1.5-2.0"), (3.0, "rr_2.0-3.0"),
)
_ATR_BUCKETS: Final[tuple[tuple[float, str], ...]] = (
    (0.25, "stop<0.25atr"), (0.5, "stop_0.25-0.5atr"), (1.0, "stop_0.5-1.0atr"),
    (1.5, "stop_1.0-1.5atr"), (2.0, "stop_1.5-2.0atr"),
)
_BPS_BUCKETS: Final[tuple[tuple[float, str], ...]] = (
    (10.0, "stop<10bp"), (25.0, "stop_10-25bp"), (50.0, "stop_25-50bp"),
    (100.0, "stop_50-100bp"), (250.0, "stop_100-250bp"), (500.0, "stop_250-500bp"),
)


@dataclass(frozen=True, slots=True)
class Finding:
    """One question from §2, the number that answers it, and the reading.

    ``supported`` is tri-state on purpose. ``None`` means the sample could not
    answer the question, which is a different statement from "no" and must never
    be rendered as one.
    """

    question: str
    supported: bool | None
    evidence: str
    reading: str


@dataclass(frozen=True, slots=True)
class GeometryDiagnosis:
    """Everything §2 and §6 ask for, over one policy's records."""

    label: str
    records: tuple[GeometryRecord, ...]
    skips: tuple[GeometrySkip, ...]
    distributions: tuple[Distribution, ...]
    breakdowns: tuple[tuple[str, tuple[VariantMetrics, ...]], ...]
    reward_below_risk: Share
    target_exits_below_one_r: Share
    stops_inside_one_atr: Share
    mfe_exceeds_realized_by_one_r: Share
    stopped_then_reached_target: Share
    skip_reasons: tuple[tuple[str, int], ...]
    findings: tuple[Finding, ...]

    def distribution(self, label: str) -> Distribution:
        for item in self.distributions:
            if item.label == label:
                return item
        raise SwingLabError(
            f"no distribution named {label!r}; this diagnosis holds "
            f"{', '.join(item.label for item in self.distributions)}"
        )

    def breakdown(self, name: str) -> tuple[VariantMetrics, ...]:
        for label, cohorts in self.breakdowns:
            if label == name:
                return cohorts
        raise SwingLabError(
            f"no breakdown named {name!r}; this diagnosis holds "
            f"{', '.join(label for label, _ in self.breakdowns)}"
        )


def _share_by(
    records: Sequence[GeometryRecord],
    key: Callable[[GeometryRecord], str],
    predicate: Callable[[GeometryRecord], bool],
) -> tuple[tuple[str, Share], ...]:
    """Per-cohort share of ``predicate``, sorted by cohort label."""
    totals: dict[str, list[int]] = {}
    for record in records:
        cohort = totals.setdefault(key(record), [0, 0])
        cohort[1] += 1
        if predicate(record):
            cohort[0] += 1
    return tuple(
        (label, Share(numerator=hits, denominator=total))
        for label, (hits, total) in sorted(totals.items())
    )


def _concentration_finding(
    question: str,
    shares: Sequence[tuple[str, Share]],
    *,
    subject: str,
) -> Finding:
    """Whether a behaviour concentrates in one cohort, or is spread evenly.

    Only cohorts that cleared the sample floor can carry a rate, so a spread is
    judged over those alone and the rest are named as unmeasurable rather than
    folded in at zero.
    """
    measurable = [
        (label, share) for label, share in shares if share.fraction is not None
    ]
    if len(measurable) < 2:
        return Finding(
            question=question,
            supported=None,
            evidence=(
                f"{len(measurable)} of {len(shares)} cohorts cleared the "
                f"{SAMPLE_FLOOR}-trade floor"
            ),
            reading=(
                "Not answerable at this sample size. Splitting these trades by "
                f"{subject} leaves cohorts too small to carry a rate."
            ),
        )
    ranked = sorted(measurable, key=lambda item: item[1].fraction, reverse=True)
    highest, lowest = ranked[0], ranked[-1]
    spread = highest[1].fraction - lowest[1].fraction
    concentrated = spread >= Decimal("0.25")
    evidence = "; ".join(f"{label} {share.text}" for label, share in ranked)
    return Finding(
        question=question,
        supported=concentrated,
        evidence=evidence,
        reading=(
            f"Concentrated: {highest[0]} at {highest[1].fraction:.1%} against "
            f"{lowest[0]} at {lowest[1].fraction:.1%}, a spread of {spread:.1%}."
            if concentrated
            else (
                f"Spread rather than concentrated: every measurable {subject} "
                f"cohort sits within {spread:.1%} of the others."
            )
        ),
    )


def diagnose_geometry(
    records: Sequence[GeometryRecord],
    skips: Sequence[GeometrySkip],
    *,
    label: str,
) -> GeometryDiagnosis:
    """Measure one policy's geometry and answer §2's questions from the measurements.

    Pure: the same records always produce the same diagnosis. Every rate refuses
    itself below `SAMPLE_FLOOR`, and every finding that a small sample cannot
    support reports ``supported=None`` rather than a confident-looking guess.
    """
    if not isinstance(label, str) or not label.strip():
        raise SwingLabError("label must be a non-empty str")
    items = tuple(records)
    for record in items:
        if not isinstance(record, GeometryRecord):
            raise TypeError("every record must be a GeometryRecord")

    measurable = [r for r in items if r.realized_r is not None]
    winners = [r for r in measurable if r.is_winner]
    losers = [r for r in measurable if r.is_loser]
    target_exits = [r for r in measurable if r.reached_target]
    stopped = [r for r in items if r.trade.exit_reason is LabExitReason.STOP]

    distributions = (
        describe([r.plan.planned_rr for r in items], label="planned_rr"),
        describe(
            [float(r.realized_r) for r in measurable], label="realized_r"
        ),
        describe([float(r.realized_r) for r in winners], label="winner_r"),
        describe([float(r.realized_r) for r in losers], label="loser_r"),
        describe([r.plan.stop_bps for r in items], label="stop_bps"),
        describe([r.plan.target_bps for r in items], label="target_bps"),
        describe(
            [r.plan.stop_atr_multiple for r in items if r.plan.stop_atr_multiple is not None],
            label="stop_atr_multiple",
        ),
        describe(
            [
                r.plan.target_atr_multiple
                for r in items
                if r.plan.target_atr_multiple is not None
            ],
            label="target_atr_multiple",
        ),
        describe(
            [float(r.trade.mfe_r) for r in items if r.trade.mfe_r is not None],
            label="mfe_r",
        ),
        describe(
            [float(r.trade.mae_r) for r in items if r.trade.mae_r is not None],
            label="mae_r",
        ),
        describe([float(r.trade.bars_held) for r in measurable], label="bars_held"),
        describe(
            [r.plan.entry_position_in_range for r in items],
            label="entry_position_in_range",
        ),
    )

    trades: tuple[LabTrade, ...] = tuple(r.trade for r in items)
    by_record = {(r.trade.symbol, r.trade.setup_id, r.trade.signal_at): r for r in items}

    def record_key(getter: Callable[[GeometryRecord], str]) -> Callable[[LabTrade], str]:
        def key(trade: LabTrade) -> str:
            record = by_record.get((trade.symbol, trade.setup_id, trade.signal_at))
            return "unattributed" if record is None else getter(record)

        return key

    breakdowns = (
        ("symbol", lab_breakdown_by(trades, lambda t: t.symbol)),
        ("direction", lab_breakdown_by(trades, lambda t: t.direction.value)),
        (
            "context_regime",
            lab_breakdown_by(trades, lambda t: t.context_regime_structure),
        ),
        (
            "setup_structural_trend",
            lab_breakdown_by(trades, lambda t: t.setup_structural_trend),
        ),
        ("planned_rr_bucket", lab_breakdown_by(trades, record_key(lambda r: r.rr_bucket))),
        ("stop_bps_bucket", lab_breakdown_by(trades, record_key(lambda r: r.stop_bps_bucket))),
        (
            "stop_atr_bucket",
            lab_breakdown_by(trades, record_key(lambda r: r.stop_atr_bucket)),
        ),
        (
            "stop_source_interval",
            lab_breakdown_by(trades, record_key(lambda r: r.plan.stop.interval)),
        ),
        (
            "target_source_interval",
            lab_breakdown_by(trades, record_key(lambda r: r.plan.target.interval)),
        ),
    )

    reward_below_risk = Share(
        numerator=sum(1 for r in items if r.plan.reward_below_risk),
        denominator=len(items),
    )
    target_below_one_r = Share(
        numerator=sum(
            1 for r in target_exits if r.realized_r is not None and r.realized_r < 1
        ),
        denominator=len(target_exits),
    )
    with_atr = [r for r in items if r.plan.stop_atr_multiple is not None]
    stops_inside_atr = Share(
        numerator=sum(1 for r in with_atr if r.plan.stop_atr_multiple < 1.0),
        denominator=len(with_atr),
    )
    giveback = [r for r in items if r.outcome.unrealised_giveback_r is not None]
    mfe_exceeds = Share(
        numerator=sum(1 for r in giveback if r.outcome.gave_back_a_full_r),
        denominator=len(giveback),
    )
    continued = Share(
        numerator=sum(
            1 for r in stopped if r.outcome.target_reached_after_stop is True
        ),
        denominator=len(stopped),
    )

    skip_counts: dict[str, int] = {}
    for skip in skips:
        skip_counts[skip.reason.value] = skip_counts.get(skip.reason.value, 0) + 1

    findings = _findings(
        items=items,
        winners=winners,
        target_exits=target_exits,
        reward_below_risk=reward_below_risk,
        target_below_one_r=target_below_one_r,
        stops_inside_atr=stops_inside_atr,
        mfe_exceeds=mfe_exceeds,
        continued=continued,
    ) + (
        # The two §2 questions that are about WHERE a defect lives rather than
        # how common it is. Both are answered by the same concentration rule,
        # over different cohorts.
        _concentration_finding(
            "Does reward < risk concentrate in particular setup types?",
            _share_by(
                items,
                lambda record: record.trade.setup_structural_trend or "unattributed",
                lambda record: record.plan.reward_below_risk,
            ),
            subject="setup structural trend",
        ),
        _concentration_finding(
            "Does tight-stop behaviour concentrate in particular volatility regimes?",
            _share_by(
                [r for r in items if r.plan.stop_atr_multiple is not None],
                lambda record: (
                    record.plan.candidate.context_regime_volatility or "unattributed"
                ),
                lambda record: record.plan.stop_atr_multiple < 1.0,
            ),
            subject="context volatility regime",
        ),
        _concentration_finding(
            "Does reward < risk concentrate in particular symbols?",
            _share_by(
                items,
                lambda record: record.trade.symbol,
                lambda record: record.plan.reward_below_risk,
            ),
            subject="symbol",
        ),
    )

    return GeometryDiagnosis(
        label=label,
        records=items,
        skips=tuple(skips),
        distributions=distributions,
        breakdowns=breakdowns,
        reward_below_risk=reward_below_risk,
        target_exits_below_one_r=target_below_one_r,
        stops_inside_one_atr=stops_inside_atr,
        mfe_exceeds_realized_by_one_r=mfe_exceeds,
        stopped_then_reached_target=continued,
        skip_reasons=tuple(sorted(skip_counts.items())),
        findings=findings,
    )


def _supported(share: Share, threshold: Decimal) -> bool | None:
    value = share.fraction
    return None if value is None else value >= threshold


def _findings(
    *,
    items: Sequence[GeometryRecord],
    winners: Sequence[GeometryRecord],
    target_exits: Sequence[GeometryRecord],
    reward_below_risk: Share,
    target_below_one_r: Share,
    stops_inside_atr: Share,
    mfe_exceeds: Share,
    continued: Share,
) -> tuple[Finding, ...]:
    """§2's questions, each answered from one measurement and nothing else.

    The thresholds that turn a rate into a *yes* are round and pre-declared: a
    third for "concentrates", a half for "characteristic of the population". They
    are stated here rather than tuned, and every finding shows its rate so a
    reader who prefers a different threshold can apply it themselves.
    """
    winner_by_exit: dict[str, int] = {}
    for record in winners:
        reason = record.trade.exit_reason.value
        winner_by_exit[reason] = winner_by_exit.get(reason, 0) + 1
    winners_at_target = Share(
        numerator=winner_by_exit.get(LabExitReason.TARGET.value, 0),
        denominator=len(winners),
    )

    return (
        Finding(
            question="Are winners small because targets are close?",
            supported=_supported(target_below_one_r, Decimal("0.5")),
            evidence=(
                f"target-exit trades returning under +1R: {target_below_one_r.text}; "
                f"setups planning reward < risk: {reward_below_risk.text}"
            ),
            reading=(
                "A trade that reaches its target and still pays under 1R was "
                "planned that way: its target sat nearer than its stop. This is "
                "geometry, not execution — the trade did exactly what it set out "
                "to do."
            ),
        ),
        Finding(
            question="Are winners small because trades exit before target?",
            supported=(
                None
                if winners_at_target.fraction is None
                else winners_at_target.fraction < Decimal("0.5")
            ),
            evidence=(
                "winning trades by exit reason: "
                + ("; ".join(f"{k} {v}" for k, v in sorted(winner_by_exit.items())) or "none")
            ),
            reading=(
                "If most winners exit at their target, the target is the binding "
                "constraint. If most exit on the time stop, the evaluation window "
                "is — and that is a measurement policy rather than a finding "
                "about the strategy."
            ),
        ),
        Finding(
            question="Are stops too tight relative to ordinary market noise?",
            supported=_supported(stops_inside_atr, Decimal("0.5")),
            evidence=f"stops inside one ATR(14) of the entry: {stops_inside_atr.text}",
            reading=(
                "A stop closer than one average bar range is not protecting a "
                "thesis; an ordinary candle removes it. The level may still be "
                "structurally real — the two questions are separate."
            ),
        ),
        Finding(
            question="Are targets structurally valid but economically too close?",
            supported=_supported(reward_below_risk, Decimal("0.33")),
            evidence=f"setups whose real structural target pays under 1R: {reward_below_risk.text}",
            reading=(
                "Every target here is a level the structural engine produced, so "
                "validity is not in question. What is in question is whether a "
                "valid level that pays less than the risk is worth trading to."
            ),
        ),
        Finding(
            question="How often does MFE materially exceed realized R?",
            supported=_supported(mfe_exceeds, Decimal("0.33")),
            evidence=f"trades giving back at least a full R of open profit: {mfe_exceeds.text}",
            reading=(
                "A large gap between the best price seen and the price taken "
                "points at exit management rather than at entry or stop "
                "placement. It is the one diagnosis here that geometry alone "
                "cannot fix."
            ),
        ),
        Finding(
            question=(
                "How often does price stop out and then move toward the original "
                "thesis anyway?"
            ),
            supported=_supported(continued, Decimal("0.33")),
            evidence=(
                "stopped-out trades whose original target was reached later in "
                f"the same evaluation window: {continued.text}"
            ),
            reading=(
                "A stop that is removed by noise before the thesis plays out is "
                "the signature of a stop placed too close, not of a wrong thesis. "
                "Bounded by the trade's own evaluation window: 'eventually' is "
                "not a measurable claim."
            ),
        ),
    )
