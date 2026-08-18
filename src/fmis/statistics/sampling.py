"""The `n` guard, and the six reductions every statistic in this package uses.

`AP` §20.7 rule 2 requires the sample guard **at the boundary, so no surface can
route around it**. This module is that boundary: nothing else in the package
divides, averages, takes a median or picks an extremum, so a statistic cannot be
computed without passing through a function that has already decided what to do
about a missing value and a small sample.

**One rule, applied twice, and the distinction is the whole design.**

* A **total** whose contributor is missing is `Absent`. `PortfolioSnapshot`'s own
  rule, generalized by `sum_or_absent` and reused here rather than restated: *"a
  partial total is the most dangerous number a page can show, because it looks
  complete."* Gross profit that quietly omits one winner is wrong, not
  approximate.
* A **distribution** — mean, median, extremum — is computed over the members
  that have the value, and **reports the `n` that contributed**. That is a
  correct statement about a stated population. Refusing it would discard a real
  answer, and computing it silently would let eight simulated excursions stand
  for twelve trades.

**Counts are facts; rates are claims.** `Tally` carries a count and never a
floor: *"you closed three trades and lost on all three"* is true at `n = 3`.
`ratio` and everything built on it consult the `SamplePolicy` first, because a
win rate at `n = 3` is arithmetic about three trades wearing the clothes of a
property of a process.

**The median of an even sample is the mean of the two middle values**, in exact
`Decimal`, and of a `timedelta` sample the mean of the two middle durations. No
interpolation policy beyond that, and none needed: both are exact.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any, Callable, TypeVar

from fmis.money import AssetCode, Money
from fmis.portfolio_risk import sum_or_absent
from fmis.provenance import Absent
from fmis.records import require_int, require_text
from fmis.statistics.models import SamplePolicy, StatisticsRefusedError

__all__ = [
    "Tally",
    "Sample",
    "collect_values",
    "count_of",
    "total_or_absent",
    "mean_or_absent",
    "median_or_absent",
    "extremum_or_absent",
    "mean_duration_or_absent",
    "median_duration_or_absent",
    "ratio_or_absent",
    "share_or_absent",
    "ordered_values",
]

T = TypeVar("T")

_TWO = Decimal(2)


@dataclass(frozen=True, slots=True)
class Tally:
    """A count, and what it is a count of. No floor — a count is a fact.

    `total` is the population the count was taken over, so a reader gets *"4 of
    12"* rather than *"4"*. A bare count of winners with no denominator is the
    number most easily mistaken for a rate.
    """

    subject: str
    count: int
    total: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject", require_text(self.subject, "subject"))
        require_int(self.count, "count", minimum=0)
        require_int(self.total, "total", minimum=0)
        if self.count > self.total:
            raise StatisticsRefusedError(
                f"{self.subject}: a count of {self.count} over a population of "
                f"{self.total} counts members the population does not hold"
            )

    def share(self, policy: SamplePolicy) -> Decimal | Absent:
        """This count as a fraction of its population — a **rate**, so guarded."""
        return share_or_absent(self.count, self.total, self.subject, policy)

    def to_payload(self) -> dict[str, Any]:
        return {"subject": self.subject, "count": self.count, "total": self.total}


@dataclass(frozen=True, slots=True)
class Sample:
    """The values that were stateable, and how many were not.

    Every distributional statistic in this package is computed from one of these
    and reports both numbers, so *"the average MAE of my trades"* is never
    printed when what was measured is the average MAE of the two thirds of them
    that were simulated.
    """

    subject: str
    values: tuple[Any, ...]
    missing: int
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject", require_text(self.subject, "subject"))
        if not isinstance(self.values, tuple):
            raise TypeError("values must be a tuple")
        require_int(self.missing, "missing", minimum=0)
        if not isinstance(self.reasons, tuple):
            raise TypeError("reasons must be a tuple of str")
        for reason in self.reasons:
            require_text(reason, "reason")

    @property
    def size(self) -> int:
        """The `n` that contributed. The number every statistic reports."""
        return len(self.values)

    @property
    def population(self) -> int:
        return self.size + self.missing

    @property
    def is_partial(self) -> bool:
        return self.missing > 0

    @property
    def coverage_note(self) -> str | Absent:
        """What was left out, named — or the absence that says nothing was."""
        if not self.missing:
            return Absent("every trade in this population contributed")
        listed = "; ".join(sorted(set(self.reasons))) or "no reason was recorded"
        return (
            f"{self.size} of {self.population} contributed; {self.missing} did "
            f"not: {listed}"
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "size": self.size,
            "missing": self.missing,
            "population": self.population,
        }


def collect_values(
    items: Iterable[T], read: Callable[[T], Any], subject: str
) -> Sample:
    """Pull one field off every item, keeping the absences and their reasons.

    The single place this package turns *"a field that may be `Absent`"* into a
    population, so the count of what was dropped can never be lost between the
    read and the statistic.
    """
    require_text(subject, "subject")
    values: list[Any] = []
    reasons: list[str] = []
    for item in items:
        value = read(item)
        if isinstance(value, Absent):
            reasons.append(value.reason)
        else:
            values.append(value)
    return Sample(
        subject=subject,
        values=tuple(values),
        missing=len(reasons),
        reasons=tuple(reasons),
    )


def count_of(items: Iterable[T], matches: Callable[[T], bool], subject: str) -> Tally:
    """How many members satisfy a predicate, over how many there were."""
    require_text(subject, "subject")
    members = tuple(items)
    return Tally(
        subject=subject,
        count=sum(1 for item in members if matches(item)),
        total=len(members),
    )


def total_or_absent(
    values: Iterable[Money | Absent], *, asset: AssetCode, subject: str
) -> Money | Absent:
    """A sum that refuses to omit a missing contributor.

    `fmis.portfolio_risk.sum_or_absent`, called rather than reimplemented: the
    rule that a partial total is worse than no total is already written, already
    tested and already load-bearing for the portfolio page, and a second copy of
    it here would be a second place it could be relaxed.
    """
    return sum_or_absent(values, asset=asset, subject=subject)


def mean_or_absent(sample: Sample, policy: SamplePolicy) -> Decimal | Absent:
    """The arithmetic mean of a `Decimal` sample, over the stated `n`.

    **Not floored.** A mean is a description of the values in hand, not a claim
    about a process: *"the three R multiples I have average 0.4"* is exactly
    true. The `n` travels with it in `Sample`, and the surfaces print both.
    """
    _require_sample(sample)
    _require_policy(policy)
    if not sample.values:
        return _empty(sample)
    total = sum(sample.values, Decimal(0))
    return total / Decimal(sample.size)


def median_or_absent(sample: Sample, policy: SamplePolicy) -> Decimal | Absent:
    """The middle value, or the exact mean of the two middle values."""
    _require_sample(sample)
    _require_policy(policy)
    if not sample.values:
        return _empty(sample)
    ordered = sorted(sample.values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / _TWO


def extremum_or_absent(
    sample: Sample, policy: SamplePolicy, *, largest: bool
) -> Any | Absent:
    """The largest or smallest member of a sample.

    `largest` is a keyword rather than two functions because the pair differ by
    one comparison, and two functions is two places for that comparison to be
    written the wrong way round.
    """
    _require_sample(sample)
    _require_policy(policy)
    if not sample.values:
        return _empty(sample)
    if not isinstance(largest, bool):
        raise TypeError("largest must be a bool")
    return max(sample.values) if largest else min(sample.values)


def mean_duration_or_absent(sample: Sample, policy: SamplePolicy) -> Any | Absent:
    """The mean of a `timedelta` sample, exact to the microsecond."""
    _require_sample(sample)
    _require_policy(policy)
    if not sample.values:
        return _empty(sample)
    total = timedelta(0)
    for value in sample.values:
        total = total + value
    return total / sample.size


def median_duration_or_absent(sample: Sample, policy: SamplePolicy) -> Any | Absent:
    """The middle duration, or the mean of the two middle durations."""
    _require_sample(sample)
    _require_policy(policy)
    if not sample.values:
        return _empty(sample)
    ordered = sorted(sample.values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def ratio_or_absent(
    numerator: Decimal,
    denominator: Decimal,
    subject: str,
    sample_size: int,
    policy: SamplePolicy,
) -> Decimal | Absent:
    """A quotient that is a **claim about a process**, and is therefore floored.

    Three refusals, and each is a different fact:

    * below the floor — `InsufficientSample(n)`, carrying `n`;
    * a zero denominator — undefined, and a large number would be the usual
      way profit factor lies when a corpus has no losers;
    * nothing observed at all — absent, never zero.
    """
    require_text(subject, "subject")
    _require_policy(policy)
    require_int(sample_size, "sample_size", minimum=0)
    for name, value in (("numerator", numerator), ("denominator", denominator)):
        if not isinstance(value, Decimal):
            raise TypeError(f"{name} must be a Decimal, got {type(value).__name__}")
    if not policy.admits(sample_size):
        return policy.insufficient(subject, sample_size)
    if denominator == 0:
        return Absent(
            f"{subject} has a denominator of zero over {sample_size} observation(s), "
            "so it is undefined rather than large",
            sample_size=sample_size,
        )
    return numerator / denominator


def share_or_absent(
    count: int, total: int, subject: str, policy: SamplePolicy
) -> Decimal | Absent:
    """A count as a fraction of its population — the rate form of `Tally`."""
    require_int(count, "count", minimum=0)
    require_int(total, "total", minimum=0)
    return ratio_or_absent(
        Decimal(count), Decimal(total), subject, total, policy
    )


def _require_sample(sample: Sample) -> None:
    if not isinstance(sample, Sample):
        raise TypeError(f"sample must be a Sample, got {type(sample).__name__}")


def _require_policy(policy: SamplePolicy) -> None:
    if not isinstance(policy, SamplePolicy):
        raise TypeError(f"policy must be a SamplePolicy, got {type(policy).__name__}")


def _empty(sample: Sample) -> Absent[Any]:
    """No member had the value — absent with the count, never zero."""
    note = sample.coverage_note
    detail = "" if isinstance(note, Absent) else f" ({note})"
    return Absent(
        f"no trade in this population has a stateable {sample.subject}{detail}",
        sample_size=0,
    )


def ordered_values(sample: Sample) -> Sequence[Any]:
    """The sample's values, smallest first. For histograms, which need order."""
    _require_sample(sample)
    return sorted(sample.values)
