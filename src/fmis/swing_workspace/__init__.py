"""The Swing Decision Workspace — one page, arranged for one decision.

    fmits workspace

**What it is.** The operator's page: what the market is doing, what is already
held, what has confirmed, what is waiting on its confirmation, what the engines
concluded is no trade and why, what the simulator is running, what the recorded
book is worth, whether any of it has worked, and everything qualifying the rest.

**What it adds to `fmits today`, and it is exactly one thing:** a *decision
order*. The day's page refuses to order actionable setups by anything but scan
order, because ordering by a property of the analysis reads as ordering by
quality. This page orders them and pays for it in full — the ordering is a
lexicographic key over four named components, each one a state an engine already
decided, each printed on the row it placed. Two adjacent rows can be compared
component by component without reading any code, and nothing in this package
multiplies, weights, sums or scales anything.

**What it is not.** A second engine. `fmis.swing_workspace` computes no market
quantity, no monetary quantity and no statistic. Every figure on the page was
produced by an engine below it or folded from a record, and the composition root
runs **one** scan, **one** store read, **one** valuation and **one** approval
pass by delegating to `fmis.today.assemble_today` — so a figure here and the same
figure on `fmits today` are one calculation rendered twice.

**Rules for anything added here:**

  * **Compose, never compute.** If a value needs arithmetic, it belongs in the
    package that owns the quantity, and this one calls it.
  * **Every section is an existing engine's output, re-sectioned.** The three
    per-setup attachments — evidence digest, stable identity, paper status —
    are one call each to `fmis.setup_evidence`, `fmis.setup_observation` and the
    already-folded paper views.
  * **No score, weight, confidence, probability or rank** in a value, a field
    name or metadata. A rank *position* is the index of a row in a tuple.
  * **No direction is named in this package's source.** ADR-0028's boundary:
    values are carried at runtime, never spelled here.
  * **Nothing is written.** No store verb appears anywhere in the package, and a
    guard asserts it.
"""

from __future__ import annotations

from fmis.swing_workspace.builder import (
    SWING_WORKSPACE_LIMITATIONS,
    build_swing_workspace,
    run_swing_workspace,
)
from fmis.swing_workspace.models import (
    SWING_WORKSPACE_SCHEMA_VERSION,
    BookExposure,
    EvidenceDigest,
    GlobalSummary,
    NoTradeGroup,
    PaperPosition,
    RankComponent,
    RankKey,
    RankedSetup,
    SwingWorkspace,
    SwingWorkspaceError,
    UnanalysedSymbol,
)
from fmis.swing_workspace.ranking import (
    APPROVAL_ORDER,
    EXCLUDED_FROM_RANKING,
    RANK_KEYS,
    RANKING_RULE,
    READINESS_ORDER,
    SUFFICIENCY_ORDER,
    UNSTATED,
    rank_key_for,
    rank_setups,
)
from fmis.swing_workspace.render import (
    WORKSPACE_PAGE_WIDTH,
    render_swing_workspace,
)
from fmis.swing_workspace.sections import (
    BOOK_AXIS,
    ONE_READING_GAP_BARS,
    PAPER_LIVE_STATES,
    aggregated_warnings,
    books_from,
    evidence_digest_for,
    global_summary,
    holding_for,
    identity_ref_for,
    no_trade_groups,
    paper_positions,
    paper_status_for,
    ranked_setups,
    require_actionable_split,
    risk_state_of,
    unanalysed_from,
)

__all__ = [
    # the model
    "SWING_WORKSPACE_SCHEMA_VERSION",
    "SwingWorkspace",
    "SwingWorkspaceError",
    "GlobalSummary",
    "RankedSetup",
    "RankKey",
    "RankComponent",
    "EvidenceDigest",
    "NoTradeGroup",
    "UnanalysedSymbol",
    "PaperPosition",
    "BookExposure",
    # the ordering
    "RANKING_RULE",
    "RANK_KEYS",
    "EXCLUDED_FROM_RANKING",
    "READINESS_ORDER",
    "APPROVAL_ORDER",
    "SUFFICIENCY_ORDER",
    "UNSTATED",
    "rank_key_for",
    "rank_setups",
    # sections
    "ONE_READING_GAP_BARS",
    "BOOK_AXIS",
    "PAPER_LIVE_STATES",
    "identity_ref_for",
    "evidence_digest_for",
    "paper_status_for",
    "holding_for",
    "ranked_setups",
    "no_trade_groups",
    "unanalysed_from",
    "paper_positions",
    "books_from",
    "risk_state_of",
    "global_summary",
    "aggregated_warnings",
    "require_actionable_split",
    # composition and rendering
    "SWING_WORKSPACE_LIMITATIONS",
    "build_swing_workspace",
    "run_swing_workspace",
    "render_swing_workspace",
    "WORKSPACE_PAGE_WIDTH",
]
