"""Milestone BJ — the `fmits today` CLI surface.

No test here re-derives the directional policy, the warning rules or the page's
own content — those have their own modules. This one covers parsing, wiring to
the real composition root, that the command reads the store and never writes to
it, exit codes, and that a store failure is reported rather than traced.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fmis.pipeline import cli as cli_module
from fmis.swing_setup import SCAN_UNIVERSE
from fmis.swing_setup import compose as compose_module
from fmis.swing_setup.compose import SetupRunResult
from fmis.today import builder as builder_module

from tests.archive_helpers import multi
from tests.test_swing_setup_render import candidate_short_with_watched_level, confirmed_long


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        compose_module, "multi_timeframe_facts_for_symbol",
        lambda symbol, **kw: multi(symbol=symbol),
    )


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def test_today_is_registered_exactly_once() -> None:
    names = [command.name for command in cli_module.COMMANDS]
    assert names.count("today") == 1


def test_today_needs_no_arguments_and_defaults_to_the_watchlist() -> None:
    args = cli_module.build_parser().parse_args(["today"])
    assert args.symbols == list(SCAN_UNIVERSE)
    assert args.store_root is None
    assert args.no_records is False


def test_today_accepts_an_explicit_watchlist() -> None:
    args = cli_module.build_parser().parse_args(["today", "BTCUSDT", "ETHUSDT"])
    assert args.symbols == ["BTCUSDT", "ETHUSDT"]


def test_today_accepts_every_setup_style_flag() -> None:
    args = cli_module.build_parser().parse_args(
        [
            "today", "--context", "1M", "--setup", "1w", "--execution", "1d",
            "--band", "0.3", "--transition-lookback", "4", "-n", "300",
            "--left-bars", "3", "--right-bars", "3",
        ]
    )
    assert (args.context, args.setup, args.execution) == ("1M", "1w", "1d")
    assert args.band == 0.3
    assert args.transition_lookback == 4
    assert args.limit == 300


def test_today_accepts_the_record_flags() -> None:
    args = cli_module.build_parser().parse_args(
        [
            "today", "--store-root", "/tmp/store", "--archive-root", "/tmp/arch",
            "--no-records", "--reference-time", "2026-08-12T21:00:00+00:00",
        ]
    )
    assert args.store_root == "/tmp/store"
    assert args.archive_root == "/tmp/arch"
    assert args.no_records is True
    assert args.reference_time == "2026-08-12T21:00:00+00:00"


def test_today_rejects_an_unknown_flag() -> None:
    with pytest.raises(SystemExit):
        cli_module.build_parser().parse_args(["today", "--rank-by-risk-reward"])


def test_the_command_description_states_what_it_refuses_to_do() -> None:
    command = next(c for c in cli_module.COMMANDS if c.name == "today")
    assert "never writes" in command.description
    assert "ranked by desirability" in command.description
    assert "places no orders" in command.description


# --------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------


def _run(capsys, *argv: str) -> tuple[int, str]:
    code = cli_module.main(["today", *argv])
    return code, capsys.readouterr().out


def test_today_renders_a_full_page_and_exits_zero(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code, out = _run(
        capsys,
        "BTCUSDT",
        "--store-root", str(tmp_path / "store"),
        "--archive-root", str(tmp_path / "archive"),
        "--reference-time", "2026-08-12T21:00:00+00:00",
    )
    assert code == cli_module.EXIT_OK
    assert "FMITS TODAY" in out
    for heading in (
        "1. MARKET OVERVIEW", "2. PORTFOLIO OVERVIEW", "3. TODAY'S OPPORTUNITIES",
        "4. PRIORITY QUEUE", "5. TRADE JOURNAL", "6. RECENT ANALYSIS",
        "7. WORKSPACE WARNINGS",
    ):
        assert heading in out, heading


def test_today_creates_nothing_under_the_store_root(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A read-only surface, checked against the filesystem rather than promised."""
    root = tmp_path / "store"
    _run(
        capsys,
        "BTCUSDT",
        "--store-root", str(root),
        "--archive-root", str(tmp_path / "archive"),
        "--reference-time", "2026-08-12T21:00:00+00:00",
    )
    assert not root.exists()


