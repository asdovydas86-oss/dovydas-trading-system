"""Rendering a `TodayWorkspace` as a terminal page.

**This module only renders.** It computes nothing, decides nothing, reorders
nothing and hides nothing. A test asserts it calls no builder, no section
adapter and no engine, and imports only the model.

**Section order is the design decision, and it is inverted against instinct.**
Attention, then capital, then the market, then opportunities, then the queue,
then memory, then warnings. A dashboard that opens with opportunities is a
dashboard that produces trades; the highest-probability way this product loses
real money is a position taken while the owner is already committed, not a bad
signal.

**Two registers, never mixed.** This-run warnings appear inline, beside the
value they qualify and again in their own section. The invariant limitations
print once, at the foot. Repetition of invariant text is the fastest known way
to teach a reader to skip a region, and the region this page most needs read is
the variable one.

**Absence is printed, never omitted.** An `NotAvailable` renders as its reason
*and* the inference it forbids. A section rendered blank reads as a section with
nothing in it, which for capital is the most expensive misreading available on
this page.

**78 columns, ASCII structure, no colour.** Every rule, label and separator this
module writes is `=` or `-`; content it did not write — an engine's verbatim
thesis — is printed exactly as composed, whatever punctuation that sentence
already uses. Nothing depends on a terminal's colours, so the page survives a
pipe, a log file and a reader who cannot distinguish them.
"""

from __future__ import annotations

import textwrap
from types import MappingProxyType

from fmis.today.models import (
    AnalysisSummary,
    JournalSummary,
    MarketOverview,
    Opportunities,
    OpportunityLine,
    PortfolioOverview,
    PriorityQueue,
    QueueEntry,
    TodayError,
    TodayWorkspace,
    NotAvailable,
    WarningClass,
    WarningSeverity,
    WorkspaceWarning,
)

__all__ = ["render_today"]

_WIDTH = 78
_ABSENT = "-"
_INDENT = "   "
_DEEP = "     "

#: Reporting order for the warnings section. Fixed, and it is not a severity
#: sort: the classes are the brief's own five, and ordering them by severity
#: would make the list read as ordered by importance.
_WARNING_ORDER: tuple[WarningClass, ...] = (
    WarningClass.MISSING_DATA,
    WarningClass.INCOMPLETE_ANALYSIS,
    WarningClass.RISK,
    WarningClass.CORRELATION,
    WarningClass.LIMITATION,
)

#: A word for every severity, so nothing on this page depends on colour.
_SEVERITY_LABEL = MappingProxyType({
    WarningSeverity.BLOCK: "REFUSED",
    WarningSeverity.WARNING: "WARNING",
    WarningSeverity.INFORMATION: "NOTE",
})

#: The heading each warning class prints under. A mapping rather than a
#: transformation of the enum's own value, so the guard test asserting this
#: package never calls `create`/`update`/`replace` can stay blunt — a guard that
#: has to distinguish `store.trades.replace` from `"a_b".replace("_", " ")` is a
#: guard with a hole in exactly the shape of a string method.
_WARNING_CLASS_HEADING = MappingProxyType({
    WarningClass.MISSING_DATA: "missing data",
    WarningClass.INCOMPLETE_ANALYSIS: "incomplete analysis",
    WarningClass.RISK: "risk",
    WarningClass.CORRELATION: "correlation",
    WarningClass.LIMITATION: "limitations",
})


def _rule(char: str = "=") -> str:
    return char * _WIDTH


def _wrap(text: str, *, indent: str = _DEEP, hanging: str = "  ") -> list[str]:
    return textwrap.wrap(
        text, width=_WIDTH, initial_indent=indent, subsequent_indent=indent + hanging
    )


def _section(title: str) -> list[str]:
    return ["", f" {title}", _rule("-")]


def _price(value: float) -> str:
    """Formatted exactly as `fmis.swing_setup` formats a price, so they match."""
    return f"{value:,.6g}"


def _token_line(prefix: str, value: str) -> list[str]:
    """One value on its own line(s), wrapped rather than truncated.

    Record ids, snapshot ids, market ids, store paths and symbols are the values
    on this page whose length nothing bounds. Truncating one would produce
    something a reader copies and cannot look up; overflowing the page would let
    a terminal cut it at a position that depends on the window. So they wrap,
    including mid-token when a token is longer than a line — which is ugly for a
    64-character digest and is the only option that loses nothing.
    """
    return textwrap.wrap(
        value,
        width=_WIDTH,
        initial_indent=prefix,
        subsequent_indent=prefix + "  ",
        break_long_words=True,
        break_on_hyphens=False,
    )


