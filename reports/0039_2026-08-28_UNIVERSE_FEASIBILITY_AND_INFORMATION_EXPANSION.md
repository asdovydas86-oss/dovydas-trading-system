# Universe Feasibility & Information Expansion — Implementation and Research Record

| Field | Value |
|---|---|
| **Report number** | 0039 |
| **Title** | Universe Feasibility & Information Expansion Study (Milestone CC) |
| **Date** | 2026-08-28; reviewed and revised 2026-09-03 |
| **Report type** | Implementation + Research |
| **Model** | Claude Opus 5 |
| **Repository branch** | `main` |
| **Audited commit** | base `c320525`; this milestone's work is **uncommitted** in the working tree |
| **Status** | Final — independent review performed 2026-08-29 / 2026-09-03 (§21); artifact regenerated 2026-09-03 (§24) |

**Milestone:** CC — Universe Feasibility & Information Expansion Study.

**Scope guard.** No production trading policy changed. `CONFIRMATION_LOOKBACK_BARS`
is still `10`, `MINIMUM_AGREEING_FAMILIES` is still `2`, `DEFAULT_TIMEFRAMES` is
still `1w/1d/4h` and `DEFAULT_BACKTEST_LIMIT` is still `250` — each asserted by
import in `tests/test_universe_architecture.py::TestProductionSafety`. The BY and
CA seals are byte-identical and CB's results reproduce. **No strategy was tested,
no threshold tuned, no admission rule altered, no order placed, no credential
read, no private endpoint touched and no AI called.** Two public, unauthenticated,
read-only endpoints were used: `GET /api/v3/exchangeInfo` and `GET /api/v3/klines`.

**No verdict in this milestone is permission to trade, paper trade, shadow trade
or promote anything.** `FeasibilityVerdict.is_approved_for_trading` is `False` for
every member, asserted over the whole enum. Milestone CA's `NO_EDGE` stands
untouched: CC measures *information*, never *edge*.

---

## 1. The one-sentence answer

**No.** Binance public spot — the only market-data provider this repository
integrates — cannot supply enough independent information to honestly test
Milestone CA's +0.10 ATR swing admission effect, and the shortfall is roughly a
factor of four to twelve depending on which dimension is counted. The binding
constraint is **cluster count**, and it is imposed not by the exchange but by
FMITS's own production analysis path.

Verdict: **`INFEASIBLE`**, binding constraint `cluster_count`.

---

## 2. Reading key

| Tag | Meaning |
|---|---|
| **FACT** | A property of the repository or the provider, checkable by inspection. |
| **MEASUREMENT** | A number this milestone computed from data it fetched. |
| **PROJECTION** | A model output. Never presented as a measurement. |
| **INTERPRETATION** | What the author concludes from the above. |
| **ASSUMPTION** | Something taken as true without measuring it. |
| **LIMITATION** | Something this milestone could not settle. |

---

## 3. Verified starting state

**FACT.** Every check below was run before any file changed.

| Check | Value |
|---|---|
| `HEAD` | `c320525c3913df993e01d98ff4f8d1b66f75e7e3` |
| local `main` | `c320525c3913df993e01d98ff4f8d1b66f75e7e3` |
| `origin/main` | `c320525c3913df993e01d98ff4f8d1b66f75e7e3` |
| `git ls-remote origin refs/heads/main` | `c320525c3913df993e01d98ff4f8d1b66f75e7e3` |
| ahead / behind | `0 / 0` |
| staged files | none |
| stash | empty |
| merge/rebase/cherry-pick/bisect in progress | none |
| untracked research documents | 16, all preserved unmodified |

**MEASUREMENT.** Baseline suite before implementation:
`uv run python -W error -m pytest -q` → **12,952 passed in 502.33s**, exit 0.

---

## 4. Architecture and data audit

**FACT.** Authoritative owners identified, and what CC did about each.

| Concern | Owner | CC's decision |
|---|---|---|
| Market-data fetching | `fmis.providers.binance` | **Extended**, not replaced — see §5 |
| Provider abstraction | `binance.Transport` | Reused verbatim |
| Candle schema | `fmis.data.Candle` / `CandleSeries` | Reused; no second candle model |
| Canonical decoding | `fmis.ingest.decode_candle_series` | Reused; it caught a real defect (§9) |
| Timeframe normalisation | `binance.KLINE_INTERVALS` | Reused |
| Symbol identity | `fmis.data.SeriesIdentity` | Reused for series; **economic** identity is new (§6) |
| Warm-up requirement | `fmis.swing_setup.research_warmup.derive_warmup` | **Called, never restated** |
| Production timeframes | `fmis.pipeline.multi_timeframe.DEFAULT_TIMEFRAMES` | Read, unchanged |
| Sample boundaries | `fmis.swing_lab.preregistration.SAMPLES` | Imported by identity |
| CA's sealed constants | `fmis.swing_lab.admission_preregistration` | Imported by identity |
| Statistical design | `fmis.research_design` (CB) | **Called, not reimplemented** |
| CA published figures | `fmis.swing_lab.admission_power` | Reused |
| Admission replay | `fmis.swing_lab.validation_study.capture_for_window` | Reused under the production variant |
| Artifact conventions | `fmis.swing_lab.persistence_artifact` | Pattern reused (digest-excludes-own-slot, deterministic gzip) |
| CLI | `fmis.pipeline.cli` `research` subcommand | Extended with one area |
| Architecture guards | `tests/test_research_design_architecture.py` | Pattern reused |

**FACT.** Nothing was duplicated. No second candle model, no second exchange
adapter, no second bootstrap, no second power calculator, no second sample-floor
framework, no second digest convention, no second CLI architecture. The only new
abstraction is **economic asset identity**, and §6 states why the repository
lacked it.

**INTERPRETATION.** The single most valuable thing the audit found is that
`derive_warmup` already owns the history requirement. Hard-coding 1,750 days would
have made CC's central finding an artefact of a number retyped in a research
module; calling the production owner makes it a statement about the product.

---

## 5. Provider extension, and why it was necessary

**FACT.** Before CC, `fmis.providers.binance` supported exactly one endpoint,
`GET /api/v3/klines`. That endpoint answers *what did this instrument do*; it
cannot answer *which instruments exist*. A universe-feasibility study whose
universe came from a hand-written list would be measuring the list.

**FACT.** CC added `fetch_exchange_info`, `build_exchange_info_url`,
`map_symbol_record`, `SymbolRecord` and `ExchangeInfo` to the **existing** adapter.
`GET /api/v3/exchangeInfo` is public, unauthenticated, signs nothing and reads no
account. No second provider was added: the brief's test — *does the existing
provider fail to answer the feasibility question* — is not met, because it answers
it well.

**FACT.** The repository's existing guard
`test_only_the_public_klines_endpoint_is_referenced` asserted the endpoint set was
exactly `{"/api/v3/klines"}` and correctly failed. It was renamed to
`test_only_public_unauthenticated_endpoints_are_referenced` and widened to exactly
`{"/api/v3/klines", "/api/v3/exchangeinfo"}` — **still an exact set**, so a third
endpoint still fails. `test_no_private_or_authenticated_endpoints` was **not**
touched and still covers the property that matters.

---

## 6. The unit of "symbol", and why a ticker is not a cluster

**FACT.** Milestone CA's sealed cluster axis is the symbol, and CB's requirement
is stated in clusters. So the ticker → experimental-unit mapping is the single
most consequential rule in CC.

**FACT.** The repository had no economic-asset identity. `SeriesIdentity` names a
series; nothing said that `BTCUSDT`, `BTCFDUSD` and `WBTCUSDT` are one exposure.
CC implements the smallest research-only representation that closes it:
`EconomicAsset`, with sealed sets for stablecoins, wrapped representations,
leveraged tokens and redenominations. Production identity was **not** redesigned.

**FACT — a design decision worth recording.** The obvious leveraged-token rule is
a suffix match on `UP`/`DOWN`/`BULL`/`BEAR`. Run against Binance's actual USDT
listings that rule deletes **`JUP`** (Jupiter) and **`SYRUP`** (Maple), two
ordinary tokens. Every classification in CC is therefore an explicit sealed set
matched by exact string equality, and `test_a_suffix_rule_would_have_removed_real_assets`
pins the counterexample so nobody re-introduces the pattern.

**MEASUREMENT.** The name rule can only err by *omitting* a peg, which inflates
the cluster count. So it is not trusted alone: `peg_like_by_volatility` flags any
asset realising under 5 % annualised, whatever it is called. On the eligible
universe it flagged **zero** assets — the sealed list and the data agree.

