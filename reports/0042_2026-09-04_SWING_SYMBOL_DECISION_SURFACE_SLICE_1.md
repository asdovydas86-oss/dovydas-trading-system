# Swing Product Slice 1 — The Symbol Decision Surface

| Field | Value |
|---|---|
| **Report number** | 0042 |
| **Title** | Swing Product Slice 1 — The Symbol Decision Surface |
| **Date** | 2026-09-04 |
| **Report type** | Implementation (product) |
| **Model** | Claude Opus 5 (1M context) |
| **Repository branch** | `main` |
| **Audited commit** | `666723bc667ecaa074bf3df759142cd29d20a802` |
| **Status** | Complete |
| **Scope** | Carry per-symbol decision information across the seam that destroyed it, and put it on the page. **No trading-policy change of any kind.** Not freshness engineering, not new strategy logic, not a dashboard redesign. |

---

## 1. The problem, stated first

The operator's verdict on the existing Swing dashboard was:

> *"Today I cannot make a better swing-trading decision with this system."*

The Swing Product Capability Audit established that this was **not** a shortage
of analysis. FMITS computes, for every scanned symbol, a full `SetupAssessment`
— a state, a decision-context sufficiency verdict, a thesis, the directional
families it tallied with each family's lean, observation and source interval,
and the regime reading behind the gate. `fmis.setup_evidence` will project a
complete evidence report off any of them, `WAIT` included.

**Almost none of that reached the operator.** It was computed on every refresh
and thrown away one layer before the screen.

## 2. Root cause, confirmed

Two seams, both confirmed in the code at the audited commit.

### 2.1 `no_trade_groups` — the seam that mattered

`fmis.swing_workspace.sections.no_trade_groups` was the **only** path by which a
`WAIT` symbol reached the workspace. It folds every waiting symbol into:

```python
NoTradeGroup(reason: str, classification: str, symbols: tuple[str, ...])
```

Three fields. A symbol arrives as **a name inside a list of names**, under one
sentence shared with every other symbol that reached the same conclusion. Its
regime reading, its directional families, its sufficiency, its `as_of` and its
entire evidence report reached the workspace nowhere at all.

The consequence on the surface: `SwingView.row_for` — the lookup the
`/swing/SYMBOL` route used — consults `opportunities` and `wait_list` only. A
waiting BTCUSDT therefore had **no row anywhere**, and the detail route answered:

> *"BTCUSDT is not an actionable or waiting setup on this refresh."*

…while the engine had in fact produced a complete assessment for it.

### 2.2 `evidence_digest_for` — counts, not evidence

The evidence attachment reduced a whole `SetupEvidenceReport` to four integers
plus two flags, and was built for *actionable* rows only. Four integers cannot
tell two `WAIT` symbols apart, cannot be checked by hand, and carry none of the
`statement`, `observed`, `source`, `scope`, `families`, `correlated_with` or
`independence_note` that `fmis.setup_evidence` had already produced per item.

### 2.3 The third seam — measured, and deliberately deferred

`build_setup_inputs` computes all three timeframe regimes and carries only the
**context** role's three dimensions into `SetupInputs`; per-view `as_of` is
likewise dropped in favour of one `newest_as_of`. Closing that seam requires
widening `SetupInputs`, which changes `SetupAssessment.regime_context` — a
change to assessment output, which §5 of this milestone forbids. **Deferred to
Slice 2**, explicitly, in §12 below.

## 3. Architecture chosen

The stated preference, followed exactly:

```
existing deterministic calculation
  → existing structured evidence  (project_setup_evidence, unchanged)
    → narrow Swing product projection  (SymbolDecision)     ← NEW
      → workspace  (SwingWorkspace.decisions)               ← NEW FIELD
        → renderer  (SymbolDecisionRow → HTML)              ← NEW
```

Three properties held deliberately:

* **No trading logic is duplicated in the dashboard.** The renderer reads a
  model and formats it. Every value on the page was produced by an engine.
* **No parallel representation.** `SymbolDecision` carries `SetupAssessment`'s
  and `SetupEvidenceReport`'s own fields; the existing `SetupRow`,
  `EvidenceDigest`, `NoTradeGroup` and `RankedSetup` contracts are untouched.
* **One rule, one place.** `no_trade_groups` and `symbol_decisions` now both
  derive `reason` and `classification` through the same two helpers
  (`_reason_of`, `_classification_of`), so the grouped section and the
  per-symbol row cannot describe one symbol differently. A test asserts it.

`SwingWorkspace.decisions` **spans** the three decision sections rather than
partitioning them, and the existing section-exclusivity check deliberately does
not consult it — overlapping is what it is for. A separate rule requires one
decision record per symbol, and `symbol_decisions` honours it by keeping the
first record for a repeated symbol rather than rejecting the page (the
`fmits workspace BTCUSDT BTCUSDT` case the repository already had a test for).

