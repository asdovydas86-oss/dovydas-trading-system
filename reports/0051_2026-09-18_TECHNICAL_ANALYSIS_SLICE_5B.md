# Report 0051 — Technical Analysis Slice 5B: Price Zone Foundation & Product Surface

| Field | Value |
|---|---|
| **Report number** | 0051 |
| **Title** | Technical Analysis Slice 5B — Price Zone Foundation & Product Surface |
| **Date** | 2026-09-18 |
| **Report type** | Implementation record (production milestone) |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Baseline commit** | `693e162e149ae302d92a00f789ccb1a1cfd01471` (Price Zone Semantics & Parameter Research Gate, final documentation commit) |
| **Delivered at commit** | `3739d425423bf36ec7bad32d0e9534970ab60d55` (production code + tests) · the documentation commit follows it |
| **Status** | Final |

---

## The milestone in one sentence

**FMITS sees an area where it used to see three unrelated lines** — and it still refuses to say what
that area *means*.

---

## 1. Verified starting baseline

Every line below was read from the live repository before anything was changed. **The brief's own
stated hashes, counts and process IDs were treated as untrusted** and re-derived.

| Claim | Verified? | Evidence |
|---|---|---|
| `HEAD` = `main` = `origin/main` = remote `refs/heads/main` | **Yes** | all four resolve to `693e162e149ae302d92a00f789ccb1a1cfd01471`; the remote by `git ls-remote origin main` |
| Branch `main`, `0/0` ahead/behind | **Yes** | `git rev-list --left-right --count origin/main...HEAD` → `0	0` |
| Stash empty, no active Git operation | **Yes** | `git stash list` empty; no `rebase-merge`, `rebase-apply`, `MERGE_HEAD` or `CHERRY_PICK_HEAD` |
| Tracked tree clean | **Yes** | `git status --porcelain` showed only untracked entries |
| 16 untracked research documents | **Yes** | 15 under `docs/design/`, 1 under `docs/reviews/`. **None was modified, and all 16 are still untracked at close** |
| Policy baseline 81 fixtures, 72 `WAIT`, 9 `CANDIDATE` | **Yes** | recomputed independently of the test suite, §10 |
| Aggregate `sha256 8b22e6c9…` | **Yes** | recomputed with report 0045 §11.6's committed formula **before** any change |
| Operator instance PID 46403 on `127.0.0.1:8787` | **Yes** | confirmed `LISTEN` by `lsof`, and confirmed `LISTEN` again at close. **Never stopped, signalled or requested. `pkill` and `killall` were not used at any point** |
| `~/.fmits` contents | **Yes** | read-only: `scan_memory/` with 8 scan files and nothing else. A `sha256` of all 8 was taken before live verification and compared after — **identical** |
| `~/.fmits/risk_policy.json` absent | **Yes** | absent at start and **not created** |
| Test baseline 15,092 under `-W error` | **Carried, then superseded** | this milestone changed `src/`, so the suite was re-established rather than quoted — §11 |

**Discrepancies found: none.** The live repository matched the brief's expected baseline exactly.

**One operational fact worth recording.** `python -m fmis.pipeline.cli dashboard …` exits `0` and
prints **nothing** — `cli.py` has no `__main__` guard, so running the module as a script executes the
imports and stops. The working invocation is the installed console script, `.venv/bin/fmits`. Three
minutes were lost to a silently successful no-op; the next session should not repeat them.

---

## 2. Authority reconciliation

Read live, in this order: `CLAUDE.md`, `START_HERE_FOR_AI.md`, `CURRENT_STATE.md` §0,
`CAPABILITY_REGISTRY.md`, the backlog, the changelog, the ADR index, the report index, reports 0047
(and its review disposition), 0048, 0049, 0050, ADR-0031, ADR-0032, ADR-0033 and
`PRICE_ZONE_ENGINE_V1.md`, plus the live `fmis.level_crossing`, `fmis.features.series`,
`fmis.pipeline.structural_facts`, `fmis.pipeline.technical_context` and `fmis.operator_dashboard`
sources.

**One contradiction between binding sources was found, and the brief itself had already resolved it.**
The backlog, `CAPABILITY_REGISTRY.md` §6 and report 0049's closing line all name the next milestone
**"TA Slice 5B — Price Zones & Interactions"**. ADR-0033 — later, more specific, and the accepted
decision record — states that `ZoneInteraction` and `ZoneReading` are **not** V1, that R3 and R4 are
unanswered, and that a `CLOSE_BREACH` is not a breakout. **ADR-0033 wins**, per `CLAUDE.md`'s rule
that the ADRs are authoritative where documents disagree. The milestone was therefore executed as
**Price Zone Foundation & Product Surface**, and the planning documents have been corrected to match
rather than the reverse (§16).

No other contradiction was found. Nothing in this milestone required stopping for a decision.

---

## 3. Owner decisions recorded

Four, taken by the owner after review with ChatGPT, and written into ADR-0033's header as an
**acceptance record** that adds to the document without rewriting any of its research claims.

