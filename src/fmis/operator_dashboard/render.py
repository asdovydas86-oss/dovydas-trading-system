"""Read models → HTML. Presentation only, and presentation is a narrow word here.

**What this module is allowed to do:** escape, format, group, label, lay out,
link. Turning `0.0231` into ``+2.31%`` is formatting. Putting confirmed setups
above the wait list is *reading the order the workspace already produced*.

**What it is not allowed to do, and what a guard asserts it does not:** compute
a market or monetary quantity, sort rows by a property of the analysis, sum,
divide, or compare two figures to decide which is better. There is no
`sorted()`, no `sum()`, and no arithmetic on any engine value in this file. The
one exception is the equity chart, which scales values to pixel coordinates —
and pixels are not financial observations. That is stated on the chart.

**Every string reaching the page goes through `_e`.** A provider's error message
is text this repository did not write, and a symbol could in principle be
anything; both are escaped. There is no template engine and no interpolation of
raw values into markup anywhere below.

**Absence never renders as a blank or a bare dash.** `_absent` produces the
reason beside the gap, because a blank cell where a risk figure belongs is read
as *no risk* rather than as *not measured*, and that misreading is the specific
thing this dashboard exists to prevent.

**Nothing on any page submits anything.** No `<form>`, no `<button>`, no
`<input>`, no script. Every interactive element is a link to another read-only
view, and a guard asserts the absence of the write-capable elements.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from html import escape
from typing import Any, Iterable, Sequence
from urllib.parse import quote

from fmis.operator_dashboard.models import (
    BenchmarkRow,
    DataHealthView,
    MacroView,
    MoveCell,
    OperatorDashboardSnapshot,
    PaperView,
    PerformanceView,
    PortfolioView,
    PulseView,
    DashboardSection,
    DashboardSectionStatus,
    BlockerRow,
    DevelopingEvidenceRow,
    EvidenceItemRow,
    SetupRow,
    SourceState,
    SwingSnapshot,
    SwingView,
    SymbolDecisionRow,
    TimeframeRow,
    WarningRow,
)
from fmis.operator_dashboard.theme import (
    EQUITY_CHART_HEIGHT,
    EQUITY_CHART_WIDTH,
    STYLESHEET,
)

__all__ = ["PAGES", "render_page", "page_titles"]

#: Every route the server serves, in navigation order. The server refuses any
#: path not in this mapping, so the route table and the navigation cannot drift.
PAGES: tuple[tuple[str, str], ...] = (
    ("/", "Overview"),
    ("/markets", "Markets"),
    ("/swing", "Swing"),
    ("/portfolio", "Portfolio"),
    ("/paper", "Paper"),
    ("/performance", "Performance"),
    ("/lab", "Swing Lab"),
    ("/geometry", "Trade Geometry"),
    ("/validation", "Validation"),
    ("/system", "System"),
)


def page_titles() -> tuple[str, ...]:
    return tuple(title for _, title in PAGES)


# ---------------------------------------------------------------------------
# Escaping and formatting
# ---------------------------------------------------------------------------


def _e(value: Any) -> str:
    """Escape anything for HTML text. The only way a value reaches the page."""
    return escape("" if value is None else str(value), quote=True)


def _percent(value: float) -> str:
    """A fraction as a signed percentage. Explicit ``+`` so sign is never lost."""
    return f"{value * 100:+.2f}%"


def _plain(value: float) -> str:
    """A unitless measured number — a volatility, a correlation — at 4 decimals."""
    return f"{value:.4f}"


def _basis_points(value: float) -> str:
    return f"{value:+.1f} bp"


def _sign_class(value: float) -> str:
    """The class marking a measured number's sign. **Not** a recommendation.

    Zero is its own class rather than borrowing the positive one: a move of
    exactly nothing is a real observation and should not be tinted as a gain.
    """
    if value > 0:
        return "pos"
    if value < 0:
        return "neg"
    return "zero"


def _duration(span: timedelta) -> str:
    """An age in a compact form. Seconds are dropped above an hour."""
    total = int(span.total_seconds())
    sign = "-" if total < 0 else ""
    total = abs(total)
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, seconds = divmod(rest, 60)
    if days:
        return f"{sign}{days}d {hours}h"
    if hours:
        return f"{sign}{hours}h {minutes}m"
    if minutes:
        return f"{sign}{minutes}m {seconds}s"
    return f"{sign}{seconds}s"


def _stamp(moment: datetime | None) -> str:
    if moment is None:
        return _absent("no instant is recorded for this value")
    return f"<span title=\"{_e(moment.isoformat())}\">{_e(moment.strftime('%Y-%m-%d %H:%M'))}Z</span>"


def _absent(reason: str | None) -> str:
    """A gap and the reason for it, never a bare dash.

    The word *unavailable* is spelled out beside the reason. A dash alone is
    read as a zero by anybody scanning a column of numbers, and one misread
    zero in a risk column is worth more than the space this costs.
    """
    if not reason:
        return '<span class="absent">unavailable</span>'
    return (
        '<span class="absent">unavailable'
        f'<span class="why">{_e(reason)}</span></span>'
    )


def _measured(
    value: float | None, reason: str | None, formatter: Any = _percent
) -> str:
    """A measured number with its sign class, or its absence with the reason."""
    if value is None:
        return _absent(reason)
    return f'<span class="{_sign_class(value)}">{_e(formatter(value))}</span>'


def _text(value: str | None, reason: str | None = None) -> str:
    """Engine text, or the stated absence. Empty string counts as absent."""
    if value is None or value == "":
        return _absent(reason)
    return _e(value)


def _chip(label: str, kind: str) -> str:
    slug = str(kind).strip().lower().replace(" ", "-")
    return f'<span class="chip state-{_e(slug)}">{_e(label)}</span>'


def _state_chip(state: SourceState) -> str:
    return _chip(state.value.replace("_", " "), state.value)


def _setup_chip(state: str) -> str:
    """A setup's state as the engine spelled it.

    WAIT and NO TRADE reach the neutral classes in `theme`, not the fault ones:
    both are conclusions this system reached on purpose, and painting a correct
    refusal in the colour of an error teaches the owner to distrust it.
    """
    return _chip(state, state.strip().lower().replace(" ", "-").replace("_", "-"))


def _list(items: Sequence[str]) -> str:
    if not items:
        return ""
    rows = "".join(f"<li>{_e(item)}</li>" for item in items)
    return f'<ul class="plain">{rows}</ul>'


def _kv(pairs: Iterable[tuple[str, str]]) -> str:
    rows = "".join(f"<dt>{_e(key)}</dt><dd>{value}</dd>" for key, value in pairs)
    return f'<dl class="kv">{rows}</dl>'


def _details(summary: str, body: str, *, open_: bool = False) -> str:
    if not body:
        return ""
    flag = " open" if open_ else ""
    return f"<details{flag}><summary>{_e(summary)}</summary>{body}</details>"


def _tile(key: str, value: str, *, small: bool = False) -> str:
    cls = "v small" if small else "v"
    return f'<div class="tile"><div class="k">{_e(key)}</div><div class="{cls}">{value}</div></div>'


def _table(headers: Sequence[tuple[str, str]], rows: Sequence[str]) -> str:
    """A table, or nothing. ``headers`` pairs a label with its column class."""
    if not rows:
        return ""
    head = "".join(
        f'<th class="{_e(cls)}">{_e(label)}</th>' for label, cls in headers
    )
    return (
        '<div class="scroll"><table><thead><tr>'
        f"{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _empty(message: str) -> str:
    return f'<p class="empty">{_e(message)}</p>'


# ---------------------------------------------------------------------------
# Section envelopes
# ---------------------------------------------------------------------------


def _panel(title: str, body: str, *, meta: str = "") -> str:
    tail = f'<span class="meta">{meta}</span>' if meta else ""
    return (
        f'<section class="panel"><h2>{_e(title)}{tail}</h2>'
        f'<div class="body">{body}</div></section>'
    )


def _section_meta(section: DashboardSection[Any]) -> str:
    """The provenance line every panel carries: data instant, then source.

    This is the answer to *"can the owner see as_of, source and freshness
    without opening code"*. It sits on every panel, at small size, always.
    """
    parts: list[str] = []
    if section.as_of is not None:
        parts.append(f"as of {_stamp(section.as_of)}")
    if section.source:
        parts.append(_e(section.source))
    return " · ".join(parts)


def _failed(section: DashboardSection[Any]) -> str:
    """A section that could not be read. Loud, specific, and isolated.

    The other sections on the page render normally around this. That is the
    whole point of per-section isolation: FRED being down must not cost the
    owner the swing page.
    """
    return (
        f'<div class="failed"><div class="t">{_e(section.name)} unavailable</div>'
        f'<div class="m">{_e(section.unavailable_reason)}</div></div>'
    )


def _guarded(section: DashboardSection[Any], title: str, body: Any) -> str:
    """Render a section's body, or its failure, or its emptiness."""
    meta = _section_meta(section)
    if section.failed:
        return _panel(title, _failed(section), meta=meta)
    if section.status is DashboardSectionStatus.EMPTY or section.data is None:
        return _panel(
            title,
            _empty(_empty_message(section.name)),
            meta=meta,
        )
    return _panel(title, body(section.data), meta=meta)


def _empty_message(name: str) -> str:
    """Emptiness, stated as the fact it is rather than as a failure.

    *"No trades recorded"* and *"the store could not be read"* are different
    facts and must never share a message. An owner who has not traded has not
    suffered an outage.
    """
    return {
        # Like the paper message below, this keeps the *paper is never counted
        # here* framing on an empty page. A separation that only appears once
        # there is data to separate teaches the reader it is a property of the
        # data rather than of the page.
        "portfolio": "No durable store is present, so no position, limit or "
        "capital figure was read. Nothing failed — there is nothing recorded "
        "yet. Simulated trades are never added into any figure on this page; "
        "they are on the Paper page.",
        # The *simulated, never real exposure* framing belongs on this page even
        # when it is empty. It lives in the populated body too, and a section
        # that drops it when the table is empty teaches the framing as something
        # that appears with the data rather than as a property of the page.
        "paper": "No paper trade is recorded. Nothing failed. Paper trades are "
        "simulated: none of them is real exposure, and none appears in any "
        "portfolio figure.",
        "performance": "No closed trade is recorded, so there is no statistic "
        "to state. Nothing failed.",
        "pulse": "No market was read on this refresh.",
        "macro": "No macro market was read on this refresh.",
        "health": "No source was touched on this refresh.",
        "swing": "No symbol was scanned on this refresh.",
    }.get(name, "Nothing was read for this section.")


# ---------------------------------------------------------------------------
# Markets
# ---------------------------------------------------------------------------


class _Footnotes:
    """Distinct absence reasons for one table, numbered and printed once.

    **Why a table needs this and a paragraph does not.** A yield holds no
    percentage move over any of its three windows, and the reason is the same
    long sentence for all three. The terminal renderer collapses that case —
    *"one reason, stated once"* — because repeating it three times buries the
    page. A table cannot collapse three columns into one, so the reason moves
    beneath the table and the cells carry a marker to it.

    Nothing is hidden and nothing is truncated: every distinct reason appears in
    full, on the page, exactly once, and the full text is also on each cell's
    `title` for a reader who hovers rather than scrolls.
    """

    def __init__(self) -> None:
        self._reasons: dict[str, int] = {}

    def mark(self, reason: str | None) -> str:
        if not reason:
            return '<span class="absent">unavailable</span>'
        number = self._reasons.setdefault(reason, len(self._reasons) + 1)
        return (
            f'<span class="absent" title="{_e(reason)}">unavailable'
            f"<sup>{number}</sup></span>"
        )

    def render(self) -> str:
        if not self._reasons:
            return ""
        items = "".join(
            f"<li><sup>{number}</sup> {_e(reason)}</li>"
            for reason, number in self._reasons.items()
        )
        return (
            '<ul class="footnotes">'
            f"{items}</ul>"
        )


def _move_cell(
    move: MoveCell, formatter: Any = _percent, notes: _Footnotes | None = None
) -> str:
    if move.value is None and notes is not None:
        return notes.mark(move.unavailable_reason)
    return _measured(move.value, move.unavailable_reason, formatter)


