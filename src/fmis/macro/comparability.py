"""When two measurements may be placed side by side, and when they may not.

**This is a refusal mechanism, not a formatter.** A cross-asset page's
characteristic failure is not a crash; it is two numbers printed in one column
that mean different things. *"BTC +2.1%, S&P 500 +0.4%"* looks like one
comparison and is two, if the first is twenty-four hours and the second five
weeks. *"US10Y +2.38%"* beside *"Gold +2.38%"* looks like agreement between two
markets and is a category error. Neither of those raises anything.

So comparability is made an explicit, computed value rather than a convention the
renderer is trusted to observe. Two measurements are comparable exactly when
**every** component of their `ComparabilityKey` matches:

    quantity kind          a yield difference is not a price return
    quote unit             a return in EUR silently contains EUR/USD
    observation interval   24 hourly bars and 24 daily bars are not one window
    horizon                a 5-observation move is not a 21-observation move
    metric                 a correlation is not a return

Any mismatch produces a `NotComparable` naming **every** component that differs —
not the first one found. A reader told only that units differ will change the
units and be refused again for the interval; a reader told both learns what the
comparison would actually require.

**Nothing here is a threshold and nothing is approximate.** Each component is
compared for exact equality. There is no tolerance on the interval, no
"close enough" on the horizon, and no rule that two units are compatible because
they look similar — `"index points"` and `"index points (Jan 2006 = 100)"` are
different units, and the S&P and the broad dollar index are not on one scale
merely because both are called an index.

This module holds no arithmetic and no market quantity: it decides only whether a
comparison is permitted, never what the comparison would say.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from fmis.market_pulse import QuantityKind

__all__ = [
    "NotComparableReason",
    "ComparabilityKey",
    "Comparability",
    "compare_keys",
    "compare_for_correlation",
    "COMPARABILITY_RULE",
    "CORRELATION_COMPARABILITY_RULE",
]

#: Printed wherever a refusal appears, so a reader meets the rule rather than
#: inferring it from an absence.
COMPARABILITY_RULE = (
    "Two measurements are placed side by side only when they are the same kind "
    "of quantity, in the same unit, measured on the same observation interval, "
    "over the same horizon, by the same metric. Any difference in any one of "
    "those makes the comparison a different question than the one the column "
    "header asks, so it is refused and the difference is named."
)


class NotComparableReason(Enum):
    """Exactly which component of a comparison does not match.

    A closed vocabulary, one member per component of `ComparabilityKey`, so a
    refusal is a machine-readable fact a later consumer can act on rather than a
    sentence it would have to parse.
    """

    #: One side is a price-like level and the other is a rate. A percentage
    #: return and a basis-point difference are not two values of one quantity.
    DIFFERENT_QUANTITY_KIND = "different_quantity_kind"
    #: The two levels are denominated in different things, so a return on one
    #: contains an exchange rate or a rebasing the other does not.
    DIFFERENT_QUOTE_UNIT = "different_quote_unit"
    #: The two series are sampled at different cadences. Twenty-four hourly bars
    #: and twenty-four daily bars are the same *count* over windows differing by
    #: a factor of twenty-four.
    DIFFERENT_OBSERVATION_INTERVAL = "different_observation_interval"
    #: The two measurements span different numbers of observations.
    DIFFERENT_HORIZON = "different_horizon"
    #: The two numbers were produced by different functions.
    DIFFERENT_METRIC = "different_metric"


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a str, got {type(value).__name__}")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must not be blank")
    return stripped


@dataclass(frozen=True, slots=True)
class ComparabilityKey:
    """Everything that must match for two measurements to be comparable.

    Frozen and hashable, so grouping comparable measurements is a dictionary
    lookup rather than a nest of conditionals — which is what keeps the rule in
    one place instead of re-implemented at every call site that wants a column.

    **Every field is load-bearing and none has a default.** A key that could be
    constructed without stating its interval would let a caller omit the one
    component that separates a week of crypto from eight months of equities.
    """

    quantity_kind: QuantityKind
    quote_unit: str
    observation_interval: str
    horizon_id: str
    metric: str

    def __post_init__(self) -> None:
        if not isinstance(self.quantity_kind, QuantityKind):
            raise TypeError(
                f"quantity_kind must be a QuantityKind, got "
                f"{type(self.quantity_kind).__name__}"
            )
        for name in ("quote_unit", "observation_interval", "horizon_id", "metric"):
            object.__setattr__(self, name, _text(getattr(self, name), name))

    @property
    def label(self) -> str:
        """One line naming the comparison this key defines."""
        return (
            f"{self.metric} of a {self.quantity_kind.value} level in "
            f"{self.quote_unit}, over {self.horizon_id} on {self.observation_interval} "
            "observations"
        )


@dataclass(frozen=True, slots=True)
class Comparability:
    """Whether two keys may be compared, and every reason they may not.

    `reasons` is empty exactly when `is_comparable` is true; the constructor
    proves it, so there is no way to build a verdict that permits a comparison
    while carrying an objection to it.
    """

    is_comparable: bool
    reasons: tuple[NotComparableReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.is_comparable, bool):
            raise TypeError(
                f"is_comparable must be a bool, got "
                f"{type(self.is_comparable).__name__}"
            )
        reasons = tuple(self.reasons)
        for reason in reasons:
            if not isinstance(reason, NotComparableReason):
                raise TypeError(
                    "reasons must hold NotComparableReason values, got "
                    f"{type(reason).__name__}"
                )
        if len(set(reasons)) != len(reasons):
            raise ValueError(
                f"a component is named twice as a reason: {reasons!r}; one "
                "component has one verdict"
            )
        if self.is_comparable and reasons:
            raise ValueError(
                "a comparison cannot be permitted while carrying reasons it is "
                "refused"
            )
        if not self.is_comparable and not reasons:
            raise ValueError(
                "a comparison cannot be refused for no stated reason; a refusal "
                "a reader cannot act on is worse than no refusal"
            )
        object.__setattr__(self, "reasons", reasons)

    def explain(self) -> str:
        """One sentence a page can print. Empty string when comparable."""
        if self.is_comparable:
            return ""
        return "not comparable: " + ", ".join(
            reason.value.replace("_", " ") for reason in self.reasons
        )


#: The component checks, in the order a refusal lists them. A tuple rather than a
#: chain of ``if``s so that adding a component to `ComparabilityKey` without
#: adding its check here is a visible omission in one place.
_CHECKS: tuple[tuple[str, NotComparableReason], ...] = (
    ("quantity_kind", NotComparableReason.DIFFERENT_QUANTITY_KIND),
    ("quote_unit", NotComparableReason.DIFFERENT_QUOTE_UNIT),
    (
        "observation_interval",
        NotComparableReason.DIFFERENT_OBSERVATION_INTERVAL,
    ),
    ("horizon_id", NotComparableReason.DIFFERENT_HORIZON),
    ("metric", NotComparableReason.DIFFERENT_METRIC),
)


#: The correlation rule's checks — `_CHECKS` without the quote unit. See
#: `compare_for_correlation` for why the unit is dropped and why nothing else is.
_CORRELATION_CHECKS: tuple[tuple[str, NotComparableReason], ...] = tuple(
    entry for entry in _CHECKS if entry[0] != "quote_unit"
)

#: Printed above a correlation, so the weaker rule is visible rather than
#: looking like an oversight next to `COMPARABILITY_RULE`.
CORRELATION_COMPARABILITY_RULE = (
    "A correlation is computed on simple returns, which are ratios and "
    "therefore carry no unit. Two markets priced in different currencies can "
    "still be correlated, and requiring one unit would refuse every genuine "
    "cross-asset comparison this page exists to make. Every other requirement "
    "stands: the two series must be the same kind of quantity, sampled at the "
    "same interval, over the same horizon, by the same metric."
)


def _verdict(
    left: ComparabilityKey,
    right: ComparabilityKey,
    checks: tuple[tuple[str, NotComparableReason], ...],
) -> Comparability:
    for name, side in (("left", left), ("right", right)):
        if not isinstance(side, ComparabilityKey):
            raise TypeError(
                f"{name} must be a ComparabilityKey, got {type(side).__name__}"
            )
    reasons = tuple(
        reason
        for field, reason in checks
        if getattr(left, field) != getattr(right, field)
    )
    return Comparability(is_comparable=not reasons, reasons=reasons)


def compare_keys(left: ComparabilityKey, right: ComparabilityKey) -> Comparability:
    """Decide whether two measurements may be placed side by side by magnitude.

    The rule for a **ranking or a difference** — where the two numbers appear in
    one column and a reader compares how big they are. Every component must
    match, including the unit; see `COMPARABILITY_RULE`.

    Returns a verdict naming **every** mismatched component, never just the
    first. Symmetric: swapping the arguments produces an equal verdict, because
    comparability is a property of the pair rather than of an order.

    Raises:
        TypeError: either argument is not a `ComparabilityKey`.
    """
    return _verdict(left, right, _CHECKS)


def compare_for_correlation(
    left: ComparabilityKey, right: ComparabilityKey
) -> Comparability:
    """Decide whether two series may be **correlated**. Weaker, and deliberately.

    **The unit requirement is dropped, and only the unit.** A Pearson correlation
    of simple returns is scale-invariant by construction: multiplying either
    series by any positive constant leaves the value unchanged, which is exactly
    what changing a currency or rebasing an index does. Refusing to correlate the
    S&P with Bitcoin because one is quoted in index points and the other in USDT
    would refuse the whole cross-asset question on a technicality that the
    arithmetic does not care about.

    **Nothing else is dropped, and the quantity kind least of all.** A yield's
    *simple return* — 4.30 divided by 4.20 — is a ratio of two rates, and
    correlating it against an equity index's return would put two different
    constructions in one number. A yield's honest co-movement measure is built on
    its basis-point changes, which this build does not yet compute a correlation
    over; until it does, the pair is refused and told why rather than answered
    with the wrong construction.

    Raises:
        TypeError: either argument is not a `ComparabilityKey`.
    """
    return _verdict(left, right, _CORRELATION_CHECKS)
