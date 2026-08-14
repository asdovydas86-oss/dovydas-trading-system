"""`PlanRepository` — the tenth repository, and the one that refuses hardest.

A `TradePlan` is a captured artifact and every edit verb raises. That is not a
classification detail: *"did I honour my stop?"* is answerable only if the stop
cannot be changed after the trade moved, so the refusal **is** the feature.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from persistence_helpers import NOW, new_store, write_request
from trade_domain_helpers import AT, MARKET, OTHER_MARKET, trade_plan

from fmis.persistence import (
    DurabilityClass,
    FrozenRecordError,
    RecordKind,
    SPECS,
    StorageShape,
    TradingStore,
    UnknownRecordKindError,
    spec_for_record,
)
from fmis.plan import TRADE_PLAN_TYPE_SLUG, TradePlan
from fmis.snapshotting import TradeDirection


@pytest.fixture()
def store(tmp_path: Path) -> TradingStore:
    return new_store(tmp_path)


# --------------------------------------------------------------------------
# The spec table.
# --------------------------------------------------------------------------


def test_a_plan_is_a_frozen_record_file_keyed_on_its_market() -> None:
    spec = SPECS[RecordKind.TRADE_PLAN]
    assert spec.durability is DurabilityClass.CAPTURED_ARTIFACT
    assert spec.shape is StorageShape.RECORD_FILE
    assert spec.type_slug == TRADE_PLAN_TYPE_SLUG
    assert spec.is_frozen is True
    assert spec.supersedes_kinds == frozenset()


def test_a_plan_may_not_be_filed_before_it_is_committed_to() -> None:
    assert SPECS[RecordKind.TRADE_PLAN].moment_may_be_future is False


def test_the_spec_reads_the_plans_own_identity_and_scope() -> None:
    plan = trade_plan()
    spec = spec_for_record(plan)
    assert spec.identity(plan) == plan.plan_id
    assert spec.digest(plan) == plan.content_digest
    assert spec.moment(plan) == plan.committed_at
    assert spec.lineage_key(plan) == MARKET.value
    scope = spec.owner_scope(plan)
    assert (scope.book, scope.market, scope.account) == ("swing", MARKET.value, None)


# --------------------------------------------------------------------------
# Writing.
# --------------------------------------------------------------------------


def test_a_committed_plan_is_stored_and_reads_back_identical(
    store: TradingStore,
) -> None:
    plan = trade_plan()
    receipt = store.plans.create(plan, request=write_request())
    assert receipt.created is True
    assert receipt.record_id == plan.plan_id
    assert store.plans.load(plan.plan_id) == plan


def test_committing_the_identical_plan_twice_stores_one_record(
    store: TradingStore,
) -> None:
    plan = trade_plan()
    store.plans.create(plan, request=write_request())
    second = store.plans.create(plan, request=write_request())
    assert second.created is False
    assert store.plans.count() == 1


def test_an_idempotent_republish_appends_no_second_journal_event(
    store: TradingStore,
) -> None:
    plan = trade_plan()
    store.plans.create(plan, request=write_request())
    before = len(store.write_journal.events())
    store.plans.create(plan, request=write_request())
    assert len(store.write_journal.events()) == before


def test_a_plan_cannot_be_updated(store: TradingStore) -> None:
    plan = trade_plan()
    store.plans.create(plan, request=write_request())
    with pytest.raises(FrozenRecordError, match="captured artifact"):
        store.plans.update(plan.plan_id)


def test_a_plan_cannot_be_replaced(store: TradingStore) -> None:
    """A widened stop is an *amendment*, which this build does not implement."""
    plan = trade_plan()
    store.plans.create(plan, request=write_request())
    with pytest.raises(FrozenRecordError, match="no edit path"):
        store.plans.replace(plan.plan_id, trade_plan(initial_invalidation=Decimal("57000")))


def test_the_plan_repository_refuses_a_record_it_does_not_own(
    store: TradingStore,
) -> None:
    from trade_domain_helpers import trade

    with pytest.raises(UnknownRecordKindError, match="does not own"):
        store.plans.create(trade(), request=write_request())


def test_a_revised_commitment_is_a_second_record_and_both_stay_readable(
    store: TradingStore,
) -> None:
    """There is no supersession here. Two commitments are two decisions."""
    first = trade_plan()
    second = trade_plan(initial_invalidation=Decimal("57000"), committed_at=AT(11))
    store.plans.create(first, request=write_request())
    store.plans.create(second, request=write_request())
    assert store.plans.load(first.plan_id) == first
    assert store.plans.load(second.plan_id) == second
    assert store.plans.count() == 2


# --------------------------------------------------------------------------
# Reading.
# --------------------------------------------------------------------------


def test_plans_are_returned_in_commitment_order(store: TradingStore) -> None:
    late = trade_plan(committed_at=AT(14))
    early = trade_plan(committed_at=AT(10))
    store.plans.create(late, request=write_request())
    store.plans.create(early, request=write_request())
    assert [plan.committed_at for plan in store.plans.plans()] == [AT(10), AT(14)]


def test_for_market_selects_only_that_market(store: TradingStore) -> None:
    here = trade_plan()
    elsewhere = trade_plan(market=OTHER_MARKET)
    store.plans.create(here, request=write_request())
    store.plans.create(elsewhere, request=write_request())
    assert store.plans.for_market(MARKET.value) == (here,)
    assert store.plans.for_market(OTHER_MARKET.value) == (elsewhere,)


def test_the_latest_commitment_in_a_market_is_the_most_recent_one(
    store: TradingStore,
) -> None:
    store.plans.create(trade_plan(committed_at=AT(10)), request=write_request())
    late = trade_plan(committed_at=AT(14))
    store.plans.create(late, request=write_request())
    assert store.plans.latest_for_market(MARKET.value) == late


def test_a_market_with_no_commitment_reports_none_rather_than_raising(
    store: TradingStore,
) -> None:
    assert store.plans.latest_for_market(MARKET.value) is None


def test_plan_ids_lists_every_stored_commitment(store: TradingStore) -> None:
    first = trade_plan(committed_at=AT(10))
    second = trade_plan(committed_at=AT(14))
    for plan in (first, second):
        store.plans.create(plan, request=write_request())
    assert store.plans.plan_ids() == (first.plan_id, second.plan_id)


def test_live_at_excludes_a_commitment_not_yet_made(store: TradingStore) -> None:
    future = trade_plan(committed_at=AT(9, day=20))
    store.plans.create(
        future, request=write_request(written_at=AT(9, day=21))
    )
    assert store.plans.live_at(AT(9, day=19)) == ()
    assert store.plans.live_at(AT(9, day=21)) == (future,)


def test_live_at_excludes_an_expired_commitment(store: TradingStore) -> None:
    plan = trade_plan(expires_at=AT(9, day=13))
    store.plans.create(plan, request=write_request())
    assert store.plans.live_at(AT(10, day=12)) == (plan,)
    assert store.plans.live_at(AT(9, day=14)) == ()


def test_an_unexpiring_commitment_stays_live(store: TradingStore) -> None:
    plan = trade_plan()
    store.plans.create(plan, request=write_request())
    assert store.plans.live_at(NOW + timedelta(days=365)) == (plan,)


# --------------------------------------------------------------------------
# Integrity.
# --------------------------------------------------------------------------


def test_a_stored_plan_survives_a_full_store_verification(
    store: TradingStore,
) -> None:
    store.plans.create(trade_plan(), request=write_request())
    result = store.verify()
    assert result.ok is True
    assert result.integrity_failures == ()


def test_the_index_can_be_thrown_away_and_rebuilt(store: TradingStore) -> None:
    plan = trade_plan()
    store.plans.create(plan, request=write_request())
    before = store.store.index.entries()
    store.store.layout.index_path.unlink()
    store.store.rebuild_index()
    assert store.store.index.entries() == before


def test_a_plan_reaches_disk_under_its_kind_year_and_month(
    store: TradingStore,
) -> None:
    receipt = store.plans.create(trade_plan(), request=write_request())
    assert receipt.relative_path.startswith("records/trade_plan/2026/08/")
    assert (store.root / receipt.relative_path).is_file()


def test_a_short_commitment_stores_and_reloads(store: TradingStore) -> None:
    plan = trade_plan(
        direction=TradeDirection.SHORT,
        initial_invalidation=Decimal("62000"),
        targets=(Decimal("58000"),),
    )
    store.plans.create(plan, request=write_request())
    reloaded = store.plans.load(plan.plan_id)
    assert isinstance(reloaded, TradePlan)
    assert reloaded.direction is TradeDirection.SHORT
