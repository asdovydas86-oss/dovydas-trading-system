| Field | Value |
|---|---|
| **Report number** | 0045 |
| **Title** | Dashboard Shutdown Reliability Gate — the two order-dependent smoke failures |
| **Date** | 2026-09-06 |
| **Report type** | Investigation and repair (engineering reliability) |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | `71a92e3` (baseline) |
| **Status** | Final |

---

# Dashboard Shutdown Reliability Gate

## 1. What this closes

Report 0044 §16.1 left two failing tests and a hypothesis:

```
FAILED tests/test_operator_dashboard_startup_smoke.py::test_the_operators_command_starts_serves_the_dashboard_and_stops
FAILED tests/test_operator_dashboard_startup_smoke.py::test_a_dashboard_whose_main_route_is_broken_is_caught
```

Both timed out in `_Dashboard.interrupt()`: after `SIGINT`, the dashboard subprocess did not exit
inside the 30 s `EXIT_TIMEOUT`. They were believed to be **order-dependent** — passing alone,
failing "after roughly 4,650 other tests" — and a very high `RLIMIT_NOFILE` was recorded as a
suspected factor.

**Neither was true.** The suite's ordering is not involved, no test leaks state, no descriptor
leaks, no thread or child process survives, and `RLIMIT_NOFILE` is irrelevant. The dashboard's
shutdown path was never at fault and has not been changed.

**The two tests failed whenever the pytest process itself had `SIGINT` set to `SIG_IGN`** — which
is what a shell without job control gives any background job, and therefore what every run long
enough to be backgrounded had. An *ignored* signal disposition is inherited **across `exec`**, so
the dashboard child could not receive `SIGINT` at all. The tests were measuring how the suite had
been launched.

## 2. Baseline gate

| | |
|---|---|
| `HEAD` / local `main` / `origin/main` / `git ls-remote origin main` | `71a92e397d7304310c97f00b9ca975c49f95edef` — all four identical |
| ahead / behind | `0 / 0` |
| tracked tree | clean |
| untracked | exactly the 16 pre-existing research documents |
| stash | empty |
| active git operation | none |
| operator dashboard | PID **74079**, listening on `127.0.0.1:8787`, found with `lsof -nP -iTCP:8787 -sTCP:LISTEN` |
| shell `ulimit -n` / process `RLIMIT_NOFILE` | `1048576` / `(1048576, ∞)` |
| collected | 14,531 tests · pytest 9.1.1 · CPython 3.12.13 · **no pytest plugins installed** |

The operator's dashboard was never stopped and never signalled. `pkill` was not used at any point.
All work ran on ephemeral ports (`--port 0`) or on port 8799, with isolated scan-history roots.

## 3. The path that was read before anything was changed

```
test  →  subprocess.Popen(driver)  →  dashboard_smoke_driver.main
      →  fmis.pipeline.cli.main(["dashboard", …])  →  _run_dashboard
      →  serve()  →  build_server()  →  bind
                  →  holder.current()          (the warming refresh)
                  →  announce("open <url>")
                  →  server.serve_forever()    (selectors.PollSelector, 0.5 s poll)
      ← SIGINT → KeyboardInterrupt → except: pass
                  → finally: server.shutdown(); server.server_close()
      →  _run_dashboard prints "stopped", returns 0
```

`DashboardServer` sets `daemon_threads = True`, so `ThreadingMixIn.server_close()` joins nothing and
no handler thread can hold the interpreter open. `serve_forever`'s own `finally` sets the shut-down
event before `shutdown()` waits on it, so `shutdown()` after a `KeyboardInterrupt` cannot block.
Nothing on this path is capable of the observed hang, which is the first evidence that the signal
never arrived.

## 4. Baseline reproduction, and the confound in the original one

Every run below is on `71a92e3`, unmodified, under `-W error`.

