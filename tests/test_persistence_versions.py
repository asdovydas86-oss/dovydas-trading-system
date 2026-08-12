"""The version engine: chains, history, reconstruction at a past instant, series.

Two questions this module keeps apart because the store does:

* a **chain** is one record's successive versions — the correction that replaced a
  trade, the entry that replaced a note. Only the head is current.
* a **series** is many records sharing a subject — three snapshots of one
  portfolio, three generations of one budget. Nothing supersedes anything.

And two time axes, kept equally apart: `at()` reconstructs what the store *knew*
at an instant, and `as_of` on the portfolio repository answers what was *true* at
one. A correction filed today does not change what April's report was entitled to
say.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from persistence_helpers import (
    NOW,
    journal_entry,
    new_record_store,
    new_store,
    portfolio_snapshot,
    risk_budget,
    write_request,
)
from trade_domain_helpers import AT, correction, quantity, trade

from fmis.persistence import (
    Lineage,
    LineageError,
    RecordKind,
    RecordMissingError,
    VersionEngine,
)
from fmis.provenance import Absent

# --------------------------------------------------------------------------
# Chains.
# --------------------------------------------------------------------------


def _corrected(store, times: int = 1):
    """A trade and `times` successive corrections, each filed an hour after the last.

    A chain, not a branch: correction *n* supersedes correction *n-1*, which is the
    only shape the store accepts.
    """
    original = trade()
    store.publish(original, request=write_request())
    chain: list = [original]
    for step in range(times):
        replacement = trade(quantity=quantity(f"0.{6 + step}"))
        fix = correction(chain[-1], replacement, occurred_at=AT(11 + step))
        store.publish(
            fix, request=write_request(written_at=NOW + timedelta(hours=step + 1))
        )
        chain.append(fix)
    return original, tuple(chain)


def test_an_uncorrected_record_is_a_chain_of_one(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    lineage = VersionEngine(store).lineage(subject.event_id)
    assert lineage.version_ids == (subject.event_id,)
    assert lineage.head_id == subject.event_id
    assert not lineage.was_superseded


def test_a_correction_extends_the_chain(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    original, chain = _corrected(store)
    lineage = VersionEngine(store).lineage(original.event_id)
    assert lineage.version_ids == tuple(item.event_id for item in chain)
    assert lineage.was_superseded
    assert lineage.length == 2


def test_a_chain_is_reachable_from_any_member(tmp_path: Path) -> None:
    """A caller holding a correction's id is asking about the same history."""
    store = new_record_store(tmp_path)
    original, chain = _corrected(store)
    engine = VersionEngine(store)
    assert engine.lineage(chain[-1].event_id) == engine.lineage(original.event_id)


