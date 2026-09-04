"""The observation-level paired-effect dataset. **Every row auditable offline.**

Milestone CB reasoned about Milestone CA's sample from *published figures* — a
half-width, a count, a symbol total — because CA's observation-level data did not
exist anywhere in this repository. Milestone CC then wrote that limitation down
(CC-1) and tried to work around it with a price-return proxy, which failed. CD's
first job is to stop reasoning about the observations and produce them.

**Where a row comes from.** `fmis.swing_lab.admission_study.study_from_capture`
runs the sealed CA experiment and now accepts an additive observer sink; CD
attaches one and keeps every `PairedRecord` the study collects at its primary
master seed. Nothing about CA's measurement is re-derived here — the paired
difference is `PairedRecord.difference(PRIMARY_HORIZON)` called, the direction,
the volatility band, the matching tier and the pool size are copied, and the
economic identity is `fmis.universe.identity.economic_asset_id` called.

**One row is one (admission, null family) pair at one horizon.** Five families
measure the *same* admitted instants against different controls, so five rows can
share an admission. That is not five experiments and the row count must never be
presented as one: `dependence_coverage_of` reports rows, admissions and economic assets as
three separate numbers, and the headline estimate is computed **within one
family**, never across the pooled five.

**Nothing here filters on an outcome.** Every exclusion this module can make is a
property of the admission's identity or of the panel's shape — a missing horizon,
an unknown quote asset — and `fmis.paired_dependence.controls` asserts
non-vacuously that permuting every measured difference leaves the excluded set
identical.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from fmis.paired_dependence.estimator import block_index
from fmis.paired_dependence.models import (
    PairedDependenceError,
    require_count,
    require_text,
)

__all__ = [
    "CD_QUOTE_ASSETS",
    "BASE_ASSET_RULE",
    "ObservationRow",
    "base_asset_of",
    "rows_from_records",
    "observations_from_capture",
    "dependence_coverage_of",
    "dependence_concentration_of",
    "dependence_overlap_of",
]

#: The quote assets CD can strip to reach a base asset. Milestone CA's three
#: sealed universes are USDT pairs without exception, and a symbol quoted in
#: anything else is REFUSED rather than guessed at — `ETHBTC` split on a guessed
#: quote would map an ETH/BTC cross onto the ETH exposure and silently merge two
#: clusters into one.
CD_QUOTE_ASSETS: Final[tuple[str, ...]] = ("USDT",)

BASE_ASSET_RULE: Final[str] = (
    "A symbol's base asset is the symbol with a known quote asset removed from "
    "its end, where the known quote assets are exactly CD_QUOTE_ASSETS. A symbol "
    "ending in no known quote asset is REFUSED, never split on a length guess. "
    "The base asset is then resolved to an economic identity by Milestone CC's "
    "fmis.universe.identity.economic_asset_id, so a wrapped, leveraged or "
    "redenominated representation collapses onto the exposure it represents."
)


@dataclass(frozen=True, slots=True)
class ObservationRow:
    """One paired admission-vs-control effect, with the provenance to audit it.

    ``difference`` is the estimand: the admission's forward ATR excursion at the
    primary horizon minus the mean of its own matched controls' — Milestone CA's
    `PairedRecord.difference`, copied rather than recomputed.
    """

    observation_id: str
    family_id: str
    sample: str
    universe: str
    symbol: str
    base_asset: str
    economic_asset: str
    bar_index: int
    as_of: datetime
    direction: str
    horizon: int
    segment: str | None
    volatility: str
    pool_size: int
    radius_tier: int | None
    control_draws: int
    admission_forward: float
    control_forward: float
    difference: float
    capture_content_digest: str
    capture_captured_at: str | None

    def __post_init__(self) -> None:
        for field in (
            "observation_id", "family_id", "sample", "universe", "symbol",
            "base_asset", "economic_asset", "direction", "volatility",
            "capture_content_digest",
        ):
            require_text(getattr(self, field), field)
        require_count(self.bar_index, "bar_index", minimum=0)
        require_count(self.horizon, "horizon", minimum=1)
        require_count(self.pool_size, "pool_size", minimum=0)
        require_count(self.control_draws, "control_draws", minimum=1)
        if not isinstance(self.as_of, datetime) or self.as_of.utcoffset() is None:
            raise PairedDependenceError("as_of must be a timezone-aware datetime")
        for field in ("admission_forward", "control_forward", "difference"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PairedDependenceError(f"{field} must be a real number")
        # The difference is CA's, copied — so it must still BE the difference.
        # A row whose stored parts do not reconstruct it has been edited, and an
        # edited row is a fabricated observation.
        if abs((self.admission_forward - self.control_forward) - self.difference) > 1e-9:
            raise PairedDependenceError(
                f"observation {self.observation_id} stores a difference of "
                f"{self.difference} but its parts give "
                f"{self.admission_forward - self.control_forward}; a row whose "
                "difference is not its own arithmetic has been edited"
            )

    def block(self, block_bars: int) -> int:
        """Which time block this observation falls in."""
        return block_index(self.bar_index, block_bars=block_bars)

    def payload(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "family_id": self.family_id,
            "sample": self.sample,
            "universe": self.universe,
            "symbol": self.symbol,
            "base_asset": self.base_asset,
            "economic_asset": self.economic_asset,
            "bar_index": self.bar_index,
            "as_of": self.as_of.isoformat(),
            "direction": self.direction,
            "horizon": self.horizon,
            "segment": self.segment,
            "volatility": self.volatility,
            "pool_size": self.pool_size,
            "radius_tier": self.radius_tier,
            "control_draws": self.control_draws,
            "admission_forward": self.admission_forward,
            "control_forward": self.control_forward,
            "difference": self.difference,
            "capture_content_digest": self.capture_content_digest,
            "capture_captured_at": self.capture_captured_at,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ObservationRow":
        """Rebuild a row from its own payload. **The artifact's read path.**"""
        return cls(
            observation_id=payload["observation_id"],
            family_id=payload["family_id"],
            sample=payload["sample"],
            universe=payload["universe"],
            symbol=payload["symbol"],
            base_asset=payload["base_asset"],
            economic_asset=payload["economic_asset"],
            bar_index=payload["bar_index"],
            as_of=datetime.fromisoformat(payload["as_of"]),
            direction=payload["direction"],
            horizon=payload["horizon"],
            segment=payload["segment"],
            volatility=payload["volatility"],
            pool_size=payload["pool_size"],
            radius_tier=payload["radius_tier"],
            control_draws=payload["control_draws"],
            admission_forward=payload["admission_forward"],
            control_forward=payload["control_forward"],
            difference=payload["difference"],
            capture_content_digest=payload["capture_content_digest"],
            capture_captured_at=payload["capture_captured_at"],
        )


