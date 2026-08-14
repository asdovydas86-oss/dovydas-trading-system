"""Portfolio valuation — the bridge between the market half and the owner half.

Before this package, `fmis.portfolio_risk` could compute every exposure figure a
portfolio has and reported all of them as `Absent`, because **no mark source
reached the owner half**. `fmis.marks` reads a price; this package is the one
place that price becomes a `MarkQuote` and reaches a position.

    fmis.marks             PriceSnapshot   (candles, floats, no venue named)
      -> fmis.valuation    MarkQuote       (the one crossing — `marking.py`)
      -> fmis.portfolio_risk               (exposure, open risk, constraints)

**This is the second package in the repository that reads both halves**, after
`fmis.today`, and the *conversion* is exactly one module wide: `marking.py` is
the only place in the repository that turns a price into a `MarkQuote`, and a
guard test asserts that by checking who may construct one rather than who may
import what. Three sibling modules carry a `PriceSnapshot` — as a field, as an
argument, as a fetch result — and none of them opens it. Guards run in both
directions: no engine, no domain package and no store module imports
`fmis.valuation`, and the four modules that touch `fmis.marks` are pinned as a
set so widening the surface is a visible edit.

**No adapter lives in the owner domain.** `fmis.portfolio_risk`'s dependency
surface is unchanged and its venue-agnostic guard still passes: it receives a
`Mapping[str, MarkQuote]` and knows nothing about where one came from. This
package names no exchange either — the provider is reached through
`fmis.pipeline.prices`, which is where every other provider call in this
repository already lives.

**No pricing logic is duplicated.** Market value delegates to
`PortfolioState.net_exposure`, unrealized profit and loss to
`Position.unrealized_pnl`, the float→exact conversion to
`fmis.money.exact_from_market_price`, and the *"a partial total is the most
dangerous number a portfolio page can show"* rule to
`fmis.portfolio_risk.sum_or_absent`. This package adds matching and provenance,
not arithmetic.

**Every mark carries where it came from and how old it is**, and every figure
that could not be computed carries the market that broke it. There is no zero
standing in for a missing price anywhere in this package.

**Nothing here is stored, and that is a decision rather than an omission.** `AP`
§14.3's frozen observation is a `PortfolioSnapshot`, which requires deposits and
withdrawals since the previous one; this build records no transfer event, so a
snapshot written now would carry flows nobody could state and every return figure
derived from it would be wrong. A valuation is a rebuildable reading until that
gap closes.
"""

from __future__ import annotations

from fmis.valuation.compose import (
    DEFAULT_BASE_CURRENCY,
    DEFAULT_PORTFOLIO_ID,
    VALUATION_DUST_POLICY,
    marks_for_store,
    run_valuation,
)
from fmis.valuation.marking import (
    CROSS_VENUE_NOTE,
    MARKABLE_MODES,
    MarkMismatchError,
    MarkSet,
    PortfolioStoreError,
    ValuationError,
    mark_from_reading,
    marks_for_markets,
    symbols_for_markets,
)
from fmis.valuation.models import (
    VALUATION_LIMITATIONS,
    MarkedPosition,
    PortfolioValuation,
)
from fmis.valuation.reading import (
    marked_positions,
    markets_to_price,
    open_positions_in,
    symbols_to_price,
    value_portfolio,
)
from fmis.valuation.render import render_valuation

__all__ = [
    # errors
    "ValuationError",
    "PortfolioStoreError",
    "MarkMismatchError",
    # the crossing
    "CROSS_VENUE_NOTE",
    "MARKABLE_MODES",
    "MarkSet",
    "mark_from_reading",
    "symbols_for_markets",
    "marks_for_markets",
    # the reading
    "VALUATION_LIMITATIONS",
    "MarkedPosition",
    "PortfolioValuation",
    "open_positions_in",
    "markets_to_price",
    "symbols_to_price",
    "marked_positions",
    "value_portfolio",
    # the outer edge
    "DEFAULT_PORTFOLIO_ID",
    "DEFAULT_BASE_CURRENCY",
    "VALUATION_DUST_POLICY",
    "marks_for_store",
    "run_valuation",
    # rendering
    "render_valuation",
]
