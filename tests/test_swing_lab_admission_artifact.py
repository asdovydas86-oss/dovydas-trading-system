"""Milestone CA end to end: offline reproduction, the artifact, and failing closed.

The reproducibility claim is proven by making a fetch **fatal**, not by asserting
that none happened: `fetch_raw_klines` is monkeypatched to raise, and the study
is then run to completion over a synthetic Milestone BZ capture. A study that
reached the network would raise rather than pass.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from fmis.swing_lab.admission import AdmissionStage
from fmis.swing_lab.admission_artifact import (
    CA_ARTIFACT_KIND,
    CA_ARTIFACT_SCHEMA_VERSION,
    AdmissionStudyArtifact,
    admission_study_digest,
    encode_admission_study,
    read_admission_study,
    verify_admission_study_digest,
    write_admission_study,
)
from fmis.swing_lab.admission_preregistration import CA_PREREGISTRATION_DIGEST
from fmis.swing_lab.admission_study import build_sample_instants, study_from_capture
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.persistence_artifact import (
    BZ_CAPTURE_KIND,
    BZ_CAPTURE_SCHEMA_VERSION,
    PersistenceCaptureArtifact,
    capture_digest,
)
from fmis.swing_lab.preregistration import SampleSpec, SampleRole

T0 = datetime(2023, 6, 1, tzinfo=timezone.utc)
SYMBOLS = ("AAAUSDT", "BBBUSDT", "CCCUSDT")
BAR_COUNT = 900
LIMIT = 60


def _bars(symbol: str, seed: int) -> list[list[str]]:
    """A deterministic saw-tooth series. Never random: a fixture that moved
    between runs could not support a reproducibility test."""
    rows = []
    price = 100.0 + seed
    for index in range(BAR_COUNT):
        # A repeating pattern with genuine range, so ATR is positive and the
        # excursion race has something to resolve against.
        drift = ((index * (seed + 3)) % 17) - 8
        open_ = price
        close = price + drift * 0.1
        high = max(open_, close) + 0.5 + (index % 5) * 0.1
        low = min(open_, close) - 0.5 - (index % 3) * 0.1
        price = close
        rows.append(
            [
                (T0 + timedelta(hours=4 * index)).isoformat(),
                f"{open_:.6f}",
                f"{high:.6f}",
                f"{low:.6f}",
                f"{close:.6f}",
            ]
        )
    return rows


def _observation(symbol: str, index: int, state: str, direction: str | None, close: float):
    return {
        "as_of": (T0 + timedelta(hours=4 * index) + timedelta(hours=4)).isoformat(),
        "bar_index": index,
        "context_structural_trend": "sustained_higher",
        "setup_structural_trend": "sustained_higher",
        "execution_structural_trend": "sustained_higher",
        "context_regime_structure": "trending",
        "evidence_state": "proceed",
        "evidence_dominant_alignment": "upward",
        "decision_context_state": "sufficient",
        "setup_state": state,
        "setup_direction": direction,
        "execution_close": close,
        "upper_levels": [],
        "lower_levels": [],
    }


def _universe() -> dict:
    """One universe whose timeline yields admissions, unconfirmed instants and
    direction-less instants, so every rung of the ladder is populated."""
    bars = {symbol: _bars(symbol, seed) for seed, symbol in enumerate(SYMBOLS)}
    timeline: dict[str, list] = {}
    candidates: list[dict] = []
    for seed, symbol in enumerate(SYMBOLS):
        rows = []
        previous_state = "wait"
        for index in range(20, BAR_COUNT - 70):
            close = float(bars[symbol][index][4])
            # A repeating lifecycle: wait -> candidate -> confirmed -> wait.
            phase = (index + seed * 7) % 40
            if phase < 18:
                state, direction = "wait", None
            elif phase < 30:
                state, direction = "candidate", "long"
            elif phase < 34:
                state, direction = "confirmed", "long"
            else:
                state, direction = "wait", None
            rows.append(_observation(symbol, index, state, direction, close))
            # The first CONFIRMED after a run began is the admission, which the
            # OpportunityTracker decides; the fixture records the same instants
            # and the study is asserted to agree with this list.
            if state == "confirmed" and previous_state == "candidate":
                candidates.append(
                    {
                        "symbol": symbol,
                        "setup_id": f"{symbol}|long|from={index}",
                        "direction": "long",
                        "signal_at": bars[symbol][index][0],
                        "signal_index": index,
                        "reference_price": close,
                        "execution_stop_levels": [],
                        "setup_stop_levels": [],
                        "setup_target_levels": [],
                        "context_target_levels": [],
                        "execution_atr": 1.0,
                        "setup_atr": 2.0,
                        "context_interval": "1w",
                        "setup_interval": "1d",
                        "execution_interval": "4h",
                        "segment": "year_1_of_1",
                        "context_regime_structure": "trending",
                        "context_regime_volatility": "steady",
                        "context_structural_trend": "sustained_higher",
                        "setup_structural_trend": "sustained_higher",
                        "metadata": {},
                    }
                )
            previous_state = state
        timeline[symbol] = rows
    return {
        "admission_variant_id": "swing_current",
        "admission_policy_id": "swing-setup-v1",
        "execution_interval": "4h",
        "symbols": sorted(SYMBOLS),
        "metadata": {
            "candle_limit": LIMIT,
            "measurement_start": T0.isoformat(),
            "measurement_end": (T0 + timedelta(hours=4 * BAR_COUNT)).isoformat(),
            "measured_instants": 0,
        },
        "bars": bars,
        "candidates": sorted(candidates, key=lambda c: (c["symbol"], c["signal_at"])),
        "timeline": timeline,
    }


def _capture_payload() -> dict:
    universe = _universe()
    payload = {
        "schema_version": BZ_CAPTURE_SCHEMA_VERSION,
        "kind": BZ_CAPTURE_KIND,
        "manifest": {
            "preregistration_id": "bz-swing-thesis-persistence-v1",
            "preregistration_digest": "0" * 64,
            "captured_at": T0.isoformat(),
            "evaluation_window_bars": 60,
            "candle_limit": LIMIT,
            "deciding_cost_policy_id": "swing-lab-conservative-10bps",
            "provider": {"transport": "fixture", "note": "synthetic"},
        },
        "universes": {"primary": universe, "holdout": _universe()},
    }
    payload["manifest"]["content_digest"] = capture_digest(payload)
    return payload


@pytest.fixture(scope="module")
def capture() -> PersistenceCaptureArtifact:
    return PersistenceCaptureArtifact(_capture_payload())


@pytest.fixture(scope="module")
def samples() -> tuple[SampleSpec, ...]:
    mid = T0 + timedelta(hours=4 * 500)
    end = T0 + timedelta(hours=4 * BAR_COUNT)
    return (
        SampleSpec(
            name="development", role=SampleRole.DEVELOPMENT, symbols=SYMBOLS,
            signal_start=T0, signal_end=mid, contamination="fixture",
        ),
        SampleSpec(
            name="validation", role=SampleRole.VALIDATION, symbols=SYMBOLS,
            signal_start=mid, signal_end=end, contamination="fixture",
        ),
        SampleSpec(
            name="holdout", role=SampleRole.HOLDOUT, symbols=SYMBOLS,
            signal_start=T0, signal_end=end, contamination="fixture",
        ),
    )


@pytest.fixture(scope="module")
def study(capture, samples):
    return study_from_capture(
        capture,
        universe_for_sample={
            "development": "primary",
            "validation": "primary",
            "holdout": "holdout",
        },
        run_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        causal_proven=False,
        samples=samples,
    )


class TestTheAdmittedSetIsProductionsOwn:
    def test_the_ladder_reproduces_the_captures_candidate_list(
        self, capture, samples
    ) -> None:
        """The claim that entitles CA to call its ADMITTED stage the live
        product's decision, rather than a reconstruction of it."""
        sample = next(item for item in samples if item.name == "holdout")
        instants, _bars_by, _vol = build_sample_instants(
            capture, universe="holdout", sample=sample
        )
        admitted = sorted(
            (item.symbol, item.bar_index)
            for item in instants
            if item.stage is AdmissionStage.ADMITTED
        )
        expected = sorted(
            (item.symbol, item.signal_index)
            for item in capture.universe("holdout").capture.candidates
            if sample.holds(item.symbol, item.signal_at)
            and item.signal_index + 60 < len(capture.universe("holdout").capture.bars_by_symbol[item.symbol])
        )
        assert admitted == expected
        assert admitted

    def test_every_rung_of_the_ladder_is_populated(self, capture, samples) -> None:
        """A fixture exercising only one rung would make the gate attribution
        vacuous."""
        sample = next(item for item in samples if item.name == "holdout")
        instants, _b, _v = build_sample_instants(
            capture, universe="holdout", sample=sample
        )
        reached = {item.stage for item in instants}
        assert AdmissionStage.ADMITTED in reached
        assert AdmissionStage.UNCONFIRMED in reached
        assert AdmissionStage.CONFIRMED_REPEAT in reached
        assert AdmissionStage.TALLY_DISAGREED in reached


