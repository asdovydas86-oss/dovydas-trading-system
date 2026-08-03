"""Milestone AI — deterministic market-regime classification.

`ARCH` §9 asks for an explicit, testable classification of the *environment* that
higher layers can condition on, carrying evidence and uncertainty rather than a
bare word, and reproducible on historical data.

The rules that matter most here are the ones `docs/analysis-notes.md` bought
expensively. The v2 analyzer's regime gate was directional and its two branches
were not mirror images, so one side of the book began every analysis two free
confirmations ahead. This suite pins the three structural answers to that: the
engine never learns which way a trend points, correlated evidence votes once per
family, and a threshold band is one number whose two edges are multiplicative
mirrors — so an asymmetric gate cannot be written through the API at all.
"""

from __future__ import annotations

import ast
import pathlib
import pickle
import re
import subprocess
import sys
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from fmis.market_regime import (
    DEFAULT_POLICY,
    FAMILY_MOVING_AVERAGES,
    FAMILY_SWING_STRUCTURE,
    FAMILY_TRUE_RANGE,
    FAMILY_VOLUME,
    EvidenceStatus,
    MarketRegime,
    ParticipationState,
    RegimeDimension,
    RegimeDimensionName,
    RegimeEvidence,
    RegimeInput,
    RegimeInputError,
    RegimePolicy,
    RegimePolicyError,
    StructureState,
    VolatilityState,
    classify_regime,
)
from fmis.structural_trend import StructuralTrendType

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "fmis"
PACKAGE_DIR = SRC / "market_regime"


# ============================ fixtures =======================================


def make_input(**overrides: object) -> RegimeInput:
    """A complete, ordinary input: trending structure, steady vol, typical volume."""
    fields: dict = dict(
        symbol="BTCUSDT",
        timeframe="4h",
        as_of=_BASE,
        structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        last_index=100,
        latest_change_index=None,
        close=110.0,
        ema_fast=100.0,
        ema_slow=95.0,
        atr_fast=10.0,
        atr_slow=10.0,
        participation_ratio=1.0,
    )
    fields.update(overrides)
    return RegimeInput(**fields)  # type: ignore[arg-type]


def state(name: RegimeDimensionName, **overrides: object):
    return classify_regime(make_input(**overrides)).by_dimension[name].state


# ============ 1. every state is reachable ===================================


def test_structure_trending_needs_both_families_to_agree() -> None:
    got = state(
        RegimeDimensionName.STRUCTURE,
        structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
        close=110.0,
        ema_fast=100.0,
        ema_slow=95.0,
    )
    assert got is StructureState.TRENDING


def test_structure_ranging_when_both_families_say_so() -> None:
    got = state(
        RegimeDimensionName.STRUCTURE,
        structural_trend=StructuralTrendType.NEUTRAL,
        close=97.0,
        ema_fast=100.0,
        ema_slow=95.0,
    )
    assert got is StructureState.RANGING


def test_structure_indeterminate_when_the_families_disagree() -> None:
    dimension = classify_regime(
        make_input(
            structural_trend=StructuralTrendType.SUSTAINED_HIGHER,
            close=97.0,
            ema_fast=100.0,
            ema_slow=95.0,
        )
    ).by_dimension[RegimeDimensionName.STRUCTURE]
    assert dimension.state is StructureState.INDETERMINATE
    assert len(dimension.conflicting) == 2
    assert dimension.reason is not None and "disagree" in dimension.reason


def test_structure_insufficient_when_a_family_cannot_be_read() -> None:
    dimension = classify_regime(
        make_input(structural_trend=StructuralTrendType.INDETERMINATE)
    ).by_dimension[RegimeDimensionName.STRUCTURE]
    assert dimension.state is StructureState.INSUFFICIENT
    assert dimension.reason is not None and "both evidence families" in dimension.reason


