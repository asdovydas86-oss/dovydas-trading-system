"""Tests for Decision Support Evidence v1 (fmis.decision_support).

Two styles are used deliberately:

  * the classification rules and the one derived calculation are tested as pure
    functions, directly on values, including every band boundary;
  * the report is tested against real `AnalysisSnapshot`s built through the
    pipeline with an injected transport and clock, so the shapes are the ones
    the engines actually emit rather than hand-made stand-ins.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import fmis.decision_support as ds
from fmis.decision_support import (
    Alignment,
    Comparison,
    EvidenceReport,
    Observation,
    OverallState,
    RsiZone,
    Sign,
    atr_percent_of_close,
    build_evidence_report,
    classify_comparison,
    classify_rsi_zone,
    classify_sign,
)
from fmis.decision_support.report import (
    ATR_FEATURE,
    EMA_FAST_FEATURE,
    EMA_SLOW_FEATURE,
    MACD_FEATURE,
    MIN_DIRECTIONAL_OBSERVATIONS,
    RSI_FEATURE,
)
from fmis.features.indicators.ema import ExponentialMovingAverage
from fmis.pipeline import analyze_symbol
from fmis.providers.binance import HttpResponse

_OPEN_MS = 1_704_067_200_000
_FOUR_HOURS_MS = 4 * 60 * 60 * 1000
_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
LATER = datetime(2024, 6, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------- fixtures ---


def kline(i: int, close: float) -> list[object]:
    open_ms = _OPEN_MS + i * _FOUR_HOURS_MS
    return [
        open_ms,
        f"{close:.8f}", f"{close * 1.01:.8f}", f"{close * 0.99:.8f}", f"{close:.8f}",
        "1000.00000000",
        open_ms + _FOUR_HOURS_MS - 1,
        "1000.0", 100, "500.0", "500.0", "0",
    ]


def routed(by_symbol: dict[str, list]):
    def _transport(url: str) -> HttpResponse:
        for symbol, payload in by_symbol.items():
            if f"symbol={symbol}&" in url or url.endswith(f"symbol={symbol}"):
                return HttpResponse(status=200, body=json.dumps(payload).encode())
        raise AssertionError(f"unexpected symbol in {url}")

    return _transport


def snapshot_for(closes: list[float], **kwargs):
    payload = {"BTCUSDT": [kline(i, c) for i, c in enumerate(closes)]}
    benchmark = kwargs.pop("benchmark_closes", None)
    if benchmark is not None:
        payload["ETHUSDT"] = [kline(i, c) for i, c in enumerate(benchmark)]
        kwargs["benchmark_symbol"] = "ETHUSDT"
    return analyze_symbol(
        "BTCUSDT", "4h", transport=routed(payload), clock=lambda: LATER, **kwargs
    )


def rising(n: int = 60) -> list[float]:
    """Accelerating rise: every observation leans upward, MACD included.

    A *linear* ramp is deliberately not used here — see `linear_ramp`.
    """
    return [100.0 * (1.02 ** i) for i in range(n)]


def falling(n: int = 60) -> list[float]:
    """Rise then a sharp drop: every observation leans downward.

    Price ends below both EMAs, the fast EMA below the slow, and MACD below its
    signal with a negative histogram.
    """
    return [100.0 + 2.0 * i for i in range(50)] + [150.0 - 8.0 * i for i in range(10)]


def conflicting(n: int = 60) -> list[float]:
    """Decaying series: trend leans down while MACD leans up.

    An exponential decay flattens, so the MACD line rises toward its signal from
    below and the histogram turns positive while price is still under both EMAs.
    Real, and exactly the disagreement the grouping rules exist to report.
    """
    return [100.0 * (0.98 ** i) for i in range(n)]


def linear_ramp(n: int = 60) -> list[float]:
    """Perfectly linear rise.

    A mathematical edge case worth pinning: on a constant-slope series the MACD
    line settles at a constant, so its signal EMA equals it exactly — giving
    `equal` and a `zero` histogram rather than a lean either way.
    """
    return [100.0 + 2.0 * i for i in range(n)]


def flat(n: int = 60, level: float = 100.0) -> list[float]:
    return [level] * n


def report_for(closes: list[float], **kwargs) -> EvidenceReport:
    return build_evidence_report(snapshot_for(closes, **kwargs))


# ============================ classify_comparison ============================


@pytest.mark.parametrize(
    "left,right,expected",
    [
        (2.0, 1.0, Comparison.ABOVE),
        (1.0, 2.0, Comparison.BELOW),
        (1.0, 1.0, Comparison.EQUAL),
        (0.0, 0.0, Comparison.EQUAL),
        (-1.0, -2.0, Comparison.ABOVE),
        (None, 1.0, Comparison.UNAVAILABLE),
        (1.0, None, Comparison.UNAVAILABLE),
        (None, None, Comparison.UNAVAILABLE),
    ],
)
def test_classify_comparison(left, right, expected) -> None:
    assert classify_comparison(left, right) is expected


def test_comparison_uses_no_tolerance() -> None:
    # A hair apart is ABOVE, not EQUAL: no epsilon is invented.
    assert classify_comparison(1.0 + 1e-12, 1.0) is Comparison.ABOVE


# ============================ classify_rsi_zone ==============================


@pytest.mark.parametrize(
    "rsi,expected",
    [
        (0.0, RsiZone.OVERSOLD_ZONE),
        (29.999, RsiZone.OVERSOLD_ZONE),
        (30.0, RsiZone.LOWER_NEUTRAL),      # 30 is NOT oversold
        (44.999, RsiZone.LOWER_NEUTRAL),
        (45.0, RsiZone.NEUTRAL),
        (50.0, RsiZone.NEUTRAL),
        (55.0, RsiZone.NEUTRAL),            # upper edge inclusive
        (55.001, RsiZone.UPPER_NEUTRAL),
        (70.0, RsiZone.UPPER_NEUTRAL),      # 70 is NOT overbought
        (70.001, RsiZone.OVERBOUGHT_ZONE),
        (100.0, RsiZone.OVERBOUGHT_ZONE),
        (None, RsiZone.UNAVAILABLE),
    ],
)
def test_classify_rsi_zone_boundaries(rsi, expected) -> None:
    assert classify_rsi_zone(rsi) is expected


def test_rsi_bands_are_exhaustive_and_ordered() -> None:
    zones = [classify_rsi_zone(v) for v in [i / 2 for i in range(0, 201)]]
    assert RsiZone.UNAVAILABLE not in zones
    # Bands never go backwards as RSI rises.
    order = list(RsiZone)[:5]
    positions = [order.index(z) for z in zones]
    assert positions == sorted(positions)


# ============================ classify_sign ==================================


@pytest.mark.parametrize(
    "value,expected",
    [
        (0.5, Sign.POSITIVE),
        (-0.5, Sign.NEGATIVE),
        (0.0, Sign.ZERO),
        (-0.0, Sign.ZERO),
        (None, Sign.UNAVAILABLE),
    ],
)
def test_classify_sign(value, expected) -> None:
    assert classify_sign(value) is expected


# ============================ atr_percent_of_close ===========================


def test_atr_percent_basic() -> None:
    assert atr_percent_of_close(5.0, 100.0) == pytest.approx(5.0)
    assert atr_percent_of_close(1.5, 200.0) == pytest.approx(0.75)


def test_atr_percent_zero_atr_is_zero_not_none() -> None:
    assert atr_percent_of_close(0.0, 100.0) == 0.0


def test_atr_percent_zero_close_is_unavailable() -> None:
    assert atr_percent_of_close(5.0, 0.0) is None


@pytest.mark.parametrize("atr,close", [(None, 100.0), (5.0, None), (None, None)])
def test_atr_percent_unavailable_inputs(atr, close) -> None:
    assert atr_percent_of_close(atr, close) is None


def test_atr_percent_is_scale_invariant() -> None:
    assert atr_percent_of_close(5.0, 100.0) == pytest.approx(
        atr_percent_of_close(50.0, 1000.0)
    )


# ============================ market context =================================


def test_context_facts() -> None:
    report = report_for(rising(60))
    context = report.context
    assert context.symbol == "BTCUSDT"
    assert context.interval == "4h"
    assert context.as_of == _BASE + timedelta(hours=4 * 59)
    assert context.analysed_candle_count == 60
    assert context.benchmark_symbol is None


# ============================ trend evidence =================================


def test_price_above_both_emas_when_rising() -> None:
    trend = report_for(rising(60)).trend
    assert trend.price_vs_ema_fast.classification == "above"
    assert trend.price_vs_ema_slow.classification == "above"
    assert trend.ema_fast_vs_ema_slow.classification == "above"


def test_price_below_both_emas_when_falling() -> None:
    trend = report_for(falling(60)).trend
    assert trend.price_vs_ema_fast.classification == "below"
    assert trend.price_vs_ema_slow.classification == "below"
    assert trend.ema_fast_vs_ema_slow.classification == "below"


def test_price_equal_to_emas_when_flat() -> None:
    trend = report_for(flat(60)).trend
    assert trend.price_vs_ema_fast.classification == "equal"
    assert trend.price_vs_ema_slow.classification == "equal"
    assert trend.ema_fast_vs_ema_slow.classification == "equal"
    for obs in trend.observations:
        assert obs.alignment is Alignment.NEUTRAL


def test_trend_observations_carry_their_inputs() -> None:
    trend = report_for(rising(60)).trend
    inputs = trend.price_vs_ema_fast.inputs
    assert set(inputs) == {"close", EMA_FAST_FEATURE}
    assert inputs["close"] == pytest.approx(rising(60)[-1])


def test_trend_unavailable_when_emas_missing() -> None:
    # Only an RSI feature requested -> no EMA results at all.
    from fmis.features.indicators.rsi import RelativeStrengthIndex

    report = build_evidence_report(
        snapshot_for(rising(60), features=[RelativeStrengthIndex(14)])
    )
    for obs in report.trend.observations:
        assert obs.classification == "unavailable"
        assert obs.alignment is Alignment.UNAVAILABLE


def test_trend_unavailable_on_warmup() -> None:
    # 25 candles: EMA(20) resolves, EMA(50) is still warming up.
    report = report_for(rising(25))
    assert report.trend.price_vs_ema_fast.classification == "above"
    assert report.trend.price_vs_ema_slow.classification == "unavailable"
    assert report.trend.ema_fast_vs_ema_slow.classification == "unavailable"
    assert EMA_SLOW_FEATURE in report.metadata["warming_up_features"]


# ============================ momentum evidence ==============================


def test_macd_classifications_when_rising() -> None:
    momentum = report_for(rising(60)).momentum
    assert momentum.macd_vs_signal.classification == "above"
    assert momentum.macd_histogram.classification == "positive"
    assert momentum.macd_line is not None
    assert momentum.macd_signal_line is not None


def test_linear_ramp_gives_macd_exactly_equal_to_its_signal() -> None:
    # On a constant-slope series the MACD line is constant, so its signal EMA
    # equals it exactly: the EQUAL/ZERO branch, reached by real data.
    momentum = report_for(linear_ramp(60)).momentum
    assert momentum.macd_line == momentum.macd_signal_line
    assert momentum.macd_vs_signal.classification == "equal"
    assert momentum.macd_histogram.classification == "zero"


def test_macd_classifications_when_falling() -> None:
    momentum = report_for(falling(60)).momentum
    assert momentum.macd_vs_signal.classification == "below"
    assert momentum.macd_histogram.classification == "negative"


def test_flat_series_gives_zero_histogram() -> None:
    momentum = report_for(flat(60)).momentum
    assert momentum.macd_histogram.classification == "zero"
    assert momentum.macd_histogram.alignment is Alignment.NEUTRAL


def test_rsi_zone_reported_but_never_directional() -> None:
    momentum = report_for(rising(60)).momentum
    assert momentum.rsi_value == pytest.approx(100.0)  # monotonic rise
    assert momentum.rsi_zone.classification == "overbought_zone"
    # The whole point: an extreme band contributes no direction.
    assert momentum.rsi_zone.alignment is Alignment.NOT_DIRECTIONAL
    assert not momentum.rsi_zone.directional


def test_overbought_rsi_never_becomes_conflicting_evidence() -> None:
    report = report_for(rising(60))
    assert report.momentum.rsi_zone.classification == "overbought_zone"
    assert report.momentum.rsi_zone not in report.groups.conflicting
    assert report.momentum.rsi_zone not in report.groups.supporting
    assert report.state is OverallState.WATCH  # not downgraded by the band


def test_momentum_unavailable_on_warmup() -> None:
    report = report_for(rising(10))
    assert report.momentum.macd_vs_signal.classification == "unavailable"
    assert report.momentum.macd_histogram.classification == "unavailable"
    assert report.momentum.rsi_zone.classification == "unavailable"


# ============================ volatility evidence ============================


def test_volatility_evidence_available() -> None:
    volatility = report_for(rising(60)).volatility
    last_close = rising(60)[-1]
    assert volatility.atr_value is not None
    assert volatility.last_close == pytest.approx(last_close)
    assert volatility.atr_percent_of_close == pytest.approx(
        volatility.atr_value / last_close * 100.0
    )
    assert volatility.available


def test_volatility_unavailable_on_warmup() -> None:
    volatility = report_for(rising(10)).volatility
    assert volatility.atr_value is None
    assert volatility.atr_percent_of_close is None
    assert not volatility.available


def test_volatility_zero_close_yields_unavailable_percentage() -> None:
    # A run of zero closes: ATR resolves to 0, but ATR% is undefined at price 0.
    report = report_for(flat(60, level=0.0))
    assert report.volatility.last_close == 0.0
    assert report.volatility.atr_percent_of_close is None
    assert not report.volatility.available


# ============================ relative-value evidence ========================


def test_relative_value_absent_without_benchmark() -> None:
    assert report_for(rising(60)).relative_value is None
    assert report_for(rising(60)).context.benchmark_symbol is None


def test_relative_value_present_with_benchmark() -> None:
    report = report_for(rising(60), benchmark_closes=[50.0 + i for i in range(60)])
    section = report.relative_value
    assert section is not None
    assert section.benchmark_symbol == "ETHUSDT"
    assert report.context.benchmark_symbol == "ETHUSDT"
    assert section.aligned_observation_count == 60
    for value in (section.primary_return, section.benchmark_return,
                  section.relative_return, section.volatility_ratio,
                  section.correlation):
        assert value is not None


def test_relative_value_reuses_snapshot_results_exactly() -> None:
    """Values must be copied from the RVE result, never recomputed."""
    snapshot = snapshot_for(rising(60), benchmark_closes=[50.0 + i for i in range(60)])
    report = build_evidence_report(snapshot)
    metrics = snapshot.relative_value.metrics
    section = report.relative_value
    assert section.relative_return == metrics["relative_return"].value
    assert section.volatility_ratio == metrics["volatility_ratio"].value
    assert section.correlation == metrics["pearson_correlation"].value
    assert section.primary_return == metrics["period_return_primary"].value
    assert section.benchmark_return == metrics["period_return_benchmark"].value


def test_undefined_rve_metrics_carry_their_reason() -> None:
    # A flat benchmark has zero return variance -> correlation UNDEFINED.
    report = report_for(rising(60), benchmark_closes=flat(60, 50.0))
    section = report.relative_value
    assert section.correlation is None
    assert section.undefined_reasons["pearson_correlation"] == "zero_variance"
    assert section.undefined_reasons["volatility_ratio"] == "zero_reference_volatility"


def test_undefined_reasons_empty_when_all_defined() -> None:
    report = report_for(rising(60), benchmark_closes=[50.0 + i for i in range(60)])
    assert dict(report.relative_value.undefined_reasons) == {}


# ============================ grouping =======================================


def test_all_upward_observations_support_each_other() -> None:
    groups = report_for(rising(60)).groups
    assert groups.dominant_alignment is Alignment.UPWARD
    assert len(groups.supporting) == 5  # 3 trend + macd_vs_signal + histogram
    assert groups.conflicting == ()
    assert groups.unavailable == ()


def test_all_downward_observations_support_each_other() -> None:
    groups = report_for(falling(60)).groups
    assert groups.dominant_alignment is Alignment.DOWNWARD
    assert len(groups.supporting) == 5
    assert groups.conflicting == ()


def test_neutral_observations_support_nothing_and_conflict_with_nothing() -> None:
    groups = report_for(flat(60)).groups
    assert groups.supporting == ()
    assert groups.conflicting == ()
    assert groups.unavailable == ()


def test_mixed_evidence_produces_conflict() -> None:
    groups = report_for(conflicting(60)).groups
    # Trend leans down (3 observations), MACD leans up (2): a real disagreement.
    assert groups.dominant_alignment is Alignment.DOWNWARD
    assert len(groups.supporting) == 3
    assert len(groups.conflicting) == 2
    assert {o.key for o in groups.conflicting} == {"macd_vs_signal", "macd_histogram"}


def test_unavailable_observations_are_grouped_separately() -> None:
    report = report_for(rising(25))  # EMA(50) and MACD still warming up
    keys = {o.key for o in report.groups.unavailable}
    assert "price_vs_ema_slow" in keys
    assert "ema_fast_vs_ema_slow" in keys
    for obs in report.groups.unavailable:
        assert obs not in report.groups.supporting
        assert obs not in report.groups.conflicting


def test_every_observation_lands_in_exactly_one_place() -> None:
    for closes in (rising(60), falling(60), conflicting(60), linear_ramp(60),
                   rising(25), rising(10)):
        report = build_evidence_report(snapshot_for(closes))
        directional = report.trend.observations + (
            report.momentum.macd_vs_signal,
            report.momentum.macd_histogram,
        )
        grouped = (
            list(report.groups.supporting)
            + list(report.groups.conflicting)
            + [o for o in report.groups.unavailable if o.key != "rsi_zone"]
        )
        neutral = [o for o in directional if o.alignment is Alignment.NEUTRAL]
        assert len(grouped) + len(neutral) == len(directional)


# ============================ scenarios ======================================


def test_scenarios_always_present() -> None:
    scenarios = report_for(rising(60)).scenarios
    assert set(scenarios) == {"continuation", "deterioration", "neutral"}


def test_continuation_restates_supporting_observations() -> None:
    report = report_for(rising(60))
    conditions = report.scenarios["continuation"].conditions
    assert len(conditions) == len(report.groups.supporting)
    assert "price_vs_ema_fast remains above" in conditions


def test_deterioration_flips_supporting_observations() -> None:
    conditions = report_for(rising(60)).scenarios["deterioration"].conditions
    assert "price_vs_ema_fast becomes below" in conditions
    assert "macd_histogram becomes negative" in conditions


def test_deterioration_flips_the_other_way_when_falling() -> None:
    conditions = report_for(falling(60)).scenarios["deterioration"].conditions
    assert "price_vs_ema_fast becomes above" in conditions


def test_neutral_scenario_collects_conflicting_and_unavailable() -> None:
    report = report_for(rising(25))
    conditions = report.scenarios["neutral"].conditions
    assert any("unavailable" in c for c in conditions)


def test_scenarios_contain_no_levels_or_quantities() -> None:
    for closes in (rising(60), falling(60), conflicting(60), flat(60), rising(25)):
        report = build_evidence_report(snapshot_for(closes))
        for scenario in report.scenarios.values():
            for condition in scenario.conditions:
                assert not re.search(r"\d", condition), condition


# ============================ overall state ==================================


def test_watch_when_evidence_agrees() -> None:
    assert report_for(rising(60)).state is OverallState.WATCH
    assert report_for(falling(60)).state is OverallState.WATCH


def test_wait_when_evidence_conflicts() -> None:
    assert report_for(conflicting(60)).state is OverallState.WAIT


def test_watch_survives_a_linear_ramp_being_partly_neutral() -> None:
    # 3 upward trend observations, 2 neutral MACD ones, nothing conflicting.
    report = report_for(linear_ramp(60))
    assert report.groups.conflicting == ()
    assert len(report.groups.supporting) == 3
    assert report.state is OverallState.WATCH


def test_wait_when_everything_is_neutral() -> None:
    # Coherent but saying nothing is WAIT, not WATCH.
    report = report_for(flat(60))
    assert report.groups.supporting == ()
    assert report.state is OverallState.WAIT


def test_insufficient_data_on_warmup() -> None:
    assert report_for(rising(10)).state is OverallState.INSUFFICIENT_DATA


def test_insufficient_data_when_features_missing() -> None:
    report = build_evidence_report(
        snapshot_for(rising(60), features=[ExponentialMovingAverage(20)])
    )
    assert report.state is OverallState.INSUFFICIENT_DATA
    assert set(report.metadata["missing_features"]) == {
        EMA_SLOW_FEATURE, RSI_FEATURE, ATR_FEATURE, MACD_FEATURE,
    }


def test_state_threshold_boundary() -> None:
    # 25 candles: ema_20 vs price available, ema_50 and MACD are not -> 1 of 5.
    report = report_for(rising(25))
    available = [
        o for o in report.trend.observations
        + (report.momentum.macd_vs_signal, report.momentum.macd_histogram)
        if o.directional
    ]
    assert len(available) < MIN_DIRECTIONAL_OBSERVATIONS
    assert report.state is OverallState.INSUFFICIENT_DATA


def test_state_values_are_the_only_allowed_ones() -> None:
    assert {s.value for s in OverallState} == {"watch", "wait", "insufficient_data"}


# ============================ determinism / immutability =====================


def test_report_is_deterministic() -> None:
    snapshot = snapshot_for(rising(60), benchmark_closes=[50.0 + i for i in range(60)])
    first = build_evidence_report(snapshot)
    second = build_evidence_report(snapshot)
    assert first == second


def test_report_is_frozen() -> None:
    report = report_for(rising(60))
    with pytest.raises(AttributeError):
        report.state = OverallState.WAIT  # type: ignore[misc]


def test_report_mappings_are_read_only() -> None:
    report = report_for(rising(60), benchmark_closes=[50.0 + i for i in range(60)])
    with pytest.raises(TypeError):
        report.metadata["x"] = 1  # type: ignore[index]
    with pytest.raises(TypeError):
        report.scenarios["x"] = None  # type: ignore[index]
    with pytest.raises(TypeError):
        report.relative_value.undefined_reasons["x"] = "y"  # type: ignore[index]
    with pytest.raises(TypeError):
        report.trend.price_vs_ema_fast.inputs["x"] = 1  # type: ignore[index]


def test_observation_inputs_are_defensively_copied() -> None:
    original = {"close": 1.0}
    obs = Observation(key="k", classification="above", alignment=Alignment.UPWARD,
                      inputs=original)
    original["close"] = 999.0
    assert obs.inputs["close"] == 1.0


def test_grouped_sequences_are_tuples() -> None:
    groups = report_for(rising(60)).groups
    for group in (groups.supporting, groups.conflicting, groups.unavailable):
        assert isinstance(group, tuple)


def test_snapshot_is_not_mutated() -> None:
    snapshot = snapshot_for(rising(60), benchmark_closes=[50.0 + i for i in range(60)])
    before = (
        snapshot.as_of,
        snapshot.window,
        dict(snapshot.metadata),
        {k: v.value for k, v in snapshot.features.features.items()},
        {k: v.value for k, v in snapshot.relative_value.metrics.items()},
    )
    build_evidence_report(snapshot)
    after = (
        snapshot.as_of,
        snapshot.window,
        dict(snapshot.metadata),
        {k: v.value for k, v in snapshot.features.features.items()},
        {k: v.value for k, v in snapshot.relative_value.metrics.items()},
    )
    assert before == after


# ============================ no prohibited vocabulary =======================

_BANNED = (
    "buy", "sell", "long", "short", "bullish", "bearish", "bull", "bear",
    "confidence", "recommend", "recommendation", "target", "stop_loss",
    "stoploss", "position_size", "entry", "exit", "signal", "score", "rating",
)


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z_]+", text.lower()))


def test_no_prohibited_vocabulary_in_public_fields_or_metadata() -> None:
    report = report_for(rising(60), benchmark_closes=[50.0 + i for i in range(60)])
    surface: list[str] = [
        report.state.value,
        *report.metadata.keys(),
        *(str(v) for v in report.metadata.values()),
        *report.scenarios.keys(),
        *(c for s in report.scenarios.values() for c in s.conditions),
        *(o.key for o in report.trend.observations + report.momentum.observations),
        *(o.classification for o in report.trend.observations
          + report.momentum.observations),
        *report.relative_value.undefined_reasons.keys(),
    ]
    words = _words(" ".join(surface))
    for banned in _BANNED:
        assert banned not in words, banned


def test_no_prohibited_vocabulary_in_public_type_field_names() -> None:
    from dataclasses import fields, is_dataclass

    names: set[str] = set()
    for exported in ds.__all__:
        obj = getattr(ds, exported)
        if is_dataclass(obj):
            names |= {f.name for f in fields(obj)}
    for banned in _BANNED:
        assert not any(banned in _words(n) for n in names), banned


def test_state_vocabulary_carries_no_direction() -> None:
    for state in OverallState:
        words = _words(state.value)
        assert not (words & {"up", "down", "upward", "downward", "rising", "falling"})


# ============================ no recalculation ===============================


def test_layer_defines_no_calculation_outside_derived() -> None:
    """Only derived.py may compute; the rest classifies and arranges.

    `Add` is excluded because tuple concatenation uses it and this layer
    assembles a lot of tuples. The remaining operators cannot be sequence
    operations, and no average, ratio, percentage, or difference can be built
    without one of them.
    """
    package = Path(ds.__file__).parent
    for py in package.glob("*.py"):
        if py.name == "derived.py":
            continue
        operators = [
            node for node in ast.walk(ast.parse(py.read_text()))
            if isinstance(node, ast.BinOp)
            and isinstance(node.op, (ast.Sub, ast.Mult, ast.Div,
                                     ast.FloorDiv, ast.Pow, ast.Mod))
        ]
        assert operators == [], f"{py.name} contains arithmetic"


def test_derived_module_is_the_only_place_that_divides() -> None:
    derived = Path(ds.__file__).parent / "derived.py"
    divisions = [
        node for node in ast.walk(ast.parse(derived.read_text()))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
    ]
    assert len(divisions) == 1  # atr / close


def test_layer_imports_no_engine_math() -> None:
    imports = _internal_imports(Path(ds.__file__).parent)
    for forbidden in ("fmis.providers", "fmis.ingest", "fmis.alignment",
                      "fmis.features.indicators", "fmis.relative_value"):
        assert not any(i.startswith(forbidden) for i in imports), forbidden


def test_layer_uses_no_numeric_library() -> None:
    package = Path(ds.__file__).parent
    roots: set[str] = set()
    for py in package.glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                roots |= {a.name.split(".")[0] for a in node.names}
    for forbidden in ("math", "statistics", "decimal", "fractions"):
        assert forbidden not in roots, forbidden


# ============================ public API / boundaries ========================


def _internal_imports(pkg_dir: Path) -> set[str]:
    found: set[str] = set()
    for py in pkg_dir.glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("fmis"):
                    found.add(node.module)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith("fmis"):
                        found.add(a.name)
    return found


def test_public_api_exports() -> None:
    for name in ("build_evidence_report", "EvidenceReport", "OverallState",
                 "atr_percent_of_close", "classify_rsi_zone"):
        assert name in ds.__all__
        assert hasattr(ds, name)


def test_nothing_below_imports_decision_support() -> None:
    src = Path(ds.__file__).parent.parent  # src/fmis
    offenders: list[str] = []
    for package in ("data", "ingest", "providers", "features", "alignment",
                    "relative_value", "pipeline"):
        for py in (src / package).rglob("*.py"):
            if "decision_support" in py.read_text():
                offenders.append(str(py))
    assert offenders == []


def test_depends_on_pipeline_result_types_only() -> None:
    imports = _internal_imports(Path(ds.__file__).parent)
    assert "fmis.pipeline" in imports
    assert not any(i.startswith("fmis.pipeline.") for i in imports)


def test_importing_pipeline_does_not_load_decision_support(
    fresh_fmis_imports: None,
) -> None:
    import fmis.pipeline  # noqa: F401

    assert not any(m.startswith("fmis.decision_support") for m in sys.modules)
