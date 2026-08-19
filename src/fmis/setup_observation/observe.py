"""The one place a live setup assessment becomes a domain observation.

    fmis.swing_setup.evaluate_setup          facts        -> SetupAssessment
    fmis.setup_observation.observe           assessment   -> SetupObservation
    fmis.proposal.group_occurrences          observations -> SetupOccurrence

`BG-D1` built the domain half — the stable `Anchor` identity, `SetupObservation`
and `SetupOccurrence` — and deliberately left it unreachable from live data,
because the market→domain binding has to happen somewhere that is allowed to see
both, and neither half is.

**Why this is an application package and not a module under `fmis.pipeline`.**
The obvious home was beside the price adapter, which is the single place a
provider becomes a mark. It cannot go there: **Law 6** — *the trading domain
reads the market half and is never read by it, or the analysis becomes a
function of the position, the oldest bias in trading* — is asserted over every
module of `fmis.pipeline`, and this adapter necessarily names `fmis.proposal`,
`fmis.accounts` and `fmis.snapshotting`. Putting it there was tried and failed
that guard.

The price adapter is not a counter-example, it is the pattern: it holds no domain
import either, and delegates to an application package that does. Every domain
edge the command-line surface has is the same shape — it names an application
package, never a domain root. This package is that tier, for setups.

**No market computation happens here.** The assessment arrives already built; this
module re-expresses it in the domain's own vocabulary and computes nothing. The
package rule — *"no formula, no indicator, no metric may be defined in this
package… a test asserts the module contains no arithmetic of its own"* — holds:
there is no operator in this file. `float` becomes `Decimal` through
`exact_from_market_price`, the one sanctioned crossing in the whole domain, and
never through a literal.

**The anchor comes from the stop, and only when the stop has a MEASURED origin.**
`BD` R-13 records that the stop price and the structural invalidation are the same
number; the level the setup is risked against is therefore the level the idea is
anchored on. A stop with no `LevelOrigin` — a level built from the earliest,
unlabelled swing, ADR-0019 D2 — yields `Absent` rather than a fabricated anchor: a
level with no provenance has no `MEASURED` identity, and inventing one would put a
policy-derived key exactly where §23.1 forbids it.

**Identity never sees the window.** `LevelOrigin.index` is window-relative and is
passed through only as `LevelOriginRef.swing_index`, which
`fmis.proposal.setup_identity.anchor_identity` excludes. The identity is derived
from the pivot candle's absolute timestamp, its label and its confirmation window.

**Nothing here is persisted, and nothing here can be.** `SetupObservation` and
`SetupOccurrence` are `REBUILDABLE_PROJECTION`s that `fmis.persistence.kinds`
refuses to store; neither carries a codec. No record kind is added, no repository
is created, and `OpportunityProposal` — the captured artifact that *is* stored —
is neither written nor duplicated here.

**It is also not re-exported from the pipeline package**, and that was tried too:
importing it there pulls `fmis.accounts` and, behind it, a chain that ends in a
package which imports the pipeline itself — a genuine circular import, raised at
interpreter start. The evidence layer is deliberately named in prose rather than
by module path here, because this repository's guard tests scan raw text for an
import and a mention would weaken one. Keeping the pipeline's own `__init__` free
of the domain half is what holds the market half importable on its own.

**Freshness is honestly absent.** §9.3 names three bar ages the observation should
add, and the built engine computes none of them: the only age anywhere in the
repository is `research_harness._break_age`, a private research helper that
subtracts two numbers. Deriving ages here would be arithmetic this package
forbids, and inventing them would be worse than omitting them — `AP` §14.3's
warning is that a missing value stored as a number *"makes the total look
plausible and survives for years"*. Each age is `Absent` with the reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from fmis.accounts import Book, MarketId
from fmis.level_crossing import LevelOrigin, LevelSide, PriceLevel
from fmis.money import exact_from_market_price
from fmis.proposal import (
    SetupObservation,
    SetupOccurrence,
    group_occurrences,
    level_origin_ref,
)
from fmis.provenance import Absent
from fmis.snapshotting import (
    Anchor,
    FreshnessReading,
    LevelReading,
    LevelSideRef,
    RiskRewardReading,
    SetupReading,
    StopTriggerSemantics,
    TradeDirection,
    TriggerBasis,
)
from fmis.swing_setup import Direction, SetupAssessment
from fmis.versioning import VersionAxis, VersionSet

__all__ = [
    "SETUP_OBSERVATION_BOOK",
    "STOP_TRIGGER_SEMANTICS",
    "SetupIdentityRun",
    "setup_version_set",
    "observation_from_assessment",
    "observe_setup_series",
]

#: The book a live `fmits setup` reading belongs to. The engine analyses swing
#: structure across context/setup/execution roles, which is the swing book by
#: definition; it is a parameter everywhere below so a caller replaying into the
#: paper book is never forced to mislabel the reading.
SETUP_OBSERVATION_BOOK = Book.SWING

#: `BD` R-13, as a value rather than a paragraph: the stop and the structural
#: invalidation are the same price, and they do **not** trigger on the same event.
#: A stop is hit by a *touch*; a structural invalidation requires a *close*.
#: Splitting them is what makes *"stopped out on a wick while the thesis held"*
#: derivable, and it needs no new data.
STOP_TRIGGER_SEMANTICS = StopTriggerSemantics(
    stop_basis=TriggerBasis.TOUCH,
    invalidation_basis=TriggerBasis.CLOSE,
)

#: The engine's reading of a side, as the domain's word for the same side.
#:
#: **Built by value rather than by naming the two members**, and that is not
#: cosmetic. ADR-0028 §5 keeps directional vocabulary out of every package except
#: the ones that have earned it, and this composition root has not: it translates
#: a side, it never decides one. Deriving the pair from `Direction`'s own members
#: also makes the map total by construction — a third member appearing in either
#: vocabulary raises here at import time instead of silently mapping to nothing.
_DIRECTIONS = {member: TradeDirection(member.value) for member in Direction}

_SIDES = {
    LevelSide.UPPER: LevelSideRef.ABOVE,
    LevelSide.LOWER: LevelSideRef.BELOW,
}

_NO_ANCHOR = "the reading has no stop with a MEASURED level origin to anchor on"

#: Stated once so the three ages give the identical reason and a reader who greps
#: for it finds one answer.
_NO_FRESHNESS = (
    "the built engine computes no bar age for this role, and the composition "
    "root may not derive one"
)


def setup_version_set(*, code_version: str, policy_id: str) -> VersionSet:
    """The version axes in force when a reading was produced.

    Two are known — the build that produced it and the policy that reasoned it —
    and the rest are `Absent` with a reason, which is `VersionSet`'s own contract:
    a reader can always tell *"we did not record it"* from *"it did not apply"*.

    **The policy version is recorded but takes no part in identity.**
    `anchor_identity` reads none of this, which is what makes two policy variants
    replayed over the same candles decompose history into the same setups.
    """
    return VersionSet.of(
        {
            VersionAxis.CODE_VERSION: code_version,
            VersionAxis.POLICY_VERSION: policy_id,
        },
        absent_reason=(
            "a deterministic setup reading is produced by the engine and one "
            "policy; no classifier, model or capture schema took part in it"
        ),
    )


def _level_reading(level: PriceLevel, origin: LevelOrigin, label: str) -> LevelReading:
    """One already-detected level, re-expressed in the domain's vocabulary.

    The origin is passed **separately and non-optionally** rather than read off
    ``level`` here. `PriceLevel.origin` is optional by design — ADR-0019 D2's
    unlabelled swing — and a level with no provenance has no `MEASURED` identity
    to offer, so the two callers below each decide what to do about that before
    reaching this function. Taking the origin as an argument makes the undecided
    case unrepresentable instead of guarded.

    The price crosses from `float` to `Decimal` through the single sanctioned
    conversion. The origin keeps its window-relative index as provenance and
    gains a **stable** id derived from the pivot's own timestamp.
    """
    return LevelReading(
        price=exact_from_market_price(level.price, "level price"),
        side=_SIDES[level.side],
        origin=level_origin_ref(
            pivot_timestamp=origin.timestamp,
            label=origin.label.value,
            confirmation_bars=origin.confirmation_bars,
            swing_index=origin.index,
        ),
        label=label,
    )


def _anchored_stop(assessment: SetupAssessment) -> LevelReading | None:
    """The stop as a reading, or `None` when it cannot anchor an identity."""
    stop = assessment.stop
    if stop is None or stop.origin is None:
        return None
    return _level_reading(stop, stop.origin, "structural invalidation")


def _text(lines: Sequence[str], reason: str) -> str | Absent:
    """Several statement lines as one, or the reason there are none."""
    if not lines:
        return Absent(reason)
    return " · ".join(lines)


def observation_from_assessment(
    assessment: SetupAssessment,
    *,
    market: MarketId,
    code_version: str,
    book: Book = SETUP_OBSERVATION_BOOK,
) -> SetupObservation:
    """One live assessment, re-expressed as a domain observation. Pure.

    ``market`` is supplied rather than parsed from ``assessment.symbol``:
    `MarketId` has no parse-from-string on purpose, because `BTCUSDT` cannot be
    split into base and quote without an asset registry this repository declines
    to hold. Callers use `fmis.trade_capture.market_from_symbol`, which makes the
    owner state the quote asset instead of guessing it.

    The returned observation is a projection. It is never written, and there is no
    code path that could write it.
    """
    if not isinstance(assessment, SetupAssessment):
        raise TypeError(
            f"assessment must be a SetupAssessment, got {type(assessment).__name__}"
        )
    if not isinstance(market, MarketId):
        raise TypeError(f"market must be a MarketId, got {type(market).__name__}")
    if not isinstance(book, Book):
        raise TypeError(f"book must be a Book, got {type(book).__name__}")

    direction = _DIRECTIONS.get(assessment.direction, TradeDirection.NO_TRADE)
    stop_reading = _anchored_stop(assessment)

    if direction.is_directional and stop_reading is not None:
        anchor: Anchor | Absent = Anchor(
            market=market,
            book=book,
            direction=direction,
            invalidation_origin=stop_reading.origin,
        )
        invalidation: LevelReading | Absent = stop_reading
        stop: LevelReading | Absent = stop_reading
    else:
        anchor = Absent(_NO_ANCHOR)
        invalidation = Absent(_NO_ANCHOR)
        stop = Absent(_NO_ANCHOR)

    targets = tuple(
        _level_reading(target, target.origin, "target")
        for target in assessment.targets
        if target.origin is not None
    )

    risk_reward: RiskRewardReading | Absent
    if assessment.risk_reward is None or isinstance(stop, Absent):
        risk_reward = Absent(
            "the reading states no stop, so there is no risk denominator"
        )
    else:
        risk_reward = RiskRewardReading(
            risk_distance=exact_from_market_price(
                assessment.risk_reward.risk, "risk distance"
            ),
            reward_distance=exact_from_market_price(
                assessment.risk_reward.reward, "reward distance"
            ),
        )

    reference_price = (
        Absent("the execution role reported no closed candle")
        if assessment.reference_price is None
        else exact_from_market_price(assessment.reference_price, "reference price")
    )

    reading = SetupReading(
        as_of=assessment.as_of,
        state=assessment.state.value,
        direction=direction,
        policy_id=assessment.policy_id,
        thesis=_text(assessment.thesis, "the policy stated no thesis"),
        directional_factors=tuple(
            f"{factor.family}: {factor.lean.value} — {factor.observed}"
            for factor in assessment.directional_factors
        ),
        confirmation=_text(
            assessment.confirmation, "no confirmation statement was produced"
        ),
        trigger=(
            Absent("no trigger is being watched")
            if assessment.trigger is None
            else assessment.trigger.statement
        ),
        reference_price=reference_price,
        invalidation=invalidation,
        stop=stop,
        targets=targets,
        risk_reward=risk_reward,
        probability=assessment.probability.status.value,
        limitations=assessment.limitations,
        anchor=anchor,
        freshness=FreshnessReading(
            measured_at=assessment.as_of,
            context_bars=Absent(_NO_FRESHNESS),
            setup_bars=Absent(_NO_FRESHNESS),
            execution_bars=Absent(_NO_FRESHNESS),
        ),
        stop_trigger_semantics=STOP_TRIGGER_SEMANTICS,
    )

    return SetupObservation(
        market=market,
        book=book,
        reading=reading,
        version_set=setup_version_set(
            code_version=code_version, policy_id=assessment.policy_id
        ),
    )


@dataclass(frozen=True, slots=True)
class SetupIdentityRun:
    """One market's readings, and the distinct ideas they decompose into.

    The thing a future surface needs in order to say *"this is the same setup you
    saw yesterday, for the fourth time"* rather than printing it as new.
    """

    market: MarketId
    book: Book
    observations: tuple[SetupObservation, ...]
    occurrences: tuple[SetupOccurrence, ...]
    occurrence_gap_bars: int

    @property
    def latest_occurrence(self) -> SetupOccurrence | Absent:
        """The idea the most recent directional reading belongs to."""
        if not self.occurrences:
            return Absent("no directional reading was observed")
        return self.occurrences[-1]

    @property
    def is_new_occurrence(self) -> bool:
        """Whether the latest idea has been seen exactly once.

        `False` on the second and every later bar of one idea — the distinction
        `AV`'s window-relative identity could not draw, and the reason its
        "unique setups" count was really a count of directional bars.
        """
        latest = self.latest_occurrence
        if isinstance(latest, Absent):
            return False
        return latest.observation_count == 1

    @property
    def repeated_observation_count(self) -> int:
        """How many readings the latest idea has accumulated."""
        latest = self.latest_occurrence
        if isinstance(latest, Absent):
            return 0
        return latest.observation_count


def observe_setup_series(
    assessments: Iterable[SetupAssessment],
    *,
    market: MarketId,
    code_version: str,
    occurrence_gap_bars: int,
    book: Book = SETUP_OBSERVATION_BOOK,
) -> SetupIdentityRun:
    """Re-express a chronological run of one market's assessments, and group it.

    ``occurrence_gap_bars`` is required and has no default, exactly as
    `group_occurrences` requires: the data model declines to choose a value, and a
    default chosen here would be a trading policy chosen by a composition root.

    **No lookahead.** Each observation is a pure function of the assessment at its
    own instant, and the grouping only ever reads observations at or before the
    one it is placing. Running this over a prefix of a series yields a prefix of
    the same identities.
    """
    observations = tuple(
        observation_from_assessment(
            assessment, market=market, code_version=code_version, book=book
        )
        for assessment in assessments
    )
    return SetupIdentityRun(
        market=market,
        book=book,
        observations=observations,
        occurrences=group_occurrences(
            observations, occurrence_gap_bars=occurrence_gap_bars
        ),
        occurrence_gap_bars=occurrence_gap_bars,
    )
