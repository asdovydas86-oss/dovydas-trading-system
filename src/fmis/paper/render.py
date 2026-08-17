"""Rendering the paper-trading surfaces as terminal pages.

**This module only renders.** It computes nothing and decides nothing: every
figure it prints was produced by `fmis.paper.views`, `fmis.paper.monitor` or the
domain, and a guard test asserts it calls no repository and no builder. A renderer
that computed one number would become the second place that number is defined.

**Absence is printed with its reason, never omitted.** An unrealized R rendered
blank reads as *flat*; a line reading *"no bar has been observed"* cannot be
misread that way, and on this page that misreading is the difference between a
trade that is level and one nobody has priced.

**78 columns, ASCII structure, no colour** — the geometry `fmits today` and
`fmits trade` already use, so all three read as one product and every one of them
survives a pipe and a log file.
"""

from __future__ import annotations

import textwrap
from decimal import Decimal
from typing import Any

from fmis.money import canonical_decimal_text
from fmis.provenance import Absent
from fmis.paper.compose import ActivationOutcome, SimulationReport
from fmis.paper.models import PAPER_LIMITATIONS
from fmis.paper.monitor import MONITOR_BASIS, TradeMonitor
from fmis.paper.views import PaperTradeView

__all__ = [
    "render_activation",
    "render_simulation",
    "render_status",
    "render_history",
    "render_lifecycle",
]

_WIDTH = 78
_LABEL = 18
_ABSENT = "-"


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

    Wrapped rather than truncated, including mid-token: a truncated record id is
    something the owner copies and cannot look up, which is worse than ugly.
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


def _value(value: Any) -> str:
    """One rule for every optional value on every page in this package."""
    if isinstance(value, Absent):
        return _ABSENT
    if isinstance(value, Decimal):
        return canonical_decimal_text(value)
    return str(value)


def _absences(pairs: tuple[tuple[str, Any], ...]) -> list[str]:
    """Every absent figure, with the reason it is absent, once at the foot.

    Beside the value would repeat a sentence up to a dozen times on one page and
    teach the reader to skip all of them; omitting it would let a dash read as a
    zero. Collected here, each reason is printed once and every dash on the page
    above has somewhere to be looked up.
    """
    lines: list[str] = []
    for label, value in pairs:
        if isinstance(value, Absent):
            lines.extend(_wrap(f"{label}: {value.reason}"))
    return lines


def _limitations() -> list[str]:
    lines = _section("LIMITATIONS")
    for code, text in PAPER_LIMITATIONS:
        lines.extend(_wrap(f"{code}  {text}"))
    return lines


def _monitor_block(monitor: TradeMonitor) -> list[str]:
    lines = _section("POSITION")
    lines.append(_field("state", monitor.state))
    lines.append(_field("open size", str(monitor.remaining)))
    lines.append(_field("entry", _value(monitor.entry_price)))
    lines.append(_field("last price", _value(monitor.last_price)))
    lines.append(
        _field(
            "stop",
            f"{canonical_decimal_text(monitor.effective_stop)} "
            f"(committed {canonical_decimal_text(monitor.initial_stop)})",
        )
    )
    lines.append(_field("next target", _value(monitor.next_target)))
    lines.append(_field("distance to stop", _value(monitor.distance_to_stop)))
    lines.append(_field("distance to tgt", _value(monitor.distance_to_target)))
    lines.append(_field("initial risk", _value(monitor.initial_risk)))
    lines.append(_field("realized R", _value(monitor.realized_r)))
    lines.append(_field("unrealized R", _value(monitor.unrealized_r)))
    lines.append(_field("total R", _value(monitor.total_r)))
    lines.append(_field("MFE / MAE (R)", f"{_value(monitor.max_favourable_r)} / {_value(monitor.max_adverse_r)}"))
    lines.append(_field("MFE / MAE", f"{_value(monitor.max_favourable_price)} / {_value(monitor.max_adverse_price)}"))
    lines.append(_field("bars in trade", str(monitor.bars_in_trade)))
    lines.append(_field("holding time", _value(monitor.holding_time)))
    lines.append(_field("days in trade", _value(monitor.days_in_trade)))
    lines.append(
        _field(
            "stop moves",
            f"{monitor.stop_moves} ({monitor.stop_widenings} widened)",
        )
    )
    absences = _absences(
        (
            ("entry", monitor.entry_price),
            ("last price", monitor.last_price),
            ("initial risk", monitor.initial_risk),
            ("realized R", monitor.realized_r),
            ("unrealized R", monitor.unrealized_r),
            ("total R", monitor.total_r),
            ("MFE (R)", monitor.max_favourable_r),
            ("MAE (R)", monitor.max_adverse_r),
            ("next target", monitor.next_target),
            ("distance to stop", monitor.distance_to_stop),
            ("distance to target", monitor.distance_to_target),
            ("holding time", monitor.holding_time),
        )
    )
    if absences:
        lines.append("")
        lines.append(" not stateable:")
        lines.extend(absences)
    return lines


