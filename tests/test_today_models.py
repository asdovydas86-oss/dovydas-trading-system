"""Milestone BJ — the Daily Trading Workspace's value types.

The theme is that this model refuses to hold a state the page could misreport.
Absence needs a reason *and* a forbidden inference; a refusal and a warning
cannot share a list; a queue entry cannot appear in the wrong half of the queue;
and a workspace cannot exist without stating its limitations.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmis.today import (
    TODAY_SCHEMA_VERSION,
    AnalysisLine,
    AnalysisSummary,
    ClosedPositionLine,
    FailedSymbol,
    JournalLine,
    JournalSummary,
    LimitLine,
    MarketOverview,
    Opportunities,
    OpportunityLine,
    PositionLine,
    PriorityQueue,
    QueueEntry,
    StoreUnreadableError,
    TodayError,
    TodayWorkspace,
    NotAvailable,
    WaitGroup,
    WarningClass,
    WarningSeverity,
    WorkspaceWarning,
)
from today_helpers import REFERENCE, line, portfolio, reading, result, workspace

from tests.test_swing_setup_render import confirmed_long, waiting


def _warning(severity: WarningSeverity = WarningSeverity.WARNING) -> WorkspaceWarning:
    return WorkspaceWarning(
        code="X-1",
        kind=WarningClass.RISK,
        severity=severity,
        statement="a statement",
        evidence="a source",
    )


# --------------------------------------------------------------------------
# Absence
# --------------------------------------------------------------------------


def test_an_absence_needs_all_three_of_its_fields() -> None:
    """The forbidden inference is the load-bearing one and has no default."""
    for missing in ("reason", "owned_by", "forbidden_inference"):
        fields = {
            "reason": "r",
            "owned_by": "o",
            "forbidden_inference": "f",
            missing: "  ",
        }
        with pytest.raises(TodayError):
            NotAvailable(**fields)


def test_an_absence_carries_the_inference_it_forbids() -> None:
    absent = NotAvailable(
        reason="no mark source exists",
        owned_by="the risk layer",
        forbidden_inference="Do not read this as risk being within budget.",
    )
    assert "Do not read" in absent.forbidden_inference


# --------------------------------------------------------------------------
# Warnings
# --------------------------------------------------------------------------


def test_a_warning_cannot_ship_without_a_stated_source() -> None:
    with pytest.raises(TodayError):
        WorkspaceWarning(
            code="X-1",
            kind=WarningClass.RISK,
            severity=WarningSeverity.WARNING,
            statement="a statement",
            evidence="   ",
        )


def test_a_warning_rejects_a_non_member_kind_or_severity() -> None:
    with pytest.raises(TypeError):
        WorkspaceWarning(
            code="X", kind="risk", severity=WarningSeverity.WARNING,
            statement="s", evidence="e",
        )
    with pytest.raises(TypeError):
        WorkspaceWarning(
            code="X", kind=WarningClass.RISK, severity="warning",
            statement="s", evidence="e",
        )


def test_a_warning_rejects_a_blank_subject_or_detail() -> None:
    with pytest.raises(TodayError):
        WorkspaceWarning(
            code="X", kind=WarningClass.RISK, severity=WarningSeverity.WARNING,
            statement="s", evidence="e", subjects=("",),
        )
    with pytest.raises(TodayError):
        WorkspaceWarning(
            code="X", kind=WarningClass.RISK, severity=WarningSeverity.WARNING,
            statement="s", evidence="e", detail=("  ",),
        )


def test_subjects_must_be_a_tuple() -> None:
    with pytest.raises(TypeError):
        WorkspaceWarning(
            code="X", kind=WarningClass.RISK, severity=WarningSeverity.WARNING,
            statement="s", evidence="e", subjects=["BTCUSDT"],
        )


# --------------------------------------------------------------------------
# The two registers never share a list
# --------------------------------------------------------------------------


def test_a_refusal_may_not_be_filed_as_an_ordinary_warning() -> None:
    """A block is not a worse setup. Rendering it as one would be a lie about
    what the system did."""
    with pytest.raises(TodayError, match="blocked_by"):
        QueueEntry(opportunity=line(), warnings=(_warning(WarningSeverity.BLOCK),))


def test_a_warning_may_not_be_filed_as_a_refusal() -> None:
    with pytest.raises(TodayError, match="not a block"):
        QueueEntry(opportunity=line(), blocked_by=(_warning(),))


def test_a_queue_entry_rejects_a_non_opportunity() -> None:
    with pytest.raises(TypeError):
        QueueEntry(opportunity="BTCUSDT")


def test_a_blocked_entry_cannot_sit_in_the_attention_list() -> None:
    blocked = QueueEntry(
        opportunity=line(), blocked_by=(_warning(WarningSeverity.BLOCK),)
    )
    with pytest.raises(TodayError, match="belongs in"):
        PriorityQueue(needs_attention=(blocked,), blocked=(), ordering="rule")


def test_an_unblocked_entry_cannot_sit_in_the_blocked_list() -> None:
    with pytest.raises(TodayError, match="must name what refused it"):
        PriorityQueue(
            needs_attention=(), blocked=(QueueEntry(opportunity=line()),),
            ordering="rule",
        )


def test_a_queue_states_its_own_ordering_rule() -> None:
    queue = PriorityQueue(needs_attention=(), blocked=(), ordering="attention order")
    assert queue.ordering
    assert queue.is_empty


# --------------------------------------------------------------------------
# Opportunities
# --------------------------------------------------------------------------


def test_an_opportunity_accepts_an_absent_direction_stop_and_target() -> None:
    """WAIT results and stopless candidates are ordinary, not errors."""
    bare = OpportunityLine(symbol="BTCUSDT", state="wait", sufficiency="limited")
    assert bare.direction is None
    assert bare.stop is None


def test_an_opportunity_rejects_a_non_numeric_ratio() -> None:
    with pytest.raises(TypeError):
        line(risk_reward="2.0")


def test_an_opportunity_rejects_a_boolean_ratio() -> None:
    """`True` is an `int` in Python and would render as `1.00`."""
    with pytest.raises(TypeError):
        line(risk_reward=True)


def test_a_wait_group_with_no_symbols_is_not_a_group() -> None:
    with pytest.raises(TodayError):
        WaitGroup(reason="a reason", symbols=())


def test_counts_are_projections_over_the_groups() -> None:
    opportunities = Opportunities(
        confirmed=(line(),),
        candidates=(line(symbol="ETHUSDT", state="candidate"),),
        waiting=(WaitGroup(reason="r", symbols=("A", "B")),),
        failed=(FailedSymbol(symbol="C", detail="d"),),
    )
    assert opportunities.actionable_count == 2
    assert opportunities.waiting_count == 2


def test_opportunities_rejects_the_wrong_member_type() -> None:
    with pytest.raises(TypeError):
        Opportunities(confirmed=("BTCUSDT",), candidates=(), waiting=(), failed=())


# --------------------------------------------------------------------------
# The workspace
# --------------------------------------------------------------------------


def test_a_workspace_must_state_its_limitations() -> None:
    space = workspace((result(confirmed_long()),))
    with pytest.raises(TodayError, match="limitations"):
        TodayWorkspace(
            reference_time=space.reference_time,
            objective=space.objective,
            source=space.source,
            market=space.market,
            portfolio=space.portfolio,
            opportunities=space.opportunities,
            queue=space.queue,
            paper=space.paper,
            performance=space.performance,
            journal=space.journal,
            analysis=space.analysis,
            warnings=space.warnings,
            limitations=(),
        )


def test_a_workspace_rejects_a_section_of_the_wrong_type() -> None:
    space = workspace((result(confirmed_long()),))
    with pytest.raises(TypeError, match="market"):
        TodayWorkspace(
            reference_time=space.reference_time,
            objective=space.objective,
            source=space.source,
            market="a market",
            portfolio=space.portfolio,
            opportunities=space.opportunities,
            queue=space.queue,
            paper=space.paper,
            performance=space.performance,
            journal=space.journal,
            analysis=space.analysis,
            warnings=space.warnings,
            limitations=space.limitations,
        )


def test_a_workspace_rejects_a_naive_reference_time_only_by_type() -> None:
    with pytest.raises(TypeError):
        workspace((result(confirmed_long()),), reference_time="2026-08-12")


def test_a_workspace_metadata_is_read_only() -> None:
    space = workspace((result(confirmed_long()),))
    with pytest.raises(TypeError):
        space.metadata["dust_policy"] = "something else"  # type: ignore[index]


def test_warnings_can_be_selected_by_class_and_by_code() -> None:
    space = workspace((result(waiting()),))
    limitations = space.warnings_of(WarningClass.LIMITATION)
    assert limitations
    assert all(w.kind is WarningClass.LIMITATION for w in limitations)
    assert space.warning("L-NO-SIZING") is not None
    assert space.warning("NOT-A-CODE") is None


def test_warnings_of_rejects_a_non_member() -> None:
    space = workspace((result(waiting()),))
    with pytest.raises(TypeError):
        space.warnings_of("risk")


def test_the_schema_version_is_pinned() -> None:
    """A consumer reading a stored page needs this to move deliberately.

    Bumped to `2` by Milestone BN, which is the deliberate move this test exists
    to force: `OpportunityLine` gained five approval fields and `Opportunities`
    gained the note that says whether an approval was computed at all. A consumer
    reading a version-1 page would render every candidate as unapproved, which is
    a different claim from *"this page did not check"*.

    Bumped to `3` by Milestone BO for the same reason one layer out: the page
    gained a whole section. A consumer reading a version-2 page against a store
    full of live paper trades would render none of them, which is a different
    claim from *"this page did not check"*.

    Bumped to `4` by Milestone BP, which added the performance section. The
    reason is one step stronger here: a consumer reading a version-4 page and
    ignoring `PerformanceSummary.sample_floor` would render a rate the guard
    **refused** as one the page merely lacked, which is the specific
    misreading `AP` §20.7 puts a boundary in front of.
    """
    assert TODAY_SCHEMA_VERSION == 4
    assert workspace((result(waiting()),)).schema_version == TODAY_SCHEMA_VERSION


# --------------------------------------------------------------------------
# The smaller records
# --------------------------------------------------------------------------


def test_a_position_line_requires_every_identifying_field() -> None:
    with pytest.raises(TodayError):
        PositionLine(
            market="  ", book="swing", direction="flat", quantity="1 BTC",
            average_entry="1 / 1", opened_at=REFERENCE, trade_count=1,
            event_ids=("e",),
        )


def test_a_position_line_rejects_a_negative_trade_count() -> None:
    with pytest.raises(TodayError):
        PositionLine(
            market="m", book="swing", direction="flat", quantity="1 BTC",
            average_entry="1 / 1", opened_at=REFERENCE, trade_count=-1,
            event_ids=(),
        )


def test_a_position_line_rejects_a_non_datetime_opened_at() -> None:
    with pytest.raises(TypeError):
        PositionLine(
            market="m", book="swing", direction="flat", quantity="1 BTC",
            average_entry="1 / 1", opened_at="yesterday", trade_count=1,
            event_ids=(),
        )


def test_a_limit_line_accepts_a_measured_value_or_an_absence() -> None:
    absent = NotAvailable(reason="r", owned_by="o", forbidden_inference="f")
    measured = LimitLine(
        limit_id="l", scope="per_trade_risk", stated_limit="2 percent",
        severity="hard_block", current="1.2 percent", status="within",
    )
    unmeasured = LimitLine(
        limit_id="l", scope="per_trade_risk", stated_limit="2 percent",
        severity="hard_block", current=absent, status=absent,
    )
    assert measured.status == "within"
    assert isinstance(unmeasured.status, NotAvailable)


def test_a_journal_summary_accepts_an_absence_as_its_note() -> None:
    absent = NotAvailable(reason="r", owned_by="o", forbidden_inference="f")
    summary = JournalSummary(
        entries=(), closed_positions=(), decisions=(), note=absent
    )
    assert isinstance(summary.note, NotAvailable)


def test_a_journal_line_carries_whether_it_is_a_recollection() -> None:
    entry = JournalLine(
        entry_id="e", kind="note", recorded_at=REFERENCE, author="owner",
        title="t", recollection=True,
    )
    assert entry.recollection is True


def test_a_journal_line_rejects_a_non_boolean_recollection() -> None:
    with pytest.raises(TypeError):
        JournalLine(
            entry_id="e", kind="note", recorded_at=REFERENCE, author="owner",
            title="t", recollection="yes",
        )


def test_a_closed_position_line_requires_a_closing_instant() -> None:
    with pytest.raises(TypeError):
        ClosedPositionLine(
            market="m", book="swing", closed_at=None, realized_net="0 USDT",
            trade_count=2,
        )


def test_an_analysis_summary_accepts_an_absent_change_note() -> None:
    absent = NotAvailable(reason="r", owned_by="o", forbidden_inference="f")
    summary = AnalysisSummary(
        archived=(), citations=(), snapshots=(), change_note=absent
    )
    assert isinstance(summary.change_note, NotAvailable)


def test_an_analysis_line_requires_a_real_instant() -> None:
    with pytest.raises(TypeError):
        AnalysisLine(
            record_id="r", record_type="workspace", subject="BTCUSDT",
            analysis_as_of="2026-08-12",
        )


def test_a_market_overview_rejects_a_malformed_count_pair() -> None:
    with pytest.raises(TypeError):
        MarketOverview(
            scanned=1, status_counts=(("wait",),), breadth=(),
            readable_declined=(), unreadable=(), observations=(),
            regime_note="a note",
        )


def test_a_market_overview_rejects_a_negative_count() -> None:
    with pytest.raises(TodayError):
        MarketOverview(
            scanned=1, status_counts=(("wait", -1),), breadth=(),
            readable_declined=(), unreadable=(), observations=(),
            regime_note="a note",
        )


def test_a_market_overview_rejects_a_non_datetime_as_of() -> None:
    with pytest.raises(TypeError):
        MarketOverview(
            scanned=1, status_counts=(), breadth=(), readable_declined=(),
            unreadable=(), observations=(), regime_note="n",
            analysis_as_of="today",
        )


def test_a_portfolio_overview_rejects_a_non_boolean_presence() -> None:
    with pytest.raises(TypeError):
        portfolio(store_present="yes")


def test_a_portfolio_overview_rejects_a_non_datetime_snapshot_instant() -> None:
    with pytest.raises(TypeError):
        portfolio(snapshot_as_of="today")


def test_the_open_count_is_derived_never_stored() -> None:
    assert portfolio().open_count == 0


def test_the_store_unreadable_error_is_a_today_error() -> None:
    """So the outermost edge catches one exception type, not two."""
    assert issubclass(StoreUnreadableError, TodayError)


def test_a_store_reading_rejects_a_blank_root() -> None:
    with pytest.raises(TodayError):
        reading(root="   ")


def test_a_store_reading_rejects_a_list_where_a_tuple_is_required() -> None:
    with pytest.raises(TypeError):
        reading(positions=[])


def test_a_store_reading_rejects_a_non_boolean_presence() -> None:
    with pytest.raises(TypeError):
        reading(present="yes")


def test_the_reference_time_is_carried_verbatim() -> None:
    pinned = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
    space = workspace((result(waiting()),), reference_time=pinned)
    assert space.reference_time == pinned


# --------------------------------------------------------------------------
# The remaining type refusals, each on the branch that raises it
# --------------------------------------------------------------------------


def test_a_tuple_field_rejects_a_list() -> None:
    with pytest.raises(TypeError, match="tuple of QueueEntry"):
        PriorityQueue(needs_attention=[], blocked=(), ordering="rule")


def test_a_count_field_rejects_a_non_integer() -> None:
    with pytest.raises(TypeError, match="scanned must be an int"):
        MarketOverview(
            scanned="one", status_counts=(), breadth=(), readable_declined=(),
            unreadable=(), observations=(), regime_note="n",
        )


def test_a_count_pair_field_rejects_a_non_tuple() -> None:
    with pytest.raises(TypeError, match="status_counts must be a tuple"):
        MarketOverview(
            scanned=0, status_counts="wait", breadth=(), readable_declined=(),
            unreadable=(), observations=(), regime_note="n",
        )


def test_a_journal_line_rejects_a_non_datetime_recorded_at() -> None:
    with pytest.raises(TypeError, match="recorded_at"):
        JournalLine(
            entry_id="e", kind="note", recorded_at="yesterday", author="o",
            title="t", recollection=False,
        )


def test_a_closed_position_line_rejects_a_negative_trade_count() -> None:
    with pytest.raises(TodayError, match="trade_count"):
        ClosedPositionLine(
            market="m", book="swing", closed_at=REFERENCE,
            realized_net="0 USDT", trade_count=-1,
        )


def _rebuild(space, **changes):
    fields = {
        "reference_time": space.reference_time,
        "objective": space.objective,
        "source": space.source,
        "market": space.market,
        "portfolio": space.portfolio,
        "opportunities": space.opportunities,
        "queue": space.queue,
        "paper": space.paper,
        "performance": space.performance,
        "journal": space.journal,
        "analysis": space.analysis,
        "warnings": space.warnings,
        "limitations": space.limitations,
    }
    fields.update(changes)
    return TodayWorkspace(**fields)


def test_a_workspace_rejects_a_list_of_warnings() -> None:
    space = workspace((result(waiting()),))
    with pytest.raises(TypeError, match="warnings must be a tuple"):
        _rebuild(space, warnings=[])


def test_a_workspace_rejects_limitations_that_are_not_a_tuple() -> None:
    space = workspace((result(waiting()),))
    with pytest.raises(TypeError, match="limitations must be a tuple"):
        _rebuild(space, limitations="TD-1")


def test_a_workspace_rejects_a_limitation_that_is_not_a_pair() -> None:
    space = workspace((result(waiting()),))
    with pytest.raises(TypeError, match="must be a 2-tuple"):
        _rebuild(space, limitations=(("TD-1",),))


def test_a_workspace_rejects_a_non_integer_schema_version() -> None:
    space = workspace((result(waiting()),))
    with pytest.raises(TypeError, match="schema_version"):
        _rebuild(space, schema_version="1")


def test_a_workspace_rejects_a_non_datetime_reference_time_by_name() -> None:
    space = workspace((result(waiting()),))
    with pytest.raises(TypeError, match="reference_time must be a datetime"):
        _rebuild(space, reference_time="2026-08-12T21:00:00+00:00")
