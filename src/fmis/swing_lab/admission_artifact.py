"""Persisting Milestone CA's **result**, so a later run is a diff rather than an argument.

Milestone BZ persists a *capture* — the inputs a study was computed from — and CA
reads one. This module persists the other half: what CA concluded from those
inputs, with enough provenance that the pair can be re-joined later.

**The two digests that make that possible.** A CA artifact carries the
`preregistration_digest` it was measured under *and* the `capture_content_digest`
of the BZ capture it was measured over. Together they answer the question BZ
could not answer of BY:

> Two runs disagree. Is it the code, the rules, or the data?

Different capture digest → the data. Different pre-registration digest → the
rules. Both equal and the numbers differ → the code, and nothing else.

**It fails closed, never open.** A foreign schema version, a capture artifact
handed in by mistake, a missing manifest field or an edited payload is refused by
name. Nothing is recomputed to fill a gap, because a reader that re-measures a
missing field has silently turned an audit back into a run.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from fmis.swing_lab.models import SwingLabError

__all__ = [
    "CA_ARTIFACT_SCHEMA_VERSION",
    "CA_ARTIFACT_KIND",
    "AdmissionStudyArtifact",
    "encode_admission_study",
    "admission_study_digest",
    "write_admission_study",
    "read_admission_study",
    "verify_admission_study_digest",
]

#: Bumped whenever this layout changes. **Never upgraded silently on read.**
CA_ARTIFACT_SCHEMA_VERSION: Final[int] = 1

#: What this file is. Carried so a reader handed a BZ *capture* refuses it by
#: name rather than failing on a missing key three levels down.
CA_ARTIFACT_KIND: Final[str] = "ca-admission-study"

_REQUIRED_MANIFEST: Final[tuple[str, ...]] = (
    "preregistration_id",
    "preregistration_digest",
    "capture_content_digest",
    "run_at",
    "primary_horizon",
    "causal_proven",
)


def admission_study_digest(payload: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical content, **excluding the digest field itself**.

    The digest cannot cover the slot it is written into, so `manifest` is
    digested with `content_digest` removed. Every other field — the
    pre-registration digest, the capture digest, the run timestamp, every result
    and every verdict — **is** covered, so a hand-edited effect is caught exactly
    as a hand-edited manifest is.

    Taken over canonical JSON rather than over the file, so gzip's own header
    cannot reach it. `fmis.swing_lab.persistence_artifact` reached this
    conclusion first and this is the same rule, deliberately.
    """
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


def encode_admission_study(study, *, writer: str) -> dict[str, Any]:
    """Encode one `AdmissionStudy` into a JSON-safe payload with its own digest."""
    payload: dict[str, Any] = {
        "schema_version": CA_ARTIFACT_SCHEMA_VERSION,
        "kind": CA_ARTIFACT_KIND,
        **study.payload(),
    }
    payload["manifest"] = {**dict(payload.get("manifest", {})), "writer": writer}
    payload["manifest"]["content_digest"] = admission_study_digest(payload)
    return payload


def write_admission_study(
    payload: Mapping[str, Any], path: str | Path, *, compress: bool = True
) -> Path:
    """Write the study. **Gzip is made deterministic, deliberately.**

    `gzip.GzipFile` writes the current time — and, given a file object, that
    object's name — into its header, so two byte-identical studies would produce
    two different files. ``mtime=0`` and ``filename=""`` make the *file*
    reproducible too, and the digest is still taken over the canonical JSON so a
    reader never depends on it.
    """
    target = Path(path)
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if compress:
        if target.suffix != ".gz":
            target = target.with_suffix(target.suffix + ".gz")
        with open(target, "wb") as raw:
            with gzip.GzipFile(
                filename="", fileobj=raw, mode="wb", compresslevel=6, mtime=0
            ) as stream:
                stream.write(canonical)
    else:
        target.write_bytes(canonical)
    return target


class AdmissionStudyArtifact:
    """A decoded CA study. **Refuses anything it cannot fully account for.**"""

    __slots__ = ("_payload",)

    def __init__(self, payload: Mapping[str, Any]) -> None:
        kind = payload.get("kind")
        if kind != CA_ARTIFACT_KIND:
            raise SwingLabError(
                f"this file declares kind {kind!r}, not {CA_ARTIFACT_KIND!r}; a "
                "BZ capture and a CA study are different documents and are not "
                "interchangeable"
            )
        version = payload.get("schema_version")
        if version != CA_ARTIFACT_SCHEMA_VERSION:
            raise SwingLabError(
                f"this study was written by schema version {version!r}; this "
                f"build reads version {CA_ARTIFACT_SCHEMA_VERSION}. It is NOT "
                "upgraded silently — a reader guessing at an older layout will "
                "eventually mis-read a field and report a number nobody measured"
            )
        for required in ("manifest", "results", "assessments"):
            if required not in payload:
                raise SwingLabError(f"this study has no {required!r} section")
        manifest = payload["manifest"]
        for required in _REQUIRED_MANIFEST + ("content_digest",):
            if required not in manifest:
                raise SwingLabError(
                    f"this study's manifest has no {required!r}; a study that "
                    "cannot say what it was measured under cannot be audited"
                )
        self._payload = payload

    @property
    def payload(self) -> Mapping[str, Any]:
        return self._payload

    @property
    def manifest(self) -> Mapping[str, Any]:
        return self._payload["manifest"]

    @property
    def content_digest(self) -> str:
        return self.manifest["content_digest"]

    @property
    def preregistration_digest(self) -> str:
        return self.manifest["preregistration_digest"]

    @property
    def capture_content_digest(self) -> str:
        return self.manifest["capture_content_digest"]

    @property
    def headline(self) -> str:
        return self._payload.get("headline", "")


def read_admission_study(path: str | Path) -> AdmissionStudyArtifact:
    """Decode a CA study from disk. **No network, at any point, for any reason.**

    Raises:
        SwingLabError: the file is unreadable, is not a CA study, was written by
            another schema version, or is missing a manifest field.
    """
    target = Path(path)
    try:
        raw = target.read_bytes()
    except OSError as error:
        raise SwingLabError(f"cannot read study {target}: {error}") from None
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError) as error:
            raise SwingLabError(
                f"study {target} is gzipped but truncated or corrupt: {error}"
            ) from None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SwingLabError(f"study {target} is not valid JSON: {error}") from None
    if not isinstance(payload, dict):
        raise SwingLabError(f"study {target} is not a JSON object")
    return AdmissionStudyArtifact(payload)


def verify_admission_study_digest(artifact: AdmissionStudyArtifact) -> bool:
    """Recompute the content digest and compare it to the stored one.

    This catches a hand-edited effect, verdict or manifest field. It is a
    **separate** question from whether the study was measured under this build's
    seal; a study can be perfectly intact and still describe a different
    experiment, and merging those two failures would report a foreign experiment
    as a corrupt file.
    """
    if not isinstance(artifact, AdmissionStudyArtifact):
        raise TypeError("artifact must be an AdmissionStudyArtifact")
    return admission_study_digest(artifact.payload) == artifact.content_digest
