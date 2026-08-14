"""The one crossing: a market-half `PriceReading` becomes an owner-half `MarkQuote`.

This module is the whole of the bridge. Everything above it works in `Money`,
`Quantity` and `MarketId`; everything below it works in candles and floats. One
function converts, and it is the only place in the repository where a price
crosses from one world into the other.

**One float→exact conversion, and it is not this module's own.**
`fmis.money.exact_from_market_price` already exists as *"the one `float` → exact
crossing in the whole domain (AP-D1 Q3)"*, converting through `repr` — the
shortest text that round-trips the float exactly. Re-implementing the conversion
here would create a second answer to a question the money kernel has already
settled, and two answers to *what is this price, exactly* is how two surfaces
come to disagree about a total.

**A symbol is matched to a market by its pair symbol, and the substitution that
implies is stated rather than hidden.** `MarketId.pair_symbol` is documented as
*"the venue-facing symbol, for reaching the market half"*; it carries no venue.
So a holding recorded at one venue can be priced from another venue's candles,
and the fact travels on `MarkQuote.source` — every figure derived from it names
where its price came from. `CROSS_VENUE_NOTE` is the sentence a surface prints.

**A non-spot market is refused rather than approximated.** A perpetual and its
spot pair share a symbol and are two instruments with two prices; pricing one
from the other would substitute an instrument's price for a different
instrument's and call the result a valuation. `fmis.portfolio_risk.exposure`
already refuses to state deployed capital for a margined market for the mirror
reason, and this is the same refusal one step earlier.

**This module names no venue.** It branches on `MarketMode`, a domain enum, and
on nothing else. A guard test asserts the whole package spells no exchange.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from fmis.accounts import MarketId, MarketMode
from fmis.marks import PriceReading, PriceSnapshot
from fmis.money import exact_from_market_price
from fmis.portfolio import MarkQuote

__all__ = [
    "CROSS_VENUE_NOTE",
    "MARKABLE_MODES",
    "MarkSet",
    "ValuationError",
    "PortfolioStoreError",
    "MarkMismatchError",
    "mark_from_reading",
    "symbols_for_markets",
    "marks_for_markets",
]


class ValuationError(Exception):
    """Base class for every failure this package raises."""


class PortfolioStoreError(ValuationError):
    """The store exists and could not be read.

    Defined here rather than left to `fmis.persistence`'s own hierarchy for the
    reason `fmis.today.StoreUnreadableError` exists: `fmis.pipeline.cli` is a
    market-half module and **may not import the store**, so it cannot catch a
    store exception it has no name for. Wrapping at this boundary is what lets
    the CLI report a corrupt store as a message instead of a traceback.

    A *missing* store is not this. `fmis.persistence` treats an absent line file
    as emptiness, and a valuation of a machine that has never recorded a trade
    is a complete page saying so — not a failure.
    """


class MarkMismatchError(ValuationError, ValueError):
    """A reading was offered for a market it does not describe.

    A caller error rather than a data condition: matching a reading to a market
    is this module's job, so a mismatch reaching `mark_from_reading` means the
    caller paired them by hand and paired them wrong. Silently accepting it
    would value one holding at another's price.
    """


#: The market modes this build can price. Spot only, and the exclusion is a
#: refusal rather than an omission — see the module docstring.
MARKABLE_MODES: frozenset[MarketMode] = frozenset({MarketMode.SPOT})

#: Printed wherever a marked figure appears. The substitution is real, it is
#: unavoidable while one price source exists, and a reader is entitled to see it
#: named rather than to discover it from a `MarkQuote.source` they did not read.
CROSS_VENUE_NOTE = (
    "A holding is matched to a price by its pair symbol, which carries no venue. "
    "A market held somewhere other than the price source is therefore priced by "
    "substitution, and every figure derived from it names its price source."
)


@dataclass(frozen=True, slots=True)
class MarkSet:
    """Marks for the markets that could be priced, and reasons for the rest.

    Keyed by `MarketId.value` — the citation form, venue and mode included —
    because that is the key `fmis.portfolio_risk.read_exposure_lines` looks a
    mark up by. Two markets that share a pair symbol are two keys here, and that
    is the point: a spot holding and a perpetual holding are never handed one
    another's price.

    **The two halves are exhaustive over what was asked for.** Every market
    passed in appears in exactly one of them, so a caller can never mistake *"not
    priced"* for *"not asked about"*.
    """

    quotes: Mapping[str, MarkQuote]
    reasons: Mapping[str, str]

    def __post_init__(self) -> None:
        for name in ("quotes", "reasons"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise TypeError(f"{name} must be a mapping")
            object.__setattr__(self, name, dict(value))
        shared = set(self.quotes) & set(self.reasons)
        if shared:
            raise ValueError(
                f"{sorted(shared)} is both priced and unpriced; one market has a "
                "mark or a reason, never both"
            )

    @property
    def marked_count(self) -> int:
        return len(self.quotes)

    @property
    def unmarked_count(self) -> int:
        return len(self.reasons)

    @property
    def requested_count(self) -> int:
        return self.marked_count + self.unmarked_count

    @property
    def is_complete(self) -> bool:
        """Whether every market asked about was priced.

        The condition under which a portfolio's totals can be money rather than
        `Absent`. Named so a surface states it rather than inferring it from a
        total that happened to come out.
        """
        return not self.reasons

    def reason_for(self, market: MarketId | str) -> str | None:
        key = market.value if isinstance(market, MarketId) else market
        return self.reasons.get(key)


def mark_from_reading(reading: PriceReading, *, market: MarketId) -> MarkQuote:
    """One market-half reading as one owner-half mark. The crossing, in full.

    Args:
        reading: a price read from closed candles.
        market: the market it prices. Its `quote_asset` becomes the mark's, and
            its `pair_symbol` must equal the reading's symbol.

    Raises:
        TypeError: an argument is of the wrong type.
        MarkMismatchError: the reading does not describe this market, or this
            market's mode is one this build refuses to price.
    """
    if not isinstance(reading, PriceReading):
        raise TypeError(
            f"reading must be a PriceReading, got {type(reading).__name__}"
        )
    if not isinstance(market, MarketId):
        raise TypeError(f"market must be a MarketId, got {type(market).__name__}")
    if reading.symbol.upper() != market.pair_symbol.upper():
        raise MarkMismatchError(
            f"the reading is for {reading.symbol} and the market is "
            f"{market.value}, whose pair symbol is {market.pair_symbol}; pricing "
            "one market from another's candles is a substitution this function "
            "will not make silently"
        )
    if market.mode not in MARKABLE_MODES:
        raise MarkMismatchError(
            f"{market.value} is a {market.mode.value} market and this build reads "
            f"{sorted(mode.value for mode in MARKABLE_MODES)} candles only; a "
            "perpetual and its spot pair share a symbol and are two instruments "
            "with two prices, and valuing one at the other's price is not a "
            "valuation"
        )
    return MarkQuote(
        price=exact_from_market_price(reading.price, f"{reading.symbol} price"),
        quote_asset=market.quote_asset,
        source=reading.provenance,
        as_of=reading.observed_at,
    )


def symbols_for_markets(markets: Iterable[MarketId]) -> tuple[str, ...]:
    """The provider symbols a set of markets needs, deduplicated, in order.

    Two markets differing only in venue or mode need one fetch, because a price
    source is asked for a symbol and knows nothing of either. Order is
    first-seen rather than sorted, so a fetch sequence is reproducible without
    being reordered behind the caller's back.
    """
    found: list[str] = []
    for market in markets:
        if not isinstance(market, MarketId):
            raise TypeError(
                f"markets must be MarketId values, got {type(market).__name__}"
            )
        symbol = market.pair_symbol
        if symbol not in found:
            found.append(symbol)
    return tuple(found)


def marks_for_markets(
    snapshot: PriceSnapshot, markets: Iterable[MarketId]
) -> MarkSet:
    """Match a price snapshot to a set of markets, naming every failure.

    Four ways a market goes unpriced, and each carries its own sentence:

    * the snapshot holds a recorded failure for its symbol,
    * the snapshot was never asked for its symbol,
    * its mode is one this build refuses to price,
    * the reading and the market disagree — which cannot happen through this
      function and is caught anyway, because a defence that is never exercised
      is a defence that stops working unnoticed.
    """
    if not isinstance(snapshot, PriceSnapshot):
        raise TypeError(
            f"snapshot must be a PriceSnapshot, got {type(snapshot).__name__}"
        )
    quotes: dict[str, MarkQuote] = {}
    reasons: dict[str, str] = {}
    for market in markets:
        if not isinstance(market, MarketId):
            raise TypeError(
                f"markets must be MarketId values, got {type(market).__name__}"
            )
        key = market.value
        if key in quotes or key in reasons:
            continue
        if market.mode not in MARKABLE_MODES:
            reasons[key] = (
                f"{key} is a {market.mode.value} market; this build prices "
                f"{sorted(mode.value for mode in MARKABLE_MODES)} markets only, "
                "because a perpetual and its spot pair are two instruments with "
                "two prices"
            )
            continue
        reading = snapshot.reading_for(market.pair_symbol)
        if reading is None:
            recorded = snapshot.reason_for(market.pair_symbol)
            reasons[key] = (
                f"no price was read for {market.pair_symbol}: {recorded}"
                if recorded is not None
                else (
                    f"{market.pair_symbol} was not among the "
                    f"{snapshot.requested_count} symbol(s) this price snapshot "
                    f"covers ({snapshot.source})"
                )
            )
            continue
        try:
            quotes[key] = mark_from_reading(reading, market=market)
        except MarkMismatchError as error:  # pragma: no cover - defence in depth
            reasons[key] = str(error)
    return MarkSet(quotes=quotes, reasons=reasons)