---

## 7. Pre-registration

**FACT.** Sealed **before** the full-universe funnel was run.

```
CC_PREREGISTRATION_DIGEST = ef6f39508a3d183c88618c727ba65fd8c6ffdcada4452660aaa4ad74a0021bac
```

Sealed content: research question · provider · discovery rule · eligible quote
asset · depth interval · minimum measurement years · maximum missing fraction ·
maximum gap · minimum median notional · representative rule · ordering rule ·
growth sizes · effect grid · primary effect · dependence scenarios · density
subsample size and seed · verdict rules · refutation conditions · limitations ·
CA's pre-registration id and digest · the full identity ruleset · the survivorship
and verdict vocabularies.

**FACT — digest determinism proven, not asserted.**
`test_the_digest_is_stable_across_hash_seeds` recomputes it in four subprocesses
under `PYTHONHASHSEED` ∈ {0, 1, 12345, 999983}; all four agree.

**FACT — mutation coverage.** Twenty-three parameterised mutations, one material
field each, all assert the digest **moves**. One test asserts that reordering a
dict literal does **not** move it, so the seal tracks content rather than
formatting.

**FACT.** Two constants are imported by identity rather than retyped: the +0.10
ATR bar is `Decimal(str(MIN_ADMISSION_EDGE_ATR))` and the window is BY's
`development` sample. Tests assert both.

---

## 8. Discovery and the eligibility funnel

**MEASUREMENT.** Discovery at provider `serverTime` `2026-08-28T20:30:15.971Z`.

| Stage | Removed | Remaining |
|---|---:|---:|
| Discovered spot instruments | — | **3,649** |
| Quote currency not USDT | 2,951 | 698 |
| Base is a stablecoin | 21 | 677 |
| Base is a leveraged token | 8 | 669 |
| Base is a wrapped representation | 3 | 666 |
| Duplicate economic exposure | 6 | **660 economic assets** |
| No history available | 24 | 636 |
| Insufficient history for warm-up | 526 | 110 |
| Insufficient measurement coverage | 72 | 38 |
| Data quality (missing / gap / duplicate / malformed) | 0 | 38 |
| Liquidity (insufficient / no evidence) | 0 | **38 eligible** |

**FACT — these two input counts changed during the milestone, and that is the
point of recording them.** The first measurement, on 2026-08-28, discovered
**3,645** instruments and **656** economic assets. The artifact was regenerated on
2026-09-03 after the independent review (§21, §24) and the provider had listed
**four** more instruments in the interval — all tokenised-equity products
(`CRWDB`, `MRNAB`, `SQQQB`, `STXB`) listed in 2026, every one of which fails the
warm-up rule immediately, which is why `insufficient_history_for_warmup` rose from
522 to 526 and **the eligible universe did not move at all**.

**Every downstream SCIENTIFIC figure is bit-identical across the two runs** — the
dependence measurements, the density, the growth curve, the effect grid, the
horizon ceiling and the verdict. Checked field by field, not inferred.

**The survivorship counts moved, and they are the exception.** Halted instruments
rose 2,287 → 2,290 and halted-and-eligible 3 → 4, because **ICX was delisted during
the milestone** (§10). Survivorship is a *statement about the provider's current
listing*, so unlike every other figure here it is expected to move when the listing
does; recording it as identical would have been wrong.

This is provider mutability observed live — exactly the hazard Milestone BZ recorded
as BZ-D2, and the reason the capture and the study are separate layers.

**FACT.** The funnel reconciles: 3,649 − 3,611 = 38, asserted by `FunnelCounts`
which refuses to construct otherwise. Every one of the 3,611 removals carries a
machine-readable `ExclusionReason` **and** a non-empty detail sentence naming the
number that fired the rule; `Exclusion` refuses an empty detail.

**MEASUREMENT.** The 38 eligible economic assets:

```
ADA ALGO ANKR ATOM BAT BNB BTC CELR COS DASH DOGE DUSK ENJ EOS ETC ETH FET HOT
ICX IOST IOTA LINK LTC NEO NULS ONE ONG ONT QTUM TFUEL THETA TRX WIN XLM XRP
ZEC ZIL ZRX
```

**INTERPRETATION — the decisive structural fact.** 594 of the 618 depth
exclusions (522 + 72) are *history*, not data quality. Zero instruments were
removed for missing bars, gaps, duplicates or liquidity. **Binance's data is not
the problem. FMITS's own warm-up requirement is.**

---

## 9. Historical depth, data quality, liquidity

**MEASUREMENT — the derived warm-up.**
`derive_warmup(DEFAULT_TIMEFRAMES, limit=250)` returns **1,750 days = 4.791
years**, driven entirely by the `CONTEXT` role: the weekly timeframe at a
250-candle analysis window. The `SETUP` role costs 250 days and `EXECUTION` costs
41. An instrument must therefore have listed **1,750 days before a measurement
window opens** to contribute a single analysable instant.

**MEASUREMENT — listing-year distribution across the 656 economic assets** (as
measured on 2026-08-28; the four instruments listed since are all 2026):

| Year | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Assets | 6 | 13 | 62 | 107 | 124 | 39 | 53 | 62 | 98 | 92 |

**INTERPRETATION.** Only 81 economic assets listed before 2020, and the CA
development window (opening 2023-06-01) needs a listing on or before 2018-08-25
for a full two years of measurement. The crypto listing distribution and the FMITS
warm-up requirement are close to disjoint.

**MEASUREMENT — usable measurement span across the 38 eligible assets:**
min 1.875 y · median 2.001 y · max 2.001 y · mean **1.998 y**.

**MEASUREMENT — data quality.** Zero eligible assets exceeded the 2 % missing-bar
ceiling, the 7-bar gap ceiling, or carried any duplicate or malformed bar.

**FACT — one real defect found.** `KLAYUSDT` returns a kline whose close time
(`1730084399999`) **precedes** its open time (`1730246400000`). The canonical
`fmis.ingest` boundary refused it. CC records this as a named
`MALFORMED_BARS` exclusion rather than crashing — one bad listing must not take a
universe measurement down. This is a genuine provider data defect, found by
reusing the repository's own validation rather than by writing a looser one.

**MEASUREMENT — historical liquidity.** Median daily traded notional *inside the
window*, across the 38 eligible: min 815,881 · median 3,113,733 · max
1,658,609,658 USDT/day. All 38 clear the sealed 100,000 floor by at least 8×.

**LIMITATION (CC-4).** Notional is `close × volume`, a proxy for the provider's
quote volume computed from canonical fields. It is not depth, not spread and not
slippage. **An asset passing this floor is not thereby executable at size.** The
floor was set deliberately low so that feasibility would not silently become a
liquidity answer — and it did not bind on a single instrument.

**LIMITATION (CC-5).** Eligibility is assessed on **daily** bars. A daily series
can be complete while its 4h series is not, so these quality figures are an upper
bound on 4h completeness.

---

## 10. Survivorship

**FACT — the finding that makes this measurable at all.** Binance retains
delisted spot pairs in `exchangeInfo` with `status="BREAK"` **and continues to
serve their klines up to the day they stopped trading.** Verified directly:
`SRMUSDT` (last bar 2022-11-28), `BTCSTUSDT` (2022-11-28), `WAVESUSDT`
(2024-06-17), and retention reaching back to `VENUSDT` (2018-10-19) and `BCCUSDT`
(2018-11-20).

**MEASUREMENT.** 2,290 of 3,649 discovered instruments (62.8 %) are halted. **Four**
halted assets — **COS, EOS, ICX, NULS** — survive into the 38-asset eligible
universe. Instruments that disappeared are genuinely represented.

**FACT — one of them was delisted during this milestone.** On 2026-08-28 the
halted-and-eligible set was three (COS, EOS, NULS); on 2026-09-03 it was four.
**ICX (ICON) stopped trading in the interval**, while remaining eligible — correctly,
because its full measurement-window history is intact and CC measures a historical
window rather than present tradability. An instrument leaving the market mid-study
is the clearest possible demonstration of why a current-listing snapshot is not a
research universe.

**FACT — retention is demonstrably incomplete.** `HSRUSDT` traded on this provider
and is absent from **both** `exchangeInfo` and `klines` (HTTP 400). At least one
instrument is unrecoverable.

**Classification: `PARTIALLY_SURVIVORSHIP_AWARE`.**

**LIMITATION (CC-3).** The size of the unrecoverable set cannot be measured from
inside the provider. It is recorded as **unmeasurable**, never as zero.
`SurvivorshipReading` refuses to construct `SURVIVORSHIP_AWARE` while a gap is
demonstrated, and refuses `CURRENT_SURVIVOR_ONLY` while halted instruments are
present — both directions of misdescription are rejected.

