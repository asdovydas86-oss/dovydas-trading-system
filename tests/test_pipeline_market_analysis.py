"""Tests for the Market Analysis Pipeline v1 (fmis.pipeline.market_analysis).

Fully deterministic and network-free: the provider transport and the clock are
injected, so every candle, timestamp and closed/forming decision is fixed by the
test rather than by wall-clock time or a live endpoint.
"""

from __future__ import annotations

import ast
import json

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import fmis.pipeline as pipeline
from fmis.alignment import AlignmentReport
from fmis.data import CandleField, candle_series_to_observations
from fmis.features import FeatureSet
from fmis.features.indicators.ema import ExponentialMovingAverage
from fmis.features.indicators.rsi import RelativeStrengthIndex
from fmis.ingest import IngestError
from fmis.pipeline import (
    AnalysisSnapshot,
    DataWindow,
    InsufficientDataError,
    PipelineError,
    RelativeValueSection,
    analyze_symbol,
    default_features,
)
from fmis.providers.binance import (
    BinanceAPIError,
    BinanceResponseError,
    BinanceTransportError,
    HttpResponse,
)
from fmis.relative_value import MetricStatus, pearson_correlation, relative_return

_OPEN_MS = 1_704_067_200_000  # 2024-01-01T00:00:00Z
_FOUR_HOURS_MS = 4 * 60 * 60 * 1000
_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
LATER = datetime(2024, 6, 1, tzinfo=timezone.utc)  # everything closed


