"""`fmits trade` — parsing, dispatch, exit codes, and what a refusal looks like.

The CLI holds no logic, so these tests are about two things: that every flag
reaches the capture layer intact, and that **a refusal is reported as a refusal**
— non-zero, on stderr, naming the two values that disagree — rather than as a
crash the owner cannot act on.

**Every invocation names `--store-root` and `--reference-time`.** The first keeps
the owner's real store untouched; the second keeps the pages reproducible, since
the CLI is the one place in this repository that reads a clock.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fmis.pipeline import cli as cli_module

REFERENCE = "2026-08-12T11:00:00+00:00"
LATER = "2026-08-14T10:00:00+00:00"


def _record(root: Path, *extra: str) -> list[str]:
    return [
        "trade", "record", "BTCUSDT",
        "--direction", "long",
        "--account", "binance_spot",
        "--book", "swing",
        "--entry", "60000",
        "--stop", "58400",
        "--target", "64000",
        "--size", "0.5",
        "--fee", "15",
        "--fx-rate", "10.5",
        "--fx-source", "riksbank",
        "--confidence", "moderate",
        "--occurred-at", "2026-08-12T10:00:00+00:00",
        "--reference-time", REFERENCE,
        "--store-root", str(root),
        *extra,
    ]


def _plan_id(root: Path, capsys) -> str:
    """The id of the single recorded trade, read back off the listing."""
    assert cli_module.main(
        ["trade", "list", "--store-root", str(root), "--reference-time", REFERENCE]
    ) == 0
    text = capsys.readouterr().out
    joined = "".join(line.strip() for line in text.splitlines())
    start = joined.index("trade_plan-")
    return joined[start : start + len("trade_plan-binance_BTCUSDT_spot-20260812T100000Z-0123456789abcdef")]


# --------------------------------------------------------------------------
# Parsing.
# --------------------------------------------------------------------------


def test_the_trade_command_is_reachable_from_the_parser() -> None:
    parser = cli_module.build_parser()
    action = next(a for a in parser._actions if a.dest == "command")
    assert "trade" in action.choices


@pytest.mark.parametrize(
    "subcommand", ["record", "show", "list", "note", "close"]
)
def test_every_subcommand_is_registered(subcommand: str) -> None:
    parser = cli_module.build_parser()
    trade = next(a for a in parser._actions if a.dest == "command").choices["trade"]
    action = next(a for a in trade._actions if a.dest == "trade_command")
    assert subcommand in action.choices


def test_record_parses_every_flag_it_offers(tmp_path: Path) -> None:
    args = cli_module.build_parser().parse_args(
        _record(
            tmp_path,
            "--target", "68000",
            "--setup", "trend_continuation",
            "--thesis", "the weekly retest held",
            "--note", "sized down",
            "--author", "dovydas",
            "--quote", "USDT",
            "--venue", "binance",
            "--mode", "spot",
        )
    )
    assert args.command == "trade"
    assert args.trade_command == "record"
    assert args.symbol == "BTCUSDT"
    assert args.targets == ["64000", "68000"]
    assert args.setup == "trend_continuation"
    assert args.author == "dovydas"


def test_a_subcommand_is_required() -> None:
    with pytest.raises(SystemExit):
        cli_module.build_parser().parse_args(["trade"])


def test_a_book_must_be_named_because_it_is_never_inferred(tmp_path: Path) -> None:
    flags = [flag for flag in _record(tmp_path) if flag not in ("--book", "swing")]
    with pytest.raises(SystemExit):
        cli_module.build_parser().parse_args(flags)


def test_the_fx_rate_is_required_because_it_cannot_be_recovered(
    tmp_path: Path,
) -> None:
    flags = [flag for flag in _record(tmp_path) if flag not in ("--fx-rate", "10.5")]
    with pytest.raises(SystemExit):
        cli_module.build_parser().parse_args(flags)


def test_an_unknown_direction_is_rejected_by_the_parser(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli_module.build_parser().parse_args(
            [flag if flag != "long" else "sideways" for flag in _record(tmp_path)]
        )


# --------------------------------------------------------------------------
# Recording.
# --------------------------------------------------------------------------


def test_recording_a_trade_prints_a_receipt_and_the_page(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_module.main(_record(tmp_path, "--thesis", "the retest held")) == 0
    text = capsys.readouterr().out
    assert "RECORDED" in text
    assert "trade_plan       created" in text
    assert "RECORDED TRADE — BTCUSDT long" in text
    assert "capital at risk  800 USDT" in text


def test_recording_writes_into_the_store_root_it_was_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_module.main(_record(tmp_path)) == 0
    capsys.readouterr()
    assert (tmp_path / "index.jsonl").is_file()
    assert (tmp_path / "records" / "trade_plan").is_dir()
    assert (tmp_path / "ledger" / "trade").is_dir()


def test_recording_the_same_trade_twice_records_it_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_module.main(_record(tmp_path)) == 0
    capsys.readouterr()
    assert cli_module.main(_record(tmp_path)) == 0
    text = capsys.readouterr().out
    assert "already stored, unchanged" in text


def test_a_short_trade_records_through_the_same_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flags = _record(tmp_path)
    flags[flags.index("long")] = "short"
    flags[flags.index("58400")] = "62000"
    flags[flags.index("64000")] = "55000"
    assert cli_module.main(flags) == 0
    assert "BTCUSDT short" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Reading.
# --------------------------------------------------------------------------


def test_show_prints_the_trade_it_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_module.main(_record(tmp_path)) == 0
    capsys.readouterr()
    plan_id = _plan_id(tmp_path, capsys)
    capsys.readouterr()
    assert cli_module.main(
        ["trade", "show", plan_id, "--store-root", str(tmp_path),
         "--reference-time", REFERENCE]
    ) == 0
    assert "RECORDED TRADE" in capsys.readouterr().out


def test_list_on_an_empty_store_succeeds_and_says_it_is_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_module.main(
        ["trade", "list", "--store-root", str(tmp_path), "--reference-time", REFERENCE]
    ) == 0
    assert "does not mean nothing is held" in capsys.readouterr().out


def test_list_filters_and_says_what_it_excluded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_module.main(_record(tmp_path)) == 0
    capsys.readouterr()
    assert cli_module.main(
        ["trade", "list", "--symbol", "ETHUSDT", "--store-root", str(tmp_path),
         "--reference-time", REFERENCE]
    ) == 0
    text = capsys.readouterr().out
    assert "symbol=ETHUSDT" in text
    assert "0 of 1 recorded (1 excluded" in text


def test_list_accepts_every_filter_axis(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_module.main(_record(tmp_path)) == 0
    capsys.readouterr()
    assert cli_module.main(
        [
            "trade", "list",
            "--status", "open",
            "--symbol", "BTCUSDT",
            "--account", "binance_spot",
            "--direction", "long",
            "--since", "2026-08-01T00:00:00+00:00",
            "--until", "2026-08-31T00:00:00+00:00",
            "--store-root", str(tmp_path),
            "--reference-time", REFERENCE,
        ]
    ) == 0
    assert "1 of 1 recorded" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Noting and closing.
# --------------------------------------------------------------------------


def test_note_appends_an_entry_and_prints_the_page(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_module.main(_record(tmp_path)) == 0
    capsys.readouterr()
    plan_id = _plan_id(tmp_path, capsys)
    capsys.readouterr()
    assert cli_module.main(
        ["trade", "note", plan_id, "--body", "holding through the weekly close",
         "--title", "mid-trade", "--store-root", str(tmp_path),
         "--reference-time", REFERENCE]
    ) == 0
    text = capsys.readouterr().out
    assert "NOTED" in text
    assert "holding through the weekly close" in text


def test_close_appends_an_exit_and_reports_the_realized_figures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_module.main(_record(tmp_path)) == 0
    capsys.readouterr()
    plan_id = _plan_id(tmp_path, capsys)
    capsys.readouterr()
    assert cli_module.main(
        [
            "trade", "close", plan_id,
            "--price", "63800",
            "--fee", "16",
            "--fx-rate", "10.6",
            "--fx-source", "riksbank",
            "--reason", "target_reached",
            "--note", "took it at the first target",
            "--occurred-at", "2026-08-14T09:00:00+00:00",
            "--store-root", str(tmp_path),
            "--reference-time", LATER,
        ]
    ) == 0
    text = capsys.readouterr().out
    assert "CLOSED" in text
    assert "realized net     1869 USDT" in text
    assert "exit_reason:target_reached" in text


def test_a_close_requires_a_reason(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli_module.build_parser().parse_args(
            ["trade", "close", "an-id", "--price", "1", "--fee", "0",
             "--fx-rate", "1", "--fx-source", "x"]
        )


# --------------------------------------------------------------------------
# Refusals.
# --------------------------------------------------------------------------


def test_a_stop_on_the_wrong_side_exits_non_zero_and_says_why(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flags = _record(tmp_path)
    flags[flags.index("58400")] = "61000"
    assert cli_module.main(flags) == cli_module.EXIT_FAILURE
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "PlanPlacementError" in captured.err
    assert "is not below the entry" in captured.err


def test_a_refused_capture_leaves_the_store_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flags = _record(tmp_path)
    flags[flags.index("58400")] = "61000"
    assert cli_module.main(flags) == cli_module.EXIT_FAILURE
    capsys.readouterr()
    assert not (tmp_path / "records" / "trade_plan").exists()


def test_a_numeric_confidence_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flags = _record(tmp_path)
    flags[flags.index("moderate")] = "0.7"
    assert cli_module.main(flags) == cli_module.EXIT_FAILURE
    assert "looks like a number" in capsys.readouterr().err


def test_showing_a_trade_that_is_not_stored_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_module.main(
        ["trade", "show", "trade_plan-x-20260812T100000Z-0123456789abcdef",
         "--store-root", str(tmp_path), "--reference-time", REFERENCE]
    ) == cli_module.EXIT_FAILURE
    assert "TradeNotFoundError" in capsys.readouterr().err


def test_a_symbol_that_cannot_be_split_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flags = _record(tmp_path) + ["--quote", "USDC"]
    assert cli_module.main(flags) == cli_module.EXIT_FAILURE
    assert "will not guess the split" in capsys.readouterr().err


def test_a_naive_timestamp_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flags = _record(tmp_path)
    flags[flags.index("2026-08-12T10:00:00+00:00")] = "2026-08-12T10:00:00"
    assert cli_module.main(flags) == cli_module.EXIT_FAILURE
    assert "timezone-aware" in capsys.readouterr().err


def test_a_price_that_is_not_a_number_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    flags = _record(tmp_path)
    flags[flags.index("60000")] = "sixty thousand"
    assert cli_module.main(flags) == cli_module.EXIT_FAILURE
    assert "not a decimal number" in capsys.readouterr().err


def test_closing_a_trade_that_is_not_stored_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_module.main(
        ["trade", "close", "trade_plan-x-20260812T100000Z-0123456789abcdef",
         "--price", "1", "--fee", "0", "--fx-rate", "1", "--fx-source", "x",
         "--reason", "stopped_out", "--store-root", str(tmp_path),
         "--reference-time", REFERENCE]
    ) == cli_module.EXIT_FAILURE
    assert "TradeNotFoundError" in capsys.readouterr().err


# --------------------------------------------------------------------------
# The command's own description.
# --------------------------------------------------------------------------


def test_the_command_help_states_that_nothing_is_executed() -> None:
    parser = cli_module.build_parser()
    trade = next(a for a in parser._actions if a.dest == "command").choices["trade"]
    assert "executes nothing" in (trade.description or "")


def test_the_registry_holds_the_trade_command_between_portfolio_and_archive() -> None:
    # Milestone BM inserted "portfolio" between "today" and "trade": the page
    # that values what is held sits beside the page that summarizes it, and
    # before the commands that change what is held. `trade` still immediately
    # precedes `archive`, which is the ordering this test was written to pin.
    names = [command.name for command in cli_module.COMMANDS]
    assert names[names.index("today") + 1] == "portfolio"
    assert names[names.index("portfolio") + 1] == "trade"
    assert names[names.index("trade") + 1] == "archive"
