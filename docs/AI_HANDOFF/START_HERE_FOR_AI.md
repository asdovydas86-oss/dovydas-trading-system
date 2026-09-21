# Start Here — For AI Agents and Engineers

**This is the cold-start entry point for every session in this repository.**

It does not restate what other documents say correctly. It tells you **where current truth lives**,
**what you must verify before acting**, and **what you must never assume**. Read it, then open only
the sources it routes you to for your actual task.

If a task instruction conflicts with a rule linked from here, **stop and surface the conflict** rather
than guessing.

> ## ⏸ FMITS IS PAUSED (2026-09-21)
>
> **The project was paused indefinitely by the owner on 2026-09-21, at a clean and fully pushed
> repository.** Before anything else, read
> **[`FMITS_PROJECT_PAUSE_2026-09-21.md`](FMITS_PROJECT_PAUSE_2026-09-21.md)** — it carries the exact
> state at pause, the cold-start procedure, the unresolved market-model problem, and a warning about
> **16 uncommitted research documents (1.1 MB) that exist only in the working tree.**
>
> **There is no NOW milestone, and selecting one is the owner's decision, not a resuming session's.**

---

## 1. What FMITS is

**FMITS** — Financial Market Intelligence & Trading System.

It is **not merely a trading bot.** It is a personal Financial Market Intelligence **operating
environment**, covering over time: technical analysis · swing trading · long-term investing · global
markets · crypto · stocks · macro · geopolitics · news · on-chain · derivatives · flows · China ·
IPO/special opportunities · portfolio intelligence · risk · research · backtesting · paper/shadow
trading · reporting/delivery · and carefully controlled execution **much later**.

**The immediate product priority is Swing Trading / Technical Market Intelligence.** That is a
priority, not the boundary of the project — narrowing FMITS to swing trading would be a change of
scope, not a simplification.

The architecture:

```
deterministic computation → structured evidence → interpretation/context → scenarios
    → human decision → validated automation much later
```

---

## 2. Non-negotiable principles

Read these before proposing anything. They override convenience, elegance and enthusiasm.

- **Product first.** The objective is a production-quality system the owner uses daily. Documentation,
  architecture and reports exist to support implementation, not to replace it.
- **Every milestone must increase product value.** *What can the owner do after this that was
  impossible before?* Greater internal complexity alone is not value.
- **Deterministic first, AI second.** If a value can be computed objectively, code computes it. AI
  interprets structured facts — conflicts, scenarios, uncertainty, the strongest opposing case — and
  **never produces the facts themselves**.
- **No simplistic indicator rules.** *RSI oversold = buy* is exactly what this system exists to refuse.
- **No LONG bias. No SHORT bias.**
- **No correlated-indicator vote inflation.** More indicators ≠ more independence. See
  [`CAPABILITY_REGISTRY.md`](CAPABILITY_REGISTRY.md) §3 — it is measured, not asserted.
- **`WAIT` and `NO TRADE` are valid, successful outcomes.**
- **Strategies must be explicit, testable, version-controlled and validated.** The ladder is:
  research → explicit rules → historical backtesting → robustness / out-of-sample → paper trading →
  shadow mode → small controlled live testing → gradual scaling.
- **Capital preservation is primary.** **2 % per-trade portfolio risk is a HARD MAXIMUM** under
  current accepted policy — never a default, never a target.
- **Long-term investing and Swing Trading are separate disciplines and separate books.** Swing
  capital is a separate capital domain from long-term investing and from future day trading.
  **One book must never size another.**
- **TradingView MCP is an adapter, not the permanent core.**
- **Never expose or commit secrets. No automated trading system may ever have withdrawal
  permissions.**

Full statements: [`CLAUDE.md`](../../CLAUDE.md) · [`PROJECT_SPECIFICATION_V1.md`](../../PROJECT_SPECIFICATION_V1.md) ·
[`PROJECT_VISION_ADDENDUM_V1.md`](../../PROJECT_VISION_ADDENDUM_V1.md).

---

## 3. Source authority hierarchy

**When two sources disagree, do not silently pick one.** Work out *what kind* of disagreement it is —
technical state, architecture policy, product intent, or historical planning — then apply this order:

| # | Source | Authoritative for |
|---|---|---|
| **1** | **Live repository + tests** | **Current technical truth.** Always wins on *what the code does* |
| **2** | **Accepted ADRs** ([`../adr/README.md`](../adr/README.md)) | Architecture and policy truth |
| **3** | [`PROJECT_SPECIFICATION_V1.md`](../../PROJECT_SPECIFICATION_V1.md) + [`PROJECT_VISION_ADDENDUM_V1.md`](../../PROJECT_VISION_ADDENDUM_V1.md) | Approved product intent and long-term scope |
| **4** | Newer accepted milestone/design/review reports | Decisions and verified findings **for their audited baseline** |
| **5** | [`CURRENT_STATE.md`](CURRENT_STATE.md) | Current operational summary and continuity entry point |
| **6** | [`CAPABILITY_REGISTRY.md`](CAPABILITY_REGISTRY.md) | Capability status index |
| **7** | [`../../FMITS_PRODUCT_BACKLOG.md`](../../FMITS_PRODUCT_BACKLOG.md) / [`CHANGELOG`](../../FMITS_PRODUCT_CHANGELOG.md) | Planning state / product history |
| **8** | Older roadmap / master-map / architecture-history documents | **Historical planning context only — never automatic current-state truth** |

**Never rewrite a historical report to make it look current.** Reports are point-in-time evidence.
When a report's conclusion is later reviewed or overturned, record that in a **separate** review
record — as was done for report 0047 in
[`../reviews/REPORT_0047_REVIEW_DISPOSITION.md`](../reviews/REPORT_0047_REVIEW_DISPOSITION.md).

---

## 4. Where everything is

| I need... | Go to |
|---|---|
| **Current state** — verified commit, tests, product surface, next milestone | [`CURRENT_STATE.md`](CURRENT_STATE.md) — **read the block at the top** |
| **Capability status** — what exists, what is partial, what is deferred and **why** | [`CAPABILITY_REGISTRY.md`](CAPABILITY_REGISTRY.md) |
| **Architectural decisions** — binding, one per file | [`../adr/README.md`](../adr/README.md) |
| **The backlog** — NOW / NEXT / LATER / DONE | [`../../FMITS_PRODUCT_BACKLOG.md`](../../FMITS_PRODUCT_BACKLOG.md) |
| **Product history** — what the owner could do, and from when | [`../../FMITS_PRODUCT_CHANGELOG.md`](../../FMITS_PRODUCT_CHANGELOG.md) |
| **Milestone reports** — audits, implementations, reviews | [`../../reports/README.md`](../../reports/README.md) index |
| **Session handoffs** — what happened last session, and the exact next step | [`daily/`](daily/) — newest file |
| **Design docs + their reviews** | [`../README.md`](../README.md) index · [`../design/`](../design/) · [`../reviews/`](../reviews/) |
| **Directory import rules** — what may import what | [`../REPOSITORY_MAP.md`](../REPOSITORY_MAP.md) |
| **Git safety rules** | [`CLAUDE.md`](../../CLAUDE.md) — read before any commit or push |
| **Model / cost policy** | [`../development/AI_ENGINEERING_WORKFLOW_AND_COST_POLICY.md`](../development/AI_ENGINEERING_WORKFLOW_AND_COST_POLICY.md) |
| **Rules to paste into a ChatGPT project** | [`CHATGPT_PROJECT_INSTRUCTIONS.md`](CHATGPT_PROJECT_INSTRUCTIONS.md) |

---

## 5. Startup ritual

**Before** recommending or performing architecture work, a new milestone, a capability-status claim,
an implementation, a roadmap change or a major refactor:

1. Read this document.
2. Read [`CURRENT_STATE.md`](CURRENT_STATE.md) — the current-state block at the top.
3. Read [`CAPABILITY_REGISTRY.md`](CAPABILITY_REGISTRY.md).
4. Read the **newest** file in [`daily/`](daily/).
5. Read the backlog/changelog if you are planning product work.
6. Read the relevant ADR / spec / report for the domain you are about to change.
7. **Verify the live Git state** — §6 below.
8. **Inspect the live implementation before claiming any capability status.**
9. **If documentation and live code disagree, stop treating the documentation as current technical
   truth** and reconcile it.
10. Only then propose or implement the next step.

### 6. What to verify in the live repository before acting

