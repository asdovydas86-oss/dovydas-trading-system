"""Milestone AI — the regime composition root, its renderer and its command.

Where `test_market_regime.py` pins the engine, this pins the *boundary*: that the
application layer adapts rather than computes, that the engine never sees a fact
sheet, that the rendered page shows conflicting and unavailable evidence rather
than only what agrees, and that AF and AG still produce exactly what they did.
"""

from __future__ import annotations

import ast
import pathlib
import random
from datetime import datetime, timedelta, timezone

import pytest

from fmis.data import Candle, CandleSeries
from fmis.market_regime import (
    MarketRegime,
    ParticipationState,
    RegimeDimensionName,
    RegimePolicy,
    StructureState,
    VolatilityState,
)
from fmis.pipeline import cli as cli_module
from fmis.pipeline import render as render_module
from fmis.pipeline.multi_timeframe import TimeframeRole
from fmis.pipeline.regime import (
    FAST_ATR_PERIOD,
    REGIME_LIMITATIONS,
    SLOW_ATR_PERIOD,
    MultiTimeframeRegime,
    RegimeView,
    regime_features,
    regime_for_sheet,
    regime_input_from_sheet,
)
from fmis.pipeline.structural_facts import (
    DetectionSettings,
    build_structural_facts,
)

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "fmis"


# ============================ fixtures =======================================


def seeded_series(count: int = 260, seed: int = 5) -> CandleSeries:
    rng = random.Random(seed)
    candles = []
    for i in range(count):
        open_ = rng.uniform(95.0, 105.0)
        close = rng.uniform(95.0, 105.0)
        candles.append(
            Candle(
                timestamp=_BASE + timedelta(hours=4 * i),
                symbol="BTCUSDT",
                timeframe="4h",
                open=open_,
                high=max(open_, close) + rng.uniform(0.0, 3.0),
                low=min(open_, close) - rng.uniform(0.0, 3.0),
                close=close,
                volume=rng.uniform(0.5, 5.0),
                is_closed=True,
            )
        )
    return CandleSeries(symbol="BTCUSDT", timeframe="4h", candles=tuple(candles))


def sheet(**kwargs):
    return build_structural_facts(
        seeded_series(**kwargs), features=regime_features(), source="fixture"
    )


# ============ 1. the feature set ============================================


def test_regime_features_add_only_the_slow_baseline() -> None:
    from fmis.pipeline.multi_timeframe import swing_features

    added = {f.name for f in regime_features()} - {f.name for f in swing_features()}
    assert added == {f"atr_{SLOW_ATR_PERIOD}"}


def test_the_shared_feature_sets_are_untouched() -> None:
    """`facts` and `mtf` must compute exactly what they computed before AI."""
    from fmis.pipeline.market_analysis import default_features
    from fmis.pipeline.multi_timeframe import swing_features

    assert [f.name for f in default_features()] == [
        "ema_20", "ema_50", "rsi_close_14", "atr_14",
        "macd_close_12_26_9", "relative_volume_20",
    ]
    assert f"atr_{SLOW_ATR_PERIOD}" not in {f.name for f in swing_features()}


def test_the_two_true_range_windows_differ() -> None:
    assert FAST_ATR_PERIOD < SLOW_ATR_PERIOD


# ============ 2. the adapter ================================================


def test_the_adapter_copies_and_never_recomputes() -> None:
    built = sheet()
    subject = regime_input_from_sheet(built)
    assert subject.symbol == built.symbol
    assert subject.timeframe == built.interval
    assert subject.as_of == built.as_of
    assert subject.structural_trend is built.structure.trend
    assert subject.close == built.window.last_close
    assert subject.ema_fast == built.features.features["ema_20"].value
    assert subject.atr_slow == built.features.features[f"atr_{SLOW_ATR_PERIOD}"].value


def test_a_warming_up_feature_reaches_the_engine_as_none() -> None:
    """Not zero, and not omitted — `None`, so the dimension reports insufficient."""
    short = build_structural_facts(
        seeded_series(count=40), features=regime_features(), source="fixture"
    )
    subject = regime_input_from_sheet(short)
    assert subject.atr_slow is None
    regime = regime_for_sheet(short)
    assert regime.by_dimension[RegimeDimensionName.VOLATILITY].state is (
        VolatilityState.INSUFFICIENT
    )


