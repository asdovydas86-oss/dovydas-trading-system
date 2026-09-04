"""Uncertainty for a dependence estimate. **Resampled on the axis it belongs to.**

A point estimate of a correlation is not a scientific result, and the interval
around one is not a free choice: it has to resample whatever the estimate treats
as an independent replicate, or it reports a precision the panel does not have.

**Two estimands, two natural resampling axes, and CD runs both.**

* ``r_b`` — the between-asset correlation — is estimated with **time block** as
  the grouping. Its independent replicates are therefore blocks, and the primary
  interval resamples blocks with replacement.
* ``rho_w`` — the within-asset correlation — is estimated with **economic asset**
  as the grouping. Its independent replicates are assets, and the primary
  interval resamples assets — the same axis Milestone CA's own bootstrap
  resamples, deliberately, so the two milestones' uncertainty statements are
  about the same thing.

Each is also run on the *other* axis as a declared sensitivity. When the two
disagree the disagreement is **reported, not resolved**: it means the panel's
dependence is not separable into the two components the model posits, which is
information about the model rather than a defect in the interval.

**A resampled group drawn twice becomes two groups.** This is the property that
makes a cluster bootstrap a cluster bootstrap. Merging the two copies back into
one group would shrink the between-group variance toward the observed one and
produce an interval too narrow by exactly the resampling it was supposed to do.

**Fisher-z is not used.** Its variance formula assumes independent bivariate
normal pairs, and every observation here is one of a handful on a clustered,
serially overlapping panel. It would produce the narrowest interval on offer and
would be the least defensible; the narrowness is the reason to refuse it.

**Every draw is seeded from its own identity.** `derive_seed` is
`fmis.research_design.numeric.derive_seed`, the repository's single definition,
so a draw is a pure function of what it is drawing for and no result moves when
a caller reorders a loop or changes ``PYTHONHASHSEED``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from random import Random
from typing import Any

from fmis.paired_dependence.estimator import (
    CellReduction,
    VarianceComponents,
    block_index,
    group_by_asset,
    group_by_block,
    intraclass_icc,
)
from fmis.paired_dependence.models import (
    GroupingAxis,
    PairedDependenceError,
    Weighting,
    require_count,
    require_probability,
)

__all__ = [
    "DependenceInterval",
    "estimate_on_axis",
    "bootstrap_interval",
]


@dataclass(frozen=True, slots=True)
class DependenceInterval:
    """One correlation with its resampled interval and everything that shaped it."""

    axis: GroupingAxis
    resample_axis: GroupingAxis
    point: float | None
    lower: float | None
    upper: float | None
    confidence: float
    draws_requested: int
    draws_used: int
    draws_undefined: int
    components: VarianceComponents
    reason: str | None

    @property
    def half_width(self) -> float | None:
        if self.lower is None or self.upper is None:
            return None
        return (self.upper - self.lower) / 2.0

    @property
    def excludes_zero(self) -> bool | None:
        if self.lower is None or self.upper is None:
            return None
        return self.lower > 0.0 or self.upper < 0.0

    def payload(self) -> dict[str, Any]:
        return {
            "axis": self.axis.value,
            "measures": self.axis.measures,
            "resample_axis": self.resample_axis.value,
            "point": self.point,
            "lower": self.lower,
            "upper": self.upper,
            "half_width": self.half_width,
            "excludes_zero": self.excludes_zero,
            "confidence": self.confidence,
            "draws_requested": self.draws_requested,
            "draws_used": self.draws_used,
            "draws_undefined": self.draws_undefined,
            "components": self.components.payload(),
            "reason": self.reason,
        }


def estimate_on_axis(
    rows: Sequence[Any],
    *,
    axis: GroupingAxis,
    block_bars: int,
    reduction: CellReduction = CellReduction.CELL_MEAN,
    weighting: Weighting = Weighting.EQUAL_CELL,
) -> VarianceComponents:
    """One point estimate on one axis. **The single entry point both axes share.**

    On `ECONOMIC_ASSET` the members are individual paired differences; on
    `TIME_BLOCK` they are per-(asset, block) cell values reduced by ``reduction``.
    ``weighting`` is meaningful only on the block axis, where a cell can stand for
    several observations; on the asset axis every member already *is* one
    observation and observation weighting is identical to equal weighting.
    """
    if not isinstance(axis, GroupingAxis):
        raise PairedDependenceError("axis must be a GroupingAxis")
    if axis is GroupingAxis.ECONOMIC_ASSET:
        grouped = group_by_asset(rows)
        return intraclass_icc(grouped, axis=axis, weighting=Weighting.EQUAL_CELL)
    values, weights, _assets = group_by_block(
        rows, block_bars=block_bars, reduction=reduction
    )
    return intraclass_icc(
        values,
        axis=axis,
        weighting=weighting,
        weights=weights if weighting is Weighting.OBSERVATION_COUNT else None,
    )


class _Relabelled:
    """A row wearing a resampled group label. **A view, never a mutation.**

    A cluster bootstrap that drew one asset twice must treat the two copies as
    two groups. Rather than copying every row's twenty fields, this wraps the
    original and overrides only the two attributes the estimator reads.
    """

    __slots__ = ("_row", "economic_asset", "bar_index", "difference")

    def __init__(self, row: Any, *, economic_asset: str, bar_index: int) -> None:
        self._row = row
        self.economic_asset = economic_asset
        self.bar_index = bar_index
        self.difference = float(row.difference)


def bootstrap_interval(
    rows: Sequence[Any],
    *,
    axis: GroupingAxis,
    resample_axis: GroupingAxis,
    block_bars: int,
    draws: int,
    confidence: float,
    master_seed: int,
    identity: Sequence[Any],
    reduction: CellReduction = CellReduction.CELL_MEAN,
    weighting: Weighting = Weighting.EQUAL_CELL,
) -> DependenceInterval:
    """Resample ``resample_axis`` with replacement and re-estimate on ``axis``.

    Bounds are **nearest-rank percentiles** of the resampled estimates —
    `fmis.research_design.numeric.nearest_rank_quantile`, the repository's rule:
    an interpolated bound reports a correlation no resample ever produced.

    Draws on which the estimator is undefined (a resample that happened to draw
    one group, or a constant panel) are **counted and excluded**, never replaced
    by a zero. If fewer than half the requested draws are usable, the interval is
    refused with a reason rather than reported from the survivors.

    Raises:
        PairedDependenceError: a malformed count, confidence or axis.
    """
    from fmis.research_design.numeric import derive_seed, nearest_rank_quantile

    if not isinstance(resample_axis, GroupingAxis):
        raise PairedDependenceError("resample_axis must be a GroupingAxis")
    require_count(draws, "draws", minimum=1)
    require_count(block_bars, "block_bars", minimum=1)
    level = require_probability(confidence, "confidence")

    point = estimate_on_axis(
        rows, axis=axis, block_bars=block_bars, reduction=reduction, weighting=weighting
    )

    def refused(reason: str) -> DependenceInterval:
        return DependenceInterval(
            axis=axis,
            resample_axis=resample_axis,
            point=point.correlation,
            lower=None,
            upper=None,
            confidence=level,
            draws_requested=draws,
            draws_used=0,
            draws_undefined=draws,
            components=point,
            reason=reason,
        )

    if point.correlation is None:
        return refused(
            f"the point estimate is undefined, so no interval can surround it: "
            f"{point.reason}"
        )

    if resample_axis is GroupingAxis.ECONOMIC_ASSET:
        buckets: dict[Any, list[Any]] = {}
        for row in rows:
            buckets.setdefault(row.economic_asset, []).append(row)
    else:
        buckets = {}
        for row in rows:
            buckets.setdefault(block_index(row.bar_index, block_bars=block_bars), []).append(row)
    keys = sorted(buckets, key=str)
    if len(keys) < 2:
        return refused(
            f"resampling {resample_axis.value} needs at least two of them; this "
            f"panel has {len(keys)}. An interval drawn from one bucket would "
            "resample nothing and would report a width of zero"
        )

    estimates: list[float] = []
    undefined = 0
    for draw in range(draws):
        seed = derive_seed(
            master=master_seed,
            parts=[*identity, axis.value, resample_axis.value, block_bars, draw],
        )
        generator = Random(seed)
        drawn = [generator.choice(keys) for _ in range(len(keys))]
        resampled: list[Any] = []
        for replica, key in enumerate(drawn):
            for row in buckets[key]:
                if resample_axis is GroupingAxis.ECONOMIC_ASSET:
                    resampled.append(
                        _Relabelled(
                            row,
                            economic_asset=f"{row.economic_asset}#{replica}",
                            bar_index=row.bar_index,
                        )
                    )
                else:
                    # A block drawn twice becomes two blocks: the replica index is
                    # folded into the bar index so `block_index` separates them.
                    resampled.append(
                        _Relabelled(
                            row,
                            economic_asset=row.economic_asset,
                            bar_index=(
                                replica * block_bars
                                + row.bar_index % block_bars
                            ),
                        )
                    )
        estimate = estimate_on_axis(
            resampled,
            axis=axis,
            block_bars=block_bars,
            reduction=reduction,
            weighting=weighting,
        )
        if estimate.correlation is None:
            undefined += 1
            continue
        estimates.append(estimate.correlation)

    if len(estimates) * 2 < draws:
        return DependenceInterval(
            axis=axis,
            resample_axis=resample_axis,
            point=point.correlation,
            lower=None,
            upper=None,
            confidence=level,
            draws_requested=draws,
            draws_used=len(estimates),
            draws_undefined=undefined,
            components=point,
            reason=(
                f"only {len(estimates)} of {draws} resamples produced a defined "
                "estimate. An interval read off a minority of draws describes the "
                "resamples that happened to work, not the panel"
            ),
        )

    tail = (1.0 - level) / 2.0
    return DependenceInterval(
        axis=axis,
        resample_axis=resample_axis,
        point=point.correlation,
        lower=nearest_rank_quantile(estimates, tail),
        upper=nearest_rank_quantile(estimates, 1.0 - tail),
        confidence=level,
        draws_requested=draws,
        draws_used=len(estimates),
        draws_undefined=undefined,
        components=point,
        reason=None,
    )
