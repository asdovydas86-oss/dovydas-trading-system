"""Readings in, one frozen pulse out. The ordering rule, and nothing else.

This module assembles what `fmis.market_pulse.measure` produced. It computes no
market quantity — a guard test asserts it holds no arithmetic operator — and it
adds no information: every number on the resulting page was already on a reading
before this module ran.

**The ordering rule, stated in full.**

    Markets are ordered by one measured quantity: their `period_return` over
    exactly one named horizon, among markets denominated in exactly one quote
    unit. Higher first. A tie is broken by `benchmark_id`, ascending.

That is the whole of it. There is no second component, no weight, no
normalization and no total, and `HorizonRanking` has no field one could enter
through. This is deliberately *weaker* than `fmis.swing_workspace.ranking`,
which orders setups by a four-component lexicographic key: that key exists
because four engine states genuinely bear on whether a setup is actionable.
Nothing comparable is true of *"which market moved most"* — it is one number,
and combining it with volatility or volume would produce an ordering whose
meaning nobody could state.

**An ordering is scoped to one quote unit, and that is a refusal rather than a
filter.** A percentage move in a market priced in EUR silently contains the
EUR/USD move; placed beside a USD-denominated return it would rank the currency
pair as much as the markets. So a universe spanning two units produces **two
orderings** for one horizon rather than one mixed ordering, each printing the
unit it compares. Markets in another unit are not *excluded* from an ordering —
they are outside the comparison it defines, and they get their own.

Units are visited in the order the universe first mentions them, so the page is
a function of the configuration rather than of a set's iteration order.

**Two reasons a market of the right unit is excluded, each reported:**

  * it produced no reading — a provider failure, or no provider configured at
    all, with that reason carried verbatim;
  * its move over that horizon is unavailable — a window shorter than the
    horizon names, or a mathematically undefined result.

An excluded market is never silently dropped. `HorizonRanking.excluded` carries
every one with its reason, because a leaderboard missing the market that
actually moved most reads as a complete picture and is not one.

**Co-movement is measured against one named reference**, not as a matrix. A
matrix over eleven markets is fifty-five numbers nobody reads, and every one of
them invites the causal reading `CO_MOVEMENT_CAVEAT` exists to refuse. The
reference is the first read market in universe order — a stated choice, printed
on the page, never inferred from the data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from fmis.data.observation import ObservationSeries
from fmis.market_pulse.measure import measure_co_movement
from fmis.market_pulse.models import (
    CoMovement,
    Horizon,
    HorizonRanking,
    MarketPulse,
    MarketReading,
    MarketUnavailable,
    MarketUniverse,
    QuantityKind,
    RankedMove,
)

__all__ = [
    "ORDERING_QUANTITY",
    "ORDERING_UNIT_SCOPE",
    "EXCLUDED_FROM_ORDERING",
    "NOT_READ_REASON",
    "RATE_LIKE_EXCLUSION",
    "MINIMUM_ORDERED_MARKETS",
    "rank_by_horizon",
    "co_movements_against",
    "build_market_pulse",
]

#: Printed on every ordering. The exact quantity that produced the order, named
#: so a reader can reconstruct it without opening this file.
ORDERING_QUANTITY = (
    "period_return over the stated horizon, measured from closed bar closes"
)

#: Named on the page as *not* participating in any ordering. Each is a quantity
#: this repository can produce and that a reader might reasonably assume is
#: folded in. Stating them is cheaper than being asked.
EXCLUDED_FROM_ORDERING: tuple[str, ...] = (
    "realized volatility",
    "traded volume",
    "market capitalization",
    "any other horizon's move",
    "market structure, trend or regime",
    "any setup, signal or evidence this repository produces elsewhere",
    "the order the universe configures",
)

#: Printed above the orderings. Why there may be more than one for a horizon,
#: and why a market can be absent from all of them without anything being wrong.
ORDERING_UNIT_SCOPE = (
    "An ordering compares only markets denominated in the same quote unit. A "
    "return on a market priced in another currency contains that currency's "
    "own move, so placing the two side by side would order the exchange rate "
    "as much as the markets. Each unit present in the universe is ordered "
    "separately, and a unit with no readable market produces no ordering."
)

#: Why a market has no position in an ordering when it produced no reading.
NOT_READ_REASON = "no reading was produced for this market"

#: Why a yield is never placed in an ordering, however many other yields share
#: its unit.
#:
#: **Added by Milestone BU, and it closes the one hole the unit rule left open.**
#: Scoping an ordering by quote unit keeps a USD return away from a USDT return,
#: but two Treasury yields share the unit *percent per annum* exactly — so
#: without this they would have been ordered against each other by
#: `period_return`, and a page would have reported the 10-year as having "moved"
#: +2.38% when what happened was +10 basis points. That figure is arithmetically
#: correct and answers a question nobody asked. A yield's move belongs to
#: `fmits macro`, which states it in basis points.
RATE_LIKE_EXCLUSION = (
    "this market is a rate, not a price: its move is a difference in basis "
    "points rather than a percentage return, so it is not ordered against "
    "price-like markets or against other rates here — see `fmits macro`"
)

#: How many markets an ordering must place to be one.
#:
#: **Two, because a comparison needs two things.** An ordering that placed a
#: single market would print a leaderboard with one row under a heading claiming
#: a comparison had been made, and an ordering that placed none would print a
#: heading over a list of absences.
#:
#: **Milestone BU is what made this necessary rather than tidy.** Before BU every
#: readable market was crypto quoted in USDT on one cadence, so a universe of six
#: markets over three horizons produced three orderings of six. BU's universe
#: spans two observation cadences and five quote units, and the full cross
#: product is thirty (horizon, unit) pairs of which twenty-seven place nothing —
#: a market is not measured over the other cadence's horizons, and a unit with
#: one market has nothing to order it against. Emitting all thirty buried the
#: three real orderings under twelve sections reading *"no market in this unit
#: could be ordered"*.
#:
#: **Nothing is hidden by this.** A market absent from every ordering still
#: carries its own move on its own row, and a market that could not be read is
#: still reported — with its reason — in the page's unavailable section. What is
#: dropped is a heading, never a fact.
MINIMUM_ORDERED_MARKETS = 2


def _ordering_units(universe: MarketUniverse) -> tuple[str, ...]:
    """Quote units worth ordering, in the order the universe first names them.

    Only units with at least one **supported** market. A unit whose every market
    is unsupported would otherwise produce an ordering that places nothing and
    excludes everything — a section header over a list of the same absences the
    page already reports once, in the place a reader looks for them.
    """
    units: list[str] = []
    for benchmark in universe.benchmarks:
        if benchmark.is_supported and benchmark.quote_unit not in units:
            units.append(benchmark.quote_unit)
    return tuple(units)


def rank_by_horizon(
    universe: MarketUniverse,
    readings: Sequence[MarketReading],
    horizon: Horizon,
    *,
    quote_unit: str,
) -> HorizonRanking:
    """Markets denominated in ``quote_unit``, ordered by their move over ``horizon``.

    Every market in ``universe`` **with that quote unit** appears exactly once —
    in `ordered` if its move was measured, in `excluded` with its reason
    otherwise. A market in another unit is outside this comparison entirely and
    is neither placed nor excluded; see `ORDERING_UNIT_SCOPE`.

    **The order is produced by two stable sorts rather than one composite key**:
    ascending by `benchmark_id`, then descending by value. Python's sort keeps
    equal elements in their existing relative order even under ``reverse``, so
    the result is exactly *(value descending, id ascending)* — a total order,
    with no negation of a market quantity anywhere in it. Two markets that moved
    identically are placed by id, so the same history always produces the same
    page. Nothing here reads a set, a dict's iteration order or an object's
    identity.
    """
    if not isinstance(horizon, Horizon):
        raise TypeError(f"horizon must be a Horizon, got {type(horizon).__name__}")
    by_id = {reading.benchmark_id: reading for reading in readings}
    placed: list[RankedMove] = []
    excluded: list[tuple[str, str]] = []
    for benchmark in universe.benchmarks:
        if benchmark.quote_unit != quote_unit:
            continue
        if benchmark.quantity_kind is QuantityKind.RATE_LIKE:
            excluded.append((benchmark.benchmark_id, RATE_LIKE_EXCLUSION))
            continue
        if not benchmark.is_supported:
            excluded.append((benchmark.benchmark_id, benchmark.unsupported_reason))
            continue
        reading = by_id.get(benchmark.benchmark_id)
        if reading is None:
            excluded.append((benchmark.benchmark_id, NOT_READ_REASON))
            continue
        move = reading.move_for(horizon.horizon_id)
        if move is None:
            excluded.append(
                (
                    benchmark.benchmark_id,
                    f"this reading holds no move for {horizon.horizon_id}",
                )
            )
            continue
        if not move.is_measured:
            excluded.append((benchmark.benchmark_id, move.unavailable_reason))
            continue
        placed.append(
            RankedMove(
                benchmark_id=benchmark.benchmark_id,
                display_name=benchmark.display_name,
                value=move.value,
            )
        )
    placed.sort(key=lambda row: row.benchmark_id)
    placed.sort(key=lambda row: row.value, reverse=True)
    return HorizonRanking(
        horizon_id=horizon.horizon_id,
        quote_unit=quote_unit,
        ordering_quantity=ORDERING_QUANTITY,
        ordered=tuple(placed),
        excluded=tuple(excluded),
    )


def co_movements_against(
    reference_id: str,
    observations: Mapping[str, ObservationSeries],
    order: Sequence[str],
    horizon: Horizon,
) -> tuple[CoMovement, ...]:
    """Every read market's co-movement with ``reference_id``, in ``order``.

    The reference is not correlated with itself — that value is `1.0` by
    construction and is arithmetic rather than information, which
    `CoMovement.__post_init__` refuses outright. A market with no observations
    is skipped rather than reported: it already appears on the page as
    unavailable, and a second absence for it would be the same fact twice.
    """
    reference = observations.get(reference_id)
    if reference is None:
        return ()
    found: list[CoMovement] = []
    for benchmark_id in order:
        if benchmark_id == reference_id:
            continue
        subject = observations.get(benchmark_id)
        if subject is None:
            continue
        found.append(
            measure_co_movement(
                benchmark_id, subject, reference_id, reference, horizon
            )
        )
    return tuple(found)


def build_market_pulse(
    *,
    as_of: datetime,
    universe: MarketUniverse,
    readings: Sequence[MarketReading],
    unavailable: Sequence[MarketUnavailable],
    horizons: Sequence[Horizon],
    observations: Mapping[str, ObservationSeries] | None = None,
    co_movement_horizon: Horizon | None = None,
) -> MarketPulse:
    """Assemble one immutable pulse from measured readings and stated failures.

    Args:
        as_of: the instant this page describes. Supplied rather than read, so
            two runs over one history produce one page.
        universe: the stated scope. Every supported market in it must appear in
            ``readings`` or ``unavailable`` — `MarketPulse` proves it.
        readings: the markets that were read, in the order to print them.
        unavailable: the markets a configured provider failed to deliver.
        horizons: the windows measured, in the order to print them.
        observations: each read market's closed-close series, keyed by benchmark
            id. Supplied only when co-movement is wanted; `None` omits the
            section entirely rather than filling it with absences.
        co_movement_horizon: the window co-movement is measured over. Required
            when ``observations`` is supplied.

    Returns:
        A `MarketPulse` holding one ordering per (horizon, quote unit) present
        in the universe, and the co-movements if any were requested.

    Raises:
        ValueError: ``observations`` was supplied without a horizon, or the
            universe and the results disagree about which markets exist.
    """
    ordered_readings = tuple(readings)
    placed: list[HorizonRanking] = []
    for horizon in horizons:
        for unit in _ordering_units(universe):
            ranking = rank_by_horizon(
                universe, ordered_readings, horizon, quote_unit=unit
            )
            # An ordering that compares fewer than two markets is not an
            # ordering; see `MINIMUM_ORDERED_MARKETS`. The markets it would have
            # held are not lost — each already appears on its own row above, with
            # the same move, and in the unavailable section if it failed.
            if len(ranking.ordered) < MINIMUM_ORDERED_MARKETS:
                continue
            placed.append(ranking)
    rankings = tuple(placed)
    movements: tuple[CoMovement, ...] = ()
    reference_id: str | None = None
    if observations is not None:
        if co_movement_horizon is None:
            raise ValueError(
                "observations were supplied with no co-movement horizon; a "
                "correlation over an unnamed window cannot be reconstructed"
            )
        order = tuple(reading.benchmark_id for reading in ordered_readings)
        for benchmark_id in order:
            if benchmark_id in observations:
                reference_id = benchmark_id
                break
        if reference_id is not None:
            # **Only markets sampled at the reference's own cadence.** A daily
            # series and an hourly one share no bar opens, so every such pair
            # would be reported unavailable for a misalignment that is a fact
            # about two calendars rather than about the markets. Those pairs are
            # not silently dropped from the product: `fmits macro` measures them
            # over shared observation dates and states what alignment cost.
            cadence = observations[reference_id].frequency
            comparable = {
                benchmark_id: series
                for benchmark_id, series in observations.items()
                if series.frequency == cadence
            }
            movements = co_movements_against(
                reference_id, comparable, order, co_movement_horizon
            )
            if not movements:
                # A reference with nothing to compare against is not a
                # reference. Naming one anyway would print a section header
                # over an empty body and imply the comparison was attempted.
                reference_id = None
    return MarketPulse(
        as_of=as_of,
        universe=universe,
        readings=ordered_readings,
        unavailable=tuple(unavailable),
        rankings=rankings,
        horizons=tuple(horizons),
        co_movements=movements,
        co_movement_reference=reference_id,
    )
