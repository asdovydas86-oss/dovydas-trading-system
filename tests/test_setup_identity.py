"""BG-D1 — stable setup identity, its two projections, and the defect it closes.

The headline test is `test_one_idea_across_a_sliding_window_is_one_occurrence`.
Everything else exists to stop that one passing for the wrong reason.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fmis.accounts import Book, MarketId
from fmis.provenance import Absent, VersionedTerm
from fmis.proposal import (
    SETUP_IDENTITY_VERSION,
    SETUP_VOCABULARY_ID,
    SetupObservation,
    SetupOccurrence,
    anchor_identity,
    anchor_of,
    anchors_match,
    group_occurrences,
    level_origin_ref,
    stable_origin_id,
)
from fmis.proposal.occurrence import CONFIRMED_STATE
from fmis.records import DomainValidationError
from fmis.snapshotting import Anchor, LevelOriginRef, TradeDirection

from trade_domain_helpers import (
    MARKET,
    OTHER_MARKET,
    level,
    setup_reading,
    version_set,
)

PIVOT = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
START = datetime(2026, 8, 1, tzinfo=timezone.utc)


def at(bar: int) -> datetime:
    """The instant of the ``bar``-th observation. One observation per hour."""
    return START + timedelta(hours=bar)


def ref(*, swing_index: int, pivot: datetime = PIVOT, bars: int = 3) -> LevelOriginRef:
    """A level origin ref for one fixed pivot, seen from a window at ``swing_index``."""
    return level_origin_ref(
        pivot_timestamp=pivot,
        label="higher_low",
        confirmation_bars=bars,
        swing_index=swing_index,
    )


def observation(
    *,
    bar: int,
    swing_index: int,
    direction: TradeDirection = TradeDirection.LONG,
    state: str = "candidate",
    pivot: datetime = PIVOT,
    market: MarketId | None = None,
    book: Book = Book.SWING,
    setup_type: VersionedTerm | Absent | None = None,
) -> SetupObservation:
    """One reading of one idea, from a window that has slid ``swing_index`` back."""
    market = MARKET if market is None else market
    if direction.is_directional:
        anchor: Anchor | Absent = anchor_of(
            market=market,
            book=book,
            direction=direction,
            invalidation_origin=ref(swing_index=swing_index, pivot=pivot),
        )
    else:
        anchor = Absent("a NO_TRADE reading has no invalidation level to anchor on")
    reading = setup_reading(
        as_of=at(bar), state=state, direction=direction, anchor=anchor
    )
    values = {
        "market": market,
        "book": book,
        "reading": reading,
        "version_set": version_set(),
    }
    if setup_type is not None:
        values["setup_type"] = setup_type
    return SetupObservation(**values)


def wait(bar: int) -> SetupObservation:
    """A `WAIT` reading — no direction, no anchor, no identity."""
    return observation(
        bar=bar, swing_index=0, direction=TradeDirection.NO_TRADE, state="wait"
    )


# ---------------------------------------------------------------------------
# The defect. Report 0012 §7: 549 "unique setups" from 552 directional
# observations, because identity was keyed on a window-relative bar index.
# ---------------------------------------------------------------------------


def test_one_idea_across_a_sliding_window_is_one_occurrence() -> None:
    """552 observations of one unchanged idea group into exactly one occurrence.

    The window slides forward one candle per instant, so the *same* pivot sits at
    a lower `swing_index` on every bar — 551 down to 0. That falling index is
    precisely what `AV` keyed identity on, and precisely what this milestone
    excludes from it.
    """
    total = 552
    observations = tuple(
        observation(bar=bar, swing_index=total - 1 - bar) for bar in range(total)
    )

    occurrences = group_occurrences(observations, occurrence_gap_bars=0)

    assert len(occurrences) == 1, (
        f"{total} readings of one idea produced {len(occurrences)} occurrences; "
        "AV's window-relative identity produced 549"
    )
    only = occurrences[0]
    assert only.observation_count == total
    assert only.began_at == at(0)
    assert only.last_seen_at == at(total - 1)


def test_the_swing_index_moves_every_bar_in_that_series() -> None:
    """The defect's cause is present in the fixture, so the test above is real.

    Without this, `test_one_idea_across_a_sliding_window_is_one_occurrence` would
    pass just as well against a fixture that never varied the index.
    """
    first = observation(bar=0, swing_index=551)
    last = observation(bar=551, swing_index=0)

    assert first.anchor.invalidation_origin.swing_index == 551
    assert last.anchor.invalidation_origin.swing_index == 0
    # The raw dataclass comparison the old `_anchor_matches` used says these are
    # two different ideas. That is the bug, reproduced here as a fact.
    assert first.anchor != last.anchor
    # The identity rule says they are one idea.
    assert anchors_match(first.anchor, last.anchor)


def test_identity_survives_the_window_but_not_a_different_pivot() -> None:
    moved = observation(bar=3, swing_index=7, pivot=PIVOT + timedelta(hours=1))
    same = observation(bar=3, swing_index=7)

    assert same.identity != moved.identity, "a different pivot is a different idea"


# ---------------------------------------------------------------------------
# `stable_origin_id`
# ---------------------------------------------------------------------------


def test_stable_origin_id_is_deterministic() -> None:
    first = stable_origin_id(pivot_timestamp=PIVOT, label="higher_low", confirmation_bars=3)
    second = stable_origin_id(pivot_timestamp=PIVOT, label="higher_low", confirmation_bars=3)

    assert first == second


@pytest.mark.parametrize(
    "changed",
    [
        {"pivot_timestamp": PIVOT + timedelta(minutes=1)},
        {"label": "lower_low"},
        {"confirmation_bars": 4},
    ],
)
def test_every_component_changes_the_origin_id(changed: dict[str, object]) -> None:
    """No component is decorative — each one moves the id."""
    base = {"pivot_timestamp": PIVOT, "label": "higher_low", "confirmation_bars": 3}
    assert stable_origin_id(**base) != stable_origin_id(**{**base, **changed})


def test_a_naive_pivot_timestamp_is_refused() -> None:
    with pytest.raises(Exception):
        stable_origin_id(
            pivot_timestamp=datetime(2026, 7, 1, 12), label="higher_low", confirmation_bars=3
        )


def test_confirmation_bars_below_one_is_refused() -> None:
    with pytest.raises(Exception):
        stable_origin_id(pivot_timestamp=PIVOT, label="higher_low", confirmation_bars=0)


def test_level_origin_ref_carries_the_index_without_counting_it() -> None:
    near = ref(swing_index=2)
    far = ref(swing_index=400)

    assert near.swing_index == 2
    assert far.swing_index == 400
    assert near.origin_id == far.origin_id
    assert near != far


# ---------------------------------------------------------------------------
# `anchor_identity`
# ---------------------------------------------------------------------------


def test_anchor_identity_ignores_the_swing_index() -> None:
    near = anchor_of(
        market=MARKET,
        book=Book.SWING,
        direction=TradeDirection.LONG,
        invalidation_origin=ref(swing_index=1),
    )
    far = anchor_of(
        market=MARKET,
        book=Book.SWING,
        direction=TradeDirection.LONG,
        invalidation_origin=ref(swing_index=999),
    )

    assert anchor_identity(near) == anchor_identity(far)


def test_anchor_identity_separates_the_two_directions() -> None:
    long_side = anchor_of(
        market=MARKET,
        book=Book.SWING,
        direction=TradeDirection.LONG,
        invalidation_origin=ref(swing_index=1),
    )
    short_side = anchor_of(
        market=MARKET,
        book=Book.SWING,
        direction=TradeDirection.SHORT,
        invalidation_origin=ref(swing_index=1),
    )

    assert not anchors_match(long_side, short_side)


def test_anchor_identity_separates_two_confirmation_windows() -> None:
    """ADR-0024: a level under a different confirmation window is a different level."""
    three = anchor_of(
        market=MARKET,
        book=Book.SWING,
        direction=TradeDirection.LONG,
        invalidation_origin=ref(swing_index=1, bars=3),
    )
    five = anchor_of(
        market=MARKET,
        book=Book.SWING,
        direction=TradeDirection.LONG,
        invalidation_origin=ref(swing_index=1, bars=5),
    )

    assert not anchors_match(three, five)


def test_anchor_identity_refuses_a_non_anchor() -> None:
    with pytest.raises(TypeError):
        anchor_identity("BTCUSDT|swing|long|abc")


def test_identity_does_not_depend_on_policy_version() -> None:
    """Two variants over the same candles decompose into the same setups."""
    first = observation(bar=0, swing_index=5)
    second = SetupObservation(
        market=MARKET,
        book=Book.SWING,
        reading=setup_reading(
            as_of=at(0),
            state="confirmed",
            direction=TradeDirection.LONG,
            policy_id="swing-setup-v2-experimental",
            anchor=first.anchor,
        ),
        version_set=version_set(policy_version="9.9.9"),
    )

    assert first.identity == second.identity


# ---------------------------------------------------------------------------
# `SetupObservation`
# ---------------------------------------------------------------------------


def test_a_no_trade_observation_has_no_identity() -> None:
    subject = wait(0)

    assert not subject.is_directional
    assert isinstance(subject.identity, Absent)
    assert isinstance(subject.anchor, Absent)


def test_the_observation_is_a_projection_and_carries_no_codec() -> None:
    """§9.3 gives it write authority *none*. A codec would be a way to store it."""
    subject = observation(bar=0, swing_index=1)

    assert not hasattr(subject, "to_payload")
    assert not hasattr(type(subject), "from_payload")
    assert not hasattr(subject, "audit")


def test_a_setup_type_from_another_vocabulary_is_refused() -> None:
    with pytest.raises(DomainValidationError):
        observation(
            bar=0,
            swing_index=1,
            setup_type=VersionedTerm(
                vocabulary_id="mistake", term_id="chased-entry", taxonomy_version=1
            ),
        )


def test_a_setup_type_in_the_setup_vocabulary_is_accepted() -> None:
    term = VersionedTerm(
        vocabulary_id=SETUP_VOCABULARY_ID,
        term_id="trend-continuation-retest",
        taxonomy_version=1,
    )
    subject = observation(bar=0, swing_index=1, setup_type=term)

    assert subject.setup_type == term


def test_setup_type_is_absent_by_default() -> None:
    """The engine classifies readiness and direction, never setup *kind*."""
    assert isinstance(observation(bar=0, swing_index=1).setup_type, Absent)


def test_an_anchor_disagreeing_with_the_observations_market_is_refused() -> None:
    other = OTHER_MARKET
    reading = setup_reading(
        as_of=at(0),
        direction=TradeDirection.LONG,
        anchor=anchor_of(
            market=other,
            book=Book.SWING,
            direction=TradeDirection.LONG,
            invalidation_origin=ref(swing_index=1),
        ),
    )
    with pytest.raises(DomainValidationError):
        SetupObservation(
            market=MARKET, book=Book.SWING, reading=reading, version_set=version_set()
        )


# ---------------------------------------------------------------------------
# `group_occurrences`
# ---------------------------------------------------------------------------


def test_a_direction_flip_ends_the_occurrence_immediately() -> None:
    observations = (
        observation(bar=0, swing_index=3),
        observation(bar=1, swing_index=2),
        observation(bar=2, swing_index=1, direction=TradeDirection.SHORT),
    )

    occurrences = group_occurrences(observations, occurrence_gap_bars=5)

    assert len(occurrences) == 2
    assert occurrences[0].direction is TradeDirection.LONG
    assert occurrences[0].observation_count == 2
    assert occurrences[1].direction is TradeDirection.SHORT


def test_tolerance_covers_silence_but_never_disagreement() -> None:
    """A generous gap does not merge two different ideas."""
    observations = (
        observation(bar=0, swing_index=3),
        observation(bar=1, swing_index=2, pivot=PIVOT - timedelta(days=1)),
    )

    assert len(group_occurrences(observations, occurrence_gap_bars=99)) == 2


def test_a_wait_shorter_than_the_tolerance_interrupts_without_ending() -> None:
    observations = (
        observation(bar=0, swing_index=4),
        wait(1),
        observation(bar=2, swing_index=2),
    )

    occurrences = group_occurrences(observations, occurrence_gap_bars=1)

    assert len(occurrences) == 1
    assert occurrences[0].observation_count == 2


def test_a_wait_run_beyond_the_tolerance_ends_the_occurrence() -> None:
    observations = (
        observation(bar=0, swing_index=5),
        wait(1),
        wait(2),
        observation(bar=3, swing_index=2),
    )

    occurrences = group_occurrences(observations, occurrence_gap_bars=1)

    assert len(occurrences) == 2
    assert occurrences[0].observation_count == 1
    assert occurrences[1].observation_count == 1


def test_zero_tolerance_means_any_wait_ends_it() -> None:
    observations = (
        observation(bar=0, swing_index=3),
        wait(1),
        observation(bar=2, swing_index=1),
    )

    assert len(group_occurrences(observations, occurrence_gap_bars=0)) == 2


def test_the_gap_parameter_is_required() -> None:
    """The data model declines to choose a value; so does this module."""
    with pytest.raises(TypeError):
        group_occurrences((observation(bar=0, swing_index=1),))


def test_a_negative_gap_is_refused() -> None:
    with pytest.raises(Exception):
        group_occurrences((observation(bar=0, swing_index=1),), occurrence_gap_bars=-1)


def test_no_observations_produce_no_occurrences() -> None:
    assert group_occurrences((), occurrence_gap_bars=0) == ()


def test_only_waits_produce_no_occurrences() -> None:
    assert group_occurrences((wait(0), wait(1)), occurrence_gap_bars=3) == ()


def test_trailing_waits_do_not_lose_the_open_occurrence() -> None:
    observations = (observation(bar=0, swing_index=2), wait(1))

    occurrences = group_occurrences(observations, occurrence_gap_bars=5)

    assert len(occurrences) == 1
    assert occurrences[0].observation_count == 1


def test_grouping_is_pure() -> None:
    observations = tuple(observation(bar=b, swing_index=9 - b) for b in range(5))

    first = group_occurrences(observations, occurrence_gap_bars=2)
    second = group_occurrences(observations, occurrence_gap_bars=2)

    assert first == second


def test_out_of_order_observations_are_refused() -> None:
    observations = (observation(bar=3, swing_index=1), observation(bar=1, swing_index=2))

    with pytest.raises(DomainValidationError):
        group_occurrences(observations, occurrence_gap_bars=0)


def test_a_repeated_instant_is_refused() -> None:
    observations = (observation(bar=1, swing_index=2), observation(bar=1, swing_index=1))

    with pytest.raises(DomainValidationError):
        group_occurrences(observations, occurrence_gap_bars=0)


def test_two_markets_in_one_series_are_refused() -> None:
    other = OTHER_MARKET
    observations = (
        observation(bar=0, swing_index=2),
        observation(bar=1, swing_index=1, market=other),
    )

    with pytest.raises(DomainValidationError):
        group_occurrences(observations, occurrence_gap_bars=0)


def test_two_books_in_one_series_are_refused() -> None:
    observations = (
        observation(bar=0, swing_index=2),
        observation(bar=1, swing_index=1, book=Book.PAPER),
    )

    with pytest.raises(DomainValidationError):
        group_occurrences(observations, occurrence_gap_bars=0)


def test_a_non_observation_is_refused() -> None:
    with pytest.raises(TypeError):
        group_occurrences(("not an observation",), occurrence_gap_bars=0)


def test_a_non_tuple_series_is_refused() -> None:
    with pytest.raises(TypeError):
        group_occurrences([observation(bar=0, swing_index=1)], occurrence_gap_bars=0)


# ---------------------------------------------------------------------------
# `SetupOccurrence`
# ---------------------------------------------------------------------------


def test_first_confirmation_fires_once_per_occurrence() -> None:
    """The flag AV's identity could not deliver: it fired on every confirmed bar."""
    observations = (
        observation(bar=0, swing_index=4, state="candidate"),
        observation(bar=1, swing_index=3, state=CONFIRMED_STATE),
        observation(bar=2, swing_index=2, state=CONFIRMED_STATE),
        observation(bar=3, swing_index=1, state=CONFIRMED_STATE),
    )

    occurrences = group_occurrences(observations, occurrence_gap_bars=0)

    assert len(occurrences) == 1
    only = occurrences[0]
    assert only.ever_confirmed
    assert only.first_confirmed_at == at(1)
    confirmations = sum(1 for item in only.observations if item.reading.state == CONFIRMED_STATE)
    assert confirmations == 3, "three confirmed bars…"
    assert len([o for o in occurrences if o.ever_confirmed]) == 1, "…but one decision"


