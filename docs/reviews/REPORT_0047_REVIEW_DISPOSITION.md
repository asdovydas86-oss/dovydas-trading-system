# Report 0047 — Review Disposition

**Review record for [report 0047 — Technical Analysis Capability Audit & Architecture Gate](../../reports/0047_2026-09-07_TECHNICAL_ANALYSIS_ARCHITECTURE_GATE.md).**

| Field | Value |
|---|---|
| **Reviewed report** | `0047_2026-09-07_TECHNICAL_ANALYSIS_ARCHITECTURE_GATE.md` |
| **Reviewed by** | Dovydas + ChatGPT |
| **Recorded on** | 2026-09-16 |
| **Recorded at commit** | `66bab74` |
| **Disposition** | ## APPROVED WITH REQUIRED ARCHITECTURAL MODIFICATIONS |

---

## Why this file exists

Report 0047 is a **point-in-time report** and, by this repository's convention, is never rewritten to
look current. It remains immutable historical evidence of what was proposed on 2026-09-07.

Without this record, a future agent reading 0047 would find it marked *"awaiting Dovydas + ChatGPT
approval"* with no way to learn that the review happened, or that twelve modifications were required.

**Read this file whenever you read report 0047.**

---

## What the disposition means

**Approved:** the audit, its measurements, its findings, its statements of what exists and what does
not, and the *general direction* of its recommended sequence.

**NOT approved verbatim:** the implementation plan. Twelve modifications below are **binding on the
implementation**, and several explicitly refuse to freeze a decision that 0047 stated more
confidently than the evidence supports.

**Not authorization to implement.** Approval of the direction is not approval to build. Each slice
still needs its own implementation brief.

---

## The twelve required modifications

### A. Opportunity ≠ Strategy

Market Opportunity must remain **conceptually separate** from Swing Strategy:

```
deterministic market facts → market opportunity interpretation/projection → product workspace
deterministic market facts → versioned strategy policy              → strategy decision
```

The workspace may combine both outputs. All of these must remain **logically possible**:

| Opportunity | Strategy decision |
|---|---|
| `WATCH LONG` | `WAIT` |
| `WATCH LONG` | `CANDIDATE` |
| `NONE` | `WAIT` |

**Opportunity must NOT be defined as *"strategy gates are not satisfied"*** — under that definition
`WATCH` + `CANDIDATE` is logically impossible, which defeats the purpose.

*Not implemented in the Memory Gate. Internal vocabulary and package ownership remain design work for
the Market Opportunity milestone.*

### B. Missing market confirmation ≠ policy Blocker

| Concept | The question it answers |
|---|---|
| Policy **`Blocker`** | *Why did this strategy/policy stop?* |
| Market **`MissingConfirmation`** | *What market event has not happened yet?* |

They must not be conflated. A future workspace may legitimately show both at once:

```
Market confirmation missing:  acceptance above zone X
Strategy blocker:             context-role regime is not TRENDING
```

*Not implemented now.*

### C. `compute_series()` precedes production ATR-based zone clustering

0047 correctly identifies `compute_series()` as a high-leverage **additive** protocol extension.

Production zone width may eventually use the historical ATR **at the zone's establishment point**.
Therefore historical series access **must exist before** a production zone engine depends on
establishment-time ATR.

*Not implemented in the Memory Gate. Recorded as prerequisite work in TA Slice 5A.*

### D. Zone evidence independence is NOT established

0047 describes zone/location evidence as independent in one place while also declaring correlation
with structural trend, because both derive from shared pivots.

**The unqualified independence claim is not preserved.** Use instead:

> *"a new / potentially more orthogonal evidence family"*

**Status: `INDEPENDENCE NOT ESTABLISHED`.** Future research (R15 or equivalent) must test it
empirically before any claim of independence is made in code, tests or product copy.

### E. Support / resistance terminology

Internal semantics must remain **interaction-based**. This derivation is **forbidden**:

```
below current price = support        ← NEVER
above current price = resistance     ← NEVER
```

Future internal states may use precise interaction/lifecycle semantics such as `HELD_FROM_ABOVE`,
`HELD_FROM_BELOW`, `BROKEN_UPWARD`, `BROKEN_DOWNWARD`, `ROLE_FLIPPED`.

User-facing *"Support"* / *"Resistance"* wording **may be permitted later**, but only when the
deterministic interaction history justifies the role, and only with explicit architecture and test
reconciliation — three existing guards currently forbid those words in output, and that is deliberate.

### F. Price phases — do not freeze the segmentation model

0047's phase **direction** is approved.

**Not approved as a permanent architecture axiom:** *"one exhaustive non-overlapping phase per
candle."* Markets may contain nested structure and scale-dependent phases.

Future design must explicitly decide: segmentation scale · whether overlaps/nesting are permitted ·
how timeframe/scale identity is preserved.

### G. Trendline anchors — sequencing approved, anchor rule not

**Approved:** phases before trendlines, as sequencing.

