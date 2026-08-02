# Repository Audit — `dovydas-trading-system` (FMITS)

| Field | Value |
|---|---|
| **Report number** | 0001 |
| **Title** | Repository Audit |
| **Date** | 2026-07-31 |
| **Report type** | Audit |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `d132cea` |
| **Status** | Final |

**Method:** static inspection + import-graph extraction + full test run + stdlib-`trace` coverage measurement
**Scope:** read-only. No source, test, doc, or config file was modified; no git state was changed; no packages were installed. Working tree was clean and in sync with `origin/main` at audit time.

---

## 1. Repository at a glance

| Metric | Value |
|---|---|
| Tracked files | 164 |
| Production Python | 74 files · **11,128 LOC** (`src/fmis/`) |
| Test Python | 32 files · **21,009 LOC** (`tests/`) |
| Test:source LOC ratio | **1.89 : 1** |
| Test functions / collected tests | 1,934 / **3,221** |
| Test result | **3,221 passed** in 3.84 s |
| Measured line coverage | **96 %** (3,485 / 3,642 statements) |
| Documentation | 50 Markdown files · **14,905 lines** |
| Runtime dependencies | **zero** (stdlib only) |
| Dev dependencies | `pytest>=7` only |
| Commits / span | 83 · 2026-07-04 → 2026-07-31 |
| Python | 3.12 (pinned via `.python-version`, `uv.lock`) |

Two distinct things live in one repo: a small **TradingView-MCP operations workspace** (`config/`, `scripts/`, `prompts/`, `.env.example`) and a large, self-contained **`fmis` Python library**. They share no code.

---

## 2. Major architectural modules

`src/fmis/` — 17 top-level packages, organised as a strict deterministic chain from raw candles to structural interpretation.

### Foundation (L0 — no internal imports)

| Package | LOC | Role |
|---|---|---|
| `data` | 521 | `Candle`, `CandleSeries`, `ObservationSeries`, UTC time contract, candle→observation reduction |
| `evidence` | 358 | `EvidenceFamily` / `EvidenceDescriptor` taxonomy + catalog |
| `trading_context` | 201 | `TradingObjective`, `TradingAnalysisContext` — value objects, no behaviour |

### Deterministic engines (L1–L2)

| Package | LOC | Role |
|---|---|---|
| `features` | 1,213 | Feature Engine, registry, typed contracts; Tier-1 indicators (EMA/ATR/RSI/MACD) + volume statistics |
| `market_structure` | 1,511 | Swing detection, relationships, labels, sequence state, state history |
| `relative_value` | 550 | Correlation, relative return, realized volatility, volatility ratio |
| `alignment` | 190 | Temporal intersection policy across series |
| `ingest` | 333 | Strict candle decoding boundary |
| `providers` | 499 | Binance public klines adapter (stdlib `urllib`) |
| `structural_trend` | 688 | Sustained-run trend policy over sequence state |

### Structural interpretation chain (L3–L6)

| Package | LOC | Depth | Role |
|---|---|---|---|
| `series_context` | 515 | L3 | Series identity + `ContextualSeries` envelope contract |
| `pipeline` | 435 | L3 | `AnalysisSnapshot` orchestration |
| `level_crossing` | 1,304 | L4 | Price levels + crossing events |
| `decision_support` | 821 | L4 | `EvidenceReport`, classification, `WATCH`/`WAIT` verdicts |
| `structure_break` | 827 | L5 | Break of Structure (BOS) |
| `change_of_character` | 650 | L6 | Change of Character (CHoCH) |

The chain the docs describe — `CandleSeries → Swings → Relationships → Labels → Sequence State → Trend → Context → Level Crossing → BOS → CHoCH` — is fully implemented and matches the code.

---

## 3. Dependency graph

```
fmis.data ─────────┬──> alignment ──┐
                   ├──> features ───┤
                   ├──> ingest ──> providers ──┤
                   ├──> relative_value ────────┼──> pipeline ──> decision_support
                   └──> market_structure ──┬──> structural_trend
                                           │            │
                                           └────────────┴──> series_context
                                                                   │
   market_structure ───────────────────────────────────────────────┤
   data ────────────────────────────────────────────────────────> level_crossing
                                                                   │
                              market_structure + series_context ───┴──> structure_break
                                                                              │
                                            level_crossing + series_context ──┴──> change_of_character

fmis.evidence          (L0, no dependents)
fmis.trading_context   (L0, no dependents)
```

