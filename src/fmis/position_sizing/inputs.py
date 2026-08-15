"""The text boundary: what the owner typed, and what the scanner produced.

**This module exists so that `fmis.pipeline.cli` never imports the trading domain
or the store.** Milestone `BJ` established that rule, `BK` kept it with
`fmis.trade_capture.inputs`, and this is the third instance: the CLI parses no
price, constructs no `AccountId` and opens no `TradingStore` for `fmits approve`.
It hands strings here and prints what comes back.

**The symbol split is `fmis.trade_capture`'s, imported rather than rewritten.**
`market_from_symbol` already refuses to guess where `BTCUSDT` divides — *"`BTCU`
/`SDT` is a legal reading of the same characters"* — and requires the owner to
name the quote asset. A second implementation of that rule would be a second
place the split could be wrong, and the two would agree until the day a symbol
arrived that neither author had thought about.

**This is the one module in the package that may name a venue**, on exactly the
footing `fmis.trade_capture` holds it: a *surface* pre-filling a field the owner
can change is not a portfolio calculation branching on an exchange. Every module
that computes anything is guarded against naming one, asserted as a set.

**A scan result becomes a candidate only when it carries what a size needs.**
Not when it reaches a particular state: this module compares no `SetupState` and
imports nothing from `fmis.swing_setup`. A result with no side proposes nothing,
and a result with a side but no stop has no risk denominator — so the filter is
*"has a direction"* and the refusals are *"has no stop"* and *"has no reference
price"*, each reported by name. `WAIT` falls out of the first because a `WAIT`
carries no direction, which is the engine's own fact rather than this module's
reading of it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from fmis.accounts import AccountId, Book, MarketMode
from fmis.money import exact_from_market_price
from fmis.portfolio_risk import PortfolioState
from fmis.provenance import Absent
from fmis.records import TradeDomainError
from fmis.risk import RiskBudget
from fmis.snapshotting import TradeDirection
from fmis.trade_capture import (
    DEFAULT_MARKET_MODE,
    DEFAULT_QUOTE_ASSET,
    DEFAULT_VENUE,
    TradeCaptureError,
    market_from_symbol,
)

from fmis.position_sizing.approval import ApprovalEngine
from fmis.position_sizing.models import (
    ApprovalResult,
    PositionProposal,
    PositionSizingError,
    SizingRefusedError,
)
from fmis.position_sizing.policy import SizingPolicy

__all__ = [
    "APPROVAL_ERRORS",
    "DEFAULT_SIZING_POLICY_ID",
    "price_from_text",
    "scope_from_text",
    "proposal_from_text",
    "sizing_policy_from_text",
    "proposals_from_results",
    "approve_results",
]

#: Everything an approval command can fail with, as one tuple a caller can catch.
#: `TradeDomainError` covers the domain's own refusals *and* every persistence
#: error, which derives from it — so a surface catching this pair cannot miss a
#: refusal by forgetting a layer. The same shape `CAPTURE_ERRORS` already has.
APPROVAL_ERRORS: tuple[type[BaseException], ...] = (
    PositionSizingError,
    TradeDomainError,
    TradeCaptureError,
)

#: What the owner's sizing rule is called when they name it nothing. An
#: identifier rather than a blank, so the day a second policy exists the first
#: keeps its identity instead of inheriting a new default. It carries **no
#: fraction** — naming a policy is not the same as configuring one.
DEFAULT_SIZING_POLICY_ID = "owner_sizing"


def _decimal(raw: str, name: str) -> Decimal:
    """Exact text → exact `Decimal`, refusing anything that is not a number.

    `Decimal(text)` and never `Decimal(float(text))`, for the reason
    `fmis.trade_capture.inputs` gives: binary floating point cannot represent
    `0.1`, and one pass through a float puts a fifty-five-digit expansion into
    every figure downstream of it.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise SizingRefusedError(f"{name} is required and must be a number")
    try:
        value = Decimal(raw.strip())
    except InvalidOperation as error:
        raise SizingRefusedError(f"{name} {raw!r} is not a decimal number") from error
    if not value.is_finite():
        raise SizingRefusedError(f"{name} {raw!r} is not a finite number")
    return value


