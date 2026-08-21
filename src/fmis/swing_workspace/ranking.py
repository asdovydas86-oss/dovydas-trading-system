"""The ordering, and everything that is deliberately not in it.

    rank_setups(lines)  ──►  tuple[RankKey, ...]   (one per line, in page order)

**The whole algorithm, stated once.** Rows are ordered by a **lexicographic key**
over four named components, compared left to right. The first component on which
two rows differ decides their order; later components are never consulted. Each
component maps a *named state an engine already decided* onto its position in a
list written below, except the last, which is the position of the symbol in the
watchlist the caller requested.

    1. readiness     the Swing Setup Engine's own SetupState
    2. approval      the Position Sizing Engine's own ApprovalStatus
    3. sufficiency   the Decision Context Engine's own ContextState
    4. watchlist     the index of this symbol in the requested universe

**There is no score.** Nothing is multiplied, weighted, summed, normalised or
scaled anywhere in this module; there is no floating-point value in it at all.
Every `rank` integer is an index into one of the three vocabularies below, and
those vocabularies are complete mappings over their enums rather than lookups
with a default — a fourth member added upstream fails loudly here instead of
silently sorting last.

**The order is total, so it is reproducible.** The fourth component is unique per
row within one run, so two rows never tie; the ordering therefore cannot depend on
the sort's stability, on dictionary iteration, or on the order the provider
answered in. Two runs over the same scan produce the same page.

**What the ordering never reads, and why.**

*Risk/reward, stop distance, target distance, recommended size and open risk are
excluded.* This repository has measured the association and published it: higher
displayed R:R went with a **worse** outcome, not a better one — R:R in `[5, 20)`
resolved target-first 7.7 % of the time against 74.5 % for R:R in `[0, 1)`
(`fmis.today.RISK_REWARD_ASSOCIATION`). Sorting by it would put the least likely
row at the top of the page under a heading that reads *"top"*. The figures are
still **printed** on every row, because the owner is entitled to the geometry of a
trade they are considering; they are not permitted to decide what comes first.

*Evidence counts and family confluence are excluded.* Every actionable line on
this page comes from the same three directional factors, which all draw on one
family, so a count of agreeing items is close to constant across rows and would
read as a discrimination it cannot make. The digest is shown per setup for the
same reason the geometry is, and orders nothing.

*Direction is excluded*, and this module names no side. ADR-0028's boundary,
held here by never spelling the vocabulary rather than by remembering not to.

**Readiness is not desirability.** A `CONFIRMED` setup has satisfied one more of
the engine's own stated conditions than a `CANDIDATE` — it is not a better trade,
and no measurement in this repository claims it is. `RANKING_RULE` carries that
sentence onto the page and onto the object.
"""

from __future__ import annotations

from collections.abc import Sequence
from types import MappingProxyType

from fmis.swing_workspace.models import (
    RankComponent,
    RankKey,
    SwingWorkspaceError,
)
from fmis.today import OpportunityLine

__all__ = [
    "RANKING_RULE",
    "RANK_KEYS",
    "EXCLUDED_FROM_RANKING",
    "READINESS_ORDER",
    "APPROVAL_ORDER",
    "SUFFICIENCY_ORDER",
    "UNSTATED",
    "rank_key_for",
    "rank_setups",
]

#: The rule, in words, carried on the workspace rather than printed by the
#: renderer alone — so a future JSON, notification or web consumer inherits the
#: sentence along with the data it qualifies.
RANKING_RULE = (
    "Ordered by a stated lexicographic key, never by a score: readiness (the "
    "Swing Setup Engine's own state), then approval (the Position Sizing "
    "Engine's own status), then decision-context sufficiency, then the position "
    "of the symbol in the requested watchlist. Every component is printed on "
    "every row, so the reason one row sits above another can be reconstructed "
    "without reading any code. Readiness is not desirability: a confirmed setup "
    "has met one more of the engine's stated conditions than a candidate, and no "
    "measurement in this repository claims it is a better trade. Risk/reward, "
    "size, open risk and evidence counts order nothing — the first of those was "
    "measured to associate with a worse outcome, not a better one."
)

