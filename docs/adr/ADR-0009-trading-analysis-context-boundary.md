# ADR-0009 — Trading analysis context, and the trading/investing boundary

**Status:** Accepted
**Date:** 2026-07-28
**Decides:** an explicit context for *trading* analysis, and that long-term investing is not one of its
objectives (Milestone S)
**Implemented by:** `feat(trading_context): add trading analysis context v1`
**Relates to:** [ADR-0008](ADR-0008-decision-support-evidence-boundary.md) (evidence, the layer trading
reasoning will consume); [ADR-0006](ADR-0006-provider-adapter-contract.md) §6 (timeframe labels are
provider-native; no canonical vocabulary exists); `PROJECT_SPECIFICATION_V1.md` §4

---

## Context

The system now produces facts (`AnalysisSnapshot`) and organises them into evidence (`EvidenceReport`).
The next layer interprets that evidence — and interpretation is the first point where *who is asking*
changes the answer. A 4-hour EMA cross is a primary event to a swing trader, background texture to a day
trader, and close to noise to a long-term investor. The measurement is identical in all three cases; the
meaning is not.

Nothing in the system currently records who is asking. Without that, a reasoning layer would have to
infer it — from the timeframe, or from a default — and an inferred objective is an invisible assumption
sitting underneath every conclusion drawn from it.

A second problem is more structural. It is tempting to treat long-term investing as simply the slowest
trading objective, one more enum member alongside swing and day. That framing is wrong in a way that
would be expensive to undo later, and this ADR settles it before any reasoning code exists.

## Decisions

### 1. A trading analysis states its objective explicitly, in its own value object
`fmis.trading_context` holds `TradingObjective` and `TradingAnalysisContext`: what kind of trading is in
view, which timeframe is primary, which are supporting, an optional benchmark, and optional notes. It is
descriptive input — no behaviour, no calculation, no selection.

It is a leaf: it imports **nothing** from `fmis`. Higher layers depend on it, never the reverse. That
keeps it usable by any future reasoning module without dragging the pipeline or an engine along.

### 2. Swing trading and day trading are separate objectives
They are different activities, not points on a dial: different timeframes, different holding horizons,
different tolerance for the same observation. Collapsing them into one "trading" value would force every
future rule to re-derive the distinction from timeframes, which is the inference this ADR exists to
prevent. Two explicit members cost nothing now and keep the difference visible.

### 3. Long-term investing is **not** a trading objective, and is deliberately absent
There is no `LONG_TERM_INVESTMENT` member, and a test asserts there never quietly becomes one.

Investing is not slow trading. It rests on an investment thesis, fundamentals, valuation, catalysts,
risks, and portfolio construction — none of which a trading objective implies, and none of which this
system has. Adding the member would be a one-word change that silently commits every future trading rule
to being applied to investment decisions, because the enum is what reasoning layers will branch on.

Long-term investing will be its own application module, with its own context type, its own
interpretation, and its own decision records. Technical entry timing may well be part of it — an
investor still chooses when to buy — but that is a *component* of an investment process, not evidence
that investing belongs inside the trading vocabulary.

### 4. Shared calculations do not imply shared decision logic
This is the boundary the whole ADR protects. `fmis.data`, `fmis.features`, `fmis.alignment` and
`fmis.relative_value` are deterministic and objective-agnostic: an EMA is an EMA whoever is looking at
it, and every objective — including, later, investing — reuses them unchanged. That reuse is the point of
keeping the engines free of interpretation.

What must **not** be shared is what those numbers mean. Interpretation stays module-specific: trading
reasoning reads `TradingAnalysisContext`, investment reasoning will read its own context, and neither
inherits the other's rules by accident. Sharing an EMA is not sharing a conclusion.

### 5. The objective is never inferred, least of all from a timeframe
No mapping from timeframe to objective, in either direction. A 4h chart belongs to swing and day traders
alike; a 1h chart is a day trader's primary and a swing trader's supporting view. Inferring would decide
the exact thing the caller is stating, invisibly, and would then be very hard to notice being wrong.