def _warnings_block(view: PaperTradeView) -> list[str]:
    if not view.warnings:
        return []
    lines = _section("WARNINGS")
    for warning in view.warnings:
        lines.extend(_wrap(f"{warning.code}  {warning.text}"))
    return lines


def _outcome_block(view: PaperTradeView) -> list[str]:
    if isinstance(view.outcome, Absent):
        return []
    reading = view.outcome
    lines = _section("OUTCOME")
    lines.append(_field("exit reason", reading.exit_reason))
    lines.append(_field("entry", _value(reading.entry_price)))
    lines.append(_field("exit", _value(reading.exit_price)))
    lines.append(_field("P&L gross", _value(reading.realized_pnl_gross)))
    lines.append(_field("P&L net", _value(reading.realized_pnl_net)))
    lines.append(_field("P&L fraction", _value(reading.pnl_percent)))
    lines.append(_field("final R", _value(reading.final_r)))
    lines.append(
        _field(
            "MFE / MAE (R)",
            f"{_value(reading.max_favourable_r)} / {_value(reading.max_adverse_r)}",
        )
    )
    lines.append(_field("bars held", _value(reading.bars_held)))
    lines.append(_field("holding time", _value(reading.holding_time)))
    lines.append(_field("days held", _value(reading.days_held)))
    lines.append(
        _field(
            "fees",
            ", ".join(str(fee) for fee in reading.fees) or "none recorded",
        )
    )
    lines.extend(_wrap(view.activation.cost_policy.basis))
    return lines


def _header(view: PaperTradeView) -> list[str]:
    activation = view.activation
    lines = [_rule(), f" PAPER TRADE  {activation.market.pair_symbol}", _rule()]
    lines.extend(_token_lines("activation", activation.activation_id))
    lines.extend(_token_lines("plan", activation.plan_id))
    lines.append(_field("market", activation.market.value))
    lines.append(_field("book / account", f"{activation.book.value} / {activation.account}"))
    lines.append(_field("entry", f"{activation.entry_type.value} {_value(activation.entry_price)}"))
    lines.append(_field("size activated", str(activation.quantity)))
    lines.append(_field("interval", activation.interval))
    lines.append(_field("activated at", activation.activated_at.isoformat()))
    lines.append(_field("expires", _value(activation.expires_at)))
    return lines


def render_activation(outcome: ActivationOutcome) -> str:
    """The receipt for one write path: what was written, and whether it was new."""
    lines = [_rule(), f" {outcome.action.upper()}", _rule()]
    lines.extend(_token_lines("activation", outcome.activation.activation_id))
    lines.append(_field("market", outcome.activation.market.value))
    lines.extend(_section("RECORDS"))
    for kind, record_id, created in outcome.written:
        lines.extend(
            _token_lines(kind, f"{record_id} {'(new)' if created else '(already held)'}")
        )
    if not outcome.created_any:
        lines.append("")
        lines.extend(
            _wrap(
                "Nothing was written: every record this command produces was "
                "already in the store, byte for byte. Re-running is an idempotent "
                "success, not a second instruction."
            )
        )
    lines.extend(_limitations())
    return "\n".join(lines)


def render_simulation(report: SimulationReport) -> str:
    """What one `fmits simulate` run advanced, skipped and could not reach."""
    lines = [_rule(), " PAPER SIMULATION", _rule()]
    lines.append(_field("ran at", report.ran_at.isoformat()))
    lines.append(_field("interval", report.interval))
    lines.append(_field("activations", str(len(report.runs))))
    lines.append(_field("advanced", str(report.advanced)))
    if not report.runs:
        lines.append("")
        lines.extend(
            _wrap(
                "No activation in this store is waiting for a bar. `fmits trade "
                "activate` hands a recorded commitment to the simulator."
            )
        )
    for run in report.runs:
        lines.extend(_section(f"{run.market}  →  {run.state.value}"))
        lines.extend(_token_lines("activation", run.activation.activation_id))
        lines.append(_field("bars advanced", str(run.bars_advanced)))
        new = [entry for entry in run.written if entry[2]]
        lines.append(
            _field("records written", f"{len(new)} new of {len(run.written)}")
        )
        for note in run.notes:
            lines.extend(_wrap(note))
    if report.skipped:
        lines.extend(_section("SKIPPED"))
        for activation_id, reason in report.skipped:
            lines.extend(_token_lines("activation", activation_id))
            lines.extend(_wrap(reason))
    if report.unreachable:
        lines.extend(_section("UNREACHABLE"))
        for symbol, reason in report.unreachable:
            lines.extend(_wrap(f"{symbol}: {reason}"))
    if not report.created_any and report.runs:
        lines.append("")
        lines.extend(
            _wrap(
                "Nothing new was written. Every event this run derived was already "
                "in the store, byte for byte — which is what a replay of the same "
                "bars is supposed to produce."
            )
        )
    lines.extend(_limitations())
    return "\n".join(lines)


