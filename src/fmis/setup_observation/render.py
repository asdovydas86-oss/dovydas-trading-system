"""Plain-text rendering of a setup's stable identity.

Presentation only. Every value printed here already exists on the observation;
this module computes nothing and reaches no engine.

**It lives here rather than beside `render_setup`** for the reason the package
docstring gives: the engine's own renderer is a market-half module and may not
import the trading domain, and an identity is a domain value. The two renderers
therefore sit either side of that line and are composed by the command surface,
which is allowed to see both.

The width, the em dash and the "absent values state their reason" rule are the
engine renderer's, matched exactly so the two blocks read as one page.

**What this block deliberately does not print.** `LevelOriginRef.swing_index` is
window-relative — it moves every bar as the analysis window slides — and printing
it beside an identity would invite a reader to treat it as one. It is real
provenance and it is kept on the observation; it is simply not identity, and this
block is about identity.
"""

from __future__ import annotations

from fmis.provenance import Absent
from fmis.setup_observation.observe import SetupIdentityRun
from fmis.snapshotting import Anchor

__all__ = ["IDENTITY_WIDTH", "render_setup_identity", "render_identity_run"]

IDENTITY_WIDTH = 70
_ABSENT = "—"

#: How much of the identity digest is shown. The full value is 71 characters and
#: would wrap the page; this prefix is what a reader compares between two runs.
#: Comparison is the whole use, and a prefix that differs proves the ideas differ.
_SHOWN = 24


def _rule(title: str) -> str:
    """One titled section rule, the engine renderer's shape and width.

    Titled only: this block has exactly one section, so the engine's untitled
    full-width variant would be a branch no caller reaches.
    """
    return f"── {title} " + "─" * max(IDENTITY_WIDTH - len(title) - 4, 0)


def _anchor_lines(anchor: Anchor) -> list[str]:
    """The `MEASURED` facts the identity is actually built from."""
    origin = anchor.invalidation_origin
    return [
        f"  anchor      {anchor.market.value} · {anchor.book.value} · "
        f"{anchor.direction.value}",
        f"  origin      {origin.origin_id} "
        f"(confirmed over {origin.confirmation_bars} bars)",
    ]


def render_setup_identity(run: SetupIdentityRun) -> str:
    """One identity block for the latest reading in ``run``.

    A single `fmits setup` invocation observes **one** bar, so this block reports
    what one reading can support: the stable identity, the `MEASURED` anchor it
    was built from, and the versions in force. It does **not** claim a repeat
    count — see `render_identity_run`, which does, when a caller holds a series.
    """
    if not isinstance(run, SetupIdentityRun):
        raise TypeError(f"run must be a SetupIdentityRun, got {type(run).__name__}")

    lines = [_rule("SETUP IDENTITY")]

    if not run.observations:
        lines.append(f"  {_ABSENT} no reading was observed")
        return "\n".join(lines)

    latest = run.observations[-1]
    identity = latest.identity

    if isinstance(identity, Absent):
        lines.append(f"  {_ABSENT} {identity.reason}")
    else:
        lines.append(f"  occurrence  {identity[:_SHOWN]}…")
        lines.extend(_anchor_lines(latest.anchor))
        lines.append("  continuity  the same idea keeps this line between runs.")
        lines.append("              A different line is a different setup.")

    lines.append(f"  policy      {latest.reading.policy_id}")
    lines.append(f"  measured    {latest.as_of.isoformat()}")
    return "\n".join(lines)


def render_identity_run(run: SetupIdentityRun) -> str:
    """The same block plus the counts a **series** supports.

    Separate from `render_setup_identity` rather than a flag on it, because
    *"this is the fourth bar of one idea"* is a claim only a caller holding
    several readings may make, and a renderer that produced it from one reading
    would be stating something it cannot know.
    """
    if not isinstance(run, SetupIdentityRun):
        raise TypeError(f"run must be a SetupIdentityRun, got {type(run).__name__}")

    lines = [render_setup_identity(run)]
    latest = run.latest_occurrence
    if isinstance(latest, Absent):
        lines.append(f"  observed    {_ABSENT} {latest.reason}")
        return "\n".join(lines)

    status = "new occurrence" if run.is_new_occurrence else "repeat of an open idea"
    lines.append(f"  observed    {run.repeated_observation_count}× · {status}")
    lines.append(f"  began       {latest.began_at.isoformat()}")
    first_confirmed = latest.first_confirmed_at
    if isinstance(first_confirmed, Absent):
        lines.append(f"  confirmed   {_ABSENT} {first_confirmed.reason}")
    else:
        lines.append(f"  confirmed   {first_confirmed.isoformat()}")
    return "\n".join(lines)
