"""Lines in, one portfolio out. The arithmetic, and nothing else.

`build_state` is a **pure function**: same lines, same marks, same equity, same
answer, forever. It opens nothing, reaches nothing and reads no clock — every
instant and every price arrives as an argument, which is what makes a portfolio
reproducible and a test of one non-flaky.

**Gross and net are computed separately and are never derived from each other.**
Gross is the sum of magnitudes and net is the sum of signed values; a portfolio
that is long 10 and short 10 has a gross of 20 and a net of 0, and a reader shown
only one of them is reading a different portfolio from the one that exists. Long
and short exposure are computed the same way, each from its own filtered set,
because a subtraction that recovered one from the other two would go wrong
silently the first time a figure it depended on was `Absent`.

**One missing input never shrinks a total.** Every aggregate is `Absent(reason)`
if any contributor is, and the reason names the positions that broke it —
`sum_or_absent` is the single place that rule is implemented, so it cannot be
half-applied.

**`deployed_capital` refuses to answer for a leveraged or short book, and says
why.** What capital is committed to a short or to a margin position is *margin*,
which this domain records nowhere. Reporting cost basis under the name "deployed
capital" would understate what a leveraged account has at stake, and that is the
direction of error a risk engine must never make.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from fmis.accounts import Book, MarketMode
from fmis.money import AssetCode, Money
from fmis.positions import PositionDirection
from fmis.provenance import Absent
from fmis.records import require_member, require_utc

from fmis.portfolio_risk.classification import ClassificationMap
from fmis.portfolio_risk.models import (
    UNCLASSIFIED,
    ExposureBreakdown,
    ExposureDimension,
    ExposureEntry,
    ExposureLine,
    PendingCommitment,
    PortfolioState,
    sum_or_absent,
)

__all__ = [
    "DEFAULT_BOOKS_COVERED",
    "SPOT_ONLY_MODES",
    "build_state",
    "breakdown_by",
    "breakdown_by_group",
    "markets_held_in_several_accounts",
]

#: What a portfolio covers unless the caller narrows it: every book that holds
#: real capital, in the reporting order the accounts package already defines, with
#: `PAPER` excluded. Neither the order nor the exclusion is invented here —
#: `BOOK_ORDER` and `DEFAULT_EXCLUDED_BOOKS` are `fmis.accounts`' own, and the
#: reason for the exclusion is its own too: paper and live contamination is
#: detectable only if every aggregate states which books it covers.
DEFAULT_BOOKS_COVERED: tuple[Book, ...] = (Book.INVESTING, Book.SWING, Book.DAY)

#: The modes whose committed capital is the cost basis. Everything else is
#: margined, and how much margin is posted is a venue fact this domain holds no
#: field for.
SPOT_ONLY_MODES: frozenset[MarketMode] = frozenset({MarketMode.SPOT})


def markets_held_in_several_accounts(
    lines: Iterable[ExposureLine],
) -> tuple[str, ...]:
    """Markets whose exposure sits in more than one account, in one book.

    Where a per-account fold and a book-wide fold legitimately disagree. Named on
    the state so the disagreement is a documented property rather than a bug
    report waiting to be filed.
    """
    seen: dict[tuple[str, str], set[str]] = {}
    for line in lines:
        seen.setdefault(
            (line.market.value, line.book.value), set()
        ).add(line.account.value)
    return tuple(
        sorted(
            f"{market} ({book})"
            for (market, book), accounts in seen.items()
            if len(accounts) > 1
        )
    )


def _entry_for(
    key: str, lines: Sequence[ExposureLine], base: AssetCode
) -> ExposureEntry:
    return ExposureEntry(
        key=key,
        gross=sum_or_absent(
            (line.notional(base) for line in lines),
            asset=base,
            subject=f"gross exposure in {key!r}",
        ),
        net=sum_or_absent(
            (line.signed_notional(base) for line in lines),
            asset=base,
            subject=f"net exposure in {key!r}",
        ),
        open_risk=sum_or_absent(
            (line.capital_at_risk(base) for line in lines),
            asset=base,
            subject=f"open risk in {key!r}",
        ),
        line_count=len(lines),
    )


def _totals(
    lines: Sequence[ExposureLine], base: AssetCode
) -> tuple[Money | Absent, Money | Absent]:
    gross = sum_or_absent(
        (line.notional(base) for line in lines),
        asset=base,
        subject="gross exposure",
    )
    risk = sum_or_absent(
        (line.capital_at_risk(base) for line in lines),
        asset=base,
        subject="open risk",
    )
    return gross, risk


def breakdown_by(
    dimension: ExposureDimension,
    lines: Sequence[ExposureLine],
    *,
    base: AssetCode,
) -> ExposureBreakdown:
    """Group lines on one axis. Buckets are disjoint and every line falls in one.

    `GROUP` is refused here and has its own function, because a line belongs to
    as many groups as the owner's map names and this function's whole contract is
    that the buckets partition the portfolio.
    """
    require_member(dimension, ExposureDimension, "dimension")
    if dimension is ExposureDimension.GROUP:
        raise ValueError(
            "group exposure overlaps and needs the owner's classification map; "
            "use breakdown_by_group"
        )
    buckets: dict[str, list[ExposureLine]] = {}
    for line in lines:
        buckets.setdefault(line.key_on(dimension), []).append(line)
    gross, risk = _totals(lines, base)
    return ExposureBreakdown(
        dimension=dimension,
        entries=tuple(
            _entry_for(key, buckets[key], base) for key in sorted(buckets)
        ),
        total_gross=gross,
        total_open_risk=risk,
    )


def breakdown_by_group(
    lines: Sequence[ExposureLine],
    *,
    base: AssetCode,
    classification: ClassificationMap,
) -> ExposureBreakdown:
    """Group exposure under the owner's own classification, at its stated version.

    **The buckets deliberately overlap.** An asset in three groups contributes its
    whole exposure to all three, so the entries sum to more than the portfolio's
    gross — `overlapping_keys` names every asset responsible, and the totals on
    the breakdown remain the portfolio's real ones so a share is still a share of
    the portfolio rather than of an inflated denominator.
    """
    if not isinstance(classification, ClassificationMap):
        raise TypeError("classification must be a ClassificationMap")
    buckets: dict[str, list[ExposureLine]] = {}
    for line in lines:
        groups = classification.groups_for(line.market.base_asset)
        keys = (UNCLASSIFIED,) if isinstance(groups, Absent) else groups
        for key in keys:
            buckets.setdefault(key, []).append(line)
    gross, risk = _totals(lines, base)
    return ExposureBreakdown(
        dimension=ExposureDimension.GROUP,
        entries=tuple(
            _entry_for(key, buckets[key], base) for key in sorted(buckets)
        ),
        total_gross=gross,
        total_open_risk=risk,
        overlapping_keys=classification.multi_group_assets(
            line.market.base_asset for line in lines
        ),
        classification_version=classification.version,
    )


def _directional(
    lines: Sequence[ExposureLine], direction: PositionDirection, base: AssetCode
) -> Money | Absent:
    """One side's exposure, summed from its own lines and never by subtraction."""
    selected = [line for line in lines if line.direction is direction]
    return sum_or_absent(
        (line.notional(base) for line in selected),
        asset=base,
        subject=f"{direction.value} exposure",
    )


