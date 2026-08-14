"""The milestone's central question: what changes if this trade is opened now.

Two halves. The first is **detection** — what the candidate meets, in its own
scope and across the portfolio — and the second is **impact**, the before/after
comparison and the constraints evaluated against both.

The before/after tests deliberately assert *both* numbers rather than the
difference. A swapped before/after would leave a difference of the same magnitude
with the opposite sign, and a test that only checked the magnitude would pass.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from persistence_helpers import risk_budget, risk_limit
from portfolio_risk_helpers import (
    ETH,
    ETH_MARKET,
    EUR,
    EUR_MARKET,
    EVEDEX_MARKET,
    EVEDEX_PERP,
    SECOND_ACCOUNT,
    btc,
    groups,
    line,
    mark,
    no_groups,
    owner,
    proposal,
    state,
    usdt,
)
from trade_domain_helpers import ACCOUNT, AT, BTC, MARKET, USDT

from fmis.accounts import Book
from fmis.money import Money, Quantity
from fmis.portfolio_risk import (
    PROPOSED_MARK_SOURCE,
    evaluate_constraints,
    ExposureSource,
    IntendedEffect,
    PortfolioImpact,
    PortfolioRiskError,
    PositionRelationship,
    ProposedTrade,
    detect_overlap,
    evaluate_impact,
    lines_after,
)
from fmis.positions import PositionDirection
from fmis.provenance import Absent, ValueOrigin
from fmis.records import DomainValidationError
from fmis.risk import LimitScope, LimitStatus, LimitUnit
from fmis.snapshotting import TradeDirection

OWNER = owner()

TOTAL_MONEY = risk_limit(
    "total_open", scope=LimitScope.TOTAL_OPEN_RISK, value=usdt("1500"),
    unit=LimitUnit.MONEY,
)
PER_TRADE = risk_limit(
    "per_trade", scope=LimitScope.PER_TRADE_RISK, value=Decimal("0.02"),
    unit=LimitUnit.PERCENT_OF_EQUITY,
)


def impact(
    *lines: object, proposed: ProposedTrade | None = None, **state_kwargs: object
) -> PortfolioImpact:
    """A before-state over `lines` and the impact of one candidate on it.

    The same classification map reaches both the state and the impact, because a
    before/after comparison computed under two different taxonomies would be two
    readings of two portfolios.
    """
    classification = _classification(state_kwargs.pop("classification", None))
    return evaluate_impact(
        proposed=proposal() if proposed is None else proposed,
        before=state(
            *lines,  # type: ignore[arg-type]
            classification=classification,  # type: ignore[arg-type]
            **state_kwargs,  # type: ignore[arg-type]
        ),
        budget=risk_budget(limits=(PER_TRADE, TOTAL_MONEY)),
        owner=OWNER,
        classification=classification,  # type: ignore[arg-type]
    )


def _classification(supplied: object) -> object:
    return no_groups() if supplied is None else supplied


# -- ProposedTrade ----------------------------------------------------------


def test_a_proposal_computes_its_own_capital_at_risk() -> None:
    assert proposal().capital_at_risk() == usdt("400")  # 0.25 x 1600


def test_a_short_proposal_uses_the_short_geometry() -> None:
    short = proposal(
        direction=TradeDirection.SHORT, entry=Decimal("60000"), stop=Decimal("61600")
    )
    assert short.capital_at_risk() == usdt("400")


def test_a_proposal_with_a_transposed_stop_reports_the_reason() -> None:
    broken = proposal(entry=Decimal("58000"))
    risk = broken.capital_at_risk()
    assert isinstance(risk, Absent)
    assert "not below the entry" in risk.reason


def test_a_no_trade_proposal_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="decision not to act"):
        proposal(direction=TradeDirection.NO_TRADE)


def test_a_proposal_is_asserted_not_measured() -> None:
    assert proposal().origin is ValueOrigin.ASSERTED


def test_a_proposals_line_is_marked_at_its_own_entry_and_labelled() -> None:
    """The only honest valuation of exposure that does not exist yet — and a
    reader can always tell it from a measured mark."""
    candidate = proposal().as_line(AT(12))
    assert candidate.source is ExposureSource.PROPOSED
    assert candidate.mark.price == Decimal("60000")
    assert candidate.mark.source == PROPOSED_MARK_SOURCE
    assert candidate.origin is ValueOrigin.ASSERTED


def test_from_plan_takes_the_stop_from_the_commitment_and_cannot_override_it() -> None:
    """`initial_invalidation` is the field the plan entity exists to keep
    immutable; a sizing helper with a `stop=` parameter would be the edit path."""
    import inspect

    parameters = set(inspect.signature(ProposedTrade.from_plan).parameters)
    assert "stop" not in parameters
    assert parameters == {"plan", "account", "entry", "quantity"}


def test_a_proposal_serializes() -> None:
    payload = proposal().to_payload()
    assert payload["entry"] == "60000"
    assert payload["market"]["venue"] == "binance"


# -- detection: relationship and effect -------------------------------------


def test_an_empty_scope_is_a_new_position() -> None:
    overlap = detect_overlap(state(), proposal())
    assert overlap.relationship is PositionRelationship.NO_EXISTING_POSITION
    assert overlap.effect is IntendedEffect.NEW_POSITION
    assert isinstance(overlap.matched, Absent)


def test_the_same_direction_in_the_same_scope_is_a_scale_in() -> None:
    overlap = detect_overlap(state(line()), proposal())
    assert overlap.relationship is PositionRelationship.SAME_DIRECTION
    assert overlap.effect is IntendedEffect.SCALE_IN
    assert overlap.matched.quantity == btc("0.5")


def test_a_smaller_opposite_quantity_is_a_reduction() -> None:
    overlap = detect_overlap(
        state(line()),
        proposal(direction=TradeDirection.SHORT, entry=Decimal("60000"), stop=Decimal("61600"), quantity=btc("0.25")),
    )
    assert overlap.relationship is PositionRelationship.OPPOSITE_DIRECTION
    assert overlap.effect is IntendedEffect.REDUCTION


def test_an_equal_opposite_quantity_is_a_close() -> None:
    """The `<` / `==` / `>` boundary. Exactly flat is a close, not a reversal."""
    overlap = detect_overlap(
        state(line()),
        proposal(direction=TradeDirection.SHORT, entry=Decimal("60000"), stop=Decimal("61600"), quantity=btc("0.5")),
    )
    assert overlap.effect is IntendedEffect.CLOSE


def test_a_larger_opposite_quantity_is_a_reversal_candidate() -> None:
    overlap = detect_overlap(
        state(line()),
        proposal(direction=TradeDirection.SHORT, entry=Decimal("60000"), stop=Decimal("61600"), quantity=btc("0.75")),
    )
    assert overlap.effect is IntendedEffect.REVERSAL_CANDIDATE


def test_one_unit_either_side_of_the_close_boundary() -> None:
    def effect(quantity: str) -> IntendedEffect:
        return detect_overlap(
            state(line()),
            proposal(direction=TradeDirection.SHORT, entry=Decimal("60000"), stop=Decimal("61600"), quantity=btc(quantity)),
        ).effect

    assert effect("0.49999999") is IntendedEffect.REDUCTION
    assert effect("0.5") is IntendedEffect.CLOSE
    assert effect("0.50000001") is IntendedEffect.REVERSAL_CANDIDATE


def test_the_same_market_in_a_different_book_is_a_new_position() -> None:
    """Books never share capacity; merging them would move risk between pools."""
    overlap = detect_overlap(state(line()), proposal(book=Book.INVESTING))
    assert overlap.relationship is PositionRelationship.NO_EXISTING_POSITION
    assert overlap.effect is IntendedEffect.NEW_POSITION


def test_the_same_market_in_a_different_account_is_a_new_position() -> None:
    overlap = detect_overlap(state(line()), proposal(account=SECOND_ACCOUNT))
    assert overlap.relationship is PositionRelationship.NO_EXISTING_POSITION


def test_two_lines_in_one_scope_make_the_effect_indeterminate() -> None:
    """Unreachable from a fold, reachable from supplied lines — and an effect
    computed against an arbitrary one of two would be a guess."""
    doubled = state(line(), line(quantity=btc("0.25")))
    overlap = detect_overlap(doubled, proposal())
    assert isinstance(overlap.effect, Absent)
    assert "2 open lines" in overlap.effect.reason


# -- detection: duplicate exposure elsewhere --------------------------------


def test_the_same_symbol_at_another_venue_is_reported_as_duplicate() -> None:
    overlap = detect_overlap(state(line(market=EVEDEX_MARKET)), proposal())
    assert overlap.relationship is PositionRelationship.NO_EXISTING_POSITION
    assert len(overlap.same_instrument_elsewhere) == 1
    assert overlap.is_duplicate


def test_the_same_symbol_in_another_account_is_reported_as_duplicate() -> None:
    overlap = detect_overlap(state(line(account=SECOND_ACCOUNT)), proposal())
    assert len(overlap.same_instrument_elsewhere) == 1


def test_a_different_symbol_is_not_a_duplicate() -> None:
    overlap = detect_overlap(
        state(line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH))), proposal()
    )
    assert overlap.same_instrument_elsewhere == ()
    assert not overlap.is_duplicate


def test_the_matched_line_is_not_also_listed_as_elsewhere() -> None:
    overlap = detect_overlap(state(line()), proposal())
    assert overlap.same_instrument_elsewhere == ()


def test_a_relationship_and_a_matched_line_cannot_contradict_each_other() -> None:
    from fmis.portfolio_risk import PositionOverlap

    with pytest.raises(DomainValidationError, match="contradictory"):
        PositionOverlap(
            relationship=PositionRelationship.NO_EXISTING_POSITION,
            effect=IntendedEffect.NEW_POSITION,
            matched=line(),
        )


# -- the after-state --------------------------------------------------------


def test_a_new_position_is_added_as_its_own_line() -> None:
    after = lines_after(state(), proposal(), as_of=AT(12))
    assert len(after) == 1
    assert after[0].source is ExposureSource.PROPOSED


def test_a_scale_in_keeps_two_lines_and_two_stops() -> None:
    """Blending them would need a weighted-average stop the owner never stated."""
    after = lines_after(state(line()), proposal(stop=Decimal("59000")), as_of=AT(12))
    assert len(after) == 2
    assert {entry.stop for entry in after} == {Decimal("58400"), Decimal("59000")}


def test_a_reduction_shrinks_the_existing_line_and_adds_nothing() -> None:
    after = lines_after(
        state(line()),
        proposal(direction=TradeDirection.SHORT, entry=Decimal("60000"), stop=Decimal("61600"), quantity=btc("0.25")),
        as_of=AT(12),
    )
    assert len(after) == 1
    assert after[0].quantity == btc("0.25")
    assert after[0].direction is PositionDirection.LONG


def test_a_close_removes_the_line() -> None:
    after = lines_after(
        state(line()),
        proposal(direction=TradeDirection.SHORT, entry=Decimal("60000"), stop=Decimal("61600"), quantity=btc("0.5")),
        as_of=AT(12),
    )
    assert after == ()


def test_a_reversal_leaves_the_remainder_on_the_other_side() -> None:
    """The split `_crosses_zero` already performs, applied to a candidate."""
    after = lines_after(
        state(line()),
        proposal(direction=TradeDirection.SHORT, entry=Decimal("60000"), stop=Decimal("61600"), quantity=btc("0.75")),
        as_of=AT(12),
    )
    assert len(after) == 1
    assert after[0].direction is PositionDirection.SHORT
    assert after[0].quantity == btc("0.25")


def test_a_reduction_does_not_inflate_gross_exposure() -> None:
    """Appending an opposite line instead of reducing would report a de-risking
    trade as doubling the book."""
    result = impact(
        line(),
        proposed=proposal(direction=TradeDirection.SHORT, entry=Decimal("60000"), stop=Decimal("61600"), quantity=btc("0.25")),
    )
    assert result.before.gross_exposure == usdt("30500")
    assert result.after.gross_exposure == usdt("15250")


# -- before / after ---------------------------------------------------------


def test_the_before_state_never_contains_the_candidate() -> None:
    result = impact(line())
    assert result.before.proposed_lines == ()
    assert result.after.proposed_lines != ()


def test_both_states_are_reported_and_neither_is_derived_from_the_other() -> None:
    result = impact(line())
    assert result.before.open_risk == usdt("800")
    assert result.after.open_risk == usdt("1200")  # 800 + 400
    assert result.incremental_open_risk == usdt("400")


def test_a_before_after_swap_would_change_the_sign_of_the_increment() -> None:
    """Asserted explicitly: the increment is `after − before`, so a de-risking
    trade produces a negative number rather than a positive one."""
    result = impact(
        line(),
        proposed=proposal(direction=TradeDirection.SHORT, entry=Decimal("60000"), stop=Decimal("61600"), quantity=btc("0.25")),
    )
    assert result.after.open_risk < result.before.open_risk
    assert result.incremental_open_risk == usdt("-400")


def test_the_increment_is_the_difference_and_not_the_candidates_own_risk() -> None:
    """A reducing trade has 400 USDT of standalone risk and lowers the portfolio's
    open risk by 400. Reporting the first as the increment would report a
    de-risking trade as the largest addition to the book."""
    reducing = proposal(direction=TradeDirection.SHORT, entry=Decimal("60000"), stop=Decimal("61600"), quantity=btc("0.25"))
    assert reducing.capital_at_risk() == usdt("400")
    assert impact(line(), proposed=reducing).incremental_open_risk == usdt("-400")


def test_the_two_states_share_one_instant_and_one_currency() -> None:
    result = impact(line())
    assert result.before.as_of == result.after.as_of
    assert result.before.base_currency == result.after.base_currency


def test_the_resulting_exposures_are_readable_off_the_impact() -> None:
    result = impact(line())
    assert result.resulting_gross_exposure == usdt("45500")  # 30500 + 15000
    assert result.resulting_long_exposure == usdt("45500")
    assert result.resulting_short_exposure == usdt("0")
    assert result.resulting_net_exposure == usdt("45500")
    assert result.resulting_open_risk == usdt("1200")


def test_incremental_capital_required_is_the_notional_for_a_spot_long() -> None:
    result = impact(line())
    assert result.incremental_notional == usdt("15000")  # 0.25 x 60000
    assert result.incremental_capital_required == usdt("15000")


def test_incremental_capital_required_is_absent_for_a_short() -> None:
    result = impact(
        proposed=proposal(direction=TradeDirection.SHORT, entry=Decimal("60000"), stop=Decimal("61600"))
    )
    assert result.incremental_notional == usdt("15000")
    assert isinstance(result.incremental_capital_required, Absent)
    assert "margin" in result.incremental_capital_required.reason


def test_incremental_capital_required_is_absent_for_a_perpetual() -> None:
    result = impact(proposed=proposal(market=EVEDEX_PERP))
    assert isinstance(result.incremental_capital_required, Absent)
    assert "perpetual" in result.incremental_capital_required.reason


def test_a_foreign_quote_makes_both_capital_figures_absent() -> None:
    result = impact(
        proposed=proposal(market=EUR_MARKET, entry=Decimal("54000"), stop=Decimal("52000"))
    )
    assert isinstance(result.incremental_notional, Absent)
    assert isinstance(result.incremental_capital_required, Absent)
    assert "EUR" in result.incremental_notional.reason


# -- constraints on both states ---------------------------------------------


def test_a_limit_the_trade_would_breach_is_reported_as_newly_binding() -> None:
    """1120 USDT of open risk is within a 1500 budget; the candidate's 400 takes
    it to 1520, which is not."""
    result = impact(line(quantity=btc("0.7")))
    assert result.before_check.result("total_open").status is LimitStatus.WITHIN
    assert result.after_check.result("total_open").status is LimitStatus.EXCEEDED
    assert result.newly_binding == ("total_open",)
    assert result.already_binding == ()


def test_a_limit_already_breached_is_not_blamed_on_the_trade() -> None:
    result = impact(line(quantity=btc("1")))
    assert result.already_binding == ("total_open",)
    assert "total_open" not in result.newly_binding


def test_the_candidates_own_risk_drives_the_per_trade_limit() -> None:
    """With a candidate, PER_TRADE means *this* trade — not the largest held."""
    result = impact(line(quantity=btc("1.5")), proposed=proposal())
    assert result.after_check.result("per_trade").current_value == Decimal("0.004")


def test_the_two_percent_ceiling_binds_on_the_candidate() -> None:
    result = impact(proposed=proposal(quantity=btc("1.25")))  # 2000 USDT at risk
    assert result.after_check.result("per_trade").status is LimitStatus.AT_LIMIT


def test_one_unit_over_the_two_percent_ceiling_is_exceeded() -> None:
    result = impact(proposed=proposal(quantity=btc("1.2506250")))
    assert result.after_check.result("per_trade").status is LimitStatus.EXCEEDED


def test_remaining_risk_budget_is_reported_after_the_trade() -> None:
    assert impact().remaining_risk_budget == usdt("1100")  # 1500 - 400


def test_the_impact_returns_no_verdict() -> None:
    fields = set(PortfolioImpact.__dataclass_fields__)
    for forbidden in ("verdict", "decision", "recommendation", "score", "action"):
        assert not any(forbidden in name for name in fields)


# -- notes ------------------------------------------------------------------


def codes(result: PortfolioImpact) -> set[str]:
    return {note.code for note in result.notes}


def test_duplicate_exposure_elsewhere_produces_a_note_naming_the_venue() -> None:
    result = impact(line(market=EVEDEX_MARKET))
    assert "PR-N1" in codes(result)
    note = next(entry for entry in result.notes if entry.code == "PR-N1")
    assert "evedex" in note.statement
    assert "do not net" in note.statement


def test_a_shared_group_produces_a_concentration_note_not_a_diversification_one() -> None:
    result = impact(
        line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), mark=mark("3000"), entry=Decimal("3000"), stop=Decimal("2800")),
        classification=groups("owner-v1", BTC=["l1"], ETH=["l1"]),
    )
    note = next(entry for entry in result.notes if entry.code == "PR-N2")
    assert "'l1'" in note.statement
    assert "concentration rather than diversification" in note.statement


def test_an_unclassified_candidate_says_so_rather_than_measuring_nothing() -> None:
    result = impact(line(), classification=groups("owner-v1", ETH=["l1"]))
    note = next(entry for entry in result.notes if entry.code == "PR-N7")
    assert "unclassified" in note.statement
    assert "not the same as measuring it and finding none" in note.statement


def test_no_group_note_when_the_candidate_shares_nothing() -> None:
    result = impact(
        line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH), mark=mark("3000"), entry=Decimal("3000"), stop=Decimal("2800")),
        classification=groups("owner-v1", BTC=["l1"], ETH=["defi"]),
    )
    assert "PR-N2" not in codes(result)


def test_a_reversal_produces_a_note() -> None:
    result = impact(
        line(),
        proposed=proposal(direction=TradeDirection.SHORT, entry=Decimal("60000"), stop=Decimal("61600"), quantity=btc("0.75")),
    )
    assert "PR-N6" in codes(result)


def test_a_newly_binding_limit_and_an_already_binding_one_get_different_codes() -> None:
    assert "PR-N3" in codes(impact(line(quantity=btc("0.7"))))
    assert "PR-N4" in codes(impact(line(quantity=btc("1"))))


def test_an_indeterminate_limit_after_the_trade_is_flagged_distinctly() -> None:
    result = impact(line(), equity=Absent("no snapshot has been taken"))
    note = next(entry for entry in result.notes if entry.code == "PR-N5")
    assert "not a limit that was met" in note.statement


def test_an_unstopped_position_after_the_trade_is_flagged() -> None:
    result = impact(line(stop=Absent("no plan")))
    assert "PR-N9" in codes(result)


def test_a_note_carries_no_severity_and_no_rank() -> None:
    from fmis.portfolio_risk import PortfolioNote

    assert set(PortfolioNote.__dataclass_fields__) == {"code", "statement"}


# -- refusals and determinism ------------------------------------------------


def test_a_candidate_in_an_uncovered_book_is_refused_with_the_reason() -> None:
    with pytest.raises(PortfolioRiskError, match="never share capacity"):
        evaluate_impact(
            proposed=proposal(book=Book.PAPER),
            before=state(),
            budget=risk_budget(limits=(PER_TRADE,)),
            owner=OWNER,
            classification=_classification(None),
        )


def test_the_same_inputs_produce_an_equal_impact_every_time() -> None:
    assert impact(line()) == impact(line())


def test_the_impact_serializes_both_states_and_both_checks() -> None:
    payload = impact(line(quantity=btc("0.7"))).to_payload()
    assert payload["before"]["open_risk"] == {"value": {"amount": "1120", "asset": "USDT"}}
    assert payload["after"]["open_risk"] == {"value": {"amount": "1520", "asset": "USDT"}}
    assert payload["newly_binding"] == ["total_open"]
    assert payload["overlap"]["effect"] == {"value": "scale_in"}


def test_the_impact_refuses_inputs_of_the_wrong_type() -> None:
    with pytest.raises(TypeError):
        evaluate_impact(
            proposed=object(),  # type: ignore[arg-type]
            before=state(),
            budget=risk_budget(),
            owner=OWNER,
            classification=_classification(None),
        )
    with pytest.raises(TypeError):
        evaluate_impact(
            proposed=proposal(),
            before=object(),  # type: ignore[arg-type]
            budget=risk_budget(),
            owner=OWNER,
            classification=_classification(None),
        )


# -- building a candidate from a recorded commitment ------------------------


def _plan(**overrides: object):
    """A committed `TradePlan`, built through the domain's own constructor."""
    from fmis.plan import TradePlan
    from fmis.proposal import StatedConfidence
    from fmis.records import RecordAudit
    from trade_domain_helpers import version_set

    values: dict[str, object] = {
        "created_at": AT(9),
        "committed_at": AT(10),
        "market": MARKET,
        "book": Book.SWING,
        "direction": TradeDirection.LONG,
        "initial_invalidation": Decimal("58400"),
        "targets": (Decimal("64000"),),
        "stated_confidence": StatedConfidence("moderate"),
        "version_set": version_set(),
        "audit": RecordAudit.frozen_at(AT(9)),
    }
    values.update(overrides)
    return TradePlan(**values)  # type: ignore[arg-type]


