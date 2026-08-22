"""Rendering a `MarketPulse` as a terminal page.

**This module only renders.** It computes nothing, decides nothing, reorders
nothing and hides nothing. Guard tests assert it calls no builder and no engine,
holds no floating-point literal, and multiplies only strings.

**The information hierarchy is the design, and it is ordered by what a reader
needs first.** Scope before facts, facts before comparisons, comparisons before
caveats:

    1. WHAT THIS PAGE IS  — the orientation note, so the page cannot be
       mistaken for a recommendation before a single number is read.
    2. MARKET MOVES       — every read market, one row each, all horizons.
    3. RELATIVE ORDERING  — the same numbers ordered, with the quantity named.
    4. VOLATILITY         — measured, and explicitly unclassified.
    5. CROSS-ASSET        — co-movement against one named reference.
    6. NOT AVAILABLE      — every market that produced nothing, and why.
    7. DATA QUALITY       — provenance, ages, limitations, staleness policy.

**Absence is printed, never omitted.** A market that could not be read gets a
row with its reason; a horizon that could not be measured prints the reason in
place of the number. There is no short form and nothing is dropped for being
empty, because an omitted absence reads as a reassuring one.

**Percent is formatted here and only here.** Moves are carried as fractions
everywhere else, so no intermediate value can be scaled twice. The multiplier
lives in `fmis.market_pulse.render`'s own constant and is applied at the moment
of printing.

**78 columns, ASCII structure, no colour.** The same width `fmis.swing_workspace`
uses, so the two pages sit in one terminal without either reflowing. Every rule
and separator is `=` or `-`; a reason composed elsewhere is printed exactly as
composed, wrapped rather than truncated. Nothing depends on a terminal's
colours, so the page survives a pipe, a log file and a reader who cannot
distinguish them.

**No directional or interpretive vocabulary is written here.** The page says a
market's measured move and never what it means. `LEADERS`/`LAGGARDS` name
positions in a stated ordering — the highest and lowest of one measured number —
and are printed beside that number, never alone.
"""

from __future__ import annotations

import textwrap
from datetime import timedelta

from fmis.market_pulse.models import (
    CO_MOVEMENT_CAVEAT,
    PULSE_ORIENTATION_NOTE,
    SCHEDULE_LIMITATION,
    VOLATILITY_CLASSIFICATION_NOTE,
    CoMovement,
    Horizon,
    HorizonMove,
    HorizonRanking,
    MarketPulse,
    MarketReading,
)
from fmis.market_pulse.pulse import EXCLUDED_FROM_ORDERING, ORDERING_UNIT_SCOPE

__all__ = ["PULSE_PAGE_WIDTH", "NO_STALENESS_BOUND", "render_market_pulse"]

#: The page width. Named with the package's own prefix because
#: `fmis.swing_workspace` already exports `WORKSPACE_PAGE_WIDTH` and
#: `fmis.setup_evidence` a bare `PAGE_WIDTH`; this repository holds zero export
#: collisions by rule, and a guard test is what enforces it.
PULSE_PAGE_WIDTH = 78

#: What the page prints when the owner configured no staleness bound.
#:
#: **The bound is the owner's, and this package chooses none.**
#: `fmis.position_sizing.SizingPolicy` records the rule this follows: an age
#: judged against a number this build picked would be a threshold invented at
#: exactly the point the specification says not to. So an age is always
#: reported, and *"stale"* is only ever said against a bound that was supplied.
NO_STALENESS_BOUND = (
    "No staleness bound is configured, so no reading below is called stale. "
    "Every age is stated and judged by you. Pass --max-age to have this page "
    "mark readings older than a duration you choose."
)

_PERCENT_SCALE = 100
_INDENT = "  "
_ABSENT = "not available"


def _rule(char: str) -> str:
    return char * PULSE_PAGE_WIDTH


def _heading(title: str) -> list[str]:
    return ["", title, _rule("-")]


def _wrap(text: str, *, indent: str = "") -> list[str]:
    """One paragraph, wrapped to the page width.

    `textwrap` breaks a word longer than the width rather than overflowing, so
    an unbreakable identifier is chopped instead of pushing a line past column
    78. Every caller passes non-empty text — each is a label, a sentence or a
    value a model has already refused to leave blank — so there is no
    empty-result case to handle here.
    """
    return textwrap.wrap(
        text,
        width=PULSE_PAGE_WIDTH,
        initial_indent=indent,
        subsequent_indent=indent,
    )


