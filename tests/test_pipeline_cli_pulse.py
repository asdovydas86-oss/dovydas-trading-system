"""Milestone BT — `fmits pulse` at the surface.

The command's contract: the **default with no arguments is the useful one**, one
unavailable market never costs the page, a bad argument is a clean message
rather than a traceback, and the exit code says whether anything could be read.
"""

from __future__ import annotations

import pytest

from fmis.pipeline import cli
from tests.market_pulse_helpers import (
    error_response,
    instant,
    linear_klines,
    ok_response,
    transport_for,
)

AS_OF = instant(500).isoformat()


@pytest.fixture
def fake_provider(monkeypatch):
    """Every default market answers, so the command needs no network.

    Patched at the adapter's transport seam rather than at the composition root,
    so the command exercises the real fetch path, the real decoder and the real
    canonical boundary.
    """
    from fmis.market_pulse import DEFAULT_PULSE_UNIVERSE

    responses = {
        benchmark.instrument.symbol: ok_response(
            linear_klines(100.0, float(index + 1), 200)
        )
        for index, benchmark in enumerate(DEFAULT_PULSE_UNIVERSE.supported)
    }
    state = {"responses": responses, "calls": []}

    def send(url: str):
        symbol = url.split("symbol=")[1].split("&")[0]
        state["calls"].append(symbol)
        return state["responses"][symbol]

    real = cli.run_market_pulse

    def patched(**kwargs):
        kwargs.setdefault("transport", send)
        kwargs.setdefault("clock", lambda: instant(500))
        return real(**kwargs)

    monkeypatch.setattr(cli, "run_market_pulse", patched)
    return state


def run(argv, capsys):
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------


def test_the_command_is_registered_with_a_runner() -> None:
    command = next(entry for entry in cli.COMMANDS if entry.name == "pulse")
    assert callable(command.run) and callable(command.configure)


def test_the_command_parses_with_no_arguments_at_all() -> None:
    """*The default command must be useful with no arguments.*"""
    args = cli.build_parser().parse_args(["pulse"])
    assert args.benchmarks == []
    assert args.as_of is None
    assert args.max_age is None


def test_the_help_names_no_directional_or_advisory_vocabulary() -> None:
    command = next(entry for entry in cli.COMMANDS if entry.name == "pulse")
    text = f"{command.help} {command.description}".lower()
    for token in ("buy", "sell", "bullish", "bearish", "recommend", "advice"):
        assert token not in text, token


# --------------------------------------------------------------------------
# The default run
# --------------------------------------------------------------------------


def test_the_default_run_prints_the_page_and_exits_zero(fake_provider, capsys) -> None:
    code, out, err = run(["pulse", "--as-of", AS_OF], capsys)
    assert code == cli.EXIT_OK
    assert "GLOBAL MARKET PULSE" in out
    assert err == ""


def test_the_default_run_covers_the_whole_configured_universe(
    fake_provider, capsys
) -> None:
    from fmis.market_pulse import DEFAULT_PULSE_UNIVERSE

    _, out, _ = run(["pulse", "--as-of", AS_OF], capsys)
    for benchmark in DEFAULT_PULSE_UNIVERSE.benchmarks:
        assert benchmark.benchmark_id in out


def test_the_default_run_reports_the_markets_it_cannot_read(
    fake_provider, capsys
) -> None:
    _, out, _ = run(["pulse", "--as-of", AS_OF], capsys)
    assert "no provider is configured" in " ".join(out.split())
    assert "DXY" in out


def test_the_page_holds_no_line_beyond_the_repository_width(
    fake_provider, capsys
) -> None:
    from fmis.market_pulse import PULSE_PAGE_WIDTH

    _, out, _ = run(["pulse", "--as-of", AS_OF], capsys)
    for line in out.splitlines():
        assert len(line) <= PULSE_PAGE_WIDTH, (len(line), line)


# --------------------------------------------------------------------------
# Selecting markets
# --------------------------------------------------------------------------


def test_named_markets_narrow_the_page_and_keep_the_typed_order(
    fake_provider, capsys
) -> None:
    _, out, _ = run(["pulse", "ETH", "BTC", "--as-of", AS_OF], capsys)
    assert out.index("[ETH]") < out.index("[BTC]")
    assert "[SOL]" not in out


def test_naming_only_an_unreadable_market_still_produces_a_page(
    fake_provider, capsys
) -> None:
    code, out, _ = run(["pulse", "DXY", "--as-of", AS_OF], capsys)
    assert "GLOBAL MARKET PULSE" in out
    assert "no provider is configured" in " ".join(out.split())
    assert code == cli.EXIT_FAILURE  # nothing was read


