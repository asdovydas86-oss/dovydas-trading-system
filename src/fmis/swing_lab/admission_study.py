"""Milestone CA's experiment: does FMITS admission beat a matched null?

This module runs what `fmis.swing_lab.admission_preregistration` sealed. It owns
no threshold, no horizon, no seed and no criterion — every one of those is read
from the pre-registration, and a study whose manifest does not carry that
pre-registration's digest cannot promote anything.

**The measurement, in one paragraph.** Each of the three samples is cut from a
Milestone BZ capture and replayed into `DecisionInstant`s using production's own
opportunity tracker, so CA's `ADMITTED` stage is the live product's decision
rather than a reconstruction of it. For every admission and every sealed null
family, controls are drawn under the sealed matching rule. The **effect** is the
mean, over admissions, of the admission's forward ATR excursion minus the mean of
its own controls' — a *paired* difference, because a matched null answered
against an unmatched aggregate would import every symbol and period difference
into the result. Uncertainty comes from a symbol-clustered bootstrap; the null
comes from pairing two independent control draws, which is centred at zero by
construction and carries the same sample size.

**The null is NOT symbol-clustered, and the sealed text says it is.** Independent
review found that `CA_RANDOMISATION.rationale` and the `null_percentile`
criterion both claim it "carries the same clustering ... as the observed effect".
It does not: `_empirical_null` draws one generator per record and takes a plain
mean. That claim is inside the digest and cannot be corrected without breaking
the seal, so report 0037 §22 **discloses** it instead — but this docstring is not
sealed, so it states the truth. The error is conservative in direction: the null
is wider than a clustered one, so it can only suppress a positive result, never
manufacture one, and it decided no verdict.

**Three things this module deliberately does not do.**

* It applies **no cost, no stop, no target and no exit**. CA's outcome is not a
  trade — see `CA_LIMITATIONS`' CA-1. Costs enter once, as the magnitude an
  effect must clear, and that magnitude is sealed rather than computed here.
* It **never pools universes**. Milestone BY published a wrong conclusion by
  pooling three samples into one walk-forward curve while the traded universe
  doubled mid-curve. Every statistic here carries its sample identity and a
  regression refuses a pooled curve by name.
* It **never promotes anything**. `CaVerdict.earns_forward_test` is `False` for
  every member including `ADMISSION_EDGE_CANDIDATE`, because an admission edge
  with no geometry attached is not a strategy and there is nothing to run.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from random import Random
from typing import Any, Final

from fmis.paper.models import PriceBar
from fmis.swing_lab.admission import (
    FORWARD_HORIZONS,
    AdmissionStage,
    DecisionInstant,
    ForwardOutcome,
    RaceOutcome,
    atr_series,
    forward_outcome,
    walk_decision_instants,
)
from fmis.swing_lab.admission_matching import (
    ControlDraw,
    MatchedAdmission,
    PoolIndex,
    build_pool_index,
    derive_seed,
    match_admission,
)
from fmis.swing_lab.admission_preregistration import (
    CA_EDGE_CRITERIA,
    CA_MECHANISM_CRITERIA,
    CA_NULL_FAMILIES,
    CA_PRE_REGISTRATION,
    CA_PREREGISTRATION_DIGEST,
    CA_PREREGISTRATION_ID,
    MIN_ADMISSION_EDGE_ATR,
    MIN_HORIZON_AGREEMENT,
    NULL_PERCENTILE_BAR,
    PRIMARY_HORIZON,
    CaControlSource,
    CaNullFamily,
    CaVerdict,
    is_ca_pre_registered,
    verify_ca_preregistration,
)
from fmis.swing_lab.metrics import SAMPLE_FLOOR, nearest_rank_quantile
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.persistence_artifact import (
    PersistenceCaptureArtifact,
    verify_capture_digest,
)
from fmis.swing_lab.preregistration import SAMPLES, SampleSpec
from fmis.swing_lab.robustness import concentration_of_magnitudes
from fmis.swing_lab.validation_study import MAJOR_SYMBOLS, walk_forward_boundaries
from fmis.swing_setup.models import Direction

__all__ = [
    "CA_SCHEMA_VERSION",
    "PairedRecord",
    "FamilySampleResult",
    "Criterion",
    "CaAssessment",
    "GateRung",
    "AdmissionStudy",
    "assess_ca",
    "build_sample_instants",
    "measure_family",
    "study_from_capture",
]

#: Bumped whenever a persisted CA artifact changes shape.
CA_SCHEMA_VERSION: Final[int] = 1

#: How the direction-less rungs of the gate ladder are reported. They carry no
#: production direction, so a direction-normalised return cannot be computed for
#: them and is REFUSED rather than substituted with a long's.
NO_DIRECTION_TO_NORMALISE: Final[str] = (
    "This rung is below the family tally, so production had formed no direction "
    "at these instants. A direction-normalised return is therefore undefined for "
    "them and is refused rather than computed as a long's, which would report "
    "the market's own drift as though it were a selection result. The census and "
    "the unsigned mean absolute move are stated instead, and they are NOT "
    "comparable with the directional rungs above."
)


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _race_rate(favourable: int, adverse: int) -> float | None:
    """The share of SETTLED races that resolved favourably.

    **Ambiguity is excluded from the denominator, never folded into a side.** A
    bar whose range spans both thresholds cannot say which was touched first, and
    counting it either way would move a rate by a path nobody observed. `None`
    when nothing settled — a stated absence rather than a zero, which would read
    as "never favourable" instead of "never decided".
    """
    settled = favourable + adverse
    return favourable / settled if settled else None


# ---------------------------------------------------------------------------
# 1. Building one sample's decision instants from a capture.
# ---------------------------------------------------------------------------


def build_sample_instants(
    artifact: PersistenceCaptureArtifact,
    *,
    universe: str,
    sample: SampleSpec,
    horizons: Sequence[int] = FORWARD_HORIZONS,
    atrs_by_symbol: Mapping[str, Sequence[float | None]] | None = None,
) -> tuple[
    tuple[DecisionInstant, ...],
    Mapping[str, tuple[PriceBar, ...]],
    Mapping[str, Mapping[int, str]],
]:
    """Replay one universe's captured timeline into one sample's decision instants.

    Returns the instants, the bars they resolve against, and the per-symbol map of
    admitted bar index to the production regime volatility recorded on that
    candidate — read from the capture's own candidates rather than re-derived, and
    used only to label a declared stratum.

    **The admitted set this produces is asserted, by regression, to equal the
    capture's own candidate list** symbol for symbol and bar for bar. That is
    what entitles CA to describe its `ADMITTED` stage as the live product's
    decision.
    """
    captured = artifact.universe(universe)
    limit = captured.capture.metadata.get("candle_limit")
    if not isinstance(limit, int):
        raise SwingLabError(
            f"universe {universe!r} records no candle limit; the ATR window the "
            "replay view held cannot be reproduced without it"
        )
    furthest = max(horizons)
    volatility: dict[str, dict[int, str]] = {}
    for candidate in captured.capture.candidates:
        volatility.setdefault(candidate.symbol, {})[candidate.signal_index] = (
            candidate.context_regime_volatility
        )
    boundaries = walk_forward_boundaries(
        start=sample.signal_start, end=sample.signal_end
    )

    def segment_of(moment: datetime) -> str | None:
        for lower, upper in boundaries:
            if lower <= moment < upper:
                return f"{lower.date().isoformat()}→{upper.date().isoformat()}"
        return None

    instants: list[DecisionInstant] = []
    for symbol in sorted(captured.timelines):
        if symbol not in sample.symbols:
            continue
        bars = captured.capture.bars_by_symbol[symbol]
        # The ATR walk is the single most expensive part of building a sample, and
        # development and validation share a universe. It is therefore computed
        # once per universe by the caller and handed in; recomputing it here would
        # double the cost for a number that cannot differ.
        atrs = (
            atr_series(bars, limit=limit)
            if atrs_by_symbol is None
            else atrs_by_symbol[symbol]
        )
        instants.extend(
            walk_decision_instants(
                captured.timelines[symbol],
                symbol=symbol,
                bars=bars,
                atrs=atrs,
                sample_holds=sample.holds,
                sample_name=sample.name,
                furthest_horizon=furthest,
                segment_of=segment_of,
                volatility_of=volatility.get(symbol),
            )
        )
    return tuple(instants), captured.capture.bars_by_symbol, volatility


# ---------------------------------------------------------------------------
# 2. One admission measured against one family.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PairedRecord:
    """One admission and its own controls, under one family. **The unit of CA.**

    ``control_forward`` is the *mean* over the family's draws at each horizon;
    ``control_primary_draws`` keeps every individual draw at the primary horizon
    alone, because that is what the empirical null needs and keeping all six
    horizons per draw would multiply the study's memory by six for no statistic
    that reads it.
    """

    family_id: str
    sample: str
    symbol: str
    bar_index: int
    as_of: datetime
    direction: Direction
    segment: str | None
    volatility: str
    pool_size: int
    radius_tier: int | None
    admission_forward: Mapping[int, float]
    admission_mfe: Mapping[int, float]
    admission_mae: Mapping[int, float]
    admission_race: Mapping[int, RaceOutcome]
    control_forward: Mapping[int, float]
    control_mfe: Mapping[int, float]
    control_mae: Mapping[int, float]
    control_race_favourable: Mapping[int, int]
    control_race_adverse: Mapping[int, int]
    control_race_ambiguous: Mapping[int, int]
    control_primary_draws: tuple[float, ...]

    def difference(self, horizon: int) -> float:
        """The paired difference at one horizon. **Admission minus its own controls.**"""
        admission = self.admission_forward.get(horizon)
        control = self.control_forward.get(horizon)
        if admission is None or control is None:
            raise SwingLabError(
                f"this record holds no horizon {horizon}; it holds "
                f"{sorted(self.admission_forward)}"
            )
        return admission - control

    @property
    def symbol_class(self) -> str:
        return "major" if self.symbol in MAJOR_SYMBOLS else "non_major"


class _OutcomeCache:
    """Forward outcomes for one symbol, computed once per (bar, direction).

    A pool of five hundred instants is drawn from two hundred times per
    admission, so the same control bar is measured many times over. Measuring it
    once and reading it afterwards is what keeps the run in minutes.

    **The key is (bar index, direction) and that is sufficient**, because the ATR
    is itself a function of the bar index: `fmis.swing_lab.admission.atr_series`
    produces exactly one reading per bar. So a cached outcome is already
    normalised by the right denominator and needs no rescaling — which matters
    beyond tidiness, because the ±1 ATR race compares an excursion against a
    THRESHOLD and therefore cannot be rescaled after the fact. A cache holding
    unit-denominator walks would have to recompute every race, and a race
    recomputed under a different denominator is a different measurement.
    """

    __slots__ = ("_bars", "_horizons", "_atrs", "_cache")

    def __init__(
        self,
        bars: Sequence[PriceBar],
        horizons: Sequence[int],
        atrs: Sequence[float | None],
    ) -> None:
        self._bars = bars
        self._horizons = tuple(horizons)
        self._atrs = atrs
        self._cache: dict[tuple[int, Direction], ForwardOutcome] = {}

    def outcome(self, bar_index: int, direction: Direction) -> ForwardOutcome:
        key = (bar_index, direction)
        found = self._cache.get(key)
        if found is None:
            atr = self._atrs[bar_index]
            if atr is None:  # pragma: no cover - instants without one are excluded
                raise SwingLabError(
                    f"bar {bar_index} carries no ATR; an instant without a "
                    "volatility scale is excluded before it reaches here"
                )
            found = forward_outcome(
                self._bars,
                signal_index=bar_index,
                direction=direction,
                atr=atr,
                horizons=self._horizons,
            )
            self._cache[key] = found
        return found


def _outcome_for(
    cache: _OutcomeCache, instant: DecisionInstant, direction: Direction
) -> ForwardOutcome:
    """One instant's outcome, already normalised by that instant's own ATR."""
    return cache.outcome(instant.bar_index, direction)


def measure_family(
    admissions: Sequence[DecisionInstant],
    *,
    family: CaNullFamily,
    index: PoolIndex,
    caches: Mapping[str, _OutcomeCache],
    horizons: Sequence[int],
    master_seed: int,
    matching=CA_PRE_REGISTRATION.matching,
    randomisation=CA_PRE_REGISTRATION.randomisation,
) -> tuple[tuple[PairedRecord, ...], tuple[MatchedAdmission, ...]]:
    """Draw and measure every admission's controls under one family.

    Returns the matched records and **every** matching attempt, so unmatched
    admissions are countable rather than absent.
    """
    records: list[PairedRecord] = []
    attempts: list[MatchedAdmission] = []
    for admission in admissions:
        matched = match_admission(
            admission,
            index,
            family=family,
            matching=matching,
            randomisation=randomisation,
            master_seed=master_seed,
        )
        attempts.append(matched)
        if not matched.is_matched:
            continue
        cache = caches[admission.symbol]
        if admission.direction is None:  # pragma: no cover - ADMITTED has one
            raise SwingLabError("an admitted instant carries no direction")
        own = _outcome_for(cache, admission, admission.direction)
        own_race = own.race

        totals = {h: 0.0 for h in horizons}
        mfe_totals = {h: 0.0 for h in horizons}
        mae_totals = {h: 0.0 for h in horizons}
        favourable = {h: 0 for h in horizons}
        adverse = {h: 0 for h in horizons}
        ambiguous = {h: 0 for h in horizons}
        primary_draws: list[float] = []
        for draw in matched.draws:
            control = draw.instant if draw.instant is not None else admission
            outcome = _outcome_for(cache, control, draw.direction)
            race = outcome.race
            for horizon in horizons:
                totals[horizon] += float(outcome.forward[horizon])
                mfe_totals[horizon] += float(outcome.mfe[horizon])
                mae_totals[horizon] += float(outcome.mae[horizon])
                verdict = race[horizon]
                if verdict is RaceOutcome.FAVOURABLE:
                    favourable[horizon] += 1
                elif verdict is RaceOutcome.ADVERSE:
                    adverse[horizon] += 1
                elif verdict is RaceOutcome.AMBIGUOUS:
                    ambiguous[horizon] += 1
            primary_draws.append(float(outcome.forward[PRIMARY_HORIZON]))

        count = len(matched.draws)
        if count == 0:  # pragma: no cover - a matched admission always draws
            raise SwingLabError(
                f"{admission.symbol} at bar {admission.bar_index} matched but "
                "drew no control"
            )
        records.append(
            PairedRecord(
                family_id=family.family_id,
                sample=admission.sample,
                symbol=admission.symbol,
                bar_index=admission.bar_index,
                as_of=admission.as_of,
                direction=admission.direction,
                segment=admission.segment,
                volatility=admission.context_regime_volatility,
                pool_size=matched.pool_size,
                radius_tier=matched.radius_tier,
                admission_forward={h: float(own.forward[h]) for h in horizons},
                admission_mfe={h: float(own.mfe[h]) for h in horizons},
                admission_mae={h: float(own.mae[h]) for h in horizons},
                admission_race=dict(own_race),
                control_forward={h: totals[h] / count for h in horizons},
                control_mfe={h: mfe_totals[h] / count for h in horizons},
                control_mae={h: mae_totals[h] / count for h in horizons},
                control_race_favourable=dict(favourable),
                control_race_adverse=dict(adverse),
                control_race_ambiguous=dict(ambiguous),
                control_primary_draws=tuple(primary_draws),
            )
        )
    return tuple(records), tuple(attempts)


# ---------------------------------------------------------------------------
# 3. Aggregating one (family, sample) into a result.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FamilySampleResult:
    """One null family measured on one sample. **Carries its sample identity.**

    Every figure here belongs to exactly one sample and one family. There is no
    field that could hold a pooled number, which is the structural half of the
    answer to Milestone BY's pooling defect; the other half is a regression that
    refuses a pooled curve by name.
    """

    family_id: str
    sample: str
    matched: int
    unmatched: int
    symbols: int
    effect: float | None
    effect_by_horizon: Mapping[int, float | None]
    bootstrap_low: float | None
    bootstrap_high: float | None
    null_percentile: float | None
    null_low: float | None
    null_high: float | None
    concentration: float | None
    by_direction: Mapping[str, tuple[int, float | None]]
    by_volatility: Mapping[str, tuple[int, float | None]]
    by_symbol_class: Mapping[str, tuple[int, float | None]]
    walk_forward: tuple[tuple[str, int, float | None], ...]
    radius_tiers: Mapping[str, int]
    admission_mean_mfe: Mapping[int, float | None]
    admission_mean_mae: Mapping[int, float | None]
    control_mean_mfe: Mapping[int, float | None]
    control_mean_mae: Mapping[int, float | None]
    admission_positive_rate: Mapping[int, float | None]
    admission_race_rate: Mapping[int, float | None]
    control_race_rate: Mapping[int, float | None]
    race_ambiguous: Mapping[int, int]
    clustered_admissions: int

    def payload(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "sample": self.sample,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "symbols": self.symbols,
            "effect": self.effect,
            "effect_by_horizon": {str(k): v for k, v in self.effect_by_horizon.items()},
            "bootstrap_low": self.bootstrap_low,
            "bootstrap_high": self.bootstrap_high,
            "null_percentile": self.null_percentile,
            "null_low": self.null_low,
            "null_high": self.null_high,
            "concentration": self.concentration,
            "by_direction": {k: list(v) for k, v in self.by_direction.items()},
            "by_volatility": {k: list(v) for k, v in self.by_volatility.items()},
            "by_symbol_class": {k: list(v) for k, v in self.by_symbol_class.items()},
            "walk_forward": [list(item) for item in self.walk_forward],
            "radius_tiers": dict(self.radius_tiers),
            "admission_mean_mfe": {
                str(k): v for k, v in self.admission_mean_mfe.items()
            },
            "admission_mean_mae": {
                str(k): v for k, v in self.admission_mean_mae.items()
            },
            "control_mean_mfe": {str(k): v for k, v in self.control_mean_mfe.items()},
            "control_mean_mae": {str(k): v for k, v in self.control_mean_mae.items()},
            "admission_positive_rate": {
                str(k): v for k, v in self.admission_positive_rate.items()
            },
            "admission_race_rate": {
                str(k): v for k, v in self.admission_race_rate.items()
            },
            "control_race_rate": {
                str(k): v for k, v in self.control_race_rate.items()
            },
            "race_ambiguous": {str(k): v for k, v in self.race_ambiguous.items()},
            "clustered_admissions": self.clustered_admissions,
        }


def _cohort_effect(
    records: Sequence[PairedRecord], horizon: int
) -> tuple[int, float | None]:
    """A cohort's size and its effect, **refused below the sample floor**.

    `fmis.swing_lab.metrics.SAMPLE_FLOOR`'s discipline applied to a paired
    difference: below it the count is still reported and the figure is `None`,
    so a reader sees "not enough admissions" rather than a precise-looking lie.
    """
    if len(records) < SAMPLE_FLOOR:
        return len(records), None
    return len(records), _mean([item.difference(horizon) for item in records])


def _bootstrap_interval(
    records: Sequence[PairedRecord],
    *,
    horizon: int,
    replicates: int,
    master_seed: int,
    family_id: str,
    sample: str,
) -> tuple[float | None, float | None]:
    """A 95 % interval, resampled **by symbol** rather than by admission.

    Admissions on one symbol share its drift and its regime and are not
    independent; resampling them individually would report an interval too narrow
    by exactly that dependence. The cluster is the symbol, which is the coarsest
    unit CA can afford and therefore the most conservative one available.
    """
    if len(records) < SAMPLE_FLOOR:
        return None, None
    by_symbol: dict[str, list[PairedRecord]] = {}
    for record in records:
        by_symbol.setdefault(record.symbol, []).append(record)
    symbols = sorted(by_symbol)
    generator = Random(
        derive_seed(
            master=master_seed,
            family_id=family_id,
            sample=sample,
            symbol="__bootstrap__",
            bar_index=horizon,
            replicate=replicates,
        )
    )
    effects: list[float] = []
    for _ in range(replicates):
        drawn: list[float] = []
        for _ in symbols:
            chosen = generator.choice(symbols)
            drawn.extend(item.difference(horizon) for item in by_symbol[chosen])
        value = _mean(drawn)
        if value is not None:
            effects.append(value)
    if not effects:  # pragma: no cover - symbols is non-empty here
        return None, None
    return (
        nearest_rank_quantile(effects, 0.025),
        nearest_rank_quantile(effects, 0.975),
    )


def _empirical_null(
    records: Sequence[PairedRecord],
    *,
    replicates: int,
    master_seed: int,
    family_id: str,
    sample: str,
) -> tuple[float, ...]:
    """The null distribution of the effect, from **two independent control draws**.

    For each replicate, every admission contributes the difference between two of
    its own distinct control draws. The result is centred at zero by
    construction, carries the same sample size as the observed effect, and is
    built from the same pools — so a percentile against it asks "is the admission
    further from its controls than two controls are from each other".

    **It is NOT symbol-clustered, and it is wider than the statistic it judges.**
    The sealed text claims otherwise (see the module docstring); that claim is
    inside the digest and is disclosed in report 0037 §22 rather than corrected.
    Two independent single draws have roughly twice the per-record variance of
    the observed effect's own control term, which averages two hundred — so this
    null is conservative, can only suppress a positive result, and decided no
    verdict in Milestone CA. `_bootstrap_interval` is the variance-matched,
    genuinely symbol-clustered uncertainty statement and is the one to read.

    Families whose control is the admission's own bar have a **degenerate** null:
    every draw sits on one bar, so two draws differ only when the direction rule
    is random. That is a property of those families and is reported rather than
    hidden — see `CaNullFamily.is_degenerate_at_primary`.
    """
    usable = [item for item in records if len(item.control_primary_draws) >= 2]
    if not usable:
        return ()
    effects: list[float] = []
    for replicate in range(replicates):
        drawn: list[float] = []
        for record in usable:
            generator = Random(
                derive_seed(
                    master=master_seed,
                    family_id=family_id,
                    sample=sample,
                    symbol=record.symbol,
                    bar_index=record.bar_index,
                    replicate=1_000_000 + replicate,
                )
            )
            first, second = generator.sample(
                range(len(record.control_primary_draws)), 2
            )
            drawn.append(
                record.control_primary_draws[first]
                - record.control_primary_draws[second]
            )
        value = _mean(drawn)
        if value is not None:
            effects.append(value)
    return tuple(sorted(effects))


def _percentile_of(value: float, distribution: Sequence[float]) -> float | None:
    """Where ``value`` falls in ``distribution``, as a percentage strictly below it."""
    if not distribution:
        return None
    below = sum(1 for item in distribution if item < value)
    return 100.0 * below / len(distribution)


def _aggregate(
    records: Sequence[PairedRecord],
    attempts: Sequence[MatchedAdmission],
    *,
    family: CaNullFamily,
    sample: SampleSpec,
    horizons: Sequence[int],
    master_seed: int,
    randomisation=CA_PRE_REGISTRATION.randomisation,
) -> FamilySampleResult:
    """Reduce one family's records on one sample to a reported result."""
    matched = len(records)
    unmatched = sum(1 for item in attempts if not item.is_matched)
    tiers: dict[str, int] = {}
    for attempt in attempts:
        label = "unmatched" if attempt.radius_tier is None else f"tier_{attempt.radius_tier}"
        if attempt.is_matched or attempt.unmatched_reason is not None:
            tiers[label] = tiers.get(label, 0) + 1

    # DEFECT CA-D1, found by independent review. The headline effect was the ONE
    # figure in this module exempt from `SAMPLE_FLOOR` — `_cohort_effect` refuses
    # below it, and this did not. A family with three matched admissions would
    # therefore have its `sample` criterion report "the test COULD NOT BE RUN"
    # while `development_effect` was decided as False on the very same three
    # observations, producing NO_EDGE — a refutation from a test that was never
    # run, which is exactly the defect Milestone BZ recorded as BZ-D1 and fixed
    # one layer up. Below the floor the effect is now ABSENT, so every criterion
    # reading it reports unmeasurable and the verdict is INCONCLUSIVE.
    measurable = len(records) >= SAMPLE_FLOOR
    effect = (
        _mean([item.difference(PRIMARY_HORIZON) for item in records])
        if measurable
        else None
    )
    by_horizon = {
        horizon: (
            _mean([item.difference(horizon) for item in records])
            if measurable
            else None
        )
        for horizon in horizons
    }
    low, high = _bootstrap_interval(
        records,
        horizon=PRIMARY_HORIZON,
        replicates=randomisation.bootstrap_replicates,
        master_seed=master_seed,
        family_id=family.family_id,
        sample=sample.name,
    )
    null = _empirical_null(
        records,
        replicates=randomisation.null_replicates,
        master_seed=master_seed,
        family_id=family.family_id,
        sample=sample.name,
    )
    concentration = concentration_of_magnitudes(
        (item.symbol, Decimal(str(abs(item.difference(PRIMARY_HORIZON)))))
        for item in records
    )

    def cut(key: Callable[[PairedRecord], str], values: Sequence[str]):
        grouped: dict[str, list[PairedRecord]] = {value: [] for value in values}
        for record in records:
            grouped.setdefault(key(record), []).append(record)
        return {
            label: _cohort_effect(found, PRIMARY_HORIZON)
            for label, found in sorted(grouped.items())
        }

    windows: list[tuple[str, int, float | None]] = []
    for lower, upper in walk_forward_boundaries(
        start=sample.signal_start, end=sample.signal_end
    ):
        label = f"{lower.date().isoformat()}→{upper.date().isoformat()}"
        inside = [item for item in records if lower <= item.as_of < upper]
        # Emitted even when empty. A curve that silently omits its empty windows
        # reads as continuous coverage when the engine in fact admitted nothing.
        windows.append((label, len(inside), _mean([i.difference(PRIMARY_HORIZON) for i in inside])))

    return FamilySampleResult(
        family_id=family.family_id,
        sample=sample.name,
        matched=matched,
        unmatched=unmatched,
        symbols=len({item.symbol for item in records}),
        effect=effect,
        effect_by_horizon=by_horizon,
        bootstrap_low=low,
        bootstrap_high=high,
        null_percentile=None if effect is None else _percentile_of(effect, null),
        null_low=nearest_rank_quantile(null, 0.025) if null else None,
        null_high=nearest_rank_quantile(null, 0.975) if null else None,
        concentration=None if concentration is None else float(concentration),
        by_direction=cut(lambda r: r.direction.value, ("long", "short")),
        by_volatility=cut(
            lambda r: r.volatility or "unrecorded",
            ("contracting", "steady", "expanding"),
        ),
        by_symbol_class=cut(lambda r: r.symbol_class, ("major", "non_major")),
        walk_forward=tuple(windows),
        radius_tiers=dict(sorted(tiers.items())),
        admission_mean_mfe={
            h: _mean([r.admission_mfe[h] for r in records]) for h in horizons
        },
        admission_mean_mae={
            h: _mean([r.admission_mae[h] for r in records]) for h in horizons
        },
        control_mean_mfe={
            h: _mean([r.control_mfe[h] for r in records]) for h in horizons
        },
        control_mean_mae={
            h: _mean([r.control_mae[h] for r in records]) for h in horizons
        },
        admission_positive_rate={
            h: (
                None
                if len(records) < SAMPLE_FLOOR
                else sum(1 for r in records if r.admission_forward[h] > 0) / len(records)
            )
            for h in horizons
        },
        admission_race_rate={
            h: _race_rate(
                sum(1 for r in records if r.admission_race[h] is RaceOutcome.FAVOURABLE),
                sum(1 for r in records if r.admission_race[h] is RaceOutcome.ADVERSE),
            )
            for h in horizons
        },
        control_race_rate={
            h: _race_rate(
                sum(r.control_race_favourable[h] for r in records),
                sum(r.control_race_adverse[h] for r in records),
            )
            for h in horizons
        },
        race_ambiguous={
            h: sum(1 for r in records if r.admission_race[h] is RaceOutcome.AMBIGUOUS)
            + sum(r.control_race_ambiguous[h] for r in records)
            for h in horizons
        },
        clustered_admissions=_clustered_admissions(records),
    )


