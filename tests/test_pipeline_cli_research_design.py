"""`fmits research design`, end to end through `main`.

Exercised through `cli_module.main` rather than by calling the renderer, because
the parsing, the refusals and the exit code are what this file exists to hold —
the figures themselves are held by `test_swing_lab_admission_power.py` and the
statistics by `test_research_design_resolution.py`.

The command's defining property is that it **reads nothing**: no network, no
capture, no store, no market data of any kind. Two tests hold that from the
outside, by making both unavailable and requiring the command to still succeed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fmis.pipeline import cli as cli_module


def run(capsys, *argv: str) -> tuple[int, str]:
    code = cli_module.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out + captured.err


class TestItRuns:
    def test_it_exits_zero_and_prints_a_report(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out = run(capsys, "research", "design")
        assert code == 0
        assert "RESEARCH DESIGN ASSESSMENT" in out

    def test_it_answers_every_question_the_brief_asks_for(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out = run(capsys, "research", "design")
        for heading in (
            "QUESTION",
            "MINIMUM MEANINGFUL EFFECT",
            "AVAILABLE INFORMATION",
            "DEPENDENCE AND CLUSTERING",
            "CURRENT UNCERTAINTY",
            "WHAT THIS DESIGN CAN AND CANNOT RESOLVE",
            "VERDICT",
            "WHAT ADDITIONAL INFORMATION WOULD HELP",
            "ASSUMPTIONS",
            "CAVEATS",
        ):
            assert heading in out, heading

    def test_it_labels_itself_a_post_hoc_diagnostic_not_prospective_power(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out = run(capsys, "research", "design")
        assert "POST-HOC RESOLUTION DIAGNOSTIC" in out
        assert "must never be quoted as one" in out
        assert "PROSPECTIVE DESIGN ASSESSMENT" not in out

    def test_it_prints_the_verdict_and_the_binding_dimension(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out = run(capsys, "research", "design")
        assert "UNDERPOWERED" in out
        assert "cluster_count" in out

    def test_it_reproduces_cas_published_requirement(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out = run(capsys, "research", "design")
        assert "REPRODUCING MILESTONE CA'S PUBLISHED REQUIREMENT" in out
        assert "4,800" in out
        assert "4,827" in out
        assert "REPRODUCED" in out

    def test_it_prints_a_design_curve_marked_as_modelled(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out = run(capsys, "research", "design")
        assert "DESIGN CURVE — MODELLED, AND EXTRAPOLATED BEYOND 155" in out
        assert "more_clusters_same_density" in out
        assert "more_observations_same_clusters" in out

    def test_it_prints_the_post_hoc_reading_of_every_sample(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out = run(capsys, "research", "design")
        assert "POST-HOC RESOLUTION, EVERY SAMPLE" in out
        for sample in ("development", "validation", "holdout"):
            assert sample in out

    def test_it_states_what_it_cannot_do(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out = run(capsys, "research", "design")
        assert "WHAT THIS ASSESSMENT CANNOT DO" in out
        assert "CB-1" in out

    def test_it_makes_no_trading_recommendation(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out = run(capsys, "research", "design")
        assert "does not say whether the hypothesis is true" in out
        for token in ("buy ", "sell ", "should trade", "approved for"):
            assert token not in out.lower()

    def test_every_line_fits_the_report_width(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, out = run(capsys, "research", "design")
        over = [line for line in out.splitlines() if len(line) > 78]
        assert over == []

    def test_two_runs_produce_the_identical_report(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, first = run(capsys, "research", "design")
        _, second = run(capsys, "research", "design")
        assert first == second


class TestItReadsNothing:
    def test_it_succeeds_with_the_network_made_fatal(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The strongest form of "offline": make a fetch raise, then run it."""
        import fmis.providers.binance as binance

        def explode(*args, **kwargs):  # pragma: no cover - must never be called
            raise AssertionError("fmits research design reached the network")

        monkeypatch.setattr(binance, "fetch_raw_klines", explode, raising=False)
        code, out = run(capsys, "research", "design")
        assert code == 0
        assert "RESEARCH DESIGN ASSESSMENT" in out

    def test_it_succeeds_with_no_store_and_no_capture_anywhere(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        code, _ = run(capsys, "research", "design")
        assert code == 0


class TestItRefusesWhatItCannotHonour:
    @pytest.mark.parametrize("flag", ("--start", "--end", "--from-capture"))
    def test_a_window_or_a_capture_is_refused(
        self, capsys: pytest.CaptureFixture[str], flag: str
    ) -> None:
        code, out = run(capsys, "research", "design", flag, "2024-01-01T00:00:00+00:00")
        assert code != 0
        assert "is not accepted" in out

    def test_a_universe_is_refused(self, capsys: pytest.CaptureFixture[str]) -> None:
        code, out = run(capsys, "research", "design", "BTCUSDT")
        assert code != 0
        assert "reads no market data at all" in out

    def test_a_holdout_universe_is_refused(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code, out = run(capsys, "research", "design", "--holdout", "ETHUSDT")
        assert code != 0
        assert "is not accepted" in out


class TestSavingTheAssessment:
    def test_it_writes_an_artifact_that_verifies(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        from fmis.research_design import verify_design_assessment_digest

        target = tmp_path / "design.json"
        code, _ = run(capsys, "research", "design", "--save-study", str(target))
        assert code == 0
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert verify_design_assessment_digest(payload)
        assert payload["kind"] == "research-design-assessment"
        assert payload["verdict"] == "underpowered"
        assert payload["mode"] == "post_hoc"

    def test_the_same_assessment_written_twice_is_byte_identical(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        first, second = tmp_path / "a.json", tmp_path / "b.json"
        run(capsys, "research", "design", "--save-study", str(first))
        run(capsys, "research", "design", "--save-study", str(second))
        assert first.read_bytes() == second.read_bytes()

    def test_an_existing_file_is_never_overwritten(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        target = tmp_path / "design.json"
        target.write_text("keep me", encoding="utf-8")
        code, out = run(capsys, "research", "design", "--save-study", str(target))
        assert code != 0
        assert "never overwritten" in out
        assert target.read_text(encoding="utf-8") == "keep me"

    def test_the_artifact_carries_no_market_data(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """It records a DESIGN, not the observations a design was measured over.

        Asserted structurally rather than by keyword. The word "close" appears in
        the effect's own rationale — *"the median ATR/close over its admitted
        instants"* — which is the sentence that says where the +0.10 bar came from
        and exactly the sort of provenance the artifact should carry. What must be
        absent is a **series**: a per-observation payload of prices or values.
        """
        target = tmp_path / "design.json"
        run(capsys, "research", "design", "--save-study", str(target))
        payload = json.loads(target.read_text(encoding="utf-8"))

        def keys_of(node) -> set[str]:
            if isinstance(node, dict):
                return set(node) | {
                    name for item in node.values() for name in keys_of(item)
                }
            if isinstance(node, list):
                return {name for item in node for name in keys_of(item)}
            return set()

        # Checked over KEYS, not over the serialised text: the prose legitimately
        # says "60 bars" when it explains the separation constraint, and a probe
        # that could not tell a field from a sentence would force the document to
        # stop explaining itself.
        present = keys_of(payload)
        for key in ("bars", "candles", "klines", "prices", "observations_data", "values"):
            assert key not in present

        def longest_numeric_list(node) -> int:
            if isinstance(node, list):
                own = (
                    len(node)
                    if node and all(isinstance(item, (int, float)) for item in node)
                    else 0
                )
                return max([own, *(longest_numeric_list(item) for item in node)] or [0])
            if isinstance(node, dict):
                return max([0, *(longest_numeric_list(item) for item in node.values())])
            return 0

        assert longest_numeric_list(payload) < 20, (
            "a design assessment carrying a long numeric series would be carrying "
            "the data it was computed from, which is the one thing it must not"
        )


class TestTheAreaIsDiscoverable:
    def test_design_is_offered_beside_the_other_research_areas(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exit_code:
            run(capsys, "research", "--help")
        assert exit_code.value.code == 0
        out = capsys.readouterr().out
        assert "design" in out
        for other in ("swing", "geometry", "validation", "persistence", "admission"):
            assert other in out

    def test_an_unknown_area_is_still_refused(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            run(capsys, "research", "nonsense")
