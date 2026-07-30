"""Tests for series identity and the context contract (fmis.data, fmis.series_context).

The contract exists because of one measured fact, which the first test in §6 pins:
two candle series with different identities but identical OHLC rows produce
**byte-identical** analytical histories. Before this milestone nothing could tell
them apart. The tests that matter most are therefore the ones proving that the
envelope distinguishes them while the payload stays untouched.

The second theme is that adding context must not change a single analytical value.
That is proved rather than asserted: §7 compares context-aware payloads against
context-free returns across every fixture class the milestone names — empty,
insufficient structure, each trend outcome, each sequence state, and outside-bar
derived structure.

Identity propagation is asserted with `is`, not `==`. A wrapper that rebuilt an
equal identity would pass every equality test while quietly severing the link to
the series the payload actually came from.
"""

from __future__ import annotations

import ast
import pickle
import sys
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import fmis.data as data_pkg
import fmis.series_context as sc
from fmis.data import Candle, CandleSeries, SeriesIdentity
from fmis.market_structure import (
    DEFAULT_LEFT_BARS,
    DEFAULT_RIGHT_BARS,
    StructuralSequenceStateType,
    compare_swing_sequence,
    derive_structural_sequence_state_history,
    detect_swings,
    label_swing_sequence,
)
from fmis.series_context import (
    ContextualSeries,
    SeriesContextError,
    SeriesIdentityMismatchError,
    contextual_structural_state_history,
    contextual_structural_swings,
    contextual_structural_trend_history,
    require_same_identity,
)
from fmis.structural_trend import (
    StructuralTrendType,
    derive_structural_trend_history,
)

_BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
PACKAGE_DIR = Path(sc.__file__).parent

S = StructuralSequenceStateType
TT = StructuralTrendType


# ================================ fixtures ==================================


def candles(symbol: str, timeframe: str, rows) -> tuple[Candle, ...]:
    return tuple(
        Candle(
            timestamp=_BASE + timedelta(hours=4 * position),
            symbol=symbol,
            timeframe=timeframe,
            open=o,
            high=h,
            low=lo,
            close=c,
            volume=10.0,
            is_closed=True,
        )
        for position, (o, h, lo, c) in enumerate(rows)
    )


def series(symbol: str, timeframe: str, rows) -> CandleSeries:
    return CandleSeries(
        symbol=symbol, timeframe=timeframe, candles=candles(symbol, timeframe, rows)
    )


#: Filler high/low. Every non-pivot bar carries these, so a filler can never be a
#: pivot itself: `detect_swings` needs a strictly greater high than its left
#: neighbours, and equal fillers fail that.
FILLER_HIGH, FILLER_LOW = 100.0, 90.0


def wave_rows(pivots, *, outside: bool = False):
    """Deterministic 8-bar cycles, one confirmed swing high and low per cycle.

    Each cycle places a spike high at slot 2 and a spike low at slot 6, far enough
    apart that both confirm under the repository's **default** 2-bar window — which
    is the window the wrappers forward, and the reason a naive 2-bar zigzag produces
    no pivots at all.

    With ``outside=True`` both spikes land on the *same* bar, which is exactly an
    outside bar: one candle yielding a HIGH and a LOW at one index.

    ``pivots`` is a list of ``(high, low)`` per cycle, so a caller shapes the
    structural story directly: both rising gives `SHIFTED_HIGHER`, both falling
    `SHIFTED_LOWER`, widening `EXPANDED`, narrowing `CONTRACTED`, repeating
    `UNCHANGED`, and alternating gives a contested history.
    """
    rows = []
    for high, low in pivots:
        for slot in range(8):
            spike_low_here = slot == 2 if outside else slot == 6
            mid = (FILLER_HIGH + FILLER_LOW) / 2
            rows.append((
                mid,
                high if slot == 2 else FILLER_HIGH,
                low if spike_low_here else FILLER_LOW,
                mid,
            ))
    return rows


def _alternating_pivots(count: int = 8):
    return [
        (105 + 5 * i, 60 + 5 * i) if i % 2 == 0 else (130 - 5 * i, 85 - 5 * i)
        for i in range(count)
    ]


#: The fixture classes the milestone requires equivalence to be proved over.
#: Between them they exercise every `StructuralSequenceStateType` member, every
#: `StructuralTrendType` member, and outside-bar structure — asserted, not assumed,
#: by `test_every_required_fixture_class_is_actually_exercised`.
FIXTURES: dict[str, list] = {
    "empty": [],
    "insufficient": wave_rows([(120.0, 70.0)]),
    "sustained_higher": wave_rows([(105 + 5 * i, 60 + 5 * i) for i in range(6)]),
    "sustained_lower": wave_rows([(130 - 5 * i, 85 - 5 * i) for i in range(6)]),
    "expanded": wave_rows([(105 + 5 * i, 85 - 5 * i) for i in range(6)]),
    "contracted": wave_rows([(130 - 5 * i, 60 + 5 * i) for i in range(6)]),
    "unchanged": wave_rows([(120.0, 70.0) for _ in range(6)]),
    "alternating": wave_rows(_alternating_pivots()),
    "outside_bars": wave_rows(
        [(105 + 5 * i, 60 + 5 * i) for i in range(6)], outside=True
    ),
    "outside_alternating": wave_rows(_alternating_pivots(), outside=True),
}

