"""The pre-specified variants. **Written before any history was replayed.**

This module is the milestone's anti-overfitting device, and it only works if it
is read as one: the five variants below were fixed, with their ids and their
stated hypotheses, before a single number came back. A variant added after a
result has been seen is a *new experiment* and belongs in a later milestone
under its own id — never as a quiet edit here.

**Why these five and no more.** The brief asks specifically not to invent extra
variants in search of a winner. Each one below answers a question the owner
actually asked:

* `swing_current` — what does the product do today?
* `swing_1w_hard_gate` — is the override mechanism faithful? It must reproduce
  `swing_current` exactly, and if it does not, every other comparison here is
  worthless. This is a **control**, not a candidate.
* `swing_1w_context` — the owner's own hypothesis: 1W informs, but cannot kill.
* `swing_1d4h_core` — 1D and 4H decide alone; 1W neither gates nor votes.
* `swing_1d4h1h_roles` — the unmodified production policy with 1D/4H/1H in the
  three roles: 4H forms the setup, 1H times the entry.

**What is deliberately absent.** No variant tunes a threshold, a lookback, a
band, `MINIMUM_AGREEING_FAMILIES`, or a detection setting. The brief forbids
threshold mining and the repository forbids threshold shopping; a policy that
wins only at one hand-picked number is not a finding.
"""

from __future__ import annotations

from typing import Final

from fmis.pipeline.multi_timeframe import DEFAULT_TIMEFRAMES, TimeframeRole
from fmis.swing_lab.models import LabVariant, SwingLabError
from fmis.swing_setup.policy import CONFIRMATION_LOOKBACK_BARS, ContextRoleTreatment

__all__ = [
    "PRODUCTION_INTERVALS",
    "SHIFTED_INTERVALS",
    "BASELINE_VARIANT",
    "HARD_GATE_CONTROL_VARIANT",
    "CONTEXT_ONLY_VARIANT",
    "CORE_1D4H_VARIANT",
    "SHIFTED_ROLE_VARIANT",
    "PRE_SPECIFIED_VARIANTS",
    "variant_by_id",
]

#: What the live product maps today, read from the production constant rather
#: than retyped — a copy would silently stop tracking a change to the original.
PRODUCTION_INTERVALS: Final[dict[TimeframeRole, str]] = dict(DEFAULT_TIMEFRAMES)

#: The owner's stated alternative: the whole analysis shifted one step down, so
#: 1D carries context, 4H forms the setup and 1H times the entry.
SHIFTED_INTERVALS: Final[dict[TimeframeRole, str]] = {
    TimeframeRole.CONTEXT: "1d",
    TimeframeRole.SETUP: "4h",
    TimeframeRole.EXECUTION: "1h",
}


BASELINE_VARIANT: Final[LabVariant] = LabVariant(
    variant_id="swing_current",
    title="Current production policy",
    hypothesis=(
        "The baseline. Neither research override is supplied, so this is the "
        "live product's own code path with its own constants, and its "
        "assessments carry the production policy_id. Every other variant is "
        "measured as a difference from this one."
    ),
    context_role=None,
    max_confirmation_age=None,
    timeframes=PRODUCTION_INTERVALS,
)

HARD_GATE_CONTROL_VARIANT: Final[LabVariant] = LabVariant(
    variant_id="swing_1w_hard_gate",
    title="1W hard gate, stated explicitly (control)",
    hypothesis=(
        "A CONTROL, not a candidate. It reproduces the production semantics "
        "through the research override machinery: the context role both gates "
        "and votes, at the production staleness bound. It must therefore agree "
        "with swing_current on every observation and every trade. Any "
        "disagreement means the override mechanism is unfaithful and "
        "invalidates every counterfactual in this study, so it is measured "
        "rather than assumed."
    ),
    context_role=ContextRoleTreatment.GATE_AND_VOTE,
    max_confirmation_age=CONFIRMATION_LOOKBACK_BARS,
    timeframes=PRODUCTION_INTERVALS,
)

CONTEXT_ONLY_VARIANT: Final[LabVariant] = LabVariant(
    variant_id="swing_1w_context",
    title="1W as context only",
    hypothesis=(
        "The owner's hypothesis. The weekly regime no longer refuses a thesis "
        "outright; the weekly structural trend still votes as one of three "
        "families. If the gate is merely restrictive, this should produce more "
        "trades at similar expectancy. If the gate is load-bearing, "
        "expectancy and drawdown should deteriorate."
    ),
    context_role=ContextRoleTreatment.VOTE_ONLY,
    max_confirmation_age=None,
    timeframes=PRODUCTION_INTERVALS,
)

CORE_1D4H_VARIANT: Final[LabVariant] = LabVariant(
    variant_id="swing_1d4h_core",
    title="1D and 4H core, 1W excluded entirely",
    hypothesis=(
        "The weekly role neither gates nor votes. Note the consequence, which "
        "is stated rather than compensated for: MINIMUM_AGREEING_FAMILIES is "
        "unchanged at 2, so with only two families left BOTH must agree with "
        "neither opposing. This is a stricter unanimity requirement than the "
        "baseline's two-of-three, and both surviving families are computed "
        "from the same 1D candles — so this variant is also a direct test of "
        "whether those two families are independent."
    ),
    context_role=ContextRoleTreatment.IGNORED,
    max_confirmation_age=None,
    timeframes=PRODUCTION_INTERVALS,
)

SHIFTED_ROLE_VARIANT: Final[LabVariant] = LabVariant(
    variant_id="swing_1d4h1h_roles",
    title="1D context, 4H setup, 1H execution",
    hypothesis=(
        "The UNMODIFIED production policy, applied to a different role→interval "
        "mapping: 1D describes context, 4H forms the setup, 1H times the "
        "entry. No override is supplied, so the policy_id is production's own "
        "— what changes is which candles play which part. This isolates 'the "
        "weekly timeframe is the wrong context' from 'a hard context gate is "
        "wrong', which the other variants cannot separate."
    ),
    context_role=None,
    max_confirmation_age=None,
    timeframes=SHIFTED_INTERVALS,
)


#: The full pre-specified set, in the order results should be presented.
PRE_SPECIFIED_VARIANTS: Final[tuple[LabVariant, ...]] = (
    BASELINE_VARIANT,
    HARD_GATE_CONTROL_VARIANT,
    CONTEXT_ONLY_VARIANT,
    CORE_1D4H_VARIANT,
    SHIFTED_ROLE_VARIANT,
)

_BY_ID: Final[dict[str, LabVariant]] = {
    variant.variant_id: variant for variant in PRE_SPECIFIED_VARIANTS
}

if len(_BY_ID) != len(PRE_SPECIFIED_VARIANTS):  # pragma: no cover - import-time guard
    raise SwingLabError("two pre-specified variants share a variant_id")


def variant_by_id(variant_id: str) -> LabVariant:
    """Look one variant up by id.

    Raises:
        SwingLabError: no pre-specified variant carries that id. Names the
            available ids rather than only the missing one, because a caller
            who mistyped needs to see the alternatives.
    """
    try:
        return _BY_ID[variant_id]
    except KeyError:
        raise SwingLabError(
            f"no pre-specified variant {variant_id!r}; the study defines "
            f"{', '.join(sorted(_BY_ID))}"
        ) from None
