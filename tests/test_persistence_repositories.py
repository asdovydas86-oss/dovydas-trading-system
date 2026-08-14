"""The ten repositories: what each one accepts, refuses, and answers.

The refusals are tested as hard as the successes. A store whose first rule is
*nothing is deleted and nothing is rewritten* is only as good as the verbs it turns
down, and every `update` in this package raises — the test below sweeps all ten
rather than trusting that a base class covers them.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from persistence_helpers import (
    ARCHIVE_RECORD_ID,
    NOW,
    analysis_record,
    journal_entry,
    new_store,
    portfolio_snapshot,
    risk_budget,
    risk_limit,
    write_request,
)
from trade_domain_helpers import (
    ACCOUNT,
    AT,
    BTC,
    MARKET,
    OTHER_MARKET,
    USDT,
    correction,
    decision_window,
    lifecycle_event,
    market_snapshot,
    proposal,
    quantity,
    trade,
)

from fmis.accounts import Book
from fmis.journal import JournalKind, JournalLink, LinkKind
from fmis.ledger import TradeStatus
from fmis.persistence import (
    FrozenRecordError,
    PersistenceError,
    ProjectionError,
    RecordKind,
    RecordMissingError,
    SearchCriteria,
    TradingStore,
    UnknownRecordKindError,
)
from fmis.proposal import LifecycleKind, ProposalState
from fmis.provenance import Absent
from fmis.risk import LimitPeriod, LimitScope, LimitSeverity, LimitUnit


@pytest.fixture
def store(tmp_path: Path) -> TradingStore:
    return new_store(tmp_path)


# --------------------------------------------------------------------------
# The composition root.
# --------------------------------------------------------------------------


def test_the_composition_root_wires_ten_repositories(store: TradingStore) -> None:
    # Widened for Milestone BK to admit `PlanRepository`, wired right after
    # `TradeRepository`: additive, and not a replacement for any existing one.
    assert len(store.repositories()) == 10
    assert len({id(repo) for repo in store.repositories()}) == 10


def test_every_repository_shares_one_store(store: TradingStore) -> None:
    """One store means one journal, which is what makes the audit trail complete."""
    for repository in store.repositories():
        assert repository.store is store.store


def test_a_dust_policy_is_required() -> None:
    with pytest.raises(TypeError, match="DustPolicy"):
        TradingStore("/tmp/nowhere", dust="0.00000001")  # type: ignore[arg-type]


def test_a_repository_owning_no_kind_is_refused(store: TradingStore) -> None:
    from fmis.persistence import Repository

    class Nothing(Repository):
        pass

    with pytest.raises(PersistenceError, match="declares no kinds"):
        Nothing(store.store)


# --------------------------------------------------------------------------
# `update` raises on all ten.
# --------------------------------------------------------------------------


def test_update_raises_on_every_repository(store: TradingStore) -> None:
    """No kind has an edit path, and the message names the legal one."""
    for repository in store.repositories():
        with pytest.raises((FrozenRecordError, ProjectionError)):
            repository.update("trade-x-20260812T100000Z-0123456789abcdef")


def test_a_frozen_kind_says_it_is_a_captured_artifact(store: TradingStore) -> None:
    subject = market_snapshot()
    store.snapshots.create(subject, request=write_request())
    with pytest.raises(FrozenRecordError, match="captured artifact"):
        store.snapshots.update(subject.snapshot_id)
    with pytest.raises(FrozenRecordError, match="captured artifact"):
        store.snapshots.replace(subject.snapshot_id)


def test_an_append_only_kind_points_at_supersession(store: TradingStore) -> None:
    subject = trade()
    store.trades.create(subject, request=write_request())
    with pytest.raises(FrozenRecordError, match="supersedes it"):
        store.trades.update(subject.event_id)


def test_a_repository_refuses_a_kind_it_does_not_own(store: TradingStore) -> None:
    with pytest.raises(UnknownRecordKindError, match="does not own"):
        store.trades.create(market_snapshot(), request=write_request())
    with pytest.raises(UnknownRecordKindError, match="does not own"):
        store.snapshots.entries(kind=RecordKind.TRADE)


def test_loading_another_repositorys_record_is_refused(store: TradingStore) -> None:
    subject = market_snapshot()
    store.snapshots.create(subject, request=write_request())
    with pytest.raises(UnknownRecordKindError, match="does not own"):
        store.journals.load(subject.snapshot_id)


# --------------------------------------------------------------------------
# TradeRepository.
# --------------------------------------------------------------------------


def test_a_draft_trade_is_refused(store: TradingStore) -> None:
    draft = trade(status=TradeStatus.DRAFT)
    with pytest.raises(PersistenceError, match="not in the ledger"):
        store.trades.create(draft, request=write_request())
    assert store.trades.count() == 0


def test_a_promoted_draft_is_accepted(store: TradingStore) -> None:
    assert store.trades.create(
        trade(status=TradeStatus.DRAFT).recorded(), request=write_request()
    ).created


def test_replacing_a_trade_appends_a_correction(store: TradingStore) -> None:
    original = trade()
    store.trades.create(original, request=write_request())
    replacement = trade(quantity=quantity("0.6"))
    fix = correction(original, replacement)
    receipt = store.trades.replace(
        original.event_id, replacement, correction=fix, request=write_request()
    )
    assert receipt.created
    assert store.trades.load(original.event_id) == original
    assert store.trades.load_latest(original.event_id) == replacement


def test_a_correction_naming_a_different_trade_is_refused(store: TradingStore) -> None:
    original = trade()
    other = trade(occurred_at=AT(12))
    store.trades.create(original, request=write_request())
    store.trades.create(other, request=write_request())
    fix = correction(other, trade(quantity=quantity("0.6")))
    with pytest.raises(PersistenceError, match="not the trade"):
        store.trades.replace(original.event_id, correction=fix, request=write_request())


def test_a_correction_carrying_a_different_replacement_is_refused(
    store: TradingStore,
) -> None:
    original = trade()
    store.trades.create(original, request=write_request())
    fix = correction(original, trade(quantity=quantity("0.6")))
    with pytest.raises(PersistenceError, match="not the trade that was supplied"):
        store.trades.replace(
            original.event_id,
            trade(quantity=quantity("0.7")),
            correction=fix,
            request=write_request(),
        )


def test_correcting_a_trade_this_store_does_not_hold_is_refused(
    store: TradingStore,
) -> None:
    original = trade()
    fix = correction(original, trade(quantity=quantity("0.6")))
    with pytest.raises(RecordMissingError, match="detected gap"):
        store.trades.replace(original.event_id, correction=fix, request=write_request())


def test_replacing_without_a_correction_is_refused(store: TradingStore) -> None:
    original = trade()
    store.trades.create(original, request=write_request())
    with pytest.raises(PersistenceError, match="needs the Correction"):
        store.trades.replace(original.event_id)


def test_trades_can_be_read_by_market_and_book(store: TradingStore) -> None:
    from fmis.money import AssetCode

    here = trade()
    elsewhere = trade(
        market=OTHER_MARKET, quantity=quantity("2", AssetCode("ETH")), price=Decimal("3000")
    )
    store.trades.create(here, request=write_request())
    store.trades.create(elsewhere, request=write_request())
    assert store.trades.for_market(MARKET.value) == (here,)
    assert store.trades.for_market(OTHER_MARKET.value) == (elsewhere,)
    assert store.trades.for_market(MARKET.value, book=Book.SWING) == (here,)
    assert store.trades.for_market(MARKET.value, book=Book.DAY) == ()


def test_load_latest_of_a_never_corrected_trade_is_itself(store: TradingStore) -> None:
    subject = trade()
    store.trades.create(subject, request=write_request())
    assert store.trades.load_latest(subject.event_id) == subject


# --------------------------------------------------------------------------
# LedgerRepository.
# --------------------------------------------------------------------------


def test_the_ledger_resolves_supersession(store: TradingStore) -> None:
    original = trade()
    store.trades.create(original, request=write_request())
    fix = correction(original, trade(quantity=quantity("0.6")))
    store.trades.replace(original.event_id, correction=fix, request=write_request())
    resolved = store.ledger.resolved()
    assert len(resolved) == 1
    assert resolved[0].trade.quantity.text == "0.6"
    assert resolved[0].was_corrected
    assert store.ledger.status_of(original.event_id) is TradeStatus.SUPERSEDED


def test_the_ledger_reports_stale_inputs(store: TradingStore) -> None:
    """What a frozen artifact's `consumed_sources` is compared against."""
    original = trade()
    store.trades.create(original, request=write_request())
    replacement = trade(quantity=quantity("0.6"))
    fix = correction(original, replacement)
    store.trades.replace(original.event_id, correction=fix, request=write_request())
    stale = store.ledger.stale_inputs()
    assert stale == {original.event_id: replacement.content_digest}


