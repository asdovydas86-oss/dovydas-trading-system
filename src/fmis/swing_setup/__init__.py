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
    setup_inputs_and_assessment_for_sheet,
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
from fmis.swing_setup.scan import SCAN_UNIVERSE, render_scan, result_status, run_market_scan
from fmis.swing_setup.scan_report import render_scan_report
from fmis.swing_setup.backtest_harness import (
    BACKTEST_LIMITATIONS,
    DEFAULT_BACKTEST_DAYS,
    DEFAULT_BACKTEST_LIMIT,
    DEFAULT_BACKTEST_SYMBOLS,
    DEFAULT_EVALUATION_WINDOW_BARS,
    run_backtest,
)
from fmis.swing_setup.backtest_metrics import BacktestMetrics, compute_metrics
from fmis.swing_setup.backtest_models import (
    BACKTEST_SCHEMA_VERSION,
    BacktestError,
    BacktestRun,
    DataBoundary,
    HistoricalObservation,
    OutcomeStatus,
    SetupOutcome,
)
from fmis.swing_setup.backtest_render import render_backtest_report

__all__ = [
    # entry points
    "setup_for_symbol",
    "setup_assessment_for_sheet",
    "setup_inputs_and_assessment_for_sheet",
    "run_setup_for_symbols",
    "SetupRunResult",
    "evaluate_setup",
    "render_setup",
    # market scanner
    "SCAN_UNIVERSE",
    "run_market_scan",
    "render_scan",
    "render_scan_report",
    "result_status",
    # historical backtest harness
    "run_backtest",
    "compute_metrics",
    "render_backtest_report",
    "BacktestRun",
    "BacktestMetrics",
    "HistoricalObservation",
    "SetupOutcome",
    "OutcomeStatus",
    "DataBoundary",
    "BacktestError",
    "BACKTEST_SCHEMA_VERSION",
    "BACKTEST_LIMITATIONS",
    "DEFAULT_BACKTEST_SYMBOLS",
    "DEFAULT_BACKTEST_DAYS",
    "DEFAULT_BACKTEST_LIMIT",
    "DEFAULT_EVALUATION_WINDOW_BARS",
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
