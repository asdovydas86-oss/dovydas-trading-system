# ADR-0003 — Availability-time boundary: no macro/vintage data before an availability-time model

**Status:** Accepted
**Date:** 2026-07-24
**Decides:** review finding **R3** ([ARCHITECTURE_REVIEW_2026-07-24.md](../ARCHITECTURE_REVIEW_2026-07-24.md))
**Corrects:** the phrasing in [ARCHITECTURE_AND_ROADMAP_V1.md](../ARCHITECTURE_AND_ROADMAP_V1.md) §7.3 that
lists look-ahead bias as "structurally prevented" — that is a **future requirement** for the RVE over
macro/vintage data, **not** a present guarantee (see §Correction). This ADR is the authoritative
current-state statement; the versioned V1 document is annotated, not rewritten.

---

## Context

A correct backtest may only use information that was **knowable** at the instant it evaluates. For market
candles that is naturally true — a *closed* candle represents a completed market event, and the system
already computes on closed candles only. For macroeconomic and other released/revised data it is **not**
naturally true, because such data has two distinct time dimensions that must not be conflated:

- **observation / event time** — the period the value describes (e.g. "March 2026 M2");
- **availability / knowledge time** — the instant the value became knowable (its release/publication
  date), with revisions producing several values, at several availability times, for one observation time.

The canonical models today carry only the first dimension. `ObservationSeries` timestamps are observation
timestamps; there is no release, publication, revision, or knowledge time anywhere in the model. Strict
intersection therefore aligns on observation time, which for macro data would let a value influence a
computation *before it was published* — the precise look-ahead bias this project exists to avoid.

Nothing enforces the boundary at present; only the **absence of any macro/released/revised data source**
keeps the system safe. That is a safe accident, not a guarantee, and it must be made explicit before any
such data is introduced.

## Decision

### Current guarantees (true today)

1. **Market candle observations represent completed market events.** Calculations run on `series.closed()`;
   a still-forming bar can never change an output. This is enforced and tested.
2. **Canonical timestamps are exact instants** under the canonical-UTC contract
   ([ADR-0001](ADR-0001-canonical-utc-timestamps.md)), so alignment's instant equality is exact.

### What is NOT guaranteed today (explicitly)

3. **The `ObservationSeries` model does not represent release, publication, revision, or knowledge time.**
   It has one time dimension (observation time) only.
4. **No-look-ahead protection for macro/released/revised/vintage data is therefore _planned, not
   implemented_.** The alignment service aligns on observation time and has no notion of availability time.

### The boundary (accepted, binding)

5. **Macroeconomic, fundamental-release, revised, and vintage datasets MUST NOT be integrated — for
   analysis or for backtesting — until an explicit availability-time model is designed and accepted.**
   Introducing them against the current single-dimension model would silently consume future information.

6. **The availability-time model is a required architectural milestone** that must precede any
   macro/fundamental-release/revised/vintage-data backtesting. It is not scheduled here; it is a
   prerequisite gate, not a near-term task. Designing it is out of scope for the current milestone.

## Correction to the architecture document

[ARCHITECTURE_AND_ROADMAP_V1.md](../ARCHITECTURE_AND_ROADMAP_V1.md) §7.3 lists, in the RVE alignment
*requirements* table, look-ahead bias as "Structurally prevented … Tested explicitly", and §14 lists a
no-look-ahead test as Milestone I acceptance. Read as a **requirement for the future RVE over
availability-timed data**, the row is a valid design goal. Read as a statement about the **current**
system, it is inaccurate: the knowledge-time dimension does not exist, so the guarantee cannot hold and the
test cannot be written. This ADR is the authoritative correction; the V1 planning document is left intact
as the target statement and is annotated by this ADR rather than silently edited (per the repository's
versioning convention).

The mixed-calendar (crypto 7-day vs equity 5-day) alignment test, also listed under Milestone I, is a
*separate* matter: it **is** writable today against the existing model, and its absence is ordinary missing
coverage, scheduled with Milestone I-E — not blocked by this ADR.

## Alternatives considered

**A. Add the availability-time dimension now.** Rejected: designing a release/revision/vintage model is a
substantial architectural task that changes a canonical model every later layer depends on; doing it
speculatively, before a concrete macro source and its real semantics exist, risks the wrong abstraction.
It gets its own milestone, driven by a real data source.

**B. Leave the claim and integrate macro data behind discipline/convention.** Rejected: convention is
exactly what silently reintroduces look-ahead bias. The only safe control is to make the pathological data
*unrepresentable* until the model exists — hence the hard integration gate in decision (5).

**C. Say nothing and rely on the absence of macro data.** Rejected: a safe accident that is not written
down is one refactor or one eager contributor away from becoming an unsafe one.

## Consequences

- The documentation now distinguishes current guarantees (1–2) from future ones (3–4) wherever look-ahead
  is discussed, instead of implying the guarantee already holds.
- Macro/fundamental/revised/vintage integration is gated behind an accepted availability-time model; a
  reviewer can point at decision (5) to block a premature macro PR.
- The availability-time model is recorded as a required precursor milestone, so it is scheduled
  deliberately when a real macro source arrives, rather than discovered mid-backtest.

## Related

- [ADR-0002](ADR-0002-alignment-as-temporal-comparison-policy-layer.md) — the future as-of-join /
  availability-aware policy that consumes availability time lives in the `fmis.alignment` layer.
- [RVE_DESIGN_V1.md](../RVE_DESIGN_V1.md) §11 — the no-look-ahead test is expressible for the injected
  `as_of` truncation form only; the release-date form is blocked on this ADR.
