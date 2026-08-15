"""`PositionSizer` — the arithmetic, and every way it refuses to produce one.

**The numbers here are checkable by hand and are meant to be.** Equity 100 000,
a fraction of 0.01, a risk distance of 1 600: the allowance is 1 000, the
quantity is 0.625 BTC, and the capital at risk of *that quantity* is 1 000 again.
Every test below either confirms that chain or breaks one link in it deliberately.

The distinction this file exists to pin is between the two ways there is no size:
`REFUSED` — the arithmetic is impossible — and `UNDETERMINED` — an input is not
known. They become a block and an indeterminate approval respectively, and
inferring one from the other would make a portfolio with no recorded equity look
like a portfolio with a transposed stop.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from portfolio_risk_helpers import btc, usdt
from position_sizing_helpers import (
    budget_with,
    ceiling,
    policy,
    proposal,
    sizer,
    total_risk_limit,
)
from trade_domain_helpers import BTC, USDT

from fmis.accounts import MarketId, MarketMode, VenueId
from fmis.money import AssetCode, Money
from fmis.position_sizing import ROUNDING_NOTE, PositionSizer, SizingOutcome
from fmis.provenance import Absent


def size(**kwargs: object) -> object:
    """One sizing call with everything defaulted to the checkable case."""
    values: dict[str, object] = {
        "equity": usdt("100000"),
        "budget": budget_with(),
        "remaining_open_risk": None,
    }
    values.update(kwargs)
    candidate = values.pop("proposal", proposal())
    built = values.pop("sizer", sizer())
    return built.size(candidate, **values)  # type: ignore[union-attr, arg-type]


# ==========================================================================
# 1. The arithmetic
# ==========================================================================


def test_the_size_is_the_allowance_divided_by_the_risk_distance() -> None:
    """1 % of 100 000 = 1 000; 1 000 ÷ 1 600 = 0.625 BTC."""
    result = size()
    assert result.outcome is SizingOutcome.SIZED
    assert result.quantity == btc("0.625")
    assert result.risk_fraction == Decimal("0.01")


def test_the_risk_reported_is_the_risk_of_the_size_that_was_produced() -> None:
    """Recomputed through `capital_at_risk_of`, never carried from the allowance."""
    assert size().money_at_risk == usdt("1000")


def test_the_risk_is_recomputed_even_when_the_division_does_not_terminate() -> None:
    """The case that makes the recomputation observable rather than decorative.

    With a risk distance of 1 600 the allowance and the size's own risk agree
    exactly, so carrying the allowance forward would pass every other test in
    this file. With a distance of 3 the quotient does not terminate, and the
    capital actually at risk of the quantity that was produced is
    `999.9999…` — not the 1 000 the allowance says. The reported figure must be
    the risk of the reported size, or the two disagree the first time anything
    rounds.
    """
    thin = proposal(
        entry=Decimal("60000"), stop=Decimal("59997"), targets=(Decimal("64000"),)
    )
    result = size(proposal=thin)
    assert result.quantity == btc("333.3333333333333333333333333")
    assert result.money_at_risk == usdt("999.9999999999999999999999999")
    assert result.money_at_risk != usdt("1000")


def test_the_exposure_is_the_quantity_at_the_entry_price() -> None:
    assert size().expected_exposure == usdt("37500")


def test_the_planned_ratio_travels_with_the_size_and_is_never_an_input() -> None:
    result = size()
    assert result.expected_r_multiple == Decimal("2.5")
    assert result.planned_risk_reward.risk_distance == Decimal("1600")


def test_a_short_candidate_sizes_identically_on_mirrored_geometry() -> None:
    from fmis.snapshotting import TradeDirection

    short = proposal(
        direction=TradeDirection.SHORT,
        entry=Decimal("60000"),
        stop=Decimal("61600"),
        targets=(Decimal("56000"),),
    )
    assert size(proposal=short).quantity == btc("0.625")
    assert size(proposal=short).money_at_risk == usdt("1000")


def test_the_owners_own_fraction_is_used_when_they_state_one() -> None:
    result = size(sizer=sizer(risk_fraction=Decimal("0.02")))
    assert result.quantity == btc("1.25")
    assert result.money_at_risk == usdt("2000")


def test_the_rounding_note_is_on_every_recommendation() -> None:
    """A quantity rounded *up* at a venue risks more than the fraction allows."""
    assert ROUNDING_NOTE in size().notes
    assert ROUNDING_NOTE in size(equity=Absent("nothing observed")).notes


def test_the_arithmetic_is_shown_and_not_merely_its_result() -> None:
    assert any(
        "0.01 of equity 100000 USDT = 1000 USDT at risk" in note
        for note in size().notes
    )


def test_the_basis_names_where_the_fraction_came_from() -> None:
    assert "default 0.01 the owner set below their ceiling" in size().basis


# ==========================================================================
# 2. REFUSED — the arithmetic is impossible
# ==========================================================================


def test_a_stop_the_entry_has_already_passed_refuses_a_size() -> None:
    result = size(proposal=proposal(stop=Decimal("61000")))
    assert result.outcome is SizingOutcome.REFUSED
    assert isinstance(result.quantity, Absent)
    assert "not below the entry" in result.quantity.reason


def test_a_non_positive_equity_is_a_refusal_to_trade_not_a_small_position() -> None:
    result = size(equity=Money(Decimal("0"), USDT))
    assert result.outcome is SizingOutcome.REFUSED
    assert "refusal to trade rather than a small position" in result.quantity.reason


def test_a_spent_open_risk_budget_refuses_any_size_that_increases_it() -> None:
    """`SWING_TRADING_MVP_BLUEPRINT_V1` §7.2 H-3, and the cap is named."""
    result = size(remaining_open_risk=usdt("0"))
    assert result.outcome is SizingOutcome.REFUSED
    assert "outranks any single candidate's quality" in result.quantity.reason
    assert result.caps


# ==========================================================================
# 3. UNDETERMINED — an input is not known
# ==========================================================================


def test_no_resolvable_fraction_leaves_the_size_undetermined() -> None:
    result = size(budget=budget_with(ceiling("0.02", default=None)))
    assert result.outcome is SizingOutcome.UNDETERMINED
    assert "ceiling is a ceiling and not a target" in result.quantity.reason
    assert isinstance(result.risk_fraction, Absent)


def test_an_unobserved_equity_leaves_the_size_undetermined() -> None:
    result = size(equity=Absent("no portfolio snapshot has been taken"))
    assert result.outcome is SizingOutcome.UNDETERMINED
    assert "a fraction of equity needs equity" in result.quantity.reason


def test_equity_in_another_currency_is_refused_rather_than_converted() -> None:
    """Converting here would hide the rate that made the two comparable."""
    result = size(equity=Money(Decimal("100000"), AssetCode("SEK")))
    assert result.outcome is SizingOutcome.UNDETERMINED
    assert "needs a dated rate this system holds nowhere" in result.quantity.reason


def test_an_unsized_recommendation_carries_every_figure_as_the_same_reason() -> None:
    result = size(equity=Absent("nothing observed"))
    for value in (result.quantity, result.money_at_risk, result.expected_exposure):
        assert isinstance(value, Absent)
        assert value.reason == result.quantity.reason


def test_an_unsized_recommendation_still_reports_the_planned_ratio() -> None:
    """The geometry is a fact about the candidate, not about the portfolio."""
    assert size(equity=Absent("nothing")).expected_r_multiple == Decimal("2.5")


# ==========================================================================
# 4. The portfolio bound
# ==========================================================================


def test_a_smaller_headroom_reduces_the_size_and_names_the_reduction() -> None:
    result = size(remaining_open_risk=usdt("400"))
    assert result.quantity == btc("0.25")
    assert result.money_at_risk == usdt("400")
    assert any("left in the total-open-risk budget" in cap for cap in result.caps)


def test_a_larger_headroom_leaves_the_size_alone_and_names_no_cap() -> None:
    assert size(remaining_open_risk=usdt("5000")).caps == ()


def test_an_unmeasurable_headroom_still_sizes_and_says_it_was_not_bounded() -> None:
    """*'Your budget is spent'* and *'nobody could tell'* are different answers."""
    result = size(remaining_open_risk=Absent("no mark for BTCUSDT"))
    assert result.outcome is SizingOutcome.SIZED
    assert result.caps == ()
    assert any("bounded by the per-trade ceiling alone" in n for n in result.notes)


def test_no_portfolio_at_all_is_a_third_and_different_answer() -> None:
    result = size(remaining_open_risk=None)
    assert result.outcome is SizingOutcome.SIZED
    assert any("no portfolio was supplied" in note for note in result.notes)


def test_a_headroom_in_another_currency_is_not_compared() -> None:
    result = size(remaining_open_risk=Money(Decimal("100"), AssetCode("SEK")))
    assert result.quantity == btc("0.625")
    assert any("were not compared" in note for note in result.notes)


def test_the_per_trade_ceiling_caps_an_over_stated_fraction_and_is_named() -> None:
    result = size(sizer=sizer(risk_fraction=Decimal("0.05")))
    assert result.risk_fraction == Decimal("0.02")
    assert result.quantity == btc("1.25")
    assert any("reduced to the per-trade ceiling 0.02" in cap for cap in result.caps)


def test_both_ceilings_can_apply_and_both_are_listed_in_order() -> None:
    result = size(
        sizer=sizer(risk_fraction=Decimal("0.05")), remaining_open_risk=usdt("400")
    )
    assert result.quantity == btc("0.25")
    assert len(result.caps) == 2
    assert "reduced to the per-trade ceiling 0.02" in result.caps[0]
    assert "left in the total-open-risk budget" in result.caps[1]


# ==========================================================================
# 5. Types and refusals of the call itself
# ==========================================================================


def test_the_sizer_holds_a_policy_and_refuses_anything_else() -> None:
    with pytest.raises(TypeError, match="SizingPolicy"):
        PositionSizer("owner_sizing")  # type: ignore[arg-type]
    assert PositionSizer(policy()).policy.policy_id == "owner_sizing"


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"proposal": "BTCUSDT"}, "PositionProposal"),
        ({"equity": Decimal("100000")}, "Money or Absent"),
        ({"budget": "swing_budget"}, "RiskBudget"),
        ({"remaining_open_risk": Decimal("1")}, "Money, Absent or None"),
    ],
)
def test_a_malformed_call_raises_rather_than_returning_a_refusal(
    kwargs: dict[str, object], match: str
) -> None:
    """A programming error is not dressed up as an answer about the owner's money."""
    with pytest.raises(TypeError, match=match):
        size(**kwargs)


def test_a_market_quoted_in_something_else_is_sized_in_its_own_quote_asset() -> None:
    """The equity currency must match the market's quote asset, or there is no size."""
    eur_market = MarketId(VenueId("binance"), BTC, AssetCode("EUR"), MarketMode.SPOT)
    result = size(proposal=proposal(market=eur_market))
    assert result.outcome is SizingOutcome.UNDETERMINED
    assert "EUR" in result.quantity.reason
