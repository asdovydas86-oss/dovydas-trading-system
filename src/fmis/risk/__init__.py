"""Risk: the owner's asserted limits, and the measured state of each.

Two objects, never one. `RiskBudget` is `ASSERTED` and versioned;
`RiskBudgetState` is `MEASURED` and recomputed. Merging them would produce a
record whose limit appears to change whenever exposure changes.

**No threshold is defined in this package.** Every value is the owner's.
"""

from __future__ import annotations

from fmis.risk.models import (
    RISK_BUDGET_KIND,
    RISK_BUDGET_SCHEMA_VERSION,
    RISK_BUDGET_TYPE_SLUG,
    SUPPORTED_RISK_BUDGET_VERSIONS,
    LimitEvaluation,
    LimitPeriod,
    LimitScope,
    LimitSeverity,
    LimitStatus,
    LimitUnit,
    RiskBudget,
    RiskBudgetState,
    RiskError,
    RiskLimit,
    effective_budget,
    evaluate_budget,
    evaluate_limit,
    period_key,
)

__all__ = [
    "RiskError",
    "LimitScope",
    "LimitUnit",
    "LimitPeriod",
    "LimitSeverity",
    "LimitStatus",
    "RiskLimit",
    "RiskBudget",
    "LimitEvaluation",
    "RiskBudgetState",
    "effective_budget",
    "period_key",
    "evaluate_limit",
    "evaluate_budget",
    "RISK_BUDGET_SCHEMA_VERSION",
    "SUPPORTED_RISK_BUDGET_VERSIONS",
    "RISK_BUDGET_TYPE_SLUG",
    "RISK_BUDGET_KIND",
]
