"""**The operator decision layer: what was concluded, and what is holding it.**

    summarise_decision(assessment, readings)  ──►  DecisionSummary   (pure)

`SetupAssessment` states a conclusion and the sentences that explain it, and
`fmis.setup_evidence` projects the evidence behind it item by item. Between the
two, a reader still has to *assemble* the two answers a person actually asks
first:

  * **Is directional evidence developing, even though no direction was stated?**
  * **Which named condition stopped this, and what must become different?**

Both are already determined by facts the assessment and `SetupReadings` carry.
Nothing here reads a candle, evaluates a policy, or reaches a conclusion the
engine did not already reach.

**Why this module lives in `fmis.swing_setup`.** ADR-0028 makes this the one
package permitted to represent trading direction. `DevelopingEvidence` names a
side, so it belongs here and nowhere above: a summary built one layer up would
have had to spell `LONG` in a package the repository forbids from doing so, or
infer a side by string-matching prose, and the second is worse than the first.

---

**The distinction this module exists to protect.**

A `WAIT` result means *no directional candidate exists*. That is a statement of
**policy**, and it is final for this reading. But the three families the policy
tallies can still lean one way while the policy refuses — because the gate
before the tally rejected the symbol, or because one family opposed the other
two. Reporting only *"WAIT, direction unavailable"* discards a real, computed
fact; reporting *"LONG"* would contradict the policy.

So this module reports a third thing, in its own vocabulary and its own type:
**developing evidence**, which is *what the families read*, never *what the
policy decided*. `DevelopingEvidence` cannot express a `SetupState`, carries no
score and no probability, and `DecisionSummary` holds the assessment's own
`state` beside it so the two are always read together. A guard test asserts that
a leaning summary never accompanies a state the policy did not reach.

**And the blocker is the policy's own path, not a re-decision.** `_blocker`
walks the same three exits `evaluate_setup` walks, in the same order, over the
same structured values — decision-context sufficiency, then the context-role
regime gate, then the directional tally — and *names* the one that fired. It
does not re-evaluate them: a test runs the whole eighty-one-fixture matrix and
asserts the named blocker always agrees with the sentence the policy itself
wrote, so the two cannot drift apart unnoticed.

**What is deliberately absent.** No price target, no invented level, no
predicted event, no time estimate, no probability, no ranking key and no field
one could be stored in. A `requirement` states what the *existing* gate already
demands (*"the context-role regime structure must be `trending`"*); it never
states what the market must do to get there.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fmis.decision_context import ContextState
from fmis.swing_setup.models import (
    Direction,
    Lean,
    SetupAssessment,
    SetupReadings,
    SetupState,
    SwingSetupError,
)
from fmis.swing_setup.policy import (
    CONTEXT_ROLE_STRUCTURE_REQUIREMENT,
    MINIMUM_AGREEING_FAMILIES,
)

__all__ = [
    "DevelopingEvidenceState",
    "DevelopingEvidence",
    "BlockerKind",
    "Blocker",
    "DecisionSummary",
    "summarise_decision",
]

#: The two `Lean` members that are votes. `CONFLICTING` and `UNAVAILABLE` are
#: the other two, and neither is a vote — for different, stated reasons that
#: `Lean`'s own docstring gives. Named once here so the distinction is read off
#: the enum rather than re-derived at each use.
VOTING_LEANS: tuple[Lean, ...] = (Lean.LONG, Lean.SHORT)

#: Printed where the policy recorded no directional family at all.
_NO_FAMILIES = "no directional family was recorded"

#: `Lean` value to `Direction` value. Both enums spell the two sides
#: identically, and this mapping is what makes that an asserted fact rather than
#: a coincidence two independent enums happen to share.
_LEAN_DIRECTION = {Lean.LONG: Direction.LONG, Lean.SHORT: Direction.SHORT}


class DevelopingEvidenceState(Enum):
    """What the directional families read — **never what the policy decided.**

    * `DIRECTION_STATED` — the policy named a direction. `lean` is that
      direction, and it is the assessment's own, not a re-derivation.
    * `LEANING` — no direction was stated, and every family that cast a vote
      cast it on the same side. Evidence is developing; a candidate does not
      exist and this member does not claim one does.
    * `DIVIDED` — no direction was stated, and the voting families disagree.
    * `NONE_READABLE` — no direction was stated and no family cast a vote at
      all: each was either self-conflicting or unreadable.

    Deliberately absent: any member naming readiness, closeness, strength or
    likelihood. This enum answers *which way did what could be read point*, and
    that is the whole of it.
    """

    DIRECTION_STATED = "direction_stated"
    LEANING = "leaning"
    DIVIDED = "divided"
    NONE_READABLE = "none_readable"


@dataclass(frozen=True, slots=True)
class DevelopingEvidence:
    """Which way the readable families point, and exactly which ones they were.

    ``lean`` is set only for `DIRECTION_STATED` and `LEANING`, and is `None`
    otherwise — there is no third member and no "neutral" side.

    The three family tuples are the **traceability contract**: every conclusion
    here names the families that produced it, so *"why did the page say the
    evidence is leaning?"* is answered by reading `agreeing` and checking those
    families on the assessment. Nothing is summarised without being cited.
    """

    state: DevelopingEvidenceState
    lean: Direction | None
    agreeing: tuple[str, ...]
    opposing: tuple[str, ...]
    non_voting: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.state, DevelopingEvidenceState):
            raise TypeError(
                f"state must be a DevelopingEvidenceState, got "
                f"{type(self.state).__name__}"
            )
        if self.lean is not None and not isinstance(self.lean, Direction):
            raise TypeError("lean must be a Direction or None")
        directional = self.state in (
            DevelopingEvidenceState.DIRECTION_STATED,
            DevelopingEvidenceState.LEANING,
        )
        if directional != (self.lean is not None):
            raise SwingSetupError(
                "lean is set if and only if the state names a side; a leaning "
                "summary with no side, or a divided one carrying a side, is not "
                "representable"
            )
        for name in ("agreeing", "opposing", "non_voting"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple of str")
            for item in value:
                if not isinstance(item, str) or not item.strip():
                    raise SwingSetupError(f"every {name} entry must be a non-empty str")
        if self.state is DevelopingEvidenceState.LEANING and self.opposing:
            raise SwingSetupError(
                "a LEANING summary cannot have an opposing family; that is what "
                "DIVIDED means"
            )
        if self.state is DevelopingEvidenceState.NONE_READABLE and (
            self.agreeing or self.opposing
        ):
            raise SwingSetupError(
                "NONE_READABLE means no family cast a vote; a voting family "
                "beside it contradicts it"
            )


class BlockerKind(Enum):
    """Which named condition stopped this reading from going further.

    The four non-`NONE` members are the four exits `evaluate_setup` actually
    has, in the order it applies them. They are **not** a severity scale and
    **not** an ordering: a symbol is at exactly one of them, and no member is
    closer to a trade than another.

    * `DECISION_CONTEXT_INSUFFICIENT` — the data was flagged inadequate before
      any market question was asked. A **system** condition, not a market one.
    * `CONTEXT_REGIME_NOT_ELIGIBLE` — the higher-timeframe regime gate. The
      reading never reached the directional tally.
    * `DIRECTIONAL_FAMILIES_DISAGREE` — the gate passed and the tally did not
      produce the agreement the policy requires.
    * `AWAITING_CONFIRMATION` — a directional candidate exists and the
      execution-timeframe confirmation has not occurred.
    * `NONE` — nothing is blocking; the setup confirmed.
    * `UNDETERMINED` — the structured facts needed to name the exit were not
      carried on this result. **An honest gap, never a guess**: the two `WAIT`
      exits below the sufficiency check are told apart by the context-role
      regime state, and a result assembled without `SetupReadings` does not have
      it. Inferring which one fired from the assessment's thesis prose is
      exactly the renderer-side inference this layer exists to remove.
    """

    DECISION_CONTEXT_INSUFFICIENT = "decision_context_insufficient"
    CONTEXT_REGIME_NOT_ELIGIBLE = "context_regime_not_eligible"
    DIRECTIONAL_FAMILIES_DISAGREE = "directional_families_disagree"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    NONE = "none"
    UNDETERMINED = "undetermined"


@dataclass(frozen=True, slots=True)
class Blocker:
    """The named condition, what was observed, and what the gate already demands.

    ``requirement`` answers *"what must become different in the existing
    analysis for this to progress?"* — and only ever by restating a condition
    the policy **already** states. *"The context-role regime structure must be
    `trending`"* is the gate's own rule. *"Price must close above X"* is not,
    unless an engine below actually supplied X for that purpose, and for these
    four exits none does.

    ``observed`` is the value that failed the condition, in the vocabulary the
    engine that produced it uses, so a reader can check the requirement against
    the reading without consulting this source.

    ``source`` names the engine or policy that owns the condition. No field here
    holds a price, a date, a probability or an estimate of when it might clear.
    """

    kind: BlockerKind
    statement: str
    requirement: str
    observed: str
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, BlockerKind):
            raise TypeError(f"kind must be a BlockerKind, got {type(self.kind).__name__}")
        for name in ("statement", "requirement", "observed", "source"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SwingSetupError(f"{name} must be a non-empty str")


@dataclass(frozen=True, slots=True)
class DecisionSummary:
    """The decision, the developing evidence, and the condition holding it.

    ``state`` is `SetupAssessment.state`, carried **by value and unchanged**, so
    that no consumer can render the developing evidence without the policy's own
    conclusion beside it. That pairing is the whole safety property of this type:
    a page showing *"evidence leaning long"* with the word `WAIT` removed would
    be a page showing a signal the policy refused to give.
    """

    symbol: str
    state: SetupState
    direction: Direction | None
    sufficiency: ContextState
    developing: DevelopingEvidence
    blocker: Blocker

    def __post_init__(self) -> None:
        if not isinstance(self.state, SetupState):
            raise TypeError(f"state must be a SetupState, got {type(self.state).__name__}")
        if (self.direction is None) != (self.state is SetupState.WAIT):
            raise SwingSetupError(
                "direction is None if and only if state is WAIT, exactly as "
                "SetupAssessment requires; a summary that disagreed with the "
                "assessment it summarises is the defect this type prevents"
            )
        if (
            self.developing.state is DevelopingEvidenceState.DIRECTION_STATED
        ) != (self.direction is not None):
            raise SwingSetupError(
                "DIRECTION_STATED is used exactly when the policy stated a "
                "direction; using it for a WAIT result would promote developing "
                "evidence into a decision"
            )


def _developing_evidence(assessment: SetupAssessment) -> DevelopingEvidence:
    """Which way the families point. **A tally of stated leans, never a vote.**

    Reads `SetupAssessment.directional_factors` and nothing else. Each family is
    placed by its own `Lean`, which `fmis.swing_setup.policy` already assigned;
    this counts them into groups and does not weight, score or threshold
    anything.

    When the policy stated a direction, that direction is carried verbatim and
    the families are grouped **against it** rather than against a re-derived
    side — so the summary can never disagree with the assessment about which way
    a candidate leans.
    """
    factors = assessment.directional_factors
    non_voting = tuple(
        factor.family for factor in factors if factor.lean not in VOTING_LEANS
    )
    voting = tuple(factor for factor in factors if factor.lean in VOTING_LEANS)

    if assessment.direction is not None:
        stated = assessment.direction
        return DevelopingEvidence(
            state=DevelopingEvidenceState.DIRECTION_STATED,
            lean=stated,
            agreeing=tuple(
                factor.family
                for factor in voting
                if _LEAN_DIRECTION[factor.lean] is stated
            ),
            opposing=tuple(
                factor.family
                for factor in voting
                if _LEAN_DIRECTION[factor.lean] is not stated
            ),
            non_voting=non_voting,
        )

    sides = {_LEAN_DIRECTION[factor.lean] for factor in voting}
    if not sides:
        return DevelopingEvidence(
            state=DevelopingEvidenceState.NONE_READABLE,
            lean=None,
            agreeing=(),
            opposing=(),
            non_voting=non_voting,
        )
    if len(sides) == 1:
        side = next(iter(sides))
        return DevelopingEvidence(
            state=DevelopingEvidenceState.LEANING,
            lean=side,
            agreeing=tuple(factor.family for factor in voting),
            opposing=(),
            non_voting=non_voting,
        )
    # Divided. Neither side is named as *the* lean, because neither is: the
    # families are reported on their own sides and the reader sees both.
    return DevelopingEvidence(
        state=DevelopingEvidenceState.DIVIDED,
        lean=None,
        agreeing=(),
        opposing=tuple(factor.family for factor in voting),
        non_voting=non_voting,
    )


def _blocker(
    assessment: SetupAssessment, readings: SetupReadings | None
) -> Blocker:
    """The policy's own exit, named. **Walked in the policy's own order.**

    `evaluate_setup` applies decision-context sufficiency, then the context-role
    regime gate, then the directional tally, and returns at the first that
    fires. This checks the same three, in the same order, over the same
    structured values — and a matrix test asserts the result always agrees with
    the sentence the policy itself wrote for that reading.

    ``readings`` is optional because a result assembled without them is a
    legitimate shape. Without them the two remaining `WAIT` exits cannot be told
    apart structurally — that distinction *is* the context-role regime state —
    so this returns `UNDETERMINED` and says so, rather than recovering the
    answer from the assessment's thesis prose. Reading a conclusion back out of
    a sentence a policy wrote is the inference this layer exists to remove.
    """
    if assessment.sufficiency is ContextState.INSUFFICIENT:
        return Blocker(
            kind=BlockerKind.DECISION_CONTEXT_INSUFFICIENT,
            statement=(
                "The decision context was reported INSUFFICIENT, so no "
                "directional candidate may be formed from it."
            ),
            requirement=(
                "Every blocking decision-context requirement must be met. This "
                "is a data-adequacy condition, not a market condition — it is "
                "about what could be read, not about what the market did."
            ),
            observed=assessment.sufficiency.value,
            source="fmis.decision_context",
        )

    if assessment.state is SetupState.WAIT and readings is None:
        return Blocker(
            kind=BlockerKind.UNDETERMINED,
            statement=(
                "This result was assembled without the structured facts the "
                "policy read, so which condition stopped it cannot be named."
            ),
            requirement=(
                "The context-role regime state must be carried on the result "
                "for the two remaining WAIT conditions to be told apart. The "
                "assessment's own thesis states the reason in words."
            ),
            observed="no readings were carried",
            source="the composition root",
        )

    if (
        assessment.state is SetupState.WAIT
        and readings is not None
        and readings.context_regime_structure
        is not CONTEXT_ROLE_STRUCTURE_REQUIREMENT
    ):
        return Blocker(
            kind=BlockerKind.CONTEXT_REGIME_NOT_ELIGIBLE,
            statement=(
                "The context-role regime is not eligible, so the reading never "
                "reached the directional tally."
            ),
            requirement=(
                "The context-role regime structure must be "
                f"{CONTEXT_ROLE_STRUCTURE_REQUIREMENT.value}. This package "
                "infers no direction from a regime; the regime classifies the "
                "environment only."
            ),
            observed=readings.context_regime_structure.value,
            source="fmis.market_regime (context role)",
        )

    if assessment.state is SetupState.WAIT:
        return Blocker(
            kind=BlockerKind.DIRECTIONAL_FAMILIES_DISAGREE,
            statement=(
                "The context-role regime gate passed and the directional "
                "families did not produce the agreement the policy requires."
            ),
            requirement=(
                f"At least {MINIMUM_AGREEING_FAMILIES} independent families "
                "must agree, with none opposing."
            ),
            observed=", ".join(
                f"{factor.family}={factor.lean.value}"
                for factor in assessment.directional_factors
            )
            or _NO_FAMILIES,
            source="fmis.swing_setup.policy",
        )

    if assessment.state is SetupState.CANDIDATE:
        return Blocker(
            kind=BlockerKind.AWAITING_CONFIRMATION,
            statement=(
                "A directional candidate exists and the execution-timeframe "
                "confirmation this policy requires has not occurred."
            ),
            requirement=(
                assessment.trigger.statement
                if assessment.trigger is not None
                else "The policy's execution-timeframe confirmation rule must "
                "be satisfied. No candidate level was named for this reading."
            ),
            observed=assessment.state.value,
            source="fmis.swing_setup.policy",
        )

    return Blocker(
        kind=BlockerKind.NONE,
        statement="Nothing is blocking this reading; the setup confirmed.",
        requirement=(
            "No further condition is named. Confirmation describes how far the "
            "analysis has gone and never how good the trade is."
        ),
        observed=assessment.state.value,
        source="fmis.swing_setup.policy",
    )


def summarise_decision(
    assessment: SetupAssessment, readings: SetupReadings | None = None
) -> DecisionSummary:
    """Summarise one assessment for an operator. **Pure, and decides nothing.**

    Reads the assessment and the readings and nothing else: no network, no
    clock, no randomness, no engine call, no candle. Equal inputs always produce
    an equal summary.

    Raises:
        TypeError: ``assessment`` is not a `SetupAssessment`, or ``readings`` is
            neither a `SetupReadings` nor `None`.
    """
    if not isinstance(assessment, SetupAssessment):
        raise TypeError(
            f"assessment must be a SetupAssessment, got {type(assessment).__name__}"
        )
    if readings is not None and not isinstance(readings, SetupReadings):
        raise TypeError(
            f"readings must be a SetupReadings or None, got {type(readings).__name__}"
        )
    return DecisionSummary(
        symbol=assessment.symbol,
        state=assessment.state,
        direction=assessment.direction,
        sufficiency=assessment.sufficiency,
        developing=_developing_evidence(assessment),
        blocker=_blocker(assessment, readings),
    )