BTC4 = ("BTCUSDT", "4h")
ETH4 = ("ETHUSDT", "4h")
BTC1 = ("BTCUSDT", "1h")


def full_context(symbol: str, timeframe: str, rows):
    return contextual_structural_trend_history(
        contextual_structural_state_history(
            contextual_structural_swings(series(symbol, timeframe, rows))
        )
    )


def full_plain(symbol: str, timeframe: str, rows):
    plain = series(symbol, timeframe, rows)
    swings = label_swing_sequence(
        compare_swing_sequence(
            detect_swings(
                plain, left_bars=DEFAULT_LEFT_BARS, right_bars=DEFAULT_RIGHT_BARS
            )
        )
    )
    states = derive_structural_sequence_state_history(swings)
    return swings, states, derive_structural_trend_history(states)


# ===================== 1. SeriesIdentity construction =======================


def test_identity_holds_exactly_two_fields() -> None:
    assert [f.name for f in fields(SeriesIdentity)] == ["symbol", "timeframe"]


def test_identity_is_constructed_from_symbol_and_timeframe() -> None:
    one = SeriesIdentity(symbol="BTCUSDT", timeframe="4h")
    assert one.symbol == "BTCUSDT" and one.timeframe == "4h"


@pytest.mark.parametrize(
    "absent",
    ["venue", "exchange", "source", "provider", "market", "market_type",
     "quote_currency", "price_type", "contract", "contract_id", "metadata",
     "as_of", "run_id"],
)
def test_identity_has_no_speculative_field(absent: str) -> None:
    """A field earns inclusion only if something today would be wrong without it."""
    assert absent not in {f.name for f in fields(SeriesIdentity)}


# ===================== 2. immutability ======================================


def test_identity_is_frozen() -> None:
    one = SeriesIdentity("BTCUSDT", "4h")
    with pytest.raises(FrozenInstanceError):
        one.symbol = "ETHUSDT"  # type: ignore[misc]


def test_identity_is_slotted_and_grows_no_attribute() -> None:
    one = SeriesIdentity("BTCUSDT", "4h")
    assert not hasattr(one, "__dict__")
    with pytest.raises((AttributeError, FrozenInstanceError, TypeError)):
        one.venue = "BINANCE"  # type: ignore[attr-defined]


def test_contextual_series_is_frozen_and_slotted() -> None:
    envelope = ContextualSeries(identity=SeriesIdentity("BTCUSDT", "4h"), values=())
    assert not hasattr(envelope, "__dict__")
    with pytest.raises(FrozenInstanceError):
        envelope.identity = SeriesIdentity("ETHUSDT", "4h")  # type: ignore[misc]


def test_contextual_series_payload_is_an_immutable_tuple() -> None:
    envelope = ContextualSeries(
        identity=SeriesIdentity("BTCUSDT", "4h"), values=[1, 2, 3]
    )
    assert envelope.values == (1, 2, 3)
    assert isinstance(envelope.values, tuple)
    with pytest.raises(TypeError):
        envelope.values[0] = 9  # type: ignore[index]


# ===================== 3-4. equality and hashing ============================


def test_identity_equality_is_exact_and_structural() -> None:
    assert SeriesIdentity("BTCUSDT", "4h") == SeriesIdentity("BTCUSDT", "4h")


def test_the_same_identity_reconstructed_separately_compares_equal() -> None:
    a, b = SeriesIdentity("BTCUSDT", "4h"), SeriesIdentity("BTCUSDT", "4h")
    assert a is not b
    assert a == b and hash(a) == hash(b)
    assert len({a, b}) == 1


def test_identity_hash_is_stable_across_calls() -> None:
    one = SeriesIdentity("BTCUSDT", "4h")
    assert len({hash(one) for _ in range(100)}) == 1


def test_identity_can_key_a_dict() -> None:
    table = {SeriesIdentity("BTCUSDT", "4h"): "btc", SeriesIdentity("ETHUSDT", "4h"): "eth"}
    assert table[SeriesIdentity("BTCUSDT", "4h")] == "btc"
    assert len(table) == 2


@pytest.mark.parametrize(
    "other",
    [("ETHUSDT", "4h"), ("BTCUSDT", "1h"), ("btcusdt", "4h"), ("BTCUSDT", "4H"),
     (" BTCUSDT", "4h"), ("BTCUSDT ", "4h"), ("BTCUSDT", " 4h"), ("BTC/USDT", "4h"),
     ("BTCUSDT", "240m"), ("NASDAQ:BTCUSDT", "4h")],
)
def test_identities_that_must_not_be_equal(other: tuple[str, str]) -> None:
    """No case folding, no trimming, no alias translation — the contract over-rejects."""
    assert SeriesIdentity("BTCUSDT", "4h") != SeriesIdentity(*other)


def test_identity_is_not_equal_to_a_plain_tuple() -> None:
    assert SeriesIdentity("BTCUSDT", "4h") != ("BTCUSDT", "4h")


