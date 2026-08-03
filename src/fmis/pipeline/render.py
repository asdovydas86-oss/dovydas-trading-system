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
from fmis.market_regime import (
    EvidenceStatus,
    MarketRegime,
    RegimeDimension,
    RegimePolicy,
)
from fmis.pipeline.regime import MultiTimeframeRegime
from fmis.pipeline.multi_timeframe import MultiTimeframeFactSheet, TimeframeView
from fmis.pipeline.structural_facts import StructuralFactSheet

__all__ = ["render_fact_sheet", "render_multi_timeframe_sheet"]

_WIDTH = 66
_ABSENT = "—"

#: Evidence display order. An explicit tuple, never the enum's definition order,
#: so renaming or reordering a member cannot silently reshuffle the page — the
#: same rule `_SIDE_RANK` and `_ROLE_ORDER` follow elsewhere in the repository.
_EVIDENCE_ORDER = (
    EvidenceStatus.CONSISTENT,
    EvidenceStatus.CONFLICTING,
    EvidenceStatus.CONTEXT,
    EvidenceStatus.UNAVAILABLE,
)


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


def _structure_rows(structure) -> list[str]:
    """The latest label, break and change of character, rendered once.

    Shared by `render_fact_sheet` and `_view_block`, which previously carried
    near-identical copies. The duplication was found by an independent review and
    proved by a mutation probe: an anchor matching one copy silently mutated the
    other, reporting a false survivor. One implementation makes that
    unrepresentable.

    Counts are deliberately **not** included. The single-timeframe sheet adds
    "Breaks in window" and "Changes in window" after these rows; the
    multi-timeframe view block omits them to stay readable across three views.
    That is the only difference between the two callers, and it stays at the
    call site rather than becoming a flag on this function.
    """
    rows: list[str] = []
    latest_label = structure.labelled[-1] if structure.labelled else None
    if latest_label is None:
        rows.append(_row("Latest label", _ABSENT, "no labelled swing yet"))
    else:
        rows.append(
            _row(
                "Latest label",
                latest_label.label.value,
                f"@ bar {latest_label.comparison.current.index}",
            )
        )

    latest_break = structure.latest_break
    if latest_break is None:
        rows.append(_row("Break of structure", _ABSENT, "none in this window"))
    else:
        rows.append(
            _row(
                "Break of structure",
                f"{latest_break.side.value} @ bar {latest_break.index}",
                latest_break.timestamp.isoformat(),
            )
        )

    latest_change = structure.latest_change
    if latest_change is None:
        rows.append(_row("Change of character", _ABSENT, "none in this window"))
    else:
        rows.append(
            _row(
                "Change of character",
                f"{latest_change.side.value} @ bar {latest_change.index}",
                latest_change.timestamp.isoformat(),
            )
        )
    return rows


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
            f"confirmation_bars={sheet.detection.right_bars} (carried on each level)",
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
    label_row, break_row, change_row = _structure_rows(structure)
    lines.append(label_row)
    lines.append(break_row)
    lines.append(_row("Breaks in window", str(len(structure.breaks))))
    lines.append(change_row)
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


def _view_block(view: TimeframeView, reference: datetime | None) -> list[str]:
    """One timeframe's compact block: freshness, structure, indicators, levels.

    Compact by design. The single-timeframe sheet is the place to read one
    timeframe exhaustively; this is the place to read three at once, and a
    three-times-full-sheet page is not readable. Nothing is *computed* differently
    — the same fields are read, fewer are shown.
    """
    sheet = view.sheet
    structure = sheet.structure
    near = sheet.nearest_levels
    window = sheet.window
    lines = [_rule(f"{view.role.value.upper()} · {view.interval}")]

    age = _age(sheet.as_of, reference)
    lines.append(_row("As of", sheet.as_of.isoformat(), age or "last closed candle"))
    lines.append(
        _row(
            "Window",
            f"{window.closed_count} closed",
            f"{window.excluded_forming_count} forming excluded",
        )
    )
    lines.append(_row("Last close", _number(window.last_close)))

    lines.append(_row("Structural trend", structure.trend.value))
    lines.extend(_structure_rows(structure))

    for name, result in sheet.features.features.items():
        value = result.value
        if isinstance(value, dict) or hasattr(value, "keys"):
            for key in sorted(value):  # type: ignore[union-attr]
                lines.append(_row(f"{name}.{key}", _number(value[key])))  # type: ignore[index]
            continue
        lines.append(
            _row(name, _number(value), "warming up" if value is None else "")
        )

    above_value, above_note = _level(near.above)
    below_value, below_note = _level(near.below)
    lines.append(
        _row(
            "Levels",
            str(len(structure.levels)),
            f"{near.upper_count} upper, {near.lower_count} lower",
        )
    )
    lines.append(_row("Nearest above close", above_value, above_note))
    lines.append(_row("Nearest below close", below_value, below_note))
    return lines


