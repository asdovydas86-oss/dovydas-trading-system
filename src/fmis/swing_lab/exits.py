"""Exit management, measured rather than assumed. **Mechanisms, no threshold mining.**

Milestone BX measured that **68.8 % of trades gave back at least a full R of open
profit** and then declined to test any fix, because
`fmis.swing_lab.trades.simulate_trade` resolves exactly one stop against exactly
one target and a partial exit adds a third level to bars it already could not
order. `fmis.swing_lab.intrabar` removes that obstacle with real lower-timeframe
candles, so the question is now answerable — and this module answers it with the
**smallest** set of rules that can, because the brief is explicit that ten
trailing variants would be threshold mining rather than research.

===========================  ==========================================================
**Milestone BY — resolved inside a bar, by the ladder**
`FULL_TARGET`                the control: BW/BX's own rule, one stop and one target
`PARTIAL_AT_1R`              half off at +1R, the remainder to the structural target
`BREAK_EVEN_AT_1R`           the stop moves to the entry once +1R has been reached
`TRAIL_PRIOR_BAR_EXTREME`    once armed at +1R, the stop trails the prior bar's extreme
---------------------------  ----------------------------------------------------------
**Milestone BZ — decided at a bar's close, filled at the next bar's open**
`THESIS_FAILURE`             the setup-timeframe structure opposed the direction
`STAGNATION`                 no favourable progress within a declared bar count
`GIVEBACK_FRACTION`          a declared share of a declared peak was surrendered
`STRUCTURAL_TRAIL`           the stop follows newly CONFIRMED structural levels
`THESIS_AND_GIVEBACK`        the sealed combination of the first and the third
===========================  ==========================================================

**BY's four and BZ's five are resolved in different places, and that is the
design rather than an inconsistency.** BY's watch a *price* and can therefore be
ordered inside a bar by descending the ladder. BZ's read a *close* — a structural
verdict, a bar count, a peak-to-close give-back — and a close is settled only when
the bar ends, so there is nothing finer to descend to. BZ's mechanics are
consequently evaluated at execution-bar boundaries and filled at the next bar's
open, which is the same one-bar convention that separates a signal from its entry
fill everywhere else in this package. Neither family may be read as the other.

**One convention decides what these numbers mean, and it is stated rather than
buried: a state change takes effect from the bar AFTER the bar that triggered
it.** A break-even stop armed by a bar's high is not also tested against that
same bar's low, because four prices cannot say whether the low came before or
after the high, and `fmis.swing_lab.intrabar` exists precisely so this module
never guesses. Where the ladder *can* order two events — the bar touched both the
trigger and the stop — the walk descends to 1H, then 15m, and only then refuses.
The convention therefore applies at the **finest resolution the data supports**,
not at 4H.

**What is deliberately absent.**

* No trailing threshold is swept. `TRAIL_PRIOR_BAR_EXTREME` arms at +1R because
  that is the same number `PARTIAL_AT_1R` and `BREAK_EVEN_AT_1R` use — the R at
  which BX measured the give-back — not because 1R won a comparison.
* No mechanic may *widen* a stop. Every state change tightens or exits, and the
  loop asserts it: a "management" rule that moved a stop away from the entry
  would be improving a losing trade's odds by taking more risk than the plan
  declared, which is not exit management.
* No mechanic reads a level this module derived. The structural stop and target
  arrive from `fmis.swing_lab.geometry`, already selected.

**The partial exit and `LabTrade` are exactly compatible, which is why no new
metrics layer exists.** A trade leaving in two pieces at prices ``p1`` and ``p2``
with weights ``f`` and ``1-f`` has gross return ``sign × (f·p1 + (1-f)·p2 − e)``
and fees ``rate × (e + f·p1 + (1-f)·p2)``. Both are functions of the
notional-weighted average exit alone, so recording that average as
`LabTrade.exit_price` reproduces the leg arithmetic **exactly** — and
`fmis.swing_lab.trades.reprice` then costs a partial-exit trade correctly without
knowing it was one. A test asserts the identity leg-by-leg rather than trusting
the algebra here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Final

from fmis.paper.fills import fill_at_level
from fmis.paper.models import PriceBar
from fmis.snapshotting import TradeDirection
from fmis.swing_lab.intrabar import BarLadder, TouchLevel
from fmis.swing_lab.models import LabExitReason, LabTrade, SwingLabError
from fmis.swing_lab.persistence import ThesisObservation, ThesisTimeline, thesis_state
from fmis.swing_setup.models import Direction
from fmis.trade_lifecycle import PaperCostPolicy

__all__ = [
    "ARMING_R",
    "DEFAULT_PARTIAL_FRACTION",
    "ExitMechanic",
    "ExitPolicy",
    "PRE_DECLARED_EXIT_POLICIES",
    "BZ_EXIT_POLICIES",
    "COMBINATION_COMPONENTS",
    "ExitLeg",
    "ManagedResult",
    "simulate_managed_trade",
    "exit_policy_by_id",
]

#: The R multiple at which every managed mechanic arms. **One number, shared.**
#: Using the same arming point for the partial, the break-even and the trail is
#: what keeps this a comparison of *mechanics* rather than a sweep of a
#: threshold: three rules that differ only in what they do at +1R can be read
#: against each other, and three rules that also differ in *when* cannot.
ARMING_R: Final[Decimal] = Decimal("1")

#: How much of the position `PARTIAL_AT_1R` realises. Half, pre-declared, never
#: swept: a fraction chosen after seeing results would be the whole finding.
DEFAULT_PARTIAL_FRACTION: Final[Decimal] = Decimal("0.5")

_DIRECTION_TO_TRADE: Final[dict[Direction, TradeDirection]] = {
    Direction.LONG: TradeDirection.LONG,
    Direction.SHORT: TradeDirection.SHORT,
}

_STOP: Final[str] = "stop"
_TARGET: Final[str] = "target"
_ARM: Final[str] = "arm"


class ExitMechanic(str, Enum):
    """How an open position is managed between the entry and a terminal exit.

    The first four are Milestone BY's and are **frozen**: their values appear in
    BY's sealed pre-registration payload, so renaming one would silently
    invalidate a published digest. The last four are Milestone BZ's, added
    additively — a new member changes no existing member's value, and BY's seal
    is asserted byte-identical after this file grew.

    BZ's four differ from BY's in one structural way, and it decides where they
    are evaluated: **they act on a bar's CLOSE, not on a price touched inside
    it.** A thesis reading, a stagnation count, a peak-to-close give-back and a
    newly confirmed structural level are all facts a bar only settles when it
    ends, so none of them can be resolved by descending a ladder — there is
    nothing finer to descend to. They are therefore evaluated at execution-bar
    boundaries and executed at the **next** bar's open, which is the same
    convention `fmis.swing_lab.trades.simulate_trade` uses to fill an entry from
    a signal, mirrored.
    """

    FULL_TARGET = "full_target"
    PARTIAL_AT_1R = "partial_at_1r"
    BREAK_EVEN_AT_1R = "break_even_at_1r"
    TRAIL_PRIOR_BAR_EXTREME = "trail_prior_bar_extreme"
    THESIS_FAILURE = "thesis_failure"
    STAGNATION = "stagnation"
    GIVEBACK_FRACTION = "giveback_fraction"
    STRUCTURAL_TRAIL = "structural_trail"
    THESIS_AND_GIVEBACK = "thesis_and_giveback"

    @property
    def arms(self) -> bool:
        """Whether this mechanic watches for `ARMING_R` as a *watched level*.

        BZ's give-back mechanic has an arming threshold too, but it is measured
        from the running peak at a bar's close rather than watched as a price
        inside the bar, so it does not add a third level to the ladder and does
        not appear here. Conflating the two would put a level in
        `_State.levels()` that nothing ever resolves against.
        """
        return self in _LEVEL_ARMING_MECHANICS

    @property
    def decides_on_close(self) -> bool:
        """Whether this mechanic is evaluated at an execution bar's close."""
        return self in _CLOSE_DECIDED_MECHANICS


