"""What a marked portfolio is: positions with prices, and the totals over them.

Two shapes. `MarkedPosition` is one open position beside the price it is valued
at; `PortfolioValuation` is every one of them, the `PortfolioState` the risk
engine folded from the same store, and the money figures that only exist once a
mark does.

**Nothing here re-implements an existing calculation.** Market value, gross, net,
long, short and open risk are read off `PortfolioState`, which `fmis.portfolio_risk`
already computes from the same marks — a second implementation would be a second
answer, and the day they disagree neither is checkable. Unrealized profit and
loss is the one figure this module adds, and even that delegates the per-position
arithmetic to `Position.unrealized_pnl` and the totalling rule to
`fmis.portfolio_risk.sum_or_absent`, so *"a partial total is the most dangerous
number a portfolio page can show"* is enforced in one place rather than two.

**Every money figure is `Money` or `Absent(reason)`.** There is no zero standing
in for a missing mark anywhere in this file, and the reason always names the
market that broke the figure.

**Two folds meet here, and the difference is named rather than reconciled.**
`positions` are `PositionRepository`'s book-wide fold — the answer `fmits today`
and `fmits trade show` already print — while `PortfolioState` folds one account
at a time, because a portfolio reports per account and a `Position` holds no
account. The two agree except on the markets `PortfolioState.accounts_share_a_market`
names, and `PortfolioValuation.fold_disagreement` surfaces exactly that list
rather than quietly presenting one number as both.

**Nothing here is stored.** This is a reading, not a record: `AP` §14.3's frozen
observation is `PortfolioSnapshot`, which requires deposits and withdrawals since
the previous snapshot — flows this build records nowhere, because no transfer
event kind exists. `to_payload` is for export and there is deliberately no
decoder, following `PortfolioState`'s own precedent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from fmis.accounts import MarketId
from fmis.marks import PriceSnapshot
from fmis.money import AssetCode, Money
from fmis.portfolio import MarkQuote
from fmis.portfolio_risk import PortfolioState, sum_or_absent
from fmis.positions import Position
from fmis.provenance import Absent, ValueOrigin
from fmis.records import IDENTIFIER_PATTERN, require_pattern, require_utc

from fmis.valuation.marking import CROSS_VENUE_NOTE, MarkSet

__all__ = [
    "VALUATION_LIMITATIONS",
    "MarkedPosition",
    "PortfolioValuation",
]

#: The invariant register. Printed at the foot of every valuation, never beside a
#: figure — the separation `fmis.today` established between what is always true
#: of this page and what is wrong with this run's numbers.
VALUATION_LIMITATIONS: tuple[tuple[str, str], ...] = (
    (
        "VA-1",
        "A valuation is a reading, not a record. Nothing here is stored: a "
        "frozen portfolio observation requires deposits and withdrawals since "
        "the previous one, and no transfer event kind exists in this build, so "
        "every return figure computed from one would be wrong.",
    ),
    (
        "VA-2",
        CROSS_VENUE_NOTE,
    ),
    (
        "VA-3",
        "Equity is cash plus the market value of open positions. Cash is read "
        "from the latest portfolio snapshot the owner took and is never "
        "derived, because no transfer or balance event is recorded anywhere.",
    ),
    (
        "VA-4",
        "Open positions are folded book-wide; portfolio totals are folded one "
        "account at a time. The two answer different questions wherever one "
        "market's fills sit in more than one account, and those markets are "
        "named on this page rather than reconciled behind it.",
    ),
    (
        "VA-5",
        "No position size is proposed, no trade is evaluated and nothing is "
        "ranked. Every limit shown is one the owner set, and every status "
        "beside it is a comparison rather than a conclusion.",
    ),
)


@dataclass(frozen=True, slots=True)
class MarkedPosition:
    """One open position and the price it is valued at, or why it has none.

    A thin pairing on purpose. Every figure below is the `Position`'s own method
    called with this mark — the fold owns the arithmetic and this owns the
    matching, which is the split that keeps a valuation from becoming a second
    position engine.
    """

    position: Position
    mark: MarkQuote | Absent = field(
        default_factory=lambda: Absent("no mark was supplied for this market")
    )

    def __post_init__(self) -> None:
        if not isinstance(self.position, Position):
            raise TypeError(
                f"position must be a Position, got {type(self.position).__name__}"
            )
        if not isinstance(self.mark, (MarkQuote, Absent)):
            raise TypeError("mark must be a MarkQuote or Absent")
        if isinstance(self.mark, MarkQuote):
            if self.mark.quote_asset != self.position.market.quote_asset:
                raise ValueError(
                    f"the mark for {self.position.market.value} is quoted in "
                    f"{self.mark.quote_asset} and the market trades in "
                    f"{self.position.market.quote_asset}; a price in the wrong "
                    "currency is not a cheaper price"
                )

    # -- identity ------------------------------------------------------------

    @property
    def market(self) -> MarketId:
        return self.position.market

    @property
    def quote_asset(self) -> AssetCode:
        return self.position.market.quote_asset

    @property
    def is_marked(self) -> bool:
        return isinstance(self.mark, MarkQuote)

    @property
    def origin(self) -> ValueOrigin:
        """`MEASURED`: a fold over recorded fills, valued at an observed price."""
        return ValueOrigin.MEASURED

    # -- money, or the reason there is none ---------------------------------

    @property
    def _price(self) -> Any:
        return self.mark.price if isinstance(self.mark, MarkQuote) else self.mark

    @property
    def market_value(self) -> Money | Absent:
        """`net quantity × mark`, signed — negative while short.

        The signed form rather than the magnitude, because this figure is
        summed into a portfolio's market value and a short holding reduces what
        the portfolio is worth. `PortfolioState` reports the unsigned gross
        beside it, and the two are different questions.
        """
        if isinstance(self.mark, Absent):
            return Absent(
                f"no mark for {self.market.value}: {self.mark.reason}"
            )
        return self.position.net_quantity.value_at(self.mark.price, self.quote_asset)

    @property
    def cost_basis(self) -> Money | Absent:
        """`net quantity × weighted average entry` — what it was opened at.

        `AverageCost` holds the `(total_cost, total_quantity)` pair and divides
        at read time; a position with no quantity behind it has no per-unit cost
        and `Absent` says so rather than dividing by zero.
        """
        entry = self.position.average_entry.per_unit
        if isinstance(entry, Absent):
            return Absent(
                f"no average entry for {self.market.value}: {entry.reason}"
            )
        return self.position.net_quantity.value_at(entry, self.quote_asset)

    @property
    def unrealized_pnl(self) -> Money | Absent:
        """`(mark − average entry) × net quantity`, from the fold's own method.

        Delegated rather than recomputed. `Position.unrealized_pnl` already
        refuses a closed position, refuses an unmarked one, and carries the sign
        through `net_quantity`; a copy of that logic here would be a second
        answer to the single most-read number on a portfolio page.
        """
        return self.position.unrealized_pnl(self._price, self.quote_asset)

    def mark_age_at(self, moment: datetime) -> timedelta | Absent:
        """How stale this position's price is at an instant, or why that is unknown."""
        if isinstance(self.mark, Absent):
            return Absent(
                f"no mark for {self.market.value}: {self.mark.reason}"
            )
        return self.mark.staleness_at(require_utc(moment, "moment"))

    def to_payload(self) -> dict[str, Any]:
        """For export and rendering. **There is no decoder**, by design."""
        return {
            "market": self.market.to_payload(),
            "book": self.position.book.value,
            "direction": self.position.direction.value,
            "net_quantity": self.position.net_quantity.to_payload(),
            "mark": (
                {"absent": self.mark.to_payload()}
                if isinstance(self.mark, Absent)
                else {"value": self.mark.to_payload()}
            ),
            "market_value": _amount(self.market_value),
            "cost_basis": _amount(self.cost_basis),
            "unrealized_pnl": _amount(self.unrealized_pnl),
        }


