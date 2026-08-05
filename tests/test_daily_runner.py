"""Milestone AN — running the universe.

Three claims carry the milestone, and each is tested here against the real
composition root rather than a stand-in:

  1. **One symbol's failure does not end the run.** An expected provider failure
     becomes a row; every later symbol is still analysed.
  2. **A defect is not a market failure.** Anything absent from `_FAILURE_KINDS`
     propagates, because a report that renders an internal bug as an ordinary
     outage teaches the owner to ignore both.
  3. **The runner adds no engine.** Each symbol goes through
     `workspace_for_symbol` — the same root `fmits swing` uses — so a daily row
     and a full page cannot disagree.
"""

from __future__ import annotations

import ast
import json
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from fmis.daily import runner as runner_module
from fmis.daily.models import (
    DailyRun,
    DailyRunError,
    FailureKind,
    ResultCategory,
    SymbolResult,
)
from fmis.daily.runner import (
    DAILY_LIMITATIONS,
    analyse_symbol,
    run_daily,
)
from fmis.decision_context import ContextState
from fmis.pipeline.multi_timeframe import DEFAULT_TIMEFRAMES, TimeframeRole
from fmis.pipeline.structural_facts import DetectionSettings
from fmis.providers.binance import HttpResponse
from fmis.trading_context import TradingObjective
from fmis.workspace import SectionId, Workspace

REFERENCE = datetime(2026, 6, 1, tzinfo=timezone.utc)
LATER = datetime(2030, 1, 1, tzinfo=timezone.utc)
_OPEN_MS = 1_704_067_200_000
_FOUR_HOURS_MS = 4 * 60 * 60 * 1000
RUNNER_PATH = pathlib.Path(runner_module.__file__)


# ============================ fixtures =======================================


def kline(i: int, close: float) -> list[object]:
    open_ms = _OPEN_MS + i * _FOUR_HOURS_MS
    return [
        open_ms, f"{close:.8f}", f"{close * 1.02:.8f}", f"{close * 0.98:.8f}",
        f"{close:.8f}", "1000.00000000", open_ms + _FOUR_HOURS_MS - 1, "1000.0",
        100, "500.0", "500.0", "0",
    ]


def wave(n: int) -> list[float]:
    return [100.0 + (10.0 if i % 4 in (1, 2) else 0.0) + i for i in range(n)]


def _symbol_of(url: str) -> str:
    return url.split("symbol=", 1)[1].split("&", 1)[0]


def universe_transport(behaviour: dict[str, object], length: int = 120):
    """A transport answering per symbol, so one symbol can fail while others do not.

    A value of ``"ok"`` answers with candles; an ``Exception`` instance is
    raised; an `HttpResponse` is returned verbatim.
    """

    def _transport(url: str) -> HttpResponse:
        symbol = _symbol_of(url)
        _transport.calls.append(symbol)  # type: ignore[attr-defined]
        answer = behaviour.get(symbol, "ok")
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, HttpResponse):
            return answer
        return HttpResponse(status=200, body=json.dumps(
            [kline(i, c) for i, c in enumerate(wave(length))]).encode())

    _transport.calls = []  # type: ignore[attr-defined]
    return _transport


def go(symbols, behaviour=None, **kwargs) -> DailyRun:
    kwargs.setdefault("transport", universe_transport(behaviour or {}))
    kwargs.setdefault("clock", lambda: LATER)
    return run_daily(symbols, reference_time=REFERENCE, **kwargs)


NOT_FOUND = HttpResponse(
    status=400, body=json.dumps({"code": -1121, "msg": "Invalid symbol."}).encode()
)
GARBAGE = HttpResponse(status=200, body=b"{not json")


# ============ 1. the happy path composes, and composes only =================


