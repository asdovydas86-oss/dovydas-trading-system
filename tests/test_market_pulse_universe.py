"""Milestone BT — the configured universe, and what it promises about extension.

The registry's claim is that **a symbol appears in exactly one place**. The
load-bearing test here is `test_a_market_can_be_added_without_touching_a_renderer`:
it adds a benchmark and re-renders with no other edit, which is what makes the
next provider milestone an addition rather than a rewrite.
"""

from __future__ import annotations

import pathlib

import pytest

import fmis
from fmis.market_pulse import (
    CO_MOVEMENT_HORIZON,
    DEFAULT_HORIZONS,
    DEFAULT_PULSE_UNIVERSE,
    HORIZON_168_BARS,
    HORIZON_24_BARS,
    HORIZON_LATEST_BAR,
    MarketCategory,
    MarketUniverse,
    PULSE_CANDLE_LIMIT,
    PULSE_INTERVAL,
    PULSE_PROVIDER,
    PulseUniverseError,
    TradingSchedule,
    VOLATILITY_HORIZON,
    universe_subset,
)
from tests.market_pulse_helpers import crypto_benchmark, dark_benchmark, universe_of


# --------------------------------------------------------------------------
# The default universe is honest about what it cannot see
# --------------------------------------------------------------------------


def test_the_default_universe_carries_markets_it_cannot_read() -> None:
    """*A page that listed only what it can fetch would answer "what is
    happening across the markets" with a silence the reader could not see.*

    Milestone BU lit five of BT's five dark markets and left two dark, for two
    different reasons neither of which is an oversight. The dark set is asserted
    exactly, so lighting one or losing one is a deliberate edit here.
    """
    assert DEFAULT_PULSE_UNIVERSE.unsupported, "the dark markets are the point"
    dark = {entry.benchmark_id for entry in DEFAULT_PULSE_UNIVERSE.unsupported}
    assert dark == {"DXY", "XAU"}


def test_every_unsupported_market_states_why_and_names_what_it_needs() -> None:
    """Each dark market names the *specific* obstacle, not a generic absence.

    Both remaining dark markets are dark for want of a licence rather than for
    want of an adapter, and the sentence says so — telling the owner to write
    code for a market no code can reach would be worse than saying nothing.
    """
    for benchmark in DEFAULT_PULSE_UNIVERSE.unsupported:
        reason = benchmark.unsupported_reason
        assert "no source configured in this build publishes" in reason
        assert "rather than substituted" in reason, benchmark.benchmark_id


def test_the_dollar_index_is_never_substituted_by_the_broad_index() -> None:
    """The single most plausible-looking lie this page could tell, refused.

    ICE's DXY and the Federal Reserve's nominal broad index are different
    measures over different baskets with different weighting rules. The broad
    index is carried under its own id and its own name; DXY stays dark and says
    why. A page printing one under the other's name would be wrong in a way no
    downstream check could catch.
    """
    dxy = DEFAULT_PULSE_UNIVERSE.benchmark_for("DXY")
    broad = DEFAULT_PULSE_UNIVERSE.benchmark_for("USDBROAD")
    assert dxy is not None and broad is not None
    assert not dxy.is_supported
    assert broad.is_supported
    assert broad.instrument.symbol == "DTWEXBGS"
    assert "DXY" in dxy.display_name
    assert "DXY" not in broad.display_name
    assert "broad" in broad.display_name.lower()
    assert dxy.display_name != broad.display_name
    assert dxy.quote_unit != broad.quote_unit


def test_every_supported_market_sits_on_a_provider_this_build_has() -> None:
    """The build's actual reach, asserted so the report cannot overstate it.

    Two providers now, and each market's schedule, cadence and quantity kind
    follow from which one serves it: continuously traded hourly crypto, or
    session-bound daily macro.
    """
    from fmis.market_pulse import MACRO_INTERVAL, MACRO_PROVIDER, QuantityKind

    for benchmark in DEFAULT_PULSE_UNIVERSE.supported:
        provider = benchmark.instrument.provider
        assert provider in {PULSE_PROVIDER, MACRO_PROVIDER}
        if provider == PULSE_PROVIDER:
            assert benchmark.category is MarketCategory.CRYPTO
            assert benchmark.schedule is TradingSchedule.CONTINUOUS
            assert benchmark.instrument.interval == PULSE_INTERVAL
            assert benchmark.quote_unit == "USDT"
            assert benchmark.quantity_kind is QuantityKind.PRICE_LIKE
        else:
            assert benchmark.category is not MarketCategory.CRYPTO
            assert benchmark.schedule is TradingSchedule.SESSION_BOUND
            assert benchmark.instrument.interval == MACRO_INTERVAL
        # Every readable market states how often its source publishes.
        assert benchmark.freshness_policy is not None