def test_the_adapter_rejects_anything_that_is_not_a_sheet() -> None:
    with pytest.raises(TypeError):
        regime_input_from_sheet("not a sheet")  # type: ignore[arg-type]


def test_the_composition_root_contains_no_arithmetic() -> None:
    """The same rule `structural_facts` follows: comparisons belong to engines."""
    tree = ast.parse((SRC / "pipeline" / "regime.py").read_text())
    offenders = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp)
        and isinstance(
            node.op,
            (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Pow, ast.Mod),
        )
    ]
    assert offenders == [], [ast.unparse(o) for o in offenders]


def test_the_root_reaches_the_engine_through_the_narrow_model_only() -> None:
    """`classify_regime` is called with a `RegimeInput` and nothing else."""
    source = (SRC / "pipeline" / "regime.py").read_text()
    tree = ast.parse(source)
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "classify_regime"
    ]
    assert calls
    for call in calls:
        assert isinstance(call.args[0], ast.Call)
        assert call.args[0].func.id == "regime_input_from_sheet"  # type: ignore[attr-defined]


# ============ 3. multi-timeframe stays per view =============================


def test_a_multi_timeframe_regime_carries_no_combination() -> None:
    banned = (
        "agreement", "aligned", "alignment", "consensus", "conflict", "dominant",
        "overall", "score", "confluence", "majority",
    )
    for field in MultiTimeframeRegime.__dataclass_fields__:
        for word in banned:
            assert word not in field.lower(), field
    for name in dir(MultiTimeframeRegime):
        if name.startswith("_"):
            continue
        for word in banned:
            assert word not in name.lower(), name


def test_each_view_keeps_its_own_identity_and_as_of() -> None:
    built = sheet()
    views = tuple(
        RegimeView(role=role, interval=interval, regime=regime_for_sheet(built))
        for role, interval in (
            (TimeframeRole.CONTEXT, "1w"),
            (TimeframeRole.SETUP, "1d"),
            (TimeframeRole.EXECUTION, "4h"),
        )
    )
    multi = MultiTimeframeRegime(
        symbol="BTCUSDT",
        source="fixture",
        views=views,
        policy=views[0].regime.policy,
        limitations=REGIME_LIMITATIONS,
    )
    assert len(multi.views) == 3
    assert set(multi.by_role) == set(TimeframeRole)
    for view in multi.views:
        assert view.regime.as_of == built.as_of
        assert view.regime.symbol == "BTCUSDT"
    assert multi.newest_as_of == built.as_of


def test_an_empty_multi_timeframe_regime_is_rejected() -> None:
    with pytest.raises(ValueError):
        MultiTimeframeRegime(
            symbol="X", source="fixture", views=(),
            policy=RegimePolicy(), limitations=(),
        )


# ============ 4. the renderer ===============================================


def test_the_rendered_page_shows_every_evidence_group() -> None:
    """Including what conflicts and what was unavailable — not only what agrees."""
    from fmis.market_regime import classify_regime
    from tests.test_market_regime import make_input
    from fmis.structural_trend import StructuralTrendType

    regime = classify_regime(
        make_input(
            structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
            close=97.0, ema_fast=100.0, ema_slow=95.0,
            atr_slow=None, participation_ratio=None,
        )
    )
    text = render_module.render_regime_sheet(regime, limitations=REGIME_LIMITATIONS)
    assert "conflicting" in text
    assert "unavailable" in text
    assert "why:" in text


def test_the_rendered_page_carries_the_policy_that_produced_it() -> None:
    text = render_module.render_regime_sheet(regime_for_sheet(sheet()))
    assert "policy_id" in text
    assert "regime-v1" in text
    assert "multiplicative" in text
    assert "transition lookback" in text


def test_the_rendered_page_states_it_is_not_a_recommendation() -> None:
    text = render_module.render_regime_sheet(regime_for_sheet(sheet()))
    assert "not a direction" in text
    assert "none is expressed or implied" in text


_FORBIDDEN = (
    "buy", "sell", "bullish", "bearish", "resistance",
    "recommend", "entry", "target", "confidence", "score",
)


def test_no_trading_vocabulary_in_the_rendered_regime() -> None:
    import re

    text = render_module.render_regime_sheet(
        regime_for_sheet(sheet()), limitations=REGIME_LIMITATIONS
    )
    # The closing disclaimer denies making a recommendation, and says so using
    # the word; asserted separately so removing it fails a test rather than
    # passing this one.
    body = text.replace("a recommendation, and none is expressed or implied.", "")
    words = set(re.findall(r"[a-z]+", body.lower()))
    for banned in _FORBIDDEN:
        assert banned not in words, banned