def kline(i: int, close: float, *, closed: bool = True) -> list[object]:
    """One Binance kline. ``closed=False`` pushes close time past the test clock."""
    open_ms = _OPEN_MS + i * _FOUR_HOURS_MS
    close_ms = open_ms + _FOUR_HOURS_MS - 1
    if not closed:
        # Far future close time -> still forming relative to the LATER clock.
        close_ms = int(datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    return [
        open_ms,
        f"{close:.8f}",
        f"{close * 1.01:.8f}",
        f"{close * 0.99:.8f}",
        f"{close:.8f}",
        "1000.00000000",
        close_ms,
        "1000.0", 100, "500.0", "500.0", "0",
    ]


def klines(closes: list[float], *, forming_tail: bool = False) -> list[list[object]]:
    rows = [kline(i, c) for i, c in enumerate(closes)]
    if forming_tail and rows:
        rows[-1] = kline(len(closes) - 1, closes[-1], closed=False)
    return rows


def ramp(n: int, start: float = 100.0, step: float = 1.0) -> list[float]:
    return [start + step * i for i in range(n)]


def routed_transport(by_symbol: dict[str, object], *, status: int = 200):
    """Transport answering per-symbol, so a primary and benchmark differ."""

    def _transport(url: str) -> HttpResponse:
        _transport.calls.append(url)  # type: ignore[attr-defined]
        for symbol, payload in by_symbol.items():
            if f"symbol={symbol}&" in url or url.endswith(f"symbol={symbol}"):
                body = (
                    payload if isinstance(payload, bytes)
                    else json.dumps(payload).encode()
                )
                return HttpResponse(status=status, body=body)
        raise AssertionError(f"unexpected symbol in {url}")

    _transport.calls = []  # type: ignore[attr-defined]
    return _transport


def fixed_clock(moment: datetime = LATER):
    return lambda: moment


def analyse(payload_by_symbol: dict[str, object], **kwargs):
    kwargs.setdefault("transport", routed_transport(payload_by_symbol))
    kwargs.setdefault("clock", fixed_clock())
    symbol = kwargs.pop("symbol", "BTCUSDT")
    interval = kwargs.pop("interval", "4h")
    return analyze_symbol(symbol, interval, **kwargs)


# ============================ single-symbol pipeline =========================


def test_single_symbol_snapshot() -> None:
    snapshot = analyse({"BTCUSDT": klines(ramp(60))})
    assert isinstance(snapshot, AnalysisSnapshot)
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.interval == "4h"
    assert snapshot.benchmark_symbol is None
    assert snapshot.relative_value is None
    assert isinstance(snapshot.features, FeatureSet)


def test_as_of_is_last_closed_candle_not_wall_clock() -> None:
    snapshot = analyse({"BTCUSDT": klines(ramp(60))})
    assert snapshot.as_of == _BASE + timedelta(hours=4 * 59)
    assert snapshot.as_of != LATER


def test_default_features_all_present_and_valued() -> None:
    snapshot = analyse({"BTCUSDT": klines(ramp(60))})
    names = {f.name for f in default_features()}
    assert set(snapshot.features.features) == names
    # 60 closed candles clears every default warm-up (MACD needs 34).
    for name in names:
        assert snapshot.features.get(name).value is not None, name


def test_explicit_feature_selection_is_honoured() -> None:
    snapshot = analyse(
        {"BTCUSDT": klines(ramp(30))},
        features=[ExponentialMovingAverage(10), RelativeStrengthIndex(14)],
    )
    assert set(snapshot.features.features) == {"ema_10", "rsi_close_14"}


def test_warmup_is_a_result_not_a_failure() -> None:
    # 10 closed candles: EMA(20) cannot be computed yet, but this is not an error.
    snapshot = analyse(
        {"BTCUSDT": klines(ramp(10))}, features=[ExponentialMovingAverage(20)]
    )
    result = snapshot.features.get("ema_20")
    assert result.value is None
    assert result.metadata  # warm-up metadata preserved from the feature


def test_window_facts_reported() -> None:
    snapshot = analyse({"BTCUSDT": klines(ramp(20))})
    window = snapshot.window
    assert isinstance(window, DataWindow)
    assert window.fetched_count == 20
    assert window.closed_count == 20
    assert window.excluded_forming_count == 0
    assert window.first_timestamp == _BASE
    assert window.last_timestamp == _BASE + timedelta(hours=4 * 19)


def test_request_metadata_is_factual() -> None:
    snapshot = analyse({"BTCUSDT": klines(ramp(20))}, limit=20)
    assert snapshot.metadata["requested_limit"] == 20
    assert snapshot.metadata["candle_policy"] == "closed_only"
    assert snapshot.metadata["relative_value_source_field"] == "close"
    assert "ema_20" in snapshot.metadata["feature_names"]


# ============================ forming-candle exclusion =======================


def test_forming_candle_is_excluded_from_analysis() -> None:
    snapshot = analyse({"BTCUSDT": klines(ramp(21), forming_tail=True)})
    assert snapshot.window.fetched_count == 21
    assert snapshot.window.closed_count == 20
    assert snapshot.window.excluded_forming_count == 1
    # as_of is the last *closed* candle, not the forming one.
    assert snapshot.as_of == _BASE + timedelta(hours=4 * 19)


def test_forming_candle_does_not_change_feature_values() -> None:
    closes = ramp(40)
    with_forming = analyse({"BTCUSDT": klines(closes + [999.0], forming_tail=True)})
    without = analyse({"BTCUSDT": klines(closes)})
    assert with_forming.features.get("ema_20").value == pytest.approx(
        without.features.get("ema_20").value
    )
    assert with_forming.as_of == without.as_of


def test_all_candles_forming_raises_insufficient_data() -> None:
    payload = [kline(i, 100.0 + i, closed=False) for i in range(5)]
    with pytest.raises(InsufficientDataError) as ei:
        analyse({"BTCUSDT": payload})
    assert ei.value.fetched == 5 and ei.value.closed == 0


# ============================ insufficient / empty data ======================


def test_empty_provider_response_raises_insufficient_data() -> None:
    with pytest.raises(InsufficientDataError) as ei:
        analyse({"BTCUSDT": []})
    assert ei.value.subject == "BTCUSDT"
    assert ei.value.fetched == 0 and ei.value.closed == 0


def test_insufficient_data_error_is_a_pipeline_error() -> None:
    assert issubclass(InsufficientDataError, PipelineError)
    assert issubclass(InsufficientDataError, ValueError)


def test_empty_benchmark_response_raises_and_returns_nothing_partial() -> None:
    with pytest.raises(InsufficientDataError) as ei:
        analyse(
            {"BTCUSDT": klines(ramp(40)), "ETHUSDT": []}, benchmark_symbol="ETHUSDT"
        )
    assert ei.value.subject == "ETHUSDT"


def test_too_few_aligned_observations_raises() -> None:
    # Two candles each: enough to analyse alone, too few for the 3-observation
    # v1a volatility/correlation metrics.
    with pytest.raises(InsufficientDataError, match="aligned"):
        analyse(
            {"BTCUSDT": klines(ramp(2)), "ETHUSDT": klines(ramp(2, 50.0))},
            benchmark_symbol="ETHUSDT",
            features=[ExponentialMovingAverage(2)],
        )


# ============================ benchmark comparison ===========================


def test_benchmark_snapshot_has_relative_value_section() -> None:
    snapshot = analyse(
        {"BTCUSDT": klines(ramp(40)), "ETHUSDT": klines(ramp(40, 50.0, 0.5))},
        benchmark_symbol="ETHUSDT",
    )
    assert snapshot.benchmark_symbol == "ETHUSDT"
    section = snapshot.relative_value
    assert isinstance(section, RelativeValueSection)
    assert section.benchmark_symbol == "ETHUSDT"
    assert isinstance(section.alignment, AlignmentReport)


def test_all_five_v1a_metrics_are_present() -> None:
    snapshot = analyse(
        {"BTCUSDT": klines(ramp(40)), "ETHUSDT": klines(ramp(40, 50.0, 0.5))},
        benchmark_symbol="ETHUSDT",
    )
    assert set(snapshot.relative_value.metrics) == {
        "relative_return",
        "volatility_ratio",
        "pearson_correlation",
        "period_return_primary",
        "period_return_benchmark",
        "realized_volatility_primary",
        "realized_volatility_benchmark",
    }


def test_metric_values_match_calling_the_rve_directly() -> None:
    """The pipeline must *reuse* the RVE, not reimplement it."""
    primary_closes, benchmark_closes = ramp(30), ramp(30, 50.0, 0.5)
    snapshot = analyse(
        {"BTCUSDT": klines(primary_closes), "ETHUSDT": klines(benchmark_closes)},
        benchmark_symbol="ETHUSDT",
    )
    # Rebuild the same aligned inputs independently and call the RVE directly.
    from fmis.alignment import align_intersection
    from fmis.providers.binance import fetch_klines

    def series_for(symbol: str, payload: list[list[object]]):
        raw = fetch_klines(
            symbol, "4h",
            transport=routed_transport({symbol: payload}),
            clock=fixed_clock(),
        ).closed()
        return candle_series_to_observations(raw, CandleField.CLOSE)

    left, right = align_intersection(
        (series_for("BTCUSDT", klines(primary_closes)),
         series_for("ETHUSDT", klines(benchmark_closes)))
    ).series

    assert snapshot.relative_value.metrics["relative_return"] == relative_return(
        left, right
    )
    assert snapshot.relative_value.metrics[
        "pearson_correlation"
    ] == pearson_correlation(left, right)


def test_alignment_report_counts_are_exposed() -> None:
    snapshot = analyse(
        {"BTCUSDT": klines(ramp(40)), "ETHUSDT": klines(ramp(40, 50.0, 0.5))},
        benchmark_symbol="ETHUSDT",
    )
    report = snapshot.relative_value.alignment
    assert report.input_series_count == 2
    assert report.aligned_observation_count == 40
    assert report.common_start == _BASE


def test_benchmark_window_is_reported_separately() -> None:
    snapshot = analyse(
        {
            "BTCUSDT": klines(ramp(40)),
            "ETHUSDT": klines(ramp(41, 50.0, 0.5), forming_tail=True),
        },
        benchmark_symbol="ETHUSDT",
    )
    assert snapshot.window.closed_count == 40
    assert snapshot.relative_value.benchmark_window.closed_count == 40
    assert snapshot.relative_value.benchmark_window.excluded_forming_count == 1


def test_undefined_metric_is_passed_through_not_hidden() -> None:
    # A perfectly flat benchmark has zero return variance -> UNDEFINED, not an error.
    snapshot = analyse(
        {"BTCUSDT": klines(ramp(30)), "ETHUSDT": klines([50.0] * 30)},
        benchmark_symbol="ETHUSDT",
    )
    correlation = snapshot.relative_value.metrics["pearson_correlation"]
    assert correlation.status is MetricStatus.UNDEFINED
    assert correlation.value is None
    assert correlation.reason is not None


# ============================ mismatched timestamps / alignment ==============


def test_partially_overlapping_series_are_intersected() -> None:
    # Benchmark starts 10 bars later; only the overlap is compared.
    primary = klines(ramp(30))
    benchmark = [kline(i, 50.0 + i) for i in range(10, 30)]
    snapshot = analyse(
        {"BTCUSDT": primary, "ETHUSDT": benchmark}, benchmark_symbol="ETHUSDT"
    )
    report = snapshot.relative_value.alignment
    assert report.aligned_observation_count == 20
    assert report.common_start == _BASE + timedelta(hours=4 * 10)
    # The primary's own window is untouched by the comparison.
    assert snapshot.window.closed_count == 30


def test_alignment_drop_counts_are_visible() -> None:
    primary = klines(ramp(30))
    benchmark = [kline(i, 50.0 + i) for i in range(10, 30)]
    snapshot = analyse(
        {"BTCUSDT": primary, "ETHUSDT": benchmark}, benchmark_symbol="ETHUSDT"
    )
    stats = {s.series_id: s for s in snapshot.relative_value.alignment.series_stats}
    primary_stats = stats["BTCUSDT.close.4h"]
    assert primary_stats.original_count == 30
    assert primary_stats.aligned_count == 20
    assert primary_stats.dropped_count == 10


def test_disjoint_series_raise_rather_than_analysing_nothing() -> None:
    primary = klines(ramp(10))
    benchmark = [kline(i, 50.0 + i) for i in range(100, 110)]
    with pytest.raises(InsufficientDataError, match="aligned"):
        analyse(
            {"BTCUSDT": primary, "ETHUSDT": benchmark},
            benchmark_symbol="ETHUSDT",
            features=[ExponentialMovingAverage(5)],
        )


# ============================ error propagation ==============================


def test_provider_api_error_propagates() -> None:
    def transport(url: str) -> HttpResponse:
        error = {"code": -1121, "msg": "Invalid symbol."}
        return HttpResponse(status=400, body=json.dumps(error).encode())

    with pytest.raises(BinanceAPIError):
        analyze_symbol("BTCUSDT", "4h", transport=transport, clock=fixed_clock())


def test_provider_transport_error_propagates() -> None:
    def transport(url: str) -> HttpResponse:
        raise BinanceTransportError("connection refused")

    with pytest.raises(BinanceTransportError):
        analyze_symbol("BTCUSDT", "4h", transport=transport, clock=fixed_clock())


def test_provider_response_error_propagates() -> None:
    with pytest.raises(BinanceResponseError):
        analyse({"BTCUSDT": [[1, 2, 3]]})


def test_ingestion_error_propagates() -> None:
    # high below close violates a canonical invariant, owned by Candle.
    broken = kline(0, 100.0)
    broken[2] = "1.0"
    with pytest.raises(IngestError):
        analyse({"BTCUSDT": [broken]})


def test_feature_engine_error_propagates() -> None:
    with pytest.raises(ValueError, match="unknown feature"):
        analyse({"BTCUSDT": klines(ramp(30))}, features=[_UnregisteredDependency()])


class _UnregisteredDependency(ExponentialMovingAverage):
    """A feature declaring a dependency the registry does not contain."""

    def __init__(self) -> None:
        super().__init__(5)
        self.dependencies = ("does_not_exist",)


def test_benchmark_failure_does_not_yield_a_technical_only_snapshot() -> None:
    def transport(url: str) -> HttpResponse:
        if "ETHUSDT" in url:
            return HttpResponse(status=503, body=b"[]")
        return HttpResponse(status=200, body=json.dumps(klines(ramp(40))).encode())

    with pytest.raises(BinanceAPIError):
        analyze_symbol(
            "BTCUSDT", "4h", benchmark_symbol="ETHUSDT",
            transport=transport, clock=fixed_clock(),
        )


def test_invalid_arguments_fail_before_any_fetch() -> None:
    sent = routed_transport({"BTCUSDT": klines(ramp(10))})
    with pytest.raises(ValueError):
        analyze_symbol("btcusdt", "4h", transport=sent, clock=fixed_clock())
    assert sent.calls == []  # type: ignore[attr-defined]


# ============================ determinism / immutability =====================


def test_repeated_analysis_is_deterministic() -> None:
    payload = {"BTCUSDT": klines(ramp(40)), "ETHUSDT": klines(ramp(40, 50.0, 0.5))}
    first = analyse(payload, benchmark_symbol="ETHUSDT")
    second = analyse(payload, benchmark_symbol="ETHUSDT")
    assert first.as_of == second.as_of
    assert first.window == second.window
    for name in first.features.features:
        assert first.features.get(name).value == second.features.get(name).value
    for key, result in first.relative_value.metrics.items():
        assert result == second.relative_value.metrics[key]


def test_provider_payload_is_not_mutated() -> None:
    payload = klines(ramp(30))
    before = json.dumps(payload)
    analyse({"BTCUSDT": payload})
    assert json.dumps(payload) == before


def test_supplied_feature_sequence_is_not_mutated() -> None:
    features = [ExponentialMovingAverage(10), RelativeStrengthIndex(14)]
    snapshot_names = [f.name for f in features]
    analyse({"BTCUSDT": klines(ramp(30))}, features=features)
    assert [f.name for f in features] == snapshot_names
    assert len(features) == 2


def test_default_features_returns_fresh_instances() -> None:
    first, second = default_features(), default_features()
    assert [f.name for f in first] == [f.name for f in second]
    assert all(a is not b for a, b in zip(first, second))


def test_snapshot_is_frozen() -> None:
    snapshot = analyse({"BTCUSDT": klines(ramp(20))})
    with pytest.raises(AttributeError):
        snapshot.symbol = "ETHUSDT"  # type: ignore[misc]


def test_snapshot_metadata_is_read_only() -> None:
    snapshot = analyse({"BTCUSDT": klines(ramp(20))})
    with pytest.raises(TypeError):
        snapshot.metadata["candle_policy"] = "anything"  # type: ignore[index]


def test_relative_value_metrics_mapping_is_read_only() -> None:
    snapshot = analyse(
        {"BTCUSDT": klines(ramp(30)), "ETHUSDT": klines(ramp(30, 50.0, 0.5))},
        benchmark_symbol="ETHUSDT",
    )
    with pytest.raises(TypeError):
        snapshot.relative_value.metrics["relative_return"] = None  # type: ignore[index]


def test_snapshot_feature_mapping_is_read_only() -> None:
    # AnalysisSnapshot claims defensively protected results; the FeatureSet it
    # carries must honour that too.
    snapshot = analyse({"BTCUSDT": klines(ramp(40))})
    with pytest.raises(TypeError):
        snapshot.features.features["injected"] = None  # type: ignore[index]


def test_snapshot_feature_mapping_order_is_deterministic() -> None:
    payload = {"BTCUSDT": klines(ramp(40))}
    first = analyse(payload)
    second = analyse(payload)
    assert list(first.features.features) == list(second.features.features)


def test_feature_sets_compare_equal_across_identical_runs() -> None:
    payload = {"BTCUSDT": klines(ramp(40))}
    assert analyse(payload).features == analyse(payload).features


def test_window_is_frozen() -> None:
    snapshot = analyse({"BTCUSDT": klines(ramp(20))})
    with pytest.raises(AttributeError):
        snapshot.window.closed_count = 0  # type: ignore[misc]


# ============================ fact-only / no interpretation ==================


def test_no_directional_vocabulary_in_output() -> None:
    snapshot = analyse(
        {"BTCUSDT": klines(ramp(40)), "ETHUSDT": klines(ramp(40, 50.0, 0.5))},
        benchmark_symbol="ETHUSDT",
    )
    blob = " ".join(
        [
            repr({k: str(v) for k, v in snapshot.metadata.items()}),
            repr(list(snapshot.relative_value.metrics)),
            repr(sorted(snapshot.features.features)),
        ]
    ).lower()
    for banned in ("long", "short", "buy", "sell", "bull", "bear", "score",
                   "signal", "confidence", "recommend", "target", "entry"):
        assert banned not in blob, banned


# ============================ no reimplemented math ==========================


def test_pipeline_module_contains_no_arithmetic() -> None:
    """Orchestration only: every number must come from an engine, not from here.

    Subtraction is permitted in exactly one place — deriving the excluded-candle
    count from two lengths, which is bookkeeping, not a market calculation.
    """
    source = Path(pipeline.market_analysis.__file__).read_text()
    tree = ast.parse(source)
    operators = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.BinOp)
        and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div,
                                 ast.FloorDiv, ast.Pow, ast.Mod))
    ]
    assert len(operators) == 1
    assert isinstance(operators[0].op, ast.Sub)


