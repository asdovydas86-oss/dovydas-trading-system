"""`ScanRecord` ⇄ bytes. **One schema number, checked on every read.**

**Why an explicit codec rather than pickling or `repr`.** A persisted record
outlives the process, the commit and the refactor that renames a field. A format
that serialises whatever a dataclass happens to hold today silently reinterprets
tomorrow's fields under yesterday's meanings — which §25 forbids and which no
test can catch, because both sides change together. So every field is written by
name, the schema number is written beside them, and a record whose number this
build does not know is refused rather than guessed at.

**Refusal is a first-class outcome.** `decode_scan` raises
`ScanHistoryFormatError` for corrupt bytes, a truncated file, a missing field, a
wrong type and an unsupported schema alike. The caller's contract for all five is
identical and is the whole point: *history is unavailable, the current market
analysis is untouched.*
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fmis.scan_memory.models import (
    SCAN_MEMORY_SCHEMA_VERSION,
    ScanHistoryFormatError,
    ScanIdentity,
    ScanMemoryError,
    ScanRecord,
    SymbolState,
)

__all__ = ["encode_scan", "decode_scan"]

#: Every schema this build can read. One entry today; a second appears here only
#: beside a migration that states what changed.
SUPPORTED_SCHEMAS = frozenset({SCAN_MEMORY_SCHEMA_VERSION})


def _stamp(moment: datetime | None) -> str | None:
    return None if moment is None else moment.astimezone(timezone.utc).isoformat()


def _parse_stamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise ScanHistoryFormatError(f"{name} must be an ISO 8601 string, got {value!r}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ScanHistoryFormatError(f"{name} is not an instant: {value!r}") from error
    if parsed.tzinfo is None:
        raise ScanHistoryFormatError(f"{name} carries no timezone: {value!r}")
    return parsed


def _state_payload(state: SymbolState) -> dict[str, Any]:
    return {
        "symbol": state.symbol,
        "state": state.state,
        "classification": state.classification,
        "sufficiency": state.sufficiency,
        "as_of": _stamp(state.as_of),
        "direction": state.direction,
        "developing_state": state.developing_state,
        "developing_lean": state.developing_lean,
        "blocker_kind": state.blocker_kind,
        "blocker_observed": state.blocker_observed,
        "structural_trends": [[role, value] for role, value in state.structural_trends],
        "independence_established": state.independence_established,
        "evidence_available": state.evidence_available,
        "supporting": state.supporting,
        "conflicting": state.conflicting,
        "missing": state.missing,
        "unavailable": state.unavailable,
    }


def encode_scan(record: ScanRecord) -> bytes:
    """One record as canonical UTF-8 JSON.

    Keys are sorted and separators are tight, so the same record always produces
    the same bytes — which is what lets a test assert a round trip by equality of
    bytes as well as of value.
    """
    if not isinstance(record, ScanRecord):
        raise ScanMemoryError(f"record must be a ScanRecord, got {type(record).__name__}")
    payload = {
        "schema_version": record.identity.schema_version,
        "recorded_at": _stamp(record.recorded_at),
        "identity": {
            "universe": list(record.identity.universe),
            "timeframes": [[role, interval] for role, interval in record.identity.timeframes],
            "reference_time": _stamp(record.identity.reference_time),
            "analysis_as_of": _stamp(record.identity.analysis_as_of),
        },
        "symbols": [_state_payload(state) for state in record.symbols],
        "unreadable": list(record.unreadable),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _require(payload: Any, key: str, kind: type | tuple[type, ...], where: str) -> Any:
    if not isinstance(payload, dict) or key not in payload:
        raise ScanHistoryFormatError(f"{where} is missing {key!r}")
    value = payload[key]
    if not isinstance(value, kind):
        raise ScanHistoryFormatError(
            f"{where}.{key} must be {kind}, got {type(value).__name__}"
        )
    return value


def _pairs(raw: Any, where: str, *, optional_second: bool = False) -> tuple[tuple[Any, Any], ...]:
    if not isinstance(raw, list):
        raise ScanHistoryFormatError(f"{where} must be a list of pairs")
    out: list[tuple[Any, Any]] = []
    for item in raw:
        if not isinstance(item, list) or len(item) != 2:
            raise ScanHistoryFormatError(f"{where} must hold two-element pairs")
        first, second = item
        if not isinstance(first, str):
            raise ScanHistoryFormatError(f"{where} keys must be strings")
        if second is None and not optional_second:
            raise ScanHistoryFormatError(f"{where} values must be strings")
        if second is not None and not isinstance(second, str):
            raise ScanHistoryFormatError(f"{where} values must be strings")
        out.append((first, second))
    return tuple(out)


def _state_from(payload: Any) -> SymbolState:
    where = "symbols[]"
    return SymbolState(
        symbol=_require(payload, "symbol", str, where),
        state=_require(payload, "state", str, where),
        classification=_require(payload, "classification", str, where),
        sufficiency=_require(payload, "sufficiency", str, where),
        as_of=_parse_stamp(_require(payload, "as_of", str, where), f"{where}.as_of"),
        direction=_require(payload, "direction", (str, type(None)), where),
        developing_state=_require(payload, "developing_state", (str, type(None)), where),
        developing_lean=_require(payload, "developing_lean", (str, type(None)), where),
        blocker_kind=_require(payload, "blocker_kind", (str, type(None)), where),
        blocker_observed=_require(payload, "blocker_observed", str, where),
        structural_trends=_pairs(
            _require(payload, "structural_trends", list, where),
            f"{where}.structural_trends",
            optional_second=True,
        ),
        independence_established=_require(payload, "independence_established", bool, where),
        evidence_available=_require(payload, "evidence_available", bool, where),
        supporting=_require(payload, "supporting", int, where),
        conflicting=_require(payload, "conflicting", int, where),
        missing=_require(payload, "missing", int, where),
        unavailable=_require(payload, "unavailable", int, where),
    )


def decode_scan(data: bytes) -> ScanRecord:
    """One record from bytes, or a refusal naming what was wrong.

    Raises:
        ScanHistoryFormatError: the bytes are not JSON, are not an object, carry
            a schema this build does not support, are missing a field, hold a
            field of the wrong type, or describe a record the domain refuses.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise ScanMemoryError(f"data must be bytes, got {type(data).__name__}")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ScanHistoryFormatError(f"scan history is not readable JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ScanHistoryFormatError("a scan record must be a JSON object")
    schema = _require(payload, "schema_version", int, "record")
    if schema not in SUPPORTED_SCHEMAS:
        raise ScanHistoryFormatError(
            f"scan history was written under schema {schema} and this build "
            f"reads {sorted(SUPPORTED_SCHEMAS)}; reinterpreting its fields under "
            "the current meanings would compare two different things"
        )
    identity_payload = _require(payload, "identity", dict, "record")
    try:
        identity = ScanIdentity(
            schema_version=schema,
            universe=tuple(_require(identity_payload, "universe", list, "identity")),
            timeframes=_pairs(
                _require(identity_payload, "timeframes", list, "identity"),
                "identity.timeframes",
            ),
            reference_time=_parse_stamp(
                _require(identity_payload, "reference_time", str, "identity"),
                "identity.reference_time",
            ),
            analysis_as_of=(
                None
                if identity_payload.get("analysis_as_of") is None
                else _parse_stamp(identity_payload["analysis_as_of"], "identity.analysis_as_of")
            ),
        )
        symbols = tuple(
            _state_from(item) for item in _require(payload, "symbols", list, "record")
        )
        return ScanRecord(
            identity=identity,
            recorded_at=_parse_stamp(
                _require(payload, "recorded_at", str, "record"), "recorded_at"
            ),
            symbols=symbols,
            unreadable=tuple(_require(payload, "unreadable", list, "record")),
        )
    except ScanHistoryFormatError:
        raise
    except ScanMemoryError as error:
        # A domain refusal on decode is a *format* failure: the bytes describe a
        # record this build's own model rejects, and the caller's contract for
        # that is the same as for corrupt bytes.
        raise ScanHistoryFormatError(f"scan history holds an invalid record: {error}") from error
