"""Swing Setup Engine v1 — deterministic swing-trade setup assessment.

The one package in the repository permitted to represent trading direction.
See [ADR-0028](../../../docs/adr/ADR-0028-directional-interpretation-boundary.md)
and [the design record](../../../docs/design/SWING_SETUP_ENGINE_V1.md).

    setup_for_symbol("BTCUSDT")  -> (MultiTimeframeFactSheet, SetupAssessment)

`SetupAssessment.state` is one of `WAIT`, `CANDIDATE` or `CONFIRMED`. `WAIT` is
a first-class, successful result — refusing a weak setup correctly is this
package's job, not a failure of it.
"""

from __future__ import annotations

from fmis.swing_setup.compose import (
    SETUP_LIMITATIONS,
    SETUP_ROLE,
    SetupRunResult,
    build_setup_inputs,
    context_input_from_sheet,
    run_setup_for_symbols,
    setup_assessment_for_sheet,
    setup_for_symbol,
)
from fmis.swing_setup.models import (
    CONFIRMATION_SIDE,
    NOT_CALIBRATED,
    SETUP_SCHEMA_VERSION,
    Direction,
    DirectionalFactor,
    ExecutionBreakEvent,
    Lean,
    Probability,
    ProbabilityStatus,
    RiskReward,
    SetupAssessment,
    SetupInputs,
    SetupState,
    SwingSetupError,
    Trigger,
    TriggerKind,
)
from fmis.swing_setup.policy import (
    CONFIRMATION_LOOKBACK_BARS,
    MINIMUM_AGREEING_FAMILIES,
    SETUP_POLICY_ID,
    evaluate_setup,
)
from fmis.swing_setup.render import render_setup

__all__ = [
    # entry points
    "setup_for_symbol",
    "setup_assessment_for_sheet",
    "run_setup_for_symbols",
    "SetupRunResult",
    "evaluate_setup",
    "render_setup",
    # the artifact
    "SetupAssessment",
    "SetupState",
    "Direction",
    "Lean",
    "DirectionalFactor",
    "TriggerKind",
    "Trigger",
    "RiskReward",
    "ProbabilityStatus",
    "Probability",
    "NOT_CALIBRATED",
    "CONFIRMATION_SIDE",
    "SETUP_SCHEMA_VERSION",
    # input boundary
    "SetupInputs",
    "ExecutionBreakEvent",
    "build_setup_inputs",
    # adapters and constants
    "context_input_from_sheet",
    "SETUP_ROLE",
    "SETUP_LIMITATIONS",
    "SETUP_POLICY_ID",
    "MINIMUM_AGREEING_FAMILIES",
    "CONFIRMATION_LOOKBACK_BARS",
    # errors
    "SwingSetupError",
]
