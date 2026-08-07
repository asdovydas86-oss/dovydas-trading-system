# Swing Setup Engine v1 — design

**Milestone:** AR
**Status:** Implemented
**Date:** 2026-08-07
**Contracts:** [ADR-0028](../adr/ADR-0028-directional-interpretation-boundary.md)
**Repository state at start:** `75a4f40`, plus the four untracked AQ documents already reviewed by
[`ADR_IMPLEMENTATION_GATE.md`](ADR_IMPLEMENTATION_GATE.md).

## 1. What this milestone builds

A deterministic interpretation layer, `fmis.swing_setup`, that turns an already-computed
multi-timeframe fact sheet, its per-role regimes, its evidence report and its decision context into
one explicit, testable swing-trade assessment — and the `fmits setup SYMBOL [SYMBOL...]` command that
prints it. The product acceptance test, verbatim from the task brief: *"I can now ask FMITS for a
deterministic swing setup assessment on a real crypto instrument and receive either a justified setup
or a justified `WAIT` result."*

**Not built, and named here so the gap is not silent:** position sizing, calibrated probability,
opportunity ranking across symbols, and money/portfolio awareness. Each is out of scope per the task
brief and is stated as a limitation on every result.

## 2. Where it sits

`fmis.swing_setup` is a new top-level application/domain package, at the same tier as `fmis.workspace`
— see [ADR-0028](../adr/ADR-0028-directional-interpretation-boundary.md) for why it is not inside
`fmis.workspace` and not a new engine layer. It composes, and computes no market quantity a lower
engine already computes:

```
multi_timeframe_facts_for_symbol   ──►  MultiTimeframeFactSheet   (fmis.pipeline)
        │                                        │
        │                                        ├──► regime_for_sheet (per view)   (fmis.pipeline.regime)
        │                                        └──► build_evidence_report (SETUP view)
        │                                                 (fmis.decision_support)
        ▼
build_setup_inputs  ──►  SetupInputs  ──►  evaluate_setup  ──►  SetupAssessment
                              ▲
                     evaluate_context (fmis.decision_context)
```

`build_setup_inputs` and `evaluate_setup` are pure — no network, no clock. `setup_for_symbol` is the
one network edge, exactly mirroring every other composition root's split (`structural_facts_for_symbol`
/ `build_structural_facts`, `workspace_for_symbol` / `build_workspace`).

## 3. Result model

`SetupAssessment` (frozen, schema-versioned) carries: `symbol`, `as_of`, `objective` (always
`"swing"`), `state` (`SetupState`), `direction` (`Direction | None`), `thesis` (`tuple[str, ...]` —
deterministic reasons, never authored prose), `directional_factors` (`tuple[DirectionalFactor, ...]`
— every family read, its lean, and whether it counted), `confirmation` (`tuple[str, ...]`),
`invalidation` (`tuple[str, ...]`), `trigger` (`Trigger | None`), `stop` (`PriceLevel | None`),
`targets` (`tuple[PriceLevel, ...]`), `risk_reward` (`RiskReward | None`), `probability`
(`Probability`, always `NOT_CALIBRATED` in v1), `regime_context` (`tuple[str, ...]`), `sufficiency`
(`ContextState`), `limitations` (`tuple[str, ...]`), `policy_id`, `schema_version`.

Every optional field is `None` precisely when the data does not justify a value — never a sentinel
number. `stop`/`targets` reuse `fmis.level_crossing.PriceLevel` **by reference**: the level was
already computed by `fmis.level_crossing`, and wrapping it in a new type would be exactly the
duplicated-value pattern ADR-0016 §4 already rejected.

## 4. Setup states

Three states, never four: `WAIT`, `CANDIDATE`, `CONFIRMED`. No `BUY`/`SELL` state — direction and
readiness are two different dimensions, matching the task brief's own example
(`state=CANDIDATE, direction=LONG` is a weak hypothesis, not a confirmed trade).