def _horizon_families(
    rows: Sequence[BenchmarkRow],
) -> tuple[tuple[tuple[str, ...], list[BenchmarkRow]], ...]:
    """Group markets by the set of windows they were actually measured over.

    **One table per cadence, not one table with every column.** An hourly crypto
    series and a daily macro series are measured over different windows with
    different ids, and a single table spanning both puts three empty cells on
    every row. Milestone BU removed exactly that from the terminal renderer —
    *"a daily series has no twenty-four-hourly-bar window, and never will"* — so
    printing *unavailable* there says a measurement was attempted and failed
    when none was attempted. This grouping is the table-shaped form of that
    same fix.

    Grouping is presentation. Families appear in the order their first market
    appears, and markets keep their order within a family; nothing is sorted.
    """
    families: dict[tuple[str, ...], list[BenchmarkRow]] = {}
    for row in rows:
        key = tuple(move.horizon_id for move in row.moves)
        families.setdefault(key, []).append(row)
    return tuple(families.items())


def _pulse_family_table(
    horizon_ids: Sequence[str], rows: Sequence[BenchmarkRow], labels: dict[str, str]
) -> str:
    headers: list[tuple[str, str]] = [
        ("Market", "sym"),
        ("Category", ""),
        ("State", ""),
    ]
    headers.extend((labels.get(hid, hid), "num") for hid in horizon_ids)
    headers.extend(
        [("Volatility", "num"), ("Age", "num"), ("Source", ""), ("Last bar", "")]
    )
    notes = _Footnotes()
    body: list[str] = []
    for row in rows:
        moves = {move.horizon_id: move for move in row.moves}
        cells = [
            f'<td class="sym">{_e(row.benchmark_id)}<br>'
            f'<span class="sub">{_e(row.display_name)}</span></td>',
            f"<td>{_e(row.category)}</td>",
            f"<td>{_state_chip(row.state)}</td>",
        ]
        for horizon_id in horizon_ids:
            move = moves[horizon_id]
            cells.append(f'<td class="num">{_move_cell(move, _percent, notes)}</td>')
        cells.append(
            f'<td class="num">{_measured(row.volatility, row.volatility_reason, _plain) if row.volatility is not None else notes.mark(row.volatility_reason)}</td>'
        )
        cells.append(
            f'<td class="num">{_e(_duration(row.age)) if row.age is not None else notes.mark("no age is stated")}</td>'
        )
        cells.append(f"<td>{_text(row.source, 'no source is named')}</td>")
        cells.append(f"<td>{_stamp(row.last_bar_open)}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")
    return _table(headers, body) + notes.render()


def _unreadable_markets_table(rows: Sequence[Any]) -> str:
    """Markets with no reading, each with the reason it has none — stated once.

    **One row, one reason cell.** A market with no reading has nothing for the
    level, move, volatility, age or source columns, and putting it in the main
    table repeats one long paragraph six times across one row. So these markets
    get their own table with a single reason column, which is also how the
    terminal renderer's *NOT AVAILABLE* section reads.

    *Unsupported* and *unavailable* both land here and keep their own chips: one
    means this build has no provider for that market at all — permanent, and
    true again tomorrow — while the other means a provider that exists did not
    answer on this run.
    """
    return _table(
        [("Market", "sym"), ("Category", ""), ("State", ""), ("Reason", "")],
        [
            "<tr>"
            f'<td class="sym">{_e(row.benchmark_id)}<br>'
            f'<span class="sub">{_e(row.display_name)}</span></td>'
            f'<td>{_e(getattr(row, "category", ""))}</td>'
            f"<td>{_state_chip(row.state)}</td>"
            f"<td>{_text(row.unavailable_reason, 'no reason was stated')}</td>"
            "</tr>"
            for row in rows
        ],
    )


def _pulse_rows(view: PulseView) -> str:
    labels = dict(view.horizons)
    parts: list[str] = []
    unreadable: list[BenchmarkRow] = []
    for horizon_ids, rows in _horizon_families(view.rows):
        if not horizon_ids:
            unreadable.extend(rows)
            continue
        parts.append(_pulse_family_table(horizon_ids, rows, labels))
    if unreadable:
        parts.append(_unreadable_markets_table(unreadable))
    return "".join(parts) or _empty("No market was read on this refresh.")


def _pulse_body(view: PulseView) -> str:
    legend = ", ".join(
        f"{horizon_id} = {description}" for horizon_id, description in view.horizons
    )
    parts = [_pulse_rows(view)]
    parts.append(
        f'<p class="note">{_e(view.read_count)} of {_e(view.requested_count)} '
        f"markets read; {_e(view.unsupported_count)} unsupported in this build. "
        "Windows are counts of closed bars, not durations — this build holds no "
        "trading calendar.</p>"
    )
    if legend:
        parts.append(f'<p class="note">{_e(legend)}</p>')
    if view.co_movement_reference:
        co_rows = [
            f"<tr><td class=\"sym\">{_e(row.benchmark_id)}</td>"
            f'<td class="num">{_measured(row.co_movement, row.co_movement_reason, _plain)}</td></tr>'
            for row in view.rows
            if row.co_movement is not None or row.co_movement_reason
        ]
        parts.append(
            _details(
                f"co-movement against {view.co_movement_reference}",
                _table([("Market", "sym"), ("Correlation", "num")], co_rows),
            )
        )
    return "".join(parts)


def _macro_body(view: MacroView) -> str:
    headers: list[tuple[str, str]] = [
        ("Market", "sym"),
        ("State", ""),
        ("Level", "num"),
        ("Unit", ""),
        ("Moves", ""),
        ("Volatility", "num"),
        ("Age", "num"),
        ("Observed", ""),
        ("Source", ""),
    ]
    # A market with no reading has nothing for eight of these nine columns, so
    # it goes to its own one-reason table rather than repeating one paragraph
    # across a row. Partitioning preserves order within each group.
    readable = [row for row in view.rows if row.unavailable_reason is None]
    unreadable = [row for row in view.rows if row.unavailable_reason is not None]
    notes = _Footnotes()
    rows: list[str] = []
    for row in readable:
        formatter = _basis_points if row.change_unit == "basis points" else _percent
        moves = " · ".join(
            f"{_e(move.label or move.horizon_id)} {_move_cell(move, formatter, notes)}"
            for move in row.moves
        )
        level = (
            _e(f"{row.level:,.4f}".rstrip("0").rstrip("."))
            if row.level is not None
            else notes.mark("no level was produced for this market")
        )
        rows.append(
            "<tr>"
            f'<td class="sym">{_e(row.benchmark_id)}<br>'
            f'<span class="sub">{_e(row.display_name)}</span></td>'
            f"<td>{_state_chip(row.state)}</td>"
            f'<td class="num">{level}</td>'
            f"<td>{_text(row.unit, 'no unit is stated')}</td>"
            f"<td>{moves or notes.mark('this market holds no move')}</td>"
            f'<td class="num">{_measured(row.volatility, row.volatility_reason, _plain) if row.volatility is not None else notes.mark(row.volatility_reason)}</td>'
            f'<td class="num">{_e(_duration(row.age)) if row.age is not None else notes.mark("no age is stated")}</td>'
            f"<td>{_stamp(row.observed_at)}</td>"
            f"<td>{_text(row.source, 'no source is named')}</td>"
            "</tr>"
        )
    parts = [_table(headers, rows), notes.render()]
    if unreadable:
        parts.append(_unreadable_markets_table(unreadable))
    parts.append(
        '<p class="note">Yields move in basis points, not percentage returns — '
        "the two are different quantities and are never shown in one unit.</p>"
    )
    if view.relationships:
        rel_rows = [
            "<tr>"
            f'<td class="sym">{_e(row.subject_id)}</td>'
            f"<td>{_e(row.reference_id)}</td>"
            f"<td>{_e(row.metric)}</td>"
            f'<td class="num">{_measured(row.value, row.unavailable_reason, _plain)}</td>'
            f'<td class="num">{_e(row.aligned_count)} / {_e(row.observation_count)}</td>'
            f"<td>{_text(row.comparability, row.detail or 'no comparability key was stated')}</td>"
            "</tr>"
            for row in view.relationships
        ]
        parts.append(
            _details(
                f"cross-asset relationships against {view.relationship_reference or 'the stated reference'}",
                _table(
                    [
                        ("Subject", "sym"),
                        ("Reference", ""),
                        ("Metric", ""),
                        ("Value", "num"),
                        ("Aligned / observed", "num"),
                        ("Comparability", ""),
                    ],
                    rel_rows,
                )
                + '<p class="note">Aligned counts are shown because a '
                "correlation over four aligned observations and one over ninety "
                "are different claims.</p>",
            )
        )
    return "".join(parts)


# ---------------------------------------------------------------------------
# Swing
# ---------------------------------------------------------------------------


def _setup_link(symbol: str) -> str:
    return f'<a href="/swing/{quote(symbol, safe="")}">{_e(symbol)}</a>'


def _evidence_cell(row: SetupRow) -> str:
    if row.evidence is None:
        return _absent(row.evidence_reason)
    digest = row.evidence
    ready = "ready" if digest.decision_ready else "not ready"
    return (
        f'<span title="{_e(digest.decision_ready_reason)}">'
        f"{_e(digest.supporting)}✓ {_e(digest.conflicting)}✗ "
        f"{_e(digest.missing)}? · {_e(ready)}</span>"
    )


def _setup_rows(rows: Sequence[SetupRow]) -> str:
    body: list[str] = []
    for row in rows:
        body.append(
            "<tr>"
            f'<td class="num">{_e(row.position)}</td>'
            f'<td class="sym">{_setup_link(row.symbol)}</td>'
            f"<td>{_setup_chip(row.state)}</td>"
            f"<td>{_text(row.direction, 'no direction is stated for this setup')}</td>"
            f"<td>{_text(row.approval_status, 'no approval was produced')}</td>"
            f"<td>{_text(row.sufficiency)}</td>"
            f"<td>{_evidence_cell(row)}</td>"
            f'<td class="num">{_measured(row.risk_reward, "no risk/reward was produced", lambda value: f"{value:.2f}")}</td>'
            f"<td>{_text(row.identity, row.identity_reason)}</td>"
            f"<td>{_text(row.paper_status, 'no paper trade for this symbol')}</td>"
            f"<td>{_text(row.held, 'not held')}</td>"
            "</tr>"
        )
    return _table(
        [
            ("#", "num"),
            ("Symbol", "sym"),
            ("State", ""),
            ("Direction", ""),
            ("Approval", ""),
            ("Sufficiency", ""),
            ("Evidence", ""),
            ("R:R", "num"),
            ("Identity", ""),
            ("Paper", ""),
            ("Held", ""),
        ],
        body,
    )


#: Presentation labels for the vocabularies an operator reads most often.
#:
#: **Presentation only.** Each map is keyed on the engine's own value and the
#: raw key is printed beside or beneath every label it replaces, so nothing is
#: hidden and provenance survives. A missing key falls back to the engine's own
#: text — a new enum member renders as itself rather than as a blank.
_FAMILY_LABELS: dict[str, str] = {
    "context_structural_trend": "HTF structural trend",
    "setup_structural_trend": "Setup structural trend",
    "setup_evidence_alignment": "Setup evidence alignment",
}

_BLOCKER_LABELS: dict[str, str] = {
    "decision_context_insufficient": "decision context insufficient",
    "context_regime_not_eligible": "HTF regime not eligible",
    "directional_families_disagree": "timeframes disagree",
    "awaiting_confirmation": "awaiting confirmation",
    "none": "nothing blocking",
    "undetermined": "not determinable from this result",
}

_ROLE_LABELS: dict[str, str] = {
    "context": "HTF context",
    "setup": "setup",
    "execution": "execution",
}


def _label(value: str, table: dict[str, str]) -> str:
    """A readable label, or the engine's own text when none is defined."""
    return table.get(value, value.replace("_", " "))


def _item_label(key: str) -> str:
    """An evidence item's label. Its keys are namespaced — `factor:<family>`.

    Only the family half has a readable name, so the namespace is split off
    before the lookup and the **full key is still printed beneath the label** by
    the caller. A key with no namespace, or a family with no label, renders as
    itself.
    """
    _, _, tail = key.partition(":")
    return _FAMILY_LABELS.get(tail or key, key)


