"""Rendering a `SwingWorkspace` as a terminal page.

**This module only renders.** It computes nothing, decides nothing, reorders
nothing and hides nothing. A guard test asserts it calls no builder, no section
adapter and no engine, and imports only the model and the ranking vocabulary.

**Section order is the design decision, and it is inherited rather than
reinvented.** The global summary and the capital position come before the
opportunities for the reason `fmis.today` states: the highest-probability way
this product loses real money is not a bad signal, it is a new position taken
while the owner is already at their limit. The one departure is that the summary
*counts* the opportunities at the top, so a reader who stops after eight lines
knows whether there is anything to read further down.

**Every ranked row prints its own key.** That is what makes the ordering
reconstructable: two adjacent rows can be compared component by component
without opening this file, and a row that moved between two runs moved because
one of the four printed values changed.

**Absence is printed, never omitted.** A `NotAvailable` renders as its reason
*and* the inference it forbids. There is no short form.

**78 columns, ASCII structure, no colour.** Every rule, label and separator this
module writes is `=` or `-`; content it did not write — an engine's verbatim
thesis, a policy's own sentence — is printed exactly as composed. Nothing
depends on a terminal's colours, so the page survives a pipe, a log file and a
reader who cannot distinguish them.
"""

from __future__ import annotations

import textwrap
from types import MappingProxyType

from fmis.swing_workspace.models import (
    BookExposure,
    EvidenceDigest,
    GlobalSummary,
    NoTradeGroup,
    PaperPosition,
    RankedSetup,
    SwingWorkspace,
    SwingWorkspaceError,
    UnanalysedSymbol,
)
from fmis.swing_workspace.ranking import EXCLUDED_FROM_RANKING
from fmis.today import (
    NotAvailable,
    PerformanceSummary,
    PortfolioOverview,
    WarningClass,
    WarningSeverity,
    WorkspaceWarning,
)

__all__ = ["WORKSPACE_PAGE_WIDTH", "render_swing_workspace"]

#: Named with the package prefix because `fmis.setup_evidence` already exports a
#: name spelled `PAGE_WIDTH`, and this repository holds zero export collisions by
#: rule — the guard that enforces it is what caught this one.
WORKSPACE_PAGE_WIDTH = 78

_INDENT = "   "
_DEEP = "     "
_ROW = "       "
_ABSENT = "-"

#: A word for every severity, so nothing on this page depends on colour.
_SEVERITY_LABEL = MappingProxyType(
    {
        WarningSeverity.BLOCK: "REFUSED",
        WarningSeverity.WARNING: "WARNING",
        WarningSeverity.INFORMATION: "NOTE",
    }
)

#: Reporting order for the warnings section. Fixed, and it is not a severity
#: sort: ordering by severity makes a list read as ordered by importance, and
#: these are five categories rather than five levels.
_WARNING_ORDER: tuple[WarningClass, ...] = (
    WarningClass.MISSING_DATA,
    WarningClass.INCOMPLETE_ANALYSIS,
    WarningClass.RISK,
    WarningClass.CORRELATION,
    WarningClass.LIMITATION,
)

_WARNING_HEADING = MappingProxyType(
    {
        WarningClass.MISSING_DATA: "missing data",
        WarningClass.INCOMPLETE_ANALYSIS: "incomplete analysis",
        WarningClass.RISK: "risk",
        WarningClass.CORRELATION: "correlation",
        WarningClass.LIMITATION: "limitations",
    }
)


def _rule(char: str = "=") -> str:
    return char * WORKSPACE_PAGE_WIDTH


def _wrap(text: str, *, indent: str = _DEEP, hanging: str = "  ") -> list[str]:
    return textwrap.wrap(
        text,
        width=WORKSPACE_PAGE_WIDTH,
        initial_indent=indent,
        subsequent_indent=indent + hanging,
    )


