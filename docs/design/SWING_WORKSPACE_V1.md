# Swing Trading Workspace v1 — Design

**Milestone:** AK
**Status:** Implemented
**Date:** 2026-08-04
**Executes:** the Milestone AJ workspace architecture, followed without redesign

---

## 1. The problem, measured

Before this milestone the owner assembled a swing analysis by hand from three
commands and a chart. Worse, the repository contained **1,131 statements of
accepted, ADR-governed, fully-tested code that no product surface could reach**:

| Package | Statements | Test files | Production importers before AK |
|---|---:|---:|---|
| `fmis.decision_support` — `EvidenceReport` v1 (ADR-0008) | 674 | 16 | **none** |
| `fmis.evidence` — the ten-family taxonomy (ADR-0011) | 291 | 11 | **none** |
| `fmis.trading_context` — `TradingObjective` (ADR-0009) | 166 | 13 | **none** |

Report 0003 named the "two islands" problem — measurement and structure with no
import edge — and AF/AG/AH/AI joined them. This was the **third island**, and the
Swing Workspace is the surface all three were designed for.

## 2. Scope

**In:** the `Workspace` model as a first-class object · a section registry · seven
deterministic sections · deterministic conflict detection · a terminal renderer ·
`fmits swing` · tests · this design · an independent review.

**Out, and rendered as explicitly unavailable:** risk · portfolio · trade plan ·
AI interpretation. **Out entirely:** news, macro, on-chain, derivatives — which
appear as *catalogued families with no descriptor* in §5 rather than as sections.

## 3. The design questions, resolved

### 3.1 Is the workspace an object or a command?

**An object.** `Workspace` is frozen, complete, schema-versioned and serializable
in shape. The CLI renders one; a future Telegram renderer, dashboard or JSON
serializer will render the same instance. Nothing about the page lives in the
command.

### 3.2 Where does it sit?

A **new top layer**, `fmis.workspace`, above both `fmis.pipeline` and
`fmis.decision_support`. It could not live lower: `decision_support` sits above
the pipeline by ADR-0008 §1, and the workspace consumes both.

`fmis.pipeline.cli` imports it, which is safe because `fmis.pipeline.__init__`
does not import `cli` — so no cycle exists, and a test asserts importing
`fmis.pipeline` still does not load `decision_support`.

### 3.3 How are unbuilt sections represented?

As an `Unavailable` model, never a placeholder string. It carries the **owning
milestone** and a **prohibition** — the inference its absence forbids:

> *"No position size shown here would be legitimate. Do not infer one."*

An omitted section is invisible, and an invisible gap reads as a gap that does
not exist. `SPEC` §6 requires missing data as a first-class output and `SPEC` §7
names excessive confidence from incomplete data as a bias to guard against.

`Section` **cannot** carry `UNAVAILABLE` status — the model rejects it — so the
two kinds cannot be confused, while both expose the same six-member surface a
renderer walks.

### 3.4 How does evidence integrate without duplication?

Two shipped packages already own it, and the join between them turned out to be
free: **`Observation.key` is already the `EvidenceDescriptor` name.** The
workspace calls `evidence.find(observation.key)` to place each observation in its
family. It re-implements no grouping, no classification and no alignment rule.

`build_evidence_report` needs an `AnalysisSnapshot`, and a `StructuralFactSheet`
already carries every field one requires. `snapshot_from_sheet` is therefore a
**copy, not a computation, and costs no second fetch** — the same adapter pattern
`regime_input_from_sheet` established in AI. Calling `analyze_symbol` instead
would fetch the same candles twice and could return a different window if a
candle closed between the calls, putting two `as_of` values on one page.

### 3.5 What may conflict detection do?

**Report, never resolve.** ADR-0023 forbids deriving anything from the
combination of views and ADR-0025 forbids collapsing a regime's dimensions. Both
leave a real gap: nothing had ever *said out loud* that 1W and 4H disagree, even
though both facts were printed side by side.

