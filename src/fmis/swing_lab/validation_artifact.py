"""Persisting a validation study. **The only module here that touches a file.**

Follows `fmis.swing_lab.geometry_artifact`'s rules exactly, for its reasons — an
artifact is never overwritten, the schema version is checked and never upgraded
silently, and only what a reader cannot recompute is stored — and adds one of its
own that Milestone BY needs:

> **The pre-registration digest travels inside the artifact.** A result read back
> under a *different* pre-registration is a result about a different experiment,
> and `verify_preregistration_seal` says so. A study whose seal no longer matches
> the live module is still readable — the numbers are what they were — but every
> surface prints the mismatch, because the criteria those numbers were judged
> against are no longer the criteria in the repository.

Two digests, therefore, and they answer different questions:

* `verify_result_digest` — *were these numbers edited?* Recomputed from the
  stored trades, so a hand-changed R, a truncated file or a figure pasted from
  another run fails here rather than being quoted as evidence.
* `verify_preregistration_seal` — *were these numbers judged against the rules
  that are in the repository now?*
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fmis.swing_lab.artifact import trade_from_payload, trade_payload
from fmis.swing_lab.geometry_study import canonical_trade
from fmis.swing_lab.metrics import VariantMetrics, compute_lab_metrics
from fmis.swing_lab.models import LabTrade, SwingLabError
from fmis.swing_lab.preregistration import verify_preregistration
from fmis.swing_lab.trades import FRICTIONLESS_COSTS
from fmis.swing_lab.validation_study import VALIDATION_SCHEMA_VERSION, ValidationStudy

__all__ = [
    "encode_validation_study",
    "write_validation_study",
    "ValidationArtifact",
    "read_validation_artifact",
    "verify_result_digest",
    "verify_preregistration_seal",
]


def _metrics_payload(metrics: VariantMetrics) -> dict[str, Any]:
    def measure(item: Any) -> dict[str, Any]:
        return {
            "value": None if item.value is None else str(item.value),
            "n": item.n,
            "reason": item.reason,
        }

    return {
        "label": metrics.label,
        "trades": metrics.trades,
        "measurable_trades": metrics.measurable_trades,
        "ambiguous_trades": metrics.ambiguous_trades,
        "unentered_trades": metrics.unentered_trades,
        "wins": metrics.wins,
        "losses": metrics.losses,
        "scratches": metrics.scratches,
        "win_rate": measure(metrics.win_rate),
        "expectancy_r": measure(metrics.expectancy_r),
        "median_r": measure(metrics.median_r),
        "profit_factor": measure(metrics.profit_factor),
        "average_win_r": measure(metrics.average_win_r),
        "average_loss_r": measure(metrics.average_loss_r),
        "total_r": str(metrics.total_r),
        "max_drawdown_r": str(metrics.max_drawdown.max_drawdown_r),
        "exit_reasons": [list(item) for item in metrics.exit_reasons],
    }


def _measurement_payload(measurement: Any) -> dict[str, Any]:
    share = measurement.largest_symbol_share
    return {
        "sample": measurement.sample,
        "cost_policy_id": measurement.cost_policy_id,
        "admitted": measurement.admitted,
        "refused": measurement.refused,
        "skip_reasons": [list(item) for item in measurement.skip_reasons],
        "largest_symbol_share": None if share is None else str(share),
        "metrics": _metrics_payload(measurement.metrics),
        # Trades are stored ONCE, on the frictionless scenario, and re-priced on
        # read. Storing them per scenario would triple the artifact to carry
        # three copies of the same path, and would let the copies drift. The
        # geometry records travel with them for the same reason.
        "trades": (
            [trade_payload(trade) for trade in measurement.trades]
            if measurement.cost_policy_id == FRICTIONLESS_COSTS.policy_id
            else []
        ),
        "geometry": (
            [dict(item) for item in measurement.geometry]
            if measurement.cost_policy_id == FRICTIONLESS_COSTS.policy_id
            else []
        ),
    }


def _decomposition_payload(item: Any) -> dict[str, Any]:
    return {
        "name": item.name,
        "question": item.question,
        "agrees_on_sign": item.agrees_on_sign,
        "cohorts": [_metrics_payload(cohort) for cohort in item.cohorts],
    }


def encode_validation_study(study: ValidationStudy) -> dict[str, Any]:
    """One validation study as a JSON-safe mapping. **Everything a verdict rests on.**

    The criteria are stored individually rather than only their conclusion, so a
    reader can check the verdict against the measurements that produced it
    instead of taking a report's word for it.
    """
    if not isinstance(study, ValidationStudy):
        raise TypeError(
            f"study must be a ValidationStudy, got {type(study).__name__}"
        )
    return {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "manifest": study.manifest.to_payload(),
        "walk_forward_policy_id": study.walk_forward_policy_id,
        "policies": [
            {
                **item.hypothesis.payload(),
                "assessment": item.assessment.payload(),
                "measurements": [
                    _measurement_payload(cell) for cell in item.measurements
                ],
            }
            for item in study.policies
        ],
        "walk_forward": [window.payload() for window in study.walk_forward],
        "holdout_walk_forward": [
            window.payload() for window in study.holdout_walk_forward
        ],
        "decompositions": [
            _decomposition_payload(item) for item in study.decompositions
        ],
        "holdout_decompositions": [
            _decomposition_payload(item) for item in study.holdout_decompositions
        ],
    }


def write_validation_study(study: ValidationStudy, path: str | Path) -> Path:
    """Write one validation study as a JSON artifact. Refuses to overwrite.

    Raises:
        SwingLabError: the path already exists.
    """
    target = Path(path)
    if target.exists():
        raise SwingLabError(
            f"{target} already exists; a validation artifact is never "
            "overwritten, because replacing one measurement with another under "
            "the same name makes two different results indistinguishable "
            "afterwards"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(encode_validation_study(study), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


class ValidationArtifact:
    """A validation study read back from disk: what it measured and what it concluded."""

    def __init__(self, payload: Mapping[str, Any]) -> None:
        version = payload.get("schema_version")
        if version != VALIDATION_SCHEMA_VERSION:
            raise SwingLabError(
                f"this artifact is schema version {version!r}; this build reads "
                f"version {VALIDATION_SCHEMA_VERSION}. It is not upgraded "
                "silently — a figure whose meaning changed between versions "
                "would be read under the wrong basis"
            )
        self.payload = payload
        self.manifest: Mapping[str, Any] = payload["manifest"]

    @property
    def experiment_id(self) -> str:
        return self.manifest["experiment_id"]

    @property
    def preregistration_digest(self) -> str:
        return self.manifest["preregistration_digest"]

    @property
    def policy_ids(self) -> tuple[str, ...]:
        return tuple(item["policy_id"] for item in self.payload["policies"])

    @property
    def sample_names(self) -> tuple[str, ...]:
        return tuple(item["name"] for item in self.manifest["samples"])

    @property
    def deciding_cost_policy_id(self) -> str:
        return self.manifest["deciding_cost_policy_id"]

    def policy(self, policy_id: str) -> Mapping[str, Any]:
        for item in self.payload["policies"]:
            if item["policy_id"] == policy_id:
                return item
        raise SwingLabError(
            f"this artifact holds no policy {policy_id!r}; it holds "
            f"{', '.join(self.policy_ids)}"
        )

    def measurement(
        self, policy_id: str, sample: str, cost_policy_id: str
    ) -> Mapping[str, Any]:
        for item in self.policy(policy_id)["measurements"]:
            if item["sample"] == sample and item["cost_policy_id"] == cost_policy_id:
                return item
        raise SwingLabError(
            f"{policy_id} holds no measurement of {sample!r} under "
            f"{cost_policy_id!r}"
        )

    def trades(self, policy_id: str, sample: str) -> tuple[LabTrade, ...]:
        """The stored frictionless trades. **The path, which no cost scenario changes.**"""
        measurement = self.measurement(
            policy_id, sample, FRICTIONLESS_COSTS.policy_id
        )
        return tuple(trade_from_payload(item) for item in measurement["trades"])

    def geometry(self, policy_id: str, sample: str) -> tuple[Mapping[str, Any], ...]:
        """Each trade's plan provenance. **The chart seam.**

        Positionally aligned with `trades`, so a caller drawing a historical
        trade gets its symbol, its signal bar index, both structural levels with
        the timeframe and swing label that produced them, and the ATR the
        distances were normalised by — without re-running an hour-long replay.
        """
        measurement = self.measurement(
            policy_id, sample, FRICTIONLESS_COSTS.policy_id
        )
        return tuple(measurement["geometry"])

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
            if item["assessment"]["verdict"] == "candidate_for_forward_test"
        )

    @property
    def is_approved_for_trading(self) -> bool:
        """Always ``False``. No artifact this repository writes approves trading."""
        return False


def read_validation_artifact(path: str | Path) -> ValidationArtifact:
    """Read one validation artifact from disk.

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
        raise SwingLabError(f"{target} does not hold a validation artifact object")
    return ValidationArtifact(payload)


