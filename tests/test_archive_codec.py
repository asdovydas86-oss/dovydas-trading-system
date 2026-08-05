"""Round-trip and rejection tests for `fmis.archive.codec`.

`decode(encode(x)) == x` is the central contract (ADR-0027 §1); every other
test here is either a corruption case the codec must reject, or a case
proving the codec reconstructs real, independently-validated domain objects
rather than bypassing their own `__post_init__` checks.
"""

from __future__ import annotations

import copy

import pytest

from fmis.archive.codec import (
    decode_daily_run,
    decode_workspace,
    encode_daily_run,
    encode_workspace,
)
from fmis.archive.errors import CorruptRecordError, RecordValidationError
from fmis.daily.models import DailyRun
from fmis.workspace.models import SectionId, SectionStatus, Unavailable, Workspace
from tests.archive_helpers import (
    fixture_daily_run,
    fixture_failed_result,
    fixture_workspace,
)


# ============ 1. Workspace round trip ========================================


def test_a_full_workspace_round_trips() -> None:
    workspace = fixture_workspace()
    assert decode_workspace(encode_workspace(workspace)) == workspace


def test_the_workspace_has_both_section_and_unavailable_members() -> None:
    # A real fixture always mixes both — Risk/Portfolio/Trade Plan/AI
    # Interpretation are unbuilt — so one round-trip already exercises the
    # closed WorkspaceSection union both ways.
    workspace = fixture_workspace()
    kinds = {type(section) for section in workspace.sections}
    assert kinds == {type(workspace.by_id[SectionId.INSTRUMENT]), Unavailable}


def test_unicode_survives_the_round_trip() -> None:
    workspace = fixture_workspace()
    unicode_workspace = Workspace(
        symbol=workspace.symbol,
        objective=workspace.objective,
        as_of=workspace.as_of,
        source="fixture · 世界 · héllo",
        sections=workspace.sections,
        metadata={**workspace.metadata, "note": "état — 東京"},
    )
    assert decode_workspace(encode_workspace(unicode_workspace)) == unicode_workspace


def test_empty_and_non_empty_metadata_both_round_trip() -> None:
    workspace = fixture_workspace()
    empty = Workspace(
        symbol=workspace.symbol,
        objective=workspace.objective,
        as_of=workspace.as_of,
        source=workspace.source,
        sections=workspace.sections,
        metadata={},
    )
    assert decode_workspace(encode_workspace(empty)) == empty
    assert decode_workspace(encode_workspace(workspace)) == workspace
    assert workspace.metadata


def test_timezone_aware_but_non_utc_as_of_round_trips() -> None:
    from datetime import timedelta, timezone

    workspace = fixture_workspace()
    shifted = Workspace(
        symbol=workspace.symbol,
        objective=workspace.objective,
        as_of=workspace.as_of.astimezone(timezone(timedelta(hours=-5))),
        source=workspace.source,
        sections=workspace.sections,
        metadata=workspace.metadata,
    )
    assert decode_workspace(encode_workspace(shifted)) == shifted


def test_encode_workspace_rejects_a_non_workspace() -> None:
    with pytest.raises(RecordValidationError):
        encode_workspace("not a workspace")  # type: ignore[arg-type]


# ============ 2. Workspace decode rejects corruption ==========================


def test_decode_workspace_requires_a_json_object() -> None:
    with pytest.raises(CorruptRecordError):
        decode_workspace(["not", "an", "object"])


def test_decode_workspace_rejects_a_missing_field() -> None:
    payload = encode_workspace(fixture_workspace())
    del payload["symbol"]
    with pytest.raises(CorruptRecordError):
        decode_workspace(payload)


def test_decode_workspace_rejects_an_unknown_field() -> None:
    payload = encode_workspace(fixture_workspace())
    payload["unexpected"] = True
    with pytest.raises(CorruptRecordError):
        decode_workspace(payload)


def test_decode_workspace_rejects_a_wrong_primitive_type() -> None:
    payload = encode_workspace(fixture_workspace())
    payload["symbol"] = 123
    with pytest.raises(CorruptRecordError):
        decode_workspace(payload)


