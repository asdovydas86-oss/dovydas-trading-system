| Field | Value |
|---|---|
| **Report number** | 0046 |
| **Title** | Swing Product Slice 4 — Risk & Trade-Planning Foundation |
| **Date** | 2026-09-06 |
| **Report type** | Audit and implementation (product milestone) |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `03dd4e0` (baseline) |
| **Status** | Final |

---

# Slice 4 — Risk & Trade-Planning Foundation

## 1. Product First — the one-sentence problem

**The risk engine was finished and Dovydas could not reach any part of it.**

Roughly 8,300 lines of correct, tested, architecturally-guarded risk, sizing and portfolio
implementation existed. Not one figure from it appeared on the dashboard, and the dashboard could
not say why. The audit found the exact reason, and it was not a missing feature: **the chain had no
first link.**

## 2. Baseline gate

| | |
|---|---|
| `HEAD` / local `main` / `origin/main` / `git ls-remote origin main` | `03dd4e0001e6e94c33e1a0487598b79e6358db98` — all four identical |
| ahead / behind | `0 / 0` |
| tracked tree | clean |
| untracked | exactly the 16 pre-existing research documents |
| stash · active git operation | empty · none |
| operator dashboard | PID **74079**, `127.0.0.1:8787`, `HTTP 200` |
| full suite before any edit | **14,533 passed, 0 failed, 0 skipped, 0 warnings**, 676 s, under `-W error` |

**A note on that baseline number.** The first full run reported `1 failed, 14532 passed`. The
failure was `test_universe_architecture.py::…test_the_research_package_allowed_above_is_itself_unreachable`,
and it was **caused by this session**: the run was still executing when `src/fmis/risk_policy/`
was created on disk, and `architecture_tiers.assert_tier_partition_is_complete` correctly refuses an
unclassified package. Proved by moving the directory aside and re-running that file alone —
**174 passed**. The clean baseline is 14,533. The guard behaved exactly as designed.

All development ran on port **8799**. The operator's instance was never stopped and never signalled
**during development**; it was stopped once, deliberately, at handoff, because production code
changed and it was serving the old build — see §15.3. `pkill` was not used at any point.

## 3. Gate C — the risk and portfolio capability audit

Read-only, before anything was written.

### 3.1 What exists

| package | files | lines | role | numeric basis |
|---|---|---|---|---|
| `fmis.money` | 2 | 576 | `Money`, `Quantity`, `AssetCode`, canonical text | exact `Decimal` |
| `fmis.risk` | 2 | 761 | `RiskLimit`, `RiskBudget`, `LimitEvaluation`, `evaluate_budget` | `Decimal` / `Money` |
| `fmis.portfolio_risk` | 8 | 3,767 | geometry, exposure, impact, constraints, classification | `Decimal` / `Money` |
| `fmis.position_sizing` | 9 | 3,737 | `PositionSizer`, `SizingPolicy`, `ApprovalEngine`, `approve_results` | `Decimal` / `Money` |
| `fmis.portfolio` | 2 | 747 | `PortfolioState`, holdings | `Decimal` / `Money` |
| `fmis.positions` | 3 | 732 | position fold | `Decimal` / `Money` |
| `fmis.accounts` | 2 | 356 | `AccountId`, `Book`, `OwnerContext` | — |
| `fmis.valuation` | 6 | 1,498 | store → `PortfolioState` (equity, `mark_age`) | `Decimal` / `Money` |
| `fmis.plan` | 3 | 736 | plan adherence, stop placement | `Decimal` |

**The audit's headline finding is that this code is good.** It already satisfies almost every
Slice-4 principle without modification: unknown risk is `Absent(reason)` and never zero; no taxonomy,
liquidity figure or event-risk verdict is invented; `INDETERMINATE` is structurally distinct from
`APPROVED`; the sign rule for long and short is written once and refuses a transposed stop rather
than absolute-valuing it; `fmis.risk` and the computing modules of `fmis.position_sizing` are
AST-guarded to hold no numeric literal beyond `0` and `1`; and `ApprovalResult` has no field that
could hold *"take this trade"*.

**Nothing in it was rewritten.** This milestone connected it.

### 3.2 Break 1 — no producer

```
$ grep -rn "RiskBudget(" src/fmis --include='*.py'   ->  (nothing)
$ grep -rn "RiskLimit("  src/fmis --include='*.py'   ->  (nothing)
```