def render_multi_timeframe_sheet(
    sheet: MultiTimeframeFactSheet, *, reference_time: datetime | None = None
) -> str:
    """Render several role-labelled timeframe views as one plain-text page.

    Args:
        sheet: the multi-timeframe sheet to render.
        reference_time: instant to measure each view's age against. Omitted by
            default, because a renderer that read the clock would make its output
            non-reproducible.

    Returns:
        A newline-joined report: a header, one block per view in role order, a
        side-by-side structural-trend summary, and the limitations.

    **The trend summary restates, it does not synthesise.** It lists each view's
    trend beside its role and derives nothing from the combination — no agreement
    flag, no count of matches, no verdict. Reconciling timeframes that disagree is
    a later layer's decision, and pre-empting it here would be an interpretation
    in the one layer that must not hold any.
    """
    lines: list[str] = []
    lines.append(_rule())
    lines.append(" FMITS MULTI-TIMEFRAME FACT SHEET — deterministic facts only")
    lines.append(_rule())
    lines.append(_row("Asset", sheet.symbol))
    lines.append(_row("Exchange / source", sheet.source))
    lines.append(
        _row("Timeframes", " · ".join(sheet.intervals), f"{len(sheet.views)} views")
    )
    lines.append(
        _row("Newest data", sheet.newest_as_of.isoformat(), "not a shared instant")
    )

    for view in sheet.views:
        lines.append("")
        lines.extend(_view_block(view, reference_time))

    lines.append("")
    lines.append(_rule("STRUCTURAL TREND BY ROLE"))
    for view in sheet.views:
        lines.append(
            _row(
                f"{view.role.value} · {view.interval}",
                view.sheet.structure.trend.value,
            )
        )
    lines.append(" Reported side by side. Nothing is derived from the combination.")

    lines.append("")
    lines.append(_rule("LIMITATIONS OF THESE FACTS"))
    for limitation in sheet.limitations:
        head = f" [{limitation.code}] "
        lines.extend(
            textwrap.wrap(
                limitation.text,
                width=_WIDTH,
                initial_indent=head,
                subsequent_indent=" " * len(head),
            )
        )

    lines.append("")
    lines.append(_rule())
    lines.append(
        " These are measurements, not conclusions. No direction, ranking or"
    )
    lines.append(" recommendation is expressed or implied.")
    lines.append(_rule())
    return "\n".join(lines)


def _evidence_lines(dimension: RegimeDimension) -> list[str]:
    """One indented line per evidence item, grouped by status in a fixed order.

    The order is consistent → conflicting → context → unavailable, from an
    explicit tuple rather than the enum's definition order, so renaming or
    reordering a member cannot silently reshuffle the page.

    Every item is printed. A renderer that showed only the evidence agreeing with
    the state would be the opposite of what `ARCH` §9 asked for, and would make a
    classification look better supported than it is.
    """
    lines: list[str] = []
    for status in _EVIDENCE_ORDER:
        for item in dimension.evidence:
            if item.status is not status:
                continue
            value = "" if item.value is None else _number(item.value)
            lines.append(
                _row(f"   {status.value}", item.observed, f"{item.source} {value}".strip())
            )
    return lines


