"""Rendering a `MacroContextReport` as a terminal page.

The page answers, in order, the questions the owner opens it to ask:

    1. WHAT THIS PAGE IS   — the orientation note, so the page cannot be
                             mistaken for a market view.
    2. LEVELS              — where each market is, with its unit.
    3. MOVES               — what each price-like market did, per horizon.
    4. RATES               — what the yields did, in basis points.
    5. VOLATILITY          — measured, and deliberately unclassified.
    6. CROSS-ASSET         — correlations, and every refused comparison.
    7. DATA QUALITY        — provenance, ages, freshness, limitations.
    8. UNAVAILABLE         — every market this build cannot see, and why.

**Structure follows `fmis.market_pulse.render` deliberately.** Same width, same
rules, same hanging indents, so a macro page and a pulse page sit in one terminal
without either reflowing and a reader learns one layout. The width constant is
shared rather than re-declared, because two page widths that are equal today and
independently editable tomorrow are a divergence waiting to happen.

**No directional or interpretive vocabulary is written here.** The page says a
yield rose ten basis points; it does not say rates are rising, that the move was
large, or what it implies for anything. Absences are printed as sentences, and
every number is printed beside the unit and window that make it mean something.

**The one arithmetic operation is the percent scale**, applied once at the moment
of printing, exactly as the pulse renderer does it. A basis-point figure arrives
already in basis points — `fmis.macro.rates` owns that scale — so this module
never converts a rate.
"""

from __future__ import annotations

import textwrap
from datetime import timedelta

from fmis.macro.comparability import (
    COMPARABILITY_RULE,
    CORRELATION_COMPARABILITY_RULE,
)
from fmis.macro.models import (
    MACRO_FRESHNESS_NOTE,
    MACRO_ORIENTATION_NOTE,
    MACRO_RATE_NOTE,
    MACRO_RELATIONSHIP_CAVEAT,
    MACRO_SESSION_LIMITATION,
    CrossAssetRelationship,
    MacroContextReport,
    MacroLevel,
    RateFact,
)
from fmis.macro.rates import RateChange
from fmis.market_pulse import (
    VOLATILITY_CLASSIFICATION_NOTE,
    FreshnessState,
    Horizon,
    MarketReading,
    PULSE_PAGE_WIDTH,
)

__all__ = ["MACRO_PAGE_WIDTH", "render_macro_context"]

#: The page width, taken from the pulse renderer rather than re-declared. The two
#: pages are read in one terminal and must not disagree; a second literal would
#: be a divergence the day one of them was tuned.
MACRO_PAGE_WIDTH = PULSE_PAGE_WIDTH

_PERCENT_SCALE = 100
_INDENT = "  "
_ABSENT = "not available"


def _rule(char: str) -> str:
    return char * MACRO_PAGE_WIDTH


def _heading(title: str) -> list[str]:
    return ["", title, _rule("-")]


def _wrap(text: str, *, indent: str = "") -> list[str]:
    """One paragraph, wrapped to the page width."""
    return textwrap.wrap(
        text,
        width=MACRO_PAGE_WIDTH,
        initial_indent=indent,
        subsequent_indent=indent,
    )


def _label_and_body(label: str, body: str, *, indent: str = _INDENT) -> list[str]:
    """``label: body``, hanging-indented when it does not fit on one line.

    Never truncated, for the reason `fmis.market_pulse.render` records: a
    provider's error or a market's name cut off at column 78 is a value the owner
    cannot act on.
    """
    return textwrap.wrap(
        f"{label}: {body}",
        width=MACRO_PAGE_WIDTH,
        initial_indent=indent,
        subsequent_indent=indent + _INDENT,
    )


def _observations(count: int) -> str:
    """``1 observation`` / ``21 observations``. Grammar, stated once."""
    return f"{count} observation" if count == 1 else f"{count} observations"


def _percent(fraction: float) -> str:
    """A fraction rendered as a signed percentage with two decimals.

    The one place a move is scaled on this page.
    """
    return f"{fraction * _PERCENT_SCALE:+.2f}%"


