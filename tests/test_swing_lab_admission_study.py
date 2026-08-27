"""Milestone CA's statistics and its verdict rules.

The verdict is where a milestone either holds its own bar or quietly lowers it.
These tests build synthetic paired records with known effects and assert that
each sealed criterion passes, fails or REFUSES exactly when it should — and, in
particular, that a criterion which could not be evaluated is never reported as a
refutation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fmis.swing_lab.admission import FORWARD_HORIZONS
from fmis.swing_lab.admission_preregistration import (
    CA_EDGE_CRITERIA,
    CA_NULL_FAMILIES,
    CA_PRE_REGISTRATION,
    CA_PREREGISTRATION_DIGEST,
    MIN_ADMISSION_EDGE_ATR,
    PRIMARY_HORIZON,
    CaVerdict,
)
from fmis.swing_lab.admission_study import (
    NO_DIRECTION_TO_NORMALISE,
    AdmissionStudy,
    CaAssessment,
    Criterion,
    FamilySampleResult,
    PairedRecord,
    assess_ca,
)
from fmis.swing_lab.metrics import SAMPLE_FLOOR
from fmis.swing_lab.models import SwingLabError
from fmis.swing_setup.models import Direction

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
FAMILY = {item.family_id: item for item in CA_NULL_FAMILIES}
TIMING = FAMILY["ca_null_matched_timing"]


def record(
    *,
    difference: float,
    symbol: str = "BTCUSDT",
    bar_index: int = 100,
    direction: Direction = Direction.LONG,
    sample: str = "development",
) -> PairedRecord:
    admission = {h: difference for h in FORWARD_HORIZONS}
    control = {h: 0.0 for h in FORWARD_HORIZONS}
    return PairedRecord(
        family_id=TIMING.family_id,
        sample=sample,
        symbol=symbol,
        bar_index=bar_index,
        as_of=T0 + timedelta(hours=4 * bar_index),
        direction=direction,
        segment=None,
        volatility="steady",
        pool_size=100,
        radius_tier=0,
        admission_forward=admission,
        admission_mfe={h: abs(difference) for h in FORWARD_HORIZONS},
        admission_mae={h: -abs(difference) for h in FORWARD_HORIZONS},
        admission_race={h: None for h in FORWARD_HORIZONS},  # type: ignore[dict-item]
        control_forward=control,
        control_mfe=control,
        control_mae=control,
        control_race_favourable={h: 0 for h in FORWARD_HORIZONS},
        control_race_adverse={h: 0 for h in FORWARD_HORIZONS},
        control_race_ambiguous={h: 0 for h in FORWARD_HORIZONS},
        control_primary_draws=(0.0, 0.0),
    )


def result(
    *,
    sample: str,
    effect: float | None,
    matched: int = 100,
    percentile: float | None = 99.0,
    boot_low: float | None = 0.05,
    concentration: float | None = 0.2,
    directions: dict | None = None,
    horizons: dict | None = None,
    windows=None,
) -> FamilySampleResult:
    return FamilySampleResult(
        family_id=TIMING.family_id,
        sample=sample,
        matched=matched,
        unmatched=0,
        symbols=15,
        effect=effect,
        effect_by_horizon=(
            horizons if horizons is not None else {h: effect for h in FORWARD_HORIZONS}
        ),
        bootstrap_low=boot_low,
        bootstrap_high=None if boot_low is None else boot_low + 1.0,
        null_percentile=percentile,
        null_low=-0.1,
        null_high=0.1,
        concentration=concentration,
        by_direction=(
            directions
            if directions is not None
            else {"long": (60, effect), "short": (40, effect)}
        ),
        by_volatility={},
        by_symbol_class={},
        walk_forward=(
            windows if windows is not None else (("w1", 50, effect), ("w2", 50, effect))
        ),
        radius_tiers={"tier_0": matched},
        admission_mean_mfe={},
        admission_mean_mae={},
        control_mean_mfe={},
        control_mean_mae={},
        admission_positive_rate={},
        admission_race_rate={},
        control_race_rate={},
        race_ambiguous={},
        clustered_admissions=0,
    )


def _passing_results(effect: float = 0.5) -> dict[str, FamilySampleResult]:
    return {
        name: result(sample=name, effect=effect)
        for name in ("development", "validation", "holdout")
    }


def _assess(results, *, seeds=None, causal=True, digest=CA_PREREGISTRATION_DIGEST):
    return assess_ca(
        TIMING,
        results,
        seed_effects=seeds if seeds is not None else {s: 0.5 for s in (1, 2, 3, 4, 5)},
        manifest_digest=digest,
        causal_proven=causal,
    )


class TestTheVerdictHoldsItsOwnBar:
    def test_everything_passing_reaches_the_candidate_verdict(self) -> None:
        assessment = _assess(_passing_results())
        assert assessment.verdict is CaVerdict.ADMISSION_EDGE_CANDIDATE
        assert assessment.failed == ()

    def test_the_candidate_verdict_still_approves_nothing(self) -> None:
        assessment = _assess(_passing_results())
        assert assessment.verdict.is_approved_for_trading is False
        assert assessment.verdict.earns_forward_test is False

    def test_every_sealed_criterion_is_evaluated(self) -> None:
        """A criterion that quietly evaporated would be a lowered bar."""
        assessment = _assess(_passing_results())
        assert [item.name for item in assessment.criteria] == [
            item.name for item in CA_EDGE_CRITERIA
        ]

    def test_a_development_effect_below_the_bar_fails(self) -> None:
        results = _passing_results()
        results["development"] = result(
            sample="development", effect=MIN_ADMISSION_EDGE_ATR - 0.001
        )
        assessment = _assess(results)
        assert "development_effect" in assessment.failed
        assert assessment.verdict is CaVerdict.NO_EDGE

    def test_the_bar_is_inclusive_at_exactly_the_threshold(self) -> None:
        results = _passing_results()
        results["development"] = result(
            sample="development", effect=MIN_ADMISSION_EDGE_ATR
        )
        assert "development_effect" not in _assess(results).failed

    def test_a_negative_validation_sign_fails(self) -> None:
        results = _passing_results()
        results["validation"] = result(sample="validation", effect=-0.2)
        assessment = _assess(results)
        assert "validation_sign" in assessment.failed

    def test_a_negative_holdout_sign_fails(self) -> None:
        results = _passing_results()
        results["holdout"] = result(sample="holdout", effect=-0.2)
        assert "holdout_sign" in _assess(results).failed

    def test_development_only_success_is_mechanism_evidence_never_a_candidate(
        self,
    ) -> None:
        """The brief's CASE 5: development positive, unseen samples fail."""
        results = _passing_results()
        results["validation"] = result(sample="validation", effect=-0.2)
        results["holdout"] = result(sample="holdout", effect=-0.3)
        assessment = _assess(results)
        assert assessment.verdict is CaVerdict.MECHANISM_EVIDENCE
        assert assessment.verdict.earns_forward_test is False

    def test_an_unsealed_family_can_never_be_promoted(self) -> None:
        from dataclasses import replace

        rogue = replace(TIMING, family_id="ca_null_invented_after_results")
        assessment = assess_ca(
            rogue,
            _passing_results(),
            seed_effects={s: 0.5 for s in (1, 2, 3, 4, 5)},
            manifest_digest=CA_PREREGISTRATION_DIGEST,
            causal_proven=True,
        )
        assert "pre_registered" in assessment.failed
        assert assessment.verdict is not CaVerdict.ADMISSION_EDGE_CANDIDATE

    def test_a_tampered_seal_can_never_be_promoted(self) -> None:
        assessment = _assess(_passing_results(), digest="0" * 64)
        assert "pre_registered" in assessment.failed

    def test_an_unproven_causality_claim_blocks_promotion(self) -> None:
        assessment = _assess(_passing_results(), causal=False)
        assert "causal" in assessment.failed

    def test_a_foreign_family_type_is_refused(self) -> None:
        with pytest.raises(TypeError):
            assess_ca(
                object(), {}, seed_effects={}, manifest_digest="x", causal_proven=True  # type: ignore[arg-type]
            )


