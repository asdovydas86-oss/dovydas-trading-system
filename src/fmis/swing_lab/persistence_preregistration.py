"""**Milestone BZ's frozen pre-registration. Sealed before a single result was read.**

This module is BZ's entire claim to be a test rather than a search, and it works
only if the following is literally true:

> Every hypothesis id, every threshold, every checkpoint, every sample boundary,
> every cost scenario, every promotion criterion and every classification rule
> below was fixed, and its SHA-256 recorded in `BZ_PREREGISTRATION_DIGEST`,
> **before the first capture was run**. `test_swing_lab_persistence_preregistration`
> recomputes the digest from the content and fails if the two disagree.

The seal and the content live in the same file, so a change to either without
the other is a red test — Milestone BY's device, reused rather than reinvented.

**Why BZ has two verdicts and BY had one, and why that is not a softened bar.**

BY asked *is this geometry profitable*, and one verdict answers that. BZ asks a
different question — *does post-entry management add information* — and that
question is answerable even where the absolute level is negative. Production
geometry loses roughly 0.5R per trade on every sample BW, BX and BY measured, so
a milestone whose only verdict were "positive expectancy" would return
NO_CANDIDATE without having measured anything, and would have learned nothing.

So two verdicts are sealed, and they are **not** ranked as a consolation:

    MECHANISM_EVIDENCE   did the family improve on its own H0 control, on the
                         same setups, robustly, on all three samples?
    CANDIDATE            is the complete policy — geometry AND exit — positive
                         cost-inclusive on all three samples, and does it clear
                         every other gate?

`MECHANISM_EVIDENCE` can never promote anything. It is a finding about
information, and the report says so. **Only `CANDIDATE` earns shadow or paper
testing, and it requires absolute positivity on development, validation and the
holdout — the identical bar BY used, unchanged.**

**What is deliberately absent.** No threshold is swept to find a winner. Each
family carries the one number its mechanism needs; the robustness neighbourhood
below exists to ask *does this mechanism survive a nearby reasonable value*, is
measured for every family, and **no neighbourhood point may ever be promoted** —
`assess_bz_candidate`'s first criterion is membership in `BZ_HYPOTHESES`, decided
by set membership plus a digest match rather than by a flag a caller passes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Final

from fmis.swing_lab.exits import (
    BZ_EXIT_POLICIES,
    COMBINATION_COMPONENTS,
    ExitMechanic,
    ExitPolicy,
)
from fmis.swing_lab.geometry import GeometryPolicy
from fmis.swing_lab.geometry_variants import PRODUCTION_GEOMETRY
from fmis.swing_lab.geometry_verdict import MAX_SINGLE_SYMBOL_SHARE
from fmis.swing_lab.metrics import SAMPLE_FLOOR
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.persistence import (
    ADVERSE_THRESHOLD,
    CHECKPOINT_BARS,
    EXCURSION_THRESHOLDS,
    LEVELS_PER_SIDE,
)
# Samples, cost scenarios and the deciding scenario are IMPORTED from Milestone
# BY, never restated. BZ measures the same populations under the same costs, so
# a BZ figure and a BY figure describe comparable trades; a copy here could drift
# from BY's and the two milestones would silently stop being comparable.
from fmis.swing_lab.preregistration import (
    DECIDING_COST_POLICY_ID,
    PRIMARY_POLICY as BY_PRIMARY_GEOMETRY,
    SAMPLES,
    VALIDATION_COST_SCENARIOS,
    SampleSpec,
)
from fmis.trade_lifecycle import PaperCostPolicy

__all__ = [
    "BZ_PREREGISTRATION_ID",
    "BZ_PREREGISTRATION_DIGEST",
    "BZ_RESEARCH_QUESTION",
    "BZ_GEOMETRIES",
    "BZ_HYPOTHESES",
    "BZ_HYPOTHESIS_IDS",
    "BzHypothesis",
    "BzPreregistration",
    "BZ_PRE_REGISTRATION",
    "STAGNATION_NEIGHBOURHOOD",
    "GIVEBACK_NEIGHBOURHOOD",
    "ROBUSTNESS_NEIGHBOURHOOD",
    "NEIGHBOURHOOD_IS_NOT_A_SEARCH",
    "BZ_CANDIDATE_CRITERIA",
    "BZ_MECHANISM_CRITERIA",
    "BZ_CLASSIFICATION_RULES",
    "BZ_AMBIGUITY_POLICY",
    "BZ_REQUIRED_DECOMPOSITIONS",
    "BZ_METRICS_REPORTED",
    "BZ_LIMITATIONS",
    "MIN_MECHANISM_IMPROVEMENT_R",
    "bz_preregistration_digest",
    "verify_bz_preregistration",
    "is_bz_pre_registered",
]

BZ_PREREGISTRATION_ID: Final[str] = "bz-swing-thesis-persistence-v1"

BZ_RESEARCH_QUESTION: Final[str] = (
    "Do FMITS swing setups contain measurable post-entry thesis persistence that "
    "can support an explicit, causal exit policy which generalises beyond the "
    "development period? This is NOT an entry study and no geometry is searched: "
    "the two geometries below are FIXED, both are Milestone BX's and BY's own, "
    "and every hypothesis varies only what happens to a position AFTER it is "
    "open."
)


# ---------------------------------------------------------------------------
# 1. The geometries. Fixed, imported, and not under test.
# ---------------------------------------------------------------------------

#: The two geometries every exit family is measured under. **Neither is a BZ
#: hypothesis and neither may be promoted by this milestone.**
#:
#: `geom_production` is the live rule and is the one an exit change would
#: actually be applied to, so it is the primary. BY's `by_stop_0_5atr_target_2r`
#: is measured as well and for one stated reason: BY refuted it as a strategy
#: while showing it selects a genuinely better-shaped trade, and "can management
#: rescue a better-shaped trade" is a different question from "can management
#: rescue the live one". Reporting only the first would answer half of what the
#: evidence can address. **BY's geometry remains REJECTED; measuring an exit
#: family over it does not reopen it.**
BZ_GEOMETRIES: Final[tuple[GeometryPolicy, ...]] = (
    PRODUCTION_GEOMETRY,
    BY_PRIMARY_GEOMETRY,
)


# ---------------------------------------------------------------------------
# 2. The observational study. Fixed before any path was walked.
# ---------------------------------------------------------------------------

#: Everything the observational half of BZ freezes in advance, so the dataset
#: cannot be reshaped after its distributions are seen.
OBSERVATION_SPEC: Final[Mapping[str, Any]] = {
    "checkpoint_bars": list(CHECKPOINT_BARS),
    "excursion_thresholds": [str(item) for item in EXCURSION_THRESHOLDS],
    "adverse_threshold": str(ADVERSE_THRESHOLD),
    "levels_per_side": LEVELS_PER_SIDE,
    "thesis_states": [
        "intact", "strengthened", "weakened", "conflicted", "invalidated",
        "unavailable",
    ],
    "thesis_state_precedence": (
        "UNAVAILABLE, then INVALIDATED, then CONFLICTED, then WEAKENED, then "
        "STRENGTHENED, then INTACT. Fixed here so two milestones cannot read the "
        "same two observations differently."
    ),
    "descriptive_fields_may_never_become_rules": (
        "peak_r, bars_to_peak_r, final_close_r, total_giveback_r and every "
        "bars_to_* timing are statements about a WHOLE path and therefore about "
        "the future as seen from any bar inside it. They are reported as path "
        "observations and are barred from every exit rule. Only a "
        "PostEntryCheckpoint's fields — each confirmed by its own bar — may "
        "decide anything."
    ),
}


# ---------------------------------------------------------------------------
# 3. The hypotheses.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BzHypothesis:
    """One pre-registered exit family, its prediction and what would refute it.

    ``prediction`` and ``refuted_by`` are read from the `ExitPolicy`'s own
    sealed hypothesis text rather than restated here, so there is exactly one
    place either can be edited and the digest covers it.
    """

    hypothesis_id: str
    role: str
    policy: ExitPolicy

    def __post_init__(self) -> None:
        for name in ("hypothesis_id", "role"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SwingLabError(f"{name} must be a non-empty str")
        if not isinstance(self.policy, ExitPolicy):
            raise TypeError("policy must be an ExitPolicy")
        if self.role != "control":
            for marker in ("PREDICTION:", "REFUTED BY:"):
                if marker not in self.policy.hypothesis:
                    raise SwingLabError(
                        f"{self.hypothesis_id} states no {marker.rstrip(':')}; a "
                        "rule with no stated refutation cannot fail, and a "
                        "milestone whose rules cannot fail is a search"
                    )

    @property
    def policy_id(self) -> str:
        return self.policy.policy_id

    @property
    def is_combination(self) -> bool:
        return self.policy.mechanic in COMBINATION_COMPONENTS

    @property
    def components(self) -> tuple[ExitMechanic, ...]:
        return COMBINATION_COMPONENTS.get(self.policy.mechanic, ())

    def payload(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "role": self.role,
            "policy": self.policy.payload(),
            "reads_structural_timeline": self.policy.needs_timeline,
            "decides_on_close": self.policy.mechanic.decides_on_close,
            "components": [item.value for item in self.components],
        }


_ROLES: Final[dict[str, str]] = {
    "bz_exit_control": "control",
    "bz_exit_thesis_failure": "thesis",
    "bz_exit_stagnation_12": "time",
    "bz_exit_giveback_half": "profit_protection",
    "bz_exit_structural_trail": "structural_trail",
    "bz_exit_thesis_and_giveback": "combination",
}

_IDS: Final[dict[str, str]] = {
    "bz_exit_control": "BZ-H0",
    "bz_exit_thesis_failure": "BZ-H1",
    "bz_exit_stagnation_12": "BZ-H2",
    "bz_exit_giveback_half": "BZ-H3",
    "bz_exit_structural_trail": "BZ-H4",
    "bz_exit_thesis_and_giveback": "BZ-H5",
}

BZ_HYPOTHESES: Final[tuple[BzHypothesis, ...]] = tuple(
    BzHypothesis(
        hypothesis_id=_IDS[policy.policy_id],
        role=_ROLES[policy.policy_id],
        policy=policy,
    )
    for policy in BZ_EXIT_POLICIES
)

BZ_HYPOTHESIS_IDS: Final[frozenset[str]] = frozenset(
    item.policy_id for item in BZ_HYPOTHESES
)

if len(BZ_HYPOTHESIS_IDS) != len(BZ_HYPOTHESES):  # pragma: no cover
    raise SwingLabError("two BZ hypotheses share a policy_id")


def is_bz_pre_registered(policy_id: str) -> bool:
    """Whether this exit policy was sealed before results existed. **The gate.**"""
    return policy_id in BZ_HYPOTHESIS_IDS


# ---------------------------------------------------------------------------
# 4. The robustness neighbourhood. Measured, never promoted.
# ---------------------------------------------------------------------------

#: The stagnation bar counts measured around the declared 12. **Neither 8 nor 18
#: may be promoted**; they exist to answer whether the mechanism survives a
#: nearby reasonable value or whether 12 is a spike.
STAGNATION_NEIGHBOURHOOD: Final[tuple[int, ...]] = (8, 12, 18)

#: The give-back fractions measured around the declared one half. A third and
#: two thirds straddle it rather than crowding it: neighbours chosen close
#: enough to be indistinguishable cannot fail, and a plateau that cannot fail is
#: not evidence.
GIVEBACK_NEIGHBOURHOOD: Final[tuple[str, ...]] = ("0.33", "0.5", "0.67")

ROBUSTNESS_NEIGHBOURHOOD: Final[Mapping[str, Any]] = {
    "bz_exit_stagnation_12": {
        "parameter": "stagnation_bars",
        "points": list(STAGNATION_NEIGHBOURHOOD),
        "declared": 12,
    },
    "bz_exit_giveback_half": {
        "parameter": "giveback_fraction",
        "points": list(GIVEBACK_NEIGHBOURHOOD),
        "declared": "0.5",
    },
}

NEIGHBOURHOOD_IS_NOT_A_SEARCH: Final[str] = (
    "Two families carry a threshold and each is measured at three points; the "
    "other three families have no threshold to sweep. Six extra measurements "
    "exist ONLY to classify the declared point as a plateau or a spike, under "
    "the same all-not-any rule Milestone BY used. No neighbourhood point is a "
    "pre-registered hypothesis, `is_bz_pre_registered` returns False for every "
    "one of them, and `assess_bz_candidate` refuses to promote anything it "
    "returns False for. A milestone that could promote its own neighbourhood "
    "would have run a nine-point grid search and called it robustness."
)


# ---------------------------------------------------------------------------
# 5. Intrabar ambiguity. The policy, fixed in advance.
# ---------------------------------------------------------------------------

BZ_AMBIGUITY_POLICY: Final[tuple[str, ...]] = (
    "BZ's five mechanics are decided at an execution bar's CLOSE and filled at "
    "the next bar's OPEN. A close and an open are single prices, so none of "
    "these decisions has an intrabar ordering problem at all — this is a "
    "property of the mechanism design, not a claim that ambiguity was solved.",
    "The stop and the target are still watched INSIDE the bar and can still "
    "collide there. That case remains `AMBIGUOUS_SAME_BAR`, is resolved by "
    "descending Milestone BY's ladder to 1H and then 15m, and is REFUSED — never "
    "guessed — when the finest available rung still holds both.",
    "A structural trail adds no watched level: it MOVES the existing stop. It "
    "therefore does not multiply ambiguity the way BY's +1R arming level did, "
    "and the ambiguous count is reported beside every expectancy so the claim "
    "can be checked rather than believed.",
    "Every mechanic's ambiguous count is reported. A family whose result rests "
    "on a materially different ambiguous population from the control's is "
    "reported as such and additionally re-measured over the setups EVERY family "
    "could measure — BY defect BY-D9's `comparable` column, reused.",
    "If a conclusion changes under either defensible boundary assumption for the "
    "still-ambiguous trades, the conclusion is INCONCLUSIVE and is reported as "
    "INCONCLUSIVE. Precision is not manufactured.",
)


# ---------------------------------------------------------------------------
# 6. The bar. Written before any result, so it cannot be argued down after one.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CriterionSpec:
    """One requirement, as a sentence and a number, fixed in advance."""

    name: str
    requirement: str
    threshold: float | None

    def __post_init__(self) -> None:
        for field_name in ("name", "requirement"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise SwingLabError(f"{field_name} must be a non-empty str")

    def payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "requirement": self.requirement,
            "threshold": self.threshold,
        }


#: The smallest per-trade improvement over H0 that BZ will call evidence of a
#: mechanism. **Declared in advance and deliberately not tiny.** BY measured
#: break-even stops at roughly +0.30R over the same control, so a bar of +0.10R
#: is well inside what a real mechanism produced and well outside the noise of a
#: 130-trade sample. A figure chosen after the results would be one a researcher
#: could argue down to whatever was measured.
MIN_MECHANISM_IMPROVEMENT_R: Final[float] = 0.10

BZ_MECHANISM_CRITERIA: Final[tuple[CriterionSpec, ...]] = (
    CriterionSpec(
        "pre_registered",
        "the exit family appears in BZ_HYPOTHESES and the study's manifest "
        "carries this pre-registration's digest",
        None,
    ),
    CriterionSpec(
        "causal",
        "every decision the family took was proven blind to bars after it, by "
        "the milestone's own future-mutation suite WITH a non-vacuity control",
        None,
    ),
    CriterionSpec(
        "sample",
        f"at least {SAMPLE_FLOOR} measurable trades on each of the three samples",
        SAMPLE_FLOOR,
    ),
    CriterionSpec(
        "improves_development",
        f"cost-inclusive expectancy at least {MIN_MECHANISM_IMPROVEMENT_R:g}R "
        "above its own H0 control on development, measured over the setups BOTH "
        "could measure",
        MIN_MECHANISM_IMPROVEMENT_R,
    ),
    CriterionSpec(
        "improves_validation",
        "a non-negative improvement over H0 on validation; a mechanism that "
        "helps only where it was developed is not a mechanism",
        0.0,
    ),
    CriterionSpec(
        "improves_holdout",
        "a non-negative improvement over H0 on twenty-one never-measured symbols",
        0.0,
    ),
    CriterionSpec(
        "robust",
        "for a family carrying a threshold, EVERY measurable neighbourhood point "
        "also improves on H0 on development. `all`, never `any` — one improving "
        "point beside a worsening one is a spike",
        None,
    ),
    CriterionSpec(
        "ambiguity_not_decisive",
        "the family's conclusion is unchanged under both boundary assumptions "
        "for trades that remain ambiguous at the finest available rung",
        None,
    ),
)

BZ_CANDIDATE_CRITERIA: Final[tuple[CriterionSpec, ...]] = (
    CriterionSpec(
        "mechanism_evidence",
        "every criterion in BZ_MECHANISM_CRITERIA passed; a policy that does not "
        "even improve on its own control cannot be a candidate",
        None,
    ),
    CriterionSpec(
        "development_expectancy",
        "a POSITIVE cost-inclusive expectancy on development under the deciding "
        "cost scenario. The frictionless column may never promote anything",
        0.0,
    ),
    CriterionSpec(
        "validation_expectancy",
        "a NON-NEGATIVE cost-inclusive expectancy on validation",
        0.0,
    ),
    CriterionSpec(
        "holdout_expectancy",
        "a NON-NEGATIVE cost-inclusive expectancy on the holdout. This is "
        "Milestone BY's bar, unchanged, and it is not weakened because BZ "
        "measures a different lever",
        0.0,
    ),
    CriterionSpec(
        "profit_factor",
        "a cost-inclusive profit factor above 1.0 on development",
        1.0,
    ),
    CriterionSpec(
        "drawdown_recovered",
        "the worst peak-to-trough decline on development is smaller than the "
        "total R the policy gained",
        None,
    ),
    CriterionSpec(
        "symbol_concentration",
        f"no single symbol contributes more than {MAX_SINGLE_SYMBOL_SHARE:.0%} of "
        "gross absolute R on development",
        float(MAX_SINGLE_SYMBOL_SHARE),
    ),
    CriterionSpec(
        "both_directions_understood",
        "LONG and SHORT are each reported, and a cohort below the sample floor "
        "REFUSES an expectancy rather than stating a thin one",
        None,
    ),
    CriterionSpec(
        "no_single_period",
        "the policy does not depend on one walk-forward window: it is measured "
        "in every half-year block with the frozen rule and NO re-optimisation",
        None,
    ),
    CriterionSpec(
        "components_earned_it",
        "a COMBINATION may be promoted only if each of its components "
        "independently cleared development_expectancy, so a combination can "
        "never launder a component that failed on its own",
        None,
    ),
)

BZ_CLASSIFICATION_RULES: Final[tuple[str, ...]] = (
    "NOT_MEASURED — the family produced no measurable trades at all, or its "
    "prerequisite was unavailable (a thesis rule with no structural timeline). "
    "Nothing was established; this is not a negative result.",
    f"INCONCLUSIVE — fewer than {SAMPLE_FLOOR} measurable trades on any sample "
    "the criteria read, or the conclusion flips under a defensible intrabar "
    "boundary assumption. The test could not be run, which is NOT a pass.",
    "REJECTED — the family was measured and failed at least one criterion in "
    "BZ_MECHANISM_CRITERIA. It did not improve on its own control, robustly, "
    "out of sample.",
    "MECHANISM_EVIDENCE — every BZ_MECHANISM_CRITERIA criterion passed. The "
    "family carries information. This is a finding about INFORMATION and is "
    "explicitly NOT approval for shadow, paper or forward testing.",
    "CANDIDATE — MECHANISM_EVIDENCE plus every criterion in "
    "BZ_CANDIDATE_CRITERIA, including a positive cost-inclusive expectancy on "
    "development and a non-negative one on BOTH unseen samples. This is the "
    "only verdict that earns shadow or paper testing, and there is no state "
    "above it.",
)

BZ_REQUIRED_DECOMPOSITIONS: Final[tuple[str, ...]] = (
    "per exit family, per geometry, per sample — never pooled across samples, "
    "because Milestone BY defect BY-D6 showed that pooling a 15-symbol universe "
    "with a 21-symbol one changes what is being measured half-way along",
    "long against short, with expectancy REFUSED for any cohort below the floor",
    "per symbol, and the largest single symbol's share of gross absolute R",
    "chronological walk-forward in half-year blocks, ONE CURVE PER UNIVERSE, "
    "with the frozen policy and no re-optimisation inside any window",
    "exit reason — how often each mechanism actually fired, beside its expectancy",
    "outcome by trade age, and by the thesis state observed at each checkpoint",
)

BZ_METRICS_REPORTED: Final[tuple[str, ...]] = (
    "trades, measurable trades, ambiguous trades, unentered records",
    "expectancy R gross and cost-inclusive, median R, win rate, profit factor",
    "average winner, average loser, maximum peak-to-trough drawdown in R",
    "average and median bars held, and how often the mechanism fired",
    "MFE, MAE, peak R, give-back, and the share of trades surrendering a full R",
    "time to first +0.5R, +1R, +1.5R, +2R and to the first adverse half R",
    "thesis-state distribution at every checkpoint, and state transitions",
    "cost drag per trade, and the ambiguous-event count beside every figure",
)

BZ_LIMITATIONS: Final[tuple[str, ...]] = (
    "BZ-1 — the evaluation window is 60 execution bars (10 calendar days), "
    "inherited unchanged from BW so BZ's figures stay comparable with BW, BX and "
    "BY. Every statement about trade age, stagnation and time-to-peak is bounded "
    "by it, and a longer window would give different answers to all three.",
    "BZ-2 — the thesis vocabulary is the production engines' output, so BZ "
    "inherits every limitation of `structural_trend`, `market_regime` and "
    "`decision_context`. A thesis rule can be no more sensitive than the "
    "structure detection underneath it.",
    "BZ-3 — the structural timeline is sampled at execution-bar closes only. A "
    "level confirmed between two 4H closes is seen at the later close, which is "
    "the correct causal treatment and also means a trail can never be tighter "
    "than 4H resolution.",
    "BZ-4 — an observation carries the nearest five levels per side. A trail "
    "that would have wanted a sixth is not measured, and the cap is declared "
    "rather than discovered.",
    "BZ-5 — samples, symbols and windows are Milestone BY's, so BY-2 through "
    "BY-5 apply here unchanged: development is contaminated by construction, the "
    "holdout window opens later than development's, the holdout symbols are "
    "materially less liquid, and the universe is survivorship-filtered.",
    "BZ-6 — production geometry loses roughly 0.5R per trade on every sample "
    "measured so far. An exit family measured over it is being asked to improve "
    "a losing strategy, and MECHANISM_EVIDENCE over such a strategy is evidence "
    "about information, never about profitability.",
)


# ---------------------------------------------------------------------------
# 7. The seal.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BzPreregistration:
    """Everything BZ fixed in advance, in one addressable object."""

    preregistration_id: str
    research_question: str
    hypotheses: tuple[BzHypothesis, ...]
    geometry_policy_ids: tuple[str, ...]
    samples: tuple[SampleSpec, ...]
    observation: Mapping[str, Any]
    robustness: Mapping[str, Any]
    neighbourhood_note: str
    cost_scenarios: tuple[PaperCostPolicy, ...]
    deciding_cost_policy_id: str
    ambiguity_policy: tuple[str, ...]
    mechanism_criteria: tuple[CriterionSpec, ...]
    candidate_criteria: tuple[CriterionSpec, ...]
    classification_rules: tuple[str, ...]
    decompositions: tuple[str, ...]
    metrics: tuple[str, ...]
    limitations: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        """The canonical content the digest is taken over. **Order is fixed.**

        Every collection is emitted in declaration order rather than sorted: the
        order the hypotheses were written in is itself part of what was frozen,
        and re-ordering them is a change a reader should be able to see.
        """
        return {
            "preregistration_id": self.preregistration_id,
            "research_question": self.research_question,
            "hypotheses": [item.payload() for item in self.hypotheses],
            "geometry_policy_ids": list(self.geometry_policy_ids),
            "samples": [item.payload() for item in self.samples],
            "observation": dict(self.observation),
            "robustness": dict(self.robustness),
            "neighbourhood_note": self.neighbourhood_note,
            "cost_scenarios": [dict(item.to_payload()) for item in self.cost_scenarios],
            "deciding_cost_policy_id": self.deciding_cost_policy_id,
            "ambiguity_policy": list(self.ambiguity_policy),
            "mechanism_criteria": [item.payload() for item in self.mechanism_criteria],
            "candidate_criteria": [item.payload() for item in self.candidate_criteria],
            "classification_rules": list(self.classification_rules),
            "decompositions": list(self.decompositions),
            "metrics": list(self.metrics),
            "limitations": list(self.limitations),
        }

    def sample(self, name: str) -> SampleSpec:
        for item in self.samples:
            if item.name == name:
                return item
        raise SwingLabError(
            f"no pre-registered sample {name!r}; this study declares "
            f"{', '.join(item.name for item in self.samples)}"
        )

    def hypothesis_for(self, policy_id: str) -> BzHypothesis:
        for item in self.hypotheses:
            if item.policy_id == policy_id:
                return item
        raise SwingLabError(
            f"{policy_id!r} is NOT pre-registered; this pre-registration seals "
            f"{', '.join(sorted(BZ_HYPOTHESIS_IDS))}"
        )

    @property
    def control(self) -> BzHypothesis:
        for item in self.hypotheses:
            if item.role == "control":
                return item
        raise SwingLabError(  # pragma: no cover - BZ-H0 is declared above
            "this pre-registration declares no control"
        )


BZ_PRE_REGISTRATION: Final[BzPreregistration] = BzPreregistration(
    preregistration_id=BZ_PREREGISTRATION_ID,
    research_question=BZ_RESEARCH_QUESTION,
    hypotheses=BZ_HYPOTHESES,
    geometry_policy_ids=tuple(item.policy_id for item in BZ_GEOMETRIES),
    samples=SAMPLES,
    observation=OBSERVATION_SPEC,
    robustness=ROBUSTNESS_NEIGHBOURHOOD,
    neighbourhood_note=NEIGHBOURHOOD_IS_NOT_A_SEARCH,
    cost_scenarios=VALIDATION_COST_SCENARIOS,
    deciding_cost_policy_id=DECIDING_COST_POLICY_ID,
    ambiguity_policy=BZ_AMBIGUITY_POLICY,
    mechanism_criteria=BZ_MECHANISM_CRITERIA,
    candidate_criteria=BZ_CANDIDATE_CRITERIA,
    classification_rules=BZ_CLASSIFICATION_RULES,
    decompositions=BZ_REQUIRED_DECOMPOSITIONS,
    metrics=BZ_METRICS_REPORTED,
    limitations=BZ_LIMITATIONS,
)


def bz_preregistration_digest(
    preregistration: BzPreregistration = BZ_PRE_REGISTRATION,
) -> str:
    """SHA-256 over the canonical content. **The seal.**

    `sort_keys` is on so a dict literal reordered by an editor does not change
    the digest, while every *sequence* stays in declaration order because the
    order of the hypotheses is part of what was frozen. `ensure_ascii` is off and
    the encoding is explicit, so a hypothesis containing "≥" digests the same on
    every platform. Milestone BY's function, reproduced for BY's reasons.
    """
    if not isinstance(preregistration, BzPreregistration):
        raise TypeError("preregistration must be a BzPreregistration")
    canonical = json.dumps(
        preregistration.payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


#: **The seal, pinned.** Recomputed and compared by
#: `tests/test_swing_lab_persistence_preregistration.py`. If you are reading a
#: diff that changes this line, the pre-registration changed with it and every
#: result measured under the old digest describes a different experiment.
BZ_PREREGISTRATION_DIGEST: Final[str] = (
    "4d089ff43ec11e24e7e43e0a0f7ca377da996ee5a6391bb8f9c70d6922a3a175"
)


def verify_bz_preregistration(digest: str) -> bool:
    """Whether a recorded digest is the one this module currently seals."""
    if not isinstance(digest, str):
        raise TypeError("digest must be a str")
    return digest == bz_preregistration_digest()
