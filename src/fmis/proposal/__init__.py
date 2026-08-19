"""The decision chain's first two objects: the proposal and its lifecycle stream.

`OpportunityProposal` is the brief's *Opportunity*; the lifecycle stream is the
brief's *Decision*, and `ProposalState` is the half of the brief's *TradeStatus*
that belongs to a suggestion rather than to money.

The package reads `fmis.snapshotting` for the frozen bundle a proposal rests on
and imports nothing from the market half. Whether the setup engine's own live
`SetupObservation` becomes a type here is a later slice's question; what is frozen
onto a snapshot is the reading, and that is what a proposal cites.
"""

from __future__ import annotations

from fmis.proposal.lifecycle import (
    ASSERTED_KINDS,
    LIFECYCLE_EVENT_SCHEMA_VERSION,
    LIFECYCLE_EVENT_TYPE_SLUG,
    MEASURED_KINDS,
    SUPPORTED_LIFECYCLE_EVENT_VERSIONS,
    TERMINAL_STATES,
    TRANSITIONS,
    AdmissionOutcome,
    IllegalTransitionError,
    KIND_ORIGINS,
    LifecycleKind,
    ProposalAdmission,
    ProposalLifecycleEvent,
    ProposalState,
    ProposalStateView,
    admit,
    fold_proposal_state,
)
from fmis.proposal.observation import ObservationError, SetupObservation
from fmis.proposal.occurrence import (
    OccurrenceError,
    SetupOccurrence,
    group_occurrences,
)
from fmis.proposal.setup_identity import (
    SETUP_IDENTITY_VERSION,
    SETUP_VOCABULARY_ID,
    anchor_identity,
    anchor_of,
    anchors_match,
    level_origin_ref,
    stable_origin_id,
)
from fmis.proposal.models import (
    AUTHOR_ORIGINS,
    UNCALIBRATED_PROBABILITY,
    PROPOSAL_KIND,
    PROPOSAL_SCHEMA_VERSION,
    PROPOSAL_TYPE_SLUG,
    SUPPORTED_PROPOSAL_VERSIONS,
    DirectionalAssessment,
    DirectionalCase,
    EvidenceCitation,
    ModelAttribution,
    OpportunityProposal,
    ProposalAuthor,
    ProposalError,
    StatedConfidence,
)

__all__ = [
    "ProposalError",
    "IllegalTransitionError",
    # the proposal
    "OpportunityProposal",
    "ProposalAuthor",
    "AUTHOR_ORIGINS",
    "StatedConfidence",
    "ModelAttribution",
    "DirectionalCase",
    "DirectionalAssessment",
    "EvidenceCitation",
    "UNCALIBRATED_PROBABILITY",
    "PROPOSAL_SCHEMA_VERSION",
    "SUPPORTED_PROPOSAL_VERSIONS",
    "PROPOSAL_TYPE_SLUG",
    "PROPOSAL_KIND",
    # the lifecycle stream
    "ProposalLifecycleEvent",
    "LifecycleKind",
    "KIND_ORIGINS",
    "MEASURED_KINDS",
    "ASSERTED_KINDS",
    "ProposalState",
    "TERMINAL_STATES",
    "TRANSITIONS",
    "ProposalStateView",
    "fold_proposal_state",
    "LIFECYCLE_EVENT_SCHEMA_VERSION",
    "SUPPORTED_LIFECYCLE_EVENT_VERSIONS",
    "LIFECYCLE_EVENT_TYPE_SLUG",
    # creation rule 4
    "AdmissionOutcome",
    "ProposalAdmission",
    "admit",
    # BG-D1 — stable setup identity and its two projections
    "SETUP_VOCABULARY_ID",
    "SETUP_IDENTITY_VERSION",
    "stable_origin_id",
    "level_origin_ref",
    "anchor_of",
    "anchor_identity",
    "anchors_match",
    "ObservationError",
    "SetupObservation",
    "OccurrenceError",
    "SetupOccurrence",
    "group_occurrences",
]
