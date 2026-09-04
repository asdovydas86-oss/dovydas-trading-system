"""Milestone CD's verdict. **Decided by the sealed rules, in the sealed order.**

The order matters and is part of the seal. Calibration is read **first** and
short-circuits everything after it: an estimator that cannot recover a dependence
it was *given* has not earned the right to report one it *found*, however clean
the real numbers look. Milestone CC believed a number for a whole milestone
before a simulation showed the estimator could never have produced any other one,
and this ordering is that lesson made executable.

After calibration the rules read the **interval** before the point estimate.
A point estimate that sits below the saturation threshold while its interval
reaches above it does not mean the requirement is finite; it means the panel
cannot say. Reading the point first would convert that ignorance into a design
input, which is the specific error the whole milestone exists to avoid.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from fmis.paired_dependence.integration import RequirementAssessment
from fmis.paired_dependence.models import (
    DependenceVerdict,
    GroupingAxis,
    PairedDependenceError,
)
from fmis.paired_dependence.uncertainty import DependenceInterval

__all__ = [
    "CalibrationReading",
    "CalibrationOutcome",
    "FloorReading",
    "CdAssessment",
    "calibrate",
    "check_floors",
    "assess_cd",
]


@dataclass(frozen=True, slots=True)
class CalibrationReading:
    """One synthetic scenario's expectation against what the estimator returned."""

    scenario_id: str
    axis: GroupingAxis
    expected: float | None
    mean_estimate: float | None
    tolerance: float
    replicates: int
    within_tolerance: bool | None

    def payload(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "axis": self.axis.value,
            "expected": self.expected,
            "mean_estimate": self.mean_estimate,
            "tolerance": self.tolerance,
            "replicates": self.replicates,
            "deviation": (
                None
                if self.expected is None or self.mean_estimate is None
                else abs(self.mean_estimate - self.expected)
            ),
            "within_tolerance": self.within_tolerance,
        }


@dataclass(frozen=True, slots=True)
class CalibrationOutcome:
    """Whether the estimator may be believed on real data at all."""

    readings: tuple[CalibrationReading, ...]
    ordering_reproduced: bool
    ordering_detail: tuple[tuple[str, float | None], ...]
    passed: bool
    reasoning: str

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(
            f"{item.scenario_id}/{item.axis.value}"
            for item in self.readings
            if item.within_tolerance is False
        )

    def payload(self) -> dict[str, Any]:
        return {
            "readings": [item.payload() for item in self.readings],
            "ordering_reproduced": self.ordering_reproduced,
            "ordering_detail": [
                {"scenario_id": name, "mean_estimate": value}
                for name, value in self.ordering_detail
            ],
            "failures": list(self.failures),
            "passed": self.passed,
            "reasoning": self.reasoning,
        }


@dataclass(frozen=True, slots=True)
class FloorReading:
    """One sample floor, its requirement and what the panel actually supplied."""

    name: str
    required: int
    observed: int
    met: bool

    def payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required": self.required,
            "observed": self.observed,
            "met": self.met,
        }


@dataclass(frozen=True, slots=True)
class CdAssessment:
    """Milestone CD's scientific verdict, with every input that decided it."""

    verdict: DependenceVerdict
    calibration: CalibrationOutcome
    floors: tuple[FloorReading, ...]
    between_asset: DependenceInterval
    within_asset: DependenceInterval
    requirement: RequirementAssessment
    reasoning: str

    @property
    def unmet_floors(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.floors if not item.met)

    def payload(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "is_approved_for_trading": self.verdict.is_approved_for_trading,
            "earns_forward_test": self.verdict.earns_forward_test,
            "says_nothing_about_the_hypothesis": (
                self.verdict.says_nothing_about_the_hypothesis
            ),
            "calibration": self.calibration.payload(),
            "floors": [item.payload() for item in self.floors],
            "unmet_floors": list(self.unmet_floors),
            "between_asset": self.between_asset.payload(),
            "within_asset": self.within_asset.payload(),
            "requirement": self.requirement.payload(),
            "reasoning": self.reasoning,
        }


#: The four between-asset scenarios whose ORDERING the estimator must reproduce.
#: Ordering is a stronger and more honest requirement than any single point: an
#: estimator that is biased but monotone is still usable for a design question,
#: and one that is unbiased on average but scrambles the order is not.
_ORDERING: tuple[str, ...] = (
    "independent",
    "weak_between",
    "moderate_between",
    "strong_between",
)


