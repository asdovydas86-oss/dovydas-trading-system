"""Milestone BT — the composition root: failure isolation, and what still raises.

The contract has two halves and both must hold. **A provider failure on one
market becomes a row and never costs the page** — one, several, or all of them.
And **a programming defect still propagates**: a `KeyError` from inside FMITS
rendered as *"this market could not be read"* teaches the owner to ignore both,
so only the named operational families are caught.

Every test here is network-free: the adapter's own `transport` seam is injected,
which is the same seam `fmis.pipeline.prices` and `fmis.pipeline.candles` use.
"""

from __future__ import annotations

import json

import pytest

from fmis.market_pulse import (
    DEFAULT_HORIZONS,
    DEFAULT_PULSE_UNIVERSE,
    HORIZON_LATEST_BAR,
    Horizon,
    render_market_pulse,
)
from fmis.pipeline.pulse import PULSE_SOURCE, run_market_pulse
from fmis.providers.binance import HttpResponse
from tests.market_pulse_helpers import (
    crypto_benchmark,
    dark_benchmark,
    error_response,
    instant,
    linear_klines,
    ok_response,
    transport_for,
    universe_of,
)

ONE = HORIZON_LATEST_BAR
THREE = Horizon(horizon_id="h3", bars=3, description="three bars")
FIVE = Horizon(horizon_id="h5", bars=5, description="five bars")

AS_OF = instant(500)


def run(universe, transport, **extra):
    defaults = dict(
        as_of=AS_OF,
        universe=universe,
        horizons=(ONE, THREE),
        volatility_horizon=FIVE,
        co_movement_horizon=FIVE,
        limit=50,
        transport=transport,
        clock=lambda: AS_OF,
    )
    defaults.update(extra)
    return run_market_pulse(**defaults)


def two_market_universe():
    return universe_of(
        crypto_benchmark("BTC", symbol="BTCUSDT"),
        crypto_benchmark("ETH", symbol="ETHUSDT"),
    )


def rising(count: int = 40, base: float = 100.0, step: float = 1.0):
    return ok_response(linear_klines(base, step, count))


# --------------------------------------------------------------------------
# The happy path, and what it proves about cost
# --------------------------------------------------------------------------


def test_every_supported_market_is_read_and_the_page_assembles() -> None:
    send = transport_for({"BTCUSDT": rising(), "ETHUSDT": rising(step=-0.5)})
    page = run(two_market_universe(), send)
    assert page.read_count == 2
    assert page.unavailable == ()
    assert [reading.benchmark_id for reading in page.readings] == ["BTC", "ETH"]


def test_each_market_is_fetched_exactly_once() -> None:
    """*The page costs exactly one request per market.* The co-movement step
    reuses the series it already reduced rather than fetching again."""
    send = transport_for({"BTCUSDT": rising(), "ETHUSDT": rising(step=-0.5)})
    run(two_market_universe(), send)
    assert send.calls == ["BTCUSDT", "ETHUSDT"]


def test_an_unsupported_market_is_never_fetched() -> None:
    """*Fetching a market that has no adapter and calling the resulting error a
    provider failure would erase the distinction the whole surface is built
    on.*"""
    send = transport_for({"BTCUSDT": rising()})
    page = run(
        universe_of(crypto_benchmark("BTC", symbol="BTCUSDT"), dark_benchmark("DXY")),
        send,
    )
    assert send.calls == ["BTCUSDT"]
    assert page.unavailable == ()
    assert page.unsupported_count == 1


def test_the_source_label_travels_onto_every_reading() -> None:
    send = transport_for({"BTCUSDT": rising()})
    page = run(universe_of(crypto_benchmark("BTC", symbol="BTCUSDT")), send)
    assert page.readings[0].source == PULSE_SOURCE


def test_the_page_is_measured_against_the_supplied_instant_not_a_clock() -> None:
    """The composition root reads no clock; `as_of` decides the window."""
    send = transport_for({"BTCUSDT": ok_response(linear_klines(100.0, 1.0, 40))})
    early = run(universe_of(crypto_benchmark("BTC", symbol="BTCUSDT")), send,
                as_of=instant(10))
    late = run(universe_of(crypto_benchmark("BTC", symbol="BTCUSDT")), send,
               as_of=instant(30))
    assert early.readings[0].last_bar_open == instant(10)
    assert late.readings[0].last_bar_open == instant(30)


# --------------------------------------------------------------------------
# Failure isolation
# --------------------------------------------------------------------------


