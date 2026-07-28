"""The families an evidence concept can belong to.

A *family* answers "what kind of thing is this evidence about", and nothing
else. It carries no direction, no magnitude, no availability state, and no
relationship to any hypothesis.

Deliberately distinct from `fmis.features.FeatureCategory`, which the two enums
share five names with. They are different axes and must not be merged:

  * `FeatureCategory` classifies a **deterministic calculation** — which bucket a
    computed feature belongs to. Its own docstring forbids macro, news and
    sentiment members, because the Feature Engine is technical-only by design.
  * `EvidenceFamily` classifies an **evidence concept**, which may come from a
    technical calculation, from a domain the Feature Engine will never own
    (macro, news, sentiment), or from nothing yet implemented at all.

`FeatureCategory` additionally has INDICATOR, PATTERN and SUPPORT_RESISTANCE,
which describe how something is computed rather than what it is evidence about.
Extending `FeatureCategory` instead of adding this enum was not an option: that
enum explicitly prohibits the non-technical members this one requires.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["EvidenceFamily"]


class EvidenceFamily(str, Enum):
    """What an evidence concept is about. Never what to do about it.

    Members deliberately absent: anything naming an action or a stance. A family
    is a subject area, so BUY, SELL, LONG, SHORT and SIGNAL would be category
    errors here as much as they would be premature.

    Several families have no descriptors yet. That is the honest state of the
    system, not an oversight: a family exists so a future module has somewhere to
    put its evidence, and leaving it empty records that nothing interprets it
    today.
    """

    TREND = "trend"
    MOMENTUM = "momentum"
    VOLUME = "volume"
    VOLATILITY = "volatility"
    MARKET_STRUCTURE = "market_structure"
    RELATIVE_STRENGTH = "relative_strength"
    LIQUIDITY = "liquidity"
    MACRO = "macro"
    NEWS = "news"
    SENTIMENT = "sentiment"
