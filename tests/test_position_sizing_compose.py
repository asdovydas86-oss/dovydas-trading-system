"""The outer edge: a store on disk, a price snapshot, one approval.

Everything here runs against a **real store on a real temporary directory** and
**no network**: the price snapshot is a value, exactly as it is for
`fmis.valuation`, so the whole composition root is exercisable without a
provider.

The assertions that matter are about the preconditions: a missing risk budget is
a refusal naming what to record, an unresolvable account is another, and a
corrupt store is reported as a message rather than a traceback.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from marks_helpers import snapshot as price_snapshot
from persistence_helpers import risk_budget, write_request
from position_sizing_helpers import ceiling, policy, proposal
from trade_domain_helpers import ACCOUNT, AT, trade, trade_plan
from valuation_helpers import store_with, with_cash

from fmis.accounts import AccountId, Book, OwnerContext
from fmis.money import AssetCode
from fmis.position_sizing import (
    APPROVAL_CLASSIFICATION_VERSION,
    DEFAULT_BOOK,
    DEFAULT_OWNER_TIMEZONE,
    ApprovalEngine,
    ApprovalResult,
    ApprovalStatus,
    ApprovalUnavailableError,
    PositionProposal,
    engine_for,
    owner_context,
    portfolio_for,
    proposal_for_plan,
    resolve_account,
    run_approval,
)
from fmis.valuation import PortfolioStoreError


def planted(root: Path, *, budget: Any = None, **kwargs: Any) -> Any:
    """A store holding one fill, a cash snapshot and — unless refused — a budget."""
    store = store_with(root, trade(), snapshots=(with_cash(),), **kwargs)
    if budget is not False:
        store.risk.create(
            risk_budget(limits=(ceiling("0.02"),)) if budget is None else budget,
            request=write_request(),
        )
    return store


def approve(root: Path, **overrides: Any) -> ApprovalResult:
    values: dict[str, Any] = {
        "proposal": proposal(),
        "as_of": AT(12),
        "policy": policy(risk_fraction=Decimal("0.01")),
        "read_marks": False,
    }
    values.update(overrides)
    return run_approval(root, **values)


# ==========================================================================
# 1. End to end, without a network
# ==========================================================================


def test_one_approval_runs_end_to_end_against_a_real_store(tmp_path: Path) -> None:
    planted(tmp_path)
    result = approve(tmp_path)
    assert isinstance(result, ApprovalResult)
    assert result.evaluated_at == AT(12)
    assert result.before_check.budget_id == "swing_budget"


def test_skipping_the_price_fetch_leaves_the_answer_indeterminate(
    tmp_path: Path,
) -> None:
    """*'This page did not look'* is an honest answer, and it is not `APPROVED`."""
    planted(tmp_path)
    result = approve(tmp_path)
    assert result.status is ApprovalStatus.INDETERMINATE
    assert "TR-MARKS" in {reason.code for reason in result.reasons}


def test_the_portfolio_is_the_valuation_layers_own_reading(tmp_path: Path) -> None:
    planted(tmp_path)
    valuation = portfolio_for(tmp_path, as_of=AT(12), read_marks=False)
    assert valuation.state.as_of == AT(12)
    assert valuation.state.portfolio_id == "owner_portfolio"


# ==========================================================================
# 2. Preconditions — refusals the owner can act on
# ==========================================================================


def test_a_store_with_no_budget_refuses_rather_than_approving_nothing(
    tmp_path: Path,
) -> None:
    """`APPROVED` would mean *'nothing you set was breached'* where nothing is set."""
    planted(tmp_path, budget=False)
    with pytest.raises(ApprovalUnavailableError, match="Record a risk budget"):
        approve(tmp_path)


def test_an_account_is_resolved_from_the_only_one_the_store_records(
    tmp_path: Path,
) -> None:
    planted(tmp_path)
    assert resolve_account(tmp_path, stated=None) == ACCOUNT


def test_a_named_account_is_taken_at_its_word(tmp_path: Path) -> None:
    planted(tmp_path)
    assert resolve_account(tmp_path, stated="other") == AccountId("other")


def test_an_unresolvable_account_is_a_refusal_naming_the_remedy(
    tmp_path: Path,
) -> None:
    with pytest.raises(ApprovalUnavailableError, match="Name one explicitly"):
        resolve_account(tmp_path, stated=None)


# ==========================================================================
# 3. Sizing a recorded commitment — the Trade Capture integration
# ==========================================================================


def test_a_recorded_commitment_supplies_the_stop_and_the_ladder(tmp_path: Path) -> None:
    store = planted(tmp_path)
    recorded = trade_plan()
    store.plans.create(recorded, request=write_request())
    built = proposal_for_plan(
        tmp_path, plan_id=recorded.plan_id, account=ACCOUNT, entry=Decimal("60000")
    )
    assert isinstance(built, PositionProposal)
    assert built.stop == recorded.initial_invalidation
    assert built.targets == recorded.targets
    assert built.plan_id == recorded.plan_id


def test_an_unknown_commitment_is_a_refusal(tmp_path: Path) -> None:
    planted(tmp_path)
    with pytest.raises(ApprovalUnavailableError, match="holds no commitment"):
        proposal_for_plan(
            tmp_path,
            plan_id="trade_plan-nope-20260812T090000Z-0000",
            account=ACCOUNT,
            entry=Decimal("60000"),
        )


# ==========================================================================
# 4. A corrupt store is a message, never a traceback
# ==========================================================================


def test_a_corrupt_store_is_reported_as_the_bridges_own_error(tmp_path: Path) -> None:
    planted(tmp_path)
    index = next(tmp_path.rglob("*.jsonl"))
    index.write_text("{ not json\n", encoding="utf-8")
    with pytest.raises(PortfolioStoreError, match="could not be read"):
        approve(tmp_path)


def test_a_corrupt_store_also_defeats_the_account_resolver(tmp_path: Path) -> None:
    planted(tmp_path)
    index = next(tmp_path.rglob("*.jsonl"))
    index.write_text("{ not json\n", encoding="utf-8")
    with pytest.raises(PortfolioStoreError, match="could not be read"):
        resolve_account(tmp_path, stated=None)


def test_a_corrupt_store_defeats_the_plan_reader_the_same_way(tmp_path: Path) -> None:
    planted(tmp_path)
    index = next(tmp_path.rglob("*.jsonl"))
    index.write_text("{ not json\n", encoding="utf-8")
    with pytest.raises(PortfolioStoreError, match="could not be read"):
        proposal_for_plan(
            tmp_path, plan_id="anything", account=ACCOUNT, entry=Decimal("1")
        )


# ==========================================================================
# 5. The defaults, and what each of them is
# ==========================================================================


def test_the_owner_context_is_a_locale_and_never_a_threshold() -> None:
    built = owner_context(base_currency="USDT")
    assert isinstance(built, OwnerContext)
    assert built.display_timezone == DEFAULT_OWNER_TIMEZONE
    assert built.tax_period_timezone == DEFAULT_OWNER_TIMEZONE
    assert built.base_currency == AssetCode("USDT")


def test_the_owner_context_takes_a_stated_zone_and_an_asset_code() -> None:
    built = owner_context(base_currency=AssetCode("SEK"), timezone="Europe/London")
    assert built.display_timezone == "Europe/London"


def test_the_default_book_is_the_one_the_daily_page_already_declares() -> None:
    from fmis.today import OBJECTIVE

    assert DEFAULT_BOOK is Book.SWING
    assert DEFAULT_BOOK.value == OBJECTIVE


def test_an_engine_is_built_once_with_an_honest_empty_classification() -> None:
    built = engine_for(policy())
    assert isinstance(built, ApprovalEngine)
    assert built.classification.version == APPROVAL_CLASSIFICATION_VERSION
    assert built.classification.is_empty


def test_a_supplied_classification_is_used_unchanged() -> None:
    from portfolio_risk_helpers import groups

    owner_map = groups(BTC=["l1"])
    assert engine_for(policy(), owner_map).classification is owner_map


# ==========================================================================
# 6. Argument validation — a typo in a flag is not a broken store
# ==========================================================================


def test_a_malformed_portfolio_id_raises_before_the_store_is_read(
    tmp_path: Path,
) -> None:
    planted(tmp_path)
    with pytest.raises(Exception) as caught:
        approve(tmp_path, portfolio_id="not an identifier!")
    assert not isinstance(caught.value, PortfolioStoreError)


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"proposal": "BTCUSDT"}, "PositionProposal"),
        ({"policy": "owner_sizing"}, "SizingPolicy"),
    ],
)
def test_a_malformed_call_raises_a_type_error(
    tmp_path: Path, kwargs: dict[str, Any], match: str
) -> None:
    planted(tmp_path)
    with pytest.raises(TypeError, match=match):
        approve(tmp_path, **kwargs)


# ==========================================================================
# 7. With prices, the answer becomes measurable
# ==========================================================================


def test_a_priced_reading_makes_the_exposure_figures_real(tmp_path: Path) -> None:
    """The one test here that goes through the price path, with a value not a fetch."""
    from fmis.valuation import value_portfolio

    store = planted(tmp_path)
    valuation = value_portfolio(
        store,
        portfolio_id="owner_portfolio",
        base_currency="USDT",
        as_of=AT(12),
        prices=price_snapshot(61000.0, taken_at=AT(12)),
    )
    result = engine_for(policy(risk_fraction=Decimal("0.01"))).evaluate(
        proposal(),
        state=valuation.state,
        budget=risk_budget(limits=(ceiling("0.02"),)),
        owner=owner_context(base_currency="USDT"),
        mark_age=valuation.mark_age,
    )
    assert "TR-MARKS" not in {reason.code for reason in result.reasons}
    assert result.recommendation.is_sized