**Package-level edges (13 total):**

| From | To |
|---|---|
| `alignment` | `data` |
| `features` | `data` |
| `ingest` | `data` |
| `market_structure` | `data` |
| `relative_value` | `data` |
| `providers` | `data`, `ingest` |
| `structural_trend` | `market_structure` |
| `series_context` | `data`, `market_structure`, `structural_trend` |
| `pipeline` | `alignment`, `data`, `features`, `providers`, `relative_value` |
| `level_crossing` | `data`, `market_structure`, `series_context` |
| `decision_support` | `pipeline` |
| `structure_break` | `level_crossing`, `market_structure`, `series_context` |
| `change_of_character` | `level_crossing`, `series_context`, `structure_break` |

**Depth ladder:** L0 `data`/`evidence`/`trading_context` → L1 `alignment`/`features`/`ingest`/`market_structure`/`relative_value` → L2 `providers`/`structural_trend` → L3 `pipeline`/`series_context` → L4 `decision_support`/`level_crossing` → L5 `structure_break` → L6 `change_of_character`.

The graph is a clean DAG. Dependency direction is one-way in every case, and each package's `__init__.py` docstring names the packages it must never import — a rule the cold-import tests actually verify (`fresh_fmis_imports` fixture in `tests/conftest.py:11`).

---

## 4. Circular dependencies

**None.** Verified by DFS over both the package-level and module-level import graphs.

One apparent module-level self-edge, `providers.binance → providers.binance`, is a **false positive**: it comes from the usage example inside the module docstring (`src/fmis/providers/binance.py:7`), not from executable code. Real imports begin at line 41.

This is a genuinely strong result for a 17-package graph six layers deep, and it is the direct consequence of every package declaring a one-way import contract in its docstring.

---

## 5. Obsolete, duplicated or unused files

### 5.1 Orphan packages — implemented, tested, never consumed

**`fmis.evidence` (358 LOC, 62 tests) has zero production consumers.** No module in `src/` imports it; five packages mention it only in docstrings, as something they must *not* import. Its entire public API (`EvidenceFamily`, `EvidenceDescriptor`, `descriptors`, `descriptors_for`, `find`) is exercised only by `tests/test_evidence_taxonomy.py`.

Compounding this: `fmis.decision_support` builds an `EvidenceReport` (`report.py:429`) via a completely independent path with its own vocabulary in `classification.py`. **Two unrelated modules own the concept "evidence"**, and the one specified by ADR-0011 is the one nothing uses.

**`fmis.trading_context` (201 LOC, 40 tests) also has zero consumers.** This one is documented as intentional (`trading_context/__init__.py:41` — "a leaf that higher layers depend on"), but no higher layer depends on it yet.

### 5.2 Placeholder packages — 6 of 7 still empty

`features/trend`, `momentum`, `volatility`, `market_structure`, `support_resistance`, `pattern_detection` each contain only a docstring, a TODO list, and `__all__: list[str] = []`. `features/volume` graduated to real code (ADR-0010); the rest have not moved since the Feature Engine was built. They are documented placeholders, not accidents — but see finding 7.3, where one has gone stale.

### 5.3 Deliberate duplication — `_require_envelope` ×4

Four byte-similar private validators, one per contextual pipeline:

- `src/fmis/series_context/pipeline.py:172`
- `src/fmis/level_crossing/pipeline.py:129`
- `src/fmis/structure_break/pipeline.py:100`
- `src/fmis/change_of_character/pipeline.py:84`

The duplication is documented and justified (each docstring explains that a caller moving between pipelines "should not meet three wordings of one rule"). But the invariant those docstrings assert — *the messages match exactly* — is enforced by nothing. The tests only assert each name stays private. A copy-edit to one message would silently break the stated contract.

The same pattern repeats structurally: `series_context`, `structure_break` and `change_of_character` each ship an identical `__init__ / models / <domain> / pipeline` quadruple, and `level_crossing` adds one file to the same shape.

### 5.4 Ordering validators — 4 near-siblings, correctly separated