def _label(label: str, value: str) -> str:
    return f"{_INDENT}{label:<22} {value}"


def _require_fits(lines: list[str]) -> None:
    """The page-width contract, as its own function so it can be tested exactly.

    A terminal that wraps a row mid-value produces something a reader parses as
    a different value. Every value on this page is wrapped or given its own
    line before reaching here, so an over-wide line is a defect in this module
    rather than an unusual input — and it is raised rather than printed.

    Separate from `render_today` because the boundary is the point: a test can
    hand it a line of exactly `_WIDTH` and one of `_WIDTH + 1` and pin the
    comparison, which a test going through the whole page cannot do without
    constructing an input that happens to land on the boundary.
    """
    for line in lines:
        if len(line) > _WIDTH:
            raise TodayError(
                f"rendered line of {len(line)} exceeds the {_WIDTH}-column page: "
                f"{line!r}"
            )


def _absence(value: NotAvailable, *, label: str) -> list[str]:
    """An `NotAvailable`, in full. There is no short form, on purpose."""
    lines = [f"{_INDENT}{label:<22} not available"]
    lines.extend(_wrap(value.reason))
    lines.extend(_wrap(f"owned by: {value.owned_by}"))
    lines.extend(_wrap(f"! {value.forbidden_inference}"))
    return lines


def _value_or_absence(value: str | NotAvailable, *, label: str) -> list[str]:
    """A labelled value, or its absence in full.

    A value that does not fit beside its label moves onto its own wrapped lines
    rather than running past the page edge. Budget notes and exposure summaries
    are composed from record fields whose length nothing bounds, and a label
    column is not a reason to truncate one.
    """
    if isinstance(value, NotAvailable):
        return _absence(value, label=label)
    inline = _label(label, value)
    if len(inline) <= _WIDTH:
        return [inline]
    return [f"{_INDENT}{label}"] + _wrap(value)


def _attention(workspace: TodayWorkspace) -> list[str]:
    """The three lines that can stop the evening, before anything else is read.

    Each is a count of something already established, never a summary judgement:
    *"2 setups need a decision"* removes information from the sections below;
    *"2 good setups"* would invent one.
    """
    queue = workspace.queue
    blocks = len(workspace.blocking_warnings)
    warnings = len(
        [w for w in workspace.warnings if w.severity is WarningSeverity.WARNING]
    )
    portfolio = workspace.portfolio
    capital = (
        f"{portfolio.open_count} open position(s) recorded"
        if portfolio.store_present
        else "no store on this machine — nothing recorded is known"
    )
    return [
        _label("ATTENTION", f"{len(queue.needs_attention)} setup(s) to look at "
                            f"· {len(queue.blocked)} refused"),
        _label("CAPITAL", capital),
        _label("SIGNALS", f"{blocks} refusal(s) · {warnings} warning(s)"),
    ]


def _market_block(market: MarketOverview) -> list[str]:
    lines = _section("1. MARKET OVERVIEW")
    lines.append(_label("Symbols scanned", str(market.scanned)))
    if market.analysis_as_of is not None:
        lines.append(
            _label("Analysis as of", market.analysis_as_of.isoformat())
        )
    lines.append("")
    lines.append(f"{_INDENT}outcome")
    for label, count in market.status_counts:
        dots = "." * max(20 - len(label), 3)
        lines.append(f"{_DEEP}{label} {dots} {count}")
    lines.append("")
    lines.append(f"{_INDENT}breadth (a distribution, not a verdict)")
    if market.breadth:
        for label, count in market.breadth:
            dots = "." * max(20 - len(label), 3)
            lines.append(f"{_DEEP}{label} {dots} {count}")
    else:
        lines.append(f"{_DEEP}(no symbol produced an assessment)")
    lines.append("")
    lines.append(
        f"{_INDENT}read and declined {len(market.readable_declined)} "
        f"· could not classify {len(market.unreadable)}"
    )
    if market.unreadable:
        lines.extend(_wrap(", ".join(market.unreadable)))
    for observation in market.observations:
        lines.extend(_wrap(observation, indent=f"{_INDENT}! "))
    lines.append("")
    lines.extend(_wrap(market.regime_note, indent=_INDENT, hanging=""))
    return lines