def calibrate(
    *, replicates: int, block_bars: int, master_seed: int
) -> CalibrationOutcome:
    """Run every synthetic scenario and compare the mean estimate to its expectation.

    The tolerance is `CALIBRATION_TOLERANCE_RULE`'s ``1 / (K - 1)``, derived from
    the scenario's own asset count rather than chosen — it is exactly the
    magnitude of the cross-sectional exchangeability artefact at ``K`` assets, and
    an estimator cannot be asked to resolve a correlation finer than that on a
    ``K``-asset panel.

    Scenarios carrying no point expectation contribute to the readings with
    ``within_tolerance`` `None` and cannot fail the calibration; they are kept
    because the estimator must still return something sane on them and a reader
    should see what.
    """
    from fmis.paired_dependence.synthetic import CALIBRATION_SCENARIOS, generate_panel
    from fmis.paired_dependence.uncertainty import estimate_on_axis

    readings: list[CalibrationReading] = []
    means: dict[str, float | None] = {}
    for scenario in CALIBRATION_SCENARIOS:
        tolerance = 1.0 / (scenario.assets - 1)
        between: list[float] = []
        within: list[float] = []
        for replicate in range(replicates):
            panel = generate_panel(
                scenario,
                block_bars=block_bars,
                master_seed=master_seed,
                replicate=replicate,
            )
            estimate = estimate_on_axis(
                panel, axis=GroupingAxis.TIME_BLOCK, block_bars=block_bars
            ).correlation
            if estimate is not None:
                between.append(estimate)
            estimate = estimate_on_axis(
                panel, axis=GroupingAxis.ECONOMIC_ASSET, block_bars=block_bars
            ).correlation
            if estimate is not None:
                within.append(estimate)
        mean_between = statistics.fmean(between) if between else None
        mean_within = statistics.fmean(within) if within else None
        means[scenario.scenario_id] = mean_between
        for axis, expected, mean in (
            (GroupingAxis.TIME_BLOCK, scenario.expected_between_asset, mean_between),
            (
                GroupingAxis.ECONOMIC_ASSET,
                scenario.expected_within_asset,
                mean_within,
            ),
        ):
            readings.append(
                CalibrationReading(
                    scenario_id=scenario.scenario_id,
                    axis=axis,
                    expected=expected,
                    mean_estimate=mean,
                    tolerance=tolerance,
                    replicates=replicates,
                    within_tolerance=(
                        None
                        if expected is None
                        else (
                            False
                            if mean is None
                            else abs(mean - expected) <= tolerance
                        )
                    ),
                )
            )

    ordered = [(name, means.get(name)) for name in _ORDERING]
    values = [value for _name, value in ordered]
    ordering_ok = all(value is not None for value in values) and all(
        values[index] < values[index + 1] for index in range(len(values) - 1)
    )
    failures = [item for item in readings if item.within_tolerance is False]
    passed = ordering_ok and not failures
    if passed:
        reasoning = (
            f"Every point expectation was recovered within its 1/(K-1) tolerance "
            f"over {replicates} replicates, and the four between-asset scenarios "
            "reproduced their ordering strictly"
        )
    elif not ordering_ok:
        reasoning = (
            "The estimator did not reproduce the between-asset ordering "
            f"{' < '.join(_ORDERING)} over {replicates} replicates. An estimator "
            "that scrambles a known ordering cannot be read as a measurement"
        )
    else:
        reasoning = (
            f"{len(failures)} scenario/axis pair(s) missed their expectation by "
            "more than the 1/(K-1) tolerance: "
            + ", ".join(
                f"{item.scenario_id}/{item.axis.value}" for item in failures
            )
        )
    return CalibrationOutcome(
        readings=tuple(readings),
        ordering_reproduced=ordering_ok,
        ordering_detail=tuple(ordered),
        passed=passed,
        reasoning=reasoning,
    )