def test_structure_transitioning_on_a_recent_change_of_character() -> None:
    dimension = classify_regime(
        make_input(last_index=100, latest_change_index=98)
    ).by_dimension[RegimeDimensionName.STRUCTURE]
    assert dimension.state is StructureState.TRANSITIONING
    assert dimension.consistent[0].source == FAMILY_SWING_STRUCTURE
    assert "change of character 2 bars ago" in dimension.consistent[0].observed


@pytest.mark.parametrize(
    "fast,slow,expected",
    [
        (13.0, 10.0, VolatilityState.EXPANDING),
        (10.0, 10.0, VolatilityState.STEADY),
        (7.0, 10.0, VolatilityState.CONTRACTING),
    ],
)
def test_every_volatility_state_is_reachable(fast, slow, expected) -> None:
    assert state(RegimeDimensionName.VOLATILITY, atr_fast=fast, atr_slow=slow) is expected


@pytest.mark.parametrize(
    "ratio,expected",
    [
        (1.5, ParticipationState.ELEVATED),
        (1.0, ParticipationState.TYPICAL),
        (0.5, ParticipationState.SUBDUED),
    ],
)
def test_every_participation_state_is_reachable(ratio, expected) -> None:
    assert state(RegimeDimensionName.PARTICIPATION, participation_ratio=ratio) is expected


# ============ 2. no direction, anywhere =====================================


def test_swapping_the_trend_direction_changes_nothing() -> None:
    """The engine must not be able to tell a rising structure from a falling one."""
    higher = classify_regime(
        make_input(structural_trend=StructuralTrendType.SUSTAINED_HIGHER)
    )
    lower = classify_regime(
        make_input(structural_trend=StructuralTrendType.SUSTAINED_LOWER)
    )
    assert higher.dimensions == lower.dimensions


def test_mirroring_price_around_the_averages_changes_nothing() -> None:
    """Beyond both averages is beyond both, whichever side it is beyond."""
    above = classify_regime(make_input(close=110.0, ema_fast=100.0, ema_slow=95.0))
    below = classify_regime(make_input(close=90.0, ema_fast=100.0, ema_slow=105.0))
    assert (
        above.by_dimension[RegimeDimensionName.STRUCTURE].state
        is below.by_dimension[RegimeDimensionName.STRUCTURE].state
    )


#: Words a regime may never use. Matched as **whole words**, not substrings:
#: "up" is a direction, but "warming up" is a warm-up state and "group" is a
#: noun, and a substring scan would fail on both while teaching nobody anything.
_DIRECTIONAL = frozenset(
    {
        "bullish", "bearish", "buy", "sell", "long", "short", "up", "down",
        "rising", "falling", "higher", "lower", "signal", "recommend", "entry",
        "target", "confidence", "score", "profit", "bias", "verdict",
    }
)


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def test_no_directional_vocabulary_in_the_result_models() -> None:
    for enum in (StructureState, VolatilityState, ParticipationState, EvidenceStatus):
        for member in enum:
            assert not (_words(member.value) & _DIRECTIONAL), (enum, member)


def test_no_directional_vocabulary_in_any_produced_evidence() -> None:
    """Every reachable evidence string, over a wide sweep of inputs."""
    seen: set[str] = set()
    for trend in StructuralTrendType:
        for close in (90.0, 97.0, 110.0, None):
            for change in (None, 99, 50):
                for ratio in (0.5, 1.0, 1.5, None):
                    regime = classify_regime(
                        make_input(
                            structural_trend=trend,
                            close=close,
                            latest_change_index=change,
                            participation_ratio=ratio,
                        )
                    )
                    for dimension in regime.dimensions:
                        for item in dimension.evidence:
                            seen.add(item.observed.lower())
                            seen.add(item.source.lower())
                        if dimension.reason:
                            seen.add(dimension.reason.lower())
    assert seen
    for text in seen:
        offending = _words(text) & _DIRECTIONAL
        assert not offending, (offending, text)


