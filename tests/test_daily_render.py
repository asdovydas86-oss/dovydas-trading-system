"""Milestone AN — the compact readiness index, and the `fmits daily` command.

The renderer's whole job is to lose nothing while showing much less. Two things
would defeat it: dropping a symbol, and implying an order the run does not have.
Both are asserted here, along with the width contract that makes the page
readable in a terminal, a pipe and a log file.
"""

from __future__ import annotations

import ast
import io
import json
import pathlib
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone

import pytest

from fmis.daily import render as render_module
from fmis.daily.models import (
    DailyRun,
    FailureKind,
    ResultCategory,
    SymbolFailure,
    SymbolResult,
)
from fmis.daily.render import CATEGORY_GLYPH, render_daily_run
from fmis.daily.runner import DAILY_LIMITATIONS
from fmis.pipeline import cli as cli_module
from fmis.pipeline.multi_timeframe import DEFAULT_TIMEFRAMES, TimeframeRole
from fmis.providers.binance import HttpResponse

RENDER_PATH = pathlib.Path(render_module.__file__)
_WIDTH = 78
REFERENCE = datetime(2026, 6, 1, tzinfo=timezone.utc)
LATER = datetime(2030, 1, 1, tzinfo=timezone.utc)
_OPEN_MS = 1_704_067_200_000
_FOUR_HOURS_MS = 4 * 60 * 60 * 1000

NOT_FOUND = HttpResponse(
    status=400, body=json.dumps({"code": -1121, "msg": "Invalid symbol."}).encode()
)


def universe_transport(behaviour: dict[str, object], length: int = 120):
    """A transport answering per symbol, so one symbol can fail while others do not."""

    def _transport(url: str) -> HttpResponse:
        symbol = url.split("symbol=", 1)[1].split("&", 1)[0]
        answer = behaviour.get(symbol, "ok")
        if isinstance(answer, HttpResponse):
            return answer
        closes = [100.0 + (10.0 if i % 4 in (1, 2) else 0.0) + i for i in range(length)]
        body = [
            [
                _OPEN_MS + i * _FOUR_HOURS_MS, f"{c:.8f}", f"{c * 1.02:.8f}",
                f"{c * 0.98:.8f}", f"{c:.8f}", "1000.00000000",
                _OPEN_MS + (i + 1) * _FOUR_HOURS_MS - 1, "1000.0", 100,
                "500.0", "500.0", "0",
            ]
            for i, c in enumerate(closes)
        ]
        return HttpResponse(status=200, body=json.dumps(body).encode())

    return _transport


# ============================ fixtures =======================================


class _Page:
    """The minimum a renderer may read off a workspace: an `as_of`."""

    def __init__(self, as_of: datetime) -> None:
        self.as_of = as_of


def completed(symbol: str, category: ResultCategory = ResultCategory.SUFFICIENT,
              regime: str | None = "trending · steady · typical") -> SymbolResult:
    return SymbolResult(
        requested_symbol=symbol,
        category=category,
        resolved_symbol=symbol,
        workspace=_Page(datetime(2026, 6, 1, 8, tzinfo=timezone.utc)),
        context=object(),
        regime_summary=regime,
    )


def failed(symbol: str, detail: str = "Invalid symbol.") -> SymbolResult:
    return SymbolResult(
        requested_symbol=symbol,
        category=ResultCategory.FAILED,
        failure=SymbolFailure(
            kind=FailureKind.INVALID_SYMBOL,
            detail=detail,
            exception_type="BinanceAPIError",
        ),
    )


def run(results=None, **overrides) -> DailyRun:
    fields = dict(
        reference_time=REFERENCE,
        results=results
        or (
            completed("BTCUSDT"),
            completed("ETHUSDT", ResultCategory.LIMITED),
            completed("SOLUSDT", ResultCategory.INSUFFICIENT),
            failed("NOPE"),
        ),
        objective="swing_trade",
        source="binance-spot",
        limitations=DAILY_LIMITATIONS,
    )
    fields.update(overrides)
    return DailyRun(**fields)  # type: ignore[arg-type]


