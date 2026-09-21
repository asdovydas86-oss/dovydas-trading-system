# Unapproved research and design documents — August 2026

**This index carries no authority and decides nothing.** It exists to classify the sixteen documents
listed below, which were written between 2026-08-06 and 2026-08-12, kept untracked for thirteen
months, and committed unchanged on 2026-09-21 to preserve them before the project was paused.

---

## Read this before reading any document it lists

> **None of these sixteen documents is approved architecture, and none of them decides anything.**
>
> They sit in `docs/design/` and `docs/reviews/` alongside **approved** designs — documents that
> were accepted and implemented by an ADR, and that `docs/README.md` indexes with statuses such as
> *"Design — implemented by ADR-0017"*. **These sixteen have no such status and never did.** Each
> states so in its own header, in its own words: *"Nothing here is decided, nothing here is an
> ADR"*, *"This document is the only artifact"*, *"Nothing here is authorization to implement"*.
>
> **The authority chain is unchanged by their being committed:** accepted ADRs under `docs/adr/`
> bind; `docs/AI_HANDOFF/CURRENT_STATE.md` §0 states current state; **the live code wins over
> every document, including this one.** A proposal in any file below is a proposal, whether or not
> Git now tracks it.

**Why they were committed anyway.** They are 15,750 lines of genuine FMITS research, design and
audit work — the reasoning behind decisions the repository later made, and the record of several it
deliberately did not make. Deleting the working tree would have destroyed them. Preserving reasoning
is not the same as endorsing it.

**They were committed byte-for-byte unchanged.** Not edited, renamed, moved, merged, deduplicated,
summarised or corrected. Several are superseded by later work, several contradict each other, and at
least one is an adversarial review of another in the same list. **All of that is left exactly as it
was.** A future reader wanting current truth should read `CURRENT_STATE.md` §0, not these.

---

## The sixteen documents

Grouped by the milestone that produced them, oldest first. "Status" is quoted from each document's
own header, not assigned here.

### Milestone AQ — ADR Phase 1 (2026-08-06 → 2026-08-07)

| Document | Date | Status, as the document states it |
|---|---|---|
| [`AP_ADR_DISCOVERY.md`](AP_ADR_DISCOVERY.md) | 2026-08-06 | *"Discovery only. Nothing here is decided, nothing here is an ADR, nothing here is a recommendation between options."* |
| [`AP_D1_D2_INVESTIGATION.md`](AP_D1_D2_INVESTIGATION.md) | 2026-08-06 | *"Investigation. Nothing here is decided, and nothing here is an ADR."* Options presented for the owner to choose between |
| [`../reviews/AP_D1_D2_INVESTIGATION_REVIEW.md`](../reviews/AP_D1_D2_INVESTIGATION_REVIEW.md) | 2026-08-06 | Independent **hostile review** of the investigation above, audited at commit `75a4f40` |
| [`IMPLEMENTATION_ROADMAP_V1.md`](IMPLEMENTATION_ROADMAP_V1.md) | 2026-08-06 | *"Executable plan. Not architecture, not an ADR, not a decision."* |
| [`ADR_IMPLEMENTATION_GATE.md`](ADR_IMPLEMENTATION_GATE.md) | 2026-08-07 | *"Assessment. Not architecture, not an ADR, not a roadmap, not an investigation."* |

### Milestones AW–BB — evidence and edge research (2026-08-08 → 2026-08-11)

| Document | Milestone · date | Status, as the document states it |
|---|---|---|
| [`EVIDENCE_FAMILY_INDEPENDENCE_RESEARCH_V1.md`](EVIDENCE_FAMILY_INDEPENDENCE_RESEARCH_V1.md) | AW · 2026-08-08 | *"Investigation complete — measurement only, no code changes"* |
| [`FMITS_INFORMATION_EDGE_RESEARCH.md`](FMITS_INFORMATION_EDGE_RESEARCH.md) | — · 2026-08-08 | *"Research only."* Written *"adversarial to the product's own self-image"* |
| [`EVIDENCE_CALIBRATION_RESEARCH_V1.md`](EVIDENCE_CALIBRATION_RESEARCH_V1.md) | AX · 2026-08-10 | *"Investigation complete — measurement only, no code changes"* |
| [`EDGE_SEGMENTATION_RESEARCH_V1.md`](EDGE_SEGMENTATION_RESEARCH_V1.md) | AY · 2026-08-10 | *"Investigation complete — measurement only, no code changes"* |
| [`FAILURE_ATTRIBUTION_RESEARCH_V1.md`](FAILURE_ATTRIBUTION_RESEARCH_V1.md) | AZ · 2026-08-10 | *"Research only — measurement only, no code changes"* |
| [`CONFIRMATION_FRESHNESS_HYPOTHESIS_RESEARCH_V1.md`](CONFIRMATION_FRESHNESS_HYPOTHESIS_RESEARCH_V1.md) | BA · 2026-08-10 | *"Investigation complete — measurement only, no code changes"* |
| [`CONFIRMATION_FRESHNESS_POLICY_DECISION_V1.md`](CONFIRMATION_FRESHNESS_POLICY_DECISION_V1.md) | BB · 2026-08-11 | *"Decision analysis complete — evidence assessment only, no code changes, no policy change"* |

