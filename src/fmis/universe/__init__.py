"""Can this repository build a universe big enough to ask its own question?

Milestone CA measured 155 matched swing admissions over 15 symbols and returned
`NO_EDGE`. Milestone CB then established that the experiment was `UNDERPOWERED`,
that the binding dimension was `cluster_count`, and that resolving the declared
+0.10 ATR effect would need roughly **4,823 admissions across roughly 467
clusters** — about thirty times the data CA had.

Milestone CC asks whether such a universe exists. Not whether the strategy works;
not whether an edge is there. **Whether the question can be honestly asked at
all.**

**The distinction this package exists to enforce.**

    3,645 tickers  !=  656 economic assets
      656 assets   !=  38 that can be measured
       38 assets   !=  38 independent experimental clusters

Each arrow is a real loss and each is measured rather than assumed. A trading pair
is a market, not an asset — `BTCUSDT` and `WBTCUSDT` price one exposure. An asset
is not an experiment — the production context role reads 250 weekly candles, so an
instrument needs 1,750 days of history *before* a measurement window opens, and
most listings are younger than that. And assets are not independent — crypto
returns share a market factor that accounts for well over half their variance, so
``K`` assets supply ``K / (1 + (K-1) r)`` effective clusters, which **saturates at
1/r** however many are added.

**What is deliberately absent.** No verdict here approves trading, paper trading,
shadow trading or a strategy; `FeasibilityVerdict.is_approved_for_trading` is
`False` for every member and a hostile test asserts it over the whole enum. No
production constant is changed — `CONFIRMATION_LOOKBACK_BARS`,
`MINIMUM_AGREEING_FAMILIES`, the context-role semantics, the trend, regime and
geometry logic are all untouched, and a production-safety test asserts their
values. And no statistics are reimplemented: the design arithmetic is Milestone
CB's `fmis.research_design`, called rather than copied.

**Nothing here reads an outcome.** Eligibility consumes timestamps, bar counts,
prices and volumes; dependence consumes price returns; ordering consumes history
and a ticker. `fmis.universe.controls` proves this non-vacuously rather than
asserting it — each control is paired with a broken input it is shown to catch.

**Two endpoints, read-only, no key.** `exchangeInfo` for discovery and `klines`
for history, both public and unauthenticated. Nothing signs a request, reads a
credential or touches an order path.
"""

from __future__ import annotations

from fmis.universe.artifact import (
    CC_ARTIFACT_KIND,
    CC_ARTIFACT_SCHEMA_VERSION,
    OFFLINE_CLAIM,
    UniverseArtifact,
    artifact_digest,
    encode_universe_study,
    read_universe_artifact,
    verify_artifact_digest,
    write_universe_artifact,
)
from fmis.universe.capture import (
    EPOCH,
    DailyBar,
    SeriesCache,
    discover_pairs,
    fetch_daily_bars,
    network_is_fatal,
    series_digest,
)
from fmis.universe.controls import (
    ControlResult,
    offline_reproduction,
    ordering_is_outcome_free,
    outcome_free_decision,
    perturb_outcomes,
)
from fmis.universe.density import (
    AssetDensity,
    DensitySummary,
    count_admissions,
    published_densities,
    subsample_for_density,
    summarise_density,
)
from fmis.universe.dependence import (
    DependenceSummary,
    correlated_groups,
    effective_clusters,
    log_returns,
    measure_dependence,
    pearson,
)
from fmis.universe.eligibility import (
    FunnelCounts,
    assess_asset,
    coverage_of,
    funnel_counts,
    liquidity_of,
    peg_disagreements,
    quality_of,
    screen_pair,
    usable_measurement_years,
    warmup_prefix,
)
from fmis.universe.growth import (
    EffectRequirement,
    GrowthRow,
    ca_observation_dispersion,
    cb_required_information,
    effect_for,
    growth_curve,
    growth_row,
    requirement_for_effect,
)
from fmis.universe.horizon import (
    AssetHorizon,
    HorizonCeiling,
    asset_horizon,
    horizon_ceiling,
)
from fmis.universe.identity import (
    LEVERAGED_TOKENS,
    REDENOMINATIONS,
    STABLECOIN_ASSETS,
    WRAPPED_REPRESENTATIONS,
    classify_asset,
    economic_asset_id,
    group_by_economic_asset,
    identity_rules_payload,
    peg_like_by_volatility,
)
from fmis.universe.models import (
    AssetAssessment,
    AssetClass,
    CoverageMetrics,
    EconomicAsset,
    Exclusion,
    ExclusionReason,
    FeasibilityVerdict,
    FunnelStage,
    LiquidityEvidence,
    PairStatus,
    QualityMetrics,
    SurvivorshipClass,
    TradingPair,
    UniverseError,
)
from fmis.universe.preregistration import (
    CC_PREREGISTRATION_DIGEST,
    CC_PREREGISTRATION_ID,
    CC_PRE_REGISTRATION,
    CcPreregistration,
    cc_preregistration_digest,
    measurement_window,
    representative_of,
    verify_cc_preregistration,
)
from fmis.universe.render import render_funnel, render_growth, render_universe_study
from fmis.universe.study import UniverseStudy, ordered_assets, run_universe_study
from fmis.universe.verdict import (
    FeasibilityAssessment,
    SurvivorshipReading,
    classify_survivorship,
    decide_feasibility,
)

