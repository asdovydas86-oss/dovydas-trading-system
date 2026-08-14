"""Rendering a recorded trade as a terminal page.

**This module only renders.** It computes nothing and decides nothing: every
figure it prints was produced by `fmis.trade_capture.views` or by the domain, and
a guard test asserts it calls no repository and no builder. A renderer that
computed one number would become the second place that number is defined.

**Absence is printed with its reason, never omitted.** An `Absent` renders as
its own sentence. A capital-at-risk line rendered blank reads as *no risk*; a
line reading *"no fill has established an average entry"* cannot be misread that
way, and on this page that misreading costs money.

**Arithmetic is shown, not merely its result.** Capital at risk prints the
subtraction and the multiplication beside the answer, and risk/reward prints the
division. `AR`-3's rule, and the reason is that the owner must be able to check
the number rather than trust it.

**78 columns, ASCII structure, no colour** — the same page geometry `fmits today`
uses, so the two read as one product and both survive a pipe and a log file.
"""

from __future__ import annotations

import textwrap
from decimal import Decimal
from typing import Any

from fmis.money import canonical_decimal_text
from fmis.provenance import Absent
from fmis.trade_capture.models import (
    CaptureOutcome,
    TradeListing,
    TradeView,
)
from fmis.trade_capture.views import CAPTURE_LIMITATIONS

__all__ = ["render_trade", "render_listing", "render_outcome"]

_WIDTH = 78
_ABSENT = "-"
_LABEL = 16


def _rule(char: str = "=") -> str:
    return char * _WIDTH


def _section(title: str) -> list[str]:
    return ["", f" {title}", _rule("-")]


def _wrap(text: str, *, indent: str = "   ", hanging: str = "  ") -> list[str]:
    return textwrap.wrap(
        text, width=_WIDTH, initial_indent=indent, subsequent_indent=indent + hanging
    ) or [indent]


def _field(label: str, value: str) -> str:
    return f" {label:<{_LABEL}} {value}"


def _token_lines(label: str, value: str) -> list[str]:
    """A value nothing bounds the length of — an id, a market, a path.

    Wrapped rather than truncated, including mid-token. Truncating a record id
    produces something the owner copies and cannot look up, which is worse than
    ugly.
    """
    prefix = f" {label:<{_LABEL}} "
    return textwrap.wrap(
        value,
        width=_WIDTH,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
        break_long_words=True,
        break_on_hyphens=False,
    ) or [prefix.rstrip()]


def _price(value: Decimal) -> str:
    return canonical_decimal_text(value)


def _maybe(value: Any, render: Any = str) -> str:
    """A `T | Absent` as text: the value, or the reason it is not there."""
    if isinstance(value, Absent):
        return value.reason
    return render(value)


def _term(value: Any) -> str:
    if isinstance(value, Absent):
        return value.reason
    return f"{value.qualified_id} (taxonomy v{value.taxonomy_version})"


def _header(title: str, subject: str) -> list[str]:
    return [_rule(), f" {title}", _rule()] + _token_lines("id", subject)


# --------------------------------------------------------------------------
# One trade.
# --------------------------------------------------------------------------


def _commitment_section(view: TradeView) -> list[str]:
    plan = view.plan
    lines = _section("COMMITMENT")
    lines.append(_field("committed", plan.committed_at.isoformat()))
    lines.append(
        _field("market", f"{plan.market.value}   book {plan.book.value}")
    )
    lines.append(_field("direction", plan.direction.value))
    lines.append(_field("stop", _price(plan.initial_invalidation)))
    lines.append(
        _field(
            "targets",
            ", ".join(_price(target) for target in plan.targets) or _ABSENT,
        )
    )
    lines.append(_field("confidence", plan.stated_confidence.label))
    lines.append(_field("setup", _term(plan.setup_type)))
    lines.append(_field("expires", _maybe(plan.expires_at, lambda at: at.isoformat())))
    lines.extend(_token_lines("proposal", _maybe(plan.proposal_id)))
    lines.extend(_token_lines("snapshot", _maybe(plan.market_snapshot_id)))
    for record_id in plan.analysis_record_ids or ():
        lines.extend(_token_lines("analysis", record_id))
    if not plan.analysis_record_ids:
        lines.append(_field("analysis", _ABSENT))
    if not isinstance(plan.note, Absent):
        lines.extend(_wrap(f"note: {plan.note}"))
    return lines


