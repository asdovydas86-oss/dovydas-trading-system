"""Milestone BM — what a marked portfolio is, and what it refuses to invent.

The rules asserted here are the ones a money figure silently depends on: every
total is `Money` or `Absent(reason)` naming the position that broke it, no
calculation is duplicated, the two folds that meet here are named rather than
reconciled, and nothing on this object is storable.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from marks_helpers import SOURCE, snapshot
from portfolio_risk_helpers import SOL_MARKET
from trade_domain_helpers import AT, BTC, MARKET, USDT, trade
from valuation_helpers import marked, one_position, valued, with_cash

from fmis.accounts import AccountId
from fmis.ledger import TradeSide
from fmis.money import AssetCode, Money, Quantity
from fmis.portfolio import MarkQuote
from fmis.provenance import Absent, ValueOrigin
from fmis.valuation import (
    VALUATION_LIMITATIONS,
    MarkedPosition,
    PortfolioValuation,
)

# --------------------------------------------------------------------------
# MarkedPosition
# --------------------------------------------------------------------------


def test_market_value_is_quantity_times_mark() -> None:
    """0.5 BTC at 61000 USDT."""
    assert marked(61000.0).market_value == Money(Decimal("30500"), USDT)


def test_cost_basis_is_quantity_times_weighted_average_entry() -> None:
    assert marked().cost_basis == Money(Decimal("30000"), USDT)


def test_unrealized_pnl_is_the_folds_own_method_and_not_a_second_one() -> None:
    """Delegated rather than recomputed: a copy would be a second answer to the
    single most-read number on a portfolio page."""
    entry = marked(61000.0)
    assert entry.unrealized_pnl == entry.position.unrealized_pnl(
        entry.mark.price, USDT
    )
    assert entry.unrealized_pnl == Money(Decimal("500"), USDT)


def test_a_short_position_is_valued_negative() -> None:
    """A short holding reduces what the portfolio is worth, and the sign is
    carried by the fold's own signed net quantity."""
    entry = marked(61000.0, side=TradeSide.SELL)
    assert entry.market_value == Money(Decimal("-30500"), USDT)


def test_a_short_position_gains_when_the_price_falls() -> None:
    assert marked(59000.0, side=TradeSide.SELL).unrealized_pnl == Money(
        Decimal("500"), USDT
    )


def test_an_unmarked_position_states_every_figure_as_absent_with_a_reason() -> None:
    """Never a zero. A zero unrealized P&L on an unmarked position makes a total
    look plausible and survives for years."""
    entry = marked(None)
    for figure in (entry.market_value, entry.unrealized_pnl):
        assert isinstance(figure, Absent)
        assert MARKET.value in figure.reason
    assert entry.is_marked is False


def test_the_cost_basis_survives_a_missing_mark() -> None:
    """It needs no price — only what was paid."""
    assert marked(None).cost_basis == Money(Decimal("30000"), USDT)


def test_a_mark_in_the_wrong_currency_is_refused_at_construction() -> None:
    """A price in the wrong currency is not a cheaper price."""
    wrong = MarkQuote(
        price=Decimal("61000"), quote_asset=AssetCode("EUR"), source=SOURCE,
        as_of=AT(11),
    )
    with pytest.raises(ValueError, match="not a cheaper price"):
        MarkedPosition(position=one_position(), mark=wrong)


def test_cost_basis_is_absent_when_nothing_has_been_acquired() -> None:
    """An average cost over no units is undefined, not zero — and a zero would
    flow into a P&L figure that looked plausible.

    Unreachable through the fold, which never opens a position on zero
    quantity, so the defence is exercised against a position built with one.
    """
    import dataclasses

    from fmis.positions import AverageCost

    position = one_position()
    hollow = dataclasses.replace(
        position,
        average_entry=AverageCost(
            total_cost=Money(Decimal("0"), USDT), total_quantity=Quantity(
                Decimal("0"), BTC
            )
        ),
    )
    entry = MarkedPosition(position=hollow, mark=marked().mark)
    assert isinstance(entry.cost_basis, Absent)
    assert "no average entry" in entry.cost_basis.reason


def test_mark_age_is_computed_at_read_time() -> None:
    """The single-close fixture's bar opens at 08:00, so a 13:00 reading is 5h."""
    assert marked().mark_age_at(AT(13)) == timedelta(hours=5)


def test_mark_age_of_an_unmarked_position_is_absent_with_a_reason() -> None:
    assert isinstance(marked(None).mark_age_at(AT(13)), Absent)


def test_a_marked_position_refuses_arguments_of_the_wrong_type() -> None:
    with pytest.raises(TypeError, match="Position"):
        MarkedPosition(position="binance:BTCUSDT:spot")
    with pytest.raises(TypeError, match="MarkQuote or Absent"):
        MarkedPosition(position=one_position(), mark=Decimal("61000"))


def test_a_marked_position_is_measured_and_exports_without_a_decoder() -> None:
    entry = marked()
    assert entry.origin is ValueOrigin.MEASURED
    payload = entry.to_payload()
    assert payload["market_value"]["value"]["amount"] == "30500"
    assert not hasattr(MarkedPosition, "from_payload")


