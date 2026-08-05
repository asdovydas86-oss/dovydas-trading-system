"""Record identity: slugs, digests, `record_id` construction and validation."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from fmis.archive.errors import InvalidRecordIdError
from fmis.archive.identity import (
    RECORD_ID_PATTERN,
    build_record_id,
    content_digest,
    parse_record_id,
    slugify_subject,
    validate_record_id,
)

_AS_OF = datetime(2026, 8, 5, 12, 0, 0, tzinfo=timezone.utc)
_DIGEST = "sha256:" + "a" * 64


# ============ 1. slugify_subject =============================================


def test_slugify_keeps_alphanumerics() -> None:
    assert slugify_subject("BTCUSDT") == "BTCUSDT"


def test_slugify_replaces_unsafe_characters() -> None:
    assert slugify_subject("BTC/USDT:perp") == "BTC_USDT_perp"


def test_slugify_caps_length() -> None:
    assert len(slugify_subject("A" * 100)) == 24


def test_slugify_rejects_empty_string() -> None:
    with pytest.raises(InvalidRecordIdError):
        slugify_subject("")


def test_slugify_rejects_non_str() -> None:
    with pytest.raises(InvalidRecordIdError):
        slugify_subject(123)  # type: ignore[arg-type]


def test_slugify_never_returns_empty() -> None:
    assert slugify_subject("///") == "___"
    assert slugify_subject("///") != ""


# ============ 2. content_digest ==============================================


def test_content_digest_is_deterministic() -> None:
    assert content_digest(b"x") == content_digest(b"x")


def test_content_digest_differs_on_different_content() -> None:
    assert content_digest(b"x") != content_digest(b"y")


def test_content_digest_has_the_sha256_prefix_and_length() -> None:
    digest = content_digest(b"anything")
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest)


# ============ 3. build_record_id =============================================


def test_build_record_id_matches_the_pattern() -> None:
    record_id = build_record_id(type_slug="workspace", subject="BTCUSDT", analysis_as_of=_AS_OF, digest=_DIGEST)
    assert RECORD_ID_PATTERN.fullmatch(record_id)


def test_build_record_id_is_deterministic() -> None:
    a = build_record_id(type_slug="workspace", subject="BTCUSDT", analysis_as_of=_AS_OF, digest=_DIGEST)
    b = build_record_id(type_slug="workspace", subject="BTCUSDT", analysis_as_of=_AS_OF, digest=_DIGEST)
    assert a == b


def test_build_record_id_changes_with_digest() -> None:
    a = build_record_id(type_slug="workspace", subject="BTCUSDT", analysis_as_of=_AS_OF, digest=_DIGEST)
    b = build_record_id(
        type_slug="workspace", subject="BTCUSDT", analysis_as_of=_AS_OF, digest="sha256:" + "b" * 64
    )
    assert a != b


def test_build_record_id_uses_utc_regardless_of_input_offset() -> None:
    from datetime import timedelta

    plus5 = _AS_OF.astimezone(timezone(timedelta(hours=5)))  # same instant, different offset
    a = build_record_id(type_slug="workspace", subject="BTCUSDT", analysis_as_of=_AS_OF, digest=_DIGEST)
    b = build_record_id(type_slug="workspace", subject="BTCUSDT", analysis_as_of=plus5, digest=_DIGEST)
    assert a == b


def test_build_record_id_rejects_bad_type_slug() -> None:
    with pytest.raises(InvalidRecordIdError):
        build_record_id(type_slug="bogus", subject="BTCUSDT", analysis_as_of=_AS_OF, digest=_DIGEST)


def test_build_record_id_rejects_naive_datetime() -> None:
    with pytest.raises(InvalidRecordIdError):
        build_record_id(type_slug="workspace", subject="BTCUSDT", analysis_as_of=datetime(2026, 1, 1), digest=_DIGEST)


def test_build_record_id_rejects_non_datetime() -> None:
    with pytest.raises(InvalidRecordIdError):
        build_record_id(type_slug="workspace", subject="BTCUSDT", analysis_as_of="2026-01-01", digest=_DIGEST)  # type: ignore[arg-type]


def test_build_record_id_rejects_a_malformed_digest() -> None:
    with pytest.raises(InvalidRecordIdError):
        build_record_id(type_slug="workspace", subject="BTCUSDT", analysis_as_of=_AS_OF, digest="not-a-digest")


def test_build_record_id_daily_uses_the_daily_type_slug() -> None:
    record_id = build_record_id(type_slug="daily", subject="3sym", analysis_as_of=_AS_OF, digest=_DIGEST)
    assert record_id.startswith("daily-3sym-")


# ============ 4. validate_record_id / parse_record_id ========================


def test_validate_accepts_a_well_formed_id() -> None:
    record_id = build_record_id(type_slug="workspace", subject="BTCUSDT", analysis_as_of=_AS_OF, digest=_DIGEST)
    validate_record_id(record_id)  # does not raise


@pytest.mark.parametrize(
    "bad_id",
    [
        "../../etc/passwd",
        "workspace-BTC/USDT-20260805T120000Z-aaaaaaaa",
        "workspace-BTCUSDT-20260805T120000Z-aaaaaaaa/../x",
        "workspace-BTCUSDT-20260805T120000Z-aaaaaaaa\\x",
        "not-a-record-id",
        "",
        "workspace-BTCUSDT-20260805T120000Z-AAAAAAAA",  # digest must be lowercase hex
        "workspace-BTCUSDT-2026-08-05-aaaaaaaa",  # wrong timestamp shape
        "unknown-BTCUSDT-20260805T120000Z-aaaaaaaa",  # unknown type slug
        "workspace-" + "X" * 40 + "-20260805T120000Z-aaaaaaaa",  # subject too long
    ],
)
def test_validate_rejects_every_malformed_shape(bad_id: str) -> None:
    with pytest.raises(InvalidRecordIdError):
        validate_record_id(bad_id)


def test_validate_rejects_non_str() -> None:
    with pytest.raises(InvalidRecordIdError):
        validate_record_id(12345)  # type: ignore[arg-type]


def test_parse_record_id_exposes_components() -> None:
    record_id = build_record_id(type_slug="daily", subject="3sym", analysis_as_of=_AS_OF, digest=_DIGEST)
    match = parse_record_id(record_id)
    assert match.group("type_slug") == "daily"
    assert match.group("subject_slug") == "3sym"
    assert match.group("timestamp") == "20260805T120000Z"


def test_parse_record_id_rejects_malformed_input() -> None:
    with pytest.raises(InvalidRecordIdError):
        parse_record_id("../escape")
