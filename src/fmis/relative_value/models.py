"""Result and error types for the Relative Value Engine (v1a).

These are the *vocabulary* of the RVE: the single-metric result object every
metric function returns, the status/reason enums that make an undefined result
explicit rather than a crash, and the exception hierarchy for structural/caller
errors. No metric mathematics lives here.

Result policy (hybrid, decided in ADR-0004):

  * **Structural / caller-contract failures raise** — a caller mistake that makes
    the request itself ill-formed: wrong input type (``TypeError``), too few
    observations (``InsufficientObservationsError``), or unaligned inputs
    (``NotAlignedError``). These must surface loudly.
  * **Mathematically undefined results do NOT crash** — valid, aligned, long
    enough series whose metric is simply undefined (zero denominator, zero
    variance, zero reference volatility, non-finite result) return a
    ``RelativeValueResult`` with ``status=UNDEFINED``, ``value=None`` and a
    ``reason``, so an analytics pipeline can record and continue.

Conventions mirror the rest of the codebase: frozen slotted dataclass,
``MappingProxyType`` metadata (defensively copied), explicit validation, explicit
``__all__``. Deliberately contains no interpretation, score, label, or
recommendation of any kind.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

__all__ = [
    "MetricStatus",
    "UndefinedReason",
    "RelativeValueResult",
    "RelativeValueError",
    "NotAlignedError",
    "InsufficientObservationsError",
]


class MetricStatus(str, Enum):
    """Whether a metric produced a finite value or is explicitly undefined."""

    OK = "ok"
    UNDEFINED = "undefined"


class UndefinedReason(str, Enum):
    """Why an otherwise-valid metric could not produce a finite value."""

    ZERO_DENOMINATOR = "zero_denominator"
    ZERO_VARIANCE = "zero_variance"
    ZERO_REFERENCE_VOLATILITY = "zero_reference_volatility"
    NON_FINITE_RESULT = "non_finite_result"


class RelativeValueError(Exception):
    """Base class for all Relative Value Engine structural errors."""


class NotAlignedError(RelativeValueError, ValueError):
    """Two series were not aligned (unequal length or mismatched timestamps).

    The RVE never aligns, intersects, fills, resamples, or drops observations;
    callers must align upstream (e.g. via ``fmis.alignment.align_intersection``).
    """


class InsufficientObservationsError(RelativeValueError, ValueError):
    """A series has fewer observations than the metric's minimum."""

    def __init__(self, *, metric: str, required: int, actual: int) -> None:
        self.metric = metric
        self.required = required
        self.actual = actual
        super().__init__(
            f"{metric} requires at least {required} observations, got {actual}"
        )


@dataclass(frozen=True, slots=True)
class RelativeValueResult:
    """One metric's outcome: a finite value, or an explicit undefined state.

    Invariants (enforced in ``__post_init__``; violations raise ``ValueError``):
      * ``status == OK``  -> ``value`` is a finite ``float`` and ``reason is None``.
      * ``status == UNDEFINED`` -> ``value is None`` and ``reason`` is an
        ``UndefinedReason``.

    ``metadata`` is defensively copied into an immutable mapping so a computed
    result is fully immutable and independently auditable.
    """

    name: str
    value: float | None
    status: MetricStatus
    reason: UndefinedReason | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("name cannot be empty")
        if not isinstance(self.status, MetricStatus):
            raise ValueError("status must be a MetricStatus")

        if self.status is MetricStatus.OK:
            # bool is a subclass of int/float-adjacent; reject it explicitly.
            if isinstance(self.value, bool) or not isinstance(self.value, float):
                raise ValueError("OK result requires a float value")
            if not math.isfinite(self.value):
                raise ValueError("OK result value must be finite")
            if self.reason is not None:
                raise ValueError("OK result must not carry a reason")
        else:  # UNDEFINED
            if self.value is not None:
                raise ValueError("UNDEFINED result must have value=None")
            if not isinstance(self.reason, UndefinedReason):
                raise ValueError("UNDEFINED result requires an UndefinedReason")

        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(
                self, "metadata", MappingProxyType(dict(self.metadata))
            )

    # Convenience constructors keep metric code honest about the invariants.
    @classmethod
    def ok(
        cls, name: str, value: float, metadata: Mapping[str, Any]
    ) -> RelativeValueResult:
        """Build an OK result with a finite float value."""
        return cls(
            name=name,
            value=value,
            status=MetricStatus.OK,
            reason=None,
            metadata=metadata,
        )

    @classmethod
    def undefined(
        cls, name: str, reason: UndefinedReason, metadata: Mapping[str, Any]
    ) -> RelativeValueResult:
        """Build an explicit UNDEFINED result carrying its reason."""
        return cls(
            name=name,
            value=None,
            status=MetricStatus.UNDEFINED,
            reason=reason,
            metadata=metadata,
        )