def render_lifecycle(view: PaperTradeView) -> str:
    """One trade's complete stream: every event, every stop move, the outcome."""
    lines = _header(view)
    lines.extend(_section("LIFECYCLE"))
    lines.append(_field("state", view.state.value))
    lines.append(_field("events applied", str(len(view.lifecycle.applied))))
    lines.append(_field("last event", _value(view.lifecycle.last_event_at)))
    lines.extend(_section("STOP HISTORY"))
    lines.append(
        _field(
            "committed → now",
            f"{canonical_decimal_text(view.stop_history.initial)} → "
            f"{canonical_decimal_text(view.stop_history.effective)}",
        )
    )
    lines.append(
        _field(
            "moves",
            f"{len(view.stop_history.moves)} "
            f"({view.stop_history.tightening_count} tightened, "
            f"{view.stop_history.widening_count} widened)",
        )
    )
    for move in view.stop_history.moves:
        lines.extend(
            _wrap(
                f"{move.at.isoformat()}  {move.arithmetic}  "
                f"{move.reason.qualified_id}  ({move.origin.value})"
            )
        )
    lines.extend(_section("FILLS"))
    if not view.fills:
        lines.extend(_wrap("Nothing has filled against this activation."))
    for entry in view.fills:
        trade = entry.trade
        lines.extend(
            _wrap(
                f"{trade.occurred_at.isoformat()}  {trade.side.value}  "
                f"{trade.quantity}  at {canonical_decimal_text(trade.price)}"
                + ("  (corrected)" if entry.was_corrected else "")
            )
        )
    lines.extend(_monitor_block(view.monitor))
    lines.extend(_outcome_block(view))
    lines.extend(_warnings_block(view))
    lines.extend(_section("BASIS"))
    lines.extend(_wrap(MONITOR_BASIS))
    lines.extend(_limitations())
    return "\n".join(lines)


def render_status(views: tuple[PaperTradeView, ...]) -> str:
    """Every trade the simulator is still running, with its monitoring block."""
    lines = [_rule(), " PAPER TRADE STATUS", _rule()]
    lines.append(_field("open activations", str(len(views))))
    if not views:
        lines.append("")
        lines.extend(
            _wrap(
                "No activation is pending, triggered, open or partially exited. "
                "`fmits trade activate` hands a recorded commitment to the "
                "simulator."
            )
        )
    for view in views:
        lines.extend(_section(f"{view.activation.market.pair_symbol}  →  {view.state.value}"))
        lines.extend(_token_lines("activation", view.activation_id))
        lines.extend(_monitor_block(view.monitor)[3:])
        lines.extend(_warnings_block(view))
    lines.extend(_section("BASIS"))
    lines.extend(_wrap(MONITOR_BASIS))
    lines.extend(_limitations())
    return "\n".join(lines)


def render_history(views: tuple[PaperTradeView, ...]) -> str:
    """Every finished trade, with the outcome frozen when it finished."""
    lines = [_rule(), " PAPER TRADE HISTORY", _rule()]
    lines.append(_field("finished trades", str(len(views))))
    if not views:
        lines.append("")
        lines.extend(
            _wrap(
                "No simulated trade has finished. A trade appears here once its "
                "outcome has been frozen, which happens the moment it closes, "
                "expires, is cancelled or is superseded."
            )
        )
    for view in views:
        lines.extend(_section(f"{view.activation.market.pair_symbol}"))
        lines.extend(_token_lines("activation", view.activation_id))
        lines.append(_field("activated at", view.activation.activated_at.isoformat()))
        lines.extend(_outcome_block(view)[3:])
    lines.extend(_limitations())
    return "\n".join(lines)