def test_the_ledger_will_not_publish_a_correction_directly(store: TradingStore) -> None:
    with pytest.raises(FrozenRecordError, match="TradeRepository.replace"):
        store.ledger.replace("trade-x-20260812T100000Z-0123456789abcdef")


def test_the_ledger_reads_both_kinds(store: TradingStore) -> None:
    original = trade()
    store.trades.create(original, request=write_request())
    fix = correction(original, trade(quantity=quantity("0.6")))
    store.trades.replace(original.event_id, correction=fix, request=write_request())
    assert len(store.ledger.trades()) == 1
    assert len(store.ledger.corrections()) == 1
    assert len(store.ledger.entries()) == 2


# --------------------------------------------------------------------------
# PositionRepository — the repository that stores nothing.
# --------------------------------------------------------------------------


def test_a_position_can_never_be_written(store: TradingStore) -> None:
    positions = store.positions.rebuild()
    with pytest.raises(ProjectionError, match="never stored"):
        store.positions.create(positions, request=write_request())
    with pytest.raises(ProjectionError):
        store.positions.update("anything")
    with pytest.raises(ProjectionError):
        store.positions.replace("anything")
    with pytest.raises(ProjectionError, match="no ids in this store"):
        store.positions.load("anything")


def test_positions_fold_from_the_resolved_ledger(store: TradingStore) -> None:
    store.trades.create(trade(), request=write_request())
    positions = store.positions.rebuild()
    assert len(positions) == 1
    assert positions[0].net_quantity.text == "0.5"
    assert positions[0].is_open


