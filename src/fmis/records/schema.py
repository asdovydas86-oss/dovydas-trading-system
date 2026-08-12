"""Payload version handling — one forward-only reader contract, stated once.

`AP` §5.7 and the investigation's Option A, implemented rather than restated:

1. **No published byte is ever rewritten.** Nothing in this package writes; the
   only thing it does to an old payload is *read* it.
2. **Every bump ships readers for all prior versions.** `SUPPORTED_VERSIONS` on
   each record type is a set, never a single number, and `require_payload_version`
   returns the version that was read so a decoder can branch on it.
3. **An unknown version is a clean rejection**, never a best-effort parse.
4. **A field introduced in a later version reads as absent on an older record,
   never as zero and never as a default** — `field_introduced_in` produces the
   `Absent` reason text `AP_ADR_DISCOVERY` AP-D17 asks for, so a bias metric
   degrading across a version boundary is visible instead of silent.

Unknown keys are rejected as hard as unknown versions. A payload carrying a field
this build does not know about was written by a newer build, and reading it while
ignoring that field is exactly how a "successful" load loses data.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any

from fmis.records.errors import PayloadDecodeError, UnsupportedPayloadVersionError

__all__ = [
    "SCHEMA_VERSION_KEY",
    "require_mapping",
    "require_payload_version",
    "require_exact_keys",
    "field_introduced_in",
]

#: The one key every serialized domain payload carries.
SCHEMA_VERSION_KEY = "schema_version"


def require_mapping(raw: Any, entity: str) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise PayloadDecodeError(
            f"{entity} payload must be a JSON object, got {type(raw).__name__}"
        )
    for key in raw:
        if not isinstance(key, str):
            raise PayloadDecodeError(f"{entity} payload has a non-str key {key!r}")
    return raw


def require_payload_version(
    raw: Mapping[str, Any], *, supported: Collection[int], entity: str
) -> int:
    """Read and check `schema_version`, returning the version that was read."""
    if SCHEMA_VERSION_KEY not in raw:
        raise PayloadDecodeError(f"{entity} payload is missing {SCHEMA_VERSION_KEY!r}")
    version = raw[SCHEMA_VERSION_KEY]
    if isinstance(version, bool) or not isinstance(version, int):
        raise PayloadDecodeError(f"{entity} {SCHEMA_VERSION_KEY} must be an int")
    if version not in supported:
        raise UnsupportedPayloadVersionError(
            f"{entity} schema_version {version} is not supported; this build "
            f"reads {sorted(supported)}"
        )
    return version


def require_exact_keys(
    raw: Mapping[str, Any], expected: Collection[str], entity: str
) -> None:
    """Reject a payload whose key set is not exactly `expected`.

    Both directions matter and for different reasons: a missing key means the
    record is incomplete, and an unknown key means a newer build wrote something
    this one would silently drop.
    """
    present = set(raw)
    wanted = set(expected)
    missing = wanted - present
    if missing:
        raise PayloadDecodeError(
            f"{entity} payload is missing field(s) {sorted(missing)}"
        )
    unknown = present - wanted
    if unknown:
        raise PayloadDecodeError(
            f"{entity} payload has unknown field(s) {sorted(unknown)}; it was "
            "written by a newer build and reading it would drop them"
        )


def field_introduced_in(field: str, version: int) -> str:
    """The absence reason an older record must report for a newer field.

    Written as a function rather than an f-string at each call site so every
    coverage gap in the domain reads identically and a surface can recognise the
    class without parsing prose.
    """
    return f"{field} was introduced in schema version {version}"