---

## 11. Dependence — the core of CC

**MEASUREMENT.** Daily log returns, aligned by instant, over the 38 eligible
assets across the 731-day window. 703 pairs measured, 0 skipped.

| Quantity | Value |
|---|---:|
| Raw mean pairwise correlation | **0.6041** |
| Raw median pairwise correlation | 0.6200 |
| 90th-percentile pairwise correlation | 0.7498 |
| First eigenvalue's share of variance | **0.6254** |
| Residual mean correlation (market factor removed) | **−0.0248** |
| Demeaning artefact, −1/(K−1) at K=38 | **−0.0270** |
| **Residual excess over the artefact** | **+0.0023** |

**FACT — why the residual must not be read against zero.** Subtracting the
cross-sectional mean from K series constrains the residuals to sum to zero on
every instant, inducing a pairwise correlation of exactly −1/(K−1) *even among
perfectly independent series*. The measured −0.0248 sits **above** the −0.0270
floor by 0.0023.

**INTERPRETATION — and a correction the independent review forced.** Crypto assets
share a single dominant market factor accounting for **62.5 %** of return variance.
Once it is removed, what remains is statistically indistinguishable from
independence.

**But that sentence means less than it appears to, and the review established why.**
Cross-sectional demeaning removes *any* exchangeable common component **exactly**:
for `K` series `x_i = f + e_i` whose idiosyncratic parts are equicorrelated at any
level `rho_e`, the demeaned residuals have pairwise correlation exactly `−1/(K−1)`.
Verified by simulation at `rho_e` of 0.0, 0.2, 0.5 and 0.8 — all four return an
excess of `0.00000`.

So the residual measurement is **structurally incapable of measuring the level of
residual dependence**; it measures departure from exchangeability. The
pre-registration's claim that the three scenarios "bracket the answer" is wrong:
the usable bracket is `[independent = 0, raw = 0.604]` with **no informative
middle**. Recorded as post-review limitations **CC-7** and **CC-8** (§21.2, §23).

**This cuts against feasibility, not for it — and the size of the effect is worth
stating precisely.** Because the effective cluster count saturates at `1/r`, the
half-width approaches a floor of `z·σ·sqrt(r / (years × density))`, so a
between-asset correlation of order **0.002** is enough to put that floor above the
+0.10 ATR bar and make the effect unreachable at *any* universe size. The
break-even value — where the floor equals the bar exactly — is **r = 0.00214**.

**+0.0023 is NOT a measured between-asset correlation and must not be read as one.**
It is the measured *excess over the demeaning artefact*, and CC-7 says that quantity
cannot identify a dependence level. It is used here only as a **sensitivity input**,
and its margin over break-even is thin: **5.9 %**. A release audit re-derived the
sensitivity and it flips under ordinary variation —

| perturbation | break-even `r` | does the measured excess still exceed it? |
|---|---:|---|
| as measured | 0.00214 | yes |
| density ±10 % | 0.00192 / 0.00235 | yes / **no** |
| usable years ±10 % | 0.00192 / 0.00235 | yes / **no** |
| CA half-width ±30 % (limitation CB-6) | 0.00127 / 0.00436 | yes / **no** |

So the claim this milestone actually supports is the **conditional** one: *a
between-asset correlation of this order would be decisive, and CC cannot exclude
one.* The stronger reading — that the measured excess by itself proves
unreachability — is **not** supported, because CB-6 states the input interval
carries roughly ±30 % scatter and the claim does not survive that.

**MEASUREMENT — measured co-moving groups** (single linkage at r ≥ 0.80, letting
the data draw the boundaries rather than a label): two groups, of 15 members
(`ANKR ATOM BAT CELR DASH ENJ HOT ICX IOST IOTA NEO ONE ONT QTUM ZIL`) and 2
(`ETC ETH`). Notably the 15-member group cuts straight across the usual "L1 /
DeFi / meme" taxonomy — evidence that subjective category labels are a poor
dependence model, which is why they are not used as one.

### 11.1 The intracluster correlation CB left open

**MEASUREMENT + LIMITATION (CC-1).** CB left the intracluster correlation
unspecified. CC closes the part that can be closed and is explicit about the part
that cannot.

CA's estimand is a **paired within-symbol difference** — an admitted instant
against a volatility-matched control on the same symbol in the same period. The
market factor is very largely differenced out of such a comparison. So:

* the **raw** 0.6041 is an **upper bound** on between-asset dependence for this
  estimand, not an estimate of it;
* the **residual** +0.0023-over-artefact was pre-registered as the closest
  strategy-outcome-independent proxy for what a paired difference retains —
  **this reading is SUPERSEDED by CC-7** and is recorded here as what was sealed,
  not as what is claimed. It cannot identify a dependence level;
* **zero** is the lower bound, and is exactly what CA's own ~4,800 figure assumes.

The true between-asset correlation *of the paired admission effect* cannot be
measured without the admission outcomes CC exists to decide whether to acquire.
**No single scalar is forced.** All three sealed scenarios are reported and the
verdict reads the residual as primary.

**CC-7 supersedes the middle of that bracket.** The review established that the
residual measurement cannot report a dependence *level* at all (§11, §21.2), so
"the closest strategy-outcome-independent proxy" is a weaker description than the
pre-registration gives it. The sealed scenario is honoured as sealed — changing
what it computes after seeing its result is what a seal prevents — and the
limitation is recorded beside it rather than papered over.

**FACT.** Nothing in the dependence measurement reads a strategy outcome.
Correlations are between price returns, which exist whether or not the strategy
ever ran.

---

## 12. Admission density

**MEASUREMENT.** Milestone CA published admission counts for three **disjoint**
samples over 36 distinct symbols, reproduced here from sealed constants:

| Sample | Admissions | Symbols | Years | Per symbol-year |
|---|---:|---:|---:|---:|
| development | 155 | 15 | 2.000 | **5.163** |
| validation | 91 | 15 | 1.166 | **5.202** |
| holdout | 234 | 21 | 2.166 | **5.145** |
| **Pooled** | **480** | — | **93.0 symbol-years** | **5.1616** |

**INTERPRETATION.** The three agree to within **1.1 %** — across two disjoint time
periods and two disjoint symbol sets, one of which (the holdout) CA recorded as
*materially less liquid* (median 24h quote volume ~0.7M against ~18.8M). Density
is remarkably stable and does not fall with liquidity. The ~5.2 divisor behind
CB's 467 is **well supported**, and if anything is the least uncertain input in
this milestone.

**LIMITATION (CC-2).** CA published per-*sample* counts, not per-*symbol* ones, so
admission concentration cannot be read from CA's publication and is **NOT
MEASURED** here. The brief asks specifically whether a tiny subset produces most
admissions; CC cannot answer that from published data.

**FACT — what was not run, and why.** CC seals a 12-asset subsample
(`DENSITY_SUBSAMPLE_SIZE`, seed = SHA-256 of the pre-registration id) for a fresh
production replay. **That replay was not executed in this session.** A single
symbol's two-year replay through the production multi-timeframe fact path costs
roughly five minutes; twelve assets is about an hour of wall clock, and it was not
affordable alongside the rest of the milestone. `count_admissions` is implemented,
tested for its production-faithfulness (it uses `capture_for_window` under
`BASELINE_VARIANT` and supplies no override — asserted by
`test_the_admission_density_measurement_uses_the_production_variant`), and is
ready to run.

**INTERPRETATION.** This is stated as a gap rather than papered over. It matters
less than it would otherwise, because the three existing measurements already span
two symbol sets and two periods and agree to 1.1 % — but it is a gap, and §20
records it as the first recommended follow-up.

---

## 13. The information-growth curve

**PROJECTION.** Every row below is model output except where marked. The chain is
CB's arithmetic plus one factor CC adds and names:

```
h = z * sigma * sqrt((rho_within + (1 - rho_within)/m) / N)  *  sqrt(1 + (N-1) r)
    \___________________ Milestone CB's formula ____________/   \__ CC's term __/
```

`sigma` = 3.5432, inverted from CA's published interval bounds by CB's
`observation_dispersion_from_half_width`. `rho_within` is held at **0.0** — the
most favourable value — so **every requirement below is a lower bound**.

**Independent scenario (r = 0):**

