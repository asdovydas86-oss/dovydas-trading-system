"""Milestone BJ — the composition root.

Three properties are asserted here and each one is a claim the package makes
about itself:

* **`build_today` is pure.** No clock, no network, no filesystem — proved by
  assembling a full page from hand-built objects with no store on disk at all,
  and by asserting two calls over the same inputs produce an equal workspace.
* **A missing store is a reading, not a failure.** Opening the workspace on a
  machine that has never recorded a trade produces a complete page that says so.
  A store that exists and is *corrupt* is the opposite and must raise.
* **The two halves never meet before the workspace.** `read_store` is exercised
  against a real store on disk containing one of every kind, and nothing it
  returns depends on a scan result.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from fmis.today import (
    DUST_POLICY,
    TODAY_LIMITATIONS,
    OBJECTIVE,
    StoreReading,
    StoreUnreadableError,
    TodayError,
    NotAvailable,
    build_today,
    empty_reading,
    read_store,
    run_today,
)
from fmis.today import builder as builder_module
from persistence_helpers import NOW, new_store, write_request
from today_helpers import REFERENCE, failed_result, reading, result, workspace

from tests.test_swing_setup_render import (
    candidate_short_with_watched_level,
    confirmed_long,
    waiting,
)


def _scan():
    return (
        result(confirmed_long()),
        result(candidate_short_with_watched_level()),
        result(waiting()),
        failed_result("BADUSDT"),
    )


# --------------------------------------------------------------------------
# Purity
# --------------------------------------------------------------------------


def test_the_same_inputs_produce_an_equal_workspace() -> None:
    results = _scan()
    store = reading()
    first = build_today(results, store, reference_time=REFERENCE, source="fixture")
    second = build_today(results, store, reference_time=REFERENCE, source="fixture")
    assert first == second


def test_building_touches_no_filesystem_path_that_does_not_exist() -> None:
    """The reading is data. `build_today` cannot reach a store even by accident."""
    space = build_today(
        _scan(),
        reading(root="/nowhere/at/all", present=False),
        reference_time=REFERENCE,
        source="fixture",
    )
    assert space.portfolio.store_root == "/nowhere/at/all"
    assert not Path("/nowhere/at/all").exists()


def test_the_workspace_states_the_dust_policy_it_folded_under() -> None:
    space = workspace(_scan())
    assert space.metadata["dust_policy"] == DUST_POLICY.policy_id


def test_the_dust_policy_configures_no_threshold() -> None:
    """Zero is the only tolerance that is not a policy decision, so this package
    chooses none on the owner's behalf."""
    assert DUST_POLICY.thresholds == ()


def test_the_objective_and_limitations_are_carried_through() -> None:
    space = workspace(_scan())
    assert space.objective == OBJECTIVE
    assert space.limitations == TODAY_LIMITATIONS
    assert len(TODAY_LIMITATIONS) == len({code for code, _ in TODAY_LIMITATIONS})


def test_build_rejects_a_foreign_reading_or_reference_time() -> None:
    with pytest.raises(TypeError, match="StoreReading"):
        build_today(_scan(), "a reading", reference_time=REFERENCE, source="s")
    with pytest.raises(TypeError, match="reference_time"):
        build_today(_scan(), reading(), reference_time="today", source="s")


def test_build_rejects_an_empty_universe() -> None:
    with pytest.raises(TodayError):
        build_today((), reading(), reference_time=REFERENCE, source="s")


# --------------------------------------------------------------------------
# Reading a store that is not there
# --------------------------------------------------------------------------


def test_a_missing_store_reads_as_empty_and_creates_nothing(tmp_path: Path) -> None:
    root = tmp_path / "never-created"
    found = read_store(root, at=NOW, archive_root=tmp_path / "no-archive")
    assert found.present is False
    assert found.positions == ()
    assert found.journal_entries == ()
    assert not root.exists()


def test_a_missing_store_still_produces_a_complete_page(tmp_path: Path) -> None:
    found = read_store(
        tmp_path / "never-created", at=NOW, archive_root=tmp_path / "none"
    )
    space = build_today(_scan(), found, reference_time=REFERENCE, source="fixture")
    assert space.warning("M-NO-STORE") is not None
    assert isinstance(space.portfolio.cash, NotAvailable)
    assert space.market.scanned == len(_scan())


def test_a_skipped_store_is_distinguishable_from_an_empty_one() -> None:
    """*"This page did not look"* is a different fact from *"you recorded
    nothing"*, and only one of them is about the owner."""
    skipped = empty_reading("/some/root")
    assert skipped.present is False
    assert skipped.root == "/some/root"


def test_read_store_requires_an_instant() -> None:
    with pytest.raises(TypeError):
        read_store("/tmp", at="now")


