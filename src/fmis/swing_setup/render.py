"""Plain-text rendering of a `SetupAssessment`.

Presentation only. Every value printed here already exists on the assessment;
this module computes nothing and reaches no engine. This is one of the two
places in the repository directional vocabulary may appear — see
[ADR-0028](../../../docs/adr/ADR-0028-directional-interpretation-boundary.md).

Absent values print as an em dash with a stated reason, never as a blank or a
zero, following every other renderer in this repository. A `WAIT` result is
rendered as a complete, successful page — never as an error and never with
fields hidden to make the page look shorter.
"""

from __future__ import annotations

from fmis.swing_setup.models import (
    Direction,
    Probability,
    ProbabilityStatus,
    RiskReward,
    SetupAssessment,
    SetupState,
    Trigger,
)

__all__ = ["render_setup"]

_WIDTH = 70
_ABSENT = "—"


def _rule(title: str = "") -> str:
    if not title:
        return "═" * _WIDTH
    return f"── {title} " + "─" * max(_WIDTH - len(title) - 4, 0)


def _number(value: float) -> str:
    """Format a price. Every caller already guards its own absence with `_ABSENT`."""
    return f"{value:,.6g}"


def _lines(items: tuple[str, ...], *, empty: str) -> list[str]:
    if not items:
        return [f"  {empty}"]
    return [f"  · {item}" for item in items]


def _trigger_block(trigger: Trigger | None) -> list[str]:
    if trigger is None:
        return [f"  {_ABSENT}"]
    lines = [f"  {trigger.statement}"]
    if trigger.level is not None:
        origin = trigger.level.origin
        provenance = (
            f"{trigger.level.side.value} · {origin.label.value} @ bar {origin.index}"
            if origin is not None
            else trigger.level.side.value
        )
        lines.append(f"    level: {_number(trigger.level.price)} ({provenance})")
    if trigger.bar_index is not None:
        lines.append(f"    confirmed at bar: {trigger.bar_index}")
    return lines


def _risk_reward_block(risk_reward: RiskReward | None) -> list[str]:
    if risk_reward is None:
        return [f"  {_ABSENT}"]
    return [
        f"  reference {_number(risk_reward.entry)} (not an order price)  "
        f"stop {_number(risk_reward.stop)}  "
        f"target {_number(risk_reward.target)}",
        f"  risk {_number(risk_reward.risk)}  reward {_number(risk_reward.reward)}  "
        f"R:R {risk_reward.ratio:,.2f}",
    ]


def _probability_line(probability: Probability) -> str:
    # ProbabilityStatus has exactly one member today, NOT_CALIBRATED — see its
    # own docstring for why. A calibrated status is a future milestone's field
    # to render, not a branch to speculate about here.
    assert probability.status is ProbabilityStatus.NOT_CALIBRATED
    return "  NOT_CALIBRATED — no backtested statistical model exists yet"


def render_setup(assessment: SetupAssessment) -> str:
    """Render one `SetupAssessment` as a fixed-width plain-text page.

    Raises:
        TypeError: ``assessment`` is not a `SetupAssessment`.
    """
    if not isinstance(assessment, SetupAssessment):
        raise TypeError(
            f"assessment must be a SetupAssessment, got {type(assessment).__name__}"
        )

    direction_text = assessment.direction.value.upper() if assessment.direction else _ABSENT
    lines: list[str] = [
        _rule(f"SWING SETUP — {assessment.symbol}"),
        f"  as of: {assessment.as_of.isoformat()}   objective: {assessment.objective}   "
        f"source: {assessment.source}",
        f"  state: {assessment.state.value.upper()}   direction: {direction_text}   "
        f"sufficiency: {assessment.sufficiency.value}",
        "",
        _rule("THESIS"),
        *_lines(assessment.thesis, empty="no thesis — see WAIT reason above"),
        "",
        _rule("DIRECTIONAL FACTORS"),
    ]
    for factor in assessment.directional_factors:
        lines.append(
            f"  · {factor.family}: {factor.lean.value} "
            f"({factor.observed}) — {factor.source}"
        )
    lines.extend(
        [
            "",
            _rule("REGIME CONTEXT"),
            *_lines(assessment.regime_context, empty=_ABSENT),
            "",
            _rule("CONFIRMATION"),
            *_lines(assessment.confirmation, empty="not applicable — WAIT"),
            "",
            _rule("TRIGGER"),
            *_trigger_block(assessment.trigger),
            "",
            _rule("INVALIDATION / STOP"),
            *_lines(assessment.invalidation, empty="not applicable — WAIT"),
        ]
    )
    if assessment.stop is not None:
        origin = assessment.stop.origin
        provenance = (
            f"{assessment.stop.side.value} · {origin.label.value} @ bar {origin.index}"
            if origin is not None
            else assessment.stop.side.value
        )
        lines.append(f"  stop level: {_number(assessment.stop.price)} ({provenance})")
    else:
        lines.append(f"  stop level: {_ABSENT}")

    lines.extend([
        "",
        _rule("TARGET(S)"),
    ])
    if assessment.targets:
        for target in assessment.targets:
            origin = target.origin
            provenance = (
                f"{target.side.value} · {origin.label.value} @ bar {origin.index}"
                if origin is not None
                else target.side.value
            )
            lines.append(f"  · {_number(target.price)} ({provenance})")
    else:
        lines.append(f"  {_ABSENT}")

    lines.extend(
        [
            "",
            _rule("RISK / REWARD"),
            *_risk_reward_block(assessment.risk_reward),
            "",
            _rule("PROBABILITY"),
            _probability_line(assessment.probability),
            "",
            _rule("LIMITATIONS"),
            *_lines(assessment.limitations, empty="none stated"),
            "",
            _rule(),
            "  Policy: " + assessment.policy_id,
            "  This is a technically valid setup according to policy v1, not a "
            "claim of profitability.",
            "  Nothing here is a recommendation to trade; position sizing and "
            "money risk are not computed.",
        ]
    )
    return "\n".join(lines)
