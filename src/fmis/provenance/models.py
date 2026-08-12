"""Provenance: where a value came from, whether it can be wrong, and absence.

Four types, and the whole package imports nothing from `fmis` except the record
spine's validators. `AP` §5.2 places it below the trading domain beside the
kernel for a reason: the ledger, the journal, the portfolio, the proposal and the
memory layer all need it, and none of them imports the presentation model.

**`ValueOrigin` is not the workspace's `Tier`.** `Tier` answers *"how must the
analysis page render this"*; `ValueOrigin` answers *"where did this come from and
can it be wrong"*. The mapping between them is one-way and applied only at a
presentation boundary, and `ASSERTED` has no `Tier` equivalent at all — a gap the
mapping surfaces rather than hides. No existing enum changes.

**`Absent[T]` is one shape for four ideas.** `AP` writes `ABSENT`,
`INDETERMINATE(reason)`, `NotApplicable(reason)` and `InsufficientSample(n)` in
four different sections. They are one concept — *absence, with a reason* — and
`AP_ADR_DISCOVERY` AP-D13 records three independent reinventions of it inside
`AP`'s own text. One shape here is that decision's proposed answer, carrying the
sample size for the one variant where `n` is the entire point.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.records import (
    DomainValidationError,
    PayloadDecodeError,
    TradeDomainError,
    require_int,
    require_member,
    require_optional_text,
    require_optional_utc,
    require_text,
)

__all__ = [
    "ProvenanceError",
    "ValueOrigin",
    "Absent",
    "Assertion",
    "VersionedTerm",
    "CORRECTABLE_ORIGINS",
    "encode_maybe",
    "decode_maybe",
]

T = TypeVar("T")


class ProvenanceError(TradeDomainError):
    """Base class for every provenance failure."""


class ValueOrigin(str, Enum):
    """Where a value came from — and therefore what may be done about it.

    * `MEASURED` — computed by an engine from data, reproducibly. It cannot be
      wrong; only its inputs can.
    * `POLICY_DERIVED` — produced from measured values under a **named, versioned
      policy**. Wrong only if the policy is, and the policy version is recorded
      rather than the value rewritten.
    * `ASSERTED` — stated by the owner or a venue. **The only class that can
      simply be wrong**, and the only one correctable by supersession.
    * `INTERPRETED` — produced by a model, or authored as opinion. Not a truth
      claim, and never an input to a computation.
    * `ABSENT` — not available, with a stated reason.

    A surface that cannot distinguish `ASSERTED` from `MEASURED` is rendering a
    lie of omission, which is why this is a property of the value and not of the
    subsystem that happens to hold it.
    """

    MEASURED = "measured"
    POLICY_DERIVED = "policy_derived"
    ASSERTED = "asserted"
    INTERPRETED = "interpreted"
    ABSENT = "absent"


#: The origins a later record may supersede. `MEASURED` and `POLICY_DERIVED` are
#: absent from this set on purpose: a measurement is not corrected, it is
#: recomputed, and a policy reading is not corrected, its policy is versioned.
CORRECTABLE_ORIGINS: frozenset[ValueOrigin] = frozenset(
    {ValueOrigin.ASSERTED, ValueOrigin.INTERPRETED}
)


@dataclass(frozen=True, slots=True)
class Absent(Generic[T]):
    """A value that is not there, and the reason it is not there.

    Never `None`, never `0`, never `""`. `AP` §14.3's warning is the concrete
    case: a missing mark stored as zero *"makes the total look plausible and
    survives for years"*.

    `sample_size` is populated only for the `InsufficientSample(n)` face, where
    the count is the whole content of the answer — *"we have three closed trades
    in this cohort"* is a different statement from *"we have none"*, and a reader
    who cannot tell them apart will treat both as silence.
    """

    reason: str
    sample_size: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", require_text(self.reason, "reason"))
        if self.sample_size is not None:
            require_int(self.sample_size, "sample_size", minimum=0)

    @property
    def origin(self) -> ValueOrigin:
        """Absence is itself an origin — `AP` §5.2's fifth member."""
        return ValueOrigin.ABSENT

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"reason": self.reason}
        if self.sample_size is not None:
            payload["sample_size"] = self.sample_size
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> Absent[Any]:
        if not isinstance(raw, Mapping):
            raise PayloadDecodeError(
                f"absence must be a JSON object, got {type(raw).__name__}"
            )
        unknown = set(raw) - {"reason", "sample_size"}
        if unknown:
            raise PayloadDecodeError(f"absence has unknown field(s) {sorted(unknown)}")
        if "reason" not in raw:
            raise PayloadDecodeError("absence is missing 'reason'")
        sample_size = raw.get("sample_size")
        if sample_size is not None and (
            isinstance(sample_size, bool) or not isinstance(sample_size, int)
        ):
            raise PayloadDecodeError("absence sample_size must be an int or absent")
        return cls(reason=str(raw["reason"]), sample_size=sample_size)