def _clustered_admissions(records: Sequence[PairedRecord]) -> int:
    """How many admissions fall within one evaluation window of another, same symbol.

    Reported rather than assumed to be zero. The 60-bar minimum separation keeps a
    CONTROL from overlapping its own admission's forward window; it says nothing
    about two ADMISSIONS overlapping each other, and CA-7 names that limitation
    rather than letting the bootstrap imply it away.
    """
    window = CA_PRE_REGISTRATION.matching.minimum_separation_bars
    by_symbol: dict[str, list[int]] = {}
    for record in records:
        by_symbol.setdefault(record.symbol, []).append(record.bar_index)
    total = 0
    for indices in by_symbol.values():
        ordered = sorted(indices)
        for position, index in enumerate(ordered):
            neighbours = ordered[:position] + ordered[position + 1 :]
            if any(abs(index - other) < window for other in neighbours):
                total += 1
    return total


# ---------------------------------------------------------------------------
# 4. The verdict.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Criterion:
    """One sealed requirement, whether it was met, and what decided it.

    ``passed`` is tri-state: `None` means the criterion could not be EVALUATED —
    a cohort below the sample floor, a sample never opened — and is never
    reported as a failure. Reporting an unrun test as a refutation claims
    evidence against a hypothesis nobody measured, which is the defect Milestone
    BZ recorded as BZ-D1 and fixed.
    """

    name: str
    passed: bool | None
    detail: str

    @property
    def is_unmeasurable(self) -> bool:
        return self.passed is None

    def payload(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class CaAssessment:
    """One family's verdict, and every criterion that produced it."""

    family_id: str
    verdict: CaVerdict
    criteria: tuple[Criterion, ...]

    @property
    def failed(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.criteria if item.passed is False)

    @property
    def unmeasurable(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.criteria if item.passed is None)

    def payload(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "verdict": self.verdict.value,
            "criteria": [item.payload() for item in self.criteria],
            "failed": list(self.failed),
            "unmeasurable": list(self.unmeasurable),
        }


def assess_ca(
    family: CaNullFamily,
    results: Mapping[str, FamilySampleResult],
    *,
    seed_effects: Mapping[int, float | None],
    manifest_digest: str,
    causal_proven: bool,
) -> CaAssessment:
    """Apply the sealed criteria to one family. **The only place a verdict is made.**

    Every threshold is read from `CA_EDGE_CRITERIA` and none is computed here. A
    family absent from the seal, or a study whose manifest carries a different
    digest, fails the first criterion and can reach no verdict above `NO_EDGE`
    whatever its numbers.
    """
    if not isinstance(family, CaNullFamily):
        raise TypeError("family must be a CaNullFamily")
    development = results.get("development")
    validation = results.get("validation")
    holdout = results.get("holdout")
    checks: list[Criterion] = []

    sealed = is_ca_pre_registered(family.family_id) and verify_ca_preregistration(
        manifest_digest
    )
    checks.append(
        Criterion(
            "pre_registered",
            sealed,
            (
                f"{family.family_id} is sealed and the manifest digest matches"
                if sealed
                else f"{family.family_id} is not sealed, or the manifest digest "
                f"{manifest_digest} is not {CA_PREREGISTRATION_DIGEST}"
            ),
        )
    )
    checks.append(
        Criterion(
            "causal",
            bool(causal_proven),
            (
                "the milestone's future-mutation suite passed with its "
                "non-vacuity controls"
                if causal_proven
                else "NOT PROVEN in this run; a run that cannot show its controls "
                "were blind to the future may not promote"
            ),
        )
    )

    counts = {
        name: (0 if result is None else result.matched)
        for name, result in (
            ("development", development),
            ("validation", validation),
            ("holdout", holdout),
        )
    }
    thin = [name for name, value in counts.items() if value < SAMPLE_FLOOR]
    checks.append(
        Criterion(
            "sample",
            # UNMEASURABLE, never False: a sample too thin to measure is a test
            # that could not be run, which is not evidence against the family.
            None if thin else True,
            (
                f"{counts} matched admissions; {', '.join(thin)} below the "
                f"{SAMPLE_FLOOR}-admission floor, so the test COULD NOT BE RUN "
                "there — this is not a refutation"
                if thin
                else f"{counts} matched admissions, all at or above {SAMPLE_FLOOR}"
            ),
        )
    )

    def effect_of(result: FamilySampleResult | None) -> float | None:
        return None if result is None else result.effect

    dev_effect = effect_of(development)
    checks.append(
        Criterion(
            "development_effect",
            None if dev_effect is None else dev_effect >= MIN_ADMISSION_EDGE_ATR,
            f"development effect {dev_effect} against a bar of "
            f"{MIN_ADMISSION_EDGE_ATR} ATR at horizon {PRIMARY_HORIZON}",
        )
    )
    val_effect = effect_of(validation)
    checks.append(
        Criterion(
            "validation_sign",
            None if val_effect is None else val_effect > 0.0,
            f"validation effect {val_effect}",
        )
    )
    hold_effect = effect_of(holdout)
    checks.append(
        Criterion(
            "holdout_sign",
            None if hold_effect is None else hold_effect > 0.0,
            f"holdout effect {hold_effect}",
        )
    )
    every = (dev_effect, val_effect, hold_effect)
    checks.append(
        Criterion(
            "economically_meaningful",
            (
                None
                if any(item is None for item in every)
                else all(item >= MIN_ADMISSION_EDGE_ATR for item in every)
            ),
            f"effects {every} against {MIN_ADMISSION_EDGE_ATR} ATR on every sample",
        )
    )

    percentile = None if development is None else development.null_percentile
    checks.append(
        Criterion(
            "null_percentile",
            None if percentile is None else percentile >= NULL_PERCENTILE_BAR,
            f"development effect at percentile {percentile} of its empirical "
            f"null, against a bar of {NULL_PERCENTILE_BAR}",
        )
    )
    boot_low = None if development is None else development.bootstrap_low
    checks.append(
        Criterion(
            "bootstrap_excludes_zero",
            None if boot_low is None else boot_low > 0.0,
            f"development 95 % symbol-clustered bootstrap lower bound {boot_low}",
        )
    )
    concentration = None if development is None else development.concentration
    bound = float(CA_PRE_REGISTRATION.payload()["max_single_symbol_share"])
    checks.append(
        Criterion(
            "concentration",
            None if concentration is None else concentration <= bound,
            f"largest single-symbol share {concentration} against a bound of {bound}",
        )
    )

    signs = {
        seed: (None if value is None else (value > 0)) for seed, value in seed_effects.items()
    }
    distinct = {value for value in signs.values() if value is not None}
    checks.append(
        Criterion(
            "seed_stable",
            None if not distinct else len(distinct) == 1,
            f"development effect signs by master seed: {signs}",
        )
    )

    if development is None:
        cohort_pass: bool | None = None
        cohort_detail = "development was not measured"
    else:
        measured = {
            label: value
            for label, (count, value) in development.by_direction.items()
            if value is not None
        }
        if not measured or dev_effect is None:
            cohort_pass = None
            cohort_detail = (
                f"no direction cohort reached the {SAMPLE_FLOOR}-admission floor "
                f"({development.by_direction}); the cut COULD NOT BE MEASURED"
            )
        else:
            cohort_pass = all((value > 0) == (dev_effect > 0) for value in measured.values())
            cohort_detail = f"direction cohorts {development.by_direction}"
    checks.append(Criterion("long_short_consistent", cohort_pass, cohort_detail))

    if development is None or dev_effect is None:
        horizon_pass: bool | None = None
        horizon_detail = "development was not measured"
    else:
        agreeing = sum(
            1
            for value in development.effect_by_horizon.values()
            if value is not None and (value > 0) == (dev_effect > 0)
        )
        horizon_pass = agreeing >= MIN_HORIZON_AGREEMENT
        horizon_detail = (
            f"{agreeing} of {len(development.effect_by_horizon)} horizons share "
            f"the primary sign, against a bar of {MIN_HORIZON_AGREEMENT}: "
            f"{development.effect_by_horizon}"
        )
    checks.append(Criterion("horizon_profile", horizon_pass, horizon_detail))

    if development is None or dev_effect is None:
        walk_pass: bool | None = None
        walk_detail = "development was not measured"
    else:
        populated = [
            value for _label, count, value in development.walk_forward
            if count > 0 and value is not None
        ]
        if not populated:
            walk_pass = None
            walk_detail = "no development walk-forward window held an admission"
        else:
            agreeing = sum(1 for value in populated if (value > 0) == (dev_effect > 0))
            walk_pass = agreeing / len(populated) >= 0.5
            walk_detail = (
                f"{agreeing} of {len(populated)} non-empty development windows "
                f"share the aggregate sign: {development.walk_forward}"
            )
    checks.append(Criterion("walk_forward", walk_pass, walk_detail))

    by_name = {item.name: item for item in checks}
    missing = {item.name for item in CA_EDGE_CRITERIA} - set(by_name)
    if missing:  # pragma: no cover - a build error
        raise SwingLabError(f"sealed criteria were not evaluated: {sorted(missing)}")

    ordered = tuple(by_name[item.name] for item in CA_EDGE_CRITERIA)
    if any(item.passed is False for item in ordered):
        mechanism = [by_name[name] for name in CA_MECHANISM_CRITERIA]
        if all(item.passed is True for item in mechanism):
            verdict = CaVerdict.MECHANISM_EVIDENCE
        elif any(item.passed is False for item in mechanism):
            verdict = CaVerdict.NO_EDGE
        else:
            verdict = CaVerdict.INCONCLUSIVE
    elif any(item.passed is None for item in ordered):
        verdict = CaVerdict.INCONCLUSIVE
    else:
        verdict = CaVerdict.ADMISSION_EDGE_CANDIDATE
    return CaAssessment(family_id=family.family_id, verdict=verdict, criteria=ordered)


# ---------------------------------------------------------------------------
# 5. The gate ladder, measured.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GateRung:
    """One rung of the admission ladder, and the forward outcomes of what stopped there.

    ``mean_forward`` is `None` for every rung below the family tally, and that is
    a **refusal rather than a gap** — see `NO_DIRECTION_TO_NORMALISE`. The
    unsigned mean absolute move is stated for those rungs so the census is not
    bare, and it is explicitly not comparable with the directional rungs.
    """

    stage: str
    sample: str
    count: int
    directional: bool
    mean_forward: float | None
    mean_absolute_move: float | None
    #: How many instants the two means were actually computed over. **DEFECT
    #: CA-D2, found by independent review**: `count` is the full rung size while
    #: the non-directional rungs are strided, so any count-weighted aggregation
    #: of `mean_absolute_move` would misweight it by up to `stride`. The two
    #: numbers are now reported separately, and they are equal for every
    #: directional rung because those are never strided.
    measured: int = 0

    def payload(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "sample": self.sample,
            "count": self.count,
            "measured": self.measured,
            "directional": self.directional,
            "mean_forward": self.mean_forward,
            "mean_absolute_move": self.mean_absolute_move,
            "refusal": None if self.directional else NO_DIRECTION_TO_NORMALISE,
        }


def _gate_ladder(
    instants: Sequence[DecisionInstant],
    caches: Mapping[str, _OutcomeCache],
    *,
    sample: str,
    horizon: int = PRIMARY_HORIZON,
    stride: int = 1,
) -> tuple[GateRung, ...]:
    """Measure every rung's forward outcome distribution at the primary horizon.

    ``stride`` samples the two enormous direction-less rungs rather than walking
    every one of eighty thousand instants; it is applied to those rungs ONLY, is
    recorded on the result, and cannot reach a directional rung or any figure a
    verdict reads.
    """
    grouped: dict[AdmissionStage, list[DecisionInstant]] = {}
    for instant in instants:
        grouped.setdefault(instant.stage, []).append(instant)
    rungs: list[GateRung] = []
    for stage in AdmissionStage:
        found = grouped.get(stage, [])
        if not found:
            rungs.append(
                GateRung(
                    stage=stage.value, sample=sample, count=0,
                    directional=stage.has_direction, mean_forward=None,
                    mean_absolute_move=None, measured=0,
                )
            )
            continue
        step = 1 if stage.has_direction else stride
        sampled = found[::step]
        forwards: list[float] = []
        absolutes: list[float] = []
        for instant in sampled:
            cache = caches[instant.symbol]
            direction = instant.direction or Direction.LONG
            outcome = _outcome_for(cache, instant, direction)
            value = float(outcome.forward[horizon])
            absolutes.append(abs(value))
            if stage.has_direction:
                forwards.append(value)
        rungs.append(
            GateRung(
                stage=stage.value,
                sample=sample,
                count=len(found),
                measured=len(sampled),
                directional=stage.has_direction,
                mean_forward=_mean(forwards) if stage.has_direction else None,
                mean_absolute_move=_mean(absolutes),
            )
        )
    return tuple(rungs)


# ---------------------------------------------------------------------------
# 6. The study.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AdmissionStudy:
    """Everything Milestone CA measured, and the seal it was measured under."""

    manifest: Mapping[str, Any]
    results: Mapping[tuple[str, str], FamilySampleResult]
    assessments: Mapping[str, CaAssessment]
    gate_ladder: tuple[GateRung, ...]
    seed_effects: Mapping[str, Mapping[int, float | None]]
    control_identity_digest: Mapping[str, str]
    limitations: tuple[str, ...] = CA_PRE_REGISTRATION.limitations

    @property
    def candidates(self) -> tuple[str, ...]:
        return tuple(
            family_id
            for family_id, item in sorted(self.assessments.items())
            if item.verdict is CaVerdict.ADMISSION_EDGE_CANDIDATE
        )

    @property
    def headline(self) -> CaVerdict:
        """The strongest verdict any family reached. **Still approves nothing.**"""
        order = (
            CaVerdict.ADMISSION_EDGE_CANDIDATE,
            CaVerdict.MECHANISM_EVIDENCE,
            CaVerdict.INCONCLUSIVE,
            CaVerdict.NO_EDGE,
        )
        reached = {item.verdict for item in self.assessments.values()}
        for verdict in order:
            if verdict in reached:
                return verdict
        return CaVerdict.NO_EDGE  # pragma: no cover - assessments is never empty

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": CA_SCHEMA_VERSION,
            "manifest": dict(self.manifest),
            "preregistration": CA_PRE_REGISTRATION.payload(),
            "results": [
                item.payload()
                for _key, item in sorted(self.results.items())
            ],
            "assessments": [
                item.payload() for _key, item in sorted(self.assessments.items())
            ],
            "gate_ladder": [item.payload() for item in self.gate_ladder],
            "seed_effects": {
                family: {str(seed): value for seed, value in sorted(effects.items())}
                for family, effects in sorted(self.seed_effects.items())
            },
            "control_identity_digest": dict(self.control_identity_digest),
            "headline": self.headline.value,
            "candidates": list(self.candidates),
            "limitations": list(self.limitations),
        }


