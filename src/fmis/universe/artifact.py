"""The persisted study. **Layered, because one layer cannot honestly do both jobs.**

Milestone BZ recorded BZ-D2: a study measured against mutable market data is not
reproducible even with frozen code, because a re-run fetches different bars. CC
inherits the lesson and answers it in two layers, which are deliberately separate
files:

**Layer A — the capture.** `fmis.universe.capture.SeriesCache`, holding every
daily series the study read, each with its own SHA-256. It is the raw input,
frozen. An assessment re-run against it with the network made fatal is a pure
function of the file.

**Layer B — this artifact.** The derived feasibility assessment: the funnel, every
eligibility decision with its exclusion reason, the dependence summary, the
density summary, the growth curve, the effect grid, the survivorship reading and
the verdict — plus the *digest of every series it was computed from*. It does not
carry the bars, because 656 instruments' daily history is tens of megabytes and a
reader wanting the arithmetic checked does not need them.

**The claim each layer makes is exactly the one it can support.** Layer B alone
reproduces every number derived from the measurements, and identifies the inputs
cryptographically without holding them. Layer B **plus** layer A reproduces the
study from raw bars offline. Layer B alone does *not* claim offline
reproducibility from raw inputs, and `OFFLINE_CLAIM` says so in the file itself
rather than in a report a future reader may not have.

**The digest covers everything except the slot it is written into.** Milestone BZ's
device, reused: `content_digest` is removed from the manifest before hashing, so a
hand-edited manifest is caught exactly as a hand-edited number is.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from fmis.universe.models import UniverseError, require_text

__all__ = [
    "CC_ARTIFACT_KIND",
    "CC_ARTIFACT_SCHEMA_VERSION",
    "OFFLINE_CLAIM",
    "UniverseArtifact",
    "encode_universe_study",
    "artifact_digest",
    "write_universe_artifact",
    "read_universe_artifact",
    "verify_artifact_digest",
]

CC_ARTIFACT_KIND: Final[str] = "fmits.universe.feasibility"
CC_ARTIFACT_SCHEMA_VERSION: Final[int] = 1

OFFLINE_CLAIM: Final[str] = (
    "This artifact reproduces every DERIVED figure offline: the funnel, the "
    "eligibility decisions, the dependence summary, the density summary, the "
    "growth curve, the effect grid, the survivorship reading and the verdict are "
    "all present. It does NOT carry the raw daily bars, so it cannot re-derive "
    "those figures FROM raw inputs on its own. It identifies every series it was "
    "computed from by SHA-256 in 'series_digests'; pair it with the capture file "
    "holding those series to reproduce the study from bars with the network made "
    "fatal. Market data is mutable at source, so a re-fetch is NOT a reproduction "
    "and this artifact does not claim it is. "
    "ONE INPUT IS NOT FROZEN, and an independent review was right to insist this "
    "be said plainly: the DISCOVERY response is a provider call, not a candle, so "
    "the series capture cannot hold it. An offline reproduction therefore proves "
    "the funnel, the dependence measurement, the growth curve and the verdict are "
    "a deterministic function of a symbol list plus the frozen bars — it does NOT "
    "independently re-establish that the provider listed 3,645 instruments on the "
    "discovery date. That count is recorded here and in the exclusion records, and "
    "is reproducible only against the provider itself."
)


def encode_universe_study(study, *, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Encode a `UniverseStudy` into a JSON-safe payload with its digest attached.

    ``manifest`` carries provenance the study object does not own — when it was
    run, which build produced it, which capture file the series came from. The
    digest is computed over everything and then written into the manifest, so the
    payload is self-verifying.
    """
    payload: dict[str, Any] = {
        "schema_version": CC_ARTIFACT_SCHEMA_VERSION,
        "kind": CC_ARTIFACT_KIND,
        "offline_claim": OFFLINE_CLAIM,
        "manifest": dict(manifest),
        "study": study.payload(),
    }
    payload["manifest"] = {
        **payload["manifest"],
        "content_digest": artifact_digest(payload),
    }
    return payload


def artifact_digest(payload: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical content, **excluding the digest field itself**.

    A digest cannot cover the slot it is written into, so ``content_digest`` is
    removed from the manifest before hashing. Every other field — the
    pre-registration seal, the discovery instant, the window, the verdict — is
    covered.
    """
    manifest = {
        key: value
        for key, value in payload.get("manifest", {}).items()
        if key != "content_digest"
    }
    canonical = json.dumps(
        {
            "schema_version": payload["schema_version"],
            "kind": payload["kind"],
            "offline_claim": payload["offline_claim"],
            "manifest": manifest,
            "study": payload["study"],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_universe_artifact(
    payload: Mapping[str, Any], path: str | Path, *, compress: bool = True
) -> Path:
    """Write the artifact. **Deterministic bytes; refuses to overwrite.**

    Refusing to overwrite is Milestone CA's rule and it is inherited: silently
    replacing a persisted study destroys the record a later disagreement would be
    adjudicated against.
    """
    target = Path(path)
    if compress and target.suffix != ".gz":
        target = target.with_suffix(target.suffix + ".gz")
    if target.exists():
        raise UniverseError(
            f"{target} already exists. A persisted study is a record, and "
            "overwriting one destroys the evidence a later disagreement would be "
            "settled by. Choose another path or move the old file"
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


@dataclass(frozen=True, slots=True)
class UniverseArtifact:
    """A persisted CC study, read back."""

    payload: dict[str, Any]

    @property
    def manifest(self) -> dict[str, Any]:
        return dict(self.payload["manifest"])

    @property
    def study(self) -> dict[str, Any]:
        return dict(self.payload["study"])

    @property
    def content_digest(self) -> str:
        return str(self.manifest["content_digest"])

    @property
    def preregistration_digest(self) -> str:
        return str(self.study["preregistration_digest"])

    @property
    def verdict(self) -> str:
        return str(self.study["assessment"]["verdict"])


def read_universe_artifact(path: str | Path) -> UniverseArtifact:
    """Load a persisted artifact, refusing a schema or kind this build cannot read."""
    source = Path(path)
    raw = source.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise UniverseError(f"{source}: an artifact must be a JSON object")
    if payload.get("kind") != CC_ARTIFACT_KIND:
        raise UniverseError(
            f"{source}: kind {payload.get('kind')!r}; this reader accepts only "
            f"{CC_ARTIFACT_KIND!r}. A capture and a study are different files and "
            "must not be read as each other"
        )
    if payload.get("schema_version") != CC_ARTIFACT_SCHEMA_VERSION:
        raise UniverseError(
            f"{source}: schema version {payload.get('schema_version')!r}; this "
            f"build reads version {CC_ARTIFACT_SCHEMA_VERSION}. It is NOT read on "
            "a guess"
        )
    for field in ("manifest", "study", "offline_claim"):
        if field not in payload:
            raise UniverseError(f"{source}: artifact carries no {field!r}")
    require_text(payload["offline_claim"], "offline_claim")
    return UniverseArtifact(payload=payload)


def verify_artifact_digest(artifact: UniverseArtifact) -> bool:
    """Whether the artifact's contents still hash to the digest it carries."""
    if not isinstance(artifact, UniverseArtifact):
        raise TypeError("artifact must be a UniverseArtifact")
    return artifact_digest(artifact.payload) == artifact.content_digest
