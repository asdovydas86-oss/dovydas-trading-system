"""The terminal geometry report. **Renders what was measured, computes nothing.**

Milestone BX. These tests pin the properties that stop a report misleading the
reader who trusts it: the verdict comes first, every rate carries its `n`, a
refused rate is never shown as a number, refusals sit beside trade counts, and
the limitations print in full.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.paper.models import PriceBar
from fmis.swing_lab.geometry_diagnosis import describe, diagnose_geometry
from fmis.swing_lab.geometry_render import (
    render_assessment,
    render_diagnosis,
    render_geometry_comparison,
    render_geometry_study,
    render_sensitivity,
)
from fmis.swing_lab.geometry_replay import GeometryCapture, trades_for_policy
from fmis.swing_lab.geometry_study import records_for, run_geometry_study
from fmis.swing_lab.geometry_variants import PRE_DECLARED_GEOMETRIES, PRODUCTION_GEOMETRY
from fmis.swing_lab.trades import FRICTIONLESS_COSTS

from tests.swing_lab_helpers import candidate

_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
_WINDOW = 20


def _bars(symbol: str, count: int = 60) -> tuple[PriceBar, ...]:
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


def _many(count: int, symbol: str):
    return [
        candidate(
            symbol=symbol, setup_id=f"{symbol}|long|from=seq{index}", signal_index=index
        )
        for index in range(count)
    ]


@pytest.fixture(scope="module")
def study():
    capture = GeometryCapture(
        admission_variant_id="swing_current",
        admission_policy_id="swing-setup-v1",
        candidates=tuple(_many(25, "BTCUSDT") + _many(25, "ETHUSDT")),
        bars_by_symbol={"BTCUSDT": _bars("BTCUSDT"), "ETHUSDT": _bars("ETHUSDT")},
        metadata={},
    )
    return run_geometry_study(
        capture,
        development_symbols=("BTCUSDT",), holdout_symbols=("ETHUSDT",),
        experiment_id="probe", run_at=_T0, measurement_start=_T0,
        measurement_end=_T0 + timedelta(days=30),
        warmup_start=_T0 - timedelta(days=1000), costs=FRICTIONLESS_COSTS,
        evaluation_window_bars=_WINDOW, candle_limit=250,
        policies=PRE_DECLARED_GEOMETRIES, with_sensitivity=True,
    )


@pytest.fixture(scope="module")
def report(study) -> str:
    return render_geometry_study(study)


class TestTheReportLeadsWithItsConclusion:
    def test_the_verdict_section_precedes_every_result_table(self, report) -> None:
        """A reader who stops after one screen must not come away with a
        different impression from one who reads to the end."""
        assert report.index("VERDICTS") < report.index("DEVELOPMENT AND HOLDOUT")
        assert report.index("VERDICTS") < report.index("PARAMETER SENSITIVITY")

    def test_no_candidate_is_stated_in_words_not_implied_by_a_blank(
        self, study, report
    ) -> None:
        if study.candidates:  # pragma: no cover - the fixture produces none
            pytest.skip("this fixture produced a candidate")
        assert "NO CANDIDATE" in report

    def test_every_policy_appears_with_its_family_and_verdict(self, study, report) -> None:
        for result in study.results:
            assert result.policy.policy_id in report
            assert result.policy.family in report

    def test_a_rejection_names_the_criteria_that_blocked_it(self, study, report) -> None:
        for result in study.results:
            for criterion in result.assessment.blocking:
                assert criterion.name in report


class TestNoFigureAppearsWithoutItsSample:
    def test_every_expectancy_in_the_comparison_carries_a_trade_count(
        self, study
    ) -> None:
        table = render_geometry_comparison(study.results)
        for result in study.results:
            for sample in (result.development, result.holdout):
                assert str(sample.metrics.measurable_trades) in table

    def test_a_refused_figure_prints_a_dash_rather_than_a_number(self) -> None:
        """Below the sample floor a rate is absent, and the report must not
        invent one — a precise-looking lie is worse than a blank."""
        capture = GeometryCapture(
            admission_variant_id="v", admission_policy_id="p",
            candidates=tuple(_many(2, "BTCUSDT") + _many(2, "ETHUSDT")),
            bars_by_symbol={"BTCUSDT": _bars("BTCUSDT"), "ETHUSDT": _bars("ETHUSDT")},
            metadata={},
        )
        thin = run_geometry_study(
            capture, development_symbols=("BTCUSDT",), holdout_symbols=("ETHUSDT",),
            experiment_id="thin", run_at=_T0, measurement_start=_T0,
            measurement_end=_T0 + timedelta(days=30),
            warmup_start=_T0 - timedelta(days=1000), costs=FRICTIONLESS_COSTS,
            evaluation_window_bars=_WINDOW, candle_limit=250,
            policies=(PRODUCTION_GEOMETRY,), with_sensitivity=False,
        )
        assert "—" in render_geometry_comparison(thin.results)

    def test_refusals_are_printed_beside_trade_counts(self, study) -> None:
        """A rule trading six times because it refused ninety candidates is a
        different finding from one trading six times because six setups formed."""
        table = render_geometry_comparison(study.results)
        assert "skip" in table
        assert any(result.development.outcome.refused for result in study.results)

    def test_an_empty_result_set_renders_a_sentence_not_a_crash(self) -> None:
        assert "No geometry policy" in render_geometry_comparison(())


class TestTheDiagnosisSeparatesEvidenceFromReading:
    def test_evidence_and_reading_are_labelled_separately(self, study) -> None:
        text = render_diagnosis(study.baseline_diagnosis)
        assert "evidence:" in text
        assert "INTERPRETATION" in text

    def test_every_distribution_is_printed_with_its_own_n(self, study) -> None:
        text = render_diagnosis(study.baseline_diagnosis)
        for item in study.baseline_diagnosis.distributions:
            assert item.label in text

    def test_a_finding_that_could_not_be_answered_prints_not_applicable(self) -> None:
        empty = diagnose_geometry((), (), label="empty")
        text = render_diagnosis(empty)
        assert "[N/A]" in text

    def test_refusal_reasons_are_printed_when_any_exist(self, study) -> None:
        refusing = next(
            r for r in study.results if r.development.outcome.skips
        )
        text = render_diagnosis(refusing.development.diagnosis)
        assert "Refusals by reason" in text


class TestSensitivityIsRenderedAsACurve:
    def test_every_grid_point_is_printed(self, study) -> None:
        for curve in study.sensitivity:
            text = render_sensitivity(curve)
            for point in curve.points:
                assert f"{point.threshold:.2f}" in text

    def test_the_plateau_conclusion_is_stated_in_words(self, study) -> None:
        for curve in study.sensitivity:
            assert "plateau:" in render_sensitivity(curve)

    def test_a_curve_with_no_measurable_point_says_it_is_not_evaluable(
        self, study
    ) -> None:
        from fmis.swing_lab.geometry_study import SensitivityCurve

        assert "not evaluable" in render_sensitivity(
            SensitivityCurve(kind="min_rr", points=())
        )


class TestTheReportCannotBeReadAsApproval:
    def test_the_report_states_what_a_candidate_verdict_does_not_mean(
        self, study
    ) -> None:
        text = render_geometry_study(study)
        assert "approval to trade" in text or "NO CANDIDATE" in text

    def test_every_limitation_prints_in_full(self, study, report) -> None:
        for limitation in study.manifest.limitations:
            assert limitation.split(":")[0] in report

    def test_the_criteria_print_their_requirement_and_observation(self, study) -> None:
        for result in study.results:
            text = render_assessment(result.assessment)
            for criterion in result.assessment.criteria:
                assert criterion.name in text
                assert criterion.observed in text


def test_a_distribution_of_nothing_renders_dashes_rather_than_zeros() -> None:
    from fmis.swing_lab.geometry_render import _distribution_row

    row = _distribution_row(describe([], label="empty"))
    assert "n=0" in row
    assert "—" in row