def test_deleting_and_recomputing_a_projection_gives_the_identical_answer(
    store: TradingStore,
) -> None:
    """Architecture §24.3's classification test, as a test."""
    store.trades.create(trade(), request=write_request())
    store.trades.create(trade(occurred_at=AT(12)), request=write_request())
    assert store.positions.rebuild() == store.positions.rebuild()
    assert store.positions.is_reproducible()


def test_positions_scope_to_a_book_or_market(store: TradingStore) -> None:
    store.trades.create(trade(), request=write_request())
    assert len(store.positions.load_by_owner(market=MARKET.value)) == 1
    assert store.positions.load_by_owner(market=OTHER_MARKET.value) == ()
    assert len(store.positions.load_by_owner(book=Book.SWING.value)) == 1
    assert store.positions.load_by_owner(book=Book.DAY.value) == ()


def test_open_positions_exclude_closed_ones(store: TradingStore) -> None:
    from fmis.ledger import TradeSide

    store.trades.create(trade(), request=write_request())
    store.trades.create(
        trade(occurred_at=AT(12), side=TradeSide.SELL), request=write_request()
    )
    assert store.positions.rebuild()[0].state.value == "closed"
    assert store.positions.open_positions() == ()


def test_a_position_repository_needs_a_dust_policy(store: TradingStore) -> None:
    from fmis.persistence import PositionRepository

    with pytest.raises(TypeError, match="DustPolicy"):
        PositionRepository(store.store, dust=None)  # type: ignore[arg-type]


def test_fee_drag_is_summed_across_positions(store: TradingStore) -> None:
    store.trades.create(trade(), request=write_request())
    total = store.positions.total_fees_in(USDT)
    assert total.amount == Decimal("15")
    assert total.asset == USDT


# --------------------------------------------------------------------------
# PortfolioRepository.
# --------------------------------------------------------------------------


def test_a_portfolio_snapshot_is_frozen(store: TradingStore) -> None:
    subject = portfolio_snapshot()
    store.portfolios.create(subject, request=write_request())
    with pytest.raises(FrozenRecordError):
        store.portfolios.replace(subject.snapshot_id)
    assert store.portfolios.load(subject.snapshot_id) == subject


