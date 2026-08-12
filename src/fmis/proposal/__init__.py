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
]