def test_an_unconfirmed_occurrence_says_why_it_has_no_confirmation() -> None:
    occurrences = group_occurrences(
        (observation(bar=0, swing_index=1),), occurrence_gap_bars=0
    )

    assert isinstance(occurrences[0].first_confirmed_at, Absent)
    assert not occurrences[0].ever_confirmed


def test_the_confirmed_state_matches_the_engines_own_member() -> None:
    """The domain holds the spelling as text; this pins it to the engine."""
    from fmis.swing_setup import SetupState

    assert CONFIRMED_STATE == SetupState.CONFIRMED.value


def test_an_occurrence_with_no_observations_is_refused() -> None:
    with pytest.raises(DomainValidationError):
        SetupOccurrence(
            identity="x",
            market=MARKET,
            book=Book.SWING,
            direction=TradeDirection.LONG,
            anchor=anchor_of(
                market=MARKET,
                book=Book.SWING,
                direction=TradeDirection.LONG,
                invalidation_origin=ref(swing_index=1),
            ),
            observations=(),
        )


def test_the_identity_version_is_stamped_into_the_key() -> None:
    """A bump re-derives every occurrence — safe only because nothing frozen points at one."""
    assert SETUP_IDENTITY_VERSION == 1
    subject = observation(bar=0, swing_index=1)
    assert isinstance(subject.identity, str) and subject.identity


