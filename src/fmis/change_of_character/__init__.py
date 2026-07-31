"""Change of character — the first break opposing the last determinate one.

The first layer built on **one** derived fact and nothing else. It consumes the
break-of-structure sequence and reads no candle, no level and no crossing — this
package does not import `fmis.data`, so `Candle` is not a name it can reach, and
its only use of `fmis.level_crossing` is the type name `LevelSide`. Tests enforce
both.

    ContextualSeries[StructureBreak]
                  │
                  ▼  contextual_changes_of_character(breaks)
    ContextualSeries[ChangeOfCharacter]

**What a change of character is here, in full:**

> a **break of structure** whose **side differs** from the side broken at the
> **most recent strictly earlier** break-bearing bar, when that bar broke
> **exactly one** side.

Four conjuncts, each decided separately and each testable:

  1. the subject is a `StructureBreak`, so every break conjunct already holds;
  2. a break-bearing bar exists **strictly earlier** than the subject's;
  3. that bar broke **exactly one** side — the prior character is determinate;
  4. the subject's side **differs** from it.

**This is the first milestone in the chain that adds no primitive and requests
none.** `StructureBreak` already exposes ``index`` and ``side``, which is
everything the rule reads. ADR-0020's deferred question D1 — the confirmation
delay is carried on no derived fact — is inherited and is **not made worse**:
eligibility was resolved one layer down, so this layer takes **no configuration
of any kind** and therefore cannot be misconfigured.

**The predecessor is chosen by bar, not by adjacency, and that is the milestone's
one sharp edge.** ADR-0020 §7 sketched this layer as

    tuple(b for a, b in zip(breaks, breaks[1:]) if a.side is not b.side)

That sketch is **superseded**. Two breaks may share a bar — one upper, one lower —
and ADR-0019 §2.6 and ADR-0020 §3.5 both state that their order is the *level*
ordering, **not** a claim about which happened first. Adjacency would therefore
infer a change of character from an ordering the layer below explicitly refuses to
read as temporal. On a constructible run of ``upper@4 · upper@12 · lower@12`` the
sketch pairs ``upper@12 → lower@12`` — a predecessor on the **same bar** — while
this package pairs ``upper@4 → lower@12``. Both agree bar 12 changed character;
only one can say what it changed *from* without fabricating an intrabar path.

Notably this is **not** a prefix-stability argument: both rules measure 0
violations over 6,400 prefixes. The correction is about correctness, and the
design says so rather than borrowing a stronger-sounding justification.

**A two-sided break bar leaves character indeterminate.** No change is claimed at
the next break bar, because choosing one of that bar's two breaks to be "the"
prior character is the intrabar claim reintroduced one step later. Indeterminacy
**suppresses without persisting** — the next single-sided break bar restores a
determinate character. This is the milestone's principal limitation, named rather
than papered over; resolving it needs sub-bar data this repository does not
ingest.

**Character is the most recent break bar only**, never an accumulated run. Three
consecutive upper breaks give the same character as one. Accumulation is trend's
job and `MINIMUM_DIRECTIONAL_SHIFTS` already owns that idea one package over.

**At most one change per bar**, so output is ordered by the changing bar index
**alone** — total and strictly increasing. Both breaks at a two-sided bar are
tested against the same prior side and they are each other's opposite, so at most
one can differ from it. The consequence is deliberate and load-bearing: **no side
ordering exists anywhere in this package**, so `fmis.structure_break`'s private
side rank is neither imported nor restated.

**Nothing is invalidated.** A change of character is a fact about two closed bars.
There is no "failed CHoCH", no re-arming and no lifecycle — that would be a later
reading over the change sequence.

**No trend is consulted, in either direction.** The market-structure architecture
review §15 fixed the ordering and it stands: **BOS is defined purely on levels,
CHoCH over the BOS sequence, and trend is a summary of both, defining neither.**
Any definition in which trend is an input to CHoCH is rejected on sight, and this
package cannot reach the trend package at all.

**No direction enum, no bullish or bearish.** `ChangeOfCharacter.side` projects
the subject break's side, which already carries the only sense this layer knows.
`UPPER` means the break closed above its level; it does not mean bullish, a
reversal, or a reason to trade. ADR-0019 §D, unchanged through three layers.

**Order-invariant and duplicate-invariant.** Breaks may arrive in any order and
duplicated equal breaks collapse, because the sequence is rebuilt by bar rather
than assumed. Two **distinct** breaks sharing a bar and a side are **rejected** —
picking one would change the character at every later bar without saying so.
Re-validating the break run's canonical order would be a second implementation of
a rule `fmis.structure_break` owns.

**Prefix stability is exact.** Breaks derived from a candle prefix give exactly
the changes of the full run whose index falls inside that prefix, in the same
order — because breaks are exactly prefix-stable and the rule at bar ``i`` reads
only breaks at bars ``<= i``. Measured at 0 violations.

**Identity is carried by reference**, through the single-input wrapper shape.
`require_same_identity` is deliberately not called: there is one subject, and a
one-subject "check" would imply a guarantee that is not happening.

Rules for anything added here:
  * **Never read a candle, a level or a crossing.** Every fact a change needs is
    already on a break. If something here would need a price, it belongs in
    `fmis.level_crossing` or `fmis.structure_break` instead.
  * **Never re-derive.** Swing detection, labelling, level construction, the
    crossing rule, the break rule, the break ordering and identity propagation
    each have exactly one implementation elsewhere, and none is repeated here.
  * **Never consult trend**, and never let trend consult this in a way that makes
    either an input to the other's definition.
  * **No interpretation.** No regime, bias, protected level, inducement,
    liquidity sweep, support, resistance, signal, entry, exit, stop, target,
    size, strength or confidence. Reporting that structure broke the other way is
    arithmetic over two integers and two enum members; calling it a reversal is
    not.
  * **No lifecycle.** No invalidation, no re-arming, no retest tracking.
  * **No configuration.** No threshold, no minimum spacing, no qualifying-side
    policy — a setting makes every historical result non-reproducible without it.
  * **A model may never contradict its own fields.** `ChangeOfCharacter`
    validates that the sides differ and that the previous break is strictly
    earlier, so a change claiming a same-bar or same-side predecessor cannot be
    constructed.
  * **Validate before deriving; reject, never repair.** A conflicting break pair
    raises rather than resolving itself and silently changing every later
    character.
  * **No global mutable state**, no cache, no registry, no wall clock, no
    randomness, no environment dependence.
  * **Imports only `fmis.structure_break` and `fmis.series_context`** — and, for
    the single type name `LevelSide`, `fmis.level_crossing`. Never `fmis.data`,
    never `fmis.market_structure`, never the structural-trend package, never
    `fmis.decision_support`, `fmis.evidence`, `fmis.providers` or
    `fmis.pipeline` — and nothing imports this package.

See ADR-0021 and `docs/design/CHOCH_FOUNDATION_V1.md`.
"""

from __future__ import annotations

from fmis.change_of_character.changes import derive_changes_of_character
from fmis.change_of_character.models import (
    ChangeOfCharacter,
    ChangeOfCharacterError,
    ChangeOfCharacterInputError,
)
from fmis.change_of_character.pipeline import contextual_changes_of_character

__all__ = [
    "ChangeOfCharacter",
    "ChangeOfCharacterError",
    "ChangeOfCharacterInputError",
    "derive_changes_of_character",
    "contextual_changes_of_character",
]
