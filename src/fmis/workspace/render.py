"""Rendering a `Workspace` as a plain-text terminal page.

**This module only renders.** It contains no business logic, performs no
arithmetic on a market value, reads no engine, and makes no decision about what
belongs on the page — the `Workspace` decided all of that. A test asserts the
module calls no builder and no engine.

The contract every renderer shares, and which makes a future Telegram or JSON
renderer safe: a renderer may **drop** sections and **shorten** values. It may
never **add** a claim, **reorder** sections, or **change a value's tier**. A
Telegram message can therefore never assert something the terminal did not.

Dispatch on block type goes through an explicit mapping rather than a chain of
`isinstance` branches, so a fourth block shape fails at the mapping instead of
rendering as nothing.
"""

from __future__ import annotations

import textwrap
from collections.abc import Callable, Mapping

from fmis.workspace.models import (
    Block,
    NoteBlock,
    RowBlock,
    SectionStatus,
    TableBlock,
    Unavailable,
    Workspace,
    WorkspaceSection,
)

__all__ = ["render_workspace", "STATUS_GLYPH"]

#: Page width. Wider than the 66 columns AF and AG use, because the workspace
#: carries tables of three views; still narrow enough to paste into a message or
#: an issue without wrapping, which is the constraint that decides it.
_WIDTH = 78

#: Where a row's value ends and its note begins.
_VALUE_COLUMN = 46

#: Status glyphs. Every status carries a **glyph and a word**, never colour
#: alone: this page is read through pipes, in logs, and by readers who cannot
#: distinguish the colours a terminal would use.
STATUS_GLYPH: Mapping[SectionStatus, str] = {
    SectionStatus.AVAILABLE: "✓",
    SectionStatus.PARTIAL: "◐",
    SectionStatus.UNAVAILABLE: "⧗",
    SectionStatus.FAILED: "✗",
}


def _rule(char: str = "─") -> str:
    return char * _WIDTH


def _section_rule(title: str, status: SectionStatus) -> str:
    """A section heading with its status glyph pinned to the right margin."""
    glyph = STATUS_GLYPH[status]
    head = f"── {title} "
    tail = f" {glyph} ──"
    filler = max(0, _WIDTH - len(head) - len(tail))
    return f"{head}{'─' * filler}{tail}"


def _row(label: str, value: str, note: str = "") -> str:
    """One label/value/note line, aligned so values compare vertically."""
    left = f" {label}"
    pad = max(1, _VALUE_COLUMN - len(left) - len(value))
    line = f"{left}{' ' * pad}{value}"
    if note:
        line = f"{line}   {note}"
    return line


def _render_row_block(block: RowBlock) -> list[str]:
    """Aligned rows, wrapping any that will not fit the page.

    A row whose value is a sentence — a limitation, a conflict statement — does
    not fit beside its label. It is rendered as label then wrapped value rather
    than allowed to overflow, because a terminal wrapping a line mid-number
    produces something a reader parses as a different value.
    """
    lines: list[str] = []
    if block.heading:
        lines.append(f" {block.heading}")
    for row in block.rows:
        line = _row(row.label, row.value, row.note)
        if len(line) <= _WIDTH:
            lines.append(line)
            continue
        lines.append(f" {row.label}")
        text = row.value if not row.note else f"{row.value}  ({row.note})"
        lines.extend(
            textwrap.wrap(
                text, width=_WIDTH, initial_indent="     ", subsequent_indent="     "
            )
        )
    return lines


def _render_table_block(block: TableBlock) -> list[str]:
    """A column-aligned table, sized from its own content.

    Widths come from the data rather than from constants, so a long symbol or a
    long statement is never truncated into something that reads as a different
    value.
    """
    columns = block.columns
    widths = [len(column) for column in columns]
    for record in block.records:
        for index, cell in enumerate(record):
            widths[index] = max(widths[index], len(cell))

    # The rendered width exactly: one leading space, the cells, and a two-space
    # separator between each adjacent pair.
    rendered_width = 1 + sum(widths) + 2 * (len(widths) - 1)
    if rendered_width > _WIDTH:
        raise ValueError(
            f"table is {rendered_width} columns wide but the page is {_WIDTH}; a "
            "provider must choose narrower columns rather than let a row wrap "
            "into something that reads as a different value"
        )

    lines: list[str] = []
    if block.heading:
        lines.append(f" {block.heading}")
    header = " " + "  ".join(
        column.upper().ljust(widths[index]) for index, column in enumerate(columns)
    )
    lines.append(header.rstrip())
    for record in block.records:
        line = " " + "  ".join(
            cell.ljust(widths[index]) for index, cell in enumerate(record)
        )
        lines.append(line.rstrip())
    return lines