def test_from_plan_carries_the_market_book_side_and_stop_across() -> None:
    """Sizing a commitment the owner already recorded, without retyping any of
    it — the BK-to-BL join at the value level."""
    plan = _plan()
    candidate = ProposedTrade.from_plan(
        plan, account=ACCOUNT, entry=Decimal("60000"), quantity=btc("0.25")
    )
    assert candidate.market == plan.market
    assert candidate.book is plan.book
    assert candidate.direction is plan.direction
    assert candidate.stop == plan.initial_invalidation
    assert candidate.plan_id == plan.plan_id
    assert candidate.capital_at_risk() == usdt("400")


def test_from_plan_carries_a_short_commitments_side() -> None:
    plan = _plan(
        direction=TradeDirection.SHORT,
        initial_invalidation=Decimal("61600"),
        targets=(Decimal("56000"),),
    )
    candidate = ProposedTrade.from_plan(
        plan, account=ACCOUNT, entry=Decimal("60000"), quantity=btc("0.25")
    )
    assert candidate.side is PositionDirection.SHORT
    assert candidate.capital_at_risk() == usdt("400")


def test_from_plan_refuses_something_that_is_not_a_plan() -> None:
    with pytest.raises(TypeError, match="TradePlan"):
        ProposedTrade.from_plan(
            object(),  # type: ignore[arg-type]
            account=ACCOUNT,
            entry=Decimal("60000"),
            quantity=btc("0.25"),
        )