# ===================== 5-8. validation policy ===============================


@pytest.mark.parametrize("field", ["symbol", "timeframe"])
@pytest.mark.parametrize("bad", ["", " ", "\t", "\n", "   \t\n  "])
def test_empty_or_blank_identity_values_are_rejected(field: str, bad: str) -> None:
    kwargs = {"symbol": "BTCUSDT", "timeframe": "4h", field: bad}
    with pytest.raises(ValueError, match=f"{field} cannot be empty"):
        SeriesIdentity(**kwargs)


@pytest.mark.parametrize("field", ["symbol", "timeframe"])
@pytest.mark.parametrize("bad", [None, 4, 4.0, True, b"BTCUSDT", ["BTCUSDT"]])
def test_non_string_identity_values_are_rejected(field: str, bad: object) -> None:
    kwargs = {"symbol": "BTCUSDT", "timeframe": "4h", field: bad}
    with pytest.raises(TypeError, match=f"{field} must be a str"):
        SeriesIdentity(**kwargs)


@pytest.mark.parametrize("value", [" BTCUSDT", "BTCUSDT ", " BTCUSDT ", "BTC USDT"])
def test_whitespace_bearing_values_are_accepted_and_preserved_never_trimmed(
    value: str,
) -> None:
    """Forced by compatibility: `CandleSeries` accepts these, so the projection must."""
    one = SeriesIdentity(symbol=value, timeframe="4h")
    assert one.symbol == value
    assert one != SeriesIdentity(symbol=value.strip().replace(" ", ""), timeframe="4h")


def test_the_identity_rule_is_no_stricter_than_candle_series() -> None:
    """The compatibility constraint, pinned: every valid series has a valid identity."""
    for symbol in ("BTCUSDT", " BTCUSDT ", "BTC USDT", "btcusdt", "Ω-USDT"):
        for timeframe in ("4h", "4H", " 4h", "banana"):
            built = series(symbol, timeframe, [(100.0, 101.0, 99.0, 100.5)])
            assert built.identity == SeriesIdentity(symbol, timeframe)


@pytest.mark.parametrize("timeframe", ["4h", "4H", "1m", "banana", "-4h", "0", "1Y", "P4H"])
def test_a_timeframe_label_is_opaque_and_its_grammar_is_not_validated(
    timeframe: str,
) -> None:
    """ADR-0009: validating the grammar needs a canonical vocabulary that does not exist."""
    assert SeriesIdentity("BTCUSDT", timeframe).timeframe == timeframe


@pytest.mark.parametrize(
    "symbol", ["BTCUSDT", "BTC-USD", "ΒΤCUSDT", "btcüsdt", "BTC​usdt", "日経225"]
)
def test_unicode_values_are_accepted_as_is_and_never_normalized(symbol: str) -> None:
    assert SeriesIdentity(symbol, "4h").symbol == symbol


def test_visually_similar_unicode_forms_are_different_identities() -> None:
    """No NFC/NFKC folding: normalizing is normalizing. Over-rejection is the safe direction."""
    composed, decomposed = "CAFÉUSD", "CAFÉUSD"
    assert composed != decomposed
    assert SeriesIdentity(composed, "4h") != SeriesIdentity(decomposed, "4h")


def test_no_default_identity_exists() -> None:
    """A default identity is the silent-mixing bug with extra steps."""
    with pytest.raises(TypeError):
        SeriesIdentity()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        SeriesIdentity("BTCUSDT")  # type: ignore[call-arg]


# ===================== CandleSeries.identity projection =====================


def test_candle_series_identity_is_a_projection_not_a_stored_field() -> None:
    stored = {f.name for f in fields(CandleSeries)}
    assert "identity" not in stored
    assert stored == {"symbol", "timeframe", "candles"}


def test_candle_series_identity_matches_its_own_fields() -> None:
    built = series(*BTC4, FIXTURES["unchanged"])
    assert built.identity == SeriesIdentity(built.symbol, built.timeframe)


def test_candle_series_identity_survives_closed() -> None:
    built = series(*BTC4, FIXTURES["unchanged"])
    assert built.closed().identity == built.identity


def test_an_empty_candle_series_still_has_an_identity() -> None:
    assert CandleSeries(symbol="BTCUSDT", timeframe="4h", candles=()).identity == (
        SeriesIdentity("BTCUSDT", "4h")
    )


# ===================== 9. empty contextual series ===========================


def test_an_empty_contextual_series_is_legal_and_keeps_its_identity() -> None:
    envelope = ContextualSeries(identity=SeriesIdentity(*BTC4), values=())
    assert envelope.values == () and len(envelope) == 0
    assert envelope.identity == SeriesIdentity(*BTC4)


def test_an_empty_series_keeps_identity_through_every_stage() -> None:
    empty = series(*BTC4, [])
    swings = contextual_structural_swings(empty)
    states = contextual_structural_state_history(swings)
    trend = contextual_structural_trend_history(states)
    for stage in (swings, states, trend):
        assert stage.values == ()
        assert stage.identity is empty.identity or stage.identity == empty.identity
    assert trend.identity == SeriesIdentity(*BTC4)


