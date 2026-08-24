# FMITS Operator Dashboard V0 (Milestone BV) — Implementation Record

| Field | Value |
|---|---|
| **Report number** | 0032 |
| **Title** | FMITS Operator Dashboard V0 (Milestone BV) — `fmits dashboard` |
| **Date** | 2026-08-24 |
| **Report type** | Implementation |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `0f31293` (production code + tests), on base `1a73cf8`, with this product-docs commit recorded directly on top of it |
| **Status** | Final |

---

## 1. What the owner can do now that was impossible before

```
uv run fmits dashboard
```

The owner opens `http://127.0.0.1:8787/` in a browser and **sees** FMITS. Seven
pages over the engines that already existed: what the tracked markets are doing,
what the macro series are doing and in which unit, which setups confirmed and
which are waiting and which the engines concluded are no trade, what the recorded
book holds, what the simulator is running, whether any of it has worked, and the
state of every data source the refresh touched.

Before BV, every one of those facts existed but could only be read as terminal
text, one command at a time, with no way to move between them and no way to see
two of them at once. The dashboard changes nothing beneath it — **not one figure
on any page is computed by this milestone** — and that is the point: it is a
window, and the engines behind it do not know it exists.

**What it deliberately does not do:** place an order, record a trade, activate a
paper trade, change a stored value, or recommend anything. It answers `GET` and
`HEAD`, binds loopback, and exposes no method that could change any state.

---

## 2. Starting state, verified rather than assumed

| Fact | Value |
|---|---|
| `HEAD` at start | `1a73cf85ea4cc48c3422fa1bd876d314232f158d` |
| `origin/main` at start | `1a73cf85ea4cc48c3422fa1bd876d314232f158d` |
| Ahead / behind | `0 / 0` |
| Stash | empty |
| Unresolved operation | none |
| Untracked at start | 16 research documents under `docs/design/` and `docs/reviews/` |

The expected HEAD given in the brief was confirmed by `git rev-parse`, not
assumed. The 16 pre-existing research documents were left untouched.

---

## 3. Repository audit — what already existed

The audit's purpose was to find the composition roots the dashboard could reuse,
so that no composition logic would be duplicated.

**Existing user-facing surfaces** (`fmis.pipeline.cli`, 23 commands): `facts`,
`mtf`, `regime`, `swing`, `setup`, `evidence`, `scan`, `backtest`, `daily`,
`today`, `workspace`, `pulse`, `macro`, `portfolio`, `approve`, `trade`,
`simulate`, `statistics`, `performance`, `expectancy`, `equity`, `trades`,
`archive`.

**The decisive finding.** `fmis.swing_workspace.run_swing_workspace` already
assembles the global market summary, ranked opportunities, wait list, no-trade
groups, unreadable symbols, active paper trades, portfolio overview, book
exposure, statistics snapshot and aggregated warnings — from **one** scan, **one**
store read, **one** valuation and **one** approval pass, by delegating to
`fmis.today.assemble_today`. Five of the dashboard's seven sections therefore
needed no new composition at all.

**Search for existing web / dashboard / API / serialization code:** none. No
module in `src/` imports `http.server`, `socketserver`, or any HTTP client for
serving. There was no presentation layer, no view model, no JSON projection and
no frontend of any kind. Nothing was duplicated because nothing existed.

**Two constraints found in the repository, not chosen by this milestone:**

1. `pyproject.toml` declares `dependencies = []`.
2. `tests/test_statistics_completeness.py` holds a `FORBIDDEN_VOCABULARY` guard
   naming `flask`, `django`, `fastapi`, `numpy`, `pandas`, `scipy`, `matplotlib`,
   `plotly`, `requests`, `websockets` and others as source-level absences.

---

## 4. UI technology decision

**Chosen: a server-rendered local web application on the standard library's
`http.server`, with hand-written HTML and one CSS file. Zero new dependencies.**

### Alternatives evaluated and rejected

| Option | Verdict | Why |
|---|---|---|
| **A. Minimal server-rendered local web app (stdlib `http.server`)** | **Chosen** | Routing, escaping and a socket are all in the standard library. No build step, no bundler, no lockfile change. Satisfies every requirement below, and the backend/frontend seam is a Python function returning a string. |
| **B. Small Python UI framework (Streamlit)** | Rejected | Its dependency tree includes `pandas` and `numpy` — both on the repository's existing forbidden list, which would have to be widened for a *presentation* layer. It also inverts control: the script re-runs top to bottom on interaction, which fights the "one refresh, one snapshot" contract this milestone needs. |
| **C. Backend API + separate frontend (FastAPI/Flask + React/Next)** | Rejected | `fastapi` and `flask` are named in the forbidden guard. It adds a Node toolchain, a build step and a second language for seven static routes. The brief explicitly warned against a permanent frontend framework commitment for a V0 that will be redesigned. |

