"""**Milestone CA's frozen pre-registration. Sealed before a single result was read.**

This module is CA's entire claim to be a test rather than a search, and it works
only if the following is literally true:

> Every null family, every threshold, every horizon, every matching rule, every
> seed, every sample boundary, every stratum and every verdict criterion below
> was fixed, and its SHA-256 recorded in `CA_PREREGISTRATION_DIGEST`, **before
> the first forward outcome was computed**.
> `tests/test_swing_lab_admission_preregistration.py` recomputes the digest from
> the content and fails if the two disagree.

The seal and the content live in the same file, so a change to either without the
other is a red test — Milestone BY's device, reused rather than reinvented.

**What CA asks, and why no previous milestone could ask it.**

BW rejected the timeframe variants, BX thirteen geometries, BY one geometry's
neighbourhood, BZ five exit mechanisms. Every one of those measurements is a
joint statement about admission *and* trade management, because their unit is a
trade. BZ then established that management is the losing half — which leaves
"the geometry is wrong" and "there is no signal to shape" indistinguishable.

CA separates them by changing the unit. Its unit is a decision instant and its
outcome is a fixed-horizon, direction-normalised, ATR-normalised excursion with
**no stop, no target, no exit and no cost**. The comparison is not "is FMITS
profitable"; it is "does FMITS select better than a matched entry it did not
select".

**The null must be hard to beat honestly.** A random timestamp from arbitrary
history would be confounded by volatility, regime, symbol, base rates, calendar
period and warm-up eligibility, and beating it would prove nothing. Every control
below is drawn from the **same symbol, the same sample, a comparable volatility
band and a bounded calendar neighbourhood**, and every one of those constraints
is declared here rather than chosen once the effect was known.

**What is deliberately absent.** No threshold is swept. No subgroup is defined
after a result. No horizon is promoted for looking best — `PRIMARY_HORIZON` is
fixed by a stated rule below and every other horizon is a diagnostic. And
**nothing in CA can promote anything**: `CaVerdict.is_approved_for_trading` and
`CaVerdict.earns_forward_test` are `False` for every member, including
`ADMISSION_EDGE_CANDIDATE`, because CA is a diagnosis and the promotion gates it
would need do not exist in this repository yet.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Final

from fmis.swing_lab.admission import (
    EXCURSION_RACE_ATR,
    FORWARD_HORIZONS,
    AdmissionStage,
    RaceOutcome,
)
from fmis.swing_lab.geometry_verdict import MAX_SINGLE_SYMBOL_SHARE
from fmis.swing_lab.metrics import SAMPLE_FLOOR
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.persistence import CHECKPOINT_BARS
# Samples, cost scenarios and the deciding scenario are IMPORTED from Milestone
# BY, never restated — the identical discipline Milestone BZ applied. CA measures
# the same populations over the same windows, so a CA figure and a BZ figure
# describe comparable instants; a copy here could drift and the milestones would
# silently stop being comparable. A test asserts identity, not equality.
from fmis.swing_lab.preregistration import (
    DECIDING_COST_POLICY_ID,
    SAMPLES,
    VALIDATION_COST_SCENARIOS,
    SampleSpec,
)
from fmis.swing_lab.validation_study import MAJOR_SYMBOLS, WALK_FORWARD_MONTHS

__all__ = [
    "CA_PREREGISTRATION_ID",
    "CA_PREREGISTRATION_DIGEST",
    "CA_RESEARCH_QUESTION",
    "CA_NULL_FAMILIES",
    "CA_FAMILY_IDS",
    "CaNullFamily",
    "CaEdgeQuestion",
    "CaControlSource",
    "CaDirectionRule",
    "CaVerdict",
    "CaPreregistration",
    "CA_PRE_REGISTRATION",
    "CA_MATCHING",
    "CA_RANDOMISATION",
    "CA_EDGE_CRITERIA",
    "CA_MECHANISM_CRITERIA",
    "CA_CLASSIFICATION_RULES",
    "CA_REQUIRED_DECOMPOSITIONS",
    "CA_DECLARED_STRATA",
    "CA_METRICS_REPORTED",
    "CA_LIMITATIONS",
    "CriterionSpec",
    "MatchingSpec",
    "RandomisationSpec",
    "PRIMARY_HORIZON",
    "PRIMARY_HORIZON_RULE",
    "MIN_ADMISSION_EDGE_ATR",
    "MIN_HORIZON_AGREEMENT",
    "NULL_PERCENTILE_BAR",
    "ca_preregistration_digest",
    "verify_ca_preregistration",
    "is_ca_pre_registered",
]

CA_PREREGISTRATION_ID: Final[str] = "ca-swing-admission-null-model-v1"

CA_RESEARCH_QUESTION: Final[str] = (
    "Does the current FMITS swing admission rule select execution-timeframe "
    "instants and directions whose forward outcomes are better than MATCHED "
    "entries it did not select, on the same symbols, in the same periods, at "
    "comparable volatility? This is NOT a strategy study, NOT a geometry study "
    "and NOT an exit study: no stop, target, exit rule or cost is applied to any "
    "outcome measured here, because Milestones BW, BX, BY and BZ established "
    "that trade management is the losing half of this strategy and a measurement "
    "carrying it cannot separate a bad entry from a bad exit."
)


# ---------------------------------------------------------------------------
# 1. The outcome. Fixed before any of it was computed.
# ---------------------------------------------------------------------------

#: The rule that picks the primary horizon, stated so the choice is checkable
#: rather than asserted. It resolves to exactly one member of
#: `fmis.swing_lab.admission.FORWARD_HORIZONS` and it was written down before any
#: forward outcome existed.
PRIMARY_HORIZON_RULE: Final[str] = (
    "The PRIMARY horizon is the shortest declared horizon strictly greater than "
    "Milestone BZ's measured median bars-to-peak on production geometry over the "
    "development sample, which is 19 execution bars (report 0036 §8). Over "
    "FORWARD_HORIZONS = (1, 3, 6, 12, 24, 60) that rule resolves uniquely to 24. "
    "The reasoning is that a swing admission should be judged at the point a "
    "typical favourable move has fully expressed itself rather than before it "
    "has (1-12 bars is intraday-to-two-day noise on a 4H timeframe) or so late "
    "that the window bound dominates the measurement (60 bars IS the bound). "
    "24 bars is 4 calendar days and 40 % of the inherited evaluation window. "
    "Every other horizon is a DIAGNOSTIC and none may be promoted to primary "
    "after the fact."
)

#: The one horizon the verdict is decided at. Chosen by `PRIMARY_HORIZON_RULE`.
PRIMARY_HORIZON: Final[int] = 24

if PRIMARY_HORIZON not in FORWARD_HORIZONS:  # pragma: no cover - a build error
    raise SwingLabError("the primary horizon must be one of the declared horizons")

#: The smallest effect, in ATR units at `PRIMARY_HORIZON`, that CA will call
#: economically meaningful.
#:
#: **Derived from the deciding cost scenario rather than chosen.** The deciding
#: policy is `swing-lab-conservative-10bps`, whose round trip costs 0.002 of
#: notional. The primary universe's median ATR/close over its own admitted
#: instants is 0.0202, so one round trip is 0.002 / 0.0202 = 0.099 ATR. An
#: admission edge smaller than the cost of acting on it is not an edge, so the
#: bar is set at the round-trip cost, rounded to 0.10. It happens to equal
#: Milestone BZ's own +0.10R mechanism bar, which keeps the two milestones'
#: magnitudes readable against each other, but it is derived here independently.
MIN_ADMISSION_EDGE_ATR: Final[float] = 0.10

#: How many of the six horizons must share the primary horizon's sign on
#: development before the primary result is called consistent with the profile.
#: Four of six is a simple majority plus one: it refuses a primary result that
#: only one horizon agrees with, without demanding a unanimity that no noisy
#: measurement over 155 instants could reach.
MIN_HORIZON_AGREEMENT: Final[int] = 4

#: Where in its own empirical null the observed development effect must fall.
#: The conventional one-sided 95th percentile, declared rather than discovered.
NULL_PERCENTILE_BAR: Final[float] = 95.0


# ---------------------------------------------------------------------------
# 2. The null families. Five, each with a prediction and a refutation.
# ---------------------------------------------------------------------------


class CaEdgeQuestion(str, Enum):
    """Which of the brief's four questions a family answers."""

    TIMING = "timing"
    DIRECTION = "direction"
    COMBINED = "combined"
    GATE = "gate"


