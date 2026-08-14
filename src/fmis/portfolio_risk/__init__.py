"""Portfolio Intelligence & Risk — the deterministic step between facts and limits.

`AP` §15's boundary, built. The system stops evaluating trades one at a time and
answers one question:

    What changes in the portfolio if the owner opens this proposed trade now?

**Venue-agnostic by construction.** Every type here operates on `AccountId`,
`VenueId`, `MarketId`, `Book`, `Position`, `TradePlan`, `RiskBudget` and
`Money` — the domain's own abstractions. Nothing in this package imports a
provider, an exchange adapter, a chart source or any market-half engine, and a
guard test asserts it. Binance, EVEDEX, Bybit, a future DEX and a hand-kept
account all reach the same arithmetic through the same records; the venue is an
identifier on a `MarketId` and never the owner of portfolio logic.

**Three strata, kept apart** (`AP` §15.2):

| Stratum | Here | `ValueOrigin` |
|---|---|---|
| Deterministic portfolio facts | `PortfolioState`, `ExposureBreakdown` | `MEASURED` |
| The owner's own limits | `fmis.risk.RiskBudget`, read by `evaluate_constraints` | `ASSERTED` |
| Interpretation | **not here, and never will be** | `INTERPRETED` |

**There is no composite portfolio score, health grade or risk rating**, and there
never will be: *"a single number would collapse all three strata into one value
whose meaning no one could recover."* Every check returns `WITHIN`, `AT_LIMIT`,
`EXCEEDED` or `Absent(reason)`, and `PortfolioImpact` reports facts — it holds no
field that could say `BUY`, `SELL`, take or reject. The human owns the decision.

**Nothing here is stored.** A `PortfolioState` is a rebuildable projection in the
architecture's §24.3 sense: delete it, recompute it from the resolved ledger and
the same supplied marks, and the result is equal. The frozen half of the portfolio
is `PortfolioSnapshot`, which `PortfolioRepository` already owns and which this
package reads and never writes.

**Nothing is fabricated.** Marks, equity and cash are arguments; a missing one
produces `Absent(reason)` naming what is missing and which position broke the
figure. No aggregate silently shrinks, no missing value becomes zero, and a limit
this engine cannot measure is reported in its own list rather than counted as
within.

One layer touches disk — `fmis.portfolio_risk.reading` — and it only reads.
"""

from __future__ import annotations

from fmis.portfolio_risk.classification import ClassificationMap, unclassified_map
from fmis.portfolio_risk.constraints import (
    CONSTRAINT_POLICY_VERSION,
    PERCENT_UNIT_CONVENTION,
    ConstraintResult,
    PortfolioConstraintCheck,
    evaluate_constraints,
    remaining_risk_capacity,
)
from fmis.portfolio_risk.exposure import (
    DEFAULT_BOOKS_COVERED,
    SPOT_ONLY_MODES,
    breakdown_by,
    breakdown_by_group,
    build_state,
    markets_held_in_several_accounts,
)
from fmis.portfolio_risk.geometry import (
    RISK_BASIS,
    PortfolioRiskError,
    RiskGeometryError,
    capital_at_risk_of,
    maximum_quantity_for_risk,
    stop_distance,
    risk_fraction_of_equity,
)
from fmis.portfolio_risk.impact import (
    PROPOSED_MARK_SOURCE,
    IntendedEffect,
    PortfolioImpact,
    PortfolioNote,
    PositionOverlap,
    PositionRelationship,
    ProposedTrade,
    detect_overlap,
    evaluate_impact,
    lines_after,
)
from fmis.portfolio_risk.models import (
    UNCLASSIFIED,
    ExposureBreakdown,
    ExposureDimension,
    ExposureEntry,
    ExposureLine,
    ExposureSource,
    PendingCommitment,
    PortfolioState,
    direction_of,
    sum_or_absent,
)
from fmis.portfolio_risk.reading import (
    UNCLASSIFIED_VERSION,
    budget_in_force,
    read_equity_and_cash,
    read_exposure_lines,
    read_pending,
    read_portfolio,
)

__all__ = [
    # arithmetic
    "PortfolioRiskError",
    "RiskGeometryError",
    "RISK_BASIS",
    "stop_distance",
    "capital_at_risk_of",
    "risk_fraction_of_equity",
    "maximum_quantity_for_risk",
    # exposure
    "UNCLASSIFIED",
    "ExposureSource",
    "ExposureDimension",
    "ExposureLine",
    "ExposureEntry",
    "ExposureBreakdown",
    "PendingCommitment",
    "PortfolioState",
    "direction_of",
    "sum_or_absent",
    "DEFAULT_BOOKS_COVERED",
    "SPOT_ONLY_MODES",
    "build_state",
    "breakdown_by",
    "breakdown_by_group",
    "markets_held_in_several_accounts",
    # classification
    "ClassificationMap",
    "unclassified_map",
    # constraints
    "CONSTRAINT_POLICY_VERSION",
    "PERCENT_UNIT_CONVENTION",
    "ConstraintResult",
    "PortfolioConstraintCheck",
    "evaluate_constraints",
    "remaining_risk_capacity",
    # proposed-trade impact
    "PROPOSED_MARK_SOURCE",
    "ProposedTrade",
    "PositionRelationship",
    "IntendedEffect",
    "PositionOverlap",
    "PortfolioNote",
    "PortfolioImpact",
    "detect_overlap",
    "lines_after",
    "evaluate_impact",
    # reading the store
    "UNCLASSIFIED_VERSION",
    "read_exposure_lines",
    "read_pending",
    "read_equity_and_cash",
    "read_portfolio",
    "budget_in_force",
]