def _control_identity_digest(
    attempts: Sequence[MatchedAdmission], *, family_id: str, sample: str
) -> str:
    """SHA-256 over every control identity this family actually drew.

    **Why a digest and not the list.** The brief requires the selected control
    identities to be persisted. Three families draw two hundred controls for each
    of four hundred and eighty admissions, so the list is roughly three hundred
    thousand bar indices — and storing it would make the artifact mostly
    bookkeeping. A digest over the same identities is *stronger* than the list
    for the purpose the list serves: it detects any difference at all, in one
    comparison, without a reader having to diff a quarter of a million rows. The
    identities themselves remain exactly reproducible from the sealed seed
    derivation, and a regression asserts that regenerating them reproduces this
    digest.
    """
    import hashlib

    running = hashlib.sha256()
    running.update(f"{family_id}|{sample}".encode("utf-8"))
    for attempt in sorted(attempts, key=lambda item: (item.admission.symbol, item.admission.bar_index)):
        running.update(
            f"\n{attempt.admission.symbol}|{attempt.admission.bar_index}|"
            f"{attempt.pool_size}|{attempt.radius_tier}|"
            f"{attempt.unmatched_reason is not None}".encode("utf-8")
        )
        for draw in attempt.draws:
            index = "self" if draw.instant is None else str(draw.instant.bar_index)
            running.update(f",{draw.replicate}:{index}:{draw.direction.value}".encode("utf-8"))
    return running.hexdigest()


