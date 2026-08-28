"""The four primitives every estimate here rests on. **Each defined exactly once.**

Three of these already existed inside `fmis.swing_lab`, welded to a trade or to a
milestone. They are **extracted** rather than copied: the laboratory's own
functions now delegate to these, so there is still one seed derivation, one
quantile rule and one share calculation in the repository, and a research package
that must not depend on the swing laboratory can still reach them.

The extraction is behaviour-preserving and is proven that way — the laboratory's
wrappers keep their own exception type and their own message, and regressions
assert the values are identical to what they were.

**Why the seed is a hash and never `hash()`.** Python's built-in `hash` is salted
per process. A study seeded with it would draw different samples on two runs of
the same machine while claiming to be deterministic — the exact failure a
reproducibility claim is supposed to exclude. Every draw here is seeded by
SHA-256 over the draw's own identity, so a draw is a pure function of what it is
drawing for, and no result moves when a caller reorders a loop.

**Why the quantile does not interpolate.** Interpolating between two real
observations reports a value nothing in the sample ever took. The rank is rounded
and a real element is returned.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from statistics import NormalDist
from typing import Any

from fmis.research_design.models import ResearchDesignError

__all__ = [
    "derive_seed",
    "nearest_rank_quantile",
    "largest_share",
    "two_sided_z",
    "one_sided_z",
]

_STANDARD_NORMAL = NormalDist()


def derive_seed(*, master: int, parts: Sequence[Any]) -> int:
    """A draw's seed, derived from its identity. **Never from iteration order.**

    SHA-256 over the UTF-8 of ``master`` and ``parts`` joined by ``|``, truncated
    to 64 bits. `fmis.swing_lab.admission_matching.derive_seed` is this function
    with Milestone CA's own identity fields, and calls it, so CA's control draws
    are unchanged by the extraction.

    Raises:
        ResearchDesignError: ``master`` is not an int, or ``parts`` is empty or
            holds a value whose text form contains the ``|`` separator — which
            would let two different identities collide on one seed.
    """
    if isinstance(master, bool) or not isinstance(master, int):
        raise ResearchDesignError("master must be an int")
    items = list(parts)
    if not items:
        raise ResearchDesignError(
            "parts must name what is being drawn; a seed derived from the master "
            "alone is the same seed for every draw in the study"
        )
    rendered = [str(item) for item in items]
    for item in rendered:
        if "|" in item:
            raise ResearchDesignError(
                f"seed identity part {item!r} contains the {'|'!r} separator, so two "
                "different identities could join to one string and share a seed"
            )
    identity = "|".join([str(master), *rendered])
    digest = hashlib.sha256(identity.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def nearest_rank_quantile(values: Sequence, fraction: float):
    """A nearest-rank quantile. **No interpolation between two real observations.**

    Generic over anything sortable. ``None`` for an empty sequence — a stated
    absence, never a zero.

    Raises:
        ResearchDesignError: ``fraction`` is outside [0, 1].
    """
    if not isinstance(fraction, (int, float)) or isinstance(fraction, bool):
        raise ResearchDesignError("fraction must be a real number")
    if not 0.0 <= fraction <= 1.0:
        raise ResearchDesignError(f"fraction must lie in [0, 1], got {fraction}")
    if not values:
        return None
    ordered = sorted(values)
    index = int(fraction * (len(ordered) - 1) + 0.5)
    return ordered[min(index, len(ordered) - 1)]


def largest_share(contributions: Iterable[tuple[str, Any]]):
    """The largest single label's share of a total magnitude. **The formula, once.**

    ``None`` when nothing contributed any magnitude at all, which is a stated
    absence rather than a zero share. Generic over `Decimal` and `float` so that
    a milestone measuring trades in exact R and one measuring paired differences
    in floating-point ATR read the same definition.

    Raises:
        ResearchDesignError: a contribution is negative. A share of a total is
            taken over absolute contributions, and a negative one would let a
            numerator exceed its own denominator.
    """
    totals: dict[str, Any] = {}
    grand: Any = 0
    for label, magnitude in contributions:
        if magnitude < 0:
            raise ResearchDesignError(
                f"cohort {label!r} contributed a negative magnitude {magnitude}; "
                "a share of a total must be taken over absolute contributions"
            )
        totals[label] = totals.get(label, 0) + magnitude
        grand += magnitude
    if grand == 0:
        return None
    return max(totals.values()) / grand


def two_sided_z(confidence: float) -> float:
    """The standard-normal multiplier for a two-sided interval at ``confidence``.

    Used **only** where a normal approximation is declared as an assumption. The
    empirical estimators in `fmis.research_design.resolution` do not consult it;
    they read their bounds off resampled quantiles.

    Raises:
        ResearchDesignError: ``confidence`` is not strictly inside (0, 1).
    """
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ResearchDesignError("confidence must be a real number")
    value = float(confidence)
    if not 0.0 < value < 1.0:
        raise ResearchDesignError(
            f"confidence must lie strictly inside (0, 1), got {confidence}"
        )
    return _STANDARD_NORMAL.inv_cdf(1.0 - (1.0 - value) / 2.0)


def one_sided_z(probability: float) -> float:
    """The standard-normal quantile at ``probability``. The power term's multiplier.

    Raises:
        ResearchDesignError: ``probability`` is not strictly inside (0, 1).
    """
    if isinstance(probability, bool) or not isinstance(probability, (int, float)):
        raise ResearchDesignError("probability must be a real number")
    value = float(probability)
    if not 0.0 < value < 1.0:
        raise ResearchDesignError(
            f"probability must lie strictly inside (0, 1), got {probability}"
        )
    return _STANDARD_NORMAL.inv_cdf(value)
