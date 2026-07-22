"""FeatureEngine — orchestrator that turns a CandleSeries into a FeatureSet.

The engine's job is coordination only: given a price series and a set of feature
names, resolve their dependency order, run each feature once, and assemble the
results into a single ``FeatureSet``. It performs **no indicator math itself** —
all math lives in the individual ``Feature`` implementations added in later
milestones.

``compute`` is intentionally left unimplemented in this architecture milestone.
The algorithm is specified in its docstring so the contract is fixed before any
calculation is written.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Mapping

from fmis.data import CandleSeries
from fmis.features.registry import FeatureRegistry
from fmis.features.types import FeatureSet

__all__ = ["FeatureEngine"]


class FeatureEngine:
    """Runs registered features against a price series to build a FeatureSet."""

    def __init__(self, registry: FeatureRegistry) -> None:
        self._registry = registry

    @property
    def registry(self) -> FeatureRegistry:
        return self._registry

    def compute(
        self,
        series: CandleSeries,
        names: Sequence[str] | None = None,
        *,
        sources: Mapping[str, Any] | None = None,
    ) -> FeatureSet:
        """Build a FeatureSet for ``series``.

        Planned algorithm (implemented in the Milestone C computation phase):
            1. Select the target features: ``names`` if given, else all
               registered features.
            2. Expand and topologically sort them by ``dependencies`` so every
               feature runs after the features it reads. Detect and reject
               dependency cycles.
            3. Build a FeatureContext (primary=series, computed={}, sources=...),
               and run each feature in order, adding its FeatureResult to
               ``computed`` so later features can read it.
            4. Assemble a FeatureSet(symbol, timeframe, as_of=last closed candle
               timestamp, features=computed).

        Note: only closed candles feed reproducible features — the engine will
        operate on ``series.closed()`` (see fmis.data.CandleSeries) so a still-
        forming bar can never leak into a signal.
        """
        raise NotImplementedError(
            "FeatureEngine.compute is defined in the Milestone C computation phase"
        )