`RiskBudget` and `RiskLimit` were constructed **nowhere in `src/`** — only in four test files. No
CLI command, no configuration path and no product surface could bring one into existence. So
`per_trade_ceiling` was never consulted with a real budget, `SizingPolicy.fraction_for` never
resolved a fraction, `ApprovalEngine` never ran against real limits, and every downstream figure was
unreachable by construction.

### 3.3 Break 2 — no dashboard consumer

`fmis.swing_workspace.builder` put `approval_note` into `workspace.metadata` (line 218).
`fmis.operator_dashboard.sections.swing_view` **read `workspace.metadata` nowhere at all** — so the
dashboard never stated whether a size had been computed or which input was missing. A blank where
that sentence belongs reads as *nothing to report*.

`SymbolDecisionRow` — the `/swing/SYMBOL` page covering the whole scanned population, every `WAIT`
included — carried **no risk field of any kind**.

### 3.4 Live proof of unreachability, before any change

- `~/.fmits/` contained only `scan_memory/`. No store, no account, no budget, no fill, no mark.
- `GET /swing` → 39,966 bytes, **zero** risk content beyond one sentence of ranking prose.
- `GET /swing/BTCUSDT` → four panels: decision, timeframes, families, evidence. **No risk panel.**
- `fmits approve BTCUSDT --direction long --entry 60000 --stop 58000` on an empty store →
  `ApprovalUnavailableError: no account can be inferred…` — honest, and a dead end.

### 3.5 Trade geometry — real, and deliberately incomplete

The swing engine **does** produce geometry, and it is not invented: `stop` is the nearest structural
level from the execution timeframe, `targets` likewise, and `reference_price` is the execution-
timeframe close they were measured against. The engine deliberately **fabricates no entry** —
`reference_price` is *"a recorded fact, never an executable order price"*. `fmis.position_sizing`
already makes that the proposal's entry and carries the caveat.

So no geometry needed inventing, and none was invented.

### 3.6 Where the 2 % ceiling was

**Nowhere.** `SPEC` §8.1 states it; no code held it. It could not live in `fmis.risk` or the
computing half of `fmis.position_sizing`, both of which are guarded to hold no numeric literal
beyond `0` and `1`. A ceiling that exists only in a specification document is a ceiling nothing
enforces.

## 4. Gate D — money and numeric semantics

**Outcome: the semantics were already implemented; the ADR was missing.** `fmis.money` has held
exact, asset-tagged `Money`/`Quantity` since Milestone BI, sixty-odd modules depend on it, and the
durable store persists its canonical text — but `docs/adr/` ran 0001–0028 with no money ADR.

Ratified as **[ADR-0029](../docs/adr/ADR-0029-money-and-numeric-semantics.md)**. It describes the
boundary as built and **changed no production code**:

| quantity | type | why |
|---|---|---|
| account / declared equity, risk amount, notional, fees | `Money` (`Decimal` + asset) | summed into balances; float residue never closes a position |
| position quantity | `Quantity` (`Decimal` + asset) | same |
| entry, stop, target **once inside a proposal** | `Decimal` | compared against money figures |
| risk fraction, percent-of-equity limit, the 2 % ceiling | `Decimal` | a ceiling decided by representation error is not a ceiling |
| OHLCV, indicators, ATR, level prices, ratios | `float` — **unchanged** | measurements, not assertions; ADR-0013 §4 untouched |

`exact_from_market_price` is the single named `float` → exact crossing. `NaN`/`Infinity` are rejected
at construction. JSON numbers in the owner's config are refused by name, because JSON numbers are
binary floating point.

## 5. Gate E — the slice

**[ADR-0030](../docs/adr/ADR-0030-risk-policy-declaration-boundary.md)**: a new package,
`fmis.risk_policy`, is the owner's declaration boundary — the one place the specification's ceiling
is written, and the only producer of a `RiskBudget` in the repository.

```
~/.fmits/risk_policy.json          the owner's declared capital and fraction
        │
        ▼
RiskPolicyDeclaration              2% refused at construction; nothing defaulted
        ├── budget_from()      ──► RiskBudget      (fmis.risk)         ← first producer in src/
        ├── sizing_policy_from() ► SizingPolicy    (fmis.position_sizing)
        └── plan_for(assessment) ► TradeRiskPlan
                                       │  PositionSizer.size(..., remaining_open_risk=None)
                                       ▼
                            SymbolDecision.plan  →  TradeRiskPlanRow  →  /swing/SYMBOL panel
                                                                      →  /swing risk column + note
```

