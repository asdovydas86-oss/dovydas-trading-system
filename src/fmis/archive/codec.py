"""Explicit, hand-written codecs for `Workspace` and `DailyRun`.

Every function here is a pure mapping between a domain object and a JSON-safe
`dict`/`list`/primitive tree — no reflection, no `dataclasses.asdict`, no
`pickle`. Each nested type gets its own `encode_*`/`decode_*` pair, and every
decode function validates the exact expected key set: an unknown key is a
corrupt record, not a silently-ignored one (ADR-0027 §1).

`decode_*` reconstructs real domain instances by calling their real
constructors, so every `__post_init__` validation in `fmis.workspace`/
`fmis.daily` runs again on the way back in — a record that decodes cleanly but
fails model validation raises `RecordValidationError`, never a bypass.
"""

from __future__ import annotations

from typing import Any

from fmis.archive.errors import CorruptRecordError, RecordValidationError, UnsupportedSchemaVersionError
from fmis.archive.json_safe import decode_metadata, decode_timestamp, encode_metadata, encode_timestamp
from fmis.daily.models import (
    DAILY_SCHEMA_VERSION,
    DailyRun,
    DailyRunError,
    FailureKind,
    ResultCategory,
    SymbolFailure,
    SymbolResult,
)
from fmis.workspace.models import (
    WORKSPACE_SCHEMA_VERSION,
    NoteBlock,
    Provenance,
    Row,
    RowBlock,
    Section,
    SectionId,
    SectionStatus,
    TableBlock,
    Tier,
    Unavailable,
    Workspace,
    WorkspaceError,
)

#: Every exception a `Workspace`/`DailyRun` model's own `__post_init__` may
#: raise. Caught around every domain-model construction on decode and
#: re-raised as `RecordValidationError` — a record that decodes cleanly but
#: fails model validation never bypasses that validation.
_MODEL_VALIDATION_ERRORS = (TypeError, ValueError, WorkspaceError, DailyRunError)

#: The payload schema versions this build can read — distinct from the
#: envelope's own `ARCHIVE_SCHEMA_VERSION` (ADR-0027 §3, §8). No migration
#: path exists yet: a payload version outside these sets is rejected
#: cleanly, the same way an unsupported envelope version already is.
SUPPORTED_WORKSPACE_SCHEMA_VERSIONS = frozenset({WORKSPACE_SCHEMA_VERSION})
SUPPORTED_DAILY_SCHEMA_VERSIONS = frozenset({DAILY_SCHEMA_VERSION})

__all__ = [
    "encode_workspace",
    "decode_workspace",
    "encode_daily_run",
    "decode_daily_run",
]