def _developing_text(row: DevelopingEvidenceRow | None) -> str:
    """Which way the readable families point — **never a decision.**

    The wording is deliberate and the words *signal*, *candidate*, *entry* and
    *ready* appear in none of it. A `LEANING` row says evidence is **leaning and
    not confirmed**, because the policy did not name a direction and this page
    must not appear to.
    """
    if row is None:
        return _absent("no developing-evidence summary was produced")
    if row.state == "direction_stated":
        return (
            f'<span class="chip state-{_e(row.lean or "")}">{_e(row.lean or "")}</span>'
            ' <span class="sub">stated by the policy</span>'
        )
    if row.state == "leaning":
        return (
            f'<span class="chip state-{_e(row.lean or "")}">{_e(row.lean or "")}</span>'
            ' <span class="sub">leaning · not confirmed, and no direction '
            "was stated</span>"
        )
    if row.state == "divided":
        return '<span class="sub">divided — the readable families disagree</span>'
    return '<span class="sub">none readable — no family cast a vote</span>'


def _role_reading(rows: Sequence[TimeframeRow], role: str) -> TimeframeRow | None:
    for row in rows:
        if row.role == role:
            return row
    return None


def _state_cell(rows: Sequence[TimeframeRow], role: str) -> str:
    """One role's structural trend, **read as a value.**

    `TimeframeRow.structural_trend` is the trend engine's own enum value for
    this role, carried through `SetupReadings`. An earlier draft recovered it by
    finding the directional factor whose `source` string contained the role's
    interval — renderer inference over provenance prose, when a structured field
    for it exists one layer down. It reads that field.

    **No engine module is named here.** The producing engine is already on the
    page, supplied by the engine itself, on every row of the directional
    families table; spelling it as a literal in this file would make the
    renderer a second place that name lives, and a repository guard forbids
    exactly that.

    Falls back to a stated absence — never to a blank, which reads as a neutral
    market.
    """
    reading = _role_reading(rows, role)
    if reading is None:
        return _absent("this role was not read on this refresh")
    if reading.structural_trend is None:
        return (
            f"{_e(reading.interval)}"
            '<br><span class="sub">no structural trend was carried for this '
            "role</span>"
        )
    return (
        f"{_e(reading.interval)} {_e(reading.structural_trend)}"
        '<br><span class="sub">structural trend</span>'
    )


def _freshness_cell(rows: Sequence[TimeframeRow]) -> str:
    """Every role's age, side by side. **An age, never a verdict.**

    The three roles are listed separately because they are read separately: a
    weekly candle closes once a week and a four-hour candle six times a day, so
    one number describing all three would be a claim the pipeline cannot make.
    No threshold is applied and no cell is coloured — see the note the page
    prints beneath the table.
    """
    if not rows:
        return _absent("no per-role reading instant was carried for this symbol")
    return " · ".join(
        f'<span title="{_e(row.as_of.isoformat())}">{_e(row.interval)} '
        + (
            _e(_duration(row.age))
            if row.age is not None
            else '<span class="sub">no age</span>'
        )
        + "</span>"
        for row in rows
    )


def _swing_snapshot(snapshot: SwingSnapshot) -> str:
    """The scan in tiles and two distributions. **Descriptive, never predictive.**

    No bullish figure, no bearish figure, no breadth reading, no *"conditions
    are improving"*. The distributions are ordered by the engines' own enum
    order, not by size, so the first row is never presented as the important
    one.
    """
    tiles = "".join(
        [
            _tile("Scanned", _e(snapshot.scanned)),
            _tile("Confirmed", _e(snapshot.confirmed)),
            _tile("Candidates", _e(snapshot.candidates)),
            _tile("Waiting", _e(snapshot.waiting)),
            _tile("Could not be read", _e(snapshot.unreadable)),
        ]
    )
    blockers = _table(
        [("What is holding it", ""), ("Symbols", "num")],
        [
            "<tr>"
            f"<td>{_e(_label(kind, _BLOCKER_LABELS))}"
            f'<br><span class="sub">{_e(kind)}</span></td>'
            f'<td class="num">{_e(count)}</td>'
            "</tr>"
            for kind, count in snapshot.blockers
        ],
    )
    developing = _table(
        [("Developing evidence", ""), ("Symbols", "num")],
        [
            "<tr>"
            f'<td>{_e(state.replace("_", " "))}</td>'
            f'<td class="num">{_e(count)}</td>'
            "</tr>"
            for state, count in snapshot.developing
        ],
    )
    return (
        f'<div class="tiles">{tiles}</div>'
        + blockers
        + developing
        + '<p class="note">Counts of symbols that reached each named condition '
        "the engine itself produced. They are ordered by the engine's own "
        "vocabulary, not by size, and none of them is a market verdict: this "
        "page measures no breadth, calibrates no probability and states no "
        "view on direction.</p>"
    )


def _decision_rows(rows: Sequence[SymbolDecisionRow]) -> str:
    """Every scanned symbol, one per line. **Scan order, and no other.**

    The columns are the three the owner scans for: what the symbol is, what the
    engine concluded, and the engine's own sentence for why. There is no rank
    column and no number column, because there is nothing here to rank by — the
    order is the order the symbols were requested in and means nothing else.
    """
    body = [
        "<tr>"
        f'<td class="sym">{_setup_link(row.symbol)}</td>'
        f"<td>{_setup_chip(row.state)}</td>"
        f"<td>{_developing_text(row.developing)}</td>"
        f"<td>{_state_cell(row.timeframes, 'context')}</td>"
        f"<td>{_state_cell(row.timeframes, 'setup')}</td>"
        f"<td>{_blocker_cell(row.blocker, row.reason)}</td>"
        f"<td>{_freshness_cell(row.timeframes)}</td>"
        "</tr>"
        for row in rows
    ]
    return _table(
        [
            ("Symbol", "sym"),
            ("Decision", ""),
            ("Developing evidence", ""),
            ("HTF context", ""),
            ("Setup state", ""),
            ("What is holding it", ""),
            ("Data age", ""),
        ],
        body,
    )


def _blocker_cell(row: BlockerRow | None, reason: str) -> str:
    """The named condition, with the engine's own sentence behind it.

    The label is short enough to scan a column of twenty; the full sentence the
    policy wrote is the `title`, so the compact form never becomes the only
    version of the truth.
    """
    if row is None:
        return f'<span title="{_e(reason)}">{_e(reason)}</span>'
    return (
        f'<span title="{_e(row.statement)}">{_e(_label(row.kind, _BLOCKER_LABELS))}'
        "</span>"
        f'<br><span class="sub">{_e(row.observed)}</span>'
    )


#: Printed under the per-symbol table. The order of that table is scan order,
#: and a table with no visible ordering rule is read as one sorted by something.
_DECISION_ORDER_NOTE = (
    "One row per scanned symbol, in the order the symbols were scanned. That "
    "order carries no meaning: the first row is not closer to a trade than the "
    "last, and nothing here measures how close any symbol is to anything. "
    "Developing evidence is what the readable families point at, never a "
    "direction the policy stated — a leaning row is still whatever its decision "
    "says it is. Data age is stated per timeframe role and carries no verdict: "
    "no validated staleness bound exists for any role, so nothing here says "
    "fresh or stale. Open a symbol for the evidence behind its conclusion."
)


class _IndependenceNotes:
    """Distinct independence explanations for one symbol, numbered and printed once.

    The projection attaches a full explanation to **every** non-independent
    item, and several items legitimately share the same one — two structural
    trend readings and the regime gate all cite the same shared-input sentence.
    Rendered inline on each row, the operator read one long paragraph three
    times and the evidence table stopped being scannable.

    **Nothing is hidden and nothing is merged.** Each row still carries its own
    marker, so *"which explanation applies to this item"* is still answerable
    per row; each distinct explanation appears in full, once, beneath the table;
    and the full text is on the row's `title` for a reader who hovers. The
    semantics are untouched — only the number of times one sentence is printed.
    """

    def __init__(self) -> None:
        self._notes: dict[str, int] = {}

    def mark(self, note: str | None) -> str:
        if not note:
            return ""
        number = self._notes.setdefault(note, len(self._notes) + 1)
        return f"<sup>{number}</sup>"

    def render(self) -> str:
        if not self._notes:
            return ""
        items = "".join(
            f"<li><sup>{number}</sup> {_e(note)}</li>"
            for note, number in self._notes.items()
        )
        return f'<ul class="footnotes">{items}</ul>'


def _evidence_item_rows(
    items: Sequence[EvidenceItemRow],
    correlated: frozenset[str],
    notes: _IndependenceNotes,
) -> str:
    """One evidence group as a table, with non-independence marked on the row.

    A row whose key another item declares itself correlated with, or which
    declares a correlation of its own, is marked *not independent* — the
    disclosure `fmis.setup_evidence` produced, carried to the surface rather
    than summarised away. Three correlated observations rendered as three plain
    rows read as three-fold confirmation, and they are one reading seen thrice.
    """
    body = []
    for item in items:
        dependent = bool(item.correlated_with) or item.key in correlated
        if dependent:
            marker = notes.mark(item.independence_note)
            title = (
                f' title="{_e(item.independence_note)}"'
                if item.independence_note
                else ""
            )
            note = (
                f'<span class="absent"{title}>not independent{marker}</span>'
            )
        else:
            note = '<span class="sub">no correlation stated</span>'
        shared = (
            '<br><span class="sub">shares inputs with: '
            f'{_e(", ".join(item.correlated_with))}</span>'
            if item.correlated_with
            else ""
        )
        body.append(
            "<tr>"
            f"<td>{_e(_item_label(item.key))}"
            + (
                f'<br><span class="sub">{_e(item.key)}</span>'
                if _item_label(item.key) != item.key
                else ""
            )
            + "</td>"
            f"<td>{_e(item.statement)}</td>"
            f"<td>{_e(item.observed)}</td>"
            f"<td>{_text(', '.join(item.families), 'no family in the taxonomy')}</td>"
            f"<td>{_text(item.scope, 'no scope was stated')}"
            f'<br><span class="sub">{_e(item.source)}</span></td>'
            f"<td>{note}{shared}</td>"
            "</tr>"
        )
    return _table(
        [
            ("Key", ""),
            ("Statement", ""),
            ("Observed", ""),
            ("Family", ""),
            ("Scope / source", ""),
            ("Independence", ""),
        ],
        body,
    )


def _blocker_summary(row: BlockerRow | None, reason: str) -> str:
    """What is holding this reading, and what the existing gate already demands.

    Two lines and no third: the condition, and the requirement the policy
    **already** states. There is no estimate of when it might clear, no price
    that would clear it and no field one could be written into — the gates this
    names are regime and agreement conditions, and no engine below supplies a
    level for any of them.
    """
    if row is None:
        return _text(reason, "no blocking condition was projected")
    return (
        f"{_e(_label(row.kind, _BLOCKER_LABELS))}"
        f'<br><span class="sub">{_e(row.statement)}</span>'
        f'<br><span class="sub">observed: {_e(row.observed)}</span>'
        f'<br><span class="sub">to progress: {_e(row.requirement)}</span>'
        f'<br><span class="sub">{_e(row.source)}</span>'
    )


def _evidence_quality(row: SymbolDecisionRow) -> str:
    """Whether agreement, where there is any, is independent agreement.

    The one evidence fact that belongs in a ten-second summary: three readings
    of one underlying input look exactly like three-fold corroboration, and this
    is where the page says they are not.
    """
    if row.evidence_reason is not None:
        return _absent(row.evidence_reason)
    counts = (
        f"{_e(len(row.supporting))} supporting · "
        f"{_e(len(row.conflicting))} conflicting · "
        f"{_e(len(row.missing))} awaited"
    )
    if row.independence_established:
        return f'{counts}<br><span class="sub">independence established</span>'
    return (
        f"{counts}<br>"
        '<span class="absent">independent corroboration not established'
        '<span class="why">Agreement among the readable families draws on '
        "shared upstream inputs. Read it as one subject area seen more than "
        "once, not as separate sources agreeing.</span></span>"
    )


def _no_invalidation() -> str:
    """Stated rather than blank. **No level is derived to fill the gap.**

    A `WAIT` reading has no structural invalidation because the engine produced
    none — there is no directional thesis for one to invalidate. Printing an
    empty section would read as *"nothing invalidates this"*; deriving a price
    here would be this renderer inventing a level, which it must never do.
    """
    return _empty(
        "The engine produced no structural invalidation for this reading. "
        "None is derived here: a level this page computed would not be one the "
        "engine could be held to."
    )