def base_asset_of(symbol: str) -> str:
    """A symbol's base asset under `BASE_ASSET_RULE`. **Refuses a guess.**

    Raises:
        PairedDependenceError: the symbol ends in no known quote asset, or the
            remainder would be empty.
    """
    text = require_text(symbol, "symbol")
    for quote in CD_QUOTE_ASSETS:
        if text.endswith(quote) and len(text) > len(quote):
            return text[: -len(quote)]
    raise PairedDependenceError(
        f"symbol {text!r} ends in none of {', '.join(CD_QUOTE_ASSETS)}, so its "
        "base asset cannot be read without guessing where the quote begins. A "
        "guessed split would merge two economic exposures onto one identity"
    )


def rows_from_records(
    records: Sequence[Any],
    *,
    horizon: int,
    universe_for_sample: Mapping[str, str],
    capture_content_digest: str,
    capture_captured_at: str | None,
) -> tuple[ObservationRow, ...]:
    """Turn Milestone CA's `PairedRecord`s into CD rows. **A projection, not a study.**

    Every field is copied from the record or derived by a sealed identity rule.
    Nothing is measured here and nothing is filtered on a measured value.

    Raises:
        PairedDependenceError: a record holds no such horizon, names a sample the
            mapping does not cover, or carries a symbol with an unknown quote.
    """
    from fmis.universe.identity import economic_asset_id

    require_count(horizon, "horizon", minimum=1)
    rows: list[ObservationRow] = []
    for record in records:
        sample = record.sample
        universe = universe_for_sample.get(sample)
        if universe is None:
            raise PairedDependenceError(
                f"record on sample {sample!r} names no captured universe; the "
                f"mapping covers {', '.join(sorted(universe_for_sample))}"
            )
        admission = record.admission_forward.get(horizon)
        control = record.control_forward.get(horizon)
        if admission is None or control is None:
            raise PairedDependenceError(
                f"a {record.family_id} record on {record.symbol} holds no horizon "
                f"{horizon}; it holds {sorted(record.admission_forward)}"
            )
        base = base_asset_of(record.symbol)
        direction = getattr(record.direction, "value", record.direction)
        rows.append(
            ObservationRow(
                observation_id=(
                    f"{record.family_id}|{sample}|{record.symbol}|{record.bar_index}"
                ),
                family_id=record.family_id,
                sample=sample,
                universe=universe,
                symbol=record.symbol,
                base_asset=base,
                economic_asset=economic_asset_id(base),
                bar_index=record.bar_index,
                as_of=record.as_of,
                direction=str(direction),
                horizon=horizon,
                segment=record.segment,
                volatility=record.volatility,
                pool_size=record.pool_size,
                radius_tier=record.radius_tier,
                control_draws=len(record.control_primary_draws),
                admission_forward=float(admission),
                control_forward=float(control),
                difference=record.difference(horizon),
                capture_content_digest=capture_content_digest,
                capture_captured_at=capture_captured_at,
            )
        )
    seen: set[str] = set()
    for row in rows:
        if row.observation_id in seen:
            raise PairedDependenceError(
                f"observation {row.observation_id} appears twice; a duplicated "
                "observation would be counted as new information by every "
                "estimator downstream"
            )
        seen.add(row.observation_id)
    return tuple(sorted(rows, key=lambda item: item.observation_id))


