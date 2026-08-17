"""`TradeOutcome` — what is frozen when a simulated trade finishes, and only that.

**A captured artifact holding exactly what cannot be recomputed.** `AP` §25.2
classes position quantity, average entry and realized P&L as *projections* —
*"pure fold, recomputable: yes"* — and the ledger they fold over is permanent, so
storing them here would be a fourth place the same fact lives and the first to
disagree with a `Correction`. The same table classes **MAE and MFE** the other
way, and states the reason in one line: *"kline history is not permanent and
instruments get delisted; a lazily-computed excursion metric can quietly become
uncomputable."*

So the record holds the excursions, the bar count, the exit reason, the stop that
was in force when it ended and the policies that produced it — and nothing that
the ledger already answers. `fmis.paper.views.read_outcome` folds the two together
at read time and produces every figure the milestone brief asks for.

**The excursions are stored as prices, not as money and not as R.** A price is the
raw fact a candle actually contains; money needs a quantity that changed with
every partial exit, and R needs an entry the ledger owns. Storing either would
freeze a *quotient* — the one thing `AP` §5.3 says is never a stored field — and
would make the figure wrong the moment a correction moved the entry it was
computed against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fmis.accounts import MarketId
from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.money import canonical_decimal_text, parse_decimal
from fmis.provenance import Absent, ValueOrigin, decode_maybe, encode_maybe
from fmis.records import (
    ConsumedSource,
    DomainValidationError,
    PayloadDecodeError,
    RecordAudit,
    build_domain_record_id,
    content_digest_over,
    require_exact_keys,
    require_int,
    require_mapping,
    require_member,
    require_payload_version,
    require_text,
    require_tuple_of,
    require_unmodified,
    require_utc,
    validate_domain_record_id,
)
from fmis.trade_lifecycle.models import PaperCostPolicy, TradeLifecycleError
from fmis.versioning import VersionSet

__all__ = [
    "TRADE_OUTCOME_SCHEMA_VERSION",
    "SUPPORTED_TRADE_OUTCOME_VERSIONS",
    "TRADE_OUTCOME_TYPE_SLUG",
    "TRADE_OUTCOME_KIND",
    "OutcomeError",
    "ExitReason",
    "EXPOSED_EXIT_REASONS",
    "TradeOutcome",
]

TRADE_OUTCOME_SCHEMA_VERSION = 1
SUPPORTED_TRADE_OUTCOME_VERSIONS = frozenset({1})
TRADE_OUTCOME_TYPE_SLUG = "trade_outcome"
TRADE_OUTCOME_KIND = "trade_outcome"


class OutcomeError(DomainValidationError, TradeLifecycleError):
    """An outcome whose fields cannot all be true at once."""


class ExitReason(Enum):
    """Why the trade ended. A closed set, and every member is a different fact.

    `EXPIRED`, `CANCELLED` and `SUPERSEDED` describe a trade that **never held
    exposure**, and keeping them here rather than treating "no outcome" as an
    absence is what makes *"how many of my activations never triggered"*
    answerable at all — the same reason `AP` §8.4 splits `EXPIRED_UNTRIGGERED`
    from `EXPIRED_UNDECIDED` instead of merging them.
    """

    TARGET_HIT = "target_hit"
    STOP_HIT = "stop_hit"
    MANUAL_CLOSE = "manual_close"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


#: The reasons that imply a position existed. Everything else ended before a fill,
#: and an excursion over a position that never opened is not zero — it is absent.
EXPOSED_EXIT_REASONS: frozenset[ExitReason] = frozenset(
    {ExitReason.TARGET_HIT, ExitReason.STOP_HIT, ExitReason.MANUAL_CLOSE}
)


def _exact_price(value: Any, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if value <= 0:
        raise OutcomeError(f"{name} must be positive, got {value}")
    return Decimal(canonical_decimal_text(value))


@dataclass(frozen=True, slots=True)
class TradeOutcome:
    """One finished simulated trade, frozen at the instant it finished."""

    activation_id: str
    plan_id: str
    market: MarketId
    exit_reason: ExitReason
    frozen_at: datetime
    interval: str
    cost_policy: PaperCostPolicy
    fill_policy_id: str
    fill_policy_version: int
    initial_stop: Decimal
    version_set: VersionSet
    audit: RecordAudit
    opened_at: datetime | Absent = field(
        default_factory=lambda: Absent("no fill ever opened this trade")
    )
    closed_at: datetime | Absent = field(
        default_factory=lambda: Absent("no fill ever opened this trade")
    )
    bars_held: int | Absent = field(
        default_factory=lambda: Absent("no fill ever opened this trade")
    )
    max_favourable_price: Decimal | Absent = field(
        default_factory=lambda: Absent("no fill ever opened this trade")
    )
    max_adverse_price: Decimal | Absent = field(
        default_factory=lambda: Absent("no fill ever opened this trade")
    )
    effective_stop_at_exit: Decimal | Absent = field(
        default_factory=lambda: Absent("no fill ever opened this trade")
    )
    fill_event_ids: tuple[str, ...] = ()
    note: str | Absent = field(default_factory=lambda: Absent("no note"))
    schema_version: int = TRADE_OUTCOME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_domain_record_id(self.activation_id)
        validate_domain_record_id(self.plan_id)
        if not isinstance(self.market, MarketId):
            raise TypeError("market must be a MarketId")
        require_member(self.exit_reason, ExitReason, "exit_reason")
        object.__setattr__(self, "frozen_at", require_utc(self.frozen_at, "frozen_at"))
        object.__setattr__(self, "interval", require_text(self.interval, "interval"))
        if not isinstance(self.cost_policy, PaperCostPolicy):
            raise TypeError("cost_policy must be a PaperCostPolicy")
        object.__setattr__(
            self, "fill_policy_id", require_text(self.fill_policy_id, "fill_policy_id")
        )
        require_int(self.fill_policy_version, "fill_policy_version", minimum=1)
        object.__setattr__(
            self, "initial_stop", _exact_price(self.initial_stop, "initial_stop")
        )
        if not isinstance(self.version_set, VersionSet):
            raise TypeError("version_set must be a VersionSet")
        require_unmodified(self.audit, "TradeOutcome")
        if self.audit.created_at != self.frozen_at:
            raise DomainValidationError(
                "audit.created_at must equal frozen_at; an outcome comes into being "
                "at the moment it is frozen and at no other"
            )
        for name in ("opened_at", "closed_at"):
            value = getattr(self, name)
            if not isinstance(value, Absent):
                object.__setattr__(self, name, require_utc(value, name))
        for name in (
            "max_favourable_price",
            "max_adverse_price",
            "effective_stop_at_exit",
        ):
            value = getattr(self, name)
            if not isinstance(value, Absent):
                object.__setattr__(self, name, _exact_price(value, name))
        if not isinstance(self.bars_held, Absent):
            require_int(self.bars_held, "bars_held", minimum=1)
        require_tuple_of(self.fill_event_ids, str, "fill_event_ids")
        object.__setattr__(
            self,
            "fill_event_ids",
            tuple(
                sorted(
                    {
                        validate_domain_record_id(event_id)
                        for event_id in self.fill_event_ids
                    }
                )
            ),
        )
        if not isinstance(self.note, Absent):
            object.__setattr__(self, "note", require_text(self.note, "note"))
        if self.schema_version not in SUPPORTED_TRADE_OUTCOME_VERSIONS:
            raise DomainValidationError(
                f"trade outcome schema_version {self.schema_version} is not one "
                f"this build writes ({sorted(SUPPORTED_TRADE_OUTCOME_VERSIONS)})"
            )
        self._validate_exposure_consistency()

    def _validate_exposure_consistency(self) -> None:
        """A trade that held exposure states every fact about it, or none.

        Half a record is worse than none: an outcome carrying a close time and no
        excursions reads as *"this trade never went against us"*, which is a claim
        about the market rather than about what was recorded.
        """
        exposed_fields = (
            "opened_at",
            "closed_at",
            "bars_held",
            "max_favourable_price",
            "max_adverse_price",
            "effective_stop_at_exit",
        )
        stated = [
            name for name in exposed_fields if not isinstance(getattr(self, name), Absent)
        ]
        if self.exit_reason in EXPOSED_EXIT_REASONS:
            missing = [name for name in exposed_fields if name not in stated]
            if missing:
                raise OutcomeError(
                    f"an outcome that ended by {self.exit_reason.value} held a "
                    f"position, and must state {sorted(missing)}. A partial record "
                    "reads as a claim about the market rather than about what was "
                    "recorded"
                )
            if not self.fill_event_ids:
                raise OutcomeError(
                    f"an outcome that ended by {self.exit_reason.value} folds at "
                    "least one fill and must name them; a captured artifact that "
                    "cannot point at its own sources cannot be checked against them"
                )
            assert not isinstance(self.opened_at, Absent)  # proved above
            assert not isinstance(self.closed_at, Absent)  # proved above
            if self.closed_at < self.opened_at:
                raise OutcomeError("closed_at precedes opened_at")
            if self.frozen_at < self.closed_at:
                raise OutcomeError(
                    f"this outcome is frozen at {self.frozen_at.isoformat()}, "
                    f"before the {self.closed_at.isoformat()} it says the trade "
                    "closed at. FMITS cannot record an ending before it happens"
                )
        elif stated:
            raise OutcomeError(
                f"an outcome that ended by {self.exit_reason.value} never held a "
                f"position, and must state none of {sorted(stated)}. An excursion "
                "over a position that never opened is absent, not zero"
            )
        elif self.fill_event_ids:
            raise OutcomeError(
                f"an outcome that ended by {self.exit_reason.value} names "
                f"{len(self.fill_event_ids)} fill(s); a trade that never opened "
                "folded none"
            )

    # -- projections ---------------------------------------------------------

    @property
    def origin(self) -> ValueOrigin:
        """`MEASURED` over frozen inputs — `AP` §6.1's class for a snapshot."""
        return ValueOrigin.MEASURED

    @property
    def held_exposure(self) -> bool:
        return self.exit_reason in EXPOSED_EXIT_REASONS

    @property
    def stop_was_moved(self) -> bool:
        """Whether the stop in force at the exit differed from the one committed to."""
        if isinstance(self.effective_stop_at_exit, Absent):
            return False
        return self.effective_stop_at_exit != self.initial_stop

    def holding_time(self) -> Any:
        """How long exposure existed, or the absence that says it never did."""
        if isinstance(self.opened_at, Absent) or isinstance(self.closed_at, Absent):
            return Absent("this trade never held a position")
        return self.closed_at - self.opened_at

    # -- identity and serialization -----------------------------------------

    @property
    def digest_basis(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "activation_id": self.activation_id,
            "plan_id": self.plan_id,
            "market": self.market.to_payload(),
            "exit_reason": self.exit_reason.value,
            "frozen_at": encode_timestamp(self.frozen_at),
            "interval": self.interval,
            "cost_policy": self.cost_policy.to_payload(),
            "fill_policy_id": self.fill_policy_id,
            "fill_policy_version": self.fill_policy_version,
            "initial_stop": canonical_decimal_text(self.initial_stop),
            "opened_at": encode_maybe(self.opened_at, encode_timestamp),
            "closed_at": encode_maybe(self.closed_at, encode_timestamp),
            "bars_held": encode_maybe(self.bars_held, int),
            "max_favourable_price": encode_maybe(
                self.max_favourable_price, canonical_decimal_text
            ),
            "max_adverse_price": encode_maybe(
                self.max_adverse_price, canonical_decimal_text
            ),
            "effective_stop_at_exit": encode_maybe(
                self.effective_stop_at_exit, canonical_decimal_text
            ),
            "fill_event_ids": list(self.fill_event_ids),
            "note": encode_maybe(self.note, str),
            "version_set": self.version_set.to_payload(),
        }

    @property
    def outcome_id(self) -> str:
        return build_domain_record_id(
            type_slug=TRADE_OUTCOME_TYPE_SLUG,
            subject=self.market.value,
            moment=self.frozen_at,
            digest=content_digest_over(self.digest_basis),
        )

    @property
    def content_digest(self) -> str:
        return content_digest_over(self.digest_basis)

    def as_consumed_source(self) -> ConsumedSource:
        return ConsumedSource(
            record_id=self.outcome_id,
            content_digest=self.content_digest,
            kind=TRADE_OUTCOME_KIND,
        )

    def to_payload(self) -> dict[str, Any]:
        payload = self.digest_basis
        payload["outcome_id"] = self.outcome_id
        payload["audit"] = self.audit.to_payload()
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> TradeOutcome:
        mapping = require_mapping(raw, "trade outcome")
        version = require_payload_version(
            mapping,
            supported=SUPPORTED_TRADE_OUTCOME_VERSIONS,
            entity="trade outcome",
        )
        require_exact_keys(mapping, _OUTCOME_KEYS, "trade outcome")
        try:
            reason = ExitReason(mapping["exit_reason"])
        except ValueError as error:
            raise PayloadDecodeError(
                f"exit reason {mapping['exit_reason']!r} is not known to this "
                "build; an unknown member is a clean rejection, never a default"
            ) from error
        decoded = cls(
            activation_id=str(mapping["activation_id"]),
            plan_id=str(mapping["plan_id"]),
            market=MarketId.from_payload(mapping["market"], "outcome market"),
            exit_reason=reason,
            frozen_at=decode_timestamp(mapping["frozen_at"]),
            interval=str(mapping["interval"]),
            cost_policy=PaperCostPolicy.from_payload(mapping["cost_policy"]),
            fill_policy_id=str(mapping["fill_policy_id"]),
            fill_policy_version=require_int(
                mapping["fill_policy_version"], "fill_policy_version", minimum=1
            ),
            initial_stop=parse_decimal(mapping["initial_stop"], "initial_stop"),
            version_set=VersionSet.from_payload(mapping["version_set"]),
            audit=RecordAudit.from_payload(mapping["audit"]),
            opened_at=decode_maybe(mapping["opened_at"], decode_timestamp),
            closed_at=decode_maybe(mapping["closed_at"], decode_timestamp),
            bars_held=decode_maybe(mapping["bars_held"], _as_int),
            max_favourable_price=decode_maybe(
                mapping["max_favourable_price"],
                lambda value: parse_decimal(value, "max_favourable_price"),
            ),
            max_adverse_price=decode_maybe(
                mapping["max_adverse_price"],
                lambda value: parse_decimal(value, "max_adverse_price"),
            ),
            effective_stop_at_exit=decode_maybe(
                mapping["effective_stop_at_exit"],
                lambda value: parse_decimal(value, "effective_stop_at_exit"),
            ),
            fill_event_ids=tuple(
                str(item)
                for item in _array(mapping["fill_event_ids"], "fill_event_ids")
            ),
            note=decode_maybe(mapping["note"], str),
            schema_version=version,
        )
        if mapping["outcome_id"] != decoded.outcome_id:
            raise PayloadDecodeError(
                f"outcome_id {mapping['outcome_id']!r} does not match the digest of "
                f"the outcome it claims to identify ({decoded.outcome_id!r})"
            )
        return decoded


_OUTCOME_KEYS = frozenset({
    "schema_version",
    "outcome_id",
    "activation_id",
    "plan_id",
    "market",
    "exit_reason",
    "frozen_at",
    "interval",
    "cost_policy",
    "fill_policy_id",
    "fill_policy_version",
    "initial_stop",
    "opened_at",
    "closed_at",
    "bars_held",
    "max_favourable_price",
    "max_adverse_price",
    "effective_stop_at_exit",
    "fill_event_ids",
    "note",
    "version_set",
    "audit",
})


def _array(raw: Any, entity: str) -> list[Any]:
    if not isinstance(raw, list):
        raise PayloadDecodeError(
            f"trade outcome {entity} must be a JSON array, got {type(raw).__name__}"
        )
    return raw


def _as_int(raw: Any) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise PayloadDecodeError(f"expected an int, got {type(raw).__name__}")
    return raw