def test_the_result_carries_no_overall_state_and_no_score() -> None:
    regime = classify_regime(make_input())
    for banned in ("overall", "score", "confidence", "rank", "verdict", "bias"):
        assert not hasattr(regime, banned), banned
        assert banned not in {f for f in MarketRegime.__dataclass_fields__}


# ============ 3. correlated evidence votes once =============================


def test_each_family_appears_in_exactly_one_dimension() -> None:
    """No number may push two dimensions and look like corroboration."""
    regime = classify_regime(make_input())
    families_by_dimension = {
        d.name: {item.source for item in d.evidence} for d in regime.dimensions
    }
    seen: set[str] = set()
    for families in families_by_dimension.values():
        assert not (families & seen), families & seen
        seen |= families
    assert seen == {
        FAMILY_SWING_STRUCTURE,
        FAMILY_MOVING_AVERAGES,
        FAMILY_TRUE_RANGE,
        FAMILY_VOLUME,
    }


def test_structure_counts_two_families_not_three_observations() -> None:
    """The swing family contributes trend *and* change of character as one vote.

    Both are structure evidence — `docs/analysis-notes.md` §1 names exactly this
    kind of pair as the v2 double count — so they share a family name and the
    dimension still requires the *moving averages* family to agree before it
    classifies.
    """
    dimension = classify_regime(
        make_input(latest_change_index=50, last_index=100)
    ).by_dimension[RegimeDimensionName.STRUCTURE]
    swing_items = [i for i in dimension.evidence if i.source == FAMILY_SWING_STRUCTURE]
    assert len(swing_items) == 2
    assert len({i.source for i in dimension.evidence}) == 2


def test_one_readable_family_is_never_enough_to_classify_structure() -> None:
    """A single free confirmation is what produced the v2 bias; it is refused."""
    only_swings = classify_regime(
        make_input(close=None, ema_fast=None, ema_slow=None)
    ).by_dimension[RegimeDimensionName.STRUCTURE]
    assert only_swings.state is StructureState.INSUFFICIENT

    only_averages = classify_regime(
        make_input(structural_trend=StructuralTrendType.INDETERMINATE)
    ).by_dimension[RegimeDimensionName.STRUCTURE]
    assert only_averages.state is StructureState.INSUFFICIENT


# ============ 4. unavailable is not negative ================================


def test_unavailable_evidence_is_never_counted_as_conflicting() -> None:
    regime = classify_regime(
        make_input(
            structural_trend=StructuralTrendType.INDETERMINATE,
            close=None,
            ema_fast=None,
            ema_slow=None,
            atr_fast=None,
            atr_slow=None,
            participation_ratio=None,
        )
    )
    for dimension in regime.dimensions:
        assert dimension.conflicting == ()
        assert dimension.consistent == ()
        assert dimension.unavailable


def test_a_stale_change_of_character_is_context_not_conflict() -> None:
    dimension = classify_regime(
        make_input(last_index=100, latest_change_index=10)
    ).by_dimension[RegimeDimensionName.STRUCTURE]
    stale = [i for i in dimension.context if "change of character" in i.observed]
    assert len(stale) == 1
    assert stale[0].status is EvidenceStatus.CONTEXT
    assert dimension.state is StructureState.TRENDING


def test_warm_up_propagates_to_each_dimension_independently() -> None:
    regime = classify_regime(make_input(atr_slow=None))
    assert regime.by_dimension[RegimeDimensionName.VOLATILITY].state is (
        VolatilityState.INSUFFICIENT
    )
    assert regime.by_dimension[RegimeDimensionName.STRUCTURE].state is (
        StructureState.TRENDING
    )
    assert regime.by_dimension[RegimeDimensionName.PARTICIPATION].state is (
        ParticipationState.TYPICAL
    )


def test_a_non_positive_baseline_is_insufficient_not_a_division() -> None:
    assert state(RegimeDimensionName.VOLATILITY, atr_slow=0.0) is (
        VolatilityState.INSUFFICIENT
    )