def test_an_unknown_market_is_a_clean_message_and_not_a_traceback(
    fake_provider, capsys
) -> None:
    code, out, err = run(["pulse", "NOPE", "--as-of", AS_OF], capsys)
    assert code == cli.EXIT_FAILURE
    assert "PulseUniverseError" in err
    assert "not a market in universe" in err
    assert out == ""


def test_a_market_named_twice_is_a_clean_message(fake_provider, capsys) -> None:
    """The `fmits workspace BTCUSDT BTCUSDT` defect BS found, not repeated: the
    duplicate is refused with its own sentence rather than losing the page."""
    code, out, err = run(["pulse", "BTC", "BTC", "--as-of", AS_OF], capsys)
    assert code == cli.EXIT_FAILURE
    assert "named twice" in err
    assert "Traceback" not in err


# --------------------------------------------------------------------------
# Failure isolation at the surface
# --------------------------------------------------------------------------


def test_one_unavailable_market_does_not_destroy_the_page(
    fake_provider, capsys
) -> None:
    fake_provider["responses"]["ETHUSDT"] = error_response()
    code, out, _ = run(["pulse", "--as-of", AS_OF], capsys)
    assert code == cli.EXIT_OK
    assert "asked for and not delivered" in " ".join(out.split())
    assert "[BTC]" in out


def test_every_market_failing_still_prints_a_page_and_exits_non_zero(
    fake_provider, capsys
) -> None:
    for symbol in list(fake_provider["responses"]):
        fake_provider["responses"][symbol] = error_response()
    code, out, _ = run(["pulse", "--as-of", AS_OF], capsys)
    assert code == cli.EXIT_FAILURE
    assert "No market could be read" in " ".join(out.split())


# --------------------------------------------------------------------------
# Flags
# --------------------------------------------------------------------------


def test_without_a_bound_nothing_is_called_stale(fake_provider, capsys) -> None:
    _, out, _ = run(["pulse", "--as-of", AS_OF], capsys)
    assert "No staleness bound is configured" in " ".join(out.split())


def test_a_bound_marks_the_readings_that_exceed_it(fake_provider, capsys) -> None:
    _, out, _ = run(["pulse", "--as-of", AS_OF, "--max-age", "0.25"], capsys)
    assert "staleness bound" in out
    assert "stale ·" in out


def test_a_generous_bound_marks_nothing(fake_provider, capsys) -> None:
    # The fixture's last bar opens at hour 199 and `--as-of` is hour 500, so
    # the readings are 301 hours old; the bound has to clear that.
    _, out, _ = run(["pulse", "--as-of", AS_OF, "--max-age", "400"], capsys)
    assert "no reading exceeds it" in " ".join(out.split())
    assert "stale ·" not in out


@pytest.mark.parametrize("bound", ["0", "-1"])
def test_a_non_positive_bound_is_refused_with_a_message(
    fake_provider, capsys, bound: str
) -> None:
    code, out, err = run(["pulse", "--as-of", AS_OF, "--max-age", bound], capsys)
    assert code == cli.EXIT_FAILURE
    assert "must be positive" in err
    assert out == ""


def test_a_naive_as_of_is_refused(fake_provider, capsys) -> None:
    code, out, _ = run(["pulse", "--as-of", "2026-08-01T00:00:00"], capsys)
    assert code == cli.EXIT_FAILURE
    assert "timezone-aware" in out


def test_a_malformed_as_of_is_refused(fake_provider, capsys) -> None:
    code, out, _ = run(["pulse", "--as-of", "not-a-date"], capsys)
    assert code == cli.EXIT_FAILURE


def test_the_as_of_makes_the_page_reproducible(fake_provider, capsys) -> None:
    _, first, _ = run(["pulse", "--as-of", AS_OF], capsys)
    _, second, _ = run(["pulse", "--as-of", AS_OF], capsys)
    assert first == second


# --------------------------------------------------------------------------
# The page's own prohibitions, at the surface
# --------------------------------------------------------------------------


def test_the_printed_page_names_no_direction_and_no_market_view(
    fake_provider, capsys
) -> None:
    _, out, _ = run(["pulse", "--as-of", AS_OF], capsys)
    text = " ".join(out.split()).lower()
    for token in (
        "buy", "sell", "long", "short", "bullish", "bearish",
        "risk-on", "risk-off", "risk on", "risk off",
    ):
        assert token not in text, token


def test_the_printed_page_states_that_it_is_orientation(
    fake_provider, capsys
) -> None:
    _, out, _ = run(["pulse", "--as-of", AS_OF], capsys)
    assert "orientation, not a recommendation" in " ".join(out.split())


def test_no_credential_or_secret_appears_in_the_output(
    fake_provider, capsys
) -> None:
    _, out, err = run(["pulse", "--as-of", AS_OF], capsys)
    joined = f"{out} {err}".lower()
    for token in ("api_key", "apikey", "secret", "signature", "password"):
        assert token not in joined
