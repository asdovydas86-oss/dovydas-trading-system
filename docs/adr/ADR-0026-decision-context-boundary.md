# ADR-0026 — Decision context: one question about the information, never about the market

**Status:** Accepted
**Date:** 2026-08-04
**Decides:** whether a sufficiency judgement exists, what it may say, where it lives, and why it holds
no thresholds of its own (Milestone AL)
**Implemented by:** *(uncommitted at the time of writing)*
**Relates to:** [ADR-0007](ADR-0007-application-layer-boundary.md) (the layer direction it respects);
[ADR-0008](ADR-0008-decision-support-evidence-boundary.md) §7 (the evidence rule it delegates to);
[ADR-0011](ADR-0011-evidence-taxonomy.md) (classified, not merely calculated);
[ADR-0016](ADR-0016-structural-sequence-state-history-foundation.md) §4 (projections, not stored copies);
[ADR-0017](ADR-0017-structural-trend-foundation.md) (a stated policy is not a measurement);
[ADR-0025](ADR-0025-market-regime-engine-v1.md) (no composite label; absence ≠ disagreement);
`SPEC` §6 (missing data is an output) and §7 (excessive confidence from incomplete data)

---

## Context

Measured on the repository at `6ebf1e0`, before this milestone:

| A 40-candle page rendered | What was underneath |
|---|---|
| regime section **✓ available** | `structure: insufficient · volatility: insufficient` |
| evidence **state watch** | three features still warming up |
| structure **`neutral`**, 10 levels | 40 closed candles |

A section's status says whether it **produced output**, not whether the output can be **trusted**, and
nothing aggregated the difference. `required_candles` existed per indicator and `InsufficientDataError`
fired only at zero closed candles. **No layer judged whether an analysis as a whole rested on enough
data** — which is exactly the bias `SPEC` §7 names.

This also gates the next milestone. `reports/0005` Phase 4 names *"alert fatigue from an unfiltered
brief"* as the daily workflow's principal risk; the filter is a sufficiency judgement, and building it
inside the workflow would mean extracting it later.

---

## Decision

A new engine package **`fmis.decision_context`** answering exactly one question: *does this analysis
contain enough trustworthy information to continue toward a trading setup?*

### 1. It judges the information, never the market

The result carries no direction, entry, exit, target, stop, position size or risk. `SUFFICIENT` says
the data each layer asked for is present; it says nothing whatever about price.

**This does not contradict ADR-0025's refusal of a composite label.** That refusal was about collapsing
*market state* into one word. This is a claim about the *analysis*, which is a different object — and
`SPEC` §6 requires missing data as a first-class output.

### 2. It invents no threshold

Five requirements, and **every one delegates its rule to the layer that already declared it**:

| Requirement | Met when | Rule owned by | Severity |
|---|---|---|---|
| `PRIMARY_DATA_DEPTH` | closed ≥ the view's own `required_candles` | `fmis.market_structure` | blocking |
| `WARM_UP_COMPLETE` | nothing on the primary view is warming up | `fmis.features` | limiting |
| `REGIME_DETERMINATE` | no dimension reported `INSUFFICIENT` | `fmis.market_regime` | limiting |
| `STRUCTURE_PRESENT` | at least one level exists | `fmis.level_crossing` | blocking |
| `EVIDENCE_PRESENT` | the evidence state is not `INSUFFICIENT_DATA` | ADR-0008 §7 | blocking |

`ContextPolicy` therefore carries **no numbers** — the only policy object in the repository that does
not. A threshold here would be a *second definition* of a rule another layer owns, and the second
definition is the one that drifts. A test asserts no numeric literal other than 0 and 1 appears in the
evaluator.

### 3. Severity is fixed in code; strictness is the one knob

Which gaps are fatal is a semantic property of the gap, not a setting. `ContextPolicy` exposes a single
`strict` flag promoting every limiting gap to blocking — **not** a per-requirement override, because a
demotable severity set would let a caller quietly switch off the one check about to stop them, which is
the shape of gate `docs/analysis-notes.md` blames for the v2 bias.

### 4. Conflicts never move the verdict

Sufficiency is about what is **available**, not about whether it agrees. A market whose timeframes
disagree is still analysable, and penalising disagreement would reward pages that look tidy by being
one-sided. The conflict count is carried into metadata so a page can show it beside the verdict, and a
test asserts that varying it changes no state and no check.

### 5. There is no score

Three states and five named checks. A number would compress exactly the information a reader needs in
order to disagree, and would imply a calibration never performed (`SPEC` §4.1).

### 6. The engine imports nothing from `fmis`

Its input is seven integers, two strings, a flag and a timestamp. It cannot reach a candle, a fact
sheet, an evidence report or a rendered page.

**This matters more than it looks.** The `Workspace` model is *presentation-shaped* — its body values
are formatted strings such as `('setup · 1d', 'insufficient', ...)`. An engine consuming the workspace
would be parsing presentation back into data. The application layer adapts; the engine stays testable
from primitives.

### 7. `may_continue` derives from the state, not from the checks

An earlier implementation tested "no blocking check", which disagreed with itself under `strict`:
strictness promotes a limiting gap to blocking at the *state* while the check keeps its fixed severity,
so a result reported `INSUFFICIENT` and `may_continue` simultaneously. One source of truth removes the
contradiction rather than validating against it — ADR-0016 §4 applied to a property.

### 8. The workspace gains a twelfth section, placed between conflicts and risk

A gate belongs after everything it judges and before everything it guards. This is the first test of
Milestone AJ's promise that a new capability is a **registration**: one enum member, one entry in
`SECTION_ORDER`, one provider. Nothing else moved.

---

## Rejected alternatives

| Alternative | Why rejected |
|---|---|
| **A confidence score 0–1** | Never calibrated; compresses the checks a reader needs; `SPEC` §4.1 |
| **Thresholds owned here** (min candles, max warm-up) | A second definition of rules other layers own — the one that drifts |
| **Per-requirement severity overrides** | Lets a caller switch off the check about to stop them |
| **Counting conflicts against sufficiency** | Rewards one-sided pages; conflates disagreement with absence |
| **Consuming the `Workspace`** | The model is presentation-shaped; parsing formatted strings back into data |
| **A projection on `Workspace` instead of an engine** | Needs a versioned policy and per-view adequacy the model does not expose numerically |
| **Deferring until the daily workflow needs it** | Guarantees the filter is built inside the workflow and extracted later |
| **Two states (enough / not enough)** | Loses the honest middle: nothing blocking is missing but the analysis is degraded |

---

## Consequences

**The measured gap closes.** 12 candles → `INSUFFICIENT`, 40 → `LIMITED`, 260 → `SUFFICIENT`, where
all three previously rendered as an available page.

**The next milestone gains its filter.** A watchlist scan can exclude instruments whose analysis is
insufficient, using a judgement that exists outside it.

**New public names** appear only in `fmis.decision_context` (16). `DEFAULT_POLICY` was renamed
`DEFAULT_CONTEXT_POLICY` — `fmis.market_regime` already exports the former, and the repository's
export-collision guard caught it.

**Still deliberately absent:** direction, entry, exit, target, stop, sizing, risk, portfolio, strategy,
interpretation, and any number expressing how sufficient something is.
