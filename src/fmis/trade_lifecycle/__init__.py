"""The lifecycle of a commitment that has been acted on — the domain half.

Four record types and two folds, and nothing else:

| Type | Durability | Answers |
|---|---|---|
| `TradeActivation` | Captured artifact | *What was activated, at what size, on what entry?* |
| `TradeLifecycleEvent` | Source of truth | *What happened to it, and in what order?* |
| `StopAmendment` | Source of truth | *Where has the stop been moved, by whom, and why?* |
| `TradeOutcome` | Captured artifact | *How did it end, and how far did it run either way?* |

**No state is stored.** `fold_trade_lifecycle` and `fold_stop_history` are the
only places a state or an effective stop exists, and both are pure: delete every
folded value, recompute it, and the answer is identical.

**This package holds no candle, no clock, no path and no store.** Every instant
is an argument and every price is already exact, which is what lets
`fmis.persistence` import it — a domain package the store depends on must not
reach the market half, or the store transitively depends on a candle decoder.
`fmis.paper` sits one layer above and owns the single crossing.

**It computes no risk arithmetic of its own.** The sign rule is
`TradeDirection.sign`, the risk distance is `fmis.portfolio_risk.stop_distance`,
the average entry is `AverageCost.per_unit` and the position fold is
`fmis.positions.fold_positions` — every one of them called from `fmis.paper`,
where they can be reached without inverting the store's dependency direction.
"""

from __future__ import annotations

from fmis.trade_lifecycle.events import (
    CAUSAL_RANK,
    LIFECYCLE_KIND_ORIGINS,
    LIFECYCLE_TRANSITIONS,
    LIVE_LIFECYCLE_STATES,
    MEASURED_LIFECYCLE_KINDS,
    SUPPORTED_TRADE_LIFECYCLE_EVENT_VERSIONS,
    TERMINAL_LIFECYCLE_STATES,
    TRADE_LIFECYCLE_EVENT_KIND,
    TRADE_LIFECYCLE_EVENT_SCHEMA_VERSION,
    TRADE_LIFECYCLE_EVENT_TYPE_SLUG,
    IllegalLifecycleTransitionError,
    TradeLifecycleEvent,
    TradeLifecycleKind,
    TradeLifecycleState,
    TradeLifecycleView,
    fold_trade_lifecycle,
)
from fmis.trade_lifecycle.models import (
    SUPPORTED_TRADE_ACTIVATION_VERSIONS,
    TRADE_ACTIVATION_KIND,
    TRADE_ACTIVATION_SCHEMA_VERSION,
    TRADE_ACTIVATION_TYPE_SLUG,
    ActivationError,
    BreakEvenRule,
    EntryType,
    ExitLadder,
    ExitLeg,
    PaperCostPolicy,
    StopManagement,
    TradeActivation,
    TradeLifecycleError,
    TrailingRule,
)
from fmis.trade_lifecycle.outcome import (
    EXPOSED_EXIT_REASONS,
    SUPPORTED_TRADE_OUTCOME_VERSIONS,
    TRADE_OUTCOME_KIND,
    TRADE_OUTCOME_SCHEMA_VERSION,
    TRADE_OUTCOME_TYPE_SLUG,
    ExitReason,
    OutcomeError,
    TradeOutcome,
)
from fmis.trade_lifecycle.stops import (
    AMENDABLE_ORIGINS,
    BREAK_EVEN_TERM,
    STOP_AMENDMENT_KIND,
    STOP_AMENDMENT_REASON_VOCABULARY,
    STOP_AMENDMENT_SCHEMA_VERSION,
    STOP_AMENDMENT_TYPE_SLUG,
    STOP_POLICY_VOCABULARY,
    SUGGESTED_AMENDMENT_REASONS,
    SUPPORTED_STOP_AMENDMENT_VERSIONS,
    TRAILING_TERM,
    StopAmendment,
    StopAmendmentError,
    StopHistory,
    StopMove,
    fold_stop_history,
)

__all__ = [
    # errors
    "TradeLifecycleError",
    "ActivationError",
    "StopAmendmentError",
    "OutcomeError",
    "IllegalLifecycleTransitionError",
    # the activation
    "TRADE_ACTIVATION_SCHEMA_VERSION",
    "SUPPORTED_TRADE_ACTIVATION_VERSIONS",
    "TRADE_ACTIVATION_TYPE_SLUG",
    "TRADE_ACTIVATION_KIND",
    "EntryType",
    "ExitLeg",
    "ExitLadder",
    "BreakEvenRule",
    "TrailingRule",
    "StopManagement",
    "PaperCostPolicy",
    "TradeActivation",
    # the lifecycle stream
    "TRADE_LIFECYCLE_EVENT_SCHEMA_VERSION",
    "SUPPORTED_TRADE_LIFECYCLE_EVENT_VERSIONS",
    "TRADE_LIFECYCLE_EVENT_TYPE_SLUG",
    "TRADE_LIFECYCLE_EVENT_KIND",
    "TradeLifecycleKind",
    "LIFECYCLE_KIND_ORIGINS",
    "MEASURED_LIFECYCLE_KINDS",
    "CAUSAL_RANK",
    "TradeLifecycleState",
    "TERMINAL_LIFECYCLE_STATES",
    "LIVE_LIFECYCLE_STATES",
    "LIFECYCLE_TRANSITIONS",
    "TradeLifecycleEvent",
    "TradeLifecycleView",
    "fold_trade_lifecycle",
    # stop management
    "STOP_AMENDMENT_SCHEMA_VERSION",
    "SUPPORTED_STOP_AMENDMENT_VERSIONS",
    "STOP_AMENDMENT_TYPE_SLUG",
    "STOP_AMENDMENT_KIND",
    "STOP_AMENDMENT_REASON_VOCABULARY",
    "STOP_POLICY_VOCABULARY",
    "SUGGESTED_AMENDMENT_REASONS",
    "BREAK_EVEN_TERM",
    "TRAILING_TERM",
    "AMENDABLE_ORIGINS",
    "StopAmendment",
    "StopMove",
    "StopHistory",
    "fold_stop_history",
    # the outcome
    "TRADE_OUTCOME_SCHEMA_VERSION",
    "SUPPORTED_TRADE_OUTCOME_VERSIONS",
    "TRADE_OUTCOME_TYPE_SLUG",
    "TRADE_OUTCOME_KIND",
    "ExitReason",
    "EXPOSED_EXIT_REASONS",
    "TradeOutcome",
]
