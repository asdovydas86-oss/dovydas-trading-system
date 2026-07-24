# ADR-0002 — Alignment is a temporal-comparison policy layer, separate from canonical data

**Status:** Accepted
**Date:** 2026-07-24
**Decides:** review finding **R2** ([ARCHITECTURE_REVIEW_2026-07-24.md](../ARCHITECTURE_REVIEW_2026-07-24.md))
**Confirms:** architecture decision **D4** ([ARCHITECTURE_AND_ROADMAP_V1.md](../ARCHITECTURE_AND_ROADMAP_V1.md) §12)
**Implemented by:** nothing yet — the code move is planned as **Milestone I-E** (see §Consequences)

---

## Context

Strict-intersection alignment was implemented at `src/fmis/data/alignment.py` and re-exported from
`fmis.data`, whereas decision D4 and the Milestone I code scope both place alignment in a **separate**
module because it is a *policy/service*, not a model. The architecture review (R2) surfaced this as a live
divergence between the code and an accepted decision, and left the choice to the repository owner: move the
code to a dedicated package, or amend D4 to bless the current placement.

The decision has now been made.

## Decision

**Alignment moves out of `fmis.data` into a dedicated `src/fmis/alignment/` package.**

The boundary is:

- **`fmis.data` defines canonical data** — what a market observation *is* (`Candle`, `CandleSeries`,
  `ObservationSeries`) and the invariants it must satisfy (including the canonical-UTC contract,
  [ADR-0001](ADR-0001-canonical-utc-timestamps.md)).
- **`fmis.alignment` defines temporal-comparison policy** — how two or more canonical series are made
  comparable in time. Strict intersection is the *first* such policy; it is not the only one.

The code is **not moved in this ADR's milestone** (I-D is documentation only). This ADR records the
decision and the planned follow-up.

## Alternatives considered

**A. Keep alignment inside `fmis.data` and amend D4.**
Rejected. It operates only on canonical models and imports nothing else, so it is harmless *today* — but
strict intersection is one of several coming policies (as-of joins, resampling, availability-aware
alignment, calendar-aware logic). A `fmis.data` that accumulates them stops being a kernel and becomes a
grab-bag, and the invariant "canonical models import nothing from outside `fmis.data`" becomes hard to
state. The cost of the move is asymmetric: cheap now (one package, one public import path), expensive once
RVE and portfolio consumers depend on it.

**B. Move now, in this milestone.**
Rejected only for *timing*. The milestone (I-D) is explicitly documentation-only; moving code here would
violate that scope and bundle unrelated change. The move is scheduled as its own implementation milestone
so it carries its own import and test updates under review.

## Consequences

**Planned follow-up — Milestone I-E "Observation Reduction & Alignment Boundary"** (implementation, under a
separate prompt; **not** authorized by this ADR):

- create the `fmis.alignment` package boundary;
- move the strict-intersection implementation (`align_intersection`, `AlignmentResult`, `AlignmentReport`,
  `SeriesAlignmentStats`) into it;
- update imports and tests; the public path becomes `fmis.alignment.align_intersection`;
- (the same milestone also carries the R1 reduction helper and related items — see
  [CURRENT_STATE.md](../AI_HANDOFF/CURRENT_STATE.md)).

**Until the move happens:**

- do **not** add a *second* temporal-comparison policy (forward-fill, as-of join, resampling) to
  `fmis.data` — the next policy waits for the dedicated package;
- `fmis.data` continues to re-export `align_intersection` so nothing breaks in the interim.

**After the move:** future policies join `fmis.alignment` as siblings of strict intersection, and
`fmis.data` returns to being a pure canonical kernel.

## Related

- [ADR-0001](ADR-0001-canonical-utc-timestamps.md) — the canonical-UTC contract alignment relies on for
  exact instant equality.
- [ADR-0003](ADR-0003-availability-time-boundary.md) — availability-time is the policy dimension that a
  future alignment policy (as-of join on release date) will need; it lives in this same policy layer.
- [RVE_DESIGN_V1.md](../RVE_DESIGN_V1.md) — the first consumer of `fmis.alignment`.
