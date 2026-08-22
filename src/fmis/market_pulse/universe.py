"""The tracked market universe and the horizons it is measured over.

**This is configuration, and it is the only place a symbol appears.** No
renderer, no composition root and no CLI module in this repository names a
market this page shows; they all read this registry. That is what makes adding
a market a one-line edit rather than a search, and it is what
`test_market_pulse_universe.py` asserts by adding one and re-rendering with no
other change.

**Five of the eleven default markets are unsupported, and that is the design.**
The owner asked to be able to see equities, the dollar, gold, yields and
volatility. This build can obtain none of them: the only market data adapter in
the repository is `fmis.providers.binance`, which serves public crypto spot
klines. The honest response is to carry those markets in the universe with the
sentence saying why they are dark — a page that listed only what it can fetch
would answer *"what is happening across the markets"* with a crypto-shaped
silence about everything else, and the reader would not know the silence was
there.

Each unsupported entry names the **kind of adapter** that would light it up, so
the registry doubles as the specification for the next provider milestone.

**Horizons are counts of closed bars, never durations.** See `Horizon` for why
that is the correct primitive for a repository with no trading calendar. The
wall-clock sentence attached to each is what a continuously traded market may
additionally print; `SCHEDULE_LIMITATION` states that no other market may.
"""

from __future__ import annotations

from datetime import timedelta

from fmis.market_pulse.models import (
    Benchmark,
    Horizon,
    MarketCategory,
    MarketUniverse,
    ProviderInstrument,
    PulseUniverseError,
    TradingSchedule,
)

__all__ = [
    "PULSE_PROVIDER",
    "PULSE_INTERVAL",
    "PULSE_CANDLE_LIMIT",
    "HORIZON_LATEST_BAR",
    "HORIZON_24_BARS",
    "HORIZON_168_BARS",
    "DEFAULT_HORIZONS",
    "VOLATILITY_HORIZON",
    "CO_MOVEMENT_HORIZON",
    "NO_CRYPTO_ADAPTER_FOR",
    "DEFAULT_PULSE_UNIVERSE",
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

#: The sentence every unsupported market carries, completed with the kind of
#: adapter it needs. Written once so eleven markets cannot acquire eleven
#: slightly different explanations of one architectural fact.
NO_CRYPTO_ADAPTER_FOR = (
    "no provider is configured for this market in this build; the only market "
    "data adapter that exists here serves public crypto spot candles, and {} "
    "is not reachable through it"
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
    )


def _dark(
    benchmark_id: str,
    display_name: str,
    category: MarketCategory,
    schedule: TradingSchedule,
    quote_unit: str,
    needs: str,
) -> Benchmark:
    """One market the owner wants and this build cannot obtain."""
    return Benchmark(
        benchmark_id=benchmark_id,
        display_name=display_name,
        category=category,
        schedule=schedule,
        quote_unit=quote_unit,
        unsupported_reason=NO_CRYPTO_ADAPTER_FOR.format(needs),
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
        _dark(
            "SPX",
            "S&P 500",
            MarketCategory.EQUITY_INDEX,
            TradingSchedule.SESSION_BOUND,
            "index points",
            "a US equity index",
        ),
        _dark(
            "DXY",
            "US Dollar Index",
            MarketCategory.CURRENCY,
            TradingSchedule.SESSION_BOUND,
            "index points",
            "a currency index",
        ),
        _dark(
            "XAU",
            "Gold (spot)",
            MarketCategory.COMMODITY,
            TradingSchedule.SESSION_BOUND,
            "USD",
            "spot gold",
        ),
        _dark(
            "US10Y",
            "US 10-year Treasury yield",
            MarketCategory.RATES,
            TradingSchedule.SESSION_BOUND,
            "percent",
            "a government bond yield",
        ),
        _dark(
            "VIX",
            "CBOE Volatility Index",
            MarketCategory.VOLATILITY_INDEX,
            TradingSchedule.SESSION_BOUND,
            "index points",
            "an options-derived volatility index",
        ),
    ),
)


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