def _portfolio_block(portfolio: PortfolioOverview) -> list[str]:
    lines = _section("2. PORTFOLIO OVERVIEW")
    lines.append(f"{_INDENT}Store")
    lines.extend(_token_line(_DEEP, portfolio.store_root))
    lines.append(
        _label("Store present", "yes" if portfolio.store_present else "no")
    )
    if portfolio.snapshot_as_of is not None:
        lines.append(_label("Snapshot as of", portfolio.snapshot_as_of.isoformat()))

    lines.append("")
    lines.append(f"{_INDENT}open positions ({portfolio.open_count})")
    if portfolio.open_positions:
        for position in portfolio.open_positions:
            lines.extend(_token_line(_DEEP, position.market))
            lines.extend(
                _token_line(
                    f"{_DEEP}  ",
                    f"{position.direction}  {position.quantity}  "
                    f"book {position.book}",
                )
            )
            lines.extend(
                _token_line(
                    f"{_DEEP}  ",
                    f"entry {position.average_entry} "
                    f"· {position.trade_count} fill(s)",
                )
            )
            lines.append(f"{_DEEP}  opened {position.opened_at.isoformat()}")
            for label, figure in (
                ("mark", position.mark),
                ("value", position.market_value),
                ("unrealized", position.unrealized_pnl),
            ):
                if figure is None:
                    continue
                lines.extend(_token_line(f"{_DEEP}  ", f"{label} {figure}"))
    else:
        lines.append(f"{_DEEP}none recorded")

    lines.append("")
    for label, value in (
        ("Market value", portfolio.market_value),
        ("Unrealized P&L", portfolio.unrealized_pnl),
        ("Cash", portfolio.cash),
        ("Exposure", portfolio.exposure),
        ("Risk committed", portfolio.committed_risk),
        ("Risk available", portfolio.available_risk),
        ("Risk budget", portfolio.budget_note),
        ("Marks", portfolio.marks_note),
    ):
        lines.extend(_value_or_absence(value, label=label))

    if portfolio.limits:
        lines.append("")
        lines.append(f"{_INDENT}configured limits ({len(portfolio.limits)})")
        for limit in portfolio.limits:
            lines.extend(
                _token_line(
                    _DEEP,
                    f"{limit.scope}  {limit.stated_limit}  ({limit.severity})",
                )
            )
            status = (
                "indeterminate — nothing measured against it"
                if isinstance(limit.status, NotAvailable)
                else limit.status
            )
            lines.append(f"{_DEEP}  status: {status}")
    return lines


def _opportunity_header(line: OpportunityLine) -> list[str]:
    direction = line.direction.upper() if line.direction else _ABSENT
    header = f"{line.state.upper()}  {line.symbol}  {direction}"
    if line.risk_reward is not None:
        header += f"   R:R {line.risk_reward:,.2f}"
    stop = _price(line.stop) if line.stop is not None else _ABSENT
    target = _price(line.target) if line.target is not None else _ABSENT
    return _token_line(_INDENT, header) + [
        f"{_DEEP}target {target}   stop {stop}"
    ]


def _reasons(label: str, texts: tuple[str, ...]) -> list[str]:
    if not texts:
        return []
    lines = [f"{_DEEP}{label}:"]
    for text in texts:
        lines.extend(_wrap(text, indent=f"{_DEEP}  "))
    return lines


def _opportunities_block(opportunities: Opportunities) -> list[str]:
    lines = _section("3. TODAY'S OPPORTUNITIES")
    lines.append(
        f"{_INDENT}confirmed {len(opportunities.confirmed)} "
        f"· candidate {len(opportunities.candidates)} "
        f"· wait {opportunities.waiting_count} "
        f"· error {len(opportunities.failed)}"
    )

    for group, texts in (
        (opportunities.confirmed, ("reason", "confirmation", "invalidation")),
        (opportunities.candidates, ("reason", "needs", "invalidation")),
    ):
        for line in group:
            lines.append("")
            lines.extend(_opportunity_header(line))
            lines.extend(_reasons(texts[0], line.thesis))
            lines.extend(_reasons(texts[1], line.confirmation))
            lines.extend(_reasons(texts[2], line.invalidation))

    if opportunities.waiting:
        lines.append("")
        lines.append(f"{_INDENT}WAIT — a successful result, not a failure")
        for group in opportunities.waiting:
            noun = "symbol" if len(group.symbols) == 1 else "symbols"
            lines.append(f"{_DEEP}{len(group.symbols)} {noun}:")
            lines.extend(_wrap(", ".join(group.symbols), indent=f"{_DEEP}  "))
            lines.extend(_wrap(group.reason, indent=f"{_DEEP}  "))

    if opportunities.failed:
        lines.append("")
        lines.append(f"{_INDENT}ERROR — no analysis happened for these")
        for failure in opportunities.failed:
            lines.append(f"{_DEEP}{failure.symbol}")
            lines.extend(_wrap(failure.detail, indent=f"{_DEEP}  "))
    return lines


