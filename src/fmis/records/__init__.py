"""The trading domain's record spine — identity, audit, provenance, versioning.

Every entity in the owner half of FMITS answers the same four structural
questions, and answering them thirteen times would produce thirteen slightly
different answers. This package answers them once:

* **identity** — content-derived ids over a digest of the *economic* fields only;
* **audit** — `created_at` / `updated_at`, with "frozen" enforced rather than
  documented;
* **provenance** — the ids and digests of everything a captured artifact read
  (Law 8);
* **versioning** — a forward-only reader contract with clean rejection.

It imports `fmis.archive.json_safe` and `fmis.archive.identity` for the canonical
encoder and the SHA-256 helper, and nothing else from `fmis`. Those two are
already frozen, already shipped and already load-bearing for the archive's own
records; reimplementing them here would create a second definition of "the
bytes", which is Law 1's failure at the level of a function.
"""

from __future__ import annotations

from fmis.records.audit import (
    ConsumedSource,
    RecordAudit,
    decode_consumed_sources,
    encode_consumed_sources,
    normalize_consumed_sources,
    require_unmodified,
)
from fmis.records.errors import (
    DomainStateError,
    DomainValidationError,
    PayloadDecodeError,
    TradeDomainError,
    UnsupportedPayloadVersionError,
)
from fmis.records.identity import (
    DIGEST_PREFIX_LENGTH,
    DOMAIN_RECORD_ID_PATTERN,
    MAXIMUM_SUBJECT_SLUG_LENGTH,
    TYPE_SLUG_PATTERN,
    build_domain_record_id,
    content_digest_over,
    digest_prefix_of,
    parse_domain_record_id,
    slugify,
    validate_domain_record_id,
)
from fmis.records.schema import (
    SCHEMA_VERSION_KEY,
    field_introduced_in,
    require_exact_keys,
    require_mapping,
    require_payload_version,
)
from fmis.records.validation import (
    IDENTIFIER_PATTERN,
    SLUG_PATTERN,
    require_bool,
    require_int,
    require_member,
    require_optional_text,
    require_optional_utc,
    require_ordered,
    require_pattern,
    require_text,
    require_tuple_of,
    require_utc,
)

__all__ = [
    # errors
    "TradeDomainError",
    "DomainValidationError",
    "DomainStateError",
    "PayloadDecodeError",
    "UnsupportedPayloadVersionError",
    # audit and provenance
    "RecordAudit",
    "ConsumedSource",
    "normalize_consumed_sources",
    "require_unmodified",
    "encode_consumed_sources",
    "decode_consumed_sources",
    # identity
    "DOMAIN_RECORD_ID_PATTERN",
    "TYPE_SLUG_PATTERN",
    "DIGEST_PREFIX_LENGTH",
    "MAXIMUM_SUBJECT_SLUG_LENGTH",
    "slugify",
    "content_digest_over",
    "digest_prefix_of",
    "build_domain_record_id",
    "validate_domain_record_id",
    "parse_domain_record_id",
    # schema
    "SCHEMA_VERSION_KEY",
    "require_mapping",
    "require_payload_version",
    "require_exact_keys",
    "field_introduced_in",
    # validation
    "IDENTIFIER_PATTERN",
    "SLUG_PATTERN",
    "require_text",
    "require_optional_text",
    "require_utc",
    "require_optional_utc",
    "require_int",
    "require_bool",
    "require_member",
    "require_tuple_of",
    "require_pattern",
    "require_ordered",
]