| Assets | Kind | K_eff | Admissions | Half-width | Resolves +0.10? |
|---:|---|---:|---:|---:|---|
| 15 | observed | 15.00 | 154 | **0.5596** | no |
| 30 | observed | 30.00 | 309 | 0.3951 | no |
| 50 | projected | 50.00 | 515 | 0.3060 | no |
| 75 | projected | 75.00 | 773 | 0.2498 | no |
| 100 | projected | 100.00 | 1,031 | 0.2163 | no |
| 150 | projected | 150.00 | 1,546 | 0.1766 | no |
| 200 | projected | 200.00 | 2,062 | 0.1529 | no |
| 300 | projected | 300.00 | 3,093 | 0.1249 | no |
| 400 | projected | 400.00 | 4,124 | 0.1081 | no |
| 467 | projected | 467.00 | 4,815 | 0.1001 | no |
| 500 | projected | 500.00 | 5,155 | 0.0967 | **yes** |

**FACT — an internal validation worth stating.** At 15 assets the model projects a
half-width of **0.5596 ATR**. Milestone CA *measured* **0.5578 ATR** on 15 symbols
by symbol-clustered bootstrap. The model reproduces the observed value to within
**0.3 %** at the one point where an observation exists.

**PROJECTION — raw scenario (r = 0.6041):**

| Assets | K_eff | Admissions | Half-width |
|---:|---:|---:|---:|
| 15 | 1.59 | 154 | 1.7210 |
| 100 | 1.64 | 1,031 | 1.6865 |
| 467 | 1.65 | 4,815 | 1.6821 |
| 500 | 1.65 | 5,155 | 1.6821 |
| ∞ | **1.655** | ∞ | **→ 1.6821** |

**INTERPRETATION — the saturation mechanism.** Under any r > 0 the effective
cluster count saturates at 1/r while projected admissions grow linearly in N, so
the two N's cancel and the half-width approaches

```
h → z * sigma * sqrt(r / (years_per_asset * density))
```

At r = 0.6041 that floor is **1.6821 ATR — seventeen times the +0.10 bar** — and
**no universe size whatever goes below it.** `requirement_for_effect` reports this
as `reachable=False` with a reason, which is a finding, not a timeout.

---

## 14. Effect-size alternatives

**PROJECTION.** The +0.10 ATR target remains CA's question and is **not**
reopened. The larger members answer a separate question: *what could this universe
honestly test?*

| Effect | Independent | Residual | Raw |
|---|---:|---:|---|
| **0.10 (primary)** | **468 assets / 4,825 adm** | **468 / 4,825** | unreachable at any size |
| 0.20 | 117 / 1,206 | 117 / 1,206 | unreachable |
| 0.30 | 52 / 536 | 52 / 536 | unreachable |
| 0.50 | 19 / 195 | 19 / 195 | unreachable |

**INTERPRETATION.** The measured 38-asset universe sits between the 0.30 (52) and
0.50 (19) requirements. **The question FMITS can honestly ask today is roughly
"is the admission effect at least 0.3–0.5 ATR?"** — three to five times the cost
of trading. It cannot ask CA's question. Reading this as licence to restate CA's
hypothesis at 0.30 ATR would be exactly the failure CC-6 forbids.

---

## 15. Universe ordering, and why it is not a selection

**FACT.** Assets enter the growth curve in **descending usable history, ties
broken by ascending asset id**. Both keys are design properties read from bar
timestamps and tickers. Expectancy, win rate, admission performance and every
other realised result are forbidden as ordering keys.

**FACT.** `ordering_is_outcome_free` runs the ordering from both the forward and
reversed input order and asserts the output is identical — and
`test_the_control_FIRES_on_an_order_dependent_rule` substitutes an
arrival-ordered rule and asserts the control catches it. The control is
non-vacuous.

---

## 16. No-lookahead and holdout safety

**FACT.** Four controls, each paired with a deliberately broken input it is shown
to catch.

| Claim | Control | Non-vacuity check |
|---|---|---|
| No outcome informs eligibility | `outcome_free_decision` triples every price and asserts the decision and every structural coverage figure are unchanged | A price-level-reading rule is injected and the control fires |
| No outcome informs ordering | `ordering_is_outcome_free` | An arrival-ordered rule is injected and the control fires |
| The capture is what was measured | `SeriesCache.get` re-digests every entry | An edited bar is injected and raises "has been edited" |
| The assessment reproduces offline | study re-run with a transport that raises on every candle call | A cache miss with `allow_fetch=False` raises rather than refetching |

**FACT — the holdout was never opened.** CC reads **no realised outcome of any
kind**, from any sample. Every eligibility rule consumes a timestamp, a bar count,
a price or a volume; dependence consumes price returns; ordering consumes history
and a ticker. Historical *availability* was inspected — a design property — and
holdout *outcomes* were not, because there is no code path in `fmis.universe` that
could read one.

**FACT.** `test_no_production_module_imports_this_package` asserts that only
`pipeline/cli.py` imports `fmis.universe` anywhere in `src/`.

---

## 17. Crypto-only feasibility and the cross-asset implication

**POST-HOC ROBUSTNESS ANALYSIS — labelled as such, and not pre-registered.**

The sealed funnel measures one two-year window. That leaves an obvious objection:
*maybe a different window does better.* So a strictly more generous bound was
computed **after** seeing the `INFEASIBLE` result — asking how many asset-years
this provider has **ever** produced under the same sealed rules, across its entire
history rather than the sealed window.

It is admissible after the fact for one reason, asserted in code
(`HorizonCeiling.is_post_hoc` cannot be set `False`): **it can only move the answer
toward `FEASIBLE`.** It is a search for evidence *against* the milestone's own
conclusion.

**MEASUREMENT.**

| Quantity | Value |
|---|---:|
| Candidate economic assets | 659 |
| Ever paid the warm-up and cleared 1 usable year | **106** |
| Total usable asset-years, all history | **211.1** |
| Projected admissions at 5.1616/asset-year | **1,089** |
| CB's required admissions | 4,823 |
| CB's required clusters | 467 |
| **Reaches the requirement** | **No** |
| Admission shortfall | 3,734 (4.4× short) |
| Cluster shortfall | 361 (4.4× short) |

**INTERPRETATION — crypto alone is insufficient, and not marginally.** Using every
year Binance spot has ever produced, on every economic asset that has ever paid
the production warm-up, the provider yields about **1,089 matched admissions
across 106 clusters** against a requirement of **4,823 across 467**. The
`INFEASIBLE` verdict survives the most favourable universe that can be
constructed.

**INTERPRETATION — the cross-asset implication.** Reaching 467 clusters requires
roughly 360 more economic assets with ≥ 4.79 years of pre-window history plus ≥ 1
year of measurement. That population does not exist in crypto: crypto is younger
than the warm-up requirement. It does exist in equities (thousands of listings with
decades of history), and in FX, commodities and rates.

**But this is not a recommendation to add providers**, and CC deliberately
implemented none. Two questions come first:

1. **Is the admission rule economically comparable across asset classes?** The
   +0.10 ATR bar is derived from a *crypto* round-trip cost at a *crypto* median
   ATR/close of 0.0202. Equity ATR/close is roughly an order of magnitude smaller,
   so +0.10 ATR is a different economic claim there. Pooling without settling this
   would put two units under one inequality — the error `MetricUnit` exists to
   refuse.
2. **Is the warm-up itself the right requirement?** Which leads to §18.

---

## 18. The finding the brief asked for: was 467 the right mental model?

**INTERPRETATION.** No, and this is the most useful thing CC found.

CB's 467 treats cluster count as the scarce resource. CC's funnel shows the scarce
resource is something else: **598 of 622 depth exclusions are the 1,750-day
warm-up**, and that warm-up is not a property of the market. It is a property of
FMITS's decision to make the weekly timeframe the context role at a 250-candle
analysis window.

The arithmetic is stark. Of 660 economic assets, **526 are excluded because
`first_bar + 1750 days` lands at or after the window end.** Zero are excluded for
data quality. Zero for liquidity. The provider offers 660 usable economic
exposures; FMITS's own analysis window is what reduces them to 38.

**This is not a claim that the warm-up is wrong.** A 250-candle weekly window may
well be exactly what the strategy needs, and CC changed nothing. It is a claim
that *the binding constraint on FMITS's ability to test itself is currently
internal, not external* — and that is a different problem from "buy more data",
with different and much cheaper solutions available.

**Explicitly NOT claimed:** that reducing the warm-up would preserve the strategy's
behaviour. Shortening the context window changes what the context role sees, which
changes admissions, which changes the very effect under test. That is a research
question, not a fix, and it is out of CC's scope.

---

## 19. Verification performed