def test_decode_workspace_rejects_a_non_int_schema_version() -> None:
    payload = encode_workspace(fixture_workspace())
    payload["schema_version"] = "1"
    with pytest.raises(CorruptRecordError):
        decode_workspace(payload)


def test_decode_workspace_rejects_a_bool_schema_version() -> None:
    payload = encode_workspace(fixture_workspace())
    payload["schema_version"] = True
    with pytest.raises(CorruptRecordError):
        decode_workspace(payload)


def test_decode_workspace_rejects_an_invalid_section_status_enum() -> None:
    payload = encode_workspace(fixture_workspace())
    payload["sections"][0]["status"] = "not-a-status"
    with pytest.raises(CorruptRecordError):
        decode_workspace(payload)


def test_decode_workspace_rejects_an_invalid_section_id_enum() -> None:
    payload = encode_workspace(fixture_workspace())
    payload["sections"][0]["id"] = "not-a-section"
    with pytest.raises(CorruptRecordError):
        decode_workspace(payload)


def test_decode_workspace_rejects_a_naive_as_of() -> None:
    payload = encode_workspace(fixture_workspace())
    payload["as_of"] = "2026-01-01T00:00:00"
    with pytest.raises(CorruptRecordError):
        decode_workspace(payload)


def test_decode_workspace_rejects_a_missing_row_field() -> None:
    payload = encode_workspace(fixture_workspace())
    section = next(s for s in payload["sections"] if s.get("kind") == "section" and s["body"])
    for block in section["body"]:
        if block["kind"] == "row_block" and block["rows"]:
            del block["rows"][0]["label"]
            with pytest.raises(CorruptRecordError):
                decode_workspace(payload)
            return
    pytest.fail("fixture has no row_block with rows to corrupt")


def test_decode_workspace_rejects_an_unknown_block_kind() -> None:
    payload = encode_workspace(fixture_workspace())
    section = next(s for s in payload["sections"] if s.get("kind") == "section" and s["body"])
    section["body"][0]["kind"] = "bogus_block"
    with pytest.raises(CorruptRecordError):
        decode_workspace(payload)


def test_decode_workspace_rejects_an_unknown_section_kind() -> None:
    payload = encode_workspace(fixture_workspace())
    payload["sections"][0]["kind"] = "bogus_section"
    with pytest.raises(CorruptRecordError):
        decode_workspace(payload)


def test_decode_workspace_surfaces_model_validation_as_record_validation_error() -> None:
    # An empty sections tuple decodes cleanly but a Workspace requires every
    # SECTION_ORDER id present exactly once — the model's own __post_init__
    # must still run, proving decode never bypasses it.
    payload = encode_workspace(fixture_workspace())
    payload["sections"] = []
    with pytest.raises(RecordValidationError):
        decode_workspace(payload)


def test_decode_workspace_rejects_a_non_str_metadata_key() -> None:
    payload = encode_workspace(fixture_workspace())
    payload["metadata"] = {"m": {1: "bad key"}}
    with pytest.raises(CorruptRecordError):
        decode_workspace(payload)


# ============ 3. DailyRun round trip =========================================


def test_a_daily_run_with_only_successes_round_trips() -> None:
    run = fixture_daily_run(symbols=("BTCUSDT", "ETHUSDT"), include_failure=False)
    assert decode_daily_run(encode_daily_run(run)) == run


def test_a_daily_run_with_only_failures_round_trips() -> None:
    run = DailyRun(
        reference_time=fixture_daily_run().reference_time,
        results=(fixture_failed_result("SOLUSDT"), fixture_failed_result("ADAUSDT")),
        objective="swing_trade",
        source="binance-spot",
        limitations=(("AN-1", "This is a readiness index, not a ranking."),),
        metadata={},
    )
    assert decode_daily_run(encode_daily_run(run)) == run


def test_a_daily_run_with_a_mix_round_trips() -> None:
    run = fixture_daily_run(symbols=("BTCUSDT",), include_failure=True)
    assert decode_daily_run(encode_daily_run(run)) == run