Correspondingly, the context never selects, defaults, reorders, or recommends a timeframe. It records
what was chosen. Supporting timeframes keep the order supplied, because that order is the caller's stated
priority and not the system's to improve.

### 6. No objective-dependent behaviour in this package
There is no `if objective == ...` anywhere, and a test asserts no enum member is referenced outside its
own definition. Per-objective behaviour belongs to the layer that has behaviour; putting even one branch
here would make a value object quietly authoritative about interpretation.

### 7. No strategy rules, presets, or timeframe heuristics yet
No timeframe presets per objective, no automatic selection, no risk/position/entry/stop/target/direction/
confidence fields. Every one of those needs a module that can define and test it; a placeholder field
invites a caller to read an unfilled value as a decision. A test pins the field list to exactly the five
that exist.

### 8. Timeframes are `str`, because no canonical timeframe type exists
`Candle.timeframe`, `CandleSeries.timeframe` and `ObservationSeries.frequency` are all plain `str`. The
only interval vocabulary in the repository is Binance's `KLINE_INTERVALS`, which ADR-0006 §6 records as
provider-native precisely because a canonical vocabulary has not been decided. Importing it here would
break this package's dependency rules *and* freeze one exchange's spelling as canonical.

So a timeframe is a `str` and its syntax is **not** validated. What is checked is only what can be
checked without inventing a vocabulary: presence, non-blankness, no duplicates, and that the primary is
not also listed as supporting. Comparison is exact, so `"4h"` and `"4H"` are distinct labels — consistent
with the rest of the system treating a timeframe as opaque. When a canonical timeframe type arrives, this
is one of the first places to adopt it.

### 9. Not integrated with the pipeline in this milestone
`analyze_symbol` does not take a context, and `AnalysisSnapshot` does not carry one. Nothing in the
pipeline would read it: the pipeline fetches and computes, and both are objective-agnostic by design.
Attaching it now would create a field that is stored and never consulted — the kind of dead optional
field that later gets mistaken for something meaningful, and that makes the pipeline *look* as though it
branches on objective when it must not.

The context is a standalone value object until a trading reasoning layer exists to consume it. That layer
will take an `EvidenceReport` and a `TradingAnalysisContext` together, which is the first point where
both are genuinely needed.

## Alternatives considered

- **Add `LONG_TERM_INVESTMENT` to `TradingObjective`.** Rejected: see §3. It is the change this ADR
  exists to prevent, and its cost is invisible until trading rules have already been applied to
  investment decisions.
- **One `TRADING` objective, distinguishing swing from day by timeframe.** Rejected: it is inference by
  another name, and it makes every future rule re-derive the distinction.
- **Timeframe presets per objective** (e.g. swing → 1d/4h). Rejected: a heuristic dressed as a
  convenience. It would make the module choose, which is exactly what §5 forbids, and it is untestable
  against anything but taste.
- **Validate timeframe syntax against a pattern.** Rejected: any pattern is an invented canonical
  vocabulary, and ADR-0006 deliberately left that undecided.
- **Attach the context to `AnalysisSnapshot`.** Rejected: see §9 — a dead optional field.
- **Put the context inside `fmis.pipeline` or `fmis.decision_support`.** Rejected: both are consumers of
  it, not owners; a leaf with no dependencies is usable by future modules that neither of them anticipate.

## Consequences

- Trading reasoning, when it is built, receives its objective explicitly and cannot silently assume one.
- The trading/investing split is settled in code, not just in prose: the enum has no investing member and
  a test enforces it.
- A future long-term investing module gets its own package and context, reuses the shared deterministic
  engines, and shares none of the trading interpretation. It will need its own ADR.
- The context is currently unused by any layer. That is expected for a value object introduced ahead of
  its consumer, and is preferable to speculative integration — but it does mean the type will get its
  first real exercise when trading reasoning lands, and may need additive fields then.
- `notes` is free text and deliberately unstructured. If it starts carrying meaning that code reads, that
  is the signal a real field is missing.
