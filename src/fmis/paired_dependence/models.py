"""Milestone CD's vocabulary. **Two verdicts, and neither of them is about trading.**

CD measures how dependent Milestone CA's paired admission-vs-control effects are
across economic assets. That produces two different kinds of statement and they
must not be merged:

* `DependenceVerdict` — *was the dependence measured well enough to be used?* It
  is a statement about this estimator on this panel, and its worst member says
  the estimator itself is unsuitable.
* `RequirementOutcome` — *given what was measured, can a +0.10 ATR admission
  experiment be designed at all?* It is a statement about Milestone CB's
  information requirement after CD's dependence is applied to it.

Neither vocabulary has a member that approves anything, and a hostile test
asserts `is_approved_for_trading` is `False` across every member of both.

**Why two new enums rather than CB's `DesignVerdict`.** `DesignVerdict` answers
"can this design resolve its effect" and its members (`ready`, `limited`,
`underpowered`, `misaligned_unit`, `insufficient_independence`, `not_measurable`)
are all statements about a *design*. CD's first question is about an *estimate* —
whether a correlation was identified — and `not_measurable` would flatten
"the panel cannot identify it" together with "the estimator is structurally
invalid", which is the exact distinction Milestone CC's residual estimator taught
this project to keep. `RequirementOutcome` is the smaller addition: it names the
four outcomes the milestone brief asks for, and `unreachable` has no
`DesignVerdict` equivalent because CB's `RequiredInformation.reachable` carries
that fact as a boolean on a path rather than as a verdict.

**The three counts that must never be confused**, given names here so that no
downstream module can quietly substitute one for another:

    rows          one paired observation: one admission, one family, one horizon
    admissions    one admitted instant — five rows, one per null family
    assets        one economic exposure — many admissions
"""

from __future__ import annotations

from enum import Enum
from typing import Any

__all__ = [
    "PairedDependenceError",
    "DependenceVerdict",
    "RequirementOutcome",
    "GroupingAxis",
    "Weighting",
    "require_text",
    "require_count",
    "require_probability",
]


class PairedDependenceError(ValueError):
    """Anything Milestone CD refuses. **Never raised to signal an absence.**

    A quantity that cannot be computed is reported as `None` with a stated
    reason; this exception is for malformed input and broken invariants only.
    """


class DependenceVerdict(Enum):
    """How well CD identified the dependence it set out to measure.

    Ordered from the strongest claim to the weakest, and the weakest is not
    "no dependence" — it is "this estimator should not be believed".
    """

    MEASURED = "measured"
    WEAKLY_IDENTIFIED = "weakly_identified"
    INCONCLUSIVE = "inconclusive"
    INVALID_ESTIMATOR = "invalid_estimator"

    @property
    def is_approved_for_trading(self) -> bool:
        """**Always False.** Asserted over the whole enum by a hostile test."""
        return False

    @property
    def earns_forward_test(self) -> bool:
        """**Always False.** A dependence measurement promotes nothing."""
        return False

    @property
    def says_nothing_about_the_hypothesis(self) -> bool:
        """**Always True.** CA's `NO_EDGE` is untouched by every member."""
        return True

    @property
    def is_usable_by_a_design(self) -> bool:
        """Whether a research design may quote this estimate as an input."""
        return self in (DependenceVerdict.MEASURED, DependenceVerdict.WEAKLY_IDENTIFIED)


class RequirementOutcome(Enum):
    """What CD's dependence does to Milestone CB's information requirement.

    `UNREACHABLE` is the member with no `DesignVerdict` equivalent and the one
    that matters: above a between-cluster correlation of ``1 / K*`` the effective
    cluster count saturates below the requirement, and **no universe of any size**
    satisfies it.
    """

    RESOLVABLE = "resolvable"
    UNDERPOWERED = "underpowered"
    UNREACHABLE = "unreachable"
    INCONCLUSIVE = "inconclusive"

    @property
    def is_approved_for_trading(self) -> bool:
        """**Always False.** Asserted over the whole enum by a hostile test."""
        return False

    @property
    def earns_forward_test(self) -> bool:
        """**Always False.**"""
        return False

    @property
    def says_nothing_about_the_hypothesis(self) -> bool:
        """**Always True.**"""
        return True


class GroupingAxis(Enum):
    """Which grouping a variance-component correlation is taken over.

    The **same** estimator applied on these two axes answers two different
    questions, and the milestone brief is explicit that they must not both be
    called "correlation" without saying which:

    * `ECONOMIC_ASSET` — group = one economic exposure, members = its admissions.
      Yields the **within-asset (intracluster) correlation** ``rho_w``: how much
      two admissions on the same asset co-vary. This is the number Milestone CB's
      design effect ``1 + (m - 1) * rho`` consumes.
    * `TIME_BLOCK` — group = one contemporaneous window, members = the per-asset
      mean paired effects inside it. Yields the **between-asset correlation**
      ``r_b``: how much two *different* assets' paired effects co-move at the same
      time. This is the number that caps the effective cluster count at ``1 / r_b``.
    """

    ECONOMIC_ASSET = "economic_asset"
    TIME_BLOCK = "time_block"

    @property
    def measures(self) -> str:
        return (
            "within-asset (intracluster) correlation of paired differences"
            if self is GroupingAxis.ECONOMIC_ASSET
            else "between-asset (cross-sectional) correlation of contemporaneous "
            "per-asset mean paired differences"
        )

    @property
    def member_unit(self) -> str:
        return (
            "one paired observation"
            if self is GroupingAxis.ECONOMIC_ASSET
            else "one (economic asset, time block) cell mean"
        )


class Weighting(Enum):
    """Whether a cell counts once or counts its observations.

    Pre-registered as a sensitivity dimension rather than chosen: equal weighting
    lets a one-observation asset move the estimate as far as a fifty-observation
    one, and observation weighting lets the busiest asset dominate. Neither is
    obviously right and CD reports both.
    """

    EQUAL_CELL = "equal_cell"
    OBSERVATION_COUNT = "observation_count"


def require_text(value: Any, field: str) -> str:
    """A non-empty string, or `PairedDependenceError`."""
    if not isinstance(value, str) or not value.strip():
        raise PairedDependenceError(f"{field} must be a non-empty string, got {value!r}")
    return value


def require_count(value: Any, field: str, *, minimum: int = 0) -> int:
    """A plain int at or above ``minimum``. **`True` is not 1 here.**"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise PairedDependenceError(f"{field} must be an int, got {value!r}")
    if value < minimum:
        raise PairedDependenceError(f"{field} must be at least {minimum}, got {value}")
    return value


def require_probability(value: Any, field: str) -> float:
    """A real number strictly inside (0, 1)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PairedDependenceError(f"{field} must be a real number, got {value!r}")
    number = float(value)
    if not 0.0 < number < 1.0:
        raise PairedDependenceError(
            f"{field} must lie strictly inside (0, 1), got {value!r}"
        )
    return number
