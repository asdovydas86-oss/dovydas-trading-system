"""Cutting the corpus by one dimension at a time, and saying how many cuts.

`AP` §20.3's cohort dimensions, built for the ones this system's records
actually carry. A dimension whose value a record does not hold produces an
`UNCLASSIFIED` cell rather than a dropped trade: *"eleven of my trades name no
setup type"* is a finding about the owner's record-keeping, and silently
excluding them would make the classified minority speak for everything.

**The multiplicity hazard is a mechanism here, not a paragraph.**
`TRADER_WORKSPACE` §3.4.12 is explicit that with roughly twenty-five
segmentations and no multiplicity correction, *"a new set of striking-looking
cells will appear, and the defence is a document, not a mechanism."* The
mechanism is `BreakdownSet.cells_examined`: the count of every cell produced
across every dimension, carried on the object and rendered beside any cell the
owner is reading. This package applies **no** correction — it has no basis to
choose one — and states the number instead of implying there was nothing to
correct.

**Every cell carries its own `n` and its own sample floor.** A per-symbol win
rate over three trades is refused exactly as the corpus-wide one is, which is
what makes the breakdown safe to look at: the cells that survive slicing are
the ones with enough trades behind them, and the rest say so.

**`UNCLASSIFIED` is `fmis.portfolio_risk`'s own constant, reused.** A second
spelling of *"this record does not say"* would be a second thing a reader has to
learn means the same.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from fmis.accounts import BOOK_ORDER
from fmis.money import AssetCode
from fmis.portfolio_risk import UNCLASSIFIED
from fmis.provenance import Absent
from fmis.records import require_text
from fmis.statistics.general import GeneralStatistics, general_statistics
from fmis.statistics.models import SamplePolicy, StatSource, TradeStat
from fmis.statistics.performance import PerformanceStatistics, performance_statistics

__all__ = [
    "BreakdownCell",
    "Breakdown",
    "BreakdownSet",
    "DIMENSIONS",
    "DIMENSION_NAMES",
    "cut_by",
    "breakdown_set",
    "MULTIPLICITY_NOTE",
    "DEFAULT_REGIME_DIMENSION",
]

#: Rendered beside every breakdown. `TRADER_WORKSPACE` §3.4.12's mechanism.
MULTIPLICITY_NOTE = (
    "No multiplicity correction is applied to these cells and none is implied. "
    "The number of cells examined is stated so that a striking-looking cell can "
    "be read against how many chances there were for one to appear."
)

#: Which regime dimension a per-regime breakdown groups on when the caller names
#: none. Chosen rather than merged: `RegimeReading` holds several dimensions and
#: a composite key across all of them would produce a cell per combination, most
#: of them holding one trade.
#:
#: **It must be a name the regime engine actually emits**, and the first draft
#: of this constant was `"trend"` — a dimension that engine has never produced,
#: so the default cut silently placed every trade in `UNCLASSIFIED` and the
#: per-regime breakdown was dead on arrival. The value is copied here rather
#: than imported because this package may not reach the market half; the
#: engine's own module is deliberately not named in this file, because a
#: repository-wide scan reads a mention as a dependency. What keeps the copy
#: honest is `test_statistics_architecture`, which asserts it still matches
#: `RegimeDimensionName` — the same copy-and-guard the boundary tests use for
#: the market-half list itself.
DEFAULT_REGIME_DIMENSION = "structure"


def _symbol_of(stat: TradeStat) -> str:
    return f"{stat.market.base_asset.code}{stat.market.quote_asset.code}"


def _period_key(moment: datetime | Absent, span: str) -> str:
    """A calendar bucket for a trade's close, in UTC — `ST-8`.

    A trade that has not closed has no calendar period. Bucketing it by the
    instant it was committed would put a running trade into a completed month's
    performance, which is the shape of a figure that changes after the month is
    over.
    """
    if isinstance(moment, Absent):
        return UNCLASSIFIED
    if span == "month":
        return f"{moment.year:04d}-{moment.month:02d}"
    if span == "quarter":
        return f"{moment.year:04d}-Q{(moment.month - 1) // 3 + 1}"
    return f"{moment.year:04d}"


def _plain(value: str | Absent) -> str:
    return UNCLASSIFIED if isinstance(value, Absent) else value


#: Every dimension, its key function and the order its cells are rendered in.
#: A tuple rather than a dict so the order is the declaration order and a new
#: dimension is a visible edit — the count of cells examined depends on this
#: list, so it must not be assembled by accident.
DIMENSIONS: tuple[tuple[str, Callable[[TradeStat], str]], ...] = (
    ("symbol", _symbol_of),
    ("venue", lambda stat: stat.market.venue.value),
    ("timeframe", lambda stat: _plain(stat.interval)),
    ("setup", lambda stat: _plain(stat.setup_type)),
    ("direction", lambda stat: stat.direction.value),
    ("book", lambda stat: stat.book.value),
    ("source", lambda stat: stat.source.value),
    ("account", lambda stat: _plain(stat.account)),
    ("month", lambda stat: _period_key(stat.closed_at, "month")),
    ("quarter", lambda stat: _period_key(stat.closed_at, "quarter")),
    ("year", lambda stat: _period_key(stat.closed_at, "year")),
)

#: The dimension names, for a caller naming one on a command line.
DIMENSION_NAMES: tuple[str, ...] = tuple(name for name, _ in DIMENSIONS) + ("regime",)


@dataclass(frozen=True, slots=True)
class BreakdownCell:
    """One value of one dimension, with the corpus narrowed to it."""

    key: str
    general: GeneralStatistics
    performance: PerformanceStatistics

    @property
    def size(self) -> int:
        return self.general.total

    def to_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "general": self.general.to_payload(),
            "performance": self.performance.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class Breakdown:
    """Every cell of one dimension, in a stable order."""

    dimension: str
    cells: tuple[BreakdownCell, ...]
    quote_asset: AssetCode

    def __post_init__(self) -> None:
        object.__setattr__(self, "dimension", require_text(self.dimension, "dimension"))
        if not isinstance(self.cells, tuple):
            raise TypeError("cells must be a tuple of BreakdownCell")
        keys = [cell.key for cell in self.cells]
        if len(set(keys)) != len(keys):
            raise TypeError(
                f"dimension {self.dimension!r} produced a duplicate cell key; two "
                "cells for one value would let a reader pick the one they preferred"
            )

    @property
    def size(self) -> int:
        return len(self.cells)

    def cell(self, key: str) -> BreakdownCell | Absent:
        for entry in self.cells:
            if entry.key == key:
                return entry
        return Absent(f"no trade in this corpus falls under {key!r}")

    def to_payload(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "quote_asset": self.quote_asset.code,
            "cells": [cell.to_payload() for cell in self.cells],
        }


@dataclass(frozen=True, slots=True)
class BreakdownSet:
    """Every dimension computed, and the total number of cells that produced.

    `cells_examined` is the whole point of this type. A `Breakdown` on its own
    invites the reader to look at its best cell; the set knows how many cells
    they were choosing from.
    """

    breakdowns: tuple[Breakdown, ...]
    regime_dimension: str
    note: str = MULTIPLICITY_NOTE

    @property
    def cells_examined(self) -> int:
        return sum(entry.size for entry in self.breakdowns)

    def by_dimension(self, dimension: str) -> Breakdown | Absent:
        for entry in self.breakdowns:
            if entry.dimension == dimension:
                return entry
        return Absent(
            f"{dimension!r} is not a dimension this engine cuts on; the choices "
            f"are {', '.join(DIMENSION_NAMES)}"
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "cells_examined": self.cells_examined,
            "regime_dimension": self.regime_dimension,
            "breakdowns": [entry.to_payload() for entry in self.breakdowns],
        }


def _cell_order(dimension: str, keys: list[str]) -> list[str]:
    """The order a dimension's cells are rendered in.

    Books follow `BOOK_ORDER` and sources follow their enum, because both are
    small closed sets with a meaningful sequence. Everything else is
    alphabetical with `UNCLASSIFIED` last — sorting by size would put the
    largest cell first and quietly rank the dimensions by prominence, and this
    package ranks nothing.
    """
    if dimension == "book":
        ordered = [book.value for book in BOOK_ORDER if book.value in keys]
    elif dimension == "source":
        ordered = [origin.value for origin in StatSource if origin.value in keys]
    else:
        ordered = sorted(key for key in keys if key != UNCLASSIFIED)
    remaining = [key for key in sorted(keys) if key not in ordered]
    return ordered + remaining


def cut_by(
    trades: tuple[TradeStat, ...],
    dimension: str,
    key_of: Callable[[TradeStat], str],
    policy: SamplePolicy,
    *,
    quote_asset: AssetCode,
) -> Breakdown:
    """Cut one corpus by one dimension, computing each cell's own statistics.

    Named `cut_by` rather than `breakdown_by` because `fmis.portfolio_risk`
    already exports that name for breaking **exposure** down by dimension, and
    this repository holds zero public-name collisions as a measured invariant.
    The two do different things over different inputs, so sharing a name would
    make an `import *` silently resolve to whichever came last.
    """
    if not isinstance(trades, tuple):
        raise TypeError("trades must be a tuple of TradeStat")
    require_text(dimension, "dimension")
    if not callable(key_of):
        raise TypeError("key_of must be callable")
    if not isinstance(policy, SamplePolicy):
        raise TypeError("policy must be a SamplePolicy")
    if not isinstance(quote_asset, AssetCode):
        raise TypeError("quote_asset must be an AssetCode")

    grouped: dict[str, list[TradeStat]] = {}
    for stat in trades:
        grouped.setdefault(key_of(stat), []).append(stat)
    return Breakdown(
        dimension=dimension,
        quote_asset=quote_asset,
        cells=tuple(
            BreakdownCell(
                key=key,
                general=general_statistics(tuple(grouped[key]), policy),
                performance=performance_statistics(
                    tuple(grouped[key]), policy, quote_asset=quote_asset
                ),
            )
            for key in _cell_order(dimension, list(grouped))
        ),
    )


def breakdown_set(
    trades: tuple[TradeStat, ...],
    policy: SamplePolicy,
    *,
    quote_asset: AssetCode,
    regime_dimension: str = DEFAULT_REGIME_DIMENSION,
) -> BreakdownSet:
    """Every dimension, cut, with the count of cells that produced.

    The regime dimension is a parameter because `RegimeReading` holds several
    and this engine picks none for the owner. The name used is carried on the
    result, so a page cannot show *"by regime"* without saying which regime.
    """
    require_text(regime_dimension, "regime_dimension")
    cuts = [
        cut_by(trades, name, key_of, policy, quote_asset=quote_asset)
        for name, key_of in DIMENSIONS
    ]
    cuts.append(
        cut_by(
            trades,
            "regime",
            lambda stat: stat.regime_states.get(regime_dimension, UNCLASSIFIED),
            policy,
            quote_asset=quote_asset,
        )
    )
    return BreakdownSet(
        breakdowns=tuple(cuts), regime_dimension=regime_dimension
    )
