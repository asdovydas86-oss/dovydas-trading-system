"""Evidence taxonomy — shared vocabulary for what evidence is *about*.

Three small things and no behaviour: `EvidenceFamily` (subject areas),
`EvidenceDescriptor` (the definition of one evidence concept), and an immutable
catalog of the concepts this repository genuinely interprets today.

The distinction this package exists to hold:

    an indicator is a deterministic calculation
    evidence is interpretation-ready domain information
    a calculated indicator is not automatically evidence

Relative volume is computed today and classified nowhere, so it is a measurement
and has no descriptor. Price-versus-EMA is computed *and* classified, so it does.
The catalog records that difference honestly, including by leaving five families
empty (see `catalog`).

Why a shared vocabulary at all: trading, investing, macro and news modules will
each interpret the same family differently — what MOMENTUM means to a day trader
and to a long-term investor are not the same claim — but they should be able to
say *which family* they are talking about in the same words. Shared vocabulary,
separate interpretation, exactly as ADR-0009 established for shared calculations.

What this package deliberately does not define:

  * **supporting / conflicting** — a relationship to a hypothesis, already owned
    by `fmis.decision_support.EvidenceGroups`.
  * **neutral / unavailable** — already owned by
    `fmis.decision_support.Alignment`.
  * **insufficient data** — already owned by `OverallState` and by the
    ``insufficient_data`` key in feature metadata.

Those are three different dimensions living in the layer that observes data.
Redefining any of them here would create a second source of truth for concepts
that already work, which is why no combined "evidence type" enum exists.

Dependency rules:
  * imports **nothing** from `fmis` outside this package — not the pipeline, not
    providers, not features, and specifically **not `decision_support`**;
  * `decision_support` is likewise not modified to depend on this package during
    this milestone — connecting the two is deferred, so the taxonomy can settle
    before anything is built on it;
  * higher layers may depend on this package later; the direction never reverses.

No value, score, weight, confidence, direction, or availability state appears in
any type here. No calculation, no classification, no counting, no hypothesis.
"""

from __future__ import annotations

from fmis.evidence.catalog import descriptors, descriptors_for, find
from fmis.evidence.descriptors import EvidenceDescriptor
from fmis.evidence.families import EvidenceFamily

__all__ = [
    "EvidenceFamily",
    "EvidenceDescriptor",
    "descriptors",
    "descriptors_for",
    "find",
]
