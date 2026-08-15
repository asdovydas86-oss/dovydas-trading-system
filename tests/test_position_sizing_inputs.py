"""The text boundary: typed flags and scan results become domain values.

**Every conversion here is a place a value can be mis-read**, and putting them in
one tested module rather than in an argparse callback is the difference between
*"the CLI is thin"* as a claim and as a property. The assertions below are about
what is refused as much as what is accepted.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from persistence_helpers import risk_limit
from portfolio_risk_helpers import groups, line, state, usdt
from position_sizing_helpers import budget_with, ceiling, engine, owner
from trade_domain_helpers import ACCOUNT, MARKET

from fmis.accounts import AccountId, Book, MarketMode
from fmis.money import AssetCode
from fmis.position_sizing import (
    APPROVAL_ERRORS,
    DEFAULT_SIZING_POLICY_ID,
    ApprovalResult,
    PositionProposal,
    SizingRefusedError,
    approve_results,
    price_from_text,
    proposal_from_text,
    proposals_from_results,
    scope_from_text,
    sizing_policy_from_text,
)
from fmis.provenance import Absent
from fmis.snapshotting import TradeDirection


# ==========================================================================
# 1. A typed candidate
# ==========================================================================


def typed(**overrides: Any) -> PositionProposal:
    values: dict[str, Any] = {
        "symbol": "BTCUSDT",
        "direction": "long",
        "account": "binance_spot",
        "book": "swing",
        "entry": "60000",
        "stop": "58400",
    }
    values.update(overrides)
    return proposal_from_text(**values)


def test_a_typed_candidate_becomes_the_domains_own_values() -> None:
    built = typed(targets=["64000", "68000"])
    assert built.market == MARKET
    assert built.account == ACCOUNT
    assert built.book is Book.SWING
    assert built.direction is TradeDirection.LONG
    assert built.entry == Decimal("60000")
    assert built.targets == (Decimal("64000"), Decimal("68000"))


def test_a_price_crosses_as_exact_text_and_never_through_a_float() -> None:
    """One pass through a float puts a fifty-five-digit expansion downstream."""
    assert typed(entry="0.1").entry == Decimal("0.1")
    assert price_from_text("0.1", "--entry") == Decimal("0.1")


@pytest.mark.parametrize("raw", ["", "   ", "not-a-number", "nan", "Infinity"])
def test_a_malformed_price_is_refused_by_name(raw: str) -> None:
    with pytest.raises(SizingRefusedError, match="--entry"):
        price_from_text(raw, "--entry")


def test_a_missing_price_names_the_flag_that_would_have_set_it() -> None:
    with pytest.raises(SizingRefusedError, match="--stop is required"):
        typed(stop="")


def test_an_unknown_side_is_a_clean_rejection_and_never_a_default() -> None:
    with pytest.raises(SizingRefusedError, match=r"\['long', 'short'\]"):
        typed(direction="up")


def test_a_decision_not_to_act_is_refused_before_the_domain_sees_it() -> None:
    with pytest.raises(SizingRefusedError, match="commits to a side"):
        typed(direction="no_trade")


@pytest.mark.parametrize(
    "field,value,match",
    [("book", "hodl", "--book"), ("mode", "options", "--mode")],
)
def test_every_closed_vocabulary_refuses_an_unknown_member(
    field: str, value: str, match: str
) -> None:
    with pytest.raises(SizingRefusedError, match=match):
        typed(**{field: value})


def test_the_symbol_split_is_the_capture_packages_and_is_not_guessed() -> None:
    """`BTCU`/`SDT` is a legal reading of the same characters."""
    from fmis.trade_capture import TradeCaptureError

    with pytest.raises(TradeCaptureError, match="does not end in the quote asset"):
        typed(symbol="BTCEUR")
    assert typed(symbol="BTCEUR", quote="EUR").market.quote_asset == AssetCode("EUR")


def test_a_perpetual_is_a_different_market_from_its_spot_pair() -> None:
    assert typed(mode="perpetual").market.mode is MarketMode.PERPETUAL


def test_the_error_tuple_covers_every_layer_a_refusal_can_come_from() -> None:
    from fmis.records import TradeDomainError
    from fmis.trade_capture import TradeCaptureError

    from fmis.position_sizing import PositionSizingError

    assert set(APPROVAL_ERRORS) == {
        PositionSizingError,
        TradeDomainError,
        TradeCaptureError,
    }


# ==========================================================================
# 2. The scope and the policy
# ==========================================================================


def test_an_unnamed_account_stays_unresolved_rather_than_becoming_a_default() -> None:
    account, book = scope_from_text(account=None, book="swing")
    assert account is None
    assert book is Book.SWING


def test_a_named_account_becomes_the_domains_identifier() -> None:
    account, _ = scope_from_text(account="binance_spot", book="day")
    assert account == AccountId("binance_spot")


def test_an_unknown_book_is_refused_at_the_boundary() -> None:
    with pytest.raises(SizingRefusedError, match="--book"):
        scope_from_text(account=None, book="hodl")


def test_a_policy_built_from_no_flags_states_nothing() -> None:
    built = sizing_policy_from_text()
    assert built.policy_id == DEFAULT_SIZING_POLICY_ID
    for value in (
        built.risk_fraction,
        built.max_equity_age,
        built.max_mark_age,
        built.minimum_risk_reward,
    ):
        assert isinstance(value, Absent)


def test_every_absence_names_the_flag_that_would_have_set_it() -> None:
    built = sizing_policy_from_text()
    assert "--risk-fraction" in built.risk_fraction.reason
    assert "--max-equity-age" in built.max_equity_age.reason
    assert "--max-mark-age" in built.max_mark_age.reason
    assert "--min-risk-reward" in built.minimum_risk_reward.reason


def test_a_policy_built_from_flags_carries_them_exactly() -> None:
    built = sizing_policy_from_text(
        risk_fraction="0.01",
        max_equity_age="7d",
        max_mark_age="36h",
        minimum_risk_reward="1.5",
    )
    assert built.risk_fraction == Decimal("0.01")
    assert built.max_equity_age == timedelta(days=7)
    assert built.max_mark_age == timedelta(hours=36)
    assert built.minimum_risk_reward == Decimal("1.5")


@pytest.mark.parametrize("raw", ["90m", "36h", "7d"])
def test_every_supported_duration_suffix_parses(raw: str) -> None:
    assert sizing_policy_from_text(max_mark_age=raw).max_mark_age > timedelta()


@pytest.mark.parametrize("raw", ["4", "", "h", "36w", "abch", "-1h", "0h"])
def test_a_bare_or_malformed_duration_is_refused_rather_than_guessed(raw: str) -> None:
    """`--max-mark-age 4` has several readings and none of them is the right one."""
    with pytest.raises(SizingRefusedError, match="--max-mark-age"):
        sizing_policy_from_text(max_mark_age=raw)


# ==========================================================================
# 3. Scan results become candidates
# ==========================================================================


class _Level:
    def __init__(self, price: float) -> None:
        self.price = price


class _Direction:
    def __init__(self, value: str) -> None:
        self.value = value


class _Assessment:
    """The five fields this boundary reads off a `SetupAssessment`, and no more.

    Hand-built rather than produced by the engine, so a shape the scanner has not
    yet emitted — a directional result with no stop — can be exercised at all.
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        *,
        direction: str | None = "long",
        reference_price: float | None = 60000.0,
        stop: float | None = 58400.0,
        targets: tuple[float, ...] = (64000.0,),
    ) -> None:
        self.symbol = symbol
        self.direction = None if direction is None else _Direction(direction)
        self.reference_price = reference_price
        self.stop = None if stop is None else _Level(stop)
        self.targets = tuple(_Level(price) for price in targets)


