"""Simulating one trade over historical bars. **The fill rules are borrowed, not restated.**

The single most dangerous thing a backtest can do is invent its own, slightly
kinder, definition of where an order filled. This module therefore owns no fill
rule at all:

* the **gap rule** — a level fills at the level unless the bar opened past it,
  in which case it fills at the open — is `fmis.paper.fills.fill_at_level`,
  called;
* whether a bar **touched** a level is `PriceBar.reached`, called;
* the bar type, with its own invariant that the extremes contain the body, is
  `fmis.paper.models.PriceBar`;
* the cost basis is `fmis.trade_lifecycle.PaperCostPolicy`, the same versioned
  type the owner's paper trades already carry.

A test asserts this module contains no second comparison of a high or a low
against a stop or a target. What is genuinely new here is only the *loop*: a
single entry, a single target, no stop management, walked bar by bar, with R
bookkeeping — and that loop is what the production paper engine does not offer,
because it exists to run one live trade rather than tens of thousands of
hypothetical ones.

**Three rules that decide whether this measurement flatters itself.**

1. **Entry is the open of the bar after the signal.** Never the close that
   produced the signal. `fmis.paper.fills.entry_reached` states the same rule
   for the same reason: filling at the price you were looking at when you
   decided is a one-bar lookahead wearing a realism costume.
2. **A bar that reaches both levels halts as ambiguous.** It is never resolved
   toward the target, never toward the stop, and never by candle colour.
3. **The stop is tested before the target on the entry bar only when the entry
   gapped through it** — otherwise both are tested together and rule 2 applies.
   There is no ordering rule that could favour the target.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fmis.data import CandleSeries
from fmis.paper.fills import fill_at_level
from fmis.paper.models import PriceBar
from fmis.snapshotting import TradeDirection
from fmis.swing_lab.models import LabExitReason, LabTrade, SwingLabError
from fmis.swing_setup.models import Direction
from fmis.trade_lifecycle import PaperCostPolicy

__all__ = [
    "FRICTIONLESS_COSTS",
    "CONSERVATIVE_COSTS",
    "COST_SCENARIOS",
    "LAB_TRADE_BASIS",
    "to_price_bars",
    "simulate_trade",
    "reprice",
]

#: The zero-cost scenario. Named a policy rather than an omission, exactly as
#: `PaperCostPolicy`'s own docstring argues: a zero that is a stated basis and a
#: zero that is a forgotten multiplication look identical in a result table.
FRICTIONLESS_COSTS = PaperCostPolicy(
    policy_id="swing-lab-frictionless",
    version=1,
    fee_rate=Decimal("0"),
    slippage_rate=Decimal("0"),
)

#: A deliberately conservative round-turn cost, applied to **both** the entry and
#: the exit notional. 10 basis points per side is above every major spot venue's
#: published taker fee, and it is chosen to be pessimistic rather than accurate:
#: this milestone's question is whether an edge *survives* costs, and a
#: pessimistic answer to that question is the useful one. It is **not** a claim
#: about any particular venue's fees, and no venue is named.
#:
#: `slippage_rate` remains zero and is carried, not applied — modelling slippage
#: needs spread and depth data FMITS does not ingest, and inventing a figure
#: would be a guess wearing a policy's clothes (`PaperCostPolicy`'s own words).
CONSERVATIVE_COSTS = PaperCostPolicy(
    policy_id="swing-lab-conservative-10bps",
    version=1,
    fee_rate=Decimal("0.001"),
    slippage_rate=Decimal("0"),
)

#: Every scenario a study reports, in presentation order.
COST_SCENARIOS: tuple[PaperCostPolicy, ...] = (FRICTIONLESS_COSTS, CONSERVATIVE_COSTS)

LAB_TRADE_BASIS = (
    "Every R multiple is measured against the initial risk — the distance from "
    "the actual entry fill to the initial stop — and never against the planned "
    "reference price. Entry is a market fill at the open of the bar after the "
    "signal. A bar reaching both the stop and the target halts as ambiguous and "
    "is excluded from expectancy. Fees are charged on the entry and the exit "
    "notional; slippage is carried and not applied."
)

_DIRECTION_TO_TRADE: dict[Direction, TradeDirection] = {
    Direction.LONG: TradeDirection.LONG,
    Direction.SHORT: TradeDirection.SHORT,
}


def _exact(value: float | Decimal, name: str) -> Decimal:
    """A price as an exact decimal, via ``str`` so no binary artefact survives.

    ``Decimal(0.1)`` is ``0.1000000000000000055511151231257827``; ``Decimal(
    str(0.1))`` is ``0.1``. Prices arrive here as floats from the setup engine,
    and carrying a float's representation error into a stop comparison would
    make a level "reached" or "not reached" on the seventeenth decimal place.
    """
    if isinstance(value, Decimal):
        candidate = value
    elif isinstance(value, float) and value == value and value not in (float("inf"), float("-inf")):
        candidate = Decimal(str(value))
    elif isinstance(value, int) and not isinstance(value, bool):
        candidate = Decimal(value)
    else:
        raise SwingLabError(f"{name} must be a finite real price, got {value!r}")
    try:
        candidate = Decimal(candidate)
    except InvalidOperation:  # pragma: no cover - unreachable via the guards above
        raise SwingLabError(f"{name} is not a usable decimal") from None
    if candidate <= 0:
        raise SwingLabError(f"{name} must be positive, got {candidate}")
    return candidate


def to_price_bars(series: CandleSeries) -> tuple[PriceBar, ...]:
    """Adapt a canonical closed-candle series into the paper engine's bar type.

    A conversion, never a computation: four prices and an instant are copied
    across, and `PriceBar`'s own constructor re-checks that the extremes contain
    the body — so a provider row that violates it fails here rather than
    producing a silently impossible fill later.
    """
    if not isinstance(series, CandleSeries):
        raise TypeError(f"series must be a CandleSeries, got {type(series).__name__}")
    return tuple(
        PriceBar(
            symbol=series.symbol,
            interval=series.timeframe,
            open_time=candle.timestamp,
            open=_exact(candle.open, "open"),
            high=_exact(candle.high, "high"),
            low=_exact(candle.low, "low"),
            close=_exact(candle.close, "close"),
        )
        for candle in series.candles
    )


def _excursions(
    bars: Sequence[PriceBar], side: TradeDirection, entry: Decimal
) -> tuple[Decimal, Decimal]:
    """Best and worst prices seen while exposed, from the bars' own extremes."""
    best = worst = entry
    for bar in bars:
        favourable = bar.favourable_extreme(side)
        adverse = bar.adverse_extreme(side)
        if side.sign * (favourable - best) > 0:
            best = favourable
        if side.sign * (adverse - worst) < 0:
            worst = adverse
    return best, worst


