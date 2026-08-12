"""Tests written to kill specific mutation survivors.

A mutation sweep over `fmis.persistence` (mutmut 3.7.0) leaves two classes of
survivor that are equivalent for behaviour and are documented in
[`reports/0015`](../reports/0015_2026-08-12_TRADE_REPOSITORY_AND_JOURNAL_ENGINE_IMPLEMENTATION.md)
§7 rather than chased: mutations of error-message prose, and mutations of the
*name* an argument is reported under when it fails validation. Killing either
would require asserting exact message text everywhere, which makes every wording
change a test failure and buys nothing.

Everything else is real, and this module is it. Each test names the mutant it
kills and the behaviour that mutant would have silently changed. They are grouped
here rather than scattered because *"this exists because a mutation survived"* is
a fact about a test worth keeping visible — it is the difference between a test
that was designed and one that was reverse-engineered from a gap.

**The second half of this module exists because the first triage was wrong.** It
binned every `f(x)` → `f(None)` mutation as diagnostic, assuming the argument was
always an error-message entity name. Several were *functional* arguments — a
dropped `criteria`, a dropped `kind`, `astimezone(None)` silently converting to
local time — and each was a genuine gap wearing a harmless-looking shape. Every
test below was verified by applying its mutant to the real source, clearing the
bytecode cache, and confirming the suite fails.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
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
from trade_domain_helpers import (
    ACCOUNT,
    AT,
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
from fmis.archive.json_safe import canonical_dumps
from fmis.persistence import (
    AppendOnlyViolationError,
    PersistenceError,
    RecordKind,
    RecordStore,
    SearchCriteria,
    StoreLayout,
    VersionEngine,
    append_lines,
)
from fmis.persistence.envelope import encode_line
from fmis.persistence.index import RecordIndex
from fmis.proposal import LifecycleKind, ProposalState
from fmis.records import PayloadDecodeError

# --------------------------------------------------------------------------
# Boundary comparisons: the instant *on* the boundary.
# --------------------------------------------------------------------------


def test_a_record_filed_at_the_exact_instant_it_describes_is_accepted(
    tmp_path: Path,
) -> None:
    """Kills `publish` `<` → `<=`.

    A fill entered the moment it happened is the ordinary case, not an error. The
    rule is *"cannot be filed **before** it happened"*, and the boundary belongs on
    the accepting side.
    """
    store = new_record_store(tmp_path)
    subject = trade(occurred_at=AT(10))
    assert store.publish(subject, request=write_request(written_at=AT(10))).created


def test_an_interval_of_one_instant_is_a_legal_interval(tmp_path: Path) -> None:
    """Kills `events_between` `<` → `<=`. `since == until` selects that instant."""
    store = new_record_store(tmp_path)
    store.publish(trade(), request=write_request())
    assert len(store.journal.events_between(since=NOW, until=NOW)) == 1


def test_a_budget_generation_sharing_an_effective_instant_is_refused(
    tmp_path: Path,
) -> None:
    """Kills `revise` `<=` → `<`.

    Two versions of one budget taking effect at the same instant makes *"which
    limits applied"* depend on a tie the fold breaks by policy version — resolvable,
    but invisible. An owner who meant to schedule a change would rather be told.
    """
    store = new_store(tmp_path)
    store.risk.create(risk_budget(effective_from=AT(0)), request=write_request())
    with pytest.raises(PersistenceError, match="moves forward"):
        store.risk.revise(
            risk_budget(effective_from=AT(0), risk_policy_version=2),
            request=write_request(written_at=NOW + timedelta(hours=1)),
        )


def test_a_series_lookup_on_an_exact_instant_selects_that_record(
    tmp_path: Path,
) -> None:
    """Kills `series_at` `<=` → `<`. A snapshot taken *at* the moment asked about
    is the answer, not the one before it."""
    store = new_record_store(tmp_path)
    for filed, hour in enumerate((9, 11)):
        store.publish(
            portfolio_snapshot(as_of=AT(hour)),
            request=write_request(written_at=NOW + timedelta(hours=filed)),
        )
    chosen = VersionEngine(store).series_at(
        RecordKind.PORTFOLIO_SNAPSHOT, "main", AT(11)
    )
    assert chosen is not None and chosen.occurred_at == AT(11)


# --------------------------------------------------------------------------
# `or` is not `and`: both arguments are required, separately.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["correction", "request"])
def test_correcting_a_trade_needs_both_arguments(tmp_path: Path, missing: str) -> None:
    """Kills `TradeRepository.replace` `or` → `and`.

    Supplying one of the two is the realistic mistake; supplying neither is the one
    a test written from the happy path would cover.
    """
    store = new_store(tmp_path)
    original = trade()
    store.trades.create(original, request=write_request())
    fix = correction(original, trade(quantity=quantity("0.6")))
    arguments = {"correction": fix, "request": write_request()}
    arguments.pop(missing)
    with pytest.raises(PersistenceError, match="needs the Correction"):
        store.trades.replace(original.event_id, **arguments)


@pytest.mark.parametrize("missing", ["superseding", "request"])
def test_superseding_a_journal_entry_needs_both_arguments(
    tmp_path: Path, missing: str
) -> None:
    """Kills `JournalRepository.replace` `or` → `and`."""
    store = new_store(tmp_path)
    first = journal_entry()
    store.journals.create(first, request=write_request())
    second = journal_entry(recorded_at=AT(10), supersedes=first.entry_id)
    arguments = {"superseding": second, "request": write_request()}
    arguments.pop(missing)
    with pytest.raises(PersistenceError, match="needs the replacement entry"):
        store.journals.replace(first.entry_id, **arguments)


@pytest.mark.parametrize("missing", ["superseding", "request"])
def test_superseding_a_lifecycle_event_needs_both_arguments(
    tmp_path: Path, missing: str
) -> None:
    """Kills `OpportunityRepository.replace` `or` → `and`."""
    store = new_store(tmp_path)
    subject = proposal()
    store.opportunities.create(subject, request=write_request())
    first = lifecycle_event(subject, LifecycleKind.REAFFIRMED, 11)
    store.opportunities.append_event(first, request=write_request())
    later = lifecycle_event(
        subject, LifecycleKind.REAFFIRMED, 12, supersedes=first.event_id
    )
    arguments = {"superseding": later, "request": write_request()}
    arguments.pop(missing)
    with pytest.raises(PersistenceError, match="needs the replacement event"):
        store.opportunities.replace(first.event_id, **arguments)


def test_a_state_reconstruction_excludes_other_proposals_events(
    tmp_path: Path,
) -> None:
    """Kills `state_as_known_at` `and` → `or`.

    Two live proposals, one event each. Reading one proposal's state must not fold
    the other's events into it — with `or`, every event in the store that is not
    superseded would reach every fold.
    """
    from trade_domain_helpers import anchor

    store = new_store(tmp_path)
    first = proposal()
    second = proposal(
        market=OTHER_MARKET, anchor=anchor(market=OTHER_MARKET), created_at=AT(10)
    )
    store.opportunities.create(first, request=write_request())
    store.opportunities.create(second, request=write_request())
    store.opportunities.append_event(
        lifecycle_event(second, LifecycleKind.INVALIDATION_REACHED, 11),
        request=write_request(),
    )
    view = store.opportunities.state_as_known_at(first.proposal_id, NOW)
    assert view.state is ProposalState.LIVE
    assert view.applied == ()


# --------------------------------------------------------------------------
# Loop control: `continue` is not `break`.
# --------------------------------------------------------------------------


def test_an_unindexed_later_event_in_a_year_file_is_recognised(
    tmp_path: Path,
) -> None:
    """Kills `_write_payload` `continue` → `break`.

    The scan for an already-written event has to look past the lines that are not
    it. With `break` it would give up after the first line, append a duplicate, and
    the year file would hold one event twice.
    """
    store = new_record_store(tmp_path)
    first = trade(occurred_at=AT(10))
    second = trade(occurred_at=AT(11))
    store.publish(first, request=write_request())
    receipt = store.publish(second, request=write_request())
    store.layout.index_path.unlink()
    again = store.publish(
        second, request=write_request(written_at=NOW + timedelta(hours=1))
    )
    assert not again.created
    path = tmp_path / receipt.relative_path
    assert len(path.read_text(encoding="utf-8").strip().split("\n")) == 2


def test_verification_looks_past_a_healthy_record_to_find_a_broken_one(
    tmp_path: Path,
) -> None:
    """Kills `verify` `continue` → `break`."""
    store = new_record_store(tmp_path)
    healthy = trade(occurred_at=AT(10))
    store.publish(healthy, request=write_request())
    broken = market_snapshot()
    receipt = store.publish(broken, request=write_request())
    (tmp_path / receipt.relative_path).unlink()
    result = store.verify()
    assert result.missing_payloads == (broken.snapshot_id,)


def test_lineage_checks_look_past_records_that_supersede_nothing(
    tmp_path: Path,
) -> None:
    """Kills both `_lineage_problems` `continue` → `break`.

    An ordinary trade supersedes nothing and a dangling correction names an event
    that is not here. Meeting either must not stop the sweep before it reaches the
    branch that follows.
    """
    store = new_record_store(tmp_path)
    ordinary = trade(occurred_at=AT(10))
    store.publish(ordinary, request=write_request())
    absent = trade(occurred_at=AT(9))
    dangling = correction(absent, trade(quantity=quantity("0.7")), occurred_at=AT(11))
    store.publish(dangling, request=write_request())
    real = correction(ordinary, trade(quantity=quantity("0.6")), occurred_at=AT(12))
    other = correction(ordinary, trade(quantity=quantity("0.8")), occurred_at=AT(13))
    store.publish(real, request=write_request())
    store.publish(other, request=write_request())
    third = correction(ordinary, trade(quantity=quantity("0.9")), occurred_at=AT(14))
    store.publish(third, request=write_request())
    result = store.verify()
    assert result.dangling_supersessions
    # Two branches, not one: recording the first must not stop the sweep.
    assert len(result.lineage_branches) == 2


def test_a_narrowed_criteria_carries_every_axis_it_was_not_asked_to_change(
    tmp_path: Path,
) -> None:
    """Kills every mutant that deletes one field from a criteria copy.

    A field-by-field copy was the first implementation of `load_by_owner`'s
    narrowing, and eleven of its twelve lines could be deleted without any test
    noticing — because *forgetting to forward an axis* looks exactly like *the
    caller not setting it*. `dataclasses.replace` cannot forget a field, and this
    asserts it forgets none.
    """
    full = SearchCriteria(
        kinds=(RecordKind.TRADE,),
        book=Book.SWING.value,
        market=MARKET.value,
        account=ACCOUNT.value,
        lineage_key=MARKET.value,
        since=AT(9),
        until=AT(12),
        known_since=NOW,
        known_until=NOW + timedelta(days=1),
        superseded=False,
        limit=5,
    )
    narrowed = full.narrowed(market=OTHER_MARKET.value)
    assert narrowed.market == OTHER_MARKET.value
    for axis in (
        "kinds",
        "book",
        "account",
        "lineage_key",
        "since",
        "until",
        "known_since",
        "known_until",
        "superseded",
        "limit",
    ):
        assert getattr(narrowed, axis) == getattr(full, axis), axis
    assert full.narrowed() == full


def test_narrowing_a_search_actually_reaches_the_repositories(
    tmp_path: Path,
) -> None:
    """Every axis a caller sets survives the trip through `load_by_owner`."""
    store = new_store(tmp_path)
    store.trades.create(trade(occurred_at=AT(10)), request=write_request())
    store.trades.create(trade(occurred_at=AT(12)), request=write_request())
    narrow = SearchCriteria(until=AT(11), limit=5)
    assert len(store.trades.load_by_owner(market=MARKET.value, criteria=narrow)) == 1
    assert len(store.positions.load_by_owner(book=Book.SWING.value, criteria=narrow)) == 1
    assert (
        store.portfolios.snapshots("main", criteria=SearchCriteria(limit=1)) == ()
    )


def test_a_rebuild_looks_past_an_unjournalled_payload(tmp_path: Path) -> None:
    """Kills `rebuild_index` `continue` → `break`.

    One payload with no journal event, one with. The first is skipped and the
    second is still indexed — `break` would silently drop everything after it.
    """
    store = new_record_store(tmp_path)
    orphan = market_snapshot()
    store.publish(orphan, request=write_request())
    for year in store.layout.journal_years():
        (tmp_path / "journal" / f"{year}.jsonl").unlink()
    store.layout.index_path.unlink()
    later = market_snapshot(built_at=AT(11))
    store.publish(later, request=write_request(written_at=NOW + timedelta(hours=1)))
    rebuilt = store.rebuild_index()
    assert [entry.record_id for entry in rebuilt] == [later.snapshot_id]


# --------------------------------------------------------------------------
# Verification's `ok` is a disjunction, and every term matters alone.
# --------------------------------------------------------------------------


def test_an_orphan_payload_alone_makes_a_store_not_ok(tmp_path: Path) -> None:
    """Kills `verify` `orphans or unindexed` → `orphans and unindexed`.

    A record file this store never wrote — restored by hand, or left by a crash
    before the journal — is a defect on its own, with nothing else wrong.
    """
    store = new_record_store(tmp_path)
    store.publish(trade(), request=write_request())
    stray = tmp_path / "records" / "market_snapshot" / "2026" / "08" / "stray.json"
    stray.parent.mkdir(parents=True, exist_ok=True)
    subject = market_snapshot()
    stray.write_bytes(
        canonical_dumps(
            {
                "schema_version": 1,
                "kind": "market_snapshot",
                "record_id": subject.snapshot_id,
                "payload_schema_version": 1,
                "occurred_at": subject.built_at.isoformat(),
                "written_at": NOW.isoformat(),
                "content_digest": subject.content_digest,
                "payload": subject.to_payload(),
            }
        )
    )
    result = store.verify()
    assert not result.ok
    assert result.orphan_payloads == (subject.snapshot_id,)
    # Nothing else is wrong: the file was never journalled, so it is an orphan and
    # only an orphan. That is what makes this the test for the term in isolation.
    assert result.unindexed_writes == ()
    assert result.missing_payloads == ()
    assert result.integrity_failures == ()


def test_a_journalled_write_with_nothing_left_on_disk_makes_a_store_not_ok(
    tmp_path: Path,
) -> None:
    """Kills `verify` `unindexed or unjournalled` → `unindexed and unjournalled`.

    The journal says a record was written and neither the payload nor the index row
    is there. Nothing else is wrong, and this alone is as serious as it gets.
    """
    store = new_record_store(tmp_path)
    subject = trade()
    receipt = store.publish(subject, request=write_request())
    (tmp_path / receipt.relative_path).unlink()
    store.layout.index_path.unlink()
    result = store.verify()
    assert not result.ok
    assert result.unindexed_writes == (subject.event_id,)
    assert result.orphan_payloads == ()
    assert result.unjournalled_records == ()


# --------------------------------------------------------------------------
# Filters that must actually filter.
# --------------------------------------------------------------------------


def test_a_position_fold_narrows_by_account(tmp_path: Path) -> None:
    """Kills `PositionRepository.load_by_owner` `is not None` → `is None`."""
    store = new_store(tmp_path)
    store.trades.create(trade(), request=write_request())
    assert len(store.positions.load_by_owner(account=ACCOUNT.value)) == 1
    assert store.positions.load_by_owner(account="a_different_account") == ()


def test_proposals_exclude_lifecycle_events_and_respect_criteria(
    tmp_path: Path,
) -> None:
    """Kills `proposals` dropping its kind filter, and dropping its criteria."""
    store = new_store(tmp_path)
    subject = proposal()
    store.opportunities.create(subject, request=write_request())
    store.opportunities.append_event(
        lifecycle_event(subject, LifecycleKind.REAFFIRMED, 11), request=write_request()
    )
    assert store.opportunities.proposals() == (subject,)
    assert store.opportunities.proposals(SearchCriteria(market=OTHER_MARKET.value)) == ()


def test_the_latest_snapshot_is_the_last_of_three_not_the_second(
    tmp_path: Path,
) -> None:
    """Kills `latest_for_market` `rows[-1]` → `rows[+1]`.

    Two rows cannot tell those apart; three can.
    """
    store = new_store(tmp_path)
    built = [market_snapshot(built_at=AT(hour)) for hour in (9, 10, 11)]
    for filed, subject in enumerate(built):
        store.snapshots.create(
            subject, request=write_request(written_at=NOW + timedelta(hours=filed))
        )
    assert store.snapshots.latest_for_market(MARKET.value) == built[-1]


def test_a_series_never_spans_two_kinds(tmp_path: Path) -> None:
    """Kills `series_at` passing `None` as the kind.

    `entries(None)` means *every* kind. A series silently spanning kinds would
    group two unrelated records that happen to share a lineage key.
    """
    store = new_record_store(tmp_path)
    with pytest.raises(TypeError, match="kind"):
        VersionEngine(store).series(None, "main")  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# The line codec's three flags.
# --------------------------------------------------------------------------


def test_a_line_is_a_pure_function_of_content_not_of_key_order(tmp_path: Path) -> None:
    """Kills `encode_line` `sort_keys=True` → `False`.

    A line whose bytes depend on dict insertion order cannot be compared against
    the line already on disk, and that comparison is the whole of this store's
    append-only proof.
    """
    assert encode_line({"b": 1, "a": 2}) == encode_line({"a": 2, "b": 1})
    assert encode_line({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_a_line_keeps_non_ascii_text_as_itself(tmp_path: Path) -> None:
    """Kills `encode_line` `ensure_ascii=False` → `True`.

    The owner writes journal entries in their own language; escaping every accented
    character would make the file unreadable to the person it is about, and would
    change the bytes of every record carrying one.
    """
    line = encode_line({"note": "höjde stoppen"})
    assert "höjde" in line
    assert "\\u" not in line


def test_a_non_finite_number_never_reaches_a_line(tmp_path: Path) -> None:
    """Kills `encode_line` `allow_nan=False` → `True`.

    `NaN` and `Infinity` are not JSON. Writing them produces a file every standard
    reader rejects, discovered whenever something else tries to read the store.
    """
    with pytest.raises(PayloadDecodeError, match="not JSON-safe"):
        encode_line({"amount": float("nan")})
    with pytest.raises(PayloadDecodeError, match="not JSON-safe"):
        encode_line({"amount": float("inf")})


# --------------------------------------------------------------------------
# The append guard's own argument.
# --------------------------------------------------------------------------


def test_a_state_reconstruction_orders_its_events_before_folding(
    tmp_path: Path,
) -> None:
    """Kills `state_as_known_at` `key=lambda event: (ordering_key, id)` → `None`.

    Two events written in the wrong order must still fold in candle order. Sorting
    by nothing leaves them in the order the index happened to return, which is the
    order they were *written* — recreating ADR-0021's intrabar problem one layer up.
    """
    store = new_store(tmp_path)
    subject = proposal()
    store.opportunities.create(subject, request=write_request())
    later = lifecycle_event(subject, LifecycleKind.INVALIDATION_REACHED, 13)
    earlier = lifecycle_event(subject, LifecycleKind.REAFFIRMED, 11)
    store.opportunities.append_event(later, request=write_request())
    store.opportunities.append_event(
        earlier, request=write_request(written_at=NOW + timedelta(hours=1))
    )
    view = store.opportunities.state_as_known_at(
        subject.proposal_id, NOW + timedelta(hours=2)
    )
    assert view.applied == (earlier.event_id, later.event_id)


def test_snapshot_listings_honour_their_criteria(tmp_path: Path) -> None:
    """Kills `snapshots`, `windows` and `for_market` dropping their filters."""
    store = new_store(tmp_path)
    here = market_snapshot()
    window = decision_window()
    store.snapshots.create(here, request=write_request())
    store.snapshots.create(window, request=write_request())
    # Both kinds carry the same market, so each listing must also be filtering on
    # *kind* — without that assertion, dropping the kind filter goes unnoticed.
    assert store.snapshots.snapshots() == (here,)
    assert store.snapshots.windows() == (window,)
    assert store.snapshots.snapshots(SearchCriteria(market=OTHER_MARKET.value)) == ()
    assert store.snapshots.windows(SearchCriteria(market=OTHER_MARKET.value)) == ()
    assert store.snapshots.for_market(OTHER_MARKET.value) == ()
    assert store.snapshots.for_market(
        MARKET.value, kind=RecordKind.MARKET_SNAPSHOT
    ) == (here,)
    assert len(store.snapshots.for_market(MARKET.value)) == 2


def test_two_different_owner_scopes_are_reported_as_two(tmp_path: Path) -> None:
    """Kills `owner_scopes` `setdefault(key, …)` → `setdefault(None, …)`.

    Keying the deduplication on `None` collapses every scope to the first one, and
    a store spanning two books would report one.
    """
    from fmis.money import AssetCode

    store = new_store(tmp_path)
    store.trades.create(trade(), request=write_request())
    store.trades.create(
        trade(
            market=OTHER_MARKET,
            quantity=quantity("2", AssetCode("ETH")),
            price=Decimal("3000"),
        ),
        request=write_request(),
    )
    scopes = store.trades.owner_scopes()
    assert len(scopes) == 2
    assert {scope.market for scope in scopes} == {MARKET.value, OTHER_MARKET.value}


def test_a_stored_file_is_not_writable_by_anybody_else(tmp_path: Path) -> None:
    """Kills `append_lines` `0o644` → anything wider.

    This is a store of one person's financial history on a shared filesystem. The
    mode is not decoration.
    """
    store = new_record_store(tmp_path)
    receipt = store.publish(trade(), request=write_request())
    for path in (
        tmp_path / receipt.relative_path,
        store.layout.index_path,
        tmp_path / "journal" / "2026.jsonl",
    ):
        mode = path.stat().st_mode & 0o777
        assert mode & 0o022 == 0, f"{path} is group- or world-writable ({mode:o})"


# --------------------------------------------------------------------------
# Found by re-auditing the survivor set, not by the first classification pass.
#
# The first sweep's triage binned every `f(x)` → `f(None)` mutation as
# "diagnostic", on the assumption that the argument being replaced was always an
# error-message entity name. It was not: several were *functional* arguments, and
# calling them diagnostic was a mistake in the triage rather than in the code.
# Everything below closes a gap that mistake was hiding.
# --------------------------------------------------------------------------


def test_every_position_fold_that_takes_criteria_honours_them(tmp_path: Path) -> None:
    """Kills `rebuild(criteria)` → `rebuild(None)` in three places.

    `open_positions`, `total_fees_in` and `is_reproducible` all forward a criteria
    to the fold. Dropping it silently widens the answer to the whole ledger.
    """
    from fmis.money import AssetCode

    store = new_store(tmp_path)
    store.trades.create(trade(), request=write_request())
    store.trades.create(
        trade(
            market=OTHER_MARKET,
            quantity=quantity("2", AssetCode("ETH")),
            price=Decimal("3000"),
        ),
        request=write_request(),
    )
    only_here = SearchCriteria(market=MARKET.value)
    assert len(store.positions.rebuild()) == 2
    assert len(store.positions.rebuild(only_here)) == 1
    assert len(store.positions.open_positions(only_here)) == 1
    assert store.positions.total_fees_in(USDT, only_here).amount == Decimal("15")
    assert store.positions.total_fees_in(USDT).amount == Decimal("30")
    assert store.positions.is_reproducible(only_here)


def test_portfolio_snapshots_honour_criteria_with_no_portfolio_named(
    tmp_path: Path,
) -> None:
    """Kills `snapshots` `search(base)` → `search(None)`."""
    store = new_store(tmp_path)
    for filed, hour in enumerate((9, 11)):
        store.portfolios.create(
            portfolio_snapshot(as_of=AT(hour)),
            request=write_request(written_at=NOW + timedelta(hours=filed)),
        )
    assert len(store.portfolios.snapshots()) == 2
    assert len(store.portfolios.snapshots(criteria=SearchCriteria(until=AT(10)))) == 1


def test_live_proposals_honour_criteria(tmp_path: Path) -> None:
    """Kills `live_proposals` `proposals(criteria)` → `proposals(None)`."""
    from trade_domain_helpers import anchor

    store = new_store(tmp_path)
    here = proposal()
    elsewhere = proposal(
        market=OTHER_MARKET, anchor=anchor(market=OTHER_MARKET), created_at=AT(10)
    )
    store.opportunities.create(here, request=write_request())
    store.opportunities.create(elsewhere, request=write_request())
    assert len(store.opportunities.live_proposals()) == 2
    narrowed = store.opportunities.live_proposals(SearchCriteria(market=MARKET.value))
    assert [item[0] for item in narrowed] == [here]


def test_the_latest_snapshot_is_never_a_decision_window(tmp_path: Path) -> None:
    """Kills `latest_for_market` `kind=RecordKind.MARKET_SNAPSHOT` → `kind=None`.

    Both kinds carry the same market as their owner scope, so dropping the kind
    filter makes whichever is newest win — and a window is not a snapshot.
    """
    from fmis.snapshotting import WindowBar

    store = new_store(tmp_path)
    snapshot = market_snapshot(built_at=AT(9))
    store.snapshots.create(snapshot, request=write_request())
    # A window whose last candle closes *after* the snapshot was built. Without
    # that, the snapshot is last by instant anyway and the filter never has to
    # do anything — which is how this test first passed against the mutant.
    later_bars = tuple(
        WindowBar(
            close_time=AT(0, day=16 + index),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            volume=Decimal("12.5"),
        )
        for index in range(3)
    )
    window = decision_window(bars=later_bars)
    store.snapshots.create(window, request=write_request())
    assert window.last_close_time > snapshot.built_at
    assert store.snapshots.entries()[-1].record_id == window.window_id
    latest = store.snapshots.latest_for_market(MARKET.value)
    assert latest == snapshot


def test_a_write_receipt_describes_the_record_it_wrote(tmp_path: Path) -> None:
    """Kills every `WriteReceipt(field=None)` on the created and duplicate paths."""
    store = new_record_store(tmp_path)
    subject = trade()
    created = store.publish(subject, request=write_request())
    assert created.record_id == subject.event_id
    assert created.kind is RecordKind.TRADE
    assert created.content_digest == subject.content_digest
    assert created.relative_path == "ledger/trade/2026.jsonl"
    assert created.created is True

    duplicate = store.publish(subject, request=write_request())
    assert duplicate.record_id == created.record_id
    assert duplicate.kind is created.kind
    assert duplicate.content_digest == created.content_digest
    assert duplicate.relative_path == created.relative_path
    assert duplicate.created is False


def test_a_verification_result_says_false_and_not_merely_something_falsy(
    tmp_path: Path,
) -> None:
    """Kills `ok=False` → `ok=None` in three verification results.

    `assert not result.ok` cannot tell `False` from `None`, and a caller
    serializing the result to JSON would write `null` where a boolean belongs.
    """
    store = new_record_store(tmp_path)
    check = store.verify_record("trade-x-20260812T100000Z-0123456789abcdef")
    assert check.ok is False

    subject = trade()
    receipt = store.publish(subject, request=write_request())
    healthy = store.verify_record(subject.event_id)
    assert healthy.ok is True
    assert healthy.record_id == subject.event_id
    assert healthy.problems == ()
    assert check.record_id == "trade-x-20260812T100000Z-0123456789abcdef"
    (tmp_path / receipt.relative_path).unlink()
    assert store.verify().ok is False

    store.layout.index_path.write_text("{not json\n", encoding="utf-8")
    assert store.verify().ok is False
    journal = tmp_path / "journal" / "2026.jsonl"
    journal.write_text(journal.read_text(encoding="utf-8").rstrip("\n"), encoding="utf-8")
    assert store.journal.verify().ok is False


def test_a_record_files_under_its_utc_year_not_the_machines_local_year(
    tmp_path: Path,
) -> None:
    """Kills `_utc` `astimezone(timezone.utc)` → `astimezone(None)`.

    `astimezone(None)` converts to the machine's *local* zone. An event at
    23:30 UTC on 31 December is 00:30 on 1 January in Stockholm — the same
    instant, filed under a different year, on a machine that happens to sit east
    of UTC. ADR-0001's contract is that storage is UTC, and the layout is where
    that contract is either kept or quietly broken.
    """
    from datetime import timezone as tz

    store = new_record_store(tmp_path)
    new_years_eve = datetime(2026, 12, 31, 23, 30, tzinfo=tz.utc)
    subject = trade(occurred_at=new_years_eve)
    receipt = store.publish(
        subject, request=write_request(written_at=new_years_eve)
    )
    assert receipt.relative_path == "ledger/trade/2026.jsonl"
    assert store.layout.log_years(RecordKind.TRADE) == (2026,)
    assert store.layout.journal_years() == (2026,)

    snapshot = market_snapshot(built_at=new_years_eve)
    snap = store.publish(snapshot, request=write_request(written_at=new_years_eve))
    assert snap.relative_path.startswith("records/market_snapshot/2026/12/")
    assert store.verify().ok is True


# --------------------------------------------------------------------------
# Found in the third pass: filters that only ever had one thing to filter.
#
# A filter tested against a store containing exactly one subject cannot fail.
# Each test below adds the second subject that makes the filter load-bearing.
# --------------------------------------------------------------------------


def test_records_of_one_kind_exclude_every_other_kind(tmp_path: Path) -> None:
    """Kills `RecordStore.records` `entries(kind)` → `entries(None)`."""
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    store.publish(market_snapshot(), request=write_request())
    assert len(store.entries()) == 2
    assert store.records(RecordKind.TRADE) == (subject,)
    assert len(store.records(RecordKind.MARKET_SNAPSHOT)) == 1


def test_portfolio_lookups_narrow_to_the_portfolio_named(tmp_path: Path) -> None:
    """Kills `snapshots` and `latest` dropping their `lineage_key`.

    One portfolio in the store makes every portfolio filter look correct.
    """
    store = new_store(tmp_path)
    main = portfolio_snapshot(as_of=AT(9))
    other = portfolio_snapshot(portfolio_id="paper", as_of=AT(11))
    store.portfolios.create(main, request=write_request())
    store.portfolios.create(
        other, request=write_request(written_at=NOW + timedelta(hours=1))
    )
    assert set(store.portfolios.portfolio_ids()) == {"main", "paper"}
    assert store.portfolios.snapshots("main") == (main,)
    assert store.portfolios.snapshots("paper") == (other,)
    assert len(store.portfolios.snapshots()) == 2
    assert store.portfolios.latest("main") == main
    assert store.portfolios.latest("paper") == other
    assert store.portfolios.as_of("main", AT(23)) == main


def test_analysis_citations_narrow_to_the_subject_named(tmp_path: Path) -> None:
    """Kills `for_subject` dropping its `lineage_key`."""
    from persistence_helpers import analysis_record

    store = new_store(tmp_path)
    here = analysis_record()
    elsewhere = analysis_record(
        record_id="workspace-ETHUSDT-20260812T090000Z-abcdef0123456789",
        subject=("ETHUSDT",),
    )
    store.analyses.create(here, request=write_request())
    store.analyses.create(elsewhere, request=write_request())
    assert store.analyses.for_subject("BTCUSDT") == (here,)
    assert store.analyses.for_subject("ETHUSDT") == (elsewhere,)
    assert len(store.analyses.all()) == 2


def test_verification_reports_a_record_the_journal_never_recorded(
    tmp_path: Path,
) -> None:
    """Kills `verify` dropping `unjournalled_records`.

    An indexed record with no journal event is the one direction nothing can
    repair — the index can be rebuilt from the journal, never the reverse. Every
    other test left this tuple empty, so deleting the field changed nothing.
    """
    store = new_record_store(tmp_path)
    subject = trade()
    store.publish(subject, request=write_request())
    for year in store.layout.journal_years():
        (tmp_path / "journal" / f"{year}.jsonl").unlink()
    result = store.verify()
    assert result.ok is False
    assert result.unjournalled_records == (subject.event_id,)
    assert result.journal_event_count == 0


def test_an_unreadable_index_still_reports_the_journals_own_state(
    tmp_path: Path,
) -> None:
    """Kills `verify` dropping `journal_event_count` / `journal_problems` on the
    early-return path.

    When the index cannot be read the sweep returns early — and that is exactly
    when a reader most needs to know whether the *journal* is intact, because the
    journal is what the index would be rebuilt from.
    """
    store = new_record_store(tmp_path)
    store.publish(trade(occurred_at=AT(10)), request=write_request())
    store.publish(trade(occurred_at=AT(11)), request=write_request())
    store.layout.index_path.write_text("{not json\n", encoding="utf-8")
    result = store.verify()
    assert result.ok is False
    assert result.journal_event_count == 2
    assert result.journal_problems == ()
    assert any("index unreadable" in problem for problem in result.integrity_failures)


def test_an_explicit_expected_count_is_honoured_over_the_current_one(
    tmp_path: Path,
) -> None:
    """Kills `RecordIndex.append` `is None` → `is not None`.

    The whole point of passing the count is that it is the caller's belief, not the
    file's current state. Swapping the branches would make the check compare the
    file against itself and always pass.
    """
    layout = StoreLayout(tmp_path)
    index = RecordIndex(layout)
    store = RecordStore(tmp_path)
    store.publish(trade(), request=write_request())
    entry = index.entries()[0]
    with pytest.raises(AppendOnlyViolationError, match="computed against"):
        index.append(entry, expected_existing=0)