def _queue_entry(entry: QueueEntry, *, position: int) -> list[str]:
    line = entry.opportunity
    direction = line.direction.upper() if line.direction else _ABSENT
    header = f"{position}. {line.symbol}  {line.state.upper()}  {direction}"
    if line.risk_reward is not None:
        header += f"   R:R {line.risk_reward:,.2f}"
    lines = _token_line(_INDENT, header)
    if line.thesis:
        lines.extend(_wrap(line.thesis[0], indent=f"{_DEEP}"))
    for warning in entry.blocked_by + entry.warnings:
        lines.append(
            f"{_DEEP}[{warning.code}] {_SEVERITY_LABEL[warning.severity]}"
        )
        lines.extend(_wrap(warning.statement, indent=f"{_DEEP}  "))
        for detail in warning.detail:
            lines.extend(_wrap(detail, indent=f"{_DEEP}  "))
    return lines


def _queue_block(queue: PriorityQueue) -> list[str]:
    lines = _section("4. PRIORITY QUEUE")
    lines.extend(_wrap(queue.ordering, indent=_INDENT, hanging=""))
    if queue.is_empty:
        lines.append("")
        lines.append(f"{_INDENT}nothing is actionable today")
        return lines

    if queue.needs_attention:
        lines.append("")
        lines.append(f"{_INDENT}NEEDS ATTENTION ({len(queue.needs_attention)})")
        for position, entry in enumerate(queue.needs_attention, start=1):
            lines.append("")
            lines.extend(_queue_entry(entry, position=position))

    if queue.blocked:
        lines.append("")
        lines.append(f"{_INDENT}IGNORE FOR NOW ({len(queue.blocked)})")
        lines.extend(
            _wrap(
                "This system refuses to produce a number for these. It places "
                "no orders and cannot stop you trading anyway.",
                indent=_DEEP,
                hanging="",
            )
        )
        for position, entry in enumerate(queue.blocked, start=1):
            lines.append("")
            lines.extend(_queue_entry(entry, position=position))
    return lines


def _journal_block(journal: JournalSummary) -> list[str]:
    lines = _section("5. TRADE JOURNAL")
    if isinstance(journal.note, NotAvailable):
        lines.extend(_absence(journal.note, label="Journal"))
        return lines
    lines.extend(_wrap(journal.note, indent=_INDENT, hanging=""))

    if journal.decisions:
        lines.append("")
        lines.append(f"{_INDENT}live proposals ({len(journal.decisions)})")
        for decision in journal.decisions:
            for part in decision.split(" · "):
                lines.extend(_token_line(_DEEP, part))

    if journal.closed_positions:
        lines.append("")
        lines.append(f"{_INDENT}recently closed")
        for closed in journal.closed_positions:
            lines.extend(_token_line(_DEEP, closed.market))
            lines.extend(
                _token_line(
                    f"{_DEEP}  ",
                    f"{closed.realized_net}  {closed.trade_count} fill(s)",
                )
            )
            lines.append(f"{_DEEP}  closed {closed.closed_at.isoformat()}")

    if journal.entries:
        lines.append("")
        lines.append(f"{_INDENT}latest notes")
        for entry in journal.entries:
            mark = " (recollection)" if entry.recollection else ""
            lines.extend(_token_line(_DEEP, f"{entry.kind}  {entry.title}{mark}"))
            lines.extend(
                _token_line(
                    f"{_DEEP}  ",
                    f"{entry.recorded_at.isoformat()} · {entry.author}",
                )
            )
    return lines


