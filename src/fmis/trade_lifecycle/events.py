"""The lifecycle stream, and the fold that is the only place a state exists.

**No state is stored anywhere.** A `TradeLifecycleEvent` is appended, never
edited; a wrong one is superseded by a later event carrying `supersedes`, the
identical mechanism the ledger uses for a `Correction` and the proposal stream
uses for its own events. `fold_trade_lifecycle` replays what is left and returns
the state it reaches. Deleting every folded state and recomputing must produce the
identical answer, which is the test the durability classification rests on.

**Why not reuse `ProposalLifecycleEvent`.** Its states describe a *suggestion* —
was it decided, did it lapse, was it entered after it had already become invalid.
These describe a *commitment with money behind it* — is the entry still waiting,
has one rung of the ladder filled, is exposure flat. `AP` §7 is explicit that
Proposal, Plan, Order, Trade and Position are five objects because each occurs
without the next, and collapsing two of their lifecycles into one enum would lose
exactly the behaviours §7's table names. The **mechanism** is reused; the
vocabulary is not.

**`TRIGGERED` and `OPEN` are two states.** *The condition was met* and *the fill
happened* are different facts — under a `MARKET` entry they are a bar apart — and
merging them makes the delay between them unmeasurable. This is the same split
§8.4 already draws between `ENTRY_TRIGGERED` and `EXECUTED`.

**`PARTIALLY_EXITED` is a state here and deliberately is not one on `Position`.**
The subject differs. A position is a fold over fills, where a partial exit changes
the numbers without changing what the position *is*; an activation is an
instruction, and *"two of the three rungs have filled"* is genuinely its state —
it decides which rungs the next bar may still fill.

**Two events caused by one candle are ordered by geometry, never by guess.**
`bar_sequence` carries the order the *engine derived*: a nearer ladder rung is
passed before a further one, and a fill cannot precede the trigger that caused it.
Neither is an observation about intrabar price path. The one case that **is** an
observation about the path — a bar that reaches both the stop and a target — is
refused upstream as `AMBIGUOUS_BAR` and never reaches this fold as two events, so
nothing here ever has to arbitrate ADR-0021's question.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any

from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.provenance import Absent, ValueOrigin, VersionedTerm, decode_maybe, encode_maybe
from fmis.records import (
    DomainStateError,
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
from fmis.trade_lifecycle.models import TradeLifecycleError

__all__ = [
    "TRADE_LIFECYCLE_EVENT_SCHEMA_VERSION",
    "SUPPORTED_TRADE_LIFECYCLE_EVENT_VERSIONS",
    "TRADE_LIFECYCLE_EVENT_TYPE_SLUG",
    "TRADE_LIFECYCLE_EVENT_KIND",
    "IllegalLifecycleTransitionError",
    "TradeLifecycleKind",
    "LIFECYCLE_KIND_ORIGINS",
    "MEASURED_LIFECYCLE_KINDS",
    "CAUSAL_RANK",
    "TradeLifecycleState",
    "TERMINAL_LIFECYCLE_STATES",
    "LIVE_LIFECYCLE_STATES",
    "LIFECYCLE_TRANSITIONS",
    "TradeLifecycleEvent",
    "TradeLifecycleView",
    "fold_trade_lifecycle",
]

TRADE_LIFECYCLE_EVENT_SCHEMA_VERSION = 1
SUPPORTED_TRADE_LIFECYCLE_EVENT_VERSIONS = frozenset({1})
TRADE_LIFECYCLE_EVENT_TYPE_SLUG = "lifecycle_step"
TRADE_LIFECYCLE_EVENT_KIND = "lifecycle_step"


class IllegalLifecycleTransitionError(DomainStateError, TradeLifecycleError):
    """An event that cannot follow the state the stream had reached.

    Never a silent no-op and never a best guess at what the caller meant. The
    brief's requirement — *"illegal transitions must raise"* — is this class and
    the table below, and nothing else in the package may decide a state.
    """


class TradeLifecycleKind(Enum):
    """One thing that happened to an activated commitment. A closed set.

    A new kind is an enum extension and therefore a capture-schema version bump,
    with an unknown member a clean rejection.
    """

    ENTRY_TRIGGERED = "entry_triggered"
    ENTRY_FILLED = "entry_filled"
    STOP_AMENDED = "stop_amended"
    PARTIAL_EXIT_FILLED = "partial_exit_filled"
    EXIT_FILLED = "exit_filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    AMBIGUOUS_BAR = "ambiguous_bar"
    OUTCOME_RECORDED = "outcome_recorded"


#: Fixed per kind and **not** a free choice a caller may set.
#:
#: `STOP_AMENDED` is the one kind whose origin is not fixed here, because it is
#: genuinely two facts: the owner moving their own stop is `ASSERTED` and can be
#: wrong; the simulator applying a break-even or trailing rule the owner stated is
#: `POLICY_DERIVED` and is wrong only if the policy is. The `StopAmendment` the
#: event references carries which, and this table therefore holds `ABSENT` for it
#: rather than a plausible single answer.
LIFECYCLE_KIND_ORIGINS: Mapping[TradeLifecycleKind, ValueOrigin] = MappingProxyType(
    {
        TradeLifecycleKind.ENTRY_TRIGGERED: ValueOrigin.MEASURED,
        TradeLifecycleKind.ENTRY_FILLED: ValueOrigin.MEASURED,
        TradeLifecycleKind.STOP_AMENDED: ValueOrigin.ABSENT,
        TradeLifecycleKind.PARTIAL_EXIT_FILLED: ValueOrigin.MEASURED,
        TradeLifecycleKind.EXIT_FILLED: ValueOrigin.MEASURED,
        TradeLifecycleKind.CANCELLED: ValueOrigin.ASSERTED,
        TradeLifecycleKind.EXPIRED: ValueOrigin.MEASURED,
        TradeLifecycleKind.SUPERSEDED: ValueOrigin.ASSERTED,
        TradeLifecycleKind.AMBIGUOUS_BAR: ValueOrigin.MEASURED,
        TradeLifecycleKind.OUTCOME_RECORDED: ValueOrigin.MEASURED,
    }
)

#: Every kind caused by a closed candle, and therefore every kind that must carry
#: the close time the stream is ordered by. `EXIT_FILLED` is **not** in this set:
#: the same kind records both a simulated exit and the owner's own manual close,
#: and requiring a causing candle would make the second unrepresentable.
MEASURED_LIFECYCLE_KINDS: frozenset[TradeLifecycleKind] = frozenset(
    {
        TradeLifecycleKind.ENTRY_TRIGGERED,
        TradeLifecycleKind.ENTRY_FILLED,
        TradeLifecycleKind.AMBIGUOUS_BAR,
    }
)

#: The order two events caused by **one** candle are applied in.
#:
#: Every pair below is ordered by the state machine's own shape or by the
#: geometry of the levels — a fill cannot precede the trigger that caused it, and
#: a stop cannot be amended before the entry that created the exposure. **No pair
#: here is ordered by an assumption about the intrabar price path**; the one pair
#: that would be is refused as `AMBIGUOUS_BAR` before it ever becomes two events.
CAUSAL_RANK: Mapping[TradeLifecycleKind, int] = MappingProxyType(
    {
        TradeLifecycleKind.EXPIRED: 0,
        TradeLifecycleKind.SUPERSEDED: 1,
        TradeLifecycleKind.CANCELLED: 2,
        TradeLifecycleKind.ENTRY_TRIGGERED: 3,
        TradeLifecycleKind.ENTRY_FILLED: 4,
        TradeLifecycleKind.STOP_AMENDED: 5,
        TradeLifecycleKind.PARTIAL_EXIT_FILLED: 6,
        TradeLifecycleKind.EXIT_FILLED: 7,
        TradeLifecycleKind.AMBIGUOUS_BAR: 8,
        TradeLifecycleKind.OUTCOME_RECORDED: 9,
    }
)


class TradeLifecycleState(Enum):
    """The fold of the stream — **never stored, always derived**.

    `PROPOSED` is absent, and its absence is the design. A suggestion's states
    already exist as `fmis.proposal.ProposalState`, and duplicating one of them
    here would give *"was this proposed"* two answers. `fmis.paper.compose` joins
    the two streams instead, so `PROPOSED → PENDING → TRIGGERED → OPEN` is one
    chain across two objects rather than one enum pretending to be both.
    """

    PENDING = "pending"
    TRIGGERED = "triggered"
    OPEN = "open"
    PARTIALLY_EXITED = "partially_exited"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    AMBIGUOUS = "ambiguous"
    RESOLVED = "resolved"


#: `RESOLVED` is the only terminal state, and it is itself an event: an outcome
#: was computed and frozen. Nothing follows it.
TERMINAL_LIFECYCLE_STATES: frozenset[TradeLifecycleState] = frozenset(
    {TradeLifecycleState.RESOLVED}
)

#: The states a simulation run still has work to do in. `AMBIGUOUS` is **not**
#: among them: it is a halt, and advancing it would require inventing the
#: intrabar order this system refuses to invent.
LIVE_LIFECYCLE_STATES: frozenset[TradeLifecycleState] = frozenset(
    {
        TradeLifecycleState.PENDING,
        TradeLifecycleState.TRIGGERED,
        TradeLifecycleState.OPEN,
        TradeLifecycleState.PARTIALLY_EXITED,
    }
)


def _row(**kinds: TradeLifecycleState) -> Mapping[TradeLifecycleKind, TradeLifecycleState]:
    return MappingProxyType(
        {TradeLifecycleKind[name]: state for name, state in kinds.items()}
    )


#: The whole legal machine, in one table. An event whose kind is absent from the
#: current state's row raises.
LIFECYCLE_TRANSITIONS: Mapping[
    TradeLifecycleState, Mapping[TradeLifecycleKind, TradeLifecycleState]
] = MappingProxyType(
    {
        # `STOP_AMENDED` is legal before a fill: the owner adjusting the
        # invalidation while an entry is still waiting is an ordinary act, and
        # the stop that results is the one the engine will size the trade's risk
        # against when it does fill.
        TradeLifecycleState.PENDING: _row(
            STOP_AMENDED=TradeLifecycleState.PENDING,
            ENTRY_TRIGGERED=TradeLifecycleState.TRIGGERED,
            EXPIRED=TradeLifecycleState.EXPIRED,
            CANCELLED=TradeLifecycleState.CANCELLED,
            SUPERSEDED=TradeLifecycleState.SUPERSEDED,
            AMBIGUOUS_BAR=TradeLifecycleState.AMBIGUOUS,
        ),
        TradeLifecycleState.TRIGGERED: _row(
            STOP_AMENDED=TradeLifecycleState.TRIGGERED,
            ENTRY_FILLED=TradeLifecycleState.OPEN,
            EXPIRED=TradeLifecycleState.EXPIRED,
            CANCELLED=TradeLifecycleState.CANCELLED,
            SUPERSEDED=TradeLifecycleState.SUPERSEDED,
            AMBIGUOUS_BAR=TradeLifecycleState.AMBIGUOUS,
        ),
        TradeLifecycleState.OPEN: _row(
            STOP_AMENDED=TradeLifecycleState.OPEN,
            PARTIAL_EXIT_FILLED=TradeLifecycleState.PARTIALLY_EXITED,
            EXIT_FILLED=TradeLifecycleState.CLOSED,
            AMBIGUOUS_BAR=TradeLifecycleState.AMBIGUOUS,
        ),
        TradeLifecycleState.PARTIALLY_EXITED: _row(
            STOP_AMENDED=TradeLifecycleState.PARTIALLY_EXITED,
            PARTIAL_EXIT_FILLED=TradeLifecycleState.PARTIALLY_EXITED,
            EXIT_FILLED=TradeLifecycleState.CLOSED,
            AMBIGUOUS_BAR=TradeLifecycleState.AMBIGUOUS,
        ),
        # A halt, not an end. The owner resolves it through the path that already
        # exists — recording the exit they judge they would have taken — and that
        # exit is `ASSERTED` beside `MEASURED` fills, which is exactly the
        # distinction `ValueOrigin` exists to carry.
        TradeLifecycleState.AMBIGUOUS: _row(
            EXIT_FILLED=TradeLifecycleState.CLOSED,
            CANCELLED=TradeLifecycleState.CANCELLED,
        ),
        TradeLifecycleState.CLOSED: _row(
            OUTCOME_RECORDED=TradeLifecycleState.RESOLVED
        ),
        TradeLifecycleState.CANCELLED: _row(
            OUTCOME_RECORDED=TradeLifecycleState.RESOLVED
        ),
        TradeLifecycleState.EXPIRED: _row(
            OUTCOME_RECORDED=TradeLifecycleState.RESOLVED
        ),
        TradeLifecycleState.SUPERSEDED: _row(
            OUTCOME_RECORDED=TradeLifecycleState.RESOLVED
        ),
        TradeLifecycleState.RESOLVED: MappingProxyType({}),
    }
)


@dataclass(frozen=True, slots=True)
class TradeLifecycleEvent:
    """One thing that happened to an activation. Append-only, immutable.

    **It carries no price and no quantity.** A fill's numbers live on the `Trade`
    the ledger holds, and this event names it through `reference`. *"If two fields
    could ever disagree about the same fact, one of them is not a field"* — and a
    lifecycle event holding its own copy of a fill price is the pair that would
    eventually disagree with a `Correction`.
    """

    activation_id: str
    kind: TradeLifecycleKind
    occurred_at: datetime
    recorded_at: datetime
    audit: RecordAudit
    causing_close_time: datetime | Absent = field(
        default_factory=lambda: Absent("no candle caused this event")
    )
    reason: VersionedTerm | Absent = field(
        default_factory=lambda: Absent("this kind carries no reason tag")
    )
    reference: str | Absent = field(default_factory=lambda: Absent("no reference"))
    note: str | Absent = field(default_factory=lambda: Absent("no note"))
    bar_sequence: int = 0
    supersedes: str | Absent = field(
        default_factory=lambda: Absent("supersedes nothing")
    )
    schema_version: int = TRADE_LIFECYCLE_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_domain_record_id(self.activation_id)
        require_member(self.kind, TradeLifecycleKind, "kind")
        object.__setattr__(
            self, "occurred_at", require_utc(self.occurred_at, "occurred_at")
        )
        object.__setattr__(
            self, "recorded_at", require_utc(self.recorded_at, "recorded_at")
        )
        if self.recorded_at < self.occurred_at:
            raise DomainValidationError(
                f"recorded_at {self.recorded_at.isoformat()} precedes occurred_at "
                f"{self.occurred_at.isoformat()}; FMITS cannot learn of something "
                "before it happened"
            )
        require_unmodified(self.audit, "TradeLifecycleEvent")
        if not isinstance(self.causing_close_time, Absent):
            object.__setattr__(
                self,
                "causing_close_time",
                require_utc(self.causing_close_time, "causing_close_time"),
            )
        if not isinstance(self.reason, (VersionedTerm, Absent)):
            raise TypeError("reason must be a VersionedTerm or Absent")
        for name in ("reference", "note"):
            value = getattr(self, name)
            if not isinstance(value, Absent):
                object.__setattr__(self, name, require_text(value, name))
        require_int(self.bar_sequence, "bar_sequence", minimum=0)
        if not isinstance(self.supersedes, Absent):
            validate_domain_record_id(self.supersedes)
        if self.schema_version not in SUPPORTED_TRADE_LIFECYCLE_EVENT_VERSIONS:
            raise DomainValidationError(
                f"lifecycle step schema_version {self.schema_version} is not one "
                f"this build writes "
                f"({sorted(SUPPORTED_TRADE_LIFECYCLE_EVENT_VERSIONS)})"
            )
        self._validate_kind_rules()

    def _validate_kind_rules(self) -> None:
        caused_by_candle = not isinstance(self.causing_close_time, Absent)
        if self.kind in MEASURED_LIFECYCLE_KINDS and not caused_by_candle:
            raise DomainValidationError(
                f"{self.kind.value} is caused by a closed candle and must carry "
                "that candle's close time. The stream is ordered by it, not by "
                "scan time — ordering by scan time recreates ADR-0021's "
                "intrabar-order problem one layer up"
            )
        if self.kind is TradeLifecycleKind.CANCELLED and isinstance(
            self.reason, Absent
        ):
            raise DomainValidationError(
                "CANCELLED requires a reason tag from the owner's own vocabulary. "
                "A cancellation nobody gave a reason for is a row nobody can learn "
                "from, which is the identical demand OWNER_DECIDED already makes"
            )
        if self.kind is TradeLifecycleKind.AMBIGUOUS_BAR and isinstance(
            self.note, Absent
        ):
            raise DomainValidationError(
                "AMBIGUOUS_BAR halts a trade and must say what could not be "
                "ordered. A halt with no statement of what caused it is one the "
                "owner cannot resolve"
            )
        if self.kind is TradeLifecycleKind.SUPERSEDED and isinstance(
            self.reference, Absent
        ):
            raise DomainValidationError(
                "SUPERSEDED names the activation that replaced this one; without "
                "it the stream records that something took over and not what"
            )
        if self.bar_sequence and not caused_by_candle:
            raise DomainValidationError(
                "bar_sequence orders two events inside one candle; an event with "
                "no causing candle has no position inside one"
            )

    # -- projections ---------------------------------------------------------

    @property
    def origin(self) -> ValueOrigin:
        """Fixed by kind, and `ABSENT` for the one kind that is genuinely two."""
        return LIFECYCLE_KIND_ORIGINS[self.kind]

    @property
    def ordering_key(self) -> datetime:
        """The instant the stream is ordered by.

        The causing candle's close where there is one, and the moment it occurred
        for an assertion. A simulation run that happens late records a *later*
        `recorded_at` and the *same* ordering key, which is the whole point.
        """
        if isinstance(self.causing_close_time, Absent):
            return self.occurred_at
        return self.causing_close_time

    @property
    def sort_key(self) -> tuple[datetime, int, int]:
        """`(when, position inside the bar, causal rank)` — the fold's own order."""
        return (self.ordering_key, self.bar_sequence, CAUSAL_RANK[self.kind])

    # -- identity and serialization -----------------------------------------

    @property
    def digest_basis(self) -> dict[str, Any]:
        """The event itself. `recorded_at` is excluded.

        Following ADR-0027 §3's precedent for `archived_at` and the ledger's for
        its own `recorded_at`: whether a re-run of the simulator recognises an
        event as already recorded must not depend on when the run happened. Replay
        the same bars twice and the second run publishes nothing.
        """
        return {
            "schema_version": self.schema_version,
            "activation_id": self.activation_id,
            "kind": self.kind.value,
            "occurred_at": encode_timestamp(self.occurred_at),
            "causing_close_time": encode_maybe(
                self.causing_close_time, encode_timestamp
            ),
            "reason": encode_maybe(self.reason, VersionedTerm.to_payload),
            "reference": encode_maybe(self.reference, str),
            "note": encode_maybe(self.note, str),
            "bar_sequence": self.bar_sequence,
            "supersedes": encode_maybe(self.supersedes, str),
        }

    @property
    def event_id(self) -> str:
        return build_domain_record_id(
            type_slug=TRADE_LIFECYCLE_EVENT_TYPE_SLUG,
            subject=self.kind.value,
            moment=self.occurred_at,
            digest=content_digest_over(self.digest_basis),
        )

    @property
    def content_digest(self) -> str:
        return content_digest_over(self.digest_basis)

    def to_payload(self) -> dict[str, Any]:
        payload = self.digest_basis
        payload["event_id"] = self.event_id
        payload["recorded_at"] = encode_timestamp(self.recorded_at)
        payload["audit"] = self.audit.to_payload()
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> TradeLifecycleEvent:
        mapping = require_mapping(raw, "lifecycle step")
        version = require_payload_version(
            mapping,
            supported=SUPPORTED_TRADE_LIFECYCLE_EVENT_VERSIONS,
            entity="lifecycle step",
        )
        require_exact_keys(mapping, _EVENT_KEYS, "lifecycle step")
        try:
            kind = TradeLifecycleKind(mapping["kind"])
        except ValueError as error:
            raise PayloadDecodeError(
                f"lifecycle kind {mapping['kind']!r} is not known to this build; "
                "an unknown member is a clean rejection, never a default"
            ) from error
        decoded = cls(
            activation_id=str(mapping["activation_id"]),
            kind=kind,
            occurred_at=decode_timestamp(mapping["occurred_at"]),
            recorded_at=decode_timestamp(mapping["recorded_at"]),
            audit=RecordAudit.from_payload(mapping["audit"]),
            causing_close_time=decode_maybe(
                mapping["causing_close_time"], decode_timestamp
            ),
            reason=decode_maybe(mapping["reason"], VersionedTerm.from_payload),
            reference=decode_maybe(mapping["reference"], str),
            note=decode_maybe(mapping["note"], str),
            bar_sequence=require_int(
                mapping["bar_sequence"], "bar_sequence", minimum=0
            ),
            supersedes=decode_maybe(mapping["supersedes"], str),
            schema_version=version,
        )
        if mapping["event_id"] != decoded.event_id:
            raise PayloadDecodeError(
                f"event_id {mapping['event_id']!r} does not match the digest of "
                f"the event it claims to identify ({decoded.event_id!r})"
            )
        return decoded