def _label_and_body(label: str, body: str, *, indent: str = _INDENT) -> list[str]:
    """``label: body``, hanging-indented when it does not fit on one line.

    The continuation sits one level deeper than the label, so a wrapped reason
    is visibly part of the row above it rather than a new row. Never truncated:
    a provider's error, a market's display name and a filesystem path are all
    values this page has no right to shorten — a reason cut off at column 78 is
    a reason the owner cannot act on.
    """
    return textwrap.wrap(
        f"{label}: {body}",
        width=PULSE_PAGE_WIDTH,
        initial_indent=indent,
        subsequent_indent=indent + _INDENT,
    )


def _bars(count: int) -> str:
    """``1 bar`` / ``24 bars``. Grammar, stated once."""
    return f"{count} bar" if count == 1 else f"{count} bars"


def _percent(fraction: float) -> str:
    """A fraction rendered as a signed percentage with two decimals.

    The one place a move is scaled. `+0.00%` and `-0.00%` are both possible and
    both honest: they say the move was measured and rounds to zero at this
    precision, which is a different statement from `not available`.
    """
    return f"{fraction * _PERCENT_SCALE:+.2f}%"


def _plain(value: float) -> str:
    """A unitless number — a volatility or a correlation — at four decimals."""
    return f"{value:.4f}"


def _duration(span: timedelta) -> str:
    """A duration in the standard library's own form, to whole seconds.

    `str(timedelta)` rather than a hand-rolled hours-and-minutes formatter, for
    two reasons: it is the spelling `fmis.position_sizing.policy` already writes
    a duration with, so a bound printed there and an age printed here read the
    same; and it keeps every division out of a module whose contract is that it
    computes nothing.

    **Sub-second precision is dropped, and the direction is checked.** A default
    run takes `as_of` from the wall clock, so every age would otherwise carry
    six digits of microseconds on every row — noise on a page that has to be
    readable in half a minute. Truncating shortens a stated age by under one
    second; the bar-open timestamping already *lengthens* it by up to a full
    interval, so the figure remains overstated overall and the page's own claim
    — never understated — still holds. `fmis.pipeline.render` truncates the same
    way for the same reason.
    """
    return str(timedelta(seconds=int(span.total_seconds())))


def _horizon_label(
    horizon: Horizon, *, wall_clock: bool, move: HorizonMove | None = None
) -> str:
    """How a horizon is named on a row. Elapsed time is claimed only when true.

    **Two conditions, and both are necessary.** The market must trade
    continuously — a schedule nobody established is not a schedule that happens
    to be 24/7 — *and* the window this move actually spanned must equal the
    duration the phrase asserts. The second is what stops the page printing
    *"168_bars (7 days)"* over a window that really covered eleven days because
    the provider omitted bars for maintenance. A `CandleSeries` permits forward
    gaps, so this is a live possibility rather than a theoretical one.

    When either condition fails the horizon is named by its bar count, which is
    true of every market under every schedule with every gap.
    """
    if (
        wall_clock
        and horizon.wall_clock_equivalent is not None
        and move is not None
        and move.measured_span == horizon.wall_clock_span
    ):
        return f"{horizon.horizon_id} ({horizon.wall_clock_equivalent})"
    return f"{horizon.horizon_id} ({_bars(horizon.bars)})"


# ------------------------------------------------------------------ sections ---


def _header(pulse: MarketPulse) -> list[str]:
    lines = [_rule("="), "GLOBAL MARKET PULSE", _rule("=")]
    lines.extend(
        _label_and_body("as of", pulse.as_of.isoformat(), indent="")
    )
    lines.extend(
        _label_and_body("universe", pulse.universe.name, indent="")
    )
    lines.extend(
        _label_and_body(
            "scope",
            f"{pulse.read_count} market(s) read · "
            f"{len(pulse.unavailable)} provider failure(s) · "
            f"{pulse.unsupported_count} market(s) with no configured provider",
            indent="",
        )
    )
    lines.append("")
    lines.extend(_wrap(PULSE_ORIENTATION_NOTE))
    return lines


def _moves_section(pulse: MarketPulse) -> list[str]:
    lines = _heading("MARKET MOVES")
    if pulse.is_empty:
        lines.extend(
            _wrap(
                "No market could be read. This is a statement about this run, "
                "not about the markets: nothing below should be read as calm, "
                "quiet or unchanged.",
                indent=_INDENT,
            )
        )
        return lines
    for reading in pulse.readings:
        lines.append("")
        lines.extend(
            _wrap(
                f"{reading.benchmark.display_name}  [{reading.benchmark_id}]",
                indent="",
            )
        )
        wall_clock = reading.benchmark.claims_wall_clock_horizons
        for horizon in pulse.horizons:
            move = reading.move_for(horizon.horizon_id)
            label = _horizon_label(horizon, wall_clock=wall_clock, move=move)
            if move is None:
                lines.extend(_label_and_body(label, "not measured on this run"))
            elif move.is_measured:
                lines.extend(_label_and_body(label, _percent(move.value)))
            else:
                lines.extend(_label_and_body(label, move.unavailable_reason))
        lines.extend(
            _label_and_body(
                "measured from",
                f"{reading.provenance} · age "
                f"{_duration(reading.age_at(pulse.as_of))}",
            )
        )
        lines.extend(
            _label_and_body(
                "market",
                f"{reading.benchmark.category.value} · "
                f"{reading.benchmark.schedule.value}",
            )
        )
    return lines


