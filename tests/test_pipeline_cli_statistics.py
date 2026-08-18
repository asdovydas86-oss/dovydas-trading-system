"""The five statistics commands, end to end through `main`.

Exercised through `cli_module.main` rather than by calling the renderers,
because the parsing, the flag threading and the exit code are what these tests
exist to hold — the figures themselves are held by the package's own suite.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fmis.pipeline import cli as cli_module

REFERENCE = "2026-03-20T00:00:00+00:00"
COMMANDS = ("statistics", "performance", "expectancy", "equity")


def run(capsys, *argv: str) -> tuple[int, str]:
    code = cli_module.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def populated(root: Path) -> None:
    """A store with one closed and one open recorded trade, via the write path."""
    from test_statistics_collect import close, write_trade

    plan_id = write_trade(root, symbol="BTC", entry="100", stop="90", size="10", day=0)
    close(root, plan_id, price="120", day=3)
    write_trade(root, symbol="ETH", entry="50", stop="45", size="20", day=5)


# --------------------------------------------------------------------------
# Every page, over a missing store and a populated one
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", COMMANDS)
def test_a_page_over_a_missing_store_exits_zero_and_says_why(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, name: str
) -> None:
    """A missing store is emptiness, not a failure: an owner who has recorded
    nothing has no statistics, and exiting non-zero would teach them the command
    is broken."""
    code, out = run(
        capsys, name, "--store-root", str(tmp_path / "nowhere"),
        "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_OK
    assert "NO TRADES" in out
    assert "No store exists at this path" in " ".join(out.split())


@pytest.mark.parametrize("name", COMMANDS)
def test_a_page_over_a_populated_store_prints_its_figures(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, name: str
) -> None:
    root = tmp_path / "store"
    populated(root)
    code, out = run(
        capsys, name, "--store-root", str(root),
        "--minimum-sample", "1", "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_OK
    assert "LIMITATIONS" in out
    assert "USDT" in out


def test_trades_summary_is_a_subcommand_and_prints_the_recent_trades(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = tmp_path / "store"
    populated(root)
    code, out = run(
        capsys, "trades", "summary", "--store-root", str(root),
        "--minimum-sample", "1", "--reference-time", REFERENCE, "--limit", "5",
    )
    assert code == cli_module.EXIT_OK
    assert "FMITS TRADES SUMMARY" in out
    assert "LAST 1 CLOSED" in out


def test_trades_without_a_subcommand_is_a_usage_error(
    capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli_module.main(["trades"])
    assert raised.value.code == 2


# --------------------------------------------------------------------------
# The flags, and what they change
# --------------------------------------------------------------------------


def test_the_sample_floor_flag_changes_which_rates_render(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = tmp_path / "store"
    populated(root)
    _, permissive = run(
        capsys, "expectancy", "--store-root", str(root),
        "--minimum-sample", "1", "--reference-time", REFERENCE,
    )
    _, strict = run(
        capsys, "expectancy", "--store-root", str(root),
        "--minimum-sample", "500", "--reference-time", REFERENCE,
    )
    assert "Win rate" in permissive
    assert "below the stated floor" in " ".join(strict.split())


def test_a_starting_equity_turns_the_curve_into_an_equity_curve(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = tmp_path / "store"
    populated(root)
    _, without = run(
        capsys, "equity", "--store-root", str(root), "--reference-time", REFERENCE
    )
    _, with_base = run(
        capsys, "equity", "--store-root", str(root),
        "--starting-equity", "10000", "--reference-time", REFERENCE,
    )
    assert "records the owner's opening capital nowhere" in " ".join(without.split())
    assert "10200" in with_base


def test_an_equity_basis_produces_the_risk_percentages(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = tmp_path / "store"
    populated(root)
    _, out = run(
        capsys, "statistics", "--store-root", str(root),
        "--equity-basis", "10000", "--minimum-sample", "1",
        "--reference-time", REFERENCE,
    )
    assert "Average risk %" in out
    assert "Equity basis" in out


def test_the_as_of_flag_narrows_the_corpus_to_what_was_knowable_then(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = tmp_path / "store"
    populated(root)
    _, out = run(
        capsys, "statistics", "--store-root", str(root),
        "--as-of", "2026-03-02T00:00:00+00:00",
        "--minimum-sample", "1", "--reference-time", REFERENCE,
    )
    assert "Point-in-time cut" in out
    # The BTC trade closed on day 3 and the cut is day 1, so **neither** trade
    # was knowable then: the ETH one was not committed until day 5, and the BTC
    # one was still open. A page that showed the BTC trade as closed would be
    # telling the owner something only the future revealed.
    assert "NO TRADES" in out


def test_a_naive_as_of_is_refused_with_a_sentence(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code, out = run(
        capsys, "statistics", "--store-root", str(tmp_path),
        "--as-of", "2026-03-02T00:00:00", "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_FAILURE
    assert "timezone-aware" in out


def test_a_bad_sample_floor_is_refused_rather_than_defaulted(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code, out = run(
        capsys, "statistics", "--store-root", str(tmp_path),
        "--minimum-sample", "0", "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_FAILURE
    assert "no floor at all" in out


def test_a_bad_starting_equity_is_refused_and_names_the_flag(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code, out = run(
        capsys, "equity", "--store-root", str(tmp_path),
        "--starting-equity", "-5", "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_FAILURE
    assert "--starting-equity" in out


def test_the_regime_dimension_flag_is_named_on_the_page(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A page cannot show *"by regime"* without saying which regime."""
    root = tmp_path / "store"
    populated(root)
    _, out = run(
        capsys, "statistics", "--store-root", str(root),
        "--regime", "volatility", "--minimum-sample", "1",
        "--reference-time", REFERENCE,
    )
    assert "Regime dimension           volatility" in out


