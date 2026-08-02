"""Plain-text rendering of a `StructuralFactSheet`.

Presentation only. This module formats numbers that already exist; it computes
no market quantity, derives no fact, and reaches no engine. The one thing it
calculates is **data age**, which is a property of the *reading*, not of the
market: it requires a reference instant that the sheet deliberately does not
carry, because a sheet must stay a pure function of its candles.

**Fact-only vocabulary is a rendering obligation too.** Nothing here emits buy,
sell, long, short, bullish, bearish, strong, weak, support, resistance, or any
other word that reads as a conclusion. A `PriceLevel` above the close is printed
as "nearest above", never as resistance — the distinction ADR-0019 §I draws
between a fact and a reading survives all the way to the terminal, or it was
never really enforced.

Absent values print as an em dash with a stated reason, never as a blank or a
zero: "not computed yet" and "computed to be nothing" must not look alike.
"""

from __future__ import annotations

import textwrap
from datetime import datetime

from fmis.level_crossing import PriceLevel
from fmis.pipeline.structural_facts import StructuralFactSheet

__all__ = ["render_fact_sheet"]

_WIDTH = 66
_ABSENT = "—"


def _rule(title: str = "") -> str:
    if not title:
        return "═" * _WIDTH
    return f"── {title} " + "─" * max(_WIDTH - len(title) - 4, 0)


def _row(label: str, value: str, note: str = "") -> str:
    line = f" {label:<30}{value:>14}"
    return f"{line}   {note}" if note else line


def _number(value: object) -> str:
    """Format a numeric feature value; anything non-numeric prints via ``repr``."""
    if value is None:
        return _ABSENT
    if isinstance(value, bool):
        return repr(value)
    if isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return str(value)


def _level(level: PriceLevel | None) -> tuple[str, str]:
    """A level as (price, provenance note), or absent."""
    if level is None:
        return _ABSENT, ""
    origin = level.origin
    if origin is None:
        return _number(level.price), f"{level.side.value} · no origin"
    return (
        _number(level.price),
        f"{level.side.value} · {origin.label.value} @ bar {origin.index}",
    )


def _age(as_of: datetime, reference: datetime | None) -> str:
    """Human age of the newest closed candle, relative to an injected instant."""
    if reference is None:
        return ""
    delta = reference - as_of
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "reference precedes the data"
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours:
        return f"age {hours}h {minutes:02d}m"
    return f"age {minutes}m"


def render_fact_sheet(
    sheet: StructuralFactSheet, *, reference_time: datetime | None = None
) -> str:
    """Render one fact sheet as plain text.

    Args:
        sheet: the sheet to render.
        reference_time: instant to measure data age against. Omitted by default,
            because a renderer that read the clock on its own would make its
            output non-reproducible. The caller at the edge supplies it.

    Returns:
        A newline-joined report. Deterministic for a given sheet and reference.
    """
    structure = sheet.structure
    near = sheet.nearest_levels
    window = sheet.window
    lines: list[str] = []

    lines.append(_rule())
    lines.append(" FMITS STRUCTURAL FACT SHEET — deterministic facts only")
    lines.append(_rule())
    lines.append(_row("Asset", sheet.symbol))
    lines.append(_row("Exchange / source", sheet.source))
    lines.append(_row("Timeframe", sheet.interval))
    lines.append(_row("As of", sheet.as_of.isoformat(), "last closed candle"))
    freshness = _age(sheet.as_of, reference_time)
    if freshness:
        lines.append(_row("Data freshness", freshness))
    lines.append(
        _row(
            "Window",
            f"{window.closed_count} closed / {window.fetched_count} fetched",
            f"{window.excluded_forming_count} forming excluded",
        )
    )
    lines.append(
        _row(
            "Detection",
            f"L{sheet.detection.left_bars} R{sheet.detection.right_bars}",
            f"confirmation_bars={sheet.detection.right_bars} (single source)",
        )
    )
    lines.append(_row("Last close", _number(window.last_close)))

    lines.append("")
    lines.append(_rule("INDICATORS"))
    for name, result in sheet.features.features.items():
        value = result.value
        if isinstance(value, dict) or hasattr(value, "keys"):
            for key in sorted(value):  # type: ignore[union-attr]
                lines.append(_row(f"{name}.{key}", _number(value[key])))  # type: ignore[index]
            continue
        note = "warming up" if value is None else ""
        lines.append(_row(name, _number(value), note))

    lines.append("")
    lines.append(_rule("MARKET STRUCTURE"))
    unlabelled = len(structure.swings) - len(structure.labelled)
    lines.append(
        _row(
            "Swing points",
            str(len(structure.swings)),
            f"{len(structure.labelled)} labelled, {unlabelled} without a label",
        )
    )
    lines.append(_row("Structural trend", structure.trend.value))
    latest_label = (
        structure.labelled[-1] if structure.labelled else None
    )
    if latest_label is not None:
        lines.append(
            _row(
                "Latest label",
                latest_label.label.value,
                f"@ bar {latest_label.comparison.current.index}",
            )
        )
    else:
        lines.append(_row("Latest label", _ABSENT, "no labelled swing yet"))

    latest_break = structure.latest_break
    if latest_break is None:
        lines.append(_row("Break of structure", _ABSENT, "none in this window"))
    else:
        lines.append(
            _row(
                "Break of structure",
                f"{latest_break.side.value} @ bar {latest_break.index}",
                latest_break.timestamp.isoformat(),
            )
        )
    lines.append(_row("Breaks in window", str(len(structure.breaks))))

    latest_change = structure.latest_change
    if latest_change is None:
        lines.append(_row("Change of character", _ABSENT, "none in this window"))
    else:
        lines.append(
            _row(
                "Change of character",
                f"{latest_change.side.value} @ bar {latest_change.index}",
                latest_change.timestamp.isoformat(),
            )
        )
    lines.append(_row("Changes in window", str(len(structure.changes))))

    lines.append("")
    lines.append(_rule("STRUCTURAL LEVELS"))
    lines.append(
        _row(
            "Levels",
            str(len(structure.levels)),
            f"{near.upper_count} upper, {near.lower_count} lower",
        )
    )
    above_value, above_note = _level(near.above)
    below_value, below_note = _level(near.below)
    lines.append(_row("Nearest above close", above_value, above_note))
    lines.append(_row("Nearest below close", below_value, below_note))
    lines.append(_row("Crossing events", str(len(structure.crossings))))

    lines.append("")
    lines.append(_rule("WARM-UP"))
    total = len(sheet.features.features)
    if sheet.warming_up:
        lines.append(
            _row("Features warming up", f"{len(sheet.warming_up)} of {total}")
        )
        for name in sheet.warming_up:
            lines.append(f"   · {name}")
    else:
        lines.append(_row("Features warming up", f"0 of {total}", "all ready"))

    lines.append("")
    lines.append(_rule("LIMITATIONS OF THESE FACTS"))
    for limitation in sheet.limitations:
        head = f" [{limitation.code}] "
        wrapped = textwrap.wrap(
            limitation.text,
            width=_WIDTH,
            initial_indent=head,
            subsequent_indent=" " * len(head),
        )
        lines.extend(wrapped)

    lines.append("")
    lines.append(_rule())
    lines.append(
        " These are measurements, not conclusions. No direction, ranking or"
    )
    lines.append(" recommendation is expressed or implied.")
    lines.append(_rule())
    return "\n".join(lines)