def _ranking_block(ranking: HorizonRanking, horizon: Horizon) -> list[str]:
    lines = [""]
    lines.extend(
        _wrap(
            f"{horizon.horizon_id} ({_bars(horizon.bars)}) · "
            f"denominated in {ranking.quote_unit}",
            indent="",
        )
    )
    if ranking.is_empty:
        lines.extend(
            _wrap("no market in this unit could be ordered", indent=_INDENT)
        )
    else:
        for position, row in enumerate(ranking.ordered, start=1):
            lines.extend(
                _wrap(
                    f"{position}. {_percent(row.value)}  {row.display_name} "
                    f"[{row.benchmark_id}]",
                    indent=_INDENT,
                )
            )
        leader = ranking.leader
        laggard = ranking.laggard
        if leader is not None and laggard is not None and leader is not laggard:
            lines.extend(
                _label_and_body(
                    "highest measured move", f"{leader.benchmark_id} "
                    f"{_percent(leader.value)}"
                )
            )
            lines.extend(
                _label_and_body(
                    "lowest measured move", f"{laggard.benchmark_id} "
                    f"{_percent(laggard.value)}"
                )
            )
    for benchmark_id, reason in ranking.excluded:
        lines.extend(_label_and_body(f"not ordered · {benchmark_id}", reason))
    return lines


def _ordering_section(pulse: MarketPulse) -> list[str]:
    lines = _heading("RELATIVE ORDERING")
    lines.extend(_wrap(ORDERING_UNIT_SCOPE, indent=_INDENT))
    if not pulse.rankings:
        lines.append("")
        lines.extend(
            _wrap(
                "No ordering was produced: no configured market could be read.",
                indent=_INDENT,
            )
        )
        return lines
    by_id = {horizon.horizon_id: horizon for horizon in pulse.horizons}
    for ranking in pulse.rankings:
        lines.extend(_ranking_block(ranking, by_id[ranking.horizon_id]))
    lines.append("")
    lines.extend(
        _label_and_body("ordered by", pulse.rankings[0].ordering_quantity, indent="")
    )
    lines.extend(_wrap("not part of any ordering above:", indent=""))
    for quantity in EXCLUDED_FROM_ORDERING:
        lines.extend(_wrap(f"· {quantity}", indent=_INDENT))
    return lines


def _volatility_section(pulse: MarketPulse) -> list[str]:
    lines = _heading("VOLATILITY")
    lines.extend(_wrap(VOLATILITY_CLASSIFICATION_NOTE, indent=_INDENT))
    lines.append("")
    if pulse.is_empty:
        lines.extend(_wrap("no market could be read", indent=_INDENT))
        return lines
    for reading in pulse.readings:
        volatility = reading.volatility
        body = (
            _plain(volatility.value)
            if volatility.is_measured
            else volatility.unavailable_reason
        )
        lines.extend(_label_and_body(reading.benchmark_id, body))
        if volatility.is_measured:
            lines.extend(
                _label_and_body(
                    "measured by",
                    f"{volatility.metric} over "
                    f"{_bars(volatility.observation_count)}, "
                    f"{volatility.window_start.isoformat()} to "
                    f"{volatility.window_end.isoformat()}",
                    indent=_INDENT + _INDENT,
                )
            )
    return lines


def _co_movement_row(movement: CoMovement) -> list[str]:
    if movement.is_measured:
        body = (
            f"{_plain(movement.value)} over {_bars(movement.observation_count)}, "
            f"{movement.window_start.isoformat()} to "
            f"{movement.window_end.isoformat()}"
        )
    else:
        body = movement.unavailable_reason
    return _label_and_body(movement.subject_id, body)


def _cross_asset_section(pulse: MarketPulse) -> list[str]:
    lines = _heading("CROSS-ASSET")
    lines.extend(_wrap(CO_MOVEMENT_CAVEAT, indent=_INDENT))
    lines.append("")
    if pulse.co_movement_reference is None:
        lines.extend(
            _wrap(
                "No co-movement was measured: this run established no reference "
                "market to measure one against.",
                indent=_INDENT,
            )
        )
        return lines
    lines.extend(
        _label_and_body(
            "measured against", pulse.co_movement_reference, indent=_INDENT
        )
    )
    lines.append("")
    for movement in pulse.co_movements:
        lines.extend(_co_movement_row(movement))
    return lines


