"""How many, of what kind, and for how long — the counts and the durations.

Every figure here is either a `Tally` — a count over a stated population, which
is a fact at any `n` — or a duration statistic over the trades that actually
held exposure. No rate appears in this module. The rates live in `performance`,
where the sample floor applies to them.

**A count is never a rate wearing its clothes.** `Tally` carries its
denominator, so a surface renders *"4 of 12"* and cannot render *"4"* on its
own. The single most common way a statistics page misleads is a numerator
whose population moved.

**Durations are measured over trades that opened.** A cancelled activation has
no holding time and contributes nothing rather than a zero, which would drag
every average toward a number describing trades that never existed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from fmis.accounts import Book
from fmis.provenance import Absent
from fmis.snapshotting import TradeDirection
from fmis.statistics.models import (
    LifecyclePhase,
    SamplePolicy,
    StatSource,
    TradeResult,
    TradeStat,
)
from fmis.statistics.sampling import (
    Sample,
    Tally,
    collect_values,
    count_of,
    extremum_or_absent,
    mean_duration_or_absent,
    mean_or_absent,
    median_duration_or_absent,
    median_or_absent,
)

__all__ = ["GeneralStatistics", "general_statistics", "total_duration"]


@dataclass(frozen=True, slots=True)
class GeneralStatistics:
    """The shape of the corpus: what it holds, and how long its trades ran."""

    total: int
    winning: Tally
    losing: Tally
    scratch: Tally
    unresolved: Tally
    cancelled: Tally
    expired: Tally
    triggered: Tally
    pending: Tally
    open_trades: Tally
    closed: Tally
    ambiguous: Tally
    paper: Tally
    live: Tally
    by_direction: tuple[Tally, ...]
    by_source: tuple[Tally, ...]
    holding_time: Sample
    average_holding_time: Any | Absent
    median_holding_time: Any | Absent
    maximum_holding_time: Any | Absent
    minimum_holding_time: Any | Absent
    bars_held: Sample
    average_bars_held: Any | Absent
    median_bars_held: Any | Absent

    def to_payload(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "winning": self.winning.to_payload(),
            "losing": self.losing.to_payload(),
            "scratch": self.scratch.to_payload(),
            "unresolved": self.unresolved.to_payload(),
            "cancelled": self.cancelled.to_payload(),
            "expired": self.expired.to_payload(),
            "triggered": self.triggered.to_payload(),
            "pending": self.pending.to_payload(),
            "open": self.open_trades.to_payload(),
            "closed": self.closed.to_payload(),
            "ambiguous": self.ambiguous.to_payload(),
            "paper": self.paper.to_payload(),
            "live": self.live.to_payload(),
            "by_direction": [entry.to_payload() for entry in self.by_direction],
            "by_source": [entry.to_payload() for entry in self.by_source],
            "holding_time": self.holding_time.to_payload(),
            "bars_held": self.bars_held.to_payload(),
        }


def _phase_tally(trades: tuple[TradeStat, ...], phase: LifecyclePhase) -> Tally:
    return count_of(trades, lambda stat: stat.phase is phase, phase.value)


def _result_tally(trades: tuple[TradeStat, ...], result: TradeResult) -> Tally:
    return count_of(trades, lambda stat: stat.result is result, result.value)


def general_statistics(
    trades: tuple[TradeStat, ...], policy: SamplePolicy
) -> GeneralStatistics:
    """Every count and duration the milestone's general list names.

    `policy` is threaded through even though nothing here is floored, because
    the duration reductions share one signature with the floored ones and a
    second signature would be the seam where the floor is later forgotten.
    """
    if not isinstance(trades, tuple):
        raise TypeError("trades must be a tuple of TradeStat")
    for stat in trades:
        if not isinstance(stat, TradeStat):
            raise TypeError("every trade must be a TradeStat")
    if not isinstance(policy, SamplePolicy):
        raise TypeError("policy must be a SamplePolicy")

    holding = collect_values(trades, lambda stat: stat.holding_time, "holding time")
    bars = collect_values(trades, lambda stat: stat.bars_held, "bar count")
    bars_as_numbers = Sample(
        subject=bars.subject,
        values=tuple(_as_decimal(value) for value in bars.values),
        missing=bars.missing,
        reasons=bars.reasons,
    )
    return GeneralStatistics(
        total=len(trades),
        winning=_result_tally(trades, TradeResult.WIN),
        losing=_result_tally(trades, TradeResult.LOSS),
        scratch=_result_tally(trades, TradeResult.SCRATCH),
        unresolved=_result_tally(trades, TradeResult.UNRESOLVED),
        cancelled=_phase_tally(trades, LifecyclePhase.CANCELLED),
        expired=_phase_tally(trades, LifecyclePhase.EXPIRED),
        triggered=_phase_tally(trades, LifecyclePhase.TRIGGERED),
        pending=_phase_tally(trades, LifecyclePhase.PENDING),
        open_trades=_phase_tally(trades, LifecyclePhase.OPEN),
        closed=_phase_tally(trades, LifecyclePhase.CLOSED),
        ambiguous=_phase_tally(trades, LifecyclePhase.AMBIGUOUS),
        paper=count_of(trades, lambda stat: stat.is_paper, Book.PAPER.value),
        live=count_of(trades, lambda stat: not stat.is_paper, "non-paper books"),
        by_direction=tuple(
            count_of(
                trades,
                lambda stat, side=side: stat.direction is side,
                side.value,
            )
            for side in TradeDirection
            if side.is_directional
        ),
        by_source=tuple(
            count_of(
                trades,
                lambda stat, origin=origin: stat.source is origin,
                origin.value,
            )
            for origin in StatSource
        ),
        holding_time=holding,
        average_holding_time=mean_duration_or_absent(holding, policy),
        median_holding_time=median_duration_or_absent(holding, policy),
        maximum_holding_time=extremum_or_absent(holding, policy, largest=True),
        minimum_holding_time=extremum_or_absent(holding, policy, largest=False),
        bars_held=bars,
        average_bars_held=mean_or_absent(bars_as_numbers, policy),
        median_bars_held=median_or_absent(bars_as_numbers, policy),
    )


def _as_decimal(value: Any) -> Decimal:
    """A bar count is a whole number; averaging it needs the exact type.

    `Decimal` rather than `float` for the identical reason every other quotient
    in this repository is exact: an average bar count of `4.999999999999999`
    would be a rendering artefact of the arithmetic and not of the trades.
    """
    return Decimal(value)


def total_duration(sample: Sample) -> timedelta:
    """Every holding time added together — exposure, not calendar time.

    Two trades held simultaneously contribute twice, which is what *"how much
    time was I in a trade"* means for a per-trade statistic and is **not** what
    *"how much of the calendar was I exposed"* means. The second question needs
    an interval union this milestone does not build.
    """
    if not isinstance(sample, Sample):
        raise TypeError("sample must be a Sample")
    total = timedelta(0)
    for value in sample.values:
        total = total + value
    return total
