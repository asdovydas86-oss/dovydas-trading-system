"""Record identity: `record_id` construction, validation, and content digest.

ADR-0027 §4. A record ID is content-derived — `{type_slug}-{subject_slug}-
{compact_utc_timestamp}-{digest_prefix}` — so two archive calls producing
byte-identical content produce the identical ID, and the "same identity,
different content" scenario reduces to a digest-prefix collision, handled
explicitly by `fmis.archive.storage` rather than assumed unreachable.

`digest_prefix` is **16 lowercase hex characters (64 bits)**. An 8-character
(32-bit) prefix was the v1a draft and was rejected before release: a durable
archive whose IDs are meant to become stable references for future work
(journals, comparisons, outcome tracking, dashboards) needs a birthday bound
that stays negligible at realistic long-term record counts, not merely
"unlikely today" — 32 bits reaches meaningful collision probability in the
tens-of-thousands of records; 64 bits does not at any volume this product
could plausibly reach. The full SHA-256 `content_digest` is still stored on
every record regardless — the prefix is only ever a *display and lookup*
convenience carved out of it, never the integrity check itself.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from fmis.archive.errors import InvalidRecordIdError

__all__ = [
    "RECORD_ID_PATTERN",
    "DIGEST_PREFIX_LENGTH",
    "MAXIMUM_SUBJECT_SLUG_LENGTH",
    "slugify_subject",
    "content_digest",
    "build_record_id",
    "validate_record_id",
    "parse_record_id",
]

#: Every character a record ID may contain, and the exact shape it must take.
#: Deliberately narrow: this is joined onto a filesystem path, so the pattern
#: is the whole of the path-traversal defense at the identity layer — nothing
#: matching it can contain "..", "/", or any other path-meaningful character.
#: The digest component is exactly 16 lowercase hex characters (64 bits) —
#: see the module docstring for why 8 (32 bits) was rejected before release.
RECORD_ID_PATTERN = re.compile(
    r"^(?P<type_slug>workspace|daily)-"
    r"(?P<subject_slug>[A-Za-z0-9_]{1,24})-"
    r"(?P<timestamp>\d{8}T\d{6}Z)-"
    r"(?P<digest_prefix>[0-9a-f]{16})$"
)

#: The number of hex characters `build_record_id` carves out of `content_digest`
#: for the id's own digest component. A named constant so every place that
#: needs to know the length agrees with the pattern above by construction.
DIGEST_PREFIX_LENGTH = 16

MAXIMUM_SUBJECT_SLUG_LENGTH = 24

_SAFE_SLUG_CHARACTER = re.compile(r"[A-Za-z0-9]")


def slugify_subject(text: str) -> str:
    """Replace every character outside `[A-Za-z0-9]` with `_`, capped in length.

    Never raises: a record ID must always be constructible from any valid
    `symbol`/`objective` string a domain model already accepted, and
    over-substitution (turning an unusual symbol into a run of underscores) is
    safe where under-rejection would not be.
    """
    if not isinstance(text, str) or not text:
        raise InvalidRecordIdError("subject text must be a non-empty str")
    slug = "".join(ch if _SAFE_SLUG_CHARACTER.fullmatch(ch) else "_" for ch in text)
    slug = slug[:MAXIMUM_SUBJECT_SLUG_LENGTH]
    return slug or "_"


def content_digest(canonical_bytes: bytes) -> str:
    """`sha256:<hex>` over already-canonical bytes."""
    return "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()


def build_record_id(
    *, type_slug: str, subject: str, analysis_as_of: datetime, digest: str
) -> str:
    if type_slug not in ("workspace", "daily"):
        raise InvalidRecordIdError(f"type_slug must be 'workspace' or 'daily', got {type_slug!r}")
    if not isinstance(analysis_as_of, datetime):
        raise InvalidRecordIdError("analysis_as_of must be a datetime")
    if analysis_as_of.tzinfo is None:
        raise InvalidRecordIdError("analysis_as_of must be timezone-aware")
    if not digest.startswith("sha256:") or len(digest) != len("sha256:") + 64:
        raise InvalidRecordIdError(f"digest must be a sha256:<64-hex> string, got {digest!r}")
    subject_slug = slugify_subject(subject)
    compact = analysis_as_of.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    digest_prefix = digest[len("sha256:") :][:DIGEST_PREFIX_LENGTH]
    record_id = f"{type_slug}-{subject_slug}-{compact}-{digest_prefix}"
    validate_record_id(record_id)
    return record_id


def validate_record_id(record_id: str) -> None:
    """Raise `InvalidRecordIdError` unless `record_id` matches `RECORD_ID_PATTERN` exactly.

    Called on every use, not only at write time (ADR-0027 §4): a record ID
    typed at the CLI is exactly as untrusted as one read from a corrupted
    manifest line.
    """
    if not isinstance(record_id, str):
        raise InvalidRecordIdError(f"record_id must be a str, got {type(record_id).__name__}")
    if ".." in record_id or "/" in record_id or "\\" in record_id:
        raise InvalidRecordIdError(f"record_id {record_id!r} contains a path-traversal character")
    if not RECORD_ID_PATTERN.fullmatch(record_id):
        raise InvalidRecordIdError(f"record_id {record_id!r} does not match the expected shape")


def parse_record_id(record_id: str) -> re.Match[str]:
    """Validate and return the regex match, so callers can read the components."""
    validate_record_id(record_id)
    match = RECORD_ID_PATTERN.fullmatch(record_id)
    assert match is not None  # validate_record_id already proved this
    return match
