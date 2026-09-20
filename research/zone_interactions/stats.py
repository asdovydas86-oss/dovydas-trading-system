"""The inference this gate is allowed to use, in pure Python.

Three tools, and the preregistration (§7) fixes all three:

  * **the symbol is the unit** — never the event. 153,148 events came from
    9,881 bands and 36 symbols, so an interval computed over the event count
    would be a statement about arithmetic rather than about markets;
  * **a paired signed-rank test** across symbols, because each symbol supplies
    its own difference and symbols are not exchangeable with one another;
  * **a cluster bootstrap** resampling *symbols*, seeded at 20260920, fixed in
    the preregistration before any number existed.

Normal approximations are used where noted, and where they are used the
sample is ≥ 15 clusters. None of this manufactures precision the design does
not have: every table that reports an interval also reports the cluster count
that produced it.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence

#: §7.2, sealed before results.
BOOTSTRAP_SEED = 20260920
BOOTSTRAP_DRAWS = 2000


def rate(hits: int, total: int) -> float | None:
    return (hits / total) if total else None


def wilcoxon_signed_rank(differences: Sequence[float]) -> tuple[float, int]:
    """Two-sided signed-rank test over per-symbol differences.

    Zero differences are dropped, ties share an average rank, and the normal
    approximation carries a continuity correction and a tie correction.
    Returns `(p, n)` where `n` is the number of non-zero pairs actually used —
    reported everywhere alongside the p-value, because a p-value over nine
    clusters is a different object from one over thirty-six.
    """
    values = [d for d in differences if d != 0.0]
    n = len(values)
    if n < 6:
        return float("nan"), n

    order = sorted(range(n), key=lambda i: abs(values[i]))
    ranks = [0.0] * n
    i = 0
    tie_correction = 0.0
    while i < n:
        j = i
        while j + 1 < n and abs(values[order[j + 1]]) == abs(values[order[i]]):
            j += 1
        average = (i + j) / 2.0 + 1.0
        size = j - i + 1
        if size > 1:
            tie_correction += size**3 - size
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1

    w_plus = sum(r for r, v in zip(ranks, values) if v > 0)
    mean = n * (n + 1) / 4.0
    var = n * (n + 1) * (2 * n + 1) / 24.0 - tie_correction / 48.0
    if var <= 0:
        return float("nan"), n
    z = (abs(w_plus - mean) - 0.5) / math.sqrt(var)
    p = 2.0 * (1.0 - _normal_cdf(z))
    return min(1.0, max(0.0, p)), n


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def cluster_bootstrap(
    clusters: Sequence[object],
    statistic: Callable[[Sequence[object]], float | None],
    *,
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float | None, float | None, float | None]:
    """Percentile interval and a two-sided p against 0, resampling *clusters*.

    ``clusters`` is one opaque bundle per symbol; ``statistic`` reduces a
    resampled collection of bundles to one number. Resampling whole symbols is
    what keeps the interval honest when one symbol contributes 9,000 correlated
    events and another contributes 40.
    """
    if len(clusters) < 3:
        return None, None, None
    rng = random.Random(seed)
    size = len(clusters)
    values: list[float] = []
    for _ in range(draws):
        sample = [clusters[rng.randrange(size)] for _ in range(size)]
        value = statistic(sample)
        if value is not None and value == value:
            values.append(value)
    if len(values) < draws // 10:
        return None, None, None
    values.sort()
    lo = values[int(0.025 * len(values))]
    hi = values[min(len(values) - 1, int(0.975 * len(values)))]
    below = sum(1 for v in values if v <= 0.0)
    above = sum(1 for v in values if v >= 0.0)
    p = min(1.0, 2.0 * min(below, above) / len(values))
    return lo, hi, p


def holm(pairs: Sequence[tuple[str, float]]) -> dict[str, float]:
    """Holm step-down adjustment within one preregistered family (§7.5)."""
    usable = [(k, p) for k, p in pairs if p == p]
    usable.sort(key=lambda kv: kv[1])
    m = len(usable)
    out: dict[str, float] = {}
    running = 0.0
    for i, (key, p) in enumerate(usable):
        adjusted = min(1.0, (m - i) * p)
        running = max(running, adjusted)
        out[key] = running
    for key, p in pairs:
        if p != p:
            out[key] = float("nan")
    return out
