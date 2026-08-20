"""Setup Evidence — the deterministic explanation layer for a `SetupAssessment`.

Answers, for one already-produced assessment: why this setup exists, what
currently supports it, what conflicts with it, what is still awaited, what could
not be read, and whether enough deterministic information exists to decide.

    fmis.swing_setup (SetupAssessment) -> fmis.setup_evidence (SetupEvidenceReport)

**This is a projection, not a second decision engine.** It re-decides nothing.
`sufficiency`, `directional_factors`, `invalidation`, `confirmation`,
`limitations` and `thesis` are carried through or grouped, never reinterpreted,
and `decision_ready` is a total function of `sufficiency` alone.

**Why it is a separate package, and not `fmis.evidence`.** `fmis.evidence` is a
*taxonomy* — `EvidenceFamily`, `EvidenceDescriptor` and a catalog — and
ADR-0011 §4 explicitly rejected putting supporting/conflicting/unavailable
vocabulary inside it, because `fmis.decision_support` already owns those
concepts one layer down. This package is the taxonomy's first real consumer in
the sense ADR-0011 §7 intended: *shared vocabulary, separate interpretation*. It
imports `EvidenceFamily` and adds nothing to it.

**Why the report is not called `EvidenceReport`.**
`fmis.decision_support.EvidenceReport` already exists and means something
narrower — classified observations over one `AnalysisSnapshot`. Two classes with
one name in one repository is a defect waiting to happen, so this one is
`SetupEvidenceReport` and the two never meet.

**The thing this package exists to prevent.** Correlated readings presented as
independent corroboration. Three items that all restate one upstream fact look
exactly like three-fold agreement on a page. `fmis.setup_evidence.correlation`
holds every established correlation with its reason, confluence is measured over
*families* rather than items, and independence is reported as NOT established
whenever it is not proven. See that module for the five correlations currently
known, including the regime precondition that is the same reading as the context
trend vote.

Rules for anything added here:
  * **Consumes a `SetupAssessment` only.** No provider, no engine call, no
    candle, no store, no clock, no network.
  * **No score, weight, confidence, probability or rank**, in a value, a field
    name or metadata. A four-level strength enum was specified for this
    milestone and deliberately dropped — see `models`.
  * **No direction is named in this package's source.** ADR-0028 permits that
    vocabulary in `fmis.swing_setup` and `pipeline/cli.py` only; values are
    carried at runtime, never spelled here.
  * **Nothing below imports this** — test-enforced.
"""

from __future__ import annotations

from fmis.setup_evidence.correlation import (
    FACTOR_FAMILIES,
    KNOWN_CORRELATIONS,
    CorrelationRule,
    standing_family_note,
)
from fmis.setup_evidence.models import (
    SETUP_EVIDENCE_PROJECTION_VERSION,
    ConfluenceSummary,
    EvidenceItem,
    SetupEvidenceStatus,
    FamilySummary,
    SetupEvidenceError,
    SetupEvidenceReport,
    SetupIdentityRef,
)
from fmis.setup_evidence.project import (
    DECISION_READY_REASONS,
    decision_ready_for,
    project_setup_evidence,
)
from fmis.setup_evidence.render import PAGE_WIDTH, render_setup_evidence

__all__ = [
    # entry point
    "project_setup_evidence",
    # report types
    "SetupEvidenceReport",
    "EvidenceItem",
    "SetupEvidenceStatus",
    "FamilySummary",
    "ConfluenceSummary",
    "SetupIdentityRef",
    "SetupEvidenceError",
    # correlation vocabulary
    "CorrelationRule",
    "KNOWN_CORRELATIONS",
    "FACTOR_FAMILIES",
    "standing_family_note",
    # readiness
    "decision_ready_for",
    "DECISION_READY_REASONS",
    # rendering
    "render_setup_evidence",
    "PAGE_WIDTH",
    # versioning
    "SETUP_EVIDENCE_PROJECTION_VERSION",
]
