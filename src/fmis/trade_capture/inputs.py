"""The text boundary: what the owner typed becomes what the domain accepts.

**This module exists so that `fmis.pipeline.cli` never imports the trading
domain or the store.** Milestone BJ established that rule and enforces it —
*"`fmis.pipeline` is a market-half package and may not reach the store"* — and
Milestone BK keeps it: the CLI parses no amount, constructs no `AccountId` and
opens no `TradingStore`. It hands strings here and prints what comes back.

That is worth more than a guard test. Every conversion below is a place a value
can be mis-read — a price through a float, a naive timestamp, a symbol split at
the wrong character — and putting them in one tested module rather than in an
argparse callback is the difference between *"the CLI is thin"* as a claim and as
a property.

**Nothing here defaults a value the owner must state.** A missing FX rate, a
missing book, a missing stop: each is a required argument and stays one. What is
defaulted is only what has exactly one honest reading — the fee's asset is the
market's quote asset, the FX rate's instant is the fill's own — and each default
is stated where it is applied.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import fmis
from fmis.accounts import AccountId, Book, MarketMode
from fmis.money import AssetCode, Money, Quantity
from fmis.persistence import TradingStore, default_store_root
from fmis.provenance import Absent
from fmis.records import TradeDomainError
from fmis.snapshotting import TradeDirection
from fmis.trade_capture.capture import (
    CAPTURE_DUST_POLICY,
    DEFAULT_QUOTE_ASSET,
    DEFAULT_VENUE,
    CloseRequest,
    NoteRequest,
    RecordRequest,
    market_from_symbol,
)
from fmis.trade_capture.models import (
    CaptureStatus,
    TradeCaptureError,
    TradeFilters,
)
from fmis.trade_capture.views import load_plan

__all__ = [
    "CAPTURE_ERRORS",
    "BOOK_CHOICES",
    "DIRECTION_CHOICES",
    "MARKET_MODE_CHOICES",
    "STATUS_CHOICES",
    "DEFAULT_MARKET_MODE",
    "capture_store_root",
    "open_store",
    "record_request_from_text",
    "close_request_from_text",
    "note_request_from_text",
    "filters_from_text",
]

#: Everything a capture command can fail with, as one tuple a caller can catch.
#: `TradeDomainError` covers the domain's own refusals *and* every persistence
#: error, which derives from it — so a surface catching this pair cannot miss a
#: refusal by forgetting a layer.
CAPTURE_ERRORS: tuple[type[BaseException], ...] = (TradeCaptureError, TradeDomainError)

#: The closed vocabularies a surface offers as choices. Derived from the enums
#: rather than retyped, so a member added to `Book` appears at the CLI without an
#: edit and a member removed cannot linger in a help string.
BOOK_CHOICES: tuple[str, ...] = tuple(book.value for book in Book)
MARKET_MODE_CHOICES: tuple[str, ...] = tuple(mode.value for mode in MarketMode)
STATUS_CHOICES: tuple[str, ...] = tuple(state.value for state in CaptureStatus)

#: `NO_TRADE` is deliberately absent: it is a decision *not* to act, it belongs to
#: a proposal's lifecycle where it can be scored, and a plan with it has no stop
#: to be wrong about.
DIRECTION_CHOICES: tuple[str, ...] = tuple(
    direction.value for direction in TradeDirection if direction.is_directional
)

DEFAULT_MARKET_MODE = MarketMode.SPOT.value


def capture_store_root() -> Path:
    """The owner's store, when a command names none."""
    return default_store_root()


def open_store(root: str | Path | None) -> TradingStore:
    """The store at `root`, or the owner's own.

    Constructing one creates no directory and writes no byte, so opening a store
    on a path that does not exist is safe and reads as emptiness — which is what
    it means.
    """
    return TradingStore(
        Path(root) if root else capture_store_root(), dust=CAPTURE_DUST_POLICY
    )