def test_three_snapshots_of_one_portfolio_are_three_observations(
    store: TradingStore,
) -> None:
    for filed, hour in enumerate((9, 10, 11)):
        store.portfolios.create(
            portfolio_snapshot(as_of=AT(hour)),
            request=write_request(written_at=NOW + timedelta(hours=filed)),
        )
    assert len(store.portfolios.snapshots("main")) == 3
    assert store.portfolios.latest("main").as_of == AT(11)
    assert store.portfolios.as_of("main", AT(10, minute=30)).as_of == AT(10)
    assert store.portfolios.as_of("main", AT(8)) is None
    assert store.portfolios.portfolio_ids() == ("main",)


def test_the_latest_snapshot_of_an_unknown_portfolio_is_none(
    store: TradingStore,
) -> None:
    assert store.portfolios.latest("main") is None


# --------------------------------------------------------------------------
# RiskRepository.
# --------------------------------------------------------------------------


def test_the_first_budget_is_created_and_the_next_is_revised(
    store: TradingStore,
) -> None:
    first = risk_budget(effective_from=AT(0))
    store.risk.create(first, request=write_request())
    second = risk_budget(effective_from=AT(0, day=15), risk_policy_version=2)
    store.risk.revise(second, request=write_request(written_at=NOW + timedelta(hours=1)))
    assert store.risk.versions_of("swing_budget") == (first, second)
    assert store.risk.budget_ids() == ("swing_budget",)


def test_revising_a_budget_that_does_not_exist_is_refused(store: TradingStore) -> None:
    with pytest.raises(RecordMissingError, match="created, not revised"):
        store.risk.revise(risk_budget(), request=write_request())


def test_a_back_dated_budget_generation_is_refused(store: TradingStore) -> None:
    """Back-dating one would change which limits an already-frozen check ran against."""
    store.risk.create(risk_budget(effective_from=AT(0, day=10)), request=write_request())
    with pytest.raises(PersistenceError, match="moves forward"):
        store.risk.revise(
            risk_budget(effective_from=AT(0, day=5), risk_policy_version=2),
            request=write_request(written_at=NOW + timedelta(hours=1)),
        )


def test_a_budget_generation_may_take_effect_in_the_future(store: TradingStore) -> None:
    store.risk.create(risk_budget(effective_from=AT(0)), request=write_request())
    scheduled = risk_budget(
        effective_from=NOW + timedelta(days=7), risk_policy_version=2
    )
    assert store.risk.revise(
        scheduled, request=write_request(written_at=NOW + timedelta(hours=1))
    ).created
    assert store.risk.in_force_at("swing_budget", NOW).risk_policy_version == 1


def test_evaluating_against_a_budget_nobody_set_is_refused(store: TradingStore) -> None:
    with pytest.raises(PersistenceError, match="no risk budget"):
        store.risk.evaluate("swing_budget", moment=AT(9), measurements={})


def test_a_budget_evaluation_uses_the_generation_in_force(store: TradingStore) -> None:
    store.risk.create(risk_budget(effective_from=AT(0)), request=write_request())
    state = store.risk.evaluate(
        "swing_budget",
        moment=AT(9),
        measurements={"per_trade_risk": Decimal("0.01")},
    )
    assert len(state.evaluations) == 1
    assert state.evaluations[0].limit_id == "per_trade_risk"


def test_the_risk_repository_refuses_a_non_budget(store: TradingStore) -> None:
    with pytest.raises(TypeError, match="RiskBudget"):
        store.risk.revise("swing_budget", request=write_request())


# --------------------------------------------------------------------------
# JournalRepository.
# --------------------------------------------------------------------------


def test_an_entry_supersedes_another_and_both_survive(store: TradingStore) -> None:
    first = journal_entry(title="uneasy")
    store.journals.create(first, request=write_request())
    second = journal_entry(
        title="on reflection", recorded_at=AT(10), supersedes=first.entry_id
    )
    store.journals.replace(
        first.entry_id, second, request=write_request(written_at=NOW + timedelta(hours=1))
    )
    assert store.journals.load(first.entry_id) == first
    assert store.journals.live_entries() == (second,)


