"""Builders for portfolio and risk-engine fixtures.

Extends `tests/trade_domain_helpers.py` and `tests/persistence_helpers.py` rather
than duplicating either. The market, the account, the assets, the dust policy and
the risk-budget builders are already defined there, and a second definition of
"a valid limit" would drift from the first.

**Two venues and two accounts are first-class fixtures**, because the milestone's
central architectural claim is that portfolio logic is venue-agnostic. A test
suite whose only market is `binance:BTCUSDT:spot` cannot demonstrate that claim,
and `EVEDEX_MARKET` exists so the same arithmetic is exercised against a venue
this repository has no provider for and never will inside this package.

**No clock and no threshold.** Every instant is `AT(...)`; every limit value is
passed in by the test that cares about it.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from trade_domain_helpers import ACCOUNT, AT, BTC, MARKET, USDT

from fmis.accounts import AccountId, Book, MarketId, MarketMode, OwnerContext, VenueId
from fmis.money import AssetCode, Money, Quantity
from fmis.portfolio import MarkQuote
from fmis.portfolio_risk import (
    ClassificationMap,
    ExposureLine,
    ExposureSource,
    PortfolioState,
    ProposedTrade,
    build_state,
    unclassified_map,
)
from fmis.positions import PositionDirection
from fmis.provenance import Absent
from fmis.snapshotting import TradeDirection

__all__ = [
    "ETH",
    "SOL",
    "EUR",
    "EVEDEX",
    "SECOND_ACCOUNT",
    "ETH_MARKET",
    "SOL_MARKET",
    "EVEDEX_MARKET",
    "EVEDEX_PERP",
    "EUR_MARKET",
    "USDC",
    "BTCUSDC_MARKET",
    "PORTFOLIO_ID",
    "owner",
    "mark",
    "line",
    "state",
    "proposal",
    "groups",
    "no_groups",
    "usdt",
    "btc",
]

ETH = AssetCode("ETH")
SOL = AssetCode("SOL")
EUR = AssetCode("EUR")

#: A venue this repository has no provider for, no adapter for and no plan to
#: build either. Every figure computed against it must be identical in kind to
#: one computed against Binance, or the venue-agnostic claim is false.
EVEDEX = VenueId("evedex")

SECOND_ACCOUNT = AccountId("evedex_main")

ETH_MARKET = MarketId(VenueId("binance"), ETH, USDT, MarketMode.SPOT)
SOL_MARKET = MarketId(VenueId("binance"), SOL, USDT, MarketMode.SPOT)
#: The *same pair* at a different venue. Two markets, two counterparties, and
#: deliberately not one netted position.
EVEDEX_MARKET = MarketId(EVEDEX, BTC, USDT, MarketMode.SPOT)
EVEDEX_PERP = MarketId(EVEDEX, BTC, USDT, MarketMode.PERPETUAL)
#: A market quoted in something other than the portfolio's base currency.
EUR_MARKET = MarketId(VenueId("binance"), BTC, EUR, MarketMode.SPOT)
#: The same base asset under a *different quote*. Two symbols, one bet on BTC —
#: the shape that made hostile-review finding H1 possible.
USDC = AssetCode("USDC")
BTCUSDC_MARKET = MarketId(VenueId("binance"), BTC, USDC, MarketMode.SPOT)

PORTFOLIO_ID = "main"


def owner(**overrides: Any) -> OwnerContext:
    values: dict[str, Any] = {
        "display_timezone": "Europe/Stockholm",
        "base_currency": USDT,
        "tax_period_timezone": "Europe/Stockholm",
    }
    values.update(overrides)
    return OwnerContext(**values)


def usdt(amount: str) -> Money:
    return Money(Decimal(amount), USDT)


def btc(amount: str) -> Quantity:
    return Quantity(Decimal(amount), BTC)


def mark(
    price: str, *, quote: AssetCode = USDT, at: datetime | None = None
) -> MarkQuote:
    return MarkQuote(
        price=Decimal(price),
        quote_asset=quote,
        source="fixture",
        as_of=AT(9) if at is None else at,
    )


def line(**overrides: Any) -> ExposureLine:
    """A marked, stopped, 0.5 BTC long in the swing book. Override one thing."""
    values: dict[str, Any] = {
        "account": ACCOUNT,
        "market": MARKET,
        "book": Book.SWING,
        "direction": PositionDirection.LONG,
        "quantity": btc("0.5"),
        "source": ExposureSource.HELD,
        "entry": Decimal("60000"),
        "stop": Decimal("58400"),
        "mark": mark("61000"),
    }
    values.update(overrides)
    return ExposureLine(**values)


def groups(version: str = "owner-v1", **assignments: Any) -> ClassificationMap:
    """`groups(BTC=["l1"], ETH=["l1", "defi"])` — the owner's own words."""
    return ClassificationMap.of(
        version, {asset: tuple(labels) for asset, labels in assignments.items()}
    )


def no_groups(version: str = "owner-v1") -> ClassificationMap:
    return unclassified_map(version)


def state(
    *lines: ExposureLine,
    equity: Money | Absent | None = None,
    cash: Money | Absent | None = None,
    classification: ClassificationMap | None = None,
    **overrides: Any,
) -> PortfolioState:
    """A portfolio over the supplied lines, with 100 000 USDT equity by default."""
    values: dict[str, Any] = {
        "portfolio_id": PORTFOLIO_ID,
        "base_currency": USDT,
        "as_of": AT(12),
        "lines": lines,
        "equity": usdt("100000") if equity is None else equity,
        "cash": usdt("40000") if cash is None else cash,
        "classification": no_groups() if classification is None else classification,
    }
    values.update(overrides)
    return build_state(**values)


def proposal(**overrides: Any) -> ProposedTrade:
    """A 0.25 BTC long at 60 000 with a 58 400 stop — 400 USDT at risk."""
    values: dict[str, Any] = {
        "account": ACCOUNT,
        "market": MARKET,
        "book": Book.SWING,
        "direction": TradeDirection.LONG,
        "entry": Decimal("60000"),
        "stop": Decimal("58400"),
        "quantity": btc("0.25"),
    }
    values.update(overrides)
    return ProposedTrade(**values)