def _token(prefix: str, value: str) -> list[str]:
    """One unbounded value — an id, a digest, a store path — wrapped, never cut.

    Truncating a record id produces something a reader copies and cannot look
    up; overflowing the page lets the terminal cut it at a position that depends
    on the window. So it wraps, mid-token if it must.

    **The continuation is blank, not a repeat of the prefix.** An earlier draft
    indented with `prefix + "  "`, which printed the label again on every wrapped
    line — and a label printed twice reads as two values, which for a rank key is
    exactly the misreading this page exists to prevent.
    """
    return textwrap.wrap(
        value,
        width=WORKSPACE_PAGE_WIDTH,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
        break_long_words=True,
        break_on_hyphens=False,
    )


def _section(title: str) -> list[str]:
    return ["", f" {title}", _rule("-")]


def _label(label: str, value: str, *, indent: str = _INDENT, width: int = 20) -> str:
    return f"{indent}{label:<{width}} {value}"


def _value_or_absence(
    value: str | NotAvailable,
    *,
    label: str,
    indent: str = _INDENT,
    width: int = 20,
) -> list[str]:
    """A labelled value, or its absence in full. There is no short form."""
    if isinstance(value, NotAvailable):
        return _absence(value, label=label, indent=indent, width=width)
    inline = _label(label, value, indent=indent, width=width)
    if len(inline) <= WORKSPACE_PAGE_WIDTH:
        return [inline]
    return _token(f"{indent}{label:<{width}} ", value)


def _absence(
    value: NotAvailable, *, label: str, indent: str = _INDENT, width: int = 20
) -> list[str]:
    lines = [_label(label, "not available", indent=indent, width=width)]
    lines.extend(_wrap(value.reason, indent=indent + "  "))
    lines.extend(_wrap(f"owned by: {value.owned_by}", indent=indent + "  "))
    lines.extend(_wrap(f"! {value.forbidden_inference}", indent=indent + "  "))
    return lines


def _price(value: float) -> str:
    """Formatted exactly as `fmis.swing_setup` formats a price, so they match."""
    return f"{value:,.6g}"


def _require_fits(lines: list[str]) -> None:
    """The page-width contract, as its own function so it can be tested exactly.

    A terminal that wraps a row mid-value produces something a reader parses as a
    different value. Every value on this page is wrapped or given its own line
    before reaching here, so an over-wide line is a defect in this module rather
    than an unusual input — and it is raised rather than printed.
    """
    for line in lines:
        if len(line) > WORKSPACE_PAGE_WIDTH:
            raise SwingWorkspaceError(
                f"rendered line of {len(line)} exceeds the {WORKSPACE_PAGE_WIDTH}-column "
                f"page: {line!r}"
            )


# ---------------------------------------------------------------------------
# 1. Header and global summary
# ---------------------------------------------------------------------------


def _header(workspace: SwingWorkspace) -> list[str]:
    lines = [
        _rule(),
        " SWING DECISION WORKSPACE",
        f" as of {workspace.reference_time.isoformat()} · objective "
        f"{workspace.objective}",
        _rule(),
    ]
    lines.extend(_token(" source: ", workspace.source))
    return lines


def _summary(summary: GlobalSummary) -> list[str]:
    lines = _section("GLOBAL MARKET SUMMARY")
    lines.append(_label("scanned", f"{summary.scanned} symbol(s)"))
    lines.append(
        _label(
            "analysis as of",
            _ABSENT
            if summary.analysis_as_of is None
            else summary.analysis_as_of.isoformat(),
        )
    )
    lines.append(_label("confirmed", str(summary.confirmed)))
    lines.append(_label("candidates", str(summary.candidates)))
    lines.append(_label("no trade", str(summary.waiting)))
    lines.append(_label("could not be read", str(summary.unanalysed)))
    lines.append(_label("open positions", str(summary.open_positions)))
    lines.append(_label("paper positions", str(summary.paper_positions)))
    lines.append(
        _label(
            "breadth",
            " · ".join(f"{label} {count}" for label, count in summary.breadth)
            or _ABSENT,
        )
    )
    lines.extend(_value_or_absence(summary.risk_state, label="risk state"))
    lines.extend(_value_or_absence(summary.open_exposure, label="open exposure"))
    lines.extend(_wrap(summary.regime_note, indent=_INDENT))
    return lines


