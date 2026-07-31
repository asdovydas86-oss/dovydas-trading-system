# Level-Crossing Foundation v1 — Independent Review

**Reviewed:** `fmis.level_crossing` as merged into local `main` at
`2aad48071c2499abf48d26fe647a3f5ca4fc74d4` (*Merge Level-Crossing Foundation v1*).
**Method:** everything below was **re-derived from production source**. No design claim, test count,
ordering claim, prefix-stability claim, context-preservation claim, documentation example or
implementation comment was taken on trust. The 45 adversarial cases and the mutation harness were written
against the shipped package and run independently of the milestone's own suite.

---

## 1. Verdict

**Two real defects found, both in the level ordering key, both fixed.** One is P1 — the published event
order depended on the **host's time zone**, contradicting the package's own stated rule that it produces
no environment-dependent output. One is P2 — the key was **not total** for far-future timestamps, so
ordering silently fell back to input order in exactly the case the contract promises it does not.

Everything else held. 45/45 adversarial cases pass, 38/38 mutation probes are detected, prefix stability
is exact at 0 violations across every fixture class, and the intrabar-honesty and no-lifecycle claims are
structurally true rather than merely documented.

| Severity | Found | Fixed |
|---|---|---|
| **P0** | 0 | — |
| **P1** | 1 | 1 |
| **P2** | 2 | 2 |
| **P3** | 3 | 2 (1 documented) |

---

## 2. Findings

### P1-1 — The event ordering key was environment-dependent *(fixed)*

`models._level_key` projected a level's origin timestamp with `datetime.timestamp()`.

`LevelOrigin` validated only `isinstance(timestamp, datetime)` — deliberately matching `SwingPoint`,
which does the same. So a **timezone-naive** origin was representable. `datetime.timestamp()` interprets a
naive value **in the host's local time zone**, so the key — and therefore the public event ordering
contract — changed with `TZ`. Measured directly against the shipped code:

```
TZ=UTC                (0, 100.0, 1, 3, 1704110400.0, 0)
TZ=America/New_York   (0, 100.0, 1, 3, 1704128400.0, 0)
TZ=Asia/Tokyo         (0, 100.0, 1, 3, 1704078000.0, 0)
identical across zones: False
```

Two machines could publish two different orderings of the same level set. That contradicts
`__init__.py`'s own rule — *"no global mutable state, no cache, no registry, no wall clock, no randomness,
**no environment dependence**"* — and it is exactly the class of defect the package's guards exist to
prevent. The existing `test_no_environment_dependence` guard scanned for `os.environ` / `getenv` /
`sys.argv` and could not see this, because the dependence entered through a *standard-library projection*
rather than an environment read.

**Fix.** `LevelOrigin` now requires a **timezone-aware** timestamp, and `_level_key` carries the
`datetime` itself rather than a float. Direct aware-datetime comparison is total, exact and chronological,
and the defect becomes unrepresentable rather than merely tested against.

Stricter than `SwingPoint`, and justified rather than inherited: this timestamp is an **ordering key**,
where `SwingPoint`'s is not. The strictness costs nothing reachable — `structural_levels` builds every
origin from `SwingPoint.timestamp` ← `Candle.timestamp`, which `fmis.data` has already validated as
canonical UTC, verified by `test_every_swing_derived_origin_is_accepted`. Awareness is required but UTC
specifically is not, so `fmis.data`'s contract is not restated in a second place
(`test_a_non_utc_aware_origin_timestamp_is_accepted`).

**Tests added:** `test_a_naive_origin_timestamp_is_rejected` (exact message),
`test_a_non_utc_aware_origin_timestamp_is_accepted`, `test_every_swing_derived_origin_is_accepted`,
`test_the_ordering_key_is_independent_of_the_host_time_zone` (drives `TZ` through three zones and
restores it). **Mutation probe 37** re-drops the check and is detected.

### P2-1 — The ordering key was not total for far-future timestamps *(fixed)*

The same float projection loses resolution as the epoch offset grows. A double has ~2⁻⁵² relative
precision, so beyond roughly the year 2900 it can no longer separate microseconds. Measured:

```
origins 1 microsecond apart in year 3000 -> keys equal: True
  (0, 100.0, 1, 3, 32503680000.0, 0)
  (0, 100.0, 1, 3, 32503680000.0, 0)
```

Two **distinct, non-duplicate** levels therefore produced an **equal** key. `sorted` is stable, so their
relative order became the *input* order — silently violating the permutation-invariance the contract
states and the design's experiment 22 demonstrated (on near-present dates, where the defect is invisible).

Fixed by the same change. **Tests added:** `test_the_ordering_key_is_total_for_far_future_timestamps`,
which asserts the keys differ, that they order chronologically, and that forward and reversed input give
identical output. **Mutation probe 36** reverts to the float projection and is detected.

