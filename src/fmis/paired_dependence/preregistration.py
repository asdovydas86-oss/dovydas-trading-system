"""**Milestone CD's frozen pre-registration. Sealed before the first real estimate.**

Milestone CA sealed a hypothesis before measuring an effect. Milestone CC sealed
the rules that decide which instruments count. CD seals the thing that is most
dangerous to leave open in a *measurement* milestone: **the estimator, its
grouping axes, its uncertainty method, its sample floors and its verdict
boundaries.**

The danger is specific and it is not hypothetical. CD's decision-relevant
threshold is ``1 / K*`` — a between-asset correlation of roughly 0.002 — and the
panel available to measure it is fifteen economic assets carrying a few hundred
paired observations. An analyst who ran the estimator first and chose the block
length, the cell reduction, the weighting and the verdict boundary afterwards
could produce almost any answer they wanted from that grid and would never have
to lie once. So the whole grid is fixed here, its SHA-256 is recorded in
`CD_PREREGISTRATION_DIGEST`, and `tests/test_paired_dependence_preregistration.py`
recomputes the digest from the content and fails if the two disagree.

**What CD asks.**

> Across the economic assets Milestone CA actually measured, how dependent are
> the paired admission-versus-control forward-effect observations that CA's
> estimate is computed from — within one asset, and between assets at the same
> time — and what does that dependence do to Milestone CB's information
> requirement?

**What CD does not ask, and cannot answer.** Whether an admission edge exists —
CA's `NO_EDGE` stands. Whether the design is powered — CB's `UNDERPOWERED`
stands. Whether a universe can be built — CC's `INFEASIBLE` stands unless CD
supplies a mathematically valid refinement, which is recorded *separately* from
CC's historical verdict rather than written over it. Nothing here approves
trading, paper trading, shadow trading, a threshold change or a strategy, and
`fmis.paired_dependence.models` asserts that over both verdict enums.

**Holdout contamination rule.** Every choice in this file was fixed before any
real paired difference was read, on *any* sample. The holdout is therefore
measured under the same sealed design as development and validation rather than
being withheld: withholding it would not protect anything once the design is
frozen, and it would leave the milestone's most-informative sample — 234
admissions over 21 assets — unused for a question that is starved of assets. What
the seal forbids is the reverse: **no CD threshold, block length, reduction,
weighting, floor or verdict boundary may be revised after any sample is read**,
and `fmis.paired_dependence.controls` plus the leakage regressions assert that a
CD decision path cannot consult a realised difference.

**The seal was pinned twice, and the second time is recorded rather than hidden.**
It was first fixed at `e2656f1f…` before any capture completed and before any
paired difference existed. It was then re-pinned at `28f8ebed…` — still before
any real estimate was computed — because one sealed sentence named a helper
function by its identifier, and that identifier had to change to satisfy the
repository's zero-collision export invariant. The sentence now names the
*concept* rather than the function, so no future rename can move this digest. **No
threshold, axis, floor, grid, rule or verdict boundary differs between the two
digests**, and the whole `git diff` between them is that one sentence. The
earlier digest is recorded here so the change is auditable rather than silent.

**Known provider mutability, stated in advance.** The Milestone BZ capture that
Milestones BZ and CA were measured over was never persisted, so CD must take a
new one. Binance's history is mutable at source and three years have passed; CC
already observed the provider delist `ICXUSDT` — one of CA's fifteen — between two
runs eight days apart. CD's capture is therefore a **new dataset taken under the
same sealed rules**, not CA's, and the report compares its reconstructed
admission counts against CA's published ones rather than assuming they agree. A
disagreement is a finding about the provider, not a defect in CD.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Final

from fmis.paired_dependence.estimator import CellReduction
from fmis.paired_dependence.models import (
    DependenceVerdict,
    GroupingAxis,
    PairedDependenceError,
    RequirementOutcome,
    Weighting,
    require_count,
    require_probability,
    require_text,
)
# Imported, never restated. A horizon, a family or a sample boundary retyped here
# could drift from the milestone that sealed it and the two would silently stop
# describing the same instants.
from fmis.swing_lab.admission_preregistration import (
    CA_NULL_FAMILIES,
    CA_PREREGISTRATION_DIGEST,
    CA_PREREGISTRATION_ID,
    MIN_ADMISSION_EDGE_ATR,
    PRIMARY_HORIZON,
)
from fmis.swing_lab.persistence_preregistration import (
    BZ_PREREGISTRATION_DIGEST,
    BZ_PREREGISTRATION_ID,
)
from fmis.swing_lab.preregistration import SAMPLES
from fmis.universe.identity import identity_rules_payload
from fmis.universe.preregistration import CC_PREREGISTRATION_DIGEST, CC_PREREGISTRATION_ID

__all__ = [
    "CD_PREREGISTRATION_ID",
    "CD_PREREGISTRATION_DIGEST",
    "CD_RESEARCH_QUESTION",
    "CD_ESTIMAND",
    "CD_UNIT_OF_EVIDENCE",
    "CD_UNIVERSE_SOURCE",
    "CD_PRIMARY_FAMILY",
    "CD_PRIMARY_SAMPLE",
    "CD_MEASURED_SAMPLES",
    "CD_UNMATCHED_RULE",
    "CD_REPEATED_OBSERVATION_RULE",
    "CD_OVERLAP_RULE",
    "CD_CROSS_ASSET_RULE",
    "PRIMARY_ESTIMATOR_ID",
    "PRIMARY_ESTIMATOR_RULE",
    "SECONDARY_ESTIMATORS",
    "PRIMARY_BLOCK_BARS",
    "BLOCK_BARS_GRID",
    "CELL_REDUCTIONS",
    "WEIGHTINGS",
    "PRIMARY_CELL_REDUCTION",
    "PRIMARY_WEIGHTING",
    "UNCERTAINTY_RULE",
    "BOOTSTRAP_DRAWS",
    "BOOTSTRAP_CONFIDENCE",
    "CD_MASTER_SEED",
    "MIN_GROUPS",
    "MIN_MEMBERS",
    "MIN_ECONOMIC_ASSETS",
    "MIN_INFORMATIVE_BLOCKS",
    "MIN_SHARED_BLOCKS_PER_PAIR",
    "WINSORISATION",
    "CALIBRATION_REPLICATES",
    "CALIBRATION_TOLERANCE_RULE",
    "CD_VERDICT_RULES",
    "CD_REQUIREMENT_RULES",
    "CD_INTERPRETATION_RULES",
    "CD_NON_PROMOTION_RULE",
    "CD_PROVIDER_MUTABILITY",
    "CD_ARTIFACT_REQUIREMENTS",
    "CD_LIMITATIONS",
    "CD_POST_REVIEW_LIMITATIONS",
    "CdPreregistration",
    "CD_PRE_REGISTRATION",
    "cd_preregistration_digest",
    "verify_cd_preregistration",
]

CD_PREREGISTRATION_ID: Final[str] = "cd-paired-effect-dependence-v1"

CD_RESEARCH_QUESTION: Final[str] = (
    "Across the economic assets Milestone CA actually measured, how dependent "
    "are the paired admission-versus-control forward-effect observations that "
    "CA's estimate is computed from — WITHIN one economic asset, and BETWEEN "
    "economic assets observed in the same period — and what does the measured "
    "dependence do to Milestone CB's information requirement for a +0.10 ATR "
    "admission effect? This is a question about research-design dependence. It "
    "is NOT a question about whether an admission edge exists, NOT a strategy "
    "study, and no answer to it approves trading of any kind."
)

CD_ESTIMAND: Final[str] = (
    "For every admitted instant i under one sealed Milestone CA null family, the "
    "paired difference at the primary horizon: D_i = admission_forward(H) - "
    "mean over that admission's own matched control draws of control_forward(H), "
    "in ATR units, direction-normalised, exactly as "
    "fmis.swing_lab.admission_study.PairedRecord.difference(H) computes it. CD "
    "COPIES this quantity and never recomputes it. Two dependence parameters are "
    "estimated from the population of D: (1) rho_w, the correlation between two "
    "D on the SAME economic asset; (2) r_b, the correlation between two D on "
    "DIFFERENT economic assets falling in the SAME time block. These are "
    "different quantities and are never reported under one name."
)

CD_UNIT_OF_EVIDENCE: Final[str] = (
    "One (admitted instant, null family) pair at the primary horizon is one ROW. "
    "One admitted instant is one ADMISSION and produces up to five rows, one per "
    "sealed family, measuring the same instant against different controls. One "
    "economic exposure is one ECONOMIC ASSET and holds many admissions. A "
    "headline estimate is computed WITHIN one family; rows are never pooled "
    "across families, because five rows sharing an admission are one observation "
    "measured five ways and pooling them would multiply the apparent sample by "
    "five without adding an instant."
)

CD_UNIVERSE_SOURCE: Final[str] = (
    "Milestone BY's three sealed sample specifications, imported by identity from "
    "fmis.swing_lab.preregistration.SAMPLES: development and validation over the "
    "same fifteen symbols across adjacent windows, and the holdout over "
    "twenty-one symbols no milestone before CA measured. CD adds no symbol, "
    "removes no symbol and re-orders nothing. It does NOT use Milestone CC's 38 "
    "eligible economic assets: no paired admission-versus-control observation has "
    "ever been computed for 23 of them, and constructing some now would require a "
    "1,750-day warm-up replay of a universe CC already proved cannot reach the "
    "requirement. CD measures the dependence of the observations that EXIST."
)

#: The family the headline reads. `ca_null_matched_timing` is Milestone CA's own
#: leading family — the one its development table opens with and the only one
#: whose interval excluded zero on any sample — and it asks the cleanest version
#: of the question: holding direction at FMITS's own, is an admitted instant
#: better than a matched instant the engine declined?
CD_PRIMARY_FAMILY: Final[str] = "ca_null_matched_timing"

CD_PRIMARY_SAMPLE: Final[str] = "development"

CD_MEASURED_SAMPLES: Final[tuple[str, ...]] = ("development", "validation", "holdout")

CD_UNMATCHED_RULE: Final[str] = (
    "An admission that drew no control produces NO row, because there is no "
    "paired difference to hold. The count of such admissions is reported per "
    "family and per sample rather than left implicit — Milestone CA reported 4 "
    "of 155 on development for the eligible-but-rejected family and 0 elsewhere "
    "— and their exclusion is a property of the matching pool, which is fixed "
    "before any outcome is measured."
)

CD_REPEATED_OBSERVATION_RULE: Final[str] = (
    "Repeated admissions on one economic asset are KEPT and are the entire "
    "source of rho_w. They are never treated as independent: the asset axis "
    "groups them, the asset-clustered bootstrap resamples whole assets, and "
    "the coverage report states observations-per-asset as its own dimension so a "
    "large row count on few assets cannot be read as a large N."
)

CD_OVERLAP_RULE: Final[str] = (
    "Two admissions on one economic asset whose signal bars sit fewer than 60 "
    "execution bars apart share forward evaluation bars and are mechanically "
    "dependent. CD does NOT drop them — dropping them would select on the "
    "timeline and would remove exactly the clustered admissions rho_w exists to "
    "measure — but counts them per family and per sample and reports the share. "
    "Sixty bars is Milestone BW's evaluation window, inherited unchanged, and is "
    "the same span Milestone CA used as its minimum control separation."
)

CD_CROSS_ASSET_RULE: Final[str] = (
    "Two admissions on DIFFERENT economic assets are treated as contemporaneous "
    "when their signal bars fall in the same time block. Blocks are cut from bar "
    "zero of the capture at a fixed length so a bar lands in the same block for "
    "every asset and every sample. Where an asset contributes several "
    "observations to one block they are reduced to ONE member first, so a busy "
    "asset cannot contribute its own within-asset correlation to a between-asset "
    "estimate. A pair of assets that never share a block yields NO pairwise "
    "correlation — not a zero — and the count of such pairs is reported."
)

PRIMARY_ESTIMATOR_ID: Final[str] = "cd-oneway-random-effects-icc-v1"

PRIMARY_ESTIMATOR_RULE: Final[str] = (
    "The unbalanced one-way random-effects intraclass correlation, by the ANOVA "
    "method of moments: for groups g holding n_g members y_gm, with "
    "SSB = sum n_g (mean_g - mean)^2 on G-1 degrees of freedom, "
    "SSW = sum (y_gm - mean_g)^2 on N-G, and "
    "k0 = (N - sum n_g^2 / N) / (G - 1), the estimate is "
    "rho = (MSB - MSW) / k0 / ((MSB - MSW) / k0 + MSW). It is applied to the SAME "
    "paired differences on TWO grouping axes: group = economic asset yields "
    "rho_w, group = time block yields r_b. No iteration, no optimisation, no "
    "starting value, nothing to tune. A negative estimate is REPORTED as measured "
    "and truncated to [0, 1] only where downstream arithmetic requires it, with "
    "both values carried. Milestone CC's cross-sectional-residual estimator is "
    "explicitly NOT the primary estimator and is retained only as a known "
    "uninformative negative control."
)

SECONDARY_ESTIMATORS: Final[tuple[str, ...]] = (
    "pairwise_asset_correlation — Pearson correlation per asset pair over the "
    "blocks both occupy, with the count of unmeasurable pairs reported. "
    "Secondary because with a few observations per asset most pairs share too "
    "few blocks for a correlation to carry meaning, and a mean over the "
    "survivors would describe the densest corner of the panel.",
    "cc_residual_correlation — Milestone CC's estimator, reported as a "
    "comparison so a reader can see it return the same value at every true "
    "correlation. It is never read as an estimate and no verdict consults it.",
    "effective_cluster_count — K / (1 + (K - 1) r_b), "
    "fmis.universe.dependence.effective_clusters called, evaluated at the point "
    "estimate and at both interval bounds.",
)

#: Sixty execution bars — ten days at 4H. Milestone BW's evaluation window, CA's
#: minimum control separation, and the span beyond which two admissions on one
#: symbol share no forward bar. Chosen because it is already the repository's
#: definition of "the same episode", not because it produced a number.
PRIMARY_BLOCK_BARS: Final[int] = 60

#: The whole sealed grid. Every one is reported; none is selected after the fact.
#: 24 is the primary horizon, 60 the evaluation window, 120 and 180 are twenty
#: and thirty days — the range over which a "swing episode" could plausibly be
#: defined for a strategy whose horizon bound is ten days.
BLOCK_BARS_GRID: Final[tuple[int, ...]] = (24, 60, 120, 180)

CELL_REDUCTIONS: Final[tuple[str, ...]] = tuple(item.value for item in CellReduction)
PRIMARY_CELL_REDUCTION: Final[str] = CellReduction.CELL_MEAN.value

WEIGHTINGS: Final[tuple[str, ...]] = tuple(item.value for item in Weighting)
PRIMARY_WEIGHTING: Final[str] = Weighting.EQUAL_CELL.value

UNCERTAINTY_RULE: Final[str] = (
    "A nonparametric bootstrap resampling the axis each estimand's independent "
    "replicates lie on, with nearest-rank percentile bounds and no "
    "interpolation. r_b resamples TIME BLOCKS with replacement; rho_w resamples "
    "ECONOMIC ASSETS with replacement, the same axis Milestone CA's own bootstrap "
    "resamples. A group drawn twice becomes two groups. Each estimand is ALSO run "
    "on the other axis as a declared sensitivity and a disagreement is reported "
    "rather than resolved. Fisher-z is REFUSED: its variance formula assumes "
    "independent bivariate normal pairs, which this panel violates on every "
    "count, and it would give the narrowest interval on offer. Draws on which the "
    "estimator is undefined are counted and excluded; if fewer than half the "
    "draws are usable the interval is REFUSED rather than read off the survivors."
)

BOOTSTRAP_DRAWS: Final[int] = 2000
BOOTSTRAP_CONFIDENCE: Final[float] = 0.95

#: Fixed before any result. Every draw's seed is SHA-256 over this and the draw's
#: own identity, so no result moves across processes or PYTHONHASHSEED values.
CD_MASTER_SEED: Final[int] = 20260903

#: Below any of these the panel cannot identify the parameter and the sample is
#: reported INCONCLUSIVE rather than estimated. They are minima at which the
#: estimator is defined and the bootstrap has more than 2^10 distinct resamples —
#: not thresholds chosen to be cleared.
MIN_GROUPS: Final[int] = 10
MIN_MEMBERS: Final[int] = 30
MIN_ECONOMIC_ASSETS: Final[int] = 3
MIN_INFORMATIVE_BLOCKS: Final[int] = 10
MIN_SHARED_BLOCKS_PER_PAIR: Final[int] = 4

WINSORISATION: Final[str] = (
    "NONE. No paired difference is trimmed, clipped or winsorised at any stage. "
    "Milestone CA's own falsification pass found its negative result was WORSE "
    "without outliers, so trimming here could only flatter the panel, and a "
    "trimming rule chosen after seeing a heavy tail is a threshold fitted to a "
    "result."
)

CALIBRATION_REPLICATES: Final[int] = 25

CALIBRATION_TOLERANCE_RULE: Final[str] = (
    "The mean estimate over CALIBRATION_REPLICATES independent realisations of a "
    "synthetic scenario must lie within 1/(K-1) of that scenario's stated "
    "expectation, where K is the scenario's asset count. The tolerance is "
    "DERIVED, not chosen: 1/(K-1) is exactly the magnitude of the "
    "cross-sectional exchangeability artefact at K assets, and an estimator "
    "cannot be asked to resolve a correlation finer than that on a K-asset "
    "panel. Two scenarios carry no point expectation — unequal cell sizes and a "
    "non-exchangeable block structure — and are asserted by ordering alone rather "
    "than against a fabricated target. The four between-asset scenarios must ALSO "
    "reproduce their ordering strictly."
)

CD_VERDICT_RULES: Final[tuple[str, ...]] = (
    "INVALID_ESTIMATOR if the synthetic calibration fails: any point expectation "
    "missed by more than its stated tolerance, or the between-asset ordering not "
    "reproduced. This verdict is checked FIRST and short-circuits the rest — an "
    "estimator that cannot recover a dependence it was given may not report one "
    "it found.",
    "INCONCLUSIVE if any sample floor is unmet on the primary family and primary "
    "sample, or the primary interval is refused, or the interval for r_b spans "
    "from at or below zero to at or above 1/K*, so the panel cannot distinguish "
    "'no dependence penalty at all' from 'unreachable at any universe size'.",
    "WEAKLY_IDENTIFIED if the interval yields a finite required-cluster range "
    "whose bounds span more than one order of magnitude, or one bound is "
    "unreachable while the other is finite.",
    "MEASURED if the interval yields a finite required-cluster range whose upper "
    "and lower bounds lie within one order of magnitude of each other.",
    "No verdict reads a p-value, a significance test or an effect size, and no "
    "verdict is permitted to depend on the SIGN of Milestone CA's admission "
    "effect. A dependence measurement that changed with the direction of the "
    "result it is measuring would be an outcome-conditioned design.",
)

CD_REQUIREMENT_RULES: Final[tuple[str, ...]] = (
    "K* is Milestone CB's required cluster count on the MORE_CLUSTERS_SAME_DENSITY "
    "growth path, obtained by CALLING fmis.research_design.resolution."
    "required_information. CD implements no second power calculator.",
    "With between-cluster correlation r, K real clusters supply K / (1 + (K-1) r) "
    "independent ones, so the requirement is met at K = K* (1 - r) / (1 - K* r) "
    "and ONLY while r < 1 / K*. At or above 1/K* the effective count saturates "
    "below the requirement and the outcome is UNREACHABLE at any universe size.",
    "RESOLVABLE if the required cluster count at the UPPER interval bound is at "
    "or below the provider ceiling Milestone CC measured.",
    "UNDERPOWERED if the requirement is finite at the upper bound but exceeds "
    "CC's ceiling.",
    "UNREACHABLE if the requirement is unreachable at the POINT estimate.",
    "INCONCLUSIVE if the interval straddles 1/K*, so the same data supports both "
    "a finite requirement and no finite requirement.",
)

CD_INTERPRETATION_RULES: Final[tuple[str, ...]] = (
    "rho_w and r_b are DIFFERENT parameters and are never substituted for each "
    "other. rho_w feeds Milestone CB's design effect 1 + (m-1) rho; r_b caps the "
    "effective cluster count at 1/r_b. A report that quoted one where the other "
    "belongs would be off by orders of magnitude in the direction that flatters "
    "the design.",
    "A negative r_b is reported as measured and is NOT evidence of independence: "
    "on a K-asset panel the cross-sectional artefact alone produces -1/(K-1), so "
    "a measurement near that value is consistent with a wide range of truths.",
    "An estimate driven by a small number of assets is not a universe-level "
    "measurement. Concentration is reported with every headline and a largest "
    "share above 0.40 — Milestone CA's own bound — is stated as a limitation on "
    "the face of the result.",
    "The row count is never presented as the sample size. Rows, admissions, "
    "economic assets, informative blocks and effective clusters are five separate "
    "numbers and the report prints all five.",
    "A re-captured dataset is not Milestone CA's dataset. Every CD figure "
    "describes the capture CD took, and the reconstructed admission counts are "
    "printed beside CA's published ones so a reader can see how far the provider "
    "moved.",
)

CD_NON_PROMOTION_RULE: Final[str] = (
    "No Milestone CD verdict promotes anything. DependenceVerdict and "
    "RequirementOutcome each report is_approved_for_trading False and "
    "earns_forward_test False for EVERY member, asserted over the whole enum by "
    "a hostile test. CD does not change a production constant, does not evaluate "
    "a strategy, does not tune a threshold, does not open a position and does not "
    "read a credential. Milestone CA's NO_EDGE, Milestone CB's UNDERPOWERED and "
    "Milestone CC's INFEASIBLE all stand; where CD refines CC's information "
    "requirement the refinement is recorded SEPARATELY and CC's historical "
    "verdict is preserved unaltered."
)

CD_PROVIDER_MUTABILITY: Final[str] = (
    "The Milestone BZ capture that BZ and CA were measured over was never "
    "persisted into this repository, so CD takes a new one under the same sealed "
    "BZ pre-registration. Binance's spot history is mutable at source: Milestone "
    "CC observed four instruments listed and ICXUSDT — one of CA's fifteen — "
    "delisted between two discovery runs eight days apart. CD's capture is "
    "therefore a NEW DATASET under the same rules, its own content digest is "
    "recorded, and any divergence between CD's reconstructed admission counts and "
    "CA's published ones is reported as a provider finding rather than "
    "reconciled away."
)

CD_ARTIFACT_REQUIREMENTS: Final[tuple[str, ...]] = (
    "The Milestone BZ capture CD replays is persisted in full, closing the "
    "provenance gap that made CD necessary. It is written once and never deleted "
    "to be regenerated.",
    "Every observation-level row is persisted with the provenance to audit it "
    "offline: admission identity, economic asset, symbol, base asset, direction, "
    "sample, bar index, timestamp, horizon, admission forward, control forward, "
    "paired difference, control draw count, matching pool size and radius tier, "
    "and the source capture's content digest.",
    "The artifact carries its schema version, its kind, this pre-registration's "
    "digest, the CA / BZ / CC digests it stands on, the estimator and uncertainty "
    "configuration, every sensitivity cell, every control reading and its own "
    "content digest taken over canonical JSON so no compression header or "
    "filename can reach it.",
    "The reader REFUSES a wrong kind, a wrong schema version, a digest mismatch, "
    "a seal mismatch, a missing provenance field and an incompatible source "
    "artifact identity — each by name, and none of them by recomputing the "
    "missing value.",
    "Offline reproduction is proven by re-deriving every CD measurement from the "
    "artifact with every market-data and network entry point monkeypatched to "
    "raise.",
)

CD_LIMITATIONS: Final[tuple[str, ...]] = (
    "CD-1 — THE PANEL IS FIFTEEN AND TWENTY-ONE ASSETS, NOT CC'S THIRTY-EIGHT. "
    "CD measures the dependence of the observations that exist. Nothing here "
    "says what the dependence would be on a universe nobody has measured.",
    "CD-2 — A TIME BLOCK IS A MODELLING CHOICE. Two admissions in one block are "
    "treated as contemporaneous and two either side of a boundary are not, "
    "however close they sit. The whole sealed block grid is reported for exactly "
    "this reason.",
    "CD-3 — THE CELL-MEAN REDUCTION IS HETEROSKEDASTIC. A cell built from five "
    "observations is less noisy than one built from one, which biases r_b "
    "DOWNWARD — the direction that flatters feasibility. CELL_FIRST is reported "
    "beside it as the homoskedastic alternative.",
    "CD-4 — THE ANOVA ICC IS A RATIO OF UNBIASED ESTIMATES, NOT AN UNBIASED "
    "ESTIMATE. Its small-sample bias is quantified by the synthetic calibration "
    "rather than assumed away.",
    "CD-5 — THE ONE-WAY MODEL POSITS EXCHANGEABILITY WITHIN A GROUP. A panel "
    "whose dependence changes over the timeline has no single correct r_b, and "
    "the non-exchangeable calibration scenario exists to show what the estimator "
    "does when that assumption fails.",
    "CD-6 — EVERY MILESTONE CA LIMITATION IS INHERITED. The outcome is not a "
    "trade, the horizon bound is Milestone BW's, matching cannot remove an "
    "unobserved confound, the samples are Milestone BY's and the universe is "
    "survivorship-filtered.",
    "CD-7 — CD RE-CAPTURED THE DATA. The paired differences CD measures are not "
    "bit-identical to the ones CA measured, because CA's capture no longer "
    "exists. See CD_PROVIDER_MUTABILITY.",
)


#: What three independent reviewers established about this milestone **after** the
#: pre-registration was sealed and after the real estimate was computed.
#:
#: These are deliberately **not** added to `CD_LIMITATIONS`, which is part of the
#: sealed payload: retro-fitting a seal with what was learned later would destroy
#: the only property a seal has. They are carried separately, reported
#: separately, and dated to the review rather than to the pre-registration.
#: Milestone CC carried its own post-review findings the same way.
CD_POST_REVIEW_LIMITATIONS: Final[tuple[str, ...]] = (
    "CD-8 — r_b IS NOT THE CORRELATION THE EFFECTIVE-CLUSTER FORMULA CONSUMES, "
    "AND THE SEALED SECONDARY ESTIMATOR SAYS IT IS. r_b is the correlation "
    "between two INDIVIDUAL contemporaneous observations on different assets; "
    "K / (1 + (K-1) r) expects the mean pairwise correlation of CLUSTER-LEVEL "
    "series. Those coincide only if every admission of one asset is "
    "contemporaneous with every admission of another, and admissions are "
    "scattered over the window. The design-relevant quantity is q * r_b, where q "
    "is the fraction of cross-asset observation pairs that actually share a "
    "block. Measured on a Milestone CA-shaped panel with a known r_b of 0.20, "
    "the true design effect is 1.43; 1 + (K-1) r_b gives 3.74 and "
    "1 + (K-1) q r_b gives 1.39. Every effective-cluster figure computed under "
    "the sealed formula is therefore OVERSTATED by roughly 3x. The sealed path is "
    "left exactly as sealed and `contemporaneity_fraction` and "
    "`overlap_corrected_correlation` are reported beside it. The qualitative "
    "conclusion is unchanged: every corrected value still exceeds 1/K*.",
    "CD-9 — THE SEALED STRADDLE RULE TESTS THE WRONG BOUND. It fires when the "
    "interval runs 'from at or below zero to at or above 1/K*'. The condition "
    "that actually means 'the data supports both a finite and an infinite "
    "requirement' is lower < 1/K* <= upper; zero has no role in it. An interval "
    "such as [+0.0005, +0.30] is therefore reported UNREACHABLE when the honest "
    "answer is INCONCLUSIVE — the anti-conservative direction for a milestone "
    "whose headline is negative. It did not fire on any measured panel. It is "
    "inside the digest and is DISCLOSED rather than corrected, because changing a "
    "verdict rule after seeing results is what a pre-registration exists to "
    "prevent.",
    "CD-10 — THE SEALED MECHANISM CLAIM IN THE FIRST DRAFT OF REPORT 0040 WAS "
    "WRONG, AND THE TRUTH IS WORSE. That draft attributed r_b > 0 to controls "
    "sitting 90-360 days from their admission. The matching radius is a CEILING, "
    "not a floor, so controls sit 10-90 days away for 1,387 of 1,430 matched "
    "rows; and two of the five families draw a SAME-BAR control, so no calendar "
    "distance applies to 960 of 2,390 rows at all. The real mechanism is that "
    "control_forward is a mean over 200 draws whose standard deviation is 0.17 "
    "of the admission leg's, so corr(D, admission_forward) = +0.987 and the "
    "paired difference is arithmetically close to the raw admission outcome. For "
    "ca_null_opposite_direction it is exactly 2 x the admission return, so that "
    "family's r_b IS the raw-outcome r_b by construction.",
    "CD-11 — THE PANEL IS SURVIVOR-ONLY, AND THAT BIASES r_b UPWARD. Every one "
    "of the 36 symbols resolves to a single bar-zero timestamp per universe, so "
    "no instrument that listed or delisted mid-window is present. Listings and "
    "delistings are exactly the events that decorrelate a crypto panel. Sealed "
    "limitation CD-6 inherits Milestone BY's survivorship filtering; this states "
    "its direction, which is toward CD's own finding.",
    "CD-12 — THE PRIMARY FAMILY'S JUSTIFICATION CITES A REALISED HOLDOUT "
    "RESULT. The sealed comment on CD_PRIMARY_FAMILY calls ca_null_matched_timing "
    "'the only one whose interval excluded zero on any sample', and per report "
    "0037 that sample is the HOLDOUT. The choice is therefore outcome-informed. "
    "Material impact is nil — every family's development interval straddles zero, "
    "so any choice yields the same verdict — but the claim that no CD decision "
    "read a sample is true only because 'primary family' was not on the list.",
    "CD-13 — THE CALIBRATION GATE IS 33x COARSER THAN THE DECISION BOUNDARY. The "
    "tolerance 1/(K-1) is 0.0714 at K = 15; the threshold every design conclusion "
    "turns on is 1/K* = 0.002141. With 25 replicates the calibration mean itself "
    "carries a Monte-Carlo standard error near 0.020. The gate can certify that "
    "the estimator recovers an ordering; it cannot certify precision anywhere "
    "near the boundary. Its derivation is also a non sequitur: 1/(K-1) is the "
    "magnitude of the artefact CC's BROKEN estimator produces, which bounds "
    "nothing about this one.",
    "CD-14 — THE 'DECISIVE' CALIBRATION ROW IS AN ALGEBRAIC IDENTITY. After "
    "cross-sectional demeaning every block sums to zero, so SSB is identically "
    "zero (measured at 1.3e-31) and rho is -1/(k0-1) whatever the variance-"
    "component logic does. market_factor_removed is a correct prediction and a "
    "VACUOUS test: it would return -1/(K-1) even if the estimator were broken.",
    "CD-15 — THE WEIGHTED ICC WAS WRONG AND IS NOW FIXED. The observation-count "
    "path divided a weighted sum of squares by unweighted degrees of freedom and "
    "omitted the s2_e coefficient in E[MSB], so multiplying every weight by a "
    "constant moved the estimate (rho 0.860 at weight 1, 0.381 at weight 10). "
    "The only weighted test used weights of exactly 1.0 — the one case that "
    "cannot see it. Fixed to the exact weighted ANOVA, which is now scale-"
    "invariant and reduces to the unweighted form exactly. Only the eight "
    "observation-weighted sensitivity cells were affected; the headline uses "
    "equal-cell weighting and is unchanged.",
    "CD-16 — THE HEADLINE IS LESS STABLE THAN THE CONCENTRATION AUDIT SUGGESTS. "
    "Dropping one economic asset moves r_b from +0.1414 to +0.3122, a 2.2x "
    "spread; dropping one block moves it +0.1434 to +0.2635. The sealed "
    "concentration statistic measures share of absolute magnitude, which is "
    "close to uninformative about the stability of a VARIANCE RATIO. "
    "`leave_one_out` is reported alongside it from now on.",
    "CD-17 — THE BLOCK BOOTSTRAP IS ANTI-CONSERVATIVE UNDER PLAUSIBLE "
    "STRUCTURE. Simulated coverage at nominal 95 % is 0.95 with iid blocks and "
    "homogeneous loadings, but 0.83 with heterogeneous factor loadings and 0.88 "
    "with AR(1) block factors — both plausible for crypto. For rho_w at a true "
    "value of zero the asset bootstrap falsely excludes zero in about 15 % of "
    "runs, so the reported exclusion of zero is a ~15 % event and not a 5 % one.",
    "CD-18 — 'FIFTEEN OF FIFTEEN PANELS' IS NOT FIFTEEN INDEPENDENT "
    "MEASUREMENTS. The five families share the same admitted instants and, per "
    "CD-10, nearly the same estimand; development and validation share the same "
    "fifteen symbols; and the holdout window (2024-06 to 2026-08) fully CONTAINS "
    "validation's. There are roughly two quasi-independent measurements over "
    "overlapping calendar periods.",
    "CD-19 — THE VALIDATION ANOMALY IS NOT A SMALL-SAMPLE EFFECT, AND CD HAD "
    "THE TEST. Twenty-nine contiguous development sub-windows matched to "
    "validation's n give r_b median +0.138 and maximum +0.308; NONE reaches "
    "validation's +0.478. The first draft said the two explanations could not be "
    "separated. They can, and the small-sample one is refuted.",
)


@dataclass(frozen=True, slots=True)
class CdPreregistration:
    """Everything CD froze, in one digestible object."""

    preregistration_id: str
    research_question: str
    estimand: str
    unit_of_evidence: str
    universe_source: str
    primary_family: str
    primary_sample: str
    measured_samples: tuple[str, ...]
    primary_horizon: int
    unmatched_rule: str
    repeated_observation_rule: str
    overlap_rule: str
    cross_asset_rule: str
    primary_estimator_id: str
    primary_estimator_rule: str
    secondary_estimators: tuple[str, ...]
    grouping_axes: tuple[str, ...]
    primary_block_bars: int
    block_bars_grid: tuple[int, ...]
    cell_reductions: tuple[str, ...]
    primary_cell_reduction: str
    weightings: tuple[str, ...]
    primary_weighting: str
    uncertainty_rule: str
    bootstrap_draws: int
    bootstrap_confidence: float
    master_seed: int
    min_groups: int
    min_members: int
    min_economic_assets: int
    min_informative_blocks: int
    min_shared_blocks_per_pair: int
    winsorisation: str
    calibration_replicates: int
    calibration_tolerance_rule: str
    verdict_rules: tuple[str, ...]
    requirement_rules: tuple[str, ...]
    interpretation_rules: tuple[str, ...]
    non_promotion_rule: str
    provider_mutability: str
    artifact_requirements: tuple[str, ...]
    limitations: tuple[str, ...]
    meaningful_effect_atr: float
    ca_preregistration_id: str
    ca_preregistration_digest: str
    bz_preregistration_id: str
    bz_preregistration_digest: str
    cc_preregistration_id: str
    cc_preregistration_digest: str
    identity_rules: dict[str, Any]

    def __post_init__(self) -> None:
        for field in (
            "preregistration_id", "research_question", "estimand",
            "unit_of_evidence", "universe_source", "primary_family",
            "primary_sample", "unmatched_rule", "repeated_observation_rule",
            "overlap_rule", "cross_asset_rule", "primary_estimator_id",
            "primary_estimator_rule", "primary_cell_reduction",
            "primary_weighting", "uncertainty_rule", "winsorisation",
            "calibration_tolerance_rule", "non_promotion_rule",
            "provider_mutability", "ca_preregistration_id",
            "ca_preregistration_digest", "bz_preregistration_id",
            "bz_preregistration_digest", "cc_preregistration_id",
            "cc_preregistration_digest",
        ):
            require_text(getattr(self, field), field)
        for field in (
            "measured_samples", "secondary_estimators", "grouping_axes",
            "block_bars_grid", "cell_reductions", "weightings", "verdict_rules",
            "requirement_rules", "interpretation_rules", "artifact_requirements",
            "limitations",
        ):
            value = getattr(self, field)
            if not isinstance(value, tuple) or not value:
                raise PairedDependenceError(f"{field} must be a non-empty tuple")
        require_count(self.primary_horizon, "primary_horizon", minimum=1)
        require_count(self.primary_block_bars, "primary_block_bars", minimum=1)
        require_count(self.bootstrap_draws, "bootstrap_draws", minimum=100)
        require_count(self.min_groups, "min_groups", minimum=2)
        require_count(self.min_members, "min_members", minimum=3)
        require_count(self.min_economic_assets, "min_economic_assets", minimum=2)
        require_count(self.min_informative_blocks, "min_informative_blocks", minimum=1)
        require_count(
            self.min_shared_blocks_per_pair, "min_shared_blocks_per_pair", minimum=2
        )
        require_count(self.calibration_replicates, "calibration_replicates", minimum=2)
        require_probability(self.bootstrap_confidence, "bootstrap_confidence")
        if self.primary_block_bars not in self.block_bars_grid:
            raise PairedDependenceError(
                f"the primary block length {self.primary_block_bars} is not in the "
                "declared grid; a length the grid does not report cannot be the "
                "one the grid is read against"
            )
        if self.primary_cell_reduction not in self.cell_reductions:
            raise PairedDependenceError(
                "the primary cell reduction is not one of the declared reductions"
            )
        if self.primary_weighting not in self.weightings:
            raise PairedDependenceError(
                "the primary weighting is not one of the declared weightings"
            )
        if self.primary_sample not in self.measured_samples:
            raise PairedDependenceError(
                "the primary sample is not one of the measured samples"
            )
        if self.primary_family not in {item.family_id for item in CA_NULL_FAMILIES}:
            raise PairedDependenceError(
                f"the primary family {self.primary_family!r} is not one Milestone "
                "CA sealed; CD measures CA's families and invents none"
            )
        if self.primary_horizon != PRIMARY_HORIZON:
            raise PairedDependenceError(
                f"the primary horizon {self.primary_horizon} is not Milestone "
                f"CA's sealed {PRIMARY_HORIZON}; measuring the dependence of a "
                "different horizon's differences would not describe CA's estimate"
            )

    def payload(self) -> dict[str, Any]:
        """The canonical content the seal is taken over. **Every material field.**

        Result fields are absent by construction: there is no attribute on this
        dataclass that could hold a measured correlation, an interval, a verdict
        or a count, so a post-hoc value cannot enter the digest even by mistake.
        A mutation test asserts the payload keys are exactly these.
        """
        return {
            "preregistration_id": self.preregistration_id,
            "research_question": self.research_question,
            "estimand": self.estimand,
            "unit_of_evidence": self.unit_of_evidence,
            "universe_source": self.universe_source,
            "primary_family": self.primary_family,
            "primary_sample": self.primary_sample,
            "measured_samples": list(self.measured_samples),
            "primary_horizon": self.primary_horizon,
            "unmatched_rule": self.unmatched_rule,
            "repeated_observation_rule": self.repeated_observation_rule,
            "overlap_rule": self.overlap_rule,
            "cross_asset_rule": self.cross_asset_rule,
            "primary_estimator_id": self.primary_estimator_id,
            "primary_estimator_rule": self.primary_estimator_rule,
            "secondary_estimators": list(self.secondary_estimators),
            "grouping_axes": list(self.grouping_axes),
            "primary_block_bars": self.primary_block_bars,
            "block_bars_grid": list(self.block_bars_grid),
            "cell_reductions": list(self.cell_reductions),
            "primary_cell_reduction": self.primary_cell_reduction,
            "weightings": list(self.weightings),
            "primary_weighting": self.primary_weighting,
            "uncertainty_rule": self.uncertainty_rule,
            "bootstrap_draws": self.bootstrap_draws,
            "bootstrap_confidence": self.bootstrap_confidence,
            "master_seed": self.master_seed,
            "min_groups": self.min_groups,
            "min_members": self.min_members,
            "min_economic_assets": self.min_economic_assets,
            "min_informative_blocks": self.min_informative_blocks,
            "min_shared_blocks_per_pair": self.min_shared_blocks_per_pair,
            "winsorisation": self.winsorisation,
            "calibration_replicates": self.calibration_replicates,
            "calibration_tolerance_rule": self.calibration_tolerance_rule,
            "verdict_rules": list(self.verdict_rules),
            "requirement_rules": list(self.requirement_rules),
            "interpretation_rules": list(self.interpretation_rules),
            "non_promotion_rule": self.non_promotion_rule,
            "provider_mutability": self.provider_mutability,
            "artifact_requirements": list(self.artifact_requirements),
            "limitations": list(self.limitations),
            "meaningful_effect_atr": self.meaningful_effect_atr,
            "ca_preregistration_id": self.ca_preregistration_id,
            "ca_preregistration_digest": self.ca_preregistration_digest,
            "bz_preregistration_id": self.bz_preregistration_id,
            "bz_preregistration_digest": self.bz_preregistration_digest,
            "cc_preregistration_id": self.cc_preregistration_id,
            "cc_preregistration_digest": self.cc_preregistration_digest,
            "identity_rules": self.identity_rules,
            "sample_boundaries": [
                {
                    "name": item.name,
                    "role": item.role.value,
                    "symbols": list(item.symbols),
                    "signal_start": item.signal_start.isoformat(),
                    "signal_end": item.signal_end.isoformat(),
                }
                for item in SAMPLES
            ],
            "dependence_verdict_vocabulary": [
                item.value for item in DependenceVerdict
            ],
            "requirement_outcome_vocabulary": [
                item.value for item in RequirementOutcome
            ],
        }


CD_PRE_REGISTRATION: Final[CdPreregistration] = CdPreregistration(
    preregistration_id=CD_PREREGISTRATION_ID,
    research_question=CD_RESEARCH_QUESTION,
    estimand=CD_ESTIMAND,
    unit_of_evidence=CD_UNIT_OF_EVIDENCE,
    universe_source=CD_UNIVERSE_SOURCE,
    primary_family=CD_PRIMARY_FAMILY,
    primary_sample=CD_PRIMARY_SAMPLE,
    measured_samples=CD_MEASURED_SAMPLES,
    primary_horizon=PRIMARY_HORIZON,
    unmatched_rule=CD_UNMATCHED_RULE,
    repeated_observation_rule=CD_REPEATED_OBSERVATION_RULE,
    overlap_rule=CD_OVERLAP_RULE,
    cross_asset_rule=CD_CROSS_ASSET_RULE,
    primary_estimator_id=PRIMARY_ESTIMATOR_ID,
    primary_estimator_rule=PRIMARY_ESTIMATOR_RULE,
    secondary_estimators=SECONDARY_ESTIMATORS,
    grouping_axes=tuple(item.value for item in GroupingAxis),
    primary_block_bars=PRIMARY_BLOCK_BARS,
    block_bars_grid=BLOCK_BARS_GRID,
    cell_reductions=CELL_REDUCTIONS,
    primary_cell_reduction=PRIMARY_CELL_REDUCTION,
    weightings=WEIGHTINGS,
    primary_weighting=PRIMARY_WEIGHTING,
    uncertainty_rule=UNCERTAINTY_RULE,
    bootstrap_draws=BOOTSTRAP_DRAWS,
    bootstrap_confidence=BOOTSTRAP_CONFIDENCE,
    master_seed=CD_MASTER_SEED,
    min_groups=MIN_GROUPS,
    min_members=MIN_MEMBERS,
    min_economic_assets=MIN_ECONOMIC_ASSETS,
    min_informative_blocks=MIN_INFORMATIVE_BLOCKS,
    min_shared_blocks_per_pair=MIN_SHARED_BLOCKS_PER_PAIR,
    winsorisation=WINSORISATION,
    calibration_replicates=CALIBRATION_REPLICATES,
    calibration_tolerance_rule=CALIBRATION_TOLERANCE_RULE,
    verdict_rules=CD_VERDICT_RULES,
    requirement_rules=CD_REQUIREMENT_RULES,
    interpretation_rules=CD_INTERPRETATION_RULES,
    non_promotion_rule=CD_NON_PROMOTION_RULE,
    provider_mutability=CD_PROVIDER_MUTABILITY,
    artifact_requirements=CD_ARTIFACT_REQUIREMENTS,
    limitations=CD_LIMITATIONS,
    meaningful_effect_atr=MIN_ADMISSION_EDGE_ATR,
    ca_preregistration_id=CA_PREREGISTRATION_ID,
    ca_preregistration_digest=CA_PREREGISTRATION_DIGEST,
    bz_preregistration_id=BZ_PREREGISTRATION_ID,
    bz_preregistration_digest=BZ_PREREGISTRATION_DIGEST,
    cc_preregistration_id=CC_PREREGISTRATION_ID,
    cc_preregistration_digest=CC_PREREGISTRATION_DIGEST,
    identity_rules=identity_rules_payload(),
)


def cd_preregistration_digest(
    preregistration: CdPreregistration = CD_PRE_REGISTRATION,
) -> str:
    """SHA-256 over the canonical content. **The seal.**

    ``sort_keys`` is on so an editor reordering a dict literal does not move the
    digest, while every *sequence* keeps declaration order because the order of
    the block grid and the verdict rules is part of what was frozen. Milestone
    BY's function, reproduced for BY's reasons.
    """
    if not isinstance(preregistration, CdPreregistration):
        raise TypeError("preregistration must be a CdPreregistration")
    canonical = json.dumps(
        preregistration.payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


#: **The seal, pinned.** Recomputed and compared by
#: `tests/test_paired_dependence_preregistration.py`. A diff that changes this
#: line changed the pre-registration with it, and every figure measured under the
#: old digest describes a different study.
CD_PREREGISTRATION_DIGEST: Final[str] = (
    "28f8ebed0aa66dd77d16b08b8a8eecda86c922e5ded9db6da24881674c37c25d"
)


def verify_cd_preregistration(digest: str) -> bool:
    """Whether a recorded digest is the one this module currently seals."""
    if not isinstance(digest, str):
        raise TypeError("digest must be a str")
    return digest == cd_preregistration_digest()