def test_a_replacement_entry_must_name_what_it_supersedes(store: TradingStore) -> None:
    first = journal_entry()
    store.journals.create(first, request=write_request())
    unlinked = journal_entry(title="something else", recorded_at=AT(10))
    with pytest.raises(PersistenceError, match="names nothing it supersedes"):
        store.journals.replace(first.entry_id, unlinked, request=write_request())


def test_a_replacement_entry_must_name_the_right_one(store: TradingStore) -> None:
    first = journal_entry()
    store.journals.create(first, request=write_request())
    other_id = "journal_entry-note-20260812T090000Z-0123456789abcdef"
    wrong = journal_entry(
        title="something else", recorded_at=AT(10), supersedes=other_id
    )
    with pytest.raises(PersistenceError, match="not the entry"):
        store.journals.replace(first.entry_id, wrong, request=write_request())


def test_superseding_an_entry_this_store_lacks_is_refused(store: TradingStore) -> None:
    missing = "journal_entry-note-20260812T090000Z-0123456789abcdef"
    second = journal_entry(recorded_at=AT(10), supersedes=missing)
    with pytest.raises(RecordMissingError):
        store.journals.replace(missing, second, request=write_request())


def test_replacing_without_the_replacement_is_refused(store: TradingStore) -> None:
    first = journal_entry()
    store.journals.create(first, request=write_request())
    with pytest.raises(PersistenceError, match="needs the replacement entry"):
        store.journals.replace(first.entry_id)


def test_the_trade_journal_view_gathers_what_links_to_a_subject(
    store: TradingStore,
) -> None:
    linked = journal_entry()
    other = journal_entry(
        title="unrelated",
        recorded_at=AT(10),
        links=(JournalLink(LinkKind.ABOUT, "market", OTHER_MARKET.value),),
    )
    store.journals.create(linked, request=write_request())
    store.journals.create(other, request=write_request())
    view = store.journals.for_market(MARKET.value)
    assert view.entries == (linked,)
    assert store.journals.linked_to("market", OTHER_MARKET.value) == (other,)


def test_entries_can_be_read_by_kind(store: TradingStore) -> None:
    note = journal_entry(kind=JournalKind.NOTE)
    store.journals.create(note, request=write_request())
    assert store.journals.entries_of_kind(JournalKind.NOTE) == (note,)
    assert store.journals.entries_of_kind(JournalKind.REVIEW) == ()


def test_the_link_kinds_actually_used_are_reported(store: TradingStore) -> None:
    store.journals.create(journal_entry(), request=write_request())
    assert store.journals.link_kinds_used() == (LinkKind.ABOUT,)


# --------------------------------------------------------------------------
# SnapshotRepository.
# --------------------------------------------------------------------------


def test_snapshots_and_windows_share_one_repository(store: TradingStore) -> None:
    snapshot = market_snapshot()
    window = decision_window()
    store.snapshots.create(snapshot, request=write_request())
    store.snapshots.create(window, request=write_request())
    assert store.snapshots.snapshots() == (snapshot,)
    assert store.snapshots.windows() == (window,)
    assert len(store.snapshots.for_market(MARKET.value)) == 2


def test_the_latest_snapshot_for_a_market_is_the_most_recently_built(
    store: TradingStore,
) -> None:
    early = market_snapshot(built_at=AT(9))
    late = market_snapshot(built_at=AT(11))
    store.snapshots.create(late, request=write_request())
    store.snapshots.create(early, request=write_request())
    assert store.snapshots.latest_for_market(MARKET.value) == late
    assert store.snapshots.latest_for_market(OTHER_MARKET.value) is None


def test_a_snapshot_citing_no_window_resolves_to_none(store: TradingStore) -> None:
    snapshot = market_snapshot()
    store.snapshots.create(snapshot, request=write_request())
    assert isinstance(snapshot.decision_window_id, Absent)
    assert store.snapshots.window_of(snapshot) is None


