"""Rendering: what the page must always say, and what it must never say.

Three properties carry most of these tests. **Absence prints its reason**, so a
blank line can never be read as a zero. **Arithmetic prints beside its result**,
so the owner can check a figure rather than trust it. And **the page never
truncates a record id**, because a truncated id is one the owner copies and
cannot look up.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from persistence_helpers import write_request
from trade_capture_helpers import capture_store, closed, note_request, recorded
from trade_domain_helpers import AT, BTC, trade_plan

from fmis.money import Quantity
from fmis.persistence import TradingStore
from fmis.trade_capture import (
    CAPTURE_DUST_POLICY,
    CAPTURE_LIMITATIONS,
    TradeFilters,
    append_note,
    list_trades,
    load_trade,
    render_listing,
    render_outcome,
    render_trade,
)

WIDTH = 78


@pytest.fixture()
def store(tmp_path: Path) -> TradingStore:
    return capture_store(tmp_path)


def _page(store: TradingStore, plan_id: str, *, at=AT(12)) -> str:
    return render_trade(load_trade(store, plan_id, dust=CAPTURE_DUST_POLICY, at=at))


# --------------------------------------------------------------------------
# Shape.
# --------------------------------------------------------------------------


def test_every_section_appears_on_a_recorded_trade(store: TradingStore) -> None:
    page = _page(store, recorded(store, thesis="a reason").plan_id)
    for heading in (
        "RECORDED TRADE",
        "COMMITMENT",
        "FILLS",
        "POSITION",
        "JOURNAL",
        "WARNINGS",
        "LIMITATIONS",
    ):
        assert heading in page


def test_no_line_is_wider_than_the_page(store: TradingStore) -> None:
    outcome = recorded(store, thesis="a" * 200, note="b" * 200)
    page = _page(store, outcome.plan_id)
    assert max(len(line) for line in page.splitlines()) <= WIDTH


def test_a_listing_line_is_never_wider_than_the_page(store: TradingStore) -> None:
    recorded(store)
    text = render_listing(list_trades(store, dust=CAPTURE_DUST_POLICY, at=AT(12)))
    assert max(len(line) for line in text.splitlines()) <= WIDTH


def test_a_record_id_is_wrapped_rather_than_truncated(store: TradingStore) -> None:
    outcome = recorded(store)
    page = _page(store, outcome.plan_id)
    assert "..." not in page
    assert outcome.plan_id.replace("", "")
    joined = "".join(line.strip() for line in page.splitlines())
    assert outcome.plan_id in joined


def test_the_page_prints_no_colour_and_no_control_characters(
    store: TradingStore,
) -> None:
    page = _page(store, recorded(store).plan_id)
    assert "\x1b" not in page
    assert "\t" not in page


# --------------------------------------------------------------------------
# The commitment.
# --------------------------------------------------------------------------


def test_the_stop_and_the_targets_are_printed_exactly(store: TradingStore) -> None:
    page = _page(
        store, recorded(store, targets=(Decimal("64000"), Decimal("68000"))).plan_id
    )
    assert "stop             58400" in page
    assert "64000, 68000" in page


def test_a_commitment_with_no_target_prints_a_dash_rather_than_nothing(
    store: TradingStore,
) -> None:
    page = _page(store, recorded(store, targets=()).plan_id)
    assert "targets          -" in page


def test_an_absent_link_prints_the_reason_it_is_absent(store: TradingStore) -> None:
    page = _page(store, recorded(store).plan_id)
    assert "this plan was not proposed" in page
    assert "no market context was frozen" in page
    assert "no setup type was named" in page


def test_a_setup_type_prints_its_vocabulary_and_generation(
    store: TradingStore,
) -> None:
    page = _page(store, recorded(store, setup_type="trend_continuation").plan_id)
    assert "setup_type:trend_continuation (taxonomy v1)" in page


def test_an_analysis_citation_is_printed_in_full(store: TradingStore) -> None:
    record_id = "workspace-BTCUSDT-20260812T090000Z-0123456789abcdef"
    page = _page(store, recorded(store, analysis_record_ids=(record_id,)).plan_id)
    assert record_id in "".join(line.strip() for line in page.splitlines())


# --------------------------------------------------------------------------
# The arithmetic.
# --------------------------------------------------------------------------


def test_capital_at_risk_prints_the_multiplication_beside_the_answer(
    store: TradingStore,
) -> None:
    page = _page(store, recorded(store).plan_id)
    assert "capital at risk  800 USDT" in page
    assert "(|60000 − 58400| × 0.5)" in page


def test_the_risk_reward_pair_prints_the_division(store: TradingStore) -> None:
    page = _page(store, recorded(store).plan_id)
    assert "risk / reward    2.5" in page
    assert "(4000 ÷ 1600)" in page


def test_the_average_entry_prints_the_division_it_came_from(
    store: TradingStore,
) -> None:
    page = _page(store, recorded(store).plan_id)
    assert "(30000 ÷ 0.5)" in page


def test_gross_and_net_realized_are_both_printed(store: TradingStore) -> None:
    plan_id = recorded(store).plan_id
    closed(store, plan_id)
    page = _page(store, plan_id, at=AT(10, day=14))
    assert "realized gross   1900 USDT" in page
    assert "realized net     1869 USDT" in page


def test_the_fold_and_the_dust_policy_are_named_on_the_page(
    store: TradingStore,
) -> None:
    page = _page(store, recorded(store).plan_id)
    assert "position-fold-v1" in page
    assert "fmits-trade-capture-exact-zero v1" in page


# --------------------------------------------------------------------------
# Absence.
# --------------------------------------------------------------------------


def test_a_commitment_with_no_fill_says_so_in_words(store: TradingStore) -> None:
    plan = trade_plan()
    store.plans.create(plan, request=write_request())
    page = _page(store, plan.plan_id)
    assert "Nothing has filled against this commitment" in page
    assert "PLANNED" in page


def test_an_empty_journal_prints_the_command_that_fills_it(
    store: TradingStore,
) -> None:
    page = _page(store, recorded(store).plan_id)
    assert "fmits trade note" in page


def test_a_journal_entry_prints_its_kind_its_title_and_its_body(
    store: TradingStore,
) -> None:
    plan_id = recorded(store, thesis="the weekly retest held").plan_id
    page = _page(store, plan_id)
    assert "idea" in page
    assert "the weekly retest held" in page


def test_an_exit_reason_prints_as_a_counted_tag(store: TradingStore) -> None:
    plan_id = recorded(store).plan_id
    closed(store, plan_id, reason="target_reached")
    page = _page(store, plan_id, at=AT(10, day=14))
    assert "tag exit_reason:target_reached [owner, counted]" in page


def test_no_warnings_prints_none_rather_than_an_empty_section(
    store: TradingStore,
) -> None:
    plan_id = recorded(store, thesis="a reason").plan_id
    page = _page(store, plan_id)
    assert "WARNINGS" in page
    assert " none" in page


def test_every_invariant_limitation_prints_once(store: TradingStore) -> None:
    page = _page(store, recorded(store).plan_id)
    for code, _ in CAPTURE_LIMITATIONS:
        assert page.count(f"{code} ") == 1


# --------------------------------------------------------------------------
# The listing.
# --------------------------------------------------------------------------


def test_an_empty_listing_says_an_empty_list_is_not_a_flat_book(
    store: TradingStore,
) -> None:
    text = render_listing(list_trades(store, dust=CAPTURE_DUST_POLICY, at=AT(12)))
    assert "does not mean nothing is held" in text


def test_a_listing_states_its_filters_and_what_they_excluded(
    store: TradingStore,
) -> None:
    recorded(store)
    text = render_listing(
        list_trades(
            store,
            dust=CAPTURE_DUST_POLICY,
            at=AT(12),
            filters=TradeFilters(symbol="ETHUSDT"),
        )
    )
    assert "symbol=ETHUSDT" in text
    assert "0 of 1 recorded (1 excluded" in text


def test_a_listing_with_no_filter_says_none(store: TradingStore) -> None:
    recorded(store)
    text = render_listing(list_trades(store, dust=CAPTURE_DUST_POLICY, at=AT(12)))
    assert "filters          none" in text


def test_a_listing_states_that_it_is_not_a_ranking(store: TradingStore) -> None:
    recorded(store)
    text = render_listing(list_trades(store, dust=CAPTURE_DUST_POLICY, at=AT(12)))
    assert "not a ranking" in text


def test_a_row_carries_the_symbol_the_direction_and_the_status(
    store: TradingStore,
) -> None:
    recorded(store)
    text = render_listing(list_trades(store, dust=CAPTURE_DUST_POLICY, at=AT(12)))
    assert "BTCUSDT" in text
    assert "long" in text
    assert "OPEN" in text


# --------------------------------------------------------------------------
# The receipt.
# --------------------------------------------------------------------------


def test_a_receipt_names_each_record_and_where_it_landed(
    store: TradingStore,
) -> None:
    text = render_outcome(recorded(store, thesis="a reason"))
    assert "RECORDED" in text
    assert "trade_plan       created" in text
    assert "ledger/trade/2026.jsonl" in text


def _flowed(text: str) -> str:
    """The page with its wrapping removed, for asserting on a whole sentence."""
    return " ".join(line.strip() for line in text.splitlines())


def test_a_re_entry_says_nothing_was_written(store: TradingStore) -> None:
    recorded(store)
    text = render_outcome(recorded(store))
    assert "already stored, unchanged" in text
    assert "no second trade exists" in _flowed(text)


def test_a_first_entry_does_not_claim_to_be_a_re_entry(
    store: TradingStore,
) -> None:
    assert "no second trade exists" not in _flowed(render_outcome(recorded(store)))


def test_a_note_receipt_names_only_the_entry_it_wrote(
    store: TradingStore,
) -> None:
    plan_id = recorded(store).plan_id
    text = render_outcome(append_note(store, note_request(plan_id)))
    assert "NOTED" in text
    assert text.count("journal_entry    created") == 1


def test_a_close_receipt_reports_the_closed_position(store: TradingStore) -> None:
    plan_id = recorded(store).plan_id
    text = render_outcome(closed(store, plan_id))
    assert "CLOSED" in text
    assert "realized net     1869 USDT" in text


# --------------------------------------------------------------------------
# Refusals.
# --------------------------------------------------------------------------


def test_rendering_refuses_something_that_is_not_a_view() -> None:
    with pytest.raises(TypeError, match="must be a TradeView"):
        render_trade("a trade")  # type: ignore[arg-type]


def test_rendering_refuses_something_that_is_not_a_listing() -> None:
    with pytest.raises(TypeError, match="must be a TradeListing"):
        render_listing("a listing")  # type: ignore[arg-type]


def test_rendering_refuses_something_that_is_not_an_outcome() -> None:
    with pytest.raises(TypeError, match="must be a CaptureOutcome"):
        render_outcome("an outcome")  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# What the page must never claim.
# --------------------------------------------------------------------------


def test_the_page_never_calls_realized_profit_a_taxable_gain(
    store: TradingStore,
) -> None:
    plan_id = recorded(store).plan_id
    closed(store, plan_id)
    page = _page(store, plan_id, at=AT(10, day=14))
    assert "is not a taxable gain" in _flowed(page)


def test_the_page_states_that_the_fold_is_this_commitments_own(
    store: TradingStore,
) -> None:
    page = _page(store, recorded(store).plan_id)
    assert "fold this commitment's own fills" in _flowed(page)


def test_the_page_never_offers_a_probability_or_a_score(
    store: TradingStore,
) -> None:
    page = _page(store, recorded(store, thesis="a reason").plan_id).lower()
    for forbidden in ("probability:", "score", "grade", "rating", "recommend"):
        assert forbidden not in page


def test_the_page_says_fmits_places_no_order(store: TradingStore) -> None:
    page = _page(store, recorded(store).plan_id)
    assert "places no order" in _flowed(page)


def test_a_reduced_position_warning_reaches_the_page(store: TradingStore) -> None:
    plan_id = recorded(store).plan_id
    closed(store, plan_id, quantity=Quantity(Decimal("0.2"), BTC))
    page = _page(store, plan_id, at=AT(10, day=14))
    assert "TC-W5" in page
    assert "0.3 BTC is open" in _flowed(page)


def test_a_position_with_no_risk_distance_prints_the_reason_not_a_number(
    store: TradingStore,
) -> None:
    """The drifted-entry case, rendered. A blank line here would read as no risk."""
    from trade_domain_helpers import trade

    outcome = recorded(store, stop=Decimal("59000"), targets=(Decimal("64000"),))
    store.trades.create(
        trade(
            occurred_at=AT(13),
            price=Decimal("57000"),
            quantity=Quantity(Decimal("2"), BTC),
            plan_id=outcome.plan_id,
        ),
        request=write_request(),
    )
    page = _page(store, outcome.plan_id, at=AT(14))
    assert "capital at risk: the stop 59000 is not below the entry" in _flowed(page)
    assert "risk / reward: the stop 59000 is not below the entry" in _flowed(page)
