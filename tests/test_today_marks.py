"""Milestone BM — what changed on `fmits today` when a mark source arrived.

Milestone BJ's own record named the gap: *"open risk cannot be measured without
a mark for every holding and a recorded stop for every position, and neither
exists."* Half of that is now false, and this module asserts the half that
changed and the half that did not.

Nothing here re-tests the page's structure, the priority queue or the warnings —
those are `tests/test_today_*.py` and are unchanged by this milestone.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from marks_helpers import klines_transport, snapshot
from portfolio_risk_helpers import SOL_MARKET
from today_helpers import REFERENCE, reading, result, workspace
from trade_domain_helpers import AT, MARKET, trade
from valuation_helpers import store_with, with_cash

from fmis.money import AssetCode, Quantity
from fmis.today import DUST_POLICY, NotAvailable, build_today, read_store, render_today
from fmis.today import builder as builder_module
from fmis.today.sections import portfolio_overview


def _scan():
    from tests.test_swing_setup_render import confirmed_long

    return (result(confirmed_long()),)


# --------------------------------------------------------------------------
# The section, with and without a valuation
# --------------------------------------------------------------------------


def test_without_a_valuation_the_page_reads_exactly_as_BJ_shipped_it() -> None:
    """`None` rather than an empty valuation: *"this page did not look"* and
    *"this page looked and priced nothing"* are different facts."""
    overview = portfolio_overview(
        store_root="/tmp/store", store_present=True, positions=(),
        budget=None, snapshot=None,
    )
    for figure in (overview.market_value, overview.unrealized_pnl,
                   overview.marks_note, overview.committed_risk):
        assert isinstance(figure, NotAvailable)
    assert "no price source was consulted" in overview.market_value.reason


def test_a_position_carries_no_price_field_when_none_was_sought(tmp_path) -> None:
    from fmis.valuation import open_positions_in

    positions = open_positions_in(store_with(tmp_path / "store"))
    overview = portfolio_overview(
        store_root="/tmp/store", store_present=True, positions=positions,
        budget=None, snapshot=None,
    )
    line = overview.open_positions[0]
    assert (line.mark, line.market_value, line.unrealized_pnl) == (None, None, None)


def test_with_a_valuation_the_figures_are_money(tmp_path) -> None:
    from fmis.valuation import DEFAULT_PORTFOLIO_ID, value_portfolio

    valuation = value_portfolio(
        store_with(tmp_path / "store"), portfolio_id=DEFAULT_PORTFOLIO_ID,
        base_currency="USDT", as_of=AT(12),
        prices=snapshot(61000.0, taken_at=AT(12)),
    )
    overview = portfolio_overview(
        store_root="/tmp/store", store_present=True,
        positions=[entry.position for entry in valuation.positions],
        budget=None, snapshot=None, valuation=valuation,
    )
    assert overview.market_value == "30500 USDT"
    assert overview.unrealized_pnl == "500 USDT"
    assert overview.exposure == "30500 USDT"
    assert "1 of 1 market(s) priced" in overview.marks_note


def test_each_position_carries_its_own_mark_and_figures(tmp_path) -> None:
    from fmis.valuation import DEFAULT_PORTFOLIO_ID, value_portfolio

    valuation = value_portfolio(
        store_with(tmp_path / "store"), portfolio_id=DEFAULT_PORTFOLIO_ID,
        base_currency="USDT", as_of=AT(12),
        prices=snapshot(61000.0, taken_at=AT(12)),
    )
    overview = portfolio_overview(
        store_root="/tmp/store", store_present=True, positions=(),
        budget=None, snapshot=None, valuation=valuation,
    )
    line = overview.open_positions[0]
    assert "61000 USDT" in line.mark
    assert "last_closed_candle_close" in line.mark
    assert line.market_value == "30500 USDT"
    assert line.unrealized_pnl == "500 USDT"


def test_an_unmarked_position_carries_a_reason_rather_than_a_zero(
    tmp_path,
) -> None:
    from fmis.valuation import DEFAULT_PORTFOLIO_ID, value_portfolio

    valuation = value_portfolio(
        store_with(tmp_path / "store"), portfolio_id=DEFAULT_PORTFOLIO_ID,
        base_currency="USDT", as_of=AT(12), prices=snapshot(),
    )
    overview = portfolio_overview(
        store_root="/tmp/store", store_present=True, positions=(),
        budget=None, snapshot=None, valuation=valuation,
    )
    line = overview.open_positions[0]
    assert line.mark.startswith("unavailable")
    assert line.market_value.startswith("unavailable")
    assert isinstance(overview.market_value, NotAvailable)


def test_open_risk_stays_absent_because_no_plan_records_a_stop(tmp_path) -> None:
    """The half of BJ's gap this milestone did **not** close, stated rather than
    quietly still failing."""
    from fmis.valuation import DEFAULT_PORTFOLIO_ID, value_portfolio

    valuation = value_portfolio(
        store_with(tmp_path / "store"), portfolio_id=DEFAULT_PORTFOLIO_ID,
        base_currency="USDT", as_of=AT(12),
        prices=snapshot(61000.0, taken_at=AT(12)),
    )
    overview = portfolio_overview(
        store_root="/tmp/store", store_present=True, positions=(),
        budget=None, snapshot=None, valuation=valuation,
    )
    assert isinstance(overview.committed_risk, NotAvailable)
    assert "no commitment is recorded" in overview.committed_risk.reason
    assert "a stop is what a TradePlan states" in overview.committed_risk.reason


# --------------------------------------------------------------------------
# The store reading
# --------------------------------------------------------------------------


def test_read_store_produces_no_valuation_when_no_prices_are_supplied(
    tmp_path,
) -> None:
    store_with(tmp_path / "store")
    found = read_store(tmp_path / "store", at=REFERENCE, archive_root=tmp_path / "a")
    assert found.valuation is None


def test_read_store_produces_a_valuation_when_prices_are_supplied(
    tmp_path,
) -> None:
    store_with(tmp_path / "store")
    found = read_store(
        tmp_path / "store", at=REFERENCE, archive_root=tmp_path / "a",
        prices=snapshot(61000.0, taken_at=REFERENCE),
    )
    assert found.valuation is not None
    assert str(found.valuation.market_value) == "30500 USDT"


def test_an_empty_reading_carries_no_valuation() -> None:
    assert reading().valuation is None


# --------------------------------------------------------------------------
# End to end through run_today
# --------------------------------------------------------------------------


def test_run_today_prices_only_what_the_store_holds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Not the watchlist. A watchlist symbol has no quantity and therefore no
    value; asking for one would spend a request to produce a number nothing on
    this page may show."""
    from fmis.pipeline import prices as prices_module

    root = tmp_path / "store"
    store_with(root, snapshots=(with_cash(),))
    seen: list[str] = []

    def _capturing(url: str):
        seen.append(url)
        return klines_transport(60000.0, 61000.0)(url)

    monkeypatch.setattr(builder_module, "run_market_scan", lambda s, **k: _scan())
    monkeypatch.setattr(
        prices_module, "urlopen_transport", _capturing, raising=False
    )
    space = builder_module.run_today(
        ("BTCUSDT", "ETHUSDT", "SOLUSDT"),
        reference_time=AT(20),
        store_root=root,
        archive_root=tmp_path / "archive",
        transport=_capturing,
    )
    assert len(seen) == 1
    assert "symbol=BTCUSDT" in seen[0]
    assert space.portfolio.market_value == "30500 USDT"


