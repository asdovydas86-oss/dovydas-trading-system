"""Persisting a geometry study. **The only module here that touches a file.**

Follows `fmis.swing_lab.artifact`'s rules exactly, for its reasons:

* **an artifact is never overwritten** — replacing one measurement with a later
  one under the same experiment id makes two different results indistinguishable
  afterwards;
* **the schema version is checked, never upgraded silently** — a figure whose
  basis changed between versions would be read under the wrong one;
* **only what a reader cannot recompute is carried.** Candidates and plans are
  rebuildable from the manifest by rerunning the replay; trades, verdicts and
  the criteria that produced them are what the eleven-minute replay bought, and
  those are stored.

The reader is deliberately thin. It answers *what did this study conclude*, and
a caller needing more must rerun the experiment — which the manifest makes
possible.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fmis.swing_lab.artifact import trade_from_payload, trade_payload
from fmis.swing_lab.geometry_study import (
    GEOMETRY_SCHEMA_VERSION,
    GeometryStudy,
    canonical_trade,
)
from fmis.swing_lab.metrics import VariantMetrics, compute_lab_metrics
from fmis.swing_lab.models import LabTrade, SwingLabError

__all__ = [
    "encode_geometry_study",
    "write_geometry_study",
    "GeometryArtifact",
    "read_geometry_artifact",
    "verify_geometry_digest",
]


def _distribution_payload(item: Any) -> dict[str, Any]:
    return {
        "label": item.label, "n": item.n, "minimum": item.minimum,
        "p25": item.p25, "median": item.median, "p75": item.p75,
        "maximum": item.maximum, "mean": item.mean,
    }


def _share_payload(item: Any) -> dict[str, Any]:
    """One share, with the ENGINE's own canonical text carried beside the counts.

    `Share.text` is the only place this repository formats a share, exactly as
    `Money.text` is for money. Carrying the raw `Decimal` alone would leave every
    surface to round it, and a page rounding `0.5294117647058823529411764706`
    itself is a page doing arithmetic on an engine value.
    """
    fraction = item.fraction
    return {
        "numerator": item.numerator,
        "denominator": item.denominator,
        "fraction": None if fraction is None else str(fraction),
        "text": item.text,
    }


def _diagnosis_payload(diagnosis: Any) -> dict[str, Any]:
    return {
        "label": diagnosis.label,
        "distributions": [
            _distribution_payload(item) for item in diagnosis.distributions
        ],
        "reward_below_risk": _share_payload(diagnosis.reward_below_risk),
        "target_exits_below_one_r": _share_payload(diagnosis.target_exits_below_one_r),
        "stops_inside_one_atr": _share_payload(diagnosis.stops_inside_one_atr),
        "mfe_exceeds_realized_by_one_r": _share_payload(
            diagnosis.mfe_exceeds_realized_by_one_r
        ),
        "stopped_then_reached_target": _share_payload(
            diagnosis.stopped_then_reached_target
        ),
        "skip_reasons": [list(item) for item in diagnosis.skip_reasons],
        "findings": [
            {
                "question": item.question,
                "supported": item.supported,
                "evidence": item.evidence,
                "reading": item.reading,
            }
            for item in diagnosis.findings
        ],
    }


def _sample_payload(sample: Any) -> dict[str, Any]:
    share = sample.largest_symbol_share
    return {
        "sample": sample.sample,
        "trades": [trade_payload(trade) for trade in sample.trades],
        "admitted": sample.outcome.admitted,
        "refused": sample.outcome.refused,
        "largest_symbol_share": None if share is None else str(share),
        "diagnosis": _diagnosis_payload(sample.diagnosis),
    }


def encode_geometry_study(study: GeometryStudy) -> dict[str, Any]:
    """One geometry study as a JSON-safe mapping. **Everything a verdict rests on.**

    The criteria are stored individually rather than only their conclusion, so a
    reader can check the verdict against the measurements that produced it
    instead of taking a report's word for it.
    """
    if not isinstance(study, GeometryStudy):
        raise TypeError(f"study must be a GeometryStudy, got {type(study).__name__}")
    return {
        "schema_version": GEOMETRY_SCHEMA_VERSION,
        "manifest": study.manifest.to_payload(),
        "policies": [
            {
                "policy_id": result.policy.policy_id,
                "title": result.policy.title,
                "family": result.policy.family,
                "hypothesis": result.policy.hypothesis,
                "stop_rule": result.policy.stop_rule.value,
                "target_rule": result.policy.target_rule.value,
                "min_planned_rr": result.policy.min_planned_rr,
                "min_stop_atr": result.policy.min_stop_atr,
                "volatility_source": result.policy.volatility_source.value,
                "is_production_geometry": result.policy.is_production_geometry,
                "verdict": result.assessment.verdict.value,
                "verdict_statement": result.assessment.statement,
                "criteria": [
                    {
                        "name": item.name,
                        "requirement": item.requirement,
                        "passed": item.passed,
                        "observed": item.observed,
                    }
                    for item in result.assessment.criteria
                ],
                "development": _sample_payload(result.development),
                "holdout": _sample_payload(result.holdout),
            }
            for result in study.results
        ],
        "sensitivity": [
            {
                "kind": curve.kind,
                "is_plateau": curve.is_plateau,
                "points": [
                    {
                        "threshold": point.threshold,
                        "policy_id": point.policy_id,
                        "development_trades": point.development.measurable_trades,
                        "development_expectancy_r": (
                            None
                            if point.development.expectancy_r.value is None
                            else str(point.development.expectancy_r.value)
                        ),
                        "holdout_trades": point.holdout.measurable_trades,
                        "holdout_expectancy_r": (
                            None
                            if point.holdout.expectancy_r.value is None
                            else str(point.holdout.expectancy_r.value)
                        ),
                    }
                    for point in curve.points
                ],
            }
            for curve in study.sensitivity
        ],
    }


def write_geometry_study(study: GeometryStudy, path: str | Path) -> Path:
    """Write one geometry study as a JSON artifact. Refuses to overwrite.

    Raises:
        SwingLabError: the path already exists.
    """
    target = Path(path)
    if target.exists():
        raise SwingLabError(
            f"{target} already exists; a geometry artifact is never overwritten, "
            "because replacing one measurement with another under the same name "
            "makes two different results indistinguishable afterwards"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(encode_geometry_study(study), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


class GeometryArtifact:
    """A geometry study read back from disk: what it measured and what it concluded."""

    def __init__(self, payload: Mapping[str, Any]) -> None:
        version = payload.get("schema_version")
        if version != GEOMETRY_SCHEMA_VERSION:
            raise SwingLabError(
                f"this artifact is schema version {version!r}; this build reads "
                f"version {GEOMETRY_SCHEMA_VERSION}. It is not upgraded silently "
                "— a figure whose meaning changed between versions would be read "
                "under the wrong basis"
            )
        self.payload = payload
        self.manifest: Mapping[str, Any] = payload["manifest"]

    @property
    def experiment_id(self) -> str:
        return self.manifest["experiment_id"]

    @property
    def policy_ids(self) -> tuple[str, ...]:
        return tuple(item["policy_id"] for item in self.payload["policies"])

    def policy(self, policy_id: str) -> Mapping[str, Any]:
        for item in self.payload["policies"]:
            if item["policy_id"] == policy_id:
                return item
        raise SwingLabError(
            f"this artifact holds no geometry {policy_id!r}; it holds "
            f"{', '.join(self.policy_ids)}"
        )

    def trades(self, policy_id: str, sample: str) -> tuple[LabTrade, ...]:
        entry = self.policy(policy_id)
        if sample not in ("development", "holdout"):
            raise SwingLabError(
                f"sample must be 'development' or 'holdout', got {sample!r}"
            )
        return tuple(trade_from_payload(item) for item in entry[sample]["trades"])

    def metrics(self, policy_id: str, sample: str) -> VariantMetrics:
        return compute_lab_metrics(
            self.trades(policy_id, sample), label=f"{policy_id}:{sample}"
        )

    @property
    def candidate_policy_ids(self) -> tuple[str, ...]:
        """Every policy the study judged worth forward testing. Usually empty."""
        return tuple(
            item["policy_id"]
            for item in self.payload["policies"]
            if item["verdict"] == "candidate_for_forward_test"
        )

    @property
    def is_approved_for_trading(self) -> bool:
        """Always ``False``. No artifact this repository writes approves trading."""
        return False


def read_geometry_artifact(path: str | Path) -> GeometryArtifact:
    """Read one geometry artifact from disk.

    Raises:
        SwingLabError: the file is unreadable, not JSON, or a different schema.
    """
    target = Path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as error:
        raise SwingLabError(f"cannot read {target}: {error}") from None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SwingLabError(f"{target} is not valid JSON: {error}") from None
    if not isinstance(payload, Mapping):
        raise SwingLabError(f"{target} does not hold a geometry artifact object")
    return GeometryArtifact(payload)


def verify_geometry_digest(artifact: GeometryArtifact) -> bool:
    """Recompute the digest from the stored trades and compare it to the manifest.

    This is what makes an artifact **checkable** rather than merely readable: a
    hand-edited trade, a truncated file or a figure copied from another run
    fails here rather than being quoted as evidence.
    """
    rows = sorted(
        (
            canonical_trade(trade)
            for policy_id in artifact.policy_ids
            for sample in ("development", "holdout")
            for trade in artifact.trades(policy_id, sample)
        ),
        key=lambda row: (row[0], row[1], row[4], row[2]),
    )
    payload = json.dumps(rows, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest() == artifact.manifest[
        "result_digest"
    ]
