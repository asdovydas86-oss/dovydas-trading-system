"""Canonical JSON encoding and the JSON-safe metadata codec."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import MappingProxyType

import pytest

from fmis.archive.errors import CorruptRecordError, RecordValidationError
from fmis.archive.json_safe import (
    canonical_dumps,
    canonical_loads,
    decode_metadata,
    decode_timestamp,
    encode_metadata,
    encode_timestamp,
)


# ============ 1. canonical_dumps / canonical_loads ===========================


def test_dumps_is_deterministic_regardless_of_key_insertion_order() -> None:
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert canonical_dumps(a) == canonical_dumps(b)


def test_dumps_produces_utf8_bytes_ending_in_newline() -> None:
    data = canonical_dumps({"note": "héllo — 世界"})
    assert data.endswith(b"\n")
    assert "世界" in data.decode("utf-8")


def test_dumps_rejects_nan() -> None:
    with pytest.raises(RecordValidationError):
        canonical_dumps({"x": float("nan")})


def test_dumps_rejects_infinity() -> None:
    with pytest.raises(RecordValidationError):
        canonical_dumps({"x": float("inf")})
    with pytest.raises(RecordValidationError):
        canonical_dumps({"x": float("-inf")})


def test_loads_round_trips_dumps() -> None:
    value = {"a": [1, 2, "x"], "b": {"c": None, "d": True}}
    assert canonical_loads(canonical_dumps(value)) == value


def test_loads_rejects_duplicate_keys() -> None:
    with pytest.raises(CorruptRecordError):
        canonical_loads(b'{"a": 1, "a": 2}')


def test_loads_rejects_malformed_json() -> None:
    with pytest.raises(CorruptRecordError):
        canonical_loads(b"{not json")


def test_loads_rejects_non_utf8_bytes() -> None:
    with pytest.raises(CorruptRecordError):
        canonical_loads(b"\xff\xfe\x00\x01")


def test_loads_rejects_nan_token() -> None:
    with pytest.raises(CorruptRecordError):
        canonical_loads(b'{"x": NaN}')


def test_loads_rejects_infinity_token() -> None:
    with pytest.raises(CorruptRecordError):
        canonical_loads(b'{"x": Infinity}')


def test_loads_rejects_truncated_content() -> None:
    with pytest.raises(CorruptRecordError):
        canonical_loads(canonical_dumps({"a": 1})[:5])


# ============ 2. timestamps ==================================================


def test_encode_timestamp_requires_a_datetime() -> None:
    with pytest.raises(RecordValidationError):
        encode_timestamp("2026-01-01")  # type: ignore[arg-type]


def test_encode_timestamp_rejects_naive() -> None:
    with pytest.raises(RecordValidationError):
        encode_timestamp(datetime(2026, 1, 1))


def test_encode_timestamp_preserves_offset() -> None:
    dt = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=5)))
    assert encode_timestamp(dt) == dt.isoformat()


def test_decode_timestamp_round_trips_encode() -> None:
    dt = datetime(2026, 3, 4, 5, 6, 7, tzinfo=timezone.utc)
    assert decode_timestamp(encode_timestamp(dt)) == dt


def test_decode_timestamp_rejects_non_str() -> None:
    with pytest.raises(CorruptRecordError):
        decode_timestamp(12345)


def test_decode_timestamp_rejects_invalid_iso() -> None:
    with pytest.raises(CorruptRecordError):
        decode_timestamp("not-a-timestamp")


def test_decode_timestamp_rejects_naive() -> None:
    with pytest.raises(CorruptRecordError):
        decode_timestamp("2026-01-01T00:00:00")


# ============ 3. metadata =====================================================


def test_encode_metadata_accepts_every_json_safe_primitive() -> None:
    metadata = {"s": "x", "i": 1, "f": 1.5, "b": True, "n": None}
    assert encode_metadata(metadata) == metadata


def test_encode_metadata_accepts_tuples_as_arrays() -> None:
    assert encode_metadata({"t": ("a", "b")}) == {"t": ["a", "b"]}


def test_encode_metadata_accepts_nested_mappings() -> None:
    assert encode_metadata({"m": {"inner": (1, 2)}}) == {"m": {"inner": [1, 2]}}


def test_encode_metadata_accepts_a_mappingproxy() -> None:
    assert encode_metadata(MappingProxyType({"x": 1})) == {"x": 1}


def test_encode_metadata_rejects_list() -> None:
    # The message must specifically name the list rule, not merely "some
    # RecordValidationError" — a disabled list-check would still raise from
    # the generic unsupported-type fallback at the bottom of the function,
    # which this distinguishes from.
    with pytest.raises(RecordValidationError, match="is a list"):
        encode_metadata({"t": ["a", "b"]})


def test_encode_metadata_rejects_nan() -> None:
    with pytest.raises(RecordValidationError):
        encode_metadata({"x": float("nan")})


def test_encode_metadata_rejects_infinity() -> None:
    with pytest.raises(RecordValidationError):
        encode_metadata({"x": float("inf")})


def test_encode_metadata_rejects_bytes() -> None:
    with pytest.raises(RecordValidationError):
        encode_metadata({"x": b"raw"})


def test_encode_metadata_rejects_a_live_object() -> None:
    class Thing:
        pass

    with pytest.raises(RecordValidationError):
        encode_metadata({"x": Thing()})


def test_encode_metadata_rejects_a_non_str_key() -> None:
    with pytest.raises(RecordValidationError):
        encode_metadata({1: "x"})  # type: ignore[dict-item]


def test_encode_metadata_rejects_a_non_str_nested_key() -> None:
    with pytest.raises(RecordValidationError):
        encode_metadata({"m": {1: "x"}})


def test_encode_metadata_requires_a_mapping() -> None:
    with pytest.raises(RecordValidationError):
        encode_metadata(["not", "a", "mapping"])  # type: ignore[arg-type]


def test_decode_metadata_turns_arrays_into_tuples() -> None:
    assert decode_metadata({"t": ["a", "b"]}) == {"t": ("a", "b")}


def test_decode_metadata_recurses_into_nested_objects() -> None:
    assert decode_metadata({"m": {"inner": [1, 2]}}) == {"m": {"inner": (1, 2)}}


def test_decode_metadata_requires_a_json_object() -> None:
    with pytest.raises(CorruptRecordError):
        decode_metadata(["not", "an", "object"])


def test_decode_metadata_rejects_non_str_key() -> None:
    with pytest.raises(CorruptRecordError):
        decode_metadata({1: "x"})


def test_decode_metadata_rejects_a_type_that_never_comes_from_real_json() -> None:
    # json.loads can never produce a set; this pins the defensive fallback
    # for a caller that bypasses the parser and calls the codec directly.
    with pytest.raises(CorruptRecordError):
        decode_metadata({"x": {1, 2, 3}})


def test_metadata_round_trips_every_accepted_shape() -> None:
    original = {
        "s": "x",
        "i": 7,
        "f": 2.5,
        "b": False,
        "n": None,
        "t": ("a", "b", "c"),
        "m": {"nested": ("x",), "flag": True},
    }
    assert decode_metadata(encode_metadata(original)) == {
        "s": "x", "i": 7, "f": 2.5, "b": False, "n": None,
        "t": ("a", "b", "c"), "m": {"nested": ("x",), "flag": True},
    }
