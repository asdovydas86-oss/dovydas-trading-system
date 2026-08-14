"""The value types: what they refuse, and what they compute at read time.

Every refusal below is a shape that would be *representable* without the guard
and *wrong* with it — a flat line, a signed quantity, a status attached to an
unmeasurable value. A constructor that accepted any of them would push the
failure to the first surface that rendered it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from portfolio_risk_helpers import (
    ETH,
    ETH_MARKET,
    EUR,
    EUR_MARKET,
    EVEDEX,
    EVEDEX_MARKET,
    EVEDEX_PERP,
    btc,
    line,
    mark,
    usdt,
)
from trade_domain_helpers import ACCOUNT, AT, BTC, MARKET, USDT

from fmis.accounts import Book
from fmis.money import Money, Quantity
from fmis.portfolio_risk import (
    UNCLASSIFIED,
    ClassificationMap,
    ExposureDimension,
    ExposureEntry,
    ExposureLine,
    ExposureSource,
    PendingCommitment,
    direction_of,
    unclassified_map,
)
from fmis.positions import PositionDirection
from fmis.provenance import Absent, ValueOrigin
from fmis.records import DomainValidationError
from fmis.snapshotting import TradeDirection


# -- ExposureLine -----------------------------------------------------------


def test_a_flat_line_is_not_exposure() -> None:
    with pytest.raises(DomainValidationError, match="flat line is not exposure"):
        line(direction=PositionDirection.FLAT)


@pytest.mark.parametrize("amount", ["0", "-0.5"])
def test_a_signed_or_zero_quantity_is_refused(amount: str) -> None:
    with pytest.raises(DomainValidationError, match="positive magnitude"):
        line(quantity=Quantity(Decimal(amount), BTC))


def test_a_quantity_in_the_wrong_asset_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="base asset"):
        line(quantity=Quantity(Decimal("1"), ETH))


def test_a_held_line_is_measured_and_a_proposed_line_is_asserted() -> None:
    """A surface that rendered both the same way would be a lie of omission."""
    assert line().origin is ValueOrigin.MEASURED
    assert line(source=ExposureSource.PROPOSED).origin is ValueOrigin.ASSERTED


def test_a_line_names_its_venue_and_mode_from_the_market() -> None:
    """Venue is an identifier on a `MarketId`, never a field this package owns."""
    perp = line(market=EVEDEX_PERP)
    assert perp.venue == EVEDEX
    assert perp.mode.value == "perpetual"


def test_the_scope_triple_includes_the_book() -> None:
    """Books never share capacity: the same market in two books is two
    positions, and a scope without the book would merge them."""
    assert line().scope == (ACCOUNT.value, MARKET.value, "swing")
    assert line(book=Book.INVESTING).scope != line().scope


def test_a_line_has_no_single_group_key() -> None:
    with pytest.raises(DomainValidationError, match="several of the owner"):
        line().key_on(ExposureDimension.GROUP)


def test_every_other_axis_reads_a_key_off_the_line() -> None:
    only = line()
    assert only.key_on(ExposureDimension.ACCOUNT) == ACCOUNT.value
    assert only.key_on(ExposureDimension.VENUE) == "binance"
    assert only.key_on(ExposureDimension.BOOK) == "swing"
    assert only.key_on(ExposureDimension.INSTRUMENT) == "binance:BTCUSDT:spot"
    assert only.key_on(ExposureDimension.SYMBOL) == "BTCUSDT"
    assert only.key_on(ExposureDimension.DIRECTION) == "long"


def test_notional_is_unsigned_and_signed_notional_carries_the_direction() -> None:
    assert line().notional(USDT) == usdt("30500")
    assert line().signed_notional(USDT) == usdt("30500")
    short = line(direction=PositionDirection.SHORT, stop=Decimal("61600"))
    assert short.notional(USDT) == usdt("30500")
    assert short.signed_notional(USDT) == usdt("-30500")


def test_a_mark_in_another_currency_is_absent_rather_than_converted() -> None:
    foreign = line(mark=mark("55000", quote=EUR))
    assert isinstance(foreign.notional(USDT), Absent)
    assert "EUR" in foreign.notional(USDT).reason


def test_cost_basis_is_quantity_times_entry() -> None:
    assert line().cost_basis(USDT) == usdt("30000")


def test_cost_basis_is_absent_without_an_entry() -> None:
    assert isinstance(line(entry=Absent("nothing acquired")).cost_basis(USDT), Absent)


def test_capital_at_risk_names_which_input_is_missing() -> None:
    assert "no stop" in line(stop=Absent("no plan")).capital_at_risk(USDT).reason
    assert "no entry price" in line(entry=Absent("none")).capital_at_risk(USDT).reason


def test_capital_at_risk_in_a_foreign_quote_is_absent() -> None:
    foreign = line(
        market=EUR_MARKET, entry=Decimal("54000"), stop=Decimal("52000")
    )
    assert isinstance(foreign.capital_at_risk(USDT), Absent)


def test_with_quantity_preserves_everything_but_the_size() -> None:
    resized = line().with_quantity(btc("0.25"))
    assert resized.quantity == btc("0.25")
    assert resized.entry == line().entry
    assert resized.stop == line().stop
    assert resized.mark == line().mark


def test_a_line_serializes_and_has_no_decoder() -> None:
    payload = line().to_payload()
    assert payload["market"]["venue"] == "binance"
    assert payload["entry"] == {"value": "60000"}
    assert not hasattr(ExposureLine, "from_payload")


def test_an_absent_field_serializes_as_a_tagged_reason() -> None:
    payload = line(stop=Absent("no plan")).to_payload()
    assert payload["stop"]["absent"]["reason"] == "no plan"


# -- direction_of -----------------------------------------------------------


def test_the_two_directional_members_map_across() -> None:
    assert direction_of(TradeDirection.LONG) is PositionDirection.LONG
    assert direction_of(TradeDirection.SHORT) is PositionDirection.SHORT


def test_no_trade_has_no_position_direction() -> None:
    """Mapping it to FLAT would make a declined idea indistinguishable from a
    closed position."""
    with pytest.raises(DomainValidationError, match="decision not to act"):
        direction_of(TradeDirection.NO_TRADE)


# -- ExposureEntry / PendingCommitment --------------------------------------


def test_an_entry_with_no_lines_is_refused() -> None:
    with pytest.raises(DomainValidationError):
        ExposureEntry(
            key="binance", gross=usdt("0"), net=usdt("0"), open_risk=usdt("0"), line_count=0
        )


def test_a_pending_commitment_carries_the_stop_and_no_size() -> None:
    """`TradePlan` states no intended size, and this record does not invent one."""
    pending = PendingCommitment(
        plan_id="trade_plan-x-20260812-abc",
        market=MARKET,
        book=Book.SWING,
        direction=TradeDirection.LONG,
        stop=Decimal("58400"),
        committed_at=AT(10),
    )
    assert pending.stop == Decimal("58400")
    assert not hasattr(pending, "quantity")
    assert not hasattr(pending, "capital")


# -- ClassificationMap ------------------------------------------------------


def test_the_map_returns_the_owners_groups_sorted_and_deduplicated() -> None:
    mapping = ClassificationMap.of("v1", {"BTC": ["l1", "btc_beta", "l1"]})
    assert mapping.groups_for(BTC) == ("btc_beta", "l1")


def test_an_unnamed_asset_is_absent_rather_than_unclassified() -> None:
    """*"We have not classified this"* and *"this is classified"* are different
    facts, and a caller that cannot tell them apart reports an unclassified
    portfolio as a diversified one."""
    groups = ClassificationMap.of("v1", {"BTC": ["l1"]}).groups_for(ETH)
    assert isinstance(groups, Absent)
    assert "v1" in groups.reason


def test_an_empty_map_classifies_nothing_and_still_has_a_version() -> None:
    empty = unclassified_map("no-classification-v1")
    assert empty.is_empty
    assert empty.version == "no-classification-v1"
    assert isinstance(empty.groups_for(BTC), Absent)


def test_an_asset_may_belong_to_several_groups() -> None:
    mapping = ClassificationMap.of("v1", {"ETH": ["l1", "defi", "staking"]})
    assert len(mapping.groups_for(ETH)) == 3
    assert mapping.multi_group_assets((ETH,)) == ("ETH",)
    assert mapping.multi_group_assets((BTC,)) == ()


def test_an_asset_in_one_group_is_not_reported_as_overlapping() -> None:
    mapping = ClassificationMap.of("v1", {"BTC": ["l1"]})
    assert mapping.multi_group_assets((BTC,)) == ()


def test_assigning_the_unclassified_word_is_refused() -> None:
    """Otherwise *"not classified"* and *"classified as not classified"* become
    one bucket."""
    with pytest.raises(DomainValidationError, match="not a group"):
        ClassificationMap.of("v1", {"BTC": [UNCLASSIFIED]})


def test_an_asset_with_no_groups_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="listed with no group"):
        ClassificationMap.of("v1", {"BTC": []})


def test_an_asset_assigned_twice_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="assigned twice"):
        ClassificationMap(
            version="v1",
            assignments=((BTC, ("l1",)), (BTC, ("defi",))),
        )


def test_the_map_is_asserted_and_lists_every_group_it_names() -> None:
    mapping = ClassificationMap.of("v1", {"BTC": ["l1"], "ETH": ["l1", "defi"]})
    assert mapping.origin is ValueOrigin.ASSERTED
    assert mapping.groups == ("defi", "l1")


def test_the_map_serializes_its_version_with_it() -> None:
    payload = ClassificationMap.of("v9", {"BTC": ["l1"]}).to_payload()
    assert payload["version"] == "v9"
    assert payload["assignments"] == [{"asset": "BTC", "groups": ["l1"]}]


def test_two_maps_with_the_same_content_are_equal_and_ordering_is_stable() -> None:
    first = ClassificationMap.of("v1", {"ETH": ["defi"], "BTC": ["l1"]})
    second = ClassificationMap.of("v1", {"BTC": ["l1"], "ETH": ["defi"]})
    assert first == second


# -- read-time branches reached only through a hand-built state -------------


def test_a_state_reports_which_axis_it_was_not_broken_down_by() -> None:
    """`build_state` always builds all eight, but `PortfolioState` is a public
    constructor and a caller may build a narrower one. Asking it for a missing
    axis is an absence with the axis named, not a crash."""
    from fmis.portfolio_risk import PortfolioState
    from portfolio_risk_helpers import PORTFOLIO_ID, usdt

    narrow = PortfolioState(
        portfolio_id=PORTFOLIO_ID,
        base_currency="USDT",  # coerced from text
        as_of=AT(12),
        books_covered=(Book.SWING,),
        lines=(),
        pending=(),
        breakdowns=(),
        equity=usdt("1"),
        cash=usdt("1"),
        gross_exposure=usdt("0"),
        net_exposure=usdt("0"),
        long_exposure=usdt("0"),
        short_exposure=usdt("0"),
        open_risk=usdt("0"),
        deployed_capital=usdt("0"),
        reserved_capital=usdt("0"),
    )
    assert narrow.base_currency == USDT
    missing = narrow.breakdown(ExposureDimension.VENUE)
    assert isinstance(missing, Absent)
    assert "not broken down by venue" in missing.reason


def test_a_share_is_absent_when_the_portfolio_total_is_unknown() -> None:
    """The bucket is measurable and the whole is not, so the ratio is not."""
    from fmis.portfolio_risk import ExposureBreakdown, ExposureEntry
    from portfolio_risk_helpers import usdt

    breakdown = ExposureBreakdown(
        dimension=ExposureDimension.VENUE,
        entries=(
            ExposureEntry(
                key="somewhere",
                gross=usdt("100"),
                net=usdt("100"),
                open_risk=usdt("10"),
                line_count=1,
            ),
        ),
        total_gross=Absent("one holding is unmarked"),
        total_open_risk=Absent("one position has no stop"),
    )
    for share in (breakdown.gross_share("somewhere"), breakdown.risk_share("somewhere")):
        assert isinstance(share, Absent)
        assert "portfolio's total" in share.reason


def test_an_absent_money_figure_serializes_as_a_tagged_reason() -> None:
    """The `Absent` arm of the state's payload encoder."""
    from portfolio_risk_helpers import line, state

    payload = state(line(mark=Absent("no price source"))).to_payload()
    assert "absent" in payload["gross_exposure"]
    assert "no price source" in payload["gross_exposure"]["absent"]["reason"]


def test_a_malformed_assignment_pair_is_refused() -> None:
    """A one- or three-element tuple is not an `(asset, groups)` pair."""
    with pytest.raises(TypeError, match="AssetCode, groups"):
        ClassificationMap(version="v1", assignments=((BTC, ("l1",), "extra"),))