def _fills_section(view: TradeView) -> list[str]:
    lines = _section("FILLS")
    if not view.fills:
        lines.extend(
            _wrap(
                "Nothing has filled against this commitment. It is a plan the "
                "owner made and has not taken."
            )
        )
        return lines
    for fill in view.fills:
        marker = "   CORRECTED" if fill.was_corrected else ""
        lines.append(
            f" {fill.occurred_at.isoformat()}  {fill.side.value:<4} "
            f"{fill.quantity} @ {_price(fill.price)}{marker}"
        )
        lines.append(_field("", f"fee {fill.fee}   account {fill.account}"))
        lines.extend(_token_lines("", fill.event_id))
    return lines


def _position_section(view: TradeView) -> list[str]:
    lines = _section("POSITION")
    lines.append(_field("status", view.status.value.upper()))
    if isinstance(view.position, Absent):
        lines.extend(_wrap(view.position.reason))
        return lines
    position = view.position
    lines.append(
        _field("average entry", f"{_maybe(view.entry_price, _price)}")
    )
    lines.append(_field("", f"({position.average_entry.arithmetic})"))
    lines.append(_field("open", str(position.net_quantity)))
    lines.append(_field("max exposure", str(position.max_exposure)))
    if isinstance(view.capital_at_risk, Absent):
        lines.extend(_wrap(f"capital at risk: {view.capital_at_risk.reason}"))
    else:
        lines.append(_field("capital at risk", str(view.capital_at_risk)))
        lines.append(
            _field(
                "",
                f"(|{_maybe(view.entry_price, _price)} − "
                f"{_price(view.plan.initial_invalidation)}| × "
                f"{position.max_exposure.text})",
            )
        )
    if isinstance(view.planned_risk_reward, Absent):
        lines.extend(_wrap(f"risk / reward: {view.planned_risk_reward.reason}"))
    else:
        reading = view.planned_risk_reward
        lines.append(_field("risk / reward", f"{reading.ratio}"))
        lines.append(_field("", f"({reading.arithmetic})"))
    lines.append(_field("realized gross", str(position.realized_pnl_gross)))
    lines.append(_field("realized net", str(position.realized_pnl_net)))
    lines.append(
        _field(
            "fees",
            ", ".join(str(fee) for fee in position.fees) or _ABSENT,
        )
    )
    lines.append(
        _field("accounts", ", ".join(view.accounts) or _ABSENT)
    )
    lines.append(_field("fold", position.calculation_version))
    lines.append(
        _field(
            "dust policy",
            f"{position.dust_policy_id} v{position.dust_policy_version}",
        )
    )
    return lines


def _journal_section(view: TradeView) -> list[str]:
    lines = _section("JOURNAL")
    if view.journal.is_empty:
        lines.extend(
            _wrap(
                "Nothing has been written about this trade. `fmits trade note` "
                "appends an entry; nothing is ever edited."
            )
        )
        return lines
    for entry in view.journal.entries:
        recollection = " (written after the decision resolved)" if entry.recollection else ""
        lines.append(
            f" {entry.recorded_at.isoformat()}  {entry.kind.value}{recollection}"
        )
        if not isinstance(entry.title, Absent):
            lines.extend(_wrap(entry.title, indent="   "))
        if not isinstance(entry.body, Absent):
            lines.extend(_wrap(entry.body, indent="     "))
        for tag in entry.tags:
            counted = "counted" if tag.is_counted else "not counted"
            lines.append(f"     tag {tag.term.qualified_id} [{tag.origin.value}, {counted}]")
    return lines


def _warnings_section(view: TradeView) -> list[str]:
    lines = _section("WARNINGS")
    if not view.warnings:
        lines.append(" none")
        return lines
    for warning in view.warnings:
        lines.extend(_wrap(f"{warning.code}  {warning.statement}", indent=" "))
    return lines


def _limitations_section() -> list[str]:
    lines = _section("LIMITATIONS")
    for code, statement in CAPTURE_LIMITATIONS:
        lines.extend(_wrap(f"{code}  {statement}", indent=" "))
    return lines