## 4. Files changed

| File | Change |
|---|---|
| `src/fmis/swing_workspace/models.py` | `FactorLine`, `EvidenceLine`, `SymbolDecision`; `SwingWorkspace.decisions`, `decision()`, one-decision-per-symbol rule |
| `src/fmis/swing_workspace/sections.py` | `symbol_decisions()`; `_reason_of` / `_classification_of` shared with `no_trade_groups` |
| `src/fmis/swing_workspace/builder.py` | wires `decisions`; adds limitation **WS-11** |
| `src/fmis/swing_workspace/__init__.py` | exports |
| `src/fmis/operator_dashboard/models.py` | `FactorRow`, `EvidenceItemRow`, `SymbolDecisionRow`; `SwingView.decisions`, `decision_for()` |
| `src/fmis/operator_dashboard/sections.py` | `symbol_decision_rows()` |
| `src/fmis/operator_dashboard/render.py` | per-symbol table on `/swing`; `_decision_detail`; `_symbol_page` now serves every assessed symbol |
| `src/fmis/operator_dashboard/theme.py` | three lean chip classes, both directions weighted identically |
| `src/fmis/operator_dashboard/__init__.py` | exports |
| `tests/swing_decision_helpers.py` | **new** — offline fixtures for the three decision exits |
| `tests/test_swing_symbol_decision.py` | **new** — 30 tests |
| `tests/test_swing_symbol_decision_non_vacuity.py` | **new** — 7 tests |
| `tests/test_swing_setup_policy_non_regression.py` | **new** — 4 tests, 81-fixture baseline |
| `tests/test_operator_dashboard_architecture.py` | guard widened for one new lookup (`decision_for`) |
| `tests/test_operator_dashboard_render.py` | one assertion narrowed with the wording it tests |

Nothing under `fmis/swing_setup/`, `fmis/setup_evidence/`, `fmis/decision_context/`,
`fmis/market_regime/`, `fmis/structural_trend/` or `fmis/today/` was modified.

## 5. Data preserved that was previously lost

For **every** scanned symbol, in every state:

| Previously lost | Now carried |
|---|---|
| per-symbol identity of a `WAIT` result | one `SymbolDecision` per symbol |
| decision-context sufficiency | `sufficiency` |
| the full thesis (only line 1 survived, shared) | `thesis` |
| regime reading behind the gate | `regime_context` |
| every directional family | `factors` — family, lean, observed value, source interval |
| the evidence report, item by item | `supporting` / `conflicting` / `missing` / `unavailable` |
| each item's statement, observed value, source, scope, families | `EvidenceLine` fields |
| **`correlated_with` and `independence_note`** | carried and rendered as *not independent* |
| independence caveats, evidence warnings, open questions | carried |
| the assessment instant | `as_of` |

## 6. Dashboard changes

**`/swing`** gains a first section, *Every scanned symbol*: one row per symbol —
`Symbol · Status · Direction · Classification · Current condition (the engine's
own words)` — each linked to its detail page. The grouped *No trade* table
stays, now labelled as a distribution over named conditions rather than the only
per-symbol carrier.

**`/swing/SYMBOL`** now resolves for every assessed symbol, not only actionable
ones, and renders four panels: **decision** (status, classification,
sufficiency, condition, full thesis, `as_of`), **timeframe and regime context**,
**directional families** (the table that makes a split visible), and
**evidence** (four groups as item tables with family, scope/source and an
explicit independence column, plus caveats, warnings and open questions). An
actionable symbol keeps all its previous panels and gains these.

## 7. Policy non-regression proof

**Boundary chosen:** `setup_assessment_for_sheet` — the composition root the
live product enters through, which runs the whole chain (three regime
evaluations → evidence report → decision context → `build_setup_inputs` →
`evaluate_setup`). A baseline here covers every stage Slice 1 could have
disturbed, not just the policy function.

**Canonical representation:** each assessment and each evidence report
canonicalised as its `repr()`. For a frozen, slotted dataclass that is a
complete recursive field-by-field rendering — every nested `PriceLevel`,
`DirectionalFactor`, `Trigger`, `RiskReward`, `EvidenceItem` and
`ConfluenceSummary`, enum members with their values, floats with `repr`'s exact
round-trip. Nothing normalised away, no field excluded, no tolerance applied.
This is **stricter** than an equality check on a hand-listed subset of fields,
which is what it was chosen over. The comparison was not weakened to pass.

**Matrix:** 27 seed triples × 3 symbols = **81 fixtures**, over synthetic seeded
candles — offline, network-free, clock-free. It covers all three `WAIT` exits
and `CANDIDATE`; a fourth test asserts that coverage, so a matrix that silently
stopped exercising the paths would fail rather than pass vacuously.

