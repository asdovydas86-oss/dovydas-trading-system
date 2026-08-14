"""The measured figures this package cites, and nothing else.

**Every number in `fmis.today` lives here, and every one of them is a
measurement this repository already published — never a threshold this
milestone chose.** The distinction is the whole reason this module exists
separately: a constant sitting in a warning rule reads as a policy decision, and
a reader has no way to tell an invented cut-off from a recorded observation
unless the two are kept apart and the second carries its source.

A guard test asserts that no other module in this package contains a numeric
literal beyond `0` and `1` — the same discipline `fmis.decision_context`'s
evaluator already holds, applied here for the same reason.

**Each figure carries its own caveat, and the caveat is printed, not merely
stored.** `SWING_TRADING_MVP_BLUEPRINT_V1.md` §7.6 is explicit about this:

    Every soft warning drawn from that chain must therefore be rendered with its
    `n` and a note that the sample is superseded — or the warning becomes the
    thing it exists to prevent: a confident number the owner acts on.

So `MeasuredFigure` has no field a renderer may skip. There is no short form.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "MeasuredFigure",
    "RISK_REWARD_P90",
    "RISK_REWARD_ELEVATED",
    "RISK_REWARD_DISTRIBUTION",
    "RISK_REWARD_ASSOCIATION",
    "MEASURED_FIGURES",
]


@dataclass(frozen=True, slots=True)
class MeasuredFigure:
    """One published observation, with everything needed to print it honestly.

    ``sample`` is the `n` behind it; ``source`` names the artifact that
    published it; ``caveat`` states what is wrong with the sample. A figure
    whose caveat is empty would be a figure claiming there is nothing to know
    about how it was obtained, and every figure this package cites has
    something.
    """

    label: str
    statement: str
    sample: int
    source: str
    caveat: str

    def __post_init__(self) -> None:
        for name in ("label", "statement", "source", "caveat"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty str")
        if not isinstance(self.sample, int) or isinstance(self.sample, bool):
            raise TypeError("sample must be an int")
        if self.sample < 1:
            raise ValueError(
                "a measured figure needs at least one observation behind it; a "
                "figure with no sample is an assertion wearing a measurement's "
                "clothes"
            )

    def rendered(self) -> tuple[str, ...]:
        """The full form — statement, sample and caveat. There is no short form."""
        return (self.statement, f"n = {self.sample} · {self.source}", self.caveat)


#: The 90th percentile of risk/reward at confirmation, from the corrected
#: research harness. A displayed R:R above this is outside the range this
#: repository has ever measured its own policy producing.
RISK_REWARD_P90 = 10.70

#: The lower edge of the `[5, 20)` bucket in `AX` §3.7 — the bucket whose
#: resolved win rate is the lowest of the five measured.
RISK_REWARD_ELEVATED = 5.0

_SUPERSEDED_SAMPLE = (
    "Sample superseded: BB proved the window was 41-43 usable days inside a "
    "period described as 400, and BC proved the setup identity changed every "
    "bar. Read as a direction of association, never as a probability."
)

RISK_REWARD_DISTRIBUTION = MeasuredFigure(
    label="risk_reward_distribution",
    statement=(
        "Measured R:R at confirmation: p50 0.98 · p75 2.59 · p90 10.70 · "
        "max 25.90."
    ),
    sample=44,
    source="report 0012 section 9 (corrected research harness)",
    caveat=(
        "A distribution of what the policy displayed, not of what it earned. "
        "The tail is pathological and is reported rather than trimmed."
    ),
)

RISK_REWARD_ASSOCIATION = MeasuredFigure(
    label="risk_reward_association",
    statement=(
        "Higher displayed R:R was measured with a worse outcome, not a better "
        "one: R:R in [5, 20) resolved target-first 7.7% of the time, against "
        "74.5% for R:R in [0, 1)."
    ),
    sample=146,
    source="EVIDENCE_CALIBRATION_RESEARCH_V1.md section 3.7 (AX)",
    caveat=_SUPERSEDED_SAMPLE,
)

#: Every figure, so a test can assert each one is reachable and complete.
MEASURED_FIGURES: tuple[MeasuredFigure, ...] = (
    RISK_REWARD_DISTRIBUTION,
    RISK_REWARD_ASSOCIATION,
)