def _regime_block(regime: MarketRegime, heading: str) -> list[str]:
    """One regime as a titled block: each dimension, its state, and its evidence."""
    lines = [_rule(heading)]
    lines.append(_row("As of", regime.as_of.isoformat(), "last closed candle"))
    for dimension in regime.dimensions:
        lines.append("")
        lines.append(_row(dimension.name.value, dimension.state.value))
        lines.extend(_evidence_lines(dimension))
        if dimension.reason is not None:
            lines.extend(
                textwrap.wrap(
                    dimension.reason,
                    width=_WIDTH,
                    initial_indent="   why: ",
                    subsequent_indent="        ",
                )
            )
    return lines


def render_regime_sheet(
    regime: MarketRegime, *, limitations: tuple[Limitation, ...] = ()
) -> str:
    """Render one timeframe's regime as a plain-text page.

    Shows every dimension, every piece of evidence behind it including the
    evidence that conflicts and the evidence that was unavailable, the reason a
    dimension declined to classify, and the exact policy that produced the
    result. A regime without its thresholds is not reproducible, which is the
    objection `ARCH` §9 raises against a regime call buried in a prompt.

    There is no overall line and no score, because there is no overall state and
    no score to print.
    """
    lines: list[str] = []
    lines.append(_rule())
    lines.append(" FMITS MARKET REGIME — the environment, not a direction")
    lines.append(_rule())
    lines.append(_row("Asset", regime.symbol))
    lines.append(_row("Timeframe", regime.timeframe))
    lines.extend(_regime_block(regime, "REGIME BY DIMENSION"))
    lines.append("")
    lines.extend(_policy_lines(regime.policy))
    if limitations:
        lines.append("")
        lines.extend(_limitation_lines(limitations))
    lines.append("")
    lines.extend(_regime_closing())
    return "\n".join(lines)


def _policy_lines(policy: RegimePolicy) -> list[str]:
    """The exact parameters used, so the classification can be reproduced."""
    lines = [_rule("POLICY THAT PRODUCED THIS")]
    for name, value in policy.describe():
        lines.append(_row(name, value))
    return lines


def _limitation_lines(limitations: tuple[Limitation, ...]) -> list[str]:
    """The shared limitations block, wrapped exactly as the fact sheets wrap it."""
    lines = [_rule("LIMITATIONS OF THIS CLASSIFICATION")]
    for limitation in limitations:
        head = f" [{limitation.code}] "
        lines.extend(
            textwrap.wrap(
                limitation.text,
                width=_WIDTH,
                initial_indent=head,
                subsequent_indent=" " * len(head),
            )
        )
    return lines


def _regime_closing() -> list[str]:
    """The closing disclaimer, worded for a classification rather than a measurement."""
    return [
        _rule(),
        " A regime describes the environment. It is not a direction, a ranking or",
        " a recommendation, and none is expressed or implied.",
        _rule(),
    ]


def render_multi_timeframe_regime(sheet: MultiTimeframeRegime) -> str:
    """Render one regime per role, side by side, with nothing derived from the set."""
    lines: list[str] = []
    lines.append(_rule())
    lines.append(" FMITS MULTI-TIMEFRAME REGIME — the environment, not a direction")
    lines.append(_rule())
    lines.append(_row("Asset", sheet.symbol))
    lines.append(_row("Exchange / source", sheet.source))
    lines.append(
        _row("Newest data", sheet.newest_as_of.isoformat(), "not a shared instant")
    )
    for view in sheet.views:
        lines.append("")
        lines.extend(
            _regime_block(
                view.regime, f"{view.role.value.upper()} · {view.interval}"
            )
        )
    lines.append("")
    lines.append(_rule("REGIME BY ROLE"))
    for view in sheet.views:
        states = " · ".join(d.state.value for d in view.regime.dimensions)
        lines.append(_row(f"{view.role.value} · {view.interval}", states))
    lines.append(" Reported side by side. Nothing is derived from the combination.")
    lines.append("")
    lines.extend(_policy_lines(sheet.policy))
    lines.append("")
    lines.extend(_limitation_lines(sheet.limitations))
    lines.append("")
    lines.extend(_regime_closing())
    return "\n".join(lines)