**Result:**

```
before:  81 records, sha256 096a575a015f1e0ed991a049033993b90350b36be6361458d07fbcc36b4a7a42
after:   81 records, sha256 096a575a015f1e0ed991a049033993b90350b36be6361458d07fbcc36b4a7a42
state distribution unchanged: 72 WAIT, 9 CANDIDATE
```

**Byte-identical.** The per-fixture digests are committed in
`tests/test_swing_setup_policy_non_regression.py`, so any future change to the
policy breaks the test and names the seed triple that moved.

## 8. Tests added

**41 new tests**, all offline and deterministic (no provider, no clock, no
filesystem, no network in any call graph).

**Full suite: 14,061 → 14,102 passing under `-W error`, in 11:33.** The delta is
exactly the 41 tests added — no test elsewhere was removed, disabled or
renamed. **No failures, no new warnings, and no skips** (`-ra` is in `addopts`,
so a skip would have been reported; none was).

| Module | Tests | Covers |
|---|---|---|
| `test_swing_setup_policy_non_regression.py` | 4 | policy non-regression; matrix-coverage guard |
| `test_swing_symbol_decision.py` | 30 | projection, WAIT evidence, per-symbol preservation, the two distinct WAIT paths, independence disclosure, **no-ranking guards**, routing/detail, research boundary, one-decision-per-symbol |
| `test_swing_symbol_decision_non_vacuity.py` | 7 | §9 below |

The no-ranking guards are the architectural ones: a regex over both models'
field names rejecting `score|rank|closeness|confidence|probabilit|weight|
strength|percentile|priority|opportunity_|likelihood|conviction`; an
order-reversal test proving scan order is the only order; and a check that the
rendered table carries no ordering column and states that its order means
nothing.

## 9. Non-vacuity proof

Demonstrated **directly** against pre-Slice-1 code that is still in the
repository and still unmodified — `no_trade_groups`, `evidence_digest_for` and
`SwingView.row_for` — rather than by test-count increase.

* `NoTradeGroup` has exactly three fields (asserted), and every fact the new
  record carries about a symbol is asserted **absent** from what the old carrier
  produced: regime line, sufficiency, each factor's observed value and source,
  each evidence item's statement and observed value.
* Two symbols reaching the same conclusion produce **one** old group with two
  names in it and **two** new records with different evidence.
* `evidence_digest_for` is asserted to have no `statement`, `observed`,
  `source`, `scope` or `correlated_with` attribute, and its `repr()` is asserted
  to contain no `structure=`, no `1w`/`1d`, no `sustained_higher`/`sustained_lower`
  — the four things that distinguish an early regime rejection from a
  weekly-versus-daily conflict.
* `row_for` is asserted to return `None` for both waiting symbols while
  `decision_for` returns a record for both.
* The rendered detail page for a waiting symbol is asserted to no longer contain
  the refusal and to contain all four panels.

Each of these would fail against the pre-Slice-1 surface.

## 10. Manual live verification (2026-09-04, live Binance data)

Run on port **8899**, leaving the operator's instance on 8787 untouched.
Watchlist: BTCUSDT BNBUSDT ETHUSDT SOLUSDT XRPUSDT.

All ten routes answered `200` (`/`, `/markets`, `/swing`, `/portfolio`,
`/paper`, `/performance`, `/lab`, `/geometry`, `/validation`, `/system`), plus
`/swing/BTCUSDT` (32,592 bytes) and `/swing/NOSUCHUSDT` (the honest refusal).

**The live per-symbol table:**

```
BTCUSDT | wait | read and declined | Context-role (1w) regime structure is transitioning, not trending…
BNBUSDT | wait | read and declined | Directional factors do not agree: 1 long, 1 short, 1 conflicting…
ETHUSDT | wait | read and declined | Context-role (1w) regime structure is transitioning, not trending…
SOLUSDT | wait | read and declined | Context-role (1w) regime structure is transitioning, not trending…
XRPUSDT | wait | read and declined | Context-role (1w) regime structure is ranging, not trending…
```

Three distinct named conditions across five symbols, where the previous page
would have shown grouped rows.

**BTCUSDT detail — the audit's finding, now visible:**

```
status                        wait
classification                read and declined
decision-context sufficiency  sufficient
current condition             Context-role (1w) regime structure is transitioning, not trending.
assessment as of              2026-09-04T04:00:00+00:00
regime                        context (1w): structure=transitioning, volatility=steady, participation=typical

directional families
  context_structural_trend  | conflicting | neutral                 | fmis.structural_trend (1w)
  setup_structural_trend    | long        | sustained_higher        | fmis.structural_trend (1d)
  setup_evidence_alignment  | long        | watch (dominant=upward) | fmis.decision_support

evidence   agreeing families: trend, momentum   conflicting: trend   independence: NOT ESTABLISHED
  supporting(2)  factor:setup_structural_trend    sustained_higher  trend  1d  → not independent
                 factor:setup_evidence_alignment  watch (upward)    trend, momentum → not independent
  conflicting(1) factor:context_structural_trend  neutral           trend  1w  → not independent
```