def test_a_run_produces_one_result_per_symbol_in_order() -> None:
    run = go(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    assert isinstance(run, DailyRun)
    assert run.requested_symbols == ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    assert run.completed_count == 3
    assert run.failed_count == 0


def test_each_result_carries_the_same_workspace_a_full_page_would_show() -> None:
    run = go(["BTCUSDT"])
    result = run.results[0]
    assert isinstance(result.workspace, Workspace)
    assert result.workspace.symbol == "BTCUSDT"
    assert result.resolved_symbol == "BTCUSDT"
    assert result.context is result.workspace.by_id[SectionId.CONTEXT]


def test_the_category_is_the_decision_context_state_carried_through() -> None:
    """AL decided it; AN must not re-decide it."""
    run = go(["BTCUSDT"])
    result = run.results[0]
    state = ContextState(result.workspace.metadata["context_state"])
    assert result.category.value == state.value


def test_the_regime_summary_is_read_from_the_page_not_recomputed() -> None:
    run = go(["BTCUSDT"])
    result = run.results[0]
    section = result.workspace.by_id[SectionId.REGIME]
    assert result.regime_summary is not None
    assert any(result.regime_summary in line for line in section.summary)


def test_the_regime_summary_names_the_primary_role_and_not_another_view() -> None:
    """A row headed by one timeframe carrying another's regime is the worst defect
    this milestone could ship, and a live fixture cannot catch it: all three views
    usually classify the same way, so reading the wrong one looks correct.
    """

    class _Section:
        summary = (
            "context · 1w: trending · expanding · elevated",
            "setup · 1d: ranging · contracting · subdued",
            "execution · 4h: transitioning · steady · typical",
        )

    class _Page:
        by_id = {SectionId.REGIME: _Section()}
        metadata = {"primary_role": "setup"}

    assert runner_module._regime_line(_Page()) == "ranging · contracting · subdued"


def test_the_regime_summary_prefers_the_primary_role() -> None:
    run = go(["BTCUSDT"])
    workspace = run.results[0].workspace
    primary = workspace.metadata["primary_role"]
    line = next(
        s for s in workspace.by_id[SectionId.REGIME].summary if s.startswith(primary)
    )
    assert run.results[0].regime_summary == line.split(": ", 1)[-1]


def test_a_page_with_no_regime_summary_yields_no_regime_line() -> None:
    """An absence stays an absence rather than becoming the first thing available."""

    class _Section:
        summary: tuple[str, ...] = ()

    class _Page:
        by_id = {SectionId.REGIME: _Section()}
        metadata = {"primary_role": "setup"}

    assert runner_module._regime_line(_Page()) is None


@pytest.mark.parametrize("metadata", [{}, {"primary_role": "execution"}])
def test_an_unmatched_primary_role_falls_back_to_the_first_summary_line(
    metadata: dict,
) -> None:
    """A page whose primary role names no summary still reports *a* regime.

    Both branches are exercised: a page with no `primary_role` at all, and one
    naming a role the summary does not carry.
    """

    class _Section:
        summary = ("context · 1w: trending", "setup · 1d: ranging")

    class _Page:
        by_id = {SectionId.REGIME: _Section()}

    page = _Page()
    page.metadata = metadata  # type: ignore[attr-defined]
    assert runner_module._regime_line(page) == "trending"


# ============ 2. error isolation ============================================


def test_one_bad_symbol_does_not_stop_the_others() -> None:
    run = go(["BTCUSDT", "NOPE", "ETHUSDT"], {"NOPE": NOT_FOUND})
    assert run.requested_symbols == ("BTCUSDT", "NOPE", "ETHUSDT")
    assert [r.completed for r in run.results] == [True, False, True]
    assert run.failed_count == 1


def test_a_rejected_symbol_reports_why_in_the_provider_s_own_words() -> None:
    run = go(["NOPE"], {"NOPE": NOT_FOUND})
    failure = run.results[0].failure
    assert failure is not None
    assert failure.kind is FailureKind.INVALID_SYMBOL
    assert "Invalid symbol" in failure.detail
    assert failure.exception_type == "BinanceAPIError"


def test_an_undecodable_response_is_malformed_data_not_an_invalid_symbol() -> None:
    run = go(["BTCUSDT"], {"BTCUSDT": GARBAGE})
    failure = run.results[0].failure
    assert failure is not None
    assert failure.kind is FailureKind.MALFORMED_DATA


def test_a_transport_outage_is_a_provider_failure() -> None:
    from fmis.providers.binance import BinanceTransportError

    run = go(["BTCUSDT"], {"BTCUSDT": BinanceTransportError("connection reset")})
    failure = run.results[0].failure
    assert failure is not None
    assert failure.kind is FailureKind.PROVIDER_FAILURE
    assert "connection reset" in failure.detail


def test_too_few_candles_is_insufficient_data_and_not_an_analysis() -> None:
    """Distinct from INSUFFICIENT, which means an analysis was produced."""
    run = go(["BTCUSDT"], transport=universe_transport({}, length=1))
    result = run.results[0]
    assert result.category is ResultCategory.FAILED
    assert result.failure is not None
    assert result.failure.kind is FailureKind.INSUFFICIENT_DATA


def test_a_defect_is_not_swallowed_as_a_market_failure() -> None:
    """A KeyError from this repository must stop the run, loudly."""

    def exploding(url: str) -> HttpResponse:
        raise KeyError("a bug in FMITS, not a market condition")

    with pytest.raises(KeyError, match="a bug in FMITS"):
        run_daily(["BTCUSDT"], reference_time=REFERENCE, transport=exploding,
                  clock=lambda: LATER)


@pytest.mark.parametrize("error", [RuntimeError("boom"), AttributeError("boom"),
                                   ZeroDivisionError("boom")])
def test_no_unexpected_exception_becomes_a_result(error: Exception) -> None:
    with pytest.raises(type(error)):
        go(["BTCUSDT"], {"BTCUSDT": error})


def test_the_failure_table_lists_the_specific_error_before_its_base() -> None:
    """Both Binance value errors subclass ValueError; first match must be specific."""
    from fmis.providers.binance import BinanceAPIError, BinanceRequestError

    order = [kind for kind, _ in runner_module._FAILURE_KINDS]
    assert order.index(BinanceRequestError) < order.index(BinanceAPIError)
    for position, (exception_type, _) in enumerate(runner_module._FAILURE_KINDS):
        for later, _ in runner_module._FAILURE_KINDS[position + 1:]:
            assert not issubclass(later, exception_type), (
                f"{later.__name__} is shadowed by {exception_type.__name__}"
            )


def test_an_unclassified_error_is_reported_as_none() -> None:
    assert runner_module._classify(RuntimeError("x")) is None
    assert runner_module._classify(
        __import__("fmis.ingest", fromlist=["IngestError"]).IngestError("x")
    ) is FailureKind.MALFORMED_DATA


def test_every_context_state_has_a_category() -> None:
    """A new state added upstream must fail here rather than be binned silently."""
    assert set(runner_module._CATEGORY_OF) == set(ContextState)


def test_the_category_is_the_state_verbatim_and_re_decides_nothing() -> None:
    """AL owns the judgement. Binning LIMITED as SUFFICIENT would re-decide it.

    Asserted over the whole mapping rather than through a fixture, because a
    fixture only ever exercises the state it happens to produce — and the states
    it does not produce are exactly where a mis-binning would hide.
    """
    for state, category in runner_module._CATEGORY_OF.items():
        assert category.value == state.value, state


def test_an_unmapped_state_would_raise_rather_than_default() -> None:
    """Subscripted, never `.get(state, SOMETHING)` — a default would bin it silently."""
    body = RUNNER_PATH.read_text().split('"""', 2)[-1]
    assert "_CATEGORY_OF[state]" in body
    assert "_CATEGORY_OF.get" not in body
    with pytest.raises(KeyError):
        runner_module._CATEGORY_OF["a state nobody defined"]  # type: ignore[index]


def test_the_dispatch_table_cannot_be_mutated_at_runtime() -> None:
    with pytest.raises(TypeError):
        runner_module._CATEGORY_OF[ContextState.SUFFICIENT] = (  # type: ignore[index]
            ResultCategory.FAILED
        )


# ============ 3. the universe is validated before anything is fetched =======


def test_an_invalid_universe_stops_the_run_before_a_single_request() -> None:
    transport = universe_transport({})
    with pytest.raises(DailyRunError, match="must not repeat"):
        run_daily(["BTCUSDT", "BTCUSDT"], reference_time=REFERENCE,
                  transport=transport, clock=lambda: LATER)
    assert transport.calls == []  # type: ignore[attr-defined]


def test_a_run_requires_a_reference_time_before_it_fetches_anything() -> None:
    """Checked up front, so a bad boundary costs no provider calls at all.

    The model would reject it too, but only after every symbol had been fetched
    and analysed — a hundred and fifty requests thrown away at the last step.
    """
    transport = universe_transport({})
    with pytest.raises(TypeError, match="reference_time"):
        run_daily(["BTCUSDT"], reference_time="2026-06-01",  # type: ignore[arg-type]
                  transport=transport, clock=lambda: LATER)
    assert transport.calls == []  # type: ignore[attr-defined]


def test_the_run_records_the_reference_time_it_was_given() -> None:
    assert go(["BTCUSDT"]).reference_time == REFERENCE


# ============ 4. determinism ================================================


def test_two_runs_over_the_same_candles_are_identical() -> None:
    first = go(["BTCUSDT", "ETHUSDT"])
    second = go(["BTCUSDT", "ETHUSDT"])
    assert [r.category for r in first.results] == [r.category for r in second.results]
    assert [r.regime_summary for r in first.results] == [
        r.regime_summary for r in second.results
    ]
    assert first.reference_time == second.reference_time


def test_the_package_reads_no_clock_of_its_own() -> None:
    """`reference_time` and `clock` both arrive from the boundary."""
    source = RUNNER_PATH.read_text()
    body = source.split('"""', 2)[-1]
    for forbidden in ("datetime.now", "datetime.utcnow", "time.time("):
        assert forbidden not in body, forbidden


def test_the_duration_is_measured_by_an_injected_timer() -> None:
    ticks = iter([0.0, 2.5])
    result = analyse_symbol("BTCUSDT", transport=universe_transport({}),
                            clock=lambda: LATER, timer=lambda: next(ticks))
    assert result.duration_seconds == 2.5


def test_a_failed_symbol_is_timed_too() -> None:
    ticks = iter([1.0, 1.75])
    result = analyse_symbol("NOPE", transport=universe_transport({"NOPE": NOT_FOUND}),
                            clock=lambda: LATER, timer=lambda: next(ticks))
    assert result.category is ResultCategory.FAILED
    assert result.duration_seconds == 0.75


# ============ 5. one setting reaches every symbol ===========================


def test_every_symbol_is_analysed_under_identical_settings() -> None:
    """Rows analysed under different settings are rows that cannot be compared."""
    seen: list[dict] = []
    original = runner_module.workspace_for_symbol

    def spy(symbol, **kwargs):
        seen.append(kwargs)
        return original(symbol, **kwargs)

    runner_module.workspace_for_symbol = spy  # type: ignore[assignment]
    try:
        detection = DetectionSettings(left_bars=3, right_bars=3)
        go(["BTCUSDT", "ETHUSDT", "SOLUSDT"], detection=detection, limit=200)
    finally:
        runner_module.workspace_for_symbol = original  # type: ignore[assignment]
    assert len(seen) == 3
    assert all(call["detection"] is detection for call in seen)
    assert {call["limit"] for call in seen} == {200}


def test_the_runner_takes_no_per_symbol_override() -> None:
    tree = ast.parse(RUNNER_PATH.read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "run_daily")
    names = {a.arg for a in fn.args.args} | {a.arg for a in fn.args.kwonlyargs}
    assert not any("per_symbol" in n or "overrides" in n for n in names)


def test_the_objective_and_source_are_recorded_on_the_run() -> None:
    run = go(["BTCUSDT"], objective=TradingObjective.SWING_TRADE)
    assert run.objective == TradingObjective.SWING_TRADE.value
    assert run.source == "binance-spot"


def test_the_run_records_the_universe_and_the_intervals_it_used() -> None:
    run = go(["BTCUSDT"], timeframes=DEFAULT_TIMEFRAMES)
    assert run.metadata["requested"] == ("BTCUSDT",)
    assert run.metadata["intervals"] == tuple(
        DEFAULT_TIMEFRAMES[role] for role in TimeframeRole
    )


# ============ 6. the layer sits above everything it consumes ================


def test_no_engine_imports_this_package() -> None:
    """`fmis.daily` is an application-layer root; nothing below it may reach up.

    Only `fmis.pipeline.cli` — the terminal boundary — imports it, and
    `fmis.pipeline.__init__` does not import `cli`, so no cycle exists.
    `fmis.archive` (Milestone AO) also imports it, for the same reason:
    the archive consumes the finished `DailyRun`, it does not sit below it.
    """
    root = RUNNER_PATH.parent.parent
    permitted = {root / "daily", root / "pipeline", root / "archive"}
    for path in root.rglob("*.py"):
        if path.parent in permitted or "__pycache__" in path.parts:
            continue
        assert "fmis.daily" not in path.read_text(), path


def test_only_the_cli_imports_this_package_from_the_pipeline() -> None:
    pipeline = RUNNER_PATH.parent.parent / "pipeline"
    importers = sorted(
        p.name for p in pipeline.glob("*.py") if "fmis.daily" in p.read_text()
    )
    assert importers == ["cli.py"]


def test_importing_the_pipeline_does_not_load_the_daily_layer() -> None:
    """A cycle would be invisible until the day the import order changed."""
    import subprocess

    probe = (
        "import fmis.pipeline, sys; "
        "print('fmis.daily' in sys.modules)"
    )
    result = subprocess.run(
        [__import__("sys").executable, "-c", probe],
        capture_output=True, text=True, cwd=str(RUNNER_PATH.parents[3]),
    )
    assert result.stdout.strip() == "False", result.stderr


# ============ 7. the runner adds no engine ==================================


def test_the_runner_calls_exactly_one_composition_root() -> None:
    tree = ast.parse(RUNNER_PATH.read_text())
    called = {
        getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    for engine in ("detect_swings", "structural_levels", "derive_structure_breaks",
                   "derive_level_crossings", "classify_regime", "evaluate_context",
                   "build_workspace", "analyze_symbol", "build_structural_facts"):
        assert engine not in called, engine
    assert "workspace_for_symbol" in called


def test_the_runner_computes_no_market_quantity() -> None:
    """A subtraction is allowed for the elapsed clock and nowhere else."""
    tree = ast.parse(RUNNER_PATH.read_text())
    arithmetic = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp)
        and isinstance(node.op, (ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod))
    ]
    assert arithmetic == ["timer() - started", "timer() - started"]


