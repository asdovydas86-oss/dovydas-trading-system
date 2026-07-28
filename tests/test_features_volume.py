"""Tests for the deterministic volume foundation (fmis.features.volume).

Expected values are hand-derived, never taken from the implementation. The
central property under test is the window convention: the latest candle is
compared against a baseline it is **not** part of.
"""

from __future__ import annotations

import ast
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import fmis.features.volume as volume_pkg
from fmis.data import Candle, CandleSeries
from fmis.features import FeatureCategory, FeatureContext, FeatureRegistry
from fmis.features.feature_engine import FeatureEngine
from fmis.features.volume import AverageVolume, RelativeVolume, trailing_mean
from fmis.features.volume.statistics import ZERO_BASELINE

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
SRC = Path(volume_pkg.__file__).parent.parent.parent  # src/fmis


def series(volumes: list[float], *, closed: bool = True) -> CandleSeries:
    """A candle series whose only varying field is volume."""
    return CandleSeries(
        symbol="BTCUSDT",
        timeframe="4h",
        candles=tuple(
            Candle(
                timestamp=_BASE + timedelta(hours=4 * i),
                symbol="BTCUSDT",
                timeframe="4h",
                open=100.0, high=100.0, low=100.0, close=100.0,
                volume=v,
                is_closed=closed,
            )
            for i, v in enumerate(volumes)
        ),
    )


def compute(feature, volumes: list[float], **kwargs):
    return feature.compute(FeatureContext(primary=series(volumes, **kwargs)))


# ============================ trailing_mean kernel ===========================


def test_trailing_mean_excludes_the_last_value() -> None:
    # Baseline is v6,v7,v8 -> mean 3.0; v9 is excluded even though it is huge.
    values = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0, 3.0, 4.0, 999.0]
    assert trailing_mean(values, 3) == pytest.approx(3.0)


def test_trailing_mean_exactly_enough_values() -> None:
    assert trailing_mean([1.0, 2.0, 3.0, 99.0], 3) == pytest.approx(2.0)


def test_trailing_mean_one_short_is_none() -> None:
    assert trailing_mean([1.0, 2.0, 3.0], 3) is None


def test_trailing_mean_empty_is_none() -> None:
    assert trailing_mean([], 1) is None


def test_trailing_mean_lookback_one() -> None:
    assert trailing_mean([7.0, 99.0], 1) == pytest.approx(7.0)


def test_trailing_mean_rejects_non_positive_lookback() -> None:
    for bad in (0, -1):
        with pytest.raises(ValueError, match="lookback must be at least 1"):
            trailing_mean([1.0, 2.0], bad)


def test_trailing_mean_does_not_mutate_input() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    before = list(values)
    trailing_mean(values, 2)
    assert values == before


# ============================ AverageVolume ==================================


def test_average_volume_known_value() -> None:
    # Baseline = mean(10, 20, 30) = 20; the trailing 999 is excluded.
    result = compute(AverageVolume(3), [10.0, 20.0, 30.0, 999.0])
    assert result.value == pytest.approx(20.0)
    assert result.metadata["insufficient_data"] is False
    assert result.category is FeatureCategory.VOLUME


def test_average_volume_name_encodes_lookback() -> None:
    assert AverageVolume(20).name == "average_volume_20"
    assert AverageVolume(5).name == "average_volume_5"


def test_average_volume_insufficient_history() -> None:
    result = compute(AverageVolume(3), [10.0, 20.0, 30.0])  # need 4
    assert result.value is None
    assert result.metadata["insufficient_data"] is True
    assert result.metadata["required_candles"] == 4


def test_average_volume_empty_series() -> None:
    result = compute(AverageVolume(3), [])
    assert result.value is None
    assert result.metadata["insufficient_data"] is True
    assert result.metadata["closed_candles_available"] == 0


