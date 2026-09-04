"""**Milestone CD — how dependent are Milestone CA's paired effects, really?**

Milestone CB found Milestone CA's admission experiment `UNDERPOWERED` and put a
number on what would fix it: roughly **467 clusters and 4,823 admissions**. That
number is stated in *independent* clusters, and CB could not say how far from
independent CA's clusters actually are, because CA's observation-level data was
never persisted (limitation CB-2). Milestone CC tried to close the gap from
outside — correlating price returns and then their cross-sectional residuals —
and an independent review showed the residual estimator was **structurally
incapable** of answering: cross-sectional demeaning removes an exchangeable
common component exactly, pinning the residual correlation at ``-1/(K-1)``
whatever the truth is (CC-7).

CD measures the dependence from **the actual paired effect observations**.

**The estimand, once.** For each admitted instant under one sealed CA null
family, the paired difference at CA's sealed primary horizon:

    D = admission_forward(24) - mean(control_forward(24) over its own draws)

`fmis.swing_lab.admission_study.PairedRecord.difference` called, never
recomputed. CD reaches those records by attaching an **additive observer** to
CA's own study loop, so the observations CD measures are the observations CA's
effect is computed from, not a reconstruction of them.

**Two parameters, never one.** The same one-way random-effects ICC is applied on
two grouping axes and the two results are different quantities:

    group = economic asset  →  rho_w   feeds CB's design effect 1 + (m-1) rho
    group = time block      →  r_b     caps effective clusters at 1 / r_b

Reporting one where the other belongs would be wrong by orders of magnitude in
the direction that flatters the design, and the sealed interpretation rules
forbid it.

**The number that decides everything is tiny.** With ``K* ≈ 467`` the saturation
threshold is ``1 / K* ≈ 0.00214``: above that between-asset correlation, no
universe of any size supplies enough independent clusters. Whether a
fifteen-asset panel can resolve a correlation to that precision is the real
question, and `DependenceVerdict.INCONCLUSIVE` is a valid and expected answer
rather than a failure.

**Nothing here approves anything.** `DependenceVerdict` and `RequirementOutcome`
each report `is_approved_for_trading` `False` and `earns_forward_test` `False`
for every member, asserted over both enums by a hostile test. CA's `NO_EDGE`,
CB's `UNDERPOWERED` and CC's `INFEASIBLE` all stand; where CD refines CC's
information requirement the refinement is recorded separately and CC's historical
verdict is preserved unaltered.

**Standard library only, and one network module.** `fmis.paired_dependence.capture`
is the sole module permitted to reach a provider — it rebuilds the Milestone BZ
capture that was never kept — and an architecture guard asserts that every other
module here is arithmetic.
"""

from __future__ import annotations

