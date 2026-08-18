"""Distributions — where the results actually fell, not just where they averaged.

A mean of `+0.1 R` over twenty trades is the same number whether every trade
finished near zero or nineteen lost a full R and one made twenty. `SPEC` §4
requires distribution over point estimates for exactly that reason, and `BD`'s
own finding — that a mean hides a clustered outcome — is why this module exists
rather than a single average being considered sufficient.

**The bucket edges are fixed and named, never derived from the data.** A
histogram whose bins are chosen from the sample changes shape when one trade is
added, so two runs a week apart are not comparable and a striking-looking bin is
an artefact of the binning. The edges here are declared constants, chosen once
around the values a swing trader's results actually take, and the same edges are
used at every `n`.

**An empty bucket is rendered, not dropped.** The gaps in a distribution are the
information: three trades at `-1 R`, nothing between, two at `+3 R` is a
different system from five trades spread evenly, and a renderer that skipped the
empty middle would draw them identically.

**Values outside the outermost edges land in the open-ended buckets**, which are
labelled as open-ended. Clamping them into the last closed bucket would make the
tail — the part that decides whether a system survives — invisible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from fmis.money import canonical_decimal_text
from fmis.records import require_int, require_text
from fmis.statistics.models import StatisticsRefusedError
from fmis.statistics.sampling import Sample

__all__ = [
    "Bucket",
    "Histogram",
    "histogram_of",
    "R_MULTIPLE_EDGES",
    "HOLDING_TIME_EDGES",
    "HISTOGRAM_KINDS",
]

#: The R-multiple bins, in R. Chosen around the values that mean something to a
#: trader rather than around the data: a full stop-out, a partial loss, a
#: scratch, and the multiples of the risk above it.
R_MULTIPLE_EDGES: tuple[Decimal, ...] = (
    Decimal("-2"),
    Decimal("-1"),
    Decimal("-0.5"),
    Decimal("0"),
    Decimal("0.5"),
    Decimal("1"),
    Decimal("2"),
    Decimal("3"),
)

#: The holding-time bins, in days, for a **swing** trading system. A position
#: held under a day and one held over a month are different trades under the
#: same name, and `SPEC` §10 scopes this product to the days-to-weeks band.
HOLDING_TIME_EDGES: tuple[Decimal, ...] = (
    Decimal("1"),
    Decimal("3"),
    Decimal("7"),
    Decimal("14"),
    Decimal("30"),
)

#: What a histogram may be built over, and the edges each one uses.
HISTOGRAM_KINDS: dict[str, tuple[Decimal, ...]] = {
    "r_multiple": R_MULTIPLE_EDGES,
    "holding_time": HOLDING_TIME_EDGES,
}

_SECONDS_PER_DAY = Decimal(60 * 60 * 24)


@dataclass(frozen=True, slots=True)
class Bucket:
    """One bin: its bounds, its label, and how many landed in it.

    `lower` and `upper` are `None` at the open ends rather than a sentinel
    number, so a reader cannot mistake the outermost bin's bound for a value the
    data reached.
    """

    label: str
    lower: Decimal | None
    upper: Decimal | None
    count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", require_text(self.label, "label"))
        for name in ("lower", "upper"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal or None")
        require_int(self.count, "count", minimum=0)
        if (
            self.lower is not None
            and self.upper is not None
            and self.lower >= self.upper
        ):
            raise StatisticsRefusedError(
                f"bucket {self.label!r} has a lower bound at or above its upper "
                "bound, so nothing can fall inside it"
            )
        if self.lower is None and self.upper is None:
            raise StatisticsRefusedError(
                "a bucket open at both ends is the whole population and is not a "
                "bucket"
            )

    @property
    def is_open_ended(self) -> bool:
        return self.lower is None or self.upper is None

    def to_payload(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "lower": None if self.lower is None else canonical_decimal_text(self.lower),
            "upper": None if self.upper is None else canonical_decimal_text(self.upper),
            "count": self.count,
        }


@dataclass(frozen=True, slots=True)
class Histogram:
    """Every bucket, in order, plus what the population was and what was missing.

    `missing` travels with the buckets rather than beside them: a distribution
    over eight of twelve trades that did not say so would be read as the shape
    of all twelve.
    """

    kind: str
    unit: str
    buckets: tuple[Bucket, ...]
    size: int
    missing: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", require_text(self.kind, "kind"))
        object.__setattr__(self, "unit", require_text(self.unit, "unit"))
        if not isinstance(self.buckets, tuple) or not self.buckets:
            raise TypeError("buckets must be a non-empty tuple of Bucket")
        for bucket in self.buckets:
            if not isinstance(bucket, Bucket):
                raise TypeError("every bucket must be a Bucket")
        require_int(self.size, "size", minimum=0)
        require_int(self.missing, "missing", minimum=0)
        counted = sum(bucket.count for bucket in self.buckets)
        if counted != self.size:
            raise StatisticsRefusedError(
                f"the buckets hold {counted} value(s) but the sample had "
                f"{self.size}; a histogram that dropped one would draw a shape the "
                "data does not have"
            )

    @property
    def population(self) -> int:
        return self.size + self.missing

    @property
    def is_empty(self) -> bool:
        return self.size == 0

    @property
    def peak(self) -> int:
        """The tallest bucket's count — what a bar chart scales against."""
        return max(bucket.count for bucket in self.buckets)

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "unit": self.unit,
            "size": self.size,
            "missing": self.missing,
            "buckets": [bucket.to_payload() for bucket in self.buckets],
        }


