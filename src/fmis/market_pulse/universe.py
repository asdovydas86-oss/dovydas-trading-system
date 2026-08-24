"""The tracked market universe and the horizons it is measured over.

**This is configuration, and it is the only place a symbol appears.** No
renderer, no composition root and no CLI module in this repository names a
market this page shows; they all read this registry. That is what makes adding
a market a one-line edit rather than a search, and it is what
`test_market_pulse_universe.py` asserts by adding one and re-rendering with no
other change.

**Eleven live markets and two dark ones, and both numbers are the design.**
Milestone BT carried five dark markets because the only adapter in the
repository served crypto spot klines. Milestone BU added a second adapter over
public FRED series downloads and lit five of them: a US equity index, a dollar
index, two Treasury yields and a volatility index.

**Two markets stay dark, and each names why.** They are not oversights and not
work left undone:

  * `DXY` — the ICE US Dollar Index is a licensed index. This build reads the
    Federal Reserve's nominal broad dollar index instead, and carries it under
    its own name as `USDBROAD` rather than printing it under DXY's. The two are
    genuinely different measures, and substituting one for the other would be
    the single most plausible-looking lie this page could tell.
  * `XAU` — the LBMA gold benchmark series the macro source used to publish were
    discontinued and now return not-found. No configured source publishes spot
    gold.

A page that listed only what it can fetch would answer *"what is happening
across the markets"* with a silence the reader could not see. Each dark entry
therefore names **why** it is dark, so the registry doubles as the specification
for the next provider milestone.

**Horizons are counts of closed bars, never durations.** See `Horizon` for why
that is the correct primitive for a repository with no trading calendar. The
wall-clock sentence attached to each is what a continuously traded market may
additionally print; `SCHEDULE_LIMITATION` states that no other market may.
"""

from __future__ import annotations

from datetime import timedelta
from types import MappingProxyType

from fmis.market_pulse.models import (
    Benchmark,
    FreshnessPolicy,
    Horizon,
    MarketCategory,
    MarketUniverse,
    ProviderInstrument,
    PulseUniverseError,
    QuantityKind,
    TradingSchedule,
)

__all__ = [
    "PULSE_PROVIDER",
    "PULSE_INTERVAL",
    "PULSE_CANDLE_LIMIT",
    "MACRO_PROVIDER",
    "MACRO_INTERVAL",
    "CRYPTO_FRESHNESS",
    "FRED_DAILY_FRESHNESS",
    "FRED_LAGGED_WEEKLY_FRESHNESS",
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
    "NO_CRYPTO_ADAPTER_FOR",
    "NO_LICENSED_SOURCE_FOR",
    "DEFAULT_PULSE_UNIVERSE",
    "MACRO_CATEGORIES",
    "MACRO_BENCHMARK_IDS",
    "horizons_for",
    "universe_subset",
]

#: The one provider this build can read a market from. Spelled to match the
#: label the fact-sheet composition root already carries, so a fact sheet, a
#: mark and a pulse reading taken from the same endpoint cannot claim three
#: different sources — asserted by a test rather than left to care.
#:
#: That module is named in prose rather than by path, for the reason
#: `fmis.pipeline.prices` records for the identical situation: this
#: repository's guard tests scan raw text for an import, and a mention would
#: weaken one. A guard that has to be widened for a docstring is a guard that
#: gets widened for a real violation next.
PULSE_PROVIDER = "binance-spot"

#: The bar size every default reading is measured on. An hour: fine enough that
#: the latest-bar move is a recent fact rather than yesterday's, coarse enough
#: that a week of history fits in one provider page. A stated policy that
#: travels on every reading it produces, never a number buried at a call site.
PULSE_INTERVAL = "1h"

#: Candles requested per market. The longest horizon needs 169 closed bars; the
#: margin absorbs the forming bar and any bar the provider omits, and stays far
#: inside the adapter's own 1000-row maximum. A window shorter than a horizon
#: needs is reported as insufficient rather than measured over what arrived.
PULSE_CANDLE_LIMIT = 200

