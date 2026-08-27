"""Rendering Milestone CA. **Presentation only — it computes nothing.**

The renderer holds no threshold, no sample floor and no `Decimal`. Everything it
prints was decided by `fmis.swing_lab.admission_study`, and a test asserts the
absence rather than trusting it: presentation must stay replaceable, so it may
own no rule. Milestone BZ's renderer states the same constraint for the same
reason and this one inherits it.

The order is deliberate and is the order a sceptical reader needs:

    1. the verdict, first, before anything that could soften it
    2. the seal, the capture it was measured over, and whether both verify
    3. what a positive number here does NOT mean
    4. the sealed families, with the primary effect and its uncertainty
    5. the horizon profile, so a primary result can be read against its own shape
    6. the gate ladder, with its refusals stated rather than blank
    7. the limitations, in full
"""

from __future__ import annotations

from collections.abc import Sequence

from fmis.swing_lab.admission_preregistration import (
    CA_NULL_FAMILIES,
    CA_PREREGISTRATION_DIGEST,
    CA_PREREGISTRATION_ID,
    MIN_ADMISSION_EDGE_ATR,
    PRIMARY_HORIZON,
    CaVerdict,
)

__all__ = ["render_admission_study"]

_HEADLINES = {
    CaVerdict.NO_EDGE: (
        "NO EDGE — no sealed null family showed the admission engine selecting "
        "better than its matched control by the pre-declared threshold."
    ),
    CaVerdict.INCONCLUSIVE: (
        "INCONCLUSIVE — at least one sealed criterion could not be evaluated. "
        "This is NOT a refutation: an unrun test is not evidence against a "
        "hypothesis."
    ),
    CaVerdict.MECHANISM_EVIDENCE: (
        "MECHANISM EVIDENCE — a real, meaningful effect exists where the engine "
        "was developed and did not survive both unseen samples. A finding about "
        "information. It changes no rule and earns no test."
    ),
    CaVerdict.ADMISSION_EDGE_CANDIDATE: (
        "ADMISSION EDGE CANDIDATE — every sealed criterion was met. This means "
        "the admission engine is worth PRESERVING AND DECOMPOSING in a later "
        "milestone. It does NOT approve live, shadow, paper or forward trading, "
        "and no verdict in this milestone can."
    ),
}

_WHAT_IT_IS_NOT = (
    "WHAT A POSITIVE EFFECT HERE DOES NOT MEAN.",
    "  CA measures admission with NO stop, NO target, NO exit and NO cost. A",
    "  positive effect says the engine selects better-than-matched moments; it",
    "  does not say a strategy built on them is profitable. Milestones BW, BX,",
    "  BY and BZ have already shown that the geometry applied to these moments",
    "  loses. Both findings can be true at once, and separating them is the",
    "  entire reason this milestone exists.",
)


def _fmt(value, digits: int = 4) -> str:
    if value is None:
        return "   n/a"
    return f"{value:+.{digits}f}"


def _line(width: int = 78) -> str:
    return "-" * width