### Milestones BD–BG — swing product and trading domain design (2026-08-11 → 2026-08-12)

| Document | Milestone · date | Status, as the document states it |
|---|---|---|
| [`SWING_TRADING_READINESS_AUDIT_V1.md`](SWING_TRADING_READINESS_AUDIT_V1.md) | BD · 2026-08-11 | *"Research only — audit. … This document is the only artifact."* |
| [`TRADER_WORKSPACE_PRODUCT_ARCHITECTURE_V1.md`](TRADER_WORKSPACE_PRODUCT_ARCHITECTURE_V1.md) | BE · 2026-08-11 | *"Design/research only. … This document is the only artifact."* |
| [`SWING_TRADING_MVP_BLUEPRINT_V1.md`](SWING_TRADING_MVP_BLUEPRINT_V1.md) | BF · 2026-08-11 | *"Product specification / design only. … This document is the only artifact."* |
| [`TRADING_DOMAIN_DATA_MODEL_V1.md`](TRADING_DOMAIN_DATA_MODEL_V1.md) | BG · 2026-08-12 | *"Design only. … Nothing here is authorization to implement, and nothing here is an accepted decision."* |

**Milestone labels BE, BF and BG are self-assigned.** Each of those three documents says so in its
own header — *"this document's own label. The board is not edited and no milestone is sequenced by
this document"*. They do not appear as sequenced milestones on
[`FMITS_PRODUCT_BACKLOG.md`](../../FMITS_PRODUCT_BACKLOG.md).

---

## Provenance of this preservation

| Field | Value |
|---|---|
| Written unchanged since | 2026-08-19 (file mtimes); content dated 2026-08-06 → 2026-08-12 |
| Committed | 2026-09-21, during the project pause |
| Committed onto | `79b3717` |
| Total | 16 files · 15,750 lines · 1,139,245 bytes |
| Modifications made | **none** — byte-for-byte as they were |
| Related | [`../AI_HANDOFF/FMITS_PROJECT_PAUSE_2026-09-21.md`](../AI_HANDOFF/FMITS_PROJECT_PAUSE_2026-09-21.md) §2.1 |

**Content checksums at the moment of commit** (`sha256`, first 16 hex characters), so a later reader
can confirm nothing was altered in the act of preserving them:

```
c13449304cecba1e  docs/design/ADR_IMPLEMENTATION_GATE.md
1af5a9477b65c113  docs/design/AP_ADR_DISCOVERY.md
94f61e5e3617173f  docs/design/AP_D1_D2_INVESTIGATION.md
72e232185e9db530  docs/design/CONFIRMATION_FRESHNESS_HYPOTHESIS_RESEARCH_V1.md
d1524c9790b1a071  docs/design/CONFIRMATION_FRESHNESS_POLICY_DECISION_V1.md
9386d2535a244b37  docs/design/EDGE_SEGMENTATION_RESEARCH_V1.md
8ffaa7439456d0c5  docs/design/EVIDENCE_CALIBRATION_RESEARCH_V1.md
2cf0d02ee9147a04  docs/design/EVIDENCE_FAMILY_INDEPENDENCE_RESEARCH_V1.md
5212f817652dd406  docs/design/FAILURE_ATTRIBUTION_RESEARCH_V1.md
a084ea158c2415e7  docs/design/FMITS_INFORMATION_EDGE_RESEARCH.md
250795339058653f  docs/design/IMPLEMENTATION_ROADMAP_V1.md
9296099caff441a0  docs/design/SWING_TRADING_MVP_BLUEPRINT_V1.md
539262c057a0f488  docs/design/SWING_TRADING_READINESS_AUDIT_V1.md
285a4fe31739d1f9  docs/design/TRADER_WORKSPACE_PRODUCT_ARCHITECTURE_V1.md
fb9f672e4373bfb2  docs/design/TRADING_DOMAIN_DATA_MODEL_V1.md
aa4012d8f6a5f6bf  docs/reviews/AP_D1_D2_INVESTIGATION_REVIEW.md
```

**Safety review performed before committing.** All sixteen were scanned for API keys, tokens, PEM
and private-key blocks, seed phrases and mnemonics, crypto addresses, email addresses, absolute home
paths, currency amounts, account balances, `.env` references, base64 blobs and control characters.
**Zero hits in every category.** The only credential-adjacent text is a handful of design rules
*forbidding* secrets — for example `TRADING_DOMAIN_DATA_MODEL_V1.md` §815: *"no private key, seed
phrase, address-with-balance or API secret is ever a field on any entity in this model"*. No
generated, runtime or cache data is present; all sixteen are hand-written prose.

---

## What this index is not

It does not summarise the documents' conclusions, reconcile their disagreements, mark any of them
superseded, or promote any proposal in them. **Doing any of that would be the drift this file exists
to prevent** — an index that interprets becomes a document that decides. It lists what exists, says
plainly that none of it is approved, and stops.