**No arithmetic was added.** `fmis.risk_policy.planning` contains no `*`, `/` or `//` on any money
value — asserted by an AST guard. Every quotient remains `fmis.portfolio_risk.geometry`'s, reached
through `PositionSizer.size`, the single place the sizing division is written in this repository.

### 5.1 The ceiling

`SPECIFICATION_PER_TRADE_CEILING = Decimal("0.02")`, cited to `SPEC` §8.1. A guard asserts that
`Decimal("0.02")` is constructed in **exactly one module of the entire source tree** — matched on the
AST shape rather than on text (`ast.unparse` normalizes the quotes, so a substring search passes
vacuously), with docstrings stripped so the prose in `fmis.portfolio_risk.constraints` that
*explains* the ceiling does not trip it. It was proved non-vacuous by adding a second spelling to a
copy of `src/` and confirming the guard fails. It is **structural**: a declaration above it cannot be constructed, so there is no
object to render and no branch to forget. `<= 2 %` is accepted, `> 2 %` is refused, and both
boundaries are tested exactly — `1.9999999999 %` in, `2.0000000001 %` out.

It is **never a default**. `budget_from` leaves `default_below_ceiling` `Absent`; the owner's
declared fraction travels on `SizingPolicy.risk_fraction` instead. A declaration with no fraction
resolves to no fraction at all, and the plan names the missing input rather than sizing at the
ceiling.

### 5.2 Declared capital, not measured equity

`RiskPolicyDeclaration.equity` is `ASSERTED` and dated, and the page says so: *"a figure the owner
typed, not a balance this system observed."* It is deliberately not `PortfolioState.equity`, which is
`MEASURED` from recorded fills. **No account was connected, no credential exists, and no capital
figure was guessed.**

### 5.3 Scope, stated rather than implied

Linear spot-like instruments · one trade in isolation · before fees, funding and slippage · planned
risk at invalidation, **not** maximum possible loss · no leverage modelled · no portfolio, exposure,
correlation, concentration, liquidity or event risk. Every one of those is printed on the panel.

## 6. Product surface

### `/swing/SYMBOL` — a fifth panel, between the families and the audit

Placed there deliberately: the trading question sits above the audit question, which is Slice 2's
own ordering rule.

**`WAIT` (most of the watchlist):**

```
planning   NO TRADE PLAN
           No trade plan is available for risk evaluation. The engine states no direction
           for this symbol, so there is no trade to plan. Nothing is missing and nothing
           is wrong. No entry, invalidation or position size is shown, because there is no
           trade here to size.
```

No entry. No stop. No size. Not a zero — nothing.

**A candidate, with a declared policy** (real hand-checkable figures):

```
planning            WITHIN DECLARED RISK BUDGET
direction           long
entry               60000     ← the execution-timeframe close the stop and targets were
                                measured against — a recorded fact, not an order price
invalidation        58000     ← where the thesis is wrong, not an order resting at a venue
risk per unit       2000 USDT
reward : risk       3 (6000 ÷ 2000)
declared capital    10000 USDT   declared 2026-09-06 — a figure the owner typed
risk per trade      0.005
hard ceiling        0.02      PROJECT_SPECIFICATION_V1 §8.1 — a hard ceiling, not a default target
capital at risk     50 USDT
maximum quantity    0.025 BTC
position value      1500 USDT
portfolio impact    unavailable — total open risk, concentration and correlation are not
                    evaluated, which is not the same as their being zero
```

**A candidate with an input missing:**

```
planning            NOT EVALUABLE
…
capital at risk, quantity, position value    unavailable — …
missing before a size can be produced (1)
  · a per-trade risk fraction. Declare `per_trade_fraction` — a fraction, not a percentage,
    at most 0.02. None is assumed: the specification states a ceiling and no default, and
    sizing at the ceiling would make the ceiling the target
```

### `/swing` — one column and one sentence

A `Risk` column carrying a **state and never a figure** — no size, no capital at risk, no
reward:risk, because a column of numbers is a column the eye ranks and the research record found
reward:risk associated with a *worse* outcome. And the note the dashboard used to drop:

> Risk: no risk policy is declared, so no trade-planning figure can be produced for any symbol.
> Nothing is assumed in its place — not a capital figure, and above all not a risk fraction.
> Declare one in `~/.fmits/risk_policy.json`: the capital you plan against, and the fraction of it
> you risk per trade (at most 0.02, which is a ceiling and not a target).

