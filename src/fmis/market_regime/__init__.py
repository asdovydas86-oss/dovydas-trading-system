"""Deterministic market-regime classification — the environment, never the direction.

    RegimeInput  ──►  classify_regime(input, policy)  ──►  MarketRegime
                                                             ├─ structure
                                                             ├─ volatility
                                                             └─ participation

`ARCH` §9 asks for "an explicit, testable classification of the market
environment that higher layers can condition on", carrying **evidence and
uncertainty** rather than a bare word, and reproducible on historical data. This
package is that, and nothing more.

**What it will not do.** No direction, no LONG or SHORT, no bullish or bearish,
no signal, no setup, no score, no confidence number, no recommendation, and no
overall label collapsing the three dimensions into one. `docs/analysis-notes.md`
records what a directional regime gate cost the v2 analyzer — checklists that
looked symmetric while one side was satisfied by conditions that hold most of the
time — and this engine cannot express that shape: it never learns which way a
trend points, and its thresholds are single bands whose two edges are
multiplicative mirrors.

**Where it sits.** An engine package at L5, below `fmis.pipeline`. It imports
`fmis.structural_trend` for one enum and nothing else from the repository; it
cannot see a fact sheet, a candle, a feature set or a provider. The application
composition root adapts what the engines produced into a `RegimeInput`, which is
the whole boundary — seven optional numbers, one enum, and an identity.

**Evidence votes by family.** Swing structure and moving averages are two
families; each contributes one vote and structure needs both to agree. No number
is read by two dimensions, so nothing can corroborate itself.
"""

from __future__ import annotations

from fmis.market_regime.classify import (
    FAMILY_MOVING_AVERAGES,
    FAMILY_SWING_STRUCTURE,
    FAMILY_TRUE_RANGE,
    FAMILY_VOLUME,
    classify_regime,
)
from fmis.market_regime.models import (
    EvidenceStatus,
    MarketRegime,
    MarketRegimeError,
    ParticipationState,
    RegimeDimension,
    RegimeDimensionName,
    RegimeEvidence,
    RegimeInput,
    RegimeInputError,
    StructureState,
    VolatilityState,
)
from fmis.market_regime.policy import (
    DEFAULT_POLICY,
    RegimePolicy,
    RegimePolicyError,
)

__all__ = [
    # entry point
    "classify_regime",
    # result models
    "MarketRegime",
    "RegimeDimension",
    "RegimeEvidence",
    "RegimeDimensionName",
    "EvidenceStatus",
    # dimension vocabularies
    "StructureState",
    "VolatilityState",
    "ParticipationState",
    # input boundary
    "RegimeInput",
    # policy
    "RegimePolicy",
    "DEFAULT_POLICY",
    # evidence families
    "FAMILY_SWING_STRUCTURE",
    "FAMILY_MOVING_AVERAGES",
    "FAMILY_TRUE_RANGE",
    "FAMILY_VOLUME",
    # errors
    "MarketRegimeError",
    "RegimeInputError",
    "RegimePolicyError",
]
