# FMITS — Project Pause, 2026-09-21

**Status: PAUSED INDEFINITELY, by owner decision, at a clean and fully pushed repository.**

This document is the single place a future reader — human or AI — should start from when FMITS
resumes. It records the exact state at pause, what is true, what was decided, what is unresolved,
and how to cold-start. It **changes no production code, no strategy policy, no test, no risk
configuration and no research conclusion.**

> **Reading order on resume.** This file first, then
> [`START_HERE_FOR_AI.md`](START_HERE_FOR_AI.md), then [`CURRENT_STATE.md`](CURRENT_STATE.md) §0,
> then [`CAPABILITY_REGISTRY.md`](CAPABILITY_REGISTRY.md). **Where this file disagrees with an
> older document, verify against the live repository — never against either document.**

---

## 1. Exact repository state at pause

Verified live on 2026-09-21, not copied from any prior document.

| Field | Value |
|---|---|
| **Branch** | `main` |
| **`HEAD`** | `1af559030c59ceefe29e0b601f8060ab532c118f` |
| **`main`** | `1af559030c59ceefe29e0b601f8060ab532c118f` |
| **`origin/main`** | `1af559030c59ceefe29e0b601f8060ab532c118f` |
| **Remote `refs/heads/main`** (`git ls-remote`) | `1af559030c59ceefe29e0b601f8060ab532c118f` |
| **Ahead / behind** | `0 / 0` |
| **Tracked working tree** | **clean** — zero modified, zero staged, zero deleted |
| **Stash** | empty |
| **Active Git operation** | none — no merge, rebase, cherry-pick or bisect |
| **Remote** | `https://github.com/asdovydas86-oss/dovydas-trading-system.git` |

**All four SHAs are equal.** Everything committed is pushed; nothing is only local.

Last four commits:

```
1af5590 2026-09-20 12:56:34 +0200  research(zones): the retest was first-passage geometry all along
296831a 2026-09-20 12:12:11 +0200  research(zones): seal R3/R4 before the harness can answer them
527a162 2026-09-18 13:27:48 +0200  docs(zones): accept ADR-0033, and record what 5B refused to build
3739d42 2026-09-18 13:27:01 +0200  feat(zones): FMITS sees an area where it saw three unrelated lines
```

*(This pause document adds one further commit, on top of `1af5590`.)*

---

## 2. Untracked state — the loss risk, now resolved

### 2.1 Sixteen research documents — **1.1 MB, 15,750 lines, PRESERVED IN GIT 2026-09-21**

> **RESOLVED.** These sixteen documents had been untracked since 2026-08-19 and existed nowhere but
> this working tree. **They are now committed and pushed**, in preservation commit
> **`d04a409bc52de507d6eb0070564c45d98443fc56`**, and are **no longer an outstanding local-loss
> risk.** Deleting the working tree or re-cloning no longer destroys them.

They were committed **byte-for-byte unchanged** — not edited, renamed, moved, merged, deduplicated,
summarised or corrected. Each staged blob was verified `sha256`-identical to its working-tree file
before the commit.

**Preservation is not approval.** They are classified as historical, unapproved and
non-authoritative by [`../design/UNAPPROVED_RESEARCH_INDEX_2026-08.md`](../design/UNAPPROVED_RESEARCH_INDEX_2026-08.md),
committed alongside them, which quotes each document's own disclaimer rather than assigning one and
records that the authority chain is unchanged: **accepted ADRs bind, §0 of `CURRENT_STATE.md` states
current state, and the live code wins over every document.** Nothing proposed in any of them is
promoted by their being tracked.

