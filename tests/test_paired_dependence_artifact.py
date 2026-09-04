"""The CD artifact: what it carries, what it refuses, and offline reproduction.

Milestone CD exists because a file was not kept, so the artifact's job is not to
record a conclusion — it is to record **the observations**, with enough
provenance that every figure can be re-derived from the file alone. These tests
assert that, and that the reader fails closed on every way the file can be wrong.
"""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone

import pytest

from fmis.paired_dependence.artifact import (
    CD_ARTIFACT_KIND,
    CD_ARTIFACT_SCHEMA_VERSION,
    PairedDependenceArtifact,
    encode_dependence_study,
    read_dependence_study,
    dependence_rows_of,
    dependence_study_digest,
    verify_dependence_study_digest,
    write_dependence_study,
)
from fmis.paired_dependence.models import PairedDependenceError
from fmis.paired_dependence.preregistration import CD_PREREGISTRATION_DIGEST
from fmis.paired_dependence.study import study_from_capture, study_from_rows
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
def payload(cd_study):
    return encode_dependence_study(cd_study, writer="tests")


class TestEncoding:
    def test_it_declares_its_kind_and_schema(self, payload):
        assert payload["kind"] == CD_ARTIFACT_KIND
        assert payload["schema_version"] == CD_ARTIFACT_SCHEMA_VERSION

    def test_it_carries_every_observation(self, payload, cd_study):
        assert len(payload["observations"]) == len(cd_study.rows)

    def test_it_carries_the_four_digests_that_attribute_a_disagreement(self, payload):
        manifest = payload["manifest"]
        assert manifest["preregistration_digest"] == CD_PREREGISTRATION_DIGEST
        assert manifest["capture_content_digest"]
        assert manifest["ca_preregistration_digest"]
        assert manifest["content_digest"]

    def test_encoding_is_deterministic(self, cd_study):
        first = encode_dependence_study(cd_study, writer="tests")
        second = encode_dependence_study(cd_study, writer="tests")
        assert first == second

    def test_the_digest_excludes_only_itself(self, payload):
        stripped = json.loads(json.dumps(payload))
        del stripped["manifest"]["content_digest"]
        assert dependence_study_digest(stripped) == payload["manifest"]["content_digest"]

    def test_editing_a_measured_correlation_breaks_the_digest(self, payload):
        edited = json.loads(json.dumps(payload))
        edited["panels"][0]["between_asset"]["point"] = 0.99
        assert dependence_study_digest(edited) != payload["manifest"]["content_digest"]

    def test_editing_an_observation_breaks_the_digest(self, payload):
        edited = json.loads(json.dumps(payload))
        edited["observations"][0]["difference"] = 99.0
        assert dependence_study_digest(edited) != payload["manifest"]["content_digest"]

    def test_editing_the_verdict_breaks_the_digest(self, payload):
        edited = json.loads(json.dumps(payload))
        edited["assessment"]["verdict"] = "measured"
        assert dependence_study_digest(edited) != payload["manifest"]["content_digest"]


class TestWriting:
    def test_the_file_is_byte_reproducible(self, payload, tmp_path):
        first = write_dependence_study(payload, tmp_path / "a.json.gz")
        second = write_dependence_study(payload, tmp_path / "b.json.gz")
        assert first.read_bytes() == second.read_bytes()

    def test_the_digest_does_not_depend_on_the_filename(self, payload, tmp_path):
        write_dependence_study(payload, tmp_path / "one.json.gz")
        write_dependence_study(payload, tmp_path / "another-name-entirely.json.gz")
        assert read_dependence_study(tmp_path / "one.json.gz").content_digest == read_dependence_study(
            tmp_path / "another-name-entirely.json.gz"
        ).content_digest

    def test_it_refuses_to_overwrite(self, payload, tmp_path):
        write_dependence_study(payload, tmp_path / "c.json.gz")
        with pytest.raises(PairedDependenceError, match="never overwritten"):
            write_dependence_study(payload, tmp_path / "c.json.gz")

    def test_uncompressed_is_readable_too(self, payload, tmp_path):
        target = write_dependence_study(payload, tmp_path / "plain.json", compress=False)
        assert read_dependence_study(target).content_digest == payload["manifest"]["content_digest"]


