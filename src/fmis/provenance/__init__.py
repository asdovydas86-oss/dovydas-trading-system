"""Provenance vocabulary for the trading domain.

`ValueOrigin` · `Absent[T]` · `Assertion[T]` · `VersionedTerm`. Imports the
record spine and nothing else from `fmis` — every other domain package imports
this one, so anything it reached would become a dependency of the whole domain.
"""

from __future__ import annotations

from fmis.provenance.models import (
    CORRECTABLE_ORIGINS,
    Absent,
    Assertion,
    ProvenanceError,
    ValueOrigin,
    VersionedTerm,
    decode_maybe,
    encode_maybe,
)

__all__ = [
    "ProvenanceError",
    "ValueOrigin",
    "CORRECTABLE_ORIGINS",
    "Absent",
    "Assertion",
    "VersionedTerm",
    "encode_maybe",
    "decode_maybe",
]
