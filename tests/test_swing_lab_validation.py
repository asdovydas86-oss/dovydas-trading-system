"""The frozen bar, applied. **These tests exist to make promotion hard.**

Every test here asks the same question from a different angle: *can something
that should not be promoted get promoted?* A post-hoc policy, the non-structural
control, a thin sample, a frictionless-only edge, a spike whose neighbours fail,
a result carried by one symbol, a broken seal. All of them must be refused, and
refused for a **named** reason a report can print.

The one test that runs the other way — `test_a_policy_meeting_every_criterion_is_a_candidate`
— exists so the criteria are known to be satisfiable. A bar nothing can clear is
not a bar either; it is a foregone conclusion.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fmis.swing_lab.metrics import VariantMetrics, compute_lab_metrics
from fmis.swing_lab.models import LabVerdict, SwingLabError
from fmis.swing_lab.validation import (
    MIN_PLATEAU_POINTS,
    CandidateAssessment,
    NeighbourReading,
    PlateauClass,
    assess_candidate,
    classify_plateau,
    criteria_index,
)

from tests.test_swing_lab_metrics import many, trade

PRIMARY = "by_stop_0_5atr_target_2r"


def _metrics(label: str, count: int = 30, net_r: str = "0.4", **kwargs) -> VariantMetrics:
    return compute_lab_metrics(many(count, net_r, **kwargs), label=label)


def _mixed(label: str, wins: int, losses: int, *, win_r="1.5", loss_r="-1") -> VariantMetrics:
    trades = [trade(win_r, index=i) for i in range(wins)]
    trades += [trade(loss_r, index=wins + i) for i in range(losses)]
    return compute_lab_metrics(trades, label=label)


def _reading(axis: str, threshold: float, metrics: VariantMetrics, *, primary=False):
    return NeighbourReading(
        policy_id=f"p_{axis}_{threshold}", axis=axis, threshold=threshold,
        is_primary=primary, metrics=metrics,
    )


# --------------------------------------------------------------- plateau ---


def test_all_neighbours_positive_is_a_robust_plateau() -> None:
    reading = classify_plateau(
        [
            _reading("stop_atr", 0.35, _metrics("a", net_r="0.2")),
            _reading("stop_atr", 0.50, _metrics("b", net_r="0.4"), primary=True),
            _reading("stop_atr", 0.65, _metrics("c", net_r="0.1")),
        ]
    )
    assert reading.classification is PlateauClass.ROBUST_PLATEAU


def test_one_failing_neighbour_makes_it_a_fragile_spike() -> None:
    """**BX's §10 shape.** A rule that survives at one threshold and dies at the next."""
    reading = classify_plateau(
        [
            _reading("stop_atr", 0.35, _metrics("a", net_r="-0.1")),
            _reading("stop_atr", 0.50, _metrics("b", net_r="0.4"), primary=True),
            _reading("stop_atr", 0.65, _metrics("c", net_r="0.1")),
        ]
    )
    assert reading.classification is PlateauClass.FRAGILE_SPIKE
    assert "shape a fitted parameter makes" in reading.classification.statement


def test_the_rule_is_all_and_never_any() -> None:
    """One positive point beside a negative one is a spike, not a majority verdict."""
    reading = classify_plateau(
        [
            _reading("stop_atr", 0.35, _metrics("a", net_r="0.5")),
            _reading("stop_atr", 0.50, _metrics("b", net_r="0.4"), primary=True),
            _reading("stop_atr", 0.65, _metrics("c", net_r="-0.01")),
            _reading("stop_atr", 0.80, _metrics("d", net_r="0.5")),
        ]
    )
    assert reading.classification is PlateauClass.FRAGILE_SPIKE


def test_a_non_positive_centre_is_no_edge_and_not_a_spike() -> None:
    """Precedence matters: there is no spike to be fragile about."""
    reading = classify_plateau(
        [
            _reading("stop_atr", 0.35, _metrics("a", net_r="-0.1")),
            _reading("stop_atr", 0.50, _metrics("b", net_r="-0.2"), primary=True),
            _reading("stop_atr", 0.65, _metrics("c", net_r="0.3")),
        ]
    )
    assert reading.classification is PlateauClass.NO_EDGE


def test_a_zero_centre_is_no_edge() -> None:
    """`> 0`, not `>= 0`. A break-even rule has not shown an edge."""
    reading = classify_plateau(
        [
            _reading("stop_atr", 0.35, _metrics("a", net_r="0.1")),
            _reading("stop_atr", 0.50, _metrics("b", net_r="0"), primary=True),
            _reading("stop_atr", 0.65, _metrics("c", net_r="0.1")),
        ]
    )
    assert reading.classification is PlateauClass.NO_EDGE


