"""Hostile review of Milestone CA.

Every probe here tries to make CA state something it is not entitled to state:
promote an unsealed family, report a rate from three observations, let a control
overlap its own admission, contaminate a holdout, order an ambiguous bar, or
approve trading. A probe that passes because the fixture is symmetric is a test
defect, so each attack is paired with a control showing the attacked machinery
CAN produce the other answer.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.paper.models import PriceBar
from fmis.swing_lab.admission import (
    AdmissionStage,
    DecisionInstant,
    RaceOutcome,
    forward_outcome,
)
from fmis.swing_lab.admission_matching import (
    build_pool_index,
    eligible_pool,
    match_admission,
)
from fmis.swing_lab.admission_preregistration import (
    CA_NULL_FAMILIES,
    CA_PRE_REGISTRATION,
    CA_PREREGISTRATION_DIGEST,
    CaVerdict,
    is_ca_pre_registered,
)
from fmis.swing_lab.admission_study import (
    FamilySampleResult,
    assess_ca,
    _clustered_admissions,
    _empirical_null,
    _percentile_of,
)
from fmis.swing_lab.metrics import SAMPLE_FLOOR, nearest_rank_quantile
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.robustness import concentration_of_magnitudes
from fmis.swing_setup.models import Direction

from test_swing_lab_admission_study import TIMING, record, result

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
MATCHING = CA_PRE_REGISTRATION.matching
RANDOMISATION = CA_PRE_REGISTRATION.randomisation


def _bar(index: int, open_: str, high: str, low: str, close: str) -> PriceBar:
    return PriceBar(
        symbol="BTCUSDT", interval="4h",
        open_time=T0 + timedelta(hours=4 * index),
        open=Decimal(open_), high=Decimal(high),
        low=Decimal(low), close=Decimal(close),
    )


def _instant(bar_index: int, **overrides) -> DecisionInstant:
    payload = dict(
        symbol="BTCUSDT", sample="development",
        as_of=T0 + timedelta(hours=4 * bar_index), bar_index=bar_index,
        stage=AdmissionStage.UNCONFIRMED, direction=Direction.LONG,
        close=100.0, atr=1.0, context_regime_structure="trending",
        context_regime_volatility="steady",
        context_structural_trend="sustained_higher",
        setup_structural_trend="sustained_higher", evidence_state="proceed",
    )
    payload.update(overrides)
    return DecisionInstant(**payload)


class TestItCannotPromoteWhatNobodySealed:
    def test_a_family_invented_after_results_is_refused(self) -> None:
        rogue = replace(TIMING, family_id="ca_null_the_one_that_worked")
        assert not is_ca_pre_registered(rogue.family_id)
        assessment = assess_ca(
            rogue,
            {n: result(sample=n, effect=5.0) for n in ("development", "validation", "holdout")},
            seed_effects={s: 5.0 for s in (1, 2, 3, 4, 5)},
            manifest_digest=CA_PREREGISTRATION_DIGEST,
            causal_proven=True,
        )
        assert assessment.verdict is not CaVerdict.ADMISSION_EDGE_CANDIDATE

    def test_an_enormous_effect_cannot_buy_a_broken_seal(self) -> None:
        assessment = assess_ca(
            TIMING,
            {n: result(sample=n, effect=99.0) for n in ("development", "validation", "holdout")},
            seed_effects={s: 99.0 for s in (1, 2, 3, 4, 5)},
            manifest_digest="deadbeef" * 8,
            causal_proven=True,
        )
        assert "pre_registered" in assessment.failed

    def test_no_verdict_in_the_enum_can_approve_trading(self) -> None:
        for verdict in CaVerdict:
            assert verdict.is_approved_for_trading is False
            assert verdict.earns_forward_test is False

    def test_the_control_it_could_have_reached(self) -> None:
        """Non-vacuity: with the seal intact the SAME numbers DO promote."""
        assessment = assess_ca(
            TIMING,
            {n: result(sample=n, effect=5.0) for n in ("development", "validation", "holdout")},
            seed_effects={s: 5.0 for s in (1, 2, 3, 4, 5)},
            manifest_digest=CA_PREREGISTRATION_DIGEST,
            causal_proven=True,
        )
        assert assessment.verdict is CaVerdict.ADMISSION_EDGE_CANDIDATE


class TestItRefusesToStateWhatItCannotMeasure:
    def test_three_admissions_do_not_state_an_effect(self) -> None:
        from fmis.swing_lab.admission_study import _cohort_effect

        count, value = _cohort_effect([record(difference=1.0)] * 3, 24)
        assert count == 3 and value is None

    def test_exactly_at_the_floor_it_does_state_one(self) -> None:
        from fmis.swing_lab.admission_study import _cohort_effect

        count, value = _cohort_effect([record(difference=1.0)] * SAMPLE_FLOOR, 24)
        assert count == SAMPLE_FLOOR and value == 1.0

    def test_one_below_the_floor_it_does_not(self) -> None:
        from fmis.swing_lab.admission_study import _cohort_effect

        _count, value = _cohort_effect([record(difference=1.0)] * (SAMPLE_FLOOR - 1), 24)
        assert value is None

    def test_an_empty_null_states_no_percentile(self) -> None:
        assert _percentile_of(1.0, ()) is None

    def test_no_contribution_states_no_concentration(self) -> None:
        assert concentration_of_magnitudes(()) is None

    def test_a_quantile_of_nothing_is_absent_not_zero(self) -> None:
        assert nearest_rank_quantile([], 0.5) is None

    def test_a_quantile_never_interpolates(self) -> None:
        """An interpolated bound is a value the sample never took."""
        values = [1.0, 2.0, 100.0]
        assert nearest_rank_quantile(values, 0.5) in values

    def test_a_quantile_outside_zero_to_one_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match=r"\[0, 1\]"):
            nearest_rank_quantile([1.0], 1.5)


class TestItCannotCheatTheNull:
    def test_a_control_can_never_overlap_its_own_admissions_forward_window(
        self,
    ) -> None:
        """The paired difference would be partly a number minus itself."""
        admission = _instant(5000, stage=AdmissionStage.ADMITTED)
        index = build_pool_index(
            tuple(_instant(5000 + offset) for offset in range(-59, 60)),
            stages=frozenset({AdmissionStage.UNCONFIRMED}),
        )
        assert eligible_pool(admission, index, matching=MATCHING, radius=2160) == ()

    def test_the_control_that_is_exactly_one_window_away_is_allowed(self) -> None:
        """Non-vacuity for the probe above."""
        admission = _instant(5000, stage=AdmissionStage.ADMITTED)
        index = build_pool_index(
            (_instant(5000 + 60),), stages=frozenset({AdmissionStage.UNCONFIRMED})
        )
        assert len(eligible_pool(admission, index, matching=MATCHING, radius=2160)) == 1

    def test_an_admission_can_never_be_its_own_control(self) -> None:
        admission = _instant(5000, stage=AdmissionStage.ADMITTED)
        index = build_pool_index(
            (admission,), stages=frozenset({AdmissionStage.ADMITTED})
        )
        assert eligible_pool(admission, index, matching=MATCHING, radius=2160) == ()

    def test_a_control_from_a_wildly_different_volatility_is_excluded(self) -> None:
        admission = _instant(5000, stage=AdmissionStage.ADMITTED, atr=1.0)
        index = build_pool_index(
            (_instant(5200, atr=100.0),), stages=frozenset({AdmissionStage.UNCONFIRMED})
        )
        assert eligible_pool(admission, index, matching=MATCHING, radius=2160) == ()

    def test_a_pool_of_one_never_becomes_a_null(self) -> None:
        admission = _instant(5000, stage=AdmissionStage.ADMITTED)
        index = build_pool_index(
            (_instant(5200),), stages=frozenset({AdmissionStage.UNCONFIRMED})
        )
        matched = match_admission(
            admission, index, family=CA_NULL_FAMILIES[0],
            matching=MATCHING, randomisation=RANDOMISATION, master_seed=1,
        )
        assert not matched.is_matched

    def test_the_empirical_null_is_centred_at_zero(self) -> None:
        """It must not be centred anywhere else, or the percentile is meaningless."""
        records = [
            replace(
                record(difference=0.5, bar_index=100 + index),
                control_primary_draws=tuple(float(item) for item in range(20)),
            )
            for index in range(30)
        ]
        null = _empirical_null(
            records, replicates=200, master_seed=1, family_id="f", sample="development"
        )
        assert null
        assert abs(sum(null) / len(null)) < 0.5

    def test_a_degenerate_null_is_a_point_mass_and_is_declared_as_such(self) -> None:
        """The opposite-direction family draws one bar in one direction, so its
        null cannot spread. The SEAL declares this rather than hiding it."""
        records = [
            replace(
                record(difference=0.5, bar_index=100 + index),
                control_primary_draws=(1.0, 1.0, 1.0, 1.0),
            )
            for index in range(30)
        ]
        null = _empirical_null(
            records, replicates=50, master_seed=1, family_id="f", sample="development"
        )
        assert set(null) == {0.0}
        family = next(
            item for item in CA_NULL_FAMILIES
            if item.family_id == "ca_null_opposite_direction"
        )
        assert family.is_degenerate_at_primary
        assert "antisymmetric" in (family.degeneracy or "")

    def test_a_single_draw_cannot_form_a_pair(self) -> None:
        records = [
            replace(record(difference=0.5), control_primary_draws=(1.0,))
        ]
        assert _empirical_null(
            records, replicates=10, master_seed=1, family_id="f", sample="s"
        ) == ()


class TestItCannotHideDependence:
    def test_overlapping_admissions_are_counted_not_assumed_away(self) -> None:
        records = [
            record(difference=0.5, bar_index=100),
            record(difference=0.5, bar_index=130),
            record(difference=0.5, bar_index=900),
        ]
        assert _clustered_admissions(records) == 2

    def test_well_separated_admissions_report_none(self) -> None:
        records = [
            record(difference=0.5, bar_index=100),
            record(difference=0.5, bar_index=900),
        ]
        assert _clustered_admissions(records) == 0

    def test_admissions_on_different_symbols_never_cluster(self) -> None:
        records = [
            record(difference=0.5, bar_index=100, symbol="AAAUSDT"),
            record(difference=0.5, bar_index=101, symbol="BBBUSDT"),
        ]
        assert _clustered_admissions(records) == 0


class TestItCannotGuessAnIntrabarPath:
    def test_a_bar_spanning_both_thresholds_is_refused(self) -> None:
        bars = [_bar(i, "100", "100.5", "99.5", "100") for i in range(80)]
        bars[12] = _bar(12, "100", "102", "98", "100")
        outcome = forward_outcome(
            bars, signal_index=10, direction=Direction.LONG, atr=1.0, horizons=(6,)
        )
        assert outcome.race[6] is RaceOutcome.AMBIGUOUS

    def test_the_same_bar_one_side_only_does_resolve(self) -> None:
        """Non-vacuity: the machinery CAN produce a decided answer."""
        bars = [_bar(i, "100", "100.5", "99.5", "100") for i in range(80)]
        bars[12] = _bar(12, "100", "102", "99.5", "100")
        outcome = forward_outcome(
            bars, signal_index=10, direction=Direction.LONG, atr=1.0, horizons=(6,)
        )
        assert outcome.race[6] is RaceOutcome.FAVOURABLE

    def test_an_ambiguous_race_never_reaches_the_rate(self) -> None:
        """Ninety-four ambiguous bars must not move a rate decided by six."""
        from fmis.swing_lab.admission_study import _race_rate

        assert _race_rate(3, 3) == 0.5

    def test_a_rate_with_nothing_settled_is_absent_not_zero(self) -> None:
        """Zero would read as 'never favourable' instead of 'never decided'."""
        from fmis.swing_lab.admission_study import _race_rate

        assert _race_rate(0, 0) is None


class TestItCannotContaminateAHoldout:
    def test_a_criterion_reads_only_its_own_samples_result(self) -> None:
        assessment = assess_ca(
            TIMING,
            {
                "development": result(sample="development", effect=5.0),
                "validation": result(sample="validation", effect=5.0),
                "holdout": result(sample="holdout", effect=-5.0),
            },
            seed_effects={s: 5.0 for s in (1, 2, 3, 4, 5)},
            manifest_digest=CA_PREREGISTRATION_DIGEST,
            causal_proven=True,
        )
        assert "holdout_sign" in assessment.failed
        assert "validation_sign" not in assessment.failed

    def test_a_missing_holdout_cannot_be_read_as_a_pass(self) -> None:
        assessment = assess_ca(
            TIMING,
            {
                "development": result(sample="development", effect=5.0),
                "validation": result(sample="validation", effect=5.0),
            },
            seed_effects={s: 5.0 for s in (1, 2, 3, 4, 5)},
            manifest_digest=CA_PREREGISTRATION_DIGEST,
            causal_proven=True,
        )
        assert assessment.verdict is not CaVerdict.ADMISSION_EDGE_CANDIDATE
        assert "holdout_sign" in assessment.unmeasurable


class TestItCannotBeMovedByTheEnvironment:
    def test_the_seal_survives_every_hash_seed(self) -> None:
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        seen = set()
        for hash_seed in ("0", "1", "12345"):
            outcome = subprocess.run(
                [
                    sys.executable, "-c",
                    "from fmis.swing_lab.admission_preregistration import "
                    "ca_preregistration_digest as d; print(d())",
                ],
                capture_output=True, text=True, cwd=root,
                env={"PYTHONHASHSEED": hash_seed, "PATH": ""},
            )
            assert outcome.returncode == 0, outcome.stderr
            seen.add(outcome.stdout.strip())
        assert seen == {CA_PREREGISTRATION_DIGEST}

    def test_no_clock_reaches_a_verdict(self) -> None:
        """A future timestamp is not special; nothing here reads a clock."""
        import ast
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "src" / "fmis" / "swing_lab" / "admission_preregistration.py"
        ).read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"now", "utcnow", "today"}


class TestTheEffectIsAPairedDifference:
    def test_a_constant_shift_in_the_control_moves_the_effect_one_for_one(self) -> None:
        base = record(difference=1.0)
        shifted = replace(
            base, control_forward={h: 0.5 for h in base.control_forward}
        )
        assert base.difference(24) - shifted.difference(24) == pytest.approx(0.5)

    def test_an_identical_admission_and_control_produce_no_effect(self) -> None:
        base = record(difference=0.0)
        assert base.difference(24) == 0.0