def test_one_failing_market_does_not_cost_the_others() -> None:
    send = transport_for({"BTCUSDT": rising(), "ETHUSDT": error_response()})
    page = run(two_market_universe(), send)
    assert [reading.benchmark_id for reading in page.readings] == ["BTC"]
    assert [entry.benchmark_id for entry in page.unavailable] == ["ETH"]
    assert "Invalid symbol" in page.unavailable[0].reason


def test_a_failure_between_two_successes_is_isolated() -> None:
    """The ordering case: a failure in the middle must not truncate the rest."""
    universe = universe_of(
        crypto_benchmark("A", symbol="AUSDT"),
        crypto_benchmark("B", symbol="BUSDT"),
        crypto_benchmark("C", symbol="CUSDT"),
    )
    send = transport_for(
        {"AUSDT": rising(), "BUSDT": error_response(), "CUSDT": rising(step=2.0)}
    )
    page = run(universe, send)
    assert [reading.benchmark_id for reading in page.readings] == ["A", "C"]
    assert [entry.benchmark_id for entry in page.unavailable] == ["B"]


def test_every_market_failing_still_produces_a_page() -> None:
    send = transport_for({"BTCUSDT": error_response(), "ETHUSDT": error_response()})
    page = run(two_market_universe(), send)
    assert page.is_empty
    assert len(page.unavailable) == 2
    assert render_market_pulse(page)  # and it renders


def test_an_empty_provider_response_is_a_reason_and_not_a_move_of_zero() -> None:
    send = transport_for({"BTCUSDT": ok_response([])})
    page = run(universe_of(crypto_benchmark("BTC", symbol="BTCUSDT")), send)
    assert page.is_empty
    assert "NoObservationsError" in page.unavailable[0].reason
    assert "rather than a move of zero" in page.unavailable[0].reason


def test_a_single_observation_is_a_reason_rather_than_a_measured_zero() -> None:
    """One closed bar cannot produce a move; the reading exists and says so."""
    send = transport_for({"BTCUSDT": ok_response(linear_klines(100.0, 1.0, 1))})
    page = run(universe_of(crypto_benchmark("BTC", symbol="BTCUSDT")), send)
    reading = page.readings[0]
    assert reading.closed_bar_count == 1
    assert all(not move.is_measured for move in reading.moves)
    assert not reading.volatility.is_measured


def test_a_transport_error_becomes_a_row_carrying_the_provider_s_words() -> None:
    from fmis.providers.binance import BinanceTransportError

    def send(url: str):
        raise BinanceTransportError("connection timed out after 10.0s")

    page = run(universe_of(crypto_benchmark("BTC", symbol="BTCUSDT")), send)
    assert "BinanceTransportError" in page.unavailable[0].reason
    assert "connection timed out" in page.unavailable[0].reason


def test_a_malformed_response_becomes_a_row_rather_than_a_traceback() -> None:
    send = transport_for(
        {"BTCUSDT": HttpResponse(status=200, body=b"not json at all")}
    )
    page = run(universe_of(crypto_benchmark("BTC", symbol="BTCUSDT")), send)
    assert "BinanceResponseError" in page.unavailable[0].reason


def test_a_negative_price_is_refused_by_the_canonical_boundary() -> None:
    """The ingestion boundary rejects it; the row carries the refusal."""
    rows = linear_klines(100.0, 1.0, 5)
    rows[2][4] = "-5.0"
    send = transport_for({"BTCUSDT": ok_response(rows)})
    page = run(universe_of(crypto_benchmark("BTC", symbol="BTCUSDT")), send)
    assert page.is_empty
    assert page.unavailable[0].reason


def test_a_failed_market_is_absent_from_every_ordering_but_reported_in_each() -> None:
    send = transport_for({"BTCUSDT": rising(), "ETHUSDT": error_response()})
    page = run(two_market_universe(), send)
    for ranking in page.rankings:
        assert "ETH" not in {row.benchmark_id for row in ranking.ordered}
        assert "ETH" in dict(ranking.excluded)


def test_a_failed_market_gets_no_co_movement_row() -> None:
    """*A second absence for it would be the same fact twice.*"""
    send = transport_for({"BTCUSDT": rising(), "ETHUSDT": error_response()})
    page = run(two_market_universe(), send)
    assert [item.subject_id for item in page.co_movements] == []


# --------------------------------------------------------------------------
# A programming defect must still raise
# --------------------------------------------------------------------------