def _timeframe_table(rows: Sequence[TimeframeRow]) -> str:
    """Every role's reading instant, age and bar count. **No verdict column.**

    The roles are listed separately and never averaged: they are fetched
    separately, close at different rates, and the context role is the one that
    gates whether any direction may exist at all — so an age describing "the
    data" would hide the age that matters most.
    """
    if not rows:
        return _empty(
            "No per-role reading instant was carried for this symbol. The "
            "assessment states one instant of its own; the three timeframes "
            "behind it were read separately and their times are not on this "
            "result."
        )
    body = [
        "<tr>"
        f"<td>{_e(_label(row.role, _ROLE_LABELS))}"
        f'<br><span class="sub">{_e(row.role)}</span></td>'
        f"<td>{_e(row.interval)}</td>"
        f"<td>{_stamp(row.as_of)}</td>"
        f'<td class="num">'
        + (
            _e(_duration(row.age))
            if row.age is not None
            else _absent("no reference instant was available")
        )
        + "</td>"
        f'<td class="num">{_e(row.closed_count)}</td>'
        "</tr>"
        for row in rows
    ]
    return _table(
        [
            ("Role", ""),
            ("Interval", ""),
            ("Last closed candle", ""),
            ("Age", "num"),
            ("Closed bars", "num"),
        ],
        body,
    ) + (
        '<p class="note">The three roles are read separately and close at '
        "different rates, so they are stated separately and never averaged. "
        "<strong>No age here is called fresh or stale.</strong> This repository "
        "has validated no staleness bound for any role, and a threshold invented "
        "so a cell could be coloured would be an unvalidated policy presented as "
        "a fact. The age and the bar count are stated; the judgement is "
        "yours.</p>"
    )


def _decision_detail(row: SymbolDecisionRow) -> str:
    """One symbol's decision, in full. Every value is an engine's own.

    **Four panels, in the order the question is actually asked**, and the order
    is the design decision:

        1. the decision — what was concluded, which way the readable evidence
           points, what is holding it, the two timeframe states, whether the
           agreement is independent, and how old the data is. Everything an
           operator needs before deciding whether to read further;
        2. timeframe context and data times — the environment, and when each
           role was last read;
        3. directional families — how the tally lined up;
        4. evidence and independence audit — every item, behind a disclosure.

    Slice 1 built panels 3 and 4 and put them first, and the operator's own
    report was that the page answered an audit question before it answered a
    trading one. **Nothing from Slice 1 was removed to make room**: the full
    decision fields, thesis, confirmation and invalidation are one disclosure
    inside panel 1, and every evidence item is still rendered in full in panel
    4. What changed is the order and how many times one sentence is printed.

    Nothing here is computed, ranked or scored; the page is a renderer.
    """
    parts: list[str] = [
        _panel(
            f"{row.symbol} — decision",
            _kv(
                [
                    ("decision", _setup_chip(row.state)),
                    ("developing evidence", _developing_text(row.developing)),
                    (
                        "what is holding it",
                        _blocker_summary(row.blocker, row.reason),
                    ),
                    (
                        "HTF context",
                        _state_cell(row.timeframes, "context"),
                    ),
                    ("setup state", _state_cell(row.timeframes, "setup")),
                    ("evidence quality", _evidence_quality(row)),
                    ("data age", _freshness_cell(row.timeframes)),
                ]
            )
            + '<p class="note">The decision is the policy\'s. Developing '
            "evidence is what the readable families point at and is never a "
            "direction the policy stated — a leaning symbol is still whatever "
            "its decision says it is. Nothing here is a probability, a "
            "confidence or an expected return, and no number on this page "
            "ranks this symbol against another.</p>"
            + _details(
                "the decision in full",
                _kv(
                    [
                        ("classification", _e(row.classification)),
                        ("decision-context sufficiency", _e(row.sufficiency)),
                        (
                            "policy direction",
                            _text(row.direction, "no direction is stated"),
                        ),
                        ("current condition", _e(row.reason)),
                        (
                            "assessment as of",
                            _e(row.as_of.isoformat())
                            + '<br><span class="sub">the instant the assessment '
                            "carries. Per-role reading times are below.</span>",
                        ),
                    ]
                )
                + _details("full thesis", _list(row.thesis), open_=True)
                + _details("confirmation", _list(row.confirmation))
                + _details(
                    "invalidation", _list(row.invalidation) or _no_invalidation()
                ),
            ),
        ),
        _panel(
            f"{row.symbol} — timeframe context and data times",
            (
                _list(row.regime_context)
                or _empty(
                    "The engine stated no regime context line for this symbol."
                )
            )
            + _timeframe_table(row.timeframes),
        ),
    ]

    factor_table = _table(
        [("Family", ""), ("Lean", ""), ("Observed", ""), ("Source / timeframe", "")],
        [
            "<tr>"
            f"<td>{_e(_label(factor.family, _FAMILY_LABELS))}"
            f'<br><span class="sub">{_e(factor.family)}</span></td>'
            f"<td>{_setup_chip(factor.lean)}</td>"
            f"<td>{_e(factor.observed)}</td>"
            f"<td>{_e(factor.source)}</td>"
            "</tr>"
            for factor in row.factors
        ],
    )
    # `or` on the concatenation would never fire: the note alone is truthy, and
    # an empty table would render the explanation of a table that is not there.
    parts.append(
        _panel(
            f"{row.symbol} — directional families",
            (
                factor_table
                + '<p class="note">The families the policy tallies, and what '
                "each one read. A lean of <em>conflicting</em> means the family "
                "disagreed with itself and cast no vote; <em>unavailable</em> "
                "means nothing could be read from it. Neither is a vote, and "
                "these are counted, never weighted.</p>"
            )
            if factor_table
            else _empty("No directional family was recorded for this assessment."),
        )
    )

    if row.evidence_reason is not None:
        parts.append(
            _panel(f"{row.symbol} — evidence", _absent(row.evidence_reason))
        )
        return "".join(parts)

    # Every key some carried item declares it is not independent of. Folded
    # here rather than stored on the row: `fmis.operator_dashboard.models` holds
    # lookups and predicates only, and a guard asserts it.
    groups = (
        ("supporting", row.supporting, "Nothing supports this conclusion."),
        ("conflicting", row.conflicting, "Nothing conflicts with it."),
        (
            "missing",
            row.missing,
            "Nothing named by the policy is still awaited.",
        ),
        (
            "unavailable",
            row.unavailable,
            "Everything the projection names could be read.",
        ),
    )
    correlated = frozenset(
        key
        for _, items, _ in groups
        for item in items
        for key in item.correlated_with
    )
    notes = _IndependenceNotes()
    evidence = "".join(
        _details(
            f"{name} ({len(items)})",
            _evidence_item_rows(items, correlated, notes) or _empty(blank),
            open_=name in ("supporting", "conflicting"),
        )
        for name, items, blank in groups
    )
    independence = (
        "independence established"
        if row.independence_established
        else '<span class="absent">not established</span>'
    )
    # The audit sits *below* the summary and *behind* a disclosure, deliberately.
    # Everything Slice 1 built is here in full — this changes where it sits on
    # the page, never what it says.
    parts.append(
        _panel(
            f"{row.symbol} — evidence and independence audit",
            _kv(
                [
                    (
                        "agreeing families",
                        _text(
                            ", ".join(
                                _label(family, _FAMILY_LABELS)
                                for family in row.agreeing_families
                            ),
                            "none",
                        ),
                    ),
                    (
                        "conflicting families",
                        _text(
                            ", ".join(
                                _label(family, _FAMILY_LABELS)
                                for family in row.conflicting_families
                            ),
                            "none",
                        ),
                    ),
                    ("independence", independence),
                    (
                        "decision ready",
                        _e("yes" if row.decision_ready else "no")
                        + f'<br><span class="sub">{_e(row.decision_ready_reason)}</span>',
                    ),
                ]
            )
            + _details(
                "every evidence item, with its source and independence",
                evidence + notes.render(),
            )
            + _details(
                "independence caveats", _list(row.independence_caveats)
            )
            + _details("warnings", _list(row.evidence_warnings))
            + _details("open questions", _list(row.open_questions))
            + '<p class="note">Counts of evidence items are counts, not a score. '
            "Items that share an upstream input are marked <em>not "
            "independent</em>, with the explanation printed once beneath the "
            "table and referenced from each row, and must not be read as "
            "separate confirmation. No probability, confidence or expected "
            "return is computed anywhere on this page.</p>",
        )
    )
    return "".join(parts)


def _swing_body(view: SwingView) -> str:
    parts: list[str] = []
    parts.append("<h3>This scan</h3>")
    parts.append(_swing_snapshot(view.snapshot))
    parts.append("<h3>Every scanned symbol</h3>")
    parts.append(
        _decision_rows(view.decisions)
        or _empty("No symbol produced an assessment on this refresh.")
    )
    if view.decisions:
        parts.append(f'<p class="note">{_e(_DECISION_ORDER_NOTE)}</p>')
    parts.append("<h3>Top opportunities</h3>")
    parts.append(
        _setup_rows(view.opportunities)
        or _empty(
            "No setup is confirmed or a candidate on this refresh. That is a "
            "conclusion, not a failure."
        )
    )
    parts.append("<h3>Wait list</h3>")
    parts.append(
        _setup_rows(view.wait_list)
        or _empty("Nothing is waiting on a confirmation.")
    )
    parts.append("<h3>No trade</h3>")
    no_trade = _table(
        [("Reason", ""), ("Classification", ""), ("Symbols", "")],
        [
            "<tr>"
            f"<td>{_e(row.reason)}</td>"
            f"<td>{_e(row.classification)}</td>"
            f'<td class="sym">{_e(", ".join(row.symbols))}</td>'
            "</tr>"
            for row in view.no_trade
        ],
    )
    parts.append(
        no_trade
        or _empty("No symbol was concluded a no-trade on this refresh.")
    )
    if view.no_trade:
        parts.append(
            '<p class="note">A distribution over the conditions the engine '
            "named, not a ranking of them. Each symbol above has its own row "
            "in <em>every scanned symbol</em>, with the evidence behind its "
            "conclusion.</p>"
        )
    parts.append("<h3>Could not be read</h3>")
    unreadable = _table(
        [("Symbol", "sym"), ("Detail", "")],
        [
            f'<tr><td class="sym">{_e(row.symbol)}</td><td>{_e(row.detail)}</td></tr>'
            for row in view.unreadable
        ],
    )
    parts.append(
        unreadable
        or _empty("Every scanned symbol produced a readable analysis.")
    )
    if view.ranking_rule:
        parts.append(
            f'<p class="note">Ordering: {_e(view.ranking_rule)} This surface '
            "does not reorder anything.</p>"
        )
    return "".join(parts)


