"""Decision Support Evidence v1 — structured facts for a reasoning step.

Sits directly above `fmis.pipeline` and consumes an `AnalysisSnapshot` only. It
fetches nothing, calculates no indicator, and recomputes no metric: it classifies
values the engines already produced and organises them so that a human — or,
later, an interpretation layer — starts from structure rather than from a bag of
numbers.

    fmis.pipeline (AnalysisSnapshot) -> fmis.decision_support (EvidenceReport)

The line this package does not cross: **organising evidence is not forming a
view.** There is no direction to trade, no price target, no stop, no position
size, no confidence number, and no ranking — not in a value, not in a field name,
not in metadata. `OverallState` is deliberately undirectional: `WATCH` reports
that the available evidence agrees with itself, never that anything should be
bought or sold. Interpretation is a later layer's job, and it needs the facts
laid out honestly, including the gaps.

Two rules encode that discipline structurally rather than by good intentions:

  * An RSI band is `NOT_DIRECTIONAL` and is excluded from directional grouping,
    so "oversold" can never become evidence of anything by itself.
  * A tie between opposing observations yields no dominant alignment: everything
    is reported as conflicting rather than resolved by an arbitrary rule.

Rules for anything added here:
  * **Consumes snapshots only.** No provider, no engine call, no candle access.
  * **One derived calculation**, `derived.atr_percent_of_close`, kept in its own
    module. A second derived number belongs beside it, or in an engine.
  * **No LLM, prompt, API, network, persistence, CLI, or dashboard**, and no
    generic rule-engine or configurable strategy system. The classification
    rules are plain functions, written out, and individually tested.
  * **Nothing below imports this.** `fmis.pipeline` and every engine stay
    unaware of it — test-enforced.
  * Results are frozen, with mappings defensively copied and sequences stored as
    tuples, matching the repository's existing conventions.
"""

from __future__ import annotations

from fmis.decision_support.classification import (
    Alignment,
    Comparison,
    RsiZone,
    Sign,
    alignment_of_comparison,
    alignment_of_sign,
    classify_comparison,
    classify_rsi_zone,
    classify_sign,
)
from fmis.decision_support.derived import atr_percent_of_close
from fmis.decision_support.report import (
    EvidenceGroups,
    EvidenceReport,
    MarketContext,
    MomentumEvidence,
    Observation,
    OverallState,
    RelativeValueEvidence,
    Scenario,
    TrendEvidence,
    VolatilityEvidence,
    build_evidence_report,
)

__all__ = [
    # entry point
    "build_evidence_report",
    # report types
    "EvidenceReport",
    "MarketContext",
    "TrendEvidence",
    "MomentumEvidence",
    "VolatilityEvidence",
    "RelativeValueEvidence",
    "EvidenceGroups",
    "Observation",
    "Scenario",
    "OverallState",
    # classification vocabulary + rules
    "Comparison",
    "RsiZone",
    "Sign",
    "Alignment",
    "classify_comparison",
    "classify_rsi_zone",
    "classify_sign",
    "alignment_of_comparison",
    "alignment_of_sign",
    # the single derived calculation
    "atr_percent_of_close",
]
