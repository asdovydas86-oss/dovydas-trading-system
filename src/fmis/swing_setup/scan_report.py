"""Market Scanner Intelligence Report v1 — a readable market report, not a table.

    render_scan_report(results)  ──►  plain-text report a trader can read in
                                       one sitting, over the same
                                       `tuple[SetupRunResult, ...]`
                                       `fmis.swing_setup.scan.render_scan`
                                       already renders as a table.

**This module adds no engine, no policy, no ranking and no score.** Every
fact printed here already exists on a `SetupAssessment` or a
`SetupRunResult.failure` — this module only selects, groups and formats what
`fmis.swing_setup.compose`/`fmis.swing_setup.policy` already computed. It
imports no engine module and calls no engine function.

**Four sections, each reading a different already-computed fact:**

* `SCAN SUMMARY` — the same per-status counts `render_scan`'s own summary
  line prints, produced by the same `scan.result_status` classifier so the
  two can never disagree.
* `MARKET OVERVIEW` — every scanned symbol bucketed as `DIRECTIONAL`,
  `CONFLICTED`, `NO DATA` or `NOT SCANNED` (see `_overview_lean`). A
  `CANDIDATE`/`CONFIRMED` result is bucketed from its own
  `SetupAssessment.direction` — the policy's already-final directional
  verdict, reached from all three families plus execution confirmation, never
  from one family's read in isolation. Only a `WAIT` result (`direction is
  None`, no final verdict exists) falls back to the lean of its own
  `context_structural_trend` directional factor (`DirectionalFactor.lean`,
  `fmis.swing_setup.policy._directional_factors`'s first entry) — the same
  factor `ACTIONABLE SETUPS`' own reason lines already cite by name. An
  earlier draft bucketed every result from that one factor alone; an
  adversarial review found two real defects that followed from it — a
  `CONFIRMED` trade whose winning families were the *other* two could land in
  `NO DATA`/`CONFLICTED`, and the label `TRENDING` could sit beside a `WAIT`
  reason literally stating "not trending" for the same symbol, since
  `context_regime_structure` (which gates that WAIT branch) and
  `context_structural_trend` (which feeds this factor) are two independently
  computed facts that can disagree. Reading `direction` first when one exists
  removes the first defect outright; the label `DIRECTIONAL` (never the word
  "trending") removes the second regardless of which fact produced it. This
  is deliberately *not* `fmis.market_regime`'s own `StructureState`
  (`TRENDING`/`RANGING`/`TRANSITIONING`/...) — that value is never stored on
  `SetupAssessment`, only folded into one formatted sentence in
  `regime_context`, and this module does not parse rendered prose to recover
  a fact it could otherwise fabricate the meaning of. A symbol whose analysis
  failed carries no assessment at all and is bucketed `NOT SCANNED`.
* `ACTIONABLE SETUPS` — every `CONFIRMED` result, then every `CANDIDATE`
  result, in scan order within each group (a filter, never a reorder — the
  same discipline `render_scan`'s own `TOP OPPORTUNITIES` section applies).
  Both states share one header builder, `_setup_header`: RR/stop/target are
  `SetupAssessment.risk_reward`/`.stop`/`.targets` read directly and printed
  identically regardless of state — `policy.py` computes `risk_reward`
  whenever a stop and a target both exist, never conditioned on `state`, so a
  `CANDIDATE` with a known level on each side already carries a real RR
  exactly as a `CONFIRMED` result does (an earlier draft printed RR/target
  for `CONFIRMED` only, silently dropping an already-computed number for
  `CANDIDATE` — also an adversarial-review finding). The "reason"/"needs"/
  "invalidation" lines are `SetupAssessment.thesis`/`.confirmation`/
  `.invalidation`, printed verbatim. Nothing here is composed, paraphrased or
  summarised into new wording — every printed sentence already exists,
  character-for-character, on the assessment.
* `WAIT REASONS` — every `WAIT` result grouped by its own `thesis[0]` string,
  compared for exact equality. Two symbols reaching `WAIT` by the same policy
  branch produce byte-identical thesis text (see `policy.py`'s `_wait`
  call sites, each templated from `SetupInputs` with no symbol name in the
  sentence), so exact-string grouping is a real category, not a coincidence.
  Counted and sorted by descending count — a distribution over already-stated
  reasons, not a ranking of trade opportunities; ties keep scan order.
  **Known, accepted limitation:** the "factors do not agree" branch's thesis
  is templated only from vote *counts* (`N long, N short, ...`), not from
  *which* families voted which way — two symbols reaching that branch through
  different families can render byte-identical text and group together. Fixing
  this would mean this module re-deriving which-family-voted from
  `directional_factors` — exactly the kind of duplicated policy logic this
  module exists to avoid. Grouping by the engine's own exact wording, warts
  included, is judged the lesser fabrication.

**This module's own structural text is ASCII-only, on purpose.** Every rule,
section title, dot-leader and label this module writes itself uses `-` and
`=`, never a box-drawing character or an em dash — meant to be read
identically in a terminal, a log file and Telegram, without depending on a
font that renders `—` or `─`. The one exception is content this module does
not write: a `thesis`/`confirmation`/`invalidation` sentence is printed
exactly as `fmis.swing_setup.policy` composed it, including whichever
punctuation that sentence already uses (a small number do use "—") — because
printing it *unmodified* is what makes the "reason" lines trustworthy in the
first place. Editing an inherited sentence to enforce this module's own
character set would be exactly the kind of invention the module docstring
above rules out.
"""