def _swing_detail(row: SetupRow) -> str:
    """One symbol's full picture. Every field is the engines' own; none is new."""
    parts: list[str] = []
    parts.append(
        _panel(
            f"{row.symbol} — setup",
            _kv(
                [
                    ("state", _setup_chip(row.state)),
                    ("direction", _text(row.direction, "no direction is stated")),
                    ("sufficiency", _text(row.sufficiency)),
                    ("approval", _text(row.approval_status, "no approval was produced")),
                    (
                        "risk / reward",
                        _measured(
                            row.risk_reward,
                            "no risk/reward was produced",
                            lambda value: f"{value:.2f}",
                        ),
                    ),
                    (
                        "stop",
                        _measured(row.stop, "no stop was produced", lambda v: f"{v:g}"),
                    ),
                    (
                        "target",
                        _measured(
                            row.target, "no target was produced", lambda v: f"{v:g}"
                        ),
                    ),
                    (
                        "recommended size",
                        _text(row.recommended_size, "no size was produced"),
                    ),
                    (
                        "open risk after",
                        _text(row.open_risk_after, "no figure was produced"),
                    ),
                ]
            ),
        )
    )
    if row.evidence is not None:
        digest = row.evidence
        parts.append(
            _panel(
                f"{row.symbol} — evidence",
                _kv(
                    [
                        ("supporting", _e(digest.supporting)),
                        ("conflicting", _e(digest.conflicting)),
                        ("missing", _e(digest.missing)),
                        ("unavailable", _e(digest.unavailable)),
                        (
                            "agreeing families",
                            _text(", ".join(digest.agreeing_families), "none"),
                        ),
                        (
                            "conflicting families",
                            _text(", ".join(digest.conflicting_families), "none"),
                        ),
                        (
                            "independence established",
                            _e("yes" if digest.independence_established else "no"),
                        ),
                        (
                            "decision ready",
                            _e("yes" if digest.decision_ready else "no")
                            + f'<br><span class="sub">{_e(digest.decision_ready_reason)}</span>',
                        ),
                    ]
                )
                + _details("caveats", _list(digest.caveats)),
            )
        )
    else:
        parts.append(
            _panel(f"{row.symbol} — evidence", _absent(row.evidence_reason))
        )
    parts.append(
        _panel(
            f"{row.symbol} — thesis, confirmation, invalidation",
            _details("thesis", _list(row.thesis), open_=True)
            + _details("confirmation", _list(row.confirmation), open_=True)
            + _details("invalidation", _list(row.invalidation), open_=True)
            or _empty("No thesis, confirmation or invalidation was produced."),
        )
    )
    parts.append(
        _panel(
            f"{row.symbol} — identity, paper and holdings",
            _kv(
                [
                    ("stable identity", _text(row.identity, row.identity_reason)),
                    (
                        "paper trade",
                        _text(row.paper_status, "no paper trade for this symbol"),
                    ),
                    ("held", _text(row.held, "not held")),
                ]
            ),
        )
    )
    ordering = _table(
        [("Component", ""), ("Value", "")],
        [
            f"<tr><td>{_e(name)}</td><td>{_e(value)}</td></tr>"
            for name, value in row.rank_components
        ],
    )
    blocking = _details("blocking reasons", _list(row.blocking_reasons))
    warnings = _details("approval warnings", _list(row.approval_warnings))
    parts.append(
        _panel(
            f"{row.symbol} — ordering and warnings",
            (ordering or _empty("No ordering key was recorded for this row."))
            + blocking
            + warnings,
        )
    )
    return "".join(parts)


# ---------------------------------------------------------------------------
# Portfolio, paper, performance
# ---------------------------------------------------------------------------


def _portfolio_body(view: PortfolioView) -> str:
    tiles = "".join(
        [
            _tile("Open positions", _e(len(view.positions))),
            _tile("Cash", _text(view.cash, view.cash_reason), small=True),
            _tile("Exposure", _text(view.exposure, view.exposure_reason), small=True),
            _tile(
                "Market value",
                _text(view.market_value, view.market_value_reason),
                small=True,
            ),
            _tile(
                "Unrealized",
                _text(view.unrealized_pnl, view.unrealized_pnl_reason),
                small=True,
            ),
            _tile(
                "Committed risk",
                _text(view.committed_risk, view.committed_risk_reason),
                small=True,
            ),
            _tile(
                "Available risk",
                _text(view.available_risk, view.available_risk_reason),
                small=True,
            ),
        ]
    )
    positions = _table(
        [
            ("Market", "sym"),
            ("Book", ""),
            ("Direction", ""),
            ("Quantity", "num"),
            ("Avg entry", "num"),
            ("Mark", "num"),
            ("Market value", "num"),
            ("Unrealized", "num"),
            ("Opened", ""),
        ],
        [
            "<tr>"
            f'<td class="sym">{_e(row.market)}</td>'
            f"<td>{_e(row.book)}</td>"
            f"<td>{_e(row.direction)}</td>"
            f'<td class="num">{_e(row.quantity)}</td>'
            f'<td class="num">{_e(row.average_entry)}</td>'
            f'<td class="num">{_text(row.mark, "no mark was read for this market")}</td>'
            f'<td class="num">{_text(row.market_value, "no mark, so no value")}</td>'
            f'<td class="num">{_text(row.unrealized_pnl, "no mark, so no unrealized figure")}</td>'
            f"<td>{_stamp(row.opened_at)}</td>"
            "</tr>"
            for row in view.positions
        ],
    )
    books = _table(
        [("Book", ""), ("Open positions", "num"), ("Market value", "num")],
        [
            "<tr>"
            f"<td>{_e(row.label)}</td>"
            f'<td class="num">{_e(row.open_positions)}</td>'
            f'<td class="num">{_text(row.market_value, row.market_value_reason)}</td>'
            "</tr>"
            for row in view.books
        ],
    )
    limits = _table(
        [
            ("Limit", ""),
            ("Scope", ""),
            ("Stated", "num"),
            ("Current", "num"),
            ("Status", ""),
            ("Severity", ""),
        ],
        [
            "<tr>"
            f"<td>{_e(row.limit_id)}</td>"
            f"<td>{_e(row.scope)}</td>"
            f'<td class="num">{_e(row.stated_limit)}</td>'
            f'<td class="num">{_text(row.current, row.current_reason)}</td>'
            f"<td>{_text(row.status, row.status_reason)}</td>"
            f"<td>{_e(row.severity)}</td>"
            "</tr>"
            for row in view.limits
        ],
    )
    parts = [f'<div class="tiles">{tiles}</div>']
    parts.append(
        '<p class="note">These are recorded positions only. Simulated trades '
        'are on the <a href="/paper">Paper</a> page and are never added into '
        "any figure above.</p>"
    )
    parts.append(positions or _empty("No open position is recorded."))
    if books:
        parts.append(_details("books", books, open_=True))
    if limits:
        parts.append(_details("risk limits", limits, open_=True))
    notes = [note for note in (view.budget_note, view.marks_note) if note]
    if notes:
        parts.append(_details("notes", _list(notes)))
    return "".join(parts)


def _paper_body(view: PaperView) -> str:
    rows = _table(
        [
            ("Activation", ""),
            ("Market", "sym"),
            ("State", ""),
            ("Open size", "num"),
            ("Entry", "num"),
            ("Stop", "num"),
            ("Initial stop", "num"),
            ("Initial risk", "num"),
            ("Total R", "num"),
            ("MFE R", "num"),
            ("MAE R", "num"),
            ("Bars", "num"),
            ("Widenings", "num"),
        ],
        [
            "<tr>"
            f"<td>{_e(row.activation_id)}</td>"
            f'<td class="sym">{_e(row.market)}</td>'
            f"<td>{_setup_chip(row.state)}</td>"
            f'<td class="num">{_e(row.open_size)}</td>'
            f'<td class="num">{_text(row.entry, row.entry_reason)}</td>'
            f'<td class="num">{_e(row.stop)}</td>'
            f'<td class="num">{_e(row.initial_stop)}</td>'
            f'<td class="num">{_text(row.initial_risk, row.initial_risk_reason)}</td>'
            f'<td class="num">{_text(row.total_r, row.total_r_reason)}</td>'
            f'<td class="num">{_text(row.max_favourable_r, row.max_favourable_r_reason)}</td>'
            f'<td class="num">{_text(row.max_adverse_r, row.max_adverse_r_reason)}</td>'
            f'<td class="num">{_e(row.bars_in_trade)}</td>'
            f'<td class="num">{_e(row.stop_widenings)}</td>'
            "</tr>"
            for row in view.rows
        ],
    )
    parts = [
        '<p class="note">Simulated trades. None of it is real exposure, and '
        "none of it appears in any portfolio figure.</p>"
    ]
    parts.append(rows or _empty("No paper trade is recorded."))
    if view.note:
        parts.append(f'<p class="note">{_e(view.note)}</p>')
    return "".join(parts)


def _equity_chart(view: PerformanceView) -> str:
    """The cumulative curve, one step per closed trade.

    **Pixels are interpolated; observations are not.** The polyline between two
    points is a drawing convenience — no trade closed between them, and the note
    under the chart says so. Scaling values into a viewBox is coordinate
    arithmetic, not a financial calculation: no figure here is new, and every
    vertex is a `cumulative` the statistics engine produced.
    """
    points = view.equity
    if len(points) < 2:
        return _empty(
            "A curve needs at least two closed trades. Nothing is interpolated "
            "to fill the gap."
        )
    values = [float(point.cumulative) for point in points]
    low = min(values)
    high = max(values)
    span = high - low
    if span == 0:
        span = 1.0
    width = EQUITY_CHART_WIDTH
    height = EQUITY_CHART_HEIGHT
    pad = 22
    step = (width - 2 * pad) / (len(values) - 1)

    def _y(value: float) -> float:
        return height - pad - ((value - low) / span) * (height - 2 * pad)

    coords = [
        (pad + index * step, _y(value)) for index, value in enumerate(values)
    ]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    zero = ""
    if low <= 0 <= high:
        zero_y = _y(0.0)
        zero = (
            f'<line class="zero" x1="{pad}" y1="{zero_y:.1f}" '
            f'x2="{width - pad}" y2="{zero_y:.1f}"/>'
        )
    dots = "".join(
        f'<circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="2"><title>'
        f"{_e(points[index].trade_ref)} · {_e(points[index].cumulative)} "
        f"{_e(view.quote_asset)}</title></circle>"
        for index, (x, y) in enumerate(coords)
    )
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Cumulative realized profit and loss in {_e(view.quote_asset)}">'
        f'<line class="axis" x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}"/>'
        f"{zero}"
        f'<polyline class="line" points="{path}"/>'
        f"{dots}"
        f'<text x="{pad}" y="14">{_e(f"{high:,.2f}")}</text>'
        f'<text x="{pad}" y="{height - 6}">{_e(f"{low:,.2f}")}</text>'
        "</svg>"
        f'<p class="note">{_e(view.equity_basis)} The line between two points '
        "is drawn, not observed — no trade closed between them.</p>"
    )


def _performance_body(views: tuple[PerformanceView, ...]) -> str:
    parts: list[str] = []
    for view in views:
        tiles = "".join(
            [
                _tile("Trades", _e(view.trades)),
                _tile("Open", _e(view.open_trades)),
                _tile("Resolved", _e(view.resolved)),
                _tile("Sample floor", _e(view.sample_floor)),
                _tile("Net", _text(view.net, view.net_reason), small=True),
                _tile(
                    "Expectancy",
                    _text(view.expectancy, view.expectancy_reason),
                    small=True,
                ),
                _tile(
                    "Win rate", _text(view.win_rate, view.win_rate_reason), small=True
                ),
                _tile(
                    "Profit factor",
                    _text(view.profit_factor, view.profit_factor_reason),
                    small=True,
                ),
                _tile(
                    "Average R",
                    _text(view.average_r, view.average_r_reason),
                    small=True,
                ),
                _tile(
                    "Max drawdown",
                    _text(view.max_drawdown, view.max_drawdown_reason),
                    small=True,
                ),
            ]
        )
        body = [f'<div class="tiles">{tiles}</div>']
        body.append(
            f'<p class="note">Figures are stated in {_e(view.quote_asset)} and '
            "are never summed across quote assets. A rate below the sample "
            "floor is refused rather than printed, and says so.</p>"
        )
        if view.floor_note:
            body.append(f'<p class="note">{_e(view.floor_note)}</p>')
        body.append(_equity_chart(view))
        steps = _table(
            [("Closed", ""), ("Trade", ""), ("Delta", "num"), ("Cumulative", "num")],
            [
                "<tr>"
                f"<td>{_stamp(point.at)}</td>"
                f"<td>{_e(point.trade_ref)}</td>"
                f'<td class="num">{_e(point.delta)}</td>'
                f'<td class="num">{_e(point.cumulative)}</td>'
                "</tr>"
                for point in view.equity
            ],
        )
        if steps:
            body.append(_details("every closed-trade step", steps))
        if view.equity_excluded:
            body.append(_details("excluded from the curve", _list(view.equity_excluded)))
        parts.append(_panel(f"Performance — {view.quote_asset}", "".join(body)))
    return "".join(parts)


# ---------------------------------------------------------------------------
# System / data health
# ---------------------------------------------------------------------------


