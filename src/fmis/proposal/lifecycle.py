"""The proposal lifecycle stream — the brief's *Decision*, and why it is not one object.

The brief asks for a `Decision` entity. The data model's answer is that **there is
no single decision object**, and the reason is the same one `AP` §8.3 gave when it
refused a single `ProposalDecision` enum: the things a person calls "a decision"
have three different authors and three different truth conditions.

* `OWNER_DECIDED` — the owner accepted or rejected, with a required reason tag.
  `ASSERTED`, and it can simply be wrong.
* Every `ENTRY_TRIGGERED` / `INVALIDATION_REACHED` / `EXPIRED_*` / `EXECUTED*` /
  `REAFFIRMED` / `RESOLVED` — the *market* decided, on a closed candle.
  `MEASURED`, and it cannot be wrong; only its inputs can.
* `WITHDRAWN_BY_AUTHOR` — the proposing policy or model cancelled it. `ASSERTED`.

So a decision is an **event in an append-only stream whose fold is the proposal's
state**. No state is stored anywhere. That is what keeps four measurable
behaviours alive: a proposal rejected has no position, a position exists with no
proposal, a setup cycles without anything being decided, and a fill can land
*after* the proposal was already invalid — which is `EXECUTED_WHILE_INVALID`, a
first-class bias metric.

**Ordering is by causing candle close, never by scan time.** AP-D4a shows that a
coarse scan cadence recreates ADR-0021's intrabar-order problem one layer up: a
scan that first runs after both the entry trigger and the invalidation have
occurred could record them in an order that did not happen, corrupting the
`EXECUTED_WHILE_INVALID` classification. Two kinds caused by the *same* candle are
marked `same_bar` and are **never ordered against each other** — the fold reports
the ambiguity, exactly as ADR-0021 refuses to guess a two-sided break bar and as
`AV`'s shipped `AMBIGUOUS_SAME_BAR` outcome already implements.

**No model may ever author an event here.** This is the sharpest single instance
of the rule that AI never writes to a source of truth: a model that could record
that the owner decided something, or that a market fact occurred, would be
authoring the highest-value dataset in the system.
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
    require_mapping,
    require_member,
    require_payload_version,
    require_text,
    require_tuple_of,
    require_unmodified,
    require_utc,
    validate_domain_record_id,
)
from fmis.proposal.models import OpportunityProposal, ProposalError
from fmis.proposal.setup_identity import anchors_match
from fmis.snapshotting import Anchor

__all__ = [
    "LIFECYCLE_EVENT_SCHEMA_VERSION",
    "SUPPORTED_LIFECYCLE_EVENT_VERSIONS",
    "LIFECYCLE_EVENT_TYPE_SLUG",
    "LifecycleKind",
    "KIND_ORIGINS",
    "MEASURED_KINDS",
    "ProposalState",
    "TERMINAL_STATES",
    "TRANSITIONS",
    "ProposalLifecycleEvent",
    "ProposalStateView",
    "IllegalTransitionError",
    "fold_proposal_state",
    "AdmissionOutcome",
    "ProposalAdmission",
    "admit",
]

LIFECYCLE_EVENT_SCHEMA_VERSION = 1
SUPPORTED_LIFECYCLE_EVENT_VERSIONS = frozenset({1})
LIFECYCLE_EVENT_TYPE_SLUG = "lifecycle_event"


class IllegalTransitionError(DomainStateError, ProposalError):
    """An event that cannot follow the state the stream had reached.

    Both a `DomainStateError` and a `ProposalError`, so a caller can catch
    "illegal transition anywhere in the domain" or "anything wrong with a
    proposal" and neither `except` is a lie.
    """


class LifecycleKind(Enum):
    """One thing that happened to a proposal.

    A closed set. **A new kind is an enum extension and therefore a capture-schema
    version bump**, with an unknown member a clean rejection.

    `EXPIRED_UNDECIDED` and `EXPIRED_UNTRIGGERED` are two kinds and not one, and
    the split carries the most information of any decision here: the first is an
    *engagement* measure (the owner never decided), the second a *policy quality*
    measure (the setup never triggered). Merging them makes both unmeasurable.

    `EXPIRED_UNDECIDED` observes **the absence of a decision, never whether the
    owner looked** — the system cannot know the second, and asserting it would be
    the same dishonesty as inferring a trading session from timestamps.
    """

    OWNER_DECIDED = "owner_decided"
    WITHDRAWN_BY_AUTHOR = "withdrawn_by_author"
    REAFFIRMED = "reaffirmed"
    ENTRY_TRIGGERED = "entry_triggered"
    INVALIDATION_REACHED = "invalidation_reached"
    EXPIRED_UNTRIGGERED = "expired_untriggered"
    EXPIRED_UNDECIDED = "expired_undecided"
    EXECUTED = "executed"
    EXECUTED_WHILE_INVALID = "executed_while_invalid"
    UNTRADEABLE_ASSESSED = "untradeable_assessed"
    RESOLVED = "resolved"


#: `origin` is fixed per kind and is **not** a free choice a caller may set.
#: `UNTRADEABLE_ASSESSED` is `ABSENT` today: judging tradeability at size needs
#: spread and depth data FMITS does not ingest, so the kind exists in the
#: vocabulary with no way to produce it honestly, and that is recorded rather
#: than filled in with a guess.
KIND_ORIGINS: Mapping[LifecycleKind, ValueOrigin] = MappingProxyType(
    {
        LifecycleKind.OWNER_DECIDED: ValueOrigin.ASSERTED,
        LifecycleKind.WITHDRAWN_BY_AUTHOR: ValueOrigin.ASSERTED,
        LifecycleKind.REAFFIRMED: ValueOrigin.MEASURED,
        LifecycleKind.ENTRY_TRIGGERED: ValueOrigin.MEASURED,
        LifecycleKind.INVALIDATION_REACHED: ValueOrigin.MEASURED,
        LifecycleKind.EXPIRED_UNTRIGGERED: ValueOrigin.MEASURED,
        LifecycleKind.EXPIRED_UNDECIDED: ValueOrigin.MEASURED,
        LifecycleKind.EXECUTED: ValueOrigin.MEASURED,
        LifecycleKind.EXECUTED_WHILE_INVALID: ValueOrigin.MEASURED,
        LifecycleKind.UNTRADEABLE_ASSESSED: ValueOrigin.ABSENT,
        LifecycleKind.RESOLVED: ValueOrigin.MEASURED,
    }
)

#: Every kind caused by a closed candle or a clock, and therefore every kind that
#: must carry the `close_time` the stream is ordered by.
MEASURED_KINDS: frozenset[LifecycleKind] = frozenset(
    kind for kind, origin in KIND_ORIGINS.items() if origin is ValueOrigin.MEASURED
)

#: Kinds the owner asserts about themselves and their own policy.
ASSERTED_KINDS: frozenset[LifecycleKind] = frozenset(
    kind for kind, origin in KIND_ORIGINS.items() if origin is ValueOrigin.ASSERTED
)


class ProposalState(Enum):
    """The fold of the stream — **never stored, always derived**.

    This is the brief's `TradeStatus` as it applies to a *suggestion*. The brief's
    thirteen candidate states mixed four objects' lifecycles into one list; these
    are the ones that belong to a proposal. `Detected` / `Candidate` / `Confirmed`
    belong to the recomputed setup reading and are not states of anything stored;
    `Entered` / `Scaled` / `Reduced` / `Closed` belong to the position fold;
    `Archived` is a storage property and not a state at all.
    """

    LIVE = "live"
    DECIDED = "decided"
    WITHDRAWN = "withdrawn"
    LAPSED = "lapsed"
    TRIGGERED = "triggered"
    INVALIDATED = "invalidated"
    EXECUTED = "executed"
    ENTERED_ANYWAY = "entered_anyway"
    RESOLVED = "resolved"


#: `RESOLVED` is the only terminal state, and it is itself an event: an outcome
#: was computed and frozen. Nothing follows it.
TERMINAL_STATES: frozenset[ProposalState] = frozenset({ProposalState.RESOLVED})

#: The whole legal state machine, in one table. An event whose kind is absent from
#: the current state's row is an `IllegalTransitionError` — never a silent
#: no-op, and never a "best guess" at what the caller meant.
TRANSITIONS: Mapping[ProposalState, Mapping[LifecycleKind, ProposalState]] = (
    MappingProxyType(
        {
            ProposalState.LIVE: MappingProxyType(
                {
                    LifecycleKind.REAFFIRMED: ProposalState.LIVE,
                    LifecycleKind.UNTRADEABLE_ASSESSED: ProposalState.LIVE,
                    LifecycleKind.OWNER_DECIDED: ProposalState.DECIDED,
                    LifecycleKind.WITHDRAWN_BY_AUTHOR: ProposalState.WITHDRAWN,
                    LifecycleKind.EXPIRED_UNDECIDED: ProposalState.LAPSED,
                    LifecycleKind.INVALIDATION_REACHED: ProposalState.INVALIDATED,
                }
            ),
            ProposalState.DECIDED: MappingProxyType(
                {
                    LifecycleKind.REAFFIRMED: ProposalState.DECIDED,
                    LifecycleKind.ENTRY_TRIGGERED: ProposalState.TRIGGERED,
                    LifecycleKind.EXPIRED_UNTRIGGERED: ProposalState.LAPSED,
                    LifecycleKind.INVALIDATION_REACHED: ProposalState.INVALIDATED,
                    LifecycleKind.RESOLVED: ProposalState.RESOLVED,
                }
            ),
            ProposalState.TRIGGERED: MappingProxyType(
                {
                    LifecycleKind.EXECUTED: ProposalState.EXECUTED,
                    LifecycleKind.INVALIDATION_REACHED: ProposalState.INVALIDATED,
                    LifecycleKind.RESOLVED: ProposalState.RESOLVED,
                }
            ),
            ProposalState.INVALIDATED: MappingProxyType(
                {
                    LifecycleKind.EXECUTED_WHILE_INVALID: ProposalState.ENTERED_ANYWAY,
                    LifecycleKind.RESOLVED: ProposalState.RESOLVED,
                }
            ),
            ProposalState.LAPSED: MappingProxyType(
                {
                    LifecycleKind.EXECUTED_WHILE_INVALID: ProposalState.ENTERED_ANYWAY,
                    LifecycleKind.RESOLVED: ProposalState.RESOLVED,
                }
            ),
            ProposalState.WITHDRAWN: MappingProxyType(
                {LifecycleKind.RESOLVED: ProposalState.RESOLVED}
            ),
            ProposalState.EXECUTED: MappingProxyType(
                {LifecycleKind.RESOLVED: ProposalState.RESOLVED}
            ),
            ProposalState.ENTERED_ANYWAY: MappingProxyType(
                {LifecycleKind.RESOLVED: ProposalState.RESOLVED}
            ),
            ProposalState.RESOLVED: MappingProxyType({}),
        }
    )
)


@dataclass(frozen=True, slots=True)
class ProposalLifecycleEvent:
    """One thing that happened to a proposal. Append-only, immutable, never edited.

    A wrong event is superseded by a later event carrying `supersedes` — the
    identical mechanism the ledger uses for a `Correction`, not a second one.
    """

    proposal_id: str
    kind: LifecycleKind
    occurred_at: datetime
    recorded_at: datetime
    reason_tag: VersionedTerm | Absent
    causing_close_time: datetime | Absent
    audit: RecordAudit
    note: str | Absent = field(default_factory=lambda: Absent("no note"))
    reference: str | Absent = field(default_factory=lambda: Absent("no reference"))
    session_id: str | Absent = field(default_factory=lambda: Absent("no session"))
    same_bar: bool = False
    supersedes: str | Absent = field(default_factory=lambda: Absent("supersedes nothing"))
    schema_version: int = LIFECYCLE_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_domain_record_id(self.proposal_id)
        require_member(self.kind, LifecycleKind, "kind")
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
        if not isinstance(self.reason_tag, (VersionedTerm, Absent)):
            raise TypeError("reason_tag must be a VersionedTerm or Absent")
        if not isinstance(self.causing_close_time, Absent):
            object.__setattr__(
                self,
                "causing_close_time",
                require_utc(self.causing_close_time, "causing_close_time"),
            )
        require_unmodified(self.audit, "ProposalLifecycleEvent")
        for name in ("note", "reference", "session_id"):
            value = getattr(self, name)
            if not isinstance(value, Absent):
                object.__setattr__(self, name, require_text(value, name))
        if not isinstance(self.same_bar, bool):
            raise TypeError("same_bar must be a bool")
        if not isinstance(self.supersedes, Absent):
            validate_domain_record_id(self.supersedes)
        if self.schema_version not in SUPPORTED_LIFECYCLE_EVENT_VERSIONS:
            raise DomainValidationError(
                f"lifecycle event schema_version {self.schema_version} is not one "
                f"this build writes ({sorted(SUPPORTED_LIFECYCLE_EVENT_VERSIONS)})"
            )
        self._validate_kind_rules()

    def _validate_kind_rules(self) -> None:
        if self.kind is LifecycleKind.OWNER_DECIDED and isinstance(
            self.reason_tag, Absent
        ):
            raise DomainValidationError(
                "OWNER_DECIDED requires a reason_tag from the closed "
                "acceptance/rejection vocabulary. The reason is the field that "
                "makes rejections analysable; without it a rejected proposal is a "
                "row nobody can learn from"
            )
        if self.kind in MEASURED_KINDS and isinstance(self.causing_close_time, Absent):
            raise DomainValidationError(
                f"{self.kind.value} is MEASURED and must carry the close_time of "
                "the candle that caused it. The stream is ordered by that time, "
                "not by scan time — ordering by scan time recreates ADR-0021's "
                "intrabar-order problem one layer up"
            )
        if self.kind not in MEASURED_KINDS and not isinstance(
            self.causing_close_time, Absent
        ):
            raise DomainValidationError(
                f"{self.kind.value} is not caused by a candle and must not claim "
                "a causing close_time"
            )
        if self.same_bar and isinstance(self.causing_close_time, Absent):
            raise DomainValidationError(
                "same_bar marks two events caused by one candle; an event with no "
                "causing candle cannot share a bar with anything"
            )
        if self.kind is LifecycleKind.UNTRADEABLE_ASSESSED:
            raise DomainValidationError(
                "UNTRADEABLE_ASSESSED exists in the vocabulary and cannot be "
                "produced: judging tradeability at size needs spread and depth "
                "data this system does not ingest. It is recorded as a known gap "
                "rather than filled in with a guess"
            )

    @property
    def origin(self) -> ValueOrigin:
        """Fixed by kind. Never a caller's choice."""
        return KIND_ORIGINS[self.kind]

    @property
    def ordering_key(self) -> datetime:
        """The instant the stream is ordered by.

        The causing candle's close for a `MEASURED` event; the moment it occurred
        for an assertion. A scan that runs late records a *later* `recorded_at`
        and the *same* ordering key, which is the whole point.
        """
        if isinstance(self.causing_close_time, Absent):
            return self.occurred_at
        return self.causing_close_time

    @property
    def digest_basis(self) -> dict[str, Any]:
        """The economic/semantic fields only.

        `recorded_at` is excluded, following ADR-0027 §3's precedent for
        `archived_at`: whether the same event is recognised as already recorded
        must not depend on when a crashed scan was restarted.
        """
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "kind": self.kind.value,
            "occurred_at": encode_timestamp(self.occurred_at),
            "reason_tag": encode_maybe(self.reason_tag, VersionedTerm.to_payload),
            "causing_close_time": encode_maybe(
                self.causing_close_time, encode_timestamp
            ),
            "note": encode_maybe(self.note, str),
            "reference": encode_maybe(self.reference, str),
            "session_id": encode_maybe(self.session_id, str),
            "same_bar": self.same_bar,
            "supersedes": encode_maybe(self.supersedes, str),
        }

    @property
    def event_id(self) -> str:
        return build_domain_record_id(
            type_slug=LIFECYCLE_EVENT_TYPE_SLUG,
            subject=self.kind.value,
            moment=self.occurred_at,
            digest=content_digest_over(self.digest_basis),
        )

    def to_payload(self) -> dict[str, Any]:
        payload = self.digest_basis
        payload["event_id"] = self.event_id
        payload["recorded_at"] = encode_timestamp(self.recorded_at)
        payload["audit"] = self.audit.to_payload()
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> ProposalLifecycleEvent:
        mapping = require_mapping(raw, "lifecycle event")
        version = require_payload_version(
            mapping,
            supported=SUPPORTED_LIFECYCLE_EVENT_VERSIONS,
            entity="lifecycle event",
        )
        require_exact_keys(
            mapping,
            {
                "schema_version",
                "event_id",
                "proposal_id",
                "kind",
                "occurred_at",
                "recorded_at",
                "reason_tag",
                "causing_close_time",
                "note",
                "reference",
                "session_id",
                "same_bar",
                "supersedes",
                "audit",
            },
            "lifecycle event",
        )
        try:
            kind = LifecycleKind(mapping["kind"])
        except ValueError as error:
            raise PayloadDecodeError(
                f"lifecycle kind {mapping['kind']!r} is not known to this build; "
                "an unknown member is a clean rejection, never a default"
            ) from error
        decoded = cls(
            proposal_id=str(mapping["proposal_id"]),
            kind=kind,
            occurred_at=decode_timestamp(mapping["occurred_at"]),
            recorded_at=decode_timestamp(mapping["recorded_at"]),
            reason_tag=decode_maybe(mapping["reason_tag"], VersionedTerm.from_payload),
            causing_close_time=decode_maybe(
                mapping["causing_close_time"], decode_timestamp
            ),
            audit=RecordAudit.from_payload(mapping["audit"]),
            note=decode_maybe(mapping["note"], str),
            reference=decode_maybe(mapping["reference"], str),
            session_id=decode_maybe(mapping["session_id"], str),
            same_bar=bool(mapping["same_bar"]),
            supersedes=decode_maybe(mapping["supersedes"], str),
            schema_version=version,
        )
        if mapping["event_id"] != decoded.event_id:
            raise PayloadDecodeError(
                f"event_id {mapping['event_id']!r} does not match the digest of "
                f"the event it claims to identify ({decoded.event_id!r})"
            )
        return decoded