class CaControlSource(str, Enum):
    """Where a family's control instant comes from.

    * `SAME_BAR` — the admission's own bar. Only the direction differs, so
      timing is held exactly fixed and nothing is drawn.
    * `MATCHED_ANY_STAGE` — an instant matched on symbol, sample, volatility and
      calendar proximity, at any rung of the admission ladder except `ADMITTED`.
      This is the opportunity-matched random-timing pool.
    * `MATCHED_UNCONFIRMED` — the same matching, restricted to
      `AdmissionStage.UNCONFIRMED`: production formed a directional thesis and
      the execution confirmation did not occur. **The eligible-but-rejected
      population, and production's own vocabulary rather than an invented
      "almost setup".**
    """

    SAME_BAR = "same_bar"
    MATCHED_ANY_STAGE = "matched_any_stage"
    MATCHED_UNCONFIRMED = "matched_unconfirmed"


class CaDirectionRule(str, Enum):
    """Which direction a control is measured in.

    * `FMITS` — the admission's own direction, so direction is held fixed and
      only timing varies.
    * `OPPOSITE` — the admission's direction reversed.
    * `RANDOM` — a seeded fair coin, drawn per replicate.
    * `CONTROL_OWN` — the control instant's own production direction. Only
      available where the control reached a rung that has one.
    """

    FMITS = "fmits"
    OPPOSITE = "opposite"
    RANDOM = "random"
    CONTROL_OWN = "control_own"