_LEVEL_ARMING_MECHANICS: Final[frozenset["ExitMechanic"]] = frozenset(
    {
        ExitMechanic.PARTIAL_AT_1R,
        ExitMechanic.BREAK_EVEN_AT_1R,
        ExitMechanic.TRAIL_PRIOR_BAR_EXTREME,
    }
)

_CLOSE_DECIDED_MECHANICS: Final[frozenset["ExitMechanic"]] = frozenset(
    {
        ExitMechanic.THESIS_FAILURE,
        ExitMechanic.STAGNATION,
        ExitMechanic.GIVEBACK_FRACTION,
        ExitMechanic.STRUCTURAL_TRAIL,
        ExitMechanic.THESIS_AND_GIVEBACK,
    }
)


@dataclass(frozen=True, slots=True)
class ExitPolicy:
    """One pre-declared exit mechanic, with the parameters its own mechanic takes.

    Milestone BZ's four mechanics each need one or two numbers BY's did not, and
    every one of them defaults to ``None``. That default is load-bearing rather
    than tidy: `payload` emits a key **only when it is set**, so the four BY
    policies digest to exactly the bytes they digested before this class grew,
    and BY's pinned pre-registration seal is unaffected. A test asserts the seal
    is byte-identical, because "additive" is a claim worth checking rather than
    a claim worth making.

    Each parameter is validated against the mechanic that uses it, in both
    directions: a stagnation policy without a bar count is refused, and so is a
    full-target policy that carries one. A parameter that is silently ignored is
    a parameter a reader will believe took effect.
    """

    policy_id: str
    title: str
    mechanic: ExitMechanic
    hypothesis: str
    partial_fraction: Decimal = DEFAULT_PARTIAL_FRACTION
    #: `STAGNATION`: how many execution bars a position may fail to make
    #: `stagnation_progress_r` of favourable progress before it is closed.
    stagnation_bars: int | None = None
    #: `STAGNATION`: the favourable excursion that counts as progress.
    stagnation_progress_r: Decimal | None = None
    #: `GIVEBACK_FRACTION`: the peak favourable excursion at which the mechanic
    #: arms. Below it there is no profit worth protecting and the rule is inert.
    giveback_arm_r: Decimal | None = None
    #: `GIVEBACK_FRACTION`: the share of the peak whose surrender closes the
    #: position. Expressed as a fraction of the peak rather than as an absolute
    #: R, so the rule does not become stricter the better the trade went.
    giveback_fraction: Decimal | None = None

    def __post_init__(self) -> None:
        for name in ("policy_id", "title", "hypothesis"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SwingLabError(f"{name} must be a non-empty str")
        if not isinstance(self.mechanic, ExitMechanic):
            raise TypeError("mechanic must be an ExitMechanic")
        if not isinstance(self.partial_fraction, Decimal):
            raise TypeError("partial_fraction must be a Decimal")
        if not Decimal(0) < self.partial_fraction < Decimal(1):
            raise SwingLabError(
                "partial_fraction must lie strictly between 0 and 1, got "
                f"{self.partial_fraction}; 0 and 1 are the two mechanics that "
                "already have their own names"
            )
        self._check_parameters()

    def _check_parameters(self) -> None:
        """Each mechanic carries its own numbers, and only its own."""
        required: tuple[str, ...] = _REQUIRED_PARAMETERS.get(self.mechanic, ())
        for name in _ALL_PARAMETERS:
            value = getattr(self, name)
            if name in required:
                if value is None:
                    raise SwingLabError(
                        f"{self.policy_id}: mechanic {self.mechanic.value} "
                        f"requires {name}"
                    )
            elif value is not None:
                raise SwingLabError(
                    f"{self.policy_id}: mechanic {self.mechanic.value} does not "
                    f"read {name}, so carrying one would be a parameter a reader "
                    "believes took effect"
                )
        if self.stagnation_bars is not None:
            if isinstance(self.stagnation_bars, bool) or not isinstance(
                self.stagnation_bars, int
            ):
                raise TypeError("stagnation_bars must be an int")
            if self.stagnation_bars < 1:
                raise SwingLabError("stagnation_bars must be at least 1")
        for name in ("stagnation_progress_r", "giveback_arm_r", "giveback_fraction"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal")
        if self.stagnation_progress_r is not None and self.stagnation_progress_r <= 0:
            raise SwingLabError("stagnation_progress_r must be positive")
        if self.giveback_arm_r is not None and self.giveback_arm_r <= 0:
            raise SwingLabError("giveback_arm_r must be positive")
        if self.giveback_fraction is not None and not (
            Decimal(0) < self.giveback_fraction <= Decimal(1)
        ):
            raise SwingLabError(
                "giveback_fraction must lie in (0, 1]; surrendering none of the "
                "peak is not a rule and surrendering more than all of it is not "
                "reachable"
            )

    @property
    def is_baseline(self) -> bool:
        return self.mechanic is ExitMechanic.FULL_TARGET

    @property
    def needs_timeline(self) -> bool:
        """Whether this mechanic reads the structural timeline at all."""
        return self.mechanic in _TIMELINE_MECHANICS

    def payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "policy_id": self.policy_id,
            "title": self.title,
            "mechanic": self.mechanic.value,
            "hypothesis": self.hypothesis,
            "partial_fraction": str(self.partial_fraction),
        }
        # Emitted only when set. See the class docstring: this is what keeps
        # Milestone BY's sealed digest byte-identical after BZ grew this type.
        if self.stagnation_bars is not None:
            payload["stagnation_bars"] = self.stagnation_bars
        if self.stagnation_progress_r is not None:
            payload["stagnation_progress_r"] = str(self.stagnation_progress_r)
        if self.giveback_arm_r is not None:
            payload["giveback_arm_r"] = str(self.giveback_arm_r)
        if self.giveback_fraction is not None:
            payload["giveback_fraction"] = str(self.giveback_fraction)
        return payload


_ALL_PARAMETERS: Final[tuple[str, ...]] = (
    "stagnation_bars",
    "stagnation_progress_r",
    "giveback_arm_r",
    "giveback_fraction",
)

_REQUIRED_PARAMETERS: Final[dict[ExitMechanic, tuple[str, ...]]] = {
    ExitMechanic.STAGNATION: ("stagnation_bars", "stagnation_progress_r"),
    ExitMechanic.GIVEBACK_FRACTION: ("giveback_arm_r", "giveback_fraction"),
    ExitMechanic.THESIS_AND_GIVEBACK: ("giveback_arm_r", "giveback_fraction"),
}

#: Which single mechanics a combination is composed of. Declared as data so the
#: pre-registration can state the components and the promotion rule can require
#: each of them to have earned its place independently.
COMBINATION_COMPONENTS: Final[dict[ExitMechanic, tuple[ExitMechanic, ...]]] = {
    ExitMechanic.THESIS_AND_GIVEBACK: (
        ExitMechanic.THESIS_FAILURE,
        ExitMechanic.GIVEBACK_FRACTION,
    ),
}

#: The mechanics that consult `fmis.swing_lab.persistence.ThesisTimeline`. Both
#: read structure the production engines produced at that instant; neither
#: derives any structure of its own.
_TIMELINE_MECHANICS: Final[frozenset[ExitMechanic]] = frozenset(
    {
        ExitMechanic.THESIS_FAILURE,
        ExitMechanic.STRUCTURAL_TRAIL,
        ExitMechanic.THESIS_AND_GIVEBACK,
    }
)


PRE_DECLARED_EXIT_POLICIES: Final[tuple[ExitPolicy, ...]] = (
    ExitPolicy(
        policy_id="exit_full_target",
        title="Full position to the structural target (control)",
        mechanic=ExitMechanic.FULL_TARGET,
        hypothesis=(
            "The rule Milestones BW and BX measured, unchanged: one stop, one "
            "target, no management. A CONTROL, not a candidate. Run over the "
            "same ladder as every other mechanic so the comparison isolates "
            "management rather than resolution — and run a second time WITHOUT "
            "a ladder, where it must reproduce simulate_trade exactly."
        ),
    ),
    ExitPolicy(
        policy_id="exit_partial_1r",
        title="Half off at +1R, remainder to the structural target",
        mechanic=ExitMechanic.PARTIAL_AT_1R,
        hypothesis=(
            "BX measured 68.8% of trades giving back a full R of open profit "
            "and 85.7% of target exits paying under +1R. If the target is "
            "systematically too near, realising half the position at +1R should "
            "convert some of that give-back into a booked return. The risk this "
            "rule runs is the one that must be reported beside its expectancy: "
            "it halves the position before every large winner too, so a "
            "positive-tail strategy can be made worse by it."
        ),
    ),
    ExitPolicy(
        policy_id="exit_break_even_1r",
        title="Stop to break-even once +1R is reached",
        mechanic=ExitMechanic.BREAK_EVEN_AT_1R,
        hypothesis=(
            "The cheapest possible answer to the give-back finding: keep the "
            "whole position, but refuse to let a trade that was a full R ahead "
            "become a full R loss. It cannot improve a winner and cannot "
            "worsen the entry; it can only convert some losers into scratches "
            "and some winners into scratches, and which of those dominates is "
            "exactly what is being measured."
        ),
    ),
    ExitPolicy(
        policy_id="exit_trail_prior_bar",
        title="Trail the prior execution bar's extreme once armed at +1R",
        mechanic=ExitMechanic.TRAIL_PRIOR_BAR_EXTREME,
        hypothesis=(
            "The only trailing rule tested, and it is deliberately the dumbest "
            "one that is fully deterministic: once +1R has been reached, the "
            "stop becomes the previous CLOSED execution-timeframe bar's adverse "
            "extreme and never loosens. It is NOT a structural trail — the "
            "prior bar's low is a price, not a level the structural engines "
            "produced — and it is labelled that way wherever it is reported."
        ),
    ),
)

#: Milestone BZ's exit families. **Mechanisms, not a parameter grid.**
#:
#: Five entries for five *mechanisms*, each with the smallest number of numbers
#: it can have. There is deliberately no sweep: BX and BY between them measured
#: nineteen geometry points, and the lesson BY drew was that a twentieth was not
#: the answer. A family that needs a threshold takes one pre-declared value, and
#: the robustness question — does the mechanism survive a nearby value — is asked
#: once, of the neighbourhood, rather than answered by picking the best cell.
#:
#: `bz_exit_control` is BY's `exit_full_target` under a BZ id. It is measured so
#: every BZ figure has a control taken through the identical machinery, and its
#: numbers must reproduce BY's §11 control exactly.
BZ_EXIT_POLICIES: Final[tuple[ExitPolicy, ...]] = (
    ExitPolicy(
        policy_id="bz_exit_control",
        title="Full position to the structural target (BZ control)",
        mechanic=ExitMechanic.FULL_TARGET,
        hypothesis=(
            "H0. The rule BW, BX and BY all measured, unchanged: one stop, one "
            "target, no management. A CONTROL, not a candidate. Every other BZ "
            "family is a difference FROM this, measured on the same setups over "
            "the same bars, so a difference between two rows is management and "
            "not machinery. It must reproduce BY's own control to the digit."
        ),
    ),
    ExitPolicy(
        policy_id="bz_exit_thesis_failure",
        title="Exit when the setup-timeframe thesis is invalidated or conflicted",
        mechanic=ExitMechanic.THESIS_FAILURE,
        hypothesis=(
            "H1. If a swing thesis persists at all, the structural engines that "
            "admitted it should be able to say when it has stopped holding. The "
            "position is closed at the next bar's open once the setup-timeframe "
            "structural trend OPPOSES the direction the trade was taken in, or "
            "once the setup and execution timeframes disagree in sign. "
            "PREDICTION: if persistence is real, this exits losers earlier than "
            "the stop does and leaves winners alone, so expectancy improves and "
            "the average loser shrinks. REFUTED BY: no improvement over H0 on "
            "development, or an improvement on development that does not survive "
            "validation or the holdout. Deliberately does NOT fire on WEAKENED — "
            "a rule that exits on every pass through NEUTRAL is a time stop."
        ),
    ),
    ExitPolicy(
        policy_id="bz_exit_stagnation_12",
        title="Exit after 12 bars without +0.5R of favourable progress",
        mechanic=ExitMechanic.STAGNATION,
        hypothesis=(
            "H2. BX measured a median hold of one bar and a p75 of three, so a "
            "position still going nowhere after twelve 4H bars — two calendar "
            "days — has not behaved like the setups this strategy admits. "
            "PREDICTION: if edge decays with time in trade, releasing capital "
            "from stagnant positions improves expectancy per trade. REFUTED BY: "
            "no improvement over H0 on development, or an improvement that does "
            "not survive both unseen samples. The threshold pair (12 bars, "
            "+0.5R) is declared here and swept nowhere; 8 and 18 are measured "
            "ONLY as the robustness neighbourhood and neither may be promoted."
        ),
        stagnation_bars=12,
        stagnation_progress_r=Decimal("0.5"),
    ),
    ExitPolicy(
        policy_id="bz_exit_giveback_half",
        title="Exit after surrendering half of a peak of at least +1R",
        mechanic=ExitMechanic.GIVEBACK_FRACTION,
        hypothesis=(
            "H3. BX measured 68.8% of development trades giving back a full R of "
            "open profit, against a mean MFE of +5.26R and a mean realised "
            "-0.276R. This is the direct answer to that finding: once a position "
            "has run +1R, surrendering half of whatever peak it reached closes "
            "it. PREDICTION: the give-back distribution is wide enough that "
            "capping it converts a material share of the surrendered R into "
            "booked return. REFUTED BY: no improvement over H0 on development, "
            "or an improvement that does not survive both unseen samples. THE "
            "RISK THAT MUST BE REPORTED BESIDE ITS EXPECTANCY: it also closes "
            "every large winner on its first ordinary retracement, so a "
            "positive-tail strategy can be made materially worse by it."
        ),
        giveback_arm_r=Decimal("1"),
        giveback_fraction=Decimal("0.5"),
    ),
    ExitPolicy(
        policy_id="bz_exit_structural_trail",
        title="Trail the stop to newly confirmed execution-timeframe levels",
        mechanic=ExitMechanic.STRUCTURAL_TRAIL,
        hypothesis=(
            "H4. The only trailing rule BZ tests, and unlike BY's "
            "exit_trail_prior_bar it IS structural: the stop moves to the "
            "nearest execution-timeframe protective level the production "
            "engines had ALREADY CONFIRMED at that bar, never to a bar's "
            "extreme and never to a pivot confirmed later in the window. "
            "PREDICTION: if structure persists after entry, structural levels "
            "are better stops than either the initial level or a price. "
            "REFUTED BY: no improvement over H0 on development, or an "
            "improvement that does not survive both unseen samples. A bar at "
            "which the engines confirmed nothing moves nothing — the rule never "
            "falls back to a price when structure is absent."
        ),
    ),
    ExitPolicy(
        policy_id="bz_exit_thesis_and_giveback",
        title="Thesis failure OR half a peak of at least +1R surrendered",
        mechanic=ExitMechanic.THESIS_AND_GIVEBACK,
        hypothesis=(
            "H5. The one COMBINATION, and it is sealed here — before any "
            "component's result exists — precisely so it cannot be assembled "
            "afterwards from whichever two happened to work. It composes H1 and "
            "H3 unchanged and at their own declared thresholds; neither is "
            "loosened to make room for the other, and the exit reason names "
            "which component fired so a combined result is always attributable. "
            "PREDICTION: the two act on different failure modes — a thesis that "
            "reversed and a profit that evaporated — so if BOTH show independent "
            "evidence their union should beat either alone. REFUTED BY: no "
            "improvement over the better of its two components on development, "
            "or an improvement that does not survive both unseen samples. "
            "ADDITIONALLY BARRED FROM PROMOTION unless each component "
            "independently cleared the development-expectancy criterion, so a "
            "combination can never launder a component that failed on its own."
        ),
        giveback_arm_r=Decimal("1"),
        giveback_fraction=Decimal("0.5"),
    ),
)

_EXITS_BY_ID: Final[dict[str, ExitPolicy]] = {
    policy.policy_id: policy
    for policy in PRE_DECLARED_EXIT_POLICIES + BZ_EXIT_POLICIES
}

if len(_EXITS_BY_ID) != len(PRE_DECLARED_EXIT_POLICIES) + len(BZ_EXIT_POLICIES):
    raise SwingLabError(  # pragma: no cover
        "two pre-declared exit policies share a policy_id"
    )


def exit_policy_by_id(policy_id: str) -> ExitPolicy:
    """Look one exit policy up by id, naming the alternatives when it is absent."""
    try:
        return _EXITS_BY_ID[policy_id]
    except KeyError:
        raise SwingLabError(
            f"no pre-declared exit policy {policy_id!r}; this milestone defines "
            f"{', '.join(sorted(_EXITS_BY_ID))}"
        ) from None


@dataclass(frozen=True, slots=True)
class ExitLeg:
    """One piece of a position leaving, at one price, for one named reason."""

    fraction: Decimal
    price: Decimal
    at: datetime
    reason: LabExitReason
    interval: str

    def payload(self) -> dict[str, object]:
        return {
            "fraction": str(self.fraction),
            "price": str(self.price),
            "at": self.at.isoformat(),
            "reason": self.reason.value,
            "interval": self.interval,
        }


@dataclass(frozen=True, slots=True)
class ManagedResult:
    """One managed trade, plus how much lower-timeframe evidence it consumed."""

    trade: LabTrade
    legs: tuple[ExitLeg, ...]
    descents: int
    ambiguous_bar_at: datetime | None
    armed_at: datetime | None


@dataclass(slots=True)
class _State:
    """Everything the walk mutates. Separated so the loop reads as a state machine."""

    side: TradeDirection
    entry: Decimal
    risk: Decimal
    stop: Decimal
    target: Decimal
    policy: ExitPolicy
    armed: bool = False
    armed_at: datetime | None = None
    remaining: Decimal = Decimal(1)
    legs: list[ExitLeg] = field(default_factory=list)
    descents: int = 0

    @property
    def arming_price(self) -> Decimal:
        return self.entry + self.side.sign * ARMING_R * self.risk

    def levels(self) -> tuple[TouchLevel, ...]:
        watched = [
            TouchLevel(name=_STOP, price=self.stop, favourable=False),
            TouchLevel(name=_TARGET, price=self.target, favourable=True),
        ]
        if self.policy.mechanic.arms and not self.armed:
            price = self.arming_price
            # The arming price can coincide with the target when the structural
            # objective pays exactly 1R. Watching two levels at one price would
            # be permanent, unresolvable ambiguity invented by this module, so
            # the arming level is dropped: the target is the stronger event and
            # reaching it ends the trade anyway.
            if price != self.target:
                watched.append(TouchLevel(name=_ARM, price=price, favourable=True))
        return tuple(watched)

    def tighten(self, price: Decimal) -> None:
        """Move the stop toward the entry, never away from it. Asserted, not assumed."""
        if self.side.sign * (price - self.stop) < 0:
            raise SwingLabError(
                f"an exit mechanic tried to move the stop from {self.stop} to "
                f"{price}, which is further from the entry; management may only "
                "tighten or exit"
            )
        self.stop = price

    def close(self, fraction: Decimal, price: Decimal, at: datetime, reason: LabExitReason, interval: str) -> None:
        self.legs.append(
            ExitLeg(fraction=fraction, price=price, at=at, reason=reason, interval=interval)
        )
        self.remaining -= fraction


class _Step(str, Enum):
    CONTINUE = "continue"
    TERMINAL = "terminal"
    AMBIGUOUS = "ambiguous"


def _apply(state: _State, level: TouchLevel, bar: PriceBar, price: Decimal) -> _Step:
    """One resolved touch, turned into a state change or a terminal exit."""
    if level.name == _TARGET:
        state.close(state.remaining, price, bar.open_time, LabExitReason.TARGET, bar.interval)
        return _Step.TERMINAL
    if level.name == _STOP:
        state.close(state.remaining, price, bar.open_time, LabExitReason.STOP, bar.interval)
        return _Step.TERMINAL

    state.armed = True
    state.armed_at = bar.open_time
    mechanic = state.policy.mechanic
    if mechanic is ExitMechanic.PARTIAL_AT_1R:
        # A resting limit at +1R: it fills at its own price when touched, which
        # is what `fill_at_level` returns unless the bar gapped past it.
        state.close(
            state.policy.partial_fraction, price, bar.open_time,
            LabExitReason.TARGET, bar.interval,
        )
        return _Step.CONTINUE
    if mechanic is ExitMechanic.BREAK_EVEN_AT_1R:
        state.tighten(state.entry)
        return _Step.CONTINUE
    # TRAIL_PRIOR_BAR_EXTREME arms here and moves at each execution-bar
    # boundary; there is no prior bar inside this bar to trail to yet.
    return _Step.CONTINUE


def _process(
    bar: PriceBar, state: _State, ladder: BarLadder | None, depth: int
) -> _Step:
    """Resolve every event inside one bar, descending the ladder only when it must.

    **A state change takes effect from the next bar at this resolution.** A single
    resolved touch therefore returns `CONTINUE` rather than re-examining the same
    bar: re-testing a freshly armed break-even stop against the same bar's low
    would compare it to a price that may have occurred *before* the high that
    armed it, which is the exact intrabar guess this package refuses to make. The
    descent below is what recovers the resolution that convention costs.
    """
    levels = state.levels()
    hits = [
        level for level in levels
        if bar.reached(state.side, level.price, favourable=level.favourable)
    ]
    if not hits:
        return _Step.CONTINUE
    if len(hits) == 1:
        price, _ = fill_at_level(state.side, bar, hits[0].price, favourable=hits[0].favourable)
        state.descents = max(state.descents, depth)
        return _apply(state, hits[0], bar, price)

    # Two or more levels in one bar. A level the bar OPENED beyond was reached at
    # the bar's first price and nothing inside it can have preceded that; several
    # such levels are past the open simultaneously and cannot be ordered at all.
    #
    # **Only consulted when a ladder is present.** `fmis.swing_lab.trades.simulate_trade`
    # does not use this fact, and `exit_full_target`'s sealed hypothesis requires
    # the no-ladder run to reproduce it *exactly* — so a run that resolved a bar
    # the coarse simulator refused would not be the control the pre-registration
    # defines, and the ambiguity count it produces would not be the one Milestone
    # BX measured. The extra fact belongs to the laddered run, beside the finer
    # candles, where it is reported as lower-timeframe resolution.
    opened = (
        [
            level for level in hits
            if bar.opened_beyond(state.side, level.price, favourable=level.favourable)
        ]
        if ladder is not None
        else []
    )
    if len(opened) == 1:
        price, _ = fill_at_level(
            state.side, bar, opened[0].price, favourable=opened[0].favourable
        )
        state.descents = max(state.descents, depth)
        return _apply(state, opened[0], bar, price)
    if len(opened) > 1:
        return _Step.AMBIGUOUS

    finer = None if ladder is None else ladder.refine(bar)
    if finer is None:
        return _Step.AMBIGUOUS
    _, window = finer
    for inner in window:
        step = _process(inner, state, ladder, depth + 1)
        if step is not _Step.CONTINUE:
            return step
    return _Step.CONTINUE


def _weighted_exit(legs: Sequence[ExitLeg]) -> Decimal:
    """The notional-weighted average exit price. The whole reason no new type exists."""
    return sum((leg.fraction * leg.price for leg in legs), start=Decimal(0))


def _trail_to(
    state: _State, observation: "ThesisObservation | None", close: Decimal
) -> Decimal | None:
    """The nearest confirmed structural level to trail a stop to, or ``None``.

    **Only levels the structural engines had already confirmed at this bar.** The
    observation carries the execution-timeframe levels ordered against this
    instant's own close by `fmis.swing_setup.policy.ordered_levels` — production's
    ordering, called — so "nearest" here and "nearest" in a stop selection mean
    the same thing. A pivot confirmed later in the window is simply absent, which
    is what makes this trail causal rather than a hindsight line drawn through
    the highs.

    Returns ``None`` rather than a level when there is nothing to move to, when
    the nearest level would *loosen* the stop, or when the observation is
    missing. A structural trail with no confirmed structure does nothing; it
    never falls back to a price.
    """
    if observation is None:
        return None
    # A LONG is protected by levels BELOW it, a SHORT by levels above.
    levels = observation.levels_for(state.side is not TradeDirection.LONG)
    for level in levels:
        candidate = Decimal(str(level.price))
        # Strictly tightening, and strictly still a stop: a level on the wrong
        # side of this bar's close is not an invalidation any more.
        if (
            state.side.sign * (candidate - state.stop) > 0
            and state.side.sign * (close - candidate) > 0
        ):
            return candidate
    return None


def _decide_on_close(
    state: _State,
    *,
    position: int,
    close_r: Decimal,
    peak_r: Decimal,
    close: Decimal,
    observation: "ThesisObservation | None",
    entry_observation: "ThesisObservation | None",
    direction: Direction,
) -> "tuple[LabExitReason | None, Decimal | None]":
    """Evaluate one bar's close under a close-decided mechanic. **Causal.**

    Returns ``(exit_reason, new_stop)``, both optional. The caller executes an
    exit at the **next** bar's open and applies a stop change from the next bar
    onward, which is the same one-bar convention that separates a signal from
    its fill everywhere else in this package.

    Every input is a fact this bar settled: its close, the running peak through
    it, and the structural reading the production engines produced from it.
    Nothing here reads a later bar, and `test_swing_lab_persistence_exits`
    proves it by mutating every bar after the decision and requiring the
    decision not to move.
    """
    mechanic = state.policy.mechanic
    if mechanic is ExitMechanic.THESIS_FAILURE:
        # `is_adverse` is INVALIDATED or CONFLICTED and deliberately NOT
        # WEAKENED — see `ThesisState.is_adverse` for why a rule that fires on
        # weakening is a time stop wearing a structure rule's clothes.
        if thesis_state(entry_observation, observation, direction).is_adverse:
            return LabExitReason.THESIS_INVALIDATED, None
        return None, None
    if mechanic is ExitMechanic.STAGNATION:
        bars = state.policy.stagnation_bars
        progress = state.policy.stagnation_progress_r
        assert bars is not None and progress is not None  # guaranteed by ExitPolicy
        if position >= bars and peak_r < progress:
            return LabExitReason.STAGNATION, None
        return None, None
    if mechanic is ExitMechanic.GIVEBACK_FRACTION:
        arm = state.policy.giveback_arm_r
        fraction = state.policy.giveback_fraction
        assert arm is not None and fraction is not None  # guaranteed by ExitPolicy
        if peak_r < arm:
            return None, None
        if not state.armed:
            state.armed = True
        # Measured from the peak through THIS bar against THIS bar's close, so
        # the quantity is exactly BX's give-back and not a different one.
        if peak_r - close_r >= fraction * peak_r:
            return LabExitReason.GIVEBACK, None
        return None, None
    if mechanic is ExitMechanic.STRUCTURAL_TRAIL:
        return None, _trail_to(state, observation, close)
    if mechanic is ExitMechanic.THESIS_AND_GIVEBACK:
        # The two components, evaluated in declaration order on the SAME bar.
        # Neither is weakened to make room for the other: whichever fires first
        # closes the position, and the exit reason names which one it was, so a
        # combination's result can always be attributed back to a component.
        if thesis_state(entry_observation, observation, direction).is_adverse:
            return LabExitReason.THESIS_INVALIDATED, None
        arm = state.policy.giveback_arm_r
        fraction = state.policy.giveback_fraction
        assert arm is not None and fraction is not None  # guaranteed by ExitPolicy
        if peak_r >= arm:
            if not state.armed:
                state.armed = True
            if peak_r - close_r >= fraction * peak_r:
                return LabExitReason.GIVEBACK, None
        return None, None
    return None, None  # pragma: no cover - every close-decided mechanic is above


def simulate_managed_trade(
    bars: Sequence[PriceBar],
    *,
    variant_id: str,
    symbol: str,
    setup_id: str,
    direction: Direction,
    entry_index: int,
    entry_price: Decimal,
    entry_at: datetime,
    signal_at: datetime,
    reference_price: Decimal,
    stop_price: Decimal,
    target_price: Decimal,
    planned_risk_reward: float,
    window_bars: int,
    costs: PaperCostPolicy,
    policy: ExitPolicy,
    ladder: BarLadder | None = None,
    timeline: ThesisTimeline | None = None,
    segment: str | None = None,
    context_regime_structure: str = "",
    context_structural_trend: str = "",
    setup_structural_trend: str = "",
) -> ManagedResult:
    """Walk an already-entered trade under one exit mechanic.

    ``entry_index`` is the position of the bar the entry filled **on**, and
    ``entry_price`` its fill — both decided by `fmis.swing_lab.entry`, never here.
    Separating them is what lets an entry rule and an exit mechanic be measured
    independently rather than as one compound change.

    ``timeline`` (Milestone BZ) is the symbol's structural reading at every
    execution bar, keyed by the **same** bar index this function's ``bars``
    sequence uses. It is consulted only by the two mechanics that declare they
    need it (`ExitPolicy.needs_timeline`) and only at bars at or after the
    entry. Supplying it to a BY mechanic changes nothing, and withholding it
    from a BZ mechanic that needs it is refused rather than silently treated as
    "no structure" — a thesis rule that quietly never fires would be reported as
    a mechanism that did no harm.

    Deterministic and pure: no clock, no randomness, no network. The ladder and
    the timeline are both already-collected history.

    Raises:
        SwingLabError: the geometry is unusable, the ladder and the coarse bars
            disagree about a span, or a timeline-reading mechanic was given no
            timeline.
    """
    if isinstance(window_bars, bool) or not isinstance(window_bars, int) or window_bars <= 0:
        raise SwingLabError("window_bars must be a positive int")
    if not isinstance(costs, PaperCostPolicy):
        raise TypeError("costs must be a PaperCostPolicy")
    if not isinstance(policy, ExitPolicy):
        raise TypeError("policy must be an ExitPolicy")
    if direction not in _DIRECTION_TO_TRADE:
        raise SwingLabError(f"direction must be LONG or SHORT, got {direction!r}")
    if timeline is not None and not isinstance(timeline, ThesisTimeline):
        raise TypeError("timeline must be a ThesisTimeline")
    if policy.needs_timeline and timeline is None:
        raise SwingLabError(
            f"{policy.policy_id} reads the structural timeline and none was "
            "supplied; a thesis rule with no structure to read would never fire "
            "and would be reported as a mechanism that did no harm"
        )
    if timeline is not None and timeline.symbol != symbol:
        raise SwingLabError(
            f"the timeline describes {timeline.symbol} but the trade describes "
            f"{symbol}; one symbol's structure cannot manage another's position"
        )
    if entry_index < 0 or entry_index >= len(bars):
        raise SwingLabError("entry_index must address a bar in the series")
    side = _DIRECTION_TO_TRADE[direction]

    def _record(
        exit_price: Decimal | None,
        exit_at: datetime | None,
        reason: LabExitReason,
        held: int,
        gross: Decimal | None,
        net: Decimal | None,
        mfe: Decimal | None,
        mae: Decimal | None,
        state: _State | None,
        ambiguous_at: datetime | None,
    ) -> ManagedResult:
        legs = () if state is None else tuple(state.legs)
        return ManagedResult(
            trade=LabTrade(
                variant_id=variant_id, symbol=symbol, setup_id=setup_id,
                direction=direction, signal_at=signal_at, entry_at=entry_at,
                entry_price=entry_price, initial_stop=stop_price, target=target_price,
                planned_reference_price=reference_price, exit_at=exit_at,
                exit_price=exit_price, exit_reason=reason, bars_held=held,
                gross_r=gross, net_r=net, mfe_r=mfe, mae_r=mae,
                cost_policy_id=costs.policy_id,
                planned_risk_reward=planned_risk_reward, segment=segment,
                context_regime_structure=context_regime_structure,
                context_structural_trend=context_structural_trend,
                setup_structural_trend=setup_structural_trend,
                metadata={
                    "exit_policy_id": policy.policy_id,
                    "exit_mechanic": policy.mechanic.value,
                    "legs": [leg.payload() for leg in legs],
                },
            ),
            legs=legs,
            descents=0 if state is None else state.descents,
            ambiguous_bar_at=ambiguous_at,
            armed_at=None if state is None else state.armed_at,
        )

    def _unentered_record(reason: LabExitReason) -> ManagedResult:
        """A record with no position: no fill, no exit, no R. Matches `simulate_trade`."""
        return ManagedResult(
            trade=LabTrade(
                variant_id=variant_id, symbol=symbol, setup_id=setup_id,
                direction=direction, signal_at=signal_at, entry_at=None,
                entry_price=None, initial_stop=stop_price, target=target_price,
                planned_reference_price=reference_price, exit_at=None,
                exit_price=None, exit_reason=reason, bars_held=0,
                gross_r=None, net_r=None, mfe_r=None, mae_r=None,
                cost_policy_id=costs.policy_id,
                planned_risk_reward=planned_risk_reward, segment=segment,
                context_regime_structure=context_regime_structure,
                context_structural_trend=context_structural_trend,
                setup_structural_trend=setup_structural_trend,
                metadata={
                    "exit_policy_id": policy.policy_id,
                    "exit_mechanic": policy.mechanic.value,
                    "legs": [],
                },
            ),
            legs=(), descents=0, ambiguous_bar_at=None, armed_at=None,
        )

    risk = side.sign * (entry_price - stop_price)
    if risk <= 0:
        # The entry is already at or beyond the stop. Recorded as a full loss at
        # the fill, exactly as `simulate_trade` does — never skipped, because
        # skipping deletes precisely the worst fills.
        return _record(
            entry_price, entry_at, LabExitReason.ENTRY_GAPPED_THROUGH_STOP, 0,
            Decimal("-1"), Decimal("-1"), Decimal("0"), Decimal("0"), None, None,
        )
    if side.sign * (target_price - entry_price) <= 0:
        # The entry gapped past the target: there is no longer a trade to take.
        # `simulate_trade._unentered` records this with entry_at and entry_price
        # ABSENT, and so must this — a record that carries a fill while claiming
        # no position was opened makes `entry_price is not None` an unreliable
        # test for "this setup traded", which is how the unentered counts and the
        # ENTRY_NOT_TRIGGERED accounting drift apart.
        return _unentered_record(LabExitReason.NO_ENTRY_BAR)

    state = _State(
        side=side, entry=entry_price, risk=risk, stop=stop_price,
        target=target_price, policy=policy,
    )
    window = bars[entry_index : entry_index + window_bars]
    best = worst = entry_price
    previous: PriceBar | None = None
    held = 0
    ambiguous_at: datetime | None = None
    step = _Step.CONTINUE
    peak_r = Decimal(0)
    # A decision confirmed by bar t's close, executed at bar t+1's open.
    pending_exit: LabExitReason | None = None
    pending_stop: Decimal | None = None
    entry_observation = (
        None if timeline is None else timeline.at(entry_index - 1)
    )

    for position, bar in enumerate(window, start=1):
        held = position
        if pending_exit is not None:
            # The previous bar's close decided this. It fills at THIS bar's open,
            # which is the same convention `simulate_trade` uses to fill an entry
            # from a signal — never at the close that was being looked at.
            state.close(
                state.remaining, bar.open, bar.open_time, pending_exit, bar.interval
            )
            step = _Step.TERMINAL
            break
        if pending_stop is not None:
            state.tighten(pending_stop)
            pending_stop = None
        if (
            state.armed
            and policy.mechanic is ExitMechanic.TRAIL_PRIOR_BAR_EXTREME
            and previous is not None
        ):
            candidate = previous.adverse_extreme(side)
            # Only ever tighten. A prior bar whose extreme sits beyond the
            # current stop is ignored rather than obeyed.
            if side.sign * (candidate - state.stop) > 0:
                state.tighten(candidate)
        favourable = bar.favourable_extreme(side)
        adverse = bar.adverse_extreme(side)
        if side.sign * (favourable - best) > 0:
            best = favourable
        if side.sign * (adverse - worst) < 0:
            worst = adverse
        running_peak = side.sign * (best - entry_price) / risk
        if running_peak > peak_r:
            peak_r = running_peak
        step = _process(bar, state, ladder, 0)
        if step is _Step.AMBIGUOUS:
            ambiguous_at = bar.open_time
            break
        if step is _Step.TERMINAL:
            break
        if policy.mechanic.decides_on_close:
            # Evaluated from THIS bar's close and acted on at the NEXT bar's
            # open. Everything handed in is a fact this bar settled.
            was_armed = state.armed
            pending_exit, pending_stop = _decide_on_close(
                state,
                position=position,
                close_r=side.sign * (bar.close - entry_price) / risk,
                peak_r=peak_r,
                close=bar.close,
                observation=(
                    None
                    if timeline is None
                    else timeline.at(entry_index + position - 1)
                ),
                entry_observation=entry_observation,
                direction=direction,
            )
            # `armed_at` records when the mechanic ARMED, not when it exited.
            # Setting it on the exit instead would make "armed" and "armed_at"
            # describe different events, and a give-back mechanic that armed and
            # never fired would report as never having armed at all.
            if state.armed and not was_armed:
                state.armed_at = bar.open_time
        previous = bar
    else:
        step = _Step.CONTINUE

    mfe = side.sign * (best - entry_price) / risk
    mae = side.sign * (worst - entry_price) / risk

    if step is _Step.AMBIGUOUS:
        return _record(
            None, ambiguous_at, LabExitReason.AMBIGUOUS_SAME_BAR, held,
            None, None, mfe, mae, state, ambiguous_at,
        )

    if step is not _Step.TERMINAL:
        if not window:  # pragma: no cover - entry_index addresses a bar
            return _unentered_record(LabExitReason.NO_ENTRY_BAR)
        last = window[-1]
        state.close(
            state.remaining, last.close, last.open_time, LabExitReason.TIME_STOP, last.interval
        )

    legs = tuple(state.legs)
    average = _weighted_exit(legs)
    gross = side.sign * (average - entry_price)
    fees = costs.fee_rate * (entry_price + average)
    final = legs[-1]
    return _record(
        average, final.at, final.reason, held,
        gross / risk, (gross - fees) / risk, mfe, mae, state, None,
    )