| | Decision | Where it is now binding |
|---|---|---|
| **A** | ADR-0033 is **Accepted** | ADR status line · `docs/adr/README.md` |
| **B** | `k = 0.50`, a **declared** V1 representation parameter — not an optimum, not a calibrated threshold, not an edge claim, not a confidence | `ZONE_WIDTH_POLICY_V1`; `ZoneWidthPolicy`'s own docstring; the rendered panel says *"declared V1 setting, not a measured optimum"* |
| **C** | **One `k` for 1W, 1D and 4H**; no per-timeframe hidden constant | One module-level default handed to every role; a test asserts every zone on a real three-role sheet stamps the **identical** policy object |
| **D** | *"Support zone"* / *"Resistance zone"* approved as **future UI labels over a derived role**, never over position, never for `UNTESTED` — **and not permission to build the interaction engine** | Recorded in the ADR. **Nothing in this milestone used it**, and the guards that forbid the words stay in force |

**Decision D is the one this milestone had to be most careful with**, because approval for a future
label is the easiest thing in the world to cash in early. It was not cashed in: no role is derived,
and §8 records that the role *vocabulary* was deliberately left out of the code as well.

---

## 4. Architecture implemented

```
detect_swings → label_swing_sequence → structural_levels ─┐
                                                          ├─► derive_price_zones ─► PriceZoneSet
AverageTrueRange(14).compute_series() ────────────────────┘          (fmis.price_zones)
                                                                             │
                                             StructureFacts.zones ◄──────────┘
                                                      │   (fmis.pipeline.structural_facts)
                                                      ▼
                                          TechnicalContextView.zones          by reference
                                                      │   (fmis.pipeline.technical_context, ADR-0032)
                                                      ▼
                                   SetupRunResult → SymbolDecision → SymbolDecisionRow.zones
                                                      ▼
                                              /swing/SYMBOL price zones panel
```

**New package: `fmis.price_zones`** — 1,132 lines across three modules, `models.py`, `engine.py` and
`__init__.py`, exporting 15 public names with **0 collisions** against the rest of the repository's
1,774.

**Where each decision physically lives.**

| Decision | Home | Why there |
|---|---|---|
| What a band *is*, and what it may never carry | `fmis.price_zones.models` | The types are the enforcement. There is no field a role, strength or score could be stored in |
| How bands are built | `fmis.price_zones.engine` | One function, `derive_price_zones` |
| Which feature sizes a band | `ZoneWidthPolicy.feature_name`, resolved by `zone_width_series` against the caller's registry | The width and the sheet's own ATR reading come from **one** feature instance, not two that agree |
| Which bands a page shows, and in what order | `PriceZoneSet.near` / `nearest_above` / `nearest_below` | Beside the set it selects from. §12 records the guard that moved it there |
| *How many* bands a page shows | `fmis.operator_dashboard.sections` | A presentation bound, and the only zone decision the dashboard makes |

**No second market-data pipeline.** Zones are built inside `build_structural_facts`, from the level
run the chain already produced and the ATR history the registry it already built can compute. The
three roles are the sheet's own three roles.

**Nothing is reimplemented.** Swing detection, labelling, level projection, crossing classification
and ATR each keep their single implementation elsewhere. `fmis.price_zones` performs exactly two
arithmetic operations of its own: `k × feature` (in `ZoneWidthPolicy.width_from`, the one place it
exists) and the half-width. A test parses `engine.py` with `ast` and asserts it contains **no
multiplication at all**.

---

## 5. The exact `PriceZone` semantics

```
low  = anchor.price − w/2        high = anchor.price + w/2
w    = 0.50 × atr_14, read at the anchor's own establishment bar
```

| Rule | Statement | The alternative it refuses, and what that cost |
|---|---|---|
| **Order** | Levels are processed by `origin.knowable_from` = `origin.index + confirmation_bars` — the bar the market made the level knowable | Ordering by the pivot's own bar would let a zone exist before its level did |
| **Construction** | Anchored and online. A level joins the band it falls inside, or opens one at its own price. Zones are never merged, split, resized or deleted | Single-linkage clustering: **247 of 339 levels into one zone** on BTC 1D. Diameter-bounded greedy: not reflection-symmetric, **120,441** illegal prefix events |
| **Band** | **Frozen at construction** | Width from the latest ATR: **983,916** illegal prefix events. A joining member widening the band: **34,192** |
| **Membership** | `low <= price <= high`, inclusive both edges, by price alone. An `UPPER` and a `LOWER` level may share a band | Making side a membership condition would assert that a former high and a former low at one price are two different areas — a claim no measurement supports |
| **Ties** | The **oldest** containing band takes the level | Nearest centre — the preregistration's own rule — compares two nearly equal floats and flipped on **35 %** of series under a rescale |
| **Same bar** | One bar is one instant. Levels at bar *i* are tested against bands that existed **before** *i*; bands opened at *i* cannot claim each other's levels | One candle can be both a swing high and a swing low; any intra-bar order breaks the tie on side or price, and both invert under reflection |
| **No width** | No value at the anchor's bar → **no zone**. The level is carried as `unassigned` with a count | A default width would be the invented threshold this design exists to avoid, placed where nobody would look for it |
| **Overlap** | Bands overlap and are **never merged**. `overlapping` reports the pairs; `zones_containing` returns a tuple | At `k = 0.50`, 70 % of adjacent pairs intersect. Hiding it would hide a real property of the representation |
| **Exactness** | `PriceLevel` equality, `classify_comparison` and `CrossingKind` are **untouched**. The tolerance is scoped to band membership alone | `PriceLevel(A) != PriceLevel(B)` and `zone.members == (A, B)` are both true, by design |
| **Reproducibility** | The `ZoneWidthPolicy` is stamped **by value** on every zone | A zone recorded a year ago stays reproducible after the default moves |
| **Identity** | One `SeriesIdentity` per set, **by reference** (ADR-0018) | A set cannot hold two series; a zone whose identity differs from its set is rejected at construction |
| **Pairing** | A level whose establishment bar the width history never saw raises `SeriesWindowMismatchError` | `PriceLevel` carries no identity, so a mismatched pair could not otherwise be detected — and the nearest-earlier fallback would have sized every affected band from the wrong volatility and said nothing |