def render_trade(view: TradeView) -> str:
    """The whole page for one recorded swing trade."""
    if not isinstance(view, TradeView):
        raise TypeError(f"view must be a TradeView, got {type(view).__name__}")
    lines = _header(
        f"RECORDED TRADE — {view.plan.market.pair_symbol} "
        f"{view.plan.direction.value}",
        view.plan_id,
    )
    lines.extend(_commitment_section(view))
    lines.extend(_fills_section(view))
    lines.extend(_position_section(view))
    lines.extend(_journal_section(view))
    lines.extend(_warnings_section(view))
    lines.extend(_limitations_section())
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# The listing.
# --------------------------------------------------------------------------


def render_listing(listing: TradeListing) -> str:
    """One row per commitment, with the filters and the exclusions stated.

    Rows keep the store's own deterministic order — by the instant each
    commitment was made, then by id. **Not a ranking**: nothing on this page is
    sorted by size, by profit or by anything a reader could mistake for quality.
    """
    if not isinstance(listing, TradeListing):
        raise TypeError(
            f"listing must be a TradeListing, got {type(listing).__name__}"
        )
    lines = [_rule(), " RECORDED TRADES", _rule()]
    stated = listing.filters.stated
    lines.append(
        _field(
            "filters",
            ", ".join(f"{axis}={value}" for axis, value in stated) or "none",
        )
    )
    lines.append(
        _field(
            "showing",
            f"{len(listing.rows)} of {listing.total} recorded "
            f"({listing.excluded} excluded by the filters above)",
        )
    )
    lines.append("")
    if not listing.rows:
        lines.extend(
            _wrap(
                "No recorded trade matches. An empty list means nothing was "
                "recorded here — it does not mean nothing is held.",
                indent=" ",
            )
        )
        lines.append("")
        return "\n".join(lines)
    header = (
        f" {'COMMITTED':<20} {'SYMBOL':<10} {'DIR':<5} {'STATUS':<8} "
        f"{'STOP':>10} {'AT RISK':>14}"
    )
    lines.append(header)
    lines.append(_rule("-"))
    for row in listing.rows:
        lines.append(
            f" {row.committed_at.strftime('%Y-%m-%d %H:%M'):<20} "
            f"{row.market.pair_symbol:<10} {row.direction.value:<5} "
            f"{row.status.value.upper():<8} {_price(row.stop):>10} "
            f"{_maybe(row.capital_at_risk, lambda money: money.text + ' ' + money.asset.code):>14}"
        )
        lines.extend(_token_lines("", row.plan_id))
        if not isinstance(row.realized_pnl_net, Absent):
            lines.append(_field("", f"realized net {row.realized_pnl_net}"))
    lines.append("")
    lines.extend(
        _wrap(
            "Rows are ordered by when each commitment was made. This is not a "
            "ranking: nothing here is sorted by size, profit or quality.",
            indent=" ",
        )
    )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# What a write command wrote.
# --------------------------------------------------------------------------


def render_outcome(outcome: CaptureOutcome) -> str:
    """What reached the store, then the trade as it now stands.

    The receipt comes first and names each record's id and whether it was
    **created**. A re-run after a crash creates nothing and says so, because a
    surface that printed "recorded" either way would teach the owner that running
    the command twice records the trade twice.
    """
    if not isinstance(outcome, CaptureOutcome):
        raise TypeError(
            f"outcome must be a CaptureOutcome, got {type(outcome).__name__}"
        )
    lines = [_rule(), f" {outcome.action.upper()}", _rule()]
    for record in outcome.written:
        state = "created" if record.created else "already stored, unchanged"
        lines.append(_field(record.kind, state))
        lines.extend(_token_lines("", record.record_id))
        lines.extend(_token_lines("", record.relative_path))
    if outcome.was_already_stored:
        lines.append("")
        lines.extend(
            _wrap(
                "Every record this command names was already in the store, byte "
                "for byte. Nothing was written and no second trade exists — an "
                "identical re-entry is an idempotent success.",
                indent=" ",
            )
        )
    lines.append("")
    lines.append(render_trade(outcome.view))
    return "\n".join(lines)
