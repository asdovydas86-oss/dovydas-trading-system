"""How much of a bigger universe is actually *new*. **The core of Milestone CC.**

Milestone CB established that raw symbol count is not information, and left the
intracluster correlation unspecified because Milestone CA's observation-level data
does not exist in this repository. CC closes as much of that gap as can honestly
be closed, and is explicit about the part that cannot.

**The quantity that matters, and why it is not the obvious one.**

Crypto assets co-move. If the between-asset correlation of the estimand is
``r``, then ``K`` assets do not supply ``K`` independent clusters; they supply

    K_eff = K / (1 + (K - 1) * r)

which is the design effect for an equicorrelated mean, applied along the cluster
axis rather than inside a cluster. Its behaviour is the whole story: it rises
linearly while ``K * r`` is small and then **saturates at ``1 / r``**, however many
assets are added. At ``r = 0.5`` a thousand assets supply two effective clusters.

**But ``r`` measured on raw returns is not the estimand's ``r``.** Milestone CA's
effect is a *paired within-symbol difference* — an admitted instant against a
volatility-matched control on the same symbol in the same period. The market-wide
factor that dominates raw crypto return correlation is very largely differenced
out of such a comparison. Using raw correlation as if it were the estimand's would
overstate dependence, possibly by a great deal, and would manufacture an
`INFEASIBLE` verdict out of an inapplicable number.

So this module measures **three** things and forces none of them to be the answer:

* `raw_mean_correlation` — mean pairwise correlation of daily log returns. An
  **upper bound** on dependence for a paired estimand.
* `residual_mean_correlation` — the same, after the equal-weight cross-sectional
  market factor is removed from every asset. The closest
  strategy-outcome-independent **proxy** for what a paired difference retains.
* `market_factor_share` — the first eigenvalue's share of total variance, which
  says how much of the co-movement the single market factor accounts for and
  therefore how much the residual step actually removed.

The lower bound is zero, which is exactly the assumption Milestone CA's ~4,800
figure makes. `fmis.universe.growth` reports every design figure at all three, and
the verdict rule reads the residual scenario as primary and the other two as the
bracket around it.

**Nothing here reads a strategy outcome.** Correlation is measured between price
returns, which exist whether or not the strategy ever ran. A control asserts that
this module imports nothing from `fmis.swing_lab` and that permuting every trade
result in the repository leaves its output unchanged.

**Standard library only.** No numpy. The eigenvalue is obtained by power
iteration over the correlation matrix with a deterministic starting vector, which
for a matrix whose leading eigenvector is the near-uniform market direction
converges in tens of iterations and needs no external dependency.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from fmis.universe.models import UniverseError, require_count, require_text

__all__ = [
    "MIN_OVERLAP_DAYS",
    "POST_REVIEW_LIMITATIONS",
    "POWER_ITERATIONS",
    "DependenceSummary",
    "log_returns",
    "aligned_returns",
    "pearson",
    "market_residuals",
    "effective_clusters",
    "measure_dependence",
    "correlated_groups",
]

#: What an independent review established about this module **after** the CC
#: pre-registration was sealed.
#:
#: These are deliberately **not** added to `CC_LIMITATIONS`, which is part of the
#: sealed payload: retro-fitting a seal with what was learned later would destroy
#: the only property a seal has. They are carried separately, reported separately,
#: and dated to the review rather than to the pre-registration.
POST_REVIEW_LIMITATIONS: Final[tuple[str, ...]] = (
    "CC-7 — THE SEALED RESIDUAL SCENARIO CANNOT MEASURE RESIDUAL DEPENDENCE. "
    "Cross-sectional demeaning removes any exchangeable common component exactly: "
    "for x_i = f + e_i with corr(e_i, e_j) = rho_e, the demeaned residuals have "
    "pairwise correlation exactly -1/(K-1) for EVERY rho_e. Verified by simulation "
    "at rho_e = 0.0, 0.2, 0.5 and 0.8, all returning an excess of 0.00000. The "
    "measured excess therefore quantifies departure from exchangeability, NOT the "
    "level of residual dependence, and the three sealed scenarios do not bracket "
    "the answer as the pre-registration claims. The usable bracket is "
    "[independent = 0, raw = 0.604] with no informative middle.",
    "CC-8 — A VERY SMALL RESIDUAL DEPENDENCE WOULD BE DECISIVE, AND CANNOT BE "
    "RULED OUT. Because the effective cluster count saturates at 1/r, the "
    "half-width floor is z*sigma*sqrt(r/(years*density)) and a between-asset "
    "correlation of ORDER 0.002 puts it above the +0.10 bar, making the effect "
    "unreachable at ANY universe size; the break-even value is r = 0.00214. CC-7 "
    "means no measurement here can exclude a correlation of that order. NOTE the "
    "measured residual excess (+0.0023) is NOT a measured between-asset "
    "correlation and exceeds break-even by only 5.9 %, a margin that does not "
    "survive the +/-30 % scatter limitation CB-6 places on the input interval. The "
    "supported claim is therefore the CONDITIONAL one. It strengthens the "
    "INFEASIBLE verdict rather than weakening it, and is reported because it was "
    "found, not because it helps.",
    "CC-9 — THE LEADING-EIGENVALUE SHARE IS GUARDED, NOT UNIVERSAL. Power "
    "iteration from a uniform start finds the dominant eigenvector only when the "
    "two are not orthogonal. It is sound here because all 703 measured pairwise "
    "correlations are non-negative (Perron-Frobenius), and a converged value below "
    "1 is now refused as impossible for a correlation matrix. A universe including "
    "genuinely anti-correlated instruments would report no share rather than a "
    "wrong one.",
)

#: The fewest overlapping observations a pair of assets must share for their
#: correlation to be counted. Sixty daily bars. A correlation from a handful of
#: overlapping days is dominated by its own standard error, and averaging such
#: pairs into a mean would import that noise as if it were structure.
MIN_OVERLAP_DAYS: Final[int] = 60

#: Power-iteration steps for the leading eigenvalue. Fixed rather than
#: convergence-tested so the result is a deterministic function of the input: a
#: tolerance-based loop would run a different number of steps on a different
#: machine's floating point and report a different last digit.
POWER_ITERATIONS: Final[int] = 200


def log_returns(closes: Sequence[float]) -> tuple[float, ...]:
    """Log returns of a close series. **Refuses a non-positive price.**

    A zero or negative close has no log return, and skipping it silently would
    join two non-adjacent days into one return that no market produced.
    """
    out: list[float] = []
    previous: float | None = None
    for value in closes:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise UniverseError("every close must be a real number")
        price = float(value)
        if price <= 0.0:
            raise UniverseError(
                f"a close of {price} cannot be a traded price; its log return is "
                "undefined and skipping it would fabricate an adjacency"
            )
        if previous is not None:
            out.append(math.log(price / previous))
        previous = price
    return tuple(out)


def aligned_returns(
    series: Mapping[str, Mapping[Any, float]]
) -> tuple[tuple[Any, ...], dict[str, dict[Any, float]]]:
    """Index the return series by instant so pairs can be aligned exactly.

    Returned as a sorted tuple of every instant seen and the per-asset maps, so a
    pair's overlap is an intersection rather than a positional assumption. Two
    assets whose histories start on different days must **not** be correlated
    position-by-position; that would align an asset's first week against another's
    third year.
    """
    instants: set[Any] = set()
    out: dict[str, dict[Any, float]] = {}
    for name, values in series.items():
        require_text(name, "asset name")
        out[name] = dict(values)
        instants.update(out[name])
    return tuple(sorted(instants)), out


def pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    """Pearson correlation, or `None` when it is undefined.

    `None` — not zero — when either series has zero variance. A constant series
    is uncorrelated with nothing; it has no correlation at all, and reporting zero
    would let a peg dilute a mean correlation downward.
    """
    if len(left) != len(right):
        raise UniverseError("pearson needs two series of equal length")
    if len(left) < 2:
        return None
    mean_left = statistics.fmean(left)
    mean_right = statistics.fmean(right)
    covariance = 0.0
    var_left = 0.0
    var_right = 0.0
    for a, b in zip(left, right):
        da = a - mean_left
        db = b - mean_right
        covariance += da * db
        var_left += da * da
        var_right += db * db
    if var_left <= 0.0 or var_right <= 0.0:
        return None
    return covariance / math.sqrt(var_left * var_right)


def market_residuals(
    instants: Sequence[Any], series: Mapping[str, Mapping[Any, float]]
) -> dict[str, dict[Any, float]]:
    """Remove the equal-weight cross-sectional market factor from every asset.

    On each instant the market factor is the **mean return across every asset that
    traded that day**, and each asset's residual is its return minus that mean.
    This is the crudest possible one-factor removal and it is chosen for exactly
    that reason: it estimates nothing, fits nothing, and cannot overfit. A
    regression-based removal would estimate a beta per asset from the same data
    the residual correlation is then measured on, and the shrinkage that induces
    would understate the residual correlation — biasing CC toward a more
    favourable answer than the data supports.

    Days on which fewer than two assets traded produce no factor and are dropped:
    a "market" of one asset is that asset, and subtracting it would zero the
    series by construction.
    """
    factor: dict[Any, float] = {}
    for instant in instants:
        values = [
            values_for[instant]
            for values_for in series.values()
            if instant in values_for
        ]
        if len(values) >= 2:
            factor[instant] = statistics.fmean(values)
    return {
        name: {
            instant: value - factor[instant]
            for instant, value in values_for.items()
            if instant in factor
        }
        for name, values_for in series.items()
    }


def effective_clusters(clusters: int, correlation: float) -> float:
    """``K / (1 + (K - 1) * r)``. **The number that saturates.**

    At ``r = 0`` this is ``K`` and every asset is an experiment. At ``r > 0`` it
    approaches ``1 / r`` from below and no quantity of additional assets passes
    that ceiling — which is the single most consequential fact Milestone CC has to
    report, because it means the answer to *"how many symbols do we need"* can be
    *"no number of them is enough"*.

    Raises:
        UniverseError: ``clusters`` is below 1, or ``correlation`` is outside
            [0, 1]. A negative mean correlation across a large universe is not
            physically reachable (the mean pairwise correlation of ``K`` series is
            bounded below by ``-1/(K-1)``) and would produce an effective count
            above ``K``, claiming that co-movement *added* independent clusters.
    """
    count = require_count(clusters, "clusters", minimum=1)
    if isinstance(correlation, bool) or not isinstance(correlation, (int, float)):
        raise UniverseError("correlation must be a real number")
    rho = float(correlation)
    if rho != rho:
        raise UniverseError("correlation must be a real number, got NaN")
    if not 0.0 <= rho <= 1.0:
        raise UniverseError(
            f"correlation must lie in [0, 1] for an effective-cluster count, got "
            f"{rho}. A negative value would report more effective clusters than "
            "there are assets, which would claim co-movement created information"
        )
    return count / (1.0 + (count - 1) * rho)


@dataclass(frozen=True, slots=True)
class DependenceSummary:
    """Everything CC measured about co-movement. **Three numbers, not one.**

    ``residual_mean_correlation`` is the scenario the verdict reads as primary;
    the other two bracket it. None of them is the correlation of the paired
    admission effect itself, which cannot be measured without the outcomes CC
    exists to decide whether to acquire — see limitation CC-1.
    """

    assets: int
    pairs_measured: int
    pairs_skipped: int
    raw_mean_correlation: float | None
    raw_median_correlation: float | None
    residual_mean_correlation: float | None
    residual_median_correlation: float | None
    demeaning_artefact: float | None
    market_factor_share: float | None
    highest_decile_correlation: float | None
    window_days: int
    method: str

    def __post_init__(self) -> None:
        require_count(self.assets, "assets")
        require_count(self.pairs_measured, "pairs_measured")
        require_count(self.pairs_skipped, "pairs_skipped")
        require_count(self.window_days, "window_days")
        require_text(self.method, "method")

    @property
    def is_measured(self) -> bool:
        """Whether a dependence estimate could be formed at all."""
        return self.pairs_measured > 0 and self.residual_mean_correlation is not None

    @property
    def residual_excess_over_artefact(self) -> float | None:
        """Measured residual correlation **minus the artefact demeaning creates**.

        Subtracting the cross-sectional mean from ``K`` series induces a pairwise
        correlation of exactly ``-1 / (K - 1)`` even when the underlying series
        are perfectly independent — the residuals are constrained to sum to zero
        on every instant, so they cannot all be free. A measured residual
        correlation must therefore be read **against** that floor and never
        against zero.

        **What this can and cannot tell you — established by review, after sealing.**
        Cross-sectional demeaning removes *any* exchangeable common component
        **exactly**. For ``K`` series ``x_i = f + e_i`` whose idiosyncratic parts are
        equicorrelated at any level ``rho_e``, the demeaned residuals have pairwise
        correlation exactly ``-1/(K-1)`` — algebraically, and confirmed by
        simulation at ``rho_e`` of 0.0, 0.2, 0.5 and 0.8, all of which return an
        excess of 0.00000. So this quantity does **not** measure the *level* of
        residual dependence; it measures departure from exchangeability. A reading
        of zero is consistent with residual dependence of any magnitude, and the
        sealed residual scenario therefore does not bracket the answer in the way
        the pre-registration claims. See `POST_REVIEW_LIMITATIONS`.
        """
        if self.residual_mean_correlation is None or self.demeaning_artefact is None:
            return None
        return self.residual_mean_correlation - self.demeaning_artefact

    def correlation_for(self, scenario: str) -> float:
        """The correlation one sealed scenario uses.

        Raises:
            UniverseError: the scenario is unknown, or the measurement it names
                was not taken. A missing measurement is never silently read as
                zero — that would be the most favourable possible substitution.
        """
        if scenario == "independent":
            return 0.0
        if scenario == "residual":
            # **The SEALED quantity, deliberately.** The pre-registration defines
            # the residual scenario as "the measured mean pairwise correlation of
            # daily log returns AFTER the equal-weight market factor is removed",
            # which is this field and not the artefact-corrected excess. An
            # independent review proposed substituting the excess; that was
            # REJECTED, because changing what a sealed scenario computes after
            # seeing its result is precisely what a seal exists to prevent. The
            # excess is reported beside it as a diagnostic, and the consequence of
            # reading it instead is reported as a labelled post-hoc sensitivity.
            value = self.residual_mean_correlation
        elif scenario == "raw":
            value = self.raw_mean_correlation
        else:
            raise UniverseError(
                f"unknown dependence scenario {scenario!r}; this study seals "
                "'independent', 'residual' and 'raw'"
            )
        if value is None:
            raise UniverseError(
                f"the {scenario!r} dependence scenario has no measurement. "
                "Substituting zero would silently apply the most favourable "
                "assumption available"
            )
        # A negative mean correlation is arithmetically possible in a small
        # sample and is clamped to zero rather than propagated: it would report
        # MORE effective clusters than assets, which no co-movement can create.
        return max(0.0, value)

    def payload(self) -> dict[str, Any]:
        return {
            "assets": self.assets,
            "pairs_measured": self.pairs_measured,
            "pairs_skipped": self.pairs_skipped,
            "raw_mean_correlation": self.raw_mean_correlation,
            "raw_median_correlation": self.raw_median_correlation,
            "residual_mean_correlation": self.residual_mean_correlation,
            "residual_median_correlation": self.residual_median_correlation,
            "demeaning_artefact": self.demeaning_artefact,
            "residual_excess_over_artefact": self.residual_excess_over_artefact,
            "market_factor_share": self.market_factor_share,
            "highest_decile_correlation": self.highest_decile_correlation,
            "window_days": self.window_days,
            "method": self.method,
        }


def _mean_pairwise(
    names: Sequence[str], series: Mapping[str, Mapping[Any, float]]
) -> tuple[list[float], int]:
    """Every pairwise correlation with enough overlap, and how many were skipped."""
    values: list[float] = []
    skipped = 0
    for index, left in enumerate(names):
        left_values = series[left]
        for right in names[index + 1 :]:
            right_values = series[right]
            shared = sorted(left_values.keys() & right_values.keys())
            if len(shared) < MIN_OVERLAP_DAYS:
                skipped += 1
                continue
            correlation = pearson(
                [left_values[i] for i in shared], [right_values[i] for i in shared]
            )
            if correlation is None:
                skipped += 1
                continue
            values.append(correlation)
    return values, skipped


def _leading_eigenvalue_share(
    names: Sequence[str], series: Mapping[str, Mapping[Any, float]]
) -> float | None:
    """The first eigenvalue's share of total variance, by power iteration.

    Returns `None` when the correlation matrix cannot be completed — a pair with
    too little overlap leaves a hole, and filling it with zero would understate
    the market factor by asserting an independence that was not measured.
    """
    size = len(names)
    if size < 2:
        return None
    matrix: list[list[float]] = [[0.0] * size for _ in range(size)]
    for i in range(size):
        matrix[i][i] = 1.0
    for i in range(size):
        for j in range(i + 1, size):
            left, right = series[names[i]], series[names[j]]
            shared = sorted(left.keys() & right.keys())
            if len(shared) < MIN_OVERLAP_DAYS:
                return None
            correlation = pearson(
                [left[k] for k in shared], [right[k] for k in shared]
            )
            if correlation is None:
                return None
            matrix[i][j] = matrix[j][i] = correlation

    vector = [1.0 / math.sqrt(size)] * size
    eigenvalue = 0.0
    for _ in range(POWER_ITERATIONS):
        product = [
            sum(matrix[i][j] * vector[j] for j in range(size)) for i in range(size)
        ]
        norm = math.sqrt(sum(value * value for value in product))
        if norm <= 0.0:  # pragma: no cover - a correlation matrix has unit trace
            return None
        vector = [value / norm for value in product]
        eigenvalue = norm
    # **Convergence is checked, not assumed.** A uniform start vector finds the
    # dominant eigenvector only when the two are not orthogonal. For an
    # all-non-negative correlation matrix Perron-Frobenius guarantees a strictly
    # positive dominant eigenvector, so the overlap is non-zero and the iteration
    # is sound — which is the case for every universe measured here (703 of 703
    # pairwise correlations non-negative, minimum 0.2276). It is NOT guaranteed in
    # general: an independent review supplied a two-block matrix with intra-block
    # +0.9 and inter-block -0.9 whose dominant eigenvector is exactly orthogonal to
    # uniform, on which this loop silently returns a share 55x too small.
    #
    # The detector is exact and costs nothing. A correlation matrix has trace
    # `size`, so its eigenvalues average exactly 1 and the LARGEST is therefore
    # always >= 1. A converged value below 1 cannot be the dominant eigenvalue, so
    # the iteration has landed on a subdominant one and `None` — "not measured" —
    # is the only honest answer.
    if eigenvalue < 1.0:
        return None
    # The trace of a correlation matrix is exactly its dimension.
    return eigenvalue / size


def measure_dependence(
    series: Mapping[str, Sequence[float]],
    *,
    instants: Mapping[str, Sequence[Any]],
    window_days: int,
) -> DependenceSummary:
    """Measure co-movement across a universe. **Returns, never outcomes.**

    ``series`` maps an asset id to its closes and ``instants`` maps the same id to
    the matching bar times, so returns are aligned by instant rather than by
    position. Every asset with fewer than three closes is dropped, because a
    single return has no correlation.
    """
    require_count(window_days, "window_days")
    returns: dict[str, dict[Any, float]] = {}
    for name, closes in series.items():
        stamps = instants.get(name)
        if stamps is None or len(stamps) != len(closes):
            raise UniverseError(
                f"{name}: {len(closes)} close(s) against "
                f"{0 if stamps is None else len(stamps)} instant(s); a return "
                "series that cannot be dated cannot be aligned against another"
            )
        if len(closes) < 3:
            continue
        values = log_returns(closes)
        # A return is dated by the bar it ENDS on, so it pairs with stamps[1:].
        returns[name] = dict(zip(stamps[1:], values))

    names = sorted(returns)
    ordered_instants, indexed = aligned_returns(returns)
    residual = market_residuals(ordered_instants, indexed)

    raw_values, raw_skipped = _mean_pairwise(names, indexed)
    residual_values, residual_skipped = _mean_pairwise(names, residual)

    def summarise(values: list[float]) -> tuple[float | None, float | None]:
        if not values:
            return None, None
        return statistics.fmean(values), statistics.median(values)

    raw_mean, raw_median = summarise(raw_values)
    residual_mean, residual_median = summarise(residual_values)

    top_decile: float | None = None
    if len(raw_values) >= 10:
        ordered = sorted(raw_values)
        top_decile = ordered[int(len(ordered) * 0.9)]

    return DependenceSummary(
        assets=len(names),
        pairs_measured=len(raw_values),
        pairs_skipped=raw_skipped,
        raw_mean_correlation=raw_mean,
        raw_median_correlation=raw_median,
        residual_mean_correlation=residual_mean,
        residual_median_correlation=residual_median,
        demeaning_artefact=(-1.0 / (len(names) - 1)) if len(names) > 1 else None,
        market_factor_share=_leading_eigenvalue_share(names, indexed),
        highest_decile_correlation=top_decile,
        window_days=window_days,
        method=(
            "Pearson correlation of daily log returns, aligned by instant, over "
            f"pairs sharing at least {MIN_OVERLAP_DAYS} days. The residual series "
            "removes the equal-weight cross-sectional mean return per day — an "
            "unfitted one-factor removal, chosen because a regressed beta would "
            "shrink the residual correlation using the same data it is then "
            "measured on. The residual mean must be read against "
            "demeaning_artefact = -1/(K-1), which cross-sectional demeaning "
            "induces even among perfectly independent series, NOT against zero. "
            "Correlations are between PRICE RETURNS and no strategy outcome "
            "enters any figure here"
        ),
    )


def correlated_groups(
    series: Mapping[str, Mapping[Any, float]], *, threshold: float
) -> tuple[tuple[str, ...], ...]:
    """Single-linkage groups of assets correlated above ``threshold``.

    Deliberately **not** a labelled taxonomy. Calling a set of tickers "L1" or
    "DeFi" and then reporting that they co-move is an assertion dressed as a
    measurement; single linkage over a measured correlation lets the data draw the
    groups, and lets it disagree with any label a reader had in mind.

    Groups come back sorted by descending size then by first member, and members
    are sorted, so the result never depends on the input's ordering.
    """
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise UniverseError("threshold must be a real number")
    bar = float(threshold)
    if not -1.0 <= bar <= 1.0:
        raise UniverseError(f"threshold must lie in [-1, 1], got {bar}")

    names = sorted(series)
    parent = {name: name for name in names}

    def find(name: str) -> str:
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            shared = sorted(series[left].keys() & series[right].keys())
            if len(shared) < MIN_OVERLAP_DAYS:
                continue
            correlation = pearson(
                [series[left][k] for k in shared], [series[right][k] for k in shared]
            )
            if correlation is not None and correlation >= bar:
                a, b = find(left), find(right)
                if a != b:
                    parent[a] = b

    buckets: dict[str, list[str]] = {}
    for name in names:
        buckets.setdefault(find(name), []).append(name)
    groups = [tuple(sorted(members)) for members in buckets.values() if len(members) > 1]
    return tuple(sorted(groups, key=lambda item: (-len(item), item)))
