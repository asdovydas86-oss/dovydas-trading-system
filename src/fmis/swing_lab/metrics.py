"""Aggregating trades into figures, with the sample size welded to every one.

**Every rate and every average carries its `n`.** Not as a courtesy — as a type
invariant. `LabMeasure` cannot be constructed without one, so there is no way to
render an expectancy in this repository without rendering the number of trades
it came from, and no way for a 3-trade cohort to appear beside a 300-trade one
looking equally solid.

**Below the floor, a figure is absent rather than small.** `SAMPLE_FLOOR`
follows `fmis.statistics.sampling`'s existing discipline: a win rate over four
trades is not a weak estimate, it is not an estimate. Such cohorts report
`value=None` with the count still visible, and a reader sees "not enough trades"
instead of a precise-looking lie.

**Ambiguous trades are excluded from expectancy and counted beside it.** They
have no R by construction (`fmis.swing_lab.trades` refuses to guess an intrabar
path), and dropping them silently would let a variant that produces many
unresolvable trades look identical to one that produces none.

**Drawdown is measured on the R equity curve in trade order**, peak-to-trough,
where the peak is the running maximum *including the current point*. Using the
prior peak instead is the classic off-by-one that makes every drawdown one trade
too shallow.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Final

from fmis.swing_lab.models import (
    LabExitReason,
    LabTrade,
    LabVerdict,
    SwingLabError,
    TradeVerdict,
)
from fmis.swing_setup.models import Direction

__all__ = [
    "SAMPLE_FLOOR",
    "LabMeasure",
    "LabEquityPoint",
    "LabDrawdownReading",
    "VariantMetrics",
    "compute_lab_metrics",
    "lab_breakdown_by",
    "classify",
]

#: The fewest measurable trades a rate or an average may be computed from.
#: Deliberately the same number `fmis.statistics.sampling` already uses, imported
#: in spirit rather than in code because that package's floor governs the
#: owner's *real* trades and this one governs simulated ones — two different
#: populations that happen to warrant the same threshold.
SAMPLE_FLOOR: Final[int] = 20


@dataclass(frozen=True, slots=True)
class LabMeasure:
    """One figure and the sample it rests on. Neither is optional.

    ``value`` is ``None`` when ``n`` is below `SAMPLE_FLOOR` or when the figure
    is undefined for another stated reason (no losses, so no profit factor).
    ``reason`` then says which, so a blank cell on a page is never ambiguous
    between "too few" and "not applicable".
    """

    value: Decimal | None
    n: int
    reason: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.n, bool) or not isinstance(self.n, int) or self.n < 0:
            raise SwingLabError("n must be a non-negative int")
        if self.value is not None and self.reason is not None:
            raise SwingLabError(
                "a LabMeasure states a value or a reason for its absence, never both"
            )
        if self.value is None and self.reason is None:
            raise SwingLabError("an absent LabMeasure must carry a reason")

    @property
    def is_present(self) -> bool:
        return self.value is not None


def _below_floor(n: int) -> LabMeasure:
    return LabMeasure(
        value=None,
        n=n,
        reason=f"{n} measurable trade(s) is below the {SAMPLE_FLOOR}-trade floor",
    )


@dataclass(frozen=True, slots=True)
class LabEquityPoint:
    """One point on the cumulative-R curve, in trade order."""

    index: int
    at: datetime
    cumulative_r: Decimal
    drawdown_r: Decimal


@dataclass(frozen=True, slots=True)
class LabDrawdownReading:
    """The worst peak-to-trough decline on the R equity curve, and how long it lasted."""

    max_drawdown_r: Decimal
    peak_index: int | None
    trough_index: int | None
    peak_at: datetime | None
    trough_at: datetime | None
    duration: timedelta | None
    recovered: bool


@dataclass(frozen=True, slots=True)
class VariantMetrics:
    """Every figure the milestone brief asks for, for one variant or one cohort."""

    label: str
    trades: int
    measurable_trades: int
    ambiguous_trades: int
    unentered_trades: int
    wins: int
    losses: int
    scratches: int
    win_rate: LabMeasure
    expectancy_r: LabMeasure
    median_r: LabMeasure
    profit_factor: LabMeasure
    average_win_r: LabMeasure
    average_loss_r: LabMeasure
    largest_win_r: Decimal | None
    largest_loss_r: Decimal | None
    total_r: Decimal
    max_drawdown: LabDrawdownReading
    average_mfe_r: LabMeasure
    average_mae_r: LabMeasure
    average_bars_held: LabMeasure
    equity_curve: tuple[LabEquityPoint, ...]
    exit_reasons: tuple[tuple[str, int], ...]

    @property
    def has_reportable_edge_figure(self) -> bool:
        return self.expectancy_r.is_present


def _median(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    if count % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _equity(trades: Sequence[LabTrade]) -> tuple[tuple[LabEquityPoint, ...], LabDrawdownReading]:
    """The cumulative-R curve and its worst decline, in one pass.

    Trades are consumed in the order given — which callers order by exit
    instant, because an equity curve ordered by *signal* would let a fast trade
    opened later be credited before a slow one opened earlier.
    """
    points: list[LabEquityPoint] = []
    cumulative = Decimal("0")
    peak = Decimal("0")
    peak_index: int | None = None
    peak_at: datetime | None = None
    worst = Decimal("0")
    worst_peak_index: int | None = None
    worst_peak_at: datetime | None = None
    worst_trough_index: int | None = None
    worst_trough_at: datetime | None = None
    for position, trade in enumerate(trades):
        if trade.net_r is None:  # pragma: no cover - callers filter first
            continue
        cumulative += trade.net_r
        moment = trade.exit_at or trade.signal_at
        # The running peak INCLUDES this point: a new high is a peak, and a
        # decline is measured from it and not from the previous one.
        if cumulative >= peak:
            peak = cumulative
            peak_index = position
            peak_at = moment
        decline = cumulative - peak
        if decline < worst:
            worst = decline
            worst_peak_index, worst_peak_at = peak_index, peak_at
            worst_trough_index, worst_trough_at = position, moment
        points.append(
            LabEquityPoint(
                index=position, at=moment, cumulative_r=cumulative, drawdown_r=decline
            )
        )
    recovered = False
    if worst_trough_index is not None:
        recovered = any(
            point.drawdown_r == 0
            for point in points
            if point.index > worst_trough_index
        )
    duration = (
        worst_trough_at - worst_peak_at
        if worst_peak_at is not None and worst_trough_at is not None
        else None
    )
    return tuple(points), LabDrawdownReading(
        max_drawdown_r=-worst,
        peak_index=worst_peak_index,
        trough_index=worst_trough_index,
        peak_at=worst_peak_at,
        trough_at=worst_trough_at,
        duration=duration,
        recovered=recovered,
    )


def compute_lab_metrics(trades: Sequence[LabTrade], *, label: str) -> VariantMetrics:
    """Fold a trade list into every reported figure. Pure and order-stable.

    Trades are sorted by exit instant before the equity curve is built, so a
    caller passing them in signal order and a caller passing them in symbol
    order produce the identical curve and the identical drawdown.
    """
    if not isinstance(label, str) or not label.strip():
        raise SwingLabError("label must be a non-empty str")
    ordered = tuple(trades)
    for trade in ordered:
        if not isinstance(trade, LabTrade):
            raise TypeError("every trade must be a LabTrade")

    measurable = sorted(
        (trade for trade in ordered if trade.net_r is not None),
        key=lambda trade: (
            trade.exit_at or trade.signal_at,
            trade.symbol,
            trade.setup_id,
        ),
    )
    ambiguous = sum(
        1 for trade in ordered if trade.exit_reason is LabExitReason.AMBIGUOUS_SAME_BAR
    )
    unentered = sum(
        1 for trade in ordered if trade.exit_reason is LabExitReason.NO_ENTRY_BAR
    )
    n = len(measurable)
    returns = [trade.net_r for trade in measurable]
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    scratches = n - len(wins) - len(losses)

    enough = n >= SAMPLE_FLOOR
    win_rate = (
        LabMeasure(value=Decimal(len(wins)) / Decimal(n), n=n) if enough and n else _below_floor(n)
    )
    expectancy = (
        LabMeasure(value=sum(returns, Decimal("0")) / Decimal(n), n=n)
        if enough and n
        else _below_floor(n)
    )
    median = LabMeasure(value=_median(returns), n=n) if enough and n else _below_floor(n)

    gross_profit = sum(wins, Decimal("0"))
    gross_loss = -sum(losses, Decimal("0"))
    if not enough:
        profit_factor = _below_floor(n)
    elif gross_loss == 0:
        profit_factor = LabMeasure(
            value=None,
            n=n,
            reason="no losing trade, so a profit factor has no denominator",
        )
    else:
        profit_factor = LabMeasure(value=gross_profit / gross_loss, n=n)

    average_win = (
        LabMeasure(value=gross_profit / Decimal(len(wins)), n=len(wins))
        if len(wins) >= SAMPLE_FLOOR
        else _below_floor(len(wins))
    )
    average_loss = (
        LabMeasure(value=-gross_loss / Decimal(len(losses)), n=len(losses))
        if len(losses) >= SAMPLE_FLOOR
        else _below_floor(len(losses))
    )

    excursion_trades = [
        trade for trade in ordered if trade.mfe_r is not None and trade.mae_r is not None
    ]
    mfe = (
        LabMeasure(
            value=sum((t.mfe_r for t in excursion_trades), Decimal("0"))
            / Decimal(len(excursion_trades)),
            n=len(excursion_trades),
        )
        if len(excursion_trades) >= SAMPLE_FLOOR
        else _below_floor(len(excursion_trades))
    )
    mae = (
        LabMeasure(
            value=sum((t.mae_r for t in excursion_trades), Decimal("0"))
            / Decimal(len(excursion_trades)),
            n=len(excursion_trades),
        )
        if len(excursion_trades) >= SAMPLE_FLOOR
        else _below_floor(len(excursion_trades))
    )
    bars = (
        LabMeasure(
            value=Decimal(sum(t.bars_held for t in measurable)) / Decimal(n), n=n
        )
        if enough and n
        else _below_floor(n)
    )

    curve, drawdown = _equity(measurable)
    reasons: dict[str, int] = {}
    for trade in ordered:
        reasons[trade.exit_reason.value] = reasons.get(trade.exit_reason.value, 0) + 1

    return VariantMetrics(
        label=label,
        trades=len(ordered),
        measurable_trades=n,
        ambiguous_trades=ambiguous,
        unentered_trades=unentered,
        wins=len(wins),
        losses=len(losses),
        scratches=scratches,
        win_rate=win_rate,
        expectancy_r=expectancy,
        median_r=median,
        profit_factor=profit_factor,
        average_win_r=average_win,
        average_loss_r=average_loss,
        largest_win_r=max(wins) if wins else None,
        largest_loss_r=min(losses) if losses else None,
        total_r=sum(returns, Decimal("0")),
        max_drawdown=drawdown,
        average_mfe_r=mfe,
        average_mae_r=mae,
        average_bars_held=bars,
        equity_curve=curve,
        exit_reasons=tuple(sorted(reasons.items())),
    )


def lab_breakdown_by(
    trades: Sequence[LabTrade],
    key: Callable[[LabTrade], str | None],
    *,
    prefix: str = "",
) -> tuple[VariantMetrics, ...]:
    """Split trades into cohorts and measure each. Cohorts are sorted by label.

    A trade whose key is ``None`` is placed in an explicit ``"unattributed"``
    cohort rather than dropped, so the cohort counts always add back to the
    whole and a breakdown can never quietly lose trades.
    """
    cohorts: dict[str, list[LabTrade]] = {}
    for trade in trades:
        label = key(trade)
        cohorts.setdefault("unattributed" if label is None else label, []).append(trade)
    return tuple(
        compute_lab_metrics(members, label=f"{prefix}{label}")
        for label, members in sorted(cohorts.items())
    )


def classify(metrics: VariantMetrics) -> LabVerdict:
    """The verdict one variant's measured result supports. Pure and total.

    **Deterministic and reconstructable**: the only input is the measured
    result, so anyone holding the artifact can recompute this and check it
    against what a report claimed. No judgement, no weighting of several
    criteria into a hidden score, and no threshold that could be shopped.

    The rule, in full:

    * an expectancy that could not be stated — too few measurable trades for
      `SAMPLE_FLOOR` — is `INCONCLUSIVE`, because nothing was established;
    * an expectancy of zero or less is `REJECTED`;
    * a positive expectancy is `CANDIDATE_FOR_FORWARD_TEST`, which means *worth
      testing forward* and nothing stronger.

    Note what is deliberately absent. A variant is **never** promoted on profit
    factor, win rate, drawdown or total R, and never on a combination of them.
    One criterion decides, it is the one that answers "did this make money per
    trade", and a reader can see it beside the verdict.
    """
    if not isinstance(metrics, VariantMetrics):
        raise TypeError(
            f"metrics must be a VariantMetrics, got {type(metrics).__name__}"
        )
    expectancy = metrics.expectancy_r.value
    if expectancy is None:
        return LabVerdict.INCONCLUSIVE
    if expectancy > 0:
        return LabVerdict.CANDIDATE_FOR_FORWARD_TEST
    return LabVerdict.REJECTED