**One place the implementation is stricter than the design, deliberately.** `PRICE_ZONE_ENGINE_V1.md`
§6 says V1 *must declare* `k` inside `[0.10, 1.00]`. `ZoneWidthPolicy` **enforces** that region: a
multiple outside it raises. The region is the one thing about `k` that was measured, and a bound
written down but not enforced is a bound a later caller steps over without noticing.

**`position` is geometry, and the type system is what keeps it that way.** `ZonePricePosition` has
three members, each named as a sentence about the **price** (`PRICE_ABOVE`, `PRICE_BELOW`,
`PRICE_INSIDE`), the accessor is `PriceZone.price_position`, and there is no `role` attribute on any
type in the package. A parameterised test asserts that no field or public attribute of `PriceZone`,
`PriceZoneSet`, `ZoneMember` or `ZoneWidthPolicy` contains any of eighteen reading words; another
asserts that asking a zone where price stands leaves its `repr` byte-identical, so no role can
accumulate on it.

---

## 6. Product changes

**`/swing/SYMBOL` gained a price zones panel**, placed directly under the technical context panel it
groups and well above the evidence audit. Ordering is the design decision: the decision layer stays
first, the exact facts come before the areas they form, and the audit stays last. Tests assert both
relations rather than a fixed panel index.

**Scannable first, deep second** — the technical panel's own pattern.

* **Headline table, one row per role:** the nearest area above the last close, the area price is
  inside (the **oldest** containing band, which is the one the membership rule itself prefers), the
  nearest area below, and the true area count. Each cell prints the two boundaries, the geometric
  position and the level count.
* **Behind a per-role disclosure:** the last closed price; the area count split above / below /
  containing; how many levels formed **no** area and why; the overlapping-pair count with the
  statement that bands are never merged; the width policy spelled out as `0.5 × atr_14`; a table of
  the bands nearest the close on both sides with their distance to the nearest edge; and, behind a
  further disclosure per band, its provenance — the anchor level and the swing that made it, the bar
  the band was written at, the most recent member's bar, the width, and the contributing levels in
  join order.

**A bounded selection, with the truth beside it.** A real symbol produces 20–250 bands per role, so
the page shows the three nearest on each side plus up to three containing bands — at most nine of a
possible two hundred and fifty — and prints the true totals next to them. The same discipline the
crossing history uses when it prints two events out of thousands.

**Distance is printed and is transparent.** It is the gap to the band's nearest edge, zero inside it,
computed by `PriceZone.distance_from` and reproducible from the two numbers printed beside it. It
orders the rows and nothing else; the panel does not call it a score and the type does not name it
one.

**The `/swing` list page, the decision panel, the timeframe panel, the risk panel and the evidence
audit are untouched.**

---

## 7. Live examples, from real markets

Four symbols on a development dashboard on port **8799** against live Binance data. Headline row,
verbatim from the rendered page:

**BTCUSDT** (last 1D close `76417.01`)

| Role | Nearest area above | Price inside an area | Nearest area below | Areas |
|---|---|---|---|---|
| 1w | `78069.685 – 83130.315` · price is below · 2 levels | `74218.907 – 78993.093` · price is inside · 2 levels | `72460.355 – 75093.645` · price is above · 3 levels | 46 |
| 1d | `77696.336 – 78969.664` · price is below · 3 levels | `75239.602 – 76760.398` · price is inside · 5 levels | `74432.729 – 75503.211` · price is above · 1 level | 47 |
| 4h | `78477.136 – 79179.164` · price is below · 4 levels | `77249.035 – 77846.885` · price is inside · 6 levels | `76973.204 – 77385.736` · price is above · 1 level | 39 |