# ---------------------------------------------------------------------------
# Type guards. Each one is a field that would otherwise fail far from its cause.
# ---------------------------------------------------------------------------


def _observation_values() -> dict[str, object]:
    return {
        "market": MARKET,
        "book": Book.SWING,
        "reading": setup_reading(as_of=at(0), direction=TradeDirection.LONG),
        "version_set": version_set(),
    }


@pytest.mark.parametrize(
    "field, value",
    [
        ("market", "BTCUSDT"),
        ("book", "swing"),
        ("reading", object()),
        ("version_set", "1.0"),
        ("setup_type", "trend-continuation"),
    ],
)
def test_the_observation_refuses_a_wrong_field_type(field: str, value: object) -> None:
    with pytest.raises(TypeError):
        SetupObservation(**{**_observation_values(), field: value})


def test_an_anchor_disagreeing_with_the_observations_book_is_refused() -> None:
    reading = setup_reading(
        as_of=at(0),
        direction=TradeDirection.LONG,
        anchor=anchor_of(
            market=MARKET,
            book=Book.PAPER,
            direction=TradeDirection.LONG,
            invalidation_origin=ref(swing_index=1),
        ),
    )
    with pytest.raises(DomainValidationError):
        SetupObservation(
            market=MARKET, book=Book.SWING, reading=reading, version_set=version_set()
        )


