"""The three things an approval reads from the store, and none of them guessed.

Every resolver here follows one rule: **exactly one, or none — never the first.**
An approval scoped to the wrong account measures the wrong capacity pool and
reports a clean answer about a portfolio the owner does not have, so *"there are
three and you must say which"* is a refusal rather than a choice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from persistence_helpers import new_store, risk_budget, write_request
from trade_domain_helpers import ACCOUNT, AT, dust_policy, trade, trade_plan

from fmis.accounts import AccountId
from fmis.plan import TradePlan
from fmis.position_sizing import (
    accounts_in,
    budget_in_effect,
    plan_to_size,
    sole_account,
)
from fmis.provenance import Absent
from fmis.risk import RiskBudget


def store(root: Path, **overrides: Any) -> Any:
    return new_store(root, dust=overrides.pop("dust", dust_policy()), **overrides)


# ==========================================================================
# 1. The budget
# ==========================================================================


def test_a_store_with_no_budget_names_the_gap_in_the_owners_policy(tmp_path: Path) -> None:
    absent = budget_in_effect(store(tmp_path), at=AT(12))
    assert isinstance(absent, Absent)
    assert "gap in the owner's own policy" in absent.reason


def test_the_single_lineage_in_force_is_returned(tmp_path: Path) -> None:
    opened = store(tmp_path)
    opened.risk.create(risk_budget(), request=write_request())
    found = budget_in_effect(opened, at=AT(12))
    assert isinstance(found, RiskBudget)
    assert found.budget_id == "swing_budget"


def test_two_lineages_are_a_refusal_rather_than_an_id_sort(tmp_path: Path) -> None:
    opened = store(tmp_path)
    opened.risk.create(risk_budget(), request=write_request())
    opened.risk.create(
        risk_budget(budget_id="day_budget"), request=write_request()
    )
    absent = budget_in_effect(opened, at=AT(12))
    assert isinstance(absent, Absent)
    assert "day_budget, swing_budget" in absent.reason


def test_a_budget_not_yet_in_force_is_the_repositorys_own_absence(tmp_path: Path) -> None:
    """*'No budget existed'* and *'the first budget applied'* are different facts."""
    opened = store(tmp_path)
    opened.risk.create(risk_budget(effective_from=AT(20)), request=write_request())
    absent = budget_in_effect(opened, at=AT(12))
    assert isinstance(absent, Absent)
    assert "no risk budget was in force" in absent.reason


# ==========================================================================
# 2. The account
# ==========================================================================


def test_an_empty_store_can_infer_no_account(tmp_path: Path) -> None:
    absent = sole_account(store(tmp_path))
    assert isinstance(absent, Absent)
    assert "records no fill in any account" in absent.reason


def test_the_one_account_a_store_records_fills_in_is_returned(tmp_path: Path) -> None:
    opened = store(tmp_path)
    opened.trades.create(trade(), request=write_request())
    assert sole_account(opened) == ACCOUNT
    assert accounts_in(opened) == (ACCOUNT.value,)


def test_two_accounts_are_a_refusal_because_books_never_share_capacity(
    tmp_path: Path,
) -> None:
    opened = store(tmp_path)
    opened.trades.create(trade(), request=write_request())
    opened.trades.create(
        trade(account=AccountId("evedex_main"), occurred_at=AT(10)),
        request=write_request(),
    )
    absent = sole_account(opened)
    assert isinstance(absent, Absent)
    assert "binance_spot, evedex_main" in absent.reason
    assert accounts_in(opened) == ("binance_spot", "evedex_main")


# ==========================================================================
# 3. The commitment
# ==========================================================================


def test_a_recorded_commitment_is_read_back_whole(tmp_path: Path) -> None:
    opened = store(tmp_path)
    recorded = trade_plan()
    opened.plans.create(recorded, request=write_request())
    found = plan_to_size(opened, recorded.plan_id)
    assert isinstance(found, TradePlan)
    assert found.initial_invalidation == recorded.initial_invalidation


def test_the_right_commitment_is_found_among_several(tmp_path: Path) -> None:
    """A store holding two plans must return the one that was asked for."""
    opened = store(tmp_path)
    first = trade_plan()
    second = trade_plan(committed_at=AT(11), created_at=AT(11))
    for plan in (first, second):
        opened.plans.create(plan, request=write_request())
    assert plan_to_size(opened, second.plan_id).plan_id == second.plan_id
    assert plan_to_size(opened, first.plan_id).plan_id == first.plan_id


def test_an_unknown_commitment_says_what_a_stop_is_for(tmp_path: Path) -> None:
    absent = plan_to_size(store(tmp_path), "trade_plan-nope-20260812T090000Z-0000")
    assert isinstance(absent, Absent)
    assert "a stop is what a size is computed from" in absent.reason


# ==========================================================================
# 4. Types
# ==========================================================================


@pytest.mark.parametrize(
    "call",
    [
        lambda: budget_in_effect("store", at=AT(12)),
        lambda: sole_account("store"),
        lambda: accounts_in("store"),
        lambda: plan_to_size("store", "plan-1"),
    ],
)
def test_every_reader_requires_a_real_store(call: Any) -> None:
    with pytest.raises(TypeError, match="TradingStore"):
        call()


def test_the_instant_must_be_utc(tmp_path: Path) -> None:
    from datetime import datetime

    with pytest.raises(Exception):
        budget_in_effect(store(tmp_path), at=datetime(2026, 8, 12, 12, 0))
