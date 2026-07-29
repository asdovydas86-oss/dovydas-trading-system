"""Structural trend — the first deterministic consumer of the state history.

One stage, over facts another package already settled:

    StructuralSequenceStateSnapshots -> derive_structural_trend
                                                    -> StructuralTrendType
    StructuralSequenceStateSnapshots -> derive_structural_trend_history
                                                    -> tuple[…TrendSnapshot, ...]

**What a structural trend is here.** A *sustained same-direction structural
shift*: at least `MINIMUM_DIRECTIONAL_SHIFTS` snapshots whose state was the same
directional member, with no opposing directional snapshot between them. Exactly two
of the six `StructuralSequenceStateType` members are directional —
`SHIFTED_HIGHER` and `SHIFTED_LOWER`, the two that say *both* structural sides
moved the same way in price (ADR-0015 §2). Those are the only directional evidence
that exists at this layer, and this package accumulates them and nothing else.

**The four remaining states are transparent.** `EXPANDED` is outward with nothing
inward, `CONTRACTED` is inward with nothing outward, `UNCHANGED` is nothing moved,
and `INSUFFICIENT_STRUCTURE` is a side that does not exist yet. None of them is
evidence *against* a direction, so none advances or invalidates a run. Deciding
that expansion *ends* a trend would be a market claim of exactly the kind ADR-0015
§5 forbids, so this package does not make it — and the cost of that choice is
stated below rather than hidden.

**The threshold is a policy and it is named.** `MINIMUM_DIRECTIONAL_SHIFTS` is 2.
"How many shifts make a trend" has no objective answer; two is the smallest
integer that expresses repetition, and one shift is a single settled fact about one
candle rather than a sequence. It is a module constant and deliberately not a
parameter — see its own docstring.

**Summarising is not forecasting.** `SUSTAINED_HIGHER` says the same two-sided
shift happened more than once and nothing reversed it in between. It is **not** an
uptrend, bullish, strong, momentum, a breakout, a continuation, a reason to buy, or
a prediction, and `SUSTAINED_LOWER` is not a short signal. There is no confidence,
score, strength, rank, probability, duration or magnitude anywhere here, and no
`EvidenceDescriptor` — nothing in this package classifies in ADR-0011 §1's sense,
so `EvidenceFamily.MARKET_STRUCTURE` stays empty.

**Ambiguity is reported, never resolved.** A history whose shifts alternate never
reaches the minimum, and the answer is `NEUTRAL` — not the latest direction.
`NEUTRAL` (evidence exists on both sides and conflicts) and `INDETERMINATE`
(evidence is absent) are kept apart on purpose: folding them together would make a
choppy market indistinguishable from a quiet one.

**Persistence, and the limitation it carries.** A sustained trend survives any
number of non-directional snapshots, and only a single opposing directional shift
invalidates it. So a trend established once and followed by five hundred
contracting snapshots still reads as sustained. That is a real limitation, recorded
plainly: every alternative needs an arbitrary decay constant this layer has no
basis for, and a wrong constant would be invisible.

**Prefix stability — the exact guarantee.** For any snapshot history ``h`` and any
``k``, ``derive_structural_trend_history(h[:k])`` equals
``derive_structural_trend_history(h)[:k]``. Composed with ADR-0016 §6, the trend
history is prefix-stable under **candle-series extension** and under **complete
structural-group extension**: appending later candles, or later whole same-candle
groups, never alters a reading already produced.

It is **not** stable under an arbitrary cut inside a same-candle HIGH/LOW group,
inherited verbatim from ADR-0016 §7 — neither weakened nor repaired here, because
it cannot arise from candle growth and is not detectable. Nothing is claimed across
two different `detect_swings` parameterisations, or across two different values of
`MINIMUM_DIRECTIONAL_SHIFTS`. And the guarantee is that an already-emitted reading
never changes; it is **not** that the trend keeps its value, since a later opposing
shift may invalidate it. See ADR-0017.

**Why this is a sibling package.** Not inside `fmis.market_structure`: ADR-0016 §12
states trend is not that package's job, and its own architecture test forbids the
token there, precisely to hold this line. Not `fmis.features.trend` either: a tuple
of `StructuralTrendSnapshot` dataclasses is not a `FeatureValue`, so it cannot be a
`FeatureResult.value` without being flattened into dictionaries and losing its type
— the same reasoning that made `market_structure` a package rather than a Feature
(ADR-0012). That placeholder remains for indicator-derived trend features. This
placement keeps `market_structure`'s property that only its first stage ever
touches a candle.

Rules for anything added here:
  * **Consume snapshots only.** No `CandleSeries`, no `SwingPoint`, no
    `SwingComparison`, no `StructuralSwing`. If a question needs a candle, it does
    not belong in this package.
  * **Never re-derive anything below.** Detection, comparison, labelling and state
    classification each have exactly one authority, all of them in
    `fmis.market_structure`, and none is re-implemented here.
  * **No interpretation beyond the stated policy.** No BOS, CHoCH, support,
    resistance, protected level, liquidity or sweep; no signal, LONG/SHORT
    recommendation, price prediction, probability or confidence. Summarising a run
    of settled facts is arithmetic over a sequence; calling the result a reason to
    trade is not, and only the first belongs here.
  * **Trend is never an input to a break.** The architecture review §15 fixed the
    ordering: BOS is defined purely on levels, CHoCH over the BOS sequence, and any
    definition making trend an input to either is rejected on sight. This package
    consumes the state history and defines nothing directional for a lower layer.
  * **One authoritative rule per concept**, all private: the directional-state
    mapping (`models._TREND_BY_DIRECTIONAL_STATE`), the fold step
    (`trend._advance`), the classification (`trend._classify`) and the ordering rule
    (`models._validate_snapshot_history_order`). Both public functions share the
    step and the classification, so the two API shapes cannot drift apart.
  * **Validate order, never repair it.** Unsorted input is a caller bug; sorting it
    silently would fold the wrong prefixes together and change the answer.
  * **Keep the accumulator private.** A run length exposed publicly is a confidence
    score by another name, and it would invite threshold-shopping over a policy
    already stated once.
  * **Imports only `fmis.market_structure`.** Never `fmis.data` directly,
    `fmis.decision_support`, `fmis.evidence`, `fmis.providers`, `fmis.pipeline`,
    `fmis.features`, or anything to do with AI, execution, or portfolios — and
    nothing below imports this package.
"""

from __future__ import annotations

from fmis.structural_trend.models import (
    MINIMUM_DIRECTIONAL_SHIFTS,
    StructuralTrendSnapshot,
    StructuralTrendType,
)
from fmis.structural_trend.trend import (
    derive_structural_trend,
    derive_structural_trend_history,
)

__all__ = [
    "MINIMUM_DIRECTIONAL_SHIFTS",
    "StructuralTrendType",
    "StructuralTrendSnapshot",
    "derive_structural_trend",
    "derive_structural_trend_history",
]
