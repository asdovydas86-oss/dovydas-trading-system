"""Milestone AR — Swing Setup Engine v1: the composition root and its adapters.

Covers what `fmis.swing_setup.compose` adds beyond the policy: the two small
duplicated adapters (§ ADR-0028), wiring `build_setup_inputs` correctly off a
real `MultiTimeframeFactSheet`, and `run_setup_for_symbols`'s per-symbol
isolation. No test here recomputes an engine value independently — every
expectation is read off the same fixture the adapter consumes.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from fmis.decision_context import ContextState, evaluate_context
from fmis.market_regime import RegimeDimensionName
from fmis.pipeline.market_analysis import InsufficientDataError
from fmis.pipeline.multi_timeframe import TimeframeRole
from fmis.pipeline.regime import regime_for_sheet
from fmis.providers.binance import BinanceTransportError
from fmis.swing_setup import compose as compose_module
from fmis.swing_setup.compose import (
    build_setup_inputs,
    context_input_from_sheet,
    run_setup_for_symbols,
    setup_assessment_for_sheet,
    setup_for_symbol,
    snapshot_from_sheet,
)
from tests.archive_helpers import facts, multi

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "fmis"
PACKAGE_DIR = SRC / "swing_setup"


# ============================ adapters =========================================


def test_snapshot_from_sheet_copies_without_recomputing() -> None:
    sheet = facts(seed=5)
    snapshot = snapshot_from_sheet(sheet)
    assert snapshot.symbol == sheet.symbol
    assert snapshot.interval == sheet.interval
    assert snapshot.as_of == sheet.as_of
    assert snapshot.window is sheet.window
    assert snapshot.features is sheet.features


def test_snapshot_from_sheet_rejects_the_wrong_type() -> None:
    with pytest.raises(TypeError):
        snapshot_from_sheet(object())  # type: ignore[arg-type]


def test_context_input_from_sheet_reports_zero_conflicts() -> None:
    sheet = multi()
    regimes = {v.role: regime_for_sheet(v.sheet) for v in sheet.views}
    context_input = context_input_from_sheet(
        sheet, regimes, None, primary_role=TimeframeRole.SETUP
    )
    assert context_input.conflict_count == 0
    assert context_input.evidence_is_insufficient is True  # no evidence supplied


def test_context_input_from_sheet_matches_the_views() -> None:
    sheet = multi()
    regimes = {v.role: regime_for_sheet(v.sheet) for v in sheet.views}
    context_input = context_input_from_sheet(
        sheet, regimes, None, primary_role=TimeframeRole.SETUP
    )
    roles = {view.role for view in context_input.views}
    assert roles == {"context", "setup", "execution"}


# ============================ build_setup_inputs ================================


def test_build_setup_inputs_reads_the_right_role_for_each_field() -> None:
    sheet = multi()
    regimes = {v.role: regime_for_sheet(v.sheet) for v in sheet.views}
    context = evaluate_context(
        context_input_from_sheet(sheet, regimes, None, primary_role=TimeframeRole.SETUP)
    )
    inputs = build_setup_inputs(sheet, regimes, None, context)

    context_view = sheet.by_role[TimeframeRole.CONTEXT].sheet
    setup_view = sheet.by_role[TimeframeRole.SETUP].sheet
    execution_view = sheet.by_role[TimeframeRole.EXECUTION].sheet

    assert inputs.context_structural_trend is context_view.structure.trend
    assert inputs.setup_structural_trend is setup_view.structure.trend
    assert inputs.execution_structural_trend is execution_view.structure.trend
    assert inputs.execution_levels == execution_view.structure.levels
    assert inputs.setup_levels == setup_view.structure.levels
    assert inputs.execution_close == execution_view.window.last_close
    assert inputs.execution_closed_count == execution_view.window.closed_count
    assert [e.level for e in inputs.execution_breaks] == list(
        b.level for b in execution_view.structure.breaks
    )
    assert [e.index for e in inputs.execution_breaks] == [
        b.index for b in execution_view.structure.breaks
    ]
    # And specifically NOT the setup view's breaks, unless they happen to be
    # identical — assert the two views actually differ so this is a real check.
    assert execution_view.structure.breaks != setup_view.structure.breaks
    assert [e.level for e in inputs.execution_breaks] != [
        b.level for b in setup_view.structure.breaks
    ]
    assert inputs.context_regime_structure is regimes[TimeframeRole.CONTEXT].by_dimension[
        RegimeDimensionName.STRUCTURE
    ].state
    assert inputs.decision_context_state is context.state


def test_build_setup_inputs_requires_all_three_roles() -> None:
    sheet = multi()
    # Rebuild a sheet missing the execution role by filtering views.
    from fmis.pipeline.multi_timeframe import MultiTimeframeFactSheet

    partial = MultiTimeframeFactSheet(
        symbol=sheet.symbol,
        source=sheet.source,
        views=tuple(v for v in sheet.views if v.role is not TimeframeRole.EXECUTION),
        newest_as_of=sheet.newest_as_of,
        limitations=sheet.limitations,
    )
    regimes = {v.role: regime_for_sheet(v.sheet) for v in partial.views}
    context = evaluate_context(
        context_input_from_sheet(partial, regimes, None, primary_role=TimeframeRole.SETUP)
    )
    with pytest.raises(ValueError, match="execution"):
        build_setup_inputs(partial, regimes, None, context)


def test_build_setup_inputs_rejects_a_context_setup_interval_collision() -> None:
    """Regression: a one-flag misconfiguration must not silently collapse the
    'at least two independent families' guarantee to one fact counted twice."""
    from fmis.pipeline.multi_timeframe import build_multi_timeframe_facts

    sheet = multi()
    colliding = build_multi_timeframe_facts(
        {v.role: v.sheet for v in sheet.views},
        intervals={
            TimeframeRole.CONTEXT: "1d",
            TimeframeRole.SETUP: "1d",  # collides with CONTEXT
            TimeframeRole.EXECUTION: "4h",
        },
        source=sheet.source,
    )
    regimes = {v.role: regime_for_sheet(v.sheet) for v in colliding.views}
    context = evaluate_context(
        context_input_from_sheet(colliding, regimes, None, primary_role=TimeframeRole.SETUP)
    )
    with pytest.raises(ValueError, match="distinct"):
        build_setup_inputs(colliding, regimes, None, context)


# ============================ setup_assessment_for_sheet ========================


def test_setup_assessment_for_sheet_is_pure_and_deterministic() -> None:
    sheet = multi()
    first = setup_assessment_for_sheet(sheet)
    second = setup_assessment_for_sheet(sheet)
    assert first == second


def test_setup_assessment_for_sheet_rejects_the_wrong_type() -> None:
    with pytest.raises(TypeError):
        setup_assessment_for_sheet(object())  # type: ignore[arg-type]


def test_setup_assessment_carries_inherited_limitations() -> None:
    sheet = multi()
    assessment = setup_assessment_for_sheet(sheet)
    codes = {line.split(":", 1)[0] for line in assessment.limitations}
    assert "AR-1" in codes  # this package's own limitation
    assert any(code.startswith("ADR-") for code in codes)  # inherited from the sheet


# ============================ setup_for_symbol (network edge) ===================


def test_setup_for_symbol_delegates_to_the_multi_timeframe_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_multi_timeframe(symbol: str, **kwargs: object):
        captured["symbol"] = symbol
        captured["kwargs"] = kwargs
        return multi(symbol=symbol)

    monkeypatch.setattr(
        compose_module, "multi_timeframe_facts_for_symbol", fake_multi_timeframe
    )
    sheet, assessment = setup_for_symbol("ETHUSDT", limit=250)
    assert captured["symbol"] == "ETHUSDT"
    assert captured["kwargs"]["limit"] == 250
    assert sheet.symbol == "ETHUSDT"
    assert assessment.symbol == "ETHUSDT"


# ============================ run_setup_for_symbols ==============================


def test_run_setup_for_symbols_preserves_input_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        compose_module, "multi_timeframe_facts_for_symbol",
        lambda symbol, **kw: multi(symbol=symbol),
    )
    results = run_setup_for_symbols(["ETHUSDT", "BTCUSDT", "SOLUSDT"])
    assert [r.requested_symbol for r in results] == ["ETHUSDT", "BTCUSDT", "SOLUSDT"]
    assert all(r.assessment is not None for r in results)


def test_run_setup_for_symbols_isolates_a_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def flaky(symbol: str, **kw: object):
        if symbol == "BADUSDT":
            raise BinanceTransportError("connection refused")
        return multi(symbol=symbol)

    monkeypatch.setattr(compose_module, "multi_timeframe_facts_for_symbol", flaky)
    results = run_setup_for_symbols(["BTCUSDT", "BADUSDT", "ETHUSDT"])
    assert results[0].assessment is not None
    assert results[1].assessment is None
    assert "BinanceTransportError" in results[1].failure
    assert results[2].assessment is not None


def test_run_setup_for_symbols_isolates_insufficient_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def flaky(symbol: str, **kw: object):
        if symbol == "THINUSDT":
            raise InsufficientDataError(subject=symbol, required=200, fetched=5, closed=5)
        return multi(symbol=symbol)

    monkeypatch.setattr(compose_module, "multi_timeframe_facts_for_symbol", flaky)
    results = run_setup_for_symbols(["THINUSDT", "BTCUSDT"])
    assert results[0].assessment is None
    assert "InsufficientDataError" in results[0].failure
    assert results[1].assessment is not None


def test_run_setup_for_symbols_does_not_swallow_a_defect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(symbol: str, **kw: object):
        raise KeyError("not a market failure")

    monkeypatch.setattr(compose_module, "multi_timeframe_facts_for_symbol", broken)
    with pytest.raises(KeyError):
        run_setup_for_symbols(["BTCUSDT"])


def test_run_setup_for_symbols_rejects_an_empty_list() -> None:
    with pytest.raises(ValueError):
        run_setup_for_symbols([])


def test_run_setup_for_symbols_rejects_a_blank_symbol() -> None:
    with pytest.raises(ValueError):
        run_setup_for_symbols(["BTCUSDT", "  "])


def test_run_setup_for_symbols_rejects_a_string_as_the_whole_argument() -> None:
    with pytest.raises(TypeError):
        run_setup_for_symbols("BTCUSDT")  # type: ignore[arg-type]


def test_evidence_is_none_when_the_setup_view_window_has_no_closed_candle() -> None:
    """`_evidence_for` reports absence rather than raising on an empty window."""
    from datetime import datetime, timezone

    from fmis.pipeline.market_analysis import DataWindow
    from fmis.pipeline.structural_facts import StructuralFactSheet

    setup_sheet = facts(seed=5)
    empty_window = DataWindow(
        fetched_count=0, closed_count=0, excluded_forming_count=0,
        first_timestamp=None, last_timestamp=None, last_close=None,
    )
    empty_setup_sheet = StructuralFactSheet(
        symbol=setup_sheet.symbol, interval=setup_sheet.interval, source=setup_sheet.source,
        as_of=setup_sheet.as_of, window=empty_window, detection=setup_sheet.detection,
        features=setup_sheet.features, warming_up=setup_sheet.warming_up,
        structure=setup_sheet.structure, nearest_levels=setup_sheet.nearest_levels,
    )
    result = compose_module._evidence_for(empty_setup_sheet)
    assert result is None


# ============================ SetupRunResult =====================================


def test_setup_run_result_rejects_a_blank_symbol() -> None:
    with pytest.raises(ValueError):
        compose_module.SetupRunResult(requested_symbol="", failure="x")


def test_setup_run_result_requires_exactly_one_of_assessment_or_failure() -> None:
    with pytest.raises(ValueError):
        compose_module.SetupRunResult(requested_symbol="BTCUSDT")
    with pytest.raises(ValueError):
        compose_module.SetupRunResult(
            requested_symbol="BTCUSDT",
            assessment=setup_assessment_for_sheet(multi()),
            failure="x",
        )


def test_setup_run_result_rejects_wrong_types() -> None:
    with pytest.raises(TypeError):
        compose_module.SetupRunResult(requested_symbol="BTCUSDT", assessment=object())
    with pytest.raises(TypeError):
        compose_module.SetupRunResult(requested_symbol="BTCUSDT", failure=object())


# ============================ import boundary (ADR-0028 §3) =====================


def test_swing_setup_never_imports_workspace_daily_or_archive() -> None:
    forbidden = ("fmis.workspace", "fmis.daily", "fmis.archive")
    for py in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(alias.name.startswith(f) for f in forbidden), (py, alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not any(node.module.startswith(f) for f in forbidden), (py, node.module)
