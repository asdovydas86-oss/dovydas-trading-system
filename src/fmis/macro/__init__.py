"""Macro & cross-asset context — deterministic facts about markets outside crypto.

Milestone BU. The layer that turns published macro observations into stated
facts, and stops there:

    RAW SOURCE DATA
        -> fmis.providers.fred            CSV -> canonical ObservationSeries
        -> fmis.macro.context             observations -> measured facts
        -> fmis.macro.models              facts -> one frozen report
        -> fmis.macro.render              report -> a page
        -> LATER INTERPRETATION           (not in this build)

**This package stops before interpretation, and there is nothing here to cross
that line with.** It contains no AI call, no prompt, no prediction, no causal
claim, no regime label and no signal. It will state that the 10-year moved +10 bp
and that the S&P and Bitcoin correlated 0.31 over 21 shared observations; it will
never state that yields are pressuring equities. That reading is a later
milestone's, and it will consume these facts rather than replace them.

**It is not a trading package and is deliberately not named like one.** Nothing
here is called *swing* anything. The same facts serve an equity thesis, an ETF or
sector review, a country analysis and a portfolio risk review, none of which have
any business importing a trade plan — and this package imports none.

What it owns that nothing else did:

  * `rates` — a yield is not a price. Basis points, percentage points and the
    relative change are three named quantities and none is *the* change.
  * `comparability` — an explicit refusal mechanism. Two measurements are placed
    side by side only when they are the same question, and a refusal names every
    component that differs.
  * `models` — a level, a rate fact, a relationship and a report, each of which
    can hold an absence with its reason and none of which can hold a blank.

What it deliberately reuses rather than reimplements:

  * `fmis.market_pulse` — the benchmark registry, the horizons and the reading
    types. There is **one** registry in this repository and this is not it.
  * `fmis.relative_value` — every return, volatility and correlation.
  * `fmis.alignment` — the intersection that makes a five-day market comparable
    with a seven-day one, with its own diagnostics.
"""

from __future__ import annotations

from fmis.macro.comparability import (
    COMPARABILITY_RULE,
    CORRELATION_COMPARABILITY_RULE,
    Comparability,
    ComparabilityKey,
    NotComparableReason,
    compare_for_correlation,
    compare_keys,
)
from fmis.macro.context import (
    RATE_CHANGE_METRIC,
    RELATIONSHIP_METRIC,
    RELATIONSHIP_MINIMUM_OBSERVATIONS,
    build_macro_context,
    build_rate_fact,
    comparability_key,
    macro_level,
    observations_reference,
    relate_markets,
)
from fmis.macro.models import (
    MACRO_FRESHNESS_NOTE,
    MACRO_ORIENTATION_NOTE,
    MACRO_RATE_NOTE,
    MACRO_RELATIONSHIP_CAVEAT,
    MACRO_SESSION_LIMITATION,
    CrossAssetRelationship,
    MacroContextReport,
    MacroError,
    MacroLevel,
    MacroReportError,
    RateFact,
)
from fmis.macro.rates import (
    BASIS_POINTS_PER_PERCENTAGE_POINT,
    RATE_LEVEL_UNIT,
    RateChange,
    RateChangeError,
    rate_change,
)
from fmis.macro.render import MACRO_PAGE_WIDTH, render_macro_context

__all__ = [
    # comparability
    "COMPARABILITY_RULE",
    "CORRELATION_COMPARABILITY_RULE",
    "Comparability",
    "ComparabilityKey",
    "NotComparableReason",
    "compare_for_correlation",
    "compare_keys",
    # rates
    "BASIS_POINTS_PER_PERCENTAGE_POINT",
    "RATE_LEVEL_UNIT",
    "RateChange",
    "RateChangeError",
    "rate_change",
    # models
    "MACRO_FRESHNESS_NOTE",
    "MACRO_ORIENTATION_NOTE",
    "MACRO_RATE_NOTE",
    "MACRO_RELATIONSHIP_CAVEAT",
    "MACRO_SESSION_LIMITATION",
    "CrossAssetRelationship",
    "MacroContextReport",
    "MacroError",
    "MacroLevel",
    "MacroReportError",
    "RateFact",
    # context
    "RATE_CHANGE_METRIC",
    "RELATIONSHIP_METRIC",
    "RELATIONSHIP_MINIMUM_OBSERVATIONS",
    "build_macro_context",
    "build_rate_fact",
    "comparability_key",
    "macro_level",
    "observations_reference",
    "relate_markets",
    # render
    "MACRO_PAGE_WIDTH",
    "render_macro_context",
]