def _occurrence_values() -> dict[str, object]:
    subject = observation(bar=0, swing_index=1)
    return {
        "identity": subject.identity,
        "market": MARKET,
        "book": Book.SWING,
        "direction": TradeDirection.LONG,
        "anchor": subject.anchor,
        "observations": (subject,),
    }


@pytest.mark.parametrize(
    "field, value",
    [
        ("identity", 7),
        ("identity", ""),
        ("market", "BTCUSDT"),
        ("book", "swing"),
        ("direction", "long"),
        ("anchor", "an-anchor"),
        ("observations", [1]),
        ("observations", ("not an observation",)),
    ],
)
def test_the_occurrence_refuses_a_wrong_field_type(field: str, value: object) -> None:
    with pytest.raises(TypeError):
        SetupOccurrence(**{**_occurrence_values(), field: value})


# ---------------------------------------------------------------------------
# Architecture guards. §9.3 and §9.4 give both types durability
# REBUILDABLE_PROJECTION, which `fmis.persistence.kinds` refuses to store.
# ---------------------------------------------------------------------------


def test_neither_projection_is_a_persisted_record_kind() -> None:
    """No record kind was added by this milestone, and none may be."""
    from fmis.persistence.kinds import SPECS

    stored = {spec.record_type for spec in SPECS.values()}

    assert SetupObservation not in stored
    assert SetupOccurrence not in stored