| Check | Result |
|---|---|
| Focused CC tests, whole suite | **432 passed** (all six `test_universe_*.py`; 393 before the review, +26 review regressions) |
| Provider tests | **98 passed** (`test_providers_binance.py`) |
| Architecture + boundary guards | **763 passed** (CC, CB, swing-lab, trade-capture, multi-timeframe) |
| CB / CA / BZ / BY / BX / BW regressions | **2,277 passed** |
| `research_design` regression | passed within the full suite |
| CA / BZ / BY / BX / BW regressions | passed within the full suite |
| **Full repository suite** (`-W error`) | **13,384 passed**, exit 0 (baseline 12,952; +432) |
| Statement + branch coverage, CC scope | **90 %** (1,859 stmts, 556 branches) |
| Hostile probes | 55, all passing |
| Review regressions | 39, one or more per confirmed finding (32 review + 7 release audit) |
| Mutation of sealed fields | 23 mutations, all move the digest; 1 asserts formatting does not |
| Mutation of material RULES | **10 probes, 10 killed, 0 survivors** (§20) |
| Digest determinism across `PYTHONHASHSEED` | 4 seeds, all agree |
| Offline reproduction, network fatal | passes; no candle refetched |
| No-lookahead controls | 4, each with a non-vacuity check |
| `git diff --check` | clean |
| Credential scan | no `api_key`, `secret`, `signature`, `hmac`, `/order`, `wss://` anywhere in `fmis.universe` |

**Coverage by module:** `preregistration` 99 % · `render` 97 % · `growth` 93 % ·
`dependence` 91 % · `eligibility` 91 % · `horizon` 90 % · `study` 89 % ·
`controls` 88 % · `verdict` 88 % · `models` 88 % · `identity` 87 % · `artifact`
87 % · `density` 84 % · `capture` 81 % · `providers.binance` 91 %.

**Uncovered, and why:** the residue is defensive validation branches and
`density.count_admissions`, whose body is the production replay described in §12
as not executed.

### 19.1 Full suite

**MEASUREMENT, before the review.** `uv run python -W error -m pytest -q` →
**13,345 passed in 511.05s**, exit 0, against a 12,952 baseline.

**MEASUREMENT, after the review.** `uv run python -W error -m pytest -q` →
**13,384 passed in 516.01s**, exit 0. Against the 12,952 pre-milestone baseline,
Milestone CC adds **432 tests** and breaks none.

### 19.2 Four architecture guards fired, and were obeyed

**FACT.** The first full-suite run after implementation produced **four failures**,
every one a genuine boundary violation by the new package. None was a false alarm
and none was suppressed. Each was widened following the convention the repository
already uses — an explicit entry with its reason recorded in the test — and in each
case the property the guard actually protects was checked to be unaffected.

| Guard | Violation | Resolution |
|---|---|---|
| `test_no_engine_imports_the_multi_timeframe_root` | `universe/eligibility.py` reads `DEFAULT_TIMEFRAMES` | `universe` added as a sixth application-layer root. Direction unchanged: no engine reaches upward |
| `test_only_the_cli_and_the_laboratory_import_this_package` | `universe/growth.py` imports CB | `universe/growth.py` admitted as CB's **second adapter** — which is what CB was built for. Nothing in CB imports `fmis.universe` |
| `test_only_the_cli_imports_the_laboratory` | three `universe/` modules import `swing_lab` | Exactly those three admitted, by name. `fmis.universe` is a research package at the same tier, not an engine |
| `test_the_cli_reaches_neither_the_domain_nor_the_store` | `cli.py` imports `fmis.universe` | `fmis.universe` added to the CLI's permitted prefixes, on the footing BW/CB/BT already established |

**FACT.** The allowlist for the swing-laboratory guard was first written with four
modules and then **tightened to the exact three** that import it, after checking
which actually do. A `<=` assertion tolerates an over-broad list silently; it was
narrowed rather than left convenient.

**FACT — no safety guard was weakened.** `test_no_private_or_authenticated_endpoints`
is untouched. Every widening is an entry naming a research package that no engine
can reach, and the transitive property still holds:
`test_no_production_module_imports_this_package` asserts only `pipeline/cli.py`
imports `fmis.universe` anywhere in `src/`.

---

## 20. Mutation testing: survivors investigated

**FACT.** Every mutation of a sealed field moved the digest. Beyond the seal, the
scientifically material rules were mutated and each produced a failing test:

| Mutated | Detected by |
|---|---|
| Eligibility thresholds (missing fraction, gap, liquidity, min years) | seal mutations + funnel tests |
| Economic identity sets | `test_mutating_the_identity_rules_moves_the_digest` + collapse tests |
| History requirement | `test_the_derived_warmup_is_seventeen_fifty_days` |
| Dependence handling | `test_a_missing_scenario_measurement_is_never_read_as_zero` |
| Ordering | `test_the_control_FIRES_on_an_order_dependent_rule` |
| Meaningful-effect values | `test_the_primary_effect_is_CA_s_own_constant` |
| CB integration | `test_CB_s_published_requirement_reproduces_exactly` |
| Verdict boundaries | `test_falling_short_of_the_INDEPENDENT_case_is_INFEASIBLE` |
| Survivorship classification | both directions refused by `SurvivorshipReading` |
| Artifact digest | `test_editing_a_measured_number_breaks_the_digest` |

### 20.1 Rule-level mutation, after the review

**MEASUREMENT.** Ten probes over the scientifically material rules, each reverting
one rule to a value that should change an answer. **All ten killed; zero
survivors.**

| Mutated rule | Result |
|---|---|
| `WITHIN_CLUSTER_CORRELATION` 0.0 → 0.5 | killed |
| `DESIGN_SAMPLE` `development` → `holdout` | killed |
| `MIN_OVERLAP_DAYS` 60 → 2 | killed |
| eigenvalue convergence guard disabled | killed |
| `MIN_MEASUREMENT_YEARS` 1.0 → 0.1 | killed |
| `MAX_MISSING_FRACTION` 0.02 → 0.5 | killed |
| `MIN_MEDIAN_QUOTE_VOLUME` 100,000 → 1 | killed |
| `MAX_GAP_BARS` 7 → 400 | killed |
| `WBTC → BTC` identity mapping removed | killed |
| `KNOWN_UNRECOVERABLE_PAIR` renamed | killed |

**Three of those ten survived the first run and were investigated rather than
reported as a percentage.** All three survived for the same reason: the measured
universe never exercises the branch, so only a constructed case can constrain it.

- **`MIN_OVERLAP_DAYS`** — all 703 measured pairs share the full window, so the
  threshold never binds. Closed with a constructed pair overlapping on 49 instants,
  plus its counterpart at 100 so the test is a bound rather than a wall.
- **The eigenvalue guard** — the anti-correlation test written for it lands on the
  earlier `norm <= 0` branch, so the guard proper was never reached. Closed with two
  series at `r ≈ −0.9`, whose uniform start converges to `1 + r ≈ 0.1`: below 1, and
  therefore impossible for a correlation matrix's dominant eigenvalue.
- **`KNOWN_UNRECOVERABLE_PAIR`** — nothing pinned that the demonstrated survivorship
  gap is `HSRUSDT`, which is the fact that makes the gap *demonstrated* rather than
  suspected. Closed.

### 20.2 The pre-review survivor

**One survivor investigated and fixed before the review.** The first implementation
passed the *effective* cluster count as both `clusters` and the divisor for
observations-per-cluster. Because `rho_within = 0` makes CB's structural factor
`1/m`, the two cancelled and **the between-asset correlation had no effect on the
half-width at all** — the dependence measurement was decorative. It was caught by
`test_a_saturating_correlation_makes_the_effect_unreachable_at_any_size` failing,
traced to the derivation, and fixed by applying `sqrt(1 + (N−1)r)` to CB's *output*
(§13). The corrected model is now checked against its own closed-form floor and
against CA's measured half-width.

---

## 21. Independent code review

**PERFORMED, 2026-08-29 / 2026-09-03.** Three independent reviewers attacked the
milestone in parallel, each with a narrower scope than the two earlier attempts
that died mid-analysis (one on an API error, one on a session limit). Splitting
the brief's seventeen attack areas three ways was a deliberate response to those
failures: a single reviewer needing the whole package in context is the thing that
kept running out.

| Reviewer | Attacked |
|---|---|
| **A — statistical** | pseudoreplication · correlation and dependence assumptions · ICC methodology · CB integration and power calculations · observed vs projected |
| **B — bias and leakage** | survivorship · economic identity and duplicate exposure · historical liquidity · holdout leakage · outcome-based filtering · universe ordering · admission-density concentration · no-lookahead guarantees |
| **C — engineering and claims** | artifact reproducibility and provenance · provider mutability · verdict boundaries · overclaiming · vacuous tests · weakened guards |

