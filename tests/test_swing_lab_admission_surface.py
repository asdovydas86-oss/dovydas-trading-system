"""Milestone CA's surfaces: the renderer and the CLI.

The renderer must **own no rule**. Presentation is the most-replaced layer in any
system, and a threshold living in it would be a threshold that quietly changed
when the report was reformatted. These tests assert the absence rather than
trusting it.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

import pytest

from fmis.pipeline.cli import _configure_research, _run_research
from fmis.swing_lab.admission_preregistration import (
    CA_NULL_FAMILIES,
    CA_PRE_REGISTRATION,
    CA_PREREGISTRATION_DIGEST,
    CaVerdict,
)
from fmis.swing_lab.admission_render import render_admission_study
from fmis.swing_lab.admission_study import AdmissionStudy, CaAssessment, Criterion

_SOURCE = None


def _renderer_source() -> str:
    global _SOURCE
    if _SOURCE is None:
        from pathlib import Path

        _SOURCE = (
            Path(__file__).resolve().parents[1]
            / "src" / "fmis" / "swing_lab" / "admission_render.py"
        ).read_text(encoding="utf-8")
    return _SOURCE


def _study(verdict: CaVerdict = CaVerdict.NO_EDGE) -> AdmissionStudy:
    return AdmissionStudy(
        manifest={
            "preregistration_digest": CA_PREREGISTRATION_DIGEST,
            "capture_content_digest": "abc123",
            "capture_captured_at": "2026-08-27T03:11:50+00:00",
            "primary_horizon": 24,
            "causal_proven": False,
            "run_at": "2026-08-27T00:00:00+00:00",
            "horizons": [1, 3, 6, 12, 24, 60],
            "stage_census": {"development": {"admitted": 155, "unconfirmed": 8793}},
        },
        results={},
        assessments={
            family.family_id: CaAssessment(
                family_id=family.family_id,
                verdict=verdict,
                criteria=(
                    Criterion("pre_registered", True, "sealed"),
                    Criterion("causal", False, "NOT PROVEN"),
                    Criterion("sample", None, "below the floor"),
                ),
            )
            for family in CA_NULL_FAMILIES
        },
        gate_ladder=(),
        seed_effects={},
        control_identity_digest={},
    )


class TestTheRendererOwnsNoRule:
    """Checked on the parsed module rather than on its text, so a docstring
    mentioning `Decimal` and a renderer *constructing* one are told apart."""

    def _tree(self):
        import ast

        return ast.parse(_renderer_source())

    def test_it_never_constructs_a_decimal_or_imports_one(self) -> None:
        import ast

        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Import):
                assert all(a.name != "decimal" for a in node.names)
            if isinstance(node, ast.ImportFrom):
                assert node.module != "decimal"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "Decimal"

    def test_it_imports_no_statistic_only_the_seal(self) -> None:
        """It may read what the study computed; it may not reach the machinery
        that computes one."""
        import ast

        for node in ast.walk(self._tree()):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.endswith("admission_study")
                assert not node.module.endswith("admission_matching")
                assert not node.module.endswith("metrics")
                assert not node.module.endswith("robustness")

    def test_it_aggregates_nothing(self) -> None:
        """A renderer that could average could disagree with the study.

        `sorted` is deliberately NOT forbidden: ordering rows for a stable,
        reproducible report is presentation, and a renderer that could not sort
        would emit a different document per run. Reducing values to a new number
        is what it may not do.
        """
        import ast

        forbidden = {"sum", "min", "max", "mean", "_mean", "round"}
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden, node.func.id

    def test_its_only_threshold_is_read_from_the_seal(self) -> None:
        source = _renderer_source()
        assert "MIN_ADMISSION_EDGE_ATR" in source
        for literal in ("0.40", "0.10", "95.0", "SAMPLE_FLOOR"):
            assert literal not in source, f"the renderer names {literal}"


class TestTheReport:
    def test_the_verdict_comes_first(self) -> None:
        rendered = render_admission_study(_study())
        head = rendered.split("SEAL AND PROVENANCE")[0]
        assert "NO EDGE" in head

    def test_it_states_what_a_positive_effect_does_not_mean(self) -> None:
        rendered = render_admission_study(_study())
        assert "WHAT A POSITIVE EFFECT HERE DOES NOT MEAN" in rendered
        assert "NO stop, NO target, NO exit and NO cost" in rendered

    def test_it_prints_the_seal_and_whether_it_verifies(self) -> None:
        rendered = render_admission_study(_study())
        assert CA_PREREGISTRATION_DIGEST in rendered
        assert "seal verifies         True" in rendered

    def test_it_prints_the_capture_it_was_measured_over(self) -> None:
        assert "abc123" in render_admission_study(_study())

    def test_it_marks_an_unmeasurable_criterion_as_such(self) -> None:
        rendered = render_admission_study(_study())
        assert "UNMEASURABLE" in rendered
        assert "[        FAIL] causal" in rendered

    def test_it_prints_the_declared_degeneracy(self) -> None:
        rendered = render_admission_study(_study())
        assert "DECLARED DEGENERACY" in rendered
        assert "ca_null_opposite_direction" in rendered

    def test_it_prints_every_limitation(self) -> None:
        rendered = render_admission_study(_study())
        for limitation in CA_PRE_REGISTRATION.limitations:
            assert limitation.split(" — ")[0] in rendered

    def test_it_ends_by_refusing_to_approve_trading(self) -> None:
        rendered = render_admission_study(_study())
        assert "APPROVES LIVE, SHADOW, PAPER OR FORWARD" in rendered

    def test_a_candidate_headline_still_refuses_to_promote(self) -> None:
        rendered = render_admission_study(
            _study(CaVerdict.ADMISSION_EDGE_CANDIDATE)
        )
        assert "does NOT approve live, shadow, paper or forward trading" in rendered

    def test_every_verdict_has_a_headline(self) -> None:
        for verdict in CaVerdict:
            assert render_admission_study(_study(verdict))

    def test_it_is_deterministic(self) -> None:
        assert render_admission_study(_study()) == render_admission_study(_study())


def _parse(*argv):
    parser = argparse.ArgumentParser()
    _configure_research(parser)
    return parser.parse_args(list(argv))


class TestTheCommandRefusesWhatWasSealed:
    def test_it_requires_a_capture_because_there_is_no_live_path(self, capsys) -> None:
        assert _run_research(_parse("admission")) == 1
        assert "--from-capture is REQUIRED" in capsys.readouterr().err

    @pytest.mark.parametrize("name", ["BTCUSDT"])
    def test_a_universe_is_refused_by_name(self, capsys, name: str) -> None:
        assert _run_research(_parse("admission", name)) == 1
        assert "symbols is not accepted" in capsys.readouterr().err

    def test_a_development_set_is_refused(self, capsys) -> None:
        assert _run_research(_parse("admission", "--development", "BTCUSDT")) == 1
        assert "development is not accepted" in capsys.readouterr().err

    def test_a_holdout_set_is_refused(self, capsys) -> None:
        assert _run_research(_parse("admission", "--holdout", "BTCUSDT")) == 1
        assert "holdout is not accepted" in capsys.readouterr().err

    def test_a_window_boundary_is_refused(self, capsys) -> None:
        assert _run_research(_parse("admission", "--start", "2024-01-01")) == 1
        assert "--start is not accepted" in capsys.readouterr().err

    def test_an_end_boundary_is_refused(self, capsys) -> None:
        assert _run_research(_parse("admission", "--end", "2024-01-01")) == 1
        assert "--end is not accepted" in capsys.readouterr().err

    def test_save_capture_belongs_to_persistence_not_here(self, capsys) -> None:
        assert (
            _run_research(
                _parse("admission", "--from-capture", "x", "--save-capture", "y")
            )
            == 1
        )
        assert "belongs to 'persistence'" in capsys.readouterr().err

    def test_an_unreadable_capture_is_reported_rather_than_crashed(
        self, capsys, tmp_path
    ) -> None:
        assert (
            _run_research(
                _parse("admission", "--from-capture", str(tmp_path / "absent.json"))
            )
            == 1
        )
        assert "cannot read capture" in capsys.readouterr().err

    def test_it_refuses_to_overwrite_an_existing_study(self, capsys, tmp_path) -> None:
        existing = tmp_path / "ca.json.gz"
        existing.write_text("x", encoding="utf-8")
        assert (
            _run_research(
                _parse(
                    "admission", "--from-capture", "x", "--save-study", str(existing)
                )
            )
            == 1
        )
        assert "already exists" in capsys.readouterr().err

    def test_causality_is_off_by_default(self) -> None:
        """A run cannot verify the repository's own suite from inside itself."""
        assert _parse("admission", "--from-capture", "x").causal_proven is False
