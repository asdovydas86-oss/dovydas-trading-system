"""Rendering an `ApprovalResult` as a terminal page.

**This module only renders.** It computes no monetary quantity, sums nothing and
divides nothing: every figure it prints is a property already on the model. A
guard test asserts it names no `Money` or `Quantity` constructor and no
summation, so a number cannot appear on this page that no engine can be held to.
The one calculation it performs is turning a `Decimal` ratio into text, which is
formatting.

**The three registers are three sections and never one list.** Blocking reasons,
warnings and indeterminate reasons are rendered under three separate headings
with three separate counts, because *"indeterminate must be visually distinct
from within"* is the whole of `AP` §15.5 property 2 and the cheapest way to keep
it distinct is to never put it in the same list as anything else.

**The status is printed with what it does and does not mean, every time.**
`APPROVED` on this page means *the owner's own limits permit a position of this
size*. It is not a judgement about the idea, and the sentence beside it says so
rather than leaving a reader to remember.

**An absent figure prints its reason where the figure would have been.** A blank
where a size belongs reads as a size of nothing, and `AP` §14.3's warning is the
whole discipline: *"a zero makes the total look plausible and survives for
years."*

**78 columns, ASCII structure, no colour** — the convention `fmis.today`,
`fmis.trade_capture` and `fmis.valuation` already hold, so an approval survives a
pipe and a log file.

**This module names no side of its own.** A candidate's direction is printed by
reading `TradeDirection.value` at runtime, because ADR-0028's repository-wide
guard bans those words as literals and reading the enum is cheaper than widening
a boundary for a label.
"""

from __future__ import annotations

import textwrap
from typing import Any

from fmis.money import canonical_decimal_text
from fmis.provenance import Absent

from fmis.position_sizing.models import (
    ApprovalReason,
    ApprovalResult,
    ApprovalStatus,
    ReasonClass,
    ReasonScope,
)

__all__ = ["APPROVAL_LIMITATIONS", "STATUS_MEANING", "render_approval"]

_WIDTH = 78
_INDENT = "   "

#: What each status means and, more importantly, what it does not. Printed beside
#: the status on every page rather than documented somewhere a reader will not be
#: standing when they read the word.
STATUS_MEANING: dict[ApprovalStatus, str] = {
    ApprovalStatus.APPROVED: (
        "every limit the owner set was measured and none is breached by a "
        "position of this size. This is a statement about the owner's limits, "
        "not about the idea: nothing here judges the setup, and no probability "
        "is attached to anything on this page"
    ),
    ApprovalStatus.BLOCKED: (
        "at least one hard limit the owner set is breached, or no size could be "
        "produced at all. FMITS places no orders and cannot prevent the owner "
        "from trading anyway — a block means this system refuses to state that "
        "the size is within their limits, and the reasons below name which"
    ),
    ApprovalStatus.INDETERMINATE: (
        "something this approval depends on could not be measured. It is not a "
        "milder approval: an unmeasured limit is not a limit that was met, and "
        "the reasons below name every input that was missing"
    ),
}

#: The invariant register. Printed at the foot of every approval, never beside a
#: figure — the separation `fmis.today` established between what is always true of
#: this page and what is wrong with this run's numbers.
APPROVAL_LIMITATIONS: tuple[tuple[str, str], ...] = (
    (
        "AP-1",
        "This engine never executes. No order is placed, no venue is reached "
        "and nothing is reserved. It evaluates and reports.",
    ),
    (
        "AP-2",
        "Nothing is stored. An approval is a projection over the ledger and the "
        "owner's limits: recompute it and it is equal, store it and it drifts "
        "the first time either moves.",
    ),
    (
        "AP-3",
        "The recommended quantity is exact and is not rounded to any venue's lot "
        "or step size, which this system records nowhere. Round DOWN. It is a "
        "quotient, so where the division does not terminate it carries a long "
        "expansion and every figure derived from it inherits one — that tail is "
        "arithmetic, not precision, and a shorter number here would be a "
        "rounding policy this system does not set.",
    ),
    (
        "AP-4",
        "Every figure is pre-cost and pre-funding and assumes the stop is "
        "honoured at the stated price. Fees, slippage, funding and liquidation "
        "are not included, and no data this system ingests bounds a gap through "
        "the stop.",
    ),
    (
        "AP-5",
        "Correlation between markets is never measured. A duplicate-exposure "
        "warning counts positions in the same instrument, the same asset or a "
        "group the owner named; it does not claim those markets move together.",
    ),
    (
        "AP-6",
        "Each candidate is evaluated against the portfolio as it stands, "
        "independently of every other candidate. Two candidates that each fit "
        "the budget alone do not both fit it together, and nothing here "
        "sequences them.",
    ),
    (
        "AP-7",
        "No probability is calibrated. The planned R multiple is what one unit "
        "of risk buys if the nearest target is reached and the stop holds; it is "
        "not a likelihood that either happens.",
    ),
)


def _rule(character: str = "=") -> str:
    return character * _WIDTH


def _heading(title: str) -> list[str]:
    return [_rule(), title, _rule()]


def _section(title: str) -> list[str]:
    return ["", title, _rule("-")]


def _wrap(text: str, *, indent: str = _INDENT) -> list[str]:
    return textwrap.wrap(
        text, width=_WIDTH, initial_indent=indent, subsequent_indent=indent
    ) or [f"{indent}{text}"]


def _amount(value: Any) -> str:
    """A figure, or the reason there is none — never a blank and never a zero."""
    if isinstance(value, Absent):
        return f"unavailable — {value.reason}"
    return f"{value.text} {value.asset}"


def _ratio(value: Any) -> str:
    if isinstance(value, Absent):
        return f"unavailable — {value.reason}"
    return canonical_decimal_text(value)