def study_from_capture(
    artifact: PersistenceCaptureArtifact,
    *,
    universe_for_sample: Mapping[str, str],
    run_at: datetime,
    causal_proven: bool = False,
    samples: Sequence[SampleSpec] = SAMPLES,
    families: Sequence[CaNullFamily] = CA_NULL_FAMILIES,
    horizons: Sequence[int] = FORWARD_HORIZONS,
    gate_ladder_stride: int = 25,
    progress: Callable[[str], None] | None = None,
) -> AdmissionStudy:
    """Run the sealed CA experiment over a persisted Milestone BZ capture.

    **No network, at any point, for any reason.** Every input is decoded from the
    capture, and a regression runs this function with the replay transport
    monkeypatched to raise, so "offline" is proven by making a fetch fatal rather
    than asserted.

    The walk is **per symbol**: a symbol's instants, ATRs, outcome cache, pools
    and draws are built, measured and discarded before the next symbol starts.
    That is not an optimisation detail — matching is same-symbol by seal, so a
    symbol is the natural unit, and holding every symbol's outcome cache at once
    would cost several hundred megabytes for nothing.

    Raises:
        SwingLabError: the capture's digest does not verify, a sample names a
            universe the capture does not hold, or the capture was taken under a
            different pre-registration than the one this build seals.
    """
    if not isinstance(artifact, PersistenceCaptureArtifact):
        raise TypeError("artifact must be a PersistenceCaptureArtifact")
    if not verify_capture_digest(artifact):
        raise SwingLabError(
            "the capture's content digest does not verify; a study measured over "
            "an edited capture would report numbers nobody captured"
        )
    say = progress if progress is not None else (lambda _message: None)

    matching = CA_PRE_REGISTRATION.matching
    randomisation = CA_PRE_REGISTRATION.randomisation
    by_name = {item.name: item for item in samples}

    results: dict[tuple[str, str], FamilySampleResult] = {}
    seed_effects: dict[str, dict[int, float | None]] = {
        family.family_id: {} for family in families
    }
    identity_digests: dict[str, str] = {}
    rungs: list[GateRung] = []
    census: dict[str, dict[str, int]] = {}
    #: One ATR walk per universe, shared by every sample cut from it. Development
    #: and validation are the same fifteen symbols over disjoint periods, so
    #: computing it per sample would do the same work twice for a value that
    #: cannot differ between them.
    atr_by_universe: dict[str, dict[str, tuple[float | None, ...]]] = {}

    for sample_name, universe in sorted(universe_for_sample.items()):
        sample = by_name.get(sample_name)
        if sample is None:
            raise SwingLabError(f"no sample named {sample_name!r} is sealed")
        say(f"sample {sample_name} over universe {universe}")
        captured = artifact.universe(universe)
        if universe not in atr_by_universe:
            limit = captured.capture.metadata["candle_limit"]
            say(f"  computing production ATR over {universe}")
            atr_by_universe[universe] = {
                symbol: atr_series(bars, limit=limit)
                for symbol, bars in sorted(captured.capture.bars_by_symbol.items())
            }
        atrs_by_symbol = atr_by_universe[universe]
        instants, bars_by_symbol, _volatility = build_sample_instants(
            artifact,
            universe=universe,
            sample=sample,
            horizons=horizons,
            atrs_by_symbol=atrs_by_symbol,
        )
        census[sample_name] = {stage.value: 0 for stage in AdmissionStage}
        for instant in instants:
            census[sample_name][instant.stage.value] += 1

        indices = {
            family.family_id: build_pool_index(
                instants,
                stages=frozenset(
                    stage
                    for stage in AdmissionStage
                    if stage is not AdmissionStage.ADMITTED
                )
                if family.control_source is CaControlSource.MATCHED_ANY_STAGE
                else frozenset({AdmissionStage.UNCONFIRMED}),
            )
            for family in families
        }
        admissions = [
            item for item in instants if item.stage is AdmissionStage.ADMITTED
        ]
        say(f"  {len(instants)} instants, {len(admissions)} admissions")

        by_symbol: dict[str, list[DecisionInstant]] = {}
        for instant in admissions:
            by_symbol.setdefault(instant.symbol, []).append(instant)

        collected: dict[str, list[PairedRecord]] = {f.family_id: [] for f in families}
        attempted: dict[str, list[MatchedAdmission]] = {f.family_id: [] for f in families}
        alternates: dict[str, dict[int, list[PairedRecord]]] = {
            f.family_id: {seed: [] for seed in randomisation.master_seeds}
            for f in families
        }
        ladder_instants: dict[str, list[DecisionInstant]] = {}
        for instant in instants:
            ladder_instants.setdefault(instant.symbol, []).append(instant)

        for symbol in sorted(bars_by_symbol):
            if symbol not in sample.symbols:
                continue
            bars = bars_by_symbol[symbol]
            cache = _OutcomeCache(bars, horizons, atrs_by_symbol[symbol])
            caches = {symbol: cache}
            here = by_symbol.get(symbol, [])
            for family in families:
                records, attempts = measure_family(
                    here,
                    family=family,
                    index=indices[family.family_id],
                    caches=caches,
                    horizons=horizons,
                    master_seed=randomisation.primary_seed,
                    matching=matching,
                    randomisation=randomisation,
                )
                collected[family.family_id].extend(records)
                attempted[family.family_id].extend(attempts)
                alternates[family.family_id][randomisation.primary_seed].extend(records)
                # The other master seeds exist ONLY to answer whether the sign is
                # a property of the data or of one draw, and only on development.
                if sample_name == "development":
                    for seed in randomisation.master_seeds:
                        if seed == randomisation.primary_seed:
                            continue
                        extra, _ = measure_family(
                            here,
                            family=family,
                            index=indices[family.family_id],
                            caches=caches,
                            horizons=horizons,
                            master_seed=seed,
                            matching=matching,
                            randomisation=randomisation,
                        )
                        alternates[family.family_id][seed].extend(extra)
            rungs.extend(
                _gate_ladder(
                    ladder_instants.get(symbol, ()),
                    caches,
                    sample=f"{sample_name}:{symbol}",
                    stride=gate_ladder_stride,
                )
            )

        for family in families:
            results[(family.family_id, sample_name)] = _aggregate(
                collected[family.family_id],
                attempted[family.family_id],
                family=family,
                sample=sample,
                horizons=horizons,
                master_seed=randomisation.primary_seed,
                randomisation=randomisation,
            )
            identity_digests[f"{family.family_id}|{sample_name}"] = (
                _control_identity_digest(
                    attempted[family.family_id],
                    family_id=family.family_id,
                    sample=sample_name,
                )
            )
            if sample_name == "development":
                for seed, records in alternates[family.family_id].items():
                    seed_effects[family.family_id][seed] = _mean(
                        [item.difference(PRIMARY_HORIZON) for item in records]
                    )
            say(f"  {family.family_id}: {results[(family.family_id, sample_name)].matched} matched")

    manifest = {
        "preregistration_id": CA_PREREGISTRATION_ID,
        "preregistration_digest": CA_PREREGISTRATION_DIGEST,
        "capture_content_digest": artifact.content_digest,
        "capture_preregistration_digest": artifact.preregistration_digest,
        "capture_captured_at": artifact.manifest.get("captured_at"),
        "run_at": run_at.isoformat(),
        "universe_for_sample": dict(sorted(universe_for_sample.items())),
        "horizons": list(horizons),
        "primary_horizon": PRIMARY_HORIZON,
        "causal_proven": bool(causal_proven),
        "gate_ladder_stride": gate_ladder_stride,
        "stage_census": census,
        "provider": dict(artifact.manifest.get("provider", {})),
    }
    assessments = {
        family.family_id: assess_ca(
            family,
            {
                sample_name: results[(family.family_id, sample_name)]
                for sample_name in universe_for_sample
                if (family.family_id, sample_name) in results
            },
            seed_effects=seed_effects[family.family_id],
            manifest_digest=CA_PREREGISTRATION_DIGEST,
            causal_proven=causal_proven,
        )
        for family in families
    }
    return AdmissionStudy(
        manifest=manifest,
        results=results,
        assessments=assessments,
        gate_ladder=tuple(rungs),
        seed_effects=seed_effects,
        control_identity_digest=identity_digests,
    )
