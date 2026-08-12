"""The record spine, provenance, money, versioning and reference identifiers.

Everything above this file depends on these five packages agreeing, so the tests
here are about *invariants* rather than about features: one instant has one
spelling, one amount has one spelling, absence carries a reason, and a version set
is its own digest.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.accounts import (
    BOOK_ORDER,
    DEFAULT_EXCLUDED_BOOKS,
    AccountId,
    Book,
    MarketId,
    MarketMode,
    OwnerContext,
    VenueId,
)
from fmis.money import (
    AssetCode,
    AssetMismatchError,
    DustPolicy,
    Money,
    Quantity,
    canonical_decimal_text,
    exact_from_market_price,
    parse_decimal,
    sum_money,
)
from fmis.provenance import (
    CORRECTABLE_ORIGINS,
    Absent,
    Assertion,
    ValueOrigin,
    VersionedTerm,
    decode_maybe,
    encode_maybe,
)
from fmis.records import (
    ConsumedSource,
    DomainValidationError,
    PayloadDecodeError,
    RecordAudit,
    UnsupportedPayloadVersionError,
    build_domain_record_id,
    content_digest_over,
    field_introduced_in,
    normalize_consumed_sources,
    parse_domain_record_id,
    require_exact_keys,
    require_payload_version,
    require_unmodified,
    require_utc,
    validate_domain_record_id,
)
from fmis.versioning import AXIS_ORDER, VersionAxis, VersionSet, deduplicate

UTC_NOON = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
STOCKHOLM_NOON = datetime(
    2026, 8, 12, 14, 0, tzinfo=timezone(timedelta(hours=2))
)


# --------------------------------------------------------------------------
# Timestamps: one instant, one spelling.
# --------------------------------------------------------------------------


def test_two_spellings_of_one_instant_normalize_to_one_value() -> None:
    assert require_utc(STOCKHOLM_NOON, "moment") == require_utc(UTC_NOON, "moment")
    assert require_utc(STOCKHOLM_NOON, "moment").tzinfo is timezone.utc


def test_a_naive_instant_is_rejected_rather_than_assumed_utc() -> None:
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        require_utc(datetime(2026, 8, 12, 12, 0), "moment")


def test_a_non_datetime_instant_is_a_type_error() -> None:
    with pytest.raises(TypeError, match="must be a datetime"):
        require_utc("2026-08-12T12:00:00Z", "moment")


# --------------------------------------------------------------------------
# RecordAudit — created_at, updated_at, and "frozen" enforced not documented.
# --------------------------------------------------------------------------


def test_a_frozen_audit_block_reports_itself_unmodified() -> None:
    audit = RecordAudit.frozen_at(UTC_NOON)
    assert audit.created_at == audit.updated_at == UTC_NOON
    assert audit.is_unmodified


def test_an_append_advances_updated_at_and_never_created_at() -> None:
    audit = RecordAudit.frozen_at(UTC_NOON).appended_at(UTC_NOON + timedelta(hours=1))
    assert audit.created_at == UTC_NOON
    assert audit.updated_at == UTC_NOON + timedelta(hours=1)
    assert not audit.is_unmodified


def test_a_record_cannot_change_before_it_exists() -> None:
    with pytest.raises(DomainValidationError, match="precedes created_at"):
        RecordAudit(created_at=UTC_NOON, updated_at=UTC_NOON - timedelta(seconds=1))


def test_require_unmodified_rejects_a_captured_artifact_that_claims_to_have_changed() -> None:
    audit = RecordAudit.frozen_at(UTC_NOON).appended_at(UTC_NOON + timedelta(hours=1))
    with pytest.raises(DomainValidationError, match="frozen at creation"):
        require_unmodified(audit, "Widget")


def test_require_unmodified_rejects_a_non_audit() -> None:
    with pytest.raises(TypeError, match="RecordAudit"):
        require_unmodified("today", "Widget")


def test_record_audit_round_trips_through_its_payload() -> None:
    audit = RecordAudit.frozen_at(UTC_NOON).appended_at(UTC_NOON + timedelta(days=1))
    assert RecordAudit.from_payload(audit.to_payload()) == audit


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"created_at": "x"}, "missing"),
        (
            {"created_at": "2026-08-12T12:00:00+00:00", "updated_at": "2026-08-12T12:00:00+00:00", "extra": 1},
            "unknown",
        ),
        ("not an object", "JSON object"),
    ],
)
def test_a_malformed_audit_payload_is_rejected(payload: object, message: str) -> None:
    with pytest.raises(PayloadDecodeError, match=message):
        RecordAudit.from_payload(payload)


# --------------------------------------------------------------------------
# Law 8 — consumed sources.
# --------------------------------------------------------------------------


def _source(record_id: str, digest_char: str = "a") -> ConsumedSource:
    return ConsumedSource(record_id, "sha256:" + digest_char * 64, "trade")


VALID_ID = "trade-BTCUSDT-20260812T120000Z-0123456789abcdef"
OTHER_ID = "trade-ETHUSDT-20260812T120000Z-fedcba9876543210"


def test_consumed_sources_are_sorted_and_deduplicated() -> None:
    first = _source(VALID_ID)
    second = _source(OTHER_ID, "b")
    assert normalize_consumed_sources([second, first, first]) == (first, second)


def test_one_record_claiming_two_digests_is_a_detected_conflict() -> None:
    with pytest.raises(DomainValidationError, match="one of the two readings is stale"):
        normalize_consumed_sources([_source(VALID_ID, "a"), _source(VALID_ID, "b")])


def test_a_consumed_source_requires_a_full_sha256_digest() -> None:
    with pytest.raises(DomainValidationError, match="sha256"):
        ConsumedSource(VALID_ID, "sha256:short", "trade")


def test_a_consumed_source_round_trips() -> None:
    source = _source(VALID_ID)
    assert ConsumedSource.from_payload(source.to_payload()) == source


def test_a_consumed_source_payload_with_the_wrong_keys_is_rejected() -> None:
    with pytest.raises(PayloadDecodeError):
        ConsumedSource.from_payload({"record_id": VALID_ID})


# --------------------------------------------------------------------------
# Content-derived identity.
# --------------------------------------------------------------------------


def test_identical_content_produces_an_identical_id() -> None:
    basis = {"quantity": "0.5", "price": "60000"}
    left = build_domain_record_id(
        type_slug="trade", subject="BTCUSDT", moment=UTC_NOON,
        digest=content_digest_over(basis),
    )
    right = build_domain_record_id(
        type_slug="trade", subject="BTCUSDT", moment=UTC_NOON,
        digest=content_digest_over(dict(reversed(list(basis.items())))),
    )
    assert left == right


def test_different_content_produces_a_different_id() -> None:
    first = content_digest_over({"quantity": "0.5"})
    second = content_digest_over({"quantity": "0.6"})
    assert first != second


def test_a_record_id_carrying_a_path_traversal_character_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="path-traversal"):
        validate_domain_record_id("../trade-BTC-20260812T120000Z-0123456789abcdef")


def test_a_record_id_of_the_wrong_shape_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="expected shape"):
        validate_domain_record_id("trade-BTCUSDT-nope-0123456789abcdef")


def test_a_record_id_that_is_not_a_string_is_a_type_error() -> None:
    with pytest.raises(TypeError):
        validate_domain_record_id(7)


def test_a_record_id_parses_back_into_its_components() -> None:
    match = parse_domain_record_id(VALID_ID)
    assert match.group("type_slug") == "trade"
    assert match.group("subject_slug") == "BTCUSDT"
    assert match.group("digest_prefix") == "0123456789abcdef"


def test_a_subject_with_unsafe_characters_is_slugified_rather_than_rejected() -> None:
    record_id = build_domain_record_id(
        type_slug="trade",
        subject="binance:BTCUSDT:spot",
        moment=UTC_NOON,
        digest=content_digest_over({"a": 1}),
    )
    assert "binance_BTCUSDT_spot" in record_id


def test_an_unknown_type_slug_shape_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="type_slug"):
        build_domain_record_id(
            type_slug="Trade", subject="x", moment=UTC_NOON,
            digest=content_digest_over({"a": 1}),
        )


def test_a_digest_that_is_not_a_full_sha256_cannot_build_an_id() -> None:
    with pytest.raises(DomainValidationError, match="sha256"):
        build_domain_record_id(
            type_slug="trade", subject="x", moment=UTC_NOON, digest="deadbeef"
        )


def test_a_digest_basis_must_be_a_mapping() -> None:
    with pytest.raises(TypeError, match="Mapping"):
        content_digest_over(["not", "a", "mapping"])


# --------------------------------------------------------------------------
# Schema guards — forward-only readers, clean rejection, coverage gaps.
# --------------------------------------------------------------------------


def test_an_unsupported_payload_version_is_a_clean_rejection() -> None:
    with pytest.raises(UnsupportedPayloadVersionError, match="not supported"):
        require_payload_version({"schema_version": 99}, supported={1}, entity="widget")


def test_a_missing_payload_version_is_rejected() -> None:
    with pytest.raises(PayloadDecodeError, match="missing"):
        require_payload_version({}, supported={1}, entity="widget")


def test_a_non_integer_payload_version_is_rejected() -> None:
    with pytest.raises(PayloadDecodeError, match="must be an int"):
        require_payload_version(
            {"schema_version": True}, supported={1}, entity="widget"
        )


def test_an_unknown_field_written_by_a_newer_build_is_rejected_not_dropped() -> None:
    with pytest.raises(PayloadDecodeError, match="newer build"):
        require_exact_keys({"a": 1, "b": 2}, {"a"}, "widget")


def test_a_missing_field_is_reported_by_name() -> None:
    with pytest.raises(PayloadDecodeError, match=r"\['b'\]"):
        require_exact_keys({"a": 1}, {"a", "b"}, "widget")


def test_a_field_introduced_later_reads_as_a_named_coverage_gap() -> None:
    assert field_introduced_in("cluster_key", 3) == (
        "cluster_key was introduced in schema version 3"
    )


# --------------------------------------------------------------------------
# Provenance.
# --------------------------------------------------------------------------


def test_absence_carries_a_reason_and_is_never_a_bare_none() -> None:
    absent = Absent("no mark is available")
    assert absent.reason == "no mark is available"
    assert absent.origin is ValueOrigin.ABSENT
    assert absent.sample_size is None


def test_the_insufficient_sample_face_carries_its_n() -> None:
    absent: Absent[int] = Absent("only three closed trades in this cohort", sample_size=3)
    assert absent.sample_size == 3
    assert Absent.from_payload(absent.to_payload()) == absent


def test_an_empty_absence_reason_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="non-empty"):
        Absent("   ")


def test_only_asserted_and_interpreted_values_are_correctable() -> None:
    assert CORRECTABLE_ORIGINS == {ValueOrigin.ASSERTED, ValueOrigin.INTERPRETED}
    assert Assertion("x", ValueOrigin.ASSERTED, "owner").is_correctable
    assert not Assertion("x", ValueOrigin.MEASURED, "engine").is_correctable


def test_an_assertion_cannot_carry_the_absent_origin() -> None:
    with pytest.raises(DomainValidationError, match="Absent"):
        Assertion("x", ValueOrigin.ABSENT, "nobody")


def test_an_assertion_round_trips_with_a_supplied_codec() -> None:
    assertion = Assertion(Decimal("1.5"), ValueOrigin.MEASURED, "binance", UTC_NOON)
    payload = assertion.to_payload(canonical_decimal_text)
    assert Assertion.from_payload(payload, lambda raw: Decimal(raw)) == assertion


def test_an_assertion_payload_with_an_unknown_origin_is_rejected() -> None:
    with pytest.raises(PayloadDecodeError, match="ValueOrigin"):
        Assertion.from_payload(
            {"value": "1", "origin": "guessed", "source": "x", "as_of": None}, str
        )


def test_a_versioned_term_renders_a_qualified_id_and_round_trips() -> None:
    term = VersionedTerm("mistake", "moved_stop", 2, display_label="Moved the stop")
    assert term.qualified_id == "mistake:moved_stop"
    assert VersionedTerm.from_payload(term.to_payload()) == term


def test_a_versioned_term_requires_a_taxonomy_version() -> None:
    with pytest.raises(DomainValidationError, match="taxonomy_version"):
        VersionedTerm("mistake", "moved_stop", 0)


def test_a_maybe_union_is_tagged_so_absence_can_carry_its_reason() -> None:
    assert encode_maybe(Absent("nothing"), str) == {"absent": {"reason": "nothing"}}
    assert encode_maybe("value", str) == {"value": "value"}
    assert decode_maybe({"value": "v"}, str) == "v"
    assert decode_maybe({"absent": {"reason": "r"}}, str) == Absent("r")


@pytest.mark.parametrize("payload", [{}, {"a": 1, "b": 2}, {"other": 1}, "text"])
def test_a_malformed_maybe_union_is_rejected(payload: object) -> None:
    with pytest.raises(PayloadDecodeError):
        decode_maybe(payload, str)


# --------------------------------------------------------------------------
# Money and quantity.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, canonical",
    [
        ("0.10", "0.1"),
        ("0.1", "0.1"),
        ("1E+3", "1000"),
        ("-0", "0"),
        ("0.000", "0"),
        ("-12.500", "-12.5"),
    ],
)
def test_one_amount_has_one_canonical_spelling(raw: str, canonical: str) -> None:
    assert canonical_decimal_text(Decimal(raw)) == canonical


def test_two_spellings_of_one_amount_produce_one_money_and_one_digest() -> None:
    left = Money(Decimal("0.10"), "USDT")
    right = Money(Decimal("0.1"), AssetCode("USDT"))
    assert left == right
    assert hash(left) == hash(right)
    assert left.to_payload() == right.to_payload()


def test_a_non_finite_amount_is_not_an_amount() -> None:
    with pytest.raises(DomainValidationError, match="not finite"):
        canonical_decimal_text(Decimal("NaN"))


def test_an_amount_wider_than_the_canonical_form_is_rejected_not_rounded() -> None:
    with pytest.raises(DomainValidationError, match="significant digits"):
        canonical_decimal_text(Decimal("1." + "1" * 40))


def test_a_float_never_reaches_an_exact_field() -> None:
    with pytest.raises(TypeError, match="never accepts a float"):
        Money(0.1, "USDT")  # type: ignore[arg-type]


def test_the_one_float_crossing_uses_the_shortest_round_tripping_form() -> None:
    assert exact_from_market_price(0.1) == Decimal("0.1")
    assert exact_from_market_price(58400.0) == Decimal("58400")


def test_the_float_crossing_rejects_a_non_float() -> None:
    with pytest.raises(TypeError, match="must be a float"):
        exact_from_market_price("0.1")  # type: ignore[arg-type]


def test_arithmetic_between_two_assets_raises_rather_than_converting() -> None:
    with pytest.raises(AssetMismatchError, match="dated rate"):
        Money(Decimal("1"), "USDT") + Money(Decimal("1"), "BTC")
    with pytest.raises(AssetMismatchError):
        Quantity(Decimal("1"), "BTC") - Quantity(Decimal("1"), "ETH")


def test_money_comparison_requires_one_asset() -> None:
    with pytest.raises(AssetMismatchError):
        Money(Decimal("1"), "USDT") < Money(Decimal("2"), "BTC")


def test_money_supports_the_arithmetic_a_fold_needs() -> None:
    ten = Money(Decimal("10"), "USDT")
    three = Money(Decimal("3"), "USDT")
    assert (ten - three).text == "7"
    assert (-three).text == "-3"
    assert abs(-three) == three
    assert ten.scale(Decimal("2")).text == "20"
    assert ten >= three and three <= ten and ten > three
    assert Money.zero("USDT").is_zero
    assert (-three).is_negative


def test_scaling_by_anything_but_a_decimal_is_a_type_error() -> None:
    with pytest.raises(TypeError):
        Money(Decimal("1"), "USDT").scale(2)  # type: ignore[arg-type]


def test_summing_an_empty_sequence_still_names_its_asset() -> None:
    assert sum_money([], asset="USDT") == Money(Decimal("0"), "USDT")


def test_a_quantity_valued_at_a_price_produces_money_in_the_quote_asset() -> None:
    value = Quantity(Decimal("1.5"), "BTC").value_at(Decimal("60000"), "USDT")
    assert value == Money(Decimal("90000"), "USDT")


def test_valuing_a_quantity_requires_an_exact_price() -> None:
    with pytest.raises(TypeError):
        Quantity(Decimal("1"), "BTC").value_at(60000.0, "USDT")  # type: ignore[arg-type]


def test_money_round_trips_through_its_payload() -> None:
    amount = Money(Decimal("-12.5"), "SEK")
    assert Money.from_payload(amount.to_payload()) == amount
    quantity = Quantity(Decimal("0.00000001"), "BTC")
    assert Quantity.from_payload(quantity.to_payload()) == quantity


def test_a_json_number_cannot_carry_an_exact_amount() -> None:
    with pytest.raises(PayloadDecodeError, match="decimal \\*string\\*"):
        parse_decimal(0.1, "amount")


def test_a_non_canonical_amount_string_is_rejected_on_decode() -> None:
    with pytest.raises(PayloadDecodeError, match="canonical form"):
        parse_decimal("0.10", "amount")


def test_an_undecodable_amount_string_is_rejected() -> None:
    with pytest.raises(PayloadDecodeError, match="is not a decimal"):
        parse_decimal("twelve", "amount")


def test_an_amount_payload_with_the_wrong_keys_is_rejected() -> None:
    with pytest.raises(PayloadDecodeError):
        Money.from_payload({"amount": "1"})


@pytest.mark.parametrize("code", ["btc", "", "TOO_LONG_ASSET_CODE_FOR_THIS", "BT-C"])
def test_an_asset_code_outside_the_pattern_is_rejected(code: str) -> None:
    with pytest.raises((DomainValidationError, TypeError)):
        AssetCode(code)


# --------------------------------------------------------------------------
# Dust policy — a named, versioned policy that invents no number.
# --------------------------------------------------------------------------


def test_an_asset_with_no_configured_threshold_uses_exact_zero() -> None:
    policy = DustPolicy("dust", 1)
    assert policy.threshold_for("ETH") == Decimal(0)
    assert policy.is_dust(Quantity(Decimal("0"), "ETH"))
    assert not policy.is_dust(Quantity(Decimal("0.0000000001"), "ETH"))


def test_a_configured_threshold_makes_a_residue_flat() -> None:
    policy = DustPolicy("dust", 1, ((AssetCode("BTC"), Decimal("0.00000001")),))
    assert policy.is_dust(Quantity(Decimal("0.000000001"), "BTC"))
    assert not policy.is_dust(Quantity(Decimal("0.1"), "BTC"))


def test_one_asset_cannot_carry_two_dust_thresholds() -> None:
    with pytest.raises(DomainValidationError, match="two dust thresholds"):
        DustPolicy(
            "dust",
            1,
            ((AssetCode("BTC"), Decimal("1")), (AssetCode("BTC"), Decimal("2"))),
        )


def test_a_negative_dust_threshold_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="cannot be negative"):
        DustPolicy("dust", 1, ((AssetCode("BTC"), Decimal("-1")),))


def test_a_dust_policy_round_trips() -> None:
    policy = DustPolicy("dust", 2, ((AssetCode("BTC"), Decimal("0.00000001")),))
    assert DustPolicy.from_payload(policy.to_payload()) == policy


def test_is_dust_requires_a_quantity() -> None:
    with pytest.raises(TypeError):
        DustPolicy("dust", 1).is_dust(Decimal("0"))  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# VersionSet.
# --------------------------------------------------------------------------


def test_a_version_set_is_complete_or_it_is_not_a_version_set() -> None:
    with pytest.raises(DomainValidationError, match="every axis must be present"):
        VersionSet(axes=((VersionAxis.CODE_VERSION, "abc123"),))


def test_of_fills_every_unsupplied_axis_with_a_reasoned_absence() -> None:
    version_set = VersionSet.of({VersionAxis.CODE_VERSION: "abc123"})
    assert len(version_set.axes) == len(AXIS_ORDER)
    assert version_set.require(VersionAxis.CODE_VERSION) == "abc123"
    assert isinstance(version_set.value_of(VersionAxis.POLICY_VERSION), Absent)


def test_requiring_an_absent_axis_refuses_to_substitute_anything() -> None:
    version_set = VersionSet.of({})
    with pytest.raises(DomainValidationError, match="handle the absence"):
        version_set.require(VersionAxis.CODE_VERSION)


def test_two_identical_version_sets_share_one_content_addressed_id() -> None:
    left = VersionSet.of({VersionAxis.CODE_VERSION: "abc123"})
    right = VersionSet.of({VersionAxis.CODE_VERSION: "abc123"})
    assert left.version_set_id == right.version_set_id
    assert deduplicate([left, right]) == (left,)


def test_a_different_axis_value_is_a_different_set() -> None:
    left = VersionSet.of({VersionAxis.CODE_VERSION: "abc123"})
    right = VersionSet.of({VersionAxis.CODE_VERSION: "def456"})
    assert left.version_set_id != right.version_set_id
    assert len(deduplicate([left, right])) == 2


def test_a_version_set_round_trips_and_verifies_its_own_id() -> None:
    version_set = VersionSet.of({VersionAxis.CODE_VERSION: "abc123"})
    payload = version_set.to_payload()
    assert VersionSet.from_payload(payload) == version_set
    payload["version_set_id"] = "sha256:" + "0" * 64
    with pytest.raises(PayloadDecodeError, match="does not match the digest"):
        VersionSet.from_payload(payload)


def test_an_axis_supplied_twice_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="twice"):
        VersionSet(
            axes=tuple((axis, "v") for axis in AXIS_ORDER)
            + ((VersionAxis.CODE_VERSION, "w"),)
        )


def test_an_unknown_axis_name_on_decode_is_rejected() -> None:
    version_set = VersionSet.of({})
    payload = version_set.to_payload()
    payload["axes"]["telepathy_version"] = {"value": "1"}
    with pytest.raises(PayloadDecodeError, match="not known to this build"):
        VersionSet.from_payload(payload)


def test_deduplicate_rejects_something_that_is_not_a_version_set() -> None:
    with pytest.raises(TypeError):
        deduplicate(["not a version set"])


def test_of_rejects_an_axis_it_does_not_know() -> None:
    with pytest.raises(DomainValidationError, match="unknown version axes"):
        VersionSet.of({"telepathy": "1"})  # type: ignore[dict-item]


# --------------------------------------------------------------------------
# Reference identifiers.
# --------------------------------------------------------------------------


def test_the_four_books_are_closed_and_ordered_from_the_longest_horizon() -> None:
    assert set(BOOK_ORDER) == set(Book)
    assert BOOK_ORDER[0] is Book.INVESTING
    assert BOOK_ORDER[-1] is Book.PAPER
    assert DEFAULT_EXCLUDED_BOOKS == {Book.PAPER}


def test_a_market_renders_its_citation_form_and_its_venue_symbol() -> None:
    market = MarketId(VenueId("binance"), "BTC", "USDT", MarketMode.SPOT)
    assert market.value == "binance:BTCUSDT:spot"
    assert market.pair_symbol == "BTCUSDT"
    assert str(market) == market.value


def test_a_perpetual_and_a_spot_pair_on_one_symbol_are_two_markets() -> None:
    spot = MarketId(VenueId("binance"), "BTC", "USDT", MarketMode.SPOT)
    perp = MarketId(VenueId("binance"), "BTC", "USDT", MarketMode.PERPETUAL)
    assert spot != perp
    assert spot.value != perp.value


def test_a_market_cannot_exchange_an_asset_for_itself() -> None:
    with pytest.raises(DomainValidationError, match="exchanges one asset"):
        MarketId(VenueId("binance"), "BTC", "BTC", MarketMode.SPOT)


def test_a_market_mode_has_no_default() -> None:
    with pytest.raises(TypeError, match="no default"):
        MarketId(VenueId("binance"), "BTC", "USDT", "spot")  # type: ignore[arg-type]


def test_a_market_round_trips_through_its_four_components() -> None:
    market = MarketId(VenueId("binance"), "BTC", "USDT", MarketMode.PERPETUAL)
    assert MarketId.from_payload(market.to_payload()) == market


def test_an_unknown_market_mode_on_decode_is_rejected() -> None:
    with pytest.raises(PayloadDecodeError, match="MarketMode"):
        MarketId.from_payload(
            {"venue": "binance", "base_asset": "BTC", "quote_asset": "USDT", "mode": "swaps"}
        )


@pytest.mark.parametrize("identifier", ["Binance", "", "9binance", "binance-spot"])
def test_a_declared_identifier_outside_the_pattern_is_rejected(identifier: str) -> None:
    with pytest.raises((DomainValidationError, TypeError)):
        AccountId(identifier)


def test_the_owner_context_projects_an_owner_local_date_without_storing_one() -> None:
    owner = OwnerContext("Europe/Stockholm", "SEK", "Europe/Stockholm", ("07:00",))
    late_utc = datetime(2026, 8, 12, 22, 30, tzinfo=timezone.utc)
    assert owner.local_date(late_utc) == "2026-08-13"
    assert owner.local_date(datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)) == "2026-08-12"


def test_the_owner_context_rejects_an_invalid_zone_and_an_invalid_routine_time() -> None:
    with pytest.raises(DomainValidationError, match="IANA"):
        OwnerContext("Mars/Olympus", "SEK", "Europe/Stockholm")
    with pytest.raises(DomainValidationError, match="HH:MM"):
        OwnerContext("Europe/Stockholm", "SEK", "Europe/Stockholm", ("7am",))


def test_the_owner_context_rejects_a_repeated_routine_time() -> None:
    with pytest.raises(DomainValidationError, match="must not repeat"):
        OwnerContext("Europe/Stockholm", "SEK", "Europe/Stockholm", ("07:00", "07:00"))


def test_the_owner_context_round_trips() -> None:
    owner = OwnerContext("Europe/Stockholm", "SEK", "Europe/Berlin", ("07:00", "22:15"))
    assert OwnerContext.from_payload(owner.to_payload()) == owner


def test_a_local_date_needs_an_aware_instant() -> None:
    owner = OwnerContext("Europe/Stockholm", "SEK", "Europe/Stockholm")
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        owner.local_date(datetime(2026, 8, 12, 12, 0))
