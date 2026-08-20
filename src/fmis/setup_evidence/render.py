"""Plain-text rendering of a `SetupEvidenceReport`.

Presentation only. Every value printed here already exists on the report; this
module computes nothing, groups nothing and reaches no engine.

**The page never recommends.** It answers why a setup exists, what supports it,
what conflicts with it, what is still awaited and what could not be read — and
stops there. `WAIT` renders as a complete, successful page with its evidence
shown honestly, never as an error and never with sections hidden to make an
empty result look shorter.

Every line is wrapped to the page width. A line that overflows in a terminal
reads as a different value, so the width is a contract and a test asserts it.
"""

from __future__ import annotations

import textwrap

from fmis.setup_evidence.models import (
    ConfluenceSummary,
    EvidenceItem,
    SetupEvidenceReport,
)

__all__ = ["render_setup_evidence", "PAGE_WIDTH"]

#: The page width, matching `fmis.swing_setup.render`'s own so the two pages sit
#: together in one terminal without either reflowing.
PAGE_WIDTH = 70

_ABSENT = "—"


def _rule(title: str = "") -> str:
    """A section rule that is exactly the page width, whatever the title.

    The title is truncated rather than allowed to push the rule over the margin.
    Nothing in this repository bounds `SetupAssessment.symbol`, so a long one
    would otherwise produce the single over-wide line the width contract exists
    to prevent — and it would appear only for that symbol, which is the hardest
    kind of layout bug to find.
    """
    if not title:
        return "═" * PAGE_WIDTH
    room = PAGE_WIDTH - 4
    if len(title) > room:
        title = title[: room - 1] + "…"
    return f"── {title} " + "─" * max(PAGE_WIDTH - len(title) - 4, 0)


def _wrap(text: str, *, indent: str, first: str | None = None) -> list[str]:
    """Wrap one logical line to the page width, never exceeding it."""
    initial = indent if first is None else first
    wrapped = textwrap.wrap(
        text,
        width=PAGE_WIDTH,
        initial_indent=initial,
        subsequent_indent=indent,
        break_long_words=True,
        break_on_hyphens=False,
    )
    return wrapped or [f"{initial.rstrip()} {_ABSENT}".rstrip()]


def _bullets(lines: tuple[str, ...], *, empty: str) -> list[str]:
    if not lines:
        return [f"  {empty}"]
    out: list[str] = []
    for line in lines:
        out.extend(_wrap(line, indent="    ", first="  · "))
    return out


def _item_block(item: EvidenceItem) -> list[str]:
    """One evidence item: its statement, then its provenance and any caveat."""
    out = _wrap(item.statement, indent="    ", first="  · ")
    families = (
        ", ".join(family.value for family in item.families) if item.families else "none"
    )
    out.extend(
        _wrap(
            f"family: {families}   source: {item.source}",
            indent="      ",
            first="      ",
        )
    )
    if item.correlated_with:
        out.extend(
            _wrap(
                "not independent of: " + ", ".join(item.correlated_with),
                indent="      ",
                first="      ",
            )
        )
    elif item.independence_note is not None:
        # An item with a note but no links is one composed of correlated parts
        # — the geometry projected from three restatements of one level, or the
        # confirmation that is also the trigger. Printed here because it is the
        # only place a reader would see that a deduplication happened at all;
        # items that *do* link are already explained under FAMILY CONFLUENCE.
        out.extend(_wrap(item.independence_note, indent="      ", first="      note: "))
    return out


def _items(items: tuple[EvidenceItem, ...], *, empty: str) -> list[str]:
    if not items:
        return [f"  {empty}"]
    out: list[str] = []
    for item in items:
        out.extend(_item_block(item))
    return out


def _confluence_block(confluence: ConfluenceSummary) -> list[str]:
    """Family agreement, printed as families and never as a total.

    The independence line is printed whether or not independence holds. A page
    that only mentioned the problem case would let its absence read as a claim
    that everything is fine, which is exactly the inference this block exists to
    prevent.
    """
    agreeing = (
        ", ".join(family.value for family in confluence.agreeing_families)
        if confluence.agreeing_families
        else "none"
    )
    conflicting = (
        ", ".join(family.value for family in confluence.conflicting_families)
        if confluence.conflicting_families
        else "none"
    )
    out = [
        f"  agreeing families:    {agreeing}",
        f"  conflicting families: {conflicting}",
        f"  agreeing items: {confluence.agreeing_item_count}   "
        f"distinct families: {confluence.independent_agreeing_families}",
    ]
    if not confluence.agreeing_item_count:
        # "NOT established" beside an empty set would read as a finding about
        # evidence that was examined. Nothing was examined, and those are
        # different statements.
        verdict = "not assessed — no agreeing evidence to compare"
    elif confluence.independence_established:
        verdict = (
            "established — at least two agreeing items share no family and no "
            "upstream input"
        )
    else:
        verdict = "NOT established — see the caveats below"
    out.extend(
        _wrap(f"independent corroboration: {verdict}", indent="    ", first="  ")
    )
    for caveat in confluence.caveats:
        out.extend(_wrap(caveat, indent="    ", first="  ! "))
    return out