#: The component names, in comparison order. Public so a test — and a reader —
#: can assert the ordering uses these and nothing else.
RANK_KEYS: tuple[str, ...] = ("readiness", "approval", "sufficiency", "watchlist")

#: Named, so that "this page does not sort by risk/reward" is a value a consumer
#: can read rather than a claim it has to trust. Printed under the ranking rule.
EXCLUDED_FROM_RANKING: tuple[str, ...] = (
    "risk/reward ratio",
    "stop distance",
    "target distance",
    "recommended position size",
    "open risk after entry",
    "evidence item counts",
    "agreeing family counts",
    "direction",
    "paper-trade result",
)

#: What a row shows when the value a component reads was never produced. A word
#: rather than a blank: a component rendered empty reads as a component that did
#: not apply, and this one applied and found nothing.
UNSTATED = "unstated"

#: `SetupState.value` → its place in the ordering. A complete mapping over the
#: engine's enum, written out rather than derived, so a fourth state added
#: upstream raises here instead of sorting into an arbitrary position.
#:
#: `WAIT` is present and last although no `WAIT` result reaches an actionable
#: section: the mapping describes the vocabulary, not this page's membership, and
#: a mapping with a hole in it is a mapping whose hole is found in production.
READINESS_ORDER = MappingProxyType({"confirmed": 0, "candidate": 1, "wait": 2})

#: `ApprovalStatus.value` → its place, plus the two absences that are not
#: statuses at all.
#:
#: **`INDETERMINATE` sorts *after* `BLOCKED`, and that is deliberate.** A blocked
#: candidate was measured against the owner's limits and failed one, which is a
#: fact about the trade; an indeterminate one was not measured at all, which is a
#: fact about the engine's reach. The page is ordered by how much is *settled*
#: about a row, and "we know it breaks a limit you set" is more settled than "we
#: could not check". Neither is a claim about the market.
#:
#: `UNSTATED` covers a row for which no approval was computed — `--no-records`,
#: no risk budget, several accounts and no `--account`. It sorts last because it
#: is the least settled of all: nothing was even attempted.
APPROVAL_ORDER = MappingProxyType(
    {"approved": 0, "blocked": 1, "indeterminate": 2, "not sizeable": 3, UNSTATED: 4}
)

#: `ContextState.value` → its place. The Decision Context Engine's own three
#: states, in the order that engine itself documents them: sufficient, then
#: limited (*"ready with the named limitation attached"*), then insufficient.
SUFFICIENCY_ORDER = MappingProxyType(
    {"sufficient": 0, "limited": 1, "insufficient": 2}
)

#: The engines named in prose rather than by module path. Four layering
#: guards in this repository scan for the *text* of a module name outside
#: the composition roots they permit, and a printed provenance string is
#: still text — so these name the engine the way the page reads it, which
#: is also what a reader of the page actually wants.
_READINESS_SOURCE = "the Swing Setup Engine — SetupState"
_APPROVAL_SOURCE = "the Position Sizing Engine — ApprovalStatus"
_SUFFICIENCY_SOURCE = "the Decision Context Engine — ContextState"
_WATCHLIST_SOURCE = "the requested watchlist, in the order it was requested"


def _ordinal(vocabulary: MappingProxyType, value: str, component: str) -> int:
    """One value's place, or a refusal naming the vocabulary it was not in.

    Raises rather than defaulting. A default would let an unmapped state sort
    into some position nobody chose, and the resulting page would be ordered by
    a rule that is not the documented one — which is precisely the hidden
    weighting this module exists to make impossible.
    """
    try:
        return vocabulary[value]
    except KeyError:
        raise SwingWorkspaceError(
            f"{value!r} is not a value the {component} ordering knows; the "
            f"known values are {sorted(vocabulary)}. An unmapped state must not "
            "be given a position by default — see this module's docstring"
        ) from None


