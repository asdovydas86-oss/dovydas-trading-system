"""The composition-root adapter: live `SetupAssessment` → domain projections.

Fully deterministic and network-free. Every fixture is built by hand; no
expectation is derived by calling the production helper it checks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.accounts import Book, MarketId, MarketMode, VenueId
from fmis.money import AssetCode
from fmis.level_crossing import LevelOrigin, LevelSide, PriceLevel
from fmis.market_structure import StructuralSwingLabel
from fmis.setup_observation import (
    SETUP_OBSERVATION_BOOK,
    STOP_TRIGGER_SEMANTICS,
    SetupIdentityRun,
    observation_from_assessment,
    observe_setup_series,
    setup_version_set,
)
from fmis.proposal import SetupObservation, SetupOccurrence, anchor_identity
from fmis.provenance import Absent
from fmis.snapshotting import LevelSideRef, TradeDirection, TriggerBasis
from fmis.swing_setup import (
    Direction,
    Probability,
    ProbabilityStatus,
    RiskReward,
    SetupAssessment,
    SetupState,
    Trigger,
    TriggerKind,
)

MARKET = MarketId(VenueId("binance"), AssetCode("BTC"), AssetCode("USDT"), MarketMode.SPOT)
OTHER_MARKET = MarketId(
    VenueId("binance"), AssetCode("ETH"), AssetCode("USDT"), MarketMode.SPOT
)
CODE = "fmits-test"
PIVOT = datetime(2026, 6, 1, tzinfo=timezone.utc)
START = datetime(2026, 8, 1, tzinfo=timezone.utc)
NOT_CALIBRATED = Probability(status=ProbabilityStatus.NOT_CALIBRATED, value=None)


def at(bar: int) -> datetime:
    return START + timedelta(hours=bar)


def origin(
    *, index: int, pivot: datetime = PIVOT, bars: int = 2,
    label: StructuralSwingLabel = StructuralSwingLabel.LOWER_LOW,
) -> LevelOrigin:
    return LevelOrigin(
        index=index, timestamp=pivot, label=label, confirmation_bars=bars
    )


def stop_level(*, index: int, pivot: datetime = PIVOT, price: float = 90.0) -> PriceLevel:
    return PriceLevel(
        side=LevelSide.LOWER, price=price, origin=origin(index=index, pivot=pivot)
    )


def target_level(price: float = 130.0) -> PriceLevel:
    return PriceLevel(
        side=LevelSide.UPPER,
        price=price,
        origin=origin(index=3, label=StructuralSwingLabel.HIGHER_HIGH),
    )


def assessment(
    *,
    bar: int,
    swing_index: int = 5,
    pivot: datetime = PIVOT,
    direction: Direction | None = Direction.LONG,
    state: SetupState = SetupState.CANDIDATE,
    policy_id: str = "swing-setup-v1",
    stop: PriceLevel | None = None,
    with_geometry: bool = True,
) -> SetupAssessment:
    """One live assessment. `direction=None` builds the WAIT shape."""
    if direction is None:
        return SetupAssessment(
            symbol="BTCUSDT", as_of=at(bar), objective="swing",
            state=SetupState.WAIT, direction=None, thesis=("no candidate",),
            directional_factors=(), confirmation=(), invalidation=(), trigger=None,
            reference_price=None, stop=None, targets=(), risk_reward=None,
            probability=NOT_CALIBRATED, regime_context=("context: trending",),
            sufficiency=__import__(
                "fmis.decision_context", fromlist=["ContextState"]
            ).ContextState.SUFFICIENT,
            limitations=("X-1: none",), policy_id=policy_id, source="fixture",
        )
    from fmis.decision_context import ContextState

    chosen_stop = stop if stop is not None else stop_level(index=swing_index, pivot=pivot)
    targets = (target_level(),) if with_geometry else ()
    risk_reward = (
        RiskReward(entry=100.0, stop=90.0, target=130.0, risk=10.0, reward=30.0, ratio=3.0)
        if with_geometry
        else None
    )
    return SetupAssessment(
        symbol="BTCUSDT", as_of=at(bar), objective="swing", state=state,
        direction=direction, thesis=("trend continuation retest",),
        directional_factors=(), confirmation=("awaiting confirmation",),
        invalidation=("structural invalidation",),
        trigger=Trigger(kind=TriggerKind.AWAITING_STRUCTURE_BREAK, statement="awaiting"),
        reference_price=100.0, stop=chosen_stop, targets=targets,
        risk_reward=risk_reward, probability=NOT_CALIBRATED,
        regime_context=("context: trending",), sufficiency=ContextState.SUFFICIENT,
        limitations=("X-1: none",), policy_id=policy_id, source="fixture",
    )


def observed(**kwargs) -> SetupObservation:
    return observation_from_assessment(
        assessment(**kwargs), market=MARKET, code_version=CODE
    )


# ---------------------------------------------------------------------------
# The mapping
# ---------------------------------------------------------------------------


def test_the_adapter_produces_a_projection_not_a_record() -> None:
    subject = observed(bar=0)

    assert isinstance(subject, SetupObservation)
    assert not hasattr(subject, "to_payload")
    assert isinstance(subject.setup_type, Absent)


def test_the_reading_carries_the_engines_own_facts_unchanged() -> None:
    subject = observed(bar=0, state=SetupState.CONFIRMED)
    reading = subject.reading

    assert reading.as_of == at(0)
    assert reading.state == "confirmed"
    assert reading.direction is TradeDirection.LONG
    assert reading.policy_id == "swing-setup-v1"
    assert reading.thesis == "trend continuation retest"
    assert reading.reference_price == Decimal("100")
    assert reading.limitations == ("X-1: none",)
    assert reading.probability == "not_calibrated"


def test_the_stop_crosses_to_an_exact_decimal_through_the_one_conversion() -> None:
    reading = observed(bar=0).reading

    assert reading.stop.price == Decimal("90")
    assert reading.stop.side is LevelSideRef.BELOW
    assert reading.risk_reward.risk_distance == Decimal("10")
    assert reading.risk_reward.reward_distance == Decimal("30")


def test_the_stop_and_the_invalidation_are_the_same_level() -> None:
    """`BD` R-13: one price, two trigger semantics."""
    reading = observed(bar=0).reading

    assert reading.stop == reading.invalidation
    assert STOP_TRIGGER_SEMANTICS.stop_basis is TriggerBasis.TOUCH
    assert STOP_TRIGGER_SEMANTICS.invalidation_basis is TriggerBasis.CLOSE
    assert reading.stop_trigger_semantics is STOP_TRIGGER_SEMANTICS


def test_the_default_book_is_the_swing_book() -> None:
    assert SETUP_OBSERVATION_BOOK is Book.SWING
    assert observed(bar=0).book is Book.SWING


def test_the_book_is_a_parameter() -> None:
    subject = observation_from_assessment(
        assessment(bar=0), market=MARKET, code_version=CODE, book=Book.PAPER
    )

    assert subject.book is Book.PAPER
    assert subject.anchor.book is Book.PAPER


def test_freshness_is_absent_with_a_reason_rather_than_invented() -> None:
    freshness = observed(bar=0).reading.freshness

    assert freshness.measured_at == at(0)
    for age in (freshness.context_bars, freshness.setup_bars, freshness.execution_bars):
        assert isinstance(age, Absent)
        assert "computes no bar age" in age.reason


def test_a_wait_reading_carries_no_anchor_and_no_geometry() -> None:
    subject = observed(bar=0, direction=None)

    assert subject.reading.direction is TradeDirection.NO_TRADE
    assert isinstance(subject.anchor, Absent)
    assert isinstance(subject.identity, Absent)
    assert isinstance(subject.reading.stop, Absent)
    assert isinstance(subject.reading.risk_reward, Absent)


def test_a_stop_without_provenance_yields_no_anchor() -> None:
    """ADR-0019 D2: a level from the earliest, unlabelled swing has no origin."""
    subject = observation_from_assessment(
        assessment(bar=0, stop=PriceLevel(side=LevelSide.LOWER, price=90.0, origin=None)),
        market=MARKET,
        code_version=CODE,
    )

    assert isinstance(subject.anchor, Absent)
    assert "MEASURED level origin" in subject.anchor.reason


def test_the_short_side_maps_across(  ) -> None:
    short_stop = PriceLevel(
        side=LevelSide.UPPER,
        price=110.0,
        origin=origin(index=5, label=StructuralSwingLabel.HIGHER_HIGH),
    )
    subject = observation_from_assessment(
        assessment(bar=0, direction=Direction.SHORT, stop=short_stop, with_geometry=False),
        market=MARKET,
        code_version=CODE,
    )

    assert subject.reading.direction is TradeDirection.SHORT
    assert subject.anchor.direction is TradeDirection.SHORT
    assert subject.reading.stop.side is LevelSideRef.ABOVE


def test_the_version_set_records_the_policy_without_identity_reading_it() -> None:
    subject = observed(bar=0)

    assert subject.version_set == setup_version_set(
        code_version=CODE, policy_id="swing-setup-v1"
    )


@pytest.mark.parametrize("bad", ["an assessment", 7, None])
def test_a_non_assessment_is_refused(bad: object) -> None:
    with pytest.raises(TypeError):
        observation_from_assessment(bad, market=MARKET, code_version=CODE)


def test_a_non_market_is_refused() -> None:
    with pytest.raises(TypeError):
        observation_from_assessment(assessment(bar=0), market="BTCUSDT", code_version=CODE)


def test_a_non_book_is_refused() -> None:
    with pytest.raises(TypeError):
        observation_from_assessment(
            assessment(bar=0), market=MARKET, code_version=CODE, book="swing"
        )


# ---------------------------------------------------------------------------
# Requirement 6 — the properties this milestone exists to guarantee
# ---------------------------------------------------------------------------


def test_one_setup_across_many_bars_is_one_occurrence() -> None:
    run = observe_setup_series(
        [assessment(bar=bar, swing_index=5) for bar in range(40)],
        market=MARKET, code_version=CODE, occurrence_gap_bars=0,
    )

    assert len(run.occurrences) == 1
    assert run.occurrences[0].observation_count == 40


def test_a_sliding_window_does_not_create_new_identities() -> None:
    """The same pivot, seen from windows that place it at 39 different indices."""
    assessments = [assessment(bar=bar, swing_index=39 - bar) for bar in range(40)]
    indices = {a.stop.origin.index for a in assessments}
    assert len(indices) == 40, "the fixture must exercise the defect"

    run = observe_setup_series(
        assessments, market=MARKET, code_version=CODE, occurrence_gap_bars=0
    )

    assert len(run.occurrences) == 1
    identities = {o.identity for o in run.observations}
    assert len(identities) == 1


def test_the_swing_index_survives_as_provenance() -> None:
    """Excluded from identity, still carried on the reading."""
    first = observed(bar=0, swing_index=39)
    last = observed(bar=39, swing_index=0)

    assert first.reading.stop.origin.swing_index == 39
    assert last.reading.stop.origin.swing_index == 0
    assert first.identity == last.identity


def test_a_new_structural_anchor_starts_a_new_occurrence() -> None:
    run = observe_setup_series(
        [
            assessment(bar=0, swing_index=5),
            assessment(bar=1, swing_index=5),
            assessment(bar=2, swing_index=5, pivot=PIVOT + timedelta(days=3)),
        ],
        market=MARKET, code_version=CODE, occurrence_gap_bars=5,
    )

    assert len(run.occurrences) == 2
    assert run.occurrences[0].observation_count == 2
    assert run.occurrences[1].observation_count == 1


def test_a_direction_flip_starts_a_new_occurrence() -> None:
    short_stop = PriceLevel(
        side=LevelSide.UPPER, price=110.0,
        origin=origin(index=5, label=StructuralSwingLabel.HIGHER_HIGH),
    )
    run = observe_setup_series(
        [
            assessment(bar=0),
            assessment(bar=1, direction=Direction.SHORT, stop=short_stop, with_geometry=False),
        ],
        market=MARKET, code_version=CODE, occurrence_gap_bars=5,
    )

    assert len(run.occurrences) == 2
    assert run.occurrences[0].direction is TradeDirection.LONG
    assert run.occurrences[1].direction is TradeDirection.SHORT


def test_a_deterministic_rerun_produces_identical_identities() -> None:
    assessments = [assessment(bar=bar, swing_index=9 - bar) for bar in range(9)]

    first = observe_setup_series(
        assessments, market=MARKET, code_version=CODE, occurrence_gap_bars=1
    )
    second = observe_setup_series(
        assessments, market=MARKET, code_version=CODE, occurrence_gap_bars=1
    )

    assert first == second
    assert [o.identity for o in first.occurrences] == [
        o.identity for o in second.occurrences
    ]


def test_a_policy_version_change_does_not_rewrite_identity() -> None:
    baseline = observed(bar=0, swing_index=5)
    variant = observed(bar=0, swing_index=5, policy_id="swing-setup-v2-experimental")

    assert variant.reading.policy_id == "swing-setup-v2-experimental"
    assert variant.version_set != baseline.version_set
    assert variant.identity == baseline.identity


def test_no_lookahead_a_prefix_yields_a_prefix_of_the_same_identities() -> None:
    """Grouping never reads an observation later than the one it is placing."""
    assessments = [
        assessment(bar=bar, swing_index=20 - bar, pivot=PIVOT + timedelta(days=bar // 5))
        for bar in range(20)
    ]
    full = observe_setup_series(
        assessments, market=MARKET, code_version=CODE, occurrence_gap_bars=2
    )
    full_identities = [o.identity for o in full.occurrences]

    for cut in range(1, len(assessments) + 1):
        partial = observe_setup_series(
            assessments[:cut], market=MARKET, code_version=CODE, occurrence_gap_bars=2
        )
        partial_identities = [o.identity for o in partial.occurrences]
        assert partial_identities == full_identities[: len(partial_identities)], (
            f"a {cut}-bar prefix disagreed with the full run"
        )


def test_an_observation_never_depends_on_a_later_one() -> None:
    """Each reading is a pure function of its own assessment."""
    alone = observation_from_assessment(
        assessment(bar=3, swing_index=5), market=MARKET, code_version=CODE
    )
    in_series = observe_setup_series(
        [assessment(bar=bar, swing_index=5) for bar in range(9)],
        market=MARKET, code_version=CODE, occurrence_gap_bars=0,
    ).observations[3]

    assert alone == in_series


# ---------------------------------------------------------------------------
# Requirement 3 — what a future surface reads
# ---------------------------------------------------------------------------


def test_the_run_distinguishes_a_repeat_from_a_new_occurrence() -> None:
    assessments = [assessment(bar=bar, swing_index=5) for bar in range(3)]

    first = observe_setup_series(
        assessments[:1], market=MARKET, code_version=CODE, occurrence_gap_bars=0
    )
    third = observe_setup_series(
        assessments, market=MARKET, code_version=CODE, occurrence_gap_bars=0
    )

    assert first.is_new_occurrence
    assert first.repeated_observation_count == 1
    assert not third.is_new_occurrence
    assert third.repeated_observation_count == 3


def test_a_run_with_no_directional_reading_says_so() -> None:
    run = observe_setup_series(
        [assessment(bar=0, direction=None)],
        market=MARKET, code_version=CODE, occurrence_gap_bars=0,
    )

    assert isinstance(run.latest_occurrence, Absent)
    assert not run.is_new_occurrence
    assert run.repeated_observation_count == 0


def test_an_empty_series_is_an_empty_run() -> None:
    run = observe_setup_series(
        [], market=MARKET, code_version=CODE, occurrence_gap_bars=0
    )

    assert run.observations == ()
    assert run.occurrences == ()
    assert isinstance(run.latest_occurrence, Absent)


def test_the_run_carries_the_parameter_it_grouped_under() -> None:
    run = observe_setup_series(
        [assessment(bar=0)], market=MARKET, code_version=CODE, occurrence_gap_bars=4
    )

    assert run.occurrence_gap_bars == 4
    assert isinstance(run, SetupIdentityRun)


def test_the_gap_parameter_is_required() -> None:
    with pytest.raises(TypeError):
        observe_setup_series([assessment(bar=0)], market=MARKET, code_version=CODE)


# ---------------------------------------------------------------------------
# Persistence and boundary guards
# ---------------------------------------------------------------------------


def test_the_adapter_adds_no_record_kind() -> None:
    from fmis.persistence.kinds import SPECS

    stored = {spec.record_type for spec in SPECS.values()}

    assert len(SPECS) == 15
    assert SetupObservation not in stored
    assert SetupOccurrence not in stored
    assert SetupIdentityRun not in stored


def test_the_store_refuses_everything_this_module_produces() -> None:
    from fmis.persistence.errors import UnknownRecordKindError
    from fmis.persistence.kinds import spec_for_record

    run = observe_setup_series(
        [assessment(bar=0)], market=MARKET, code_version=CODE, occurrence_gap_bars=0
    )
    for value in (run, run.observations[0], run.occurrences[0]):
        with pytest.raises(UnknownRecordKindError):
            spec_for_record(value)


def test_a_captured_artifact_never_references_a_derived_occurrence_key() -> None:
    """§23.1. The proposal cites the `MEASURED` anchor, never the grouping key."""
    from fmis.proposal import OpportunityProposal

    run = observe_setup_series(
        [assessment(bar=0)], market=MARKET, code_version=CODE, occurrence_gap_bars=0
    )
    derived_key = run.occurrences[0].identity

    fields = OpportunityProposal.__dataclass_fields__
    assert "occurrence_id" not in fields
    assert "setup_occurrence" not in fields
    assert "occurrence" not in fields
    # The anchor a proposal may cite is the MEASURED fact, and it is not the key.
    assert derived_key != run.observations[0].anchor.invalidation_origin.origin_id


def test_the_adapter_contains_no_arithmetic_of_its_own() -> None:
    """The composition-root rule: a number produced here answers to no engine.

    AST-based, matching `fmis.decision_support`'s own guard. `Add` is excluded
    because tuple and string concatenation use it; the remaining operators cannot
    be sequence operations, and no ratio, difference or average can be built
    without one of them.
    """
    import ast
    import pathlib as _pathlib

    import fmis.setup_observation.observe as module

    tree = ast.parse(_pathlib.Path(module.__file__).read_text())
    operators = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp)
        and isinstance(
            node.op, (ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Pow, ast.Mod)
        )
    ]

    assert operators == [], "the adapter computes something"


# ---------------------------------------------------------------------------
# Requirement 6 — live admission deduplication uses stable anchor semantics
# ---------------------------------------------------------------------------


def test_admission_deduplicates_an_adapter_built_anchor_across_a_window_slide() -> None:
    """The end-to-end claim: a re-run one bar later reaffirms, it does not duplicate."""
    from fmis.proposal import AdmissionOutcome, admit, fold_proposal_state
    from trade_domain_helpers import AT, level, proposal

    early = observed(bar=0, swing_index=39)
    later = observed(bar=39, swing_index=0)
    assert early.anchor != later.anchor, "the fixture must exercise the defect"

    def as_proposal(subject: SetupObservation):
        return proposal(
            market=MARKET,
            anchor=subject.anchor,
            invalidation=level(origin=subject.anchor.invalidation_origin),
        )

    existing = as_proposal(early)
    candidate = as_proposal(later)

    admission = admit(
        candidate,
        [(existing, fold_proposal_state(existing, ()))],
        occurred_at=AT(10), recorded_at=AT(10), causing_close_time=AT(10),
    )

    assert admission.outcome is AdmissionOutcome.REAFFIRMED
    assert admission.proposal is existing


def test_admission_still_creates_when_the_adapter_reports_a_new_anchor() -> None:
    from fmis.proposal import AdmissionOutcome, admit, fold_proposal_state
    from trade_domain_helpers import AT, level, proposal

    early = observed(bar=0, swing_index=5)
    moved = observed(bar=1, swing_index=5, pivot=PIVOT + timedelta(days=3))

    def as_proposal(subject: SetupObservation):
        return proposal(
            market=MARKET,
            anchor=subject.anchor,
            invalidation=level(origin=subject.anchor.invalidation_origin),
        )

    existing = as_proposal(early)
    admission = admit(
        as_proposal(moved),
        [(existing, fold_proposal_state(existing, ()))],
        occurred_at=AT(10), recorded_at=AT(10), causing_close_time=AT(10),
    )

    assert admission.outcome is AdmissionOutcome.CREATED


def test_the_adapter_anchor_agrees_with_the_domain_identity_rule() -> None:
    early = observed(bar=0, swing_index=39)
    later = observed(bar=39, swing_index=0)

    assert anchor_identity(early.anchor) == anchor_identity(later.anchor)
    assert early.identity == anchor_identity(early.anchor)


def test_the_adapter_is_not_re_exported_from_the_pipeline_package() -> None:
    """Re-exporting it closes an import cycle. Proven, not asserted from memory.

    `fmis.pipeline.__init__` importing this module pulls `fmis.accounts` and with
    it `money → records → archive → daily → workspace → decision_support`, and
    `fmis.decision_support` imports `fmis.pipeline`. Exporting it was tried and
    raised `ImportError: cannot import name 'EvidenceReport' from partially
    initialized module 'fmis.decision_support'`.
    """
    import fmis.pipeline as package

    for name in (
        "observe_setup_series",
        "observation_from_assessment",
        "SetupIdentityRun",
    ):
        assert name not in package.__all__, (
            f"{name} is re-exported from fmis.pipeline; that closes an import cycle"
        )


def test_the_market_half_still_imports_without_the_domain_half() -> None:
    """The package init must stay free of `fmis.accounts` and everything under it."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", "import fmis.pipeline, sys; "
         "assert 'fmis.accounts' not in sys.modules, sorted(sys.modules)"],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "first, second",
    [
        ("fmis.swing_setup", "fmis.setup_observation.observe"),
        ("fmis.setup_observation.observe", "fmis.swing_setup"),
        ("fmis.decision_support", "fmis.setup_observation.observe"),
        ("fmis.persistence", "fmis.setup_observation.observe"),
    ],
)
def test_the_adapter_imports_cleanly_in_either_order(first: str, second: str) -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", f"import {first}; import {second}"],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr


def test_the_adapter_names_no_direction_and_needs_no_exemption() -> None:
    """ADR-0028 §5. This composition root translates a side; it never decides one.

    The mapping is derived from `Direction`'s own members, so the adapter needed
    no entry in `test_directional_vocabulary_boundary`'s permitted lists — the
    guard passes over it unchanged.
    """
    import ast
    import pathlib as _pathlib

    import fmis.setup_observation.observe as module

    banned = {"long", "short", "buy", "sell", "bullish", "bearish"}
    tree = ast.parse(_pathlib.Path(module.__file__).read_text())
    tokens = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            tokens.append(node.attr)
        elif isinstance(node, ast.Name):
            tokens.append(node.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            tokens.append(node.value)

    assert [t for t in tokens if t.lower() in banned] == []


def test_the_direction_map_is_total_over_the_engines_vocabulary() -> None:
    """A third member in either vocabulary must fail loudly, not map to nothing."""
    from fmis.setup_observation.observe import _DIRECTIONS

    assert set(_DIRECTIONS) == set(Direction)
    for engine_member, domain_member in _DIRECTIONS.items():
        assert engine_member.value == domain_member.value
        assert domain_member.is_directional


# ---------------------------------------------------------------------------
# Gaps found by mutation testing.
# ---------------------------------------------------------------------------


def test_the_confirmation_window_reaches_the_identity() -> None:
    """ADR-0024: a level under a different confirmation window is a different level."""
    two_bar = observation_from_assessment(
        assessment(bar=0, stop=PriceLevel(
            side=LevelSide.LOWER, price=90.0, origin=origin(index=5, bars=2))),
        market=MARKET, code_version=CODE,
    )
    five_bar = observation_from_assessment(
        assessment(bar=0, stop=PriceLevel(
            side=LevelSide.LOWER, price=90.0, origin=origin(index=5, bars=5))),
        market=MARKET, code_version=CODE,
    )

    assert two_bar.reading.stop.origin.confirmation_bars == 2
    assert five_bar.reading.stop.origin.confirmation_bars == 5
    assert two_bar.identity != five_bar.identity


def test_the_pivot_instant_reaches_the_identity() -> None:
    """The one fact identity is actually built from."""
    early = observed(bar=0, swing_index=5, pivot=PIVOT)
    late = observed(bar=0, swing_index=5, pivot=PIVOT + timedelta(minutes=1))

    assert early.identity != late.identity


def test_the_market_reaches_the_identity() -> None:
    btc = observation_from_assessment(
        assessment(bar=0), market=MARKET, code_version=CODE
    )
    eth = observation_from_assessment(
        assessment(bar=0), market=OTHER_MARKET, code_version=CODE
    )

    assert btc.anchor.market == MARKET
    assert eth.anchor.market == OTHER_MARKET
    assert btc.identity != eth.identity


def test_a_target_without_provenance_is_dropped_rather_than_fabricated() -> None:
    """ADR-0019 D2 again: no origin, no `LevelReading` — and no invented one."""
    subject = observation_from_assessment(
        assessment(
            bar=0,
            stop=stop_level(index=5),
        ),
        market=MARKET,
        code_version=CODE,
    )
    assert len(subject.reading.targets) == 1

    from dataclasses import replace

    # A stop and a target together make risk/reward mandatory on the engine's
    # own model, so only the target's provenance is removed.
    unprovenanced = replace(
        assessment(bar=0),
        targets=(PriceLevel(side=LevelSide.UPPER, price=130.0, origin=None),),
    )
    dropped = observation_from_assessment(
        unprovenanced, market=MARKET, code_version=CODE
    )

    assert dropped.reading.targets == ()


def test_the_gap_parameter_reaches_the_grouping() -> None:
    """Same series, two tolerances, two answers — so the value is not ignored."""
    series = [
        assessment(bar=0, swing_index=5),
        assessment(bar=1, direction=None),
        assessment(bar=2, swing_index=5),
    ]

    strict = observe_setup_series(
        series, market=MARKET, code_version=CODE, occurrence_gap_bars=0
    )
    tolerant = observe_setup_series(
        series, market=MARKET, code_version=CODE, occurrence_gap_bars=1
    )

    assert len(strict.occurrences) == 2
    assert len(tolerant.occurrences) == 1
    assert tolerant.occurrences[0].observation_count == 2


def test_the_latest_occurrence_is_the_most_recent_one() -> None:
    run = observe_setup_series(
        [
            assessment(bar=0, swing_index=5),
            assessment(bar=1, swing_index=5),
            assessment(bar=2, swing_index=5, pivot=PIVOT + timedelta(days=3)),
        ],
        market=MARKET, code_version=CODE, occurrence_gap_bars=5,
    )

    assert len(run.occurrences) == 2
    assert run.latest_occurrence is run.occurrences[1]
    assert run.latest_occurrence.began_at == at(2)
    assert run.is_new_occurrence


def test_the_pivot_year_reaches_the_identity() -> None:
    """Every component of the instant counts, not only month and day."""
    this_year = observed(bar=0, swing_index=5, pivot=PIVOT)
    last_year = observed(
        bar=0, swing_index=5, pivot=PIVOT.replace(year=PIVOT.year - 1)
    )

    assert this_year.identity != last_year.identity


def test_a_wait_assessment_can_never_carry_a_stop_to_anchor_on() -> None:
    """Why the `is_directional` guard in the adapter is belt-and-braces.

    `SetupAssessment` refuses a WAIT result that carries a stop, so the anchor
    branch is unreachable for a non-directional reading by the engine's own
    construction. The guard stays because a future third direction member must
    not silently acquire an anchor.
    """
    from fmis.swing_setup.models import SwingSetupError

    with pytest.raises(SwingSetupError):
        SetupAssessment(
            symbol="BTCUSDT", as_of=at(0), objective="swing", state=SetupState.WAIT,
            direction=None, thesis=("no candidate",), directional_factors=(),
            confirmation=(), invalidation=(), trigger=None, reference_price=None,
            stop=stop_level(index=5), targets=(), risk_reward=None,
            probability=NOT_CALIBRATED, regime_context=("context: trending",),
            sufficiency=__import__(
                "fmis.decision_context", fromlist=["ContextState"]
            ).ContextState.SUFFICIENT,
            limitations=("X-1: none",), policy_id="swing-setup-v1", source="fixture",
        )