| # | Scenario | Parent `SIGINT` | Result |
|---|---|---|---|
| A | `tests/test_operator_dashboard_startup_smoke.py` alone | default | **7 passed in 5.26 s** |
| B | 67-file prefix — every test file collected up to and including the smoke file, 4,660 tests | default | **4,660 passed in 30.39 s** |
| C | B, repeated ×3 | default | **4,660 passed** each time (30.5 s, 30.6 s, 31.7 s) |
| D | Whole `tests/` collected (all 284 modules), only the two named tests run | default | **2 passed in 1.7–1.9 s**, ×4 |
| E | Full suite | default | ran past index 4654 clean (0 failures at 82 %) |
| F | Full suite | `SIG_IGN` | **2 failed, 14,529 passed in 772.49 s** |
| G | 67-file prefix (identical command to B) | `SIG_IGN` | **2 failed, 4,658 passed in 90.62 s** |
| H | Smoke file alone — 7 tests, no prefix at all | `SIG_IGN` | **2 failed, 5 passed in 65.85 s** |

Row F reproduces report 0044's headline figure (`14,529 passed, 2 failed`) exactly. Row G
reproduces its prefix experiment to within 0.03 s of the reported `90.65 s`. Row H is the one that
settles it: **the same two tests, and only those two, fail with no preceding tests at all.**

The prior session's "it needs ~4,650 preceding tests" was an artifact of which runs were
backgrounded. Only long runs are backgrounded, and backgrounding is what set `SIG_IGN` — so the
short isolated runs passed and the long ones failed, and the difference looked like ordering.

The failing pair is not arbitrary: `interrupt()` is called by **exactly** those two tests. The other
five make the same HTTP requests and let the fixture's `kill()` (`SIGKILL`) end the process, which
no disposition can ignore.

## 5. Historical reproduction on `77b956d`

A clean `git worktree` at `77b956d`, run against **its own** `src` (`PYTHONPATH` set to the
worktree — without it the venv's editable install silently resolves `fmis` to `HEAD`, which is a
trap worth recording):

| Scenario | Parent `SIGINT` | Result |
|---|---|---|
| Smoke file alone at `77b956d` | default | **6 passed in 5.20 s** |
| Smoke file alone at `77b956d` | `SIG_IGN` | **2 failed, 4 passed in 64.91 s** — the same two |

So report 0044's conclusion that the defect predates Slice 3 is **correct**, and its reasoning about
*why* is not: the axis is the launcher's signal disposition, not the commit and not the test count.
The worktree was read only and has been removed.

## 6. Root cause

**A signal disposition of `SIG_IGN` is inherited across `exec`, and `subprocess` does not restore
it.**

Three facts compose into the failure:

1. **A shell without job control starts a background job with `SIGINT` and `SIGQUIT` ignored.**
   Measured directly in this session's shell — a foreground child reports
   `<built-in function default_int_handler>`; the same child started with `&` reports `SIG_IGN`.
   This applies to `pytest &`, `nohup pytest &`, `sh -c '… &'`, and to most CI and agent runners.

2. **`SIG_IGN` survives `exec`; a handler does not.** POSIX resets *handled* signals to `SIG_DFL`
   across `exec` and leaves *ignored* ones ignored. `subprocess.Popen`'s `restore_signals=True` —
   on by default — does **not** cover this: it restores only the three signals CPython itself
   ignores (`SIGPIPE`, `SIGXFZ`, `SIGXFSZ`). Proved directly: from a parent with default `SIGINT`
   the child reports `default_int_handler`; from a parent with `SIG_IGN` the same child, same
   `Popen` call, reports `SIG_IGN`.

3. **CPython deliberately does not override an inherited `SIG_IGN`** when it installs its own
   `SIGINT` handler at startup. So the dashboard child ran with `SIGINT` ignored, and
   `os.kill(child, SIGINT)` was discarded by the kernel.

### 6.1 The hung child, observed

Captured live while the child sat past its timeout (`sample`, `ps -M`, `lsof`, `pgrep -P`):

```
ps      7739  S  0.0%cpu  — sleeping, not spinning
threads exactly 1                    — no worker thread, no non-daemon thread
pgrep -P 7739 →  (empty)             — no child process
lsof    9 rows: cwd, 2 mapped images, fd0 /dev/null, fd1+fd2 pipes,
                fd3 TCP 127.0.0.1:51380 (LISTEN), one unix socket
stack   … _PyEval_EvalFrameDefault → select_poll_poll → poll (libsystem_kernel)
```

That stack is `serve_forever`'s selector: **the process is exactly where a healthy serving dashboard
sits.** It is not stalled in `shutdown()`, not blocked on a lock, not draining a pipe, not closing a
socket, not waiting on a thread. It was never interrupted. A **second** `SIGINT` 60 s later changed
nothing; at 101 s it was still serving. `SIGKILL` from the fixture ended it, which is why the
failure was a timeout and never an orphan.