def test_two_empty_series_with_different_identities_are_not_equal() -> None:
    """Missing evidence is not missing identity."""
    a = contextual_structural_swings(series(*BTC4, []))
    b = contextual_structural_swings(series(*ETH4, []))
    assert a.values == b.values == ()
    assert a != b
    with pytest.raises(SeriesIdentityMismatchError):
        require_same_identity(a, b)


# ===================== 10-11. context preservation ==========================


def test_identity_is_carried_by_object_identity_not_rebuilt() -> None:
    """`is`, not `==`: a rebuilt equal identity would sever the link silently."""
    built = series(*BTC4, FIXTURES["sustained_higher"])
    swings = contextual_structural_swings(built)
    states = contextual_structural_state_history(swings)
    trend = contextual_structural_trend_history(states)
    assert states.identity is swings.identity
    assert trend.identity is states.identity


def test_one_identity_object_is_reused_across_many_transformations() -> None:
    built = series(*BTC4, FIXTURES["sustained_higher"])
    swings = contextual_structural_swings(built)
    chain = [swings]
    for _ in range(5):
        chain.append(contextual_structural_state_history(swings))
    assert len({id(link.identity) for link in chain}) == 1


def test_identity_is_stored_once_per_series_not_once_per_element() -> None:
    trend = full_context(*BTC4, FIXTURES["sustained_higher"])
    assert len(trend) > 0
    for element in trend.values:
        assert not hasattr(element, "identity")
        assert not hasattr(element, "symbol")
        assert not hasattr(element, "timeframe")


def test_no_wrapper_accepts_an_identity_argument() -> None:
    """Substitution is unrepresentable, not merely discouraged."""
    import inspect

    for fn in (contextual_structural_swings, contextual_structural_state_history,
               contextual_structural_trend_history):
        assert "identity" not in inspect.signature(fn).parameters, fn.__name__


def test_context_cannot_be_replaced_mid_pipeline_by_assignment() -> None:
    swings = contextual_structural_swings(series(*BTC4, FIXTURES["alternating"]))
    with pytest.raises(FrozenInstanceError):
        swings.identity = SeriesIdentity(*ETH4)  # type: ignore[misc]


def test_a_deliberately_mislabelled_envelope_is_still_rejected_downstream() -> None:
    """Hand-building a wrong envelope is possible; combining it is not."""
    honest = contextual_structural_swings(series(*BTC4, FIXTURES["alternating"]))
    forged = ContextualSeries(identity=SeriesIdentity(*ETH4), values=honest.values)
    assert forged.values == honest.values
    with pytest.raises(SeriesIdentityMismatchError):
        require_same_identity(honest, forged)


# ===================== 12-15. mismatch and acceptance =======================


def test_different_instrument_same_timeframe_is_rejected() -> None:
    a, b = full_context(*BTC4, FIXTURES["sustained_higher"]), full_context(*ETH4, FIXTURES["sustained_higher"])
    with pytest.raises(
        SeriesIdentityMismatchError,
        match=r"subjects\[1\] has identity 'ETHUSDT'/'4h', expected 'BTCUSDT'/'4h'",
    ):
        require_same_identity(a, b)


def test_same_instrument_different_timeframe_is_rejected() -> None:
    a, b = full_context(*BTC4, FIXTURES["sustained_higher"]), full_context(*BTC1, FIXTURES["sustained_higher"])
    with pytest.raises(
        SeriesIdentityMismatchError,
        match=r"subjects\[1\] has identity 'BTCUSDT'/'1h', expected 'BTCUSDT'/'4h'",
    ):
        require_same_identity(a, b)


def test_case_difference_alone_is_a_mismatch() -> None:
    a = contextual_structural_swings(series("BTCUSDT", "4h", FIXTURES["alternating"]))
    b = contextual_structural_swings(series("btcusdt", "4h", FIXTURES["alternating"]))
    with pytest.raises(SeriesIdentityMismatchError):
        require_same_identity(a, b)


def test_whitespace_difference_alone_is_a_mismatch() -> None:
    a = contextual_structural_swings(series("BTCUSDT", "4h", FIXTURES["alternating"]))
    b = contextual_structural_swings(series(" BTCUSDT", "4h", FIXTURES["alternating"]))
    with pytest.raises(SeriesIdentityMismatchError):
        require_same_identity(a, b)


def test_identical_identity_is_accepted_and_the_shared_identity_returned() -> None:
    a = contextual_structural_swings(series(*BTC4, FIXTURES["sustained_higher"]))
    b = contextual_structural_swings(series(*BTC4, FIXTURES["alternating"]))
    assert require_same_identity(a, b) == SeriesIdentity(*BTC4)


def test_a_candle_series_and_a_contextual_series_check_against_each_other() -> None:
    """The shape Level-Crossing needs: candles plus derived facts, one check."""
    built = series(*BTC4, FIXTURES["sustained_higher"])
    swings = contextual_structural_swings(built)
    assert require_same_identity(built, swings) == SeriesIdentity(*BTC4)
    with pytest.raises(SeriesIdentityMismatchError):
        require_same_identity(series(*ETH4, FIXTURES["sustained_higher"]), swings)


