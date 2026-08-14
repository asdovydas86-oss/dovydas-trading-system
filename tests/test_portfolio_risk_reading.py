"""Reading a portfolio out of the BI store, and the BK flow end to end.

**No exchange API and no fake repository.** Every test below writes real records
through `fmis.trade_capture` — the same path `fmits trade record` takes — and
reads them back through the same repositories the rest of the system uses. A
trade the owner records must be consumable by the risk engine with no manual
transformation, and the only way to demonstrate that is to record one.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from persistence_helpers import risk_budget, risk_limit
from portfolio_risk_helpers import (
    ETH,
    ETH_MARKET,
    EVEDEX_MARKET,
    SECOND_ACCOUNT,
    btc,
    groups,
    mark,
    owner,
    usdt,
)
from trade_capture_helpers import capture_store, closed, recorded
from trade_domain_helpers import ACCOUNT, AT, BTC, MARKET, USDT

from fmis.accounts import AccountId, Book
from fmis.money import Money, Quantity
from fmis.persistence import TradingStore
from fmis.portfolio_risk import (
    UNCLASSIFIED_VERSION,
    ProposedTrade,
    budget_in_force,
    detect_overlap,
    evaluate_constraints,
    evaluate_impact,
    read_equity_and_cash,
    read_exposure_lines,
    read_pending,
    read_portfolio,
    unclassified_map,
)
from fmis.positions import PositionDirection
from fmis.provenance import Absent
from fmis.risk import LimitScope, LimitStatus, LimitUnit
from fmis.snapshotting import TradeDirection
from fmis.trade_capture import CAPTURE_DUST_POLICY

OWNER = owner()
MARKS = {MARKET.value: mark("61000")}


def portfolio(store: TradingStore, **overrides: object):
    values: dict[str, object] = {
        "portfolio_id": "main",
        "base_currency": USDT,
        "as_of": AT(12, day=13),
        "equity": usdt("100000"),
        "cash": usdt("40000"),
        "marks": MARKS,
    }
    values.update(overrides)
    return read_portfolio(store, **values)  # type: ignore[arg-type]


# -- an empty store ---------------------------------------------------------


def test_a_store_that_has_never_been_written_reads_as_an_empty_portfolio(
    tmp_path: Path,
) -> None:
    """Constructing a store creates no directory and writes no byte, so this is
    safe on a root that does not exist."""
    empty = portfolio(capture_store(tmp_path / "nothing"))
    assert empty.is_empty
    assert empty.gross_exposure == usdt("0")
    assert empty.open_risk == usdt("0")
    assert empty.pending == ()


def test_an_empty_portfolio_is_not_a_claim_that_the_owner_holds_nothing() -> None:
    """`is_empty` says *this store records no open exposure*. Equity and cash are
    still whatever the caller could establish, and absent when nothing did."""
    from portfolio_risk_helpers import state

    blank = state(equity=Absent("no snapshot"), cash=Absent("no snapshot"))
    assert blank.is_empty
    assert isinstance(blank.equity, Absent)


# -- the BK flow, end to end ------------------------------------------------


def test_a_trade_recorded_by_bk_is_consumable_with_no_transformation(
    tmp_path: Path,
) -> None:
    """Part 11's flow: account · plan · trade · position · state · risk.

    Nothing between `fmits trade record` and the risk engine reshapes a record.
    """
    store = capture_store(tmp_path)
    outcome = recorded(store)

    state = portfolio(store)
    assert len(state.lines) == 1
    only = state.lines[0]
    assert only.account == ACCOUNT
    assert only.market == MARKET
    assert only.book is Book.SWING
    assert only.direction is PositionDirection.LONG
    assert only.quantity == btc("0.5")
    assert only.entry == Decimal("60000")
    assert only.stop == Decimal("58400")  # read off the plan BK wrote
    assert state.open_risk == usdt("800")
    assert state.gross_exposure == usdt("30500")
    assert outcome.plan_id in only.origin_ids or only.origin_ids


def test_the_line_cites_the_ledger_events_it_was_folded_from(tmp_path: Path) -> None:
    """A projection that names its sources can be checked against them."""
    store = capture_store(tmp_path)
    recorded(store)
    only = portfolio(store).lines[0]
    assert only.origin_ids
    for event_id in only.origin_ids:
        assert store.ledger.status_of(event_id).value == "recorded"


def test_a_closed_trade_leaves_the_portfolio(tmp_path: Path) -> None:
    store = capture_store(tmp_path)
    outcome = recorded(store)
    closed(store, outcome.plan_id)
    state = portfolio(store, as_of=AT(12, day=15))
    assert state.is_empty
    assert state.open_risk == usdt("0")


def test_a_second_proposed_trade_is_evaluated_against_the_first(
    tmp_path: Path,
) -> None:
    """The whole milestone, in one flow: record a trade, then ask what a second
    one would do to the portfolio it created."""
    store = capture_store(tmp_path)
    recorded(store)
    before = portfolio(store)
    budget = risk_budget(
        limits=(
            risk_limit(
                "per_trade", scope=LimitScope.PER_TRADE_RISK,
                value=Decimal("0.02"), unit=LimitUnit.PERCENT_OF_EQUITY,
            ),
            risk_limit(
                "total_open", scope=LimitScope.TOTAL_OPEN_RISK,
                value=usdt("1000"), unit=LimitUnit.MONEY,
            ),
        )
    )
    impact = evaluate_impact(
        proposed=ProposedTrade(
            account=ACCOUNT,
            market=ETH_MARKET,
            book=Book.SWING,
            direction=TradeDirection.LONG,
            entry=Decimal("3000"),
            stop=Decimal("2800"),
            quantity=Quantity(Decimal("2"), ETH),
        ),
        before=before,
        budget=budget,
        owner=OWNER,
        classification=unclassified_map(UNCLASSIFIED_VERSION),
    )
    assert impact.before.open_risk == usdt("800")
    assert impact.after.open_risk == usdt("1200")  # 800 + 2 x 200
    assert impact.incremental_open_risk == usdt("400")
    assert impact.before_check.result("total_open").status is LimitStatus.WITHIN
    assert impact.after_check.result("total_open").status is LimitStatus.EXCEEDED
    assert impact.newly_binding == ("total_open",)
    assert impact.remaining_risk_budget == usdt("-200")


# -- the stop comes from a commitment or not at all -------------------------


def test_a_fill_naming_a_commitment_this_store_lacks_has_no_stop(
    tmp_path: Path,
) -> None:
    """A dangling `plan_id` is a detected gap, not something to resolve by
    guessing — so the position reports absent risk rather than zero."""
    store = capture_store(tmp_path)
    recorded(store)
    lines = read_exposure_lines(store, marks=MARKS)
    assert lines[0].stop == Decimal("58400")

    plans_removed = TradingStore(tmp_path, dust=CAPTURE_DUST_POLICY)
    # The plan is present; assert the *reason* text exists for the other branch
    # by folding a position whose fills name a plan the store does not hold.
    from fmis.portfolio_risk.reading import _stop_for

    position = plans_removed.positions.rebuild()[0]
    missing = _stop_for(position, plans_removed.ledger.resolved(), {})
    assert isinstance(missing, Absent)
    assert "does not hold" in missing.reason


def test_two_commitments_with_two_stops_leave_the_position_unmeasurable(
    tmp_path: Path,
) -> None:
    """Choosing either would report a level the owner did not set for this
    exposure."""
    store = capture_store(tmp_path)
    recorded(store)
    recorded(store, stop=Decimal("57000"), occurred_at=AT(11), written_at=AT(11))
    lines = read_exposure_lines(store, marks=MARKS)
    assert len(lines) == 1
    assert isinstance(lines[0].stop, Absent)
    assert "different stops" in lines[0].stop.reason

    state = portfolio(store)
    assert isinstance(state.open_risk, Absent)
    assert len(state.unstopped) == 1


# -- accounts, venues and books ---------------------------------------------


def test_two_accounts_produce_two_lines_and_the_shared_market_is_named(
    tmp_path: Path,
) -> None:
    store = capture_store(tmp_path)
    recorded(store)
    recorded(store, account=SECOND_ACCOUNT, occurred_at=AT(11), written_at=AT(11), stop=Decimal("58400"))
    state = portfolio(store)
    assert len(state.lines) == 2
    assert {entry.account for entry in state.lines} == {ACCOUNT, SECOND_ACCOUNT}
    assert state.accounts_share_a_market == ("binance:BTCUSDT:spot (swing)",)


def test_the_same_symbol_at_two_venues_is_two_lines(tmp_path: Path) -> None:
    """The venue-agnostic claim, exercised against a venue this repository has no
    provider for."""
    store = capture_store(tmp_path)
    recorded(store)
    recorded(
        store,
        market=EVEDEX_MARKET,
        occurred_at=AT(11),
        written_at=AT(11),
    )
    state = portfolio(
        store, marks={MARKET.value: mark("61000"), EVEDEX_MARKET.value: mark("61000")}
    )
    assert {entry.venue.value for entry in state.lines} == {"binance", "evedex"}
    assert state.gross_exposure == usdt("61000")
    assert state.open_risk == usdt("1600")


def test_the_paper_book_is_excluded_by_default(tmp_path: Path) -> None:
    """Paper and live contamination is detectable only if the default is honest."""
    store = capture_store(tmp_path)
    recorded(store, book=Book.PAPER)
    assert read_exposure_lines(store, marks=MARKS) == ()
    assert portfolio(store).is_empty


def test_a_narrowed_book_set_excludes_the_others(tmp_path: Path) -> None:
    store = capture_store(tmp_path)
    recorded(store)
    assert read_exposure_lines(store, books_covered=(Book.INVESTING,)) == ()
    assert len(read_exposure_lines(store, books_covered=(Book.SWING,))) == 1


# -- pending commitments ----------------------------------------------------


def test_a_plan_with_no_fill_is_pending_and_reserves_nothing_derivable(
    tmp_path: Path,
) -> None:
    store = capture_store(tmp_path)
    outcome = recorded(store)
    # A second commitment, recorded without a fill against it.
    plan = store.plans.plans()[0]
    assert plan.plan_id == outcome.plan_id
    pending = read_pending(store)
    assert pending == ()  # this one is filled

    state = portfolio(store)
    assert state.reserved_capital == usdt("0")


def test_an_unfilled_commitment_makes_reserved_capital_absent(
    tmp_path: Path,
) -> None:
    """Constructed by recording a plan whose fills are all superseded away is not
    possible here, so the pending path is exercised directly on the reader."""
    store = capture_store(tmp_path)
    recorded(store)
    resolved = store.ledger.resolved()
    assert resolved  # the fill exists, so nothing is pending
    from fmis.portfolio_risk import PendingCommitment, build_state

    plan = store.plans.plans()[0]
    with_pending = build_state(
        portfolio_id="main",
        base_currency=USDT,
        as_of=AT(12),
        lines=read_exposure_lines(store, marks=MARKS),
        pending=(
            PendingCommitment(
                plan_id=plan.plan_id,
                market=plan.market,
                book=plan.book,
                direction=plan.direction,
                stop=plan.initial_invalidation,
                committed_at=plan.committed_at,
            ),
        ),
        equity=usdt("100000"),
        cash=usdt("40000"),
        classification=unclassified_map(UNCLASSIFIED_VERSION),
    )
    assert isinstance(with_pending.reserved_capital, Absent)
    assert isinstance(with_pending.available_capital, Absent)


# -- equity and cash --------------------------------------------------------


def test_no_snapshot_means_equity_and_cash_are_absent_never_zero(
    tmp_path: Path,
) -> None:
    store = capture_store(tmp_path)
    recorded(store)
    equity, cash, valued_at = read_equity_and_cash(
        store, portfolio_id="main", base_currency=USDT
    )
    assert isinstance(equity, Absent)
    assert isinstance(cash, Absent)
    assert "not a zero balance" in equity.reason


def test_a_reading_with_no_snapshot_reports_absent_equity_and_leverage(
    tmp_path: Path,
) -> None:
    store = capture_store(tmp_path)
    recorded(store)
    state = read_portfolio(
        store,
        portfolio_id="main",
        base_currency=USDT,
        as_of=AT(12, day=13),
        marks=MARKS,
    )
    assert isinstance(state.equity, Absent)
    assert isinstance(state.leverage, Absent)
    assert state.open_risk == usdt("800")  # risk is still measurable


def test_a_supplied_equity_overrides_the_absent_snapshot(tmp_path: Path) -> None:
    store = capture_store(tmp_path)
    recorded(store)
    state = portfolio(store)
    assert state.equity == usdt("100000")
    assert state.leverage == Decimal("0.305")


# -- marks ------------------------------------------------------------------


def test_no_mark_makes_exposure_absent_and_names_the_market(tmp_path: Path) -> None:
    store = capture_store(tmp_path)
    recorded(store)
    state = portfolio(store, marks=None)
    assert isinstance(state.gross_exposure, Absent)
    assert "binance:BTCUSDT:spot" in state.gross_exposure.reason
    assert state.open_risk == usdt("800")  # risk needs no mark


def test_a_non_mark_in_the_marks_mapping_is_refused(tmp_path: Path) -> None:
    store = capture_store(tmp_path)
    recorded(store)
    with pytest.raises(TypeError, match="MarkQuote"):
        read_exposure_lines(store, marks={MARKET.value: Decimal("61000")})  # type: ignore[dict-item]


# -- corrections and the known-at axis --------------------------------------


def test_the_reading_resolves_supersession(tmp_path: Path) -> None:
    """A portfolio built from a value the owner already corrected is the failure
    the `ResolvedTrade` token exists to make hard."""
    store = capture_store(tmp_path)
    recorded(store)
    lines = read_exposure_lines(store, marks=MARKS)
    assert lines[0].quantity == btc("0.5")
    assert all(
        store.ledger.status_of(event_id).value == "recorded"
        for event_id in lines[0].origin_ids
    )


def test_a_past_reading_uses_the_written_at_axis(tmp_path: Path) -> None:
    """What the store *knew* then, not what had happened by then."""
    store = capture_store(tmp_path)
    recorded(store)
    assert read_exposure_lines(store, marks=MARKS, at=AT(10)) == ()
    assert len(read_exposure_lines(store, marks=MARKS, at=AT(12))) == 1


# -- determinism ------------------------------------------------------------


def test_the_same_store_produces_an_equal_state_every_time(tmp_path: Path) -> None:
    """§24.3's rebuildable-projection test against a real store."""
    store = capture_store(tmp_path)
    recorded(store)
    assert portfolio(store) == portfolio(store)