class TestReadingFailsClosed:
    def _write(self, payload, tmp_path, name="s.json.gz"):
        target = tmp_path / name
        with open(target, "wb") as raw:
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as stream:
                stream.write(json.dumps(payload).encode("utf-8"))
        return target

    def test_a_missing_file_is_refused(self, tmp_path):
        with pytest.raises(PairedDependenceError, match="cannot read"):
            read_dependence_study(tmp_path / "nope.json.gz")

    def test_a_foreign_kind_is_refused_by_name(self, payload, tmp_path):
        edited = json.loads(json.dumps(payload))
        edited["kind"] = "bz-persistence-capture"
        with pytest.raises(PairedDependenceError, match="not interchangeable"):
            read_dependence_study(self._write(edited, tmp_path))

    def test_a_foreign_schema_version_is_refused_and_not_upgraded(self, payload, tmp_path):
        edited = json.loads(json.dumps(payload))
        edited["schema_version"] = CD_ARTIFACT_SCHEMA_VERSION + 1
        with pytest.raises(PairedDependenceError, match="NOT\\s+upgraded silently"):
            read_dependence_study(self._write(edited, tmp_path))

    @pytest.mark.parametrize(
        "section",
        ["observations", "panels", "calibration", "requirement", "assessment",
         "cc_comparison", "reconstruction", "preregistration"],
    )
    def test_a_missing_section_is_refused_by_name(self, payload, tmp_path, section):
        edited = json.loads(json.dumps(payload))
        del edited[section]
        with pytest.raises(PairedDependenceError, match=section):
            read_dependence_study(self._write(edited, tmp_path))

    @pytest.mark.parametrize(
        "field",
        ["preregistration_digest", "capture_content_digest",
         "ca_preregistration_digest", "primary_horizon", "master_seed",
         "universe_for_sample"],
    )
    def test_a_missing_manifest_field_is_refused_by_name(self, payload, tmp_path, field):
        edited = json.loads(json.dumps(payload))
        del edited["manifest"][field]
        with pytest.raises(PairedDependenceError, match=field):
            read_dependence_study(self._write(edited, tmp_path))

    def test_an_artifact_with_no_observations_is_refused(self, payload, tmp_path):
        edited = json.loads(json.dumps(payload))
        edited["observations"] = []
        with pytest.raises(PairedDependenceError, match="holds no observations"):
            read_dependence_study(self._write(edited, tmp_path))

    @pytest.mark.parametrize(
        "field", ["economic_asset", "bar_index", "difference", "capture_content_digest"]
    )
    def test_an_observation_missing_provenance_is_refused(self, payload, tmp_path, field):
        edited = json.loads(json.dumps(payload))
        del edited["observations"][0][field]
        with pytest.raises(PairedDependenceError, match=field):
            read_dependence_study(self._write(edited, tmp_path))

    def test_invalid_json_is_refused(self, tmp_path):
        target = tmp_path / "bad.json"
        target.write_text("{not json", encoding="utf-8")
        with pytest.raises(PairedDependenceError, match="not valid JSON"):
            read_dependence_study(target)

    def test_a_json_array_is_refused(self, tmp_path):
        target = tmp_path / "arr.json"
        target.write_text("[]", encoding="utf-8")
        with pytest.raises(PairedDependenceError, match="not a JSON object"):
            read_dependence_study(target)

    def test_a_truncated_gzip_is_refused(self, payload, tmp_path):
        target = self._write(payload, tmp_path)
        target.write_bytes(target.read_bytes()[:40])
        with pytest.raises(PairedDependenceError, match="truncated or corrupt"):
            read_dependence_study(target)