def test_the_store_refuses_a_projection_outright() -> None:
    from fmis.persistence.errors import UnknownRecordKindError
    from fmis.persistence.kinds import spec_for_record

    with pytest.raises(UnknownRecordKindError):
        spec_for_record(observation(bar=0, swing_index=1))


def test_the_identity_layer_imports_no_engine() -> None:
    """The domain half stays describable without the market half.

    `tests/test_trade_domain_architecture.py` asserts this for every module in
    `fmis.proposal`; this states it for BG-D1's three specifically, so the day
    someone reaches for `SetupAssessment` here it fails with the reason attached.
    """
    import fmis.proposal.observation as observation_module
    import fmis.proposal.occurrence as occurrence_module
    import fmis.proposal.setup_identity as identity_module

    market_half = ("swing_setup", "level_crossing", "market_structure", "features")
    for module in (identity_module, observation_module, occurrence_module):
        source = module.__doc__ or ""
        imported = [
            name
            for name in dir(module)
            if any(half in str(getattr(module, name, "")) for half in market_half)
        ]
        assert imported == [], f"{module.__name__} reaches {imported}"
        assert source, "each module states why it exists"


# ---------------------------------------------------------------------------
# The composition of the key, pinned. A silent change to what identity is built
# from is a silent re-partitioning of every statistic computed over occurrences.
# ---------------------------------------------------------------------------


