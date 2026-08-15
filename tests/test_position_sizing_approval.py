"""`ApprovalEngine` — the two independent evaluations and the three answers.

Organised the way the engine is: what it says about the **trade**, what it says
about the **portfolio**, and how the two combine into one status. The assertions
that matter most are the ones about what the engine refuses to say — that
`INDETERMINATE` is never silently `APPROVED`, that a ceiling reached exactly is
not a breach, that an unconstrained axis is reported rather than passed over, and
that the severity of every reason is the owner's rather than this engine's.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from persistence_helpers import risk_limit
from portfolio_risk_helpers import (
    ETH_MARKET,
    EVEDEX_MARKET,
    btc,
    groups,
    line,
    mark,
    state,
    usdt,
)
from position_sizing_helpers import (
    budget_with,
    ceiling,
    cluster_limit,
    concentration_limit,
    engine,
    evaluate,
    owner,
    policy,
    proposal,
    total_risk_limit,
)
from trade_domain_helpers import ACCOUNT, AT, MARKET, USDT

from fmis.accounts import Book
from fmis.money import AssetCode, Money, Quantity
from fmis.portfolio_risk import PortfolioState
from fmis.position_sizing import (
    APPROVAL_POLICY_VERSION,
    REQUIRED_AXES,
    ApprovalEngine,
    ApprovalStatus,
    PositionSizer,
    ReasonClass,
    ReasonScope,
)
from fmis.provenance import Absent
from fmis.risk import LimitPeriod, LimitScope, LimitSeverity, LimitUnit


def codes(result: object) -> set[str]:
    return {reason.code for reason in result.reasons}  # type: ignore[attr-defined]


def reason_for(result: object, code: str) -> object:
    return next(r for r in result.reasons if r.code == code)  # type: ignore[attr-defined]


#: A budget that constrains every axis the engine reports coverage for, so a test
#: about one axis is not drowned in warnings about the other four.
def full_budget(*extra: object) -> object:
    return budget_with(
        ceiling("0.02"),
        total_risk_limit(Money(Decimal("6000"), USDT)),
        concentration_limit(f"instrument:{MARKET.value}", Decimal("1")),
        concentration_limit("asset:BTC", Decimal("1")),
        concentration_limit(f"account:{ACCOUNT.value}", Decimal("1")),
        cluster_limit("l1", Decimal("1")),
        *extra,
    )


def full_engine(**overrides: object) -> ApprovalEngine:
    return engine(classification=groups(BTC=["l1"]), **overrides)


# ==========================================================================
# 1. The happy path
# ==========================================================================


def test_a_candidate_within_every_limit_is_approved_with_a_size() -> None:
    result = evaluate(
        portfolio=state(equity=usdt("100000"), cash=usdt("40000")),
        budget=full_budget(),
        approval_engine=full_engine(),
    )
    assert result.status is ApprovalStatus.APPROVED
    assert result.blocking == ()
    assert result.indeterminate == ()
    assert result.recommended_quantity == btc("0.625")
    assert result.open_risk_after == usdt("1000")


def test_the_result_cites_the_rule_versions_it_ran_under() -> None:
    result = evaluate()
    assert result.policy_version == APPROVAL_POLICY_VERSION
    assert result.before_check.policy_version == "portfolio-constraint-v1"


def test_the_evaluation_instant_defaults_to_the_readings_own() -> None:
    """Nothing here reads a clock, so an approval is dated by its portfolio."""
    portfolio = state(as_of=AT(15))
    assert evaluate(portfolio=portfolio).evaluated_at == AT(15)
    assert evaluate(portfolio=portfolio, evaluated_at=AT(16)).evaluated_at == AT(16)


def test_the_impact_is_computed_against_the_very_reading_the_result_carries() -> None:
    result = evaluate()
    assert result.impact.before is result.state


# ==========================================================================
# 2. Trade-scope reasons
# ==========================================================================


def test_a_transposed_stop_blocks_and_names_the_geometry() -> None:
    result = evaluate(proposal(stop=Decimal("61000")))
    assert result.status is ApprovalStatus.BLOCKED
    assert "TR-STOP" in codes(result)
    assert "TR-SIZE" not in codes(result), "one cause, one reason"
    assert reason_for(result, "TR-STOP").scope is ReasonScope.TRADE


def test_an_impossible_allowance_blocks_under_its_own_code() -> None:
    result = evaluate(
        portfolio=state(line(), equity=Money(Decimal("0"), USDT)),
        approval_engine=full_engine(),
        budget=full_budget(),
    )
    assert result.status is ApprovalStatus.BLOCKED
    assert "TR-SIZE" in codes(result)
    assert reason_for(result, "TR-SIZE").classification is ReasonClass.BLOCKING


def test_an_unknown_input_leaves_the_size_indeterminate_rather_than_blocked() -> None:
    """The distinction the whole `SizingOutcome` enum exists for."""
    result = evaluate(
        portfolio=state(equity=Absent("no snapshot has been taken")),
        approval_engine=full_engine(),
        budget=full_budget(),
    )
    assert result.status is ApprovalStatus.INDETERMINATE
    assert reason_for(result, "TR-SIZE").classification is ReasonClass.INDETERMINATE


def test_a_candidate_in_an_uncovered_book_is_blocked_because_books_never_share() -> None:
    result = evaluate(
        proposal(book=Book.DAY),
        portfolio=state(line(), books_covered=(Book.SWING,)),
    )
    assert result.status is ApprovalStatus.BLOCKED
    assert "TR-BOOK" in codes(result)
    assert "Books never share capacity" in reason_for(result, "TR-BOOK").statement
    assert isinstance(result.impact, Absent)


def test_a_reduced_size_warns_and_lists_every_ceiling_that_reduced_it() -> None:
    result = evaluate(
        approval_engine=full_engine(risk_fraction=Decimal("0.05")),
        budget=full_budget(),
    )
    assert reason_for(result, "TR-CAP").classification is ReasonClass.WARNING
    assert "reduced to the per-trade ceiling" in reason_for(result, "TR-CAP").statement


def test_an_unreduced_size_raises_no_cap_warning() -> None:
    result = evaluate(budget=full_budget(), approval_engine=full_engine())
    assert "TR-CAP" not in codes(result)


# -- freshness --------------------------------------------------------------


def dated(**overrides: object) -> PortfolioState:
    """A reading whose equity states the instant it was true."""
    values: dict[str, object] = {
        "equity": usdt("100000"),
        "cash": usdt("40000"),
        "as_of": AT(12),
        "equity_as_of": AT(10),
    }
    values.update(overrides)
    return state(line(), **values)  # type: ignore[arg-type]


def test_an_equity_age_with_no_configured_bound_is_reported_and_not_judged() -> None:
    """A bound this package chose would be a threshold invented at exactly the
    point the specification says not to."""
    result = evaluate(portfolio=dated(), budget=full_budget(), approval_engine=full_engine())
    entry = reason_for(result, "TR-EQUITY-AGE")
    assert entry.classification is ReasonClass.WARNING
    assert "reported and not judged" in entry.statement


def test_an_equity_older_than_the_owners_bound_blocks_sizing() -> None:
    result = evaluate(
        portfolio=dated(),
        budget=full_budget(),
        approval_engine=full_engine(max_equity_age=timedelta(hours=1)),
    )
    assert result.status is ApprovalStatus.BLOCKED
    assert reason_for(result, "TR-EQUITY-AGE").classification is ReasonClass.BLOCKING


def test_an_equity_inside_the_bound_raises_nothing_at_all() -> None:
    result = evaluate(
        portfolio=dated(),
        budget=full_budget(),
        approval_engine=full_engine(max_equity_age=timedelta(hours=6)),
    )
    assert "TR-EQUITY-AGE" not in codes(result)


def test_an_undated_equity_with_a_bound_configured_cannot_be_checked() -> None:
    """The owner's own check could not run, so the whole approval is demoted."""
    result = evaluate(
        budget=full_budget(),
        approval_engine=full_engine(max_equity_age=timedelta(hours=6)),
    )
    entry = reason_for(result, "TR-EQUITY-AGE")
    assert entry.classification is ReasonClass.INDETERMINATE
    assert "could not be applied" in entry.statement
    assert result.status is ApprovalStatus.INDETERMINATE


