"""Builders for marked positions, valuations and the stores behind them.

Extends `tests/trade_domain_helpers.py`, `tests/persistence_helpers.py`,
`tests/portfolio_risk_helpers.py` and `tests/marks_helpers.py` rather than
duplicating any of them: the market, the account, the trade, the store and the
price snapshot are all already defined there.

**Positions are folded, never constructed.** `Position` is a rebuildable
projection, and a hand-built one would let a test assert a fold this repository
cannot actually produce. Everything here starts from `Trade` records and runs
them through the real fold.

**No clock and no network.** Every instant is `AT(...)` and every price arrives
as a `PriceSnapshot` built from candles.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from marks_helpers import snapshot as price_snapshot
from persistence_helpers import new_store, write_request
from trade_domain_helpers import AT, MARKET, USDT, trade

from fmis.ledger import LedgerResolver
from fmis.marks import PriceSnapshot
from fmis.money import DustPolicy
from fmis.positions import Position, fold_positions
from fmis.valuation import (
    DEFAULT_PORTFOLIO_ID,
    MarkedPosition,
    PortfolioValuation,
    marks_for_markets,
    value_portfolio,
)

__all__ = [
    "DUST",
    "positions_from",
    "one_position",
    "marked",
    "store_with",
    "with_cash",
    "valued",
]

#: Exact zero, matching what the production composition root configures.
DUST = DustPolicy(policy_id="fmits-valuation-exact-zero", version=1)


def positions_from(*trades: Any) -> tuple[Position, ...]:
    """Fold real `Trade` records through the real fold."""
    resolved = LedgerResolver(trades=tuple(trades), corrections=()).resolved()
    return fold_positions(resolved, dust=DUST)


def one_position(**overrides: Any) -> Position:
    """The single open position a default `trade()` folds to."""
    folded = positions_from(trade(**overrides))
    return folded[0]


def marked(price: float | None = 61000.0, **overrides: Any) -> MarkedPosition:
    """One position paired with a mark read at ``price``, or with none."""
    position = one_position(**overrides)
    if price is None:
        return MarkedPosition(position=position)
    found = marks_for_markets(price_snapshot(price), (position.market,))
    return MarkedPosition(position=position, mark=found.quotes[position.market.value])


def store_with(root: Path, *trades: Any, **extra: Any) -> Any:
    """A store holding the supplied trades, and nothing else unless asked.

    ``snapshots`` plants `PortfolioSnapshot` records, which is the only place
    cash and equity come from — there is no transfer event in this build, so a
    valuation that needs a cash figure needs one of these.
    """
    store = new_store(root, dust=DUST)
    for one in trades or (trade(),):
        store.trades.create(one, request=write_request())
    for record in extra.get("snapshots", ()):
        store.portfolios.create(record, request=write_request())
    return store


def with_cash(portfolio_id: str = DEFAULT_PORTFOLIO_ID, **overrides: Any) -> Any:
    """A `PortfolioSnapshot` this build's default valuation will actually read.

    `persistence_helpers.portfolio_snapshot` files under `"main"`; a valuation
    reads the portfolio it was asked about, so the id has to match or cash is
    correctly reported as never observed.
    """
    from persistence_helpers import portfolio_snapshot

    return portfolio_snapshot(portfolio_id=portfolio_id, **overrides)


def valued(
    root: Path,
    *trades: Any,
    prices: PriceSnapshot | None = None,
    as_of: Any = None,
    **kwargs: Any,
) -> PortfolioValuation:
    """A full valuation over a store built from ``trades``."""
    store = store_with(root, *trades, **kwargs)
    moment = AT(12) if as_of is None else as_of
    return value_portfolio(
        store,
        portfolio_id=kwargs.get("portfolio_id", DEFAULT_PORTFOLIO_ID),
        base_currency=USDT,
        as_of=moment,
        prices=price_snapshot(61000.0, taken_at=moment) if prices is None else prices,
    )
