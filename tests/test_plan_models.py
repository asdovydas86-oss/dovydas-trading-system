"""`TradePlan` — the commitment, and everything it refuses to represent.

The entity §11.6 assigns *stop, target and intended size* to by name. These tests
are organised the way the record's failures matter: what it refuses at
construction, what its identity covers, and what survives a round trip.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from trade_domain_helpers import (
    AT,
    MARKET,
    OTHER_MARKET,
    reason_tag,
    trade_plan,
    version_set,
)

from fmis.accounts import Book
from fmis.plan import (
    SUPPORTED_TRADE_PLAN_VERSIONS,
    TRADE_PLAN_KIND,
    TRADE_PLAN_SCHEMA_VERSION,
    TRADE_PLAN_TYPE_SLUG,
    PlanError,
    TradePlan,
)
from fmis.proposal import StatedConfidence
from fmis.provenance import Absent, ValueOrigin
from fmis.records import (
    DomainValidationError,
    PayloadDecodeError,
    RecordAudit,
    TradeDomainError,
)
from fmis.snapshotting import TradeDirection


# --------------------------------------------------------------------------
# The happy path.
# --------------------------------------------------------------------------


def test_a_committed_plan_holds_the_stop_and_the_targets() -> None:
    plan = trade_plan()
    assert plan.initial_invalidation == Decimal("58400")
    assert plan.stop == plan.initial_invalidation
    assert plan.targets == (Decimal("64000"),)
    assert plan.first_target == Decimal("64000")
    assert plan.book is Book.SWING
    assert plan.market == MARKET


def test_a_plan_is_asserted_because_intent_can_be_wrong() -> None:
    assert trade_plan().origin is ValueOrigin.ASSERTED


def test_a_plan_with_no_target_reports_an_absence_rather_than_a_zero() -> None:
    absent = trade_plan(targets=()).first_target
    assert isinstance(absent, Absent)
    assert "no target" in absent.reason


def test_the_package_error_is_catchable_as_a_domain_error() -> None:
    assert issubclass(PlanError, TradeDomainError)


def test_the_constants_this_build_writes_are_pinned() -> None:
    assert TRADE_PLAN_SCHEMA_VERSION == 1
    assert SUPPORTED_TRADE_PLAN_VERSIONS == frozenset({1})
    assert TRADE_PLAN_TYPE_SLUG == "trade_plan"
    assert TRADE_PLAN_KIND == "trade_plan"


# --------------------------------------------------------------------------
# What it refuses.
# --------------------------------------------------------------------------


def test_a_plan_refuses_a_direction_that_is_not_a_side() -> None:
    with pytest.raises(DomainValidationError, match="commits to a side"):
        trade_plan(direction=TradeDirection.NO_TRADE)


@pytest.mark.parametrize("stop", [Decimal("0"), Decimal("-1")])
def test_a_plan_refuses_a_stop_that_is_not_a_price(stop: Decimal) -> None:
    with pytest.raises(DomainValidationError, match="must be positive"):
        trade_plan(initial_invalidation=stop)


def test_a_long_plan_refuses_a_target_below_its_stop() -> None:
    with pytest.raises(DomainValidationError, match="not above the stop"):
        trade_plan(targets=(Decimal("58000"),))


def test_a_short_plan_refuses_a_target_above_its_stop() -> None:
    with pytest.raises(DomainValidationError, match="not below the stop"):
        trade_plan(
            direction=TradeDirection.SHORT,
            initial_invalidation=Decimal("62000"),
            targets=(Decimal("63000"),),
        )


def test_a_short_plan_accepts_targets_below_its_stop() -> None:
    plan = trade_plan(
        direction=TradeDirection.SHORT,
        initial_invalidation=Decimal("62000"),
        targets=(Decimal("58000"), Decimal("55000")),
    )
    assert plan.first_target == Decimal("58000")


def test_a_target_ladder_that_steps_backwards_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="stated nearest first"):
        trade_plan(targets=(Decimal("68000"), Decimal("64000")))


def test_a_short_target_ladder_that_steps_backwards_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="stated nearest first"):
        trade_plan(
            direction=TradeDirection.SHORT,
            initial_invalidation=Decimal("62000"),
            targets=(Decimal("55000"), Decimal("58000")),
        )


def test_the_same_target_twice_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="stated nearest first"):
        trade_plan(targets=(Decimal("64000"), Decimal("64000")))


def test_a_commitment_dated_before_its_own_creation_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="precedes created_at"):
        trade_plan(created_at=AT(11), committed_at=AT(10))


def test_an_expiry_at_or_before_the_commitment_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="is not after"):
        trade_plan(expires_at=AT(10))


def test_an_audit_block_that_does_not_match_creation_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="audit.created_at must equal"):
        trade_plan(audit=RecordAudit.frozen_at(AT(11)))


def test_a_plan_that_claims_to_have_changed_is_refused() -> None:
    """A captured artifact is frozen at a named moment; a change is a new record."""
    with pytest.raises(DomainValidationError, match="frozen at creation"):
        trade_plan(audit=RecordAudit(created_at=AT(10), updated_at=AT(11)))


def test_a_numeric_confidence_label_is_refused_by_the_type_it_reuses() -> None:
    with pytest.raises(DomainValidationError, match="looks like a number"):
        trade_plan(stated_confidence=StatedConfidence("0.7"))


def test_a_malformed_proposal_id_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="expected shape"):
        trade_plan(proposal_id="not-an-id")


def test_a_setup_type_must_be_a_versioned_term() -> None:
    with pytest.raises(TypeError, match="VersionedTerm"):
        trade_plan(setup_type="trend_continuation")


def test_an_unsupported_schema_version_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        trade_plan(schema_version=2)


def test_a_plan_refuses_attribute_assignment() -> None:
    plan = trade_plan()
    with pytest.raises((AttributeError, TypeError)):
        plan.initial_invalidation = Decimal("1")  # type: ignore[misc]


def test_there_is_no_code_path_that_changes_the_initial_invalidation() -> None:
    """§10.3 rule 8, asserted rather than trusted: *by construction, not by rule*.

    Every callable this record exposes either decodes one, describes one or
    serializes one. None of them returns a modified plan, and the list is pinned
    so that adding a `with_stop` would fail here rather than three milestones
    after somebody found it convenient.
    """
    methods = sorted(
        name
        for name in dir(TradePlan)
        if not name.startswith("_") and callable(getattr(TradePlan, name, None))
    )
    assert methods == [
        "as_consumed_source",
        "from_payload",
        "is_expired_at",
        "to_payload",
    ]


# --------------------------------------------------------------------------
# Expiry is a comparison, never a stored flag.
# --------------------------------------------------------------------------


def test_a_plan_with_no_expiry_never_expires() -> None:
    plan = trade_plan()
    assert isinstance(plan.expires_at, Absent)
    assert plan.is_expired_at(AT(9, day=30)) is False


def test_expiry_is_a_comparison_against_a_supplied_instant() -> None:
    plan = trade_plan(expires_at=AT(9, day=15))
    assert plan.is_expired_at(AT(9, day=14)) is False
    assert plan.is_expired_at(AT(9, day=15)) is True
    assert plan.is_expired_at(AT(9, day=16)) is True


def test_no_field_records_whether_the_plan_has_expired() -> None:
    assert "expired" not in TradePlan.__dataclass_fields__


# --------------------------------------------------------------------------
# Identity.
# --------------------------------------------------------------------------


def test_two_identical_commitments_share_one_id() -> None:
    assert trade_plan().plan_id == trade_plan().plan_id


def test_the_id_names_its_type_its_market_and_the_commitment_instant() -> None:
    plan_id = trade_plan().plan_id
    assert plan_id.startswith("trade_plan-binance_BTCUSDT_spot-20260812T100000Z-")


@pytest.mark.parametrize(
    "changed",
    [
        {"initial_invalidation": Decimal("58500")},
        {"targets": (Decimal("65000"),)},
        {"direction": TradeDirection.SHORT, "initial_invalidation": Decimal("62000"), "targets": ()},
        {"book": Book.INVESTING},
        {"market": OTHER_MARKET},
        {"stated_confidence": StatedConfidence("high")},
        {"setup_type": reason_tag("range_break", "setup_type")},
        {"note": "sized down"},
        {"expires_at": AT(9, day=20)},
        {"analysis_record_ids": ("workspace-BTCUSDT-20260812T090000Z-0123456789abcdef",)},
        {"version_set": version_set(code_version="deadbeef")},
    ],
)
def test_changing_any_committed_value_changes_the_id(changed: dict) -> None:
    assert trade_plan(**changed).plan_id != trade_plan().plan_id


def test_when_the_owner_started_typing_is_not_part_of_the_identity() -> None:
    """`created_at` is excluded, so a crash and a retype are one commitment.

    The same precedent ADR-0027 §3 set for `archived_at` and the ledger set for
    `recorded_at`.
    """
    early = trade_plan(created_at=AT(9), committed_at=AT(10))
    late = trade_plan(created_at=AT(10), committed_at=AT(10))
    assert early.plan_id == late.plan_id
    assert early.content_digest == late.content_digest
    assert early != late


def test_a_plan_names_itself_as_a_consumed_source_by_id_and_digest() -> None:
    plan = trade_plan()
    source = plan.as_consumed_source()
    assert source.record_id == plan.plan_id
    assert source.content_digest == plan.content_digest
    assert source.kind == TRADE_PLAN_KIND


def test_two_identical_plans_are_equal_and_hash_alike() -> None:
    assert trade_plan() == trade_plan()
    assert len({trade_plan(), trade_plan()}) == 1


# --------------------------------------------------------------------------
# Serialization.
# --------------------------------------------------------------------------


def test_a_plan_round_trips_to_an_equal_value() -> None:
    plan = trade_plan(
        setup_type=reason_tag("trend_continuation", "setup_type"),
        note="scaled in once",
        expires_at=AT(9, day=20),
        analysis_record_ids=("workspace-BTCUSDT-20260812T090000Z-0123456789abcdef",),
        targets=(Decimal("64000"), Decimal("68000")),
    )
    payload = plan.to_payload()
    assert TradePlan.from_payload(payload) == plan
    assert TradePlan.from_payload(payload).to_payload() == payload


def test_a_payload_whose_id_does_not_match_its_content_is_refused() -> None:
    payload = trade_plan().to_payload()
    payload["plan_id"] = "trade_plan-x-20260812T100000Z-0123456789abcdef"
    with pytest.raises(PayloadDecodeError, match="does not match the digest"):
        TradePlan.from_payload(payload)


def test_a_payload_missing_a_field_is_refused() -> None:
    payload = trade_plan().to_payload()
    del payload["targets"]
    with pytest.raises(PayloadDecodeError, match="missing field"):
        TradePlan.from_payload(payload)


def test_a_payload_carrying_an_unknown_field_is_refused() -> None:
    payload = trade_plan().to_payload()
    payload["intended_risk"] = "100"
    with pytest.raises(PayloadDecodeError, match="unknown field"):
        TradePlan.from_payload(payload)


def test_a_payload_naming_an_unknown_direction_is_refused() -> None:
    payload = trade_plan().to_payload()
    payload["direction"] = "sideways"
    with pytest.raises(PayloadDecodeError, match="not a known TradeDirection"):
        TradePlan.from_payload(payload)


def test_a_payload_naming_an_unknown_book_is_refused() -> None:
    payload = trade_plan().to_payload()
    payload["book"] = "scalping"
    with pytest.raises(PayloadDecodeError, match="not a known Book"):
        TradePlan.from_payload(payload)


def test_a_payload_whose_targets_are_not_an_array_is_refused() -> None:
    payload = trade_plan().to_payload()
    payload["targets"] = "64000"
    with pytest.raises(PayloadDecodeError, match="must be a JSON array"):
        TradePlan.from_payload(payload)


def test_a_payload_whose_analysis_records_are_not_an_array_is_refused() -> None:
    payload = trade_plan().to_payload()
    payload["analysis_record_ids"] = "workspace-x"
    with pytest.raises(PayloadDecodeError, match="must be a JSON array"):
        TradePlan.from_payload(payload)


def test_a_payload_from_an_unreadable_version_is_refused() -> None:
    payload = trade_plan().to_payload()
    payload["schema_version"] = 99
    with pytest.raises(PayloadDecodeError, match="not supported"):
        TradePlan.from_payload(payload)


def test_a_price_serialized_as_a_json_number_is_refused() -> None:
    """A float in the payload means the writer had already lost the exact value."""
    payload = trade_plan().to_payload()
    payload["initial_invalidation"] = 58400.0
    with pytest.raises(PayloadDecodeError, match="decimal \\*string\\*"):
        TradePlan.from_payload(payload)


def test_two_spellings_of_one_stop_produce_one_record() -> None:
    """`Decimal('58400.0')` and `Decimal('58400')` are one commitment, not two."""
    assert (
        trade_plan(initial_invalidation=Decimal("58400.0")).plan_id
        == trade_plan(initial_invalidation=Decimal("58400")).plan_id
    )


def test_a_target_is_canonicalized_the_same_way() -> None:
    assert (
        trade_plan(targets=(Decimal("64000.00"),)).plan_id
        == trade_plan(targets=(Decimal("64000"),)).plan_id
    )


def test_analysis_record_ids_are_sorted_and_deduplicated() -> None:
    """So two plans that read the same pages in a different order share an id."""
    first = "workspace-BTCUSDT-20260812T090000Z-0123456789abcdef"
    second = "daily-BTCUSDT-20260812T090000Z-0123456789abcdef"
    left = trade_plan(analysis_record_ids=(first, second, first))
    right = trade_plan(analysis_record_ids=(second, first))
    assert left.analysis_record_ids == (second, first)
    assert left.plan_id == right.plan_id


def test_a_plan_that_expires_far_out_is_still_a_plan() -> None:
    plan = trade_plan(expires_at=AT(10) + timedelta(days=90))
    assert plan.is_expired_at(AT(10) + timedelta(days=89)) is False


# --------------------------------------------------------------------------
# Type guards. Defensive, and exercised so they cannot rot into always-true.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("market", "binance:BTCUSDT:spot", "must be a MarketId"),
        ("stated_confidence", "moderate", "must be a StatedConfidence"),
        ("version_set", {"code_version": "x"}, "must be a VersionSet"),
    ],
)
def test_a_plan_refuses_a_field_of_the_wrong_type(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(TypeError, match=message):
        trade_plan(**{field: value})


@pytest.mark.parametrize("field", ["initial_invalidation", "targets"])
def test_a_price_supplied_as_a_float_is_refused(field: str) -> None:
    """One float in a price path is a fifty-five-digit digest away from a bug."""
    value = 58400.0 if field == "initial_invalidation" else (64000.0,)
    with pytest.raises(TypeError, match="must be a Decimal"):
        trade_plan(**{field: value})