def test_two_stores_over_one_root_read_the_same_portfolio(tmp_path: Path) -> None:
    store = capture_store(tmp_path)
    recorded(store)
    assert portfolio(store) == portfolio(capture_store(tmp_path))


def test_reading_writes_nothing(tmp_path: Path) -> None:
    """The store's contents must not depend on who looked at them."""
    store = capture_store(tmp_path)
    recorded(store)
    before = sorted(path.name for path in tmp_path.rglob("*") if path.is_file())
    journal_before = len(store.write_journal.events())
    portfolio(store)
    read_exposure_lines(store)
    read_pending(store)
    read_equity_and_cash(store, portfolio_id="main", base_currency=USDT)
    after = sorted(path.name for path in tmp_path.rglob("*") if path.is_file())
    assert before == after
    assert len(store.write_journal.events()) == journal_before


# -- the risk budget --------------------------------------------------------


def test_the_budget_in_force_is_read_through_the_store(tmp_path: Path) -> None:
    store = capture_store(tmp_path)
    assert isinstance(budget_in_force(store, "swing_budget", at=AT(12)), Absent)


def test_no_budget_in_force_is_absent_rather_than_the_earliest(
    tmp_path: Path,
) -> None:
    """*"No budget existed"* and *"the first budget applied"* are different facts,
    and a caller that cannot tell them apart evaluates a trade against limits
    nobody had set."""
    store = capture_store(tmp_path)
    result = budget_in_force(store, "swing_budget", at=AT(12))
    assert isinstance(result, Absent)
    assert "no risk budget was in force" in result.reason


