# ADR-0028: Directional interpretation boundary — where LONG/SHORT may exist

**Status:** Accepted
**Date:** 2026-08-07
**Milestone:** AR — Swing Setup Engine v1

## Context

Every deterministic engine in this repository refuses direction on purpose, and each refusal is
already an accepted decision: `fmis.market_structure` names `HIGHER_HIGH`/`LOWER_LOW` and stops
there (ADR-0012/0014); `fmis.structural_trend` reports `SUSTAINED_HIGHER`/`SUSTAINED_LOWER` as
facts about structure, never as a reason to buy (ADR-0017); `fmis.market_regime` classifies the
*environment* and cannot represent a bullish or bearish regime at all (ADR-0025); `fmis.decision_support`
groups evidence by alignment but its own vocabulary guard bans `long`/`short`/`buy`/`sell` from every
value it produces (ADR-0008); `fmis.pipeline.multi_timeframe` reports timeframes side by side and
derives nothing from their combination (ADR-0023); `fmis.workspace`'s rendered `fmits swing` page is
scanned end to end for `entry`, `target`, `buy`, `sell`, `recommend`, `confidence`, `score`, `verdict`
(`tests/test_workspace_render.py`), and its TRADE PLAN section is explicitly `Unavailable`, owned by
epic EP-13, with the stated reason *"entry, invalidation, stop, target and risk/reward are not
computed by this system."`

The owner's stated first priority (`docs/AI_HANDOFF/ADR_IMPLEMENTATION_GATE.md`, Finding I) is a
system that turns this into an explicit swing-trade setup — a directional candidate with entry,
invalidation, stop, target and risk/reward. That capability cannot be built without direction
existing *somewhere*, and until now no document has said where.

## Decision

**A new package, `fmis.swing_setup`, is the one place directional trade vocabulary is allowed to
exist**, plus its one necessary consumer at the outermost edge, `fmis.pipeline.cli`.

1. `fmis.swing_setup` is a top-level application/domain layer, at the same tier as `fmis.workspace`
   — not below it and not inside it. It consumes the public surfaces of `fmis.pipeline`
   (`multi_timeframe`, `regime`), `fmis.decision_support`, `fmis.decision_context`,
   `fmis.market_regime`, `fmis.level_crossing` (`LevelSide`, `PriceLevel` — types only),
   `fmis.structural_trend` (`StructuralTrendType`), and `fmis.structure_break` (`StructureBreak`).
   It computes no market quantity a lower engine already computes — it interprets already-produced
   facts under an explicit, testable policy, which is exactly what `ARCH` §9 reserves for a layer
   like this.
2. Directional vocabulary — `LONG`, `SHORT`, and the words `entry`/`stop`/`target`/`trigger` used in
   their trading sense — may appear only in `fmis.swing_setup`'s own modules
   (`models.py`, `policy.py`, `render.py`, `compose.py`) and in `pipeline/cli.py`, which already holds
   the one necessary exception for `fmis.archive` (ADR-0027) and gains a second, same-shaped one here:
   it is the outermost edge and already imports every top-level product surface directly.
3. `fmis.swing_setup` never imports `fmis.workspace`, `fmis.daily` or `fmis.archive` — it needs
   nothing from any of them, and importing one would create a peer-to-peer dependency between two
   top-level product surfaces with no basis in the data either needs. It duplicates two small
   (10–20 line) pure adapters that `fmis.workspace.builder` also has —
   `snapshot_from_sheet`-equivalent and `context_input_from_facts`-equivalent — rather than importing
   them; see "Consequences" for why that duplication is accepted rather than avoided.
4. Every requirement the existing engines already enforce keeps applying unchanged: closed candles
   only, no epsilon comparisons, immutable results, and the layering direction in
   [`REPOSITORY_MAP.md`](../REPOSITORY_MAP.md) — nothing below `fmis.swing_setup` may import it.
5. A repository-wide guard test (`tests/test_directional_vocabulary_boundary.py`) scans the source
   text of every package **except** `fmis.swing_setup` for the same forbidden-word list the existing
   page-scoped and package-scoped guards already use, so a future change that leaks `LONG` into
   `fmis.features` or `fmis.market_structure` fails a test rather than a review. This is additive to,
   and does not replace or weaken, the narrower guards already in place
   (`test_workspace_render.py`, `test_daily_models.py`, `test_workspace_build.py`).
6. A directional candidate may never be formed from a single evidence family, and never when
   `fmis.decision_context` reports `INSUFFICIENT` — both enforced in `fmis.swing_setup.policy`, not
   merely documented. `WAIT` (no directional candidate) is a first-class, successful result, not an
   error and not a degraded case.

## Alternatives considered

- **Extend `fmis.workspace`'s TRADE PLAN section directly.** Rejected: `fmits swing`'s rendered page
  is scanned in full for trading vocabulary by an existing, accepted test contract
  (`test_workspace_render.py`). Putting direction there would force that test to be rewritten rather
  than narrowed, and would make every existing consumer of `fmis.workspace` (`fmis.daily`,
  `fmis.archive`) a directional producer by accident.
- **Put the directional policy inside `fmis.decision_support` or `fmis.market_regime`.** Rejected
  outright by ADR-0008 and ADR-0025's own text — both packages are accepted specifically *because*
  they cannot represent a direction.
- **A generic pluggable "interpretation layer" framework.** Rejected as unnecessary abstraction for
  a milestone that needs exactly one new package; CLAUDE.md's working principles reject speculative
  infrastructure the task does not require.

## Consequences

**Positive.** The owner's first priority becomes buildable without touching any existing accepted
ADR boundary. Every existing non-directional guarantee is not just preserved but gains a positive,
repository-wide test rather than remaining implicit in a handful of page-scoped scans.

**Cost, stated rather than hidden.** `fmis.swing_setup` duplicates roughly 20–30 lines of pure
adapter plumbing that `fmis.workspace.builder` already has. Both pieces are trivial dataclass
construction with zero market computation, not an engine, so the duplication is judged cheaper than
the alternative — a new cross-dependency between two top-level product surfaces neither the
architecture nor the data requires.

## Enforcement

- The repository-wide guard test named above (§5), plus the standard import-boundary AST tests every
  new package receives (no engine or lower layer imports `fmis.swing_setup`; `fmis.swing_setup`
  imports only its declared allowed surfaces).
- `fmis.swing_setup.policy` tests assert: no directional candidate from fewer than two agreeing,
  independent evidence families; no directional candidate when `DecisionContext.state` is
  `INSUFFICIENT`; `WAIT` is reachable and asserted as a successful, non-exceptional result.