**No reviewer finding was accepted on assertion.** Every one was reproduced
independently before disposition, and two were **rejected with evidence** — one of
them a finding that agreed with the report and was wrong to.

### 21.1 Findings and dispositions

| # | Finding | Severity | Disposition |
|---|---|---|---|
| A-1 | `correlation_for("residual")` returns the raw residual mean, not the artefact-corrected excess its own module documents at length | MAJOR | **Confirmed as a documentation defect; the proposed code change REJECTED.** See §21.2 |
| A-2 | `_leading_eigenvalue_share` can silently return a subdominant eigenvalue when the leading eigenvector is orthogonal to the uniform start | MAJOR | **Confirmed. Fixed** — a converged value below 1 is now refused |
| A-3 | `int()` truncation of projected admissions floors rather than rounds | MINOR | **Confirmed, no change.** Conservative direction; noted |
| A-4 | Residual and independent scenarios are numerically identical in this run, so they bracket nothing | MAJOR (scope) | **Confirmed, and deeper than reported.** See §21.2 |
| A-7 | The claim "`rho_within = 0` is the most favourable value, so every requirement is a lower bound" is **true** | — | **REJECTED.** The reviewer held `sigma` fixed; it is inverted under the same `rho`. See §21.3 |
| B-1 | `offline_reproduction` is defined and exported but never called by any test | MAJOR | **Confirmed. Fixed** — now exercised, with a non-vacuity case |
| B-2 | `reads_no_holdout_outcome`, named in the module docstring as one of four checked claims, **does not exist** | MAJOR | **Confirmed. Fixed** — implemented, with four tests |
| B-3 | `ordering_is_outcome_free` cannot detect an outcome-dependent ordering | MAJOR | **Confirmed by demonstration. Fixed** — see §21.4 |
| B-6 | `published_densities()` reads the holdout's admission counts | — | **Confirmed as fact, accepted as sound.** An admission count is a signal-time decision count, not a forward outcome. Now automated by B-2's control |
| B-7 | `render.py` prints `largest single share of admissions` with no caveat that it is across three samples, not assets | MINOR | **Confirmed. Fixed** — the renderer now prints the CC-2 caveat beside the number |
| C-1 | The report's "371 passed" is false; an architecture guard fails | CRITICAL | **Confirmed at the moment it was measured, and self-inflicted.** See §21.5 |
| C-4 | The horizon ceiling silently skips an asset whose tail probe fails (656 → 655 candidates) | MINOR | **Confirmed, no change.** Skipping shrinks a bound that may only shrink; documented |
| C-5 | Discovery is not frozen, so "offline reproduction" is narrower than a reader might assume | MAJOR (reporting) | **Confirmed. Fixed** — `OFFLINE_CLAIM` now states it in the artifact itself |
| C-7 | "asserted over the whole enum by a hostile test" oversells a property that is `False` by construction | MINOR | **Confirmed, wording only** |
| — | **Own pass:** `ca_observation_dispersion` accepted *any* sample, including the protected holdout | MAJOR | **Confirmed. Fixed** — see §21.6 |
| — | **Own pass:** the sealed residual scenario cannot measure residual dependence *at all* | MAJOR | **Confirmed by derivation and simulation.** See §21.2 |

Reviewers additionally **verified as correct**, independently of the author: the
central half-width formula and its `K_eff` equivalence; the saturation limit; the
`−1/(K−1)` demeaning artefact; monotonicity of the bisection search; the economic
identity of all 38 eligible assets (including that TFUEL/THETA and ONG/ONT are
genuinely distinct instruments); survivorship classification's inability to
self-flatter; window-scoped liquidity; every headline number against the artifact;
the warm-up attribution (then 594 of 618, now 598 of 622 after the
discovery drift); digest and gzip determinism;
`decide_feasibility`'s branch ordering; all five guard widenings as widenings
rather than weakenings; and the absence of vacuous tests in the new suites.

### 21.2 A-1 and A-4 — the most consequential finding, and why the fix was refused

Reviewer A observed that `dependence.py` documents at length that the residual
correlation "must be read against `demeaning_artefact = −1/(K−1)`, NOT against
zero", and then `correlation_for("residual")` reads it against zero. Reproduced:
the code uses `max(0, −0.0248) = 0.0` where the documented reading is the excess,
`+0.0023`.

The consequence is **material**: at `r = 0.0023` the effective cluster count
saturates at 442 and the half-width floor is **0.1029 ATR — above the +0.10 bar**,
making the effect *unreachable at any universe size* rather than needing 468
assets.

**The proposed code change was rejected.** The pre-registration defines the
residual scenario as *"the measured mean pairwise correlation of daily log returns
AFTER the equal-weight market factor is removed"* — which is the field the code
uses. Substituting the excess would change what a **sealed** scenario computes
after seeing its result, which is exactly what a seal exists to prevent. The
docstring, not the code, was wrong; the docstring was corrected.

**Re-deriving it produced something more important.** For `K` series
`x_i = f + e_i` whose idiosyncratic parts are equicorrelated at *any* level
`rho_e`, cross-sectional demeaning gives residuals with pairwise correlation
**exactly `−1/(K−1)`**. Proved algebraically and confirmed by simulation at
`rho_e` of 0.0, 0.2, 0.5 and 0.8 — all four return an excess of `0.00000`.

So the sealed residual scenario is **structurally incapable of measuring the level
of residual dependence.** It measures departure from exchangeability. The
pre-registration's claim that the three scenarios "bracket the answer" is
therefore wrong: the usable bracket is `[independent = 0, raw = 0.604]` with **no
informative middle**, and A-4's observation that the two scenarios coincide is a
consequence of the method rather than a coincidence of this dataset.

This is recorded as post-review limitations **CC-7** and **CC-8**. They are
deliberately **not** added to `CC_LIMITATIONS`: retro-fitting a seal with what was
learned after sealing would destroy the only property a seal has. They live in
`fmis.universe.dependence.POST_REVIEW_LIMITATIONS`, are carried into the artifact
under a separate key, and are dated to the review.

**It strengthens the negative result and is reported because it was found, not
because it helps.** A residual dependence of 0.0023 — two-tenths of one per cent —
would make +0.10 ATR unreachable at any size, and CC-7 means no measurement here
can exclude it.

### 21.3 A-7 — a reviewer finding that agreed with the report, and was rejected

Reviewer A confirmed the report's claim that holding the within-cluster
correlation at zero is "the most favourable value", making every requirement a
lower bound, reasoning that `rho + (1−rho)/m` is non-decreasing in `rho`.

**That holds `sigma` fixed, and `sigma` is not fixed** — it is inverted from CA's
published interval under the *same* `rho`, so raising `rho` lowers `sigma` and the
two effects very nearly cancel. Measured:

| `rho_within` | 0.0 | 0.05 | 0.10 | 0.20 | 0.50 | 0.80 |
|---|---:|---:|---:|---:|---:|---:|
| required assets | **468** | 468 | 468 | 467 | 467 | 467 |

The requirement moves by **one asset** across the whole range, and in the
direction *opposite* to the claim: `rho = 0` demands very slightly **more** data.

The cancellation is near-exact for a reason worth recording: CA's
observations-per-cluster is `155/15 = 10.333`, and CC's projected
admissions-per-asset is `years × density = 10.311`. The two structural factors
are evaluated at almost the same `m` and divide out.

The honest statement is therefore not *"this is a lower bound"* but **"this
requirement is robust to the one dependence parameter nobody can measure"** —
which is a better result. The docstring, the module constant and the runtime note
were all corrected, and
`test_the_requirement_is_robust_to_the_within_cluster_correlation` pins the table
above. `test_zero_is_NOT_the_most_favourable_value` pins the discarded claim as
false so it cannot be reinstated.

### 21.4 B-3 — an ordering control that could not do its job

The control ran the ordering forward and reversed and compared. That is worthless
for the property it claimed: **sorting a fixed multiset by any deterministic
per-item key is invariant to arrival order.** Demonstrated by substituting an
ordering sorted by a fabricated expectancy — `['AAA','CCC','BBB']` against the
sealed `['BBB','CCC','AAA']` — which the control passed unchanged.

