# Architecture Decision Records

An **ADR** records one architectural decision: the context that forced it, the decision itself, the
alternatives that were rejected, and the consequences that follow. Its purpose is to preserve **why**,
because *what* is already visible in the code and *why* is not.

## Relationship to the architecture document

[../ARCHITECTURE_AND_ROADMAP_V1.md](../ARCHITECTURE_AND_ROADMAP_V1.md) §12 holds the decision table
**D1–D11**. That table remains authoritative for those eleven decisions. This directory is the
[docs/README.md](../README.md) "dedicated per-decision ADR directory" moving from *Planned* to *exists*,
and it is used for decisions that need more than a table row — typically because the reasoning is subtle,
the alternatives are individually defensible, or the decision constrains code that has already been
written.

Both forms coexist. Nothing in §12 is migrated retroactively; new significant decisions are written here.

## Conventions

- One decision per file: `ADR-<4-digit>-<kebab-case-title>.md`, numbered in creation order.
- Numbers are never reused, and a superseded ADR is never deleted — it is marked `Superseded by ADR-NNNN`
  and left in place, because historical outputs were produced under it.
- Status is one of: `Proposed` · `Accepted` · `Superseded` · `Rejected`.
- Every ADR states the decision, the **alternatives considered and why each was rejected**, the
  consequences (including the ones the project must live with), and how the decision is enforced.

## Index

| ADR | Title | Status | Decides |
|---|---|---|---|
| [ADR-0001](ADR-0001-canonical-utc-timestamps.md) | Canonical UTC timestamps | Accepted | Which timezones a canonical model may store, and that timestamps are validated but never converted |
| [ADR-0002](ADR-0002-alignment-as-temporal-comparison-policy-layer.md) | Alignment is a temporal-comparison policy layer | Accepted | Alignment moves from `fmis.data` to a dedicated `fmis.alignment` package (review finding R2); code move planned as Milestone I-E |
| [ADR-0003](ADR-0003-availability-time-boundary.md) | Availability-time boundary | Accepted | No macro/released/revised/vintage data until an explicit availability-time model is designed and accepted (review finding R3); corrects the "look-ahead structurally prevented" phrasing |
