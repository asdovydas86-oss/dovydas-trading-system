"""The three write paths: record a trade, close it, write a note about it.

**Nothing here reaches disk except through `TradingStore`.** Every write is a
repository call, so the store's hash-chained write journal stays a *complete*
account of what happened: a record that reached disk without a journal event
would have to have been written by code that does not exist, and a guard test
asserts this module names no path, no file and no atomic write.

**Everything is validated before anything is published.** All three records are
constructed first — construction is where the domain's rules live — and the
cross-record checks the domain cannot make run after that. Only then does the
first byte move. A command that had written a plan and then refused its fill
would leave the owner with a commitment they did not make.

**The order is plan → fill → note, and it is deliberate.** A `Trade` names its
`plan_id`, so publishing the fill first would produce a fill pointing at nothing
if the run died between them. The reverse gap leaves a plan with no fill, which
is a real and readable state — `CaptureStatus.PLANNED` — rather than a dangling
reference.

**This module reads a clock nowhere.** Every instant on every record is supplied
by the caller, exactly as the domain and the store both require of themselves.
`fmis.pipeline.cli` is the only place in this repository that takes the time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from fmis.accounts import AccountId, Book, MarketId, MarketMode, VenueId
from fmis.journal import (
    JournalEntry,
    JournalKind,
    JournalLink,
    JournalTag,
    LinkKind,
    TagOrigin,
)
from fmis.ledger import LedgerSource, Trade, TradeSide
from fmis.money import AssetCode, DustPolicy, Money, Quantity, canonical_decimal_text
from fmis.persistence import TradingStore, WriteRequest, WriteSource
from fmis.plan import TRADE_PLAN_SCHEMA_VERSION, TradePlan, check_placement
from fmis.positions import POSITION_CALCULATION_VERSION
from fmis.proposal import StatedConfidence
from fmis.provenance import Absent, VersionedTerm
from fmis.records import (
    RecordAudit,
    require_text,
    require_tuple_of,
    require_utc,
)
from fmis.snapshotting import TradeDirection
from fmis.trade_capture.models import (
    CaptureOutcome,
    CaptureRefusedError,
    CaptureStatus,
    TradeView,
    WrittenRecord,
)
from fmis.trade_capture.views import (
    PLAN_SUBJECT_KIND,
    TRADE_SUBJECT_KIND,
    load_trade,
)
from fmis.versioning import VersionAxis, VersionSet

__all__ = [
    "CAPTURE_DUST_POLICY",
    "TAXONOMY_VERSION",
    "WRITE_REASON_VOCABULARY",
    "SETUP_TYPE_VOCABULARY",
    "EXIT_REASON_VOCABULARY",
    "RECORD_REASON",
    "CLOSE_REASON",
    "NOTE_REASON",
    "DEFAULT_VENUE",
    "DEFAULT_QUOTE_ASSET",
    "market_from_symbol",
    "capture_version_set",
    "RecordRequest",
    "CloseRequest",
    "NoteRequest",
    "record_trade",
    "close_trade",
    "append_note",
]

#: Exact zero, with no configured threshold. `fmis.money.DustPolicy` states the
#: rule this follows: *"an asset with no configured threshold uses exact zero...
#: zero is the only tolerance that is not a policy decision"*. `fmis.today` made
#: the identical choice for the identical reason, and a capture surface that
#: chose a different one would draw the boundary between two round trips in a
#: different place from the page that reports them.
CAPTURE_DUST_POLICY = DustPolicy(policy_id="fmits-trade-capture-exact-zero", version=1)

#: The generation every vocabulary term this package mints is stamped with. One
#: constant rather than a parameter, because a taxonomy version is a property of
#: the *vocabulary*, and a caller who could choose it per call could make two
#: records claim two generations of one word.
TAXONOMY_VERSION = 1

#: Why the store performed a write. A property of this code path, not a trading
#: policy — the same class of value as `WriteSource.OWNER` — so naming these
#: three terms here is not this layer choosing a policy on the owner's behalf.
WRITE_REASON_VOCABULARY = "write_reason"

#: The owner's own vocabularies. **This package defines no member of either.**
#: A term id typed at the CLI is carried through verbatim, because membership is
#: the owner's and `AP` §20.2's rule is *retire and add, never redefine*.
SETUP_TYPE_VOCABULARY = "setup_type"
EXIT_REASON_VOCABULARY = "exit_reason"


def _write_reason(term_id: str) -> VersionedTerm:
    return VersionedTerm(
        vocabulary_id=WRITE_REASON_VOCABULARY,
        term_id=term_id,
        taxonomy_version=TAXONOMY_VERSION,
    )


RECORD_REASON = _write_reason("manual_trade_capture")
CLOSE_REASON = _write_reason("manual_trade_exit")
NOTE_REASON = _write_reason("manual_trade_note")

#: The only venue this repository has a provider for, and the quote asset every
#: pair in its watchlist is denominated in. Defaults at the *surface*, never a
#: fallback in a record: a `MarketId` still names all four components, and a
#: trade on another venue states it.
DEFAULT_VENUE = "binance"
DEFAULT_QUOTE_ASSET = "USDT"

#: Which way the base asset moves when a commitment is opened. The inverse
#: closes it. A mapping rather than a conditional so that a third direction —
#: `NO_TRADE`, which `TradePlan` already refuses — raises a `KeyError` here
#: rather than silently taking one branch.
_ENTRY_SIDE = MappingProxyType(
    {
        TradeDirection.LONG: TradeSide.BUY,
        TradeDirection.SHORT: TradeSide.SELL,
    }
)

_EXIT_SIDE = MappingProxyType(
    {
        TradeDirection.LONG: TradeSide.SELL,
        TradeDirection.SHORT: TradeSide.BUY,
    }
)


def market_from_symbol(
    symbol: str,
    *,
    venue: str = DEFAULT_VENUE,
    quote: str = DEFAULT_QUOTE_ASSET,
    mode: MarketMode = MarketMode.SPOT,
) -> MarketId:
    """`BTCUSDT` + a stated quote asset → the four-component market identity.

    **`MarketId` deliberately has no parse-from-string**, and its docstring says
    why: *"`BTCUSDT` cannot be split back into base and quote without an asset
    registry this package declines to hold — `BTCU`/`SDT` is a legal reading of
    the same characters."* This function does not guess that split. The **owner**
    supplies the quote asset, which makes the split a stated fact rather than an
    inference, and a symbol that does not end in the quote they named is refused
    instead of being cut somewhere plausible.
    """
    text = require_text(symbol, "symbol").upper()
    quote_asset = AssetCode(require_text(quote, "quote").upper())
    suffix = quote_asset.code
    if not text.endswith(suffix) or len(text) == len(suffix):
        raise CaptureRefusedError(
            f"symbol {text!r} does not end in the quote asset {suffix!r}, so FMITS "
            "cannot tell where the base asset ends. Name the quote asset with "
            "--quote, or state the pair as base+quote — this system holds no asset "
            "registry and will not guess the split"
        )
    return MarketId(
        venue=VenueId(require_text(venue, "venue")),
        base_asset=AssetCode(text[: -len(suffix)]),
        quote_asset=quote_asset,
        mode=mode,
    )


def capture_version_set(*, code_version: str) -> VersionSet:
    """The ten version axes, for a record the owner asserted.

    Four are known and six are `Absent` with a reason, which is `VersionSet`'s own
    contract: *"a reader can always tell 'we did not record it' from 'it did not
    apply'."* Nothing about a manually captured trade was produced by a policy, a
    classifier or a model, and stamping a policy version on one would make it
    indistinguishable from a generated proposal in every later cohort.
    """
    return VersionSet.of(
        {
            VersionAxis.CODE_VERSION: require_text(code_version, "code_version"),
            VersionAxis.CAPTURE_SCHEMA_VERSION: str(TRADE_PLAN_SCHEMA_VERSION),
            VersionAxis.CALCULATION_VERSION: POSITION_CALCULATION_VERSION,
            VersionAxis.TAXONOMY_VERSION: str(TAXONOMY_VERSION),
        },
        absent_reason=(
            "no policy, classifier or model produced this record; the owner "
            "asserted it"
        ),
    )


def _write_request(
    *, written_at: datetime, author: str, reason: VersionedTerm, version_set: VersionSet
) -> WriteRequest:
    return WriteRequest(
        written_at=written_at,
        source=WriteSource.OWNER,
        author=author,
        reason=reason,
        version_set=version_set,
    )


def _written(kind: str, receipt: Any) -> WrittenRecord:
    return WrittenRecord(
        kind=kind,
        record_id=receipt.record_id,
        created=receipt.created,
        relative_path=receipt.relative_path,
    )


def _plan_link(plan_id: str) -> JournalLink:
    return JournalLink(LinkKind.ABOUT, PLAN_SUBJECT_KIND, plan_id)


def _trade_link(event_id: str) -> JournalLink:
    return JournalLink(LinkKind.ABOUT, TRADE_SUBJECT_KIND, event_id)


def _require_store(store: Any) -> TradingStore:
    if not isinstance(store, TradingStore):
        raise TypeError(f"store must be a TradingStore, got {type(store).__name__}")
    return store


def _require_price(value: Any, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if value <= 0:
        raise CaptureRefusedError(
            f"{name} must be positive, got {canonical_decimal_text(value)}"
        )
    return Decimal(canonical_decimal_text(value))


def _require_filing(written_at: datetime, occurred_at: datetime, entity: str) -> datetime:
    filed = require_utc(written_at, "written_at")
    if filed < occurred_at:
        raise CaptureRefusedError(
            f"this {entity} is being filed at {filed.isoformat()}, before the "
            f"{occurred_at.isoformat()} it says it happened at. FMITS cannot learn "
            "of something before it happens"
        )
    return filed


@dataclass(frozen=True, slots=True)
class RecordRequest:
    """Everything `fmits trade record` needs, validated as one object.

    A record rather than fourteen parameters, so that the checks which span two
    fields — the fee's asset against the market, the filing instant against the
    fill's — have somewhere to live that is not the CLI. The CLI parses strings;
    this decides whether what they say can be true.
    """

    market: MarketId
    book: Book
    account: AccountId
    direction: TradeDirection
    entry_price: Decimal
    stop: Decimal
    quantity: Quantity
    fee: Money
    fx_rate_to_tax_currency: Decimal
    fx_source: str
    occurred_at: datetime
    written_at: datetime
    author: str
    confidence: str
    code_version: str
    targets: tuple[Decimal, ...] = ()
    committed_at: datetime | Absent = field(
        default_factory=lambda: Absent("committed at the moment of entry")
    )
    fx_timestamp: datetime | Absent = field(
        default_factory=lambda: Absent("the fill's own instant")
    )
    fee_fx_rate_to_tax_currency: Decimal | Absent = field(
        default_factory=lambda: Absent("fee is one side of this trade")
    )
    setup_type: str | Absent = field(
        default_factory=lambda: Absent("no setup type was named")
    )
    proposal_id: str | Absent = field(
        default_factory=lambda: Absent("this plan was not proposed")
    )
    market_snapshot_id: str | Absent = field(
        default_factory=lambda: Absent("no market context was frozen")
    )
    analysis_record_ids: tuple[str, ...] = ()
    expires_at: datetime | Absent = field(
        default_factory=lambda: Absent("this plan does not expire")
    )
    thesis: str | Absent = field(default_factory=lambda: Absent("no thesis was stated"))
    note: str | Absent = field(default_factory=lambda: Absent("no note"))

    def __post_init__(self) -> None:
        if not isinstance(self.market, MarketId):
            raise TypeError("market must be a MarketId")
        if not isinstance(self.account, AccountId):
            raise TypeError("account must be an AccountId")
        object.__setattr__(
            self, "occurred_at", require_utc(self.occurred_at, "occurred_at")
        )
        object.__setattr__(
            self,
            "written_at",
            _require_filing(self.written_at, self.occurred_at, "fill"),
        )
        object.__setattr__(
            self, "entry_price", _require_price(self.entry_price, "entry price")
        )
        object.__setattr__(self, "stop", _require_price(self.stop, "stop"))
        require_tuple_of(self.targets, Decimal, "targets")
        object.__setattr__(
            self,
            "targets",
            tuple(
                _require_price(target, f"target {position + 1}")
                for position, target in enumerate(self.targets)
            ),
        )
        if not isinstance(self.quantity, Quantity):
            raise TypeError("quantity must be a Quantity")
        if self.quantity.amount <= 0:
            raise CaptureRefusedError(
                f"position size must be positive, got {self.quantity}. Direction is "
                "stated separately, and a signed size would be the same fact twice"
            )
        if not isinstance(self.fee, Money):
            raise TypeError("fee must be a Money")
        if self.fee.amount < 0:
            raise CaptureRefusedError(
                f"fee must not be negative, got {self.fee}. A rebate is a different "
                "economic fact and is recorded as its own event"
            )
        object.__setattr__(self, "author", require_text(self.author, "author"))
        object.__setattr__(self, "confidence", require_text(self.confidence, "confidence"))
        object.__setattr__(
            self, "code_version", require_text(self.code_version, "code_version")
        )
        object.__setattr__(self, "fx_source", require_text(self.fx_source, "fx_source"))
        require_tuple_of(self.analysis_record_ids, str, "analysis_record_ids")
        if not isinstance(self.committed_at, Absent):
            object.__setattr__(
                self, "committed_at", require_utc(self.committed_at, "committed_at")
            )
            if self.committed_at > self.occurred_at:
                raise CaptureRefusedError(
                    f"the commitment is dated {self.committed_at.isoformat()}, after "
                    f"the fill at {self.occurred_at.isoformat()}. A plan is what was "
                    "committed to *before* the market moved; one dated after its own "
                    "fill cannot be scored against it"
                )

    @property
    def commitment_instant(self) -> datetime:
        """When the owner committed — the fill's instant unless they said otherwise."""
        if isinstance(self.committed_at, Absent):
            return self.occurred_at
        return self.committed_at

    @property
    def fx_instant(self) -> datetime:
        if isinstance(self.fx_timestamp, Absent):
            return self.occurred_at
        return require_utc(self.fx_timestamp, "fx_timestamp")

    def build_plan(self) -> TradePlan:
        """The commitment, exactly as it will be stored."""
        committed = self.commitment_instant
        return TradePlan(
            created_at=committed,
            committed_at=committed,
            market=self.market,
            book=self.book,
            direction=self.direction,
            initial_invalidation=self.stop,
            targets=self.targets,
            stated_confidence=StatedConfidence(self.confidence),
            version_set=capture_version_set(code_version=self.code_version),
            audit=RecordAudit.frozen_at(committed),
            setup_type=(
                self.setup_type
                if isinstance(self.setup_type, Absent)
                else VersionedTerm(
                    vocabulary_id=SETUP_TYPE_VOCABULARY,
                    term_id=self.setup_type,
                    taxonomy_version=TAXONOMY_VERSION,
                )
            ),
            proposal_id=self.proposal_id,
            market_snapshot_id=self.market_snapshot_id,
            analysis_record_ids=self.analysis_record_ids,
            expires_at=self.expires_at,
            note=self.note,
        )

    def build_trade(self, plan: TradePlan) -> Trade:
        """The entry fill, carrying the commitment it was taken under."""
        return Trade(
            occurred_at=self.occurred_at,
            recorded_at=self.written_at,
            account=self.account,
            book=self.book,
            market=self.market,
            side=_ENTRY_SIDE[self.direction],
            quantity=self.quantity,
            price=self.entry_price,
            fee=self.fee,
            fx_rate_to_tax_currency=self.fx_rate_to_tax_currency,
            fx_source=self.fx_source,
            fx_timestamp=self.fx_instant,
            source=LedgerSource.MANUAL,
            asserted_by=self.author,
            audit=RecordAudit.frozen_at(self.occurred_at),
            fee_fx_rate_to_tax_currency=self.fee_fx_rate_to_tax_currency,
            plan_id=plan.plan_id,
            proposal_id=self.proposal_id,
        )

    def build_journal_entry(self, plan: TradePlan, trade: Trade) -> JournalEntry | None:
        """The thesis, as the owner's own words. `None` when they stated none.

        **Not a field on the plan and not a field on the trade.** §11.6 routes
        *thesis, reasoning, emotion* to `JournalEntry` by name, and the routing is
        what makes the journal's own discipline metric — whether anything was
        written at all — mean something. A thesis auto-filled onto every plan
        would make that metric read 100 % forever.
        """
        if isinstance(self.thesis, Absent):
            return None
        return JournalEntry(
            kind=JournalKind.IDEA,
            recorded_at=self.written_at,
            author=self.author,
            audit=RecordAudit.frozen_at(self.written_at),
            title=f"thesis: {self.market.pair_symbol} {self.direction.value}",
            body=self.thesis,
            market_snapshot_id=self.market_snapshot_id,
            links=(_plan_link(plan.plan_id), _trade_link(trade.event_id)),
        )


