"""The frozen shapes a market snapshot is built from.

**This module imports no engine, and that is a rule rather than an accident**
(data model §6.3 rule 11). It holds the *shape* of a frozen market bundle; the
composition root — which does import the engines — fills it. The precedent is
the decision-context engine, which imports nothing from `fmis` and takes seven
integers, two strings, a flag and a timestamp, precisely so it cannot parse a
presentation model back into data.

The practical consequence: every reading below is plain frozen data — strings,
ints, exact decimals, timestamps and `Absent(reason)`. A structural trend arrives
as the *label the engine produced*, not as a `StructuralTrendSnapshot`. That
keeps Law 6 checkable by a single import guard rather than by reading every
import in the domain, and it means a regime policy change in 2029 cannot reach
backwards into a 2026 snapshot through a shared object.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from fmis.accounts import Book, MarketId
from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.money import canonical_decimal_text, parse_decimal
from fmis.provenance import Absent, decode_maybe, encode_maybe
from fmis.records import (
    DomainValidationError,
    PayloadDecodeError,
    TradeDomainError,
    require_bool,
    require_int,
    require_member,
    require_text,
    require_tuple_of,
    require_utc,
)

__all__ = [
    "SnapshotError",
    "SnapshotRole",
    "ROLE_ORDER",
    "SnapshotTrigger",
    "TradeDirection",
    "LevelSideRef",
    "LevelOriginRef",
    "LevelReading",
    "RiskRewardReading",
    "RegimeDimensionReading",
    "RegimeReading",
    "RequirementReading",
    "SufficiencyReading",
    "EvidenceFamilyReading",
    "IndependenceDisclosure",
    "ConflictNote",
    "FreshnessReading",
    "TriggerBasis",
    "StopTriggerSemantics",
    "SetupReading",
    "Anchor",
    "RoleReading",
]


class SnapshotError(TradeDomainError):
    """Base class for every snapshotting failure."""


class SnapshotRole(Enum):
    """The three timeframe roles a decision is read across.

    The names are the workspace's own. `CONTEXT` gates whether any direction may
    exist at all, which is why its bar age is the one freshness number that can
    invalidate everything below it.
    """

    CONTEXT = "context"
    SETUP = "setup"
    EXECUTION = "execution"


#: Reporting order — never enum definition order by accident. Widest first, so a
#: reader meets the gate before the trigger.
ROLE_ORDER: tuple[SnapshotRole, ...] = (
    SnapshotRole.CONTEXT,
    SnapshotRole.SETUP,
    SnapshotRole.EXECUTION,
)


class SnapshotTrigger(Enum):
    """Why this bundle was frozen.

    Recorded because "what did the system know" is a different question at
    proposal time, at acceptance and at the moment a journal entry was written —
    and `AP` §25.3 requires the constraint check to be evaluated twice for exactly
    that reason.
    """

    PROPOSAL_CREATED = "proposal_created"
    PROPOSAL_ACCEPTED = "proposal_accepted"
    PLAN_COMMITTED = "plan_committed"
    JOURNAL_WRITE = "journal_write"
    EPISODE_CAPTURE = "episode_capture"
    POSITION_REVIEW = "position_review"


class TradeDirection(Enum):
    """Which side a reading or a proposal came down on.

    **`NO_TRADE` is a first-class value, not an absence.** An explicit decision
    not to act is a decision, and it reaches the same lifecycle stream and the
    same learning corpus every other decision does. Modelling it as `None` would
    make "we looked and declined" indistinguishable from "we never looked".

    Named `TradeDirection` rather than `Direction` because the swing-setup engine
    already exports a `Direction` for the market half's own reading, and this
    repository holds zero public-name collisions as a measured invariant.
    """

    LONG = "long"
    SHORT = "short"
    NO_TRADE = "no_trade"

    @property
    def is_directional(self) -> bool:
        return self is not TradeDirection.NO_TRADE

    @property
    def opposite(self) -> TradeDirection:
        if self is TradeDirection.LONG:
            return TradeDirection.SHORT
        if self is TradeDirection.SHORT:
            return TradeDirection.LONG
        return TradeDirection.NO_TRADE


class LevelSideRef(Enum):
    """Which side of price a level sits on, as the engine reported it."""

    ABOVE = "above"
    BELOW = "below"


def _encode_decimal(value: Decimal) -> str:
    return canonical_decimal_text(value)


def _decode_decimal(raw: Any) -> Decimal:
    return parse_decimal(raw, "decimal")


@dataclass(frozen=True, slots=True)
class LevelOriginRef:
    """Where a price level came from — a `MEASURED` fact, carried by reference.

    ADR-0024's provenance, frozen: the originating swing, its index and the
    confirmation bars that made it a level. This is the component of an `Anchor`
    that makes the anchor `MEASURED` rather than policy-derived, which is the
    whole reason one-live-proposal-per-anchor cannot be redrawn by a later policy
    change.
    """

    origin_id: str
    swing_index: int
    confirmation_bars: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "origin_id", require_text(self.origin_id, "origin_id"))
        require_int(self.swing_index, "swing_index", minimum=0)
        require_int(self.confirmation_bars, "confirmation_bars", minimum=0)

    def to_payload(self) -> dict[str, Any]:
        return {
            "origin_id": self.origin_id,
            "swing_index": self.swing_index,
            "confirmation_bars": self.confirmation_bars,
        }

    @classmethod
    def from_payload(cls, raw: Any) -> LevelOriginRef:
        mapping = _object(raw, "level origin")
        _keys(mapping, {"origin_id", "swing_index", "confirmation_bars"}, "level origin")
        return cls(
            origin_id=str(mapping["origin_id"]),
            swing_index=mapping["swing_index"],
            confirmation_bars=mapping["confirmation_bars"],
        )


@dataclass(frozen=True, slots=True)
class LevelReading:
    """One already-detected price level, frozen with its origin.

    **No price in this domain is fabricated.** A stop and every target is a real,
    already-detected level reused by reference, or explicitly `Absent`. The exact
    price arrives through `exact_from_market_price` at the composition root — the
    single named `float` → exact crossing — never by re-deriving the level here.
    """

    price: Decimal
    side: LevelSideRef
    origin: LevelOriginRef
    label: str

    def __post_init__(self) -> None:
        if not isinstance(self.price, Decimal):
            raise TypeError(f"price must be a Decimal, got {type(self.price).__name__}")
        if self.price <= 0:
            raise DomainValidationError(
                f"level price must be positive, got {self.price}"
            )
        object.__setattr__(self, "price", Decimal(canonical_decimal_text(self.price)))
        require_member(self.side, LevelSideRef, "side")
        if not isinstance(self.origin, LevelOriginRef):
            raise TypeError(
                f"origin must be a LevelOriginRef, got {type(self.origin).__name__}"
            )
        object.__setattr__(self, "label", require_text(self.label, "label"))

    def to_payload(self) -> dict[str, Any]:
        return {
            "price": canonical_decimal_text(self.price),
            "side": self.side.value,
            "origin": self.origin.to_payload(),
            "label": self.label,
        }

    @classmethod
    def from_payload(cls, raw: Any) -> LevelReading:
        mapping = _object(raw, "level")
        _keys(mapping, {"price", "side", "origin", "label"}, "level")
        return cls(
            price=parse_decimal(mapping["price"], "level price"),
            side=_member(LevelSideRef, mapping["side"], "level side"),
            origin=LevelOriginRef.from_payload(mapping["origin"]),
            label=str(mapping["label"]),
        )


@dataclass(frozen=True, slots=True)
class RiskRewardReading:
    """Risk and reward as a **pair**, never as a stored quotient.

    §4.3's rule, at its sharpest: `risk_reward` is a name that implies a division,
    so the numerator and denominator are what is stored and `ratio_text` is
    computed at read time. `avg × qty ≠ cost` under any decimal context, and a
    stored ratio would be the one number nobody could reconcile against the two it
    came from.
    """

    risk_distance: Decimal
    reward_distance: Decimal

    def __post_init__(self) -> None:
        for name in ("risk_distance", "reward_distance"):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
            if value <= 0:
                raise DomainValidationError(
                    f"{name} must be positive, got {value}; a zero risk distance "
                    "means there is no stop, which is a different fact"
                )
            object.__setattr__(self, name, Decimal(canonical_decimal_text(value)))

    @property
    def ratio(self) -> Decimal:
        """Reward ÷ risk — a projection, computed here and stored nowhere."""
        return self.reward_distance / self.risk_distance

    @property
    def arithmetic(self) -> str:
        """The division shown, not merely its result (`AR`-3, unchanged)."""
        return (
            f"{canonical_decimal_text(self.reward_distance)} ÷ "
            f"{canonical_decimal_text(self.risk_distance)}"
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "risk_distance": canonical_decimal_text(self.risk_distance),
            "reward_distance": canonical_decimal_text(self.reward_distance),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> RiskRewardReading:
        mapping = _object(raw, "risk/reward")
        _keys(mapping, {"risk_distance", "reward_distance"}, "risk/reward")
        return cls(
            risk_distance=parse_decimal(mapping["risk_distance"], "risk_distance"),
            reward_distance=parse_decimal(mapping["reward_distance"], "reward_distance"),
        )


@dataclass(frozen=True, slots=True)
class RegimeDimensionReading:
    """One regime dimension as the engine reported it, with what was missing.

    `unavailable` is separate from a low-confidence state on purpose: ADR-0025's
    own distinction is between evidence that was *absent* and evidence that
    *disagreed*, and collapsing them is how a snapshot starts looking more certain
    than the reading it froze.
    """

    name: str
    state: str | Absent
    evidence: tuple[str, ...] = ()
    unavailable: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_text(self.name, "name"))
        if not isinstance(self.state, Absent):
            object.__setattr__(self, "state", require_text(self.state, "state"))
        require_tuple_of(self.evidence, str, "evidence")
        require_tuple_of(self.unavailable, str, "unavailable")

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": encode_maybe(self.state, str),
            "evidence": list(self.evidence),
            "unavailable": list(self.unavailable),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> RegimeDimensionReading:
        mapping = _object(raw, "regime dimension")
        _keys(mapping, {"name", "state", "evidence", "unavailable"}, "regime dimension")
        return cls(
            name=str(mapping["name"]),
            state=decode_maybe(mapping["state"], str),
            evidence=tuple(_array(mapping["evidence"], "regime evidence", str)),
            unavailable=tuple(
                _array(mapping["unavailable"], "regime unavailable", str)
            ),
        )


@dataclass(frozen=True, slots=True)
class RegimeReading:
    """Every regime dimension for one role, in a stable order."""

    dimensions: tuple[RegimeDimensionReading, ...]

    def __post_init__(self) -> None:
        require_tuple_of(
            self.dimensions, RegimeDimensionReading, "dimensions", minimum_length=1
        )
        names = [dimension.name for dimension in self.dimensions]
        if len(set(names)) != len(names):
            raise DomainValidationError(
                "a regime dimension must not be reported twice; two answers for "
                "one dimension would let a reader pick the one they preferred"
            )

    def dimension(self, name: str) -> RegimeDimensionReading | None:
        for dimension in self.dimensions:
            if dimension.name == name:
                return dimension
        return None

    def to_payload(self) -> dict[str, Any]:
        return {"dimensions": [d.to_payload() for d in self.dimensions]}

    @classmethod
    def from_payload(cls, raw: Any) -> RegimeReading:
        mapping = _object(raw, "regime")
        _keys(mapping, {"dimensions"}, "regime")
        return cls(
            dimensions=tuple(
                RegimeDimensionReading.from_payload(item)
                for item in _array(mapping["dimensions"], "regime dimensions", dict)
            )
        )


@dataclass(frozen=True, slots=True)
class RequirementReading:
    """One sufficiency requirement, whether it was met, and which layer decided.

    ADR-0026's own output, frozen — **not a summary of it**. `source` names the
    layer whose rule was applied, so a reader who disagrees with a verdict goes to
    that layer rather than to a threshold invented at snapshot time.
    """

    requirement: str
    met: bool
    severity: str
    statement: str
    source: str

    def __post_init__(self) -> None:
        require_bool(self.met, "met")
        for name in ("requirement", "severity", "statement", "source"):
            object.__setattr__(self, name, require_text(getattr(self, name), name))

    def to_payload(self) -> dict[str, Any]:
        return {
            "requirement": self.requirement,
            "met": self.met,
            "severity": self.severity,
            "statement": self.statement,
            "source": self.source,
        }

    @classmethod
    def from_payload(cls, raw: Any) -> RequirementReading:
        mapping = _object(raw, "requirement")
        _keys(
            mapping,
            {"requirement", "met", "severity", "statement", "source"},
            "requirement",
        )
        return cls(
            requirement=str(mapping["requirement"]),
            met=require_bool(mapping["met"], "met"),
            severity=str(mapping["severity"]),
            statement=str(mapping["statement"]),
            source=str(mapping["source"]),
        )


@dataclass(frozen=True, slots=True)
class SufficiencyReading:
    """The decision-context state plus every requirement behind it.

    Every requirement is carried, **including the met ones**: a reader who sees
    only failures cannot tell a clean reading from a partial one, and the
    completeness rule is the whole reason ADR-0026 exists.
    """

    state: str
    checks: tuple[RequirementReading, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", require_text(self.state, "state"))
        require_tuple_of(self.checks, RequirementReading, "checks", minimum_length=1)
        names = [check.requirement for check in self.checks]
        if len(set(names)) != len(names):
            raise DomainValidationError("a requirement must not be checked twice")

    @property
    def unmet(self) -> tuple[RequirementReading, ...]:
        """A projection over the frozen checks — never a stored field."""
        return tuple(check for check in self.checks if not check.met)

    def to_payload(self) -> dict[str, Any]:
        return {"state": self.state, "checks": [c.to_payload() for c in self.checks]}

    @classmethod
    def from_payload(cls, raw: Any) -> SufficiencyReading:
        mapping = _object(raw, "sufficiency")
        _keys(mapping, {"state", "checks"}, "sufficiency")
        return cls(
            state=str(mapping["state"]),
            checks=tuple(
                RequirementReading.from_payload(item)
                for item in _array(mapping["checks"], "sufficiency checks", dict)
            ),
        )


@dataclass(frozen=True, slots=True)
class EvidenceFamilyReading:
    """One evidence family's status and what contributed to it."""

    family: str
    status: str
    alignment: str | Absent
    contributing: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "family", require_text(self.family, "family"))
        object.__setattr__(self, "status", require_text(self.status, "status"))
        if not isinstance(self.alignment, Absent):
            object.__setattr__(
                self, "alignment", require_text(self.alignment, "alignment")
            )
        require_tuple_of(self.contributing, str, "contributing")

    def to_payload(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "status": self.status,
            "alignment": encode_maybe(self.alignment, str),
            "contributing": list(self.contributing),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> EvidenceFamilyReading:
        mapping = _object(raw, "evidence family")
        _keys(
            mapping, {"family", "status", "alignment", "contributing"}, "evidence family"
        )
        return cls(
            family=str(mapping["family"]),
            status=str(mapping["status"]),
            alignment=decode_maybe(mapping["alignment"], str),
            contributing=tuple(
                _array(mapping["contributing"], "contributing", str)
            ),
        )


@dataclass(frozen=True, slots=True)
class IndependenceDisclosure:
    """How independent the evidence families actually were, measured.

    This field earns its place for one reason: `AW` §5.2 measured κ = 0.02 / 0.10
    / **0.41** across the three family pairs, with the CONTEXT family
    participating in **100.0 %** of 578 directional results — traced to the regime
    gate and the CTX vote reading the identical trend value. `BD` R-05 rates it
    Certain probability, High impact, **Low detectability**: *"invisible on every
    page, while the page states the guarantee as designed."*

    Freezing it onto the snapshot is what makes the weakness travel with the
    decision instead of living only in an untracked research document. It carries
    its own `n`, and `superseded_by` names the later study whose sample replaces
    this one rather than silently keeping a stale number.
    """

    pair_kappas: tuple[tuple[str, Decimal], ...]
    family_participation: tuple[tuple[str, Decimal], ...]
    sample_size: int
    note: str
    superseded_by: str | Absent

    def __post_init__(self) -> None:
        for field_name in ("pair_kappas", "family_participation"):
            entries = getattr(self, field_name)
            if not isinstance(entries, tuple):
                raise TypeError(f"{field_name} must be a tuple of (str, Decimal) pairs")
            seen: set[str] = set()
            normalized: list[tuple[str, Decimal]] = []
            for position, entry in enumerate(entries):
                if not isinstance(entry, tuple) or len(entry) != 2:
                    raise TypeError(
                        f"{field_name}[{position}] must be a (str, Decimal) pair"
                    )
                label = require_text(entry[0], f"{field_name}[{position}] label")
                if not isinstance(entry[1], Decimal):
                    raise TypeError(
                        f"{field_name}[{position}] value must be a Decimal, got "
                        f"{type(entry[1]).__name__}"
                    )
                if label in seen:
                    raise DomainValidationError(
                        f"{field_name} names {label!r} twice"
                    )
                seen.add(label)
                normalized.append(
                    (label, Decimal(canonical_decimal_text(entry[1])))
                )
            object.__setattr__(self, field_name, tuple(sorted(normalized)))
        require_int(self.sample_size, "sample_size", minimum=0)
        object.__setattr__(self, "note", require_text(self.note, "note"))
        if not isinstance(self.superseded_by, Absent):
            object.__setattr__(
                self, "superseded_by", require_text(self.superseded_by, "superseded_by")
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "pair_kappas": [
                {"pair": label, "kappa": canonical_decimal_text(value)}
                for label, value in self.pair_kappas
            ],
            "family_participation": [
                {"family": label, "share": canonical_decimal_text(value)}
                for label, value in self.family_participation
            ],
            "sample_size": self.sample_size,
            "note": self.note,
            "superseded_by": encode_maybe(self.superseded_by, str),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> IndependenceDisclosure:
        mapping = _object(raw, "independence disclosure")
        _keys(
            mapping,
            {
                "pair_kappas",
                "family_participation",
                "sample_size",
                "note",
                "superseded_by",
            },
            "independence disclosure",
        )
        kappas = tuple(
            (str(item["pair"]), parse_decimal(item["kappa"], "kappa"))
            for item in _array(mapping["pair_kappas"], "pair_kappas", dict)
        )
        participation = tuple(
            (str(item["family"]), parse_decimal(item["share"], "share"))
            for item in _array(
                mapping["family_participation"], "family_participation", dict
            )
        )
        return cls(
            pair_kappas=kappas,
            family_participation=participation,
            sample_size=mapping["sample_size"],
            note=str(mapping["note"]),
            superseded_by=decode_maybe(mapping["superseded_by"], str),
        )


@dataclass(frozen=True, slots=True)
class ConflictNote:
    """One conflict, reported verbatim and **never resolved**.

    There is no `resolution`, no `winner`, no `severity_rank` and no tiebreak
    field on this type, and there never will be. A vocabulary scan already asserts
    the workspace's conflict module contains no verb of resolution; the data model
    keeps that, and a snapshot's conflict list is a frozen statement rather than an
    input to a decision the system makes on the owner's behalf.
    """

    kind: str
    statement: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", require_text(self.kind, "kind"))
        object.__setattr__(self, "statement", require_text(self.statement, "statement"))

    def to_payload(self) -> dict[str, Any]:
        return {"kind": self.kind, "statement": self.statement}

    @classmethod
    def from_payload(cls, raw: Any) -> ConflictNote:
        mapping = _object(raw, "conflict")
        _keys(mapping, {"kind", "statement"}, "conflict")
        return cls(kind=str(mapping["kind"]), statement=str(mapping["statement"]))


@dataclass(frozen=True, slots=True)
class FreshnessReading:
    """The **three** bar ages — context, setup and execution — measured at freeze.

    `fmits setup` does not print these, and the context role was measured live at
    8 days 16 hours. That is the role that gates whether any direction may exist,
    so a proposal resting on it without stating its age is a proposal whose
    strongest claim is undated.
    """

    measured_at: datetime
    context_bars: int | Absent
    setup_bars: int | Absent
    execution_bars: int | Absent

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "measured_at", require_utc(self.measured_at, "measured_at")
        )
        for name in ("context_bars", "setup_bars", "execution_bars"):
            value = getattr(self, name)
            if not isinstance(value, Absent):
                require_int(value, name, minimum=0)

    @property
    def gating_age(self) -> int | Absent:
        """The context role's age — the one that can invalidate everything below."""
        return self.context_bars

    def to_payload(self) -> dict[str, Any]:
        return {
            "measured_at": encode_timestamp(self.measured_at),
            "context_bars": encode_maybe(self.context_bars, int),
            "setup_bars": encode_maybe(self.setup_bars, int),
            "execution_bars": encode_maybe(self.execution_bars, int),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> FreshnessReading:
        mapping = _object(raw, "freshness")
        _keys(
            mapping,
            {"measured_at", "context_bars", "setup_bars", "execution_bars"},
            "freshness",
        )
        return cls(
            measured_at=decode_timestamp(mapping["measured_at"]),
            context_bars=decode_maybe(mapping["context_bars"], _as_int),
            setup_bars=decode_maybe(mapping["setup_bars"], _as_int),
            execution_bars=decode_maybe(mapping["execution_bars"], _as_int),
        )


class TriggerBasis(Enum):
    """What makes a level count as reached: a touch, or a close beyond it."""

    TOUCH = "touch"
    CLOSE = "close"


@dataclass(frozen=True, slots=True)
class StopTriggerSemantics:
    """Two fields where the product has one number.

    `BD` R-13: the stop price and the structural invalidation are the same number,
    and one triggers on a **touch** while the other requires a **close**. Splitting
    them is named as the cheapest correctness improvement available anywhere in
    `BE`, and it makes *"stopped out on a wick while the thesis held"* derivable
    with no new data — which is the one lifecycle state §16.5 says the model would
    like and cannot otherwise have.
    """

    stop_basis: TriggerBasis
    invalidation_basis: TriggerBasis

    def __post_init__(self) -> None:
        require_member(self.stop_basis, TriggerBasis, "stop_basis")
        require_member(self.invalidation_basis, TriggerBasis, "invalidation_basis")

    @property
    def separates_wick_from_thesis(self) -> bool:
        """Whether a wick through the stop can leave the thesis standing.

        True exactly when the stop triggers on a touch and the invalidation
        requires a close. When both use the same basis the distinction collapses
        and the measurement is unavailable — which is the situation today.
        """
        return (
            self.stop_basis is TriggerBasis.TOUCH
            and self.invalidation_basis is TriggerBasis.CLOSE
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "stop_basis": self.stop_basis.value,
            "invalidation_basis": self.invalidation_basis.value,
        }

    @classmethod
    def from_payload(cls, raw: Any) -> StopTriggerSemantics:
        mapping = _object(raw, "stop trigger semantics")
        _keys(mapping, {"stop_basis", "invalidation_basis"}, "stop trigger semantics")
        return cls(
            stop_basis=_member(TriggerBasis, mapping["stop_basis"], "stop_basis"),
            invalidation_basis=_member(
                TriggerBasis, mapping["invalidation_basis"], "invalidation_basis"
            ),
        )


@dataclass(frozen=True, slots=True)
class Anchor:
    """What makes two observations *the same idea*.

    `(market_id, book, direction, invalidation_level_origin)`. Every component is
    either declared or `MEASURED` — the level origin is a fact the level-crossing
    engine already produced, carrying its own `confirmation_bars` provenance
    (ADR-0024) — so an anchor **cannot be redrawn by a later policy change**.

    That property is the whole argument for keying deduplication here rather than
    on a policy-derived occurrence id. `AV`'s setup identity was derived from a
    window-relative bar index and changed every bar, producing 549 "unique setups"
    from 552 directional observations — a 1:1 ratio. An anchor that a
    `calculation_version` bump can move would reproduce that failure one layer up,
    and captured artifacts would be pointing at it.
    """

    market: MarketId
    book: Book
    direction: TradeDirection
    invalidation_origin: LevelOriginRef

    def __post_init__(self) -> None:
        if not isinstance(self.market, MarketId):
            raise TypeError(
                f"market must be a MarketId, got {type(self.market).__name__}"
            )
        require_member(self.book, Book, "book")
        require_member(self.direction, TradeDirection, "direction")
        if not isinstance(self.invalidation_origin, LevelOriginRef):
            raise TypeError(
                "invalidation_origin must be a LevelOriginRef, got "
                f"{type(self.invalidation_origin).__name__}"
            )
        if not self.direction.is_directional:
            raise DomainValidationError(
                "an anchor requires a direction; NO_TRADE has no invalidation "
                "level to anchor on, so a no-trade decision is never deduplicated "
                "against a directional one"
            )

    @property
    def key(self) -> str:
        """A stable, human-readable rendering — for logs and messages only."""
        return (
            f"{self.market.value}|{self.book.value}|{self.direction.value}|"
            f"{self.invalidation_origin.origin_id}"
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "market": self.market.to_payload(),
            "book": self.book.value,
            "direction": self.direction.value,
            "invalidation_origin": self.invalidation_origin.to_payload(),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> Anchor:
        mapping = _object(raw, "anchor")
        _keys(
            mapping, {"market", "book", "direction", "invalidation_origin"}, "anchor"
        )
        return cls(
            market=MarketId.from_payload(mapping["market"], "anchor market"),
            book=_member(Book, mapping["book"], "book"),
            direction=_member(TradeDirection, mapping["direction"], "direction"),
            invalidation_origin=LevelOriginRef.from_payload(
                mapping["invalidation_origin"]
            ),
        )


@dataclass(frozen=True, slots=True)
class SetupReading:
    """The deterministic setup reading, frozen — plus the three fields it lacks.

    The first block is the engine's own `SetupAssessment` as it was produced:
    state, direction, thesis, factors, confirmation, invalidation, trigger,
    reference price, stop, targets, risk/reward, probability, limitations and the
    policy id. **This layer adds no market computation and recomputes nothing.**

    The three additions are `anchor` (§9.4), `freshness` (the three bar ages the
    CLI does not print) and `stop_trigger_semantics` (§16.5's wick case). Each is
    a field the engine has no reason to compute and the domain cannot do without.
    """

    as_of: datetime
    state: str
    direction: TradeDirection
    policy_id: str
    thesis: str | Absent
    directional_factors: tuple[str, ...]
    confirmation: str | Absent
    trigger: str | Absent
    reference_price: Decimal | Absent
    invalidation: LevelReading | Absent
    stop: LevelReading | Absent
    targets: tuple[LevelReading, ...]
    risk_reward: RiskRewardReading | Absent
    probability: str
    limitations: tuple[str, ...]
    anchor: Anchor | Absent
    freshness: FreshnessReading
    stop_trigger_semantics: StopTriggerSemantics

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", require_utc(self.as_of, "as_of"))
        object.__setattr__(self, "state", require_text(self.state, "state"))
        require_member(self.direction, TradeDirection, "direction")
        object.__setattr__(self, "policy_id", require_text(self.policy_id, "policy_id"))
        for name in ("thesis", "confirmation", "trigger"):
            value = getattr(self, name)
            if not isinstance(value, Absent):
                object.__setattr__(self, name, require_text(value, name))
        require_tuple_of(self.directional_factors, str, "directional_factors")
        if not isinstance(self.reference_price, Absent):
            if not isinstance(self.reference_price, Decimal):
                raise TypeError("reference_price must be a Decimal or Absent")
            object.__setattr__(
                self,
                "reference_price",
                Decimal(canonical_decimal_text(self.reference_price)),
            )
        for name in ("invalidation", "stop"):
            value = getattr(self, name)
            if not isinstance(value, (LevelReading, Absent)):
                raise TypeError(f"{name} must be a LevelReading or Absent")
        require_tuple_of(self.targets, LevelReading, "targets")
        if not isinstance(self.risk_reward, (RiskRewardReading, Absent)):
            raise TypeError("risk_reward must be a RiskRewardReading or Absent")
        object.__setattr__(
            self, "probability", require_text(self.probability, "probability")
        )
        require_tuple_of(self.limitations, str, "limitations")
        if not isinstance(self.anchor, (Anchor, Absent)):
            raise TypeError("anchor must be an Anchor or Absent")
        if not isinstance(self.freshness, FreshnessReading):
            raise TypeError("freshness must be a FreshnessReading")
        if not isinstance(self.stop_trigger_semantics, StopTriggerSemantics):
            raise TypeError("stop_trigger_semantics must be a StopTriggerSemantics")
        if isinstance(self.stop, Absent) and not isinstance(self.risk_reward, Absent):
            raise DomainValidationError(
                "a reading with no stop cannot state a risk/reward; without a "
                "stop there is no risk denominator"
            )
        if not self.direction.is_directional and not isinstance(self.anchor, Absent):
            raise DomainValidationError(
                "a NO_TRADE reading cannot carry an anchor; there is no "
                "invalidation level to anchor on"
            )
        if isinstance(self.anchor, Anchor) and self.anchor.direction is not self.direction:
            raise DomainValidationError(
                f"anchor direction {self.anchor.direction.value} disagrees with "
                f"the reading's own direction {self.direction.value}"
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "as_of": encode_timestamp(self.as_of),
            "state": self.state,
            "direction": self.direction.value,
            "policy_id": self.policy_id,
            "thesis": encode_maybe(self.thesis, str),
            "directional_factors": list(self.directional_factors),
            "confirmation": encode_maybe(self.confirmation, str),
            "trigger": encode_maybe(self.trigger, str),
            "reference_price": encode_maybe(self.reference_price, _encode_decimal),
            "invalidation": encode_maybe(self.invalidation, LevelReading.to_payload),
            "stop": encode_maybe(self.stop, LevelReading.to_payload),
            "targets": [target.to_payload() for target in self.targets],
            "risk_reward": encode_maybe(
                self.risk_reward, RiskRewardReading.to_payload
            ),
            "probability": self.probability,
            "limitations": list(self.limitations),
            "anchor": encode_maybe(self.anchor, Anchor.to_payload),
            "freshness": self.freshness.to_payload(),
            "stop_trigger_semantics": self.stop_trigger_semantics.to_payload(),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> SetupReading:
        mapping = _object(raw, "setup reading")
        _keys(
            mapping,
            {
                "as_of",
                "state",
                "direction",
                "policy_id",
                "thesis",
                "directional_factors",
                "confirmation",
                "trigger",
                "reference_price",
                "invalidation",
                "stop",
                "targets",
                "risk_reward",
                "probability",
                "limitations",
                "anchor",
                "freshness",
                "stop_trigger_semantics",
            },
            "setup reading",
        )
        return cls(
            as_of=decode_timestamp(mapping["as_of"]),
            state=str(mapping["state"]),
            direction=_member(TradeDirection, mapping["direction"], "direction"),
            policy_id=str(mapping["policy_id"]),
            thesis=decode_maybe(mapping["thesis"], str),
            directional_factors=tuple(
                _array(mapping["directional_factors"], "directional_factors", str)
            ),
            confirmation=decode_maybe(mapping["confirmation"], str),
            trigger=decode_maybe(mapping["trigger"], str),
            reference_price=decode_maybe(mapping["reference_price"], _decode_decimal),
            invalidation=decode_maybe(mapping["invalidation"], LevelReading.from_payload),
            stop=decode_maybe(mapping["stop"], LevelReading.from_payload),
            targets=tuple(
                LevelReading.from_payload(item)
                for item in _array(mapping["targets"], "targets", dict)
            ),
            risk_reward=decode_maybe(
                mapping["risk_reward"], RiskRewardReading.from_payload
            ),
            probability=str(mapping["probability"]),
            limitations=tuple(_array(mapping["limitations"], "limitations", str)),
            anchor=decode_maybe(mapping["anchor"], Anchor.from_payload),
            freshness=FreshnessReading.from_payload(mapping["freshness"]),
            stop_trigger_semantics=StopTriggerSemantics.from_payload(
                mapping["stop_trigger_semantics"]
            ),
        )


@dataclass(frozen=True, slots=True)
class RoleReading:
    """Everything one timeframe role contributed, frozen together."""

    role: SnapshotRole
    interval: str
    as_of: datetime
    closed_count: int
    bar_age: int | Absent
    structural_trend: str | Absent
    sequence_state: str | Absent
    nearest_level_above: LevelReading | Absent
    nearest_level_below: LevelReading | Absent
    latest_break: str | Absent
    latest_change_of_character: str | Absent
    regime: RegimeReading

    def __post_init__(self) -> None:
        require_member(self.role, SnapshotRole, "role")
        object.__setattr__(self, "interval", require_text(self.interval, "interval"))
        object.__setattr__(self, "as_of", require_utc(self.as_of, "as_of"))
        require_int(self.closed_count, "closed_count", minimum=0)
        if not isinstance(self.bar_age, Absent):
            require_int(self.bar_age, "bar_age", minimum=0)
        for name in (
            "structural_trend",
            "sequence_state",
            "latest_break",
            "latest_change_of_character",
        ):
            value = getattr(self, name)
            if not isinstance(value, Absent):
                object.__setattr__(self, name, require_text(value, name))
        for name in ("nearest_level_above", "nearest_level_below"):
            value = getattr(self, name)
            if not isinstance(value, (LevelReading, Absent)):
                raise TypeError(f"{name} must be a LevelReading or Absent")
        if isinstance(self.nearest_level_above, LevelReading) and (
            self.nearest_level_above.side is not LevelSideRef.ABOVE
        ):
            raise DomainValidationError(
                "nearest_level_above carries a level marked as being below price"
            )
        if isinstance(self.nearest_level_below, LevelReading) and (
            self.nearest_level_below.side is not LevelSideRef.BELOW
        ):
            raise DomainValidationError(
                "nearest_level_below carries a level marked as being above price"
            )
        if not isinstance(self.regime, RegimeReading):
            raise TypeError("regime must be a RegimeReading")

    def to_payload(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "interval": self.interval,
            "as_of": encode_timestamp(self.as_of),
            "closed_count": self.closed_count,
            "bar_age": encode_maybe(self.bar_age, int),
            "structural_trend": encode_maybe(self.structural_trend, str),
            "sequence_state": encode_maybe(self.sequence_state, str),
            "nearest_level_above": encode_maybe(
                self.nearest_level_above, LevelReading.to_payload
            ),
            "nearest_level_below": encode_maybe(
                self.nearest_level_below, LevelReading.to_payload
            ),
            "latest_break": encode_maybe(self.latest_break, str),
            "latest_change_of_character": encode_maybe(
                self.latest_change_of_character, str
            ),
            "regime": self.regime.to_payload(),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> RoleReading:
        mapping = _object(raw, "role reading")
        _keys(
            mapping,
            {
                "role",
                "interval",
                "as_of",
                "closed_count",
                "bar_age",
                "structural_trend",
                "sequence_state",
                "nearest_level_above",
                "nearest_level_below",
                "latest_break",
                "latest_change_of_character",
                "regime",
            },
            "role reading",
        )
        return cls(
            role=_member(SnapshotRole, mapping["role"], "role"),
            interval=str(mapping["interval"]),
            as_of=decode_timestamp(mapping["as_of"]),
            closed_count=mapping["closed_count"],
            bar_age=decode_maybe(mapping["bar_age"], _as_int),
            structural_trend=decode_maybe(mapping["structural_trend"], str),
            sequence_state=decode_maybe(mapping["sequence_state"], str),
            nearest_level_above=decode_maybe(
                mapping["nearest_level_above"], LevelReading.from_payload
            ),
            nearest_level_below=decode_maybe(
                mapping["nearest_level_below"], LevelReading.from_payload
            ),
            latest_break=decode_maybe(mapping["latest_break"], str),
            latest_change_of_character=decode_maybe(
                mapping["latest_change_of_character"], str
            ),
            regime=RegimeReading.from_payload(mapping["regime"]),
        )


# --------------------------------------------------------------------------
# Decoding helpers, shared by every reading above.
# --------------------------------------------------------------------------


def _object(raw: Any, entity: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise PayloadDecodeError(
            f"{entity} must be a JSON object, got {type(raw).__name__}"
        )
    return raw


def _keys(mapping: Mapping[str, Any], expected: set[str], entity: str) -> None:
    if set(mapping) != expected:
        raise PayloadDecodeError(
            f"{entity} keys {sorted(mapping)} != {sorted(expected)}"
        )


def _array(raw: Any, entity: str, item_type: type) -> list[Any]:
    if not isinstance(raw, list):
        raise PayloadDecodeError(
            f"{entity} must be a JSON array, got {type(raw).__name__}"
        )
    for position, item in enumerate(raw):
        if not isinstance(item, item_type):
            raise PayloadDecodeError(
                f"{entity}[{position}] must be a {item_type.__name__}, got "
                f"{type(item).__name__}"
            )
    return raw


def _member(enum_type: type[Enum], value: Any, entity: str) -> Any:
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
