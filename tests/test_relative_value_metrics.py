"""Tests for RVE v1a metrics (fmis.relative_value.metrics).

Expected values are hand-derived, never taken from the implementation. Worked
anchors used throughout:

    L  = [100, 110,  99]   -> simple returns [ 0.10, -0.10]
    R  = [100,  90,  99]   -> simple returns [-0.10,  0.10]   (exact opposite of L)
    RR = [100, 105, 99.75] -> simple returns [ 0.05, -0.05]
    F  = [100, 100, 100]   -> simple returns [ 0.00,  0.00]   (constant)

    sample stdev (Bessel, m-1) of [0.1, -0.1] : mean 0, ss 0.02, var 0.02 -> sqrt(0.02)
    sample stdev of [0.05, -0.05]             : var 0.005          -> sqrt(0.005)
    volatility_ratio(L, RR) = sqrt(0.02)/sqrt(0.005) = sqrt(4) = 2.0
    pearson_correlation(L, R) = -1 ; (L, L) = +1
"""

from __future__ import annotations

import ast
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import fmis.relative_value as rv
from fmis.alignment import align_intersection
from fmis.data import CandleField, ObservationSeries, candle_series_to_observations
from fmis.data.models import Candle, CandleSeries
from fmis.relative_value import (
    InsufficientObservationsError,
    MetricStatus,
    NotAlignedError,
    UndefinedReason,
    pearson_correlation,
    period_return,
    realized_volatility,
    relative_return,
    volatility_ratio,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
_REL_TOL = 1e-12


def obs(
    series_id: str,
    values: list[float],
    *,
    unit: str = "price",
    frequency: str = "1D",
    day_offsets: list[int] | None = None,
) -> ObservationSeries:
    offs = day_offsets if day_offsets is not None else list(range(len(values)))
    return ObservationSeries(
        series_id=series_id,
        unit=unit,
        frequency=frequency,
        timestamps=tuple(_BASE + timedelta(days=d) for d in offs),
        values=tuple(values),
    )


# ============================ period_return ==================================


def test_period_return_basic() -> None:
    r = period_return(obs("A", [100.0, 150.0]))
    assert r.status is MetricStatus.OK
    assert r.value == pytest.approx(0.5, rel=_REL_TOL)


def test_period_return_multi_step() -> None:
    assert period_return(obs("A", [100.0, 110.0, 121.0])).value == pytest.approx(
        0.21, rel=_REL_TOL
    )


def test_period_return_scale_invariance() -> None:
    a = period_return(obs("A", [1.0, 2.0])).value
    b = period_return(obs("B", [1000.0, 2000.0])).value
    assert a == pytest.approx(1.0, rel=_REL_TOL)
    assert b == pytest.approx(1.0, rel=_REL_TOL)


def test_period_return_negative_levels_allowed() -> None:
    # ObservationSeries permits negative values; P_last/P_first is still defined.
    r = period_return(obs("A", [-100.0, -50.0]))
    assert r.value == pytest.approx(-0.5, rel=_REL_TOL)


def test_period_return_zero_denominator() -> None:
    r = period_return(obs("A", [0.0, 100.0]))
    assert r.status is MetricStatus.UNDEFINED
    assert r.value is None
    assert r.reason is UndefinedReason.ZERO_DENOMINATOR


def test_period_return_insufficient_one_short() -> None:
    with pytest.raises(InsufficientObservationsError) as ei:
        period_return(obs("A", [100.0]))
    assert ei.value.required == 2 and ei.value.actual == 1


def test_period_return_exactly_enough() -> None:
    assert period_return(obs("A", [100.0, 150.0])).status is MetricStatus.OK


def test_period_return_wrong_type() -> None:
    with pytest.raises(TypeError, match="series must be an ObservationSeries"):
        period_return([100.0, 150.0])  # type: ignore[arg-type]


# ============================ relative_return ================================


def test_relative_return_basic() -> None:
    left = obs("L", [100.0, 121.0])   # R_left = 0.21
    right = obs("R", [100.0, 100.0])  # R_right = 0.0
    r = relative_return(left, right)
    assert r.status is MetricStatus.OK
    assert r.value == pytest.approx(0.21, rel=_REL_TOL)


def test_relative_return_exact_fraction() -> None:
    # (1.10 / 1.05) - 1 = 22/21 - 1 = 1/21
    r = relative_return(obs("L", [100.0, 110.0]), obs("R", [100.0, 105.0]))
    assert r.value == pytest.approx(1.0 / 21.0, rel=_REL_TOL)


def test_relative_return_left_first_zero() -> None:
    r = relative_return(obs("L", [0.0, 100.0]), obs("R", [100.0, 110.0]))
    assert r.status is MetricStatus.UNDEFINED
    assert r.reason is UndefinedReason.ZERO_DENOMINATOR


def test_relative_return_right_last_zero() -> None:
    # 1 + R_right == right_last/right_first == 0
    r = relative_return(obs("L", [100.0, 110.0]), obs("R", [100.0, 0.0]))
    assert r.status is MetricStatus.UNDEFINED
    assert r.reason is UndefinedReason.ZERO_DENOMINATOR


def test_relative_return_ordering_in_metadata() -> None:
    r = relative_return(obs("L", [100.0, 121.0]), obs("R", [100.0, 100.0]))
    assert r.metadata["source_series_ids"] == ("L", "R")


def test_relative_return_insufficient_one_short() -> None:
    with pytest.raises(InsufficientObservationsError):
        relative_return(obs("L", [100.0]), obs("R", [100.0]))


# ============================ realized_volatility ============================


def test_realized_volatility_value() -> None:
    r = realized_volatility(obs("L", [100.0, 110.0, 99.0]))
    assert r.status is MetricStatus.OK
    assert r.value == pytest.approx(math.sqrt(0.02), rel=_REL_TOL)


def test_realized_volatility_uses_bessel_correction() -> None:
    # Returns [0.1, -0.1]: population sd = 0.1, sample (Bessel) sd = sqrt(0.02).
    val = realized_volatility(obs("L", [100.0, 110.0, 99.0])).value
    assert val == pytest.approx(math.sqrt(0.02), rel=_REL_TOL)
    assert val != pytest.approx(0.1, rel=1e-6)  # not the population sd


def test_realized_volatility_constant_returns_is_zero() -> None:
    r = realized_volatility(obs("A", [100.0, 110.0, 121.0]))  # returns [0.1, 0.1]
    assert r.status is MetricStatus.OK
    assert r.value == pytest.approx(0.0, abs=1e-15)


def test_realized_volatility_constant_series_is_zero() -> None:
    r = realized_volatility(obs("F", [100.0, 100.0, 100.0]))
    assert r.status is MetricStatus.OK
    assert r.value == 0.0


def test_realized_volatility_interior_zero_price_undefined() -> None:
    r = realized_volatility(obs("A", [100.0, 0.0, 100.0]))
    assert r.status is MetricStatus.UNDEFINED
    assert r.reason is UndefinedReason.ZERO_DENOMINATOR


def test_realized_volatility_insufficient_one_short() -> None:
    with pytest.raises(InsufficientObservationsError) as ei:
        realized_volatility(obs("A", [100.0, 110.0]))
    assert ei.value.required == 3 and ei.value.actual == 2


def test_realized_volatility_exactly_enough() -> None:
    assert realized_volatility(obs("A", [100.0, 110.0, 99.0])).status is MetricStatus.OK


def test_realized_volatility_not_annualized() -> None:
    r = realized_volatility(obs("L", [100.0, 110.0, 99.0]))
    assert r.metadata["annualized"] is False
    assert r.metadata["standard_deviation"] == "sample_bessel"
    # value is the per-period sd, not multiplied by any sqrt(periods-per-year)
    assert r.value == pytest.approx(math.sqrt(0.02), rel=_REL_TOL)


# ============================ volatility_ratio ===============================


def test_volatility_ratio_value() -> None:
    r = volatility_ratio(obs("L", [100.0, 110.0, 99.0]), obs("R", [100.0, 105.0, 99.75]))
    assert r.status is MetricStatus.OK
    assert r.value == pytest.approx(2.0, rel=_REL_TOL)


def test_volatility_ratio_zero_reference_volatility() -> None:
    r = volatility_ratio(obs("L", [100.0, 110.0, 99.0]), obs("F", [100.0, 100.0, 100.0]))
    assert r.status is MetricStatus.UNDEFINED
    assert r.reason is UndefinedReason.ZERO_REFERENCE_VOLATILITY


def test_volatility_ratio_zero_numerator_is_ok_zero() -> None:
    # Left constant -> vol 0, right non-zero -> ratio 0.0 (defined).
    r = volatility_ratio(obs("F", [100.0, 100.0, 100.0]), obs("R", [100.0, 105.0, 99.75]))
    assert r.status is MetricStatus.OK
    assert r.value == 0.0


def test_volatility_ratio_interior_zero_price_undefined() -> None:
    r = volatility_ratio(obs("L", [100.0, 0.0, 100.0]), obs("R", [100.0, 105.0, 99.75]))
    assert r.status is MetricStatus.UNDEFINED
    assert r.reason is UndefinedReason.ZERO_DENOMINATOR


def test_volatility_ratio_insufficient_one_short() -> None:
    with pytest.raises(InsufficientObservationsError):
        volatility_ratio(obs("L", [100.0, 110.0]), obs("R", [100.0, 105.0]))


# ============================ pearson_correlation ============================


def test_correlation_opposite_returns_is_minus_one() -> None:
    r = pearson_correlation(obs("L", [100.0, 110.0, 99.0]), obs("R", [100.0, 90.0, 99.0]))
    assert r.status is MetricStatus.OK
    assert r.value == pytest.approx(-1.0, rel=_REL_TOL)


def test_correlation_identical_series_is_plus_one() -> None:
    s = obs("L", [100.0, 110.0, 99.0])
    r = pearson_correlation(s, s)
    assert r.value == pytest.approx(1.0, rel=_REL_TOL)


def test_correlation_scale_invariant() -> None:
    a = obs("A", [100.0, 110.0, 99.0])
    b = obs("B", [1000.0, 1100.0, 990.0])  # same returns, 10x scale
    r = pearson_correlation(a, b)
    assert r.value == pytest.approx(1.0, rel=_REL_TOL)


def test_correlation_value_is_bounded() -> None:
    r = pearson_correlation(obs("L", [100.0, 110.0, 99.0]), obs("R", [100.0, 90.0, 99.0]))
    assert -1.0 <= r.value <= 1.0


def test_correlation_zero_variance_left() -> None:
    r = pearson_correlation(obs("F", [100.0, 100.0, 100.0]), obs("R", [100.0, 90.0, 99.0]))
    assert r.status is MetricStatus.UNDEFINED
    assert r.reason is UndefinedReason.ZERO_VARIANCE


def test_correlation_zero_variance_right() -> None:
    r = pearson_correlation(obs("L", [100.0, 110.0, 99.0]), obs("F", [100.0, 100.0, 100.0]))
    assert r.status is MetricStatus.UNDEFINED
    assert r.reason is UndefinedReason.ZERO_VARIANCE


def test_correlation_interior_zero_price_undefined() -> None:
    r = pearson_correlation(obs("A", [100.0, 0.0, 100.0]), obs("R", [100.0, 90.0, 99.0]))
    assert r.status is MetricStatus.UNDEFINED
    assert r.reason is UndefinedReason.ZERO_DENOMINATOR


def test_correlation_symmetric_value_ordered_metadata() -> None:
    a = obs("A", [100.0, 110.0, 99.0])
    b = obs("B", [100.0, 90.0, 99.0])
    ab = pearson_correlation(a, b)
    ba = pearson_correlation(b, a)
    assert ab.value == pytest.approx(ba.value, rel=_REL_TOL)  # symmetric value
    assert ab.metadata["source_series_ids"] == ("A", "B")     # order preserved
    assert ba.metadata["source_series_ids"] == ("B", "A")


def test_correlation_insufficient_one_short() -> None:
    with pytest.raises(InsufficientObservationsError):
        pearson_correlation(obs("L", [100.0, 110.0]), obs("R", [100.0, 90.0]))


# ============================ alignment enforcement ==========================


def test_pairwise_mismatched_timestamps_raise() -> None:
    left = obs("L", [100.0, 110.0, 99.0], day_offsets=[0, 1, 2])
    right = obs("R", [100.0, 90.0, 99.0], day_offsets=[0, 1, 3])  # differs at last
    with pytest.raises(NotAlignedError, match="timestamps must be identical"):
        pearson_correlation(left, right)


def test_pairwise_unequal_lengths_raise() -> None:
    left = obs("L", [100.0, 110.0, 99.0])
    right = obs("R", [100.0, 90.0])
    with pytest.raises(NotAlignedError, match="equal length"):
        volatility_ratio(left, right)


def test_rve_does_not_silently_align() -> None:
    # Two overlapping-but-unequal series that WOULD intersect must NOT be aligned
    # by the RVE; it must raise rather than compute on a silent intersection.
    left = obs("L", [1.0, 2.0, 3.0], day_offsets=[0, 1, 2])
    right = obs("R", [1.0, 2.0, 3.0], day_offsets=[1, 2, 3])
    with pytest.raises(NotAlignedError):
        relative_return(left, right)


# ============================ metadata / provenance ==========================


def test_metadata_common_provenance_fields() -> None:
    r = period_return(obs("A", [100.0, 110.0, 121.0]))
    md = r.metadata
    assert md["metric_name"] == "period_return"
    assert md["source_series_ids"] == ("A",)
    assert md["units"] == ("price",)
    assert md["observation_count"] == 3
    assert md["start_timestamp"] == _BASE
    assert md["end_timestamp"] == _BASE + timedelta(days=2)
    assert md["return_convention"] == "simple"
    assert md["annualized"] is False
    assert md["formula"] == "period_return@1"


def test_metadata_return_observation_count_for_return_metrics() -> None:
    r = realized_volatility(obs("A", [100.0, 110.0, 99.0, 105.0]))
    assert r.metadata["observation_count"] == 4
    assert r.metadata["return_observation_count"] == 3


def test_metadata_present_on_undefined_results() -> None:
    r = period_return(obs("A", [0.0, 100.0]))
    assert r.status is MetricStatus.UNDEFINED
    assert r.metadata["metric_name"] == "period_return"
    assert r.metadata["observation_count"] == 2


def test_metadata_is_deterministic() -> None:
    s = obs("A", [100.0, 110.0, 99.0])
    r1 = realized_volatility(s)
    r2 = realized_volatility(s)
    assert r1.value == r2.value
    assert dict(r1.metadata) == dict(r2.metadata)
    assert list(r1.metadata.keys()) == list(r2.metadata.keys())


def test_metadata_no_interpretation_vocabulary() -> None:
    r = pearson_correlation(obs("L", [100.0, 110.0, 99.0]), obs("R", [100.0, 90.0, 99.0]))
    blob = repr({k: str(v) for k, v in r.metadata.items()}).lower()
    for banned in ("long", "short", "buy", "sell", "bull", "bear", "score",
                   "signal", "confidence", "recommend"):
        assert banned not in blob


# ============================ immutability ===================================


def test_inputs_not_mutated() -> None:
    left = obs("L", [100.0, 110.0, 99.0])
    right = obs("R", [100.0, 90.0, 99.0])
    before_left = (left.series_id, left.timestamps, left.values)
    before_right = (right.series_id, right.timestamps, right.values)
    pearson_correlation(left, right)
    volatility_ratio(left, right)
    relative_return(left, right)
    assert (left.series_id, left.timestamps, left.values) == before_left
    assert (right.series_id, right.timestamps, right.values) == before_right


# ============================ public API / boundaries ========================


def test_public_api_exports() -> None:
    for name in (
        "period_return", "relative_return", "realized_volatility",
        "volatility_ratio", "pearson_correlation",
        "RelativeValueResult", "MetricStatus", "UndefinedReason",
        "RelativeValueError", "NotAlignedError", "InsufficientObservationsError",
    ):
        assert name in rv.__all__
        assert hasattr(rv, name)


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


def test_import_boundary_source_level() -> None:
    pkg_dir = Path(rv.__file__).parent
    imports = _internal_imports(pkg_dir)
    # May import canonical models from fmis.data only.
    assert any(i.startswith("fmis.data") for i in imports)
    # Must not import fmis.features, and must not call fmis.alignment internally.
    for forbidden in imports:
        assert not forbidden.startswith("fmis.features"), forbidden
        assert not forbidden.startswith("fmis.alignment"), forbidden


def test_import_does_not_load_features_or_alignment(fresh_fmis_imports: None) -> None:
    # A fresh import of the RVE must not pull in fmis.features or fmis.alignment.
    import fmis.relative_value  # noqa: F401
    assert not any(m.startswith("fmis.features") for m in sys.modules)
    assert not any(m.startswith("fmis.alignment") for m in sys.modules)


# ============================ integration: mixed calendar ====================


def _candle(i: int, price: float, *, symbol: str, timeframe: str) -> Candle:
    return Candle(
        timestamp=_BASE + timedelta(days=i),
        symbol=symbol,
        timeframe=timeframe,
        open=price, high=price, low=price, close=price, volume=1.0,
        is_closed=True,
    )


def test_mixed_crypto_equity_after_explicit_alignment() -> None:
    # Crypto trades every day; equity only weekdays. Reduce both to observation
    # series, align UPSTREAM via align_intersection, then run RVE on the aligned
    # pair. The RVE itself performs no alignment.
    crypto_offsets = list(range(14))
    equity_offsets = [d for d in crypto_offsets if (_BASE + timedelta(days=d)).weekday() < 5]

    crypto_candles = CandleSeries(
        symbol="BTCUSD", timeframe="1D",
        candles=tuple(_candle(d, 100.0 + d, symbol="BTCUSD", timeframe="1D")
                      for d in crypto_offsets),
    )
    equity_candles = CandleSeries(
        symbol="SPX", timeframe="1D",
        candles=tuple(_candle(d, 200.0 + 2.0 * d, symbol="SPX", timeframe="1D")
                      for d in equity_offsets),
    )

    crypto = candle_series_to_observations(crypto_candles, CandleField.CLOSE)
    equity = candle_series_to_observations(equity_candles, CandleField.CLOSE)

    aligned = align_intersection((crypto, equity))
    assert aligned.report.aligned_observation_count == 10  # weekdays only
    left, right = aligned.series

    corr = pearson_correlation(left, right)
    assert corr.status is MetricStatus.OK
    assert corr.metadata["observation_count"] == 10
    assert corr.metadata["source_series_ids"] == ("BTCUSD.close.1D", "SPX.close.1D")

    # period_return is defined per aligned series
    assert period_return(left).status is MetricStatus.OK