**ETHUSDT** 1w: nearest above `2508.673 – 2795.327` (4 levels) · inside `2278.302 – 2539.698`
(6 levels) · nearest below `2002.497 – 2315.503` (7 levels) · 32 areas.

**ADAUSDT** — a sub-dollar altcoin, included because a width policy that is not scale-invariant fails
here first. 1d: nearest above `0.20908 – 0.21432` (1 level) · inside `0.19702 – 0.20298` (2 levels) ·
nearest below `0.18698 – 0.19302` (2 levels) · 51 areas.

**DOGEUSDT** — a second low-priced market, at `0.085`. 1w: nearest above `0.08429 – 0.09843` ·
inside `0.07216 – 0.08544` (5 levels) · nearest below `0.06020 – 0.07760` (6 levels) · 34 areas.

**Overlapping bands occur naturally and are visible.** BTCUSDT 1D reports **31 overlapping pairs** and
**2 areas containing the last close**; the page prints both facts. On ADAUSDT 4h the *nearest below*
band (`0.21021 – 0.21319`) intersects the *containing* band (`0.21065 – 0.21595`) — two areas, not
merged, exactly as ADR-0033 §5 requires.

**The limited-data case occurs naturally too, and is stated rather than hidden.** BTCUSDT 1W reports
*"1 structural level formed no area: the width feature had no value at the bar it became knowable,
and a band is never given a default width"*; ETHUSDT 1W reports 2 and its 4H role 3. These are levels
confirmed before ATR(14) warmed up. **No zone was invented for them.**

**What the pages do *not* say** — a scan of the whole rendered document for four markets found
`support`, `resistance` and `breakout` only in (a) the technical panel's existing denial sentence,
(b) the zone panel's own denial paragraph, (c) the package name `decision_support`, and (d) the CSS
class `state-unsupported`. The word-level scan of the zone panel with its denial carved out returned
**zero** of the 36 refused words across all four symbols.

**The Strategy Decision is unchanged.** BTCUSDT still reads `wait` · *HTF regime not eligible* ·
*"The context-role regime is not eligible, so the reading never reached the directional tally"* —
the same conclusion, from the same policy, with the digest to prove it (§10).

---

## 8. What intentionally remains unavailable

**Shipped:** the deterministic price-zone foundation · the `/swing/SYMBOL` zone surface ·
`k = 0.50` as a declared, versioned, stamped V1 policy · one policy shared across 1W / 1D / 4H.

**Not shipped, and each one deliberately:**

| Absent | Why |
|---|---|
| `ZoneInteraction`, `ZoneReading` | Each needs a parameter **R3** / **R4** has not answered |
| Zone **role** — and **the role vocabulary itself** | ADR-0033 §8 approves the seven-member vocabulary. It is **not declared in code**: a role vocabulary present in the source is one something will populate, and the enum would be the interaction engine's first half built without its second. It lives in the ADR until the engine exists |
| Support / resistance labels | Owner-approved for the future (decision D); unusable until a role is derived |
| Breakout · acceptance · reclaim · retest · false breakout · rejection | **A `CLOSE_BREACH` is not a breakout.** None of these has a definition this repository accepts |
| Zone strength, quality, score, rank, confidence | A member count is a size. No measurement says six levels beat two |
| Directional bias, `WATCH LONG` / `WATCH SHORT`, opportunity state | 0047 **D3** is open |
| Zone evidence in the policy | **R15**. `INDEPENDENCE NOT ESTABLISHED` — zones derive from the same confirmed pivots as structural trend |
| Chart patterns · Fibonacci · Elliott · trendlines · divergence · phases | Not in this slice's scope, and each has its own prerequisite |
| Any strategy, policy-gate, 1W-regime, risk or capital change | This milestone had no authority over any of them |

**Revisit triggers, recorded:**

* **R3 / R4 answered** → interaction states may be specified, and only then may a role be derived.
* **R15 answered** → and only then may zone evidence independence be discussed.
* **Product evidence that one shared `k` behaves materially badly on some role** → the one-`k` policy
  is re-taken as an explicit decision, not patched with a second constant.
* **`k` shown to affect a product outcome** → the question stops being representation-only, and
  ADR-0033 §6's declaration must be re-taken as a **measurement**.
* **A tick-size model reaches ingestion** → `W-TICK` becomes expressible.

---

## 9. Targeted test results

**+324 tests**, across four new files plus two added to the Scan Memory isolation suite.

| File | Tests | What it proves |
|---|---|---|
| `test_price_zones.py` | 86 | The policy, the band, membership, ties, one-bar-is-one-instant, missing width, overlap, position-is-not-a-role, distance, the set, the page's selection, and the model's refusal to hold an impossible zone |
| `test_price_zones_causality.py` | 112 | Prefix stability, no lookahead, determinism, unit invariance and long/short symmetry — over the **production** chain, across 8 series (4 seeds × flat and trending) |
| `test_price_zones_architecture.py` | 57 | The import boundary, delegation, the decision boundary, the rendering boundary, and the refused vocabulary |
| `test_price_zone_surface.py` | 67 | The seam by identity, the selection rule, what the page shows, and the vocabulary scan across three markets |
| `test_scan_memory_technical_context_isolation.py` | +2 | A decision with zones and one without project the **same** state; no comparison dimension names a zone |

