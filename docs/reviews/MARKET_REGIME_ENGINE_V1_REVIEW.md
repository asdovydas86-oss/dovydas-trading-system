# Market Regime Engine v1 — Independent Review

**Milestone:** AI
**Reviews:** [ADR-0025](../adr/ADR-0025-market-regime-engine-v1.md),
[design](../design/MARKET_REGIME_ENGINE_V1.md)
**Date:** 2026-08-03
**Verdict:** no P0, no P1, **four P2 found and fixed**, three P3 documented

Every claim was re-derived from production code. Counts, coverage, timings and mutation results were
measured in this review, not copied from the design.

---

## 1. Scope

The review targeted the failure modes the milestone brief named, and the ones
`docs/analysis-notes.md` records from v2:

hidden direction bias · forced classification · threshold overfitting · double-counted correlated
evidence · unavailable evidence treated as real · regime conflated with signal · cross-timeframe
leakage · duplicated calculation · import inversion · opaque confidence · output more certain than its
evidence.

---

## 2. Hidden direction bias — verified absent, after a fix

The engine cannot distinguish a rising structure from a falling one. `SUSTAINED_HIGHER` and
`SUSTAINED_LOWER` are members of one tuple and there is no branch between them; a test compares two
whole regimes built from each and asserts equality. The moving-average family asks *beyond both* rather
than *above both*, so mirroring price around the averages yields the same state.

**One leak was found and fixed during the review** — see P2-1: the evidence line printed the raw trend
value, so a run showed `sustained_lower` inside the regime output. Nothing consumed it, but it put a
direction in front of a reader on a page whose own limitation says direction is not restated.

A whole-word scan over every reachable evidence string, source and reason — swept across all four
`StructuralTrendType` values × four closes × three change positions × four participation ratios — now
finds none of: bullish, bearish, buy, sell, long, short, up, down, rising, falling, higher, lower,
signal, recommend, entry, target, confidence, score, profit, bias, verdict.

## 3. Forced classification — verified absent

`INSUFFICIENT` and `INDETERMINATE` are distinct states and both are reachable. Structure refuses to
classify from one readable family, which is the strictest of the three dimensions and deliberately so:
a single-family call is the free confirmation v2 gave away.

The result carries **no overall state and no score**. `MarketRegime` has no field or attribute matching
overall, score, confidence, rank, verdict or bias, asserted directly.

## 4. Double counting — verified absent

The four evidence families partition across the three dimensions, and a test asserts the partition
rather than describing it: no family name appears under two dimensions, and the union is exactly the
four declared families.

Within the structure dimension, structural trend and change of character share the `swing structure`
family name, so the dimension sees **two** families where a naive implementation would have counted
three observations. That is asserted too.

## 5. Findings

### P2-1 — the regime printed a direction it did not use *(found and fixed)*

The swing-structure evidence carried `trend.value`, so live output read
`context  sustained_lower  swing structure`.

The classification never used the direction — the code cannot see it — but the *evidence* displayed it,
directly beneath a limitation stating that which way structure points is not restated here. A reader
would reasonably take it as part of the regime.

**Found by reading live output**, not by a test: every test asserted states, and the states were right.

**Fixed** by reporting what the family actually read: `"structure sustained in one direction"`,
`"structure not sustained"`, `"structural trend indeterminate"`. The whole-word sweep in §2 now covers
every reachable string, so the leak cannot return silently.

### P2-2 — the provenance field accepted anything *(found and fixed)*

`MarketRegime.policy` was typed `Any` and never validated. A result could cite a string, a dict or
`None` as the policy that produced it — and `ARCH` §9's whole requirement is that a regime be
reproducible from its parameters. A result citing a policy that could not have produced it is worse
than one citing none, because it reads as reproducible.

**Fixed**: typed `RegimePolicy` and type-checked in `__post_init__`. No import cycle exists —
`policy.py` imports only the standard library.

### P2-3 — validation ran in the wrong order *(found and fixed)*