def _basis_points(value: float) -> str:
    """A signed basis-point figure at one decimal place.

    **One decimal, not two.** A Treasury yield is published to two decimal places
    in percent, so its basis-point difference is exact to whole basis points and
    a tenth is already past the precision of the input. The tenth is kept only so
    that a genuinely sub-basis-point move reads as `+0.4 bp` rather than
    rounding to a flat `+0 bp` that looks like no move at all.
    """
    return f"{value:+.1f} bp"


def _plain(value: float) -> str:
    """A unitless number — a volatility or a correlation — at four decimals."""
    return f"{value:.4f}"


def _level_value(level: MacroLevel) -> str:
    """A level at four decimals, which every unit on this page survives.

    The broad dollar index is published to four decimal places, a yield to two
    and an equity index to two. One precision is used for all of them rather than
    a per-unit rule, because a page that formatted each market differently would
    invite the reader to infer significance from the number of digits.
    """
    return f"{level.value:.4f} {level.unit}"


def _duration(span: timedelta) -> str:
    """A duration in the standard library's own form, to whole seconds."""
    return str(timedelta(seconds=int(span.total_seconds())))


def _horizon_label(horizon: Horizon) -> str:
    """How a horizon is named on a row — always by its observation count.

    **No wall-clock equivalent is ever printed on this page**, and there is no
    branch that could print one. Every market here is session-bound, so a count
    of completed observations is the only honest name for a window; the pulse
    renderer's `_horizon_label` has a wall-clock branch because its universe
    contains continuously traded markets, and this one deliberately does not.
    """
    return f"{horizon.horizon_id} ({_observations(horizon.bars)})"


def _freshness_word(state: FreshnessState) -> str:
    """The phrase a freshness state prints as. Never "fresh" and never "stale"."""
    if state is FreshnessState.ON_SCHEDULE:
        return "on schedule"
    if state is FreshnessState.BEHIND_SCHEDULE:
        return "behind schedule"
    return "no schedule established"


# ------------------------------------------------------------------ sections ---


def _header(report: MacroContextReport) -> list[str]:
    lines = [_rule("="), "MACRO & CROSS-ASSET CONTEXT", _rule("=")]
    lines.extend(_label_and_body("as of", report.as_of.isoformat(), indent=""))
    lines.extend(_label_and_body("universe", report.universe.name, indent=""))
    lines.extend(
        _label_and_body(
            "scope",
            f"{report.read_count} market(s) read · "
            f"{len(report.unavailable)} source failure(s) · "
            f"{report.unsupported_count} market(s) with no configured source",
            indent="",
        )
    )
    lines.append("")
    lines.extend(_wrap(MACRO_ORIENTATION_NOTE))
    return lines


def _levels_section(report: MacroContextReport) -> list[str]:
    lines = _heading("MARKET LEVELS")
    if not report.levels:
        lines.extend(
            _wrap(
                "No market could be read, so no level is stated. This is not a "
                "market at zero; it is a page with no data.",
                indent=_INDENT,
            )
        )
        return lines
    for level in report.levels:
        lines.append("")
        lines.extend(_label_and_body(level.display_name, _level_value(level)))
        lines.extend(
            _label_and_body(
                "observed",
                f"{level.observed_at.isoformat()} · {level.source}",
                indent=_INDENT + _INDENT,
            )
        )
    return lines


def _move_row(reading: MarketReading, horizon: Horizon) -> list[str]:
    move = reading.move_for(horizon.horizon_id)
    label = _horizon_label(horizon)
    if move is None:
        return _label_and_body(
            label, "this reading holds no move for this horizon",
            indent=_INDENT + _INDENT,
        )
    if not move.is_measured:
        return _label_and_body(
            label, f"{_ABSENT} — {move.unavailable_reason}",
            indent=_INDENT + _INDENT,
        )
    return _label_and_body(
        label,
        f"{_percent(move.value)} · {move.metric} over "
        f"{_observations(move.observation_count)}",
        indent=_INDENT + _INDENT,
    )