def test_an_unmarked_positions_payload_carries_reasons_rather_than_nulls() -> None:
    payload = marked(None).to_payload()
    assert "absent" in payload["mark"]
    assert "absent" in payload["unrealized_pnl"]


# --------------------------------------------------------------------------
# PortfolioValuation — the totals
# --------------------------------------------------------------------------


def test_market_value_delegates_to_net_exposure_rather_than_recomputing_it(
    tmp_path,
) -> None:
    """Computing it twice would give a page two numbers for one question and no
    way to say which was right."""
    valuation = valued(tmp_path / "store")
    assert valuation.market_value == valuation.state.net_exposure
    assert valuation.market_value == Money(Decimal("30500"), USDT)


def test_gross_long_short_and_open_risk_all_come_from_the_folded_state(
    tmp_path,
) -> None:
    valuation = valued(tmp_path / "store")
    assert valuation.gross_exposure == valuation.state.gross_exposure
    assert valuation.long_exposure == valuation.state.long_exposure
    assert valuation.short_exposure == valuation.state.short_exposure
    assert valuation.open_risk == valuation.state.open_risk


def test_unrealized_pnl_totals_the_positions(tmp_path) -> None:
    assert valued(tmp_path / "store").unrealized_pnl == Money(Decimal("500"), USDT)


def test_one_unmarked_position_makes_the_total_absent_and_names_it(
    tmp_path,
) -> None:
    """Never a smaller number that looks complete — `sum_or_absent`'s rule, and
    it is enforced in one place rather than two."""
    valuation = valued(
        tmp_path / "store",
        trade(),
        trade(
            market=SOL_MARKET,
            quantity=Quantity(Decimal("10"), AssetCode("SOL")),
            price=Decimal("150"),
            occurred_at=AT(11),
        ),
    )
    total = valuation.unrealized_pnl
    assert isinstance(total, Absent)
    assert SOL_MARKET.value in total.reason
    assert valuation.is_fully_marked is False
    assert [p.market.value for p in valuation.unmarked_positions] == [SOL_MARKET.value]


def test_equity_is_cash_plus_market_value_and_says_so(tmp_path) -> None:
    valuation = valued(tmp_path / "store")
    assert "cash" in valuation.equity_basis
    assert "market value" in valuation.equity_basis
    assert "oldest mark" in valuation.equity_basis


def test_equity_is_absent_when_no_snapshot_states_cash(tmp_path) -> None:
    """A balance this system has not observed is not a zero balance."""
    equity = valued(tmp_path / "store").marked_equity
    assert isinstance(equity, Absent)
    assert "cash is not known" in equity.reason


def test_equity_is_absent_when_the_market_value_is(tmp_path) -> None:
    """Cash known, prices absent: the second of the two ways equity fails, and
    it names the market half rather than the cash half."""
    valuation = valued(
        tmp_path / "store", prices=snapshot(), snapshots=(with_cash(),)
    )
    assert valuation.cash == Money(Decimal("2500"), USDT)
    assert isinstance(valuation.marked_equity, Absent)
    assert "market value is not known" in valuation.marked_equity.reason


def test_cost_basis_totals_the_positions(tmp_path) -> None:
    assert valued(tmp_path / "store").cost_basis == Money(Decimal("30000"), USDT)


# --------------------------------------------------------------------------
# Coverage, provenance and the two folds
# --------------------------------------------------------------------------


def test_the_oldest_mark_bounds_the_reading_rather_than_an_average(
    tmp_path,
) -> None:
    valuation = valued(tmp_path / "store")
    assert valuation.mark_age == timedelta(hours=4)


def test_mark_age_is_absent_when_nothing_was_priced(tmp_path) -> None:
    valuation = valued(tmp_path / "store", prices=snapshot())
    assert isinstance(valuation.mark_age, Absent)
    assert "priced nothing" in valuation.mark_age.reason


def test_every_priced_market_prints_where_its_price_came_from(tmp_path) -> None:
    lines = valued(tmp_path / "store").price_provenance
    assert len(lines) == 1
    assert MARKET.value in lines[0]
    assert "last_closed_candle_close" in lines[0]


def test_unstopped_markets_are_named_because_they_are_why_risk_is_absent(
    tmp_path,
) -> None:
    valuation = valued(tmp_path / "store")
    assert valuation.unstopped_markets == (MARKET.value,)
    assert isinstance(valuation.open_risk, Absent)


def test_the_two_folds_disagreement_is_named_rather_than_reconciled(
    tmp_path,
) -> None:
    """One market's fills in two accounts: the book-wide fold and the per-account
    fold answer different questions, and the page says which markets those are."""
    valuation = valued(
        tmp_path / "store",
        trade(),
        trade(account=AccountId("second_account"), occurred_at=AT(11)),
    )
    assert valuation.fold_disagreement == (f"{MARKET.value} (swing)",)


def test_no_disagreement_is_reported_when_one_account_holds_everything(
    tmp_path,
) -> None:
    assert valued(tmp_path / "store").fold_disagreement == ()


