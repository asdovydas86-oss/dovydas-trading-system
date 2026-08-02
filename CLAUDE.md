# CLAUDE.md

Project-level instructions for AI coding agents working in this repository.

> Engineering rules, architecture boundaries and milestone workflow are **not** restated here.
> They live in [`docs/AI_HANDOFF/START_HERE_FOR_AI.md`](docs/AI_HANDOFF/START_HERE_FOR_AI.md),
> [`docs/README.md`](docs/README.md) and the ADRs under [`docs/adr/`](docs/adr/). Read those first.
>
> **Where they disagree, the ADRs win.** `START_HERE_FOR_AI.md` is a useful orientation document but
> is known to lag: it predates `series_context`, `structural_trend`, `level_crossing`,
> `structure_break` and `change_of_character`. The live repository and the ADRs are authoritative.

## Product documents

Two living documents track execution and capability. Keep them current:

- [`FMITS_PRODUCT_BACKLOG.md`](FMITS_PRODUCT_BACKLOG.md) — the execution board. Exactly one NOW item.
  A status only moves to DONE on evidence from the repository, never from a plan.
- [`FMITS_PRODUCT_CHANGELOG.md`](FMITS_PRODUCT_CHANGELOG.md) — user-visible capability only. Never
  record documentation or refactors as a product release.

## Working principles

**Product first.** The objective is a production-quality system the owner uses daily — not
documentation, architecture or reports. Those exist to support implementation. A task that produces
documentation without creating long-term product value should be questioned.

**Every milestone must increase product value.** Ask what the owner can do after a milestone that was
impossible before. Greater internal complexity alone is not sufficient value.

**Deterministic first, AI second.** If a value can be computed objectively, code computes it; AI is
never asked to estimate what arithmetic can produce. AI interprets structured facts — conflicts,
scenarios, uncertainty, the strongest opposing case — and never produces the facts themselves.

## Git safety

**Never commit, merge, rebase, tag or push without explicit authorization from the owner.** Reading,
running tests and inspecting history need no permission; changing history or the remote always does.

- **Never** `push --force`, `--force-with-lease`, `--all`, `--mirror`, or push tags.
- Push `main` only, and only when explicitly told to.
- Never amend, squash or rebase a commit that has been reported to the owner.
- Before any push, verify: branch · clean working tree · untracked files · stash · unresolved
  operation · ahead/behind · fast-forward ancestry · exact commit range · tests · public exports.
- After any push, verify `HEAD`, local `main`, `origin/main` and `git ls-remote` all match.
- Stop and ask when the repository state does not match what the task assumed.

## Operational reports

Dated, numbered, point-in-time records of work performed on the repository — audits, design
records, implementation records, reviews. Distinct from `docs/`, which holds the project's
standing documentation.

**All reports live in [`reports/`](reports/). Never create a generic `REPORT.md` in the
repository root.**

### Filename convention

```
NNNN_YYYY-MM-DD_DESCRIPTIVE_TITLE.md
```

`NNNN` zero-padded four digits · `YYYY-MM-DD` production date · title in UPPERCASE_SNAKE_CASE.

Example: `0002_2026-08-01_LEVEL_ORIGIN_DESIGN.md`

### Rules

- Numbering is **global and sequential across all report types** — one shared counter for design,
  implementation, review and audit reports.
- **Never overwrite or reuse a number**, including for archived or superseded reports.
- Open each report with a metadata header: report number, title, date, report type, model,
  repository branch, audited commit, status.
- **Every new report must be added to the index table in [`reports/README.md`](reports/README.md)**
  in the same change that creates it, and the "next available report number" there must be bumped.
- Active and recent reports stay directly in `reports/`. Older or superseded reports may be moved
  to `reports/archive/` — they keep their number and their index row; only the link and status
  change.
- **Never delete a report** unless the user explicitly authorizes deletion.
