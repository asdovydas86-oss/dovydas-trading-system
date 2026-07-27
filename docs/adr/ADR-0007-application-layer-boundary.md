# ADR-0007 — Application layer boundary

**Status:** Accepted
**Date:** 2026-07-28
**Decides:** where multi-engine orchestration lives, and what it may and may not do (Milestone Q)
**Implemented by:** `feat(pipeline): add Market Analysis Pipeline v1`
**Relates to:** [ADR-0006](ADR-0006-provider-adapter-contract.md) (the adapter it calls);
[ADR-0005](ADR-0005-ingestion-boundary-strictness.md) (the boundary beneath that);
[ADR-0004](ADR-0004-rve-v1a-return-and-result-policy.md) (the RVE metrics it reuses);
`ARCHITECTURE_AND_ROADMAP_V1.md` §5 (dependency direction)

---

## Context

Every engine now exists — provider, ingestion, canonical models, features, alignment, RVE — and each is
correctly ignorant of the others. That independence is the architecture's main strength and the reason
nothing yet answers a whole question: producing one analysis means calling six modules in the right
order, and there is no layer allowed to know about more than one of them.

Something must own that composition. Placing it inside any existing engine would destroy exactly the
property that makes the engines testable: `fmis.features` would learn about networking, or
`fmis.providers` about indicators.

## Decisions

### 1. `fmis.pipeline` is the application layer, and it sits at the top
It may import every engine. **No engine may import it** — a test walks all of `src/fmis` outside the
package and asserts no file mentions `fmis.pipeline`. The dependency arrow points one way, so any engine
remains usable, and testable, without the application layer existing.

### 2. Orchestration only — no calculation may be defined here
Every number in an `AnalysisSnapshot` comes from an engine. A test parses the module's AST and asserts it
contains exactly **one** arithmetic operator — the subtraction deriving the excluded-candle count from
two lengths, which is bookkeeping, not a market calculation — and that it imports no `math`, `statistics`,
`decimal`, or `fractions`. A second test asserts the pipeline's relative-value outputs are *equal* to the
result of calling the RVE directly on the same aligned inputs, so reuse is proven rather than assumed.

Adding an indicator or a metric means adding it to `fmis.features` or `fmis.relative_value`. If a
calculation ever seems to belong in the pipeline, that is the signal it belongs in an engine.

### 3. Closed candles only, unconditionally
The forming candle is dropped before any calculation, and this is **not** a configurable default. A
snapshot computed over a forming bar is not reproducible: re-running it minutes later silently yields
different numbers, which defeats the determinism every layer beneath is built to guarantee.

Exclusion is reported, not implied: `DataWindow` carries `fetched_count`, `closed_count`, and
`excluded_forming_count`, so a caller can always see what was left out. Callers wanting the forming bar
have it on the `CandleSeries` from `fmis.providers` — one layer down, where it is not yet an analysis.

### 4. Warm-up is a result; insufficient data is an error
An indicator without enough history returns `value=None` plus warm-up metadata — the documented Feature
Engine behaviour, passed through unchanged. That is a *complete* answer to a well-formed question.

Having no closed candles at all, or fewer than three aligned observations for a comparison, is a
different thing: the question cannot be answered. It raises `InsufficientDataError` naming the subject,
the requirement, and the actual counts. The three-observation floor is checked in the pipeline because
the alternative — an `InsufficientObservationsError` surfacing from deep inside the RVE — does not tell
the caller which of the two series was short.

### 5. Nothing partial, and nothing re-wrapped
If a benchmark comparison was requested and fails, the whole call fails. Returning a technical-only
snapshot would silently deliver less than was asked for, and a caller reading `relative_value is None`
cannot distinguish "not requested" from "requested but broken".

Errors from below — `BinanceError`, `IngestError`, feature-engine `ValueError`, alignment errors,
`RelativeValueError` — propagate **unwrapped**. They are already precise about which stage failed, and
wrapping them in a pipeline exception would discard that. `PipelineError` covers only failures the
pipeline itself detects.

### 6. Concrete functions, not a workflow framework
`analyze_symbol` answers one question. Another question means another function, not a registry of steps,
a DSL, or a pluggable stage abstraction. There is no second workflow yet, so there is nothing to
generalize from — the same reasoning that deferred a provider Protocol in ADR-0006.

### 7. Fact-only, and no interpretation
A snapshot restates measurements and provenance. No direction, score, ranking, confidence, label, or
recommendation, and no AI. A test asserts the output vocabulary contains none of it. Composition is not a
licence to editorialize: if the engines are fact-only, an assembly of their outputs must be too.

## Alternatives considered

- **Put orchestration in `fmis.features`** (it already has an "engine"). Rejected: it would make the
  deterministic engine depend on networking, and `FeatureEngine` orchestrates *features*, a different job
  at a different level.
- **A new top-level `apps/` or CLI.** Rejected for this milestone: a CLI is a presentation concern on top
  of this API, and building one first would freeze the result shape to whatever printed nicely.
- **Wrap every downstream error in `PipelineError`.** Rejected: uniform-looking errors that hide which
  stage failed are worse to debug than four precise hierarchies.
- **Return a partial snapshot when the benchmark fails**, with `relative_value=None`. Rejected: silently
  ambiguous, and it violates the project-wide rule against silently degraded output.
- **Make closed-only a flag.** Rejected: the non-default branch produces irreproducible analysis, which
  is not an option worth offering.
- **Compute a composite "technical score".** Rejected outright: interpretation, and out of scope for
  every layer built so far.

## Consequences

- The first whole-system answer exists: a real symbol produces a structured, reproducible snapshot with
  provenance, and the same call with a benchmark adds the five v1a relative-value metrics.
- The result shape (`AnalysisSnapshot`, `DataWindow`, `RelativeValueSection`) is now a public contract.
  It is deliberately small and immutable so it can grow additively.
- Known limitations carried forward: single timeframe per call (no 1W/1D/4H composition), one benchmark,
  close-price comparison only, no persistence, and the provider's no-pagination limit applies
  (ADR-0006 §7). Each is additive future work.
- The `default_features()` set is a convenience, not a contract: adding a Tier-2 composite later changes
  what a default snapshot contains, which is why the feature names are recorded in the snapshot metadata.
