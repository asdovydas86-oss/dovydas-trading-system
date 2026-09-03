"""The ceiling. **What this provider could supply if every year were used.**

**This analysis is POST-HOC and says so in its own name.** It was written after the
sealed funnel returned 38 eligible economic assets over Milestone CA's development
window, and it is not part of `CC_PREREGISTRATION_DIGEST`. Adding an analysis
after seeing a result is normally how a study talks itself into an answer — so the
one property that makes this one admissible is stated first and asserted in code:

> **It can only move the answer toward FEASIBLE.**

The sealed window is two years long and admits an instrument only if it has paid a
1,750-day warm-up before that window opens. This analysis asks the strictly more
generous question — *how many economic assets have EVER paid that warm-up, and how
many asset-years have they produced in total across the provider's whole history*
— using the **same sealed eligibility rules** at a window running from the
provider's first bar to the discovery instant. Every instrument the sealed funnel
admitted is admitted here, and more. A verdict of `INFEASIBLE` that survives this
is a verdict that survives the most favourable universe the provider can construct.

Because it is looking for evidence **against** the milestone's own conclusion
rather than for evidence supporting it, running it after seeing that conclusion is
the safe direction — and the report labels it `POST-HOC ROBUSTNESS` rather than
`MEASUREMENT`, so no reader can mistake it for pre-registered.

**It reads no outcome.** A listing date, a last bar and a warm-up are timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fmis.universe.models import UniverseError, require_count, require_text
from fmis.universe.preregistration import DEPTH_BARS_PER_YEAR, MIN_MEASUREMENT_YEARS

__all__ = [
    "AssetHorizon",
    "HorizonCeiling",
    "asset_horizon",
    "horizon_ceiling",
]


@dataclass(frozen=True, slots=True)
class AssetHorizon:
    """One asset's total measurable lifetime, warm-up already paid."""

    asset_id: str
    listed_at: datetime
    last_bar: datetime
    warmup_days: int
    usable_years: float

    def __post_init__(self) -> None:
        require_text(self.asset_id, "asset_id")
        if self.usable_years < 0.0:
            raise UniverseError(
                f"{self.asset_id}: a negative usable span is not a short one; the "
                "boundaries crossed and the value should be zero"
            )

    @property
    def qualifies(self) -> bool:
        return self.usable_years >= MIN_MEASUREMENT_YEARS

    def payload(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "listed_at": self.listed_at.isoformat(),
            "last_bar": self.last_bar.isoformat(),
            "warmup_days": self.warmup_days,
            "usable_years": self.usable_years,
            "qualifies": self.qualifies,
        }


def asset_horizon(
    *,
    asset_id: str,
    listed_at: datetime,
    last_bar: datetime,
    warmup: timedelta,
) -> AssetHorizon:
    """One asset's usable lifetime: from warm-up completion to its final bar."""
    if not isinstance(warmup, timedelta):
        raise UniverseError("warmup must be a timedelta")
    ready = listed_at + warmup
    span = 0.0 if last_bar <= ready else (last_bar - ready).days / DEPTH_BARS_PER_YEAR
    return AssetHorizon(
        asset_id=asset_id,
        listed_at=listed_at,
        last_bar=last_bar,
        warmup_days=warmup.days,
        usable_years=span,
    )


@dataclass(frozen=True, slots=True)
class HorizonCeiling:
    """The most this provider can ever supply, under the sealed rules.

    ``projected_admissions`` is a **projection**, marked as one: it multiplies
    measured asset-years by a measured admission density, and the density is
    Milestone CA's rather than a full-universe replay's.
    """

    candidate_assets: int
    qualifying_assets: int
    total_asset_years: float
    admissions_per_asset_year: float
    projected_admissions: int
    required_admissions: int
    required_clusters: int
    is_post_hoc: bool
    note: str

    def __post_init__(self) -> None:
        require_count(self.candidate_assets, "candidate_assets")
        require_count(self.qualifying_assets, "qualifying_assets")
        require_text(self.note, "note")
        if not self.is_post_hoc:
            raise UniverseError(
                "this analysis is post-hoc by construction and may not be "
                "presented as pre-registered. The flag is not settable to False"
            )
        if self.qualifying_assets > self.candidate_assets:
            raise UniverseError(
                "more qualifying assets than candidates; the counts describe two "
                "different universes"
            )

    @property
    def admission_shortfall(self) -> int:
        """How many admissions short of Milestone CB's requirement the ceiling is."""
        return max(0, self.required_admissions - self.projected_admissions)

    @property
    def cluster_shortfall(self) -> int:
        return max(0, self.required_clusters - self.qualifying_assets)

    @property
    def reaches_requirement(self) -> bool:
        """Whether the ceiling clears **both** dimensions CB's requirement names."""
        return (
            self.projected_admissions >= self.required_admissions
            and self.qualifying_assets >= self.required_clusters
        )

    def payload(self) -> dict[str, Any]:
        return {
            "candidate_assets": self.candidate_assets,
            "qualifying_assets": self.qualifying_assets,
            "total_asset_years": self.total_asset_years,
            "admissions_per_asset_year": self.admissions_per_asset_year,
            "projected_admissions": self.projected_admissions,
            "required_admissions": self.required_admissions,
            "required_clusters": self.required_clusters,
            "admission_shortfall": self.admission_shortfall,
            "cluster_shortfall": self.cluster_shortfall,
            "reaches_requirement": self.reaches_requirement,
            "is_post_hoc": self.is_post_hoc,
            "note": self.note,
        }


def horizon_ceiling(
    horizons,
    *,
    admissions_per_asset_year: float,
    required_admissions: int,
    required_clusters: int,
) -> HorizonCeiling:
    """Aggregate every asset's lifetime into the provider's ceiling.

    Only assets clearing `MIN_MEASUREMENT_YEARS` contribute, and they contribute
    their **whole** usable lifetime rather than the two years the sealed window
    allows — which is precisely why this is the generous bound.
    """
    items = tuple(horizons)
    qualifying = [item for item in items if item.qualifies]
    years = sum(item.usable_years for item in qualifying)
    admissions = int(years * admissions_per_asset_year)
    return HorizonCeiling(
        candidate_assets=len(items),
        qualifying_assets=len(qualifying),
        total_asset_years=years,
        admissions_per_asset_year=admissions_per_asset_year,
        projected_admissions=admissions,
        required_admissions=required_admissions,
        required_clusters=required_clusters,
        is_post_hoc=True,
        note=(
            f"POST-HOC ROBUSTNESS, not pre-registered. {len(qualifying)} of "
            f"{len(items)} economic assets have ever paid the warm-up and cleared "
            f"{MIN_MEASUREMENT_YEARS} usable year(s), contributing "
            f"{years:,.1f} asset-years in total across the provider's ENTIRE "
            f"history — every year of it, not the sealed two-year window. At "
            f"{admissions_per_asset_year:.3f} admissions per asset-year that "
            f"projects {admissions:,} admissions against the {required_admissions:,} "
            f"required, and {len(qualifying)} clusters against the "
            f"{required_clusters:,} required. This bound is strictly more "
            "favourable than the sealed measurement, so it can only move the "
            "answer toward FEASIBLE"
        ),
    )