def test_pipeline_does_not_import_indicator_math_kernels() -> None:
    imports = _internal_imports(Path(pipeline.__file__).parent)
    for forbidden in ("fmis.features.indicators.ema_math",
                      "fmis.features.indicators.sources"):
        assert forbidden not in imports


def test_no_numeric_library_use() -> None:
    """No math/statistics import: a real calculation here would need one."""
    tree = ast.parse(Path(pipeline.market_analysis.__file__).read_text())
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
    for forbidden in ("math", "statistics", "decimal", "fractions"):
        assert forbidden not in roots, forbidden


def test_pipeline_calls_every_rve_metric_by_name() -> None:
    """Each metric key maps to a real RVE function call, not a local computation."""
    tree = ast.parse(Path(pipeline.market_analysis.__file__).read_text())
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for metric in ("relative_return", "volatility_ratio", "pearson_correlation",
                   "period_return", "realized_volatility"):
        assert metric in called, metric


# ============================ public API / boundaries ========================


def test_public_api_exports() -> None:
    for name in (
        "analyze_symbol", "default_features", "AnalysisSnapshot", "DataWindow",
        "RelativeValueSection", "PipelineError", "InsufficientDataError",
    ):
        assert name in pipeline.__all__
        assert hasattr(pipeline, name)


