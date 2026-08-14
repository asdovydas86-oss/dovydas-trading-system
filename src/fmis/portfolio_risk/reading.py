"""The composition root: a `TradingStore` in, a `PortfolioState` out.

**The only module in this package that touches persistence**, and it introduces
no store of its own. Every record it reads comes through a BI repository —
`store.ledger`, `store.plans`, `store.portfolios`, `store.risk` — and it writes
nothing at all. A guard test asserts this module names no write verb, for the
reason `fmis.trade_capture.views` gives for the same rule: a read path that
repaired something would make the store's contents depend on who looked at them.

**The fills are read through the resolver, never raw.** `LedgerRepository`
returns `ResolvedTrade`, a token this layer cannot construct, so a portfolio can
never be built from a value the owner has already corrected.

**Positions are folded one account at a time, and the consequence is on the
page.** A `Position` is keyed by `(market, book)` and holds no account, because a
book never shares capacity across accounts. A *portfolio* must report exposure per
account and per venue, so this module groups the resolved fills by account and
folds each group — the operation `PositionRepository.load_by_owner` already
sanctions (*"account narrows which trades are folded"*). Where a market's fills
sit in more than one account, the per-account fold and the book-wide fold answer
different questions, and `PortfolioState.accounts_share_a_market` names every
market where that is true rather than leaving a reader to discover it.

**A stop comes from a commitment or it does not exist.** The fills that folded
into a position carry `plan_id`; this module resolves those to `TradePlan`s and
uses `initial_invalidation` when exactly one distinct stop is found. Two
commitments with two different stops folding into one position produce
`Absent(reason)` naming both, never the first, the newest or an average — a
position whose risk is computed against a stop the owner did not set for it is
worse than a position with no risk figure at all.

**Nothing is fabricated when a mark is missing.** This package reaches no venue
and ingests no price. `marks` is an argument; an empty one is the honest state of
this build, and every exposure figure then reports `Absent` with the markets
named.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from fmis.accounts import AccountId, Book
from fmis.ledger import ResolvedTrade
from fmis.money import AssetCode, Money
from fmis.persistence import TradingStore
from fmis.plan import TradePlan
from fmis.portfolio import MarkQuote, PortfolioSnapshot
from fmis.positions import Position, PositionDirection, fold_positions
from fmis.provenance import Absent
from fmis.records import require_text, require_utc
from fmis.risk import RiskBudget

from fmis.portfolio_risk.classification import ClassificationMap, unclassified_map
from fmis.portfolio_risk.exposure import DEFAULT_BOOKS_COVERED, build_state
from fmis.portfolio_risk.models import (
    ExposureLine,
    ExposureSource,
    PendingCommitment,
    PortfolioState,
)

__all__ = [
    "UNCLASSIFIED_VERSION",
    "read_exposure_lines",
    "read_pending",
    "read_equity_and_cash",
    "read_portfolio",
    "budget_in_force",
]

#: The classification version a caller who supplies none is reading under. Named
#: rather than blank, so the day the owner writes a taxonomy the two readings are
#: visibly different rather than one silently replacing the other.
UNCLASSIFIED_VERSION = "no-classification-v1"


def _require_store(store: object) -> TradingStore:
    if not isinstance(store, TradingStore):
        raise TypeError(f"store must be a TradingStore, got {type(store).__name__}")
    return store


def _by_account(
    resolved: Sequence[ResolvedTrade],
) -> dict[AccountId, list[ResolvedTrade]]:
    grouped: dict[AccountId, list[ResolvedTrade]] = {}
    for entry in resolved:
        grouped.setdefault(entry.trade.account, []).append(entry)
    return grouped


def _plan_ids_behind(
    position: Position, resolved: Sequence[ResolvedTrade]
) -> tuple[str, ...]:
    """Which commitments the fills in one position were recorded against."""
    wanted = set(position.event_ids)
    found = {
        entry.trade.plan_id
        for entry in resolved
        if entry.event_id in wanted and not isinstance(entry.trade.plan_id, Absent)
    }
    return tuple(sorted(found))


def _stop_for(
    position: Position,
    resolved: Sequence[ResolvedTrade],
    plans: Mapping[str, TradePlan],
) -> object:
    """The stop this position is measured against, or the reason there is none.

    One distinct level or nothing. A position folded from two commitments with two
    different stops has no single risk distance, and picking either would report a
    number the owner never committed to.
    """
    plan_ids = _plan_ids_behind(position, resolved)
    if not plan_ids:
        return Absent(
            f"no commitment is recorded against the fills in "
            f"{position.market.value} ({position.book.value}); a stop is what a "
            "TradePlan states, and none of these fills names one"
        )
    known = [plans[plan_id] for plan_id in plan_ids if plan_id in plans]
    missing = [plan_id for plan_id in plan_ids if plan_id not in plans]
    if missing:
        return Absent(
            f"the fills in {position.market.value} ({position.book.value}) name "
            f"commitment(s) this store does not hold: {', '.join(missing)}"
        )
    stops = sorted({plan.initial_invalidation for plan in known})
    if len(stops) > 1:
        return Absent(
            f"{len(known)} commitments fold into {position.market.value} "
            f"({position.book.value}) with different stops "
            f"({', '.join(str(stop) for stop in stops)}); no single risk distance "
            "exists, and choosing one would report a level the owner did not set "
            "for this exposure"
        )
    return stops[0]


def read_exposure_lines(
    store: TradingStore,
    *,
    books_covered: tuple[Book, ...] = DEFAULT_BOOKS_COVERED,
    marks: Mapping[str, MarkQuote] | None = None,
    at: datetime | None = None,
) -> tuple[ExposureLine, ...]:
    """Every open position in the store, as portfolio exposure lines.

    `at` reconstructs what the store *knew* at a past instant rather than what
    happened by then — the `written_at` axis, which is what makes a past portfolio
    reading reproducible after a correction is filed.
    """
    trading = _require_store(store)
    supplied = {} if marks is None else dict(marks)
    for key, quote in supplied.items():
        if not isinstance(quote, MarkQuote):
            raise TypeError(f"the mark for {key!r} must be a MarkQuote")
    resolved = (
        trading.ledger.resolved()
        if at is None
        else trading.ledger.resolved_as_known_at(require_utc(at, "at"))
    )
    plans = {plan.plan_id: plan for plan in trading.plans.plans()}
    lines: list[ExposureLine] = []
    for account, group in sorted(
        _by_account(resolved).items(), key=lambda item: item[0].value
    ):
        for position in fold_positions(group, dust=trading.dust):
            if not position.is_open or position.book not in books_covered:
                continue
            if position.direction is PositionDirection.FLAT:  # pragma: no cover
                continue
            entry = position.average_entry.per_unit
            lines.append(
                ExposureLine(
                    account=account,
                    market=position.market,
                    book=position.book,
                    direction=position.direction,
                    quantity=abs(position.net_quantity),
                    source=ExposureSource.HELD,
                    entry=entry,
                    stop=_stop_for(position, group, plans),  # type: ignore[arg-type]
                    mark=supplied.get(
                        position.market.value,
                        Absent(
                            f"no mark was supplied for {position.market.value}; "
                            "this build reaches no venue and ingests no price"
                        ),
                    ),
                    origin_ids=position.event_ids,
                )
            )
    return tuple(lines)


def read_pending(
    store: TradingStore,
    *,
    books_covered: tuple[Book, ...] = DEFAULT_BOOKS_COVERED,
    at: datetime | None = None,
) -> tuple[PendingCommitment, ...]:
    """Commitments with no live fill against them, in the covered books.

    A commitment the owner made and has not acted on is a real portfolio fact —
    and the one whose capital consumption is not derivable, because a `TradePlan`
    states no intended size.
    """
    trading = _require_store(store)
    resolved = (
        trading.ledger.resolved()
        if at is None
        else trading.ledger.resolved_as_known_at(require_utc(at, "at"))
    )
    filled = {
        entry.trade.plan_id
        for entry in resolved
        if not isinstance(entry.trade.plan_id, Absent)
    }
    return tuple(
        PendingCommitment(
            plan_id=plan.plan_id,
            market=plan.market,
            book=plan.book,
            direction=plan.direction,
            stop=plan.initial_invalidation,
            committed_at=plan.committed_at,
        )
        for plan in trading.plans.plans()
        if plan.book in books_covered and plan.plan_id not in filled
    )


def read_equity_and_cash(
    store: TradingStore, *, portfolio_id: str, base_currency: AssetCode
) -> tuple[object, object, object]:
    """Equity, cash and **the instant they were true**, from the latest snapshot.

    Three values rather than two, and the third is the one a reader is entitled
    to. A snapshot taken six weeks ago is a perfectly good record and a poor
    description of today's equity, and every percent-of-equity limit is measured
    against it — so the valuation instant travels with the figures rather than
    being inferred from the fact that a reading happened now.

    **Read, never derived.** A `PortfolioSnapshot` is the only place a valued
    observation of this portfolio lives, and its `total_value` already refuses to
    produce a partial total. If no snapshot has been taken, both are
    `Absent(reason)` — never the sum of what happens to be recorded, and never
    zero.
    """
    trading = _require_store(store)
    wanted = require_text(portfolio_id, "portfolio_id")
    snapshot = trading.portfolios.latest(wanted)
    if snapshot is None:
        reason = Absent(
            f"no portfolio snapshot has been taken for {wanted!r}. A balance this "
            "system has not observed is not a zero balance"
        )
        return reason, reason, Absent(reason.reason)
    return (
        _equity_of(snapshot, base_currency),
        _cash_of(snapshot, base_currency),
        snapshot.as_of,
    )


def _equity_of(snapshot: PortfolioSnapshot, base: AssetCode) -> object:
    if snapshot.base_currency != base:
        return Absent(
            f"the latest snapshot is denominated in {snapshot.base_currency} and "
            f"this reading is in {base}; no rate between them was supplied"
        )
    return snapshot.total_value()


def _cash_of(snapshot: PortfolioSnapshot, base: AssetCode) -> object:
    if snapshot.base_currency != base:
        return Absent(
            f"the latest snapshot is denominated in {snapshot.base_currency} and "
            f"this reading is in {base}; no rate between them was supplied"
        )
    total = Money.zero(base)
    for balance in snapshot.cash:
        value = balance.value_in_base(base)
        if isinstance(value, Absent):
            return value
        total = total + value
    return total


def budget_in_force(
    store: TradingStore, budget_id: str, *, at: datetime
) -> RiskBudget | Absent:
    """The owner's limit generation in force at an instant — the store's own fold.

    Forwarded rather than reimplemented. `RiskRepository.in_force_at` already
    returns `Absent` when nothing was in force, and *"no budget existed"* and
    *"the first budget applied"* are different facts a caller must be able to tell
    apart before evaluating a trade against limits nobody had set.
    """
    return _require_store(store).risk.in_force_at(
        require_text(budget_id, "budget_id"), require_utc(at, "at")
    )


def read_portfolio(
    store: TradingStore,
    *,
    portfolio_id: str,
    base_currency: AssetCode,
    as_of: datetime,
    books_covered: tuple[Book, ...] = DEFAULT_BOOKS_COVERED,
    marks: Mapping[str, MarkQuote] | None = None,
    classification: ClassificationMap | None = None,
    equity: Money | Absent | None = None,
    cash: Money | Absent | None = None,
    known_at: datetime | None = None,
) -> PortfolioState:
    """The whole portfolio, read from the store and folded on demand.

    `equity` and `cash` override what the latest snapshot says, for a caller who
    knows a figure this store has not observed. Supplying neither reads the
    snapshot; supplying `Absent(reason)` states plainly that the figure is not
    known, which is a different and equally legitimate answer.
    """
    trading = _require_store(store)
    asset = (
        base_currency
        if isinstance(base_currency, AssetCode)
        else AssetCode(base_currency)
    )
    moment = require_utc(as_of, "as_of")
    read_equity, read_cash, valued_at = (
        read_equity_and_cash(
            trading, portfolio_id=portfolio_id, base_currency=asset
        )
        if equity is None or cash is None
        else (
            None,
            None,
            Absent(
                "the caller supplied equity and cash directly and stated no "
                "instant for them"
            ),
        )
    )
    return build_state(
        portfolio_id=portfolio_id,
        base_currency=asset,
        as_of=moment,
        lines=read_exposure_lines(
            trading, books_covered=books_covered, marks=marks, at=known_at
        ),
        pending=read_pending(trading, books_covered=books_covered, at=known_at),
        equity=read_equity if equity is None else equity,  # type: ignore[arg-type]
        cash=read_cash if cash is None else cash,  # type: ignore[arg-type]
        classification=(
            unclassified_map(UNCLASSIFIED_VERSION)
            if classification is None
            else classification
        ),
        books_covered=books_covered,
        equity_as_of=valued_at,  # type: ignore[arg-type]
    )