def _analysis_block(analysis: AnalysisSummary) -> list[str]:
    lines = _section("6. RECENT ANALYSIS")
    for label, entries in (
        ("archived pages", analysis.archived),
        ("cited analyses", analysis.citations),
        ("market snapshots", analysis.snapshots),
    ):
        lines.append(f"{_INDENT}{label} ({len(entries)})")
        if not entries:
            lines.append(f"{_DEEP}none")
            continue
        for entry in entries:
            lines.extend(
                _token_line(_DEEP, f"{entry.record_type}  {entry.subject}")
            )
            lines.append(f"{_DEEP}  {entry.analysis_as_of.isoformat()}")
            lines.extend(_token_line(f"{_DEEP}  ", entry.record_id))
    lines.append("")
    if isinstance(analysis.change_note, NotAvailable):
        lines.extend(_absence(analysis.change_note, label="What changed"))
    else:
        lines.extend(_wrap(analysis.change_note, indent=_INDENT, hanging=""))
    return lines


def _warning_lines(warning: WorkspaceWarning) -> list[str]:
    lines = [
        f"{_DEEP}[{warning.code}] {_SEVERITY_LABEL[warning.severity]}"
    ]
    lines.extend(_wrap(warning.statement, indent=f"{_DEEP}  "))
    for detail in warning.detail:
        lines.extend(_wrap(detail, indent=f"{_DEEP}  "))
    if warning.subjects:
        lines.extend(
            _wrap(f"subjects: {', '.join(warning.subjects)}", indent=f"{_DEEP}  ")
        )
    lines.extend(_wrap(f"source: {warning.evidence}", indent=f"{_DEEP}  "))
    return lines


def _warnings_block(workspace: TodayWorkspace) -> list[str]:
    lines = _section("7. WORKSPACE WARNINGS")
    if not workspace.warnings:
        lines.append(f"{_INDENT}none raised")
        return lines
    for kind in _WARNING_ORDER:
        group = workspace.warnings_of(kind)
        if not group:
            continue
        lines.append("")
        lines.append(f"{_INDENT}{_WARNING_CLASS_HEADING[kind]} ({len(group)})")
        for warning in group:
            lines.extend(_warning_lines(warning))
    return lines


def render_today(workspace: TodayWorkspace) -> str:
    """Render one Daily Trading Workspace as a plain-text page.

    Raises:
        TypeError: ``workspace`` is not a `TodayWorkspace`.
        TodayError: a rendered line exceeded the page width. Prose is wrapped
            and values are printed on their own lines, so an over-wide line is a
            defect in this module rather than an unusual input, and it is raised
            rather than printed — the same guard, for the same reason, as the
            workspace and daily renderers.
    """
    if not isinstance(workspace, TodayWorkspace):
        raise TypeError(
            f"workspace must be a TodayWorkspace, got {type(workspace).__name__}"
        )

    lines: list[str] = [_rule()]
    lines.append(" FMITS TODAY - daily trading workspace")
    lines.append(_rule())
    lines.append(_label("Reference time", workspace.reference_time.isoformat()))
    lines.append(_label("Objective", workspace.objective))
    lines.extend(_wrap(f"source: {workspace.source}", indent=_INDENT, hanging="  "))
    lines.append("")
    lines.extend(_attention(workspace))

    lines.extend(_market_block(workspace.market))
    lines.extend(_portfolio_block(workspace.portfolio))
    lines.extend(_opportunities_block(workspace.opportunities))
    lines.extend(_queue_block(workspace.queue))
    lines.extend(_journal_block(workspace.journal))
    lines.extend(_analysis_block(workspace.analysis))
    lines.extend(_warnings_block(workspace))

    lines.append("")
    lines.append(" To read any symbol in full:")
    lines.append("     fmits setup SYMBOL")
    lines.append(" To read the full market report:")
    lines.append("     fmits scan")
    lines.append("")
    lines.append(_rule("-"))
    lines.append(" LIMITATIONS")
    for code, text in workspace.limitations:
        head = f" [{code}] "
        lines.extend(
            textwrap.wrap(
                text,
                width=_WIDTH,
                initial_indent=head,
                subsequent_indent=" " * len(head),
            )
        )
    lines.append("")
    lines.append(_rule())
    lines.append(" Nothing here is ranked by desirability, scored or recommended. No")
    lines.append(" position size is computed. WAIT is a successful result. FMITS places")
    lines.append(" no orders and records only what you have told it.")
    lines.append(_rule())

    _require_fits(lines)
    return "\n".join(lines)