def test_average_volume_ignores_forming_candles() -> None:
    # A forming candle must not enter the baseline.
    closed_only = compute(AverageVolume(3), [10.0, 20.0, 30.0, 40.0])
    with_forming = AverageVolume(3).compute(
        FeatureContext(
            primary=CandleSeries(
                symbol="BTCUSDT",
                timeframe="4h",
                candles=series([10.0, 20.0, 30.0, 40.0]).candles
                + series([999.0], closed=False).candles[:0],
            )
        )
    )
    assert closed_only.value == with_forming.value == pytest.approx(20.0)


# ============================ RelativeVolume =================================


def test_relative_volume_known_value() -> None:
    # baseline mean(10,20,30) = 20 ; current 40 -> 2.0
    result = compute(RelativeVolume(3), [10.0, 20.0, 30.0, 40.0])
    assert result.value == pytest.approx(2.0)
    assert result.metadata["current_volume"] == pytest.approx(40.0)
    assert result.metadata["average_volume"] == pytest.approx(20.0)


def test_relative_volume_current_candle_excluded_from_its_own_baseline() -> None:
    """The defining property of this milestone.

    With volumes [1, 1, 1, 999] and lookback 3 the baseline is mean(1,1,1) = 1,
    so the ratio is 999. Had the current candle been included the baseline would
    be mean(1,1,999) = 333.67 and the ratio ~2.99 — the spike would have hidden
    itself inside its own comparison.
    """
    result = compute(RelativeVolume(3), [1.0, 1.0, 1.0, 999.0])
    assert result.value == pytest.approx(999.0)
    assert result.value != pytest.approx(999.0 / ((1.0 + 1.0 + 999.0) / 3))


def test_relative_volume_of_one_when_volume_matches_baseline() -> None:
    assert compute(RelativeVolume(3), [50.0] * 4).value == pytest.approx(1.0)


def test_relative_volume_exactly_lookback_plus_one_candles() -> None:
    result = compute(RelativeVolume(4), [10.0, 10.0, 10.0, 10.0, 25.0])
    assert result.value == pytest.approx(2.5)
    assert result.metadata["closed_candles_available"] == 5


def test_relative_volume_more_than_enough_candles_uses_only_the_window() -> None:
    # Ancient history must not affect the baseline.
    older = [1_000_000.0] * 30
    result = compute(RelativeVolume(3), older + [10.0, 10.0, 10.0, 30.0])
    assert result.value == pytest.approx(3.0)


def test_relative_volume_zero_current_volume_is_zero_not_undefined() -> None:
    result = compute(RelativeVolume(3), [10.0, 20.0, 30.0, 0.0])
    assert result.value == 0.0
    assert result.metadata["insufficient_data"] is False
    assert "undefined_reason" not in result.metadata


def test_relative_volume_zero_baseline_is_undefined_not_infinite() -> None:
    # A halted or untraded window: no denominator, so no value — and no infinity.
    result = compute(RelativeVolume(3), [0.0, 0.0, 0.0, 500.0])
    assert result.value is None
    assert result.metadata["insufficient_data"] is False  # warm-up was satisfied
    assert result.metadata["undefined_reason"] == ZERO_BASELINE
    assert result.metadata["average_volume"] == 0.0
    assert result.metadata["current_volume"] == pytest.approx(500.0)


def test_relative_volume_zero_baseline_and_zero_current_is_still_undefined() -> None:
    result = compute(RelativeVolume(3), [0.0, 0.0, 0.0, 0.0])
    assert result.value is None
    assert result.metadata["undefined_reason"] == ZERO_BASELINE


def test_relative_volume_insufficient_history() -> None:
    result = compute(RelativeVolume(20), [100.0] * 20)  # need 21
    assert result.value is None
    assert result.metadata["insufficient_data"] is True
    assert "undefined_reason" not in result.metadata


def test_relative_volume_one_candle_short_then_exactly_enough() -> None:
    assert compute(RelativeVolume(5), [10.0] * 5).value is None
    assert compute(RelativeVolume(5), [10.0] * 6).value == pytest.approx(1.0)


def test_relative_volume_empty_series() -> None:
    result = compute(RelativeVolume(3), [])
    assert result.value is None
    assert result.metadata["insufficient_data"] is True