### How the choice meets each stated requirement

| Requirement | How |
|---|---|
| Local visual dashboard on macOS | `fmits dashboard` binds `127.0.0.1:8787` |
| Interactive navigation | Seven top-level routes plus per-symbol detail, all plain links |
| Tables / cards / status views | Semantic HTML tables, tiles and status chips |
| Future charts | Inline SVG; the equity curve is already one |
| Future filters | Query parameters (`?refresh=1` is the first) |
| Easy local launch | One command, no build step |
| Clear backend/frontend boundary | `models.py` is the contract; `render.py` consumes it |
| Read-only V0 | `GET`/`HEAD` only; every other method returns 405 |
| Redesign without touching engines | Delete `render.py` + `theme.py`, write a new UI against `models.py` |
| Reasonable testing | 847 focused tests; 100 % statement and branch coverage |
| Minimal dependencies | Zero added |

**Migration boundary.** If this is later replaced by a JSON API plus a
JavaScript frontend, the replacement point is `render.py` — a function taking an
`OperatorDashboardSnapshot` and returning a string. A JSON serializer at that
same seam would serve the same snapshot to any client.

---

## 5. Architecture and the read-model boundary

```
FMITS deterministic engines
        │
        ├── fmis.swing_workspace.run_swing_workspace  ─┐
        ├── fmis.pipeline.pulse.run_market_pulse       │  four reads,
        ├── fmis.pipeline.macro.run_macro_context      │  one refresh
        └── fmis.statistics.report_for_store          ─┘
        │
        ▼
fmis.operator_dashboard.sections     translation only: rename, split, format
        │
        ▼
fmis.operator_dashboard.models       the presentation contract  ◄── the seam
        │
        ▼
fmis.operator_dashboard.render/theme HTML and appearance        ◄── replaceable
        │
        ▼
fmis.operator_dashboard.server       stdlib socket, GET/HEAD only
```

**The UI imports one package.** `fmis.pipeline.cli` gained exactly one new
import — `fmis.operator_dashboard` — not twenty domain packages.

**No CLI text is parsed anywhere.** Every section consumes structured Python
values. `render_*` functions from the terminal renderers are never called, and
no rendered page is ever scraped.

### The read-model contract

Root: `OperatorDashboardSnapshot`, carrying `refreshed_at`, `reference_time`,
`counts`, seven `DashboardSection` envelopes, `warnings`, `limitations` and
`schema_version`.

Each `DashboardSection[T]` carries `name`, `status`, `as_of`, `source`, `data`
and `unavailable_reason`. Invariants enforced at construction:

* an `UNAVAILABLE` section **must** state a reason — an unexplained absence
  renders as an empty section, and an empty section reads as a calm one;
* an `UNAVAILABLE` section **must not** also carry data;
* every timestamp **must** be timezone-aware.

`DashboardSectionStatus` has exactly three members — `AVAILABLE`, `EMPTY`,
`UNAVAILABLE`. The fourth anybody reaches for, *degraded*, is a severity
judgement this layer has no basis to make.

`SourceState` has six — `AVAILABLE`, `BEHIND_SCHEDULE`, `SCHEDULE_UNKNOWN`,
`UNSUPPORTED`, `UNAVAILABLE`, `ABSENT`. **There is deliberately no `STALE`.**
`fmis.market_pulse` refuses the word because staleness is a judgement about
usability; `BEHIND_SCHEDULE` — older than that source's own publication cadence
explains — is what can be stated objectively, and it is the engine's own verdict
carried across, not one computed here.

**Three absence vocabularies collapse to one shape.** `NotAvailable` (from
`fmis.today`), `Absent` (from `fmis.provenance`) and the
`value`/`unavailable_reason` pairing (from `fmis.market_pulse`) all become
`(value | None, reason | None)` with exactly one set. That invariant is what
keeps *zero* and *absent* visually distinct on the page.

---

## 6. Pages, navigation and exact functionality