def _buckets_for(edges: tuple[Decimal, ...]) -> tuple[tuple[str, Decimal | None, Decimal | None], ...]:
    """Turn `n` edges into `n + 1` bins, open at both ends.

    Half-open `[lower, upper)` throughout, so a value exactly on an edge lands
    in exactly one bin and the total is always the sample size.
    """
    spans: list[tuple[str, Decimal | None, Decimal | None]] = [
        (f"< {canonical_decimal_text(edges[0])}", None, edges[0])
    ]
    for lower, upper in zip(edges, edges[1:]):
        spans.append(
            (
                f"{canonical_decimal_text(lower)} to {canonical_decimal_text(upper)}",
                lower,
                upper,
            )
        )
    spans.append((f">= {canonical_decimal_text(edges[-1])}", edges[-1], None))
    return tuple(spans)


def _as_number(value: Any, kind: str) -> Decimal:
    """One value, in the unit its histogram is binned in.

    A `timedelta` becomes exact days rather than a float of seconds: the bins
    are stated in days and converting through `float` would put a value on the
    wrong side of an edge it sits exactly on.
    """
    if kind == "holding_time":
        if not isinstance(value, timedelta):
            raise TypeError("a holding-time histogram takes timedelta values")
        micros = Decimal(value.days) * _SECONDS_PER_DAY * Decimal(1000000)
        micros += Decimal(value.seconds) * Decimal(1000000) + Decimal(value.microseconds)
        return micros / (_SECONDS_PER_DAY * Decimal(1000000))
    if not isinstance(value, Decimal):
        raise TypeError(f"a {kind} histogram takes Decimal values")
    return value


def histogram_of(sample: Sample, *, kind: str) -> Histogram:
    """Bin a sample under the fixed edges its kind declares."""
    if not isinstance(sample, Sample):
        raise TypeError(f"sample must be a Sample, got {type(sample).__name__}")
    require_text(kind, "kind")
    if kind not in HISTOGRAM_KINDS:
        raise StatisticsRefusedError(
            f"no bucket edges are declared for {kind!r}; the choices are "
            f"{sorted(HISTOGRAM_KINDS)}. Deriving edges from the data would make "
            "two runs incomparable"
        )
    edges = HISTOGRAM_KINDS[kind]
    spans = _buckets_for(edges)
    counts = [0] * len(spans)
    for raw in sample.values:
        value = _as_number(raw, kind)
        # **The index is counted, not searched.** `spans` is `len(edges) + 1`
        # half-open bins covering the whole line, so the number of edges a value
        # has reached *is* its bin: none reached is the open bottom, all reached
        # is the open top. A search loop expresses the same thing with a
        # fall-through case that cannot happen — and an unreachable branch is
        # one nobody can test and everybody has to reason about.
        counts[sum(1 for edge in edges if value >= edge)] += 1
    return Histogram(
        kind=kind,
        unit="R" if kind == "r_multiple" else "days",
        buckets=tuple(
            Bucket(label=label, lower=lower, upper=upper, count=count)
            for (label, lower, upper), count in zip(spans, counts)
        ),
        size=sample.size,
        missing=sample.missing,
    )