@dataclass(frozen=True, slots=True)
class CaNullFamily:
    """One pre-registered control, and what measuring it would settle.

    **A family with no stated refutation cannot fail, and a milestone whose
    families cannot fail is a search.** `__post_init__` refuses to construct one
    without both a `PREDICTION:` and a `REFUTED BY:` sentence — Milestone BZ's
    device, reused.
    """

    family_id: str
    question: CaEdgeQuestion
    control_source: CaControlSource
    direction_rule: CaDirectionRule
    hypothesis: str
    degeneracy: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.family_id, str) or not self.family_id.strip():
            raise SwingLabError("family_id must be a non-empty str")
        for marker in ("PREDICTION:", "REFUTED BY:"):
            if marker not in self.hypothesis:
                raise SwingLabError(
                    f"{self.family_id} states no {marker.rstrip(':')}; a family "
                    "with no stated refutation cannot fail, and a milestone "
                    "whose families cannot fail is a search"
                )
        if (
            self.direction_rule is CaDirectionRule.CONTROL_OWN
            and self.control_source is CaControlSource.SAME_BAR
        ):
            raise SwingLabError(
                f"{self.family_id} takes the control's own direction at the "
                "admission's own bar, which is the admission itself"
            )

    @property
    def draws_a_control_instant(self) -> bool:
        """Whether this family needs a matched instant drawn for it."""
        return self.control_source is not CaControlSource.SAME_BAR

    @property
    def draws_a_direction(self) -> bool:
        """Whether this family needs a seeded coin flip."""
        return self.direction_rule is CaDirectionRule.RANDOM

    @property
    def is_degenerate_at_primary(self) -> bool:
        """Whether its primary-metric result is algebraically fixed by FMITS's own.

        Stated rather than hidden: a fixed-horizon direction-normalised return is
        **antisymmetric in direction**, so a control taken at the admission's own
        bar in the opposite direction returns exactly the negative of the
        admission's. Its paired difference is therefore exactly twice the
        admission's own return and contains no information the admission's mean
        does not already carry. It is measured and reported as a consistency
        check, and a report that presented it as independent evidence would be
        double-counting one number.
        """
        return self.degeneracy is not None

    def payload(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "question": self.question.value,
            "control_source": self.control_source.value,
            "direction_rule": self.direction_rule.value,
            "hypothesis": self.hypothesis,
            "degeneracy": self.degeneracy,
        }


CA_NULL_FAMILIES: Final[tuple[CaNullFamily, ...]] = (
    CaNullFamily(
        family_id="ca_null_matched_timing",
        question=CaEdgeQuestion.TIMING,
        control_source=CaControlSource.MATCHED_ANY_STAGE,
        direction_rule=CaDirectionRule.FMITS,
        hypothesis=(
            "Holding the direction at FMITS's own, an admitted instant's forward "
            "excursion exceeds that of instants matched on symbol, sample, "
            "volatility band and calendar neighbourhood that the engine did not "
            "admit. "
            "PREDICTION: if the admission rule contains timing information, the "
            "paired difference is positive on development and keeps its sign on "
            "temporal validation and on the never-measured holdout. "
            "REFUTED BY: a paired difference at or below zero on development, or "
            "a sign that does not survive both unseen samples, or a development "
            "effect inside its own empirical null's central 90 %."
        ),
    ),
    CaNullFamily(
        family_id="ca_null_opposite_direction",
        question=CaEdgeQuestion.DIRECTION,
        control_source=CaControlSource.SAME_BAR,
        direction_rule=CaDirectionRule.OPPOSITE,
        hypothesis=(
            "At the admission's own instant, FMITS's chosen side outperforms the "
            "reverse of it. "
            "PREDICTION: if direction selection carries information, the paired "
            "difference is positive. "
            "REFUTED BY: a paired difference at or below zero. "
            "DECLARED DEGENERACY: see `degeneracy` — this family's primary-metric "
            "result is algebraically twice the admission's own mean return and is "
            "reported as a consistency check, never as independent evidence."
        ),
        degeneracy=(
            "A fixed-horizon direction-normalised ATR return is antisymmetric in "
            "direction, so the opposite-direction control at the same bar equals "
            "MINUS the admission's own return exactly. The paired difference is "
            "therefore identically 2x the admission's return and carries no "
            "information beyond it. It is sealed and measured anyway because its "
            "MFE/MAE diagnostics are NOT degenerate — a long's favourable "
            "excursion is a short's adverse one — and because omitting a control "
            "the brief names would be a silent narrowing of the experiment."
        ),
    ),
    CaNullFamily(
        family_id="ca_null_random_direction_same_bar",
        question=CaEdgeQuestion.DIRECTION,
        control_source=CaControlSource.SAME_BAR,
        direction_rule=CaDirectionRule.RANDOM,
        hypothesis=(
            "At the admission's own instant, FMITS's chosen side outperforms a "
            "seeded fair coin. This asks a different question from the opposite "
            "control: a coin is right half the time, so this measures the value "
            "of KNOWING the side rather than the cost of inverting it. "
            "PREDICTION: if direction selection carries information, the paired "
            "difference is positive and stable across the five declared master "
            "seeds. "
            "REFUTED BY: a paired difference at or below zero, or a sign that "
            "changes between master seeds."
        ),
    ),
    CaNullFamily(
        family_id="ca_null_matched_timing_random_direction",
        question=CaEdgeQuestion.COMBINED,
        control_source=CaControlSource.MATCHED_ANY_STAGE,
        direction_rule=CaDirectionRule.RANDOM,
        hypothesis=(
            "The complete admission — FMITS's instant AND FMITS's direction — "
            "outperforms a matched instant entered on a seeded fair coin. This is "
            "the brief's combined admission edge and the closest thing CA "
            "measures to 'is the engine worth having'. "
            "PREDICTION: if admission as a whole contains information, the paired "
            "difference is positive on development, keeps its sign on both unseen "
            "samples, and clears the declared magnitude. "
            "REFUTED BY: a paired difference at or below zero on development, a "
            "sign that does not survive both unseen samples, or a magnitude below "
            "the round-trip cost of acting on it."
        ),
    ),
    CaNullFamily(
        family_id="ca_null_eligible_but_rejected",
        question=CaEdgeQuestion.GATE,
        control_source=CaControlSource.MATCHED_UNCONFIRMED,
        direction_rule=CaDirectionRule.CONTROL_OWN,
        hypothesis=(
            "An admitted setup outperforms a matched instant at which production "
            "had formed the SAME KIND of directional thesis — decision context "
            "sufficient, context-role regime trending, family tally agreed — and "
            "which the execution-timeframe confirmation gate then declined. Each "
            "control is measured in its own production direction, so this "
            "isolates the confirmation gate and nothing else. "
            "PREDICTION: if the confirmation gate adds information, the paired "
            "difference is positive on all three samples. "
            "REFUTED BY: a paired difference at or below zero on development, or "
            "a sign that does not survive both unseen samples. A difference at "
            "zero means the gate separates nothing and the engine's last stage is "
            "costing opportunities for no measured return."
        ),
    ),
)

