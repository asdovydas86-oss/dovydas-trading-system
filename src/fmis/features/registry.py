"""Feature registry — the discovery mechanism that keeps the engine open/closed.

The engine never imports concrete features by name. Instead, feature modules
register their calculators here, and the engine asks the registry what exists.
That indirection is what lets a completely new *technical* feature module (e.g.
a new indicator or market-structure calculation) be added *without editing the
engine or any other module* — the core requirement for growing the system for
years. Non-technical domains (macro, news, on-chain, derivatives, sentiment, AI)
are out of scope for this engine and its registry; they are separate future
engines combined by a higher aggregation layer.

This file is container plumbing, not calculation.
"""

from __future__ import annotations

from fmis.features.types import Feature, FeatureCategory

__all__ = ["FeatureRegistry"]


class FeatureRegistry:
    """An in-memory name -> Feature map with category lookup.

    Names must be unique; registering a duplicate name is a programming error
    and raises, so two modules cannot silently shadow each other.
    """

    def __init__(self) -> None:
        self._features: dict[str, Feature] = {}

    def register(self, feature: Feature) -> None:
        """Add a feature. Raises ValueError if its name is already registered."""
        if feature.name in self._features:
            raise ValueError(f"feature {feature.name!r} is already registered")
        self._features[feature.name] = feature

    def get(self, name: str) -> Feature:
        """Return the named feature. Raises KeyError if absent."""
        return self._features[name]

    def has(self, name: str) -> bool:
        """Return True if a feature with this name is registered."""
        return name in self._features

    def all(self) -> tuple[Feature, ...]:
        """Return every registered feature (registration order)."""
        return tuple(self._features.values())

    def by_category(self, category: FeatureCategory) -> tuple[Feature, ...]:
        """Return every registered feature in one category."""
        return tuple(f for f in self._features.values() if f.category == category)

    def __contains__(self, name: object) -> bool:
        return name in self._features

    def __len__(self) -> int:
        return len(self._features)
