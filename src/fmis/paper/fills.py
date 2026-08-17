"""Where a simulated fill lands. Pure arithmetic over exact values.

No candle, no clock, no store, no randomness — four prices, a side, a level, and
one rule applied identically to every case.

**The gap rule, stated once.** A level is filled at the level, unless the bar's
**open** was already past it, in which case it is filled at the open. That is not
a courtesy to the owner and not a penalty: it is what a real order does, and it is
applied to a favourable gap (a limit that filled better) and an unfavourable one
(a breakout that filled worse) by the same two lines. Rounding the asymmetry
towards the owner's benefit is the single commonest way a paper record flatters
itself, and writing the rule once is what makes that impossible here.

**A level that fills intrabar does not tell you where price went next.** If a
`LIMIT` or `STOP_ENTRY` fills *at its level* rather than at the bar's open, the
remainder of that bar's path is unknowable from four numbers, and this module says
so: `entry_resolves_the_bar` is `False`. What the engine does with that answer is
`fmis.paper.engine`'s decision and is stated there — a quiet bar defers, and a bar
that also reached an exit level halts.

**A market entry and a gapped entry both fill at the open**, which *is* the
earliest price of the bar, so the rest of that bar is fully available and the
ordinary exit rules apply to it.
"""

from __future__ import annotations

from decimal import Decimal

from fmis.provenance import Absent
from fmis.records import require_member
from fmis.snapshotting import TradeDirection
from fmis.trade_lifecycle import EntryType, TradeActivation
from fmis.paper.models import PaperRefusedError, PriceBar

__all__ = [
    "ENTRY_IS_FAVOURABLE",
    "fill_at_level",
    "entry_level_of",
    "entry_reached",
    "entry_fill",
    "entry_resolves_the_bar",
    "stop_reached",
    "stop_fill",
    "reached_legs",
    "target_fill",
]

#: Which side of the entry each entry type's level sits on.
#:
#: A `LIMIT` waits for price to come **back** to it — the adverse side of where
#: price is now — and a `STOP_ENTRY` waits for price to run **through** a level in
#: the trade's own direction. Two entry types, one table, so the gap rule below
#: cannot be applied with the sides swapped for one of them.
ENTRY_IS_FAVOURABLE: dict[EntryType, bool] = {
    EntryType.LIMIT: False,
    EntryType.STOP_ENTRY: True,
}


def _require_bar(bar: object) -> PriceBar:
    if not isinstance(bar, PriceBar):
        raise TypeError(f"bar must be a PriceBar, got {type(bar).__name__}")
    return bar


def _require_activation(activation: object) -> TradeActivation:
    if not isinstance(activation, TradeActivation):
        raise TypeError(
            f"activation must be a TradeActivation, got {type(activation).__name__}"
        )
    return activation


def fill_at_level(
    direction: TradeDirection, bar: PriceBar, level: Decimal, *, favourable: bool
) -> tuple[Decimal, bool]:
    """`(price, gapped)` for a level this bar reached.

    Raises when the bar did not reach it: producing a price for a level price
    never touched would be the one failure this whole module exists to prevent,
    and returning a sentinel would let a caller use it by accident.
    """
    require_member(direction, TradeDirection, "direction")
    candle = _require_bar(bar)
    if not candle.reached(direction, level, favourable=favourable):
        raise PaperRefusedError(
            f"the bar opening {candle.open_time.isoformat()} did not reach the "
            "level, so there is no price at which it filled"
        )
    if candle.opened_beyond(direction, level, favourable=favourable):
        return candle.open, True
    return level, False


def entry_level_of(activation: TradeActivation) -> Decimal | Absent:
    """The price a non-market entry waits for, or the absence a market one has."""
    return _require_activation(activation).entry_price