def _deployed(lines: Sequence[ExposureLine], base: AssetCode) -> Money | Absent:
    """Cost basis of open exposure, or the reason capital committed is unknowable.

    Only answerable for unleveraged long exposure. A short's committed capital is
    margin, a perpetual's is margin, and neither is a field on any record in this
    domain — so the figure is refused with the blocker named rather than
    approximated by a cost basis that would understate what is at stake.
    """
    found: set[str] = set()
    for line in lines:
        if line.mode not in SPOT_ONLY_MODES:
            found.add(
                f"{line.market.value} is a {line.mode.value} market and is margined"
            )
        elif line.direction is PositionDirection.SHORT:
            found.add(
                f"{line.market.value} is held short, and a short's committed "
                "capital is margin rather than cost"
            )
    blockers = sorted(found)
    if blockers:
        return Absent(
            "capital deployed cannot be stated: "
            + "; ".join(blockers)
            + ". Margin posted is a venue fact this domain records nowhere"
        )
    return sum_or_absent(
        (line.cost_basis(base) for line in lines),
        asset=base,
        subject="capital deployed",
    )


def _reserved(
    pending: Sequence[PendingCommitment], base: AssetCode
) -> Money | Absent:
    """What pending commitments hold back — zero only when there are none.

    A `TradePlan` states a stop and targets and **no intended size**, so the
    capital a pending commitment would consume is not derivable from anything
    stored. Zero when nothing is pending is a fact; zero when four plans are open
    would be a fabrication, so that case is `Absent` with the missing field named.
    """
    if not pending:
        return Money.zero(base)
    return Absent(
        f"{len(pending)} commitment(s) are pending and a TradePlan states no "
        "intended size, so the capital they would consume is not derivable from "
        "anything recorded. Naming a size is the proposed-trade input's job"
    )