from __future__ import annotations

import textwrap
from collections.abc import Sequence

from fmis.swing_setup.compose import SetupRunResult
from fmis.swing_setup.models import (
    Direction,
    DirectionalFactor,
    Lean,
    SetupState,
    SwingSetupError,
)
from fmis.swing_setup.scan import result_status

__all__ = ["render_scan_report"]

_WIDTH = 78
_ABSENT = "-"
_STATUS_ORDER = ("WAIT", "CANDIDATE", "CONFIRMED", "ERROR")
_OVERVIEW_ORDER = ("DIRECTIONAL", "CONFLICTED", "NO DATA", "NOT SCANNED")

#: Which family backs the `MARKET OVERVIEW` fallback read for a `WAIT` result
#: (one with no `direction` of its own) — see the module docstring and
#: `_overview_label`/`_overview_lean` for the full rule, including why a
#: `CANDIDATE`/`CONFIRMED` result never reaches this factor at all.
_TREND_FAMILY = "context_structural_trend"


def _rule(char: str = "=") -> str:
    return char * _WIDTH


def _price(value: float) -> str:
    """Format a price exactly as `scan._price`/`render._number` do."""
    return f"{value:,.6g}"


def _wrap(text: str, *, indent: str = "     ") -> list[str]:
    return textwrap.wrap(
        text, width=_WIDTH, initial_indent=indent, subsequent_indent=indent + "  "
    )


def _section(title: str) -> list[str]:
    return ["", f" {title}", _rule("-")]


def _count_line(label: str, count: int) -> str:
    dots = "." * max(20 - len(label), 3)
    return f"   {label} {dots} {count}"


def _context_trend_factor(
    factors: tuple[DirectionalFactor, ...],
) -> DirectionalFactor | None:
    for factor in factors:
        if factor.family == _TREND_FAMILY:
            return factor
    return None


def _overview_lean(result: SetupRunResult) -> Lean | None:
    """The directional read `MARKET OVERVIEW` bases its bucket on, or `None`.

    `assessment.direction` — set exactly when `state` is `CANDIDATE`/
    `CONFIRMED` — is read first, because it is the policy's own, already-final
    directional verdict across *all three* families plus execution
    confirmation (`policy.py`'s `_tally` and the confirmation branch below
    it); reading only the `context_structural_trend` factor here, as an
    earlier draft did, could bucket a live `CONFIRMED` trade under `NO DATA`
    or `CONFLICTED` whenever that one family happened not to be the one that
    won the tally — a real, reachable defect an adversarial review caught.

    Only a `WAIT` result (`direction is None`) falls back to the
    `context_structural_trend` factor's own `lean` — the best already-computed
    directional read available for a symbol the policy did not turn into a
    thesis, and the same factor `ACTIONABLE SETUPS`' own reason lines already
    cite by name for `CONFIRMED`/`CANDIDATE` rows.
    """
    if result.assessment is None:
        return None
    if result.assessment.direction is not None:
        return Lean.LONG if result.assessment.direction is Direction.LONG else Lean.SHORT
    factor = _context_trend_factor(result.assessment.directional_factors)
    return None if factor is None else factor.lean