# --------------------------------------------------------------------------
# Construction rules
# --------------------------------------------------------------------------


def test_a_valuation_refuses_a_state_for_a_different_portfolio(tmp_path) -> None:
    valuation = valued(tmp_path / "store")
    with pytest.raises(ValueError, match="claims"):
        PortfolioValuation(
            portfolio_id="another_portfolio",
            base_currency=USDT,
            as_of=AT(12),
            state=valuation.state,
            positions=valuation.positions,
            marks=valuation.marks,
            prices=valuation.prices,
        )


def test_a_valuation_refuses_a_state_in_a_different_currency(tmp_path) -> None:
    valuation = valued(tmp_path / "store")
    with pytest.raises(ValueError, match="denominated in"):
        PortfolioValuation(
            portfolio_id=valuation.portfolio_id,
            base_currency=AssetCode("EUR"),
            as_of=AT(12),
            state=valuation.state,
            positions=valuation.positions,
            marks=valuation.marks,
            prices=valuation.prices,
        )


def test_a_base_currency_may_be_supplied_as_text(tmp_path) -> None:
    valuation = valued(tmp_path / "store")
    rebuilt = PortfolioValuation(
        portfolio_id=valuation.portfolio_id,
        base_currency="USDT",
        as_of=AT(12),
        state=valuation.state,
        positions=valuation.positions,
        marks=valuation.marks,
        prices=valuation.prices,
    )
    assert rebuilt.base_currency == USDT


def test_a_valuation_refuses_arguments_of_the_wrong_type(tmp_path) -> None:
    valuation = valued(tmp_path / "store")
    base = dict(
        portfolio_id=valuation.portfolio_id,
        base_currency=USDT,
        as_of=AT(12),
        state=valuation.state,
        positions=valuation.positions,
        marks=valuation.marks,
        prices=valuation.prices,
    )
    with pytest.raises(TypeError, match="PortfolioState"):
        PortfolioValuation(**{**base, "state": "a state"})
    with pytest.raises(TypeError, match="MarkSet"):
        PortfolioValuation(**{**base, "marks": {}})
    with pytest.raises(TypeError, match="PriceSnapshot"):
        PortfolioValuation(**{**base, "prices": {}})
    with pytest.raises(TypeError, match="MarkedPosition"):
        PortfolioValuation(**{**base, "positions": ("a position",)})


def test_a_valuation_refuses_a_portfolio_id_the_domain_would_not_accept(
    tmp_path,
) -> None:
    valuation = valued(tmp_path / "store")
    with pytest.raises(Exception, match="does not match"):
        PortfolioValuation(
            portfolio_id="Owner-Portfolio",
            base_currency=USDT,
            as_of=AT(12),
            state=valuation.state,
            positions=valuation.positions,
            marks=valuation.marks,
            prices=valuation.prices,
        )


# --------------------------------------------------------------------------
# Nothing here is stored
# --------------------------------------------------------------------------


def test_a_valuation_exports_and_has_no_decoder(tmp_path) -> None:
    payload = valued(tmp_path / "store").to_payload()
    assert payload["market_value"]["value"]["amount"] == "30500"
    assert payload["unrealized_pnl"]["value"]["amount"] == "500"
    assert not hasattr(PortfolioValuation, "from_payload")


def test_nothing_in_this_package_is_a_persisted_record_kind() -> None:
    """A derived reading must not become authoritative truth. The day one does,
    it needs a `RecordKind`, a spec row and a durability class chosen
    deliberately."""
    from fmis import valuation as package
    from fmis.persistence import SPECS

    persisted = {spec.record_type for spec in SPECS.values()}
    for name in package.__all__:
        assert getattr(package, name) not in persisted, name


def test_the_limitations_state_why_nothing_is_frozen() -> None:
    codes = {code for code, _ in VALUATION_LIMITATIONS}
    assert codes == {"VA-1", "VA-2", "VA-3", "VA-4", "VA-5"}
    text = " ".join(statement for _, statement in VALUATION_LIMITATIONS)
    assert "no transfer event kind exists" in text
    assert "folded book-wide" in text


def test_a_valuation_carries_its_limitations_by_default(tmp_path) -> None:
    assert valued(tmp_path / "store").limitations == VALUATION_LIMITATIONS


def test_a_valuation_is_measured(tmp_path) -> None:
    assert valued(tmp_path / "store").origin is ValueOrigin.MEASURED


def test_marked_and_unmarked_positions_partition_the_list(tmp_path) -> None:
    valuation = valued(
        tmp_path / "store",
        trade(),
        trade(
            market=SOL_MARKET,
            quantity=Quantity(Decimal("10"), AssetCode("SOL")),
            price=Decimal("150"),
            occurred_at=AT(11),
        ),
    )
    assert len(valuation.marked_positions) + len(valuation.unmarked_positions) == len(
        valuation.positions
    )
    assert len(valuation.positions) == 2


def test_the_quantity_asset_is_the_markets_base_asset(tmp_path) -> None:
    assert marked().position.net_quantity.asset == BTC
