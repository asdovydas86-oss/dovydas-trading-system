"""Reading a recorded swing trade back out of the store.

**Nothing here writes.** A guard test asserts this module names no write verb on
any repository, because the read path is where a "convenience" write would be
least visible and most damaging: a `trade show` that repaired something would
make the store's contents depend on who looked at them.

**The fills are read through the resolver, never raw.** `LedgerRepository`
returns `ResolvedTrade`, a token this layer cannot construct, and every figure
below folds those. That is `AP` §5.1's rule — *"reading ledger files directly is
a test-enforced violation. Without this, one consumer eventually reports a
superseded value and nothing detects it"* — and this package is the first
consumer it has ever had.

**A plan's fold is over that plan's fills only, and the page says so.** The
position fold groups by `(market, book)`; two plans in one market and one book
fold into one position, so the figures here would silently include a second
trade's fills if this filtered on anything coarser than `plan_id`. Restricting
the input is what makes *"how did this trade do"* answerable at all — and it
means the number differs from the book-wide position, which is a warning on
every view rather than a footnote.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Any

from fmis.journal import TradeJournal
from fmis.ledger import ResolvedTrade
from fmis.money import DustPolicy, Money
from fmis.persistence import TradingStore
from fmis.plan import PlanPlacementError, TradePlan, capital_at_risk, planned_risk_reward
from fmis.positions import Position, PositionState, fold_positions
from fmis.provenance import Absent
from fmis.records import require_text, require_utc
from fmis.snapshotting import RiskRewardReading
from fmis.trade_capture.models import (
    CaptureStatus,
    CaptureWarning,
    FillLine,
    TradeFilters,
    TradeListing,
    TradeNotFoundError,
    TradeRow,
    TradeView,
)

__all__ = [
    "PLAN_SUBJECT_KIND",
    "TRADE_SUBJECT_KIND",
    "CAPTURE_LIMITATIONS",
    "fills_for_plan",
    "load_plan",
    "load_trade",
    "list_trades",
]

#: The `JournalLink.target_kind` every entry about a commitment carries. Equal to
#: the persisted record kind on purpose: a link whose target kind did not name a
#: real kind would be a foreign key into nothing.
PLAN_SUBJECT_KIND = "trade_plan"

#: The target kind for an entry about one specific fill rather than the whole
#: commitment. Both exist because *"I closed early"* is about the trade and
#: *"the thesis was wrong"* is about the plan, and one untyped edge would collapse
#: the two answerable questions into one that is not.
TRADE_SUBJECT_KIND = "trade"

#: Printed at the foot of every capture surface, unchanged. The invariant
#: register: these qualify the whole page and belong once, at the bottom, rather
#: than beside a number where repetition teaches a reader to skip them.
CAPTURE_LIMITATIONS: tuple[tuple[str, str], ...] = (
    (
        "TC-1",
        "FMITS records what the owner did. It places no order, reaches no "
        "exchange, and confirms nothing against a venue. A fill recorded here "
        "and a fill that happened are two facts, and only the first is visible.",
    ),
    (
        "TC-2",
        "Capital at risk is |entry − stop| × quantity and assumes the stop is "
        "honoured at that price. A gap through the stop loses more, and no data "
        "this system ingests bounds by how much.",
    ),
    (
        "TC-3",
        "Realized profit and loss is the position fold's figure for review. It "
        "is not a taxable gain and no surface may present one as the other.",
    ),
    (
        "TC-4",
        "The figures on this page fold this commitment's own fills. The "
        "book-wide position in the same market may differ, and neither is wrong.",
    ),
    (
        "TC-5",
        "No position size is computed and no probability is calibrated. The "
        "size recorded here is the one the owner stated they filled.",
    ),
)


def _require_store(store: Any) -> TradingStore:
    if not isinstance(store, TradingStore):
        raise TypeError(f"store must be a TradingStore, got {type(store).__name__}")
    return store


def _require_dust(dust: Any) -> DustPolicy:
    if not isinstance(dust, DustPolicy):
        raise TypeError(
            "a position fold needs a DustPolicy: what counts as flat is the "
            "owner's threshold, and this layer invents none"
        )
    return dust


def load_plan(store: TradingStore, plan_id: str) -> TradePlan:
    """The commitment named, or a refusal that says it is not here.

    `TradeNotFoundError` rather than the store's own `RecordMissingError`,
    because at this layer *"you mistyped an id"* and *"the store is missing a
    record it should hold"* are different problems with different remedies.
    """
    _require_store(store)
    wanted = require_text(plan_id, "plan_id")
    if not store.plans.exists(wanted):
        raise TradeNotFoundError(
            f"no recorded trade {wanted!r} is in this store. `fmits trade list` "
            "shows every commitment it holds"
        )
    return store.plans.load(wanted)


def fills_for_plan(
    resolved: Iterable[ResolvedTrade], plan_id: str
) -> tuple[ResolvedTrade, ...]:
    """The live fills carrying one `plan_id`, oldest first.

    Takes an already-resolved stream rather than a store, so a listing over forty
    commitments resolves the ledger once instead of forty times — and so the
    filter is a pure function a test can exercise without a filesystem.
    """
    wanted = require_text(plan_id, "plan_id")
    return tuple(
        entry
        for entry in resolved
        if not isinstance(entry.trade.plan_id, Absent)
        and entry.trade.plan_id == wanted
    )


def _fill_lines(resolved: tuple[ResolvedTrade, ...]) -> tuple[FillLine, ...]:
    return tuple(
        FillLine(
            event_id=entry.event_id,
            occurred_at=entry.trade.occurred_at,
            side=entry.trade.side,
            quantity=entry.trade.quantity,
            price=entry.trade.price,
            fee=entry.trade.fee,
            account=entry.trade.account.value,
            was_corrected=entry.was_corrected,
        )
        for entry in resolved
    )


def _positions_of(
    resolved: tuple[ResolvedTrade, ...], *, dust: DustPolicy
) -> tuple[Position, ...]:
    return fold_positions(resolved, dust=dust)


def _entry_price(position: Position | Absent) -> Decimal | Absent:
    """The average entry, divided at read time.

    `AverageCost.per_unit` is the domain's own division and is reused rather than
    recomputed — a second definition of "the average entry" is the one figure
    nobody could reconcile against the pair it came from.
    """
    if isinstance(position, Absent):
        return Absent("nothing has filled against this commitment")
    return position.average_entry.per_unit


def _risk_figures(
    plan: TradePlan, position: Position | Absent, entry: Decimal | Absent
) -> tuple[Money | Absent, RiskRewardReading | Absent, tuple[CaptureWarning, ...]]:
    """Capital at risk and the planned risk/reward, or the reasons neither exists.

    Both are refused rather than approximated when the average entry has drifted
    to the stop's side — which happens for real, by adding to a position after
    price has passed the level the plan named. Reporting a negative risk distance
    as a positive number would make the worst-managed trades look like the
    best-sized ones.
    """
    if isinstance(position, Absent) or isinstance(entry, Absent):
        reason = Absent("no fill has established an average entry")
        return reason, reason, ()
    try:
        risk = capital_at_risk(
            plan, entry_price=entry, quantity=position.max_exposure
        )
        reward = planned_risk_reward(plan, entry)
    except PlanPlacementError as error:
        absent = Absent(str(error))
        return (
            absent,
            absent,
            (
                CaptureWarning(
                    "TC-W1",
                    "The average entry has moved to the stop's side of the trade, "
                    "so no risk distance exists and no capital-at-risk figure is "
                    f"produced: {error}",
                ),
            ),
        )
    return risk, reward, ()


def _status_of(position: Position | Absent) -> CaptureStatus:
    if isinstance(position, Absent):
        return CaptureStatus.PLANNED
    return (
        CaptureStatus.OPEN
        if position.state is PositionState.OPEN
        else CaptureStatus.CLOSED
    )


def _warnings_for(
    plan: TradePlan,
    *,
    position: Position | Absent,
    positions: tuple[Position, ...],
    fills: tuple[FillLine, ...],
    journal: TradeJournal,
    accounts: tuple[str, ...],
    at: datetime,
) -> tuple[CaptureWarning, ...]:
    """Everything qualifying this view, in a fixed order.

    Fixed rather than severity-sorted: ordering by severity would make the list
    read as ranked by importance, and this package ranks nothing.
    """
    found: list[CaptureWarning] = []
    if len(positions) > 1:
        found.append(
            CaptureWarning(
                "TC-W2",
                f"This commitment's fills cross flat {len(positions)} times, so "
                "they fold into more than one round trip. Every figure below "
                "describes the most recent one; the earlier ones are visible in "
                "the fill list and nowhere else.",
            )
        )
    if len(accounts) > 1:
        found.append(
            CaptureWarning(
                "TC-W3",
                "Fills against this commitment sit in more than one account "
                f"({', '.join(accounts)}). A book never shares capacity across "
                "accounts, and this system does not reconcile the two.",
            )
        )
    if any(fill.was_corrected for fill in fills):
        found.append(
            CaptureWarning(
                "TC-W4",
                "At least one fill below has been corrected. What is shown is "
                "what the ledger now resolves to; the original stays readable "
                "through the correction chain.",
            )
        )
    if (
        not isinstance(position, Absent)
        and position.state is PositionState.OPEN
        and position.net_quantity != position.max_exposure
    ):
        found.append(
            CaptureWarning(
                "TC-W5",
                f"The position has been reduced: {position.net_quantity} is open "
                f"against a maximum exposure of {position.max_exposure}. Capital "
                "at risk above describes the maximum, not what is open now.",
            )
        )
    if plan.is_expired_at(at) and _status_of(position) is CaptureStatus.OPEN:
        found.append(
            CaptureWarning(
                "TC-W6",
                "The commitment expired while the position was still open. FMITS "
                "records the expiry and takes no action on it.",
            )
        )
    if not plan.targets:
        found.append(
            CaptureWarning(
                "TC-W7",
                "This commitment names no target, so no risk/reward pair exists "
                "for it. That is an absence, not a ratio of zero.",
            )
        )
    if journal.is_empty:
        found.append(
            CaptureWarning(
                "TC-W8",
                "Nothing has been written about this trade. Whether an entry "
                "exists at all is the cheapest discipline metric in this system, "
                "and this one has none. `fmits trade note` appends one.",
            )
        )
    return tuple(found)


def _view_from(
    plan: TradePlan,
    resolved: tuple[ResolvedTrade, ...],
    journal: TradeJournal,
    *,
    dust: DustPolicy,
    at: datetime,
) -> TradeView:
    fills = _fill_lines(resolved)
    positions = _positions_of(resolved, dust=dust)
    position: Position | Absent = (
        positions[-1]
        if positions
        else Absent("nothing has filled against this commitment")
    )
    entry = _entry_price(position)
    risk, reward, risk_warnings = _risk_figures(plan, position, entry)
    accounts = tuple(sorted({fill.account for fill in fills}))
    return TradeView(
        plan=plan,
        status=_status_of(position),
        fills=fills,
        position=position,
        entry_price=entry,
        capital_at_risk=risk,
        planned_risk_reward=reward,
        journal=journal,
        accounts=accounts,
        warnings=risk_warnings
        + _warnings_for(
            plan,
            position=position,
            positions=positions,
            fills=fills,
            journal=journal,
            accounts=accounts,
            at=at,
        ),
    )


def load_trade(
    store: TradingStore, plan_id: str, *, dust: DustPolicy, at: datetime
) -> TradeView:
    """Assemble one recorded swing trade from the plan, the ledger and the journal.

    `at` is supplied rather than read, exactly as everything below this layer
    requires: it decides only whether the commitment has expired, and a view that
    stamped itself could not be pinned in a test.
    """
    _require_store(store)
    _require_dust(dust)
    moment = require_utc(at, "at")
    plan = load_plan(store, plan_id)
    resolved = fills_for_plan(store.ledger.resolved(), plan.plan_id)
    journal = store.journals.trade_journal(PLAN_SUBJECT_KIND, plan.plan_id)
    return _view_from(plan, resolved, journal, dust=dust, at=moment)


def _matches(view: TradeView, filters: TradeFilters) -> bool:
    plan = view.plan
    if filters.status is not None and view.status is not filters.status:
        return False
    if filters.direction is not None and plan.direction is not filters.direction:
        return False
    if filters.symbol is not None:
        wanted = filters.symbol.upper()
        if wanted not in (plan.market.pair_symbol.upper(), plan.market.value.upper()):
            return False
    if filters.account is not None and filters.account not in view.accounts:
        return False
    if filters.since is not None and plan.committed_at < filters.since:
        return False
    if filters.until is not None and plan.committed_at > filters.until:
        return False
    return True


def _row_of(view: TradeView) -> TradeRow:
    return TradeRow(
        plan_id=view.plan_id,
        committed_at=view.plan.committed_at,
        market=view.plan.market,
        book=view.plan.book,
        direction=view.plan.direction,
        status=view.status,
        stop=view.plan.initial_invalidation,
        first_target=view.plan.first_target,
        accounts=view.accounts,
        capital_at_risk=view.capital_at_risk,
        realized_pnl_net=view.realized_pnl_net,
    )


def list_trades(
    store: TradingStore,
    *,
    dust: DustPolicy,
    at: datetime,
    filters: TradeFilters | None = None,
) -> TradeListing:
    """Every recorded swing trade, filtered, with what was excluded stated.

    The ledger is resolved **once** for the whole listing and the journal read
    once per plan. Both are O(rows) at this owner's volumes, on the same cost
    curve ADR-0027 accepted for the archive manifest; the trigger for changing
    that is the store's, not this surface's.
    """
    _require_store(store)
    _require_dust(dust)
    moment = require_utc(at, "at")
    applied = filters if filters is not None else TradeFilters()
    if not isinstance(applied, TradeFilters):
        raise TypeError("filters must be a TradeFilters")
    resolved = store.ledger.resolved()
    plans = store.plans.plans()
    rows: list[TradeRow] = []
    for plan in plans:
        view = _view_from(
            plan,
            fills_for_plan(resolved, plan.plan_id),
            store.journals.trade_journal(PLAN_SUBJECT_KIND, plan.plan_id),
            dust=dust,
            at=moment,
        )
        if _matches(view, applied):
            rows.append(_row_of(view))
    return TradeListing(rows=tuple(rows), filters=applied, total=len(plans))
