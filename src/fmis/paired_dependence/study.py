"""Milestone CD's measurement, assembled. **Nothing here decides anything.**

Every threshold, axis, block length, reduction, weighting, floor, seed and
verdict boundary this module uses is read from
`fmis.paired_dependence.preregistration`. It owns no number of its own, and a
study whose manifest does not carry that pre-registration's digest cannot be read
as CD.

**Two entry points, one measurement.**

    study_from_capture(...)   a Milestone BZ capture → observations → everything
    study_from_rows(...)      a persisted CD row set → everything

The second is what makes offline reproduction real rather than claimed: given the
artifact alone, with every market-data and network function monkeypatched to
raise, it must reproduce every measured figure the first produced. A regression
asserts exactly that, by comparing the two payloads field for field.

**Every statistic carries its sample and its family, and there is no field that
could hold a pooled one.** Milestone BY published a wrong conclusion by pooling
three samples whose universes differed; Milestone CA built the structural refusal
and CD inherits it. Five families measuring the same admitted instants are five
views of one sample, never five samples.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from fmis.paired_dependence.controls import (
    ControlReading,
    cc_residual_correlation,
    run_negative_controls,
)
from fmis.paired_dependence.estimator import (
    CellReduction,
    contemporaneity_fraction,
    leave_one_out,
    overlap_corrected_correlation,
    pairwise_asset_correlations,
)
from fmis.paired_dependence.integration import (
    RequirementAssessment,
    assess_requirement,
    cc_reevaluation,
)
from fmis.paired_dependence.models import (
    GroupingAxis,
    PairedDependenceError,
    Weighting,
)
from fmis.paired_dependence.observations import (
    ObservationRow,
    dependence_coverage_of,
    dependence_concentration_of,
    dependence_overlap_of,
)
from fmis.paired_dependence.preregistration import (
    BLOCK_BARS_GRID,
    BOOTSTRAP_CONFIDENCE,
    BOOTSTRAP_DRAWS,
    CALIBRATION_REPLICATES,
    CD_MASTER_SEED,
    CD_MEASURED_SAMPLES,
    CD_PRE_REGISTRATION,
    CD_PREREGISTRATION_DIGEST,
    CD_PREREGISTRATION_ID,
    CD_PRIMARY_FAMILY,
    CD_PRIMARY_SAMPLE,
    MIN_ECONOMIC_ASSETS,
    MIN_GROUPS,
    MIN_INFORMATIVE_BLOCKS,
    MIN_MEMBERS,
    MIN_SHARED_BLOCKS_PER_PAIR,
    PRIMARY_BLOCK_BARS,
)
from fmis.paired_dependence.uncertainty import (
    DependenceInterval,
    bootstrap_interval,
    estimate_on_axis,
)
from fmis.paired_dependence.verdict import (
    CalibrationOutcome,
    CdAssessment,
    assess_cd,
    calibrate,
    check_floors,
)

__all__ = [
    "CD_SCHEMA_VERSION",
    "PanelResult",
    "SensitivityCell",
    "PairedDependenceStudy",
    "study_from_capture",
    "study_from_rows",
]

#: Bumped whenever a persisted CD artifact changes shape.
CD_SCHEMA_VERSION: Final[int] = 1

_EVALUATION_WINDOW_BARS: Final[int] = 60


@dataclass(frozen=True, slots=True)
class SensitivityCell:
    """One point of the sealed grid. **Reported whether or not it is convenient.**"""

    block_bars: int
    reduction: str
    weighting: str
    between_asset: float | None
    within_asset: float | None
    informative_blocks: int
    groups: int
    members: int
    reason: str | None

    def payload(self) -> dict[str, Any]:
        return {
            "block_bars": self.block_bars,
            "reduction": self.reduction,
            "weighting": self.weighting,
            "between_asset": self.between_asset,
            "within_asset": self.within_asset,
            "informative_blocks": self.informative_blocks,
            "groups": self.groups,
            "members": self.members,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PanelResult:
    """One (family, sample) panel, measured on both axes. **Never pooled.**"""

    family_id: str
    sample: str
    coverage: dict[str, Any]
    concentration: dict[str, Any]
    overlap: dict[str, Any]
    between_asset: DependenceInterval
    within_asset: DependenceInterval
    between_asset_cross_axis: DependenceInterval
    within_asset_cross_axis: DependenceInterval
    pairwise: dict[str, Any]
    cc_residual: float | None
    sensitivity: tuple[SensitivityCell, ...]
    controls: tuple[ControlReading, ...]
    #: Added after independent review. See CD-8 and CD-16.
    contemporaneity: dict[str, Any]
    stability: dict[str, Any]

    def payload(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "sample": self.sample,
            "coverage": self.coverage,
            "concentration": self.concentration,
            "overlap": self.overlap,
            "between_asset": self.between_asset.payload(),
            "within_asset": self.within_asset.payload(),
            "between_asset_cross_axis": self.between_asset_cross_axis.payload(),
            "within_asset_cross_axis": self.within_asset_cross_axis.payload(),
            "pairwise": self.pairwise,
            "cc_residual_correlation": self.cc_residual,
            "sensitivity": [item.payload() for item in self.sensitivity],
            "controls": [item.payload() for item in self.controls],
            "contemporaneity": self.contemporaneity,
            "stability": self.stability,
        }


@dataclass(frozen=True, slots=True)
class PairedDependenceStudy:
    """Everything Milestone CD measured, with the seal it was measured under."""

    manifest: dict[str, Any]
    rows: tuple[ObservationRow, ...]
    panels: tuple[PanelResult, ...]
    calibration: CalibrationOutcome
    requirement: RequirementAssessment
    cc_comparison: dict[str, Any]
    assessment: CdAssessment
    reconstruction: dict[str, Any]

    def panel(self, family_id: str, sample: str) -> PanelResult:
        """One panel by identity.

        Raises:
            PairedDependenceError: no panel carries that pair.
        """
        for item in self.panels:
            if item.family_id == family_id and item.sample == sample:
                return item
        raise PairedDependenceError(
            f"this study holds no panel for family {family_id!r} on sample "
            f"{sample!r}"
        )

    @property
    def headline(self) -> PanelResult:
        """The pre-registered primary family on the pre-registered primary sample."""
        return self.panel(CD_PRIMARY_FAMILY, CD_PRIMARY_SAMPLE)

    def payload(self) -> dict[str, Any]:
        return {
            "manifest": dict(self.manifest),
            "observations": [row.payload() for row in self.rows],
            "panels": [item.payload() for item in self.panels],
            "calibration": self.calibration.payload(),
            "requirement": self.requirement.payload(),
            "cc_comparison": dict(self.cc_comparison),
            "assessment": self.assessment.payload(),
            "reconstruction": dict(self.reconstruction),
            "preregistration": CD_PRE_REGISTRATION.payload(),
        }


def _panel_rows(
    rows: Sequence[ObservationRow], *, family_id: str, sample: str
) -> tuple[ObservationRow, ...]:
    return tuple(
        row for row in rows if row.family_id == family_id and row.sample == sample
    )


def _sensitivity(
    rows: Sequence[ObservationRow],
) -> tuple[SensitivityCell, ...]:
    """The whole sealed grid, every cell, in declaration order.

    Point estimates only. A bootstrap on every one of the sixteen cells would
    invite reading the narrowest interval as the answer, which is the search this
    milestone pre-registered its way out of; the interval belongs to the primary
    cell and to the block-length row that varies the one dimension a reader most
    needs to see.
    """
    cells: list[SensitivityCell] = []
    for block_bars in BLOCK_BARS_GRID:
        for reduction in CellReduction:
            for weighting in Weighting:
                between = estimate_on_axis(
                    rows,
                    axis=GroupingAxis.TIME_BLOCK,
                    block_bars=block_bars,
                    reduction=reduction,
                    weighting=weighting,
                )
                within = estimate_on_axis(
                    rows, axis=GroupingAxis.ECONOMIC_ASSET, block_bars=block_bars
                )
                coverage = dependence_coverage_of(rows, block_bars=block_bars)
                cells.append(
                    SensitivityCell(
                        block_bars=block_bars,
                        reduction=reduction.value,
                        weighting=weighting.value,
                        between_asset=between.correlation,
                        within_asset=within.correlation,
                        informative_blocks=int(
                            coverage["blocks_with_two_or_more_assets"]
                        ),
                        groups=between.groups,
                        members=between.members,
                        reason=between.reason,
                    )
                )
    return tuple(cells)


def _contemporaneity(rows: Sequence[ObservationRow], correlation: float | None):
    """``q``, ``q * r_b`` and what each implies. **Post-review; not sealed.**

    The sealed secondary estimator feeds ``r_b`` straight into
    `effective_clusters`, and independent review established that the formula
    wants a cluster-level correlation rather than an observation-level one
    (CD-8). Both are reported: the sealed figure so the artifact still says what
    the seal said, and the corrected one beside it so a reader is not misled by
    it.
    """
    from fmis.universe.dependence import effective_clusters

    fraction = contemporaneity_fraction(rows, block_bars=PRIMARY_BLOCK_BARS)
    corrected = overlap_corrected_correlation(
        rows, correlation=correlation, block_bars=PRIMARY_BLOCK_BARS
    )

    def clusters(count: int, value: float | None) -> float | None:
        if value is None:
            return None
        return effective_clusters(count, min(1.0, max(0.0, value)))

    return {
        "note": (
            "POST-REVIEW, NOT SEALED. r_b is an observation-level contemporaneous "
            "correlation; K/(1+(K-1)r) expects a cluster-level one. The "
            "design-relevant quantity is q * r_b. See CD-8."
        ),
        "contemporaneity_fraction": fraction,
        "sealed_correlation": correlation,
        "overlap_corrected_correlation": corrected,
        "effective_clusters_at_38_sealed": clusters(38, correlation),
        "effective_clusters_at_38_corrected": clusters(38, corrected),
        "effective_clusters_at_106_sealed": clusters(106, correlation),
        "effective_clusters_at_106_corrected": clusters(106, corrected),
    }


def _measure_panel(
    rows: Sequence[ObservationRow], *, family_id: str, sample: str
) -> PanelResult:
    identity = [CD_PREREGISTRATION_ID, family_id, sample]
    between = bootstrap_interval(
        rows,
        axis=GroupingAxis.TIME_BLOCK,
        resample_axis=GroupingAxis.TIME_BLOCK,
        block_bars=PRIMARY_BLOCK_BARS,
        draws=BOOTSTRAP_DRAWS,
        confidence=BOOTSTRAP_CONFIDENCE,
        master_seed=CD_MASTER_SEED,
        identity=identity,
    )
    within = bootstrap_interval(
        rows,
        axis=GroupingAxis.ECONOMIC_ASSET,
        resample_axis=GroupingAxis.ECONOMIC_ASSET,
        block_bars=PRIMARY_BLOCK_BARS,
        draws=BOOTSTRAP_DRAWS,
        confidence=BOOTSTRAP_CONFIDENCE,
        master_seed=CD_MASTER_SEED,
        identity=identity,
    )
    between_cross = bootstrap_interval(
        rows,
        axis=GroupingAxis.TIME_BLOCK,
        resample_axis=GroupingAxis.ECONOMIC_ASSET,
        block_bars=PRIMARY_BLOCK_BARS,
        draws=BOOTSTRAP_DRAWS,
        confidence=BOOTSTRAP_CONFIDENCE,
        master_seed=CD_MASTER_SEED,
        identity=identity,
    )
    within_cross = bootstrap_interval(
        rows,
        axis=GroupingAxis.ECONOMIC_ASSET,
        resample_axis=GroupingAxis.TIME_BLOCK,
        block_bars=PRIMARY_BLOCK_BARS,
        draws=BOOTSTRAP_DRAWS,
        confidence=BOOTSTRAP_CONFIDENCE,
        master_seed=CD_MASTER_SEED,
        identity=identity,
    )
    correlations, pair_coverage = pairwise_asset_correlations(
        rows,
        block_bars=PRIMARY_BLOCK_BARS,
        minimum_shared_blocks=MIN_SHARED_BLOCKS_PER_PAIR,
    )
    values = sorted(correlations.values())
    from fmis.research_design.numeric import nearest_rank_quantile

    return PanelResult(
        family_id=family_id,
        sample=sample,
        coverage=dependence_coverage_of(rows, block_bars=PRIMARY_BLOCK_BARS),
        concentration=dependence_concentration_of(rows),
        overlap=dependence_overlap_of(rows, evaluation_window_bars=_EVALUATION_WINDOW_BARS),
        between_asset=between,
        within_asset=within,
        between_asset_cross_axis=between_cross,
        within_asset_cross_axis=within_cross,
        pairwise={
            **pair_coverage,
            "minimum_shared_blocks": MIN_SHARED_BLOCKS_PER_PAIR,
            "mean": (sum(values) / len(values)) if values else None,
            "median": nearest_rank_quantile(values, 0.5),
            "minimum": values[0] if values else None,
            "maximum": values[-1] if values else None,
        },
        cc_residual=cc_residual_correlation(rows, block_bars=PRIMARY_BLOCK_BARS),
        sensitivity=_sensitivity(rows),
        controls=run_negative_controls(
            rows, block_bars=PRIMARY_BLOCK_BARS, seed=CD_MASTER_SEED
        ),
        contemporaneity=_contemporaneity(rows, between.point),
        stability={
            "by_asset": leave_one_out(
                rows,
                axis=GroupingAxis.TIME_BLOCK,
                block_bars=PRIMARY_BLOCK_BARS,
                by="asset",
            ),
            "by_block": leave_one_out(
                rows,
                axis=GroupingAxis.TIME_BLOCK,
                block_bars=PRIMARY_BLOCK_BARS,
                by="block",
            ),
        },
    )


def _assemble(
    rows: Sequence[ObservationRow],
    *,
    manifest: Mapping[str, Any],
    reconstruction: Mapping[str, Any],
    progress: Callable[[str], None] | None = None,
) -> PairedDependenceStudy:
    say = progress if progress is not None else (lambda _message: None)
    families = sorted({row.family_id for row in rows})
    panels: list[PanelResult] = []
    for family_id in families:
        for sample in CD_MEASURED_SAMPLES:
            panel_rows = _panel_rows(rows, family_id=family_id, sample=sample)
            if not panel_rows:
                continue
            say(f"measuring {family_id} on {sample}: {len(panel_rows)} rows")
            panels.append(
                _measure_panel(panel_rows, family_id=family_id, sample=sample)
            )
    if not panels:
        raise PairedDependenceError(
            "no panel held a single paired observation; there is nothing to "
            "measure the dependence of"
        )

    say("calibrating the estimator against synthetic panels")
    calibration = calibrate(
        replicates=CALIBRATION_REPLICATES,
        block_bars=PRIMARY_BLOCK_BARS,
        master_seed=CD_MASTER_SEED,
    )

    headline = next(
        (
            item
            for item in panels
            if item.family_id == CD_PRIMARY_FAMILY and item.sample == CD_PRIMARY_SAMPLE
        ),
        None,
    )
    if headline is None:
        raise PairedDependenceError(
            f"no panel holds the pre-registered primary family "
            f"{CD_PRIMARY_FAMILY!r} on the primary sample {CD_PRIMARY_SAMPLE!r}; "
            "the headline is fixed by the seal and is not substituted with "
            "whichever panel happens to exist"
        )
    requirement = assess_requirement(
        point=headline.between_asset.point,
        lower=headline.between_asset.lower,
        upper=headline.between_asset.upper,
        within_asset_correlation=headline.within_asset.point,
        sample=CD_PRIMARY_SAMPLE,
    )
    floors = check_floors(
        headline.coverage,
        headline.between_asset,
        headline.within_asset,
        min_groups=MIN_GROUPS,
        min_members=MIN_MEMBERS,
        min_economic_assets=MIN_ECONOMIC_ASSETS,
        min_informative_blocks=MIN_INFORMATIVE_BLOCKS,
    )
    assessment = assess_cd(
        calibration=calibration,
        floors=floors,
        between=headline.between_asset,
        within=headline.within_asset,
        requirement=requirement,
    )
    return PairedDependenceStudy(
        manifest=dict(manifest),
        rows=tuple(rows),
        panels=tuple(panels),
        calibration=calibration,
        requirement=requirement,
        cc_comparison=cc_reevaluation(requirement),
        assessment=assessment,
        reconstruction=dict(reconstruction),
    )


def study_from_capture(
    artifact: Any,
    *,
    run_at: datetime,
    universe_for_sample: Mapping[str, str] | None = None,
    samples: Sequence[Any] | None = None,
    progress: Callable[[str], None] | None = None,
) -> PairedDependenceStudy:
    """Replay Milestone CA over a capture and measure the dependence of its output.

    **No network, at any point, for any reason.** Every input is decoded from the
    capture, and a regression runs this with every transport monkeypatched to
    raise.
    """
    from fmis.paired_dependence.capture import CA_UNIVERSE_FOR_SAMPLE
    from fmis.paired_dependence.observations import observations_from_capture
    from fmis.swing_lab.admission_preregistration import PRIMARY_HORIZON

    mapping = dict(
        CA_UNIVERSE_FOR_SAMPLE if universe_for_sample is None else universe_for_sample
    )
    say = progress if progress is not None else (lambda _message: None)
    say("replaying Milestone CA over the capture")
    rows, ca_study = observations_from_capture(
        artifact,
        horizon=PRIMARY_HORIZON,
        universe_for_sample=mapping,
        run_at=run_at,
        samples=samples,
        progress=progress,
    )
    reconstruction = _reconstruction_of(ca_study)
    manifest = {
        "preregistration_id": CD_PREREGISTRATION_ID,
        "preregistration_digest": CD_PREREGISTRATION_DIGEST,
        "capture_content_digest": artifact.content_digest,
        "capture_preregistration_digest": artifact.preregistration_digest,
        "capture_captured_at": artifact.manifest.get("captured_at"),
        "ca_preregistration_digest": ca_study.payload()["manifest"][
            "preregistration_digest"
        ],
        "run_at": run_at.isoformat(),
        "universe_for_sample": dict(sorted(mapping.items())),
        "primary_horizon": PRIMARY_HORIZON,
        "primary_family": CD_PRIMARY_FAMILY,
        "primary_sample": CD_PRIMARY_SAMPLE,
        "primary_block_bars": PRIMARY_BLOCK_BARS,
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_confidence": BOOTSTRAP_CONFIDENCE,
        "master_seed": CD_MASTER_SEED,
        "source": "capture",
    }
    return _assemble(
        rows, manifest=manifest, reconstruction=reconstruction, progress=progress
    )


def study_from_rows(
    rows: Sequence[ObservationRow],
    *,
    manifest: Mapping[str, Any],
    reconstruction: Mapping[str, Any],
    progress: Callable[[str], None] | None = None,
) -> PairedDependenceStudy:
    """Re-measure from a persisted CD row set. **The offline reproduction path.**

    Takes the manifest and the reconstruction census from the artifact rather
    than recomputing them: a reader that re-derived a missing field would have
    silently turned an audit back into a run.
    """
    if not rows:
        raise PairedDependenceError(
            "a study needs at least one observation; an empty row set is a "
            "corrupt artifact rather than an empty result"
        )
    # **Canonical order, always.** `group_by_asset` preserves input order, so a
    # reordered JSON array moves `rho_w` at the last bit and with it the
    # asset-axis bootstrap bounds. Independent review measured three distinct
    # values across six shuffles. Sorting here makes the reproduction a function
    # of the rows rather than of their order in the file.
    return _assemble(
        tuple(sorted(rows, key=lambda item: item.observation_id)),
        manifest={**dict(manifest), "source": "artifact"},
        reconstruction=dict(reconstruction),
        progress=progress,
    )


def _reconstruction_of(ca_study: Any) -> dict[str, Any]:
    """CD's reconstructed CA counts beside Milestone CA's published ones.

    The capture CD took is not the capture CA measured — it cannot be, because
    CA's was never persisted — so this is the honest comparison rather than an
    assumed identity. A divergence is a statement about the provider.
    """
    from fmis.swing_lab.admission_power import CA_PUBLISHED

    payload = ca_study.payload()
    published = {item.sample: item for item in CA_PUBLISHED}
    rows: list[dict[str, Any]] = []
    for result in payload.get("results", []):
        if result.get("family_id") != CD_PRIMARY_FAMILY:
            continue
        sample = result.get("sample")
        figure = published.get(sample)
        matched = result.get("matched")
        rows.append(
            {
                "sample": sample,
                "family_id": CD_PRIMARY_FAMILY,
                "cd_matched": matched,
                "ca_published_matched": None if figure is None else figure.matched,
                "cd_symbols": result.get("symbols"),
                "ca_published_symbols": None if figure is None else figure.symbols,
                "cd_effect": result.get("effect"),
                "ca_published_interval": (
                    None
                    if figure is None
                    else [figure.bootstrap_low, figure.bootstrap_high]
                ),
                "matched_delta": (
                    None
                    if figure is None or matched is None
                    else matched - figure.matched
                ),
            }
        )
    return {
        "note": (
            "Milestone CA's capture was never persisted, so CD re-captured. These "
            "counts describe CD's capture beside CA's published figures; a "
            "difference is a provider finding, not a defect."
        ),
        "stage_census": payload.get("manifest", {}).get("stage_census", {}),
        "by_sample": rows,
    }