`_validate_key_order` (`market_structure/models.py:336`), `_validate_current_point_order` (:435), `_validate_event_order` (`level_crossing/crossing.py:266`), `_validate_snapshot_history_order` (`structural_trend/models.py:162`). These *look* duplicated but are not: each docstring derives why its strictness rule differs, and `_validate_current_point_order` is an explicit thin adapter over `_validate_key_order`. This is correct as-is — flagged only so a future refactor doesn't collapse them by mistake.

### 5.5 Stale build artifacts (untracked, git-ignored — harmless)

- `src/fmis.egg-info/SOURCES.txt` — 9 lines, predates `change_of_character` and `structure_break`
- `.pytest_cache/`, `__pycache__/` (220 `.pyc`), `.DS_Store`, `.venv/` (~21 MB, the bulk of repo size on disk)

`.gitignore` covers all of these correctly. Nothing stale is tracked.

---

## 6. TODO / FIXME / XXX inventory

**27 `TODO` markers. Zero `FIXME`. Zero `XXX`. Zero `HACK`.** One `NotImplementedError` (`features/types.py:259`), which is a legitimate abstract-method body.

| Location | Count | Nature |
|---|---|---|
| `features/indicators/__init__.py:16-20` | 5 | Planned: EMA slope, RSI MA, ADX, Bollinger Bands, VWAP |
| `features/support_resistance/__init__.py:7-10` | 4 | Planned S/R levels, strength, proximity, role-flip |
| `features/trend/__init__.py:8-11` | 4 | Planned trend direction, strength, EMA distance/stacking |
| `features/momentum/__init__.py:8-11` | 4 | Planned momentum regime, MACD slope, RSI slope, divergence |
| `features/volatility/__init__.py:8-10` | 3 | Planned volatility regime, normalized ATR, BB squeeze |
| `features/market_structure/__init__.py:12-14` | 3 | Planned HH/HL/LH/LL, **BOS/CHoCH**, consolidation vs expansion |
| `features/pattern_detection/__init__.py:13-17` | 3 | Planned candlestick / chart patterns, pattern location |
| `features/types.py:216` | 1 | `TODO(milestone-C-impl)`: typed convenience accessors on `FeatureSet` |

Every marker is a forward-looking roadmap entry inside a declared placeholder. None marks a defect, a workaround, or known-broken code. The single tagged TODO (`milestone-C-impl`) is also referenced from `docs/ARCHITECTURE_AND_ROADMAP_V1.md:438` — the codebase and roadmap agree on it.

---

## 7. Documentation vs implementation

Documentation quality here is unusually high — 21 ADRs, 6 design docs, 7 independent review records, one ADR per decision with alternatives and consequences. The inconsistencies below are drift in the *summary* documents, not in the decision records.

### 7.1 Root `README.md` — describes a repository that no longer exists (highest severity)

`README.md:10-15` lists the structure as `config/`, `scripts/`, `docs/`, `prompts/`. It **never mentions `src/` or `tests/`** — 11,128 lines of production Python and 21,009 lines of tests are invisible to anyone landing on the repo. The one-line summary ("Personal trading automation workspace… for working with TradingView Desktop") describes what the repo was at commit 1 of 83.

### 7.2 `docs/ARCHITECTURE_AND_ROADMAP_V1.md` — marked authoritative, ~2 months stale

`docs/README.md` labels it **"Authoritative — architecture"**. Its own header (line 3-5) says:

> **Status:** Proposal … **Repository baseline:** `e0ba4c1b…` (MACD milestone), 147 passing tests

Today: 3,221 tests. Its §2.1 directory tree and §2.2 "current internal dependency graph (verified)" predate **7 of the 17 packages**. Grep confirms zero occurrences of `structural_trend`, `series_context`, `level_crossing`, `structure_break`, `change_of_character`, `decision_support`, or `trading_context` anywhere in the file. Its "outside `src/`" block claims "8 test modules, 147 tests"; there are 32 and 3,221.

`docs/ARCHITECTURE_REVIEW_2026-07-24.md` is billed as amending §5 only, so it does not repair the tree or the graph.

### 7.3 A placeholder TODO now contradicts shipped code

`src/fmis/features/market_structure/__init__.py:13` still reads:

> `TODO: break of structure (BOS) / change of character (CHoCH)`

BOS shipped in Milestone AD (`fmis.structure_break`, 827 LOC) and CHoCH in Milestone AE (`fmis.change_of_character`, 650 LOC). ADR-0012 already corrected this same file's *swing-detection* claim (`market_structure/__init__.py:78` notes "the placeholder there no longer claims swing…"), but the BOS/CHoCH line was not revisited when AD/AE landed. A reader of that package is told two implemented subsystems are unbuilt.