# ============ 5. the policy cannot express an asymmetric gate ===============


def test_a_band_is_one_number_producing_two_mirrored_edges() -> None:
    policy = RegimePolicy(volatility_band=0.25)
    assert policy.volatility_upper_edge == 1.25
    assert policy.volatility_lower_edge == pytest.approx(1.0 / 1.25)
    assert policy.volatility_upper_edge * policy.volatility_lower_edge == pytest.approx(1.0)


def test_no_field_can_skew_one_edge_against_the_other() -> None:
    """The v2 failure, made unrepresentable rather than validated against."""
    fields = set(RegimePolicy.__dataclass_fields__)
    assert fields == {
        "policy_id",
        "volatility_band",
        "participation_band",
        "transition_lookback_bars",
    }
    for banned in ("upper", "lower", "expansion", "contraction", "elevated", "subdued"):
        assert not any(banned in f for f in fields), banned


def test_expansion_and_contraction_are_symmetric_on_real_ratios() -> None:
    """A ratio and its reciprocal must classify as exact mirrors."""
    for band in (0.1, 0.2, 0.5):
        policy = RegimePolicy(volatility_band=band)
        for factor in (1.05, 1.2, 1.5, 3.0):
            up = classify_regime(
                make_input(atr_fast=10.0 * factor, atr_slow=10.0), policy
            ).by_dimension[RegimeDimensionName.VOLATILITY].state
            down = classify_regime(
                make_input(atr_fast=10.0, atr_slow=10.0 * factor), policy
            ).by_dimension[RegimeDimensionName.VOLATILITY].state
            if up is VolatilityState.EXPANDING:
                assert down is VolatilityState.CONTRACTING, (band, factor)
            else:
                assert up is VolatilityState.STEADY and down is VolatilityState.STEADY


@pytest.mark.parametrize("bad", [0.0, -0.1, float("inf"), float("nan")])
def test_an_invalid_band_is_rejected(bad: float) -> None:
    with pytest.raises((RegimePolicyError, ValueError)):
        RegimePolicy(volatility_band=bad)


@pytest.mark.parametrize("bad", ["", "   ", None, 5])
def test_an_invalid_policy_id_is_rejected(bad: object) -> None:
    with pytest.raises((RegimePolicyError, TypeError)):
        RegimePolicy(policy_id=bad)  # type: ignore[arg-type]


def test_a_negative_transition_lookback_is_rejected() -> None:
    with pytest.raises(RegimePolicyError):
        RegimePolicy(transition_lookback_bars=-1)
    with pytest.raises(TypeError):
        RegimePolicy(transition_lookback_bars=True)  # type: ignore[arg-type]


def test_threshold_boundaries_are_inclusive_on_both_sides() -> None:
    policy = RegimePolicy(volatility_band=0.2)
    exact_up = policy.volatility_upper_edge
    exact_down = policy.volatility_lower_edge
    assert classify_regime(
        make_input(atr_fast=exact_up, atr_slow=1.0), policy
    ).by_dimension[RegimeDimensionName.VOLATILITY].state is VolatilityState.EXPANDING
    assert classify_regime(
        make_input(atr_fast=exact_down, atr_slow=1.0), policy
    ).by_dimension[RegimeDimensionName.VOLATILITY].state is VolatilityState.CONTRACTING


def test_the_policy_travels_with_the_result() -> None:
    policy = RegimePolicy(policy_id="experiment-7", volatility_band=0.33)
    regime = classify_regime(make_input(), policy)
    assert regime.policy is policy
    assert dict(regime.policy.describe())["policy_id"] == "experiment-7"


def test_the_default_policy_is_shared_and_frozen() -> None:
    assert classify_regime(make_input()).policy is DEFAULT_POLICY
    with pytest.raises(FrozenInstanceError):
        DEFAULT_POLICY.volatility_band = 0.5  # type: ignore[misc]