def test_an_indeterminate_effect_reaches_the_page_as_its_own_note() -> None:
    """Two lines in one scope: the effect cannot be stated, and the reason is
    carried onto the impact rather than dropped."""
    result = impact(line(), line(quantity=btc("0.25")))
    note = next(entry for entry in result.notes if entry.code == "PR-N8")
    assert "2 open lines" in note.statement
    assert isinstance(result.overlap.effect, Absent)


def test_the_increment_is_absent_when_only_the_before_state_is_unmeasurable() -> None:
    """Closing an unstopped position leaves a measurable *after* and an
    unmeasurable *before*. The change is still absent: subtracting a known number
    from an unknown one does not produce a known difference."""
    result = impact(
        line(stop=Absent("no plan")),
        proposed=proposal(
            direction=TradeDirection.SHORT,
            entry=Decimal("60000"),
            stop=Decimal("61600"),
            quantity=btc("0.5"),
        ),
    )
    assert isinstance(result.before.open_risk, Absent)
    assert result.after.open_risk == usdt("0")
    assert isinstance(result.incremental_open_risk, Absent)
    assert "current open risk is not known" in result.incremental_open_risk.reason


def test_an_unstopped_position_makes_the_increment_absent() -> None:
    """A portfolio with an unstopped position has no open-risk figure, so the
    *change* in open risk has none either — never a number computed from half."""
    result = impact(line(stop=Absent("no plan")))
    assert isinstance(result.before.open_risk, Absent)
    assert isinstance(result.incremental_open_risk, Absent)


