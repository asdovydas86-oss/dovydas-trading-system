"""What is true about a trade right now — every figure the brief's §3 asks for.

A **projection**. Nothing here is stored, everything is recomputed, and deleting
a monitor reading and rebuilding it produces the identical answer.

**No arithmetic is duplicated.** The sign rule is `TradeDirection.sign`; the risk
distance and the capital at risk are `fmis.portfolio_risk.geometry`'s, called; the
average entry is `AverageCost.per_unit`; the realized profit and loss is the
position fold's; the effective stop is `fold_stop_history`'s. This module's own
contribution is three quotients and a subtraction, and it computes them at read
time and stores none of them.

**Every R multiple rests on the same denominator**, and it is the **initial**
risk — `|entry − initial stop| × the size that was activated`. Two consequences
are deliberate. Realized, unrealized and total R add up, because all three are
that one amount divided into. And an R multiple does not grow when the stop is
tightened: measuring against the *effective* stop would make good management read
as a smaller trade and would make two trades' R multiples incomparable.

**Absence is a value with a reason, never a zero.** An unmarked position has no
unrealized R and a trade that never filled has no excursion; a zero in either
place makes a page look complete and survives for years.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fmis.money import AssetCode, Money, Quantity, canonical_decimal_text
from fmis.portfolio_risk import (
    RISK_BASIS,
    RiskGeometryError,
    capital_at_risk_of,
    direction_of,
    stop_distance,
)
from fmis.positions import Position
from fmis.provenance import Absent
from fmis.records import require_int, require_member, require_utc
from fmis.snapshotting import TradeDirection
from fmis.trade_lifecycle import StopHistory, TradeActivation, TradeLifecycleView
from fmis.paper.models import Excursion, PaperRefusedError, PriceBar

__all__ = ["MONITOR_BASIS", "TradeMonitor", "monitor_trade"]

#: What every figure below assumes, stated once and printed beside the numbers.
#: `RISK_BASIS` is `fmis.portfolio_risk`'s own sentence, reused rather than
#: paraphrased — a second wording of one caveat is a second caveat somebody will
#: eventually decide is a different one.
MONITOR_BASIS = (
    f"Every R multiple is measured against the initial risk, which is {RISK_BASIS}. "
    "Prices come from the simulation interval's closed bars only."
)

_SECONDS_PER_DAY = Decimal(60 * 60 * 24)


@dataclass(frozen=True, slots=True)
class TradeMonitor:
    """One reading of one trade, at one instant. Computed, never stored."""

    activation_id: str
    market: str
    state: str
    remaining: Quantity
    initial_stop: Decimal
    effective_stop: Decimal
    entry_price: Decimal | Absent = field(
        default_factory=lambda: Absent("no fill has opened this trade")
    )
    last_price: Decimal | Absent = field(
        default_factory=lambda: Absent("no bar has been observed")
    )
    risk_distance: Decimal | Absent = field(
        default_factory=lambda: Absent("no entry to measure risk from")
    )
    initial_risk: Money | Absent = field(
        default_factory=lambda: Absent("no entry to measure risk from")
    )
    realized_r: Decimal | Absent = field(
        default_factory=lambda: Absent("nothing has been realized")
    )
    unrealized_r: Decimal | Absent = field(
        default_factory=lambda: Absent("no mark and no open size")
    )
    total_r: Decimal | Absent = field(
        default_factory=lambda: Absent("neither half of the R multiple is stateable")
    )
    max_favourable_r: Decimal | Absent = field(
        default_factory=lambda: Absent("no excursion has been observed")
    )
    max_adverse_r: Decimal | Absent = field(
        default_factory=lambda: Absent("no excursion has been observed")
    )
    max_favourable_price: Decimal | Absent = field(
        default_factory=lambda: Absent("no excursion has been observed")
    )
    max_adverse_price: Decimal | Absent = field(
        default_factory=lambda: Absent("no excursion has been observed")
    )
    holding_time: timedelta | Absent = field(
        default_factory=lambda: Absent("this trade has never held a position")
    )
    days_in_trade: Decimal | Absent = field(
        default_factory=lambda: Absent("this trade has never held a position")
    )
    bars_in_trade: int = 0
    distance_to_stop: Decimal | Absent = field(
        default_factory=lambda: Absent("no mark to measure the distance from")
    )
    distance_to_target: Decimal | Absent = field(
        default_factory=lambda: Absent("no unfilled target, or no mark")
    )
    next_target: Decimal | Absent = field(
        default_factory=lambda: Absent("every rung of the ladder has filled")
    )
    stop_moves: int = 0
    stop_widenings: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.remaining, Quantity):
            raise TypeError("remaining must be a Quantity")
        require_int(self.bars_in_trade, "bars_in_trade", minimum=0)
        require_int(self.stop_moves, "stop_moves", minimum=0)
        require_int(self.stop_widenings, "stop_widenings", minimum=0)
        if self.stop_widenings > self.stop_moves:
            raise PaperRefusedError(
                "more stop moves widened than were made; a widening is one kind of "
                "move, not a separate count"
            )

    @property
    def is_exposed(self) -> bool:
        return not self.remaining.is_zero

    @property
    def stop_was_moved(self) -> bool:
        return self.stop_moves > 0

    def to_payload(self) -> dict[str, Any]:
        """Exportable. **No decoder**, deliberately: a reading is recomputed, and
        one that could be read back would be a stored projection."""
        return {
            "activation_id": self.activation_id,
            "market": self.market,
            "state": self.state,
            "remaining": self.remaining.to_payload(),
            "initial_stop": canonical_decimal_text(self.initial_stop),
            "effective_stop": canonical_decimal_text(self.effective_stop),
            "entry_price": _maybe_text(self.entry_price),
            "last_price": _maybe_text(self.last_price),
            "risk_distance": _maybe_text(self.risk_distance),
            "initial_risk": _maybe_money(self.initial_risk),
            "realized_r": _maybe_text(self.realized_r),
            "unrealized_r": _maybe_text(self.unrealized_r),
            "total_r": _maybe_text(self.total_r),
            "max_favourable_r": _maybe_text(self.max_favourable_r),
            "max_adverse_r": _maybe_text(self.max_adverse_r),
            "max_favourable_price": _maybe_text(self.max_favourable_price),
            "max_adverse_price": _maybe_text(self.max_adverse_price),
            "holding_time_seconds": (
                None
                if isinstance(self.holding_time, Absent)
                else self.holding_time.total_seconds()
            ),
            "days_in_trade": _maybe_text(self.days_in_trade),
            "bars_in_trade": self.bars_in_trade,
            "distance_to_stop": _maybe_text(self.distance_to_stop),
            "distance_to_target": _maybe_text(self.distance_to_target),
            "next_target": _maybe_text(self.next_target),
            "stop_moves": self.stop_moves,
            "stop_widenings": self.stop_widenings,
        }


def _maybe_text(value: Decimal | Absent) -> str | None:
    return None if isinstance(value, Absent) else canonical_decimal_text(value)


def _maybe_money(value: Money | Absent) -> dict[str, Any] | None:
    return None if isinstance(value, Absent) else value.to_payload()


def monitor_trade(
    *,
    activation: TradeActivation,
    direction: TradeDirection,
    stop_history: StopHistory,
    view: TradeLifecycleView,
    position: Position | Absent,
    excursion: Excursion,
    last_bar: PriceBar | Absent,
    filled_legs: tuple[int, ...] = (),
    at: datetime,
) -> TradeMonitor:
    """Every figure the milestone brief's position-monitoring list names.

    `at` is supplied rather than read: a reading that stamped itself could not be
    pinned in a test, and `fmis.pipeline.cli` is the only place in this repository
    that takes the time.
    """
    if not isinstance(activation, TradeActivation):
        raise TypeError("activation must be a TradeActivation")
    require_member(direction, TradeDirection, "direction")
    if not isinstance(stop_history, StopHistory):
        raise TypeError("stop_history must be a StopHistory")
    if not isinstance(view, TradeLifecycleView):
        raise TypeError("view must be a TradeLifecycleView")
    if not isinstance(position, (Position, Absent)):
        raise TypeError("position must be a Position or Absent")
    if not isinstance(excursion, Excursion):
        raise TypeError("excursion must be an Excursion")
    if not isinstance(last_bar, (PriceBar, Absent)):
        raise TypeError("last_bar must be a PriceBar or Absent")
    moment = require_utc(at, "at")

    quote = activation.market.quote_asset
    remaining = _remaining_of(position, activation.quantity.asset)
    entry = _entry_of(position)
    mark = (
        Absent("no bar has been observed for this market")
        if isinstance(last_bar, Absent)
        else last_bar.close
    )
    distance, initial_risk = _risk_of(
        activation, direction, entry, quote, initial_stop=stop_history.initial
    )

    realized = _realized_r(position, initial_risk)
    unrealized = _unrealized_r(direction, entry, mark, remaining, initial_risk, quote)
    total = _sum_r(realized, unrealized)
    favourable_r = _excursion_r(direction, entry, excursion.favourable, distance)
    adverse_r = _excursion_r(direction, entry, excursion.adverse, distance)
    holding, days = _holding(position, moment)
    target = _next_target(activation, filled_legs)

    return TradeMonitor(
        activation_id=activation.activation_id,
        market=activation.market.value,
        state=view.state.value,
        remaining=remaining,
        initial_stop=stop_history.initial,
        effective_stop=stop_history.effective,
        entry_price=entry,
        last_price=mark,
        risk_distance=distance,
        initial_risk=initial_risk,
        realized_r=realized,
        unrealized_r=unrealized,
        total_r=total,
        max_favourable_r=favourable_r,
        max_adverse_r=adverse_r,
        max_favourable_price=excursion.favourable,
        max_adverse_price=excursion.adverse,
        holding_time=holding,
        days_in_trade=days,
        bars_in_trade=excursion.bars,
        distance_to_stop=_gap(direction, mark, stop_history.effective, towards=False),
        distance_to_target=_gap(direction, mark, target, towards=True),
        next_target=target,
        stop_moves=len(stop_history.moves),
        stop_widenings=stop_history.widening_count,
    )


def _remaining_of(position: Position | Absent, asset: AssetCode) -> Quantity:
    """The open size, as a positive magnitude. Direction is carried separately."""
    if isinstance(position, Absent):
        return Quantity.zero(asset)
    return abs(position.net_quantity)


def _entry_of(position: Position | Absent) -> Decimal | Absent:
    if isinstance(position, Absent):
        return Absent("nothing has filled against this activation")
    return position.average_entry.per_unit


def _risk_of(
    activation: TradeActivation,
    direction: TradeDirection,
    entry: Decimal | Absent,
    quote: AssetCode,
    *,
    initial_stop: Decimal,
) -> tuple[Decimal | Absent, Money | Absent]:
    """`(risk distance, initial risk amount)`, or the reason neither exists.

    Both come from `fmis.portfolio_risk`, which owns the sign rule and refuses a
    transposed stop rather than returning its magnitude. A refusal is turned into
    an `Absent` carrying that engine's own message, because a monitor that raised
    would take the whole page down with one badly-placed stop.

    **`initial_stop`, never the effective one.** An R multiple measured against a
    moving denominator is not an R: it would grow every time the stop was
    tightened, making good management read as a smaller trade and making two
    trades' R multiples incomparable.
    """
    if isinstance(entry, Absent):
        return entry, Absent(entry.reason)
    side = direction_of(direction)
    try:
        distance = stop_distance(side, entry=entry, stop=initial_stop)
        risk = capital_at_risk_of(
            side,
            entry=entry,
            stop=initial_stop,
            quantity=activation.quantity,
            quote_asset=quote,
        )
    except RiskGeometryError as error:
        reason = Absent(str(error))
        return reason, reason
    return distance, risk


def _realized_r(
    position: Position | Absent, initial_risk: Money | Absent
) -> Decimal | Absent:
    if isinstance(position, Absent):
        return Absent("nothing has been realized")
    if isinstance(initial_risk, Absent):
        return Absent(initial_risk.reason)
    if position.realized_pnl_net.asset != initial_risk.asset:
        return Absent(
            f"realized profit is stated in {position.realized_pnl_net.asset} and "
            f"the risk in {initial_risk.asset}; a ratio over two currencies needs "
            "a dated rate this reading does not carry"
        )
    return position.realized_pnl_net.amount / initial_risk.amount


def _unrealized_r(
    direction: TradeDirection,
    entry: Decimal | Absent,
    mark: Decimal | Absent,
    remaining: Quantity,
    initial_risk: Money | Absent,
    quote: AssetCode,
) -> Decimal | Absent:
    if remaining.is_zero:
        # A **known** zero, not an absence. Nothing is open, so the unrealized
        # half is exactly nothing — and returning `Absent` here would make the
        # total R of every closed trade unstateable, which is the one figure a
        # finished trade most obviously has.
        return Decimal(0)
    if isinstance(entry, Absent):
        return Absent(entry.reason)
    if isinstance(mark, Absent):
        return Absent(mark.reason)
    if isinstance(initial_risk, Absent):
        return Absent(initial_risk.reason)
    open_value = Money(direction.sign * (mark - entry) * remaining.amount, quote)
    return open_value.amount / initial_risk.amount


def _sum_r(
    realized: Decimal | Absent, unrealized: Decimal | Absent
) -> Decimal | Absent:
    """Realized plus unrealized, and `Absent` when either half is unstateable.

    Never a partial total. `fmis.portfolio_risk.sum_or_absent` states the rule
    this follows: a sum missing one of its terms reads as a smaller total rather
    than as an unknown one.
    """
    if isinstance(realized, Absent) and isinstance(unrealized, Absent):
        return Absent("neither half of the R multiple is stateable")
    if isinstance(realized, Absent):
        return Absent(f"the realized half is not stateable: {realized.reason}")
    if isinstance(unrealized, Absent):
        return Absent(f"the unrealized half is not stateable: {unrealized.reason}")
    return realized + unrealized


def _excursion_r(
    direction: TradeDirection,
    entry: Decimal | Absent,
    extreme: Decimal | Absent,
    distance: Decimal | Absent,
) -> Decimal | Absent:
    if isinstance(entry, Absent):
        return Absent(entry.reason)
    if isinstance(extreme, Absent):
        return Absent(extreme.reason)
    if isinstance(distance, Absent):
        return Absent(distance.reason)
    return direction.sign * (extreme - entry) / distance


def _holding(
    position: Position | Absent, at: datetime
) -> tuple[timedelta | Absent, Decimal | Absent]:
    if isinstance(position, Absent):
        reason = Absent("this trade has never held a position")
        return reason, reason
    ended = at if isinstance(position.closed_at, Absent) else position.closed_at
    elapsed = ended - position.opened_at
    days = Decimal(str(elapsed.total_seconds())) / _SECONDS_PER_DAY
    return elapsed, days


def _next_target(
    activation: TradeActivation, filled_legs: tuple[int, ...]
) -> Decimal | Absent:
    for index, leg in enumerate(activation.ladder.legs):
        if index not in filled_legs:
            return leg.target
    if activation.ladder.is_empty:
        return Absent("this activation states no target ladder")
    return Absent("every rung of the ladder has filled")


def _gap(
    direction: TradeDirection,
    mark: Decimal | Absent,
    level: Decimal | Absent,
    *,
    towards: bool,
) -> Decimal | Absent:
    """How far price is from a level, signed so that positive is *not yet there*.

    One function for both distances, so the distance to a stop and the distance
    to a target cannot acquire two different sign conventions — the failure that
    makes a page read as safe when it is not.
    """
    if isinstance(mark, Absent):
        return Absent(mark.reason)
    if isinstance(level, Absent):
        return Absent(level.reason)
    return direction.sign * (level - mark) if towards else direction.sign * (mark - level)