# ============ 6. determinism, immutability, replay ==========================


def test_classification_is_a_pure_function_of_its_inputs() -> None:
    subject = make_input()
    assert classify_regime(subject) == classify_regime(subject)


def test_results_are_immutable_and_hashable_evidence() -> None:
    regime = classify_regime(make_input())
    with pytest.raises(FrozenInstanceError):
        regime.symbol = "ETHUSDT"  # type: ignore[misc]
    item = regime.dimensions[0].evidence[0]
    assert hash(item) == hash(
        RegimeEvidence(item.source, item.status, item.observed, item.value)
    )


def test_a_regime_is_not_picklable_and_neither_is_any_sibling_sheet() -> None:
    """Recorded rather than special-cased: `MappingProxyType` metadata cannot pickle.

    `MarketRegime` copies its metadata into a read-only mapping, which is the
    repository's established convention — `StructuralFactSheet` and
    `MultiTimeframeFactSheet` do the same and are equally unpicklable. Giving
    this one model a custom ``__reduce__`` would make it the odd one out for no
    consumer that exists: persistence is open decision **D-01**, and when it is
    settled the answer belongs to every metadata-carrying model at once.

    Equality and immutability, which consumers *do* rely on, are asserted above.
    """
    regime = classify_regime(make_input())
    with pytest.raises(TypeError):
        pickle.dumps(regime)

    from fmis.pipeline.structural_facts import StructuralFactSheet

    assert "metadata" in StructuralFactSheet.__dataclass_fields__


def test_metadata_is_copied_and_read_only() -> None:
    source = {"a": 1}
    regime = classify_regime(make_input(metadata=source))
    source["a"] = 2
    assert regime.metadata["a"] == 1
    with pytest.raises(TypeError):
        regime.metadata["b"] = 3  # type: ignore[index]


def test_classification_is_stable_across_processes() -> None:
    script = (
        "from tests.test_market_regime import make_input;"
        "from fmis.market_regime import classify_regime;"
        "r = classify_regime(make_input());"
        "print([(d.name.value, d.state.value) for d in r.dimensions])"
    )
    outputs = set()
    for seed in ("0", "1", "42", "12345"):
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin", "PYTHONPATH": "src:."},
            cwd=str(pathlib.Path(__file__).resolve().parent.parent),
        )
        assert proc.returncode == 0, proc.stderr
        outputs.add(proc.stdout.strip())
    assert len(outputs) == 1


def test_dimension_order_is_fixed_and_asserted() -> None:
    regime = classify_regime(make_input())
    assert [d.name for d in regime.dimensions] == [
        RegimeDimensionName.STRUCTURE,
        RegimeDimensionName.VOLATILITY,
        RegimeDimensionName.PARTICIPATION,
    ]


def test_a_regime_cannot_repeat_or_reorder_its_dimensions() -> None:
    regime = classify_regime(make_input())
    first = regime.dimensions[0]
    with pytest.raises(RegimeInputError):
        MarketRegime(
            symbol="X", timeframe="4h", as_of=_BASE,
            dimensions=(first, first), policy=DEFAULT_POLICY,
        )
    with pytest.raises(RegimeInputError):
        MarketRegime(
            symbol="X", timeframe="4h", as_of=_BASE,
            dimensions=tuple(reversed(regime.dimensions)), policy=DEFAULT_POLICY,
        )


# ============ 7. input validation ===========================================


@pytest.mark.parametrize(
    "field", ["close", "ema_fast", "ema_slow", "atr_fast", "atr_slow",
              "participation_ratio"],
)
def test_a_non_finite_number_is_rejected(field: str) -> None:
    with pytest.raises(RegimeInputError):
        make_input(**{field: float("inf")})
    with pytest.raises(RegimeInputError):
        make_input(**{field: float("nan")})


def test_a_negative_index_is_rejected() -> None:
    with pytest.raises(RegimeInputError):
        make_input(last_index=-1)