def test_an_undated_equity_with_no_bound_is_a_warning_and_not_a_demotion() -> None:
    """Nothing was checking it, so an unknown age is not an unmeasured check.

    An `INDETERMINATE` that fires on every page for a rule the owner never asked
    for is an `INDETERMINATE` nobody reads.
    """
    result = evaluate(budget=full_budget(), approval_engine=full_engine())
    entry = reason_for(result, "TR-EQUITY-AGE")
    assert entry.classification is ReasonClass.WARNING
    assert "Nothing was checking it" in entry.statement
    assert result.status is ApprovalStatus.APPROVED


def test_an_absent_equity_raises_no_age_reason_at_all() -> None:
    """The size already reports it; a second sentence about the same gap is noise."""
    result = evaluate(
        portfolio=state(equity=Absent("no snapshot")),
        budget=full_budget(),
        approval_engine=full_engine(),
    )
    assert "TR-EQUITY-AGE" not in codes(result)


def test_a_mark_age_with_no_bound_is_reported_and_not_judged() -> None:
    result = evaluate(
        portfolio=dated(),
        budget=full_budget(),
        approval_engine=full_engine(),
        mark_age=timedelta(hours=3),
    )
    assert reason_for(result, "TR-MARK-AGE").classification is ReasonClass.WARNING