`MarketRegime.__post_init__` built the list of dimension names *before* checking that each element was
a `RegimeDimension`, so a wrong element raised `AttributeError` from inside a comprehension instead of
the intended `TypeError` naming the argument.

**Found by a coverage test**, written to reach a branch nothing had executed — which is the argument
for the 100 % standard: an unexecuted validation branch is one whose wording and behaviour nobody has
checked.

**Fixed** by checking types first.

### P2-4 — an assertion that could never fail *(found and fixed)*

`test_the_fact_sheet_renders_exactly_as_before` contained
`assert "structure" not in text.split("STRUCTURE")[0].lower() or True`.

The trailing `or True` makes the whole expression unconditionally true. It read as coverage of AF's
output and provided none. **Removed**; the surrounding assertions that do the real work — that no
regime vocabulary appears in the fact sheet — were already present and pass.

### P3-1 — volatility and participation each rest on one evidence family

Neither can be corroborated or contradicted within its own dimension, so neither can ever report a
disagreement. Only structure requires two families to agree.

This is a property of what the repository computes, not an oversight: there is one true-range
comparison and one volume ratio. It is printed as limitation `AI-2` on every run so a reader weights
those two dimensions accordingly.

### P3-2 — a regime cannot be pickled

`MarketRegime` copies metadata into a `MappingProxyType`, which pickle cannot serialise. This is the
repository's established convention and **not specific to AI**: `StructuralFactSheet` and
`MultiTimeframeFactSheet` are equally unpicklable, which the review verified directly.

Giving this one model a custom `__reduce__` would make it the odd one out for no consumer that exists.
Persistence is open decision **D-01**; when it is settled the answer belongs to every metadata-carrying
model at once. A test records the current behaviour rather than leaving it undiscovered.

### P3-3 — the thresholds have never been validated against history

The bands are stated policy. No backtest justifies 0.20, because no backtester exists. `ARCH` §9 asks
that regimes be *measurable after the fact*, and that half of the contract is met structurally — the
policy travels on every result and classification is reproducible — but not yet empirically. Printed as
`AI-3`.

## 6. Mutation results

**45 probes · 45 detected · 0 survivors · 0 no-ops**, with byte-identical source restoration verified
by SHA-256 across all six touched modules.

Probes cover: both structure families and their voting rule, the two-family requirement, the
transition rule and its boundary, evidence-status handling including the unavailable guard, the
volatility ratio and both its edges, the participation edges, family separation, dimension order and
assembly, policy symmetry and validation, every adapter field, the renderer's evidence grouping, and
the command registry.

**Seven probes survived their first run. Every one was a real test gap, and all seven are closed:**

| Probe | Gap it exposed |
|---|---|
| indeterminate trend becomes conflicting | the *status* of that evidence was never asserted — restating laundered the mutation |
| transition boundary excluded | no test at exactly `transition_lookback_bars` |
| unavailable restated as conflicting | the guard that protects silence was never exercised directly |
| elevated boundary excluded | participation boundaries untested; volatility's were tested |
| subdued boundary excluded | same |
| participation edges not mirrors | symmetry asserted for volatility only |
| adapter drops the change of character | no fixture with a change of character reached the adapter |

The last one is worth naming: the adapter test used a fixture whose sheet had no change of character,
so the field could be deleted with nothing noticing. The replacement uses seed 5, which produces three
changes with the latest at bar 254, and asserts the value reaches the classification.

The harness purges `__pycache__` and sets `PYTHONDONTWRITEBYTECODE=1` before every probe, and runs the
**full suite** per probe — both corrections carried forward from the AG review §6.

## 7. Measured results

**3,582 tests pass**, identically under `-W error` (3,449 before AI; **+133**).

| Module | Coverage |
|---|---|
| `market_regime/classify.py` | **100 %** |
| `market_regime/models.py` | **100 %** |
| `market_regime/policy.py` | **100 %** |
| `market_regime/__init__.py` | **100 %** |
| `pipeline/regime.py` | **100 %** |
| `pipeline/render.py` | **100 %** |
| `pipeline/cli.py` | **100 %** |

