"""Swing Trading Workspace — one instrument, one page, every section.

    workspace_for_symbol(symbol)  ──►  (MultiTimeframeFactSheet, Workspace)
                                              │
                       render_workspace(workspace)  ──►  terminal page

The `Workspace` is a **first-class object**, not the output of a command. The
CLI renders one; a future Telegram renderer, dashboard or JSON serializer will
render the same object. Renderers may drop sections and shorten values; they may
never add a claim, reorder sections, or change a value's tier.

**What this layer adds.** No engine. It composes what AF, AG, AH and AI already
produce, joins them to the evidence taxonomy, reports the disagreements between
them, and lays the result out in a fixed order.

**What it is the first consumer of.** `fmis.decision_support` and
`fmis.evidence` shipped with full test suites, accepted ADRs, and **no
production importer**. This package is the surface they were designed for.

**Sections that no milestone has built are rendered, not hidden.** Risk,
portfolio, trade plan and interpretation appear on every page as `Unavailable`,
each naming the milestone that owns it and the inference its absence forbids. An
omitted section is invisible, and an invisible gap reads as a gap that does not
exist — which is how a reader comes to believe risk was considered when it was
not.

**Where it sits.** Above `fmis.pipeline` and `fmis.decision_support`, at the top
of the graph. Nothing below imports it, which a test asserts.
"""

from __future__ import annotations

from fmis.workspace.builder import (
    PRIMARY_ROLE,
    WORKSPACE_LIMITATIONS,
    build_workspace,
    snapshot_from_sheet,
    workspace_for_symbol,
)
from fmis.workspace.conflicts import Conflict, ConflictKind, detect_conflicts
from fmis.workspace.models import (
    SECTION_ORDER,
    WORKSPACE_SCHEMA_VERSION,
    Block,
    NoteBlock,
    Provenance,
    Row,
    RowBlock,
    Section,
    SectionId,
    SectionStatus,
    TableBlock,
    Tier,
    Unavailable,
    Workspace,
    WorkspaceError,
    WorkspaceSection,
)
from fmis.workspace.render import render_workspace
from fmis.workspace.sections import (
    SECTION_PROVIDERS,
    SectionProvider,
    WorkspaceInputs,
    build_sections,
)

__all__ = [
    # entry points
    "workspace_for_symbol",
    "build_workspace",
    "render_workspace",
    # the artifact
    "Workspace",
    "Section",
    "Unavailable",
    "WorkspaceSection",
    "SectionId",
    "SectionStatus",
    "Tier",
    "Provenance",
    # body blocks
    "Block",
    "Row",
    "RowBlock",
    "TableBlock",
    "NoteBlock",
    # conflicts
    "Conflict",
    "ConflictKind",
    "detect_conflicts",
    # extension surface
    "SECTION_PROVIDERS",
    "SectionProvider",
    "WorkspaceInputs",
    "build_sections",
    "SECTION_ORDER",
    # adapters and constants
    "snapshot_from_sheet",
    "PRIMARY_ROLE",
    "WORKSPACE_LIMITATIONS",
    "WORKSPACE_SCHEMA_VERSION",
    # errors
    "WorkspaceError",
]
