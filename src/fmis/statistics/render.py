"""The five statistics pages, as 78-column ASCII.

**This module only renders.** It computes nothing and decides nothing: every
figure it prints was produced by a fold in this package, and a guard test asserts
it calls no repository and no builder. A renderer that computed one number would
become the second place that number is defined.

**`n` is never optional and never small print.** Every rate is printed beside
the population it rests on, and a refused rate prints its reason in full rather
than a dash. `AP` §20.7's guard is worthless if the page can render around it,
so the renderer has no short form that could drop the sample.

**The cells-examined count sits beside the breakdowns, not beneath them.**
`TRADER_WORKSPACE` §3.4.12's mechanism: the owner reading a striking cell must
be able to see, without scrolling, how many chances there were for one to appear.

**78 columns, ASCII, no colour** — the geometry `fmits today`, `fmits trade` and
`fmits simulate` already use, so all of them read as one product and every one
survives a pipe and a log file.
"""

from __future__ import annotations

import textwrap
from datetime import timedelta
from decimal import Decimal
from typing import Any

from fmis.money import Money, canonical_decimal_text
from fmis.provenance import Absent
from fmis.statistics.breakdown import Breakdown, BreakdownSet
from fmis.statistics.distribution import Histogram
from fmis.statistics.drawdown import DrawdownCurve, DrawdownPeriod
from fmis.statistics.equity import EquityCurve
from fmis.statistics.general import GeneralStatistics
from fmis.statistics.models import StatisticsRefusedError, TradeStat
from fmis.statistics.performance import PerformanceStatistics
from fmis.statistics.quality import QualityStatistics
from fmis.statistics.report import AssetReport, StatisticsReport, recent_trades
from fmis.statistics.risk import RiskStatistics
from fmis.statistics.sampling import Sample, Tally

__all__ = [
    "duration_text",
    "render_statistics",
    "render_performance",
    "render_expectancy",
    "render_equity",
    "render_trades_summary",
]