class TestOfflineReproduction:
    def test_the_study_runs_with_the_network_made_fatal(self, capture, samples) -> None:
        """Proven by making a fetch raise, not by asserting none happened."""
        import fmis.swing_setup.backtest_replay as transport

        original = transport.fetch_raw_klines

        def explode(*args, **kwargs):  # pragma: no cover - must never be called
            raise AssertionError("CA reached the network; it has no live path")

        transport.fetch_raw_klines = explode
        try:
            result = study_from_capture(
                capture,
                universe_for_sample={"development": "primary", "holdout": "holdout"},
                run_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
                samples=samples,
            )
        finally:
            transport.fetch_raw_klines = original
        assert result.results

    def test_two_runs_of_the_same_capture_agree_exactly(self, capture, samples) -> None:
        def run():
            return study_from_capture(
                capture,
                universe_for_sample={"development": "primary"},
                run_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
                samples=samples,
            )

        first, second = run(), run()
        assert first.payload()["results"] == second.payload()["results"]
        assert first.control_identity_digest == second.control_identity_digest

    def test_an_edited_capture_is_refused_before_anything_is_measured(
        self, samples
    ) -> None:
        payload = _capture_payload()
        symbol = sorted(SYMBOLS)[0]
        # Edited to a value that is still a VALID bar, so the refusal under test
        # is the digest's and not the price model's — an edit the bar validator
        # would reject anyway proves nothing about the digest.
        payload["universes"]["primary"]["bars"][symbol][100][3] = "1.000000"
        with pytest.raises(SwingLabError, match="does not verify"):
            study_from_capture(
                PersistenceCaptureArtifact(payload),
                universe_for_sample={"development": "primary"},
                run_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
                samples=samples,
            )

    def test_an_unsealed_sample_name_is_refused(self, capture, samples) -> None:
        with pytest.raises(SwingLabError, match="no sample named"):
            study_from_capture(
                capture,
                universe_for_sample={"invented": "primary"},
                run_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
                samples=samples,
            )

    def test_a_foreign_artifact_type_is_refused(self) -> None:
        with pytest.raises(TypeError):
            study_from_capture(
                object(),  # type: ignore[arg-type]
                universe_for_sample={},
                run_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
            )


