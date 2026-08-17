"""`Trade` and `Correction` — the record of what happened to real money.

`Trade` is the brief's *Trade*, and `TradeStatus` is the half of the brief's
*TradeStatus* that belongs to a ledger event.

**This is the only class of value in the whole domain that can simply be wrong.**
Everything else is measured, derived under a versioned policy, or interpreted; a
fill is *asserted*, by the owner or by a venue, and assertions are corrected by
supersession rather than by editing. A trade that did not happen is corrected,
never removed — the correction and the original both stay readable, which is the
difference between *what happened* and *what the owner believed happened*.

**Three owner inputs on the happy path**: filled quantity, filled price, fee.
Everything else is pre-filled from the accepted proposal and the last-used account
for that venue. A model requiring more than three inputs on the happy path fails
the workflow test regardless of how correct it is.

**The identity scope is the one thing that had to be right on the first record.**
`event_id` covers the **economic** fields only. `recorded_at`, `source`,
`asserted_by`, `capture_schema_version`, `venue_trade_id` and `note` are excluded,
following ADR-0027 §3's own precedent for `archived_at`. Including them breaks
idempotency three ways: a fill re-entered twenty minutes after a crash becomes a
second position-moving event; the same fill typed manually and later synced from
the exchange becomes two; and an annotation added a week later becomes a third.
Idempotency is exercised on day one, not in year three.

**No model may create, correct, link or annotate a trade, ever.** There is no
configuration under which that changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from fmis.accounts import AccountId, Book, MarketId
from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.money import AssetCode, Money, Quantity, canonical_decimal_text, parse_decimal
from fmis.provenance import Absent, ValueOrigin, VersionedTerm, decode_maybe, encode_maybe
from fmis.records import (
    ConsumedSource,
    DomainStateError,
    DomainValidationError,
    PayloadDecodeError,
    RecordAudit,
    TradeDomainError,
    build_domain_record_id,
    content_digest_over,
    require_exact_keys,
    require_int,
    require_mapping,
    require_member,
    require_payload_version,
    require_text,
    require_unmodified,
    require_utc,
    validate_domain_record_id,
)

__all__ = [
    "LedgerError",
    "IllegalTradeTransitionError",
    "TRADE_SCHEMA_VERSION",
    "SUPPORTED_TRADE_VERSIONS",
    "TRADE_TYPE_SLUG",
    "TRADE_KIND",
    "CORRECTION_SCHEMA_VERSION",
    "SUPPORTED_CORRECTION_VERSIONS",
    "CORRECTION_TYPE_SLUG",
    "CORRECTION_KIND",
    "LedgerEventKind",
    "LedgerSource",
    "TradeSide",
    "TradeStatus",
    "TRADE_STATUS_TRANSITIONS",
    "advance_trade_status",
    "BalanceEffect",
    "Trade",
    "Correction",
    "balance_effects",
]

TRADE_SCHEMA_VERSION = 1
SUPPORTED_TRADE_VERSIONS = frozenset({1})
TRADE_TYPE_SLUG = "trade"
TRADE_KIND = "trade"

CORRECTION_SCHEMA_VERSION = 1
SUPPORTED_CORRECTION_VERSIONS = frozenset({1})
CORRECTION_TYPE_SLUG = "correction"
CORRECTION_KIND = "correction"


class LedgerError(TradeDomainError):
    """Base class for every ledger failure."""


class IllegalTradeTransitionError(DomainStateError, LedgerError):
    """A trade status change the lifecycle does not permit."""


class LedgerEventKind(Enum):
    """The six kinds of economic event, as a closed vocabulary.

    All six are named because the enum is closed and extension is a
    capture-schema version bump; **two have record types in this milestone**
    (`TRADE` and `CORRECTION`). The other four are additive and belong to the
    slice that first builds them — enumerating a kind is not the same as needing
    it, and building four record types nothing reads would be weight without
    value.
    """

    TRADE = "trade"
    TRANSFER = "transfer"
    REWARD = "reward"
    STANDALONE_FEE = "standalone_fee"
    ADJUSTMENT = "adjustment"
    CORRECTION = "correction"


class LedgerSource(Enum):
    """How FMITS came to know about the event.

    Excluded from `event_id` on purpose: the same fill typed by hand and later
    synced from the exchange is **one** event, and a digest that separated them
    would double-count every manual fill on the day sync ships.
    """

    MANUAL = "manual"
    STATEMENT_IMPORT = "statement_import"
    EXCHANGE_API = "exchange_api"
    #: A fill **no venue produced and the owner did not type**: computed by the
    #: paper simulator from a closed candle under a named, versioned fill policy.
    #: Its own member rather than `MANUAL`, because a surface that cannot tell a
    #: simulated fill from an asserted one is rendering a lie of omission — and
    #: because the day a real fill and a simulated one sit in the same list, the
    #: distinction has to be a field rather than a memory of which book was used.
    PAPER_SIMULATION = "paper_simulation"


class TradeSide(Enum):
    """Which way the base asset moved."""

    BUY = "buy"
    SELL = "sell"

    @property
    def base_sign(self) -> int:
        return 1 if self is TradeSide.BUY else -1

    @property
    def quote_sign(self) -> int:
        return -self.base_sign


class TradeStatus(Enum):
    """A trade's own lifecycle: `Draft → Recorded → (optionally) Superseded`.

    **Only `DRAFT` and `RECORDED` are ever stored.** `SUPERSEDED` is produced by
    the resolver from the correction chain and is never a field on a `Trade` —
    storing it would be a second representation of a fact the chain already holds,
    and the two would eventually disagree. That is Law 1 at its most concrete: a
    trade that "knows" it is superseded and a correction that says so are two
    places one fact can rot.
    """

    DRAFT = "draft"
    RECORDED = "recorded"
    SUPERSEDED = "superseded"


#: The whole legal machine. `DRAFT → SUPERSEDED` is illegal because a draft was
#: never in the ledger and there is nothing to supersede; `SUPERSEDED → anything`
#: is illegal because a superseded event is history, and `RECORDED → DRAFT` is
#: illegal because un-recording is what a `Correction` exists to avoid.
TRADE_STATUS_TRANSITIONS: Mapping[TradeStatus, frozenset[TradeStatus]] = (
    MappingProxyType(
        {
            TradeStatus.DRAFT: frozenset({TradeStatus.RECORDED}),
            TradeStatus.RECORDED: frozenset({TradeStatus.SUPERSEDED}),
            TradeStatus.SUPERSEDED: frozenset(),
        }
    )
)

#: What may be written onto a record. `SUPERSEDED` is derived, never asserted.
STORABLE_TRADE_STATUSES: frozenset[TradeStatus] = frozenset(
    {TradeStatus.DRAFT, TradeStatus.RECORDED}
)


def advance_trade_status(current: TradeStatus, target: TradeStatus) -> TradeStatus:
    """Move a trade's status, refusing every transition the machine forbids."""
    require_member(current, TradeStatus, "current")
    require_member(target, TradeStatus, "target")
    allowed = TRADE_STATUS_TRANSITIONS[current]
    if target not in allowed:
        raise IllegalTradeTransitionError(
            f"a {current.value} trade cannot become {target.value}. Legal here: "
            f"{sorted(status.value for status in allowed) or ['(terminal — nothing)']}"
        )
    return target