def test_the_equity_page_points_flag_bounds_the_listing(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = tmp_path / "store"
    populated(root)
    _, out = run(
        capsys, "equity", "--store-root", str(root),
        "--points", "0", "--reference-time", REFERENCE,
    )
    assert "CLOSED-TRADE STEPS" not in out


# --------------------------------------------------------------------------
# Determinism and read-only
# --------------------------------------------------------------------------


def test_two_runs_over_one_store_print_the_identical_page(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = tmp_path / "store"
    populated(root)
    _, first = run(
        capsys, "statistics", "--store-root", str(root), "--reference-time", REFERENCE
    )
    _, second = run(
        capsys, "statistics", "--store-root", str(root), "--reference-time", REFERENCE
    )
    assert first == second


def test_a_statistics_run_writes_nothing_to_the_store(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """`AP` §25.2 classes these as disposable aggregates, so the store must be
    byte-identical after a run — asserted, not assumed."""
    import hashlib

    root = tmp_path / "store"
    populated(root)

    def fingerprint() -> str:
        digest = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            if path.is_file():
                digest.update(path.relative_to(root).as_posix().encode())
                digest.update(path.read_bytes())
        return digest.hexdigest()

    before = fingerprint()
    for name in COMMANDS:
        run(capsys, name, "--store-root", str(root), "--reference-time", REFERENCE)
    run(capsys, "trades", "summary", "--store-root", str(root),
        "--reference-time", REFERENCE)
    assert fingerprint() == before


@pytest.mark.parametrize("name", COMMANDS + ("trades",))
def test_every_command_carries_a_short_help_and_a_full_description(name: str) -> None:
    """Both, and they are different things: `help` is the one line `fmits
    --help` lists, and `description` is what the command's own `--help` prints.
    A command registered with one and not the other is reachable but
    unexplained."""
    command = next(c for c in cli_module.COMMANDS if c.name == name)
    assert command.help and len(command.help) < 80
    assert command.description and len(command.description) > 100
    assert command.description != command.help