@dataclass(frozen=True, slots=True)
class ProposalStateView:
    """The fold's result: a state, the events behind it, and any ambiguity.

    `is_ambiguous` is a first-class answer rather than an exception. When two
    events caused by the *same* closed candle would move the proposal to two
    different states, their real order is unknowable without sub-bar data this
    repository does not ingest — so the fold stops at the last unambiguous state
    and *says so*. Resolving it to the flattering side is the rejected
    alternative; ADR-0021 already refuses the identical guess for a two-sided
    break bar.
    """

    state: ProposalState
    applied: tuple[str, ...]
    is_ambiguous: bool = False
    ambiguous_events: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_member(self.state, ProposalState, "state")
        require_tuple_of(self.applied, str, "applied")
        if not isinstance(self.is_ambiguous, bool):
            raise TypeError("is_ambiguous must be a bool")
        require_tuple_of(self.ambiguous_events, str, "ambiguous_events")
        if self.is_ambiguous and len(self.ambiguous_events) < 2:
            raise DomainValidationError(
                "an ambiguity names at least the two events that cannot be "
                "ordered against each other"
            )
        if not self.is_ambiguous and self.ambiguous_events:
            raise DomainValidationError(
                "ambiguous_events is populated on a view that is not ambiguous"
            )

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def is_live(self) -> bool:
        """Whether a second proposal on the same anchor would be a duplicate."""
        return self.state is ProposalState.LIVE

    def to_payload(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "applied": list(self.applied),
            "is_ambiguous": self.is_ambiguous,
            "ambiguous_events": list(self.ambiguous_events),
        }