CA_FAMILY_IDS: Final[frozenset[str]] = frozenset(
    item.family_id for item in CA_NULL_FAMILIES
)

if len(CA_FAMILY_IDS) != len(CA_NULL_FAMILIES):  # pragma: no cover - a build error
    raise SwingLabError("two CA null families share a family_id")


def is_ca_pre_registered(family_id: str) -> bool:
    """Whether this null family was sealed before results existed. **The gate.**"""
    if not isinstance(family_id, str):
        raise TypeError("family_id must be a str")
    return family_id in CA_FAMILY_IDS


# ---------------------------------------------------------------------------
# 3. The matching rule. Declared BEFORE any outcome was computed.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MatchingSpec:
    """How a control instant is drawn for one admission. **The whole null.**

    Every constraint here exists to remove a confound the brief names, and each
    was set from a property of the INPUTS — pool sizes, eligibility counts — with
    no forward outcome computed. Reading pool sizes before sealing is what makes
    these numbers defensible; reading an effect would have made them a search.
    """

    same_symbol: bool
    same_sample: bool
    calendar_radius_tiers: tuple[int, ...]
    minimum_separation_bars: int
    atr_log_tolerance: float
    minimum_pool: int
    excludes_admitted: bool
    rationale: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "same_symbol": self.same_symbol,
            "same_sample": self.same_sample,
            "calendar_radius_tiers": list(self.calendar_radius_tiers),
            "minimum_separation_bars": self.minimum_separation_bars,
            "atr_log_tolerance": self.atr_log_tolerance,
            "minimum_pool": self.minimum_pool,
            "excludes_admitted": self.excludes_admitted,
            "rationale": list(self.rationale),
        }


CA_MATCHING: Final[MatchingSpec] = MatchingSpec(
    same_symbol=True,
    same_sample=True,
    # 540 bars is 90 calendar days on a 4H timeframe; 1080 is 180; 2160 is 360.
    # Tiers are tried in order and the FIRST that reaches `minimum_pool` is used,
    # so a control is drawn from the tightest calendar neighbourhood that can
    # populate a pool. Which tier each match used is recorded and reported.
    calendar_radius_tiers=(540, 1080, 2160),
    minimum_separation_bars=60,
    atr_log_tolerance=0.60,
    minimum_pool=10,
    excludes_admitted=True,
    rationale=(
        "SAME SYMBOL, exactly. A control drawn from another symbol would carry "
        "that symbol's drift, liquidity and beta, and the admission engine does "
        "not choose symbols — it is handed a universe.",
        "SAME SAMPLE, exactly. A control crossing a sample boundary would import "
        "the holdout into development, which is the contamination Milestone BY's "
        "own defect BY-D6 exists to prevent one layer down.",
        "MINIMUM SEPARATION of 60 execution bars, which is exactly the inherited "
        "evaluation window. A control nearer than that would share forward bars "
        "with the admission it is being compared against, and the paired "
        "difference would be partly a number minus itself. This is the single "
        "most important constraint against pseudoreplication and it is why the "
        "separation equals the window rather than some smaller round number.",
        "CALENDAR RADIUS in tiers of 90, 180 and 360 days, tightest first. A "
        "control from a distant year would be matched on volatility but not on "
        "market-wide risk regime; a radius too tight would leave the "
        "eligible-but-rejected pool empty for a quarter of admissions. The tiers "
        "resolve that without a per-family knob: the escalation rule is one rule "
        "for every family, and the tier used is reported per match.",
        "ATR LOG TOLERANCE of 0.60, i.e. a control's ATR within [0.55x, 1.82x] of "
        "the admission's. The outcome is already divided by ATR, so this band is "
        "not there to equalise the denominator — it is there to keep the control "
        "in a comparable volatility ENVIRONMENT. It was set to the value at which "
        "the eligible-but-rejected control retains at least 97 % of admissions on "
        "every sample, because a control family that silently discards a quarter "
        "of its admissions is a biased control, not a strict one.",
        "ADMITTED INSTANTS ARE EXCLUDED from every control pool. A null "
        "containing FMITS admissions is partly a comparison of FMITS with "
        "itself. Instants at every other rung — including CONFIRMED_REPEAT — are "
        "deliberately KEPT, because they are moments the engine did not admit and "
        "removing them would quietly make the null easier.",
        "AN ADMISSION WHOSE POOL CANNOT REACH `minimum_pool` AT THE WIDEST TIER "
        "IS UNMATCHED and is excluded from that family with its count reported. "
        "It is never matched against a smaller pool, and never silently dropped.",
    ),
)


# ---------------------------------------------------------------------------
# 4. Randomisation. Seeded, reproducible, and justified before the fact.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RandomisationSpec:
    """How randomness is drawn, and how many times. **Deterministic by construction.**"""

    master_seeds: tuple[int, ...]
    primary_seed: int
    draws_per_admission: int
    null_replicates: int
    bootstrap_replicates: int
    seed_derivation: str
    rationale: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.primary_seed not in self.master_seeds:
            raise SwingLabError("the primary seed must be one of the master seeds")

    def payload(self) -> dict[str, Any]:
        return {
            "master_seeds": list(self.master_seeds),
            "primary_seed": self.primary_seed,
            "draws_per_admission": self.draws_per_admission,
            "null_replicates": self.null_replicates,
            "bootstrap_replicates": self.bootstrap_replicates,
            "seed_derivation": self.seed_derivation,
            "rationale": list(self.rationale),
        }