def test_three_outcomes_are_distinguishable() -> None:
    calculated = compute(RelativeVolume(3), [10.0, 10.0, 10.0, 20.0])
    warming = compute(RelativeVolume(3), [10.0, 10.0])
    undefined = compute(RelativeVolume(3), [0.0, 0.0, 0.0, 5.0])

    assert (calculated.value is not None)
    assert (warming.value is None and warming.metadata["insufficient_data"] is True)
    assert (
        undefined.value is None
        and undefined.metadata["insufficient_data"] is False
        and undefined.metadata["undefined_reason"] == ZERO_BASELINE
    )


def test_relative_volume_name_encodes_lookback() -> None:
    assert RelativeVolume(20).name == "relative_volume_20"


def test_default_lookback_is_twenty() -> None:
    assert AverageVolume().lookback == 20
    assert RelativeVolume().lookback == 20
    assert RelativeVolume().name == "relative_volume_20"


# ============================ shared arithmetic ==============================


def test_both_features_agree_on_the_baseline() -> None:
    volumes = [3.0, 9.0, 15.0, 21.0, 60.0]
    average = compute(AverageVolume(4), volumes)
    relative = compute(RelativeVolume(4), volumes)
    assert relative.metadata["average_volume"] == pytest.approx(average.value)
    assert relative.value == pytest.approx(60.0 / average.value)


def test_metadata_records_the_window_convention() -> None:
    for feature in (AverageVolume(7), RelativeVolume(7)):
        metadata = compute(feature, [10.0] * 10).metadata
        assert metadata["lookback"] == 7
        assert metadata["warmup_candles"] == 8
        assert metadata["current_candle_excluded_from_baseline"] is True
        assert metadata["source"] == "volume"


# ============================ lookback validation ============================


@pytest.mark.parametrize("feature_cls", [AverageVolume, RelativeVolume])
@pytest.mark.parametrize("bad", [0, -1, -20])
def test_non_positive_lookback_rejected(feature_cls, bad: int) -> None:
    with pytest.raises(ValueError, match="lookback must be at least 1"):
        feature_cls(bad)


@pytest.mark.parametrize("feature_cls", [AverageVolume, RelativeVolume])
@pytest.mark.parametrize("bad", [True, 2.5, "20", None])
def test_non_int_lookback_rejected(feature_cls, bad) -> None:
    with pytest.raises(TypeError, match="lookback must be an int"):
        feature_cls(bad)


# ============================ inherited volume validation ====================


def test_negative_volume_rejected_by_the_canonical_model() -> None:
    # Reused guarantee, not re-implemented: Candle owns this rule.
    with pytest.raises(ValueError, match="volume cannot be negative"):
        series([10.0, -1.0])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_volume_rejected_by_the_canonical_model(bad: float) -> None:
    with pytest.raises(ValueError, match="volume must be a finite number"):
        series([10.0, bad])


def test_zero_volume_is_valid_data() -> None:
    assert series([0.0, 0.0]).candles[0].volume == 0.0


def test_volume_features_do_not_revalidate_volume() -> None:
    # No volume validation strings in the package: the model already owns them.
    for py in sorted(Path(volume_pkg.__file__).parent.glob("*.py")):
        source = py.read_text()
        assert "cannot be negative" not in source, py.name
        assert "must be a finite number" not in source, py.name


# ============================ determinism / immutability =====================


def test_repeated_computation_is_deterministic() -> None:
    volumes = [11.0, 22.0, 33.0, 44.0, 55.0]
    first = compute(RelativeVolume(4), volumes)
    second = compute(RelativeVolume(4), volumes)
    assert first.value == second.value
    assert dict(first.metadata) == dict(second.metadata)


def test_results_are_immutable() -> None:
    result = compute(RelativeVolume(3), [10.0, 10.0, 10.0, 20.0])
    with pytest.raises(AttributeError):
        result.value = 99.0  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.metadata["lookback"] = 99  # type: ignore[index]


def test_input_series_is_not_mutated() -> None:
    candles = series([10.0, 20.0, 30.0, 40.0])
    before = tuple(c.volume for c in candles.candles)
    RelativeVolume(3).compute(FeatureContext(primary=candles))
    assert tuple(c.volume for c in candles.candles) == before