def test_a_single_subject_is_accepted_and_returns_its_identity() -> None:
    built = series(*BTC4, FIXTURES["unchanged"])
    assert require_same_identity(built) == SeriesIdentity(*BTC4)


def test_many_subjects_all_matching_are_accepted() -> None:
    built = series(*BTC4, FIXTURES["sustained_higher"])
    swings = contextual_structural_swings(built)
    states = contextual_structural_state_history(swings)
    trend = contextual_structural_trend_history(states)
    assert require_same_identity(built, swings, states, trend) == SeriesIdentity(*BTC4)


def test_the_error_names_the_first_offending_position_deterministically() -> None:
    good = contextual_structural_swings(series(*BTC4, FIXTURES["alternating"]))
    bad1 = contextual_structural_swings(series(*ETH4, FIXTURES["alternating"]))
    bad2 = contextual_structural_swings(series(*BTC1, FIXTURES["alternating"]))
    with pytest.raises(SeriesIdentityMismatchError, match=r"subjects\[2\]"):
        require_same_identity(good, good, bad1, bad2)
    for _ in range(20):
        with pytest.raises(SeriesIdentityMismatchError, match=r"subjects\[1\] .*ETHUSDT"):
            require_same_identity(good, bad1, bad2)


def test_no_subjects_is_rejected() -> None:
    with pytest.raises(TypeError, match="at least one subject"):
        require_same_identity()


@pytest.mark.parametrize("bad", [None, 7, "BTCUSDT", ("BTCUSDT", "4h"), object()])
def test_a_subject_without_a_series_identity_is_rejected(bad: object) -> None:
    good = contextual_structural_swings(series(*BTC4, FIXTURES["unchanged"]))
    with pytest.raises(TypeError, match=r"subjects\[1\] must expose a SeriesIdentity"):
        require_same_identity(good, bad)


def test_the_mismatch_error_is_a_value_error_and_a_context_error() -> None:
    assert issubclass(SeriesIdentityMismatchError, SeriesContextError)
    assert issubclass(SeriesIdentityMismatchError, ValueError)
    assert issubclass(SeriesContextError, Exception)


# ===================== 16-17. mixed histories ===============================


def test_a_mixed_instrument_state_history_is_rejected_by_the_safe_api() -> None:
    a = contextual_structural_state_history(
        contextual_structural_swings(series(*BTC4, FIXTURES["sustained_higher"]))
    )
    b = contextual_structural_state_history(
        contextual_structural_swings(series(*ETH4, FIXTURES["sustained_higher"]))
    )
    with pytest.raises(SeriesIdentityMismatchError):
        require_same_identity(a, b)


def test_a_mixed_timeframe_trend_history_is_rejected_by_the_safe_api() -> None:
    a = full_context(*BTC4, FIXTURES["sustained_higher"])
    b = full_context(*BTC1, FIXTURES["sustained_higher"])
    with pytest.raises(SeriesIdentityMismatchError):
        require_same_identity(a, b)


def test_the_measured_risk_this_contract_closes() -> None:
    """Identical rows, different identities: the analytics cannot tell them apart.

    This is the P3-2 finding from the Trend Foundation review, reproduced as a
    test. The payloads really are equal — the envelope is the only thing that
    distinguishes them, which is precisely why the envelope had to exist.
    """
    rows = FIXTURES["sustained_higher"]
    btc, eth = full_context(*BTC4, rows), full_context(*ETH4, rows)
    assert btc.values == eth.values, "fixture no longer reproduces the risk"
    assert len(btc.values) > 0
    assert btc != eth
    assert btc.identity != eth.identity
    with pytest.raises(SeriesIdentityMismatchError):
        require_same_identity(btc, eth)


# ===================== 18-23. analytical equivalence ========================


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_context_aware_payloads_equal_context_free_results(name: str) -> None:
    """Wrapping must not change a single analytical value."""
    rows = FIXTURES[name]
    plain_swings, plain_states, plain_trend = full_plain(*BTC4, rows)
    built = series(*BTC4, rows)
    swings = contextual_structural_swings(built)
    states = contextual_structural_state_history(swings)
    trend = contextual_structural_trend_history(states)
    assert swings.values == plain_swings, name
    assert states.values == plain_states, name
    assert trend.values == plain_trend, name


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_identity_does_not_influence_analytical_values(name: str) -> None:
    """The same rows under three identities give three identical payloads."""
    rows = FIXTURES[name]
    payloads = [full_context(sym, tf, rows).values for sym, tf in (BTC4, ETH4, BTC1)]
    assert payloads[0] == payloads[1] == payloads[2], name


