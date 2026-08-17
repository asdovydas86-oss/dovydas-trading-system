"""`TradeActivation` — the instruction that starts a simulated trade's life.

**Not an `Order`.** `AP` §10 reserves that name for what was actually placed at a
venue, and §10.3 defers it with a stated trigger — exchange read-only sync. This
milestone places nothing anywhere. An activation is an *instruction to the
simulator*: which commitment, at what size, on what entry, out through which
ladder, with which stop management, until when. Calling it an order would make a
future real order the second thing with that name, and the failure §10.1 exists
to expose — *"the plan says the stop is at 58,400, and no stop order was ever
placed"* — would become unstatable.

**The activation does not carry the stop, and its absence is the point.** The stop
is `TradePlan.initial_invalidation` and lives in exactly one place; the *effective*
stop at any instant is the fold of `StopAmendment`s over it (`stops.py`). Two
fields that could disagree about the same fact would be one field too many, and
the one that decides R-multiple, stop integrity and every discipline metric is the
worst candidate in the domain for a second copy.

**`Book.PAPER` is required in this build.** `AP` §5.5 already says what the book
means — *"paper events live in the same ledger under `PAPER`, are excluded from
every real-money aggregate by default, and use identical sizing, fee and risk
logic"* — and this milestone simulates. Refusing any other book here is what stops
a simulator from writing fills into a real-money pool by a typo. Widening it later,
for shadow-mode over a live book, is additive; narrowing it afterwards would not be.

**Nothing here reads a candle, a clock, a path or a store.** Every instant is an
argument and every price is already exact. `fmis.paper.bars` is the only module in
this milestone that converts a `float` OHLC bar into exact values, and it sits one
layer above this package precisely so `fmis.persistence` can import this one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fmis.accounts import AccountId, Book, MarketId
from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.money import Quantity, canonical_decimal_text, parse_decimal
from fmis.provenance import Absent, ValueOrigin, decode_maybe, encode_maybe
from fmis.records import (
    ConsumedSource,
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
    require_tuple_of,
    require_unmodified,
    require_utc,
    validate_domain_record_id,
)
from fmis.snapshotting import TradeDirection
from fmis.versioning import VersionSet

__all__ = [
    "TradeLifecycleError",
    "ActivationError",
    "TRADE_ACTIVATION_SCHEMA_VERSION",
    "SUPPORTED_TRADE_ACTIVATION_VERSIONS",
    "TRADE_ACTIVATION_TYPE_SLUG",
    "TRADE_ACTIVATION_KIND",
    "EntryType",
    "ExitLeg",
    "ExitLadder",
    "BreakEvenRule",
    "TrailingRule",
    "StopManagement",
    "PaperCostPolicy",
    "TradeActivation",
]

TRADE_ACTIVATION_SCHEMA_VERSION = 1
SUPPORTED_TRADE_ACTIVATION_VERSIONS = frozenset({1})
TRADE_ACTIVATION_TYPE_SLUG = "trade_activation"
TRADE_ACTIVATION_KIND = "trade_activation"


class TradeLifecycleError(TradeDomainError):
    """Base class for every failure raised by this package."""


class ActivationError(DomainValidationError, TradeLifecycleError):
    """An activation whose fields cannot all be true at once.

    Both a `DomainValidationError` and a `TradeLifecycleError`, so a caller
    catching either is not told a half-truth — the convention `RiskGeometryError`
    and `IllegalTransitionError` already follow.
    """


def _exact_price(value: Any, name: str) -> Decimal:
    """One canonical spelling of one exact price, or a refusal.

    Canonicalizing at construction is what makes re-activating the identical
    instruction idempotent: `Decimal("58400.0")` and `Decimal("58400")` produce
    different bytes and therefore different record ids.
    """
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if value <= 0:
        raise ActivationError(f"{name} must be positive, got {value}")
    return Decimal(canonical_decimal_text(value))


def _exact_fraction(value: Any, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if value <= 0 or value > 1:
        raise ActivationError(
            f"{name} must lie in (0, 1], got {canonical_decimal_text(value)}; a "
            "fraction of a position is a share of it, and a share above the whole "
            "would exit more than was ever opened"
        )
    return Decimal(canonical_decimal_text(value))


def _exact_multiple(value: Any, name: str, *, allow_zero: bool = False) -> Decimal:
    """A multiple of the initial risk distance — an R, not a price.

    Stated in R rather than in price units on purpose: a price offset needs the
    market's tick size, which is venue reference data this domain declines to
    hold, and an offset typed in the wrong instrument's units is invisible.
    """
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if value < 0 or (value == 0 and not allow_zero):
        raise ActivationError(
            f"{name} must be {'non-negative' if allow_zero else 'positive'}, got "
            f"{canonical_decimal_text(value)}"
        )
    return Decimal(canonical_decimal_text(value))


class EntryType(Enum):
    """How the simulator decides an entry has happened. A closed set of three.

    `STOP_ENTRY` rather than `STOP`, because in this domain *stop* already means
    the invalidation the trade dies on, and one word for two levels on opposite
    sides of the entry is how a breakout entry becomes a stop-loss in somebody's
    reading of the code.
    """

    MARKET = "market"
    LIMIT = "limit"
    STOP_ENTRY = "stop_entry"

    @property
    def needs_a_level(self) -> bool:
        """Whether the owner must state a price for this entry to mean anything."""
        return self is not EntryType.MARKET


@dataclass(frozen=True, slots=True)
class ExitLeg:
    """One rung of the exit ladder: a target, and the share taken there."""

    target: Decimal
    fraction: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", _exact_price(self.target, "target"))
        object.__setattr__(
            self, "fraction", _exact_fraction(self.fraction, "fraction")
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "target": canonical_decimal_text(self.target),
            "fraction": canonical_decimal_text(self.fraction),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> ExitLeg:
        mapping = require_mapping(raw, "exit leg")
        require_exact_keys(mapping, {"target", "fraction"}, "exit leg")
        return cls(
            target=parse_decimal(mapping["target"], "target"),
            fraction=parse_decimal(mapping["fraction"], "fraction"),
        )


@dataclass(frozen=True, slots=True)
class ExitLadder:
    """The ordered legs a position is taken off through.

    **The fractions may sum to less than one, and the remainder runs to the stop.**
    That is not a gap in the model: *"take half at the first target and let the
    rest run"* is the commonest swing exit there is, and a ladder forced to sum to
    exactly one could not express it. A sum **above** one is refused, because it
    would exit more than was ever opened.

    An empty ladder is legal and means *"this trade exits at the stop, or by hand"*.
    """

    legs: tuple[ExitLeg, ...] = ()

    def __post_init__(self) -> None:
        require_tuple_of(self.legs, ExitLeg, "legs")
        targets = [leg.target for leg in self.legs]
        if len(set(targets)) != len(targets):
            raise ActivationError(
                "two legs of one ladder name the same target price; one price is "
                "one rung, and two rungs at one price is a size the fold cannot "
                "attribute"
            )
        if self.total_fraction > 1:
            raise ActivationError(
                f"the ladder takes {canonical_decimal_text(self.total_fraction)} of "
                "the position, which is more than there is. Fractions are shares of "
                "the activated size, not of what happens to remain"
            )

    @property
    def total_fraction(self) -> Decimal:
        total = Decimal(0)
        for leg in self.legs:
            total = total + leg.fraction
        return total

    @property
    def runner_fraction(self) -> Decimal:
        """What is left to run to the stop after every leg has filled."""
        return Decimal(1) - self.total_fraction

    @property
    def is_empty(self) -> bool:
        return not self.legs

    def to_payload(self) -> list[Any]:
        return [leg.to_payload() for leg in self.legs]

    @classmethod
    def from_payload(cls, raw: Any) -> ExitLadder:
        if not isinstance(raw, list):
            raise PayloadDecodeError(
                f"exit ladder must be a JSON array, got {type(raw).__name__}"
            )
        return cls(legs=tuple(ExitLeg.from_payload(item) for item in raw))


@dataclass(frozen=True, slots=True)
class BreakEvenRule:
    """Move the stop to the entry once the trade is `trigger_r` in front.

    `offset_r` moves it a further fraction of the initial risk beyond the entry,
    so *"break even plus a tenth of the risk to cover costs"* is expressible
    without this package inventing a cost model.
    """

    trigger_r: Decimal
    offset_r: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "trigger_r", _exact_multiple(self.trigger_r, "trigger_r")
        )
        object.__setattr__(
            self,
            "offset_r",
            _exact_multiple(self.offset_r, "offset_r", allow_zero=True),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "trigger_r": canonical_decimal_text(self.trigger_r),
            "offset_r": canonical_decimal_text(self.offset_r),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> BreakEvenRule:
        mapping = require_mapping(raw, "break-even rule")
        require_exact_keys(mapping, {"trigger_r", "offset_r"}, "break-even rule")
        return cls(
            trigger_r=parse_decimal(mapping["trigger_r"], "trigger_r"),
            offset_r=parse_decimal(mapping["offset_r"], "offset_r"),
        )


@dataclass(frozen=True, slots=True)
class TrailingRule:
    """Trail the stop `distance_r` behind the best price the trade has seen.

    The best price is the **maximum favourable excursion's** price, measured on
    the simulation interval's closed bars — so a trail is a function of the same
    excursion the outcome record freezes, and not of a second, separately
    accumulated extreme that could disagree with it.

    `activate_at_r` holds the trail off until the trade is that far in front. It
    is `Absent` rather than zero when the owner did not state one: a trail that
    starts immediately is a *choice*, and a zero default would make it look like
    the absence of one.
    """

    distance_r: Decimal
    activate_at_r: Decimal | Absent = field(
        default_factory=lambda: Absent("the trail runs from the first bar")
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "distance_r", _exact_multiple(self.distance_r, "distance_r")
        )
        if not isinstance(self.activate_at_r, Absent):
            object.__setattr__(
                self,
                "activate_at_r",
                _exact_multiple(self.activate_at_r, "activate_at_r"),
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "distance_r": canonical_decimal_text(self.distance_r),
            "activate_at_r": encode_maybe(self.activate_at_r, canonical_decimal_text),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> TrailingRule:
        mapping = require_mapping(raw, "trailing rule")
        require_exact_keys(mapping, {"distance_r", "activate_at_r"}, "trailing rule")
        return cls(
            distance_r=parse_decimal(mapping["distance_r"], "distance_r"),
            activate_at_r=decode_maybe(
                mapping["activate_at_r"],
                lambda value: parse_decimal(value, "activate_at_r"),
            ),
        )


@dataclass(frozen=True, slots=True)
class StopManagement:
    """Which automatic stop rules this activation asked for. Both are optional.

    **A rule this package applies can only ever tighten the stop.** Widening one
    is the owner's own act and reaches the store as an `ASSERTED` amendment with
    a reason from their own vocabulary — never as a `POLICY_DERIVED` one nobody
    chose. `AP` §9.3 states why in one sentence: *"widening a stop under pressure
    is the most reliable predictor of an outsized loss, and it is invisible to any
    model that lets a plan be edited in place."*
    """

    break_even: BreakEvenRule | Absent = field(
        default_factory=lambda: Absent("no break-even rule was stated")
    )
    trailing: TrailingRule | Absent = field(
        default_factory=lambda: Absent("no trailing rule was stated")
    )

    def __post_init__(self) -> None:
        if not isinstance(self.break_even, (BreakEvenRule, Absent)):
            raise TypeError("break_even must be a BreakEvenRule or Absent")
        if not isinstance(self.trailing, (TrailingRule, Absent)):
            raise TypeError("trailing must be a TrailingRule or Absent")

    @property
    def is_manual(self) -> bool:
        """Whether every stop move on this trade will be the owner's own."""
        return isinstance(self.break_even, Absent) and isinstance(
            self.trailing, Absent
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "break_even": encode_maybe(self.break_even, BreakEvenRule.to_payload),
            "trailing": encode_maybe(self.trailing, TrailingRule.to_payload),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> StopManagement:
        mapping = require_mapping(raw, "stop management")
        require_exact_keys(mapping, {"break_even", "trailing"}, "stop management")
        return cls(
            break_even=decode_maybe(mapping["break_even"], BreakEvenRule.from_payload),
            trailing=decode_maybe(mapping["trailing"], TrailingRule.from_payload),
        )


@dataclass(frozen=True, slots=True)
class PaperCostPolicy:
    """What a simulated fill is assumed to cost. **A named, versioned policy.**

    In this build both rates are zero, and the zero is the whole reason the type
    exists. A zero that is a *policy* is a different object from a zero that is an
    omission: the day a real fee model arrives it is version 2, every outcome
    already recorded still names the basis that produced it, and no figure
    silently changes meaning. Every surface prints the basis beside the number.

    `slippage_rate` is carried and applied nowhere in this build, which is stated
    rather than hidden: modelling slippage needs spread and depth data FMITS does
    not ingest, and a made-up basis-point figure would be a guess wearing a
    policy's clothes.
    """

    policy_id: str
    version: int
    fee_rate: Decimal
    slippage_rate: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", require_text(self.policy_id, "policy_id"))
        require_int(self.version, "version", minimum=1)
        for name in ("fee_rate", "slippage_rate"):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal")
            if value < 0:
                raise ActivationError(
                    f"{name} must not be negative, got {canonical_decimal_text(value)}; "
                    "a rebate is a different economic fact and is recorded as its own "
                    "event"
                )
            object.__setattr__(self, name, Decimal(canonical_decimal_text(value)))

    @property
    def is_frictionless(self) -> bool:
        return self.fee_rate == 0 and self.slippage_rate == 0

    @property
    def basis(self) -> str:
        """The sentence every surface prints beside a simulated figure."""
        return (
            f"{self.policy_id} v{self.version}: fee rate "
            f"{canonical_decimal_text(self.fee_rate)}, slippage rate "
            f"{canonical_decimal_text(self.slippage_rate)}. A simulated fill is "
            "what this system computes would have happened, not a trade"
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "fee_rate": canonical_decimal_text(self.fee_rate),
            "slippage_rate": canonical_decimal_text(self.slippage_rate),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> PaperCostPolicy:
        mapping = require_mapping(raw, "paper cost policy")
        require_exact_keys(
            mapping,
            {"policy_id", "version", "fee_rate", "slippage_rate"},
            "paper cost policy",
        )
        return cls(
            policy_id=str(mapping["policy_id"]),
            version=require_int(mapping["version"], "version", minimum=1),
            fee_rate=parse_decimal(mapping["fee_rate"], "fee_rate"),
            slippage_rate=parse_decimal(mapping["slippage_rate"], "slippage_rate"),
        )


@dataclass(frozen=True, slots=True)
class TradeActivation:
    """One commitment, handed to the simulator with everything it needs to run it."""

    activated_at: datetime
    plan_id: str
    market: MarketId
    book: Book
    account: AccountId
    direction: TradeDirection
    entry_type: EntryType
    quantity: Quantity
    ladder: ExitLadder
    stop_management: StopManagement
    cost_policy: PaperCostPolicy
    fill_policy_id: str
    fill_policy_version: int
    interval: str
    version_set: VersionSet
    audit: RecordAudit
    entry_price: Decimal | Absent = field(
        default_factory=lambda: Absent("a market entry names no level")
    )
    expires_at: datetime | Absent = field(
        default_factory=lambda: Absent("this activation does not expire")
    )
    proposal_id: str | Absent = field(
        default_factory=lambda: Absent("this activation was not proposed")
    )
    note: str | Absent = field(default_factory=lambda: Absent("no note"))
    schema_version: int = TRADE_ACTIVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "activated_at", require_utc(self.activated_at, "activated_at")
        )
        validate_domain_record_id(self.plan_id)
        if not isinstance(self.market, MarketId):
            raise TypeError("market must be a MarketId")
        require_member(self.book, Book, "book")
        if self.book is not Book.PAPER:
            raise ActivationError(
                f"this build activates the {Book.PAPER.value} book only, and this "
                f"activation names {self.book.value}. The simulator writes fills, "
                "and a fill written into a real-money capacity pool by a typo is "
                "the one mistake no later correction can undo cleanly"
            )
        if not isinstance(self.account, AccountId):
            raise TypeError("account must be an AccountId")
        require_member(self.direction, TradeDirection, "direction")
        if not self.direction.is_directional:
            raise ActivationError(
                "an activation commits to a side; a decision not to act has no "
                "entry to trigger and no stop to be wrong about"
            )
        require_member(self.entry_type, EntryType, "entry_type")
        if not isinstance(self.quantity, Quantity):
            raise TypeError("quantity must be a Quantity")
        if self.quantity.amount <= 0:
            raise ActivationError(
                f"quantity must be positive, got {self.quantity}; direction is "
                "carried by `direction`, and a signed size would be the same fact "
                "in two places"
            )
        if self.quantity.asset != self.market.base_asset:
            raise ActivationError(
                f"the size is stated in {self.quantity.asset} but "
                f"{self.market.value} trades {self.market.base_asset} as its base "
                "asset. Size is a quantity of what is bought, never of what pays "
                "for it"
            )
        if not isinstance(self.ladder, ExitLadder):
            raise TypeError("ladder must be an ExitLadder")
        if not isinstance(self.stop_management, StopManagement):
            raise TypeError("stop_management must be a StopManagement")
        if not isinstance(self.cost_policy, PaperCostPolicy):
            raise TypeError("cost_policy must be a PaperCostPolicy")
        object.__setattr__(
            self, "fill_policy_id", require_text(self.fill_policy_id, "fill_policy_id")
        )
        require_int(self.fill_policy_version, "fill_policy_version", minimum=1)
        object.__setattr__(self, "interval", require_text(self.interval, "interval"))
        if not isinstance(self.version_set, VersionSet):
            raise TypeError("version_set must be a VersionSet")
        require_unmodified(self.audit, "TradeActivation")
        if self.audit.created_at != self.activated_at:
            raise DomainValidationError(
                "audit.created_at must equal activated_at; an activation comes into "
                "being at the moment it is activated and at no other"
            )
        self._validate_entry_level()
        self._validate_ladder_geometry()
        if not isinstance(self.expires_at, Absent):
            object.__setattr__(
                self, "expires_at", require_utc(self.expires_at, "expires_at")
            )
            if self.expires_at <= self.activated_at:
                raise ActivationError(
                    f"expires_at {self.expires_at.isoformat()} is not after "
                    f"activated_at {self.activated_at.isoformat()}; an instruction "
                    "that has already lapsed cannot be acted on"
                )
        if not isinstance(self.proposal_id, Absent):
            validate_domain_record_id(self.proposal_id)
        if not isinstance(self.note, Absent):
            object.__setattr__(self, "note", require_text(self.note, "note"))
        if self.schema_version not in SUPPORTED_TRADE_ACTIVATION_VERSIONS:
            raise DomainValidationError(
                f"trade activation schema_version {self.schema_version} is not one "
                f"this build writes ({sorted(SUPPORTED_TRADE_ACTIVATION_VERSIONS)})"
            )

    def _validate_entry_level(self) -> None:
        """A level is required exactly when the entry type is about one."""
        stated = not isinstance(self.entry_price, Absent)
        if self.entry_type.needs_a_level and not stated:
            raise ActivationError(
                f"a {self.entry_type.value} entry is defined by the price it waits "
                "for, and none was stated. There is no level this package could "
                "supply that would not be an invented one"
            )
        if not self.entry_type.needs_a_level and stated:
            raise ActivationError(
                "a market entry fills at the next bar's open and waits for no "
                "level; a price on one would be a number nothing reads"
            )
        if stated:
            object.__setattr__(
                self, "entry_price", _exact_price(self.entry_price, "entry_price")
            )

    def _validate_ladder_geometry(self) -> None:
        """Targets step away from the entry, in the direction the trade is on.

        Checkable here only when the entry names a level; a market entry has no
        price until a bar supplies one, and the engine checks the ladder against
        the fill it produced. What is always checkable is that the rungs *step*,
        because a ladder that walks backwards has no reading under which it means
        something.
        """
        sign = self.direction.sign
        targets = [leg.target for leg in self.ladder.legs]
        for position, (previous, current) in enumerate(zip(targets, targets[1:])):
            if sign * (current - previous) <= 0:
                raise ActivationError(
                    f"the ladder rung at {canonical_decimal_text(current)} does "
                    f"not lie beyond the one at {canonical_decimal_text(previous)} "
                    "before it. Rungs are stated nearest first and must step away "
                    "from the entry"
                )
        if isinstance(self.entry_price, Absent):
            return
        for position, target in enumerate(targets):
            if sign * (target - self.entry_price) <= 0:
                raise ActivationError(
                    f"ladder leg {position + 1} at "
                    f"{canonical_decimal_text(target)} is not beyond the entry "
                    f"{canonical_decimal_text(self.entry_price)}. A target the "
                    "entry has already passed is not a target"
                )

    # -- projections ---------------------------------------------------------

    @property
    def origin(self) -> ValueOrigin:
        """`ASSERTED`. An instruction is intent, and intent can be wrong."""
        return ValueOrigin.ASSERTED

    @property
    def has_expiry(self) -> bool:
        return not isinstance(self.expires_at, Absent)

    def is_expired_at(self, moment: datetime) -> bool:
        """Whether the instruction has lapsed — a comparison, never a stored flag."""
        when = require_utc(moment, "moment")
        if isinstance(self.expires_at, Absent):
            return False
        return when >= self.expires_at

    def leg_quantity(self, position: int) -> Quantity:
        """The size one rung takes off: `activated quantity × that leg's fraction`.

        A product over the **activated** size, never over what happens to remain.
        Fractions of a shrinking remainder would make the last rung's size a
        function of the order the earlier ones filled in, and two ladders that
        stated the same shares would take different amounts.
        """
        require_int(position, "position", minimum=0)
        if position >= len(self.ladder.legs):
            raise ActivationError(
                f"this ladder has {len(self.ladder.legs)} leg(s); there is no leg "
                f"{position + 1}"
            )
        return self.quantity.scale(self.ladder.legs[position].fraction)

    # -- identity and serialization -----------------------------------------

    @property
    def digest_basis(self) -> dict[str, Any]:
        """The instruction itself, and nothing else.

        Every field below decides what the simulator will do; none of them is
        metadata about when this build happened to write it. Two activations of
        the same commitment at the same instant with the same size, ladder and
        stop rules **are** one instruction, and re-running the command that
        produced them publishes nothing — the idempotency every id in this domain
        already provides, inherited rather than reinvented.
        """
        return {
            "schema_version": self.schema_version,
            "activated_at": encode_timestamp(self.activated_at),
            "plan_id": self.plan_id,
            "market": self.market.to_payload(),
            "book": self.book.value,
            "account": self.account.value,
            "direction": self.direction.value,
            "entry_type": self.entry_type.value,
            "entry_price": encode_maybe(self.entry_price, canonical_decimal_text),
            "quantity": self.quantity.to_payload(),
            "ladder": self.ladder.to_payload(),
            "stop_management": self.stop_management.to_payload(),
            "cost_policy": self.cost_policy.to_payload(),
            "fill_policy_id": self.fill_policy_id,
            "fill_policy_version": self.fill_policy_version,
            "interval": self.interval,
            "expires_at": encode_maybe(self.expires_at, encode_timestamp),
            "proposal_id": encode_maybe(self.proposal_id, str),
            "note": encode_maybe(self.note, str),
            "version_set": self.version_set.to_payload(),
        }

    @property
    def activation_id(self) -> str:
        return build_domain_record_id(
            type_slug=TRADE_ACTIVATION_TYPE_SLUG,
            subject=self.market.value,
            moment=self.activated_at,
            digest=content_digest_over(self.digest_basis),
        )

    @property
    def content_digest(self) -> str:
        return content_digest_over(self.digest_basis)

    def as_consumed_source(self) -> ConsumedSource:
        return ConsumedSource(
            record_id=self.activation_id,
            content_digest=self.content_digest,
            kind=TRADE_ACTIVATION_KIND,
        )

    def to_payload(self) -> dict[str, Any]:
        payload = self.digest_basis
        payload["activation_id"] = self.activation_id
        payload["audit"] = self.audit.to_payload()
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> TradeActivation:
        mapping = require_mapping(raw, "trade activation")
        version = require_payload_version(
            mapping,
            supported=SUPPORTED_TRADE_ACTIVATION_VERSIONS,
            entity="trade activation",
        )
        require_exact_keys(mapping, _ACTIVATION_KEYS, "trade activation")
        decoded = cls(
            activated_at=decode_timestamp(mapping["activated_at"]),
            plan_id=str(mapping["plan_id"]),
            market=MarketId.from_payload(mapping["market"], "activation market"),
            book=_member(Book, mapping["book"], "book"),
            account=AccountId(str(mapping["account"])),
            direction=_member(TradeDirection, mapping["direction"], "direction"),
            entry_type=_member(EntryType, mapping["entry_type"], "entry_type"),
            quantity=Quantity.from_payload(mapping["quantity"], "quantity"),
            ladder=ExitLadder.from_payload(mapping["ladder"]),
            stop_management=StopManagement.from_payload(mapping["stop_management"]),
            cost_policy=PaperCostPolicy.from_payload(mapping["cost_policy"]),
            fill_policy_id=str(mapping["fill_policy_id"]),
            fill_policy_version=require_int(
                mapping["fill_policy_version"], "fill_policy_version", minimum=1
            ),
            interval=str(mapping["interval"]),
            version_set=VersionSet.from_payload(mapping["version_set"]),
            audit=RecordAudit.from_payload(mapping["audit"]),
            entry_price=decode_maybe(
                mapping["entry_price"],
                lambda value: parse_decimal(value, "entry_price"),
            ),
            expires_at=decode_maybe(mapping["expires_at"], decode_timestamp),
            proposal_id=decode_maybe(mapping["proposal_id"], str),
            note=decode_maybe(mapping["note"], str),
            schema_version=version,
        )
        if mapping["activation_id"] != decoded.activation_id:
            raise PayloadDecodeError(
                f"activation_id {mapping['activation_id']!r} does not match the "
                f"digest of the instruction it claims to identify "
                f"({decoded.activation_id!r})"
            )
        return decoded


_ACTIVATION_KEYS = frozenset({
    "schema_version",
    "activation_id",
    "activated_at",
    "plan_id",
    "market",
    "book",
    "account",
    "direction",
    "entry_type",
    "entry_price",
    "quantity",
    "ladder",
    "stop_management",
    "cost_policy",
    "fill_policy_id",
    "fill_policy_version",
    "interval",
    "expires_at",
    "proposal_id",
    "note",
    "version_set",
    "audit",
})


def _member(enum_type: Any, value: Any, entity: str) -> Any:
    try:
        return enum_type(value)
    except ValueError as error:
        raise PayloadDecodeError(
            f"{entity} {value!r} is not a known {enum_type.__name__}; an unknown "
            "member is a clean rejection, never a default"
        ) from error
