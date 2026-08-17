"""Stop management as appended events — `AP` §9.3, built for the first time.

> *"Widening a stop under pressure is the most reliable predictor of an outsized
> loss, and it is invisible to any model that lets a plan be edited in place."*

`fmis.plan` shipped with `PlanAmendment` deliberately unbuilt and said so:
*"nothing in this milestone amends a plan, and a record type nobody writes is
weight without value."* This milestone writes them, and writes exactly one field's
worth — the **stop** — because that is the field with a behavioural metric
attached (`AP` §20.5, *"stop integrity … the highest-value single behavioural
metric"*). A record type able to move targets, size and expiry with nothing
writing three of those four would be the same weight without value, one milestone
later. Widening it is additive.

**`TradePlan.initial_invalidation` is never touched, by construction.** There is
no code path in this repository that changes it — not a rule, an absence. What
moves is the *effective* stop, and the effective stop is the fold of this stream
over that immutable origin. R-multiple, stop integrity and every discipline
metric key on the origin, and they stay correct for exactly that reason.

**The chain is validated, not trusted.** Every amendment states the stop it
moved *from*, and the fold refuses a stream where that does not match what the
previous amendment left. Two amendments both claiming to move the original stop
would give the effective stop two answers, and reporting either would be a guess.

**A rule this system applies may only ever tighten.** A `POLICY_DERIVED`
amendment that loosened the stop would be a widened stop with no owner behind
it — the exact behaviour the metric exists to catch, laundered into a policy. The
fold refuses one, so a store containing it is rejected at read time rather than
quietly measured.

**An amendment is keyed on the activation, not on the plan.** One commitment can
be activated more than once — the first cancelled, the second superseding it —
and a stop history keyed on the plan would fold two runs' amendments into one
answer. The plan still owns the origin every amendment is measured from; the
activation owns the run.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.money import canonical_decimal_text, parse_decimal
from fmis.provenance import Absent, ValueOrigin, VersionedTerm, decode_maybe, encode_maybe
from fmis.records import (
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
from fmis.snapshotting import TradeDirection
from fmis.trade_lifecycle.models import ActivationError, TradeLifecycleError

__all__ = [
    "STOP_AMENDMENT_SCHEMA_VERSION",
    "SUPPORTED_STOP_AMENDMENT_VERSIONS",
    "STOP_AMENDMENT_TYPE_SLUG",
    "STOP_AMENDMENT_KIND",
    "STOP_AMENDMENT_REASON_VOCABULARY",
    "STOP_POLICY_VOCABULARY",
    "SUGGESTED_AMENDMENT_REASONS",
    "BREAK_EVEN_TERM",
    "TRAILING_TERM",
    "AMENDABLE_ORIGINS",
    "StopAmendmentError",
    "StopAmendment",
    "StopMove",
    "StopHistory",
    "fold_stop_history",
]

STOP_AMENDMENT_SCHEMA_VERSION = 1
SUPPORTED_STOP_AMENDMENT_VERSIONS = frozenset({1})
STOP_AMENDMENT_TYPE_SLUG = "stop_amendment"
STOP_AMENDMENT_KIND = "stop_amendment"

#: The **owner's** vocabulary. This package defines no member of it and carries a
#: term id through verbatim, because membership is the owner's and `AP` §20.2's
#: rule is *retire and add, never redefine* — the identical footing
#: `fmis.trade_capture` holds for the exit-reason and setup-type vocabularies.
STOP_AMENDMENT_REASON_VOCABULARY = "stop_amendment_reason"

#: **This code path's** own vocabulary, and the distinction from the one above is
#: the same one `fmis.trade_capture.WRITE_REASON_VOCABULARY` draws: naming the two
#: rules this package implements is not this layer choosing a trading policy on
#: the owner's behalf, because the owner chose to enable them.
STOP_POLICY_VOCABULARY = "stop_policy"

#: The generation every term this package mints is stamped with.
_TAXONOMY_VERSION = 1

#: `AP` §9.3's six terms, offered to the owner as suggestions and **not
#: enforced**. §9.3 calls the vocabulary closed; §20.2 says membership is the
#: owner's and this repository's shipped precedent follows §20.2. Where the two
#: disagree the later rule and the running code win, so these are printed in the
#: CLI's help and never checked against a typed value.
SUGGESTED_AMENDMENT_REASONS: tuple[str, ...] = (
    "structure_changed",
    "volatility_expanded",
    "de_risking",
    "emotional",
    "error_correction",
    "thesis_invalidated",
)

BREAK_EVEN_TERM = VersionedTerm(
    vocabulary_id=STOP_POLICY_VOCABULARY,
    term_id="break_even",
    taxonomy_version=_TAXONOMY_VERSION,
)

TRAILING_TERM = VersionedTerm(
    vocabulary_id=STOP_POLICY_VOCABULARY,
    term_id="trailing",
    taxonomy_version=_TAXONOMY_VERSION,
)

#: The only two origins an amendment may claim. `MEASURED` is absent because a
#: stop is not measured from anything — it is either the owner's assertion or a
#: policy's output. `INTERPRETED` is absent because **no model may move a stop**,
#: and there is no configuration under which that changes.
AMENDABLE_ORIGINS: frozenset[ValueOrigin] = frozenset(
    {ValueOrigin.ASSERTED, ValueOrigin.POLICY_DERIVED}
)


class StopAmendmentError(DomainValidationError, TradeLifecycleError):
    """An amendment whose fields cannot all be true at once."""


def _exact_price(value: Any, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if value <= 0:
        raise StopAmendmentError(f"{name} must be positive, got {value}")
    return Decimal(canonical_decimal_text(value))


@dataclass(frozen=True, slots=True)
class StopAmendment:
    """One recorded move of one trade's stop. Append-only; nothing is edited."""

    activation_id: str
    previous_stop: Decimal
    new_stop: Decimal
    reason: VersionedTerm
    origin: ValueOrigin
    author: str
    occurred_at: datetime
    recorded_at: datetime
    audit: RecordAudit
    policy_id: str | Absent = field(
        default_factory=lambda: Absent("the owner moved this stop themselves")
    )
    policy_version: int | Absent = field(
        default_factory=lambda: Absent("the owner moved this stop themselves")
    )
    causing_close_time: datetime | Absent = field(
        default_factory=lambda: Absent("no candle caused this amendment")
    )
    note: str | Absent = field(default_factory=lambda: Absent("no note"))
    supersedes: str | Absent = field(
        default_factory=lambda: Absent("supersedes nothing")
    )
    schema_version: int = STOP_AMENDMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_domain_record_id(self.activation_id)
        object.__setattr__(
            self, "previous_stop", _exact_price(self.previous_stop, "previous_stop")
        )
        object.__setattr__(self, "new_stop", _exact_price(self.new_stop, "new_stop"))
        if self.new_stop == self.previous_stop:
            raise StopAmendmentError(
                f"the stop is already {canonical_decimal_text(self.new_stop)}; an "
                "amendment that changes nothing is a row in the discipline metric "
                "that did not happen"
            )
        if not isinstance(self.reason, VersionedTerm):
            raise TypeError(
                "reason must be a VersionedTerm; an untagged stop move cannot be "
                "counted, and counting them is the whole point of the record"
            )
        require_member(self.origin, ValueOrigin, "origin")
        if self.origin not in AMENDABLE_ORIGINS:
            raise StopAmendmentError(
                f"a stop amendment is {sorted(o.value for o in AMENDABLE_ORIGINS)}, "
                f"never {self.origin.value}. A measurement does not move a stop, "
                "and no model may"
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
                "recorded_at precedes occurred_at on a stop amendment"
            )
        require_unmodified(self.audit, "StopAmendment")
        if not isinstance(self.causing_close_time, Absent):
            object.__setattr__(
                self,
                "causing_close_time",
                require_utc(self.causing_close_time, "causing_close_time"),
            )
        for name in ("note",):
            value = getattr(self, name)
            if not isinstance(value, Absent):
                object.__setattr__(self, name, require_text(value, name))
        if not isinstance(self.supersedes, Absent):
            validate_domain_record_id(self.supersedes)
        if self.schema_version not in SUPPORTED_STOP_AMENDMENT_VERSIONS:
            raise DomainValidationError(
                f"stop amendment schema_version {self.schema_version} is not one "
                f"this build writes ({sorted(SUPPORTED_STOP_AMENDMENT_VERSIONS)})"
            )
        self._validate_policy_fields()

    def _validate_policy_fields(self) -> None:
        """A policy's output names the policy; an assertion must not pretend to.

        The pair is required together and refused together. A `POLICY_DERIVED`
        amendment with no version could not be re-read against the rule that
        produced it, which is the entire difference between `POLICY_DERIVED` and
        `ASSERTED`; and an `ASSERTED` one carrying a policy version would claim a
        provenance the owner's own judgement does not have.
        """
        stated = not isinstance(self.policy_id, Absent)
        versioned = not isinstance(self.policy_version, Absent)
        if stated != versioned:
            raise StopAmendmentError(
                "policy_id and policy_version are stated together or not at all; "
                "a policy nobody can version is one nobody can re-read"
            )
        if self.origin is ValueOrigin.POLICY_DERIVED:
            if not stated:
                raise StopAmendmentError(
                    "a POLICY_DERIVED amendment names the policy and its version. "
                    "Without them the record says a rule moved the stop and not "
                    "which rule, and a later change to that rule becomes invisible"
                )
            if isinstance(self.causing_close_time, Absent):
                raise StopAmendmentError(
                    "a POLICY_DERIVED amendment is produced from a closed candle "
                    "and must carry that candle's close time; the stop history is "
                    "ordered by it, not by when the simulator happened to run"
                )
            object.__setattr__(
                self, "policy_id", require_text(self.policy_id, "policy_id")
            )
            require_int(self.policy_version, "policy_version", minimum=1)
        elif stated:
            raise StopAmendmentError(
                "an ASSERTED amendment is the owner's own judgement and names no "
                "policy; a version on one would claim a provenance it does not have"
            )

    # -- projections ---------------------------------------------------------

    @property
    def is_owner_stated(self) -> bool:
        return self.origin is ValueOrigin.ASSERTED

    @property
    def ordering_key(self) -> datetime:
        if isinstance(self.causing_close_time, Absent):
            return self.occurred_at
        return self.causing_close_time

    def tightens(self, direction: TradeDirection) -> bool:
        """Whether the move brought the stop **towards** the entry.

        Takes the direction rather than storing it: the activation already holds
        the side, and a second copy here would be the field that eventually
        disagrees with it.
        """
        return direction.sign * (self.new_stop - self.previous_stop) > 0

    def widens(self, direction: TradeDirection) -> bool:
        return not self.tightens(direction)

    # -- identity and serialization -----------------------------------------

    @property
    def digest_basis(self) -> dict[str, Any]:
        """The move itself. `recorded_at` and `author` are excluded.

        `recorded_at` for the reason every record in this domain excludes it. The
        `author` because the same move recorded twice — once by a crashed run and
        once by its retry — is one amendment, and the simulator and the owner
        never produce the same move at the same instant from the same stop with
        the same reason.
        """
        return {
            "schema_version": self.schema_version,
            "activation_id": self.activation_id,
            "previous_stop": canonical_decimal_text(self.previous_stop),
            "new_stop": canonical_decimal_text(self.new_stop),
            "reason": self.reason.to_payload(),
            "origin": self.origin.value,
            "occurred_at": encode_timestamp(self.occurred_at),
            "policy_id": encode_maybe(self.policy_id, str),
            "policy_version": encode_maybe(self.policy_version, int),
            "causing_close_time": encode_maybe(
                self.causing_close_time, encode_timestamp
            ),
            "note": encode_maybe(self.note, str),
            "supersedes": encode_maybe(self.supersedes, str),
        }

    @property
    def amendment_id(self) -> str:
        return build_domain_record_id(
            type_slug=STOP_AMENDMENT_TYPE_SLUG,
            subject=self.reason.term_id,
            moment=self.occurred_at,
            digest=content_digest_over(self.digest_basis),
        )

    @property
    def content_digest(self) -> str:
        return content_digest_over(self.digest_basis)

    def to_payload(self) -> dict[str, Any]:
        payload = self.digest_basis
        payload["amendment_id"] = self.amendment_id
        payload["recorded_at"] = encode_timestamp(self.recorded_at)
        payload["author"] = self.author
        payload["audit"] = self.audit.to_payload()
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> StopAmendment:
        mapping = require_mapping(raw, "stop amendment")
        version = require_payload_version(
            mapping,
            supported=SUPPORTED_STOP_AMENDMENT_VERSIONS,
            entity="stop amendment",
        )
        require_exact_keys(mapping, _AMENDMENT_KEYS, "stop amendment")
        try:
            origin = ValueOrigin(mapping["origin"])
        except ValueError as error:
            raise PayloadDecodeError(
                f"value origin {mapping['origin']!r} is not known to this build"
            ) from error
        decoded = cls(
            activation_id=str(mapping["activation_id"]),
            previous_stop=parse_decimal(mapping["previous_stop"], "previous_stop"),
            new_stop=parse_decimal(mapping["new_stop"], "new_stop"),
            reason=VersionedTerm.from_payload(mapping["reason"]),
            origin=origin,
            author=str(mapping["author"]),
            occurred_at=decode_timestamp(mapping["occurred_at"]),
            recorded_at=decode_timestamp(mapping["recorded_at"]),
            audit=RecordAudit.from_payload(mapping["audit"]),
            policy_id=decode_maybe(mapping["policy_id"], str),
            policy_version=decode_maybe(mapping["policy_version"], _as_int),
            causing_close_time=decode_maybe(
                mapping["causing_close_time"], decode_timestamp
            ),
            note=decode_maybe(mapping["note"], str),
            supersedes=decode_maybe(mapping["supersedes"], str),
            schema_version=version,
        )
        if mapping["amendment_id"] != decoded.amendment_id:
            raise PayloadDecodeError(
                f"amendment_id {mapping['amendment_id']!r} does not match the "
                f"digest of the move it claims to identify ({decoded.amendment_id!r})"
            )
        return decoded


