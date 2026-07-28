# ADR-0011 — Evidence taxonomy: a calculated indicator is not automatically evidence

**Status:** Accepted
**Date:** 2026-07-28
**Decides:** a shared vocabulary for what evidence is *about*, and the rule for what earns a place in it
(Milestone U)
**Implemented by:** `feat(evidence): add evidence taxonomy v1`
**Relates to:** [ADR-0008](ADR-0008-decision-support-evidence-boundary.md) (the layer that observes and
classifies); [ADR-0009](ADR-0009-trading-analysis-context-boundary.md) (shared calculations do not imply
shared decision logic); [ADR-0010](ADR-0010-volume-foundation.md) (volume is measured, its
interpretation deferred)

---

## Context

The system now computes a lot and interprets a little. `fmis.features` produces EMA, RSI, ATR, MACD and
relative volume; `fmis.relative_value` produces five metrics; `fmis.decision_support` classifies a subset
of them into observations. There is no shared word for *what a piece of evidence is about* — nothing that
lets a trading module, a future investing module, and a future macro module say "this is momentum
evidence" in the same vocabulary.

The temptation, when adding such a vocabulary, is to enumerate every indicator the system computes and
call the list "evidence". That would be wrong in a way that compounds: it would assert that anything
calculated is interpretation-ready, and every later layer would inherit the assumption.

## Decisions

### 1. Indicators are calculations; evidence is interpretation-ready information
A deterministic calculation produces a number. Evidence is a *statement about a relationship* that a
reasoning step can use. The two are not the same, and the gap between them is a real design boundary the
system already embodies:

| | calculated today | classified today | evidence? |
|---|---|---|---|
| price vs EMA(20) | yes | yes (`above`/`below`/`equal`) | **yes** |
| RSI band | yes | yes (`oversold_zone` …) | **yes** |
| relative volume | yes | **no** (ADR-0010 deferred it) | not yet |
| ATR percent of close | yes | **no** (reported as a raw value) | not yet |
| relative return, correlation | yes | **no** (restated from the RVE unchanged) | not yet |

A descriptor is earned by the middle column, not the left one.

### 2. `EvidenceFamily` names subject areas only
Ten families: TREND, MOMENTUM, VOLUME, VOLATILITY, MARKET_STRUCTURE, RELATIVE_STRENGTH, LIQUIDITY,
MACRO, NEWS, SENTIMENT. A family says what evidence is *about* and never what to do about it, so BUY,
SELL, LONG, SHORT and SIGNAL are category errors here, not merely premature.

**Deliberately distinct from `FeatureCategory`, which it shares five names with.** They are different
axes and neither contains the other:

- `FeatureCategory` classifies a **deterministic calculation** and additionally has INDICATOR, PATTERN
  and SUPPORT_RESISTANCE — descriptions of *how* something is computed.
- `EvidenceFamily` classifies an **evidence concept**, including MACRO, NEWS, SENTIMENT, LIQUIDITY and
  RELATIVE_STRENGTH — five families with no feature at all.

Extending `FeatureCategory` was not available as an option: its own docstring states that macro, news and
sentiment are "intentionally NOT represented here" and instructs "Do not add such members to this enum".
The overlap is a real and slightly uncomfortable fact, so it is recorded here and asserted by a test
rather than left to be rediscovered: the two enums must not be merged, and neither is a rename of the
other.

### 3. `EvidenceDescriptor` defines a concept, not an observation
Three fields — `family`, `name`, `description` — frozen and slotted. It says a kind of evidence exists
and what it is about. It carries no value, no reading, and no timestamp, because two analyses of two
instruments on two days refer to the same descriptor and differ only in what they observed.

The omissions are the design. No score, weight, or confidence: nothing in the system estimates any of
them, and a field is an invitation to supply a number with no basis. No direction: a subject area has no
stance. Slots make the omissions enforceable — a "just this once" attribute cannot be attached later.

### 4. No combined evidence-type enum, because three concepts already have owners
An enum mixing SUPPORTING, CONFLICTING, NEUTRAL, UNAVAILABLE and INSUFFICIENT_DATA was explicitly not
created. It would conflate **two different dimensions** — a relationship to a hypothesis, and data
availability — and it would duplicate three things that already work:

- **supporting / conflicting** → `fmis.decision_support.EvidenceGroups` fields;
- **neutral / unavailable** → `fmis.decision_support.Alignment` members;
- **insufficient data** → `OverallState.INSUFFICIENT_DATA`, plus the `insufficient_data` key that every
  feature already writes into its own metadata.

