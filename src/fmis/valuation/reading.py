"""The composition root: a store and a price snapshot in, a valuation out.

    markets_to_price(store)             ──►  which markets need a price at all
    value_portfolio(store, prices)      ──►  PortfolioValuation

**This module reads and never writes.** Every record reaches it through a BI
repository and no write verb appears anywhere in the file — the identical rule
`fmis.portfolio_risk.reading` and `fmis.trade_capture.views` already hold, for
the identical reason: a read path that repaired something would make the store's
contents depend on who looked at them.

**It fetches nothing.** `prices` is an argument. A `PriceSnapshot` is a value,
and taking it as a parameter is what lets the whole of this milestone's
arithmetic be exercised without a network, a clock or a temporary directory.

**The store is opened once and folded twice, and both folds are named.**
`PositionRepository.rebuild` gives the book-wide positions the rest of the
product already shows; `fmis.portfolio_risk.read_portfolio` folds the same fills
one account at a time, because a portfolio reports per account and a `Position`
holds none. Every figure on the valuation states which fold produced it, and
`PortfolioValuation.fold_disagreement` names every market where the two can
legitimately differ.

**Nothing is fabricated when a price is missing.** A market with no reading
becomes an unmarked position with the reason attached, every total that depended
on it becomes `Absent` naming it, and no figure quietly shrinks.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from fmis.accounts import Book, MarketId
from fmis.marks import PriceSnapshot
from fmis.money import AssetCode
from fmis.persistence import TradingStore
from fmis.portfolio import MarkQuote
from fmis.portfolio_risk import (
    DEFAULT_BOOKS_COVERED,
    ClassificationMap,
    read_portfolio,
)
from fmis.positions import Position
from fmis.provenance import Absent
from fmis.records import IDENTIFIER_PATTERN, require_pattern, require_utc

from fmis.valuation.marking import MarkSet, marks_for_markets, symbols_for_markets
from fmis.valuation.models import MarkedPosition, PortfolioValuation

__all__ = [
    "markets_to_price",
    "symbols_to_price",
    "open_positions_in",
    "marked_positions",
    "value_portfolio",
]


def _require_store(store: object) -> TradingStore:
    if not isinstance(store, TradingStore):
        raise TypeError(f"store must be a TradingStore, got {type(store).__name__}")
    return store


def open_positions_in(
    store: TradingStore,
    *,
    books_covered: tuple[Book, ...] = DEFAULT_BOOKS_COVERED,
    at: datetime | None = None,
) -> tuple[Position, ...]:
    """Every open position in the covered books, book-wide.

    ``at`` reconstructs what the store *knew* at a past instant rather than what
    had happened by then — the `written_at` axis, which is what makes a past
    valuation reproducible after a correction is filed.
    """
    trading = _require_store(store)
    folded = (
        trading.positions.rebuild()
        if at is None
        else trading.positions.as_known_at(require_utc(at, "at"))
    )
    return tuple(
        position
        for position in folded
        if position.is_open and position.book in books_covered
    )


def markets_to_price(
    store: TradingStore,
    *,
    books_covered: tuple[Book, ...] = DEFAULT_BOOKS_COVERED,
    at: datetime | None = None,
) -> tuple[MarketId, ...]:
    """Which markets a valuation of this store needs a price for.

    Open positions only. A closed position has no unrealized profit and loss and
    no market value, so fetching a price for it would spend a request to produce
    a number nothing may show.
    """
    found: list[MarketId] = []
    for position in open_positions_in(store, books_covered=books_covered, at=at):
        if position.market not in found:
            found.append(position.market)
    return tuple(found)


def symbols_to_price(
    store: TradingStore,
    *,
    books_covered: tuple[Book, ...] = DEFAULT_BOOKS_COVERED,
    at: datetime | None = None,
) -> tuple[str, ...]:
    """The provider symbols a valuation of this store needs, deduplicated."""
    return symbols_for_markets(
        markets_to_price(store, books_covered=books_covered, at=at)
    )


def marked_positions(
    positions: tuple[Position, ...], marks: Mapping[str, MarkQuote]
) -> tuple[MarkedPosition, ...]:
    """Pair each position with its mark, or with the reason it has none.

    A pure function over two arguments, so the pairing rule is testable without a
    store. The key is `MarketId.value` — venue and mode included — because a spot
    holding and a perpetual holding of the same pair must never be handed one
    another's price.
    """
    paired: list[MarkedPosition] = []
    for position in positions:
        quote = marks.get(position.market.value)
        paired.append(
            MarkedPosition(
                position=position,
                mark=(
                    quote
                    if quote is not None
                    else Absent(
                        f"no mark was supplied for {position.market.value}"
                    )
                ),
            )
        )
    return tuple(paired)


def value_portfolio(
    store: TradingStore,
    *,
    portfolio_id: str,
    base_currency: AssetCode | str,
    as_of: datetime,
    prices: PriceSnapshot,
    books_covered: tuple[Book, ...] = DEFAULT_BOOKS_COVERED,
    classification: ClassificationMap | None = None,
    known_at: datetime | None = None,
) -> PortfolioValuation:
    """The whole valuation: positions, marks, exposure, risk and the totals.

    Args:
        store: the durable store. Read, never written.
        portfolio_id: which portfolio's snapshot supplies cash and equity.
        base_currency: what every money figure is stated in.
        as_of: the instant this reading describes. An argument, never a clock.
        prices: the price snapshot marks are matched from.
        books_covered: which capacity pools this reading covers.
        classification: the owner's asset groups, or the unclassified map.
        known_at: reconstruct what the store knew at a past instant.

    Raises:
        TypeError: an argument is of the wrong type.
        PersistenceError, TradeDomainError: the store is unreadable. Neither is
            caught here — a corrupt store rendered as an empty portfolio is a
            page saying the owner holds nothing.
    """
    trading = _require_store(store)
    if not isinstance(prices, PriceSnapshot):
        raise TypeError(
            f"prices must be a PriceSnapshot, got {type(prices).__name__}"
        )
    asset = (
        base_currency
        if isinstance(base_currency, AssetCode)
        else AssetCode(base_currency)
    )
    moment = require_utc(as_of, "as_of")
    identifier = require_pattern(
        portfolio_id, IDENTIFIER_PATTERN, "portfolio_id"
    )

    positions = open_positions_in(
        trading, books_covered=books_covered, at=known_at
    )
    marks: MarkSet = marks_for_markets(
        prices, (position.market for position in positions)
    )
    state = read_portfolio(
        trading,
        portfolio_id=identifier,
        base_currency=asset,
        as_of=moment,
        books_covered=books_covered,
        marks=marks.quotes,
        classification=classification,
        known_at=known_at,
    )
    return PortfolioValuation(
        portfolio_id=identifier,
        base_currency=asset,
        as_of=moment,
        state=state,
        positions=marked_positions(positions, marks.quotes),
        marks=marks,
        prices=prices,
    )
