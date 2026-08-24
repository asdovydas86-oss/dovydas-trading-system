"""Global Market Pulse — deterministic orientation across a tracked universe.

    fmits pulse

Answers one question, before any question about an individual asset: **what are
the markets this system tracks actually doing right now, and what can it not
tell me?**

This package is not a swing engine and does not depend on one. It imports no
trade plan, no position sizing, no paper trading, no setup, no approval and no
proposal, and a guard test asserts each of those by name. A market pulse
describes the market; it does not describe whether to trade it, and nothing here
can change a `CONFIRMED`, `CANDIDATE` or `WAIT` state anywhere else in the
repository.

**Where it sits.** Below AI interpretation and above the engines:

    provider adapter                   fmis.providers.binance
        -> canonical candles           fmis.data
        -> canonical observations      fmis.data.reduction
        -> deterministic metrics       fmis.relative_value
        -> pulse records               fmis.market_pulse.measure
        -> one immutable page          fmis.market_pulse.pulse
        -> text                        fmis.market_pulse.render

The provider terminates two layers below this package, which imports no adapter
at all: `fmis.pipeline.pulse` is the single module that binds one to the other,
the same way `fmis.pipeline.prices` is the single module that binds one to a
mark. No LLM, no prompt, no narrative and no hidden score exists anywhere here.

**What it computes: nothing.** Every number is produced by the Relative Value
Engine — `period_return`, `realized_volatility`, `pearson_correlation` — over
observation series produced by `fmis.data.reduction`. This package selects
windows, records absences, orders one measured quantity, and prints. A guard
test asserts its measurement and assembly modules contain no arithmetic
operator at all.

**Five distinct absences, kept distinct**, because a page that collapses them
is a page that teaches its reader to ignore all of them: a market with no
configured provider, a provider that failed, a window shorter than the horizon
names, a mathematically undefined result, and a comparison the units or the bars
refuse. A zero move is none of those, and it prints as `+0.00%`.

**Known limitations, stated on the page rather than in this docstring alone:**
this build can read crypto spot only; it holds no trading calendar, so horizons
are counts of closed bars and wall-clock equivalence is claimed only for
continuously traded markets; volatility is measured and deliberately not
classified; and no reading is called stale unless the owner supplies a bound.
"""

from __future__ import annotations

from fmis.market_pulse.measure import (
    CO_MOVEMENT_METRIC,
    MOVE_METRIC,
    RATE_LIKE_MEASURE_REASON,
    VOLATILITY_METRIC,
    NoObservationsError,
    measure_co_movement,
    measure_from_observations,
    measure_market,
    measure_move,
    measure_volatility,
    observations_for,
)
from fmis.market_pulse.models import (
    CO_MOVEMENT_CAVEAT,
    PULSE_ORIENTATION_NOTE,
    SCHEDULE_LIMITATION,
    VOLATILITY_CLASSIFICATION_NOTE,
    Benchmark,
    CoMovement,
    Horizon,
    HorizonMove,
    HorizonRanking,
    FreshnessPolicy,
    FreshnessState,
    MarketCategory,
    MarketPulse,
    MarketPulseError,
    MarketReading,
    MarketUnavailable,
    MarketUniverse,
    ProviderInstrument,
    PulseUniverseError,
    QuantityKind,
    RankedMove,
    TradingSchedule,
    VolatilityReading,
)
from fmis.market_pulse.pulse import (
    EXCLUDED_FROM_ORDERING,
    MINIMUM_ORDERED_MARKETS,
    NOT_READ_REASON,
    ORDERING_QUANTITY,
    ORDERING_UNIT_SCOPE,
    RATE_LIKE_EXCLUSION,
    build_market_pulse,
    co_movements_against,
    rank_by_horizon,
)
from fmis.market_pulse.render import (
    NO_STALENESS_BOUND,
    PULSE_PAGE_WIDTH,
    render_market_pulse,
)
from fmis.market_pulse.universe import (
    CO_MOVEMENT_HORIZON,
    CRYPTO_FRESHNESS,
    DEFAULT_HORIZONS,
    DEFAULT_PULSE_UNIVERSE,
    FRED_DAILY_FRESHNESS,
    FRED_LAGGED_WEEKLY_FRESHNESS,
    HORIZON_168_BARS,
    HORIZON_21_OBSERVATIONS,
    HORIZON_24_BARS,
    HORIZON_5_OBSERVATIONS,
    HORIZON_LATEST_BAR,
    HORIZON_LATEST_OBSERVATION,
    MACRO_BENCHMARK_IDS,
    MACRO_CATEGORIES,
    MACRO_CO_MOVEMENT_HORIZON,
    MACRO_HORIZONS,
    MACRO_INTERVAL,
    MACRO_PROVIDER,
    MACRO_VOLATILITY_HORIZON,
    NO_CRYPTO_ADAPTER_FOR,
    NO_LICENSED_SOURCE_FOR,
    PULSE_CANDLE_LIMIT,
    PULSE_INTERVAL,
    PULSE_PROVIDER,
    VOLATILITY_HORIZON,
    horizons_for,
    universe_subset,
)

