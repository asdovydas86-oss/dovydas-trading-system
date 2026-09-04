"""Persisting Milestone CD, so a later disagreement is a diff rather than an argument.

Milestone CD exists because a file was not kept. Milestone BZ's capture — the
inputs every BZ and CA figure was measured from — was produced by an ad-hoc
runner and never written into `reports/artifacts/`, so when Milestone CB needed
CA's observations it had to reason from published summary statistics (limitation
CB-1) and when Milestone CC needed the paired effects' dependence it had to
substitute a price-return proxy that could not answer the question (CC-1, and
then CC-7 when the proxy was shown to be structurally uninformative).

**So this artifact persists the observations, not only the conclusions.** Every
paired difference, with the admission that produced it, the economic asset it
belongs to, the control mean it was taken against and the capture digest it was
measured over. That is what makes `study_from_rows` a real reproduction path and
not a claim.

**Four digests, answering four different questions.**

    preregistration_digest        did the RULES change?
    capture_content_digest        did the DATA change?
    ca_preregistration_digest     was CA's seal the same one?
    content_digest                was THIS FILE edited?

Two runs that disagree can be attributed rather than argued about, and a file
whose content digest fails is refused outright — nothing is recomputed to fill a
gap, because a reader that re-measures a missing field has silently turned an
audit back into a run.

**The digest is taken over canonical JSON, never over the file.** gzip writes the
current time and the file object's name into its header, so two byte-identical
studies would otherwise produce two different digests.
`fmis.swing_lab.persistence_artifact` reached this conclusion first and this is
the same rule, deliberately.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from fmis.paired_dependence.models import PairedDependenceError
from fmis.paired_dependence.observations import ObservationRow
from fmis.paired_dependence.preregistration import (
    CD_PREREGISTRATION_DIGEST,
    CD_PREREGISTRATION_ID,
)
from fmis.paired_dependence.study import CD_SCHEMA_VERSION

__all__ = [
    "CD_ARTIFACT_KIND",
    "CD_ARTIFACT_SCHEMA_VERSION",
    "PairedDependenceArtifact",
    "encode_dependence_study",
    "dependence_study_digest",
    "write_dependence_study",
    "read_dependence_study",
    "verify_dependence_study_digest",
    "dependence_rows_of",
]

#: What this file is. Carried so a reader handed a BZ capture, a CA study or a CC
#: universe artifact refuses it by name rather than failing on a missing key
#: three levels down.
CD_ARTIFACT_KIND: Final[str] = "cd-paired-effect-dependence"

CD_ARTIFACT_SCHEMA_VERSION: Final[int] = CD_SCHEMA_VERSION

_REQUIRED_MANIFEST: Final[tuple[str, ...]] = (
    "preregistration_id",
    "preregistration_digest",
    "capture_content_digest",
    "capture_preregistration_digest",
    "ca_preregistration_digest",
    "run_at",
    "primary_horizon",
    "primary_family",
    "primary_sample",
    "primary_block_bars",
    "bootstrap_draws",
    "bootstrap_confidence",
    "master_seed",
    "universe_for_sample",
)

_REQUIRED_SECTIONS: Final[tuple[str, ...]] = (
    "manifest",
    "observations",
    "panels",
    "calibration",
    "requirement",
    "cc_comparison",
    "assessment",
    "reconstruction",
    "preregistration",
)

#: Every field an observation must carry to be auditable offline. A row missing
#: one of these cannot be traced back to the admission that produced it, and a
#: dataset of untraceable rows is a table of numbers rather than evidence.
_REQUIRED_OBSERVATION_FIELDS: Final[tuple[str, ...]] = (
    "observation_id",
    "family_id",
    "sample",
    "universe",
    "symbol",
    "base_asset",
    "economic_asset",
    "bar_index",
    "as_of",
    "direction",
    "horizon",
    "segment",
    "volatility",
    "pool_size",
    "radius_tier",
    "control_draws",
    "admission_forward",
    "control_forward",
    "difference",
    "capture_content_digest",
    "capture_captured_at",
)


def dependence_study_digest(payload: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical content, **excluding the digest field itself**.

    The digest cannot cover the slot it is written into, so `manifest` is
    digested with `content_digest` removed. Every other field — the four other
    digests, every observation, every panel, every sensitivity cell, every
    control reading and the verdict — **is** covered, so a hand-edited
    correlation is caught exactly as a hand-edited manifest is.
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


def encode_dependence_study(study, *, writer: str) -> dict[str, Any]:
    """Encode one `PairedDependenceStudy` into a JSON-safe payload with its digest."""
    payload: dict[str, Any] = {
        "schema_version": CD_ARTIFACT_SCHEMA_VERSION,
        "kind": CD_ARTIFACT_KIND,
        **study.payload(),
    }
    payload["manifest"] = {**dict(payload.get("manifest", {})), "writer": writer}
    payload["manifest"]["content_digest"] = dependence_study_digest(payload)
    return payload


def write_dependence_study(
    payload: Mapping[str, Any], path: str | Path, *, compress: bool = True
) -> Path:
    """Write the study. **Gzip is made deterministic, deliberately.**

    ``mtime=0`` and ``filename=""`` keep the *file* reproducible too, and the
    digest is still taken over the canonical JSON so a reader never depends on it.

    Raises:
        PairedDependenceError: the target already exists. A research artifact is
            never overwritten — Milestone CC lost one that way and recorded the
            incident rather than absorbing it.
    """
    target = Path(path)
    if compress and target.suffix != ".gz":
        target = target.with_suffix(target.suffix + ".gz")
    if target.exists():
        raise PairedDependenceError(
            f"{target} already exists; a research artifact is never overwritten. "
            "Move or rename the existing file and record the lineage"
        )
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if compress:
        with open(target, "wb") as raw:
            with gzip.GzipFile(
                filename="", fileobj=raw, mode="wb", compresslevel=6, mtime=0
            ) as stream:
                stream.write(canonical)
    else:
        target.write_bytes(canonical)
    return target


class PairedDependenceArtifact:
    """A decoded CD study. **Refuses anything it cannot fully account for.**"""

    __slots__ = ("_payload",)

    def __init__(self, payload: Mapping[str, Any]) -> None:
        kind = payload.get("kind")
        if kind != CD_ARTIFACT_KIND:
            raise PairedDependenceError(
                f"this file declares kind {kind!r}, not {CD_ARTIFACT_KIND!r}; a "
                "BZ capture, a CA study, a CC universe artifact and a CD "
                "dependence study are different documents and are not "
                "interchangeable"
            )
        version = payload.get("schema_version")
        if version != CD_ARTIFACT_SCHEMA_VERSION:
            raise PairedDependenceError(
                f"this study was written by schema version {version!r}; this "
                f"build reads version {CD_ARTIFACT_SCHEMA_VERSION}. It is NOT "
                "upgraded silently — a reader guessing at an older layout will "
                "eventually mis-read a field and report a number nobody measured"
            )
        for required in _REQUIRED_SECTIONS:
            if required not in payload:
                raise PairedDependenceError(f"this study has no {required!r} section")
        manifest = payload["manifest"]
        for required in _REQUIRED_MANIFEST + ("content_digest",):
            if required not in manifest:
                raise PairedDependenceError(
                    f"this study's manifest has no {required!r}; a study that "
                    "cannot say what it was measured under cannot be audited"
                )
        observations = payload["observations"]
        if not isinstance(observations, list) or not observations:
            raise PairedDependenceError(
                "this study holds no observations. Milestone CD exists to persist "
                "them; a CD artifact without them is a summary wearing the wrong "
                "kind"
            )
        for position, row in enumerate(observations):
            missing = [
                field for field in _REQUIRED_OBSERVATION_FIELDS if field not in row
            ]
            if missing:
                raise PairedDependenceError(
                    f"observation {position} is missing {', '.join(missing)}; a "
                    "row that cannot be traced back to its admission is not "
                    "evidence"
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
    def verdict(self) -> str:
        return self._payload["assessment"]["verdict"]

    def require_seal(self) -> None:
        """Refuse a study measured under a different pre-registration.

        **Separate from the digest check, deliberately.** A study can be perfectly
        intact and still describe a different experiment, and merging those two
        failures would report a foreign experiment as a corrupt file.

        Raises:
            PairedDependenceError: the seal or its id does not match this build.
        """
        if self.manifest["preregistration_id"] != CD_PREREGISTRATION_ID:
            raise PairedDependenceError(
                f"this study was measured under pre-registration "
                f"{self.manifest['preregistration_id']!r}, not "
                f"{CD_PREREGISTRATION_ID!r}"
            )
        if self.preregistration_digest != CD_PREREGISTRATION_DIGEST:
            raise PairedDependenceError(
                f"this study was measured under seal {self.preregistration_digest}, "
                f"and this build seals {CD_PREREGISTRATION_DIGEST}. The file is "
                "intact; it describes a different Milestone CD design"
            )

    def require_source(self, capture_content_digest: str) -> None:
        """Refuse a study whose source capture is not the one named.

        Raises:
            PairedDependenceError: the capture identity does not match.
        """
        if self.capture_content_digest != capture_content_digest:
            raise PairedDependenceError(
                f"this study was measured over capture "
                f"{self.capture_content_digest}, not {capture_content_digest}. "
                "Two studies over two datasets are not comparable and are not "
                "reconciled here"
            )


def read_dependence_study(path: str | Path) -> PairedDependenceArtifact:
    """Decode a CD study from disk. **No network, at any point, for any reason.**

    Raises:
        PairedDependenceError: the file is unreadable, is not a CD study, was
            written by another schema version, or is missing required provenance.
    """
    target = Path(path)
    try:
        raw = target.read_bytes()
    except OSError as error:
        raise PairedDependenceError(f"cannot read study {target}: {error}") from None
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError) as error:
            raise PairedDependenceError(
                f"study {target} is gzipped but truncated or corrupt: {error}"
            ) from None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PairedDependenceError(f"study {target} is not valid JSON: {error}") from None
    if not isinstance(payload, dict):
        raise PairedDependenceError(f"study {target} is not a JSON object")
    return PairedDependenceArtifact(payload)


def verify_dependence_study_digest(artifact: PairedDependenceArtifact) -> bool:
    """Recompute the content digest and compare it to the stored one."""
    if not isinstance(artifact, PairedDependenceArtifact):
        raise TypeError("artifact must be a PairedDependenceArtifact")
    return dependence_study_digest(artifact.payload) == artifact.content_digest


def dependence_rows_of(artifact: PairedDependenceArtifact) -> tuple[ObservationRow, ...]:
    """Rebuild every observation from a decoded artifact.

    Each row is reconstructed through `ObservationRow`, whose own invariant
    re-checks that the stored difference is still the arithmetic of its parts —
    so a hand-edited paired difference is refused here even before the content
    digest is consulted.
    """
    if not isinstance(artifact, PairedDependenceArtifact):
        raise TypeError("artifact must be a PairedDependenceArtifact")
    return tuple(
        ObservationRow.from_payload(row) for row in artifact.payload["observations"]
    )
