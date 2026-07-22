"""FeatureEngine — orchestrator that turns a CandleSeries into a FeatureSet.

The engine's job is coordination only: given a price series and a set of feature
names, resolve their dependency order, run each feature once, and assemble the
results into a single ``FeatureSet``. It performs **no indicator math itself** —
all math lives in the individual ``Feature`` implementations, discovered through
the registry (the engine never imports a concrete feature).

Only closed candles feed reproducible features, so the engine operates on
``series.closed()`` and derives ``as_of`` from the last closed candle. Individual
features also close their input defensively; the two guarantees are idempotent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from fmis.data import CandleSeries
from fmis.features.registry import FeatureRegistry
from fmis.features.types import FeatureContext, FeatureResult, FeatureSet

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

        1. Operate on closed candles only (``series.closed()``).
        2. Select target features: ``names`` if given, else every registered one.
        3. Resolve dependency order (deps before dependents); reject unknown
           features/dependencies and dependency cycles.
        4. Run each feature once, threading already-computed results through the
           FeatureContext so a feature can read its dependencies.
        5. Assemble the FeatureSet, stamped with the last closed candle's time.
        """
        closed_series = series.closed()
        if not closed_series.candles:
            raise ValueError("cannot build a FeatureSet: series has no closed candles")

        requested = (
            list(names) if names is not None else [f.name for f in self._registry.all()]
        )
        order = self._resolve_order(requested)

        aux = dict(sources) if sources else {}
        computed: dict[str, FeatureResult] = {}
        for name in order:
            feature = self._registry.get(name)
            context = FeatureContext(
                primary=closed_series, computed=computed, sources=aux
            )
            computed[name] = feature.compute(context)

        return FeatureSet(
            symbol=closed_series.symbol,
            timeframe=closed_series.timeframe,
            as_of=closed_series.candles[-1].timestamp,
            features=computed,
        )

    def _resolve_order(self, requested: Sequence[str]) -> list[str]:
        """Depth-first topological sort. Deterministic in ``requested`` order.

        Raises ValueError on an unknown feature/dependency or a dependency cycle.
        """
        order: list[str] = []
        state: dict[str, str] = {}  # name -> "visiting" | "done"

        def visit(name: str, path: list[str]) -> None:
            if not self._registry.has(name):
                trail = " -> ".join([*path, name])
                raise ValueError(f"unknown feature {name!r} (required via: {trail})")
            marker = state.get(name)
            if marker == "done":
                return
            if marker == "visiting":
                trail = " -> ".join([*path, name])
                raise ValueError(f"dependency cycle detected: {trail}")

            state[name] = "visiting"
            for dep in self._registry.get(name).dependencies:
                visit(dep, [*path, name])
            state[name] = "done"
            order.append(name)

        for name in requested:
            visit(name, [])
        return order