CA_RANDOMISATION: Final[RandomisationSpec] = RandomisationSpec(
    master_seeds=(1, 2, 3, 4, 5),
    primary_seed=1,
    draws_per_admission=200,
    null_replicates=1000,
    bootstrap_replicates=2000,
    seed_derivation=(
        "Every draw's seed is SHA-256 over the UTF-8 of "
        "'{master}|{family_id}|{sample}|{symbol}|{bar_index}|{replicate}', "
        "truncated to 64 bits. It is derived from IDENTITY rather than from "
        "iteration order, so a draw does not move when a symbol is added, when a "
        "family is reordered, or when PYTHONHASHSEED changes. Python's built-in "
        "`hash` is never used for this: it is salted per process and would make "
        "the experiment irreproducible across runs on the same machine."
    ),
    rationale=(
        "200 DRAWS PER ADMISSION. Each admission's control term is the mean over "
        "its draws, so the control's own sampling error enters the effect at "
        "1/sqrt(200) = 7 % of the per-instant control spread — small against the "
        "between-admission spread that the bootstrap measures. Pool medians are "
        "roughly 400-550 instants, so 200 draws sample a large fraction of each "
        "pool without exhausting it.",
        "1000 NULL REPLICATES. The empirical null is built by pairing two "
        "INDEPENDENT control draws per admission and taking the same mean "
        "difference, which is centred at zero by construction and carries the "
        "same clustering and the same sample size as the observed effect. 1000 "
        "replicates resolve a percentile to 0.1, which is finer than the 95.0 bar "
        "the verdict reads.",
        "2000 BOOTSTRAP REPLICATES, resampled BY SYMBOL rather than by "
        "admission. Admissions on one symbol share its drift and its regime and "
        "are not independent; resampling admissions individually would report an "
        "interval too narrow by exactly that dependence. 2000 is the conventional "
        "count for a stable 95 % percentile interval.",
        "FIVE MASTER SEEDS, with seed 1 primary and 2-5 existing ONLY to answer "
        "whether a result is a property of the data or of one lucky draw. No "
        "verdict may be read from a non-primary seed; they can only make a "
        "criterion FAIL, never pass, and the criterion they feed is a sign "
        "agreement test rather than a magnitude.",
        "EVERY NUMBER ABOVE WAS FIXED BEFORE THE FIRST FORWARD OUTCOME WAS "
        "COMPUTED. None was raised after a result fell short of a bar.",
    ),
)


# ---------------------------------------------------------------------------
# 5. Verdicts, and the criteria that decide them.
# ---------------------------------------------------------------------------


class CaVerdict(str, Enum):
    """What CA is entitled to conclude. **No member approves anything.**

    * `NO_EDGE` — measured, and the family did not clear its development bar.
    * `INCONCLUSIVE` — the test could not be run: too few matched admissions on
      some sample. **Not a refutation** — reporting an unrun test as a failure
      claims evidence against a hypothesis nobody measured, which is the defect
      Milestone BZ recorded as BZ-D1 and fixed.
    * `MECHANISM_EVIDENCE` — a real, meaningful effect on development that did
      not survive both unseen samples. A finding about information, and never a
      reason to change a rule.
    * `ADMISSION_EDGE_CANDIDATE` — every sealed criterion met. **This still
      approves nothing**: it means the admission engine is worth preserving and
      decomposing in a later milestone, not that it may be traded.
    """

    NO_EDGE = "no_edge"
    INCONCLUSIVE = "inconclusive"
    MECHANISM_EVIDENCE = "mechanism_evidence"
    ADMISSION_EDGE_CANDIDATE = "admission_edge_candidate"

    @property
    def is_approved_for_trading(self) -> bool:
        """**Always `False`.** Asserted over the whole enum by the test suite."""
        return False

    @property
    def earns_forward_test(self) -> bool:
        """**Always `False`**, including for `ADMISSION_EDGE_CANDIDATE`.

        Milestones BX, BY and BZ each had a verdict that earned a forward test,
        because each measured a complete policy — an entry, a geometry and an
        exit — that could in principle be run. CA measures none of those: an
        admission edge with no geometry attached is not a strategy and there is
        nothing to forward-test. The promotion gates a candidate would need do
        not exist in this repository, and inventing one inside a research
        milestone is how a laboratory becomes a trading system.
        """
        return False


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