`features/trend/__init__.py:8` has a milder version of the same issue — "TODO: trend direction (up / down / sideways)" alongside a shipped `fmis.structural_trend`. Here ADR-0017 §170 and the design doc do explain why the two are different things, so this is a missing cross-reference rather than a false claim.

### 7.4 `docs/AI_HANDOFF/START_HERE_FOR_AI.md` — onboarding stops at Milestone AB

Billed as "non-negotiable rules for AI agents", it has zero mentions of `change_of_character`, `structure_break`, `level_crossing`, `series_context`, or `structural_trend`. Its "What has already been implemented" section omits the entire L3–L6 chain. An agent following it as instructed would not know the top four layers exist.

### 7.5 Minor / acceptable

- `docs/AI_HANDOFF/CURRENT_STATE.md:7` self-reports its baseline as `5aac1a3`; HEAD is `d132cea` (3 commits later). The file explicitly predicted this ("the Milestone AE commits are created by this milestone"). Its package coverage is current.
- `docs/CURRENT_SYSTEM_AUDIT_V1.md:153` asserts `[FACT]` a "two-commit git history". Now 83. The doc is correctly indexed as "Historical record", so this is a labelling nuance, not drift.
- ADR-0011 §157 documents the `descriptors.py` → `descriptor.py` rename, and `tests/test_evidence_taxonomy.py:549` asserts the plural is gone. Doc, code and test agree — the dangling branch `fix/evidence-descriptor-module-name` is merged.

---

## 8. Git repository status and branch structure

| Property | Value |
|---|---|
| HEAD | `d132cea` — *Merge Change of Character Foundation v1 Review* |
| Working tree | **clean** — no modified, staged, or untracked non-ignored files |
| `main` vs `origin/main` | **0 ahead / 0 behind** |
| Local branches | 35 (incl. `main`) — **all 34 merged into `main`** |
| Remote branches | 1 (`origin/main`) |
| Tags | none |
| Stashes | none |
| Remote | `github.com/asdovydas86-oss/dovydas-trading-system` |

**Branch naming follows a strict three-phase-per-milestone convention:**

```
design/<milestone>   →   feature/<milestone>   →   review/<milestone>
```

each merged into `main` as its own merge commit. The last four milestones are textbook:

```
21cbdc3 Merge Change of Character Foundation v1 design
9658003 Merge Change of Character Foundation v1
d132cea Merge Change of Character Foundation v1 Review
```

Design-before-code, review-before-done, enforced by branch topology. This is the strongest process signal in the repository.

**Findings:**

1. **34 fully-merged local branches are never deleted.** Every design/feature/review branch from every milestone is still present. The list will grow ~3 branches per milestone indefinitely; `git branch` is already unreadable. All are safely deletable (`git branch --no-merged main` is empty).
2. **Two prefix conventions coexist** for the same role: `feat/` (10 branches, earlier milestones) and `feature/` (6 branches, later). Cosmetic, but it defeats prefix-based filtering.
3. **No tags.** 83 commits, 21 ADRs, ~25 completed milestones, and no way to check out "the repo at Milestone AD". `pyproject.toml` has held `version = "0.0.1"` throughout.
4. **No CI.** No `.github/`, no workflow file of any kind. All 3,221 tests are run manually. Nothing prevents a red `main`.

---

## 9. Testing architecture and coverage

### 9.1 Architecture

- **Layout:** flat `tests/`, one module per subsystem, `test_<subject>.py`. No nesting, no test packages.
- **Config:** `pyproject.toml` — `testpaths = ["tests"]`, `addopts = "-ra"`. Nothing else.
- **Fixtures:** exactly one shared fixture (`fresh_fmis_imports`, `tests/conftest.py:11`) plus one data fixture (`tests/fixtures/btcusdt_4h.json`, 20 closed 4H candles, used by 6 test modules).
- **Isolation:** no network, no filesystem writes, no mocking framework. The Binance adapter is tested through an injected `urlopen_transport` seam (`providers/binance.py`), which is why a network-bound module still reaches 94 %.
- **Speed:** 3,221 tests in **3.84 s** — the whole suite is a sub-4-second inner loop.