_AMENDMENT_KEYS = frozenset({
    "schema_version",
    "amendment_id",
    "activation_id",
    "previous_stop",
    "new_stop",
    "reason",
    "origin",
    "author",
    "occurred_at",
    "recorded_at",
    "policy_id",
    "policy_version",
    "causing_close_time",
    "note",
    "supersedes",
    "audit",
})


def _as_int(raw: Any) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise PayloadDecodeError(f"expected an int, got {type(raw).__name__}")
    return raw


@dataclass(frozen=True, slots=True)
class StopMove:
    """One step of the folded history, with what it did to the stop."""

    amendment_id: str
    at: datetime
    previous_stop: Decimal
    new_stop: Decimal
    reason: VersionedTerm
    origin: ValueOrigin
    tightened: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "amendment_id", validate_domain_record_id(self.amendment_id)
        )
        object.__setattr__(self, "at", require_utc(self.at, "at"))
        for name in ("previous_stop", "new_stop"):
            object.__setattr__(self, name, _exact_price(getattr(self, name), name))
        if not isinstance(self.reason, VersionedTerm):
            raise TypeError("reason must be a VersionedTerm")
        require_member(self.origin, ValueOrigin, "origin")
        if not isinstance(self.tightened, bool):
            raise TypeError("tightened must be a bool")

    @property
    def arithmetic(self) -> str:
        """The move shown, not merely its result."""
        return (
            f"{canonical_decimal_text(self.previous_stop)} → "
            f"{canonical_decimal_text(self.new_stop)}"
        )