def test_a_mark_older_than_the_owners_bound_blocks() -> None:
    result = evaluate(
        portfolio=dated(),
        budget=full_budget(),
        approval_engine=full_engine(max_mark_age=timedelta(hours=1)),
        mark_age=timedelta(hours=3),
    )
    assert result.status is ApprovalStatus.BLOCKED
    assert reason_for(result, "TR-MARK-AGE").classification is ReasonClass.BLOCKING


def test_an_unstated_mark_age_cannot_be_checked_against_a_configured_bound() -> None:
    result = evaluate(
        portfolio=dated(),
        budget=full_budget(),
        approval_engine=full_engine(max_mark_age=timedelta(hours=1)),
        mark_age=Absent("this reading priced nothing"),
    )
    entry = reason_for(result, "TR-MARK-AGE")
    assert entry.classification is ReasonClass.INDETERMINATE
    assert result.status is ApprovalStatus.INDETERMINATE


def test_an_unstated_mark_age_with_no_bound_is_only_a_warning() -> None:
    result = evaluate(
        portfolio=dated(),
        budget=full_budget(),
        approval_engine=full_engine(),
        mark_age=Absent("this reading priced nothing"),
    )
    assert reason_for(result, "TR-MARK-AGE").classification is ReasonClass.WARNING


def test_no_price_source_consulted_raises_no_mark_age_reason() -> None:
    """*'Nothing was priced'* and *'this page did not look'* are different facts."""
    result = evaluate(portfolio=dated(), budget=full_budget(), approval_engine=full_engine())
    assert "TR-MARK-AGE" not in codes(result)


# -- coverage of the reading itself ------------------------------------------


def test_an_unmarked_position_makes_the_whole_approval_indeterminate() -> None:
    result = evaluate(
        portfolio=state(line(mark=Absent("no mark was supplied")), equity=usdt("100000")),
        budget=full_budget(),
        approval_engine=full_engine(),
    )
    assert result.status is ApprovalStatus.INDETERMINATE
    assert "TR-MARKS" in codes(result)
    assert MARKET.value in reason_for(result, "TR-MARKS").statement


def test_an_unstopped_position_makes_open_risk_unmeasurable() -> None:
    result = evaluate(
        portfolio=state(line(stop=Absent("no commitment records a stop")), equity=usdt("100000")),
        budget=full_budget(),
        approval_engine=full_engine(),
    )
    assert result.status is ApprovalStatus.INDETERMINATE
    assert "TR-STOPS" in codes(result)