| Route | Page | Contents |
|---|---|---|
| `/` | Overview | Swing counts (scanned / confirmed / candidates / waiting / unreadable / open positions / paper trades), top opportunities, the pulse table, portfolio headline tiles, performance headline tiles, data-health counts, warnings |
| `/markets` | Markets | Full pulse grouped by cadence family, co-movement against the named reference, full macro context with levels and units, yields in basis points, cross-asset relationships with alignment counts, unsupported markets with reasons |
| `/swing` | Swing | Top opportunities · Wait list · No trade · Could not be read, each with state, direction, approval, sufficiency, evidence digest, R:R, stable identity, paper status, held status; the ordering rule printed verbatim |
| `/swing/<SYMBOL>` | Swing detail | Setup · Evidence · Thesis/Confirmation/Invalidation · Identity, paper and holdings · Ordering key component-by-component, blocking reasons, approval warnings |
| `/portfolio` | Portfolio | Position tiles, open positions, books, risk limits with stated/current/status, notes — recorded positions only |
| `/paper` | Paper | Activation id, market, state, open size, entry, stop, initial stop, initial risk, total R, MFE R, MAE R, bars, stop widenings |
| `/performance` | Performance | One section per quote asset: trades, open, resolved, sample floor, net, expectancy, win rate, profit factor, average R, max drawdown, the equity curve as SVG, every closed-trade step, exclusions |
| `/system` | System | Every source with its state, last observation, age, provider and detail; per-state counts; each section's status/as_of/source; the surface's stated limitations |

Every panel carries `as of <instant> · <source>`. The header carries **last
refresh** and **data as of** on every page, always both.

---

## 7. Exact data reused per section

| Section | Engine output consumed | Computed here |
|---|---|---|
| Overview counts | `SwingWorkspace.summary` | nothing |
| Pulse | `MarketPulse.readings` / `.unavailable` / `.universe.unsupported` / `.co_movements`; `MarketReading.age_at()`, `.freshness_at()` | nothing |
| Macro | `MacroContextReport.levels` / `.readings` / `.rate_facts` / `.relationships` / `.unavailable` / `.universe.unsupported` | nothing |
| Swing | `SwingWorkspace.opportunities` / `.wait_list` / `.no_trade` / `.unanalysed`, each `RankedSetup.key.components` | nothing; **order is inherited index-for-index** |
| Portfolio | `SwingWorkspace.portfolio` (a `PortfolioOverview`) and `.books` | nothing |
| Paper | `SwingWorkspace.paper` (`PaperPosition`) and `.paper_note` | nothing |
| Performance | `StatisticsReport.assets[].general/.performance/.equity/.drawdown` | nothing but pixel coordinates |
| Data health | the states above, plus `PortfolioOverview.store_present` | nothing |
| Warnings | `SwingWorkspace.warnings` | nothing |

**The one piece of arithmetic in the package** is the equity chart scaling
`cumulative` values into an SVG viewBox. Pixels are not financial observations,
and the page says so beneath the chart: *"The line between two points is drawn,
not observed — no trade closed between them."* An architecture guard asserts
that no other function in the package contains a `-`, `*` or `/` on an engine
value.

---

## 8. Dependencies added

**None.**

`pyproject.toml` still declares `dependencies = []`; `uv.lock` is unmodified.
Verified by a clean-environment install into a fresh virtualenv:

```
fmis==0.0.1
pip==25.0.1
```

All seven routes served `200` from that clean environment, and the `fmits`
entry point resolved. Every import in the package is either the standard library
(`dataclasses`, `datetime`, `decimal`, `enum`, `html`, `http`, `pathlib`,
`threading`, `typing`, `urllib`) or `fmis` itself; a guard asserts the permitted
set.

---

## 9. Read-only and security guarantees

| Guarantee | How it is enforced |
|---|---|
| No order, trade, activation or stored value can change | No store write verb, no execution verb and no `open()` appears anywhere in the package — asserted by AST guards over every module |
| Only `GET` and `HEAD` reach a handler | `do_POST`/`do_PUT`/`do_PATCH`/`do_DELETE`/`do_OPTIONS` are **defined** and all five return `405` with an `Allow` header. Defined deliberately: the stdlib's own `501` reads as *not implemented yet*, which invites implementation |
| Loopback only | `DEFAULT_HOST = "127.0.0.1"`; binding anything else raises `ValueError` unless `allow_public=True` is passed explicitly. Refused, not warned about |
| No filesystem is served | There is no static route and no request path is ever joined to a filesystem root. Traversal attempts return `404` |
| No credentials, no `.env` | The package contains no `environ`, `getenv`, `.env` or credential reference at all |
| Nothing is cached by the browser | `Cache-Control: no-store, max-age=0` on every response |
| No scripts can run | `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:`; no `<script>` is emitted, and a guard asserts it |
| Not embeddable, no referrer leakage | `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff` |
| No page can submit anything | No `<form>`, `<button>`, `<input>`, `<textarea>` or `<select>` on any route — asserted per route per element |
| Every value is escaped | One `_e()` helper wraps `html.escape`; a mutation disabling it is killed |

