"""Drawing a control for one admission. **Seeded, matched, and blind to outcomes.**

This module is where Milestone CA's null is actually constructed, and it is the
half of the experiment most able to produce a false result. A control drawn from
a different volatility environment, a different market period or a different
symbol would let the admission engine "beat" a null it was never compared
against; a control drawn with an unseeded generator would make the whole study
irreproducible; a control drawn using anything the admission's own future
determined would be lookahead wearing a matching rule's clothes.

**Three properties, each enforced structurally rather than promised.**

1. **It cannot read an outcome.** Every function here is handed
   `fmis.swing_lab.admission.DecisionInstant`s, which hold a symbol, a bar index,
   a stage, a direction, a close and an ATR — and *no bar and no forward result*.
   A matching rule therefore cannot consult a future price, not by discipline but
   by what exists. An architecture guard asserts this module imports neither
   `PriceBar` nor `ForwardOutcome`.

2. **It is reproducible without a shared clock or a shared process.** Every seed
   is SHA-256 over the draw's own identity — master seed, family, sample, symbol,
   bar index, replicate — so a draw is a pure function of what it is drawing for.
   Python's built-in `hash` is never used: it is salted per process, and a study
   seeded with it would produce different controls on two runs of the same
   machine while claiming to be deterministic.

3. **It fails closed.** An admission whose pool cannot reach the sealed minimum
   at the widest calendar tier is `UNMATCHED` — reported by name and excluded
   from that family — never matched against a pool too small to be a null.

**The separation constraint is the one that matters most.** Controls are drawn at
least `minimum_separation_bars` away from their admission, and that number is
sealed as exactly the evaluation window. A nearer control would share forward
bars with the admission it is compared against, and the paired difference would
be partly a number minus itself — the pseudoreplication the brief warns about,
arriving through the matching rule rather than through the sample size.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import log
from random import Random
from typing import Final

from fmis.research_design.models import ResearchDesignError
from fmis.research_design.numeric import derive_seed as general_seed
from fmis.swing_lab.admission import AdmissionStage, DecisionInstant
from fmis.swing_lab.admission_preregistration import (
    CaControlSource,
    CaDirectionRule,
    CaNullFamily,
    MatchingSpec,
    RandomisationSpec,
)
from fmis.swing_lab.models import SwingLabError
from fmis.swing_setup.models import Direction

__all__ = [
    "ControlDraw",
    "MatchedAdmission",
    "PoolIndex",
    "derive_seed",
    "build_pool_index",
    "eligible_pool",
    "match_admission",
    "OPPOSITE_DIRECTION",
]

#: Reversing a side, as a mapping rather than a branch. A branch would be written
#: twice — once for the control and once for a diagnostic — and the second one is
#: where a short's arithmetic silently becomes a long's.
OPPOSITE_DIRECTION: Final[Mapping[Direction, Direction]] = {
    Direction.LONG: Direction.SHORT,
    Direction.SHORT: Direction.LONG,
}

#: The stages a `MATCHED_ANY_STAGE` pool draws from: every rung except the one
#: the engine admitted. `CONFIRMED_REPEAT` is deliberately INCLUDED — it is a
#: moment the engine did not admit, and excluding it would quietly make the null
#: easier by removing its most signal-like members.
_ANY_STAGE_POOL: Final[frozenset[AdmissionStage]] = frozenset(
    stage for stage in AdmissionStage if stage is not AdmissionStage.ADMITTED
)

_UNCONFIRMED_POOL: Final[frozenset[AdmissionStage]] = frozenset(
    {AdmissionStage.UNCONFIRMED}
)

_POOL_STAGES: Final[Mapping[CaControlSource, frozenset[AdmissionStage]]] = {
    CaControlSource.MATCHED_ANY_STAGE: _ANY_STAGE_POOL,
    CaControlSource.MATCHED_UNCONFIRMED: _UNCONFIRMED_POOL,
}


def derive_seed(
    *,
    master: int,
    family_id: str,
    sample: str,
    symbol: str,
    bar_index: int,
    replicate: int,
) -> int:
    """A draw's seed, derived from its identity. **Never from iteration order.**

    SHA-256 over the UTF-8 of the joined identity, truncated to 64 bits. The
    consequences are the ones a reproducibility claim needs:

    * adding a symbol, reordering the families or changing `PYTHONHASHSEED` moves
      no existing draw, because none of those is in the identity;
    * two studies run months apart on different machines draw the same controls;
    * and a draw cannot be nudged by re-running until it looks better, because
      there is no state to re-run.

    **The derivation itself now lives in `fmis.research_design.numeric`**, which
    Milestone CB extracted so a research package that must not depend on this
    laboratory can seed its own draws from the same rule. This function is that
    one with Milestone CA's identity fields, and the extraction is
    behaviour-preserving: the joined identity string is byte-for-byte what it was,
    so every control CA drew is the control it drew before.
    """
    if isinstance(master, bool) or not isinstance(master, int):
        raise SwingLabError("master must be an int")
    if isinstance(replicate, bool) or not isinstance(replicate, int) or replicate < 0:
        raise SwingLabError("replicate must be a non-negative int")
    try:
        return general_seed(
            master=master,
            parts=(family_id, sample, symbol, bar_index, replicate),
        )
    except ResearchDesignError as error:
        raise SwingLabError(str(error)) from None


@dataclass(frozen=True, slots=True)
class PoolIndex:
    """Every candidate control instant of one universe, addressed by symbol.

    Built once and shared by every admission, because a per-admission scan of a
    hundred thousand instants would dominate the run. The instants themselves are
    the same frozen objects the study measures, so a pool cannot hold a different
    view of a bar from the one being compared against it.
    """

    by_symbol: Mapping[str, tuple[DecisionInstant, ...]]
    admitted_indices: Mapping[str, frozenset[int]]

    def instants(self, symbol: str) -> tuple[DecisionInstant, ...]:
        return self.by_symbol.get(symbol, ())


def build_pool_index(
    instants: Sequence[DecisionInstant], *, stages: frozenset[AdmissionStage]
) -> PoolIndex:
    """Index one sample's instants by symbol, keeping only ``stages``.

    ``admitted_indices`` is recorded separately from the filtered pool so the
    exclusion of admitted bars is checkable rather than implicit in whichever
    stages happened to be requested.
    """
    by_symbol: dict[str, list[DecisionInstant]] = {}
    admitted: dict[str, set[int]] = {}
    for instant in instants:
        if instant.stage is AdmissionStage.ADMITTED:
            admitted.setdefault(instant.symbol, set()).add(instant.bar_index)
        if instant.stage in stages:
            by_symbol.setdefault(instant.symbol, []).append(instant)
    return PoolIndex(
        by_symbol={
            symbol: tuple(sorted(found, key=lambda item: item.bar_index))
            for symbol, found in sorted(by_symbol.items())
        },
        admitted_indices={
            symbol: frozenset(found) for symbol, found in sorted(admitted.items())
        },
    )


def eligible_pool(
    admission: DecisionInstant,
    index: PoolIndex,
    *,
    matching: MatchingSpec,
    radius: int,
) -> tuple[DecisionInstant, ...]:
    """Every instant this admission may be matched against, at one calendar tier.

    Four constraints, and each removes a confound the pre-registration names:
    the same symbol (by construction — the index is keyed on it), a bounded
    calendar neighbourhood, a minimum separation of a full evaluation window, and
    a comparable volatility band. Admitted instants are removed regardless of the
    stage filter, so a null can never contain an FMITS admission.

    **Nothing here consults a bar.** The volatility comparison is between two
    ATRs already frozen onto the instants, and the calendar comparison is between
    two bar indices. A future price cannot reach this function.
    """
    if not isinstance(admission, DecisionInstant):
        raise TypeError("admission must be a DecisionInstant")
    if isinstance(radius, bool) or not isinstance(radius, int) or radius <= 0:
        raise SwingLabError("radius must be a positive int")
    reference = admission.atr
    if reference <= 0:  # pragma: no cover - DecisionInstant refuses one
        raise SwingLabError("the admission carries no usable volatility scale")
    tolerance = matching.atr_log_tolerance
    separation = matching.minimum_separation_bars
    excluded = (
        index.admitted_indices.get(admission.symbol, frozenset())
        if matching.excludes_admitted
        else frozenset()
    )
    found: list[DecisionInstant] = []
    for candidate in index.instants(admission.symbol):
        distance = abs(candidate.bar_index - admission.bar_index)
        if distance < separation or distance > radius:
            continue
        if candidate.bar_index in excluded:
            continue
        if abs(log(candidate.atr / reference)) > tolerance:
            continue
        found.append(candidate)
    return tuple(found)


@dataclass(frozen=True, slots=True)
class ControlDraw:
    """One replicate's control: which instant, and in which direction.

    ``instant`` is ``None`` for the same-bar families, whose control *is* the
    admission's own bar and differs only in direction. Keeping one type for both
    means the study has one code path rather than a branch per family, and a
    branch per family is where a direction rule gets applied to the wrong one.
    """

    replicate: int
    instant: DecisionInstant | None
    direction: Direction


@dataclass(frozen=True, slots=True)
class MatchedAdmission:
    """One admission, its pool and its draws for one family. **Or a stated refusal.**

    ``unmatched_reason`` is set when no calendar tier reached the sealed minimum
    pool. The admission is then excluded from this family's effect and counted in
    the report — never matched against a pool too small to be a null, and never
    silently dropped.
    """

    admission: DecisionInstant
    family_id: str
    draws: tuple[ControlDraw, ...]
    pool_size: int
    radius_tier: int | None
    unmatched_reason: str | None = None

    @property
    def is_matched(self) -> bool:
        return self.unmatched_reason is None


def _direction_for(
    family: CaNullFamily,
    admission: DecisionInstant,
    control: DecisionInstant | None,
    generator: Random,
) -> Direction:
    """Which way the control is measured. **One place, four named rules.**

    Raises:
        SwingLabError: the control's own direction was asked for and the control
            reached a rung that has none. That is a build error rather than a
            data condition — `CaControlSource.MATCHED_UNCONFIRMED` only ever
            yields directional instants — and it is refused loudly rather than
            defaulted to a side.
    """
    rule = family.direction_rule
    if rule is CaDirectionRule.FMITS:
        if admission.direction is None:  # pragma: no cover - ADMITTED always has one
            raise SwingLabError("an admitted instant carries no direction")
        return admission.direction
    if rule is CaDirectionRule.OPPOSITE:
        if admission.direction is None:  # pragma: no cover - as above
            raise SwingLabError("an admitted instant carries no direction")
        return OPPOSITE_DIRECTION[admission.direction]
    if rule is CaDirectionRule.RANDOM:
        # A fair coin, drawn from the replicate's own seeded generator. `choice`
        # over a fixed two-element sequence rather than `random() < 0.5`, so the
        # draw does not depend on floating-point comparison at the boundary.
        return generator.choice((Direction.LONG, Direction.SHORT))
    if control is None or control.direction is None:
        raise SwingLabError(
            f"{family.family_id} takes the control's own direction but the "
            "control instant carries none; a control drawn from a rung below "
            "the family tally has no production direction to measure"
        )
    return control.direction


def match_admission(
    admission: DecisionInstant,
    index: PoolIndex,
    *,
    family: CaNullFamily,
    matching: MatchingSpec,
    randomisation: RandomisationSpec,
    master_seed: int,
) -> MatchedAdmission:
    """Draw every replicate's control for one admission under one family.

    The calendar tiers are tried in the sealed order and the **first** that
    reaches `matching.minimum_pool` is used, so a control comes from the tightest
    neighbourhood that can populate a pool. The tier used is carried on the
    result, so an escalated match is visible in the report rather than averaged
    into invisibility.

    Same-bar families draw no instant at all: their control is the admission's
    own bar and only the direction differs. They still consume a seeded generator
    per replicate, because a random-direction family needs one and giving the two
    same-bar families different machinery would make them incomparable.
    """
    if not isinstance(family, CaNullFamily):
        raise TypeError("family must be a CaNullFamily")
    if admission.stage is not AdmissionStage.ADMITTED:
        raise SwingLabError(
            f"{admission.symbol} at bar {admission.bar_index} is "
            f"{admission.stage.value}, not admitted; a control is drawn FOR an "
            "admission and matching anything else would compare two nulls"
        )

    def draws_for(pool: tuple[DecisionInstant, ...]) -> tuple[ControlDraw, ...]:
        collected: list[ControlDraw] = []
        for replicate in range(randomisation.draws_per_admission):
            generator = Random(
                derive_seed(
                    master=master_seed,
                    family_id=family.family_id,
                    sample=admission.sample,
                    symbol=admission.symbol,
                    bar_index=admission.bar_index,
                    replicate=replicate,
                )
            )
            control = generator.choice(pool) if pool else None
            collected.append(
                ControlDraw(
                    replicate=replicate,
                    instant=control,
                    direction=_direction_for(family, admission, control, generator),
                )
            )
        return tuple(collected)

    if not family.draws_a_control_instant:
        # The control is the admission's own bar. There is no pool, no tier and
        # nothing to be unmatched about: the instant always exists.
        return MatchedAdmission(
            admission=admission,
            family_id=family.family_id,
            draws=draws_for(()),
            pool_size=0,
            radius_tier=None,
        )

    stages = _POOL_STAGES.get(family.control_source)
    if stages is None:  # pragma: no cover - a build error
        raise SwingLabError(f"no pool is defined for {family.control_source}")
    # DEFECT CA-D3, found by independent review. `stages` was derived and never
    # used: the pool's composition came entirely from the caller's `index`, so a
    # caller handing `ca_null_eligible_but_rejected` a broad index would silently
    # measure a DIFFERENT null under the sealed family's name — and the
    # control-identity digest would still verify, because it digests what was
    # drawn rather than what should have been drawable. The index is now checked
    # against the family's own sealed pool definition.
    present = {item.stage for item in index.instants(admission.symbol)}
    unexpected = present - stages
    if unexpected:
        raise SwingLabError(
            f"{family.family_id} draws from {sorted(item.value for item in stages)} "
            f"but the index for {admission.symbol} also holds "
            f"{sorted(item.value for item in unexpected)}; measuring a sealed "
            "family against a pool it does not name would report a different "
            "null under this family's id"
        )

    for tier, radius in enumerate(matching.calendar_radius_tiers):
        pool = eligible_pool(admission, index, matching=matching, radius=radius)
        if len(pool) >= matching.minimum_pool:
            return MatchedAdmission(
                admission=admission,
                family_id=family.family_id,
                draws=draws_for(pool),
                pool_size=len(pool),
                radius_tier=tier,
            )
    widest = matching.calendar_radius_tiers[-1]
    final = eligible_pool(admission, index, matching=matching, radius=widest)
    return MatchedAdmission(
        admission=admission,
        family_id=family.family_id,
        draws=(),
        pool_size=len(final),
        radius_tier=None,
        unmatched_reason=(
            f"{admission.symbol} at bar {admission.bar_index} has {len(final)} "
            f"comparable instants at the widest declared radius ({widest} bars), "
            f"below the sealed minimum of {matching.minimum_pool}; it is "
            "EXCLUDED from this family rather than matched against a pool too "
            "small to be a null"
        ),
    )
