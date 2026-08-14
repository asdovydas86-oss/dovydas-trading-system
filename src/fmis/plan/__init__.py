"""What the owner committed to, before the market moved.

`TradePlan` is the data model's entity 19 (§10.3) and the architecture's §9 —
designed since Milestone AP, named as accepted debt by
`SWING_TRADING_MVP_BLUEPRINT_V1` §12.3, and built here because the alternative is
a stop with nowhere to live. §11.6 assigns *stop, target and intended size* to
this entity by name, and a swing trade recorded without them is a fill, not a
decision.

`adherence` holds the read-time comparison: capital at risk, the planned
risk/reward pair, and where an exit landed against the level nearest to it. Every
one is arithmetic over values the caller supplies, and none is stored.

**`PlanAmendment` is not built.** §10.4's amendment stream is what makes a
*widened* stop visible, and nothing in this milestone widens one. Until it
exists, every field here is immutable — stricter than §10.3, and the gap is
recorded rather than closed by a record type nobody writes.
"""

from __future__ import annotations

from fmis.plan.adherence import (
    ExitDivergence,
    PlanPlacementError,
    capital_at_risk,
    check_placement,
    exit_divergence,
    nearest_planned_level,
    planned_risk_reward,
    risk_distance,
)
from fmis.plan.models import (
    SUPPORTED_TRADE_PLAN_VERSIONS,
    TRADE_PLAN_KIND,
    TRADE_PLAN_SCHEMA_VERSION,
    TRADE_PLAN_TYPE_SLUG,
    PlanError,
    TradePlan,
)

__all__ = [
    "PlanError",
    "PlanPlacementError",
    "TradePlan",
    "TRADE_PLAN_SCHEMA_VERSION",
    "SUPPORTED_TRADE_PLAN_VERSIONS",
    "TRADE_PLAN_TYPE_SLUG",
    "TRADE_PLAN_KIND",
    "ExitDivergence",
    "check_placement",
    "risk_distance",
    "capital_at_risk",
    "planned_risk_reward",
    "nearest_planned_level",
    "exit_divergence",
]