def page(**kwargs) -> str:
    return render_daily_run(run(**kwargs))


# ============ 1. nothing is lost ============================================


def test_every_requested_symbol_appears_exactly_once() -> None:
    text = page()
    for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "NOPE"):
        assert sum(1 for line in text.splitlines()
                   if line.split()[1:2] == [symbol]) == 1, symbol


def test_rows_appear_in_the_order_the_caller_requested() -> None:
    """Not sorted by readiness: a sorted list reads as a list of picks."""
    order = ("SOLUSDT", "BTCUSDT", "NOPE", "ETHUSDT")
    text = render_daily_run(run(results=tuple(
        failed(s) if s == "NOPE" else completed(s) for s in order)))
    positions = [text.index(f" {s} ") for s in order]
    assert positions == sorted(positions)


def test_readiness_order_does_not_leak_into_the_row_order() -> None:
    """The same four symbols in reverse readiness keep their requested order."""
    results = (
        completed("A", ResultCategory.INSUFFICIENT),
        completed("B", ResultCategory.LIMITED),
        completed("C", ResultCategory.SUFFICIENT),
    )
    text = render_daily_run(run(results=results))
    assert text.index(" A ") < text.index(" B ") < text.index(" C ")


def test_a_failed_symbol_shows_its_reason_beneath_its_row() -> None:
    text = page()
    lines = text.splitlines()
    row = next(i for i, line in enumerate(lines) if "NOPE" in line)
    assert "invalid_symbol" in lines[row + 1]
    assert "Invalid symbol." in lines[row + 1]


def test_a_very_long_failure_detail_wraps_instead_of_overrunning() -> None:
    text = render_daily_run(run(results=(failed("NOPE", "x " * 120),)))
    assert all(len(line) <= _WIDTH for line in text.splitlines())
    assert text.count("x") >= 120


# ============ 2. the page states its own nature ==============================


def test_the_header_denies_that_it_is_a_ranking() -> None:
    assert "not a ranking" in page().splitlines()[1]


def test_the_footer_says_readiness_is_about_the_analysis() -> None:
    text = page()
    assert "Readiness describes the analysis, not the instrument" in text
    assert "No ranking" in text


def test_every_limitation_is_printed() -> None:
    text = page()
    for code, _ in DAILY_LIMITATIONS:
        assert f"[{code}]" in text


def test_the_page_says_how_to_open_one_symbol_in_full() -> None:
    """The compact index is only safe if the full page is one command away."""
    assert "fmits swing SYMBOL" in page()


def test_the_counts_are_shown_and_agree_with_the_rows() -> None:
    text = page()
    assert "sufficient 1" in text
    assert "limited 1" in text
    assert "insufficient 1" in text
    assert "failed 1" in text
    assert "3 analysed · 1 failed" in text


# ============ 3. no colour is required ======================================


def test_every_category_carries_a_glyph_and_a_word_on_its_own_row() -> None:
    """Asserted **on the row**, not merely somewhere on the page.

    Every category word also appears in the summary counts, so a page-wide
    search passes even when the rows themselves show nothing but a glyph.
    """
    assert set(CATEGORY_GLYPH) == set(ResultCategory)
    rows = {
        line.split()[1]: line
        for line in page().splitlines()
        if line[:2] in {f" {glyph}" for glyph in CATEGORY_GLYPH.values()}
    }
    expected = {
        "BTCUSDT": ResultCategory.SUFFICIENT,
        "ETHUSDT": ResultCategory.LIMITED,
        "SOLUSDT": ResultCategory.INSUFFICIENT,
        "NOPE": ResultCategory.FAILED,
    }
    assert set(rows) == set(expected)
    for symbol, category in expected.items():
        assert CATEGORY_GLYPH[category] in rows[symbol], symbol
        assert category.value in rows[symbol], symbol


def test_the_glyphs_are_distinct() -> None:
    assert len(set(CATEGORY_GLYPH.values())) == len(ResultCategory)


def test_the_glyph_table_cannot_be_mutated_at_runtime() -> None:
    with pytest.raises(TypeError):
        CATEGORY_GLYPH[ResultCategory.FAILED] = "?"  # type: ignore[index]


