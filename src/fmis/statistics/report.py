"""One reading of one store: every family, every curve, every cut, one asset.

The composition root. It reads nothing itself — `collect` does that — and
computes nothing itself either; it decides **which populations exist** and hands
each to the fold that knows how to reduce it.

**The corpus is split by quote asset and never summed across it.** `ST-5`. A
store settled in two assets produces two `AssetReport`s, and `StatisticsReport`
holds both rather than picking one: a page with room for a single set of figures
shows the first and says how many others exist, which is a different thing from
a page that silently dropped them.

**Everything is recomputed on every call and nothing is written.** `AP` §25.2
classes these as `Aggregate` — disposable. Deleting a report and rebuilding it
from the same store produces an equal value, and there is no code path in this
package that could write one down.

**One instant, threaded from the outermost edge.** `at` decides what has expired
and what a monitor reads; `as_of` decides what the corpus is allowed to know.
Nothing below the CLI takes a clock, so both arrive as parameters and two runs
over one store agree exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fmis.money import AssetCode, DustPolicy, Money
from fmis.persistence import TradingStore
from fmis.provenance import Absent
from fmis.records import require_utc
from fmis.statistics.breakdown import (
    DEFAULT_REGIME_DIMENSION,
    BreakdownSet,
    breakdown_set,
)
from fmis.statistics.collect import (
    COLLECT_DUST_POLICY,
    CollectedTrades,
    collect_trades,
    open_risk_limit,
    quote_assets_of,
)
from fmis.statistics.drawdown import DrawdownCurve, drawdown_curve
from fmis.statistics.equity import EquityCurve, equity_curve
from fmis.statistics.general import GeneralStatistics, general_statistics
from fmis.statistics.models import (
    DEFAULT_SAMPLE_POLICY,
    STATISTICS_LIMITATIONS,
    SamplePolicy,
    TradeStat,
)
from fmis.statistics.performance import (
    PerformanceStatistics,
    performance_statistics,
)
from fmis.statistics.quality import QualityStatistics, quality_statistics
from fmis.statistics.risk import RiskStatistics, risk_statistics, utilization_of

__all__ = [
    "AssetReport",
    "StatisticsReport",
    "build_report",
    "report_for_store",
    "recent_trades",
    "closed_between",
    "STATISTICS_OBJECTIVE",
]

#: What these pages are for, printed at the top of each. `SPEC` §25's success
#: criterion, stated as the question rather than as a claim to answer it.
STATISTICS_OBJECTIVE = (
    "Whether this system has an edge, measured from recorded history only. "
    "Every figure is arithmetic over trades the owner recorded or the simulator "
    "produced. Nothing here is estimated, inferred or predicted."
)


@dataclass(frozen=True, slots=True)
class AssetReport:
    """Every figure for one settlement asset."""

    quote_asset: AssetCode
    trades: tuple[TradeStat, ...]
    general: GeneralStatistics
    performance: PerformanceStatistics
    risk: RiskStatistics
    quality: QualityStatistics
    equity: EquityCurve
    drawdown: DrawdownCurve
    breakdowns: BreakdownSet

    @property
    def size(self) -> int:
        return len(self.trades)

    def to_payload(self) -> dict[str, Any]:
        return {
            "quote_asset": self.quote_asset.code,
            "size": self.size,
            "general": self.general.to_payload(),
            "performance": self.performance.to_payload(),
            "risk": self.risk.to_payload(),
            "quality": self.quality.to_payload(),
            "equity": self.equity.to_payload(),
            "drawdown": self.drawdown.to_payload(),
            "breakdowns": self.breakdowns.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class StatisticsReport:
    """One reading of one store, at one instant, for every asset it settles in."""

    reference_time: datetime
    store_root: str
    present: bool
    policy: SamplePolicy
    assets: tuple[AssetReport, ...]
    refused: tuple[str, ...]
    as_of: datetime | Absent
    objective: str = STATISTICS_OBJECTIVE
    limitations: tuple[tuple[str, str], ...] = STATISTICS_LIMITATIONS

    @property
    def is_empty(self) -> bool:
        return not self.assets

    @property
    def primary(self) -> AssetReport | Absent:
        """The first asset, for a surface with room for one set of figures.

        First by asset code, which `quote_assets_of` fixes — **not** by trade
        count. Ordering by size would make the page's headline figures change
        asset as the corpus grew, and an owner comparing two weeks' pages would
        be comparing two different populations without being told.
        """
        if not self.assets:
            return Absent("this store holds no trade to compute statistics over")
        return self.assets[0]

    @property
    def total_trades(self) -> int:
        return sum(entry.size for entry in self.assets)

    def for_asset(self, asset: AssetCode) -> AssetReport | Absent:
        for entry in self.assets:
            if entry.quote_asset == asset:
                return entry
        return Absent(f"this store records no trade settled in {asset.code}")

    def to_payload(self) -> dict[str, Any]:
        return {
            "reference_time": self.reference_time.isoformat(),
            "store_root": self.store_root,
            "present": self.present,
            "minimum_sample": self.policy.minimum_sample,
            "as_of": None if isinstance(self.as_of, Absent) else self.as_of.isoformat(),
            "total_trades": self.total_trades,
            "assets": [entry.to_payload() for entry in self.assets],
            "refused": list(self.refused),
            "limitations": [list(pair) for pair in self.limitations],
        }


def build_report(
    collected: CollectedTrades,
    *,
    at: datetime,
    policy: SamplePolicy = DEFAULT_SAMPLE_POLICY,
    starting_equity: Money | Absent = Absent(
        "no starting equity was supplied, and this system records the owner's "
        "opening capital nowhere"
    ),
    equity_basis: Money | Absent = Absent(
        "no equity basis was supplied for risk percentages"
    ),
    open_risk_ceiling: Money | Absent = Absent(
        "no total-open-risk ceiling was read for this report"
    ),
    as_of: datetime | Absent = Absent("no point-in-time cut was requested"),
    regime_dimension: str = DEFAULT_REGIME_DIMENSION,
) -> StatisticsReport:
    """Fold an already-collected corpus. **Pure** — no store, no clock, no I/O.

    Separated from `report_for_store` so that every figure on every page can be
    exercised from hand-built `TradeStat` values with no filesystem at all,
    which is the same separation `fmis.today` draws with `StoreReading`.

    `starting_equity` and `equity_basis` are two different baselines and are
    deliberately not one parameter: the first is what the account began with and
    turns a cumulative-P&L curve into an equity curve; the second is what a risk
    amount is a percentage *of*. An owner may know one and not the other.
    """
    if not isinstance(collected, CollectedTrades):
        raise TypeError(
            f"collected must be a CollectedTrades, got {type(collected).__name__}"
        )
    moment = require_utc(at, "at")
    if not isinstance(policy, SamplePolicy):
        raise TypeError("policy must be a SamplePolicy")
    for name, value in (
        ("starting_equity", starting_equity),
        ("equity_basis", equity_basis),
        ("open_risk_ceiling", open_risk_ceiling),
    ):
        if not isinstance(value, (Money, Absent)):
            raise TypeError(f"{name} must be a Money or Absent")

    reports: list[AssetReport] = []
    for asset in quote_assets_of(collected.trades):
        subset = collected.in_asset(asset)
        curve = equity_curve(
            subset,
            quote_asset=asset,
            starting_equity=_matching(starting_equity, asset),
        )
        risk = risk_statistics(
            subset,
            policy,
            quote_asset=asset,
            equity_basis=_matching(equity_basis, asset),
            utilization=Absent("computed below, once open risk is totalled"),
        )
        reports.append(
            AssetReport(
                quote_asset=asset,
                trades=subset,
                general=general_statistics(subset, policy),
                performance=performance_statistics(subset, policy, quote_asset=asset),
                # Utilization needs the total this same fold produces, so the
                # reduction runs once and the share is filled in from its own
                # answer. Computing open risk twice would be two chances to
                # disagree about which trades are open.
                risk=_with_utilization(
                    risk, _matching(open_risk_ceiling, asset)
                ),
                quality=quality_statistics(subset, policy),
                equity=curve,
                drawdown=drawdown_curve(curve, policy),
                breakdowns=breakdown_set(
                    subset,
                    policy,
                    quote_asset=asset,
                    regime_dimension=regime_dimension,
                ),
            )
        )
    return StatisticsReport(
        reference_time=moment,
        store_root=collected.store_root,
        present=collected.present,
        policy=policy,
        assets=tuple(reports),
        refused=collected.refused,
        as_of=as_of,
    )


def _with_utilization(
    reading: RiskStatistics, ceiling: Money | Absent
) -> RiskStatistics:
    """Fill in the one field that depends on this same reading's own total."""
    return RiskStatistics(
        quote_asset=reading.quote_asset,
        open_risk=reading.open_risk,
        closed_risk=reading.closed_risk,
        largest_open_risk=reading.largest_open_risk,
        largest_closed_risk=reading.largest_closed_risk,
        average_open_risk=reading.average_open_risk,
        average_closed_risk=reading.average_closed_risk,
        total_open_risk=reading.total_open_risk,
        risk_utilization=utilization_of(reading.total_open_risk, ceiling),
        risk_fraction=reading.risk_fraction,
        average_risk_fraction=reading.average_risk_fraction,
        median_risk_fraction=reading.median_risk_fraction,
        equity_basis=reading.equity_basis,
    )