def fold_proposal_state(
    proposal: OpportunityProposal, events: Iterable[ProposalLifecycleEvent]
) -> ProposalStateView:
    """Replay the stream and return the state it reaches.

    Pure: same proposal, same events, same answer, forever. Nothing is stored and
    nothing is cached — deleting a folded state and recomputing it must produce
    the identical result, which is the CI test the durability classification rests
    on.
    """
    if not isinstance(proposal, OpportunityProposal):
        raise TypeError(
            f"proposal must be an OpportunityProposal, got {type(proposal).__name__}"
        )
    ordered = _order_events(proposal, events)
    state = ProposalState.LIVE
    applied: list[str] = []
    position = 0
    while position < len(ordered):
        group = _same_bar_group(ordered, position)
        if len(group) > 1:
            outcomes = {
                TRANSITIONS[state].get(event.kind) for event in group
            }
            if len(outcomes) > 1:
                return ProposalStateView(
                    state=state,
                    applied=tuple(applied),
                    is_ambiguous=True,
                    ambiguous_events=tuple(event.event_id for event in group),
                )
        for event in group:
            state = _apply(state, event)
            applied.append(event.event_id)
        position += len(group)
    return ProposalStateView(state=state, applied=tuple(applied))


def _order_events(
    proposal: OpportunityProposal, events: Iterable[ProposalLifecycleEvent]
) -> tuple[ProposalLifecycleEvent, ...]:
    materialized = tuple(events)
    require_tuple_of(materialized, ProposalLifecycleEvent, "events")
    for event in materialized:
        if event.proposal_id != proposal.proposal_id:
            raise DomainValidationError(
                f"event {event.event_id} belongs to proposal {event.proposal_id}, "
                f"not to {proposal.proposal_id}"
            )
    superseded = {
        event.supersedes
        for event in materialized
        if not isinstance(event.supersedes, Absent)
    }
    live = [event for event in materialized if event.event_id not in superseded]
    ordered = tuple(
        sorted(live, key=lambda event: (event.ordering_key, event.kind.value))
    )
    _require_same_bar_marked(ordered)
    return ordered