def test_no_marks_keeps_the_store_and_skips_only_the_prices(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "store"
    store_with(root)

    def _never(url: str):  # pragma: no cover - proving it is never reached
        raise AssertionError("a price was fetched with read_marks=False")

    monkeypatch.setattr(builder_module, "run_market_scan", lambda s, **k: _scan())
    space = builder_module.run_today(
        ("BTCUSDT",), reference_time=AT(20), store_root=root,
        archive_root=tmp_path / "archive", read_marks=False, transport=_never,
    )
    assert space.portfolio.open_count == 1
    assert isinstance(space.portfolio.market_value, NotAvailable)


def test_a_price_outage_leaves_the_page_standing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A portfolio page that vanishes when one symbol is unreachable is a page
    the owner learns not to rely on."""
    from marks_helpers import failing_transport

    root = tmp_path / "store"
    store_with(root)
    monkeypatch.setattr(builder_module, "run_market_scan", lambda s, **k: _scan())
    space = builder_module.run_today(
        ("BTCUSDT",), reference_time=AT(20), store_root=root,
        archive_root=tmp_path / "archive", transport=failing_transport(),
    )
    assert space.portfolio.open_count == 1
    assert isinstance(space.portfolio.market_value, NotAvailable)
    assert "0 of 1 market(s) priced" in space.portfolio.marks_note


def test_the_mark_interval_reaches_the_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "store"
    store_with(root)
    seen: list[str] = []

    def _capturing(url: str):
        seen.append(url)
        return klines_transport(1.0, 2.0)(url)

    monkeypatch.setattr(builder_module, "run_market_scan", lambda s, **k: _scan())
    builder_module.run_today(
        ("BTCUSDT",), reference_time=AT(20), store_root=root,
        archive_root=tmp_path / "archive", transport=_capturing,
        mark_interval="4h",
    )
    assert "interval=4h" in seen[0]


def test_a_corrupt_store_fails_pricing_as_a_workspace_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two names for one condition reaching the same surface is how one of them
    stops being handled."""
    from fmis.today import StoreUnreadableError

    root = tmp_path / "store"
    store_with(root)
    next(root.rglob("*.jsonl")).write_text("{ not json\n", encoding="utf-8")
    monkeypatch.setattr(builder_module, "run_market_scan", lambda s, **k: _scan())
    with pytest.raises(StoreUnreadableError, match="could not be read"):
        builder_module.run_today(
            ("BTCUSDT",), reference_time=AT(20), store_root=root,
            archive_root=tmp_path / "archive", transport=klines_transport(1.0),
        )


# --------------------------------------------------------------------------
# The rendered page
# --------------------------------------------------------------------------


def test_the_marked_figures_reach_the_rendered_page(tmp_path) -> None:
    from fmis.valuation import DEFAULT_PORTFOLIO_ID, value_portfolio

    store_with(tmp_path / "store")
    found = read_store(
        tmp_path / "store", at=REFERENCE, archive_root=tmp_path / "a",
        prices=snapshot(61000.0, taken_at=REFERENCE),
    )
    page = render_today(
        build_today(_scan(), found, reference_time=REFERENCE, source="fixture")
    )
    assert "Market value" in page
    assert "Unrealized P&L" in page
    assert "30500 USDT" in page
    assert "Marks" in page


def test_the_marked_page_still_fits_the_page_width(tmp_path) -> None:
    store_with(tmp_path / "store")
    found = read_store(
        tmp_path / "store", at=REFERENCE, archive_root=tmp_path / "a",
        prices=snapshot(61000.0, taken_at=REFERENCE),
    )
    page = render_today(
        build_today(_scan(), found, reference_time=REFERENCE, source="fixture")
    )
    for line in page.splitlines():
        assert len(line) <= 78, line


def test_an_unpriced_page_still_fits_the_page_width(tmp_path) -> None:
    """The reasons are sentences, and a sentence is longer than a column."""
    store_with(
        tmp_path / "store",
        trade(),
        trade(
            market=SOL_MARKET,
            quantity=Quantity(Decimal("10"), AssetCode("SOL")),
            price=Decimal("150"),
            occurred_at=AT(11),
        ),
    )
    found = read_store(
        tmp_path / "store", at=REFERENCE, archive_root=tmp_path / "a",
        prices=snapshot(),
    )
    page = render_today(
        build_today(_scan(), found, reference_time=REFERENCE, source="fixture")
    )
    for line in page.splitlines():
        assert len(line) <= 78, line


def test_the_page_still_writes_nothing_when_it_prices(tmp_path) -> None:
    root = tmp_path / "store"
    store_with(root)
    before = {
        path: path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()
    }
    read_store(
        root, at=REFERENCE, archive_root=tmp_path / "a",
        prices=snapshot(61000.0, taken_at=REFERENCE),
    )
    after = {
        path: path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()
    }
    assert after == before


def test_the_mark_age_prints_to_whole_seconds(tmp_path) -> None:
    """A microsecond is the only thing on the line that changes between two runs
    a second apart, which made a reproducible page look otherwise."""
    from fmis.valuation import DEFAULT_PORTFOLIO_ID, value_portfolio

    valuation = value_portfolio(
        store_with(tmp_path / "store"), portfolio_id=DEFAULT_PORTFOLIO_ID,
        base_currency="USDT",
        as_of=AT(12).replace(microsecond=123456),
        prices=snapshot(61000.0, taken_at=AT(12)),
    )
    overview = portfolio_overview(
        store_root="/tmp/store", store_present=True, positions=(),
        budget=None, snapshot=None, valuation=valuation,
    )
    assert "oldest mark age 4:00:00" in overview.marks_note
    assert "." not in overview.marks_note.split("oldest mark age ")[1]


def test_the_invariant_limitation_states_what_is_now_measurable() -> None:
    """`BJ`'s TD-3 said no mark source existed. Half of that is no longer true,
    and a limitation register that lags is a register a reader stops reading."""
    from fmis.today import TODAY_LIMITATIONS

    statement = dict(TODAY_LIMITATIONS)["TD-3"]
    assert "Market value and exposure are measured from marks" in statement
    assert "open risk still cannot be" in statement


def test_the_workspace_dust_policy_matches_the_valuations(tmp_path) -> None:
    """Two folds of one ledger under two dust policies would give the workspace
    and the valuation two different position lists."""
    from fmis.valuation import VALUATION_DUST_POLICY

    assert DUST_POLICY.thresholds == VALUATION_DUST_POLICY.thresholds == ()