def test_too_few_measurable_points_is_not_measurable_and_not_a_pass() -> None:
    reading = classify_plateau(
        [
            _reading("stop_atr", 0.35, _metrics("a", count=3, net_r="0.2")),
            _reading("stop_atr", 0.50, _metrics("b", net_r="0.4"), primary=True),
            _reading("stop_atr", 0.65, _metrics("c", count=2, net_r="0.1")),
        ]
    )
    assert reading.classification is PlateauClass.NOT_MEASURABLE
    assert reading.classification.is_robust is False


def test_a_thin_centre_is_not_measurable_even_with_healthy_neighbours() -> None:
    reading = classify_plateau(
        [
            _reading("stop_atr", 0.35, _metrics("a", net_r="0.2")),
            _reading("stop_atr", 0.50, _metrics("b", count=4, net_r="0.4"), primary=True),
            _reading("stop_atr", 0.65, _metrics("c", net_r="0.1")),
        ]
    )
    assert reading.classification is PlateauClass.NOT_MEASURABLE


def test_the_minimum_point_count_is_three() -> None:
    """Two points cannot distinguish a plateau from a slope."""
    assert MIN_PLATEAU_POINTS == 3


def test_a_neighbourhood_needs_exactly_one_centre() -> None:
    with pytest.raises(SwingLabError, match="exactly one primary point"):
        classify_plateau([_reading("stop_atr", 0.5, _metrics("a"))])
    with pytest.raises(SwingLabError, match="exactly one primary point"):
        classify_plateau(
            [
                _reading("stop_atr", 0.35, _metrics("a"), primary=True),
                _reading("stop_atr", 0.50, _metrics("b"), primary=True),
            ]
        )


def test_the_detail_names_every_point_including_the_thin_ones() -> None:
    """A report must never be able to omit a failing neighbour."""
    reading = classify_plateau(
        [
            _reading("stop_atr", 0.35, _metrics("a", net_r="-0.9")),
            _reading("stop_atr", 0.50, _metrics("b", net_r="0.4"), primary=True),
            _reading("stop_atr", 0.65, _metrics("c", count=2, net_r="0.1")),
        ]
    )
    assert "-0.9000R" in reading.detail
    assert "below floor" in reading.detail
    assert "*stop_atr=0.5" in reading.detail


# --------------------------------------------------------------- verdict ---


def _assess(*, policy_id: str = PRIMARY, **overrides) -> CandidateAssessment:
    kwargs = dict(
        policy_id=policy_id,
        is_structural=True,
        manifest_digest_matches=True,
        development=_mixed(f"{policy_id}:development", 20, 10),
        validation=_mixed(f"{policy_id}:validation", 15, 10),
        holdout=_mixed(f"{policy_id}:holdout", 15, 10),
        development_symbol_share=Decimal("0.2"),
        plateau=classify_plateau(
            [
                _reading("stop_atr", 0.35, _metrics("a", net_r="0.2")),
                _reading("stop_atr", 0.50, _metrics("b", net_r="0.4"), primary=True),
                _reading("stop_atr", 0.65, _metrics("c", net_r="0.1")),
            ]
        ),
        no_lookahead_proven=True,
        cost_policy_id="swing-lab-conservative-10bps",
    )
    kwargs.update(overrides)
    return assess_candidate(**kwargs)


def test_a_policy_meeting_every_criterion_is_a_candidate() -> None:
    """The bar must be clearable, or it is a foregone conclusion rather than a test."""
    assessment = _assess()
    assert assessment.verdict is LabVerdict.CANDIDATE_FOR_FORWARD_TEST
    assert assessment.blocking == ()
    assert "NOT approval to trade" in assessment.statement


def test_the_strongest_verdict_still_does_not_approve_trading() -> None:
    assert _assess().verdict.is_approved_for_trading is False


def test_a_post_hoc_policy_cannot_be_promoted() -> None:
    """Not 'is unlikely to be'. Cannot — by set membership in the sealed manifest."""
    assessment = _assess(policy_id="geom_min_rr_1")
    assert assessment.verdict is LabVerdict.REJECTED
    assert "pre_registered" in {item.name for item in assessment.blocking}


def test_a_broken_seal_blocks_every_policy() -> None:
    assessment = _assess(manifest_digest_matches=False)
    assert assessment.verdict is LabVerdict.REJECTED
    assert "pre_registered" in {item.name for item in assessment.blocking}


def test_the_non_structural_control_cannot_be_promoted_however_good_it_is() -> None:
    """A control that could win the thing it controls for is not a control."""
    assessment = _assess(
        is_structural=False,
        development=_mixed(f"{PRIMARY}:development", 28, 2),
    )
    assert assessment.verdict is LabVerdict.REJECTED
    blocker = next(i for i in assessment.blocking if i.name == "structural")
    assert "permanently ineligible" in blocker.observed


def test_a_negative_holdout_blocks_promotion() -> None:
    assessment = _assess(holdout=_mixed(f"{PRIMARY}:holdout", 5, 20))
    assert assessment.verdict is LabVerdict.REJECTED
    assert "holdout_expectancy" in {item.name for item in assessment.blocking}