def _require_same_bar_marked(ordered: tuple[ProposalLifecycleEvent, ...]) -> None:
    """Two events caused by one candle must say so, or the fold would guess.

    Without the marker the sort falls back to kind name, which is an arbitrary
    order presented as a real one — precisely the corruption AP-D4a names for the
    `EXECUTED_WHILE_INVALID` classification. Refusing here is cheaper than
    discovering it in a bias metric three years later.
    """
    for previous, current in zip(ordered, ordered[1:]):
        if isinstance(previous.causing_close_time, Absent):
            continue
        if previous.causing_close_time != current.causing_close_time:
            continue
        if not (previous.same_bar and current.same_bar):
            raise DomainValidationError(
                f"{previous.kind.value} and {current.kind.value} were both caused "
                f"by the candle closing at {previous.ordering_key.isoformat()} and "
                "are not marked same_bar. Their real order is unknowable without "
                "sub-bar data this system does not ingest, and ordering them by "
                "anything else would invent a sequence"
            )


def _same_bar_group(
    ordered: tuple[ProposalLifecycleEvent, ...], start: int
) -> tuple[ProposalLifecycleEvent, ...]:
    """The run of events sharing one causing candle and marked `same_bar`."""
    first = ordered[start]
    if not first.same_bar:
        return (first,)
    group = [first]
    index = start + 1
    while (
        index < len(ordered)
        and ordered[index].same_bar
        and ordered[index].ordering_key == first.ordering_key
    ):
        group.append(ordered[index])
        index += 1
    return tuple(group)


