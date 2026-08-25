"""What it takes for a geometry to earn forward testing. **Every criterion is measured.**

Milestone BW's `fmis.swing_lab.metrics.classify` promotes on one number: a
positive expectancy. That was the right bar for BW, which was asking whether a
gate helped, and it is **not** enough here. BX is explicitly looking for a policy
to propose, and a policy chosen because one backtest improved is exactly what §8
of the milestone brief forbids.

So this module states the bar as a **list of named, individually reported
criteria**, every one of them computed from measured results:

===  ==============================  ==================================================
 1   `pre_declared`                  the policy was written down before results existed
 2   `development_sample`            enough measurable trades to state a figure at all
 3   `holdout_sample`                the same, on symbols the study never looked at
 4   `development_expectancy`        positive on development
 5   `holdout_expectancy`            positive on the holdout too
 6   `symbol_concentration`          no single symbol carries the result
 7   `drawdown_recovered`            the worst decline is smaller than the total gain
 8   `parameter_plateau`             neighbouring thresholds behave, so it is not a spike
===  ==============================  ==================================================

**Why criterion 5 is "positive" rather than "not much worse".** BW measured a
variant that improved on its primary study and *deteriorated* on its holdout,
and the report had to spend a paragraph explaining why that was not an
improvement. A bar phrased as "no catastrophic deterioration" needs a number for
"catastrophic", and any such number is one a researcher can argue down after
seeing the result. "Positive on both samples" cannot be argued down. The softer
reading is still computed and reported as `holdout_not_catastrophic` so a reader
can see how far a near-miss missed by — it simply does not promote anything.

**Nothing here can produce approval to trade.** The strongest verdict remains
`LabVerdict.CANDIDATE_FOR_FORWARD_TEST`, which means *worth testing forward* and
whose `is_approved_for_trading` is `False` by construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from fmis.swing_lab.metrics import SAMPLE_FLOOR, VariantMetrics
from fmis.swing_lab.models import LabVerdict, SwingLabError

__all__ = [
    "MAX_SINGLE_SYMBOL_SHARE",
    "Criterion",
    "GeometryAssessment",
    "assess_geometry",
]

#: The largest share of gross absolute R one symbol may contribute before the
#: result is called that symbol's rather than the universe's. Pre-declared, and
#: chosen against the sample rather than against a result: with a development
#: universe of six symbols an even split is 16.7 %, so 40 % still admits real
#: concentration while refusing a result that is one coin wearing a universe.
MAX_SINGLE_SYMBOL_SHARE: Final[Decimal] = Decimal("0.40")


@dataclass(frozen=True, slots=True)
class Criterion:
    """One requirement, whether it was met, and the measurement that decided it.

    ``passed`` is deliberately a tri-state via ``None``: a criterion that could
    not be evaluated — because a cohort never reached the sample floor — is
    **not** a pass, and recording it as `False` would read as a measured failure.
    An unevaluated criterion blocks promotion exactly as a failed one does, but
    it says so in different words.
    """

    name: str
    requirement: str
    passed: bool | None
    observed: str

    def __post_init__(self) -> None:
        for field_name in ("name", "requirement", "observed"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise SwingLabError(f"{field_name} must be a non-empty str")
        if self.passed is not None and not isinstance(self.passed, bool):
            raise TypeError("passed must be True, False or None")

    @property
    def symbol(self) -> str:
        return {True: "PASS", False: "FAIL", None: "N/A "}[self.passed]


@dataclass(frozen=True, slots=True)
class GeometryAssessment:
    """One geometry policy judged against every criterion, with its verdict.

    **Reconstructable.** Everything here is derived from the two metric objects
    and the plateau reading, so a reader holding the artifact can recompute the
    verdict and check it against what a report claimed.
    """

    policy_id: str
    verdict: LabVerdict
    criteria: tuple[Criterion, ...]

    @property
    def blocking(self) -> tuple[Criterion, ...]:
        """Every criterion that is not a pass, in declaration order."""
        return tuple(item for item in self.criteria if item.passed is not True)

    @property
    def statement(self) -> str:
        """One sentence naming the verdict and what, if anything, blocked it."""
        if self.verdict is LabVerdict.CANDIDATE_FOR_FORWARD_TEST:
            return (
                f"{self.policy_id}: every criterion met. Worth testing forward — "
                "this is NOT approval to trade."
            )
        blockers = ", ".join(item.name for item in self.blocking)
        return f"{self.policy_id}: {self.verdict.value} — blocked by {blockers}."


def _sample_criterion(name: str, sample: str, metrics: VariantMetrics) -> Criterion:
    """A sample-size requirement, whose failure mode is ``None`` and never ``False``.

    A cohort below `SAMPLE_FLOOR` has established *nothing*, and `LabVerdict`
    already fixes the vocabulary for that: `INCONCLUSIVE` means too few trades to
    state a figure and is explicitly **not a negative result**. Recording a thin
    sample as a measured `False` would make the verdict read `REJECTED` — "this
    policy lost money" — about a policy nobody has measured. The count is
    reported either way, so a reader can see that a variant trading three times
    in three years is unusable without the verdict having to overclaim.
    """
    enough = metrics.measurable_trades >= SAMPLE_FLOOR
    return Criterion(
        name=name,
        requirement=f"at least {SAMPLE_FLOOR} measurable trades on {sample}",
        passed=True if enough else None,
        observed=f"{metrics.measurable_trades} measurable trades",
    )


def _not_catastrophic(
    development: Decimal | None, holdout: Decimal | None
) -> Criterion:
    """The brief's softer holdout reading. **Reported, never promoting.**

    *"No catastrophic deterioration on the holdout"* compares the holdout against
    what development gained — so the question only has a meaning when development
    gained something. With a negative development expectancy there is no gain to
    deteriorate from, and forcing an answer produced a nonsensical one: the first
    real run of this study reported a policy that made money on its holdout as
    having *failed* a not-catastrophic test, because it had not out-earned the
    magnitude of its own development loss.

    So a non-positive development expectancy makes this **not evaluable** rather
    than failed. The verdict is unaffected either way — this criterion is
    advisory and `_ADVISORY` excludes it from the decision — but a page that
    marks a passing holdout as a failure is a page that misleads.
    """
    requirement = (
        "REPORTED, NEVER PROMOTING: the softer reading of the brief — where "
        "development showed a gain, the holdout did not give more of it back "
        "than development earned. Not evaluable when development lost money, "
        "because there is then no gain to deteriorate from"
    )
    if development is None or holdout is None:
        return Criterion(
            name="holdout_not_catastrophic",
            requirement=requirement,
            passed=None,
            observed="not evaluable — an expectancy could not be stated",
        )
    if development <= 0:
        return Criterion(
            name="holdout_not_catastrophic",
            requirement=requirement,
            passed=None,
            observed=(
                f"not evaluable — development expectancy is {development:+.4f}R, "
                "so there is no gain for the holdout to give back"
            ),
        )
    return Criterion(
        name="holdout_not_catastrophic",
        requirement=requirement,
        passed=holdout > -development,
        observed=f"holdout {holdout:+.4f}R against development {development:+.4f}R",
    )


def _measure_text(metrics: VariantMetrics) -> str:
    value = metrics.expectancy_r.value
    if value is None:
        return f"no expectancy ({metrics.expectancy_r.reason})"
    return f"{value:+.4f}R over n={metrics.expectancy_r.n}"


def assess_geometry(
    *,
    policy_id: str,
    pre_declared: bool,
    development: VariantMetrics,
    holdout: VariantMetrics,
    development_symbol_share: Decimal | None,
    plateau: bool | None,
    plateau_detail: str,
) -> GeometryAssessment:
    """Judge one geometry against every criterion. **Pure, total and explicit.**

    ``plateau`` is supplied by the caller because a plateau is a property of a
    *family* of thresholds rather than of one policy, and this function judges
    one policy. ``None`` means the test could not be run — a policy with no
    numeric threshold has no neighbours, and that is reported as not-applicable
    rather than quietly passed.

    Raises:
        SwingLabError: ``policy_id`` is empty.
    """
    if not isinstance(policy_id, str) or not policy_id.strip():
        raise SwingLabError("policy_id must be a non-empty str")
    for name, value in (("development", development), ("holdout", holdout)):
        if not isinstance(value, VariantMetrics):
            raise TypeError(f"{name} must be a VariantMetrics")

    dev_expectancy = development.expectancy_r.value
    hold_expectancy = holdout.expectancy_r.value

    criteria: list[Criterion] = [
        Criterion(
            name="pre_declared",
            requirement=(
                "the policy was specified before any result was observed; a "
                "post-hoc policy can be reported but never independently validated"
            ),
            passed=pre_declared,
            observed="pre-declared" if pre_declared else "added after results were seen",
        ),
        _sample_criterion("development_sample", "development", development),
        _sample_criterion("holdout_sample", "the holdout", holdout),
        Criterion(
            name="development_expectancy",
            requirement="a positive expectancy on the development sample",
            passed=None if dev_expectancy is None else dev_expectancy > 0,
            observed=_measure_text(development),
        ),
        Criterion(
            name="holdout_expectancy",
            requirement=(
                "a positive expectancy on the holdout too — stated as 'positive' "
                "rather than 'not much worse' because any threshold for "
                "'catastrophic' is one a researcher could argue down after "
                "seeing the number"
            ),
            passed=None if hold_expectancy is None else hold_expectancy > 0,
            observed=_measure_text(holdout),
        ),
        _not_catastrophic(dev_expectancy, hold_expectancy),
        Criterion(
            name="symbol_concentration",
            requirement=(
                f"no single symbol contributes more than "
                f"{MAX_SINGLE_SYMBOL_SHARE:.0%} of gross absolute R on development"
            ),
            passed=(
                None
                if development_symbol_share is None
                else development_symbol_share <= MAX_SINGLE_SYMBOL_SHARE
            ),
            observed=(
                "no trade carries an R"
                if development_symbol_share is None
                else f"largest symbol share {development_symbol_share:.1%}"
            ),
        ),
        Criterion(
            name="drawdown_recovered",
            requirement=(
                "the worst peak-to-trough decline on the development R curve is "
                "smaller than the total R the sample earned"
            ),
            passed=(
                None
                if development.measurable_trades < SAMPLE_FLOOR
                else development.total_r > development.max_drawdown.max_drawdown_r
            ),
            observed=(
                f"total {development.total_r:+.2f}R against a worst decline of "
                f"{development.max_drawdown.max_drawdown_r:.2f}R"
            ),
        ),
        Criterion(
            name="parameter_plateau",
            requirement=(
                "neighbouring threshold values behave similarly, so the result is "
                "a plateau rather than a spike at one hand-picked number"
            ),
            passed=plateau,
            observed=plateau_detail,
        ),
    ]

    verdict = _verdict_from(criteria)
    return GeometryAssessment(
        policy_id=policy_id, verdict=verdict, criteria=tuple(criteria)
    )


#: Criteria that report but never promote or demote. `holdout_not_catastrophic`
#: is the softer reading of the brief, kept visible so a near-miss is legible,
#: and deliberately excluded from the decision so it cannot be used to argue a
#: losing holdout into a candidate.
_ADVISORY: Final[frozenset[str]] = frozenset({"holdout_not_catastrophic"})


def _verdict_from(criteria: Sequence[Criterion]) -> LabVerdict:
    """Fold criteria into one verdict. **A conjunction, never a score.**

    No weighting, no points, no "three out of four". Every deciding criterion
    must pass, because each one names a distinct way a backtest result can be an
    artifact and passing seven of them does not repair the eighth.

    * any deciding criterion measured as failed → `REJECTED`;
    * otherwise any deciding criterion that could not be evaluated →
      `INCONCLUSIVE`, because nothing was established rather than something
      negative;
    * all deciding criteria passed → `CANDIDATE_FOR_FORWARD_TEST`.
    """
    deciding = [item for item in criteria if item.name not in _ADVISORY]
    if any(item.passed is False for item in deciding):
        return LabVerdict.REJECTED
    if any(item.passed is None for item in deciding):
        return LabVerdict.INCONCLUSIVE
    return LabVerdict.CANDIDATE_FOR_FORWARD_TEST
