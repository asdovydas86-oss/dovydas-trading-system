"""How many admissions an asset-year actually produces. **Measured, not assumed.**

The ~467-symbol figure Milestone CB derived is ``4,823 required admissions``
divided by ``155 / 15 / 2 years ~= 5.2 admissions per symbol-year``. That divisor
is an assumption about a universe of fifteen large, liquid, long-listed pairs, and
Milestone CC's eligible universe is neither as liquid nor as long-listed. If
density falls with liquidity or with listing age, the required symbol count rises
by the same factor and the 467 is optimistic; if it rises, the reverse.

**The production admission rule is used unchanged.** `capture_for_window` replays
history through `fmis.swing_lab.variants.BASELINE_VARIANT`, which supplies no
override at all and is therefore the live product's own code path with its own
constants. `CONFIRMATION_LOOKBACK_BARS`, `MINIMUM_AGREEING_FAMILIES`, the
context-role semantics, the trend logic, the regime logic and the geometry are
untouched, and a production-safety test asserts their values are what they were
before this milestone. **This is measurement, not tuning.**

**An admission is not an outcome.** Counting how often the engine says *yes* reads
no forward excursion, no return and no trade result — which is why this can be run
over any window, including one overlapping the protected holdout, without opening
anything the holdout protects. `count_admissions` is asserted by a control to
touch no outcome field.

**Three densities already exist and are used first.** Milestone CA published
admission counts for three disjoint samples over 36 distinct symbols, one of which
— the holdout — is materially less liquid than the others by CA's own record. Those
are reproduced here from sealed constants before any new replay is run, because
three independent measurements that already exist are better evidence about the
*stability* of density than one new one, and they cost nothing.
"""

from __future__ import annotations

import hashlib
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from fmis.swing_lab.admission_power import CA_PUBLISHED
from fmis.swing_lab.preregistration import SAMPLES
from fmis.universe.models import UniverseError, require_count, require_text
from fmis.universe.preregistration import DENSITY_SUBSAMPLE_SEED

__all__ = [
    "AssetDensity",
    "DensitySummary",
    "published_densities",
    "summarise_density",
    "subsample_for_density",
    "count_admissions",
]


