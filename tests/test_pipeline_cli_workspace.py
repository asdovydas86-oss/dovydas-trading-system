"""Milestone BS — `fmits workspace` at the command line.

Network-free: the composition root is stubbed, so no candle is fetched and no
provider is contacted. What is exercised here is the wiring — the flags, the
exit codes, the failure paths and the promise that this command and `fmits
today` are configured by one function rather than two that drift.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmis.pipeline import cli
from fmis.swing_setup import SetupState
from fmis.swing_workspace import SwingWorkspaceError, build_swing_workspace
from fmis.today import StoreUnreadableError

from tests.swing_workspace_helpers import (
    assessment,
    failed_result,
    result,
    run_of,
)

REFERENCE = "2026-08-20T21:00:00+00:00"


def _args(*extra: str):
    return cli.build_parser().parse_args(["workspace", *extra])


def _stub(monkeypatch, run):
    captured: dict = {}

    def _fake(symbols, **options):
        captured["symbols"] = tuple(symbols)
        captured.update(options)
        return build_swing_workspace(run)

    monkeypatch.setattr(cli, "run_swing_workspace", _fake)
    return captured


# ---------------------------------------------------------------------------
# Registration and configuration
# ---------------------------------------------------------------------------


def test_the_command_is_registered_after_today() -> None:
    names = [command.name for command in cli.COMMANDS]

    assert names.index("workspace") == names.index("today") + 1


def test_it_shares_the_days_own_configuration_function() -> None:
    """One configure function, not two that could drift apart."""
    workspace = next(c for c in cli.COMMANDS if c.name == "workspace")
    today = next(c for c in cli.COMMANDS if c.name == "today")

    assert workspace.configure is today.configure


def test_the_default_watchlist_is_the_scanners_own() -> None:
    from fmis.swing_setup import SCAN_UNIVERSE

    assert tuple(_args().symbols) == SCAN_UNIVERSE


def test_a_requested_watchlist_reaches_the_composition_root(monkeypatch) -> None:
    captured = _stub(monkeypatch, run_of(result(assessment("BTCUSDT"))))
    cli._run_workspace_command(
        _args("BTCUSDT", "ETHUSDT", "--reference-time", REFERENCE)
    )

    assert captured["symbols"] == ("BTCUSDT", "ETHUSDT")


def test_the_reference_time_is_passed_through_so_the_page_is_reproducible(
    monkeypatch,
) -> None:
    captured = _stub(monkeypatch, run_of(result(assessment())))
    cli._run_workspace_command(_args("--reference-time", REFERENCE))

    assert captured["reference_time"] == datetime(
        2026, 8, 20, 21, 0, tzinfo=timezone.utc
    )


def test_the_record_and_mark_switches_are_inverted_exactly_once(monkeypatch) -> None:
    captured = _stub(monkeypatch, run_of(result(assessment())))
    cli._run_workspace_command(
        _args("--no-records", "--no-marks", "--reference-time", REFERENCE)
    )

    assert captured["read_records"] is False
    assert captured["read_marks"] is False


# ---------------------------------------------------------------------------
# Output and exit codes
# ---------------------------------------------------------------------------


def test_a_successful_run_prints_the_page_and_exits_zero(monkeypatch, capsys) -> None:
    _stub(monkeypatch, run_of(result(assessment("BTCUSDT", state=SetupState.CONFIRMED))))
    code = cli._run_workspace_command(_args("--reference-time", REFERENCE))
    printed = capsys.readouterr().out

    assert code == cli.EXIT_OK
    assert "SWING DECISION WORKSPACE" in printed
    assert "TOP OPPORTUNITIES" in printed


def test_a_run_in_which_every_symbol_failed_exits_non_zero(monkeypatch, capsys) -> None:
    """The "at least one true report" contract `scan`, `daily` and `today` hold."""
    _stub(monkeypatch, run_of(failed_result("BTCUSDT"), failed_result("ETHUSDT")))
    code = cli._run_workspace_command(_args("--reference-time", REFERENCE))

    assert code == cli.EXIT_FAILURE
    assert "could not be read" in capsys.readouterr().out


def test_one_failure_among_several_symbols_still_exits_zero(monkeypatch) -> None:
    _stub(
        monkeypatch,
        run_of(result(assessment("BTCUSDT")), failed_result("ETHUSDT")),
    )

    assert cli._run_workspace_command(_args("--reference-time", REFERENCE)) == cli.EXIT_OK


@pytest.mark.parametrize(
    "failure",
    [
        StoreUnreadableError("the store at /x could not be read"),
        SwingWorkspaceError("a symbol reached both actionable states"),
    ],
)
def test_a_refusal_is_reported_on_stderr_and_exits_non_zero(
    monkeypatch, capsys, failure
) -> None:
    def _raise(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(cli, "run_swing_workspace", _raise)
    code = cli._run_workspace_command(_args("--reference-time", REFERENCE))
    captured = capsys.readouterr()

    assert code == cli.EXIT_FAILURE
    assert "fmits workspace:" in captured.err
    assert captured.out == ""


def test_a_programmer_error_is_never_rendered_as_an_ordinary_outcome(
    monkeypatch,
) -> None:
    def _raise(*_args, **_kwargs):
        raise AttributeError("a defect in this repository")

    monkeypatch.setattr(cli, "run_swing_workspace", _raise)
    with pytest.raises(AttributeError):
        cli._run_workspace_command(_args("--reference-time", REFERENCE))


def test_the_page_reaches_stdout_through_main(monkeypatch, capsys) -> None:
    _stub(monkeypatch, run_of(result(assessment("BTCUSDT"))))
    code = cli.main(["workspace", "BTCUSDT", "--reference-time", REFERENCE])

    assert code == cli.EXIT_OK
    assert "HOW THIS PAGE IS ORDERED" in capsys.readouterr().out


def test_the_help_text_states_that_risk_reward_orders_nothing() -> None:
    command = next(c for c in cli.COMMANDS if c.name == "workspace")

    assert "order nothing" in command.description
    assert "never writes to it" in command.description