def _health_body(view: DataHealthView) -> str:
    rows = _table(
        [
            ("Source", "sym"),
            ("Label", ""),
            ("State", ""),
            ("Last observation", ""),
            ("Age", "num"),
            ("Provider", ""),
            ("Detail", ""),
        ],
        [
            "<tr>"
            f'<td class="sym">{_e(row.source_id)}</td>'
            f"<td>{_e(row.label)}</td>"
            f"<td>{_state_chip(row.state)}</td>"
            f"<td>{_stamp(row.last_observation)}</td>"
            f'<td class="num">{_e(_duration(row.age)) if row.age is not None else _absent("no age is stated for this source")}</td>'
            f"<td>{_text(row.provider, 'no provider is named for this source')}</td>"
            f"<td>{_text(row.detail, 'no detail was stated')}</td>"
            "</tr>"
            for row in view.sources
        ],
    )
    counts = "".join(
        _tile(state.value.replace("_", " "), _e(len(view.with_state(state))))
        for state in SourceState
    )
    return (
        f'<div class="tiles">{counts}</div>'
        '<p class="note">Counts, not a score. There is deliberately no single '
        "health figure: sources publish on different schedules, and one number "
        "over all of them would be a judgement this system has no basis to "
        "make. <b>Behind schedule</b> means older than that source's own "
        "publication cadence explains — not that the number is wrong. "
        "<b>Unsupported</b> means this build has no provider for that market at "
        "all, which is permanent rather than an outage.</p>"
        f"{rows or _empty('No source was touched on this refresh.')}"
    )


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------


def _warnings_body(warnings: Sequence[WarningRow]) -> str:
    if not warnings:
        return _empty("No warning was raised on this refresh.")
    rows = [
        "<tr>"
        f'<td class="sym">{_e(row.code)}</td>'
        f'<td><span class="chip sev-{_e(row.severity.lower())}">{_e(row.severity)}</span></td>'
        f"<td>{_e(row.kind)}</td>"
        f"<td>{_e(row.statement)}"
        + (
            f'<br><span class="sub">{_e(row.evidence)}</span>'
            if row.evidence
            else ""
        )
        + "</td>"
        f'<td class="sym">{_e(", ".join(row.subjects))}</td>'
        "</tr>"
        for row in warnings
    ]
    return _table(
        [
            ("Code", "sym"),
            ("Severity", ""),
            ("Kind", ""),
            ("Statement", ""),
            ("Subjects", "sym"),
        ],
        rows,
    )


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def _overview(snapshot: OperatorDashboardSnapshot) -> str:
    counts = snapshot.counts
    parts: list[str] = []
    parts.append(
        _panel(
            "Swing",
            f'<div class="tiles">'
            + _tile("Scanned", _e(counts.scanned))
            + _tile("Confirmed", _e(counts.confirmed))
            + _tile("Candidates", _e(counts.candidates))
            + _tile("Waiting", _e(counts.waiting))
            + _tile("Unreadable", _e(counts.unreadable))
            + _tile("Open positions", _e(counts.open_positions))
            + _tile("Paper trades", _e(counts.paper_positions))
            + "</div>"
            + (
                _setup_rows(snapshot.swing.data.opportunities)
                if snapshot.swing.data is not None
                and snapshot.swing.data.opportunities
                else _empty(
                    "No confirmed or candidate setup on this refresh. A quiet "
                    "market is a legitimate result."
                )
            ),
            meta=_section_meta(snapshot.swing),
        )
        if not snapshot.swing.failed
        else _panel("Swing", _failed(snapshot.swing))
    )

    parts.append(
        _guarded(
            snapshot.pulse,
            "Global market pulse",
            lambda view: _pulse_rows(view)
            + '<p class="note">Full detail on the <a href="/markets">Markets</a> page.</p>',
        )
    )
    parts.append(
        _guarded(
            snapshot.portfolio,
            "Portfolio",
            lambda view: '<div class="tiles">'
            + _tile("Open positions", _e(len(view.positions)))
            + _tile("Exposure", _text(view.exposure, view.exposure_reason), small=True)
            + _tile(
                "Committed risk",
                _text(view.committed_risk, view.committed_risk_reason),
                small=True,
            )
            + _tile(
                "Available risk",
                _text(view.available_risk, view.available_risk_reason),
                small=True,
            )
            + "</div>",
        )
    )
    parts.append(
        _guarded(
            snapshot.performance,
            "Performance",
            lambda views: "".join(
                '<div class="tiles">'
                + _tile("Asset", _e(view.quote_asset), small=True)
                + _tile("Sample n", _e(view.trades))
                + _tile("Net", _text(view.net, view.net_reason), small=True)
                + _tile(
                    "Expectancy",
                    _text(view.expectancy, view.expectancy_reason),
                    small=True,
                )
                + _tile(
                    "Profit factor",
                    _text(view.profit_factor, view.profit_factor_reason),
                    small=True,
                )
                + _tile(
                    "Max drawdown",
                    _text(view.max_drawdown, view.max_drawdown_reason),
                    small=True,
                )
                + "</div>"
                for view in views
            ),
        )
    )
    parts.append(
        _guarded(
            snapshot.health,
            "Data health",
            lambda view: '<div class="tiles">'
            + "".join(
                _tile(state.value.replace("_", " "), _e(len(view.with_state(state))))
                for state in SourceState
            )
            + "</div>"
            + '<p class="note">Detail on the <a href="/system">System</a> page.</p>',
        )
    )
    parts.append(_panel("Warnings", _warnings_body(snapshot.warnings)))
    return "".join(parts)


def _markets(snapshot: OperatorDashboardSnapshot) -> str:
    return _guarded(snapshot.pulse, "Global market pulse", _pulse_body) + _guarded(
        snapshot.macro, "Macro & cross-asset context", _macro_body
    )


def _swing(snapshot: OperatorDashboardSnapshot) -> str:
    return _guarded(snapshot.swing, "Swing decision workspace", _swing_body)


def _symbol_page(snapshot: OperatorDashboardSnapshot, symbol: str) -> str:
    """One symbol's detail, whatever the engine concluded about it.

    **Two sources, and the decision one covers the whole scanned universe.**
    `row_for` finds a `SetupRow`, which exists only for an actionable or waiting
    setup; `decision_for` finds the decision record, which exists for every
    symbol that produced an assessment at all — including every `WAIT`. Before
    this page carried decisions, a waiting BTCUSDT reached the *not on this
    page* message while the engine had in fact produced a full assessment,
    three directional factors, a regime reading and a complete evidence report
    for it. Now the decision panels render for it, and the setup panels are
    added on top when there is also a `SetupRow`.

    A symbol with neither still gets the honest statement: it produced no
    analysis on this refresh, which the Swing page's *could not be read*
    section names.
    """
    back = '<p class="note"><a href="/swing">Back to Swing</a></p>'
    if snapshot.swing.failed:
        return _panel("Swing", _failed(snapshot.swing))
    view = snapshot.swing.data
    row = None if view is None else view.row_for(symbol)
    decision = None if view is None else view.decision_for(symbol)
    if row is None and decision is None:
        return _panel(
            f"{symbol}",
            _empty(
                f"{symbol} produced no assessment on this refresh. It may not "
                "have been readable, or may not be on the scanned watchlist — "
                "the Swing page states which."
            )
            + back,
        )
    parts = []
    if decision is not None:
        parts.append(_decision_detail(decision))
    if row is not None:
        parts.append(_swing_detail(row))
    return "".join(parts) + back


def _portfolio(snapshot: OperatorDashboardSnapshot) -> str:
    return _guarded(snapshot.portfolio, "Portfolio", _portfolio_body)


def _paper(snapshot: OperatorDashboardSnapshot) -> str:
    return _guarded(snapshot.paper, "Paper trades", _paper_body)


def _performance(snapshot: OperatorDashboardSnapshot) -> str:
    if snapshot.performance.failed:
        return _panel(
            "Performance",
            _failed(snapshot.performance),
            meta=_section_meta(snapshot.performance),
        )
    views = snapshot.performance.data
    if not views:
        return _panel(
            "Performance",
            _empty(_empty_message("performance")),
            meta=_section_meta(snapshot.performance),
        )
    return _performance_body(views)


def _system(snapshot: OperatorDashboardSnapshot) -> str:
    parts = [_guarded(snapshot.health, "Data health", _health_body)]
    sections = _table(
        [("DashboardSection", ""), ("Status", ""), ("As of", ""), ("Source", "")],
        [
            "<tr>"
            f'<td class="sym">{_e(section.name)}</td>'
            f"<td>{_chip(section.status.value, section.status.value)}</td>"
            f"<td>{_stamp(section.as_of)}</td>"
            f"<td>{_text(section.source, section.unavailable_reason)}</td>"
            "</tr>"
            for section in snapshot.sections
        ],
    )
    parts.append(_panel("Sections read this refresh", sections))
    parts.append(
        _panel(
            "What this surface cannot do",
            _kv(
                [(name, _e(statement)) for name, statement in snapshot.limitations]
            ),
        )
    )
    return "".join(parts)


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------


def _header(snapshot: OperatorDashboardSnapshot, active: str) -> str:
    """The header. **Last refresh and data instant are always both present.**

    A page that showed only one would let an hour-old snapshot look live. The
    refresh instant says when this HTML was built; each panel's own `as_of` says
    what moment its figures describe, and the two are routinely different.
    """
    tabs = "".join(
        f'<a href="{_e(path)}" class="{"on" if path == active else ""}">{_e(title)}</a>'
        for path, title in PAGES
    )
    failures = len(snapshot.failed_sections)
    failure_note = (
        f' · <span class="chip state-unavailable">{failures} section(s) unavailable</span>'
        if failures
        else ""
    )
    # A link, not a button, and deliberately: a button implies a form, a form
    # implies a POST, and this surface has no method that could change anything.
    # Re-reading the engines is the only thing "refresh" does.
    refresh = f'<a href="{_e(active)}?refresh=1">refresh now</a>'
    return (
        '<header class="top"><div class="brand">'
        "<h1>FMITS Operator Dashboard</h1>"
        '<span class="ro">read only · v0</span>'
        '<div class="stamps">'
        f"<span>last refresh <b>{_stamp(snapshot.refreshed_at)}</b></span>"
        f"<span>data as of <b>{_stamp(snapshot.reference_time)}</b></span>"
        f"<span>schema <b>{_e(snapshot.schema_version)}</b>{failure_note}</span>"
        f"<span>{refresh}</span>"
        "</div></div>"
        f'<nav class="tabs">{tabs}</nav></header>'
    )


def _footer() -> str:
    return (
        '<footer class="foot">'
        "<p>This surface reads FMITS. It places no order, records no trade, "
        "activates no paper trade and changes no stored value. No write method "
        "is reachable from it.</p>"
        "<p>Nothing here is a recommendation. Colour marks a measured number's "
        "sign, a status or an availability — never a suggested action. WAIT and "
        "NO TRADE are conclusions, not failures. An unavailable figure is not a "
        "zero, and every one of them states its reason.</p>"
        "<p>The page is not live. It shows what one refresh read; reload to "
        "refresh.</p>"
        "</footer>"
    )