class _Result:
    def __init__(self, assessment: Any, symbol: str | None = None) -> None:
        self.assessment = assessment
        self.requested_symbol = symbol or (
            assessment.symbol if assessment is not None else "UNKNOWN"
        )


def test_a_directional_result_becomes_a_candidate() -> None:
    found = proposals_from_results(
        (_Result(_Assessment()),), account=ACCOUNT, book=Book.SWING
    )
    built = found["BTCUSDT"]
    assert built.entry == Decimal("60000")
    assert built.stop == Decimal("58400")
    assert built.targets == (Decimal("64000"),)


def test_a_result_with_no_direction_is_not_a_candidate_at_all() -> None:
    """A `WAIT` falls out of this filter because it carries no side."""
    found = proposals_from_results(
        (_Result(_Assessment(direction=None)),), account=ACCOUNT, book=Book.SWING
    )
    assert found == {}


def test_a_failed_result_is_not_a_candidate_either() -> None:
    found = proposals_from_results(
        (_Result(None, symbol="ADAUSDT"),), account=ACCOUNT, book=Book.SWING
    )
    assert found == {}


def test_a_directional_result_with_no_stop_says_so_rather_than_vanishing() -> None:
    """No stop means no risk denominator, and a dropped row reads as unchecked."""
    found = proposals_from_results(
        (_Result(_Assessment(stop=None)),), account=ACCOUNT, book=Book.SWING
    )
    assert isinstance(found["BTCUSDT"], Absent)
    assert "no risk denominator" in found["BTCUSDT"].reason