def test_today_reads_a_populated_store(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from persistence_helpers import new_store, write_request
    from trade_domain_helpers import trade

    root = tmp_path / "store"
    new_store(root).trades.create(trade(), request=write_request())
    before = sorted(path.name for path in root.rglob("*"))
    _, out = _run(
        capsys,
        "BTCUSDT",
        "--store-root", str(root),
        "--archive-root", str(tmp_path / "archive"),
        "--reference-time", "2026-08-12T21:00:00+00:00",
    )
    assert "open positions (1)" in out
    assert sorted(path.name for path in root.rglob("*")) == before


def test_no_records_skips_the_store_and_says_so(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from persistence_helpers import new_store, write_request
    from trade_domain_helpers import trade

    root = tmp_path / "store"
    new_store(root).trades.create(trade(), request=write_request())
    _, out = _run(
        capsys,
        "BTCUSDT",
        "--store-root", str(root),
        "--no-records",
        "--reference-time", "2026-08-12T21:00:00+00:00",
    )
    assert "M-NO-STORE" in out
    assert "open positions (0)" in out


def test_a_symbol_that_fails_does_not_stop_the_run(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _mixed(symbols, **kwargs):
        return (
            SetupRunResult("BTCUSDT", assessment=confirmed_long()),
            SetupRunResult("BADUSDT", failure="provider rejected the symbol"),
        )

    monkeypatch.setattr(builder_module, "run_market_scan", _mixed)
    code, out = _run(
        capsys,
        "--store-root", str(tmp_path / "store"),
        "--archive-root", str(tmp_path / "archive"),
        "--reference-time", "2026-08-12T21:00:00+00:00",
    )
    assert code == cli_module.EXIT_OK
    assert "BADUSDT" in out
    assert "provider rejected the symbol" in out


def test_the_run_exits_non_zero_only_when_every_symbol_failed(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The same "at least one result is a true report" contract `scan` and
    `daily` already hold."""
    monkeypatch.setattr(
        builder_module,
        "run_market_scan",
        lambda symbols, **kwargs: (
            SetupRunResult("AUSDT", failure="down"),
            SetupRunResult("BUSDT", failure="down"),
        ),
    )
    code, _ = _run(
        capsys,
        "--store-root", str(tmp_path / "store"),
        "--reference-time", "2026-08-12T21:00:00+00:00",
    )
    assert code == cli_module.EXIT_FAILURE


def test_a_candidate_and_a_confirmed_result_both_reach_the_page(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        builder_module,
        "run_market_scan",
        lambda symbols, **kwargs: (
            SetupRunResult("BTCUSDT", assessment=confirmed_long()),
            SetupRunResult(
                "DOTUSDT", assessment=candidate_short_with_watched_level()
            ),
        ),
    )
    _, out = _run(
        capsys,
        "--store-root", str(tmp_path / "store"),
        "--reference-time", "2026-08-12T21:00:00+00:00",
    )
    assert "CONFIRMED" in out
    assert "CANDIDATE" in out


def test_a_corrupt_store_is_reported_rather_than_traced(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    from persistence_helpers import new_store, write_request
    from trade_domain_helpers import trade

    root = tmp_path / "store"
    new_store(root).trades.create(trade(), request=write_request())
    index = root / "index.jsonl"
    index.write_bytes(index.read_bytes().replace(b'"kind"', b'"knid"'))
    code = cli_module.main(
        [
            "today", "BTCUSDT",
            "--store-root", str(root),
            "--reference-time", "2026-08-12T21:00:00+00:00",
        ]
    )
    captured = capsys.readouterr()
    assert code == cli_module.EXIT_FAILURE
    assert "fmits today: StoreUnreadableError" in captured.err
    assert captured.out == ""


def test_the_reference_time_pins_the_page(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Two runs at the same stated instant produce byte-identical output."""
    argv = (
        "BTCUSDT",
        "--store-root", str(tmp_path / "store"),
        "--archive-root", str(tmp_path / "archive"),
        "--reference-time", "2026-08-12T21:00:00+00:00",
    )
    _, first = _run(capsys, *argv)
    _, second = _run(capsys, *argv)
    assert first == second
    assert "2026-08-12T21:00:00+00:00" in first


def test_a_naive_reference_time_is_rejected(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`main` maps it to a message and an exit code, as it does for every other
    caller error — no traceback reaches the terminal."""
    code = cli_module.main(
        ["today", "BTCUSDT", "--reference-time", "2026-08-12T21:00:00"]
    )
    assert code == cli_module.EXIT_FAILURE
    assert "timezone-aware" in capsys.readouterr().out
