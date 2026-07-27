"""Tests for the ingestion boundary (fmis.ingest.candles).

The boundary's contract is *strictness*: every test here asserts either that a
well-formed payload decodes to exactly the canonical object, or that a malformed
one is rejected with a positional error — never silently repaired.
"""

from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import fmis.ingest as ingest
from fmis.data import Candle, CandleSeries
from fmis.ingest import (
    CANDLE_FIELDS,
    IngestError,
    RecordDecodeError,
    SeriesDecodeError,
    decode_candle,
    decode_candle_series,
    decode_candle_series_from_json,
)

FIXTURES = Path(__file__).parent / "fixtures"
_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def record(**overrides: object) -> dict[str, object]:
    """A valid canonical record; override one field to exercise a failure case."""
    base: dict[str, object] = {
        "timestamp": "2024-01-01T00:00:00+00:00",
        "symbol": "BTCUSDT",
        "timeframe": "4H",
        "open": 100.0,
        "high": 110.0,
        "low": 90.0,
        "close": 105.0,
        "volume": 1000.0,
        "is_closed": True,
    }
    base.update(overrides)
    return base


def records_at(offsets: list[int], **overrides: object) -> list[dict[str, object]]:
    """Valid records spaced 4h apart, one per offset."""
    return [
        record(timestamp=(_BASE + timedelta(hours=4 * o)).isoformat(), **overrides)
        for o in offsets
    ]


# ============================ happy path =====================================


def test_decode_candle_produces_canonical_candle() -> None:
    candle = decode_candle(record())
    assert candle == Candle(
        timestamp=_BASE,
        symbol="BTCUSDT",
        timeframe="4H",
        open=100.0,
        high=110.0,
        low=90.0,
        close=105.0,
        volume=1000.0,
        is_closed=True,
    )


def test_decode_candle_accepts_datetime_timestamp() -> None:
    assert decode_candle(record(timestamp=_BASE)).timestamp == _BASE


def test_decode_candle_accepts_z_suffix() -> None:
    assert decode_candle(record(timestamp="2024-01-01T00:00:00Z")).timestamp == _BASE


def test_decode_candle_accepts_permanent_utc_zoneinfo() -> None:
    ts = datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC"))
    assert decode_candle(record(timestamp=ts)).timestamp == ts


def test_decode_candle_widens_int_to_float() -> None:
    candle = decode_candle(record(open=100, high=110, low=90, close=105, volume=1000))
    for field in ("open", "high", "low", "close", "volume"):
        assert isinstance(getattr(candle, field), float)


def test_decode_candle_field_names_match_canonical_model() -> None:
    # The record shape is the Candle shape; drift in either must fail loudly.
    assert set(CANDLE_FIELDS) == set(Candle.__dataclass_fields__)


def test_decode_series_builds_ordered_series() -> None:
    series = decode_candle_series(records_at([0, 1, 2]))
    assert isinstance(series, CandleSeries)
    assert series.symbol == "BTCUSDT"
    assert series.timeframe == "4H"
    assert len(series.candles) == 3
    assert [c.timestamp for c in series.candles] == [
        _BASE, _BASE + timedelta(hours=4), _BASE + timedelta(hours=8)
    ]


def test_decode_series_infers_identity_from_first_record() -> None:
    series = decode_candle_series(records_at([0, 1]))
    assert (series.symbol, series.timeframe) == ("BTCUSDT", "4H")


def test_decode_series_explicit_identity_is_honoured() -> None:
    series = decode_candle_series(records_at([0, 1]), symbol="BTCUSDT", timeframe="4H")
    assert (series.symbol, series.timeframe) == ("BTCUSDT", "4H")


def test_decode_empty_payload_with_explicit_identity() -> None:
    series = decode_candle_series([], symbol="BTCUSDT", timeframe="4H")
    assert series.candles == ()


def test_decode_series_accepts_any_iterable() -> None:
    series = decode_candle_series(iter(records_at([0, 1])))
    assert len(series.candles) == 2


# ============================ no silent repair ===============================


def test_decode_series_does_not_sort() -> None:
    # Descending timestamps must raise, never be quietly reordered into a series.
    with pytest.raises(SeriesDecodeError, match="strictly increasing"):
        decode_candle_series(records_at([2, 1, 0]))


def test_decode_series_does_not_deduplicate() -> None:
    with pytest.raises(SeriesDecodeError, match="strictly increasing"):
        decode_candle_series(records_at([0, 0]))


def test_decode_series_does_not_filter_forming_candles() -> None:
    payload = records_at([0, 1])
    payload[1]["is_closed"] = False
    series = decode_candle_series(payload)
    assert [c.is_closed for c in series.candles] == [True, False]
    assert len(series.closed().candles) == 1  # filtering stays the caller's choice


def test_decode_series_reports_first_out_of_order_index() -> None:
    with pytest.raises(SeriesDecodeError) as ei:
        decode_candle_series(records_at([0, 1, 1, 2]))
    assert ei.value.index == 2