Stating that they differ produces no third value — the compared values are
already on the page. What would cross the line is picking a winner, weighting a
timeframe, or emitting a net direction, and a test scans the module for that
vocabulary.

Five kinds, and the exclusions matter as much as the inclusions:

| Kind | Fires when | Deliberately does not fire |
|---|---|---|
| `STRUCTURAL_TREND` | two roles sustained in opposite senses | against `NEUTRAL` or `INDETERMINATE` — absence is not disagreement |
| `REGIME_STRUCTURE` | trending against ranging | against `TRANSITIONING` / `INSUFFICIENT` — not opposites of anything |
| `REGIME_INDETERMINATE` | a regime's own families disagreed | on `INSUFFICIENT`, which is missing evidence, not conflict |
| `EVIDENCE_DISAGREEMENT` | `decision_support` grouped conflicting observations | — |
| `EVIDENCE_TIE` | no dominant alignment | — (ADR-0008 §5: a tie is reported, never broken) |

### 3.6 What is the section order, and why?

Fixed in `SECTION_ORDER`, validated on every `Workspace`, and asserted by test:

**instrument → regime → structure → levels → evidence → conflicts → risk →
portfolio → trade plan → interpretation → limitations**

Data quality first, because every reasoning failure in `docs/analysis-notes.md`
happened on top of data the reader assumed was sound. Regime second, from two
independent sources that agree — `SPEC` §5 puts the higher timeframe's
environment before the setup, and the v3 prompt's own first correction was
*"regime classification first"*. Structure third, so the environment is known
before a directional impression forms inside it. Conflicts before every planning
section, so nothing is planned around evidence that disagrees. Interpretation
last, so a model's narrative cannot anchor the facts above it.

### 3.7 What does the renderer do?

**Only render.** It imports `fmis.workspace.models` and nothing else, and calls
no builder and no engine — both asserted. Block dispatch goes through an explicit
type→function mapping, so an unregistered block raises rather than rendering
silence.

The contract that makes future surfaces safe: a renderer may **drop** sections
and **shorten** values; it may never **add** a claim, **reorder** sections, or
**change a tier**.

## 4. Invariants, each test-enforced

| # | Invariant | How |
|---|---|---|
| I1 | Every section is present, unrepeated, in canonical order | validated in `Workspace.__post_init__` |
| I2 | A `Section` cannot claim `UNAVAILABLE` | rejected at construction |
| I3 | An unavailable section names its owner and a prohibition | non-empty fields required |
| I4 | Conflicts are never resolved, ranked or scored | vocabulary scan over the module |
| I5 | Conflict output is independent of input order | roles sorted before pairing; asserted both ways |
| I6 | Absence never becomes disagreement | `NEUTRAL`/`INDETERMINATE`/`INSUFFICIENT` cases asserted |
| I7 | No provider computes a market quantity | AST: no `Sub`/`Mult`/`Div`/`Pow`/`Mod` in `sections.py` |
| I8 | The builder calls no engine directly | AST over call names |
| I9 | The renderer imports only the model | AST over imports |
| I10 | No page line exceeds 78 columns | every line of a rendered page |
| I11 | No trading vocabulary on the page | whole-word scan, with denials asserted separately |
| I12 | Evidence families come from the catalogue, never guessed | `find()` resolves every observation key |

## 5. Measured results

**Correctness.** 3,702 tests pass, identically under `-W error` (3,582 before AK;
**+120**). Coverage is **100 %** on all six workspace modules and on
`pipeline/cli.py`. Public exports 212, zero collisions. Import cycles **0**.
Runtime dependencies **0**. `pyproject.toml` and `uv.lock` untouched.

**Mutation.** See the review §6 for the full result.

**Reachability.** `fmis.decision_support`, `fmis.evidence` and
`fmis.trading_context` now have a production importer for the first time.

## 6. What it does not claim

No direction, no recommendation, no score, no ranking, no trade plan, no sizing,
no interpretation. The workspace assembles facts other layers computed, states
where they disagree, and shows what it cannot tell you. Every section that could
mislead by its absence says so on every run.