def build_state(
    *,
    portfolio_id: str,
    base_currency: AssetCode,
    as_of: datetime,
    lines: Sequence[ExposureLine],
    pending: Sequence[PendingCommitment] = (),
    equity: Money | Absent,
    cash: Money | Absent,
    classification: ClassificationMap,
    books_covered: tuple[Book, ...] = DEFAULT_BOOKS_COVERED,
    equity_as_of: datetime | Absent | None = None,
) -> PortfolioState:
    """Every figure a portfolio has, from the lines it is made of.

    `equity` and `cash` are **arguments, not derivations**. This package reaches
    no venue and holds no balance: equity comes from a `PortfolioSnapshot` the
    owner took or from nothing at all, and `Absent(reason)` is the correct answer
    in the second case rather than the sum of what happens to be recorded.
    """
    ordered = tuple(lines)
    for line in ordered:
        if not isinstance(line, ExposureLine):
            raise TypeError("lines must be ExposureLine values")
    asset = (
        base_currency
        if isinstance(base_currency, AssetCode)
        else AssetCode(base_currency)
    )
    moment = require_utc(as_of, "as_of")
    gross, risk = _totals(ordered, asset)
    return PortfolioState(
        portfolio_id=portfolio_id,
        base_currency=asset,
        as_of=moment,
        books_covered=books_covered,
        lines=ordered,
        pending=tuple(pending),
        breakdowns=(
            breakdown_by(ExposureDimension.ACCOUNT, ordered, base=asset),
            breakdown_by(ExposureDimension.VENUE, ordered, base=asset),
            breakdown_by(ExposureDimension.BOOK, ordered, base=asset),
            breakdown_by(ExposureDimension.INSTRUMENT, ordered, base=asset),
            breakdown_by(ExposureDimension.SYMBOL, ordered, base=asset),
            breakdown_by(ExposureDimension.ASSET, ordered, base=asset),
            breakdown_by(ExposureDimension.DIRECTION, ordered, base=asset),
            breakdown_by_group(ordered, base=asset, classification=classification),
        ),
        equity=equity,
        cash=cash,
        equity_as_of=(
            Absent("the caller stated no instant for the equity figure")
            if equity_as_of is None
            else equity_as_of
        ),
        gross_exposure=gross,
        net_exposure=sum_or_absent(
            (line.signed_notional(asset) for line in ordered),
            asset=asset,
            subject="net exposure",
        ),
        long_exposure=_directional(ordered, PositionDirection.LONG, asset),
        short_exposure=_directional(ordered, PositionDirection.SHORT, asset),
        open_risk=risk,
        deployed_capital=_deployed(ordered, asset),
        reserved_capital=_reserved(tuple(pending), asset),
        accounts_share_a_market=markets_held_in_several_accounts(ordered),
    )