# ============================ engine integration =============================


def test_features_run_through_the_engine() -> None:
    registry = FeatureRegistry()
    registry.register(AverageVolume(3))
    registry.register(RelativeVolume(3))
    feature_set = FeatureEngine(registry).compute(series([10.0, 20.0, 30.0, 40.0]))

    assert feature_set.get("average_volume_3").value == pytest.approx(20.0)
    assert feature_set.get("relative_volume_3").value == pytest.approx(2.0)
    assert len(feature_set.by_category(FeatureCategory.VOLUME)) == 2


def test_relative_volume_is_in_the_default_feature_set() -> None:
    from fmis.pipeline import default_features

    names = {f.name for f in default_features()}
    assert "relative_volume_20" in names


def test_average_volume_is_registerable_but_not_a_default() -> None:
    from fmis.pipeline import default_features

    names = {f.name for f in default_features()}
    assert "average_volume_20" not in names  # its numbers ride in relative's metadata


# ============================ architecture: one authority ====================


def _volume_sources() -> list[Path]:
    return sorted(Path(volume_pkg.__file__).parent.glob("*.py"))


def _divisions(path: Path) -> list[ast.BinOp]:
    return [
        node for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
    ]


def test_the_mean_is_computed_in_exactly_one_module() -> None:
    divisions = {py.name: len(_divisions(py)) for py in _volume_sources()}
    assert divisions["volume_math.py"] == 1  # sum(window) / lookback
    assert divisions["statistics.py"] == 1   # current / baseline
    assert divisions["__init__.py"] == 0


def test_statistics_delegates_the_baseline_to_the_kernel() -> None:
    tree = ast.parse((Path(volume_pkg.__file__).parent / "statistics.py").read_text())
    called = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "trailing_mean" in called


@pytest.mark.parametrize(
    "package",
    ["pipeline", "decision_support", "providers", "ingest", "data",
     "alignment", "relative_value"],
)
def test_no_other_package_recomputes_relative_volume(package: str) -> None:
    """Only the volume package may compute a volume baseline or ratio.

    Instantiating the feature is fine and expected; re-deriving its arithmetic
    is not. Referring to it in prose is neither.
    """
    for py in (SRC / package).rglob("*.py"):
        tokens = _code_tokens(py)
        for marker in ("average_volume", "trailing_mean", "relative_volume",
                       "avg_volume", "volume_ratio"):
            assert marker not in tokens, f"{py}: {marker}"


def test_scanned_packages_actually_exist() -> None:
    # Guards the scan above from silently passing if a package is renamed.
    for package in ("pipeline", "decision_support", "providers", "ingest", "data",
                    "alignment", "relative_value"):
        assert (SRC / package / "__init__.py").is_file(), package


def test_pipeline_references_volume_only_through_the_feature_mechanism() -> None:
    source = (SRC / "pipeline" / "market_analysis.py").read_text()
    tree = ast.parse(source)
    # It may import and instantiate the feature...
    assert "RelativeVolume" in source
    # ...but must not branch on volume or read a volume value itself.
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr != "volume", "pipeline reads candle volume directly"
    assert "relative_volume" not in source.replace("RelativeVolume", "")


def test_provider_adapter_computes_no_volume_indicator() -> None:
    source = (SRC / "providers" / "binance.py").read_text()
    for marker in ("average", "relative_volume", "trailing_mean", "mean("):
        assert marker not in source, marker


# ============================ architecture: boundaries =======================