def _apply(state: ProposalState, event: ProposalLifecycleEvent) -> ProposalState:
    allowed = TRANSITIONS[state]
    if event.kind not in allowed:
        raise IllegalTransitionError(
            f"{event.kind.value} cannot follow state {state.value}. Legal here: "
            f"{sorted(kind.value for kind in allowed) or ['(terminal — nothing)']}"
        )
    return allowed[event.kind]


# --------------------------------------------------------------------------
# Creation rule 4 — one live proposal per anchor.
# --------------------------------------------------------------------------


class AdmissionOutcome(Enum):
    """What happened when a candidate proposal met the existing live ones."""

    CREATED = "created"
    REAFFIRMED = "reaffirmed"


@dataclass(frozen=True, slots=True)
class ProposalAdmission:
    """The result of applying creation rule 4."""

    outcome: AdmissionOutcome
    proposal: OpportunityProposal
    reaffirmation: ProposalLifecycleEvent | Absent

    def __post_init__(self) -> None:
        require_member(self.outcome, AdmissionOutcome, "outcome")
        if not isinstance(self.proposal, OpportunityProposal):
            raise TypeError("proposal must be an OpportunityProposal")
        if not isinstance(self.reaffirmation, (ProposalLifecycleEvent, Absent)):
            raise TypeError("reaffirmation must be a ProposalLifecycleEvent or Absent")
        if self.outcome is AdmissionOutcome.REAFFIRMED and isinstance(
            self.reaffirmation, Absent
        ):
            raise DomainValidationError(
                "a reaffirmation outcome carries the event that records it"
            )
        if self.outcome is AdmissionOutcome.CREATED and not isinstance(
            self.reaffirmation, Absent
        ):
            raise DomainValidationError(
                "a newly created proposal has nothing to reaffirm"
            )