**Live proof of read-only.** The owner's store at `~/.fmits/store` did not exist
before the demonstration; after browsing all seven routes, the symbol detail page
and a forced refresh, it **still did not exist**. The dashboard did not even
create the directory.

---

## 10. Refresh model and fetch behaviour

**One snapshot is held and shared by all seven routes.** A refresh happens on the
first request and thereafter only when explicitly asked for — the `refresh now`
link in the header, which is `?refresh=1` on the current route. It is a link, not
a button: a button implies a form, a form implies a `POST`, and this surface has
no method that could change anything.

**Measured live:**

```
/?refresh=1        200   45.45s     ← four engine reads
/markets           200    0.00s
/swing             200    0.00s
/portfolio         200    0.00s
/paper             200    0.00s
/performance       200    0.00s
/system            200    0.00s
/swing/BTCUSDT     200    (instant)
```

One refresh, seven pages. This is not an optimisation — it is the correctness
property. Seven routes each fetching would mean seven different instants behind
one header, and the header can only state one.

`REFRESH_READS` names the four reads, and a test asserts the composition root
performs exactly four calls, one each. Three sections (swing, portfolio, paper)
share the single workspace read, and that is stated rather than hidden: when it
fails, all three fail together and each carries the same reason.

Concurrent refreshes collapse into one under a lock — verified with four threads
on a barrier: one refresh performed, four identical snapshots returned, no waiter
saw a half-assembled page.

**No caching that risks stale financial data.** The header always carries both
instants, and every panel carries its own `as_of`. An old page cannot pass for a
live one.

---

## 11. Failure isolation

Each read catches exactly the exception family its own CLI command catches —
`MarketPulseError`, `MacroError`, `SwingWorkspaceError`/`TodayError`/
`APPROVAL_ERRORS`, `STATISTICS_ERRORS`. Everything else propagates.

**Not one `except Exception` exists in the package**, and a guard asserts it. A
`KeyError` in a mapping function is a defect, and a dashboard that renders a
defect as a tidy amber "section unavailable" panel is a dashboard that hides its
own bugs.

Verified: macro fails → pulse, swing, portfolio, paper and performance all
render; pulse fails → the other five render; the workspace fails → pulse, macro
and performance render, and data health reports the store as unavailable rather
than silently omitting it.

---

## 12. Tests

### Focused BV suite — 847 tests

| File | Tests | Covers |
|---|---:|---|
| `test_operator_dashboard_architecture.py` | 487 | computes nothing · orders nothing · writes nothing · no execution verb · no third-party import · no import cycle · no export collision · redesign seam intact · no judgement vocabulary |
| `test_operator_dashboard_render.py` | 143 | every route renders · both instants · no write controls · absence never a dash · colour semantics · escaping · charts · formatting |
| `test_operator_dashboard_server.py` | 58 | routing · traversal refusal · 405 on every mutating method · loopback binding · hardening headers · refresh model · concurrency · store untouched |
| `test_operator_dashboard_hostile.py` | 37 | every source dark · staleness visible · 200 symbols · huge decimals · long messages · paper/live separation · malformed routes · concurrent and repeated use |
| `test_operator_dashboard_sections.py` | 31 | the three absence vocabularies · unsupported markets · freshness carried · ordering preserved · paper/portfolio separation |
| `test_operator_dashboard_coverage.py` | 30 | co-movement · relationships · books and limits · paper rows · failure paths · small surfaces |
| `test_operator_dashboard_compose.py` | 20 | four reads · section isolation · determinism · statuses · no write method |
| `test_operator_dashboard_surfaces.py` | 17 | rate facts in basis points · paper metrics · statistics per quote asset · equity curve |
| `test_operator_dashboard_models.py` | 16 | section invariants · zero vs absent · no `STALE` · no score |
| `test_pipeline_cli_dashboard.py` | 8 | command registration · flags · read-only description · bind failures |

