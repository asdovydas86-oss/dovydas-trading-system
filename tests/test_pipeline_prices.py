"""Milestone BM — the price snapshot service, the one place a venue is named.

Every test here runs through the real `fetch_klines` with an injected transport,
so the argument construction, the closed-candle derivation and the mapping into
`fmis.marks` are exercised end to end without a socket.

What this module owns and is therefore tested for: what to fetch, per-symbol
failure isolation, and that it computes nothing.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from marks_helpers import failing_transport, klines_transport
from trade_domain_helpers import AT

from fmis.marks import PriceSnapshot
from fmis.pipeline import prices as prices_module
from fmis.pipeline.prices import (
    MARK_CANDLE_LIMIT,
    MARK_INTERVAL,
    MARK_SOURCE,
    NO_SOURCE_CONSULTED,
    fetch_price_snapshot,
)

CLOCK = lambda: AT(20)  # noqa: E731 - a pinned instant, injected everywhere below


# --------------------------------------------------------------------------
# The stated policy
# --------------------------------------------------------------------------


def test_the_mark_interval_is_an_hour_and_is_a_named_policy() -> None:
    """Fine enough that a valuation is at most an hour behind the market, coarse
    enough that every market this system watches has a real closed hourly bar."""
    assert MARK_INTERVAL == "1h"


def test_two_candles_are_requested_not_one() -> None:
    """A one-candle window can be entirely the forming bar, which would make
    every symbol unpriceable at the top of an interval."""
    assert MARK_CANDLE_LIMIT == 2


def test_the_source_label_is_the_one_the_fact_sheets_already_use() -> None:
    """A fact sheet and a mark taken from the same endpoint must not claim two
    different sources."""
    from fmis.pipeline.structural_facts import BINANCE_SPOT

    assert MARK_SOURCE == BINANCE_SPOT


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------


def test_one_symbol_is_fetched_and_priced_from_its_last_closed_close() -> None:
    taken = fetch_price_snapshot(
        ("BTCUSDT",), taken_at=AT(20), transport=klines_transport(60000.0, 61000.0),
        clock=CLOCK,
    )
    assert isinstance(taken, PriceSnapshot)
    assert taken.reading_for("BTCUSDT").price == 61000.0
    assert taken.reading_for("BTCUSDT").source == MARK_SOURCE


def test_every_symbol_asked_for_appears_exactly_once() -> None:
    taken = fetch_price_snapshot(
        ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
        taken_at=AT(20), transport=klines_transport(1.0, 2.0), clock=CLOCK,
    )
    assert taken.requested_count == 3
    assert set(taken.priced_symbols) == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}


def test_a_duplicate_symbol_is_asked_for_once() -> None:
    """One market has one price; asking twice would build a snapshot the domain
    refuses to construct."""
    seen: list[str] = []

    def _counting(url: str):
        seen.append(url)
        return klines_transport(1.0, 2.0)(url)

    taken = fetch_price_snapshot(
        ("BTCUSDT", "BTCUSDT"), taken_at=AT(20), transport=_counting, clock=CLOCK
    )
    assert len(seen) == 1
    assert taken.requested_count == 1


def test_first_seen_order_is_preserved_rather_than_sorted() -> None:
    taken = fetch_price_snapshot(
        ("SOLUSDT", "BTCUSDT", "ETHUSDT"),
        taken_at=AT(20), transport=klines_transport(1.0, 2.0), clock=CLOCK,
    )
    assert taken.priced_symbols == ("SOLUSDT", "BTCUSDT", "ETHUSDT")


def test_no_symbols_costs_no_request_and_says_nothing_was_consulted() -> None:
    """An owner holding nothing needs no price, and that is a legitimate
    morning rather than a failure."""

    def _never(url: str):  # pragma: no cover - proving it is never reached
        raise AssertionError("a request was made for an empty symbol list")

    taken = fetch_price_snapshot((), taken_at=AT(20), transport=_never)
    assert taken.is_empty is True
    assert taken.source == NO_SOURCE_CONSULTED
    assert taken.unavailable == ()


def test_the_interval_and_limit_reach_the_provider_request() -> None:
    seen: list[str] = []

    def _capturing(url: str):
        seen.append(url)
        return klines_transport(1.0, 2.0)(url)

    fetch_price_snapshot(
        ("BTCUSDT",), taken_at=AT(20), interval="4h", limit=5,
        transport=_capturing, clock=CLOCK,
    )
    assert "interval=4h" in seen[0]
    assert "limit=5" in seen[0]


def test_an_explicit_base_url_is_forwarded() -> None:
    seen: list[str] = []

    def _capturing(url: str):
        seen.append(url)
        return klines_transport(1.0, 2.0)(url)

    fetch_price_snapshot(
        ("BTCUSDT",), taken_at=AT(20), transport=_capturing, clock=CLOCK,
        base_url="https://example.invalid",
    )
    assert seen[0].startswith("https://example.invalid")


def test_the_forming_candle_the_provider_returns_is_dropped() -> None:
    taken = fetch_price_snapshot(
        ("BTCUSDT",), taken_at=AT(20),
        transport=klines_transport(60000.0, 61000.0, forming=True), clock=CLOCK,
    )
    assert taken.reading_for("BTCUSDT").price == 60000.0
    assert taken.reading_for("BTCUSDT").closed_count == 1


# --------------------------------------------------------------------------
# Per-symbol failure isolation
# --------------------------------------------------------------------------


def test_a_transport_failure_becomes_a_reason_and_never_a_missing_row() -> None:
    taken = fetch_price_snapshot(
        ("BTCUSDT",), taken_at=AT(20), transport=failing_transport("connection reset"),
        clock=CLOCK,
    )
    assert taken.priced_symbols == ()
    assert "connection reset" in taken.reason_for("BTCUSDT")
    assert "BinanceTransportError" in taken.reason_for("BTCUSDT")


def test_one_symbols_outage_never_stops_the_others() -> None:
    def _selective(url: str):
        if "ETHUSDT" in url:
            return failing_transport("provider rejected the symbol")(url)
        return klines_transport(1.0, 2.0)(url)

    taken = fetch_price_snapshot(
        ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
        taken_at=AT(20), transport=_selective, clock=CLOCK,
    )
    assert set(taken.priced_symbols) == {"BTCUSDT", "SOLUSDT"}
    assert taken.unpriced_symbols == ("ETHUSDT",)


def test_a_provider_error_status_becomes_a_reason() -> None:
    taken = fetch_price_snapshot(
        ("BTCUSDT",), taken_at=AT(20),
        transport=klines_transport(1.0, status=418), clock=CLOCK,
    )
    assert "BinanceAPIError" in taken.reason_for("BTCUSDT")


def test_an_invalid_interval_is_reported_per_symbol_rather_than_raised() -> None:
    taken = fetch_price_snapshot(
        ("BTCUSDT",), taken_at=AT(20), interval="7h",
        transport=klines_transport(1.0), clock=CLOCK,
    )
    assert "BinanceRequestError" in taken.reason_for("BTCUSDT")


def test_a_defect_inside_fmits_propagates_rather_than_reading_as_an_outage() -> None:
    """A `KeyError` from inside FMITS rendered as *"this market could not be
    priced"* teaches the owner to ignore both."""

    def _broken(url: str):
        raise KeyError("an internal defect, not a provider failure")

    with pytest.raises(KeyError):
        fetch_price_snapshot(
            ("BTCUSDT",), taken_at=AT(20), transport=_broken, clock=CLOCK
        )