def test_the_renderer_shows_no_overall_line() -> None:
    text = render_module.render_regime_sheet(regime_for_sheet(sheet()))
    assert "overall" not in text.lower()


def test_evidence_is_ordered_by_an_explicit_rank_not_enum_order() -> None:
    from fmis.market_regime import EvidenceStatus

    assert render_module._EVIDENCE_ORDER == (
        EvidenceStatus.CONSISTENT,
        EvidenceStatus.CONFLICTING,
        EvidenceStatus.CONTEXT,
        EvidenceStatus.UNAVAILABLE,
    )
    assert set(render_module._EVIDENCE_ORDER) == set(EvidenceStatus)


def test_rendering_is_deterministic() -> None:
    built = sheet()
    first = render_module.render_regime_sheet(regime_for_sheet(built))
    second = render_module.render_regime_sheet(regime_for_sheet(built))
    assert first == second


# ============ 5. the command ================================================


def test_the_registry_carries_seven_commands() -> None:
    names = [command.name for command in cli_module.COMMANDS]
    assert names == ["facts", "mtf", "regime", "swing", "setup", "daily", "archive"]
    assert len(set(names)) == len(names)


def test_the_regime_command_parses_its_flags() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(
        ["regime", "BTCUSDT", "-i", "1d", "-n", "300", "--band", "0.3",
         "--transition-lookback", "9"]
    )
    assert args.command == "regime"
    assert args.interval == "1d"
    assert args.band == 0.3
    assert args.transition_lookback == 9
    assert args.multi is False


def test_one_band_flag_reaches_both_dimensions() -> None:
    """Two flags would let a caller skew one gate against the other."""
    parser = cli_module.build_parser()
    args = parser.parse_args(["regime", "BTCUSDT", "--band", "0.4"])
    policy = cli_module._policy_from(args)
    assert policy.volatility_band == policy.participation_band == 0.4
    assert policy.policy_id.endswith("-custom")


def test_the_default_flags_produce_the_default_policy() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(["regime", "BTCUSDT"])
    assert cli_module._policy_from(args) == RegimePolicy()


def test_the_multi_flag_exists_and_defaults_off() -> None:
    parser = cli_module.build_parser()
    assert parser.parse_args(["regime", "BTCUSDT", "--multi"]).multi is True
    assert parser.parse_args(["regime", "BTCUSDT"]).multi is False


# ============ 6. AF and AG are unchanged ====================================


def test_the_fact_sheet_renders_exactly_as_before() -> None:
    """AI adds a command; it must not change what `facts` prints."""
    built = build_structural_facts(seeded_series(), source="fixture")
    text = render_module.render_fact_sheet(built)
    assert "FMITS STRUCTURAL FACT SHEET" in text
    assert "MARKET REGIME" not in text
    for word in ("regime", "trending", "ranging", "participation"):
        assert word not in text.lower(), word


def test_the_multi_timeframe_sheet_renders_exactly_as_before() -> None:
    from fmis.pipeline.multi_timeframe import build_multi_timeframe_facts

    built = build_structural_facts(seeded_series(), source="fixture")
    multi = build_multi_timeframe_facts(
        {role: built for role in TimeframeRole},
        intervals={
            TimeframeRole.CONTEXT: "1w",
            TimeframeRole.SETUP: "1d",
            TimeframeRole.EXECUTION: "4h",
        },
        source="fixture",
    )
    text = render_module.render_multi_timeframe_sheet(multi)
    assert "Reported side by side" in text
    for word in ("regime", "participation", "policy_id"):
        assert word not in text.lower(), word


def test_ah_provenance_survives_the_regime_path() -> None:
    built = sheet()
    assert built.structure.levels
    for level in built.structure.levels:
        assert level.origin is not None
        assert level.origin.confirmation_bars == built.detection.right_bars
    for brk in built.structure.breaks:
        assert brk.eligible_from == brk.origin.knowable_from