def test_the_origin_id_is_a_pinned_value() -> None:
    """A golden value. If this changes, every occurrence in the repository re-derives.

    That is legal — nothing frozen points at one (§23.1) — but it must be a
    deliberate edit to this line, with `SETUP_IDENTITY_VERSION` bumped alongside,
    rather than a side effect of touching the digest basis.
    """
    assert (
        stable_origin_id(
            pivot_timestamp=PIVOT, label="higher_low", confirmation_bars=3
        )
        == "749c82df9423217b"
    )


def test_the_book_participates_in_the_identity() -> None:
    """The same level in two capacity pools is two ideas, not one."""
    swing = anchor_of(
        market=MARKET,
        book=Book.SWING,
        direction=TradeDirection.LONG,
        invalidation_origin=ref(swing_index=1),
    )
    paper = anchor_of(
        market=MARKET,
        book=Book.PAPER,
        direction=TradeDirection.LONG,
        invalidation_origin=ref(swing_index=1),
    )

    assert not anchors_match(swing, paper)


def test_the_market_participates_in_the_identity() -> None:
    btc = anchor_of(
        market=MARKET,
        book=Book.SWING,
        direction=TradeDirection.LONG,
        invalidation_origin=ref(swing_index=1),
    )
    eth = anchor_of(
        market=OTHER_MARKET,
        book=Book.SWING,
        direction=TradeDirection.LONG,
        invalidation_origin=ref(swing_index=1),
    )

    assert not anchors_match(btc, eth)


