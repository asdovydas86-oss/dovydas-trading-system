"""The outer edge: open the store, fetch what it needs priced, value it.

Two functions, and the split between them is the whole design.

    marks_for_store(root, ...)   ──►  PriceSnapshot   (touches the network)
    run_valuation(root, ...)     ──►  PortfolioValuation

**Everything that touches a network lives here**, so `fmis.valuation.reading`
and `fmis.valuation.models` stay pure and every rule in them is testable without
one. This is the same split `fmis.today.builder` makes between `run_today` and
`build_today`, and it exists for the same reason.

**The store is asked what to fetch before anything is fetched.** A price source
is asked for exactly the symbols the owner has open positions in — never a
watchlist, never a universe. An owner holding nothing costs zero requests, and
`empty_price_snapshot` says so in words rather than by returning an empty
mapping that reads as a failure.

**The store is opened twice, and that is a deliberate trade.** Once to learn
which markets need a price, once to fold the valuation against the prices that
came back. Threading a half-read store through a network call to avoid the second
open would make the fold depend on when the fetch happened; two local reads of an
append-only store cost nothing and keep both folds honest.

**`read_marks=False` is a different answer from a failed fetch.** The first
produces an empty snapshot whose `source` says nothing was consulted; the second
produces a snapshot full of `unavailable` rows naming what went wrong. A page
that could not tell them apart would report an outage when the owner had simply
asked not to look.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fmis.accounts import Book
from fmis.marks import PriceSnapshot, empty_price_snapshot
from fmis.money import AssetCode, DustPolicy
from fmis.persistence import PersistenceError, TradingStore, default_store_root
from fmis.pipeline.prices import (
    MARK_CANDLE_LIMIT,
    MARK_INTERVAL,
    NO_SOURCE_CONSULTED,
    fetch_price_snapshot,
)
from fmis.portfolio_risk import DEFAULT_BOOKS_COVERED, ClassificationMap
from fmis.records import (
    IDENTIFIER_PATTERN,
    TradeDomainError,
    require_pattern,
    require_utc,
)

from fmis.valuation.marking import PortfolioStoreError
from fmis.valuation.models import PortfolioValuation
from fmis.valuation.reading import symbols_to_price, value_portfolio

__all__ = [
    "DEFAULT_PORTFOLIO_ID",
    "DEFAULT_BASE_CURRENCY",
    "VALUATION_DUST_POLICY",
    "marks_for_store",
    "run_valuation",
]

#: The portfolio a reading describes when the caller names none. FMITS has one
#: owner and, so far, one portfolio; naming it rather than leaving it blank means
#: the day a second exists, the first keeps its identity instead of inheriting a
#: new default. Underscored rather than hyphenated because `IDENTIFIER_PATTERN`
#: is the domain's own rule for what an id may look like, and a default that
#: failed it would fail at the first call rather than at review.
DEFAULT_PORTFOLIO_ID = "owner_portfolio"

#: What figures are stated in unless the caller says otherwise. `USDT` rather
#: than a fiat currency because that is what every market this build can price is
#: quoted in, and converting to one this system holds no rate for would be a
#: fabricated number rather than a convenience.
DEFAULT_BASE_CURRENCY = "USDT"

#: Exact zero, with no configured threshold. `fmis.money.DustPolicy`'s own rule:
#: *"an asset with no configured threshold uses exact zero... zero is the only
#: tolerance that is not a policy decision."* This package chooses no policy on
#: the owner's behalf, exactly as `fmis.today` does not.
VALUATION_DUST_POLICY = DustPolicy(policy_id="fmits-valuation-exact-zero", version=1)


def marks_for_store(
    root: Path | str | None = None,
    *,
    taken_at: datetime,
    books_covered: tuple[Book, ...] = DEFAULT_BOOKS_COVERED,
    interval: str = MARK_INTERVAL,
    limit: int = MARK_CANDLE_LIMIT,
    transport: object | None = None,
    clock: object | None = None,
    base_url: str | None = None,
    known_at: datetime | None = None,
) -> PriceSnapshot:
    """Fetch one price for every market this store has an open position in.

    Constructing a `TradingStore` creates no directory and writes no byte, so
    this is safe on a root that has never existed — it simply finds no market to
    price and returns an empty snapshot.

    Raises:
        PortfolioStoreError: the store exists and cannot be read. Wrapped rather
            than propagated, because `fmis.pipeline.cli` may not import the
            store and therefore cannot name the exception it would otherwise
            have to catch.
    """
    moment = require_utc(taken_at, "taken_at")
    store_root = default_store_root() if root is None else Path(root)
    store = TradingStore(store_root, dust=VALUATION_DUST_POLICY)
    symbols = _guarded(
        lambda: symbols_to_price(store, books_covered=books_covered, at=known_at),
        store_root,
    )
    if not symbols:
        return empty_price_snapshot(
            taken_at=moment,
            source=(
                "no open position in the covered books, so no price was needed"
            ),
        )
    return fetch_price_snapshot(
        symbols,
        taken_at=moment,
        interval=interval,
        limit=limit,
        transport=transport,  # type: ignore[arg-type]
        clock=clock,  # type: ignore[arg-type]
        base_url=base_url,
    )


def run_valuation(
    root: Path | str | None = None,
    *,
    as_of: datetime,
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    base_currency: AssetCode | str = DEFAULT_BASE_CURRENCY,
    books_covered: tuple[Book, ...] = DEFAULT_BOOKS_COVERED,
    classification: ClassificationMap | None = None,
    read_marks: bool = True,
    interval: str = MARK_INTERVAL,
    limit: int = MARK_CANDLE_LIMIT,
    transport: object | None = None,
    clock: object | None = None,
    base_url: str | None = None,
    known_at: datetime | None = None,
) -> PortfolioValuation:
    """One portfolio valuation end to end: fetch the prices, fold the store.

    ``read_marks=False`` skips the network entirely. The page still renders, and
    every figure that needed a price says so with the reason attached.

    Raises:
        PortfolioStoreError: the store exists and cannot be read.
        DomainValidationError: an argument is malformed. Raised rather than
            wrapped, because a typo in a flag is not a broken store.
    """
    moment = require_utc(as_of, "as_of")
    # Validated **before** the guarded read below, not inside it. A malformed
    # asset code or portfolio id raises `DomainValidationError`, which is a
    # `TradeDomainError` — the same family a corrupt payload raises — so leaving
    # it to `_guarded` reported *"the store could not be read"* for a typo in a
    # command-line flag, and sent the owner looking at their store files.
    identifier = require_pattern(portfolio_id, IDENTIFIER_PATTERN, "portfolio_id")
    asset = (
        base_currency
        if isinstance(base_currency, AssetCode)
        else AssetCode(base_currency)
    )
    store_root = default_store_root() if root is None else Path(root)
    prices = (
        marks_for_store(
            store_root,
            taken_at=moment,
            books_covered=books_covered,
            interval=interval,
            limit=limit,
            transport=transport,
            clock=clock,
            base_url=base_url,
            known_at=known_at,
        )
        if read_marks
        else empty_price_snapshot(taken_at=moment, source=NO_SOURCE_CONSULTED)
    )
    store = TradingStore(store_root, dust=VALUATION_DUST_POLICY)
    return _guarded(
        lambda: value_portfolio(
            store,
            portfolio_id=identifier,
            base_currency=asset,
            as_of=moment,
            prices=prices,
            books_covered=books_covered,
            classification=classification,
            known_at=known_at,
        ),
        store_root,
    )


def _guarded(read: Any, root: Path) -> Any:
    """Run a store read, turning an unreadable store into this package's error.

    Both families are caught, and the second is not redundant: a hand-edited
    index row or a payload written by a newer build fails the **domain's** own
    decoder (`PayloadDecodeError`, a `TradeDomainError`) long before any
    store-level check runs. `fmis.today.read_store` records the same finding —
    catching only `PersistenceError` let that escape as an unhandled traceback.
    """
    try:
        return read()
    except (PersistenceError, TradeDomainError) as error:
        raise PortfolioStoreError(
            f"the store at {root} could not be read: "
            f"{type(error).__name__}: {error}"
        ) from error