### P2-2 — The wall-clock guard was a substring scan and produced a false positive *(fixed)*

`test_no_wall_clock_access` scanned source text for `"time.time"`, which matches **inside**
`datetime.timestamp()`. Documenting *why* that projection was rejected therefore failed a guard about
*using* a clock. A guard that punishes accurate documentation of a fixed defect is a guard that will be
weakened by the next person who hits it.

Rewritten AST-based: no `import time` / `import calendar`, and no attribute access named `now`, `utcnow`,
`today`, `monotonic`, `perf_counter` or `time_ns`. Strictly more precise — it catches `x.now()` through
any alias, which the text scan for `datetime.now` did not.

### P3-1 — The internal ordering guard was never exercised *(fixed)*

`crossing._validate_event_order` checks this module's *own output* and is unreachable by construction, so
no test proved it would fire if a future refactor broke the loops. It was verified by hand to fire
correctly, and `test_the_internal_order_guard_actually_fires` now calls it directly with a duplicated
event and pins the exact message.

### P3-2 — The `_NO_TIMESTAMP` sentinel deserved an explicit test *(fixed)*

An origin-less level uses a sentinel in the timestamp slot. It is unreachable for comparison because the
preceding `has-origin` element already separates the two classes — but that is a reasoning step, not a
test. `test_the_no_origin_sentinel_cannot_collide_with_a_real_timestamp` pins it against a level whose
origin timestamp is `datetime.min`, the earliest value a real origin can hold. **Mutation probe 38** makes
the sentinel collide and is detected.

### P3-3 — Event volume is O(candles × levels) with no guard rail *(documented, not fixed)*

At 10,000 candles × 100 levels the derivation produces **580,820 events in 1.69 s at 51.5 MB peak** — linear
and repeatable, but large. This is the accepted cost of the all-crossings decision (ADR-0019 §2.7) and
fixing it would mean adding the lifecycle the milestone deliberately refused. Recorded here so the BOS
milestone sizes its level sets deliberately rather than discovering this later. **No action.**

---

## 3. Re-derived contract verification

Each row was checked against source, not documentation.

| Claim | Verdict |
|---|---|
| **Level semantics** — a price, a side, optional provenance; no lifecycle field | ✅ field set is exactly `{price, side, origin}` |
| **Level identity** — structural and exact; same price + different origin = two levels | ✅ verified; dedup is a detected mutation |
| **Provenance** — index, timestamp and label copied from the swing, never reinterpreted | ✅ `levels.py` reads `comparison.current` and `swing.label` only |
| **Crossing policy** — `TOUCH` / `WICK_BREACH` / `CLOSE_BREACH`, mutually exclusive and exhaustive | ✅ confirmed exhaustively over a 5-value OHLC grid (420 arrangements) |
| **Equality** — exact, `TOUCH` never a breach, no tolerance token anywhere | ✅ AST scan clean; `0.1+0.2` vs `0.3` is a strict breach |
| **Close breach nests inside wick breach** (`high >= close`) | ✅ verified over 200 seeded candles × 22 levels |
| **Wick vs close, `open` never consulted** | ✅ two candles differing only in `open` classify identically |
| **Gap handling** — `GAPPED_BEYOND` / `ALREADY_BEYOND` / `WITHIN_RANGE`, suppression when already beyond | ✅ all four transitions confirmed |
| **Outside-bar ambiguity** — two events, one index, order is the level order | ✅ swapping which side sits nearer the extreme does not reorder |
| **Intrabar-order honesty** — no path field, no "unknown" flag | ✅ structurally unrepresentable, not merely absent |
| **First-candle semantics** | ✅ `ALREADY_BEYOND` at index 0 on both sides |
| **Repeated-crossing semantics** | ✅ cross → retreat → re-cross gives three events |
| **Duplicate levels** — different provenance kept, exact duplicates rejected before derivation | ✅ rejected even with zero candles |
| **Duplicate events** | ✅ none; the internal guard would catch one |
| **Event ordering** | ✅ **after the P1/P2 fixes**: total, explicit, chronological, permutation-invariant |
| **Index semantics** — closed-candle position, matching `SwingPoint.index` | ✅ `closed[event.index] is event.candle` for every event |
| **Timestamp semantics** — the crossing bar's, not the origin's | ✅ pinned with a provenanced level whose origin time differs |
| **Prefix stability** | ✅ **0 violations**: 201 seeded prefixes, 121×22 design fixture, the real fixture, an exhaustive 2-candle × 5-shape space |
| **Replay determinism** | ✅ identical across repeated and rebuilt runs at every size |
| **Context integrity** | ✅ mismatch rejected before arithmetic; empty data keeps identity; no identity argument exists |
| **Exception behaviour** | ✅ every message re-derived and pinned with `==`; no existing message changed |
| **Immutability / hashing** | ✅ frozen+slots throughout; attribute set and new-attribute both raise; events collapse in a set; `pickle` round-trips |
| **Serialization** | ✅ `pickle` equal and hash-equal, matching every sibling; no JSON schema exists anywhere in the repository |
| **Memory duplication** | ✅ levels and candles are held **by reference**; no OHLC value is copied into an event |
| **Runtime complexity** | ✅ linear in candles × levels, confirmed at four sizes |
| **Hidden state** | ✅ no `global`, no module-level mutable literal, no cache, no clock, no randomness |
| **Dependency directions** | ✅ `fmis.data`, `fmis.market_structure`, `fmis.series_context` only; no trend, in imports **or source text** |
| **Public exports** | ✅ 13 names, all resolve, no private leaked, **0 collisions** across the whole `fmis` tree |
| **Future BOS suitability** | ✅ 423 qualifying breaks derived from 2,631 events **without reading one OHLC field** |
| **Future CHoCH suitability** | ✅ definable over the BOS sequence alone |
| **Documentation accuracy** | ✅ after correcting the test-count figures and the ordering-key description |

