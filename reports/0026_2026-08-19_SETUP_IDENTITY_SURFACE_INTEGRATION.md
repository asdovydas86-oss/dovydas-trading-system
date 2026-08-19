# Report 0026 — Setup Identity Surface Integration (BG-D1c) — Implementation Record

| Field | Value |
|---|---|
| **Report number** | 0026 |
| **Title** | Setup Identity Surface Integration (BG-D1c) — Implementation Record |
| **Date** | 2026-08-19 |
| **Report type** | Implementation |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `a4191f2` — the production code and tests of this slice. This record and the product documents are committed directly on top of it |
| **Status** | Final |

---

## 1. What shipped, in one sentence

`fmits setup SYMBOL` now prints the setup's **stable identity** — the line the
owner compares between runs to tell *"the same idea, still there"* from *"a new
idea"* — appended below the existing page, which is byte-identical.

**This is the first user-visible capability of the BG-D1 line.**

---

## 2. The design decision that shaped the slice

The brief asked the surface to show four things: occurrence identity, **new vs
repeated**, **repeated observation count**, and the stable anchor.

A single `fmits setup` invocation observes **one bar**. It fetches each timeframe
once — that is the command's stated contract — and `StructuralFactSheet` keeps a
`DataWindow`, not its candles, so there is no way to re-derive an earlier reading
without a second fetch. From one reading, `is_new_occurrence` is `True` and the
count is `1` **by construction**, for every setup, forever.

Printing those would be a field that is always the same value dressed as a
measurement — exactly what requirement 9 calls *stale or misleading*. So:

- **The identity, the anchor and the provenance are printed.** They are what one
  reading genuinely supports, and the identity line is the whole mechanism: it is
  equal across runs when the idea is the same and different when it is not. The
  block says so in one sentence rather than leaving the reader to infer it.
- **The counts are not printed by `fmits setup`.** They live in
  `render_identity_run`, which a caller holding a *series* uses. That renderer is
  built, exported and tested here; no surface holds a series yet.

Both renderers are shipped, so the capability is complete and the surface claims
only what it can.

---

## 3. What was built

| File | Change |
|---|---|
| `src/fmis/setup_observation/render.py` | **new** — `render_setup_identity` (one reading) and `render_identity_run` (a series) |
| `src/fmis/setup_observation/__init__.py` | exports both, plus `IDENTITY_WIDTH` |
| `src/fmis/pipeline/cli.py` | `_setup_identity_block`, `SETUP_IDENTITY_GAP_BARS`, and three lines in `_run_setup` |

**The renderer lives in the application package, not beside `render_setup`.** The
engine's own renderer is a market-half module and may not import a domain value;
an identity is one. The two renderers therefore sit either side of that line and
the command surface composes them — which is the only layer allowed to see both.

**A symbol that cannot be resolved to a market suppresses the block, not the
page.** `market_from_symbol` refuses to guess where `BTCUSDT` divides into base
and quote, and a symbol quoted in something other than the default is legitimate.
Printing a fabricated market to keep the section would put an invented fact under
a heading whose entire purpose is identity. `fmits setup BTCEUR` prints its full
analysis and no identity block.

**`swing_index` is never printed.** It is window-relative, it moves every bar, and
printing it beside an identity would invite a reader to treat it as one. It stays
on the observation as provenance; a test asserts it never reaches the page.

---

## 4. Verification

| Gate | Result |
|---|---|
| Focused surface suite | **31 passed** (`tests/test_setup_identity_surface.py`) |
| BG-D1b adapter suite | **53 passed** |
| BG-D1 domain suite | **66 passed** |
| Full repository under `-W error` | **8530 passed**, 0 failed (8499 → 8530) |
| Statement + branch coverage, `fmis.setup_observation` | **100 %**, 0 missed |
| Coverage of the new `cli.py` region | 0 lines missed |
| Mutation probes, surface | **21 / 21 detected, zero survivors** |
| Architecture / boundary / static guards | all pass |

### 4.1 Requirement 10, test by test

| Required property | Test |
|---|---|
| same setup across repeated calls keeps the identity | `test_repeated_calls_on_the_same_setup_print_the_same_identity` |
| new anchor → different identity | `test_a_new_anchor_prints_a_different_identity` |
| repeat count increments deterministically | `test_the_repeat_count_increments_deterministically` |
| existing fields behaviourally unchanged | `test_the_existing_page_is_unchanged_byte_for_byte` |
| no-lookahead intact | `test_no_lookahead_a_prefix_prints_the_prefixs_own_identity` |
| CLI output within width rules | `test_every_line_stays_within_the_page_width`, `test_the_block_rule_matches_the_engine_renderers_rule` |
| no persistence occurs | `test_the_command_writes_nothing_anywhere`, `test_the_projections_remain_unstorable` |