```
pwd
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse main
git rev-parse origin/main
git ls-remote origin refs/heads/main     # when a push is in scope
git stash list
```

Also check: any active Git operation · tracked vs untracked state · relevant running FMITS/dashboard
processes (**read-only**).

**Rules:**

- **Never** reset, clean, checkout, delete, stash or overwrite anything merely to match an expected
  baseline. Preserve all existing work.
- **Never** use broad process-kill commands such as `pkill -f`.
- **If an operator dashboard is running, protect it.** The owner runs a live instance on
  `127.0.0.1:8787`. Develop on another port; restart only at handoff, and only by its exact PID.
- **Stop and ask** when the repository state does not match what the task assumed.

---

## 7. What you must NEVER assume from an old report

This repository has already experienced this failure, and it is the reason the memory documents exist.

- **Never assume a report's baseline is still HEAD.** A report is evidence about *one commit*.
- **Never assume a backlog or roadmap status is current** because it is written in a standing document.
  Only the repository and accepted ADRs can move an item to DONE.
- **Never assume `DEFERRED` means `CANCELLED`.** It never does, unless an explicit decision says so.
- **Never assume a capability is absent because you did not find it**, or present because a document
  claims it. Check `src/`.
- **Never restore a superseded old statement.** The project has progressed far beyond the August 2026
  documents. Do not reintroduce claims such as *"the only product is `fmits facts`"*, *"AG is the next
  milestone"*, *"no persistence exists"* or *"the risk engine is future work"* — all four are false
  today, and all four are still findable in older sections of this repository's own history.
- **A document that is internally stale is not thereby wrong about everything.** `CURRENT_STATE.md`
  in particular holds a current block at the top and a long historical archive below it; see its own
  header for which is which.

---

## 8. Shutdown ritual

**Event-driven — not every trivial edit produces every document.**

| Update | When |
|---|---|
| [`CURRENT_STATE.md`](CURRENT_STATE.md) | the current state changed |
| [`CAPABILITY_REGISTRY.md`](CAPABILITY_REGISTRY.md) | a capability's **status** changed |
| [`CHANGELOG`](../../FMITS_PRODUCT_CHANGELOG.md) | **user-visible product capability** changed |
| [`BACKLOG`](../../FMITS_PRODUCT_BACKLOG.md) | planning state changed |
| an **ADR** | a **binding architecture decision** changed |
| a numbered **report** | a milestone / audit / research gate warrants one |
| [`daily/YYYY-MM-DD.md`](daily/) | at the end of any meaningful project session |

Then:

1. Run the verification the work warrants (§9).
2. Commit — **only with the owner's explicit authorization**.
3. Push — **only if safe and explicitly authorized**; verify `HEAD`, local `main`, `origin/main` and
   `git ls-remote` all match afterwards.
4. **State the exact next step.**

---

## 9. Validation proportionality

Match validation to what actually changed.

- **Documentation-only work:** first *prove* `git diff -- src tests` is empty. Then validate the
  documentation — links resolve, referenced files exist, no duplicate canonical document was created,
  the source hierarchy is internally consistent, report numbering is correct, no secrets, no risk
  config created, no dashboard disturbed. A 10+ minute production suite is **not** required for
  Markdown edits.
- **Any change to `src/` or `tests/`:** the full suite under `-W error`, plus the policy
  non-regression digest and the Reliability Gate.

**Never claim "full suite green" unless you actually ran it.** Report exactly what was and was not
tested.

---

## 10. Do not create false authority

| Document | Is | Is NOT |
|---|---|---|
| Capability registry | a status index | an ADR |
| `CURRENT_STATE.md` | a current-state summary | a replacement for tests |
| A daily handoff | a continuity note | architecture authority |
| A milestone report | evidence about **one** baseline | eternal truth |
| The backlog | planning | implementation truth |
| The changelog | product history | repository truth |
| An old roadmap | historical planning | a command |

---

## 11. The current next step

**Read [`CURRENT_STATE.md`](CURRENT_STATE.md)'s current-state block — it holds the live pointer, and
this document deliberately does not duplicate it.** A next-step pointer written in two places drifts
in one of them, and this is the document that gets read first and updated least.

---

**When in doubt:** prefer the smaller, more reversible, better-tested change — and ask the owner
rather than guess on anything this document does not resolve.