def test_a_negative_validation_blocks_promotion() -> None:
    assessment = _assess(validation=_mixed(f"{PRIMARY}:validation", 5, 20))
    assert "validation_expectancy" in {item.name for item in assessment.blocking}


def test_validation_and_holdout_may_be_exactly_zero() -> None:
    """The sealed wording is NON-NEGATIVE for the unseen samples; `>= 0`, not `> 0`."""
    flat = compute_lab_metrics(many(25, "0"), label=f"{PRIMARY}:validation")
    assessment = _assess(validation=flat)
    assert next(
        i for i in assessment.criteria if i.name == "validation_expectancy"
    ).passed is True


def test_development_must_be_strictly_positive() -> None:
    """Development is the one sample where break-even is not good enough."""
    flat = compute_lab_metrics(many(25, "0"), label=f"{PRIMARY}:development")
    assessment = _assess(development=flat)
    assert next(
        i for i in assessment.criteria if i.name == "development_expectancy"
    ).passed is False


def test_a_thin_sample_is_inconclusive_and_never_rejected() -> None:
    """`REJECTED` means 'this lost money'. Nobody measured it, so nobody may say that."""
    thin = compute_lab_metrics(many(4, "0.5"), label=f"{PRIMARY}:holdout")
    assessment = _assess(holdout=thin)
    assert assessment.verdict is LabVerdict.INCONCLUSIVE
    blocker = next(i for i in assessment.blocking if i.name == "holdout_sample")
    assert blocker.passed is None


def test_a_measured_failure_beats_an_unevaluable_one_in_the_verdict() -> None:
    """One `False` makes it REJECTED even beside several `None`s."""
    thin = compute_lab_metrics(many(4, "0.5"), label=f"{PRIMARY}:holdout")
    assessment = _assess(holdout=thin, is_structural=False)
    assert assessment.verdict is LabVerdict.REJECTED


def test_symbol_domination_blocks_promotion() -> None:
    assessment = _assess(development_symbol_share=Decimal("0.55"))
    blocker = next(i for i in assessment.blocking if i.name == "symbol_concentration")
    assert "55.0%" in blocker.observed


def test_the_concentration_bound_is_inclusive_at_forty_percent() -> None:
    assessment = _assess(development_symbol_share=Decimal("0.40"))
    assert next(
        i for i in assessment.criteria if i.name == "symbol_concentration"
    ).passed is True


def test_a_fragile_spike_is_rejected_however_good_its_centre() -> None:
    spike = classify_plateau(
        [
            _reading("stop_atr", 0.35, _metrics("a", net_r="-0.3")),
            _reading("stop_atr", 0.50, _metrics("b", net_r="0.9"), primary=True),
            _reading("stop_atr", 0.65, _metrics("c", net_r="-0.2")),
        ]
    )
    assessment = _assess(plateau=spike)
    assert assessment.verdict is LabVerdict.REJECTED
    blocker = next(i for i in assessment.blocking if i.name == "parameter_plateau")
    assert "FRAGILE_SPIKE" in blocker.observed


def test_an_absent_neighbourhood_is_not_evaluable_and_not_a_pass() -> None:
    assessment = _assess(plateau=None)
    criterion = next(i for i in assessment.criteria if i.name == "parameter_plateau")
    assert criterion.passed is None
    assert assessment.verdict is not LabVerdict.CANDIDATE_FOR_FORWARD_TEST


def test_an_unproven_lookahead_suite_blocks_promotion() -> None:
    assessment = _assess(no_lookahead_proven=False)
    assert assessment.verdict is LabVerdict.REJECTED
    assert "no_lookahead" in {item.name for item in assessment.blocking}


def test_metrics_from_different_policies_cannot_be_judged_as_one_variant() -> None:
    """Three unrelated samples judged as one verdict is the silent-misalignment bug."""
    with pytest.raises(SwingLabError, match="cannot be one"):
        _assess(holdout=_mixed("some_other_policy:holdout", 15, 10))


def test_the_verdict_carries_the_cost_scenario_it_was_decided_under() -> None:
    """A page must never present a frictionless verdict as a cost-inclusive one."""
    assessment = _assess()
    assert assessment.cost_policy_id == "swing-lab-conservative-10bps"
    assert "swing-lab-conservative-10bps" in assessment.statement


def test_the_assessment_payload_carries_every_criterion_not_just_the_verdict() -> None:
    payload = _assess(development_symbol_share=Decimal("0.55")).payload()
    assert len(payload["criteria"]) == len(_assess().criteria)
    assert payload["plateau"]["classification"] == "robust_plateau"


def test_the_study_level_index_counts_what_blocked_what() -> None:
    """A milestone blocked on expectancy learned something different from one blocked on plateau."""
    tally = criteria_index(
        [
            _assess(no_lookahead_proven=False),
            _assess(development_symbol_share=Decimal("0.9")),
            _assess(development_symbol_share=Decimal("0.9")),
        ]
    )
    assert tally["symbol_concentration"] == 2
    assert tally["no_lookahead"] == 1
