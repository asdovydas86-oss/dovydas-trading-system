"""Relative Value Engine (v1a) — deterministic relationship metrics.

Measures objective relationships between two or more already-aligned series (and
per-series summaries), producing reproducible, auditable numbers. It answers
*"how does A relate to B?"* — a question the single-instrument Feature Engine
cannot express, because a relationship has no single symbol.

v1a is deliberately small: five scalar metrics (`period_return`,
`relative_return`, `realized_volatility`, `volatility_ratio`,
`pearson_correlation`), simple returns only, no annualization, no rolling
windows. See ADR-0004 and `docs/RVE_DESIGN_V1.md`.

Scope boundary — the RVE is **fact-only**. It never emits LONG/SHORT/BUY/SELL,
scores, rankings, confidence values, labels, or recommendations, and never
performs AI interpretation.

Dependency boundary: this package imports only canonical models from `fmis.data`.
It does **not** import `fmis.features`, and it does **not** call `fmis.alignment`
internally — alignment is an explicit upstream policy the caller performs before
calling any pairwise metric.
"""

from __future__ import annotations

from fmis.relative_value.metrics import (
    pearson_correlation,
    period_return,
    realized_volatility,
    relative_return,
    volatility_ratio,
)
from fmis.relative_value.models import (
    InsufficientObservationsError,
    MetricStatus,
    NotAlignedError,
    RelativeValueError,
    RelativeValueResult,
    UndefinedReason,
)

__all__ = [
    # metrics
    "period_return",
    "relative_return",
    "realized_volatility",
    "volatility_ratio",
    "pearson_correlation",
    # models
    "RelativeValueResult",
    "MetricStatus",
    "UndefinedReason",
    "RelativeValueError",
    "NotAlignedError",
    "InsufficientObservationsError",
]
