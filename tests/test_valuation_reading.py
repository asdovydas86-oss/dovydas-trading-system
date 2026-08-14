"""Milestone BM — reading a store and folding it against prices.

`fmis.valuation.reading` is the composition root that touches persistence, so
this is where the store-facing rules are pinned: only open positions are priced,
nothing is written, a past instant reconstructs what the store *knew*, and a
market with no price leaves its position unmarked rather than absent from the
list.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from marks_helpers import snapshot
from persistence_helpers import new_store, write_request
from portfolio_risk_helpers import SOL_MARKET
from trade_domain_helpers import AT, MARKET, USDT, trade
from valuation_helpers import DUST, store_with, with_cash

from fmis.accounts import Book, MarketId, MarketMode, VenueId
from fmis.ledger import TradeSide
from fmis.money import AssetCode, Money, Quantity
from fmis.persistence import TradingStore
from fmis.provenance import Absent
from fmis.valuation import (
    DEFAULT_PORTFOLIO_ID,
    marked_positions,
    markets_to_price,
    open_positions_in,
    symbols_to_price,
    value_portfolio,
)

# --------------------------------------------------------------------------
# What needs a price
# --------------------------------------------------------------------------


def test_an_empty_store_needs_no_price(tmp_path) -> None:
    store = TradingStore(tmp_path / "store", dust=DUST)
    assert markets_to_price(store) == ()
    assert symbols_to_price(store) == ()


def test_a_root_that_does_not_exist_is_emptiness_rather_than_a_failure(
    tmp_path,
) -> None:
    """Constructing a store creates no directory and writes no byte."""
    root = tmp_path / "never-created"
    assert symbols_to_price(TradingStore(root, dust=DUST)) == ()
    assert not root.exists()


def test_one_open_position_needs_one_price(tmp_path) -> None:
    store = store_with(tmp_path / "store")
    assert markets_to_price(store) == (MARKET,)
    assert symbols_to_price(store) == ("BTCUSDT",)


def test_a_closed_position_is_never_priced(tmp_path) -> None:
    """It has no market value and no unrealized profit and loss, so fetching a
    price for it would spend a request to produce a number nothing may show."""
    store = store_with(
        tmp_path / "store",
        trade(),
        trade(side=TradeSide.SELL, occurred_at=AT(11)),
    )
    assert markets_to_price(store) == ()


def test_a_position_outside_the_covered_books_is_not_priced(tmp_path) -> None:
    store = store_with(tmp_path / "store", trade(book=Book.PAPER))
    assert markets_to_price(store) == ()
    assert markets_to_price(store, books_covered=(Book.PAPER,)) == (MARKET,)


def test_two_markets_need_two_symbols(tmp_path) -> None:
    store = store_with(
        tmp_path / "store",
        trade(),
        trade(
            market=SOL_MARKET,
            quantity=Quantity(Decimal("10"), AssetCode("SOL")),
            price=Decimal("150"),
            occurred_at=AT(11),
        ),
    )
    assert set(symbols_to_price(store)) == {"BTCUSDT", "SOLUSDT"}


def test_one_market_held_twice_needs_one_symbol(tmp_path) -> None:
    store = store_with(
        tmp_path / "store", trade(), trade(occurred_at=AT(11))
    )
    assert symbols_to_price(store) == ("BTCUSDT",)


def test_one_market_held_in_two_books_needs_one_price(tmp_path) -> None:
    """Two positions — books never share capacity — and one fetch, because a
    price source is asked for a symbol and knows nothing of a book."""
    store = store_with(
        tmp_path / "store",
        trade(),
        trade(book=Book.INVESTING, occurred_at=AT(11)),
    )
    assert len(open_positions_in(store)) == 2
    assert markets_to_price(store) == (MARKET,)


def test_the_store_argument_is_type_checked(tmp_path) -> None:
    with pytest.raises(TypeError, match="TradingStore"):
        markets_to_price(str(tmp_path))


# --------------------------------------------------------------------------
# Pairing positions with marks
# --------------------------------------------------------------------------


def test_a_position_with_no_mark_is_listed_with_its_reason(tmp_path) -> None:
    """Unmarked, not absent. A position missing from the list is a position the
    owner would not know they still hold."""
    positions = open_positions_in(store_with(tmp_path / "store"))
    paired = marked_positions(positions, {})
    assert len(paired) == 1
    assert paired[0].is_marked is False
    assert MARKET.value in paired[0].mark.reason


def test_the_pairing_key_is_the_full_market_identity(tmp_path) -> None:
    """Keyed by pair symbol, a perpetual would silently take the spot price."""
    positions = open_positions_in(store_with(tmp_path / "store"))
    paired = marked_positions(positions, {"BTCUSDT": "not the right key"})
    assert paired[0].is_marked is False


# --------------------------------------------------------------------------
# value_portfolio
# --------------------------------------------------------------------------


def test_a_populated_store_produces_money_where_BL_produced_absences(
    tmp_path,
) -> None:
    """The whole point of the milestone, asserted directly: every exposure
    figure was `Absent` before a mark source existed."""
    store = store_with(tmp_path / "store")
    valuation = value_portfolio(
        store,
        portfolio_id=DEFAULT_PORTFOLIO_ID,
        base_currency=USDT,
        as_of=AT(12),
        prices=snapshot(61000.0, taken_at=AT(12)),
    )
    assert valuation.market_value == Money(Decimal("30500"), USDT)
    assert valuation.gross_exposure == Money(Decimal("30500"), USDT)
    assert valuation.unrealized_pnl == Money(Decimal("500"), USDT)


def test_the_same_store_and_the_same_prices_give_an_equal_reading(
    tmp_path,
) -> None:
    """A valuation is a rebuildable projection: read it twice, get the same
    answer, or it was not a projection."""
    store = store_with(tmp_path / "store")
    kwargs = dict(
        portfolio_id=DEFAULT_PORTFOLIO_ID,
        base_currency=USDT,
        as_of=AT(12),
        prices=snapshot(61000.0, taken_at=AT(12)),
    )
    first = value_portfolio(store, **kwargs)
    second = value_portfolio(store, **kwargs)
    assert first.to_payload() == second.to_payload()


def test_an_empty_price_snapshot_leaves_every_total_absent_and_named(
    tmp_path,
) -> None:
    valuation = value_portfolio(
        store_with(tmp_path / "store"),
        portfolio_id=DEFAULT_PORTFOLIO_ID,
        base_currency=USDT,
        as_of=AT(12),
        prices=snapshot(),
    )
    assert isinstance(valuation.market_value, Absent)
    assert MARKET.value in valuation.market_value.reason
    assert valuation.positions  # the position is still listed


def test_cash_comes_from_the_snapshot_the_owner_took(tmp_path) -> None:
    valuation = value_portfolio(
        store_with(tmp_path / "store", snapshots=(with_cash(),)),
        portfolio_id=DEFAULT_PORTFOLIO_ID,
        base_currency=USDT,
        as_of=AT(12),
        prices=snapshot(61000.0, taken_at=AT(12)),
    )
    assert valuation.cash == Money(Decimal("2500"), USDT)
    assert valuation.marked_equity == Money(Decimal("33000"), USDT)


def test_the_cash_figure_carries_the_instant_it_was_true(tmp_path) -> None:
    """A snapshot taken six weeks ago is a good record and a poor description of
    today's cash, and the reader is entitled to see which."""
    valuation = value_portfolio(
        store_with(tmp_path / "store", snapshots=(with_cash(),)),
        portfolio_id=DEFAULT_PORTFOLIO_ID,
        base_currency=USDT,
        as_of=AT(12),
        prices=snapshot(61000.0, taken_at=AT(12)),
    )
    assert valuation.cash_as_of == AT(9)