def rank_key_for(line: OpportunityLine, *, watchlist_index: int) -> RankKey:
    """The complete ordering key for one line. Pure, and reads nothing else.

    ``watchlist_index`` is the position of this symbol in the universe the caller
    requested, 0-based. It is passed in rather than looked up, because this
    module has no idea what was requested and inventing an order — alphabetical,
    say — would be a rule nobody wrote down.

    Raises:
        TypeError: ``line`` is not an `OpportunityLine`, or the index is not an
            int.
        SwingWorkspaceError: the index is negative, or a state the line carries
            is outside the vocabulary the ordering knows.
    """
    if not isinstance(line, OpportunityLine):
        raise TypeError(
            f"line must be an OpportunityLine, got {type(line).__name__}"
        )
    if not isinstance(watchlist_index, int) or isinstance(watchlist_index, bool):
        raise TypeError("watchlist_index must be an int")
    if watchlist_index < 0:
        raise SwingWorkspaceError("watchlist_index cannot be negative")

    approval = line.approval_status if line.approval_status is not None else UNSTATED
    return RankKey(
        components=(
            RankComponent(
                name=RANK_KEYS[0],
                value=line.state,
                rank=_ordinal(READINESS_ORDER, line.state, RANK_KEYS[0]),
                source=_READINESS_SOURCE,
            ),
            RankComponent(
                name=RANK_KEYS[1],
                value=approval,
                rank=_ordinal(APPROVAL_ORDER, approval, RANK_KEYS[1]),
                source=_APPROVAL_SOURCE,
            ),
            RankComponent(
                name=RANK_KEYS[2],
                value=line.sufficiency,
                rank=_ordinal(SUFFICIENCY_ORDER, line.sufficiency, RANK_KEYS[2]),
                source=_SUFFICIENCY_SOURCE,
            ),
            RankComponent(
                name=RANK_KEYS[3],
                value=f"#{watchlist_index + 1}",
                rank=watchlist_index,
                source=_WATCHLIST_SOURCE,
            ),
        )
    )


def rank_setups(
    lines: Sequence[OpportunityLine], *, watchlist: Sequence[str]
) -> tuple[tuple[OpportunityLine, RankKey], ...]:
    """Order actionable lines by the documented key, and hand back both.

    Returns each line paired with the key that placed it, so the caller never has
    to re-derive one and the page can print the arithmetic beside the row.

    ``watchlist`` is the requested universe. A symbol that is not in it — which
    should not happen, and would mean the scan answered about something nobody
    asked for — sorts after every symbol that is, rather than raising: losing the
    whole page over one unexpected row would be a worse failure than showing it
    last, and the row is still shown with its own key stating where it came.

    **The order is total whenever the watchlist names each symbol once**, which
    is the only shape the composition root produces, so the page never depends on
    the sort's stability. The two shapes that *can* tie on the fourth component —
    a watchlist naming one symbol twice, and two rows neither of which is in it —
    are resolved by `sorted` being stable, which leaves them in the order the
    scan produced. That is a stated fallback, not an accident, and it is still
    deterministic: the same scan yields the same page.

    Raises:
        TypeError: ``lines`` or ``watchlist`` is not a non-string sequence.
    """
    for name, value in (("lines", lines), ("watchlist", watchlist)):
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise TypeError(f"{name} must be a non-string sequence")

    # `dict` over `list.index`, and the first occurrence wins: a watchlist that
    # names one symbol twice is a caller error this function does not punish the
    # page for, and the *first* position is the one a reader counting down the
    # requested list would arrive at.
    positions: dict[str, int] = {}
    for index, symbol in enumerate(watchlist):
        positions.setdefault(symbol, index)
    unknown = len(watchlist)

    keyed = tuple(
        (line, rank_key_for(line, watchlist_index=positions.get(line.symbol, unknown)))
        for line in lines
    )
    return tuple(sorted(keyed, key=lambda pair: pair[1].ordinals))