# ---------------------------------------------------------------------------
# 2. The ranked sections
# ---------------------------------------------------------------------------


def _evidence(evidence: EvidenceDigest | NotAvailable) -> list[str]:
    if isinstance(evidence, NotAvailable):
        return _absence(evidence, label="evidence", indent=_ROW, width=10)
    lines = [
        _label(
            "evidence",
            f"{evidence.supporting} supporting · {evidence.conflicting} "
            f"conflicting · {evidence.missing} awaited",
            indent=_ROW,
            width=10,
        )
    ]
    lines.extend(
        _wrap(
            "families agreeing: "
            + (", ".join(evidence.agreeing_families) or _ABSENT)
            + " | conflicting: "
            + (", ".join(evidence.conflicting_families) or _ABSENT),
            indent=_ROW + "  ",
        )
    )
    lines.extend(
        _wrap(
            "independence "
            + (
                "established"
                if evidence.independence_established
                else (
                    "NOT established — the agreement above shares upstream "
                    f"inputs, in {len(evidence.caveats)} stated way(s); read "
                    "them under EVIDENCE INDEPENDENCE below"
                )
            ),
            indent=_ROW + "  ",
        )
    )
    lines.extend(
        _wrap(
            "decision "
            + (
                "ready: enough deterministic information exists"
                if evidence.decision_ready
                else "NOT ready"
            ),
            indent=_ROW + "  ",
        )
    )
    lines.extend(_wrap(evidence.decision_ready_reason, indent=_ROW + "  "))
    return lines


def _geometry(row: RankedSetup) -> str:
    """Stop, target and ratio, as the engine computed them. Never a ranking key."""
    opportunity = row.opportunity
    parts = [
        f"stop {_ABSENT if opportunity.stop is None else _price(opportunity.stop)}",
        f"target "
        f"{_ABSENT if opportunity.target is None else _price(opportunity.target)}",
        f"R:R "
        f"{_ABSENT if opportunity.risk_reward is None else f'{opportunity.risk_reward:.2f}'}",
    ]
    return " · ".join(parts)


def _approval(row: RankedSetup) -> list[str]:
    opportunity = row.opportunity
    if opportunity.approval_status is None:
        return [
            _label(
                "approval",
                "not checked — see the approval note under this section",
                indent=_ROW,
                width=10,
            )
        ]
    lines = [
        _label("approval", opportunity.approval_status, indent=_ROW, width=10)
    ]
    if opportunity.recommended_size is not None:
        lines.extend(
            _wrap(f"size {opportunity.recommended_size}", indent=_ROW + "  ")
        )
    if opportunity.open_risk_after is not None:
        lines.extend(
            _wrap(
                f"open risk after entry {opportunity.open_risk_after}",
                indent=_ROW + "  ",
            )
        )
    for reason in opportunity.blocking_reasons:
        lines.extend(_wrap(f"BLOCKING: {reason}", indent=_ROW + "  "))
    for reason in opportunity.approval_warnings:
        lines.extend(_wrap(f"warning: {reason}", indent=_ROW + "  "))
    return lines