__all__ = [
    # errors
    "MarketPulseError",
    "PulseUniverseError",
    "NoObservationsError",
    # vocabulary
    "MarketCategory",
    "TradingSchedule",
    "QuantityKind",
    "FreshnessState",
    "FreshnessPolicy",
    # universe
    "ProviderInstrument",
    "Benchmark",
    "MarketUniverse",
    "DEFAULT_PULSE_UNIVERSE",
    "NO_CRYPTO_ADAPTER_FOR",
    "NO_LICENSED_SOURCE_FOR",
    "PULSE_PROVIDER",
    "PULSE_INTERVAL",
    "PULSE_CANDLE_LIMIT",
    "MACRO_PROVIDER",
    "MACRO_INTERVAL",
    "MACRO_CATEGORIES",
    "MACRO_BENCHMARK_IDS",
    "CRYPTO_FRESHNESS",
    "FRED_DAILY_FRESHNESS",
    "FRED_LAGGED_WEEKLY_FRESHNESS",
    "universe_subset",
    # horizons
    "Horizon",
    "HORIZON_LATEST_BAR",
    "HORIZON_24_BARS",
    "HORIZON_168_BARS",
    "DEFAULT_HORIZONS",
    "VOLATILITY_HORIZON",
    "CO_MOVEMENT_HORIZON",
    "HORIZON_LATEST_OBSERVATION",
    "HORIZON_5_OBSERVATIONS",
    "HORIZON_21_OBSERVATIONS",
    "MACRO_HORIZONS",
    "MACRO_VOLATILITY_HORIZON",
    "MACRO_CO_MOVEMENT_HORIZON",
    "horizons_for",
    # readings
    "HorizonMove",
    "VolatilityReading",
    "MarketReading",
    "MarketUnavailable",
    "CoMovement",
    # measurement
    "MOVE_METRIC",
    "RATE_LIKE_MEASURE_REASON",
    "VOLATILITY_METRIC",
    "CO_MOVEMENT_METRIC",
    "observations_for",
    "measure_move",
    "measure_volatility",
    "measure_from_observations",
    "measure_market",
    "measure_co_movement",
    # ordering and assembly
    "RankedMove",
    "HorizonRanking",
    "MarketPulse",
    "ORDERING_QUANTITY",
    "ORDERING_UNIT_SCOPE",
    "EXCLUDED_FROM_ORDERING",
    "NOT_READ_REASON",
    "RATE_LIKE_EXCLUSION",
    "MINIMUM_ORDERED_MARKETS",
    "rank_by_horizon",
    "co_movements_against",
    "build_market_pulse",
    # rendering
    "PULSE_PAGE_WIDTH",
    "NO_STALENESS_BOUND",
    "render_market_pulse",
    # standing notes
    "PULSE_ORIENTATION_NOTE",
    "SCHEDULE_LIMITATION",
    "VOLATILITY_CLASSIFICATION_NOTE",
    "CO_MOVEMENT_CAVEAT",
]
