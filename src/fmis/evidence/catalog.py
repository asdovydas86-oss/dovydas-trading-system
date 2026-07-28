"""The catalog of evidence concepts this repository genuinely interprets today.

Every entry below corresponds to something that already produces a
*classification* somewhere in the system. Nothing here is aspirational, and a
calculation alone was not enough to earn a place: a value that is computed,
reported, and never classified is a measurement, not evidence.

Applying that rule at the time of writing left six descriptors, all of them
mirroring an observation that `fmis.decision_support` actually emits. Several
families are therefore empty, which records the real state of the system rather
than hiding it:

  * **VOLUME** — relative volume is computed (`fmis.features.volume`), but
    ADR-0010 deliberately deferred classifying it. A ratio with no interpretation
    is not yet evidence.
  * **VOLATILITY** — ATR and ATR-percent-of-close are reported as raw values;
    `VolatilityEvidence` holds no classified observation at all.
  * **RELATIVE_STRENGTH** — the relative-value metrics are restated from the RVE
    unchanged; `RelativeValueEvidence` carries numbers and undefined reasons, and
    classifies none of them. There is no relative-value alignment to describe.
  * **MARKET_STRUCTURE, LIQUIDITY, MACRO, NEWS, SENTIMENT** — nothing computes
    or interprets these yet.

The catalog is a module-level immutable tuple built once at import, validated on
the way in. There is no mutable registry and no plugin mechanism: adding a
descriptor is a source change with a test, which is what keeps the vocabulary
reviewable.

This module does **not** import `fmis.decision_support`; the correspondence above
is a deliberate design constraint verified by tests, not a runtime dependency.
"""

from __future__ import annotations

from fmis.evidence.descriptor import EvidenceDescriptor
from fmis.evidence.families import EvidenceFamily

__all__ = ["descriptors", "descriptors_for", "find"]


def _validated(
    candidates: tuple[EvidenceDescriptor, ...],
) -> tuple[EvidenceDescriptor, ...]:
    """Reject duplicates, then return the descriptors in canonical order.

    Names are unique **globally**, not merely within a family. That is the
    stronger rule and it subsumes uniqueness of the (family, name) pair: a name
    that identifies two concepts is ambiguous however they are grouped, and a
    consumer looking one up by name would silently get whichever came first.

    Canonical order is family-declaration order, then name. Sorting rather than
    trusting source order means the catalog reads the same however the literals
    below happen to be arranged.
    """
    seen: dict[str, EvidenceDescriptor] = {}
    for candidate in candidates:
        existing = seen.get(candidate.name)
        if existing is not None:
            raise ValueError(
                f"duplicate descriptor name {candidate.name!r} "
                f"(families {existing.family.value!r} and {candidate.family.value!r})"
            )
        seen[candidate.name] = candidate

    family_order = {family: index for index, family in enumerate(EvidenceFamily)}
    return tuple(sorted(candidates, key=lambda d: (family_order[d.family], d.name)))


#: Descriptors for concepts `fmis.decision_support` classifies today. The names
#: match the observation keys it emits, so the vocabulary stays checkable against
#: the implementation rather than drifting into an independent naming scheme.
_CATALOG: tuple[EvidenceDescriptor, ...] = _validated(
    (
        EvidenceDescriptor(
            family=EvidenceFamily.TREND,
            name="price_vs_ema_fast",
            description=(
                "Where the latest close sits relative to the fast exponential "
                "moving average."
            ),
        ),
        EvidenceDescriptor(
            family=EvidenceFamily.TREND,
            name="price_vs_ema_slow",
            description=(
                "Where the latest close sits relative to the slow exponential "
                "moving average."
            ),
        ),
        EvidenceDescriptor(
            family=EvidenceFamily.TREND,
            name="ema_fast_vs_ema_slow",
            description=(
                "Where the fast exponential moving average sits relative to the "
                "slow one."
            ),
        ),
        EvidenceDescriptor(
            family=EvidenceFamily.MOMENTUM,
            name="rsi_zone",
            description=(
                "Which bounded band the Relative Strength Index reading falls in."
            ),
        ),
        EvidenceDescriptor(
            family=EvidenceFamily.MOMENTUM,
            name="macd_vs_signal",
            description=(
                "Where the MACD line sits relative to its own signal line."
            ),
        ),
        EvidenceDescriptor(
            family=EvidenceFamily.MOMENTUM,
            name="macd_histogram",
            description=(
                "The sign of the MACD histogram, the gap between the MACD line "
                "and its signal line."
            ),
        ),
    )
)


def descriptors() -> tuple[EvidenceDescriptor, ...]:
    """Every catalogued descriptor, in canonical order.

    The returned tuple is the catalog itself; it is immutable, so a caller cannot
    alter the vocabulary by holding it.
    """
    return _CATALOG


def descriptors_for(family: EvidenceFamily) -> tuple[EvidenceDescriptor, ...]:
    """Descriptors in one family, in canonical order — empty if none exist yet.

    An empty result is a real answer: it says the system does not interpret that
    family today, and is not an error to be worked around.
    """
    if not isinstance(family, EvidenceFamily):
        raise TypeError(
            f"family must be an EvidenceFamily, got {type(family).__name__}"
        )
    return tuple(d for d in _CATALOG if d.family is family)


def find(name: str) -> EvidenceDescriptor | None:
    """The descriptor with this exact name, or ``None`` if it is not catalogued.

    Matching is exact: names are required to be normalized at construction, so
    there is no case or whitespace variation to accommodate here.
    """
    if not isinstance(name, str):
        raise TypeError(f"name must be a str, got {type(name).__name__}")
    for descriptor in _CATALOG:
        if descriptor.name == name:
            return descriptor
    return None