def test_the_increment_is_absent_when_only_the_after_state_is_unmeasurable() -> None:
    broken = proposal(entry=Decimal("58000"))  # stop above the entry on a long
    result = impact(line(), proposed=broken)
    assert result.before.open_risk == usdt("800")
    assert isinstance(result.after.open_risk, Absent)
    assert isinstance(result.incremental_open_risk, Absent)
    assert "resulting open risk is not known" in result.incremental_open_risk.reason


def test_a_limit_reached_exactly_by_the_trade_is_reported_as_newly_binding() -> None:
    """Mutation N18 at the impact layer: a trade that takes a limit to exactly
    its ceiling has changed something the owner must see."""
    result = impact(proposed=proposal(quantity=btc("1.25")))  # exactly 2 % of equity
    assert result.after_check.result("per_trade").status is LimitStatus.AT_LIMIT
    assert "per_trade" in result.newly_binding
    assert "PR-N3" in codes(result)


# -- cross-quote duplicate exposure (hostile-review finding H1) -------------


def test_the_same_asset_under_a_different_quote_is_reported_as_duplicate() -> None:
    """Hostile-review finding H1. A held `BTCUSDC` long and a candidate
    `BTCUSDT` long share no symbol, no instrument and no venue-scoped key — and
    are the same bet. Answering *"no duplicate"* would be the flattering answer
    rather than the true one."""
    from portfolio_risk_helpers import BTCUSDC_MARKET, USDC

    held = line(
        market=BTCUSDC_MARKET,
        mark=mark("61000", quote=USDC),
        entry=Decimal("60000"),
        stop=Decimal("58400"),
    )
    overlap = detect_overlap(state(held), proposal())
    assert overlap.relationship is PositionRelationship.NO_EXISTING_POSITION
    assert overlap.same_instrument_elsewhere == ()
    assert len(overlap.same_asset_elsewhere) == 1
    assert overlap.is_duplicate