#: The most recent completed bar's move: this close against the one before it.
HORIZON_LATEST_BAR = Horizon(
    horizon_id="latest_bar",
    bars=1,
    description="the most recent completed bar",
    wall_clock_equivalent="1 hour",
    wall_clock_span=timedelta(hours=1),
)

#: Twenty-four bars. On a continuously traded market that is one day exactly;
#: on any other it is twenty-four bars and nothing more is claimed.
HORIZON_24_BARS = Horizon(
    horizon_id="24_bars",
    bars=24,
    description="the last 24 completed bars",
    wall_clock_equivalent="24 hours",
    wall_clock_span=timedelta(hours=24),
)

#: The second provider this build can read a market from, added by Milestone BU.
#: Public FRED series downloads — no API key, no credential, no private endpoint.
#: Named in prose rather than by module path for the reason `PULSE_PROVIDER`
#: records: this repository's guard tests scan raw text for an import.
MACRO_PROVIDER = "fred"

#: The observation cadence every FRED series this build reads is published at.
#: A **daily** figure is one observation per business day — not one per calendar
#: day, and emphatically not one per hour. It travels on every reading it
#: produces so a daily figure and an hourly one can never be silently compared.
MACRO_INTERVAL = "1d"

#: The publication schedule of an hourly crypto spot series. A venue that trades
#: continuously publishes a closed hourly bar every hour; the tolerance covers
#: the bar that is still forming plus ordinary request latency.
#:
#: **Derived from the venue's cadence, not chosen as a preference.** That is the
#: whole distinction between this and the invented threshold
#: `fmis.market_pulse.render` declines to pick for the owner: this says *"the
#: source should have published by now"*, not *"this number is too old for you"*.
CRYPTO_FRESHNESS = FreshnessPolicy(
    publication_period=timedelta(hours=1),
    tolerance=timedelta(hours=2),
    basis=(
        "a continuously traded venue closes an hourly bar every hour; the "
        "tolerance covers the bar still forming and ordinary request latency"
    ),
)

#: The publication schedule of a FRED daily business-day series — the equity
#: index, the volatility index and the Treasury yields.
#:
#: **The tolerance is where this build's missing trading calendar is paid for,
#: out loud.** A business-day series read on a Sunday is legitimately three days
#: old, and a Monday holiday makes it four; FRED then adds its own overnight
#: publication lag on top. Four days of tolerance covers a long weekend plus that
#: lag. Without it, every Sunday would report four markets behind schedule and
#: the owner would correctly learn to ignore the whole section.
FRED_DAILY_FRESHNESS = FreshnessPolicy(
    publication_period=timedelta(days=1),
    tolerance=timedelta(days=4),
    basis=(
        "a business-day series published by FRED with an overnight lag; the "
        "tolerance covers a weekend, a public holiday this build holds no "
        "calendar for, and that lag"
    ),
)

#: The publication schedule of the Fed's trade-weighted dollar index, which is
#: computed daily but released on a materially longer delay than the market
#: series above — around a week in observed practice. Judging it by the daily
#: policy would report it behind schedule almost permanently, which is the exact
#: failure a single universal threshold produces.
FRED_LAGGED_WEEKLY_FRESHNESS = FreshnessPolicy(
    publication_period=timedelta(days=1),
    tolerance=timedelta(days=13),
    basis=(
        "a daily series the Federal Reserve releases on a materially longer "
        "delay than a market print — around a week observed; the tolerance "
        "covers that release delay plus a weekend"
    ),
)

#: A hundred and sixty-eight bars — one week on a continuous market. The longest
#: window this build measures, and the one volatility and co-movement use.
HORIZON_168_BARS = Horizon(
    horizon_id="168_bars",
    bars=168,
    description="the last 168 completed bars",
    wall_clock_equivalent="7 days",
    wall_clock_span=timedelta(days=7),
)