def _moves_section(report: MacroContextReport) -> list[str]:
    lines = _heading("MOVES")
    lines.extend(_wrap(MACRO_SESSION_LIMITATION, indent=_INDENT))
    price_like = [
        reading
        for reading in report.readings
        if report.rate_fact_for(reading.benchmark_id) is None
    ]
    if not price_like:
        lines.append("")
        lines.extend(
            _wrap(
                "No price-like market was read, so no move is stated.",
                indent=_INDENT,
            )
        )
        return lines
    for reading in price_like:
        lines.append("")
        lines.extend(
            _label_and_body(
                reading.benchmark.display_name, reading.benchmark.quote_unit
            )
        )
        for horizon in report.horizons:
            lines.extend(_move_row(reading, horizon))
    return lines


def _rate_change_body(change: RateChange) -> str:
    """A yield move: basis points first, the ratio labelled and second.

    **The order is the point.** The basis-point figure is what a rates column
    asks for, so it leads; the relative change follows behind an explicit label
    so it can never be read as the answer to the same question.
    """
    body = (
        f"{_basis_points(change.basis_points)} "
        f"({change.from_value:.2f}% → {change.to_value:.2f}%)"
    )
    if change.relative_change is None:
        return f"{body} · relative change {_ABSENT}: {change.relative_unavailable_reason}"
    return f"{body} · relative change {_percent(change.relative_change)}"


def _rates_section(report: MacroContextReport) -> list[str]:
    lines = _heading("RATES")
    lines.extend(_wrap(MACRO_RATE_NOTE, indent=_INDENT))
    if not report.rate_facts:
        lines.append("")
        lines.extend(
            _wrap(
                "No yield was read, so no rate move is stated.", indent=_INDENT
            )
        )
        return lines
    for fact in report.rate_facts:
        lines.append("")
        lines.extend(
            _label_and_body(fact.display_name, _level_value(fact.level))
        )
        for horizon in report.horizons:
            change = fact.change_for(horizon.horizon_id)
            if change is not None:
                lines.extend(
                    _label_and_body(
                        _horizon_label(horizon),
                        _rate_change_body(change),
                        indent=_INDENT + _INDENT,
                    )
                )
                continue
            reason = next(
                (
                    text
                    for entry_id, text in fact.unavailable_horizons
                    if entry_id == horizon.horizon_id
                ),
                "this yield holds no move for this horizon",
            )
            lines.extend(
                _label_and_body(
                    _horizon_label(horizon),
                    f"{_ABSENT} — {reason}",
                    indent=_INDENT + _INDENT,
                )
            )
    return lines


def _volatility_section(report: MacroContextReport) -> list[str]:
    lines = _heading("VOLATILITY")
    lines.extend(_wrap(VOLATILITY_CLASSIFICATION_NOTE, indent=_INDENT))
    if not report.readings:
        lines.append("")
        lines.extend(
            _wrap("No market was read, so no volatility is stated.", indent=_INDENT)
        )
        return lines
    lines.append("")
    for reading in report.readings:
        volatility = reading.volatility
        if volatility.is_measured:
            body = (
                f"{_plain(volatility.value)} · {volatility.metric} over "
                f"{_observations(volatility.observation_count)}"
            )
        else:
            body = f"{_ABSENT} — {volatility.unavailable_reason}"
        lines.extend(_label_and_body(reading.benchmark.display_name, body))
    return lines


def _relationship_body(relationship: CrossAssetRelationship) -> str:
    if relationship.is_measured:
        return (
            f"{_plain(relationship.value)} · {relationship.metric} over "
            f"{_observations(relationship.observation_count)} "
            f"({relationship.window_start.date().isoformat()} to "
            f"{relationship.window_end.date().isoformat()}) · aligned on "
            f"{relationship.aligned_count} shared date(s), dropping "
            f"{relationship.subject_dropped} from {relationship.subject_id} and "
            f"{relationship.reference_dropped} from {relationship.reference_id}"
        )
    return f"{_ABSENT} — {relationship.unavailable_reason}"


