"""Pattern detection — deterministic candlestick and chart patterns (Tier 2).

Single responsibility: detect patterns that have **explicit, rule-based
definitions** from price/structure, producing reproducible boolean/labelled
results. Category: ``FeatureCategory.PATTERN``.

Scope: only deterministic, explicitly-defined patterns belong here. Subjective
or contextual chart-pattern *interpretation* — the kind a human or an AI does by
judgment — is NOT part of this package or the Feature Engine; it belongs to a
separate AI/interpretation layer.

Planned features (NOT implemented yet):
    TODO: candlestick patterns with fixed rules (engulfing, hammer, shooting
          star, doji, ...)
    TODO: chart patterns with explicit geometric definitions (double top/bottom,
          head & shoulders, triangles, ...)
    TODO: pattern location context (at a detected support / resistance level)
Performs no math in this milestone.
"""

from __future__ import annotations

__all__: list[str] = []
