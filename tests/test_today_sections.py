"""Milestone BJ — the section adapters.

Every test here checks the same property from a different angle: the adapter
*copies* and never *derives*. A value printed on the page is asserted equal to
the exact field on the `SetupAssessment` or domain record it came from, so an
adapter that started paraphrasing, rounding or recomputing would fail rather
than quietly produce a page that reads plausibly and is wrong.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmis.today import (
    RECENT_LIMIT,
    REGIME_NOTE,
    TodayError,
    NotAvailable,
    analysis_summary,
    journal_summary,
    market_overview_from_results,
    opportunities_from_results,
    portfolio_overview,
)
from today_helpers import failed_result, result

from tests.test_swing_setup_render import (
    candidate_short_with_watched_level,
    confirmed_long,
    waiting,
)


def unclassifiable():
    """A `WAIT` the engine could not classify, as opposed to one it declined.

    `waiting()` reaches WAIT with a `SUFFICIENT` decision context — the engine
    read the symbol and declined it. This one reaches WAIT with `INSUFFICIENT`,
    which is the other population entirely, and the two must never be counted
    together.
    """
    from fmis.decision_context import ContextState
    from fmis.decision_support import OverallState
    from fmis.market_regime import ParticipationState, StructureState, VolatilityState
    from fmis.structural_trend import StructuralTrendType
    from fmis.swing_setup import SetupInputs, evaluate_setup

    return evaluate_setup(
        SetupInputs(
            symbol="THINUSDT",
            as_of=datetime(2026, 1, 2, tzinfo=timezone.utc),
            source="fixture",
            context_interval="1w", setup_interval="1d", execution_interval="4h",
            context_structural_trend=StructuralTrendType.INDETERMINATE,
            setup_structural_trend=StructuralTrendType.INDETERMINATE,
            execution_structural_trend=StructuralTrendType.INDETERMINATE,
            context_regime_structure=StructureState.INSUFFICIENT,
            context_regime_volatility=VolatilityState.INSUFFICIENT,
            context_regime_participation=ParticipationState.INSUFFICIENT,
            evidence_state=OverallState.INSUFFICIENT_DATA,
            evidence_dominant_alignment=None,
            decision_context_state=ContextState.INSUFFICIENT,
            decision_context_statements=("too few closed candles",),
            execution_close=100.0, execution_closed_count=10,
            execution_levels=(), execution_breaks=(), setup_levels=(),
            inherited_limitations=(),
        )
    )


def _overview(results):
    return market_overview_from_results(results, opportunities_from_results(results))


# --------------------------------------------------------------------------
# Opportunities
# --------------------------------------------------------------------------


def test_every_printed_value_is_the_assessment_s_own() -> None:
    assessment = confirmed_long()
    grouped = opportunities_from_results((result(assessment),))
    printed = grouped.confirmed[0]
    assert printed.symbol == assessment.symbol
    assert printed.state == assessment.state.value
    assert printed.sufficiency == assessment.sufficiency.value
    assert printed.direction == assessment.direction.value
    assert printed.thesis == assessment.thesis
    assert printed.confirmation == assessment.confirmation
    assert printed.invalidation == assessment.invalidation
    assert printed.risk_reward == assessment.risk_reward.ratio
    assert printed.stop == assessment.stop.price
    assert printed.target == assessment.targets[0].price


def test_a_candidate_keeps_the_risk_reward_the_engine_already_computed() -> None:
    """An earlier surface dropped an already-computed number for CANDIDATE
    results; this asserts that cannot happen here."""
    assessment = candidate_short_with_watched_level()
    grouped = opportunities_from_results((result(assessment),))
    printed = grouped.candidates[0]
    assert printed.risk_reward == (
        None if assessment.risk_reward is None else assessment.risk_reward.ratio
    )
    assert printed.stop == (None if assessment.stop is None else assessment.stop.price)


def test_states_are_grouped_and_the_groups_do_not_overlap() -> None:
    grouped = opportunities_from_results(
        (
            result(confirmed_long()),
            result(candidate_short_with_watched_level()),
            result(waiting()),
            failed_result("BADUSDT"),
        )
    )
    assert len(grouped.confirmed) == 1
    assert len(grouped.candidates) == 1
    assert grouped.waiting_count == 1
    assert len(grouped.failed) == 1
    assert grouped.actionable_count == 2


def test_scan_order_is_preserved_inside_a_group() -> None:
    """Reversing the input reverses the group. Nothing sorts by any property."""
    from fmis.swing_setup.compose import SetupRunResult

    first = confirmed_long()
    second = SetupRunResult(
        requested_symbol="ZZZUSDT", assessment=confirmed_long()
    )
    forwards = opportunities_from_results((result(first), second))
    backwards = opportunities_from_results((second, result(first)))
    assert [line.symbol for line in forwards.confirmed] == [
        first.symbol,
        second.assessment.symbol,
    ]
    assert len(backwards.confirmed) == 2


def test_wait_results_group_on_the_engine_s_own_verbatim_reason() -> None:
    assessment = waiting()
    grouped = opportunities_from_results(
        (
            result(assessment),
            result(assessment),
        )
    )
    assert len(grouped.waiting) == 1
    assert grouped.waiting[0].reason == assessment.thesis[0]
    assert grouped.waiting[0].symbols == (assessment.symbol, assessment.symbol)


def test_wait_groups_are_ordered_by_how_many_symbols_reached_each_reason() -> None:
    """A distribution over already-stated reasons, not a ranking of trades."""
    common = waiting()
    rare = candidate_short_with_watched_level()
    grouped = opportunities_from_results(
        (result(common), result(common), result(rare))
    )
    assert grouped.waiting[0].symbols == (common.symbol, common.symbol)


def test_a_failed_symbol_carries_its_reason_verbatim() -> None:
    grouped = opportunities_from_results((failed_result("XUSDT", "provider said no"),))
    assert grouped.failed[0].detail == "provider said no"


@pytest.mark.parametrize("reported", ["   ", "\t\n"])
def test_a_blank_provider_message_does_not_take_the_whole_page_down(
    reported: str,
) -> None:
    """A regression test on a defect these tests found.

    Per-symbol failure isolation is worth nothing if one symbol's unhelpful
    error text can raise out of the assembly. A blank message is a message that
    said nothing, and the page says that rather than failing.
    """
    from fmis.swing_setup.compose import SetupRunResult

    grouped = opportunities_from_results(
        (SetupRunResult(requested_symbol="XUSDT", failure=reported),)
    )
    assert grouped.failed[0].detail == "no reason was reported"


def test_an_empty_universe_is_a_caller_error() -> None:
    with pytest.raises(TodayError, match="at least one"):
        opportunities_from_results(())


def test_a_string_is_not_a_result_sequence() -> None:
    with pytest.raises(TypeError):
        opportunities_from_results("BTCUSDT")


# --------------------------------------------------------------------------
# Market overview
# --------------------------------------------------------------------------


def test_no_single_directional_regime_label_is_produced() -> None:
    """ADR-0025 refuses a directional regime, and the page says so rather than
    leaving a reader to wonder where the headline went."""
    overview = _overview((result(waiting()),))
    assert overview.regime_note == REGIME_NOTE
    assert "ADR-0025" in overview.regime_note


def test_breadth_is_a_count_per_bucket_over_every_assessed_symbol() -> None:
    overview = _overview(
        (
            result(confirmed_long()),
            result(candidate_short_with_watched_level()),
            result(waiting()),
        )
    )
    assert sum(count for _, count in overview.breadth) == 3


def test_breadth_is_empty_when_nothing_was_assessed() -> None:
    overview = _overview((failed_result("XUSDT"),))
    assert overview.breadth == ()


def test_wait_results_split_into_read_and_declined_versus_unclassifiable() -> None:
    """The split `SWING_TRADING_READINESS_AUDIT_V1.md` R-12 names: shown as one
    number, a quiet system and a quiet market are indistinguishable."""
    unreadable = unclassifiable()
    declined = waiting()
    assert unreadable.sufficiency.value == "insufficient"
    assert declined.sufficiency.value == "sufficient"
    overview = _overview((result(unreadable), result(declined)))
    assert overview.unreadable == (unreadable.symbol,)
    assert overview.readable_declined == (declined.symbol,)


def test_the_status_counts_agree_with_the_grouped_opportunities() -> None:
    results = (
        result(confirmed_long()),
        result(candidate_short_with_watched_level()),
        result(waiting()),
        failed_result("XUSDT"),
    )
    grouped = opportunities_from_results(results)
    overview = market_overview_from_results(results, grouped)
    counts = dict(overview.status_counts)
    assert counts["confirmed"] == len(grouped.confirmed)
    assert counts["candidate"] == len(grouped.candidates)
    assert counts["wait"] == grouped.waiting_count
    assert counts["error"] == len(grouped.failed)
    assert sum(counts.values()) == overview.scanned


def test_a_scan_with_nothing_actionable_says_so() -> None:
    overview = _overview((result(waiting()),))
    assert any("No actionable setup" in note for note in overview.observations)


def test_a_scan_with_an_actionable_setup_does_not_say_so() -> None:
    overview = _overview((result(confirmed_long()),))
    assert not any("No actionable setup" in note for note in overview.observations)


def test_a_failure_is_observed_separately_from_a_wait() -> None:
    overview = _overview((result(confirmed_long()), failed_result("XUSDT")))
    assert any("no analysis at all" in note for note in overview.observations)


def test_the_analysis_instant_is_carried_from_the_assessment() -> None:
    assessment = confirmed_long()
    overview = _overview((result(assessment),))
    assert overview.analysis_as_of == assessment.as_of


def test_the_overview_rejects_a_foreign_opportunities_object() -> None:
    with pytest.raises(TypeError):
        market_overview_from_results((result(waiting()),), "opportunities")


# --------------------------------------------------------------------------
# Portfolio
# --------------------------------------------------------------------------


def _portfolio(**overrides):
    values = {
        "store_root": "/tmp/store",
        "store_present": True,
        "positions": (),
        "budget": None,
        "snapshot": None,
    }
    values.update(overrides)
    return portfolio_overview(**values)


def test_an_absent_budget_is_rendered_with_its_reason_not_as_no_limit() -> None:
    overview = _portfolio()
    assert isinstance(overview.budget_note, NotAvailable)
    assert "Do not infer" in overview.budget_note.forbidden_inference
    assert overview.limits == ()


def test_risk_is_never_reported_as_within_when_nothing_was_measured() -> None:
    """*"Indeterminate must be visually distinct from within"* — held here by
    making the two different types rather than two spellings of one."""
    overview = _portfolio()
    assert isinstance(overview.committed_risk, NotAvailable)
    assert isinstance(overview.available_risk, NotAvailable)
    assert "within budget" in overview.committed_risk.forbidden_inference


def test_a_configured_budget_lists_its_limits_with_nothing_measured_against_them() -> None:
    from persistence_helpers import risk_budget

    budget = risk_budget()
    overview = _portfolio(budget=budget)
    assert isinstance(overview.budget_note, str)
    assert budget.budget_id in overview.budget_note
    assert len(overview.limits) == len(budget.limits)
    for rendered, configured in zip(overview.limits, budget.limits):
        assert rendered.limit_id == configured.limit_id
        assert rendered.scope == configured.scope.value
        assert rendered.severity == configured.severity.value
        assert isinstance(rendered.status, NotAvailable)


def test_an_absent_snapshot_forbids_reading_cash_as_zero() -> None:
    overview = _portfolio()
    assert isinstance(overview.cash, NotAvailable)
    assert "zero balance" in overview.cash.forbidden_inference
    assert overview.snapshot_as_of is None


def test_a_snapshot_is_reported_from_its_own_recorded_values() -> None:
    from persistence_helpers import portfolio_snapshot

    snapshot = portfolio_snapshot()
    overview = _portfolio(snapshot=snapshot)
    assert overview.snapshot_as_of == snapshot.as_of
    assert isinstance(overview.exposure, str)
    assert snapshot.exposure.gross.text in overview.exposure


def test_a_position_is_reported_from_the_fold_and_never_recomputed() -> None:
    from fmis.positions import fold_positions
    from fmis.today import DUST_POLICY
    from fmis.ledger import LedgerResolver
    from trade_domain_helpers import trade

    original = trade()
    resolved = LedgerResolver(trades=(original,), corrections=()).resolved()
    folded = fold_positions(resolved, dust=DUST_POLICY)
    overview = _portfolio(positions=folded)
    assert overview.open_count == len(folded)
    printed = overview.open_positions[0]
    assert printed.market == folded[0].market.value
    assert printed.direction == folded[0].direction.value
    assert printed.average_entry == folded[0].average_entry.arithmetic
    assert printed.trade_count == folded[0].trade_count
    assert printed.event_ids == folded[0].event_ids


# --------------------------------------------------------------------------
# Journal and analysis
# --------------------------------------------------------------------------


def test_an_empty_journal_forbids_reading_it_as_a_quiet_month() -> None:
    summary = journal_summary(entries=(), closed_positions=(), decisions=())
    assert isinstance(summary.note, NotAvailable)
    assert "quiet month" in summary.note.forbidden_inference


def test_a_journal_entry_is_reported_with_its_recollection_flag() -> None:
    from persistence_helpers import journal_entry
    from trade_domain_helpers import AT

    plain = journal_entry()
    hindsight = journal_entry(decision_resolved_at=AT(8))
    summary = journal_summary(
        entries=(plain, hindsight), closed_positions=(), decisions=()
    )
    assert [entry.recollection for entry in summary.entries] == [
        plain.recollection,
        hindsight.recollection,
    ]
    assert hindsight.recollection is True


def test_an_entry_with_no_title_still_renders_a_line() -> None:
    from fmis.provenance import Absent
    from persistence_helpers import journal_entry

    summary = journal_summary(
        entries=(journal_entry(title=Absent("no title"), body="a body"),),
        closed_positions=(),
        decisions=(),
    )
    assert summary.entries[0].title == "(no title)"


def test_only_the_most_recent_entries_are_shown_and_the_total_is_stated() -> None:
    from persistence_helpers import journal_entry
    from trade_domain_helpers import AT

    entries = tuple(
        journal_entry(title=f"entry {index}", recorded_at=AT(9 + index))
        for index in range(RECENT_LIMIT + 3)
    )
    summary = journal_summary(entries=entries, closed_positions=(), decisions=())
    assert len(summary.entries) == RECENT_LIMIT
    assert summary.entries[-1].title == entries[-1].title
    assert str(len(entries)) in summary.note


def test_live_proposal_lines_are_carried_verbatim() -> None:
    summary = journal_summary(
        entries=(), closed_positions=(), decisions=("P-1 · live · until X",)
    )
    assert summary.decisions == ("P-1 · live · until X",)
    assert isinstance(summary.note, str)


def test_no_archived_analysis_forbids_reading_it_as_nothing_changed() -> None:
    summary = analysis_summary(archived=(), citations=(), snapshots=())
    assert isinstance(summary.change_note, NotAvailable)
    assert "nothing having changed" in summary.change_note.forbidden_inference


def test_one_artifact_states_that_a_change_needs_two_observations() -> None:
    from persistence_helpers import analysis_record

    summary = analysis_summary(
        archived=(), citations=(analysis_record(),), snapshots=()
    )
    assert isinstance(summary.change_note, str)
    assert "needs two observations" in summary.change_note


def test_several_artifacts_state_what_a_comparison_would_need() -> None:
    from persistence_helpers import analysis_record
    from trade_domain_helpers import market_snapshot

    summary = analysis_summary(
        archived=(),
        citations=(analysis_record(),),
        snapshots=(market_snapshot(),),
    )
    assert isinstance(summary.change_note, str)
    assert "is not computed here" in summary.change_note


def test_a_citation_and_a_snapshot_report_their_own_identifiers() -> None:
    from persistence_helpers import analysis_record
    from trade_domain_helpers import market_snapshot

    citation = analysis_record()
    snapshot = market_snapshot()
    summary = analysis_summary(
        archived=(), citations=(citation,), snapshots=(snapshot,)
    )
    assert summary.citations[0].record_id == citation.record_id
    assert summary.citations[0].analysis_as_of == citation.analysis_as_of
    assert summary.snapshots[0].record_id == snapshot.snapshot_id
    assert summary.snapshots[0].subject == snapshot.market.value
    assert summary.snapshots[0].analysis_as_of == snapshot.built_at


def test_an_archived_manifest_row_reports_its_metadata_only() -> None:
    from fmis.archive import ManifestEntry, RecordType

    entry = ManifestEntry(
        record_id="workspace-BTCUSDT-20260812T090000Z-0123456789abcdef",
        record_type=RecordType.WORKSPACE,
        schema_version=1,
        archived_at=datetime(2026, 8, 12, 9, tzinfo=timezone.utc),
        analysis_as_of=datetime(2026, 8, 12, 8, tzinfo=timezone.utc),
        subject=("BTCUSDT",),
        relative_path="workspace/2026/08/x.json",
        content_digest="sha256:" + "a" * 64,
    )
    summary = analysis_summary(archived=(entry,), citations=(), snapshots=())
    assert summary.archived[0].record_id == entry.record_id
    assert summary.archived[0].record_type == entry.record_type.value
    assert summary.archived[0].subject == "BTCUSDT"


def test_a_scan_where_every_wait_was_unclassifiable_says_so() -> None:
    """The observation that distinguishes a quiet market from a quiet engine."""
    overview = _overview((result(unclassifiable()),))
    assert any(
        "could not classify it" in note for note in overview.observations
    )


def test_a_scan_with_a_mixed_wait_population_makes_no_such_claim() -> None:
    overview = _overview((result(unclassifiable()), result(waiting())))
    assert not any(
        "could not classify it" in note for note in overview.observations
    )


def test_a_closed_position_is_reported_from_the_fold() -> None:
    from datetime import timedelta
    from decimal import Decimal

    from fmis.ledger import LedgerResolver, TradeSide
    from fmis.positions import fold_positions
    from fmis.today import DUST_POLICY
    from trade_domain_helpers import trade

    opening = trade()
    closing = trade(
        side=TradeSide.SELL,
        quantity=opening.quantity,
        price=Decimal("40000"),
        occurred_at=opening.occurred_at + timedelta(hours=2),
    )
    folded = fold_positions(
        LedgerResolver(trades=(opening, closing), corrections=()).resolved(),
        dust=DUST_POLICY,
    )
    closed = [position for position in folded if not position.is_open]
    summary = journal_summary(
        entries=(), closed_positions=tuple(closed), decisions=()
    )
    assert len(summary.closed_positions) == 1
    printed = summary.closed_positions[0]
    assert printed.market == closed[0].market.value
    assert printed.closed_at == closed[0].closed_at
    assert closed[0].realized_pnl_net.text in printed.realized_net


def test_wait_groups_really_are_ordered_by_population() -> None:
    """Two genuine WAIT groups, so reversing the order is observable.

    An earlier version of this test paired a WAIT result with a CANDIDATE one,
    which produced a single group and could not tell the two orderings apart —
    found by a mutation probe, not by reading it.
    """
    common = waiting()
    rare = unclassifiable()
    assert common.thesis[0] != rare.thesis[0]
    grouped = opportunities_from_results(
        (result(rare), result(common), result(common))
    )
    assert [len(group.symbols) for group in grouped.waiting] == [2, 1]
    assert grouped.waiting[0].reason == common.thesis[0]
    assert grouped.waiting[1].reason == rare.thesis[0]
