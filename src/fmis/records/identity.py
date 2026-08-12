"""Content-derived identity for every trading-domain record.

`{type_slug}-{subject_slug}-{compact_UTC}-{digest_prefix}` — ADR-0027 §4's shape,
applied to the domain. Two records with byte-identical economic content produce
the identical id, which is what makes re-entering a fill after a crash an
idempotent success rather than a second position-moving event.

**The digest covers the economic fields only.** `recorded_at`, `source`,
`asserted_by` and `capture_schema_version` are excluded, following ADR-0027 §3's
own precedent for `archived_at` — the review's C1 showed their inclusion breaks
idempotency three ways and would double-count every manual fill on the day
exchange sync ships. Each record type states its own basis; this module supplies
the digest and the id, never the choice of what goes in them.

**The canonical encoder is reused, never reimplemented.** `canonical_dumps` is
frozen in shipped, released code and is already load-bearing for `AO`'s records.
A second encoder in this package would be a second definition of "the bytes",
which is Law 1's failure at the level of a function.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fmis.archive.identity import content_digest as _sha256_over_bytes
from fmis.archive.json_safe import canonical_dumps
from fmis.records.errors import DomainValidationError
from fmis.records.validation import require_text, require_utc

__all__ = [
    "DOMAIN_RECORD_ID_PATTERN",
    "DIGEST_PREFIX_LENGTH",
    "MAXIMUM_SUBJECT_SLUG_LENGTH",
    "TYPE_SLUG_PATTERN",
    "slugify",
    "content_digest_over",
    "build_domain_record_id",
    "validate_domain_record_id",
    "parse_domain_record_id",
    "digest_prefix_of",
]

#: The number of hex characters carved out of the full SHA-256 for the id.
#: Sixteen (64 bits), matching `fmis.archive` — an 8-character prefix reaches
#: meaningful collision probability in the tens of thousands of records, and this
#: domain expects roughly 50,000 artifacts over a decade.
DIGEST_PREFIX_LENGTH = 16

MAXIMUM_SUBJECT_SLUG_LENGTH = 32

#: Which type slugs are structurally legal. Deliberately a *pattern* rather than
#: a closed enum: a closed enum here would make `fmis.records` import every
#: package that owns a record type, inverting the dependency direction the whole
#: layout exists to protect. Each package pins its own slug as a constant, and a
#: test asserts the set is unique across the domain.
TYPE_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,31}$")

DOMAIN_RECORD_ID_PATTERN = re.compile(
    r"^(?P<type_slug>[a-z][a-z0-9_]{1,31})-"
    r"(?P<subject_slug>[A-Za-z0-9_]{1,32})-"
    r"(?P<timestamp>\d{8}T\d{6}Z)-"
    r"(?P<digest_prefix>[0-9a-f]{16})$"
)

_SAFE_SLUG_CHARACTER = re.compile(r"[A-Za-z0-9]")


def slugify(text: str) -> str:
    """Every character outside `[A-Za-z0-9]` becomes `_`, capped in length.

    Over-substitution is safe here and under-rejection is not: a record id must
    always be constructible from any subject a domain model already accepted, and
    a market id legitimately contains `:`.
    """
    source = require_text(text, "subject")
    slug = "".join(
        character if _SAFE_SLUG_CHARACTER.fullmatch(character) else "_"
        for character in source
    )
    slug = slug[:MAXIMUM_SUBJECT_SLUG_LENGTH]
    return slug or "_"


def content_digest_over(basis: Mapping[str, Any]) -> str:
    """`sha256:<hex>` over the canonical encoding of a digest basis.

    The basis must already be JSON-safe — every record type builds it from its
    own `to_payload`-shaped values, so a type that cannot be serialized cannot be
    identified either, and the two can never drift apart.
    """
    if not isinstance(basis, Mapping):
        raise TypeError(f"basis must be a Mapping, got {type(basis).__name__}")
    return _sha256_over_bytes(canonical_dumps(dict(basis)))


def digest_prefix_of(digest: str) -> str:
    """The id component carved out of a full `sha256:<hex>` digest."""
    text = require_text(digest, "digest")
    if not text.startswith("sha256:") or len(text) != len("sha256:") + 64:
        raise DomainValidationError(
            f"digest must be a 'sha256:<64 hex>' string, got {text!r}"
        )
    return text[len("sha256:") :][:DIGEST_PREFIX_LENGTH]


def build_domain_record_id(
    *, type_slug: str, subject: str, moment: datetime, digest: str
) -> str:
    """Assemble — and validate — a content-derived record id."""
    slug = require_text(type_slug, "type_slug")
    if not TYPE_SLUG_PATTERN.fullmatch(slug):
        raise DomainValidationError(
            f"type_slug {slug!r} does not match {TYPE_SLUG_PATTERN.pattern}"
        )
    compact = require_utc(moment, "moment").strftime("%Y%m%dT%H%M%SZ")
    record_id = f"{slug}-{slugify(subject)}-{compact}-{digest_prefix_of(digest)}"
    validate_domain_record_id(record_id)
    return record_id


def validate_domain_record_id(record_id: Any) -> str:
    """Raise unless `record_id` has exactly the expected shape.

    Called on every *use*, not only at construction: an id typed at a CLI is
    exactly as untrusted as one read from a corrupted file.
    """
    if not isinstance(record_id, str):
        raise TypeError(f"record_id must be a str, got {type(record_id).__name__}")
    if ".." in record_id or "/" in record_id or "\\" in record_id:
        raise DomainValidationError(
            f"record_id {record_id!r} contains a path-traversal character"
        )
    if not DOMAIN_RECORD_ID_PATTERN.fullmatch(record_id):
        raise DomainValidationError(
            f"record_id {record_id!r} does not match the expected shape "
            "'{type}-{subject}-{YYYYMMDDThhmmssZ}-{16 hex}'"
        )
    return record_id


def parse_domain_record_id(record_id: str) -> re.Match[str]:
    """Validate, and return the match so a caller can read the components."""
    validate_domain_record_id(record_id)
    match = DOMAIN_RECORD_ID_PATTERN.fullmatch(record_id)
    assert match is not None  # validate_domain_record_id already proved this
    return match