class TestAnUnrunTestIsNeverARefutation:
    """Milestone BZ recorded this as defect BZ-D1 and fixed it. CA inherits the
    rule: below the floor a criterion is UNMEASURABLE, never False."""

    def test_a_thin_sample_refuses_rather_than_fails(self) -> None:
        results = _passing_results()
        results["holdout"] = result(
            sample="holdout", effect=0.5, matched=SAMPLE_FLOOR - 1
        )
        assessment = _assess(results)
        assert "sample" not in assessment.failed
        assert "sample" in assessment.unmeasurable
        assert assessment.verdict is CaVerdict.INCONCLUSIVE

    def test_exactly_at_the_floor_is_measured(self) -> None:
        results = _passing_results()
        results["holdout"] = result(sample="holdout", effect=0.5, matched=SAMPLE_FLOOR)
        assert "sample" not in _assess(results).unmeasurable

    def test_a_missing_sample_refuses_rather_than_fails(self) -> None:
        results = _passing_results()
        del results["holdout"]
        assessment = _assess(results)
        assert "holdout_sign" in assessment.unmeasurable
        assert "holdout_sign" not in assessment.failed

    def test_a_direction_cohort_below_the_floor_refuses(self) -> None:
        results = _passing_results()
        results["development"] = result(
            sample="development",
            effect=0.5,
            directions={"long": (5, None), "short": (4, None)},
        )
        assessment = _assess(results)
        assert "long_short_consistent" in assessment.unmeasurable
        assert "long_short_consistent" not in assessment.failed

    def test_a_direction_cohort_disagreeing_in_sign_does_fail(self) -> None:
        """Non-vacuity for the test above: a measurable cohort CAN fail."""
        results = _passing_results()
        results["development"] = result(
            sample="development",
            effect=0.5,
            directions={"long": (60, 0.9), "short": (40, -0.4)},
        )
        assert "long_short_consistent" in _assess(results).failed

    def test_an_inconclusive_verdict_is_not_no_edge(self) -> None:
        results = _passing_results()
        results["holdout"] = result(
            sample="holdout", effect=0.5, matched=SAMPLE_FLOOR - 1
        )
        assert _assess(results).verdict is not CaVerdict.NO_EDGE


