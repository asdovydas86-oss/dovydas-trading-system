"""Controls that can fail. **A control that always passes is not evidence.**

Every function here is designed around one question: *if this milestone were
wrong in the specific way this control watches for, would the control notice?*
That is why each one ships with a **non-vacuity** counterpart in the test suite —
a case on which the control must *fail* — because Milestone CC found a control it
had shipped that could not detect the very thing it named, and CA found another.

Four negative controls and two hostile ones:

* `shuffle_time_blocks` destroys cross-asset time alignment while keeping every
  other property of the panel. The between-asset correlation must collapse. If it
  does not, ``r_b`` is measuring something other than contemporaneity.
* `shuffle_asset_identity` destroys within-asset structure while keeping the
  timeline. The within-asset correlation must collapse. If it does not, ``rho_w``
  is measuring the timeline rather than the asset.
* `duplicate_rows` makes the panel twice as large and no more informative. The
  correlations and the effective cluster count must not move. This is the
  pseudoreplication control and it is the one most likely to catch a real defect,
  because "more rows" is exactly what a careless pipeline produces.
* `cc_residual_correlation` is Milestone CC's estimator, kept as a **known
  uninformative comparison**. It is not an estimate and no verdict reads it. Its
  job is to return the same value at four different true correlations, which is
  the proof that CC's number could never have been an answer.

* `split_exposure` takes one economic exposure, lists it under two provider
  symbols, and asserts the identity rule collapses them back. A universe that
  counted the two as two clusters would report twice the independent information
  it has.
* `outcome_permutation_stable` permutes every measured difference and asserts
  that nothing about which rows were *kept*, which groups they fell in, or how
  the panel was shaped changed at all. That is the executable form of "no
  outcome-conditioned exclusion", and it is asserted rather than claimed.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from random import Random
from typing import Any

from fmis.paired_dependence.estimator import (
    CellReduction,
    block_index,
    group_by_block,
)
from fmis.paired_dependence.models import (
    GroupingAxis,
    PairedDependenceError,
    Weighting,
    require_count,
)
from fmis.paired_dependence.synthetic import SyntheticRow

__all__ = [
    "ControlReading",
    "shuffle_time_blocks",
    "shuffle_asset_identity",
    "duplicate_rows",
    "cc_residual_correlation",
    "split_exposure",
    "outcome_permutation_stable",
    "panel_shape",
    "run_negative_controls",
]


@dataclass(frozen=True, slots=True)
class ControlReading:
    """One control's before/after pair and what it was watching for."""

    control_id: str
    watches_for: str
    axis: GroupingAxis
    observed: float | None
    under_control: float | None
    expectation: str

    @property
    def shift(self) -> float | None:
        if self.observed is None or self.under_control is None:
            return None
        return self.under_control - self.observed

    def payload(self) -> dict[str, Any]:
        return {
            "control_id": self.control_id,
            "watches_for": self.watches_for,
            "axis": self.axis.value,
            "observed": self.observed,
            "under_control": self.under_control,
            "shift": self.shift,
            "expectation": self.expectation,
        }


def _relabelled(row: Any, *, economic_asset: str, bar_index: int) -> SyntheticRow:
    """A row reduced to the three fields an estimator reads.

    Controls deliberately return `SyntheticRow` rather than a mutated
    `ObservationRow`: an `ObservationRow` carries a capture digest and an
    admission identity, and a shuffled panel is **not** an observation of
    anything. Handing one back wearing real provenance is how a control's output
    ends up in a report as though it were data.
    """
    return SyntheticRow(
        economic_asset=economic_asset,
        bar_index=bar_index,
        difference=float(row.difference),
    )


def shuffle_time_blocks(
    rows: Sequence[Any], *, block_bars: int, seed: int
) -> tuple[SyntheticRow, ...]:
    """Permute each asset's observations across the blocks that asset occupies.

    The permutation is **within asset**, so every asset keeps its own number of
    observations, its own blocks and its own values; only *which value landed in
    which block* changes. That is precisely the contemporaneity ``r_b`` claims to
    measure, and nothing else.
    """
    require_count(block_bars, "block_bars", minimum=1)
    by_asset: dict[str, list[Any]] = {}
    for row in rows:
        by_asset.setdefault(row.economic_asset, []).append(row)
    shuffled: list[SyntheticRow] = []
    for asset in sorted(by_asset):
        members = sorted(by_asset[asset], key=lambda item: item.bar_index)
        indices = [int(item.bar_index) for item in members]
        values = [float(item.difference) for item in members]
        Random(seed + hash_free(asset)).shuffle(values)
        shuffled.extend(
            SyntheticRow(economic_asset=asset, bar_index=index, difference=value)
            for index, value in zip(indices, values)
        )
    return tuple(shuffled)


def hash_free(text: str) -> int:
    """A stable integer from text. **Never Python's salted `hash`.**

    `hash()` is salted per process, so a control seeded with it would shuffle
    differently on two runs of the same machine while claiming determinism — the
    exact failure `fmis.research_design.numeric.derive_seed` exists to exclude.
    """
    from fmis.research_design.numeric import derive_seed

    return derive_seed(master=0, parts=[text])