def test_a_snapshot_citing_a_window_resolves_to_it(store: TradingStore) -> None:
    window = decision_window()
    snapshot = market_snapshot(decision_window_id=window.window_id)
    store.snapshots.create(window, request=write_request())
    store.snapshots.create(snapshot, request=write_request())
    assert store.snapshots.window_of(snapshot) == window


def test_window_of_requires_a_snapshot(store: TradingStore) -> None:
    with pytest.raises(TypeError, match="MarketSnapshot"):
        store.snapshots.window_of(decision_window())


# --------------------------------------------------------------------------
# AnalysisRecordRepository.
# --------------------------------------------------------------------------


def test_an_analysis_citation_round_trips_under_the_archives_id(
    store: TradingStore,
) -> None:
    citation = analysis_record()
    store.analyses.create(citation, request=write_request())
    assert store.analyses.load(ARCHIVE_RECORD_ID) == citation
    assert store.analyses.for_subject("BTCUSDT") == (citation,)


def test_a_citation_reports_staleness_rather_than_being_rewritten(
    store: TradingStore,
) -> None:
    citation = analysis_record()
    store.analyses.create(citation, request=write_request())
    assert store.analyses.is_current(ARCHIVE_RECORD_ID, content_digest=citation.content_digest)
    assert not store.analyses.is_current(
        ARCHIVE_RECORD_ID, content_digest="sha256:" + "f" * 64
    )
    assert store.analyses.load(ARCHIVE_RECORD_ID) == citation


def test_a_citation_is_frozen(store: TradingStore) -> None:
    citation = analysis_record()
    store.analyses.create(citation, request=write_request())
    with pytest.raises(FrozenRecordError):
        store.analyses.replace(ARCHIVE_RECORD_ID)


# --------------------------------------------------------------------------
# OpportunityRepository.
# --------------------------------------------------------------------------


def test_a_proposal_is_frozen_and_its_events_are_not(store: TradingStore) -> None:
    subject = proposal()
    store.opportunities.create(subject, request=write_request())
    with pytest.raises(FrozenRecordError, match="captured artifact"):
        store.opportunities.replace(subject.proposal_id)


def test_an_event_about_an_unknown_proposal_is_refused(store: TradingStore) -> None:
    subject = proposal()
    event = lifecycle_event(subject, LifecycleKind.REAFFIRMED, 11)
    with pytest.raises(RecordMissingError, match="never be folded"):
        store.opportunities.create(event, request=write_request())


def test_the_state_is_folded_and_never_stored(store: TradingStore) -> None:
    subject = proposal()
    store.opportunities.create(subject, request=write_request())
    assert store.opportunities.state(subject.proposal_id).state is ProposalState.LIVE
    store.opportunities.append_event(
        lifecycle_event(subject, LifecycleKind.INVALIDATION_REACHED, 11),
        request=write_request(),
    )
    assert (
        store.opportunities.state(subject.proposal_id).state
        is ProposalState.INVALIDATED
    )
    assert store.opportunities.count(kind=RecordKind.LIFECYCLE_EVENT) == 1


def test_a_superseded_event_is_dropped_from_the_fold(store: TradingStore) -> None:
    subject = proposal()
    store.opportunities.create(subject, request=write_request())
    wrong = lifecycle_event(subject, LifecycleKind.INVALIDATION_REACHED, 11)
    store.opportunities.append_event(wrong, request=write_request())
    right = lifecycle_event(
        subject, LifecycleKind.REAFFIRMED, 11, supersedes=wrong.event_id
    )
    store.opportunities.replace(
        wrong.event_id, right, request=write_request(written_at=NOW + timedelta(hours=1))
    )
    assert store.opportunities.live_events_for(subject.proposal_id) == (right,)
    assert store.opportunities.state(subject.proposal_id).state is ProposalState.LIVE
    assert len(store.opportunities.events_for(subject.proposal_id)) == 2


def test_superseding_an_event_with_one_naming_another_is_refused(
    store: TradingStore,
) -> None:
    subject = proposal()
    store.opportunities.create(subject, request=write_request())
    first = lifecycle_event(subject, LifecycleKind.REAFFIRMED, 11)
    store.opportunities.append_event(first, request=write_request())
    other_id = "lifecycle_event-reaffirmed-20260813T110000Z-0123456789abcdef"
    wrong = lifecycle_event(
        subject, LifecycleKind.REAFFIRMED, 12, supersedes=other_id
    )
    with pytest.raises(PersistenceError, match="not the event"):
        store.opportunities.replace(first.event_id, wrong, request=write_request())