def test_every_category_except_commodities_now_has_a_live_member() -> None:
    """What Milestone BU actually changed, stated as a fact about the registry.

    Five of BT's six categories now read. Commodities do not, because the only
    commodity in the universe is spot gold and no configured source publishes
    it — so the category is dark and the page says so, which is exactly the
    honest statement this surface exists to make.
    """
    live = {entry.category for entry in DEFAULT_PULSE_UNIVERSE.supported}
    assert live == {
        MarketCategory.CRYPTO,
        MarketCategory.EQUITY_INDEX,
        MarketCategory.CURRENCY,
        MarketCategory.RATES,
        MarketCategory.VOLATILITY_INDEX,
    }
    assert MarketCategory.COMMODITY not in live
    dark = {entry.category for entry in DEFAULT_PULSE_UNIVERSE.unsupported}
    assert dark == {MarketCategory.CURRENCY, MarketCategory.COMMODITY}


def test_the_provider_label_matches_the_repository_s_one_spelling() -> None:
    """*A fact sheet, a mark and a pulse reading from the same endpoint cannot
    claim three different sources.*"""
    from fmis.pipeline.structural_facts import BINANCE_SPOT
    from fmis.pipeline.prices import MARK_SOURCE

    assert PULSE_PROVIDER == BINANCE_SPOT == MARK_SOURCE


def test_the_candle_limit_covers_the_longest_horizon() -> None:
    """A budget short of the longest window would make one horizon permanently
    unavailable and the failure would look like a market with no history."""
    longest = max(horizon.required_observations for horizon in DEFAULT_HORIZONS)
    assert PULSE_CANDLE_LIMIT > longest


def test_the_candle_limit_stays_inside_the_adapter_s_maximum() -> None:
    from fmis.providers.binance import MAX_LIMIT

    assert PULSE_CANDLE_LIMIT <= MAX_LIMIT


def test_the_interval_is_one_the_adapter_accepts() -> None:
    from fmis.providers.binance import KLINE_INTERVALS

    assert PULSE_INTERVAL in KLINE_INTERVALS


# --------------------------------------------------------------------------
# Horizons
# --------------------------------------------------------------------------


def test_horizons_are_ordered_shortest_to_longest() -> None:
    """*A reader scanning a row reads outward from now.*"""
    bars = [horizon.bars for horizon in DEFAULT_HORIZONS]
    assert bars == sorted(bars)
    assert bars == [1, 24, 168]


def test_every_horizon_id_is_distinct() -> None:
    ids = [horizon.horizon_id for horizon in DEFAULT_HORIZONS]
    assert len(set(ids)) == len(ids)


def test_volatility_and_co_movement_share_one_window() -> None:
    """*Two figures describing one week are comparable; two figures describing
    two different weeks are a trap.*"""
    assert VOLATILITY_HORIZON is CO_MOVEMENT_HORIZON is HORIZON_168_BARS


def test_a_horizon_id_never_names_a_duration_it_does_not_guarantee() -> None:
    """The bar-count identity is the primitive; the wall-clock sentence is a
    separate field that only a continuous market may print."""
    assert HORIZON_24_BARS.horizon_id == "24_bars"
    assert HORIZON_24_BARS.wall_clock_equivalent == "24 hours"
    assert HORIZON_LATEST_BAR.bars == 1


# --------------------------------------------------------------------------
# Subsetting
# --------------------------------------------------------------------------


def test_a_subset_preserves_the_caller_s_order_not_the_registry_s() -> None:
    """*`fmits pulse ETH BTC` is a request to read those two in that sequence.*"""
    chosen = universe_subset(DEFAULT_PULSE_UNIVERSE, ("ETH", "BTC"), name="s")
    assert [entry.benchmark_id for entry in chosen.benchmarks] == ["ETH", "BTC"]


def test_a_subset_may_name_an_unsupported_market() -> None:
    chosen = universe_subset(DEFAULT_PULSE_UNIVERSE, ("DXY",), name="s")
    assert chosen.supported == () and len(chosen.unsupported) == 1


def test_an_unknown_market_is_refused_rather_than_dropped() -> None:
    """*Dropping an unknown id would produce a page quietly narrower than the
    request.*"""
    with pytest.raises(PulseUniverseError, match="not a market in universe"):
        universe_subset(DEFAULT_PULSE_UNIVERSE, ("BTC", "NOPE"), name="s")