The byte-identical test is the strong form: it asserts the whole of stdout equals
`render_setup(assessment) + "\n" + identity_block + "\n"`, so no existing field
can be altered, reordered or dropped without failing.

### 4.2 The engine renderer's width, corrected on the record

`render_setup`'s `_WIDTH = 70` governs its **rule** lines only; its content lines
run to 93 characters when a limitation is long. The identity block matches the
rule exactly **and** keeps every content line inside 70 — stricter than the
engine, and pinned by two tests. One line of the block was 71 characters when
first written and was caught by that test, not by review.

### 4.3 Live demonstration — real market data

`fmits setup DOTUSDT`, run twice in two independent processes against live
Binance data, on a genuinely `CONFIRMED SHORT` setup:

```
── SETUP IDENTITY ────────────────────────────────────────────────────
  occurrence  sha256:b9f854b65dfbb2451…
  anchor      binance:DOTUSDT:spot · swing · short
  origin      a58da478cdd45bf5 (confirmed over 2 bars)
  continuity  the same idea keeps this line between runs.
              A different line is a different setup.
  policy      swing-setup-v1
  measured    2026-08-19T16:00:00+00:00
```

Byte-identical across both runs. A **different** setup on the same day —
`fmits setup ARBUSDT`, `CANDIDATE SHORT` — prints
`occurrence  sha256:fa4b4870cf2092e35…` and `origin cf5bc3715cb7eb0a`: a
different idea, a different line.

`fmits setup BTCUSDT` is `WAIT` today and prints the honest absence:
`— the reading has no stop with a MEASURED level origin to anchor on`.

---

## 5. One guard allowlist extended, and it is stated plainly

`tests/test_trade_capture_architecture.py::test_the_cli_reaches_neither_the_domain_nor_the_store`
keeps an allowlist of prefixes `fmis.pipeline.cli` may import. It has been
widened once per milestone — `fmis.position_sizing` (BN), `fmis.paper` (BO),
`fmis.statistics` (BP) — each time for an application-layer package at the same
tier. `fmis.setup_observation` is the fourth, on the identical footing, with the
justification written into the test.

The rule the guard actually protects is untouched: the CLI names **no domain
root** (the one domain value it needs, a `MarketId`, comes from
`market_from_symbol` in the already-permitted `fmis.trade_capture` — the same
discipline the guard's own BP note records) and opens **no store**. Both
downstream assertions still pass unchanged.

**This is the only guard file touched by this slice.** Report 0025 touched one
other (`test_level_crossing.py`); no guard has been weakened, only allowlists
extended through their own documented mechanism.

---

## 6. Preserved, and checked

| Invariant | Result |
|---|---|
| Existing `fmits setup` page | **byte-identical**, asserted |
| `fmis.swing_setup` strategy logic | unchanged — no engine file touched |
| Directional decision logic | unchanged |
| Record kinds | **15 → 15** |
| Repositories added | 0 |
| `OpportunityProposal` / `OpportunityRepository` | not duplicated, not touched |
| Persistence of projections | none; the store refuses all three types |
| New domain types | 0 |
| New runtime dependencies | 0 |
| Scoring / confidence / AI / indicators / regime / execution / Telegram / venue code | none added |

---

## 7. Findings recorded rather than quietly fixed

1. **A single invocation cannot support a repeat count.** §2. Recorded as a
   design boundary rather than papered over with an always-`1` field.
2. **`render_setup`'s content lines exceed its own `_WIDTH`.** §4.2. Not changed —
   it is the engine's page and this slice does not own it — but now documented,
   and the identity block holds the stricter rule.
3. **Freshness and `SetupType` remain unpopulated**, unchanged from report 0025
   §7.3–7.4.
4. **No surface holds a series yet.** `render_identity_run` is built, exported
   and tested but is called by nothing in production. `fmits scan` and
   `fmits today` are the natural next callers.

---

## 8. Product documents

**The changelog IS updated for this slice** — unlike reports 0024 and 0025, this
one changes what the owner sees when they run a command, which is exactly what
`FMITS_PRODUCT_CHANGELOG.md` records. `CURRENT_STATE.md` and
`FMITS_PRODUCT_BACKLOG.md` are updated too.

---

## 9. Commits

The three-milestone line landed as six commits, each feature commit followed by
its own product-docs commit:

```
ec352b7  feat(setup): add stable setup identity projections             (BG-D1)
           docs(product): record setup identity milestone
1909134  feat(setup): integrate stable setup identity into pipeline     (BG-D1b)
           docs(product): record setup identity pipeline integration
a4191f2  feat(setup): surface stable setup identity on fmits setup      (BG-D1c)
           docs(product): record setup identity surface integration   (this record)
```

Each feature commit was verified independently checkoutable and green at its own
boundary before its documentation commit was made.
