"""`PortfolioSnapshot` — one valued observation, frozen with every input it used.

The brief calls this *PortfolioSummary*. The data model's name is
`PortfolioSnapshot`, and the difference is not cosmetic: four different objects
were all being called "a snapshot", and the rule that came out of resolving them
is that **no name in this domain uses "snapshot" without a qualifier**. A
*summary* implies a derived convenience; this is the only place historical
portfolio state exists.

Three rules, and the first is the one everything else depends on.

**It is never recomputed from live data.** *"A snapshot stores the marks and rates
it used."* A drawdown series recomputed in 2031 against a 2031 view of 2026 prices
is a *different series*, and nothing can say which is right.

**A missing mark is a first-class `Absent(reason)`, never a zero.** *"A zero makes
the total look plausible and survives for years."* `total_value` returns `Absent`
naming the unmarked holdings rather than a number that quietly excludes them.

**Flows since the previous snapshot are required.** Without them a deposit looks
like a gain, and every return figure in the product is wrong.

**There is no composite portfolio score, health grade or risk rating here, and
there never will be.** *"A single number would collapse all three strata into one
value whose meaning no one could recover."*
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from fmis.accounts import AccountId, Book
from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.money import AssetCode, Money, Quantity, canonical_decimal_text, parse_decimal
from fmis.positions import ReconciliationState
from fmis.provenance import Absent, ValueOrigin, decode_maybe, encode_maybe
from fmis.records import (
    IDENTIFIER_PATTERN,
    ConsumedSource,
    DomainValidationError,
    PayloadDecodeError,
    RecordAudit,
    TradeDomainError,
    build_domain_record_id,
    content_digest_over,
    decode_consumed_sources,
    encode_consumed_sources,
    normalize_consumed_sources,
    require_exact_keys,
    require_mapping,
    require_member,
    require_pattern,
    require_payload_version,
    require_text,
    require_tuple_of,
    require_unmodified,
    require_utc,
)
from fmis.versioning import VersionSet

__all__ = [
    "PortfolioError",
    "PORTFOLIO_SNAPSHOT_SCHEMA_VERSION",
    "SUPPORTED_PORTFOLIO_SNAPSHOT_VERSIONS",
    "PORTFOLIO_SNAPSHOT_TYPE_SLUG",
    "PORTFOLIO_SNAPSHOT_KIND",
    "MarkQuote",
    "Holding",
    "CashBalance",
    "FlowSummary",
    "ExposureSummary",
    "AllocationEntry",
    "PortfolioSnapshot",
]

PORTFOLIO_SNAPSHOT_SCHEMA_VERSION = 1
SUPPORTED_PORTFOLIO_SNAPSHOT_VERSIONS = frozenset({1})
PORTFOLIO_SNAPSHOT_TYPE_SLUG = "portfolio_snapshot"
PORTFOLIO_SNAPSHOT_KIND = "portfolio_snapshot"


class PortfolioError(TradeDomainError):
    """Base class for every portfolio failure."""


@dataclass(frozen=True, slots=True)
class MarkQuote:
    """One price, its source, and when it was true — frozen into the snapshot.

    `as_of` is not the snapshot's instant. A mark read at 22:00 and frozen into a
    22:15 snapshot is fifteen minutes stale, and a reader is entitled to see that
    rather than infer it.
    """

    price: Decimal
    quote_asset: AssetCode
    source: str
    as_of: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.price, Decimal):
            raise TypeError(f"price must be a Decimal, got {type(self.price).__name__}")
        if self.price <= 0:
            raise DomainValidationError(f"mark price must be positive, got {self.price}")
        object.__setattr__(self, "price", Decimal(canonical_decimal_text(self.price)))
        if not isinstance(self.quote_asset, AssetCode):
            object.__setattr__(self, "quote_asset", AssetCode(self.quote_asset))
        object.__setattr__(self, "source", require_text(self.source, "source"))
        object.__setattr__(self, "as_of", require_utc(self.as_of, "as_of"))

    def staleness_at(self, moment: datetime) -> Any:
        return require_utc(moment, "moment") - self.as_of

    def to_payload(self) -> dict[str, Any]:
        return {
            "price": canonical_decimal_text(self.price),
            "quote_asset": self.quote_asset.code,
            "source": self.source,
            "as_of": encode_timestamp(self.as_of),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> MarkQuote:
        mapping = require_mapping(raw, "mark")
        require_exact_keys(mapping, {"price", "quote_asset", "source", "as_of"}, "mark")
        return cls(
            price=parse_decimal(mapping["price"], "mark price"),
            quote_asset=AssetCode(str(mapping["quote_asset"])),
            source=str(mapping["source"]),
            as_of=decode_timestamp(mapping["as_of"]),
        )


@dataclass(frozen=True, slots=True)
class Holding:
    """What is held, where, and what it was worth — or why that is unknown."""

    asset: AssetCode
    account: AccountId
    quantity: Quantity
    mark: MarkQuote | Absent
    reconciliation: ReconciliationState = ReconciliationState.UNRECONCILED

    def __post_init__(self) -> None:
        if not isinstance(self.asset, AssetCode):
            object.__setattr__(self, "asset", AssetCode(self.asset))
        if not isinstance(self.account, AccountId):
            raise TypeError("account must be an AccountId")
        if not isinstance(self.quantity, Quantity):
            raise TypeError("quantity must be a Quantity")
        if self.quantity.asset != self.asset:
            raise DomainValidationError(
                f"holding is of {self.asset} but the quantity is in "
                f"{self.quantity.asset}"
            )
        if not isinstance(self.mark, (MarkQuote, Absent)):
            raise TypeError("mark must be a MarkQuote or Absent")
        require_member(self.reconciliation, ReconciliationState, "reconciliation")

    @property
    def value(self) -> Money | Absent:
        """`quantity × mark`, or the reason there is no value."""
        if isinstance(self.mark, Absent):
            return self.mark
        return self.quantity.value_at(self.mark.price, self.mark.quote_asset)

    def to_payload(self) -> dict[str, Any]:
        return {
            "asset": self.asset.code,
            "account": self.account.value,
            "quantity": self.quantity.to_payload(),
            "mark": encode_maybe(self.mark, MarkQuote.to_payload),
            "reconciliation": self.reconciliation.value,
        }

    @classmethod
    def from_payload(cls, raw: Any) -> Holding:
        mapping = require_mapping(raw, "holding")
        require_exact_keys(
            mapping,
            {"asset", "account", "quantity", "mark", "reconciliation"},
            "holding",
        )
        return cls(
            asset=AssetCode(str(mapping["asset"])),
            account=AccountId(str(mapping["account"])),
            quantity=Quantity.from_payload(mapping["quantity"], "holding quantity"),
            mark=decode_maybe(mapping["mark"], MarkQuote.from_payload),
            reconciliation=_member(
                ReconciliationState, mapping["reconciliation"], "reconciliation"
            ),
        )


@dataclass(frozen=True, slots=True)
class CashBalance:
    """Cash in one currency in one account, with the rate used to value it.

    **Never a stored balance field on an account.** A stored balance is a
    reconciliation bug waiting to be written; this is a *frozen observation* of a
    fold, which is a different thing and carries the rate that made it comparable.
    """

    account: AccountId
    amount: Money
    fx_rate_to_base: Decimal | Absent
    fx_source: str | Absent = field(default_factory=lambda: Absent("no rate applied"))

    def __post_init__(self) -> None:
        if not isinstance(self.account, AccountId):
            raise TypeError("account must be an AccountId")
        if not isinstance(self.amount, Money):
            raise TypeError("amount must be a Money")
        if not isinstance(self.fx_rate_to_base, Absent):
            if not isinstance(self.fx_rate_to_base, Decimal):
                raise TypeError("fx_rate_to_base must be a Decimal or Absent")
            if self.fx_rate_to_base <= 0:
                raise DomainValidationError("fx_rate_to_base must be positive")
            object.__setattr__(
                self,
                "fx_rate_to_base",
                Decimal(canonical_decimal_text(self.fx_rate_to_base)),
            )
            if isinstance(self.fx_source, Absent):
                raise DomainValidationError(
                    "a rate without a source cannot be checked; every conversion "
                    "carries the rate and where it came from"
                )
        if not isinstance(self.fx_source, Absent):
            object.__setattr__(self, "fx_source", require_text(self.fx_source, "fx_source"))

    def value_in_base(self, base: AssetCode) -> Money | Absent:
        if self.amount.asset == base:
            return self.amount
        if isinstance(self.fx_rate_to_base, Absent):
            return Absent(
                f"no rate from {self.amount.asset} to {base} was frozen with this "
                "snapshot"
            )
        return Money(self.amount.amount * self.fx_rate_to_base, base)

    def to_payload(self) -> dict[str, Any]:
        return {
            "account": self.account.value,
            "amount": self.amount.to_payload(),
            "fx_rate_to_base": encode_maybe(self.fx_rate_to_base, canonical_decimal_text),
            "fx_source": encode_maybe(self.fx_source, str),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> CashBalance:
        mapping = require_mapping(raw, "cash balance")
        require_exact_keys(
            mapping, {"account", "amount", "fx_rate_to_base", "fx_source"}, "cash"
        )
        return cls(
            account=AccountId(str(mapping["account"])),
            amount=Money.from_payload(mapping["amount"], "cash amount"),
            fx_rate_to_base=decode_maybe(
                mapping["fx_rate_to_base"],
                lambda value: parse_decimal(value, "fx_rate_to_base"),
            ),
            fx_source=decode_maybe(mapping["fx_source"], str),
        )


@dataclass(frozen=True, slots=True)
class FlowSummary:
    """Deposits and withdrawals since the previous snapshot. **Required.**

    Without them a deposit looks like a gain. `since` is `Absent` only on the very
    first snapshot, and that absence carries its reason rather than being an
    implicit zero.
    """

    deposits: Money
    withdrawals: Money
    since: datetime | Absent

    def __post_init__(self) -> None:
        for name in ("deposits", "withdrawals"):
            value = getattr(self, name)
            if not isinstance(value, Money):
                raise TypeError(f"{name} must be a Money")
            if value.amount < 0:
                raise DomainValidationError(
                    f"{name} is stated as a positive magnitude; direction is "
                    "carried by which field it is in"
                )
        if self.deposits.asset != self.withdrawals.asset:
            raise DomainValidationError(
                "deposits and withdrawals are stated in one currency; two would "
                "need a rate this record does not carry"
            )
        if not isinstance(self.since, Absent):
            object.__setattr__(self, "since", require_utc(self.since, "since"))

    @property
    def net(self) -> Money:
        return self.deposits - self.withdrawals

    def to_payload(self) -> dict[str, Any]:
        return {
            "deposits": self.deposits.to_payload(),
            "withdrawals": self.withdrawals.to_payload(),
            "since": encode_maybe(self.since, encode_timestamp),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> FlowSummary:
        mapping = require_mapping(raw, "flows")
        require_exact_keys(mapping, {"deposits", "withdrawals", "since"}, "flows")
        return cls(
            deposits=Money.from_payload(mapping["deposits"], "deposits"),
            withdrawals=Money.from_payload(mapping["withdrawals"], "withdrawals"),
            since=decode_maybe(mapping["since"], decode_timestamp),
        )


@dataclass(frozen=True, slots=True)
class ExposureSummary:
    """Gross, net and directional net — three numbers, never one.

    `leverage` is a ratio and is therefore stored as its **pair**: the exposure and
    the equity it is measured against, with the division done at read time.
    """

    gross: Money
    net: Money
    directional_net: Money
    equity: Money | Absent
    largest_position: Money | Absent

    def __post_init__(self) -> None:
        for name in ("gross", "net", "directional_net"):
            if not isinstance(getattr(self, name), Money):
                raise TypeError(f"{name} must be a Money")
        for name in ("equity", "largest_position"):
            value = getattr(self, name)
            if not isinstance(value, (Money, Absent)):
                raise TypeError(f"{name} must be a Money or Absent")
        if self.gross.amount < 0:
            raise DomainValidationError("gross exposure is a magnitude and is not signed")

    @property
    def leverage(self) -> Decimal | Absent:
        """`gross ÷ equity` — computed here, stored nowhere."""
        if isinstance(self.equity, Absent):
            return self.equity
        if self.equity.amount == 0:
            return Absent("equity is zero, so leverage is undefined rather than large")
        return self.gross.amount / self.equity.amount

    def to_payload(self) -> dict[str, Any]:
        return {
            "gross": self.gross.to_payload(),
            "net": self.net.to_payload(),
            "directional_net": self.directional_net.to_payload(),
            "equity": encode_maybe(self.equity, Money.to_payload),
            "largest_position": encode_maybe(self.largest_position, Money.to_payload),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> ExposureSummary:
        mapping = require_mapping(raw, "exposure")
        require_exact_keys(
            mapping,
            {"gross", "net", "directional_net", "equity", "largest_position"},
            "exposure",
        )
        decode_money = lambda value: Money.from_payload(value, "exposure money")
        return cls(
            gross=Money.from_payload(mapping["gross"], "gross"),
            net=Money.from_payload(mapping["net"], "net"),
            directional_net=Money.from_payload(
                mapping["directional_net"], "directional_net"
            ),
            equity=decode_maybe(mapping["equity"], decode_money),
            largest_position=decode_maybe(mapping["largest_position"], decode_money),
        )


@dataclass(frozen=True, slots=True)
class AllocationEntry:
    """One slice of the portfolio, as a **pair** rather than a percentage.

    `dimension` is the classification axis (`asset`, `venue`, `book`, `currency`,
    `theme`); `classification_version` travels with it, because re-classifying an
    asset in 2029 must not rewrite 2026's allocation history. Two allocations
    computed under two versions are *visibly two different things*, never silently
    contradictory.
    """

    dimension: str
    key: str
    amount: Money
    total: Money
    classification_version: str

    def __post_init__(self) -> None:
        for name in ("dimension", "key", "classification_version"):
            object.__setattr__(self, name, require_text(getattr(self, name), name))
        for name in ("amount", "total"):
            if not isinstance(getattr(self, name), Money):
                raise TypeError(f"{name} must be a Money")
        if self.amount.asset != self.total.asset:
            raise DomainValidationError(
                "an allocation's part and whole are stated in one currency"
            )

    @property
    def weight(self) -> Decimal | Absent:
        """`amount ÷ total` — computed at read time, never stored."""
        if self.total.amount == 0:
            return Absent("the portfolio total is zero, so a weight is undefined")
        return self.amount.amount / self.total.amount

    def to_payload(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "key": self.key,
            "amount": self.amount.to_payload(),
            "total": self.total.to_payload(),
            "classification_version": self.classification_version,
        }

    @classmethod
    def from_payload(cls, raw: Any) -> AllocationEntry:
        mapping = require_mapping(raw, "allocation")
        require_exact_keys(
            mapping,
            {"dimension", "key", "amount", "total", "classification_version"},
            "allocation",
        )
        return cls(
            dimension=str(mapping["dimension"]),
            key=str(mapping["key"]),
            amount=Money.from_payload(mapping["amount"], "allocation amount"),
            total=Money.from_payload(mapping["total"], "allocation total"),
            classification_version=str(mapping["classification_version"]),
        )


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    """One valued observation of one portfolio at one instant, frozen."""

    portfolio_id: str
    base_currency: AssetCode
    as_of: datetime
    books_covered: tuple[Book, ...]
    holdings: tuple[Holding, ...]
    cash: tuple[CashBalance, ...]
    flows: FlowSummary
    exposure: ExposureSummary
    allocations: tuple[AllocationEntry, ...]
    open_position_event_ids: tuple[str, ...]
    version_set: VersionSet
    audit: RecordAudit
    consumed_sources: tuple[ConsumedSource, ...] = ()
    schema_version: int = PORTFOLIO_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "portfolio_id",
            require_pattern(self.portfolio_id, IDENTIFIER_PATTERN, "portfolio_id"),
        )
        if not isinstance(self.base_currency, AssetCode):
            object.__setattr__(self, "base_currency", AssetCode(self.base_currency))
        object.__setattr__(self, "as_of", require_utc(self.as_of, "as_of"))
        require_tuple_of(self.books_covered, Book, "books_covered", minimum_length=1)
        if len(set(self.books_covered)) != len(self.books_covered):
            raise DomainValidationError("books_covered must not repeat a book")
        require_tuple_of(self.holdings, Holding, "holdings")
        seen_holdings = {(h.asset.code, h.account.value) for h in self.holdings}
        if len(seen_holdings) != len(self.holdings):
            raise DomainValidationError(
                "one (asset, account) pair holds one quantity; two rows would be "
                "two answers to one question"
            )
        require_tuple_of(self.cash, CashBalance, "cash")
        if not isinstance(self.flows, FlowSummary):
            raise TypeError(
                "flows must be a FlowSummary; without flows a deposit looks like a "
                "gain and every return figure is wrong"
            )
        if not isinstance(self.exposure, ExposureSummary):
            raise TypeError("exposure must be an ExposureSummary")
        require_tuple_of(self.allocations, AllocationEntry, "allocations")
        require_tuple_of(self.open_position_event_ids, str, "open_position_event_ids")
        if not isinstance(self.version_set, VersionSet):
            raise TypeError("version_set must be a VersionSet")
        require_unmodified(self.audit, "PortfolioSnapshot")
        if self.audit.created_at != self.as_of:
            raise DomainValidationError(
                "audit.created_at must equal as_of; a snapshot is created at the "
                "instant it observes and at no other"
            )
        object.__setattr__(
            self, "consumed_sources", normalize_consumed_sources(self.consumed_sources)
        )
        if self.schema_version not in SUPPORTED_PORTFOLIO_SNAPSHOT_VERSIONS:
            raise DomainValidationError(
                f"portfolio snapshot schema_version {self.schema_version} is not "
                f"one this build writes "
                f"({sorted(SUPPORTED_PORTFOLIO_SNAPSHOT_VERSIONS)})"
            )
        for mark_holder in self.holdings:
            if isinstance(mark_holder.mark, MarkQuote) and mark_holder.mark.as_of > self.as_of:
                raise DomainValidationError(
                    f"the mark for {mark_holder.asset} is dated after the snapshot "
                    "it is frozen into"
                )

    # -- projections ---------------------------------------------------------

    @property
    def origin(self) -> ValueOrigin:
        """`MEASURED` over frozen inputs."""
        return ValueOrigin.MEASURED

    @property
    def unmarked_holdings(self) -> tuple[Holding, ...]:
        return tuple(
            holding for holding in self.holdings if isinstance(holding.mark, Absent)
        )

    def total_value(self) -> Money | Absent:
        """The portfolio's value, or the reason it cannot be stated.

        `Absent` — naming the unmarked holdings — rather than a total that quietly
        excludes them. A partial total is the most dangerous number a portfolio
        page can show, because it looks complete.
        """
        missing = self.unmarked_holdings
        if missing:
            return Absent(
                "no mark for "
                + ", ".join(sorted(f"{h.asset} @ {h.account}" for h in missing))
            )
        total = Money.zero(self.base_currency)
        for holding in self.holdings:
            value = holding.value
            if isinstance(value, Absent):  # pragma: no cover - guarded above
                return value
            if value.asset != self.base_currency:
                return Absent(
                    f"{holding.asset} is marked in {value.asset}, and no rate to "
                    f"{self.base_currency} was frozen with this snapshot"
                )
            total = total + value
        for balance in self.cash:
            value = balance.value_in_base(self.base_currency)
            if isinstance(value, Absent):
                return value
            total = total + value
        return total

    def allocations_for(self, dimension: str) -> tuple[AllocationEntry, ...]:
        wanted = require_text(dimension, "dimension")
        return tuple(entry for entry in self.allocations if entry.dimension == wanted)

    def stale_inputs(self, superseded: dict[str, str]) -> tuple[ConsumedSource, ...]:
        """Which consumed events have since been corrected. The artifact is untouched."""
        if not isinstance(superseded, dict):
            raise TypeError("superseded must be a dict")
        return tuple(
            source
            for source in self.consumed_sources
            if source.record_id in superseded
            and superseded[source.record_id] != source.content_digest
        )

    # -- identity and serialization -----------------------------------------

    @property
    def digest_basis(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "portfolio_id": self.portfolio_id,
            "base_currency": self.base_currency.code,
            "as_of": encode_timestamp(self.as_of),
            "books_covered": [book.value for book in self.books_covered],
            "holdings": [holding.to_payload() for holding in self.holdings],
            "cash": [balance.to_payload() for balance in self.cash],
            "flows": self.flows.to_payload(),
            "exposure": self.exposure.to_payload(),
            "allocations": [entry.to_payload() for entry in self.allocations],
            "open_position_event_ids": list(self.open_position_event_ids),
            "version_set": self.version_set.to_payload(),
            "consumed_sources": encode_consumed_sources(self.consumed_sources),
        }

    @property
    def snapshot_id(self) -> str:
        return build_domain_record_id(
            type_slug=PORTFOLIO_SNAPSHOT_TYPE_SLUG,
            subject=self.portfolio_id,
            moment=self.as_of,
            digest=content_digest_over(self.digest_basis),
        )

    @property
    def content_digest(self) -> str:
        return content_digest_over(self.digest_basis)

    def as_consumed_source(self) -> ConsumedSource:
        return ConsumedSource(
            record_id=self.snapshot_id,
            content_digest=self.content_digest,
            kind=PORTFOLIO_SNAPSHOT_KIND,
        )

    def to_payload(self) -> dict[str, Any]:
        payload = self.digest_basis
        payload["snapshot_id"] = self.snapshot_id
        payload["audit"] = self.audit.to_payload()
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> PortfolioSnapshot:
        mapping = require_mapping(raw, "portfolio snapshot")
        version = require_payload_version(
            mapping,
            supported=SUPPORTED_PORTFOLIO_SNAPSHOT_VERSIONS,
            entity="portfolio snapshot",
        )
        require_exact_keys(
            mapping,
            {
                "schema_version",
                "snapshot_id",
                "portfolio_id",
                "base_currency",
                "as_of",
                "books_covered",
                "holdings",
                "cash",
                "flows",
                "exposure",
                "allocations",
                "open_position_event_ids",
                "version_set",
                "consumed_sources",
                "audit",
            },
            "portfolio snapshot",
        )
        decoded = cls(
            portfolio_id=str(mapping["portfolio_id"]),
            base_currency=AssetCode(str(mapping["base_currency"])),
            as_of=decode_timestamp(mapping["as_of"]),
            books_covered=tuple(
                _member(Book, value, "book")
                for value in _array(mapping["books_covered"], "books_covered")
            ),
            holdings=tuple(
                Holding.from_payload(item)
                for item in _array(mapping["holdings"], "holdings")
            ),
            cash=tuple(
                CashBalance.from_payload(item)
                for item in _array(mapping["cash"], "cash")
            ),
            flows=FlowSummary.from_payload(mapping["flows"]),
            exposure=ExposureSummary.from_payload(mapping["exposure"]),
            allocations=tuple(
                AllocationEntry.from_payload(item)
                for item in _array(mapping["allocations"], "allocations")
            ),
            open_position_event_ids=tuple(
                str(item)
                for item in _array(
                    mapping["open_position_event_ids"], "open_position_event_ids"
                )
            ),
            version_set=VersionSet.from_payload(mapping["version_set"]),
            audit=RecordAudit.from_payload(mapping["audit"]),
            consumed_sources=decode_consumed_sources(mapping["consumed_sources"]),
            schema_version=version,
        )
        if mapping["snapshot_id"] != decoded.snapshot_id:
            raise PayloadDecodeError(
                f"snapshot_id {mapping['snapshot_id']!r} does not match the digest "
                f"of the snapshot it claims to identify ({decoded.snapshot_id!r})"
            )
        return decoded


def _array(raw: Any, entity: str) -> list[Any]:
    if not isinstance(raw, list):
        raise PayloadDecodeError(
            f"portfolio snapshot {entity} must be a JSON array, got "
            f"{type(raw).__name__}"
        )
    return raw


def _member(enum_type: Any, value: Any, entity: str) -> Any:
    try:
        return enum_type(value)
    except ValueError as error:
        raise PayloadDecodeError(
            f"{entity} {value!r} is not a known {enum_type.__name__}"
        ) from error
