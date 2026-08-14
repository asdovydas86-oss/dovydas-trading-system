"""Milestone BM — reading a price from candles, and only from closed ones.

The whole of the mark-selection policy lives in `fmis.marks.service`, so this is
where it is pinned: the forming bar is unreadable, the last closed close is the
price, an unreadable market is a reason rather than a failure of the run, and a
price from after the instant being described is refused with both dates named.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from marks_helpers import SOURCE, candle, series
from trade_domain_helpers import AT

from fmis.data import CandleSeries
from fmis.marks import (
    MARK_BASIS_NOTE,
    PriceBasis,
    PriceSnapshot,
    PriceUnreadableError,
    build_price_snapshot,
    empty_price_snapshot,
    read_price,
)

# --------------------------------------------------------------------------
# read_price
# --------------------------------------------------------------------------


def test_the_price_is_the_last_closed_candles_close() -> None:
    assert read_price(series(1.0, 2.0, 3.0), source=SOURCE).price == 3.0


def test_the_forming_candle_is_never_read() -> None:
    """Unconditionally, not by default: there is no flag that includes it.

    A snapshot computed over a forming bar is not reproducible, and a mark is
    the input to a money figure — so the consequence is a portfolio whose value
    changes when nothing traded.
    """
    reading = read_price(series(1.0, 2.0, forming=99.0), source=SOURCE)
    assert reading.price == 2.0
    assert reading.closed_count == 2


def test_the_reading_is_timestamped_with_the_bar_that_produced_it() -> None:
    assert read_price(series(1.0, 2.0, first_hour=8), source=SOURCE).observed_at == AT(9)


def test_a_window_of_only_forming_candles_has_no_price() -> None:
    only_forming = CandleSeries(
        "BTCUSDT", "1h", (candle(9, 1.0, is_closed=False),)
    )
    with pytest.raises(PriceUnreadableError, match="no closed candle"):
        read_price(only_forming, source=SOURCE)


def test_an_empty_series_has_no_price_rather_than_a_price_of_zero() -> None:
    with pytest.raises(PriceUnreadableError, match="rather than a price of zero"):
        read_price(CandleSeries("BTCUSDT", "1h", ()), source=SOURCE)


def test_the_symbol_and_interval_come_from_the_candle_not_the_caller() -> None:
    """So a reading can never claim a market the candles did not describe."""
    reading = read_price(series(1.0, symbol="ETHUSDT", interval="4h"), source=SOURCE)
    assert (reading.symbol, reading.interval) == ("ETHUSDT", "4h")


def test_read_price_refuses_something_that_is_not_a_series() -> None:
    with pytest.raises(TypeError, match="CandleSeries"):
        read_price([1.0, 2.0], source=SOURCE)


def test_read_price_refuses_a_basis_that_is_not_a_member() -> None:
    with pytest.raises(TypeError, match="PriceBasis"):
        read_price(series(1.0), source=SOURCE, basis="closed")


def test_the_basis_defaults_to_the_only_one_that_exists() -> None:
    assert read_price(series(1.0), source=SOURCE).basis is (
        PriceBasis.LAST_CLOSED_CANDLE_CLOSE
    )
    assert read_price(
        series(1.0), source=SOURCE, basis=PriceBasis.LAST_CLOSED_CANDLE_CLOSE
    ).basis is PriceBasis.LAST_CLOSED_CANDLE_CLOSE


def test_reading_the_same_history_twice_gives_the_same_price_forever() -> None:
    """Determinism, asserted rather than described."""
    history = series(1.0, 2.0, 3.0, forming=4.0)
    assert read_price(history, source=SOURCE) == read_price(history, source=SOURCE)


# --------------------------------------------------------------------------
# build_price_snapshot
# --------------------------------------------------------------------------


def test_many_series_become_one_snapshot() -> None:
    taken = build_price_snapshot(
        (series(1.0, 2.0), series(3.0, 4.0, symbol="ETHUSDT")),
        taken_at=AT(12),
        source=SOURCE,
    )
    assert taken.priced_symbols == ("BTCUSDT", "ETHUSDT")
    assert taken.reading_for("ETHUSDT").price == 4.0


def test_one_unreadable_market_never_costs_the_others_their_prices() -> None:
    taken = build_price_snapshot(
        (
            series(1.0, 2.0),
            CandleSeries("ETHUSDT", "1h", (candle(9, 5.0, symbol="ETHUSDT",
                                                  is_closed=False),)),
        ),
        taken_at=AT(12),
        source=SOURCE,
    )
    assert taken.priced_symbols == ("BTCUSDT",)
    assert "no closed candle" in taken.reason_for("ETHUSDT")


def test_the_callers_own_fetch_failures_are_carried_verbatim() -> None:
    taken = build_price_snapshot(
        (series(1.0),),
        taken_at=AT(12),
        source=SOURCE,
        unreadable={"ETHUSDT": "provider rejected the symbol"},
    )
    assert taken.reason_for("ETHUSDT") == "provider rejected the symbol"


def test_a_price_from_after_the_instant_described_is_refused_with_both_dates() -> None:
    """Asking what the portfolio was worth on Tuesday fetches candles that have
    closed since. A mark from the future of the moment it marks is not that
    moment's price, and this build stores no price history to read one from.
    """
    taken = build_price_snapshot(
        (series(1.0, 2.0, first_hour=18),), taken_at=AT(12), source=SOURCE
    )
    reason = taken.reason_for("BTCUSDT")
    assert taken.priced_symbols == ()
    assert "after the instant this snapshot describes" in reason
    assert AT(19).isoformat() in reason
    assert AT(12).isoformat() in reason


def test_a_future_price_on_one_market_leaves_the_others_priced() -> None:
    taken = build_price_snapshot(
        (series(1.0, 2.0), series(3.0, 4.0, symbol="ETHUSDT", first_hour=18)),
        taken_at=AT(12),
        source=SOURCE,
    )
    assert taken.priced_symbols == ("BTCUSDT",)
    assert taken.unpriced_symbols == ("ETHUSDT",)


def test_a_reading_exactly_at_the_snapshot_instant_is_kept() -> None:
    """The boundary is `after`, not `at`: a bar that opened at the very instant
    being described is a legitimate price for it."""
    taken = build_price_snapshot(
        (series(1.0, 2.0, first_hour=11),), taken_at=AT(12), source=SOURCE
    )
    assert taken.priced_symbols == ("BTCUSDT",)


def test_no_series_at_all_produces_an_empty_but_valid_snapshot() -> None:
    taken = build_price_snapshot((), taken_at=AT(12), source=SOURCE)
    assert taken.is_empty is True
    assert taken.requested_count == 0


def test_the_snapshot_instant_must_be_a_utc_datetime() -> None:
    with pytest.raises(TypeError, match="must be a datetime"):
        build_price_snapshot((), taken_at="2026-08-12T12:00:00+00:00", source=SOURCE)


def test_the_snapshot_carries_the_source_onto_every_reading() -> None:
    taken = build_price_snapshot(
        (series(1.0), series(2.0, symbol="ETHUSDT")),
        taken_at=AT(12), source="a-different-source",
    )
    assert taken.source == "a-different-source"
    assert {r.source for r in taken.readings} == {"a-different-source"}


def test_building_the_same_snapshot_twice_gives_an_equal_snapshot() -> None:
    inputs = (series(1.0, 2.0), series(3.0, symbol="ETHUSDT"))
    first = build_price_snapshot(inputs, taken_at=AT(12), source=SOURCE)
    second = build_price_snapshot(inputs, taken_at=AT(12), source=SOURCE)
    assert first == second


# --------------------------------------------------------------------------
# empty_price_snapshot
# --------------------------------------------------------------------------


def test_asking_for_nothing_is_distinct_from_every_fetch_failing() -> None:
    """A page that could not tell them apart would report an outage when the
    owner had simply asked not to look."""
    skipped = empty_price_snapshot(
        taken_at=AT(12), source="no price source was consulted"
    )
    failed = build_price_snapshot(
        (), taken_at=AT(12), source=SOURCE,
        unreadable={"BTCUSDT": "provider timed out"},
    )
    assert skipped.is_empty and failed.is_empty
    assert skipped.unavailable == ()
    assert failed.unavailable != ()
    assert skipped.requested_count == 0
    assert failed.requested_count == 1


def test_an_empty_snapshot_is_a_real_snapshot() -> None:
    skipped = empty_price_snapshot(taken_at=AT(12), source="nothing was needed")
    assert isinstance(skipped, PriceSnapshot)
    assert PriceSnapshot.from_payload(skipped.to_payload()) == skipped


# --------------------------------------------------------------------------
# The note every surface prints
# --------------------------------------------------------------------------


def test_the_basis_note_states_the_rule_and_the_direction_of_the_error() -> None:
    """Staleness is overstated, never understated — the safe direction, and the
    reason the interval travels beside every reading."""
    assert "last closed candle" in MARK_BASIS_NOTE
    assert "forming bar is never read" in MARK_BASIS_NOTE
    assert "overstated" in MARK_BASIS_NOTE
    assert "never understated" in MARK_BASIS_NOTE


def test_a_marks_age_is_never_understated_by_the_chosen_timestamp() -> None:
    """The bar's open is used, so the reported age is at least the true age.

    A 1h bar that opened at 11:00 closed at 12:00; the price was true at 12:00
    and this reports it as true at 11:00. Measured at 13:00 that is 2h rather
    than 1h — older than reality, which is the direction a staleness figure is
    allowed to be wrong in.
    """
    reading = read_price(series(1.0, 2.0, first_hour=10), source=SOURCE)
    assert reading.age_at(AT(13)) == timedelta(hours=2)
    assert reading.age_at(AT(13)) >= timedelta(hours=1)