def test_a_chain_of_three_versions_walks_in_order(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    original, chain = _corrected(store, times=2)
    lineage = VersionEngine(store).lineage(original.event_id)
    assert lineage.length == 3
    assert lineage.origin_id == original.event_id
    assert lineage.head_id == chain[-1].event_id


def test_history_returns_every_version_oldest_first(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    original, chain = _corrected(store, times=2)
    history = VersionEngine(store).history(original.event_id)
    assert len(history) == 3
    assert history[0] == original


def test_a_superseded_version_is_still_loadable_forever(tmp_path: Path) -> None:
    """Nothing is deleted. What the owner first believed stays readable."""
    store = new_record_store(tmp_path)
    original, _ = _corrected(store)
    assert store.load(original.event_id) == original


def test_head_resolves_to_the_live_version(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    original, chain = _corrected(store)
    head = VersionEngine(store).head(original.event_id)
    assert head == chain[-1]


def test_is_live_distinguishes_the_head_from_the_rest(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    original, chain = _corrected(store)
    engine = VersionEngine(store)
    assert not engine.is_live(original.event_id)
    assert engine.is_live(chain[-1].event_id)


def test_a_branching_chain_is_refused(tmp_path: Path) -> None:
    """Two corrections of one event gives *what actually happened* two answers."""
    store = new_record_store(tmp_path)
    original = trade()
    store.publish(original, request=write_request())
    first = correction(original, trade(quantity=quantity("0.6")), occurred_at=AT(11))
    second = correction(original, trade(quantity=quantity("0.7")), occurred_at=AT(12))
    store.publish(first, request=write_request())
    store.publish(second, request=write_request())
    with pytest.raises(LineageError, match="never branches"):
        store.successors()
    result = store.verify()
    assert not result.ok
    assert result.lineage_branches


def test_a_chain_may_not_cross_record_kinds(tmp_path: Path) -> None:
    """A journal entry may not supersede a trade — found by a hostile probe.

    `supersedes` holds a domain record id, and the pattern cannot tell a journal
    entry's from a trade's. Before this was checked, an entry naming a fill made
    `load_latest` on that fill return the owner's prose about it: the *note*
    became the current version of the *trade*.

    Only a store can catch it. The domain validates the shape of the id, and the
    shape is identical.
    """
    store = new_store(tmp_path)
    subject = trade()
    store.trades.create(subject, request=write_request())
    store.journals.create(journal_entry(), request=write_request())
    crossing = journal_entry(recorded_at=AT(10), supersedes=subject.event_id)
    with pytest.raises(LineageError, match="may not supersede"):
        store.store.publish(crossing, request=write_request())
    assert store.trades.load_latest(subject.event_id) == subject


def test_a_correction_may_supersede_a_trade_or_another_correction(
    tmp_path: Path,
) -> None:
    """The one kind that legitimately spans two: a chain of corrections is legal."""
    store = new_record_store(tmp_path)
    original, chain = _corrected(store, times=2)
    assert VersionEngine(store).lineage(original.event_id).length == 3


def test_a_supersession_naming_an_unknown_record_is_reported(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    original = trade()
    fix = correction(original, trade(quantity=quantity("0.6")))
    store.publish(fix, request=write_request())
    result = store.verify()
    assert not result.ok
    assert result.dangling_supersessions


def test_a_lineage_for_an_unknown_record_is_refused(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    with pytest.raises(RecordMissingError):
        VersionEngine(store).lineage("trade-x-20260812T100000Z-0123456789abcdef")


def test_the_engine_requires_a_store() -> None:
    with pytest.raises(TypeError, match="RecordStore"):
        VersionEngine("/tmp")  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# The `Lineage` value itself.
# --------------------------------------------------------------------------


def test_a_lineage_must_start_at_its_own_origin() -> None:
    with pytest.raises(LineageError, match="starts at its own origin"):
        Lineage(origin_id="a", version_ids=("b",), written_ats=(NOW,))


def test_a_lineage_holds_at_least_one_version() -> None:
    with pytest.raises(LineageError, match="at least"):
        Lineage(origin_id="a", version_ids=(), written_ats=())


def test_every_version_carries_the_instant_it_was_filed() -> None:
    with pytest.raises(LineageError, match="instant it was filed"):
        Lineage(origin_id="a", version_ids=("a", "b"), written_ats=(NOW,))


# --------------------------------------------------------------------------
# Reconstruction at a past instant.
# --------------------------------------------------------------------------


def test_at_returns_the_version_the_store_held_then(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    original, chain = _corrected(store)
    engine = VersionEngine(store)
    assert engine.at(original.event_id, NOW) == original
    assert engine.at(original.event_id, NOW + timedelta(hours=2)) == chain[-1]


def test_at_returns_none_before_the_record_was_known(tmp_path: Path) -> None:
    """*"The store held no such record"* and *"the store held the first version"*
    are different answers."""
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    assert VersionEngine(store).at(subject.event_id, NOW - timedelta(days=1)) is None


def test_a_correction_does_not_change_what_a_past_report_said(tmp_path: Path) -> None:
    """The whole point of the `written_at` axis, exercised through the ledger."""
    store = new_store(tmp_path)
    original = trade()
    store.trades.create(original, request=write_request())
    before = store.ledger.resolved_as_known_at(NOW)
    fix = correction(original, trade(quantity=quantity("0.6")), occurred_at=AT(11))
    store.trades.replace(
        original.event_id,
        correction=fix,
        request=write_request(written_at=NOW + timedelta(days=30)),
    )
    after = store.ledger.resolved_as_known_at(NOW)
    assert before == after
    assert [item.trade.quantity.text for item in before] == ["0.5"]
    assert [item.trade.quantity.text for item in store.ledger.resolved()] == ["0.6"]


def test_positions_reconstruct_at_a_past_instant(tmp_path: Path) -> None:
    store = new_store(tmp_path)
    original = trade()
    store.trades.create(original, request=write_request())
    fix = correction(original, trade(quantity=quantity("0.6")), occurred_at=AT(11))
    store.trades.replace(
        original.event_id,
        correction=fix,
        request=write_request(written_at=NOW + timedelta(days=30)),
    )
    assert [p.net_quantity.text for p in store.positions.as_known_at(NOW)] == ["0.5"]
    assert [p.net_quantity.text for p in store.positions.rebuild()] == ["0.6"]


# --------------------------------------------------------------------------
# Series: many records, one subject, nothing superseded.
# --------------------------------------------------------------------------


def test_a_series_orders_observations_by_the_instant_they_describe(
    tmp_path: Path,
) -> None:
    store = new_record_store(tmp_path)
    for filed, hour in enumerate((11, 9, 10)):
        store.publish(
            portfolio_snapshot(as_of=AT(hour)),
            request=write_request(written_at=NOW + timedelta(hours=filed)),
        )
    series = VersionEngine(store).series(RecordKind.PORTFOLIO_SNAPSHOT, "main")
    assert [entry.occurred_at.hour for entry in series] == [9, 10, 11]


def test_a_series_member_supersedes_nothing(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    for hour in (9, 10):
        store.publish(
            portfolio_snapshot(as_of=AT(hour)),
            request=write_request(written_at=NOW + timedelta(hours=hour)),
        )
    assert store.successors() == {}
    engine = VersionEngine(store)
    for entry in engine.series(RecordKind.PORTFOLIO_SNAPSHOT, "main"):
        assert engine.lineage(entry.record_id).length == 1


def test_series_at_selects_the_latest_at_or_before_an_instant(tmp_path: Path) -> None:
    store = new_record_store(tmp_path)
    for hour in (9, 11):
        store.publish(
            portfolio_snapshot(as_of=AT(hour)),
            request=write_request(written_at=NOW + timedelta(hours=hour)),
        )
    engine = VersionEngine(store)
    chosen = engine.series_at(RecordKind.PORTFOLIO_SNAPSHOT, "main", AT(10))
    assert chosen is not None and chosen.occurred_at == AT(9)
    assert engine.series_at(RecordKind.PORTFOLIO_SNAPSHOT, "main", AT(8)) is None


def test_a_risk_budget_series_resolves_the_generation_in_force(tmp_path: Path) -> None:
    store = new_store(tmp_path)
    first = risk_budget(effective_from=AT(0))
    store.risk.create(first, request=write_request())
    second = risk_budget(effective_from=AT(0, day=15), risk_policy_version=2)
    store.risk.revise(second, request=write_request(written_at=NOW + timedelta(hours=1)))
    assert store.risk.in_force_at("swing_budget", AT(9)) == first
    assert store.risk.in_force_at("swing_budget", AT(9, day=20)) == second
    assert isinstance(
        store.risk.in_force_at("swing_budget", AT(0, day=1)), Absent
    )


# --------------------------------------------------------------------------
# Journal entries: the third chain mechanism.
# --------------------------------------------------------------------------


def test_a_superseded_journal_entry_keeps_both_versions(tmp_path: Path) -> None:
    store = new_store(tmp_path)
    first = journal_entry(title="uneasy about this one")
    store.journals.create(first, request=write_request())
    second = journal_entry(
        title="on reflection, fine", recorded_at=AT(10), supersedes=first.entry_id
    )
    store.journals.replace(
        first.entry_id,
        second,
        request=write_request(written_at=NOW + timedelta(hours=1)),
    )
    assert store.journals.load(first.entry_id) == first
    assert store.journals.load_latest(first.entry_id) == second
    assert len(store.journals.history(first.entry_id)) == 2
    assert store.journals.live_entries() == (second,)
