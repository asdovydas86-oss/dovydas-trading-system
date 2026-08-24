"""`fmits dashboard` — the CLI wiring, without ever serving forever.

The command binds a socket and blocks, so every test here builds the server
through the same path the runner does and closes it, rather than calling the
runner itself.
"""

from __future__ import annotations

import pytest

from fmis.pipeline.cli import COMMANDS, build_parser


def _command():
    return next(command for command in COMMANDS if command.name == "dashboard")


def test_the_command_is_registered_once() -> None:
    names = [command.name for command in COMMANDS]
    assert names.count("dashboard") == 1


def test_the_parser_accepts_the_bare_command() -> None:
    """`fmits dashboard` with no argument is the command the owner runs."""
    args = build_parser().parse_args(["dashboard"])
    assert args.command == "dashboard"
    assert args.symbols == []
    assert args.host == "127.0.0.1"
    assert args.port == 8787
    assert args.allow_public is False


def test_the_parser_accepts_a_watchlist_and_the_flags() -> None:
    args = build_parser().parse_args(
        [
            "dashboard",
            "BTCUSDT",
            "ETHUSDT",
            "--port",
            "9999",
            "--store-root",
            "/tmp/store",
            "--no-relationships",
        ]
    )
    assert args.symbols == ["BTCUSDT", "ETHUSDT"]
    assert args.port == 9999
    assert args.store_root == "/tmp/store"
    assert args.no_relationships is True


def test_the_description_states_the_read_only_boundary() -> None:
    """The owner reads this before running it."""
    description = _command().description
    assert "read-only" in description
    assert "never writes" in description
    assert "GET and HEAD only" in description
    assert "loopback" in description


def test_binding_off_loopback_without_the_flag_exits_non_zero(capsys) -> None:
    """The refusal reaches the owner as a message and an exit code, not a
    traceback."""
    parser = build_parser()
    args = parser.parse_args(["dashboard", "--host", "0.0.0.0", "--port", "0"])
    assert _command().run(args) == 1
    assert "refusing to bind" in capsys.readouterr().err


def test_the_runner_reports_a_port_it_cannot_bind_rather_than_crashing(capsys) -> None:
    from fmis.operator_dashboard import build_server

    taken, _ = build_server(port=0, quiet=True)
    port = taken.server_address[1]
    try:
        args = build_parser().parse_args(["dashboard", "--port", str(port)])
        assert _command().run(args) == 1
        assert "fmits dashboard:" in capsys.readouterr().err
    finally:
        taken.server_close()


def test_the_holder_the_command_builds_forwards_its_arguments() -> None:
    from fmis.operator_dashboard import SnapshotHolder

    holder = SnapshotHolder(
        symbols=("BTCUSDT",), store_root="/tmp/store", with_relationships=False
    )
    assert holder._symbols == ("BTCUSDT",)
    assert holder._store_root == "/tmp/store"
    assert holder._with_relationships is False


def test_the_command_appears_in_the_top_level_help() -> None:
    help_text = build_parser().format_help()
    assert "dashboard" in help_text