def test_custom_detection_settings_reach_the_regime() -> None:
    built = build_structural_facts(
        seeded_series(), features=regime_features(),
        detection=DetectionSettings(3, 4), source="fixture",
    )
    regime = regime_for_sheet(built)
    assert isinstance(regime, MarketRegime)
    for level in built.structure.levels:
        assert level.origin.confirmation_bars == 4


# ============ 7. prefix stability and replay ================================


def test_the_regime_of_a_prefix_is_the_regime_of_that_prefix() -> None:
    """Extending the series must not retroactively change an earlier answer."""
    full = seeded_series(count=300)
    for cut in (150, 200, 250):
        prefix = CandleSeries(
            symbol=full.symbol, timeframe=full.timeframe,
            candles=full.candles[:cut],
        )
        built = build_structural_facts(
            prefix, features=regime_features(), source="fixture"
        )
        first = regime_for_sheet(built)
        second = regime_for_sheet(built)
        assert first == second
        assert first.as_of == prefix.candles[-1].timestamp


def test_the_regime_reads_no_clock() -> None:
    """Two classifications of one sheet are identical, whenever they are made."""
    built = sheet()
    assert regime_for_sheet(built) == regime_for_sheet(built)
    source = (SRC / "pipeline" / "regime.py").read_text()
    for banned in ("datetime.now", "utcnow", "time.time"):
        assert banned not in source


def test_states_actually_vary_across_seeds() -> None:
    """Guards every assertion above from passing on a fixture that never moves."""
    seen = {name: set() for name in RegimeDimensionName}
    for seed in range(25):
        regime = regime_for_sheet(
            build_structural_facts(
                seeded_series(seed=seed), features=regime_features(), source="fixture"
            )
        )
        for dimension in regime.dimensions:
            seen[dimension.name].add(dimension.state)
    assert len(seen[RegimeDimensionName.STRUCTURE]) >= 2
    assert seen[RegimeDimensionName.PARTICIPATION]
    assert seen[RegimeDimensionName.VOLATILITY]


def test_the_adapter_carries_the_change_of_character_when_one_exists() -> None:
    """Survivor 41: dropping it would silently disable the transitioning state.

    Seed 5 produces three changes of character with the latest at bar 254 and the
    last swing at 255, so the adapter's two indices are both non-trivial and the
    engine can compute a real distance from them.
    """
    built = sheet(seed=5)
    assert built.structure.changes
    subject = regime_input_from_sheet(built)
    assert subject.latest_change_index == built.structure.latest_change.index
    assert subject.last_index == built.structure.swings[-1].index
    assert subject.latest_change_index is not None

    # And it reaches the classification: with a lookback wide enough to include
    # it, structure must report transitioning rather than trending or ranging.
    from fmis.market_regime import classify_regime

    wide = RegimePolicy(transition_lookback_bars=50)
    dimension = classify_regime(subject, wide).by_dimension[
        RegimeDimensionName.STRUCTURE
    ]
    assert dimension.state is StructureState.TRANSITIONING


# ============ 8. the network-facing roots, the CLI, and the multi renderer ==
#
# Covered with a stubbed transport, following the pattern AF and AG established:
# a real HTTP call in a unit test would make the suite depend on an exchange.


from tests.test_multi_timeframe import (  # noqa: E402
    DEFAULT_LENGTHS,
    interval_transport,
)

#: A fixed, timezone-aware instant. The provider requires one; supplying it
#: rather than the real clock is what keeps these tests reproducible.
_LATER = datetime(2030, 1, 1, tzinfo=timezone.utc)


def test_regime_for_symbol_fetches_once_and_classifies_that_sheet() -> None:
    from fmis.pipeline.regime import regime_for_symbol

    transport = interval_transport({"4h": 200})
    built, regime = regime_for_symbol(
        "BTCUSDT", "4h", limit=200, transport=transport, clock=lambda: _LATER
    )
    assert len(transport.calls) == 1
    assert regime.symbol == built.symbol == "BTCUSDT"
    assert regime.timeframe == "4h"
    assert regime.as_of == built.as_of
    assert regime == regime_for_sheet(built)


def test_regime_for_symbol_honours_a_supplied_policy() -> None:
    from fmis.pipeline.regime import regime_for_symbol

    policy = RegimePolicy(policy_id="swept", volatility_band=0.05)
    _, regime = regime_for_symbol(
        "BTCUSDT", "4h", limit=200,
        transport=interval_transport({"4h": 200}), clock=lambda: _LATER, policy=policy,
    )
    assert regime.policy is policy