def _code_tokens(path: Path) -> set[str]:
    """Identifiers and non-docstring string values in one module.

    Docstrings are excluded deliberately. This package's documentation has to
    *name* the things it does not do — thresholds, labels, and the very markets
    whose interpretations differ — and a raw-text scan would read that prose as
    the violation it is warning against. Only code can embody a rule.
    """
    tree = ast.parse(path.read_text())
    docstrings = {
        d for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and (d := ast.get_docstring(node, clean=False)) is not None
    }
    tokens: set[str] = set()

    def add(text: str) -> None:
        # `tokens.update(...)`, not `tokens |= ...`: an augmented assignment would
        # rebind `tokens` as a local of this closure.
        lowered = text.lower()
        tokens.add(lowered)
        tokens.update(lowered.replace("_", " ").split())

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value not in docstrings:
                add(node.value)
        elif isinstance(node, ast.Name):
            add(node.id)
        elif isinstance(node, ast.Attribute):
            add(node.attr)
        elif isinstance(node, ast.arg):
            add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            add(node.name)
        elif isinstance(node, ast.keyword) and node.arg:
            add(node.arg)
    return tokens


def _internal_imports() -> set[str]:
    found: set[str] = set()
    for py in _volume_sources():
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("fmis"):
                    found.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("fmis"):
                        found.add(alias.name)
    return found


@pytest.mark.parametrize(
    "forbidden",
    ["fmis.pipeline", "fmis.decision_support", "fmis.providers", "fmis.ingest",
     "fmis.alignment", "fmis.relative_value", "fmis.trading_context"],
)
def test_volume_package_depends_on_no_higher_or_sibling_layer(forbidden: str) -> None:
    assert not any(i.startswith(forbidden) for i in _internal_imports()), forbidden


def test_volume_package_imports_only_feature_types_and_its_own_kernel() -> None:
    assert _internal_imports() <= {
        "fmis.features.types",
        "fmis.features.volume.statistics",
        "fmis.features.volume.volume_math",
    }


def test_kernel_imports_nothing_internal() -> None:
    kernel = Path(volume_pkg.__file__).parent / "volume_math.py"
    for node in ast.walk(ast.parse(kernel.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("fmis"), node.module


def test_no_third_party_or_network_dependency() -> None:
    roots: set[str] = set()
    for py in _volume_sources():
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                roots |= {a.name.split(".")[0] for a in node.names}
    assert roots <= set(sys.stdlib_module_names) | {"fmis"}
    for forbidden in ("urllib", "http", "socket", "requests", "openai", "anthropic"):
        assert forbidden not in roots, forbidden


def test_no_provider_or_market_specific_vocabulary() -> None:
    """Market-agnostic in code: no exchange, symbol, or session assumptions.

    The package docstring names several markets on purpose — to record that the
    calculation is shared while the interpretation is not — so only code counts.
    """
    for py in _volume_sources():
        tokens = _code_tokens(py)
        for marker in ("binance", "btcusdt", "usdt", "kline", "hkex", "nasdaq",
                       "shanghai", "shenzhen", "session", "auction", "endpoint"):
            assert marker not in tokens, f"{py.name}: {marker}"


def test_public_api_exports() -> None:
    assert set(volume_pkg.__all__) == {
        "AverageVolume", "RelativeVolume", "trailing_mean", "required_values",
    }
    for name in volume_pkg.__all__:
        assert hasattr(volume_pkg, name)


# ============================ no interpretation ==============================


def test_no_trading_action_or_label_vocabulary() -> None:
    banned = (
        "buy", "sell", "long", "short", "bullish", "bearish", "entry", "exit",
        "stop", "target", "confidence", "signal", "score", "strategy",
        "breakout", "breakdown", "accumulation", "distribution", "divergence",
        "high_volume", "low_volume", "strong", "weak", "confirmed",
    )
    for py in _volume_sources():
        tokens = _code_tokens(py)
        for word in banned:
            assert word not in tokens, f"{py.name}: {word}"


def test_result_values_are_bare_numbers_not_labels() -> None:
    for volumes in ([10.0, 10.0, 10.0, 40.0], [10.0] * 4, [0.0, 0.0, 0.0, 1.0]):
        result = compute(RelativeVolume(3), volumes)
        assert result.value is None or isinstance(result.value, float)


def test_no_thresholds_are_defined() -> None:
    # A threshold constant would be an interpretation smuggled in as data.
    for py in _volume_sources():
        tokens = _code_tokens(py)
        for marker in ("threshold", "elevated", "spike", "unusual", "notable",
                       "significant"):
            assert marker not in tokens, f"{py.name}: {marker}"
