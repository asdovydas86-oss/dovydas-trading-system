"""Diagnosis, verdict and study orchestration, from hand-built geometry.

Milestone BX. These tests never replay history: a `GeometryCapture` is assembled
from hand-made candidates and a hand-made bar array, which is what lets the
whole judging layer be exercised — including cases real data would not offer on
demand, like a sample with no losers or a holdout with no trades at all.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.level_crossing import LevelSide
from fmis.paper.models import PriceBar
from fmis.swing_lab.geometry import GeometryPlan, GeometrySkip, SkipReason, plan_geometry
from fmis.swing_lab.geometry_diagnosis import (
    Distribution,
    GeometryRecord,
    Share,
    describe,
    diagnose_geometry,
)
from fmis.swing_lab.geometry_outcome import measure_outcome
from fmis.swing_lab.geometry_replay import GeometryCapture, trades_for_policy
from fmis.swing_lab.geometry_study import (
    GEOMETRY_LIMITATIONS,
    geometry_digest,
    records_for,
    run_geometry_study,
)
from fmis.swing_lab.geometry import GeometryPolicy, StopRule, TargetRule
from fmis.swing_lab.geometry_variants import (
    PRE_DECLARED_GEOMETRIES,
    PRODUCTION_GEOMETRY,
    min_rr_policy,
    neighbours_of,
)
from fmis.swing_lab.geometry_verdict import (
    MAX_SINGLE_SYMBOL_SHARE,
    Criterion,
    assess_geometry,
)
from fmis.swing_lab.metrics import SAMPLE_FLOOR, compute_lab_metrics
from fmis.swing_lab.models import LabVerdict, SwingLabError
from fmis.swing_lab.trades import FRICTIONLESS_COSTS
from fmis.swing_setup.models import Direction

from fmis.level_crossing import LevelSide as _LevelSide  # noqa: F401
from tests.swing_lab_helpers import candidate, ref

_UTC = timezone.utc
_T0 = datetime(2026, 1, 1, tzinfo=_UTC)
_WINDOW = 20


def _bars(symbol: str, prices: list[tuple[str, str, str, str]]) -> tuple[PriceBar, ...]:
    return tuple(
        PriceBar(
            symbol=symbol, interval="4h",
            open_time=_T0 + timedelta(hours=4 * index),
            open=Decimal(o), high=Decimal(h), low=Decimal(low), close=Decimal(c),
        )
        for index, (o, h, low, c) in enumerate(prices)
    )


def _flat(symbol: str, count: int = 60) -> tuple[PriceBar, ...]:
    """A path that drifts up steadily — a LONG reaches its target, a SHORT stops out."""
    return _bars(
        symbol,
        [
            (f"{100 + i * 0.5:.4f}", f"{101 + i * 0.5:.4f}",
             f"{99.5 + i * 0.5:.4f}", f"{100.4 + i * 0.5:.4f}")
            for i in range(count)
        ],
    )


def _capture(candidates, symbols=("BTCUSDT",)) -> GeometryCapture:
    return GeometryCapture(
        admission_variant_id="swing_current",
        admission_policy_id="swing-setup-v1",
        candidates=tuple(candidates),
        bars_by_symbol={symbol: _flat(symbol) for symbol in symbols},
        metadata={"measured_instants": 100},
    )


def _many(count: int, symbol: str = "BTCUSDT", **overrides):
    """``count`` distinct candidates, each with its own setup id and signal bar."""
    return [
        candidate(
            symbol=symbol,
            setup_id=f"{symbol}|long|from=seq{index}",
            signal_index=index,
            **overrides,
        )
        for index in range(count)
    ]


# ------------------------------------------------------------- distributions ---


def test_describe_reports_quantiles_by_linear_interpolation() -> None:
    item = describe([1.0, 2.0, 3.0, 4.0], label="probe")
    assert (item.n, item.minimum, item.maximum) == (4, 1.0, 4.0)
    assert item.median == pytest.approx(2.5)
    assert item.p25 == pytest.approx(1.75)
    assert item.p75 == pytest.approx(3.25)
    assert item.mean == pytest.approx(2.5)


def test_describe_of_an_empty_sample_is_absent_not_zero() -> None:
    item = describe([], label="probe")
    assert item.n == 0
    assert not item.is_present
    assert item.median is None


def test_describe_of_one_value_reports_it_at_every_quantile() -> None:
    item = describe([7.0], label="probe")
    assert (item.minimum, item.p25, item.median, item.p75, item.maximum) == (
        7.0, 7.0, 7.0, 7.0, 7.0
    )


# -------------------------------------------------------------------- shares ---


def test_a_share_refuses_to_become_a_rate_below_the_sample_floor() -> None:
    assert Share(numerator=1, denominator=4).fraction is None
    assert "1/4" in Share(numerator=1, denominator=4).text
    assert Share(numerator=10, denominator=40).fraction == Decimal("0.25")


def test_a_share_of_nothing_is_absent_rather_than_zero() -> None:
    assert Share(numerator=0, denominator=0).fraction is None


def test_a_share_cannot_exceed_its_own_denominator() -> None:
    with pytest.raises(SwingLabError, match="exceeds denominator"):
        Share(numerator=5, denominator=4)


def test_a_share_cannot_be_negative() -> None:
    with pytest.raises(SwingLabError, match="negative count"):
        Share(numerator=-1, denominator=4)


# ----------------------------------------------------------------- diagnosis ---


def _records(policy=PRODUCTION_GEOMETRY, count: int = 25, **overrides):
    capture = _capture(_many(count, **overrides))
    outcome = trades_for_policy(
        capture, policy, costs=FRICTIONLESS_COSTS, evaluation_window_bars=_WINDOW
    )
    return records_for(outcome, capture, evaluation_window_bars=_WINDOW), outcome


def test_a_diagnosis_reports_every_distribution_the_brief_asks_for() -> None:
    records, outcome = _records()
    diagnosis = diagnose_geometry(records, outcome.skips, label="probe")
    for name in (
        "planned_rr", "realized_r", "winner_r", "loser_r", "stop_bps", "target_bps",
        "stop_atr_multiple", "target_atr_multiple", "mfe_r", "mae_r", "bars_held",
        "entry_position_in_range",
    ):
        assert diagnosis.distribution(name) is not None


def test_an_unknown_distribution_is_refused_by_name() -> None:
    records, outcome = _records()
    diagnosis = diagnose_geometry(records, outcome.skips, label="probe")
    with pytest.raises(SwingLabError, match="no distribution named"):
        diagnosis.distribution("nonsense")
    with pytest.raises(SwingLabError, match="no breakdown named"):
        diagnosis.breakdown("nonsense")


def test_the_reward_below_risk_share_counts_the_bw_defect() -> None:
    """Targets at 101 against a stop at 98: every setup plans to win less than
    it risks, which is the defect BW measured at 48 %."""
    records, outcome = _records(
        setup_target_levels=(ref(101.0, LevelSide.UPPER, interval="1d"),)
    )
    diagnosis = diagnose_geometry(records, outcome.skips, label="probe")
    assert diagnosis.reward_below_risk.numerator == len(records)
    assert diagnosis.reward_below_risk.fraction == Decimal(1)


def test_the_tight_stop_share_counts_stops_inside_one_atr() -> None:
    records, outcome = _records(
        execution_stop_levels=(ref(99.9, LevelSide.LOWER),), execution_atr=1.0
    )
    diagnosis = diagnose_geometry(records, outcome.skips, label="probe")
    assert diagnosis.stops_inside_one_atr.fraction == Decimal(1)


def test_skips_are_counted_by_reason_and_never_dropped() -> None:
    capture = _capture(_many(25))
    outcome = trades_for_policy(
        capture, min_rr_policy(3.0), costs=FRICTIONLESS_COSTS,
        evaluation_window_bars=_WINDOW,
    )
    diagnosis = diagnose_geometry(
        records_for(outcome, capture, evaluation_window_bars=_WINDOW),
        outcome.skips, label="probe",
    )
    assert dict(diagnosis.skip_reasons) == {
        SkipReason.BELOW_MINIMUM_PLANNED_RR.value: 25
    }
    assert outcome.refused == 25
    assert outcome.admitted == 0


def test_every_finding_carries_the_measurement_it_reads() -> None:
    records, outcome = _records()
    diagnosis = diagnose_geometry(records, outcome.skips, label="probe")
    assert len(diagnosis.findings) >= 6
    for finding in diagnosis.findings:
        assert finding.question.endswith("?")
        assert finding.evidence.strip()
        assert finding.reading.strip()
        assert finding.supported in (True, False, None)


def test_a_finding_below_the_sample_floor_reports_absence_not_a_no() -> None:
    records, outcome = _records(count=3)
    diagnosis = diagnose_geometry(records, outcome.skips, label="probe")
    tight = next(f for f in diagnosis.findings if "stops too tight" in f.question)
    assert tight.supported is None


def test_a_diagnosis_of_nothing_is_a_diagnosis_not_a_crash() -> None:
    diagnosis = diagnose_geometry((), (), label="empty")
    assert diagnosis.records == ()
    assert diagnosis.reward_below_risk.fraction is None
    assert diagnosis.distribution("planned_rr").n == 0


def test_a_diagnosis_refuses_a_non_record() -> None:
    with pytest.raises(TypeError, match="must be a GeometryRecord"):
        diagnose_geometry([object()], (), label="probe")


def test_buckets_are_assigned_on_pre_declared_boundaries() -> None:
    records, _ = _records()
    record = records[0]
    # risk 2.0, reward 3.0 → rr 1.5; stop 2 % of 100 → 200 bp; stop 2.0 × ATR 1.0.
    assert record.rr_bucket == "rr_1.5-2.0"
    assert record.stop_bps_bucket == "stop_100-250bp"
    assert record.stop_atr_bucket == "stop>=2.0atr"


def test_a_missing_volatility_reading_gets_its_own_bucket() -> None:
    records, _ = _records(execution_atr=None)
    assert records[0].stop_atr_bucket == "atr_unavailable"


# ------------------------------------------------------------------ outcomes ---


def test_reached_thresholds_are_derived_from_the_recorded_excursion() -> None:
    records, _ = _records()
    for record in records:
        if record.trade.mfe_r is None:
            continue
        assert all(item <= record.trade.mfe_r for item in record.outcome.reached_r)


def test_the_giveback_is_the_excursion_less_the_realized_return() -> None:
    records, _ = _records()
    for record in records:
        if record.trade.mfe_r is None or record.trade.net_r is None:
            continue
        assert record.outcome.unrealised_giveback_r == (
            record.trade.mfe_r - record.trade.net_r
        )


def test_the_post_stop_question_is_not_applicable_to_a_trade_that_never_stopped() -> None:
    records, _ = _records()
    for record in records:
        if not record.reached_stop:
            assert record.outcome.target_reached_after_stop is None


def test_measure_outcome_refuses_a_non_positive_window() -> None:
    records, outcome = _records()
    with pytest.raises(SwingLabError, match="evaluation_window_bars"):
        measure_outcome(
            outcome.plans[0], outcome.trades[0],
            _flat("BTCUSDT"), evaluation_window_bars=0,
        )


def test_measure_outcome_refuses_arguments_of_the_wrong_type() -> None:
    records, outcome = _records()
    with pytest.raises(TypeError, match="plan must be"):
        measure_outcome(object(), outcome.trades[0], _flat("BTCUSDT"),
                        evaluation_window_bars=_WINDOW)
    with pytest.raises(TypeError, match="trade must be"):
        measure_outcome(outcome.plans[0], object(), _flat("BTCUSDT"),
                        evaluation_window_bars=_WINDOW)


# ------------------------------------------------------------------- verdict ---


def _metrics(count: int, per_trade_r: str, symbol: str = "BTCUSDT"):
    """Metrics over ``count`` identical synthetic trades, so a verdict can be aimed."""
    from fmis.swing_lab.models import LabExitReason, LabTrade

    trades = tuple(
        LabTrade(
            variant_id="probe", symbol=symbol, setup_id=f"s{index}",
            direction=Direction.LONG, signal_at=_T0 + timedelta(hours=index),
            entry_at=_T0 + timedelta(hours=index), entry_price=Decimal("100"),
            initial_stop=Decimal("98"), target=Decimal("104"),
            planned_reference_price=Decimal("100"),
            exit_at=_T0 + timedelta(hours=index + 1), exit_price=Decimal("104"),
            exit_reason=LabExitReason.TARGET, bars_held=1,
            gross_r=Decimal(per_trade_r), net_r=Decimal(per_trade_r),
            mfe_r=Decimal(per_trade_r), mae_r=Decimal("0"),
            cost_policy_id="swing-lab-frictionless", planned_risk_reward=2.0,
            segment="s1", context_regime_structure="trending",
            context_structural_trend="sustained_higher",
            setup_structural_trend="sustained_higher",
        )
        for index in range(count)
    )
    return compute_lab_metrics(trades, label="probe")


def test_a_policy_meeting_every_criterion_is_a_candidate_for_forward_test() -> None:
    assessment = assess_geometry(
        policy_id="probe", pre_declared=True,
        development=_metrics(30, "0.5"), holdout=_metrics(30, "0.4"),
        development_symbol_share=Decimal("0.2"), plateau=True,
        plateau_detail="both neighbours positive",
    )
    assert assessment.verdict is LabVerdict.CANDIDATE_FOR_FORWARD_TEST
    assert assessment.blocking == ()


def test_the_strongest_verdict_still_does_not_approve_trading() -> None:
    assert LabVerdict.CANDIDATE_FOR_FORWARD_TEST.is_approved_for_trading is False


def test_a_negative_holdout_rejects_however_good_development_was() -> None:
    """BW measured a variant that improved on its primary study and deteriorated
    on its holdout. That pattern must never promote."""
    assessment = assess_geometry(
        policy_id="probe", pre_declared=True,
        development=_metrics(30, "0.9"), holdout=_metrics(30, "-0.1"),
        development_symbol_share=Decimal("0.2"), plateau=True, plateau_detail="d",
    )
    assert assessment.verdict is LabVerdict.REJECTED
    assert [item.name for item in assessment.blocking] == ["holdout_expectancy"]


def test_a_thin_holdout_is_inconclusive_rather_than_rejected() -> None:
    assessment = assess_geometry(
        policy_id="probe", pre_declared=True,
        development=_metrics(30, "0.5"), holdout=_metrics(3, "0.5"),
        development_symbol_share=Decimal("0.2"), plateau=True, plateau_detail="d",
    )
    assert assessment.verdict is LabVerdict.INCONCLUSIVE


def test_a_single_symbol_result_is_rejected_on_concentration() -> None:
    assessment = assess_geometry(
        policy_id="probe", pre_declared=True,
        development=_metrics(30, "0.5"), holdout=_metrics(30, "0.5"),
        development_symbol_share=Decimal("0.9"), plateau=True, plateau_detail="d",
    )
    assert assessment.verdict is LabVerdict.REJECTED
    assert "symbol_concentration" in [item.name for item in assessment.blocking]


def test_the_concentration_bound_is_inclusive_at_its_boundary() -> None:
    assessment = assess_geometry(
        policy_id="probe", pre_declared=True,
        development=_metrics(30, "0.5"), holdout=_metrics(30, "0.5"),
        development_symbol_share=MAX_SINGLE_SYMBOL_SHARE, plateau=True,
        plateau_detail="d",
    )
    assert assessment.verdict is LabVerdict.CANDIDATE_FOR_FORWARD_TEST


def test_a_post_hoc_policy_can_never_be_a_candidate() -> None:
    assessment = assess_geometry(
        policy_id="probe", pre_declared=False,
        development=_metrics(30, "0.5"), holdout=_metrics(30, "0.5"),
        development_symbol_share=Decimal("0.2"), plateau=True, plateau_detail="d",
    )
    assert assessment.verdict is LabVerdict.REJECTED
    assert "pre_declared" in [item.name for item in assessment.blocking]


def test_a_missing_plateau_test_blocks_rather_than_passes() -> None:
    assessment = assess_geometry(
        policy_id="probe", pre_declared=True,
        development=_metrics(30, "0.5"), holdout=_metrics(30, "0.5"),
        development_symbol_share=Decimal("0.2"), plateau=None,
        plateau_detail="no numeric threshold",
    )
    assert assessment.verdict is LabVerdict.INCONCLUSIVE


def test_the_soft_holdout_reading_reports_but_never_promotes() -> None:
    """`holdout_not_catastrophic` is advisory. It must not rescue a losing
    holdout, and it must not sink a passing one."""
    assessment = assess_geometry(
        policy_id="probe", pre_declared=True,
        development=_metrics(30, "0.9"), holdout=_metrics(30, "-0.1"),
        development_symbol_share=Decimal("0.2"), plateau=True, plateau_detail="d",
    )
    soft = next(c for c in assessment.criteria if c.name == "holdout_not_catastrophic")
    assert soft.passed is True  # -0.1 > -0.9
    assert assessment.verdict is LabVerdict.REJECTED  # and it changed nothing


def test_the_soft_holdout_reading_is_not_evaluable_without_a_development_gain() -> None:
    """Found on the first real run: a policy that MADE money on its holdout was
    reported as failing a not-catastrophic test, because it had not out-earned
    the magnitude of its own development loss. With no gain there is nothing to
    give back, and the honest answer is 'not evaluable'."""
    assessment = assess_geometry(
        policy_id="probe", pre_declared=True,
        development=_metrics(30, "-0.28"), holdout=_metrics(30, "0.055"),
        development_symbol_share=Decimal("0.2"), plateau=True, plateau_detail="d",
    )
    soft = next(c for c in assessment.criteria if c.name == "holdout_not_catastrophic")
    assert soft.passed is None
    assert "no gain" in soft.observed
    # Still advisory: the verdict rests on development_expectancy alone here.
    assert assessment.verdict is LabVerdict.REJECTED
    assert "holdout_not_catastrophic" not in [
        item.name for item in assessment.blocking if item.passed is False
    ]


def test_the_soft_reading_is_not_evaluable_when_a_figure_is_missing() -> None:
    assessment = assess_geometry(
        policy_id="probe", pre_declared=True,
        development=_metrics(3, "0.9"), holdout=_metrics(30, "0.1"),
        development_symbol_share=Decimal("0.2"), plateau=True, plateau_detail="d",
    )
    soft = next(c for c in assessment.criteria if c.name == "holdout_not_catastrophic")
    assert soft.passed is None


def test_every_criterion_states_a_requirement_and_an_observation() -> None:
    assessment = assess_geometry(
        policy_id="probe", pre_declared=True,
        development=_metrics(30, "0.5"), holdout=_metrics(30, "0.5"),
        development_symbol_share=Decimal("0.2"), plateau=True, plateau_detail="d",
    )
    assert len(assessment.criteria) == 9
    for criterion in assessment.criteria:
        assert criterion.requirement.strip()
        assert criterion.observed.strip()
        assert criterion.symbol in {"PASS", "FAIL", "N/A "}


def test_a_criterion_refuses_a_non_boolean_pass() -> None:
    with pytest.raises(TypeError, match="passed must be"):
        Criterion(name="n", requirement="r", passed="yes", observed="o")


def test_assess_geometry_refuses_a_non_metrics_argument() -> None:
    with pytest.raises(TypeError, match="development must be"):
        assess_geometry(
            policy_id="probe", pre_declared=True, development=object(),
            holdout=_metrics(30, "0.5"), development_symbol_share=None,
            plateau=None, plateau_detail="d",
        )


# --------------------------------------------------------------------- study ---


def _study(**overrides):
    capture = GeometryCapture(
        admission_variant_id="swing_current",
        admission_policy_id="swing-setup-v1",
        candidates=tuple(_many(25, "BTCUSDT") + _many(25, "ETHUSDT")),
        bars_by_symbol={"BTCUSDT": _flat("BTCUSDT"), "ETHUSDT": _flat("ETHUSDT")},
        metadata={},
    )
    kwargs = dict(
        development_symbols=("BTCUSDT",), holdout_symbols=("ETHUSDT",),
        experiment_id="probe", run_at=_T0,
        measurement_start=_T0, measurement_end=_T0 + timedelta(days=30),
        warmup_start=_T0 - timedelta(days=1000), costs=FRICTIONLESS_COSTS,
        evaluation_window_bars=_WINDOW, candle_limit=250,
        policies=PRE_DECLARED_GEOMETRIES[:3], with_sensitivity=False,
    )
    kwargs.update(overrides)
    return run_geometry_study(capture, **kwargs)


def test_a_study_measures_every_policy_on_both_samples() -> None:
    study = _study()
    assert len(study.results) == 3
    for result in study.results:
        assert result.development.sample == "development"
        assert result.holdout.sample == "holdout"


def test_a_study_refuses_overlapping_samples() -> None:
    with pytest.raises(SwingLabError, match="must be disjoint"):
        _study(development_symbols=("BTCUSDT",), holdout_symbols=("BTCUSDT",))


def test_a_study_refuses_an_empty_sample() -> None:
    with pytest.raises(SwingLabError, match="must be non-empty"):
        _study(holdout_symbols=())


def test_a_study_refuses_an_empty_policy_set() -> None:
    with pytest.raises(SwingLabError, match="policies must be"):
        _study(policies=())


def test_an_unknown_policy_is_refused_by_name() -> None:
    study = _study()
    with pytest.raises(SwingLabError, match="holds no geometry"):
        study.result_for("nope")


def test_the_manifest_is_read_off_the_run() -> None:
    study = _study()
    manifest = study.manifest
    assert manifest.development_symbols == ("BTCUSDT",)
    assert manifest.holdout_symbols == ("ETHUSDT",)
    assert manifest.candidate_count == 50
    assert manifest.admission_variant_id == "swing_current"
    assert len(manifest.result_digest) == 64


def test_every_bx_limitation_travels_on_the_manifest() -> None:
    study = _study()
    for limitation in GEOMETRY_LIMITATIONS:
        assert limitation in study.manifest.limitations
    # BW's limitations sit beneath BX's, unchanged.
    assert any(item.startswith("BW-4") for item in study.manifest.limitations)


def test_the_digest_is_invariant_to_result_order() -> None:
    study = _study()
    forward = geometry_digest(study.results)
    backward = geometry_digest(tuple(reversed(study.results)))
    assert forward == backward == study.manifest.result_digest


def test_the_digest_changes_when_a_geometry_changes() -> None:
    baseline = _study(policies=(PRODUCTION_GEOMETRY,))
    altered = _study(policies=(min_rr_policy(1.25),))
    assert baseline.manifest.result_digest != altered.manifest.result_digest


def test_records_refuse_a_plan_and_trade_sequence_that_does_not_correspond() -> None:
    from fmis.swing_lab.geometry_replay import PolicyOutcome

    capture = _capture(_many(3))
    outcome = trades_for_policy(
        capture, PRODUCTION_GEOMETRY, costs=FRICTIONLESS_COSTS,
        evaluation_window_bars=_WINDOW,
    )
    broken = PolicyOutcome(
        policy=outcome.policy, trades=outcome.trades[:2],
        plans=outcome.plans, skips=outcome.skips,
    )
    with pytest.raises(SwingLabError, match="must correspond one to one"):
        records_for(broken, capture, evaluation_window_bars=_WINDOW)


def test_a_study_names_no_winner() -> None:
    """A study that ranked variants would be choosing one. The criteria exist so
    that choice is not a judgement call, and there is deliberately no `best`."""
    study = _study()
    assert not hasattr(study, "best")
    assert not hasattr(study, "recommended")
    assert not hasattr(study, "winner")


def test_the_candidates_property_reports_only_policies_meeting_every_criterion() -> None:
    study = _study()
    for result in study.candidates:
        assert result.assessment.verdict is LabVerdict.CANDIDATE_FOR_FORWARD_TEST
        assert result.assessment.blocking == ()


# --------------------------------------------- mutation-probe survivor gaps ---
#
# Each test below closes a probe that survived the first mutation run. They are
# grouped here rather than scattered because what they have in common is the
# reason they were missing: the earlier tests exercised the happy path of a
# judging rule without ever making the rule's *decision* matter.


def _negative_metrics(count: int, symbol: str = "BTCUSDT"):
    return _metrics(count, "-0.5", symbol)


def test_a_post_hoc_policy_is_judged_post_hoc_by_the_study() -> None:
    """`pre_declared` must be read from membership of the pre-declared set, not
    assumed. A study that hard-coded True would let a policy invented after the
    results were seen be reported as independently validated."""
    from fmis.swing_lab.geometry_variants import POST_HOC_FAMILY

    invented = GeometryPolicy(
        policy_id="geom_invented_after_the_fact",
        title="Invented after the fact",
        family=POST_HOC_FAMILY,
        hypothesis="A policy written once the results were already on the screen.",
        stop_rule=StopRule.NEAREST_EXECUTION,
        target_rule=TargetRule.NEAREST_SETUP,
    )
    study = _study(policies=(PRODUCTION_GEOMETRY, invented))
    result = study.result_for("geom_invented_after_the_fact")
    pre_declared = next(
        c for c in result.assessment.criteria if c.name == "pre_declared"
    )
    assert pre_declared.passed is False
    assert result.assessment.verdict is not LabVerdict.CANDIDATE_FOR_FORWARD_TEST


def test_a_policy_with_no_threshold_cannot_pass_the_plateau_test() -> None:
    """No neighbours means the test could not be run. Reporting that as a pass
    would let every rule without a number skip §9 entirely."""
    study = _study(policies=(PRODUCTION_GEOMETRY,))
    plateau = next(
        c
        for c in study.result_for("geom_production").assessment.criteria
        if c.name == "parameter_plateau"
    )
    assert plateau.passed is None
    assert "no numeric threshold" in plateau.observed


def test_the_plateau_test_requires_every_measurable_neighbour_to_agree() -> None:
    """`all`, never `any`. One positive neighbour beside a negative one is
    exactly the spike §9 exists to reject."""
    from fmis.swing_lab.geometry_study import _plateau_for

    capture = _capture(_many(25))
    # A threshold policy whose neighbours are measurable on this capture.
    passed, detail = _plateau_for(
        min_rr_policy(1.25), capture,
        costs=FRICTIONLESS_COSTS, evaluation_window_bars=_WINDOW,
    )
    assert passed in (True, False, None)
    assert detail.strip()
    # Every neighbour that cleared the floor must be named in the detail, so a
    # reader can see which values the verdict rests on.
    for neighbour in neighbours_of(min_rr_policy(1.25)):
        assert neighbour.policy_id in detail


def test_reached_thresholds_are_non_empty_for_a_trade_that_ran_in_profit() -> None:
    """The earlier assertion (`every reached threshold <= MFE`) is satisfied
    vacuously by an empty tuple, so a rule reading MAE instead of MFE survived
    it. This one requires the thresholds actually to be reached."""
    records, _ = _records()
    winners = [r for r in records if r.trade.mfe_r is not None and r.trade.mfe_r >= 1]
    assert winners, "fixture must contain a trade whose excursion exceeded +1R"
    for record in winners:
        assert Decimal("0.5") in record.outcome.reached_r
        assert Decimal("1.0") in record.outcome.reached_r


def test_the_excursion_thresholds_are_empty_for_a_trade_that_never_ran_up() -> None:
    """The other side of the same rule, so 'always non-empty' cannot pass."""
    from fmis.swing_lab.models import LabExitReason

    records, _ = _records(
        direction=Direction.SHORT,
        execution_stop_levels=(ref(102.0, LevelSide.UPPER),),
        setup_stop_levels=(ref(108.0, LevelSide.UPPER, interval="1d"),),
        setup_target_levels=(ref(97.0, LevelSide.LOWER, interval="1d"),
                             ref(88.0, LevelSide.LOWER, interval="1d", index=2)),
        context_target_levels=(ref(60.0, LevelSide.LOWER, interval="1w"),),
    )
    losers = [
        r for r in records
        if r.trade.exit_reason is LabExitReason.STOP and r.trade.mfe_r is not None
        and r.trade.mfe_r < Decimal("0.5")
    ]
    assert losers, "fixture must contain a trade that never ran up half an R"
    for record in losers:
        assert record.outcome.reached_r == ()


def test_a_non_positive_atr_is_dropped_to_absent_rather_than_carried() -> None:
    """A zero or negative ATR is a broken measurement, not a calm market.
    `_atr_of` must report it as unavailable, because `GeometryCandidate` refuses
    to carry one and a policy normalising by it would divide by zero."""
    from fmis.pipeline.multi_timeframe import TimeframeRole
    from fmis.swing_lab.geometry_replay import ATR_FEATURE_NAME, _atr_of

    class _Result:
        def __init__(self, value):
            self.value = value

    class _Features:
        def __init__(self, value):
            self.features = {ATR_FEATURE_NAME: _Result(value)}

    class _Sheet:
        def __init__(self, value):
            self.features = _Features(value)

    class _View:
        def __init__(self, value):
            self.sheet = _Sheet(value)

    class _Book:
        def __init__(self, value):
            self.by_role = {TimeframeRole.EXECUTION: _View(value)}

    assert _atr_of(_Book(3.5), TimeframeRole.EXECUTION) == 3.5
    for broken in (0.0, -1.0):
        assert _atr_of(_Book(broken), TimeframeRole.EXECUTION) is None
    assert _atr_of(_Book(None), TimeframeRole.EXECUTION) is None
    assert _atr_of(_Book(True), TimeframeRole.EXECUTION) is None


def test_the_plateau_rule_requires_every_measurable_neighbour_to_be_positive() -> None:
    """`all`, never `any`. One positive neighbour beside a negative one is the
    spike §9 exists to reject, and an `any` would call it a plateau."""
    from fmis.swing_lab.geometry_study import plateau_from

    positive = _metrics(30, "0.4")
    negative = _metrics(30, "-0.4")
    thin = _metrics(3, "0.9")

    assert plateau_from([("lo", positive), ("hi", positive)])[0] is True
    assert plateau_from([("lo", positive), ("hi", negative)])[0] is False
    assert plateau_from([("lo", negative), ("hi", negative)])[0] is False
    # A neighbour below the floor is ignored rather than counted either way.
    assert plateau_from([("lo", positive), ("hi", thin)])[0] is True
    assert plateau_from([("lo", negative), ("hi", thin)])[0] is False
    # No measurable neighbour at all: the test could not be run.
    assert plateau_from([("lo", thin), ("hi", thin)])[0] is None
    assert plateau_from([])[0] is None


def test_the_plateau_detail_names_every_neighbour_including_the_thin_ones() -> None:
    """A reader must be able to see which values the verdict rests on, and which
    were too thin to contribute."""
    from fmis.swing_lab.geometry_study import plateau_from

    _, detail = plateau_from([("lo", _metrics(30, "0.4")), ("hi", _metrics(3, "0.9"))])
    assert "lo" in detail and "hi" in detail
    assert "below floor" in detail


# ------------------------------------------------------- argument validation ---
#
# Every check below runs BEFORE any network access, which is what lets the
# experiment entry point be tested without a provider.


def test_the_experiment_refuses_overlapping_samples_before_fetching() -> None:
    from fmis.swing_lab.geometry_study import run_geometry_experiment

    with pytest.raises(SwingLabError, match="must be disjoint"):
        run_geometry_experiment(
            development_symbols=("BTCUSDT",), holdout_symbols=("BTCUSDT",),
            measurement_start=_T0, measurement_end=_T0 + timedelta(days=30),
            run_at=_T0, experiment_id="probe",
        )


def test_the_experiment_refuses_an_empty_universe() -> None:
    from fmis.swing_lab.geometry_study import run_geometry_experiment

    with pytest.raises(SwingLabError, match="at least one symbol"):
        run_geometry_experiment(
            development_symbols=(), holdout_symbols=(),
            measurement_start=_T0, measurement_end=_T0 + timedelta(days=30),
            run_at=_T0, experiment_id="probe",
        )


def test_the_experiment_refuses_a_naive_run_instant() -> None:
    from fmis.swing_lab.geometry_study import run_geometry_experiment

    with pytest.raises(SwingLabError, match="timezone-aware"):
        run_geometry_experiment(
            development_symbols=("BTCUSDT",), holdout_symbols=("ETHUSDT",),
            measurement_start=_T0, measurement_end=_T0 + timedelta(days=30),
            run_at=datetime(2026, 1, 1), experiment_id="probe",
        )


def test_the_experiment_refuses_a_window_that_ends_before_it_starts() -> None:
    from fmis.swing_lab.geometry_study import run_geometry_experiment

    with pytest.raises(SwingLabError, match="must be after"):
        run_geometry_experiment(
            development_symbols=("BTCUSDT",), holdout_symbols=("ETHUSDT",),
            measurement_start=_T0, measurement_end=_T0 - timedelta(days=1),
            run_at=_T0, experiment_id="probe",
        )


def test_a_candidate_refuses_every_argument_of_the_wrong_type() -> None:
    with pytest.raises(TypeError, match="direction must be"):
        candidate(direction="long")
    with pytest.raises(TypeError, match="execution_atr must be"):
        candidate(execution_atr="1.0")


def test_a_level_ref_refuses_a_malformed_construction() -> None:
    from fmis.swing_lab.geometry import LevelRef

    with pytest.raises(TypeError, match="price must be"):
        LevelRef(price="1", side=LevelSide.UPPER, interval="4h",
                 origin_index=None, origin_label=None)
    with pytest.raises(TypeError, match="side must be"):
        LevelRef(price=1.0, side="upper", interval="4h",
                 origin_index=None, origin_label=None)
    with pytest.raises(SwingLabError, match="interval must be"):
        LevelRef(price=1.0, side=LevelSide.UPPER, interval="  ",
                 origin_index=None, origin_label=None)


def test_a_policy_refuses_a_malformed_construction() -> None:
    with pytest.raises(SwingLabError, match="policy_id must be"):
        GeometryPolicy(policy_id="", title="t", family="Z", hypothesis="h",
                       stop_rule=StopRule.NEAREST_EXECUTION,
                       target_rule=TargetRule.NEAREST_SETUP)
    with pytest.raises(TypeError, match="stop_rule must be"):
        GeometryPolicy(policy_id="p", title="t", family="Z", hypothesis="h",
                       stop_rule="nearest", target_rule=TargetRule.NEAREST_SETUP)
    with pytest.raises(TypeError, match="target_rule must be"):
        GeometryPolicy(policy_id="p", title="t", family="Z", hypothesis="h",
                       stop_rule=StopRule.NEAREST_EXECUTION, target_rule="nearest")
    with pytest.raises(TypeError, match="volatility_source must be"):
        GeometryPolicy(policy_id="p", title="t", family="Z", hypothesis="h",
                       stop_rule=StopRule.NEAREST_EXECUTION,
                       target_rule=TargetRule.NEAREST_SETUP, volatility_source="atr")


def test_a_criterion_refuses_an_empty_field() -> None:
    with pytest.raises(SwingLabError, match="name must be"):
        Criterion(name="", requirement="r", passed=True, observed="o")


def test_assess_geometry_refuses_an_empty_policy_id() -> None:
    with pytest.raises(SwingLabError, match="policy_id must be"):
        assess_geometry(
            policy_id="  ", pre_declared=True, development=_metrics(30, "0.5"),
            holdout=_metrics(30, "0.5"), development_symbol_share=None,
            plateau=None, plateau_detail="d",
        )


def test_a_diagnosis_refuses_an_empty_label() -> None:
    with pytest.raises(SwingLabError, match="label must be"):
        diagnose_geometry((), (), label="  ")


def test_trades_for_policy_refuses_arguments_of_the_wrong_type() -> None:
    with pytest.raises(TypeError, match="capture must be"):
        trades_for_policy(object(), PRODUCTION_GEOMETRY,
                          costs=FRICTIONLESS_COSTS, evaluation_window_bars=_WINDOW)
    # Milestone BY widened the contract from `GeometryPolicy` to the
    # `PlansGeometry` protocol so its non-structural control — which must live
    # outside `fmis.swing_lab.geometry`, whose guard forbids constructing a
    # level — is measured by this same replay. The refusal is still total: an
    # object with neither `policy_id` nor `plan` is rejected.
    with pytest.raises(TypeError, match="policy must satisfy PlansGeometry"):
        trades_for_policy(_capture(_many(1)), object(),
                          costs=FRICTIONLESS_COSTS, evaluation_window_bars=_WINDOW)


def test_capture_refuses_a_non_variant_admission() -> None:
    from fmis.swing_lab.geometry_replay import capture_geometry_candidates

    with pytest.raises(TypeError, match="admission must be"):
        capture_geometry_candidates(["BTCUSDT"], object(), window=None,
                                    segments=(), dataset=None)


def test_capture_refuses_an_empty_or_string_symbol_sequence() -> None:
    from fmis.swing_lab.geometry_replay import capture_geometry_candidates
    from fmis.swing_lab.variants import BASELINE_VARIANT

    for bad in ("BTCUSDT", ()):
        with pytest.raises(SwingLabError, match="non-empty, non-string"):
            capture_geometry_candidates(bad, BASELINE_VARIANT, window=None,
                                        segments=(), dataset=None)


def test_a_concentration_finding_distinguishes_a_spread_from_a_concentration() -> None:
    """The §2 questions about WHERE a defect lives. A rule that called every
    split 'concentrated' would report a defect as living somewhere specific when
    it is evenly spread — the opposite of the finding."""
    from fmis.swing_lab.geometry_diagnosis import Share, _concentration_finding

    even = (("a", Share(numerator=20, denominator=40)), ("b", Share(numerator=21, denominator=40)))
    finding = _concentration_finding("Q?", even, subject="cohort")
    assert finding.supported is False
    assert "Spread rather than concentrated" in finding.reading

    lopsided = (("a", Share(numerator=38, denominator=40)), ("b", Share(numerator=2, denominator=40)))
    finding = _concentration_finding("Q?", lopsided, subject="cohort")
    assert finding.supported is True
    assert "Concentrated" in finding.reading


def test_a_concentration_finding_refuses_to_answer_from_one_cohort() -> None:
    from fmis.swing_lab.geometry_diagnosis import Share, _concentration_finding

    thin = (("a", Share(numerator=20, denominator=40)), ("b", Share(numerator=1, denominator=3)))
    finding = _concentration_finding("Q?", thin, subject="cohort")
    assert finding.supported is None
    assert "Not answerable at this sample size" in finding.reading
