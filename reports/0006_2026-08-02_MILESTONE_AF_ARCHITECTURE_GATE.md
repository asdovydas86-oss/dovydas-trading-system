# Milestone AF Architecture Gate — what is built next

| Field | Value |
|---|---|
| **Report number** | 0006 |
| **Title** | Milestone AF Architecture Gate |
| **Date** | 2026-08-02 |
| **Report type** | Architecture Gate |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `d132cea` + uncommitted Milestone AF |
| **Status** | Final |

**Purpose.** One decision: the single highest-value implementation milestone to build next. After this
report, planning stops.

**Note on the title.** Milestone AF (First Light) is **complete** — composition root, fact sheet, CLI,
ADR-0022, design, independent review, 3,305 tests passing. This is therefore the gate that *follows*
AF, deciding what AG should be.

**Role.** Chief Software Architect. The brief instructs me to challenge the proposal rather than
agree with it. I have, and I am **rejecting it for now**.

---

## Verdict

> ### ❌ "FMITS Workspace MVP" is **not** the correct next milestone.
>
> ### ✅ The correct next milestone is **AG — Multi-Timeframe Fact Sheet**.

Three findings drive this, in order of weight:

1. **"Workspace MVP" is defined nowhere.** It appears in no report, no ADR, no design document, no
   specification, and nowhere in the repository. A gate cannot approve an undefined proposal, so §2
   evaluates the three most charitable readings — and all three fail on the same architectural rule.
2. **The single-timeframe fact sheet AF just shipped can actively mislead.** Run live today, BTCUSDT
   reads `sustained_lower` on 4H, `neutral` on 1D and `sustained_higher` on 1W. `PROJECT_SPECIFICATION_V1.md`
   §5 names precisely this case and says the combination *"is different from simply calling the asset
   bullish"*. Building any workspace on top of a sheet that shows one of those three in isolation
   would industrialise a reading the approved specification forbids.
3. **Multi-timeframe needs no new engine.** Verified live: three calls to the existing composition
   root, three sheets, distinct identities, 1.5 s end to end including network. It is the same "pure
   composition" property that made AF succeed in a week.

---

## Table of contents

