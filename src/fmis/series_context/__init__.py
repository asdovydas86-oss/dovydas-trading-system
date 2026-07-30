"""Series context — identity that survives a deterministic pipeline.

    CandleSeries            ──► contextual_structural_swings
                                        │  ContextualSeries[StructuralSwing]
                                        ▼
                                contextual_structural_state_history
                                        │  ContextualSeries[…StateSnapshot]
                                        ▼
                                contextual_structural_trend_history
                                        │  ContextualSeries[…TrendSnapshot]
                                        ▼
                                require_same_identity(...)  ──► SeriesIdentity

**The problem this closes.** `CandleSeries` has always known which series it is —
`symbol` and `timeframe`, validated per candle. Every stage after `detect_swings`
forgot: a `SwingPoint`, a `StructuralSequenceStateSnapshot` and a
`StructuralTrendSnapshot` carry no identity at all. So two instruments' histories,
or two timeframes of one instrument, could be concatenated and every deterministic
function in the repository would accept the result and answer confidently.

That is measured, not feared: a BTCUSDT 4h series and an ETHUSDT 4h series built
from identical OHLC rows produce **byte-identical** trend histories. Nothing
downstream could tell them apart, because there was nothing to tell apart with.

**What this package adds, and what it deliberately does not.** It adds propagation,
not definition. `SeriesIdentity` lives in `fmis.data`, next to the `CandleSeries`
that already owned the pair, and `CandleSeries.identity` is a projection rather than
a second copy — so identity has exactly one source and cannot drift. This package
carries that identity through the existing pipeline and refuses to combine two of
them.

**Identity sits beside the values, never inside them.** A `ContextualSeries` holds
one identity for the whole series and a payload that is *exactly* what the
context-free function returned. No analytical function ever sees an envelope, and
no element ever grows an identity field, so adding context **cannot change a
result** — proved by equivalence tests across every fixture class, not asserted.

**Nothing analytical is re-implemented.** Swing detection, comparison, labelling,
sequence grouping, structural-state derivation, trend derivation, ordering
validation, outside-bar atomicity and prefix stability keep their single
implementation in `fmis.market_structure` and `fmis.structural_trend`. The wrappers
unwrap, delegate, and re-wrap. AST tests forbid this package from performing
arithmetic, reading a candle field, or naming a state or trend member.

**Two categories of API, stated explicitly.**

*Context-free primitives* — `detect_swings`, `compare_swing_sequence`,
`label_swing_sequence`, `derive_structural_sequence_state_history`,
`derive_structural_trend_history` and the rest — remain public and unchanged. They
are **not deprecated**: they are the arithmetic, and arithmetic does not need a
passport. Their permitted scope is unit-level computation over values already known
to come from one series. What they never promised, and still do not, is to notice
that they were handed two.

*Safe pipeline boundary* — everything exported here. These carry identity, preserve
it exactly, and reject mismatches. **A future candle-derived module enters the
pipeline here.**

**No normalization, ever, and the direction of that error is deliberate.**
`"BTCUSDT"` ≠ `"btcusdt"` ≠ `" BTCUSDT"`; `"4h"` ≠ `"4H"` ≠ `"240m"`. This is
inherited policy, not a new decision — the evidence-descriptor layer records why
identity strings are rejected rather than rewritten, and the trading-analysis
context layer records that a timeframe label is opaque until a canonical vocabulary
exists. So this contract **over-rejects**: two spellings of one series will not
combine. Over-rejection is safe; under-rejection is the silent mixing being
prevented. Normalize before building candles, where ingestion already owns the
boundary.

**How Level-Crossing Foundation consumes this.** It needs a `CandleSeries` *and* a
derived swing series, and must prove they describe the same series before comparing
a price to a level. One call does it:

    identity = require_same_identity(candle_series, contextual_swings)

`require_same_identity` accepts a `CandleSeries` (through its projection) and a
`ContextualSeries` (through its field) interchangeably, so both sides are covered by
one check and Level-Crossing needs no identity logic of its own. It can do this
**without importing `fmis.structural_trend`**: this contract sits below trend.

Rules for anything added here:
  * **Delegate, never re-derive.** Every analytical rule already has exactly one
    implementation elsewhere. If a change here would need arithmetic, it belongs in
    the layer that owns the rule.
  * **Identity is carried by reference, never rebuilt.** A reconstructed equal
    identity passes every `==` test while severing the link to the series the
    payload came from.
  * **No API may accept an identity argument.** The only place identity may come
    from is the input, which makes silent substitution unrepresentable rather than
    merely discouraged.
  * **Never infer identity.** Not from prices, not from timestamps, not from a
    default, not from a registry.
  * **No global mutable state.** No ambient "current series", no cache, no registry,
    no thread-local. Identity is passed, not looked up.
  * **Reject, never repair.** A mismatch raises; it is never warned about, resolved
    by picking a side, or fixed by normalizing.
  * **No trading logic.** No level crossing, protected level, BOS, CHoCH, regime,
    signal, entry, exit or size. This package moves a label around; it decides
    nothing about markets.
  * **Imports only `fmis.data`, `fmis.market_structure` and `fmis.structural_trend`**
    — and nothing imports this package.

See ADR-0018.
"""

from __future__ import annotations

from fmis.series_context.models import (
    ContextualSeries,
    SeriesContextError,
    SeriesIdentityMismatchError,
    require_same_identity,
)
from fmis.series_context.pipeline import (
    contextual_structural_state_history,
    contextual_structural_swings,
    contextual_structural_trend_history,
)

__all__ = [
    "ContextualSeries",
    "SeriesContextError",
    "SeriesIdentityMismatchError",
    "require_same_identity",
    "contextual_structural_swings",
    "contextual_structural_state_history",
    "contextual_structural_trend_history",
]