from fmis.paired_dependence.artifact import (
    CD_ARTIFACT_KIND,
    CD_ARTIFACT_SCHEMA_VERSION,
    PairedDependenceArtifact,
    encode_dependence_study,
    read_dependence_study,
    dependence_rows_of,
    dependence_study_digest,
    verify_dependence_study_digest,
    write_dependence_study,
)
from fmis.paired_dependence.capture import (
    CA_UNIVERSE_FOR_SAMPLE,
    capture_ca_sources,
    capture_windows,
)
from fmis.paired_dependence.controls import (
    ControlReading,
    cc_residual_correlation,
    duplicate_rows,
    outcome_permutation_stable,
    panel_shape,
    run_negative_controls,
    shuffle_asset_identity,
    shuffle_time_blocks,
    split_exposure,
)
from fmis.paired_dependence.estimator import (
    CellReduction,
    VarianceComponents,
    block_index,
    effective_clusters_from,
    group_by_asset,
    group_by_block,
    intraclass_icc,
    pairwise_asset_correlations,
    required_clusters_under_dependence,
)
from fmis.paired_dependence.integration import (
    RequirementAssessment,
    RequirementPoint,
    assess_requirement,
    cb_required_clusters,
    cc_reevaluation,
    requirement_at,
)
from fmis.paired_dependence.models import (
    DependenceVerdict,
    GroupingAxis,
    PairedDependenceError,
    RequirementOutcome,
    Weighting,
)
from fmis.paired_dependence.observations import (
    BASE_ASSET_RULE,
    CD_QUOTE_ASSETS,
    ObservationRow,
    base_asset_of,
    dependence_concentration_of,
    dependence_coverage_of,
    observations_from_capture,
    dependence_overlap_of,
    rows_from_records,
)
from fmis.paired_dependence.preregistration import (
    CD_PRE_REGISTRATION,
    CD_PREREGISTRATION_DIGEST,
    CD_PREREGISTRATION_ID,
    CdPreregistration,
    cd_preregistration_digest,
    verify_cd_preregistration,
)
from fmis.paired_dependence.render import render_dependence_study
from fmis.paired_dependence.study import (
    CD_SCHEMA_VERSION,
    PairedDependenceStudy,
    PanelResult,
    SensitivityCell,
    study_from_capture,
    study_from_rows,
)
from fmis.paired_dependence.synthetic import (
    CALIBRATION_SCENARIOS,
    SyntheticRow,
    SyntheticScenario,
    generate_panel,
    scenario_by_id,
)
from fmis.paired_dependence.uncertainty import (
    DependenceInterval,
    bootstrap_interval,
    estimate_on_axis,
)
from fmis.paired_dependence.verdict import (
    CalibrationOutcome,
    CalibrationReading,
    CdAssessment,
    FloorReading,
    assess_cd,
    calibrate,
    check_floors,
)

__all__ = [
    "BASE_ASSET_RULE",
    "CALIBRATION_SCENARIOS",
    "CA_UNIVERSE_FOR_SAMPLE",
    "CD_ARTIFACT_KIND",
    "CD_ARTIFACT_SCHEMA_VERSION",
    "CD_PRE_REGISTRATION",
    "CD_PREREGISTRATION_DIGEST",
    "CD_PREREGISTRATION_ID",
    "CD_QUOTE_ASSETS",
    "CD_SCHEMA_VERSION",
    "CalibrationOutcome",
    "CalibrationReading",
    "CdAssessment",
    "CdPreregistration",
    "CellReduction",
    "ControlReading",
    "DependenceInterval",
    "DependenceVerdict",
    "FloorReading",
    "GroupingAxis",
    "ObservationRow",
    "PairedDependenceArtifact",
    "PairedDependenceError",
    "PairedDependenceStudy",
    "PanelResult",
    "RequirementAssessment",
    "RequirementOutcome",
    "RequirementPoint",
    "SensitivityCell",
    "SyntheticRow",
    "SyntheticScenario",
    "VarianceComponents",
    "Weighting",
    "assess_cd",
    "assess_requirement",
    "base_asset_of",
    "block_index",
    "bootstrap_interval",
    "calibrate",
    "capture_ca_sources",
    "capture_windows",
    "cb_required_clusters",
    "cc_reevaluation",
    "cc_residual_correlation",
    "cd_preregistration_digest",
    "check_floors",
    "dependence_concentration_of",
    "dependence_coverage_of",
    "duplicate_rows",
    "effective_clusters_from",
    "encode_dependence_study",
    "estimate_on_axis",
    "generate_panel",
    "group_by_asset",
    "group_by_block",
    "intraclass_icc",
    "observations_from_capture",
    "outcome_permutation_stable",
    "dependence_overlap_of",
    "pairwise_asset_correlations",
    "panel_shape",
    "read_dependence_study",
    "render_dependence_study",
    "required_clusters_under_dependence",
    "requirement_at",
    "rows_from_records",
    "dependence_rows_of",
    "run_negative_controls",
    "scenario_by_id",
    "shuffle_asset_identity",
    "shuffle_time_blocks",
    "split_exposure",
    "dependence_study_digest",
    "study_from_capture",
    "study_from_rows",
    "verify_cd_preregistration",
    "verify_dependence_study_digest",
    "write_dependence_study",
]
