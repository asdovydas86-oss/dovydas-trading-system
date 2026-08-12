"""One content-addressed version bundle per captured artifact.

`VersionAxis` · `VersionSet` · `deduplicate`. Imports `fmis.provenance` and the
record spine, and nothing else.
"""

from __future__ import annotations

from fmis.versioning.models import (
    AXIS_ORDER,
    SUPPORTED_VERSION_SET_VERSIONS,
    VERSION_SET_SCHEMA_VERSION,
    VersionAxis,
    VersioningError,
    VersionSet,
    deduplicate,
)

__all__ = [
    "VersioningError",
    "VersionAxis",
    "AXIS_ORDER",
    "VersionSet",
    "deduplicate",
    "VERSION_SET_SCHEMA_VERSION",
    "SUPPORTED_VERSION_SET_VERSIONS",
]
