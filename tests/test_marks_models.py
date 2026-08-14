"""Milestone BM — the shapes a price snapshot is made of.

Every rule `fmis.marks.models` states, asserted. The ones that matter most are
the ones a portfolio silently depends on: a symbol appears once, a price is
positive, a reading is never dated after the snapshot that holds it, and a
payload version this build does not write is refused rather than half-read.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from marks_helpers import SOURCE, reading, snapshot
from trade_domain_helpers import AT

from fmis.marks import (
    PRICE_SNAPSHOT_SCHEMA_VERSION,
    SUPPORTED_PRICE_SNAPSHOT_VERSIONS,
    MarksError,
    PriceBasis,
    PriceReading,
    PriceSnapshot,
    PriceUnavailable,
    PriceUnreadableError,
)

# --------------------------------------------------------------------------
# PriceBasis
# --------------------------------------------------------------------------


def test_exactly_one_basis_exists_and_it_names_the_closed_candle_rule() -> None:
    """One member is a stated choice, not indecision — see the class docstring.

    Pinned so that adding a second is a deliberate edit here as well as there,
    and so a stored snapshot's basis can never change meaning underneath it.
    """
    assert [member.value for member in PriceBasis] == ["last_closed_candle_close"]


# --------------------------------------------------------------------------
# PriceReading
# --------------------------------------------------------------------------


def test_a_reading_carries_its_source_its_interval_and_its_rule() -> None:
    assert reading().provenance == (
        f"{SOURCE} · 1h · last_closed_candle_close · bar opened "
        f"{AT(11).isoformat()}"
    )


def test_the_provenance_line_can_never_omit_the_basis() -> None:
    """A price shown without how it was chosen is a price nobody can check."""
    line = reading().provenance
    assert "last_closed_candle_close" in line
    assert SOURCE in line
    assert "1h" in line


@pytest.mark.parametrize("price", [0, -1, 0.0])
def test_a_non_positive_price_is_refused_rather_than_recorded(price: float) -> None:
    """A zero is not a cheaper market; it is a broken reading."""
    with pytest.raises(ValueError, match="not a cheaper market"):
        reading(price=price)


def test_an_infinite_price_is_refused() -> None:
    with pytest.raises(ValueError, match="finite"):
        reading(price=float("inf"))


def test_a_bool_is_not_a_price() -> None:
    with pytest.raises(TypeError):
        reading(price=True)


def test_a_naive_instant_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        reading(observed_at=datetime(2026, 8, 12, 11))


def test_a_non_utc_offset_is_refused() -> None:
    with pytest.raises(ValueError, match="must represent UTC"):
        reading(observed_at=datetime(
            2026, 8, 12, 11, tzinfo=timezone(timedelta(hours=2))
        ))


def test_a_blank_source_is_refused_because_an_unattributable_price_is_useless() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        reading(source="   ")


def test_a_symbol_that_is_not_text_is_refused() -> None:
    with pytest.raises(TypeError, match="symbol must be a str"):
        reading(symbol=("BTC", "USDT"))


def test_a_closed_count_that_is_not_an_integer_is_refused() -> None:
    with pytest.raises(TypeError, match="closed_count must be an int"):
        reading(closed_count="2")


def test_a_basis_that_is_not_a_member_is_refused() -> None:
    with pytest.raises(TypeError, match="PriceBasis"):
        reading(basis="last_closed_candle_close")


def test_closed_count_must_be_at_least_one() -> None:
    """A reading exists only because a closed candle did."""
    with pytest.raises(ValueError, match="at least 1"):
        reading(closed_count=0)


def test_age_is_computed_at_read_time_and_stored_nowhere() -> None:
    assert reading().age_at(AT(14)) == timedelta(hours=3)
    assert "age" not in PriceReading.__dataclass_fields__


def test_age_refuses_a_naive_reference() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        reading().age_at(datetime(2026, 8, 12, 14))


def test_a_reading_round_trips_through_its_payload() -> None:
    original = reading()
    assert PriceReading.from_payload(original.to_payload()) == original


def test_a_reading_payload_missing_a_field_is_refused() -> None:
    payload = reading().to_payload()
    del payload["source"]
    with pytest.raises(ValueError, match="missing"):
        PriceReading.from_payload(payload)


def test_a_reading_payload_with_an_unknown_field_is_refused() -> None:
    """Strict, never repairing — the ingestion boundary's own rule, applied to a
    record this build wrote itself."""
    payload = reading().to_payload()
    payload["confidence"] = 0.9
    with pytest.raises(ValueError, match="unknown"):
        PriceReading.from_payload(payload)


def test_a_reading_payload_with_an_unknown_basis_is_refused_cleanly() -> None:
    payload = reading().to_payload()
    payload["basis"] = "volume_weighted_mid"
    with pytest.raises(ValueError, match="not one this build knows"):
        PriceReading.from_payload(payload)


# --------------------------------------------------------------------------
# PriceUnavailable
# --------------------------------------------------------------------------


def test_an_unavailability_needs_a_reason() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        PriceUnavailable(symbol="BTCUSDT", reason="")


def test_an_unavailability_round_trips() -> None:
    entry = PriceUnavailable(symbol="BTCUSDT", reason="provider timed out")
    assert PriceUnavailable.from_payload(entry.to_payload()) == entry


# --------------------------------------------------------------------------
# PriceSnapshot — the invariants a portfolio depends on
# --------------------------------------------------------------------------


def test_one_symbol_cannot_be_both_priced_and_unpriced() -> None:
    """Two answers for one market would let a reader pick the one they liked."""
    with pytest.raises(ValueError, match="appears twice"):
        PriceSnapshot(
            taken_at=AT(12),
            source=SOURCE,
            basis=PriceBasis.LAST_CLOSED_CANDLE_CLOSE,
            readings=(reading(),),
            unavailable=(PriceUnavailable(symbol="BTCUSDT", reason="timed out"),),
        )


def test_one_symbol_cannot_be_priced_twice() -> None:
    with pytest.raises(ValueError, match="appears twice"):
        PriceSnapshot(
            taken_at=AT(12),
            source=SOURCE,
            basis=PriceBasis.LAST_CLOSED_CANDLE_CLOSE,
            readings=(reading(), reading(price=2.0)),
        )


def test_a_reading_from_the_snapshots_own_future_is_refused() -> None:
    with pytest.raises(ValueError, match="a clock problem, not a price"):
        PriceSnapshot(
            taken_at=AT(10),
            source=SOURCE,
            basis=PriceBasis.LAST_CLOSED_CANDLE_CLOSE,
            readings=(reading(observed_at=AT(11)),),
        )


def test_a_reading_on_a_different_basis_is_refused() -> None:
    """One snapshot, one basis, or the prices in it are not comparable.

    Unreachable through `build_price_snapshot`, which stamps one basis on every
    reading it makes — and asserted anyway, because the type is what guarantees
    it and a second producer must not be able to violate it.
    """

    class _OtherBasis:
        value = "mid"

    forged = object.__new__(PriceReading)
    for name, value in (
        ("symbol", "BTCUSDT"), ("interval", "1h"), ("price", 1.0),
        ("observed_at", AT(9)), ("basis", _OtherBasis()), ("source", SOURCE),
        ("closed_count", 1),
    ):
        object.__setattr__(forged, name, value)
    with pytest.raises(ValueError, match="one snapshot has one basis"):
        PriceSnapshot(
            taken_at=AT(12),
            source=SOURCE,
            basis=PriceBasis.LAST_CLOSED_CANDLE_CLOSE,
            readings=(forged,),
        )


def test_an_empty_snapshot_is_legal_and_says_it_priced_nothing() -> None:
    empty = PriceSnapshot(
        taken_at=AT(12), source="nothing was needed",
        basis=PriceBasis.LAST_CLOSED_CANDLE_CLOSE,
    )
    assert empty.is_empty is True
    assert empty.requested_count == 0
    assert empty.oldest_reading() is None


def test_reading_for_and_reason_for_report_two_different_absences() -> None:
    """*"The fetch failed"* and *"it was never asked for"* are different facts."""
    taken = snapshot(1.0, unreadable={"ETHUSDT": "provider timed out"})
    assert taken.reading_for("BTCUSDT") is not None
    assert taken.reading_for("ETHUSDT") is None
    assert taken.reason_for("ETHUSDT") == "provider timed out"
    assert taken.reason_for("SOLUSDT") is None


def test_the_oldest_reading_is_the_one_a_total_is_bounded_by() -> None:
    """Not an average — an average lets one stale holding hide behind nine fresh
    ones, and it is the stale one that makes the total wrong."""
    bundle = PriceSnapshot(
        taken_at=AT(12),
        source=SOURCE,
        basis=PriceBasis.LAST_CLOSED_CANDLE_CLOSE,
        readings=(
            reading(symbol="ETHUSDT", observed_at=AT(11)),
            reading(symbol="BTCUSDT", observed_at=AT(8)),
            reading(symbol="SOLUSDT", observed_at=AT(10)),
        ),
    )
    assert bundle.oldest_reading().symbol == "BTCUSDT"


def test_priced_and_unpriced_symbols_are_reported_separately() -> None:
    taken = snapshot(1.0, unreadable={"ETHUSDT": "timed out"})
    assert taken.priced_symbols == ("BTCUSDT",)
    assert taken.unpriced_symbols == ("ETHUSDT",)
    assert taken.requested_count == 2


# --------------------------------------------------------------------------
# Version compatibility
# --------------------------------------------------------------------------


def test_the_schema_version_is_pinned_and_supported() -> None:
    assert PRICE_SNAPSHOT_SCHEMA_VERSION == 1
    assert PRICE_SNAPSHOT_SCHEMA_VERSION in SUPPORTED_PRICE_SNAPSHOT_VERSIONS


def test_a_snapshot_round_trips_through_its_payload() -> None:
    original = snapshot(60000.0, 61000.0, unreadable={"ETHUSDT": "timed out"})
    assert PriceSnapshot.from_payload(original.to_payload()) == original


def test_a_version_this_build_does_not_write_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="not one this build writes"):
        PriceSnapshot(
            taken_at=AT(12), source=SOURCE,
            basis=PriceBasis.LAST_CLOSED_CANDLE_CLOSE, schema_version=2,
        )


def test_a_payload_from_a_newer_build_is_refused_rather_than_half_read() -> None:
    """Decoding it while ignoring what this build does not know is a valuation
    missing prices it cannot see it is missing."""
    payload = snapshot(1.0).to_payload()
    payload["schema_version"] = 99
    with pytest.raises(ValueError, match="written by a newer build"):
        PriceSnapshot.from_payload(payload)


def test_a_payload_missing_a_field_is_refused() -> None:
    payload = snapshot(1.0).to_payload()
    del payload["basis"]
    with pytest.raises(ValueError, match="missing"):
        PriceSnapshot.from_payload(payload)


def test_a_payload_with_an_extra_field_is_refused() -> None:
    payload = snapshot(1.0).to_payload()
    payload["fx_rate"] = "1.0"
    with pytest.raises(ValueError, match="unknown"):
        PriceSnapshot.from_payload(payload)


@pytest.mark.parametrize(
    "field, value",
    [("readings", {}), ("unavailable", "none")],
)
def test_a_payload_whose_collection_is_not_a_list_is_refused(
    field: str, value: object
) -> None:
    payload = snapshot(1.0).to_payload()
    payload[field] = value
    with pytest.raises(TypeError, match="must be a list"):
        PriceSnapshot.from_payload(payload)


def test_a_payload_that_is_not_a_mapping_is_refused() -> None:
    with pytest.raises(TypeError, match="must be a mapping"):
        PriceSnapshot.from_payload(["not", "a", "mapping"])


def test_a_payload_instant_must_be_timezone_aware() -> None:
    payload = snapshot(1.0).to_payload()
    payload["taken_at"] = "2026-08-12T12:00:00"
    with pytest.raises(ValueError, match="timezone-aware"):
        PriceSnapshot.from_payload(payload)


def test_a_payload_instant_must_be_a_string() -> None:
    payload = snapshot(1.0).to_payload()
    payload["taken_at"] = 1755000000
    with pytest.raises(TypeError, match="ISO-8601"):
        PriceSnapshot.from_payload(payload)


def test_a_payload_carrying_a_non_utc_offset_is_normalized_to_utc() -> None:
    """Accepted and converted, rather than refused: the offset is unambiguous,
    and rejecting a well-formed instant would make a snapshot written on a
    machine with a local-time serializer unreadable forever."""
    payload = snapshot(1.0).to_payload()
    payload["taken_at"] = "2026-08-12T14:00:00+02:00"
    assert PriceSnapshot.from_payload(payload).taken_at == AT(12)


# --------------------------------------------------------------------------
# Types and errors
# --------------------------------------------------------------------------


def test_a_snapshot_refuses_a_non_reading_in_its_readings() -> None:
    with pytest.raises(TypeError, match="PriceReading"):
        PriceSnapshot(
            taken_at=AT(12), source=SOURCE,
            basis=PriceBasis.LAST_CLOSED_CANDLE_CLOSE, readings=("BTCUSDT 61000",),
        )


def test_a_snapshot_refuses_a_string_where_a_collection_belongs() -> None:
    with pytest.raises(TypeError, match="iterable"):
        PriceSnapshot(
            taken_at=AT(12), source=SOURCE,
            basis=PriceBasis.LAST_CLOSED_CANDLE_CLOSE, readings="BTCUSDT",
        )


def test_a_snapshot_refuses_a_basis_that_is_not_a_member() -> None:
    with pytest.raises(TypeError, match="PriceBasis"):
        PriceSnapshot(taken_at=AT(12), source=SOURCE, basis="closed")


def test_every_failure_in_this_package_shares_one_base() -> None:
    """So a caller can catch this layer's failures as a group."""
    assert issubclass(PriceUnreadableError, MarksError)
    assert issubclass(PriceUnreadableError, ValueError)
