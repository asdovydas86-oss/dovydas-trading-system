"""`MarketSnapshot`, `DecisionWindow` and the `AnalysisRecord` citation."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from trade_domain_helpers import (
    AT,
    MARKET,
    OTHER_MARKET,
    anchor,
    consumed,
    decision_window,
    level,
    level_origin,
    market_snapshot,
    role_reading,
    setup_reading,
    sufficiency,
    version_set,
)

from fmis.analysis_record import ANALYSIS_RECORD_KIND, AnalysisRecord
from fmis.provenance import Absent, ValueOrigin
from fmis.records import DomainValidationError, PayloadDecodeError, RecordAudit
from fmis.snapshotting import (
    FIELD_GROUP_ORIGINS,
    ROLE_ORDER,
    ConflictNote,
    DecisionWindow,
    EvidenceFamilyReading,
    FreshnessReading,
    IndependenceDisclosure,
    LevelReading,
    LevelSideRef,
    MarketSnapshot,
    RegimeDimensionReading,
    RegimeReading,
    RequirementReading,
    RiskRewardReading,
    SetupReading,
    SnapshotRole,
    SnapshotTrigger,
    StopTriggerSemantics,
    SufficiencyReading,
    TradeDirection,
    TriggerBasis,
    WindowBar,
    WindowMode,
    series_digest_of,
)

ARCHIVE_RECORD_ID = "workspace-BTCUSDT-20260812T090000Z-0123456789abcdef"


# --------------------------------------------------------------------------
# Readings.
# --------------------------------------------------------------------------


def test_no_trade_is_a_first_class_direction_and_not_an_absence() -> None:
    assert TradeDirection.NO_TRADE in set(TradeDirection)
    assert not TradeDirection.NO_TRADE.is_directional
    assert TradeDirection.NO_TRADE.opposite is TradeDirection.NO_TRADE
    assert TradeDirection.LONG.opposite is TradeDirection.SHORT
    assert TradeDirection.SHORT.opposite is TradeDirection.LONG


def test_risk_and_reward_are_a_pair_and_the_ratio_is_computed_at_read_time() -> None:
    reading = RiskRewardReading(Decimal("100"), Decimal("250"))
    assert reading.ratio == Decimal("2.5")
    assert reading.arithmetic == "250 ÷ 100"
    assert "ratio" not in reading.to_payload()
    assert RiskRewardReading.from_payload(reading.to_payload()) == reading


def test_a_zero_risk_distance_is_rejected_because_it_means_there_is_no_stop() -> None:
    with pytest.raises(DomainValidationError, match="no stop"):
        RiskRewardReading(Decimal("0"), Decimal("100"))


def test_a_level_price_must_be_positive_and_carry_a_measured_origin() -> None:
    with pytest.raises(DomainValidationError, match="positive"):
        level("0")
    with pytest.raises(TypeError, match="LevelOriginRef"):
        LevelReading(Decimal("1"), LevelSideRef.BELOW, "swing-114", "x")  # type: ignore[arg-type]


def test_a_level_round_trips() -> None:
    reading = level("58400.50")
    assert LevelReading.from_payload(reading.to_payload()) == reading


def test_the_wick_case_becomes_derivable_only_when_the_two_bases_differ() -> None:
    split = StopTriggerSemantics(TriggerBasis.TOUCH, TriggerBasis.CLOSE)
    merged = StopTriggerSemantics(TriggerBasis.CLOSE, TriggerBasis.CLOSE)
    assert split.separates_wick_from_thesis
    assert not merged.separates_wick_from_thesis


def test_the_three_bar_ages_are_carried_and_the_context_role_is_the_gate() -> None:
    freshness = FreshnessReading(AT(9), 8, 2, 0)
    assert freshness.gating_age == 8
    assert FreshnessReading.from_payload(freshness.to_payload()) == freshness


def test_an_absent_bar_age_survives_a_round_trip_with_its_reason() -> None:
    freshness = FreshnessReading(AT(9), Absent("context role not fetched"), 2, 0)
    restored = FreshnessReading.from_payload(freshness.to_payload())
    assert restored == freshness
    assert isinstance(restored.context_bars, Absent)


def test_a_regime_dimension_distinguishes_absent_evidence_from_a_state() -> None:
    dimension = RegimeDimensionReading(
        "volatility", Absent("ATR warming up"), (), ("atr_14",)
    )
    assert isinstance(dimension.state, Absent)
    assert dimension.unavailable == ("atr_14",)
    assert RegimeDimensionReading.from_payload(dimension.to_payload()) == dimension


def test_one_regime_dimension_cannot_be_reported_twice() -> None:
    with pytest.raises(DomainValidationError, match="must not be reported twice"):
        RegimeReading(
            (
                RegimeDimensionReading("structure", "up"),
                RegimeDimensionReading("structure", "down"),
            )
        )


def test_a_regime_reading_finds_a_named_dimension_and_returns_none_otherwise() -> None:
    reading = RegimeReading((RegimeDimensionReading("structure", "up"),))
    assert reading.dimension("structure").state == "up"
    assert reading.dimension("participation") is None


def test_a_sufficiency_reading_carries_every_check_including_the_met_ones() -> None:
    reading = sufficiency()
    assert len(reading.checks) == 2
    assert reading.unmet == ()
    assert SufficiencyReading.from_payload(reading.to_payload()) == reading


def test_a_requirement_cannot_be_checked_twice() -> None:
    check = RequirementReading("depth", True, "blocking", "ok", "layer")
    with pytest.raises(DomainValidationError, match="checked twice"):
        SufficiencyReading("sufficient", (check, check))


def test_a_conflict_is_reported_and_carries_no_resolution_field() -> None:
    note = ConflictNote("timeframe", "setup and execution disagree")
    fields = set(note.to_payload())
    assert fields == {"kind", "statement"}
    assert not fields & {"resolution", "winner", "severity_rank"}


def test_the_independence_disclosure_travels_with_its_sample_size() -> None:
    disclosure = IndependenceDisclosure(
        pair_kappas=(("context/trend", Decimal("0.41")),),
        family_participation=(("context", Decimal("1")),),
        sample_size=578,
        note="AW sample",
        superseded_by=Absent("no later study"),
    )
    assert disclosure.sample_size == 578
    assert IndependenceDisclosure.from_payload(disclosure.to_payload()) == disclosure


def test_the_independence_disclosure_rejects_a_repeated_label() -> None:
    with pytest.raises(DomainValidationError, match="twice"):
        IndependenceDisclosure(
            pair_kappas=(("a", Decimal("1")), ("a", Decimal("2"))),
            family_participation=(),
            sample_size=1,
            note="x",
            superseded_by=Absent("none"),
        )


def test_a_setup_reading_with_no_stop_cannot_claim_a_risk_reward() -> None:
    with pytest.raises(DomainValidationError, match="no risk denominator"):
        setup_reading(stop=Absent("no level detected"))


def test_a_no_trade_reading_carries_no_anchor() -> None:
    with pytest.raises(DomainValidationError, match="NO_TRADE reading"):
        setup_reading(direction=TradeDirection.NO_TRADE)


def test_an_anchor_disagreeing_with_the_reading_direction_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="disagrees"):
        setup_reading(anchor=anchor(direction=TradeDirection.SHORT))


def test_an_anchor_requires_a_direction_to_anchor_on() -> None:
    with pytest.raises(DomainValidationError, match="anchor requires a direction"):
        anchor(direction=TradeDirection.NO_TRADE)


def test_an_anchor_renders_a_stable_key_and_round_trips() -> None:
    subject = anchor()
    assert MARKET.value in subject.key
    from fmis.snapshotting import Anchor

    assert Anchor.from_payload(subject.to_payload()) == subject


def test_a_setup_reading_round_trips_in_full() -> None:
    reading = setup_reading()
    assert SetupReading.from_payload(reading.to_payload()) == reading


def test_a_role_reading_rejects_a_level_on_the_wrong_side_of_price() -> None:
    with pytest.raises(DomainValidationError, match="marked as being below"):
        role_reading(nearest_level_above=level("100", LevelSideRef.BELOW))
    with pytest.raises(DomainValidationError, match="marked as being above"):
        role_reading(nearest_level_below=level("100", LevelSideRef.ABOVE))


def test_a_role_reading_round_trips() -> None:
    reading = role_reading()
    from fmis.snapshotting import RoleReading

    assert RoleReading.from_payload(reading.to_payload()) == reading


# --------------------------------------------------------------------------
# MarketSnapshot.
# --------------------------------------------------------------------------


def test_a_snapshot_is_identified_by_its_content_and_round_trips() -> None:
    snapshot = market_snapshot()
    payload = snapshot.to_payload()
    assert MarketSnapshot.from_payload(payload) == snapshot
    assert payload["snapshot_id"] == snapshot.snapshot_id


def test_two_identical_snapshots_share_one_id() -> None:
    assert market_snapshot().snapshot_id == market_snapshot().snapshot_id


def test_changing_any_market_fact_changes_the_snapshot_id() -> None:
    baseline = market_snapshot()
    changed = market_snapshot(
        conflicts=(ConflictNote("timeframe", "a different conflict"),)
    )
    assert baseline.snapshot_id != changed.snapshot_id


def test_a_tampered_snapshot_id_is_rejected_on_decode() -> None:
    payload = market_snapshot().to_payload()
    payload["snapshot_id"] = "market_snapshot-x-20260812T090000Z-0123456789abcdef"
    with pytest.raises(PayloadDecodeError, match="does not match the digest"):
        MarketSnapshot.from_payload(payload)


def test_a_snapshot_is_frozen_and_its_audit_says_so() -> None:
    snapshot = market_snapshot()
    assert snapshot.audit.is_unmodified
    with pytest.raises(DomainValidationError, match="frozen at creation"):
        market_snapshot(audit=RecordAudit.frozen_at(AT(9)).appended_at(AT(10)))


def test_a_snapshot_audit_must_agree_with_the_moment_it_froze() -> None:
    with pytest.raises(DomainValidationError, match="must equal built_at"):
        market_snapshot(audit=RecordAudit.frozen_at(AT(8)))


def test_a_snapshot_cannot_contain_a_reading_from_its_own_future() -> None:
    with pytest.raises(DomainValidationError, match="from its own future"):
        market_snapshot(setup=setup_reading(as_of=AT(10)))
    with pytest.raises(DomainValidationError, match="after the snapshot was built"):
        market_snapshot(roles=(role_reading(as_of=AT(10)),))


def test_roles_are_reported_once_and_in_order() -> None:
    with pytest.raises(DomainValidationError, match="must not be read twice"):
        market_snapshot(roles=(role_reading(), role_reading()))
    with pytest.raises(DomainValidationError, match="ROLE_ORDER"):
        market_snapshot(
            roles=(
                role_reading(SnapshotRole.EXECUTION, "1h"),
                role_reading(SnapshotRole.CONTEXT, "1d"),
            )
        )


def test_role_order_runs_from_the_gate_outward() -> None:
    assert ROLE_ORDER == (
        SnapshotRole.CONTEXT,
        SnapshotRole.SETUP,
        SnapshotRole.EXECUTION,
    )


def test_a_snapshot_anchor_must_name_the_market_the_snapshot_is_about() -> None:
    with pytest.raises(DomainValidationError, match="while the snapshot is about"):
        market_snapshot(setup=setup_reading(anchor=anchor(market=OTHER_MARKET)))


def test_an_evidence_family_cannot_be_reported_twice() -> None:
    entry = EvidenceFamilyReading("trend", "supports", Absent("no alignment"))
    with pytest.raises(DomainValidationError, match="reported twice"):
        market_snapshot(evidence=(entry, entry))


def test_a_snapshot_exposes_role_lookups_and_projections() -> None:
    snapshot = market_snapshot()
    assert snapshot.role(SnapshotRole.CONTEXT).interval == "1d"
    assert snapshot.has_directional_setup
    assert snapshot.unmet_requirements == ()
    assert snapshot.role(SnapshotRole.EXECUTION) is not None


def test_provenance_is_carried_per_field_group_and_not_per_record() -> None:
    groups = dict(FIELD_GROUP_ORIGINS)
    assert groups["roles"] is ValueOrigin.MEASURED
    assert groups["regime"] is ValueOrigin.POLICY_DERIVED
    assert groups["setup"] is ValueOrigin.POLICY_DERIVED


def test_staleness_is_derived_from_consumed_sources_and_never_rewrites_the_record() -> None:
    trade_id = "trade-BTCUSDT-20260812T100000Z-0123456789abcdef"
    snapshot = market_snapshot(consumed_sources=(consumed(trade_id, "a"),))
    unchanged = snapshot.stale_inputs({trade_id: "sha256:" + "a" * 64})
    corrected = snapshot.stale_inputs({trade_id: "sha256:" + "b" * 64})
    assert unchanged == ()
    assert len(corrected) == 1
    assert corrected[0].record_id == trade_id
    assert snapshot == market_snapshot(consumed_sources=(consumed(trade_id, "a"),))


def test_stale_inputs_requires_a_mapping() -> None:
    with pytest.raises(TypeError):
        market_snapshot().stale_inputs([("a", "b")])  # type: ignore[arg-type]


def test_a_snapshot_can_be_cited_as_a_consumed_source() -> None:
    snapshot = market_snapshot()
    source = snapshot.as_consumed_source()
    assert source.record_id == snapshot.snapshot_id
    assert source.content_digest == snapshot.content_digest
    assert source.kind == "market_snapshot"


def test_an_unknown_snapshot_trigger_is_a_clean_rejection() -> None:
    payload = market_snapshot().to_payload()
    payload["trigger"] = "vibes"
    with pytest.raises(PayloadDecodeError, match="SnapshotTrigger"):
        MarketSnapshot.from_payload(payload)


def test_a_snapshot_payload_missing_a_field_is_rejected() -> None:
    payload = market_snapshot().to_payload()
    del payload["conflicts"]
    with pytest.raises(PayloadDecodeError, match="missing"):
        MarketSnapshot.from_payload(payload)


def test_every_snapshot_trigger_is_representable() -> None:
    for trigger in SnapshotTrigger:
        snapshot = market_snapshot(trigger=trigger)
        assert MarketSnapshot.from_payload(snapshot.to_payload()) == snapshot


# --------------------------------------------------------------------------
# DecisionWindow.
# --------------------------------------------------------------------------


def test_a_captured_window_verifies_its_rows_against_its_digest() -> None:
    window = decision_window()
    assert window.is_verifiable_offline
    assert DecisionWindow.from_payload(window.to_payload()) == window


def test_a_reference_window_holds_no_rows() -> None:
    bars = decision_window().bars
    window = decision_window(
        WindowMode.REFERENCE, bars=bars, series_digest=series_digest_of(bars)
    )
    assert window.bars == ()
    assert not window.is_verifiable_offline


def test_a_reference_window_carrying_rows_is_rejected() -> None:
    bars = decision_window().bars
    with pytest.raises(DomainValidationError, match="reference-mode window holds no rows"):
        DecisionWindow(
            market=MARKET,
            interval="1d",
            first_close_time=bars[0].close_time,
            last_close_time=bars[-1].close_time,
            bar_count=len(bars),
            series_digest=series_digest_of(bars),
            mode=WindowMode.REFERENCE,
            version_set=version_set(),
            audit=RecordAudit.frozen_at(AT(9)),
            bars=bars,
        )


def test_pruning_keeps_the_identity_and_downgrades_the_content() -> None:
    window = decision_window()
    pruned = window.prune(AT(12))
    assert pruned.window_id == window.window_id
    assert pruned.bars == ()
    assert pruned.series_digest == window.series_digest
    assert not isinstance(pruned.pruned_at, Absent)
    assert not pruned.is_verifiable_offline


def test_pruning_an_already_pruned_window_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="already in reference mode"):
        decision_window().prune(AT(12)).prune(AT(13))


def test_a_bar_count_disagreeing_with_the_rows_is_rejected() -> None:
    bars = decision_window().bars
    with pytest.raises(DomainValidationError, match="disagrees with the"):
        decision_window(bars=bars, bar_count=99)


def test_a_series_digest_that_does_not_cover_the_rows_is_rejected() -> None:
    bars = decision_window().bars
    with pytest.raises(DomainValidationError, match="does not match the digest"):
        decision_window(bars=bars, series_digest="sha256:" + "0" * 64)


def test_a_candle_series_is_strictly_ordered_by_close() -> None:
    first = WindowBar(AT(0, day=1), Decimal("1"), Decimal("2"), Decimal("1"), Decimal("1"), Decimal("0"))
    bars = (first, first)
    with pytest.raises(DomainValidationError, match="strictly ordered"):
        decision_window(bars=bars, series_digest=series_digest_of(bars))


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"high": Decimal("0.5")}, "below low"),
        ({"high": Decimal("1.2")}, "do not contain"),
        ({"low": Decimal("1.4")}, "do not contain"),
        ({"volume": Decimal("-1")}, "cannot be negative"),
        ({"open": Decimal("0")}, "positive"),
    ],
)
def test_a_bar_that_is_not_a_candle_is_rejected(kwargs: dict, message: str) -> None:
    values = {
        "close_time": AT(0),
        "open": Decimal("1"),
        "high": Decimal("2"),
        "low": Decimal("1"),
        "close": Decimal("1.5"),
        "volume": Decimal("10"),
    }
    values.update(kwargs)
    with pytest.raises(DomainValidationError, match=message):
        WindowBar(**values)


def test_a_bar_round_trips() -> None:
    bar = decision_window().bars[0]
    assert WindowBar.from_payload(bar.to_payload()) == bar


def test_a_window_whose_bounds_are_reversed_is_rejected() -> None:
    bars = decision_window().bars
    with pytest.raises(DomainValidationError, match="precedes first_close_time"):
        decision_window(
            WindowMode.REFERENCE,
            bars=bars,
            series_digest=series_digest_of(bars),
            first_close_time=bars[-1].close_time,
            last_close_time=bars[0].close_time,
        )


def test_a_tampered_window_id_is_rejected_on_decode() -> None:
    payload = decision_window().to_payload()
    payload["window_id"] = "decision_window-x-20260805T000000Z-0123456789abcdef"
    with pytest.raises(PayloadDecodeError, match="does not match the digest"):
        DecisionWindow.from_payload(payload)


def test_a_series_digest_of_the_wrong_shape_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="sha256"):
        decision_window(WindowMode.REFERENCE, series_digest="not-a-digest")


# --------------------------------------------------------------------------
# AnalysisRecord — the citation, not the page.
# --------------------------------------------------------------------------


def _analysis_record(**overrides: object) -> AnalysisRecord:
    values = {
        "record_id": ARCHIVE_RECORD_ID,
        "record_type": "workspace",
        "payload_schema_version": 1,
        "analysis_as_of": AT(9),
        "subject": ("BTCUSDT", "swing"),
        "content_digest": "sha256:" + "c" * 64,
        "archived_at": AT(9) + timedelta(minutes=1),
        "audit": RecordAudit.frozen_at(AT(9)),
    }
    values.update(overrides)
    return AnalysisRecord(**values)  # type: ignore[arg-type]


def test_an_analysis_record_citation_round_trips() -> None:
    record = _analysis_record()
    assert AnalysisRecord.from_payload(record.to_payload()) == record
    assert record.subject_label == "BTCUSDT · swing"


def test_a_citation_supplies_the_law_eight_edge_at_no_extra_cost() -> None:
    record = _analysis_record()
    source = record.as_consumed_source()
    assert source.record_id == record.record_id
    assert source.content_digest == record.content_digest
    assert source.kind == ANALYSIS_RECORD_KIND


def test_a_citation_naming_the_wrong_kind_of_page_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="disagrees with the record id"):
        _analysis_record(record_type="daily_run")


def test_a_citation_of_a_daily_run_resolves_against_its_own_slug() -> None:
    record = _analysis_record(
        record_id="daily-BTCUSDT-20260812T090000Z-0123456789abcdef",
        record_type="daily_run",
    )
    assert record.record_type == "daily_run"


def test_a_citation_requires_a_full_content_digest() -> None:
    with pytest.raises(DomainValidationError, match="sha256"):
        _analysis_record(content_digest="sha256:short")


def test_a_citation_is_frozen() -> None:
    with pytest.raises(DomainValidationError, match="frozen at creation"):
        _analysis_record(audit=RecordAudit.frozen_at(AT(9)).appended_at(AT(10)))


def test_a_citation_payload_with_an_unknown_field_is_rejected() -> None:
    payload = _analysis_record().to_payload()
    payload["surprise"] = 1
    with pytest.raises(PayloadDecodeError, match="unknown"):
        AnalysisRecord.from_payload(payload)