CA_EDGE_CRITERIA: Final[tuple[CriterionSpec, ...]] = (
    CriterionSpec(
        "pre_registered",
        "the family appears in CA_NULL_FAMILIES and the study's manifest carries "
        "this pre-registration's digest",
        None,
    ),
    CriterionSpec(
        "causal",
        "every control identity was proven to depend only on information "
        "available at or before its matched decision point, by the milestone's "
        "own future-mutation suite WITH a non-vacuity control",
        None,
    ),
    CriterionSpec(
        "sample",
        f"at least {SAMPLE_FLOOR} MATCHED admissions on each of the three "
        "samples; below the floor the criterion is UNMEASURABLE and never False",
        float(SAMPLE_FLOOR),
    ),
    CriterionSpec(
        "development_effect",
        f"a paired effect of at least {MIN_ADMISSION_EDGE_ATR:g} ATR at horizon "
        f"{PRIMARY_HORIZON} on development",
        MIN_ADMISSION_EDGE_ATR,
    ),
    CriterionSpec(
        "validation_sign",
        "a strictly positive paired effect on temporal validation; an edge that "
        "exists only where it was developed is not an edge",
        0.0,
    ),
    CriterionSpec(
        "holdout_sign",
        "a strictly positive paired effect on twenty-one never-measured symbols",
        0.0,
    ),
    CriterionSpec(
        "economically_meaningful",
        f"an effect of at least {MIN_ADMISSION_EDGE_ATR:g} ATR on ALL THREE "
        "samples, not merely a positive number — the bar is the round-trip cost "
        f"of the deciding scenario {DECIDING_COST_POLICY_ID}",
        MIN_ADMISSION_EDGE_ATR,
    ),
    CriterionSpec(
        "null_percentile",
        f"the development effect at or above the {NULL_PERCENTILE_BAR:g}th "
        "percentile of its own empirical null, built from paired independent "
        "control draws with the same clustering and the same sample size",
        NULL_PERCENTILE_BAR,
    ),
    CriterionSpec(
        "bootstrap_excludes_zero",
        "the lower bound of the 95 % symbol-clustered bootstrap interval on "
        "development strictly above zero",
        0.0,
    ),
    CriterionSpec(
        "concentration",
        "no single symbol contributing more than "
        f"{float(MAX_SINGLE_SYMBOL_SHARE):.0%} of the gross absolute paired "
        "difference on development",
        float(MAX_SINGLE_SYMBOL_SHARE),
    ),
    CriterionSpec(
        "seed_stable",
        "the sign of the development effect identical under all five declared "
        "master seeds",
        None,
    ),
    CriterionSpec(
        "long_short_consistent",
        "every direction cohort that reaches the sample floor on development "
        f"({SAMPLE_FLOOR} matched admissions) sharing the aggregate's sign; a "
        "cohort below the floor is UNMEASURABLE and never False",
        float(SAMPLE_FLOOR),
    ),
    CriterionSpec(
        "horizon_profile",
        f"at least {MIN_HORIZON_AGREEMENT} of the {len(FORWARD_HORIZONS)} "
        "declared horizons sharing the primary horizon's sign on development, so "
        "a primary result contradicted by its own profile cannot pass",
        float(MIN_HORIZON_AGREEMENT),
    ),
    CriterionSpec(
        "walk_forward",
        "at least half of the non-empty development walk-forward windows sharing "
        f"the aggregate's sign, at {WALK_FORWARD_MONTHS}-month windows",
        0.5,
    ),
)

#: What a family must clear to be reported as `MECHANISM_EVIDENCE`. A **strict
#: subset** of the edge criteria, and deliberately so: it asks whether a real
#: effect exists where the engine was developed, and says nothing about whether
#: it generalises. It can never promote anything — `CaVerdict.earns_forward_test`
#: is `False` for every member, `MECHANISM_EVIDENCE` included.
CA_MECHANISM_CRITERIA: Final[tuple[str, ...]] = (
    "pre_registered",
    "causal",
    "sample",
    "development_effect",
    "null_percentile",
    "bootstrap_excludes_zero",
    "concentration",
    "seed_stable",
)

_EDGE_NAMES: Final[frozenset[str]] = frozenset(
    item.name for item in CA_EDGE_CRITERIA
)
for _name in CA_MECHANISM_CRITERIA:  # pragma: no cover - a build error
    if _name not in _EDGE_NAMES:
        raise SwingLabError(
            f"mechanism criterion {_name!r} is not one of the edge criteria"
        )

CA_CLASSIFICATION_RULES: Final[tuple[str, ...]] = (
    "A family clears ADMISSION_EDGE_CANDIDATE only when EVERY criterion in "
    "CA_EDGE_CRITERIA passes. One failure is a failure; there is no weighting, "
    "no scoring and no majority.",
    "A criterion that could not be EVALUATED — a cohort below the sample floor, "
    "a sample that was never opened — is UNMEASURABLE. It is never reported as "
    "False, because reporting an unrun test as a refutation claims evidence "
    "against a hypothesis nobody measured. A family holding any unmeasurable "
    "criterion and no failed one is INCONCLUSIVE, not NO_EDGE.",
    "MECHANISM_EVIDENCE requires every criterion in CA_MECHANISM_CRITERIA and is "
    "reported when those pass and a generalisation criterion fails. It is a "
    "finding about information and it may never change a production rule.",
    "ADMISSION_EDGE_CANDIDATE DOES NOT MEAN APPROVED FOR TRADING, and does not "
    "earn a forward, shadow or paper test. CA measures admission with no "
    "geometry attached; there is no complete policy here to run.",
    "No subgroup, stratum, horizon or symbol cut invented AFTER results may "
    "carry any verdict. CA_DECLARED_STRATA is the complete list of conditional "
    "analyses this milestone is entitled to draw a conclusion from, and anything "
    "outside it is reported under POST_HOC and explicitly not promoted.",
    "A family's verdict is decided at PRIMARY_HORIZON alone. The other five "
    "horizons feed exactly one criterion — horizon_profile — and can only make a "
    "verdict fail, never pass.",
    "CONDITIONAL EDGE. Where a family's AGGREGATE fails but one cut of one "
    "DECLARED stratum clears every mechanism criterion on all three samples, that "
    "cut is reported as CONDITIONAL MECHANISM_EVIDENCE. It may never reach "
    "ADMISSION_EDGE_CANDIDATE, may never become a production filter, and may "
    "never be described as validated. A stratum that was not declared here cannot "
    "carry even that, whatever its numbers.",
)

