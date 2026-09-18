"""Price zones — the first FMITS abstraction over a structural price **area**.

    structural_levels(...)  ──►  derive_price_zones(levels, atr_history)
                                          │  PriceZoneSet
                                          ▼
                            StructureFacts.zones  ──►  TechnicalContextView.zones

**The gap this closes.** FMITS has always had `PriceLevel`: an exact price, a
side its swing implies, and provenance. It had no concept of an *area*. A trader
reading a chart sees one important region where FMITS saw three unrelated exact
lines, and that gap was the largest one between what FMITS computes and how the
owner reads a market.

**What it does not close.** A zone still has no role. Whether price has held at
an area or broken through it is a function of interaction history, and no
interaction engine exists (ADR-0033 §8, research questions R3 and R4). This
package therefore ships geometry and provenance, and nothing that reads them.

Package rules, in the shape `fmis.level_crossing` states its own:

  * **Exact semantics elsewhere are untouched.** `PriceLevel` equality stays
    exact, `classify_comparison` stays exact, `CrossingKind`'s
    exact-equality-is-a-`TOUCH` rule stays exact, and ADR-0013 §4 is not
    weakened globally or locally. The tolerance introduced here is scoped to one
    thing: which confirmed levels a band contains.
  * **Delegate, never re-derive.** Swing detection, labelling, level projection,
    crossing classification and ATR each keep their single implementation
    elsewhere and none is repeated here.
  * **Nothing is interpreted.** No role, no strength, no quality, no score, no
    rank, no confidence, no direction, no target, no invalidation, no breakout,
    no acceptance, no reclaim, no retest, no false breakout — and the words
    support and resistance appear in no field, value or message.
  * **No global mutable state**, no cache, no registry of its own, no wall clock,
    no randomness, no environment dependence.
  * **Imports only `fmis.data`, `fmis.features` and `fmis.level_crossing`.**
    Never the swing-setup, evidence, decision-support, market-regime,
    risk-policy, scan-memory or pipeline packages — **no zone reaches evidence
    voting, the swing policy, the 1W regime gate, Scan Memory or risk**. Zone
    evidence independence is `NOT ESTABLISHED` and stays so until research
    question **R15** measures it. The forbidden list is named in prose rather
    than as dotted module paths on purpose: several of those packages guard
    themselves with a **text** scan for their own import path, and a docstring
    that spelled one would trip a guard it is agreeing with.
    `tests/test_price_zones_architecture.py` enforces the same list over the
    real import graph, where a name in a sentence cannot be mistaken for one.

See [ADR-0033](../../../docs/adr/ADR-0033-price-zone-semantics-and-the-tolerance-boundary.md)
and `docs/design/PRICE_ZONE_ENGINE_V1.md`.
"""

from __future__ import annotations

from fmis.price_zones.engine import derive_price_zones, zone_width_series
from fmis.price_zones.models import (
    ADMISSIBLE_MULTIPLE,
    PRICE_ZONE_LIMITATIONS,
    ZONE_WIDTH_POLICY_V1,
    PriceZone,
    PriceZoneError,
    PriceZoneSet,
    SeriesWindowMismatchError,
    ZoneMember,
    ZonePricePosition,
    ZoneWidthPolicy,
    ZoneWidthPolicyMismatchError,
    ZoneWidthReference,
    ZoneWidthScale,
)

__all__ = [
    "PriceZoneError",
    "ZoneWidthPolicyMismatchError",
    "SeriesWindowMismatchError",
    "ZoneWidthScale",
    "ZoneWidthReference",
    "ZoneWidthPolicy",
    "ZONE_WIDTH_POLICY_V1",
    "ADMISSIBLE_MULTIPLE",
    "ZonePricePosition",
    "ZoneMember",
    "PriceZone",
    "PriceZoneSet",
    "PRICE_ZONE_LIMITATIONS",
    "derive_price_zones",
    "zone_width_series",
]
