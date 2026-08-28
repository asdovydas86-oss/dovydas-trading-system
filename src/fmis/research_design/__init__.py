"""Can this experiment resolve the effect it claims to test? **Asked before it runs.**

Milestones BW → CA each built a technically correct experiment, ran it, and only
afterwards discovered whether the available sample could have resolved the effect
the experiment was designed to detect. CA is the case that forced this package
into existence: 155 matched admissions, a symbol-clustered bootstrap half-width
of ≈ 0.558 ATR, and a pre-declared bar of +0.10 ATR. **No realisation of that data
could have cleared the bar**, so its `NO_EDGE` verdict is a statement about
resolution at least as much as about the market.

This package answers one question and refuses every other:

> **Can the proposed design credibly answer its own question?**

It never answers *"is the strategy any good"*. `DesignVerdict` has no member that
approves, promotes or endorses a hypothesis, and a test asserts that over the
whole enum.

**Three separations do the real work here.**

*Prospective from post-hoc.* `AssessmentMode` is not a label a caller chooses. A
`PostHocResolution` is produced only by a function handed an uncertainty width
that a realised measurement produced; a `ProspectiveDesign` only by one handed an
*assumed* dispersion. Neither carries a settable mode, so a post-hoc calculation
cannot be dressed as prospective power — the specific misrepresentation that
makes a failed study look like it was planned to fail.

*Rows from information.* Ten thousand overlapping 4-hour bars are not ten
thousand experiments, and three hundred setups on one symbol are not three
hundred independent markets. `InformationProfile` reports observations, clusters,
observations per cluster, time blocks, experimental units and concentration as
**separate dimensions**, and offers a single effective-N only when an intracluster
correlation has been declared — with its derivation attached.

*Framework from research question.* This package owns no economically meaningful
effect, no trading threshold, no unit and no universe. `MeaningfulEffect` must be
supplied with a magnitude, a unit, a direction and a rationale; the framework
validates it, computes what the design can resolve against it, and says what
would have to change. `fmis.swing_lab.admission_power` is one adapter, for one
milestone, in one unit — and the core knows nothing about ATR, R, crypto or swing.

**Standard library only.** No numpy, no scipy, no pandas. `statistics.NormalDist`
supplies the normal quantile; everything else is arithmetic and a seeded
`random.Random`. Every resampling draw is seeded by SHA-256 over the draw's own
identity, so results are stable across processes and across `PYTHONHASHSEED`.

**It opens no file and reaches no network.** The artifact layer encodes, digests
and verifies a payload; writing it somewhere is a caller's decision, and an
architecture guard asserts no module here imports `pathlib`, `open`, `gzip` or a
transport.
"""

from __future__ import annotations

from fmis.research_design.artifact import (
    RESEARCH_DESIGN_ARTIFACT_KIND,
    RESEARCH_DESIGN_SCHEMA_VERSION,
    citation_for,
    design_assessment_digest,
    encode_design_assessment,
    verify_design_assessment_digest,
)
from fmis.research_design.dependence import (
    InformationProfile,
    design_effect,
    effective_observations,
    profile_of,
)
from fmis.research_design.models import (
    AssessmentMode,
    ComparisonType,
    DependenceModel,
    DesignTarget,
    DesignVerdict,
    EffectDirection,
    EstimatorKind,
    EstimatorSpec,
    GrowthPath,
    LimitingFactor,
    MeaningfulEffect,
    MetricUnit,
    ResearchDesignError,
    ResearchQuestion,
    ResolutionCriterion,
    SampleFrame,
    SampleRole,
)
from fmis.research_design.render import render_design_assessment
from fmis.research_design.resolution import (
    BootstrapReading,
    ClusteredObservation,
    DesignPoint,
    PostHocResolution,
    ProspectiveDesign,
    RequiredInformation,
    analytic_design_curve,
    cluster_bootstrap,
    empirical_design_curve,
    half_width_for_design,
    observation_dispersion_from_half_width,
    post_hoc_resolution,
    prospective_design,
    required_information,
)
from fmis.research_design.verdict import DesignAssessment, assess_research_design

__all__ = [
    "RESEARCH_DESIGN_ARTIFACT_KIND",
    "RESEARCH_DESIGN_SCHEMA_VERSION",
    "AssessmentMode",
    "BootstrapReading",
    "ClusteredObservation",
    "ComparisonType",
    "DependenceModel",
    "DesignAssessment",
    "DesignPoint",
    "DesignTarget",
    "DesignVerdict",
    "EffectDirection",
    "EstimatorKind",
    "EstimatorSpec",
    "GrowthPath",
    "InformationProfile",
    "LimitingFactor",
    "MeaningfulEffect",
    "MetricUnit",
    "PostHocResolution",
    "ProspectiveDesign",
    "RequiredInformation",
    "ResearchDesignError",
    "ResearchQuestion",
    "ResolutionCriterion",
    "SampleFrame",
    "SampleRole",
    "analytic_design_curve",
    "assess_research_design",
    "citation_for",
    "cluster_bootstrap",
    "design_assessment_digest",
    "design_effect",
    "effective_observations",
    "empirical_design_curve",
    "encode_design_assessment",
    "half_width_for_design",
    "observation_dispersion_from_half_width",
    "post_hoc_resolution",
    "profile_of",
    "prospective_design",
    "render_design_assessment",
    "required_information",
    "verify_design_assessment_digest",
]
