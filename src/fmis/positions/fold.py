"""The fold: resolved ledger events → positions.

Pure. Same events, same dust policy, same calculation version, same answer,
forever. Nothing is stored and nothing is cached — **delete every position,
recompute, and the result must be identical**. That is the CI test the whole
durability classification rests on, and this function is the half of it that can
be wrong.

Identity policy is `FLAT_CROSSING`: a position runs between two flats in one
`(market, book)` pair, and the ordinal counts crossings. `EXPLICIT_KEY` grouping
is deferred with a stated trigger — the owner reporting that a genuine new
decision was merged into an existing holding.

Weighted average cost is used for `average_entry` because it is the only method
invariant to lot-selection policy, so a *performance* figure never changes
because a *tax* setting changed. Stated once and enforced by naming:

> **Realized P&L for review is not taxable gain, and no surface may present one
> as the other.**
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from fmis.accounts import Book, MarketId
from fmis.ledger import ResolvedTrade
from fmis.money import AssetCode, DustPolicy, Money, Quantity
from fmis.positions.models import (
    AverageCost,
    Position,
    PositionDirection,
    PositionKey,
    PositionState,
    ReconciliationState,
)
from fmis.provenance import Absent
from fmis.records import DomainValidationError, require_text, require_tuple_of

__all__ = ["fold_positions", "POSITION_CALCULATION_VERSION"]

#: This build's fold version. A bump legitimately re-derives every position — and
#: is safe *only* because nothing frozen references a position's derived key.
POSITION_CALCULATION_VERSION = "position-fold-v1"


@dataclass(slots=True)
class _Accumulator:
    """Mutable working state for one position. Never leaves this module."""

    market: MarketId
    book: Book
    ordinal: int
    base: AssetCode
    quote: AssetCode
    opened_at: datetime
    net: Decimal = Decimal(0)
    cost: Decimal = Decimal(0)
    acquired: Decimal = Decimal(0)
    disposed: Decimal = Decimal(0)
    proceeds: Decimal = Decimal(0)
    realized_gross: Decimal = Decimal(0)
    last_at: datetime = None  # type: ignore[assignment]
    max_exposure: Decimal = Decimal(0)
    trade_count: int = 0
    add_count: int = 0
    reduce_count: int = 0
    fees: dict[str, Decimal] = field(default_factory=dict)
    event_ids: list[str] = field(default_factory=list)


def fold_positions(
    resolved: Iterable[ResolvedTrade],
    *,
    dust: DustPolicy,
    calculation_version: str = POSITION_CALCULATION_VERSION,
) -> tuple[Position, ...]:
    """Fold resolved trades into positions, one sequence per `(market, book)` pair."""
    trades = tuple(resolved)
    require_tuple_of(trades, ResolvedTrade, "resolved")
    if not isinstance(dust, DustPolicy):
        raise TypeError(f"dust must be a DustPolicy, got {type(dust).__name__}")
    version = require_text(calculation_version, "calculation_version")

    grouped: dict[tuple[str, Book], list[ResolvedTrade]] = {}
    for entry in trades:
        grouped.setdefault((entry.trade.market.value, entry.trade.book), []).append(entry)

    positions: list[Position] = []
    for (_, book), group in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1].value)):
        group.sort(key=lambda entry: (entry.trade.occurred_at, entry.event_id))
        positions.extend(_fold_one_pair(group, book=book, dust=dust, version=version))
    return tuple(positions)


def _fold_one_pair(
    group: Sequence[ResolvedTrade], *, book: Book, dust: DustPolicy, version: str
) -> list[Position]:
    market = group[0].trade.market
    base = market.base_asset
    quote = market.quote_asset
    ordinal = 0
    current: _Accumulator | None = None
    finished: list[Position] = []

    for entry in group:
        trade = entry.trade
        if trade.market != market:  # pragma: no cover - grouping guarantees this
            raise DomainValidationError("a fold group must hold one market")
        signed = trade.quantity.amount * trade.side.base_sign
        if current is None:
            current = _Accumulator(
                market=market,
                book=book,
                ordinal=ordinal,
                base=base,
                quote=quote,
                opened_at=trade.occurred_at,
                last_at=trade.occurred_at,
            )

        crossing = current.net != 0 and _crosses_zero(current.net, signed)
        if crossing:
            closing_part = -current.net
            remainder = signed - closing_part
            # A flipping fill pays one fee for two positions. Apportioning by
            # quantity is the only split the trade itself supports, and the
            # remainder — rather than a second division — goes to the opening
            # half so the two shares always sum to exactly what was paid.
            closing_fee = (
                trade.fee.amount * abs(closing_part) / trade.quantity.amount
            )
            _apply(current, entry, closing_part, fee_override=closing_fee)
            finished.append(
                _freeze(current, dust=dust, version=version, closed_by_flip=True)
            )
            ordinal += 1
            current = _Accumulator(
                market=market,
                book=book,
                ordinal=ordinal,
                base=base,
                quote=quote,
                opened_at=trade.occurred_at,
                last_at=trade.occurred_at,
            )
            _apply(
                current,
                entry,
                remainder,
                fee_override=trade.fee.amount - closing_fee,
            )
        else:
            _apply(current, entry, signed, fee_override=None)

        if dust.is_dust(Quantity(current.net, base)):
            finished.append(
                _freeze(current, dust=dust, version=version, closed_by_flip=False)
            )
            ordinal += 1
            current = None

    if current is not None:
        finished.append(_open(current, dust=dust, version=version))
    return finished


def _crosses_zero(net: Decimal, signed: Decimal) -> bool:
    """Whether this fill carries exposure through zero rather than to it.

    Reaching exactly zero is a *close*; passing through it is a *flip*, which the
    model requires be split into two positions at the same instant.
    """
    after = net + signed
    return (net > 0 and after < 0) or (net < 0 and after > 0)


def _apply(
    accumulator: _Accumulator,
    entry: ResolvedTrade,
    signed: Decimal,
    *,
    fee_override: Decimal | None,
) -> None:
    trade = entry.trade
    price = trade.price
    accumulator.trade_count += 1
    accumulator.event_ids.append(entry.event_id)
    accumulator.last_at = trade.occurred_at

    fee_key = trade.fee.asset.code
    fee_amount = trade.fee.amount if fee_override is None else fee_override
    if fee_amount != 0:
        accumulator.fees[fee_key] = (
            accumulator.fees.get(fee_key, Decimal(0)) + fee_amount
        )

    increasing = accumulator.net == 0 or (accumulator.net > 0) == (signed > 0)
    if increasing:
        accumulator.add_count += 1
        accumulator.acquired += abs(signed)
        accumulator.cost += abs(signed) * price
    else:
        accumulator.reduce_count += 1
        reduced = min(abs(signed), abs(accumulator.net))
        accumulator.disposed += reduced
        accumulator.proceeds += reduced * price
        if accumulator.acquired > 0:
            unit_cost = accumulator.cost / accumulator.acquired
            direction_sign = Decimal(1) if accumulator.net > 0 else Decimal(-1)
            accumulator.realized_gross += (
                (price - unit_cost) * reduced * direction_sign
            )

    accumulator.net += signed
    accumulator.max_exposure = max(accumulator.max_exposure, abs(accumulator.net))


def _direction(net: Decimal) -> PositionDirection:
    if net > 0:
        return PositionDirection.LONG
    if net < 0:
        return PositionDirection.SHORT
    # Unreachable: `_open` is only called when the net is outside dust, and a
    # net inside dust closes the position instead. Kept so a future fold that
    # calls this with a flat net gets a defined answer rather than a KeyError.
    return PositionDirection.FLAT  # pragma: no cover


def _fee_total(accumulator: _Accumulator) -> tuple[Money, ...]:
    return tuple(
        Money(amount, AssetCode(code))
        for code, amount in sorted(accumulator.fees.items())
    )


def _net_realized(accumulator: _Accumulator) -> Decimal:
    """Gross realized P&L less the fees paid **in the quote asset**.

    Fees in any other asset stay in `fees` and are reported separately rather than
    converted: netting them would require an FX rate this fold does not have, and
    silently using the trade's own rate would put a tax-currency conversion inside
    a performance figure.
    """
    quote_fees = accumulator.fees.get(accumulator.quote.code, Decimal(0))
    return accumulator.realized_gross - quote_fees


def _common(accumulator: _Accumulator, *, dust: DustPolicy, version: str) -> dict[str, Any]:
    return {
        "key": PositionKey(
            market_id=accumulator.market.value,
            book=accumulator.book.value,
            flat_crossing_ordinal=accumulator.ordinal,
        ),
        "market": accumulator.market,
        "book": accumulator.book,
        "average_entry": AverageCost(
            total_cost=Money(accumulator.cost, accumulator.quote),
            total_quantity=Quantity(accumulator.acquired, accumulator.base),
        ),
        "average_exit": (
            AverageCost(
                total_cost=Money(accumulator.proceeds, accumulator.quote),
                total_quantity=Quantity(accumulator.disposed, accumulator.base),
            )
            if accumulator.disposed > 0
            else Absent("nothing has been disposed of yet")
        ),
        "realized_pnl_gross": Money(accumulator.realized_gross, accumulator.quote),
        "realized_pnl_net": Money(_net_realized(accumulator), accumulator.quote),
        "fees": _fee_total(accumulator),
        "opened_at": accumulator.opened_at,
        "max_exposure": Quantity(accumulator.max_exposure, accumulator.base),
        "trade_count": accumulator.trade_count,
        "add_count": accumulator.add_count,
        "reduce_count": accumulator.reduce_count,
        "event_ids": tuple(accumulator.event_ids),
        "calculation_version": version,
        "dust_policy_id": dust.policy_id,
        "dust_policy_version": dust.version,
        "reconciliation": ReconciliationState.UNRECONCILED,
    }


def _freeze(
    accumulator: _Accumulator, *, dust: DustPolicy, version: str, closed_by_flip: bool
) -> Position:
    return Position(
        state=PositionState.CLOSED,
        direction=PositionDirection.FLAT,
        net_quantity=Quantity(Decimal(0), accumulator.base),
        closed_at=accumulator.last_at,
        closed_by_flip=closed_by_flip,
        **_common(accumulator, dust=dust, version=version),
    )


def _open(accumulator: _Accumulator, *, dust: DustPolicy, version: str) -> Position:
    return Position(
        state=PositionState.OPEN,
        direction=_direction(accumulator.net),
        net_quantity=Quantity(accumulator.net, accumulator.base),
        closed_at=Absent("the position is still open"),
        closed_by_flip=False,
        **_common(accumulator, dust=dust, version=version),
    )