class TestTheRobustnessCriteria:
    def test_an_effect_inside_its_own_null_fails(self) -> None:
        results = _passing_results()
        results["development"] = result(sample="development", effect=0.5, percentile=50.0)
        assert "null_percentile" in _assess(results).failed

    def test_a_bootstrap_interval_containing_zero_fails(self) -> None:
        results = _passing_results()
        results["development"] = result(sample="development", effect=0.5, boot_low=-0.01)
        assert "bootstrap_excludes_zero" in _assess(results).failed

    def test_one_symbol_dominating_fails(self) -> None:
        results = _passing_results()
        results["development"] = result(
            sample="development", effect=0.5, concentration=0.55
        )
        assert "concentration" in _assess(results).failed

    def test_exactly_at_the_concentration_bound_passes(self) -> None:
        results = _passing_results()
        results["development"] = result(
            sample="development", effect=0.5, concentration=0.40
        )
        assert "concentration" not in _assess(results).failed

    def test_a_sign_that_changes_between_seeds_fails(self) -> None:
        assessment = _assess(
            _passing_results(), seeds={1: 0.5, 2: 0.4, 3: -0.1, 4: 0.2, 5: 0.3}
        )
        assert "seed_stable" in assessment.failed

    def test_a_primary_contradicted_by_its_horizon_profile_fails(self) -> None:
        results = _passing_results()
        results["development"] = result(
            sample="development",
            effect=0.5,
            horizons={1: -0.2, 3: -0.2, 6: -0.2, 12: -0.1, 24: 0.5, 60: -0.3},
        )
        assert "horizon_profile" in _assess(results).failed

    def test_a_profile_agreeing_on_four_of_six_passes(self) -> None:
        results = _passing_results()
        results["development"] = result(
            sample="development",
            effect=0.5,
            horizons={1: -0.2, 3: -0.2, 6: 0.1, 12: 0.1, 24: 0.5, 60: 0.3},
        )
        assert "horizon_profile" not in _assess(results).failed

    def test_a_walk_forward_curve_mostly_disagreeing_fails(self) -> None:
        results = _passing_results()
        results["development"] = result(
            sample="development",
            effect=0.5,
            windows=(("a", 10, -0.2), ("b", 10, -0.3), ("c", 10, 0.4)),
        )
        assert "walk_forward" in _assess(results).failed

    def test_empty_walk_forward_windows_are_ignored_not_counted(self) -> None:
        results = _passing_results()
        results["development"] = result(
            sample="development",
            effect=0.5,
            windows=(("a", 0, None), ("b", 10, 0.4), ("c", 10, 0.6)),
        )
        assert "walk_forward" not in _assess(results).failed


