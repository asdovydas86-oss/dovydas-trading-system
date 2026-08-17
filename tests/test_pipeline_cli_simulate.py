"""Milestone BO — `fmits simulate` and the six new `fmits trade` subcommands.

Every test runs the parser and the dispatcher end to end against a temporary
store, with no network: the simulation path is exercised by driving the store
directly and then reading it back through the CLI, so what is checked here is the
**surface** — the arguments, the refusals, the exit codes and the pages.

The rule this file protects hardest is `BJ`'s: `fmis.pipeline` parses strings and
reaches nothing. A conversion that appeared in the parser would be caught by
`tests/test_paper_architecture.py`; what is caught here is a command that
*works* only because it did.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from fmis.pipeline import cli as cli_module
from paper_helpers import at, bar

REFERENCE = "2026-08-01T08:00:00+00:00"


def _run(capsys, *argv: str) -> tuple[int, str]:
    code = cli_module.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _plan(capsys, root: Path, **extra: str) -> str:
    code, out = _run(
        capsys,
        "trade",
        "plan",
        "BTCUSDT",
        "--direction",
        "long",
        "--book",
        "paper",
        "--stop",
        "95",
        "--target",
        "110",
        "--target",
        "120",
        "--confidence",
        "medium",
        "--store-root",
        str(root),
        "--reference-time",
        "2026-08-01T00:00:00+00:00",
        *[item for pair in extra.items() for item in pair],
    )
    assert code == cli_module.EXIT_OK, out
    # Read the id back from the store rather than scraping the page: ids are
    # wrapped across lines at 78 columns, and a scraped prefix is exactly the
    # unusable half-id the renderer's own wrapping test exists to prevent.
    return _plan_id(root)


def _plan_id(root: Path) -> str:
    from fmis.paper import PAPER_DUST_POLICY
    from fmis.persistence import TradingStore

    return TradingStore(root, dust=PAPER_DUST_POLICY).plans.plans()[0].plan_id


def _activate(capsys, root: Path, plan_id: str, *extra: str) -> str:
    code, out = _run(
        capsys,
        "trade",
        "activate",
        plan_id,
        "--size",
        "1",
        "--entry-type",
        "stop_entry",
        "--entry",
        "100",
        "--share",
        "0.5",
        "--share",
        "0.5",
        "--store-root",
        str(root),
        "--reference-time",
        "2026-08-01T00:00:00+00:00",
        *extra,
    )
    assert code == cli_module.EXIT_OK, out
    return _activation_id(root)


def _activation_id(root: Path) -> str:
    from fmis.paper import PAPER_DUST_POLICY
    from fmis.persistence import TradingStore

    store = TradingStore(root, dust=PAPER_DUST_POLICY)
    return store.activations.activations()[0].activation_id


def _simulate_directly(root: Path, bars, hours: int = 8) -> None:
    from fmis.paper import PAPER_DUST_POLICY, run_simulation
    from fmis.persistence import TradingStore

    run_simulation(
        TradingStore(root, dust=PAPER_DUST_POLICY),
        ran_at=at(hours),
        code_version="test",
        interval="1h",
        bars_by_symbol={"BTCUSDT": bars},
    )


WINNING_BARS = (
    bar(0, "99", "101", "98", "100"),
    bar(1, "100", "112", "99", "111"),
    bar(2, "111", "121", "110", "120"),
)


# --------------------------------------------------------------------------
# The registry and the parser
# --------------------------------------------------------------------------


def test_simulate_is_registered_between_trade_and_archive() -> None:
    names = [command.name for command in cli_module.COMMANDS]
    assert names[names.index("trade") + 1] == "simulate"
    assert names[names.index("simulate") + 1] == "archive"


def test_every_new_trade_subcommand_parses() -> None:
    parser = cli_module.build_parser()
    for argv in (
        ["trade", "plan", "BTCUSDT", "--direction", "long", "--book", "paper",
         "--stop", "95", "--confidence", "medium"],
        ["trade", "activate", "X", "--size", "1", "--entry-type", "market"],
        ["trade", "stop", "X", "--to", "99", "--reason", "de_risking"],
        ["trade", "cancel", "X", "--reason", "thesis_invalidated"],
        ["trade", "status"],
        ["trade", "history"],
        ["trade", "lifecycle", "X"],
        ["simulate"],
        ["simulate", "--all"],
        ["simulate", "BTCUSDT", "ETHUSDT"],
    ):
        parser.parse_args(argv)


def test_naming_markets_and_asking_for_all_at_once_is_a_usage_error(capsys) -> None:
    code, out = _run(capsys, "simulate", "BTCUSDT", "--all")
    assert code == cli_module.EXIT_FAILURE
    assert "not both" in out


# --------------------------------------------------------------------------
# The write paths
# --------------------------------------------------------------------------


def test_planning_writes_a_commitment_with_no_fill(capsys, tmp_path: Path) -> None:
    root = tmp_path / "store"
    plan_id = _plan(capsys, root)
    assert plan_id.startswith("trade_plan-")
    code, out = _run(
        capsys, "trade", "show", plan_id, "--store-root", str(root),
        "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_OK
    assert "PLANNED" in out


def test_activating_prints_the_records_it_wrote(capsys, tmp_path: Path) -> None:
    root = tmp_path / "store"
    plan_id = _plan(capsys, root)
    _activate(capsys, root, plan_id)
    code, out = _run(
        capsys, "trade", "status", "--store-root", str(root),
        "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_OK
    assert "open activations   1" in out
    assert "pending" in out


def test_the_size_asset_is_read_off_the_commitment_and_never_typed(
    capsys, tmp_path: Path
) -> None:
    """`1` is a legal quantity of BTC and of USDT, and only the market says
    which one the owner meant."""
    root = tmp_path / "store"
    plan_id = _plan(capsys, root)
    _activate(capsys, root, plan_id)
    from fmis.paper import PAPER_DUST_POLICY
    from fmis.persistence import TradingStore

    store = TradingStore(root, dust=PAPER_DUST_POLICY)
    assert store.activations.activations()[0].quantity.asset.code == "BTC"


def test_a_market_entry_carrying_a_level_is_refused_with_both_values_named(
    capsys, tmp_path: Path
) -> None:
    root = tmp_path / "store"
    plan_id = _plan(capsys, root)
    code, out = _run(
        capsys, "trade", "activate", plan_id, "--size", "1", "--entry-type",
        "market", "--entry", "100", "--store-root", str(root),
        "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_FAILURE
    assert "waits for no level" in out


def test_a_limit_entry_with_no_level_is_refused(capsys, tmp_path: Path) -> None:
    root = tmp_path / "store"
    plan_id = _plan(capsys, root)
    code, out = _run(
        capsys, "trade", "activate", plan_id, "--size", "1", "--entry-type",
        "limit", "--store-root", str(root), "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_FAILURE
    assert "defined by the price it waits for" in out


def test_a_break_even_offset_with_no_trigger_is_refused(
    capsys, tmp_path: Path
) -> None:
    root = tmp_path / "store"
    plan_id = _plan(capsys, root)
    code, out = _run(
        capsys, "trade", "activate", plan_id, "--size", "1", "--entry-type",
        "market", "--break-even-offset-r", "0.1", "--store-root", str(root),
        "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_FAILURE
    assert "nothing to be past" in out


def test_a_trail_start_with_no_distance_is_refused(capsys, tmp_path: Path) -> None:
    root = tmp_path / "store"
    plan_id = _plan(capsys, root)
    code, out = _run(
        capsys, "trade", "activate", plan_id, "--size", "1", "--entry-type",
        "market", "--trail-start-r", "1", "--store-root", str(root),
        "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_FAILURE
    assert "how much" in out


def test_moving_a_stop_prints_the_records_and_leaves_the_plan_alone(
    capsys, tmp_path: Path
) -> None:
    root = tmp_path / "store"
    plan_id = _plan(capsys, root)
    _activate(capsys, root, plan_id)
    activation_id = _activation_id(root)
    code, out = _run(
        capsys, "trade", "stop", activation_id, "--to", "97", "--reason",
        "structure_changed", "--store-root", str(root),
        "--reference-time", "2026-08-01T01:00:00+00:00",
    )
    assert code == cli_module.EXIT_OK
    assert "STOP AMENDED" in out
    assert "stop_amendment" in out
    from fmis.persistence import TradingStore
    from fmis.paper import PAPER_DUST_POLICY

    store = TradingStore(root, dust=PAPER_DUST_POLICY)
    assert store.plans.load(plan_id).initial_invalidation == Decimal("95")


def test_cancelling_prints_a_receipt(capsys, tmp_path: Path) -> None:
    root = tmp_path / "store"
    plan_id = _plan(capsys, root)
    _activate(capsys, root, plan_id)
    activation_id = _activation_id(root)
    code, out = _run(
        capsys, "trade", "cancel", activation_id, "--reason", "thesis_invalidated",
        "--store-root", str(root), "--reference-time", "2026-08-01T01:00:00+00:00",
    )
    assert code == cli_module.EXIT_OK
    assert "CANCELLED" in out


def test_a_refusal_exits_non_zero_and_is_not_a_crash(capsys, tmp_path: Path) -> None:
    root = tmp_path / "store"
    code, out = _run(
        capsys, "trade", "lifecycle",
        "trade_activation-x-20260801T000000Z-" + "0" * 16,
        "--store-root", str(root), "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_FAILURE
    assert "fmits trade" in out


# --------------------------------------------------------------------------
# The read paths
# --------------------------------------------------------------------------


def test_status_history_and_lifecycle_read_a_finished_trade(
    capsys, tmp_path: Path
) -> None:
    root = tmp_path / "store"
    plan_id = _plan(capsys, root)
    _activate(capsys, root, plan_id)
    activation_id = _activation_id(root)
    _simulate_directly(root, WINNING_BARS)

    code, status = _run(
        capsys, "trade", "status", "--store-root", str(root),
        "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_OK
    assert "open activations   0" in status

    code, history = _run(
        capsys, "trade", "history", "--store-root", str(root),
        "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_OK
    assert "target_hit" in history
    assert "final R" in history

    code, lifecycle = _run(
        capsys, "trade", "lifecycle", activation_id, "--store-root", str(root),
        "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_OK
    assert "LIFECYCLE" in lifecycle
    assert "FILLS" in lifecycle


def test_a_listing_can_be_narrowed_to_one_market(capsys, tmp_path: Path) -> None:
    root = tmp_path / "store"
    plan_id = _plan(capsys, root)
    _activate(capsys, root, plan_id)
    code, out = _run(
        capsys, "trade", "status", "--symbol", "ETHUSDT", "--store-root",
        str(root), "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_OK
    assert "open activations   0" in out


def test_every_page_fits_the_terminal_width(capsys, tmp_path: Path) -> None:
    root = tmp_path / "store"
    plan_id = _plan(capsys, root)
    _activate(capsys, root, plan_id)
    _simulate_directly(root, WINNING_BARS)
    for argv in (
        ("trade", "status"),
        ("trade", "history"),
        ("trade", "lifecycle", _activation_id(root)),
    ):
        _, out = _run(
            capsys, *argv, "--store-root", str(root),
            "--reference-time", REFERENCE,
        )
        for line in out.splitlines():
            assert len(line) <= 78, line


def test_today_shows_the_paper_section_after_the_queue(capsys, tmp_path: Path) -> None:
    root = tmp_path / "store"
    plan_id = _plan(capsys, root)
    _activate(capsys, root, plan_id)
    code, out = _run(
        capsys,
        "today",
        "BTCUSDT",
        "--store-root",
        str(root),
        "--archive-root",
        str(tmp_path / "archive"),
        "--reference-time",
        REFERENCE,
    )
    assert code == cli_module.EXIT_OK
    assert out.index("5. PAPER TRADING") > out.index("4. PRIORITY QUEUE")
    assert out.index("6. TRADE JOURNAL") > out.index("5. PAPER TRADING")
    assert "PENDING (1)" in out


def test_simulate_with_no_live_activation_says_so(capsys, tmp_path: Path) -> None:
    root = tmp_path / "store"
    code, out = _run(
        capsys, "simulate", "--store-root", str(root),
        "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_OK
    assert "No activation in this store is waiting for a bar" in out
