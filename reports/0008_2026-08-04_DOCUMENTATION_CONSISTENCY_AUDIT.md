# Documentation Consistency Audit

| Field | Value |
|---|---|
| **Report number** | 0008 |
| **Title** | Documentation Consistency Audit |
| **Date** | 2026-08-04 |
| **Report type** | Audit |
| **Model** | Claude Sonnet 5 |
| **Repository branch** | `main` |
| **Audited commit** | `36f5a30` |
| **Status** | Final |

---

## Scope

A full read of the AI onboarding flow (`docs/AI_HANDOFF/START_HERE_FOR_AI.md` →
`CURRENT_STATE.md`), every document under `docs/`, `reports/`, and the repository root, checking
for duplicated explanations, obsolete text, stale milestone references, contradictory wording,
broken links, and naming inconsistency. Requested by the owner as a repository-quality pass before
resuming feature work on Milestone AO. Documentation only — no backlog, changelog, milestone-state,
or architecture-redesign changes were in scope, and none were made.

---

## A. Problems found

1. **Root `README.md` never mentioned FMITS.** It described the repository purely as a "trading
   automation workspace" of `config/`, `scripts/`, `docs/`, `prompts/` — omitting `src/fmis/` (the
   actual ~11,000+ LOC Python product, 3,905 tests) and `tests/` entirely, and never using the name
   "FMITS." This is the first file a human or external reader opens, and it described a pre-FMITS
   scaffold. **[Critical — fixed]**

2. **`docs/ARCHITECTURE_AND_ROADMAP_V1.md` is required reading (`docs/README.md`'s reading order,
   step 4 for both humans and AI) but its §2 "Current repository state" is frozen at a 147-test,
   two-package baseline** (`e0ba4c1`) against a live repository of 30+ packages and 3,905+ tests,
   with no notice pointing a reader at what superseded it. Its §4 status tags mark shipped modules
   (Provider Adapters, the Relative Value Engine, Market Regime) `deferred`/`planned`; §8 describes
   market-structure/trend as future Tier-2 packages inside the Feature Engine, when
   [ADR-0012](../docs/adr/ADR-0012-market-structure-foundation.md) built them as separate top-level
   packages instead; §9 sketches a single-label Market Regime Engine when the shipped design
   (ADR-0025) is three never-collapsed dimensions; §10's roadmap (Milestones K/L/M/N) was abandoned
   after Milestone J with no note. **[Critical — banners added]**

3. **`docs/RVE_DESIGN_V1.md` §7** presents Milestones K (v1b) and L (v1c) as pending staged work.
   CURRENT_STATE.md records this split as superseded by ADR-0004's v1a/v1b scoping, but the source
   document itself carries no matching note. **[High — banner added]**

4. **`docs/adr/ADR-0020` and `ADR-0023`** each describe ADR-0020 D1 (the confirmation-delay hazard)
   as an open, unfixed problem. Both are point-in-time records — correctly never rewritten — but
   neither carries a forward pointer to [ADR-0024](../docs/adr/ADR-0024-confirmation-delay-provenance.md),
   which closed D1 one and two milestones later respectively. A reader landing on either ADR
   directly (not via the index, which does track this) could believe the hazard is still live, or
   reimplement ADR-0020 §7's `zip()` CHoCH sketch that ADR-0021 found and marked wrong.
   **[High — "Later note" annotations added, per this directory's own convention that a superseded
   ADR is marked, not rewritten]**

5. **`reports/README.md`'s "Implementation milestones executed from these reports" table listed
   only Milestone AF**, despite the table's own stated purpose ("links each executed milestone to
   its technical records") and six more shipped milestones (AG, AH, AI, AK, AL, AN) whose contracts
   trace back to this report series (report 0006 §5 directly commissioned AG). **[High — table
   extended with sourced, verified commit/record links]**