def test_decode_series_rejects_mixed_symbol() -> None:
    payload = records_at([0, 1])
    payload[1]["symbol"] = "ETHUSDT"
    with pytest.raises(SeriesDecodeError) as ei:
        decode_candle_series(payload)
    assert ei.value.index == 1


def test_decode_series_rejects_record_disagreeing_with_explicit_identity() -> None:
    with pytest.raises(SeriesDecodeError, match="does not match"):
        decode_candle_series(records_at([0, 1]), symbol="ETHUSDT", timeframe="4H")


def test_decode_series_rejects_mixed_timeframe() -> None:
    payload = records_at([0, 1])
    payload[1]["timeframe"] = "1D"
    with pytest.raises(SeriesDecodeError):
        decode_candle_series(payload)


def test_decode_empty_payload_without_identity_raises() -> None:
    with pytest.raises(SeriesDecodeError, match="empty payload"):
        decode_candle_series([])


# ============================ field-shape rejection ==========================


@pytest.mark.parametrize("field", CANDLE_FIELDS)
def test_missing_any_required_field_raises(field: str) -> None:
    payload = record()
    del payload[field]
    with pytest.raises(RecordDecodeError, match=f"missing required field.*{field}"):
        decode_candle(payload)


def test_unexpected_field_raises() -> None:
    with pytest.raises(RecordDecodeError, match="unexpected field.*adj_close"):
        decode_candle(record(adj_close=104.0))


def test_non_mapping_record_raises() -> None:
    with pytest.raises(RecordDecodeError, match="must be a mapping"):
        decode_candle([1, 2, 3])  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
def test_numeric_string_is_rejected_not_parsed(field: str) -> None:
    with pytest.raises(RecordDecodeError, match="int or float"):
        decode_candle(record(**{field: "100.0"}))


@pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
def test_bool_rejected_as_number(field: str) -> None:
    with pytest.raises(RecordDecodeError, match="not bool"):
        decode_candle(record(**{field: True}))


def test_none_numeric_rejected() -> None:
    with pytest.raises(RecordDecodeError, match="int or float"):
        decode_candle(record(close=None))


@pytest.mark.parametrize("value", [1, 0, "true"])
def test_is_closed_must_be_bool(value: object) -> None:
    with pytest.raises(RecordDecodeError, match="must be a bool"):
        decode_candle(record(is_closed=value))


@pytest.mark.parametrize("field", ["symbol", "timeframe"])
def test_text_fields_must_be_str(field: str) -> None:
    with pytest.raises(RecordDecodeError, match="must be a str"):
        decode_candle(record(**{field: 4}))


def test_unparseable_timestamp_raises() -> None:
    with pytest.raises(RecordDecodeError, match="not a valid ISO-8601"):
        decode_candle(record(timestamp="not-a-date"))


def test_non_string_non_datetime_timestamp_raises() -> None:
    with pytest.raises(RecordDecodeError, match="datetime or an ISO-8601"):
        decode_candle(record(timestamp=1704067200))


# ============================ canonical invariants delegated =================


def test_naive_timestamp_rejected_by_utc_contract() -> None:
    # Parses fine as ISO-8601; Candle's ADR-0001 contract rejects it.
    with pytest.raises(RecordDecodeError, match="timezone-aware"):
        decode_candle(record(timestamp="2024-01-01T00:00:00"))


def test_non_utc_offset_rejected() -> None:
    with pytest.raises(RecordDecodeError, match="must represent UTC"):
        decode_candle(record(timestamp="2024-01-01T00:00:00+02:00"))


def test_seasonal_zone_rejected_even_at_zero_offset() -> None:
    ts = datetime(2024, 1, 1, tzinfo=ZoneInfo("Europe/London"))  # winter: +00:00
    with pytest.raises(RecordDecodeError, match="must represent UTC"):
        decode_candle(record(timestamp=ts))


def test_inconsistent_ohlc_rejected() -> None:
    with pytest.raises(RecordDecodeError, match="high must be"):
        decode_candle(record(high=50.0))


def test_negative_price_rejected() -> None:
    with pytest.raises(RecordDecodeError, match="cannot be negative"):
        decode_candle(record(volume=-1.0))


def test_non_finite_price_rejected() -> None:
    with pytest.raises(RecordDecodeError, match="finite"):
        decode_candle(record(close=float("nan")))


def test_empty_symbol_rejected() -> None:
    with pytest.raises(RecordDecodeError, match="symbol cannot be empty"):
        decode_candle(record(symbol="   "))


def test_model_error_is_preserved_as_cause() -> None:
    with pytest.raises(RecordDecodeError) as ei:
        decode_candle(record(high=50.0))
    assert isinstance(ei.value.__cause__, ValueError)


# ============================ positional error context =======================