def _decimal(raw: str, name: str) -> Decimal:
    """Exact text → exact `Decimal`, refusing anything that is not a number.

    `Decimal(text)` and never `Decimal(float(text))`. Binary floating point
    cannot represent `0.1`; one pass through a float would put a fifty-five-digit
    expansion into a content digest and therefore into a record id, and the same
    amount typed twice would produce two records.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise TradeCaptureError(f"{name} is required and must be a number")
    try:
        value = Decimal(raw.strip())
    except InvalidOperation as error:
        raise TradeCaptureError(f"{name} {raw!r} is not a decimal number") from error
    if not value.is_finite():
        raise TradeCaptureError(f"{name} {raw!r} is not a finite number")
    return value


def _instant(raw: str, name: str) -> datetime:
    """ISO-8601 text → a UTC instant, refusing a naive one.

    ADR-0001: UTC is canonical for storage. A naive timestamp is refused rather
    than assumed local, because the assumption would be invisible in the stored
    bytes and wrong for exactly the owner this system has.
    """
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise TradeCaptureError(
            f"{name} {raw!r} is not an ISO-8601 timestamp"
        ) from error
    if parsed.tzinfo is None:
        raise TradeCaptureError(
            f"{name} must be timezone-aware, e.g. 2026-08-12T10:00:00+00:00. A "
            "naive instant has no unambiguous UTC reading and this system stores "
            "UTC"
        )
    return parsed.astimezone(timezone.utc)


def _instant_or(raw: str | None, fallback: datetime, name: str) -> datetime:
    return fallback if raw is None else _instant(raw, name)


def _maybe_instant(raw: str | None, reason: str, name: str) -> datetime | Absent:
    return Absent(reason) if raw is None else _instant(raw, name)


def _maybe_text(raw: str | None, reason: str) -> str | Absent:
    return Absent(reason) if raw is None else raw


def _maybe_decimal(raw: str | None, reason: str, name: str) -> Decimal | Absent:
    return Absent(reason) if raw is None else _decimal(raw, name)


def _fee(amount: str, asset: str | None, quote: AssetCode) -> Money:
    """The fee, in the asset stated or in the market's quote asset.

    Defaulting to the quote asset is the venue convention this repository's one
    provider actually uses, and it is the only default here that touches an
    amount. A fee in any *third* asset is its own disposal and the domain refuses
    it without a rate of its own — which is why the default cannot hide one.
    """
    return Money(
        _decimal(amount, "--fee"),
        AssetCode(asset.strip().upper()) if asset else quote,
    )


def record_request_from_text(
    *,
    symbol: str,
    direction: str,
    account: str,
    book: str,
    entry: str,
    stop: str,
    size: str,
    fee: str,
    fx_rate: str,
    fx_source: str,
    confidence: str,
    author: str,
    filed_at: datetime,
    targets: Sequence[str] | None = None,
    fee_asset: str | None = None,
    fee_fx_rate: str | None = None,
    fx_timestamp: str | None = None,
    occurred_at: str | None = None,
    committed_at: str | None = None,
    expires: str | None = None,
    setup: str | None = None,
    proposal: str | None = None,
    snapshot: str | None = None,
    analysis: Sequence[str] | None = None,
    thesis: str | None = None,
    note: str | None = None,
    venue: str = DEFAULT_VENUE,
    quote: str = DEFAULT_QUOTE_ASSET,
    mode: str = DEFAULT_MARKET_MODE,
    code_version: str | None = None,
) -> RecordRequest:
    """Everything `fmits trade record` was given, as one validated request."""
    market = market_from_symbol(
        symbol, venue=venue, quote=quote, mode=_market_mode(mode)
    )
    occurred = _instant_or(occurred_at, filed_at, "--occurred-at")
    return RecordRequest(
        market=market,
        book=_book(book),
        account=AccountId(account),
        direction=_direction(direction),
        entry_price=_decimal(entry, "--entry"),
        stop=_decimal(stop, "--stop"),
        targets=tuple(
            _decimal(target, f"--target {position + 1}")
            for position, target in enumerate(targets or ())
        ),
        quantity=Quantity(_decimal(size, "--size"), market.base_asset),
        fee=_fee(fee, fee_asset, market.quote_asset),
        fx_rate_to_tax_currency=_decimal(fx_rate, "--fx-rate"),
        fx_source=fx_source,
        occurred_at=occurred,
        written_at=filed_at,
        author=author,
        confidence=confidence,
        code_version=code_version or fmis.__version__,
        committed_at=_maybe_instant(
            committed_at, "committed at the moment of entry", "--committed-at"
        ),
        fx_timestamp=_maybe_instant(
            fx_timestamp, "the fill's own instant", "--fx-timestamp"
        ),
        fee_fx_rate_to_tax_currency=_maybe_decimal(
            fee_fx_rate, "fee is one side of this trade", "--fee-fx-rate"
        ),
        setup_type=_maybe_text(setup, "no setup type was named"),
        proposal_id=_maybe_text(proposal, "this plan was not proposed"),
        market_snapshot_id=_maybe_text(snapshot, "no market context was frozen"),
        analysis_record_ids=tuple(analysis or ()),
        expires_at=_maybe_instant(expires, "this plan does not expire", "--expires"),
        thesis=_maybe_text(thesis, "no thesis was stated"),
        note=_maybe_text(note, "no note"),
    )


def close_request_from_text(
    store: TradingStore,
    *,
    plan_id: str,
    price: str,
    fee: str,
    fx_rate: str,
    fx_source: str,
    reason: str,
    author: str,
    filed_at: datetime,
    size: str | None = None,
    account: str | None = None,
    fee_asset: str | None = None,
    fee_fx_rate: str | None = None,
    fx_timestamp: str | None = None,
    occurred_at: str | None = None,
    note: str | None = None,
    code_version: str | None = None,
) -> CloseRequest:
    """The exit, resolved against the stored commitment it closes.

    The plan is read here because two defaults depend on it and neither has a
    reading without it: which asset a bare `--size` is denominated in, and which
    asset a bare `--fee` is. Guessing either from the string would be the split
    `market_from_symbol` already refuses to guess, one layer later.
    """
    plan = load_plan(store, plan_id)
    return CloseRequest(
        plan_id=plan.plan_id,
        exit_price=_decimal(price, "--price"),
        fee=_fee(fee, fee_asset, plan.market.quote_asset),
        fx_rate_to_tax_currency=_decimal(fx_rate, "--fx-rate"),
        fx_source=fx_source,
        occurred_at=_instant_or(occurred_at, filed_at, "--occurred-at"),
        written_at=filed_at,
        author=author,
        reason=reason,
        code_version=code_version or fmis.__version__,
        quantity=(
            Absent("close the whole open position")
            if size is None
            else Quantity(_decimal(size, "--size"), plan.market.base_asset)
        ),
        account=(
            Absent("the account the entry filled in")
            if account is None
            else AccountId(account)
        ),
        fx_timestamp=_maybe_instant(
            fx_timestamp, "the fill's own instant", "--fx-timestamp"
        ),
        fee_fx_rate_to_tax_currency=_maybe_decimal(
            fee_fx_rate, "fee is one side of this trade", "--fee-fx-rate"
        ),
        note=_maybe_text(note, "no note"),
    )


def note_request_from_text(
    *,
    plan_id: str,
    body: str,
    author: str,
    filed_at: datetime,
    title: str | None = None,
    recorded_at: str | None = None,
    code_version: str | None = None,
) -> NoteRequest:
    return NoteRequest(
        plan_id=plan_id,
        body=body,
        recorded_at=_instant_or(recorded_at, filed_at, "--recorded-at"),
        written_at=filed_at,
        author=author,
        code_version=code_version or fmis.__version__,
        title=_maybe_text(title, "no title"),
    )


def filters_from_text(
    *,
    status: str | None = None,
    symbol: str | None = None,
    account: str | None = None,
    direction: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> TradeFilters:
    return TradeFilters(
        status=None if status is None else _status(status),
        symbol=symbol,
        account=account,
        direction=None if direction is None else _direction(direction),
        since=None if since is None else _instant(since, "--since"),
        until=None if until is None else _instant(until, "--until"),
    )


def _member(enum_type: type, value: str, flag: str) -> object:
    try:
        return enum_type(value)
    except ValueError as error:
        legal = sorted(member.value for member in enum_type)
        raise TradeCaptureError(
            f"{flag} {value!r} is not one of {legal}. An unknown member is a "
            "clean rejection, never a default"
        ) from error


def _book(value: str) -> Book:
    book = _member(Book, value, "--book")
    assert isinstance(book, Book)
    return book


def _market_mode(value: str) -> MarketMode:
    mode = _member(MarketMode, value, "--mode")
    assert isinstance(mode, MarketMode)
    return mode


def _status(value: str) -> CaptureStatus:
    status = _member(CaptureStatus, value, "--status")
    assert isinstance(status, CaptureStatus)
    return status


def _direction(value: str) -> TradeDirection:
    direction = _member(TradeDirection, value, "--direction")
    assert isinstance(direction, TradeDirection)
    if not direction.is_directional:
        raise TradeCaptureError(
            "a recorded trade commits to a side. A decision not to act is a "
            "proposal outcome, where it can be scored, and has no stop to be "
            "wrong about"
        )
    return direction
