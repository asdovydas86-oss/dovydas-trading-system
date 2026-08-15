"""`PositionProposal`, `PositionRecommendation`, `ApprovalReason`, `ApprovalResult`.

The shapes, their refusals, and the one invariant that makes the whole milestone
safe: **a result cannot be `APPROVED` while holding a blocking or an
indeterminate reason.** That is asserted directly here, on hand-built objects, so
it holds for a future second producer of results as well as for the engine.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from persistence_helpers import risk_budget
from portfolio_risk_helpers import PORTFOLIO_ID, btc, state, usdt
from position_sizing_helpers import evaluate, proposal
from trade_domain_helpers import ACCOUNT, AT, BTC, MARKET, USDT, trade_plan

from fmis.accounts import AccountId, Book
from fmis.money import AssetCode, Money, Quantity
from fmis.portfolio_risk import ProposedTrade
from fmis.position_sizing import (
    ApprovalReason,
    ApprovalResult,
    ApprovalStatus,
    PositionProposal,
    PositionRecommendation,
    PositionSizingError,
    ReasonClass,
    ReasonScope,
    SizingOutcome,
    SizingRefusedError,
)
from fmis.positions import PositionDirection
from fmis.provenance import Absent, ValueOrigin
from fmis.records import DomainValidationError, TradeDomainError
from fmis.snapshotting import RiskRewardReading, TradeDirection


# ==========================================================================
# 1. PositionProposal — the candidate before it has a size
# ==========================================================================


def test_a_proposal_is_asserted_because_intent_can_be_wrong() -> None:
    assert proposal().origin is ValueOrigin.ASSERTED


def test_a_proposal_carries_no_quantity_which_is_the_whole_difference() -> None:
    """The type exists because `ProposedTrade` requires the number this step produces."""
    assert "quantity" not in PositionProposal.__dataclass_fields__
    assert "quantity" in ProposedTrade.__dataclass_fields__


def test_a_decision_not_to_act_proposes_no_exposure() -> None:
    with pytest.raises(DomainValidationError, match="not to act"):
        proposal(direction=TradeDirection.NO_TRADE)


@pytest.mark.parametrize("field", ["entry", "stop"])
def test_a_price_must_be_a_positive_decimal(field: str) -> None:
    with pytest.raises(TypeError):
        proposal(**{field: 60000.0})
    with pytest.raises(DomainValidationError, match="must be positive"):
        proposal(**{field: Decimal("0")})


def test_a_target_must_be_positive() -> None:
    with pytest.raises(DomainValidationError, match=r"targets\[0\]"):
        proposal(targets=(Decimal("0"),))


def test_prices_are_canonicalized_so_two_spellings_are_one_candidate() -> None:
    """`Decimal('58400.0')` and `Decimal('58400')` must not be two candidates."""
    assert proposal(stop=Decimal("58400.0")) == proposal(stop=Decimal("58400"))
    assert proposal(targets=(Decimal("64000.00"),)).targets == (Decimal("64000"),)


def test_the_account_and_market_are_domain_identifiers() -> None:
    with pytest.raises(TypeError, match="AccountId"):
        proposal(account="binance_spot")
    with pytest.raises(TypeError, match="MarketId"):
        proposal(market="BTCUSDT")


def test_the_book_is_a_member_and_never_a_string() -> None:
    with pytest.raises(TypeError):
        proposal(book="swing")


def test_a_plan_id_is_text_or_a_stated_absence() -> None:
    assert isinstance(proposal().plan_id, Absent)
    assert proposal(plan_id="plan-1").plan_id == "plan-1"


def test_the_scope_is_the_triple_one_open_position_lives_in() -> None:
    assert proposal().scope == (ACCOUNT.value, MARKET.value, Book.SWING.value)


def test_the_quote_asset_comes_from_the_market() -> None:
    assert proposal().quote_asset == USDT


# -- geometry ---------------------------------------------------------------


def test_the_risk_distance_is_the_geometry_engines_own_subtraction() -> None:
    assert proposal().risk_distance == Decimal("1600")


def test_a_stop_the_entry_has_already_passed_has_no_risk_distance() -> None:
    """`Absent`, not a raise: *'is this takeable'* has that as one of its answers."""
    refused = proposal(stop=Decimal("61000")).risk_distance
    assert isinstance(refused, Absent)
    assert "not below" in refused.reason


def test_the_reward_distance_is_the_same_subtraction_reversed() -> None:
    assert proposal().reward_distance == Decimal("4000")


def test_a_short_candidates_distances_are_mirrored_exactly() -> None:
    """The sign rule is written once and this proves both readings of it."""
    short = proposal(
        direction=TradeDirection.SHORT,
        entry=Decimal("60000"),
        stop=Decimal("61600"),
        targets=(Decimal("56000"),),
    )
    assert short.risk_distance == Decimal("1600")
    assert short.reward_distance == Decimal("4000")
    assert short.side is PositionDirection.SHORT


def test_a_target_on_the_stops_side_is_refused_rather_than_made_absolute() -> None:
    refused = proposal(targets=(Decimal("58000"),)).reward_distance
    assert isinstance(refused, Absent)
    assert "stop with the wrong label" in refused.reason


def test_no_target_means_no_reward_distance_and_no_ratio() -> None:
    bare = proposal(targets=())
    assert isinstance(bare.first_target, Absent)
    assert isinstance(bare.reward_distance, Absent)
    assert isinstance(bare.planned_risk_reward, Absent)


def test_the_planned_risk_reward_is_a_pair_and_divides_at_read_time() -> None:
    reading = proposal().planned_risk_reward
    assert isinstance(reading, RiskRewardReading)
    assert reading.risk_distance == Decimal("1600")
    assert reading.reward_distance == Decimal("4000")
    assert reading.ratio == Decimal("2.5")


def test_a_broken_stop_makes_the_ratio_absent_naming_the_geometry() -> None:
    refused = proposal(stop=Decimal("61000")).planned_risk_reward
    assert isinstance(refused, Absent)
    assert "no risk distance" in refused.reason


# -- projections ------------------------------------------------------------


def test_sizing_a_proposal_produces_the_portfolio_engines_own_input() -> None:
    sized = proposal().sized(btc("0.25"))
    assert isinstance(sized, ProposedTrade)
    assert sized.quantity == btc("0.25")
    assert sized.stop == Decimal("58400")


def test_sizing_requires_a_quantity() -> None:
    with pytest.raises(TypeError, match="Quantity"):
        proposal().sized(Decimal("0.25"))


def test_a_plan_supplies_the_stop_and_a_caller_cannot_override_it() -> None:
    recorded = trade_plan()
    built = PositionProposal.from_plan(
        recorded, account=ACCOUNT, entry=Decimal("60000")
    )
    assert built.stop == recorded.initial_invalidation
    assert built.targets == recorded.targets
    assert built.market == recorded.market
    assert built.direction == recorded.direction
    assert built.plan_id == recorded.plan_id


def test_from_plan_refuses_anything_that_is_not_a_plan() -> None:
    with pytest.raises(TypeError, match="TradePlan"):
        PositionProposal.from_plan(
            "plan-1", account=ACCOUNT, entry=Decimal("60000")  # type: ignore[arg-type]
        )


def test_a_proposal_exports_and_has_no_decoder() -> None:
    payload = proposal().to_payload()
    assert payload["direction"] == "long"
    assert payload["targets"] == ["64000"]
    assert payload["plan_id"]["absent"]
    assert not hasattr(PositionProposal, "from_payload")


def test_a_named_plan_appears_in_the_payload_as_a_value() -> None:
    assert proposal(plan_id="plan-1").to_payload()["plan_id"] == {"value": "plan-1"}


# ==========================================================================
# 2. PositionRecommendation
# ==========================================================================


def recommendation(**overrides: object) -> PositionRecommendation:
    values: dict[str, object] = {
        "proposal": proposal(),
        "outcome": SizingOutcome.SIZED,
        "quantity": btc("0.625"),
        "risk_fraction": Decimal("0.01"),
        "money_at_risk": usdt("1000"),
        "expected_exposure": usdt("37500"),
        "planned_risk_reward": proposal().planned_risk_reward,
        "equity": usdt("100000"),
        "basis": "the fraction the owner stated",
    }
    values.update(overrides)
    return PositionRecommendation(**values)  # type: ignore[arg-type]


def test_a_sized_recommendation_must_carry_a_quantity() -> None:
    with pytest.raises(DomainValidationError, match="SIZED recommendation"):
        recommendation(quantity=Absent("nothing"))


def test_an_unsized_recommendation_must_not_carry_one() -> None:
    with pytest.raises(DomainValidationError, match="SIZED recommendation"):
        recommendation(outcome=SizingOutcome.REFUSED)


def test_a_recommended_quantity_is_positive_or_it_is_a_refusal() -> None:
    with pytest.raises(DomainValidationError, match="must be positive"):
        recommendation(quantity=Quantity(Decimal("0"), BTC))


def test_a_quantity_must_be_a_quantity_or_a_stated_absence() -> None:
    with pytest.raises(TypeError, match="Quantity or Absent"):
        recommendation(quantity=Decimal("0.625"))


def test_a_fraction_must_be_a_decimal_or_a_stated_absence() -> None:
    with pytest.raises(TypeError, match="Decimal or Absent"):
        recommendation(risk_fraction="0.01")


def test_a_quantity_is_denominated_in_the_markets_base_asset() -> None:
    with pytest.raises(DomainValidationError, match="base asset"):
        recommendation(quantity=Quantity(Decimal("1"), AssetCode("ETH")))


def test_a_non_positive_fraction_is_a_refusal_to_trade_not_a_small_size() -> None:
    with pytest.raises(DomainValidationError, match="refusal to trade"):
        recommendation(risk_fraction=Decimal("0"))


def test_the_fraction_is_canonicalized() -> None:
    assert recommendation(risk_fraction=Decimal("0.0100")).risk_fraction == Decimal(
        "0.01"
    )


@pytest.mark.parametrize(
    "field", ["money_at_risk", "expected_exposure", "equity"]
)
def test_every_money_figure_is_money_or_absent(field: str) -> None:
    with pytest.raises(TypeError, match=field):
        recommendation(**{field: Decimal("1")})


def test_the_planned_reading_is_a_pair_or_an_absence() -> None:
    with pytest.raises(TypeError, match="RiskRewardReading"):
        recommendation(planned_risk_reward=Decimal("2.5"))


def test_the_basis_is_required_because_a_fraction_needs_a_provenance() -> None:
    with pytest.raises(TradeDomainError):
        recommendation(basis="   ")


def test_the_expected_r_multiple_is_derived_and_never_stored() -> None:
    assert "expected_r_multiple" not in PositionRecommendation.__dataclass_fields__
    assert recommendation().expected_r_multiple == Decimal("2.5")


def test_an_absent_reading_makes_the_r_multiple_absent_with_its_reason() -> None:
    absent = recommendation(planned_risk_reward=Absent("no target"))
    assert isinstance(absent.expected_r_multiple, Absent)


def test_a_sized_recommendation_can_produce_the_portfolio_engines_input() -> None:
    assert isinstance(recommendation().sized_trade(), ProposedTrade)


def test_an_unsized_one_reports_why_instead() -> None:
    refused = recommendation(
        outcome=SizingOutcome.UNDETERMINED, quantity=Absent("no equity")
    ).sized_trade()
    assert isinstance(refused, Absent)
    assert "no equity" in refused.reason


def test_the_risk_basis_is_the_geometry_engines_own_sentence() -> None:
    from fmis.portfolio_risk import RISK_BASIS

    assert recommendation().risk_basis == RISK_BASIS


def test_a_recommendation_exports_and_has_no_decoder() -> None:
    payload = recommendation().to_payload()
    assert payload["outcome"] == "sized"
    assert payload["expected_r_multiple"] == {"value": "2.5"}
    assert payload["risk_fraction"] == {"value": "0.01"}
    assert not hasattr(PositionRecommendation, "from_payload")


def test_an_unsized_recommendation_exports_its_reasons_rather_than_blanks() -> None:
    payload = recommendation(
        outcome=SizingOutcome.REFUSED,
        quantity=Absent("no risk distance"),
        money_at_risk=Absent("no risk distance"),
        expected_exposure=Absent("no risk distance"),
        risk_fraction=Absent("nothing was resolved"),
    ).to_payload()
    assert payload["quantity"]["absent"]
    assert payload["risk_fraction"]["absent"]


def test_the_proposal_must_be_a_proposal() -> None:
    with pytest.raises(TypeError, match="PositionProposal"):
        recommendation(proposal=MARKET)


def test_the_outcome_must_be_a_member() -> None:
    with pytest.raises(TypeError):
        recommendation(outcome="sized")


def test_caps_and_notes_are_tuples_of_text() -> None:
    with pytest.raises(TypeError):
        recommendation(caps=["a cap"])
    assert recommendation(caps=("a cap",)).caps == ("a cap",)


def test_the_recommendation_is_policy_derived() -> None:
    assert recommendation().origin is ValueOrigin.POLICY_DERIVED


# ==========================================================================
# 3. ApprovalReason
# ==========================================================================


def reason(**overrides: object) -> ApprovalReason:
    values: dict[str, object] = {
        "code": "TR-X",
        "scope": ReasonScope.TRADE,
        "classification": ReasonClass.WARNING,
        "statement": "something worth saying",
        "source": "a stated rule",
    }
    values.update(overrides)
    return ApprovalReason(**values)  # type: ignore[arg-type]


def test_a_reason_states_where_the_rule_comes_from() -> None:
    with pytest.raises(TradeDomainError):
        reason(source="")


def test_a_reason_names_a_subject_or_states_that_it_names_none() -> None:
    assert isinstance(reason().subject, Absent)
    assert reason(subject="per_trade_risk").subject == "per_trade_risk"


def test_a_reason_is_policy_derived_and_exports_its_class_and_scope() -> None:
    payload = reason().to_payload()
    assert reason().origin is ValueOrigin.POLICY_DERIVED
    assert payload["scope"] == "trade"
    assert payload["classification"] == "warning"
    assert payload["subject"]["absent"]


def test_a_reason_with_a_subject_exports_it_as_a_value() -> None:
    assert reason(subject="k").to_payload()["subject"] == {"value": "k"}


@pytest.mark.parametrize("field", ["scope", "classification"])
def test_the_vocabularies_are_closed(field: str) -> None:
    with pytest.raises(TypeError):
        reason(**{field: "trade"})


# ==========================================================================
# 4. ApprovalResult — the invariant that makes the milestone safe
# ==========================================================================


def test_a_result_cannot_be_approved_while_holding_a_blocking_reason() -> None:
    """The one rule this object exists to enforce, asserted directly."""
    real = evaluate()
    with pytest.raises(DomainValidationError, match="disagrees with its own reasons"):
        ApprovalResult(
            proposal=real.proposal,
            recommendation=real.recommendation,
            status=ApprovalStatus.APPROVED,
            reasons=(reason(classification=ReasonClass.BLOCKING),),
            state=real.state,
            before_check=real.before_check,
            impact=real.impact,
            evaluated_at=real.evaluated_at,
            policy_version=real.policy_version,
        )


def test_a_result_cannot_be_approved_while_holding_an_indeterminate_reason() -> None:
    real = evaluate()
    with pytest.raises(DomainValidationError, match="disagrees with its own reasons"):
        ApprovalResult(
            proposal=real.proposal,
            recommendation=real.recommendation,
            status=ApprovalStatus.APPROVED,
            reasons=(reason(classification=ReasonClass.INDETERMINATE),),
            state=real.state,
            before_check=real.before_check,
            impact=real.impact,
            evaluated_at=real.evaluated_at,
            policy_version=real.policy_version,
        )


def test_blocking_outranks_indeterminate_and_a_blocked_result_says_so() -> None:
    real = evaluate()
    built = ApprovalResult(
        proposal=real.proposal,
        recommendation=real.recommendation,
        status=ApprovalStatus.BLOCKED,
        reasons=(
            reason(code="A", classification=ReasonClass.BLOCKING),
            reason(code="B", classification=ReasonClass.INDETERMINATE),
        ),
        state=real.state,
        before_check=real.before_check,
        impact=real.impact,
        evaluated_at=real.evaluated_at,
        policy_version=real.policy_version,
    )
    assert built.status is ApprovalStatus.BLOCKED
    assert not built.is_approved


def test_a_clean_result_is_approved_and_says_so() -> None:
    real = evaluate()
    built = ApprovalResult(
        proposal=real.proposal,
        recommendation=real.recommendation,
        status=ApprovalStatus.APPROVED,
        reasons=(reason(),),
        state=real.state,
        before_check=real.before_check,
        impact=real.impact,
        evaluated_at=real.evaluated_at,
        policy_version=real.policy_version,
    )
    assert built.is_approved


def test_a_reason_code_may_not_appear_twice() -> None:
    real = evaluate()
    with pytest.raises(DomainValidationError, match="appears twice"):
        ApprovalResult(
            proposal=real.proposal,
            recommendation=real.recommendation,
            status=ApprovalStatus.INDETERMINATE,
            reasons=(
                reason(classification=ReasonClass.INDETERMINATE),
                reason(classification=ReasonClass.INDETERMINATE),
            ),
            state=real.state,
            before_check=real.before_check,
            impact=real.impact,
            evaluated_at=real.evaluated_at,
            policy_version=real.policy_version,
        )


def test_the_recommendation_must_size_the_candidate_this_result_is_about() -> None:
    real = evaluate()
    with pytest.raises(DomainValidationError, match="different candidate"):
        ApprovalResult(
            proposal=proposal(entry=Decimal("59000")),
            recommendation=real.recommendation,
            status=real.status,
            reasons=real.reasons,
            state=real.state,
            before_check=real.before_check,
            impact=real.impact,
            evaluated_at=real.evaluated_at,
            policy_version=real.policy_version,
        )


def test_a_sized_candidate_may_still_have_no_impact() -> None:
    """The invariant is one-directional, and this is the case that proves it.

    A candidate in a book the reading does not cover is perfectly sizeable and
    still has no impact against *this* portfolio — books never share capacity,
    and evaluating it here would move risk between two pools the design keeps
    apart.
    """
    real = evaluate()
    assert real.recommendation.is_sized
    built = ApprovalResult(
        proposal=real.proposal,
        recommendation=real.recommendation,
        status=ApprovalStatus.BLOCKED,
        reasons=(reason(code="TR-BOOK", classification=ReasonClass.BLOCKING),),
        state=real.state,
        before_check=real.before_check,
        impact=Absent("this candidate is in a book the reading does not cover"),
        evaluated_at=real.evaluated_at,
        policy_version=real.policy_version,
    )
    assert isinstance(built.open_risk_after, Absent)
    assert built.open_risk_before == real.open_risk_before


def test_an_impact_over_no_size_would_report_the_portfolio_as_unchanged() -> None:
    """The direction that *is* refused: an impact needs a size to be about."""
    real = evaluate()
    refused = evaluate(proposal(stop=Decimal("61000")))
    with pytest.raises(DomainValidationError, match="impact needs a size"):
        ApprovalResult(
            proposal=refused.proposal,
            recommendation=refused.recommendation,
            status=refused.status,
            reasons=refused.reasons,
            state=refused.state,
            before_check=refused.before_check,
            impact=real.impact,
            evaluated_at=refused.evaluated_at,
            policy_version=refused.policy_version,
        )


def test_the_impact_must_have_been_computed_against_this_very_reading() -> None:
    real = evaluate()
    with pytest.raises(DomainValidationError, match="different portfolio reading"):
        ApprovalResult(
            proposal=real.proposal,
            recommendation=real.recommendation,
            status=real.status,
            reasons=real.reasons,
            state=state(),
            before_check=real.before_check,
            impact=real.impact,
            evaluated_at=real.evaluated_at,
            policy_version=real.policy_version,
        )


def test_the_three_registers_are_three_lists() -> None:
    real = evaluate()
    assert set(real.blocking) | set(real.warnings) | set(real.indeterminate) == set(
        real.reasons
    )
    assert not set(real.blocking) & set(real.warnings)
    assert not set(real.warnings) & set(real.indeterminate)


def test_reasons_can_be_read_by_scope() -> None:
    real = evaluate()
    portfolio = real.scoped(ReasonScope.PORTFOLIO)
    trade = real.scoped(ReasonScope.TRADE)
    assert set(portfolio) | set(trade) == set(real.reasons)
    with pytest.raises(TypeError):
        real.scoped("portfolio")


def test_open_risk_before_survives_a_candidate_that_could_not_be_sized() -> None:
    """A fact about the portfolio, not about the trade — so it stays answerable."""
    refused = evaluate(proposal(stop=Decimal("61000")))
    assert isinstance(refused.impact, Absent)
    assert refused.open_risk_before == usdt("800")
    assert isinstance(refused.open_risk_after, Absent)
    assert "no size was produced" in refused.open_risk_after.reason


def test_the_result_exports_every_register_and_has_no_decoder() -> None:
    payload = evaluate().to_payload()
    assert payload["status"] in {"approved", "blocked", "indeterminate"}
    assert isinstance(payload["blocking"], list)
    assert isinstance(payload["warnings"], list)
    assert isinstance(payload["indeterminate"], list)
    assert payload["impact"].get("value") is not None
    assert not hasattr(ApprovalResult, "from_payload")


def test_a_refused_result_exports_the_impact_as_an_absence() -> None:
    payload = evaluate(proposal(stop=Decimal("61000"))).to_payload()
    assert payload["impact"]["absent"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("proposal", MARKET),
        ("recommendation", MARKET),
        ("state", MARKET),
        ("before_check", MARKET),
        ("impact", MARKET),
    ],
)
def test_every_component_is_type_checked(field: str, value: object) -> None:
    real = evaluate()
    values = {
        "proposal": real.proposal,
        "recommendation": real.recommendation,
        "status": real.status,
        "reasons": real.reasons,
        "state": real.state,
        "before_check": real.before_check,
        "impact": real.impact,
        "evaluated_at": real.evaluated_at,
        "policy_version": real.policy_version,
    }
    values[field] = value
    with pytest.raises(TypeError):
        ApprovalResult(**values)  # type: ignore[arg-type]


def test_the_status_must_be_a_member() -> None:
    real = evaluate()
    with pytest.raises(TypeError):
        ApprovalResult(
            proposal=real.proposal,
            recommendation=real.recommendation,
            status="approved",  # type: ignore[arg-type]
            reasons=real.reasons,
            state=real.state,
            before_check=real.before_check,
            impact=real.impact,
            evaluated_at=real.evaluated_at,
            policy_version=real.policy_version,
        )


def test_the_result_is_policy_derived_and_carries_the_risk_basis() -> None:
    real = evaluate()
    assert real.origin is ValueOrigin.POLICY_DERIVED
    assert "pre-cost" in real.risk_basis


def test_the_error_family_is_the_risk_layers_own() -> None:
    """A caller catching *'something in the risk layer refused'* keeps working."""
    from fmis.portfolio_risk import PortfolioRiskError

    assert issubclass(PositionSizingError, PortfolioRiskError)
    assert issubclass(PositionSizingError, TradeDomainError)
    assert issubclass(SizingRefusedError, PositionSizingError)
    assert issubclass(SizingRefusedError, DomainValidationError)