def test_a_perpetual_holding_is_listed_and_refused_a_price(tmp_path) -> None:
    perp = MarketId(
        VenueId("binance"), AssetCode("BTC"), AssetCode("USDT"), MarketMode.PERPETUAL
    )
    valuation = value_portfolio(
        store_with(tmp_path / "store", trade(market=perp)),
        portfolio_id=DEFAULT_PORTFOLIO_ID,
        base_currency=USDT,
        as_of=AT(12),
        prices=snapshot(61000.0, taken_at=AT(12)),
    )
    assert len(valuation.positions) == 1
    assert valuation.is_fully_marked is False
    assert "two instruments with two prices" in valuation.marks.reasons[perp.value]


def test_a_past_instant_reconstructs_what_the_store_knew_then(tmp_path) -> None:
    root = tmp_path / "store"
    store = new_store(root, dust=DUST)
    store.trades.create(trade(), request=write_request(written_at=AT(10)))
    store.trades.create(
        trade(occurred_at=AT(11)), request=write_request(written_at=AT(14))
    )
    early = value_portfolio(
        store, portfolio_id=DEFAULT_PORTFOLIO_ID, base_currency=USDT,
        as_of=AT(12), prices=snapshot(61000.0, taken_at=AT(12)), known_at=AT(12),
    )
    late = value_portfolio(
        store, portfolio_id=DEFAULT_PORTFOLIO_ID, base_currency=USDT,
        as_of=AT(15), prices=snapshot(61000.0, taken_at=AT(15)), known_at=AT(15),
    )
    assert early.market_value == Money(Decimal("30500"), USDT)
    assert late.market_value == Money(Decimal("61000"), USDT)