def _duration(raw: str, name: str) -> timedelta:
    """`36h`, `90m`, `7d` → a duration. The owner's bound, in the owner's units.

    Whole units only, and a suffix is required. `--max-mark-age 4` has three
    plausible readings and this system holds no convention that makes one of them
    right; refusing is cheaper than picking the one that makes a stale price look
    fresh.
    """
    text = raw.strip().lower() if isinstance(raw, str) else ""
    units = {"d": "days", "h": "hours", "m": "minutes"}
    if len(text) < 2 or text[-1] not in units:
        raise SizingRefusedError(
            f"{name} {raw!r} must end in 'd', 'h' or 'm' — for example '36h'. A "
            "bare number has several readings and this system holds no "
            "convention that makes one of them right"
        )
    try:
        amount = int(text[:-1])
    except ValueError as error:
        raise SizingRefusedError(
            f"{name} {raw!r} is not a whole number of {units[text[-1]]}"
        ) from error
    if amount <= 0:
        raise SizingRefusedError(
            f"{name} {raw!r} must be positive; a bound of zero would make every "
            "figure stale the instant after it was true"
        )
    return timedelta(**{units[text[-1]]: amount})


def _direction(value: str) -> TradeDirection:
    try:
        direction = TradeDirection(value)
    except ValueError as error:
        legal = sorted(
            member.value for member in TradeDirection if member.is_directional
        )
        raise SizingRefusedError(
            f"--direction {value!r} is not one of {legal}. An unknown member is a "
            "clean rejection, never a default"
        ) from error
    if not direction.is_directional:
        raise SizingRefusedError(
            "a candidate for sizing commits to a side. A decision not to act "
            "proposes no exposure and needs no size"
        )
    return direction


def _member(enum_type: type, value: str, flag: str) -> Any:
    try:
        return enum_type(value)
    except ValueError as error:
        legal = sorted(member.value for member in enum_type)
        raise SizingRefusedError(
            f"{flag} {value!r} is not one of {legal}. An unknown member is a "
            "clean rejection, never a default"
        ) from error


def price_from_text(raw: str, name: str) -> Decimal:
    """One typed price as an exact value, for a caller that needs only that.

    The `--plan` path needs an entry price without a symbol, a side or a stop
    beside it, and routing it through `proposal_from_text` would mean building a
    throwaway candidate to reach one conversion. Exported so the CLI still parses
    nothing itself and there is still exactly one parser.
    """
    return _decimal(raw, name)


def scope_from_text(
    *, account: str | None, book: str
) -> tuple[AccountId | None, Book]:
    """The account and book a page's candidates are scoped to, from flags.

    `None` for the account means *"use the one this store records fills in"* and
    is resolved later against the reading — it is not a default account, and
    there is none. Exported so a surface can pass a scope without constructing an
    `AccountId` of its own, which is the boundary `fmis.pipeline` may not cross.
    """
    return (
        None if account is None else AccountId(account),
        _member(Book, book, "--book"),
    )


def proposal_from_text(
    *,
    symbol: str,
    direction: str,
    account: str,
    book: str,
    entry: str,
    stop: str,
    targets: Sequence[str] | None = None,
    venue: str = DEFAULT_VENUE,
    quote: str = DEFAULT_QUOTE_ASSET,
    mode: str = DEFAULT_MARKET_MODE,
) -> PositionProposal:
    """Everything `fmits approve` was given about the candidate, validated once."""
    market = market_from_symbol(
        symbol, venue=venue, quote=quote, mode=_member(MarketMode, mode, "--mode")
    )
    return PositionProposal(
        account=AccountId(account),
        market=market,
        book=_member(Book, book, "--book"),
        direction=_direction(direction),
        entry=_decimal(entry, "--entry"),
        stop=_decimal(stop, "--stop"),
        targets=tuple(
            _decimal(target, f"--target {position + 1}")
            for position, target in enumerate(targets or ())
        ),
    )


def sizing_policy_from_text(
    *,
    policy_id: str = DEFAULT_SIZING_POLICY_ID,
    risk_fraction: str | None = None,
    max_equity_age: str | None = None,
    max_mark_age: str | None = None,
    minimum_risk_reward: str | None = None,
) -> SizingPolicy:
    """The owner's sizing rule, from flags. **Nothing here defaults a number.**

    Every argument that is `None` becomes `Absent(reason)` naming the flag that
    would have set it, so a page produced under a half-configured policy says
    which half is missing rather than quietly sizing at something.
    """
    return SizingPolicy(
        policy_id=policy_id,
        risk_fraction=(
            Absent(
                "no --risk-fraction was given, so the fraction falls back to the "
                "default the owner set below their per-trade ceiling"
            )
            if risk_fraction is None
            else _decimal(risk_fraction, "--risk-fraction")
        ),
        max_equity_age=(
            Absent("no --max-equity-age was given")
            if max_equity_age is None
            else _duration(max_equity_age, "--max-equity-age")
        ),
        max_mark_age=(
            Absent("no --max-mark-age was given")
            if max_mark_age is None
            else _duration(max_mark_age, "--max-mark-age")
        ),
        minimum_risk_reward=(
            Absent("no --min-risk-reward was given")
            if minimum_risk_reward is None
            else _decimal(minimum_risk_reward, "--min-risk-reward")
        ),
    )