def observations_from_capture(
    artifact: Any,
    *,
    horizon: int,
    universe_for_sample: Mapping[str, str],
    run_at: datetime,
    samples: Sequence[Any] | None = None,
    progress: Callable[[str], None] | None = None,
) -> tuple[tuple[ObservationRow, ...], Any]:
    """Run CA's sealed study over a capture and keep every paired observation.

    **No network, at any point, for any reason** — `study_from_capture` has no
    live path at all, and a regression runs this with every transport
    monkeypatched to raise.

    Returns ``(rows, study)``. The study is returned rather than discarded so the
    report can state the reconstructed admission counts beside Milestone CA's
    published ones instead of assuming a re-capture reproduced them.

    ``samples`` defaults to Milestone BY's sealed specifications and exists for
    the same reason Milestone CA's own entry point carries it — a fixture capture
    holds three synthetic symbols, and a test that could not name them could not
    exercise this path at all. A guard asserts the default IS the sealed set, so
    the parameter cannot become a way to quietly re-cut a sample.
    """
    from fmis.swing_lab.admission_study import study_from_capture
    from fmis.swing_lab.preregistration import SAMPLES

    collected: list[Any] = []
    study = study_from_capture(
        artifact,
        universe_for_sample=universe_for_sample,
        run_at=run_at,
        causal_proven=False,
        samples=SAMPLES if samples is None else samples,
        progress=progress,
        record_observer=collected.extend,
    )
    rows = rows_from_records(
        collected,
        horizon=horizon,
        universe_for_sample=universe_for_sample,
        capture_content_digest=artifact.content_digest,
        capture_captured_at=artifact.manifest.get("captured_at"),
    )
    return rows, study


