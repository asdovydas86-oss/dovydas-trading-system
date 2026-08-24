"""Milestone BU — `fmits macro` at the surface.

The command's contract, matching `fmits pulse`'s: the **default with no
arguments is the useful one**, one unavailable market never costs the page, a
bad argument is a clean message rather than a traceback, and the exit code says
whether anything could be read.
"""

from __future__ import annotations

import pytest

from fmis.pipeline import cli
from tests.macro_helpers import fred_transport_for, not_found, series_ending
from tests.market_pulse_helpers import (
    error_response,
    instant,
    linear_klines,
    ok_response,
    transport_for,
)

AS_OF_INSTANT = instant(500)
AS_OF = AS_OF_INSTANT.isoformat()


@pytest.fixture
def fake_sources(monkeypatch):
    """Every default market answers, so the command needs no network.

    Patched at each adapter's transport seam rather than at the composition
    root, so the command exercises the real fetch path, the real decoder and the
    real canonical boundary.
    """
    from fmis.market_pulse import DEFAULT_PULSE_UNIVERSE, MACRO_PROVIDER
    from fmis.pipeline.market_data import MarketDataSources

    macro = {}
    crypto = {}
    for index, benchmark in enumerate(DEFAULT_PULSE_UNIVERSE.supported):
        symbol = benchmark.instrument.symbol
        if benchmark.instrument.provider == MACRO_PROVIDER:
            macro[symbol] = series_ending(
                symbol, AS_OF_INSTANT, base=100.0 + index, step=0.5 + index, count=60
            )
        else:
            crypto[symbol] = ok_response(linear_klines(100.0, float(index + 1), 200))
    state = {"macro": macro, "crypto": crypto}

    real = cli.run_macro_context

    def patched(**kwargs):
        kwargs["sources"] = MarketDataSources(
            binance_transport=transport_for(state["crypto"]),
            fred_transport=fred_transport_for(state["macro"]),
            clock=lambda: AS_OF_INSTANT,
        )
        return real(**kwargs)

    monkeypatch.setattr(cli, "run_macro_context", patched)
    return state


def run(argv, capsys):
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --------------------------------------------------------------------------
# Registration and parsing
# --------------------------------------------------------------------------


def test_the_command_is_registered_with_a_runner() -> None:
    command = next(entry for entry in cli.COMMANDS if entry.name == "macro")
    assert callable(command.run) and callable(command.configure)


def test_the_command_parses_with_no_arguments_at_all() -> None:
    """*The default command must be useful with no arguments.*"""
    args = cli.build_parser().parse_args(["macro"])
    assert args.benchmarks == []
    assert args.as_of is None
    assert args.no_relationships is False


def test_the_command_shares_no_configure_or_runner_with_another() -> None:
    macro = next(entry for entry in cli.COMMANDS if entry.name == "macro")
    others = [entry for entry in cli.COMMANDS if entry.name != "macro"]
    assert all(macro.configure is not entry.configure for entry in others)
    assert all(macro.run is not entry.run for entry in others)


def test_the_description_states_what_the_command_will_not_do() -> None:
    macro = next(entry for entry in cli.COMMANDS if entry.name == "macro")
    text = macro.description
    assert "no regime" in text
    assert "no risk-on or risk-off" in text
    assert "places no orders" in text
    assert "No setup, plan, position or approval is read" in text


# --------------------------------------------------------------------------
# The default run
# --------------------------------------------------------------------------


def test_the_default_run_prints_the_whole_page_and_exits_zero(
    fake_sources, capsys
) -> None:
    code, out, _ = run(["macro", "--as-of", AS_OF], capsys)
    assert code == cli.EXIT_OK
    for heading in ("MARKET LEVELS", "MOVES", "RATES", "UNAVAILABLE"):
        assert heading in out


def test_every_readable_macro_market_appears(fake_sources, capsys) -> None:
    _, out, _ = run(["macro", "--as-of", AS_OF], capsys)
    for benchmark_id in ("SPX", "USDBROAD", "US2Y", "US10Y", "VIX"):
        assert benchmark_id in out or benchmark_id.replace("US", "US ") in out


def test_the_markets_with_no_source_are_named_with_their_reason(
    fake_sources, capsys
) -> None:
    _, out, _ = run(["macro", "--as-of", AS_OF], capsys)
    flat = " ".join(out.split())
    assert "ICE US Dollar Index (DXY)" in flat
    assert "Gold (spot)" in flat
    assert "no configured source" in flat


def test_the_page_names_a_source_for_every_figure(fake_sources, capsys) -> None:
    _, out, _ = run(["macro", "--as-of", AS_OF], capsys)
    flat = " ".join(out.split())
    assert "fred SP500 1d" in flat
    assert "fred DGS10 1d" in flat


def test_a_yield_is_reported_in_basis_points(fake_sources, capsys) -> None:
    _, out, _ = run(["macro", "--as-of", AS_OF], capsys)
    assert " bp" in out


