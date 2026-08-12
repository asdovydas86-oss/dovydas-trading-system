"""Type guards, decode failures and edge cases, swept systematically.

Every record in this domain validates in `__post_init__` and rejects a malformed
payload on decode. Those branches are the ones a feature test never reaches and
the ones a caller meets first when something is wrong, so they are covered here
rather than left to a future incident.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from trade_domain_helpers import (
    ACCOUNT,
    AT,
    BTC,
    MARKET,
    USDT,
    anchor,
    consumed,
    decision_window,
    dust_policy,
    level,
    level_origin,
    lifecycle_event,
    market_snapshot,
    money,
    owner_context,
    proposal,
    quantity,
    reason_tag,
    role_reading,
    setup_reading,
    sufficiency,
    trade,
    version_set,
)

from fmis.accounts import AccountId, Book, MarketId, MarketMode, VenueId
from fmis.analysis_record import AnalysisRecord
from fmis.journal import (
    JournalEntry,
    JournalKind,
    JournalLink,
    JournalTag,
    LinkKind,
    TagOrigin,
    TradeJournal,
)
from fmis.ledger import (
    BalanceEffect,
    Correction,
    LedgerSource,
    Trade,
    TradeSide,
    TradeStatus,
)
from fmis.money import AssetCode, DustPolicy, Money, Quantity
from fmis.portfolio import (
    AllocationEntry,
    CashBalance,
    ExposureSummary,
    FlowSummary,
    Holding,
    MarkQuote,
    PortfolioSnapshot,
)
from fmis.positions import AverageCost, Position, PositionKey, fold_positions
from fmis.proposal import (
    DirectionalCase,
    LifecycleKind,
    ModelAttribution,
    OpportunityProposal,
    ProposalLifecycleEvent,
    StatedConfidence,
    fold_proposal_state,
)
from fmis.provenance import Absent, Assertion, ValueOrigin, VersionedTerm
from fmis.records import (
    ConsumedSource,
    DomainValidationError,
    PayloadDecodeError,
    RecordAudit,
    require_bool,
    require_int,
    require_member,
    require_optional_text,
    require_optional_utc,
    require_ordered,
    require_pattern,
    require_text,
    require_tuple_of,
)
from fmis.risk import (
    LimitEvaluation,
    LimitPeriod,
    LimitScope,
    LimitSeverity,
    LimitStatus,
    LimitUnit,
    RiskBudget,
    RiskBudgetState,
    RiskLimit,
    evaluate_budget,
)
from fmis.snapshotting import (
    Anchor,
    ConflictNote,
    DecisionWindow,
    EvidenceFamilyReading,
    FreshnessReading,
    IndependenceDisclosure,
    LevelOriginRef,
    LevelReading,
    LevelSideRef,
    MarketSnapshot,
    RegimeDimensionReading,
    RegimeReading,
    RequirementReading,
    RiskRewardReading,
    RoleReading,
    SetupReading,
    SnapshotRole,
    StopTriggerSemantics,
    SufficiencyReading,
    TradeDirection,
    TriggerBasis,
    WindowBar,
    WindowMode,
)
from fmis.versioning import VersionAxis, VersionSet


# --------------------------------------------------------------------------
# Shared validators.
# --------------------------------------------------------------------------


def test_require_text_strips_and_rejects_the_empty_and_the_non_string() -> None:
    assert require_text("  moved stop  ", "x") == "moved stop"
    with pytest.raises(DomainValidationError):
        require_text("   ", "x")
    with pytest.raises(TypeError):
        require_text(7, "x")


def test_require_optional_text_accepts_none_and_rejects_the_empty_string() -> None:
    assert require_optional_text(None, "x") is None
    assert require_optional_text(" note ", "x") == "note"
    with pytest.raises(DomainValidationError):
        require_optional_text("", "x")


def test_require_optional_utc_accepts_none_and_normalizes_the_rest() -> None:
    assert require_optional_utc(None, "x") is None
    assert require_optional_utc(AT(9), "x") == AT(9)


def test_require_int_rejects_a_bool_and_enforces_its_bound() -> None:
    assert require_int(3, "x", minimum=1) == 3
    with pytest.raises(TypeError):
        require_int(True, "x")
    with pytest.raises(DomainValidationError):
        require_int(0, "x", minimum=1)


def test_require_bool_rejects_a_truthy_non_bool() -> None:
    assert require_bool(False, "x") is False
    with pytest.raises(TypeError):
        require_bool(1, "x")


def test_require_member_rejects_the_raw_enum_value() -> None:
    assert require_member(Book.SWING, Book, "x") is Book.SWING
    with pytest.raises(TypeError):
        require_member("swing", Book, "x")


def test_require_tuple_of_rejects_a_list_and_a_wrong_item_type() -> None:
    assert require_tuple_of(("a",), str, "x", minimum_length=1) == ("a",)
    with pytest.raises(TypeError, match="must be a tuple"):
        require_tuple_of(["a"], str, "x")
    with pytest.raises(TypeError, match=r"x\[0\]"):
        require_tuple_of((1,), str, "x")
    with pytest.raises(DomainValidationError, match="at least 2"):
        require_tuple_of(("a",), str, "x", minimum_length=2)


def test_require_pattern_reports_the_pattern_it_failed() -> None:
    import re

    with pytest.raises(DomainValidationError, match=r"\^a\+\$"):
        require_pattern("b", re.compile(r"^a+$"), "x")


def test_require_ordered_accepts_ties_unless_strictness_is_asked_for() -> None:
    require_ordered([AT(9), AT(9), AT(10)], "x")
    with pytest.raises(DomainValidationError, match="ordered by time"):
        require_ordered([AT(9), AT(9)], "x", strict=True)
    with pytest.raises(DomainValidationError, match="ordered by time"):
        require_ordered([AT(10), AT(9)], "x")


# --------------------------------------------------------------------------
# Provenance and money guards.
# --------------------------------------------------------------------------


def test_absence_rejects_a_malformed_payload() -> None:
    with pytest.raises(PayloadDecodeError, match="JSON object"):
        Absent.from_payload("nothing")
    with pytest.raises(PayloadDecodeError, match="unknown"):
        Absent.from_payload({"reason": "x", "why": "y"})
    with pytest.raises(PayloadDecodeError, match="missing"):
        Absent.from_payload({})
    with pytest.raises(PayloadDecodeError, match="sample_size"):
        Absent.from_payload({"reason": "x", "sample_size": "three"})


def test_absence_rejects_a_negative_sample_size() -> None:
    with pytest.raises(DomainValidationError):
        Absent("x", sample_size=-1)


def test_an_assertion_rejects_a_malformed_payload() -> None:
    with pytest.raises(PayloadDecodeError, match="JSON object"):
        Assertion.from_payload("x", str)
    with pytest.raises(PayloadDecodeError, match="keys"):
        Assertion.from_payload({"value": "x"}, str)


def test_a_versioned_term_rejects_a_malformed_payload() -> None:
    with pytest.raises(PayloadDecodeError, match="JSON object"):
        VersionedTerm.from_payload("x")
    with pytest.raises(PayloadDecodeError, match="keys"):
        VersionedTerm.from_payload({"vocabulary_id": "a"})


def test_money_and_quantity_reject_a_non_money_operand() -> None:
    with pytest.raises(TypeError, match="expected Money"):
        Money(Decimal("1"), USDT) + Decimal("1")  # type: ignore[operator]
    with pytest.raises(TypeError, match="expected Quantity"):
        Quantity(Decimal("1"), BTC) - Decimal("1")  # type: ignore[operator]


def test_quantity_supports_the_comparisons_and_arithmetic_a_fold_needs() -> None:
    one = Quantity(Decimal("1"), BTC)
    two = Quantity(Decimal("2"), BTC)
    assert one < two and two > one and one <= one and two >= one
    assert (two - one) == one
    assert (-one).is_negative
    assert abs(-one) == one
    assert one.scale(Decimal("2")) == two
    assert Quantity.zero(BTC).is_zero
    assert str(one) == "1 BTC"
    with pytest.raises(TypeError):
        one.scale(2)  # type: ignore[arg-type]


def test_an_asset_code_rejects_a_non_string() -> None:
    with pytest.raises(TypeError):
        AssetCode(7)  # type: ignore[arg-type]
    assert str(AssetCode("BTC")) == "BTC"


def test_a_dust_policy_rejects_a_malformed_payload_and_shape() -> None:
    with pytest.raises(TypeError, match="tuple"):
        DustPolicy("dust", 1, thresholds=[(BTC, Decimal("1"))])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="pair"):
        DustPolicy("dust", 1, thresholds=((BTC,),))  # type: ignore[arg-type]
    with pytest.raises(PayloadDecodeError, match="JSON object"):
        DustPolicy.from_payload("dust")
    with pytest.raises(PayloadDecodeError, match="keys"):
        DustPolicy.from_payload({"policy_id": "dust"})
    with pytest.raises(PayloadDecodeError, match="array"):
        DustPolicy.from_payload(
            {"policy_id": "dust", "version": 1, "thresholds": "none"}
        )
    with pytest.raises(PayloadDecodeError, match="entries"):
        DustPolicy.from_payload(
            {"policy_id": "dust", "version": 1, "thresholds": [{"asset": "BTC"}]}
        )


# --------------------------------------------------------------------------
# Records kernel guards.
# --------------------------------------------------------------------------


def test_a_consumed_source_rejects_a_non_string_record_id() -> None:
    with pytest.raises(TypeError):
        ConsumedSource(7, "sha256:" + "a" * 64, "trade")  # type: ignore[arg-type]


def test_normalizing_consumed_sources_rejects_a_wrong_type() -> None:
    from fmis.records import normalize_consumed_sources

    with pytest.raises(TypeError):
        normalize_consumed_sources(["not a source"])


def test_decoding_consumed_sources_requires_an_array() -> None:
    from fmis.records import decode_consumed_sources

    with pytest.raises(PayloadDecodeError, match="array"):
        decode_consumed_sources({"a": 1})


def test_require_mapping_rejects_a_non_string_key() -> None:
    from fmis.records import require_mapping

    with pytest.raises(PayloadDecodeError, match="non-str key"):
        require_mapping({1: "a"}, "widget")
    with pytest.raises(PayloadDecodeError, match="JSON object"):
        require_mapping("widget", "widget")


# --------------------------------------------------------------------------
# Versioning guards.
# --------------------------------------------------------------------------


def test_a_version_set_rejects_a_malformed_axis_tuple() -> None:
    with pytest.raises(TypeError, match="tuple of"):
        VersionSet(axes=[(VersionAxis.CODE_VERSION, "a")])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="pair"):
        VersionSet(axes=((VersionAxis.CODE_VERSION,),))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="VersionAxis"):
        VersionSet(axes=(("code_version", "a"),))  # type: ignore[arg-type]


def test_a_version_set_rejects_an_unwritable_schema_version() -> None:
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        VersionSet.of({}).__class__(axes=VersionSet.of({}).axes, schema_version=7)


def test_value_of_requires_a_version_axis() -> None:
    with pytest.raises(TypeError):
        VersionSet.of({}).value_of("code_version")  # type: ignore[arg-type]


def test_a_version_set_payload_must_be_shaped_correctly() -> None:
    version_set_payload = VersionSet.of({}).to_payload()
    version_set_payload["axes"] = "all of them"
    with pytest.raises(PayloadDecodeError, match="JSON object"):
        VersionSet.from_payload(version_set_payload)
    payload = VersionSet.of({}).to_payload()
    payload["axes"]["code_version"] = {"value": "a", "absent": {"reason": "b"}}
    with pytest.raises(PayloadDecodeError, match="exactly one"):
        VersionSet.from_payload(payload)
    payload = VersionSet.of({}).to_payload()
    payload["axes"]["code_version"] = {"maybe": "a"}
    with pytest.raises(PayloadDecodeError, match="neither"):
        VersionSet.from_payload(payload)


# --------------------------------------------------------------------------
# Snapshotting guards.
# --------------------------------------------------------------------------


def test_the_readings_reject_wrong_types() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        LevelReading("58400", LevelSideRef.BELOW, level_origin(), "x")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Decimal"):
        RiskRewardReading("1", Decimal("2"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="RegimeReading"):
        role_reading(regime="trending")
    with pytest.raises(TypeError, match="LevelReading or Absent"):
        role_reading(nearest_level_above="58400")
    with pytest.raises(TypeError, match="SufficiencyReading"):
        market_snapshot(sufficiency="sufficient")
    with pytest.raises(TypeError, match="SetupReading or Absent"):
        market_snapshot(setup="candidate")
    with pytest.raises(TypeError, match="IndependenceDisclosure or Absent"):
        market_snapshot(independence="kappa 0.41")
    with pytest.raises(TypeError, match="VersionSet"):
        market_snapshot(version_set="v1")
    with pytest.raises(TypeError, match="MarketId"):
        market_snapshot(market="BTCUSDT")


def test_the_setup_reading_rejects_wrong_types() -> None:
    with pytest.raises(TypeError, match="Decimal or Absent"):
        setup_reading(reference_price="61500")
    with pytest.raises(TypeError, match="LevelReading or Absent"):
        setup_reading(invalidation="58400")
    with pytest.raises(TypeError, match="RiskRewardReading or Absent"):
        setup_reading(risk_reward="2:1")
    with pytest.raises(TypeError, match="Anchor or Absent"):
        setup_reading(anchor="BTCUSDT-long")
    with pytest.raises(TypeError, match="FreshnessReading"):
        setup_reading(freshness=AT(9))
    with pytest.raises(TypeError, match="StopTriggerSemantics"):
        setup_reading(stop_trigger_semantics="touch")


def test_an_anchor_rejects_wrong_types() -> None:
    with pytest.raises(TypeError, match="MarketId"):
        Anchor("BTCUSDT", Book.SWING, TradeDirection.LONG, level_origin())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="LevelOriginRef"):
        Anchor(MARKET, Book.SWING, TradeDirection.LONG, "swing-114")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "decoder, payload, message",
    [
        (LevelOriginRef.from_payload, "x", "JSON object"),
        (LevelOriginRef.from_payload, {"origin_id": "x"}, "keys"),
        (LevelReading.from_payload, {"price": "1"}, "keys"),
        (RiskRewardReading.from_payload, {"risk_distance": "1"}, "keys"),
        (RegimeDimensionReading.from_payload, {"name": "x"}, "keys"),
        (RegimeReading.from_payload, {"dimensions": []}, "at least 1"),
        (RequirementReading.from_payload, {"requirement": "x"}, "keys"),
        (SufficiencyReading.from_payload, {"state": "x"}, "keys"),
        (EvidenceFamilyReading.from_payload, {"family": "x"}, "keys"),
        (IndependenceDisclosure.from_payload, {"note": "x"}, "keys"),
        (ConflictNote.from_payload, {"kind": "x"}, "keys"),
        (FreshnessReading.from_payload, {"measured_at": "x"}, "keys"),
        (StopTriggerSemantics.from_payload, {"stop_basis": "touch"}, "keys"),
        (Anchor.from_payload, {"market": {}}, "keys"),
        (SetupReading.from_payload, {"state": "x"}, "keys"),
        (RoleReading.from_payload, {"role": "context"}, "keys"),
    ],
)
def test_a_reading_rejects_a_malformed_payload(decoder, payload, message) -> None:
    with pytest.raises((PayloadDecodeError, DomainValidationError), match=message):
        decoder(payload)


def test_an_unknown_reading_enum_member_is_a_clean_rejection() -> None:
    payload = level().to_payload()
    payload["side"] = "sideways"
    with pytest.raises(PayloadDecodeError, match="LevelSideRef"):
        LevelReading.from_payload(payload)


def test_a_reading_array_field_must_actually_be_an_array() -> None:
    payload = market_snapshot().to_payload()
    payload["roles"] = "three of them"
    with pytest.raises(PayloadDecodeError, match="array"):
        MarketSnapshot.from_payload(payload)


def test_a_freshness_bar_age_must_decode_as_an_integer() -> None:
    payload = FreshnessReading(AT(9), 1, 1, 1).to_payload()
    payload["context_bars"] = {"value": "eight"}
    with pytest.raises(PayloadDecodeError, match="expected an int"):
        FreshnessReading.from_payload(payload)


def test_a_decision_window_rejects_wrong_types() -> None:
    with pytest.raises(TypeError, match="MarketId"):
        decision_window(market="BTCUSDT")
    with pytest.raises(TypeError, match="VersionSet"):
        decision_window(version_set="v1")
    with pytest.raises(TypeError, match="Decimal"):
        WindowBar(AT(0), 1.0, Decimal("2"), Decimal("1"), Decimal("1"), Decimal("1"))  # type: ignore[arg-type]


def test_a_window_bar_count_must_be_at_least_one() -> None:
    with pytest.raises(DomainValidationError, match="at least 1"):
        decision_window(WindowMode.REFERENCE, bar_count=0)


def test_a_window_rejects_an_unwritable_schema_version() -> None:
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        decision_window(schema_version=7)


def test_a_pruned_capture_window_is_a_contradiction() -> None:
    with pytest.raises(DomainValidationError, match="documented downgrade"):
        decision_window(pruned_at=AT(12))


def test_a_window_payload_must_be_shaped_correctly() -> None:
    payload = decision_window().to_payload()
    payload["bars"] = "five of them"
    with pytest.raises(PayloadDecodeError, match="array"):
        DecisionWindow.from_payload(payload)
    payload = decision_window().to_payload()
    payload["mode"] = "sampled"
    with pytest.raises(PayloadDecodeError, match="WindowMode"):
        DecisionWindow.from_payload(payload)


def test_a_snapshot_rejects_an_unwritable_schema_version() -> None:
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        market_snapshot(schema_version=7)


def test_a_snapshot_rejects_a_decision_window_id_that_is_not_a_record_id() -> None:
    with pytest.raises(DomainValidationError, match="expected shape"):
        market_snapshot(decision_window_id="last week's candles")


def test_the_series_digest_helper_type_checks_its_input() -> None:
    from fmis.snapshotting import series_digest_of

    with pytest.raises(TypeError):
        series_digest_of(["not a bar"])  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Analysis record guards.
# --------------------------------------------------------------------------


def test_an_analysis_record_requires_a_non_empty_subject() -> None:
    with pytest.raises(DomainValidationError, match="at least 1"):
        AnalysisRecord(
            record_id="workspace-BTCUSDT-20260812T090000Z-0123456789abcdef",
            record_type="workspace",
            payload_schema_version=1,
            analysis_as_of=AT(9),
            subject=(),
            content_digest="sha256:" + "c" * 64,
            archived_at=AT(9),
            audit=RecordAudit.frozen_at(AT(9)),
        )


def test_an_analysis_record_payload_must_hold_an_array_subject() -> None:
    payload = AnalysisRecord(
        record_id="workspace-BTCUSDT-20260812T090000Z-0123456789abcdef",
        record_type="workspace",
        payload_schema_version=1,
        analysis_as_of=AT(9),
        subject=("BTCUSDT",),
        content_digest="sha256:" + "c" * 64,
        archived_at=AT(9),
        audit=RecordAudit.frozen_at(AT(9)),
    ).to_payload()
    payload["subject"] = "BTCUSDT"
    with pytest.raises(Exception, match="array"):
        AnalysisRecord.from_payload(payload)


# --------------------------------------------------------------------------
# Proposal guards.
# --------------------------------------------------------------------------


def test_a_proposal_rejects_wrong_types() -> None:
    with pytest.raises(TypeError, match="MarketId"):
        proposal(market="BTCUSDT")
    with pytest.raises(TypeError, match="DirectionalAssessment"):
        proposal(directional_assessment="long")
    with pytest.raises(TypeError, match="LevelReading or Absent"):
        proposal(stop="58400")
    with pytest.raises(TypeError, match="RiskRewardReading or Absent"):
        proposal(risk_reward="2:1")
    with pytest.raises(TypeError, match="StatedConfidence"):
        proposal(stated_confidence="moderate")
    with pytest.raises(TypeError, match="Anchor or Absent"):
        proposal(anchor="BTCUSDT-long")
    with pytest.raises(TypeError, match="VersionSet"):
        proposal(version_set="v1")
    with pytest.raises(TypeError, match="ModelAttribution or Absent"):
        proposal(model="claude")


def test_a_proposal_rejects_an_unwritable_schema_version() -> None:
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        proposal(schema_version=7)


def test_a_proposal_supersedes_must_be_a_record_id() -> None:
    with pytest.raises(DomainValidationError, match="expected shape"):
        proposal(supersedes="the one from tuesday")


def test_a_directional_case_requires_non_empty_factors_text() -> None:
    with pytest.raises(DomainValidationError, match="non-empty"):
        DirectionalCase(TradeDirection.LONG, ("",), "statement")


@pytest.mark.parametrize(
    "decoder, payload, message",
    [
        (DirectionalCase.from_payload, {"direction": "long"}, "missing"),
        (ModelAttribution.from_payload, {"model_id": "m"}, "missing"),
    ],
)
def test_a_proposal_component_rejects_a_malformed_payload(
    decoder, payload, message
) -> None:
    with pytest.raises(PayloadDecodeError, match=message):
        decoder(payload)


def test_a_proposal_array_field_must_actually_be_an_array() -> None:
    payload = proposal().to_payload()
    payload["entry_conditions"] = "close above 62000"
    with pytest.raises(PayloadDecodeError, match="array"):
        OpportunityProposal.from_payload(payload)


def test_a_directional_case_payload_factors_must_be_an_array() -> None:
    payload = proposal().to_payload()["directional_assessment"]["long_case"]
    payload["factors"] = "trend up"
    with pytest.raises(PayloadDecodeError, match="array"):
        DirectionalCase.from_payload(payload)


def test_an_unknown_proposal_author_is_a_clean_rejection() -> None:
    payload = proposal().to_payload()
    payload["author"] = "an oracle"
    with pytest.raises(PayloadDecodeError, match="ProposalAuthor"):
        OpportunityProposal.from_payload(payload)


def test_a_lifecycle_event_rejects_wrong_types() -> None:
    subject = proposal()
    with pytest.raises(TypeError, match="VersionedTerm or Absent"):
        lifecycle_event(
            subject,
            LifecycleKind.OWNER_DECIDED,
            10,
            causing_close_time=Absent("asserted"),
            reason_tag="accepted",
        )
    with pytest.raises(TypeError, match="same_bar must be a bool"):
        lifecycle_event(subject, LifecycleKind.REAFFIRMED, 10, same_bar="yes")


def test_a_lifecycle_event_rejects_an_unwritable_schema_version() -> None:
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        lifecycle_event(proposal(), LifecycleKind.REAFFIRMED, 10, schema_version=7)


def test_a_lifecycle_event_supersedes_must_be_a_record_id() -> None:
    with pytest.raises(DomainValidationError, match="expected shape"):
        lifecycle_event(
            proposal(), LifecycleKind.REAFFIRMED, 10, supersedes="the wrong one"
        )


def test_the_fold_rejects_a_list_of_events() -> None:
    with pytest.raises(TypeError, match="must be a ProposalLifecycleEvent"):
        fold_proposal_state(proposal(), ["not an event"])


def test_admission_type_checks_every_input() -> None:
    from fmis.proposal import admit

    subject = proposal()
    with pytest.raises(TypeError, match="OpportunityProposal"):
        admit(
            "a proposal", (), occurred_at=AT(10), recorded_at=AT(10),
            causing_close_time=AT(10),
        )
    with pytest.raises(TypeError, match="OpportunityProposal"):
        admit(
            subject,
            (("x", fold_proposal_state(subject, ())),),
            occurred_at=AT(10),
            recorded_at=AT(10),
            causing_close_time=AT(10),
        )
    with pytest.raises(TypeError, match="ProposalStateView"):
        admit(
            subject,
            ((subject, "live"),),
            occurred_at=AT(10),
            recorded_at=AT(10),
            causing_close_time=AT(10),
        )


def test_a_proposal_admission_rejects_an_inconsistent_result() -> None:
    from fmis.proposal import AdmissionOutcome, ProposalAdmission

    subject = proposal()
    with pytest.raises(DomainValidationError, match="carries the event"):
        ProposalAdmission(
            AdmissionOutcome.REAFFIRMED, subject, Absent("nothing to reaffirm")
        )
    with pytest.raises(DomainValidationError, match="nothing to reaffirm"):
        ProposalAdmission(
            AdmissionOutcome.CREATED,
            subject,
            lifecycle_event(subject, LifecycleKind.REAFFIRMED, 10),
        )
    with pytest.raises(TypeError, match="OpportunityProposal"):
        ProposalAdmission(AdmissionOutcome.CREATED, "x", Absent("none"))
    with pytest.raises(TypeError, match="ProposalLifecycleEvent or Absent"):
        ProposalAdmission(AdmissionOutcome.REAFFIRMED, subject, "reaffirmed")


def test_a_state_view_type_checks_its_fields() -> None:
    from fmis.proposal import ProposalState, ProposalStateView

    with pytest.raises(TypeError):
        ProposalStateView("live", ())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ProposalStateView(ProposalState.LIVE, ("a",), is_ambiguous="yes")  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Ledger guards.
# --------------------------------------------------------------------------


def test_a_trade_rejects_wrong_types() -> None:
    with pytest.raises(TypeError, match="AccountId"):
        trade(account="binance_spot")
    with pytest.raises(TypeError, match="MarketId"):
        trade(market="BTCUSDT")
    with pytest.raises(TypeError, match="Quantity"):
        trade(quantity=Decimal("0.5"))
    with pytest.raises(TypeError, match="price must be a Decimal"):
        trade(price="60000")
    with pytest.raises(TypeError, match="fee must be a Money"):
        trade(fee=Decimal("15"))
    with pytest.raises(TypeError, match="fx_rate_to_tax_currency must be a Decimal"):
        trade(fx_rate_to_tax_currency="10.5")
    with pytest.raises(TypeError, match="is_maker must be a bool or Absent"):
        trade(is_maker="yes")


def test_a_trade_rejects_an_unwritable_schema_version() -> None:
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        trade(schema_version=7)


def test_a_trade_records_an_optional_reported_at_for_an_import() -> None:
    imported = trade(
        source=LedgerSource.STATEMENT_IMPORT,
        reported_at=AT(11),
        asserted_by="binance statement",
    )
    assert imported.reported_at == AT(11)
    assert Trade.from_payload(imported.to_payload()) == imported


def test_a_balance_effect_type_checks_its_fields() -> None:
    with pytest.raises(TypeError, match="AccountId"):
        BalanceEffect("binance_spot", quantity("1"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Quantity"):
        BalanceEffect(ACCOUNT, Decimal("1"))  # type: ignore[arg-type]
    effect = BalanceEffect(ACCOUNT, quantity("1"))
    assert effect.asset == BTC
    assert "binance_spot" in str(effect)


def test_a_correction_rejects_wrong_types_and_an_unwritable_version() -> None:
    original = trade()
    replacement = trade(price=Decimal("60001"))
    with pytest.raises(TypeError, match="replacement must be a Trade"):
        Correction(
            supersedes=original.event_id,
            replacement=replacement.to_payload(),  # type: ignore[arg-type]
            reason=reason_tag("x", "correction_reason"),
            author="owner",
            occurred_at=AT(11),
            recorded_at=AT(11),
            audit=RecordAudit.frozen_at(AT(11)),
        )
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        Correction(
            supersedes=original.event_id,
            replacement=replacement,
            reason=reason_tag("x", "correction_reason"),
            author="owner",
            occurred_at=AT(11),
            recorded_at=AT(11),
            audit=RecordAudit.frozen_at(AT(11)),
            schema_version=7,
        )


def test_a_correction_recorded_before_it_happened_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="recorded_at precedes"):
        Correction(
            supersedes=trade().event_id,
            replacement=trade(price=Decimal("60001")),
            reason=reason_tag("x", "correction_reason"),
            author="owner",
            occurred_at=AT(12),
            recorded_at=AT(11),
            audit=RecordAudit.frozen_at(AT(12)),
        )


def test_a_correction_may_carry_a_note() -> None:
    subject = Correction(
        supersedes=trade().event_id,
        replacement=trade(price=Decimal("60001")),
        reason=reason_tag("x", "correction_reason"),
        author="owner",
        occurred_at=AT(11),
        recorded_at=AT(11),
        audit=RecordAudit.frozen_at(AT(11)),
        note="the app showed the pre-fee price",
    )
    assert Correction.from_payload(subject.to_payload()) == subject


def test_a_trade_payload_must_hold_a_boolean_is_maker() -> None:
    payload = trade(is_maker=True).to_payload()
    payload["is_maker"] = {"value": "yes"}
    with pytest.raises(PayloadDecodeError, match="expected a bool"):
        Trade.from_payload(payload)


def test_a_trade_payload_must_hold_an_integer_occurrence_index() -> None:
    payload = trade(occurrence_index=2).to_payload()
    payload["occurrence_index"] = {"value": "two"}
    with pytest.raises(PayloadDecodeError, match="expected an int"):
        Trade.from_payload(payload)


# --------------------------------------------------------------------------
# Positions guards.
# --------------------------------------------------------------------------


def test_a_position_type_checks_every_field() -> None:
    (position,) = fold_positions(
        __import__("fmis.ledger", fromlist=["resolve"]).resolve((trade(),)).resolved(),
        dust=dust_policy(),
    )
    fields = {
        name: getattr(position, name) for name in Position.__dataclass_fields__
    }
    for name, bad in (
        ("key", "a key"),
        ("market", "BTCUSDT"),
        ("net_quantity", Decimal("1")),
        ("average_entry", "61000"),
        ("average_exit", "61000"),
        ("realized_pnl_gross", Decimal("1")),
        ("max_exposure", Decimal("1")),
    ):
        with pytest.raises(TypeError):
            Position(**{**fields, name: bad})


def test_a_position_rejects_contradictory_state() -> None:
    (position,) = fold_positions(
        __import__("fmis.ledger", fromlist=["resolve"]).resolve((trade(),)).resolved(),
        dust=dust_policy(),
    )
    fields = {
        name: getattr(position, name) for name in Position.__dataclass_fields__
    }
    from fmis.positions import PositionDirection, PositionState

    with pytest.raises(DomainValidationError, match="states when it closed"):
        Position(**{**fields, "state": PositionState.CLOSED,
                    "direction": PositionDirection.FLAT})
    with pytest.raises(DomainValidationError, match="has no closed_at"):
        Position(**{**fields, "closed_at": AT(12)})
    with pytest.raises(DomainValidationError, match="closed position is flat"):
        Position(
            **{
                **fields,
                "state": PositionState.CLOSED,
                "closed_at": AT(12),
                "direction": PositionDirection.LONG,
            }
        )
    with pytest.raises(DomainValidationError, match="how a position ended"):
        Position(**{**fields, "closed_by_flip": True})
    with pytest.raises(DomainValidationError, match="precedes opened_at"):
        Position(
            **{
                **fields,
                "state": PositionState.CLOSED,
                "direction": PositionDirection.FLAT,
                "closed_at": AT(1),
            }
        )
    with pytest.raises(DomainValidationError, match="must not appear twice"):
        Position(**{**fields, "fees": (money("1"), money("2"))})
    with pytest.raises(TypeError):
        Position(**{**fields, "closed_by_flip": "yes"})


def test_the_average_cost_type_checks_its_pair() -> None:
    with pytest.raises(TypeError, match="total_cost must be a Money"):
        AverageCost(Decimal("1"), quantity("1"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="total_quantity must be a Quantity"):
        AverageCost(money("1"), Decimal("1"))  # type: ignore[arg-type]


def test_unrealized_pnl_type_checks_its_mark() -> None:
    (position,) = fold_positions(
        __import__("fmis.ledger", fromlist=["resolve"]).resolve((trade(),)).resolved(),
        dust=dust_policy(),
    )
    with pytest.raises(TypeError, match="Decimal or Absent"):
        position.unrealized_pnl("62000", USDT)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Portfolio guards.
# --------------------------------------------------------------------------


def test_the_portfolio_components_type_check_their_fields() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        MarkQuote("60000", USDT, "binance", AT(8))  # type: ignore[arg-type]
    with pytest.raises(DomainValidationError, match="positive"):
        MarkQuote(Decimal("0"), USDT, "binance", AT(8))
    with pytest.raises(TypeError, match="AccountId"):
        Holding(BTC, "binance_spot", quantity("1"), Absent("no mark"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Quantity"):
        Holding(BTC, ACCOUNT, Decimal("1"), Absent("no mark"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="MarkQuote or Absent"):
        Holding(BTC, ACCOUNT, quantity("1"), Decimal("60000"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="AccountId"):
        CashBalance("binance_spot", money("1"), Absent("base"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Money"):
        CashBalance(ACCOUNT, Decimal("1"), Absent("base"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Decimal or Absent"):
        CashBalance(ACCOUNT, money("1"), "0.1", "riksbank")  # type: ignore[arg-type]
    with pytest.raises(DomainValidationError, match="positive"):
        CashBalance(ACCOUNT, money("1"), Decimal("-1"), "riksbank")
    with pytest.raises(TypeError, match="Money"):
        FlowSummary(Decimal("1"), money("0"), Absent("first"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Money"):
        ExposureSummary(Decimal("1"), money("1"), money("1"), money("1"), money("1"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Money or Absent"):
        ExposureSummary(money("1"), money("1"), money("1"), "1", money("1"))  # type: ignore[arg-type]
    with pytest.raises(DomainValidationError, match="magnitude"):
        ExposureSummary(
            money("-1"), money("1"), money("1"), money("1"), money("1")
        )
    with pytest.raises(TypeError, match="Money"):
        AllocationEntry("asset", "BTC", Decimal("1"), money("2"), "cls-v1")  # type: ignore[arg-type]
    with pytest.raises(DomainValidationError, match="one currency"):
        AllocationEntry(
            "asset", "BTC", money("1"), Money(Decimal("2"), AssetCode("SEK")), "cls-v1"
        )


def test_an_allocation_weight_over_a_zero_total_is_undefined() -> None:
    entry = AllocationEntry("asset", "BTC", money("0"), money("0"), "cls-v1")
    assert isinstance(entry.weight, Absent)


@pytest.mark.parametrize(
    "decoder, payload",
    [
        (MarkQuote.from_payload, {"price": "1"}),
        (Holding.from_payload, {"asset": "BTC"}),
        (CashBalance.from_payload, {"account": "binance_spot"}),
        (FlowSummary.from_payload, {"deposits": {}}),
        (ExposureSummary.from_payload, {"gross": {}}),
        (AllocationEntry.from_payload, {"dimension": "asset"}),
    ],
)
def test_a_portfolio_component_rejects_a_malformed_payload(decoder, payload) -> None:
    with pytest.raises(PayloadDecodeError):
        decoder(payload)


def test_a_portfolio_snapshot_rejects_wrong_types_and_versions() -> None:
    base = {
        "portfolio_id": "main",
        "base_currency": USDT,
        "as_of": AT(9),
        "books_covered": (Book.SWING,),
        "holdings": (),
        "cash": (),
        "flows": FlowSummary(money("0"), money("0"), Absent("first")),
        "exposure": ExposureSummary(
            money("0"), money("0"), money("0"), money("0"), Absent("none")
        ),
        "allocations": (),
        "open_position_event_ids": (),
        "version_set": version_set(),
        "audit": RecordAudit.frozen_at(AT(9)),
    }
    with pytest.raises(TypeError, match="ExposureSummary"):
        PortfolioSnapshot(**{**base, "exposure": "flat"})
    with pytest.raises(TypeError, match="VersionSet"):
        PortfolioSnapshot(**{**base, "version_set": "v1"})
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        PortfolioSnapshot(**{**base, "schema_version": 7})
    with pytest.raises(DomainValidationError, match="at least 1"):
        PortfolioSnapshot(**{**base, "books_covered": ()})


def test_a_portfolio_snapshot_payload_array_fields_must_be_arrays() -> None:
    from test_trade_domain_capital import _snapshot

    payload = _snapshot().to_payload()
    payload["holdings"] = "one of them"
    with pytest.raises(PayloadDecodeError, match="array"):
        PortfolioSnapshot.from_payload(payload)


def test_an_unknown_book_on_decode_is_a_clean_rejection() -> None:
    from test_trade_domain_capital import _snapshot

    payload = _snapshot().to_payload()
    payload["books_covered"] = ["scalping"]
    with pytest.raises(PayloadDecodeError, match="Book"):
        PortfolioSnapshot.from_payload(payload)


# --------------------------------------------------------------------------
# Risk guards.
# --------------------------------------------------------------------------


def test_a_risk_limit_rejects_a_non_positive_value_and_a_bad_default() -> None:
    with pytest.raises(DomainValidationError, match="must be positive"):
        RiskLimit(
            "leverage",
            LimitScope.LEVERAGE,
            Decimal("0"),
            LimitUnit.RATIO,
            LimitPeriod.NONE,
            LimitSeverity.ADVISORY,
        )
    with pytest.raises(DomainValidationError, match="a money limit must be positive"):
        RiskLimit(
            "daily_loss",
            LimitScope.PERIOD_LOSS,
            Money(Decimal("0"), USDT),
            LimitUnit.MONEY,
            LimitPeriod.DAY,
            LimitSeverity.HARD_BLOCK,
        )
    with pytest.raises(TypeError, match="Decimal or Absent"):
        RiskLimit(
            "leverage",
            LimitScope.LEVERAGE,
            Decimal("2"),
            LimitUnit.RATIO,
            LimitPeriod.NONE,
            LimitSeverity.ADVISORY,
            default_below_ceiling="1",
        )
    with pytest.raises(DomainValidationError, match="does not apply to a money limit"):
        RiskLimit(
            "daily_loss",
            LimitScope.PERIOD_LOSS,
            Money(Decimal("500"), USDT),
            LimitUnit.MONEY,
            LimitPeriod.DAY,
            LimitSeverity.HARD_BLOCK,
            default_below_ceiling=Decimal("100"),
        )


def test_a_risk_limit_may_name_the_key_it_constrains() -> None:
    limit = RiskLimit(
        "venue_concentration",
        LimitScope.CONCENTRATION,
        Decimal("0.4"),
        LimitUnit.PERCENT_OF_OPEN_RISK,
        LimitPeriod.NONE,
        LimitSeverity.ADVISORY,
        key="binance",
    )
    assert RiskLimit.from_payload(limit.to_payload()) == limit


def test_a_risk_budget_rejects_wrong_types_and_versions() -> None:
    limit = RiskLimit(
        "leverage",
        LimitScope.LEVERAGE,
        Decimal("2"),
        LimitUnit.RATIO,
        LimitPeriod.NONE,
        LimitSeverity.ADVISORY,
    )
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        RiskBudget("b", 1, AT(0), (limit,), RecordAudit.frozen_at(AT(0)), schema_version=7)
    with pytest.raises(DomainValidationError, match="at least 1"):
        RiskBudget("b", 1, AT(0), (), RecordAudit.frozen_at(AT(0)))
    budget = RiskBudget(
        "b", 1, AT(0), (limit,), RecordAudit.frozen_at(AT(0)), note="tightened"
    )
    assert RiskBudget.from_payload(budget.to_payload()) == budget


def test_a_risk_budget_payload_limits_must_be_an_array() -> None:
    limit = RiskLimit(
        "leverage",
        LimitScope.LEVERAGE,
        Decimal("2"),
        LimitUnit.RATIO,
        LimitPeriod.NONE,
        LimitSeverity.ADVISORY,
    )
    payload = RiskBudget("b", 1, AT(0), (limit,), RecordAudit.frozen_at(AT(0))).to_payload()
    payload["limits"] = "one of them"
    with pytest.raises(PayloadDecodeError, match="array"):
        RiskBudget.from_payload(payload)


def test_a_limit_evaluation_rejects_an_inconsistent_pair() -> None:
    with pytest.raises(TypeError, match="Decimal or Money"):
        LimitEvaluation("x", "0.02", Decimal("0.01"), LimitStatus.WITHIN)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Decimal, Money or Absent"):
        LimitEvaluation("x", Decimal("0.02"), "0.01", LimitStatus.WITHIN)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="LimitStatus or Absent"):
        LimitEvaluation("x", Decimal("0.02"), Decimal("0.01"), "within")  # type: ignore[arg-type]
    with pytest.raises(DomainValidationError, match="unmeasurable limit"):
        LimitEvaluation("x", Decimal("0.02"), Absent("unknown"), LimitStatus.WITHIN)
    with pytest.raises(DomainValidationError, match="ratio limit in a"):
        LimitEvaluation("x", Decimal("0.02"), money("1"), LimitStatus.WITHIN)


def test_evaluating_a_budget_type_checks_its_inputs() -> None:
    limit = RiskLimit(
        "leverage",
        LimitScope.LEVERAGE,
        Decimal("2"),
        LimitUnit.RATIO,
        LimitPeriod.NONE,
        LimitSeverity.ADVISORY,
    )
    budget = RiskBudget("b", 1, AT(0), (limit,), RecordAudit.frozen_at(AT(0)))
    with pytest.raises(TypeError, match="RiskBudget"):
        evaluate_budget("b", {}, evaluated_at=AT(9))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="dict"):
        evaluate_budget(budget, [("leverage", Decimal("1"))], evaluated_at=AT(9))  # type: ignore[arg-type]
    from fmis.risk import evaluate_limit

    with pytest.raises(TypeError, match="RiskLimit"):
        evaluate_limit("leverage", Decimal("1"))  # type: ignore[arg-type]


def test_a_risk_budget_state_rejects_an_empty_evaluation_set() -> None:
    with pytest.raises(DomainValidationError, match="at least 1"):
        RiskBudgetState("b", 1, AT(9), ())


def test_the_effective_budget_ignores_a_non_budget_in_the_stream() -> None:
    from fmis.risk import effective_budget

    assert isinstance(effective_budget(["not a budget"], AT(9)), Absent)


# --------------------------------------------------------------------------
# Journal guards.
# --------------------------------------------------------------------------


def test_a_journal_entry_type_checks_its_audit_and_collections() -> None:
    with pytest.raises(TypeError, match="RecordAudit"):
        JournalEntry(
            kind=JournalKind.NOTE, recorded_at=AT(9), author="owner", audit=AT(9),
            title="x",
        )
    with pytest.raises(TypeError, match="tuple"):
        JournalEntry(
            kind=JournalKind.NOTE,
            recorded_at=AT(9),
            author="owner",
            audit=RecordAudit.frozen_at(AT(9)),
            title="x",
            tags=[],
        )


def test_a_journal_entry_rejects_an_unwritable_schema_version() -> None:
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        JournalEntry(
            kind=JournalKind.NOTE,
            recorded_at=AT(9),
            author="owner",
            audit=RecordAudit.frozen_at(AT(9)),
            title="x",
            schema_version=7,
        )


def test_a_journal_payload_array_field_must_be_an_array() -> None:
    entry = JournalEntry(
        kind=JournalKind.NOTE,
        recorded_at=AT(9),
        author="owner",
        audit=RecordAudit.frozen_at(AT(9)),
        title="x",
    )
    payload = entry.to_payload()
    payload["tags"] = "one of them"
    with pytest.raises(PayloadDecodeError, match="array"):
        JournalEntry.from_payload(payload)


@pytest.mark.parametrize(
    "decoder, payload",
    [
        (JournalTag.from_payload, {"term": {}}),
        (JournalLink.from_payload, {"kind": "about"}),
    ],
)
def test_a_journal_component_rejects_a_malformed_payload(decoder, payload) -> None:
    with pytest.raises(PayloadDecodeError):
        decoder(payload)


def test_an_unknown_link_kind_on_decode_is_a_clean_rejection() -> None:
    payload = JournalLink(LinkKind.ABOUT, "market", "x").to_payload()
    payload["kind"] = "vaguely_related"
    with pytest.raises(PayloadDecodeError, match="LinkKind"):
        JournalLink.from_payload(payload)


def test_the_journal_view_type_checks_its_subject_and_entries() -> None:
    with pytest.raises(DomainValidationError):
        TradeJournal("", "x", ())
    with pytest.raises(TypeError):
        TradeJournal("market", "x", ["not an entry"])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        TradeJournal.gather("market", "x", (), ).of_kind("note")  # type: ignore[arg-type]


def test_a_supersedes_link_must_be_a_record_id() -> None:
    with pytest.raises(DomainValidationError, match="expected shape"):
        JournalEntry(
            kind=JournalKind.NOTE,
            recorded_at=AT(9),
            author="owner",
            audit=RecordAudit.frozen_at(AT(9)),
            title="x",
            supersedes="the earlier one",
        )


# --------------------------------------------------------------------------
# The last edges: coercions, projections and the remaining decode branches.
# --------------------------------------------------------------------------


def test_a_market_accepts_a_plain_venue_string_and_coerces_it() -> None:
    market = MarketId("binance", "BTC", "USDT", MarketMode.SPOT)
    assert market.venue == VenueId("binance")


def test_a_market_payload_must_be_an_object_with_the_right_keys() -> None:
    with pytest.raises(PayloadDecodeError, match="JSON object"):
        MarketId.from_payload("binance:BTCUSDT:spot")
    with pytest.raises(PayloadDecodeError, match="keys"):
        MarketId.from_payload({"venue": "binance"})


def test_the_owner_context_rejects_a_non_tuple_routine_and_a_bad_payload() -> None:
    with pytest.raises(TypeError, match="tuple"):
        owner_context(routine_times=["07:00"])
    from fmis.accounts import OwnerContext

    with pytest.raises(PayloadDecodeError, match="JSON object"):
        OwnerContext.from_payload("Europe/Stockholm")
    with pytest.raises(PayloadDecodeError, match="keys"):
        OwnerContext.from_payload({"display_timezone": "Europe/Stockholm"})
    payload = owner_context().to_payload()
    payload["routine_times"] = "07:00"
    with pytest.raises(PayloadDecodeError, match="array"):
        OwnerContext.from_payload(payload)


def test_the_owner_local_date_rejects_a_non_datetime() -> None:
    with pytest.raises(TypeError, match="must be a datetime"):
        owner_context().local_date("2026-08-12")


def test_a_third_asset_fee_rate_must_be_an_exact_decimal() -> None:
    with pytest.raises(TypeError, match="Decimal or Absent"):
        trade(
            fee=Money(Decimal("0.01"), AssetCode("BNB")),
            fee_fx_rate_to_tax_currency="3000",
        )


def test_a_trade_round_trips_with_every_optional_field_populated() -> None:
    subject = trade(
        occurrence_index=2,
        is_maker=True,
        reported_at=AT(11),
        order_id="order-77",
        plan_id="plan-7",
        proposal_id=proposal().proposal_id,
        venue_trade_id="9911223",
        note="typed from the exchange app",
    )
    assert Trade.from_payload(subject.to_payload()) == subject


def test_a_correction_reports_its_own_origin_digest_and_citation() -> None:
    subject = Correction(
        supersedes=trade().event_id,
        replacement=trade(price=Decimal("60001")),
        reason=reason_tag("typed_the_wrong_price", "correction_reason"),
        author="owner",
        occurred_at=AT(11),
        recorded_at=AT(11),
        audit=RecordAudit.frozen_at(AT(11)),
    )
    assert subject.origin is ValueOrigin.ASSERTED
    assert subject.content_digest.startswith("sha256:")
    assert subject.as_consumed_source().record_id == subject.event_id
    assert subject.as_consumed_source().kind == "correction"


def test_the_canonical_text_helper_rejects_a_non_decimal() -> None:
    from fmis.money import canonical_decimal_text

    with pytest.raises(TypeError, match="must be a Decimal"):
        canonical_decimal_text("0.1")


def test_the_float_crossing_rejects_a_non_finite_price() -> None:
    from fmis.money import exact_from_market_price

    with pytest.raises(DomainValidationError, match="not finite"):
        exact_from_market_price(float("inf"))


def test_an_amount_pair_requires_an_asset_of_a_known_kind() -> None:
    with pytest.raises(TypeError, match="must be an AssetCode"):
        Money(Decimal("1"), 7)  # type: ignore[arg-type]


def test_money_less_than_compares_within_one_asset() -> None:
    assert Money(Decimal("1"), USDT) < Money(Decimal("2"), USDT)


def test_quantity_addition_across_assets_raises() -> None:
    from fmis.money import AssetMismatchError

    with pytest.raises(AssetMismatchError):
        Quantity(Decimal("1"), BTC) + Quantity(Decimal("1"), AssetCode("ETH"))


def test_an_amount_payload_must_be_an_object() -> None:
    with pytest.raises(PayloadDecodeError, match="JSON object"):
        Money.from_payload("1 USDT")


def test_summing_money_adds_every_item() -> None:
    from fmis.money import sum_money

    assert sum_money([money("1"), money("2")], asset=USDT) == money("3")


def test_a_closed_position_reports_its_duration() -> None:
    from fmis.ledger import TradeSide, resolve

    positions = fold_positions(
        resolve(
            (
                trade(occurred_at=AT(10)),
                trade(
                    occurred_at=AT(12),
                    side=TradeSide.SELL,
                    quantity=Quantity(Decimal("0.5"), BTC),
                    price=Decimal("61000"),
                ),
            )
        ).resolved(),
        dust=dust_policy(),
    )
    assert positions[0].duration.total_seconds() == 7200


def test_unrealized_pnl_is_absent_when_nothing_has_been_acquired() -> None:
    from fmis.ledger import resolve
    from fmis.positions import PositionState

    (position,) = fold_positions(resolve((trade(),)).resolved(), dust=dust_policy())
    fields = {name: getattr(position, name) for name in Position.__dataclass_fields__}
    empty = Position(
        **{
            **fields,
            "average_entry": AverageCost(money("0"), quantity("0")),
        }
    )
    assert empty.state is PositionState.OPEN
    assert isinstance(empty.unrealized_pnl(Decimal("62000"), USDT), Absent)


def test_stated_confidence_renders_its_own_label() -> None:
    assert str(StatedConfidence("moderate")) == "moderate"


def test_a_directional_assessment_rejects_a_non_case() -> None:
    from fmis.proposal import DirectionalAssessment

    with pytest.raises(TypeError, match="DirectionalCase"):
        DirectionalAssessment(
            long_case=DirectionalCase(TradeDirection.LONG, ("x",), "y"),
            short_case="bearish",  # type: ignore[arg-type]
        )


def test_a_risk_limit_reports_its_origin() -> None:
    limit = RiskLimit(
        "leverage",
        LimitScope.LEVERAGE,
        Decimal("2"),
        LimitUnit.RATIO,
        LimitPeriod.NONE,
        LimitSeverity.ADVISORY,
    )
    assert limit.origin is ValueOrigin.ASSERTED
    assert not limit.is_ceiling


def test_a_money_limit_evaluation_reports_headroom_in_money() -> None:
    evaluation = LimitEvaluation(
        "daily_loss", money("500"), money("200"), LimitStatus.WITHIN
    )
    assert evaluation.headroom == money("300")


def test_a_money_limit_and_a_money_measurement_must_share_a_currency() -> None:
    with pytest.raises(DomainValidationError, match="one currency"):
        LimitEvaluation(
            "daily_loss",
            money("500"),
            Money(Decimal("200"), AssetCode("SEK")),
            LimitStatus.WITHIN,
        )


def test_an_unknown_risk_enum_member_on_decode_is_a_clean_rejection() -> None:
    limit = RiskLimit(
        "leverage",
        LimitScope.LEVERAGE,
        Decimal("2"),
        LimitUnit.RATIO,
        LimitPeriod.NONE,
        LimitSeverity.ADVISORY,
    )
    payload = limit.to_payload()
    payload["scope"] = "vibes"
    with pytest.raises(PayloadDecodeError, match="LimitScope"):
        RiskLimit.from_payload(payload)


def test_the_independence_disclosure_type_checks_its_pairs() -> None:
    with pytest.raises(TypeError, match="tuple of"):
        IndependenceDisclosure(
            pair_kappas=[("a", Decimal("1"))],  # type: ignore[arg-type]
            family_participation=(),
            sample_size=1,
            note="x",
            superseded_by=Absent("none"),
        )
    with pytest.raises(TypeError, match="pair"):
        IndependenceDisclosure(
            pair_kappas=(("a",),),  # type: ignore[arg-type]
            family_participation=(),
            sample_size=1,
            note="x",
            superseded_by=Absent("none"),
        )
    with pytest.raises(TypeError, match="must be a Decimal"):
        IndependenceDisclosure(
            pair_kappas=(("a", "1"),),  # type: ignore[arg-type]
            family_participation=(),
            sample_size=1,
            note="x",
            superseded_by=Absent("none"),
        )


def test_the_independence_disclosure_carries_a_superseding_study_by_name() -> None:
    disclosure = IndependenceDisclosure(
        pair_kappas=(),
        family_participation=(),
        sample_size=380,
        note="corrected harness",
        superseded_by="BC research harness",
    )
    assert IndependenceDisclosure.from_payload(disclosure.to_payload()) == disclosure


def test_a_reading_array_helper_rejects_a_wrong_item_type() -> None:
    payload = market_snapshot().to_payload()
    payload["conflicts"] = ["a conflict"]
    with pytest.raises(PayloadDecodeError):
        MarketSnapshot.from_payload(payload)


def test_a_snapshot_reports_a_missing_role_as_none() -> None:
    snapshot = market_snapshot(roles=(role_reading(SnapshotRole.CONTEXT, "1d"),))
    assert snapshot.role(SnapshotRole.EXECUTION) is None
    with pytest.raises(TypeError):
        snapshot.role("context")  # type: ignore[arg-type]


def test_a_window_bar_payload_must_be_an_object_with_the_right_keys() -> None:
    with pytest.raises(PayloadDecodeError, match="JSON object"):
        WindowBar.from_payload("a candle")
    with pytest.raises(PayloadDecodeError, match="keys"):
        WindowBar.from_payload({"close_time": "x"})


def test_a_capture_window_bounds_must_agree_with_its_rows() -> None:
    bars = decision_window().bars
    with pytest.raises(DomainValidationError, match="first captured row"):
        decision_window(bars=bars, first_close_time=bars[1].close_time)
    with pytest.raises(DomainValidationError, match="last captured row"):
        decision_window(
            bars=bars,
            last_close_time=bars[-2].close_time,
            first_close_time=bars[0].close_time,
        )


def test_an_analysis_record_subject_entry_must_be_non_empty() -> None:
    with pytest.raises(DomainValidationError, match="non-empty"):
        AnalysisRecord(
            record_id="workspace-BTCUSDT-20260812T090000Z-0123456789abcdef",
            record_type="workspace",
            payload_schema_version=1,
            analysis_as_of=AT(9),
            subject=("BTCUSDT", "  "),
            content_digest="sha256:" + "c" * 64,
            archived_at=AT(9),
            audit=RecordAudit.frozen_at(AT(9)),
        )


def test_the_resolved_type_still_checks_its_payload_behind_the_token() -> None:
    """The token stops a consumer constructing one; the type check stops the
    resolver itself from handing back something that is not a trade."""
    from fmis.ledger.resolver import _RESOLVER_TOKEN, ResolvedTrade

    with pytest.raises(TypeError, match="must be a Trade"):
        ResolvedTrade(token=_RESOLVER_TOKEN, trade="a trade", chain=("x",))


def test_quantity_addition_within_one_asset_runs_in_the_pinned_context() -> None:
    assert Quantity(Decimal("0.5"), BTC) + Quantity(Decimal("0.25"), BTC) == Quantity(
        Decimal("0.75"), BTC
    )


def test_the_portfolio_components_coerce_a_plain_asset_string() -> None:
    mark = MarkQuote(Decimal("60000"), "USDT", "binance", AT(8))
    assert mark.quote_asset == USDT
    holding = Holding("BTC", ACCOUNT, quantity("1"), Absent("no mark"))
    assert holding.asset == BTC
    assert isinstance(holding.value, Absent)


def test_a_portfolio_snapshot_coerces_a_plain_base_currency_and_reports_its_origin() -> None:
    from test_trade_domain_capital import _snapshot

    snapshot = _snapshot(base_currency="USDT")
    assert snapshot.base_currency == USDT
    assert snapshot.origin is ValueOrigin.MEASURED


def test_a_total_stops_at_the_first_cash_balance_it_cannot_value() -> None:
    from test_trade_domain_capital import _snapshot

    snapshot = _snapshot(
        holdings=(),
        cash=(
            CashBalance(ACCOUNT, money("100"), Absent("base currency")),
            CashBalance(
                ACCOUNT,
                Money(Decimal("100"), AssetCode("SEK")),
                Absent("no rate was frozen"),
            ),
        ),
    )
    assert isinstance(snapshot.total_value(), Absent)


def test_admission_skips_a_live_proposal_with_no_anchor() -> None:
    from fmis.proposal import AdmissionOutcome, admit

    no_trade = proposal(
        direction=TradeDirection.NO_TRADE,
        anchor=Absent("no invalidation level to anchor on"),
        invalidation=Absent("no level"),
        stop=Absent("no level"),
        risk_reward=Absent("no stop"),
        take_profit_structure=(),
    )
    admission = admit(
        proposal(created_at=AT(11)),
        ((no_trade, fold_proposal_state(no_trade, ())),),
        occurred_at=AT(11),
        recorded_at=AT(11),
        causing_close_time=AT(11),
    )
    assert admission.outcome is AdmissionOutcome.CREATED


def test_an_audit_payload_missing_a_field_names_it() -> None:
    with pytest.raises(PayloadDecodeError, match="missing"):
        RecordAudit.from_payload({"created_at": "2026-08-12T12:00:00+00:00"})


def test_a_reading_array_helper_rejects_a_non_array_and_a_wrong_item() -> None:
    payload = sufficiency().to_payload()
    payload["checks"] = "two of them"
    with pytest.raises(PayloadDecodeError, match="array"):
        SufficiencyReading.from_payload(payload)
    payload = sufficiency().to_payload()
    payload["checks"] = ["a check"]
    with pytest.raises(PayloadDecodeError, match="must be a dict"):
        SufficiencyReading.from_payload(payload)


def test_an_analysis_record_rejects_an_unwritable_schema_version() -> None:
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        AnalysisRecord(
            record_id="workspace-BTCUSDT-20260812T090000Z-0123456789abcdef",
            record_type="workspace",
            payload_schema_version=1,
            analysis_as_of=AT(9),
            subject=("BTCUSDT",),
            content_digest="sha256:" + "c" * 64,
            archived_at=AT(9),
            audit=RecordAudit.frozen_at(AT(9)),
            schema_version=7,
        )


def test_a_consumed_source_payload_must_be_a_json_object() -> None:
    with pytest.raises(PayloadDecodeError, match="JSON object"):
        ConsumedSource.from_payload("trade-BTCUSDT-20260812T120000Z-0123456789abcdef")
