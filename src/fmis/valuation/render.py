"""Rendering a `PortfolioValuation` as a terminal page.

**This module only renders.** It computes no monetary quantity, sums nothing and
hides nothing: every money figure it prints is a property already on the model.
A guard test asserts it names no `Money` constructor and no summation, so a
figure cannot appear on this page that no engine can be held to. The one
calculation it does perform is turning a `timedelta` into hours and minutes,
which is a formatting decision and belongs to a renderer.

**An absent figure prints its reason where the figure would have been.** A blank
where a total belongs reads as a total of nothing, and for a portfolio that is
the most expensive misreading available. `AP` §14.3's warning is the whole of the
discipline: *"a zero makes the total look plausible and survives for years."*

**Provenance is on the page, not in a footnote.** Every priced market prints
where its price came from and how it was chosen, because a reader who cannot
trace a total back to its prices has to take it on faith.

**78 columns, ASCII structure, no colour** — the convention `fmis.today` and
`fmis.trade_capture` already hold, so a valuation survives a pipe and a log file.

**This module names no side of its own.** A position's direction is printed by
reading `PositionDirection.value` at runtime; the two exposure rows are labelled
*"long exposure"* and *"short exposure"* — the domain's own field names — rather
than by the bare words, because ADR-0028's repository-wide guard bans those as
literals and rewording is cheaper than widening a boundary for a label.
"""

from __future__ import annotations

import textwrap
from datetime import timedelta

from fmis.money import Money
from fmis.provenance import Absent

from fmis.valuation.models import MarkedPosition, PortfolioValuation

__all__ = ["render_valuation"]

_WIDTH = 78
_INDENT = "   "


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


def _money(value: Money | Absent) -> str:
    """A figure, or the reason there is none — never a blank and never a zero."""
    if isinstance(value, Absent):
        return f"unavailable — {value.reason}"
    return f"{value.text} {value.asset}"


def _duration(value: timedelta | Absent) -> str:
    if isinstance(value, Absent):
        return f"unavailable — {value.reason}"
    total = int(value.total_seconds())
    hours, seconds = divmod(abs(total), 3600)
    minutes = seconds // 60
    sign = "-" if total < 0 else ""
    return f"{sign}{hours}h {minutes}m"


def _figure(label: str, value: Money | Absent) -> list[str]:
    """One labelled figure, wrapped rather than allowed to run off the page.

    A reason is a sentence and a sentence is longer than a column. Milestone BJ
    found four places where a long value pushed a *different* value past the page
    edge and the row's truncation cut that one in half — every width test passed,
    because the line fitted; the value inside it did not. So this returns lines,
    not a line, and the caller extends.
    """
    head = f"{_INDENT}{label:<22}"
    text = _money(value)
    if len(head) + len(text) <= _WIDTH:
        return [f"{head}{text}"]
    return textwrap.wrap(
        text,
        width=_WIDTH,
        initial_indent=head,
        subsequent_indent=" " * len(head),
    )


def _position_lines(entry: MarkedPosition) -> list[str]:
    # The indent is `_wrap`'s to add. Passing an already-indented string here
    # produced a doubly-indented header — found by the live run, not by a width
    # test, because the line still fitted.
    header = (
        f"{entry.market.pair_symbol} · {entry.position.book.value} · "
        f"{entry.position.direction.value} · "
        f"{entry.position.net_quantity.text} "
        f"{entry.position.net_quantity.asset}"
    )
    lines = _wrap(header, indent=_INDENT)
    if isinstance(entry.mark, Absent):
        lines.extend(
            _wrap(f"mark: unavailable — {entry.mark.reason}", indent=_INDENT * 2)
        )
    else:
        lines.extend(
            _wrap(
                f"mark {entry.mark.price} {entry.mark.quote_asset} as of "
                f"{entry.mark.as_of.isoformat()}",
                indent=_INDENT * 2,
            )
        )
        lines.extend(_wrap(f"from {entry.mark.source}", indent=_INDENT * 2))
    for label, value in (
        ("value", entry.market_value),
        ("cost basis", entry.cost_basis),
        ("unrealized", entry.unrealized_pnl),
    ):
        lines.extend(_wrap(f"{label:<13}{_money(value)}", indent=_INDENT * 2))
    return lines


def render_valuation(valuation: PortfolioValuation) -> str:
    """One valuation as a plain-text page.

    Raises:
        TypeError: ``valuation`` is not a `PortfolioValuation`.
    """
    if not isinstance(valuation, PortfolioValuation):
        raise TypeError(
            f"valuation must be a PortfolioValuation, got "
            f"{type(valuation).__name__}"
        )
    lines: list[str] = []
    lines.extend(
        _heading(
            f"PORTFOLIO VALUATION · {valuation.portfolio_id} · "
            f"{valuation.base_currency}"
        )
    )
    lines.extend(_wrap(f"as of {valuation.as_of.isoformat()}", indent=""))
    lines.extend(
        _wrap(
            f"prices taken {valuation.prices.taken_at.isoformat()} · "
            f"{valuation.prices.source}",
            indent="",
        )
    )
    lines.extend(
        _wrap(f"oldest mark age: {_duration(valuation.mark_age)}", indent="")
    )

    lines.extend(_section("VALUE"))
    lines.extend(_figure("market value", valuation.market_value))
    lines.extend(_figure("cost basis", valuation.cost_basis))
    lines.extend(_figure("unrealized P&L", valuation.unrealized_pnl))
    lines.extend(_figure("cash", valuation.cash))
    lines.extend(_figure("equity", valuation.marked_equity))
    lines.extend(_wrap(valuation.equity_basis))

    lines.extend(_section("EXPOSURE"))
    lines.extend(_figure("gross", valuation.gross_exposure))
    lines.extend(_figure("net", valuation.market_value))
    lines.extend(_figure("long exposure", valuation.long_exposure))
    lines.extend(_figure("short exposure", valuation.short_exposure))
    lines.extend(_figure("open risk", valuation.open_risk))
    if valuation.unstopped_markets:
        lines.extend(
            _wrap(
                "open risk is unavailable because no commitment records a stop "
                "for: " + ", ".join(valuation.unstopped_markets)
            )
        )

    lines.extend(_section(f"POSITIONS ({len(valuation.positions)})"))
    if not valuation.positions:
        lines.extend(
            _wrap(
                "no open position in the covered books. This is what the "
                "recorded fills fold to, not a statement about accounts this "
                "system has never been told about."
            )
        )
    for entry in valuation.positions:
        lines.extend(_position_lines(entry))

    lines.extend(_section("PRICES"))
    lines.extend(
        _wrap(
            f"{valuation.marks.marked_count} of "
            f"{valuation.marks.requested_count} market(s) priced"
        )
    )
    for line in valuation.price_provenance:
        lines.extend(_wrap(line))
    for market, reason in sorted(valuation.marks.reasons.items()):
        lines.extend(_wrap(f"{market}: {reason}"))

    if valuation.fold_disagreement:
        lines.extend(_section("TWO FOLDS"))
        lines.extend(
            _wrap(
                "these markets hold fills in more than one account, so the "
                "position list and the portfolio totals answer different "
                "questions about them: "
                + ", ".join(valuation.fold_disagreement)
            )
        )

    lines.extend(_section("LIMITATIONS"))
    for code, statement in valuation.limitations:
        lines.extend(_wrap(f"{code} · {statement}"))

    lines.append("")
    return "\n".join(lines)