Fixtures build **real** engine objects — genuine `MarketPulse`,
`MacroContextReport`, `SwingWorkspace` and `StatisticsReport` values — so a field
an engine renames fails a test here rather than rendering as a silent absence.

### Coverage — 100 % statement and branch

```
Name                                      Stmts   Miss Branch BrPart  Cover
src/fmis/operator_dashboard/__init__.py       8      0      0      0   100%
src/fmis/operator_dashboard/compose.py       89      0     12      0   100%
src/fmis/operator_dashboard/models.py       345      0     24      0   100%
src/fmis/operator_dashboard/render.py       360      0    102      0   100%
src/fmis/operator_dashboard/sections.py     178      0     64      0   100%
src/fmis/operator_dashboard/server.py       120      0     20      0   100%
src/fmis/operator_dashboard/theme.py          5      0      0      0   100%
TOTAL                                      1105      0    222      0   100%
```

Backend read-model code only. Template and CSS coverage is not claimed as
financial correctness.

### Regressions and the full suite

| Gate | Result |
|---|---|
| BU macro regressions | pass |
| BT pulse regressions | pass |
| BS swing-workspace regressions | pass |
| BR / BG-D1 evidence regressions | pass |
| BP statistics regressions | pass |
| BO / BN / BM / BL paper, sizing, portfolio, valuation | pass |
| today / pipeline regressions | pass |
| **Full repository** | **10,671 passed** |
| **Full repository under `-W error`** | **10,671 passed** |
| Import cycles (297 modules) | 0 |
| Export collisions (all `fmis` packages) | 0 |
| `git diff --check` | clean |
| Secret scan | none |
| Clean-environment install | `fmis==0.0.1`, zero dependencies, all routes 200 |

---

## 13. Mutation testing — 34 / 34 killed

Semantic mutations over the meaning-bearing decisions, restored by in-memory
byte restoration (never `git checkout --`), with the working tree verified
byte-identical afterwards.

| Area | Probes | Survived |
|---|---:|---:|
| Read-model mapping (absence reason dropped, vocabularies conflated) | 2 | 0 |
| Stale vs fresh (behind-schedule and unknown-schedule reported as available) | 2 | 0 |
| Unsupported markets (dropped entirely, or shown as an ordinary outage) | 2 | 0 |
| Ordering (re-sorted by symbol, ordering key not carried) | 2 | 0 |
| Paper vs live (held and paper status collapsed) | 1 | 0 |
| Section isolation (failure rendered as empty; defects swallowed) | 4 | 0 |
| Data health (failed domain vanishes; absent store shown as available) | 2 | 0 |
| Provenance (`as_of` replaced by the refresh instant) | 1 | 0 |
| Render (bare dash, zero tinted as gain, sign dropped, negative age hidden, cadence grouping removed, escaping disabled, refresh instant hidden, silent truncation) | 8 | 0 |
| Server (POST accepted, binds all interfaces, default host widened, cache removed, lock removed, unknown path falls through, encoded separator accepted, no-store dropped) | 8 | 0 |
| Models (unavailable need not say why, naive timestamps accepted) | 2 | 0 |
| **Total** | **34** | **0** |

One mutant survived the first run — *"an absent store reported as available
rather than empty"* — which was a genuine gap: the suite did not assert that the
three portfolio statuses (`EMPTY` for a store that does not exist yet,
`AVAILABLE` for one that was read, `UNAVAILABLE` for one that failed) stay
distinct. A test was added and the mutant now dies.

---

## 14. Hostile review — findings and fixes

Attacking the surface found **five real defects**, all fixed. Each was a
*misleading page* rather than a crash, which is the class that matters.

### D1 — Every crypto row showed three false "unavailable" cells

The first live page unioned horizon columns across all markets, so each crypto
row carried three *unavailable* cells for macro-only windows and vice versa.
Milestone BU had already fixed exactly this in the terminal renderer — *"a daily
series has no twenty-four-hourly-bar window, and never will"* — and the table
reintroduced it. Printing *unavailable* there says a measurement was attempted
and failed when none was ever attempted.

**Fix:** markets are grouped into tables by the cadence family they were actually
measured over. Guarded by `test_markets_with_different_cadences_get_different_tables`.

### D2 — DXY and XAU vanished from the page entirely

The mapping read `pulse.readings` and `pulse.unavailable` but not
`pulse.universe.unsupported`. Unsupported markets were never *asked for*, so they
live on the universe rather than in the failure tuple. The result answered *"what
can this system not tell me?"* with silence — the exact question the section
exists to answer.

