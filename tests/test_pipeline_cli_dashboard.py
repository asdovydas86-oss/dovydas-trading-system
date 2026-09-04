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


def test_the_command_warms_the_dashboard_before_announcing_its_url(monkeypatch) -> None:
    """**The repair, at the wiring level.** `serve` can warm; whether an
    operator's dashboard is not ready until it can answer is a decision this
    command makes, so it is this command that must pass ``warm=True``.

    The startup smoke test proves the behaviour end to end. This proves the one
    argument that produces it, in milliseconds, so a refactor that drops it is
    caught by the fast suite as well as the slow one.
    """
    from fmis.pipeline import cli

    captured: dict[str, object] = {}

    def fake_serve(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(cli, "serve_dashboard", fake_serve)
    args = build_parser().parse_args(["dashboard", "--port", "0"])
    assert _command().run(args) == 0

    assert captured["warm"] is True, "the dashboard is served without warming"
    assert callable(captured["preparing"]), (
        "no notice is printed before the warming refresh, so the operator waits "
        "on a silent terminal"
    )


def test_the_banner_offers_the_address_before_the_refresh_and_the_url_after(
    capsys, monkeypatch
) -> None:
    """The two notices carry different words on purpose: the operator is told
    the address is *coming*, then told it is *open*. Printing `open` first is
    the outage this pair replaced."""
    from fmis.pipeline import cli

    order: list[str] = []

    def fake_serve(*, preparing, announce, **_kwargs) -> None:
        preparing("http://127.0.0.1:8787/")
        order.append("prepared")
        announce("http://127.0.0.1:8787/", object())
        order.append("announced")

    monkeypatch.setattr(cli, "serve_dashboard", fake_serve)
    args = build_parser().parse_args(["dashboard", "--port", "0"])
    assert _command().run(args) == 0

    assert order == ["prepared", "announced"]
    out = capsys.readouterr().out
    assert out.index("address") < out.index("open"), (
        "the URL is offered as open before the refresh behind it is announced"
    )
    assert "30-45 s" in out, "the wait is not explained to the operator"
