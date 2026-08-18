"""Builders for `fmis.statistics` tests — one `TradeStat` factory, and a store.

Two levels, matching the package's own split. `stat(...)` builds a normalized
trade with no store and no filesystem, which is how every fold in the package is
exercised; `simulated_store(...)` writes real records through the product's own
write paths, which is how `collect` is exercised.

**Directional vocabulary is legitimate here.** `tests/` is outside ADR-0028's
scope, and a fixture that could not name which side a trade took could not build
one. The guard covers `src/fmis` and `fmis.statistics` takes no exemption.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fmis.accounts import Book, MarketId, MarketMode, VenueId
from fmis.money import AssetCode, Money
from fmis.provenance import Absent
from fmis.snapshotting import TradeDirection
from fmis.statistics import LifecyclePhase, StatSource, TradeStat

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
USDT = AssetCode("USDT")

#: Sentinel for a field that must come back `Absent`, where `None` already
#: means something else. Used only by `gross`, whose `None` means *"mirror
#: net"*.
ABSENT = object()


def market(symbol: str = "BTC", quote: str = "USDT", venue: str = "binance") -> MarketId:
    return MarketId(
        venue=VenueId(venue),
        base_asset=AssetCode(symbol),
        quote_asset=AssetCode(quote),
        mode=MarketMode.SPOT,
    )


def money(amount: str, asset: str = "USDT") -> Money:
    return Money(Decimal(amount), AssetCode(asset))


def at(days: int = 0, hours: int = 0) -> datetime:
    return EPOCH + timedelta(days=days, hours=hours)


def stat(
    ref: str = "act-1",
    *,
    plan_id: str | None = None,
    source: StatSource = StatSource.SIMULATED,
    phase: LifecyclePhase = LifecyclePhase.CLOSED,
    symbol: str = "BTC",
    quote: str = "USDT",
    venue: str = "binance",
    book: Book = Book.PAPER,
    direction: TradeDirection = TradeDirection.LONG,
    committed_day: int = 0,
    opened_day: int | None = 0,
    closed_day: int | None = 1,
    net: str | None = "100",
    #: `None` means *"mirror net"*, which is what a fee-free trade looks like.
    #: `ABSENT` means *"this figure genuinely is not stateable"* — a distinction
    #: the first draft could not express, so a mutation swapping which of the
    #: two fields decides `UNRESOLVED` survived every assertion over it.
    gross: str | None | object = None,
    risk: str | None = "50",
    r_multiple: str | None = "2",
    mfe: str | None = "3",
    mae: str | None = "-0.5",
    bars: int | None = 12,
    exit_reason: str | None = "target_hit",
    account: str | None = "main",
    interval: str | None = "1h",
    setup_type: str | None = "breakout",
    regime_states: dict[str, str] | None = None,
    stop_moves: int = 0,
    stop_widenings: int = 0,
) -> TradeStat:
    """One normalized trade. Every optional field becomes `Absent` when `None`.

    The defaults describe a finished, simulated, winning long — the shape most
    tests vary one field of. A test that needs an absence passes `None`, which
    is the one place in this repository `None` means *"make this absent"* and is
    confined to a fixture for exactly that reason.
    """
    quote_asset = AssetCode(quote)
    return TradeStat(
        trade_ref=ref,
        plan_id=plan_id or f"plan-{ref}",
        source=source,
        phase=phase,
        market=market(symbol, quote, venue),
        book=book,
        direction=direction,
        quote_asset=quote_asset,
        committed_at=at(committed_day),
        opened_at=_maybe(opened_day, at) if opened_day is not None else _absent("opened"),
        closed_at=_maybe(closed_day, at) if closed_day is not None else _absent("closed"),
        realized_pnl_net=_money(net, quote),
        realized_pnl_gross=_money(
            net if gross is None else (None if gross is ABSENT else gross), quote
        ),
        initial_risk=_money(risk, quote),
        r_multiple=_decimal(r_multiple),
        max_favourable_r=_decimal(mfe),
        max_adverse_r=_decimal(mae),
        bars_held=bars if bars is not None else _absent("bars"),
        holding_time=(
            at(closed_day) - at(opened_day)
            if closed_day is not None and opened_day is not None
            else _absent("holding time")
        ),
        exit_reason=exit_reason if exit_reason is not None else _absent("exit reason"),
        account=account if account is not None else _absent("account"),
        interval=interval if interval is not None else _absent("interval"),
        setup_type=setup_type if setup_type is not None else _absent("setup type"),
        regime_states=regime_states or {},
        stop_moves=stop_moves,
        stop_widenings=stop_widenings,
    )


def _absent(what: str) -> Absent:
    return Absent(f"the fixture made {what} absent")


def _maybe(day: int, build) -> datetime:
    return build(day)


def _money(raw: str | None, quote: str) -> Money | Absent:
    if raw is None:
        return _absent("money")
    return Money(Decimal(raw), AssetCode(quote))


def _decimal(raw: str | None) -> Decimal | Absent:
    if raw is None:
        return _absent("a number")
    return Decimal(raw)