#: Measured for every market, in this order, on every page. Ordered shortest to
#: longest so a reader scanning a row reads outward from now.
DEFAULT_HORIZONS: tuple[Horizon, ...] = (
    HORIZON_LATEST_BAR,
    HORIZON_24_BARS,
    HORIZON_168_BARS,
)

#: The window realized volatility is measured over. The longest horizon, because
#: a standard deviation over twenty-four observations is a number about a day
#: rather than about a market.
VOLATILITY_HORIZON = HORIZON_168_BARS

#: The window co-movement is measured over. The same window as volatility, on
#: purpose: two figures describing one week are comparable with each other, and
#: two figures describing two different weeks are a trap.
CO_MOVEMENT_HORIZON = HORIZON_168_BARS


# ------------------------------------------------------- macro horizons (BU) ---
#
# **Macro gets its own horizons, and that is the milestone's central honesty
# decision.** The horizons above are measured on hourly bars: 168 of them is one
# week. A daily macro series measured over 168 observations is *eight months*.
# Reusing one horizon id across both would put two windows differing by a factor
# of twenty-four under one label, and a reader comparing "168 bars" of BTC with
# "168 bars" of the S&P would be comparing a week with two-thirds of a year.
#
# So the ids are distinct, the counts suit a daily cadence, and none of them
# claims a wall-clock equivalent — every market measured on them is
# `SESSION_BOUND`, where a bar count is not a duration. `fmis.macro.comparability`
# is what refuses to place the two families side by side.

#: The most recent completed observation's move: this print against the one
#: before it. One business day on a daily series, and the page says exactly that
#: rather than "one day", because a Tuesday print follows a Monday print except
#: when it follows a Friday one.
HORIZON_LATEST_OBSERVATION = Horizon(
    horizon_id="latest_observation",
    bars=1,
    description="the most recent completed observation",
)

#: Five observations — one business week on a daily series, and deliberately not
#: called "one week": five business days span seven calendar days normally and
#: nine over a holiday weekend.
HORIZON_5_OBSERVATIONS = Horizon(
    horizon_id="5_observations",
    bars=5,
    description="the last 5 completed observations",
)

#: Twenty-one observations — roughly one calendar month of business days. The
#: longest macro window this build measures, and the one macro volatility and
#: macro co-movement use.
HORIZON_21_OBSERVATIONS = Horizon(
    horizon_id="21_observations",
    bars=21,
    description="the last 21 completed observations",
)

#: Measured for every macro market, shortest to longest.
MACRO_HORIZONS: tuple[Horizon, ...] = (
    HORIZON_LATEST_OBSERVATION,
    HORIZON_5_OBSERVATIONS,
    HORIZON_21_OBSERVATIONS,
)

#: The window macro realized volatility is measured over.
MACRO_VOLATILITY_HORIZON = HORIZON_21_OBSERVATIONS

#: The window macro co-movement is measured over. The same window as macro
#: volatility, for the reason `CO_MOVEMENT_HORIZON` records.
MACRO_CO_MOVEMENT_HORIZON = HORIZON_21_OBSERVATIONS

#: The sentence a market carries when no adapter in this build can reach the
#: *kind* of market it is. Retained from Milestone BT and currently unused by the
#: default universe: BU wrote the adapter that lit every market this template
#: described. Kept because it is the correct wording for the next market whose
#: problem is a missing adapter rather than a missing licence — the distinction
#: `NO_LICENSED_SOURCE_FOR` exists to preserve.
NO_CRYPTO_ADAPTER_FOR = (
    "no provider is configured for this market in this build; the only market "
    "data adapter that exists here serves public crypto spot candles, and {} "
    "is not reachable through it"
)


#: The sentence a market carries when a real, published benchmark exists and no
#: source this build can lawfully and freely reach publishes it. Distinct from
#: `NO_CRYPTO_ADAPTER_FOR`, because the two are different problems with different
#: fixes: one needs an adapter written, the other needs a data licence bought.
NO_LICENSED_SOURCE_FOR = (
    "no source configured in this build publishes {}; {} — so this market is "
    "reported as unavailable rather than substituted with a different series "
    "wearing its name"
)