### 6.2 What the root cause has to explain, and does

| Observation | Explanation |
|---|---|
| Isolated runs passed | They were foreground. `SIGINT` was live and delivery worked. |
| Late-suite runs failed | They were backgrounded because they are long. `SIGINT` was ignored. |
| `SIGINT` exit "stalls" | It does not stall. The signal is discarded; the process serves on. |
| Reproduces across commits | Nothing in the repository is involved — it predates the smoke test itself. |
| Only these two tests | They are the only two that call `interrupt()`. |
| The `RLIMIT_NOFILE` clue | Coincidence. See §7. |
| The fix removes the mechanism | The child restores its own `SIGINT` handler, so the signal is delivered. |

## 7. `RLIMIT_NOFILE` and file descriptors — both excluded

The high-soft-limit hypothesis was tested in **both** directions rather than assumed away:

| `ulimit -n` | Parent `SIGINT` | Result |
|---|---|---|
| 4096 | `SIG_IGN` | **2 failed** — a low limit does not prevent it |
| 1,048,576 | default | **7 passed in 5.19 s** — a high limit does not cause it |

`RLIMIT_NOFILE` is not causal in either direction. The earlier observation that "it passed under
4096" is explained by the same confound as the ordering one: that run was in a foreground shell.

**File descriptors are likewise excluded, structurally rather than by counting.** The failure
reproduces on a **seven-test** run in which no accumulation can occur, and does not reproduce on a
**4,660-test** run in which any accumulation would be maximal. The measured counts agree: the hung
child held 9 descriptors and the parent 19 — a normal set for a bound listener plus two pipes, with
no growth, no leaked pipe, and no inherited descriptor keeping anything open.

`os.environ`, the working directory, logging handlers, `multiprocessing`, monkeypatch scope and
temp-directory lifecycle were all excluded by the same argument. A global-state audit found the
suite mutates none of the process-global knobs: `resource.setrlimit`, `signal.signal`, `os.chdir`
and `multiprocessing.set_start_method` appear **nowhere** in `tests/` or `src/`. The one occurrence
of `signal` was `send_signal(SIGINT)` in the smoke test itself.

## 8. The fix, and the layer that owns it

**Owner: the smoke test harness — specifically `tests/dashboard_smoke_driver.py`.**

The driver is what stands in for the operator's terminal session. A terminal always has Ctrl-C live;
the driver was inheriting whatever the launcher happened to hold. It now states the condition it is
supposed to be reproducing:

```python
def _enable_ctrl_c() -> None:
    signal.signal(signal.SIGINT, signal.default_int_handler)


if __name__ == "__main__":
    _enable_ctrl_c()
    raise SystemExit(main())
```

**Why in the child rather than `preexec_fn` in the parent.** `preexec_fn` runs between `fork` and
`exec` and is documented as unsafe in a process that has threads — and the smoke harness keeps one
pipe-draining thread per running dashboard, so it is precisely the process that must not use it.
Doing it in the child's own `__main__` has no fork-safety hazard at all.

**Why under `if __name__ == "__main__"` rather than in `main()`.** The smoke test imports
`SLOW_REFRESH_SECONDS` from this module. Guarding the call keeps the file incapable of changing the
signal state of the pytest process that imports it.

**Why production was deliberately not touched.** `fmits dashboard &` ignoring Ctrl-C is correct
POSIX behaviour for a background job. A command that overrode its caller's signal disposition would
be compensating in the product for how a test was started — the exact inversion this gate forbids.
No file under `src/` was modified: the diff is **156 added lines, 0 deletions, two test files.**

## 9. Tests added

Two, in `tests/test_operator_dashboard_startup_smoke.py`. 14,531 → **14,533** collected.

**`test_ctrl_c_stops_the_dashboard_even_when_the_session_that_started_it_ignores_it`** — the
root-cause reproducer. It sets this process's `SIGINT` to `SIG_IGN` inside a context manager that
restores it, starts a dashboard, serves a request, and presses Ctrl-C. It reproduces the exact
condition of the failure in five seconds instead of hiding until the next full run.