def test_a_corrupt_store_raises_rather_than_rendering_an_empty_page(
    tmp_path: Path,
) -> None:
    """A detected corruption must never become a page saying the owner holds
    nothing — which is exactly what swallowing the failure would produce."""
    root = tmp_path / "store"
    store = new_store(root)
    from trade_domain_helpers import trade

    store.trades.create(trade(), request=write_request())
    index = root / "index.jsonl"
    index.write_bytes(index.read_bytes().replace(b'"kind"', b'"knid"'))
    with pytest.raises(StoreUnreadableError, match="could not be read"):
        read_store(root, at=NOW, archive_root=tmp_path / "none")


def test_the_store_failure_is_chained_rather_than_discarded(tmp_path: Path) -> None:
    root = tmp_path / "store"
    store = new_store(root)
    from trade_domain_helpers import trade

    store.trades.create(trade(), request=write_request())
    index = root / "index.jsonl"
    index.write_bytes(index.read_bytes().replace(b'"kind"', b'"knid"'))
    with pytest.raises(StoreUnreadableError) as caught:
        read_store(root, at=NOW, archive_root=tmp_path / "none")
    assert caught.value.__cause__ is not None


# --------------------------------------------------------------------------
# Reading a store that is there
# --------------------------------------------------------------------------


def _populated(root: Path):
    """A store holding one of every kind the workspace reads."""
    from persistence_helpers import journal_entry, portfolio_snapshot, risk_budget
    from trade_domain_helpers import market_snapshot, trade

    store = new_store(root)
    store.trades.create(trade(), request=write_request())
    store.snapshots.create(market_snapshot(), request=write_request())
    store.journals.create(journal_entry(), request=write_request())
    store.risk.create(risk_budget(), request=write_request())
    store.portfolios.create(portfolio_snapshot(), request=write_request())
    return store


def test_a_populated_store_reports_every_family_it_holds(tmp_path: Path) -> None:
    root = tmp_path / "store"
    _populated(root)
    found = read_store(root, at=NOW, archive_root=tmp_path / "none")
    assert found.present is True
    assert found.positions
    assert found.journal_entries
    assert found.budget is not None
    assert found.snapshot is not None
    assert found.market_snapshots


def test_a_populated_store_produces_a_page_with_real_capital(tmp_path: Path) -> None:
    root = tmp_path / "store"
    _populated(root)
    found = read_store(root, at=NOW, archive_root=tmp_path / "none")
    space = build_today(_scan(), found, reference_time=REFERENCE, source="fixture")
    assert space.portfolio.open_count == len(found.positions)
    assert space.portfolio.limits
    assert isinstance(space.portfolio.budget_note, str)
    assert space.warning("M-NO-STORE") is None
    assert space.warning("M-NO-POSITIONS") is None
    assert space.warning("R-NO-BUDGET") is None


def test_the_budget_generation_in_force_is_resolved_against_the_reference_time(
    tmp_path: Path,
) -> None:
    """A budget that takes effect tomorrow is not in force today."""
    from persistence_helpers import risk_budget

    root = tmp_path / "store"
    store = new_store(root)
    future = risk_budget(effective_from=NOW + timedelta(days=1))
    store.risk.create(future, request=write_request())
    before = read_store(root, at=NOW, archive_root=tmp_path / "none")
    after = read_store(
        root, at=NOW + timedelta(days=2), archive_root=tmp_path / "none"
    )
    assert before.budget is None
    assert after.budget is not None


def test_two_budget_lineages_resolve_to_none_rather_than_to_a_guess(
    tmp_path: Path,
) -> None:
    """Picking one would make *which limits apply* depend on an id sort nobody
    wrote down."""
    from persistence_helpers import risk_budget

    root = tmp_path / "store"
    store = new_store(root)
    store.risk.create(risk_budget(), request=write_request())
    store.risk.create(risk_budget(budget_id="second_budget"), request=write_request())
    found = read_store(root, at=NOW, archive_root=tmp_path / "none")
    assert found.budget is None


def test_two_portfolio_lineages_resolve_to_none_for_the_same_reason(
    tmp_path: Path,
) -> None:
    from persistence_helpers import portfolio_snapshot

    root = tmp_path / "store"
    store = new_store(root)
    store.portfolios.create(portfolio_snapshot(), request=write_request())
    store.portfolios.create(
        portfolio_snapshot(portfolio_id="second_portfolio"), request=write_request()
    )
    found = read_store(root, at=NOW, archive_root=tmp_path / "none")
    assert found.snapshot is None


def test_a_live_proposal_appears_as_a_decision_line(tmp_path: Path) -> None:
    from trade_domain_helpers import market_snapshot, proposal

    root = tmp_path / "store"
    store = new_store(root)
    store.snapshots.create(market_snapshot(), request=write_request())
    subject = proposal()
    store.opportunities.create(subject, request=write_request())
    found = read_store(root, at=NOW, archive_root=tmp_path / "none")
    assert len(found.decisions) == 1
    assert subject.proposal_id in found.decisions[0]
    assert subject.market.value in found.decisions[0]


