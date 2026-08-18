"""The equity curve: one step per closed trade, and nothing between them.

**No interpolation, and the refusal is the design.** A curve drawn daily between
two closed trades would be inventing the account's value on days no measurement
was taken — and to draw it truthfully would need a mark for every open position
on every one of those days, which `ST-3` records this system does not keep. So
the curve moves only when a trade closes, and between closes it is flat because
nothing was measured, not because nothing happened.

**Open trades are tracked separately and never fold into the curve.** An open
trade's contribution needs a mark, is unrealized, and reverses. Adding it would
make yesterday's curve change today, which is the property that makes a curve
untrustworthy.

**The baseline is honest about being missing.** The owner's opening capital is
recorded nowhere in this system. Without a stated starting equity, this is a
**cumulative realized profit-and-loss curve** — every shape statement about it
holds, and every percentage statement does not, so percentages are `Absent` and
say why. With one supplied, it is an equity curve and the drawdown figures gain
their percentage form.

**One asset per curve.** `ST-5`: no rate in this system crosses two quote
assets, so a store settled in two produces two curves rather than one wrong one.

**Replay is truncation, not recomputation.** `as_of` drops every point after an
instant, which is correct precisely because each point is a fact frozen when a
trade closed rather than a value re-derived from today's prices. `AP` §20.7's
point-in-time rule, satisfied by the shape of the data rather than by a filter
somebody has to remember to apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from fmis.money import AssetCode, Money
from fmis.provenance import Absent
from fmis.records import require_text, require_utc
from fmis.statistics.models import StatisticsRefusedError, TradeStat

__all__ = [
    "EquityPoint",
    "EquityCurve",
    "equity_curve",
    "as_percentage",
    "EQUITY_BASIS",
]

#: Printed on every page that shows the curve.
EQUITY_BASIS = (
    "Realized profit and loss, one step per closed trade. Nothing is "
    "interpolated between closes, open positions are excluded, and no "
    "mark-to-market value is included — this system retains no mark history to "
    "reconstruct one from."
)


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """One closed trade's effect on the curve, and where the curve then stood."""

    at: datetime
    trade_ref: str
    delta: Money
    cumulative: Money
    equity: Money | Absent

    def __post_init__(self) -> None:
        object.__setattr__(self, "at", require_utc(self.at, "at"))
        object.__setattr__(self, "trade_ref", require_text(self.trade_ref, "trade_ref"))
        for name in ("delta", "cumulative"):
            if not isinstance(getattr(self, name), Money):
                raise TypeError(f"{name} must be a Money")
        if not isinstance(self.equity, (Money, Absent)):
            raise TypeError("equity must be a Money or Absent")
        if self.delta.asset != self.cumulative.asset:
            raise StatisticsRefusedError(
                f"a step in {self.delta.asset.code} cannot move a curve in "
                f"{self.cumulative.asset.code}"
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "at": self.at.isoformat(),
            "trade_ref": self.trade_ref,
            "delta": self.delta.to_payload(),
            "cumulative": self.cumulative.to_payload(),
            "equity": None if isinstance(self.equity, Absent) else self.equity.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class EquityCurve:
    """Every closed trade's step, oldest first, plus what was left out and why."""

    quote_asset: AssetCode
    points: tuple[EquityPoint, ...]
    starting_equity: Money | Absent
    excluded: tuple[str, ...]
    open_trades: int
    basis: str = EQUITY_BASIS

    def __post_init__(self) -> None:
        if not isinstance(self.quote_asset, AssetCode):
            raise TypeError("quote_asset must be an AssetCode")
        if not isinstance(self.points, tuple):
            raise TypeError("points must be a tuple of EquityPoint")
        previous: datetime | None = None
        for point in self.points:
            if not isinstance(point, EquityPoint):
                raise TypeError("every point must be an EquityPoint")
            if previous is not None and point.at < previous:
                raise StatisticsRefusedError(
                    "equity points must be ordered oldest first; an out-of-order "
                    "curve produces a drawdown that never happened"
                )
            previous = point.at
        if not isinstance(self.starting_equity, (Money, Absent)):
            raise TypeError("starting_equity must be a Money or Absent")
        if not isinstance(self.excluded, tuple):
            raise TypeError("excluded must be a tuple of str")
        for reason in self.excluded:
            require_text(reason, "excluded reason")

    @property
    def is_empty(self) -> bool:
        return not self.points

    @property
    def realized(self) -> Money:
        """Where cumulative realized profit and loss stands. Zero is a real answer
        here: no closed trade genuinely means no realized profit or loss."""
        if not self.points:
            return Money.zero(self.quote_asset)
        return self.points[-1].cumulative

    @property
    def current_equity(self) -> Money | Absent:
        """The account's realized value, or the absence naming the missing baseline."""
        if isinstance(self.starting_equity, Absent):
            return self.starting_equity
        return self.starting_equity + self.realized

    @property
    def peak_equity(self) -> Money:
        """The highest the curve reached, on whichever baseline it has.

        Peaks are computed on the *cumulative* series, which is baseline-free:
        adding a constant starting equity moves every point equally and cannot
        move where the peak is. So a drawdown is the same shape with or without
        a baseline, and only its percentage form needs one.
        """
        best = Money.zero(self.quote_asset)
        for point in self.points:
            if point.cumulative > best:
                best = point.cumulative
        return best

    def as_of(self, moment: datetime) -> EquityCurve:
        """The curve as it stood at a past instant — `AP` §20.7's replay.

        Truncation rather than recomputation. Every point is a fact frozen when
        a trade closed, so dropping the later ones gives exactly the curve that
        existed then; re-deriving would answer today's question with today's
        data and call it history.
        """
        cut = require_utc(moment, "moment")
        kept = tuple(point for point in self.points if point.at <= cut)
        dropped = len(self.points) - len(kept)
        excluded = self.excluded
        if dropped:
            excluded = excluded + (
                f"{dropped} trade(s) closed after {cut.isoformat()} and are not "
                "part of this replay",
            )
        return EquityCurve(
            quote_asset=self.quote_asset,
            points=kept,
            starting_equity=self.starting_equity,
            excluded=excluded,
            open_trades=self.open_trades,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "quote_asset": self.quote_asset.code,
            "points": [point.to_payload() for point in self.points],
            "starting_equity": (
                None
                if isinstance(self.starting_equity, Absent)
                else self.starting_equity.to_payload()
            ),
            "realized": self.realized.to_payload(),
            "excluded": list(self.excluded),
            "open_trades": self.open_trades,
        }


def _sort_key(stat: TradeStat) -> tuple[datetime, str]:
    """Close time, then reference — a total order over trades that tie.

    Two trades closing in the same instant would otherwise order by whatever the
    store happened to return, and the curve's intermediate points — and
    therefore its peak, and therefore its drawdown — would differ between two
    runs over identical data.
    """
    closed = stat.closed_at
    if isinstance(closed, Absent):  # pragma: no cover - filtered before sorting
        raise StatisticsRefusedError("a curve point needs a close instant")
    return (closed, stat.trade_ref)


def equity_curve(
    trades: tuple[TradeStat, ...],
    *,
    quote_asset: AssetCode,
    starting_equity: Money | Absent,
) -> EquityCurve:
    """Build the curve from every closed trade whose result is stateable.

    A closed trade whose profit and loss cannot be stated is **excluded and
    named**, never treated as a zero step: a zero step would draw a flat segment
    where the truth is an unmeasured one, and the drawdown computed over it
    would be a number about a curve that does not exist.
    """
    if not isinstance(trades, tuple):
        raise TypeError("trades must be a tuple of TradeStat")
    for stat in trades:
        if not isinstance(stat, TradeStat):
            raise TypeError("every trade must be a TradeStat")
    if not isinstance(quote_asset, AssetCode):
        raise TypeError("quote_asset must be an AssetCode")
    if not isinstance(starting_equity, (Money, Absent)):
        raise TypeError("starting_equity must be a Money or Absent")
    if isinstance(starting_equity, Money) and starting_equity.asset != quote_asset:
        raise StatisticsRefusedError(
            f"a starting equity in {starting_equity.asset.code} cannot baseline a "
            f"curve in {quote_asset.code}"
        )

    excluded: list[str] = []
    contributing: list[TradeStat] = []
    for stat in trades:
        if stat.quote_asset != quote_asset:
            continue
        if not stat.is_closed:
            continue
        if isinstance(stat.closed_at, Absent):
            excluded.append(
                f"{stat.trade_ref} is closed but records no closing instant"
            )
            continue
        if isinstance(stat.realized_pnl_net, Absent):
            excluded.append(
                f"{stat.trade_ref} closed with no stateable profit and loss: "
                f"{stat.realized_pnl_net.reason}"
            )
            continue
        contributing.append(stat)

    points: list[EquityPoint] = []
    running = Money.zero(quote_asset)
    for stat in sorted(contributing, key=_sort_key):
        running = running + stat.realized_pnl_net
        points.append(
            EquityPoint(
                at=stat.closed_at,
                trade_ref=stat.trade_ref,
                delta=stat.realized_pnl_net,
                cumulative=running,
                equity=(
                    starting_equity
                    if isinstance(starting_equity, Absent)
                    else starting_equity + running
                ),
            )
        )
    return EquityCurve(
        quote_asset=quote_asset,
        points=tuple(points),
        starting_equity=starting_equity,
        excluded=tuple(excluded),
        open_trades=sum(
            1 for stat in trades if stat.is_open and stat.quote_asset == quote_asset
        ),
    )


def as_percentage(amount: Money, basis: Money | Absent) -> Decimal | Absent:
    """An amount as a fraction of a baseline, or the absence naming its lack.

    Written here rather than at each call site because the two failure cases —
    no baseline at all, and a baseline of zero — are different absences and both
    are easy to render as `0.00 %`.
    """
    if not isinstance(amount, Money):
        raise TypeError("amount must be a Money")
    if isinstance(basis, Absent):
        return Absent(
            "no starting equity was supplied, so an amount has no percentage form. "
            "This system records the owner's opening capital nowhere"
        )
    if not isinstance(basis, Money):
        raise TypeError("basis must be a Money or Absent")
    if basis.asset != amount.asset:
        return Absent(
            f"the baseline is in {basis.asset.code} and the amount is in "
            f"{amount.asset.code}; no rate in this system crosses them"
        )
    if basis.amount == 0:
        return Absent("a baseline of zero has no fraction of it")
    return amount.amount / basis.amount