class TestTheStudySurface:
    def _study(self, verdicts) -> AdmissionStudy:
        return AdmissionStudy(
            manifest={"preregistration_digest": CA_PREREGISTRATION_DIGEST},
            results={},
            assessments={
                f"family_{index}": CaAssessment(
                    family_id=f"family_{index}",
                    verdict=verdict,
                    criteria=(Criterion("x", True, "y"),),
                )
                for index, verdict in enumerate(verdicts)
            },
            gate_ladder=(),
            seed_effects={},
            control_identity_digest={},
        )

    def test_the_headline_is_the_strongest_verdict_reached(self) -> None:
        study = self._study(
            [CaVerdict.NO_EDGE, CaVerdict.MECHANISM_EVIDENCE, CaVerdict.INCONCLUSIVE]
        )
        assert study.headline is CaVerdict.MECHANISM_EVIDENCE

    def test_all_rejected_reads_as_no_edge(self) -> None:
        assert self._study([CaVerdict.NO_EDGE] * 3).headline is CaVerdict.NO_EDGE

    def test_candidates_lists_only_candidates(self) -> None:
        study = self._study(
            [CaVerdict.ADMISSION_EDGE_CANDIDATE, CaVerdict.NO_EDGE]
        )
        assert study.candidates == ("family_0",)

    def test_the_limitations_travel_with_every_study(self) -> None:
        study = self._study([CaVerdict.NO_EDGE])
        assert study.limitations is CA_PRE_REGISTRATION.limitations

    def test_the_payload_is_json_safe(self) -> None:
        import json

        json.dumps(self._study([CaVerdict.NO_EDGE]).payload())


class TestThePairedRecord:
    def test_the_difference_is_admission_minus_control(self) -> None:
        assert record(difference=0.75).difference(PRIMARY_HORIZON) == 0.75

    def test_an_unmeasured_horizon_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="holds no horizon"):
            record(difference=0.5).difference(999)

    def test_the_symbol_class_is_milestone_bys(self) -> None:
        assert record(difference=0.5, symbol="BTCUSDT").symbol_class == "major"
        assert record(difference=0.5, symbol="ZILUSDT").symbol_class == "non_major"


def test_the_direction_less_rungs_state_their_refusal() -> None:
    assert "refused" in NO_DIRECTION_TO_NORMALISE
    assert "NOT" in NO_DIRECTION_TO_NORMALISE


