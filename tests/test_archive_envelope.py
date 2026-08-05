"""Direct tests for `ArchiveEnvelope` construction and `decode_envelope`.

`fmis.archive.storage` only ever builds valid envelopes, so the defensive
validation in `ArchiveEnvelope.__post_init__` and every corruption branch in
`decode_envelope` needs its own direct coverage here.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmis.archive.envelope import (
    ARCHIVE_SCHEMA_VERSION,
    ArchiveEnvelope,
    RecordType,
    decode_envelope,
    encode_envelope,
)
from fmis.archive.errors import (
    CorruptRecordError,
    InvalidRecordIdError,
    UnsupportedRecordTypeError,
    UnsupportedSchemaVersionError,
)
from fmis.archive.identity import build_record_id

_AS_OF = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)
_DIGEST = "sha256:" + "a" * 64
_RECORD_ID = build_record_id(type_slug="workspace", subject="BTCUSDT", analysis_as_of=_AS_OF, digest=_DIGEST)


def _valid_kwargs(**overrides: object) -> dict:
    kwargs = dict(
        record_type=RecordType.WORKSPACE,
        schema_version=ARCHIVE_SCHEMA_VERSION,
        record_id=_RECORD_ID,
        archived_at=_AS_OF,
        analysis_as_of=_AS_OF,
        subject=("BTCUSDT",),
        payload={"x": 1},
        content_digest=_DIGEST,
    )
    kwargs.update(overrides)
    return kwargs


def test_a_valid_envelope_constructs() -> None:
    ArchiveEnvelope(**_valid_kwargs())  # does not raise


def test_rejects_a_non_record_type() -> None:
    with pytest.raises(TypeError):
        ArchiveEnvelope(**_valid_kwargs(record_type="workspace"))


def test_rejects_a_non_int_schema_version() -> None:
    with pytest.raises(TypeError):
        ArchiveEnvelope(**_valid_kwargs(schema_version="1"))


def test_rejects_a_naive_archived_at() -> None:
    with pytest.raises(TypeError):
        ArchiveEnvelope(**_valid_kwargs(archived_at=datetime(2026, 1, 1)))


def test_rejects_a_naive_analysis_as_of() -> None:
    with pytest.raises(TypeError):
        ArchiveEnvelope(**_valid_kwargs(analysis_as_of=datetime(2026, 1, 1)))


def test_rejects_an_empty_subject() -> None:
    with pytest.raises(TypeError):
        ArchiveEnvelope(**_valid_kwargs(subject=()))


def test_rejects_a_subject_that_is_not_a_tuple() -> None:
    with pytest.raises(TypeError):
        ArchiveEnvelope(**_valid_kwargs(subject=["BTCUSDT"]))


def test_rejects_a_blank_subject_entry() -> None:
    with pytest.raises(TypeError):
        ArchiveEnvelope(**_valid_kwargs(subject=("",)))


def test_rejects_a_non_dict_payload() -> None:
    with pytest.raises(TypeError):
        ArchiveEnvelope(**_valid_kwargs(payload=["not", "a", "dict"]))


def test_rejects_a_content_digest_without_the_sha256_prefix() -> None:
    with pytest.raises(TypeError):
        ArchiveEnvelope(**_valid_kwargs(content_digest="a" * 64))


def test_rejects_a_malformed_record_id() -> None:
    with pytest.raises(InvalidRecordIdError):
        ArchiveEnvelope(**_valid_kwargs(record_id="not-a-record-id"))


def test_encode_decode_round_trips() -> None:
    envelope = ArchiveEnvelope(**_valid_kwargs())
    decoded = decode_envelope(__import__("json").loads(encode_envelope(envelope)))
    assert decoded == envelope


def test_supported_schema_versions_is_exactly_one() -> None:
    # Pins the exact set, not just "999 is rejected" — a widened set that
    # still excludes 999 would otherwise pass every other test in this file.
    from fmis.archive.envelope import SUPPORTED_SCHEMA_VERSIONS

    assert SUPPORTED_SCHEMA_VERSIONS == frozenset({1})


def test_content_digest_is_a_golden_value_over_a_fixed_input() -> None:
    """Pins the exact set of fields `_digest_basis` covers.

    `compute_content_digest` is deterministic and excludes `record_id` and
    `archived_at` by construction (ADR-0027 §3) — but that exclusion alone
    does not prove *nothing else* was added to the basis, because an added
    field with a constant value would still leave "same content -> same
    digest" and "different content -> different digest" both holding. A
    golden hash over one fixed input is the only test that actually pins the
    exact composition.
    """
    from fmis.archive.envelope import compute_content_digest

    digest = compute_content_digest(
        record_type=RecordType.WORKSPACE,
        schema_version=ARCHIVE_SCHEMA_VERSION,
        analysis_as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        subject=("BTCUSDT",),
        payload={"a": 1},
    )
    assert digest == "sha256:9a9ecf40d694d9533e1ef2ec7374ecc767dc6018a3003c66387156e87fc34865"


# ============ decode_envelope corruption branches ============================


def _valid_raw() -> dict:
    return {
        "record_type": "workspace",
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "record_id": _RECORD_ID,
        "archived_at": _AS_OF.isoformat(),
        "analysis_as_of": _AS_OF.isoformat(),
        "subject": ["BTCUSDT"],
        "payload": {"x": 1},
        "content_digest": _DIGEST,
    }


def test_decode_envelope_requires_a_json_object() -> None:
    with pytest.raises(CorruptRecordError):
        decode_envelope(["not", "an", "object"])


def test_decode_envelope_rejects_a_missing_field() -> None:
    raw = _valid_raw()
    del raw["payload"]
    with pytest.raises(CorruptRecordError):
        decode_envelope(raw)


def test_decode_envelope_rejects_an_unknown_field() -> None:
    raw = _valid_raw()
    raw["unexpected"] = 1
    with pytest.raises(CorruptRecordError):
        decode_envelope(raw)


def test_decode_envelope_rejects_a_non_str_record_type() -> None:
    raw = _valid_raw()
    raw["record_type"] = 1
    with pytest.raises(CorruptRecordError):
        decode_envelope(raw)


def test_decode_envelope_rejects_an_unknown_record_type() -> None:
    raw = _valid_raw()
    raw["record_type"] = "bogus"
    with pytest.raises(UnsupportedRecordTypeError):
        decode_envelope(raw)


def test_decode_envelope_rejects_a_non_int_schema_version() -> None:
    raw = _valid_raw()
    raw["schema_version"] = "1"
    with pytest.raises(CorruptRecordError):
        decode_envelope(raw)


def test_decode_envelope_rejects_a_bool_schema_version() -> None:
    raw = _valid_raw()
    raw["schema_version"] = True
    with pytest.raises(CorruptRecordError):
        decode_envelope(raw)


def test_decode_envelope_rejects_an_unsupported_schema_version() -> None:
    raw = _valid_raw()
    raw["schema_version"] = 999
    with pytest.raises(UnsupportedSchemaVersionError):
        decode_envelope(raw)


def test_decode_envelope_rejects_a_non_str_record_id() -> None:
    raw = _valid_raw()
    raw["record_id"] = 1
    with pytest.raises(CorruptRecordError):
        decode_envelope(raw)


def test_decode_envelope_rejects_a_malformed_record_id() -> None:
    raw = _valid_raw()
    raw["record_id"] = "not-a-record-id"
    with pytest.raises(InvalidRecordIdError):
        decode_envelope(raw)


def test_decode_envelope_rejects_a_non_list_subject() -> None:
    raw = _valid_raw()
    raw["subject"] = "BTCUSDT"
    with pytest.raises(CorruptRecordError):
        decode_envelope(raw)


def test_decode_envelope_rejects_an_empty_subject() -> None:
    raw = _valid_raw()
    raw["subject"] = []
    with pytest.raises(CorruptRecordError):
        decode_envelope(raw)


def test_decode_envelope_rejects_a_non_str_subject_entry() -> None:
    raw = _valid_raw()
    raw["subject"] = [1]
    with pytest.raises(CorruptRecordError):
        decode_envelope(raw)


def test_decode_envelope_rejects_a_non_dict_payload() -> None:
    raw = _valid_raw()
    raw["payload"] = ["not", "a", "dict"]
    with pytest.raises(CorruptRecordError):
        decode_envelope(raw)


def test_decode_envelope_rejects_a_non_str_content_digest() -> None:
    raw = _valid_raw()
    raw["content_digest"] = 12345
    with pytest.raises(CorruptRecordError):
        decode_envelope(raw)