def test_no_ansi_escape_reaches_the_page() -> None:
    assert "\x1b[" not in page()


# ============ 4. the width contract =========================================


def test_no_line_exceeds_the_page_width() -> None:
    long_names = tuple(
        completed(f"VERYLONGSYMBOLNAME{i}", regime="a " * 40) for i in range(3)
    )
    for text in (page(), render_daily_run(run(results=long_names))):
        for line in text.splitlines():
            assert len(line) <= _WIDTH, f"{len(line)}: {line}"


def test_an_over_wide_line_is_raised_rather_than_printed() -> None:
    """A future change cannot reintroduce the overrun silently."""
    from fmis.daily.models import DailyRunError

    long_limitation = (("AN-9", "unwrappable" * 20),)
    original = render_module.textwrap.wrap
    render_module.textwrap.wrap = lambda text, **kwargs: [  # type: ignore[assignment]
        kwargs.get("initial_indent", "") + text
    ]
    try:
        with pytest.raises(DailyRunError, match="exceeds the 78-column page"):
            render_daily_run(run(limitations=long_limitation))
    finally:
        render_module.textwrap.wrap = original  # type: ignore[assignment]


def test_an_absent_regime_renders_as_an_absence_not_a_blank() -> None:
    text = render_daily_run(run(results=(completed("BTCUSDT", regime=None),)))
    row = next(line for line in text.splitlines() if "BTCUSDT" in line)
    assert "—" in row


def test_a_failed_row_shows_an_absence_for_both_regime_and_as_of() -> None:
    row = next(line for line in page().splitlines()
               if line.split()[1:2] == ["NOPE"])
    assert row.count("—") == 2


# ============ 5. the renderer only renders ==================================


def test_the_renderer_imports_only_the_model() -> None:
    tree = ast.parse(RENDER_PATH.read_text())
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("fmis")
    }
    assert imported == {"fmis.daily.models"}


def test_the_renderer_calls_no_runner_and_no_engine() -> None:
    tree = ast.parse(RENDER_PATH.read_text())
    called = {
        getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    for forbidden in ("run_daily", "analyse_symbol", "workspace_for_symbol",
                      "classify_regime", "evaluate_context", "build_workspace"):
        assert forbidden not in called, forbidden


def test_the_renderer_computes_no_quantity_beyond_its_own_column_geometry() -> None:
    tree = ast.parse(RENDER_PATH.read_text())
    arithmetic = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp)
        and isinstance(node.op, (ast.Sub, ast.Div, ast.Pow, ast.Mod))
    ]
    # Column geometry only: header padding and the ellipsis position. Not one
    # of these touches a price, a count or anything the market produced.
    assert arithmetic == [
        "30 - len(left) - len(value)",
        "30 - len(left)",
        "width - 1",
    ]


def test_rendering_rejects_a_stranger() -> None:
    with pytest.raises(TypeError, match="must be a DailyRun"):
        render_daily_run({"results": []})  # type: ignore[arg-type]


def test_rendering_is_a_pure_function_of_the_run() -> None:
    assert page() == page()


# ============ 6. the CLI ====================================================


def _invoke(argv: list[str], transport) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    original = cli_module.run_daily

    def patched(symbols, **kwargs):
        kwargs["transport"] = transport
        kwargs["clock"] = lambda: LATER
        return original(symbols, **kwargs)

    cli_module.run_daily = patched  # type: ignore[assignment]
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = cli_module.main(argv)
    finally:
        cli_module.run_daily = original  # type: ignore[assignment]
    return code, out.getvalue(), err.getvalue()


def test_the_command_is_registered_and_documented() -> None:
    names = {command.name for command in cli_module.COMMANDS}
    assert "daily" in names
    daily = next(c for c in cli_module.COMMANDS if c.name == "daily")
    assert "not a ranking" in daily.description
    assert "readiness index" in daily.description


def test_the_command_renders_every_requested_symbol() -> None:
    code, out, err = _invoke(
        ["daily", "BTCUSDT", "ETHUSDT", "-n", "120"], universe_transport({})
    )
    assert code == 0, err
    assert "BTCUSDT" in out and "ETHUSDT" in out
    assert "not a ranking" in out