@dataclass(frozen=True, slots=True)
class Assertion(Generic[T]):
    """One value, its origin, and who or what supplied it.

    Used where a *single field* carries a provenance different from the record
    around it — a portfolio mark inside an otherwise measured snapshot, an
    owner-asserted correlation cluster inside an otherwise measured constraint
    check. Where a whole field *group* shares one origin the card states it and
    this wrapper is unnecessary weight.

    `as_of` is the instant the value was true at its source, which is not the
    instant the record was built: a mark read at 22:00 and frozen into a 22:15
    snapshot is stale by fifteen minutes, and that is a fact a reader is entitled
    to see rather than infer.
    """

    value: T
    origin: ValueOrigin
    source: str
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        require_member(self.origin, ValueOrigin, "origin")
        if self.origin is ValueOrigin.ABSENT:
            raise DomainValidationError(
                "an Assertion cannot carry ValueOrigin.ABSENT; absence is "
                "Absent(reason), which has no value to assert"
            )
        object.__setattr__(self, "source", require_text(self.source, "source"))
        object.__setattr__(self, "as_of", require_optional_utc(self.as_of, "as_of"))

    @property
    def is_correctable(self) -> bool:
        """Whether a later record may supersede this value."""
        return self.origin in CORRECTABLE_ORIGINS

    def to_payload(self, encode_value: Callable[[T], Any]) -> dict[str, Any]:
        return {
            "value": encode_value(self.value),
            "origin": self.origin.value,
            "source": self.source,
            "as_of": None if self.as_of is None else encode_timestamp(self.as_of),
        }

    @classmethod
    def from_payload(
        cls, raw: Any, decode_value: Callable[[Any], T]
    ) -> Assertion[T]:
        if not isinstance(raw, Mapping):
            raise PayloadDecodeError(
                f"assertion must be a JSON object, got {type(raw).__name__}"
            )
        expected = {"value", "origin", "source", "as_of"}
        if set(raw) != expected:
            raise PayloadDecodeError(
                f"assertion keys {sorted(raw)} != {sorted(expected)}"
            )
        try:
            origin = ValueOrigin(raw["origin"])
        except ValueError as error:
            raise PayloadDecodeError(
                f"assertion origin {raw['origin']!r} is not a known ValueOrigin"
            ) from error
        as_of_raw = raw["as_of"]
        return cls(
            value=decode_value(raw["value"]),
            origin=origin,
            source=str(raw["source"]),
            as_of=None if as_of_raw is None else decode_timestamp(as_of_raw),
        )


@dataclass(frozen=True, slots=True, order=True)
class VersionedTerm:
    """One term in one closed, counted vocabulary, at a stated taxonomy version.

    The mechanism that stops a word being silently redefined under a statistic.
    A reason tag, a mistake tag, an emotion tag, an exit reason, a rejection
    reason, an amendment reason, an override reason and a setup type are all
    this type — seven vocabularies, one shape, and **this package defines no
    members of any of them**. Membership is the owner's; `AP` §20.2's rule is
    *retire and add, never redefine*.

    `taxonomy_version` travels with every use because a cohort spanning a term's
    introduction must report a **coverage gap** rather than a zero, and it cannot
    do that if the records it aggregates do not say which vocabulary they meant.
    """

    vocabulary_id: str
    term_id: str
    taxonomy_version: int
    display_label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "vocabulary_id", require_text(self.vocabulary_id, "vocabulary_id")
        )
        object.__setattr__(self, "term_id", require_text(self.term_id, "term_id"))
        require_int(self.taxonomy_version, "taxonomy_version", minimum=1)
        object.__setattr__(
            self,
            "display_label",
            require_optional_text(self.display_label, "display_label"),
        )

    @property
    def qualified_id(self) -> str:
        """`{vocabulary}:{term}` — the form a record cites and a surface resolves."""
        return f"{self.vocabulary_id}:{self.term_id}"

    def to_payload(self) -> dict[str, Any]:
        return {
            "vocabulary_id": self.vocabulary_id,
            "term_id": self.term_id,
            "taxonomy_version": self.taxonomy_version,
            "display_label": self.display_label,
        }

    @classmethod
    def from_payload(cls, raw: Any) -> VersionedTerm:
        if not isinstance(raw, Mapping):
            raise PayloadDecodeError(
                f"term must be a JSON object, got {type(raw).__name__}"
            )
        expected = {"vocabulary_id", "term_id", "taxonomy_version", "display_label"}
        if set(raw) != expected:
            raise PayloadDecodeError(f"term keys {sorted(raw)} != {sorted(expected)}")
        return cls(
            vocabulary_id=str(raw["vocabulary_id"]),
            term_id=str(raw["term_id"]),
            taxonomy_version=raw["taxonomy_version"],
            display_label=raw["display_label"],
        )


def encode_maybe(value: T | Absent[T], encode: Callable[[T], Any]) -> dict[str, Any]:
    """Serialize a `T | Absent[T]` union as a one-key tagged object.

    `{"value": ...}` or `{"absent": {"reason": ...}}`. Tagged rather than
    nullable because `null` cannot carry a reason, and Law 4's whole content is
    that absence has one. A caller reading a tagged union cannot accidentally
    treat "we could not compute it" as "it is nothing".
    """
    if isinstance(value, Absent):
        return {"absent": value.to_payload()}
    return {"value": encode(value)}


def decode_maybe(raw: Any, decode: Callable[[Any], T]) -> T | Absent[T]:
    """Read back what `encode_maybe` wrote, rejecting any other shape."""
    if not isinstance(raw, Mapping) or len(raw) != 1:
        raise PayloadDecodeError(
            "a maybe-absent value must be a one-key object holding 'value' or "
            f"'absent', got {raw!r}"
        )
    if "absent" in raw:
        return Absent.from_payload(raw["absent"])
    if "value" in raw:
        return decode(raw["value"])
    raise PayloadDecodeError(
        f"a maybe-absent value must hold 'value' or 'absent', got {sorted(raw)}"
    )