__all__ = [
    "AssetAssessment",
    "AssetClass",
    "AssetDensity",
    "AssetHorizon",
    "CC_ARTIFACT_KIND",
    "CC_ARTIFACT_SCHEMA_VERSION",
    "CC_PREREGISTRATION_DIGEST",
    "CC_PREREGISTRATION_ID",
    "CC_PRE_REGISTRATION",
    "CcPreregistration",
    "ControlResult",
    "CoverageMetrics",
    "DailyBar",
    "DensitySummary",
    "DependenceSummary",
    "EPOCH",
    "EconomicAsset",
    "EffectRequirement",
    "Exclusion",
    "ExclusionReason",
    "FeasibilityAssessment",
    "FeasibilityVerdict",
    "FunnelCounts",
    "FunnelStage",
    "GrowthRow",
    "HorizonCeiling",
    "LEVERAGED_TOKENS",
    "LiquidityEvidence",
    "OFFLINE_CLAIM",
    "PairStatus",
    "QualityMetrics",
    "REDENOMINATIONS",
    "STABLECOIN_ASSETS",
    "SeriesCache",
    "SurvivorshipClass",
    "SurvivorshipReading",
    "TradingPair",
    "UniverseArtifact",
    "UniverseError",
    "UniverseStudy",
    "WRAPPED_REPRESENTATIONS",
    "artifact_digest",
    "assess_asset",
    "asset_horizon",
    "ca_observation_dispersion",
    "cb_required_information",
    "cc_preregistration_digest",
    "classify_asset",
    "classify_survivorship",
    "correlated_groups",
    "count_admissions",
    "coverage_of",
    "decide_feasibility",
    "discover_pairs",
    "economic_asset_id",
    "effect_for",
    "effective_clusters",
    "encode_universe_study",
    "fetch_daily_bars",
    "funnel_counts",
    "group_by_economic_asset",
    "growth_curve",
    "growth_row",
    "horizon_ceiling",
    "identity_rules_payload",
    "liquidity_of",
    "log_returns",
    "measure_dependence",
    "measurement_window",
    "network_is_fatal",
    "offline_reproduction",
    "ordered_assets",
    "ordering_is_outcome_free",
    "outcome_free_decision",
    "pearson",
    "peg_disagreements",
    "peg_like_by_volatility",
    "perturb_outcomes",
    "published_densities",
    "quality_of",
    "read_universe_artifact",
    "render_funnel",
    "render_growth",
    "render_universe_study",
    "representative_of",
    "requirement_for_effect",
    "run_universe_study",
    "screen_pair",
    "series_digest",
    "subsample_for_density",
    "summarise_density",
    "usable_measurement_years",
    "verify_artifact_digest",
    "verify_cc_preregistration",
    "warmup_prefix",
]
