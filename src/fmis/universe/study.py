"""Milestone CC, run end to end. **The composition root, and nothing else.**

Every rule this module applies is owned somewhere else — the seal in
`preregistration`, identity in `identity`, the funnel in `eligibility`,
co-movement in `dependence`, admission rates in `density`, the design arithmetic
in `growth` (which is Milestone CB's, reused) and the decision in `verdict`. What
lives here is the *order* they run in and the staging that keeps the study
affordable, so that no rule can be changed by editing this file.

**The stages, and what each one costs.**

    1. discover          1 request           every listed spot instrument
    2. screen             0 requests          quote currency, asset class
    3. collapse           0 requests          pairs onto economic assets
    4. listing probe      1 per asset         one daily bar from the epoch
    5. window series      1 per survivor      the measurement window's daily bars
    6. assess             0 requests          depth, quality, liquidity
    7. dependence         0 requests          co-movement across the eligible set
    8. density            replay, or reuse    admissions per asset-year
    9. growth             0 requests          CB's arithmetic over 7 and 8
   10. verdict            0 requests          the sealed rules

Stage 5 is only paid for by instruments stage 4 admitted, and stage 8 is bounded
by the sealed subsample. A run that skipped the staging would download years of
4-hour history for three thousand instruments most of which fail on a listing date.

**It can run entirely offline.** Given a `SeriesCache` and ``allow_fetch=False``
every stage after discovery is a pure function of the file. Discovery itself is a
provider call — *which instruments exist* is not a bar and a candle cache cannot
answer it — so an offline reproduction supplies a transport replaying the
discovery response it recorded, and hands a fatal one for everything else.
`tests/test_universe_study.py` runs exactly that and asserts no candle was
refetched.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from fmis.ingest import IngestError
from fmis.providers.binance import BinanceResponseError, Transport
from fmis.universe.capture import (
    EPOCH,
    DailyBar,
    SeriesCache,
    discover_pairs,
    series_digest,
)
from fmis.universe.density import (
    AssetDensity,
    DensitySummary,
    published_densities,
    summarise_density,
)
from fmis.universe.dependence import (
    POST_REVIEW_LIMITATIONS,
    DependenceSummary,
    correlated_groups,
    measure_dependence,
)
from fmis.universe.eligibility import (
    assess_asset,
    funnel_counts,
    peg_disagreements,
    screen_pair,
    warmup_prefix,
)
from fmis.universe.growth import (
    GrowthRow,
    cb_required_information,
    effect_for,
    growth_curve,
    requirement_for_effect,
)
from fmis.universe.horizon import HorizonCeiling, asset_horizon, horizon_ceiling
from fmis.universe.identity import group_by_economic_asset
from fmis.universe.models import (
    AssetAssessment,
    Exclusion,
    ExclusionReason,
    PairStatus,
    UniverseError,
)
from fmis.universe.preregistration import (
    CC_LIMITATIONS,
    DEPENDENCE_SCENARIOS,
    EFFECT_SIZE_GRID,
    UNIVERSE_GROWTH_SIZES,
    cc_preregistration_digest,
    measurement_window,
    representative_of,
)
from fmis.universe.verdict import (
    FeasibilityAssessment,
    SurvivorshipReading,
    classify_survivorship,
    decide_feasibility,
)

__all__ = [
    "CORRELATED_GROUP_THRESHOLD",
    "UniverseStudy",
    "run_universe_study",
    "ordered_assets",
]

#: The correlation at which two assets are joined into one measured group.
#:
#: 0.80. High enough that a group means "these move as one thing" rather than
#: "these are both crypto", and sealed before the correlations were seen. The
#: groups are **descriptive output**, not an eligibility rule: nothing is excluded
#: for belonging to one, and the dependence arithmetic uses the mean correlation
#: rather than the grouping.
CORRELATED_GROUP_THRESHOLD: float = 0.80


def ordered_assets(assessments: Sequence[AssetAssessment]) -> tuple[AssetAssessment, ...]:
    """`UNIVERSE_ORDERING_RULE`, as code. **History, never performance.**

    Descending usable history, ties broken by ascending economic asset id. Both
    keys are design properties: the first is read from bar timestamps, the second
    from a ticker. Neither can be influenced by what the strategy earned, which is
    what makes the growth curve's "first N assets" a statement about data rather
    than a selection on outcomes.
    """
    eligible = [item for item in assessments if item.eligible and item.coverage]
    return tuple(
        sorted(
            eligible,
            key=lambda item: (-item.coverage.usable_years, item.asset.asset_id),
        )
    )


@dataclass(frozen=True, slots=True)
class UniverseStudy:
    """Everything Milestone CC measured and concluded, in one value."""

    preregistration_digest: str
    discovered_at: datetime
    provider: str
    window_start: datetime
    window_end: datetime
    warmup_days: int
    discovered_instruments: int
    economic_assets: int
    assessments: tuple[AssetAssessment, ...]
    exclusions: tuple[Exclusion, ...]
    funnel: Any
    eligible: tuple[AssetAssessment, ...]
    dependence: DependenceSummary
    correlated_groups: tuple[tuple[str, ...], ...]
    peg_disagreements: tuple[str, ...]
    density: DensitySummary
    density_entries: tuple[AssetDensity, ...]
    growth: tuple[GrowthRow, ...]
    effect_requirements: tuple[Any, ...]
    cb_required_observations: int | None
    cb_required_clusters: int | None
    survivorship: SurvivorshipReading
    assessment: FeasibilityAssessment
    series_digests: dict[str, str]
    #: The POST-HOC generous bound. `None` when the last-bar probes it needs were
    #: not available. It is not part of the sealed verdict and can only move the
    #: answer toward FEASIBLE — see `fmis.universe.horizon`.
    horizon: HorizonCeiling | None = None

    @property
    def eligible_assets(self) -> int:
        return len(self.eligible)

    @property
    def post_review_limitations(self) -> tuple[str, ...]:
        """What the independent review established AFTER the seal was taken.

        Exposed on the study so the renderer and the artifact both reach them
        without either importing a measurement module, and so a reader of the CLI
        cannot see the sealed limitations without also seeing these.
        """
        return POST_REVIEW_LIMITATIONS

    @property
    def mean_usable_years(self) -> float:
        """Mean usable measurement years across the eligible universe."""
        if not self.eligible:
            return 0.0
        return sum(
            item.coverage.usable_years for item in self.eligible if item.coverage
        ) / len(self.eligible)

    def payload(self) -> dict[str, Any]:
        return {
            "preregistration_digest": self.preregistration_digest,
            "discovered_at": self.discovered_at.isoformat(),
            "provider": self.provider,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "warmup_days": self.warmup_days,
            "discovered_instruments": self.discovered_instruments,
            "economic_assets": self.economic_assets,
            "eligible_assets": self.eligible_assets,
            "mean_usable_years": self.mean_usable_years,
            "funnel": self.funnel.payload(),
            "assessments": [item.payload() for item in self.assessments],
            "exclusions": [item.payload() for item in self.exclusions],
            "dependence": self.dependence.payload(),
            "correlated_groups": [list(group) for group in self.correlated_groups],
            "peg_disagreements": list(self.peg_disagreements),
            "density": self.density.payload(),
            "density_entries": [item.payload() for item in self.density_entries],
            "growth": [row.payload() for row in self.growth],
            "effect_requirements": [item.payload() for item in self.effect_requirements],
            "cb_required_observations": self.cb_required_observations,
            "cb_required_clusters": self.cb_required_clusters,
            "survivorship": self.survivorship.payload(),
            "assessment": self.assessment.payload(),
            "series_digests": dict(sorted(self.series_digests.items())),
            "horizon": None if self.horizon is None else self.horizon.payload(),
            # Learned AFTER the seal, so carried separately from CC_LIMITATIONS
            # rather than retro-fitted into a sealed payload.
            "post_review_limitations": list(POST_REVIEW_LIMITATIONS),
        }


def _malformed(asset, detail: str) -> AssetAssessment:
    """An asset the provider could not describe without violating an invariant.

    Recorded under `MALFORMED_BARS` with the boundary's own message, so the funnel
    stays balanced and a reader can see exactly which invariant was broken rather
    than finding the instrument silently absent.
    """
    return AssetAssessment(
        asset=asset, coverage=None, quality=None, liquidity=None, eligible=False,
        exclusion=Exclusion(
            symbol=asset.representative.symbol,
            reason=ExclusionReason.MALFORMED_BARS,
            detail=(
                f"the provider returned a series the canonical candle boundary "
                f"refuses — {detail}. A bar that violates a time invariant cannot "
                "be measured and is not silently dropped"
            ),
        ),
    )


def _window_usable_years(assessments: Sequence[AssetAssessment]) -> float:
    """Mean usable years over the eligible set, or a refusal when there is none."""
    eligible = [item for item in assessments if item.eligible and item.coverage]
    if not eligible:
        raise UniverseError(
            "no eligible asset carries coverage, so no usable-years figure can be "
            "formed. A universe with nothing in it has no density and no growth "
            "curve, and reporting zero would read as a measurement"
        )
    return sum(item.coverage.usable_years for item in eligible) / len(eligible)


def run_universe_study(
    *,
    cache: SeriesCache | None = None,
    transport: Transport | None = None,
    allow_fetch: bool = True,
    density_entries: Sequence[AssetDensity] | None = None,
    unrecoverable_gap_demonstrated: bool = True,
    discovered_at: datetime | None = None,
    measure_horizon: bool = True,
) -> UniverseStudy:
    """Run the whole staged study.

    ``density_entries`` supplies admission-density measurements. When omitted,
    Milestone CA's three published sample densities are used — three disjoint
    samples over 36 distinct symbols, which is already better evidence about the
    *stability* of density than one new replay would be. A caller that has run a
    new replay passes its entries here and both sets are reported with their
    sources attached.

    ``allow_fetch=False`` with a populated ``cache`` reproduces a previous run
    offline; any series the cache is missing raises rather than being refetched.
    """
    store = SeriesCache() if cache is None else cache
    window_start, window_end = measurement_window()
    warmup = warmup_prefix()

    # ---- stages 1-3: discovery, screening, economic identity ----
    # Discovery is the one call a candle cache cannot answer: `SeriesCache` holds
    # bars, and *which instruments exist* is not a bar. ``allow_fetch`` therefore
    # governs candles only, and an offline reproduction supplies a ``transport``
    # that replays the discovery response it recorded — which is exactly what
    # `tests/test_universe_study.py` does. A run that reaches the live provider
    # here and nowhere else has still refetched no market data.
    server_time, pairs = discover_pairs(transport=transport)
    discovered_at = server_time if discovered_at is None else discovered_at

    exclusions: list[Exclusion] = []
    survivors = []
    for pair in pairs:
        excluded = screen_pair(pair)
        if excluded is None:
            survivors.append(pair)
        else:
            exclusions.append(excluded)

    assets = group_by_economic_asset(survivors, representative_of=representative_of)
    for asset in assets:
        for duplicate in asset.duplicate_pairs:
            exclusions.append(
                Exclusion(
                    symbol=duplicate.symbol,
                    reason=ExclusionReason.DUPLICATE_ECONOMIC_EXPOSURE,
                    detail=(
                        f"prices the same economic asset {asset.asset_id!r} as "
                        f"{asset.representative.symbol}, which represents it. Two "
                        "markets on one exposure are one experimental cluster"
                    ),
                )
            )

    # ---- stages 4-6: history, quality, liquidity ----
    assessments: list[AssetAssessment] = []
    window_series: dict[str, tuple[DailyBar, ...]] = {}
    listing_dates: dict[str, datetime] = {}
    digests: dict[str, str] = {}
    for asset in assets:
        symbol = asset.representative.symbol
        try:
            listing = store.series(
                symbol, start=EPOCH, limit=1, transport=transport,
                allow_fetch=allow_fetch,
            )
        except (BinanceResponseError, IngestError) as error:
            # The provider answered with a series the canonical boundary refuses —
            # KLAYUSDT returns a kline whose close time precedes its open time.
            # That is a DATA fact about the instrument, so it becomes a named
            # exclusion rather than an aborted study: one malformed listing must
            # not be able to take the whole universe measurement down.
            assessments.append(
                _malformed(asset, f"listing probe: {error}")
            )
            continue
        if not listing:
            assessments.append(
                assess_asset(
                    asset, (), listed_at=None, window_start=window_start,
                    window_end=window_end, warmup=warmup,
                )
            )
            continue
        first_bar = listing[0].open_time
        listing_dates[symbol] = first_bar
        # The cheap refusal: an instrument whose first bar plus the warm-up lands
        # at or after the window end can contribute no measured instant, so its
        # window is never downloaded. The single listing bar is enough to state
        # the exclusion, and it is passed as the window series only because the
        # warm-up rule fires before anything reads it.
        if first_bar + warmup >= window_end:
            assessments.append(
                assess_asset(
                    asset, listing, listed_at=first_bar, window_start=window_start,
                    window_end=window_end, warmup=warmup,
                )
            )
            continue
        try:
            bars = store.series(
                symbol, start=window_start, end=window_end, limit=1000,
                transport=transport, allow_fetch=allow_fetch,
            )
        except (BinanceResponseError, IngestError) as error:
            assessments.append(_malformed(asset, f"window series: {error}"))
            continue
        window_series[symbol] = bars
        digests[symbol] = series_digest(bars)
        assessments.append(
            assess_asset(
                asset, bars, listed_at=first_bar, window_start=window_start,
                window_end=window_end, warmup=warmup,
            )
        )

    for item in assessments:
        if item.exclusion is not None:
            exclusions.append(item.exclusion)

    eligible = ordered_assets(assessments)
    counts = funnel_counts(
        discovered=len(pairs), exclusions=exclusions, eligible=len(eligible)
    )

    # ---- stage 7: dependence over the eligible universe ----
    closes = {
        item.asset.asset_id: [bar.close for bar in window_series[item.symbol]]
        for item in eligible
        if item.symbol in window_series
    }
    instants = {
        item.asset.asset_id: [bar.open_time for bar in window_series[item.symbol]]
        for item in eligible
        if item.symbol in window_series
    }
    dependence = measure_dependence(
        closes, instants=instants, window_days=(window_end - window_start).days
    )
    returns_by_asset = {
        name: dict(zip(instants[name][1:], _log_returns(closes[name])))
        for name in closes
        if len(closes[name]) >= 3
    }
    groups = correlated_groups(returns_by_asset, threshold=CORRELATED_GROUP_THRESHOLD)

    # ---- stage 8: admission density ----
    entries = tuple(density_entries) if density_entries else published_densities()
    density = summarise_density(entries)

    # ---- stage 9: the growth curve and the effect grid ----
    years = _window_usable_years(assessments)
    rate = density.pooled_per_asset_year
    curve = growth_curve(
        sizes=UNIVERSE_GROWTH_SIZES,
        scenarios=DEPENDENCE_SCENARIOS,
        dependence=dependence,
        eligible_assets=len(eligible),
        years_per_asset=years,
        admissions_per_asset_year=rate,
        effect=effect_for(Decimal("0.10")),
    )
    requirements = [
        requirement_for_effect(
            magnitude=magnitude, scenario=scenario, dependence=dependence,
            years_per_asset=years, admissions_per_asset_year=rate,
        )
        for magnitude in EFFECT_SIZE_GRID
        for scenario in DEPENDENCE_SCENARIOS
    ]
    primary = {
        item.dependence_scenario: item
        for item in requirements
        if item.effect == "0.10"
    }

    # ---- stage 10: survivorship and the verdict ----
    halted = sum(1 for pair in pairs if pair.status is PairStatus.HALTED)
    eligible_halted = sum(
        1 for item in eligible if item.asset.representative.status is PairStatus.HALTED
    )
    survivorship = classify_survivorship(
        total_instruments=len(pairs),
        halted_instruments=halted,
        eligible_halted=eligible_halted,
        unrecoverable_gap_demonstrated=unrecoverable_gap_demonstrated,
    )
    # ---- POST-HOC robustness: the generous ceiling ----
    # Not pre-registered, not part of the verdict, and able only to move the
    # answer toward FEASIBLE. It asks how many asset-years this provider has EVER
    # produced under the same sealed rules, rather than how many the sealed
    # two-year window admits. See `fmis.universe.horizon`.
    ceiling = None
    if measure_horizon:
        spans = []
        for asset in assets:
            symbol = asset.representative.symbol
            listed = listing_dates.get(symbol)
            if listed is None:
                continue
            try:
                tail = store.series(
                    symbol, start=None, end=None, limit=2, transport=transport,
                    allow_fetch=allow_fetch,
                )
            except (BinanceResponseError, IngestError, UniverseError):
                # A last-bar probe this capture does not hold simply means this
                # asset cannot contribute to the ceiling. Omitting it makes the
                # bound SMALLER, which is the safe direction for an analysis whose
                # only admissible role is to argue against the verdict.
                continue
            if not tail:
                continue
            spans.append(
                asset_horizon(
                    asset_id=asset.asset_id,
                    listed_at=listed,
                    last_bar=tail[-1].open_time,
                    warmup=warmup,
                )
            )
        if spans:
            ceiling = horizon_ceiling(
                spans,
                admissions_per_asset_year=rate,
                required_admissions=cb_required_information().required_observations or 0,
                required_clusters=cb_required_information().required_clusters or 0,
            )

    cb = cb_required_information()
    assessment = decide_feasibility(
        requirements=primary,
        eligible_assets=len(eligible),
        dependence=dependence,
        survivorship=survivorship,
        limitations=CC_LIMITATIONS,
    )

    return UniverseStudy(
        preregistration_digest=cc_preregistration_digest(),
        discovered_at=discovered_at,
        provider="binance-public-spot",
        window_start=window_start,
        window_end=window_end,
        warmup_days=warmup.days,
        discovered_instruments=len(pairs),
        economic_assets=len(assets),
        assessments=tuple(assessments),
        exclusions=tuple(
            sorted(exclusions, key=lambda item: (item.reason.value, item.symbol))
        ),
        funnel=counts,
        eligible=eligible,
        dependence=dependence,
        correlated_groups=groups,
        peg_disagreements=peg_disagreements(assessments, window_series),
        density=density,
        density_entries=entries,
        growth=curve,
        effect_requirements=tuple(requirements),
        cb_required_observations=cb.required_observations,
        cb_required_clusters=cb.required_clusters,
        survivorship=survivorship,
        assessment=assessment,
        series_digests=digests,
        horizon=ceiling,
    )


def _log_returns(closes: Sequence[float]) -> tuple[float, ...]:
    from fmis.universe.dependence import log_returns

    return log_returns(closes)
