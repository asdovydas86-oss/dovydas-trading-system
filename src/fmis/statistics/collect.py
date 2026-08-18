"""The one module in this package that opens a store, and what it refuses to do.

Everything above it is a pure fold over `TradeStat` values; everything below it
is the owner half's own read path, called rather than reimplemented. A simulated
trade is assembled by `fmis.paper.views` and a recorded one by
`fmis.trade_capture.views` — the two packages that already know how to do it —
and this module's whole contribution is the **mapping into one vocabulary** and
the honest absences that mapping produces.

**No candle is fetched, ever.** `list_paper_trades` is called with no bars, and
that is the design rather than an omission: statistics are computed from
recorded history, so a finished trade contributes its **frozen** outcome and a
running trade contributes what the store holds. Passing bars would re-derive an
excursion from today's candle history and quietly make a past statistic depend
on what the venue still serves — the exact failure `AP` §25.3 froze MAE and MFE
to prevent. A guard asserts this package imports no candle.

**The R multiple of a recorded trade is computed, and of a running trade is
not.** For a recorded trade the denominator already exists: `TradeView`'s own
`capital_at_risk`, which is `fmis.plan.capital_at_risk` over the plan's stop and
the position's largest exposure. Dividing the realized profit and loss into it
is one division and makes hand-recorded trades comparable with simulated ones on
the one scale that crosses markets. For a trade still running there is no final
R — a running R multiple averaged in beside finished ones would mix *"what this
trade did"* with *"what it has done so far"*.

**Point-in-time is a parameter, not a filter callers remember.** `as_of` narrows
the corpus to trades that had closed by an instant and drops those committed
after it, which is `AP` §20.7 rule 1 applied where the corpus is built rather
than where it is read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from fmis.money import AssetCode, DustPolicy, Money
from fmis.paper import PaperTradeView, list_paper_trades
from fmis.persistence import TradingStore
from fmis.plan import TradePlan
from fmis.provenance import Absent
from fmis.records import require_text, require_utc
from fmis.snapshotting import MarketSnapshot
from fmis.statistics.models import (
    LifecyclePhase,
    StatSource,
    StatisticsError,
    TradeStat,
)
from fmis.risk import LimitScope, LimitUnit, RiskBudget
from fmis.trade_capture import CaptureStatus, TradeView, list_trades, load_trade

__all__ = [
    "CorpusUnreadableError",
    "CollectedTrades",
    "COLLECT_DUST_POLICY",
    "PHASE_OF_LIFECYCLE_STATE",
    "PHASE_OF_CAPTURE_STATUS",
    "stat_from_paper",
    "stat_from_recorded",
    "collect_trades",
    "quote_assets_of",
    "open_risk_limit",
]


class CorpusUnreadableError(StatisticsError):
    """The store exists and cannot be read.

    Named for the **corpus** rather than the store because `fmis.today` already
    exports a `StoreUnreadableError` for the identical condition one layer out,
    and this repository holds zero public-name collisions. Two names for one
    condition is the cost; two packages exporting one name is worse, because
    the collision is silent.

    A **missing** store is emptiness — an owner who has recorded nothing has no
    statistics and that is a page, not a failure. A store whose index or
    payloads are corrupt is a failure, and rendering it as an empty page would
    turn a detected corruption into a statement that the owner has never traded.
    """


#: What counts as flat when the ledger is folded into positions, for a caller
#: that names none. **Exact zero**, which is the only tolerance that is not a
#: policy decision — `DustPolicy`'s own rule, followed rather than restated.
#:
#: A caller that already folded this store must pass **its own** policy instead
#: of relying on this one. Two policies over one store draw the boundary between
#: one round trip and the next in two places, so the same ledger would produce
#: two different position counts and two different sets of statistics over them.
#: `fmis.today` passes its policy for exactly that reason.
COLLECT_DUST_POLICY = DustPolicy(policy_id="fmits.statistics.dust", version=1)

#: The simulator's ten lifecycle states, folded into the seven phases the counts
#: in this package are stated in. Written as a table rather than as branches, so
#: a state added to `TradeLifecycleState` fails a completeness test here instead
#: of silently falling into a default.
PHASE_OF_LIFECYCLE_STATE: Mapping[str, LifecyclePhase] = {
    "pending": LifecyclePhase.PENDING,
    "triggered": LifecyclePhase.TRIGGERED,
    "open": LifecyclePhase.OPEN,
    "partially_exited": LifecyclePhase.OPEN,
    "closed": LifecyclePhase.CLOSED,
    "resolved": LifecyclePhase.CLOSED,
    "cancelled": LifecyclePhase.CANCELLED,
    "expired": LifecyclePhase.EXPIRED,
    "superseded": LifecyclePhase.CANCELLED,
    "ambiguous": LifecyclePhase.AMBIGUOUS,
}

#: The capture surface's three statuses. `PLANNED` becomes `PENDING`: a
#: commitment nothing has filled against is waiting, whichever surface recorded
#: it, and giving it its own phase would split one question across two words.
PHASE_OF_CAPTURE_STATUS: Mapping[str, LifecyclePhase] = {
    CaptureStatus.PLANNED.value: LifecyclePhase.PENDING,
    CaptureStatus.OPEN.value: LifecyclePhase.OPEN,
    CaptureStatus.CLOSED.value: LifecyclePhase.CLOSED,
}


@dataclass(frozen=True, slots=True)
class CollectedTrades:
    """Every trade in a store, normalized, plus what could not be normalized.

    `refused` is not an error list to be logged and forgotten: a trade this
    module could not map is a trade absent from every count on every page, and
    naming it is what stops a corpus quietly shrinking.
    """

    trades: tuple[TradeStat, ...]
    refused: tuple[str, ...]
    store_root: str
    present: bool

    def __post_init__(self) -> None:
        """Checked here rather than trusted, because every consumer folds this.

        Without it a corpus holding one wrong value fails several layers down —
        inside a reduction, as an `AttributeError` about a field the caller
        never mentioned — and the message names neither the collection nor what
        was wrong with it.
        """
        if not isinstance(self.trades, tuple):
            raise TypeError("trades must be a tuple of TradeStat")
        for entry in self.trades:
            if not isinstance(entry, TradeStat):
                raise TypeError(
                    f"every collected trade must be a TradeStat, got "
                    f"{type(entry).__name__}"
                )
        if not isinstance(self.refused, tuple):
            raise TypeError("refused must be a tuple of str")
        for reason in self.refused:
            require_text(reason, "refused reason")
        object.__setattr__(
            self, "store_root", require_text(self.store_root, "store_root")
        )
        if not isinstance(self.present, bool):
            raise TypeError("present must be a bool")

    @property
    def is_empty(self) -> bool:
        return not self.trades

    def in_asset(self, asset: AssetCode) -> tuple[TradeStat, ...]:
        return tuple(stat for stat in self.trades if stat.quote_asset == asset)

    def to_payload(self) -> dict[str, Any]:
        return {
            "store_root": self.store_root,
            "present": self.present,
            "trades": [stat.to_payload() for stat in self.trades],
            "refused": list(self.refused),
        }


def _regime_states(snapshot: MarketSnapshot | None) -> dict[str, str]:
    """Every regime dimension the decision's frozen snapshot recorded.

    Read from the **setup** role when it exists, because that is the timeframe
    the commitment was formed on; the context role is about the environment the
    setup sits in and the execution role about the entry, and mixing all three
    would produce a key nobody could interpret. A dimension whose state was
    unavailable at snapshot time is left out rather than recorded as unknown —
    it is already absent, and `UNCLASSIFIED` is applied once, in `breakdown`.
    """
    if snapshot is None:
        return {}
    chosen = snapshot.roles[0]
    for reading in snapshot.roles:
        if reading.role.value == "setup":
            chosen = reading
            break
    states: dict[str, str] = {}
    for dimension in chosen.regime.dimensions:
        if not isinstance(dimension.state, Absent):
            states[dimension.name] = dimension.state
    return states


def stat_from_paper(
    view: PaperTradeView, *, snapshot: MarketSnapshot | None = None
) -> TradeStat:
    """One simulated trade, mapped into the shared vocabulary."""
    if not isinstance(view, PaperTradeView):
        raise TypeError(f"view must be a PaperTradeView, got {type(view).__name__}")
    activation = view.activation
    plan = view.plan
    monitor = view.monitor
    phase = PHASE_OF_LIFECYCLE_STATE.get(view.state.value)
    if phase is None:  # pragma: no cover - a completeness test covers the table
        raise StatisticsError(
            f"no phase is declared for lifecycle state {view.state.value!r}"
        )
    finished = not isinstance(view.outcome, Absent)
    reading = view.outcome if finished else None
    position = view.position

    return TradeStat(
        trade_ref=activation.activation_id,
        plan_id=activation.plan_id,
        source=StatSource.SIMULATED,
        phase=phase,
        market=activation.market,
        book=activation.book,
        direction=plan.direction,
        quote_asset=activation.market.quote_asset,
        committed_at=activation.activated_at,
        opened_at=(
            reading.outcome.opened_at
            if reading is not None
            else _opened_of(position)
        ),
        closed_at=(
            reading.outcome.closed_at
            if reading is not None
            else Absent("this trade has not finished")
        ),
        realized_pnl_net=_pnl(position, net=True),
        realized_pnl_gross=_pnl(position, net=False),
        initial_risk=monitor.initial_risk,
        # Only a finished trade has an R multiple. The monitor's running total is
        # a live reading and averaging it beside final ones would mix two facts.
        r_multiple=(
            reading.final_r
            if reading is not None
            else Absent("this trade has not finished, so it has no final R multiple")
        ),
        max_favourable_r=(
            reading.max_favourable_r
            if reading is not None
            else Absent("no excursion is frozen until this trade finishes")
        ),
        max_adverse_r=(
            reading.max_adverse_r
            if reading is not None
            else Absent("no excursion is frozen until this trade finishes")
        ),
        bars_held=(
            reading.outcome.bars_held
            if reading is not None
            else Absent("no bar count is frozen until this trade finishes")
        ),
        holding_time=(
            reading.outcome.holding_time()
            if reading is not None
            else monitor.holding_time
        ),
        exit_reason=(
            reading.outcome.exit_reason.value
            if reading is not None
            else Absent("this trade has not ended")
        ),
        account=activation.account.value,
        interval=activation.interval,
        setup_type=_setup_of(plan),
        regime_states=_regime_states(snapshot),
        stop_moves=monitor.stop_moves,
        stop_widenings=monitor.stop_widenings,
    )


def stat_from_recorded(
    view: TradeView, *, snapshot: MarketSnapshot | None = None
) -> TradeStat:
    """One hand-recorded trade, mapped into the shared vocabulary.

    Every simulator-only figure is `Absent` with the reason, and the reason is
    the same one every time: nothing froze an excursion for a trade nobody
    simulated. `ST-2` carries that to the page.
    """
    if not isinstance(view, TradeView):
        raise TypeError(f"view must be a TradeView, got {type(view).__name__}")
    plan = view.plan
    position = view.position
    phase = PHASE_OF_CAPTURE_STATUS.get(view.status.value)
    if phase is None:  # pragma: no cover - a completeness test covers the table
        raise StatisticsError(
            f"no phase is declared for capture status {view.status.value!r}"
        )
    net = _pnl(position, net=True)
    return TradeStat(
        trade_ref=plan.plan_id,
        plan_id=plan.plan_id,
        source=StatSource.RECORDED,
        phase=phase,
        market=plan.market,
        book=plan.book,
        direction=plan.direction,
        quote_asset=plan.market.quote_asset,
        committed_at=plan.committed_at,
        opened_at=_opened_of(position),
        closed_at=_closed_of(position),
        realized_pnl_net=net,
        realized_pnl_gross=_pnl(position, net=False),
        initial_risk=view.capital_at_risk,
        r_multiple=_recorded_r(net, view.capital_at_risk, phase),
        holding_time=_duration_of(position),
        exit_reason=Absent(
            "a recorded trade carries no exit reason; the closing note holds why"
        ),
        account=view.accounts[0] if len(view.accounts) == 1 else _accounts(view),
        setup_type=_setup_of(plan),
        regime_states=_regime_states(snapshot),
    )


def _recorded_r(
    net: Money | Absent, risk: Money | Absent, phase: LifecyclePhase
) -> Decimal | Absent:
    """Realized profit and loss divided into the capital that was at risk.

    Reuses `TradeView.capital_at_risk`, which is already
    `fmis.plan.capital_at_risk` over the plan's stop and the position's largest
    exposure. This is the one arithmetic step this module performs, and it is a
    division rather than a second risk model.

    Refused while the trade is open, refused with no risk figure, and refused on
    a risk of zero. The last is the important one: a zero denominator would
    produce the largest R multiple in the corpus out of the trade whose stop
    could not be measured.
    """
    if phase is not LifecyclePhase.CLOSED:
        return Absent("this trade has not closed, so it has no final R multiple")
    if isinstance(net, Absent):
        return net
    if isinstance(risk, Absent):
        return Absent(
            f"no capital-at-risk figure exists for this trade: {risk.reason}"
        )
    if risk.amount == 0:
        return Absent(
            "the capital at risk on this trade is zero, so an R multiple over it "
            "would be undefined rather than large"
        )
    if risk.asset != net.asset:  # pragma: no cover - both come from one market
        return Absent(
            f"the risk is in {risk.asset.code} and the result in {net.asset.code}"
        )
    return net.amount / risk.amount


def _accounts(view: TradeView) -> str | Absent:
    if not view.accounts:
        return Absent("no fill has named an account")
    return Absent(
        f"this trade filled across {len(view.accounts)} accounts, so it belongs to "
        "no single one"
    )


def _setup_of(plan: TradePlan) -> str | Absent:
    if isinstance(plan.setup_type, Absent):
        return plan.setup_type
    return plan.setup_type.term_id


def _pnl(position: Any, *, net: bool) -> Money | Absent:
    if isinstance(position, Absent):
        return Absent("nothing has filled against this commitment")
    return position.realized_pnl_net if net else position.realized_pnl_gross


def _opened_of(position: Any) -> datetime | Absent:
    if isinstance(position, Absent):
        return Absent("this trade never held a position")
    return position.opened_at


def _closed_of(position: Any) -> datetime | Absent:
    if isinstance(position, Absent):
        return Absent("this trade never held a position")
    return position.closed_at


def _duration_of(position: Any) -> Any:
    if isinstance(position, Absent):
        return Absent("this trade never held a position")
    return position.duration


def quote_assets_of(trades: tuple[TradeStat, ...]) -> tuple[AssetCode, ...]:
    """Every settlement asset present, in a stable order.

    The corpus is split on this and never summed across it — `ST-5`. Sorted by
    code so two runs over one store produce the same first asset, which is the
    one a page with room for a single set of figures shows.
    """
    return tuple(
        sorted({stat.quote_asset for stat in trades}, key=lambda asset: asset.code)
    )


def open_risk_limit(
    store: TradingStore, *, at: datetime
) -> Money | Absent:
    """The owner's own total-open-risk ceiling, in money, at an instant.

    **The limit only.** This package evaluates no constraint and forms no
    opinion: `fmis.portfolio_risk` owns *"is this portfolio within its limits"*
    and `fmits approve` is where that question is asked. What is read here is
    the single number the owner configured, so that a page can say what share of
    it **the trades on that page** account for — a narrower figure than the
    portfolio-wide one, and labelled as such wherever it is shown.

    `Absent` for every way the answer can legitimately not exist: no budget
    lineage, several lineages with no way to choose, none in force at the
    instant, or a ceiling stated as a fraction of an equity this reading does
    not hold.
    """
    if not isinstance(store, TradingStore):
        raise TypeError("store must be a TradingStore")
    moment = require_utc(at, "at")
    lineages = store.risk.budget_ids()
    if not lineages:
        return Absent(
            "no risk budget has been recorded, so there is no ceiling to measure "
            "against. That is a gap in the owner's policy, not a measurement "
            "failure"
        )
    if len(lineages) > 1:
        return Absent(
            f"{len(lineages)} risk-budget lineages exist and this reading picks "
            "none; choosing one would silently measure against limits the owner "
            "did not mean"
        )
    budget = store.risk.in_force_at(lineages[0], moment)
    if isinstance(budget, Absent):
        return budget
    return _total_open_risk_ceiling(budget)


def _total_open_risk_ceiling(budget: RiskBudget) -> Money | Absent:
    """The `TOTAL_OPEN_RISK` limit, if it is stated in money.

    A ceiling expressed as a percent of equity is refused rather than converted:
    turning it into money needs the equity that produced it, and doing that
    division quietly here would be the second place a limit is interpreted —
    `remaining_risk_capacity` refuses the identical case for the identical
    reason.
    """
    for limit in budget.limits:
        if limit.scope is not LimitScope.TOTAL_OPEN_RISK:
            continue
        if limit.unit is not LimitUnit.MONEY:
            return Absent(
                f"the total-open-risk limit {limit.limit_id!r} is stated in "
                f"{limit.unit.value}; converting it to money needs the equity it "
                "was measured against, which this reading does not hold"
            )
        return limit.value
    return Absent(
        "this budget states no total-open-risk limit, so there is no ceiling to "
        "report a share of"
    )


def collect_trades(
    root: Path | str,
    *,
    at: datetime,
    as_of: datetime | Absent = Absent("no point-in-time cut was requested"),
    dust: DustPolicy = COLLECT_DUST_POLICY,
) -> CollectedTrades:
    """Read every trade in a store and normalize it. The package's only I/O.

    Raises:
        CorpusUnreadableError: the store exists and cannot be read. A missing
            store is an empty corpus, not a failure.
    """
    moment = require_utc(at, "at")
    if not isinstance(as_of, (datetime, Absent)):
        raise TypeError("as_of must be a datetime or Absent")
    cut = as_of if isinstance(as_of, Absent) else require_utc(as_of, "as_of")
    store_root = Path(root)
    if not store_root.exists():
        return CollectedTrades(
            trades=(), refused=(), store_root=str(store_root), present=False
        )
    if not isinstance(dust, DustPolicy):
        raise TypeError("dust must be a DustPolicy")
    store = TradingStore(store_root, dust=dust)

    collected: list[TradeStat] = []
    refused: list[str] = []
    try:
        # **Every** read of the store sits inside this block, the snapshot sweep
        # included. It did not, in the first draft, and a corrupt store raised
        # the store's own `StoreIntegrityError` straight past this layer — so a
        # caller catching this package's errors saw an unhandled traceback for
        # the one condition this class exists to name.
        snapshots = _snapshots_by_id(store)
        simulated = list_paper_trades(store, dust=dust, at=moment)
        recorded = list_trades(store, dust=dust, at=moment)
    except Exception as error:  # noqa: BLE001 - re-raised as this layer's failure
        raise CorpusUnreadableError(
            f"the store at {store_root} exists and could not be read: {error}. It "
            "is not rendered as an empty corpus, because that would report the "
            "owner has never traded"
        ) from error

    simulated_plans = {view.activation.plan_id for view in simulated}
    for view in simulated:
        try:
            collected.append(
                stat_from_paper(
                    view, snapshot=snapshots.get(_snapshot_id(view.plan))
                )
            )
        except StatisticsError as error:
            refused.append(f"{view.activation_id}: {error}")
    for row in recorded.rows:
        if row.plan_id in simulated_plans:
            # The same commitment reached the simulator. Counting the plan twice
            # would double every figure derived from it, and the simulated view
            # is the one carrying an excursion and a bar count.
            continue
        try:
            view = _load_recorded(store, row.plan_id, at=moment, dust=dust)
            collected.append(
                stat_from_recorded(
                    view, snapshot=snapshots.get(_snapshot_id(view.plan))
                )
            )
        except StatisticsError as error:
            refused.append(f"{row.plan_id}: {error}")

    kept = tuple(_within(stat, cut) for stat in collected)
    return CollectedTrades(
        trades=tuple(stat for stat in kept if stat is not None),
        refused=tuple(refused),
        store_root=str(store_root),
        present=True,
    )


def _within(stat: TradeStat, cut: datetime | Absent) -> TradeStat | None:
    """`AP` §20.7 rule 1 — a past statement uses only what was true by then.

    A trade committed after the cut did not exist; a trade that closed after it
    was still open. The second case is dropped rather than reported as open,
    because reconstructing what its monitor said at that instant would need the
    candle history this package refuses to fetch.
    """
    if isinstance(cut, Absent):
        return stat
    if stat.committed_at > cut:
        return None
    if not isinstance(stat.closed_at, Absent) and stat.closed_at > cut:
        return None
    return stat


def _snapshot_id(plan: TradePlan) -> str | None:
    if isinstance(plan.market_snapshot_id, Absent):
        return None
    return plan.market_snapshot_id


def _snapshots_by_id(store: TradingStore) -> dict[str, MarketSnapshot]:
    """Every frozen market snapshot, keyed by id, read once for the whole corpus.

    Read once rather than per trade for the reason `list_trades` resolves the
    ledger once: at this owner's volumes both are O(rows), and the trigger for
    changing that belongs to the store rather than to this surface.

    `SnapshotRepository.snapshots()` rather than `.all()` and a type check: that
    repository holds `MarketSnapshot` **and** `DecisionWindow`, and it already
    owns the filter. A hand-rolled `isinstance` here would be a second place
    that knows which kinds live in it, and the second place is the one that goes
    stale when a third kind is added.
    """
    return {
        snapshot.snapshot_id: snapshot for snapshot in store.snapshots.snapshots()
    }


def _load_recorded(
    store: TradingStore, plan_id: str, *, at: datetime, dust: DustPolicy
) -> TradeView:
    return load_trade(store, plan_id, dust=dust, at=at)