def test_a_clean_reading_raises_neither_coverage_reason() -> None:
    result = evaluate(budget=full_budget(), approval_engine=full_engine())
    assert not {"TR-MARKS", "TR-STOPS"} & codes(result)


# -- risk/reward -------------------------------------------------------------


def test_a_thin_ratio_warns_and_never_blocks() -> None:
    """Every risk/reward condition in the blueprint is a soft warning."""
    result = evaluate(
        budget=full_budget(),
        approval_engine=full_engine(minimum_risk_reward=Decimal("3")),
    )
    entry = reason_for(result, "TR-RR")
    assert entry.classification is ReasonClass.WARNING
    assert "never from the quality of the idea" in entry.statement
    assert result.status is not ApprovalStatus.BLOCKED


def test_a_ratio_at_the_minimum_raises_nothing() -> None:
    result = evaluate(
        budget=full_budget(),
        approval_engine=full_engine(minimum_risk_reward=Decimal("2.5")),
    )
    assert "TR-RR" not in codes(result)


def test_a_candidate_with_no_target_warns_that_the_ratio_is_absent() -> None:
    result = evaluate(
        proposal(targets=()), budget=full_budget(), approval_engine=full_engine()
    )
    entry = reason_for(result, "TR-RR")
    assert "An absent ratio is not a poor one" in entry.statement


def test_with_no_stated_minimum_a_valid_ratio_raises_nothing() -> None:
    result = evaluate(budget=full_budget(), approval_engine=full_engine())
    assert "TR-RR" not in codes(result)


# -- duplication -------------------------------------------------------------


def test_a_scale_in_is_reported_as_a_bet_already_held() -> None:
    result = evaluate(budget=full_budget(), approval_engine=full_engine())
    entry = reason_for(result, "TR-DUP")
    assert entry.classification is ReasonClass.WARNING
    assert "scale_in" in entry.statement


def test_the_same_pair_at_another_venue_is_named_as_duplication() -> None:
    """Two venues do not net: one long and one short is two counterparties."""
    elsewhere = line(market=EVEDEX_MARKET, mark=mark("61000"))
    result = evaluate(
        portfolio=state(elsewhere, equity=usdt("100000")),
        budget=full_budget(),
        approval_engine=full_engine(),
    )
    assert "do not net against each other" in reason_for(result, "TR-DUP").statement


def test_a_genuinely_new_bet_raises_no_duplication_warning() -> None:
    result = evaluate(
        proposal(market=ETH_MARKET),
        portfolio=state(line(), equity=usdt("100000")),
        budget=full_budget(),
        approval_engine=engine(classification=groups(BTC=["l1"], ETH=["l1"])),
    )
    assert "TR-DUP" not in codes(result)


def test_an_unsized_candidate_reports_no_duplication_because_there_is_no_impact() -> None:
    result = evaluate(proposal(stop=Decimal("61000")))
    assert "TR-DUP" not in codes(result)


# ==========================================================================
# 3. Portfolio-scope reasons — the owner's severity, never the engine's
# ==========================================================================


def over_budget() -> object:
    """A total-open-risk limit the existing 800 USDT position already exceeds."""
    return budget_with(
        ceiling("0.02"),
        total_risk_limit(Money(Decimal("500"), USDT)),
        concentration_limit(f"instrument:{MARKET.value}", Decimal("1")),
        concentration_limit("asset:BTC", Decimal("1")),
        concentration_limit(f"account:{ACCOUNT.value}", Decimal("1")),
        cluster_limit("l1", Decimal("1")),
    )


def test_an_exceeded_hard_limit_blocks_and_names_the_two_numbers() -> None:
    result = evaluate(
        portfolio=state(line(), equity=usdt("100000")),
        budget=over_budget(),
        approval_engine=full_engine(),
    )
    assert result.status is ApprovalStatus.BLOCKED
    entry = reason_for(result, "PF-LIMIT-total_open_risk")
    assert entry.classification is ReasonClass.BLOCKING
    assert entry.scope is ReasonScope.PORTFOLIO
    assert "against a stated ceiling of 500 USDT" in entry.statement