def test_a_cross_quote_duplicate_produces_its_own_note() -> None:
    from portfolio_risk_helpers import BTCUSDC_MARKET, USDC

    result = impact(
        line(
            market=BTCUSDC_MARKET,
            mark=mark("61000", quote=USDC),
            entry=Decimal("60000"),
            stop=Decimal("58400"),
        )
    )
    note = next(entry for entry in result.notes if entry.code == "PR-N10")
    assert "BTCUSDC" in note.statement
    assert "the same bet" in note.statement


def test_the_same_pair_elsewhere_is_not_double_reported_as_a_cross_quote_duplicate() -> None:
    """The two lists are disjoint: a `BTCUSDT` holding at another venue is a
    same-instrument duplicate and must not also appear as a cross-quote one."""
    overlap = detect_overlap(state(line(market=EVEDEX_MARKET)), proposal())
    assert len(overlap.same_instrument_elsewhere) == 1
    assert overlap.same_asset_elsewhere == ()


def test_a_different_asset_is_neither_kind_of_duplicate() -> None:
    overlap = detect_overlap(
        state(line(market=ETH_MARKET, quantity=Quantity(Decimal("1"), ETH))), proposal()
    )
    assert overlap.same_instrument_elsewhere == ()
    assert overlap.same_asset_elsewhere == ()
    assert not overlap.is_duplicate


