"""Decision Context — does this analysis contain enough to continue?

    ContextInput  ──►  evaluate_context(input, policy)  ──►  DecisionContext
                                                               ├─ state
                                                               ├─ five checks
                                                               └─ policy

**One question, and nothing else.** The engine never produces a direction, an
entry, an exit, a target, a stop, a position size or a risk number. Those belong
to milestones that do not exist, and a test asserts none of those words appears
in any public name or any statement this package can produce.

**It invents no threshold.** Every requirement delegates to the layer that
already declared the rule — `required_candles` for depth, the feature engine's
warm-up metadata for readiness, `fmis.market_regime` for whether a dimension
could classify, `fmis.level_crossing` for whether a level exists, and ADR-0008 §7
for whether the evidence layer could speak. That is why `ContextPolicy` carries
no numbers: a threshold here would be a second definition of a rule some layer
owns, and the second definition drifts.

**Conflicts never move the verdict.** Sufficiency is about what is *available*,
not about whether it agrees. Penalising disagreement would reward pages that look
tidy by being one-sided, which is the failure `docs/analysis-notes.md` records.

**Where it sits.** An engine below the application layer. It imports **nothing**
from the rest of `fmis`: its input is seven integers, two strings, a flag and a
timestamp, so it can be exercised without building a fact sheet.
"""

from __future__ import annotations

from fmis.decision_context.evaluate import SOURCES, evaluate_context
from fmis.decision_context.models import (
    REQUIREMENT_ORDER,
    SEVERITY,
    ContextInput,
    ContextInputError,
    ContextState,
    DecisionContext,
    DecisionContextError,
    Requirement,
    RequirementCheck,
    Severity,
    ViewAdequacy,
)
from fmis.decision_context.policy import (
    DEFAULT_CONTEXT_POLICY,
    ContextPolicy,
    ContextPolicyError,
)

__all__ = [
    # entry point
    "evaluate_context",
    # result
    "DecisionContext",
    "ContextState",
    "RequirementCheck",
    "Requirement",
    "Severity",
    "REQUIREMENT_ORDER",
    "SEVERITY",
    "SOURCES",
    # input boundary
    "ContextInput",
    "ViewAdequacy",
    # policy
    "ContextPolicy",
    "DEFAULT_CONTEXT_POLICY",
    # errors
    "DecisionContextError",
    "ContextInputError",
    "ContextPolicyError",
]