def _overview_label(result: SetupRunResult) -> str:
    if result.assessment is None:
        return "NOT SCANNED"
    lean = _overview_lean(result)
    if lean in (Lean.LONG, Lean.SHORT):
        return "DIRECTIONAL"
    if lean is Lean.CONFLICTING:
        return "CONFLICTED"
    return "NO DATA"


def _overview_detail(result: SetupRunResult) -> str:
    """The symbol, plus its own lean when `_overview_label` named one."""
    lean = _overview_lean(result)
    if lean in (Lean.LONG, Lean.SHORT):
        return f"{result.requested_symbol} ({lean.value})"
    return result.requested_symbol


def _market_overview(results: Sequence[SetupRunResult]) -> list[str]:
    buckets: dict[str, list[SetupRunResult]] = {label: [] for label in _OVERVIEW_ORDER}
    for result in results:
        buckets[_overview_label(result)].append(result)

    lines = _section(f"MARKET OVERVIEW  (direction when set, else {_TREND_FAMILY} lean)")
    any_bucket = False
    for label in _OVERVIEW_ORDER:
        members = buckets[label]
        if not members:
            continue
        any_bucket = True
        lines.append(f"   {label} ({len(members)})")
        for result in members:
            lines.append(f"     {_overview_detail(result)}")
    if not any_bucket:
        lines.append("   (nothing to show)")
    return lines


def _reason_lines(label: str, texts: tuple[str, ...]) -> list[str]:
    if not texts:
        return []
    lines = [f"   {label}:"]
    for text in texts:
        lines.extend(_wrap(text))
    return lines


def _setup_header(state_label: str, result: SetupRunResult) -> list[str]:
    """The `STATE  SYMBOL  SIDE  RR x.xx` header, plus its `target`/`stop`
    line — shared by `CONFIRMED` and `CANDIDATE`, since both already carry a
    `direction`, and either may already carry a `risk_reward`/`stop`/
    `targets` (RR requires both a stop and a target, computed identically
    regardless of state — see `policy.py`'s `_risk_reward`/`risk_reward`
    assignment, which never branches on `state`)."""
    assessment = result.assessment
    assert assessment is not None
    direction = assessment.direction.value.upper() if assessment.direction else _ABSENT
    rr = assessment.risk_reward
    header = f" {state_label}  {result.requested_symbol}  {direction}"
    if rr is not None:
        header += f"   RR {rr.ratio:,.2f}"
    stop_text = _price(assessment.stop.price) if assessment.stop is not None else _ABSENT
    target_text = _price(assessment.targets[0].price) if assessment.targets else _ABSENT
    return [header, f"   target {target_text}   stop {stop_text}"]


def _confirmed_block(result: SetupRunResult) -> list[str]:
    assessment = result.assessment
    assert assessment is not None
    lines = _setup_header("CONFIRMED", result)
    lines.extend(_reason_lines("reason", assessment.thesis + assessment.confirmation))
    lines.extend(_reason_lines("invalidation", assessment.invalidation))
    return lines


def _candidate_block(result: SetupRunResult) -> list[str]:
    assessment = result.assessment
    assert assessment is not None
    lines = _setup_header("CANDIDATE", result)
    lines.extend(_reason_lines("reason", assessment.thesis))
    lines.extend(_reason_lines("needs", assessment.confirmation))
    return lines


def _actionable_setups(results: Sequence[SetupRunResult]) -> list[str]:
    confirmed = [
        r for r in results if r.assessment is not None and r.assessment.state is SetupState.CONFIRMED
    ]
    candidates = [
        r for r in results if r.assessment is not None and r.assessment.state is SetupState.CANDIDATE
    ]
    if not confirmed and not candidates:
        return []

    lines = _section("ACTIONABLE SETUPS")
    first = True
    for result in confirmed:
        if not first:
            lines.append("   " + "-" * (_WIDTH - 3))
        first = False
        lines.extend(_confirmed_block(result))
    for result in candidates:
        if not first:
            lines.append("   " + "-" * (_WIDTH - 3))
        first = False
        lines.extend(_candidate_block(result))
    return lines