def shuffle_asset_identity(
    rows: Sequence[Any], *, seed: int
) -> tuple[SyntheticRow, ...]:
    """Permute the asset labels across all rows, keeping the timeline intact.

    Every bar index and every value stays exactly where it was; only which asset
    a row is attributed to moves. The asset-size profile is preserved, so a
    collapse in ``rho_w`` cannot be explained by the panel changing shape.
    """
    ordered = sorted(rows, key=lambda item: (int(item.bar_index), item.economic_asset))
    labels = [row.economic_asset for row in ordered]
    Random(seed).shuffle(labels)
    return tuple(
        SyntheticRow(
            economic_asset=label,
            bar_index=int(row.bar_index),
            difference=float(row.difference),
        )
        for row, label in zip(ordered, labels)
    )


def duplicate_rows(rows: Sequence[Any], *, copies: int = 2) -> tuple[SyntheticRow, ...]:
    """Repeat every row ``copies`` times **under its own asset and its own bar**.

    This is the naive pipeline's mistake made deliberately. The duplicated panel
    holds ``copies`` times the rows, the same assets, the same blocks and exactly
    the same information, so every dependence estimate and every effective
    cluster count must be unmoved. A row count that doubles while an effective-N
    does not is the whole point.

    Raises:
        PairedDependenceError: ``copies`` is below 2 — a control that copies once
            copies nothing.
    """
    require_count(copies, "copies", minimum=2)
    return tuple(
        _relabelled(row, economic_asset=row.economic_asset, bar_index=int(row.bar_index))
        for row in rows
        for _ in range(copies)
    )


def cc_residual_correlation(
    rows: Sequence[Any], *, block_bars: int, reduction: CellReduction = CellReduction.CELL_MEAN
) -> float | None:
    """Milestone CC's estimator, run on paired effects. **A comparison, not an estimate.**

    Cross-sectionally demeans every block — `fmis.universe.dependence.market_residuals`
    called, not reimplemented — and returns the mean pairwise Pearson correlation of
    what is left. For an exchangeable panel this is ``-1 / (K - 1)`` whatever the
    true correlation is, which is why CD reports it beside ``r_b`` rather than
    instead of it.

    `None` when fewer than two blocks survive the demeaning or no pair has two
    shared blocks — a stated absence, never a zero.
    """
    from fmis.universe.dependence import market_residuals, pearson

    values, _weights, assets = group_by_block(
        rows, block_bars=block_bars, reduction=reduction
    )
    series: dict[str, dict[int, float]] = {}
    for block, members in values.items():
        for asset, value in zip(assets[block], members):
            series.setdefault(asset, {})[block] = value
    blocks = sorted({block for by_block in series.values() for block in by_block})
    residuals = market_residuals(blocks, series)
    names = sorted(residuals)
    correlations: list[float] = []
    for position, left in enumerate(names):
        for right in names[position + 1 :]:
            shared = sorted(set(residuals[left]) & set(residuals[right]))
            if len(shared) < 2:
                continue
            value = pearson(
                [residuals[left][b] for b in shared],
                [residuals[right][b] for b in shared],
            )
            if value is not None:
                correlations.append(value)
    return statistics.fmean(correlations) if correlations else None


def split_exposure(
    rows: Sequence[Any], *, economic_asset: str, symbols: Sequence[str]
) -> tuple[SyntheticRow, ...]:
    """Deal one exposure's rows out across several provider symbols.

    The returned rows carry the *symbol* as their grouping label, which is what a
    universe keyed on provider identity would use. Collapsing them back onto one
    economic identity must restore the original panel exactly; a control asserts
    both halves.

    Raises:
        PairedDependenceError: fewer than two symbols were named, or the asset
            holds no rows.
    """
    names = tuple(symbols)
    if len(names) < 2:
        raise PairedDependenceError(
            "splitting an exposure across fewer than two symbols splits nothing"
        )
    members = [row for row in rows if row.economic_asset == economic_asset]
    if not members:
        raise PairedDependenceError(
            f"no row carries economic asset {economic_asset!r}, so there is "
            "nothing to split"
        )
    others = [
        _relabelled(row, economic_asset=row.economic_asset, bar_index=int(row.bar_index))
        for row in rows
        if row.economic_asset != economic_asset
    ]
    split = [
        _relabelled(
            row,
            economic_asset=names[position % len(names)],
            bar_index=int(row.bar_index),
        )
        for position, row in enumerate(sorted(members, key=lambda r: int(r.bar_index)))
    ]
    return tuple(others + split)