def admit(
    candidate: OpportunityProposal,
    live: Iterable[tuple[OpportunityProposal, ProposalStateView]],
    *,
    occurred_at: datetime,
    recorded_at: datetime,
    causing_close_time: datetime,
    note: str | Absent = Absent("no note"),
) -> ProposalAdmission:
    """Creation rule 4: one live proposal per anchor.

    A second proposal may not be created while a live proposal exists with the
    same anchor. A re-run that would produce a duplicate appends a `REAFFIRMED`
    event to the existing proposal and returns it.

    **This rule, and not any read-time grouping, is what prevents one idea
    becoming forty proposals.** The anchor is `MEASURED` — a level origin the
    level-crossing engine already produced, carrying its own confirmation-bar
    provenance — so it cannot be redrawn by a later policy change. `AV`'s setup
    identity was derived from a window-relative bar index that changed every bar
    and produced 549 "unique setups" from 552 directional observations; keying
    deduplication on a policy-derived id would reproduce that failure with frozen
    artifacts pointing at it.

    `REAFFIRMED` also earns its place beyond deduplication: how many times a setup
    was re-observed before the owner acted, or before it expired, is a behavioural
    measurement nothing else in the model can produce.
    """
    if not isinstance(candidate, OpportunityProposal):
        raise TypeError("candidate must be an OpportunityProposal")
    anchor = candidate.anchor
    for existing, view in live:
        if not isinstance(existing, OpportunityProposal):
            raise TypeError("live entries hold an OpportunityProposal")
        if not isinstance(view, ProposalStateView):
            raise TypeError("live entries hold a ProposalStateView")
        if not view.is_live:
            raise DomainValidationError(
                f"proposal {existing.proposal_id} is in state {view.state.value} "
                "and is not live; creation rule 4 compares against live proposals "
                "only, and passing a resolved one would suppress a legitimate "
                "new suggestion"
            )
        if isinstance(anchor, Absent) or isinstance(existing.anchor, Absent):
            continue
        if _anchor_matches(existing.anchor, anchor):
            return ProposalAdmission(
                outcome=AdmissionOutcome.REAFFIRMED,
                proposal=existing,
                reaffirmation=ProposalLifecycleEvent(
                    proposal_id=existing.proposal_id,
                    kind=LifecycleKind.REAFFIRMED,
                    occurred_at=occurred_at,
                    recorded_at=recorded_at,
                    reason_tag=Absent("REAFFIRMED is measured, not reasoned"),
                    causing_close_time=causing_close_time,
                    audit=RecordAudit.frozen_at(require_utc(recorded_at, "recorded_at")),
                    note=note,
                    reference=candidate.market_snapshot_id,
                ),
            )
    return ProposalAdmission(
        outcome=AdmissionOutcome.CREATED,
        proposal=candidate,
        reaffirmation=Absent("newly created"),
    )


def _anchor_matches(left: Anchor, right: Anchor) -> bool:
    """Whether two anchors name the same idea — `setup_identity`'s rule, not `==`.

    Structural equality was the original implementation and was wrong in a way
    that could not fire while nothing in the repository constructed an `Anchor`.
    `LevelOriginRef.swing_index` is **window-relative**: the analysis window slides
    forward one candle per instant, so the same pivot reports a different index on
    every bar, and `left == right` therefore returns `False` for two readings of
    one idea taken a bar apart. Creation rule 4 would have admitted a new proposal
    every bar — 549 "unique setups" from 552 observations, this time with frozen
    artifacts pointing at them, which is precisely the failure `admit`'s own
    docstring says keying on the `MEASURED` anchor prevents.

    Deduplication and the read-time grouping in `occurrence.py` now call the same
    function, so *"one live proposal per anchor"* and *"one occurrence per anchor"*
    can never disagree about what the same setup is.
    """
    return anchors_match(left, right)