Public exports **183** (154 before AI: **+19** in `fmis.market_regime`, **+10** re-exported from
`fmis.pipeline`), **zero collisions** — verified
against `fmis.features.VolatilityRegime`, the name that forced `VolatilityState`. Import cycles **0**.
Runtime dependencies **0**. `pyproject.toml` and `uv.lock` untouched.

**Benchmark.** Classification is free relative to the data it reads:

| candles | fact sheet | adapt | classify | classify share |
|---:|---:|---:|---:|---:|
| 100 | 1.21 ms | 0.0023 ms | 0.0059 ms | 0.49 % |
| 260 | 5.98 ms | 0.0024 ms | 0.0059 ms | 0.10 % |
| 500 | 21.54 ms | 0.0023 ms | 0.0061 ms | 0.03 % |

Live end to end, one timeframe at 300 candles including network: **~1.4 s**, essentially all of it the
fetch.

## 8. Adversarial inputs

| Input | Result |
|---|---|
| Every field `None` | all three dimensions `INSUFFICIENT`, no conflicting evidence anywhere |
| Structural trend `INDETERMINATE` | swing family `UNAVAILABLE`, structure `INSUFFICIENT` |
| Families disagreeing | `INDETERMINATE`, both marked conflicting, reason recorded |
| Change of character exactly at the lookback edge | `TRANSITIONING` (inclusive) |
| Change of character one bar beyond it | not transitioning; the event still shown as `CONTEXT` |
| `latest_change_index > last_index` | `RegimeInputError` |
| ATR baseline of 0 | `INSUFFICIENT` — no division |
| Ratio exactly at either edge | classified (inclusive on both sides) |
| A ratio and its reciprocal | exact mirror states, at three bands × four factors |
| Band of 0 or negative, or non-finite | `RegimePolicyError` |
| Blank or non-string `policy_id` | rejected |
| Negative or boolean lookback | rejected |
| A non-`RegimePolicy` policy on a result | `TypeError` |
| Repeated or reordered dimensions | `RegimeInputError` |
| `NaN` / `inf` on any numeric field | `RegimeInputError` |
| A feature present but not numeric | reads as unavailable, never as zero |
| Warm-up: 40-candle series | volatility `INSUFFICIENT`, other dimensions still classified |

## 9. Boundaries, determinism and the layers around it

`fmis.market_regime` imports **exactly one** name from the repository outside its own modules:
`fmis.structural_trend`. It cannot see `fmis.pipeline`, `fmis.decision_support`, `fmis.features`,
`fmis.data` or a provider — asserted by AST and by a docstring-stripped source scan. Nothing below the
application layer imports it.

The composition root contains **no arithmetic operator**, matching `structural_facts`' own predicate,
which is why the input carries indices rather than a distance.

Classification output is identical under `PYTHONHASHSEED` 0, 1, 42 and 12345 in fresh subprocesses.
Two classifications of one sheet are equal, and prefix behaviour was checked at three cuts.

**AF and AG are unchanged.** `default_features()` and `swing_features()` are byte-identical, the fact
sheet and multi-timeframe pages print no regime vocabulary, and AH's provenance still holds on every
level the regime path builds — all asserted.

## 10. Verdict

| Severity | Count | Detail |
|---|---:|---|
| **P0** | 0 | — |
| **P1** | 0 | — |
| **P2** | 4 | Direction printed in evidence · `policy` typed `Any` · validation order · a vacuous assertion — **all fixed** |
| **P3** | 3 | Single-family dimensions · not picklable (repository-wide, D-01) · thresholds unvalidated against history |

The milestone does what it claimed: a deterministic, versioned, diffable regime call with its evidence,
its conflicts, its gaps and its exact parameters — replacing a judgement made inside a prompt.

**The thing this review would not let pass** is the word "evidence-based" applied to volatility and
participation. Each rests on one family and therefore can never disagree with itself; calling their
output corroborated would be a stronger claim than the data supports. It is printed as a limitation on
every run rather than argued away here — and it is the first thing Market Regime v2 should fix.