def _ranked_row(row: RankedSetup, *, awaiting: bool) -> list[str]:
    opportunity = row.opportunity
    # Wrapped rather than laid out on one line: nothing bounds a symbol's
    # length, and a 60-character pair pushed the heading past the margin. Found
    # by a test rather than by a reader, which is the only acceptable way to
    # find it.
    lines = _token(
        f"{_INDENT}#{row.position}  ",
        f"{opportunity.symbol}  "
        f"{_ABSENT if opportunity.direction is None else opportunity.direction}  "
        f"[{opportunity.state} · {opportunity.sufficiency}]",
    )
    lines.extend(_token(f"{_ROW}{'rank key':<10} ", row.key.explain()))
    lines.append(_label("risk", _geometry(row), indent=_ROW, width=10))
    lines.extend(_approval(row))
    lines.extend(_evidence(row.evidence))
    lines.extend(
        _value_or_absence(row.identity, label="identity", indent=_ROW, width=10)
    )
    lines.extend(
        _value_or_absence(row.paper_status, label="paper", indent=_ROW, width=10)
    )
    lines.extend(_value_or_absence(row.held, label="held", indent=_ROW, width=10))
    for statement in opportunity.thesis:
        lines.extend(_wrap(f"- {statement}", indent=_ROW))
    if awaiting:
        for statement in opportunity.confirmation:
            lines.extend(_wrap(f"awaiting: {statement}", indent=_ROW))
    for statement in opportunity.invalidation:
        lines.extend(_wrap(f"invalidated if: {statement}", indent=_ROW))
    return lines


def _opportunities(workspace: SwingWorkspace) -> list[str]:
    lines = _section("TOP OPPORTUNITIES")
    if not workspace.opportunities:
        lines.extend(
            _wrap(
                "No setup has confirmed under this policy. That is a successful "
                "result, not a failure or a gap — the wait list below holds "
                f"{len(workspace.wait_list)} setup(s) that have a thesis and are "
                "awaiting their confirmation.",
                indent=_INDENT,
                hanging="",
            )
        )
        return lines
    for position, row in enumerate(workspace.opportunities):
        if position:
            lines.append("")
        lines.extend(_ranked_row(row, awaiting=False))
    return lines


def _wait_list(workspace: SwingWorkspace) -> list[str]:
    lines = _section("WAIT LIST — a thesis exists, its confirmation has not")
    if not workspace.wait_list:
        lines.extend(
            _wrap(
                "No symbol reached a directional thesis short of confirmation.",
                indent=_INDENT,
                hanging="",
            )
        )
        return lines
    for position, row in enumerate(workspace.wait_list):
        if position:
            lines.append("")
        lines.extend(_ranked_row(row, awaiting=True))
    return lines


def _independence(workspace: SwingWorkspace) -> list[str]:
    """The correlation caveats, printed **once** for the whole page.

    They are carried per row on `EvidenceDigest.caveats`, because a consumer
    reading one row is entitled to the complete reason its independence failed.
    They are *printed* once because they are properties of the policy rather
    than of a symbol: every actionable row on a page reports the same three, and
    printing thirty identical paragraphs is the fastest way to teach a reader to
    skip the one section that most needs reading.

    Distinct caveats appear in the order the ranked rows first stated them —
    stable, and derived from the page's own order rather than from a sort.
    """
    seen: list[str] = []
    for row in workspace.opportunities + workspace.wait_list:
        digest = row.evidence
        if isinstance(digest, NotAvailable):
            continue
        for caveat in digest.caveats:
            if caveat not in seen:
                seen.append(caveat)
    if not seen:
        return []
    lines = _section("EVIDENCE INDEPENDENCE")
    lines.extend(
        _wrap(
            "Every row above reporting NOT established shares these upstream "
            "inputs. They are properties of the policy, not of one market, "
            "which is why they are stated once.",
            indent=_INDENT,
            hanging="",
        )
    )
    for position, caveat in enumerate(seen, start=1):
        lines.extend(_wrap(f"{position}. {caveat}", indent=_INDENT, hanging="   "))
    return lines


def _no_trade(groups: tuple[NoTradeGroup, ...], unread: tuple[UnanalysedSymbol, ...]) -> list[str]:
    lines = _section("NO TRADE")
    if not groups:
        lines.extend(
            _wrap(
                "Every symbol scanned reached a directional thesis.",
                indent=_INDENT,
                hanging="",
            )
        )
    for group in groups:
        lines.append(
            _label(
                f"{len(group.symbols)} symbol(s)",
                group.classification,
                indent=_INDENT,
                width=14,
            )
        )
        lines.extend(_wrap(group.reason, indent=_DEEP))
        lines.extend(_token(f"{_DEEP}  ", " ".join(group.symbols)))
    if unread:
        lines.append("")
        lines.append(f"{_INDENT}could not be read — never a no-trade result:")
        for entry in unread:
            lines.extend(_wrap(f"{entry.symbol}: {entry.detail}", indent=_DEEP))
    return lines


