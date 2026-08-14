"""Price snapshots — one deterministic reading of what a market last traded at.

**This is a market-half package.** It imports `fmis.data` and the standard
library, and nothing else. It holds no `Money`, no `MarkQuote`, no account and no
position, because the moment a price package knows what a portfolio is, the
portfolio's valuation becomes a function of the price package's opinion of it.

Three rules, and each is a guard test rather than an aspiration.

1. **One basis, named.** A price is the close of the **last closed candle** on a
   stated interval — `PriceBasis.LAST_CLOSED_CANDLE_CLOSE`, the only member this
   build has. A forming bar is never read, so two runs over the same history
   produce the same price forever. `IMPLEMENTATION_ROADMAP_V1` §C6 states this
   basis by name as the first concrete answer to the mark-selection question, and
   this package is where that answer lives.
2. **No provider is named here.** Candles arrive as `CandleSeries`; who fetched
   them, from where, and what went wrong is the caller's business. `source` is a
   string this package carries and never interprets, which is what makes a
   TradingView export, a second exchange and a hand-typed price all reachable
   through the same type.
3. **A price that could not be read is a `PriceUnavailable` with a reason, never
   an omission and never a zero.** A snapshot that silently dropped a symbol
   would be indistinguishable from one where that symbol was never asked for,
   and the portfolio built on it would report a smaller total that looked
   complete.

**Nothing here reaches a network, opens a file or reads a clock.** `taken_at` is
an argument. That is what makes a price snapshot reproducible, and a test of one
network-free.
"""

from __future__ import annotations

from fmis.marks.models import (
    PRICE_SNAPSHOT_SCHEMA_VERSION,
    SUPPORTED_PRICE_SNAPSHOT_VERSIONS,
    MarksError,
    PriceBasis,
    PriceReading,
    PriceSnapshot,
    PriceUnavailable,
    PriceUnreadableError,
)
from fmis.marks.service import (
    MARK_BASIS_NOTE,
    build_price_snapshot,
    empty_price_snapshot,
    read_price,
)

__all__ = [
    "MarksError",
    "PriceUnreadableError",
    "PriceBasis",
    "PriceReading",
    "PriceUnavailable",
    "PriceSnapshot",
    "PRICE_SNAPSHOT_SCHEMA_VERSION",
    "SUPPORTED_PRICE_SNAPSHOT_VERSIONS",
    "MARK_BASIS_NOTE",
    "read_price",
    "build_price_snapshot",
    "empty_price_snapshot",
]