def test_an_exceeded_advisory_limit_only_warns_because_the_owner_said_so() -> None:
    """Severity is a field the owner sets; this engine reads it and chooses none."""
    advisory = budget_with(
        ceiling("0.02"),
        total_risk_limit(
            Money(Decimal("500"), USDT), severity=LimitSeverity.ADVISORY
        ),
        concentration_limit(f"instrument:{MARKET.value}", Decimal("1")),
        concentration_limit("asset:BTC", Decimal("1")),
        concentration_limit(f"account:{ACCOUNT.value}", Decimal("1")),
        cluster_limit("l1", Decimal("1")),
    )
    result = evaluate(
        portfolio=state(line(), equity=usdt("100000")),
        budget=advisory,
        approval_engine=full_engine(),
    )
    entry = reason_for(result, "PF-LIMIT-total_open_risk")
    assert entry.classification is ReasonClass.WARNING
    assert result.status is not ApprovalStatus.BLOCKED


def test_a_limit_reached_exactly_warns_rather_than_blocks() -> None:
    """A stated maximum is not breached by touching it — the next trade is."""
    exact = budget_with(
        ceiling("0.02"),
        total_risk_limit(Money(Decimal("1800"), USDT)),
        concentration_limit(f"instrument:{MARKET.value}", Decimal("1")),
        concentration_limit("asset:BTC", Decimal("1")),
        concentration_limit(f"account:{ACCOUNT.value}", Decimal("1")),
        cluster_limit("l1", Decimal("1")),
    )
    result = evaluate(
        portfolio=state(line(), equity=usdt("100000")),
        budget=exact,
        approval_engine=full_engine(),
    )
    entry = reason_for(result, "PF-LIMIT-total_open_risk")
    assert entry.classification is ReasonClass.WARNING
    assert "there is no room left after this" in entry.statement
    assert result.status is not ApprovalStatus.BLOCKED


def test_a_hard_open_risk_budget_bounds_the_size_rather_than_breaching_it() -> None:
    """The sizer respects the budget, so the after-state lands *on* the limit.

    Worth its own test because it is the behaviour that makes the "newly binding"
    case below hard to construct with a total-open-risk limit: a hard budget
    cannot be exceeded by a size this engine produced, only reached.
    """
    tight = budget_with(ceiling("0.02"), total_risk_limit(Money(Decimal("1200"), USDT)))
    result = evaluate(
        portfolio=state(line(), equity=usdt("100000")),
        budget=tight,
        approval_engine=full_engine(),
    )
    assert result.recommendation.money_at_risk == usdt("400")
    assert result.open_risk_after == usdt("1200")
    assert reason_for(result, "PF-LIMIT-total_open_risk").classification is (
        ReasonClass.WARNING
    )


def test_a_limit_the_trade_itself_moves_over_says_the_trade_did_it() -> None:
    """*'This breaches your cap'* and *'you were already over'* are two sentences.

    A concentration limit, because it is one the sizer does not bound against:
    the position is sized inside the open-risk budget and still tips the share of
    that budget sitting in one instrument past the owner's cap.
    """
    eth = line(
        market=ETH_MARKET,
        quantity=Quantity(Decimal("2"), AssetCode("ETH")),
        entry=Decimal("3000"),
        stop=Decimal("2600"),
        mark=mark("3100"),
    )
    tipping = budget_with(
        ceiling("0.02"),
        total_risk_limit(Money(Decimal("6000"), USDT)),
        concentration_limit(
            f"instrument:{MARKET.value}",
            Decimal("0.6"),
            unit=LimitUnit.PERCENT_OF_OPEN_RISK,
        ),
    )
    result = evaluate(
        portfolio=state(line(), eth, equity=usdt("100000")),
        budget=tipping,
        approval_engine=full_engine(),
    )
    concentration = next(
        limit for limit in tipping.limits if limit.scope is LimitScope.CONCENTRATION
    )
    entry = reason_for(result, f"PF-LIMIT-{concentration.limit_id}")
    assert entry.classification is ReasonClass.BLOCKING
    assert "This trade is what moves it there" in entry.statement
    assert result.status is ApprovalStatus.BLOCKED