def _internal_imports(pkg_dir: Path) -> set[str]:
    found: set[str] = set()
    for py in pkg_dir.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("fmis"):
                    found.add(node.module)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.startswith("fmis"):
                        found.add(a.name)
    return found


#: The engine packages, all of which sit *below* the application layer. Layers
#: above it (e.g. fmis.decision_support) may consume its result types; these
#: may not, in either direction of reasoning.
ENGINE_PACKAGES = (
    "data", "ingest", "providers", "features", "alignment", "relative_value",
)


def test_no_engine_imports_the_application_layer() -> None:
    """The arrow points one way: engines never depend on what orchestrates them."""
    src = Path(pipeline.__file__).parent.parent  # src/fmis
    offenders: list[str] = []
    for package in ENGINE_PACKAGES:
        for py in (src / package).rglob("*.py"):
            if "fmis.pipeline" in py.read_text():
                offenders.append(str(py))
    assert offenders == []


def test_engine_packages_scanned_actually_exist() -> None:
    # Guards the test above from silently passing if a package is renamed.
    src = Path(pipeline.__file__).parent.parent
    for package in ENGINE_PACKAGES:
        assert (src / package / "__init__.py").is_file(), package


def test_pipeline_reuses_engines_rather_than_reaching_around_them() -> None:
    imports = _internal_imports(Path(pipeline.__file__).parent)
    # It orchestrates every layer...
    for expected in ("fmis.providers.binance", "fmis.relative_value", "fmis.alignment"):
        assert any(i.startswith(expected) for i in imports), expected
    # ...and never touches a private module.
    assert not any("._" in i or i.endswith("_timeutils") for i in imports)


def test_importing_an_engine_does_not_load_pipeline(
    fresh_fmis_imports: None,
) -> None:
    import fmis.features  # noqa: F401

    assert not any(m.startswith("fmis.pipeline") for m in sys.modules)


def test_importing_pipeline_loads_full_stack(fresh_fmis_imports: None) -> None:
    import fmis.pipeline  # noqa: F401

    for expected in ("fmis.data", "fmis.ingest", "fmis.providers.binance",
                     "fmis.features", "fmis.alignment", "fmis.relative_value"):
        assert expected in sys.modules, expected