def entry_reached(
    activation: TradeActivation, direction: TradeDirection, bar: PriceBar
) -> bool:
    """Whether this closed bar met the entry condition.

    A market entry is met by the **first bar that opened at or after the
    activation** — never by the bar the owner was looking at when they activated.
    That bar's open had already happened when the decision was made, and filling
    at it would be a lookahead of exactly one bar dressed up as realism.
    """
    subject = _require_activation(activation)
    candle = _require_bar(bar)
    require_member(direction, TradeDirection, "direction")
    if candle.open_time < subject.activated_at:
        return False
    if subject.entry_type is EntryType.MARKET:
        return True
    level = subject.entry_price
    if isinstance(level, Absent):  # pragma: no cover - the model forbids it
        raise PaperRefusedError(
            "a non-market entry with no level cannot be tested against a bar"
        )
    return candle.reached(
        direction, level, favourable=ENTRY_IS_FAVOURABLE[subject.entry_type]
    )


def entry_fill(
    activation: TradeActivation, direction: TradeDirection, bar: PriceBar
) -> tuple[Decimal, bool]:
    """`(price, gapped)` for the entry this bar filled."""
    subject = _require_activation(activation)
    candle = _require_bar(bar)
    if not entry_reached(subject, direction, candle):
        raise PaperRefusedError(
            f"the bar opening {candle.open_time.isoformat()} did not meet the "
            "entry condition"
        )
    if subject.entry_type is EntryType.MARKET:
        return candle.open, False
    level = subject.entry_price
    assert not isinstance(level, Absent)  # entry_reached proved it
    return fill_at_level(
        direction,
        candle,
        level,
        favourable=ENTRY_IS_FAVOURABLE[subject.entry_type],
    )


def entry_resolves_the_bar(price: Decimal, bar: PriceBar) -> bool:
    """Whether the entry filled at the **open**, leaving the rest of the bar usable.

    A fill at the open happened at the earliest price of the bar, so everything
    that follows inside it is genuinely available to the exit rules. A fill at a
    level somewhere inside the bar is not, and the engine defers.
    """
    return price == _require_bar(bar).open


def stop_reached(
    direction: TradeDirection, bar: PriceBar, stop: Decimal
) -> bool:
    """Whether this bar's range touched the effective stop."""
    require_member(direction, TradeDirection, "direction")
    return _require_bar(bar).reached(direction, stop, favourable=False)


def stop_fill(
    direction: TradeDirection, bar: PriceBar, stop: Decimal
) -> tuple[Decimal, bool]:
    """`(price, gapped)` for a stop this bar reached. A gap fills worse, and does."""
    return fill_at_level(direction, bar, stop, favourable=False)


def reached_legs(
    activation: TradeActivation,
    direction: TradeDirection,
    bar: PriceBar,
    *,
    already_filled: tuple[int, ...],
) -> tuple[int, ...]:
    """The unfilled ladder rungs this bar reached, nearest first.

    Nearest first is the order geometry puts them in — price cannot pass the
    further rung without passing the nearer one — so two rungs filling on one bar
    carry a sequence that is derived rather than assumed. `ExitLadder` already
    refuses a ladder whose rungs do not step away from the entry, which is what
    makes that statement true rather than hopeful.
    """
    subject = _require_activation(activation)
    candle = _require_bar(bar)
    require_member(direction, TradeDirection, "direction")
    return tuple(
        index
        for index, leg in enumerate(subject.ladder.legs)
        if index not in already_filled
        and candle.reached(direction, leg.target, favourable=True)
    )


def target_fill(
    activation: TradeActivation,
    direction: TradeDirection,
    bar: PriceBar,
    *,
    leg_index: int,
) -> tuple[Decimal, bool]:
    """`(price, gapped)` for one ladder rung this bar reached."""
    subject = _require_activation(activation)
    legs = subject.ladder.legs
    if leg_index < 0 or leg_index >= len(legs):
        raise PaperRefusedError(
            f"this ladder has {len(legs)} rung(s); there is no rung {leg_index + 1}"
        )
    return fill_at_level(direction, bar, legs[leg_index].target, favourable=True)