def test_value_portfolio_type_checks_its_arguments(tmp_path) -> None:
    store = store_with(tmp_path / "store")
    with pytest.raises(TypeError, match="PriceSnapshot"):
        value_portfolio(
            store, portfolio_id=DEFAULT_PORTFOLIO_ID, base_currency=USDT,
            as_of=AT(12), prices={"BTCUSDT": 61000.0},
        )
    with pytest.raises(TypeError, match="TradingStore"):
        value_portfolio(
            "a store", portfolio_id=DEFAULT_PORTFOLIO_ID, base_currency=USDT,
            as_of=AT(12), prices=snapshot(),
        )


def test_a_base_currency_can_be_supplied_as_text(tmp_path) -> None:
    valuation = value_portfolio(
        store_with(tmp_path / "store"), portfolio_id=DEFAULT_PORTFOLIO_ID,
        base_currency="USDT", as_of=AT(12),
        prices=snapshot(61000.0, taken_at=AT(12)),
    )
    assert valuation.base_currency == USDT


def test_a_holding_quoted_in_another_currency_is_unvalued_rather_than_converted(
    tmp_path,
) -> None:
    """This system holds no exchange rate, and inventing one would be a
    fabricated number rather than a convenience."""
    valuation = value_portfolio(
        store_with(tmp_path / "store"), portfolio_id=DEFAULT_PORTFOLIO_ID,
        base_currency=AssetCode("EUR"), as_of=AT(12),
        prices=snapshot(61000.0, taken_at=AT(12)),
    )
    assert isinstance(valuation.market_value, Absent)
    assert "no rate to EUR" in valuation.market_value.reason


# --------------------------------------------------------------------------
# It writes nothing
# --------------------------------------------------------------------------


def test_valuing_a_store_changes_no_byte_on_disk(tmp_path) -> None:
    """Observed against a real store rather than promised."""
    root = tmp_path / "store"
    store = store_with(root)
    before = {
        path: path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()
    }
    value_portfolio(
        store, portfolio_id=DEFAULT_PORTFOLIO_ID, base_currency=USDT,
        as_of=AT(12), prices=snapshot(61000.0, taken_at=AT(12)),
    )
    after = {
        path: path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()
    }
    assert after == before