def _relationships_section(report: MacroContextReport) -> list[str]:
    lines = _heading("CROSS-ASSET RELATIONSHIPS")
    lines.extend(_wrap(MACRO_RELATIONSHIP_CAVEAT, indent=_INDENT))
    lines.append("")
    lines.extend(_wrap(CORRELATION_COMPARABILITY_RULE, indent=_INDENT))
    if not report.relationships:
        lines.append("")
        lines.extend(
            _wrap(
                "No relationship was measured. A correlation needs a reference "
                "market this page could read and at least one other market "
                "sharing its observation dates; that condition was not met.",
                indent=_INDENT,
            )
        )
        return lines
    lines.append("")
    lines.extend(
        _label_and_body("measured against", report.relationship_reference)
    )
    lines.append("")
    for relationship in report.relationships:
        lines.extend(
            _label_and_body(
                relationship.subject_id, _relationship_body(relationship)
            )
        )
    return lines


def _data_quality_section(report: MacroContextReport) -> list[str]:
    lines = _heading("DATA QUALITY")
    lines.extend(_wrap(MACRO_FRESHNESS_NOTE, indent=_INDENT))
    lines.append("")
    lines.extend(_wrap(COMPARABILITY_RULE, indent=_INDENT))
    if not report.readings:
        lines.append("")
        lines.extend(
            _wrap(
                "No reading was produced, so there is no age to state.",
                indent=_INDENT,
            )
        )
        return lines
    lines.append("")
    for reading in report.readings:
        state = reading.freshness_at(report.as_of)
        lines.extend(
            _label_and_body(
                reading.benchmark.display_name,
                f"{_freshness_word(state)} · age "
                f"{_duration(reading.age_at(report.as_of))}",
            )
        )
        lines.extend(
            _label_and_body(
                "source", reading.provenance, indent=_INDENT + _INDENT
            )
        )
        policy = reading.benchmark.freshness_policy
        if policy is not None:
            lines.extend(
                _label_and_body(
                    "schedule",
                    f"published every {_duration(policy.publication_period)}, "
                    f"tolerance {_duration(policy.tolerance)} — {policy.basis}",
                    indent=_INDENT + _INDENT,
                )
            )
    return lines


def _unavailable_section(report: MacroContextReport) -> list[str]:
    lines = _heading("UNAVAILABLE")
    unsupported = report.universe.unsupported
    if not report.unavailable and not unsupported:
        lines.extend(
            _wrap(
                "Every market in this universe has a configured source and every "
                "one of them answered.",
                indent=_INDENT,
            )
        )
        return lines
    for failure in report.unavailable:
        lines.append("")
        lines.extend(
            _label_and_body(
                failure.benchmark.display_name,
                f"source failure — {failure.reason}",
            )
        )
    for benchmark in unsupported:
        lines.append("")
        lines.extend(
            _label_and_body(
                benchmark.display_name,
                f"no configured source — {benchmark.unsupported_reason}",
            )
        )
    return lines


def render_macro_context(report: MacroContextReport) -> str:
    """The whole page as one string, with no trailing newline.

    Args:
        report: the frozen context to print. Nothing is fetched, computed or
            re-derived here; every figure on the page is already on the report.

    Returns:
        A deterministic page. Two calls over one report produce one string, and
        nothing here reads a clock, a set's iteration order or an object's
        identity.
    """
    if not isinstance(report, MacroContextReport):
        raise TypeError(
            f"report must be a MacroContextReport, got {type(report).__name__}"
        )
    lines: list[str] = []
    lines.extend(_header(report))
    lines.extend(_levels_section(report))
    lines.extend(_moves_section(report))
    lines.extend(_rates_section(report))
    lines.extend(_volatility_section(report))
    lines.extend(_relationships_section(report))
    lines.extend(_data_quality_section(report))
    lines.extend(_unavailable_section(report))
    lines.append("")
    lines.append(_rule("="))
    return "\n".join(lines)