def _check_consistency(request: RecordRequest, plan: TradePlan) -> None:
    """The cross-record rules neither the plan nor the fill can check alone."""
    check_placement(plan, request.entry_price)
    if request.quantity.asset != request.market.base_asset:
        raise CaptureRefusedError(
            f"the position size is stated in {request.quantity.asset} but "
            f"{request.market.value} trades {request.market.base_asset} as its base "
            "asset. Size is a quantity of what was bought, never of what paid for it"
        )
    sides = {request.market.base_asset, request.market.quote_asset}
    if request.fee.asset not in sides and isinstance(
        request.fee_fx_rate_to_tax_currency, Absent
    ):
        raise CaptureRefusedError(
            f"the fee is denominated in {request.fee.asset}, which is neither "
            f"{request.market.base_asset} nor {request.market.quote_asset}. A fee "
            "in a third asset is its own disposal and needs its own FX rate at the "
            "transaction instant — a rate that cannot be recovered later"
        )


def record_trade(store: TradingStore, request: RecordRequest) -> CaptureOutcome:
    """Record one swing trade: the commitment, the fill, and the thesis.

    Three records, one command, and every one of them refuses to be built if the
    owner's numbers cannot all be true at once. Nothing is corrected silently and
    nothing is defaulted: a stop on the wrong side of the entry, a size in the
    wrong asset and a third-asset fee with no rate are each a refusal naming the
    two values that disagree.

    Re-running the identical command is an **idempotent success**, not a second
    trade. Every id in this domain is a digest of the record's own content, so
    the second run publishes nothing, appends no journal event, and reports
    `created=False` on each record it found already there.
    """
    _require_store(store)
    if not isinstance(request, RecordRequest):
        raise TypeError("request must be a RecordRequest")
    plan = request.build_plan()
    _check_consistency(request, plan)
    trade = request.build_trade(plan)
    entry = request.build_journal_entry(plan, trade)

    versions = capture_version_set(code_version=request.code_version)
    written: list[WrittenRecord] = []
    write = _write_request(
        written_at=request.written_at,
        author=request.author,
        reason=RECORD_REASON,
        version_set=versions,
    )
    written.append(_written("trade_plan", store.plans.create(plan, request=write)))
    written.append(_written("trade", store.trades.create(trade, request=write)))
    if entry is not None:
        written.append(
            _written("journal_entry", store.journals.create(entry, request=write))
        )
    return CaptureOutcome(
        action="recorded",
        written=tuple(written),
        view=load_trade(
            store,
            plan.plan_id,
            dust=CAPTURE_DUST_POLICY,
            at=request.written_at,
        ),
    )