def test_an_asset_concentration_limit_is_addressable_on_the_asset_axis() -> None:
    """`asset:BTC` is a key a concentration limit may name, alongside
    `symbol:BTCUSDT` and `instrument:...`."""
    limit = risk_limit(
        "conc", scope=LimitScope.CONCENTRATION, value=Decimal("0.6"),
        unit=LimitUnit.RATIO, key="asset:BTC",
    )
    check = evaluate_constraints(
        risk_budget(limits=(limit,)),
        state(line(), line(market=EVEDEX_MARKET)),
        owner=OWNER,
    )
    assert check.result("conc").current_value == Decimal("1")
    assert check.result("conc").status is LimitStatus.EXCEEDED


def test_a_cross_quote_holding_is_grouped_but_not_valued_without_a_rate() -> None:
    """The honest limit of the asset axis. Two quote currencies means no
    comparable money figure, so the concentration is `INDETERMINATE` naming the
    missing rate — **not** a smaller number, and not a silent conversion. The
    duplicate is still *detected*; it is only the arithmetic that is refused."""
    from portfolio_risk_helpers import BTCUSDC_MARKET, USDC

    limit = risk_limit(
        "conc", scope=LimitScope.CONCENTRATION, value=Decimal("0.6"),
        unit=LimitUnit.RATIO, key="asset:BTC",
    )
    held = line(
        market=BTCUSDC_MARKET,
        mark=mark("61000", quote=USDC),
        entry=Decimal("60000"),
        stop=Decimal("58400"),
    )
    before = state(line(), held)
    check = evaluate_constraints(
        risk_budget(limits=(limit,)), before, owner=OWNER
    )
    assert isinstance(check.result("conc").status, Absent)
    assert "no rate to USDT" in check.result("conc").status.reason
    # Detection is unaffected: the duplicate bet is still named.
    assert detect_overlap(before, proposal()).is_duplicate


def test_an_impact_is_policy_derived_and_serializes_its_absences() -> None:
    """A measured portfolio read against asserted limits is `POLICY_DERIVED`;
    and the `Absent` arm of its payload encoder carries the reason forward."""
    result = impact(line(stop=Absent("no plan")))
    assert result.origin is ValueOrigin.POLICY_DERIVED
    payload = result.to_payload()
    assert "absent" in payload["incremental_open_risk"]
    assert "not known" in payload["incremental_open_risk"]["absent"]["reason"]