def _figure(label: str, text: str) -> list[str]:
    """One labelled figure, wrapped rather than allowed to run off the page.

    A reason is a sentence and a sentence is longer than a column. Milestone `BJ`
    found four places where a long value pushed a *different* value past the page
    edge and the row's truncation cut that one in half — every width test passed,
    because the line fitted; the value inside it did not. So this returns lines,
    not a line, and the caller extends.
    """
    head = f"{_INDENT}{label:<24}"
    if len(head) + len(text) <= _WIDTH:
        return [f"{head}{text}"]
    return textwrap.wrap(
        text, width=_WIDTH, initial_indent=head, subsequent_indent=" " * len(head)
    )


def _reason_lines(reason: ApprovalReason) -> list[str]:
    lines = _wrap(f"[{reason.code}] {reason.statement}")
    lines.extend(_wrap(f"source: {reason.source}", indent=_INDENT * 2))
    return lines


def _register(
    title: str, reasons: tuple[ApprovalReason, ...], *, empty: str
) -> list[str]:
    """One of the three registers, with its own count and its own empty sentence.

    The empty sentence is required rather than optional: a heading with nothing
    under it reads as *"none found"* only if it says so, and *"no blocking reason"*
    and *"nothing was checked"* are the two readings a blank invites.
    """
    lines = _section(f"{title} ({len(reasons)})")
    if not reasons:
        return lines + _wrap(empty)
    for reason in reasons:
        lines.extend(_reason_lines(reason))
    return lines


def render_approval(result: ApprovalResult) -> str:
    """One approval as a plain-text page.

    Raises:
        TypeError: ``result`` is not an `ApprovalResult`.
    """
    if not isinstance(result, ApprovalResult):
        raise TypeError(
            f"result must be an ApprovalResult, got {type(result).__name__}"
        )
    proposal = result.proposal
    recommendation = result.recommendation
    lines: list[str] = []
    lines.extend(
        _heading(
            f"TRADE APPROVAL · {proposal.market.pair_symbol} · "
            f"{proposal.direction.value} · {proposal.book.value}"
        )
    )
    lines.extend(_wrap(f"evaluated {result.evaluated_at.isoformat()}", indent=""))
    lines.extend(
        _wrap(
            f"market {proposal.market.value} · account {proposal.account.value}",
            indent="",
        )
    )
    lines.extend(
        _wrap(
            f"policy {result.policy_version} · "
            f"{result.before_check.policy_version} · budget "
            f"{result.before_check.budget_id} v"
            f"{result.before_check.risk_policy_version}",
            indent="",
        )
    )

    lines.extend(_section(f"STATUS · {result.status.value.upper()}"))
    lines.extend(_wrap(STATUS_MEANING[result.status]))

    lines.extend(_section("SIZE"))
    lines.extend(
        _figure(
            "recommended size",
            "unavailable — " + recommendation.quantity.reason
            if isinstance(recommendation.quantity, Absent)
            else f"{recommendation.quantity.text} {recommendation.quantity.asset}",
        )
    )
    lines.extend(_figure("risk %", _ratio(recommendation.risk_fraction)))
    lines.extend(_figure("money at risk", _amount(recommendation.money_at_risk)))
    lines.extend(_figure("exposure at entry", _amount(recommendation.expected_exposure)))
    lines.extend(
        _figure("planned R multiple", _ratio(recommendation.expected_r_multiple))
    )
    lines.extend(_figure("equity", _amount(recommendation.equity)))
    lines.extend(_wrap(f"fraction: {recommendation.basis}"))
    for cap in recommendation.caps:
        lines.extend(_wrap(f"cap: {cap}"))
    for note in recommendation.notes:
        lines.extend(_wrap(f"note: {note}"))

    lines.extend(_section("GEOMETRY"))
    lines.extend(_figure("entry (reference)", canonical_decimal_text(proposal.entry)))
    lines.extend(_figure("stop", canonical_decimal_text(proposal.stop)))
    lines.extend(
        _figure(
            "targets",
            ", ".join(canonical_decimal_text(target) for target in proposal.targets)
            or "none stated",
        )
    )
    lines.extend(_figure("risk distance", _ratio(proposal.risk_distance)))
    lines.extend(_figure("reward distance", _ratio(proposal.reward_distance)))

    lines.extend(_section("OPEN RISK"))
    lines.extend(_figure("before this trade", _amount(result.open_risk_before)))
    lines.extend(_figure("after this trade", _amount(result.open_risk_after)))
    lines.extend(
        _figure("open positions", str(result.state.open_position_count))
    )
    lines.extend(_wrap(result.risk_basis))

    lines.extend(
        _register(
            "BLOCKING REASONS",
            result.blocking,
            empty=(
                "no hard limit the owner set is breached by this size, and a size "
                "was produced."
            ),
        )
    )
    lines.extend(
        _register(
            "WARNINGS",
            result.warnings,
            empty="nothing qualifies this size beyond the limitations below.",
        )
    )
    lines.extend(
        _register(
            "INDETERMINATE",
            result.indeterminate,
            empty="every limit the owner set was measurable against this candidate.",
        )
    )

    lines.extend(_section("SCOPE"))
    for scope in (ReasonScope.PORTFOLIO, ReasonScope.TRADE):
        scoped = result.scoped(scope)
        counts = ", ".join(
            f"{len([r for r in scoped if r.classification is kind])} "
            f"{kind.value}"
            for kind in ReasonClass
        )
        lines.extend(_wrap(f"{scope.value}: {len(scoped)} reason(s) — {counts}"))

    lines.extend(_section("LIMITATIONS"))
    for code, statement in APPROVAL_LIMITATIONS:
        lines.extend(_wrap(f"{code} · {statement}"))

    lines.append("")
    return "\n".join(lines)
