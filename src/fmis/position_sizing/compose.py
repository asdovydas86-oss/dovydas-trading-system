"""The outer edge: open the store, price the book, size the candidate, check it.

    run_approval(root, proposal=..., ...)  ──►  ApprovalResult

**Everything that touches a network or a filesystem lives here**, so
`policy`, `models`, `sizing` and `approval` stay pure and every rule in them is
testable without either. This is the same split `fmis.valuation.compose` and
`fmis.today.builder` already make, and it exists for the same reason.

**The portfolio is read through `fmis.valuation`, not re-read here.**
`run_valuation` already opens the store, fetches one price per open market, folds
the positions one account at a time and returns the exact `PortfolioState` an
approval needs — plus `mark_age`, the age of the *oldest* mark, which is the only
staleness figure a total's freshness is actually bounded by. Re-implementing that
chain would give the product two portfolios: the one `fmits portfolio` prints and
the one `fmits approve` decided against, with no way to say which was right.

**A missing risk budget is a refusal, not an approval.** With no limits recorded
there is nothing to approve *against*, and returning `APPROVED` would mean
*"nothing you set was breached"* in a system where the owner has set nothing. The
command says so and names the gap.

**The owner's timezone is a locale, not a threshold.** `OwnerContext` exists so a
period limit resets on the owner's own calendar rather than on UTC's, and
`fmis.risk` states the case directly: *"a 'daily loss limit' measured on UTC days
for a Stockholm-based owner would reset in the middle of his evening."*
`DEFAULT_OWNER_TIMEZONE` names that owner rather than leaving the boundary
undefined, and every command that reaches here accepts a flag to change it.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fmis.accounts import AccountId, Book, OwnerContext
from fmis.money import AssetCode
from fmis.persistence import PersistenceError, TradingStore, default_store_root
from fmis.pipeline.prices import MARK_CANDLE_LIMIT, MARK_INTERVAL
from fmis.portfolio_risk import (
    DEFAULT_BOOKS_COVERED,
    ClassificationMap,
    unclassified_map,
)
from fmis.provenance import Absent
from fmis.records import TradeDomainError, require_utc
from fmis.valuation import (
    DEFAULT_BASE_CURRENCY,
    DEFAULT_PORTFOLIO_ID,
    VALUATION_DUST_POLICY,
    PortfolioStoreError,
    PortfolioValuation,
    run_valuation,
)

from fmis.position_sizing.approval import ApprovalEngine
from fmis.position_sizing.models import (
    ApprovalResult,
    PositionProposal,
    PositionSizingError,
)
from fmis.position_sizing.policy import SizingPolicy
from fmis.position_sizing.reading import (
    budget_in_effect,
    plan_to_size,
    sole_account,
)
from fmis.position_sizing.sizing import PositionSizer

__all__ = [
    "DEFAULT_OWNER_TIMEZONE",
    "DEFAULT_BOOK",
    "APPROVAL_CLASSIFICATION_VERSION",
    "ApprovalUnavailableError",
    "owner_context",
    "engine_for",
    "portfolio_for",
    "resolve_account",
    "proposal_for_plan",
    "run_approval",
]

#: Where the owner's calendar boundaries fall. A locale rather than a threshold:
#: it decides when a *day* ends for a daily limit and nothing else, and no figure
#: on any page changes with it except the bucket a periodic limit is measured
#: over. `AP` §22 records the owner as Swedish-taxed and `fmis.risk` names the
#: same city when explaining why this field exists at all.
DEFAULT_OWNER_TIMEZONE = "Europe/Stockholm"

#: Which capacity pool a candidate consumes when the owner names none. `SWING` is
#: the objective `fmis.today` already declares for its whole page, and books never
#: share capacity — so a default that guessed differently would size against the
#: wrong pool while looking entirely correct.
DEFAULT_BOOK = Book.SWING

#: The classification version an approval is computed under when the owner has
#: written no taxonomy. Named rather than blank, so the day they write one the two
#: readings are visibly different rather than one silently replacing the other.
APPROVAL_CLASSIFICATION_VERSION = "no-classification-v1"


class ApprovalUnavailableError(PositionSizingError):
    """The approval could not be produced at all, and the reason is actionable.

    Distinct from `BLOCKED`, which is an approval that *was* produced. This is
    raised when a precondition of the whole evaluation is missing — no risk
    budget recorded, no account resolvable — and every message names what the
    owner must record to make the command work. A refusal the owner cannot act on
    is the same as a crash.
    """


def owner_context(
    *, base_currency: AssetCode | str, timezone: str = DEFAULT_OWNER_TIMEZONE
) -> OwnerContext:
    """The owner's calendar and reporting currency, in the domain's own type."""
    return OwnerContext(
        display_timezone=timezone,
        base_currency=(
            base_currency
            if isinstance(base_currency, AssetCode)
            else AssetCode(base_currency)
        ),
        tax_period_timezone=timezone,
    )


def engine_for(
    policy: SizingPolicy, classification: ClassificationMap | None = None
) -> ApprovalEngine:
    """One engine, configured once, for every candidate a surface evaluates.

    A surface that built a fresh engine per candidate could size two rows on one
    page under two different rules, and nothing on the page would say so.
    """
    return ApprovalEngine(
        sizer=PositionSizer(policy),
        classification=(
            unclassified_map(APPROVAL_CLASSIFICATION_VERSION)
            if classification is None
            else classification
        ),
    )


def portfolio_for(
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
    """The portfolio an approval is measured against — priced, folded, and dated.

    Delegated whole to `fmis.valuation.run_valuation`, which is the reason this
    function is three lines and not three hundred. Its `PortfolioValuation`
    carries the `PortfolioState` the constraint engine needs *and* the oldest
    mark's age the staleness check needs, both produced by the same read.
    """
    return run_valuation(
        root,
        as_of=as_of,
        portfolio_id=portfolio_id,
        base_currency=base_currency,
        books_covered=books_covered,
        classification=classification,
        read_marks=read_marks,
        interval=interval,
        limit=limit,
        transport=transport,
        clock=clock,
        base_url=base_url,
        known_at=known_at,
    )


def run_approval(
    root: Path | str | None = None,
    *,
    proposal: PositionProposal,
    as_of: datetime,
    policy: SizingPolicy,
    portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    base_currency: AssetCode | str = DEFAULT_BASE_CURRENCY,
    books_covered: tuple[Book, ...] = DEFAULT_BOOKS_COVERED,
    classification: ClassificationMap | None = None,
    timezone: str = DEFAULT_OWNER_TIMEZONE,
    read_marks: bool = True,
    interval: str = MARK_INTERVAL,
    limit: int = MARK_CANDLE_LIMIT,
    transport: object | None = None,
    clock: object | None = None,
    base_url: str | None = None,
    known_at: datetime | None = None,
) -> ApprovalResult:
    """One candidate, evaluated end to end against the owner's recorded portfolio.

    ``read_marks=False`` skips the network entirely. The evaluation still runs
    and comes back `INDETERMINATE`, naming every position that could not be
    priced — which is the honest answer, and a different one from a failed fetch.

    Raises:
        ApprovalUnavailableError: no risk budget is recorded or in force, so
            there is nothing to approve this candidate against.
        PortfolioStoreError: the store exists and cannot be read.
        DomainValidationError: an argument is malformed. Raised rather than
            wrapped, because a typo in a flag is not a broken store.
    """
    if not isinstance(proposal, PositionProposal):
        raise TypeError(
            f"proposal must be a PositionProposal, got {type(proposal).__name__}"
        )
    if not isinstance(policy, SizingPolicy):
        raise TypeError(f"policy must be a SizingPolicy, got {type(policy).__name__}")
    moment = require_utc(as_of, "as_of")
    asset = (
        base_currency
        if isinstance(base_currency, AssetCode)
        else AssetCode(base_currency)
    )
    store_root = default_store_root() if root is None else Path(root)

    valuation = portfolio_for(
        store_root,
        as_of=moment,
        portfolio_id=portfolio_id,
        base_currency=asset,
        books_covered=books_covered,
        classification=classification,
        read_marks=read_marks,
        interval=interval,
        limit=limit,
        transport=transport,
        clock=clock,
        base_url=base_url,
        known_at=known_at,
    )
    budget = _budget_or_refuse(store_root, at=moment)
    return engine_for(policy, classification).evaluate(
        proposal,
        state=valuation.state,
        budget=budget,
        owner=owner_context(base_currency=asset, timezone=timezone),
        mark_age=valuation.mark_age,
        evaluated_at=moment,
    )


def resolve_account(
    root: Path | str | None, *, stated: str | None
) -> AccountId:
    """The account this candidate consumes capacity in: stated, or the only one.

    `None` from the owner means *"use the account I trade in"*, which is
    answerable exactly when the store records fills in one account and is refused
    the moment it records fills in two. `fmis.today.builder` applies the identical
    single-lineage rule to budgets and portfolio snapshots, for the identical
    reason: picking the first would make the answer depend on an id sort nobody
    wrote down.
    """
    if stated is not None:
        return AccountId(stated)
    store_root = default_store_root() if root is None else Path(root)
    resolved = _guarded(
        lambda: sole_account(TradingStore(store_root, dust=VALUATION_DUST_POLICY)),
        store_root,
    )
    if isinstance(resolved, Absent):
        raise ApprovalUnavailableError(resolved.reason)
    return resolved


def proposal_for_plan(
    root: Path | str | None,
    *,
    plan_id: str,
    account: AccountId,
    entry: Decimal,
) -> PositionProposal:
    """Size a commitment the owner already recorded with `fmits trade record`.

    **The integration point with Trade Capture, and it reads rather than
    retypes.** The market, the book, the side, the stop and the whole target
    ladder come from the stored `TradePlan`; the entry price is supplied because
    a plan deliberately does not hold one — `AR-3`'s *"no exact entry is
    fabricated"* survives into this layer, and the owner states the price they
    intend to transact at.

    Raises:
        ApprovalUnavailableError: no such commitment is in this store.
        PortfolioStoreError: the store exists and cannot be read.
    """
    store_root = default_store_root() if root is None else Path(root)
    plan = _guarded(
        lambda: plan_to_size(
            TradingStore(store_root, dust=VALUATION_DUST_POLICY), plan_id
        ),
        store_root,
    )
    if isinstance(plan, Absent):
        raise ApprovalUnavailableError(plan.reason)
    return PositionProposal.from_plan(plan, account=account, entry=entry)


def _budget_or_refuse(root: Path, *, at: datetime) -> Any:
    """The owner's limits, or a refusal naming what they must record.

    The store is opened a second time here, which is the trade
    `fmis.valuation.compose` already documents: threading a half-read store
    through a network call to avoid it would make the fold depend on when the
    fetch happened, and two local reads of an append-only store cost nothing.
    """
    budget = _guarded(
        lambda: budget_in_effect(
            TradingStore(root, dust=VALUATION_DUST_POLICY), at=at
        ),
        root,
    )
    if isinstance(budget, Absent):
        raise ApprovalUnavailableError(
            "this candidate cannot be approved against limits nobody set: "
            f"{budget.reason}. Record a risk budget and every figure on this page "
            "becomes measurable"
        )
    return budget


def _guarded(read: Any, root: Path) -> Any:
    """Run a store read, turning an unreadable store into the bridge's own error.

    Both families are caught, and the second is not redundant: a hand-edited
    index row or a payload written by a newer build fails the **domain's** own
    decoder (`PayloadDecodeError`, a `TradeDomainError`) long before any
    store-level check runs. `fmis.today.read_store` and
    `fmis.valuation.compose` both record the same finding — catching only
    `PersistenceError` let that escape as an unhandled traceback.

    `PortfolioStoreError` rather than a name of this package's own, because
    `fmis.pipeline.cli` already catches it for `fmits portfolio` and two names for
    one condition reaching one surface is how one of them stops being handled.
    """
    try:
        return read()
    except (PersistenceError, TradeDomainError) as error:
        raise PortfolioStoreError(
            f"the store at {root} could not be read: "
            f"{type(error).__name__}: {error}"
        ) from error