@dataclass(frozen=True, slots=True)
class BalanceEffect:
    """One signed movement of one asset in one account.

    Produced by `balance_effects()`, **never stored**. *"If two fields could ever
    disagree about the same fact, one of them is not a field"* — a stored posting
    beside the trade that produced it is exactly that pair.
    """

    account: AccountId
    quantity: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.account, AccountId):
            raise TypeError("account must be an AccountId")
        if not isinstance(self.quantity, Quantity):
            raise TypeError("quantity must be a Quantity")

    @property
    def asset(self) -> AssetCode:
        return self.quantity.asset

    def __str__(self) -> str:
        return f"{self.quantity} @ {self.account}"


@dataclass(frozen=True, slots=True)
class Trade:
    """One exchange of one asset for another, at a price, at an instant, in a book."""

    occurred_at: datetime
    recorded_at: datetime
    account: AccountId
    book: Book
    market: MarketId
    side: TradeSide
    quantity: Quantity
    price: Decimal
    fee: Money
    fx_rate_to_tax_currency: Decimal
    fx_source: str
    fx_timestamp: datetime
    source: LedgerSource
    asserted_by: str
    audit: RecordAudit
    status: TradeStatus = TradeStatus.RECORDED
    reported_at: datetime | Absent = field(default_factory=lambda: Absent("not imported"))
    occurrence_index: int | Absent = field(
        default_factory=lambda: Absent("no identical-instant collision reported")
    )
    fee_fx_rate_to_tax_currency: Decimal | Absent = field(
        default_factory=lambda: Absent("fee is one side of this trade")
    )
    order_id: str | Absent = field(default_factory=lambda: Absent("no order recorded"))
    plan_id: str | Absent = field(default_factory=lambda: Absent("no plan"))
    proposal_id: str | Absent = field(default_factory=lambda: Absent("no proposal"))
    is_maker: bool | Absent = field(default_factory=lambda: Absent("not reported"))
    venue_trade_id: str | Absent = field(default_factory=lambda: Absent("not reported"))
    note: str | Absent = field(default_factory=lambda: Absent("no note"))
    schema_version: int = TRADE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "occurred_at", require_utc(self.occurred_at, "occurred_at"))
        object.__setattr__(self, "recorded_at", require_utc(self.recorded_at, "recorded_at"))
        if self.recorded_at < self.occurred_at:
            raise DomainValidationError(
                f"recorded_at {self.recorded_at.isoformat()} precedes occurred_at "
                f"{self.occurred_at.isoformat()}; FMITS cannot learn of a fill "
                "before it happened"
            )
        if not isinstance(self.account, AccountId):
            raise TypeError("account must be an AccountId")
        require_member(self.book, Book, "book")
        if not isinstance(self.market, MarketId):
            raise TypeError("market must be a MarketId")
        require_member(self.side, TradeSide, "side")
        if not isinstance(self.quantity, Quantity):
            raise TypeError("quantity must be a Quantity")
        if self.quantity.amount <= 0:
            raise DomainValidationError(
                f"quantity must be positive, got {self.quantity}; direction is "
                "carried by `side`, and a signed quantity would be the same fact "
                "in two places"
            )
        if self.quantity.asset != self.market.base_asset:
            raise DomainValidationError(
                f"quantity is denominated in {self.quantity.asset} but the market "
                f"trades {self.market.base_asset} as its base asset"
            )
        if not isinstance(self.price, Decimal):
            raise TypeError(f"price must be a Decimal, got {type(self.price).__name__}")
        if self.price <= 0:
            raise DomainValidationError(f"price must be positive, got {self.price}")
        object.__setattr__(self, "price", Decimal(canonical_decimal_text(self.price)))
        if not isinstance(self.fee, Money):
            raise TypeError("fee must be a Money")
        if self.fee.amount < 0:
            raise DomainValidationError(
                f"fee must not be negative, got {self.fee}; a rebate is a "
                "different economic fact and is recorded as its own event"
            )
        if not isinstance(self.fx_rate_to_tax_currency, Decimal):
            raise TypeError("fx_rate_to_tax_currency must be a Decimal")
        if self.fx_rate_to_tax_currency <= 0:
            raise DomainValidationError(
                "fx_rate_to_tax_currency must be positive; it is unrecoverable "
                "retroactively, which is why it is required from the first record"
            )
        object.__setattr__(
            self,
            "fx_rate_to_tax_currency",
            Decimal(canonical_decimal_text(self.fx_rate_to_tax_currency)),
        )
        object.__setattr__(self, "fx_source", require_text(self.fx_source, "fx_source"))
        object.__setattr__(
            self, "fx_timestamp", require_utc(self.fx_timestamp, "fx_timestamp")
        )
        require_member(self.source, LedgerSource, "source")
        object.__setattr__(
            self, "asserted_by", require_text(self.asserted_by, "asserted_by")
        )
        require_unmodified(self.audit, "Trade")
        require_member(self.status, TradeStatus, "status")
        if self.status not in STORABLE_TRADE_STATUSES:
            raise DomainValidationError(
                f"{self.status.value} is derived from the correction chain and is "
                "never stored on a trade; a trade records DRAFT or RECORDED and "
                "the resolver reports the rest"
            )
        if not isinstance(self.reported_at, Absent):
            object.__setattr__(
                self, "reported_at", require_utc(self.reported_at, "reported_at")
            )
        if not isinstance(self.occurrence_index, Absent):
            require_int(self.occurrence_index, "occurrence_index", minimum=1)
        self._validate_fee_asset()
        for name in ("order_id", "plan_id", "proposal_id", "venue_trade_id", "note"):
            value = getattr(self, name)
            if not isinstance(value, Absent):
                object.__setattr__(self, name, require_text(value, name))
        if not isinstance(self.proposal_id, Absent):
            validate_domain_record_id(self.proposal_id)
        if not isinstance(self.is_maker, (bool, Absent)):
            raise TypeError("is_maker must be a bool or Absent")
        if self.schema_version not in SUPPORTED_TRADE_VERSIONS:
            raise DomainValidationError(
                f"trade schema_version {self.schema_version} is not one this build "
                f"writes ({sorted(SUPPORTED_TRADE_VERSIONS)})"
            )

    def _validate_fee_asset(self) -> None:
        """The fee rule, stated once and enforced here (AP-D3b).

        A fee denominated in an asset that is neither side of the event **is
        itself a disposal**, produces its own balance effect, and requires its own
        FX rate. Paying a BTC/USDT fee in BNB is a BNB disposal with a tax
        consequence, and a record that carries no rate for it is permanently
        untaxable.
        """
        sides = {self.market.base_asset, self.market.quote_asset}
        third_asset = self.fee.asset not in sides
        if third_asset and isinstance(self.fee_fx_rate_to_tax_currency, Absent):
            raise DomainValidationError(
                f"the fee is denominated in {self.fee.asset}, which is neither "
                f"{self.market.base_asset} nor {self.market.quote_asset}. A "
                "third-asset fee is its own disposal and requires its own FX rate "
                "at the transaction instant — a rate that cannot be recovered later"
            )
        if not third_asset and not isinstance(self.fee_fx_rate_to_tax_currency, Absent):
            raise DomainValidationError(
                "fee_fx_rate_to_tax_currency applies only to a fee in a third "
                "asset; the trade's own rate already covers a fee on either side"
            )
        if not isinstance(self.fee_fx_rate_to_tax_currency, Absent):
            if not isinstance(self.fee_fx_rate_to_tax_currency, Decimal):
                raise TypeError("fee_fx_rate_to_tax_currency must be a Decimal or Absent")
            if self.fee_fx_rate_to_tax_currency <= 0:
                raise DomainValidationError(
                    "fee_fx_rate_to_tax_currency must be positive"
                )
            object.__setattr__(
                self,
                "fee_fx_rate_to_tax_currency",
                Decimal(canonical_decimal_text(self.fee_fx_rate_to_tax_currency)),
            )

    # -- projections ---------------------------------------------------------

    @property
    def kind(self) -> LedgerEventKind:
        return LedgerEventKind.TRADE

    @property
    def origin(self) -> ValueOrigin:
        """`ASSERTED`. The only class of value in the domain that can be wrong."""
        return ValueOrigin.ASSERTED

    @property
    def gross_consideration(self) -> Money:
        """`quantity × price` in the quote asset — a product, never a quotient."""
        return self.quantity.value_at(self.price, self.market.quote_asset)

    def recorded(self) -> Trade:
        """Promote a draft to a recorded event, through the status machine."""
        advance_trade_status(self.status, TradeStatus.RECORDED)
        return _replace_status(self, TradeStatus.RECORDED)

    # -- identity and serialization -----------------------------------------

    @property
    def digest_basis(self) -> dict[str, Any]:
        """The **economic** fields, and nothing else.

        Excluded, each for a stated reason:
        `recorded_at` (when a crashed scan was restarted must not create an
        event) · `source` and `asserted_by` (manual entry and exchange sync
        describe one fill) · `schema_version` (a reader upgrade must not re-key
        history) · `venue_trade_id` (supplied later by sync for a fill already
        typed) · `note` and `status` (annotations and derived state).
        """
        return {
            "kind": self.kind.value,
            "occurred_at": encode_timestamp(self.occurred_at),
            "account": self.account.value,
            "book": self.book.value,
            "market": self.market.to_payload(),
            "side": self.side.value,
            "quantity": self.quantity.to_payload(),
            "price": canonical_decimal_text(self.price),
            "fee": self.fee.to_payload(),
            "fx_rate_to_tax_currency": canonical_decimal_text(
                self.fx_rate_to_tax_currency
            ),
            "fx_source": self.fx_source,
            "fx_timestamp": encode_timestamp(self.fx_timestamp),
            "fee_fx_rate_to_tax_currency": encode_maybe(
                self.fee_fx_rate_to_tax_currency, canonical_decimal_text
            ),
            "occurrence_index": encode_maybe(self.occurrence_index, int),
            "reported_at": encode_maybe(self.reported_at, encode_timestamp),
            "order_id": encode_maybe(self.order_id, str),
            "plan_id": encode_maybe(self.plan_id, str),
            "proposal_id": encode_maybe(self.proposal_id, str),
            "is_maker": encode_maybe(self.is_maker, bool),
        }

    @property
    def event_id(self) -> str:
        return build_domain_record_id(
            type_slug=TRADE_TYPE_SLUG,
            subject=self.market.value,
            moment=self.occurred_at,
            digest=content_digest_over(self.digest_basis),
        )

    @property
    def content_digest(self) -> str:
        return content_digest_over(self.digest_basis)

    def as_consumed_source(self) -> ConsumedSource:
        return ConsumedSource(
            record_id=self.event_id,
            content_digest=self.content_digest,
            kind=TRADE_KIND,
        )

    def to_payload(self) -> dict[str, Any]:
        payload = self.digest_basis
        payload.update(
            {
                "schema_version": self.schema_version,
                "event_id": self.event_id,
                "recorded_at": encode_timestamp(self.recorded_at),
                "source": self.source.value,
                "asserted_by": self.asserted_by,
                "status": self.status.value,
                "venue_trade_id": encode_maybe(self.venue_trade_id, str),
                "note": encode_maybe(self.note, str),
                "audit": self.audit.to_payload(),
            }
        )
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> Trade:
        mapping = require_mapping(raw, "trade")
        version = require_payload_version(
            mapping, supported=SUPPORTED_TRADE_VERSIONS, entity="trade"
        )
        require_exact_keys(mapping, _TRADE_KEYS, "trade")
        if mapping["kind"] != LedgerEventKind.TRADE.value:
            raise PayloadDecodeError(
                f"payload kind {mapping['kind']!r} is not a trade"
            )
        decoded = cls(
            occurred_at=decode_timestamp(mapping["occurred_at"]),
            recorded_at=decode_timestamp(mapping["recorded_at"]),
            account=AccountId(str(mapping["account"])),
            book=_member(Book, mapping["book"], "book"),
            market=MarketId.from_payload(mapping["market"], "trade market"),
            side=_member(TradeSide, mapping["side"], "side"),
            quantity=Quantity.from_payload(mapping["quantity"], "quantity"),
            price=parse_decimal(mapping["price"], "price"),
            fee=Money.from_payload(mapping["fee"], "fee"),
            fx_rate_to_tax_currency=parse_decimal(
                mapping["fx_rate_to_tax_currency"], "fx_rate_to_tax_currency"
            ),
            fx_source=str(mapping["fx_source"]),
            fx_timestamp=decode_timestamp(mapping["fx_timestamp"]),
            source=_member(LedgerSource, mapping["source"], "source"),
            asserted_by=str(mapping["asserted_by"]),
            audit=RecordAudit.from_payload(mapping["audit"]),
            status=_member(TradeStatus, mapping["status"], "status"),
            reported_at=decode_maybe(mapping["reported_at"], decode_timestamp),
            occurrence_index=decode_maybe(mapping["occurrence_index"], _as_int),
            fee_fx_rate_to_tax_currency=decode_maybe(
                mapping["fee_fx_rate_to_tax_currency"],
                lambda value: parse_decimal(value, "fee_fx_rate_to_tax_currency"),
            ),
            order_id=decode_maybe(mapping["order_id"], str),
            plan_id=decode_maybe(mapping["plan_id"], str),
            proposal_id=decode_maybe(mapping["proposal_id"], str),
            is_maker=decode_maybe(mapping["is_maker"], _as_bool),
            venue_trade_id=decode_maybe(mapping["venue_trade_id"], str),
            note=decode_maybe(mapping["note"], str),
            schema_version=version,
        )
        if mapping["event_id"] != decoded.event_id:
            raise PayloadDecodeError(
                f"event_id {mapping['event_id']!r} does not match the digest of "
                f"the economic fields it claims to identify ({decoded.event_id!r})"
            )
        return decoded


