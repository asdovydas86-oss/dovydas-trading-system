"""Milestone BO — the activation, and every rule it refuses to bend.

The theme is that an instruction the simulator will run cannot be assembled in a
state where it means two things. A ladder that walks backwards, a target the
entry has already passed, a size in the wrong asset, a market entry carrying a
level nothing reads, a book that is not `PAPER` — each is a refusal naming the
two values that disagree, not a record that renders oddly later.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from fmis.accounts import AccountId, Book
from fmis.money import AssetCode, Quantity
from fmis.provenance import Absent, ValueOrigin
from fmis.records import DomainValidationError, PayloadDecodeError, RecordAudit
from fmis.snapshotting import TradeDirection
from fmis.trade_lifecycle import (
    SUPPORTED_TRADE_ACTIVATION_VERSIONS,
    ActivationError,
    BreakEvenRule,
    EntryType,
    ExitLadder,
    ExitLeg,
    PaperCostPolicy,
    StopManagement,
    TradeActivation,
    TrailingRule,
)
from paper_helpers import START, activation, at, market_activation, plan, short_plan


# --------------------------------------------------------------------------
# The ladder
# --------------------------------------------------------------------------


def test_a_leg_takes_a_share_of_the_position_and_never_more_than_all_of_it() -> None:
    assert ExitLeg(target=Decimal("110"), fraction=Decimal("1")).fraction == 1
    for share in ("0", "-0.5", "1.0001"):
        with pytest.raises(ActivationError, match="0, 1"):
            ExitLeg(target=Decimal("110"), fraction=Decimal(share))


def test_a_ladder_may_take_less_than_the_whole_position() -> None:
    """*'Take half at the first target and let the rest run'* is the commonest
    swing exit there is, and a ladder forced to sum to one could not express it."""
    partial = ExitLadder(legs=(ExitLeg(target=Decimal("110"), fraction=Decimal("0.5")),))
    assert partial.total_fraction == Decimal("0.5")
    assert partial.runner_fraction == Decimal("0.5")


def test_a_ladder_may_not_take_more_than_the_whole_position() -> None:
    with pytest.raises(ActivationError, match="more than there is"):
        ExitLadder(
            legs=(
                ExitLeg(target=Decimal("110"), fraction=Decimal("0.6")),
                ExitLeg(target=Decimal("120"), fraction=Decimal("0.6")),
            )
        )


def test_two_rungs_at_one_price_are_refused() -> None:
    with pytest.raises(ActivationError, match="same target price"):
        ExitLadder(
            legs=(
                ExitLeg(target=Decimal("110"), fraction=Decimal("0.3")),
                ExitLeg(target=Decimal("110"), fraction=Decimal("0.3")),
            )
        )


def test_an_empty_ladder_is_legal_and_means_the_stop() -> None:
    empty = ExitLadder()
    assert empty.is_empty
    assert empty.runner_fraction == 1


# --------------------------------------------------------------------------
# The stop rules
# --------------------------------------------------------------------------


def test_a_break_even_trigger_must_be_positive_and_the_offset_may_be_zero() -> None:
    assert BreakEvenRule(trigger_r=Decimal("1")).offset_r == 0
    with pytest.raises(ActivationError, match="positive"):
        BreakEvenRule(trigger_r=Decimal("0"))
    with pytest.raises(ActivationError, match="non-negative"):
        BreakEvenRule(trigger_r=Decimal("1"), offset_r=Decimal("-1"))


def test_a_trail_that_states_no_start_says_so_rather_than_defaulting_to_zero() -> None:
    """A trail that starts immediately is a *choice*, and a zero default would
    make it look like the absence of one."""
    rule = TrailingRule(distance_r=Decimal("1"))
    assert isinstance(rule.activate_at_r, Absent)
    assert "first bar" in rule.activate_at_r.reason


def test_stop_management_knows_when_every_move_will_be_the_owners_own() -> None:
    assert StopManagement().is_manual
    assert not StopManagement(break_even=BreakEvenRule(trigger_r=Decimal("1"))).is_manual


# --------------------------------------------------------------------------
# The cost policy
# --------------------------------------------------------------------------


def test_a_zero_cost_policy_is_frictionless_and_says_so_in_words() -> None:
    policy = PaperCostPolicy(
        policy_id="p", version=1, fee_rate=Decimal(0), slippage_rate=Decimal(0)
    )
    assert policy.is_frictionless
    assert "not a trade" in policy.basis


def test_a_negative_rate_is_refused_because_a_rebate_is_a_different_event() -> None:
    with pytest.raises(ActivationError, match="rebate"):
        PaperCostPolicy(
            policy_id="p", version=1, fee_rate=Decimal("-1"), slippage_rate=Decimal(0)
        )


# --------------------------------------------------------------------------
# The activation
# --------------------------------------------------------------------------


def test_an_activation_round_trips_through_its_payload_exactly() -> None:
    original = activation()
    assert TradeActivation.from_payload(original.to_payload()) == original


def test_an_activation_id_is_a_digest_of_the_instruction_and_nothing_else() -> None:
    """Two identical instructions are one, which is what makes re-running the
    command an idempotent success rather than a second activation."""
    assert activation().activation_id == activation().activation_id
    assert activation().activation_id != activation(
        quantity=Quantity(Decimal("2"), AssetCode("BTC"))
    ).activation_id


def test_a_payload_whose_id_does_not_match_its_content_is_refused() -> None:
    payload = activation().to_payload()
    payload["activation_id"] = "trade_activation-x-20260801T000000Z-" + "0" * 16
    with pytest.raises(PayloadDecodeError, match="does not match the digest"):
        TradeActivation.from_payload(payload)


def test_an_unknown_entry_type_is_a_clean_rejection() -> None:
    payload = activation().to_payload()
    payload["entry_type"] = "iceberg"
    with pytest.raises(PayloadDecodeError, match="clean rejection"):
        TradeActivation.from_payload(payload)


def test_this_build_activates_the_paper_book_only() -> None:
    with pytest.raises(ActivationError, match="paper"):
        activation(book=Book.SWING)


def test_an_activation_commits_to_a_side() -> None:
    with pytest.raises(ActivationError, match="commits to a side"):
        activation(direction=TradeDirection.NO_TRADE)


def test_a_size_in_the_wrong_asset_is_refused() -> None:
    with pytest.raises(ActivationError, match="base asset"):
        activation(quantity=Quantity(Decimal("1"), AssetCode("USDT")))


def test_a_non_positive_size_is_refused() -> None:
    with pytest.raises(ActivationError, match="positive"):
        activation(quantity=Quantity(Decimal("0"), AssetCode("BTC")))


def test_a_level_is_required_exactly_when_the_entry_type_is_about_one() -> None:
    with pytest.raises(ActivationError, match="defined by the price it waits for"):
        activation(entry_price=Absent("none"))
    with pytest.raises(ActivationError, match="waits for no level"):
        market_activation(entry_price=Decimal("100"))


def test_a_ladder_that_walks_backwards_is_refused() -> None:
    with pytest.raises(ActivationError, match="does not lie beyond"):
        activation(
            ladder=ExitLadder(
                legs=(
                    ExitLeg(target=Decimal("120"), fraction=Decimal("0.5")),
                    ExitLeg(target=Decimal("110"), fraction=Decimal("0.5")),
                )
            )
        )


def test_a_target_the_entry_has_already_passed_is_not_a_target() -> None:
    with pytest.raises(ActivationError, match="not beyond the entry"):
        activation(
            ladder=ExitLadder(
                legs=(ExitLeg(target=Decimal("90"), fraction=Decimal("1")),)
            )
        )


def test_the_ladder_geometry_is_mirrored_for_the_other_side() -> None:
    """A short's rungs step *down*, and the same two lines decide both."""
    committed = short_plan()
    mirrored = activation(committed, entry_price=Decimal("100"))
    assert [leg.target for leg in mirrored.ladder.legs] == [
        Decimal("90"),
        Decimal("80"),
    ]
    with pytest.raises(ActivationError, match="not beyond the entry"):
        activation(
            committed,
            entry_price=Decimal("100"),
            ladder=ExitLadder(
                legs=(ExitLeg(target=Decimal("110"), fraction=Decimal("1")),)
            ),
        )


