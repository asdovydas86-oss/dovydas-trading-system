# Dashboard Startup Regression — Diagnosis, Repair and Startup Smoke Test

| Field | Value |
|---|---|
| **Report number** | 0041 |
| **Title** | Dashboard Startup Regression — Diagnosis, Repair and Startup Smoke Test |
| **Date** | 2026-09-04 |
| **Report type** | Implementation (product reliability) |
| **Model** | Claude Opus 5 (1M context) |
| **Repository branch** | `main` |
| **Audited commit** | `1a133b10283cea4f8fbb0713e81b84db53ab7f98` |
| **Status** | Complete |
| **Scope** | Restore the existing dashboard and prove it. **Not** EP-21, not a redesign, not a refresh-UX epic. |

---

## 1. The finding, stated first

**The dashboard was never dead. It was unopenable.**

`fmits dashboard` bound its socket, printed a URL, and served a correct page —
in 37.9 s. The first request performed all four live engine reads *before the
first byte of HTTP was written*. A browser given an accepted connection that
receives no status line, no header and no byte for that long does not show a
loading page; at its resource timeout it reports the server as having stopped
responding. The command started and the dashboard never opened.

That is failure mode **B** of the six the brief enumerated — *starts but the
first request never completes in time* — and it is intermittent by construction,
because whether it crosses a browser's timeout depends on how slow Binance and
FRED are on the day.

## 2. Baseline verified before anything was touched

| Check | Value |
|---|---|
| `HEAD` | `1a133b10283cea4f8fbb0713e81b84db53ab7f98` |
| local `main` | same |
| `origin/main` | same |
| `git ls-remote origin main` | same |
| ahead / behind | `0 / 0` |
| staged / unstaged | none |
| untracked | the 16 pre-existing research documents, unchanged |
| stash | empty |
| merge / rebase / cherry-pick / bisect | none in progress |

## 3. Reconstructed startup path

| Question | Answer, from code |
|---|---|
| Entrypoint | `fmis.pipeline.cli:main` → `DASHBOARD_COMMAND` → `_run_dashboard` (`src/fmis/pipeline/cli.py:3428`) |
| Console script | `fmits = "fmis.pipeline.cli:main"` (`pyproject.toml`); also `python -m fmis.pipeline` |
| Framework | None. `http.server.ThreadingHTTPServer`, standard library only — `dependencies = []`, and a guard forbids `flask`/`django`/`fastapi`/`pandas`/`numpy` |
| Host / port | `127.0.0.1:8787`; off-loopback refused without `--allow-public` |
| Routes | 10, from `render.PAGES`: `/`, `/markets`, `/swing`, `/portfolio`, `/paper`, `/performance`, `/lab`, `/geometry`, `/validation`, `/system`, plus the dynamic `/swing/<SYMBOL>` |
| Static assets | None. The stylesheet is inlined; no path is ever joined to a filesystem root |
| Data sources | Four reads named in `compose.REFRESH_READS`: `run_swing_workspace`, `run_market_pulse`, `run_macro_context`, `report_for_store` |
| Config | None required. `--store-root` defaults to `~/.fmits/store`; a missing store is a stated section, not a failure |
| Environment | Editable install in `.venv`; `fmis` resolves to `src/fmis`, not to the stale `build/lib` copy |

Documentation is thin and was **not** the problem: `README.md` never mentions
the dashboard, and `docs/AI_HANDOFF/CURRENT_STATE.md` names the command once.
The startup path above was reconstructed from code and confirmed by running it.

## 4. Reproduction

| Path | Result |
|---|---|
| `.venv/bin/fmits dashboard --help` | exit 0 |
| `.venv/bin/fmits dashboard` | binds `127.0.0.1:8787`, banner printed, empty stderr |
| `curl http://127.0.0.1:8787/` | **200**, 24,910 bytes, **37.9 s** |
| every other route, after the first | 200, ~0.5 ms |
| `uv run fmits dashboard` | identical |
| second instance on a bound port | `OSError: [Errno 48] Address already in use`, exit 1 |
| dashboard suites at baseline | 72 passed under `-W error` |

The page was real, not an empty 200: live Binance bars for six crypto
benchmarks, live FRED SPX / USDBROAD / US2Y / US10Y / VIX, a 20-symbol scan, and
four warning rows. **Nothing was broken. Everything was late.**

The owner confirmed the observed symptom independently: *browser spins, then
errors.*

## 5. Root cause

`SnapshotHolder.current()` refreshed lazily, on the first request, holding its
lock for the whole of the read; and `serve()` announced the URL immediately
after binding, before any of it had happened. The two together put a 30–45 s
silent wait inside the operator's first page load.

This was **deliberate and documented**, which is why no reviewer caught it. The
`_run_dashboard` docstring said so in as many words:

> *The first refresh happens on the first request, not here. Starting the server
> does not fetch, so the command comes up immediately and the owner sees the
> page assemble rather than watching a silent terminal.*

The reasoning is sound except for its central assumption. The owner does not see
the page assemble. Server-side HTML is written once, complete; there is no
progressive render to watch. The choice traded a silent terminal for a silent
socket, and a browser interprets a silent socket as a dead server.

**This is a dormant defect present since `0f31293` (Milestone BV, 2026-08-24),
not a recent regression.** No commit broke it. It became visible as refresh cost
grew: `git log` shows no change to `src/fmis/operator_dashboard/` since
`fd1270b` (2026-08-26), and the backlog has recorded the 30–45 s block since BV,
through CA and CC, without ever connecting it to the dashboard failing to open.

## 6. Why 14,049 tests missed it

Every piece was covered. The sequence was not.

| Suite | What it does | Why it could not see this |
|---|---|---|
| `test_operator_dashboard_server.py` | Binds a **real** socket, serves on a thread, makes **real** HTTP requests over all routes | Uses `build_server` with a stub refresher (`_Counter`) that returns instantly. Never runs `_run_dashboard`; never pays a refresh |
| `test_pipeline_cli_dashboard.py` | 8 tests: registration, flag parsing, help text, refused bind, busy port, holder arguments | **None of them serve.** `main(["dashboard"])` is never run to the point of answering a request |
| `test_operator_dashboard_compose.py` | Four reads, isolation, call counts | In-process; no socket, no HTTP, no clock |

Nothing crossed the CLI → `serve` → `compose` → HTTP → *browser-shaped client*
seam in one piece. A dashboard that starts and never answers was, to the suite,
indistinguishable from a healthy one. **Classified: product testing gap.**

## 7. The repair

Two files, one behavioural change: **the first refresh is paid before the URL is
announced, not inside the first request.**

### `src/fmis/operator_dashboard/server.py`

`serve()` gains `warm: bool = False` and `preparing: Callable[[str], None] |
None = None`. When warming, it calls `preparing(url)` after the bind, performs
one refresh through the holder it built, and only then calls `announce`.

`warm` defaults to `False` on purpose: `serve` is the mechanism, and the
decision that an operator's dashboard is not ready until it can answer belongs
to the command the operator runs. Every existing caller and every existing test
keeps its behaviour unchanged.

A warming refresh that raises is **not** swallowed. `compose.refresh` already
absorbs every *source did not answer* family into a section that says so, so
anything still escaping it is a defect — and a defect is worth reporting at
startup rather than burying in a handler thread, where it reaches the owner as a
page that never loads. The listener is closed on that path (`shutdown()` waits
on an event only `serve_forever` sets, so it cannot be used for cleanup on a
server that never served).

### `src/fmis/pipeline/cli.py`

`_run_dashboard` passes `warm=True` and a `preparing` callback. The banner is
now printed in two parts, and the words are chosen to be load-bearing:

```
FMITS Operator Dashboard — read only
  address  http://127.0.0.1:8787/
  reading  the first refresh performs four live engine reads and takes 30-45 s.
           The address answers when this finishes.
  open     http://127.0.0.1:8787/            ← printed only when it can answer
  stop     Ctrl-C
```

The terminal is never silent, and the URL is never offered before a request to
it can be served.

### What the repair is not

No redesign, no UI change, no new dashboard feature, no second dashboard, no
architecture boundary crossed, no hard-coded path, no guard weakened, no error
hidden to make a 200 appear. EP-21 is untouched.

## 8. The startup smoke test

`tests/test_operator_dashboard_startup_smoke.py` (6 tests) with
`tests/dashboard_smoke_driver.py`.

A **subprocess** runs the driver, which calls `fmis.pipeline.cli.main` with the
operator's argument vector. The process, argument parsing, runner, warming
refresh, `serve`, bound socket, HTTP handler, composition root, every `sections`
mapping, the renderer and the interrupt are production code and real.

**Only the three networked reads are replaced**, through `SnapshotHolder`'s own
documented `refresher` seam, by binding `compose.refresh`'s injected runner
arguments to the fixtures the rest of the dashboard suite already uses — real
`SwingWorkspace`, `MarketPulse` and `MacroContextReport` values, not stubs. The
fourth read, `report_for_store`, is left alone: it reads a `tmp_path` store and
touches no network. Total runtime: **4.8 s**, fully offline.

