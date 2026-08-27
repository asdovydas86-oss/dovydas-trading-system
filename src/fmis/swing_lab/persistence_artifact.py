"""Persisting Milestone BZ's **capture**, so the experiment is reproducible offline.

Every artifact this repository wrote before BZ persists a **result**: `artifact.py`
(BW), `geometry_artifact.py` (BX) and `validation_artifact.py` (BY) all encode a
finished study. None persists the *inputs* a study was computed from, and that
omission has a cost this milestone paid directly:

> Milestone BZ measured BY's own primary geometry at **+0.1906R** where BY's
> report says **+0.1995R**. The difference was traced to a single `TIME_STOP`
> trade worth 1.21R — and could not be closed, because BY stored no capture and
> the two runs cannot be diffed. Defect **BZ-D2**.

This module is the answer to that. It persists what a replay *produced* —
candidates, bars and the structural timeline — so a later run can re-measure the
identical inputs **without touching the network**, and so two runs can be
compared field by field rather than inferred from their totals.

**What "reproducible" means here, precisely.** Market data is mutable: a provider
extends its series every four hours and may revise a candle. A study that
refetches is therefore not reproducible even when its code is frozen. An artifact
written by this module fixes the inputs, so re-running BZ over it is a pure
function of the file and the code — and any later disagreement is a code change,
never a data change.

**Three ways this fails closed, and it never fails open.**

1. **Schema.** A version this build does not define is refused, never upgraded
   silently. A reader that guesses at an older layout is a reader that will
   eventually mis-read one field and report a number nobody measured.
2. **Digest.** The content digest is recomputed from the decoded payload and
   compared. A hand-edited bar, candidate or observation is caught.
3. **Completeness.** A candidate naming a symbol whose bars are absent, an
   observation whose bar index has no bar, a timeline for a symbol not in the
   capture — each is refused by name. **Nothing is refetched to fill a gap**,
   because a reader that reaches the network has silently turned an offline
   reproduction back into a live one.

**The digest is over canonical JSON, not over the file.** The file may be gzipped
— a BZ capture is hundreds of thousands of bars — and gzip embeds a modification
time that would make two identical captures digest differently. Digesting the
canonical JSON instead makes the digest a property of the *content*, which is
what a reproducibility claim needs.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

from fmis.level_crossing import LevelSide
from fmis.paper.models import PriceBar
from fmis.swing_lab.geometry import GeometryCandidate, LevelRef
from fmis.swing_lab.geometry_replay import GeometryCapture
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.persistence import ThesisObservation, ThesisTimeline
from fmis.swing_setup.models import Direction

__all__ = [
    "BZ_CAPTURE_SCHEMA_VERSION",
    "BZ_CAPTURE_KIND",
    "CapturedUniverse",
    "PersistenceCaptureArtifact",
    "encode_capture",
    "capture_digest",
    "write_persistence_capture",
    "read_persistence_capture",
    "verify_capture_digest",
]

#: Bumped whenever this layout changes. **Never upgraded silently on read.**
BZ_CAPTURE_SCHEMA_VERSION: Final[int] = 1

#: What this file is. Carried so a reader handed a *study* artifact refuses it by
#: name rather than failing on a missing key three levels down.
BZ_CAPTURE_KIND: Final[str] = "bz-persistence-capture"

_DIRECTIONS: Final[dict[str, Direction]] = {
    item.value: item for item in Direction
}
_SIDES: Final[dict[str, LevelSide]] = {item.value: item for item in LevelSide}


# ---------------------------------------------------------------------------
# Encoding. Every value is written as a string or a plain scalar, so a decoded
# artifact carries no float that a JSON round-trip could have rewritten.
# ---------------------------------------------------------------------------


def _bar_payload(bar: PriceBar) -> list[str]:
    """One bar as five strings. **Positional, because there are ~500,000 of them.**

    A dict per bar would triple the file for no information. The order is fixed
    here and asserted on read: ``[open_time, open, high, low, close]``.
    """
    return [
        bar.open_time.isoformat(),
        str(bar.open),
        str(bar.high),
        str(bar.low),
        str(bar.close),
    ]


def _bar_from(symbol: str, interval: str, row: Sequence[Any]) -> PriceBar:
    if len(row) != 5:
        raise SwingLabError(
            f"a {symbol} {interval} bar has {len(row)} fields, expected 5 "
            "([open_time, open, high, low, close])"
        )
    return PriceBar(
        symbol=symbol,
        interval=interval,
        open_time=datetime.fromisoformat(row[0]),
        open=Decimal(row[1]),
        high=Decimal(row[2]),
        low=Decimal(row[3]),
        close=Decimal(row[4]),
    )


def _level_payload(ref: LevelRef) -> list[Any]:
    return [ref.price, ref.side.value, ref.interval, ref.origin_index, ref.origin_label]


def _level_from(row: Sequence[Any]) -> LevelRef:
    if len(row) != 5:
        raise SwingLabError(f"a level has {len(row)} fields, expected 5")
    side = _SIDES.get(row[1])
    if side is None:
        raise SwingLabError(f"unknown level side {row[1]!r}")
    return LevelRef(
        price=row[0], side=side, interval=row[2],
        origin_index=row[3], origin_label=row[4],
    )


def _candidate_payload(candidate: GeometryCandidate) -> dict[str, Any]:
    return {
        "symbol": candidate.symbol,
        "setup_id": candidate.setup_id,
        "direction": candidate.direction.value,
        "signal_at": candidate.signal_at.isoformat(),
        "signal_index": candidate.signal_index,
        "reference_price": candidate.reference_price,
        "execution_stop_levels": [
            _level_payload(item) for item in candidate.execution_stop_levels
        ],
        "setup_stop_levels": [
            _level_payload(item) for item in candidate.setup_stop_levels
        ],
        "setup_target_levels": [
            _level_payload(item) for item in candidate.setup_target_levels
        ],
        "context_target_levels": [
            _level_payload(item) for item in candidate.context_target_levels
        ],
        "execution_atr": candidate.execution_atr,
        "setup_atr": candidate.setup_atr,
        "context_interval": candidate.context_interval,
        "setup_interval": candidate.setup_interval,
        "execution_interval": candidate.execution_interval,
        "segment": candidate.segment,
        "context_regime_structure": candidate.context_regime_structure,
        "context_regime_volatility": candidate.context_regime_volatility,
        "context_structural_trend": candidate.context_structural_trend,
        "setup_structural_trend": candidate.setup_structural_trend,
        "metadata": dict(candidate.metadata),
    }


def _candidate_from(payload: Mapping[str, Any]) -> GeometryCandidate:
    direction = _DIRECTIONS.get(payload["direction"])
    if direction is None:
        raise SwingLabError(f"unknown direction {payload['direction']!r}")
    return GeometryCandidate(
        symbol=payload["symbol"],
        setup_id=payload["setup_id"],
        direction=direction,
        signal_at=datetime.fromisoformat(payload["signal_at"]),
        signal_index=payload["signal_index"],
        reference_price=payload["reference_price"],
        execution_stop_levels=tuple(
            _level_from(item) for item in payload["execution_stop_levels"]
        ),
        setup_stop_levels=tuple(
            _level_from(item) for item in payload["setup_stop_levels"]
        ),
        setup_target_levels=tuple(
            _level_from(item) for item in payload["setup_target_levels"]
        ),
        context_target_levels=tuple(
            _level_from(item) for item in payload["context_target_levels"]
        ),
        execution_atr=payload["execution_atr"],
        setup_atr=payload["setup_atr"],
        context_interval=payload["context_interval"],
        setup_interval=payload["setup_interval"],
        execution_interval=payload["execution_interval"],
        segment=payload["segment"],
        context_regime_structure=payload["context_regime_structure"],
        context_regime_volatility=payload["context_regime_volatility"],
        context_structural_trend=payload["context_structural_trend"],
        setup_structural_trend=payload["setup_structural_trend"],
        metadata=dict(payload["metadata"]),
    )


def _observation_payload(observation: ThesisObservation) -> dict[str, Any]:
    return {
        "as_of": observation.as_of.isoformat(),
        "bar_index": observation.bar_index,
        "context_structural_trend": observation.context_structural_trend,
        "setup_structural_trend": observation.setup_structural_trend,
        "execution_structural_trend": observation.execution_structural_trend,
        "context_regime_structure": observation.context_regime_structure,
        "evidence_state": observation.evidence_state,
        "evidence_dominant_alignment": observation.evidence_dominant_alignment,
        "decision_context_state": observation.decision_context_state,
        "setup_state": observation.setup_state,
        "setup_direction": observation.setup_direction,
        "execution_close": observation.execution_close,
        "upper_levels": [_level_payload(item) for item in observation.upper_levels],
        "lower_levels": [_level_payload(item) for item in observation.lower_levels],
    }


def _observation_from(symbol: str, payload: Mapping[str, Any]) -> ThesisObservation:
    return ThesisObservation(
        symbol=symbol,
        as_of=datetime.fromisoformat(payload["as_of"]),
        bar_index=payload["bar_index"],
        context_structural_trend=payload["context_structural_trend"],
        setup_structural_trend=payload["setup_structural_trend"],
        execution_structural_trend=payload["execution_structural_trend"],
        context_regime_structure=payload["context_regime_structure"],
        evidence_state=payload["evidence_state"],
        evidence_dominant_alignment=payload["evidence_dominant_alignment"],
        decision_context_state=payload["decision_context_state"],
        setup_state=payload["setup_state"],
        setup_direction=payload["setup_direction"],
        execution_close=payload["execution_close"],
        upper_levels=tuple(_level_from(item) for item in payload["upper_levels"]),
        lower_levels=tuple(_level_from(item) for item in payload["lower_levels"]),
    )


def _universe_payload(
    capture: GeometryCapture,
    timelines: Mapping[str, ThesisTimeline],
    *,
    execution_interval: str,
) -> dict[str, Any]:
    return {
        "admission_variant_id": capture.admission_variant_id,
        "admission_policy_id": capture.admission_policy_id,
        "execution_interval": execution_interval,
        "symbols": sorted(capture.bars_by_symbol),
        "metadata": dict(capture.metadata),
        "bars": {
            symbol: [_bar_payload(bar) for bar in bars]
            for symbol, bars in sorted(capture.bars_by_symbol.items())
        },
        "candidates": [_candidate_payload(item) for item in capture.candidates],
        "timeline": {
            symbol: [
                _observation_payload(timeline.observations[index])
                for index in sorted(timeline.observations)
            ]
            for symbol, timeline in sorted(timelines.items())
        },
    }


def encode_capture(
    universes: Mapping[str, tuple[GeometryCapture, Mapping[str, ThesisTimeline]]],
    *,
    manifest: Mapping[str, Any],
    execution_interval: str = "4h",
) -> dict[str, Any]:
    """Encode one or more captured universes into a JSON-safe payload.

    ``universes`` maps a universe name — ``"primary"``, ``"holdout"`` — to the
    capture and the timelines that came out of the **same** replay pass. Keeping
    them together is the point: a timeline paired with a different capture would
    describe a different market at the same bar index.
    """
    if not universes:
        raise SwingLabError("a capture artifact needs at least one universe")
    payload: dict[str, Any] = {
        "schema_version": BZ_CAPTURE_SCHEMA_VERSION,
        "kind": BZ_CAPTURE_KIND,
        "manifest": dict(manifest),
        "universes": {
            name: _universe_payload(
                capture, timelines, execution_interval=execution_interval
            )
            for name, (capture, timelines) in sorted(universes.items())
        },
    }
    payload["manifest"] = {
        **payload["manifest"],
        "content_digest": capture_digest(payload),
    }
    return payload


def capture_digest(payload: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical content, **excluding the digest field itself**.

    The digest cannot cover the slot it is written into, so `manifest` is
    digested with `content_digest` removed. Every other manifest field — the
    pre-registration digest, the window, the cost scenario, the capture
    timestamp — **is** covered, so a hand-edited manifest is caught exactly as a
    hand-edited bar is.
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
            "manifest": manifest,
            "universes": payload["universes"],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------


def write_persistence_capture(
    payload: Mapping[str, Any], path: str | Path, *, compress: bool = True
) -> Path:
    """Write the capture. **Gzip is deterministic here, and that is deliberate.**

    `gzip.GzipFile` writes the current time into its header by default, so two
    byte-identical captures would produce two different files. ``mtime=0`` and a
    fixed compression level make the *file* reproducible too — but the digest is
    still taken over the canonical JSON, so a reader never depends on it.
    """
    target = Path(path)
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if compress:
        if target.suffix != ".gz":
            target = target.with_suffix(target.suffix + ".gz")
        with open(target, "wb") as raw:
            # `filename=""` matters as much as `mtime=0`: given a fileobj,
            # GzipFile otherwise stores `fileobj.name` in the header, so the
            # same capture written to two paths would produce two different
            # files and the reproducibility claim would be false.
            with gzip.GzipFile(
                filename="", fileobj=raw, mode="wb", compresslevel=6, mtime=0
            ) as stream:
                stream.write(canonical)
    else:
        target.write_bytes(canonical)
    return target


@dataclass(frozen=True, slots=True)
class CapturedUniverse:
    """One universe's frozen inputs, ready to be measured without a network."""

    name: str
    capture: GeometryCapture
    timelines: Mapping[str, ThesisTimeline]

    @property
    def candidates(self) -> int:
        return len(self.capture.candidates)

    @property
    def observations(self) -> int:
        return sum(len(item.observations) for item in self.timelines.values())

    @property
    def bars(self) -> int:
        return sum(len(item) for item in self.capture.bars_by_symbol.values())