def render_admission_study(study) -> str:
    """One deterministic report. **No clock, no randomness, no computation.**"""
    manifest = study.manifest
    out: list[str] = []
    add = out.append

    add("=" * 78)
    add("MILESTONE CA — SWING ADMISSION EDGE VS RANDOM-ENTRY NULL")
    add("=" * 78)
    add("")
    add(_HEADLINES[study.headline])
    add("")
    candidates = study.candidates
    add(
        f"families reaching ADMISSION_EDGE_CANDIDATE: "
        f"{len(candidates)}{' — ' + ', '.join(candidates) if candidates else ''}"
    )
    add("")
    add(_line())
    add("SEAL AND PROVENANCE")
    add(_line())
    add(f"  pre-registration      {CA_PREREGISTRATION_ID}")
    add(f"  sealed digest         {CA_PREREGISTRATION_DIGEST}")
    add(f"  study manifest digest {manifest.get('preregistration_digest')}")
    matches = manifest.get("preregistration_digest") == CA_PREREGISTRATION_DIGEST
    add(f"  seal verifies         {matches}")
    add(f"  BZ capture digest     {manifest.get('capture_content_digest')}")
    add(f"  capture taken at      {manifest.get('capture_captured_at')}")
    add(f"  primary horizon       {manifest.get('primary_horizon')} execution bars")
    add(f"  causality proven      {manifest.get('causal_proven')}")
    add(f"  run at                {manifest.get('run_at')}")
    add("")
    for line in _WHAT_IT_IS_NOT:
        add(line)
    add("")

    add(_line())
    add(f"SEALED NULL FAMILIES — effect in ATR at horizon {PRIMARY_HORIZON}")
    add(_line())
    add(
        f"  {'family':40s} {'sample':12s} {'n':>4s} {'un':>3s} "
        f"{'effect':>8s} {'boot lo':>8s} {'boot hi':>8s} {'null %':>7s}"
    )
    for family in CA_NULL_FAMILIES:
        for sample in ("development", "validation", "holdout"):
            result = study.results.get((family.family_id, sample))
            if result is None:
                continue
            add(
                f"  {family.family_id:40s} {sample:12s} {result.matched:4d} "
                f"{result.unmatched:3d} {_fmt(result.effect)} "
                f"{_fmt(result.bootstrap_low)} {_fmt(result.bootstrap_high)} "
                f"{'  n/a' if result.null_percentile is None else f'{result.null_percentile:6.1f}'}"
            )
        add("")
    add(f"  the bar for a meaningful effect is {MIN_ADMISSION_EDGE_ATR:+.2f} ATR on every sample")
    add("")

    degenerate = [item for item in CA_NULL_FAMILIES if item.is_degenerate_at_primary]
    if degenerate:
        add(_line())
        add("DECLARED DEGENERACY — sealed in advance, not discovered afterwards")
        add(_line())
        for family in degenerate:
            add(f"  {family.family_id}")
            for chunk in _wrap(family.degeneracy or ""):
                add(f"    {chunk}")
        add("")

    add(_line())
    add("HORIZON PROFILE — development, effect in ATR")
    add(_line())
    horizons = manifest.get("horizons", [])
    add("  " + f"{'family':40s}" + "".join(f"{h:>9d}" for h in horizons))
    for family in CA_NULL_FAMILIES:
        result = study.results.get((family.family_id, "development"))
        if result is None:
            continue
        add(
            f"  {family.family_id:40s}"
            + "".join(_fmt(result.effect_by_horizon.get(h)).rjust(9) for h in horizons)
        )
    add("")

    add(_line())
    add("VERDICTS AND THE CRITERIA THAT PRODUCED THEM")
    add(_line())
    for family in CA_NULL_FAMILIES:
        assessment = study.assessments.get(family.family_id)
        if assessment is None:
            continue
        add(f"  {family.family_id}  ->  {assessment.verdict.value.upper()}")
        add(f"    question: {family.question.value}")
        for criterion in assessment.criteria:
            mark = {True: "PASS", False: "FAIL", None: "UNMEASURABLE"}[criterion.passed]
            add(f"    [{mark:>12s}] {criterion.name}")
            for chunk in _wrap(criterion.detail, width=64):
                add(f"                   {chunk}")
        add("")

    add(_line())
    add("GATE LADDER — where instants stopped, per sample")
    add(_line())
    census = manifest.get("stage_census", {})
    for sample, counts in sorted(census.items()):
        add(f"  {sample}")
        for stage, count in counts.items():
            add(f"    {stage:24s} {count:8d}")
    add("")
    add("  Forward outcomes by rung are reported per symbol in the artifact. The")
    add("  three rungs below the family tally carry NO production direction, so a")
    add("  direction-normalised return is undefined for them and is REFUSED")
    add("  rather than computed as a long's.")
    add("")

    add(_line())
    add("LIMITATIONS")
    add(_line())
    for limitation in study.limitations:
        for index, chunk in enumerate(_wrap(limitation, width=74)):
            add(("  " if index == 0 else "     ") + chunk)
        add("")
    add("=" * 78)
    add("NOTHING IN THIS MILESTONE APPROVES LIVE, SHADOW, PAPER OR FORWARD")
    add("TRADING. NO VERDICT IT DEFINES IS ABLE TO.")
    add("=" * 78)
    return "\n".join(out)


def _wrap(text: str, width: int = 72) -> Sequence[str]:
    """Wrap without importing `textwrap`'s policy into a report's layout."""
    lines: list[str] = []
    current: list[str] = []
    length = 0
    for word in text.split():
        # A running length rather than a sum over the buffer, so this module
        # performs NO aggregation of any kind and the guard asserting that can
        # stay strict instead of carving out an exception for a text utility.
        if current and length + len(word) > width:
            lines.append(" ".join(current))
            current = [word]
            length = len(word) + 1
        else:
            current.append(word)
            length += len(word) + 1
    if current:
        lines.append(" ".join(current))
    return lines or [""]