## 7. Independent hand-calculated test vectors

Every expected value below was calculated by hand and written as a literal. None was produced by
calling the code under test or by re-deriving it with the same formula.

| | equity | fraction | entry | stop | risk/unit | capital at risk | quantity | notional |
|---|---|---|---|---|---|---|---|---|
| **A** long | 10,000 | 0.005 | 60,000 | 58,000 | 2,000 | **50** | **0.025 BTC** | **1,500** |
| **B** wider stop | 10,000 | 0.005 | 60,000 | 55,000 | 5,000 | **50** | **0.01 BTC** | **600** |
| **C** short | 10,000 | 0.005 | 180 | 190 | 10 | **50** | **5 SOL** | **900** |
| **D** exact ceiling | 10,000 | 0.02 | 60,000 | 58,000 | 2,000 | **200** | **0.1 BTC** | — |
| **E** tiny price | 500 | 0.01 | 0.00004 | 0.00003 | 0.00001 | **5** | **500,000 SHIB** | **20** |
| **F** high price | 250,000 | 0.002 | 96,000 | 92,000 | 4,000 | **500** | **0.125 BTC** | **12,000** |

Plus the refusals: a long whose stop is above the entry, a short whose stop is below it, and a stop
equal to the entry — all `REFUSED` with the geometry printed, none absolute-valued, and **a zero
stop distance never yields an infinite quantity**.

## 8. Adversarial proof — targeted mutation campaign

Twelve mutations of the financial arithmetic, each applied to a **copy** of `src/` and run against
the risk-policy suite in a subprocess.

| mutant | result |
|---|---|
| M1 ceiling comparison `>` → `>=` | **KILLED** — `…at_or_below_the_ceiling_is_accepted[0.02]` |
| M2 ceiling check removed entirely | **KILLED** — `…above_the_ceiling_cannot_be_constructed` |
| M3 ceiling raised 2 % → 20 % | **KILLED** — `…two_percent_exactly_and_is_a_decimal` |
| M4 ceiling built from a binary float (`Decimal(0.02)`) | **KILLED** — same |
| M5 a default placed on the ceiling (ceiling becomes a target) | **KILLED** — `…no_default_below_it` |
| M6 declared fraction replaced by a constant (budget ignored) | **KILLED** — `…resolves_to_no_fraction_at_all` |
| M7 LONG/SHORT geometry swapped | **KILLED** — `test_vector_a_long` |
| M8 entry and stop transposed | **KILLED** — `test_vector_a_long` |
| M9 sizing quotient inverted | **KILLED** — `test_vector_a_long` |
| M10 a missing money figure silently becomes zero | **KILLED** — see below |
| M11 portfolio impact claims zero open risk | **KILLED** — `test_vector_a_long` |
| M12 declared fraction doubled before sizing | **KILLED** — `…used_unchanged_and_is_not_raised` |

**12 / 12 killed. M10 found a real hole and it was closed.** The first run of M10 survived: the
existing zero-check exercised only the *no-stop* path, where `plan_for` returns before the sizer runs
— so it proved nothing about a figure the sizer attempted and could not produce.
`test_a_figure_the_sizer_could_not_produce_is_absent_not_zero` was added for exactly that path
(complete geometry, no declared fraction) and kills it.

Two earlier "survivors" were **equivalent mutants of my own making**, not test holes:
`Decimal(repr(0.02)) == Decimal("0.02")` exactly, and one replacement inserted only a comment. Both
were replaced with real mutations, and both are killed above.

## 9. Non-vacuity

`tests/test_risk_policy_non_vacuity.py` pins the audit finding so it cannot silently return:

```python
assert _constructions_of("RiskBudget") == {"risk_policy/planning.py": 1}
assert _constructions_of("RiskLimit")  == {"risk_policy/planning.py": 1}
```

Before this milestone both returned `{}`. Also asserted: the size is produced by **the existing
engine** (a spy fails if `PositionSizer.size` stops being called, so a future change cannot grow a
parallel implementation in the projection layer); sizing runs with `remaining_open_risk=None` rather
than `Absent`; the deterministic figures reach the page the owner opens; and with no declaration the
same page renders the absence and **no number at all**.

## 10. Risk is not confidence, and risk does not decide

Three independent mechanisms, because a feature test that fixes the evidence cannot tell a size that
moved with it from one that did not:

1. **Vocabulary guard.** Every module is AST-scanned for `confidence`, `probability`, `score`,
   `strength`, `evidence`, `supporting`, `conflicting`, `independence`, `readiness`, `confirmed`,
   `candidate`, `win_rate`, `expectancy` as identifiers. None may appear.
2. **Import guard.** `fmis.risk_policy` imports neither `fmis.swing_setup` nor `fmis.setup_evidence`
   nor `fmis.decision_support`. It duck-types over the assessment, so the independence is checkable.
3. **Whole-record comparison.** Every field of every decision record is compared with and without a
   declared policy, excluding only the plan, plus the workspace's opportunities, wait list, no-trade
   groups, summary, ranking rule and scan order. All identical. **`WAIT` remains `WAIT`;
   `CANDIDATE` remains `CANDIDATE`.**

Further guards: no execution concept as an identifier anywhere in the package; no store, provider,
socket or network import; no clock (`datetime.now`, `time.time`) in any module, so a financial result
cannot change with wall-clock time; `models` and `planning` touch no filesystem.

A companion test asserts the *prose* ruling out execution and leverage is still present — so a
refactor that silenced the warnings to satisfy the identifier guard fails.

## 11. Non-regression

| check | result |
|---|---|
| **Policy non-regression** | `tests/test_swing_setup_policy_non_regression.py` — **4 passed**. The committed reproducible aggregate over 81 fixtures reproduces **byte-identically**: `sha256 8b22e6c9…28059c`. Distribution unchanged: **72 `WAIT` / 9 `CANDIDATE`**. The undocumented `096a575a…` figure is **not** cited, per report 0045 |
| **Reliability Gate** | `tests/test_operator_dashboard_startup_smoke.py` — passing. The SIGINT repair in `tests/dashboard_smoke_driver.py` was **not modified** |
| **Scan Memory** | observational, unchanged. No schema change, no risk state persisted, no new record kind, no write path added |
| **Full suite** | see §14 |

### 11.1 Two existing tests changed, and why

Both hard-coded a **panel index** to express an **ordering invariant**, and Slice 4 inserts a panel:

- `test_the_symbol_page_puts_the_summary_above_the_audit` pinned the first four panel titles exactly.
- `test_the_symbol_page_opened_with_the_audit_rather_than_the_decision` asserted the audit was at
  index `3`.

Both now state the relation they were always about — the decision is **first**, the audit is
**last**, and every trading panel is above it — so a milestone that adds a trading panel does not
have to relitigate the invariant. **The invariant is not weakened; it is now expressed.**

## 12. Performance

| | |
|---|---|
| `budget_from(declaration)` | **4.1 µs** |
| `plan_for(candidate)` | **49.6 µs** |
| `plan_for(WAIT)` | **4.2 µs** |
| `plans_for_results` (12 candidates) | **615 µs** |
| `build_swing_workspace`, 12 symbols | 2.14 → 2.76 ms (**+0.62 ms**) |
| render `/swing` | 0.09 → 0.10 ms (**+0.00 ms**) |
| render `/swing/SYMBOL` | 0.09 → 0.10 ms (**+0.01 ms**) |

Against a market-data refresh that takes 30–45 s, the whole risk layer is **sub-millisecond** and not
measurable on the page.

## 13. Live verification

Development instances on **8799** (PIDs 15519, 16746, 45350 across sessions), each stopped by its
own exact PID. The operator's 8787 was untouched throughout development and was restarted once at
handoff — §15.3.

| | |
|---|---|
| `GET /` · `GET /swing` · `GET /swing/BTCUSDT` | **200 · 200 · 200** |
| panel order on `/swing/BTCUSDT` | decision → timeframes → families → **risk and trade planning** → evidence audit → since the previous scan |
| live risk panel (no declaration) | *"unavailable — no risk policy is declared… nothing is assumed in its place"* |
| live risk panel (declaration supplied, isolated test config) | BTCUSDT is `WAIT` → **NO TRADE PLAN**, no entry, no stop, no size |
| `/swing` risk column | one state per row, no figures |
| current decision | unchanged for every symbol |
| Scan Memory | intact; no `GET` wrote anything |

### 13.1 A process slip, recorded rather than smoothed over

**The development dashboard on 8799 was started without an isolated scan-history root**, so it used
the default `~/.fmits/scan_memory` and appended **two scans** to the operator's own rolling buffer
(`20260906T172030…` and `20260906T174023…`). Report 0044 used an isolated root for exactly this
reason and this milestone should have done the same.

