"""Application layer — workflows that wire the deterministic engines together.

This is the **top** of the dependency graph and the only layer allowed to know
about more than one engine at once. Everything below it stays independent:
`fmis.features` and `fmis.relative_value` know nothing about networking, and
`fmis.providers` knows nothing about indicators.

    fmis.providers -> fmis.ingest -> fmis.data
                                       ^     ^
                        fmis.features -+     +- fmis.alignment, fmis.relative_value
                                       |
                                  fmis.pipeline   (this package — imports all of them)

Implemented, two composition roots:
  * `market_analysis` — one symbol, optionally compared with one benchmark,
    returning a structured `AnalysisSnapshot`.
  * `structural_facts` — one symbol through **every** deterministic engine,
    measurement *and* structure, returning a `StructuralFactSheet`. Milestone AF.

`cli` and `render` sit above both: a command-line surface and a plain-text
renderer. They are presentation, hold no logic, and are the only place a wall
clock is read.

Rules for anything added here:
  * **Orchestration only.** No formula, no indicator, no metric may be defined in
    this package. It calls the engines and arranges their results. A test asserts
    the module contains no arithmetic of its own.
  * **No interpretation.** No LONG/SHORT/BUY/SELL, score, ranking, confidence,
    label, or recommendation — the fact-only rule of the engines applies here too,
    and a snapshot that merely restates facts must not acquire an opinion.
  * **Nothing partial on failure.** If a requested computation cannot be
    performed, the error surfaces. A caller never receives a snapshot that
    quietly omits what it asked for.
  * **Injectable I/O.** Transport and clock are passed through to the provider, so
    a workflow is testable without the network.
  * **No framework.** These are concrete functions for concrete questions, not a
    pluggable pipeline engine. Add another function, not another abstraction.
"""

from __future__ import annotations

from fmis.pipeline.market_analysis import (
    AnalysisSnapshot,
    DataWindow,
    InsufficientDataError,
    PipelineError,
    RelativeValueSection,
    analyze_symbol,
    default_features,
)
from fmis.pipeline.render import render_fact_sheet
from fmis.pipeline.structural_facts import (
    LIMITATIONS,
    DetectionSettings,
    Limitation,
    NearestLevels,
    StructuralFactSheet,
    StructureFacts,
    build_structural_facts,
    structural_facts_for_symbol,
)

__all__ = [
    "analyze_symbol",
    "default_features",
    "AnalysisSnapshot",
    "DataWindow",
    "RelativeValueSection",
    "PipelineError",
    "InsufficientDataError",
    "build_structural_facts",
    "structural_facts_for_symbol",
    "render_fact_sheet",
    "StructuralFactSheet",
    "StructureFacts",
    "NearestLevels",
    "DetectionSettings",
    "Limitation",
    "LIMITATIONS",
]
