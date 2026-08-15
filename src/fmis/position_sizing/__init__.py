"""Position sizing and trade approval — *can I take this trade*, not *is it good*.

The setup engine (`AR`) already answers whether a directional idea exists. The
portfolio engine (`BL`) already answers what the book looks like and how it sits
against the owner's limits. Neither answers the question that stands between an
idea and an order:

> **How large may this position be, and do my own limits permit it?**

This package answers exactly that, and refuses everything adjacent to it.

    PositionProposal   what the owner is considering — no size yet
      -> PositionSizer          the fraction, the ceilings, one division
      -> PositionRecommendation a quantity, and every figure derived from it
      -> ApprovalEngine         the sized candidate against every limit
      -> ApprovalResult         APPROVED | BLOCKED | INDETERMINATE, with reasons

**`ApprovalResult` is a deterministic fact, not an AI opinion.** No model is
consulted anywhere in this package, no probability is attached to anything, and
there is no field on any type here that could hold *"take this trade"* or *"skip
this trade"* — a guard test asserts the package names neither. `AP` §15.5:
*"`EXCEEDED` on the open-risk budget is a fact; 'don't take this trade' is the
owner's conclusion."*

**This engine never executes.** No order is placed, no exchange is reached, no
capital is reserved and nothing is written to the store. It reads and it reports.

**It invents no threshold.** Every number a size is decided by is the owner's:
the fraction they chose, the ceiling they set, the staleness bounds they
configured, the severity they attached to each limit. A test asserts the four
computing modules hold no numeric literal beyond `0` and `1` — the same test
`fmis.risk` and `fmis.portfolio_risk` already pass.

**It duplicates no arithmetic.** The sign rule, the risk distance, the capital at
risk, the maximum quantity for a risk allowance, the exposure fold, the
before/after impact and every limit comparison are all `fmis.portfolio_risk`'s,
called rather than re-implemented. The one thing this package adds is the step
that engine deliberately left out: deciding what the risk allowance should be —
which needs the owner's equity, their chosen fraction and their own ceilings, and
is *"not built at the portfolio boundary, because placing it in Portfolio would
give the portfolio object a recommendation"* (`AP` §15.4).

**Three answers, and the third is not a milder first.** `INDETERMINATE` means
something could not be measured; it is never rendered, counted or reasoned about
as `APPROVED`, and `ApprovalResult` refuses to hold that combination at all.
"""

from __future__ import annotations

from fmis.position_sizing.approval import (
    APPROVAL_POLICY_VERSION,
    REQUIRED_AXES,
    ApprovalEngine,
)
from fmis.position_sizing.compose import (
    APPROVAL_CLASSIFICATION_VERSION,
    DEFAULT_BOOK,
    DEFAULT_OWNER_TIMEZONE,
    ApprovalUnavailableError,
    engine_for,
    owner_context,
    portfolio_for,
    proposal_for_plan,
    resolve_account,
    run_approval,
)
from fmis.position_sizing.inputs import (
    APPROVAL_ERRORS,
    DEFAULT_SIZING_POLICY_ID,
    approve_results,
    price_from_text,
    proposal_from_text,
    proposals_from_results,
    scope_from_text,
    sizing_policy_from_text,
)
from fmis.position_sizing.models import (
    ApprovalReason,
    ApprovalResult,
    ApprovalStatus,
    PositionProposal,
    PositionRecommendation,
    PositionSizingError,
    ReasonClass,
    ReasonScope,
    SizingOutcome,
    SizingRefusedError,
)
from fmis.position_sizing.policy import (
    SIZING_POLICY_VERSION,
    FractionChoice,
    SizingPolicy,
    per_trade_ceiling,
)
from fmis.position_sizing.reading import (
    accounts_in,
    budget_in_effect,
    plan_to_size,
    sole_account,
)
from fmis.position_sizing.render import (
    APPROVAL_LIMITATIONS,
    STATUS_MEANING,
    render_approval,
)
from fmis.position_sizing.sizing import ROUNDING_NOTE, PositionSizer

__all__ = [
    # errors
    "PositionSizingError",
    "SizingRefusedError",
    "ApprovalUnavailableError",
    "APPROVAL_ERRORS",
    # the candidate and the size
    "PositionProposal",
    "PositionRecommendation",
    "SizingOutcome",
    "SizingPolicy",
    "FractionChoice",
    "PositionSizer",
    "SIZING_POLICY_VERSION",
    "ROUNDING_NOTE",
    "per_trade_ceiling",
    # the approval
    "ApprovalEngine",
    "ApprovalResult",
    "ApprovalReason",
    "ApprovalStatus",
    "ReasonScope",
    "ReasonClass",
    "APPROVAL_POLICY_VERSION",
    "REQUIRED_AXES",
    # the store
    "budget_in_effect",
    "sole_account",
    "accounts_in",
    "plan_to_size",
    # the outer edge
    "DEFAULT_OWNER_TIMEZONE",
    "DEFAULT_BOOK",
    "DEFAULT_SIZING_POLICY_ID",
    "APPROVAL_CLASSIFICATION_VERSION",
    "owner_context",
    "engine_for",
    "portfolio_for",
    "resolve_account",
    "proposal_for_plan",
    "run_approval",
    # the text boundary
    "price_from_text",
    "scope_from_text",
    "proposal_from_text",
    "sizing_policy_from_text",
    "proposals_from_results",
    "approve_results",
    # rendering
    "APPROVAL_LIMITATIONS",
    "STATUS_MEANING",
    "render_approval",
]