def _absent_section(pulse: MarketPulse) -> list[str]:
    lines = _heading("NOT AVAILABLE")
    if not pulse.unavailable and not pulse.universe.unsupported:
        lines.extend(
            _wrap(
                "Every market in this universe was read. No reading is missing "
                "from this page.",
                indent=_INDENT,
            )
        )
        return lines
    if pulse.unavailable:
        lines.extend(
            _wrap("asked for and not delivered — a provider failure:", indent="")
        )
        for entry in pulse.unavailable:
            lines.extend(
                _label_and_body(
                    f"{entry.benchmark.display_name} [{entry.benchmark_id}]",
                    entry.reason,
                )
            )
        lines.append("")
    if pulse.universe.unsupported:
        lines.extend(
            _wrap("never asked for — no provider is configured:", indent="")
        )
        for benchmark in pulse.universe.unsupported:
            lines.extend(
                _label_and_body(
                    f"{benchmark.display_name} [{benchmark.benchmark_id}] "
                    f"· {benchmark.category.value}",
                    benchmark.unsupported_reason,
                )
            )
    return lines


def _data_quality_section(
    pulse: MarketPulse, *, max_age: timedelta | None
) -> list[str]:
    lines = _heading("DATA QUALITY")
    oldest = pulse.oldest_reading()
    if oldest is None:
        lines.extend(
            _label_and_body(
                "freshness", "no reading was produced, so there is no age to state"
            )
        )
    else:
        lines.extend(
            _label_and_body(
                "oldest reading",
                f"{oldest.benchmark_id} · bar opened "
                f"{oldest.last_bar_open.isoformat()} · age "
                f"{_duration(oldest.age_at(pulse.as_of))}",
            )
        )
        lines.extend(
            _wrap(
                "This page is only as current as that reading. Every age is "
                "measured to the instant its bar opened, not closed, so an age "
                "is overstated by up to one interval and is never understated.",
                indent=_INDENT,
            )
        )
    lines.append("")
    if max_age is None:
        lines.extend(_wrap(NO_STALENESS_BOUND, indent=_INDENT))
    else:
        lines.extend(
            _label_and_body("staleness bound", f"{_duration(max_age)} (yours)")
        )
        overdue = [
            reading
            for reading in pulse.readings
            if reading.age_at(pulse.as_of) > max_age
        ]
        if overdue:
            for reading in overdue:
                lines.extend(
                    _label_and_body(
                        f"stale · {reading.benchmark_id}",
                        f"age {_duration(reading.age_at(pulse.as_of))} exceeds "
                        f"the bound you set",
                        indent=_INDENT + _INDENT,
                    )
                )
        else:
            lines.extend(
                _wrap("no reading exceeds it", indent=_INDENT + _INDENT)
            )
    lines.append("")
    lines.extend(_wrap(SCHEDULE_LIMITATION, indent=_INDENT))
    return lines


def render_market_pulse(
    pulse: MarketPulse, *, max_age: timedelta | None = None
) -> str:
    """The whole page as one string, with no trailing newline.

    Args:
        pulse: the assembled orientation. Every figure printed is read from it;
            none is computed here.
        max_age: the owner's staleness bound, or `None`. With no bound, ages are
            stated and nothing is called stale — see `NO_STALENESS_BOUND`.

    Raises:
        TypeError: ``pulse`` is not a `MarketPulse`.
        ValueError: a rendered line exceeds the page width. A defensive check
            rather than a reachable one: every section wraps, so a line over the
            limit means a value was interpolated without passing through `_wrap`.
    """
    if not isinstance(pulse, MarketPulse):
        raise TypeError(f"pulse must be a MarketPulse, got {type(pulse).__name__}")
    if max_age is not None:
        if not isinstance(max_age, timedelta):
            raise TypeError(
                f"max_age must be a timedelta or None, got {type(max_age).__name__}"
            )
        if max_age <= timedelta(0):
            raise ValueError(
                f"max_age must be positive, got {max_age}; a non-positive bound "
                "marks every reading stale, including one taken this second"
            )
    lines: list[str] = []
    lines.extend(_header(pulse))
    lines.extend(_moves_section(pulse))
    lines.extend(_ordering_section(pulse))
    lines.extend(_volatility_section(pulse))
    lines.extend(_cross_asset_section(pulse))
    lines.extend(_absent_section(pulse))
    lines.extend(_data_quality_section(pulse, max_age=max_age))
    for line in lines:
        if len(line) > PULSE_PAGE_WIDTH:
            raise ValueError(
                f"rendered line of {len(line)} exceeds the {PULSE_PAGE_WIDTH}-"
                f"column page width: {line!r}"
            )
    return "\n".join(lines)