**The load-bearing properties, and how each was earned.** Every one is asserted of production code
over production `structural_levels` and the production `AverageTrueRange`, not of a research harness.

| | Property | How |
|---|---|---|
| **A** | Prefix stability | Every zone of a 200/260/320-bar prefix is present **unchanged** at 400 bars — band, width, establishment bar and anchor compared as a tuple. A longer prefix **appends and never inserts**. Membership already written is a **prefix** of membership later |
| **B** | Current ATR cannot alter a historical band | Extending the series leaves every existing band's width and edges equal; and a constructed 100× volatility spike *after* a band was written changes nothing about it |
| **C** | A joining member cannot widen the band | A member joining from inside the band while its own bar's width is 5× larger leaves `(low, high, width)` identical |
| **D** | Oldest-containing-band ties | A level inside **two** bands and **nearer the second's centre** joins the first |
| **E** | Same-bar epoch semantics | Two levels on one bar open **two** bands even though each band contains the other's price — and a level from the **next** bar does join |
| **F** | Exact `PriceLevel` identity preserved | Members are the caller's own objects, asserted with `is`, element by element |
| **G** | Equal prices, different origins stay distinct | Two levels at exactly `100.0` with different origin bars and labels are **two** members of one zone, and `first != second` |
| **H** | Overlap allowed | Two overlapping bands stay two zones; one price is inside both; a real series produces overlaps and none is merged |
| **I** | Missing ATR invents nothing | Four tests: before warm-up → unassigned; never falls **forward** to a later value; falls back to the nearest **earlier** point when a gap exists; a non-positive reading forms no band |
| **J** | Determinism | Equal over two calls; invariant to a bar-preserving permutation of the input; and **byte-identical across three subprocesses under `PYTHONHASHSEED` 0, 1 and 12345** |
| **K** | Scale and symmetry | Rescaling by 2, 1024 and 0.125 leaves the **partition** exactly unchanged; **reflecting** the series mirrors the zone map exactly, over 8 series and at every `k` in {0.10, 0.25, 0.50, 0.75, 1.00} |
| **+** | Partition | Every level is a member **exactly once** or unassigned — never both, never neither, never duplicated |
| **+** | Monotonicity | Zone count is non-increasing in `k` across the admissible region — report 0050's central finding, re-earned on production code |

The partition comparison deliberately excludes prices: under a rescale they all move and under a
reflection they all invert, so a comparison including them could only fail. What must be invariant is
**which levels grouped with which**, and that is what is compared.

---

## 10. Policy non-regression — the hard gate

Recomputed **outside** the test suite, with report 0045 §11.6's committed formula:

```python
sha256(b"".join(repr(setup_assessment_for_sheet(multi(seeds=seeds, symbol=symbol))).encode()
                for key, seeds, symbol in _matrix()))
```

| | Before (`693e162`) | After |
|---|---|---|
| **Fixtures** | 81 | **81** |
| **States** | 72 `WAIT` · 9 `CANDIDATE` | **72 `WAIT` · 9 `CANDIDATE`** |
| **Aggregate** | `8b22e6c9c5e346cb8f62008325b9b0304ecae9af5e0fe46eec4a6c5aa428059c` | **`8b22e6c9c5e346cb8f62008325b9b0304ecae9af5e0fe46eec4a6c5aa428059c`** |

**Identical.** `tests/test_swing_setup_policy_non_regression.py` was **not edited**, and its 162
per-fixture digests pass. `evaluate_setup` and `SetupInputs` are byte-unchanged. No threshold, family,
gate, vote or candidate moved.

**Why it could not have moved.** `SetupInputs` gained no field, and the zone set is attached to
`StructureFacts` — a value the policy reads specific named fields from, none of which is `zones`. The
architecture tests assert the absence directly: no zone field on `SetupInputs`, `SetupAssessment` or
`EvidenceItem`; no mention of zones anywhere in `fmis.swing_setup`'s policy, model or
decision-summary modules; and no whole-word `zone` anywhere in `fmis.scan_memory`, `fmis.risk`,
`fmis.risk_policy`, `fmis.position_sizing` or `fmis.portfolio_risk`.

**Scan Memory**, additionally: a decision carrying zones and the same decision with them stripped
project the **same** `SymbolState` and the **same** comparison dimensions, and no `ChangeDimension`
names a zone.

---

## 11. Full suite

Run with `python -m pytest -W error -q` on **cleared bytecode**, with `PYTHONDONTWRITEBYTECODE=1` —
the discipline `CURRENT_STATE.md` §0.1 records after report 0049's stale-`.pyc` incident.