def test_the_context_section_is_re_derived_not_duplicated_on_the_wire() -> None:
    run = fixture_daily_run(symbols=("BTCUSDT",), include_failure=False)
    payload = encode_daily_run(run)
    assert "context" not in payload["results"][0]
    decoded = decode_daily_run(payload)
    assert decoded.results[0].context == run.results[0].workspace.by_id[SectionId.CONTEXT]
    assert decoded.results[0].context == run.results[0].context


def test_unicode_in_daily_run_survives() -> None:
    run = fixture_daily_run(symbols=("BTCUSDT",))
    unicode_run = DailyRun(
        reference_time=run.reference_time,
        results=run.results,
        objective=run.objective,
        source="binance-spot · 世界",
        limitations=(("AN-1", "état — 東京"),),
        metadata=run.metadata,
    )
    assert decode_daily_run(encode_daily_run(unicode_run)) == unicode_run


def test_encode_daily_run_rejects_a_non_daily_run() -> None:
    with pytest.raises(RecordValidationError):
        encode_daily_run(object())  # type: ignore[arg-type]


# ============ 4. DailyRun decode rejects corruption ===========================


def test_decode_daily_run_rejects_a_missing_field() -> None:
    payload = encode_daily_run(fixture_daily_run())
    del payload["objective"]
    with pytest.raises(CorruptRecordError):
        decode_daily_run(payload)


def test_decode_daily_run_rejects_an_unknown_field() -> None:
    payload = encode_daily_run(fixture_daily_run())
    payload["unexpected"] = 1
    with pytest.raises(CorruptRecordError):
        decode_daily_run(payload)


def test_decode_daily_run_rejects_an_invalid_category_enum() -> None:
    payload = encode_daily_run(fixture_daily_run())
    payload["results"][0]["category"] = "not-a-category"
    with pytest.raises(CorruptRecordError):
        decode_daily_run(payload)


def test_decode_daily_run_rejects_an_invalid_failure_kind_enum() -> None:
    run = DailyRun(
        reference_time=fixture_daily_run().reference_time,
        results=(fixture_failed_result(),),
        objective="swing_trade",
        source="binance-spot",
        limitations=(("AN-1", "text"),),
        metadata={},
    )
    payload = encode_daily_run(run)
    payload["results"][0]["failure"]["kind"] = "not-a-kind"
    with pytest.raises(CorruptRecordError):
        decode_daily_run(payload)


def test_decode_daily_run_rejects_a_non_finite_duration() -> None:
    payload = encode_daily_run(fixture_daily_run())
    payload["results"][0]["duration_seconds"] = "fast"
    with pytest.raises(CorruptRecordError):
        decode_daily_run(payload)


def test_decode_daily_run_rejects_a_malformed_limitation_pair() -> None:
    payload = encode_daily_run(fixture_daily_run())
    payload["limitations"] = [["only-one-item"]]
    with pytest.raises(CorruptRecordError):
        decode_daily_run(payload)


def test_decode_daily_run_surfaces_model_validation_as_record_validation_error() -> None:
    payload = encode_daily_run(fixture_daily_run())
    payload["results"] = []
    with pytest.raises(RecordValidationError):
        decode_daily_run(payload)


def test_decode_daily_run_does_not_mutate_its_input() -> None:
    payload = encode_daily_run(fixture_daily_run())
    before = copy.deepcopy(payload)
    decode_daily_run(payload)
    assert payload == before


def test_decode_daily_run_rejects_a_non_int_schema_version() -> None:
    payload = encode_daily_run(fixture_daily_run())
    payload["schema_version"] = "1"
    with pytest.raises(CorruptRecordError):
        decode_daily_run(payload)


def test_decode_daily_run_surfaces_a_symbol_result_model_failure() -> None:
    """A `SymbolResult` whose own invariant is violated (FAILED but carrying a
    workspace) decodes cleanly at the JSON level, so the failure must come
    from `SymbolResult.__post_init__` itself, caught inside
    `_decode_symbol_result` — not from the outer `DailyRun` constructor."""
    payload = encode_daily_run(fixture_daily_run(symbols=("BTCUSDT",)))
    result = payload["results"][0]
    result["category"] = "failed"
    result["failure"] = {"kind": "provider_failure", "detail": "x", "exception_type": "X"}
    # workspace is left populated, which FAILED forbids.
    with pytest.raises(RecordValidationError):
        decode_daily_run(payload)