def _matching(value: Money | Absent, asset: AssetCode) -> Money | Absent:
    """A money baseline applies only to the asset it is denominated in.

    A store settled in two assets and one supplied baseline gets that baseline
    on one of them and a named absence on the other, rather than the same number
    silently doing duty for both.
    """
    if isinstance(value, Absent):
        return value
    if value.asset == asset:
        return value
    return Absent(
        f"the supplied baseline is in {value.asset.code} and these trades settle "
        f"in {asset.code}; no rate in this system crosses them"
    )


def report_for_store(
    root: Path | str,
    *,
    at: datetime,
    policy: SamplePolicy = DEFAULT_SAMPLE_POLICY,
    starting_equity: Money | Absent = Absent(
        "no starting equity was supplied, and this system records the owner's "
        "opening capital nowhere"
    ),
    equity_basis: Money | Absent = Absent(
        "no equity basis was supplied for risk percentages"
    ),
    as_of: datetime | Absent = Absent("no point-in-time cut was requested"),
    regime_dimension: str = DEFAULT_REGIME_DIMENSION,
    dust: DustPolicy = COLLECT_DUST_POLICY,
) -> StatisticsReport:
    """Read one store and fold it. The outer edge of this package.

    The owner's open-risk ceiling is read here rather than passed in, because it
    is a record in the same store and reading it separately would let a caller
    supply a ceiling the store contradicts.
    """
    moment = require_utc(at, "at")
    collected = collect_trades(root, at=moment, as_of=as_of, dust=dust)
    ceiling: Money | Absent = Absent(
        "the store holds no records, so no risk ceiling was read"
    )
    if collected.present:
        ceiling = open_risk_limit(TradingStore(Path(root), dust=dust), at=moment)
    return build_report(
        collected,
        at=moment,
        policy=policy,
        starting_equity=starting_equity,
        equity_basis=equity_basis,
        open_risk_ceiling=ceiling,
        as_of=as_of,
        regime_dimension=regime_dimension,
    )