def test_the_limitations_are_stated_on_every_run() -> None:
    run = go(["BTCUSDT"])
    assert run.limitations == DAILY_LIMITATIONS
    codes = [code for code, _ in DAILY_LIMITATIONS]
    assert codes == ["AN-1", "AN-2", "AN-3", "AN-4"]
    assert all(text.strip() for _, text in DAILY_LIMITATIONS)


def test_the_first_limitation_denies_the_reading_the_page_most_invites() -> None:
    assert "not a ranking" in DAILY_LIMITATIONS[0][1]


def test_the_run_states_that_rows_are_not_comparable_in_time() -> None:
    """Each symbol is fetched at a different instant; the page must say so."""
    joined = " ".join(text for _, text in DAILY_LIMITATIONS)
    assert "shared as-of" in joined


def test_symbols_are_fetched_one_at_a_time_in_requested_order() -> None:
    transport = universe_transport({})
    run_daily(["BTCUSDT", "ETHUSDT"], reference_time=REFERENCE,
              transport=transport, clock=lambda: LATER)
    calls = transport.calls  # type: ignore[attr-defined]
    assert calls == ["BTCUSDT"] * 3 + ["ETHUSDT"] * 3


def test_no_concurrency_primitive_is_used() -> None:
    """Sequential is the design, not an accident; see the design record §4."""
    source = RUNNER_PATH.read_text()
    for forbidden in ("ThreadPool", "asyncio", "concurrent.futures", "threading"):
        assert forbidden not in source, forbidden