# ---------------------------------------------------------------------------
# 3. The owner's own book
# ---------------------------------------------------------------------------


def _paper(workspace: SwingWorkspace) -> list[str]:
    lines = _section("ACTIVE PAPER TRADES")
    if not workspace.paper:
        lines.extend(_wrap("No simulated trade is recorded.", indent=_INDENT, hanging=""))
    for position, trade in enumerate(workspace.paper):
        if position:
            lines.append("")
        lines.extend(_paper_row(trade))
    lines.append("")
    lines.extend(_value_or_absence(workspace.paper_note, label="note"))
    return lines


def _paper_row(trade: PaperPosition) -> list[str]:
    lines = [
        f"{_INDENT}{trade.market}  [{trade.state}]"
        + ("  HALTED — waiting for you, not for the market" if trade.halted else "")
    ]
    lines.extend(_token(f"{_DEEP}id      ", trade.activation_id))
    lines.append(_label("size", trade.open_size, indent=_DEEP, width=8))
    for label, value in (
        ("entry", trade.entry),
        ("risk", trade.initial_risk),
        ("R", trade.total_r),
        ("MFE", trade.max_favourable_r),
        ("MAE", trade.max_adverse_r),
    ):
        lines.extend(_value_or_absence(value, label=label, indent=_DEEP, width=8))
    lines.append(
        _label(
            "stop",
            f"{trade.stop} (initial {trade.initial_stop})"
            + (
                f" · widened {trade.stop_widenings} time(s)"
                if trade.stop_widenings
                else ""
            ),
            indent=_DEEP,
            width=8,
        )
    )
    lines.append(_label("bars", str(trade.bars_in_trade), indent=_DEEP, width=8))
    return lines


def _books(books: tuple[BookExposure, ...]) -> list[str]:
    if not books:
        return [
            f"{_INDENT}books",
            *_wrap(
                "no open position is recorded in any book, so there is nothing "
                "to separate simulated capital from real capital on",
                indent=_DEEP,
            ),
        ]
    lines = [f"{_INDENT}books"]
    for book in books:
        lines.extend(
            _value_or_absence(
                book.market_value,
                label=f"{book.label} ({book.open_positions})",
                indent=_DEEP,
            )
        )
    return lines


def _portfolio(workspace: SwingWorkspace) -> list[str]:
    portfolio: PortfolioOverview = workspace.portfolio
    lines = _section("PORTFOLIO SUMMARY")
    lines.extend(_token(f"{_INDENT}{'store':<20} ", portfolio.store_root))
    if not portfolio.store_present:
        lines.extend(
            _wrap(
                "this run did not read a durable store, so every figure below "
                "is an absence rather than a zero",
                indent=_DEEP,
            )
        )
    lines.append(
        _label("open positions", str(portfolio.open_count))
    )
    for label, value in (
        ("market value", portfolio.market_value),
        ("unrealized", portfolio.unrealized_pnl),
        ("exposure", portfolio.exposure),
        ("risk used", portfolio.committed_risk),
        ("risk remaining", portfolio.available_risk),
        ("cash", portfolio.cash),
        ("marks", portfolio.marks_note),
        ("budget", portfolio.budget_note),
    ):
        lines.extend(_value_or_absence(value, label=label))
    lines.extend(_books(workspace.books))
    return lines