**Fix:** `_unsupported_benchmarks()` reads the universe for both pulse and macro.
Guarded, and a mutation dropping it is killed.

### D3 — One long reason printed six times per row

Unsupported markets in the macro table repeated the same 60-word reason across
six columns; yields repeated theirs across three.

**Fix:** markets with no reading get their own one-reason table; repeated
absence reasons within a table become numbered footnotes printed once in full,
with the whole text also on each cell's hover title. Nothing is truncated.

### D4 — "unavailable: no detail was stated" on healthy sources

Data-health rows for markets that had been read perfectly well rendered as
absences, because their detail was empty.

**Fix:** every `SourceState` maps to a sentence. Guarded by
`test_every_health_row_states_a_detail_even_when_it_was_read_fine`.

### D5 — Paper and portfolio framing disappeared when empty

The *"simulated, never real exposure"* note on `/paper` and the *"paper is never
added into any figure"* note on `/portfolio` lived in the populated bodies only,
so an empty store or an empty simulator dropped them. A separation that appears
only alongside data teaches the reader it is a property of the data rather than
of the page.

**Fix:** both notes moved into the empty messages as well.

### Additional findings

* **Dead branch in `_unavailable_state`.** A defensive `if
  benchmark.unsupported_reason` could never be taken: `MarketUnavailable` refuses
  a benchmark with no provider at construction. Removed, and replaced with a test
  asserting the engine's invariant.
* **Unreachable route branch.** `if path == ""` in `resolve_route` was dead —
  `"".rstrip("/") or "/"` already yields `/`. Removed.
* **`serve()` was dead code duplicating the CLI's loop.** The CLI now calls it,
  so there is one place that knows how the dashboard starts and stops.
* **Inline styles in `render.py`.** Two colour decisions had leaked out of the
  theme. An architecture guard now forbids `style="` in `render.py` entirely.

### Attacks that found nothing

Every market source unavailable · one section crashing operationally · a
programming bug (correctly propagates) · no trades · 200 symbols (no truncation)
· huge `Decimal` values (no scientific notation) · 5,000-character warnings and
evidence · stale snapshots (marked behind schedule with age) · future timestamps
(negative age rendered as negative) · paper and live on the same symbol · DXY
dark · XAU dark · FRED delayed · mixed timezones · repeated manual refresh ·
simultaneous browser refreshes · dashboard closed and reopened · malformed and
traversal routes · unknown symbol detail · a provider error during a user refresh
(the held snapshot survives intact).

---

## 15. Live demonstration

Launched against **real** market data on 2026-08-24.

```
$ uv run fmits dashboard
FMITS Operator Dashboard — read only
  open   http://127.0.0.1:8787/
  stop   Ctrl-C
  This surface reads. It places no order, records no trade and changes no stored value.
```

**Verified on the live page — 19 / 19 checks:**

| Check | Result |
|---|---|
| Crypto: BTC, ETH, SOL, BNB, XRP, DOGE with moves, volatility, age, source | live from `binance-spot` |
| SPX — S&P 500 at 7,674.37 index points | live from `fred` |
| USDBROAD — Fed nominal broad dollar index at 118.9028 | live from `fred` |
| US2Y at 4.19 % p.a., moves in **basis points** (+0.0 / +4.0 / −12.0 bp) | live from `fred` |
| US10Y at 4.69 % p.a., moves in **basis points** (+4.0 / +6.0 / +2.0 bp) | live from `fred` |
| VIX at 15.13 volatility points | live from `fred` |
| DXY — **unsupported**, with the licensing reason stated in full | shown, not hidden |
| XAU — **unsupported**, with the discontinued-series reason stated in full | shown, not hidden |
| Swing: 20 scanned, 0 confirmed, 0 candidates, 20 waiting, 0 unreadable | real scan |
| No-trade groups with verbatim engine reasons | real |
| Ordering rule printed verbatim | yes |
| Portfolio: no store present — *"Nothing failed"* | correct |
| Performance: no closed trade — *"Nothing failed"* | correct |
| Data health: 17 available, 0 behind schedule, 4 unsupported, 1 absent | per-source, no score |
| Both instants in the header on every page | yes |
| `POST` / `PUT` / `PATCH` / `DELETE` / `OPTIONS` | all `405` |
| `/nope`, `/etc/passwd`, `/swing/a%2Fb`, `/../../etc/passwd` | all `404` |
| Store fingerprint before and after browsing | **unchanged — store never created** |
| One refresh serves seven pages | 45.45 s then 0.00 s × 6 |