| Run | Result |
|---|---|
| **First** | **15,403 passed · 3 failed · 0 skipped · 0 warnings** · 755.11 s. All three failures were **architecture guards**, and §12 records what each one caught |
| **Second, after all three were addressed** | **15,414 passed · 0 failed · 0 skipped · 0 warnings** · 750.96 s |
| **Third, at the delivered tree** | **15,416 passed · 0 failed · 0 skipped · 0 warnings** · 764.45 s — the two added tests are the series-window guard's |

**Baseline was 15,092** at `00c7723`, last actually run on 2026-09-17 and re-established unchanged by
report 0050 on 2026-09-18. **+324, every one new:**

| File | Tests |
|---|---|
| `tests/test_price_zones.py` | 86 |
| `tests/test_price_zones_causality.py` | 112 |
| `tests/test_price_zones_architecture.py` | 57 |
| `tests/test_price_zone_surface.py` | 67 |
| `tests/test_scan_memory_technical_context_isolation.py` | +2 (11 total) |
| **Total** | **+324** |

**No warning was silenced, no test was weakened, and no existing test was changed to accommodate new
behaviour.** Four existing test files were edited: three are justified in §12, and the fourth
(`test_technical_context.py`) added TC-6's denial sentence to the carve-out list its own
`test_the_denials_the_scan_exempts_actually_exist` then asserts still exists. **No existing assertion
was removed or relaxed, and no fixture file was touched.**

---

## 12. Three architecture guards fired, and all three were obeyed

This is the section worth reading. Each guard caught something real, and none was widened to make the
milestone pass.

### 12.1 `test_nothing_below_imports_level_crossing` — **widened, with the justification its own docstring demands**

`fmis.price_zones` imports `PriceLevel` from `fmis.level_crossing`. The guard names every permitted
consumer explicitly and says so in terms: *"a third consumer appearing anywhere fails this test and
has to justify itself in an ADR."*

**The ADR exists and predates the code.** ADR-0033 §5.1 states that every zone member is a
`PriceLevel` from `structural_levels`, **and nothing else**. `fmis.price_zones` sits *above*
`fmis.level_crossing`: it reads a level's price and its origin's `knowable_from`, holds the level by
reference, and derives, moves or reclassifies nothing.

**The direction rule — what the guard actually protects — is unchanged, and is now asserted in both
directions.** `fmis.level_crossing` cannot see `fmis.price_zones`, and neither can `fmis.data`,
`fmis.market_structure` or `fmis.features`; a new test parameterised over all four proves it. And no
exact semantic moved: `PriceLevel` equality, `classify_comparison` and `CrossingKind`'s
exact-equality-is-a-`TOUCH` rule are untouched, which this file's own tests still prove.

### 12.2 `test_no_engine_below_imports_this_package` (market regime) — **the prose was wrong, and was corrected**

`price_zones/__init__.py` listed the packages it must **never** import, spelled as dotted module
paths — including `fmis.market_regime`. The guard is a **text** scan, so a docstring agreeing with it
tripped it.

The package imports none of them. **The docstring was reworded** to name the forbidden packages in
prose, with a sentence explaining why the dotted paths are absent, and pointing at
`tests/test_price_zones_architecture.py`, which enforces the identical list over the real **import
graph** — where a name in a sentence cannot be mistaken for one in an `import`. **The guard was not
relaxed.** This is the same class of finding report 0049 §"four guards" recorded, and the same
resolution.

### 12.3 `test_the_contract_layer_performs_no_aggregation` — **the design was wrong, and was moved**

*"`sum`, `min`, `max` and `sorted` are how a presentation layer becomes an engine. A total is
arithmetic over financial values; an extremum is a comparison of them; a sort is a ranking."*

The first implementation selected and ordered the zones inside
`fmis.operator_dashboard.sections` — two `sorted` calls over market values. The guard was right: a
real symbol produces 20–250 bands per role, so *something* must choose which handful a page shows,
and letting the dashboard choose is the dashboard deciding which area matters.

**The ordering moved onto `PriceZoneSet` itself** — `near`, `nearest_above`, `nearest_below`,
`zones_above`, `zones_below` — beside the set it orders, with a documented total key over the zone's
own properties. `sections.py` now chooses only **how many** (`ZONES_SHOWN_PER_SIDE = 3`) and
translates the result field for field. It contains **no `sorted` call**, and a new test asserts both
that absence and that the engine's four selection methods are the ones it calls.

**The rendered output was byte-identical before and after the move**, verified against the same four
live symbols — the selection was correct; its *home* was not.

---

## 13. Performance

Measured, not estimated. Median of 20 runs for the engine, 10 for the whole sheet.

**Synthetic sheet path** — the zone work against the sheet build it rides inside:

| Closed bars | Levels | ATR series | Zone build | Total added | Whole sheet | Added |
|---|---|---|---|---|---|---|
| 260 | 93 | 0.152 ms | 0.077 ms | 0.229 ms | 6.15 ms | **3.7 %** |
| 500 | 186 | 0.296 ms | 0.152 ms | 0.449 ms | 22.07 ms | **2.0 %** |
| 1,000 | 380 | 0.629 ms | 0.320 ms | 0.948 ms | 88.40 ms | **1.1 %** |
| 2,000 | 774 | 1.246 ms | 0.647 ms | 1.893 ms | 373.84 ms | **0.5 %** |