Rewritten to check the property itself: the ordering must **equal the sealed key
ordering**, recomputed independently from `(−usable_years, asset_id)`. Perturbation
alone cannot catch a rule that looks an outcome up *by asset id*, because the id is
a sealed key and may not be perturbed; recomputing the specification catches any
deviation whatever its source. `test_the_control_FIRES_on_an_expectancy_ordering`
is the regression, and a second case catches a rule keyed on a non-key design
field.

### 21.5 C-1 — a guard that fired on the reviewer's own snapshot

Reviewer C found `test_a_measurement_module_touches_no_filesystem[controls.py]`
failing and correctly called the report's test counts stale. The cause was
**this review's own in-flight fix**: implementing B-2's missing control had
introduced `from pathlib import Path` into `controls.py`, which the package's
"no measurement module touches the filesystem" guard refuses.

The guard was **obeyed, not widened.** `reads_no_holdout_outcome` now takes a
mapping of module name to source text and parses what it is given; the test does
the directory reading, where reading files is ordinary. A control that had to
weaken one safety property in order to assert another would not have been worth
having.

### 21.6 Own pass — a latent path to spending the holdout

`ca_observation_dispersion` took a `sample` argument defaulting to
`"development"`, and would happily invert the per-observation dispersion from the
**holdout's** realised interval if asked. No call site did — but Milestone BY
seals `SampleRole.HOLDOUT.may_inform_design = False` and Milestone CB's
`assess_research_design` refuses a holdout-sourced width by name, and CC had no
such refusal.

Fixed: any sample but `development` is refused with a message naming why.
`test_a_protected_sample_is_refused_by_name` covers both `holdout` and
`validation`. An AST control now additionally asserts that no module in
`fmis.universe` reads CA's interval bounds or names a protected sample in code.

### 21.7 What the review did not change

**No measured figure moved.** The regenerated study was compared field by field
against the pre-review artifact: the funnel, every dependence figure, the density,
the growth curve, the effect grid, the survivorship reading, the horizon ceiling
and the verdict are **bit-identical**. The only payload difference is the added
`post_review_limitations` key. The verdict remains **`INFEASIBLE`**, binding
constraint `cluster_count`, and the pre-registration seal is unmoved at
`ef6f3950…`.

---

## 21.8 Release audit, 2026-09-03

**A pre-commit release audit re-verified the final tree** and found **five** further
items. All are fixed; none changed a measured number or the verdict.

| # | Finding | Disposition |
|---|---|---|
| AUDIT-1 | §11.1 still presented the pre-registered "residual is the closest proxy" reading as current, though CC-7 supersedes it | **Fixed** — marked as sealed-but-superseded |
| AUDIT-2 | `+0.0023` was phrased in places as if it were a measured *between-asset correlation*; it is the measured **excess over the artefact**, which CC-7 says cannot identify a dependence level | **Fixed** — restated as a sensitivity input in the report, in CC-8 and in §26 |
| AUDIT-3 | The "0.0023 makes it unreachable" claim was presented as settled. Its margin over break-even (`r = 0.00214`) is **5.9 %**, and it **flips** under ±10 % density/years or CB-6's own ±30 % interval scatter | **Fixed** — the report now states the break-even, the margin and the flip table, and asserts only the CONDITIONAL claim. Seven regressions pin the marginality |
| AUDIT-4 | §8 listed "the survivorship reading" among figures bit-identical across the two runs. It was **not** — halted moved 2,287 → 2,290 and halted-and-eligible 3 → 4, because ICX was delisted | **Fixed** — survivorship is now called out as the expected exception, cross-referenced to §10 |
| AUDIT-5 | A stale "3,607 removals" survived the funnel update (correct value 3,611) | **Fixed** |

**AUDIT-3 is the one that mattered.** Left unfixed, the report would have implied
that CC's own measurement demonstrates unreachability at any universe size. It does
not: the margin is thin and does not survive the input scatter CB-6 already
declares. The supported claim is that a correlation of *order* 0.002 would be
decisive and that **CC cannot exclude one** — which still strengthens the
`INFEASIBLE` verdict, but for a reason that survives scrutiny.

The audit also re-verified mechanically that **all 26 headline numeric claims trace
to the artifact on disk** (`60a6a11…`), that the funnel reconciles
(3,649 − 3,611 = 38, exclusion reasons summing to 3,611), that both replaced guard
assertions are **widenings with their shape preserved** (`==` stays `==`, `<=` stays
`<=` over exactly the three modules that import the laboratory), and that no
assertion was deleted anywhere in `tests/`.

---

## 22. Assumptions

1. **ASSUMPTION.** The within-cluster correlation is 0.0. Most favourable value;
   makes every requirement a lower bound.
2. **ASSUMPTION.** CA's admission density (~5.16/asset-year) holds across the
   eligible universe. Supported by three disjoint samples agreeing to 1.1 %, not
   re-measured on CC's universe (CC-2).
3. **ASSUMPTION.** The per-observation dispersion inverted from CA's published
   interval characterises a larger universe. Inherited from CB-1.
4. **ASSUMPTION.** Residual return correlation proxies the between-asset
   correlation of the paired admission effect (CC-1).
5. **ASSUMPTION.** A normal approximation to the sampling distribution of a
   clustered mean. CB's, inherited.
6. **ASSUMPTION.** `close × volume` proxies traded notional (CC-4).
7. **ASSUMPTION.** USDT-quoted pairs are the comparable universe, because every
   FMITS sample to date is USDT-quoted and the +0.10 bar is a USDT cost.

## 23. Limitations

**Sealed limitations.** CC-1 through CC-6 are carried in the code
(`CC_LIMITATIONS`), printed by the CLI and stored in the artifact. Summarised: the
dependence proxy is not the estimand · admission density was not re-measured on
CC's universe · survivorship retention is incomplete and its gap is unmeasurable ·
liquidity is a volume proxy, not a book · eligibility is assessed at daily
resolution · the +0.10 bar is CA's and is not reopened.

**Post-review limitations.** CC-7, CC-8 and CC-9 were established by the
independent review, **after** the pre-registration was sealed. They are carried in
`fmis.universe.dependence.POST_REVIEW_LIMITATIONS` and in the artifact under a
separate key — deliberately **not** merged into `CC_LIMITATIONS`, because
retro-fitting a seal with what was learned later would destroy the only property a
seal has.

- **CC-7 — the sealed residual scenario cannot measure residual dependence.**
  Cross-sectional demeaning removes any exchangeable common component exactly, so
  the measured residual correlation is `−1/(K−1)` whatever the true residual
  dependence is. The three scenarios do not bracket the answer; the usable bracket
  is `[independent = 0, raw = 0.604]` with no informative middle.
- **CC-8 — a very small residual dependence would be decisive and cannot be ruled
  out.** A between-asset correlation of 0.0023 puts the half-width floor at 0.1029
  ATR, making +0.10 unreachable at any universe size. CC-7 means no measurement
  here can exclude it. This strengthens the negative result.
- **CC-9 — the leading-eigenvalue share is guarded, not universal.** Power
  iteration from a uniform start is sound here because all 703 measured pairwise
  correlations are non-negative; a converged value below 1 is now refused as
  impossible for a correlation matrix.

**Further limitations recorded honestly rather than closed.**

- The sealed 12-asset admission-density replay was **not executed** (§12).
- **Discovery is not frozen** (§21.1 C-5). The capture holds candles, not the
  `exchangeInfo` response, so an offline reproduction proves the funnel and
  everything downstream is a deterministic function of a symbol list plus frozen
  bars — it does not independently re-establish the discovered instrument count.
- **The artifact was regenerated on a later discovery date.** The 2026-08-28
  artifact was deleted in error while re-persisting after the review, and the
  discovery response it held could not be recovered from the candle capture. The
  replacement is a fresh 2026-09-03 discovery. Every measured figure downstream of
  the funnel is bit-identical; the two input counts that moved are recorded in §8.

---

## 24. Artifacts, changed files, and git state

**Artifacts.** Layered, as the brief requires, because one layer cannot honestly
make both claims:

| Layer | File | Size | Digest |
|---|---|---:|---|
| A — raw capture | `reports/artifacts/0039_cc_series_capture.json.gz` | 5.5 MB | 1,974 series, each self-digested |
| B — derived study | `reports/artifacts/0039_cc_universe_feasibility.json.gz` | 78 KB | `60a6a11381f060777038f2950511935ba6a6507a1129d600aff355a35ca8b16e` |

**Layer B has been written three times, and the lineage is recorded in its own
manifest rather than only here.**

1. `8860bae7…` — the pre-review artifact. **Deleted in error** during the
   post-review re-persist. The candle capture holds bars, not the `exchangeInfo`
   response, so its discovery could not be recovered. **It is gone and this report
   does not pretend otherwise**; no figure below is sourced from it.