**`test_starting_and_stopping_repeatedly_is_prompt_and_leaves_nothing_behind`** — the operator's
contract, three cycles: start → ready → `GET` → Ctrl-C → exit 0 → **the port binds again**. Binding
is refused while a live listener holds an address, `SO_REUSEADDR` or not, so this catches a shutdown
that returned without closing the listener. `SHUTDOWN_BUDGET = 5.0 s` is asserted against a measured
cost of ~23 ms, and is six times tighter than `EXIT_TIMEOUT`.

Nothing was weakened: no timeout raised, no sleep added, no retry, no `xfail`, no `skip`, no
reordering, no `SIGKILL` accepted as normal shutdown. `test_a_dashboard_whose_main_route_is_broken_is_caught`
still asserts 404 on the main route and still requires a clean interrupt afterwards.

## 10. Non-vacuity

The fix was disabled (`_enable_ctrl_c()` commented out) and the file re-run:

| Condition | Pre-fix | Post-fix |
|---|---|---|
| **Ordinary foreground terminal** | **1 failed**, 8 passed in 36.34 s — the reproducer fails with the original `TimeoutExpired` | **9 passed in 6.33 s** |
| **`SIG_IGN` session** | **4 failed**, 5 passed in 125.91 s — both original tests *and* both new ones | **9 passed in 5.13 s** |

The reproducer is non-vacuous in a plain terminal, which is the point: the defect that hid for a
milestone now fails in any session, not only a backgrounded one.

## 11. Verification

### 11.1 The exact formerly-failing scenario

Full suite, `-W error`, launched from a `SIG_IGN` session — the condition under which report 0044
recorded `14,529 passed / 2 failed`:

```
14533 passed in 678.68s (0:11:18)
```

### 11.2 Full suite in a normal session

```
14533 passed in 708.78s (0:11:48)
```

### 11.3 Repeatability

The gate exists because a known flake must not be declared fixed from one lucky run. Every
scenario that ever failed was re-run, in the condition that made it fail:

| Scenario | Before | After |
|---|---|---|
| Full suite, `SIG_IGN` session | 2 failed, 14,529 passed (772.49 s) | **14,533 passed** (678.68 s) |
| 67-file prefix, `SIG_IGN` session | 2 failed, 4,658 passed (90.62 s) | **4,662 passed** (31.37 s), then **4,662 passed** (31.55 s) |
| Smoke file alone, `SIG_IGN` session ×4 | 2 failed, 5 passed (65.85 s) | **9 passed** ×4 (6.43, 6.94, 6.37, 6.30 s) |
| Smoke file alone, normal session ×4 | 7 passed | **9 passed** ×4 (6.40, 6.48, 6.52, 6.68 s) |

Eleven runs of the failing scenarios, zero failures. The 60 s that used to separate a passing
prefix run from a failing one — two `EXIT_TIMEOUT`s — is gone from the wall clock, which is its own
confirmation that nothing is waiting on a timeout any more.

### 11.4 Performance, before and after

