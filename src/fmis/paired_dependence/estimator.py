"""The dependence estimator. **Derived before it was run, on two named axes.**

Milestone CC's residual estimator failed for a reason worth restating, because
avoiding it is this module's whole design. CC removed the equal-weight
cross-sectional mean from every asset and then correlated what was left. For
``x_i = f + e_i`` with an exchangeable common factor, cross-sectional demeaning
removes ``f`` **exactly**, and the demeaned residuals have pairwise correlation
``-1/(K-1)`` whatever the true residual correlation is. The estimator could not
have reported anything else. It is kept here as a *negative control*
(`fmis.paired_dependence.controls`) and never as an estimate.

**What this module estimates instead, stated as an equation before any data.**

Every observation is one paired difference at Milestone CA's primary horizon:

    D = admission_forward(24) - mean_over_draws(control_forward(24))

which is `fmis.swing_lab.admission_study.PairedRecord.difference(24)` called, not
reimplemented. Group those observations and posit the one-way random-effects
decomposition

    D_gm = mu + alpha_g + eps_gm ,   Var(alpha) = s2_a ,   Var(eps) = s2_e

under which two members of the same group have correlation

    rho = s2_a / (s2_a + s2_e)

and two members of different groups have correlation zero. `intraclass_icc`
estimates ``rho`` by the unbalanced one-way ANOVA method of moments — no
iteration, no optimisation, no starting value, and therefore nothing to tune.

**The same formula, two grouping axes, two different quantities.** This is the
distinction the milestone brief insists on and the module keeps it in the type
system rather than in prose:

* group = **economic asset**, members = its individual paired differences →
  ``rho_w``, the *within-asset* correlation. Two observations here are two
  admissions on one exposure, generally at different times. This is what
  Milestone CB's design effect ``1 + (m - 1) * rho`` consumes.
* group = **time block**, members = the per-asset cell values inside it →
  ``r_b``, the *between-asset* correlation. Two observations here are two
  different exposures inside one contemporaneous window. This is what caps the
  effective cluster count at ``1 / r_b``.

**Are the observations synchronous?** Not exactly, and pretending otherwise is
the trap. Admissions land on whatever 4H bar production admitted them, so two
assets almost never share a bar. A time *block* is what makes the comparison
well posed: two observations are treated as contemporaneous when they fall in the
same block, and the block length is a pre-registered sensitivity dimension
precisely because that choice is a modelling decision and not a fact.

**Cells with several observations are reduced, deterministically, before the
block axis sees them.** ``CELL_MEAN`` averages them; ``CELL_FIRST`` keeps the
earliest by bar index. Both are pre-registered and both are reported, because
they trade off against each other: the mean is lower-variance but heteroskedastic
across cells of different sizes, which biases ``r_b`` *downwards* — the
anti-conservative direction for a feasibility question — while the first
observation is homoskedastic and noisier. Neither is allowed to be the silent
default.

**A negative estimate is not truncated away.** ``MSB < MSW`` yields a negative
``rho``, which is a real statement — less sharing than exchangeable noise would
produce — and is reported as measured. Truncation to ``[0, 1]`` happens only where
downstream arithmetic requires it (`effective_clusters` refuses a negative
correlation), and the truncated value is carried in its own field so a reader can
always see both.

**Standard library only.** No numpy, no scipy. Every quantity below is a sum.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from fmis.paired_dependence.models import (
    GroupingAxis,
    PairedDependenceError,
    Weighting,
    require_count,
)

__all__ = [
    "CellReduction",
    "VarianceComponents",

    "intraclass_icc",
    "group_by_asset",
    "group_by_block",
    "block_index",
    "pairwise_asset_correlations",
    "effective_clusters_from",
    "required_clusters_under_dependence",
    "contemporaneity_fraction",
    "overlap_corrected_correlation",
    "leave_one_out",
]


class CellReduction(Enum):
    """How several observations inside one (asset, block) cell become one member.

    Both are deterministic and both are pre-registered. See the module docstring
    for why neither is the default.
    """

    CELL_MEAN = "cell_mean"
    CELL_FIRST = "cell_first"


@dataclass(frozen=True, slots=True)
class VarianceComponents:
    """One ANOVA decomposition, with every intermediate kept.

    Keeping ``mean_square_between`` and ``mean_square_within`` rather than only
    the ratio is deliberate: a reader who disagrees with the ratio can recompute
    a different one, and a negative ``between_variance`` is visible as the
    ``MSB < MSW`` that produced it rather than as an unexplained negative
    correlation.
    """

    axis: GroupingAxis
    groups: int
    members: int
    groups_with_multiple: int
    degrees_between: int
    degrees_within: int
    mean_square_between: float | None
    mean_square_within: float | None
    k0: float | None
    between_variance: float | None
    within_variance: float | None
    correlation: float | None
    reason: str | None

    @property
    def is_estimated(self) -> bool:
        return self.correlation is not None

    @property
    def truncated_correlation(self) -> float | None:
        """``correlation`` clamped into ``[0, 1]``. **For arithmetic that needs it.**

        `fmis.universe.dependence.effective_clusters` refuses a negative
        correlation because it would report more effective clusters than there
        are assets. This property supplies the clamped value for that call and
        keeps the measured one intact in `correlation`.
        """
        if self.correlation is None:
            return None
        return min(1.0, max(0.0, self.correlation))

    def payload(self) -> dict[str, Any]:
        return {
            "axis": self.axis.value,
            "measures": self.axis.measures,
            "member_unit": self.axis.member_unit,
            "groups": self.groups,
            "members": self.members,
            "groups_with_multiple": self.groups_with_multiple,
            "degrees_between": self.degrees_between,
            "degrees_within": self.degrees_within,
            "mean_square_between": self.mean_square_between,
            "mean_square_within": self.mean_square_within,
            "k0": self.k0,
            "between_variance": self.between_variance,
            "within_variance": self.within_variance,
            "correlation": self.correlation,
            "truncated_correlation": self.truncated_correlation,
            "reason": self.reason,
        }


def intraclass_icc(
    groups: Mapping[Any, Sequence[float]],
    *,
    axis: GroupingAxis,
    weighting: Weighting = Weighting.EQUAL_CELL,
    weights: Mapping[Any, Sequence[float]] | None = None,
) -> VarianceComponents:
    """The unbalanced one-way random-effects ICC. **Method of moments, no fitting.**

    With ``G`` groups holding ``n_g`` members each and ``N = sum(n_g)``:

        SSB = sum_g n_g (mean_g - mean)^2         df_B = G - 1
        SSW = sum_g sum_m (y_gm - mean_g)^2       df_W = N - G
        k0  = (N - sum_g n_g^2 / N) / (G - 1)
        s2_a = (MSB - MSW) / k0        s2_e = MSW
        rho  = s2_a / (s2_a + s2_e)

    ``k0`` is the standard unbalanced correction and equals the common group size
    when every group is the same size, so the balanced case is not a special path.

    Returns a `VarianceComponents` whose ``correlation`` is `None`, with a stated
    ``reason``, when the decomposition is undefined: fewer than two groups, no
    group holding two members, a degenerate ``k0``, or a total variance of zero.
    **`None` is never replaced by a zero**, because "there is no correlation here"
    and "the correlation is zero" are different claims and only one of them is
    evidence.

    ``weighting`` selects whether each member counts once (`EQUAL_CELL`) or
    carries the weight supplied in ``weights`` (`OBSERVATION_COUNT`, used on the
    block axis so a cell built from five observations counts five times). The
    weighted form replaces every count by a weight sum; at unit weights it
    reduces to the unweighted formula exactly, and a regression asserts that.

    Raises:
        PairedDependenceError: ``axis`` is not a `GroupingAxis`, a group holds a
            non-real value, or ``weights`` does not match ``groups`` in shape.
    """
    if not isinstance(axis, GroupingAxis):
        raise PairedDependenceError("axis must be a GroupingAxis")
    if not isinstance(weighting, Weighting):
        raise PairedDependenceError("weighting must be a Weighting")

    ordered = sorted(groups.items(), key=lambda item: str(item[0]))
    cleaned: list[tuple[Any, tuple[float, ...], tuple[float, ...]]] = []
    for key, values in ordered:
        series = tuple(_real(value, f"group {key!r}") for value in values)
        if not series:
            continue
        if weighting is Weighting.OBSERVATION_COUNT:
            if weights is None or key not in weights:
                raise PairedDependenceError(
                    f"observation-count weighting needs a weight for every group; "
                    f"group {key!r} has none"
                )
            supplied = tuple(_real(w, f"weight for group {key!r}") for w in weights[key])
            if len(supplied) != len(series):
                raise PairedDependenceError(
                    f"group {key!r} has {len(series)} member(s) but "
                    f"{len(supplied)} weight(s)"
                )
            if any(w <= 0.0 for w in supplied):
                raise PairedDependenceError(
                    f"group {key!r} carries a non-positive weight; a member that "
                    "counts zero times is an exclusion and must be excluded by a "
                    "stated rule rather than weighted away"
                )
        else:
            supplied = tuple(1.0 for _ in series)
        cleaned.append((key, series, supplied))

    group_count = len(cleaned)
    member_count = sum(len(series) for _key, series, _w in cleaned)
    multiple = sum(1 for _key, series, _w in cleaned if len(series) >= 2)

    def undefined(reason: str) -> VarianceComponents:
        return VarianceComponents(
            axis=axis,
            groups=group_count,
            members=member_count,
            groups_with_multiple=multiple,
            degrees_between=max(group_count - 1, 0),
            degrees_within=max(member_count - group_count, 0),
            mean_square_between=None,
            mean_square_within=None,
            k0=None,
            between_variance=None,
            within_variance=None,
            correlation=None,
            reason=reason,
        )

    if group_count < 2:
        return undefined(
            f"a between-group variance needs at least two groups; this panel has "
            f"{group_count}. Two members of one group say nothing about how "
            "groups differ from each other"
        )
    if member_count <= group_count:
        return undefined(
            f"a within-group variance needs at least one group holding two "
            f"members; {member_count} member(s) across {group_count} group(s) "
            "leaves no within-group degrees of freedom"
        )

    total_weight = sum(sum(w) for _k, _s, w in cleaned)
    grand = sum(
        value * weight
        for _k, series, w in cleaned
        for value, weight in zip(series, w)
    ) / total_weight

    ssb = 0.0
    ssw = 0.0
    sum_squared_weights = 0.0
    group_weights: list[float] = []
    group_squared_weights: list[float] = []
    for _key, series, w in cleaned:
        group_weight = sum(w)
        sum_squared_weights += group_weight * group_weight
        group_weights.append(group_weight)
        group_squared_weights.append(sum(gw * gw for gw in w))
        group_mean = sum(v * gw for v, gw in zip(series, w)) / group_weight
        ssb += group_weight * (group_mean - grand) ** 2
        for value, gw in zip(series, w):
            ssw += gw * (value - group_mean) ** 2

    degrees_between = group_count - 1
    degrees_within = member_count - group_count
    # **The within divisor must be the WEIGHTED one.** ``ssw`` is a weighted sum
    # of squares, so dividing it by the unweighted ``N - G`` makes the estimate
    # scale with the weights: multiplying every weight by c multiplies ``msw`` by
    # c while ``k0`` also scales by c, leaving the between-variance fixed and
    # driving rho toward zero. E[SSW] under weights is
    # ``s2_e * sum_g (W_g - sum_m w^2 / W_g)``, and that is the divisor used here.
    # Found by independent review (finding A-S3); the previous form was covered
    # only by a unit-weight test, which is exactly the case that cannot see it.
    weighted_within = sum(
        group_weight - squared / group_weight
        for group_weight, squared in zip(group_weights, group_squared_weights)
    )
    msb = ssb / degrees_between
    msw = ssw / weighted_within if weighted_within > 0.0 else None
    k0 = (total_weight - sum_squared_weights / total_weight) / degrees_between
    # E[MSB] = k0 * s2_a + within_coefficient * s2_e. Under unit weights the
    # coefficient is exactly 1 and the classical formula falls out; under general
    # weights it does not, and omitting it is what made the estimate drift with a
    # pure change of units.
    within_coefficient = (
        sum(
            squared / group_weight
            for group_weight, squared in zip(group_weights, group_squared_weights)
        )
        - sum(group_squared_weights) / total_weight
    ) / degrees_between
    if msw is None:
        return undefined(
            "the weighted within-group degrees of freedom are not positive, so "
            "no within-group variance is identified from this panel"
        )
    if k0 <= 0.0:
        return undefined(
            "the unbalanced correction k0 is not positive, which happens only "
            "when one group carries the entire weight; no between-group variance "
            "is identified from such a panel"
        )

    between = (msb - within_coefficient * msw) / k0
    within = msw
    total = between + within
    if total == 0.0:
        return undefined(
            "every observation in this panel is identical, so the total variance "
            "is zero and a share of it is undefined. A constant panel has no "
            "correlation; reporting zero would let it dilute an average"
        )
    return VarianceComponents(
        axis=axis,
        groups=group_count,
        members=member_count,
        groups_with_multiple=multiple,
        degrees_between=degrees_between,
        degrees_within=degrees_within,
        mean_square_between=msb,
        mean_square_within=msw,
        k0=k0,
        between_variance=between,
        within_variance=within,
        correlation=between / total,
        reason=None,
    )


def _real(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PairedDependenceError(f"{where} holds a non-real value {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise PairedDependenceError(f"{where} holds a non-finite value {value!r}")
    return number


def block_index(bar_index: int, *, block_bars: int) -> int:
    """Which time block a bar falls in. **Absolute, never relative to a sample.**

    Blocks are cut from bar zero of the capture, so the same bar lands in the
    same block for every asset and every sample. Anchoring blocks at each
    sample's own first admission would make the block boundaries depend on which
    asset happened to admit first, and two samples cut from one capture would
    stop being comparable.
    """
    require_count(bar_index, "bar_index", minimum=0)
    require_count(block_bars, "block_bars", minimum=1)
    return bar_index // block_bars


def group_by_asset(rows: Sequence[Any]) -> dict[str, list[float]]:
    """Group paired differences by economic asset. **Members are observations.**

    ``rows`` is any sequence of objects carrying ``economic_asset`` and
    ``difference``; `fmis.paired_dependence.observations.ObservationRow` is the
    one CD builds, and the loose typing is what lets a synthetic panel exercise
    the same estimator without constructing provenance it does not have.
    """
    grouped: dict[str, list[float]] = {}
    for row in rows:
        grouped.setdefault(row.economic_asset, []).append(float(row.difference))
    return grouped


def group_by_block(
    rows: Sequence[Any],
    *,
    block_bars: int,
    reduction: CellReduction = CellReduction.CELL_MEAN,
) -> tuple[dict[int, list[float]], dict[int, list[float]], dict[int, list[str]]]:
    """Group per-asset cell values by time block. **One member per asset per block.**

    Returns ``(values, weights, assets)`` keyed by block. ``weights`` carries how
    many observations each cell reduced from, so observation-count weighting can
    be applied without recomputing the grouping. ``assets`` names which economic
    asset produced each member, in the same order, so a block's cross-sectional
    coverage is auditable and a hostile control can shuffle identities.

    **A block holding one asset is kept, not dropped.** It carries no
    cross-sectional information but it does carry between-block information, and
    `intraclass_icc` needs the between-group term. Coverage is reported
    separately by `fmis.paired_dependence.observations.dependence_coverage_of` so a reader
    can see how many blocks were cross-sectionally informative.
    """
    if not isinstance(reduction, CellReduction):
        raise PairedDependenceError("reduction must be a CellReduction")
    require_count(block_bars, "block_bars", minimum=1)
    cells: dict[tuple[int, str], list[tuple[int, float]]] = {}
    for row in rows:
        key = (block_index(row.bar_index, block_bars=block_bars), row.economic_asset)
        cells.setdefault(key, []).append((int(row.bar_index), float(row.difference)))

    values: dict[int, list[float]] = {}
    weights: dict[int, list[float]] = {}
    assets: dict[int, list[str]] = {}
    for (block, asset), members in sorted(cells.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        ordered = sorted(members)
        if reduction is CellReduction.CELL_MEAN:
            value = statistics.fmean(item[1] for item in ordered)
        else:
            value = ordered[0][1]
        values.setdefault(block, []).append(value)
        weights.setdefault(block, []).append(float(len(ordered)))
        assets.setdefault(block, []).append(asset)
    return values, weights, assets


def pairwise_asset_correlations(
    rows: Sequence[Any],
    *,
    block_bars: int,
    minimum_shared_blocks: int,
    reduction: CellReduction = CellReduction.CELL_MEAN,
) -> tuple[dict[tuple[str, str], float], dict[str, int]]:
    """The secondary view: correlation per asset pair, over blocks both occupy.

    **This deliberately manufactures nothing.** A pair that never shares a block
    yields no correlation at all — not a zero — and the count of such pairs is
    returned so the report can say how much of the universe the pairwise view
    could not see. That absence is the reason this is a secondary estimator: with
    a few admissions per asset over a few years, most pairs share too few blocks
    for a correlation to mean anything, and a mean taken over the survivors would
    describe the densest corner of the panel rather than the panel.

    Returns ``(correlations, coverage)`` where ``coverage`` counts
    ``possible_pairs``, ``measurable_pairs`` and ``pairs_below_floor``.
    """
    require_count(minimum_shared_blocks, "minimum_shared_blocks", minimum=2)
    from fmis.universe.dependence import pearson

    by_asset: dict[str, dict[int, list[tuple[int, float]]]] = {}
    for row in rows:
        block = block_index(row.bar_index, block_bars=block_bars)
        by_asset.setdefault(row.economic_asset, {}).setdefault(block, []).append(
            (int(row.bar_index), float(row.difference))
        )
    reduced: dict[str, dict[int, float]] = {}
    for asset, blocks in by_asset.items():
        reduced[asset] = {}
        for block, members in blocks.items():
            ordered = sorted(members)
            reduced[asset][block] = (
                statistics.fmean(item[1] for item in ordered)
                if reduction is CellReduction.CELL_MEAN
                else ordered[0][1]
            )

    names = sorted(reduced)
    correlations: dict[tuple[str, str], float] = {}
    possible = 0
    below = 0
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            possible += 1
            shared = sorted(set(reduced[left]) & set(reduced[right]))
            if len(shared) < minimum_shared_blocks:
                below += 1
                continue
            value = pearson(
                [reduced[left][b] for b in shared], [reduced[right][b] for b in shared]
            )
            if value is None:
                below += 1
                continue
            correlations[(left, right)] = value
    return correlations, {
        "possible_pairs": possible,
        "measurable_pairs": len(correlations),
        "pairs_below_floor": below,
    }


def effective_clusters_from(clusters: int, correlation: float | None) -> float | None:
    """``K / (1 + (K - 1) * r)``, delegating to Milestone CC's owner.

    `None` when no correlation was identified. A negative correlation is clamped
    to zero before the call, because `fmis.universe.dependence.effective_clusters`
    refuses one — a negative mean correlation would report more effective clusters
    than there are assets, claiming co-movement created information.
    """
    from fmis.universe.dependence import effective_clusters

    if correlation is None:
        return None
    return effective_clusters(clusters, min(1.0, max(0.0, float(correlation))))


def required_clusters_under_dependence(
    required_independent_clusters: int, correlation: float | None
) -> tuple[float | None, bool]:
    """Invert the saturation curve. **How many correlated clusters buy ``K*`` free ones.**

    Milestone CB's requirement is stated in *independent* clusters. If clusters
    themselves share a common component with correlation ``r``, then ``K`` real
    clusters supply only ``K / (1 + (K - 1) r)`` independent ones, so the
    requirement ``K*`` is met at

        K = K* (1 - r) / (1 - K* r)

    and **only while ``r < 1 / K*``**. At or above that the curve saturates below
    the requirement and no universe of any size satisfies it.

    Returns ``(required_clusters, reachable)``. ``(None, False)`` means
    unreachable at any size. ``(None, True)`` means **no correlation was
    identified**, so no requirement can be stated and nothing has been shown to
    be unreachable — a caller must not read it as "reachable at the base
    requirement". `fmis.paired_dependence.integration.requirement_at` branches on
    the `None` correlation before calling this, and says so in its note.

    Raises:
        PairedDependenceError: ``required_independent_clusters`` is below 1.
    """
    target = require_count(
        required_independent_clusters, "required_independent_clusters", minimum=1
    )
    if correlation is None:
        return None, True
    rho = min(1.0, max(0.0, float(correlation)))
    if rho == 0.0:
        return float(target), True
    if rho >= 1.0 / target:
        return None, False
    return target * (1.0 - rho) / (1.0 - target * rho), True


def contemporaneity_fraction(rows: Sequence[Any], *, block_bars: int) -> float | None:
    """What share of cross-asset observation pairs are actually contemporaneous.

    **Added after independent review, and it corrects a real error.** ``r_b`` is
    the correlation between two *individual* observations on different assets in
    the same block. `fmis.universe.dependence.effective_clusters` consumes the
    mean pairwise correlation of *cluster-level* series. Those are only the same
    quantity when every admission of one asset is contemporaneous with every
    admission of another — and admissions are scattered over the window, so they
    are not.

    For a mean over ``N`` observations across ``K`` assets, the variance carries
    one ``r_b`` term per **contemporaneous cross-asset pair**, not one per
    cross-asset pair. Writing ``P`` for the number of cross-asset pairs sharing a
    block, the design-relevant between-cluster correlation is ``q * r_b`` with

        q = 2 * P / (N * (K - 1))

    which is the fraction of the equicorrelated model's cross-asset covariance
    terms that are actually present. A Monte-Carlo check over a Milestone
    CA-shaped panel with a known ``r_b`` of 0.20 measures a true design effect of
    1.43 against ``1 + (K-1) * r_b`` = 3.74 and ``1 + (K-1) * q * r_b`` = 1.39.

    `None` when the panel holds fewer than two assets or no observations, which
    is a stated absence rather than a zero.
    """
    require_count(block_bars, "block_bars", minimum=1)
    occupied: dict[str, set[int]] = {}
    total = 0
    for row in rows:
        total += 1
        occupied.setdefault(row.economic_asset, set()).add(
            block_index(int(row.bar_index), block_bars=block_bars)
        )
    assets = sorted(occupied)
    if len(assets) < 2 or total == 0:
        return None
    shared = 0
    for position, left in enumerate(assets):
        for right in assets[position + 1 :]:
            shared += len(occupied[left] & occupied[right])
    return 2.0 * shared / (total * (len(assets) - 1))


def overlap_corrected_correlation(
    rows: Sequence[Any], *, correlation: float | None, block_bars: int
) -> float | None:
    """``q * r_b`` — the correlation the effective-cluster formula actually wants.

    See `contemporaneity_fraction`. `None` when either input is unavailable.
    """
    if correlation is None:
        return None
    fraction = contemporaneity_fraction(rows, block_bars=block_bars)
    if fraction is None:
        return None
    return fraction * float(correlation)


def leave_one_out(
    rows: Sequence[Any], *, axis, block_bars: int, by: str
) -> dict[str, Any]:
    """Re-estimate with each asset, or each block, removed in turn.

    **Added after independent review.** Concentration of *magnitude* — which
    `fmis.paired_dependence.observations.dependence_concentration_of` reports —
    is close to uninformative about the stability of a **variance ratio**. An
    estimate can have an unremarkable largest-contributor share and still move by
    a factor of two when one asset is dropped, and only a leave-one-out sweep
    shows it.

    Raises:
        PairedDependenceError: ``by`` is neither ``"asset"`` nor ``"block"``.
    """
    from fmis.paired_dependence.uncertainty import estimate_on_axis

    if by not in ("asset", "block"):
        raise PairedDependenceError(
            f"leave_one_out drops an asset or a block, not {by!r}"
        )
    if by == "asset":
        keys = sorted({row.economic_asset for row in rows})
        def keep(row, dropped):
            return row.economic_asset != dropped
    else:
        keys = sorted(
            {block_index(int(row.bar_index), block_bars=block_bars) for row in rows}
        )
        def keep(row, dropped):
            return block_index(int(row.bar_index), block_bars=block_bars) != dropped

    readings: list[tuple[str, float | None]] = []
    for dropped in keys:
        subset = [row for row in rows if keep(row, dropped)]
        estimate = estimate_on_axis(subset, axis=axis, block_bars=block_bars)
        readings.append((str(dropped), estimate.correlation))
    defined = [value for _name, value in readings if value is not None]
    return {
        "by": by,
        "dropped": len(keys),
        "minimum": min(defined) if defined else None,
        "maximum": max(defined) if defined else None,
        "spread": (max(defined) - min(defined)) if defined else None,
        "ratio": (
            max(defined) / min(defined)
            if defined and min(defined) not in (0.0, None) and min(defined) > 0.0
            else None
        ),
        "readings": [
            {"dropped": name, "correlation": value} for name, value in readings
        ],
    }