def _require_object(value: Any, *, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CorruptRecordError(f"{what} must be a JSON object, got {type(value).__name__}")
    return value


def _require_keys(obj: dict[str, Any], *, required: set[str], optional: set[str], what: str) -> None:
    allowed = required | optional
    present = set(obj)
    missing = required - present
    if missing:
        raise CorruptRecordError(f"{what} is missing required field(s): {sorted(missing)}")
    extra = present - allowed
    if extra:
        raise CorruptRecordError(f"{what} has unknown field(s): {sorted(extra)}")


def _require_str(value: Any, *, what: str) -> str:
    if not isinstance(value, str):
        raise CorruptRecordError(f"{what} must be a str, got {type(value).__name__}")
    return value


def _require_optional_str(value: Any, *, what: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, what=what)


def _require_list(value: Any, *, what: str) -> list[Any]:
    if not isinstance(value, list):
        raise CorruptRecordError(f"{what} must be a JSON array, got {type(value).__name__}")
    return value


def _require_enum(value: Any, enum_type: type, *, what: str) -> Any:
    raw = _require_str(value, what=what)
    try:
        return enum_type(raw)
    except ValueError as error:
        valid = [member.value for member in enum_type]
        raise CorruptRecordError(f"{what} {raw!r} is not one of {valid}") from error


# --------------------------------------------------------------------------- #
# Row / RowBlock / TableBlock / NoteBlock / Block
# --------------------------------------------------------------------------- #


def _encode_row(row: Row) -> dict[str, Any]:
    return {"label": row.label, "value": row.value, "note": row.note, "tier": row.tier.value}


def _decode_row(raw: Any) -> Row:
    obj = _require_object(raw, what="row")
    _require_keys(obj, required={"label", "value", "note", "tier"}, optional=set(), what="row")
    return Row(
        label=_require_str(obj["label"], what="row.label"),
        value=_require_str(obj["value"], what="row.value"),
        note=_require_str(obj["note"], what="row.note"),
        tier=_require_enum(obj["tier"], Tier, what="row.tier"),
    )


def _encode_block(block: RowBlock | TableBlock | NoteBlock) -> dict[str, Any]:
    if isinstance(block, RowBlock):
        return {
            "kind": "row_block",
            "heading": block.heading,
            "rows": [_encode_row(row) for row in block.rows],
        }
    if isinstance(block, TableBlock):
        return {
            "kind": "table_block",
            "heading": block.heading,
            "columns": list(block.columns),
            "records": [list(record) for record in block.records],
        }
    if isinstance(block, NoteBlock):
        return {"kind": "note_block", "notes": list(block.notes)}
    raise RecordValidationError(f"unsupported block type {type(block).__name__}")


def _decode_block(raw: Any) -> RowBlock | TableBlock | NoteBlock:
    obj = _require_object(raw, what="block")
    kind = obj.get("kind")
    if kind == "row_block":
        _require_keys(obj, required={"kind", "heading", "rows"}, optional=set(), what="row_block")
        rows = _require_list(obj["rows"], what="row_block.rows")
        return RowBlock(
            heading=_require_str(obj["heading"], what="row_block.heading"),
            rows=tuple(_decode_row(item) for item in rows),
        )
    if kind == "table_block":
        _require_keys(
            obj,
            required={"kind", "heading", "columns", "records"},
            optional=set(),
            what="table_block",
        )
        columns = _require_list(obj["columns"], what="table_block.columns")
        records = _require_list(obj["records"], what="table_block.records")
        return TableBlock(
            heading=_require_str(obj["heading"], what="table_block.heading"),
            columns=tuple(_require_str(c, what="table_block.columns[]") for c in columns),
            records=tuple(
                tuple(_require_str(cell, what="table_block.records[][]") for cell in _require_list(r, what="table_block.records[]"))
                for r in records
            ),
        )
    if kind == "note_block":
        _require_keys(obj, required={"kind", "notes"}, optional=set(), what="note_block")
        notes = _require_list(obj["notes"], what="note_block.notes")
        return NoteBlock(notes=tuple(_require_str(n, what="note_block.notes[]") for n in notes))
    raise CorruptRecordError(f"block has unknown kind {kind!r}")


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #


def _encode_provenance(provenance: Provenance | None) -> dict[str, Any] | None:
    if provenance is None:
        return None
    return {
        "engine": provenance.engine,
        "policy_id": provenance.policy_id,
        "as_of": None if provenance.as_of is None else encode_timestamp(provenance.as_of),
    }


def _decode_provenance(raw: Any) -> Provenance | None:
    if raw is None:
        return None
    obj = _require_object(raw, what="provenance")
    _require_keys(
        obj, required={"engine", "policy_id", "as_of"}, optional=set(), what="provenance"
    )
    as_of = obj["as_of"]
    return Provenance(
        engine=_require_str(obj["engine"], what="provenance.engine"),
        policy_id=_require_optional_str(obj["policy_id"], what="provenance.policy_id"),
        as_of=None if as_of is None else decode_timestamp(as_of),
    )


# --------------------------------------------------------------------------- #
# Section / Unavailable / WorkspaceSection
# --------------------------------------------------------------------------- #


def _encode_section(section: Section) -> dict[str, Any]:
    return {
        "kind": "section",
        "id": section.id.value,
        "title": section.title,
        "status": section.status.value,
        "summary": list(section.summary),
        "body": [_encode_block(block) for block in section.body],
        "caveats": list(section.caveats),
        "provenance": _encode_provenance(section.provenance),
        "reason": section.reason,
    }


def _encode_unavailable(section: Unavailable) -> dict[str, Any]:
    return {
        "kind": "unavailable",
        "id": section.id.value,
        "title": section.title,
        "owner": section.owner,
        "reason": section.reason,
        "prohibition": section.prohibition,
    }


def _decode_section_id(raw: Any, *, what: str) -> SectionId:
    return _require_enum(raw, SectionId, what=what)


def _decode_workspace_section(raw: Any) -> Section | Unavailable:
    obj = _require_object(raw, what="section")
    kind = obj.get("kind")
    if kind == "section":
        _require_keys(
            obj,
            required={
                "kind", "id", "title", "status", "summary", "body", "caveats",
                "provenance", "reason",
            },
            optional=set(),
            what="section",
        )
        summary = _require_list(obj["summary"], what="section.summary")
        body = _require_list(obj["body"], what="section.body")
        caveats = _require_list(obj["caveats"], what="section.caveats")
        return Section(
            id=_decode_section_id(obj["id"], what="section.id"),
            title=_require_str(obj["title"], what="section.title"),
            status=_require_enum(obj["status"], SectionStatus, what="section.status"),
            summary=tuple(_require_str(s, what="section.summary[]") for s in summary),
            body=tuple(_decode_block(b) for b in body),
            caveats=tuple(_require_str(c, what="section.caveats[]") for c in caveats),
            provenance=_decode_provenance(obj["provenance"]),
            reason=_require_optional_str(obj["reason"], what="section.reason"),
        )
    if kind == "unavailable":
        _require_keys(
            obj,
            required={"kind", "id", "title", "owner", "reason", "prohibition"},
            optional=set(),
            what="unavailable",
        )
        return Unavailable(
            id=_decode_section_id(obj["id"], what="unavailable.id"),
            title=_require_str(obj["title"], what="unavailable.title"),
            owner=_require_str(obj["owner"], what="unavailable.owner"),
            reason=_require_str(obj["reason"], what="unavailable.reason"),
            prohibition=_require_str(obj["prohibition"], what="unavailable.prohibition"),
        )
    raise CorruptRecordError(f"section has unknown kind {kind!r}")


def _encode_workspace_section(section: Section | Unavailable) -> dict[str, Any]:
    if isinstance(section, Unavailable):
        return _encode_unavailable(section)
    if isinstance(section, Section):
        return _encode_section(section)
    raise RecordValidationError(f"unsupported section type {type(section).__name__}")


# --------------------------------------------------------------------------- #
# Workspace
# --------------------------------------------------------------------------- #


def encode_workspace(workspace: Workspace) -> dict[str, Any]:
    if not isinstance(workspace, Workspace):
        raise RecordValidationError(f"expected a Workspace, got {type(workspace).__name__}")
    return {
        "symbol": workspace.symbol,
        "objective": workspace.objective,
        "as_of": encode_timestamp(workspace.as_of),
        "source": workspace.source,
        "sections": [_encode_workspace_section(s) for s in workspace.sections],
        "schema_version": workspace.schema_version,
        "metadata": encode_metadata(workspace.metadata),
    }


def decode_workspace(raw: Any) -> Workspace:
    obj = _require_object(raw, what="workspace")
    _require_keys(
        obj,
        required={"symbol", "objective", "as_of", "source", "sections", "schema_version", "metadata"},
        optional=set(),
        what="workspace",
    )
    sections = _require_list(obj["sections"], what="workspace.sections")
    schema_version = obj["schema_version"]
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise CorruptRecordError("workspace.schema_version must be an int")
    if schema_version not in SUPPORTED_WORKSPACE_SCHEMA_VERSIONS:
        raise UnsupportedSchemaVersionError(
            f"workspace payload schema_version {schema_version} is not supported; "
            f"this build supports {sorted(SUPPORTED_WORKSPACE_SCHEMA_VERSIONS)}"
        )
    try:
        return Workspace(
            symbol=_require_str(obj["symbol"], what="workspace.symbol"),
            objective=_require_str(obj["objective"], what="workspace.objective"),
            as_of=decode_timestamp(obj["as_of"]),
            source=_require_str(obj["source"], what="workspace.source"),
            sections=tuple(_decode_workspace_section(s) for s in sections),
            schema_version=schema_version,
            metadata=decode_metadata(obj["metadata"]),
        )
    except _MODEL_VALIDATION_ERRORS as error:
        raise RecordValidationError(f"workspace payload failed model validation: {error}") from error


# --------------------------------------------------------------------------- #
# SymbolFailure / SymbolResult / DailyRun
# --------------------------------------------------------------------------- #


def _encode_symbol_failure(failure: SymbolFailure) -> dict[str, Any]:
    return {
        "kind": failure.kind.value,
        "detail": failure.detail,
        "exception_type": failure.exception_type,
    }


def _decode_symbol_failure(raw: Any) -> SymbolFailure:
    obj = _require_object(raw, what="symbol_failure")
    _require_keys(
        obj, required={"kind", "detail", "exception_type"}, optional=set(), what="symbol_failure"
    )
    return SymbolFailure(
        kind=_require_enum(obj["kind"], FailureKind, what="symbol_failure.kind"),
        detail=_require_str(obj["detail"], what="symbol_failure.detail"),
        exception_type=_require_str(obj["exception_type"], what="symbol_failure.exception_type"),
    )


def _encode_symbol_result(result: SymbolResult) -> dict[str, Any]:
    # `context` is never encoded: at runtime it is `workspace.by_id[SectionId.CONTEXT]`,
    # the identical object already reachable through `workspace` — re-derived on
    # decode rather than duplicated (ADR-0027 §3.4 / design doc §3.4).
    return {
        "requested_symbol": result.requested_symbol,
        "category": result.category.value,
        "resolved_symbol": result.resolved_symbol,
        "workspace": None if result.workspace is None else encode_workspace(result.workspace),
        "failure": None if result.failure is None else _encode_symbol_failure(result.failure),
        "regime_summary": result.regime_summary,
        "duration_seconds": result.duration_seconds,
    }


def _require_optional_number(value: Any, *, what: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CorruptRecordError(f"{what} must be a number or null, got {type(value).__name__}")
    return value


def _decode_symbol_result(raw: Any) -> SymbolResult:
    obj = _require_object(raw, what="symbol_result")
    _require_keys(
        obj,
        required={
            "requested_symbol", "category", "resolved_symbol", "workspace",
            "failure", "regime_summary", "duration_seconds",
        },
        optional=set(),
        what="symbol_result",
    )
    workspace_raw = obj["workspace"]
    workspace = None if workspace_raw is None else decode_workspace(workspace_raw)
    context = None if workspace is None else workspace.by_id[SectionId.CONTEXT]
    failure_raw = obj["failure"]
    try:
        return SymbolResult(
            requested_symbol=_require_str(obj["requested_symbol"], what="symbol_result.requested_symbol"),
            category=_require_enum(obj["category"], ResultCategory, what="symbol_result.category"),
            resolved_symbol=_require_optional_str(obj["resolved_symbol"], what="symbol_result.resolved_symbol"),
            workspace=workspace,
            context=context,
            failure=None if failure_raw is None else _decode_symbol_failure(failure_raw),
            regime_summary=_require_optional_str(obj["regime_summary"], what="symbol_result.regime_summary"),
            duration_seconds=_require_optional_number(obj["duration_seconds"], what="symbol_result.duration_seconds"),
        )
    except _MODEL_VALIDATION_ERRORS as error:
        raise RecordValidationError(f"symbol_result payload failed model validation: {error}") from error


def encode_daily_run(daily_run: DailyRun) -> dict[str, Any]:
    if not isinstance(daily_run, DailyRun):
        raise RecordValidationError(f"expected a DailyRun, got {type(daily_run).__name__}")
    return {
        "reference_time": encode_timestamp(daily_run.reference_time),
        "results": [_encode_symbol_result(r) for r in daily_run.results],
        "objective": daily_run.objective,
        "source": daily_run.source,
        "schema_version": daily_run.schema_version,
        "limitations": [list(pair) for pair in daily_run.limitations],
        "metadata": encode_metadata(daily_run.metadata),
    }


def _decode_limitation_pair(raw: Any) -> tuple[str, str]:
    items = _require_list(raw, what="daily_run.limitations[]")
    if len(items) != 2:
        raise CorruptRecordError(f"daily_run.limitations[] must have exactly 2 items, got {len(items)}")
    return (
        _require_str(items[0], what="daily_run.limitations[][0]"),
        _require_str(items[1], what="daily_run.limitations[][1]"),
    )


def decode_daily_run(raw: Any) -> DailyRun:
    obj = _require_object(raw, what="daily_run")
    _require_keys(
        obj,
        required={
            "reference_time", "results", "objective", "source",
            "schema_version", "limitations", "metadata",
        },
        optional=set(),
        what="daily_run",
    )
    results = _require_list(obj["results"], what="daily_run.results")
    limitations = _require_list(obj["limitations"], what="daily_run.limitations")
    schema_version = obj["schema_version"]
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise CorruptRecordError("daily_run.schema_version must be an int")
    if schema_version not in SUPPORTED_DAILY_SCHEMA_VERSIONS:
        raise UnsupportedSchemaVersionError(
            f"daily_run payload schema_version {schema_version} is not supported; "
            f"this build supports {sorted(SUPPORTED_DAILY_SCHEMA_VERSIONS)}"
        )
    try:
        return DailyRun(
            reference_time=decode_timestamp(obj["reference_time"]),
            results=tuple(_decode_symbol_result(r) for r in results),
            objective=_require_str(obj["objective"], what="daily_run.objective"),
            source=_require_str(obj["source"], what="daily_run.source"),
            schema_version=schema_version,
            limitations=tuple(_decode_limitation_pair(item) for item in limitations),
            metadata=decode_metadata(obj["metadata"]),
        )
    except _MODEL_VALIDATION_ERRORS as error:
        raise RecordValidationError(f"daily_run payload failed model validation: {error}") from error