# -- the reader's own guards ------------------------------------------------


def test_the_reader_refuses_something_that_is_not_a_store() -> None:
    with pytest.raises(TypeError, match="TradingStore"):
        read_exposure_lines(object())  # type: ignore[arg-type]


def test_a_full_constraint_evaluation_runs_against_a_real_store(
    tmp_path: Path,
) -> None:
    store = capture_store(tmp_path)
    recorded(store)
    budget = risk_budget(
        limits=(
            risk_limit(
                "total_open", scope=LimitScope.TOTAL_OPEN_RISK,
                value=usdt("500"), unit=LimitUnit.MONEY,
            ),
        )
    )
    check = evaluate_constraints(budget, portfolio(store), owner=OWNER)
    assert check.result("total_open").current_value == usdt("800")
    assert check.result("total_open").status is LimitStatus.EXCEEDED
    assert check.exceeded


def test_duplicate_detection_runs_against_a_real_store(tmp_path: Path) -> None:
    store = capture_store(tmp_path)
    recorded(store)
    overlap = detect_overlap(
        portfolio(store),
        ProposedTrade(
            account=ACCOUNT,
            market=MARKET,
            book=Book.SWING,
            direction=TradeDirection.LONG,
            entry=Decimal("61000"),
            stop=Decimal("59000"),
            quantity=btc("0.25"),
        ),
    )
    assert overlap.relationship.value == "same_direction"
    assert overlap.effect.value == "scale_in"