# ============ 5. sections without provenance ==================================


def test_a_section_with_no_provenance_round_trips() -> None:
    from fmis.workspace.models import Provenance, Row, RowBlock, Section

    workspace = fixture_workspace()
    original = workspace.by_id[SectionId.INSTRUMENT]
    assert isinstance(original, Section)
    no_provenance = Section(
        id=original.id,
        title=original.title,
        status=SectionStatus.AVAILABLE,
        summary=("a fact",),
        body=(RowBlock(rows=(Row(label="x", value="y"),)),),
        provenance=None,
    )
    sections = tuple(
        no_provenance if s.id == SectionId.INSTRUMENT else s for s in workspace.sections
    )
    replaced = Workspace(
        symbol=workspace.symbol,
        objective=workspace.objective,
        as_of=workspace.as_of,
        source=workspace.source,
        sections=sections,
        metadata=workspace.metadata,
    )
    assert decode_workspace(encode_workspace(replaced)) == replaced
    payload = encode_workspace(replaced)
    encoded_instrument = next(s for s in payload["sections"] if s["id"] == "instrument")
    assert encoded_instrument["provenance"] is None


# ============ 6. defensive branches unreachable through the public API ========


def test_encode_block_rejects_an_unrecognised_type_defensively() -> None:
    from fmis.archive.codec import _encode_block

    with pytest.raises(RecordValidationError):
        _encode_block(object())  # type: ignore[arg-type]


def test_encode_workspace_section_rejects_an_unrecognised_type_defensively() -> None:
    from fmis.archive.codec import _encode_workspace_section

    with pytest.raises(RecordValidationError):
        _encode_workspace_section(object())  # type: ignore[arg-type]


def test_require_list_rejects_a_non_list() -> None:
    payload = encode_workspace(fixture_workspace())
    payload["sections"] = "not-a-list"
    with pytest.raises(CorruptRecordError):
        decode_workspace(payload)


# ============ 7. payload schema-version rejection (review finding P1-1) =======


def test_decode_workspace_rejects_an_unsupported_payload_schema_version() -> None:
    from fmis.archive.errors import UnsupportedSchemaVersionError

    payload = encode_workspace(fixture_workspace())
    payload["schema_version"] = 999
    with pytest.raises(UnsupportedSchemaVersionError):
        decode_workspace(payload)


def test_decode_daily_run_rejects_an_unsupported_payload_schema_version() -> None:
    from fmis.archive.errors import UnsupportedSchemaVersionError

    payload = encode_daily_run(fixture_daily_run())
    payload["schema_version"] = 999
    with pytest.raises(UnsupportedSchemaVersionError):
        decode_daily_run(payload)


def test_decode_daily_run_rejects_an_unsupported_nested_workspace_schema_version() -> None:
    """A nested `Workspace` inside a `DailyRun.results[]` is decoded through
    the same `decode_workspace`, so the version check applies there too."""
    from fmis.archive.errors import UnsupportedSchemaVersionError

    payload = encode_daily_run(fixture_daily_run(symbols=("BTCUSDT",)))
    payload["results"][0]["workspace"]["schema_version"] = 999
    with pytest.raises(UnsupportedSchemaVersionError):
        decode_daily_run(payload)


def test_supported_payload_schema_versions_are_exactly_the_current_ones() -> None:
    from fmis.archive.codec import SUPPORTED_DAILY_SCHEMA_VERSIONS, SUPPORTED_WORKSPACE_SCHEMA_VERSIONS
    from fmis.daily.models import DAILY_SCHEMA_VERSION
    from fmis.workspace.models import WORKSPACE_SCHEMA_VERSION

    assert SUPPORTED_WORKSPACE_SCHEMA_VERSIONS == frozenset({WORKSPACE_SCHEMA_VERSION})
    assert SUPPORTED_DAILY_SCHEMA_VERSIONS == frozenset({DAILY_SCHEMA_VERSION})