def test_record_index_is_reported() -> None:
    payload = records_at([0, 1, 2])
    payload[2]["close"] = "105.0"
    with pytest.raises(RecordDecodeError) as ei:
        decode_candle_series(payload)
    assert ei.value.index == 2
    assert ei.value.field == "close"
    assert "record 2" in str(ei.value)


def test_index_reported_for_invariant_failure_too() -> None:
    payload = records_at([0, 1])
    payload[1]["low"] = 999.0
    with pytest.raises(RecordDecodeError) as ei:
        decode_candle_series(payload)
    assert ei.value.index == 1


def test_missing_field_error_has_no_single_field_attributed() -> None:
    payload = record()
    del payload["close"]
    with pytest.raises(RecordDecodeError) as ei:
        decode_candle(payload, index=7)
    assert ei.value.index == 7 and ei.value.field is None


# ============================ JSON entry point ===============================


def test_from_json_roundtrip() -> None:
    payload = json.dumps(records_at([0, 1, 2]))
    series = decode_candle_series_from_json(payload)
    assert len(series.candles) == 3


def test_from_json_accepts_bytes() -> None:
    payload = json.dumps(records_at([0, 1])).encode()
    assert len(decode_candle_series_from_json(payload).candles) == 2


def test_from_json_rejects_malformed_json() -> None:
    with pytest.raises(IngestError, match="not valid JSON"):
        decode_candle_series_from_json("{oops")


def test_from_json_rejects_non_array_top_level() -> None:
    with pytest.raises(IngestError, match="must be a JSON array"):
        decode_candle_series_from_json('{"timestamp": "2024-01-01T00:00:00+00:00"}')


def test_from_json_decodes_the_repository_fixture() -> None:
    # The fixture that tests previously parsed by hand is now a first-class,
    # fully validated payload for this boundary.
    series = decode_candle_series_from_json((FIXTURES / "btcusdt_4h.json").read_text())
    assert (series.symbol, series.timeframe) == ("BTCUSDT", "4H")
    assert len(series.candles) == 20
    assert all(c.is_closed for c in series.candles)


def test_decoded_fixture_matches_hand_built_series() -> None:
    # Equivalence with the existing hand-rolled construction in test_data_models,
    # proving the decoder introduces no drift against the established path.
    raw = json.loads((FIXTURES / "btcusdt_4h.json").read_text())
    hand_built = CandleSeries(
        symbol="BTCUSDT",
        timeframe="4H",
        candles=tuple(
            Candle(
                timestamp=datetime.fromisoformat(r["timestamp"]),
                symbol=r["symbol"],
                timeframe=r["timeframe"],
                open=r["open"],
                high=r["high"],
                low=r["low"],
                close=r["close"],
                volume=r["volume"],
                is_closed=r["is_closed"],
            )
            for r in raw
        ),
    )
    assert decode_candle_series_from_json(json.dumps(raw)) == hand_built


# ============================ determinism / purity ===========================


def test_decoding_is_deterministic() -> None:
    payload = records_at([0, 1, 2])
    assert decode_candle_series(payload) == decode_candle_series(payload)


def test_input_records_are_not_mutated() -> None:
    payload = records_at([0, 1])
    before = json.dumps(payload, sort_keys=True)
    decode_candle_series(payload)
    assert json.dumps(payload, sort_keys=True) == before


# ============================ exception hierarchy ============================


def test_exception_hierarchy() -> None:
    assert issubclass(RecordDecodeError, IngestError)
    assert issubclass(RecordDecodeError, ValueError)
    assert issubclass(SeriesDecodeError, IngestError)
    assert issubclass(SeriesDecodeError, ValueError)


# ============================ public API / boundaries ========================


def test_public_api_exports() -> None:
    for name in (
        "decode_candle", "decode_candle_series", "decode_candle_series_from_json",
        "CANDLE_FIELDS", "IngestError", "RecordDecodeError", "SeriesDecodeError",
    ):
        assert name in ingest.__all__
        assert hasattr(ingest, name)


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
    imports = _internal_imports(Path(ingest.__file__).parent)
    assert any(i.startswith("fmis.data") for i in imports)
    for module in imports:
        for forbidden in ("fmis.features", "fmis.alignment", "fmis.relative_value"):
            assert not module.startswith(forbidden), module


def test_import_does_not_load_downstream_packages(fresh_fmis_imports: None) -> None:
    # A cold import of the ingestion boundary must pull in fmis.data and nothing
    # downstream of it.
    import fmis.ingest  # noqa: F401

    for forbidden in ("fmis.features", "fmis.alignment", "fmis.relative_value"):
        assert not any(m.startswith(forbidden) for m in sys.modules)


def test_no_dependency_on_private_time_module() -> None:
    # The decoder must not re-implement or reach into the UTC contract; it relies
    # on Candle to enforce it (see ADR-0005).
    imports = _internal_imports(Path(ingest.__file__).parent)
    assert not any("_timeutils" in i for i in imports)