def test_superseding_an_unknown_record_is_refused(store: TradingStore) -> None:
    with pytest.raises(RecordMissingError):
        store.opportunities.replace("proposal-x-20260812T090000Z-0123456789abcdef")


def test_superseding_an_event_without_a_replacement_is_refused(
    store: TradingStore,
) -> None:
    subject = proposal()
    store.opportunities.create(subject, request=write_request())
    event = lifecycle_event(subject, LifecycleKind.REAFFIRMED, 11)
    store.opportunities.append_event(event, request=write_request())
    with pytest.raises(PersistenceError, match="needs the replacement event"):
        store.opportunities.replace(event.event_id)


def test_the_state_reconstructs_at_a_past_instant(store: TradingStore) -> None:
    subject = proposal()
    store.opportunities.create(subject, request=write_request())
    later = NOW + timedelta(days=1)
    store.opportunities.append_event(
        lifecycle_event(subject, LifecycleKind.INVALIDATION_REACHED, 11),
        request=write_request(written_at=later),
    )
    assert (
        store.opportunities.state_as_known_at(subject.proposal_id, NOW).state
        is ProposalState.LIVE
    )
    assert (
        store.opportunities.state_as_known_at(subject.proposal_id, later).state
        is ProposalState.INVALIDATED
    )


def test_admission_stores_whatever_the_rule_decided(store: TradingStore) -> None:
    """One live proposal per anchor — checked against what this store actually holds."""
    first = proposal()
    outcome = store.opportunities.admit(
        first,
        request=write_request(),
        occurred_at=AT(9),
        recorded_at=AT(9),
        causing_close_time=AT(9),
    )
    assert outcome.outcome.value == "created"
    assert store.opportunities.count(kind=RecordKind.PROPOSAL) == 1

    duplicate = proposal(created_at=AT(10))
    again = store.opportunities.admit(
        duplicate,
        request=write_request(written_at=NOW + timedelta(hours=1)),
        occurred_at=AT(10),
        recorded_at=AT(10),
        causing_close_time=AT(10),
    )
    assert again.outcome.value == "reaffirmed"
    assert again.proposal == first
    assert store.opportunities.count(kind=RecordKind.PROPOSAL) == 1
    assert store.opportunities.count(kind=RecordKind.LIFECYCLE_EVENT) == 1


def test_the_state_of_a_record_that_is_not_a_proposal_is_refused(
    store: TradingStore,
) -> None:
    subject = proposal()
    store.opportunities.create(subject, request=write_request())
    event = lifecycle_event(subject, LifecycleKind.REAFFIRMED, 11)
    store.opportunities.append_event(event, request=write_request())
    with pytest.raises(PersistenceError, match="not a proposal"):
        store.opportunities.state(event.event_id)


def test_append_event_requires_an_event(store: TradingStore) -> None:
    with pytest.raises(TypeError, match="ProposalLifecycleEvent"):
        store.opportunities.append_event(proposal(), request=write_request())


# --------------------------------------------------------------------------
# Search, ordering and owner scoping.
# --------------------------------------------------------------------------


def test_search_filters_on_both_time_axes(store: TradingStore) -> None:
    """`since`/`until` on when it happened; `known_*` on when FMITS learned of it."""
    early = trade(occurred_at=AT(10))
    store.trades.create(early, request=write_request())
    backfilled = trade(occurred_at=AT(10, day=1))
    store.trades.create(
        backfilled, request=write_request(written_at=NOW + timedelta(days=1))
    )
    assert store.trades.search(SearchCriteria(since=AT(9))) == (early,)
    assert store.trades.search(SearchCriteria(known_until=NOW)) == (early,)
    assert len(store.trades.search(SearchCriteria())) == 2


def test_search_filters_on_supersession(store: TradingStore) -> None:
    original = trade()
    store.trades.create(original, request=write_request())
    fix = correction(original, trade(quantity=quantity("0.6")))
    store.trades.replace(original.event_id, correction=fix, request=write_request())
    assert store.ledger.search(SearchCriteria(superseded=True)) == (original,)
    assert store.ledger.search(SearchCriteria(superseded=False)) == (fix,)