| Lines | Bytes | Path |
|---:|---:|---|
| 3,010 | 232,503 | `docs/design/TRADING_DOMAIN_DATA_MODEL_V1.md` |
| 1,710 | 115,604 | `docs/design/SWING_TRADING_MVP_BLUEPRINT_V1.md` |
| 1,688 | 104,406 | `docs/design/TRADER_WORKSPACE_PRODUCT_ARCHITECTURE_V1.md` |
| 1,017 | 72,571 | `docs/design/CONFIRMATION_FRESHNESS_POLICY_DECISION_V1.md` |
| 904 | 69,543 | `docs/design/AP_D1_D2_INVESTIGATION.md` |
| 895 | 56,972 | `docs/design/EVIDENCE_CALIBRATION_RESEARCH_V1.md` |
| 765 | 46,418 | `docs/design/EDGE_SEGMENTATION_RESEARCH_V1.md` |
| 744 | 56,496 | `docs/design/SWING_TRADING_READINESS_AUDIT_V1.md` |
| 727 | 46,531 | `docs/design/EVIDENCE_FAMILY_INDEPENDENCE_RESEARCH_V1.md` |
| 701 | 43,576 | `docs/design/CONFIRMATION_FRESHNESS_HYPOTHESIS_RESEARCH_V1.md` |
| 694 | 66,337 | `docs/design/AP_ADR_DISCOVERY.md` |
| 690 | 44,358 | `docs/design/FAILURE_ATTRIBUTION_RESEARCH_V1.md` |
| 652 | 72,653 | `docs/design/IMPLEMENTATION_ROADMAP_V1.md` |
| 563 | 38,736 | `docs/design/FMITS_INFORMATION_EDGE_RESEARCH.md` |
| 495 | 38,257 | `docs/design/ADR_IMPLEMENTATION_GATE.md` |
| 495 | 34,284 | `docs/reviews/AP_D1_D2_INVESTIGATION_REVIEW.md` |

**They were committed but not absorbed, summarised or superseded** — the index beside them
deliberately does not reconcile their contradictions or mark any of them obsolete, because an index
that interprets becomes a document that decides. Before the commit all sixteen were scanned for
credentials, keys, seed phrases, addresses, personal data and generated runtime data, with **zero
hits in every category**; content hashes are recorded in the index so a later reader can confirm
preservation did not alter them.

### 2.2 Everything else untracked is rebuildable

`.venv/` (rebuild from the tracked `uv.lock`), `build/`, `src/fmis.egg-info/`, every `__pycache__/`,
`.pytest_cache/`, `.DS_Store`, `.dashboard.log` (last written 2026-09-12, stale), `.claude/`,
`.mcp.json`.

**`.env` does not exist** — only `.env.example` is present, so **no secret is at risk in this
checkout.** If FMITS is resumed with live data, `.env` must be recreated from `.env.example`.

---

## 3. Runtime state

| Field | Value |
|---|---|
| **Operator dashboard** | **running** — PID **46403**, `127.0.0.1:8787`, `LISTEN` |
| Started | 2026-09-07 19:40:40, uptime **14 days** at pause |
| Command | `.venv/bin/python .venv/bin/fmits dashboard` |
| Nature | local, loopback-only, **read-only**; answers `GET`/`HEAD` only; writes nothing to the store |

**It is safe to stop, and stopping loses nothing.** It holds no state of its own; it re-reads the
durable store on each refresh. Stop it with `Ctrl-C` in its own terminal, or by **exact PID**:

```
kill 46403          # never pkill/killall — other Python processes are running
```

**If this terminal session is closed without stopping it, the process is likely to be killed with
its parent shell.** That is acceptable and costs nothing.

### 3.1 `~/.fmits` — persistent store **outside** the repository

```
~/.fmits/scan_memory/scans/     8 JSON files, 2026-09-06 → 2026-09-21
~/.fmits/risk_policy.json       ABSENT — never created; risk stays undeclared
```

**This directory is not in Git and is not backed up by pushing.** It survives closing the terminal,
but not wiping the home directory. One of its files is the only machine record of the 2026-09-21
diagnostic in §6 — see §6.4.

---

## 4. Latest completed product capability

