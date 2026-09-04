"""The `fmits research dependence` command: what it refuses and what it prints.

The command has **no live path** by design, so the first class asserts every way
of asking for one is refused. The rest assert the report's structure, because the
sections are what keep measurement and inference visibly separate, and that a
reader cannot find a trading recommendation anywhere in the output.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from fmis.paired_dependence.artifact import encode_dependence_study, write_dependence_study
from fmis.paired_dependence.render import render_dependence_study
from fmis.paired_dependence.study import study_from_capture
from fmis.pipeline.cli import main
from test_swing_lab_admission_artifact import (  # noqa: F401 - fixtures
    capture,
    samples,
)

RUN_AT = datetime(2026, 9, 3, tzinfo=timezone.utc)
UNIVERSE = {"development": "primary", "validation": "primary", "holdout": "holdout"}


@pytest.fixture(scope="module")
def cd_study(capture, samples):
    return study_from_capture(
        capture, run_at=RUN_AT, universe_for_sample=UNIVERSE, samples=samples
    )


@pytest.fixture(scope="module")
def report(cd_study):
    return render_dependence_study(cd_study)


class TestTheCommandRefusesALivePath:
    def test_neither_source_is_refused(self, capsys):
        assert main(["research", "dependence"]) == 1
        assert "exactly one of --from-capture and --from-study" in capsys.readouterr().err

    def test_both_sources_are_refused(self, capsys):
        assert main(["research", "dependence", "--from-capture", "a", "--from-study", "b"]) == 1
        assert "exactly one of" in capsys.readouterr().err

    def test_a_positional_symbol_is_refused(self, capsys):
        assert main(["research", "dependence", "BTCUSDT"]) == 1
        assert "sealed pre-registration" in capsys.readouterr().err

    @pytest.mark.parametrize("flag", ["--start", "--end"])
    def test_a_window_override_is_refused(self, capsys, flag):
        assert main(
            ["research", "dependence", "--from-capture", "x", flag, "2024-01-01T00:00:00+00:00"]
        ) == 1
        assert "sealed" in capsys.readouterr().err

    def test_a_development_override_is_refused(self, capsys):
        assert main(["research", "dependence", "--development", "BTCUSDT"]) == 1
        assert "not accepted" in capsys.readouterr().err

    def test_a_missing_capture_is_refused_by_name(self, capsys):
        assert main(["research", "dependence", "--from-capture", "/no/such/file"]) == 1
        assert "cannot read" in capsys.readouterr().err

    def test_a_missing_study_is_refused_by_name(self, capsys):
        assert main(["research", "dependence", "--from-study", "/no/such/file"]) == 1
        assert "cannot read" in capsys.readouterr().err

    def test_an_existing_save_target_is_refused(self, capsys, tmp_path):
        target = tmp_path / "taken.json.gz"
        target.write_bytes(b"x")
        assert main(
            [
                "research", "dependence", "--from-capture", "/no/such/file",
                "--save-dependence", str(target),
            ]
        ) == 1
        assert "never overwritten" in capsys.readouterr().err


class TestTheReportStructure:
    @pytest.mark.parametrize(
        "section",
        ["OBSERVATION", "MEASUREMENT", "UNCERTAINTY", "DESIGN IMPLICATION",
         "VERDICT", "LIMITATIONS"],
    )
    def test_every_named_section_is_present(self, report, section):
        assert section in report

    def test_the_five_counts_are_printed_together(self, report):
        for line in ("rows (one admission x one family)", "admissions",
                     "economic assets", "provider symbols",
                     "blocks with 2+ assets"):
            assert line in report

    def test_the_two_correlations_are_named_separately(self, report):
        assert "r_b — BETWEEN economic assets" in report
        assert "rho_w — WITHIN one economic asset" in report

    def test_the_seal_and_the_source_capture_are_printed(self, report, cd_study):
        assert cd_study.manifest["preregistration_digest"] in report
        assert cd_study.manifest["capture_content_digest"] in report

    def test_the_whole_sensitivity_grid_is_printed(self, report, cd_study):
        assert report.count("cell_mean") >= len(cd_study.headline.sensitivity) // 2

    def test_the_cc_residual_comparison_is_labelled_as_not_an_estimate(self, report):
        assert "Milestone CC residual estimator" in report
        assert "none of which is an estimate" in report

    def test_the_predecessor_verdicts_are_stated_as_standing(self, report):
        assert "NO_EDGE" in report and "UNDERPOWERED" in report and "INFEASIBLE" in report

    def test_it_states_that_it_approves_nothing(self, report):
        assert "approves trading                 False" in report
        assert "earns a forward test             False" in report

    def test_it_names_no_position_of_any_kind(self, report):
        lowered = report.lower()
        for phrase in ("buy ", "sell ", "go long", "go short", "entry price",
                       "take profit", "stop loss"):
            assert phrase not in lowered, phrase

    def test_the_limitations_travel_with_the_result(self, report):
        from fmis.paired_dependence.preregistration import CD_LIMITATIONS

        for item in CD_LIMITATIONS:
            assert item.split("—")[0].strip() in report


class TestTheCommandRuns:
    def test_from_study_reproduces_and_prints(self, cd_study, tmp_path, capsys):
        payload = encode_dependence_study(cd_study, writer="tests")
        target = write_dependence_study(payload, tmp_path / "study.json.gz")
        assert main(["research", "dependence", "--from-study", str(target)]) == 0
        out = capsys.readouterr().out
        assert "MILESTONE CD" in out
        assert "DESIGN IMPLICATION" in out

    def test_an_edited_study_is_refused_before_it_is_read(self, cd_study, tmp_path, capsys):
        payload = encode_dependence_study(cd_study, writer="tests")
        edited = json.loads(json.dumps(payload))
        edited["panels"][0]["between_asset"]["point"] = 0.99
        target = write_dependence_study(edited, tmp_path / "edited.json.gz")
        assert main(["research", "dependence", "--from-study", str(target)]) == 1
        assert "does not match its own content digest" in capsys.readouterr().err

    def test_saving_writes_the_observations_and_reports_the_digest(
        self, cd_study, tmp_path, capsys
    ):
        payload = encode_dependence_study(cd_study, writer="tests")
        source = write_dependence_study(payload, tmp_path / "source.json.gz")
        target = tmp_path / "saved.json.gz"
        assert main(
            [
                "research", "dependence", "--from-study", str(source),
                "--save-dependence", str(target),
            ]
        ) == 0
        err = capsys.readouterr().err
        assert "STUDY WRITTEN to" in err
        assert "content digest" in err
        assert "observations" in err
        assert target.exists()