def test_a_failed_symbol_does_not_make_the_run_fail() -> None:
    """The other symbols succeeded, so the report is true and the exit is zero."""
    code, out, err = _invoke(
        ["daily", "BTCUSDT", "NOPE", "-n", "120"],
        universe_transport({"NOPE": NOT_FOUND}),
    )
    assert code == 0, err
    assert "invalid_symbol" in out


def test_an_invalid_universe_is_a_caller_error_with_no_partial_page() -> None:
    code, out, err = _invoke(
        ["daily", "BTCUSDT", "BTCUSDT"], universe_transport({})
    )
    assert code != 0
    assert out == ""
    assert "must not repeat" in err
    assert err.startswith("fmits daily:")


def test_the_reference_time_can_be_supplied_for_a_reproducible_page() -> None:
    code, out, _ = _invoke(
        ["daily", "BTCUSDT", "-n", "120", "--reference-time", "2026-06-01T00:00:00+00:00"],
        universe_transport({}),
    )
    assert code == 0
    assert "2026-06-01T00:00:00+00:00" in out


def test_the_command_applies_one_setting_to_every_symbol() -> None:
    seen: list[dict] = []
    original = cli_module.run_daily

    def spy(symbols, **kwargs):
        seen.append(kwargs)
        return original(symbols, **kwargs)

    cli_module.run_daily = spy  # type: ignore[assignment]
    try:
        _invoke(["daily", "BTCUSDT", "ETHUSDT", "-n", "120", "--left-bars", "3"],
                universe_transport({}))
    finally:
        cli_module.run_daily = original  # type: ignore[assignment]
    assert len(seen) == 1
    assert seen[0]["detection"].left_bars == 3
    assert seen[0]["limit"] == 120
    # Each role must carry **its own** interval. Passing one role's interval
    # under another's name produces a page headed by a timeframe it did not read.
    assert seen[0]["timeframes"] == dict(
        zip(TimeframeRole, ("1w", "1d", "4h"))
    ), seen[0]["timeframes"]


def test_the_command_requires_at_least_one_symbol() -> None:
    with pytest.raises(SystemExit):
        _invoke(["daily"], universe_transport({}))


# ============ 7. no value is ever shown cut in half =========================


def test_a_long_regime_is_clipped_with_a_mark_not_by_the_page_edge() -> None:
    """The defect this replaces printed an `AS OF` reading `2026-08-04T08:0`.

    A regime longer than its column used to push the timestamp past the page
    edge, where the row was truncated — cutting a *different* value in half with
    nothing to say it had happened.
    """
    long_regime = "transitioning · expanding · exceptionally elevated"
    text = render_daily_run(run(results=(completed("BTCUSDT", regime=long_regime),)))
    row = next(line for line in text.splitlines() if "BTCUSDT" in line)
    assert "…" in row, row
    assert row.endswith("2026-06-01 08:00"), row
    assert len(row) <= _WIDTH


def test_the_as_of_is_formatted_whole_rather_than_sliced() -> None:
    row = next(line for line in page().splitlines() if "BTCUSDT" in line)
    assert row.endswith("2026-06-01 08:00")


def test_a_long_symbol_is_clipped_without_disturbing_the_later_columns() -> None:
    text = render_daily_run(run(results=(completed("AVERYLONGSYMBOLNAMEINDEED"),)))
    row = next(line for line in text.splitlines() if "AVERYLONG" in line)
    assert "…" in row
    assert "sufficient" in row
    assert row.endswith("2026-06-01 08:00")
    assert len(row) <= _WIDTH


def test_the_header_and_the_rows_share_one_column_geometry() -> None:
    """Declared once, so a widened column cannot drift away from its heading."""
    lines = page().splitlines()
    header = next(line for line in lines if "SYMBOL" in line and "READINESS" in line)
    row = next(line for line in lines if "BTCUSDT" in line)
    assert header.index("READINESS") == row.index("sufficient")
    assert header.index("REGIME") == row.index("trending")