@dataclass(frozen=True, slots=True)
class PortfolioValuation:
    """One reading of what the portfolio is worth, and everything it rests on.

    The `PriceSnapshot` and the `MarkSet` are carried, not summarized: a total a
    reader cannot trace back to the prices behind it is a total they have to
    take on faith, and this product's whole discipline is that they never should.
    """

    portfolio_id: str
    base_currency: AssetCode
    as_of: datetime
    state: PortfolioState
    positions: tuple[MarkedPosition, ...]
    marks: MarkSet
    prices: PriceSnapshot
    limitations: tuple[tuple[str, str], ...] = VALUATION_LIMITATIONS

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "portfolio_id",
            require_pattern(self.portfolio_id, IDENTIFIER_PATTERN, "portfolio_id"),
        )
        if not isinstance(self.base_currency, AssetCode):
            object.__setattr__(self, "base_currency", AssetCode(self.base_currency))
        object.__setattr__(self, "as_of", require_utc(self.as_of, "as_of"))
        if not isinstance(self.state, PortfolioState):
            raise TypeError(
                f"state must be a PortfolioState, got {type(self.state).__name__}"
            )
        object.__setattr__(self, "positions", tuple(self.positions))
        for entry in self.positions:
            if not isinstance(entry, MarkedPosition):
                raise TypeError("positions must be MarkedPosition values")
        if not isinstance(self.marks, MarkSet):
            raise TypeError(f"marks must be a MarkSet, got {type(self.marks).__name__}")
        if not isinstance(self.prices, PriceSnapshot):
            raise TypeError("prices must be a PriceSnapshot")
        if self.state.portfolio_id != self.portfolio_id:
            raise ValueError(
                f"the folded state is for portfolio {self.state.portfolio_id!r} "
                f"and this valuation claims {self.portfolio_id!r}"
            )
        if self.state.base_currency != self.base_currency:
            raise ValueError(
                f"the folded state is denominated in {self.state.base_currency} "
                f"and this valuation is in {self.base_currency}"
            )
        object.__setattr__(self, "limitations", tuple(self.limitations))

    # -- the figures ---------------------------------------------------------

    @property
    def origin(self) -> ValueOrigin:
        return ValueOrigin.MEASURED

    @property
    def market_value(self) -> Money | Absent:
        """What the open positions are worth, signed.

        **This is `PortfolioState.net_exposure`, deliberately and by delegation.**
        Net exposure is the sum of signed notionals, which is exactly what a
        portfolio's market value is; computing it twice would give a page two
        numbers for one question and no way to say which was right.
        """
        return self.state.net_exposure

    @property
    def gross_exposure(self) -> Money | Absent:
        return self.state.gross_exposure

    @property
    def long_exposure(self) -> Money | Absent:
        return self.state.long_exposure

    @property
    def short_exposure(self) -> Money | Absent:
        return self.state.short_exposure

    @property
    def open_risk(self) -> Money | Absent:
        """Σ capital at risk. Needs a mark **and** a recorded stop for every line."""
        return self.state.open_risk

    @property
    def cash(self) -> Money | Absent:
        return self.state.cash

    @property
    def cash_as_of(self) -> Any:
        return self.state.equity_as_of

    @property
    def unrealized_pnl(self) -> Money | Absent:
        """Σ per-position unrealized profit and loss, or the reason there is none.

        Totalled through `sum_or_absent`, the one implementation of *"one missing
        input never shrinks a total"* — so an unmarked holding makes this figure
        `Absent` naming that holding, never a smaller number that looks complete.
        """
        return sum_or_absent(
            (entry.unrealized_pnl for entry in self.positions),
            asset=self.base_currency,
            subject="unrealized profit and loss",
        )

    @property
    def cost_basis(self) -> Money | Absent:
        return sum_or_absent(
            (entry.cost_basis for entry in self.positions),
            asset=self.base_currency,
            subject="cost basis",
        )

    @property
    def marked_equity(self) -> Money | Absent:
        """`cash + market value` — what the portfolio is worth right now.

        Distinct from `PortfolioState.equity`, which is the **frozen** total from
        the latest `PortfolioSnapshot` and is as old as that snapshot. This one
        is live in its prices and only as current as its cash, and
        `equity_basis` says so in words so the two are never read as one figure.
        """
        cash = self.cash
        if isinstance(cash, Absent):
            return Absent(f"cash is not known: {cash.reason}")
        value = self.market_value
        if isinstance(value, Absent):
            return Absent(f"market value is not known: {value.reason}")
        return cash + value

    @property
    def equity_basis(self) -> str:
        """One sentence naming what `marked_equity` is and is not."""
        return (
            "equity = cash recorded in the latest portfolio snapshot + the "
            "market value of open positions at this reading's prices. The cash "
            "half is as old as that snapshot; the market half is as old as the "
            "oldest mark."
        )

    # -- coverage and provenance ---------------------------------------------

    @property
    def marked_positions(self) -> tuple[MarkedPosition, ...]:
        return tuple(entry for entry in self.positions if entry.is_marked)

    @property
    def unmarked_positions(self) -> tuple[MarkedPosition, ...]:
        """The positions that broke every total on this page.

        The most useful list here, and the reason a total is `Absent` rather
        than smaller when it is non-empty.
        """
        return tuple(entry for entry in self.positions if not entry.is_marked)

    @property
    def is_fully_marked(self) -> bool:
        return not self.unmarked_positions

    @property
    def unstopped_markets(self) -> tuple[str, ...]:
        """Open exposure no commitment records a stop for — why open risk is absent."""
        return tuple(line.market.value for line in self.state.unstopped)

    @property
    def fold_disagreement(self) -> tuple[str, ...]:
        """Markets where the book-wide and per-account folds answer differently."""
        return self.state.accounts_share_a_market

    @property
    def mark_age(self) -> timedelta | Absent:
        """The age of the **oldest** mark — what a total's freshness is bounded by.

        Not an average. An average staleness lets one six-hour-old holding
        disappear behind nine fresh ones, and it is the stale one that makes a
        total wrong.
        """
        oldest = self.prices.oldest_reading()
        if oldest is None:
            return Absent(
                f"this reading priced nothing ({self.prices.source}), so no mark "
                "has an age"
            )
        return oldest.age_at(self.as_of)

    @property
    def price_provenance(self) -> tuple[str, ...]:
        """One line per priced market: which price, from where, chosen how."""
        return tuple(
            f"{market} ← {quote.source}"
            for market, quote in sorted(self.marks.quotes.items())
        )

    def to_payload(self) -> dict[str, Any]:
        """For export and rendering. **There is no decoder**, by design."""
        return {
            "portfolio_id": self.portfolio_id,
            "base_currency": self.base_currency.code,
            "as_of": self.as_of.isoformat(),
            "prices": self.prices.to_payload(),
            "positions": [entry.to_payload() for entry in self.positions],
            "market_value": _amount(self.market_value),
            "cost_basis": _amount(self.cost_basis),
            "unrealized_pnl": _amount(self.unrealized_pnl),
            "cash": _amount(self.cash),
            "marked_equity": _amount(self.marked_equity),
            "gross_exposure": _amount(self.gross_exposure),
            "long_exposure": _amount(self.long_exposure),
            "short_exposure": _amount(self.short_exposure),
            "open_risk": _amount(self.open_risk),
            "unmarked": [
                entry.market.value for entry in self.unmarked_positions
            ],
            "unstopped": list(self.unstopped_markets),
            "fold_disagreement": list(self.fold_disagreement),
            "equity_basis": self.equity_basis,
            "limitations": [
                {"id": code, "statement": text} for code, text in self.limitations
            ],
        }


def _amount(value: Money | Absent) -> dict[str, Any]:
    if isinstance(value, Absent):
        return {"absent": value.to_payload()}
    return {"value": value.to_payload()}