@dataclass(frozen=True, slots=True)
class AssetDensity:
    """One asset's admission density, and where the number came from.

    ``source`` distinguishes a figure reproduced from Milestone CA's sealed
    publication from one this milestone replayed. A summary mixing the two without
    saying which is which would let a reader attribute CC's evidence to CA or the
    reverse.
    """

    asset_id: str
    admissions: int
    usable_years: float
    source: str

    def __post_init__(self) -> None:
        require_text(self.asset_id, "asset_id")
        require_text(self.source, "source")
        require_count(self.admissions, "admissions")
        if isinstance(self.usable_years, bool) or not isinstance(
            self.usable_years, (int, float)
        ):
            raise UniverseError("usable_years must be a real number")
        if float(self.usable_years) <= 0.0:
            raise UniverseError(
                f"{self.asset_id}: usable_years is {self.usable_years}. A density "
                "per zero years is a division by zero wearing a rate's clothes"
            )

    @property
    def per_year(self) -> float:
        return self.admissions / self.usable_years

    def payload(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "admissions": self.admissions,
            "usable_years": self.usable_years,
            "per_year": self.per_year,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class DensitySummary:
    """The density distribution, and how concentrated it is.

    ``largest_share`` is the share of all admissions produced by the single most
    prolific asset. Milestone CC asks for it explicitly because a universe in
    which half the admissions come from three assets has three experimental units
    doing the work of a hundred, and the raw asset count would be reporting
    information that is not there.
    """

    assets: int
    total_admissions: int
    total_asset_years: float
    mean_per_asset_year: float
    median_per_asset_year: float
    minimum_per_asset_year: float
    maximum_per_asset_year: float
    largest_share: float
    top_decile_share: float
    sources: tuple[str, ...]

    def __post_init__(self) -> None:
        require_count(self.assets, "assets", minimum=1)
        require_count(self.total_admissions, "total_admissions")
        if not isinstance(self.sources, tuple) or not self.sources:
            raise UniverseError("a density summary must name its sources")

    @property
    def pooled_per_asset_year(self) -> float:
        """Total admissions over total asset-years. **The figure growth uses.**

        Pooled rather than averaged: the mean of per-asset rates weights a
        six-month asset equally with a two-year one, and the quantity a universe
        projection needs is admissions per asset-year across the whole universe.
        """
        return self.total_admissions / self.total_asset_years

    def payload(self) -> dict[str, Any]:
        return {
            "assets": self.assets,
            "total_admissions": self.total_admissions,
            "total_asset_years": self.total_asset_years,
            "pooled_per_asset_year": self.pooled_per_asset_year,
            "mean_per_asset_year": self.mean_per_asset_year,
            "median_per_asset_year": self.median_per_asset_year,
            "minimum_per_asset_year": self.minimum_per_asset_year,
            "maximum_per_asset_year": self.maximum_per_asset_year,
            "largest_share": self.largest_share,
            "top_decile_share": self.top_decile_share,
            "sources": list(self.sources),
        }


def published_densities() -> tuple[AssetDensity, ...]:
    """Milestone CA's three samples as sample-level densities. **Sealed figures.**

    Each entry is a *sample*, not an asset: CA published per-sample admission
    counts and symbol counts but no per-symbol breakdown, so the finest grain
    available is one row per sample carrying that sample's symbol-years. The
    ``asset_id`` therefore names the sample and the limitation is visible in the
    value rather than hidden in a footnote.
    """
    spans = {spec.name: spec.years for spec in SAMPLES}
    out: list[AssetDensity] = []
    for figure in CA_PUBLISHED:
        years = spans.get(figure.sample)
        if years is None:  # pragma: no cover - CA and BY name the same samples
            raise UniverseError(f"Milestone BY declares no sample {figure.sample!r}")
        out.append(
            AssetDensity(
                asset_id=f"ca:{figure.sample}",
                admissions=figure.matched,
                usable_years=figure.symbols * years,
                source=(
                    f"Milestone CA, {figure.source} — {figure.matched} matched "
                    f"admissions over {figure.symbols} symbols and {years:.3f} years"
                ),
            )
        )
    return tuple(out)


def summarise_density(entries: Sequence[AssetDensity]) -> DensitySummary:
    """Pool a set of density measurements and report their concentration.

    Raises:
        UniverseError: ``entries`` is empty. A density summary over nothing would
            report a rate of zero, which reads as *the engine admits nothing*
            rather than as *nothing was measured*.
    """
    items = tuple(entries)
    if not items:
        raise UniverseError(
            "no density measurement was supplied. An empty summary would report a "
            "rate rather than an absence, and the two must not read alike"
        )
    rates = sorted(item.per_year for item in items)
    admissions = [item.admissions for item in items]
    total = sum(admissions)
    ordered = sorted(admissions, reverse=True)
    decile = max(1, round(len(ordered) * 0.1))
    return DensitySummary(
        assets=len(items),
        total_admissions=total,
        total_asset_years=sum(item.usable_years for item in items),
        mean_per_asset_year=statistics.fmean(rates),
        median_per_asset_year=statistics.median(rates),
        minimum_per_asset_year=rates[0],
        maximum_per_asset_year=rates[-1],
        largest_share=(ordered[0] / total) if total else 0.0,
        top_decile_share=(sum(ordered[:decile]) / total) if total else 0.0,
        sources=tuple(sorted({item.source for item in items})),
    )


def subsample_for_density(
    asset_ids: Sequence[str], *, size: int, seed: str = DENSITY_SUBSAMPLE_SEED
) -> tuple[str, ...]:
    """Draw the assets a new density replay will measure. **Seeded, not chosen.**

    Each candidate is scored by SHA-256 over ``seed + asset_id`` and the lowest
    scores win. That is a deterministic function of the sealed seed and the asset
    name — stable across processes and across `PYTHONHASHSEED`, independent of the
    order the candidates arrive in, and impossible to have selected after seeing
    which assets it picked, because the seed is the SHA-256 of the
    pre-registration id and the id was fixed first.

    **No price, no volume, no outcome enters the draw.** Selecting the subsample
    on liquidity would make the measured density a liquid universe's density; on
    performance it would be outcome-based selection outright.
    """
    require_count(size, "size", minimum=1)
    require_text(seed, "seed")
    unique = sorted(set(asset_ids))
    if not unique:
        raise UniverseError("no candidate assets were supplied to sample from")
    scored = sorted(
        unique,
        key=lambda name: hashlib.sha256(f"{seed}:{name}".encode("utf-8")).hexdigest(),
    )
    return tuple(sorted(scored[:size]))


def count_admissions(
    symbols: Sequence[str],
    *,
    measurement_start: datetime,
    measurement_end: datetime,
    run_at: datetime,
    transport=None,
) -> dict[str, int]:
    """Replay the **production** admission rule and count what it admitted.

    Returns admissions per symbol, including zero for a symbol the engine never
    admitted — an explicit zero and a missing key mean different things, and a
    density summary must be able to tell them apart.

    Nothing here reads a forward outcome. `capture_for_window` freezes the
    admitted candidates and their bars; this function counts the candidates and
    discards everything else, so no realised excursion, return or trade result is
    reachable from its output.

    Raises:
        SwingLabError: the window is not satisfiable for some symbol. It is NOT
            quietly shortened — a symbol measured over a different window than the
            others would contribute a density from a different market period.
    """
    # Imported here rather than at module scope: the replay path pulls in the
    # whole production fact chain, and the summary-statistic functions above must
    # stay importable without it.
    from fmis.swing_lab.validation_study import capture_for_window

    requested = tuple(symbols)
    if not requested:
        raise UniverseError("at least one symbol must be requested")
    capture = capture_for_window(
        requested,
        measurement_start=measurement_start,
        measurement_end=measurement_end,
        run_at=run_at,
        transport=transport,
    )
    counts = {symbol: 0 for symbol in requested}
    for candidate in capture.candidates:
        counts[candidate.symbol] = counts.get(candidate.symbol, 0) + 1
    return counts


#: What a new density measurement can and cannot settle, carried with the module.
DENSITY_LIMITATIONS: Final[tuple[str, ...]] = (
    "Milestone CA published per-sample admission counts, not per-symbol ones, so "
    "the reproduced densities are sample-level and their concentration cannot be "
    "read from CA's publication.",
    "A new replay measures a bounded subsample. Its pooled rate carries the "
    "sampling uncertainty of that subsample and every universe-level admission "
    "count derived from it is a projection.",
)