def check_floors(
    coverage: dict[str, Any],
    between: DependenceInterval,
    within: DependenceInterval,
    *,
    min_groups: int,
    min_members: int,
    min_economic_assets: int,
    min_informative_blocks: int,
) -> tuple[FloorReading, ...]:
    """Every pre-registered sample floor, checked against what the panel supplied."""
    return (
        FloorReading(
            name="economic_assets",
            required=min_economic_assets,
            observed=int(coverage["economic_assets"]),
            met=coverage["economic_assets"] >= min_economic_assets,
        ),
        FloorReading(
            name="informative_blocks",
            required=min_informative_blocks,
            observed=int(coverage["blocks_with_two_or_more_assets"]),
            met=coverage["blocks_with_two_or_more_assets"] >= min_informative_blocks,
        ),
        FloorReading(
            name="between_asset_groups",
            required=min_groups,
            observed=between.components.groups,
            met=between.components.groups >= min_groups,
        ),
        FloorReading(
            name="between_asset_members",
            required=min_members,
            observed=between.components.members,
            met=between.components.members >= min_members,
        ),
        FloorReading(
            name="within_asset_groups",
            required=min_economic_assets,
            observed=within.components.groups,
            met=within.components.groups >= min_economic_assets,
        ),
        FloorReading(
            name="within_asset_members",
            required=min_members,
            observed=within.components.members,
            met=within.components.members >= min_members,
        ),
    )


def assess_cd(
    *,
    calibration: CalibrationOutcome,
    floors: Sequence[FloorReading],
    between: DependenceInterval,
    within: DependenceInterval,
    requirement: RequirementAssessment,
) -> CdAssessment:
    """Apply `CD_VERDICT_RULES` in their sealed order.

    Raises:
        PairedDependenceError: an argument is of the wrong type. This function
            makes no judgement call and has no tunable, so there is nothing else
            it can refuse.
    """
    if not isinstance(calibration, CalibrationOutcome):
        raise PairedDependenceError("calibration must be a CalibrationOutcome")
    if not isinstance(between, DependenceInterval) or not isinstance(
        within, DependenceInterval
    ):
        raise PairedDependenceError("between and within must be DependenceIntervals")
    if not isinstance(requirement, RequirementAssessment):
        raise PairedDependenceError("requirement must be a RequirementAssessment")
    readings = tuple(floors)

    def decided(verdict: DependenceVerdict, reasoning: str) -> CdAssessment:
        return CdAssessment(
            verdict=verdict,
            calibration=calibration,
            floors=readings,
            between_asset=between,
            within_asset=within,
            requirement=requirement,
            reasoning=reasoning,
        )

    # Rule 1 — calibration, first and short-circuiting.
    if not calibration.passed:
        return decided(
            DependenceVerdict.INVALID_ESTIMATOR,
            "The estimator failed its synthetic calibration, so no real estimate "
            f"it produced may be read. {calibration.reasoning}",
        )

    # Rule 2 — floors and a refused interval.
    unmet = [item.name for item in readings if not item.met]
    if unmet:
        return decided(
            DependenceVerdict.INCONCLUSIVE,
            "The panel does not meet the pre-registered sample floor(s) "
            f"{', '.join(unmet)}, so the dependence is not identified from it. "
            "This is a statement about the panel, not about the market",
        )
    if between.lower is None or between.upper is None:
        return decided(
            DependenceVerdict.INCONCLUSIVE,
            "No interval was produced for the between-asset correlation: "
            f"{between.reason}",
        )

    # Rule 2 (continued) — an interval that straddles the saturation threshold.
    if requirement.outcome.value == "inconclusive":
        return decided(
            DependenceVerdict.INCONCLUSIVE,
            "The between-asset interval "
            f"[{between.lower:.4f}, {between.upper:.4f}] cannot distinguish 'no "
            "dependence penalty at all' from 'unreachable at any universe size': "
            f"{requirement.reasoning}",
        )

    # Rules 3 and 4 — how wide the implied requirement is.
    span = requirement.order_of_magnitude_span
    if span is None:
        return decided(
            DependenceVerdict.WEAKLY_IDENTIFIED,
            "One bound of the interval implies a finite universe requirement and "
            "the other does not, so the direction is informative and the "
            "magnitude is not",
        )
    if span > 10.0:
        return decided(
            DependenceVerdict.WEAKLY_IDENTIFIED,
            f"The implied requirement spans {span:.1f}x between the interval "
            "bounds — more than one order of magnitude — so a design could be "
            "sized from it only to within a factor of ten",
        )
    return decided(
        DependenceVerdict.MEASURED,
        f"The implied requirement spans {span:.1f}x between the interval bounds, "
        "within one order of magnitude, so the dependence is identified well "
        "enough for a research design to quote it",
    )