def test_a_closed_position_is_separated_from_an_open_one(tmp_path: Path) -> None:
    from decimal import Decimal

    from trade_domain_helpers import trade
    from fmis.ledger import TradeSide

    root = tmp_path / "store"
    store = new_store(root)
    opening = trade()
    closing = trade(
        side=TradeSide.SELL,
        quantity=opening.quantity,
        price=Decimal("40000"),
        occurred_at=opening.occurred_at + timedelta(hours=2),
    )
    store.trades.create(opening, request=write_request())
    store.trades.create(closing, request=write_request())
    found = read_store(root, at=NOW, archive_root=tmp_path / "none")
    assert found.positions == ()
    assert len(found.closed_positions) == 1


def test_an_unreadable_archive_does_not_take_the_page_down(tmp_path: Path) -> None:
    """The memory section is an aid. Losing it is not a reason to lose the
    market and capital sections above it."""
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    (archive_root / "manifest.jsonl").write_text("not json at all\n")
    found = read_store(tmp_path / "store", at=NOW, archive_root=archive_root)
    assert found.archived == ()


def test_a_readable_archive_is_reported(tmp_path: Path) -> None:
    from fmis.archive import ArchiveStore

    from tests.archive_helpers import fixture_workspace

    archive_root = tmp_path / "archive"
    ArchiveStore(archive_root).archive_workspace(fixture_workspace())
    found = read_store(tmp_path / "store", at=NOW, archive_root=archive_root)
    assert len(found.archived) == 1


# --------------------------------------------------------------------------
# run_today
# --------------------------------------------------------------------------


def test_run_today_calls_the_scan_the_other_commands_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A row here and a page in `fmits setup` for the same symbol are produced
    by identical code and cannot disagree."""
    seen: dict[str, object] = {}

    def _fake(symbols, **kwargs):
        seen["symbols"] = tuple(symbols)
        seen["kwargs"] = kwargs
        return _scan()

    monkeypatch.setattr(builder_module, "run_market_scan", _fake)
    space = run_today(
        ("BTCUSDT",),
        reference_time=REFERENCE,
        store_root=tmp_path / "store",
        archive_root=tmp_path / "archive",
        limit=300,
    )
    assert seen["symbols"] == ("BTCUSDT",)
    assert seen["kwargs"]["limit"] == 300
    assert space.market.scanned == len(_scan())


def test_run_today_can_skip_the_store_entirely(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "store"
    _populated(root)
    monkeypatch.setattr(builder_module, "run_market_scan", lambda s, **k: _scan())
    space = run_today(
        ("BTCUSDT",),
        reference_time=REFERENCE,
        store_root=root,
        read_records=False,
    )
    assert space.portfolio.store_present is False
    assert space.portfolio.open_count == 0
    assert space.warning("M-NO-STORE") is not None


def test_run_today_reads_the_store_when_asked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "store"
    _populated(root)
    monkeypatch.setattr(builder_module, "run_market_scan", lambda s, **k: _scan())
    space = run_today(
        ("BTCUSDT",),
        reference_time=REFERENCE,
        store_root=root,
        archive_root=tmp_path / "archive",
        read_marks=False,
    )
    assert space.portfolio.store_present is True
    assert space.portfolio.open_count


def test_run_today_names_the_store_it_read_in_its_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(builder_module, "run_market_scan", lambda s, **k: _scan())
    space = run_today(
        ("BTCUSDT",),
        reference_time=REFERENCE,
        store_root=tmp_path / "store",
        archive_root=tmp_path / "archive",
    )
    assert "store" in space.source
    assert str(tmp_path / "store") in space.source


def test_run_today_defaults_to_the_owner_store_root_without_touching_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default is resolved, and reading a root that does not exist creates
    nothing — so a test can prove the default without writing to the owner's
    machine."""
    seen: dict[str, object] = {}

    def _fake_read(root, *, at, archive_root=None, prices=None):
        seen["root"] = root
        return empty_reading(root)

    monkeypatch.setattr(builder_module, "run_market_scan", lambda s, **k: _scan())
    monkeypatch.setattr(builder_module, "read_store", _fake_read)
    run_today(("BTCUSDT",), reference_time=REFERENCE)
    from fmis.persistence import default_store_root

    assert seen["root"] == default_store_root()


def test_a_store_reading_is_a_record_and_not_a_live_handle() -> None:
    """So `build_today` receives data, never something that can fetch."""
    assert isinstance(reading(), StoreReading)
    assert not hasattr(reading(), "trades")
