"""`fmits approve` — the surface, end to end, against a real store and no network.

Two properties are asserted here that no other file can:

* **A `BLOCKED` answer exits 0.** The evaluation succeeded and its answer was no,
  which is a first-class successful outcome in this product exactly as `WAIT` is.
  A non-zero code means the evaluation could not be produced at all.
* **The CLI parses nothing.** Every conversion runs through
  `fmis.position_sizing.inputs`, so a malformed flag comes back as that layer's
  refusal rather than as an argparse traceback.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from persistence_helpers import risk_budget, write_request
from position_sizing_helpers import ceiling
from trade_domain_helpers import AT, trade, trade_plan
from valuation_helpers import store_with, with_cash

from fmis.pipeline import cli as cli_module

REFERENCE = AT(12).isoformat()


def planted(root: Path, *, budget: Any = None, plans: tuple[Any, ...] = ()) -> Any:
    store = store_with(root, trade(), snapshots=(with_cash(),))
    if budget is not False:
        store.risk.create(
            risk_budget(limits=(ceiling("0.02"),)) if budget is None else budget,
            request=write_request(),
        )
    for plan in plans:
        store.plans.create(plan, request=write_request())
    return store


def run(root: Path, *extra: str) -> int:
    return cli_module.main(
        [
            "approve",
            "BTCUSDT",
            "--direction",
            "long",
            "--entry",
            "60000",
            "--stop",
            "58400",
            "--store-root",
            str(root),
            "--no-marks",
            "--reference-time",
            REFERENCE,
            *extra,
        ]
    )


# ==========================================================================
# 1. Registration
# ==========================================================================


def test_the_command_is_registered_with_a_runner_and_a_description() -> None:
    command = next(entry for entry in cli_module.COMMANDS if entry.name == "approve")
    assert callable(command.configure)
    assert callable(command.run)
    assert "never 'is this setup good'" in command.description
    assert "no order is placed" in command.description


def test_the_command_is_reachable_from_the_parser() -> None:
    parsed = cli_module.build_parser().parse_args(
        ["approve", "BTCUSDT", "--direction", "long", "--entry", "1", "--stop", "0.5"]
    )
    assert parsed.command == "approve"
    assert parsed.symbol == "BTCUSDT"


# ==========================================================================
# 2. The page
# ==========================================================================


def test_a_full_run_prints_the_page_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    planted(tmp_path)
    assert run(tmp_path, "--risk-fraction", "0.01") == 0
    text = capsys.readouterr().out
    assert "TRADE APPROVAL · BTCUSDT" in text
    assert "STATUS ·" in text
    assert "recommended size" in text
    assert "BLOCKING REASONS" in text
    assert "WARNINGS" in text


def test_a_blocked_answer_still_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The evaluation succeeded and said no. That is a result, not a failure."""
    planted(tmp_path)
    assert (
        cli_module.main(
            [
                "approve",
                "BTCUSDT",
                "--direction",
                "long",
                "--entry",
                "60000",
                "--stop",
                "61000",
                "--store-root",
                str(tmp_path),
                "--no-marks",
                "--reference-time",
                REFERENCE,
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "STATUS · BLOCKED" in text
    assert "[TR-STOP]" in text


def test_the_owners_flags_reach_the_sizing_policy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    planted(tmp_path)
    run(tmp_path, "--risk-fraction", "0.005", "--min-risk-reward", "3")
    text = capsys.readouterr().out
    assert "0.005" in text
    assert "[TR-RR]" in text


def test_a_stale_equity_bound_reaches_the_engine(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    planted(tmp_path)
    run(tmp_path, "--risk-fraction", "0.01", "--max-equity-age", "1h")
    assert "[TR-EQUITY-AGE]" in capsys.readouterr().out


# ==========================================================================
# 3. Sizing a recorded commitment
# ==========================================================================


def test_a_recorded_commitment_is_sized_without_retyping_its_stop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recorded = trade_plan()
    planted(tmp_path, plans=(recorded,))
    code = cli_module.main(
        [
            "approve",
            "--plan",
            recorded.plan_id,
            "--entry",
            "60000",
            "--store-root",
            str(tmp_path),
            "--no-marks",
            "--risk-fraction",
            "0.01",
            "--reference-time",
            REFERENCE,
        ]
    )
    assert code == 0
    text = capsys.readouterr().out
    assert "TRADE APPROVAL · BTCUSDT" in text
    assert "58400" in text


def test_restating_a_plans_stop_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A sizing call that could restate a stop would be the edit path the plan
    entity exists to prevent."""
    recorded = trade_plan()
    planted(tmp_path, plans=(recorded,))
    code = cli_module.main(
        [
            "approve",
            "--plan",
            recorded.plan_id,
            "--entry",
            "60000",
            "--stop",
            "59000",
            "--store-root",
            str(tmp_path),
            "--reference-time",
            REFERENCE,
        ]
    )
    assert code != 0
    assert "keep immutable" in capsys.readouterr().out


def test_an_unknown_commitment_is_reported_and_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    planted(tmp_path)
    code = cli_module.main(
        [
            "approve",
            "--plan",
            "trade_plan-nope-20260812T090000Z-0000",
            "--entry",
            "60000",
            "--store-root",
            str(tmp_path),
            "--reference-time",
            REFERENCE,
        ]
    )
    assert code == 1
    assert "holds no commitment" in capsys.readouterr().err


# ==========================================================================
# 4. Refusals the owner can act on
# ==========================================================================


def test_a_missing_symbol_names_every_flag_that_would_have_supplied_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    planted(tmp_path)
    code = cli_module.main(
        [
            "approve",
            "--entry",
            "60000",
            "--store-root",
            str(tmp_path),
            "--reference-time",
            REFERENCE,
        ]
    )
    assert code != 0
    text = capsys.readouterr().out
    assert "SYMBOL, --direction, --stop is required" in text


def test_a_store_with_no_budget_is_reported_with_the_remedy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    planted(tmp_path, budget=False)
    assert run(tmp_path) == 1
    assert "Record a risk budget" in capsys.readouterr().err


def test_a_malformed_price_is_the_boundarys_refusal_and_not_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    planted(tmp_path)
    code = cli_module.main(
        [
            "approve",
            "BTCUSDT",
            "--direction",
            "long",
            "--entry",
            "sixty thousand",
            "--stop",
            "58400",
            "--store-root",
            str(tmp_path),
            "--reference-time",
            REFERENCE,
        ]
    )
    assert code == 1
    assert "is not a decimal number" in capsys.readouterr().err


def test_a_corrupt_store_is_a_message_rather_than_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    planted(tmp_path)
    next(tmp_path.rglob("*.jsonl")).write_text("{ not json\n", encoding="utf-8")
    assert run(tmp_path) == 1
    assert "could not be read" in capsys.readouterr().err


def test_an_unresolvable_account_names_the_flag_that_fixes_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(tmp_path) == 1
    assert "Name one explicitly" in capsys.readouterr().err


def test_a_named_account_bypasses_the_inference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    planted(tmp_path)
    assert run(tmp_path, "--account", "binance_spot", "--risk-fraction", "0.01") == 0
    assert "account binance_spot" in capsys.readouterr().out


# ==========================================================================
# 5. The command writes nothing
# ==========================================================================


def test_the_command_leaves_the_store_byte_identical(tmp_path: Path) -> None:
    """Observed, not merely asserted: every file's bytes before and after."""
    planted(tmp_path)
    before = {
        path: path.read_bytes() for path in sorted(tmp_path.rglob("*")) if path.is_file()
    }
    run(tmp_path, "--risk-fraction", "0.01")
    after = {
        path: path.read_bytes() for path in sorted(tmp_path.rglob("*")) if path.is_file()
    }
    assert before == after