---

## 4. Adversarial cases — 45/45 pass

| # | Case | Result |
|---|---|---|
| 1–2 | upper / lower strict wick breach | PASS |
| 3–4 | upper / lower equality only | PASS — `TOUCH`, never a breach |
| 5 | close above, wick size irrelevant | PASS — a 1-point and a 30-point wick classify identically |
| 6–7 | wick beyond but close back inside, both sides | PASS |
| 8–9 | gap above / below | PASS — `GAPPED_BEYOND` + `CLOSE_BREACH` |
| 10–11 | candle entirely on the far side of the *opposite*-side level | PASS — no event |
| 12–13 | first candle beyond an upper / lower level | PASS — `ALREADY_BEYOND` |
| 14 | outside bar crossing an upper and a lower level | PASS — 2 events, one index |
| 15–17 | three upper / three lower / mixed levels in one candle | PASS — canonical order |
| 18 | equal price, different provenance | PASS — two events, neither collapsed |
| 19 | duplicate identical levels | PASS — `levels contains a duplicate level (upper 100.0); levels must be distinct` |
| 20 | repeated crossing after moving back across | PASS |
| 21–23 | empty candles / empty levels / both | PASS — `()` |
| 24 | BTCUSDT candles + ETHUSDT levels | PASS — `subjects[1] has identity 'ETHUSDT'/'4h', expected 'BTCUSDT'/'4h'` |
| 25 | BTCUSDT 4h candles + BTCUSDT 1h levels | PASS — `subjects[1] has identity 'BTCUSDT'/'1h', expected 'BTCUSDT'/'4h'` |
| 26 | separately reconstructed equal identity | PASS — accepted, and not `is` the original |
| 27 | empty contextual result | PASS — identity intact |
| 28 | attempted mutation of public models | PASS — all raise |
| 29 | attempted context substitution | PASS — envelope frozen |
| 30 | randomized deterministic replay | PASS — 3,366 events, identical across runs |
| 31 | prefix extension | PASS — **0 violations over 201 prefixes** |
| 32 | reversed input level order | PASS — byte-identical |
| 33 | reversed candle order | PASS — rejected upstream by `CandleSeries` |
| 34 | duplicate timestamps | PASS — rejected upstream |
| 35 | duplicate indices | PASS — unrepresentable; index is the enumerate position |
| 36 | level origin after the candidate crossing | PASS — reported and filterable, per D1 |
| 37 | very large prices (`1e300`) | PASS |
| 38 | negative level price | PASS — representable (`PriceLevel` does not inherit `Candle`'s non-negativity) and behaves |
| 39 | zero price | PASS — `TOUCH` |
| 40–42 | unicode / whitespace / case-different identity | PASS — three distinct identities, no normalization |
| 43 | same payload under three identities | PASS — identity never enters the arithmetic |
| 44 | no dependency on Structural Trend | PASS — absent from imports **and** source text |
| 45 | BOS consuming events without candle re-evaluation | PASS — 423 breaks from 2,631 events, six fields each, no OHLC read |

---

## 5. Performance

Measured on the shipped implementation, `tracemalloc` peak, each run repeated to confirm determinism.

| Candles × levels | Runtime | Events | Peak memory | Repeatable |
|---|---|---|---|---|
| 1,000 × 100 | 0.137 s | 57,658 | 5.2 MB | ✅ |
| 10,000 × 10 | 0.161 s | 57,173 | 5.4 MB | ✅ |
| 100 × 1,000 | 0.157 s | 57,067 | 5.1 MB | ✅ |
| 10,000 × 100 *(added)* | 1.692 s | 580,820 | 51.5 MB | ✅ |

Three equal-work shapes cost the same time to within noise, confirming the cost is the **product** and not
either factor — no pathological behaviour in either dimension. The fourth row was added to check the
product scales linearly, and it does (10× the work, 10.5× the time).

The only avoidable constant is that `LevelCrossingEvent.__post_init__` re-evaluates the crossing rule for
every event it validates, roughly doubling the predicate work. That is deliberate — it is what makes a
self-contradictory event unconstructable and is the target of mutation probe 35 — and at these magnitudes
it is not worth trading for. **No optimisation recommended.** The repository defines no benchmark
threshold, and none is proposed here.

---

## 6. Mutation validation after review fixes — 38/38 detected

Re-run independently after the fixes, with three probes added for the corrected code.

| Result | |
|---|---|
| probes | **38** |
| no-ops (SHA unchanged) | **0** |
| survivors (undetected) | **0** |
| restore failures | **0** |
| final SHA-256 match, all four sources | ✅ |

```
models.py    7fcdb7afd3ad78354cc4ab8574ef635c1fb79bcc1d2bd0095babc3b2f57b79b3  match=True
crossing.py  56987c39247466328e7b73b1c68f80506b49f458c1c581e89293a4508568dd16  match=True
levels.py    102cbd2d52d6d1de46972610073dcaafb4e07e82e40a680ebc120005855f8f99  match=True
pipeline.py  92b9b22dc905814fd435b692ebd8face26cc8fe0b680014923bff3979bd991bd  match=True
```

Probes 36–38 target the review fixes: reverting the key to a POSIX-float projection, dropping the
timezone-awareness check, and making the origin-less sentinel collide with a real timestamp. Each is
detected by exactly the test written for it, confirming the fixes are pinned rather than merely applied.

One earlier survivor is worth recording, because it found a real gap during implementation rather than
review: probe 10 (*project the origin's timestamp instead of the candle's*) initially **survived**, because
every timestamp test used origin-less levels, where the mutation's fallback path was identical. Two tests
using provenanced levels closed it.

---

## 7. Validation results

| Check | Result |
|---|---|
| full suite | **2856 passed** |
| full suite, `-W error` | **2856 passed** |
| `tests/test_level_crossing.py` | **246** |
| `tests/test_market_structure_*.py` | **1227** (unchanged) |
| `tests/test_structural_trend.py` | **353** (unchanged) |
| `tests/test_series_context.py` | **184** (183 + 1 added guard) |
| export collisions across `fmis` | **0** |
| `git diff --check` | clean |
| `pyproject.toml`, `uv.lock` | **unchanged** |
| runtime dependencies added | **none** — stdlib only |
| existing analytical behaviour changed | **none** |

---

## 8. What was *not* changed, and why

- **No lifecycle was added.** D1 (activation) remains deferred. The review deliberately did not "fix" it:
  filtering candles before a level's origin requires deciding whether a level exists at its pivot bar or
  only once that pivot is confirmed, and that decision belongs to BOS with its own record. A consumer
  applies it in one expression on fields the event already carries, which case 36 demonstrates.
- **D2 (first swing of each type has no level)** was not widened. Doing so needs `LevelOrigin.label` to
  become optional, which changes a validated invariant to serve a case no consumer has yet stated.
- **No tolerance was introduced**, per ADR-0013 §4 and market-structure review §9.
- **`PriceLevel` was not made to reject negative or zero prices.** `Candle` forbids them; a *level* is not
  a candle, and inventing a stricter numeric domain here would be a decision without a stated need.

---

## 9. Remaining P2 / P3

| | Item | Status |
|---|---|---|
| P3-3 | O(candles × levels) event volume, 580k events at 10,000 × 100 | **Open, documented.** Accepted cost of the all-crossings decision; sizing is the consumer's. |
| — | D1 activation, D2 first-swing levels, D3 tolerance, D4 gap/already self-validation, D5 time gaps, D6 multi-timeframe indices, D7 serialization | **Open by design**, each recorded in ADR-0019 §6. |

No P0 or P1 remains. No P2 remains.

---

## 10. Recommended next milestone

**Break of Structure Foundation v1**, and the precondition it was blocked on is now met: adversarial case
45 derives 423 qualifying breaks from 2,631 crossing events **without reading a single OHLC field and
without re-implementing the crossing rule**. Every input BOS needs — the level, its provenance and label,
the crossing bar's index and timestamp, the kind and the mechanism — is on the event.

What BOS must decide, all of which this milestone deliberately left open: which level is protected and
when protection ends; activation (D1); whether a `TOUCH` or a `WICK_BREACH` breaks anything or only a
`CLOSE_BREACH`; whether an `EQUAL_HIGH`-derived level breaks anything; and how the two events of an
outside bar are treated given that **their order is not a time claim**.

Then CHoCH over the BOS sequence, never over trend, per market-structure review §15.