def recent_trades(trades: tuple[TradeStat, ...], limit: int) -> tuple[TradeStat, ...]:
    """The most recently closed trades, newest first.

    Ordered by close instant and then by reference, so two trades closing in one
    instant do not swap between runs. A trade that has not closed is excluded
    rather than sorted by its commitment: *"my last ten trades"* means ten
    results, and a running trade has none.
    """
    if not isinstance(trades, tuple):
        raise TypeError("trades must be a tuple of TradeStat")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("limit must be a non-negative int")
    finished = [
        stat
        for stat in trades
        if stat.is_closed and not isinstance(stat.closed_at, Absent)
    ]
    finished.sort(key=lambda stat: (stat.closed_at, stat.trade_ref), reverse=True)
    return tuple(finished[:limit])


def closed_between(
    trades: tuple[TradeStat, ...], *, start: datetime, end: datetime
) -> tuple[TradeStat, ...]:
    """Every trade that closed inside a half-open window `[start, end)`.

    Half-open so that consecutive days partition the corpus exactly once: a
    trade closing at midnight belongs to the day that is starting, and a closed
    interval would count it on both sides of the boundary.
    """
    if not isinstance(trades, tuple):
        raise TypeError("trades must be a tuple of TradeStat")
    first = require_utc(start, "start")
    last = require_utc(end, "end")
    if last < first:
        raise ValueError("end precedes start")
    return tuple(
        stat
        for stat in trades
        if stat.is_closed
        and not isinstance(stat.closed_at, Absent)
        and first <= stat.closed_at < last
    )