def simulate_trade(
    bars: Sequence[PriceBar],
    *,
    variant_id: str,
    symbol: str,
    setup_id: str,
    direction: Direction,
    signal_index: int,
    signal_at: datetime,
    reference_price: float | Decimal,
    stop_price: float | Decimal,
    target_price: float | Decimal,
    planned_risk_reward: float,
    window_bars: int,
    costs: PaperCostPolicy,
    segment: str | None = None,
    context_regime_structure: str = "",
    context_structural_trend: str = "",
    setup_structural_trend: str = "",
) -> LabTrade:
    """Walk ``bars`` forward from ``signal_index`` and produce one terminal trade.

    ``signal_index`` is the position of the bar whose **close** produced the
    signal. The entry bar is the next one; if there is no next bar the trade is
    `LabExitReason.NO_ENTRY_BAR` and carries no R — the study ran out of history,
    which is a fact about the dataset and not a flat trade.

    Deterministic and pure: no clock, no randomness, no network. The same bars
    and the same arguments produce the same trade, always.

    Raises:
        SwingLabError: a price is unusable, the geometry places the stop or the
            target on the wrong side of the entry, or ``window_bars`` is not
            positive.
    """
    if isinstance(window_bars, bool) or not isinstance(window_bars, int) or window_bars <= 0:
        raise SwingLabError("window_bars must be a positive int")
    if not isinstance(costs, PaperCostPolicy):
        raise TypeError("costs must be a PaperCostPolicy")
    if direction not in _DIRECTION_TO_TRADE:
        raise SwingLabError(f"direction must be LONG or SHORT, got {direction!r}")
    side = _DIRECTION_TO_TRADE[direction]

    stop = _exact(stop_price, "stop_price")
    target = _exact(target_price, "target_price")
    reference = _exact(reference_price, "reference_price")

    def _unentered(reason: LabExitReason) -> LabTrade:
        return LabTrade(
            variant_id=variant_id, symbol=symbol, setup_id=setup_id,
            direction=direction, signal_at=signal_at, entry_at=None,
            entry_price=None, initial_stop=stop, target=target,
            planned_reference_price=reference, exit_at=None, exit_price=None,
            exit_reason=reason, bars_held=0, gross_r=None, net_r=None,
            mfe_r=None, mae_r=None, cost_policy_id=costs.policy_id,
            planned_risk_reward=planned_risk_reward, segment=segment,
            context_regime_structure=context_regime_structure,
            context_structural_trend=context_structural_trend,
            setup_structural_trend=setup_structural_trend,
        )

    if signal_index < 0 or signal_index + 1 >= len(bars):
        return _unentered(LabExitReason.NO_ENTRY_BAR)

    # Rule 1: the entry is the open of the bar *after* the signal bar.
    entry_bar = bars[signal_index + 1]
    entry = entry_bar.open
    risk = side.sign * (entry - stop)
    if risk <= 0:
        # The entry opened at or beyond the stop. The trade is not skipped —
        # skipping would delete exactly the worst fills — it is recorded as a
        # loss at the fill, with the stop distance it actually had.
        return LabTrade(
            variant_id=variant_id, symbol=symbol, setup_id=setup_id,
            direction=direction, signal_at=signal_at,
            entry_at=entry_bar.open_time, entry_price=entry, initial_stop=stop,
            target=target, planned_reference_price=reference,
            exit_at=entry_bar.open_time, exit_price=entry,
            exit_reason=LabExitReason.ENTRY_GAPPED_THROUGH_STOP, bars_held=0,
            gross_r=Decimal("-1"), net_r=Decimal("-1"),
            mfe_r=Decimal("0"), mae_r=Decimal("0"),
            cost_policy_id=costs.policy_id,
            planned_risk_reward=planned_risk_reward, segment=segment,
            context_regime_structure=context_regime_structure,
            context_structural_trend=context_structural_trend,
            setup_structural_trend=setup_structural_trend,
            metadata={"note": "the entry bar opened at or beyond the initial stop"},
        )
    if side.sign * (target - entry) <= 0:
        # The entry gapped past the target. Not a free win: there is no longer a
        # trade to take, because the thesis' whole reward was already spent.
        return _unentered(LabExitReason.NO_ENTRY_BAR)

    window = bars[signal_index + 1 : signal_index + 1 + window_bars]
    exit_price: Decimal | None = None
    exit_at: datetime | None = None
    reason = LabExitReason.TIME_STOP
    held = 0
    for position, bar in enumerate(window, start=1):
        held = position
        # Rules 2 and 3: both levels are tested together, with no ordering that
        # could favour either. `reached` and `fill_at_level` are the paper
        # engine's, called — this module never compares a high to a level.
        target_hit = bar.reached(side, target, favourable=True)
        stop_hit = bar.reached(side, stop, favourable=False)
        if target_hit and stop_hit:
            reason = LabExitReason.AMBIGUOUS_SAME_BAR
            exit_at = bar.open_time
            break
        if target_hit:
            exit_price, _ = fill_at_level(side, bar, target, favourable=True)
            reason, exit_at = LabExitReason.TARGET, bar.open_time
            break
        if stop_hit:
            exit_price, _ = fill_at_level(side, bar, stop, favourable=False)
            reason, exit_at = LabExitReason.STOP, bar.open_time
            break
    else:
        if window:
            exit_price = window[-1].close
            exit_at = window[-1].open_time
        else:  # pragma: no cover - signal_index+1 < len(bars) guarantees one bar
            return _unentered(LabExitReason.NO_ENTRY_BAR)

    exposed = window[:held] if held else ()
    best, worst = _excursions(exposed, side, entry)

    if reason is LabExitReason.AMBIGUOUS_SAME_BAR or exit_price is None:
        return LabTrade(
            variant_id=variant_id, symbol=symbol, setup_id=setup_id,
            direction=direction, signal_at=signal_at,
            entry_at=entry_bar.open_time, entry_price=entry, initial_stop=stop,
            target=target, planned_reference_price=reference, exit_at=exit_at,
            exit_price=None, exit_reason=LabExitReason.AMBIGUOUS_SAME_BAR,
            bars_held=held, gross_r=None, net_r=None,
            mfe_r=side.sign * (best - entry) / risk,
            mae_r=side.sign * (worst - entry) / risk,
            cost_policy_id=costs.policy_id,
            planned_risk_reward=planned_risk_reward, segment=segment,
            context_regime_structure=context_regime_structure,
            context_structural_trend=context_structural_trend,
            setup_structural_trend=setup_structural_trend,
        )

    gross = side.sign * (exit_price - entry)
    fees = costs.fee_rate * (entry + exit_price)
    return LabTrade(
        variant_id=variant_id, symbol=symbol, setup_id=setup_id,
        direction=direction, signal_at=signal_at,
        entry_at=entry_bar.open_time, entry_price=entry, initial_stop=stop,
        target=target, planned_reference_price=reference, exit_at=exit_at,
        exit_price=exit_price, exit_reason=reason, bars_held=held,
        gross_r=gross / risk, net_r=(gross - fees) / risk,
        mfe_r=side.sign * (best - entry) / risk,
        mae_r=side.sign * (worst - entry) / risk,
        cost_policy_id=costs.policy_id,
        planned_risk_reward=planned_risk_reward, segment=segment,
        context_regime_structure=context_regime_structure,
        context_structural_trend=context_structural_trend,
        setup_structural_trend=setup_structural_trend,
    )