@dataclass(frozen=True, slots=True)
class StopHistory:
    """The immutable origin, every move since, and the stop in force now.

    A **projection**: delete it and recompute it from the plan and the amendment
    stream, and the answer is identical. Nothing here is stored.
    """

    initial: Decimal
    effective: Decimal
    moves: tuple[StopMove, ...] = ()

    def __post_init__(self) -> None:
        for name in ("initial", "effective"):
            object.__setattr__(self, name, _exact_price(getattr(self, name), name))
        require_tuple_of(self.moves, StopMove, "moves")
        if not self.moves and self.effective != self.initial:
            raise DomainValidationError(
                "a history with no move cannot have an effective stop that differs "
                "from the initial one"
            )
        if self.moves and self.moves[-1].new_stop != self.effective:
            raise DomainValidationError(
                "the effective stop must be what the last move left; a third value "
                "would be a stop nobody set"
            )

    @property
    def has_moved(self) -> bool:
        return bool(self.moves)

    @property
    def widening_count(self) -> int:
        """`AP` §20.5's stop-integrity counter, and the reason this fold exists."""
        return sum(1 for move in self.moves if not move.tightened)

    @property
    def tightening_count(self) -> int:
        return sum(1 for move in self.moves if move.tightened)

    @property
    def owner_move_count(self) -> int:
        return sum(1 for move in self.moves if move.origin is ValueOrigin.ASSERTED)

    @property
    def honours_initial(self) -> bool:
        """Whether the stop in force is still no looser than the one committed to.

        Not *"unchanged"*: a stop tightened to break-even honours the commitment
        completely, and counting it as a departure would make the metric read as
        indiscipline every time the owner did the right thing.
        """
        return self.widening_count == 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "initial": canonical_decimal_text(self.initial),
            "effective": canonical_decimal_text(self.effective),
            "moves": [
                {
                    "amendment_id": move.amendment_id,
                    "at": encode_timestamp(move.at),
                    "previous_stop": canonical_decimal_text(move.previous_stop),
                    "new_stop": canonical_decimal_text(move.new_stop),
                    "reason": move.reason.to_payload(),
                    "origin": move.origin.value,
                    "tightened": move.tightened,
                }
                for move in self.moves
            ],
        }