What it does and does not mean, checked rather than assumed:

- Both are **genuine scans of the operator's own 20-symbol watchlist**, produced by the same engine
  under the same policy, minutes apart from his own. All five stored scans cover the **identical**
  universe, so every one remains comparable.
- The buffer retains **8** and holds **5**, so **nothing was evicted and no record was lost**.
- The consequence is narrow: the operator's next refresh compares against the 19:40 scan rather than
  the 18:47 one. Both are real scans of the same universe, so the comparison stays valid — and is
  slightly more current.

**The records were deliberately not deleted.** The store is append-only by design, they contain
correct data, and removing them would be a second unrequested mutation of the owner's runtime state
to tidy away the first. The operator's dashboard process was not stopped or signalled by this —
the restart in §15.3 is a separate, deliberate act.

**No live candidate was fabricated.** The live market produced only `WAIT` on this scan, so
candidate-specific verification used controlled fixtures through the real projection and renderer
(§7, §16). `~/.fmits/risk_policy.json` was **not created** — the isolated declaration used for the
declared-state check lives in the session scratchpad only.

## 14. Full regression

Run started **after** the last production and test edit — the §15.2 punctuation repair and the two
tests that pin it — under `-W error`, with **no other pytest process alive** and a unique output
path. Started 19:26:28, finished 19:37:38 on 2026-09-07; `find src tests -name '*.py' -newermt` over
the start instant returns nothing, so no source or test file changed while it ran:

```
14699 passed in 669.95s (0:11:09)
EXIT=0
```

**0 failed · 0 skipped · 0 warnings.**

The count was predicted before the run and matched exactly, which is what makes it checkable rather
than merely reported:

| | |
|---|---|
| baseline at `03dd4e0` | 14,533 |
| new `tests/test_risk_policy_*.py` | + 165 |
| `risk_policy` added to `test_scan_memory_architecture.DECIDING_PACKAGES` (parametrized) | + 1 |
| **expected** | **14,699** |
| **collected and passed** | **14,699** |

### 14.1 A second process slip, and what caught it

**Two full-suite runs were left executing concurrently, writing to one output file.** A "final" run
was started, three further edits were then made, a second run was started — and the first was never
stopped. Both redirected to the same path with `>`, so each wrote at its own offset over the other's
bytes. When the stale run finished it reported `14692 passed`, `EXIT=0`, which is indistinguishable
at a glance from the clean result being waited for.

**The exit code did not catch it; the arithmetic did.** The expected collection was known
independently: baseline **14,533** + **163** new risk-policy tests + **1** from adding `risk_policy`
to `test_scan_memory_architecture.DECIDING_PACKAGES` (a parametrized guard) = **14,697**. The stale
run reported 14,692 — exactly **4** short, matching the four tests added after it started. Without
that accounting a stale number would have been written into this report and the gate called closed
on it.

*(Those are the figures as they stood at that moment. §14's total is **14,699**, because the resumed
session in §15.2 added two more tests. The two sections are not in conflict: 163 + 2 = 165, and
14,697 + 2 = 14,699.)*

Both runs also contended for CPU, which independently disqualifies a result covering the
timing-sensitive dashboard smoke tests.

Report 0045 established this rule for this repository — *the run must begin after the last edit* —
and this milestone broke it. The result recorded in §14 is from a single run with **no other pytest
process alive**, a unique output path, and no edit after it began. Recorded here rather than
silently re-run, because a report that shows only the run that worked teaches nothing about how
close the wrong number came to being published.

## 15. Security review

- No credential, key, token or secret is read, written, logged or stored anywhere in this change.
- The declaration file's keys are validated against a **closed set**, so a file carrying `api_key`,
  `secret`, `passphrase`, `private_key` or `password` is **refused by name** rather than ignored — a
  loader that skipped unknown keys would make a credential invisible rather than impossible. Tested.
- An AST test asserts the loader names no `environ`, `getenv`, `keyring`, `urlopen`, `requests` or
  `socket`.
- No exchange, broker or account is connected. No order, preview, paper or shadow order exists. No
  write path was added to the durable store; the whole feature is read-only and a repeated `GET`
  mutates nothing.
- No test touches the owner's real `~/.fmits/risk_policy.json`; every one uses `tmp_path`.

