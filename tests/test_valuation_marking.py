"""Milestone BM — the one crossing, where a price becomes a mark.

`marking.py` is the only module in the repository where a market-half type and
an owner-half type appear together, so this is where the crossing's rules are
pinned: one float→exact conversion and it is the money kernel's, a reading is
matched to a market by pair symbol, a non-spot market is refused rather than
approximated, and every unpriced market carries its own sentence.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from marks_helpers import SOURCE, reading, snapshot
from portfolio_risk_helpers import (
    BTCUSDC_MARKET,
    ETH_MARKET,
    EVEDEX_MARKET,
    EVEDEX_PERP,
    SOL_MARKET,
)
from trade_domain_helpers import AT, MARKET

from fmis.accounts import MarketId, MarketMode, VenueId
from fmis.money import AssetCode, exact_from_market_price
from fmis.portfolio import MarkQuote
from fmis.valuation import (
    CROSS_VENUE_NOTE,
    MARKABLE_MODES,
    MarkMismatchError,
    MarkSet,
    ValuationError,
    mark_from_reading,
    marks_for_markets,
    symbols_for_markets,
)

# --------------------------------------------------------------------------
# mark_from_reading — the crossing
# --------------------------------------------------------------------------


def test_a_reading_becomes_a_mark_carrying_the_markets_quote_asset() -> None:
    quote = mark_from_reading(reading(price=61000.5), market=MARKET)
    assert isinstance(quote, MarkQuote)
    assert quote.price == Decimal("61000.5")
    assert quote.quote_asset == MARKET.quote_asset


def test_the_conversion_is_the_money_kernels_one_float_crossing() -> None:
    """Re-implementing it here would create a second answer to *what is this
    price, exactly*, and two answers is how two surfaces come to disagree."""
    assert mark_from_reading(reading(price=0.1), market=MARKET).price == (
        exact_from_market_price(0.1)
    )


def test_the_conversion_does_not_inherit_binary_float_noise() -> None:
    """`repr` is the shortest text that round-trips a float exactly, so the
    stored decimal is what a reader would have typed, not `0.1000000000000000055`."""
    assert str(mark_from_reading(reading(price=0.1), market=MARKET).price) == "0.1"


def test_the_mark_is_dated_when_the_price_was_true_not_when_it_was_read() -> None:
    quote = mark_from_reading(reading(observed_at=AT(11)), market=MARKET)
    assert quote.as_of == AT(11)


def test_the_mark_carries_the_full_provenance_line() -> None:
    """A figure derived from this mark can always name where its price came from
    and how it was chosen."""
    quote = mark_from_reading(reading(), market=MARKET)
    assert quote.source == reading().provenance
    assert SOURCE in quote.source
    assert "last_closed_candle_close" in quote.source


def test_a_reading_for_a_different_symbol_is_refused() -> None:
    with pytest.raises(MarkMismatchError, match="will not make silently"):
        mark_from_reading(reading(symbol="ETHUSDT"), market=MARKET)


def test_the_symbol_match_is_case_insensitive() -> None:
    """A provider that lower-cases its symbols must not make a portfolio
    unvaluable; the identity is the characters, not their case."""
    assert mark_from_reading(reading(symbol="btcusdt"), market=MARKET) is not None


def test_a_non_spot_market_is_refused_rather_than_priced_from_spot() -> None:
    """A perpetual and its spot pair share a symbol and are two instruments with
    two prices. Valuing one at the other's price is not a valuation."""
    with pytest.raises(MarkMismatchError, match="two instruments with two prices"):
        mark_from_reading(
            reading(symbol=EVEDEX_PERP.pair_symbol), market=EVEDEX_PERP
        )


def test_only_spot_is_markable_in_this_build_and_that_is_stated() -> None:
    assert MARKABLE_MODES == frozenset({MarketMode.SPOT})


def test_mark_from_reading_refuses_arguments_of_the_wrong_type() -> None:
    with pytest.raises(TypeError, match="PriceReading"):
        mark_from_reading("61000", market=MARKET)
    with pytest.raises(TypeError, match="MarketId"):
        mark_from_reading(reading(), market="binance:BTCUSDT:spot")


# --------------------------------------------------------------------------
# symbols_for_markets
# --------------------------------------------------------------------------


def test_two_markets_differing_only_by_venue_need_one_fetch() -> None:
    """A price source is asked for a symbol and knows nothing of a venue."""
    assert symbols_for_markets((MARKET, EVEDEX_MARKET)) == ("BTCUSDT",)


def test_order_is_first_seen_rather_than_sorted() -> None:
    assert symbols_for_markets((SOL_MARKET, ETH_MARKET, MARKET)) == (
        "SOLUSDT", "ETHUSDT", "BTCUSDT",
    )