Those live in the layer that observes actual data, which is where they belong: availability is a property
of a particular reading, not of a concept. A second definition here would be a second source of truth for
concepts whose current owners are correct.

### 5. The catalog records what is true today, including the gaps
Six descriptors, all mirroring observations `fmis.decision_support` genuinely emits: three TREND
(`price_vs_ema_fast`, `price_vs_ema_slow`, `ema_fast_vs_ema_slow`) and three MOMENTUM (`rsi_zone`,
`macd_vs_signal`, `macd_histogram`). Names match the emitted observation keys, so the vocabulary stays
checkable against the implementation instead of drifting into a parallel naming scheme — a test builds a
real report and asserts every catalogued name is actually produced and actually classified.

**Five families are empty**, and that is the honest state rather than an oversight. VOLUME is computed
and not classified. VOLATILITY is reported as raw values. RELATIVE_STRENGTH has no alignment concept at
all — `RelativeValueEvidence` carries numbers and undefined reasons and classifies none of them, so the
"relative-value alignment" that seemed a plausible entry does not exist. MARKET_STRUCTURE, LIQUIDITY,
MACRO, NEWS and SENTIMENT have no implementation. An empty family is a real answer: it says a future
module has somewhere to put its evidence, and that nothing does today.

The catalog is a module-level immutable tuple, validated at import, ordered canonically by family
declaration order then name. Names are unique **globally**, not per family — a name identifying two
concepts is ambiguous however it is grouped. There is no mutable registry and no plugin mechanism:
adding a descriptor is a source change with a test, which is what keeps a vocabulary reviewable.

### 6. Names are required to be normalized, never normalized for you
A descriptor name must already be a lower-case token with no whitespace. One that merely *could* be
normalized is rejected rather than rewritten. This follows the project-wide no-coercion rule
(ADR-0005, ADR-0009), and here it has a specific purpose: silently trimming or lower-casing would let
`"Trend "` and `"trend"` be entered as two descriptors that collapse into one, so the duplicate check
would pass while the catalog held a collision.

### 7. Shared vocabulary, separate interpretation
Trading, investing, macro and news modules will each interpret the same family differently. What MOMENTUM
means to a day trader, to a swing trader, and to a long-term investor are three different claims about
the same subject. The taxonomy gives them a common word for the subject and says nothing about the claim
— exactly the split ADR-0009 established for shared calculations, applied one layer up.

### 8. `decision_support` integration is deferred
`fmis.evidence` does not import `decision_support`, and `decision_support` was **not** modified to depend
on `fmis.evidence`. Both directions are asserted by tests. Connecting them means deciding how an
`Observation` refers to a descriptor, which is a real design question worth its own milestone; wiring it
now would freeze that answer before the vocabulary has settled and before anything needs it.

## Alternatives considered

- **Register a descriptor per indicator** (RSI, MACD, ATR, EMA, relative volume). Rejected: it asserts
  that calculation implies interpretation-readiness, which §1 exists to deny. Five of those are not
  classified anywhere.
- **Register "relative-value alignment"** as a RELATIVE_STRENGTH descriptor. Rejected after the audit
  found it does not exist: `RelativeValueEvidence` has no classification or alignment field. This is the
  clearest case of why the catalog was audited against runtime output rather than assembled from memory.
- **Extend `FeatureCategory` instead of adding `EvidenceFamily`.** Rejected: that enum explicitly
  prohibits the non-technical members required here, and it classifies a different kind of thing (§2).
- **A combined `EvidenceType` enum.** Rejected: conflates two dimensions and duplicates three existing
  owners (§4).
- **Normalize names on construction.** Rejected: silent coercion, and it defeats duplicate detection (§6).
- **A mutable registry with a `register()` hook.** Rejected: a vocabulary that can be extended at runtime
  cannot be reviewed, and nothing needs the indirection.

## Consequences

- There is now one place to answer "what kinds of evidence does this system actually have?", and the
  answer is small and honest: six concepts in two families.
- The empty families make the system's real coverage visible. Anyone expecting volume or relative-strength
  evidence can see immediately that it is measured but not interpreted.
- Adding a descriptor later requires the corresponding classification to exist first, and the
  cross-check test enforces that ordering — a descriptor cannot be added ahead of its implementation.
- The `FeatureCategory` / `EvidenceFamily` overlap is a maintenance risk if either drifts. It is recorded
  here and asserted by a test, but a future reader must understand both are intentional.
- Nothing consumes the taxonomy yet. That is expected for a vocabulary introduced ahead of its consumer,
  and it may need additive families or descriptors when a reasoning layer first uses it.