| Requirement | How it is proved |
|---|---|
| Application starts | `--port 0` subprocess prints its bound address |
| Startup does not crash | process alive, exit code checked |
| Service becomes ready | the `open` line is the readiness signal — it exists *because* of the repair |
| Main route responds | real `HTTPConnection` GET → 200 |
| Recognisably the FMITS dashboard | `<title>FMITS · Overview</title>`, `FMITS Operator Dashboard`, a link to every route in `PAGES`, `Global market pulse`, a benchmark that only an engine read could have produced, > 4,000 bytes |
| Every declared route answers | `ROUTES` derived from the production `PAGES`, so a new page is smoke-tested the day it lands |
| Shuts down cleanly | real `SIGINT`, exit code `0`, `fmits dashboard: stopped` on stderr |
| No live provider needed for the shell | asserted; if that ever changes, these tests hang against Binance and FRED instead of passing quietly |

### Non-vacuity, demonstrated rather than claimed

Three break modes, and the suite asserts it can tell each from a healthy build:

* `--break startup` — the first refresh raises. The dashboard must **not**
  announce readiness and must exit non-zero.
* `--break route` — every path resolves to nothing. The process still starts and
  still announces a URL, which is exactly the trap a startup-only check falls
  into; the assertion on the *response* catches it.
* `--break slow` — the refresh costs 3 s of real time. Offline, an instant
  fixture refresh makes the *ordering* invisible, which would leave the
  assertion about the repair a passing test that measures nothing. With a
  refresh that costs something, the two orderings are told apart by which side
  waits: the announcement, or the browser.

**Proof, run rather than asserted:** the repair was temporarily reverted
(`warm=True` → `warm=False`) and the suite re-run. **3 of 6 tests failed**,
including the one that tests the repair directly. The repair was then restored
and all 6 pass.

Four `serve()`-level tests and two CLI-wiring tests were added beside it, so a
refactor that drops `warm=True` is caught by the fast suite in milliseconds as
well as by the slow one.

## 9. Verification with the real command and live data

```
$ .venv/bin/fmits dashboard
FMITS Operator Dashboard — read only
  address  http://127.0.0.1:8787/
  reading  the first refresh performs four live engine reads and takes 30-45 s. …
  open     http://127.0.0.1:8787/          ← 23.8 s later
  stop     Ctrl-C
```

**URL: `http://127.0.0.1:8787/`.** Every route, measured after the announcement:

| Route | Status | Bytes | Time |
|---|---|---|---|
| `/` | 200 | 24,910 | 1.7 ms |
| `/markets` | 200 | 29,906 | 1.4 ms |
| `/swing` | 200 | 13,734 | 0.7 ms |
| `/portfolio` | 200 | 10,912 | 0.5 ms |
| `/paper` | 200 | 10,823 | 0.5 ms |
| `/performance` | 200 | 10,780 | 0.4 ms |
| `/lab` | 200 | 10,822 | 0.4 ms |
| `/geometry` | 200 | 10,893 | 0.4 ms |
| `/validation` | 200 | 10,862 | 0.5 ms |
| `/system` | 200 | 24,361 | 0.5 ms |
| `/swing/BTCUSDT` | 200 | 10,798 | 0.4 ms |

**37.9 s → 1.7 ms** for the operator's first page load. The wait did not
disappear; it moved to the terminal, where it is visible, explained, and does
not look like a broken server.

### What the data actually is

| Surface | Data | Provenance |
|---|---|---|
| Markets / pulse | **Live** — six crypto benchmarks from `binance-spot`, five macro series from `fred` | Real reads, ages stated per source |
| Swing | **Live** — 20 symbols scanned, 0 confirmed, 20 waiting, with a stated reason per symbol | `fmis.swing_workspace` |
| Portfolio, Paper, Performance | **Unavailable, and says so** — no durable store at `~/.fmits/store` | Correct behaviour, not a failure |
| Swing Lab / Trade Geometry / Validation | **Empty by design** — no artifact passed; each states the command that produces one | Correct behaviour |
| Data health | 17 available · 4 unsupported · 1 absent · 0 unavailable · 0 behind schedule | Real |

`DXY` and `XAU` report *unsupported* with a substantive reason rather than
substituting a different series wearing the same name. `US2Y` / `US10Y` decline
to state a percentage return of a yield. Both are correct and neither is a bug.

## 10. Regression suite

| Run | Result |
|---|---|
| `test_operator_dashboard_server.py` | **68 passed** (64 before; +4) |
| `test_pipeline_cli_dashboard.py` | **10 passed** (8 before; +2) |
| `test_operator_dashboard_startup_smoke.py` | **6 passed**, 4.8 s, fully offline |
| Dashboard + CLI + smoke together | **84 passed** |
| Architecture / import guards (`test_operator_dashboard_architecture.py`, `test_architecture_tiers.py`) | **503 passed** |
| **Full repository suite under `-W error`** | **14,061 passed**, 0 failed, exit 0, 10 m 55 s |

