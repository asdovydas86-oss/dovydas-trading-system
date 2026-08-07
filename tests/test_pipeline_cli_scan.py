"""Milestones AT/AU — the `fmits scan` CLI surface.

No test here re-derives the directional policy (`tests/test_swing_setup_policy.py`),
the table renderer's own content rules (`tests/test_swing_setup_scan.py`) or the
intelligence report's own content rules (`tests/test_swing_setup_scan_report.py`)
— only parsing, wiring to the real composition root, per-symbol failure
isolation, exit codes, and which renderer `--table` selects.
"""

from __future__ import annotations

import pytest

from fmis.pipeline import cli as cli_module
from fmis.providers.binance import BinanceTransportError
from fmis.swing_setup import SCAN_UNIVERSE
from fmis.swing_setup import compose as compose_module
from fmis.swing_setup.compose import SetupRunResult
from tests.archive_helpers import multi
from tests.test_swing_setup_render import candidate_short_with_watched_level, confirmed_long


@pytest.fixture(autouse=True)
def _offline_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        compose_module, "multi_timeframe_facts_for_symbol",
        lambda symbol, **kw: multi(symbol=symbol),
    )


def test_scan_takes_no_symbol_argument() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(["scan"])
    assert args.command == "scan"
    assert not hasattr(args, "symbols")


def test_scan_accepts_role_and_band_flags() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(
        ["scan", "--context", "1M", "--setup", "1w", "--execution", "1d", "--band", "0.3"]
    )
    assert args.context == "1M"
    assert args.setup == "1w"
    assert args.execution == "1d"
    assert args.band == 0.3


def test_scan_rejects_an_unexpected_positional() -> None:
    parser = cli_module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["scan", "BTCUSDT"])


def test_scan_table_flag_defaults_to_false() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(["scan"])
    assert args.table is False


def test_scan_accepts_the_table_flag() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(["scan", "--table"])
    assert args.table is True


def test_scan_runs_and_prints_the_report_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_module.main(["scan"])
    assert exit_code == 0
    text = capsys.readouterr().out
    assert "FMITS MARKET SCANNER" in text
    assert "SCAN SUMMARY" in text
    for symbol in SCAN_UNIVERSE:
        assert symbol in text


def test_scan_prints_the_summary_counts(capsys: pytest.CaptureFixture[str]) -> None:
    cli_module.main(["scan"])
    text = capsys.readouterr().out
    assert "20 symbols scanned" in text
    assert "WAIT" in text and "CANDIDATE" in text and "CONFIRMED" in text and "ERROR" in text


def test_scan_table_runs_and_prints_a_table(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_module.main(["scan", "--table"])
    assert exit_code == 0
    text = capsys.readouterr().out
    assert "FMITS MARKET SCANNER" in text
    assert "SCAN SUMMARY" not in text
    for symbol in SCAN_UNIVERSE:
        assert symbol in text


def test_scan_table_prints_the_summary_counts(capsys: pytest.CaptureFixture[str]) -> None:
    cli_module.main(["scan", "--table"])
    text = capsys.readouterr().out
    assert "20 scanned" in text
    assert "WAIT" in text and "CANDIDATE" in text and "CONFIRMED" in text and "ERROR" in text


def test_a_failed_symbol_does_not_stop_the_scan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def flaky(symbol: str, **kw: object):
        if symbol == "BTCUSDT":
            raise BinanceTransportError("connection refused")
        return multi(symbol=symbol)

    monkeypatch.setattr(compose_module, "multi_timeframe_facts_for_symbol", flaky)
    exit_code = cli_module.main(["scan"])
    assert exit_code == 0  # at least one symbol succeeded
    text = capsys.readouterr().out
    assert "ERROR" in text
    assert "connection refused" in text
    for symbol in SCAN_UNIVERSE:
        assert symbol in text  # every requested symbol still appears


def test_scan_exit_code_is_nonzero_when_every_symbol_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def always_fails(symbol: str, **kw: object):
        raise BinanceTransportError("down")

    monkeypatch.setattr(compose_module, "multi_timeframe_facts_for_symbol", always_fails)
    exit_code = cli_module.main(["scan"])
    assert exit_code == 1


def test_scan_table_prints_top_opportunities_when_a_candidate_or_confirmed_exists(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixed = (
        SetupRunResult(requested_symbol="BTCUSDT", assessment=confirmed_long()),
        SetupRunResult(requested_symbol="DOTUSDT", assessment=candidate_short_with_watched_level()),
    )
    monkeypatch.setattr(cli_module, "run_market_scan", lambda **kw: fixed)
    exit_code = cli_module.main(["scan", "--table"])
    assert exit_code == 0
    text = capsys.readouterr().out
    assert "TOP OPPORTUNITIES" in text
    assert "BTCUSDT" in text
    assert "DOTUSDT" in text


def test_scan_table_omits_top_opportunities_when_every_result_waits(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli_module.main(["scan", "--table"])
    text = capsys.readouterr().out
    assert "TOP OPPORTUNITIES" not in text


def test_scan_default_prints_actionable_setups_when_a_candidate_or_confirmed_exists(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixed = (
        SetupRunResult(requested_symbol="BTCUSDT", assessment=confirmed_long()),
        SetupRunResult(requested_symbol="DOTUSDT", assessment=candidate_short_with_watched_level()),
    )
    monkeypatch.setattr(cli_module, "run_market_scan", lambda **kw: fixed)
    exit_code = cli_module.main(["scan"])
    assert exit_code == 0
    text = capsys.readouterr().out
    assert "ACTIONABLE SETUPS" in text
    assert "BTCUSDT" in text
    assert "DOTUSDT" in text


def test_scan_default_omits_actionable_setups_when_every_result_waits(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli_module.main(["scan"])
    text = capsys.readouterr().out
    assert "ACTIONABLE SETUPS" not in text


def test_scan_is_registered_with_the_expected_help_text() -> None:
    names = {c.name: c for c in cli_module.COMMANDS}
    assert "scan" in names
    assert "not a ranking" in names["scan"].description.lower()


def test_scan_does_not_appear_in_setups_symbol_positional_help() -> None:
    """`scan` and `setup` are distinct commands with distinct argument shapes."""
    parser = cli_module.build_parser()
    setup_args = parser.parse_args(["setup", "BTCUSDT"])
    scan_args = parser.parse_args(["scan"])
    assert setup_args.command == "setup"
    assert scan_args.command == "scan"