6. **`docs/AI_HANDOFF/CURRENT_STATE.md`'s "Repository status" section is now factually wrong.**
   It states Milestone AN is "committed locally and deliberately NOT pushed" and that `main` is
   ahead of `origin/main` by two commits. Verified against live git state: `74036a4` (AN) **is**
   an ancestor of `origin/main`, and five further commits have landed and pushed since, including
   the two AI-workflow-policy documentation commits at `HEAD`. The identical stale claim is
   duplicated in `FMITS_PRODUCT_BACKLOG.md` (§4, "behind local main by the two AN commits; not
   pushed"), whose own "Last verified against" header (line 14, `a728f3b9f1d...` / Milestone AL)
   also lags one milestone behind its own body content (§4 is already written for AN/AO).
   **[Critical — reported only; both files are explicitly out of scope for this pass: the task
   instructions forbid changing milestone state in `CURRENT_STATE.md` and forbid backlog edits]**

7. **`FMITS_PRODUCT_CHANGELOG.md` §5 "Upcoming"** still lists Milestone AN as unreleased/not
   started, contradicting §3 and §4 of the *same file*, which record AN as released with a commit
   SHA and full test evidence. **[Critical — reported only; changelog edits are out of scope]**

8. **`docs/AI_HANDOFF/CURRENT_STATE.md` (1,108 lines) carries the full narrative prose for every
   milestone back to the project's start**, not only the current one, substantially duplicating
   content that already lives in each milestone's paired design document and review record (which
   `docs/README.md` already indexes with a one-paragraph summary each). The per-module test-count
   table (lines ~766–801) is explicitly self-flagged in the document as unmaintained since
   Milestone AG and 45% short of the real total — kept as a ~35-line table behind a caveat rather
   than removed. **[High — reported only; restructuring this file is milestone-state surgery, out
   of scope for this pass and risky without owner sign-off]**

9. **No broken relative markdown links** were found anywhere in `docs/`, `reports/`, or the root
   (79 files checked programmatically). **`git diff --check` is clean** on every edit made.

10. **Naming is materially consistent.** "Decision Context Engine" (used in `CURRENT_STATE.md` and
    `docs/README.md`) is a step more definite than ADR-0026's own "Decision Context boundary" /
    `fmis.decision_context`, a minor terminology looseness rather than an ambiguity — no two names
    refer to different things anywhere checked. "Deterministic Daily Workflow" vs. bare "Daily
    Workflow," and "Swing Trading Workspace" vs. bare "Swing Workspace," each occur exactly where
    expected: inside `reports/` documents dated *before* the milestone was built and formally named
    (reports are point-in-time and correctly never revised for terminology that hadn't been decided
    yet). **[Low — no action]**

---

## B. Recommended improvements (not implemented this pass)

| # | Recommendation | Why not implemented now |
|---|---|---|
| R1 | Correct `CURRENT_STATE.md`'s "Repository status" push-state claim (finding 6) and the mirrored claim in `FMITS_PRODUCT_BACKLOG.md`. | Explicitly out of scope: no milestone-state or backlog changes authorized for this pass. Needs an owner-authorized update as its own small change. |
| R2 | Fix `FMITS_PRODUCT_CHANGELOG.md` §5 to describe AO (the actual current NOW item) instead of the already-shipped AN (finding 7). | Changelog edits explicitly out of scope. |
| R3 | Restructure `CURRENT_STATE.md` so only the current milestone's full narrative stays inline, with earlier milestones trimmed to the one-line summary already in `docs/README.md`'s index (or moved to a dedicated history file the current doc links to). This is the single largest future-AI reading-cost item in the repository. | Large structural change to the most special-cased document in the repo; carries real risk of information loss or broken internal cross-references without owner review; also brushes against the "do not change milestone state" instruction for this pass. |
| R4 | Add resolution status for `ARCHITECTURE_REVIEW_2026-07-24.md` findings R4, R6, R7, R8, R10, R13, R14, which are absent from `CURRENT_STATE.md`'s "Known open items" table and currently undiscoverable without a source dive. | Medium value, needs someone to actually re-derive each finding's current status against the live code — a research task, not a documentation-hygiene edit. |
| R5 | Reconcile `reports/0005`'s Phase 3/4 roadmap scope (support/resistance, volatility state, scanning, brief, scheduling, persistence) against what AG–AN actually shipped, which diverged substantially with no note anywhere explaining the narrowing. | Judgment call on which items were dropped vs. deferred vs. substituted; better done by whoever plans Milestone AO, since it bears directly on that scope decision. |
| R6 | Normalize "Swing Workspace" → "Swing Trading Workspace" at `FMITS_PRODUCT_BACKLOG.md` line 520 (D-06 row) for internal consistency. | Backlog edits out of scope. |
| R7 | Standardize "Decision Context Engine" vs. ADR-0026's own "Decision Context boundary" naming on one term repository-wide. | Low value, cosmetic; risks unnecessary churn across several files for a distinction that causes no actual ambiguity. |