Baseline before this task: **14,049**. Net **+12** — 6 startup smoke, 4 `serve()`-level,
2 CLI-wiring. **No test was deleted, skipped, weakened or marked expected-to-fail**, and no guard was
widened. The full run was performed against the frozen tree that is being committed; two earlier runs
were discarded because edits landed while they were in flight.

## 11. Product-state assessment — READ ONLY

Recorded for the later dashboard refresh. **Nothing here was implemented.**

### A. Broken

**None.** Every route answers, every section renders, every figure carries its
instant, source and — where absent — its reason. The outage was the startup
path, and it is repaired.

### B. Stale

1. **The 30–45 s refresh is now honest but not fast.** Four sequential live
   reads; nothing is fetched concurrently, nothing is cached between runs.
   Restarting the dashboard pays the full cost again.
2. **`/lab`, `/geometry`, `/validation` require a CLI flag at startup.** Three of
   ten routes are empty unless the operator remembered to pass an artifact path
   when starting the server. Loading one means restarting the dashboard.
3. **The header states one instant for four reads taken seconds apart.** Honest
   at the section level (each carries its own `as_of`), approximate at the
   header level.
4. **`README.md` does not mention the dashboard at all**, and
   `docs/AI_HANDOFF/CURRENT_STATE.md` names the command once. The product's only
   visual surface is effectively undocumented, and `fmits` is not on the
   operator's `PATH` without activating `.venv`.

### C. Backend capability with no representation on the page

Substantial, and the largest category. The dashboard was built at BV and five
milestones of engine work have landed since without a surface:

* **Milestones BW–CD research output** — `fmits research persistence`,
  `admission`, `design`, `universe` and `dependence` all produce artifacts, and
  only `swing`, `geometry` and `validation` have pages.
* **Evidence detail** — the swing page states *why not* per symbol but does not
  show the evidence families, their agreement, or the conflict that produced the
  conclusion.
* **Multi-timeframe roles** — the page shows one analysis instant per symbol and
  states, in its own limitations, that it cannot show per-role freshness. The
  L-NO-FRESHNESS warning measured the context role at **8d 16h** older than the
  execution bar.
* **Backtest / expectancy / equity** — `fmits backtest`, `expectancy`, `equity`
  and `trades` have no dashboard representation beyond the aggregate
  Performance panel.
* **Macro rate facts and cross-asset relationships** — computed on every refresh
  (`with_relationships=True` by default) and only partly surfaced.
* **Archive** — `fmits archive` has no page.

### D. UX debt

1. **No refresh progress, per-source outcome, freshness or what-changed** —
   this is EP-21, and it remains entirely undone. The repair makes the *first*
   wait visible in the terminal; `?refresh=1` from the browser still blocks
   silently for 30–45 s. **That is the next real dashboard problem.**
2. **No `favicon.ico` route** — every browser requests it and gets a 404.
3. **Ten routes in a flat nav bar**, three of which are usually empty.
4. **No keyboard or deep-link affordance** to a symbol beyond typing
   `/swing/<SYMBOL>`.
5. **No auto-refresh, and correctly so** — but no indication of page age either
   beyond the printed instant.

### E. Not implemented anywhere

Alerts and notifications; any write path (approve, record, activate) — currently
forbidden by four architecture guards and a deliberate product boundary;
position sizing, which remains the owner's own work by AR-2; charts of any kind;
export.

## 12. Files changed

| File | Change |
|---|---|
| `src/fmis/operator_dashboard/server.py` | `serve()` gains `warm` and `preparing`; refresh before announce; listener closed if warming fails; module docstring corrected |
| `src/fmis/pipeline/cli.py` | `_run_dashboard` passes `warm=True` and `preparing`; two-part banner; docstring corrected to record the outage it caused |
| `tests/test_operator_dashboard_startup_smoke.py` | **New** — 6 tests |
| `tests/dashboard_smoke_driver.py` | **New** — the subprocess driver, with three break modes |
| `tests/test_operator_dashboard_server.py` | +4 tests on warming at the `serve()` level |
| `tests/test_pipeline_cli_dashboard.py` | +2 tests on the CLI wiring and banner order |

## 13. Recommended next task

**EP-21 — Operator Dashboard refresh UX.** It is now the single largest gap
between what FMITS knows and what the owner can see, and this repair sharpened
rather than solved it: the *startup* wait is explained in the terminal, but
`?refresh=1` from the browser still blocks for 30–45 s with no progress, no
per-source outcome and no way to distinguish a slow refresh from a
partially-failed one. Section C above should be scoped into it or split from it
deliberately — the refresh UX and the five milestones of unrepresented backend
capability are different problems, and merging them is how a refresh becomes a
rewrite.