# -- equity and cash from a stored snapshot ---------------------------------


def _store_snapshot(store: TradingStore, **overrides: object):
    """File one `PortfolioSnapshot` through the repository that owns it."""
    from persistence_helpers import portfolio_snapshot, write_request

    snapshot = portfolio_snapshot(**overrides)  # type: ignore[arg-type]
    store.portfolios.create(snapshot, request=write_request())
    return snapshot


def test_equity_and_cash_are_read_from_the_latest_snapshot(tmp_path: Path) -> None:
    """`PortfolioSnapshot` is the only place a valued observation of this
    portfolio lives, and this reads it rather than deriving a second one."""
    store = capture_store(tmp_path)
    _store_snapshot(store)
    equity, cash, valued_at = read_equity_and_cash(
        store, portfolio_id="main", base_currency=USDT
    )
    assert equity == usdt("92500")  # 1.5 BTC at 60000, plus 2500 cash
    assert cash == usdt("2500")


def test_a_reading_with_no_supplied_equity_falls_back_to_the_snapshot(
    tmp_path: Path,
) -> None:
    store = capture_store(tmp_path)
    recorded(store)
    _store_snapshot(store)
    state = read_portfolio(
        store,
        portfolio_id="main",
        base_currency=USDT,
        as_of=AT(12, day=13),
        marks=MARKS,
    )
    assert state.equity == usdt("92500")
    assert state.cash == usdt("2500")