def test_every_required_fixture_class_is_actually_exercised() -> None:
    """Guard the guard: the equivalence sweep must really cover the named classes."""
    seen_states: set[StructuralSequenceStateType] = set()
    seen_trends: set[StructuralTrendType] = set()
    outside_bar_seen = False
    for rows in FIXTURES.values():
        states = contextual_structural_state_history(
            contextual_structural_swings(series(*BTC4, rows))
        )
        seen_states |= {s.state.state for s in states.values}
        outside_bar_seen |= any(len(s.triggers) == 2 for s in states.values)
        trend = contextual_structural_trend_history(states)
        seen_trends |= {t.trend for t in trend.values}

    for required in (S.INSUFFICIENT_STRUCTURE, S.SHIFTED_HIGHER, S.SHIFTED_LOWER,
                     S.EXPANDED, S.CONTRACTED, S.UNCHANGED):
        assert required in seen_states, required
    for required in (TT.SUSTAINED_HIGHER, TT.SUSTAINED_LOWER, TT.NEUTRAL,
                     TT.INDETERMINATE):
        assert required in seen_trends, required
    assert outside_bar_seen, "no fixture produced an outside bar"
    assert not FIXTURES["empty"]


def test_ordering_errors_surface_from_the_delegate_unchanged() -> None:
    swings = contextual_structural_swings(series(*BTC4, FIXTURES["sustained_higher"]))
    reversed_run = ContextualSeries(
        identity=swings.identity, values=tuple(reversed(swings.values))
    )
    with pytest.raises(ValueError) as context_aware:
        contextual_structural_state_history(reversed_run)
    with pytest.raises(ValueError) as context_free:
        derive_structural_sequence_state_history(reversed_run.values)
    assert str(context_aware.value) == str(context_free.value)


def test_prefix_behaviour_is_unchanged_under_the_wrappers() -> None:
    rows = FIXTURES["outside_bars"]
    built = series(*BTC4, rows)
    full = contextual_structural_trend_history(
        contextual_structural_state_history(contextual_structural_swings(built))
    )
    for count in range(1, len(rows) + 1):
        partial_series = CandleSeries(
            symbol="BTCUSDT", timeframe="4h", candles=built.candles[:count]
        )
        partial = contextual_structural_trend_history(
            contextual_structural_state_history(
                contextual_structural_swings(partial_series)
            )
        )
        assert partial.values == full.values[: len(partial.values)], count
        assert partial.identity == full.identity


def test_outside_bar_atomicity_is_unchanged_under_the_wrappers() -> None:
    states = contextual_structural_state_history(
        contextual_structural_swings(series(*BTC4, FIXTURES["outside_bars"]))
    )
    assert any(len(s.triggers) == 2 for s in states.values)
    trend = contextual_structural_trend_history(states)
    assert len(trend.values) == len(states.values)


def test_left_and_right_bars_are_forwarded_verbatim() -> None:
    built = series(*BTC4, FIXTURES["sustained_higher"])
    for left, right in ((1, 1), (2, 2), (3, 1)):
        assert contextual_structural_swings(
            built, left_bars=left, right_bars=right
        ).values == label_swing_sequence(
            compare_swing_sequence(
                detect_swings(built, left_bars=left, right_bars=right)
            )
        )


# ===================== 24. serialization ====================================


def test_identity_survives_a_pickle_round_trip() -> None:
    one = SeriesIdentity("BTCUSDT", "4h")
    restored = pickle.loads(pickle.dumps(one))
    assert restored == one and hash(restored) == hash(one)
    assert restored.symbol == "BTCUSDT" and restored.timeframe == "4h"


def test_a_contextual_series_survives_a_pickle_round_trip() -> None:
    envelope = full_context(*BTC4, FIXTURES["sustained_higher"])
    restored = pickle.loads(pickle.dumps(envelope))
    assert restored.identity == envelope.identity
    assert restored.values == envelope.values
    assert restored == envelope


def test_a_round_tripped_identity_still_rejects_a_mismatch() -> None:
    a = pickle.loads(pickle.dumps(contextual_structural_swings(series(*BTC4, FIXTURES["alternating"]))))
    b = contextual_structural_swings(series(*ETH4, FIXTURES["alternating"]))
    with pytest.raises(SeriesIdentityMismatchError):
        require_same_identity(a, b)


# ===================== envelope type validation =============================


@pytest.mark.parametrize("bad", [None, "BTCUSDT", ("BTCUSDT", "4h"), 7])
def test_an_envelope_requires_a_real_series_identity(bad: object) -> None:
    with pytest.raises(TypeError, match="identity must be a SeriesIdentity"):
        ContextualSeries(identity=bad, values=())  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["abc", b"abc", None, 7])
def test_an_envelope_rejects_a_non_iterable_or_string_payload(bad: object) -> None:
    with pytest.raises(TypeError, match="values must be an iterable"):
        ContextualSeries(identity=SeriesIdentity(*BTC4), values=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "fn,name",
    [(contextual_structural_state_history, "structures"),
     (contextual_structural_trend_history, "snapshots")],
)
def test_a_bare_payload_passed_where_an_envelope_belongs_is_rejected(fn, name) -> None:
    """Without this the identity would be silently lost, not loudly refused."""
    plain_swings, plain_states, _ = full_plain(*BTC4, FIXTURES["sustained_higher"])
    payload = plain_swings if name == "structures" else plain_states
    with pytest.raises(TypeError, match=f"{name} must be a ContextualSeries"):
        fn(payload)


