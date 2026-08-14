"""Milestone BM — the valuation page.

Rendering only: nothing here is about what a figure is, only about whether the
page states it, states its absence, fits in 78 columns, and can be read without
colour.
"""

from __future__ import annotations

import ast
import inspect
from decimal import Decimal
from pathlib import Path

import pytest
from marks_helpers import snapshot
from portfolio_risk_helpers import SOL_MARKET
from trade_domain_helpers import AT, MARKET, USDT, trade
from valuation_helpers import store_with, valued, with_cash

from fmis.accounts import AccountId, Book
from fmis.money import AssetCode, Quantity
from fmis.valuation import DEFAULT_PORTFOLIO_ID, render_valuation, value_portfolio
from fmis.valuation import render as render_module

_WIDTH = 78


def _page(tmp_path, *trades, **kwargs) -> str:
    return render_valuation(valued(tmp_path / "store", *trades, **kwargs))


# --------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------


def test_every_section_is_present(tmp_path) -> None:
    page = _page(tmp_path)
    for heading in ("PORTFOLIO VALUATION", "VALUE", "EXPOSURE", "POSITIONS",
                    "PRICES", "LIMITATIONS"):
        assert heading in page, heading


def test_no_line_exceeds_the_page_width(tmp_path) -> None:
    for line in _page(tmp_path).splitlines():
        assert len(line) <= _WIDTH, line


def test_a_long_absence_reason_wraps_rather_than_running_off_the_page(
    tmp_path,
) -> None:
    """Milestone BJ found four places where a long value pushed a *different*
    value past the page edge; every width test passed, because the line fitted."""
    page = _page(tmp_path, prices=snapshot())
    for line in page.splitlines():
        assert len(line) <= _WIDTH, line
    assert "unavailable" in page


def test_the_page_is_ascii_structured_and_depends_on_no_colour(tmp_path) -> None:
    page = _page(tmp_path)
    assert "\x1b[" not in page
    assert "=" * _WIDTH in page
    assert "-" * _WIDTH in page


def test_rendering_is_deterministic(tmp_path) -> None:
    valuation = valued(tmp_path / "store")
    assert render_valuation(valuation) == render_valuation(valuation)


# --------------------------------------------------------------------------
# Figures and absences
# --------------------------------------------------------------------------


def test_every_money_figure_reaches_the_page(tmp_path) -> None:
    page = _page(tmp_path, snapshots=(with_cash(),))
    assert "market value" in page
    assert "unrealized P&L" in page
    assert "30500 USDT" in page
    assert "500 USDT" in page
    assert "33000 USDT" in page


def test_an_absent_figure_prints_its_reason_and_never_a_zero(tmp_path) -> None:
    """A blank where a total belongs reads as a total of nothing, and for a
    portfolio that is the most expensive misreading available."""
    page = _page(tmp_path, prices=snapshot())
    assert "unavailable" in page
    assert "no mark for" in page


def test_open_risk_names_the_positions_with_no_recorded_stop(tmp_path) -> None:
    page = _page(tmp_path)
    assert "no commitment records a stop for" in page
    assert MARKET.value in page


def test_an_empty_portfolio_says_so_rather_than_printing_nothing(tmp_path) -> None:
    valuation = value_portfolio(
        store_with(tmp_path / "store", trade(book=Book.PAPER)),
        portfolio_id=DEFAULT_PORTFOLIO_ID, base_currency=USDT, as_of=AT(12),
        prices=snapshot(),
    )
    page = render_valuation(valuation)
    assert "POSITIONS (0)" in page
    assert "not a statement about accounts this system has never been told" in page


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


def test_every_priced_market_prints_where_its_price_came_from(tmp_path) -> None:
    page = _page(tmp_path)
    assert "last_closed_candle_close" in page
    assert "1 of 1 market(s) priced" in page


def test_the_oldest_mark_age_is_on_the_page(tmp_path) -> None:
    assert "oldest mark age:" in _page(tmp_path)


def test_an_unpriced_market_prints_its_reason_in_the_prices_section(
    tmp_path,
) -> None:
    page = _page(
        tmp_path,
        trade(),
        trade(
            market=SOL_MARKET,
            quantity=Quantity(Decimal("10"), AssetCode("SOL")),
            price=Decimal("150"),
            occurred_at=AT(11),
        ),
    )
    assert SOL_MARKET.value in page
    assert "was not among the" in page


def test_each_position_prints_its_mark_value_and_unrealized(tmp_path) -> None:
    page = _page(tmp_path)
    assert "mark 61000 USDT" in page
    assert "value" in page
    assert "unrealized" in page


def test_a_position_header_sits_at_the_sections_own_indent(tmp_path) -> None:
    """Found by a live run, not by a width test: a doubly-indented header still
    fits in 78 columns and still reads as a nested block that is not there."""
    header = next(
        line for line in _page(tmp_path).splitlines() if "BTCUSDT · swing" in line
    )
    assert header.startswith("   BTCUSDT")
    assert not header.startswith("    ")


def test_an_unmarked_position_prints_why_it_has_no_price(tmp_path) -> None:
    page = _page(tmp_path, prices=snapshot())
    assert "mark: unavailable" in page


# --------------------------------------------------------------------------
# The two folds and the limitations
# --------------------------------------------------------------------------


def test_the_two_folds_section_appears_only_when_they_can_disagree(
    tmp_path,
) -> None:
    assert "TWO FOLDS" not in _page(tmp_path)
    page = _page(
        tmp_path, trade(), trade(account=AccountId("second_account"),
                                 occurred_at=AT(11))
    )
    assert "TWO FOLDS" in page
    assert "answer different questions about them" in page


def test_every_limitation_prints_at_the_foot_of_the_page(tmp_path) -> None:
    page = _page(tmp_path)
    for code in ("VA-1", "VA-2", "VA-3", "VA-4", "VA-5"):
        assert code in page
    assert page.index("VA-1") > page.index("PRICES")


# --------------------------------------------------------------------------
# The renderer computes nothing
# --------------------------------------------------------------------------


def test_the_renderer_constructs_no_money_and_sums_nothing() -> None:
    """Every money figure on this page is a property already on the model."""
    source = Path(inspect.getfile(render_module)).read_text(encoding="utf-8")
    called = {
        node.func.id
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "Money" not in called
    assert "sum" not in called
    assert "sum_or_absent" not in called


def test_the_renderer_reaches_no_store_and_no_engine() -> None:
    source = Path(inspect.getfile(render_module)).read_text(encoding="utf-8")
    imported = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(name.startswith("fmis.persistence") for name in imported)
    assert not any(name.startswith("fmis.marks") for name in imported)
    assert not any(name.startswith("fmis.pipeline") for name in imported)


def test_the_renderer_refuses_something_that_is_not_a_valuation() -> None:
    with pytest.raises(TypeError, match="PortfolioValuation"):
        render_valuation({"market_value": "30500 USDT"})