def _crypto(benchmark_id: str, display_name: str, symbol: str) -> Benchmark:
    """One continuously traded crypto spot pair on the configured provider."""
    return Benchmark(
        benchmark_id=benchmark_id,
        display_name=display_name,
        category=MarketCategory.CRYPTO,
        schedule=TradingSchedule.CONTINUOUS,
        quote_unit="USDT",
        instrument=ProviderInstrument(
            provider=PULSE_PROVIDER, symbol=symbol, interval=PULSE_INTERVAL
        ),
        quantity_kind=QuantityKind.PRICE_LIKE,
        freshness_policy=CRYPTO_FRESHNESS,
    )


def _macro(
    benchmark_id: str,
    display_name: str,
    series_id: str,
    category: MarketCategory,
    quote_unit: str,
    *,
    quantity_kind: QuantityKind = QuantityKind.PRICE_LIKE,
    freshness: FreshnessPolicy = FRED_DAILY_FRESHNESS,
) -> Benchmark:
    """One daily macro series published by FRED.

    Every one is `SESSION_BOUND`: these markets close, and this build holds no
    calendar that says when. No wall-clock equivalence is claimed for any window
    measured on them.
    """
    return Benchmark(
        benchmark_id=benchmark_id,
        display_name=display_name,
        category=category,
        schedule=TradingSchedule.SESSION_BOUND,
        quote_unit=quote_unit,
        instrument=ProviderInstrument(
            provider=MACRO_PROVIDER, symbol=series_id, interval=MACRO_INTERVAL
        ),
        quantity_kind=quantity_kind,
        freshness_policy=freshness,
    )


def _dark(
    benchmark_id: str,
    display_name: str,
    category: MarketCategory,
    schedule: TradingSchedule,
    quote_unit: str,
    reason: str,
) -> Benchmark:
    """One market the owner wants and this build cannot obtain.

    The reason is passed complete rather than assembled from a fragment. Before
    Milestone BU every dark market was dark for one reason — no adapter — and a
    single template with a blank was right. Two reasons now exist and they are
    not interchangeable: a missing adapter is engineering work, and a missing
    licence is not. A template that flattened them would tell the owner to go
    write code for a market no code can reach.
    """
    return Benchmark(
        benchmark_id=benchmark_id,
        display_name=display_name,
        category=category,
        schedule=schedule,
        quote_unit=quote_unit,
        unsupported_reason=reason,
    )


