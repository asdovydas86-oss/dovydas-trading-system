"""Milestone AR — the `fmits setup` CLI surface.

No test here re-derives the policy itself (covered in
`tests/test_swing_setup_policy.py`) — only parsing, wiring to the real
composition root, multi-symbol ordering, per-symbol failure isolation, and
exit codes.
"""

from __future__ import annotations

import pytest

from fmis.pipeline import cli as cli_module
from fmis.providers.binance import BinanceTransportError
from fmis.swing_setup import compose as compose_module
from tests.archive_helpers import multi


@pytest.fixture(autouse=True)
def _offline_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        compose_module, "multi_timeframe_facts_for_symbol",
        lambda symbol, **kw: multi(symbol=symbol),
    )


def test_setup_parses_one_symbol() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(["setup", "BTCUSDT"])
    assert args.command == "setup"
    assert args.symbols == ["BTCUSDT"]


def test_setup_parses_several_symbols_in_order() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(["setup", "ETHUSDT", "BTCUSDT", "SOLUSDT"])
    assert args.symbols == ["ETHUSDT", "BTCUSDT", "SOLUSDT"]


def test_setup_requires_at_least_one_symbol() -> None:
    parser = cli_module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["setup"])


def test_setup_accepts_role_and_band_flags() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(
        ["setup", "BTCUSDT", "--context", "1M", "--setup", "1w", "--execution", "1d", "--band", "0.3"]
    )
    assert args.context == "1M"
    assert args.setup == "1w"
    assert args.execution == "1d"
    assert args.band == 0.3


def test_setup_runs_and_prints_a_page(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_module.main(["setup", "BTCUSDT"])
    assert exit_code == 0
    text = capsys.readouterr().out
    assert "SWING SETUP" in text
    assert "BTCUSDT" in text


def test_setup_prints_one_page_per_symbol_in_order(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_module.main(["setup", "ETHUSDT", "BTCUSDT"])
    assert exit_code == 0
    text = capsys.readouterr().out
    assert text.index("ETHUSDT") < text.index("BTCUSDT")


def test_a_failed_symbol_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def flaky(symbol: str, **kw: object):
        if symbol == "BADUSDT":
            raise BinanceTransportError("connection refused")
        return multi(symbol=symbol)

    monkeypatch.setattr(compose_module, "multi_timeframe_facts_for_symbol", flaky)
    exit_code = cli_module.main(["setup", "BTCUSDT", "BADUSDT", "ETHUSDT"])
    assert exit_code == 0  # at least one symbol succeeded
    out = capsys.readouterr()
    assert "BTCUSDT" in out.out
    assert "ETHUSDT" in out.out
    assert "BADUSDT" in out.err
    assert "BinanceTransportError" in out.err


def test_exit_code_is_nonzero_when_every_symbol_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def always_fails(symbol: str, **kw: object):
        raise BinanceTransportError("down")

    monkeypatch.setattr(compose_module, "multi_timeframe_facts_for_symbol", always_fails)
    exit_code = cli_module.main(["setup", "BTCUSDT"])
    assert exit_code == 1


def test_setup_is_registered_with_the_expected_help_text() -> None:
    names = {c.name: c for c in cli_module.COMMANDS}
    assert "setup" in names
    assert "WAIT" in names["setup"].description