def verify_result_digest(artifact: ValidationArtifact) -> bool:
    """Recompute the digest from the stored trades and compare it to the manifest.

    This is what makes an artifact **checkable** rather than merely readable. The
    recomputation walks the same (policy, sample, scenario) product the study
    digested, re-pricing the stored frictionless path into each *costed* scenario
    exactly as the study did.

    **The frictionless row is used as stored, not re-priced**, and that is
    load-bearing rather than an optimisation. `reprice` recomputes ``net_r`` from
    the entry and exit prices, so re-pricing a frictionless trade *into*
    frictionless would silently repair a hand-edited ``net_r`` and the digest
    would pass over a doctored file. Taking the stored row verbatim puts every
    persisted field back inside the digest's coverage. The two are arithmetically
    identical on an honest artifact — a frictionless re-price is the identity —
    which is why the check stays exact.
    """
    from fmis.swing_lab.preregistration import VALIDATION_COST_SCENARIOS
    from fmis.swing_lab.trades import reprice

    # The scenarios the STUDY measured, read off the manifest — not the module
    # constant. `run_validation_study` takes `cost_scenarios` as a parameter, so
    # a study run with a different list would write an artifact whose digest
    # could never verify, and the dashboard would report an honest file as
    # NOT VERIFIED.
    known = {item.policy_id: item for item in VALIDATION_COST_SCENARIOS}
    measured = []
    for policy_id in artifact.manifest["cost_policy_ids"]:
        if policy_id not in known:
            raise SwingLabError(
                f"this artifact was measured under cost scenario {policy_id!r}, "
                "which this build does not define; its digest cannot be "
                "recomputed and must not be reported as unverified"
            )
        measured.append(known[policy_id])

    rows = sorted(
        (
            canonical_trade(
                trade if costs.is_frictionless else reprice(trade, costs)
            )
            for policy_id in artifact.policy_ids
            for sample in artifact.sample_names
            for costs in measured
            for trade in _stored(artifact, policy_id, sample)
        ),
        key=lambda row: (row[0], row[16], row[1], row[4], row[2]),
    )
    payload = json.dumps(rows, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return digest == artifact.manifest["result_digest"]


def _stored(artifact: ValidationArtifact, policy_id: str, sample: str) -> tuple[LabTrade, ...]:
    try:
        return artifact.trades(policy_id, sample)
    except SwingLabError:
        # A sample this policy was never measured on — the holdout of a
        # development-only pass. Absent, not empty-because-it-lost.
        return ()


def verify_preregistration_seal(artifact: ValidationArtifact) -> bool:
    """Whether this result was judged against the pre-registration in the repository.

    ``False`` does not mean the numbers are wrong. It means the **rules** moved
    after they were measured, which is exactly the situation a reader must be
    told about rather than left to infer from two files' modification times.
    """
    return verify_preregistration(artifact.preregistration_digest)