def test_search_respects_a_limit_and_a_deterministic_order(store: TradingStore) -> None:
    for hour in (12, 10, 11):
        store.trades.create(trade(occurred_at=AT(hour)), request=write_request())
    found = store.trades.search(SearchCriteria(limit=2))
    assert [item.occurred_at.hour for item in found] == [10, 11]


def test_owner_scoping_narrows_by_book_market_and_account(store: TradingStore) -> None:
    store.trades.create(trade(), request=write_request())
    assert len(store.trades.load_by_owner(book=Book.SWING.value)) == 1
    assert store.trades.load_by_owner(book=Book.DAY.value) == ()
    assert len(store.trades.load_by_owner(account=ACCOUNT.value)) == 1
    assert store.trades.load_by_owner(account="other") == ()
    assert len(store.trades.load_by_owner()) == 1


def test_the_scopes_a_repository_holds_are_reported(store: TradingStore) -> None:
    store.trades.create(trade(), request=write_request())
    scopes = store.trades.owner_scopes()
    assert len(scopes) == 1
    assert scopes[0].book == Book.SWING.value
    assert scopes[0].market == MARKET.value


def test_a_record_with_no_market_is_scoped_to_none(store: TradingStore) -> None:
    """Inventing a market would make a filter silently exclude the entry."""
    store.journals.create(journal_entry(), request=write_request())
    scope = store.journals.owner_scopes()[0]
    assert scope.market is None and scope.book is None and scope.account is None


def test_exists_and_count_agree_with_the_index(store: TradingStore) -> None:
    subject = trade()
    assert not store.trades.exists(subject.event_id)
    store.trades.create(subject, request=write_request())
    assert store.trades.exists(subject.event_id)
    assert store.trades.count() == 1
    assert not store.journals.exists(subject.event_id)


def test_an_empty_criteria_matches_everything(store: TradingStore) -> None:
    store.trades.create(trade(), request=write_request())
    assert store.trades.search(SearchCriteria()) == store.trades.all()


def test_criteria_reject_an_inverted_interval() -> None:
    with pytest.raises(PersistenceError, match="precedes"):
        SearchCriteria(since=AT(11), until=AT(9))
    with pytest.raises(PersistenceError, match="precedes"):
        SearchCriteria(known_since=AT(11), known_until=AT(9))


def test_criteria_reject_a_repeated_kind() -> None:
    with pytest.raises(PersistenceError, match="must not be listed twice"):
        SearchCriteria(kinds=(RecordKind.TRADE, RecordKind.TRADE))


def test_criteria_reject_a_non_kind() -> None:
    with pytest.raises(TypeError, match="RecordKind"):
        SearchCriteria(kinds=("trade",))  # type: ignore[arg-type]


def test_criteria_must_be_a_criteria(store: TradingStore) -> None:
    with pytest.raises(TypeError, match="SearchCriteria"):
        store.trades.entries(criteria="everything")  # type: ignore[arg-type]


def test_criteria_filter_by_kind(store: TradingStore) -> None:
    original = trade()
    store.trades.create(original, request=write_request())
    fix = correction(original, trade(quantity=quantity("0.6")))
    store.trades.replace(original.event_id, correction=fix, request=write_request())
    found = store.ledger.search(SearchCriteria(kinds=(RecordKind.CORRECTION,)))
    assert found == (fix,)


# --------------------------------------------------------------------------
# The store as a whole.
# --------------------------------------------------------------------------


def test_a_store_holding_every_kind_verifies(store: TradingStore, sample_records) -> None:
    for record in sample_records:
        store.store.publish(record, request=write_request())
    assert store.verify().ok
    assert store.write_journal.verify().ok
    assert store.versions.is_live(sample_records[1].event_id)


def test_the_root_and_dust_policy_are_reported(tmp_path: Path) -> None:
    from trade_domain_helpers import dust_policy

    policy = dust_policy()
    made = TradingStore(tmp_path, dust=policy)
    assert made.root == tmp_path
    assert made.dust is policy
