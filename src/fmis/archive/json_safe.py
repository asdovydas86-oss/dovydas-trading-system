"""Canonical JSON encoding and the JSON-safe metadata codec.

Two independent concerns share this module because they share one rule: a
value that cannot be losslessly round-tripped through JSON is rejected at
encode time rather than silently coerced. `canonical_dumps`/`canonical_loads`
handle the *bytes* (determinism, non-finite rejection, duplicate-key
rejection); `encode_metadata`/`decode_metadata` handle the *shape* a
`Workspace`/`DailyRun` `metadata: Mapping[str, Any]` field is allowed to hold.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fmis.archive.errors import CorruptRecordError, RecordValidationError

__all__ = [
    "canonical_dumps",
    "canonical_loads",
    "encode_metadata",
    "decode_metadata",
    "encode_timestamp",
    "decode_timestamp",
    "reject_duplicate_json_keys",
]


def _reject_constant(token: str) -> float:
    raise CorruptRecordError(f"non-finite numeric token {token!r} is not permitted")


def reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """`object_pairs_hook` for `json.loads` that rejects a repeated key.

    Public so every JSON parse in this package — record files via
    `canonical_loads`, and `manifest.jsonl` lines directly — applies the same
    "reject rather than repair" rule to duplicate keys, not just the former.
    """
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise CorruptRecordError(f"duplicate JSON key {key!r}")
        seen[key] = value
    return seen


def canonical_dumps(value: Any) -> bytes:
    """Deterministic, UTF-8, non-finite-rejecting JSON bytes plus a trailing newline.

    `sort_keys=True` makes the output a pure function of content, which is what
    makes a content digest meaningful (ADR-0027 §1). `allow_nan=False` makes a
    `NaN`/`Infinity` value a write-time error instead of an on-disk token a
    later reader must special-case.
    """
    try:
        text = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ": "),
            indent=2,
        )
    except ValueError as error:
        raise RecordValidationError(f"value is not JSON-safe: {error}") from error
    return (text + "\n").encode("utf-8")


def canonical_loads(data: bytes) -> Any:
    """Decode canonical JSON bytes, rejecting duplicate keys and non-finite tokens."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CorruptRecordError(f"record is not valid UTF-8: {error}") from error
    try:
        return json.loads(
            text,
            object_pairs_hook=reject_duplicate_json_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as error:
        raise CorruptRecordError(f"record is not valid JSON: {error}") from error


def encode_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise RecordValidationError(f"timestamp must be a datetime, got {type(value).__name__}")
    if value.tzinfo is None:
        raise RecordValidationError("timestamp must be timezone-aware, got a naive datetime")
    return value.isoformat()


def decode_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise CorruptRecordError(f"timestamp must be a str, got {type(value).__name__}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise CorruptRecordError(f"timestamp {value!r} is not valid ISO-8601: {error}") from error
    if parsed.tzinfo is None:
        raise CorruptRecordError(f"timestamp {value!r} is naive; a canonical record is never naive")
    return parsed


def _encode_metadata_value(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):  # NaN/inf
            raise RecordValidationError(f"metadata{path} is non-finite")
        return value
    if isinstance(value, list):
        raise RecordValidationError(
            f"metadata{path} is a list; metadata sequences must be tuples "
            "(the codebase's own tuple-not-list convention — a list would not "
            "round-trip to an equal value)"
        )
    if isinstance(value, tuple):
        return [_encode_metadata_value(item, path=f"{path}[{i}]") for i, item in enumerate(value)]
    if isinstance(value, Mapping):
        encoded: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise RecordValidationError(f"metadata{path} has a non-str key {key!r}")
            encoded[key] = _encode_metadata_value(item, path=f"{path}.{key}")
        return encoded
    raise RecordValidationError(
        f"metadata{path} has an unsupported type {type(value).__name__}; only "
        "str, bool, int, finite float, None, tuple and Mapping[str, ...] are JSON-safe here"
    )


def encode_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        raise RecordValidationError(f"metadata must be a Mapping, got {type(metadata).__name__}")
    encoded: dict[str, Any] = {}
    for key, value in metadata.items():
        if not isinstance(key, str):
            raise RecordValidationError(f"metadata has a non-str key {key!r}")
        encoded[key] = _encode_metadata_value(value, path=f"[{key!r}]")
    return encoded


def _decode_metadata_value(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, list):
        return tuple(_decode_metadata_value(item, path=f"{path}[{i}]") for i, item in enumerate(value))
    if isinstance(value, dict):
        decoded: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CorruptRecordError(f"metadata{path} has a non-str key {key!r}")
            decoded[key] = _decode_metadata_value(item, path=f"{path}.{key}")
        return decoded
    raise CorruptRecordError(f"metadata{path} has an unsupported decoded type {type(value).__name__}")


def decode_metadata(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise CorruptRecordError(f"metadata must be a JSON object, got {type(raw).__name__}")
    decoded: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise CorruptRecordError(f"metadata has a non-str key {key!r}")
        decoded[key] = _decode_metadata_value(value, path=f"[{key!r}]")
    return decoded