class PersistenceCaptureArtifact:
    """A decoded BZ capture. **Refuses anything it cannot fully account for.**"""

    __slots__ = ("_payload", "_universes")

    def __init__(self, payload: Mapping[str, Any]) -> None:
        kind = payload.get("kind")
        if kind != BZ_CAPTURE_KIND:
            raise SwingLabError(
                f"this file declares kind {kind!r}, not {BZ_CAPTURE_KIND!r}; a "
                "study artifact and a capture artifact are different documents "
                "and are not interchangeable"
            )
        version = payload.get("schema_version")
        if version != BZ_CAPTURE_SCHEMA_VERSION:
            raise SwingLabError(
                f"this capture was written by schema version {version!r}; this "
                f"build reads version {BZ_CAPTURE_SCHEMA_VERSION}. It is NOT "
                "upgraded silently — a reader guessing at an older layout will "
                "eventually mis-read a field and report a number nobody measured"
            )
        for required in ("manifest", "universes"):
            if required not in payload:
                raise SwingLabError(f"this capture has no {required!r} section")
        manifest = payload["manifest"]
        for required in (
            "preregistration_id",
            "preregistration_digest",
            "captured_at",
            "evaluation_window_bars",
            "deciding_cost_policy_id",
            "content_digest",
        ):
            if required not in manifest:
                raise SwingLabError(
                    f"this capture's manifest has no {required!r}; a capture "
                    "that cannot say what it was taken under cannot be audited"
                )
        self._payload = payload
        self._universes = {
            name: self._decode_universe(name, block)
            for name, block in payload["universes"].items()
        }

    @staticmethod
    def _decode_universe(name: str, block: Mapping[str, Any]) -> CapturedUniverse:
        interval = block["execution_interval"]
        bars_by_symbol = {
            symbol: tuple(_bar_from(symbol, interval, row) for row in rows)
            for symbol, rows in block["bars"].items()
        }
        candidates = tuple(_candidate_from(item) for item in block["candidates"])

        # ---- completeness, checked rather than assumed ----
        for candidate in candidates:
            bars = bars_by_symbol.get(candidate.symbol)
            if bars is None:
                raise SwingLabError(
                    f"universe {name!r} holds a {candidate.symbol} candidate but "
                    f"no {candidate.symbol} bars; a capture is refused rather "
                    "than completed from the network"
                )
            if candidate.signal_index >= len(bars):
                raise SwingLabError(
                    f"universe {name!r}: {candidate.symbol} candidate "
                    f"{candidate.setup_id} names bar {candidate.signal_index} "
                    f"but only {len(bars)} bars were captured"
                )
            if bars[candidate.signal_index].open_time != candidate.signal_at:
                raise SwingLabError(
                    f"universe {name!r}: {candidate.symbol} candidate "
                    f"{candidate.setup_id} says bar {candidate.signal_index} "
                    f"opens {candidate.signal_at.isoformat()} but the captured "
                    f"bar opens {bars[candidate.signal_index].open_time.isoformat()}"
                )

        timelines: dict[str, ThesisTimeline] = {}
        for symbol, rows in block.get("timeline", {}).items():
            if symbol not in bars_by_symbol:
                raise SwingLabError(
                    f"universe {name!r} holds a {symbol} timeline but no "
                    f"{symbol} bars"
                )
            observations = {}
            for row in rows:
                observation = _observation_from(symbol, row)
                if observation.bar_index >= len(bars_by_symbol[symbol]):
                    raise SwingLabError(
                        f"universe {name!r}: {symbol} observation names bar "
                        f"{observation.bar_index} but only "
                        f"{len(bars_by_symbol[symbol])} bars were captured"
                    )
                observations[observation.bar_index] = observation
            timelines[symbol] = ThesisTimeline(
                symbol=symbol, observations=observations
            )

        return CapturedUniverse(
            name=name,
            capture=GeometryCapture(
                admission_variant_id=block["admission_variant_id"],
                admission_policy_id=block["admission_policy_id"],
                candidates=candidates,
                bars_by_symbol=bars_by_symbol,
                metadata=dict(block["metadata"]),
            ),
            timelines=timelines,
        )

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
    def universe_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._universes))

    def universe(self, name: str) -> CapturedUniverse:
        found = self._universes.get(name)
        if found is None:
            raise SwingLabError(
                f"this capture holds no universe {name!r}; it holds "
                f"{', '.join(self.universe_names)}"
            )
        return found