def test_a_directional_result_with_no_reference_price_says_so_too() -> None:
    found = proposals_from_results(
        (_Result(_Assessment(reference_price=None)),),
        account=ACCOUNT,
        book=Book.SWING,
    )
    assert "nothing to measure the stop distance from" in found["BTCUSDT"].reason


def test_a_symbol_that_does_not_end_in_the_quote_asset_is_isolated() -> None:
    """One candidate this page cannot scope, not a page that fails."""
    found = proposals_from_results(
        (_Result(_Assessment("BTCEUR")),), account=ACCOUNT, book=Book.SWING
    )
    assert isinstance(found["BTCEUR"], Absent)
    assert "does not end in the quote asset" in found["BTCEUR"].reason


def test_the_float_to_exact_crossing_is_the_repositorys_one_named_function() -> None:
    found = proposals_from_results(
        (_Result(_Assessment(reference_price=61000.5)),),
        account=ACCOUNT,
        book=Book.SWING,
    )
    assert found["BTCUSDT"].entry == Decimal("61000.5")


def test_an_unknown_mode_is_refused_before_any_result_is_read() -> None:
    with pytest.raises(SizingRefusedError, match="--mode"):
        proposals_from_results((), account=ACCOUNT, book=Book.SWING, mode="options")


# ==========================================================================
# 4. Approving a whole scan
# ==========================================================================


def approvals(*results: Any, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "engine": engine(classification=groups(BTC=["l1"])),
        "state": state(line(), equity=usdt("100000")),
        "budget": budget_with(ceiling("0.02")),
        "owner": owner(),
        "account": ACCOUNT,
        "book": Book.SWING,
    }
    values.update(overrides)
    return approve_results(results, **values)


def test_every_directional_candidate_gets_its_own_result() -> None:
    found = approvals(_Result(_Assessment()))
    assert isinstance(found["BTCUSDT"], ApprovalResult)


def test_a_refused_candidate_carries_its_absence_into_the_mapping() -> None:
    found = approvals(_Result(_Assessment(stop=None)))
    assert isinstance(found["BTCUSDT"], Absent)


def test_every_candidate_is_evaluated_against_the_same_before_state() -> None:
    """Not a cumulative allocation: this mapping never claims two both fit."""
    portfolio = state(line(), equity=usdt("100000"))
    found = approvals(
        _Result(_Assessment("BTCUSDT")),
        _Result(_Assessment("ETHUSDT", reference_price=3000.0, stop=2600.0, targets=(3800.0,))),
        state=portfolio,
    )
    assert all(result.state is portfolio for result in found.values())


def test_the_engine_must_be_an_engine() -> None:
    with pytest.raises(TypeError, match="ApprovalEngine"):
        approvals(_Result(_Assessment()), engine=object())


def test_an_empty_scan_produces_an_empty_mapping_rather_than_a_failure() -> None:
    assert approvals() == {}