_TRADE_KEYS = frozenset({
    "schema_version",
    "event_id",
    "kind",
    "occurred_at",
    "recorded_at",
    "account",
    "book",
    "market",
    "side",
    "quantity",
    "price",
    "fee",
    "fx_rate_to_tax_currency",
    "fx_source",
    "fx_timestamp",
    "fee_fx_rate_to_tax_currency",
    "occurrence_index",
    "reported_at",
    "order_id",
    "plan_id",
    "proposal_id",
    "is_maker",
    "source",
    "asserted_by",
    "status",
    "venue_trade_id",
    "note",
    "audit",
})


def _replace_status(trade: Trade, status: TradeStatus) -> Trade:
    return Trade(
        occurred_at=trade.occurred_at,
        recorded_at=trade.recorded_at,
        account=trade.account,
        book=trade.book,
        market=trade.market,
        side=trade.side,
        quantity=trade.quantity,
        price=trade.price,
        fee=trade.fee,
        fx_rate_to_tax_currency=trade.fx_rate_to_tax_currency,
        fx_source=trade.fx_source,
        fx_timestamp=trade.fx_timestamp,
        source=trade.source,
        asserted_by=trade.asserted_by,
        audit=trade.audit,
        status=status,
        reported_at=trade.reported_at,
        occurrence_index=trade.occurrence_index,
        fee_fx_rate_to_tax_currency=trade.fee_fx_rate_to_tax_currency,
        order_id=trade.order_id,
        plan_id=trade.plan_id,
        proposal_id=trade.proposal_id,
        is_maker=trade.is_maker,
        venue_trade_id=trade.venue_trade_id,
        note=trade.note,
        schema_version=trade.schema_version,
    )