def test_a_market_named_twice_is_refused_rather_than_collapsed() -> None:
    with pytest.raises(PulseUniverseError, match="named twice"):
        universe_subset(DEFAULT_PULSE_UNIVERSE, ("BTC", "BTC"), name="s")


def test_an_empty_subset_is_refused() -> None:
    with pytest.raises(PulseUniverseError, match="not a universe"):
        universe_subset(DEFAULT_PULSE_UNIVERSE, (), name="s")


def test_a_subset_of_a_non_universe_is_a_type_error() -> None:
    with pytest.raises(TypeError, match="must be a MarketUniverse"):
        universe_subset(object(), ("BTC",), name="s")


# --------------------------------------------------------------------------
# Extension without touching a renderer — the registry's whole promise
# --------------------------------------------------------------------------


def test_a_market_can_be_added_without_touching_a_renderer() -> None:
    """The next provider milestone must be an addition, not a rewrite.

    A benchmark in a category with no live member, on a schedule that is not
    continuous, in a quote unit nothing else uses — the hardest shape to add —
    is added and the page renders with **no other edit anywhere**.
    """
    from datetime import timedelta

    from fmis.market_pulse import build_market_pulse, render_market_pulse
    from tests.market_pulse_helpers import instant

    extended = MarketUniverse(
        name="extended",
        benchmarks=(
            *DEFAULT_PULSE_UNIVERSE.unsupported,
            dark_benchmark(
                "NIKKEI",
                display_name="Nikkei 225",
                category=MarketCategory.EQUITY_INDEX,
                quote_unit="JPY",
                schedule=TradingSchedule.UNKNOWN,
            ),
        ),
    )
    page = build_market_pulse(
        as_of=instant(10),
        universe=extended,
        readings=(),
        unavailable=(),
        horizons=DEFAULT_HORIZONS,
    )
    text = render_market_pulse(page, max_age=timedelta(hours=2))
    assert "Nikkei 225" in text
    assert "NIKKEI" in text
    assert "3 market(s) with no" in text  # the scope line wraps


def test_no_module_outside_the_registry_names_a_tracked_provider_symbol() -> None:
    """*No renderer, no composition root and no CLI module names a market this
    page shows.* The registry is the single place, and this proves it.

    **Parsed rather than grepped**, for the reason `test_directional_vocabulary
    _boundary.py` records for its own scan: every module here is entitled to
    *discuss* a symbol in prose — `ProviderInstrument`'s docstring uses one to
    explain that symbols are never normalized — and a raw-text scan would flag
    the explanation as the violation. Only a real string **value** or identifier
    counts, which is exactly the case that would put a symbol in two places.
    """
    import ast

    symbols = {
        entry.instrument.symbol for entry in DEFAULT_PULSE_UNIVERSE.supported
    }
    root = pathlib.Path(fmis.__file__).parent
    registry = root / "market_pulse" / "universe.py"
    candidates = [
        path
        for path in sorted((root / "market_pulse").rglob("*.py"))
        if path != registry
    ] + [root / "pipeline" / "pulse.py", root / "pipeline" / "cli.py"]
    offenders: dict[str, set[str]] = {}
    for path in candidates:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(
                node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)
            )
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        found = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in symbols
            and id(node) not in docstrings
        }
        if found:
            offenders[path.name] = found
    assert offenders == {}


def test_a_benchmark_id_is_never_a_provider_symbol() -> None:
    """The CLI takes ids, not symbols. If the two coincided, a user typing a
    symbol would appear to work until the day one of them changed."""
    for benchmark in DEFAULT_PULSE_UNIVERSE.supported:
        assert benchmark.benchmark_id != benchmark.instrument.symbol


def test_the_universe_is_a_module_level_constant_and_is_immutable() -> None:
    """A page's stated scope cannot be edited at runtime by a caller."""
    with pytest.raises((AttributeError, TypeError)):
        DEFAULT_PULSE_UNIVERSE.benchmarks = ()  # type: ignore[misc]
    assert isinstance(DEFAULT_PULSE_UNIVERSE.benchmarks, tuple)


def test_a_universe_holding_only_dark_markets_is_legal() -> None:
    """Nothing requires a live market: a universe of five unreadable markets is
    a valid, and completely honest, statement of scope."""
    only_dark = universe_of(dark_benchmark("A"), dark_benchmark("B"))
    assert only_dark.supported == ()
    assert len(only_dark.unsupported) == 2


def test_a_universe_of_one_live_market_is_legal() -> None:
    assert len(universe_of(crypto_benchmark()).supported) == 1