1. [The proposal under review](#1-the-proposal-under-review)
2. [Workspace MVP evaluated](#2-workspace-mvp-evaluated)
3. [The candidate field](#3-the-candidate-field)
4. [Recommendation — Milestone AG](#4-recommendation--milestone-ag)
5. [Implementation contract](#5-implementation-contract)
6. [Architectural unknowns settled here](#6-architectural-unknowns-settled-here)
7. [What this defers, and when each returns](#7-what-this-defers-and-when-each-returns)
8. [Planning phase statement](#8-planning-phase-statement)

---

## 1. The proposal under review

### 1.1 It is undefined — a material finding

Searched every Markdown file in the repository and all five reports:

```
grep -rniE 'workspace mvp|mvp' --include='*.md' .   →   no match
```

"FMITS Workspace MVP" exists only in the brief that commissioned this report. Report 0004 §7.2
catalogues **ten** surfaces whose names end in "Workspace" (P-04 Swing, P-05 Day Trading, P-06
Long-Term Investing, P-07 Portfolio, P-08 Research, P-09 China, P-10 IPO, P-11 Crypto/On-Chain, P-12
Derivatives, P-30 TradingView) — so "the Workspace" does not disambiguate itself either.

**This is not a technicality.** A gate approves a *contract*. An undefined proposal cannot be
estimated, cannot be scoped, cannot be tested against acceptance criteria, and cannot be refused
scope-creep. Approving it would guarantee the milestone drifts.

### 1.2 The three charitable readings

Rather than block, I evaluate what it most plausibly means:

| # | Reading | What it would be |
|---|---|---|
| **R1** | **Swing Trading Workspace** (Report 0004 P-04) | The instrument-centric surface for workflow B: multi-timeframe structure, regime, evidence, plan |
| **R2** | **Consolidated five-surface shell** (Report 0004 §16.4, my own earlier recommendation) | Pulse / Analyze / Intelligence / Portfolio / Laboratory as one navigable environment |
| **R3** | **A richer CLI or TUI over the fact sheet** | Multi-symbol, saved views, richer formatting over what AF already produces |

---

## 2. Workspace MVP evaluated

Against the ten criteria the brief specifies. Scores: ✅ strong · ◐ mixed · ❌ fails.

| Criterion | R1 Swing Workspace | R2 Five-surface shell | R3 Richer CLI |
|---|:---:|:---:|:---:|
| Architectural correctness | ❌ | ❌ | ◐ |
| Earliest user-visible value | ◐ | ❌ | ◐ |
| Lowest implementation risk | ❌ | ❌ | ✅ |
| Maximum reuse | ◐ | ◐ | ✅ |
| Educational value | ◐ | ◐ | ❌ |
| Business value | ◐ | ❌ | ◐ |
| Technical-debt prevention | ❌ | ❌ | ◐ |
| Alignment with Reports 0001–0005 | ❌ | ❌ | ◐ |
| Long-term maintainability | ◐ | ❌ | ◐ |
| Future AI integration | ◐ | ◐ | ◐ |

### 2.1 Architectural correctness — the decisive failure

Report 0003 §6.3 states **Product Rule 1**, quoting `ARCH` §11:

> Presentation never precedes facts. Building a dashboard before stable deterministic facts exist
> *"would invert the pipeline."*

Report 0004 §7.3 adds that **16 of the 31 surfaces are views, not applications** — a workspace's value
is almost entirely a function of the facts beneath it.

The facts beneath it are currently **one timeframe**. R1 and R2 would both build a presentation layer
over a fact set that the approved specification says must not be read in isolation. R3 escapes this
only by being small enough not to matter.

### 2.2 The specific harm, demonstrated live

Run today against real Binance data through AF's own composition root:

| Timeframe | Structural trend | Breaks | CHoCH | `as_of` |
|---|---|---:|---:|---|
| **1W** | `sustained_higher` | 16 | 7 | 2026-07-20 |
| **1D** | `neutral` | 25 | 12 | 2026-08-01 |
| **4H** | `sustained_lower` | 29 | 15 | 2026-08-02 |

`SPEC` §5, verbatim:

> **Weekly:** bullish structural trend. **Daily:** correction. **4H:** early momentum reversal.
> That combination is different from simply calling the asset "bullish."
>
> The system must avoid mixing timeframe signals without explaining their role.

The live data reproduces that example almost exactly. **A user running `fmits facts BTCUSDT` today
sees `sustained_lower` and nothing else.** That is not a missing feature; it is a fact sheet that can
lead a reader to the conclusion the specification exists to prevent.

Building a workspace on it first would put a durable surface over that defect.

### 2.3 It requires evidence that does not exist

R1 and R2 both need answers to questions only usage can supply: which surface first, what appears
above the fold, what the scanner ranks by, which alerts fire, what layout survives daily use.

Report 0005 §11.7 — written one report ago and still correct — said of the period after First Light:

> **Not Phase 2. Use it.** Run the fact sheet daily for a sustained period and record what was
> consulted and what was ignored. That record is worth more than the next three milestones of guessing.

AF shipped hours ago. There is no usage record. A workspace designed now would be designed from
imagination.

**The distinction that resolves this:** build what the **approved specification already states is
needed**; defer what **only usage can tell you**. `SPEC` §5's timeframe structure is in the first
category. Workspace layout, ranking and alerting are in the second.

### 2.4 Technical-debt prevention — it creates debt

AF established the composition-root contract (ADR-0007's three properties, now applied twice). A
workspace is a *third* composition root. Adding one before the facts are complete means it is built
against an incomplete fact model and rewritten when regime, MTF and portfolio arrive — the exact
"interfaces before stable facts" risk Report 0004 §14 ranks **R-04**.

### 2.5 What Workspace MVP is right about

The instinct is sound and I want to record it, because it should be honoured later:

- **AF's output is adjacent to the daily workflow, not inside it.** Correct, and it is the strongest
  argument for doing *something* now.
- **A CLI is a thin surface.** Correct — but Report 0004 §12 Level 1 explicitly says text output is
  sufficient at this rung, and Level 3 (v1) is where surfaces earn their place.
- **One navigable environment beats twenty tools.** Correct, and Report 0004 §16.4 argues it — as a
  *later* consolidation, not a first build.

### 2.6 Verdict on the proposal

**Rejected for now, not rejected outright.** The Swing Trading Workspace (R1) is the correct surface
to build — after regime (Phase 3), which is what gives it something to show. R2 is a consolidation
that should happen when there are ≥3 surfaces to consolidate. R3 is not a milestone; parts of it fall
naturally out of AG.

---

## 3. The candidate field

Every realistic alternative, scored on the same criteria. Weighted toward the brief's stated
priorities: architectural correctness, earliest value, lowest risk, maximum reuse.

| # | Candidate | Value | Risk | Reuse | Correct now? |
|---|---|:---:|:---:|:---:|:---:|
| **A** | **Multi-Timeframe Fact Sheet** | **High** | **Low** | **Total** | ✅ **Yes** |
| B | AG as previously recommended — ADR-0020 D1 provenance | None user-visible | Medium | n/a | ❌ Not yet — see §3.1 |
| C | Workspace MVP (R1/R2) | Medium | High | Medium | ❌ No — §2 |
| D | Market Regime Engine (Phase 3) | High | High | High | ❌ Not yet — §3.2 |
| E | Watchlist + Global Market Pulse (Phase 2) | Medium | Low | High | ◐ Good, but second |
| F | Persistence / run recording (Phase 5 seed) | Medium | Medium | High | ◐ Good, but second |
| G | Machine-readable (JSON) output | Medium | Medium | Total | ◐ Blocked by an open decision |
| H | CI + type checking | Low direct | Very low | n/a | ◐ Parallel work, not a milestone |

### 3.1 Why D1 is *not* next — reversing my own prior recommendation

`CURRENT_STATE.md` currently recommends Milestone AG = ADR-0020 D1. **I wrote that recommendation
yesterday, and I am overriding it here.** The reasoning that changed:

D1's hazard is that `confirmation_bars` must be hand-matched to `right_bars`, undetectably. AF's
review quantified it: over 300 seeded series × 5 wrong delays, **36.1 % produced materially different
breaks**, 155 of those changed the CHoCH count, and **zero raised an error**.

But AF *contained* it: `DetectionSettings` single-sources the delay, so a mismatch is unrepresentable
through the only caller that exists. The hazard becomes live at **caller #2**.

**Multi-timeframe does not create caller #2.** It calls the *same* composition root three times. The
containment holds unchanged, verified by construction. D1 therefore stays contained through AG.

**D1 becomes urgent at the Market Regime Engine (candidate D)**, which is a genuinely new consumer of
the structural chain. That is where it must be fixed — before regime, not before MTF.

### 3.2 Why regime is not next either

Regime is the highest-leverage unbuilt module in the system (Report 0003 §L5, Report 0004 C-023), and
it is where the project's founding failure gets fixed. But:

- It requires **MTF first**: the v3 prompt's STEP 1 is *"State the regime explicitly for 1W, 1D, and
  4H"*. A regime engine that classifies one timeframe answers the wrong question.
- It requires **D1 fixed first**, because it is caller #2.
- It is a genuine new engine — Report 0005 rates it complexity 4/5, 4–6 weeks — where AG is 1–2.

So the ordering the evidence forces is: **AG (MTF) → D1 provenance → regime**.

---

## 4. Recommendation — Milestone AG

> ## 🔭 AG — Multi-Timeframe Fact Sheet
>
> **One command produces a role-labelled 1W/1D/4H fact sheet, so the analysis Dovydas performs every
> day is served by computed facts instead of visual estimates.**

### 4.1 Why it wins on every stated criterion

| Criterion | Assessment |
|---|---|
| **Architectural correctness** | Adds facts, not presentation. Composes *above* the Feature Engine exactly as `ARCH` D11 prescribes — three `FeatureSet`s side by side, not one widened identity. Presentation still follows facts |
| **Earliest user-visible value** | The 1W/1D/4H structure *is* the swing workflow. `SPEC` §5 defines it; the v3 prompt already works this way; AF cannot express it |
| **Lowest implementation risk** | **Verified live: no new engine.** Three calls, three sheets, 1.5 s including network. Same property that let AF ship in a week |
| **Maximum reuse** | Total. Reuses `structural_facts_for_symbol`, `_fetch_closed`, every engine, the renderer's row primitives, and ADR-0007's composition-root contract |
| **Educational value** | Teaches multi-timeframe reasoning — the single most transferable skill in the roadmap's learning map — plus the discipline of *not* synthesising across timeframes prematurely |
| **Business value** | Moves the fact sheet from adjacent-to-workflow to inside-workflow. Closes the largest known gap between library output and the daily task |
| **Technical-debt prevention** | Removes a live defect (§2.2). Keeps D1 contained. Avoids the premature-surface debt a workspace would create |
| **Alignment with 0001–0005** | Report 0004 marks C-022 **Core, before-v1**, and §18.5 names the MTF deferral as *"the sharpest capability/architecture mismatch found"*. This closes it |
| **Long-term maintainability** | The MTF holder is the natural input to regime, scanning and the Daily Brief. Every later phase consumes it |
| **Future AI integration** | The AI layer's first job is interpreting *conflicting* timeframe evidence. This produces exactly that artifact, in a form an interpreter can consume |

### 4.2 What it unlocks

- **Workflow B (swing trading)** becomes properly served for the first time.
- **Regime (Phase 3)** gets its required input — regime is per-timeframe by definition.
- **The Swing Trading Workspace (R1)** becomes buildable, with something real to show.
- **Scanning (Phase 4)** gets its per-symbol unit: an MTF sheet is what a scanner ranks.

### 4.3 What risks it removes

| Risk | How |
|---|---|
| **A single-timeframe reading being taken as the asset's state** | The live defect of §2.2, removed directly |
| **Silent staleness across timeframes** | The 1W view's newest bar is **13 days old** today (week not closed) while 4H is 2 hours old. AG makes per-view `as_of` and staleness first-class; nothing surfaces this now |
| **A workspace built on incomplete facts** | Deferred until the facts exist |
| **D1 reopening** | Same composition root; containment holds by construction |

---

## 5. Implementation contract

This section is the contract. It is specific enough to begin immediately.

### 5.1 Exact objective

Add a second workflow to the application layer that composes **N role-labelled timeframe views** of
one symbol into one immutable `MultiTimeframeFactSheet`, render it as text, and expose it as
`fmits mtf SYMBOL`. Add no engine, no interpretation, and no cross-timeframe synthesis.

### 5.2 Repository changes — file by file

| Path | Change | Notes |
|---|---|---|
| `src/fmis/pipeline/multi_timeframe.py` | **new** | Composition root + models |
| `src/fmis/pipeline/render.py` | **modify** | Add `render_multi_timeframe_sheet`; extract `_row`/`_rule`/`_number`/`_level` reuse unchanged |
| `src/fmis/pipeline/cli.py` | **modify** | Introduce the command registry (§5.6); add the `mtf` command |
| `src/fmis/pipeline/__init__.py` | **modify** | Export the new public names |
| `tests/test_multi_timeframe.py` | **new** | ~60 tests (§5.9) |
| `docs/design/MULTI_TIMEFRAME_FACT_SHEET_V1.md` | **new** | Design record |
| `docs/adr/ADR-0023-multi-timeframe-composition.md` | **new** | Decisions §5.4, §5.5, §5.7 |
| `docs/reviews/MULTI_TIMEFRAME_FACT_SHEET_V1_REVIEW.md` | **new** | Independent review |
| `docs/AI_HANDOFF/CURRENT_STATE.md`, `docs/README.md`, `docs/adr/README.md`, `REPORT.md` | **modify** | Indexes |

**Explicitly unchanged:** every engine package · `structural_facts.py` (AG consumes it, does not
modify it) · `market_analysis.py` · `default_features()` (see §5.8) · `pyproject.toml`.

### 5.3 Package and module placement

`fmis.pipeline.multi_timeframe` — a **third module in the existing application layer**, not a new
package. Same reasoning as ADR-0022 §1: ADR-0007 §1 already grants `fmis.pipeline` the right to import
every engine and forbids any engine importing it. No new architectural decision is needed, which
satisfies the "no extra architecture" constraint that has now governed two milestones.

### 5.4 Models

```python
class TimeframeRole(Enum):
    """The role SPEC §5 assigns a timeframe — never inferred from the interval."""
    CONTEXT   = "context"     # structural context      (typically 1W)
    SETUP     = "setup"       # primary setup           (typically 1D)
    EXECUTION = "execution"   # entry timing            (typically 4H)

@dataclass(frozen=True, slots=True)
class TimeframeView:
    role: TimeframeRole
    interval: str
    sheet: StructuralFactSheet

@dataclass(frozen=True, slots=True)
class MultiTimeframeFactSheet:
    symbol: str
    source: str
    views: tuple[TimeframeView, ...]       # ordered CONTEXT -> SETUP -> EXECUTION
    newest_as_of: datetime                 # max as_of across views; NOT a shared instant
    limitations: tuple[Limitation, ...]
    metadata: Mapping[str, Any]

    @property
    def by_role(self) -> Mapping[TimeframeRole, TimeframeView]: ...
```

**Validation:** roles unique · at least one view · all views share `symbol` · views ordered by role ·
`metadata` defensively copied into a `MappingProxyType`.

### 5.5 Composition root

```python
DEFAULT_TIMEFRAMES: Mapping[TimeframeRole, str] = MappingProxyType({
    TimeframeRole.CONTEXT:   "1w",
    TimeframeRole.SETUP:     "1d",
    TimeframeRole.EXECUTION: "4h",
})

def swing_features() -> tuple[Feature, ...]:
    """default_features() plus EMA(200) — the v3 prompt's regime reference."""

def build_multi_timeframe_facts(
    views: Mapping[TimeframeRole, StructuralFactSheet],
) -> MultiTimeframeFactSheet: ...          # pure; no network, no clock

def multi_timeframe_facts_for_symbol(
    symbol: str,
    *,
    timeframes: Mapping[TimeframeRole, str] | None = None,
    limit: int | None = None,
    features: Sequence[Feature] | None = None,
    detection: DetectionSettings | None = None,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
    base_url: str | None = None,
) -> MultiTimeframeFactSheet: ...          # the network edge
```

**Invariants, each test-enforced:**

| # | Invariant |
|---|---|
| I1 | Zero arithmetic operators in the module (AST-asserted), as in `structural_facts` |
| I2 | No clock: no `datetime.now`, `utcnow`, `time.time`, `time.monotonic` |
| I3 | One `DetectionSettings` instance is used for **every** view — D1 containment extends unchanged |
| I4 | Each view delegates wholly to `structural_facts_for_symbol`; no structural call is made here |
| I5 | Nothing outside `fmis.pipeline` references `multi_timeframe` |
| I6 | A partial failure raises; no sheet is returned with a missing view |

### 5.6 CLI layout and command registry

AF's CLI has one subcommand and an implicit dispatch. AG introduces a registry **before** a third
command makes an if/elif chain inevitable:

```python
@dataclass(frozen=True, slots=True)
class Command:
    name: str
    help: str
    description: str
    configure: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace], int]

COMMANDS: tuple[Command, ...] = (FACTS_COMMAND, MTF_COMMAND)
```

`build_parser()` iterates `COMMANDS`; `main()` dispatches on `args.command` via a name→Command
mapping. A test asserts every registered command is reachable and that names are unique.

**Command layout:**

```
fmits facts SYMBOL  [-i INTERVAL] [-n LIMIT] [--left-bars N] [--right-bars N]
                    [--reference-time ISO8601] [--no-age]          # unchanged from AF

fmits mtf   SYMBOL  [-n LIMIT] [--left-bars N] [--right-bars N]
                    [--context 1w] [--setup 1d] [--execution 4h]
                    [--reference-time ISO8601] [--no-age]
```

`--context/--setup/--execution` name the **role explicitly**, never inferring it from the interval —
the same rule ADR-0009 applies to trading objectives.

### 5.7 Deterministic outputs

The rendered MTF sheet contains, per view, in role order:

```
── CONTEXT · 1w ──────────────────────────────────────────────
 As of / age · closed count · last close
 Structural trend · latest label · latest break · latest CHoCH
 ema_20 · ema_50 · ema_200 · rsi · macd · atr · relative volume
 Levels: count by side · nearest above · nearest below
```

followed by a **side-by-side trend row** and the shared limitations block.

#### The decision that matters most: **no cross-timeframe synthesis**

The sheet reports the three trends side by side and **derives nothing from their combination** — no
"aligned", no "conflicting", no agreement flag, no score.

*Rejected alternative:* a `TrendAgreement` field (`ALL_EQUAL` / `MIXED`). It is deterministic and
cheap, and it is still **a classification of market state, which is the Market Regime Engine's job**
(Report 0003 §L5). Emitting it here would put the first interpretation into the application layer and
pre-empt Phase 3 — the same error §2 rejects the workspace for. The reader sees
`1W sustained_higher · 1D neutral · 4H sustained_lower` and draws the conclusion; the system does not.

#### Per-view staleness is first-class

Views are fetched independently and **have different `as_of` values by nature** — measured today: 1W
`2026-07-20`, 1D `2026-08-01`, 4H `2026-08-02`. The 1W bar is 13 days old because the week has not
closed. Every view therefore renders its own `as_of` and age. A single sheet-level timestamp would
imply a synchronisation that does not exist.

**No alignment is applied.** `fmis.alignment` exists to make series comparable for *arithmetic*;
nothing here computes across timeframes, and forcing intersection would discard data for no gain.

#### New limitations to add

| Code | Text |
|---|---|
| **AG-1** | Views are fetched at different instants; the higher-timeframe view's newest closed bar may be days old. |
| **AG-2** | No cross-timeframe synthesis is performed. Reconciling disagreement is the Market Regime Engine's decision. |
| **AG-3** | `ema_200` requires 200 closed bars; on a weekly view that is ~4 years of history and may report as warming up. |

Plus all six inherited from ADR-0022.

### 5.8 `default_features()` stays unchanged — decided here

The v3 prompt's regime rule is *"price above/below EMA 200"*, and `default_features()` ships EMA(20)
and EMA(50) only. EMA(200) is needed.

**Decision: add `swing_features()` in the MTF module; do not modify `default_features()`.**

Measured reason: `tests/test_pipeline_market_analysis.py:128` asserts every default feature has a
value over a **60-candle** fixture. Adding EMA(200) — warm-up 200 — makes that assertion fail, forcing
a 200+ candle fixture into a suite that runs in 3.9 s, and silently changing `analyze_symbol`'s output
for every existing caller.

Two *named* sets with stated purposes (`default_features` = general snapshot; `swing_features` = the
v3 prompt's inputs) is clearer than one set that means "whatever the last milestone needed".

**Verified:** `ExponentialMovingAverage(200)` works today. `1d` with 400 candles → `ema_200 =
73850.72`; `1w` with 300 candles → `ema_200 = 69162.99`. No warm-up in either.

### 5.9 Testing strategy

Target **≥55 tests**, mirroring AF's structure.

| Group | Coverage |
|---|---|
| Composition | Three views built; role order; delegation equals calling `structural_facts_for_symbol` directly per view |
| Roles | Never inferred from the interval; duplicate roles rejected; single-view sheet valid |
| D1 containment | One `DetectionSettings` reaches every view — **AST-asserted**, as in AF |
| Determinism | Equal inputs → equal sheets; no clock; **zero arithmetic** (AST); cross-process hash stability under four `PYTHONHASHSEED` values |
| Staleness | Per-view `as_of` preserved; `newest_as_of` is the maximum; differing `as_of` rendered per view |
| Failure | One timeframe short → raises; **no partial sheet** |
| Features | `swing_features()` includes `ema_200`; `default_features()` **unchanged** (regression) |
| Fact-only | Rendered output free of the 14 forbidden terms; **no agreement/alignment vocabulary** |
| Renderer | All three views rendered; role headers; per-view age; limitations incl. AG-1/2/3 |
| CLI | Registry completeness; unique names; role flags; exit codes; `mtf` and `facts` both reachable |
| Guards | Nothing outside `fmis.pipeline` imports it; importing an engine does not load it |

**Mutation pass: ≥30 probes, zero survivors required.** A survivor is a test gap until proven an
equivalent mutant. AF's lesson must be applied from the start: *asserting that a label appears is not
asserting that the fact is right* — assert values, not presence.

**Benchmark:** three-timeframe end-to-end wall time, and confirmation that cost is ~3× a single sheet
with no superlinear surprise. Baseline measured today: **1.5 s including network.**

### 5.10 Documentation

Design document · ADR-0023 · independent review · `CURRENT_STATE.md` · three indexes. Same standard as
AF: the ADR records decisions and rejected alternatives; the review re-derives every claim from
production code and reports P0–P3 honestly.

### 5.11 Acceptance criteria

- [ ] `fmits mtf BTCUSDT` prints a role-labelled 1W/1D/4H sheet from live data
- [ ] Each view shows its own `as_of` and age; no shared timestamp is implied
- [ ] The three structural trends appear side by side with **no derived agreement field**
- [ ] `ema_200` present in the MTF views; `default_features()` byte-identical to today
- [ ] One `DetectionSettings` reaches every view — AST-asserted
- [ ] Zero arithmetic operators in the new module — AST-asserted
- [ ] No clock beneath the CLI — source-asserted
- [ ] A short timeframe raises; no partial sheet is ever returned
- [ ] Rendered output free of interpretation vocabulary
- [ ] Full suite green including `-W error`; **no existing test modified except by documented widening**
- [ ] ≥30 mutation probes, **zero survivors**
- [ ] ADR-0023, design and review records complete; all indexes updated

### 5.12 Success metrics

| Metric | Target |
|---|---|
| New engines added | **0** |
| Engine source modified | **0 files** |
| New tests | ≥55 |
| Mutation survivors | **0** |
| Coverage of new modules | ≥98 % |
| Suite runtime | < 5 s |
| Three-timeframe wall time | < 3 s incl. network |
| Elapsed build time | 1–2 weeks at the assumed rate |
| Value ladder | Level 1 → **Level 1.5**; workflow B's deterministic step complete |

### 5.13 Out of scope — explicitly

Regime or any cross-timeframe verdict · support/resistance naming · scanning or multi-symbol ·
watchlists · persistence · scheduling · alerts · JSON or any machine-readable output · AI · portfolio
· risk · a second provider · non-crypto assets · a workspace, TUI or GUI · changing
`default_features()` · fixing ADR-0020 D1 · new indicators beyond adding existing EMA(200) to a named
set.

**If any of these appears in the branch, the milestone has failed its contract.**

---

## 6. Architectural unknowns settled here

The brief asks that anything still unclear be identified now. Six were; all six are decided above, and
none blocks implementation.

| # | Question | Decision |
|---|---|---|
| U1 | Does MTF widen `FeatureSet` identity (`ARCH` D11)? | **No.** Compose *above* — three sheets, three identities. D11 stays deferred, as `ARCH` and Report 0003 both prescribe |
| U2 | Should views be time-aligned? | **No.** Alignment serves arithmetic; nothing computes across timeframes. Per-view `as_of` reported instead |
| U3 | Does the sheet state cross-timeframe agreement? | **No.** That is the Regime Engine's job (§5.7) |
| U4 | Are roles inferred from intervals? | **No.** Explicitly supplied, per ADR-0009's precedent |
| U5 | Does `default_features()` gain EMA(200)? | **No.** `swing_features()` instead — measured reason in §5.8 |
| U6 | Does D1 need fixing first? | **No.** MTF reuses one composition root; containment holds. D1 is required before **regime** |

**One unknown remains open and is deliberately not decided here:** the serialization schema for
machine-readable output (`ARCH` §13.8). It is out of scope for AG and must be settled before either
persistence (Phase 5) or feeding the fact sheet to an AI layer. Recommend it be taken as its own small
decision milestone, not folded into a feature.

---

## 7. What this defers, and when each returns

| Deferred | Returns at | Trigger |
|---|---|---|
| **ADR-0020 D1 provenance** | Immediately after AG | The Regime Engine is caller #2 |
| **Market Regime Engine** | After D1 | Needs MTF (this milestone) and D1 |
| **Swing Trading Workspace (R1)** | After regime | Then it has something to show |
| **Five-surface consolidation (R2)** | When ≥3 surfaces exist | Report 0004 §16.4 |
| Watchlist + Global Market Pulse | Phase 2, after AG | Cheap; better informed by usage |
| Persistence / run recording | Phase 5 | Needs the serialization decision |
| JSON output | After the serialization decision | `ARCH` §13.8 |
| CI + type checking | Any time — **parallel, not sequential** | Should not wait for a milestone slot |

**The forced ordering, stated once:**

```
AF (done) → AG Multi-Timeframe → D1 provenance → Regime → Swing Workspace → v1
```

---

## 8. Planning phase statement

> ## **Planning phase complete.**

**Justification.**

The project now has, in order: an audit of what the code is (0001), a map of what the system is
(0002), a layered technical architecture (0003), a capability and business architecture (0004), a
phased roadmap with a value ladder (0005), one executed implementation milestone with an ADR, a design
record and an independent review (AF), and — in §5 above — an implementation contract specific enough
to begin immediately.

Six architectural unknowns were open when this gate started. All six are decided (§6). The one
remaining open question — the serialization schema — is **out of scope for AG and does not block it**;
it becomes decision-blocking only at persistence or AI integration, and §7 places it accordingly.

**What would have justified continuing to plan, and does not apply:**

- *An undefined next milestone.* AG is defined to the level of module names, function signatures,
  invariants, acceptance criteria and out-of-scope items.
- *An unresolved architectural conflict.* The MTF-versus-`ARCH` D11 tension that Report 0004 §18.5
  flagged as the sharpest mismatch in the project is resolved in U1: compose above, do not widen
  identity below.
- *Unquantified risk.* The two live risks — the D1 hazard and the single-timeframe misreading — are
  both measured, not asserted (36.1 % of mismatched calls; the 1W/1D/4H divergence on real data).
- *No evidence the approach works.* AF proved the composition-first approach end to end in one
  milestone, with zero engine changes and zero mutation survivors.

**The one thing that should now happen in parallel with building, not before it:** *use the system.*
Report 0005 §11.7's instruction stands — run the fact sheet daily and record what is consulted and what
is ignored. That record is the only legitimate input to the workspace decision this gate has deferred,
and it accumulates only by using what exists.

Further planning would now produce documents rather than capability. **Build AG.**

---

*Report 0006 · Milestone AF Architecture Gate · 2026-08-02 · `d132cea` + AF*
*Series: [0001](0001_2026-07-31_REPOSITORY_AUDIT.md) · [0002](0002_2026-07-31_FMITS_MASTER_MAP.md) · [0003](0003_2026-08-01_FMITS_ARCHITECTURE_BLUEPRINT_V1.md) · [0004](0004_2026-08-01_FMITS_BUSINESS_AND_CAPABILITY_ARCHITECTURE_V1.md) · [0005](0005_2026-08-01_FMITS_DEVELOPMENT_ROADMAP_2026_2027.md) · **0006 Architecture Gate***
