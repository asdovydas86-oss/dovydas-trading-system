# ADR-0034 — The zone-interaction evidence boundary

**Status:** **Proposed** — 2026-09-20
**Decides:** research questions **R3** and **R4** ([report 0047](../../reports/0047_2026-09-07_TECHNICAL_ANALYSIS_ARCHITECTURE_GATE.md) §45),
which [ADR-0033](ADR-0033-price-zone-semantics-and-the-tolerance-boundary.md) named as the reason
`ZoneInteraction` and `ZoneReading` are not in V1.
**Evidence:** [report 0052](../../reports/0052_2026-09-20_PRICE_ZONE_INTERACTION_SEMANTICS_RESEARCH_GATE.md),
against a preregistration sealed at commit `296831a` before its harness existed.
**Supersedes nothing. Rewrites nothing.** ADR-0033's research claims stand unaltered; this ADR
answers the two questions it deferred.

---

## Context

ADR-0033 shipped price zones as geometry and deliberately shipped no interaction, no role and no
support/resistance label, recording that each needed a parameter R3 or R4 had not measured. The
board then held **zero** NOW items rather than promote a successor by intuition, and named the
preregistered outcome study as the way through.

That study has run. It did not produce the two parameters. It produced a reason they should not
be produced, and that reason is worth binding so it is not re-litigated by the next reader who
finds the vocabulary obvious.

---

## Decision

### D1 — A persistence state over a band is computable, and is **not** a zone fact

Consecutive closes beyond a frozen band mark a genuinely distinguishable state. Two closes versus
one moves the ten-bar persistence probability from **0.41 to 0.65** (+22 to +25 points across 1D
and 4H, primary and holdout); a third adds +26 to +29 more.

**And a placebo band separates by exactly the same amount.** Bands of identical width, identical
establishment bar, displaced in price so that no confirmed structural level anchored them, produce
+0.243 where real zones produce +0.246 — an excess of **±0.004 that flips sign across cells**.

> **Therefore: FMITS may compute a persistence state over a band, and may not attribute it to the
> zone.** The state is a property of price behaviour relative to *any* horizontal band of that
> width, not of the structural area.

The measurement is admissible on its own terms — causal, prefix-stable, deterministic,
reflection-symmetric, scale-invariant, explicit under missing ATR — and `N` is a **resolution
control with no knee**, exactly as ADR-0033 found `k` to be. **No `N` is declared here**, because
nothing in the product currently needs one.

### D2 — There is no `RETEST`, and there is no window to choose

The return hazard to a real zone is indistinguishable from the return hazard to a clean placebo
band at **every** elapsed range on **every** role: ratio **0.96–1.02** on the two well-powered
roles, several bins significantly *below* 1, under both return definitions and all three excursion
preconditions.

> **Therefore: no `RETEST` state may be built.** A return to a zone is not attributable to the
> prior transition. `RETURN_TO_ZONE_AFTER_OUTSIDE_STATE` is the strongest honest name for the
> observable, and it claims nothing.

**The trap this closes.** The raw return hazard decays seven-fold over forty bars, steepest in the
first three. Read alone it is a textbook "retests cluster within 2–3 bars" finding and would have
yielded a confident `R4 = 3`. The placebo hazard decays identically. **The decay is first-passage
geometry, not market memory.** Any future proposal for a retest window must clear a placebo
control before it is discussed.

### D3 — Six of the seven approved role labels remain underivable

ADR-0033 §8 approved the vocabulary `UNTESTED` · `HELD_FROM_ABOVE` · `HELD_FROM_BELOW` ·
`BROKEN_UPWARD` · `BROKEN_DOWNWARD` · `ROLE_FLIPPED` · `INDETERMINATE`. Approving vocabulary did
not prove a derivation, and the derivation is now measured:

| Label | Derivable |
|---|---|
| `UNTESTED` | **Yes** — no `EXIT` and no touch since establishment; pure bookkeeping |
| `HELD_FROM_ABOVE` · `HELD_FROM_BELOW` | **No** — *held* is the attribution D2 refused |
| `BROKEN_UPWARD` · `BROKEN_DOWNWARD` | **No** — *broken* is the attribution D1 refused |
| `ROLE_FLIPPED` | **No** — needs both |
| `INDETERMINATE` | Only meaningful once a sibling exists |

> **Therefore: the only derivable label is the one that means nothing has happened.** The seven
> labels are **not** to be forced into a state machine because the ADR names them. The vocabulary
> stays out of the code until something can populate it.

### D4 — Support / resistance labels stay unavailable

ADR-0033 acceptance decision D permits *"Support zone"* / *"Resistance zone"* **only** over a role
derived from interaction history. D3 leaves no such role derivable. **The labels remain
unavailable, and deriving them from `position` remains forbidden** — report 0050 measured that
shortcut wrong, and nothing here weakens it.

### D5 — What a future interaction slice must clear

Any later proposal to build an interaction engine must, before it is discussed:

1. state the observable event at the low level, with an explicit knowledge time;
2. carry a **placebo or equivalent null**, because both of this gate's headline effects survive
   naive measurement and neither survives a control;
3. cluster inference on the **symbol**, never the event — 4H produced 22.9 events per zone;
4. name the state for what was measured, not for what traders call it.

---

## Consequences

**Blocked, now on evidence rather than on ignorance:** the Zone Interactions milestone,
`ZoneInteraction`, `ZoneReading`, derived roles, support/resistance labels, breakout, acceptance,
reclaim, retest and false-breakout vocabulary.

**Unblocked and unaffected:** Price Phases, and every capability that does not depend on a zone
role.

**Unchanged:** `k = 0.50` and every ADR-0033 zone semantic (this gate was forbidden to retune them
and did not) · `PriceLevel`, `classify_comparison` and `CrossingKind` exactness · zone evidence
independence, which remains `NOT ESTABLISHED` pending **R15** · strategy, risk, Scan Memory and
the 1W gate, none of which any zone fact reaches.

**A `CLOSE_BREACH` is still not a breakout.**

---

## Limitations of the evidence behind this ADR

Stated so a future reader can judge what would reopen it.

- **1W is `UNDERPOWERED`** in both universes (195/548 and 147/433 events against a sealed 200
  minimum). The R3 finding rests on 1D and 4H.
- **No volume** in the capture, so volume-confirmed acceptance was never tested — it is *untested*,
  not refuted.
- **Gapped transitions are unmeasurable** in continuously-traded crypto (3–161 events per cell).
- **Survivorship**: 36 symbols listed and liquid at capture; no newer majors.
- **Conditional on `k = 0.50`** throughout.
- The direction asymmetry observed in outcomes is a property of the 2023–2026 sample, **not** a
  licence for direction-dependent semantics; the classifier itself is exactly reflection-symmetric.

**What would reopen D2:** a dataset with intrabar or order-flow resolution testing a genuinely
different retest hypothesis — not more of the same bars, whose comparison here is precise rather
than noisy (±0.004 confidence intervals on 63k–70k real events against 113k–117k controls).