def test_contextual_structural_swings_rejects_a_non_candle_series() -> None:
    with pytest.raises(TypeError, match="series must be a CandleSeries"):
        contextual_structural_swings(series(*BTC4, FIXTURES["unchanged"]).candles)  # type: ignore[arg-type]


# ===================== 30. Level-Crossing consumption shape =================


def test_a_future_candle_consuming_module_can_join_the_contract() -> None:
    """The exact shape Level-Crossing Foundation will use, pinned now."""
    built = series(*BTC4, FIXTURES["sustained_higher"])
    swings = contextual_structural_swings(built)

    def hypothetical_level_consumer(candle_series: CandleSeries, structures):
        identity = require_same_identity(candle_series, structures)
        return identity, len(candle_series.candles), len(structures.values)

    identity, bars, count = hypothetical_level_consumer(built, swings)
    assert identity == SeriesIdentity(*BTC4)
    assert bars == len(built.candles) and count > 0

    with pytest.raises(SeriesIdentityMismatchError):
        hypothetical_level_consumer(series(*ETH4, FIXTURES["sustained_higher"]), swings)


def test_the_contract_is_usable_without_importing_structural_trend() -> None:
    """Level-Crossing must not have to depend on trend to get identity."""
    from fmis.series_context.models import (  # noqa: F401
        ContextualSeries as _Envelope,
        require_same_identity as _check,
    )

    tree = ast.parse((PACKAGE_DIR / "models.py").read_text())
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(m.startswith("fmis.structural_trend") for m in imported)
    assert not any(m.startswith("fmis.market_structure") for m in imported)


# ===================== 25-27. exports and dependency direction ==============


def test_the_series_context_public_api_is_exactly_seven_names() -> None:
    assert set(sc.__all__) == {
        "ContextualSeries",
        "SeriesContextError",
        "SeriesIdentityMismatchError",
        "require_same_identity",
        "contextual_structural_swings",
        "contextual_structural_state_history",
        "contextual_structural_trend_history",
    }
    assert len(sc.__all__) == 7


def test_the_data_public_api_gained_only_series_identity() -> None:
    assert set(data_pkg.__all__) == {
        "Candle", "CandleSeries", "SeriesIdentity", "ObservationSeries",
        "CandleField", "candle_series_to_observations",
    }


def test_every_exported_name_resolves() -> None:
    for name in sc.__all__:
        assert hasattr(sc, name), name


def test_no_submodule_collides_with_a_public_name() -> None:
    import pkgutil

    submodules = {m.name for m in pkgutil.iter_modules(sc.__path__)}
    assert submodules == {"models", "pipeline"}
    assert submodules & set(sc.__all__) == set()


def test_no_export_collides_across_the_whole_package_tree() -> None:
    import collections
    import importlib
    import pkgutil

    import fmis

    owners: dict[str, list[str]] = collections.defaultdict(list)
    for module in pkgutil.walk_packages(fmis.__path__, "fmis."):
        imported = importlib.import_module(module.name)
        if imported.__spec__ is None or imported.__spec__.submodule_search_locations is None:
            continue
        for name in getattr(imported, "__all__", []):
            owners[name].append(module.name)
    assert {n: o for n, o in owners.items() if len(o) > 1} == {}


def test_no_private_helper_is_exported() -> None:
    for private in ("_carry", "_identity_of", "_require_envelope",
                    "_require_identity_label"):
        assert private not in sc.__all__, private
        assert not hasattr(sc, private), private
    assert "_require_identity_label" not in data_pkg.__all__


def test_no_mutable_public_object_is_exported() -> None:
    for name in sc.__all__:
        assert not isinstance(getattr(sc, name), (list, dict, set)), name


def _internal_imports() -> set[str]:
    found: set[str] = set()
    for py in PACKAGE_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("fmis"):
                    found.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("fmis"):
                        found.add(alias.name)
    return found


def test_imports_only_the_three_permitted_packages() -> None:
    assert _internal_imports() <= {
        "fmis.data",
        "fmis.market_structure",
        "fmis.structural_trend",
        "fmis.series_context.models",
        "fmis.series_context.pipeline",
    }


@pytest.mark.parametrize(
    "forbidden",
    ["fmis.decision_support", "fmis.evidence", "fmis.providers", "fmis.pipeline",
     "fmis.ingest", "fmis.trading_context", "fmis.relative_value", "fmis.features",
     "fmis.alignment"],
)
def test_does_not_depend_on_other_layers(forbidden: str) -> None:
    assert not any(i.startswith(forbidden) for i in _internal_imports()), forbidden


def test_does_not_reach_into_private_submodules_of_its_dependencies() -> None:
    for internal in _internal_imports():
        assert not internal.startswith("fmis.market_structure."), internal
        assert not internal.startswith("fmis.structural_trend."), internal
        assert not internal.startswith("fmis.data."), internal


def test_nothing_below_imports_series_context() -> None:
    root = PACKAGE_DIR.parent
    for py in root.rglob("*.py"):
        if py.parent == PACKAGE_DIR:
            continue
        assert "fmis.series_context" not in py.read_text(), py