class TestDefectsFoundByIndependentReview:
    """Regressions for the three defects the independent review confirmed."""

    def _aggregate_over(self, count: int):
        from fmis.swing_lab.admission_study import _aggregate
        from fmis.swing_lab.admission_matching import MatchedAdmission
        from fmis.swing_lab.preregistration import SAMPLES

        records = [
            record(difference=-0.02, bar_index=1000 + index * 200)
            for index in range(count)
        ]
        attempts = [
            MatchedAdmission(
                admission=None, family_id=TIMING.family_id, draws=(),
                pool_size=100, radius_tier=0,
            )
            for _ in range(count)
        ]
        return _aggregate(
            records,
            attempts,
            family=TIMING,
            sample=next(s for s in SAMPLES if s.name == "development"),
            horizons=FORWARD_HORIZONS,
            master_seed=1,
        )

    def test_ca_d1_a_below_floor_effect_is_absent_not_stated(self) -> None:
        """The headline effect was the one figure exempt from SAMPLE_FLOOR, so a
        three-admission family could be REFUTED by a test its own `sample`
        criterion said could not be run. BZ recorded this class as BZ-D1."""
        thin = self._aggregate_over(3)
        assert thin.matched == 3
        assert thin.effect is None
        assert all(value is None for value in thin.effect_by_horizon.values())

    def test_ca_d1_at_the_floor_the_effect_is_stated(self) -> None:
        """Non-vacuity: the guard must not suppress a measurable effect."""
        fat = self._aggregate_over(SAMPLE_FLOOR)
        assert fat.matched == SAMPLE_FLOOR
        assert fat.effect == pytest.approx(-0.02)

    def test_ca_d1_a_thin_family_is_inconclusive_not_no_edge(self) -> None:
        """The verdict a refuted-but-unmeasured family must now reach."""
        thin = {
            name: result(sample=name, effect=None, matched=3, percentile=None,
                         boot_low=None, concentration=None,
                         directions={"long": (2, None), "short": (1, None)},
                         horizons={h: None for h in FORWARD_HORIZONS},
                         windows=(("w1", 3, None),))
            for name in ("development", "validation", "holdout")
        }
        assessment = _assess(thin, seeds={s: None for s in (1, 2, 3, 4, 5)})
        assert assessment.failed == ()
        assert assessment.verdict is CaVerdict.INCONCLUSIVE

    def test_ca_d2_a_strided_rung_reports_what_it_measured(self) -> None:
        """`count` is the full rung; `measured` is what the means came from. A
        count-weighted aggregation of a strided mean would misweight by `stride`."""
        from fmis.swing_lab.admission_study import GateRung

        rung = GateRung(
            stage="regime_blocked", sample="development:BTCUSDT", count=1000,
            directional=False, mean_forward=None, mean_absolute_move=0.5,
            measured=40,
        )
        assert rung.payload()["count"] == 1000
        assert rung.payload()["measured"] == 40

    def test_ca_d3_a_family_refuses_a_pool_its_seal_does_not_name(self) -> None:
        """`ca_null_eligible_but_rejected` handed a broad index would silently
        measure a different null under a sealed family's id."""
        from fmis.swing_lab.admission import AdmissionStage, DecisionInstant
        from fmis.swing_lab.admission_matching import build_pool_index, match_admission
        from fmis.swing_lab.admission_preregistration import CA_PRE_REGISTRATION
        from datetime import datetime, timedelta, timezone

        base = datetime(2026, 1, 1, tzinfo=timezone.utc)

        def instant(index: int, stage: AdmissionStage) -> DecisionInstant:
            return DecisionInstant(
                symbol="BTCUSDT", sample="development",
                as_of=base + timedelta(hours=4 * index), bar_index=index,
                stage=stage,
                direction=Direction.LONG if stage.has_direction else None,
                close=100.0, atr=1.0, context_regime_structure="trending",
                context_regime_volatility="steady",
                context_structural_trend="sustained_higher",
                setup_structural_trend="sustained_higher", evidence_state="proceed",
            )

        admission = instant(2000, AdmissionStage.ADMITTED)
        wrong = build_pool_index(
            tuple(instant(2000 + 60 + i * 5, AdmissionStage.CONFIRMED_REPEAT)
                  for i in range(40)),
            stages=frozenset({AdmissionStage.CONFIRMED_REPEAT}),
        )
        gate = next(
            item for item in CA_NULL_FAMILIES
            if item.family_id == "ca_null_eligible_but_rejected"
        )
        with pytest.raises(SwingLabError, match="does not name"):
            match_admission(
                admission, wrong, family=gate,
                matching=CA_PRE_REGISTRATION.matching,
                randomisation=CA_PRE_REGISTRATION.randomisation, master_seed=1,
            )

    def test_ca_d3_the_correct_pool_is_accepted(self) -> None:
        """Non-vacuity for the probe above."""
        from fmis.swing_lab.admission import AdmissionStage, DecisionInstant
        from fmis.swing_lab.admission_matching import build_pool_index, match_admission
        from fmis.swing_lab.admission_preregistration import CA_PRE_REGISTRATION
        from datetime import datetime, timedelta, timezone

        base = datetime(2026, 1, 1, tzinfo=timezone.utc)

        def instant(index: int, stage: AdmissionStage) -> DecisionInstant:
            return DecisionInstant(
                symbol="BTCUSDT", sample="development",
                as_of=base + timedelta(hours=4 * index), bar_index=index,
                stage=stage,
                direction=Direction.LONG if stage.has_direction else None,
                close=100.0, atr=1.0, context_regime_structure="trending",
                context_regime_volatility="steady",
                context_structural_trend="sustained_higher",
                setup_structural_trend="sustained_higher", evidence_state="proceed",
            )

        right = build_pool_index(
            tuple(instant(2000 + 60 + i * 5, AdmissionStage.UNCONFIRMED)
                  for i in range(40)),
            stages=frozenset({AdmissionStage.UNCONFIRMED}),
        )
        gate = next(
            item for item in CA_NULL_FAMILIES
            if item.family_id == "ca_null_eligible_but_rejected"
        )
        matched = match_admission(
            instant(2000, AdmissionStage.ADMITTED), right, family=gate,
            matching=CA_PRE_REGISTRATION.matching,
            randomisation=CA_PRE_REGISTRATION.randomisation, master_seed=1,
        )
        assert matched.is_matched