def test_an_expiry_must_follow_the_activation() -> None:
    with pytest.raises(ActivationError, match="already lapsed"):
        activation(expires_at=START)


def test_expiry_is_a_comparison_and_never_a_stored_flag() -> None:
    subject = activation(expires_at=at(4))
    assert subject.has_expiry
    assert not subject.is_expired_at(at(3))
    assert subject.is_expired_at(at(4))
    assert not activation().is_expired_at(at(1000))


def test_a_leg_takes_a_share_of_the_activated_size_not_of_what_remains() -> None:
    """Fractions of a shrinking remainder would make the last rung's size depend
    on the order the earlier ones filled in."""
    subject = activation()
    assert subject.leg_quantity(0) == Quantity(Decimal("0.5"), AssetCode("BTC"))
    assert subject.leg_quantity(1) == Quantity(Decimal("0.5"), AssetCode("BTC"))
    with pytest.raises(ActivationError, match="no leg 3"):
        subject.leg_quantity(2)


def test_an_activation_is_asserted_because_intent_can_be_wrong() -> None:
    assert activation().origin is ValueOrigin.ASSERTED


def test_the_audit_block_must_agree_with_the_moment_of_activation() -> None:
    with pytest.raises(DomainValidationError, match="audit.created_at"):
        activation(audit=RecordAudit.frozen_at(at(1)))


