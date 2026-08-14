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
from fmis.provenance import Absent
from fmis.records import TradeDomainError
from fmis.swing_setup import SCAN_UNIVERSE, run_market_scan
from fmis.today.attention import build_queue
from fmis.today.models import (
    StoreUnreadableError,
    TodayError,
    TodayWorkspace,
)
from fmis.today.sections import (
    analysis_summary,
    journal_summary,
    market_overview_from_results,
    opportunities_from_results,
    portfolio_overview,
)
from fmis.today.warnings import workspace_warnings

__all__ = [
    "DUST_POLICY",
    "TODAY_LIMITATIONS",
    "OBJECTIVE",
    "StoreReading",
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
        "No position size, portfolio risk or leverage is computed. Open risk "
        "cannot be measured without a mark for every holding and a recorded "
        "stop for every position, and neither exists.",
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


def read_store(
    root: Path | str,
    *,
    at: datetime,
    archive_root: Path | str | None = None,
) -> StoreReading:
    """Read everything the owner half contributes, in one pass.

    ``at`` is the instant a risk budget generation is resolved against — the
    outer boundary's reference time. Nothing in the store reads a clock, so it
    has to be supplied.

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
    )


def build_today(
    results: Sequence[Any],
    reading: StoreReading,
    *,
    reference_time: datetime,
    source: str,
) -> TodayWorkspace:
    """Assemble the workspace. Pure — no clock, no network, no filesystem.

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

    opportunities = opportunities_from_results(results)
    market = market_overview_from_results(results, opportunities)
    portfolio = portfolio_overview(
        store_root=reading.root,
        store_present=reading.present,
        positions=reading.positions,
        budget=reading.budget,
        snapshot=reading.snapshot,
    )
    queue = build_queue(opportunities.confirmed, opportunities.candidates)
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
) -> TodayWorkspace:
    """Run one evening's workspace end to end.

    Calls the exact, unmodified `run_market_scan` → `run_setup_for_symbols`
    chain `fmits scan` and `fmits setup` already use, so a row here and a page
    there for the same symbol at the same instant are produced by identical
    code and cannot disagree. Per-symbol failure isolation is inherited
    unchanged: one symbol's outage never stops the run.

    ``read_records=False`` skips the store entirely, which is what
    ``--no-records`` is for — the page still renders, and says that it did not
    look.

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
    reading = (
        read_store(root, at=reference_time, archive_root=archive_root)
        if read_records
        else empty_reading(root)
    )
    return build_today(
        results,
        reading,
        reference_time=reference_time,
        source=f"binance-public · store {root}",
    )