def _statistics(statistics: PerformanceSummary) -> list[str]:
    lines = _section("STATISTICS SNAPSHOT")
    lines.append(_label("trades recorded", str(statistics.trades)))
    lines.append(_label("open", str(statistics.open_trades)))
    lines.append(_label("resolved", str(statistics.resolved)))
    lines.append(_label("sample floor", str(statistics.sample_floor)))
    for label, value in (
        ("win rate", statistics.win_rate),
        ("expectancy", statistics.expectancy),
        ("expectancy (R)", statistics.expectancy_r),
        ("profit factor", statistics.profit_factor),
        ("average R", statistics.average_r),
        ("drawdown", statistics.current_drawdown),
        ("realized", statistics.realized),
    ):
        lines.extend(_value_or_absence(value, label=label))
    for book in statistics.books:
        lines.append(
            _label(
                f"book: {book.label}",
                f"{book.trades} trade(s) · {book.closed} resolved",
            )
        )
    lines.extend(_wrap(statistics.floor_note, indent=_INDENT))
    lines.extend(_value_or_absence(statistics.note, label="note"))
    return lines


# ---------------------------------------------------------------------------
# 4. Warnings, the ordering rule, and the standing limitations
# ---------------------------------------------------------------------------


def _warning(warning: WorkspaceWarning) -> list[str]:
    lines = _wrap(
        f"[{_SEVERITY_LABEL[warning.severity]}] {warning.code}: {warning.statement}",
        indent=_DEEP,
    )
    if warning.subjects:
        lines.extend(_token(f"{_DEEP}  ", " ".join(warning.subjects)))
    for line in warning.detail:
        lines.extend(_wrap(line, indent=_DEEP + "  "))
    lines.extend(_wrap(f"source: {warning.evidence}", indent=_DEEP + "  "))
    return lines


def _warnings(workspace: SwingWorkspace) -> list[str]:
    lines = _section("WARNINGS")
    if not workspace.warnings:
        lines.extend(
            _wrap(
                "No rule fired on this run. That is not a statement that "
                "nothing is wrong; it is a statement that none of the checks "
                "this page performs found anything.",
                indent=_INDENT,
                hanging="",
            )
        )
        return lines
    for kind in _WARNING_ORDER:
        raised = tuple(
            warning for warning in workspace.warnings if warning.kind is kind
        )
        if not raised:
            continue
        lines.append(f"{_INDENT}{_WARNING_HEADING[kind]}")
        for warning in raised:
            lines.extend(_warning(warning))
    return lines


def _ordering(workspace: SwingWorkspace) -> list[str]:
    lines = _section("HOW THIS PAGE IS ORDERED")
    lines.extend(_wrap(workspace.ranking_rule, indent=_INDENT, hanging=""))
    lines.append("")
    lines.extend(
        _wrap(
            "orders nothing here: " + ", ".join(EXCLUDED_FROM_RANKING),
            indent=_INDENT,
            hanging="  ",
        )
    )
    return lines


def _limitations(workspace: SwingWorkspace) -> list[str]:
    lines = _section("LIMITATIONS")
    for code, text in workspace.limitations:
        lines.extend(_wrap(f"{code}: {text}", indent=_INDENT, hanging="  "))
    return lines


def render_swing_workspace(workspace: SwingWorkspace) -> str:
    """The whole page, as one string. Deterministic for a given workspace.

    Raises:
        TypeError: ``workspace`` is not a `SwingWorkspace`.
        SwingWorkspaceError: a rendered line exceeded the page width, which is a
            defect in this module rather than a property of the input.
    """
    if not isinstance(workspace, SwingWorkspace):
        raise TypeError(
            f"workspace must be a SwingWorkspace, got {type(workspace).__name__}"
        )
    lines: list[str] = []
    lines.extend(_header(workspace))
    lines.extend(_summary(workspace.summary))
    lines.extend(_opportunities(workspace))
    lines.extend(_wait_list(workspace))
    lines.extend(_independence(workspace))
    lines.extend(_no_trade(workspace.no_trade, workspace.unanalysed))
    lines.extend(_paper(workspace))
    lines.extend(_portfolio(workspace))
    lines.extend(_statistics(workspace.statistics))
    lines.extend(_warnings(workspace))
    lines.extend(_ordering(workspace))
    lines.extend(_limitations(workspace))
    lines.append(_rule())
    _require_fits(lines)
    return "\n".join(lines)