def test_a_change_after_the_last_candle_is_rejected() -> None:
    with pytest.raises(RegimeInputError) as excinfo:
        make_input(last_index=10, latest_change_index=11)
    assert "cannot exceed" in str(excinfo.value)


def test_an_empty_symbol_or_timeframe_is_rejected() -> None:
    with pytest.raises(RegimeInputError):
        make_input(symbol="")
    with pytest.raises(RegimeInputError):
        make_input(timeframe="")


def test_the_wrong_argument_types_are_rejected() -> None:
    with pytest.raises(TypeError):
        classify_regime("not an input")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        classify_regime(make_input(), "not a policy")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        make_input(structural_trend="sustained_higher")


# ============ 8. boundaries and purity ======================================


def test_the_engine_imports_one_name_from_the_repository() -> None:
    """`fmis.structural_trend` only — no pipeline, no features, no data."""
    modules: set[str] = set()
    for py in PACKAGE_DIR.rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("fmis") and not node.module.startswith(
                    "fmis.market_regime"
                ):
                    modules.add(node.module)
    assert modules == {"fmis.structural_trend"}


def _code_without_docstrings(path: pathlib.Path) -> str:
    """Source with docstrings blanked, so prose is not mistaken for a dependency.

    This package documents *why* it cannot see the application layer, which means
    naming it. A raw scan would read the explanation as the violation. Comments
    and non-docstring literals are still scanned, so a dynamic
    ``importlib.import_module("fmis.pipeline")`` stays caught.
    """
    source = path.read_text()
    lines = source.splitlines(keepends=True)
    for node in ast.walk(ast.parse(source)):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body or not isinstance(body[0], ast.Expr):
            continue
        doc = body[0].value
        if isinstance(doc, ast.Constant) and isinstance(doc.value, str):
            for lineno in range(doc.lineno, doc.end_lineno + 1):
                lines[lineno - 1] = "\n"
    return "".join(lines)


def test_the_engine_cannot_see_the_application_layer() -> None:
    for py in PACKAGE_DIR.rglob("*.py"):
        code = _code_without_docstrings(py)
        for banned in ("fmis.pipeline", "fmis.decision_support", "fmis.providers"):
            assert banned not in code, f"{py}: {banned}"


def test_the_engine_reads_no_clock_and_no_network() -> None:
    for py in PACKAGE_DIR.rglob("*.py"):
        code = _code_without_docstrings(py)
        for banned in ("datetime.now", "utcnow", "time.time", "time.monotonic",
                       "requests", "urllib", "httpx", "random"):
            assert banned not in code, f"{py}: {banned}"


def test_no_engine_below_imports_this_package() -> None:
    root = PACKAGE_DIR.parent
    permitted = {root / "pipeline", PACKAGE_DIR}
    for py in root.rglob("*.py"):
        if py.parent in permitted:
            continue
        assert "fmis.market_regime" not in py.read_text(), py


def test_the_public_surface_is_exactly_what_is_documented() -> None:
    import fmis.market_regime as mr

    assert len(mr.__all__) == 19
    assert len(set(mr.__all__)) == len(mr.__all__)
    for name in mr.__all__:
        assert hasattr(mr, name), name


def test_no_export_collides_with_another_package() -> None:
    """`VolatilityRegime` already exists in `fmis.features`; ours is `VolatilityState`."""
    import fmis.features as features
    import fmis.market_regime as mr

    assert not set(mr.__all__) & set(features.__all__)
    assert "VolatilityRegime" in features.__all__
    assert "VolatilityState" in mr.__all__


# ============ 9. boundaries and statuses the mutation gate found ============