class TestTheStudyArtifact:
    def test_it_round_trips_through_a_file(self, study, tmp_path) -> None:
        payload = encode_admission_study(study, writer="test")
        path = write_admission_study(payload, tmp_path / "ca.json.gz")
        decoded = read_admission_study(path)
        assert verify_admission_study_digest(decoded)
        assert decoded.payload["results"] == payload["results"]
        assert decoded.payload["assessments"] == payload["assessments"]

    def test_it_carries_both_digests_so_a_disagreement_can_be_attributed(
        self, study
    ) -> None:
        decoded = AdmissionStudyArtifact(encode_admission_study(study, writer="test"))
        assert decoded.preregistration_digest == CA_PREREGISTRATION_DIGEST
        assert decoded.capture_content_digest

    def test_the_same_study_written_to_two_paths_is_byte_identical(
        self, study, tmp_path
    ) -> None:
        """`GzipFile` embeds a timestamp and the file object's name unless both
        are pinned. Milestone BZ found this the hard way."""
        payload = encode_admission_study(study, writer="test")
        first = write_admission_study(payload, tmp_path / "a.json.gz")
        second = write_admission_study(payload, tmp_path / "b.json.gz")
        assert first.read_bytes() == second.read_bytes()

    def test_an_uncompressed_write_round_trips_too(self, study, tmp_path) -> None:
        payload = encode_admission_study(study, writer="test")
        path = write_admission_study(payload, tmp_path / "ca.json", compress=False)
        assert verify_admission_study_digest(read_admission_study(path))

    def test_an_edited_effect_is_caught_by_the_digest(self, study, tmp_path) -> None:
        payload = encode_admission_study(study, writer="test")
        payload["results"][0]["effect"] = 99.0
        path = write_admission_study(payload, tmp_path / "ca.json.gz")
        assert not verify_admission_study_digest(read_admission_study(path))

    def test_an_edited_manifest_field_is_caught_by_the_digest(
        self, study, tmp_path
    ) -> None:
        payload = encode_admission_study(study, writer="test")
        payload["manifest"]["causal_proven"] = True
        path = write_admission_study(payload, tmp_path / "ca.json.gz")
        assert not verify_admission_study_digest(read_admission_study(path))

    def test_a_bz_capture_handed_in_by_mistake_is_refused_by_name(
        self, tmp_path
    ) -> None:
        path = tmp_path / "capture.json"
        path.write_text(json.dumps(_capture_payload()), encoding="utf-8")
        with pytest.raises(SwingLabError, match="not interchangeable"):
            read_admission_study(path)

    def test_a_foreign_schema_version_is_refused_never_upgraded(
        self, study, tmp_path
    ) -> None:
        payload = encode_admission_study(study, writer="test")
        payload["schema_version"] = CA_ARTIFACT_SCHEMA_VERSION + 1
        path = write_admission_study(payload, tmp_path / "ca.json.gz")
        with pytest.raises(SwingLabError, match="NOT.*upgraded silently"):
            read_admission_study(path)

    @pytest.mark.parametrize(
        "field",
        [
            "preregistration_id",
            "preregistration_digest",
            "capture_content_digest",
            "run_at",
            "primary_horizon",
            "causal_proven",
            "content_digest",
        ],
    )
    def test_a_missing_manifest_field_is_refused_by_name(
        self, study, tmp_path, field: str
    ) -> None:
        payload = encode_admission_study(study, writer="test")
        del payload["manifest"][field]
        path = write_admission_study(payload, tmp_path / "ca.json.gz")
        with pytest.raises(SwingLabError, match=field):
            read_admission_study(path)

    def test_a_truncated_gzip_is_refused(self, study, tmp_path) -> None:
        path = write_admission_study(
            encode_admission_study(study, writer="test"), tmp_path / "ca.json.gz"
        )
        path.write_bytes(path.read_bytes()[:-40])
        with pytest.raises(SwingLabError, match="truncated or corrupt"):
            read_admission_study(path)

    def test_a_non_json_file_is_refused(self, tmp_path) -> None:
        path = tmp_path / "ca.json"
        path.write_text("not json at all", encoding="utf-8")
        with pytest.raises(SwingLabError, match="not valid JSON"):
            read_admission_study(path)

    def test_a_json_array_is_refused(self, tmp_path) -> None:
        path = tmp_path / "ca.json"
        path.write_text("[]", encoding="utf-8")
        with pytest.raises(SwingLabError, match="not a JSON object"):
            read_admission_study(path)

    def test_a_missing_file_is_refused(self, tmp_path) -> None:
        with pytest.raises(SwingLabError, match="cannot read study"):
            read_admission_study(tmp_path / "absent.json")

    def test_the_digest_ignores_only_its_own_slot(self, study) -> None:
        payload = encode_admission_study(study, writer="test")
        without = dict(payload)
        without["manifest"] = {
            k: v for k, v in payload["manifest"].items() if k != "content_digest"
        }
        assert admission_study_digest(payload) == admission_study_digest(without)

    def test_verify_refuses_a_foreign_type(self) -> None:
        with pytest.raises(TypeError):
            verify_admission_study_digest(object())  # type: ignore[arg-type]

    def test_the_kind_is_declared(self, study) -> None:
        assert encode_admission_study(study, writer="t")["kind"] == CA_ARTIFACT_KIND


class TestNoHoldoutContamination:
    def test_a_sample_never_holds_an_instant_from_another_samples_window(
        self, capture, samples
    ) -> None:
        by_name = {item.name: item for item in samples}
        for name in ("development", "validation"):
            instants, _b, _v = build_sample_instants(
                capture, universe="primary", sample=by_name[name]
            )
            for instant in instants:
                assert by_name[name].holds(instant.symbol, instant.as_of)

    def test_development_and_validation_instants_are_disjoint(
        self, capture, samples
    ) -> None:
        by_name = {item.name: item for item in samples}
        seen = {}
        for name in ("development", "validation"):
            instants, _b, _v = build_sample_instants(
                capture, universe="primary", sample=by_name[name]
            )
            seen[name] = {(i.symbol, i.bar_index) for i in instants}
        assert not (seen["development"] & seen["validation"])

    def test_a_result_always_names_its_own_sample(self, study) -> None:
        """There is no field that could hold a pooled number, and no result
        that could forget which sample it came from."""
        for (_family, sample), result in study.results.items():
            assert result.sample == sample
