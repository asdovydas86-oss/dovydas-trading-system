"""Milestone BS — the value types refuse what a page must never show.

Every validation here exists because the shape it rejects would be printed and
believed: a rank position that disagrees with the row's place, a symbol in two
sections, a digest claiming independence while listing the reasons it does not
hold, a workspace with no stated limitations.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from fmis.swing_workspace import (
    SWING_WORKSPACE_SCHEMA_VERSION,
    BookExposure,
    EvidenceDigest,
    GlobalSummary,
    NoTradeGroup,
    PaperPosition,
    RankComponent,
    RankKey,
    RankedSetup,
    SwingWorkspaceError,
    UnanalysedSymbol,
    rank_key_for,
)
from fmis.today import NotAvailable

from tests.swing_workspace_helpers import assessment, result, workspace_of
from tests.test_swing_workspace_ranking import line

MOMENT = datetime(2026, 8, 20, 21, 0, tzinfo=timezone.utc)


def digest(**overrides) -> EvidenceDigest:
    fields = dict(
        supporting=1,
        conflicting=0,
        missing=0,
        unavailable=0,
        agreeing_families=("trend",),
        conflicting_families=(),
        independence_established=False,
        decision_ready=True,
        decision_ready_reason="stated",
        caveats=("one shared input",),
    )
    fields.update(overrides)
    return EvidenceDigest(**fields)


def row(**overrides) -> RankedSetup:
    fields = dict(
        opportunity=line(),
        key=rank_key_for(line(), watchlist_index=0),
        position=1,
        evidence=digest(),
        identity="sha256:abc",
        paper_status="none",
    )
    fields.update(overrides)
    return RankedSetup(**fields)


def summary(**overrides) -> GlobalSummary:
    fields = dict(
        scanned=1,
        confirmed=1,
        candidates=0,
        waiting=0,
        unanalysed=0,
        open_positions=0,
        paper_positions=0,
        breadth=(("no direction", 1),),
        regime_note="no single label is produced",
        risk_state="stated",
        open_exposure="stated",
    )
    fields.update(overrides)
    return GlobalSummary(**fields)


# ---------------------------------------------------------------------------
# RankComponent and RankKey
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["name", "value", "source"])
def test_a_component_refuses_a_blank_field(field) -> None:
    fields = dict(name="readiness", value="confirmed", rank=0, source="engine")
    fields[field] = "  "
    with pytest.raises(SwingWorkspaceError, match="non-empty str"):
        RankComponent(**fields)


def test_a_component_refuses_a_negative_rank() -> None:
    with pytest.raises(SwingWorkspaceError, match="cannot be negative"):
        RankComponent(name="readiness", value="confirmed", rank=-1, source="engine")


def test_a_component_refuses_a_boolean_rank() -> None:
    with pytest.raises(TypeError, match="rank must be an int"):
        RankComponent(name="readiness", value="confirmed", rank=True, source="engine")


def test_a_key_refuses_a_non_component() -> None:
    with pytest.raises(TypeError, match="RankComponent"):
        RankKey(components=("readiness",))


def test_a_key_refuses_a_non_tuple() -> None:
    with pytest.raises(TypeError, match="must be a tuple"):
        RankKey(components=[])


# ---------------------------------------------------------------------------
# EvidenceDigest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field", ["supporting", "conflicting", "missing", "unavailable"]
)
def test_a_digest_refuses_a_negative_count(field) -> None:
    with pytest.raises(SwingWorkspaceError, match="cannot be negative"):
        digest(**{field: -1})


def test_a_digest_refuses_a_non_boolean_flag() -> None:
    with pytest.raises(TypeError, match="must be a bool"):
        digest(independence_established="yes")


def test_a_digest_refuses_a_blank_family_name() -> None:
    with pytest.raises(SwingWorkspaceError, match="non-empty str"):
        digest(agreeing_families=("",))


def test_a_digest_refuses_a_non_tuple_caveat_list() -> None:
    with pytest.raises(TypeError, match="must be a tuple of str"):
        digest(caveats=["one"])


def test_a_digest_may_establish_independence_with_no_caveats() -> None:
    assert digest(independence_established=True, caveats=()).caveats == ()


# ---------------------------------------------------------------------------
# RankedSetup
# ---------------------------------------------------------------------------


def test_a_row_refuses_a_non_opportunity() -> None:
    with pytest.raises(TypeError, match="OpportunityLine"):
        row(opportunity="BTCUSDT")


def test_a_row_refuses_a_non_key() -> None:
    with pytest.raises(TypeError, match="RankKey"):
        row(key=("readiness",))


def test_a_row_refuses_a_zero_position() -> None:
    with pytest.raises(SwingWorkspaceError, match="1-based"):
        row(position=0)


def test_a_row_refuses_a_non_integer_position() -> None:
    with pytest.raises(TypeError, match="position must be an int"):
        row(position="1")


def test_a_row_refuses_an_evidence_value_that_is_neither_digest_nor_absence() -> None:
    with pytest.raises(TypeError, match="EvidenceDigest or a NotAvailable"):
        row(evidence={"supporting": 1})


def test_a_row_refuses_a_blank_identity() -> None:
    with pytest.raises(SwingWorkspaceError, match="non-empty str"):
        row(identity=" ")


def test_a_row_exposes_its_symbol() -> None:
    assert row().symbol == "BTCUSDT"


# ---------------------------------------------------------------------------
# The small section types
# ---------------------------------------------------------------------------


def test_a_no_trade_group_refuses_a_blank_classification() -> None:
    with pytest.raises(SwingWorkspaceError, match="non-empty str"):
        NoTradeGroup(reason="a reason", classification="", symbols=("BTCUSDT",))


def test_an_unanalysed_symbol_refuses_a_blank_detail() -> None:
    with pytest.raises(SwingWorkspaceError, match="non-empty str"):
        UnanalysedSymbol(symbol="BTCUSDT", detail="  ")


def test_a_book_row_refuses_a_blank_label() -> None:
    with pytest.raises(SwingWorkspaceError, match="non-empty str"):
        BookExposure(label="", open_positions=0, market_value="1 USDT")


def test_a_book_row_accepts_a_stated_absence_for_its_value() -> None:
    absent = NotAvailable(reason="r", owned_by="o", forbidden_inference="f")

    assert BookExposure(
        label="paper", open_positions=1, market_value=absent
    ).market_value is absent


def paper(**overrides) -> PaperPosition:
    fields = dict(
        activation_id="ACT-1",
        market="BTCUSDT",
        state="open",
        open_size="1 BTC",
        bars_in_trade=2,
        stop_widenings=0,
        entry="100",
        initial_risk="10 USDT",
        total_r="0.5",
        max_favourable_r="1.1",
        max_adverse_r="-0.2",
        stop="95",
        initial_stop="95",
    )
    fields.update(overrides)
    return PaperPosition(**fields)


def test_a_paper_row_derives_halted_from_the_folded_state() -> None:
    assert paper(state="ambiguous").halted is True
    assert paper(state="open").halted is False


def test_a_paper_row_derives_whether_the_stop_has_moved() -> None:
    assert paper(stop="99", initial_stop="95").stop_moved is True
    assert paper().stop_moved is False


def test_a_paper_row_refuses_a_negative_bar_count() -> None:
    with pytest.raises(SwingWorkspaceError, match="cannot be negative"):
        paper(bars_in_trade=-1)


def test_a_paper_row_refuses_a_blank_market() -> None:
    with pytest.raises(SwingWorkspaceError, match="non-empty str"):
        paper(market="")


# ---------------------------------------------------------------------------
# GlobalSummary
# ---------------------------------------------------------------------------


def test_the_summary_refuses_a_negative_count() -> None:
    with pytest.raises(SwingWorkspaceError, match="cannot be negative"):
        summary(scanned=-1)


def test_the_summary_refuses_a_malformed_breadth_pair() -> None:
    with pytest.raises(TypeError, match="must be a 2-tuple"):
        summary(breadth=(("no direction",),))


def test_the_summary_refuses_a_non_tuple_breadth() -> None:
    with pytest.raises(TypeError, match="tuple of \\(label, count\\) pairs"):
        summary(breadth=[("no direction", 1)])


def test_the_summary_refuses_a_non_datetime_instant() -> None:
    with pytest.raises(TypeError, match="analysis_as_of must be a datetime"):
        summary(analysis_as_of="2026-08-20")


def test_the_summary_adds_its_two_actionable_counts() -> None:
    assert summary(confirmed=2, candidates=3).actionable == 5


# ---------------------------------------------------------------------------
# SwingWorkspace itself
# ---------------------------------------------------------------------------


def test_the_page_refuses_a_non_datetime_reference_time() -> None:
    workspace = workspace_of(result(assessment()))
    with pytest.raises(TypeError, match="reference_time must be a datetime"):
        replace(workspace, reference_time="2026-08-20")


def test_the_page_refuses_a_mismatched_section_type() -> None:
    workspace = workspace_of(result(assessment()))
    with pytest.raises(TypeError, match="summary must be a GlobalSummary"):
        replace(workspace, summary=object())


def test_the_page_refuses_a_stamped_position_that_disagrees_with_its_place() -> None:
    workspace = workspace_of(result(assessment()))
    misstamped = (replace(workspace.opportunities[0], position=7),)
    with pytest.raises(SwingWorkspaceError, match="stamped position"):
        replace(workspace, opportunities=misstamped, wait_list=())


def test_the_page_refuses_a_workspace_with_no_limitations() -> None:
    workspace = workspace_of(result(assessment()))
    with pytest.raises(SwingWorkspaceError, match="must state its limitations"):
        replace(workspace, limitations=())


def test_the_page_refuses_a_malformed_limitation_pair() -> None:
    workspace = workspace_of(result(assessment()))
    with pytest.raises(TypeError, match="must be a 2-tuple"):
        replace(workspace, limitations=(("WS-1",),))


def test_the_page_refuses_a_non_tuple_limitation_list() -> None:
    workspace = workspace_of(result(assessment()))
    with pytest.raises(TypeError, match="tuple of \\(code, text\\) pairs"):
        replace(workspace, limitations=[("WS-1", "text")])


def test_the_page_refuses_a_boolean_schema_version() -> None:
    workspace = workspace_of(result(assessment()))
    with pytest.raises(TypeError, match="schema_version must be an int"):
        replace(workspace, schema_version=True)


def test_the_page_refuses_a_blank_paper_note() -> None:
    workspace = workspace_of(result(assessment()))
    with pytest.raises(SwingWorkspaceError, match="non-empty str"):
        replace(workspace, paper_note="")


def test_the_page_carries_its_schema_version() -> None:
    assert workspace_of(result(assessment())).schema_version == (
        SWING_WORKSPACE_SCHEMA_VERSION
    )


def test_the_metadata_is_read_only() -> None:
    workspace = workspace_of(result(assessment()))
    with pytest.raises(TypeError):
        workspace.metadata["excluded_from_ranking"] = ()


def test_a_row_can_be_found_by_symbol_and_a_missing_one_reads_as_none() -> None:
    workspace = workspace_of(result(assessment("BTCUSDT")))

    assert workspace.row("BTCUSDT") is workspace.opportunities[0]
    assert workspace.row("ETHUSDT") is None


def test_looking_a_row_up_by_a_blank_symbol_is_refused() -> None:
    workspace = workspace_of(result(assessment()))
    with pytest.raises(SwingWorkspaceError, match="non-empty str"):
        workspace.row(" ")


def test_a_page_whose_market_section_is_wrong_is_refused() -> None:
    workspace = workspace_of(result(assessment()))
    with pytest.raises(TypeError, match="market must be a MarketOverview"):
        replace(workspace, market=object())


def test_a_page_refuses_a_non_row_in_an_actionable_section() -> None:
    workspace = workspace_of(result(assessment()))
    with pytest.raises(TypeError, match="wait_list\\[0\\] must be a RankedSetup"):
        replace(workspace, wait_list=("ETHUSDT",))