def fold_stop_history(
    *,
    initial_stop: Decimal,
    direction: TradeDirection,
    amendments: Iterable[StopAmendment],
    at: datetime | None = None,
) -> StopHistory:
    """Fold the amendment stream over the plan's immutable invalidation.

    `at` bounds the fold to what was known at an instant, so a monitoring reading
    taken while replaying history uses the stop that was in force **then** rather
    than the one in force now. Passing `None` folds everything.

    Raises when the chain does not join, and when a `POLICY_DERIVED` amendment
    widens. Both are refusals rather than repairs: a stop history that silently
    skipped a link would report an effective stop no record supports.
    """
    origin_stop = _exact_price(initial_stop, "initial_stop")
    require_member(direction, TradeDirection, "direction")
    if not direction.is_directional:
        raise ActivationError(
            "a stop history needs a side to tell tightening from widening, and a "
            "decision not to act has none"
        )
    boundary = None if at is None else require_utc(at, "at")
    materialized = tuple(amendments)
    require_tuple_of(materialized, StopAmendment, "amendments")
    superseded = {
        amendment.supersedes
        for amendment in materialized
        if not isinstance(amendment.supersedes, Absent)
    }
    live = [
        amendment
        for amendment in materialized
        if amendment.amendment_id not in superseded
        and (boundary is None or amendment.ordering_key <= boundary)
    ]
    ordered = sorted(live, key=lambda amendment: (amendment.ordering_key, amendment.amendment_id))

    effective = origin_stop
    moves: list[StopMove] = []
    for amendment in ordered:
        if amendment.previous_stop != effective:
            raise StopAmendmentError(
                f"amendment {amendment.amendment_id} moves the stop from "
                f"{canonical_decimal_text(amendment.previous_stop)}, but the stop "
                f"in force was {canonical_decimal_text(effective)}. The chain does "
                "not join, and an effective stop folded across the gap would be a "
                "value no record supports"
            )
        tightened = amendment.tightens(direction)
        if not tightened and amendment.origin is ValueOrigin.POLICY_DERIVED:
            raise StopAmendmentError(
                f"amendment {amendment.amendment_id} is POLICY_DERIVED and widens "
                f"the stop from {canonical_decimal_text(amendment.previous_stop)} "
                f"to {canonical_decimal_text(amendment.new_stop)}. A rule this "
                "system applies may only tighten; widening is the owner's own act "
                "and is recorded as their assertion, with their reason"
            )
        moves.append(
            StopMove(
                amendment_id=amendment.amendment_id,
                at=amendment.ordering_key,
                previous_stop=amendment.previous_stop,
                new_stop=amendment.new_stop,
                reason=amendment.reason,
                origin=amendment.origin,
                tightened=tightened,
            )
        )
        effective = amendment.new_stop
    return StopHistory(initial=origin_stop, effective=effective, moves=tuple(moves))