def test_analyse_symbol_returns_a_result_and_never_raises_for_market_conditions() -> None:
    result = analyse_symbol("NOPE", transport=universe_transport({"NOPE": NOT_FOUND}),
                            clock=lambda: LATER)
    assert isinstance(result, SymbolResult)
    assert result.requested_symbol == "NOPE"


def test_the_requested_symbol_survives_verbatim_onto_a_failed_row() -> None:
    """The caller must recognise their own input in the row that reports its failure.

    A lowercase symbol is rejected by the provider rather than silently upcased,
    and the row still says `btcusdt` — what was typed — not a normalisation this
    layer invented.
    """
    run = go(["btcusdt"])
    result = run.results[0]
    assert result.requested_symbol == "btcusdt"
    assert result.category is ResultCategory.FAILED
    assert result.failure is not None
    assert result.failure.kind is FailureKind.INVALID_SYMBOL
    assert result.resolved_symbol is None


def test_a_completed_row_records_what_the_provider_answered_about() -> None:
    """Separate fields, so a future normalising provider makes the gap visible."""
    result = go(["BTCUSDT"]).results[0]
    assert result.requested_symbol == "BTCUSDT"
    assert result.resolved_symbol == result.workspace.symbol


def test_a_provider_answering_about_a_different_symbol_cannot_hide_it() -> None:
    """The two fields must not collapse the moment they disagree.

    Today's provider answers about exactly what it was asked, so the divergence
    is staged: the workspace is rebuilt naming a different instrument, and the
    row must still report what the caller typed.
    """
    import dataclasses

    original = runner_module.workspace_for_symbol

    def renaming(symbol, **kwargs):
        sheet, workspace = original(symbol, **kwargs)
        return sheet, dataclasses.replace(workspace, symbol="ALIAS")

    runner_module.workspace_for_symbol = renaming  # type: ignore[assignment]
    try:
        result = go(["BTCUSDT"]).results[0]
    finally:
        runner_module.workspace_for_symbol = original  # type: ignore[assignment]
    assert result.requested_symbol == "BTCUSDT"
    assert result.resolved_symbol == "ALIAS"


def test_the_run_records_the_intervals_it_actually_used() -> None:
    """A run that read 1w/1d/4h and recorded `("", "", "")` claimed something false."""
    run = go(["BTCUSDT"])  # no timeframes supplied — the defaults apply
    assert run.metadata["intervals"] == tuple(
        DEFAULT_TIMEFRAMES[role] for role in TimeframeRole
    )
    assert run.metadata["intervals"] == run.results[0].workspace.metadata["intervals"]


def test_one_resolved_interval_set_reaches_every_symbol() -> None:
    seen: list[dict] = []
    original = runner_module.workspace_for_symbol

    def spy(symbol, **kwargs):
        seen.append(kwargs["timeframes"])
        return original(symbol, **kwargs)

    runner_module.workspace_for_symbol = spy  # type: ignore[assignment]
    try:
        go(["BTCUSDT", "ETHUSDT"])
    finally:
        runner_module.workspace_for_symbol = original  # type: ignore[assignment]
    assert len(seen) == 2
    assert seen[0] is seen[1], "views received different interval mappings"
    assert seen[0] == dict(DEFAULT_TIMEFRAMES)
