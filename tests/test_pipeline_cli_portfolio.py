"""Milestone BM — the `fmits portfolio` CLI surface.

No test here re-derives a money figure; those have their own modules. This one
covers parsing, wiring to the real composition root, that the command reads the
store and never writes to it, exit codes, and that a store failure is reported
rather than traced.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from marks_helpers import klines_transport
from trade_domain_helpers import AT
from valuation_helpers import store_with, with_cash

from fmis.pipeline import cli as cli_module
from fmis.valuation import DEFAULT_BASE_CURRENCY, DEFAULT_PORTFOLIO_ID
from fmis.valuation import compose as compose_module

REFERENCE = "2026-08-12T20:00:00+00:00"


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No socket is opened by anything in this module.

    The provider's own transport injection point is patched at the one place
    this command reaches it, so the whole chain — argument construction, the
    closed-candle rule, the conversion into a mark — runs for real.
    """
    real = compose_module.fetch_price_snapshot

    def _stubbed(symbols, **kwargs):
        kwargs["transport"] = klines_transport(60000.0, 61000.0)
        kwargs["clock"] = lambda: AT(20)
        return real(symbols, **kwargs)

    monkeypatch.setattr(compose_module, "fetch_price_snapshot", _stubbed)


def _run(capsys, *argv: str) -> tuple[int, str]:
    code = cli_module.main(["portfolio", *argv])
    return code, capsys.readouterr().out


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def test_portfolio_is_registered_exactly_once() -> None:
    names = [command.name for command in cli_module.COMMANDS]
    assert names.count("portfolio") == 1


def test_portfolio_needs_no_arguments() -> None:
    args = cli_module.build_parser().parse_args(["portfolio"])
    assert args.store_root is None
    assert args.portfolio_id == DEFAULT_PORTFOLIO_ID
    assert args.base_currency == DEFAULT_BASE_CURRENCY
    assert args.no_marks is False


def test_portfolio_accepts_every_flag() -> None:
    args = cli_module.build_parser().parse_args(
        [
            "portfolio", "--store-root", "/tmp/store", "--portfolio-id", "swing_book",
            "--base-currency", "USDT", "--mark-interval", "4h", "--no-marks",
            "--reference-time", REFERENCE,
        ]
    )
    assert args.store_root == "/tmp/store"
    assert args.portfolio_id == "swing_book"
    assert args.mark_interval == "4h"
    assert args.no_marks is True


def test_portfolio_rejects_an_unknown_flag() -> None:
    with pytest.raises(SystemExit):
        cli_module.build_parser().parse_args(["portfolio", "--rebalance"])


def test_the_command_description_states_what_it_refuses_to_do() -> None:
    command = next(c for c in cli_module.COMMANDS if c.name == "portfolio")
    assert "never writes" in command.description
    assert "Nothing is stored" in command.description
    assert "no order is placed" in command.description
    assert "no position size is proposed" in command.description


def test_the_default_mark_interval_is_the_stated_policy() -> None:
    from fmis.pipeline.prices import MARK_INTERVAL

    args = cli_module.build_parser().parse_args(["portfolio"])
    assert args.mark_interval == MARK_INTERVAL


# --------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------


def test_a_populated_store_renders_a_full_page_and_exits_zero(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = tmp_path / "store"
    store_with(root, snapshots=(with_cash(),))
    code, out = _run(capsys, "--store-root", str(root), "--reference-time", REFERENCE)
    assert code == cli_module.EXIT_OK
    for heading in ("PORTFOLIO VALUATION", "VALUE", "EXPOSURE", "POSITIONS",
                    "PRICES", "LIMITATIONS"):
        assert heading in out, heading
    assert "30500 USDT" in out
    assert "33000 USDT" in out


def test_an_empty_store_still_renders_and_exits_zero(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """An owner who has recorded nothing gets a complete page saying so, not a
    failure."""
    code, out = _run(
        capsys, "--store-root", str(tmp_path / "nothing"),
        "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_OK
    assert "POSITIONS (0)" in out


def test_the_command_creates_nothing_under_the_store_root(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A read-only surface, checked against the filesystem rather than promised."""
    root = tmp_path / "store"
    store_with(root)
    before = sorted(path.name for path in root.rglob("*"))
    _run(capsys, "--store-root", str(root), "--reference-time", REFERENCE)
    assert sorted(path.name for path in root.rglob("*")) == before


def test_a_missing_store_root_is_never_created(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = tmp_path / "never-created"
    _run(capsys, "--store-root", str(root), "--reference-time", REFERENCE)
    assert not root.exists()


def test_no_marks_skips_the_price_source_and_says_so(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = tmp_path / "store"
    store_with(root)
    code, out = _run(
        capsys, "--store-root", str(root), "--no-marks",
        "--reference-time", REFERENCE,
    )
    assert code == cli_module.EXIT_OK
    assert "no price source was consulted" in out
    assert "unavailable" in out
    assert "POSITIONS (1)" in out


def test_a_corrupt_store_is_reported_rather_than_traced(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """The CLI may not import the store, so the failure has to arrive with a
    name this layer already knows."""
    root = tmp_path / "store"
    store_with(root)
    next(root.rglob("*.jsonl")).write_text("{ not json at all\n", encoding="utf-8")
    code = cli_module.main(
        ["portfolio", "--store-root", str(root), "--reference-time", REFERENCE]
    )
    captured = capsys.readouterr()
    assert code == cli_module.EXIT_FAILURE
    assert "PortfolioStoreError" in captured.err
    assert "Traceback" not in captured.err


def test_an_unknown_base_currency_is_reported_as_a_message(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code = cli_module.main(
        [
            "portfolio", "--store-root", str(tmp_path / "store"),
            "--base-currency", "not a code", "--reference-time", REFERENCE,
        ]
    )
    captured = capsys.readouterr()
    assert code == cli_module.EXIT_FAILURE
    assert "fmits:" in captured.out
    assert "asset code" in captured.out
    # A typo in a flag is not a broken store, and must not be reported as one.
    assert "PortfolioStoreError" not in captured.out
    assert "PortfolioStoreError" not in captured.err


def test_the_reference_time_makes_the_page_reproducible(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = tmp_path / "store"
    store_with(root)
    _, first = _run(capsys, "--store-root", str(root), "--reference-time", REFERENCE)
    _, second = _run(capsys, "--store-root", str(root), "--reference-time", REFERENCE)
    assert first == second


def test_the_page_prints_where_every_price_came_from(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = tmp_path / "store"
    store_with(root)
    _, out = _run(capsys, "--store-root", str(root), "--reference-time", REFERENCE)
    assert "binance-spot" in out
    assert "last_closed_candle_close" in out


def test_no_line_of_the_rendered_page_exceeds_the_page_width(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = tmp_path / "store"
    store_with(root, snapshots=(with_cash(),))
    _, out = _run(capsys, "--store-root", str(root), "--reference-time", REFERENCE)
    for line in out.splitlines():
        assert len(line) <= 78, line