# ---------------------------------------------------------------------------
# The scanner's own results, turned into candidates.
# ---------------------------------------------------------------------------


def proposals_from_results(
    results: Sequence[Any],
    *,
    account: AccountId,
    book: Book,
    venue: str = DEFAULT_VENUE,
    quote: str = DEFAULT_QUOTE_ASSET,
    mode: str = DEFAULT_MARKET_MODE,
) -> dict[str, PositionProposal | Absent]:
    """Every directional scan result as a candidate, or the reason it is not one.

    Duck-typed over the scan result, exactly as `fmis.today.sections` reads the
    same objects: this module imports nothing from `fmis.swing_setup` and names
    no setup state. A result that carries a direction is a candidate a size could
    be produced for; the two ways it can still fail — no stop, no reference price
    — are `Absent(reason)` rather than a silent omission, because a candidate
    dropped from this mapping would render as a candidate nobody checked.

    The reference price is the execution-timeframe close the stop and targets were
    measured against, and it is **not an order price** — the engine that produced
    it says so, and every figure derived from it here inherits that caveat. It
    crosses from `float` to exact through `fmis.money.exact_from_market_price`,
    the one named crossing in the repository.
    """
    market_mode = _member(MarketMode, mode, "--mode")
    found: dict[str, PositionProposal | Absent] = {}
    for result in results:
        assessment = getattr(result, "assessment", None)
        if assessment is None or assessment.direction is None:
            continue
        symbol = result.requested_symbol
        found[symbol] = _proposal_for(
            assessment,
            account=account,
            book=book,
            venue=venue,
            quote=quote,
            mode=market_mode,
        )
    return found


def _proposal_for(
    assessment: Any,
    *,
    account: AccountId,
    book: Book,
    venue: str,
    quote: str,
    mode: MarketMode,
) -> PositionProposal | Absent:
    if assessment.stop is None:
        return Absent(
            f"{assessment.symbol} has no stop level, so it has no risk "
            "denominator and no size can be produced from it"
        )
    if assessment.reference_price is None:
        return Absent(
            f"{assessment.symbol} states no reference price, so there is nothing "
            "to measure the stop distance from"
        )
    try:
        market = market_from_symbol(
            assessment.symbol, venue=venue, quote=quote, mode=mode
        )
    except (TradeCaptureError, TradeDomainError) as error:
        # A watchlist symbol that does not end in the quote asset the owner named
        # is one candidate this page cannot scope, not a page that fails. `fmits
        # scan`'s own per-symbol isolation, kept one layer later.
        return Absent(str(error))
    return PositionProposal(
        account=account,
        market=market,
        book=book,
        direction=TradeDirection(assessment.direction.value),
        entry=exact_from_market_price(assessment.reference_price, "reference price"),
        stop=exact_from_market_price(assessment.stop.price, "stop"),
        targets=tuple(
            exact_from_market_price(level.price, f"target {position + 1}")
            for position, level in enumerate(assessment.targets)
        ),
    )


def approve_results(
    results: Sequence[Any],
    *,
    engine: ApprovalEngine,
    state: PortfolioState,
    budget: RiskBudget,
    owner: Any,
    account: AccountId,
    book: Book,
    mark_age: Any = None,
    venue: str = DEFAULT_VENUE,
    quote: str = DEFAULT_QUOTE_ASSET,
    mode: str = DEFAULT_MARKET_MODE,
) -> dict[str, ApprovalResult | Absent]:
    """Approve every directional result in one scan, against one portfolio reading.

    **One reading, one budget, one engine, for every candidate on the page.**
    Evaluating each candidate against a freshly-read portfolio would let two rows
    on one page disagree about how much open risk the owner has, and the page
    would look internally consistent while being about two different portfolios.

    Each candidate is evaluated **independently and against the same before-state**
    — this is not a cumulative allocation. Two candidates that each fit the
    budget alone do not both fit it together, and this mapping does not claim they
    do; `AP` §15.6's rule is that a portfolio constrains one candidate at a time,
    and sequencing them would be a rebalancing engine, which `AP` §15.4 places
    firmly out of scope.
    """
    if not isinstance(engine, ApprovalEngine):
        raise TypeError(f"engine must be an ApprovalEngine, got {type(engine).__name__}")
    proposals = proposals_from_results(
        results, account=account, book=book, venue=venue, quote=quote, mode=mode
    )
    approved: dict[str, ApprovalResult | Absent] = {}
    for symbol, proposal in proposals.items():
        if isinstance(proposal, Absent):
            approved[symbol] = proposal
            continue
        approved[symbol] = engine.evaluate(
            proposal,
            state=state,
            budget=budget,
            owner=owner,
            mark_age=mark_age,
        )
    return approved
