"""The priority queue, and the reason it is not a ranking.

    build_queue(confirmed, candidates)  ──►  PriorityQueue

**What the queue orders by, in full, with nothing else in it:**

1. The engine's own readiness state — every `CONFIRMED` result, then every
   `CANDIDATE` result. This is the grouping `fmis.swing_setup.scan_report`
   already applies to the identical results, so the two surfaces cannot
   disagree about what is actionable.
2. Within a state, **the order the watchlist was scanned in**, unchanged.

**What it never orders by:** risk/reward, stop distance, target distance,
direction, confidence, probability, warning count, or any combination of them.
There is no sort key anywhere in this module and no comparison between two
opportunities. A test plants a high-R:R `CANDIDATE` ahead of a low-R:R
`CONFIRMED` result and asserts the queue's order is exactly the input order
within each group — the same test `fmis.swing_setup.scan` already carries for
its own `TOP OPPORTUNITIES` section, and for the same reason:

    let the owner rank by risk/reward... This attack requires no adversary; it
    happens by default.

**Blocked entries leave the queue rather than sinking in it.** An entry the
system refuses to size is not a worse opportunity — it is one no number can be
produced for, which is a different statement. Putting it at the bottom of one
list would make refusal look like low rank; putting it in its own list, with the
refusal named, makes it what it is. That is also why `PriorityQueue` has two
tuples and not one with a flag.

**Readiness is not desirability, and the queue says so on the page.** A
`CONFIRMED` setup has satisfied one more of the engine's own conditions than a
`CANDIDATE`; it is not a better trade, and no measurement in this repository
claims it is. `PriorityQueue.ordering` carries that sentence to every consumer.
"""

from __future__ import annotations

from collections.abc import Sequence

from fmis.today.models import (
    OpportunityLine,
    PriorityQueue,
    QueueEntry,
    WarningSeverity,
)
from fmis.today.warnings import warnings_for_opportunity

__all__ = ["ORDERING_RULE", "build_queue"]

#: The rule, stated once and carried on the object rather than printed by the
#: renderer alone — so a future JSON or Telegram consumer inherits it too.
ORDERING_RULE = (
    "Attention order, never desirability: confirmed setups before candidates "
    "(the engine's own readiness state), then watchlist order within each "
    "group. Nothing here is sorted by risk/reward, and readiness is not a "
    "claim that one setup is better than another."
)


def _entry(opportunity: OpportunityLine) -> QueueEntry:
    """One setup with its rules applied, split into the two registers."""
    raised = warnings_for_opportunity(opportunity)
    return QueueEntry(
        opportunity=opportunity,
        warnings=tuple(
            warning
            for warning in raised
            if warning.severity is not WarningSeverity.BLOCK
        ),
        blocked_by=tuple(
            warning for warning in raised if warning.severity is WarningSeverity.BLOCK
        ),
    )


def _require_lines(value: Sequence[OpportunityLine], name: str) -> tuple[OpportunityLine, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{name} must be a non-string sequence")
    for position, item in enumerate(value):
        if not isinstance(item, OpportunityLine):
            raise TypeError(
                f"{name}[{position}] must be an OpportunityLine, got "
                f"{type(item).__name__}"
            )
    return tuple(value)


def build_queue(
    confirmed: Sequence[OpportunityLine],
    candidates: Sequence[OpportunityLine],
) -> PriorityQueue:
    """Assemble the attention queue from the two actionable groups.

    Both arguments arrive in scan order and leave in scan order. This function
    performs exactly one reordering, and it is the partition between entries
    that carry a refusal and entries that do not — never a reordering *within*
    either side, which is why a stable single pass over the concatenation is
    used rather than any sort.

    Raises:
        TypeError: either argument is not a sequence of `OpportunityLine`.
    """
    ordered = _require_lines(confirmed, "confirmed") + _require_lines(
        candidates, "candidates"
    )
    entries = tuple(_entry(opportunity) for opportunity in ordered)
    return PriorityQueue(
        needs_attention=tuple(entry for entry in entries if not entry.is_blocked),
        blocked=tuple(entry for entry in entries if entry.is_blocked),
        ordering=ORDERING_RULE,
    )
