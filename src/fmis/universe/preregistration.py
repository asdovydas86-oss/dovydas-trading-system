"""**Milestone CC's frozen pre-registration. Sealed before the universe was measured.**

Milestone CA sealed a hypothesis before measuring an effect. CC seals something
different and, for a feasibility study, more dangerous to leave unsealed: **the
rules that decide which instruments count.** A universe assembled after seeing how
large it turned out to be is not a measurement of what is available — it is a
number chosen to clear a bar, and the bar here (roughly 467 clusters) is one a
determined analyst could reach by loosening a history requirement or a liquidity
floor until it was reached.

So every threshold, every set, every window, every ordering and every verdict
boundary below was fixed and its SHA-256 recorded in `CC_PREREGISTRATION_DIGEST`
**before the full-universe funnel was run**.
`tests/test_universe_preregistration.py` recomputes the digest from the content
and fails if the two disagree, and a mutation suite asserts that changing any
scientifically material field moves it.

**What CC asks.**

> Can a research universe be constructed from this repository's existing provider
> that supplies enough *independent information* to resolve the +0.10 ATR swing
> admission effect Milestone CA declared and Milestone CB found unresolvable at
> 155 admissions over 15 symbols?

**What CC deliberately does not ask.** Whether an admission edge exists — CA's
`NO_EDGE` stands untouched. Whether the strategy should trade — no verdict here
can approve anything, and `FeasibilityVerdict.is_approved_for_trading` is `False`
for every member. Whether a different admission rule would admit more instants —
CC changes no production constant and a control asserts it.

**The one constraint that turns out to dominate everything.** The production
context role is the weekly timeframe at a 250-candle analysis window, so every
measured instant needs 1,750 days — 4.79 years — of history *before* the
measurement window opens. That number is not restated here: it is derived by
`fmis.swing_setup.research_warmup.derive_warmup` from the production constants at
run time, so a change to the production analysis window reaches this
pre-registration instead of being contradicted by it.

**Contamination rules.** Historical *availability* is a design property and may be
inspected: how much history an instrument has is knowable from bar timestamps and
says nothing about what the strategy earned on it. Realised *outcomes* on the
protected holdout may not shape any threshold, ordering or eligibility rule here,
and `fmis.universe.controls` asserts non-vacuously that no CC decision path reads
one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Final

from fmis.swing_lab.admission_preregistration import (
    CA_PREREGISTRATION_DIGEST,
    CA_PREREGISTRATION_ID,
    MIN_ADMISSION_EDGE_ATR,
)
# Sample boundaries are IMPORTED from Milestone BY, never restated. A CC window
# and a CA result must describe the same instants by construction; a date retyped
# here could drift and the two milestones would silently stop being comparable.
from fmis.swing_lab.preregistration import SAMPLES
from fmis.universe.identity import identity_rules_payload
from fmis.universe.models import (
    FeasibilityVerdict,
    SurvivorshipClass,
    UniverseError,
    require_text,
)

__all__ = [
    "CC_PREREGISTRATION_ID",
    "CC_PREREGISTRATION_DIGEST",
    "CC_RESEARCH_QUESTION",
    "CC_PROVIDER",
    "CC_DISCOVERY_RULE",
    "ELIGIBLE_QUOTE_ASSET",
    "DEPTH_INTERVAL",
    "DEPTH_BARS_PER_YEAR",
    "MIN_MEASUREMENT_YEARS",
    "MAX_MISSING_FRACTION",
    "MAX_GAP_BARS",
    "MIN_MEDIAN_QUOTE_VOLUME",
    "REPRESENTATIVE_RULE",
    "UNIVERSE_ORDERING_RULE",
    "UNIVERSE_GROWTH_SIZES",
    "EFFECT_SIZE_GRID",
    "PRIMARY_EFFECT_ATR",
    "DEPENDENCE_SCENARIOS",
    "DENSITY_SUBSAMPLE_SIZE",
    "DENSITY_SUBSAMPLE_SEED",
    "CC_VERDICT_RULES",
    "CC_REFUTATION_CONDITIONS",
    "CC_LIMITATIONS",
    "CcPreregistration",
    "CC_PRE_REGISTRATION",
    "cc_preregistration_digest",
    "verify_cc_preregistration",
    "representative_of",
    "measurement_window",
]

CC_PREREGISTRATION_ID: Final[str] = "cc-universe-feasibility-v1"

CC_RESEARCH_QUESTION: Final[str] = (
    "Can a research universe constructed from Binance public spot market data "
    "supply enough INDEPENDENT information to resolve the +0.10 ATR swing "
    "admission effect that Milestone CA declared and Milestone CB found "
    "unresolvable at 155 matched admissions over 15 symbol clusters? This is a "
    "question about experimental design and available information. It is NOT a "
    "question about whether an admission edge exists, NOT a strategy study, and "
    "no answer to it approves trading of any kind."
)

CC_PROVIDER: Final[str] = "binance-public-spot"

CC_DISCOVERY_RULE: Final[str] = (
    "Every instrument returned by GET /api/v3/exchangeInfo?permissions=SPOT, an "
    "unauthenticated read-only endpoint, at one discovery instant recorded from "
    "the provider's own serverTime. No hand-written symbol list is used and none "
    "is maintained: a list would silently stop tracking listings and delistings, "
    "and the delistings are the half that carries the survivorship information. "
    "Instruments the endpoint no longer returns at all are unrecoverable through "
    "this provider and are recorded as an unmeasurable gap rather than assumed "
    "empty."
)

#: The single quote currency the universe is cut against.
#:
#: Not a preference — a comparability requirement. Milestone CA's effect is
#: measured in ATR units of the quote currency and its +0.10 ATR bar is derived
#: from a cost in USDT notional. A BTC-quoted pair's ATR is denominated in BTC,
#: so pooling one into the same mean would add two units under one inequality —
#: the error `MetricUnit` exists to refuse. Every sample Milestones BX, BY, BZ and
#: CA measured is USDT-quoted.
ELIGIBLE_QUOTE_ASSET: Final[str] = "USDT"

#: The interval every coverage, quality, liquidity and dependence measurement is
#: taken at. Daily, deliberately: it is the coarsest interval that resolves a
#: listing date to the day, it is one request per 1,000 days so a nine-year
#: history costs four calls rather than sixty, and dependence between assets is a
#: question about co-movement rather than about intraday microstructure. The
#: production execution interval is 4h and is NOT downloaded for ineligible
#: instruments — see the staged funnel.
DEPTH_INTERVAL: Final[str] = "1d"

#: Bars per year at `DEPTH_INTERVAL`. Crypto spot trades every day.
DEPTH_BARS_PER_YEAR: Final[float] = 365.25

#: The shortest measurement window an asset may contribute, in years.
#:
#: One year. Chosen so that an asset contributes at least one full annual cycle of
#: regimes rather than a single quarter's trend, and stated before the funnel ran.
#: It is the parameter most likely to be argued about, so the growth curve is
#: reported against measured admissions per asset-year rather than per asset, and
#: a reader who prefers a different floor can read the consequence off the curve.
MIN_MEASUREMENT_YEARS: Final[float] = 1.0

#: The largest share of expected daily bars an asset may be missing.
#:
#: Two per cent. A market that did not print on one day in fifty over the window
#: has halts frequent enough that a 4h structural analysis over it would be
#: reading across gaps it cannot see.
MAX_MISSING_FRACTION: Final[float] = 0.02

#: The longest run of consecutive missing daily bars an asset may carry.
#:
#: Seven. A week-long outage inside a weekly-context strategy destroys the very
#: candle the context role is computed from, and an aggregate missing fraction
#: cannot see it: one seven-day hole in two years is 1 % missing and passes the
#: fraction rule. Both are checked because either alone is defeatable.
MAX_GAP_BARS: Final[int] = 7

#: The lowest median daily quote volume, in USDT, an asset may show inside the
#: measurement window to be counted as tradable.
#:
#: 100,000 USDT/day. Deliberately low — an order of magnitude below the holdout
#: universe's own ~0.7M median that Milestone BY recorded as "materially less
#: liquid" — because CC is measuring how much information *exists*, not sizing a
#: book. A high floor here would remove clusters for a reason that is about
#: execution rather than about statistics, and the feasibility answer would then
#: silently be a liquidity answer. The consequence is stated: an asset passing
#: this floor is NOT thereby executable at size.
MIN_MEDIAN_QUOTE_VOLUME: Final[float] = 100_000.0

REPRESENTATIVE_RULE: Final[str] = (
    "Among the pairs sharing one economic identity, the representative is the one "
    "whose symbol sorts first lexicographically among those with the eligible "
    "quote asset, and lexicographically overall when none has it. The rule is "
    "deterministic, uses no price, no volume and no outcome, and is therefore "
    "immune to the objection that the best-performing venue was chosen."
)

UNIVERSE_ORDERING_RULE: Final[str] = (
    "Assets enter the growth curve in descending order of usable history, ties "
    "broken by ascending economic asset id. History is a DESIGN property — it is "
    "read from bar timestamps and is knowable before any outcome is computed — so "
    "an ordering built on it cannot be an outcome-based selection. Expectancy, "
    "win rate, admission performance and every other realised result are "
    "forbidden as ordering keys, and a control asserts the ordering is unchanged "
    "when outcomes are permuted."
)

#: The universe sizes the information-growth curve is reported at. Sizes larger
#: than the measured universe are reported as PROJECTIONS and are structurally
#: distinguishable in every artifact and every rendered table.
UNIVERSE_GROWTH_SIZES: Final[tuple[int, ...]] = (
    15, 30, 50, 75, 100, 150, 200, 300, 400, 467, 500,
)

#: The primary target. **Imported from CA by identity, never retyped.**
PRIMARY_EFFECT_ATR: Final[Decimal] = Decimal(str(MIN_ADMISSION_EDGE_ATR))

#: The pre-declared effect grid. The primary target is and remains +0.10 ATR; the
#: larger members answer a different and clearly separated question — *what could
#: the feasible universe honestly test?* — and are NOT permission to restate CA's
#: question after seeing the result.
EFFECT_SIZE_GRID: Final[tuple[Decimal, ...]] = (
    Decimal("0.10"), Decimal("0.20"), Decimal("0.30"), Decimal("0.50"),
)

#: The three dependence scenarios every design figure is reported under.
#:
#: CC measures between-asset dependence from returns and cannot measure it from
#: the paired admission effect without first spending the very budget it is
#: assessing. So no single scalar is forced. The scenarios bracket the answer:
#:
#: * ``independent`` — zero between-asset dependence. This is exactly the
#:   assumption CA's own ~4,800 figure makes, kept so the baseline is visible.
#: * ``residual`` — the measured mean pairwise correlation of daily log returns
#:   AFTER the equal-weight market factor is removed. CA's estimand is a paired
#:   within-symbol difference against a volatility-matched control, so the market
#:   factor is largely differenced out of it; the residual correlation is the
#:   closest strategy-outcome-independent proxy available.
#: * ``raw`` — the measured mean pairwise correlation of daily log returns with
#:   the market factor left in. An UPPER bound on dependence for this estimand,
#:   not an estimate of it.
DEPENDENCE_SCENARIOS: Final[tuple[str, ...]] = ("independent", "residual", "raw")

#: How many eligible assets the admission-density measurement replays.
#:
#: A full-universe replay costs roughly five minutes per symbol per two-year
#: window under the production fact path, so measuring every eligible asset is not
#: affordable and pretending otherwise would produce a study that never finished.
#: A bounded subsample is drawn instead, its size fixed here, and every figure
#: derived from it is reported with the sampling uncertainty it actually carries.
DENSITY_SUBSAMPLE_SIZE: Final[int] = 12

#: The subsample's seed. Derived by SHA-256 over the pre-registration id rather
#: than typed, so it is stable across processes and `PYTHONHASHSEED` values and
#: cannot have been chosen after seeing which assets it selected.
DENSITY_SUBSAMPLE_SEED: Final[str] = hashlib.sha256(
    CC_PREREGISTRATION_ID.encode("utf-8")
).hexdigest()

CC_VERDICT_RULES: Final[tuple[str, ...]] = (
    "FEASIBLE — the measured eligible universe, after economic-identity collapse "
    "and after the residual dependence scenario is applied, supplies at least the "
    "effective cluster count and admission count Milestone CB's machinery "
    "requires for the +0.10 ATR target, AND the survivorship classification is "
    "not CURRENT_SURVIVOR_ONLY.",
    "FEASIBLE_WITH_LIMITATIONS — the requirement is met under the independent "
    "scenario but not under the residual one, or it is met but the survivorship "
    "classification, the liquidity evidence or the dependence measurement carries "
    "a limitation that materially weakens the design.",
    "INFEASIBLE — the requirement is not met under ANY of the three dependence "
    "scenarios, including the most favourable one. A universe that cannot reach "
    "the target even when every asset is assumed independent cannot reach it.",
    "INDETERMINATE — a measurement CC depends on could not be taken at all: the "
    "provider did not answer, no dependence estimate could be formed, or the "
    "admission-density subsample produced no measurement. Absence of evidence is "
    "reported as absence of evidence and never as INFEASIBLE.",
)

CC_REFUTATION_CONDITIONS: Final[tuple[str, ...]] = (
    "A universe of at least 467 economic assets, each carrying the derived "
    "production warm-up plus MIN_MEASUREMENT_YEARS of usable history at "
    "DEPTH_INTERVAL, passing the data-quality and liquidity rules, would refute a "
    "verdict of INFEASIBLE on cluster count.",
    "A measured residual between-asset correlation indistinguishable from zero "
    "would refute the claim that dependence binds, and would make the "
    "independent-scenario figures the operative ones.",
    "An admission density materially above CA's ~5.2 admissions per symbol-year "
    "across the eligible universe would reduce the required cluster count "
    "proportionally and could move the verdict.",
    "A provider or data source that returns instruments absent from this "
    "provider's exchangeInfo would refute the survivorship classification and "
    "could move it toward SURVIVORSHIP_AWARE.",
)

CC_LIMITATIONS: Final[tuple[str, ...]] = (
    "CC-1 — THE DEPENDENCE PROXY IS NOT THE ESTIMAND. CC measures between-asset "
    "correlation of daily returns, not between-asset correlation of the paired "
    "admission effect. The latter needs the admission outcomes CC exists to "
    "decide whether to acquire. The three sealed scenarios bracket the answer; "
    "none of them IS the answer, and every design figure is conditional on which "
    "one is read.",
    "CC-2 — ADMISSION DENSITY IS MEASURED ON A SUBSAMPLE. A full-universe replay "
    "is not affordable, so density is measured on DENSITY_SUBSAMPLE_SIZE assets "
    "drawn by a sealed seed and projected to the universe with its sampling "
    "interval attached. Every universe-level admission count is therefore a "
    "PROJECTION and is labelled as one.",
    "CC-3 — SURVIVORSHIP RETENTION IS INCOMPLETE AND ITS GAP IS UNMEASURABLE. "
    "Binance retains delisted spot pairs in exchangeInfo with their klines "
    "history, which is why a partially survivorship-aware universe is possible at "
    "all. Retention is demonstrably not total — at least one historical pair is "
    "absent from both exchangeInfo and klines — and the size of the absent set "
    "cannot be measured from inside the provider. It is recorded as unmeasurable, "
    "never as zero.",
    "CC-4 — HISTORICAL LIQUIDITY IS A VOLUME PROXY, NOT A BOOK. Quote volume "
    "inside the window is the best historically defensible evidence this provider "
    "offers. It is not depth, not spread and not slippage, and an asset passing "
    "MIN_MEDIAN_QUOTE_VOLUME is not thereby executable at size.",
    "CC-5 — ELIGIBILITY IS MEASURED AT DAILY RESOLUTION. Data quality is assessed "
    "on daily bars because assessing 4h bars across the whole discovered universe "
    "would cost six times the download for a decision most instruments fail on "
    "history alone. A daily series can be complete while its 4h series is not, so "
    "the quality figures are an upper bound on 4h completeness.",
    "CC-6 — THE +0.10 ATR BAR IS CA'S AND IS NOT REOPENED. The effect grid exists "
    "to say what a smaller universe could honestly test. Reading a larger member "
    "of it as the answer to CA's question would be restating the hypothesis after "
    "seeing the result.",
)


def measurement_window() -> tuple[datetime, datetime]:
    """CC's measurement window. **Milestone BY's development boundaries, imported.**

    The development sample is used because it is the one sample whose realised
    outcomes a design decision is permitted to have been informed by — and CC does
    not read even those, because nothing here reads an outcome at all. The holdout
    is neither opened nor needed: how much history an instrument has is knowable
    without measuring anything that happened on it.
    """
    for spec in SAMPLES:
        if spec.name == "development":
            return spec.signal_start, spec.signal_end
    raise UniverseError(  # pragma: no cover - BY always declares development
        "Milestone BY declares no sample named 'development'"
    )


def representative_of(pairs):
    """`REPRESENTATIVE_RULE`, as code. **No price, no volume, no outcome.**

    Raises:
        UniverseError: ``pairs`` is empty.
    """
    members = tuple(pairs)
    if not members:
        raise UniverseError("an economic asset with no pairs has no representative")
    preferred = [item for item in members if item.quote_asset == ELIGIBLE_QUOTE_ASSET]
    pool = preferred or list(members)
    return min(pool, key=lambda item: item.symbol)


@dataclass(frozen=True, slots=True)
class CcPreregistration:
    """Everything CC froze, in one digestible object."""

    preregistration_id: str
    research_question: str
    provider: str
    discovery_rule: str
    eligible_quote_asset: str
    depth_interval: str
    depth_bars_per_year: float
    min_measurement_years: float
    max_missing_fraction: float
    max_gap_bars: int
    min_median_quote_volume: float
    representative_rule: str
    ordering_rule: str
    growth_sizes: tuple[int, ...]
    effect_grid: tuple[Decimal, ...]
    primary_effect: Decimal
    dependence_scenarios: tuple[str, ...]
    density_subsample_size: int
    density_subsample_seed: str
    verdict_rules: tuple[str, ...]
    refutation_conditions: tuple[str, ...]
    limitations: tuple[str, ...]
    ca_preregistration_id: str
    ca_preregistration_digest: str
    identity_rules: dict[str, Any]

    def __post_init__(self) -> None:
        for field in (
            "preregistration_id", "research_question", "provider", "discovery_rule",
            "eligible_quote_asset", "depth_interval", "representative_rule",
            "ordering_rule", "density_subsample_seed", "ca_preregistration_id",
            "ca_preregistration_digest",
        ):
            require_text(getattr(self, field), field)
        for field in ("verdict_rules", "refutation_conditions", "limitations",
                      "growth_sizes", "effect_grid", "dependence_scenarios"):
            value = getattr(self, field)
            if not isinstance(value, tuple) or not value:
                raise UniverseError(f"{field} must be a non-empty tuple")
        if self.primary_effect not in self.effect_grid:
            raise UniverseError(
                f"the primary effect {self.primary_effect} is not in the declared "
                "effect grid; a target the grid does not report cannot be the "
                "target the grid is read against"
            )
        if self.density_subsample_size < 1:
            raise UniverseError("density_subsample_size must be at least 1")
        if not 0.0 < self.min_measurement_years:
            raise UniverseError("min_measurement_years must be positive")
        if not 0.0 <= self.max_missing_fraction <= 1.0:
            raise UniverseError("max_missing_fraction must lie in [0, 1]")
        if self.max_gap_bars < 1:
            raise UniverseError("max_gap_bars must be at least 1")
        if self.min_median_quote_volume < 0.0:
            raise UniverseError("min_median_quote_volume must be non-negative")

    def payload(self) -> dict[str, Any]:
        """The canonical content the seal is taken over. **Every material field.**"""
        return {
            "preregistration_id": self.preregistration_id,
            "research_question": self.research_question,
            "provider": self.provider,
            "discovery_rule": self.discovery_rule,
            "eligible_quote_asset": self.eligible_quote_asset,
            "depth_interval": self.depth_interval,
            "depth_bars_per_year": self.depth_bars_per_year,
            "min_measurement_years": self.min_measurement_years,
            "max_missing_fraction": self.max_missing_fraction,
            "max_gap_bars": self.max_gap_bars,
            "min_median_quote_volume": self.min_median_quote_volume,
            "representative_rule": self.representative_rule,
            "ordering_rule": self.ordering_rule,
            "growth_sizes": list(self.growth_sizes),
            "effect_grid": [str(item) for item in self.effect_grid],
            "primary_effect": str(self.primary_effect),
            "dependence_scenarios": list(self.dependence_scenarios),
            "density_subsample_size": self.density_subsample_size,
            "density_subsample_seed": self.density_subsample_seed,
            "verdict_rules": list(self.verdict_rules),
            "refutation_conditions": list(self.refutation_conditions),
            "limitations": list(self.limitations),
            "ca_preregistration_id": self.ca_preregistration_id,
            "ca_preregistration_digest": self.ca_preregistration_digest,
            "identity_rules": self.identity_rules,
            "survivorship_vocabulary": [item.value for item in SurvivorshipClass],
            "verdict_vocabulary": [item.value for item in FeasibilityVerdict],
        }


CC_PRE_REGISTRATION: Final[CcPreregistration] = CcPreregistration(
    preregistration_id=CC_PREREGISTRATION_ID,
    research_question=CC_RESEARCH_QUESTION,
    provider=CC_PROVIDER,
    discovery_rule=CC_DISCOVERY_RULE,
    eligible_quote_asset=ELIGIBLE_QUOTE_ASSET,
    depth_interval=DEPTH_INTERVAL,
    depth_bars_per_year=DEPTH_BARS_PER_YEAR,
    min_measurement_years=MIN_MEASUREMENT_YEARS,
    max_missing_fraction=MAX_MISSING_FRACTION,
    max_gap_bars=MAX_GAP_BARS,
    min_median_quote_volume=MIN_MEDIAN_QUOTE_VOLUME,
    representative_rule=REPRESENTATIVE_RULE,
    ordering_rule=UNIVERSE_ORDERING_RULE,
    growth_sizes=UNIVERSE_GROWTH_SIZES,
    effect_grid=EFFECT_SIZE_GRID,
    primary_effect=PRIMARY_EFFECT_ATR,
    dependence_scenarios=DEPENDENCE_SCENARIOS,
    density_subsample_size=DENSITY_SUBSAMPLE_SIZE,
    density_subsample_seed=DENSITY_SUBSAMPLE_SEED,
    verdict_rules=CC_VERDICT_RULES,
    refutation_conditions=CC_REFUTATION_CONDITIONS,
    limitations=CC_LIMITATIONS,
    ca_preregistration_id=CA_PREREGISTRATION_ID,
    ca_preregistration_digest=CA_PREREGISTRATION_DIGEST,
    identity_rules=identity_rules_payload(),
)


def cc_preregistration_digest(
    preregistration: CcPreregistration = CC_PRE_REGISTRATION,
) -> str:
    """SHA-256 over the canonical content. **The seal.**

    `sort_keys` is on so an editor reordering a dict literal does not move the
    digest, while every *sequence* keeps declaration order because the order of
    the growth sizes and the effect grid is part of what was frozen. Milestone
    BY's function, reproduced for BY's reasons.
    """
    if not isinstance(preregistration, CcPreregistration):
        raise TypeError("preregistration must be a CcPreregistration")
    canonical = json.dumps(
        preregistration.payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


#: **The seal, pinned.** Recomputed and compared by
#: `tests/test_universe_preregistration.py`. A diff that changes this line changed
#: the pre-registration with it, and every figure measured under the old digest
#: describes a different study.
CC_PREREGISTRATION_DIGEST: Final[str] = (
    "ef6f39508a3d183c88618c727ba65fd8c6ffdcada4452660aaa4ad74a0021bac"
)


def verify_cc_preregistration(digest: str) -> bool:
    """Whether a recorded digest is the one this module currently seals."""
    if not isinstance(digest, str):
        raise TypeError("digest must be a str")
    return digest == cc_preregistration_digest()