def test_an_unmeasurable_hard_limit_is_indeterminate_and_never_within() -> None:
    """`AP` §15.5 property 2, at the point it actually matters."""
    drawdown = risk_limit(
        "drawdown",
        scope=LimitScope.DRAWDOWN,
        value=Decimal("0.2"),
        unit=LimitUnit.PERCENT_FROM_PEAK,
    )
    result = evaluate(budget=full_budget(drawdown), approval_engine=full_engine())
    entry = reason_for(result, "PF-LIMIT-drawdown")
    assert entry.classification is ReasonClass.INDETERMINATE
    assert "not a limit that was met" in entry.statement
    assert result.status is ApprovalStatus.INDETERMINATE


def test_an_unmeasurable_advisory_limit_is_only_a_warning() -> None:
    drawdown = risk_limit(
        "drawdown",
        scope=LimitScope.DRAWDOWN,
        value=Decimal("0.2"),
        unit=LimitUnit.PERCENT_FROM_PEAK,
        severity=LimitSeverity.ADVISORY,
    )
    result = evaluate(budget=full_budget(drawdown), approval_engine=full_engine())
    assert reason_for(result, "PF-LIMIT-drawdown").classification is ReasonClass.WARNING


def test_a_limit_measured_as_a_bare_count_prints_without_a_currency() -> None:
    """`MAX_CONCURRENT_POSITIONS` is a count, and a count has no asset."""
    concurrent = risk_limit(
        "max_positions",
        scope=LimitScope.MAX_CONCURRENT_POSITIONS,
        value=Decimal("1"),
        unit=LimitUnit.COUNT,
    )
    result = evaluate(
        portfolio=state(line(), equity=usdt("100000")),
        budget=full_budget(concurrent),
        approval_engine=full_engine(),
    )
    entry = reason_for(result, "PF-LIMIT-max_positions")
    assert entry.classification is ReasonClass.BLOCKING
    assert "2 against a stated ceiling of 1" in entry.statement
    assert "USDT" not in entry.statement


def test_a_limit_comfortably_within_produces_no_reason_at_all() -> None:
    result = evaluate(budget=full_budget(), approval_engine=full_engine())
    assert "PF-LIMIT-total_open_risk" not in codes(result)


def test_a_periodic_limit_is_measured_on_the_owners_own_calendar() -> None:
    """The `OwnerContext` is read for a boundary and never for a threshold."""
    period_loss = risk_limit(
        "daily_loss",
        scope=LimitScope.PERIOD_LOSS,
        value=Money(Decimal("500"), USDT),
        unit=LimitUnit.MONEY,
        period=LimitPeriod.DAY,
    )
    result = evaluate(budget=full_budget(period_loss), approval_engine=full_engine())
    entry = reason_for(result, "PF-LIMIT-daily_loss")
    assert entry.classification is ReasonClass.INDETERMINATE
    assert "closed-trip series" in entry.statement


# -- coverage gaps -----------------------------------------------------------


def test_every_unconstrained_axis_is_named_rather_than_passed_over() -> None:
    """The thing a constraint check structurally cannot report."""
    result = evaluate()
    assert {
        "PF-UNCONSTRAINED-INSTRUMENT",
        "PF-UNCONSTRAINED-ASSET",
        "PF-UNCONSTRAINED-ACCOUNT",
        "PF-UNCONSTRAINED-GROUP",
        "PF-UNCONSTRAINED-TOTAL-RISK",
    } <= codes(result)
    entry = reason_for(result, "PF-UNCONSTRAINED-ASSET")
    assert "not an axis that was found acceptable" in entry.statement
    assert entry.subject == "asset:BTC"


def test_a_fully_constrained_budget_names_no_gap() -> None:
    result = evaluate(budget=full_budget(), approval_engine=full_engine())
    assert not {code for code in codes(result) if code.startswith("PF-UNCONSTRAINED")}