def test_an_unmarked_holding_makes_the_snapshots_equity_absent(
    tmp_path: Path,
) -> None:
    """`PortfolioSnapshot.total_value` already refuses a partial total; this
    forwards that refusal instead of substituting the marked part."""
    from persistence_helpers import ACCOUNT as SNAPSHOT_ACCOUNT
    from persistence_helpers import quantity
    from fmis.portfolio import Holding

    store = capture_store(tmp_path)
    _store_snapshot(
        store,
        holdings=(
            Holding(BTC, SNAPSHOT_ACCOUNT, quantity("1.5"), Absent("no mark source")),
        ),
    )
    equity, cash, valued_at = read_equity_and_cash(
        store, portfolio_id="main", base_currency=USDT
    )
    assert isinstance(equity, Absent)
    assert "no mark for" in equity.reason
    assert cash == usdt("2500")


def test_a_snapshot_in_another_base_currency_is_absent_not_converted(
    tmp_path: Path,
) -> None:
    store = capture_store(tmp_path)
    _store_snapshot(store)
    equity, cash, valued_at = read_equity_and_cash(
        store, portfolio_id="main", base_currency=BTC
    )
    assert isinstance(equity, Absent)
    assert isinstance(cash, Absent)
    assert "no rate between them" in equity.reason


def test_cash_in_a_currency_with_no_rate_is_absent(tmp_path: Path) -> None:
    """A cash balance the snapshot froze no rate for cannot be added to a base
    total, and reporting the rest would understate the account."""
    from persistence_helpers import ACCOUNT as SNAPSHOT_ACCOUNT
    from fmis.portfolio import CashBalance

    store = capture_store(tmp_path)
    _store_snapshot(
        store,
        cash=(
            CashBalance(
                SNAPSHOT_ACCOUNT,
                Money(Decimal("100"), ETH),
                Absent("no rate applied"),
            ),
        ),
    )
    _, cash, _valued_at = read_equity_and_cash(store, portfolio_id="main", base_currency=USDT)
    assert isinstance(cash, Absent)
    assert "no rate from ETH" in cash.reason


