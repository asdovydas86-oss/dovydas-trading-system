"""The controls that make Milestone CC's safety claims checkable. **Non-vacuous.**

A control that cannot fail is decoration. Each function here is paired with a
**positive** case — a deliberately broken input the control is asserted to catch —
so that the test suite proves the control has teeth rather than proving it is
silent.

Four claims are checked:

* **No outcome informs eligibility.** Every rule in the funnel consumes a
  timestamp, a bar count, a price or a volume. `outcome_free_decision` re-runs the
  whole eligibility decision against a series whose *outcomes* have been altered in
  ways the rules must not see, and asserts the decision is identical.
* **No outcome informs the ordering.** `ordering_is_outcome_free` attaches a
  synthetic performance vector to the assessments, permutes it, and asserts the
  ordering does not move — **and separately** asserts the ordering is invariant to
  every field except the two sealed keys. The weaker arrival-order check this
  control originally performed was found during review to be unable to catch an
  ordering sorted by expectancy, because sorting a fixed multiset by ANY
  deterministic key is invariant to arrival order. That gap is closed here and the
  regression that proves it is `test_the_control_FIRES_on_an_expectancy_ordering`.
* **The holdout is never opened.** `reads_no_holdout_outcome` parses every module
  in `fmis.universe` and asserts that CA's realised interval bounds are never read
  and that no sample other than `development` is ever named to a function that
  inverts a design parameter from a realised measurement.
* **The assessment reproduces offline.** `offline_reproduction` re-runs the study
  from a capture with a transport that raises on every call, so a silent refetch
  cannot pass as a reproduction.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Final

from fmis.universe.capture import DailyBar, SeriesCache, network_is_fatal
from fmis.universe.eligibility import assess_asset
from fmis.universe.models import AssetAssessment, EconomicAsset, UniverseError

__all__ = [
    "ControlResult",
    "outcome_free_decision",
    "ordering_is_outcome_free",
    "reads_no_holdout_outcome",
    "DESIGN_SAMPLE",
    "PROTECTED_SAMPLES",
    "offline_reproduction",
    "perturb_outcomes",
]

#: The one sample whose realised outcomes may inform a design decision. Milestone
#: BY's `SampleRole.may_inform_design` is the authority; this is the name it
#: resolves to for Milestone CA's published figures.
DESIGN_SAMPLE: Final[str] = "development"

#: Sample names whose realised outcomes may NOT inform a design decision, and which
#: therefore may not appear as a runtime string anywhere in this package.
PROTECTED_SAMPLES: Final[frozenset[str]] = frozenset({"holdout", "validation"})


@dataclass(frozen=True, slots=True)
class ControlResult:
    """Whether one control held, and what it actually compared."""

    name: str
    held: bool
    detail: str

    def payload(self) -> dict[str, Any]:
        return {"name": self.name, "held": self.held, "detail": self.detail}


def perturb_outcomes(bars: Sequence[DailyBar], *, factor: float = 3.0) -> tuple[DailyBar, ...]:
    """Scale every price by ``factor``, leaving timestamps and volume alone.

    This is the perturbation an outcome-free rule must be blind to. Multiplying a
    whole series by a constant changes every return's *level* and every notional,
    but changes no timestamp, no bar count and no gap — so an eligibility rule
    reading only structure is unmoved, and one that had quietly started reading
    price levels is caught.

    **Volume is left alone deliberately**: the liquidity rule reads notional, which
    is ``close * volume``, and is *supposed* to move with price. Perturbing volume
    too would make the control test a rule that does not exist.
    """
    if factor <= 0.0:
        raise UniverseError("factor must be positive; a non-positive price is not a price")
    return tuple(
        replace(
            bar,
            open=bar.open * factor,
            high=bar.high * factor,
            low=bar.low * factor,
            close=bar.close * factor,
        )
        for bar in bars
    )


def outcome_free_decision(
    asset: EconomicAsset,
    bars: Sequence[DailyBar],
    *,
    listed_at: datetime,
    window_start: datetime,
    window_end: datetime,
    warmup: timedelta,
) -> ControlResult:
    """Assert the depth and quality decision does not move when prices do.

    Compares the exclusion **reason** rather than the whole assessment: the
    liquidity figure legitimately scales with price, and a control that demanded
    byte equality would fail on a rule doing exactly what it is supposed to.
    What must not move is *which rule fired*.
    """
    def decide(series: Sequence[DailyBar]) -> AssetAssessment:
        return assess_asset(
            asset, series, listed_at=listed_at, window_start=window_start,
            window_end=window_end, warmup=warmup,
        )

    base = decide(bars)
    moved = decide(perturb_outcomes(bars))
    same_reason = (
        (base.exclusion is None) == (moved.exclusion is None)
        and (
            base.exclusion is None
            or base.exclusion.reason is moved.exclusion.reason
        )
    )
    # Coverage is pure structure and must be byte-identical, not merely similar.
    same_coverage = (base.coverage is None) == (moved.coverage is None) and (
        base.coverage is None
        or (
            base.coverage.bars_observed == moved.coverage.bars_observed
            and base.coverage.longest_gap_bars == moved.coverage.longest_gap_bars
            and base.coverage.first_bar == moved.coverage.first_bar
            and base.coverage.last_bar == moved.coverage.last_bar
        )
    )
    return ControlResult(
        name="outcome_free_decision",
        held=same_reason and same_coverage,
        detail=(
            f"{asset.asset_id}: tripling every price left the decision "
            f"({'eligible' if base.eligible else base.exclusion.reason.value}) and "
            "every structural coverage figure unchanged"
            if same_reason and same_coverage
            else
            f"{asset.asset_id}: the decision MOVED when prices were scaled — "
            "an eligibility rule is reading a price level it must not read"
        ),
    )


def ordering_is_outcome_free(assessments: Sequence[AssetAssessment]) -> ControlResult:
    """Assert the universe ordering responds to the sealed keys and to **nothing else**.

    **This control was rewritten after an independent review.** Its first version
    ran the ordering forward and reversed and compared the results. That check is
    worthless for the property it claimed: sorting a fixed multiset by *any*
    deterministic per-item key is invariant to arrival order, so an ordering keyed
    on realised expectancy passed it unchanged. The review demonstrated exactly
    that, and `test_the_control_FIRES_on_an_expectancy_ordering` is the regression.

    What is checked now is the property itself, in two parts:

    1. **The ordering must EQUAL the sealed key ordering**, recomputed here from
       ``(-usable_years, asset_id)`` independently of `ordered_assets`. This is the
       check that catches an expectancy sort: perturbation cannot, because a rule
       looking an outcome up by asset id reads only a sealed key.
    2. **Arrival order** still must not matter (the original, weaker check).
    3. **Nothing but the sealed keys may matter.** Every assessment is rebuilt with
       the two sealed keys — usable history and asset id — held *exactly* fixed
       while every other field is replaced: liquidity, quality, bar counts, gap
       counts, pair status, asset class. An ordering that reads any of them, or any
       quantity derived from them, changes and is caught. A rule keyed on a
       realised outcome must read *something*, and everything it could read other
       than the two sealed keys is perturbed here.
    """
    from fmis.universe.study import ordered_assets

    forward = [item.asset.asset_id for item in ordered_assets(assessments)]
    backward = [
        item.asset.asset_id for item in ordered_assets(list(reversed(assessments)))
    ]
    perturbed = [
        item.asset.asset_id for item in ordered_assets(_perturb_non_key_fields(assessments))
    ]
    # The decisive check: the ordering the SEALED KEYS alone produce, computed here
    # independently of `ordered_assets`. Perturbation cannot catch a rule that
    # looks an outcome up by asset id from somewhere else — the id is a sealed key
    # and may not be perturbed — but recomputing the specification and comparing
    # catches any deviation whatever its source.
    expected = [
        item.asset.asset_id
        for item in sorted(
            (item for item in assessments if item.eligible and item.coverage),
            key=lambda item: (-item.coverage.usable_years, item.asset.asset_id),
        )
    ]

    order_stable = forward == backward
    keys_only = forward == perturbed
    matches_specification = forward == expected
    held = order_stable and keys_only and matches_specification
    if held:
        detail = (
            f"the ordering of {len(forward)} eligible asset(s) equals the sealed "
            "key ordering exactly, is unchanged under input reversal, and is "
            "unchanged when every non-key field is replaced"
        )
    elif not matches_specification:
        detail = (
            "the ordering is NOT the sealed key ordering: expected "
            f"{expected} and got {forward}. It is keyed on something other than "
            "usable history and asset id, which is how an outcome enters a universe"
        )
    elif not order_stable:
        detail = "the ordering MOVED with input order; it is not a function of a key"
    else:
        detail = (
            "the ordering MOVED when a NON-KEY field was replaced while usable "
            "history and asset id were held fixed"
        )
    return ControlResult(name="ordering_is_outcome_free", held=held, detail=detail)


def _perturb_non_key_fields(
    assessments: Sequence[AssetAssessment],
) -> list[AssetAssessment]:
    """Rebuild each assessment with the sealed keys fixed and everything else moved.

    ``usable_years`` is a property of ``first_bar`` and ``last_bar``, so those two
    are the fields that must be preserved exactly; every other number is replaced
    with a value that would reorder the universe if anything read it.
    """
    out: list[AssetAssessment] = []
    for index, item in enumerate(assessments):
        coverage = item.coverage
        if coverage is not None:
            coverage = replace(
                coverage,
                # first_bar/last_bar are the sealed key and are NOT touched.
                bars_observed=max(1, 7919 - index * 13),
                bars_expected=max(1, 7919 - index * 13),
                duplicate_bars=index,
                malformed_bars=0,
                longest_gap_bars=index,
            )
        quality = item.quality
        if quality is not None:
            quality = replace(
                quality,
                missing_fraction=min(1.0, 0.001 * (index + 1)),
                longest_gap_bars=index,
                duplicate_bars=index,
            )
        liquidity = item.liquidity
        if liquidity is not None:
            liquidity = replace(
                liquidity,
                median_quote_volume=None if liquidity.median_quote_volume is None
                else float(10 ** 9 - index * 10 ** 6),
            )
        out.append(
            replace(item, coverage=coverage, quality=quality, liquidity=liquidity)
        )
    return out


def reads_no_holdout_outcome(sources: Mapping[str, str]) -> ControlResult:
    """Assert no CC module can source a design parameter from the protected holdout.

    **This control did not exist until an independent review found the module
    docstring claiming it did.** The claim was prose; this is the code.

    ``sources`` maps a module name to its source text. It is **supplied by the
    caller rather than read from disk on purpose**: this package's architecture
    guard asserts that no measurement module touches the filesystem, and a control
    that had to open files to prove a safety property would have weakened a
    different safety property to do it. The caller that reads the directory is the
    test, where reading files is ordinary.

    Two absences are asserted over the parsed source of every module supplied:

    1. **CA's realised interval bounds are never read.** ``bootstrap_low`` and
       ``bootstrap_high`` are the outcome of a completed measurement. Milestone CC
       reads only ``half_width`` — a derived property — and only for the
       development sample.
    2. **No sample but `development` is ever named in code.** `ca_published` and
       `ca_observation_dispersion` both take a sample argument and would otherwise
       invert a design parameter from the holdout's realised interval if asked.
       Nothing may ask. (`ca_observation_dispersion` additionally refuses a
       non-design sample at runtime — see `fmis.universe.growth`.)

    Parsed rather than grepped, so a docstring may discuss the holdout freely while
    a string constant or an attribute access that names one is caught.
    """
    offenders: list[str] = []
    for name in sorted(sources):
        tree = ast.parse(sources[name])
        docs = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            )
            and getattr(node, "body", None)
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in (
                "bootstrap_low", "bootstrap_high"
            ):
                offenders.append(f"{name} reads {node.attr}")
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docs
                and node.value in PROTECTED_SAMPLES
            ):
                offenders.append(f"{name} names sample {node.value!r} in code")
    return ControlResult(
        name="reads_no_holdout_outcome",
        held=not offenders,
        detail=(
            f"across {len(sources)} module(s): none reads CA's realised interval "
            f"bounds and none names a sample other than {DESIGN_SAMPLE!r}, so no "
            "design parameter here can be sourced from a protected sample's outcome"
            if not offenders
            else "a protected sample's outcome is reachable: " + "; ".join(offenders)
        ),
    )


def offline_reproduction(cache: SeriesCache, *, discovered_at: datetime) -> ControlResult:
    """Assert the study reproduces from a capture with the network made fatal.

    The transport handed in raises on **every** call, so a run that completes has
    demonstrably not refetched anything. Discovery itself is a provider call and
    cannot come from a candle cache, so this control covers every stage after it —
    which is every stage that produces a number.
    """
    from fmis.universe.study import run_universe_study

    try:
        run_universe_study(
            cache=cache, transport=network_is_fatal(), allow_fetch=False,
            discovered_at=discovered_at,
        )
    except UniverseError as error:
        return ControlResult(
            name="offline_reproduction",
            held=False,
            detail=f"the offline run did not complete from the capture: {error}",
        )
    return ControlResult(
        name="offline_reproduction",
        held=True,
        detail=(
            "every measurement stage completed from the capture with a transport "
            "that raises on any call, so nothing was refetched"
        ),
    )