def dependence_coverage_of(
    rows: Sequence[ObservationRow], *, block_bars: int
) -> dict[str, Any]:
    """Rows, admissions, assets, blocks and pairs — **as five separate numbers.**

    This function exists to make pseudoreplication visible rather than to hide
    it. A large ``rows`` with a small ``economic_assets`` is exactly the shape
    that looks like a large sample and is not one.
    """
    require_count(block_bars, "block_bars", minimum=1)
    admissions = {(row.sample, row.symbol, row.bar_index) for row in rows}
    assets = {row.economic_asset for row in rows}
    symbols = {row.symbol for row in rows}
    blocks: dict[int, set[str]] = {}
    per_asset: dict[str, int] = {}
    cells: set[tuple[int, str]] = set()
    for row in rows:
        block = row.block(block_bars)
        blocks.setdefault(block, set()).add(row.economic_asset)
        per_asset[row.economic_asset] = per_asset.get(row.economic_asset, 0) + 1
        cells.add((block, row.economic_asset))
    informative = {b: a for b, a in blocks.items() if len(a) >= 2}
    asset_count = len(assets)
    return {
        "rows": len(rows),
        "admissions": len(admissions),
        "economic_assets": asset_count,
        "provider_symbols": len(symbols),
        "symbols_per_economic_asset": (
            len(symbols) / asset_count if asset_count else None
        ),
        "families": len({row.family_id for row in rows}),
        "samples": sorted({row.sample for row in rows}),
        "block_bars": block_bars,
        "blocks": len(blocks),
        "blocks_with_two_or_more_assets": len(informative),
        "cells": len(cells),
        "cells_in_informative_blocks": sum(len(a) for a in informative.values()),
        "possible_asset_pairs": asset_count * (asset_count - 1) // 2,
        "assets_with_two_or_more_observations": sum(
            1 for count in per_asset.values() if count >= 2
        ),
        "observations_per_asset_min": min(per_asset.values()) if per_asset else None,
        "observations_per_asset_max": max(per_asset.values()) if per_asset else None,
        "observations_per_asset_mean": (
            sum(per_asset.values()) / asset_count if asset_count else None
        ),
    }


def dependence_concentration_of(rows: Sequence[ObservationRow]) -> dict[str, Any]:
    """Which economic assets the panel actually rests on.

    A dependence estimate driven by two assets is not a universe-level
    measurement, and the only way a reader can tell is to be shown the shares.
    ``largest_share`` reuses `fmis.research_design.numeric.largest_share`, the
    repository's single definition, over the **absolute** paired differences —
    magnitude of contribution, not signed effect.
    """
    from fmis.research_design.numeric import largest_share

    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for row in rows:
        totals[row.economic_asset] = totals.get(row.economic_asset, 0.0) + abs(
            row.difference
        )
        counts[row.economic_asset] = counts.get(row.economic_asset, 0) + 1
    grand = sum(totals.values())
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    shares = [(name, (value / grand) if grand else None) for name, value in ranked]
    return {
        "largest_share": largest_share(
            (row.economic_asset, abs(row.difference)) for row in rows
        ),
        "top_three_share": (
            sum(value for _n, value in ranked[:3]) / grand if grand else None
        ),
        "shares": [
            {"economic_asset": name, "share": share, "observations": counts[name]}
            for name, share in shares
        ],
    }


def dependence_overlap_of(
    rows: Sequence[ObservationRow], *, evaluation_window_bars: int
) -> dict[str, Any]:
    """How much the forward windows overlap. **Counted, never assumed away.**

    Two observations on the same economic asset whose admissions sit fewer than
    ``evaluation_window_bars`` apart share forward bars, so their differences are
    mechanically dependent beyond anything the market did. Milestone CA counted
    this on its own samples (33 of 155 on development) and CD recounts it per
    family, because a count taken over the pooled five families would multiply it.
    """
    require_count(evaluation_window_bars, "evaluation_window_bars", minimum=1)
    per_family: dict[str, dict[str, int]] = {}
    for row in rows:
        per_family.setdefault(row.family_id, {})
    by_key: dict[tuple[str, str, str], list[int]] = {}
    for row in rows:
        by_key.setdefault(
            (row.family_id, row.sample, row.economic_asset), []
        ).append(row.bar_index)
    overlapping: dict[tuple[str, str], int] = {}
    totals: dict[tuple[str, str], int] = {}
    for (family, sample, _asset), indices in by_key.items():
        ordered = sorted(indices)
        totals[(family, sample)] = totals.get((family, sample), 0) + len(ordered)
        for position, index in enumerate(ordered):
            near = any(
                abs(index - other) < evaluation_window_bars
                for other_position, other in enumerate(ordered)
                if other_position != position
            )
            if near:
                overlapping[(family, sample)] = (
                    overlapping.get((family, sample), 0) + 1
                )
    return {
        "evaluation_window_bars": evaluation_window_bars,
        "by_family_sample": [
            {
                "family_id": family,
                "sample": sample,
                "observations": count,
                "within_window_of_another": overlapping.get((family, sample), 0),
                "share": (
                    overlapping.get((family, sample), 0) / count if count else None
                ),
            }
            for (family, sample), count in sorted(totals.items())
        ],
    }