---

## C. Estimated token savings for future AI sessions

- **Immediate (this pass):** an AI or human landing on `ARCHITECTURE_AND_ROADMAP_V1.md`,
  `RVE_DESIGN_V1.md`, `ADR-0020`, or `ADR-0023` directly (outside the guided reading order) no
  longer has to cross-reference `CURRENT_STATE.md` from scratch to discover the section is stale —
  the banner states it inline. This mainly prevents a **wrong belief**, which is a correctness
  saving more than a token-count saving; the added banners total ~50 lines against a combined
  ~2,300 lines across the four files touched.
- **Largest unrealized opportunity (R3, not implemented):** `CURRENT_STATE.md` is read by every
  session per `START_HERE_FOR_AI.md`'s stated minimum, and its ~900 lines of full historical
  milestone narrative (roughly 25,000–30,000 tokens) duplicate content already summarized in
  `docs/README.md`'s index and detailed in each milestone's design/review pair. Trimming completed
  milestones to their existing one-paragraph index summary, keeping only the current milestone's
  full detail, would cut the document a session actually needs to read by an estimated **70–80%**
  for the common case (most tasks only need the current milestone, per `START_HERE_FOR_AI.md` §8's
  own instruction to read only that section) — this is deferred to R3 above rather than attempted
  in this pass.
- The `reports/README.md` table extension (finding 5) *adds* ~6 lines but *saves* a future reader
  from having to reconstruct six milestones' contract lineage by grepping `reports/` — a small
  addition in exchange for avoiding a larger ad hoc search each time it's needed.

---

## D. Priority

**Critical**
- Root `README.md` omitting FMITS entirely — **fixed**.
- `ARCHITECTURE_AND_ROADMAP_V1.md` §2 required-reading staleness — **fixed** (banners).
- `CURRENT_STATE.md` / `FMITS_PRODUCT_BACKLOG.md` stale push-state claim — **reported only**,
  out of scope this pass (R1).
- `FMITS_PRODUCT_CHANGELOG.md` §5 stale AN-as-upcoming block — **reported only**, out of scope
  this pass (R2).

**High**
- `ARCHITECTURE_AND_ROADMAP_V1.md` §4/§8/§9/§10 stale status tags and roadmap — **fixed** (banners).
- `RVE_DESIGN_V1.md` §7 stale staged-scope — **fixed** (banner).
- ADR-0020 / ADR-0023 missing forward pointers to ADR-0024 — **fixed** (header notes).
- `reports/README.md` incomplete milestone-execution table — **fixed** (extended).
- `CURRENT_STATE.md` size/duplication (R3) — **recommendation only**.
- `FMITS_PRODUCT_BACKLOG.md` verification-anchor header lagging one milestone — **reported only**,
  out of scope this pass.

**Medium**
- `ARCHITECTURE_REVIEW_2026-07-24.md` orphaned findings (R4) — **recommendation only**.
- `reports/0005` Phase 3/4 roadmap divergence unreconciled (R5) — **recommendation only**.

**Low**
- Backlog naming nitpick (R6), Decision Context Engine/boundary terminology (R7) — **recommendation
  only**.

---

## Files changed

| File | Change |
|---|---|
| `README.md` | Rewrote opening description and `## Structure` list to include FMITS, `src/fmis/`, `tests/`, `reports/` |
| `docs/ARCHITECTURE_AND_ROADMAP_V1.md` | Added four staleness banners (§2, §4, §8, §9, §10) pointing to `CURRENT_STATE.md`, `REPOSITORY_MAP.md`, and the relevant ADRs |
| `docs/RVE_DESIGN_V1.md` | Added a staleness banner to §7 pointing to ADR-0004 |
| `docs/adr/ADR-0020-break-of-structure-foundation-v1.md` | Added a "Later note" header line pointing to ADR-0024 and ADR-0021 |
| `docs/adr/ADR-0023-multi-timeframe-composition.md` | Added a "Later note" header line pointing to ADR-0024 |
| `reports/README.md` | Extended the milestone-execution table with AG, AH, AI, AK, AL, AN rows; bumped next report number |

No production code, tests, backlog, changelog, or milestone-state files were modified. No
architecture was redesigned. Milestone AO was not started.
