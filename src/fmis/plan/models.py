"""`TradePlan` — what the owner committed to, before the market moved.

The data model's entity 19 (§10.3) and the architecture's §9, built here for the
first time. Milestone BH built thirteen domain packages and left this one out;
`SWING_TRADING_MVP_BLUEPRINT_V1` §12.3 named the omission as accepted debt with
the cost stated plainly — *"until it lands, a widened stop is invisible, and stop
integrity is the highest-value single behavioural metric"*. This is that debt's
first half.

**Why a stop cannot live on a `Trade`.** §11.6 is explicit and this package is
its consequence: *"stop, target, intended size → `TradePlan`"*. A `Trade` records
what happened to money; a stop is what the owner said would end the trade, and a
stop that never triggered is not part of what happened. Putting the two on one
record would make *"did I honour my stop?"* unanswerable, because the field would
hold whatever the stop was when the position closed rather than what it was when
the position opened.

**`initial_invalidation` is the single most important field in this domain**
(§9.2). R-multiple, stop integrity and discipline all key on it, and it must
remain the *initial* value forever. There is no code path that changes it — not a
rule, a construction. `PlanAmendment` (§10.4), which would let the *other* fields
move by appended event, is **not built**: nothing in this milestone amends a
plan, and a record type nobody writes is weight without value. The consequence is
stated rather than hidden — in this build every field is immutable, which is
stricter than §10.3 and not looser.

**A planned price is not a `LevelReading`, and the difference is provenance.**
`fmis.snapshotting.LevelReading` is a *frozen engine reading*: `MEASURED`, with a
`LevelOriginRef` naming the swing and the confirmation bars that produced it, and
its rule is that *"no price in this domain is fabricated"*. A stop the owner
types has no such origin, and manufacturing one to reuse the type would be
exactly the fabrication that rule forbids. So a plan holds exact `Decimal` prices
and the whole record is `ASSERTED` — §10.3's own provenance line, unchanged:
*"a plan is intent, and intent can be wrong."*

**There is no `capital_at_risk` field, and its absence is the money rule applied.**
Capital at risk is `|entry − stop| × quantity` — a product over one number this
record holds and two the `Trade` holds. `AP` §5.3: *"no quotient is ever a stored
field"*, and the domain's two precedents are unanimous — `RiskRewardReading`
stores the pair and computes the ratio, `AverageCost` stores the pair and divides
at read time. Storing the product here would be a fourth place the same fact
lives, and the first one to disagree with a `Correction`. `adherence.py` computes
it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from fmis.accounts import Book, MarketId
from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.money import canonical_decimal_text, parse_decimal
from fmis.proposal import StatedConfidence
from fmis.provenance import Absent, ValueOrigin, VersionedTerm, decode_maybe, encode_maybe
from fmis.records import (
    ConsumedSource,
    DomainValidationError,
    PayloadDecodeError,
    RecordAudit,
    TradeDomainError,
    build_domain_record_id,
    content_digest_over,
    require_exact_keys,
    require_mapping,
    require_member,
    require_payload_version,
    require_text,
    require_tuple_of,
    require_unmodified,
    require_utc,
    validate_domain_record_id,
)
from fmis.snapshotting import TradeDirection
from fmis.versioning import VersionSet

__all__ = [
    "PlanError",
    "TRADE_PLAN_SCHEMA_VERSION",
    "SUPPORTED_TRADE_PLAN_VERSIONS",
    "TRADE_PLAN_TYPE_SLUG",
    "TRADE_PLAN_KIND",
    "TradePlan",
]

TRADE_PLAN_SCHEMA_VERSION = 1
SUPPORTED_TRADE_PLAN_VERSIONS = frozenset({1})
TRADE_PLAN_TYPE_SLUG = "trade_plan"
TRADE_PLAN_KIND = "trade_plan"


class PlanError(TradeDomainError):
    """Base class for every trade-plan failure."""


@dataclass(frozen=True, slots=True)
class TradePlan:
    """One commitment: a market, a side, a stop, and the targets it was taken for."""

    created_at: datetime
    committed_at: datetime
    market: MarketId
    book: Book
    direction: TradeDirection
    initial_invalidation: Decimal
    targets: tuple[Decimal, ...]
    stated_confidence: StatedConfidence
    version_set: VersionSet
    audit: RecordAudit
    setup_type: VersionedTerm | Absent = field(
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
    note: str | Absent = field(default_factory=lambda: Absent("no note"))
    schema_version: int = TRADE_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))
        object.__setattr__(
            self, "committed_at", require_utc(self.committed_at, "committed_at")
        )
        if self.committed_at < self.created_at:
            raise DomainValidationError(
                f"committed_at {self.committed_at.isoformat()} precedes created_at "
                f"{self.created_at.isoformat()}; a plan cannot be committed to "
                "before it exists"
            )
        if not isinstance(self.market, MarketId):
            raise TypeError("market must be a MarketId")
        require_member(self.book, Book, "book")
        require_member(self.direction, TradeDirection, "direction")
        if not self.direction.is_directional:
            raise DomainValidationError(
                "a plan commits to a side; NO_TRADE is a decision not to act and "
                "belongs to a proposal's lifecycle, where it can be scored. A plan "
                "with no side has no stop to be wrong about"
            )
        object.__setattr__(
            self,
            "initial_invalidation",
            _exact_price(self.initial_invalidation, "initial_invalidation"),
        )
        require_tuple_of(self.targets, Decimal, "targets")
        object.__setattr__(
            self,
            "targets",
            tuple(
                _exact_price(target, f"targets[{position}]")
                for position, target in enumerate(self.targets)
            ),
        )
        self._validate_target_ladder()
        if not isinstance(self.stated_confidence, StatedConfidence):
            raise TypeError("stated_confidence must be a StatedConfidence")
        if not isinstance(self.version_set, VersionSet):
            raise TypeError("version_set must be a VersionSet")
        require_unmodified(self.audit, "TradePlan")
        if self.audit.created_at != self.created_at:
            raise DomainValidationError(
                "audit.created_at must equal created_at; a plan is created at the "
                "moment it is authored and at no other"
            )
        if not isinstance(self.setup_type, (VersionedTerm, Absent)):
            raise TypeError(
                "setup_type must be a VersionedTerm from the owner's setup "
                "vocabulary, or Absent; an untagged setup cannot be cohorted"
            )
        for name in ("proposal_id", "market_snapshot_id"):
            value = getattr(self, name)
            if not isinstance(value, Absent):
                validate_domain_record_id(value)
        require_tuple_of(self.analysis_record_ids, str, "analysis_record_ids")
        object.__setattr__(
            self,
            "analysis_record_ids",
            tuple(
                sorted(
                    {
                        require_text(record_id, "analysis record id")
                        for record_id in self.analysis_record_ids
                    }
                )
            ),
        )
        if not isinstance(self.expires_at, Absent):
            object.__setattr__(
                self, "expires_at", require_utc(self.expires_at, "expires_at")
            )
            if self.expires_at <= self.committed_at:
                raise DomainValidationError(
                    f"expires_at {self.expires_at.isoformat()} is not after "
                    f"committed_at {self.committed_at.isoformat()}; a commitment "
                    "that expires before it is made cannot be acted on"
                )
        if not isinstance(self.note, Absent):
            object.__setattr__(self, "note", require_text(self.note, "note"))
        if self.schema_version not in SUPPORTED_TRADE_PLAN_VERSIONS:
            raise DomainValidationError(
                f"trade plan schema_version {self.schema_version} is not one this "
                f"build writes ({sorted(SUPPORTED_TRADE_PLAN_VERSIONS)})"
            )

    def _validate_target_ladder(self) -> None:
        """Targets sit beyond the stop, in one direction, and never repeat.

        Checkable without an entry price, and worth checking here rather than at
        the composition root: a target on the stop's side of the trade is a
        transposition — the commonest typing error there is — and a ladder that
        steps backwards is a second one. Neither has a reading under which the
        plan means something, so both are refused rather than recorded.

        What this cannot check is the entry price, which lives on the `Trade`.
        `adherence.check_placement` is where the three are compared.
        """
        beyond = (
            (lambda target: target > self.initial_invalidation)
            if self.direction is TradeDirection.LONG
            else (lambda target: target < self.initial_invalidation)
        )
        stop_text = canonical_decimal_text(self.initial_invalidation)
        side = "above" if self.direction is TradeDirection.LONG else "below"
        for position, target in enumerate(self.targets):
            if not beyond(target):
                raise DomainValidationError(
                    f"targets[{position}] {canonical_decimal_text(target)} is not "
                    f"{side} the stop {stop_text} on a "
                    f"{self.direction.value} plan; a target the stop would reach "
                    "first is not a target"
                )
        ordered = (
            list(self.targets)
            if self.direction is TradeDirection.LONG
            else list(reversed(self.targets))
        )
        for position, (previous, current) in enumerate(zip(ordered, ordered[1:])):
            if current <= previous:
                raise DomainValidationError(
                    f"targets are stated nearest first and must step away from the "
                    f"stop; {canonical_decimal_text(self.targets[position + 1])} "
                    f"does not lie beyond "
                    f"{canonical_decimal_text(self.targets[position])}"
                )

    # -- projections ---------------------------------------------------------

    @property
    def origin(self) -> ValueOrigin:
        """`ASSERTED`. A plan is intent, and intent can be wrong."""
        return ValueOrigin.ASSERTED

    @property
    def stop(self) -> Decimal:
        """A reading name for `initial_invalidation`, and nothing more.

        A *property*, so there is exactly one stored field. A second stop field
        that could be set independently is the failure this whole entity exists
        to prevent.
        """
        return self.initial_invalidation

    @property
    def first_target(self) -> Decimal | Absent:
        """The nearest target, or the absence that says the plan named none."""
        if not self.targets:
            return Absent("this plan states no target")
        return self.targets[0]

    def is_expired_at(self, moment: datetime) -> bool:
        """Whether the commitment has lapsed — a comparison, never a stored flag."""
        when = require_utc(moment, "moment")
        if isinstance(self.expires_at, Absent):
            return False
        return when >= self.expires_at

    # -- identity and serialization -----------------------------------------

    @property
    def digest_basis(self) -> dict[str, Any]:
        """The commitment itself, and nothing else.

        `created_at` is excluded, following ADR-0027 §3's precedent for
        `archived_at` and the ledger's for `recorded_at`: *when the owner began
        typing* must not decide whether re-entering the same commitment after a
        crash is one plan or two. `committed_at` stays in, because two
        commitments to the same levels on two days are two decisions.
        """
        return {
            "schema_version": self.schema_version,
            "committed_at": encode_timestamp(self.committed_at),
            "market": self.market.to_payload(),
            "book": self.book.value,
            "direction": self.direction.value,
            "initial_invalidation": canonical_decimal_text(self.initial_invalidation),
            "targets": [canonical_decimal_text(target) for target in self.targets],
            "stated_confidence": self.stated_confidence.label,
            "setup_type": encode_maybe(self.setup_type, VersionedTerm.to_payload),
            "proposal_id": encode_maybe(self.proposal_id, str),
            "market_snapshot_id": encode_maybe(self.market_snapshot_id, str),
            "analysis_record_ids": list(self.analysis_record_ids),
            "expires_at": encode_maybe(self.expires_at, encode_timestamp),
            "note": encode_maybe(self.note, str),
            "version_set": self.version_set.to_payload(),
        }

    @property
    def plan_id(self) -> str:
        return build_domain_record_id(
            type_slug=TRADE_PLAN_TYPE_SLUG,
            subject=self.market.value,
            moment=self.committed_at,
            digest=content_digest_over(self.digest_basis),
        )

    @property
    def content_digest(self) -> str:
        return content_digest_over(self.digest_basis)

    def as_consumed_source(self) -> ConsumedSource:
        return ConsumedSource(
            record_id=self.plan_id,
            content_digest=self.content_digest,
            kind=TRADE_PLAN_KIND,
        )

    def to_payload(self) -> dict[str, Any]:
        payload = self.digest_basis
        payload["plan_id"] = self.plan_id
        payload["created_at"] = encode_timestamp(self.created_at)
        payload["audit"] = self.audit.to_payload()
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> TradePlan:
        mapping = require_mapping(raw, "trade plan")
        version = require_payload_version(
            mapping, supported=SUPPORTED_TRADE_PLAN_VERSIONS, entity="trade plan"
        )
        require_exact_keys(mapping, _PLAN_KEYS, "trade plan")
        decoded = cls(
            created_at=decode_timestamp(mapping["created_at"]),
            committed_at=decode_timestamp(mapping["committed_at"]),
            market=MarketId.from_payload(mapping["market"], "plan market"),
            book=_member(Book, mapping["book"], "book"),
            direction=_member(TradeDirection, mapping["direction"], "direction"),
            initial_invalidation=parse_decimal(
                mapping["initial_invalidation"], "initial_invalidation"
            ),
            targets=tuple(
                parse_decimal(item, "target")
                for item in _array(mapping["targets"], "targets")
            ),
            stated_confidence=StatedConfidence(str(mapping["stated_confidence"])),
            version_set=VersionSet.from_payload(mapping["version_set"]),
            audit=RecordAudit.from_payload(mapping["audit"]),
            setup_type=decode_maybe(mapping["setup_type"], VersionedTerm.from_payload),
            proposal_id=decode_maybe(mapping["proposal_id"], str),
            market_snapshot_id=decode_maybe(mapping["market_snapshot_id"], str),
            analysis_record_ids=tuple(
                str(item)
                for item in _array(mapping["analysis_record_ids"], "analysis records")
            ),
            expires_at=decode_maybe(mapping["expires_at"], decode_timestamp),
            note=decode_maybe(mapping["note"], str),
            schema_version=version,
        )
        if mapping["plan_id"] != decoded.plan_id:
            raise PayloadDecodeError(
                f"plan_id {mapping['plan_id']!r} does not match the digest of the "
                f"commitment it claims to identify ({decoded.plan_id!r})"
            )
        return decoded


_PLAN_KEYS = frozenset({
    "schema_version",
    "plan_id",
    "created_at",
    "committed_at",
    "market",
    "book",
    "direction",
    "initial_invalidation",
    "targets",
    "stated_confidence",
    "setup_type",
    "proposal_id",
    "market_snapshot_id",
    "analysis_record_ids",
    "expires_at",
    "note",
    "version_set",
    "audit",
})


def _exact_price(value: Any, name: str) -> Decimal:
    """One canonical spelling of one asserted price, or a refusal.

    Canonicalizing here rather than at the composition root is what makes
    re-entering the same commitment idempotent: `Decimal("58400.0")` and
    `Decimal("58400")` produce different bytes and therefore different plan ids.
    """
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if value <= 0:
        raise DomainValidationError(f"{name} must be positive, got {value}")
    return Decimal(canonical_decimal_text(value))


def _array(raw: Any, entity: str) -> list[Any]:
    if not isinstance(raw, list):
        raise PayloadDecodeError(
            f"trade plan {entity} must be a JSON array, got {type(raw).__name__}"
        )
    return raw


def _member(enum_type: Any, value: Any, entity: str) -> Any:
    try:
        return enum_type(value)
    except ValueError as error:
        raise PayloadDecodeError(
            f"{entity} {value!r} is not a known {enum_type.__name__}; an unknown "
            "member is a clean rejection, never a default"
        ) from error
