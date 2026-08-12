"""`VersionSet` — one content-addressed bundle replacing ten version fields.

**BG-D10.** Counted across `AP`: `policy_version`, `model_version`,
`template_version`, `classification_version`, `taxonomy_version`,
`calculation_version`, `capture_schema_version`, `rule_set_version`,
`counterfactual_assumption_version`, plus `code_version`. Ten axes. Stamping ten
fields on every captured artifact is genuine weight, and `AP_ADR_DISCOVERY`
AP-D12 already found four subsystems independently reinventing versioning.

The deduplication is the point rather than an optimization. Ten axes across
~50,000 artifacts over a decade is ~500,000 stored version strings; the number of
*distinct* combinations is bounded by releases × policy revisions — hundreds. The
larger gain is comparability: *"were these two decisions made under the same
system?"* becomes an id comparison rather than a ten-field diff nobody will write.

**The id is the digest and nothing else.** Every other captured artifact in the
domain carries `{type}-{subject}-{stamp}-{digest}`, and a version set deliberately
does not: it is a statement about the past with no instant of its own, so a
timestamped id would give one set two identities and break the deduplication this
entity exists for.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from fmis.provenance import Absent
from fmis.records import (
    DomainValidationError,
    PayloadDecodeError,
    TradeDomainError,
    content_digest_over,
    field_introduced_in,
    require_exact_keys,
    require_mapping,
    require_payload_version,
    require_text,
)

__all__ = [
    "VersioningError",
    "VersionAxis",
    "AXIS_ORDER",
    "VersionSet",
    "deduplicate",
    "VERSION_SET_SCHEMA_VERSION",
    "SUPPORTED_VERSION_SET_VERSIONS",
]

#: The set's **own** schema version. Adding an eleventh axis bumps this, and
#: prior sets then read the new axis as `Absent(reason="… introduced in schema
#: version N")` — never as an empty string and never as a default. That is the
#: coverage-gap semantics `AP_ADR_DISCOVERY` AP-D17 asks for, implemented once
#: here instead of rediscovered per record type.
VERSION_SET_SCHEMA_VERSION = 1

SUPPORTED_VERSION_SET_VERSIONS = frozenset({1})


class VersioningError(TradeDomainError):
    """Base class for every versioning failure."""


class VersionAxis(str, Enum):
    """The ten axes in force today.

    Every one is read from the running build or from an accepted policy record —
    none is typed by a person at capture time, which is why the whole record is
    `MEASURED` even though several of the things it names are policies.
    """

    #: The build that produced the artifact. The one string that keeps a future
    #: true-replay capability *possible*; unrecoverable if skipped.
    CODE_VERSION = "code_version"
    #: The payload contract the artifact was written under.
    CAPTURE_SCHEMA_VERSION = "capture_schema_version"
    #: `fmis.archive`'s envelope version, where the artifact was archived.
    ARCHIVE_SCHEMA_VERSION = "archive_schema_version"
    #: The setup / proposal policy in force.
    POLICY_VERSION = "policy_version"
    #: The vocabulary generation every term reference resolves against.
    TAXONOMY_VERSION = "taxonomy_version"
    #: Folds and groupings — the position fold, the occurrence grouping.
    CALCULATION_VERSION = "calculation_version"
    #: Read-time classification (sector, theme, cluster) applied to a snapshot.
    CLASSIFICATION_VERSION = "classification_version"
    #: Stamped at proposal creation, never chosen at evaluation.
    COUNTERFACTUAL_ASSUMPTION_VERSION = "counterfactual_assumption_version"
    #: The `RiskBudget` generation a constraint check evaluated against.
    RISK_POLICY_VERSION = "risk_policy_version"
    #: Model identity and prompt template, for anything `INTERPRETED`.
    MODEL_TEMPLATE_VERSION = "model_template_version"


#: Reporting order — the axis order every rendering and every digest basis uses.
#: Never enum definition order by accident: it runs from the build outward, so a
#: reader scanning two sets side by side sees the axis most likely to differ
#: first.
AXIS_ORDER: tuple[VersionAxis, ...] = (
    VersionAxis.CODE_VERSION,
    VersionAxis.CAPTURE_SCHEMA_VERSION,
    VersionAxis.ARCHIVE_SCHEMA_VERSION,
    VersionAxis.POLICY_VERSION,
    VersionAxis.CALCULATION_VERSION,
    VersionAxis.TAXONOMY_VERSION,
    VersionAxis.CLASSIFICATION_VERSION,
    VersionAxis.COUNTERFACTUAL_ASSUMPTION_VERSION,
    VersionAxis.RISK_POLICY_VERSION,
    VersionAxis.MODEL_TEMPLATE_VERSION,
)


@dataclass(frozen=True, slots=True)
class VersionSet:
    """Every version axis in force when an artifact was produced.

    Immutable, never superseded, never deleted. A different combination is a
    different set with a different id — there is no update path, because a
    version set is a claim about a moment that has already passed.
    """

    axes: tuple[tuple[VersionAxis, str | Absent], ...]
    schema_version: int = VERSION_SET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.axes, tuple):
            raise TypeError("axes must be a tuple of (VersionAxis, value) pairs")
        if self.schema_version not in SUPPORTED_VERSION_SET_VERSIONS:
            raise DomainValidationError(
                f"version set schema_version {self.schema_version} is not one "
                f"this build writes ({sorted(SUPPORTED_VERSION_SET_VERSIONS)})"
            )
        seen: dict[VersionAxis, str | Absent] = {}
        for position, entry in enumerate(self.axes):
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise TypeError(
                    f"axes[{position}] must be an (VersionAxis, value) pair"
                )
            axis, value = entry
            if not isinstance(axis, VersionAxis):
                raise TypeError(
                    f"axes[{position}][0] must be a VersionAxis, got "
                    f"{type(axis).__name__}"
                )
            if isinstance(value, Absent):
                normalized: str | Absent = value
            else:
                normalized = require_text(value, f"axes[{position}] value")
            if axis in seen:
                raise DomainValidationError(
                    f"axis {axis.value} was supplied twice; one axis, one value"
                )
            seen[axis] = normalized
        missing = [axis.value for axis in AXIS_ORDER if axis not in seen]
        if missing:
            raise DomainValidationError(
                f"every axis must be present or explicitly Absent(reason); "
                f"missing: {missing}. A silently omitted axis is a version "
                "nobody can later tell was never recorded"
            )
        object.__setattr__(
            self, "axes", tuple((axis, seen[axis]) for axis in AXIS_ORDER)
        )

    @classmethod
    def of(
        cls,
        values: Mapping[VersionAxis, str] | None = None,
        *,
        absent_reason: str = "not applicable to this artifact",
    ) -> VersionSet:
        """Build a complete set from the axes a caller knows.

        Every axis the caller does not supply becomes `Absent(reason)` rather
        than being dropped, so a reader can always tell "we did not record it"
        from "it did not apply".
        """
        supplied = dict(values or {})
        unknown = set(supplied) - set(AXIS_ORDER)
        if unknown:
            raise DomainValidationError(
                f"unknown version axes {sorted(a for a in unknown)}"
            )
        return cls(
            axes=tuple(
                (axis, supplied.get(axis, Absent(absent_reason)))
                for axis in AXIS_ORDER
            )
        )

    def value_of(self, axis: VersionAxis) -> str | Absent:
        """The value of one axis, or the `Absent` that stands in its place."""
        if not isinstance(axis, VersionAxis):
            raise TypeError(f"axis must be a VersionAxis, got {type(axis).__name__}")
        for candidate, value in self.axes:
            if candidate is axis:
                return value
        # Unreachable while `__post_init__` requires completeness; kept because a
        # future axis addition must read as an introduction gap, never a crash.
        return Absent(  # pragma: no cover
            field_introduced_in(axis.value, VERSION_SET_SCHEMA_VERSION)
        )

    def require(self, axis: VersionAxis) -> str:
        """The value of one axis, refusing to substitute anything for absence."""
        value = self.value_of(axis)
        if isinstance(value, Absent):
            raise DomainValidationError(
                f"version axis {axis.value} is absent ({value.reason}); a caller "
                "that needs it must handle the absence rather than default it"
            )
        return value

    @property
    def digest_basis(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "axes": {
                axis.value: (
                    {"absent": value.to_payload()}
                    if isinstance(value, Absent)
                    else {"value": value}
                )
                for axis, value in self.axes
            },
        }

    @property
    def version_set_id(self) -> str:
        """`sha256:<hex>` over the sorted axis map. The whole identity."""
        return content_digest_over(self.digest_basis)

    def to_payload(self) -> dict[str, Any]:
        payload = self.digest_basis
        payload["version_set_id"] = self.version_set_id
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> VersionSet:
        mapping = require_mapping(raw, "version set")
        version = require_payload_version(
            mapping, supported=SUPPORTED_VERSION_SET_VERSIONS, entity="version set"
        )
        require_exact_keys(
            mapping, {"schema_version", "axes", "version_set_id"}, "version set"
        )
        raw_axes = mapping["axes"]
        if not isinstance(raw_axes, Mapping):
            raise PayloadDecodeError("version set axes must be a JSON object")
        entries: list[tuple[VersionAxis, str | Absent]] = []
        for name, entry in raw_axes.items():
            try:
                axis = VersionAxis(name)
            except ValueError as error:
                raise PayloadDecodeError(
                    f"version axis {name!r} is not known to this build"
                ) from error
            if not isinstance(entry, Mapping) or len(entry) != 1:
                raise PayloadDecodeError(
                    f"version axis {name!r} must hold exactly one of "
                    "{'value', 'absent'}"
                )
            if "value" in entry:
                entries.append((axis, str(entry["value"])))
            elif "absent" in entry:
                entries.append((axis, Absent.from_payload(entry["absent"])))
            else:
                raise PayloadDecodeError(
                    f"version axis {name!r} has neither 'value' nor 'absent'"
                )
        decoded = cls(axes=tuple(entries), schema_version=version)
        stated = mapping["version_set_id"]
        if stated != decoded.version_set_id:
            raise PayloadDecodeError(
                f"version_set_id {stated!r} does not match the digest of the "
                f"axes it claims to identify ({decoded.version_set_id!r})"
            )
        return decoded


def deduplicate(sets: Iterable[VersionSet]) -> tuple[VersionSet, ...]:
    """Collapse a stream of version sets to the distinct ones, in first-seen order.

    The function that makes BG-D10's storage claim real: every artifact produced
    between two releases shares one set, so a decade of artifacts resolves to
    hundreds of records rather than half a million strings.
    """
    seen: dict[str, VersionSet] = {}
    for candidate in sets:
        if not isinstance(candidate, VersionSet):
            raise TypeError(
                f"expected a VersionSet, got {type(candidate).__name__}"
            )
        seen.setdefault(candidate.version_set_id, candidate)
    return tuple(seen.values())