#: The default tracked universe: six live crypto markets and five the owner
#: asked for that this build cannot read.
#:
#: **Six live markets, not twenty.** `fmis.swing_setup.SCAN_UNIVERSE` already
#: holds twenty symbols and is the right size for a scan, which is a search.
#: This is orientation, which is a glance: a page a reader has to work through
#: is a page they will stop opening. The six are the largest and most-referenced
#: crypto markets, and BTC leads because it is the reference every co-movement
#: below is measured against.
#:
#: **Five dark markets, each naming what it needs.** They are not placeholders
#: and not aspirations; they are the page's own statement of what it cannot see.
DEFAULT_PULSE_UNIVERSE = MarketUniverse(
    name="default",
    benchmarks=(
        _crypto("BTC", "Bitcoin (BTC/USDT)", "BTCUSDT"),
        _crypto("ETH", "Ethereum (ETH/USDT)", "ETHUSDT"),
        _crypto("SOL", "Solana (SOL/USDT)", "SOLUSDT"),
        _crypto("BNB", "BNB (BNB/USDT)", "BNBUSDT"),
        _crypto("XRP", "XRP (XRP/USDT)", "XRPUSDT"),
        _crypto("DOGE", "Dogecoin (DOGE/USDT)", "DOGEUSDT"),
        _macro(
            "SPX",
            "S&P 500",
            "SP500",
            MarketCategory.EQUITY_INDEX,
            "index points",
        ),
        _macro(
            "USDBROAD",
            "US Dollar Index (Fed nominal broad)",
            "DTWEXBGS",
            MarketCategory.CURRENCY,
            "index points (Jan 2006 = 100)",
            freshness=FRED_LAGGED_WEEKLY_FRESHNESS,
        ),
        _macro(
            "US2Y",
            "US 2-year Treasury yield",
            "DGS2",
            MarketCategory.RATES,
            "percent per annum",
            quantity_kind=QuantityKind.RATE_LIKE,
        ),
        _macro(
            "US10Y",
            "US 10-year Treasury yield",
            "DGS10",
            MarketCategory.RATES,
            "percent per annum",
            quantity_kind=QuantityKind.RATE_LIKE,
        ),
        _macro(
            "VIX",
            "CBOE Volatility Index",
            "VIXCLS",
            MarketCategory.VOLATILITY_INDEX,
            "volatility points (annualised implied %)",
        ),
        _dark(
            "DXY",
            "ICE US Dollar Index (DXY)",
            MarketCategory.CURRENCY,
            TradingSchedule.SESSION_BOUND,
            "index points",
            NO_LICENSED_SOURCE_FOR.format(
                "the ICE US Dollar Index",
                "it is a licensed index and the nominal broad dollar index this "
                "build does read (USDBROAD) is a different measure, over 26 "
                "currencies with annually revised weights rather than six with "
                "weights fixed in 1973",
            ),
        ),
        _dark(
            "XAU",
            "Gold (spot)",
            MarketCategory.COMMODITY,
            TradingSchedule.SESSION_BOUND,
            "USD per troy ounce",
            NO_LICENSED_SOURCE_FOR.format(
                "a spot gold price",
                "the LBMA gold benchmark series this build's macro source used "
                "to carry were discontinued and now return not-found, and no "
                "other configured source publishes spot gold",
            ),
        ),
    ),
)

#: The categories the macro & cross-asset surface reports on. Stated as an
#: explicit membership list rather than as *"everything that is not crypto"*: a
#: negation would silently absorb whatever category is added next, and the
#: decision about whether a new market belongs on the macro page should be made
#: when that market is added rather than inherited by default.
MACRO_CATEGORIES: tuple[MarketCategory, ...] = (
    MarketCategory.EQUITY_INDEX,
    MarketCategory.CURRENCY,
    MarketCategory.COMMODITY,
    MarketCategory.RATES,
    MarketCategory.VOLATILITY_INDEX,
)

#: The benchmarks the macro surface reports on, in the order it prints them.
#:
#: **A projection of the one registry above, never a second list of markets.**
#: `fmis.pipeline.macro` derives its universe from this, so a market added to
#: `DEFAULT_PULSE_UNIVERSE` in a macro category appears on both pages with no
#: second edit and no chance of the two disagreeing about what exists.
#:
#: **The dark markets are members.** `DXY` and `XAU` have no source, and they
#: belong on the macro page precisely because *"which of these can this system
#: not tell me about"* is one of the questions that page exists to answer.
MACRO_BENCHMARK_IDS: tuple[str, ...] = tuple(
    entry.benchmark_id
    for entry in DEFAULT_PULSE_UNIVERSE.benchmarks
    if entry.category in MACRO_CATEGORIES
)