2. `4315645…` — regenerated on a fresh **2026-09-03** discovery, which is where the
   3,649 / 660 counts come from.
3. `60a6a11…` — **the artifact on disk**, rewritten by the release audit after
   limitation CC-8 was restated as a conditional claim (§11, §21.2). Every field
   was compared against (2): all identical except the discovery timestamp and the
   intended CC-8 text. The provider did not drift further; the capture is unchanged
   at 1,974 series.

Each manifest carries `supersedes_content_digest`, so the chain is auditable from
the files rather than from this paragraph. Layer A grew by 8 series between (1) and
(2) — the four new listings' listing and last-bar probes.

Layer B carries the SHA-256 of every series behind it and an `OFFLINE_CLAIM`
string stating exactly what it can and cannot reproduce alone — **it does not
claim raw-input reproducibility without layer A**, which is the BZ-D2 lesson.

**New files.**

```
src/fmis/universe/{__init__,artifact,capture,controls,density,dependence,
                   eligibility,growth,horizon,identity,models,preregistration,
                   render,study,verdict}.py          15 modules
tests/test_universe_{preregistration,measurement,hostile,
                     architecture,controls,study}.py  6 suites, 432 tests
reports/0039_2026-08-28_UNIVERSE_FEASIBILITY_AND_INFORMATION_EXPANSION.md
reports/artifacts/0039_cc_series_capture.json.gz
reports/artifacts/0039_cc_universe_feasibility.json.gz
```

**Modified by the independent review** (all inside CC's own scope):

```
src/fmis/universe/controls.py     ordering control rewritten; reads_no_holdout_outcome added
src/fmis/universe/dependence.py   eigenvalue guard; POST_REVIEW_LIMITATIONS; docs corrected
src/fmis/universe/growth.py       holdout refusal; the rho_within claim corrected
src/fmis/universe/artifact.py     OFFLINE_CLAIM discloses that discovery is not frozen
src/fmis/universe/render.py       concentration caveat (CC-2) printed beside the number
src/fmis/universe/study.py        carries POST_REVIEW_LIMITATIONS into the artifact
tests/test_universe_controls.py     +10 regressions
tests/test_universe_measurement.py  +16 regressions
tests/test_universe_study.py        two assertions strengthened
```

**Modified files.**

```
src/fmis/providers/binance.py            exchangeInfo discovery (additive)
src/fmis/pipeline/cli.py                 `fmits research universe` (additive)
tests/test_providers_binance.py          endpoint guard widened to an exact two-set
tests/test_multi_timeframe.py            application-layer roots + `universe`
tests/test_research_design_architecture.py  CB adapter allowlist + `universe/growth.py`
tests/test_swing_lab_architecture.py     lab importers + the exact three `universe/` modules
tests/test_trade_capture_architecture.py CLI permitted prefixes + `fmis.universe`
reports/README.md                        index row + next-number bump
docs/AI_HANDOFF/CURRENT_STATE.md         milestone record
FMITS_PRODUCT_BACKLOG.md                 status
```

The four architecture-guard files are modified **only** to add a named entry with
its reason (§19.2). No assertion was loosened and no safety property removed.

**Dashboard decision — recorded explicitly, as the brief requires.** **No
dashboard work was done.** The operator dashboard has no research-artifact seam
that could present a `UniverseStudy` without new architecture, and
`test_the_dashboard_depends_on_nothing_here` asserts the dashboard imports nothing
from `fmis.universe`. The dashboard's separate freshness/refresh issue was **not**
touched and was not mixed into CC.

**Git state.** Branch `main`, base `c320525`, **nothing committed, nothing
pushed.** The 16 pre-existing untracked research documents are preserved.

**Proposed commit structure** (not executed — awaiting authorization):

1. `feat(providers): add read-only Binance exchangeInfo discovery`
2. `feat(research): add universe feasibility study (Milestone CC)`
3. `feat(cli): expose fmits research universe`
4. `docs(reports): record universe feasibility study 0039`
5. `docs(product): record Milestone CC`

---

## 25. Recommended next milestone — NOT started

**CD — Warm-Up Requirement Sensitivity Study.** CC located the binding constraint
inside FMITS rather than in the market. The next question is whether the 1,750-day
warm-up is load-bearing: how many economic assets become eligible, and how the
admission rule's behaviour changes, as the context role's analysis window is
varied. That is a strategy-semantics question and must be pre-registered exactly as
CA was, because "shorten the window until the universe is big enough" is the most
obvious way to fake CC's way out of `INFEASIBLE`.

**The review added a second candidate that may deserve to go first.** CC-7
established that CC cannot measure between-asset dependence of the *estimand* at
all, and CC-8 that a correlation of 0.0023 would be decisive. Since the admission
outcomes needed to measure it directly are the very budget CC was assessing, there
is a cheap partial answer available: measure the between-asset correlation of the
**paired excursion differences** on the 38 eligible assets over the development
window only. That is a bounded replay — 38 symbols rather than 467 — and it would
replace the uninformative middle of the bracket with a measurement.

Two smaller items should accompany either: **run the sealed 12-asset density
subsample** (§12), and **freeze the discovery response into the capture** so the
offline-reproduction claim covers the funnel's input as well as its arithmetic
(§21.1 C-5).

---

## 26. Plain-language answer

> **CAN FMITS OBTAIN ENOUGH INDEPENDENT MARKET INFORMATION TO HONESTLY TEST THE
> +0.10 ATR SWING ADMISSION QUESTION?**

**No — not from crypto spot, and not for the reason anyone expected.**

The expected answer was that crypto assets move together, so 467 tickers would
never be 467 independent experiments. That turned out to be **wrong in the way
that matters**. Yes, crypto co-moves heavily — a single market factor explains
62.5 % of return variance and the average pair correlates at 0.60. But CA's effect
is a *paired within-symbol* comparison, and a paired comparison differences that
common factor away. Once it is removed, what is left is statistically
indistinguishable from independence. **Dependence was not the wall.**

The wall is much more mundane, and it is inside the product. FMITS reads 250
weekly candles to establish context. That is 1,750 days — 4.8 years — of history
an instrument must have *before* it can contribute a single measured instant. Most
crypto assets are younger than that requirement. Of 3,649 listed spot instruments,
660 are distinct economic exposures, and only **38** can pay the warm-up and still
leave a year to measure. Not one was lost to bad data. Not one to illiquidity.
**Five hundred and twenty-six were lost to being too young for FMITS's own
analysis window.**

The gap is not close. CA's question needs about **468 clusters and 4,823
admissions**. Using every year Binance spot has ever produced, on every economic
asset that has ever paid the warm-up, this provider yields about **106 clusters
and 1,089 admissions** — roughly four and a half times short on both. There is no
window, no ordering and no threshold within the sealed rules that closes it, and
the most generous bound that could be constructed was computed specifically to try.

What FMITS *can* honestly ask today is a different question: with 38 assets it can
resolve an effect of about **0.3 to 0.5 ATR** — three to five times the cost of
trading. It cannot resolve 0.10. Those are not the same question and CC does not
permit substituting one for the other.

**The independent review made this answer stronger, not weaker.** It established
that the middle of CC's dependence bracket is not a measurement at all: subtracting
a cross-sectional mean removes any shared component *exactly*, so the "residual
correlation" is pinned at `−1/(K−1)` no matter what the true residual dependence
is. CC therefore cannot rule out a between-asset correlation of order **0.002** —
and because effective clusters saturate at `1/r`, a correlation that small would put
+0.10 ATR beyond reach at **any** universe size, not merely beyond 467 assets. (The
break-even is 0.00214. The measured excess of 0.0023 sits only 5.9 % above it, so
the *conditional* claim is what this milestone supports — not a demonstration that
the measurement itself closes the door.) The review also found
a latent path by which a design parameter could have been inverted from the
protected holdout, an ordering control that could not have caught an
expectancy-sorted universe, and a safety control the code claimed but did not have.
All are fixed. **No measured number moved.**

So the honest position is this. Milestone CA's `NO_EDGE` still means what CB said
it means: *no edge visible at 155 admissions*. CC now adds that **crypto spot
cannot, even in principle, supply the data to say more than that** — while FMITS
requires 4.8 years of weekly context per instrument. The two ways forward are to
find out whether that requirement is load-bearing, or to go where instruments are
old enough to satisfy it. Both are real milestones. Neither is a strategy change,
and neither is authorized by this report.

**Nothing here approves trading of any kind.**