An excerpt of the live Overview page, rendered to text:

```
FMITS Operator Dashboard   read only · v0
last refresh 2026-08-24 19:24Z   data as of 2026-08-24 19:24Z   schema 1

Swing   as of 2026-08-24 12:00Z · fmis.swing_workspace · one scan, one store read
  Scanned 20 | Confirmed 0 | Candidates 0 | Waiting 20 | Unreadable 0
  No confirmed or candidate setup on this refresh. A quiet market is a
  legitimate result.

Global market pulse   as of 2026-08-24 19:24Z · fmis.market_pulse · default
  BTC   crypto  available  +0.21%  +2.05%  +22.50%  0.0066  1h 24m  binance-spot
  ETH   crypto  available  +0.20%  +1.03%  +29.52%  0.0094  1h 24m  binance-spot
  ...
  SPX        equity_index      available  +0.43%  -1.43%  +3.59%   3d 19h  fred
  USDBROAD   currency          available  -0.24%  -0.14%  -1.19%  10d 19h  fred
  US2Y       rates             available  unavailable¹ ...          4d 19h  fred
  VIX        volatility_index  available  -5.50%  +6.18% -19.09%   3d 19h  fred

  ¹ this market is a rate, not a price: a percentage return of a yield is the
    ratio between two rates rather than the move a reader means, so it is not
    computed here. `fmits macro` states this market's move in basis points

  DXY  currency   unsupported  no source configured in this build publishes the
                               ICE US Dollar Index; it is a licensed index ...
  XAU  commodity  unsupported  no source configured in this build publishes a
                               spot gold price; the LBMA gold benchmark ...
```

### Screenshot

**Not captured.** The Chrome browser-automation extension is not connected in
this environment, and the repository holds no screenshot tooling. Per the brief,
no browser-automation dependency was added merely for a screenshot, and the
owner's own live launch is the stronger verification. The text rendering above
is provided in its place. The dashboard itself is fully verified.

---

## 16. Launch, URL and stop

```
Launch:  uv run fmits dashboard
URL:     http://127.0.0.1:8787/
Stop:    Ctrl-C
```

Useful variants:

```
uv run fmits dashboard --port 9000            # a different port
uv run fmits dashboard --port 0               # let the OS choose (URL is printed)
uv run fmits dashboard BTCUSDT ETHUSDT        # a smaller watchlist, faster refresh
uv run fmits dashboard --no-relationships     # skip the macro cross-asset request
uv run fmits dashboard --store-root PATH      # read a different store (still read-only)
```

**Stop semantics, verified.** `Ctrl-C` (SIGINT) exits with code `0` and prints
`fmits dashboard: stopped`; the socket is shut down and closed in a `finally`
block, and the port is released. A backgrounded instance is stopped with
`kill <pid>` (SIGTERM), also verified to release the port.

*(An initial test appeared to show SIGINT being ignored. That was the shell's
standard `SIG_IGN` inheritance for background jobs, not a defect — retested with
proper signal delivery, the process exits cleanly with code 0.)*

---

## 17. Known limitations

1. **A full refresh takes 30–45 seconds** against the default 20-symbol
   watchlist, because it performs a real 20-symbol scan plus pulse plus macro
   plus statistics. The first page load pays this; the other six are instant.
   Passing a shorter watchlist reduces it.
2. **Not live.** The page shows what one refresh read and does not stream or
   poll. This is stated on every page.
3. **No periodic refresh.** V0 is manual only, deliberately: an automatic
   refresh that silently replaced figures under the owner's cursor is a worse
   default than an explicit one.
4. **Three sections share one read.** A workspace failure costs swing, portfolio
   and paper together. The alternative — a second store read — would put two
   instants on one page.
5. **One chart.** Only the equity curve is charted. Sparklines for market moves
   were not added because the pulse retains no intra-window series to draw
   truthfully from.
6. **Single user, no authentication.** Loopback binding is the access control.
   `--allow-public` exists but is refused by default and should stay unused.
7. **No filtering or sorting controls.** The seam exists (query parameters) but
   V0 ships none.
8. **The visual design is provisional.** It is functional, not final.

---

## 18. Future redesign boundary