@dataclass(frozen=True, slots=True)
class CloseRequest:
    """Everything `fmits trade close` needs. The exit is a fill, not an edit."""

    plan_id: str
    exit_price: Decimal
    fee: Money
    fx_rate_to_tax_currency: Decimal
    fx_source: str
    occurred_at: datetime
    written_at: datetime
    author: str
    reason: str
    code_version: str
    quantity: Quantity | Absent = field(
        default_factory=lambda: Absent("close the whole open position")
    )
    account: AccountId | Absent = field(
        default_factory=lambda: Absent("the account the entry filled in")
    )
    fx_timestamp: datetime | Absent = field(
        default_factory=lambda: Absent("the fill's own instant")
    )
    fee_fx_rate_to_tax_currency: Decimal | Absent = field(
        default_factory=lambda: Absent("fee is one side of this trade")
    )
    note: str | Absent = field(default_factory=lambda: Absent("no note"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", require_text(self.plan_id, "plan_id"))
        object.__setattr__(
            self, "occurred_at", require_utc(self.occurred_at, "occurred_at")
        )
        object.__setattr__(
            self,
            "written_at",
            _require_filing(self.written_at, self.occurred_at, "exit"),
        )
        object.__setattr__(
            self, "exit_price", _require_price(self.exit_price, "exit price")
        )
        if not isinstance(self.fee, Money):
            raise TypeError("fee must be a Money")
        if self.fee.amount < 0:
            raise CaptureRefusedError(f"fee must not be negative, got {self.fee}")
        for name in ("author", "reason", "fx_source", "code_version"):
            object.__setattr__(self, name, require_text(getattr(self, name), name))
        if not isinstance(self.quantity, (Quantity, Absent)):
            raise TypeError("quantity must be a Quantity or Absent")
        if isinstance(self.quantity, Quantity) and self.quantity.amount <= 0:
            raise CaptureRefusedError(
                f"the size closed must be positive, got {self.quantity}"
            )
        if not isinstance(self.account, (AccountId, Absent)):
            raise TypeError("account must be an AccountId or Absent")

    @property
    def fx_instant(self) -> datetime:
        if isinstance(self.fx_timestamp, Absent):
            return self.occurred_at
        return require_utc(self.fx_timestamp, "fx_timestamp")

    @property
    def exit_reason(self) -> VersionedTerm:
        """The owner's own term, carried verbatim into a counted vocabulary."""
        return VersionedTerm(
            vocabulary_id=EXIT_REASON_VOCABULARY,
            term_id=self.reason,
            taxonomy_version=TAXONOMY_VERSION,
        )


def _closable(view: TradeView, request: CloseRequest) -> tuple[Quantity, AccountId]:
    """How much may be closed and where from, or the reason neither is knowable."""
    if view.status is CaptureStatus.PLANNED:
        raise CaptureRefusedError(
            f"nothing has filled against {view.plan_id}, so there is no position to "
            "close. A commitment that was never taken is closed by letting it "
            "expire, not by recording an exit that did not happen"
        )
    if view.status is CaptureStatus.CLOSED:
        raise CaptureRefusedError(
            f"{view.plan_id} is already flat. Recording a further exit would open a "
            "position in the opposite direction, which is a new decision and "
            "belongs to a new commitment"
        )
    open_quantity = view.open_quantity
    assert isinstance(open_quantity, Quantity)  # OPEN means a folded position
    available = abs(open_quantity)
    closing = available if isinstance(request.quantity, Absent) else request.quantity
    if closing.asset != available.asset:
        raise CaptureRefusedError(
            f"the size closed is stated in {closing.asset} but the open position is "
            f"in {available.asset}"
        )
    if closing > available:
        raise CaptureRefusedError(
            f"{closing} is more than the {available} this commitment has open. "
            "Closing more than is held would record a position the owner never "
            "opened; record the extra as its own trade if that is what happened"
        )
    if isinstance(request.account, AccountId):
        return closing, request.account
    if len(view.accounts) != 1:
        raise CaptureRefusedError(
            f"the fills against {view.plan_id} sit in {len(view.accounts)} accounts "
            f"({', '.join(view.accounts) or 'none'}), so FMITS cannot tell which one "
            "this exit came from. Name it with --account"
        )
    return closing, AccountId(view.accounts[0])


def close_trade(store: TradingStore, request: CloseRequest) -> CaptureOutcome:
    """Record the exit. **Appended as a fill; nothing already stored changes.**

    The entry fill, the commitment and every note about it stay byte-identical
    forever. What "closing" means here is one more `Trade` in the other
    direction, which is what actually happened — and it is why the realized
    profit or loss on the page below is a fold rather than a field somebody typed.

    A reason is required, from the owner's own exit vocabulary. The domain makes
    the identical demand of `OWNER_DECIDED` for the identical purpose: *"the
    reason is the field that makes rejections analysable; without it a rejected
    proposal is a row nobody can learn from."*
    """
    _require_store(store)
    if not isinstance(request, CloseRequest):
        raise TypeError("request must be a CloseRequest")
    before = load_trade(
        store, request.plan_id, dust=CAPTURE_DUST_POLICY, at=request.written_at
    )
    plan = before.plan
    closing, account = _closable(before, request)
    if request.fee.asset not in {plan.market.base_asset, plan.market.quote_asset} and (
        isinstance(request.fee_fx_rate_to_tax_currency, Absent)
    ):
        raise CaptureRefusedError(
            f"the exit fee is denominated in {request.fee.asset}, which is neither "
            f"side of {plan.market.value}. A third-asset fee is its own disposal "
            "and needs its own FX rate at the transaction instant"
        )
    exit_trade = Trade(
        occurred_at=request.occurred_at,
        recorded_at=request.written_at,
        account=account,
        book=plan.book,
        market=plan.market,
        side=_EXIT_SIDE[plan.direction],
        quantity=closing,
        price=request.exit_price,
        fee=request.fee,
        fx_rate_to_tax_currency=request.fx_rate_to_tax_currency,
        fx_source=request.fx_source,
        fx_timestamp=request.fx_instant,
        source=LedgerSource.MANUAL,
        asserted_by=request.author,
        audit=RecordAudit.frozen_at(request.occurred_at),
        fee_fx_rate_to_tax_currency=request.fee_fx_rate_to_tax_currency,
        plan_id=plan.plan_id,
        proposal_id=plan.proposal_id,
    )
    entry = JournalEntry(
        kind=JournalKind.NOTE,
        recorded_at=request.written_at,
        author=request.author,
        audit=RecordAudit.frozen_at(request.written_at),
        title=f"exit: {plan.market.pair_symbol} — {request.reason}",
        body=request.note,
        tags=(
            JournalTag(
                term=request.exit_reason,
                origin=TagOrigin.OWNER,
                applied_at=request.written_at,
            ),
        ),
        links=(_plan_link(plan.plan_id), _trade_link(exit_trade.event_id)),
    )
    write = _write_request(
        written_at=request.written_at,
        author=request.author,
        reason=CLOSE_REASON,
        version_set=capture_version_set(code_version=request.code_version),
    )
    written = (
        _written("trade", store.trades.create(exit_trade, request=write)),
        _written("journal_entry", store.journals.create(entry, request=write)),
    )
    return CaptureOutcome(
        action="closed",
        written=written,
        view=load_trade(
            store, plan.plan_id, dust=CAPTURE_DUST_POLICY, at=request.written_at
        ),
    )


@dataclass(frozen=True, slots=True)
class NoteRequest:
    """One appended note. There is no edit path and there never will be."""

    plan_id: str
    body: str
    recorded_at: datetime
    written_at: datetime
    author: str
    code_version: str
    title: str | Absent = field(default_factory=lambda: Absent("no title"))

    def __post_init__(self) -> None:
        for name in ("plan_id", "body", "author", "code_version"):
            object.__setattr__(self, name, require_text(getattr(self, name), name))
        object.__setattr__(
            self, "recorded_at", require_utc(self.recorded_at, "recorded_at")
        )
        object.__setattr__(
            self,
            "written_at",
            _require_filing(self.written_at, self.recorded_at, "note"),
        )
        if not isinstance(self.title, Absent):
            object.__setattr__(self, "title", require_text(self.title, "title"))


def append_note(store: TradingStore, request: NoteRequest) -> CaptureOutcome:
    """Append one note to a recorded trade. **Append-only, by construction.**

    `JournalRepository` can supersede an entry, and this command does not use
    that path. The owner rewriting a note is not the owner deleting one, and what
    they first wrote is frequently the more interesting record — *"I felt uneasy
    about that one"*, written before a loss, is signal; written after it, it is
    hindsight. Appending keeps both.
    """
    _require_store(store)
    if not isinstance(request, NoteRequest):
        raise TypeError("request must be a NoteRequest")
    plan = load_trade(
        store, request.plan_id, dust=CAPTURE_DUST_POLICY, at=request.written_at
    ).plan
    entry = JournalEntry(
        kind=JournalKind.NOTE,
        recorded_at=request.recorded_at,
        author=request.author,
        audit=RecordAudit.frozen_at(request.recorded_at),
        title=request.title,
        body=request.body,
        links=(_plan_link(plan.plan_id),),
    )
    write = _write_request(
        written_at=request.written_at,
        author=request.author,
        reason=NOTE_REASON,
        version_set=capture_version_set(code_version=request.code_version),
    )
    written = (_written("journal_entry", store.journals.create(entry, request=write)),)
    return CaptureOutcome(
        action="noted",
        written=written,
        view=load_trade(
            store, plan.plan_id, dust=CAPTURE_DUST_POLICY, at=request.written_at
        ),
    )
