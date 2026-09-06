"""Risk policy: the owner's declaration, and the first producer of a `RiskBudget`.

**The link the risk chain never had.** `fmis.risk`, `fmis.position_sizing` and
`fmis.portfolio_risk` were complete, tested and unreachable: before this package
``RiskBudget(`` and ``RiskLimit(`` appeared nowhere in `src/`, only in tests, so
no product surface could bring one into existence and none of the arithmetic
below them could run.

    RiskPolicyDeclaration      what the owner declared: capital, and a fraction
      -> budget_from()              the specification's 2 % ceiling, as a RiskBudget
      -> sizing_policy_from()       the declared fraction, as a SizingPolicy
      -> plan_for()                 one symbol's TradeRiskPlan, or what it is missing

**`SPECIFICATION_PER_TRADE_CEILING` lives here and nowhere else.** `SPEC` §8.1's
2 % is structural: a declaration above it cannot be constructed. It is not a
default, not a target and not a recommendation, and nothing here supplies a
fraction the owner did not state.

**This package computes no risk arithmetic and holds no directional opinion.** It
builds inputs and copies results. Every quotient is `fmis.position_sizing`'s and
`fmis.portfolio_risk`'s, and no evidence count, confidence, family independence
or setup state reaches any value below.
"""

from __future__ import annotations

from fmis.risk_policy.declaration import (
    DECLARATION_FILENAME,
    RiskPolicyFileError,
    declaration_from_mapping,
    declaration_path,
    load_declaration,
)
from fmis.risk_policy.models import (
    SPECIFICATION_PER_TRADE_CEILING,
    RiskPolicyDeclaration,
    RiskPolicyError,
)
from fmis.risk_policy.planning import (
    ENTRY_CAVEAT,
    PLANNING_LIMITATIONS,
    PlanningStatus,
    TradeRiskPlan,
    budget_from,
    plan_for,
    plans_for_results,
    sizing_policy_from,
)

__all__ = [
    # the declaration and the ceiling
    "RiskPolicyError",
    "RiskPolicyFileError",
    "SPECIFICATION_PER_TRADE_CEILING",
    "RiskPolicyDeclaration",
    # reading the owner's file
    "DECLARATION_FILENAME",
    "declaration_path",
    "load_declaration",
    "declaration_from_mapping",
    # the producers, and the plan
    "ENTRY_CAVEAT",
    "PLANNING_LIMITATIONS",
    "PlanningStatus",
    "TradeRiskPlan",
    "budget_from",
    "sizing_policy_from",
    "plan_for",
    "plans_for_results",
]

#: **Deliberately not exported**, though they are public names on their own
#: modules: `SPECIFICATION_CEILING_SOURCE`, `RISK_POLICY_CONTRACT_VERSION`,
#: `SUPPORTED_RISK_POLICY_VERSIONS`, `PLANNING_ACCOUNT`, `PLANNING_BOOK`,
#: `PLANNING_BUDGET_ID`, `PLANNING_POLICY_ID` and `CEILING_LIMIT_ID`. Each is
#: consumed inside this package — the first three reach a surface as fields on
#: `TradeRiskPlan`, the rest are the default arguments of `budget_from`,
#: `sizing_policy_from` and `plan_for` — and none is imported anywhere else.
#: `fmis.risk`, `fmis.portfolio_risk` and `fmis.position_sizing` each carry at
#: most one export nothing outside them uses; a package publishing eight would be
#: publishing a surface no consumer asked for. They stay reachable as
#: `fmis.risk_policy.planning.PLANNING_BOOK` for a caller that overrides a
#: default, which is the only reason to name one.