def _render_note_block(block: NoteBlock) -> list[str]:
    lines: list[str] = []
    for note in block.notes:
        lines.extend(
            textwrap.wrap(
                note, width=_WIDTH, initial_indent=" · ", subsequent_indent="   "
            )
        )
    return lines


#: Explicit dispatch. A new block type that is not registered here raises rather
#: than rendering as silence, which is the failure a chain of `isinstance` checks
#: with a fall-through `else` would produce.
_BLOCK_RENDERERS: Mapping[type, Callable[[Block], list[str]]] = {
    RowBlock: _render_row_block,
    TableBlock: _render_table_block,
    NoteBlock: _render_note_block,
}


def _render_block(block: Block) -> list[str]:
    renderer = _BLOCK_RENDERERS.get(type(block))
    if renderer is None:
        raise TypeError(
            f"no renderer registered for block type {type(block).__name__}"
        )
    return renderer(block)


def _render_section(section: WorkspaceSection) -> list[str]:
    lines = [_section_rule(section.title, section.status)]

    for line in section.summary:
        lines.extend(
            textwrap.wrap(
                line, width=_WIDTH, initial_indent=" ", subsequent_indent="   "
            )
        )

    if isinstance(section, Unavailable):
        lines.append("")
        lines.append(f" NOT AVAILABLE — owned by {section.owner}")
        return lines

    if section.status is SectionStatus.FAILED and section.reason:
        lines.append(f" reason: {section.reason}")

    for block in section.body:
        lines.append("")
        lines.extend(_render_block(block))

    if section.caveats:
        lines.append("")
        for caveat in section.caveats:
            lines.extend(
                textwrap.wrap(
                    caveat, width=_WIDTH, initial_indent=" ⚠ ", subsequent_indent="   "
                )
            )

    if section.provenance is not None:
        provenance = section.provenance
        parts = [provenance.engine]
        if provenance.policy_id:
            parts.append(f"policy {provenance.policy_id}")
        if provenance.as_of is not None:
            parts.append(provenance.as_of.isoformat())
        lines.append("")
        lines.extend(
            textwrap.wrap(
                f"via {' · '.join(parts)}",
                width=_WIDTH,
                initial_indent=" ",
                subsequent_indent="     ",
            )
        )

    return lines


def render_workspace(workspace: Workspace) -> str:
    """Render a workspace as one plain-text page.

    Every section is rendered, including the unavailable ones. A renderer that
    skipped them would make the page look finished, which is the presentation
    failure `SPEC` §7 names as excessive confidence from incomplete data.

    Raises:
        TypeError: ``workspace`` is not a `Workspace`.
    """
    if not isinstance(workspace, Workspace):
        raise TypeError(
            f"workspace must be a Workspace, got {type(workspace).__name__}"
        )

    lines: list[str] = [_rule("═")]
    lines.append(" FMITS SWING WORKSPACE — deterministic facts · interpretation marked")
    lines.append(_row(workspace.symbol, workspace.objective))
    lines.extend(
        textwrap.wrap(
            f"{workspace.source} · schema v{workspace.schema_version}",
            width=_WIDTH,
            initial_indent=" ",
            subsequent_indent="   ",
        )
    )
    lines.append(_rule("═"))

    for section in workspace.sections:
        lines.append("")
        lines.extend(_render_section(section))

    lines.append("")
    lines.append(_rule("═"))
    lines.append(" These are measurements, not conclusions. No direction, ranking or")
    lines.append(" recommendation is expressed or implied.")
    lines.append(_rule("═"))
    return "\n".join(lines)
