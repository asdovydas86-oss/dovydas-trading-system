"""How much was put at risk, on what, and against what capacity.

Risk here is **capital at risk at the moment of commitment** — the distance from
the entry to the stop, multiplied by the size taken. `fmis.portfolio_risk` owns
that arithmetic and this module never repeats it: the figure arrives already
computed on each `TradeStat`, and everything below is a reduction over it.

**Open risk and closed risk are two populations, not one figure filtered.** Open
risk is what is exposed right now and can still be lost; closed risk is what was
exposed on trades that have ended and is a fact about sizing discipline rather
than about exposure. Reporting one number for both would let a quiet week look
like restraint.

**Risk utilization measures against the owner's own ceiling and evaluates no
constraint.** The limit is read — the single `TOTAL_OPEN_RISK` number the owner
configured — and this corpus's open risk is divided into it. It is deliberately
**not** the portfolio-wide constraint answer: that covers every position,
including ones no plan records, and `fmis.portfolio_risk` owns it. Two figures
that measure different populations must not share a name, so this one says which
population it covers wherever it appears. With no budget recorded there is no
utilization, and the absence names the missing budget rather than reporting
zero, which would read as *"you have used none of your allowance"* to an owner
who has set no allowance at all.

**A risk percentage needs an equity, and this system records none per trade.**
`AP` writes no snapshot at commitment time, so the honest form is one basis
supplied for the whole corpus, stated on the page, and `Absent` when none is
given. `ST-6` carries that caveat to every surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fmis.money import AssetCode, Money, canonical_decimal_text
from fmis.provenance import Absent
from fmis.statistics.models import SamplePolicy, TradeStat
from fmis.statistics.sampling import (
    Sample,
    collect_values,
    extremum_or_absent,
    mean_or_absent,
    median_or_absent,
)

__all__ = [
    "RiskStatistics",
    "risk_statistics",
    "utilization_of",
    "RISK_UTILIZATION_BASIS",
]

#: Printed beside risk utilization, so a reader cannot mistake a limit the owner
#: configured for a judgement this system formed — and cannot mistake this
#: figure for the portfolio-wide one, which is a different population.
RISK_UTILIZATION_BASIS = (
    "The open capital at risk of the trades on this page, as a share of the "
    "owner's own recorded total-open-risk ceiling. It covers the trades this "
    "corpus holds, not every position in the portfolio; `fmits approve` "
    "evaluates the portfolio-wide constraint. The ceiling is a limit the owner "
    "set — this system invents none and forms no opinion about whether it is "
    "right."
)


@dataclass(frozen=True, slots=True)
class RiskStatistics:
    """What was risked, on the open book and on the closed one."""

    quote_asset: AssetCode
    open_risk: Sample
    closed_risk: Sample
    largest_open_risk: Money | Absent
    largest_closed_risk: Money | Absent
    average_open_risk: Money | Absent
    average_closed_risk: Money | Absent
    total_open_risk: Money | Absent
    risk_utilization: Decimal | Absent
    risk_fraction: Sample
    average_risk_fraction: Decimal | Absent
    median_risk_fraction: Decimal | Absent
    equity_basis: Money | Absent
    utilization_basis: str = RISK_UTILIZATION_BASIS

    def to_payload(self) -> dict[str, Any]:
        return {
            "quote_asset": self.quote_asset.code,
            "open_risk": self.open_risk.to_payload(),
            "closed_risk": self.closed_risk.to_payload(),
            "largest_open_risk": _money(self.largest_open_risk),
            "largest_closed_risk": _money(self.largest_closed_risk),
            "average_open_risk": _money(self.average_open_risk),
            "average_closed_risk": _money(self.average_closed_risk),
            "total_open_risk": _money(self.total_open_risk),
            "risk_utilization": _number(self.risk_utilization),
            "risk_fraction": self.risk_fraction.to_payload(),
            "average_risk_fraction": _number(self.average_risk_fraction),
            "median_risk_fraction": _number(self.median_risk_fraction),
            "equity_basis": _money(self.equity_basis),
        }


def risk_statistics(
    trades: tuple[TradeStat, ...],
    policy: SamplePolicy,
    *,
    quote_asset: AssetCode,
    equity_basis: Money | Absent,
    utilization: Decimal | Absent,
) -> RiskStatistics:
    """Reduce one quote asset's risk figures.

    `utilization` arrives already divided, from `utilization_of` over a ceiling
    the store holds. It is passed in rather than read here so that this function
    stays a pure fold with no store handle — the same separation `collect` draws
    for every other figure on the page.
    """
    if not isinstance(trades, tuple):
        raise TypeError("trades must be a tuple of TradeStat")
    for stat in trades:
        if not isinstance(stat, TradeStat):
            raise TypeError("every trade must be a TradeStat")
    if not isinstance(policy, SamplePolicy):
        raise TypeError("policy must be a SamplePolicy")
    if not isinstance(quote_asset, AssetCode):
        raise TypeError("quote_asset must be an AssetCode")
    if not isinstance(equity_basis, (Money, Absent)):
        raise TypeError("equity_basis must be a Money or Absent")
    if not isinstance(utilization, (Decimal, Absent)):
        raise TypeError("utilization must be a Decimal or Absent")

    exposed = tuple(stat for stat in trades if stat.is_open)
    ended = tuple(stat for stat in trades if stat.is_closed)
    open_risk = collect_values(
        exposed, lambda stat: stat.initial_risk, "open capital at risk"
    )
    closed_risk = collect_values(
        ended, lambda stat: stat.initial_risk, "closed capital at risk"
    )
    fractions = collect_values(
        trades,
        lambda stat: stat.risk_fraction_of(equity_basis),
        "risk as a fraction of equity",
    )

    return RiskStatistics(
        quote_asset=quote_asset,
        open_risk=open_risk,
        closed_risk=closed_risk,
        largest_open_risk=extremum_or_absent(open_risk, policy, largest=True),
        largest_closed_risk=extremum_or_absent(closed_risk, policy, largest=True),
        average_open_risk=_mean_money(open_risk, quote_asset),
        average_closed_risk=_mean_money(closed_risk, quote_asset),
        total_open_risk=_total_money(open_risk, quote_asset),
        risk_utilization=utilization,
        risk_fraction=fractions,
        average_risk_fraction=mean_or_absent(fractions, policy),
        median_risk_fraction=median_or_absent(fractions, policy),
        equity_basis=equity_basis,
    )


def utilization_of(open_risk: Money | Absent, ceiling: Money | Absent) -> Decimal | Absent:
    """Open risk over the owner's ceiling. One division, and four refusals.

    A ceiling of zero is undefined rather than fully consumed; two assets do not
    cross; and either half being absent carries **that** half's reason forward,
    so a page says *"no risk budget has been recorded"* rather than the generic
    *"no utilization"*. Which of the two is missing is the actionable part.
    """
    if isinstance(open_risk, Absent):
        return Absent(
            f"the open risk on this page cannot be totalled, so no share of a "
            f"ceiling can be stated: {open_risk.reason}"
        )
    if isinstance(ceiling, Absent):
        return Absent(
            f"no total-open-risk ceiling is available to measure against: "
            f"{ceiling.reason}"
        )
    for name, value in (("open_risk", open_risk), ("ceiling", ceiling)):
        if not isinstance(value, Money):
            raise TypeError(f"{name} must be a Money or Absent")
    if ceiling.asset != open_risk.asset:
        return Absent(
            f"the ceiling is in {ceiling.asset.code} and the open risk in "
            f"{open_risk.asset.code}; no rate in this system crosses them"
        )
    if ceiling.amount == 0:
        return Absent(
            "the recorded ceiling is zero, so the share of it consumed is "
            "undefined rather than complete"
        )
    return open_risk.amount / ceiling.amount


def _total_money(sample: Sample, asset: AssetCode) -> Money | Absent:
    """A total that refuses to omit a contributor.

    Not `total_or_absent`: that one takes the raw `Money | Absent` values, and
    by this point the absences have already been separated onto the sample. The
    refusal is the same one — a total is `Absent` the moment a member of its
    population could not be stated.
    """
    if sample.is_partial:
        note = sample.coverage_note
        return Absent(
            f"{sample.subject} cannot be totalled: "
            + ("" if isinstance(note, Absent) else note)
        )
    total = Money.zero(asset)
    for value in sample.values:
        total = total + value
    return total


def _mean_money(sample: Sample, asset: AssetCode) -> Money | Absent:
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


def _money(value: Money | Absent) -> dict[str, Any] | None:
    return None if isinstance(value, Absent) else value.to_payload()


def _number(value: Decimal | Absent) -> str | None:
    return None if isinstance(value, Absent) else canonical_decimal_text(value)
