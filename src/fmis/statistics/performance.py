"""Did the money go up, and is the reason it went up a property or an accident.

The four families the milestone brief names split cleanly on one line, and this
module is the far side of it: **everything here is a claim about a process**, so
everything here consults the sample floor. Gross and net totals are the
exception and are stated as such — a sum of what happened is not an inference
about what will happen.

**Money and R are two currencies of result and are never mixed.** Profit factor,
gross profit, average win and largest loss are money, denominated in one quote
asset and refusing to cross into a second. Average R, expectancy in R and best R
are ratios against each trade's own initial risk, and are comparable across
markets *because* they are not money. A page that added them would be adding a
figure about position size to a figure about trade selection.

**Expectancy is stated twice on purpose.** In money it answers *"what did the
average trade do to my account"*, which depends on how large the trades were.
In R it answers *"what did the average trade do relative to what it risked"*,
which is the question about the strategy. `SPEC` §18 names expectancy without
saying which, and building only one would answer the wrong half.

**Profit factor's denominator is the magnitude of the losses.** Gross loss is
carried here as a **positive** amount for exactly that reason: a signed gross
loss would make profit factor negative, which is not a scale anybody reads
correctly, and the sign carries no information a label does not.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fmis.money import AssetCode, Money, canonical_decimal_text
from fmis.provenance import Absent
from fmis.statistics.models import SamplePolicy, TradeResult, TradeStat
from fmis.statistics.sampling import (
    Sample,
    Tally,
    collect_values,
    count_of,
    extremum_or_absent,
    mean_or_absent,
    median_or_absent,
    ratio_or_absent,
    total_or_absent,
)

__all__ = [
    "PerformanceStatistics",
    "performance_statistics",
    "EXPECTANCY_BASIS",
    "PROFIT_FACTOR_BASIS",
]

#: Printed beside expectancy on every page that shows it. The definition is
#: arguable and the arguable part is which population it averages over, so the
#: population is named rather than assumed.
EXPECTANCY_BASIS = (
    "The mean result of every trade whose result is stateable — winners, losers "
    "and scratches alike. Trades still running and trades whose profit and loss "
    "cannot be stated are excluded and counted separately."
)

#: Printed beside profit factor. The zero-loss case is where this figure most
#: often becomes nonsense on other systems.
PROFIT_FACTOR_BASIS = (
    "Gross profit divided by the magnitude of gross loss. A corpus with no "
    "losing trade has no profit factor — it is undefined, not infinite, and not "
    "a large number."
)


@dataclass(frozen=True, slots=True)
class PerformanceStatistics:
    """Every performance figure the milestone brief names, in one reading."""

    quote_asset: AssetCode
    resolved: Sample
    winners: Tally
    losers: Tally
    gross_profit: Money | Absent
    gross_loss: Money | Absent
    net_profit: Money | Absent
    average_win: Money | Absent
    average_loss: Money | Absent
    largest_win: Money | Absent
    largest_loss: Money | Absent
    profit_factor: Decimal | Absent
    payoff_ratio: Decimal | Absent
    expectancy: Money | Absent
    win_rate: Decimal | Absent
    loss_rate: Decimal | Absent
    r_sample: Sample
    average_r: Decimal | Absent
    median_r: Decimal | Absent
    best_r: Decimal | Absent
    worst_r: Decimal | Absent
    expectancy_r: Decimal | Absent
    expectancy_basis: str = EXPECTANCY_BASIS
    profit_factor_basis: str = PROFIT_FACTOR_BASIS

    def to_payload(self) -> dict[str, Any]:
        return {
            "quote_asset": self.quote_asset.code,
            "resolved": self.resolved.to_payload(),
            "winners": self.winners.to_payload(),
            "losers": self.losers.to_payload(),
            "gross_profit": _money(self.gross_profit),
            "gross_loss": _money(self.gross_loss),
            "net_profit": _money(self.net_profit),
            "average_win": _money(self.average_win),
            "average_loss": _money(self.average_loss),
            "largest_win": _money(self.largest_win),
            "largest_loss": _money(self.largest_loss),
            "profit_factor": _number(self.profit_factor),
            "payoff_ratio": _number(self.payoff_ratio),
            "expectancy": _money(self.expectancy),
            "win_rate": _number(self.win_rate),
            "loss_rate": _number(self.loss_rate),
            "r_sample": self.r_sample.to_payload(),
            "average_r": _number(self.average_r),
            "median_r": _number(self.median_r),
            "best_r": _number(self.best_r),
            "worst_r": _number(self.worst_r),
            "expectancy_r": _number(self.expectancy_r),
        }


def performance_statistics(
    trades: tuple[TradeStat, ...],
    policy: SamplePolicy,
    *,
    quote_asset: AssetCode,
) -> PerformanceStatistics:
    """Fold one quote asset's trades into every performance figure.

    `quote_asset` is required rather than inferred. A corpus settled in two
    assets has two answers and no combined one, and picking the commonest would
    silently drop a market — the caller splits the corpus and names the asset,
    and `report` is the one place that split happens.
    """
    _require_trades(trades)
    if not isinstance(policy, SamplePolicy):
        raise TypeError("policy must be a SamplePolicy")
    if not isinstance(quote_asset, AssetCode):
        raise TypeError("quote_asset must be an AssetCode")
    _require_one_asset(trades, quote_asset)

    resolved = tuple(stat for stat in trades if stat.result is not TradeResult.UNRESOLVED)
    outcomes = collect_values(
        resolved, lambda stat: stat.realized_pnl_net, "realized profit and loss"
    )
    wins = tuple(stat for stat in resolved if stat.result is TradeResult.WIN)
    losses = tuple(stat for stat in resolved if stat.result is TradeResult.LOSS)

    gross_profit = total_or_absent(
        tuple(stat.realized_pnl_net for stat in wins),
        asset=quote_asset,
        subject="gross profit",
    )
    signed_gross_loss = total_or_absent(
        tuple(stat.realized_pnl_net for stat in losses),
        asset=quote_asset,
        subject="gross loss",
    )
    gross_loss = (
        signed_gross_loss if isinstance(signed_gross_loss, Absent) else abs(signed_gross_loss)
    )
    net_profit = total_or_absent(
        tuple(stat.realized_pnl_net for stat in resolved),
        asset=quote_asset,
        subject="net profit",
    )

    win_amounts = collect_values(
        wins, lambda stat: stat.realized_pnl_net, "a winner's profit"
    )
    loss_amounts = collect_values(
        losses, lambda stat: stat.realized_pnl_net, "a loser's loss"
    )
    r_sample = collect_values(trades, lambda stat: stat.r_multiple, "R multiple")

    average_win = _mean_money(win_amounts, quote_asset)
    average_loss = _mean_money(loss_amounts, quote_asset)
    expectancy = _mean_money(outcomes, quote_asset)

    winners = count_of(resolved, lambda stat: stat.result is TradeResult.WIN, "win rate")
    losers = count_of(resolved, lambda stat: stat.result is TradeResult.LOSS, "loss rate")

    return PerformanceStatistics(
        quote_asset=quote_asset,
        resolved=outcomes,
        winners=winners,
        losers=losers,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_profit=net_profit,
        average_win=average_win,
        average_loss=average_loss,
        largest_win=extremum_or_absent(win_amounts, policy, largest=True),
        largest_loss=extremum_or_absent(loss_amounts, policy, largest=False),
        profit_factor=_profit_factor(gross_profit, gross_loss, outcomes.size, policy),
        payoff_ratio=_payoff_ratio(average_win, average_loss, outcomes.size, policy),
        expectancy=expectancy,
        win_rate=winners.share(policy),
        loss_rate=losers.share(policy),
        r_sample=r_sample,
        average_r=mean_or_absent(r_sample, policy),
        median_r=median_or_absent(r_sample, policy),
        best_r=extremum_or_absent(r_sample, policy, largest=True),
        worst_r=extremum_or_absent(r_sample, policy, largest=False),
        expectancy_r=mean_or_absent(r_sample, policy),
    )


def _require_trades(trades: Any) -> None:
    if not isinstance(trades, tuple):
        raise TypeError("trades must be a tuple of TradeStat")
    for stat in trades:
        if not isinstance(stat, TradeStat):
            raise TypeError("every trade must be a TradeStat")


def _require_one_asset(trades: tuple[TradeStat, ...], quote_asset: AssetCode) -> None:
    """A corpus handed to this function settles in exactly one asset.

    Checked rather than assumed: `Money` would raise on the first addition
    anyway, but the message it raises is about two amounts, and the caller's
    actual mistake is that they did not split the corpus.
    """
    foreign = sorted(
        {stat.quote_asset.code for stat in trades if stat.quote_asset != quote_asset}
    )
    if foreign:
        raise TypeError(
            f"this corpus settles in {quote_asset.code} and also in "
            f"{', '.join(foreign)}; split it by quote asset first, because no rate "
            "in this system crosses them"
        )


def _mean_money(sample: Sample, asset: AssetCode) -> Money | Absent:
    """The mean of a money sample, kept in money rather than dropped to a number.

    Not floored, for the same reason `mean_or_absent` is not: an average of the
    amounts in hand is a description of them. Its `n` travels on `sample`.
    """
    if not sample.values:
        note = sample.coverage_note
        detail = "" if isinstance(note, Absent) else f" ({note})"
        return Absent(
            f"no trade in this population has a stateable {sample.subject}{detail}",
            sample_size=0,
        )
    total = Money.zero(asset)
    for value in sample.values:
        total = total + value
    return Money(total.amount / Decimal(sample.size), asset)


def _profit_factor(
    gross_profit: Money | Absent,
    gross_loss: Money | Absent,
    sample_size: int,
    policy: SamplePolicy,
) -> Decimal | Absent:
    if isinstance(gross_profit, Absent):
        return gross_profit
    if isinstance(gross_loss, Absent):
        return gross_loss
    return ratio_or_absent(
        gross_profit.amount, gross_loss.amount, "profit factor", sample_size, policy
    )


def _payoff_ratio(
    average_win: Money | Absent,
    average_loss: Money | Absent,
    sample_size: int,
    policy: SamplePolicy,
) -> Decimal | Absent:
    """Average win over the magnitude of the average loss.

    The companion to win rate: a system winning three times in ten is
    profitable if this figure is above roughly three, and neither number means
    anything without the other. Both are floored together for that reason.
    """
    if isinstance(average_win, Absent):
        return average_win
    if isinstance(average_loss, Absent):
        return average_loss
    return ratio_or_absent(
        average_win.amount,
        abs(average_loss.amount),
        "payoff ratio",
        sample_size,
        policy,
    )


def _money(value: Money | Absent) -> dict[str, Any] | None:
    return None if isinstance(value, Absent) else value.to_payload()


def _number(value: Decimal | Absent) -> str | None:
    return None if isinstance(value, Absent) else canonical_decimal_text(value)