@dataclass(frozen=True, slots=True)
class Correction:
    """Records that a prior event, as recorded, was wrong — without editing it.

    Carries the **replacement values in full**, so resolution is a lookup rather
    than a merge, and two live corrections of one event is a rejected state rather
    than a field-by-field reconciliation nobody can audit.

    A correction is itself correctable: a chain is legal and ordered. What is not
    legal is a *branch* — two corrections superseding the same event — because
    then "what actually happened" has two answers and the resolver would have to
    pick one.
    """

    supersedes: str
    replacement: Trade
    reason: VersionedTerm
    author: str
    occurred_at: datetime
    recorded_at: datetime
    audit: RecordAudit
    note: str | Absent = field(default_factory=lambda: Absent("no note"))
    schema_version: int = CORRECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_domain_record_id(self.supersedes)
        if not isinstance(self.replacement, Trade):
            raise TypeError("replacement must be a Trade")
        if self.replacement.status is not TradeStatus.RECORDED:
            raise DomainValidationError(
                "a correction's replacement is a recorded event; correcting an "
                "event with a draft would put a value into the ledger that was "
                "never asserted"
            )
        if self.replacement.event_id == self.supersedes:
            raise DomainValidationError(
                "the replacement is byte-identical to the event it supersedes; "
                "re-submitting identical content is an idempotent success, not a "
                "correction"
            )
        if not isinstance(self.reason, VersionedTerm):
            raise TypeError(
                "reason must be a VersionedTerm from the correction-reason "
                "vocabulary; an untagged correction cannot be counted"
            )
        object.__setattr__(self, "author", require_text(self.author, "author"))
        object.__setattr__(
            self, "occurred_at", require_utc(self.occurred_at, "occurred_at")
        )
        object.__setattr__(
            self, "recorded_at", require_utc(self.recorded_at, "recorded_at")
        )
        if self.recorded_at < self.occurred_at:
            raise DomainValidationError(
                "recorded_at precedes occurred_at on a correction"
            )
        require_unmodified(self.audit, "Correction")
        if not isinstance(self.note, Absent):
            object.__setattr__(self, "note", require_text(self.note, "note"))
        if self.schema_version not in SUPPORTED_CORRECTION_VERSIONS:
            raise DomainValidationError(
                f"correction schema_version {self.schema_version} is not one this "
                f"build writes ({sorted(SUPPORTED_CORRECTION_VERSIONS)})"
            )

    @property
    def kind(self) -> LedgerEventKind:
        return LedgerEventKind.CORRECTION

    @property
    def origin(self) -> ValueOrigin:
        return ValueOrigin.ASSERTED

    @property
    def digest_basis(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "supersedes": self.supersedes,
            "replacement": self.replacement.digest_basis,
            "reason": self.reason.to_payload(),
            "occurred_at": encode_timestamp(self.occurred_at),
        }

    @property
    def event_id(self) -> str:
        return build_domain_record_id(
            type_slug=CORRECTION_TYPE_SLUG,
            subject=self.replacement.market.value,
            moment=self.occurred_at,
            digest=content_digest_over(self.digest_basis),
        )

    @property
    def content_digest(self) -> str:
        return content_digest_over(self.digest_basis)

    def as_consumed_source(self) -> ConsumedSource:
        return ConsumedSource(
            record_id=self.event_id,
            content_digest=self.content_digest,
            kind=CORRECTION_KIND,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "kind": self.kind.value,
            "supersedes": self.supersedes,
            "replacement": self.replacement.to_payload(),
            "reason": self.reason.to_payload(),
            "author": self.author,
            "occurred_at": encode_timestamp(self.occurred_at),
            "recorded_at": encode_timestamp(self.recorded_at),
            "note": encode_maybe(self.note, str),
            "audit": self.audit.to_payload(),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> Correction:
        mapping = require_mapping(raw, "correction")
        version = require_payload_version(
            mapping, supported=SUPPORTED_CORRECTION_VERSIONS, entity="correction"
        )
        require_exact_keys(
            mapping,
            {
                "schema_version",
                "event_id",
                "kind",
                "supersedes",
                "replacement",
                "reason",
                "author",
                "occurred_at",
                "recorded_at",
                "note",
                "audit",
            },
            "correction",
        )
        if mapping["kind"] != LedgerEventKind.CORRECTION.value:
            raise PayloadDecodeError(
                f"payload kind {mapping['kind']!r} is not a correction"
            )
        decoded = cls(
            supersedes=str(mapping["supersedes"]),
            replacement=Trade.from_payload(mapping["replacement"]),
            reason=VersionedTerm.from_payload(mapping["reason"]),
            author=str(mapping["author"]),
            occurred_at=decode_timestamp(mapping["occurred_at"]),
            recorded_at=decode_timestamp(mapping["recorded_at"]),
            audit=RecordAudit.from_payload(mapping["audit"]),
            note=decode_maybe(mapping["note"], str),
            schema_version=version,
        )
        if mapping["event_id"] != decoded.event_id:
            raise PayloadDecodeError(
                f"event_id {mapping['event_id']!r} does not match the digest of "
                f"the correction it claims to identify ({decoded.event_id!r})"
            )
        return decoded


def balance_effects(trade: Trade) -> tuple[BalanceEffect, ...]:
    """`trade → ((asset, account, signed quantity), …)`. A pure function.

    **Never a stored field.** Every downstream reading — the position fold, the
    portfolio composition, and the tax engine when it arrives — derives its
    reading from *this function* and never independently reinterprets the raw
    event fields. Without that single-interpreter rule the repository acquires two
    definitions of what a trade means, one for performance and one for tax, and
    they drift.

    Three movements on the happy path, four when the fee is a third asset:
    the base asset in or out, the quote asset the other way, and the fee out.
    """
    if not isinstance(trade, Trade):
        raise TypeError(f"trade must be a Trade, got {type(trade).__name__}")
    base_amount = trade.quantity.amount * trade.side.base_sign
    quote_amount = (
        trade.quantity.amount * trade.price * trade.side.quote_sign
    )
    effects = [
        BalanceEffect(trade.account, Quantity(base_amount, trade.market.base_asset)),
        BalanceEffect(trade.account, Quantity(quote_amount, trade.market.quote_asset)),
    ]
    if not trade.fee.is_zero:
        effects.append(
            BalanceEffect(trade.account, Quantity(-trade.fee.amount, trade.fee.asset))
        )
    return tuple(effects)


def _member(enum_type: Any, value: Any, entity: str) -> Any:
    try:
        return enum_type(value)
    except ValueError as error:
        raise PayloadDecodeError(
            f"{entity} {value!r} is not a known {enum_type.__name__}; an unknown "
            "member is a clean rejection, never a default"
        ) from error


def _as_int(raw: Any) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise PayloadDecodeError(f"expected an int, got {type(raw).__name__}")
    return raw


def _as_bool(raw: Any) -> bool:
    if not isinstance(raw, bool):
        raise PayloadDecodeError(f"expected a bool, got {type(raw).__name__}")
    return raw
