# Swing Trading Readiness Audit V1

**Milestone:** BD
**Status:** Research only — audit. No production code, no ADR, no backlog edit, no changelog entry,
no `CURRENT_STATE` edit, no commit. This document is the only artifact.
**Date:** 2026-08-11
**Model:** Claude Opus 5
**Repository state read:** `main`, `HEAD` = `7ced9e2` (Milestone BC's product docs), two commits ahead
of `origin/main` (`f9ddc54`); working tree clean apart from twelve untracked research documents under
`docs/design/` and `docs/reviews/` (§5 R-14).
**Type:** Readiness review. Assesses whether FMITS is ready to support real discretionary swing trading
in the next phase. It is not a design record and produces no contract.

**The one question this document answers:** *if the owner starts using FMITS next month, what are the
remaining product risks?*

**Method.** Full read of `PROJECT_SPECIFICATION_V1.md`, `PROJECT_VISION_ADDENDUM_V1.md`, the 28 ADRs,
`FMITS_PRODUCT_BACKLOG.md`, `FMITS_PRODUCT_CHANGELOG.md`, `docs/AI_HANDOFF/CURRENT_STATE.md`, reports
0001–0013, the milestone chain AR → BC (including the six untracked research records AW–BB), the live
`src/fmis` tree, and two live executions of the shipped product against real Binance data on
2026-08-11. Prior audits are reused, not repeated; where this document restates an earlier finding it
cites it rather than re-deriving it. Where evidence does not exist, the word used is **unknown**.

---

## Table of contents

- [1. Current maturity](#1-current-maturity)
- [2. Can a human already use FMITS?](#2-can-a-human-already-use-fmits)
- [3. Missing capabilities before paper trading](#3-missing-capabilities-before-paper-trading)
- [4. Missing capabilities before real money](#4-missing-capabilities-before-real-money)
- [5. Critical product risks](#5-critical-product-risks)
- [6. Red team](#6-red-team)
- [7. Blind spots](#7-blind-spots)
- [8. Roadmap prioritization — the next five milestones](#8-roadmap-prioritization--the-next-five-milestones)
- [9. Readiness verdict](#9-readiness-verdict)
- [10. Executive summary](#10-executive-summary)

---

## 1. Current maturity

Scores are 0–10 against *what the product must be to support real discretionary swing trading*, not
against the quality of the engineering that produced them. A dimension with excellent code and no
product surface scores low here, and that is deliberate.

| # | Dimension | Score | One-line verdict |
|---|---|---|---|
| 1 | Architecture | **8 / 10** | Genuinely strong, and now heavier than the product it carries |
| 2 | Deterministic engine | **7 / 10** | Rigorous within a narrow input class; two of ten evidence families exist |
| 3 | Research infrastructure | **6 / 10** | Correct as of BC; its own prior output has not been re-derived on it |
| 4 | Backtesting | **3 / 10** | Measures level touches, not trades. No cost, no fill, no expectancy |
| 5 | Risk management | **0 / 10** | Zero lines of code. The 2 % rule exists only in a specification |
| 6 | Signal quality | **2 / 10** | Unknown, on 44 de-duplicated outcomes, before costs |
| 7 | Portfolio logic | **0 / 10** | Rendered as `Unavailable` on every page |
| 8 | Execution readiness | **0 / 10** | No order, no fill, no broker boundary, by design |
| 9 | Paper trading readiness | **1 / 10** | Nothing exists to record a simulated trade in |
| 10 | Live trading readiness | **0 / 10** | Correctly and deliberately not built |

### 1.1 Architecture — 8 / 10

**Evidence.** 28 accepted ADRs. 129 Python modules, 28,972 lines under `src/`. 4,653 tests collected
and passing (verified live for this audit). Zero import cycles, zero public-export collisions, zero
runtime dependencies beyond the standard library plus the provider client. Boundaries are enforced by
test, not by convention: `tests/test_directional_vocabulary_boundary.py` performs an AST scan proving
that `LONG`/`SHORT` vocabulary cannot appear outside `fmis.swing_setup` and `pipeline/cli.py`
(ADR-0028); `fmis.decision_context` is asserted to contain no numeric literal beyond 0 and 1;
`fmis.daily` is asserted to contain exactly one `sorted()` call so a readiness index cannot become a
ranking. Every milestone since AG has run mutation probes with SHA-256-verified source restoration.

**Why not higher.** Three things.

1. **Documentation mass now exceeds product mass in the dimension that matters.** `docs/design/`
   alone is 17,087 lines against 28,972 lines of source, and the largest single design document
   (`TRADING_DOMAIN_ARCHITECTURE_V1.md`, 2,152 lines) describes a domain with **zero implemented
   lines**. `reports/0004` §12 already recorded this shape: "Thirty milestones have built Level 4
   [technical] exclusively."
2. **The architecture's own next step is blocked on decisions the architecture named for itself.**
   AP-D1 (money types) and AP-D2 (capture contract and migration guarantee) are named as blocking by
   `FMITS_PRODUCT_BACKLOG.md` §6 item 1 and §10, and neither is an accepted ADR. The backlog's own
   text: AP-D2 "must precede the first written trade."
3. **The board's one-NOW-item rule has been unsatisfied since 2026-08-06** (backlog §5), through six
   subsequent milestones. That is disclosed, not hidden, but it means the sequencing discipline the
   architecture depends on is currently supplied by task briefs rather than by the board.

There is no observed architectural defect. The score is 8 because the architecture is correct and is
carrying weight it is not yet being asked to bear.

### 1.2 Deterministic engine — 7 / 10

**Evidence for.** Price-structure primitives are thorough and rigorously proved: swing detection,
structural labelling, structural trend, level crossing, break of structure, change of character, each
with its own ADR and foundation design record. ADR-0024 removed an entire class of silent
misconfiguration by making a confirmation-delay mismatch unrepresentable rather than warned about.
Milestone AS corrected a real time-reference defect and measured the correction (`RegimeInputError`
1,006 → 0 across 6,452 replayed historical states).

**Evidence against.**

- **Two of ten evidence families are populated.** `fmis.evidence.EvidenceFamily` declares TREND,
  MOMENTUM, VOLUME, VOLATILITY, MARKET_STRUCTURE, RELATIVE_STRENGTH, LIQUIDITY, MACRO, NEWS,
  SENTIMENT. Only TREND and MOMENTUM carry descriptors. LIQUIDITY, MACRO, NEWS and SENTIMENT are zero
  lines (`FMITS_INFORMATION_EDGE_RESEARCH.md` Part 1 stage 8).
- **Two of the five evidence observations inside those families are provably not independent.**
  `macd_vs_signal` and `macd_histogram` are the same fact by construction — checked against all
  21,680 observations with zero mismatches — and the three TREND observations are order-transitive,
  the constraint binding in 71.3 % of the 20,960 cases where it can be checked
  (`EVIDENCE_CALIBRATION_RESEARCH_V1.md` §5.2). Five observations carry at most four independent facts.
- **Structural trend has no decay and no strength.** `fmis.structural_trend` explicitly refuses
  "score, strength, rank, probability, duration, magnitude" (`trend.py:25`). A trend that stopped
  making sense 500 candles ago still reads `SUSTAINED` if nothing opposing has occurred. This is
  documented design, not oversight — but it means the single headline fact the directional layer
  depends on most is a boolean-shaped state with no confidence gradient.
- **One fixed pivot granularity, and close-only breaks.** A wick that sweeps a level and closes back
  inside is a "rejection", never a signal — which in crypto specifically discards the liquidity-sweep
  event many traders weight most heavily.

### 1.3 Research infrastructure — 6 / 10

**Evidence for.** Milestone BC is the strongest single piece of engineering in the recent chain. It
derives the warm-up prefix by *asking the production feature objects themselves* rather than
hand-deriving it (1,750 days at the harness defaults), fetches per interval, and then **verifies per
instant** that no role was warming or short of its requested window — measured 0 and 0 across
~160,000 instants, minimum 250 closed candles at all three roles. It replaces a filter-based
counterfactual with a true replay, and proves fidelity by measurement: replaying at the production
bound of 10 reproduces the baseline exactly (45 confirmations, 45 unchanged, 0 shifted, 0 lost,
0 new). The hostile review (report 0013) found no P0; three P1s and three P2s were found and fixed
during the milestone.

**Evidence against, and it is the reason this is 6 and not 8.**

- **The research chain that BC's correction invalidated has not been re-run.** BB established that
  every number in the AV→BA chain rested on a **41–43 day** usable window inside a period described
  as 400 days, and BC additionally found that AV's setup identity changes every bar — measured at
  **549 "unique setups" from 552 directional observations** and **186 "unique confirmed setups" from
  186 confirmed observations**, a 1:1 ratio. Milestones AW (family independence), AX (evidence
  calibration), AY (edge segmentation), AZ (failure attribution) and BA (confirmation freshness) were
  all computed on that population. Their arithmetic is sound and was cross-audited (BB §2.2); their
  *subject* was a 43-day episode of near-duplicate rows. **None has been re-derived on BC's corrected
  window and identity.** The findings that survive are the ones traced to source code rather than to
  data — principally AW §5.2's CTX-dominance trace and AX §5.2's two provable redundancies.
- **The extraction code for AW–BA lives outside the repository**, in scratch directories, by each
  document's own statement (`EDGE_SEGMENTATION_RESEARCH_V1.md` Appendix). Those results are not
  reproducible from a clean checkout.
- **No coverage tooling and no CI exist.** BC measured 92.4 % line coverage using stdlib
  `sys.monitoring` because no coverage package is installed. D-07 (CI timing) is an open decision.
  Report 0013 F7 is the direct consequence: a stale `__pycache__` entry with a matching recorded
  mtime and size caused two test failures recorded on the backlog for four days as "a
  float-formatting flake", **and made `fmits scan` print prices in scientific notation on this
  machine**. A correctness fault reached the live product surface and was misclassified for days.

### 1.4 Backtesting — 3 / 10

**Evidence.** The harness exists, is deterministic, and is protected against lookahead two
independent ways (a replay transport pre-filtering to `close_time < now`, plus `fetch_klines`
re-deriving `is_closed` from the same clock), with mutation probes on the boundary.

**Why 3.** Against `PROJECT_SPECIFICATION_V1.md` §18's own list of what a backtest must report —
number of trades, win rate, average win, average loss, **expectancy**, profit factor, **maximum
drawdown**, risk-adjusted return, exposure, performance across regimes — the harness reports the
first two and nothing else. `BACKTEST_LIMITATIONS` AV-1 states it directly: *"no fees, slippage,
spread or execution delay are modelled, and no position sizing is applied."* AV-2: `TARGET_FIRST` /
`STOP_FIRST` are **wick touches**, "not a win rate and not a claim of profitability".

The corrected BC baseline: **380 days, 10 symbols, 45 confirmed opportunities, 44 evaluated outcomes,
53.8 % target-first** (report 0012 §7). Spec §18 also requires testing across bull, bear, sideways,
high-volatility and low-volatility periods; the measurement window is one common 13-month window
bounded below by AVAXUSDT's weekly history (`BC-3`), and the harness is structurally unable to reach
further back because 250 weekly candles is nearly five years and the youngest symbol has six.

**Expectancy has never been computed by any stratification, and no cost model exists anywhere in the
repository** — `grep` for slippage across `src/` returns four hits, all of them limitation text.

### 1.5 Risk management — 0 / 10

**Evidence.** `PROJECT_SPECIFICATION_V1.md` §8 states a hard 2 % per-trade ceiling, portfolio-level
open risk, correlation, concentration, drawdown and leverage limits. `PROJECT_VISION_ADDENDUM_V1.md`
names "Capital preservation comes first" as a core principle and lists a Risk Engine as a core module.

The implementation is one string, printed on every setup page:

> `AR-2: No position size, portfolio risk or leverage is computed. The existing 2% portfolio-risk
> maximum is a rule this package does not apply.`

`fmis.workspace.sections.risk_section` returns `Unavailable` with the prohibition *"No position size
shown here would be legitimate. Do not infer one."* This is the largest single gap between the
project's stated principles and its shipped code, and it has been the largest gap since the vision was
written. EP-04 is the only epic on the backlog marked **Critical**, and it is gated on D-02 / AP-D1,
which is not accepted.

### 1.6 Signal quality — 2 / 10

The score is not 2 because the signal is bad. It is 2 because after thirteen milestones, **whether the
signal is good is still unknown**, and three separate mechanisms make it hard to find out.

1. **The best available measurement is 44 outcomes.** 53.8 % target-first, before costs, on wick
   touches, across ten co-moving crypto majors with overlapping 60-bar evaluation windows, one symbol
   contributing 25 % and one contributing none (report 0012 §7, §13). BC itself says: "44 outcomes is
   a small sample."
2. **The three "independent" evidence families are not independent, and one of them is architecturally
   forced.** Chance-corrected agreement is κ = 0.02 (CTX↔SETUP), 0.10 (CTX↔EVID), **0.41
   (SETUP↔EVID)**. CTX participated in **100.0 % of 578 directional results with no exception**, and
   `EVIDENCE_FAMILY_INDEPENDENCE_RESEARCH_V1.md` §5.2 traces this to source: the regime gate's
   `TRENDING` classification and the CTX evidence vote are both built from the identical
   `context_view.structure.trend` value. The gate and one of the three votes read the same number
   under two names. The product's own headline claim — "at least two of three independent evidence
   families" — is measurably weaker than it reads.
3. **Displayed risk/reward is associated with *lower* success, and the association is visible in the
   live product today.** On the pre-correction dataset, RR ≥ 5 resolved at 7.7 % (n = 26) against
   74.5 % for RR in [0,1) (`EVIDENCE_CALIBRATION_RESEARCH_V1.md` §3.7). On BC's corrected baseline the
   RR distribution is p50 0.98, p75 2.59, **p90 10.70, max 25.90** (report 0012 §9). A live scan run
   for this audit on 2026-08-11 printed a `CANDIDATE LONG` on APTUSDT with **RR 49.00**. Nothing in
   the product bounds, flags or contextualises that number.

`probability` is permanently `NOT_CALIBRATED` (AR-1), which is the honest position and is credited —
but it also means the system has no calibrated opinion about any setup it produces.

### 1.7 Portfolio logic — 0 / 10

No positions, no exposure, no correlation, no concentration, no total open risk, no buying power.
`portfolio_section` returns `Unavailable` with the prohibition *"This analysis is instrument-only. It
cannot tell you whether you already hold correlated exposure."* EP-04 is LATER.

This is not merely absent — it is **actively load-bearing against the product's own output**. The
live scan on 2026-08-11 returned one `CONFIRMED SHORT` (DOTUSDT) and three `CANDIDATE`s, of which two
were also `SHORT` (ATOMUSDT, ARBUSDT). A trader acting on the page as printed would be constructing a
single directional bet on one asset class across three correlated instruments, and the page has no
capacity to say so.

### 1.8 Execution readiness — 0 / 10

There is no order object, no fill, no broker or exchange-account boundary, and no execution code path
of any kind. This is correct sequencing under the automation ladder (spec §11), and is not a defect.
It is scored 0 because the question asked is readiness, not intent. `IMPLEMENTATION_ROADMAP_V1.md`
places the first trade record at slice **C1**, behind five foundation slices (F1–F5) and two ADR
acceptance events.

### 1.9 Paper trading readiness — 1 / 10

EP-15's own definition on the backlog is "simulated fills on unseen data, identical sizing/risk logic
to live". None of the three clauses is satisfiable today: there is no fill model, no sizing logic, and
no place to record a simulated trade. The one point is for `fmis.archive`, which can durably store an
*analysis* snapshot with an integrity-checked, content-derived record id — real infrastructure that a
paper-trading record would sit beside, but which stores no trade, entry, exit, size, outcome or P&L
(ADR-0027 §2 states this explicitly).

### 1.10 Live trading readiness — 0 / 10

EP-17 requires EP-16 requires EP-15 requires EP-14. Backlog rule §11.7: *"No milestone may bypass the
automation ladder... No rung is skipped for any reason, including income pressure."* Nothing here
suggests it should be.

---

## 2. Can a human already use FMITS?

**Under the four stated assumptions — the owner manually reviews every trade, never blindly follows a
signal, sizes positions himself, and checks charts — yes, and it should begin. With three conditions,
and one correction to the premise.**

### 2.1 Why yes

**It works, today, on real data.** Both live runs performed for this audit returned complete,
coherent output against Binance in seconds. `fmits scan` on 2026-08-11 returned 16 WAIT, 3 CANDIDATE,
1 CONFIRMED, **0 ERROR** across the 20-symbol watchlist.

**It refuses far more than it asserts, and refusing is its default.** Sixteen of twenty symbols
returned WAIT, each with a specific stated reason. The regime gate discards the overwhelming majority
of instants before a direction is ever considered — 96.5 % of 21,680 observations in the AX funnel.
For a discretionary trader whose principal risk is his own eagerness, a tool whose modal answer is
"no, and here is precisely why" is the correct shape.

**It cannot fabricate a price.** Stop and target are always real, already-detected `PriceLevel`
objects reused by reference, or explicitly absent (AR-3). `_nearest`'s strict inequality makes a
zero-risk selection structurally unrepresentable.

**It cannot manufacture confidence.** Probability is always `NOT_CALIBRATED`. Every page prints its
inherited limitations verbatim — the live `fmits setup BTCUSDT` run printed nineteen of them,
including AR-2's flat statement that no position size or portfolio risk is computed. There is no known
instance in this repository of a limitation being softened on its way to the page.

**The evidence trail is unusually honest.** BB voted "C — interesting but insufficient" on its own
predecessor's headline finding and refused to recommend a policy change. BC disclosed a defect in its
own published predecessor (AV's identity) rather than quietly correcting it. A system that publishes
its own weaknesses is a system whose output can be trusted at face value, which is exactly the
property a discretionary user needs.

### 2.2 The correction to the premise

**FMITS cannot collect trades. It has no place to put one.** "Trade collection" as posed would in
practice be the owner keeping his own record outside the system, with FMITS as an input. That is a
legitimate way to start, and this document endorses starting — but it should be named accurately,
because it has a consequence: **a trade record kept outside FMITS cannot be joined back to the
analysis that produced it** unless the owner archives the analysis at decision time
(`fmits swing SYMBOL --archive`) and records the resulting `record_id` in his own notes. That is the
only bridge that exists today, and it is manual.

### 2.3 The three conditions

1. **Ignore the displayed risk/reward as a quality signal.** It is a geometric ratio of two structural
   distances, and the only measurement ever taken of it associates high values with *worse* outcomes
   (§1.6 item 3). A live `RR 49.00` was printed during this audit. Treat RR as a description of the
   geometry, never as a ranking key.
2. **Treat the `MARKET OVERVIEW` block as context, not as a verdict.** In the live run, BNBUSDT and
   ADAUSDT appear under `DIRECTIONAL` as *short*, while their WAIT reason two blocks later reads
   "2 long, 1 short". Both are correct under the header's own stated definition — the overview shows
   the context-role lean when no direction is set — but the two blocks read as contradicting each
   other. This is the same class of hazard Milestone AU's review recorded as its P0.
3. **Read the stop as a level, not as a resting order.** For the live DOTUSDT `CONFIRMED SHORT`, the
   page states the invalidation is *"a confirmed close beyond the upper level at 0.802 — the same
   level reported as the stop."* Structural invalidation requires a **close**; a stop-loss order
   executes on a **touch**. A wick through 0.802 that closes back inside removes the position while
   the system still regards the thesis as valid. The system is internally consistent; the trader must
   supply the distinction himself.

### 2.4 Would I personally allow it

Yes — for **collection**, explicitly not for capital deployment, and with the expectation that the
first months produce a *record*, not a return. The reason is not that FMITS is proven; it is not
(§1.6). The reason is that the alternative — waiting for a validated system before collecting any
outcomes — is unreachable. FMITS has 44 measured outcomes over 380 days across ten symbols. A
discretionary trader taking two or three trades a month will accumulate real, live, non-overlapping
outcomes at a rate the backtest cannot match, and every one of them is evidence the repository does
not currently have. **The collection is the milestone-generating asset, and it starts producing value
on day one.**

The condition on that yes: the trades must be *small enough that the answer to "was this policy any
good" arrives before the capital does*, and that is a sizing decision the owner makes himself, because
FMITS cannot make it (§1.5).

---

## 3. Missing capabilities before paper trading

Blocking only. Anything that would merely improve paper trading is excluded.

| # | Missing capability | Why it blocks | Evidence |
|---|---|---|---|
| **P-1** | **A durable record of a trade decision and its outcome** — entry, exit, size, fees, timestamps, and a link to the analysis that produced it | Paper trading that is not recorded is not paper trading; it is looking at charts. Nothing in the repository can store a trade: `fmis.archive` stores `Workspace`/`DailyRun` only, and ADR-0027 §2 states it does not recompute or replay | Backlog §6 item 2 · `IMPLEMENTATION_ROADMAP_V1.md` C1 |
| **P-2** | **AP-D1 and AP-D2 accepted as ADRs** | AP-D2 is the capture contract and migration guarantee. The backlog marks it **Blocking — must precede the first written trade**, because ADR-0027 §8's exact-match-no-migration rule was proportionate for regenerable analyses and is unsafe for records that cannot be recomputed. AP-D1 decides where `float` stops and `Decimal` begins — a paper trade with float money is a record that will need migrating | Backlog §6 item 1, §10 · `AP_D1_D2_INVESTIGATION.md` |
| **P-3** | **Position sizing** | EP-15's own definition requires "identical sizing/risk logic to live". A simulated trade with no size produces no P&L, no expectancy, no drawdown and no exposure — i.e. none of the metrics spec §18 requires a backtest to report. Zero lines exist | `AR-2` · `risk_section` → `Unavailable` |
| **P-4** | **An explicit entry and fill rule** | The product deliberately fabricates no entry price: the reference is relabelled *"reference … (not an order price)"*, and AV-4 states the harness uses the execution close at the confirming bar with "no fill at a wick, and no next-bar-open assumption". A paper trade requires a stated fill assumption; today there is none to state | `AR-3` · `BACKTEST_LIMITATIONS` AV-4 |
| **P-5** | **A cost model — fees, spread, slippage** | Without it a paper trading run reproduces the identical fantasy the backtest already reports, at slower speed. A 53.8 % wick-touch rate before costs has an unknown sign after them | `BC-1` / `AV-1` · report 0012 §13 |

**Deliberately excluded as non-blocking for paper trading:** derivatives, on-chain, macro, news,
sentiment, order-book depth, ranking, AI interpretation, alerts, scheduling, dashboards, multi-asset
support. Each is real product value; none prevents a simulated trade from being recorded and scored.

---

## 4. Missing capabilities before real money

Everything in §3, plus the following. Scoped to **small real positions**, not to scaling.

| # | Missing capability | Why it blocks small real positions | Evidence |
|---|---|---|---|
| **R-1** | **Portfolio open risk and correlation/concentration awareness** | Spec §8.2: "Five individually acceptable positions can still create excessive portfolio risk if they are highly correlated." The live scan on 2026-08-11 offered three simultaneous SHORT setups on three correlated crypto majors, with no capacity to observe that they are one bet. With real money, the failure mode is not a bad trade; it is three copies of the same bad trade | Live run · `portfolio_section` → `Unavailable` · EP-04 marked **Critical** |
| **R-2** | **A geometry plausibility bound on stop and target** | A displayed `RR 49.00` (live, 2026-08-11) is not an opportunity; it is a target so distant that reaching it is close to unrelated to the thesis. AV's own run recorded a maximum of 41,282. Whatever the correct bound is, the current bound is **none**, and the one measurement ever taken says high RR is associated with worse outcomes | Live run · report 0012 §9 · `EVIDENCE_CALIBRATION_RESEARCH_V1.md` §3.7 |
| **R-3** | **Any evidence that expectancy is positive after costs** | Not a capability request — a knowledge gap that blocks. Today the sign of expectancy is **unknown**: no expectancy figure exists at any stratification, before or after costs, anywhere in AV–BC. Deploying capital against an unmeasured sign is a decision to fund the measurement | BB §4 item 2, §9.5 · report 0012 §13 |
| **R-4** | **Tax capture at the moment of the transaction** | D-10 is owner-confirmed: Swedish tax readiness is in project scope. `AP` §22.1 separates the engine (later) from the **capture contract** (first), because FX rates and acquisition values are unrecoverable if not captured at transaction time. A real trade recorded without them is permanently incomplete | Backlog §10 D-10 · `TRADING_DOMAIN_ARCHITECTURE_V1.md` §22 |
| **R-5** | **A stated position on the stop-versus-invalidation asymmetry** | With real money the difference between "wick touches the stop" and "candle closes beyond the level" is realised loss. The product currently reports both as the same price and explains the difference only in prose | Live run (DOTUSDT, 2026-08-11) |

**Out of FMITS's scope, named so the owner does not wait for them:** exchange account setup, custody,
API keys, withdrawal controls. Execution is manual by design; FMITS is decision support. Whether the
owner's own operational security is adequate is **unknown** to this audit and outside it.

---

## 5. Critical product risks

Probability = likelihood of occurrence within the first six months of real use.
Impact = consequence for capital or for the product's trustworthiness.
Detectability = how likely the owner is to notice it *before* it costs something. **Low detectability
is the dangerous column**, not high impact.

| # | Risk | Prob. | Impact | Detect. | Mitigation available today | Evidence |
|---|---|---|---|---|---|---|
| **R-01** | **The policy is negative-expectancy after costs.** 53.8 % target-first on wick touches, no fees, no spread, no slippage, no funding. The sign after costs is unknown | Medium | **Critical** | **Low** — cannot be detected without a cost model or ~50+ live outcomes | Trade small; record every outcome from day one | Report 0012 §7, §13 · `BC-1` |
| **R-02** | **A position is sized wrong because nothing computes size.** The 2 % ceiling exists only in a specification document | Medium | **Critical** | High — the owner sets it himself | Owner-computed sizing, held to a written rule outside the system | `AR-2` · spec §8.1 |
| **R-03** | **Correlated concentration.** Several simultaneous same-direction setups on co-moving majors are taken as independent bets | **High** | **Critical** | Medium — visible on the page only if the owner reads across rows | Manual cross-check of open exposure before every entry | Live scan 2026-08-11 (3 SHORT of 4 directional) · spec §8.2 |
| **R-04** | **Pathological stop/target geometry is presented as fact.** `RR 49.00` printed live; corrected-baseline p90 = 10.70, max = 25.90; AV max = 41,282 | **High** | High | High — visible, but only if the owner knows to distrust it | Ignore RR as a quality signal (§2.3) | Live run · report 0012 §9 |
| **R-05** | **The "three independent families" guarantee is weaker than it reads.** κ = 0.41 SETUP↔EVID; CTX in 100 % of 578 directional results, traced to a shared source value | **Certain** (already true) | High | **Low** — invisible on every page; the page states the guarantee as designed | None in product. The finding exists only in an untracked research document | `EVIDENCE_FAMILY_INDEPENDENCE_RESEARCH_V1.md` §5.2, §6.1 |
| **R-06** | **Invalidated research findings re-enter decisions.** AW/AX/AY/AZ/BA were computed on a 41–43-day window with a broken identity (549 "setups" from 552 bars). None has been re-derived on BC's corrected harness | **High** | High | **Low** — the documents read as authoritative and their arithmetic is correct | Cite BB §2.3 and report 0012 §7 beside any figure from that chain | BB §2.3 · report 0012 §7 |
| **R-07** | **The sample is too small to detect that the policy has stopped working.** 45 confirmed opportunities in 380 days across 10 symbols ≈ one every 8.4 days universe-wide | **High** | High | **Low** by construction — this risk *is* a detectability failure | Widen the watchlist; record live outcomes | Report 0012 §7 |
| **R-08** | **No learning loop.** Every future improvement is argued from first principles rather than measured against lived outcomes, indefinitely | **Certain** (already true) | High | Medium | Manual journal outside the system, with archived `record_id`s | `TRADING_DOMAIN_ARCHITECTURE_V1.md` (designed, zero code) |
| **R-09** | **Irreplaceable records written before AP-D2 is accepted.** A ledger cannot be recomputed; ADR-0027's exact-match-no-migration rule would reject its own earlier records after a schema change | Medium | **Critical** | **Low** — surfaces only at the first schema change, by which time the data exists | Do not write trade records into `fmis.archive` before AP-D2 | Backlog §10 AP-D2 ("must precede the first written trade") |
| **R-10** | **Single venue, single provider, spot only.** Binance public REST is the sole input. An outage, a geo-restriction or a symbol delisting silently removes the entire information supply | Medium | High | High — `ERROR` rows are reported per symbol and do not stop a scan | Per-symbol failure isolation already exists | `FMITS_INFORMATION_EDGE_RESEARCH.md` Part 1 stage 1 |
| **R-11** | **Structural staleness on the context role.** The weekly view's newest closed bar was measured **13 days old** live during Milestone AG, because the week had not closed. The context gate that permits any direction at all can be reasoning from a two-week-old structural state | **High** | Medium | Medium — each view prints its own `as_of` | Read the per-view `as_of` on every page | `AG-1` · CURRENT_STATE AG entry |
| **R-12** | **Silence is indistinguishable from absence of opportunity.** The regime gate discarded 96.5 % of instants in the AX funnel; long stretches produce nothing, for data reasons as much as market reasons. A trader who receives nothing for weeks substitutes his own judgment — the precise bias the system exists to remove | **High** | High | **Low** — a quiet system looks identical to a quiet market | The WAIT reason strings do distinguish the two, if read | `EVIDENCE_CALIBRATION_RESEARCH_V1.md` §3.8 · live run (12 of the 16 WAIT results were for a regime reason, not a market one) |
| **R-13** | **Stop-as-touch versus invalidation-as-close.** The stop price and the invalidation level are the same number; one triggers on a wick, the other requires a close | **High** | Medium | Medium — stated in prose on the page, not as a distinct field | Owner treats them as two different things | Live run (DOTUSDT, 2026-08-11) |
| **R-14** | **The evidence base is not under version control.** Twelve research/review documents — including every AW–BB record and the implementation roadmap — are untracked in git | **Certain** (already true) | Medium | High — `git status` shows it | Commit them, or accept that they can be lost | `git status` at `7ced9e2` |
| **R-15** | **No CI, no type checking, environment-dependent correctness.** A stale bytecode cache produced two misdiagnosed test failures for four days *and* corrupted live price formatting in `fmits scan` | Medium | High | **Low** — it was misdiagnosed as a flake and recorded as one on the backlog | Full-suite runs before use; clear caches | Report 0013 F7 · backlog §10 D-07 |

**The three rows that matter most are R-01, R-05 and R-12** — not because their impact is highest, but
because all three combine high or certain probability with **low detectability**. A risk the owner
will notice is a risk he can manage. These three are invisible from the product surface.

---

## 6. Red team

Premise: the objective is to make FMITS produce a confident, well-formatted, wrong answer that a
disciplined owner acts on.

### 6.1 The cheapest attack: let the owner rank by risk/reward

No market condition is required. The product prints RR on every actionable row, sorts nothing, and
offers no other quality axis. A human reading a page with `RR 2.60`, `RR 3.08`, `RR 6.00` and
`RR 49.00` on it will pick the biggest number — and the only measurement ever taken of that variable
points the other way (RR ≥ 5 → 7.7 %, n = 26). The product supplies the anchor and supplies nothing to
counter it. **This attack requires no adversary; it happens by default.**

### 6.2 The liquidity sweep

Close-only structure breaks mean a wick that sweeps a level and closes back inside is a "rejection".
In crypto that wick is frequently the *informative* event. The attack: a stop-hunt through the level
that carries the trader's stop (which sits exactly at the level whose *close* would invalidate the
thesis, §2.3 condition 3), followed by reversal. The owner is stopped out; FMITS still holds the
thesis valid, because no candle closed beyond it. The system has no representation of this having
happened and will report the same setup again.

### 6.3 The regime that never trends

`StructureState.TRENDING` requires **both** the swing-structure family and the moving-average family
to be readable and to agree. In a prolonged chop, the gate returns `INSUFFICIENT`, `TRANSITIONING` or
`INDETERMINATE` and the product returns WAIT indefinitely — as it did for 12 of 20 symbols in the
live run (10 `indeterminate`, 2 `transitioning`), against only 4 that reached the family tally and
failed it. That is correct behaviour producing a dangerous product state: months of silence, no
outcomes accumulating, no way to distinguish "the market offers nothing" from "the engine cannot
read this market", and a bored owner with a chart.

### 6.4 The sustained trend that ended

Structural trend has no decay (§1.2). Enter a market that trended for a year and reversed six weeks
ago without producing the specific swing sequence that flips the label. The context role — the gate
that permits any direction at all, and simultaneously one of the three votes — keeps reporting
`SUSTAINED_HIGHER`. The system produces LONG candidates into a downtrend and cannot represent the
possibility that its own most important fact is stale.

### 6.5 The correlated portfolio

Nothing in FMITS knows what the owner holds. Feed it a market where the whole complex moves together
— which is the ordinary state of crypto majors — and it will produce three, five or eight
same-direction setups, each individually reasoned and each printed as a separate opportunity. One
liquidation event resolves all of them at once. This is the highest-probability path from "FMITS
worked as designed" to "the account is down 15 %".

### 6.6 The statistical attack

Run the AY/AZ segmentation methodology again on the corrected 44-outcome dataset. With ~25
segmentations and no multiplicity correction — which AY, AZ and BA all state they do not apply — a
new set of striking-looking cells will appear. Some will be extreme (AY found a 0/27 cell). The
product's own decision process is the vulnerable surface here: BB voted C and refused BA's finding,
which is the correct behaviour and the only thing that stopped it. **The defence is a document, not a
mechanism.**

### 6.7 Assumptions that remain untested

Each of these is load-bearing and has never been varied or validated:

- `CONFIRMATION_LOOKBACK_BARS = 10` — BC replayed 0/1/2/3/5/10 and produced a **non-monotonic**
  target-first series (53.8 / 51.9 / 51.7 / 61.3 / 53.1 / 60.0 / 53.8 %) on 31–44 outcomes per row.
  No bound is better-supported than any other. Unknown.
- `MINIMUM_AGREEING_FAMILIES = 2` of exactly 3 — untested; and one of the three is architecturally
  forced (§1.6).
- The 60-bar outcome evaluation window — a stated measurement policy, never varied.
- The 1w/1d/4h role assignment — never varied.
- The fixed swing pivot window — one granularity at every point of every series.
- The 20-symbol watchlist — hardcoded; five of AV's ten backtest symbols produced zero outcomes in
  the pre-correction window, and AVAXUSDT produced zero in the corrected one.
- That a wick touch of a level is a reasonable proxy for a trade outcome — the assumption every
  measurement in this repository rests on. Unknown.

### 6.8 Where the attacks fail

For completeness and calibration, three attacks that do **not** work. Lookahead: two independent
mechanisms, mutation-probed, plus BC's third boundary system. A fabricated stop or target: structurally
unrepresentable, levels are reused by reference. A silently loosened limitation: every limitation is
inherited verbatim to the page and the counts are asserted by test. These are genuinely hard to break,
and that is why the attacks above target the *interpretation* surface rather than the computation.

---

## 7. Blind spots

Dimensions an experienced discretionary crypto swing trader consults that FMITS does not represent in
any form. Percentages are the information-edge research's own estimates
(`FMITS_INFORMATION_EDGE_RESEARCH.md` Part 4), reproduced rather than re-derived.

| Dimension | Present | Consequence for swing trading specifically |
|---|---|---|
| **Derivatives** — funding, open interest, liquidations, basis, options | **0 %** | The single most crypto-specific risk factor. Identical price action with extreme positive funding and rising OI is a different trade; FMITS cannot distinguish the two |
| **On-chain** — exchange flows, stablecoin supply, whale cohorts, unlocks | **0 %** | A leading supply-pressure indicator a price-only system cannot derive from its own inputs |
| **Macro** — rates, DXY, real yields, liquidity, calendar | **0–2 %** | Crypto's dominant multi-week driver. A swing trade is precisely the horizon on which macro decides the outcome. EP-07 is BLOCKED on D-03 |
| **News / catalysts** | **0 %** | No event calendar, no unlock schedule, no mechanism reasoning. A trade entered the day before FOMC is indistinguishable from any other |
| **Sentiment** | **0 %** | — |
| **Order book / microstructure** — depth, spread, fill feasibility | **0 %** | Directly connected to R-04: nothing checks that a computed stop or target is reachable at a sane price |
| **Breadth / rotation / BTC dominance** | **0 %** | "Is this the coin, or is this just BTC" is the most common discretionary framing question, and FMITS is structurally single-symbol. The RVE can compute pairwise correlation; the product has never wired a BTC benchmark into the swing workflow |
| **ETF flows** | **0 %** | A high-signal public series specific to the post-2024 market structure |
| **Cross-venue / perpetuals** | **0 %** | One venue, spot only. Perps routinely carry more volume and more informed flow |
| **Portfolio & position risk** | **0 %** | §1.7. The largest gap between stated principle and shipped code |
| **Execution costs** | **0 %** | Every performance figure in the repository is pre-cost |
| **Session / time-of-day / weekend liquidity** | **0 %** | Every candle is treated identically |
| **Implied volatility** | **0 %** | The volatility dimension is a backward-looking realised ATR ratio only |
| **Post-trade learning** | **0 %** | Designed in full on paper; zero code |
| **Non-crypto assets** | **0 %** | Equities, ETFs, indices, commodities, China — all named in the vision, none reachable. Requires a calendar/session layer that does not exist |

**Two blind spots that are not market dimensions and are easy to miss:**

- **Operational observability.** No CI, no type checking, no health monitoring, no error budget. The
  F7 incident (§1.3) is what this looks like in practice.
- **The owner's own behaviour.** Spec §7 requires the system to guard against confirmation bias,
  recency bias and overconfidence, and §6 requires it to construct the strongest opposing case before
  a directional trade. The strongest-opposing-case capability does not exist; the AI interpretation
  section renders as `Unavailable`. The system currently guards against *its own* biases well and
  against the owner's not at all.

---

## 8. Roadmap prioritization — the next five milestones

Selection rule applied: each milestone must remove a risk from §5 that blocks real use, in the order
that maximises how much is *learnable* per unit of work. Ranked; the ordering is a dependency claim,
not a preference.

### 1st — **Trade & Outcome Record**: accept AP-D1 and AP-D2, then ship the smallest thing that can
record one trade and its result

**Why first.** Every other milestone on this list produces numbers; this one produces the ability to
keep them. It is also the only item whose cost *rises* with delay: from the moment the owner takes his
first real trade, every unrecorded decision is permanently lost, and Swedish tax capture (D-10,
owner-confirmed in scope) is unrecoverable after the fact. The backlog already sequences it as NEXT
item 1 and 2, and `IMPLEMENTATION_ROADMAP_V1.md` already decomposes it (F1–F5 → C1).

**Unlocks.** Manual trade recording, the join between an archived analysis and its realised outcome,
tax capture, and — as a consequence rather than a feature — the first dataset in this project's
history that is *not* a backtest.

**Risk removed.** R-08 (no learning loop), R-09 (irreplaceable records written under an unaccepted
capture contract), and the §3 blockers P-1 and P-2 in full.

**Scope discipline.** The temptation here is the full five-object decision chain. The smallest version
that removes R-09 is one recorded decision plus one recorded outcome under an accepted capture
contract. Everything else is later.

### 2nd — **Cost-Realistic Measurement**: fees, spread, slippage, an explicit fill rule, and expectancy in R

**Why second.** It is the only milestone that can change the **sign** of every conclusion the project
has reached. The best current number is a 53.8 % wick-touch rate with no costs modelled and no
expectancy computed at any stratification. It is cheap: no new data source, no new engine, and the
corrected research harness (BC) already exists and already replays the production path faithfully.

**Unlocks.** The first statement about this policy that is about money. `PROJECT_SPECIFICATION_V1.md`
§18's required metrics — expectancy, average win, average loss, profit factor — become computable.

**Risk removed.** R-01 (negative expectancy after costs, currently undetectable) and §3's P-4 and P-5.
It also makes R-06 partly self-correcting, because a re-run harness is the natural place to re-derive
what the invalidated chain claimed.

**Why not first.** It answers a question; it does not preserve an answer. If it runs first and the
owner starts trading in parallel, those trades are still unrecorded.

### 3rd — **Risk & Portfolio Layer**: per-trade sizing under the 2 % ceiling, total open risk, correlation and concentration

**Why third.** It is the largest gap between the project's stated principles and its code, it is the
only **Critical** epic on the backlog, and it is entirely deterministic once positions are known —
which is exactly what milestone 1 makes true. Ordering it after 1 is a hard dependency, not a
preference: a risk layer with no position record has nothing to compute over.

**Unlocks.** The first legitimate answer to "how much"; the `RISK` and `PORTFOLIO` sections stop being
`Unavailable`; and paper trading becomes definable at all, since EP-15 requires "identical sizing/risk
logic to live".

**Risk removed.** R-02 (mis-sizing), R-03 (correlated concentration — currently the highest-probability
path to a large loss), and §3's P-3.

### 4th — **Setup Feasibility Bounds**: stop/target plausibility, and the stop-versus-invalidation distinction made explicit

**Why fourth.** It is the cheapest remaining milestone and it addresses the two hazards that reach the
owner's eyes on every single page: an unbounded RR (live: 49.00) presented as a fact, and a stop price
that is simultaneously an invalidation level with different trigger semantics. It is ranked below 1–3
because a discretionary owner who has been told about both (§2.3) can compensate manually; he cannot
manually compensate for an unrecorded trade or an unsized position.

**Unlocks.** A page whose numbers can be read at face value — the property the rest of the product
already has and this part does not.

**Risk removed.** R-04 (pathological geometry presented as fact) and R-13 (stop/invalidation
asymmetry); §4's R-2 and R-5.

### 5th — **Re-derive the research chain on the corrected harness**, reproducibly, in-repo

**Why fifth and not higher.** Five research milestones (AW, AX, AY, AZ, BA) currently sit in
`docs/design/` reading as authoritative, computed on a window BB proved was 41–43 usable days and an
identity BC proved changed every bar. Their arithmetic was audited and is correct; their subject was
wrong. Until they are re-derived, the repository's stated knowledge about its own evidence quality is
of unknown validity — and the extraction scripts that produced them live outside the repository.

**Why not higher.** It regenerates knowledge; it does not remove a capital risk. Milestones 2 and 3
change what the owner can safely do next month. This changes what the repository can safely claim.

**Unlocks.** A trustworthy answer to "which evidence actually earns its place", on a de-duplicated
sample, reproducible from a clean checkout.

**Risk removed.** R-06 (invalidated findings re-entering decisions) and part of R-05 — the family
independence measurement in particular deserves re-derivation, because its *architectural* half
(CTX in 100 % of directional results, traced to a shared source value) survives the invalidation and
its *statistical* half does not.

### 8.1 Named exclusions

Stated so the ranking can be checked rather than trusted, and because several are high-value:

- **Funding rate / open interest, BTC-beta, macro liquidity flag, liquidation awareness.**
  `FMITS_INFORMATION_EDGE_RESEARCH.md` Part 7 ranks these 2nd, 3rd, 7th and 8th on
  information-edge-per-effort, and this audit does not dispute that. They are excluded from a
  *readiness* list because each adds new information, and none removes a risk that blocks the owner
  from starting. Readiness is bounded by what the system does with the information it already has.
- **AI interpretation / strongest-opposing-case.** Spec §6–§7 require it. It is excluded because it
  reasons over facts, and the facts it would most need (portfolio, cost, outcome) arrive in
  milestones 1–3.
- **Ranking, alerts, scheduling, dashboards, multi-asset, second venue.** None blocks a trade.
- **CI and type checking (D-07).** A real gap with a demonstrated incident (F7), excluded only
  because five slots were available and each of the five above removes a capital risk this does not.

---

## 9. Readiness verdict

> ## **C — Needs several milestones first.**

### Why C

Three facts decide it, and each is sufficient alone.

1. **Nothing can record what happens.** If the owner trades next month, the record of what FMITS
   recommended, what he did, and what resulted exists only in his own notes. A decision-support system
   that cannot observe its own outcomes cannot improve, cannot be validated, and cannot be falsified.
2. **Nothing computes size, and nothing sees the portfolio.** The product's own page says a position
   size shown there "would not be legitimate". With three simultaneous same-direction setups printed
   in a single live run (§1.7), the mechanism by which a disciplined owner loses badly is available
   today and unguarded.
3. **The sign of expectancy after costs is unknown.** 53.8 % target-first on 44 wick-touch
   classifications, before fees, spread and slippage, on ten co-moving symbols in one 13-month window.
   That is not evidence the policy works, and it is not evidence it fails. It is an unmeasured
   quantity, and the repository is admirably clear that it is.

### Why not B

**B is the closest call, and the distinction is worth stating precisely.** §2 of this document says
the owner *should* begin taking small real discretionary positions and collecting outcomes. That is
not a contradiction of C: it is a statement about the **owner**, not about the **product**. Under B,
FMITS would be ready to support limited positions — meaning the system carries the parts of the
decision it claims to carry. It does not. The owner supplies the sizing, the portfolio view, the cost
awareness, the RR skepticism and the record-keeping himself. He can do all of that; a spreadsheet and
discipline are sufficient. But a verdict of B would credit FMITS with work the owner is performing.

**The honest statement is: the owner is ready; the product is three milestones behind him.**

### Why not A

Paper trading as the backlog defines it (EP-15: simulated fills on unseen data, identical sizing and
risk logic to live) requires a fill model, a sizing model and a trade record. Zero of the three exist.

### Why not D

D would mean FMITS should not be used. It should. It runs correctly on live data, refuses far more
than it asserts, fabricates no price, claims no probability, and prints its own limitations
exhaustively (§2.1). A system with an honest `NOT_CALIBRATED` and an `Unavailable` risk section is
more trustworthy than most systems that print a number in both places. That is a real asset and it is
not what "not ready" describes.

### The condition attached to C

C is a statement about the product, not an instruction to stop. **Milestone 1 (trade and outcome
record) should be treated as urgent rather than merely next**, because it is the only item on the list
whose cost increases with every week of real trading that happens before it lands.

---

## 10. Executive summary

**If the owner reads only this page.**

**Where FMITS stands.** Thirteen milestones since AR have produced a deterministic swing-analysis
system of genuinely high engineering quality: 4,653 passing tests, 28 ADRs, zero import cycles,
mutation-tested boundaries, and a product that runs correctly against live Binance data in seconds. It
is honest in an unusual way — it prints `NOT_CALIBRATED` rather than a probability, renders risk and
portfolio as explicitly unavailable rather than omitting them, and its own research milestones have
twice invalidated their predecessors in public rather than quietly.

**What it can do.** Answer, rigorously, *"what did price do structurally, on one venue, at
candle-close resolution, and do two or three of my evidence families agree about it?"* — for one
symbol or a twenty-symbol watchlist. On 2026-08-11 it returned 16 WAIT, 3 CANDIDATE, 1 CONFIRMED,
0 ERROR. Refusal is its default, which is the correct shape for a discretionary trader's tool.

**What it cannot do.** Compute a position size. See the portfolio. Model a fee, a spread or a slippage.
Record a trade. Observe an outcome. Rank an opportunity. Say whether it works.

**The one number that matters.** The best measurement of this policy in existence is **44 outcomes
over 380 days, 53.8 % target-first, before all costs, on wick touches rather than trades**. Expectancy
has never been computed at any stratification. Whether the policy makes or loses money is **unknown**,
and every prior research figure that seemed to answer it was computed on a 41–43-day sample of
near-duplicate rows that Milestones BB and BC invalidated and nothing has yet replaced.

**Should the owner start next month.** **Yes — for trade collection, at sizes small enough that the
verdict arrives before the capital does.** Three conditions: ignore displayed risk/reward as a quality
signal (a live run printed `RR 49.00`, and the only measurement ever taken associates high RR with
worse outcomes); read the market-overview block as context rather than verdict; and treat the stop as
a level, not a resting order, because the stop price and the invalidation level are the same number
with different trigger semantics. The correction to the premise: **FMITS cannot collect trades — it
has no place to put one.** Collection will happen in the owner's own records, with an archived
`record_id` as the only bridge back to the analysis.

**The three risks that should keep the owner awake.** Not the largest ones — the *undetectable* ones.
(1) The policy may be negative-expectancy after costs and there is no way to find out without a cost
model or fifty live outcomes. (2) The "three independent evidence families" guarantee is measurably
weaker than the page states — one family participates in 100 % of directional results because the
regime gate and that family read the same underlying value. (3) A silent system is indistinguishable
from a quiet market, and a bored discretionary trader is the exact failure mode the system exists to
prevent.

**The highest-probability way to lose real money next month** is not a bad signal. It is taking three
simultaneous same-direction setups on three correlated majors — which the live scan offered today —
and having no component anywhere in the system capable of noticing that they are one bet.

**The next five milestones, in order.** (1) Accept AP-D1/AP-D2 and ship the smallest trade-and-outcome
record — the only item whose cost rises with every week of delay. (2) Cost-realistic measurement:
fees, spread, slippage, a stated fill rule, expectancy in R — the only item that can change the sign
of every conclusion this project has reached. (3) Risk and portfolio: per-trade sizing under the 2 %
ceiling, total open risk, correlation — the largest gap between the project's stated principles and
its code. (4) Setup feasibility bounds — the two hazards visible on every page. (5) Re-derive the
research chain on the corrected harness, reproducibly and in-repo.

**Verdict: C — needs several milestones first.** The system is trustworthy, honest and correct within
a narrow input class. It is not yet carrying the parts of a trading decision it claims to support:
size, portfolio, cost, and memory. The owner is ready to start collecting trades. The product is three
milestones behind him, and the first of those three should be treated as urgent rather than merely
next.

---

**End of audit. No production code, no ADR, no backlog edit, no changelog entry, no `CURRENT_STATE`
edit, no commit. One artifact:** `docs/design/SWING_TRADING_READINESS_AUDIT_V1.md`.
