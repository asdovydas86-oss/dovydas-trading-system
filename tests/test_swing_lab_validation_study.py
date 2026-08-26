"""Study orchestration, from hand-built captures. **No history is replayed here.**

Following `tests.test_swing_lab_geometry_study`'s method: a `GeometryCapture` is
assembled from hand-made candidates and a hand-made bar array, which is what
lets the whole orchestration be exercised — including cases real data would not
offer on demand, such as a holdout that was never opened, a sample whose window
claims nothing, and a substituted pre-registration.

**The substitution deserves its own note.** `run_validation_study` accepts a
`Preregistration` other than the sealed one, because refusing would leave this
file unable to test anything and untestable orchestration is the worse failure.
What it does *not* do is let a substituted manifest promote anything: the
`pre_registered` criterion reads both the digest match and the sealed policy-id
set, so a fixture study is always blocked. That is asserted below, twice.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.paper.models import PriceBar
from fmis.swing_lab.geometry_replay import GeometryCapture
from fmis.swing_lab.models import LabVerdict, SwingLabError
from fmis.swing_lab.preregistration import (
    DECIDING_COST_POLICY_ID,
    PRE_REGISTRATION,
    SampleRole,
    SampleSpec,
)
from fmis.swing_lab.validation_study import (
    MAJOR_SYMBOLS,
    VALIDATION_LIMITATIONS,
    WALK_FORWARD_MONTHS,
    decompose,
    narrow_to_sample,
    run_validation_study,
    validation_digest,
    walk_forward,
)

from tests.swing_lab_helpers import candidate
from tests.test_swing_lab_metrics import many

_UTC = timezone.utc
_T0 = datetime(2024, 1, 1, tzinfo=_UTC)
_RUN_AT = datetime(2026, 8, 25, tzinfo=_UTC)
_WINDOW = 20

DEV_SYMBOLS = ("BTCUSDT", "ETHUSDT")
HOLD_SYMBOLS = ("DOGEUSDT",)


def _bars(symbol: str, count: int = 80) -> tuple[PriceBar, ...]:
    """A path that drifts up steadily — a LONG reaches its target, a SHORT stops out."""
    return tuple(
        PriceBar(
            symbol=symbol, interval="4h",
            open_time=_T0 + timedelta(hours=4 * index),
            open=Decimal(f"{100 + index * 0.5:.4f}"),
            high=Decimal(f"{101 + index * 0.5:.4f}"),
            low=Decimal(f"{99.5 + index * 0.5:.4f}"),
            close=Decimal(f"{100.4 + index * 0.5:.4f}"),
        )
        for index in range(count)
    )


def _fixture_samples() -> tuple[SampleSpec, ...]:
    """Three disjoint specs over the fixture's own symbols and instants."""
    return (
        SampleSpec(
            name="development", role=SampleRole.DEVELOPMENT, symbols=DEV_SYMBOLS,
            signal_start=_T0, signal_end=_T0 + timedelta(days=30),
            contamination="fixture — CONTAMINATED BY CONSTRUCTION",
        ),
        SampleSpec(
            name="validation", role=SampleRole.VALIDATION, symbols=DEV_SYMBOLS,
            signal_start=_T0 + timedelta(days=30), signal_end=_T0 + timedelta(days=60),
            contamination="fixture — SEMI-CONTAMINATED",
        ),
        SampleSpec(
            name="holdout", role=SampleRole.HOLDOUT, symbols=HOLD_SYMBOLS,
            signal_start=_T0, signal_end=_T0 + timedelta(days=60),
            contamination="fixture — THE HOLDOUT",
        ),
    )


def _fixture_prereg():
    return replace(PRE_REGISTRATION, samples=_fixture_samples())


def _candidates(symbol: str, count: int, *, day_offset: int = 0):
    return [
        candidate(
            symbol=symbol,
            setup_id=f"{symbol}|long|seq{day_offset}-{index}",
            signal_index=index,
            signal_at=_T0 + timedelta(days=day_offset, hours=index),
        )
        for index in range(count)
    ]


def _primary_capture() -> GeometryCapture:
    people = []
    for symbol in DEV_SYMBOLS:
        people += _candidates(symbol, 22, day_offset=1)      # development
        people += _candidates(symbol, 22, day_offset=35)     # validation
    return GeometryCapture(
        admission_variant_id="swing_current",
        admission_policy_id="swing-setup-v1",
        candidates=tuple(people),
        bars_by_symbol={symbol: _bars(symbol) for symbol in DEV_SYMBOLS},
        metadata={"measured_instants": 1000},
    )