_EVENT_KEYS = frozenset({
    "schema_version",
    "event_id",
    "activation_id",
    "kind",
    "occurred_at",
    "recorded_at",
    "causing_close_time",
    "reason",
    "reference",
    "note",
    "bar_sequence",
    "supersedes",
    "audit",
})


@dataclass(frozen=True, slots=True)
class TradeLifecycleView:
    """The fold's result: a state, and the events that produced it."""

    state: TradeLifecycleState
    applied: tuple[str, ...] = ()
    last_event_at: datetime | Absent = field(
        default_factory=lambda: Absent("nothing has happened to this activation yet")
    )

    def __post_init__(self) -> None:
        require_member(self.state, TradeLifecycleState, "state")
        require_tuple_of(self.applied, str, "applied")
        if not isinstance(self.last_event_at, Absent):
            object.__setattr__(
                self, "last_event_at", require_utc(self.last_event_at, "last_event_at")
            )
        if self.applied and isinstance(self.last_event_at, Absent):
            raise DomainValidationError(
                "a view that applied events knows when the last one was"
            )
        if not self.applied and not isinstance(self.last_event_at, Absent):
            raise DomainValidationError(
                "a view that applied no event has no last event to be dated"
            )

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_LIFECYCLE_STATES

    @property
    def is_live(self) -> bool:
        """Whether a simulation run still has work to do on this activation."""
        return self.state in LIVE_LIFECYCLE_STATES

    @property
    def is_halted(self) -> bool:
        """Whether the engine stopped rather than finished. Never the same thing."""
        return self.state is TradeLifecycleState.AMBIGUOUS

    @property
    def has_exposure(self) -> bool:
        """Whether fills have opened a position that is not yet flat."""
        return self.state in {
            TradeLifecycleState.OPEN,
            TradeLifecycleState.PARTIALLY_EXITED,
        }

    def to_payload(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "applied": list(self.applied),
            "last_event_at": encode_maybe(self.last_event_at, encode_timestamp),
        }