#: The conditional analyses declared BEFORE results, and the only ones from which
#: CA may draw a conclusion. Everything else is POST_HOC by construction.
CA_DECLARED_STRATA: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "name": "direction",
        "cuts": ["long", "short"],
        "why": (
            "The universes are strongly asymmetric — the holdout admits 194 "
            "shorts against 40 longs — and an aggregate effect could be one side "
            "carrying the other. Declared because the imbalance is a property of "
            "the captured inputs and was visible before any outcome."
        ),
    },
    {
        "name": "context_regime_volatility",
        "cuts": ["contracting", "steady", "expanding"],
        "why": (
            "The brief's question D asks whether admission carries information "
            "only under specific market states. This is the production regime "
            "engine's own volatility vocabulary, read from the captured "
            "candidates rather than invented, and all three members are declared "
            "so none can be chosen after the fact."
        ),
    },
    {
        "name": "symbol_class",
        "cuts": ["major", "non_major"],
        "why": (
            "Milestone BY's own split, imported by identity from MAJOR_SYMBOLS "
            "rather than restated. The holdout is materially less liquid than "
            "development and a liquidity-driven effect must be visible as one."
        ),
    },
    {
        "name": "walk_forward",
        "cuts": [f"{WALK_FORWARD_MONTHS}-month windows, per universe, never pooled"],
        "why": (
            "Milestone BY's published conclusion was wrong because it pooled "
            "three samples into one walk-forward curve and the traded universe "
            "doubled mid-curve. CA emits one curve per universe and a test "
            "refuses a pooled one by name."
        ),
    },
)

CA_REQUIRED_DECOMPOSITIONS: Final[tuple[str, ...]] = (
    "matched admissions, unmatched admissions and unique symbols, per family and "
    "per sample",
    "effect, symbol-clustered bootstrap interval, and percentile within the "
    "empirical null, per family and per sample",
    "the full six-horizon profile, per family and per sample",
    "MFE and MAE at every horizon, for admissions and for controls",
    "long/short, volatility regime and major/non-major cuts, each refused rather "
    "than stated below the sample floor",
    "one walk-forward curve PER UNIVERSE, never pooled",
    "the gate ladder census — how many instants stopped at each rung — and the "
    "forward outcome distribution of each rung, per sample",
    "the calendar-radius tier each match used, so an escalated match is visible "
    "rather than hidden inside an average",
)

CA_METRICS_REPORTED: Final[tuple[str, ...]] = (
    "forward direction-normalised ATR return at 1, 3, 6, 12, 24 and 60 execution "
    "bars",
    "maximum favourable excursion in ATR units at every horizon",
    "maximum adverse excursion in ATR units at every horizon",
    "the probability of a positive direction-normalised return at every horizon",
    f"the probability of reaching +{EXCURSION_RACE_ATR} ATR favourable BEFORE "
    f"{EXCURSION_RACE_ATR} ATR adverse within each horizon, with bars that span "
    "both thresholds REFUSED as ambiguous and counted beside the rate rather "
    "than ordered by a guess",
    "the paired difference against each null family, per admission",
    "the empirical null distribution of that paired difference",
)

CA_LIMITATIONS: Final[tuple[str, ...]] = (
    "CA-1 — THE OUTCOME IS NOT A TRADE. No stop, target, exit or cost is applied. "
    "A positive admission effect therefore does NOT imply a profitable strategy: "
    "it says the engine selects better-than-matched moments, and BW-BZ have "
    "already shown that the geometry applied to those moments loses. The two "
    "findings are compatible and CA exists precisely to separate them.",
    "CA-2 — THE HORIZON BOUND IS INHERITED. Every horizon is bounded by BW's "
    "60-bar (10 calendar day) evaluation window so CA stays comparable with BW, "
    "BX, BY and BZ. Milestone BZ recorded this as the most questionable inherited "
    "assumption in the series for a strategy described as 'swing', and CA does "
    "not resolve it — it inherits it knowingly.",
    "CA-3 — MATCHING CANNOT REMOVE AN UNOBSERVED CONFOUND. Controls are matched "
    "on symbol, sample, volatility band and calendar neighbourhood. Anything that "
    "predicts returns and is correlated with admission but not with those four is "
    "not removed, and CA cannot name what it did not measure.",
    "CA-4 — THE ELIGIBLE-BUT-REJECTED POPULATION IS CLASSIFIED AT DECISION TIME, "
    "which means some of its instants belong to opportunities that confirmed "
    "LATER. That is deliberate: conditioning on whether an opportunity eventually "
    "confirmed would read the future into the control's own identity. The "
    "consequence is that this control is not 'opportunities the engine never "
    "took' but 'moments at which it had not yet taken one', and it is the "
    "stronger of the two definitions only because the other is unavailable "
    "without lookahead.",
    "CA-5 — SAMPLES, SYMBOLS AND WINDOWS ARE MILESTONE BY'S, imported by "
    "identity, so BY-2 to BY-5 apply unchanged: development is contaminated by "
    "construction, the holdout window opens later, the holdout symbols are "
    "materially less liquid, and the universe is survivorship-filtered.",
    "CA-6 — THE INPUTS ARE MILESTONE BZ'S CAPTURE, whose own limitation stands: "
    "only execution-timeframe bars are persisted. The 1D and 1W series that "
    "PRODUCED the structural readings are not stored, only the readings. CA "
    "therefore cannot ask why a pivot was detected, and its setup-timeframe ATR "
    "is available only at admitted instants. CA needs neither, and says so rather "
    "than working around it.",
    "CA-7 — ADMISSIONS ARE NOT INDEPENDENT OF EACH OTHER. The 60-bar minimum "
    "separation guarantees a control does not overlap its own admission's forward "
    "window, but two ADMISSIONS on one symbol may still fall within 60 bars of "
    "each other. The symbol-clustered bootstrap absorbs this at the symbol level; "
    "it is not eliminated, and the count of admissions within 60 bars of another "
    "on the same symbol is reported rather than assumed to be zero.",
)