def _holdout_capture() -> GeometryCapture:
    return GeometryCapture(
        admission_variant_id="swing_current",
        admission_policy_id="swing-setup-v1",
        candidates=tuple(_candidates("DOGEUSDT", 25, day_offset=5)),
        bars_by_symbol={"DOGEUSDT": _bars("DOGEUSDT")},
        metadata={"measured_instants": 500},
    )


def _study(*, holdout=True, prereg=None):
    return run_validation_study(
        _primary_capture(),
        holdout=_holdout_capture() if holdout else None,
        experiment_id="fixture",
        run_at=_RUN_AT,
        evaluation_window_bars=_WINDOW,
        candle_limit=200,
        no_lookahead_proven=True,
        preregistration=prereg or _fixture_prereg(),
    )


# --------------------------------------------------------------- sampling ---


def test_narrowing_selects_the_same_objects_and_never_recomputes() -> None:
    """Two samples cut from one replay must see byte-identical candidates."""
    capture = _primary_capture()
    spec = _fixture_samples()[0]
    cut = narrow_to_sample(capture, spec)
    originals = {id(item) for item in capture.candidates}
    assert cut.candidates
    assert all(id(item) in originals for item in cut.candidates)


def test_narrowing_cuts_by_symbol_AND_date() -> None:
    capture = _primary_capture()
    development, validation, _ = _fixture_samples()
    dev = narrow_to_sample(capture, development).candidates
    val = narrow_to_sample(capture, validation).candidates
    assert dev and val
    assert not {c.setup_id for c in dev} & {c.setup_id for c in val}


