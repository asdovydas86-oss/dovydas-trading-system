"""Temporal-comparison policy layer.

Alignment answers "how are two or more canonical series made comparable in
time?" — a *policy* concern, kept deliberately separate from the canonical data
models in ``fmis.data`` (which answer "what is a series?"). See ADR-0002.

Strict timestamp intersection is the first policy implemented here. Future
policies (as-of joins, resampling, availability-aware and calendar-aware
alignment) will join this package as siblings; none may silently invent data —
each must be explicit, named, and reported.

Dependency direction: ``fmis.alignment`` imports the canonical models it aligns
(``fmis.data``) and nothing downstream. Canonical models never import alignment.
"""

from __future__ import annotations

from fmis.alignment.intersection import (
    AlignmentReport,
    AlignmentResult,
    SeriesAlignmentStats,
    align_intersection,
)

__all__ = [
    "align_intersection",
    "AlignmentResult",
    "AlignmentReport",
    "SeriesAlignmentStats",
]