def test_a_different_quote_asset_is_a_different_symbol() -> None:
    """`BTCUSDT` and `BTCUSDC` are two symbols and one bet — two fetches."""
    assert symbols_for_markets((MARKET, BTCUSDC_MARKET)) == ("BTCUSDT", "BTCUSDC")


def test_symbols_for_markets_refuses_a_non_market() -> None:
    with pytest.raises(TypeError, match="MarketId"):
        symbols_for_markets(("BTCUSDT",))


# --------------------------------------------------------------------------
# marks_for_markets — matching, and every way it fails
# --------------------------------------------------------------------------


def test_a_priced_market_is_keyed_by_its_citation_form() -> None:
    """`MarketId.value` — venue and mode included — because that is the key the
    risk engine looks a mark up by."""
    found = marks_for_markets(snapshot(60000.0, 61000.0), (MARKET,))
    assert set(found.quotes) == {MARKET.value}
    assert found.quotes[MARKET.value].price == Decimal("61000")


def test_a_spot_holding_and_a_perpetual_are_never_handed_one_anothers_price() -> None:
    perp = MarketId(
        VenueId("binance"), AssetCode("BTC"), AssetCode("USDT"), MarketMode.PERPETUAL
    )
    found = marks_for_markets(snapshot(61000.0), (MARKET, perp))
    assert MARKET.value in found.quotes
    assert perp.value in found.reasons
    assert "two instruments with two prices" in found.reasons[perp.value]


def test_a_market_the_snapshot_recorded_a_failure_for_carries_that_failure() -> None:
    taken = snapshot(61000.0, unreadable={"ETHUSDT": "provider timed out"})
    found = marks_for_markets(taken, (ETH_MARKET,))
    assert "provider timed out" in found.reasons[ETH_MARKET.value]


def test_a_market_the_snapshot_never_covered_says_so_differently() -> None:
    """*"The fetch failed"* and *"it was never asked for"* are different facts."""
    found = marks_for_markets(snapshot(61000.0), (SOL_MARKET,))
    assert "was not among the" in found.reasons[SOL_MARKET.value]


def test_a_repeated_market_is_matched_once() -> None:
    found = marks_for_markets(snapshot(61000.0), (MARKET, MARKET))
    assert found.requested_count == 1


def test_a_cross_venue_holding_is_priced_and_the_substitution_is_visible() -> None:
    """Unavoidable while one price source exists, so it is named rather than
    hidden: every figure derived from it carries the price source."""
    found = marks_for_markets(snapshot(61000.0), (EVEDEX_MARKET,))
    assert EVEDEX_MARKET.value in found.quotes
    assert SOURCE in found.quotes[EVEDEX_MARKET.value].source


def test_the_cross_venue_note_states_the_substitution_plainly() -> None:
    assert "pair symbol" in CROSS_VENUE_NOTE
    assert "substitution" in CROSS_VENUE_NOTE


def test_marks_for_markets_refuses_arguments_of_the_wrong_type() -> None:
    with pytest.raises(TypeError, match="PriceSnapshot"):
        marks_for_markets({"BTCUSDT": 61000.0}, (MARKET,))
    with pytest.raises(TypeError, match="MarketId"):
        marks_for_markets(snapshot(1.0), ("BTCUSDT",))


# --------------------------------------------------------------------------
# MarkSet
# --------------------------------------------------------------------------


def test_the_two_halves_are_exhaustive_over_what_was_asked_for() -> None:
    found = marks_for_markets(snapshot(61000.0), (MARKET, SOL_MARKET))
    assert found.marked_count == 1
    assert found.unmarked_count == 1
    assert found.requested_count == 2


def test_completeness_is_a_named_property_rather_than_an_inference() -> None:
    """The condition under which a portfolio's totals can be money at all."""
    assert marks_for_markets(snapshot(61000.0), (MARKET,)).is_complete is True
    assert marks_for_markets(snapshot(61000.0), (SOL_MARKET,)).is_complete is False


def test_a_market_cannot_be_both_priced_and_unpriced() -> None:
    quote = MarkQuote(
        price=Decimal("1"), quote_asset=AssetCode("USDT"), source="x", as_of=AT(9)
    )
    with pytest.raises(ValueError, match="never both"):
        MarkSet(quotes={MARKET.value: quote}, reasons={MARKET.value: "timed out"})


def test_reason_for_accepts_a_market_or_its_citation_form() -> None:
    found = marks_for_markets(snapshot(61000.0), (SOL_MARKET,))
    assert found.reason_for(SOL_MARKET) == found.reason_for(SOL_MARKET.value)
    assert found.reason_for(MARKET) is None


def test_a_markset_refuses_something_that_is_not_a_mapping() -> None:
    with pytest.raises(TypeError, match="must be a mapping"):
        MarkSet(quotes=[], reasons={})


def test_every_failure_shares_one_base() -> None:
    assert issubclass(MarkMismatchError, ValuationError)
    assert issubclass(MarkMismatchError, ValueError)
