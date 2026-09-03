"""Can the question be asked? **Never whether it should be answered yes.**

Milestone CA's verdict enum cannot approve a trade. Milestone CB's cannot endorse
a hypothesis. Milestone CC's cannot do either, and additionally cannot say
anything about whether an admission edge exists — it answers one question, about
experimental design, and the boundary is enforced in code rather than in prose.

**The rule, stated as arithmetic before it is stated as words.**

    INFEASIBLE      the primary effect resolves under NO sealed dependence
                    scenario, including the most favourable one
    FEASIBLE        it resolves under the residual scenario AND the
                    survivorship classification is not CURRENT_SURVIVOR_ONLY
    FEASIBLE_WITH_  it resolves under the independent scenario but not the
      LIMITATIONS   residual one, or it resolves and a stated limitation
                    materially weakens the design
    INDETERMINATE   a measurement the rule depends on could not be taken

`INDETERMINATE` is checked **first** and deliberately. A dependence estimate that
could not be formed is not evidence of infeasibility; folding the two together
would let a failed download read as a scientific finding, which is the single most
damaging thing a feasibility gate can do.

**A `FEASIBLE` verdict here is weak on purpose.** Every projection it rests on
holds the within-cluster correlation at zero — the most favourable value — so the
requirement it clears is a lower bound. That is stated in the verdict's own
reasoning rather than left to a reader, and it is why nothing downstream treats
`FEASIBLE` as permission for anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from fmis.universe.dependence import DependenceSummary
from fmis.universe.growth import EffectRequirement
from fmis.universe.models import (
    FeasibilityVerdict,
    SurvivorshipClass,
    UniverseError,
    require_count,
    require_text,
)

__all__ = [
    "SurvivorshipReading",
    "FeasibilityAssessment",
    "classify_survivorship",
    "decide_feasibility",
]


@dataclass(frozen=True, slots=True)
class SurvivorshipReading:
    """What is known, and what is knowably unknown, about the disappeared.

    ``unrecoverable_gap_demonstrated`` is the field that keeps this honest. The
    provider retains many delisted pairs, which is why a partially aware universe
    is possible at all — and it demonstrably does not retain them all. The size of
    the missing set cannot be measured from inside the provider, so it is recorded
    as **unmeasurable**, never as zero.
    """

    classification: SurvivorshipClass
    total_instruments: int
    halted_instruments: int
    eligible_halted: int
    unrecoverable_gap_demonstrated: bool
    evidence: str

    def __post_init__(self) -> None:
        if not isinstance(self.classification, SurvivorshipClass):
            raise UniverseError("classification must be a SurvivorshipClass")
        require_count(self.total_instruments, "total_instruments")
        require_count(self.halted_instruments, "halted_instruments")
        require_count(self.eligible_halted, "eligible_halted")
        require_text(self.evidence, "survivorship evidence")
        if self.halted_instruments > self.total_instruments:
            raise UniverseError(
                "more halted instruments than instruments; the counts describe "
                "two different universes"
            )
        if self.classification is SurvivorshipClass.SURVIVORSHIP_AWARE and (
            self.unrecoverable_gap_demonstrated
        ):
            raise UniverseError(
                "a universe with a demonstrated unrecoverable gap cannot be "
                "classified SURVIVORSHIP_AWARE. That label asserts every "
                "instrument which ever qualified is recoverable, and one has been "
                "shown not to be"
            )
        if self.classification is SurvivorshipClass.CURRENT_SURVIVOR_ONLY and (
            self.halted_instruments
        ):
            raise UniverseError(
                f"{self.halted_instruments} halted instrument(s) were discovered, "
                "so the universe is not current-survivor-only. Understating "
                "coverage is a different error from overstating it, and both are "
                "refused"
            )

    @property
    def halted_share(self) -> float:
        if not self.total_instruments:
            return 0.0
        return self.halted_instruments / self.total_instruments

    def payload(self) -> dict[str, Any]:
        return {
            "classification": self.classification.value,
            "total_instruments": self.total_instruments,
            "halted_instruments": self.halted_instruments,
            "halted_share": self.halted_share,
            "eligible_halted": self.eligible_halted,
            "unrecoverable_gap_demonstrated": self.unrecoverable_gap_demonstrated,
            "evidence": self.evidence,
        }


#: A pair known to have traded on this provider and absent from both its current
#: `exchangeInfo` listing and its klines endpoint. Its existence is what makes the
#: retention gap a **demonstrated fact** rather than a suspicion — and what makes
#: `SURVIVORSHIP_AWARE` unreachable through this provider.
KNOWN_UNRECOVERABLE_PAIR: Final[str] = "HSRUSDT"


def classify_survivorship(
    *,
    total_instruments: int,
    halted_instruments: int,
    eligible_halted: int,
    unrecoverable_gap_demonstrated: bool,
) -> SurvivorshipReading:
    """Classify the universe's survivorship coverage. **Never flattering.**

    A universe holding no halted instrument at all is `CURRENT_SURVIVOR_ONLY`,
    whatever the provider claims to retain: what matters is what the universe
    actually contains. A universe holding some, with a demonstrated gap, is
    `PARTIALLY_SURVIVORSHIP_AWARE`. `SURVIVORSHIP_AWARE` is not reachable from
    this function while a gap has been demonstrated, and it is refused by
    `SurvivorshipReading` if it were.
    """
    require_count(total_instruments, "total_instruments")
    require_count(halted_instruments, "halted_instruments")
    require_count(eligible_halted, "eligible_halted")
    if not halted_instruments:
        classification = SurvivorshipClass.CURRENT_SURVIVOR_ONLY
        evidence = (
            "No halted instrument was discovered. Every member of this universe "
            "is a market that still trades, so an instrument that met the "
            "criteria and then disappeared is absent by construction. This is a "
            "SURVIVOR-BIASED universe and is labelled as one."
        )
    elif unrecoverable_gap_demonstrated:
        classification = SurvivorshipClass.PARTIALLY_SURVIVORSHIP_AWARE
        evidence = (
            f"{halted_instruments} of {total_instruments} discovered instruments "
            f"are halted, and {eligible_halted} of them survive into the eligible "
            "universe — so instruments that stopped trading ARE represented. "
            f"Retention is demonstrably incomplete: {KNOWN_UNRECOVERABLE_PAIR} "
            "traded on this provider and is absent from both its current listing "
            "and its klines endpoint. The size of the unrecoverable set cannot be "
            "measured from inside the provider and is recorded as UNMEASURABLE, "
            "not as zero."
        )
    else:
        classification = SurvivorshipClass.PARTIALLY_SURVIVORSHIP_AWARE
        evidence = (
            f"{halted_instruments} of {total_instruments} discovered instruments "
            "are halted and are represented in the funnel. No unrecoverable gap "
            "was demonstrated in this run, which is NOT evidence that none "
            "exists — the provider's retention policy is not published and cannot "
            "be enumerated from inside it."
        )
    return SurvivorshipReading(
        classification=classification,
        total_instruments=total_instruments,
        halted_instruments=halted_instruments,
        eligible_halted=eligible_halted,
        unrecoverable_gap_demonstrated=unrecoverable_gap_demonstrated,
        evidence=evidence,
    )


@dataclass(frozen=True, slots=True)
class FeasibilityAssessment:
    """Milestone CC's answer, with everything that produced it.

    ``verdict`` answers whether the +0.10 ATR question can be *asked* of a
    universe this provider can supply. It says nothing about whether an edge
    exists, and `FeasibilityVerdict.is_approved_for_trading` is `False` for every
    member it could hold.
    """

    verdict: FeasibilityVerdict
    primary_effect: str
    eligible_assets: int
    required_assets_independent: int | None
    required_assets_residual: int | None
    required_assets_raw: int | None
    survivorship: SurvivorshipReading
    binding_constraint: str
    reasoning: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.verdict, FeasibilityVerdict):
            raise UniverseError("verdict must be a FeasibilityVerdict")
        if not isinstance(self.survivorship, SurvivorshipReading):
            raise UniverseError("survivorship must be a SurvivorshipReading")
        require_text(self.reasoning, "reasoning")
        require_text(self.binding_constraint, "binding_constraint")
        require_text(self.primary_effect, "primary_effect")
        require_count(self.eligible_assets, "eligible_assets")
        if not isinstance(self.limitations, tuple) or not self.limitations:
            raise UniverseError(
                "a feasibility assessment must carry at least one limitation; a "
                "study that claims none has not looked"
            )

    @property
    def is_approved_for_trading(self) -> bool:
        """**Always False.** Asserted by a hostile test, not merely documented."""
        return False

    @property
    def earns_forward_test(self) -> bool:
        """**Always False.** Feasibility is not permission."""
        return False

    def payload(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "primary_effect": self.primary_effect,
            "eligible_assets": self.eligible_assets,
            "required_assets_independent": self.required_assets_independent,
            "required_assets_residual": self.required_assets_residual,
            "required_assets_raw": self.required_assets_raw,
            "survivorship": self.survivorship.payload(),
            "binding_constraint": self.binding_constraint,
            "reasoning": self.reasoning,
            "limitations": list(self.limitations),
            "is_approved_for_trading": self.is_approved_for_trading,
            "earns_forward_test": self.earns_forward_test,
        }


def decide_feasibility(
    *,
    requirements: dict[str, EffectRequirement],
    eligible_assets: int,
    dependence: DependenceSummary,
    survivorship: SurvivorshipReading,
    limitations: tuple[str, ...],
    primary_effect: Decimal = Decimal("0.10"),
) -> FeasibilityAssessment:
    """Apply the sealed verdict rules. **`INDETERMINATE` is checked first.**

    ``requirements`` maps each sealed dependence scenario to the smallest universe
    that resolves the primary effect under it, as `requirement_for_effect`
    computed it.
    """
    require_count(eligible_assets, "eligible_assets")
    if not isinstance(dependence, DependenceSummary):
        raise UniverseError("dependence must be a DependenceSummary")

    def supplied(scenario: str) -> int | None:
        item = requirements.get(scenario)
        return None if item is None or not item.reachable else item.required_assets

    if not dependence.is_measured or "residual" not in requirements:
        return FeasibilityAssessment(
            verdict=FeasibilityVerdict.INDETERMINATE,
            primary_effect=str(primary_effect),
            eligible_assets=eligible_assets,
            required_assets_independent=supplied("independent"),
            required_assets_residual=None,
            required_assets_raw=supplied("raw"),
            survivorship=survivorship,
            binding_constraint="measurement_unavailable",
            reasoning=(
                "No between-asset dependence estimate could be formed, so the "
                "scenario the verdict rule reads as primary has no value. Absence "
                "of a measurement is reported as absence of a measurement; "
                "reading it as INFEASIBLE would let a failed download become a "
                "scientific finding."
            ),
            limitations=limitations,
        )

    independent = requirements.get("independent")
    residual = requirements["residual"]
    raw = requirements.get("raw")

    reachable_anywhere = any(
        item is not None and item.reachable
        for item in (independent, residual, raw)
    )
    clears = {
        name: (
            item is not None
            and item.reachable
            and item.required_assets is not None
            and item.required_assets <= eligible_assets
        )
        for name, item in (
            ("independent", independent), ("residual", residual), ("raw", raw)
        )
    }

    r_residual = dependence.correlation_for("residual")
    saturation = (
        "unbounded" if r_residual <= 0.0 else f"{1.0 / r_residual:.2f} effective clusters"
    )

    if not reachable_anywhere:
        return FeasibilityAssessment(
            verdict=FeasibilityVerdict.INFEASIBLE,
            primary_effect=str(primary_effect),
            eligible_assets=eligible_assets,
            required_assets_independent=None,
            required_assets_residual=None,
            required_assets_raw=None,
            survivorship=survivorship,
            binding_constraint="dependence_saturation",
            reasoning=(
                f"No universe size resolves {primary_effect} ATR under ANY sealed "
                "dependence scenario. Because the effective cluster count "
                f"saturates ({saturation} under the residual scenario), the "
                "interval half-width approaches a floor that additional assets do "
                "not lower. This is the statement that no quantity of this kind of "
                "data suffices — not that a large quantity is needed."
            ),
            limitations=limitations,
        )

    if not clears["independent"]:
        needed = independent.required_assets if independent is not None else None
        return FeasibilityAssessment(
            verdict=FeasibilityVerdict.INFEASIBLE,
            primary_effect=str(primary_effect),
            eligible_assets=eligible_assets,
            required_assets_independent=supplied("independent"),
            required_assets_residual=supplied("residual"),
            required_assets_raw=supplied("raw"),
            survivorship=survivorship,
            binding_constraint="cluster_count",
            reasoning=(
                f"The measured universe supplies {eligible_assets} eligible "
                f"economic assets. Resolving {primary_effect} ATR needs "
                f"{'an unreachable number of' if needed is None else format(needed, ',')} "
                "assets even under the INDEPENDENT scenario, which assumes zero "
                "between-asset dependence and is the most favourable assumption "
                "available. A universe that falls short of the most favourable "
                "case falls short of every other one, so no dependence "
                "measurement can rescue it."
            ),
            limitations=limitations,
        )

    if not clears["residual"]:
        return FeasibilityAssessment(
            verdict=FeasibilityVerdict.FEASIBLE_WITH_LIMITATIONS,
            primary_effect=str(primary_effect),
            eligible_assets=eligible_assets,
            required_assets_independent=supplied("independent"),
            required_assets_residual=supplied("residual"),
            required_assets_raw=supplied("raw"),
            survivorship=survivorship,
            binding_constraint="between_asset_dependence",
            reasoning=(
                f"{eligible_assets} eligible assets clear the requirement when "
                "assets are assumed independent, but not once the measured "
                f"residual between-asset correlation of {r_residual:.4f} is "
                "applied. The target is reachable only under an assumption the "
                "data does not support, which is a limitation rather than a "
                "feasibility."
            ),
            limitations=limitations,
        )

    weakened = survivorship.classification is SurvivorshipClass.CURRENT_SURVIVOR_ONLY
    verdict = (
        FeasibilityVerdict.FEASIBLE_WITH_LIMITATIONS
        if weakened
        else FeasibilityVerdict.FEASIBLE
    )
    return FeasibilityAssessment(
        verdict=verdict,
        primary_effect=str(primary_effect),
        eligible_assets=eligible_assets,
        required_assets_independent=supplied("independent"),
        required_assets_residual=supplied("residual"),
        required_assets_raw=supplied("raw"),
        survivorship=survivorship,
        binding_constraint="none",
        reasoning=(
            f"{eligible_assets} eligible economic assets clear the requirement "
            f"under the residual dependence scenario ({r_residual:.4f}). "
            + (
                "The universe is current-survivor-only, which materially weakens "
                "the design, so the verdict is qualified. "
                if weakened
                else ""
            )
            + "This is a LOWER-BOUND result: every projection behind it holds the "
            "within-cluster correlation at zero, the most favourable value it can "
            "take. It is not permission to trade, to paper trade or to promote "
            "anything."
        ),
        limitations=limitations,
    )