**Real market data** — report 0040's committed offline capture, which produces far more zones per
role than the synthetic fixture and is therefore the honest measurement of the `O(levels × zones)`
inner loop:

| Window | Typical per symbol-role | Worst observed |
|---|---|---|
| **500 bars — the live product's own window** | 0.30 ms ATR + 0.22–0.28 ms zones ≈ **0.55 ms** | 0.58 ms (BTCUSDT 1D, 141 levels → 47 zones) |
| 7,313 bars — 14.6× the live window, pathological | 4.7 ms ATR + 5.4–10.2 ms zones | **14.8 ms** (BTCUSDT 4H, 2,092 levels → 244 zones) |

**Watchlist effect at the live window: ≈ 33 ms** for 20 symbols × 3 roles — against a scan whose cost
is dominated by sixty network round-trips. Even the pathological window would cost 0.89 s for the
whole watchlist.

**`/swing/SYMBOL` rendering**: no measurable change. The page is rendered from an already-built
snapshot; the zone panel adds one bounded table and at most nine disclosures per role.

**No cache was introduced.** The sheet build already owns the level run and the feature registry, so
the zone work is paid once per sheet and stored on it. Introducing a cache for a 0.55 ms computation
would trade a measured non-problem for a class of stale-state bug.

---

## 14. Live product verification

Performed on a **separate development dashboard on port 8799**, with an isolated `--store-root` and
`--scan-history-root` under the session scratchpad.

| Check | Result |
|---|---|
| Operator instance PID 46403 on 8787 | `LISTEN` at start and at close. **Never stopped, signalled or requested.** `pkill` / `killall` never used |
| Development instance | started and stopped **by exact PID**, twice — once to pick up the §12.3 refactor |
| Symbols inspected | **BTCUSDT · ETHUSDT · ADAUSDT · DOGEUSDT** — two majors and two sub-dollar altcoins |
| HTTP | 200 for all four, 86–91 KB per page |
| Rendered output inspected | **Yes** — markup stripped and read, not merely status-checked (§7) |
| Overlapping zones | Present naturally: 18–32 overlapping pairs per role; BTCUSDT 1D has **2** areas containing the last close, both printed |
| Limited-data case | Present naturally: 1–3 levels per role formed no area, each stated with its reason |
| Repeated `GET` | **Byte-identical** on BTCUSDT and ADAUSDT — `cmp` on the full documents |
| `~/.fmits` after | **Byte-identical** — `sha256` of all 8 files compared before and after |
| `~/.fmits/risk_policy.json` | still absent. **Not created** |
| Strategy Decision panel | unchanged in content and position (§7) |
| Vocabulary | zero refused words outside the denials, all four markets |

**One requested example could not be produced from live data and was not fabricated.** The brief asks
for a role with *unavailable* zone data. Every role of every live symbol produced a zone set, because
`atr_14` warms up in 15 bars and the provider returns 500. The nearest honest case — levels confirmed
**before** ATR warmed up, which produce no zone and are carried as `unassigned` — occurs naturally on
six of the twelve role-views inspected and is what §7 reports. The fully-unavailable branch
(`available=False`, *"the width policy's own feature was not computed"*) is exercised by a test that
strips the zone set from a real context, not by pretending a market produced one.

---

## 15. Files materially changed

**New — production (1,132 lines):**

```
src/fmis/price_zones/__init__.py      86    package contract, the import boundary in prose
src/fmis/price_zones/models.py       750    the types, the policy, the limitations
src/fmis/price_zones/engine.py       296    zone_width_series, derive_price_zones
```

**New — tests (2,247 lines):** `tests/price_zone_helpers.py`, `tests/test_price_zones.py`,
`tests/test_price_zones_causality.py`, `tests/test_price_zones_architecture.py`,
`tests/test_price_zone_surface.py`.

**Modified — production, all additive:**

| File | Change |
|---|---|
| `pipeline/structural_facts.py` | `StructureFacts.zones` (defaulted `None`); `_structure_of` takes the width series; `build_structural_facts` resolves it from the registry it already built |
| `pipeline/technical_context.py` | `TechnicalContextView.zones`, carried **by reference**; limitation **TC-6** |
| `operator_dashboard/models.py` | `PriceZoneRow`, `PriceZoneGroupRow`, `SymbolDecisionRow.zones` |
| `operator_dashboard/sections.py` | `price_zone_group_rows`, `_zone_row`, two presentation bounds |
| `operator_dashboard/render.py` | `_price_zone_panel` and its five helpers; one line adding it to the symbol page |
| `operator_dashboard/__init__.py` | two exports |

**Modified — tests:** `architecture_tiers.py` (classify `price_zones` PRODUCTION),
`test_level_crossing.py` (§12.1), `test_technical_context.py` (TC-6's denial added to the carve-out
list), `test_scan_memory_technical_context_isolation.py` (two zone-specific isolation tests).

