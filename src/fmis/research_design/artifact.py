"""Encoding a design assessment so a future pre-registration can cite it.

**This module opens no file.** It encodes, digests and verifies a payload;
whether that payload is written anywhere, and where, is a caller's decision. A
design assessment is **recomputable and disposable** — every input is metadata
and every step is deterministic — so there is nothing here that needs a durable
record kind, and adding one would create a store obligation for a document that
can be regenerated in milliseconds.

**The citation seam, and why it does not create a cycle.** A future
pre-registration should be able to record *"this study was sealed knowing its
design could resolve X"*. The direction that makes that safe is one-way:

    design assessment  --digested-->  citation  --embedded in-->  pre-registration
                                                                        |
                                                                   its own digest

`design_assessment_digest` covers the question, the effect, the samples, the
dependence model, the estimator, the target, the mode, the resolution, the
requirements, the verdict, the assumptions and the caveats — and **nothing about
any pre-registration**. So embedding a citation changes the pre-registration's
digest and cannot change the assessment's. A regression asserts both halves,
because a citation that fed back into the thing it cites would be a seal that
could never be computed.

**Sealed documents are never rewritten.** Milestones BY, BZ and CA are sealed
with their own digests and this package does not touch them. The seam is forward
only: the next seal may carry a citation; the previous ones stay as they are.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Final

from fmis.research_design.models import ResearchDesignError

__all__ = [
    "RESEARCH_DESIGN_SCHEMA_VERSION",
    "RESEARCH_DESIGN_ARTIFACT_KIND",
    "design_assessment_digest",
    "encode_design_assessment",
    "verify_design_assessment_digest",
    "citation_for",
]

#: Bumped whenever the encoded layout changes. **Never upgraded silently on read.**
RESEARCH_DESIGN_SCHEMA_VERSION: Final[int] = 1

#: What this document is, carried so a reader handed some other artifact refuses
#: it by name rather than failing on a missing key three levels down.
RESEARCH_DESIGN_ARTIFACT_KIND: Final[str] = "research-design-assessment"

_REQUIRED_SECTIONS: Final[tuple[str, ...]] = (
    "assessment_id",
    "mode",
    "question",
    "effect",
    "dependence",
    "estimator",
    "target",
    "frames",
    "resolution",
    "requirements",
    "verdict",
    "limiting_factor",
    "assumptions",
)


def design_assessment_digest(payload: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical content, **excluding the digest field itself**.

    Taken over canonical JSON rather than over any file, so a compressor's header
    or a writer's line endings cannot reach it. Every substantive field is
    covered: a hand-edited verdict, a moved effect threshold, a changed cluster
    count and a swapped mode are all caught.
    """
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    manifest = {
        key: value
        for key, value in payload.get("manifest", {}).items()
        if key != "content_digest"
    }
    canonical = json.dumps(
        {**{k: v for k, v in payload.items() if k != "manifest"}, "manifest": manifest},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def encode_design_assessment(assessment, *, writer: str) -> dict[str, Any]:
    """Encode one `DesignAssessment` into a JSON-safe payload with its own digest.

    Raises:
        ResearchDesignError: ``writer`` is empty, or the assessment does not
            produce the sections a reader needs.
    """
    if not isinstance(writer, str) or not writer.strip():
        raise ResearchDesignError(
            "writer must name what produced this document; an artifact that cannot "
            "say who wrote it cannot be audited"
        )
    body = assessment.payload()
    missing = [name for name in _REQUIRED_SECTIONS if name not in body]
    if missing:
        raise ResearchDesignError(
            f"this assessment produced no {', '.join(missing)} section(s)"
        )
    payload: dict[str, Any] = {
        "schema_version": RESEARCH_DESIGN_SCHEMA_VERSION,
        "kind": RESEARCH_DESIGN_ARTIFACT_KIND,
        **body,
    }
    payload["manifest"] = {"writer": writer}
    payload["manifest"]["content_digest"] = design_assessment_digest(payload)
    return payload


def verify_design_assessment_digest(payload: Mapping[str, Any]) -> bool:
    """Recompute the content digest and compare it to the stored one.

    Raises:
        ResearchDesignError: the payload is not a design assessment, was written
            by another schema version, or carries no digest to check.
    """
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    kind = payload.get("kind")
    if kind != RESEARCH_DESIGN_ARTIFACT_KIND:
        raise ResearchDesignError(
            f"this document declares kind {kind!r}, not "
            f"{RESEARCH_DESIGN_ARTIFACT_KIND!r}; documents of different kinds are "
            "not interchangeable"
        )
    version = payload.get("schema_version")
    if version != RESEARCH_DESIGN_SCHEMA_VERSION:
        raise ResearchDesignError(
            f"this document was written by schema version {version!r}; this build "
            f"reads version {RESEARCH_DESIGN_SCHEMA_VERSION}. It is NOT upgraded "
            "silently — a reader guessing at an older layout will eventually "
            "mis-read a field and report a design nobody assessed"
        )
    manifest = payload.get("manifest")
    if not isinstance(manifest, Mapping) or "content_digest" not in manifest:
        raise ResearchDesignError(
            "this document carries no content digest, so there is nothing to verify"
        )
    return design_assessment_digest(payload) == manifest["content_digest"]


def citation_for(payload: Mapping[str, Any]) -> dict[str, str]:
    """The minimal record a future pre-registration embeds to cite this assessment.

    Deliberately five strings and no numbers. A seal that copied the effect
    threshold, the sample counts and the verdict would hold a second copy of
    facts that can drift from the first; the digest is the reference and the
    assessment is the document.

    Raises:
        ResearchDesignError: the payload does not verify, so the citation would
            point at a document that no longer says what it said.
    """
    if not verify_design_assessment_digest(payload):
        raise ResearchDesignError(
            "this design assessment's content digest does not match its content, so "
            "a citation of it would name a document that has been edited since"
        )
    return {
        "assessment_id": str(payload["assessment_id"]),
        "content_digest": str(payload["manifest"]["content_digest"]),
        "mode": str(payload["mode"]),
        "verdict": str(payload["verdict"]),
        "limiting_factor": str(payload["limiting_factor"]),
    }