def _wait_reason_groups(
    results: Sequence[SetupRunResult],
) -> list[tuple[str, list[str]]]:
    groups: dict[str, list[str]] = {}
    for result in results:
        assessment = result.assessment
        if assessment is None or assessment.state is not SetupState.WAIT:
            continue
        reason = assessment.thesis[0] if assessment.thesis else "no reason stated"
        groups.setdefault(reason, []).append(result.requested_symbol)
    # sorted() is stable, so ties keep dict-insertion order — the order each
    # reason was first seen in `results` (scan order), never an invented
    # tie-break.
    return sorted(groups.items(), key=lambda item: len(item[1]), reverse=True)


def _wait_reasons(results: Sequence[SetupRunResult]) -> list[str]:
    groups = _wait_reason_groups(results)
    if not groups:
        return []

    lines = _section("WAIT REASONS")
    for reason, symbols in groups:
        noun = "symbol" if len(symbols) == 1 else "symbols"
        lines.append(f"   {len(symbols)} {noun}:")
        lines.extend(_wrap(", ".join(symbols)))
        lines.extend(_wrap(reason))
    return lines


def _scan_errors(results: Sequence[SetupRunResult]) -> list[str]:
    failed = [r for r in results if r.failure is not None]
    if not failed:
        return []

    lines = _section("SCAN ERRORS")
    for result in failed:
        lines.append(f"   {result.requested_symbol}")
        lines.extend(_wrap(result.failure or "", indent="     "))
    return lines


def render_scan_report(results: Sequence[SetupRunResult]) -> str:
    """Render a market scan as a readable market intelligence report.

    Same input `fmis.swing_setup.scan.render_scan` renders as a table: a
    `tuple[SetupRunResult, ...]`, one per requested symbol. Every fact printed
    here already exists on the assessment or the failure string that produced
    it — see the module docstring for exactly which field backs each section.

    Raises:
        TypeError: ``results`` is not a sequence of `SetupRunResult`.
        ValueError: ``results`` is empty.
        SwingSetupError: a rendered line exceeded the page width — a defect in
            this module, raised rather than silently truncated further.
    """
    if isinstance(results, (str, bytes)) or not isinstance(results, Sequence):
        raise TypeError(
            f"results must be a non-string sequence, got {type(results).__name__}"
        )
    for position, result in enumerate(results):
        if not isinstance(result, SetupRunResult):
            raise TypeError(
                f"results[{position}] must be a SetupRunResult, got "
                f"{type(result).__name__}"
            )
    if not results:
        raise ValueError("at least one result is required")

    counts: dict[str, int] = {label: 0 for label in _STATUS_ORDER}
    for result in results:
        counts[result_status(result)] += 1

    lines: list[str] = [_rule(), " FMITS MARKET SCANNER - MARKET INTELLIGENCE REPORT", _rule()]
    lines.append(f" {len(results)} symbols scanned")
    lines.extend(_section("SCAN SUMMARY"))
    for label in _STATUS_ORDER:
        lines.append(_count_line(label, counts[label]))

    lines.extend(_market_overview(results))
    lines.extend(_actionable_setups(results))
    lines.extend(_wait_reasons(results))
    lines.extend(_scan_errors(results))

    lines.append("")
    lines.append(" To read any symbol in full:")
    lines.append("     fmits setup SYMBOL")
    lines.append("")
    lines.append(_rule())
    lines.append(" This is the fixed watchlist scanned in list order, not a ranking. No")
    lines.append(" score, probability or recommendation is computed. WAIT is a")
    lines.append(" successful result, not a failure. Position sizing is not computed.")
    lines.append(_rule())

    for line in lines:
        if len(line) > _WIDTH:
            raise SwingSetupError(
                f"rendered line of {len(line)} exceeds the {_WIDTH}-column page: "
                f"{line!r}"
            )
    return "\n".join(lines)