def render_setup_evidence(report: SetupEvidenceReport) -> str:
    """Render one `SetupEvidenceReport` as a fixed-width plain-text page.

    Raises:
        TypeError: ``report`` is not a `SetupEvidenceReport`.
    """
    if not isinstance(report, SetupEvidenceReport):
        raise TypeError(
            f"report must be a SetupEvidenceReport, got {type(report).__name__}"
        )

    direction = report.direction_text or _ABSENT
    lines: list[str] = [
        _rule(f"SETUP EVIDENCE — {report.symbol}"),
        f"  as of: {report.as_of.isoformat()}",
        f"  state: {report.state_text}   direction: {direction}   "
        f"sufficiency: {report.sufficiency.value}",
    ]
    if report.setup_identity is not None:
        identity = report.setup_identity
        lines.extend(
            _wrap(
                f"setup identity: {report.setup_identity.setup_id}",
                indent="    ",
                first="  ",
            )
        )
        if identity.occurrence_id is not None:
            lines.extend(
                _wrap(
                    f"occurrence: {identity.occurrence_id}",
                    indent="    ",
                    first="  ",
                )
            )

    lines.extend(
        [
            "",
            _rule("WHY THIS SETUP EXISTS"),
            *_bullets(
                report.thesis,
                empty="no thesis stated — this assessment reached no directional view",
            ),
        ]
    )
    if report.regime_context:
        lines.append("")
        lines.extend(_bullets(report.regime_context, empty=_ABSENT))

    lines.extend(
        [
            "",
            _rule("SUPPORTING EVIDENCE"),
            *_items(
                report.supporting,
                empty="none — nothing currently supports a directional view",
            ),
            "",
            _rule("CONFLICTING EVIDENCE"),
            *_items(report.conflicting, empty="none currently conflicts"),
        ]
    )
    if report.invalidation:
        lines.append("")
        lines.extend(
            _wrap(
                "standing invalidation — a condition that would contradict this "
                "setup, not a present conflict:",
                indent="  ",
                first="  ",
            )
        )
        lines.extend(_bullets(report.invalidation, empty=_ABSENT))

    lines.extend(
        [
            "",
            _rule("MISSING CONFIRMATION"),
            *_items(report.missing, empty="nothing is outstanding"),
            "",
            _rule("UNAVAILABLE / LIMITATIONS"),
            *_items(report.unavailable, empty="nothing was unreadable"),
            "",
            _rule("FAMILY CONFLUENCE"),
            *_confluence_block(report.confluence),
            "",
            _rule("DECISION READINESS"),
            f"  decision_ready: {'yes' if report.decision_ready else 'no'}   "
            f"(sufficiency: {report.sufficiency.value})",
        ]
    )
    lines.extend(_wrap(report.decision_ready_reason, indent="  ", first="  "))
    lines.extend(
        _wrap(
            "decision_ready states only that enough deterministic information "
            "exists. It is not a direction, not an instruction, and not a claim "
            "the setup will work.",
            indent="  ",
            first="  ",
        )
    )

    if report.warnings:
        lines.extend(["", _rule("WARNINGS")])
        lines.extend(_bullets(report.warnings, empty=_ABSENT))

    lines.extend(["", _rule()])
    lines.extend(
        _wrap(
            f"Policy: {report.provenance.get('policy_id', _ABSENT)}   "
            f"projection v{report.provenance.get('projection_version', _ABSENT)}",
            indent="  ",
            first="  ",
        )
    )
    lines.extend(
        _wrap(
            "This page explains an assessment. It is not a recommendation to "
            "trade, and no position size, calibrated probability or quality "
            "score is produced anywhere in this system.",
            indent="  ",
            first="  ",
        )
    )
    return "\n".join(lines)
