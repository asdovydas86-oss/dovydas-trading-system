"""The composition root: two halves read separately, assembled once.

    read_store(root, at=...)              ──►  StoreReading   (owner half)
    build_today(results, reading, ...)    ──►  TodayWorkspace (pure)
    run_today(...)                        ──►  TodayWorkspace (fetches)

**`build_today` is a pure function and is the whole of the assembly.** It fetches
nothing, opens nothing and reads no clock; given the same scan results and the
same store reading it returns an equal workspace. Everything that touches a
network or a filesystem lives in `run_today` and `read_store`, which is what
makes the assembly testable without either.

**The two halves are read by two functions that cannot see each other's inputs.**
`read_store` receives no scan result and `opportunities_from_results` receives no
position — *the market half never reads the trading half, or the analysis becomes
a function of the position, the oldest bias in trading.* Here that separation is
free, because the two families meet only inside `TodayWorkspace`.

**A missing store is a reading, not a failure.** `fmis.persistence` treats a
missing line file as emptiness, and this module keeps that: opening a workspace
on a machine that has never recorded a trade produces a complete page whose
capital section says, in words, that it knows nothing about what the owner
holds. Constructing a `TradingStore` creates no directory and writes no byte, so
reading is safe on a root that does not exist.

**The dust policy is exact zero and is not a chosen number.** Folding a position
needs to know what counts as flat, and `fmis.money.DustPolicy` states that *"an
asset with no configured threshold uses exact zero... zero is the only tolerance
that is not a policy decision."* This package therefore configures no threshold
at all rather than inventing one, and the workspace says which policy it folded
under.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fmis.archive import ArchiveError, ArchiveStore, default_archive_root
from fmis.decision_context import ContextPolicy
from fmis.market_regime import RegimePolicy
from fmis.money import DustPolicy
from fmis.persistence import PersistenceError, TradingStore, default_store_root
from fmis.pipeline.multi_timeframe import TimeframeRole
from fmis.pipeline.structural_facts import DetectionSettings
from fmis.position_sizing import (
    DEFAULT_BOOK,
    DEFAULT_SIZING_POLICY_ID,
    SizingPolicy,
    approve_results,
    budget_in_effect,
    engine_for,
    owner_context,
    sole_account,
)
from fmis.provenance import Absent
from fmis.records import TradeDomainError
from fmis.swing_setup import SCAN_UNIVERSE, run_market_scan
from fmis.today.attention import build_queue
from fmis.paper import load_paper_trade
from fmis.today.models import (
    NotAvailable,
    StoreUnreadableError,
    TodayError,
    TodayWorkspace,
)
from fmis.today.sections import (
    analysis_summary,
    journal_summary,
    market_overview_from_results,
    paper_trading,
    opportunities_from_results,
    portfolio_overview,
)
from fmis.today.warnings import workspace_warnings
from fmis.valuation import (
    DEFAULT_BASE_CURRENCY,
    DEFAULT_PORTFOLIO_ID,
    ValuationError,
    marks_for_store,
    value_portfolio,
)

__all__ = [
    "DUST_POLICY",
    "TODAY_LIMITATIONS",
    "OBJECTIVE",
    "StoreReading",
    "approvals_for",
    "build_today",
    "empty_reading",
    "read_store",
    "run_today",
]

OBJECTIVE = "swing"

#: Exact zero, with no configured threshold, for the reason the module docstring
#: gives: zero is the only tolerance that is not a policy decision, and this
#: package chooses no policy on the owner's behalf.
DUST_POLICY = DustPolicy(policy_id="fmits-today-exact-zero", version=1)

#: Printed on every page, unchanged. These are the *invariant* register: they
#: belong once, at the foot of the page, and never beside a number. The
#: this-run register — the warnings section — is where anything qualifying a
#: specific value appears.
TODAY_LIMITATIONS: tuple[tuple[str, str], ...] = (
    (
        "TD-1",
        "This page assembles what already exists. It computes no market "
        "quantity and no monetary one, and every figure on it was produced by "
        "an engine or read from a record.",
    ),
    (
        "TD-2",
        "Nothing here is ranked by desirability. The priority queue orders by "
        "the engine's own readiness state and then by watchlist order; "
        "readiness describes the analysis, not the instrument.",
    ),
    (
        "TD-3",
        "No position size is computed and nothing is rebalanced. Market value "
        "and exposure are measured from marks; open risk still cannot be, "
        "because it needs a recorded stop for every open position and a "
        "TradePlan is what states one.",
    ),
    (
        "TD-4",
        "No probability is calibrated. No resolved-episode cohort exists, so "
        "no number on this page is a likelihood of anything.",
    ),
    (
        "TD-5",
        "No macro, news, derivatives, on-chain, orderbook or liquidity data is "
        "represented anywhere. Identical price action under extreme funding is "
        "a different trade, and this page cannot distinguish them.",
    ),
    (
        "TD-6",
        "Positions, capital, decisions and journal entries are read from the "
        "durable store only. Anything held at an exchange and not recorded "
        "there is invisible to every section below.",
    ),
    (
        "TD-7",
        "One analysis instant is shown per symbol, not the age of each "
        "timeframe role. The weekly context role gates whether any direction "
        "may exist and can be many days older than the execution bar.",
    ),
    (
        "TD-8",
        "Correlation between markets is never measured. A concentration "
        "observation counts setups sharing one side; it does not claim those "
        "markets move together.",
    ),
)


@dataclass(frozen=True, slots=True)
class StoreReading:
    """Everything the owner half contributes, read once and passed as data.

    A record rather than a live store handle, so `build_today` cannot reach the
    filesystem even by accident and a test can assemble a full page from
    hand-built domain objects with no store at all.
    """

    root: str
    present: bool
    positions: tuple[Any, ...]
    closed_positions: tuple[Any, ...]
    budget: Any | None
    snapshot: Any | None
    journal_entries: tuple[Any, ...]
    decisions: tuple[str, ...]
    citations: tuple[Any, ...]
    market_snapshots: tuple[Any, ...]
    archived: tuple[Any, ...]
    #: The `PortfolioValuation` for this run, or `None` when no price source was
    #: consulted. `None` rather than an empty valuation, because *"this page did
    #: not look"* and *"this page looked and priced nothing"* are different
    #: facts and the second one is a problem.
    valuation: Any | None = None
    #: The one account this store records fills in, or `Absent` naming why there
    #: is no single answer. An approval is scoped to an account because books
    #: never share capacity across accounts, and picking one of several would
    #: produce a confident answer about the wrong capacity pool.
    account: Any | None = None
    #: Every simulated trade this store holds, already assembled by the paper
    #: package's own read path. Views rather than raw records, so this page and
    #: `fmits trade status` render one calculation instead of two that agree.
    paper_trades: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.root, str) or not self.root.strip():
            raise TodayError("root must be a non-empty str")
        if not isinstance(self.present, bool):
            raise TypeError("present must be a bool")
        for name in (
            "positions",
            "closed_positions",
            "journal_entries",
            "decisions",
            "citations",
            "market_snapshots",
            "archived",
            "paper_trades",
        ):
            if not isinstance(getattr(self, name), tuple):
                raise TypeError(f"{name} must be a tuple")


def _budget_in_force(store: TradingStore, at: datetime) -> Any | None:
    """The single risk budget in force, or `None` when none is.

    A store with several budget lineages is not an error and is not guessed at:
    with more than one, none is chosen, because picking the first would make
    *which limits apply* depend on an id sort nobody wrote down.
    """
    ids = store.risk.budget_ids()
    if len(ids) != 1:
        return None
    budget = store.risk.in_force_at(ids[0], at)
    return None if isinstance(budget, Absent) else budget


def _latest_snapshot(store: TradingStore) -> Any | None:
    """The latest portfolio snapshot, or `None` — same single-lineage rule."""
    ids = store.portfolios.portfolio_ids()
    if len(ids) != 1:
        return None
    return store.portfolios.latest(ids[0])


def _decision_lines(store: TradingStore) -> tuple[str, ...]:
    """One line per live proposal, naming its folded state and when it expires.

    The state is folded on every call and stored nowhere, which is the only
    reading that stays correct when a superseding event arrives.
    """
    lines = []
    for proposal, view in store.opportunities.live_proposals():
        lines.append(
            f"{proposal.proposal_id} · {proposal.market.value} · "
            f"{view.state.value} · valid until {proposal.valid_until.isoformat()}"
        )
    return tuple(lines)


def _archived_entries(archive_root: Path) -> tuple[Any, ...]:
    """Archive manifest rows, metadata only — no payload is opened.

    An unreadable or corrupt archive must not take the page down with it: this
    section is a memory aid, and losing it is not a reason to lose the market
    and capital sections above it. A failure reads as no entries, and the
    absence is reported by the analysis section's own note.
    """
    try:
        return tuple(ArchiveStore(archive_root).list())
    except (ArchiveError, OSError):
        return ()


def _paper_views(store: TradingStore, at: datetime) -> tuple[Any, ...]:
    """Every simulated trade this store holds, assembled by the paper read path.

    **No candles are fetched.** This page runs offline against the store, so the
    excursions of a trade that has not finished come back `Absent` with the
    reason — `fmits simulate` is where a bar is read, and the frozen outcome is
    where a finished trade's excursion comes from. A page that invented a zero
    excursion for an open trade would make every one of them look like a trade
    that never went against the owner.
    """
    return tuple(
        load_paper_trade(store, activation.activation_id, dust=DUST_POLICY, at=at)
        for activation in store.activations.activations()
    )


def read_store(
    root: Path | str,
    *,
    at: datetime,
    archive_root: Path | str | None = None,
    prices: Any | None = None,
) -> StoreReading:
    """Read everything the owner half contributes, in one pass.

    ``at`` is the instant a risk budget generation is resolved against — the
    outer boundary's reference time. Nothing in the store reads a clock, so it
    has to be supplied.

    ``prices`` is a `PriceSnapshot` when the caller fetched one, and `None` when
    it did not. Supplying one turns every marked figure on the page from an
    absence into money; supplying none leaves the page exactly as `BJ` shipped
    it, which is why this parameter defaults to `None` rather than to a fetch.

    Raises:
        StoreUnreadableError: the store exists and is corrupt. A *missing* store
            is emptiness, not a failure; a store whose index, journal or payload
            cannot be read is a failure, and is never quietly rendered as an
            empty page — that would turn a detected corruption into a page
            saying the owner holds nothing.
    """
    if not isinstance(at, datetime):
        raise TypeError(f"at must be a datetime, got {type(at).__name__}")
    store_root = Path(root)
    store = TradingStore(store_root, dust=DUST_POLICY)
    try:
        folded = store.positions.rebuild()
        return StoreReading(
            root=str(store_root),
            present=store_root.exists(),
            positions=tuple(position for position in folded if position.is_open),
            closed_positions=tuple(
                position for position in folded if not position.is_open
            ),
            budget=_budget_in_force(store, at),
            snapshot=_latest_snapshot(store),
            journal_entries=store.journals.live_entries(),
            decisions=_decision_lines(store),
            citations=store.analyses.search(),
            market_snapshots=store.snapshots.snapshots(),
            archived=_archived_entries(
                default_archive_root() if archive_root is None else Path(archive_root)
            ),
            valuation=(
                None
                if prices is None
                else value_portfolio(
                    store,
                    portfolio_id=DEFAULT_PORTFOLIO_ID,
                    base_currency=DEFAULT_BASE_CURRENCY,
                    as_of=at,
                    prices=prices,
                )
            ),
            account=sole_account(store),
            paper_trades=_paper_views(store, at),
        )
    except (PersistenceError, TradeDomainError) as error:
        # Both families, and the second is not redundant: a hand-edited index
        # row or a payload written by a newer build fails the *domain's* own
        # decoder (`PayloadDecodeError`, a `TradeDomainError`) long before any
        # store-level check runs. Catching only `PersistenceError` let that
        # escape as an unhandled traceback — found by the corrupt-store test
        # below, not by reading the hierarchy.
        raise StoreUnreadableError(
            f"the store at {store_root} could not be read: "
            f"{type(error).__name__}: {error}"
        ) from error


def empty_reading(root: Path | str) -> StoreReading:
    """A reading for a root that was never opened — used when the store is skipped.

    Distinct from a reading of an empty store: ``present`` is `False`, which is
    what raises `M-NO-STORE` rather than `M-NO-POSITIONS`, and the difference is
    the difference between *"you have recorded nothing"* and *"this page did not
    look."*
    """
    return StoreReading(
        root=str(root),
        present=False,
        positions=(),
        closed_positions=(),
        budget=None,
        snapshot=None,
        journal_entries=(),
        decisions=(),
        citations=(),
        market_snapshots=(),
        archived=(),
        valuation=None,
        account=None,
    )


def _prices_for(
    root: Path,
    *,
    at: datetime,
    transport: Any | None,
    interval: str | None,
) -> Any:
    """One price per market the store holds an open position in.

    Wrapped so `run_today` reads as one line and so the store-unreadable
    translation happens once. `fmis.valuation` raises its own
    `PortfolioStoreError`; this package's own `StoreUnreadableError` is what the
    CLI already catches, and having two names for one condition reach the same
    surface is how one of them stops being handled.
    """
    try:
        return (
            marks_for_store(root, taken_at=at, transport=transport)
            if interval is None
            else marks_for_store(
                root, taken_at=at, transport=transport, interval=interval
            )
        )
    except ValuationError as error:
        raise StoreUnreadableError(
            f"the store at {root} could not be read for pricing: "
            f"{type(error).__name__}: {error}"
        ) from error


def approvals_for(
    reading: StoreReading,
    results: Sequence[Any],
    *,
    policy: SizingPolicy,
    account: Any | None = None,
    book: Any = DEFAULT_BOOK,
    classification: Any | None = None,
    timezone: str | None = None,
) -> tuple[dict[str, Any], str | NotAvailable]:
    """Approve every actionable candidate against one portfolio reading, or say why not.

    **Pure.** Every input is already in the `StoreReading` or is a value the
    caller configured; nothing here opens a store, reaches a venue or reads a
    clock. That is what lets a test assemble a fully-approved page from
    hand-built domain objects.

    **One reading, one budget, one engine, for every candidate on the page.**
    `fmis.position_sizing.approve_results` states the consequence: two candidates
    that each fit the budget alone do not both fit it together, and this page
    does not claim they do — each is evaluated against the portfolio *as it
    stands*, independently.

    Returns the mapping and the note that explains it. **Four inputs can be
    missing and each produces a different sentence**, because *"you did not let
    this page read the store"*, *"you have recorded no limits"*, *"you trade in
    two accounts and must say which"* and *"nothing was priced"* have four
    different remedies and one blank.
    """
    if not isinstance(policy, SizingPolicy):
        raise TypeError(f"policy must be a SizingPolicy, got {type(policy).__name__}")
    if reading.valuation is None:
        return {}, NotAvailable(
            reason=(
                "no portfolio reading was produced for this page, so there is "
                "nothing to size a candidate against"
            ),
            owned_by="the valuation layer (drop --no-records / --no-marks)",
            forbidden_inference=(
                "Do not read an unapproved candidate as one your limits permit."
            ),
        )
    if reading.budget is None:
        return {}, NotAvailable(
            reason=(
                "no single risk-budget lineage is in force, so there are no "
                "limits to evaluate a candidate against"
            ),
            owned_by="the owner — every limit is a value the owner sets",
            forbidden_inference=(
                "Do not infer that no limit applies to you. It means no limit is "
                "recorded here."
            ),
        )
    scoped = account if account is not None else reading.account
    if scoped is None or isinstance(scoped, Absent):
        return {}, NotAvailable(
            reason=(
                "no account could be scoped for this page: "
                + (
                    "the store was not read"
                    if scoped is None
                    else scoped.reason
                )
            ),
            owned_by="the owner — name one with --account",
            forbidden_inference=(
                "Do not read an unscoped candidate as one that fits an account's "
                "capacity. Books never share capacity across accounts."
            ),
        )
    state = reading.valuation.state
    approvals = approve_results(
        results,
        engine=engine_for(policy, classification),
        state=state,
        budget=reading.budget,
        owner=owner_context(
            base_currency=state.base_currency,
            **({} if timezone is None else {"timezone": timezone}),
        ),
        account=scoped,
        book=book,
        mark_age=reading.valuation.mark_age,
    )
    return approvals, (
        f"{len(approvals)} candidate(s) sized and evaluated against budget "
        f"{reading.budget.budget_id} (policy version "
        f"{reading.budget.risk_policy_version}) in account {scoped.value}, book "
        f"{book.value}, under sizing policy {policy.policy_id!r}. Each is "
        "evaluated against the portfolio as it stands, independently of the "
        "others: two candidates that each fit the budget alone do not both fit "
        "it together."
    )


def build_today(
    results: Sequence[Any],
    reading: StoreReading,
    *,
    reference_time: datetime,
    source: str,
    approvals: Any | None = None,
    approval_note: Any = None,
) -> TodayWorkspace:
    """Assemble the workspace. Pure — no clock, no network, no filesystem.

    ``approvals`` maps a requested symbol to the `ApprovalResult` computed for
    it, and ``approval_note`` says whether one was computed at all. Both are
    parameters rather than derivations because the approval is the one figure on
    this page that reads *both* halves at once — the market half's candidate and
    the owner half's limits — and computing it inside the assembly would put a
    portfolio reading inside the function that must not have one.

    Raises:
        TypeError: an argument is of the wrong type.
        TodayError: ``results`` is empty.
    """
    if not isinstance(reading, StoreReading):
        raise TypeError(
            f"reading must be a StoreReading, got {type(reading).__name__}"
        )
    if not isinstance(reference_time, datetime):
        raise TypeError(
            f"reference_time must be a datetime, got {type(reference_time).__name__}"
        )

    opportunities = opportunities_from_results(
        results, approvals, approval_note=approval_note
    )
    market = market_overview_from_results(results, opportunities)
    portfolio = portfolio_overview(
        store_root=reading.root,
        store_present=reading.present,
        positions=reading.positions,
        budget=reading.budget,
        snapshot=reading.snapshot,
        valuation=reading.valuation,
    )
    queue = build_queue(opportunities.confirmed, opportunities.candidates)
    paper = paper_trading(reading.paper_trades, read=reading.present)
    journal = journal_summary(
        entries=reading.journal_entries,
        closed_positions=reading.closed_positions,
        decisions=reading.decisions,
    )
    analysis = analysis_summary(
        archived=reading.archived,
        citations=reading.citations,
        snapshots=reading.market_snapshots,
    )
    raised = workspace_warnings(
        actionable=opportunities.confirmed + opportunities.candidates,
        failed=opportunities.failed,
        unreadable=market.unreadable,
        readable_declined=market.readable_declined,
        portfolio=portfolio,
    )
    return TodayWorkspace(
        reference_time=reference_time,
        objective=OBJECTIVE,
        source=source,
        market=market,
        portfolio=portfolio,
        opportunities=opportunities,
        queue=queue,
        paper=paper,
        journal=journal,
        analysis=analysis,
        warnings=raised,
        limitations=TODAY_LIMITATIONS,
        metadata={"dust_policy": DUST_POLICY.policy_id},
    )


def run_today(
    symbols: Sequence[str] = SCAN_UNIVERSE,
    *,
    reference_time: datetime,
    store_root: Path | str | None = None,
    archive_root: Path | str | None = None,
    read_records: bool = True,
    timeframes: Mapping[TimeframeRole, str] | None = None,
    limit: int | None = None,
    policy: RegimePolicy | None = None,
    context_policy: ContextPolicy | None = None,
    detection: DetectionSettings | None = None,
    transport: Any | None = None,
    read_marks: bool = True,
    mark_interval: str | None = None,
    sizing: SizingPolicy | None = None,
    account: Any | None = None,
    book: Any = DEFAULT_BOOK,
    classification: Any | None = None,
    timezone: str | None = None,
) -> TodayWorkspace:
    """Run one evening's workspace end to end.

    Calls the exact, unmodified `run_market_scan` → `run_setup_for_symbols`
    chain `fmits scan` and `fmits setup` already use, so a row here and a page
    there for the same symbol at the same instant are produced by identical
    code and cannot disagree. Per-symbol failure isolation is inherited
    unchanged: one symbol's outage never stops the run.

    ``read_records=False`` skips the store entirely, which is what
    ``--no-records`` is for — the page still renders, and says that it did not
    look. ``read_marks=False`` keeps the store and skips only the prices, which
    is a different and equally legitimate answer: the positions are still
    listed, and every figure that needed a price says so.

    **Prices are fetched only for markets the store already holds a position
    in.** The scan's watchlist is not priced, because a watchlist symbol has no
    quantity and therefore no value; asking for one would spend a request to
    produce a number nothing on this page may show.

    Raises:
        StoreUnreadableError: the store exists and cannot be read.
    """
    root = default_store_root() if store_root is None else Path(store_root)
    results = run_market_scan(
        symbols,
        timeframes=timeframes,
        limit=limit,
        policy=policy,
        context_policy=context_policy,
        detection=detection,
        transport=transport,
    )
    prices = (
        _prices_for(
            root,
            at=reference_time,
            transport=transport,
            interval=mark_interval,
        )
        if read_records and read_marks
        else None
    )
    reading = (
        read_store(
            root, at=reference_time, archive_root=archive_root, prices=prices
        )
        if read_records
        else empty_reading(root)
    )
    approvals, note = approvals_for(
        reading,
        results,
        policy=(
            SizingPolicy(policy_id=DEFAULT_SIZING_POLICY_ID)
            if sizing is None
            else sizing
        ),
        account=account,
        book=book,
        classification=classification,
        timezone=timezone,
    )
    return build_today(
        results,
        reading,
        reference_time=reference_time,
        source=f"binance-public · store {root}",
        approvals=approvals,
        approval_note=note,
    )
