"""The context envelope and the deterministic identity-mismatch contract.

A `ContextualSeries` is an ordered payload plus the `SeriesIdentity` it belongs
to. The identity is stored **once**, and the payload is exactly what the
context-free function that produced it returned — unchanged, untouched, and never
read by anything here.

That separation is the whole design. Identity sits *beside* the values rather than
*inside* them, so it structurally cannot reach the arithmetic: no analytical
function ever sees the envelope, and no element ever grows an identity field.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from fmis.data import SeriesIdentity

__all__ = [
    "ContextualSeries",
    "SeriesContextError",
    "SeriesIdentityMismatchError",
    "require_same_identity",
]

T = TypeVar("T")


class SeriesContextError(Exception):
    """Base class for every series-context failure.

    Follows the established package-error convention — `IngestError`,
    `RelativeValueError` — so a caller can catch this layer's failures as a group.
    """


class SeriesIdentityMismatchError(SeriesContextError, ValueError):
    """Two or more subjects describe different analytical series.

    Also a `ValueError`, matching `SeriesDecodeError(IngestError, ValueError)` and
    `NotAlignedError(RelativeValueError, ValueError)`, so existing callers that
    catch `ValueError` at a boundary keep working.

    Raised — never warned, never repaired, never resolved by picking one side.
    Combining two series is not a thing this layer knows how to do correctly, so it
    refuses rather than guessing, which is ADR-0005's rule applied to identity.
    """


@dataclass(frozen=True, slots=True)
class ContextualSeries(Generic[T]):
    """An ordered payload and the one `SeriesIdentity` it belongs to.

    Exactly two fields.

    ``identity`` is the series this payload came from — stored **once for the whole
    series**, not once per element. A history of two hundred snapshots holds one
    identity object, and every stage of a pipeline carries that same object forward
    by reference, so there is no copy anywhere to fall out of step.

    ``values`` is the payload, normalised to a tuple so the envelope is immutable.
    It is **exactly** what the corresponding context-free function returned. Nothing
    here inspects, filters, reorders, validates or interprets it — a
    `ContextualSeries` of trend snapshots and the bare tuple of trend snapshots hold
    the same facts in the same order.

    **Identity never participates in a calculation.** No analytical function in the
    repository receives an envelope; the wrappers unwrap, delegate, and re-wrap. So
    adding context cannot change a result, and that is proved rather than asserted:
    the equivalence tests compare context-aware output against context-free output
    across every fixture class.

    **Equality is structural**, and usefully separable: two envelopes are equal only
    if *both* identity and payload are equal, while ``a.values == b.values`` still
    compares the analytics alone. That is what makes two instruments' identical
    histories distinguishable — the measured risk this contract exists to close.

    ``values`` is deliberately not hashable-constrained: the envelope is frozen, but
    a payload element need not be, so `ContextualSeries` is hashable exactly when its
    payload is. Every payload this repository produces today is hashable.

    Deliberately absent: any per-element identity, any mutable metadata mapping, any
    provenance, any default identity, and any method that combines two series. The
    last one is the point — combining is `require_same_identity`'s job, and it
    refuses more often than it agrees.
    """

    identity: SeriesIdentity
    values: tuple[T, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, SeriesIdentity):
            raise TypeError(
                "identity must be a SeriesIdentity, got "
                f"{type(self.identity).__name__}"
            )
        if isinstance(self.values, (str, bytes)) or not isinstance(
            self.values, Iterable
        ):
            raise TypeError(
                "values must be an iterable of series elements, got "
                f"{type(self.values).__name__}"
            )
        # Accept any non-string iterable at construction; store an immutable
        # tuple, matching `CandleSeries`' own normalisation of `candles`.
        object.__setattr__(self, "values", tuple(self.values))

    def __len__(self) -> int:
        """The number of payload elements. An empty series is legal and keeps its identity."""
        return len(self.values)


def _identity_of(subject: object, *, position: int) -> SeriesIdentity:
    """The identity of one subject — the one authoritative accessor.

    Accepts anything exposing an ``identity`` attribute of the right type, which is
    what makes `require_same_identity` work uniformly over a `CandleSeries` (via its
    projection) and a `ContextualSeries` (via its field). That is deliberate: a
    future candle-consuming layer must check candles against derived facts, and it
    should not need two different checks to do it.

    Deliberately **private**. A public accessor would invite callers to read an
    identity and compare it by hand, which is the second implementation of one rule
    this layer exists to prevent.
    """
    identity = getattr(subject, "identity", None)
    if not isinstance(identity, SeriesIdentity):
        raise TypeError(
            f"subjects[{position}] must expose a SeriesIdentity 'identity', got "
            f"{type(subject).__name__}"
        )
    return identity


def require_same_identity(*subjects: object) -> SeriesIdentity:
    """Require every subject to describe the same analytical series.

    Args:
        *subjects: two or more identity-bearing objects — any mix of `CandleSeries`
            (whose ``identity`` is a projection) and `ContextualSeries`.

    Returns:
        The single `SeriesIdentity` they all share, so a caller can bind it to the
        result it is about to build instead of re-reading one of the inputs.

    Raises:
        TypeError: no subject was supplied, or a subject exposes no `SeriesIdentity`.
        SeriesIdentityMismatchError: two subjects describe different series.

    This is **the one place** the contract is enforced, which is what makes it
    mutation-testable: a single named function is either called or it is not.

    Comparison is structural and exact (`SeriesIdentity.__eq__`). No case folding,
    no trimming, no alias translation — so ``"BTCUSDT"``/``"btcusdt"`` and
    ``"4h"``/``"4H"`` are mismatches, and the contract **over-rejects** rather than
    silently unifying. Over-rejection is safe; under-rejection is the silent mixing
    this exists to prevent.

    The first subject is the reference, so the error names the offending position
    rather than declaring one of two equals wrong. Comparison is against that
    reference, not pairwise, so the error is deterministic regardless of how many
    subjects disagree.

    Pure: nothing is stored, cached, registered or memoised, and there is no
    ambient "current series" anywhere in this package.
    """
    if not subjects:
        raise TypeError("require_same_identity needs at least one subject")

    reference = _identity_of(subjects[0], position=0)
    for position, subject in enumerate(subjects[1:], start=1):
        identity = _identity_of(subject, position=position)
        if identity != reference:
            raise SeriesIdentityMismatchError(
                f"subjects[{position}] has identity "
                f"{identity.symbol!r}/{identity.timeframe!r}, expected "
                f"{reference.symbol!r}/{reference.timeframe!r}"
            )
    return reference


def _carry(
    source: ContextualSeries[object], values: Sequence[object]
) -> ContextualSeries[object]:
    """Re-wrap a delegated result under the source's **own identity object**.

    Carries ``source.identity`` by reference — never rebuilt from its fields, never
    defaulted, never taken from anywhere else. A wrapper that reconstructed an
    equal identity would still pass every equality test while quietly severing the
    link to the series the payload actually came from, so the tests assert `is`,
    not `==`.

    Deliberately **private**: it is the propagation rule, and a public version would
    let a caller staple any identity onto any payload — exactly the substitution
    the contract forbids.
    """
    return ContextualSeries(identity=source.identity, values=tuple(values))