Five cycles of the real startup path, offline (the driver's fixture refresh):

| Measure | Pre-fix | Post-fix |
|---|---|---|
| Bound address announced | 0.241 s | 0.239–0.247 s |
| Ready (`open` line) | 0.241 s | 0.239–0.247 s |
| First HTTP after ready | 0.7–1.4 ms | 0.7–1.5 ms |
| `SIGINT` → process exit | 0.0226 s | 0.0226–0.0403 s |

Unchanged, as expected — the fix alters one signal disposition and nothing on the serving path.

**The operator's real command**, `fmits dashboard --port 8799` with an isolated store and history
root, against live providers:

```
address line at 0.25s; ready (warm refresh done) at 37.82s
  GET /                200   26454 bytes in 0.0053s
  GET /swing           200   32998 bytes in 0.0027s
  GET /swing/BTCUSDT   200   39569 bytes in 0.0014s
  scan history files after 1 scan + 3 page loads: 1
Ctrl-C -> exit in 0.0838s, code 0
stderr: ['fmits dashboard: stopped']
port 8799 rebindable after exit: yes
```

The report 0041 repair is intact and measured: the address appears in 0.25 s, the URL is announced
only after the genuine 37.8 s warm refresh, and the first request after it costs **5.3 ms** — not the
37 s it would if the refresh were still paid inside the request. Ctrl-C returns the prompt in
**84 ms** with exit code 0 and no orphan.

### 11.5 Scan memory

Not implicated, and shown not to be: the failure reproduces identically on `77b956d`, where scan
memory does not exist. In the live run above the command recorded exactly one scan and the three
page loads recorded none, and the history root was the test's own throughout — the owner's
`~/.fmits/scan_memory` was never written by any run in this session.

### 11.6 Policy non-regression

`tests/test_swing_setup_policy_non_regression.py` — **4 passed**. That is the committed canonical
mechanism: 81 fixtures (27 seed triples × 3 symbols) through `setup_assessment_for_sheet`, each
assessment and each evidence report canonicalised as its complete recursive `repr()` and compared
against a per-fixture digest table captured before Slice 1. All 162 digests match, and the state
distribution is **72 `WAIT` / 9 `CANDIDATE`**, unchanged.

**A correction worth recording.** The aggregate figure quoted by reports 0042–0044 —
`sha256 096a575a015f1e0ed991a049033993b90350b36be6361458d07fbcc36b4a7a42` over "81 records" — is
**not reproducible from this repository**, because the formula that produced it was never committed.
Thirty-six plausible reconstructions (matrix and sorted order × three separators × six record
shapes) were tried and none matches. The per-fixture table in the test is strictly stronger than one
aggregate and it passes; so that this is checkable next time, here is a **reproducible** aggregate
with its formula stated:

```
sha256( b"".join(repr(setup_assessment_for_sheet(multi(seeds, symbol)))
                 for key, seeds, symbol in _matrix()) )
  = 8b22e6c9c5e346cb8f62008325b9b0304ecae9af5e0fe46eec4a6c5aa428059c
```

Independently, no file under `src/` was modified in this change, so no policy code could have moved.

### 11.7 Product surface

Checked against the **live operator instance on 8787** (PID 74079), read-only, without stopping or
signalling it:

```
history before:  2 scan records  (2026-09-05 09:13Z and 09:14Z)
  GET /                 -> 200   26162 bytes
  GET /swing            -> 200   34020 bytes
  GET /swing/BTCUSDT    -> 200   39574 bytes
history after:   2 scan records   ← three page loads recorded nothing
```

The Slice 3 surface is intact and comparing real scans:

> **Since the previous comparable scan** · Previous comparable scan 2026-09-05 09:13Z · This scan
> 2026-09-05 09:14Z · Changed **0** · No material change **20** — *No material Swing state change
> since the previous comparable scan.*

The two records predate this session by a day and survived the process restart that produced the
current PID, so restart continuity holds. The current decision remains authoritative: the change
block sits beneath it and states a comparison, never a recommendation.

### 11.8 Research boundary

Untouched. `CA = NO_EDGE`, `CB = UNDERPOWERED`, `CC = INFEASIBLE` and the `CD` dependence
conclusions are unaffected — this work changed two test-support files and no engine, threshold,
policy or study.

## 12. Self-review

| Question | Answer |
|---|---|
| Root cause, or added tolerance? | Root cause. The mechanism is proved in both directions and the fix removes it. |
| Any smoke test weakened? | No. Two assertions were **added**; none was relaxed. |
| Test ordering changed? | No. |
| Force-kill as normal shutdown? | No. The fixture's `kill()` remains the last-resort teardown it always was. |
| Orphan processes possible? | No — asserted by the new repeated-lifecycle test and verified live. |
| Sockets left bound? | No — the port is re-bound after every cycle as an assertion. |
| `stdout`/`stderr` deadlock possible? | No — the pump threads are unchanged and were never implicated. |
| Compensated in production for test isolation? | No. `src/` is untouched, deliberately. |
| Swing policy / scan memory / warm-up touched? | None of them. |
| The 16 research documents? | Untouched, still untracked. |
| New tests non-vacuous? | Proved in §10. |
| Does the exact old failing scenario pass? | §11.1. |

## 13. Standing recommendation

Long runs of this suite are launched in the background, and that is the condition under which
`SIGINT` is ignored. Two options keep future full runs honest:

- run the suite in the foreground, or
- launch it through a wrapper that resets `SIGINT` to `SIG_DFL` before `exec`.

Neither is required for correctness any more — the driver now enables Ctrl-C for itself, so the
suite is green either way — but the second is worth knowing about for any other test that ever
signals a child.
