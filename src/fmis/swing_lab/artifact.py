"""A completed experiment, frozen to JSON. **Rebuildable, not authoritative.**

A lab artifact is a *record of a measurement*, and this module is careful about
what that does and does not entitle it to:

* it carries the manifest, so a reader can rebuild the run that produced it;
* it carries the result digest, so a rebuild can be **checked** rather than
  assumed — `verify_digest` recomputes it from the trades in the file;
* it carries no market data, so it can never be mistaken for a source of prices;
* it is **not** part of the owner's trading store. Nothing here is a position, a
  decision or an instruction, and no production surface reads it.

**Why a file at all.** The brief asks for reproducible research artifacts and
the dashboard cannot run a fifteen-minute replay behind a page load. A study
that only exists in one process's memory can be neither reviewed nor compared
with the next one. This is a plain JSON document with a schema version, written
where the caller asks and nowhere else.

**Decimals are text, never floats.** A JSON float would silently round every R
multiple on the way out and produce a different digest on the way back in.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fmis.swing_lab.metrics import VariantMetrics, classify, compute_lab_metrics
from fmis.swing_lab.models import (
    LAB_SCHEMA_VERSION,
    LabExitReason,
    LabTrade,
    LabVerdict,
    SwingLabError,
)
from fmis.swing_lab.study import LabStudy, result_digest
from fmis.swing_setup.models import Direction

__all__ = [
    "ARTIFACT_FILENAME_SUFFIX",
    "trade_payload",
    "trade_from_payload",
    "encode_study",
    "write_study",
    "read_artifact",
    "verify_digest",
    "LabArtifact",
]

ARTIFACT_FILENAME_SUFFIX = ".lab.json"


def _text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _instant(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def trade_payload(trade: LabTrade) -> dict[str, Any]:
    return {
        "variant_id": trade.variant_id,
        "symbol": trade.symbol,
        "setup_id": trade.setup_id,
        "direction": trade.direction.value,
        "signal_at": _instant(trade.signal_at),
        "entry_at": _instant(trade.entry_at),
        "entry_price": _text(trade.entry_price),
        "initial_stop": _text(trade.initial_stop),
        "target": _text(trade.target),
        "planned_reference_price": _text(trade.planned_reference_price),
        "exit_at": _instant(trade.exit_at),
        "exit_price": _text(trade.exit_price),
        "exit_reason": trade.exit_reason.value,
        "bars_held": trade.bars_held,
        "gross_r": _text(trade.gross_r),
        "net_r": _text(trade.net_r),
        "mfe_r": _text(trade.mfe_r),
        "mae_r": _text(trade.mae_r),
        "cost_policy_id": trade.cost_policy_id,
        "planned_risk_reward": trade.planned_risk_reward,
        "segment": trade.segment,
        "context_regime_structure": trade.context_regime_structure,
        "context_structural_trend": trade.context_structural_trend,
        "setup_structural_trend": trade.setup_structural_trend,
    }


def trade_from_payload(raw: Mapping[str, Any]) -> LabTrade:
    def decimal(key: str) -> Decimal | None:
        value = raw.get(key)
        return None if value is None else Decimal(value)

    def instant(key: str) -> datetime | None:
        value = raw.get(key)
        return None if value is None else datetime.fromisoformat(value)

    return LabTrade(
        variant_id=raw["variant_id"],
        symbol=raw["symbol"],
        setup_id=raw["setup_id"],
        direction=Direction(raw["direction"]),
        signal_at=instant("signal_at"),
        entry_at=instant("entry_at"),
        entry_price=decimal("entry_price"),
        initial_stop=decimal("initial_stop"),
        target=decimal("target"),
        planned_reference_price=decimal("planned_reference_price"),
        exit_at=instant("exit_at"),
        exit_price=decimal("exit_price"),
        exit_reason=LabExitReason(raw["exit_reason"]),
        bars_held=raw["bars_held"],
        gross_r=decimal("gross_r"),
        net_r=decimal("net_r"),
        mfe_r=decimal("mfe_r"),
        mae_r=decimal("mae_r"),
        cost_policy_id=raw["cost_policy_id"],
        planned_risk_reward=raw["planned_risk_reward"],
        segment=raw["segment"],
        context_regime_structure=raw["context_regime_structure"],
        context_structural_trend=raw["context_structural_trend"],
        setup_structural_trend=raw["setup_structural_trend"],
    )


def encode_study(study: LabStudy) -> dict[str, Any]:
    """One study as a JSON-safe mapping, manifest and trades included.

    Observations are deliberately **not** carried: a four-year, four-symbol
    study holds hundreds of thousands of them, they are rebuildable from the
    manifest, and no surface reads them. What is carried is what a reader
    cannot recompute without the fifteen-minute replay — the trades.
    """
    if not isinstance(study, LabStudy):
        raise TypeError(f"study must be a LabStudy, got {type(study).__name__}")
    gate = study.gate
    return {
        "schema_version": LAB_SCHEMA_VERSION,
        "manifest": study.manifest.to_payload(),
        "variants": [
            {
                "variant_id": result.variant.variant_id,
                "title": result.variant.title,
                "hypothesis": result.variant.hypothesis,
                "policy_id": result.variant.policy_id,
                "is_production_baseline": result.variant.is_production_baseline,
                "timeframes": {
                    role.value: interval
                    for role, interval in result.variant.timeframes.items()
                },
                "trades": [trade_payload(trade) for trade in result.trades],
            }
            for result in study.results
        ],
        "gate": {
            "instants": gate.instants,
            "not_reached": gate.not_reached,
            "allowed": gate.allowed,
            "blocked_without_effect": gate.blocked_without_effect,
            "blocked_candidate": gate.blocked_candidate,
            "blocked_confirmed": gate.blocked_confirmed,
            "blocked_long": gate.blocked_long,
            "blocked_short": gate.blocked_short,
            "baseline_variant_id": gate.baseline_variant_id,
            "counterfactual_variant_id": gate.counterfactual_variant_id,
            "counterfactual_note": gate.counterfactual_note,
        },
    }


def write_study(study: LabStudy, path: str | Path) -> Path:
    """Write one study as a JSON artifact. Refuses to overwrite.

    An experiment id names a measurement, and silently replacing one with a
    later run under the same name is how two different results come to be cited
    as the same evidence.

    Raises:
        SwingLabError: the path already exists.
    """
    target = Path(path)
    if target.exists():
        raise SwingLabError(
            f"{target} already exists; a lab artifact is never overwritten, "
            "because replacing one measurement with another under the same "
            "name makes two different results indistinguishable afterwards"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(encode_study(study), indent=2, sort_keys=True), encoding="utf-8"
    )
    return target


class LabArtifact:
    """A study read back from disk: its manifest, its trades and its metrics.

    Deliberately a thin reader rather than a full `LabStudy`. A study holds the
    replay machinery that produced it; an artifact holds what it concluded.
    Anything needing more must rerun the experiment, which the manifest makes
    possible.
    """

    def __init__(self, payload: Mapping[str, Any]) -> None:
        version = payload.get("schema_version")
        if version != LAB_SCHEMA_VERSION:
            raise SwingLabError(
                f"this artifact is schema version {version!r}; this build reads "
                f"version {LAB_SCHEMA_VERSION}. It is not upgraded silently — a "
                "figure whose meaning changed between versions would be read "
                "under the wrong basis"
            )
        self.payload = payload
        self.manifest: Mapping[str, Any] = payload["manifest"]
        self.gate: Mapping[str, Any] = payload["gate"]
        self.trades_by_variant: dict[str, tuple[LabTrade, ...]] = {
            variant["variant_id"]: tuple(
                trade_from_payload(trade) for trade in variant["trades"]
            )
            for variant in payload["variants"]
        }

    @property
    def experiment_id(self) -> str:
        return self.manifest["experiment_id"]

    @property
    def variant_ids(self) -> tuple[str, ...]:
        return tuple(variant["variant_id"] for variant in self.payload["variants"])

    def variant(self, variant_id: str) -> Mapping[str, Any]:
        for item in self.payload["variants"]:
            if item["variant_id"] == variant_id:
                return item
        raise SwingLabError(f"this artifact holds no variant {variant_id!r}")

    def metrics(self, variant_id: str) -> VariantMetrics:
        return compute_lab_metrics(
            self.trades_by_variant[variant_id], label=variant_id
        )

    def all_metrics(self) -> tuple[VariantMetrics, ...]:
        return tuple(self.metrics(item) for item in self.variant_ids)

    def verdict(self, variant_id: str) -> LabVerdict:
        """The verdict this variant's measured result supports.

        Exposed here so a **presentation layer can read a verdict without
        importing the laboratory** — `fmis.operator_dashboard` is forbidden from
        depending on this package, and calling this duck-typed is what keeps
        that true while still putting a classification on the page. It is
        derived by `classify`, so it is reconstructable rather than asserted.
        """
        return classify(self.metrics(variant_id))


def read_artifact(path: str | Path) -> LabArtifact:
    """Read one artifact from disk.

    Raises:
        SwingLabError: the file is unreadable, not JSON, or a different schema.
    """
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except OSError as error:
        raise SwingLabError(f"cannot read {target}: {error}") from None
    except json.JSONDecodeError as error:
        raise SwingLabError(f"{target} is not valid JSON: {error}") from None
    if not isinstance(payload, Mapping):
        raise SwingLabError(f"{target} does not hold a lab artifact")
    return LabArtifact(payload)


def verify_digest(artifact: LabArtifact) -> bool:
    """Recompute the result digest from the artifact's own trades and compare.

    This is what makes the digest a check rather than a decoration: an artifact
    whose trades were edited after it was written no longer verifies.
    """

    class _Result:
        def __init__(self, trades: tuple[LabTrade, ...]) -> None:
            self.trades = trades

    recomputed = result_digest(
        [_Result(artifact.trades_by_variant[item]) for item in artifact.variant_ids]
    )
    return recomputed == artifact.manifest["result_digest"]