def test_no_import_cycle_exists() -> None:
    """`fmis.data` must remain importable without any of its dependents."""
    import subprocess

    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys; import fmis.data; "
         "assert 'fmis.series_context' not in sys.modules; "
         "assert 'fmis.market_structure' not in sys.modules; "
         "assert 'fmis.structural_trend' not in sys.modules; print('ok')"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


def test_uses_only_stdlib() -> None:
    roots: set[str] = set()
    for py in PACKAGE_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                roots |= {a.name.split(".")[0] for a in node.names}
    assert roots <= set(sys.stdlib_module_names) | {"fmis"}


# ===================== 28-29. architecture guards ===========================


def test_no_analytical_logic_is_duplicated_here() -> None:
    """The wrappers delegate; they must never re-derive."""
    tree = ast.parse((PACKAGE_DIR / "pipeline.py").read_text())
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for required in ("detect_swings", "compare_swing_sequence", "label_swing_sequence",
                     "derive_structural_sequence_state_history",
                     "derive_structural_trend_history"):
        assert required in called, required


def test_the_package_performs_no_arithmetic_and_reads_no_price() -> None:
    for py in sorted(PACKAGE_DIR.glob("*.py")):
        tree = ast.parse(py.read_text())
        assert not [n for n in ast.walk(tree) if isinstance(n, ast.BinOp)], py.name
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in (
                    "open", "high", "low", "close", "volume", "price",
                    "comparison", "label", "state", "trend", "triggers",
                ), f"{py.name}: {node.attr}"


def test_the_package_names_no_state_or_trend_member() -> None:
    """Delegation means never restating another layer's vocabulary."""
    for py in sorted(PACKAGE_DIR.glob("*.py")):
        source = py.read_text()
        for member in StructuralSequenceStateType:
            assert f"StructuralSequenceStateType.{member.name}" not in source
        for member in StructuralTrendType:
            assert f"StructuralTrendType.{member.name}" not in source


def test_no_global_mutable_state_exists() -> None:
    """No registry, no cache, no ambient current series."""
    for py in sorted(PACKAGE_DIR.glob("*.py")):
        tree = ast.parse(py.read_text())
        assert not [n for n in ast.walk(tree) if isinstance(n, ast.Global)], py.name
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    [node.target] if isinstance(node, ast.AnnAssign) else node.targets
                )
                if any(
                    isinstance(x, ast.Name) and x.id == "__all__" for x in targets
                ):
                    continue  # the export list is a declaration, not state
                value = node.value
                if isinstance(value, (ast.List, ast.Dict, ast.Set)):
                    raise AssertionError(f"{py.name}: module-level mutable literal")
                if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
                    assert value.func.id not in (
                        "list", "dict", "set", "defaultdict", "local",
                    ), f"{py.name}: module-level mutable {value.func.id}"


def test_no_module_level_mutable_object_is_reachable_at_runtime() -> None:
    import fmis.series_context.models as models_mod
    import fmis.series_context.pipeline as pipeline_mod

    for module in (models_mod, pipeline_mod, sc):
        for name, value in vars(module).items():
            if name.startswith("__"):
                continue
            assert not isinstance(value, (list, dict, set)), f"{module.__name__}.{name}"


def test_identity_is_never_inferred_from_timestamps_or_prices() -> None:
    """Scans code, not prose — a docstring may name what the code must not do."""
    for py in sorted(PACKAGE_DIR.glob("*.py")):
        tree = ast.parse(py.read_text())
        docstrings = {
            d
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
            and (d := ast.get_docstring(node, clean=False)) is not None
        }
        tokens: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                tokens.add(node.id.lower())
            elif isinstance(node, ast.Attribute):
                tokens.add(node.attr.lower())
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                tokens.add(node.name.lower())
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value not in docstrings:
                    tokens.add(node.value.lower())
        for banned in ("timedelta", "total_seconds", "infer", "guess",
                       "detect_timeframe", "normalize", "casefold", "strip"):
            assert banned not in tokens, f"{py.name}: {banned}"


# ===================== 19-23. upstream unchanged ============================


def test_the_market_structure_public_api_is_unchanged() -> None:
    import fmis.market_structure as ms

    assert len(ms.__all__) == 19
    assert not {n for n in ms.__all__ if "context" in n.lower() or "identity" in n.lower()}


def test_the_structural_trend_public_api_is_unchanged() -> None:
    import fmis.structural_trend as st

    assert len(st.__all__) == 5


def test_market_structure_evidence_family_remains_empty() -> None:
    from fmis.evidence import EvidenceFamily, descriptors, descriptors_for

    assert descriptors_for(EvidenceFamily.MARKET_STRUCTURE) == ()
    assert len(descriptors()) == 6


def test_no_existing_production_module_changed_its_imports() -> None:
    """Only `fmis.data.models` gained anything, and it gained no import."""
    import fmis.data.models as dm

    tree = ast.parse(Path(dm.__file__).read_text())
    modules = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert modules == {"__future__", "fmis.data._timeutils", "dataclasses", "datetime"}