**TA Slice 5B — Price Zone Foundation & Product Surface** (2026-09-18, commit `3739d42` + its
documentation commit `527a162`; [report 0051](../../reports/0051_2026-09-18_TECHNICAL_ANALYSIS_SLICE_5B.md)).

**FMITS sees a structural *area* where it previously saw unrelated exact lines.** `fmis.price_zones`
groups confirmed `PriceLevel`s into anchored, frozen, causal bands (`anchor.price ± k×ATR14/2`, read
at the anchor's own establishment bar and never moved), and `/swing/SYMBOL` gained a **price zones**
panel. `k = 0.50`, **declared by the owner, not measured**, one policy shared by 1W/1D/4H.

**It deliberately shipped no role, no strength and no breakout vocabulary.** `position` is geometry.

**This is the most recent user-visible capability. Nothing has shipped since** — the 2026-09-20
research gate ([report 0052](../../reports/0052_2026-09-20_PRICE_ZONE_INTERACTION_SEMANTICS_RESEARCH_GATE.md))
changed **zero files** under `src/` and `tests/`, and `FMITS_PRODUCT_CHANGELOG.md` correctly carries
no entry for it.

**Product surface at pause** — 25 CLI commands:

```
facts · mtf · regime · swing · setup · evidence · scan · backtest · daily · today · workspace
pulse · macro · portfolio · approve · trade · simulate · statistics · performance · expectancy
equity · trades · research · dashboard · archive
```

10 fixed dashboard pages plus one dynamic route:

```
/ · /markets · /swing · /portfolio · /paper · /performance · /lab · /geometry · /validation · /system
/swing/SYMBOL   (dynamic)
```

---

## 5. Latest research result, and ADR status

**Price Zone Interaction Semantics Research Gate — R3 / R4**, 2026-09-20,
[report 0052](../../reports/0052_2026-09-20_PRICE_ZONE_INTERACTION_SEMANTICS_RESEARCH_GATE.md).
Preregistration sealed and pushed at `296831a` **before the harness existed** (provable: that commit
contains the preregistration and **zero** files under `research/zone_interactions/`).

### FACT — measured, reproducible from committed inputs

- 153,148 real interaction events from 9,881 zones over 36 symbols × 3 timeframe roles, plus
  596,578 placebo events, offline from the committed Milestone CD capture.
- **R3:** a second consecutive close beyond a frozen band moves ten-bar persistence from **0.41 to
  0.65** (+22 to +25 points on 1D and 4H, primary and holdout, Holm-adjusted p = 5.1e−04). A third
  close adds +26 to +29 more — **no knee; `N` is a resolution control, not a threshold.**
  ATR-normalised displacement is **complementary, not dominant.**
- **R3, post-hoc control:** a **placebo band** — identical width, identical establishment bar,
  displaced so that no confirmed structural level anchored it — separates by **+0.243** against the
  real **+0.246**. The excess is ±0.004 and flips sign across cells.
- **R4:** the return hazard to a real zone is indistinguishable from a clean placebo's at **every**
  elapsed range on **every** role — ratio **0.96–1.02** — under both return definitions, all three
  excursion preconditions, and the split by prior persistence.
- The raw return hazard decays sevenfold (`0.206 → 0.121 → 0.070 → 0.046 → 0.027 → 0.015`); **the
  placebo decays identically** (`0.207 → 0.122 → 0.072 → 0.045 → 0.026 → 0.015`).
- 68/68 adversarial fixture assertions and 27/27 real-data invariant and isolation checks pass.
- Full suite at close: **15,416 passed, 0 failed, 0 warnings** under `-W error`.

### OWNER DECISION — recorded, and still standing

- `k = 0.50` is **declared, not discovered** (ADR-0033 acceptance, 2026-09-18). Not an optimum, not
  a calibrated threshold, not an edge claim.
- One `k` shared by 1W/1D/4H; no per-role constant.
- *"Support zone"* / *"Resistance zone"* are approved **only** as future labels over a role derived
  from interaction history, **never** over `position`, and never for `UNTESTED`.

### UNRESOLVED / OPEN

- **[ADR-0034](../adr/ADR-0034-zone-interaction-evidence-boundary.md) is `Proposed`, not Accepted.**
  It awaits owner + ChatGPT review. It binds the negative boundary: no `RETEST`, no `ACCEPTANCE`
  naming, six of ADR-0033's seven role labels underivable, and a requirement that any future
  interaction proposal carry a null control. **A future session must not treat it as Accepted.**
- **R15 — zone evidence independence: `NOT ESTABLISHED`.** No zone fact may reach evidence voting,
  the 1W gate, Scan Memory or risk until it is.
- **0047 D3** (where opportunity state lives, and whether it may name a side) and **0047 D5**
  (whether the three evidence-status vocabularies converge) remain open.
- **Zone Interactions is BLOCKED on evidence**, not on ignorance. It is no longer the next milestone.
- **The `8b22e6c9…` policy digest cited by earlier reports has no recipe recorded anywhere in the
  repository.** Three plausible reconstructions give three different values. Report 0052 therefore
  evidenced policy non-regression by re-running the 81-fixture assertion suite instead. **Recording
  that recipe is a small, genuinely useful follow-up.**

### ADR status at pause

**34 ADRs. 33 Accepted. One Proposed: ADR-0034.** Nothing else is pending.

---

## 6. The 2026-09-21 product diagnostic

> **This is a diagnostic about the quality of FMITS's market representation and decision layer.
> It is NOT a strategy change, and must not be read as one.** No policy, threshold, gate, evidence
> rule, weighting or parameter was altered on 2026-09-21 or by this pause. The strategy policy is
> byte-identical to its state at TA Slice 5B.

### 6.1 FACT — from the recorded scan artifact, not from recollection

A scan was recorded at **2026-09-21 18:19:46 UTC** (`analysis_as_of` 2026-09-21 12:00:00 UTC) over a
**20-symbol** universe across the three timeframe roles. Its contents, read directly:

| Observation | Value |
|---|---|
| Symbols scanned | 20 |
| **`CONFIRMED`** | **1 — `TRXUSDT`, direction `long`** |
| `WAIT` | 19 — including `BTCUSDT`, `SOLUSDT`, `ETHUSDT` |
| Unreadable symbols | 0 |
| `sufficiency` | **`sufficient` on all 20** — evidence was not missing |
| `evidence_available` | **`true` on all 20** |
| `independence_established` | **`false` on all 20** (R15) |
| **`blocker_kind`** | **`context_regime_not_eligible` on all 19 `WAIT`s**; `none` on TRX |
| `blocker_observed` | `transitioning` on all 19 `WAIT`s |

Per-symbol detail for the three the owner examined:

| | `TRXUSDT` | `BTCUSDT` | `SOLUSDT` |
|---|---|---|---|
| state | **`confirmed`** | `wait` | `wait` |
| direction | `long` | — | — |
| blocker | `none` | `context_regime_not_eligible` | `context_regime_not_eligible` |
| developing lean | `long` | **`short`** | **`long`** |
| supporting / conflicting | 5 / 1 | 1 / 2 | 1 / 2 |
| structural trend — context (1W) | **`sustained_higher`** | `neutral` | `neutral` |
| structural trend — setup (1D) | `neutral` | `sustained_lower` | `neutral` |
| structural trend — execution (4H) | `sustained_higher` | `sustained_higher` | `sustained_higher` |

**The single discriminator across the whole universe was the 1W context regime.** TRX was the only
symbol whose weekly context was eligible; all 19 others were blocked by the same gate, for the same
stated reason, at the same moment. **BTC and SOL received identical states, identical blockers and
identical supporting/conflicting tallies while leaning in opposite directions** — BTC short, SOL
long.

### 6.2 OWNER DECISION / OWNER READING

The owner compared this output against the BTC and SOL charts and concluded that **the current
market representation and decision layer is not good enough**: a twenty-symbol scan collapsing to
one binary weekly gate does not describe what the charts show, and two markets in visibly different
conditions should not be indistinguishable in the output.

**The response is to pause, not to adjust.** No threshold was moved and none should be moved on the
strength of one scan. Tuning the 1W gate to admit BTC or SOL would be exactly the invented-threshold
behaviour this repository has refused at every gate.

### 6.3 UNRESOLVED — what this diagnostic did *not* establish

- It does **not** establish that the 1W context gate is wrong; one scan on one day cannot.
- It does **not** establish that TRX's `CONFIRMED` was correct, or profitable, or repeatable.
- It does **not** measure how often the decision layer collapses to one discriminator.
- It does **not** identify which layer is deficient — the regime model, the multi-timeframe
  composition, the evidence sufficiency rule, or the representation beneath all three.

**All four are open questions, and §8 proposes the gate that would answer them.**

### 6.4 Provenance, and a preservation warning

The artifact is:

```
~/.fmits/scan_memory/scans/20260921T181946309343-b61405b8078a.json
sha256  a2c35dcdac58d603ce8bc25adccb365831a8e2f077eb9d6f3ade20776ffe5226
```

**It is outside the repository and is not preserved by any Git operation.** The tables in §6.1 are
transcribed from it so the diagnostic survives in the repository even if the file does not. The raw
file was read only; nothing in `~/.fmits` was modified by this pause.

---

## 7. No validated edge — stated plainly

**FMITS has never demonstrated predictive power, and nothing at pause claims otherwise.**

This is not a caution added by this document; it is the repository's own recorded position, and it
was re-verified live at pause:

- **Milestone CA — `NO_EDGE`** ([report 0037](../../reports/0037_2026-08-27_SWING_ADMISSION_NULL_MODEL_RESEARCH.md)):
  swing admission versus matched random-entry nulls.
- **Milestone CB — `UNDERPOWERED`** ([report 0038](../../reports/0038_2026-08-28_STATISTICAL_POWER_AND_RESEARCH_DESIGN.md)).
- **Milestone CC — `INFEASIBLE`** ([report 0039](../../reports/0039_2026-08-28_UNIVERSE_FEASIBILITY_AND_INFORMATION_EXPANSION.md)):
  universe expansion. Preserved verbatim; later work refined it without overturning it.
- **Report 0052 — `NO SUPPORT` for retest**, and R3's persistence effect **not attributable** to the
  structural zone.
- **Verified live at pause:** every verdict member of every research enum reports
  `is_approved_for_trading = False` — 11 members across `DependenceVerdict`, `RequirementOutcome`
  and `LabVerdict`. **No verdict in the system is capable of approving trading.**
- Backtesting remains `PARTIAL`: **no fees, slippage, spread or execution delay are modelled**, and
  every run prints that.

**A future session must not treat any FMITS output as a validated trading signal.** The system is
decision *support* with an explicitly unvalidated edge.

---

## 8. The unresolved market-model problem, and the proposed next gate

### 8.1 The problem, stated as a question rather than a fix

The 2026-09-21 diagnostic (§6) and the 2026-09-20 research result (§5) point at the same gap from
opposite directions:

- **From research:** the two most intuitive zone-interaction concepts — acceptance and retest —
  **both survive naive measurement and neither survives a null control.** What FMITS "sees" at a
  price area is, so far, indistinguishable from what it would see at an arbitrary band.
- **From the product:** a 20-symbol scan collapsed to **one binary weekly gate**, giving two markets
  in visibly different conditions identical output.

> **The unresolved problem: FMITS's representation of market state may not be rich enough to
> distinguish situations a competent human reader distinguishes immediately — and nothing in the
> repository currently measures whether it is.**

Every gate so far has asked *"is this specific concept real?"* None has asked *"does the whole
representation discriminate at all?"*

### 8.2 Proposed — **Market Interpretation Diagnostic Gate**

**Status: PROPOSED ONLY. Not started, not scoped, not approved, no ADR, no preregistration.**
Recorded here so the idea is not lost, and deliberately **not designed** — designing it now would
invent semantics this pause is forbidden to invent.

The question it would ask, and it is a *measurement* question:

> **How much does FMITS's decision output actually discriminate between markets, and which layer
> carries that discrimination?**

Candidate sub-questions, all unvalidated and none preregistered:

- Over a long offline history, how often does the scan collapse to a single discriminator, as it did
  on 2026-09-21? Is one `CONFIRMED` in twenty typical or unusual?
- What is the distribution of `blocker_kind`? If one blocker dominates, the other layers are not
  contributing and their cost is unjustified.
- Do symbols the system treats identically behave differently afterwards? **If they do, the
  representation is discarding information. If they do not, the gate is correct and the owner's
  chart reading is the thing being tested.** That symmetry is the point, and the gate must be able
  to return the second answer.
- Does any layer — regime, multi-timeframe composition, evidence sufficiency — add discrimination
  beyond the 1W gate alone?

**Discipline it must inherit** (from reports 0050 and 0052, and ADR-0034 D5):

1. preregister the question, the metrics and the refutation criteria **before** the harness exists,
   and push that commit first;
2. carry a **null or placebo control** — both of 0052's headline effects looked real without one;
3. cluster inference on the **symbol**, never the event;
4. offline, from committed data, no network;
5. **it may conclude that the current model is adequate**, and that outcome must be as publishable
   as the alternative.

**It is a diagnostic, not a redesign.** It ships no capability and licenses no threshold change.

### 8.3 The other live candidate

**Price Phases** (`CAPABILITY_REGISTRY.md` §6.1 step 2) was report 0052's recommended next
milestone: unblocked, needs no new research parameter, ships user-visible capability.

**Both are recorded. Neither is selected. The board has no NOW item and the selection is the
owner's.**

---

## 9. Cold-start procedure on resume

Do these in order. **Trust nothing in this file that a command can verify.**

### 9.1 Verify the repository is where this document left it

```
cd /Users/dovydas/dovydas-trading-system
git rev-parse HEAD                              # expect 1af5590… or later
git rev-parse --abbrev-ref HEAD                 # expect main
git fetch origin
git rev-list --left-right --count origin/main...HEAD    # expect 0  0
git status --porcelain=v1                       # expect completely clean, nothing untracked
git stash list                                  # expect empty
```

**The sixteen documents in §2.1 are tracked as of `d04a409` and need no special handling.** If
`git status` reports anything unexpected, stop and say so before doing anything else.

### 9.2 Rebuild the environment

```
uv sync                       # or: python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -c "import fmis; print('ok')"
```

`pyproject.toml` declares **`dependencies = []`** — FMITS has no runtime third-party dependency and
that property is deliberate. `pytest` is the only dev extra. **Do not add a numerical library**
without an explicit decision; report 0052's harness was rewritten in pure Python rather than
introduce NumPy.

### 9.3 Re-establish the baseline before changing anything

```
find . -name __pycache__ -type d -not -path './.venv/*' -exec rm -rf {} +
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -W error
```

**Expect `15,416 passed`, 0 failed, 0 warnings, ≈ 755 s (12–13 min).** Warnings are errors by
repository policy. The bytecode clearing is not optional — see the mutation-campaign lesson in
`CURRENT_STATE.md` §0.1.

### 9.4 Read the authority set

`START_HERE_FOR_AI.md` → `CURRENT_STATE.md` §0 → `CAPABILITY_REGISTRY.md` → latest daily handoff
(`docs/AI_HANDOFF/daily/2026-09-20.md`) → `FMITS_PRODUCT_BACKLOG.md` → `docs/adr/README.md`.
**Where they disagree, the ADRs win; where an ADR disagrees with the code, the code wins.**

### 9.5 Then, and only then, select a milestone

The board has **no NOW item**. §8 holds the two candidates. **Selecting one is the owner's decision,
not the resuming session's.**

---

## 10. Commands reference

### Tests

```
# full suite, the gate that must pass before any push touching src/ or tests/
find . -name __pycache__ -type d -not -path './.venv/*' -exec rm -rf {} +
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -W error

# one file
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_price_zones_architecture.py -q -W error

# strategy-policy non-regression (81 fixtures; the check that proves policy did not move)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_swing_setup_policy_non_regression.py -q -W error
```

### Dashboard

```
source .venv/bin/activate && fmits dashboard        # or: uv run fmits dashboard
.venv/bin/fmits dashboard --port 8799               # a development instance, off the live port
```

First refresh performs four live engine reads and takes 30–45 s; it prints the URL only once it can
answer. **Open the `open` line, not the `address` line.** Loopback only. Stop with `Ctrl-C`, or by
**exact PID** — never `pkill`/`killall`.

### CLI

```
.venv/bin/fmits --help
.venv/bin/fmits scan            # the 20-symbol watchlist scan — this produced §6's artifact
.venv/bin/fmits swing BTCUSDT
.venv/bin/fmits daily
```

**Use `.venv/bin/fmits`.** `python -m fmis.pipeline.cli` exits 0 and prints nothing.

### Research harnesses (offline, no network)

```
.venv/bin/python research/zone_semantics/run.py         # report 0050 — zone parameters
.venv/bin/python research/zone_interactions/run.py      # report 0052 — R3/R4 events
.venv/bin/python research/zone_interactions/analyze.py  # every table in report 0052
.venv/bin/python research/zone_interactions/posthoc.py  # the POST-HOC placebo control
.venv/bin/python research/zone_interactions/fixtures.py # 68 adversarial assertions
.venv/bin/python research/zone_interactions/verify.py   # 27 invariant + isolation checks
```

`src/` must never import from `research/`; `verify.py` asserts it.

---

## 11. What is *not* being changed by this pause

| Held | State |
|---|---|
| `src/` | untouched — zero files |
| `tests/` | untouched — zero files |
| Strategy policy, thresholds, gates, evidence rules | untouched |
| Risk configuration | untouched; `~/.fmits/risk_policy.json` still **absent** |
| Research conclusions (reports 0037–0052) | untouched; no verdict revised |
| ADR-0033 and its acceptance record | untouched |
| ADR-0034 | left `Proposed` — **not** promoted to close the milestone |
| The 16 August-2026 research documents | **contents untouched** — committed byte-for-byte unchanged in `d04a409`, unabsorbed, undeleted, and explicitly **not** approved |
| `~/.fmits` | read only; nothing written |
| `FMITS_PRODUCT_CHANGELOG.md` | untouched — a pause ships no capability |

---

## 12. One-paragraph summary for whoever resumes

FMITS is paused at `1af5590` with a clean tree, fully pushed, 15,416 tests green. The last shipped
capability is the price-zone panel (TA Slice 5B, 2026-09-18). The last research gate (0052,
2026-09-20) found that **neither zone acceptance nor retest survives a null control** — the effects
look real until you compare them against a band that means nothing, and then they vanish. On
2026-09-21 a 20-symbol scan returned **one** `CONFIRMED` (TRX long) with all 19 others blocked by
**the same** weekly-regime gate, which told the owner that the market representation is not
discriminating well enough to be worth trusting. **Nothing was tuned in response, and nothing should
be.** FMITS has no validated edge and every research verdict in the codebase is structurally
incapable of approving trading. The open question is no longer *"is this one concept real?"* but
*"does the representation discriminate at all?"* — §8 proposes the gate that would answer it, and
leaves it unscoped on purpose.