# --------------------------------------------------------------------------
# This module computes nothing
# --------------------------------------------------------------------------


def test_the_module_contains_no_arithmetic_of_its_own() -> None:
    """The same guarantee `fmis.pipeline.market_analysis` already holds: a number
    produced at the composition layer is a number no engine can be held to."""
    arithmetic = (
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
        ast.MatMult,
    )
    source = Path(inspect.getfile(prices_module)).read_text(encoding="utf-8")
    found = [
        ast.unparse(node)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.BinOp, ast.AugAssign))
        and isinstance(node.op, arithmetic)
        or (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, (ast.USub, ast.UAdd))
        )
    ]
    # `|` appears three times and every occurrence is a type union in a
    # signature (`Transport | None`), which is a type expression rather than a
    # calculation — hence the operator list above rather than a blanket ban.
    assert found == []


def test_the_module_names_no_price_of_its_own() -> None:
    """Every number in this file is a count or an argument, never a price."""
    source = Path(inspect.getfile(prices_module)).read_text(encoding="utf-8")
    floats = {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, float)
    }
    assert floats == set()


def test_the_module_reads_no_clock() -> None:
    """The clock is an injection point, forwarded to the provider and never
    called here — the CLI is the only place in this repository that takes the
    time."""
    source = Path(inspect.getfile(prices_module)).read_text(encoding="utf-8")
    for needle in ("datetime.now(", "datetime.utcnow(", "time.time("):
        assert needle not in source
