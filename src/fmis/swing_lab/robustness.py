"""Does a variant's advantage survive being cut up? **Simple splits, deliberately.**

The brief asks for robustness and forbids parameter mining, and those two
constraints together rule out most of what "robustness testing" usually means.
There is no optimizer here, no grid, no genetic search and nothing to overfit —
because nothing is being *fitted*. Every variant was specified before the data
was read, so the only honest question left is whether its measured behaviour is
concentrated in one period, one symbol or one direction.

**Four splits, each answering one way a result can be an accident.**

* **Chronological** — the first half is *train*, the second is *validation*.
  Not because anything was trained, but because a policy that only works before
  a certain date is describing a regime rather than an edge.
* **Walk-forward** — the measurement window's own segments, in order. A variant
  whose total R comes from one segment is reported as such.
* **Symbol** — one cohort per symbol. A study whose edge is one coin is a study
  about that coin.
* **Direction** — long against short. The owner asked specifically whether they
  behave differently.

**A split that thins the sample below the floor reports absence, not a small
number.** That is the common case here and it is the honest one: cutting a few
hundred trades four ways leaves cohorts too small to carry a rate, and
`LabMeasure` refuses to state one.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from fmis.swing_lab.metrics import SAMPLE_FLOOR, VariantMetrics, lab_breakdown_by, compute_lab_metrics
from fmis.swing_lab.models import LabTrade, SwingLabError

__all__ = [
    "SplitReading",
    "RobustnessReading",
    "measure_robustness",
    "concentration_of",
    "concentration_of_magnitudes",
]


@dataclass(frozen=True, slots=True)
class SplitReading:
    """One way of cutting a variant's trades, and the cohorts it produced."""

    name: str
    question: str
    cohorts: tuple[VariantMetrics, ...]

    @property
    def reportable_cohorts(self) -> tuple[VariantMetrics, ...]:
        return tuple(item for item in self.cohorts if item.expectancy_r.is_present)

    @property
    def all_cohorts_agree_on_sign(self) -> bool | None:
        """Whether every reportable cohort's expectancy has the same sign.

        ``None`` when fewer than two cohorts carry a reportable figure — with
        one cohort there is nothing to agree with, and saying ``True`` would
        dress a missing test as a passed one.
        """
        values = [
            item.expectancy_r.value
            for item in self.reportable_cohorts
            if item.expectancy_r.value is not None
        ]
        if len(values) < 2:
            return None
        return all(value > 0 for value in values) or all(value < 0 for value in values)


@dataclass(frozen=True, slots=True)
class RobustnessReading:
    """Every split for one variant, plus how concentrated its result is."""

    variant_id: str
    overall: VariantMetrics
    splits: tuple[SplitReading, ...]
    largest_symbol_share: Decimal | None
    largest_segment_share: Decimal | None

    def split(self, name: str) -> SplitReading:
        for item in self.splits:
            if item.name == name:
                return item
        raise SwingLabError(
            f"no split named {name!r}; this reading holds "
            f"{', '.join(item.name for item in self.splits)}"
        )


def concentration_of(
    trades: Sequence[LabTrade], key
) -> Decimal | None:
    """The largest single cohort's share of **gross absolute R**.

    Absolute rather than signed, because the question is *how much of this
    result came from one place* — and a cohort contributing a large loss
    concentrates the result exactly as much as one contributing a large gain.
    ``None`` when no trade carries an R at all.
    """
    return concentration_of_magnitudes(
        (key(trade) or "unattributed", abs(trade.net_r))
        for trade in trades
        if trade.net_r is not None
    )


def concentration_of_magnitudes(
    contributions: "Iterable[tuple[str, Decimal]]",
) -> Decimal | None:
    """The largest single cohort's share of a total magnitude. **The formula, once.**

    `concentration_of` is this function over a trade's net R. Milestone CA's unit
    is a paired difference rather than a trade, and it reads the same measure
    here rather than restating the arithmetic — two copies of a share
    calculation are two places for the denominator to stop matching the
    numerator.

    ``None`` when nothing contributed any magnitude at all, which is a stated
    absence rather than a zero share.
    """
    totals: dict[str, Decimal] = {}
    grand = Decimal("0")
    for label, magnitude in contributions:
        if magnitude < 0:
            raise SwingLabError(
                f"cohort {label!r} contributed a negative magnitude {magnitude}; "
                "a share of a total must be taken over absolute contributions"
            )
        totals[label] = totals.get(label, Decimal("0")) + magnitude
        grand += magnitude
    if grand == 0:
        return None
    return max(totals.values()) / grand


def measure_robustness(
    trades: Sequence[LabTrade],
    *,
    variant_id: str,
    measurement_start: datetime,
    measurement_end: datetime,
) -> RobustnessReading:
    """Cut one variant's trades four ways and measure each cohort.

    The chronological split uses the **calendar midpoint of the measurement
    window**, not the median trade. A median-trade split would put half the
    trades on each side by construction and would silently move whenever the
    trade count changed, so two variants' "first halves" would cover different
    periods and could not be compared.
    """
    if measurement_end <= measurement_start:
        raise SwingLabError("measurement_end must be after measurement_start")
    ordered = tuple(trades)
    midpoint = measurement_start + (measurement_end - measurement_start) / 2

    def period(trade: LabTrade) -> str:
        return "train_first_half" if trade.signal_at < midpoint else "validation_second_half"

    splits = (
        SplitReading(
            name="chronological",
            question=(
                "Does the result hold in the second half of the window, or is it "
                "a description of one period? Split at the window's calendar "
                f"midpoint, {midpoint.date().isoformat()}."
            ),
            cohorts=lab_breakdown_by(ordered, period),
        ),
        SplitReading(
            name="walk_forward",
            question=(
                "Is total R spread across the window's segments, or concentrated "
                "in one of them?"
            ),
            cohorts=lab_breakdown_by(ordered, lambda trade: trade.segment),
        ),
        SplitReading(
            name="symbol",
            question="Is the result one symbol's, or the universe's?",
            cohorts=lab_breakdown_by(ordered, lambda trade: trade.symbol),
        ),
        SplitReading(
            name="direction",
            question="Do LONG and SHORT behave differently?",
            cohorts=lab_breakdown_by(ordered, lambda trade: trade.direction.value),
        ),
    )
    return RobustnessReading(
        variant_id=variant_id,
        overall=compute_lab_metrics(ordered, label=variant_id),
        splits=splits,
        largest_symbol_share=concentration_of(ordered, lambda trade: trade.symbol),
        largest_segment_share=concentration_of(ordered, lambda trade: trade.segment),
    )