def panel_shape(rows: Sequence[Any], *, block_bars: int) -> dict[str, Any]:
    """Everything about a panel that is **not** its measured values.

    Used by `outcome_permutation_stable`: if permuting the outcomes changes any
    of this, some decision in the pipeline read an outcome.
    """
    require_count(block_bars, "block_bars", minimum=1)
    return {
        "rows": len(rows),
        "assets": sorted({row.economic_asset for row in rows}),
        "blocks": sorted(
            {block_index(int(row.bar_index), block_bars=block_bars) for row in rows}
        ),
        "cells": sorted(
            {
                (block_index(int(row.bar_index), block_bars=block_bars), row.economic_asset)
                for row in rows
            }
        ),
        "bar_indices": sorted(int(row.bar_index) for row in rows),
    }


def outcome_permutation_stable(
    rows: Sequence[Any], *, block_bars: int, seed: int, shaper=None
) -> bool:
    """Whether permuting every measured difference leaves the panel's shape identical.

    ``shaper`` defaults to `panel_shape` and exists so a caller can point this at
    a *pipeline* rather than at a panel — the stronger form of the same question.
    """
    take = panel_shape if shaper is None else shaper
    before = take(rows, block_bars=block_bars)
    values = [float(row.difference) for row in rows]
    Random(seed).shuffle(values)
    permuted = [
        _relabelled(row, economic_asset=row.economic_asset, bar_index=int(row.bar_index))
        for row in rows
    ]
    permuted = [
        SyntheticRow(
            economic_asset=row.economic_asset,
            bar_index=row.bar_index,
            difference=value,
        )
        for row, value in zip(permuted, values)
    ]
    return take(permuted, block_bars=block_bars) == before


def run_negative_controls(
    rows: Sequence[Any],
    *,
    block_bars: int,
    seed: int,
    reduction: CellReduction = CellReduction.CELL_MEAN,
) -> tuple[ControlReading, ...]:
    """Run every negative control over one panel and report each before/after.

    Nothing here decides a verdict. The readings go into the report so a reader
    can see whether the controls moved in the direction the design predicted, and
    a control that did not move is a finding rather than a formality.
    """
    from fmis.paired_dependence.uncertainty import estimate_on_axis

    def between(panel: Sequence[Any], weighting: Weighting = Weighting.EQUAL_CELL):
        return estimate_on_axis(
            panel,
            axis=GroupingAxis.TIME_BLOCK,
            block_bars=block_bars,
            reduction=reduction,
            weighting=weighting,
        ).correlation

    def within(panel: Sequence[Any]) -> float | None:
        return estimate_on_axis(
            panel, axis=GroupingAxis.ECONOMIC_ASSET, block_bars=block_bars
        ).correlation

    duplicated = duplicate_rows(rows)
    return (
        ControlReading(
            control_id="shuffled_time_blocks",
            watches_for=(
                "r_b measuring something other than contemporaneity. Permuting "
                "each asset's values across its own blocks destroys time "
                "alignment and nothing else"
            ),
            axis=GroupingAxis.TIME_BLOCK,
            observed=between(rows),
            under_control=between(
                shuffle_time_blocks(rows, block_bars=block_bars, seed=seed)
            ),
            expectation="collapses toward zero",
        ),
        ControlReading(
            control_id="shuffled_asset_identity",
            watches_for=(
                "rho_w measuring the timeline rather than the asset. Permuting "
                "asset labels preserves every value and every bar"
            ),
            axis=GroupingAxis.ECONOMIC_ASSET,
            observed=within(rows),
            under_control=within(shuffle_asset_identity(rows, seed=seed)),
            expectation="collapses toward zero",
        ),
        ControlReading(
            control_id="duplicated_rows_between",
            watches_for=(
                "row count being mistaken for information. Every row is copied, "
                "so the panel doubles and learns nothing"
            ),
            axis=GroupingAxis.TIME_BLOCK,
            observed=between(rows),
            under_control=between(duplicated),
            expectation="unchanged",
        ),
        ControlReading(
            control_id="duplicated_rows_within",
            watches_for="row count being mistaken for information, on the asset axis",
            axis=GroupingAxis.ECONOMIC_ASSET,
            observed=within(rows),
            under_control=within(duplicated),
            expectation="unchanged or slightly higher (a copy IS perfectly correlated)",
        ),
        ControlReading(
            control_id="duplicated_rows_between_observation_weighted",
            watches_for=(
                "row count being mistaken for information on the arm where it "
                "CAN be. Under equal-cell weighting a duplicated panel is "
                "provably unchanged, so that control cannot fail; under "
                "observation-count weighting it can, and independent review "
                "found it was never run there"
            ),
            axis=GroupingAxis.TIME_BLOCK,
            observed=between(rows, Weighting.OBSERVATION_COUNT),
            under_control=between(duplicated, Weighting.OBSERVATION_COUNT),
            expectation="unchanged",
        ),
        ControlReading(
            control_id="cc_residual_estimator",
            watches_for=(
                "Milestone CC's estimator being read as an answer. It returns "
                "-1/(K-1) whatever the true correlation is"
            ),
            axis=GroupingAxis.TIME_BLOCK,
            observed=between(rows),
            under_control=cc_residual_correlation(
                rows, block_bars=block_bars, reduction=reduction
            ),
            expectation="pinned near -1/(K-1), independent of the truth",
        ),
    )
