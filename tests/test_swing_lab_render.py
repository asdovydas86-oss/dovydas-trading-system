"""The terminal report: states its samples, its caveats, and promotes nothing."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from fmis.swing_lab.metrics import LabMeasure, compute_lab_metrics
from fmis.swing_lab.models import LabVariant, SwingLabError
from fmis.swing_lab.render import (
    render_comparison_table,
    render_gate_impact,
    render_robustness,
    render_study,
)
from fmis.swing_lab.robustness import measure_robustness
from fmis.swing_lab.study import run_lab_study
from fmis.swing_lab.variants import PRODUCTION_INTERVALS

from tests.test_swing_lab_artifact import T0, build_study, trade


@pytest.fixture
def study():
    return build_study()


class TestTheComparisonTable:
    def test_every_figure_carries_its_sample(self, study) -> None:
        rendered = render_comparison_table(
            tuple(result.metrics for result in study.results)
        )
        for line in rendered.splitlines():
            if line.startswith(("Win rate", "Expectancy", "Median R", "Profit factor")):
                assert "n=" in line, line

    def test_an_absent_figure_shows_its_sample_too(self) -> None:
        """A blank cell must never hide how thin the cohort was."""
        metrics = compute_lab_metrics([trade("v", 0)], label="thin")
        rendered = render_comparison_table((metrics,))
        assert "—" in rendered
        assert "n=1" in rendered

    def test_an_empty_metric_set_renders_a_sentence_not_a_crash(self) -> None:
        assert render_comparison_table(()) == "No variant produced a result."

    def test_a_long_variant_label_does_not_collide_with_the_next_column(self) -> None:
        long_label = "swing_" + "x" * 40
        metrics = (
            compute_lab_metrics([trade("a", 0)], label=long_label),
            compute_lab_metrics([trade("b", 1)], label="short"),
        )
        header = render_comparison_table(metrics).splitlines()[0]
        assert long_label in header
        assert header.index("short") > header.index(long_label) + len(long_label)

    def test_the_ambiguous_count_is_always_shown(self, study) -> None:
        rendered = render_comparison_table(
            tuple(result.metrics for result in study.results)
        )
        assert "Ambiguous" in rendered


class TestTheGateSection:
    def test_the_two_block_counts_are_reported_separately(self, study) -> None:
        rendered = render_gate_impact(study.gate)
        assert "Blocked, total" in rendered
        assert "Materially blocked" in rendered
        assert "removing a CONFIRMED setup" in rendered

    def test_an_absent_counterfactual_says_so(self, study) -> None:
        rendered = render_gate_impact(study.gate)
        assert "absent comparison" in rendered or "measured through the identical" in rendered


class TestTheStudyReport:
    def test_the_report_states_the_window_and_the_digest(self, study) -> None:
        rendered = render_study(study)
        assert study.manifest.result_digest in rendered
        assert "Measurement window" in rendered
        assert "Warm-up from" in rendered

    def test_every_variant_prints_its_hypothesis_and_policy_id(self, study) -> None:
        rendered = render_study(study)
        for result in study.results:
            assert result.variant.variant_id in rendered
            assert result.variant.policy_id in rendered

    def test_the_limitations_are_printed_in_full(self, study) -> None:
        rendered = render_study(study)
        assert "BW-2" in rendered
        assert "BW-4" in rendered
        assert "BW-7" in rendered

    def test_the_report_refuses_to_promote_anything(self, study) -> None:
        rendered = render_study(study)
        assert "NOTHING HERE IS A PROMOTION" in rendered
        # Normalised: the closing note is wrapped, so the phrase spans a line
        # break. Asserting on the raw text would pass or fail on column width.
        flattened = " ".join(rendered.split())
        assert "candidate for forward testing" in flattened
        assert "production strategy is unchanged by this run" in flattened

    def test_the_cost_basis_is_printed_beside_the_numbers(self, study) -> None:
        assert "fee rate" in render_study(study)


class TestRobustnessRendering:
    def test_a_split_states_whether_its_cohorts_agree(self, study) -> None:
        reading = measure_robustness(
            study.results[0].trades,
            variant_id="v",
            measurement_start=T0,
            measurement_end=T0 + timedelta(days=365),
        )
        rendered = render_robustness(reading)
        assert "Cohorts agree on sign:" in rendered
        assert "chronological" in rendered
        assert "walk_forward" in rendered

    def test_an_untestable_agreement_says_so_rather_than_claiming_yes(
        self, study
    ) -> None:
        reading = measure_robustness(
            study.results[0].trades,
            variant_id="v",
            measurement_start=T0,
            measurement_end=T0 + timedelta(days=365),
        )
        assert "not testable" in render_robustness(reading)

    def test_concentration_is_reported(self, study) -> None:
        reading = measure_robustness(
            study.results[0].trades,
            variant_id="v",
            measurement_start=T0,
            measurement_end=T0 + timedelta(days=365),
        )
        assert "Largest symbol share" in render_robustness(reading)


class TestStudyRefusals:
    """`run_lab_study` validates before it fetches, so a bad call costs no network."""

    def _call(self, **overrides):
        kwargs = dict(
            symbols=["BTCUSDT"],
            measurement_start=T0,
            measurement_end=T0 + timedelta(days=365),
            run_at=T0,
            experiment_id="x",
        )
        kwargs.update(overrides)
        return run_lab_study(**kwargs)

    def test_a_string_universe_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="non-string sequence"):
            self._call(symbols="BTCUSDT")

    def test_an_empty_universe_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="non-empty"):
            self._call(symbols=[])

    def test_a_naive_run_instant_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="timezone-aware"):
            self._call(run_at=T0.replace(tzinfo=None))

    def test_an_inverted_window_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="must be after"):
            self._call(measurement_end=T0 - timedelta(days=1))

    def test_a_blank_experiment_id_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="experiment_id"):
            self._call(experiment_id="   ")

    def test_a_non_policy_cost_is_refused(self) -> None:
        with pytest.raises(TypeError, match="PaperCostPolicy"):
            self._call(costs="free")

    def test_an_unknown_variant_in_a_study_is_refused(self, study) -> None:
        with pytest.raises(SwingLabError, match="holds no variant"):
            study.result_for("swing_nonexistent")


class TestVariantValidation:
    def _variant(self, **overrides) -> LabVariant:
        kwargs = dict(
            variant_id="v",
            title="t",
            hypothesis="h",
            context_role=None,
            max_confirmation_age=None,
            timeframes=PRODUCTION_INTERVALS,
        )
        kwargs.update(overrides)
        return LabVariant(**kwargs)

    @pytest.mark.parametrize("field", ["variant_id", "title", "hypothesis"])
    def test_blank_text_is_refused(self, field: str) -> None:
        with pytest.raises(SwingLabError, match=field if field != "variant_id" else "variant_id"):
            self._variant(**{field: "  "})

    def test_a_bad_treatment_type_is_refused(self) -> None:
        with pytest.raises(TypeError, match="ContextRoleTreatment"):
            self._variant(context_role="vote_only")

    def test_a_bool_max_age_is_refused(self) -> None:
        with pytest.raises(TypeError, match="int or None"):
            self._variant(max_confirmation_age=True)

    def test_a_negative_max_age_is_refused(self) -> None:
        with pytest.raises(SwingLabError, match="cannot be negative"):
            self._variant(max_confirmation_age=-1)

    def test_a_missing_role_is_refused(self) -> None:
        from fmis.pipeline.multi_timeframe import TimeframeRole

        partial = {TimeframeRole.CONTEXT: "1w", TimeframeRole.SETUP: "1d"}
        with pytest.raises(SwingLabError, match="missing"):
            self._variant(timeframes=partial)

    def test_the_timeframes_mapping_is_frozen_after_construction(self) -> None:
        variant = self._variant()
        with pytest.raises(TypeError):
            variant.timeframes[list(variant.timeframes)[0]] = "5m"


class TestMeasureFormatting:
    def test_a_present_measure_renders_its_value_and_sample(self) -> None:
        metrics = compute_lab_metrics(
            [trade("v", i) for i in range(25)], label="x"
        )
        rendered = render_comparison_table((metrics,))
        assert "n=25" in rendered

    def test_a_measure_reason_is_never_lost(self) -> None:
        measure = LabMeasure(value=None, n=3, reason="too thin")
        assert measure.reason == "too thin"
        assert not measure.is_present


class TestTheLabPageDistinguishesVerdicts:
    """Release-gate requirement: `/lab` must show what a study concluded.

    A page that reports expectancy without reporting the verdict leaves the
    reader to classify a variant themselves, which is exactly the judgement the
    laboratory exists to make deterministically.
    """

    @staticmethod
    def _page(**overrides):
        from datetime import datetime, timezone

        from fmis.operator_dashboard.compose import build_snapshot
        from fmis.operator_dashboard.render import render_page
        from fmis.operator_dashboard.sections import lab_view

        from tests.test_swing_lab_artifact import build_study
        from fmis.swing_lab.artifact import LabArtifact, encode_study

        payload = encode_study(build_study())
        payload.update(overrides)
        view = lab_view(LabArtifact(payload), digest_verified=True)
        now = datetime(2026, 8, 25, tzinfo=timezone.utc)
        return view, render_page(
            build_snapshot(refreshed_at=now, reference_time=now, lab=view), "/lab"
        )

    def test_every_variant_row_carries_a_verdict(self) -> None:
        view, html = self._page()
        for row in view.variants:
            assert row.verdict, row.variant_id
            assert row.verdict_statement, row.variant_id
            assert row.verdict.replace("_", " ") in html

    def test_the_page_has_a_verdict_column_and_a_verdict_panel(self) -> None:
        _, html = self._page()
        assert "<th>Verdict</th>" in html
        assert "Verdicts" in html

    def test_the_page_states_that_no_verdict_approves_trading(self) -> None:
        _, html = self._page()
        flattened = " ".join(html.split())
        assert "approves live trading" in flattened
        assert "worth testing forward" in flattened

    def test_the_page_never_uses_approval_vocabulary(self) -> None:
        _, html = self._page()
        lowered = html.lower()
        for phrase in (
            "ready for live", "approved for trading", "go live",
            "deploy this strategy", "use this strategy", "ready to trade",
        ):
            assert phrase not in lowered, phrase

    def test_an_inconclusive_variant_is_not_shown_as_rejected(self) -> None:
        """A variant with too few trades must read INCONCLUSIVE, not REJECTED."""
        from fmis.swing_lab.artifact import encode_study
        from tests.test_swing_lab_artifact import build_study

        payload = encode_study(build_study())
        # Strip every trade: nothing measurable remains.
        for variant in payload["variants"]:
            variant["trades"] = []
        view, html = self._page(variants=payload["variants"])
        assert {row.verdict for row in view.variants} == {"inconclusive"}
        assert "rejected" not in html.lower()

    def test_the_verdict_matches_what_classify_derives(self) -> None:
        """The page may not disagree with the deterministic rule."""
        from fmis.swing_lab.artifact import LabArtifact, encode_study
        from fmis.swing_lab.metrics import classify
        from tests.test_swing_lab_artifact import build_study

        artifact = LabArtifact(encode_study(build_study()))
        view, _ = self._page()
        for row in view.variants:
            assert row.verdict == classify(artifact.metrics(row.variant_id)).value