class TestSealAndSourceAreSeparateFailures:
    def _artifact(self, payload):
        return PairedDependenceArtifact(json.loads(json.dumps(payload)))

    def test_an_intact_file_under_a_foreign_seal_is_refused_as_a_foreign_design(
        self, payload
    ):
        edited = json.loads(json.dumps(payload))
        edited["manifest"]["preregistration_digest"] = "0" * 64
        artifact = PairedDependenceArtifact(edited)
        with pytest.raises(PairedDependenceError, match="different Milestone CD design"):
            artifact.require_seal()

    def test_a_foreign_preregistration_id_is_refused_separately(self, payload):
        edited = json.loads(json.dumps(payload))
        edited["manifest"]["preregistration_id"] = "cd-something-else"
        with pytest.raises(PairedDependenceError, match="measured under pre-registration"):
            PairedDependenceArtifact(edited).require_seal()

    def test_this_build_s_own_study_passes_the_seal_check(self, payload):
        self._artifact(payload).require_seal()

    def test_a_foreign_source_capture_is_refused(self, payload):
        artifact = self._artifact(payload)
        with pytest.raises(PairedDependenceError, match="not reconciled here"):
            artifact.require_source("f" * 64)

    def test_the_named_source_capture_is_accepted(self, payload):
        artifact = self._artifact(payload)
        artifact.require_source(artifact.capture_content_digest)

    def test_digest_verification_is_a_different_question_from_the_seal(self, payload):
        edited = json.loads(json.dumps(payload))
        edited["manifest"]["preregistration_digest"] = "0" * 64
        artifact = PairedDependenceArtifact(edited)
        # The file is intact under its own digest rule only if the digest is
        # recomputed; here it is NOT, and that is the point: the two checks fail
        # for different reasons and are not merged.
        assert verify_dependence_study_digest(artifact) is False
        with pytest.raises(PairedDependenceError):
            artifact.require_seal()

    def test_verify_refuses_a_foreign_object(self):
        with pytest.raises(TypeError):
            verify_dependence_study_digest(object())


class TestRowsOf:
    def test_every_row_comes_back(self, payload, cd_study):
        artifact = PairedDependenceArtifact(json.loads(json.dumps(payload)))
        assert len(dependence_rows_of(artifact)) == len(cd_study.rows)

    def test_the_rows_are_equal_to_the_originals(self, payload, cd_study):
        artifact = PairedDependenceArtifact(json.loads(json.dumps(payload)))
        assert dependence_rows_of(artifact) == cd_study.rows

    def test_a_hand_edited_difference_is_refused_before_the_digest_is_consulted(
        self, payload
    ):
        edited = json.loads(json.dumps(payload))
        edited["observations"][0]["difference"] = 99.0
        artifact = PairedDependenceArtifact(edited)
        with pytest.raises(PairedDependenceError, match="has been edited"):
            dependence_rows_of(artifact)

    def test_it_refuses_a_foreign_object(self):
        with pytest.raises(TypeError):
            dependence_rows_of(object())


class TestOfflineReproductionFromTheFile:
    def test_the_file_alone_reproduces_every_figure_with_no_capture(
        self, payload, cd_study, tmp_path, monkeypatch
    ):
        import fmis.swing_lab.admission_study as ca
        import fmis.swing_setup.backtest_replay as transport

        target = write_dependence_study(payload, tmp_path / "offline.json.gz")
        monkeypatch.setattr(
            transport,
            "fetch_raw_klines",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")),
        )
        monkeypatch.setattr(
            ca,
            "study_from_capture",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("replayed")),
        )
        artifact = read_dependence_study(target)
        assert verify_dependence_study_digest(artifact)
        artifact.require_seal()
        reproduced = study_from_rows(
            dependence_rows_of(artifact),
            manifest=artifact.manifest,
            reconstruction=artifact.payload["reconstruction"],
        )
        original = cd_study.payload()
        again = reproduced.payload()
        # The manifest legitimately gains three fields on the way through a file:
        # `source` says the figures were re-derived rather than replayed, and
        # `writer` and `content_digest` belong to the artifact rather than to the
        # measurement. Everything else — every observation, every panel, every
        # interval, the calibration, the requirement and the verdict — must be
        # identical.
        for key in ("source", "writer", "content_digest"):
            original["manifest"].pop(key, None)
            again["manifest"].pop(key, None)
        assert again == original
