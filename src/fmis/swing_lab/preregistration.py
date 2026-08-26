"""**The frozen pre-registration. Written before a single result was read.**

This module is Milestone BY's entire claim to be a test rather than a search, and
it only works if the following is literally true:

> Every hypothesis id, every threshold, every symbol, every window boundary,
> every cost scenario, every candidate criterion and every classification rule
> below was fixed, and its SHA-256 digest recorded in `PREREGISTRATION_DIGEST`,
> **before the study was run**. `test_swing_lab_preregistration` recomputes the
> digest from the content and fails if the two disagree, so a threshold edited
> after a result was seen cannot be committed without either the failure being
> visible or the pinned digest being deliberately rewritten — and rewriting it is
> a one-line diff that any review will see.

The digest is not a checksum for corruption. It is a **tamper-evident seal on a
scientific claim**, and it works because the seal and the content live in the
same file: a change to either without the other is a red test.

**What "post-hoc" means here, operationally.** Anything not in
`PRE_REGISTERED_HYPOTHESES` is `POST_HOC_FAMILY` and
`fmis.swing_lab.validation.assess_candidate` refuses to promote it *whatever its
numbers*. Milestone BX proved by construction that this cannot be bypassed; BY
keeps the same device and adds a second: the study's own result carries the
digest, and a result whose digest does not match this module is refused at
read time by `verify_preregistration`.

**Why the primary hypothesis is the one BX found post-hoc.** BX swept fifteen
combinations after its pre-declared results were on screen and one of them —
relocate the stop to the nearest real 4H level at least 0.5 ATR away, and require
a real 1D level that pays at least 2R — was positive on both its samples and
survived costs. BX refused to call that a candidate, for the right reason: it was
constructed after the results were seen and it was a single grid point whose
neighbours failed. **BY exists to pre-declare that exact rule and try to falsify
it**, on a neighbourhood rather than a point, on data BX never measured, under
costs from the first run. The correct outcome may be NO CANDIDATE, and the
criteria below are written so that outcome is reachable.

**Read `NEIGHBOURHOOD_IS_A_CROSS_NOT_A_GRID` before reading the results.** The
stop threshold is swept at a fixed target multiple and the target multiple is
swept at a fixed stop threshold. Sweeping both together would be a 4 × 3 grid
search with twelve chances to find a winner; a cross has six and tests exactly
what §13 of the brief asks — whether each parameter sits on a plateau.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Final

from fmis.swing_lab.entry import PRE_DECLARED_ENTRY_POLICIES, EntryPolicy
from fmis.swing_lab.exits import PRE_DECLARED_EXIT_POLICIES, ExitPolicy
from fmis.swing_lab.geometry import (
    GeometryPolicy,
    StopRule,
    TargetRule,
    VolatilitySource,
)
from fmis.swing_lab.geometry_variants import PRODUCTION_GEOMETRY
# `SAMPLE_FLOOR` is IMPORTED, never restated. Restating it would let the shared
# floor move without this milestone's bar moving with it, and an architecture
# guard refuses the copy. The seal still covers the VALUE, because every
# criterion below interpolates it into its requirement text: change the floor to
# 25 and the digest changes, which is exactly the sensitivity a copy would lose.
from fmis.swing_lab.geometry_verdict import MAX_SINGLE_SYMBOL_SHARE
from fmis.swing_lab.metrics import SAMPLE_FLOOR
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.nonstructural import SyntheticGeometryPolicy, synthetic_policy
from fmis.swing_lab.trades import CONSERVATIVE_COSTS, FRICTIONLESS_COSTS
from fmis.trade_lifecycle import PaperCostPolicy

__all__ = [
    "PREREGISTRATION_ID",
    "PREREGISTRATION_DIGEST",
    "PRIMARY_STOP_ATR",
    "PRIMARY_TARGET_R",
    "STOP_ATR_NEIGHBOURHOOD",
    "TARGET_R_NEIGHBOURHOOD",
    "SLIPPAGE_SENSITIVITY_COSTS",
    "VALIDATION_COST_SCENARIOS",
    "NEIGHBOURHOOD_IS_A_CROSS_NOT_A_GRID",
    "SampleRole",
    "SampleSpec",
    "Hypothesis",
    "CriterionSpec",
    "Preregistration",
    "PRE_REGISTRATION",
    "PRE_REGISTERED_HYPOTHESES",
    "PRE_REGISTERED_POLICY_IDS",
    "DEVELOPMENT_SYMBOLS",
    "VALIDATION_SYMBOLS",
    "HOLDOUT_SYMBOLS",
    "preregistration_digest",
    "verify_preregistration",
    "is_pre_registered",
    "SAMPLES",
    "CANDIDATE_CRITERIA",
    "PLATEAU_RULES",
    "REQUIRED_DECOMPOSITIONS",
    "METRICS_REPORTED",
    "MIN_PROFIT_FACTOR",
    "DECIDING_COST_POLICY_ID",
    "PRIMARY_POLICY",
    "sample_of",
    "sample_membership",
]

PREREGISTRATION_ID: Final[str] = "by-swing-geometry-validation-v1"

# ---------------------------------------------------------------------------
# 1. The thresholds. Fixed first, because everything else refers to them.
# ---------------------------------------------------------------------------

#: The stop's volatility floor, as a multiple of the execution timeframe's Wilder
#: ATR(14). BX's hypothesis-generating point was 0.50 and it is kept — moving it
#: now would make BY a *different* hypothesis dressed as a validation of BX's.
PRIMARY_STOP_ATR: Final[float] = 0.50

#: How many times the risk a real structural target must pay. BX's point was 2.0.
PRIMARY_TARGET_R: Final[float] = 2.0

#: §2's pre-declared neighbourhood, chosen to straddle the primary point rather
#: than to extend away from it. `0.35` sits below BX's failing `0.25` neighbour
#: and `0.80` above its failing `0.75` one, so the neighbourhood deliberately
#: includes the region BX already measured as bad: a plateau that appears only
#: because its neighbours were chosen close enough to be indistinguishable is not
#: a plateau, and this grid cannot produce one.
STOP_ATR_NEIGHBOURHOOD: Final[tuple[float, ...]] = (0.35, 0.50, 0.65, 0.80)

#: The same treatment for the reward requirement.
TARGET_R_NEIGHBOURHOOD: Final[tuple[float, ...]] = (1.5, 2.0, 2.5)

NEIGHBOURHOOD_IS_A_CROSS_NOT_A_GRID: Final[str] = (
    "The stop threshold is swept at target_r = 2.0 and the target multiple is "
    "swept at stop_atr = 0.50. The two sweeps meet at the primary point and "
    "nowhere else, giving 4 + 3 - 1 = 6 policies rather than the 12 a full grid "
    "would give. This is deliberate: a 12-point grid has twelve chances to "
    "contain a winner and a cross has six, and a cross answers the only "
    "question §13 asks — whether EACH parameter sits on a plateau — while a "
    "grid additionally invites picking the best cell, which is a search."
)

#: A friction scenario above the conservative one, used as the slippage
#: sensitivity §10 asks for. **It is a proxy and is labelled as one.**
#: `PaperCostPolicy.slippage_rate` is carried and applied nowhere in this build
#: (its own docstring says so), and applying a slippage to the fill *price* would
#: also move the risk denominator, which is a different and larger change than a
#: charge on notional. So the sensitivity is expressed as a higher fee rate —
#: 15 bp per side against the conservative 10 — and the report states that this
#: understates slippage's effect on R for the tightest stops rather than
#: pretending it models a spread.
SLIPPAGE_SENSITIVITY_COSTS: Final[PaperCostPolicy] = PaperCostPolicy(
    policy_id="swing-lab-friction-15bps",
    version=1,
    fee_rate=Decimal("0.0015"),
    slippage_rate=Decimal("0"),
)

#: Every cost scenario BY reports, in presentation order. Scenario 0 exists only
#: for comparability with BW and BX; **no candidate may be selected on it.**
#:
#: Named `VALIDATION_COST_SCENARIOS` rather than `COST_SCENARIOS` because
#: `fmis.swing_lab.trades` already exports that name for a **two**-scenario tuple.
#: One name meaning two different lists is how a report ends up describing the
#: wrong cost basis, and an export-collision check caught it.
VALIDATION_COST_SCENARIOS: Final[tuple[PaperCostPolicy, ...]] = (
    FRICTIONLESS_COSTS,
    CONSERVATIVE_COSTS,
    SLIPPAGE_SENSITIVITY_COSTS,
)

#: The scenario every promotion decision is made on. Named separately from the
#: list so a report cannot quietly promote on the frictionless column.
DECIDING_COST_POLICY_ID: Final[str] = CONSERVATIVE_COSTS.policy_id


# ---------------------------------------------------------------------------
# 2. The samples.
# ---------------------------------------------------------------------------

#: Every USDT pair whose weekly history reaches the production warm-up start for
#: a measurement window opening 2023-06-01. **Probed, not chosen**: 484 currently
#: tradable USDT spot pairs were measured and exactly sixteen qualify, of which
#: TUSDUSDT is a USD-pegged stablecoin and is dropped — a trend-following swing
#: strategy measured against a peg is measuring the peg's noise, and its
#: near-zero ATR would dominate every volatility-normalised statistic here.
#:
#: The fifteen that remain are **exactly Milestone BX's universe**, which is a
#: finding rather than a coincidence: the 1W role's 250-candle analysis window
#: costs 4.8 years of history and the universe that can pay it is this one.
DEVELOPMENT_SYMBOLS: Final[tuple[str, ...]] = (
    "ADAUSDT", "BNBUSDT", "BTCUSDT", "ETCUSDT", "ETHUSDT", "ICXUSDT",
    "IOTAUSDT", "LTCUSDT", "NEOUSDT", "ONTUSDT", "QTUMUSDT", "TRXUSDT",
    "VETUSDT", "XLMUSDT", "XRPUSDT",
)

#: The same symbols over a **later, disjoint** period. BX read results on all
#: fifteen, so no symbol split among them can be out-of-sample; a date split can.
VALIDATION_SYMBOLS: Final[tuple[str, ...]] = DEVELOPMENT_SYMBOLS

#: Twenty-one pairs **this repository has never measured**, over a window their
#: shorter weekly history can support. USDCUSDT and TUSDUSDT also qualified and
#: are dropped for the reason given above; USDCUSDT would additionally have
#: carried the largest notional in the sample and dominated the concentration
#: test with a peg.
HOLDOUT_SYMBOLS: Final[tuple[str, ...]] = (
    "ALGOUSDT", "ANKRUSDT", "ATOMUSDT", "BATUSDT", "CELRUSDT", "DASHUSDT",
    "DOGEUSDT", "DUSKUSDT", "ENJUSDT", "FETUSDT", "HOTUSDT", "IOSTUSDT",
    "LINKUSDT", "ONEUSDT", "ONGUSDT", "TFUELUSDT", "THETAUSDT", "WINUSDT",
    "ZECUSDT", "ZILUSDT", "ZRXUSDT",
)


class SampleRole(str, Enum):
    """What a sample is *for*. The order is the order it may be looked at in."""

    DEVELOPMENT = "development"
    VALIDATION = "validation"
    HOLDOUT = "holdout"


@dataclass(frozen=True, slots=True)
class SampleSpec:
    """One sample: which symbols, which dates, and how contaminated it is.

    ``contamination`` is a required sentence, not an optional note. Milestone BX
    had to spend a paragraph explaining that its "holdout" was a symbol split
    whose symbols were less liquid; carrying that statement *inside* the sample
    means every table printing the sample can print the caveat with it.
    """

    name: str
    role: SampleRole
    symbols: tuple[str, ...]
    signal_start: datetime
    signal_end: datetime
    contamination: str

    def __post_init__(self) -> None:
        if not self.symbols:
            raise SwingLabError(f"sample {self.name} has no symbols")
        if self.signal_end <= self.signal_start:
            raise SwingLabError(f"sample {self.name} ends before it starts")
        for name in ("name", "contamination"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SwingLabError(f"{name} must be a non-empty str")

    @property
    def years(self) -> float:
        return (self.signal_end - self.signal_start).days / 365.25

    def holds(self, symbol: str, signal_at: datetime) -> bool:
        """Whether one captured candidate belongs to this sample. **The only rule.**

        Both conditions, always: a symbol split alone would put the same market
        period in two samples, and a date split alone would put the same symbol
        in two. The study asserts the three samples are pairwise disjoint by
        running this predicate over every candidate rather than by reasoning
        about the boundaries.
        """
        return (
            symbol in self.symbols
            and self.signal_start <= signal_at < self.signal_end
        )

    def payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role.value,
            "symbols": list(self.symbols),
            "signal_start": self.signal_start.isoformat(),
            "signal_end": self.signal_end.isoformat(),
            "contamination": self.contamination,
        }


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


SAMPLES: Final[tuple[SampleSpec, ...]] = (
    SampleSpec(
        name="development",
        role=SampleRole.DEVELOPMENT,
        symbols=DEVELOPMENT_SYMBOLS,
        signal_start=_utc("2023-06-01T00:00:00"),
        signal_end=_utc("2025-06-01T00:00:00"),
        contamination=(
            "CONTAMINATED BY CONSTRUCTION. Milestone BX measured every one of "
            "these fifteen symbols over a window containing this one, and BY's "
            "primary hypothesis was written after reading BX's diagnosis of "
            "them. Nothing measured here is out-of-sample in any strict sense, "
            "and a positive figure here is a necessary condition for a "
            "candidate rather than evidence for one."
        ),
    ),
    SampleSpec(
        name="validation",
        role=SampleRole.VALIDATION,
        symbols=VALIDATION_SYMBOLS,
        signal_start=_utc("2025-06-01T00:00:00"),
        signal_end=_utc("2026-08-01T00:00:00"),
        contamination=(
            "SEMI-CONTAMINATED. The same fifteen symbols as development, over a "
            "strictly later and disjoint period that BX's window also covered. "
            "The symbols are not new, the market period is; so this tests "
            "whether the rule is one regime rather than whether it is one "
            "universe. It is temporal validation, and it is labelled as that "
            "rather than as a holdout."
        ),
    ),
    SampleSpec(
        name="holdout",
        role=SampleRole.HOLDOUT,
        symbols=HOLDOUT_SYMBOLS,
        signal_start=_utc("2024-06-01T00:00:00"),
        signal_end=_utc("2026-08-01T00:00:00"),
        contamination=(
            "THE HOLDOUT. Twenty-one symbols no milestone of this repository "
            "has ever measured, captured in a SEPARATE replay run after the "
            "development and validation results existed and after this "
            "pre-registration was sealed. Its window opens later than "
            "development's because these symbols' weekly history cannot reach "
            "the production warm-up start any earlier — a constraint of the "
            "data, recorded rather than worked around. These symbols are "
            "materially less liquid than the development set (median 24h quote "
            "volume ~0.7M USDT against ~18.8M), so this tests whether a rule "
            "generalises across STRUCTURE, not whether it would have been "
            "executable at size."
        ),
    ),
)


# ---------------------------------------------------------------------------
# 3. The hypotheses.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """One pre-registered rule, its prediction, and what would refute it.

    ``refuted_by`` is required and is the field that makes this a hypothesis
    rather than a variant. A rule with no stated refutation cannot fail, and a
    milestone whose rules cannot fail is a search.
    """

    hypothesis_id: str
    role: str
    policy: GeometryPolicy | SyntheticGeometryPolicy
    prediction: str
    refuted_by: str

    def __post_init__(self) -> None:
        for name in ("hypothesis_id", "role", "prediction", "refuted_by"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise SwingLabError(f"{name} must be a non-empty str")

    @property
    def policy_id(self) -> str:
        return self.policy.policy_id

    @property
    def is_structural(self) -> bool:
        return not isinstance(self.policy, SyntheticGeometryPolicy)

    def payload(self) -> dict[str, Any]:
        policy = self.policy
        rules: dict[str, Any] = (
            {
                "kind": "non_structural",
                "stop_atr": policy.stop_atr,
                "target_r": policy.target_r,
                "volatility_source": policy.volatility_source.value,
            }
            if isinstance(policy, SyntheticGeometryPolicy)
            else {
                "kind": "structural",
                "stop_rule": policy.stop_rule.value,
                "target_rule": policy.target_rule.value,
                "min_stop_atr": policy.min_stop_atr,
                "min_planned_rr": policy.min_planned_rr,
                "volatility_source": policy.volatility_source.value,
            }
        )
        return {
            "hypothesis_id": self.hypothesis_id,
            "role": self.role,
            "policy_id": policy.policy_id,
            "family": policy.family,
            "title": policy.title,
            "hypothesis": policy.hypothesis,
            "prediction": self.prediction,
            "refuted_by": self.refuted_by,
            "is_structural": self.is_structural,
            "rules": rules,
        }


FAMILY_PRIMARY: Final[str] = "P_volatility_aware_structural"
FAMILY_ISOLATION: Final[str] = "I_isolation_control"


def _primary(stop_atr: float, target_r: float, *, family: str = FAMILY_PRIMARY) -> GeometryPolicy:
    """The primary rule at one (stop_atr, target_r) point. **Both halves, always.**"""
    return GeometryPolicy(
        policy_id=f"by_stop_{_slug(stop_atr)}atr_target_{_slug(target_r)}r",
        title=(
            f"Structural stop ≥ {stop_atr:g}× ATR(14), structural target paying "
            f"≥ {target_r:g}R"
        ),
        family=family,
        hypothesis=(
            f"The stop is the nearest REAL execution-timeframe (4H) protective "
            f"level at least {stop_atr:g}× the execution ATR(14) from the "
            f"entry — not a widened stop, a different structural level, and no "
            f"trade at all when none qualifies. The target is the nearest REAL "
            f"setup-timeframe (1D) objective level whose reward reaches "
            f"{target_r:g}× that risk — not a computed R multiple, and no trade "
            "when no real level pays it. BX found the two halves individually "
            "useless and jointly effective; this asks whether that survives on "
            "unseen data, under costs, across a neighbourhood."
        ),
        stop_rule=StopRule.EXECUTION_BEYOND_VOLATILITY,
        target_rule=TargetRule.FIRST_SETUP_SUPPORTING_RR,
        min_stop_atr=stop_atr,
        min_planned_rr=target_r,
        volatility_source=VolatilitySource.EXECUTION_ATR,
    )


def _slug(value: float) -> str:
    return f"{value:g}".replace(".", "_").replace("-", "neg")


PRIMARY_POLICY: Final[GeometryPolicy] = _primary(PRIMARY_STOP_ATR, PRIMARY_TARGET_R)

#: The neighbourhood, as a cross. Ordered stop-sweep first, then target-sweep,
#: with the shared primary point appearing once.
_STOP_SWEEP: Final[tuple[GeometryPolicy, ...]] = tuple(
    _primary(value, PRIMARY_TARGET_R) for value in STOP_ATR_NEIGHBOURHOOD
)
_TARGET_SWEEP: Final[tuple[GeometryPolicy, ...]] = tuple(
    _primary(PRIMARY_STOP_ATR, value)
    for value in TARGET_R_NEIGHBOURHOOD
    if value != PRIMARY_TARGET_R
)

_ISOLATION_STOP_ONLY: Final[GeometryPolicy] = GeometryPolicy(
    policy_id="by_stop_only_0_5atr",
    title="Volatility-aware structural stop ALONE, production target",
    family=FAMILY_ISOLATION,
    hypothesis=(
        "One half of the primary rule. The stop is relocated to the nearest 4H "
        "level at least 0.5× ATR(14) away and the target is left as "
        "production's nearest 1D level. BX measured this as reliably negative "
        "at every threshold, and it is pre-declared here so that result is "
        "confirmed rather than remembered: if the primary rule works and this "
        "does not, the target half is load-bearing."
    ),
    stop_rule=StopRule.EXECUTION_BEYOND_VOLATILITY,
    target_rule=TargetRule.NEAREST_SETUP,
    min_stop_atr=PRIMARY_STOP_ATR,
)

_ISOLATION_TARGET_ONLY: Final[GeometryPolicy] = GeometryPolicy(
    policy_id="by_target_only_2r",
    title="Compensating structural target ALONE, production stop",
    family=FAMILY_ISOLATION,
    hypothesis=(
        "The other half. The stop is production's nearest 4H level — which BX "
        "measured at a median 0.22 ATR for high-planned-R:R setups — and the "
        "target is the nearest real 1D level paying 2× that risk. If this "
        "works alone, the stop half is decoration and the primary rule is "
        "over-specified."
    ),
    stop_rule=StopRule.NEAREST_EXECUTION,
    target_rule=TargetRule.FIRST_SETUP_SUPPORTING_RR,
    min_planned_rr=PRIMARY_TARGET_R,
)

_SETUP_TIMEFRAME_STOP: Final[GeometryPolicy] = GeometryPolicy(
    policy_id="by_setup_stop_0_5atr_target_2r",
    title="Setup-timeframe (1D) structural stop beyond the floor, 2R target",
    family=FAMILY_ISOLATION,
    hypothesis=(
        "The primary rule with the invalidation read on the SETUP timeframe "
        "instead. BX's geom_setup_stop moved the stop to the nearest 1D level "
        "and failed; it never asked what happens when that level must ALSO "
        "clear the noise floor and the target must pay the resulting, larger "
        "risk. If the thesis is formed on 1D, its invalidation arguably lives "
        "there, and this is the only variant that tests that claim honestly."
    ),
    stop_rule=StopRule.SETUP_BEYOND_VOLATILITY,
    target_rule=TargetRule.FIRST_SETUP_SUPPORTING_RR,
    min_stop_atr=PRIMARY_STOP_ATR,
    min_planned_rr=PRIMARY_TARGET_R,
    volatility_source=VolatilitySource.EXECUTION_ATR,
)

_NON_STRUCTURAL_TWIN: Final[SyntheticGeometryPolicy] = synthetic_policy(
    PRIMARY_STOP_ATR, PRIMARY_TARGET_R
)


def _hypothesis(
    hid: str, policy: Any, role: str, prediction: str, refuted_by: str
) -> Hypothesis:
    return Hypothesis(
        hypothesis_id=hid, role=role, policy=policy,
        prediction=prediction, refuted_by=refuted_by,
    )


PRE_REGISTERED_HYPOTHESES: Final[tuple[Hypothesis, ...]] = (
    _hypothesis(
        "BY-H0", PRODUCTION_GEOMETRY, "control",
        "Negative cost-inclusive expectancy on development, as BW and BX both "
        "measured. It exists to prove the harness reproduces the known result; "
        "if it comes back positive, the harness is wrong and nothing else here "
        "may be read.",
        "A positive development expectancy would refute the harness, not the "
        "production strategy.",
    ),
    *(
        _hypothesis(
            f"BY-H1.{index}", policy, "primary",
            "Positive cost-inclusive expectancy on development AND non-negative "
            "on validation AND non-negative on the holdout.",
            "A non-positive development expectancy under the deciding cost "
            "scenario, or a negative figure on either unseen sample, or fewer "
            "than 20 measurable trades on any sample.",
        )
        for index, policy in enumerate(_STOP_SWEEP + _TARGET_SWEEP, start=1)
    ),
    _hypothesis(
        "BY-H2", _ISOLATION_STOP_ONLY, "isolation",
        "Negative on development — BX measured the stop relocation alone as "
        "reliably negative at every threshold.",
        "A positive result would mean the target half of the primary rule is "
        "unnecessary and the primary rule is over-specified.",
    ),
    _hypothesis(
        "BY-H3", _ISOLATION_TARGET_ONLY, "isolation",
        "Negative on development — a 2R objective bought with a stop at a fifth "
        "of a bar's range is BX's anti-filter in structural clothing.",
        "A positive result would mean the volatility floor is decoration.",
    ),
    _hypothesis(
        "BY-H4", _SETUP_TIMEFRAME_STOP, "alternative",
        "Direction not predicted. This is a genuine open question — BX rejected "
        "the 1D stop without a noise floor and never tested it with one.",
        "It is judged by the same criteria as the primary family and is not "
        "privileged by being uncertain.",
    ),
    _hypothesis(
        "BY-H5", _NON_STRUCTURAL_TWIN, "non_structural_control",
        "If the structural claim is real, this distance-only twin should be "
        "MATERIALLY WORSE than the primary rule at the same numbers.",
        "If it matches or beats the primary rule, the structural claim is "
        "unsupported: the finding is about distance, not about market "
        "structure, and the milestone must say so. This control can never be "
        "promoted, whatever it earns.",
    ),
)

PRE_REGISTERED_POLICY_IDS: Final[frozenset[str]] = frozenset(
    item.policy_id for item in PRE_REGISTERED_HYPOTHESES
)

if len(PRE_REGISTERED_POLICY_IDS) != len(PRE_REGISTERED_HYPOTHESES):  # pragma: no cover
    raise SwingLabError("two pre-registered hypotheses share a policy_id")


def is_pre_registered(policy_id: str) -> bool:
    """Whether this policy was sealed before results existed. **The promotion gate.**"""
    return policy_id in PRE_REGISTERED_POLICY_IDS


# ---------------------------------------------------------------------------
# 4. The bar. Written before any result, so it cannot be argued down after one.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CriterionSpec:
    """One candidate requirement, as a sentence and a number, fixed in advance."""

    name: str
    requirement: str
    threshold: float | None

    def __post_init__(self) -> None:
        for field_name in ("name", "requirement"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise SwingLabError(f"{field_name} must be a non-empty str")

    def payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "requirement": self.requirement,
            "threshold": self.threshold,
        }


#: The profit factor a candidate must clear under the deciding cost scenario.
MIN_PROFIT_FACTOR: Final[float] = 1.0

CANDIDATE_CRITERIA: Final[tuple[CriterionSpec, ...]] = (
    CriterionSpec(
        "pre_registered",
        "the policy appears in PRE_REGISTERED_HYPOTHESES and the study's "
        "manifest carries this pre-registration's digest",
        None,
    ),
    CriterionSpec(
        "structural",
        "the policy selects real structural levels; the non-structural control "
        "is measured and reported but can never be promoted",
        None,
    ),
    CriterionSpec(
        "development_sample",
        f"at least {SAMPLE_FLOOR} measurable trades on development",
        SAMPLE_FLOOR,
    ),
    CriterionSpec(
        "validation_sample", f"at least {SAMPLE_FLOOR} measurable trades on validation",
        SAMPLE_FLOOR,
    ),
    CriterionSpec(
        "holdout_sample", f"at least {SAMPLE_FLOOR} measurable trades on the holdout",
        SAMPLE_FLOOR,
    ),
    CriterionSpec(
        "development_expectancy",
        "a POSITIVE cost-inclusive expectancy on development under the deciding "
        "cost scenario; the frictionless column may never promote anything",
        0.0,
    ),
    CriterionSpec(
        "validation_expectancy",
        "a NON-NEGATIVE cost-inclusive expectancy on validation. Phrased as a "
        "number rather than as 'non-catastrophic', because any word needs a "
        "number eventually and a number chosen after the result is one a "
        "researcher can argue down",
        0.0,
    ),
    CriterionSpec(
        "holdout_expectancy",
        "a NON-NEGATIVE cost-inclusive expectancy on the holdout",
        0.0,
    ),
    CriterionSpec(
        "profit_factor",
        f"a cost-inclusive profit factor above {MIN_PROFIT_FACTOR:g} on development",
        MIN_PROFIT_FACTOR,
    ),
    CriterionSpec(
        "drawdown_recovered",
        "the worst peak-to-trough decline on development is smaller than the "
        "total R the variant gained; a drawdown larger than the gain is not a "
        "manageable drawdown whatever the expectancy says",
        None,
    ),
    CriterionSpec(
        "symbol_concentration",
        f"no single symbol contributes more than {MAX_SINGLE_SYMBOL_SHARE:.0%} "
        "of gross absolute R on development",
        float(MAX_SINGLE_SYMBOL_SHARE),
    ),
    CriterionSpec(
        "parameter_plateau",
        "the policy's pre-declared neighbourhood classifies as ROBUST_PLATEAU "
        "under PLATEAU_RULES; a FRAGILE_SPIKE is rejected however good its "
        "centre looks",
        None,
    ),
    CriterionSpec(
        "no_lookahead",
        "the milestone's future-mutation suite passed for this study's capture: "
        "every candidate and every plan is byte-identical when all bars after "
        "the decision are replaced",
        None,
    ),
)

#: §13's classification, stated as rules **before** anything is classified.
PLATEAU_RULES: Final[tuple[str, ...]] = (
    "NOT_MEASURABLE — fewer than 3 points in the pre-declared neighbourhood "
    f"cleared the {SAMPLE_FLOOR}-trade floor. The test could not be run, which "
    "is not a pass.",
    "NO_EDGE — the primary point's cost-inclusive development expectancy is "
    "not positive. Neighbours are reported but decide nothing: there is no "
    "spike to be fragile about.",
    "FRAGILE_SPIKE — the primary point is positive and at least one measurable "
    "neighbour is not. This is BX's §10 result and it is REJECTED.",
    "ROBUST_PLATEAU — the primary point is positive and EVERY measurable "
    "neighbour is positive too. `all`, never `any`.",
)

#: What a study must decompose before a candidate is proposed. Reported whatever
#: the verdict, because a rejected rule's decomposition is how the next
#: milestone learns something.
REQUIRED_DECOMPOSITIONS: Final[tuple[str, ...]] = (
    "per symbol — with expectancy REFUSED for any cohort below the sample floor",
    "long against short — a rule that works in one direction only is a market "
    "call wearing a strategy's clothes",
    "symbol class — majors against the lower-liquidity remainder of the "
    "development universe",
    "context regime and setup structural trend",
    "chronological walk-forward across the whole span, with the frozen policy "
    "and NO re-optimisation inside any window",
)

METRICS_REPORTED: Final[tuple[str, ...]] = (
    "measurable trades, skipped candidates by named reason, ambiguous trades",
    "expectancy in R, median R, win rate, profit factor, total R",
    "average winner, average loser, maximum peak-to-trough drawdown in R",
    "planned R:R, stop distance in bp and in ATR, target distance in bp and in ATR",
    "MFE, MAE, and the share of trades giving back a full R of open profit",
    "largest single-symbol share of gross absolute R",
)


# ---------------------------------------------------------------------------
# 5. The seal.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Preregistration:
    """Everything that was fixed in advance, in one addressable object."""

    preregistration_id: str
    hypotheses: tuple[Hypothesis, ...]
    entry_policies: tuple[EntryPolicy, ...]
    exit_policies: tuple[ExitPolicy, ...]
    timeframe_variant_ids: tuple[str, ...]
    samples: tuple[SampleSpec, ...]
    cost_scenarios: tuple[PaperCostPolicy, ...]
    deciding_cost_policy_id: str
    candidate_criteria: tuple[CriterionSpec, ...]
    plateau_rules: tuple[str, ...]
    decompositions: tuple[str, ...]
    metrics: tuple[str, ...]
    stop_atr_neighbourhood: tuple[float, ...]
    target_r_neighbourhood: tuple[float, ...]
    neighbourhood_note: str

    def payload(self) -> dict[str, Any]:
        """The canonical content the digest is taken over. **Order is fixed.**

        Every collection is emitted in declaration order rather than sorted:
        the order hypotheses were written in is itself part of what was frozen,
        and re-ordering them is a change a reader should be able to see.
        """
        return {
            "preregistration_id": self.preregistration_id,
            "hypotheses": [item.payload() for item in self.hypotheses],
            "entry_policies": [item.payload() for item in self.entry_policies],
            "exit_policies": [item.payload() for item in self.exit_policies],
            "timeframe_variant_ids": list(self.timeframe_variant_ids),
            "samples": [item.payload() for item in self.samples],
            "cost_scenarios": [dict(item.to_payload()) for item in self.cost_scenarios],
            "deciding_cost_policy_id": self.deciding_cost_policy_id,
            "candidate_criteria": [item.payload() for item in self.candidate_criteria],
            "plateau_rules": list(self.plateau_rules),
            "decompositions": list(self.decompositions),
            "metrics": list(self.metrics),
            "stop_atr_neighbourhood": list(self.stop_atr_neighbourhood),
            "target_r_neighbourhood": list(self.target_r_neighbourhood),
            "neighbourhood_note": self.neighbourhood_note,
        }

    def sample(self, name: str) -> SampleSpec:
        for item in self.samples:
            if item.name == name:
                return item
        raise SwingLabError(
            f"no pre-registered sample {name!r}; this study declares "
            f"{', '.join(item.name for item in self.samples)}"
        )

    def hypothesis_for(self, policy_id: str) -> Hypothesis:
        for item in self.hypotheses:
            if item.policy_id == policy_id:
                return item
        raise SwingLabError(
            f"{policy_id!r} is NOT pre-registered; this pre-registration seals "
            f"{', '.join(sorted(PRE_REGISTERED_POLICY_IDS))}"
        )


PRE_REGISTRATION: Final[Preregistration] = Preregistration(
    preregistration_id=PREREGISTRATION_ID,
    hypotheses=PRE_REGISTERED_HYPOTHESES,
    entry_policies=PRE_DECLARED_ENTRY_POLICIES,
    exit_policies=PRE_DECLARED_EXIT_POLICIES,
    timeframe_variant_ids=("swing_current", "swing_1d4h1h_roles"),
    samples=SAMPLES,
    cost_scenarios=VALIDATION_COST_SCENARIOS,
    deciding_cost_policy_id=DECIDING_COST_POLICY_ID,
    candidate_criteria=CANDIDATE_CRITERIA,
    plateau_rules=PLATEAU_RULES,
    decompositions=REQUIRED_DECOMPOSITIONS,
    metrics=METRICS_REPORTED,
    stop_atr_neighbourhood=STOP_ATR_NEIGHBOURHOOD,
    target_r_neighbourhood=TARGET_R_NEIGHBOURHOOD,
    neighbourhood_note=NEIGHBOURHOOD_IS_A_CROSS_NOT_A_GRID,
)


def preregistration_digest(preregistration: Preregistration = PRE_REGISTRATION) -> str:
    """SHA-256 over the canonical content. **The seal.**

    `sort_keys` is on so a dict literal reordered by an editor does not change
    the digest, while every *sequence* stays in declaration order because the
    order of the hypotheses is part of what was frozen. `ensure_ascii` is off and
    the encoding is explicit, so a hypothesis containing "≥" digests the same on
    every platform.
    """
    if not isinstance(preregistration, Preregistration):
        raise TypeError("preregistration must be a Preregistration")
    canonical = json.dumps(
        preregistration.payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


#: **The seal, pinned.** Recomputed and compared by
#: `tests/test_swing_lab_preregistration.py`. If you are reading a diff that
#: changes this line, the pre-registration changed with it and every result
#: measured under the old digest describes a different experiment.
PREREGISTRATION_DIGEST: Final[str] = (
    "a81b6ab8314bd3cf2e8a6358f3a19cf8d6bb6c152cef9efd55fbffd9883d640a"
)


def verify_preregistration(digest: str) -> bool:
    """Whether a recorded digest is the one this module currently seals.

    A study artifact carries the digest that was live when it ran; comparing it
    here is what stops a result being read under a pre-registration it was not
    measured against.
    """
    if not isinstance(digest, str):
        raise TypeError("digest must be a str")
    return digest == preregistration_digest()


def sample_of(
    symbol: str, signal_at: datetime, samples: Sequence[SampleSpec] = SAMPLES
) -> SampleSpec | None:
    """Which sample one captured candidate belongs to, or ``None`` for neither.

    Raises:
        SwingLabError: the candidate belongs to two samples. The three specs are
            meant to be disjoint and a silent double-count would inflate one
            sample with the other's trades.
    """
    matches = [spec for spec in samples if spec.holds(symbol, signal_at)]
    if len(matches) > 1:
        raise SwingLabError(
            f"{symbol} at {signal_at.isoformat()} falls in "
            f"{', '.join(spec.name for spec in matches)}; the pre-registered "
            "samples must be pairwise disjoint"
        )
    return matches[0] if matches else None


def sample_membership(
    candidates: Sequence[tuple[str, datetime]],
    samples: Sequence[SampleSpec] = SAMPLES,
) -> Mapping[str, int]:
    """How many candidates each sample claims, plus the unclaimed count.

    Reported rather than assumed: a window boundary that silently claims nothing
    is a study measuring a sample that does not exist, and the count is the only
    thing that catches it.
    """
    tally = {spec.name: 0 for spec in samples}
    tally["unclaimed"] = 0
    for symbol, signal_at in candidates:
        spec = sample_of(symbol, signal_at, samples)
        tally[spec.name if spec is not None else "unclaimed"] += 1
    return tally
