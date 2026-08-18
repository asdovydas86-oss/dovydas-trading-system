"""How the trades behaved while they were on — excursion, capture, shape.

The performance family answers *"did it make money"*. This one answers *"how"*,
and the difference matters because two systems with the same expectancy and
different excursion profiles are not the same system: one of them sits through
drawdowns the owner will not sit through.

**Every figure here is simulated-only, and the page says so.** MAE, MFE and the
bar count are frozen at close by `AP` §25.3 because kline history is not
permanent — and nothing froze them for a trade the owner recorded by hand. So
`ST-2` is not a footnote on this module, it is its headline: the `Sample` on
every figure reports how many of the corpus's trades actually contributed, and
a corpus of twelve trades of which four are recorded produces excursion figures
that say `n = 8`.

**Excursions are carried in R, not in money or in price.** `AP` §5.3 forbids a
stored quotient and `TradeOutcome` obeys it by freezing prices; `OutcomeReading`
already divides them into the initial risk, and this module consumes that
division rather than repeating it. R is also the only form in which two markets'
excursions can be put in one average.

**Capture efficiency is `final R ÷ MFE in R`**, and a trade that never traded in
front of its entry has none. Zero there would read as *"captured none of a large
move"* when the truth is *"there was no move to capture"* — the same class of
lie a zero unrealized P&L on an unmarked position tells.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fmis.money import canonical_decimal_text
from fmis.provenance import Absent
from fmis.statistics.distribution import Histogram, histogram_of
from fmis.statistics.models import SamplePolicy, TradeStat
from fmis.statistics.sampling import (
    Sample,
    collect_values,
    extremum_or_absent,
    mean_or_absent,
    median_or_absent,
)

__all__ = ["QualityStatistics", "quality_statistics", "CAPTURE_BASIS", "EXCURSION_BASIS"]

#: Printed beside capture efficiency.
CAPTURE_BASIS = (
    "The final R multiple divided by the largest favourable excursion in R. A "
    "trade that never traded in front of its entry has no capture efficiency, "
    "because there was no favourable move to keep a share of. The mean of this "
    "ratio is dominated by trades whose favourable excursion was small — one "
    "that showed 0.1 R and lost 1 R contributes minus ten — so the median is "
    "the more readable summary and both are shown."
)

#: Printed beside average excursion.
EXCURSION_BASIS = (
    "The total distance a trade travelled in R — the largest favourable "
    "excursion plus the magnitude of the largest adverse one. It is a measure of "
    "how much movement the trade sat through, not of what it made."
)


@dataclass(frozen=True, slots=True)
class QualityStatistics:
    """Excursion, capture and shape — over the trades that recorded them."""

    adverse: Sample
    favourable: Sample
    average_adverse_r: Decimal | Absent
    average_favourable_r: Decimal | Absent
    median_adverse_r: Decimal | Absent
    median_favourable_r: Decimal | Absent
    maximum_adverse_r: Decimal | Absent
    maximum_favourable_r: Decimal | Absent
    capture: Sample
    average_capture_efficiency: Decimal | Absent
    median_capture_efficiency: Decimal | Absent
    excursion: Sample
    average_excursion_r: Decimal | Absent
    r_distribution: Histogram
    holding_time_distribution: Histogram
    capture_basis: str = CAPTURE_BASIS
    excursion_basis: str = EXCURSION_BASIS

    def to_payload(self) -> dict[str, Any]:
        return {
            "adverse": self.adverse.to_payload(),
            "favourable": self.favourable.to_payload(),
            "average_adverse_r": _number(self.average_adverse_r),
            "average_favourable_r": _number(self.average_favourable_r),
            "median_adverse_r": _number(self.median_adverse_r),
            "median_favourable_r": _number(self.median_favourable_r),
            "maximum_adverse_r": _number(self.maximum_adverse_r),
            "maximum_favourable_r": _number(self.maximum_favourable_r),
            "capture": self.capture.to_payload(),
            "average_capture_efficiency": _number(self.average_capture_efficiency),
            "median_capture_efficiency": _number(self.median_capture_efficiency),
            "excursion": self.excursion.to_payload(),
            "average_excursion_r": _number(self.average_excursion_r),
            "r_distribution": self.r_distribution.to_payload(),
            "holding_time_distribution": self.holding_time_distribution.to_payload(),
        }


def quality_statistics(
    trades: tuple[TradeStat, ...], policy: SamplePolicy
) -> QualityStatistics:
    """Every excursion and shape figure the milestone brief's quality list names."""
    if not isinstance(trades, tuple):
        raise TypeError("trades must be a tuple of TradeStat")
    for stat in trades:
        if not isinstance(stat, TradeStat):
            raise TypeError("every trade must be a TradeStat")
    if not isinstance(policy, SamplePolicy):
        raise TypeError("policy must be a SamplePolicy")

    adverse = collect_values(
        trades, lambda stat: stat.max_adverse_r, "maximum adverse excursion"
    )
    favourable = collect_values(
        trades, lambda stat: stat.max_favourable_r, "maximum favourable excursion"
    )
    capture = collect_values(
        trades, lambda stat: stat.capture_efficiency, "capture efficiency"
    )
    excursion = collect_values(
        trades, lambda stat: stat.excursion_range_r, "total excursion"
    )
    r_values = collect_values(trades, lambda stat: stat.r_multiple, "R multiple")
    holding = collect_values(trades, lambda stat: stat.holding_time, "holding time")

    return QualityStatistics(
        adverse=adverse,
        favourable=favourable,
        average_adverse_r=mean_or_absent(adverse, policy),
        average_favourable_r=mean_or_absent(favourable, policy),
        median_adverse_r=median_or_absent(adverse, policy),
        median_favourable_r=median_or_absent(favourable, policy),
        # The **largest** adverse excursion is the most negative one, so the
        # extremum is taken at the small end. Reaching for `largest=True` here
        # would report the trade that went least far against the owner as the
        # worst one they sat through.
        maximum_adverse_r=extremum_or_absent(adverse, policy, largest=False),
        maximum_favourable_r=extremum_or_absent(favourable, policy, largest=True),
        capture=capture,
        average_capture_efficiency=mean_or_absent(capture, policy),
        median_capture_efficiency=median_or_absent(capture, policy),
        excursion=excursion,
        average_excursion_r=mean_or_absent(excursion, policy),
        r_distribution=histogram_of(r_values, kind="r_multiple"),
        holding_time_distribution=histogram_of(holding, kind="holding_time"),
    )


def _number(value: Decimal | Absent) -> str | None:
    return None if isinstance(value, Absent) else canonical_decimal_text(value)
