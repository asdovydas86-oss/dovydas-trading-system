"""The artifact, the digest, and the one-way citation seam.

The seam is the point: a future pre-registration must be able to record that it
was sealed knowing what its design could resolve, **without** the assessment's own
digest depending on the seal that cites it. Two tests hold that in place from both
ends — embedding a citation moves the seal's digest, and moves nothing here.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from fmis.research_design.artifact import (
    RESEARCH_DESIGN_ARTIFACT_KIND,
    RESEARCH_DESIGN_SCHEMA_VERSION,
    citation_for,
    design_assessment_digest,
    encode_design_assessment,
    verify_design_assessment_digest,
)
from fmis.research_design.models import ResearchDesignError
from fmis.research_design.resolution import post_hoc_resolution
from fmis.research_design.verdict import assess_research_design
from tests.research_design_helpers import (
    UNIT,
    a_dependence,
    a_frame,
    a_question,
    a_target,
    an_effect,
    an_estimator,
)


def _assessment(width: float = 0.5578, assessment_id: str = "a-1"):
    frame = a_frame()
    return assess_research_design(
        assessment_id=assessment_id,
        question=a_question(),
        effect=an_effect(),
        uncertainty_unit=UNIT,
        dependence=a_dependence(),
        estimator=an_estimator(),
        target=a_target(),
        frames=(frame,),
        primary_sample=frame.name,
        resolution=post_hoc_resolution(
            frame=frame,
            observed_half_width=width,
            effect=an_effect(),
            target=a_target(),
            estimator=an_estimator(),
        ),
        sensitivity_correlations=(0.0, 0.10),
    )


class TestEncoding:
    def test_an_encoded_assessment_verifies_against_its_own_digest(self) -> None:
        payload = encode_design_assessment(_assessment(), writer="a test")
        assert verify_design_assessment_digest(payload)

    def test_it_declares_its_kind_and_schema_version(self) -> None:
        payload = encode_design_assessment(_assessment(), writer="a test")
        assert payload["kind"] == RESEARCH_DESIGN_ARTIFACT_KIND
        assert payload["schema_version"] == RESEARCH_DESIGN_SCHEMA_VERSION

    def test_it_is_json_serialisable(self) -> None:
        json.dumps(encode_design_assessment(_assessment(), writer="a test"))

    def test_two_encodings_of_one_assessment_are_byte_identical(self) -> None:
        first = encode_design_assessment(_assessment(), writer="a test")
        second = encode_design_assessment(_assessment(), writer="a test")
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    def test_an_unattributed_writer_is_refused(self) -> None:
        with pytest.raises(ResearchDesignError, match="who wrote it"):
            encode_design_assessment(_assessment(), writer="   ")

    def test_an_object_that_produces_no_sections_is_refused(self) -> None:
        class Hollow:
            def payload(self) -> dict:
                return {"assessment_id": "x"}

        with pytest.raises(ResearchDesignError, match="produced no"):
            encode_design_assessment(Hollow(), writer="a test")


class TestTampering:
    @pytest.mark.parametrize(
        "field, value",
        (
            ("verdict", "ready"),
            ("limiting_factor", "none"),
            ("mode", "prospective"),
            ("primary_sample", "holdout"),
        ),
    )
    def test_an_edited_field_is_caught(self, field: str, value: str) -> None:
        payload = encode_design_assessment(_assessment(), writer="a test")
        payload[field] = value
        assert not verify_design_assessment_digest(payload)

    def test_a_relabelled_mode_is_caught_by_the_digest(self) -> None:
        """The specific tamper this package exists to make loud."""
        payload = encode_design_assessment(_assessment(), writer="a test")
        assert payload["mode"] == "post_hoc"
        payload["mode"] = "prospective"
        payload["resolution"]["mode"] = "prospective"
        assert not verify_design_assessment_digest(payload)

    def test_an_edited_effect_threshold_is_caught(self) -> None:
        payload = encode_design_assessment(_assessment(), writer="a test")
        payload["effect"]["magnitude"] = "0.9"
        assert not verify_design_assessment_digest(payload)

    def test_an_edited_manifest_field_is_caught(self) -> None:
        payload = encode_design_assessment(_assessment(), writer="a test")
        payload["manifest"]["writer"] = "somebody else"
        assert not verify_design_assessment_digest(payload)

    def test_the_digest_does_not_cover_the_slot_it_is_written_into(self) -> None:
        payload = encode_design_assessment(_assessment(), writer="a test")
        stored = payload["manifest"]["content_digest"]
        payload["manifest"]["content_digest"] = "0" * 64
        assert design_assessment_digest(payload) == stored

    def test_a_foreign_kind_is_refused_by_name(self) -> None:
        payload = encode_design_assessment(_assessment(), writer="a test")
        payload["kind"] = "ca-admission-study"
        with pytest.raises(ResearchDesignError, match="not interchangeable"):
            verify_design_assessment_digest(payload)

    def test_a_foreign_schema_version_is_never_upgraded_silently(self) -> None:
        payload = encode_design_assessment(_assessment(), writer="a test")
        payload["schema_version"] = RESEARCH_DESIGN_SCHEMA_VERSION + 1
        with pytest.raises(ResearchDesignError, match="NOT upgraded"):
            verify_design_assessment_digest(payload)

    def test_a_payload_with_no_digest_has_nothing_to_verify(self) -> None:
        payload = encode_design_assessment(_assessment(), writer="a test")
        del payload["manifest"]["content_digest"]
        with pytest.raises(ResearchDesignError, match="nothing to verify"):
            verify_design_assessment_digest(payload)

    def test_a_non_mapping_is_a_programmer_error(self) -> None:
        with pytest.raises(TypeError):
            verify_design_assessment_digest("{}")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            design_assessment_digest("{}")  # type: ignore[arg-type]

    def test_the_digest_is_over_canonical_json_not_over_a_file(self) -> None:
        payload = encode_design_assessment(_assessment(), writer="a test")
        manifest = {
            key: value
            for key, value in payload["manifest"].items()
            if key != "content_digest"
        }
        canonical = json.dumps(
            {**{k: v for k, v in payload.items() if k != "manifest"},
             "manifest": manifest},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        assert payload["manifest"]["content_digest"] == hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest()


class TestTheCitationSeam:
    def test_a_citation_is_five_strings_and_no_numbers(self) -> None:
        payload = encode_design_assessment(_assessment(), writer="a test")
        citation = citation_for(payload)
        assert set(citation) == {
            "assessment_id", "content_digest", "mode", "verdict", "limiting_factor",
        }
        assert all(isinstance(value, str) for value in citation.values())

    def test_a_citation_of_an_edited_document_is_refused(self) -> None:
        payload = encode_design_assessment(_assessment(), writer="a test")
        payload["verdict"] = "ready"
        with pytest.raises(ResearchDesignError, match="has been edited since"):
            citation_for(payload)

    def test_embedding_a_citation_moves_the_seal_and_not_the_assessment(self) -> None:
        """The whole seam, in one assertion pair. No cycle is possible."""
        payload = encode_design_assessment(_assessment(), writer="a test")
        citation = citation_for(payload)
        assessment_digest_before = payload["manifest"]["content_digest"]

        def seal_digest(content: dict) -> str:
            return hashlib.sha256(
                json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()

        seal = {"id": "future-preregistration-v1", "families": ["a", "b"]}
        without = seal_digest(seal)
        with_citation = seal_digest({**seal, "design_assessment": citation})

        assert without != with_citation, "the seal must record that it cited a design"
        assert payload["manifest"]["content_digest"] == assessment_digest_before
        assert verify_design_assessment_digest(payload)

    def test_the_assessment_digest_names_no_preregistration_at_all(self) -> None:
        """A field that mentioned a seal would be the first half of a cycle."""
        payload = encode_design_assessment(_assessment(), writer="a test")
        rendered = json.dumps(payload).lower()
        for token in ("preregistration_digest", "seal_digest", "sealed_digest"):
            assert token not in rendered

    def test_two_different_assessments_carry_two_different_digests(self) -> None:
        first = encode_design_assessment(_assessment(width=0.5), writer="a test")
        second = encode_design_assessment(_assessment(width=0.6), writer="a test")
        assert (
            first["manifest"]["content_digest"] != second["manifest"]["content_digest"]
        )