def fold_trade_lifecycle(
    activation_id: str, events: Iterable[TradeLifecycleEvent]
) -> TradeLifecycleView:
    """Replay the stream and return the state it reaches.

    Pure: the same activation and the same events give the same answer, forever.
    Nothing is stored and nothing is cached.
    """
    wanted = validate_domain_record_id(activation_id)
    ordered = _order_events(wanted, events)
    state = TradeLifecycleState.PENDING
    applied: list[str] = []
    for event in ordered:
        state = _apply(state, event)
        applied.append(event.event_id)
    return TradeLifecycleView(
        state=state,
        applied=tuple(applied),
        last_event_at=(
            ordered[-1].ordering_key
            if ordered
            else Absent("nothing has happened to this activation yet")
        ),
    )


def _order_events(
    activation_id: str, events: Iterable[TradeLifecycleEvent]
) -> tuple[TradeLifecycleEvent, ...]:
    materialized = tuple(events)
    require_tuple_of(materialized, TradeLifecycleEvent, "events")
    for event in materialized:
        if event.activation_id != activation_id:
            raise DomainValidationError(
                f"event {event.event_id} belongs to activation "
                f"{event.activation_id}, not to {activation_id}"
            )
    superseded = {
        event.supersedes
        for event in materialized
        if not isinstance(event.supersedes, Absent)
    }
    live = [event for event in materialized if event.event_id not in superseded]
    ordered = tuple(sorted(live, key=lambda event: event.sort_key))
    _require_orderable(ordered)
    return ordered


