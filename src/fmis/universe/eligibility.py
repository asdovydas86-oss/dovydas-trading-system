"""The staged funnel. **Every instrument leaves by a named rule or stays.**

3,645 instruments arrive; some smaller number is a research universe. This module
is the whole of the difference, and its one design commitment is that the
difference is *enumerable*: for every instrument that is not in the final
universe, there is exactly one `Exclusion` naming the rule that removed it and the
number that made the rule fire.

**The stages run cheapest first**, and the ordering is not a performance detail —
it is what keeps the study affordable enough to finish. Quote currency, asset
class and economic identity are decided from provider metadata alone. Only what
survives those costs a listing probe, and only what survives *that* costs a window
of daily bars.

**The warm-up requirement is derived, never restated.** How much history an
instrument needs before it can be measured is a property of the production
analysis path — the weekly context role at a 250-candle window — and
`fmis.swing_setup.research_warmup.derive_warmup` owns it. CC asks that owner
rather than hard-coding 1,750 days, so a change to the production window reaches
this funnel instead of being silently contradicted by it.

**Nothing here reads an outcome.** Every rule below consumes a timestamp, a bar
count, a price or a volume. None consumes a return, a trade, an expectancy or an
admission result, and `fmis.universe.controls` asserts that permuting every
outcome in the repository leaves every decision in this module unchanged.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from fmis.pipeline.multi_timeframe import DEFAULT_TIMEFRAMES
from fmis.swing_setup.backtest_harness import DEFAULT_BACKTEST_LIMIT
from fmis.swing_setup.research_warmup import derive_warmup
from fmis.universe.capture import DailyBar
from fmis.universe.identity import classify_asset, peg_like_by_volatility
from fmis.universe.models import (
    AssetAssessment,
    AssetClass,
    CoverageMetrics,
    EconomicAsset,
    Exclusion,
    ExclusionReason,
    FunnelStage,
    LiquidityEvidence,
    QualityMetrics,
    TradingPair,
    UniverseError,
    require_aware,
)
from fmis.universe.preregistration import (
    DEPTH_BARS_PER_YEAR,
    ELIGIBLE_QUOTE_ASSET,
    MAX_GAP_BARS,
    MAX_MISSING_FRACTION,
    MIN_MEASUREMENT_YEARS,
    MIN_MEDIAN_QUOTE_VOLUME,
)

__all__ = [
    "WARMUP_SOURCE",
    "warmup_prefix",
    "FunnelCounts",
    "screen_pair",
    "coverage_of",
    "quality_of",
    "liquidity_of",
    "usable_measurement_years",
    "assess_asset",
    "funnel_counts",
    "peg_disagreements",
]

WARMUP_SOURCE: Final[str] = (
    "fmis.swing_setup.research_warmup.derive_warmup over "
    "fmis.pipeline.multi_timeframe.DEFAULT_TIMEFRAMES at "
    "fmis.swing_setup.backtest_harness.DEFAULT_BACKTEST_LIMIT"
)

_DAY: Final[timedelta] = timedelta(days=1)


def warmup_prefix() -> timedelta:
    """How much history must precede a measured instant. **Asked, not assumed.**

    Derived from the production timeframes and the production analysis window, so
    this returns 1,750 days today because the weekly context role reads 250
    candles — and would return something else the moment either changed.
    """
    return derive_warmup(
        dict(DEFAULT_TIMEFRAMES), limit=DEFAULT_BACKTEST_LIMIT
    ).prefix


# ------------------------------------------------------------ stage 1 and 2 ---


def screen_pair(pair: TradingPair) -> Exclusion | None:
    """Name-level screening. **No candle is downloaded to answer this.**

    Returns the `Exclusion` that removes ``pair``, or `None` when it survives to
    the identity stage. Three rules, in a fixed order: the quote currency, then
    the peg, then the derivative representations.
    """
    if not isinstance(pair, TradingPair):
        raise UniverseError("pair must be a TradingPair")
    if pair.quote_asset != ELIGIBLE_QUOTE_ASSET:
        return Exclusion(
            symbol=pair.symbol,
            reason=ExclusionReason.QUOTE_CURRENCY_NOT_ELIGIBLE,
            detail=(
                f"quoted in {pair.quote_asset}, not {ELIGIBLE_QUOTE_ASSET}. An ATR "
                f"denominated in {pair.quote_asset} cannot be pooled into a mean "
                "with one denominated in the eligible quote asset"
            ),
        )
    asset_class = classify_asset(pair.base_asset)
    if asset_class is AssetClass.STABLECOIN:
        return Exclusion(
            symbol=pair.symbol,
            reason=ExclusionReason.BASE_IS_STABLECOIN,
            detail=(
                f"base asset {pair.base_asset} tracks a peg. A direction-normalised, "
                "volatility-normalised excursion measured across a peg is the peg's "
                "tracking noise divided by a near-zero ATR"
            ),
        )
    if asset_class is AssetClass.LEVERAGED_TOKEN:
        return Exclusion(
            symbol=pair.symbol,
            reason=ExclusionReason.BASE_IS_LEVERAGED_TOKEN,
            detail=(
                f"base asset {pair.base_asset} is a leveraged or inverse derivative "
                "of an asset the universe may already hold; it is a decaying "
                "position in that asset rather than an independent market"
            ),
        )
    if asset_class is AssetClass.WRAPPED:
        return Exclusion(
            symbol=pair.symbol,
            reason=ExclusionReason.BASE_IS_WRAPPED_REPRESENTATION,
            detail=(
                f"base asset {pair.base_asset} is a wrapped or receipt "
                "representation of another economic asset; it prices the same "
                "exposure through a second token"
            ),
        )
    return None


# ------------------------------------------------------------------ stage 3 ---


def coverage_of(symbol: str, bars: Sequence[DailyBar]) -> CoverageMetrics | None:
    """Historical depth and structural integrity, from **timestamps only**.

    Returns `None` for an empty series, which is a different statement from a
    complete one and is what `ExclusionReason.NO_HISTORY_AVAILABLE` reports.

    Duplicates, malformed bars and gaps are counted separately because they have
    different causes and different consequences: a duplicate inflates a count, a
    malformed bar corrupts a value, and a gap hides a period the analysis will
    read straight across without noticing.
    """
    if not bars:
        return None
    ordered = sorted(bars, key=lambda bar: bar.open_time)
    first, last = ordered[0].open_time, ordered[-1].open_time
    expected = int(round((last - first) / _DAY)) + 1

    duplicates = 0
    malformed = 0
    longest_gap = 0
    previous: datetime | None = None
    for bar in ordered:
        if bar.high < bar.low or bar.high < bar.open or bar.high < bar.close \
                or bar.low > bar.open or bar.low > bar.close or bar.close <= 0.0 \
                or bar.volume < 0.0:
            malformed += 1
        if previous is not None:
            steps = int(round((bar.open_time - previous) / _DAY))
            if steps == 0:
                duplicates += 1
            elif steps > 1:
                longest_gap = max(longest_gap, steps - 1)
        previous = bar.open_time

    return CoverageMetrics(
        symbol=symbol,
        first_bar=first,
        last_bar=last,
        bars_observed=len(ordered) - duplicates,
        bars_expected=max(1, expected),
        duplicate_bars=duplicates,
        malformed_bars=malformed,
        longest_gap_bars=longest_gap,
    )


def quality_of(coverage: CoverageMetrics) -> QualityMetrics:
    """The four quality numbers eligibility is decided on."""
    if not isinstance(coverage, CoverageMetrics):
        raise UniverseError("coverage must be a CoverageMetrics")
    return QualityMetrics(
        symbol=coverage.symbol,
        missing_fraction=coverage.missing_fraction,
        longest_gap_bars=coverage.longest_gap_bars,
        duplicate_bars=coverage.duplicate_bars,
        malformed_bars=coverage.malformed_bars,
    )


def liquidity_of(
    symbol: str,
    bars: Sequence[DailyBar],
    *,
    window_start: datetime,
    window_end: datetime,
) -> LiquidityEvidence:
    """Median daily traded notional **inside the window**, never from today.

    The distinction is the whole point. Today's volume is evidence about today; for
    an instrument that stopped trading in 2022 it is evidence about nothing, and
    admitting such an instrument on the strength of a current figure would be
    selecting on information the study period did not have.

    Bars outside the window are ignored rather than refused, so one fetched series
    can serve both the coverage question and this one.
    """
    require_aware(window_start, "window_start")
    require_aware(window_end, "window_end")
    inside = [
        bar.notional
        for bar in bars
        if window_start <= bar.open_time < window_end and bar.volume > 0.0
    ]
    return LiquidityEvidence(
        symbol=symbol,
        median_quote_volume=statistics.median(inside) if inside else None,
        observed_days=len(inside),
        window_start=window_start,
        window_end=window_end,
        source=(
            "median of close * volume over days inside the measurement window, a "
            "proxy for the provider's quote-asset volume computed from canonical "
            "candle fields. It is notional traded, NOT depth and NOT spread"
        ),
    )


def usable_measurement_years(
    coverage: CoverageMetrics,
    *,
    listed_at: datetime,
    window_start: datetime,
    window_end: datetime,
    warmup: timedelta,
) -> float:
    """How much of the window this instrument can actually be measured over.

    ``listed_at`` is the instrument's **first ever bar**, which comes from the
    cheap listing probe and is deliberately a separate argument from ``coverage``.
    Coverage is measured over the *window* series; the listing date is years
    earlier. Folding the two into one series would place a 2017 bar and a 2023 bar
    in the same span and report the six intervening years as missing data — an
    instrument's completeness inside the window and its age are different facts.

    The instrument's measurement cannot open before its history has paid the
    warm-up prefix, and cannot run past its last observed bar. Both truncations
    are applied and the remainder is reported in years — `0.0` when the boundaries
    cross, meaning it contributes nothing rather than a negative amount.
    """
    if not isinstance(coverage, CoverageMetrics):
        raise UniverseError("coverage must be a CoverageMetrics")
    require_aware(listed_at, "listed_at")
    require_aware(window_start, "window_start")
    require_aware(window_end, "window_end")
    if not isinstance(warmup, timedelta):
        raise UniverseError("warmup must be a timedelta")
    start = max(window_start, listed_at + warmup)
    end = min(window_end, coverage.last_bar)
    if end <= start:
        return 0.0
    return (end - start).days / DEPTH_BARS_PER_YEAR


def assess_asset(
    asset: EconomicAsset,
    bars: Sequence[DailyBar],
    *,
    listed_at: datetime | None,
    window_start: datetime,
    window_end: datetime,
    warmup: timedelta,
) -> AssetAssessment:
    """One economic asset's full decision. **Depth, then quality, then liquidity.**

    ``bars`` are the instrument's bars inside the measurement window; ``listed_at``
    is its first ever bar, from the cheap listing probe. They are separate
    arguments because they answer separate questions and merging them would report
    an instrument's age as a gap in its window — see `usable_measurement_years`.
    ``listed_at`` may be `None` only when the instrument has no history at all.

    The rule order is sealed: an instrument with too little history is excluded
    for that, not for the missing-bar rate its short series happens to show.
    Reporting the first rule that fires — rather than the worst — is what makes
    the funnel's stage counts add up.
    """
    if not isinstance(asset, EconomicAsset):
        raise UniverseError("asset must be an EconomicAsset")
    symbol = asset.representative.symbol
    coverage = coverage_of(symbol, bars)
    if coverage is not None and listed_at is None:
        raise UniverseError(
            f"{symbol}: window bars were supplied with no listing date. The "
            "warm-up rule cannot be applied without one, and defaulting it to the "
            "window's own first bar would credit every instrument with history it "
            "may not have"
        )
    if coverage is None:
        return AssetAssessment(
            asset=asset, coverage=None, quality=None, liquidity=None, eligible=False,
            exclusion=Exclusion(
                symbol=symbol,
                reason=ExclusionReason.NO_HISTORY_AVAILABLE,
                detail=(
                    "the provider returned no closed daily bars at all for this "
                    "instrument, so it has no price series to measure"
                ),
            ),
        )

    years = usable_measurement_years(
        coverage, listed_at=listed_at, window_start=window_start,
        window_end=window_end, warmup=warmup,
    )
    quality = quality_of(coverage)
    liquidity = liquidity_of(
        symbol, bars, window_start=window_start, window_end=window_end
    )

    def refuse(reason: ExclusionReason, detail: str) -> AssetAssessment:
        return AssetAssessment(
            asset=asset, coverage=coverage, quality=quality, liquidity=liquidity,
            eligible=False,
            exclusion=Exclusion(symbol=symbol, reason=reason, detail=detail),
        )

    warmup_ready = listed_at + warmup
    if warmup_ready >= window_end:
        return refuse(
            ExclusionReason.INSUFFICIENT_HISTORY_FOR_WARMUP,
            f"first bar {listed_at.date().isoformat()} plus the derived "
            f"{warmup.days}-day production warm-up completes at "
            f"{warmup_ready.date().isoformat()}, which is at or after the window "
            f"end {window_end.date().isoformat()}. Not one instant inside the "
            "window could be analysed by the production fact path",
        )
    if coverage.last_bar <= window_start:
        return refuse(
            ExclusionReason.INSUFFICIENT_FORWARD_WINDOW,
            f"last bar {coverage.last_bar.date().isoformat()} is at or before the "
            f"window start {window_start.date().isoformat()}; the instrument had "
            "stopped trading before the measurement period opened",
        )
    if years < MIN_MEASUREMENT_YEARS:
        return refuse(
            ExclusionReason.INSUFFICIENT_MEASUREMENT_COVERAGE,
            f"usable measurement span is {years:.3f} years after the "
            f"{warmup.days}-day warm-up and the instrument's own last bar are both "
            f"applied, below the sealed floor of {MIN_MEASUREMENT_YEARS} years",
        )
    if coverage.malformed_bars:
        return refuse(
            ExclusionReason.MALFORMED_BARS,
            f"{coverage.malformed_bars} bar(s) violate the OHLC ordering or carry a "
            "non-positive close or negative volume; a structural analysis over one "
            "would read a level that never traded",
        )
    if coverage.duplicate_bars:
        return refuse(
            ExclusionReason.DUPLICATE_BARS,
            f"{coverage.duplicate_bars} bar(s) repeat an open time already present. "
            "A duplicated bar counts one instant twice and inflates every density "
            "figure derived from the series",
        )
    if quality.missing_fraction > MAX_MISSING_FRACTION:
        return refuse(
            ExclusionReason.EXCESSIVE_MISSING_BARS,
            f"{quality.missing_fraction:.4f} of expected daily bars are absent, "
            f"above the sealed ceiling of {MAX_MISSING_FRACTION}",
        )
    if quality.longest_gap_bars > MAX_GAP_BARS:
        return refuse(
            ExclusionReason.EXCESSIVE_GAP,
            f"the longest run of consecutive absent daily bars is "
            f"{quality.longest_gap_bars}, above the sealed ceiling of "
            f"{MAX_GAP_BARS}. An aggregate missing fraction cannot see a hole this "
            "shape, which is why both rules exist",
        )
    if not liquidity.is_measured:
        return refuse(
            ExclusionReason.NO_LIQUIDITY_EVIDENCE,
            "no day inside the measurement window carried positive volume, so no "
            "historical liquidity statement can be made. This is absence of "
            "evidence and is reported separately from measured illiquidity",
        )
    if liquidity.median_quote_volume is not None and (
        liquidity.median_quote_volume < MIN_MEDIAN_QUOTE_VOLUME
    ):
        return refuse(
            ExclusionReason.INSUFFICIENT_LIQUIDITY,
            f"median daily traded notional inside the window is "
            f"{liquidity.median_quote_volume:,.0f}, below the sealed floor of "
            f"{MIN_MEDIAN_QUOTE_VOLUME:,.0f}",
        )
    return AssetAssessment(
        asset=asset, coverage=coverage, quality=quality, liquidity=liquidity,
        eligible=True, exclusion=None,
    )


# ------------------------------------------------------------------- funnel ---


@dataclass(frozen=True, slots=True)
class FunnelCounts:
    """How many instruments each stage removed. **The counts must reconcile.**

    `reconciles` is checked rather than trusted: discovered minus the sum of every
    stage's removals must equal the eligible count, and a funnel that did not
    balance would be hiding an unattributed exclusion.
    """

    discovered: int
    by_stage: dict[str, int]
    eligible: int

    def __post_init__(self) -> None:
        if self.discovered < 0 or self.eligible < 0:
            raise UniverseError("funnel counts cannot be negative")
        if not self.reconciles:
            raise UniverseError(
                f"the funnel does not balance: {self.discovered} discovered minus "
                f"{sum(self.by_stage.values())} removed is not {self.eligible} "
                "eligible. Some instrument left the universe without a reason"
            )

    @property
    def removed(self) -> int:
        return sum(self.by_stage.values())

    @property
    def reconciles(self) -> bool:
        return self.discovered - self.removed == self.eligible

    def payload(self) -> dict[str, Any]:
        return {
            "discovered": self.discovered,
            "by_stage": {key: self.by_stage[key] for key in sorted(self.by_stage)},
            "removed": self.removed,
            "eligible": self.eligible,
        }


def funnel_counts(
    *, discovered: int, exclusions: Sequence[Exclusion], eligible: int
) -> FunnelCounts:
    """Tally exclusions by stage and assert the funnel balances."""
    by_stage: dict[str, int] = {stage.value: 0 for stage in FunnelStage}
    del by_stage[FunnelStage.DISCOVERED.value]
    for item in exclusions:
        by_stage[item.stage.value] += 1
    return FunnelCounts(discovered=discovered, by_stage=by_stage, eligible=eligible)


def peg_disagreements(
    assessments: Sequence[AssetAssessment], series: dict[str, Sequence[DailyBar]]
) -> tuple[str, ...]:
    """Assets the **data** calls peg-like that the sealed name list does not.

    This is the backstop on `STABLECOIN_ASSETS` firing. What it returns is a
    disagreement between a name rule and a measurement, and a disagreement is
    reported rather than resolved: silently excluding on it would let a measured
    threshold quietly become an eligibility rule that was never sealed.
    """
    flagged: list[str] = []
    for assessment in assessments:
        if not assessment.eligible:
            continue
        bars = series.get(assessment.symbol)
        if not bars:
            continue
        verdict = peg_like_by_volatility(
            [bar.close for bar in bars], bars_per_year=DEPTH_BARS_PER_YEAR
        )
        if verdict:
            flagged.append(assessment.asset.asset_id)
    return tuple(sorted(flagged))