Six evidence rows on that page carry the *not independent* marker.

This is precisely the audit's BTC case: **two of three families lean long, and
the weekly regime gate rejected the symbol before the tally ever ran.**

**BNBUSDT detail — a materially different case:**

```
current condition   Directional factors do not agree: 1 long, 1 short, 1 conflicting, 0 unavailable.
regime              context (1w): structure=trending   ← the gate PASSED
                    volatility=contracting, participation=typical

directional families
  context_structural_trend  | short       | sustained_lower        | fmis.structural_trend (1w)
  setup_structural_trend    | long        | sustained_higher       | fmis.structural_trend (1d)
  setup_evidence_alignment  | conflicting | wait (dominant=upward) | fmis.decision_support
```

**Weekly `sustained_lower` against daily `sustained_higher`** — a real
higher/lower-timeframe structural conflict, reached *after* clearing the gate
BTC failed. Exactly the distinction the audit named, and it is legible on the
page without reading any code.

**Checks passed:** no synthetic score, no ranking column, no opportunity or
confidence number anywhere; every non-independent evidence item is marked
*not independent* with the projection's own note; no text implies validated
profitability.

## 11. Research boundary

CA (NO_EDGE), CB (UNDERPOWERED), CC (INFEASIBLE) and CD (dependence exists; the
initial design-effect interpretation was overstated, and the corrected
diagnostics still reject the independent-cluster assumption) are **not** rewritten
or reinterpreted anywhere in this change.

The distinction this milestone keeps explicit: those conclusions forbid the
dashboard from claiming a validated edge, a calibrated probability or a
confidence score. They do **not** forbid it from showing deterministic market
analysis and explaining why a symbol is `WAIT`. Slice 1 does the second and
nothing of the first. Enforced by:

* the no-ranking field guards on both models;
* `WS-11`, which states that scan order carries no meaning;
* a rendered-page assertion rejecting any quantified edge claim
  (`expected return|win rate|hit rate|edge|probability|confidence` adjacent to a
  number) while permitting the page's own **denials** of exactly those things;
* the page's standing text: *"No probability, confidence or expected return is
  computed anywhere on this page."*

## 12. Deferred to Slice 2

1. **Per-view `as_of` and full freshness policy.** `SetupInputs` carries one
   `newest_as_of`; per-view instants are dropped in `build_setup_inputs`.
   Slice 1 carries the assessment's own `as_of` and labels it as exactly that,
   making **no** claim about whether it is recent enough to act on. The
   MarketSnapshot producer/freshness architecture is Slice 2's.
2. **Setup-role and execution-role regime dimensions.** Computed in
   `setup_inputs_and_assessment_for_sheet`, discarded in `build_setup_inputs`.
   Carrying them changes `SetupAssessment.regime_context`, which §5 forbids
   here; it belongs with a deliberate, proven assessment-output change.
3. **The terminal `fmits workspace` renderer** does not show the new section.
   The model carries it; only the dashboard renders it.
4. EP-21 refresh UX, scan memory and alerts remain out of scope and untouched.

## 13. Product acceptance gate

**Before Slice 1 — what could the operator see for BTCUSDT?**

On `/swing`: the symbol's name inside a comma-joined cell in a grouped *No
trade* row, beside one sentence shared with every other symbol that reached the
same conclusion. On `/swing/BTCUSDT`: *"BTCUSDT is not an actionable or waiting
setup on this refresh."* — one sentence, no evidence, no factors, no regime.

**After Slice 1 — what can the operator see?**

Its own row, and a 32 KB detail page carrying: the status and classification,
the decision-context sufficiency, the engine's verbatim condition, the full
thesis, the assessment instant, the weekly regime reading with all three
dimensions, all three directional families with each one's lean, observed value
and source timeframe, and the complete evidence report — every item with its
statement, observed value, family, scope, source, and an explicit independence
column carrying the projection's own correlation notes and caveats.

**What can Dovydas do after this milestone that he could not before?**

He can open BTCUSDT and see **why** it is waiting — that two of three families
lean long and the weekly regime gate stopped it first — and open BNBUSDT and see
that it is waiting for an entirely different reason: it *cleared* that gate and
then hit a weekly-short-versus-daily-long structural conflict. Before this
milestone both were one line of shared text, and the system could not tell him
they were different situations. It now can, per symbol, with the evidence
attached and the non-independence of that evidence stated rather than implied.