## 5. Directional policy — how a candidate forms

**Never from one family.** Three independent families are read, each producing a `Lean` —
`LONG`, `SHORT`, `CONFLICTING` (evidence on both sides) or `UNAVAILABLE` (nothing to read):

1. **CONTEXT-role structural trend** (`fmis.structural_trend.StructuralTrendType`, on the CONTEXT
   view's own candle series). `SUSTAINED_HIGHER` → `LONG`; `SUSTAINED_LOWER` → `SHORT`; `NEUTRAL`
   (evidence on both sides, per that package's own docs) → `CONFLICTING`; `INDETERMINATE` →
   `UNAVAILABLE`.
2. **SETUP-role structural trend**, same rule, on the SETUP view's own series — a distinct candle
   series from CONTEXT, not a second read of the same data.
3. **SETUP-role evidence dominant alignment** (`fmis.decision_support.EvidenceReport`, built once
   from the SETUP view exactly as `fmis.workspace` does). `OverallState.WATCH` with
   `Alignment.UPWARD` → `LONG`; `WATCH` with `DOWNWARD` → `SHORT`; `OverallState.WAIT` (evidence
   present but mixed) → `CONFLICTING`; `INSUFFICIENT_DATA` → `UNAVAILABLE`. This is already an
   aggregate over up to five observations, reduced to one alignment by `fmis.decision_support` itself
   — reading it as one family, not five, is what stops the double-counting the task brief forbids.

**The regime gate, not a fourth vote.** `fmis.market_regime` cannot represent a direction by design
(ADR-0025), so it is never asked to vote. Instead the CONTEXT view's `StructureState` must be
`TRENDING` for a candidate to exist at all: `RANGING`/`TRANSITIONING`/`INDETERMINATE`/`INSUFFICIENT`
all mean "the higher-timeframe environment offers no directional edge to interpret," and the result is
`WAIT` with that reason stated. This uses regime as required, without inventing a direction it does
not carry.

**The Decision Context gate.** `fmis.decision_context.ContextState.INSUFFICIENT` forecloses a
candidate unconditionally, before the vote is even tallied — the task brief's explicit requirement.
`LIMITED` is recorded on the result (`sufficiency`) and narrows the thesis language but does not by
itself block a candidate: `fmis.decision_context` already drew that exact line between blocking and
limiting gaps, and re-deriving it here would be a second, potentially-drifting definition.

**The tally.** A directional side needs **at least two families voting for it and zero voting for the
opposite side**. One vote alone is never enough (forbids `RSI < 30 → LONG`-style single-indicator
rules by construction); two votes on opposite sides, or any `CONFLICTING` lean paired with a same-count
opposing vote, produce `WAIT`. Ties, all-abstain and all-conflicting all produce `WAIT`.

**CONTEXT and SETUP must be distinct intervals — enforced, not merely assumed.** The independent
review (§17) found that nothing stopped `--context 1d --setup 1d`: two roles reading the same
candles would make one underlying fact count as two "independent" votes, collapsing the whole
guarantee this section exists to state. `build_setup_inputs` now rejects a sheet whose three role
intervals are not pairwise distinct, raising before the policy ever sees it.

## 6. Multi-timeframe roles

Following the repository's own CONTEXT/SETUP/EXECUTION roles (`fmis.pipeline.multi_timeframe`,
`PROJECT_SPECIFICATION_V1.md` §5), with responsibilities stated once and enforced by where each role's
facts are read:

- **CONTEXT** — is the broader environment supportive of a direction at all. Feeds the regime gate and
  one directional family.
- **SETUP** — does a swing thesis exist. Feeds the second directional family and the evidence family;
  its `nearest_levels`/`structure.levels` are the reference for a target candidate one timeframe out.
- **EXECUTION** — has the thesis actually confirmed enough to act. Never votes on direction (kept
  structurally separate so it can only confirm or withhold, never manufacture a candidate on its own).
  `CANDIDATE → CONFIRMED` requires a matching, **recent** `StructureBreak` and the EXECUTION structural
  trend to not be `SUSTAINED` in the opposite sense. Either failing leaves the result at `CANDIDATE` —
  explicitly the brief's own disagreement case: context and setup supportive, execution unconfirmed,
  never silently promoted.

**"Latest matching break", not "latest break" — corrected after the independent review (§17).**
`fmis.structure_break` can emit an upper and a lower break on **one** bar, ordered upper-before-lower,
so the array's positional last element always resolves toward the lower side on a tie — a real,
provable directional asymmetry the review found. `SetupInputs.execution_breaks` now carries the
**full** ordered break history, and the policy searches it backward for the most recent break whose
side matches the candidate's confirming side, rather than trusting a single precomputed "latest"
regardless of side.

**Recency is a stated policy, not an assumption.** The review also found that "latest" carried no
freshness bound at all: a break from months earlier, with no bearing on a candidate that only just
formed, could confirm it. `CONFIRMATION_LOOKBACK_BARS` (10, a module constant beside
`MINIMUM_AGREEING_FAMILIES`, the same "chosen and labelled as chosen" discipline `RegimePolicy` uses)
bounds how many of the most recent execution-timeframe bars a confirming break may fall within. A
break outside that window leaves the result at `CANDIDATE`, with its age stated.

## 7. Entry / confirmation

No exact entry price is fabricated. `CANDIDATE` reports a `Trigger` naming what is being watched for —
the nearest same-direction structural level on the EXECUTION view — using `AWAITING_STRUCTURE_BREAK`.
`CONFIRMED` reports `CONFIRMED_STRUCTURE_BREAK`, naming the EXECUTION `StructureBreak` that already
occurred, by reference, with its bar index. Both trigger kinds are `derive_structure_breaks`' own
concept (a `CLOSE_BREACH` at or after a level's `knowable_from`), never a candle inspected here: closed
candles only, no forming candle, no look-ahead, inherited entirely from the layers below.

## 8. Stop / invalidation

Deterministic and structural, or absent — never a percentage. For a `LONG`, the stop is the
EXECUTION view's `PriceLevel` with `side=LOWER` nearest below the last close (the swing low whose loss
invalidates the thesis); for `SHORT`, the nearest `UPPER` level above close. If no level of the
required side exists in the window, `stop=None` — never a fabricated one. Thesis invalidation
(`invalidation`, prose) and the execution stop (`stop`, a `PriceLevel`) are reported as two separate
fields precisely because the task brief asks them kept separate when the system cannot prove they
are identical; v1 states them as the same level and says so.

## 9. Targets

The nearest opposite-side structural level from the SETUP view (one timeframe out from EXECUTION,
following the same "higher timeframe carries the more significant level" reasoning
`fmis.pipeline.multi_timeframe` documents) — for `LONG`, the nearest `UPPER` level above the
EXECUTION close; for `SHORT`, the nearest `LOWER` level below it. `targets` is a tuple so a future
milestone can add a second candidate without a shape change; v1 populates at most one. Absent when no
such level exists, per the same rule as the stop.

**Invariant, enforced by the model, not merely by the policy:** `LONG` requires
`stop < entry < target`; `SHORT` requires `target < entry < stop`, wherever entry, stop and a given
target are all present. A geometry violation raises rather than renders — see §12.

## 10. Risk / reward

Computed in code, never asked of AI, exactly when entry, stop and a target are all present, on the
same side, and dimensionally sane:

```
LONG:  reward = target - entry   risk = entry - stop
SHORT: reward = entry - target   risk = stop - entry
```

`RiskReward.ratio = reward / risk`. Zero or negative risk, a non-finite value, or a target on the
wrong side are rejected by the model's own validation rather than rendered — `risk_reward=None` and
the reason is folded into `limitations`.

## 11. Probability

`probability.status` is always `ProbabilityStatus.NOT_CALIBRATED` in v1; `probability.value` is
structurally `None` whenever it is. No number, band, "high probability", or confidence score is ever
printed. This is deliberate product-integrity policy per the task brief, not an oversight — the seam
for a future calibrated model is the enum gaining a second member and the field being populated only
then.

## 12. Model invariants

`SetupAssessment.__post_init__` enforces, unconditionally:

- `direction is None` iff `state is SetupState.WAIT`.
- `risk_reward is not None` only if `stop is not None` and `targets` is non-empty.
- Every `PriceLevel` referenced by `stop`/`targets`/`trigger.level` is on the side geometry requires
  for the stated `direction` (`LOWER` below for a `LONG` stop, etc.) — a policy bug that picked the
  wrong side cannot be constructed into a result at all.
- `schema_version` and `policy_id` are always present.

## 13. Position sizing and probability — explicitly out

No money, no portfolio, no leverage, no position size anywhere in this package or its renderer. The
existing 2% hard-maximum portfolio-risk rule is not touched and nothing here computes toward it.

## 14. CLI

`fmits setup SYMBOL [SYMBOL ...]` — one or more symbols, in requested order. One full assessment page
per symbol, sequential, each symbol isolated: a provider/insufficient-data failure for one symbol
prints as a failure block and does not stop the remaining symbols, mirroring `fmis.daily`'s isolation
contract without importing `fmis.daily` (ADR-0028 §3). No ranking, no score, no sort — output order is
input order, always.

## 15. Reuse — nothing recomputed

No indicator, no swing detection, no BOS/CHoCH, no regime, no evidence grouping, no decision-context
verdict is recomputed. `fmis.swing_setup` calls `multi_timeframe_facts_for_symbol`,
`regime_for_sheet`, `build_evidence_report` and `evaluate_context` exactly as `fmis.workspace` does,
and reads `StructureBreak`/`PriceLevel`/`StructuralTrendType` by reference. The ~20 lines of adapter
plumbing duplicated from `fmis.workspace.builder`'s pattern are recorded, and accepted, in
[ADR-0028](../adr/ADR-0028-directional-interpretation-boundary.md).

## 16. Testing strategy

Expected values for every policy branch are derived by hand from the family-tally table in §5, never
by calling the policy under test. Symmetry is tested by mirroring every `LONG` fixture into its
`SHORT` counterpart (swap every trend/alignment/side member for its opposite) and asserting the
outputs are structural mirrors — same state, opposite direction, mirrored stop/target ordering, equal
risk/reward magnitude.

## 17. Independent review

A fresh, adversarial review (re-deriving claims from source rather than trusting this document) found
three real P1s before release, all fixed and each now covered by a named regression test:

1. **Same-bar dual-break tie always resolved toward the LOWER side** — a `LONG` candidate could stay
   unconfirmed on a bar where a `LONG`-confirming `UPPER` break and an unrelated `LOWER` break shared
   one bar, because `latest_break` is the level-crossing engine's own positional order, not a
   direction-aware search. Fixed by carrying the full break history and searching it by side (§7).
2. **No recency bound on a confirming break** — a break from months earlier could confirm a candidate
   that only just formed. Fixed by `CONFIRMATION_LOOKBACK_BARS` (§7).
3. **CONTEXT/SETUP interval collision defeated the ≥2-independent-families guarantee** — reachable
   with one CLI flag (`--context 1d --setup 1d`), with nothing rejecting it. Fixed by validating the
   three role intervals are pairwise distinct in `build_setup_inputs` (§5).

A cosmetic P3 — the risk/reward block's reference price was labelled `entry`, reading as more
actionable than the design's own "no exact entry is fabricated" claim (§7) intended — was also fixed:
relabelled `reference ... (not an order price)`.

Full record: [`docs/reviews/SWING_SETUP_ENGINE_V1_REVIEW.md`](../reviews/SWING_SETUP_ENGINE_V1_REVIEW.md).