def test_an_indeterminate_trend_is_unavailable_not_conflicting() -> None:
    """Survivor 4: the swing family's *status*, asserted directly.

    Restating hid this. `_restated` leaves an `UNAVAILABLE` item alone, so a
    mutation turning the indeterminate-trend branch into `CONFLICTING` was
    laundered into `CONTEXT` by the insufficient path and no assertion noticed.
    """
    dimension = classify_regime(
        make_input(structural_trend=StructuralTrendType.INDETERMINATE)
    ).by_dimension[RegimeDimensionName.STRUCTURE]
    swing = next(i for i in dimension.evidence if i.source == FAMILY_SWING_STRUCTURE)
    assert swing.status is EvidenceStatus.UNAVAILABLE


def test_restating_never_promotes_unavailable_evidence() -> None:
    """Survivor 16: silence must survive every branch that relabels evidence."""
    dimension = classify_regime(
        make_input(close=None, ema_fast=None, ema_slow=None)
    ).by_dimension[RegimeDimensionName.STRUCTURE]
    assert dimension.state is StructureState.INSUFFICIENT
    averages = next(
        i for i in dimension.evidence if i.source == FAMILY_MOVING_AVERAGES
    )
    assert averages.status is EvidenceStatus.UNAVAILABLE
    assert dimension.conflicting == ()
    assert averages not in dimension.context


def test_the_transition_lookback_boundary_is_inclusive() -> None:
    """Survivor 12: exactly `transition_lookback_bars` ago still transitions."""
    policy = RegimePolicy(transition_lookback_bars=5)
    inside = classify_regime(
        make_input(last_index=100, latest_change_index=95), policy
    ).by_dimension[RegimeDimensionName.STRUCTURE]
    outside = classify_regime(
        make_input(last_index=100, latest_change_index=94), policy
    ).by_dimension[RegimeDimensionName.STRUCTURE]
    assert inside.state is StructureState.TRANSITIONING
    assert outside.state is not StructureState.TRANSITIONING


def test_the_participation_boundaries_are_inclusive_on_both_sides() -> None:
    """Survivors 22 and 23: the volatility boundaries were tested; these were not."""
    policy = RegimePolicy(participation_band=0.2)
    at_upper = classify_regime(
        make_input(participation_ratio=policy.participation_upper_edge), policy
    ).by_dimension[RegimeDimensionName.PARTICIPATION]
    at_lower = classify_regime(
        make_input(participation_ratio=policy.participation_lower_edge), policy
    ).by_dimension[RegimeDimensionName.PARTICIPATION]
    assert at_upper.state is ParticipationState.ELEVATED
    assert at_lower.state is ParticipationState.SUBDUED


def test_the_participation_edges_are_multiplicative_mirrors() -> None:
    """Survivor 32: asserted for volatility, and not for participation."""
    for band in (0.1, 0.2, 0.45):
        policy = RegimePolicy(participation_band=band)
        assert policy.participation_upper_edge == 1.0 + band
        assert policy.participation_lower_edge == pytest.approx(1.0 / (1.0 + band))
        assert (
            policy.participation_upper_edge * policy.participation_lower_edge
            == pytest.approx(1.0)
        )
        # And behaviourally: a ratio and its reciprocal are exact mirrors.
        for factor in (1.05, 1.3, 2.0):
            up = classify_regime(
                make_input(participation_ratio=factor), policy
            ).by_dimension[RegimeDimensionName.PARTICIPATION].state
            down = classify_regime(
                make_input(participation_ratio=1.0 / factor), policy
            ).by_dimension[RegimeDimensionName.PARTICIPATION].state
            if up is ParticipationState.ELEVATED:
                assert down is ParticipationState.SUBDUED, (band, factor)
            else:
                assert up is down is ParticipationState.TYPICAL


def test_the_policy_field_rejects_anything_that_is_not_a_policy() -> None:
    """Review P2-1: the provenance field was typed `Any` and never checked.

    A result citing a policy that could not have produced it is worse than one
    citing none, because it reads as reproducible.
    """
    regime = classify_regime(make_input())
    for bad in ("regime-v1", {"volatility_band": 0.2}, None, 0.2):
        with pytest.raises(TypeError):
            MarketRegime(
                symbol="X",
                timeframe="4h",
                as_of=_BASE,
                dimensions=regime.dimensions,
                policy=bad,  # type: ignore[arg-type]
            )


