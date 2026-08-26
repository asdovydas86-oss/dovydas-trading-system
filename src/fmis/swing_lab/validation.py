"""Applying the frozen bar. **Every rule here was written before any result.**

`fmis.swing_lab.preregistration` states the criteria and the classification rules
in words and numbers; this module is those statements as code, and the two are
tied together by the digest. Nothing here chooses a threshold — every number it
compares against is read from the sealed pre-registration, so a number changed
here without changing the seal is a red test, and a number changed in both is a
visible diff.

**Three refusals this module makes that a looser one would not.**

1. **A post-hoc policy cannot be promoted.** Not "is unlikely to be" — cannot.
   `pre_registered` is the first criterion and it is decided by set membership in
   the sealed manifest, not by a flag a caller passes.
2. **A non-structural policy cannot be promoted.** The distance-only control in
   `fmis.swing_lab.nonstructural` exists to *falsify* the structural claim, and a
   control that could win the thing it is controlling for is not a control.
3. **The frictionless column cannot promote anything.** Every deciding criterion
   reads the sample measured under `DECIDING_COST_POLICY_ID`. BX showed costs
   move this strategy's expectancy by 0.723R per trade on average; a bar that can
   be cleared before friction is not a bar.

**Why a plateau is `all` and never `any`.** One positive point standing beside a
negative neighbour is precisely the spike BX found in its §10 sweep and refused,
and an `any` would report it as a plateau. `classify_plateau` therefore returns
`FRAGILE_SPIKE` for that shape by name, so a report cannot describe it as
"mostly positive across the neighbourhood".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Final

from fmis.swing_lab.metrics import VariantMetrics
from fmis.swing_lab.models import LabVerdict, SwingLabError
from fmis.swing_lab.geometry_verdict import Criterion, MAX_SINGLE_SYMBOL_SHARE
from fmis.swing_lab.preregistration import (
    MIN_PROFIT_FACTOR,
    SAMPLE_FLOOR,
    is_pre_registered,
)

__all__ = [
    "PlateauClass",
    "NeighbourReading",
    "PlateauReading",
    "classify_plateau",
    "CandidateAssessment",
    "assess_candidate",
    "criteria_index",
]


class PlateauClass(str, Enum):
    """§13's four outcomes, and the order of precedence between them.

    Precedence matters and is stated because two of these can look true at once:
    a primary point that is not positive *also* has failing neighbours, and
    calling that a `FRAGILE_SPIKE` would imply there was a spike. There is not —
    there is no edge — so `NO_EDGE` is tested first.
    """

    NOT_MEASURABLE = "not_measurable"
    NO_EDGE = "no_edge"
    FRAGILE_SPIKE = "fragile_spike"
    ROBUST_PLATEAU = "robust_plateau"

    @property
    def is_robust(self) -> bool:
        return self is PlateauClass.ROBUST_PLATEAU

    @property
    def statement(self) -> str:
        return _PLATEAU_STATEMENTS[self]


_PLATEAU_STATEMENTS: Final[dict[PlateauClass, str]] = {
    PlateauClass.NOT_MEASURABLE: (
        f"fewer than three neighbourhood points cleared the {SAMPLE_FLOOR}-trade "
        "floor; the plateau test could not be run, which is not a pass"
    ),
    PlateauClass.NO_EDGE: (
        "the primary point's cost-inclusive development expectancy is not "
        "positive, so there is no edge for a neighbourhood to support"
    ),
    PlateauClass.FRAGILE_SPIKE: (
        "the primary point is positive and at least one measurable neighbour is "
        "not; a result that survives at one threshold and dies at the next is "
        "the shape a fitted parameter makes"
    ),
    PlateauClass.ROBUST_PLATEAU: (
        "the primary point is positive and every measurable neighbour is "
        "positive too"
    ),
}

#: How many measurable points the neighbourhood needs before the shape means
#: anything. Two points cannot distinguish a plateau from a slope.
MIN_PLATEAU_POINTS: Final[int] = 3


@dataclass(frozen=True, slots=True)
class NeighbourReading:
    """One neighbourhood point: its policy, its threshold, and what it measured."""

    policy_id: str
    axis: str
    threshold: float
    is_primary: bool
    metrics: VariantMetrics

    @property
    def expectancy(self) -> Decimal | None:
        return self.metrics.expectancy_r.value

    @property
    def is_measurable(self) -> bool:
        return self.metrics.expectancy_r.value is not None

    def payload(self) -> dict[str, Any]:
        value = self.expectancy
        return {
            "policy_id": self.policy_id,
            "axis": self.axis,
            "threshold": self.threshold,
            "is_primary": self.is_primary,
            "measurable_trades": self.metrics.measurable_trades,
            "expectancy_r": None if value is None else str(value),
        }


@dataclass(frozen=True, slots=True)
class PlateauReading:
    """The classification, the rule that produced it, and every point behind it."""

    classification: PlateauClass
    detail: str
    readings: tuple[NeighbourReading, ...]

    @property
    def measurable(self) -> tuple[NeighbourReading, ...]:
        return tuple(item for item in self.readings if item.is_measurable)

    def payload(self) -> dict[str, Any]:
        return {
            "classification": self.classification.value,
            "statement": self.classification.statement,
            "detail": self.detail,
            "points": [item.payload() for item in self.readings],
        }


def _describe(readings: Sequence[NeighbourReading]) -> str:
    parts = []
    for item in readings:
        value = item.expectancy
        mark = "*" if item.is_primary else " "
        parts.append(
            f"{mark}{item.axis}={item.threshold:g} "
            + (
                f"{value:+.4f}R (n={item.metrics.measurable_trades})"
                if value is not None
                else f"— (n={item.metrics.measurable_trades}, below floor)"
            )
        )
    return "; ".join(parts)


def classify_plateau(readings: Sequence[NeighbourReading]) -> PlateauReading:
    """§13's rules, applied. **Deterministic, and stated before it was ever run.**

    ``readings`` must contain exactly one primary point — the classification is a
    statement *about* that point, and a neighbourhood with two centres or none is
    a caller error rather than a market condition.

    Raises:
        SwingLabError: the neighbourhood does not hold exactly one primary point.
    """
    primaries = [item for item in readings if item.is_primary]
    if not primaries:
        raise SwingLabError("a neighbourhood must hold a primary point, got none")
    # A policy can sit at the centre of BOTH axes of the cross, in which case it
    # appears once per axis. That is one point measured twice, not two points:
    # the readings must name the same policy and must agree, or the caller has
    # assembled a neighbourhood around two different centres.
    if len({item.policy_id for item in primaries}) != 1:
        raise SwingLabError(
            "a neighbourhood must hold exactly one primary POLICY, got "
            f"{sorted({item.policy_id for item in primaries})}"
        )
    values = {
        None if item.expectancy is None else str(item.expectancy) for item in primaries
    }
    if len(values) != 1:
        raise SwingLabError(
            f"the primary point {primaries[0].policy_id} reports different "
            f"measurements on different axes: {sorted(values, key=str)}"
        )
    primary = primaries[0]
    detail = _describe(readings)
    measurable = [item for item in readings if item.is_measurable]

    if len(measurable) < MIN_PLATEAU_POINTS or not primary.is_measurable:
        return PlateauReading(PlateauClass.NOT_MEASURABLE, detail, tuple(readings))
    if primary.expectancy is None or primary.expectancy <= 0:
        return PlateauReading(PlateauClass.NO_EDGE, detail, tuple(readings))
    if all(item.expectancy > 0 for item in measurable):
        return PlateauReading(PlateauClass.ROBUST_PLATEAU, detail, tuple(readings))
    return PlateauReading(PlateauClass.FRAGILE_SPIKE, detail, tuple(readings))


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    """One policy judged against every frozen criterion, with its verdict.

    **Recomputable.** Every criterion carries the measurement that decided it, so
    a reader holding the artifact can rebuild the verdict rather than trust a
    report's summary of it.
    """

    policy_id: str
    verdict: LabVerdict
    criteria: tuple[Criterion, ...]
    plateau: PlateauReading | None
    cost_policy_id: str

    @property
    def blocking(self) -> tuple[Criterion, ...]:
        return tuple(item for item in self.criteria if item.passed is not True)

    @property
    def statement(self) -> str:
        if self.verdict is LabVerdict.CANDIDATE_FOR_FORWARD_TEST:
            return (
                f"{self.policy_id}: every pre-registered criterion met under "
                f"{self.cost_policy_id}. Worth testing forward — this is NOT "
                "approval to trade."
            )
        names = ", ".join(item.name for item in self.blocking)
        return f"{self.policy_id}: {self.verdict.value} — blocked by {names}."

    def payload(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "verdict": self.verdict.value,
            "statement": self.statement,
            "cost_policy_id": self.cost_policy_id,
            "criteria": [
                {
                    "name": item.name,
                    "requirement": item.requirement,
                    "passed": item.passed,
                    "observed": item.observed,
                }
                for item in self.criteria
            ],
            "plateau": None if self.plateau is None else self.plateau.payload(),
        }


def _sample_criterion(name: str, sample: str, metrics: VariantMetrics) -> Criterion:
    """A sample-size requirement, whose failure is ``None`` and never ``False``.

    A cohort below the floor established nothing, and recording that as a
    measured `False` would make the verdict read `REJECTED` — "this lost money" —
    about a policy nobody has measured. `LabVerdict.INCONCLUSIVE` already owns
    that meaning and this preserves the distinction.
    """
    enough = metrics.measurable_trades >= SAMPLE_FLOOR
    return Criterion(
        name=name,
        requirement=f"at least {SAMPLE_FLOOR} measurable trades on {sample}",
        passed=True if enough else None,
        observed=f"{metrics.measurable_trades} measurable trades",
    )


def _expectancy_criterion(
    name: str, sample: str, metrics: VariantMetrics, *, strictly_positive: bool
) -> Criterion:
    value = metrics.expectancy_r.value
    comparison = "positive" if strictly_positive else "non-negative"
    requirement = (
        f"a {comparison} COST-INCLUSIVE expectancy on {sample}"
    )
    if value is None:
        return Criterion(
            name=name,
            requirement=requirement,
            passed=None,
            observed=f"no expectancy ({metrics.expectancy_r.reason})",
        )
    passed = value > 0 if strictly_positive else value >= 0
    return Criterion(
        name=name,
        requirement=requirement,
        passed=passed,
        observed=f"{value:+.4f}R over n={metrics.expectancy_r.n}",
    )


def assess_candidate(
    *,
    policy_id: str,
    is_structural: bool,
    manifest_digest_matches: bool,
    development: VariantMetrics,
    validation: VariantMetrics,
    holdout: VariantMetrics,
    development_symbol_share: Decimal | None,
    plateau: PlateauReading | None,
    no_lookahead_proven: bool,
    cost_policy_id: str,
) -> CandidateAssessment:
    """Judge one policy against the sealed criteria. **No criterion is optional.**

    Every metric argument must already be measured under ``cost_policy_id``; the
    caller is the only layer that knows which scenario it selected, and passing
    frictionless metrics here would produce a verdict that reads as cost-inclusive
    when it is not. `fmis.swing_lab.validation_study` asserts the scenario before
    calling, so the mistake is caught rather than documented.

    Raises:
        SwingLabError: the metrics were labelled for different policies, which
            would mean three unrelated samples were judged as one variant.
    """
    labels = {development.label, validation.label, holdout.label}
    if any(not label.startswith(policy_id) for label in labels):
        raise SwingLabError(
            f"metrics labelled {sorted(labels)} were handed to an assessment of "
            f"{policy_id!r}; three samples of different variants cannot be one "
            "verdict"
        )

    criteria: list[Criterion] = [
        Criterion(
            name="pre_registered",
            requirement=(
                "the policy is sealed in the pre-registration AND the study's "
                "manifest carries the live pre-registration digest"
            ),
            passed=is_pre_registered(policy_id) and manifest_digest_matches,
            observed=(
                f"sealed={is_pre_registered(policy_id)}, "
                f"digest_matches={manifest_digest_matches}"
            ),
        ),
        Criterion(
            name="structural",
            requirement=(
                "the policy selects real structural levels; the non-structural "
                "control is measured and reported but never promoted"
            ),
            passed=is_structural,
            observed=(
                "selects structural levels"
                if is_structural
                else "NON-STRUCTURAL control — invents its stop and target and "
                "is permanently ineligible"
            ),
        ),
        _sample_criterion("development_sample", "development", development),
        _sample_criterion("validation_sample", "validation", validation),
        _sample_criterion("holdout_sample", "the holdout", holdout),
        _expectancy_criterion(
            "development_expectancy", "development", development, strictly_positive=True
        ),
        _expectancy_criterion(
            "validation_expectancy", "validation", validation, strictly_positive=False
        ),
        _expectancy_criterion(
            "holdout_expectancy", "the holdout", holdout, strictly_positive=False
        ),
    ]

    factor = development.profit_factor.value
    criteria.append(
        Criterion(
            name="profit_factor",
            requirement=(
                f"a cost-inclusive profit factor above {MIN_PROFIT_FACTOR:g} on "
                "development"
            ),
            passed=None if factor is None else factor > Decimal(str(MIN_PROFIT_FACTOR)),
            observed=(
                f"no profit factor ({development.profit_factor.reason})"
                if factor is None
                else f"{factor:.4f}"
            ),
        )
    )

    worst = development.max_drawdown.max_drawdown_r
    total = development.total_r
    criteria.append(
        Criterion(
            name="drawdown_recovered",
            requirement=(
                "the worst peak-to-trough decline on development is smaller "
                "than the total R gained"
            ),
            # Below the floor the total is a sum of too few trades to mean
            # anything, so the comparison is not evaluable rather than failed —
            # the same reading `fmis.swing_lab.geometry_verdict` takes.
            passed=(
                None
                if development.measurable_trades < SAMPLE_FLOOR
                else total > worst
            ),
            observed=(
                f"total {total:+.2f}R against a worst decline of {worst:.2f}R"
            ),
        )
    )

    criteria.append(
        Criterion(
            name="symbol_concentration",
            requirement=(
                f"no single symbol contributes more than "
                f"{MAX_SINGLE_SYMBOL_SHARE:.0%} of gross absolute R on development"
            ),
            passed=(
                None
                if development_symbol_share is None
                else development_symbol_share <= Decimal(str(MAX_SINGLE_SYMBOL_SHARE))
            ),
            observed=(
                "no share could be computed — no measurable trade carried R"
                if development_symbol_share is None
                else f"largest symbol carries {development_symbol_share:.1%}"
            ),
        )
    )

    criteria.append(
        Criterion(
            name="parameter_plateau",
            requirement=(
                "the pre-declared neighbourhood classifies as ROBUST_PLATEAU; a "
                "FRAGILE_SPIKE is rejected however good its centre looks"
            ),
            passed=(
                None
                if plateau is None or plateau.classification is PlateauClass.NOT_MEASURABLE
                else plateau.classification.is_robust
            ),
            observed=(
                "no neighbourhood is declared for this policy"
                if plateau is None
                else f"{plateau.classification.value.upper()} — {plateau.detail}"
            ),
        )
    )

    criteria.append(
        Criterion(
            name="no_lookahead",
            requirement=(
                "the future-mutation suite passed for this study's capture: "
                "every candidate and every plan is byte-identical when all bars "
                "after the decision instant are replaced"
            ),
            passed=no_lookahead_proven,
            observed=(
                "mutation suite passed" if no_lookahead_proven
                else "NOT PROVEN for this capture"
            ),
        )
    )

    frozen = tuple(criteria)
    if all(item.passed is True for item in frozen):
        verdict = LabVerdict.CANDIDATE_FOR_FORWARD_TEST
    elif any(item.passed is False for item in frozen):
        verdict = LabVerdict.REJECTED
    else:
        # Nothing measured false; the blockers are all unevaluable. That is
        # `INCONCLUSIVE` — nothing was established either way — and calling it
        # REJECTED would report a loss nobody measured.
        verdict = LabVerdict.INCONCLUSIVE

    return CandidateAssessment(
        policy_id=policy_id,
        verdict=verdict,
        criteria=frozen,
        plateau=plateau,
        cost_policy_id=cost_policy_id,
    )


def criteria_index(assessments: Sequence[CandidateAssessment]) -> Mapping[str, int]:
    """How many policies each criterion blocked. **A study-level diagnosis.**

    A milestone where every rejection cites `development_expectancy` learned
    something different from one where they all cite `parameter_plateau`, and the
    difference is invisible in a per-policy table.
    """
    tally: dict[str, int] = {}
    for assessment in assessments:
        for item in assessment.blocking:
            tally[item.name] = tally.get(item.name, 0) + 1
    return dict(sorted(tally.items()))