def test_a_directional_bar_resets_the_gap_run() -> None:
    """Tolerance counts *consecutive* silence, not silence in total.

    With a tolerance of one, `directional, wait, directional, wait, directional`
    is one occurrence: each directional bar clears the run. Accumulating the
    total instead would split it at the second `WAIT`.
    """
    observations = (
        observation(bar=0, swing_index=6),
        wait(1),
        observation(bar=2, swing_index=4),
        wait(3),
        observation(bar=4, swing_index=2),
    )

    occurrences = group_occurrences(observations, occurrence_gap_bars=1)

    assert len(occurrences) == 1
    assert occurrences[0].observation_count == 3


# ---------------------------------------------------------------------------
# Creation rule 4 — the mechanism that protects captured artifacts.
# ---------------------------------------------------------------------------


def test_admit_reaffirms_the_same_idea_across_a_sliding_window() -> None:
    """One live proposal per anchor, when the window has moved under it.

    This is the failure that mattered: `admit` compared anchors with `==`, which
    includes the window-relative `swing_index`, so a re-run one bar later would
    have created a *second* proposal for the same idea — 549 from 552, this time
    with frozen artifacts pointing at it.
    """
    from fmis.proposal import AdmissionOutcome, admit, fold_proposal_state
    from fmis.snapshotting import Anchor as AnchorType

    def anchored(swing_index: int) -> AnchorType:
        return anchor_of(
            market=MARKET,
            book=Book.SWING,
            direction=TradeDirection.LONG,
            invalidation_origin=ref(swing_index=swing_index),
        )

    from trade_domain_helpers import AT, proposal

    def at_index(swing_index: int):
        origin = ref(swing_index=swing_index)
        return proposal(
            anchor=anchored(swing_index), invalidation=level(origin=origin)
        )

    existing = at_index(40)
    candidate = at_index(12)
    assert existing.anchor != candidate.anchor, "the fixture must exercise the defect"

    admission = admit(
        candidate,
        [(existing, fold_proposal_state(existing, ()))],
        occurred_at=AT(10),
        recorded_at=AT(10),
        causing_close_time=AT(10),
    )

    assert admission.outcome is AdmissionOutcome.REAFFIRMED
    assert admission.proposal is existing


def test_admit_still_creates_for_a_genuinely_different_idea() -> None:
    """Reaffirmation must not swallow a new idea — the opposite failure."""
    from fmis.proposal import AdmissionOutcome, admit, fold_proposal_state
    from trade_domain_helpers import AT, proposal

    def anchored_on(origin):
        return proposal(
            anchor=anchor_of(
                market=MARKET,
                book=Book.SWING,
                direction=TradeDirection.LONG,
                invalidation_origin=origin,
            ),
            invalidation=level(origin=origin),
        )

    existing = anchored_on(ref(swing_index=40))
    candidate = anchored_on(ref(swing_index=12, pivot=PIVOT - timedelta(days=2)))

    admission = admit(
        candidate,
        [(existing, fold_proposal_state(existing, ()))],
        occurred_at=AT(10),
        recorded_at=AT(10),
        causing_close_time=AT(10),
    )

    assert admission.outcome is AdmissionOutcome.CREATED