def read_persistence_capture(path: str | Path) -> PersistenceCaptureArtifact:
    """Decode a capture from disk. **No network, at any point, for any reason.**

    Raises:
        SwingLabError: the file is unreadable, is not a capture artifact, was
            written by another schema version, or is internally incomplete.
    """
    target = Path(path)
    try:
        raw = target.read_bytes()
    except OSError as error:
        raise SwingLabError(f"cannot read capture {target}: {error}") from None
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError) as error:
            raise SwingLabError(
                f"capture {target} is gzipped but truncated or corrupt: {error}"
            ) from None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SwingLabError(f"capture {target} is not valid JSON: {error}") from None
    if not isinstance(payload, dict):
        raise SwingLabError(f"capture {target} is not a JSON object")
    return PersistenceCaptureArtifact(payload)


def verify_capture_digest(artifact: PersistenceCaptureArtifact) -> bool:
    """Recompute the content digest and compare it to the stored one.

    This is what catches a hand-edited bar, candidate, observation or manifest
    field. It is a **separate** question from `verify_bz_preregistration`, which
    asks whether the capture was taken under this build's seal; a capture can be
    intact and still describe a different experiment, and the two failures must
    not be reported as one.
    """
    if not isinstance(artifact, PersistenceCaptureArtifact):
        raise TypeError("artifact must be a PersistenceCaptureArtifact")
    return capture_digest(artifact.payload) == artifact.content_digest