def _require_orderable(ordered: tuple[TradeLifecycleEvent, ...]) -> None:
    """Two events the fold cannot tell apart in time are a refusal.

    Equal `(when, bar_sequence, causal rank)` means nothing in the record decides
    which happened first, and applying them in whatever order the sort happened to
    produce would present an arbitrary sequence as a real one — exactly the
    corruption AP-D4a names for the proposal stream. Refusing here is cheaper than
    discovering it in a behavioural metric three years later.
    """
    for previous, current in zip(ordered, ordered[1:]):
        if previous.sort_key != current.sort_key:
            continue
        raise DomainValidationError(
            f"{previous.kind.value} ({previous.event_id}) and "
            f"{current.kind.value} ({current.event_id}) share an ordering key at "
            f"{previous.ordering_key.isoformat()} and cannot be ordered against "
            "each other. Nothing recorded decides which happened first, and "
            "ordering them by anything else would invent a sequence"
        )


def _apply(
    state: TradeLifecycleState, event: TradeLifecycleEvent
) -> TradeLifecycleState:
    allowed = LIFECYCLE_TRANSITIONS[state]
    if event.kind not in allowed:
        raise IllegalLifecycleTransitionError(
            f"{event.kind.value} cannot follow state {state.value}. Legal here: "
            f"{sorted(kind.value for kind in allowed) or ['(terminal — nothing)']}"
        )
    return allowed[event.kind]