# ---------------------------------------------------------------------------
# 6. The sealed document.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CaPreregistration:
    """Everything CA fixed before it measured anything. **Digested as one document.**"""

    preregistration_id: str
    research_question: str
    horizons: tuple[int, ...]
    primary_horizon: int
    primary_horizon_rule: str
    families: tuple[CaNullFamily, ...]
    matching: MatchingSpec
    randomisation: RandomisationSpec
    samples: tuple[SampleSpec, ...]
    cost_scenarios: tuple[Any, ...]
    deciding_cost_policy_id: str
    edge_criteria: tuple[CriterionSpec, ...]
    mechanism_criteria: tuple[str, ...]
    classification_rules: tuple[str, ...]
    declared_strata: tuple[Mapping[str, Any], ...]
    required_decompositions: tuple[str, ...]
    metrics: tuple[str, ...]
    limitations: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "preregistration_id": self.preregistration_id,
            "research_question": self.research_question,
            "horizons": list(self.horizons),
            "primary_horizon": self.primary_horizon,
            "primary_horizon_rule": self.primary_horizon_rule,
            "families": [item.payload() for item in self.families],
            "matching": self.matching.payload(),
            "randomisation": self.randomisation.payload(),
            "samples": [item.payload() for item in self.samples],
            "cost_scenarios": [
                {
                    "policy_id": item.policy_id,
                    "fee_rate": str(item.fee_rate),
                    "slippage_rate": str(item.slippage_rate),
                }
                for item in self.cost_scenarios
            ],
            "deciding_cost_policy_id": self.deciding_cost_policy_id,
            "edge_criteria": [item.payload() for item in self.edge_criteria],
            "mechanism_criteria": list(self.mechanism_criteria),
            "classification_rules": list(self.classification_rules),
            "declared_strata": [dict(item) for item in self.declared_strata],
            "required_decompositions": list(self.required_decompositions),
            "metrics": list(self.metrics),
            "limitations": list(self.limitations),
            "checkpoint_bars_inherited_from_bz": list(CHECKPOINT_BARS),
            "max_single_symbol_share": str(MAX_SINGLE_SYMBOL_SHARE),
            "sample_floor": SAMPLE_FLOOR,
            "walk_forward_months": WALK_FORWARD_MONTHS,
            "major_symbols": sorted(MAJOR_SYMBOLS),
            "min_admission_edge_atr": MIN_ADMISSION_EDGE_ATR,
            "min_horizon_agreement": MIN_HORIZON_AGREEMENT,
            "null_percentile_bar": NULL_PERCENTILE_BAR,
            "admission_stages": [item.value for item in AdmissionStage],
            "excursion_race_atr": str(EXCURSION_RACE_ATR),
            "race_outcomes": [item.value for item in RaceOutcome],
        }


CA_PRE_REGISTRATION: Final[CaPreregistration] = CaPreregistration(
    preregistration_id=CA_PREREGISTRATION_ID,
    research_question=CA_RESEARCH_QUESTION,
    horizons=FORWARD_HORIZONS,
    primary_horizon=PRIMARY_HORIZON,
    primary_horizon_rule=PRIMARY_HORIZON_RULE,
    families=CA_NULL_FAMILIES,
    matching=CA_MATCHING,
    randomisation=CA_RANDOMISATION,
    samples=SAMPLES,
    cost_scenarios=VALIDATION_COST_SCENARIOS,
    deciding_cost_policy_id=DECIDING_COST_POLICY_ID,
    edge_criteria=CA_EDGE_CRITERIA,
    mechanism_criteria=CA_MECHANISM_CRITERIA,
    classification_rules=CA_CLASSIFICATION_RULES,
    declared_strata=CA_DECLARED_STRATA,
    required_decompositions=CA_REQUIRED_DECOMPOSITIONS,
    metrics=CA_METRICS_REPORTED,
    limitations=CA_LIMITATIONS,
)


def ca_preregistration_digest(
    preregistration: CaPreregistration = CA_PRE_REGISTRATION,
) -> str:
    """SHA-256 over the canonical content. **The seal.**

    `sort_keys` is on so a dict literal reordered by an editor does not change the
    digest, while every *sequence* stays in declaration order because the order of
    the families is part of what was frozen. `ensure_ascii` is off and the
    encoding is explicit, so a hypothesis containing a non-ASCII character digests
    the same on every platform. Milestone BY's function, reproduced for BY's
    reasons.
    """
    if not isinstance(preregistration, CaPreregistration):
        raise TypeError("preregistration must be a CaPreregistration")
    canonical = json.dumps(
        preregistration.payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


#: **The seal, pinned.** Recomputed and compared by
#: `tests/test_swing_lab_admission_preregistration.py`. If you are reading a diff
#: that changes this line, the pre-registration changed with it and every result
#: measured under the old digest describes a different experiment.
CA_PREREGISTRATION_DIGEST: Final[str] = (
    "910cad28001ee18d9630f685e454bfd6bf24fb7d78b907e89172371b83f25e8a"
)


def verify_ca_preregistration(digest: str) -> bool:
    """Whether a recorded digest is the one this module currently seals."""
    if not isinstance(digest, str):
        raise TypeError("digest must be a str")
    return digest == ca_preregistration_digest()