**NOT approved as a permanent rule:** *"trendline anchors must always lie inside exactly one phase."*
Trendlines may legitimately connect structurally meaningful pivots **across** phases. Anchor policy
remains an open research/design question.

### H. Divergence alignment

Exact price-pivot indexing is a safe **v1** candidate.

Do **not** permanently rule out a later, explicitly researched oscillator-pivot alignment policy.

**Never acceptable in any version:** arbitrary ±N-bar cherry-picking.

### I. Fibonacci

| Field | Value |
|---|---|
| **Status** | `RESEARCH FIRST` · `OPTIONAL CONTEXT` · **NOT ORIGINAL APPROVED SCOPE** |
| **Verified** | 0 occurrences in `PROJECT_SPECIFICATION_V1.md`, 0 in `PROJECT_VISION_ADDENDUM_V1.md`, 0 files under `src/` |
| **It must never become** | a mandatory gate · a veto · a direction source by itself · a confidence multiplier · a substitute for independently derived market structure |
| **Now** | **No Fibonacci implementation.** The research is approved; the feature is not |

### J. Elliott Wave

| Field | Value |
|---|---|
| **Status** | `DEFERRED` · `UNSCHEDULED` · optional **hypothesis-level interpretation only** |
| **Verified** | 0 occurrences in either approved source, 0 files under `src/` |
| **Never** | in deterministic L4/L5 market truth |
| **Explicitly NOT recorded** | *"Elliott can never exist because it changes as the market evolves."* That is **not** a permanent prohibition. A future hypothesis layer may represent multiple alternative counts, invalidation, and changing hypotheses |
| **Now** | **No Elliott implementation** |

### K. Correlated indicators

**Preserve 0047's finding:** adding EMA slope, MACD ROC, RSI slope and similar does **not**
automatically create independent confirmation.

**Do not misread it as:** *"EMA/MACD/RSI context is not useful."* That context remains important
market information.

The point is exactly and only this:

> **contextual usefulness ≠ independent evidence family**

### L. Pattern order

Do not build chart patterns before their primitives. The dependency direction is:

```
swings → zones/interactions → phases → geometry → patterns
```

- Bull/bear flag — a later pattern candidate.
- Double top/bottom — a later candidate.
- **Rectangles** — primarily represented by **range/phase primitives**, not duplicated as a separate
  pattern.
- Head & shoulders, symmetrical triangles, wedges — **deferred**.
- **No generic pattern framework** before a second real pattern demonstrates shared abstraction.

---

## Question deliberately left open

**Should the 1W regime gate be relaxed?** 0047 §43.1 declines to recommend touching it, and that
declination stands. The opportunity layer makes the question **less urgent**, because a gated symbol
can be visibly `WATCH` without the gate moving at all.

---

## Owner decisions from 0047 §43 — still outstanding

| ID | Decision | Blocking? | Status |
|---|---|---|---|
| **D1** | Zone width tolerance (a scoped weakening of ADR-0013's no-tolerance rule) | Blocks **Slice 5B** | **Open** |
| **D2** | May a zone carry a role, and what may it be called? | Blocks **Slice 5B** | Partly settled by §E above — the *derivation* rule is fixed; the *naming* is still open |
| **D3** | Where does opportunity state live, may it name a side? | Blocks **Market Opportunity** | **Open.** 0047 recommends deferring past Slice 5; §A above fixes the separation but not the ownership |
| **D4** | `compute_series()` on the `Feature` protocol | In scope for **Slice 5A** | Approved **as additive** — `compute()` unchanged, every existing feature name, seeding convention and metadata unchanged |
| **D5** | Do the three evidence-status vocabularies converge? | Not blocking | 0047 recommends **not** merging them. No decision recorded |
| **D6** | Fibonacci: research first? | Not blocking | **Approved — the research, not the feature** (§I) |
| **D7** | Elliott: defer? | Not blocking | **Approved — deferred** (§J) |

---

## Where these decisions now live durably

| Content | Home |
|---|---|
| Capability statuses, deferrals, revisit triggers | [`../AI_HANDOFF/CAPABILITY_REGISTRY.md`](../AI_HANDOFF/CAPABILITY_REGISTRY.md) |
| Open architectural questions (§A–§L, condensed) | [`../AI_HANDOFF/CAPABILITY_REGISTRY.md`](../AI_HANDOFF/CAPABILITY_REGISTRY.md) §7 |
| Implementation sequence | [`../AI_HANDOFF/CAPABILITY_REGISTRY.md`](../AI_HANDOFF/CAPABILITY_REGISTRY.md) §6 · [`../../FMITS_PRODUCT_BACKLOG.md`](../../FMITS_PRODUCT_BACKLOG.md) §6 |
| Current state and next milestone | [`../AI_HANDOFF/CURRENT_STATE.md`](../AI_HANDOFF/CURRENT_STATE.md) |
| **Binding** architecture decisions | [`../adr/README.md`](../adr/README.md) — **none of the above is an ADR.** When one of these modifications becomes binding on code, it needs a real ADR |