## 15.1 Self-review, and what it caught

The financial-safety and architecture checklists were worked through against the built code rather
than against intent. Every answer is *no* where it must be: 2 % is nowhere a default; no path
exceeds it; float rounding cannot bypass it (mutant M4); missing risk cannot become zero (M10);
missing portfolio state cannot become zero exposure (the type refuses it); `WAIT` cannot acquire a
size (the type refuses that too); risk cannot change a `SetupAssessment` (whole-record comparison);
a strategy cannot size itself and an evidence count cannot move a fraction (vocabulary and import
guards); no AI touches any of it; leverage is not modelled at all rather than approximated; absent
correlation, liquidity and event risk are **not evaluated** rather than assumed benign; and no real
capital can be inferred without explicit input.

**Three things the review found and fixed, worth recording because two of them are the exact failure
mode this milestone exists to correct.**

1. **`PLANNING_LIMITATIONS` was dead capacity.** It was defined, exported and rendered **nowhere** —
   new capacity with no consumer, in the milestone whose whole premise is that capacity without a
   consumer is the repository's recurring failure. Fixed by giving it its consumer: it is now carried
   onto the row and rendered as a disclosure on the panel, which also put the instrument-scope
   limitation (*not correct for inverse contracts, dated futures or options; no leverage modelled*)
   on the page, where §61 wants it. A test asserts every entry reaches the panel, and that a symbol
   with no trade to plan carries no limitations block.

2. **The package published eight exports nothing outside it used.** `fmis.risk`,
   `fmis.portfolio_risk` and `fmis.position_sizing` carry **one, one and zero** such exports
   respectively; publishing eight would be a public surface no consumer asked for. Trimmed from 24
   to 16, with the eight left reachable on their own modules and the reason recorded there. Now
   **zero** unused exports.

3. **The `basis` sentence was orphaned.** *"The fraction 0.005 the owner stated…"* explains the
   *risk per trade* row and was printing as a loose paragraph several rows below it, after the reader
   had already scrolled past the number it explains. Moved directly under that row.

A fourth item was a **test defect rather than a product one**: the assertion that the page never
claims a maximum possible loss was a bare substring check, and it began failing the moment the page
started **denying** the claim in those words. Rewritten to assert the claim is absent — every
occurrence negated — rather than that the phrase is.

## 15.2 A defect found after the first closure, and fixed

**A copy fix landed on one side of a seam and not the other.** The `WAIT` panel's sentence is
assembled from three pieces — a fixed opening, the engine's own reason, and a fixed closing. An
earlier edit capitalised the engine's reason and gave it a terminal stop, but the renderer's join was
left as a colon, so the live page read:

```
No trade plan is available for risk evaluation: The engine states no direction for this symbol.
```

A colon introducing a capitalised sentence. Worse, the renderer's *fallback* string — used when a
plan carries no reason of its own — was still lowercase with no terminal stop, so that branch would
have rendered `…for this symbol No entry, invalidation or position size is shown`. That branch is
unreachable today, because a `NO_TRADE_PLAN` always states a reason; a fallback nobody exercises is
a fallback nobody notices is malformed.

This is the **one sentence most of the watchlist ever shows** — every `WAIT` symbol, every day — so
it is worth more than its size suggests. Both sides of the seam are now correct, and the *joined*
result is pinned by two tests rather than the pieces, because pinning the pieces is exactly what let
a half-landed fix pass. The tests were proved non-vacuous by restoring the defective construction in
a copy of `src/` and confirming they fail.

The full suite was re-run after this edit; §14 records that run and no earlier one.

## 15.3 Operator dashboard handoff, and a live confirmation of report 0045

Production code changed, so the operator's instance was serving a stale build and had to be
restarted. It was stopped by **its own exact PID**; `pkill` was not used.

**`SIGINT` did not stop it, and that is report 0045's root cause observed in production.** PID 74079
was started as a background job, so its `SIGINT` disposition was `SIG_IGN` — inherited across `exec`
and never restored — and the kernel discarded the signal. Ten seconds of waiting confirmed it was
still serving. `SIGTERM` ended it in under two seconds.

This is **not** a defect and nothing was changed for it. Report 0045 fixed the *test harness*
(`tests/dashboard_smoke_driver.py`) and deliberately left `src/` alone, on the grounds that
`fmits dashboard &` ignoring Ctrl-C is correct POSIX behaviour. What is new here is the operational
consequence, worth recording because it is not obvious: **Ctrl-C in the terminal that owns the
dashboard works; `kill -INT` against a backgrounded instance silently does nothing.** Use `SIGTERM`.