#: Observation interval -> the horizon family measured over it, and the window
#: volatility and co-movement use on it.
#:
#: **This is the mapping that stops a page comparing a week with eight months.**
#: A horizon is a count of completed observations, so the same count means
#: wildly different spans at different cadences: 168 hourly bars is one week and
#: 168 daily observations is two-thirds of a year. Measuring every market over
#: every horizon would produce exactly that collision under one label, so each
#: cadence gets the family that suits it and a market never holds a move for the
#: other family's window at all.
#: A read-only mapping rather than a dict, so this module holds no mutable
#: state — the rule `test_market_pulse_architecture` asserts for the whole
#: package. A configuration table that could be edited at runtime would make two
#: runs of one page differ for a reason nothing on the page could disclose.
_HORIZONS_BY_INTERVAL = MappingProxyType(
    {
        PULSE_INTERVAL: (
            DEFAULT_HORIZONS,
            VOLATILITY_HORIZON,
            CO_MOVEMENT_HORIZON,
        ),
        MACRO_INTERVAL: (
            MACRO_HORIZONS,
            MACRO_VOLATILITY_HORIZON,
            MACRO_CO_MOVEMENT_HORIZON,
        ),
    }
)


def horizons_for(
    benchmark: Benchmark,
) -> tuple[tuple[Horizon, ...], Horizon, Horizon]:
    """The horizons, volatility window and co-movement window for one market.

    Chosen by the market's **observation interval**, which travels on its
    provider instrument — so a market's declared cadence and the windows it is
    measured over cannot diverge, and adding a market at a new cadence fails here
    rather than silently measuring it over the wrong family.

    Returns:
        ``(horizons, volatility_horizon, co_movement_horizon)``.

    Raises:
        ValueError: the benchmark carries no instrument, or names an interval no
            horizon family is defined for. Both are registry defects: a market
            measured over a window nobody chose for it would produce figures
            under a label that does not describe them.
    """
    if not isinstance(benchmark, Benchmark):
        raise TypeError(
            f"benchmark must be a Benchmark, got {type(benchmark).__name__}"
        )
    if benchmark.instrument is None:
        raise PulseUniverseError(
            f"{benchmark.benchmark_id} carries no provider instrument, so it has "
            "no observation interval and no horizon family; an unsupported "
            "market is reported from the registry and never measured"
        )
    interval = benchmark.instrument.interval
    family = _HORIZONS_BY_INTERVAL.get(interval)
    if family is None:
        known = ", ".join(sorted(_HORIZONS_BY_INTERVAL))
        raise PulseUniverseError(
            f"{benchmark.benchmark_id} is sampled at {interval!r} and this build "
            f"defines horizons for {known} only; a market measured over a window "
            "nobody chose for it produces figures under a label that does not "
            "describe them"
        )
    return family


def universe_subset(
    universe: MarketUniverse, benchmark_ids: tuple[str, ...], *, name: str
) -> MarketUniverse:
    """A named universe holding only the requested markets, in *their* order.

    The owner's order, not the registry's: `fmits pulse ETH BTC` is a request to
    read those two markets in that sequence, and reordering it to match the
    configuration would silently ignore what they typed.

    Raises:
        PulseUniverseError: a requested id is not in ``universe``, or is asked
            for twice. Both are refused rather than resolved — dropping an
            unknown id would produce a page quietly narrower than the request,
            and collapsing a duplicate would answer a question nobody asked.
    """
    if not isinstance(universe, MarketUniverse):
        raise TypeError(
            f"universe must be a MarketUniverse, got {type(universe).__name__}"
        )
    wanted = tuple(benchmark_ids)
    if not wanted:
        raise PulseUniverseError(
            "no market was named; a subset of nothing is not a universe"
        )
    chosen: list[Benchmark] = []
    seen: set[str] = set()
    for benchmark_id in wanted:
        if benchmark_id in seen:
            raise PulseUniverseError(
                f"{benchmark_id!r} was named twice; one market has one entry, "
                "and asking twice is a typo rather than a request for two rows"
            )
        found = universe.benchmark_for(benchmark_id)
        if found is None:
            known = ", ".join(entry.benchmark_id for entry in universe.benchmarks)
            raise PulseUniverseError(
                f"{benchmark_id!r} is not a market in universe "
                f"{universe.name!r}; it holds {known}"
            )
        seen.add(benchmark_id)
        chosen.append(found)
    return MarketUniverse(name=name, benchmarks=tuple(chosen))
