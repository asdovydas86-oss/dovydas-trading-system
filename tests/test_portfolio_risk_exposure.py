"""Portfolio state and exposure aggregation, across every shape the brief names.

Empty · one long · one short · long and short · the same symbol twice · the same
symbol on two venues · two accounts · two quote currencies · missing equity ·
missing stop · missing mark. Each is a separate test with its own arithmetic,
because the failure mode this suite exists to catch is an aggregate that is
*plausible* rather than one that is obviously broken.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from portfolio_risk_helpers import (
    ETH,
    ETH_MARKET,
    EUR,
    EUR_MARKET,
    EVEDEX_MARKET,
    EVEDEX_PERP,
    PORTFOLIO_ID,
    SECOND_ACCOUNT,
    btc,
    groups,
    line,
    mark,
    no_groups,
    state,
    usdt,
)
from trade_domain_helpers import ACCOUNT, AT, BTC, MARKET, USDT

from fmis.accounts import Book
from fmis.money import Money, Quantity
from fmis.portfolio_risk import (
    DEFAULT_BOOKS_COVERED,
    ExposureBreakdown,
    ExposureDimension,
    ExposureEntry,
    ExposureLine,
    ExposureSource,
    PendingCommitment,
    breakdown_by,
    breakdown_by_group,
    build_state,
    markets_held_in_several_accounts,
    sum_or_absent,
)
from fmis.positions import PositionDirection
from fmis.provenance import Absent, ValueOrigin
from fmis.records import DomainValidationError
from fmis.snapshotting import TradeDirection

LONG = PositionDirection.LONG
SHORT = PositionDirection.SHORT


def short_line(**overrides: object) -> ExposureLine:
    values: dict[str, object] = {
        "direction": SHORT,
        "entry": Decimal("60000"),
        "stop": Decimal("61600"),
    }
    values.update(overrides)
    return line(**values)  # type: ignore[arg-type]


# -- the empty portfolio ----------------------------------------------------


def test_an_empty_portfolio_reports_zero_exposure_and_says_it_is_empty() -> None:
    """Zero exposure over zero positions is a *fact*, not a fabrication: nothing
    was omitted from the sum, because there was nothing to omit."""
    empty = state()
    assert empty.is_empty
    assert empty.gross_exposure == usdt("0")
    assert empty.net_exposure == usdt("0")
    assert empty.long_exposure == usdt("0")
    assert empty.short_exposure == usdt("0")
    assert empty.open_risk == usdt("0")
    assert empty.open_position_count == 0


def test_an_empty_portfolio_still_reports_every_axis() -> None:
    empty = state()
    for dimension in ExposureDimension:
        breakdown = empty.breakdown(dimension)
        assert not isinstance(breakdown, Absent), dimension
        assert breakdown.entries == ()


# -- one position -----------------------------------------------------------


def test_one_long_computes_gross_net_long_short_and_risk() -> None:
    only = state(line())
    assert only.gross_exposure == usdt("30500")  # 0.5 x 61000
    assert only.net_exposure == usdt("30500")
    assert only.long_exposure == usdt("30500")
    assert only.short_exposure == usdt("0")
    assert only.open_risk == usdt("800")  # 0.5 x (60000 - 58400)


def test_one_short_is_gross_positive_and_net_negative() -> None:
    """The inversion test: a sign error on either side swaps these two."""
    only = state(short_line())
    assert only.gross_exposure == usdt("30500")
    assert only.net_exposure == usdt("-30500")
    assert only.long_exposure == usdt("0")
    assert only.short_exposure == usdt("30500")
    assert only.open_risk == usdt("800")  # 0.5 x (61600 - 60000)


def test_a_long_and_a_short_have_a_gross_of_two_and_a_net_of_zero() -> None:
    """The single most important aggregate distinction in the whole engine: a
    hedged book is not an empty book, and a page showing only `net` would say it
    was."""
    hedged = state(line(), short_line(market=ETH_MARKET, quantity=Quantity(Decimal("0.5"), ETH)))
    assert hedged.gross_exposure == usdt("61000")
    assert hedged.net_exposure == usdt("0")
    assert hedged.long_exposure == usdt("30500")
    assert hedged.short_exposure == usdt("30500")


def test_long_and_short_exposure_are_summed_and_never_recovered_by_subtraction() -> None:
    """gross = long + short and net = long − short both hold, and neither is how
    either is computed — asserted so a refactor to a subtraction is visible."""
    hedged = state(line(), short_line(market=ETH_MARKET, quantity=Quantity(Decimal("0.5"), ETH)))
    assert hedged.long_exposure + hedged.short_exposure == hedged.gross_exposure
    assert hedged.long_exposure - hedged.short_exposure == hedged.net_exposure


# -- duplicates, venues and accounts ----------------------------------------


def test_the_same_symbol_twice_in_one_account_aggregates_on_every_axis() -> None:
    doubled = state(line(), line(book=Book.INVESTING))
    assert doubled.gross_exposure == usdt("61000")
    symbols = doubled.breakdown(ExposureDimension.SYMBOL)
    assert symbols.keys == ("BTCUSDT",)
    assert symbols.entry("BTCUSDT").line_count == 2
    books = doubled.breakdown(ExposureDimension.BOOK)
    assert set(books.keys) == {"swing", "investing"}


def test_the_same_symbol_on_two_venues_is_two_instruments_and_one_symbol() -> None:
    """Counterparty risk follows the venue; price risk does not. Collapsing the
    two axes into one would hide whichever concentration the owner cares about."""
    spread = state(line(), line(market=EVEDEX_MARKET))
    instruments = spread.breakdown(ExposureDimension.INSTRUMENT)
    assert set(instruments.keys) == {
        "binance:BTCUSDT:spot",
        "evedex:BTCUSDT:spot",
    }
    symbols = spread.breakdown(ExposureDimension.SYMBOL)
    assert symbols.keys == ("BTCUSDT",)
    assert symbols.entry("BTCUSDT").gross == usdt("61000")


def test_a_long_at_one_venue_and_a_short_at_another_do_not_net_to_flat() -> None:
    """Two venues, two counterparties. Netting them would report a flat book that
    can lose money on both legs."""
    spread = state(line(), short_line(market=EVEDEX_MARKET))
    assert spread.gross_exposure == usdt("61000")
    venues = spread.breakdown(ExposureDimension.VENUE)
    assert venues.entry("binance").net == usdt("30500")
    assert venues.entry("evedex").net == usdt("-30500")


def test_two_accounts_are_two_buckets_and_the_shared_market_is_named() -> None:
    split = state(line(), line(account=SECOND_ACCOUNT))
    accounts = split.breakdown(ExposureDimension.ACCOUNT)
    assert set(accounts.keys) == {ACCOUNT.value, SECOND_ACCOUNT.value}
    assert split.accounts_share_a_market == ("binance:BTCUSDT:spot (swing)",)


def test_a_market_in_one_account_is_not_reported_as_shared() -> None:
    assert state(line()).accounts_share_a_market == ()


def test_markets_held_in_several_accounts_is_scoped_per_book() -> None:
    """The same market in two accounts but two books is two positions by design,
    not a per-account/book-wide disagreement."""
    assert (
        markets_held_in_several_accounts(
            (line(), line(account=SECOND_ACCOUNT, book=Book.INVESTING))
        )
        == ()
    )


# -- missing inputs never become zero ---------------------------------------


def test_an_unmarked_position_makes_every_exposure_figure_absent_and_names_it() -> None:
    blind = state(line(mark=Absent("no price source")))
    for figure in (
        blind.gross_exposure,
        blind.net_exposure,
        blind.long_exposure,
    ):
        assert isinstance(figure, Absent)
        assert "binance:BTCUSDT:spot" in figure.reason
    assert blind.unmarked == blind.lines


def test_an_unmarked_position_does_not_shrink_the_total_silently() -> None:
    """One marked and one unmarked: the total is absent, never the marked half."""
    partial = state(line(), line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), mark=Absent("none")))
    assert isinstance(partial.gross_exposure, Absent)
    assert partial.gross_exposure != usdt("30500")


def test_a_position_with_no_stop_makes_open_risk_absent_rather_than_smaller() -> None:
    """The most dangerous position in a portfolio is the one with no stop. A zero
    would file it as the safest."""
    unstopped = state(line(), line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), stop=Absent("no plan")))
    assert isinstance(unstopped.open_risk, Absent)
    assert len(unstopped.unstopped) == 1
    assert unstopped.open_risk.reason != ""


def test_a_position_with_broken_geometry_reports_the_reason_not_a_number() -> None:
    """An average entry that drifted to the stop's side after an add. Real, and
    `abs()` would report it as a well-sized trade."""
    drifted = state(line(entry=Decimal("58000")))
    assert isinstance(drifted.open_risk, Absent)
    assert "not below the entry" in drifted.open_risk.reason


def test_missing_equity_is_absent_and_leverage_says_so() -> None:
    blind = state(line(), equity=Absent("no snapshot has been taken"))
    assert isinstance(blind.equity, Absent)
    assert isinstance(blind.leverage, Absent)
    assert "no snapshot" in blind.leverage.reason


def test_zero_equity_makes_leverage_undefined_rather_than_large() -> None:
    assert isinstance(state(line(), equity=usdt("0")).leverage, Absent)


def test_leverage_divides_gross_by_equity() -> None:
    assert state(line()).leverage == Decimal("0.305")  # 30500 / 100000


def test_a_market_quoted_in_another_currency_is_absent_not_converted() -> None:
    """Silently treating EUR as USDT is the cheapest way to misstate a portfolio."""
    foreign = state(
        line(market=EUR_MARKET, mark=mark("55000", quote=EUR), entry=Decimal("54000"), stop=Decimal("52000"))
    )
    assert isinstance(foreign.gross_exposure, Absent)
    assert "EUR" in foreign.gross_exposure.reason
    assert isinstance(foreign.open_risk, Absent)


# -- capital figures --------------------------------------------------------


def test_deployed_capital_is_the_cost_basis_of_unleveraged_long_exposure() -> None:
    assert state(line()).deployed_capital == usdt("30000")  # 0.5 x 60000


def test_deployed_capital_is_absent_for_a_short_and_names_margin() -> None:
    deployed = state(short_line()).deployed_capital
    assert isinstance(deployed, Absent)
    assert "margin" in deployed.reason


def test_deployed_capital_is_absent_for_a_perpetual_and_names_margin() -> None:
    deployed = state(line(market=EVEDEX_PERP)).deployed_capital
    assert isinstance(deployed, Absent)
    assert "perpetual" in deployed.reason


def test_reserved_capital_is_zero_only_when_nothing_is_pending() -> None:
    assert state(line()).reserved_capital == usdt("0")


def test_reserved_capital_is_absent_when_a_commitment_is_pending() -> None:
    """A `TradePlan` states no intended size, so what it would consume is not
    derivable. Reserving zero would be a fabrication."""
    pending = PendingCommitment(
        plan_id="trade_plan-x-20260812-abc",
        market=MARKET,
        book=Book.SWING,
        direction=TradeDirection.LONG,
        stop=Decimal("58400"),
        committed_at=AT(10),
    )
    with_plan = state(line(), pending=(pending,))
    assert isinstance(with_plan.reserved_capital, Absent)
    assert "no intended size" in with_plan.reserved_capital.reason
    assert with_plan.pending_count == 1


def test_available_capital_is_cash_minus_reserved() -> None:
    assert state(line(), cash=usdt("40000")).available_capital == usdt("40000")


def test_available_capital_is_absent_when_cash_is() -> None:
    blind = state(line(), cash=Absent("no snapshot"))
    assert isinstance(blind.available_capital, Absent)


def test_available_capital_is_absent_when_reserved_is() -> None:
    pending = PendingCommitment(
        plan_id="trade_plan-x-20260812-abc",
        market=MARKET,
        book=Book.SWING,
        direction=TradeDirection.LONG,
        stop=Decimal("58400"),
        committed_at=AT(10),
    )
    assert isinstance(state(line(), pending=(pending,)).available_capital, Absent)


# -- shares -----------------------------------------------------------------


def test_a_share_divides_the_bucket_by_the_portfolio_and_not_the_reverse() -> None:
    """A numerator/denominator swap turns 0.25 into 4."""
    mixed = state(
        line(quantity=btc("0.25")),
        line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), mark=mark("45750")),
    )
    symbols = mixed.breakdown(ExposureDimension.SYMBOL)
    assert symbols.total_gross == usdt("61000")
    assert symbols.gross_share("BTCUSDT") == Decimal("0.25")
    assert symbols.gross_share("ETHUSDT") == Decimal("0.75")


def test_the_shares_on_a_disjoint_axis_sum_to_one() -> None:
    mixed = state(line(), line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), mark=mark("3000")))
    venues = mixed.breakdown(ExposureDimension.INSTRUMENT)
    assert sum(venues.gross_share(key) for key in venues.keys) == Decimal(1)


def test_a_risk_share_divides_by_open_risk_and_not_by_gross() -> None:
    mixed = state(line(), line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), entry=Decimal("3000"), stop=Decimal("2200"), mark=mark("3000")))
    symbols = mixed.breakdown(ExposureDimension.SYMBOL)
    assert symbols.total_open_risk == usdt("1600")  # 800 + 800
    assert symbols.risk_share("BTCUSDT") == Decimal("0.5")


def test_a_share_of_an_unknown_key_is_absent_with_the_axis_named() -> None:
    share = state(line()).breakdown(ExposureDimension.VENUE).gross_share("kraken")
    assert isinstance(share, Absent)
    assert "venue" in share.reason


def test_a_share_of_a_zero_total_is_undefined_rather_than_zero() -> None:
    share = state().breakdown(ExposureDimension.VENUE).gross_share("binance")
    assert isinstance(share, Absent)


def test_a_share_is_absent_when_the_bucket_cannot_be_measured() -> None:
    blind = state(line(mark=Absent("none")))
    share = blind.breakdown(ExposureDimension.VENUE).gross_share("binance")
    assert isinstance(share, Absent)


# -- group exposure ---------------------------------------------------------


def test_group_exposure_reads_the_owners_map_at_its_stated_version() -> None:
    classified = state(
        line(),
        line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), mark=mark("3000")),
        classification=groups("owner-v3", BTC=["l1"], ETH=["l1", "defi"]),
    )
    breakdown = classified.breakdown(ExposureDimension.GROUP)
    assert breakdown.classification_version == "owner-v3"
    assert set(breakdown.keys) == {"l1", "defi"}
    assert breakdown.entry("l1").gross == usdt("33500")  # 30500 + 3000
    assert breakdown.entry("defi").gross == usdt("3000")


def test_group_buckets_overlap_and_the_overlap_is_named() -> None:
    classified = state(
        line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), mark=mark("3000")),
        classification=groups("owner-v3", ETH=["l1", "defi"]),
    )
    breakdown = classified.breakdown(ExposureDimension.GROUP)
    assert breakdown.overlapping_keys == ("ETH",)
    total = sum(
        breakdown.entry(key).gross.amount for key in breakdown.keys
    )
    assert total > breakdown.total_gross.amount


def test_an_unnamed_asset_is_unclassified_and_never_guessed() -> None:
    classified = state(line(), classification=groups("owner-v3", ETH=["l1"]))
    breakdown = classified.breakdown(ExposureDimension.GROUP)
    assert breakdown.keys == ("unclassified",)
    assert breakdown.entry("unclassified").gross == usdt("30500")


def test_group_exposure_is_policy_derived_and_every_other_axis_is_measured() -> None:
    filled = state(line())
    assert filled.breakdown(ExposureDimension.GROUP).origin is ValueOrigin.POLICY_DERIVED
    assert filled.breakdown(ExposureDimension.VENUE).origin is ValueOrigin.MEASURED


def test_a_group_breakdown_without_a_version_is_refused() -> None:
    """Two versions produce visibly different allocations rather than silently
    contradictory ones — which requires the version to be on the object."""
    with pytest.raises(DomainValidationError, match="classification version"):
        ExposureBreakdown(
            dimension=ExposureDimension.GROUP,
            entries=(),
            total_gross=usdt("0"),
            total_open_risk=usdt("0"),
        )


def test_only_a_group_breakdown_may_declare_overlapping_keys() -> None:
    """Every other axis partitions the portfolio; a line falls in exactly one
    bucket, so an overlap there would mean a line was counted twice."""
    with pytest.raises(DomainValidationError, match="disjoint"):
        ExposureBreakdown(
            dimension=ExposureDimension.VENUE,
            entries=(),
            total_gross=usdt("0"),
            total_open_risk=usdt("0"),
            overlapping_keys=("BTC",),
        )


def test_breakdown_by_refuses_the_group_axis() -> None:
    with pytest.raises(ValueError, match="breakdown_by_group"):
        breakdown_by(ExposureDimension.GROUP, (line(),), base=USDT)


# -- determinism and invariants ---------------------------------------------


def test_the_same_inputs_produce_an_equal_state_every_time() -> None:
    """The §24.3 rebuildable-projection test, as an assertion."""
    lines = (line(), short_line(market=ETH_MARKET, quantity=Quantity(Decimal("2"), ETH)))
    assert state(*lines) == state(*lines)


def test_the_state_is_measured_and_reports_the_risk_basis() -> None:
    filled = state(line())
    assert filled.origin is ValueOrigin.MEASURED
    assert "pre-cost" in filled.risk_basis


def test_a_line_in_an_uncovered_book_is_refused() -> None:
    """An aggregate states which books it covers and holds nothing else."""
    with pytest.raises(DomainValidationError, match="books"):
        build_state(
            portfolio_id=PORTFOLIO_ID,
            base_currency=USDT,
            as_of=AT(12),
            lines=(line(book=Book.PAPER),),
            equity=usdt("1"),
            cash=usdt("1"),
            classification=no_groups(),
        )


def test_paper_is_excluded_from_the_default_books() -> None:
    """Paper and live contamination is detectable only if the default is honest."""
    assert Book.PAPER not in DEFAULT_BOOKS_COVERED
    assert set(DEFAULT_BOOKS_COVERED) == {Book.INVESTING, Book.SWING, Book.DAY}


def test_a_money_figure_in_the_wrong_currency_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="base currency"):
        build_state(
            portfolio_id=PORTFOLIO_ID,
            base_currency=USDT,
            as_of=AT(12),
            lines=(),
            equity=Money(Decimal("1"), BTC),
            cash=usdt("1"),
            classification=no_groups(),
        )


def test_an_axis_is_never_broken_down_twice() -> None:
    dimensions = [b.dimension for b in state(line()).breakdowns]
    assert len(set(dimensions)) == len(dimensions)
    assert set(dimensions) == set(ExposureDimension)


def test_sum_or_absent_names_every_missing_contributor() -> None:
    total = sum_or_absent(
        (usdt("1"), Absent("no mark for A"), Absent("no mark for B")),
        asset=USDT,
        subject="gross",
    )
    assert isinstance(total, Absent)
    assert "no mark for A" in total.reason
    assert "no mark for B" in total.reason


def test_sum_or_absent_over_nothing_is_an_explicit_zero() -> None:
    assert sum_or_absent((), asset=USDT, subject="gross") == usdt("0")


def test_the_state_serializes_without_a_decoder() -> None:
    payload = state(line()).to_payload()
    assert payload["gross_exposure"] == {"value": {"amount": "30500", "asset": "USDT"}}
    assert "risk_basis" in payload
    from fmis.portfolio_risk import PortfolioState

    assert not hasattr(PortfolioState, "from_payload")


def test_leverage_is_absent_when_gross_exposure_is() -> None:
    """An unmarked portfolio has no leverage figure — not a small one."""
    blind = state(line(mark=Absent("no price source")))
    assert isinstance(blind.leverage, Absent)
    assert "gross exposure is not known" in blind.leverage.reason


def test_a_line_and_a_state_both_publish_the_same_risk_basis() -> None:
    """The caveat travels with the figure wherever it is read from."""
    assert line().risk_basis == state(line()).risk_basis


def test_held_and_proposed_lines_are_separable_on_the_state() -> None:
    from fmis.portfolio_risk import ExposureSource

    mixed = state(line(), line(book=Book.DAY, source=ExposureSource.PROPOSED))
    assert len(mixed.held_lines) == 1
    assert len(mixed.proposed_lines) == 1


def test_a_repeated_book_in_the_cover_set_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="must not repeat a book"):
        build_state(
            portfolio_id=PORTFOLIO_ID,
            base_currency=USDT,
            as_of=AT(12),
            lines=(),
            equity=usdt("1"),
            cash=usdt("1"),
            classification=no_groups(),
            books_covered=(Book.SWING, Book.SWING),
        )


def test_a_base_currency_given_as_text_is_accepted() -> None:
    assert state(line(), base_currency="USDT").base_currency == USDT


def test_available_capital_subtracts_reserved_rather_than_adding_it() -> None:
    """Mutation N13. Nothing in this build can yet produce a non-zero reserved
    figure — `_reserved` returns zero or `Absent` — so the subtraction is only
    exercised by constructing the state directly. It is pinned here anyway,
    because the day an intended size makes reserved capital derivable, an
    addition would report *more* buying power the more capital is committed.
    """
    from fmis.portfolio_risk import PortfolioState

    committed = PortfolioState(
        portfolio_id=PORTFOLIO_ID,
        base_currency=USDT,
        as_of=AT(12),
        books_covered=DEFAULT_BOOKS_COVERED,
        lines=(),
        pending=(),
        breakdowns=(),
        equity=usdt("100000"),
        cash=usdt("40000"),
        gross_exposure=usdt("0"),
        net_exposure=usdt("0"),
        long_exposure=usdt("0"),
        short_exposure=usdt("0"),
        open_risk=usdt("0"),
        deployed_capital=usdt("0"),
        reserved_capital=usdt("15000"),
    )
    assert committed.available_capital == usdt("25000")
    assert committed.available_capital < committed.cash


def test_a_share_of_a_zero_total_is_undefined_even_when_the_bucket_exists() -> None:
    """Mutation N28. `build_state` cannot produce this shape — a positive
    quantity at a positive mark is never worth zero — but `ExposureBreakdown` is
    a public constructor and a caller may. Falling through to the division would
    raise `DivisionUndefined` inside a portfolio page, which is strictly worse
    than an absence carrying its reason.
    """
    breakdown = ExposureBreakdown(
        dimension=ExposureDimension.VENUE,
        entries=(
            ExposureEntry(
                key="somewhere",
                gross=usdt("0"),
                net=usdt("0"),
                open_risk=usdt("0"),
                line_count=1,
            ),
        ),
        total_gross=usdt("0"),
        total_open_risk=usdt("0"),
    )
    for share in (breakdown.gross_share("somewhere"), breakdown.risk_share("somewhere")):
        assert isinstance(share, Absent)
        assert "undefined rather than zero" in share.reason


# -- base-asset exposure (hostile-review finding H1) ------------------------


def test_the_same_base_asset_under_two_quotes_is_one_asset_and_two_symbols() -> None:
    """Hostile-review finding H1. `BTCUSDT` and `BTCUSDC` are two instruments,
    two symbols and **one bet on BTC**. Reporting only the symbol axis would show
    two 50 % concentrations where the owner has one 100 % position."""
    from portfolio_risk_helpers import BTCUSDC_MARKET, USDC

    spread = state(
        line(),
        line(
            market=BTCUSDC_MARKET,
            mark=mark("61000", quote=USDC),
            entry=Decimal("60000"),
            stop=Decimal("58400"),
        ),
    )
    symbols = spread.breakdown(ExposureDimension.SYMBOL)
    assert set(symbols.keys) == {"BTCUSDT", "BTCUSDC"}

    assets = spread.breakdown(ExposureDimension.ASSET)
    assert assets.keys == ("BTC",)
    assert assets.entry("BTC").line_count == 2

    # The grouping is right and the *money* is honestly absent: valuing a
    # USDC-quoted line in a USDT-based portfolio needs a rate nothing supplied.
    # The axis earns its place by identity, not by arithmetic — which is exactly
    # what duplicate detection needs from it.
    assert isinstance(assets.entry("BTC").gross, Absent)
    assert "no rate to USDT" in assets.entry("BTC").gross.reason


def test_the_asset_axis_separates_genuinely_different_bets() -> None:
    mixed = state(
        line(),
        line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), mark=mark("30500"), entry=Decimal("30000"), stop=Decimal("28000")),
    )
    assets = mixed.breakdown(ExposureDimension.ASSET)
    assert set(assets.keys) == {"BTC", "ETH"}
    assert assets.gross_share("BTC") == Decimal("0.5")


def test_the_asset_axis_spans_venues_as_well_as_quotes() -> None:
    spread = state(line(), line(market=EVEDEX_MARKET))
    assert spread.breakdown(ExposureDimension.ASSET).keys == ("BTC",)
