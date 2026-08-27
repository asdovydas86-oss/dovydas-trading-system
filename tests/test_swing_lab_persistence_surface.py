"""`fmits research persistence` and the BZ renderer. **Presentation only.**

Two things are asserted here and both are about what a surface must refuse.
First, the command takes **no** universe, window or threshold: every one of them
is sealed, and a flag that looked like it could move a sealed boundary would be
worse than no flag. Second, the renderer computes nothing — it is handed a study
and formats it, so a number it prints must already exist on the object.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from fmis.swing_lab.metrics import compute_lab_metrics
from fmis.swing_lab.persistence_preregistration import (
    BZ_PRE_REGISTRATION,
    BZ_PREREGISTRATION_DIGEST,
)
from fmis.swing_lab.persistence_render import render_persistence_study
from fmis.swing_lab.persistence_study import (
    BzVerdict,
    FamilyComparison,
    FamilyMeasurement,
    GivebackDecomposition,
    PathSummary,
    PersistenceStudy,
    assess_bz,
)

_UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=_UTC)


def _measurement(policy_id: str, hypothesis_id: str) -> FamilyMeasurement:
    metrics = compute_lab_metrics((), label=policy_id)
    return FamilyMeasurement(
        policy_id=policy_id, hypothesis_id=hypothesis_id,
        geometry_policy_id="geom_production", sample="development",
        cost_policy_id="swing-lab-conservative-10bps", trades=(),
        metrics=metrics, fired=0, ambiguous=0, exit_reasons=(),
        comparable_metrics=metrics,
    )


def _study() -> PersistenceStudy:
    comparison = FamilyComparison(
        geometry_policy_id="geom_production",
        sample="development",
        cost_policy_id="swing-lab-conservative-10bps",
        control_policy_id="bz_exit_control",
        measurements=(
            _measurement("bz_exit_control", "BZ-H0"),
            _measurement("bz_exit_thesis_failure", "BZ-H1"),
        ),
        shared_setups=0,
    )
    summary = PathSummary(
        label="geom_production:development", paths=2,
        ever_reached={"0.5": 1}, median_bars_to={"0.5": 2.0},
        ever_adverse=1, median_bars_to_adverse=1.0, median_bars_to_peak=2.0,
        peak_r_p25=Decimal("0.1"), peak_r_median=Decimal("0.5"),
        peak_r_p75=Decimal("1.2"), giveback_median=Decimal("0.4"),
        gave_back_a_full_r=1,
        thesis_at_checkpoint={1: {"intact": 2}, 2: {"intact": 1, "weakened": 1}},
    )
    giveback = GivebackDecomposition(
        label="geom_production:development", paths=2, gave_back_a_full_r=1,
        realised_after_reaching={"0.5": (1, Decimal("-0.5"))},
        median_bars_peak_to_exit=1.0,
        by_direction={"long": (2, None)},
        largest_symbol_share=Decimal("0.6"),
        by_context_regime={"trending": (2, None)},
    )
    assessment = assess_bz(
        "bz_exit_thesis_failure",
        geometry_policy_id="geom_production",
        comparisons={"development": comparison},
        causal_proven=False, robust=None, ambiguity_decisive=None,
    )
    return PersistenceStudy(
        preregistration_id=BZ_PRE_REGISTRATION.preregistration_id,
        preregistration_digest=BZ_PREREGISTRATION_DIGEST,
        digest_matches=True,
        evaluation_window_bars=60,
        deciding_cost_policy_id="swing-lab-conservative-10bps",
        comparisons={("geom_production", "development"): comparison},
        paths={("geom_production", "development"): summary},
        giveback={("geom_production", "development"): giveback},
        assessments=(assessment,),
        walk_forward={},
        decompositions={},
        capture_metadata={"measured_instants": 10},
        holdout_capture_metadata=None,
        timeline_instants=10,
        limitations=BZ_PRE_REGISTRATION.limitations,
    )


class TestTheCommandRefusesASealedBoundary:
    @pytest.mark.parametrize(
        "extra",
        [
            pytest.param(["BTCUSDT"], id="a-universe"),
            pytest.param(["--development", "BTCUSDT"], id="a-development-split"),
            pytest.param(["--holdout", "ETHUSDT"], id="a-holdout-split"),
        ],
    )
    def test_a_sealed_input_is_refused_by_name(
        self, extra: list[str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        from fmis.pipeline.cli import main

        assert main(["research", "persistence", *extra]) != 0
        captured = capsys.readouterr()
        assert "is not accepted" in captured.err
        assert "sealed in the pre-registration" in captured.err

    def test_the_area_is_a_declared_choice(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from fmis.pipeline.cli import main

        with pytest.raises(SystemExit):
            main(["research", "invented"])
        assert "persistence" in capsys.readouterr().err


class TestTheRendererComputesNothing:
    def test_it_prints_the_verdict_first(self) -> None:
        text = render_persistence_study(_study())
        head = text.split("\n", 6)
        assert any("MILESTONE BZ" in line for line in head)
        assert "VERDICT:" in text

    def test_it_prints_the_seal_and_the_deciding_scenario(self) -> None:
        text = render_persistence_study(_study())
        assert BZ_PREREGISTRATION_DIGEST in text
        assert "swing-lab-conservative-10bps" in text

    def test_it_separates_descriptive_from_causal(self) -> None:
        """The methodological discipline, made visible to a reader."""
        text = render_persistence_study(_study())
        assert "DESCRIPTIVE" in text
        assert "CAUSAL" in text
        assert "may NEVER be read as decision rules" in text

    def test_it_tells_the_reader_which_column_to_read(self) -> None:
        text = render_persistence_study(_study())
        assert "like4like" in text
        assert "flatters management" in text

    def test_it_prints_every_limitation(self) -> None:
        text = render_persistence_study(_study())
        for limitation in BZ_PRE_REGISTRATION.limitations:
            assert limitation.split(" — ")[0] in text

    def test_it_never_claims_approval(self) -> None:
        text = render_persistence_study(_study())
        assert "RESEARCH ONLY" in text
        assert "No strategy adopted" in text
        assert "WORTH TESTING FORWARD" in text

    def test_a_no_candidate_run_says_so_plainly(self) -> None:
        text = render_persistence_study(_study())
        assert "NO_CANDIDATE" in text

    def test_a_non_study_is_a_type_error(self) -> None:
        with pytest.raises(TypeError, match="must be a PersistenceStudy"):
            render_persistence_study(object())  # type: ignore[arg-type]

    def test_the_renderer_holds_no_threshold_of_its_own(self) -> None:
        """Presentation must be replaceable, so it may own no rule."""
        import pathlib
        import re

        source = pathlib.Path(
            "src/fmis/swing_lab/persistence_render.py"
        ).read_text(encoding="utf-8")
        # No comparison against a numeric literal other than formatting widths.
        assert not re.search(r"[<>]=?\s*0\.\d", source)
        assert "SAMPLE_FLOOR" not in source
        assert "Decimal(" not in source


class TestTheVerdictBranches:
    """All three verdict headlines, so none is written but never rendered."""

    @staticmethod
    def _with(verdict: BzVerdict):
        from dataclasses import replace

        study = _study()
        forced = replace(study.assessments[0], verdict=verdict)
        return replace(study, assessments=(forced,))

    def test_a_candidate_run_says_worth_testing_forward_and_not_approval(self) -> None:
        text = render_persistence_study(self._with(BzVerdict.CANDIDATE))
        assert "VERDICT: CANDIDATE" in text
        assert "WORTH TESTING FORWARD" in text
        assert "NOT approval to trade" in text

    def test_a_mechanism_evidence_run_refuses_to_promote(self) -> None:
        text = render_persistence_study(self._with(BzVerdict.MECHANISM_EVIDENCE))
        assert "NO_CANDIDATE" in text
        assert "MECHANISM_EVIDENCE" in text
        assert "approves nothing and earns no forward test" in text

    def test_a_rejected_run_states_no_candidate_plainly(self) -> None:
        text = render_persistence_study(self._with(BzVerdict.REJECTED))
        assert "no sealed exit family earned the right" in text


class TestTheCaptureFlags:
    """`--from-capture` re-measures offline; `--save-capture` is not a fresh replay."""

    def test_the_two_flags_are_mutually_exclusive(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from fmis.pipeline.cli import main

        assert main([
            "research", "persistence",
            "--from-capture", "a.json", "--save-capture", "b.json",
        ]) != 0
        assert "mutually exclusive" in capsys.readouterr().err

    def test_a_missing_capture_is_refused_by_name(
        self, tmp_path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from fmis.pipeline.cli import main

        assert main([
            "research", "persistence", "--from-capture", str(tmp_path / "no.json"),
        ]) != 0
        assert "cannot read capture" in capsys.readouterr().err

    def test_a_corrupted_capture_is_refused_and_says_why(
        self, tmp_path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """**Never resolved, never repaired — reported.**"""
        import gzip
        import json

        from fmis.pipeline.cli import main
        from fmis.swing_lab.persistence_artifact import (
            encode_capture,
            write_persistence_capture,
        )
        from fmis.swing_lab.persistence_preregistration import (
            BZ_PRE_REGISTRATION,
            BZ_PREREGISTRATION_DIGEST,
        )
        from fmis.swing_lab.geometry_replay import GeometryCapture

        empty = GeometryCapture(
            admission_variant_id="v", admission_policy_id="p",
            candidates=(), bars_by_symbol={},
        )
        payload = encode_capture(
            {"primary": (empty, {})},
            manifest={
                "preregistration_id": BZ_PRE_REGISTRATION.preregistration_id,
                "preregistration_digest": BZ_PREREGISTRATION_DIGEST,
                "captured_at": "2026-08-27T00:00:00+00:00",
                "evaluation_window_bars": 60,
                "deciding_cost_policy_id": "swing-lab-conservative-10bps",
            },
        )
        path = write_persistence_capture(payload, tmp_path / "c.json")
        raw = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
        raw["manifest"]["content_digest"] = "0" * 64
        with open(path, "wb") as handle:
            with gzip.GzipFile(filename="", fileobj=handle, mode="wb", mtime=0) as z:
                z.write(json.dumps(raw, sort_keys=True, separators=(",", ":")).encode())

        assert main(["research", "persistence", "--from-capture", str(path)]) != 0
        err = capsys.readouterr().err
        assert "fails its own content digest" in err
        assert "no number in it can be trusted" in err