The `fresh_fmis_imports` fixture deserves note: it wipes and **restores by identity** every `fmis.*` module so import-boundary tests can assert what a cold `import fmis.<pkg>` pulls in, without breaking later identity comparisons. Its docstring names the exact failure it prevents — a heisenbug that would appear and vanish with alphabetical test-file ordering. That is defensive design at a level most repos never reach.

Beyond assertions, the review records document **mutation testing** (59 probes for CHoCH, 42 for BOS, 38 for level-crossing) and measured scaling runs (100,000 breaks). These are recorded in `docs/reviews/` rather than automated in the suite.

### 9.2 Measured coverage by module

No coverage tool is installed and installing one was out of scope, so this was measured in-process with the stdlib `trace` module against the full suite. Denominator = executable lines from each file's compiled code objects.

| Package | Coverage | Hit / Statements |
|---|---:|---:|
| `pipeline` | **98 %** | 197 / 202 |
| `level_crossing` | **98 %** | 305 / 312 |
| `decision_support` | **98 %** | 381 / 387 |
| `structure_break` | **97 %** | 185 / 191 |
| `market_structure` | **97 %** | 495 / 508 |
| `data` | **96 %** | 185 / 193 |
| `relative_value` | **96 %** | 265 / 276 |
| `ingest` | **96 %** | 131 / 136 |
| `structural_trend` | **96 %** | 132 / 137 |
| `change_of_character` | **95 %** | 104 / 110 |
| `evidence` | **95 %** | 107 / 113 |
| `series_context` | **95 %** | 86 / 91 |
| `alignment` | **94 %** | 65 / 69 |
| `providers` | **93 %** | 213 / 230 |
| `trading_context` | **93 %** | 56 / 60 |
| `features` | **93 %** | 578 / 623 |
| **TOTAL** | **96 %** | **3,485 / 3,642** |

**Measurement caveat:** every `__init__.py` reports 0 % — a `trace` artifact from package import timing, not a real gap. Their re-export lines are exercised by hundreds of tests. Package figures above are therefore *understated* by 4–7 points each; the true totals are effectively ceiling. Excluding `__init__.py` entirely, only **10 of 60 modules** fall below 100 %:

| File | Coverage | Missed |
|---|---:|---:|
| `providers/binance.py` | 94 % | 14 |
| `relative_value/metrics.py` | 97 % | 6 |
| `features/indicators/macd.py` | 96 % | 4 |
| `market_structure/models.py` | 99 % | 4 |
| `data/_timeutils.py` | 94 % | 1 |
| `data/models.py` | 99 % | 1 |
| `features/indicators/ema.py` | 98 % | 1 |
| `features/types.py` | 99 % | 1 |
| `ingest/candles.py` | 99 % | 1 |
| `pipeline/market_analysis.py` | 99 % | 1 |

The 14 uncovered lines in `binance.py` are the network/HTTP error branches — the only place in the repo where an untestable boundary genuinely exists.

**The real testing gaps are structural, not numeric:**

1. **No coverage tooling in `pyproject.toml`.** This 96 % figure has never been visible to the project and cannot regress-gate.
2. **No CI** — the suite runs only when someone remembers.
3. **No linter, formatter, or type checker.** No `ruff`, `mypy`, `black`, `flake8`, or `pre-commit` config exists, despite the codebase being thoroughly annotated (`from __future__ import annotations` in every module, `Final`, `Protocol`, `NamedTuple` throughout). The type annotations are decoration that nothing verifies.
4. **Test volume is uneven by an order of magnitude**, tracking milestone recency rather than risk: `test_level_crossing.py` 178 tests vs `test_atr.py` 11 and `test_ema_math.py` 5. Foundation modules (`data`, `alignment`, indicators) carry the least scrutiny while sitting underneath everything.

---

## 10. Five highest-value architectural improvements

### 1. Resolve the two competing "evidence" concepts — `fmis.evidence` is dead code

`fmis.evidence` is 358 LOC and 62 tests of fully-specified taxonomy (ADR-0011) that **no production module imports**, while `fmis.decision_support` independently builds an `EvidenceReport` from its own vocabulary in `classification.py`. Two owners of one domain concept, and the ADR-specified one is unwired.