def reprice(trade: LabTrade, costs: PaperCostPolicy) -> LabTrade:
    """The same trade under a different cost policy. **Costs only — never the path.**

    A cost scenario changes what a fill *cost*, not where price went, so the
    entry, the exit, the exit reason, the bar count and both excursions are
    carried across untouched and only the net figure is recomputed. This is what
    makes a two-scenario comparison honest: the frictionless and the costed
    tables describe the identical trades, and any difference between them is
    the cost model and nothing else.

    Re-pricing exists because the replay that produces a trade is expensive and
    the arithmetic that costs it is not. Running the whole study twice to answer
    "does the edge survive fees" would risk the two runs differing for reasons
    that have nothing to do with fees.

    Raises:
        SwingLabError: the trade has no fill to charge a cost against, which
            happens only for records that never entered.
    """
    if not isinstance(trade, LabTrade):
        raise TypeError(f"trade must be a LabTrade, got {type(trade).__name__}")
    if not isinstance(costs, PaperCostPolicy):
        raise TypeError("costs must be a PaperCostPolicy")
    if trade.entry_price is None or trade.exit_price is None or trade.gross_r is None:
        # Unentered and ambiguous trades carry no measurable return under any
        # cost policy. They are returned with the new basis recorded so a
        # scenario's trade list still holds every trade, and the counts of
        # ambiguous and unentered records match between scenarios.
        return LabTrade(
            **{
                **{
                    field: getattr(trade, field)
                    for field in trade.__slots__
                    if field != "cost_policy_id"
                },
                "cost_policy_id": costs.policy_id,
            }
        )
    side = _DIRECTION_TO_TRADE[trade.direction]
    risk = side.sign * (trade.entry_price - trade.initial_stop)
    if risk <= 0:
        return LabTrade(
            **{
                **{
                    field: getattr(trade, field)
                    for field in trade.__slots__
                    if field != "cost_policy_id"
                },
                "cost_policy_id": costs.policy_id,
            }
        )
    fees = costs.fee_rate * (trade.entry_price + trade.exit_price)
    gross = side.sign * (trade.exit_price - trade.entry_price)
    return LabTrade(
        **{
            **{
                field: getattr(trade, field)
                for field in trade.__slots__
                if field not in ("cost_policy_id", "net_r")
            },
            "cost_policy_id": costs.policy_id,
            "net_r": (gross - fees) / risk,
        }
    )
