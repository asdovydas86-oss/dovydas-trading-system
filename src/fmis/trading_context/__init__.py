"""Trading analysis context — what a *trading* analysis is scoped to.

A tiny, self-contained domain vocabulary: `TradingObjective` (swing or day
trading) and `TradingAnalysisContext` (the timeframes and reference points a
trading analysis was set up with). Descriptive input for a future trading
reasoning layer, and nothing else.

    fmis.data / fmis.features / fmis.relative_value    shared deterministic engines
        v
    fmis.pipeline            -> AnalysisSnapshot
        v
    fmis.decision_support    -> EvidenceReport
        v
    future trading reasoning <- fmis.trading_context (this package: descriptive input)

**Shared calculations do not imply shared decision logic.** An EMA is an EMA
whoever is looking at it, so every objective — and, later, long-term investing —
reuses the same deterministic engines. What a 50-period EMA *means* is not
shared: it is the swing trader's trend reference, the day trader's slow
background, and the investor's near-irrelevance. This package exists so that
distinction has somewhere to live before any layer starts interpreting.

**Long-term investing is not a trading objective and is deliberately absent.**
It rests on thesis, fundamentals, valuation, catalysts, risks and portfolio
construction; it will be a separate application module with its own context
type, reusing the shared engines and none of the trading interpretation. See
ADR-0009.

Rules for anything added here:
  * **No behaviour.** These are value objects. No calculation, no selection, no
    ranking, no interpretation, and specifically no timeframe presets or
    automatic timeframe choice — a context records what was chosen, it does not
    choose.
  * **The objective is never inferred**, least of all from a timeframe: a 4h
    chart belongs to swing and day traders alike, and guessing would silently
    decide the very thing the caller is stating.
  * **No objective-dependent branching**, here or anywhere in this package. Per
    objective behaviour belongs to the layer that has behaviour, and a test
    asserts no enum member is referenced outside its own definition.
  * **Imports nothing from `fmis`.** Not the pipeline, not decision support, not
    providers, not an engine — this is a leaf that higher layers depend on, and
    the direction never reverses.
  * No fields for direction, entry, stop, target, size, leverage, risk, holding
    period, allocation, confidence, or strategy. Those need modules that can
    define and test them; a placeholder invites treating a blank as a decision.
"""

from __future__ import annotations

from fmis.trading_context.context import TradingAnalysisContext, TradingObjective

__all__ = ["TradingObjective", "TradingAnalysisContext"]