def test_multi_timeframe_regime_classifies_each_role_independently() -> None:
    from fmis.pipeline.regime import multi_timeframe_regime_for_symbol

    transport = interval_transport(DEFAULT_LENGTHS)
    sheets, regimes = multi_timeframe_regime_for_symbol(
        "BTCUSDT", limit=120, transport=transport, clock=lambda: _LATER
    )
    assert len(transport.calls) == 3
    assert [v.role for v in regimes.views] == [
        TimeframeRole.CONTEXT, TimeframeRole.SETUP, TimeframeRole.EXECUTION
    ]
    assert [v.interval for v in regimes.views] == ["1w", "1d", "4h"]
    for view, source in zip(regimes.views, sheets.views):
        assert view.regime.as_of == source.sheet.as_of
        assert view.regime == regime_for_sheet(source.sheet)
    assert regimes.newest_as_of == max(v.regime.as_of for v in regimes.views)
    assert regimes.limitations == REGIME_LIMITATIONS


def test_the_multi_timeframe_regime_page_renders_every_role() -> None:
    from fmis.pipeline.regime import multi_timeframe_regime_for_symbol

    _, regimes = multi_timeframe_regime_for_symbol(
        "BTCUSDT", limit=120,
        transport=interval_transport(DEFAULT_LENGTHS), clock=lambda: _LATER,
    )
    text = render_module.render_multi_timeframe_regime(regimes)
    for role in ("CONTEXT", "SETUP", "EXECUTION"):
        assert role in text
    assert "REGIME BY ROLE" in text
    assert "Reported side by side. Nothing is derived from the combination." in text
    assert "policy_id" in text
    assert "[AI-1]" in text and "[AI-4]" in text
    assert "overall" not in text.lower()
    assert "agreement" not in text.lower()


def test_the_regime_command_runs_both_paths(capsys, monkeypatch) -> None:
    import fmis.pipeline.regime as regime_module

    monkeypatch.setattr(
        regime_module, "structural_facts_for_symbol",
        lambda symbol, interval, **kw: build_structural_facts(
            seeded_series(), features=regime_features(), source="fixture"
        ),
    )
    assert cli_module.main(["regime", "BTCUSDT", "-n", "260"]) == 0
    single = capsys.readouterr().out
    assert "FMITS MARKET REGIME" in single
    assert "[AI-1]" in single

    monkeypatch.setattr(
        regime_module, "multi_timeframe_facts_for_symbol",
        lambda symbol, **kw: __import__(
            "fmis.pipeline.multi_timeframe", fromlist=["build_multi_timeframe_facts"]
        ).build_multi_timeframe_facts(
            {
                role: build_structural_facts(
                    seeded_series(), features=regime_features(), source="fixture"
                )
                for role in TimeframeRole
            },
            intervals={
                TimeframeRole.CONTEXT: "1w",
                TimeframeRole.SETUP: "1d",
                TimeframeRole.EXECUTION: "4h",
            },
            source="fixture",
        ),
    )
    assert cli_module.main(["regime", "BTCUSDT", "--multi"]) == 0
    multi = capsys.readouterr().out
    assert "FMITS MULTI-TIMEFRAME REGIME" in multi
    assert "REGIME BY ROLE" in multi


def test_a_missing_or_non_numeric_feature_reads_as_unavailable() -> None:
    """Both `_value` fallbacks: absent from the set, and present but not a number."""
    from fmis.pipeline.regime import _value

    built = sheet()
    assert _value(built, "no_such_feature") is None
    assert _value(built, "ema_20") is not None


def test_a_non_numeric_feature_value_reads_as_unavailable() -> None:
    """`_value`'s last branch: present, not `None`, and not a number.

    No shipped feature returns one today, so it is constructed here rather than
    left as the one line the suite never reaches.
    """
    from fmis.features.types import FeatureCategory, FeatureResult, FeatureSet
    from fmis.pipeline.regime import _value

    built = sheet()
    odd = FeatureResult(
        name="ema_20", category=FeatureCategory.TREND, value="not a number"
    )
    patched = FeatureSet(
        symbol=built.features.symbol,
        timeframe=built.features.timeframe,
        as_of=built.features.as_of,
        features={**dict(built.features.features), "ema_20": odd},
    )
    object.__setattr__(built, "features", patched)
    assert _value(built, "ema_20") is None