_WIDTH = 78
_LABEL = 26
_BAR_WIDTH = 24
_SECONDS_PER_HOUR = 3600
_SECONDS_PER_MINUTE = 60


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
    """A value nothing bounds the length of — a store path, a record id.

    Wrapped rather than truncated, **including mid-token**: a truncated path is
    one the owner copies and cannot `cd` into, and a truncated record id is one
    they cannot look up. `fmis.paper.render` reached the identical conclusion
    for the identical reason, and this is its rule reused.
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
    """One rule for every optional value on every page in this package.

    An `Absent` prints its reason in full, wrapped, rather than a dash. On a
    statistics page a dash is read as zero more often than as unknown, and the
    difference between *"you have lost nothing"* and *"nothing here could be
    measured"* is the whole point of the type.
    """
    if isinstance(value, Absent):
        return f"- ({value.reason})"
    if isinstance(value, Money):
        return f"{value.text} {value.asset.code}"
    if isinstance(value, Decimal):
        return canonical_decimal_text(value)
    if isinstance(value, timedelta):
        return duration_text(value)
    return str(value)


def _lines_for(label: str, value: Any) -> list[str]:
    """A labelled value, wrapped when its absence reason runs long."""
    rendered = _value(value)
    prefix = f" {label:<{_LABEL}} "
    if len(prefix) + len(rendered) <= _WIDTH:
        return [f"{prefix}{rendered}"]
    return textwrap.wrap(
        rendered,
        width=_WIDTH,
        initial_indent=prefix,
        subsequent_indent=" " * (_LABEL + 2),
    )


def _percent(value: Decimal | Absent) -> str:
    if isinstance(value, Absent):
        return _value(value)
    return f"{canonical_decimal_text(value * Decimal(100))} %"


def duration_text(span: timedelta, *, minutes: bool = True) -> str:
    """Days, hours and minutes — the resolution a swing trade is read at.

    Seconds are dropped deliberately: a holding time of *"6 days 3 h 14 min"* is
    the fact, and printing the seconds implies a precision the close instant of a
    trade folded from a candle does not carry.

    **Public, and the only place a duration becomes text in this product.**
    `fmis.today` calls it rather than carrying its own copy: the day's page's
    magic-number guard forbids a rule module from typing `86400`, and it is
    right to — a second formatter is a second set of unit constants, and two
    pages that disagree about what *"1d 2h"* means is worse than one that is
    merely terse. `minutes=False` is the day-page form, which has one line.
    """
    magnitude = abs(span)
    sign = "-" if span.total_seconds() < 0 else ""
    # `timedelta` already normalizes into days, seconds and microseconds, so the
    # only arithmetic here is splitting its seconds into hours and minutes.
    hours, rest = divmod(magnitude.seconds, _SECONDS_PER_HOUR)
    if not minutes:
        return f"{sign}{magnitude.days}d {hours}h"
    remaining = rest // _SECONDS_PER_MINUTE
    if magnitude.days:
        return f"{sign}{magnitude.days}d {hours}h {remaining}m"
    if hours:
        return f"{sign}{hours}h {remaining}m"
    return f"{sign}{remaining}m"


def _tally(entry: Tally) -> str:
    return f"{entry.count} of {entry.total}"


def _sample_note(sample: Sample) -> list[str]:
    note = sample.coverage_note
    if isinstance(note, Absent):
        return []
    return _wrap(f"n = {sample.size}: {note}")


def _header(report: StatisticsReport, title: str) -> list[str]:
    lines = [_rule(), f" {title}", _rule()]
    lines.extend(_token_lines("Store", report.store_root))
    lines.append(_field("As at", report.reference_time.isoformat()))
    if not isinstance(report.as_of, Absent):
        lines.append(_field("Point-in-time cut", report.as_of.isoformat()))
    lines.append(_field("Sample floor", f"{report.policy.minimum_sample} trades"))
    lines.append(_field("Trades", str(report.total_trades)))
    lines.extend(_wrap(report.objective))
    if not report.present:
        lines.extend(
            _wrap(
                "No store exists at this path. An owner who has recorded nothing "
                "has no statistics, which is a page rather than a failure."
            )
        )
    if report.refused:
        lines.extend(_section("NOT COUNTED"))
        for entry in report.refused:
            lines.extend(_wrap(entry))
    return lines


def _asset_banner(report: StatisticsReport, asset: AssetReport) -> list[str]:
    lines = _section(f"SETTLED IN {asset.quote_asset.code}")
    lines.append(_field("Trades in this asset", str(asset.size)))
    if len(report.assets) > 1:
        others = ", ".join(
            entry.quote_asset.code
            for entry in report.assets
            if entry.quote_asset != asset.quote_asset
        )
        lines.extend(
            _wrap(
                f"This store also settles in {others}. Figures are never summed "
                "across quote assets, so each has its own page below."
            )
        )
    return lines


def _general_block(general: GeneralStatistics) -> list[str]:
    lines = _section("GENERAL")
    lines.append(_field("Total trades", str(general.total)))
    for label, entry in (
        ("Winning", general.winning),
        ("Losing", general.losing),
        ("Scratch", general.scratch),
        ("Unresolved", general.unresolved),
        ("Open", general.open_trades),
        ("Closed", general.closed),
        ("Pending", general.pending),
        ("Triggered", general.triggered),
        ("Cancelled", general.cancelled),
        ("Expired", general.expired),
        ("Halted (ambiguous)", general.ambiguous),
        ("Paper book", general.paper),
        ("Other books", general.live),
    ):
        lines.append(_field(label, _tally(entry)))
    for entry in general.by_direction:
        lines.append(_field(f"Side {entry.subject}", _tally(entry)))
    for entry in general.by_source:
        lines.append(_field(f"Source {entry.subject}", _tally(entry)))
    lines.append("")
    for label, value in (
        ("Average holding time", general.average_holding_time),
        ("Median holding time", general.median_holding_time),
        ("Longest holding time", general.maximum_holding_time),
        ("Shortest holding time", general.minimum_holding_time),
        ("Average bars held", general.average_bars_held),
        ("Median bars held", general.median_bars_held),
    ):
        lines.extend(_lines_for(label, value))
    lines.extend(_sample_note(general.holding_time))
    lines.extend(_sample_note(general.bars_held))
    return lines


def _performance_block(performance: PerformanceStatistics) -> list[str]:
    lines = _section("PERFORMANCE")
    for label, value in (
        ("Gross profit", performance.gross_profit),
        ("Gross loss", performance.gross_loss),
        ("Net profit", performance.net_profit),
        ("Average win", performance.average_win),
        ("Average loss", performance.average_loss),
        ("Largest win", performance.largest_win),
        ("Largest loss", performance.largest_loss),
        ("Expectancy per trade", performance.expectancy),
    ):
        lines.extend(_lines_for(label, value))
    lines.append("")
    lines.extend(_lines_for("Profit factor", performance.profit_factor))
    lines.extend(_lines_for("Payoff ratio", performance.payoff_ratio))
    lines.extend(_rate("Win rate", performance.win_rate, performance.winners))
    lines.extend(_rate("Loss rate", performance.loss_rate, performance.losers))
    lines.append("")
    for label, value in (
        ("Average R", performance.average_r),
        ("Median R", performance.median_r),
        ("Best R", performance.best_r),
        ("Worst R", performance.worst_r),
        ("Expectancy in R", performance.expectancy_r),
    ):
        lines.extend(_lines_for(label, value))
    lines.extend(_sample_note(performance.r_sample))
    lines.extend(_wrap(performance.expectancy_basis))
    lines.extend(_wrap(performance.profit_factor_basis))
    return lines


def _rate(label: str, value: Decimal | Absent, tally: Tally) -> list[str]:
    """A rate, its population, and its refusal in full when it has one."""
    if isinstance(value, Absent):
        return _lines_for(label, value)
    return [_field(label, f"{_percent(value)}  ({_tally(tally)})")]


def _risk_block(risk: RiskStatistics) -> list[str]:
    lines = _section("RISK")
    for label, value in (
        ("Total open risk", risk.total_open_risk),
        ("Largest open risk", risk.largest_open_risk),
        ("Average open risk", risk.average_open_risk),
        ("Largest closed risk", risk.largest_closed_risk),
        ("Average closed risk", risk.average_closed_risk),
    ):
        lines.extend(_lines_for(label, value))
    if isinstance(risk.risk_utilization, Absent):
        lines.extend(_lines_for("Risk utilization", risk.risk_utilization))
    else:
        lines.append(_field("Risk utilization", _percent(risk.risk_utilization)))
    lines.extend(_lines_for("Equity basis", risk.equity_basis))
    if isinstance(risk.average_risk_fraction, Absent):
        lines.extend(_lines_for("Average risk %", risk.average_risk_fraction))
    else:
        lines.append(_field("Average risk %", _percent(risk.average_risk_fraction)))
    if isinstance(risk.median_risk_fraction, Absent):
        lines.extend(_lines_for("Median risk %", risk.median_risk_fraction))
    else:
        lines.append(_field("Median risk %", _percent(risk.median_risk_fraction)))
    lines.extend(_wrap(risk.utilization_basis))
    return lines


def _quality_block(quality: QualityStatistics) -> list[str]:
    """The excursion figures — or, when none of them exists, one sentence.

    A corpus of hand-recorded trades has **no** excursion at all, and printing
    the identical refusal against each of seven labels buries the one fact the
    owner needs: nobody simulated these trades, so nothing froze an excursion.
    Collapsing is safe here precisely because it is all-or-nothing — the moment
    a single figure is stateable the full list is printed, absences and all, so
    a partial population can never hide behind a summary.
    """
    lines = _section("QUALITY")
    excursion_figures = (
        quality.average_adverse_r,
        quality.median_adverse_r,
        quality.maximum_adverse_r,
        quality.average_favourable_r,
        quality.median_favourable_r,
        quality.maximum_favourable_r,
        quality.average_excursion_r,
        quality.average_capture_efficiency,
        quality.median_capture_efficiency,
    )
    if all(isinstance(value, Absent) for value in excursion_figures):
        lines.extend(
            _wrap(
                "No excursion figure exists for this corpus. Maximum adverse and "
                "favourable excursion, total excursion and capture efficiency are "
                "frozen at close for simulated trades only, and none of these "
                f"{quality.adverse.population} trade(s) has one."
            )
        )
        lines.extend(_sample_note(quality.adverse))
        lines.append("")
        lines.extend(_histogram("DISTRIBUTION OF R", quality.r_distribution))
        lines.append("")
        lines.extend(
            _histogram(
                "DISTRIBUTION OF HOLDING TIME", quality.holding_time_distribution
            )
        )
        return lines
    for label, value in (
        ("Average MAE (R)", quality.average_adverse_r),
        ("Median MAE (R)", quality.median_adverse_r),
        ("Worst MAE (R)", quality.maximum_adverse_r),
        ("Average MFE (R)", quality.average_favourable_r),
        ("Median MFE (R)", quality.median_favourable_r),
        ("Best MFE (R)", quality.maximum_favourable_r),
        ("Average excursion (R)", quality.average_excursion_r),
    ):
        lines.extend(_lines_for(label, value))
    if isinstance(quality.average_capture_efficiency, Absent):
        lines.extend(
            _lines_for("Average capture", quality.average_capture_efficiency)
        )
    else:
        lines.append(
            _field("Average capture", _percent(quality.average_capture_efficiency))
        )
    if isinstance(quality.median_capture_efficiency, Absent):
        lines.extend(_lines_for("Median capture", quality.median_capture_efficiency))
    else:
        lines.append(
            _field("Median capture", _percent(quality.median_capture_efficiency))
        )
    lines.extend(_sample_note(quality.adverse))
    lines.extend(_sample_note(quality.capture))
    lines.extend(_wrap(quality.capture_basis))
    lines.extend(_wrap(quality.excursion_basis))
    lines.append("")
    lines.extend(_histogram("DISTRIBUTION OF R", quality.r_distribution))
    lines.append("")
    lines.extend(
        _histogram("DISTRIBUTION OF HOLDING TIME", quality.holding_time_distribution)
    )
    return lines


def _histogram(title: str, histogram: Histogram) -> list[str]:
    """Bars scaled to the tallest bucket, with every empty bucket still drawn.

    The gaps are the information. A renderer that skipped the empty middle would
    draw a clustered distribution and an even one identically.
    """
    lines = [f" {title}  (n = {histogram.size}, unit: {histogram.unit})"]
    if histogram.missing:
        lines.extend(
            _wrap(
                f"{histogram.missing} trade(s) had no {histogram.kind} to place "
                "and are not in this shape."
            )
        )
    if histogram.is_empty:
        lines.extend(_wrap("No trade in this population has a value to place."))
        return lines
    peak = histogram.peak
    for bucket in histogram.buckets:
        filled = 0 if peak == 0 else (bucket.count * _BAR_WIDTH) // peak
        bar = "#" * filled
        lines.append(f"   {bucket.label:<18} {bucket.count:>4}  {bar}")
    return lines


def _equity_block(equity: EquityCurve, drawdown: DrawdownCurve) -> list[str]:
    lines = _section("EQUITY")
    lines.extend(_lines_for("Starting equity", equity.starting_equity))
    lines.append(_field("Realized profit/loss", _value(equity.realized)))
    lines.extend(_lines_for("Current equity", equity.current_equity))
    lines.append(_field("Closed-trade steps", str(len(equity.points))))
    lines.append(_field("Open trades (excluded)", str(equity.open_trades)))
    for reason in equity.excluded:
        lines.extend(_wrap(reason))
    lines.extend(_wrap(equity.basis))
    lines.extend(_section("DRAWDOWN"))
    lines.append(_field("Current drawdown", _value(drawdown.current)))
    if not isinstance(drawdown.current_percent, Absent):
        lines.append(_field("Current drawdown %", _percent(drawdown.current_percent)))
    else:
        lines.extend(_lines_for("Current drawdown %", drawdown.current_percent))
    lines.extend(_lines_for("Maximum drawdown", drawdown.maximum))
    if not isinstance(drawdown.maximum_percent, Absent):
        lines.append(_field("Maximum drawdown %", _percent(drawdown.maximum_percent)))
    else:
        lines.extend(_lines_for("Maximum drawdown %", drawdown.maximum_percent))
    lines.extend(_lines_for("Average drawdown", drawdown.average))
    lines.append(_field("Drawdown periods", str(len(drawdown.periods))))
    lines.append(_field("Recovered periods", str(len(drawdown.recoveries))))
    lines.extend(_period_line("Longest", drawdown.longest))
    lines.extend(_period_line("Deepest", drawdown.deepest))
    lines.extend(_wrap(drawdown.basis))
    return lines


def _period_line(label: str, period: DrawdownPeriod | Absent) -> list[str]:
    if isinstance(period, Absent):
        return _lines_for(label, period)
    state = "ongoing" if period.is_ongoing else "recovered"
    return [
        _field(
            label,
            f"{_value(period.depth)} over {duration_text(period.duration)}, "
            f"{period.trades} trade(s), {state}",
        )
    ]


def _breakdown_block(breakdowns: BreakdownSet) -> list[str]:
    lines = _section("BREAKDOWNS")
    lines.append(_field("Cells examined", str(breakdowns.cells_examined)))
    lines.append(_field("Regime dimension", breakdowns.regime_dimension))
    lines.extend(_wrap(breakdowns.note))
    for entry in breakdowns.breakdowns:
        lines.extend(_breakdown(entry))
    return lines


def _breakdown(breakdown: Breakdown) -> list[str]:
    """One dimension's cells, as a table of **counts** rather than of rates.

    The win column is `wins/resolved`, not a percentage, and that is a
    correctness decision rather than a stylistic one. A rate here is an exact
    quotient that frequently does not terminate — `2 ÷ 3` is
    `0.6666…` to the full precision of the arithmetic — and a fixed-width
    column can only hold it by truncating, which turns a number into a
    different number. `AverageCost.arithmetic` already answers this in this
    repository by *showing the division instead of its result*, and the pair is
    exact at any width. The full quotient, unrounded, is on the payload and in
    the scalar fields above, where it may wrap.

    Nothing in this table is truncated. A shortened cell key would make two
    distinct cells read as one, and a shortened amount would be a false figure;
    an over-long row is merely untidy, and untidy beats wrong.
    """
    lines = ["", f" By {breakdown.dimension} ({breakdown.size} cell(s))"]
    if not breakdown.cells:
        lines.extend(_wrap("No trade in this corpus falls under this dimension."))
        return lines
    lines.append(f"   {'cell':<22} {'n':>4} {'won':>9}  net")
    for cell in breakdown.cells:
        winners = cell.performance.winners
        net = cell.performance.net_profit
        figures = (
            f"{cell.size:>4} {f'{winners.count}/{winners.total}':>9}  "
            f"{_value(net) if not isinstance(net, Absent) else 'not stateable'}"
        )
        row = f"   {cell.key:<22} {figures}"
        if len(row) <= _WIDTH:
            lines.append(row)
            continue
        # A cell key has no bound — a setup term and an account id are both the
        # owner's own words. Truncating it would make two distinct cells read as
        # one, which in a table is worse than an untidy row, so the long key
        # takes its own wrapped line and its figures sit beneath it.
        lines.extend(_token_lines("", cell.key))
        lines.append(f"   {'':<22} {figures}")
    below = [
        cell.key
        for cell in breakdown.cells
        if isinstance(cell.performance.win_rate, Absent)
    ]
    if below:
        lines.extend(
            _wrap(
                f"{len(below)} of {breakdown.size} cell(s) hold too few resolved "
                "trades for a rate to be stated at all: "
                + ", ".join(below)
            )
        )
    return lines


def _limitations(report: StatisticsReport) -> list[str]:
    lines = _section("LIMITATIONS")
    for code, text in report.limitations:
        lines.extend(_wrap(f"{code}. {text}"))
    return lines


def _empty(report: StatisticsReport, title: str) -> str:
    lines = _header(report, title)
    lines.extend(_section("NO TRADES"))
    lines.extend(
        _wrap(
            "This store records no trade, so there is nothing to compute. That is "
            "an empty corpus rather than a result of zero."
        )
    )
    lines.extend(_limitations(report))
    lines.append(_rule())
    return _fitted(lines)


def render_statistics(report: StatisticsReport) -> str:
    """`fmits statistics` — every family, every curve, every cut."""
    _require_report(report)
    if report.is_empty:
        return _empty(report, "FMITS STATISTICS")
    lines = _header(report, "FMITS STATISTICS")
    for asset in report.assets:
        lines.extend(_asset_banner(report, asset))
        lines.extend(_general_block(asset.general))
        lines.extend(_performance_block(asset.performance))
        lines.extend(_risk_block(asset.risk))
        lines.extend(_quality_block(asset.quality))
        lines.extend(_equity_block(asset.equity, asset.drawdown))
        lines.extend(_breakdown_block(asset.breakdowns))
    lines.extend(_limitations(report))
    lines.append(_rule())
    return _fitted(lines)


def render_performance(report: StatisticsReport) -> str:
    """`fmits performance` — the money and the R, without the cuts."""
    _require_report(report)
    if report.is_empty:
        return _empty(report, "FMITS PERFORMANCE")
    lines = _header(report, "FMITS PERFORMANCE")
    for asset in report.assets:
        lines.extend(_asset_banner(report, asset))
        lines.extend(_performance_block(asset.performance))
        lines.extend(_quality_block(asset.quality))
    lines.extend(_limitations(report))
    lines.append(_rule())
    return _fitted(lines)


def render_expectancy(report: StatisticsReport) -> str:
    """`fmits expectancy` — the one question, with the sample in front of it.

    The narrowest page in the package and the one most likely to be over-read,
    so the floor and the population come **before** the numbers rather than
    after them.
    """
    _require_report(report)
    if report.is_empty:
        return _empty(report, "FMITS EXPECTANCY")
    lines = _header(report, "FMITS EXPECTANCY")
    lines.extend(_section("WHAT THIS RESTS ON"))
    lines.extend(_wrap(report.policy.basis))
    for asset in report.assets:
        performance = asset.performance
        lines.extend(_asset_banner(report, asset))
        lines.append(
            _field("Resolved trades", str(performance.resolved.size))
        )
        lines.extend(_sample_note(performance.resolved))
        lines.extend(_lines_for("Expectancy per trade", performance.expectancy))
        lines.extend(_lines_for("Expectancy in R", performance.expectancy_r))
        lines.extend(_rate("Win rate", performance.win_rate, performance.winners))
        lines.extend(_rate("Loss rate", performance.loss_rate, performance.losers))
        lines.extend(_lines_for("Profit factor", performance.profit_factor))
        lines.extend(_lines_for("Payoff ratio", performance.payoff_ratio))
        lines.extend(_lines_for("Average win", performance.average_win))
        lines.extend(_lines_for("Average loss", performance.average_loss))
        lines.extend(_wrap(performance.expectancy_basis))
    lines.extend(_limitations(report))
    lines.append(_rule())
    return _fitted(lines)


def render_equity(report: StatisticsReport, *, points: int = 20) -> str:
    """`fmits equity` — the curve, the drawdowns, and the last steps in full."""
    _require_report(report)
    if not isinstance(points, int) or isinstance(points, bool) or points < 0:
        raise ValueError("points must be a non-negative int")
    if report.is_empty:
        return _empty(report, "FMITS EQUITY")
    lines = _header(report, "FMITS EQUITY")
    for asset in report.assets:
        lines.extend(_asset_banner(report, asset))
        lines.extend(_equity_block(asset.equity, asset.drawdown))
        shown = asset.equity.points[-points:] if points else ()
        if shown:
            lines.extend(_section(f"LAST {len(shown)} CLOSED-TRADE STEPS"))
            for point in shown:
                lines.extend(
                    _wrap(
                        f"{point.at.isoformat()[:16]}   step {point.delta.text}"
                        f"   cumulative {point.cumulative.text}",
                        indent="   ",
                    )
                )
                # The reference on its own wrapped line: an id is what the owner
                # types to see the trade again, and one cut to fit a column is
                # one they cannot look up.
                lines.extend(_token_lines("", point.trade_ref))
        if len(asset.equity.points) > len(shown):
            lines.extend(
                _wrap(
                    f"{len(asset.equity.points) - len(shown)} earlier step(s) are "
                    "not shown. Every one of them is in the figures above."
                )
            )
    lines.extend(_limitations(report))
    lines.append(_rule())
    return _fitted(lines)


def render_trades_summary(report: StatisticsReport, *, limit: int = 10) -> str:
    """`fmits trades summary` — the counts, and the last trades one per line."""
    _require_report(report)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("limit must be a non-negative int")
    if report.is_empty:
        return _empty(report, "FMITS TRADES SUMMARY")
    lines = _header(report, "FMITS TRADES SUMMARY")
    for asset in report.assets:
        lines.extend(_asset_banner(report, asset))
        lines.extend(_general_block(asset.general))
        latest = recent_trades(asset.trades, limit)
        lines.extend(_section(f"LAST {len(latest)} CLOSED"))
        if not latest:
            lines.extend(
                _wrap(
                    "No trade in this asset has closed, so there is no result to "
                    "list. Trades still running are counted above."
                )
            )
            continue
        for stat in latest:
            lines.extend(_trade_line(stat))
    lines.extend(_limitations(report))
    lines.append(_rule())
    return _fitted(lines)


def _trade_line(stat: TradeStat) -> list[str]:
    """One closed trade, over two wrapped lines rather than one fixed row.

    A fixed-width row cannot hold this: an exact R multiple runs to thirty
    digits and a market identity to twenty-four characters, so the row either
    overflows the page or truncates a number — and a truncated number is a
    different number. Two lines, both wrapped, fit at any value and shorten
    nothing.

    The instant is cut to the minute, which is the one shortening that is
    safe: a timestamp at a stated resolution is still that timestamp.
    """
    closed = (
        "-" if isinstance(stat.closed_at, Absent) else stat.closed_at.isoformat()[:16]
    )
    r_multiple = (
        "-"
        if isinstance(stat.r_multiple, Absent)
        else canonical_decimal_text(stat.r_multiple)
    )
    net = (
        "-"
        if isinstance(stat.realized_pnl_net, Absent)
        else f"{stat.realized_pnl_net.text} {stat.realized_pnl_net.asset.code}"
    )
    lines = _wrap(
        f"{closed}  {stat.market.value}  {stat.result.value}", indent="   "
    )
    lines.extend(_wrap(f"R {r_multiple}   net {net}", indent="     "))
    return lines


def _require_report(report: StatisticsReport) -> None:
    if not isinstance(report, StatisticsReport):
        raise TypeError(
            f"report must be a StatisticsReport, got {type(report).__name__}"
        )


def _fitted(lines: list[str]) -> str:
    """Join the page, refusing to emit a line wider than the page it claims.

    **Raised rather than printed**, which is `fmis.today.render`'s own choice
    and made for the same reason: every value that has no bound is wrapped
    before it reaches here, so an over-wide line is a defect in *this* module
    rather than an unusual input, and a page that silently ran to 145 columns
    is one whose width claim nobody was checking. It ran to 145 columns —
    a store path printed on one line — until this guard was added.

    Measured in **characters**, not bytes. An em-dash is three bytes and one
    column, and a byte-counting check reports every line of prose as over-wide.
    """
    for line in lines:
        if len(line) > _WIDTH:
            raise StatisticsRefusedError(
                f"rendered line of {len(line)} characters exceeds the "
                f"{_WIDTH}-column page: {line!r}"
            )
    return "\n".join(lines)