The redesign seam is **`render.py` + `theme.py`**. Both may be deleted and
replaced without touching `models.py`, `sections.py` or `compose.py`, and
therefore without touching any engine.

Enforced by guards:

* the contract layer imports neither `html` nor `urllib`, and imports no
  presentation module;
* the contract layer holds no markup and no colour literal;
* `render.py` holds no `style="`, no `color:`, no `background:`, no
  `font-family`, no `font-size:` — every appearance decision is in `theme.py`;
* `render.py` emits semantic class names (`state-unavailable`, `absent`, `pos`)
  that say what a value **is**, never what it should look like.

A JSON API for a JavaScript frontend would be a new module at the same seam,
serializing `OperatorDashboardSnapshot`. Nothing beneath would change.

---

## 19. Changed-file scope

### New — production (7 files, `src/fmis/operator_dashboard/`)

| File | Lines | Role |
|---|---:|---|
| `__init__.py` | 165 | package docstring and exports |
| `models.py` | 704 | the presentation contract |
| `sections.py` | 827 | engine output → read model |
| `compose.py` | 436 | composition root; four reads; isolation |
| `render.py` | 1,461 | read models → HTML |
| `theme.py` | 405 | every appearance decision |
| `server.py` | 325 | stdlib server, GET/HEAD only |
| **Total** | **4,323** | |

### Modified — production (1 file)

* `src/fmis/pipeline/cli.py` — one import, `_configure_dashboard`,
  `_run_dashboard`, `DASHBOARD_COMMAND`, and one registry entry placed between
  `trades` and `archive`. **No existing command, flag or behaviour changed.**

### New — tests (11 files)

`tests/operator_dashboard_helpers.py` and the ten test modules listed in §12 —
4,003 lines, 847 tests.

### Modified — tests (6 files, registry rosters only)

| File | Change |
|---|---|
| `test_pipeline_cli.py` | `EXPECTED_COMMANDS` gains `"dashboard"` |
| `test_multi_timeframe.py` | exact roster gains `"dashboard"` |
| `test_pipeline_regime.py` | declared order gains `"dashboard"` before `"archive"` |
| `test_workspace_render.py` | declared order gains `"dashboard"` before `"archive"` |
| `test_market_pulse_architecture.py` | post-BT additions become `{"pulse", "macro", "dashboard"}` |
| `test_trade_capture_architecture.py` | CLI permitted-import prefixes gain `fmis.operator_dashboard`, on the footing BS established for `fmis.swing_workspace` |

Each modification is a roster widening for an additive command, with the reason
recorded in a comment beside it. **No existing assertion was weakened or
deleted.** `archive` remains the last registered command, which three guards pin.

### Documentation (4 files + this report)

`reports/0032_...md` (new), `reports/README.md`, `docs/AI_HANDOFF/CURRENT_STATE.md`,
`FMITS_PRODUCT_BACKLOG.md`, `FMITS_PRODUCT_CHANGELOG.md`.

### Untouched

`pyproject.toml`, `uv.lock`, and the 16 pre-existing research documents.

---

## 20. Commits

**Commit A — `0f31293`**

```
feat(dashboard): add read-only FMITS Operator Dashboard V0
```

`src/fmis/operator_dashboard/` (7 files), `src/fmis/pipeline/cli.py`, the 11 new
test files, and the 6 registry-roster test updates. 25 files, +8,505 / −6.

Verified after the commit existed: the package and each of its seven modules
import in fresh interpreters; the CLI registers 24 commands with `dashboard`
present and `archive` still last; the focused BV suite passes 847; the six
widened registry guards pass 285.

**Commit B**

```
docs(product): record Operator Dashboard V0 milestone
```

`reports/0032_...md`, `reports/README.md`, `docs/AI_HANDOFF/CURRENT_STATE.md`,
`FMITS_PRODUCT_BACKLOG.md`, `FMITS_PRODUCT_CHANGELOG.md`.

Both are plain commits on `main` on top of `1a73cf8`. No amend, no squash, no
rebase, no tag.

---

## 21. Verdict

Milestone BV is complete on the standard the brief set: **"What can the owner do
himself after this milestone?"**

He can run one command, open one URL, and see FMITS — market pulse, macro
context, swing decisions in their own order, portfolio, paper trades,
performance with a real equity curve, and the honest state of every data source —
without reading a CLI report, and without the dashboard having computed a single
financial figure of its own.

The window is built. The engines behind it do not know it exists, and the window
can be replaced tomorrow without them noticing.