def test_a_schema_version_this_build_does_not_write_is_refused() -> None:
    unknown = max(SUPPORTED_TRADE_ACTIVATION_VERSIONS) + 1
    with pytest.raises(DomainValidationError, match="not one this build writes"):
        activation(schema_version=unknown)


def test_a_proposal_id_of_the_wrong_shape_is_refused() -> None:
    with pytest.raises(DomainValidationError, match="expected shape"):
        activation(proposal_id="not-an-id")


def test_the_type_checks_name_the_field_rather_than_failing_later() -> None:
    for field, value in (
        ("market", "BTCUSDT"),
        ("account", "paper"),
        ("quantity", Decimal("1")),
        ("ladder", ()),
        ("stop_management", None),
        ("cost_policy", None),
        ("version_set", None),
    ):
        with pytest.raises(TypeError, match=field.split("_")[0]):
            activation(**{field: value})


def test_an_entry_type_knows_whether_it_needs_a_level() -> None:
    assert not EntryType.MARKET.needs_a_level
    assert EntryType.LIMIT.needs_a_level
    assert EntryType.STOP_ENTRY.needs_a_level


def test_a_plan_and_its_activation_agree_on_the_market_by_construction() -> None:
    committed = plan()
    assert activation(committed).market == committed.market
    assert activation(committed).plan_id == committed.plan_id


def test_an_activation_cites_itself_as_a_consumed_source() -> None:
    source = activation().as_consumed_source()
    assert source.record_id == activation().activation_id
    assert source.kind == "trade_activation"


def test_the_payload_key_set_is_exact_in_both_directions() -> None:
    payload = activation().to_payload()
    payload["unexpected"] = 1
    with pytest.raises(PayloadDecodeError, match="unknown field"):
        TradeActivation.from_payload(payload)
    del payload["unexpected"]
    del payload["interval"]
    with pytest.raises(PayloadDecodeError, match="missing field"):
        TradeActivation.from_payload(payload)


def test_the_stop_rules_round_trip_through_the_payload() -> None:
    subject = activation(
        stop_management=StopManagement(
            break_even=BreakEvenRule(trigger_r=Decimal("1"), offset_r=Decimal("0.1")),
            trailing=TrailingRule(
                distance_r=Decimal("1.5"), activate_at_r=Decimal("2")
            ),
        )
    )
    assert TradeActivation.from_payload(subject.to_payload()) == subject


def test_an_activated_instant_is_normalized_to_utc() -> None:
    from datetime import timezone

    offset = START.astimezone(timezone(timedelta(hours=2)))
    assert activation(activated_at=offset).activated_at == START