| | before | after |
|---|---|---|
| PID | 74079 (started 2026-09-05 11:14) | **18359** (started 2026-09-06 20:05) |
| URL | `http://127.0.0.1:8787/` | unchanged |
| code served | pre-Slice-4 | Slice 4 |

Verified after the restart: `/`, `/markets`, `/swing`, `/swing/BTCUSDT`, `/swing/ETHUSDT` and
`/portfolio` all **200**; the risk panel present in position four; repeated `GET`s **byte-identical**;
and scan-memory continuity intact **across the restart** — the new process compared against the scan
the previous one had recorded and reported 0 material changes across 20 symbols.

## 16. Product First — before and after

**BEFORE.** Dovydas could open `/swing/BTCUSDT` and read a complete decision, evidence report and
timeframe context — and could not learn anything at all about what a trade there would cost him. No
entry, no invalidation, no risk per unit, no position size, no ceiling, and **no statement that any
of it was missing or why**. The engine that computes all of it existed, was tested, and had no first
link.

**AFTER.** Every scanned symbol carries a trade-planning record. Where the engine states no
direction, it says so in one sentence and shows nothing else. Where a directional candidate exists
and he has declared his planning capital and the fraction he risks, the page shows the entry, the
invalidation, the risk per unit, the reward:risk, the capital at risk, the maximum quantity and the
position value — each derived by the existing engine, each traceable to a declared input, and each
bounded by a 2 % ceiling that cannot be exceeded by configuration. Where something is missing, the
page names it and offers the remedy.

**Why this is product value.** It answers a question he could not previously ask of this system:
*if this became actionable, what would it actually risk, and does it fit inside my own limits?* It
needs no exchange connection, no recorded holdings and no capital figure anyone had to guess.

**What it still cannot do.**

- No portfolio impact. Total open risk, concentration and correlation are **not evaluated** — stated
  as such, never as zero. A plan inside the per-trade ceiling is not thereby one the book has room for.
- No fees, funding, spread or slippage. The figure is planned risk at invalidation, **not** maximum
  possible loss; a gap through the stop loses more.
- No leverage, inverse contracts, dated futures, options or FX conversion. Linear spot-like only.
- No lot-size or step-size rounding — the quantity is exact and must be rounded **down** at the venue.
- No liquidity data and no event calendar, so neither is evaluated.
- No `fmits` command writes or inspects the declaration; the owner edits the JSON file directly.
- **No trade is executed, previewed, or recorded.** Slice 4 stops at decision support.

## 17. Research boundary

Unchanged and unaffected. `CA = NO_EDGE`, `CB = UNDERPOWERED`, `CC = INFEASIBLE` and the `CD`
dependence conclusions stand. Nothing in this milestone claims a validated edge, a profitable
strategy, improved expectancy, a safer strategy or production trading readiness. A risk figure is
arithmetic over the owner's own declared limits and says nothing whatever about whether a trade is
worth taking.

## 18. Operator configuration still required

**One decision remains the owner's and was deliberately not made for him** (Slice 4 brief §56, §80):

Write `~/.fmits/risk_policy.json`:

```json
{
  "contract_version": 1,
  "equity": {"amount": "10000", "asset": "USDT"},
  "declared_at": "2026-09-06T00:00:00Z",
  "per_trade_fraction": "0.005",
  "note": "planning capital only"
}
```

`equity` is the capital he plans against — his figure, in quote asset, as text. `per_trade_fraction`
is a **fraction, not a percentage**: `0.005` is 0.5 %. The hard maximum is `0.02`, and it is a
ceiling, not a suggestion. Omitting `per_trade_fraction` is legitimate and produces `NOT EVALUABLE`
naming that input, rather than a size at the ceiling.

Until that file exists, every planning section states its absence and prints the remedy. **That is
the correct product result, not a defect.**

## 19. Deferred

Portfolio impact from recorded positions · total open risk across a book · correlation as risk
context · concentration axes · fees and slippage · lot-size rounding · leverage · non-linear
instruments · FX conversion · a `fmits risk` command to show and validate the declaration ·
persisting a versioned `RiskBudget` lineage through `RiskRepository` · risk in Scan Memory's
temporal comparison.

Each is a milestone with its own consumer. **None was built without one here.**