def test_narrowing_never_truncates_the_bars_in_time() -> None:
    """A trade opened on a sample's last day must still resolve over later bars.

    The spec here ends **inside** the bar array on purpose. A fixture whose
    sample boundary already sits past the final bar cannot tell a faithful
    narrowing from one that truncates at the boundary, and the first version of
    this test could not: a mutation clipping the bars survived it.
    """
    capture = _primary_capture()
    bars = capture.bars_by_symbol["BTCUSDT"]
    midpoint = bars[len(bars) // 2].open_time
    spec = replace(_fixture_samples()[0], signal_end=midpoint)
    cut = narrow_to_sample(capture, spec)
    assert cut.bars_by_symbol["BTCUSDT"] == bars
    assert cut.bars_by_symbol["BTCUSDT"][-1].open_time > spec.signal_end


def test_a_sample_claiming_no_candidates_is_refused_not_reported_as_zero() -> None:
    """An empty sample is a window-boundary error, and reporting it as 0 hides that."""
    empty = replace(
        _fixture_prereg(),
        samples=(
            replace(
                _fixture_samples()[0],
                signal_start=_T0 - timedelta(days=400),
                signal_end=_T0 - timedelta(days=300),
            ),
            *_fixture_samples()[1:],
        ),
    )
    with pytest.raises(SwingLabError, match="claims no candidates"):
        _study(prereg=empty)


# ------------------------------------------------------------ the verdict ---


def test_a_substituted_pre_registration_can_promote_nothing() -> None:
    """**The containment.** A fixture study runs, reports, and promotes nothing."""
    study = _study()
    assert study.candidates == ()
    assert study.manifest.preregistration_digest_matches is False
    for item in study.policies:
        blockers = {criterion.name for criterion in item.assessment.blocking}
        assert "pre_registered" in blockers, item.policy_id


def test_the_manifest_records_the_seal_it_actually_ran_under() -> None:
    study = _study()
    assert study.manifest.preregistration_id == PRE_REGISTRATION.preregistration_id
    assert len(study.manifest.preregistration_digest) == 64


def test_a_closed_holdout_leaves_every_holdout_criterion_unevaluable() -> None:
    """The development pass. It must be incapable of producing a candidate."""
    study = _study(holdout=False)
    assert study.manifest.holdout_candidate_count == 0
    for item in study.policies:
        criterion = next(
            c for c in item.assessment.criteria if c.name == "holdout_sample"
        )
        assert criterion.passed is None
        assert item.assessment.verdict is not LabVerdict.CANDIDATE_FOR_FORWARD_TEST


def test_a_closed_holdout_still_emits_every_sample_cell() -> None:
    """A renderer must never have to guess whether a cell exists."""
    study = _study(holdout=False)
    for item in study.policies:
        for sample in ("development", "validation", "holdout"):
            for cost in study.manifest.cost_policy_ids:
                assert item.measurement(sample, cost) is not None


# --------------------------------------------------------------- scenarios ---


def test_every_policy_is_measured_under_every_cost_scenario() -> None:
    study = _study()
    for item in study.policies:
        cells = {(m.sample, m.cost_policy_id) for m in item.measurements}
        assert len(cells) == 3 * len(study.manifest.cost_policy_ids)


def test_a_cost_scenario_changes_only_the_cost_and_never_the_path() -> None:
    """The identity that makes a scenario comparison honest.

    Both halves are asserted. The path must be **identical** — same fills, same
    exit reason, same gross R, same excursions — AND the net figure must
    **differ**, because a scenario that changed nothing at all would let a study
    print three columns of the frictionless number under three headings.
    """
    study = _study()
    item = study.policies[0]
    scenarios = study.manifest.cost_policy_ids
    first = item.measurement("development", scenarios[0]).trades
    second = item.measurement("development", scenarios[1]).trades
    assert len(first) == len(second)
    differed = 0
    for a, b in zip(first, second, strict=True):
        assert (a.entry_price, a.exit_price, a.exit_reason, a.bars_held) == (
            b.entry_price, b.exit_price, b.exit_reason, b.bars_held
        )
        assert a.gross_r == b.gross_r
        assert a.mfe_r == b.mfe_r and a.mae_r == b.mae_r
        assert a.cost_policy_id != b.cost_policy_id
        if a.net_r is not None and b.net_r is not None and a.net_r != b.net_r:
            differed += 1
    assert differed, (
        "no trade's net R moved between the frictionless and costed scenarios; "
        "the cost model is not being applied"
    )


def test_the_costed_expectancy_is_worse_than_the_frictionless_one() -> None:
    """Friction can only subtract. A costed column equal to the free one is a bug."""
    study = _study()
    scenarios = study.manifest.cost_policy_ids
    for item in study.policies:
        free = item.measurement("development", scenarios[0]).metrics.expectancy_r.value
        costed = item.measurement("development", scenarios[1]).metrics.expectancy_r.value
        if free is None or costed is None:
            continue
        assert costed < free, item.policy_id


def test_the_verdict_is_decided_on_the_costed_scenario_never_the_frictionless_one() -> None:
    study = _study()
    for item in study.policies:
        assert item.assessment.cost_policy_id == DECIDING_COST_POLICY_ID


def test_the_deciding_scenario_must_be_present() -> None:
    from fmis.swing_lab.trades import FRICTIONLESS_COSTS

    with pytest.raises(SwingLabError, match="deciding cost scenario"):
        run_validation_study(
            _primary_capture(), holdout=None, experiment_id="x", run_at=_RUN_AT,
            evaluation_window_bars=_WINDOW, candle_limit=200,
            no_lookahead_proven=True, preregistration=_fixture_prereg(),
            cost_scenarios=(FRICTIONLESS_COSTS,),
        )


# ------------------------------------------------------------- determinism ---


def test_the_result_digest_is_stable_across_runs() -> None:
    assert _study().manifest.result_digest == _study().manifest.result_digest


def test_the_result_digest_moves_when_a_trade_moves() -> None:
    study = _study()
    doctored = list(study.policies)
    original = validation_digest(tuple(doctored))
    trimmed = doctored[0]
    trimmed_measurements = tuple(
        replace(cell, trades=cell.trades[:-1]) if cell.trades else cell
        for cell in trimmed.measurements
    )
    doctored[0] = replace(trimmed, measurements=trimmed_measurements)
    assert validation_digest(tuple(doctored)) != original


def test_the_study_names_no_winner() -> None:
    """No ranking, no argmax, no 'best variant' field. A study that ranked would choose."""
    study = _study()
    assert not hasattr(study, "best")
    assert [item.policy_id for item in study.policies] == [
        item.policy_id for item in PRE_REGISTRATION.hypotheses
    ]


# ---------------------------------------------------------- walk-forward ---


def test_walk_forward_emits_empty_windows_rather_than_omitting_them() -> None:
    """A curve that drops its empty windows reads as continuous coverage."""
    # `many` stamps its trades from `tests.test_swing_lab_metrics`' own epoch,
    # 2026-01-01, so the window must cover that year rather than the fixture's.
    trades = many(5, "1")
    windows = walk_forward(
        trades, start=datetime(2026, 1, 1, tzinfo=_UTC),
        end=datetime(2027, 1, 1, tzinfo=_UTC), label="p",
    )
    assert len(windows) == 2
    assert sum(w.metrics.trades for w in windows) == 5
    assert any(w.metrics.trades == 0 for w in windows)


def test_walk_forward_assigns_each_trade_to_exactly_one_window() -> None:
    trades = many(40, "1")
    windows = walk_forward(
        trades, start=datetime(2026, 1, 1, tzinfo=_UTC),
        end=datetime(2027, 1, 1, tzinfo=_UTC), label="p",
    )
    assert sum(w.metrics.trades for w in windows) == 40


def test_walk_forward_windows_tile_the_span_without_gaps_or_overlap() -> None:
    windows = walk_forward(
        (), start=_T0, end=datetime(2026, 1, 1, tzinfo=_UTC), label="p"
    )
    for earlier, later in zip(windows, windows[1:], strict=False):
        assert earlier.end == later.start
    assert windows[0].start == _T0


def test_walk_forward_refuses_an_inverted_or_zero_span() -> None:
    with pytest.raises(SwingLabError, match="end must be after start"):
        walk_forward((), start=_T0, end=_T0, label="p")


def test_walk_forward_refuses_a_window_start_that_month_arithmetic_would_clamp() -> None:
    """A 31st start would produce unequal windows silently; it is refused instead."""
    with pytest.raises(SwingLabError, match="on or before the 28th"):
        walk_forward(
            (), start=datetime(2023, 12, 31, tzinfo=_UTC),
            end=datetime(2025, 1, 1, tzinfo=_UTC), label="p",
        )


def test_walk_forward_refuses_a_non_positive_window() -> None:
    with pytest.raises(SwingLabError, match="months must be a positive int"):
        walk_forward((), start=_T0, end=_T0 + timedelta(days=90), months=0, label="p")


def test_the_walk_forward_window_is_declared_and_not_swept() -> None:
    assert WALK_FORWARD_MONTHS == 6


# -------------------------------------------------------- decompositions ---


def test_every_required_decomposition_is_computed() -> None:
    cuts = {item.name for item in decompose(many(30, "1"))}
    assert cuts == {
        "symbol", "direction", "symbol_class", "context_regime",
        "setup_structural_trend",
    }


def test_the_symbol_class_split_separates_majors_from_the_rest() -> None:
    trades = many(15, "1", symbol="BTCUSDT") + many(15, "-1", symbol="ICXUSDT")
    cut = next(item for item in decompose(trades) if item.name == "symbol_class")
    labels = {item.label.split(":")[-1] for item in cut.cohorts}
    assert labels == {"major", "non_major"}
    assert "BTCUSDT" in MAJOR_SYMBOLS and "ICXUSDT" not in MAJOR_SYMBOLS


def test_a_cohort_below_the_floor_reports_absence_and_not_a_number() -> None:
    cut = next(item for item in decompose(many(6, "1")) if item.name == "symbol")
    assert all(item.expectancy_r.value is None for item in cut.cohorts)
    assert cut.agrees_on_sign is None


def test_disagreeing_cohorts_are_reported_as_disagreeing() -> None:
    trades = many(25, "1", symbol="BTCUSDT") + many(25, "-1", symbol="ICXUSDT")
    cut = next(item for item in decompose(trades) if item.name == "symbol")
    assert cut.agrees_on_sign is False


# -------------------------------------------------------------- reporting ---


def test_the_limitations_travel_with_every_study() -> None:
    study = _study()
    for item in VALIDATION_LIMITATIONS:
        assert item in study.manifest.limitations


def test_the_contamination_of_each_sample_is_carried_in_the_manifest() -> None:
    study = _study()
    for spec in study.manifest.samples:
        assert spec["contamination"].strip()


def test_the_sample_membership_tally_accounts_for_every_candidate() -> None:
    study = _study()
    tally = study.manifest.sample_membership
    total = tally["development"] + tally["validation"] + tally["unclaimed"]
    assert total == study.manifest.primary_candidate_count
    assert tally["holdout"] == study.manifest.holdout_candidate_count


# ------------------------------------------------------- the cross, guarded ---
#
# A defect the first real run exposed. `by_setup_stop_0_5atr_target_2r` — the
# 1D-invalidation ALTERNATIVE — carries the same (0.50, 2.0) thresholds as the
# primary point while being a different rule, and the neighbourhood was keyed on
# those numbers rather than on the sealed family. It silently displaced the
# primary measurement and the plateau was classified against the wrong figure.


def test_only_the_primary_family_sits_on_the_cross() -> None:
    """Membership is the sealed FAMILY, never matching threshold arithmetic."""
    from fmis.swing_lab.validation_study import _on_the_cross

    on_cross = [
        item.policy_id
        for item in PRE_REGISTRATION.hypotheses
        if _on_the_cross(item.policy)
    ]
    assert on_cross == [
        item.policy_id
        for item in PRE_REGISTRATION.hypotheses
        if item.role == "primary"
    ]
    assert "by_setup_stop_0_5atr_target_2r" not in on_cross


def test_the_alternative_shares_the_primary_thresholds_and_must_not_be_confused() -> None:
    """The collision is real; the guard is what stops it mattering."""
    alternative = PRE_REGISTRATION.hypothesis_for("by_setup_stop_0_5atr_target_2r")
    primary = PRE_REGISTRATION.hypothesis_for("by_stop_0_5atr_target_2r")
    assert alternative.policy.min_stop_atr == primary.policy.min_stop_atr
    assert alternative.policy.min_planned_rr == primary.policy.min_planned_rr
    assert alternative.policy.family != primary.policy.family


def test_the_neighbourhood_names_the_primary_policys_own_measurement() -> None:
    """Every point must be the measurement of the policy whose id it carries."""
    study = _study()
    for item in study.policies:
        if item.plateau is None:
            continue
        for point in item.plateau.readings:
            named = study.policy(point.policy_id)
            expected = named.measurement("development", DECIDING_COST_POLICY_ID)
            assert point.metrics.expectancy_r.value == expected.metrics.expectancy_r.value
            assert point.metrics.measurable_trades == expected.metrics.measurable_trades
        centre = next(p for p in item.plateau.readings if p.is_primary)
        assert centre.policy_id == item.policy_id


def test_two_sealed_policies_may_never_claim_one_cross_point() -> None:
    """If a future edit reintroduces the collision it must fail loudly, not silently."""
    from fmis.swing_lab.preregistration import FAMILY_PRIMARY

    colliding = replace(
        _fixture_prereg(),
        hypotheses=(
            *PRE_REGISTRATION.hypotheses,
            replace(
                PRE_REGISTRATION.hypothesis_for("by_stop_0_5atr_target_2r"),
                hypothesis_id="BY-DUP",
                policy=replace(
                    PRE_REGISTRATION.hypothesis_for("by_stop_0_5atr_target_2r").policy,
                    policy_id="by_stop_0_5atr_target_2r_duplicate",
                    family=FAMILY_PRIMARY,
                ),
            ),
        ),
    )
    with pytest.raises(SwingLabError, match="claim the cross point"):
        _study(prereg=colliding)


@pytest.mark.parametrize(
    ("stop", "target", "axis"),
    [(0.35, 2.0, "stop_atr"), (0.5, 2.5, "target_r")],
    ids=["stop-axis-only", "target-axis-only"],
)
def test_a_collision_on_EITHER_axis_alone_is_refused(stop, target, axis) -> None:
    """Both axes, separately.

    A duplicate at the primary point collides on both axes at once, so a check
    present on only one of them still fires and looks correct. These two cases
    collide on exactly one axis each, which is what makes the rule's coverage
    visible rather than assumed.
    """
    from fmis.swing_lab.preregistration import FAMILY_PRIMARY

    twin = PRE_REGISTRATION.hypothesis_for(
        f"by_stop_{'0_35' if stop == 0.35 else '0_5'}atr_target_"
        f"{'2' if target == 2.0 else '2_5'}r"
    )
    colliding = replace(
        _fixture_prereg(),
        hypotheses=(
            *PRE_REGISTRATION.hypotheses,
            replace(
                twin, hypothesis_id="BY-DUP",
                policy=replace(
                    twin.policy, policy_id=f"{twin.policy_id}_duplicate",
                    family=FAMILY_PRIMARY,
                ),
            ),
        ),
    )
    with pytest.raises(SwingLabError, match=f"'{axis}'"):
        _study(prereg=colliding)


# ---------------------------------------------- the walk-forward's universe ---
#
# The walk-forward and every decomposition originally pooled all three samples,
# so the traded universe doubled mid-curve as the holdout entered. A curve that
# changes what it measures half-way along cannot separate a decay in time from a
# change in universe, and reading one as the other is exactly what it invites.


def test_the_walk_forward_holds_one_universe_for_its_whole_length() -> None:
    study = _study()
    holdout = set(HOLD_SYMBOLS)
    subject = study.policy(study.walk_forward_policy_id)
    traded = {
        trade.symbol
        for measurement in subject.measurements
        if measurement.cost_policy_id == DECIDING_COST_POLICY_ID
        and measurement.sample in ("development", "validation")
        for trade in measurement.trades
    }
    assert traded
    assert not traded & holdout, "the primary curve must contain no holdout symbol"


def test_the_holdout_gets_its_own_curve_over_its_own_window() -> None:
    study = _study()
    assert study.holdout_walk_forward
    spec = _fixture_samples()[2]
    assert study.holdout_walk_forward[0].start == spec.signal_start
    assert study.holdout_walk_forward[-1].end <= spec.signal_end


def test_the_primary_curve_spans_development_through_validation() -> None:
    study = _study()
    development, validation, _ = _fixture_samples()
    assert study.walk_forward[0].start == development.signal_start
    assert study.walk_forward[-1].end <= validation.signal_end


def test_the_decompositions_are_kept_per_universe() -> None:
    """Pooling reversed two rows: `symbol_class` and `direction` both flipped."""
    study = _study()
    assert study.decompositions and study.holdout_decompositions
    cut = next(item for item in study.decompositions if item.name == "symbol")
    labels = {item.label.split(":")[-1] for item in cut.cohorts}
    assert not labels & set(HOLD_SYMBOLS)


def test_a_closed_holdout_leaves_the_holdout_curve_empty_rather_than_absent() -> None:
    study = _study(holdout=False)
    assert study.holdout_walk_forward == ()
    assert study.holdout_decompositions == ()
    assert study.walk_forward


def test_a_substituted_manifest_without_the_primary_point_is_named_not_a_StopIteration() -> None:
    """The subject is read off the PARAMETER, so a substitution fails by name."""
    trimmed = replace(
        _fixture_prereg(),
        hypotheses=tuple(
            item for item in PRE_REGISTRATION.hypotheses
            if item.policy_id != "by_stop_0_5atr_target_2r"
        ),
    )
    # `hypothesis_for` refuses first, by name. Either way the point holds: a
    # substituted manifest missing the primary point raises a NAMED SwingLabError
    # rather than the bare StopIteration the original `next(...)` produced.
    with pytest.raises(SwingLabError, match="NOT pre-registered"):
        _study(prereg=trimmed)


def test_the_primary_point_is_on_BOTH_axes_of_the_cross() -> None:
    """`stop=0.50, target=2.0` centres the stop sweep AND the target sweep.

    `_neighbourhood_for` originally returned the first matching axis, so the
    primary point's `parameter_plateau` was decided by the stop axis alone while
    the target axis was never applied to it — which is not what "whether EACH
    parameter sits on a plateau" says.
    """
    from fmis.swing_lab.preregistration import (
        PRIMARY_POLICY,
        STOP_ATR_NEIGHBOURHOOD,
        TARGET_R_NEIGHBOURHOOD,
    )
    from fmis.swing_lab.validation_study import _neighbourhood_for

    axes = _neighbourhood_for(PRIMARY_POLICY)
    assert {axis for axis, _, _ in axes} == {"stop_atr", "target_r"}
    assert len(axes) == len(STOP_ATR_NEIGHBOURHOOD) + len(TARGET_R_NEIGHBOURHOOD)
    assert sum(1 for _, _, is_primary in axes if is_primary) == 2   # one per axis


def test_an_off_centre_primary_policy_sits_on_one_axis_only() -> None:
    """Only the point where the two sweeps meet belongs to both."""
    from fmis.swing_lab.preregistration import PRE_REGISTRATION
    from fmis.swing_lab.validation_study import _neighbourhood_for

    off = PRE_REGISTRATION.hypothesis_for("by_stop_0_65atr_target_2r").policy
    assert {axis for axis, _, _ in _neighbourhood_for(off)} == {"stop_atr"}
    off = PRE_REGISTRATION.hypothesis_for("by_stop_0_5atr_target_2_5r").policy
    assert {axis for axis, _, _ in _neighbourhood_for(off)} == {"target_r"}


def test_the_primary_points_plateau_covers_both_axes(  ) -> None:
    """End to end: the sealed study's primary neighbourhood spans both sweeps."""
    study = _study()
    plateau = study.policy("by_stop_0_5atr_target_2r").plateau
    assert plateau is not None
    assert {point.axis for point in plateau.readings} == {"stop_atr", "target_r"}