def test_the_package_carries_no_unreachable_helper() -> None:
    """Review P2-2: two modules defined a validator neither of them called."""
    for py in PACKAGE_DIR.rglob("*.py"):
        tree = ast.parse(py.read_text())
        # Module-level private functions only. Methods are reached through
        # `self`, and `__post_init__` is called by the dataclass machinery —
        # neither appears as a bare Name, so counting them would make this
        # guard fire on correct code.
        defined = {
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name.startswith("_")
            and not node.name.startswith("__")
        }
        referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        unreachable = defined - referenced
        assert unreachable == set(), f"{py}: {unreachable}"


# ============ 10. every validation branch, exercised =======================
#
# The repository's standard for milestone code is 100 % coverage of what the
# milestone touched, and a validation branch nothing reaches is a branch nothing
# has checked the wording of.


@pytest.mark.parametrize(
    "kwargs,exc",
    [
        (dict(source=""), TypeError),
        (dict(source=7), TypeError),
        (dict(status="consistent"), TypeError),
        (dict(observed=""), TypeError),
        (dict(observed=None), TypeError),
        (dict(value="1.0"), TypeError),
        (dict(value=True), TypeError),
    ],
)
def test_evidence_validates_every_field(kwargs: dict, exc: type) -> None:
    base = dict(
        source="volume", status=EvidenceStatus.CONSISTENT, observed="seen", value=1.0
    )
    with pytest.raises(exc):
        RegimeEvidence(**{**base, **kwargs})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(name="structure"),
        dict(state="trending"),
        dict(evidence=[]),
        dict(evidence=("not evidence",)),
        dict(reason=7),
    ],
)
def test_a_dimension_validates_every_field(kwargs: dict) -> None:
    base = dict(
        name=RegimeDimensionName.STRUCTURE,
        state=StructureState.TRENDING,
        evidence=(),
        reason=None,
    )
    with pytest.raises(TypeError):
        RegimeDimension(**{**base, **kwargs})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs,exc",
    [
        (dict(symbol=""), RegimeInputError),
        (dict(timeframe=""), RegimeInputError),
        (dict(as_of="2026-01-01"), TypeError),
        (dict(dimensions=["not a tuple"]), TypeError),
        (dict(dimensions=("not a dimension",)), TypeError),
    ],
)
def test_a_regime_validates_every_field(kwargs: dict, exc: type) -> None:
    good = classify_regime(make_input())
    base = dict(
        symbol="BTCUSDT",
        timeframe="4h",
        as_of=_BASE,
        dimensions=good.dimensions,
        policy=DEFAULT_POLICY,
    )
    with pytest.raises(exc):
        MarketRegime(**{**base, **kwargs})  # type: ignore[arg-type]


def test_the_input_rejects_a_wrong_as_of_type() -> None:
    with pytest.raises(TypeError):
        make_input(as_of="2026-01-01")


@pytest.mark.parametrize("field", ["last_index", "latest_change_index"])
def test_the_input_rejects_a_non_int_index(field: str) -> None:
    with pytest.raises(TypeError):
        make_input(**{field: 1.5})
    with pytest.raises(TypeError):
        make_input(**{field: True})


@pytest.mark.parametrize(
    "field", ["close", "ema_fast", "ema_slow", "atr_fast", "atr_slow",
              "participation_ratio"],
)
def test_the_input_rejects_a_non_numeric_value(field: str) -> None:
    with pytest.raises(TypeError):
        make_input(**{field: "100"})
    with pytest.raises(TypeError):
        make_input(**{field: True})


def test_a_non_numeric_band_is_a_type_error() -> None:
    with pytest.raises(TypeError):
        RegimePolicy(volatility_band="0.2")  # type: ignore[arg-type]