This is the single largest divergence between the documented architecture and the running system, and it will get worse: the structural layers (`market_structure`, `structural_trend`, `level_crossing`, `structure_break`, `change_of_character`) all name `fmis.evidence` in their docstrings as something they must not import, so as the chain grows, the gap between "evidence as specified" and "evidence as built" widens.

Either wire `decision_support` onto the `EvidenceDescriptor` catalog, or write an ADR superseding ADR-0011 and delete the package. Leaving a tested, documented, unreferenced module is the worst of the three.

### 2. Add CI plus a static-analysis gate

3,221 tests running in 3.84 seconds with zero dependencies is a near-perfect CI candidate, and there is no CI. A minimal GitHub Actions workflow (`uv sync && pytest`) costs almost nothing and makes the three-phase branch discipline enforceable rather than customary.

Pair it with `ruff` and `mypy --strict`. The codebase is already written as if type-checked — full annotations, `Protocol`s, `Final` constants, `frozen=True` dataclasses everywhere — so the first `mypy` run should be close to clean, and from then on the annotations become guarantees instead of comments.

Add `pytest-cov` in the same change so the 96 % measured here becomes a visible, ratcheting number.

### 3. Extract the contextual-pipeline scaffolding into one shared contract

Four packages (`series_context`, `level_crossing`, `structure_break`, `change_of_character`) each reimplement the same envelope-validation boundary, and their own docstrings assert the four error messages "match exactly" — an invariant nothing tests. Milestone AF will make it five.

Extract a single `_require_envelope` (in `fmis.series_context`, which already owns `ContextualSeries`) and have the four pipelines delegate. If the messages must stay per-layer, at minimum add the test that asserts they are identical — right now the contract lives only in prose. This also generalises the `__init__ / models / <domain> / pipeline` quadruple that every new structural layer copies by hand.

### 4. Repair or demote the authoritative architecture document

`docs/README.md` sends every new human and AI agent to `ARCHITECTURE_AND_ROADMAP_V1.md` as **"Authoritative — architecture"**, and that file's verified dependency graph and directory tree predate 7 of 17 packages and 3,074 of 3,221 tests. `START_HERE_FOR_AI.md`, the file that claims to hold non-negotiable rules, stops at Milestone AB.

The ADRs and design docs are excellent and current; the drift is confined to the two navigational summaries — which is exactly where drift does the most damage, because they are what a newcomer reads first. Either refresh both (§2.1 tree and §2.2 graph regenerate mechanically from the import graph in §3 above), or re-label them "Historical — superseded by `AI_HANDOFF/CURRENT_STATE.md`" and point `docs/README.md` at the file that *is* maintained every milestone.

Fix `features/market_structure/__init__.py:13` in the same pass — it still lists shipped BOS/CHoCH as TODO.

### 5. Tag milestones and prune merged branches

25-ish completed milestones, 21 ADRs, zero tags, and `version = "0.0.1"` since day one. There is no way to check out "the repo as ADR-0019 describes it", which undercuts the review records that cite specific commits (`1154622`, `5e7e3d5`, `5aac1a3`) — those citations only resolve while the reflog holds.

Tag each merged milestone (`milestone-AE`, or `v0.x.0` bumped in `pyproject.toml`), then delete the 34 merged local branches — the tags preserve exactly what the branches were being kept for, and `git branch` becomes readable again. Standardise on one prefix (`feature/`, the more recent of the two) while doing it.

---

## Summary

This repository is in unusually good health. Zero circular dependencies across a 17-package, six-layer graph; 96 % measured coverage; a 1.9:1 test-to-source ratio; 3,221 tests in under four seconds; zero runtime dependencies; an ADR per decision with alternatives and consequences; and a design→implement→review branch discipline followed without exception for 83 commits. Every instance of duplication found was deliberate and argued for in a docstring. There are no `FIXME`s, no `XXX`s, and no hacks.

The weaknesses are all of one kind: **the safety net is manual.** No CI runs the excellent tests, no type checker verifies the thorough annotations, no coverage tool tracks the strong coverage, no tags mark the disciplined milestones, and the two summary documents newcomers are pointed at have fallen ~2 months behind the code the ADRs describe accurately. Item 2 addresses most of that in a single change.

The one substantive architectural issue is item 1: `fmis.evidence` is a fully-built, fully-tested, entirely unused module competing with `decision_support` for the same concept. That deserves a decision before Milestone AF adds another layer on top.