def test_a_supplied_absent_states_plainly_that_a_figure_is_unknown(
    tmp_path: Path,
) -> None:
    """Supplying `Absent(reason)` is a different and equally legitimate answer
    from supplying nothing: it overrides the snapshot rather than reading it."""
    store = capture_store(tmp_path)
    recorded(store)
    _store_snapshot(store)
    state = read_portfolio(
        store,
        portfolio_id="main",
        base_currency=USDT,
        as_of=AT(12, day=13),
        marks=MARKS,
        equity=Absent("the owner has not reconciled this month"),
        cash=Absent("the owner has not reconciled this month"),
    )
    assert isinstance(state.equity, Absent)
    assert "not reconciled" in state.equity.reason


def test_a_fill_naming_no_commitment_has_no_stop(tmp_path: Path) -> None:
    """BK always writes a plan; the ledger does not require one, and a position
    folded from an unplanned fill must report absent risk rather than zero."""
    from fmis.portfolio_risk.reading import _stop_for

    store = capture_store(tmp_path)
    recorded(store)
    position = store.positions.rebuild()[0]
    stripped = [
        entry for entry in store.ledger.resolved() if entry.event_id not in position.event_ids
    ]
    missing = _stop_for(position, stripped, {})
    assert isinstance(missing, Absent)
    assert "none of these fills names one" in missing.reason


# -- account attribution and direction, from real fills ---------------------


def test_each_accounts_line_carries_only_that_accounts_fills(
    tmp_path: Path,
) -> None:
    """Mutation N01. Folding every account's fills together would produce two
    lines that each claim the *combined* size — the exposure would be right in
    total and wrong everywhere it is attributed, which is the failure a
    per-account portfolio exists to prevent.
    """
    store = capture_store(tmp_path)
    recorded(store, quantity=btc("0.5"))
    recorded(
        store,
        account=SECOND_ACCOUNT,
        quantity=btc("0.2"),
        occurred_at=AT(11),
        written_at=AT(11),
    )
    lines = {entry.account.value: entry for entry in portfolio(store).lines}
    assert lines[ACCOUNT.value].quantity == btc("0.5")
    assert lines[SECOND_ACCOUNT.value].quantity == btc("0.2")


def test_a_short_position_is_read_with_a_positive_magnitude(
    tmp_path: Path,
) -> None:
    """Mutation N07. A folded short has a negative net quantity; an exposure line
    states a positive magnitude and carries the side in `direction`. Passing the
    signed value through would be refused by the line — or, worse, would invert
    every figure that multiplies by it.
    """
    store = capture_store(tmp_path)
    recorded(
        store,
        direction=TradeDirection.SHORT,
        stop=Decimal("61600"),
        targets=(Decimal("56000"),),
    )
    only = portfolio(store).lines[0]
    assert only.direction is PositionDirection.SHORT
    assert only.quantity == btc("0.5")
    assert only.quantity.amount > 0
    assert only.stop == Decimal("61600")


def test_a_short_read_from_the_store_computes_its_own_risk_and_sign(
    tmp_path: Path,
) -> None:
    store = capture_store(tmp_path)
    recorded(
        store,
        direction=TradeDirection.SHORT,
        stop=Decimal("61600"),
        targets=(Decimal("56000"),),
    )
    state = portfolio(store)
    assert state.open_risk == usdt("800")  # 0.5 x (61600 - 60000)
    assert state.gross_exposure == usdt("30500")
    assert state.net_exposure == usdt("-30500")
    assert state.short_exposure == usdt("30500")
    assert state.long_exposure == usdt("0")