def test_a_programming_defect_inside_the_transport_propagates() -> None:
    """*A KeyError rendered as "this market could not be read" teaches the
    owner to ignore both.*"""

    def send(url: str):
        raise KeyError("an internal defect, not a market condition")

    with pytest.raises(KeyError):
        run(universe_of(crypto_benchmark("BTC", symbol="BTCUSDT")), send)


def test_an_attribute_error_inside_the_transport_propagates() -> None:
    def send(url: str):
        raise AttributeError("NoneType has no attribute 'body'")

    with pytest.raises(AttributeError):
        run(universe_of(crypto_benchmark("BTC", symbol="BTCUSDT")), send)


def test_a_runtime_error_inside_the_transport_propagates() -> None:
    def send(url: str):
        raise RuntimeError("a defect")

    with pytest.raises(RuntimeError):
        run(universe_of(crypto_benchmark("BTC", symbol="BTCUSDT")), send)


# --------------------------------------------------------------------------
# Co-movement wiring
# --------------------------------------------------------------------------


def test_omitting_the_co_movement_horizon_omits_the_section() -> None:
    """*None omits the section entirely rather than filling it with absences.*"""
    send = transport_for({"BTCUSDT": rising(), "ETHUSDT": rising(step=-0.5)})
    page = run(two_market_universe(), send, co_movement_horizon=None)
    assert page.co_movements == ()
    assert page.co_movement_reference is None


def test_the_reference_is_the_first_market_that_was_actually_read() -> None:
    """Not the first configured — a failed first market must not become the
    reference every correlation is measured against."""
    universe = universe_of(
        crypto_benchmark("BTC", symbol="BTCUSDT"),
        crypto_benchmark("ETH", symbol="ETHUSDT"),
        crypto_benchmark("SOL", symbol="SOLUSDT"),
    )
    send = transport_for(
        {
            "BTCUSDT": error_response(),
            "ETHUSDT": rising(),
            "SOLUSDT": rising(step=3.0),
        }
    )
    page = run(universe, send)
    assert page.co_movement_reference == "ETH"
    assert [item.subject_id for item in page.co_movements] == ["SOL"]


def test_the_co_movement_window_matches_the_one_the_page_names() -> None:
    send = transport_for({"BTCUSDT": rising(), "ETHUSDT": rising(step=-0.5)})
    page = run(two_market_universe(), send)
    movement = page.co_movements[0]
    assert movement.observation_count == FIVE.required_observations


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_two_runs_over_one_snapshot_produce_byte_identical_pages() -> None:
    """The property that makes the page diffable and defensible."""
    snapshot = {"BTCUSDT": rising(), "ETHUSDT": rising(step=-0.5)}
    first = render_market_pulse(run(two_market_universe(), transport_for(snapshot)))
    second = render_market_pulse(run(two_market_universe(), transport_for(snapshot)))
    assert first == second


def test_the_default_universe_runs_end_to_end_against_a_fake_provider() -> None:
    """The shipped configuration, exercised in full without a network."""
    responses = {
        benchmark.instrument.symbol: rising(count=200, step=float(index + 1))
        for index, benchmark in enumerate(DEFAULT_PULSE_UNIVERSE.supported)
    }
    page = run_market_pulse(
        as_of=instant(500),
        universe=DEFAULT_PULSE_UNIVERSE,
        transport=transport_for(responses),
        clock=lambda: instant(500),
    )
    assert page.read_count == 6
    assert page.unsupported_count == 5
    assert len(page.rankings) == len(DEFAULT_HORIZONS)
    text = render_market_pulse(page)
    for benchmark in DEFAULT_PULSE_UNIVERSE.benchmarks:
        assert benchmark.benchmark_id in text


def test_the_composition_root_writes_nothing_to_the_filesystem(tmp_path) -> None:
    """A pulse is a projection; it has no store and no cache."""
    import os

    before = sorted(os.listdir(tmp_path))
    send = transport_for({"BTCUSDT": rising()})
    run(universe_of(crypto_benchmark("BTC", symbol="BTCUSDT")), send)
    assert sorted(os.listdir(tmp_path)) == before


def test_no_credential_appears_in_any_requested_url() -> None:
    """The adapter signs nothing and reads no key; asserted on the real URLs."""
    send = transport_for({"BTCUSDT": rising()})
    captured: list[str] = []

    def recording(url: str):
        captured.append(url)
        return send(url)

    run(universe_of(crypto_benchmark("BTC", symbol="BTCUSDT")), recording)
    joined = " ".join(captured).lower()
    for token in ("apikey", "api_key", "signature", "secret", "token"):
        assert token not in joined