def _lab(snapshot: OperatorDashboardSnapshot) -> str:
    """The Swing Lab page. **Read-only, and a record rather than a live read.**

    There is no control on this page that could change a strategy, and there is
    nothing to click that runs anything. A lab study replays years of history
    over several minutes, so what is shown is a saved experiment the operator
    passed in — which the page states, rather than letting a stale table read as
    a live one.
    """
    section = snapshot.lab
    if section is None or section.data is None:
        return _panel(
            "Swing Lab",
            "<p class='muted'>No experiment is loaded. Run one with "
            "<code>fmits research swing SYMBOL --start ... --save study.lab.json</code> "
            "and start the dashboard with <code>--lab-artifact study.lab.json</code>. "
            "This page shows a saved research record; it never runs a replay "
            "itself and never changes a strategy.</p>",
        )
    view = section.data
    head = (
        "<dl class='meta'>"
        f"<dt>Experiment</dt><dd>{_e(view.experiment_id)}</dd>"
        f"<dt>Symbols</dt><dd>{_e(', '.join(view.symbols))}</dd>"
        f"<dt>Window</dt><dd>{_e(view.measurement_start)} → {_e(view.measurement_end)}</dd>"
        f"<dt>Timeframes</dt><dd>{_e('; '.join(view.interval_groups))}</dd>"
        f"<dt>Costs</dt><dd>{_e(view.cost_policy)}</dd>"
        f"<dt>Digest</dt><dd><code>{_e(view.result_digest)}</code> "
        f"({'verified' if view.digest_verified else 'NOT VERIFIED'})</dd>"
        "</dl>"
    )

    def cell(value: str | None, reason: str | None) -> str:
        if value is None:
            return f"<td class='absent'>unavailable<small>{_e(reason or '')}</small></td>"
        return f"<td>{_e(value)}</td>"

    rows = []
    for variant in view.variants:
        rows.append(
            "<tr>"
            f"<th scope='row'>{_e(variant.variant_id)}"
            f"{' <span class=\'tag\'>baseline</span>' if variant.is_baseline else ''}"
            f"<small>{_e(variant.title)}</small></th>"
            f"<td class='verdict'>{_e(variant.verdict.replace('_', ' '))}</td>"
            f"<td>{variant.trades}</td>"
            f"<td>{variant.measurable}</td>"
            f"<td>{variant.ambiguous}</td>"
            f"<td>{variant.wins}/{variant.losses}</td>"
            + cell(variant.win_rate, variant.win_rate_reason)
            + cell(variant.expectancy, variant.expectancy_reason)
            + cell(variant.median_r, variant.median_r_reason)
            + cell(variant.profit_factor, variant.profit_factor_reason)
            + f"<td>{_e(variant.total_r)}</td>"
            f"<td>{_e(variant.max_drawdown)}</td>"
            "</tr>"
        )
    table = (
        "<table><thead><tr><th>Variant</th><th>Verdict</th><th>Trades</th><th>Measurable</th>"
        "<th>Ambiguous</th><th>W/L</th><th>Win rate</th><th>Expectancy R</th>"
        "<th>Median R</th><th>Profit factor</th><th>Total R</th>"
        "<th>Max DD (R)</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )

    gate = view.gate
    gate_html = ""
    if gate is not None:
        gate_html = _panel(
            "What the 1W gate did",
            "<dl class='meta'>"
            f"<dt>Instants judged</dt><dd>{gate.instants}</dd>"
            f"<dt>Gate never reached</dt><dd>{gate.not_reached}</dd>"
            f"<dt>Allowed</dt><dd>{gate.allowed}</dd>"
            f"<dt>Blocked, nothing to block</dt><dd>{gate.blocked_without_effect}</dd>"
            f"<dt>Blocked a CANDIDATE</dt><dd>{gate.blocked_candidate}</dd>"
            f"<dt>Blocked a CONFIRMED setup</dt><dd>{gate.blocked_confirmed}</dd>"
            f"<dt>Materially blocked</dt><dd>{gate.blocked_candidate + gate.blocked_confirmed}"
            "<small>the only count that means the gate removed something</small></dd>"
            f"<dt>Blocked long / short</dt><dd>{gate.blocked_long} / {gate.blocked_short}</dd>"
            "</dl>"
            f"<p class='muted'>{_e(gate.counterfactual_note)}</p>",
        )

    verdicts = "".join(
        f"<li><strong>{_e(item.variant_id)}</strong> — "
        f"<em>{_e(item.verdict.replace('_', ' '))}</em>: "
        f"{_e(item.verdict_statement)}</li>"
        for item in view.variants
    )

    hypotheses = "".join(
        f"<li><strong>{_e(item.variant_id)}</strong> — {_e(item.hypothesis)}"
        f"<br><small><code>{_e(item.policy_id)}</code></small></li>"
        for item in view.variants
    )
    limitations = "".join(f"<li>{_e(item)}</li>" for item in view.limitations)
    return (
        _panel("Swing Lab — saved experiment", head + table)
        + _panel(
            "Verdicts",
            f"<ul>{verdicts}</ul>"
            "<p class='muted'>Each verdict is <strong>derived from the measured "
            "expectancy alone</strong> and can be recomputed from this "
            "experiment's own artifact. No verdict this system produces "
            "approves live trading; the strongest one available means "
            "<em>worth testing forward</em>.</p>",
        )
        + gate_html
        + _panel("Pre-specified hypotheses", f"<ul>{hypotheses}</ul>")
        + _panel("Limitations", f"<ul>{limitations}</ul>")
        + _panel(
            "This page promotes nothing",
            "<p class='muted'>A variant that measures well here is a candidate "
            "for forward testing and nothing more. The production strategy is "
            "unchanged by this experiment and cannot be changed from this "
            "page.</p>",
        )
    )


def _validation(snapshot: OperatorDashboardSnapshot) -> str:
    """The Pre-Registered Validation page. **Designed for a decision, not completeness.**

    The order is the argument, and it is the same one the terminal report makes:

    1. **the verdict first**, because a reader who stops after one screen must
       not come away with a different impression from one who reads to the end;
    2. **the seal** — which pre-registration these numbers were judged under, and
       whether it still matches the repository;
    3. the samples, each with its contamination **beside** it rather than in a
       footnote;
    4. the results, in pre-registration order and never sorted by expectancy;
    5. the plateau, with the failing neighbours shown as rows like any other;
    6. costs, with the deciding scenario marked;
    7. walk-forward and the decompositions;
    8. the limitations, in full.

    There is no ranked table and no "best rule". Sorting by result would be
    choosing one, and the sealed criteria exist so that choice is not a
    judgement call.
    """
    section = snapshot.validation
    if section is None or not section.is_available or section.data is None:
        return _panel(
            "Pre-Registered Validation",
            "<p class='muted'>No validation study is loaded. Run one with "
            "<code>fmits research validation --open-holdout --save "
            "validation.json</code> and start the dashboard with "
            "<code>--validation-artifact validation.json</code>. This page shows "
            "a saved research record; it never runs a replay itself and never "
            "changes a strategy.</p>",
        )
    view = section.data

    seal = (
        "<dl class='meta'>"
        f"<dt>Experiment</dt><dd>{_e(view.experiment_id)}</dd>"
        f"<dt>Pre-registration</dt><dd>{_e(view.preregistration_id)}"
        f"<small><code>{_e(view.preregistration_digest)}</code></small></dd>"
        "<dt>Seal</dt><dd>"
        + (
            _chip("matches this repository", "ok")
            if view.seal_matches
            else _chip("DOES NOT MATCH — judged under different rules", "bad")
        )
        + "</dd>"
        f"<dt>Deciding cost scenario</dt><dd>{_e(view.deciding_cost_policy_id)}"
        "<small>no candidate may be selected on the frictionless column</small></dd>"
        "<dt>Holdout</dt><dd>"
        + (
            _chip("opened", "warn")
            if view.holdout_opened
            else _chip("NOT opened — development pass", "muted")
        )
        + "</dd><dt>No-lookahead suite</dt><dd>"
        + (
            _chip("proven for this capture", "ok")
            if view.no_lookahead_proven
            else _chip("NOT PROVEN", "bad")
        )
        + "</dd>"
        f"<dt>Digest</dt><dd><code>{_e(view.result_digest)}</code> "
        f"({'verified' if view.digest_verified else 'NOT VERIFIED'})</dd>"
        "</dl>"
    )

    winners = view.candidate_policy_ids
    if winners:
        verdict_html = (
            f"<p><strong>{len(winners)} of {len(view.policies)}</strong> "
            "pre-registered hypotheses met every sealed criterion:</p><ul>"
            + "".join(f"<li><code>{_e(item)}</code></li>" for item in winners)
            + "</ul><p class='muted'><strong>RESEARCH CANDIDATE — NOT LIVE.</strong> "
            "A candidate for forward testing is <strong>worth testing "
            "forward</strong> and nothing more. It is not approval to trade, and "
            "production remains the current policy.</p>"
        )
    else:
        verdict_html = (
            "<p><strong>NO FORWARD-TEST CANDIDATE.</strong> No pre-registered "
            "hypothesis met every sealed criterion, so none is proposed for "
            "forward or shadow testing.</p>"
            "<p class='muted'>This is a result, not a missing measurement — the "
            "criteria each hypothesis failed are listed below by name.</p>"
        )

    samples_html = "".join(
        f"<details><summary><strong>{_e(row.name.upper())}</strong> "
        f"{_e(row.signal_start[:10])} → {_e(row.signal_end[:10])} · "
        f"{len(row.symbols)} symbols · {row.candidates} candidates</summary>"
        f"<p>{_e(row.contamination)}</p>"
        f"<p class='muted'><small>{_e(', '.join(row.symbols))}</small></p>"
        "</details>"
        for row in view.samples
    )
    if view.unclaimed_candidates:
        samples_html += (
            f"<p class='muted'>{view.unclaimed_candidates} captured candidates "
            "fall in no sample and are measured by nothing. Reported rather "
            "than dropped.</p>"
        )

    def cell(value: str | None, reason: str | None = None) -> str:
        if value is None:
            return f"<td class='absent'>unavailable<small>{_e(reason or '')}</small></td>"
        return f"<td>{_e(value)}</td>"

    rows = []
    for policy in view.policies:
        deciding = [item for item in policy.cells if item.is_deciding]
        for index, item in enumerate(deciding):
            rows.append(
                "<tr>"
                + (
                    f"<th scope='row' rowspan='{len(deciding)}'>"
                    f"<code>{_e(policy.policy_id)}</code>"
                    f" <span class='tag'>{_e(policy.role)}</span>"
                    + (
                        ""
                        if policy.is_structural
                        else " <span class='tag'>NON-STRUCTURAL</span>"
                    )
                    + f"<small>{_e(policy.hypothesis_id)} · {_e(policy.title)}</small></th>"
                    f"<td class='verdict' rowspan='{len(deciding)}'>"
                    f"{_e(policy.verdict.replace('_', ' '))}</td>"
                    if index == 0
                    else ""
                )
                + f"<td>{_e(item.sample)}</td>"
                f"<td>{item.trades}</td><td>{item.refused}</td>"
                f"<td>{item.measurable}</td><td>{item.ambiguous}</td>"
                + cell(item.win_rate)
                + cell(item.expectancy, item.expectancy_reason)
                + cell(item.profit_factor)
                + f"<td>{_e(item.total_r)}</td><td>{_e(item.max_drawdown)}</td>"
                "</tr>"
            )
    table = (
        "<table><thead><tr><th>Hypothesis</th><th>Verdict</th><th>Sample</th>"
        "<th>Trades</th><th>Refused</th><th>Measurable</th><th>Ambiguous</th>"
        "<th>Win rate</th><th>Expectancy R</th><th>Profit factor</th>"
        "<th>Total R</th><th>Max DD (R)</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )

    criteria_html = ""
    for policy in view.policies:
        marks = "".join(
            "<li>"
            + _chip(
                {True: "pass", False: "fail", None: "not evaluable"}[item.passed],
                {True: "ok", False: "bad", None: "warn"}[item.passed],
            )
            + f" <strong>{_e(item.name)}</strong> — {_e(item.observed)}"
            f"<br><small>{_e(item.requirement)}</small></li>"
            for item in policy.criteria
        )
        criteria_html += (
            f"<details><summary><code>{_e(policy.policy_id)}</code> — "
            f"{_e(policy.verdict_statement)}</summary>"
            f"<p>{_e(policy.hypothesis)}</p>"
            f"<p class='muted'><small>PREDICTED: {_e(policy.prediction)}</small></p>"
            f"<p class='muted'><small>REFUTED BY: {_e(policy.refuted_by)}</small></p>"
            f"<ul class='criteria'>{marks}</ul></details>"
        )

    plateau_html = ""
    for policy in view.policies:
        if policy.plateau is None:
            continue
        points = "".join(
            f"<tr><td>{'★' if point.is_primary else ''}</td>"
            f"<td>{_e(point.axis)}</td><td>{_e(point.threshold)}</td>"
            f"<td>{point.measurable}</td>"
            f"<td>{_e(point.expectancy or '—')}</td></tr>"
            for point in policy.plateau.points
        )
        plateau_html += (
            f"<h3><code>{_e(policy.policy_id)}</code> — "
            f"{_e(policy.plateau.classification.replace('_', ' ').upper())}</h3>"
            f"<p class='muted'>{_e(policy.plateau.statement)}</p>"
            "<table><thead><tr><th></th><th>Axis</th><th>Threshold</th>"
            "<th>Measurable</th><th>Expectancy R</th></tr></thead>"
            f"<tbody>{points}</tbody></table>"
        )

    cost_rows = "".join(
        f"<tr><td><code>{_e(policy.policy_id)}</code></td>"
        f"<td>{_e(item.sample)}</td><td>{_e(item.cost_policy_id)}"
        + (" <span class='tag'>deciding</span>" if item.is_deciding else "")
        + "</td>"
        + cell(item.expectancy, item.expectancy_reason)
        + f"<td>{item.measurable}</td></tr>"
        for policy in view.policies
        for item in policy.cells
    )
    costs_html = (
        "<table><thead><tr><th>Hypothesis</th><th>Sample</th><th>Cost scenario</th>"
        "<th>Expectancy R</th><th>Measurable</th></tr></thead>"
        f"<tbody>{cost_rows}</tbody></table>"
    )

    window_rows = "".join(
        f"<tr><td>{_e(row.label)}</td><td>{row.trades}</td><td>{row.measurable}</td>"
        + cell(row.win_rate) + cell(row.expectancy) + cell(row.profit_factor)
        + f"<td>{_e(row.total_r)}</td><td>{_e(row.max_drawdown)}</td></tr>"
        for row in view.walk_forward
    )
    walk_html = (
        f"<p class='muted'>The frozen policy <code>"
        f"{_e(view.walk_forward_policy_id)}</code> across time, with no "
        "re-optimisation inside any window. Empty windows are shown, never "
        "omitted.</p>"
        "<table><thead><tr><th>Window</th><th>Trades</th><th>Measurable</th>"
        "<th>Win rate</th><th>Expectancy R</th><th>Profit factor</th>"
        "<th>Total R</th><th>Max DD (R)</th></tr></thead>"
        f"<tbody>{window_rows}</tbody></table>"
    )

    decomposition_html = ""
    for cut in view.decompositions:
        agreement = {
            True: _chip("cohorts agree on sign", "ok"),
            False: _chip("cohorts DISAGREE on sign", "bad"),
            None: _chip("too few cohorts to compare", "warn"),
        }[cut.agrees_on_sign]
        cohorts = "".join(
            f"<tr><td>{_e(row.label)}</td><td>{row.measurable}</td>"
            + cell(row.expectancy, row.expectancy_reason)
            + f"<td>{_e(row.total_r)}</td></tr>"
            for row in cut.cohorts
        )
        decomposition_html += (
            f"<details><summary><strong>{_e(cut.name)}</strong> {agreement}</summary>"
            f"<p class='muted'>{_e(cut.question)}</p>"
            "<table><thead><tr><th>Cohort</th><th>Measurable</th>"
            "<th>Expectancy R</th><th>Total R</th></tr></thead>"
            f"<tbody>{cohorts}</tbody></table></details>"
        )

    limitations_html = "<ul>" + "".join(
        f"<li>{_e(item)}</li>" for item in view.limitations
    ) + "</ul>"

    return "".join(
        (
            _panel("Validation verdict", verdict_html),
            _panel("Pre-registration", seal),
            _panel("Samples", samples_html),
            _panel("Results — cost-inclusive, in pre-registration order", table),
            _panel("Criteria, by hypothesis", criteria_html),
            _panel("Parameter plateau", plateau_html or "<p class='muted'>No "
                   "hypothesis declares a neighbourhood.</p>"),
            _panel("Cost sensitivity", costs_html),
            _panel("Walk-forward", walk_html),
            _panel("Decomposition", decomposition_html),
            _panel("Limitations", limitations_html),
        )
    )


def _geometry(snapshot: OperatorDashboardSnapshot) -> str:
    """The Trade Geometry page. **Designed for a decision, not for completeness.**

    The order is deliberate and is the order a reader needs it in:

    1. **the verdict first**, because a reader who stops after one screen must
       not come away with a different impression from one who reads to the end;
    2. the two samples side by side, never one without the other;
    3. why each rule was refused, by criterion name;
    4. the diagnosis of the production geometry, evidence before reading;
    5. the sensitivity curves, as curves;
    6. the limitations, in full.

    There is no ranked table and no "best rule" — sorting by expectancy would be
    choosing one, and the criteria exist so that choice is not a judgement call.
    """
    section = snapshot.geometry
    if section is None or not section.is_available or section.data is None:
        return _panel(
            "Trade Geometry",
            "<p class='muted'>No geometry experiment is loaded. Run one with "
            "<code>fmits research geometry --development BTCUSDT ... --holdout "
            "NEOUSDT ... --start ... --save geometry.json</code> and start the "
            "dashboard with <code>--geometry-artifact geometry.json</code>. "
            "This page shows a saved research record; it never runs a replay "
            "itself and never changes a strategy.</p>",
        )
    view = section.data

    head = (
        "<dl class='meta'>"
        f"<dt>Experiment</dt><dd>{_e(view.experiment_id)}</dd>"
        f"<dt>Development</dt><dd>{_e(', '.join(view.development_symbols))}"
        "<small>already measured by Milestone BW — NOT out-of-sample</small></dd>"
        f"<dt>Holdout</dt><dd>{_e(', '.join(view.holdout_symbols))}"
        "<small>never previously measured, same window</small></dd>"
        f"<dt>Window</dt><dd>{_e(view.measurement_start)} → {_e(view.measurement_end)}</dd>"
        f"<dt>Admission</dt><dd>{_e(view.admission)}"
        "<small>held fixed for every geometry</small></dd>"
        f"<dt>Candidates</dt><dd>{view.candidate_count}</dd>"
        f"<dt>Costs</dt><dd>{_e(view.cost_policy)}</dd>"
        f"<dt>Digest</dt><dd><code>{_e(view.result_digest)}</code> "
        f"({'verified' if view.digest_verified else 'NOT VERIFIED'})</dd>"
        "</dl>"
    )

    winners = view.candidate_policy_ids
    if winners:
        verdict_html = (
            f"<p><strong>{len(winners)} of {len(view.policies)}</strong> "
            "geometries met every criterion:</p><ul>"
            + "".join(f"<li><code>{_e(item)}</code></li>" for item in winners)
            + "</ul><p class='muted'>A candidate for forward testing is "
            "<strong>worth testing forward</strong> and nothing more. It is not "
            "approval to trade.</p>"
        )
    else:
        verdict_html = (
            "<p><strong>NO CANDIDATE.</strong> No geometry met every criterion, "
            "so none is proposed for forward or shadow testing.</p>"
            "<p class='muted'>This is a result, not a missing measurement — the "
            "criteria each policy failed are listed below by name.</p>"
        )

    def cell(value: str | None, reason: str | None) -> str:
        if value is None:
            return f"<td class='absent'>unavailable<small>{_e(reason or '')}</small></td>"
        return f"<td>{_e(value)}</td>"

    rows = []
    for policy in view.policies:
        for sample in (policy.development, policy.holdout):
            first = sample is policy.development
            rows.append(
                "<tr>"
                + (
                    f"<th scope='row' rowspan='2'><code>{_e(policy.policy_id)}</code>"
                    f"{' <span class=\'tag\'>control</span>' if policy.is_production_geometry else ''}"
                    f"<small>{_e(policy.title)}</small>"
                    f"<small>{_e(policy.family)}</small></th>"
                    f"<td class='verdict' rowspan='2'>{_e(policy.verdict.replace('_', ' '))}</td>"
                    if first
                    else ""
                )
                + f"<td>{_e(sample.sample)}</td>"
                f"<td>{sample.trades}</td>"
                f"<td>{sample.refused}</td>"
                f"<td>{sample.measurable}</td>"
                + cell(sample.win_rate, sample.win_rate_reason)
                + cell(sample.expectancy, sample.expectancy_reason)
                + cell(sample.median_r, sample.median_r_reason)
                + cell(sample.profit_factor, sample.profit_factor_reason)
                + f"<td>{_e(sample.total_r)}</td>"
                f"<td>{_e(sample.max_drawdown)}</td>"
                f"<td>{_e(sample.median_planned_rr or '—')}</td>"
                "</tr>"
            )
    table = (
        "<table><thead><tr><th>Geometry</th><th>Verdict</th><th>Sample</th>"
        "<th>Trades</th><th>Refused</th><th>Measurable</th><th>Win rate</th>"
        "<th>Expectancy R</th><th>Median R</th><th>Profit factor</th>"
        "<th>Total R</th><th>Max DD (R)</th><th>Median planned R:R</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )

    criteria_html = ""
    for policy in view.policies:
        marks = "".join(
            "<li>"
            + _chip(
                {True: "pass", False: "fail", None: "not evaluable"}[item.passed],
                {True: "ok", False: "bad", None: "warn"}[item.passed],
            )
            + f" <strong>{_e(item.name)}</strong> — {_e(item.observed)}"
            f"<br><small>{_e(item.requirement)}</small></li>"
            for item in policy.criteria
        )
        criteria_html += (
            f"<details><summary><code>{_e(policy.policy_id)}</code> — "
            f"{_e(policy.verdict_statement)}</summary>"
            f"<p class='muted'>{_e(policy.hypothesis)}</p>"
            f"<ul class='criteria'>{marks}</ul></details>"
        )

    findings_html = "".join(
        "<li>"
        + _chip(
            {True: "yes", False: "no", None: "not answerable"}[item.supported],
            {True: "warn", False: "ok", None: "muted"}[item.supported],
        )
        + f" <strong>{_e(item.question)}</strong>"
        f"<br><small>evidence: {_e(item.evidence)}</small>"
        f"<br><small>{_e(item.reading)}</small></li>"
        for item in view.baseline_findings
    )
    shares_html = "".join(
        f"<dt>{_e(item.label)}</dt><dd>{_e(item.text)}"
        + ("<small>too few to state a rate</small>" if item.fraction is None else "")
        + "</dd>"
        for item in view.baseline_shares
    )

    sensitivity_rows = "".join(
        f"<tr><td>{_e(row.kind)}</td><td>{_e(row.threshold)}</td>"
        f"<td>{row.development_trades}</td>"
        f"<td>{_e(row.development_expectancy or '—')}</td>"
        f"<td>{row.holdout_trades}</td>"
        f"<td>{_e(row.holdout_expectancy or '—')}</td></tr>"
        for row in view.sensitivity
    )
    sensitivity_html = ""
    if sensitivity_rows:
        notes = "".join(f"<li>{_e(item)}</li>" for item in view.plateau_notes)
        sensitivity_html = _panel(
            "Parameter sensitivity",
            "<p class='muted'>A plateau is evidence; a spike at one hand-picked "
            "number is an artifact. These grid points were swept after the "
            "results were seen and are <strong>not</strong> pre-declared "
            "candidates.</p>"
            f"<ul>{notes}</ul>"
            "<table><thead><tr><th>Grid</th><th>Threshold</th>"
            "<th>Dev trades</th><th>Dev expectancy R</th>"
            "<th>Holdout trades</th><th>Holdout expectancy R</th>"
            "</tr></thead><tbody>" + sensitivity_rows + "</tbody></table>",
        )

    limitations = "".join(f"<li>{_e(item)}</li>" for item in view.limitations)
    return (
        _panel("Does any geometry deserve forward testing?", verdict_html)
        + _panel("Trade Geometry — saved experiment", head + table)
        + _panel("Criteria, geometry by geometry", criteria_html)
        + _panel(
            "Diagnosis of the production geometry",
            f"<dl class='meta'>{shares_html}</dl>"
            "<p class='muted'>Evidence above; interpretation below. A reader may "
            "disagree with a reading without doubting the count it was read "
            "from.</p>"
            f"<ul class='criteria'>{findings_html}</ul>",
        )
        + sensitivity_html
        + _panel("Limitations", f"<ul>{limitations}</ul>")
        + _panel(
            "This page promotes nothing",
            "<p class='muted'>A geometry that measures well here is a candidate "
            "for forward testing and nothing more. The production stop and "
            "target rules are unchanged by this experiment and cannot be "
            "changed from this page.</p>",
        )
    )


def render_page(
    snapshot: OperatorDashboardSnapshot, path: str, *, symbol: str | None = None
) -> str:
    """One complete HTML document for one route.

    Unknown routes never reach here — the server resolves them first and asks
    for a page it knows, so this function has no fallback branch that could
    render a half-page.
    """
    if symbol is not None:
        title = f"Swing · {symbol}"
        body = _symbol_page(snapshot, symbol)
        active = "/swing"
    else:
        active = path
        title = dict(PAGES).get(path, "Overview")
        body = {
            "/": _overview,
            "/markets": _markets,
            "/swing": _swing,
            "/portfolio": _portfolio,
            "/paper": _paper,
            "/performance": _performance,
            "/lab": _lab,
            "/geometry": _geometry,
            "/validation": _validation,
            "/system": _system,
        }[path](snapshot)
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="referrer" content="no-referrer">'
        f"<title>FMITS · {_e(title)}</title>"
        f"<style>{STYLESHEET}</style></head><body>"
        f"{_header(snapshot, active)}"
        f"<main>{body}</main>"
        f"{_footer()}"
        "</body></html>"
    )