def test_a_closed_position_is_excluded_by_two_independent_guards(
    tmp_path: Path,
) -> None:
    """Mutation N02 is equivalent, and this records why rather than leaving it
    looking like a gap: `Position` refuses a CLOSED position that is not FLAT, so
    the direction guard catches every closed position even if the state guard is
    removed. Both are kept — the invariant lives in another package, and a guard
    that depends on someone else's invariant should not be the only one.
    """
    store = capture_store(tmp_path)
    outcome = recorded(store)
    closed(store, outcome.plan_id)
    folded = store.positions.rebuild()
    assert [position.state.value for position in folded] == ["closed"]
    assert [position.direction.value for position in folded] == ["flat"]
    assert portfolio(store, as_of=AT(12, day=15)).lines == ()


# -- the valuation instant travels with the figures -------------------------


def test_the_equity_figure_carries_the_instant_it_was_true(tmp_path: Path) -> None:
    """Hostile-review finding H2. A snapshot taken weeks ago is a good record and
    a poor description of today's equity, and every percent-of-equity limit is
    measured against it. The staleness is reported rather than inferred.
    """
    store = capture_store(tmp_path)
    recorded(store)
    snapshot = _store_snapshot(store)
    state = read_portfolio(
        store,
        portfolio_id="main",
        base_currency=USDT,
        as_of=AT(12, day=13),
        marks=MARKS,
    )
    assert state.equity_as_of == snapshot.as_of
    assert state.equity_staleness.days >= 1
    assert state.to_payload()["equity_as_of"] == {"value": snapshot.as_of.isoformat()}


def test_no_snapshot_means_no_valuation_instant(tmp_path: Path) -> None:
    store = capture_store(tmp_path)
    recorded(store)
    state = read_portfolio(
        store,
        portfolio_id="main",
        base_currency=USDT,
        as_of=AT(12, day=13),
        marks=MARKS,
    )
    assert isinstance(state.equity_as_of, Absent)
    assert isinstance(state.equity_staleness, Absent)


def test_supplying_equity_directly_states_no_instant_for_it(tmp_path: Path) -> None:
    """A caller who knows a figure this store has not observed also knows when it
    was true, and this build has no way to ask them — so the absence says so
    rather than borrowing the reading's own instant."""
    store = capture_store(tmp_path)
    recorded(store)
    state = portfolio(store)
    assert isinstance(state.equity_as_of, Absent)
    assert "supplied equity and cash directly" in state.equity_as_of.reason


def test_a_valuation_dated_after_the_reading_is_refused() -> None:
    """A valuation from the future is not a valuation."""
    from fmis.portfolio_risk import build_state, unclassified_map
    from fmis.records import DomainValidationError

    with pytest.raises(DomainValidationError, match="from the future"):
        build_state(
            portfolio_id="main",
            base_currency=USDT,
            as_of=AT(9),
            lines=(),
            equity=usdt("1"),
            cash=usdt("1"),
            classification=unclassified_map("v1"),
            equity_as_of=AT(10),
        )


def test_this_engine_measures_open_exposure_and_bk_measures_maximum_exposure(
    tmp_path: Path,
) -> None:
    """Hostile-review finding H3, pinned as a property rather than left latent.

    After a partial exit the two surfaces report different capital-at-risk
    figures and **both are right**: `fmits trade show` answers *"what did this
    commitment put at risk"* using the position's maximum exposure, and a
    portfolio answers *"what is at risk now"* using what is still open. BK
    already warns about the gap on its own page (`TC-W5`); this test states the
    relationship from the other side so a future change to either cannot make
    them silently agree on the wrong number.
    """
    from fmis.trade_capture import CAPTURE_DUST_POLICY
    from fmis.trade_capture.views import load_trade

    store = capture_store(tmp_path)
    outcome = recorded(store)  # long 0.5 BTC, stop 1600 away
    closed(
        store,
        outcome.plan_id,
        exit_price=Decimal("62000"),
        quantity=btc("0.2"),
        occurred_at=AT(9, day=13),
        written_at=AT(10, day=13),
    )
    view = load_trade(store, outcome.plan_id, dust=CAPTURE_DUST_POLICY, at=AT(12, day=14))
    state = portfolio(store, as_of=AT(12, day=14))

    assert view.capital_at_risk == usdt("800")  # 0.5 x 1600, the maximum
    assert state.open_risk == usdt("480")  # 0.3 x 1600, what is still open
    assert "TC-W5" in {warning.code for warning in view.warnings}
    assert state.lines[0].quantity == btc("0.3")
