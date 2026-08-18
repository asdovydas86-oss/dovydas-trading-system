"""Drawdown: how far below its own high-water mark the curve has been.

Computed on the `EquityCurve`'s **cumulative** series, which is baseline-free —
a starting equity shifts every point equally and cannot move where the peak
sits, so the shape of a drawdown is identical with or without one and only its
percentage form needs a baseline.

**A drawdown period runs from a peak to the recovery of that peak**, and a
period that has not recovered is `ongoing`. Reporting an unrecovered decline as
a finished one is the single most flattering error available here: it turns *"I
am still down and have been for four months"* into a completed episode with a
duration.

**"Longest" means the longest by duration, and the deepest is a separate
figure.** They are routinely different periods and a system that conflates them
answers *"how bad was it"* when the owner asked *"how long did I have to sit
through it"*.

**Average drawdown averages the periods, not the points.** Averaging every
point on the curve would divide by how often trades happened to close, so a
quiet stretch inside one decline would make the same decline read as shallower.
The population is the set of drawdown periods, and it is stated.

**The percentage denominator is the equity at the peak, not the starting
equity.** A 500-unit decline from a doubled account is a smaller drawdown than
the same decline from the opening balance, and dividing both by the opening
balance would report them as equal. Every percentage here therefore needs the
baseline `ST-4` says is absent by default, and is `Absent` without it.

**A decline that begins before the curve ever rose has no recorded peak
instant.** The high-water mark it fell from is the account's opening level, and
this system records neither that level's value nor when it was reached — so the
first closing trade's instant stands in, and such a period's *duration* is
therefore measured from the first close rather than from an account opening
that is not recorded. `ST-4`, extended to time.

**Zero is a real answer here.** A curve at its high-water mark has a current
drawdown of exactly zero, which is a measurement rather than a missing value —
the one place in this package where a zero is not standing in for an absence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fmis.money import AssetCode, Money, canonical_decimal_text
from fmis.provenance import Absent
from fmis.records import require_int, require_utc
from fmis.statistics.equity import EquityCurve, as_percentage
from fmis.statistics.models import SamplePolicy, StatisticsRefusedError
from fmis.statistics.sampling import Sample, extremum_or_absent, mean_or_absent

__all__ = [
    "DrawdownPeriod",
    "DrawdownCurve",
    "drawdown_curve",
    "DRAWDOWN_BASIS",
]

#: Printed on every page that shows a drawdown figure.
DRAWDOWN_BASIS = (
    "Measured on realized closed-trade equity, from each high-water mark to the "
    "recovery of that mark. A period that has not recovered is reported as "
    "ongoing rather than as a finished episode."
)


@dataclass(frozen=True, slots=True)
class DrawdownPeriod:
    """One decline from a peak, and whether it ever came back."""

    peak_at: datetime
    trough_at: datetime
    recovered_at: datetime | Absent
    peak: Money
    trough: Money
    depth: Money
    depth_percent: Decimal | Absent
    trades: int

    def __post_init__(self) -> None:
        for name in ("peak_at", "trough_at"):
            object.__setattr__(self, name, require_utc(getattr(self, name), name))
        if not isinstance(self.recovered_at, Absent):
            object.__setattr__(
                self, "recovered_at", require_utc(self.recovered_at, "recovered_at")
            )
            if self.recovered_at < self.trough_at:
                raise StatisticsRefusedError(
                    "a drawdown cannot recover before it reaches its trough"
                )
        if self.trough_at < self.peak_at:
            raise StatisticsRefusedError(
                "a drawdown's trough cannot precede the peak it fell from"
            )
        for name in ("peak", "trough", "depth"):
            if not isinstance(getattr(self, name), Money):
                raise TypeError(f"{name} must be a Money")
        if self.depth.amount < 0:
            raise StatisticsRefusedError(
                "a drawdown depth is carried as a positive magnitude; a signed one "
                "would make the deepest decline the smallest number"
            )
        if not isinstance(self.depth_percent, (Decimal, Absent)):
            raise TypeError("depth_percent must be a Decimal or Absent")
        require_int(self.trades, "trades", minimum=0)

    @property
    def is_ongoing(self) -> bool:
        return isinstance(self.recovered_at, Absent)

    @property
    def duration(self) -> timedelta:
        """Peak to recovery, or peak to the trough while it is still running.

        The second is deliberately **not** peak-to-now: this package reads no
        clock, and a duration that grew every time the page was rendered would
        be a figure about when the owner looked rather than about the decline.
        """
        if isinstance(self.recovered_at, Absent):
            return self.trough_at - self.peak_at
        return self.recovered_at - self.peak_at

    def to_payload(self) -> dict[str, Any]:
        return {
            "peak_at": self.peak_at.isoformat(),
            "trough_at": self.trough_at.isoformat(),
            "recovered_at": (
                None if isinstance(self.recovered_at, Absent) else self.recovered_at.isoformat()
            ),
            "peak": self.peak.to_payload(),
            "trough": self.trough.to_payload(),
            "depth": self.depth.to_payload(),
            "depth_percent": (
                None
                if isinstance(self.depth_percent, Absent)
                else canonical_decimal_text(self.depth_percent)
            ),
            "trades": self.trades,
            "ongoing": self.is_ongoing,
            "duration_seconds": self.duration.total_seconds(),
        }


@dataclass(frozen=True, slots=True)
class DrawdownCurve:
    """Every decline the curve made, plus the four summary figures."""

    quote_asset: AssetCode
    periods: tuple[DrawdownPeriod, ...]
    current: Money
    current_percent: Decimal | Absent
    maximum: Money | Absent
    maximum_percent: Decimal | Absent
    average: Money | Absent
    longest: DrawdownPeriod | Absent
    deepest: DrawdownPeriod | Absent
    recoveries: tuple[DrawdownPeriod, ...]
    basis: str = DRAWDOWN_BASIS

    @property
    def in_drawdown(self) -> bool:
        return self.current.amount > 0

    @property
    def ongoing(self) -> DrawdownPeriod | Absent:
        for period in self.periods:
            if period.is_ongoing:
                return period
        return Absent("the curve is at its high-water mark")

    def to_payload(self) -> dict[str, Any]:
        return {
            "quote_asset": self.quote_asset.code,
            "periods": [period.to_payload() for period in self.periods],
            "current": self.current.to_payload(),
            "current_percent": _number(self.current_percent),
            "maximum": _money(self.maximum),
            "maximum_percent": _number(self.maximum_percent),
            "average": _money(self.average),
            "longest": None if isinstance(self.longest, Absent) else self.longest.to_payload(),
            "deepest": None if isinstance(self.deepest, Absent) else self.deepest.to_payload(),
            "recoveries": [period.to_payload() for period in self.recoveries],
        }


def drawdown_curve(curve: EquityCurve, policy: SamplePolicy) -> DrawdownCurve:
    """Walk the equity curve once, recording every decline from a high-water mark.

    One pass, and the state is three values: the running peak, the trough since
    that peak, and how many trades have closed inside the current decline. A
    period ends when the curve reaches the peak again — **at or above**, because
    a curve that returns to exactly its old high has recovered, and requiring it
    to exceed the high would leave every flat recovery permanently ongoing.
    """
    if not isinstance(curve, EquityCurve):
        raise TypeError(f"curve must be an EquityCurve, got {type(curve).__name__}")
    if not isinstance(policy, SamplePolicy):
        raise TypeError("policy must be a SamplePolicy")

    asset = curve.quote_asset
    baseline = curve.starting_equity
    zero = Money.zero(asset)

    periods: list[DrawdownPeriod] = []
    peak = zero
    peak_at: datetime | None = None
    trough = zero
    trough_at: datetime | None = None
    trades_in_decline = 0
    in_decline = False

    for point in curve.points:
        value = point.cumulative
        if in_decline:
            trades_in_decline += 1
            if value < trough:
                trough = value
                trough_at = point.at
            if value >= peak:
                periods.append(
                    _period(
                        peak_at=peak_at,
                        trough_at=trough_at,
                        recovered_at=point.at,
                        peak=peak,
                        trough=trough,
                        baseline=baseline,
                        trades=trades_in_decline,
                    )
                )
                in_decline = False
                trades_in_decline = 0
                peak = value
                peak_at = point.at
            continue
        if value >= peak:
            peak = value
            peak_at = point.at
            continue
        # The curve has just turned down from `peak`, which was set at
        # `peak_at`. A decline that begins before any point rose above the
        # starting level has no recorded peak instant, so the first point of
        # the decline stands in for it — the alternative is discarding the
        # decline entirely, which would hide the drawdown a losing opening run
        # produces.
        in_decline = True
        trades_in_decline = 1
        trough = value
        trough_at = point.at
        if peak_at is None:
            peak_at = point.at

    if in_decline:
        periods.append(
            _period(
                peak_at=peak_at,
                trough_at=trough_at,
                recovered_at=Absent("this decline has not recovered its high-water mark"),
                peak=peak,
                trough=trough,
                baseline=baseline,
                trades=trades_in_decline,
            )
        )

    current = _depth(peak, curve.realized) if curve.points else zero
    depths = Sample(
        subject="drawdown depth",
        values=tuple(period.depth.amount for period in periods),
        missing=0,
    )
    durations = Sample(
        subject="drawdown duration",
        values=tuple(period.duration for period in periods),
        missing=0,
    )
    average_amount = mean_or_absent(depths, policy)
    average = (
        average_amount
        if isinstance(average_amount, Absent)
        else Money(average_amount, asset)
    )
    deepest = _pick(periods, depths, policy, key=lambda period: period.depth.amount)

    return DrawdownCurve(
        quote_asset=asset,
        periods=tuple(periods),
        current=current,
        current_percent=as_percentage(current, _equity_at(peak, baseline)),
        # The deepest period supplies **both** halves of the maximum, so the
        # money figure and the percentage describe one episode. Taking the
        # largest percentage separately can select a different period — an early
        # small decline off a small account — and a page showing one episode's
        # depth beside another's percentage reads as a single fact.
        maximum=deepest if isinstance(deepest, Absent) else deepest.depth,
        maximum_percent=deepest if isinstance(deepest, Absent) else deepest.depth_percent,
        average=average,
        longest=_pick(periods, durations, policy, key=lambda period: period.duration),
        deepest=deepest,
        recoveries=tuple(period for period in periods if not period.is_ongoing),
    )


def _period(
    *,
    peak_at: datetime | None,
    trough_at: datetime | None,
    recovered_at: datetime | Absent,
    peak: Money,
    trough: Money,
    baseline: Money | Absent,
    trades: int,
) -> DrawdownPeriod:
    if peak_at is None or trough_at is None:  # pragma: no cover - unreachable
        raise StatisticsRefusedError(
            "a drawdown period needs both the instant it began and the instant it "
            "bottomed"
        )
    depth = _depth(peak, trough)
    return DrawdownPeriod(
        peak_at=peak_at,
        trough_at=trough_at,
        recovered_at=recovered_at,
        peak=peak,
        trough=trough,
        depth=depth,
        depth_percent=as_percentage(depth, _equity_at(peak, baseline)),
        trades=trades,
    )


def _equity_at(cumulative: Money, baseline: Money | Absent) -> Money | Absent:
    """The account's value when the curve stood at `cumulative`.

    The denominator every drawdown percentage divides by. `Absent` without a
    baseline, because a percentage of an unrecorded opening balance is exactly
    the invented number this package exists to refuse.
    """
    if isinstance(baseline, Absent):
        return baseline
    return baseline + cumulative


def _depth(peak: Money, value: Money) -> Money:
    """Peak minus value, floored at zero — a magnitude, never a signed distance."""
    fallen = peak - value
    if fallen.amount < 0:
        return Money.zero(peak.asset)
    return fallen


def _pick(
    periods: list[DrawdownPeriod],
    sample: Sample,
    policy: SamplePolicy,
    *,
    key: Any,
) -> DrawdownPeriod | Absent:
    """The period whose measure is largest — or the absence naming an empty set.

    The extremum goes through `extremum_or_absent` rather than a bare `max` so
    that an empty population produces the package's one absence shape with its
    `sample_size`, instead of a `ValueError` a caller would have to translate.

    Two periods tying on the measure resolve to the **earlier** one, because the
    scan is in curve order and the first match wins. Stable rather than
    arbitrary, so two runs over one store agree.
    """
    chosen = extremum_or_absent(sample, policy, largest=True)
    if isinstance(chosen, Absent):
        return chosen
    for period in periods:
        if key(period) == chosen:
            return period
    raise StatisticsRefusedError(  # pragma: no cover - the sample comes from periods
        "the extremum of a sample drawn from these periods is not among them"
    )


def _money(value: Money | Absent) -> dict[str, Any] | None:
    return None if isinstance(value, Absent) else value.to_payload()


def _number(value: Decimal | Absent) -> str | None:
    return None if isinstance(value, Absent) else canonical_decimal_text(value)