**No file was deleted. No test was weakened. No existing fixture was edited.**

---

## 16. Documentation and project memory

| Document | Change |
|---|---|
| **ADR-0033** | `Proposed` → **Accepted**, with the owner's four declarations as an acceptance record. **No research claim was rewritten**; §6 gained the declared value and the note that the admissible region is enforced rather than advised |
| `docs/adr/README.md` | the ADR-0033 row's status |
| **`PRICE_ZONE_ENGINE_V1.md`** | `DESIGNED — not implemented` → **IMPLEMENTED**, with the two places the implementation is stricter named explicitly, and §4.4/§7 recorded as still not built |
| **`CURRENT_STATE.md` §0** | baseline, verification method, product surfaces, the milestone row, the test baseline, what the product can do, the limitations (rewritten: *zones exist, roles do not*), the structural chain, 33 accepted ADRs, and D1/D2 closed with R3/R4/R15 added |
| **`CAPABILITY_REGISTRY.md`** | *Support/resistance zones* `PLANNED` → **two rows**: *Structural price areas* `IMPLEMENTED` and *Support/resistance roles* `BLOCKED`. The sequence gains step 1b; §6 gains a Slice 5B scope table; disposition §C closed |
| **`FMITS_PRODUCT_BACKLOG.md`** | `DY` moved to §8 with its full record; §5 NOW is **empty** and says so honestly, stating both live candidates and selecting neither; §6.1 step 1 DONE, step 1b added |
| **`FMITS_PRODUCT_CHANGELOG.md`** | `DY` entry — a **user-visible capability** |
| **`docs/AI_HANDOFF/daily/2026-09-18.md`** | this session's handoff |
| **`reports/README.md`** | this report indexed; next available number bumped |

**The 16 pre-existing untracked research documents were not read-modified and are still untracked.**

---

## 17. Commit and push

**Two commits, on the repository's own convention** — production first, documentation second, so the
capability and the record of it are separately reviewable.

| | Commit | Contents |
|---|---|---|
| 1 | `3739d425423bf36ec7bad32d0e9534970ab60d55` | `fmis.price_zones`, the carriage, the dashboard surface, and all 324 tests |
| 2 | see the daily handoff | ADR-0033's acceptance, the design status, `CURRENT_STATE.md`, the registry, the backlog, the changelog, this report and the handoff |

**Verified before the push:** branch `main` · tracked tree clean apart from the two commits · the 16
pre-existing untracked research documents present and unmodified · stash empty · no active Git
operation · `0/0` against `origin/main` at the baseline · fast-forward ancestry from `693e162` · the
exact commit range reviewed with `git diff --cached --stat` · no `__pycache__` or `.pyc` staged · no
credential or secret in the diff · no `risk_policy.json` created anywhere · the operator instance on
8787 still `LISTEN` · the full suite green and the policy digest identical.

**Verified after the push:** `HEAD`, local `main`, `origin/main` and `git ls-remote origin main` all
equal, and the 16 untracked documents still present and untracked.

---

## 18. Final repository state

| Field | Value |
|---|---|
| Branch | `main` |
| `HEAD` = `main` = `origin/main` = remote `refs/heads/main` | the documentation commit |
| Ahead / behind | `0 / 0` |
| Tracked tree | clean |
| Untracked | the **16 pre-existing research documents**, unmodified |
| Stash | empty |
| Active Git operation | none |
| `~/.fmits` | byte-identical to the session's opening `sha256`; `risk_policy.json` still absent |
| Operator dashboard | PID 46403 on `127.0.0.1:8787`, `LISTEN` |

---

## 19. Recommended next milestone

**Not Zone Interactions.** It is the obvious next step and it is **blocked**, and the block is a
research block that no amount of implementation resolves: **R3** (*how many closes constitute
acceptance?*) and **R4** (*within how many bars is a return a retest?*) are unmeasured, and picking
either by intuition is exactly the invented threshold report 0050 exists to have refused. That gate's
central negative finding is that a representation-only study **cannot** produce such a value, so the
study that answers R3/R4 must be an **outcome** study with its question sealed in Git first.

**Two honest candidates, and the board states both without selecting:**

1. **An R3/R4 research gate** — preregistered, outcome-based, on the committed offline capture, in
   the shape report 0050 established. It unblocks zone roles, the first honest *Support zone* label,
   and every breakout-adjacent concept downstream. It is the highest-value next step and it is
   **research, not product**.
2. **Price Phases** (§6.1 step 2) — unblocked, needs no new research parameter, and is the next
   product-value step that can start immediately.

**The selection is the owner's.** This milestone was scoped to the zone foundation and was explicitly
forbidden to resolve R3/R4, so it has no standing to promote its own successor.

---

## 20. Claims this report does not make

No strategy edge. No predictive power. No calibrated zone strength. No support or resistance
semantics. No breakout detection. No opportunity detection. **`k = 0.50` is a declaration, not a
measurement.** A zone is a description of where a structural area is; it is not a reason to trade,
and nothing in this repository has measured that it is.
