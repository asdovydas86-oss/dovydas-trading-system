"""FMITS Swing Strategy Laboratory — historical policy research. **Never production.**

    fmits research swing ...   ──►  LabStudy  ──►  a comparison table and a verdict

**What this package is for.** One question, asked by the owner and previously
unanswerable from this repository: *is the 1W gate too restrictive for swing
trading?* Answering it needs the current policy replayed over real history,
alternative policies replayed over the **same** history and the **same** facts,
and outcomes measured through one trade simulator — which is what is here.

**What this package must never do.**

* It does not change the production strategy. The one seam it uses,
  `evaluate_setup`'s research-only overrides, stamps a research ``policy_id`` on
  every assessment it produces, and a guard asserts no live surface emits one.
* It promotes nothing. A variant that looks good here is a **candidate for
  forward testing**, and this package has no vocabulary for anything stronger.
* It writes nothing to the owner's store, opens no file and takes no execution
  action.

**Read the limitations before the numbers.** `LAB_LIMITATIONS` is not a
formality: BW-2 (the weekly warm-up bounds the window), BW-4 (R is per-trade,
not an account return) and BW-7 (nothing here is a forward test) each change
what a result is allowed to mean.
"""

from __future__ import annotations

from fmis.swing_lab.artifact import (
    ARTIFACT_FILENAME_SUFFIX,
    LabArtifact,
    encode_study,
    read_artifact,
    verify_digest,
    write_study,
)
from fmis.swing_lab.gate import GateImpact, measure_gate_impact
from fmis.swing_lab.metrics import (
    SAMPLE_FLOOR,
    LabDrawdownReading,
    LabEquityPoint,
    LabMeasure,
    VariantMetrics,
    classify,
    lab_breakdown_by,
    compute_lab_metrics,
)
from fmis.swing_lab.models import (
    LAB_SCHEMA_VERSION,
    LabExitReason,
    GateObservation,
    GateVerdict,
    LabTrade,
    LabVariant,
    LabVerdict,
    SwingLabError,
    TradeVerdict,
)
from fmis.swing_lab.replay import (
    LabObservation,
    VariantReplay,
    group_variants,
    replay_variant_group,
)
from fmis.swing_lab.robustness import (
    RobustnessReading,
    SplitReading,
    measure_robustness,
)
from fmis.swing_lab.study import (
    LAB_LIMITATIONS,
    LabManifest,
    LabStudy,
    VariantResult,
    result_digest,
    run_lab_study,
)
from fmis.swing_lab.trades import (
    CONSERVATIVE_COSTS,
    COST_SCENARIOS,
    FRICTIONLESS_COSTS,
    LAB_TRADE_BASIS,
    simulate_trade,
    to_price_bars,
)
from fmis.swing_lab.variants import (
    BASELINE_VARIANT,
    CONTEXT_ONLY_VARIANT,
    CORE_1D4H_VARIANT,
    HARD_GATE_CONTROL_VARIANT,
    PRE_SPECIFIED_VARIANTS,
    PRODUCTION_INTERVALS,
    SHIFTED_INTERVALS,
    SHIFTED_ROLE_VARIANT,
    variant_by_id,
)

__all__ = [
    # errors and schema
    "SwingLabError",
    "LAB_SCHEMA_VERSION",
    # variants
    "LabVariant",
    "PRE_SPECIFIED_VARIANTS",
    "BASELINE_VARIANT",
    "HARD_GATE_CONTROL_VARIANT",
    "CONTEXT_ONLY_VARIANT",
    "CORE_1D4H_VARIANT",
    "SHIFTED_ROLE_VARIANT",
    "PRODUCTION_INTERVALS",
    "SHIFTED_INTERVALS",
    "variant_by_id",
    # trades
    "LabTrade",
    "LabExitReason",
    "TradeVerdict",
    "simulate_trade",
    "to_price_bars",
    "FRICTIONLESS_COSTS",
    "CONSERVATIVE_COSTS",
    "COST_SCENARIOS",
    "LAB_TRADE_BASIS",
    # replay
    "LabObservation",
    "VariantReplay",
    "group_variants",
    "replay_variant_group",
    # metrics
    "LabMeasure",
    "LabEquityPoint",
    "LabDrawdownReading",
    "VariantMetrics",
    "compute_lab_metrics",
    "lab_breakdown_by",
    "classify",
    "LabVerdict",
    "SAMPLE_FLOOR",
    # the gate
    "GateVerdict",
    "GateObservation",
    "GateImpact",
    "measure_gate_impact",
    # robustness
    "SplitReading",
    "RobustnessReading",
    "measure_robustness",
    # studies
    "LabStudy",
    "LabManifest",
    "VariantResult",
    "LAB_LIMITATIONS",
    "run_lab_study",
    "result_digest",
    # artifacts
    "LabArtifact",
    "ARTIFACT_FILENAME_SUFFIX",
    "encode_study",
    "write_study",
    "read_artifact",
    "verify_digest",
]