# --------------------------------------------------------------------------
# Options
# --------------------------------------------------------------------------


def test_a_subset_reports_only_the_markets_named(fake_sources, capsys) -> None:
    code, out, _ = run(["macro", "US10Y", "--as-of", AS_OF], capsys)
    assert code == cli.EXIT_OK
    assert "US 10-year Treasury yield" in " ".join(out.split())
    assert "S&P 500" not in out


def test_a_subset_is_reported_in_the_order_the_owner_typed(
    fake_sources, capsys
) -> None:
    """*Reordering it to match the configuration would ignore what they typed.*"""
    _, out, _ = run(["macro", "VIX", "SPX", "--as-of", AS_OF], capsys)
    flat = " ".join(out.split())
    levels = flat.split("MARKET LEVELS")[1]
    assert levels.index("CBOE Volatility Index") < levels.index("S&P 500")


def test_an_unknown_benchmark_is_a_clean_message_rather_than_a_traceback(
    fake_sources, capsys
) -> None:
    code, out, err = run(["macro", "NOPE", "--as-of", AS_OF], capsys)
    assert code == cli.EXIT_FAILURE
    assert "NOPE" in err
    assert "Traceback" not in err and "Traceback" not in out


def test_a_benchmark_named_twice_is_refused(fake_sources, capsys) -> None:
    code, _, err = run(["macro", "SPX", "SPX", "--as-of", AS_OF], capsys)
    assert code == cli.EXIT_FAILURE
    assert "twice" in err


def test_omitting_relationships_removes_the_section_body(
    fake_sources, capsys
) -> None:
    _, out, _ = run(["macro", "--as-of", AS_OF, "--no-relationships"], capsys)
    assert "No relationship was measured" in " ".join(out.split())


def test_relationships_are_measured_by_default(fake_sources, capsys) -> None:
    _, out, _ = run(["macro", "--as-of", AS_OF], capsys)
    assert "measured against: BTC" in " ".join(out.split())


def test_a_naive_as_of_is_refused_with_a_clean_message(fake_sources, capsys) -> None:
    code, out, err = run(["macro", "--as-of", "2026-08-21T20:00:00"], capsys)
    assert code == cli.EXIT_FAILURE
    assert "timezone-aware" in (out + err)


def test_the_page_is_reproducible_for_one_instant(fake_sources, capsys) -> None:
    _, first, _ = run(["macro", "--as-of", AS_OF], capsys)
    _, second, _ = run(["macro", "--as-of", AS_OF], capsys)
    assert first == second


# --------------------------------------------------------------------------
# Failure
# --------------------------------------------------------------------------


def test_one_unavailable_market_does_not_destroy_the_page(
    fake_sources, capsys
) -> None:
    fake_sources["macro"]["DGS10"] = not_found()
    code, out, _ = run(["macro", "--as-of", AS_OF], capsys)
    assert code == cli.EXIT_OK
    flat = " ".join(out.split())
    assert "source failure" in flat
    assert "S&P 500" in flat


def test_every_market_failing_still_prints_a_page_and_exits_non_zero(
    fake_sources, capsys
) -> None:
    for series_id in list(fake_sources["macro"]):
        fake_sources["macro"][series_id] = not_found()
    code, out, _ = run(["macro", "--as-of", AS_OF], capsys)
    assert code == cli.EXIT_FAILURE
    assert "it is a page with no data" in " ".join(out.split())


def test_a_failing_reference_leaves_the_rest_of_the_page_intact(
    fake_sources, capsys
) -> None:
    fake_sources["crypto"]["BTCUSDT"] = error_response()
    code, out, _ = run(["macro", "--as-of", AS_OF], capsys)
    assert code == cli.EXIT_OK
    flat = " ".join(out.split())
    assert "S&P 500" in flat
    assert "No relationship was measured" in flat


# --------------------------------------------------------------------------
# The command changes nothing
# --------------------------------------------------------------------------


def test_the_command_writes_nothing_to_the_filesystem(
    fake_sources, capsys, tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.rglob("*"))
    run(["macro", "--as-of", AS_OF], capsys)
    assert set(tmp_path.rglob("*")) == before


def test_the_command_reads_no_store_and_no_trading_decision() -> None:
    """*Do NOT allow macro data to alter CONFIRMED, CANDIDATE, WAIT, ranking,
    sizing or approval.* The surface has no way to reach any of them."""
    import ast
    import inspect
    import pathlib

    source = pathlib.Path(inspect.getfile(cli)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    run_macro = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_run_macro"
    )
    names = {
        node.id for node in ast.walk(run_macro) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(run_macro) if isinstance(node, ast.Attribute)
    }
    for banned in (
        "TradingStore",
        "run_swing_workspace",
        "run_today",
        "size_position",
        "approve",
        "record_trade",
        "default_store_root",
    ):
        assert banned not in names