def test_a_limit_on_another_asset_does_not_cover_this_candidate() -> None:
    """The key must name *this* candidate's value on the axis, not any value."""
    elsewhere = budget_with(ceiling("0.02"), concentration_limit("asset:ETH", Decimal("1")))
    assert "PF-UNCONSTRAINED-ASSET" in codes(evaluate(budget=elsewhere))


def test_an_unclassified_asset_reports_that_its_group_exposure_was_not_measured() -> None:
    entry = reason_for(evaluate(), "PF-UNCONSTRAINED-GROUP")
    assert "belongs to no group" in entry.statement
    assert "not the same as measuring it and finding none" in entry.statement


def test_a_classified_asset_with_no_cluster_limit_gets_the_other_sentence() -> None:
    result = evaluate(
        budget=budget_with(ceiling("0.02")),
        approval_engine=engine(classification=groups(BTC=["l1", "majors"])),
    )
    entry = reason_for(result, "PF-UNCONSTRAINED-GROUP")
    assert "'l1', 'majors'" in entry.statement
    assert "no cluster limit" in entry.statement


def test_a_cluster_limit_covering_every_group_names_no_gap() -> None:
    result = evaluate(
        budget=full_budget(),
        approval_engine=engine(classification=groups(BTC=["l1"])),
    )
    assert "PF-UNCONSTRAINED-GROUP" not in codes(result)


def test_the_reported_axes_are_a_closed_named_set() -> None:
    """A fifth axis is a deliberate edit here rather than an emergent one."""
    from fmis.portfolio_risk import ExposureDimension

    assert REQUIRED_AXES == (
        ExposureDimension.INSTRUMENT,
        ExposureDimension.ASSET,
        ExposureDimension.ACCOUNT,
    )


# ==========================================================================
# 4. Status derivation
# ==========================================================================


def test_blocking_outranks_indeterminate() -> None:
    """A known breach must not be dropped in favour of an unknown one."""
    result = evaluate(
        proposal(stop=Decimal("61000")),
        portfolio=state(line(mark=Absent("no mark")), equity=usdt("100000")),
    )
    assert {"TR-STOP", "TR-MARKS"} <= codes(result)
    assert result.status is ApprovalStatus.BLOCKED


def test_warnings_alone_never_change_the_status() -> None:
    result = evaluate(budget=full_budget(), approval_engine=full_engine())
    assert result.warnings
    assert result.status is ApprovalStatus.APPROVED


# ==========================================================================
# 5. The engine's own construction and refusals
# ==========================================================================


def test_the_engine_holds_a_sizer_and_a_classification() -> None:
    from fmis.portfolio_risk import unclassified_map

    with pytest.raises(TypeError, match="PositionSizer"):
        ApprovalEngine(sizer=policy(), classification=unclassified_map("v1"))
    with pytest.raises(TypeError, match="ClassificationMap"):
        ApprovalEngine(sizer=PositionSizer(policy()), classification={})


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"state": "portfolio"}, "PortfolioState"),
        ({"budget": "swing"}, "RiskBudget"),
        ({"owner": "stockholm"}, "OwnerContext"),
        ({"mark_age": 3}, "timedelta, Absent or None"),
    ],
)
def test_a_malformed_call_raises_rather_than_answering(
    kwargs: dict[str, object], match: str
) -> None:
    values: dict[str, object] = {
        "state": state(line()),
        "budget": budget_with(),
        "owner": owner(),
    }
    values.update(kwargs)
    with pytest.raises(TypeError, match=match):
        engine().evaluate(proposal(), **values)  # type: ignore[arg-type]


def test_the_proposal_must_be_a_proposal() -> None:
    with pytest.raises(TypeError, match="PositionProposal"):
        engine().evaluate(
            MARKET, state=state(), budget=budget_with(), owner=owner()  # type: ignore[arg-type]
        )


def test_the_engine_names_no_trading_verdict_anywhere() -> None:
    """There is no `TAKE` and no `SKIP`, and there is no field either could sit in."""
    import fmis.position_sizing as package

    for name in package.__all__:
        assert "take_trade" not in name.lower()
        assert "skip" not in name.lower()
    assert {member.value for member in ApprovalStatus} == {
        "approved",
        "blocked",
        "indeterminate",
    }
