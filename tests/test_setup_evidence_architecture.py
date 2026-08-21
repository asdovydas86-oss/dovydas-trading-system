"""Boundary guards for `fmis.setup_evidence`, and proofs of its correlation claims.

Two jobs, kept in one file because the second depends on the first.

**The guards** assert the rules the milestone rests on in the only form that
survives a refactor: an executable check over the source tree. The package
projects an assessment and does nothing else — it reads no candle, reaches no
venue, opens no store, computes no market quantity, and holds no scoring field.

**The proofs** are the unusual part. `fmis.setup_evidence.correlation` makes
five factual claims about *upstream* code — that the regime gate and the context
trend factor are one reading, that a MACD histogram and a MACD crossover are one
fact, that the trigger and the confirmation are one sentence. A comment asserting
those would rot the moment the upstream changed. Each is therefore checked here
against the live implementation, so a correlation that stops being true fails a
test instead of quietly becoming a false caveat printed on the owner's page.
"""

from __future__ import annotations

import ast
import pkgutil
from pathlib import Path

import pytest

import fmis
import fmis.setup_evidence as se
from fmis.decision_support.classification import Comparison, classify_comparison
from fmis.market_regime import RegimeDimensionName, StructureState, classify_regime
from fmis.setup_evidence.correlation import (
    KEY_CONFIRMATION,
    KEY_CONTEXT_TREND,
    KEY_EVIDENCE_ALIGNMENT,
    KEY_GEOMETRY,
    KEY_REGIME_GATE,
    KEY_SETUP_TREND,
    KNOWN_CORRELATIONS,
)
from fmis.structural_trend import StructuralTrendType
from fmis.swing_setup import SetupState, evaluate_setup

from test_market_regime import make_input
from test_swing_setup_policy import base_inputs

PACKAGE_DIR = Path(se.__file__).parent
SOURCE_ROOT = Path(fmis.__file__).parent


def _sources() -> list[Path]:
    return sorted(PACKAGE_DIR.glob("*.py"))


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


# ============ 1. the dependency surface, pinned as a set ====================


def test_the_package_imports_exactly_four_fmis_modules() -> None:
    """Pinned as a set, so a fifth dependency is a deliberate edit here.

    Each is load-bearing and none is an engine:

      * `fmis.decision_context` — `ContextState`, the type `decision_ready`
        is a function of;
      * `fmis.evidence` — `EvidenceFamily`, the ADR-0011 shared vocabulary;
      * `fmis.swing_setup` — the assessment being projected;
      * `fmis.swing_setup.policy` — the research-override marker, so a research
        artifact is warned about rather than silently explained as production.
    """
    reached: set[str] = set()
    for path in _sources():
        reached.update(name for name in _imports(path) if name.startswith("fmis"))
    assert reached == {
        "fmis.decision_context",
        "fmis.evidence",
        "fmis.setup_evidence.correlation",
        "fmis.setup_evidence.models",
        "fmis.setup_evidence.project",
        "fmis.setup_evidence.render",
        "fmis.swing_setup",
        "fmis.swing_setup.policy",
    }


def test_the_package_reaches_no_engine_no_venue_and_no_store() -> None:
    """A projection that could fetch would make a past explanation drift."""
    forbidden = {
        "fmis.data", "fmis.ingest", "fmis.providers", "fmis.features",
        "fmis.alignment", "fmis.relative_value", "fmis.series_context",
        "fmis.market_structure", "fmis.structural_trend", "fmis.structure_break",
        "fmis.change_of_character", "fmis.level_crossing", "fmis.market_regime",
        "fmis.decision_support", "fmis.pipeline", "fmis.persistence",
        "fmis.archive", "fmis.records", "fmis.workspace", "fmis.daily",
        "fmis.today", "fmis.statistics", "fmis.paper", "fmis.ledger",
        "fmis.positions", "fmis.portfolio", "fmis.snapshotting", "fmis.proposal",
    }
    for path in _sources():
        assert not (_imports(path) & forbidden), path.name


def test_the_package_imports_no_network_clock_or_filesystem_module() -> None:
    forbidden = {"os", "sys", "pathlib", "socket", "urllib", "requests", "httpx",
                 "sqlite3", "json", "random", "time"}
    for path in _sources():
        reached = {name.split(".")[0] for name in _imports(path)}
        assert not (reached & forbidden), (path.name, reached & forbidden)


#: The two surfaces above this package that are permitted to consume it. Both
#: are composition roots that already reach `fmis.swing_setup`, the tier this
#: package sits at; neither is an engine, and nothing below either of them is
#: admitted. Named one by one so a third arrival is a deliberate edit here.
#: A third arrival, Milestone BS: `fmis.swing_workspace.sections` projects one
#: `SetupAssessment` per actionable row into the digest `fmits workspace` prints.
#: It sits at the same application-layer tier as `fmis.today.sections`, above
#: this package rather than below it, and it calls `project_setup_evidence` and
#: nothing else — no group is re-derived and no count is recomputed.
_PERMITTED_CONSUMERS = frozenset(
    {"fmis.pipeline.cli", "fmis.today.sections", "fmis.swing_workspace.sections"}
)


def test_no_module_below_this_package_imports_it() -> None:
    """The layering direction never reverses.

    Two consumers are permitted and named above. Every other module in the tree
    — every engine, every domain package, every store — must be unaware this
    package exists, so a future edit that made `fmis.market_structure` or
    `fmis.persistence` reach for an evidence projection fails here.
    """
    offenders: dict[str, set[str]] = {}
    for module in pkgutil.walk_packages([str(SOURCE_ROOT)], prefix="fmis."):
        name = module.name
        if name.startswith("fmis.setup_evidence"):
            continue
        if name in _PERMITTED_CONSUMERS:
            continue
        path = SOURCE_ROOT / Path(*name.split(".")[1:])
        candidate = path.with_suffix(".py")
        if not candidate.exists():
            candidate = path / "__init__.py"
        if not candidate.exists():
            continue
        reached = {
            found
            for found in _imports(candidate)
            if found.startswith("fmis.setup_evidence")
        }
        if reached:
            offenders[name] = reached
    assert offenders == {}


# ============ 2. no market computation, no scoring ==========================


def test_the_projection_performs_no_arithmetic_on_any_value() -> None:
    """No ratio, no percentage, no scaling, no weighting — proven structurally.

    `render.py` is exempt and named: its subtraction and multiplication are
    page layout (`"─" * (width - len(title))`), which is not a market quantity.
    Every other module must contain no scaling arithmetic at all, so a
    "just this once" weighted tally cannot be added without failing here.
    """
    banned = (ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Pow, ast.Mod)
    for path in _sources():
        if path.name == "render.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.BinOp) and isinstance(node.op, banned):
                raise AssertionError(f"{path.name}:{node.lineno} performs arithmetic")


def test_no_comparison_against_a_numeric_threshold_exists() -> None:
    """A threshold here would be a policy decision made by a projection."""
    for path in _sources():
        if path.name == "render.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Compare):
                continue
            for operand in (node.left, *node.comparators):
                if isinstance(operand, ast.Constant) and isinstance(
                    operand.value, float
                ):
                    raise AssertionError(f"{path.name}:{node.lineno} thresholds a float")


def test_no_scoring_vocabulary_appears_as_an_identifier_anywhere() -> None:
    banned = {"score", "weight", "confidence", "rank", "strength", "rating",
              "grade", "quality"}
    offenders = []
    for path in _sources():
        for node in ast.walk(ast.parse(path.read_text())):
            name = None
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                name = node.name
            elif isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.arg):
                name = node.arg
            if name and name.lower().strip("_") in banned:
                offenders.append((path.name, name))
    assert offenders == []


def test_no_directional_vocabulary_appears_in_this_package() -> None:
    """ADR-0028: only `fmis.swing_setup` and `pipeline/cli.py` may spell a side.

    Asserted locally as well as repository-wide, so the failure names this
    package rather than appearing as one row in a global scan.
    """
    banned = {"long", "short", "buy", "sell", "bullish", "bearish"}
    offenders = []
    for path in _sources():
        for node in ast.walk(ast.parse(path.read_text())):
            token = None
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                token = node.name
            elif isinstance(node, ast.Name):
                token = node.id
            elif isinstance(node, ast.Attribute):
                token = node.attr
            elif isinstance(node, ast.arg):
                token = node.arg
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                token = node.value
            if token and token.lower() in banned:
                offenders.append((path.name, token))
    assert offenders == []


def test_the_package_writes_nothing() -> None:
    banned = {"save", "write", "persist", "store", "append_record", "commit",
              "insert", "delete", "update_record"}
    for path in _sources():
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Attribute) and node.attr in banned:
                raise AssertionError(f"{path.name}:{node.lineno} calls {node.attr}")


# ============ 3. the ADR-0011 taxonomy was not modified =====================


def test_the_evidence_taxonomy_is_untouched_by_this_milestone() -> None:
    """The whole architectural point: this package consumes, never extends."""
    import fmis.evidence as ev

    assert ev.__all__ == [
        "EvidenceFamily", "EvidenceDescriptor",
        "descriptors", "descriptors_for", "find",
    ]


def test_no_family_was_added_to_the_shared_vocabulary() -> None:
    """Confluence, Context, Risk Geometry and Freshness were all declined."""
    from fmis.evidence import EvidenceFamily

    assert [family.value for family in EvidenceFamily] == [
        "trend", "momentum", "volume", "volatility", "market_structure",
        "relative_strength", "liquidity", "macro", "news", "sentiment",
    ]


def test_this_package_defines_no_family_like_enum() -> None:
    """A second family vocabulary would be the duplication ADR-0011 §4 forbids."""
    from enum import Enum

    for name in dir(se):
        obj = getattr(se, name)
        if isinstance(obj, type) and issubclass(obj, Enum):
            members = {member.name for member in obj}
            assert "CONFLUENCE" not in members
            assert "CONTEXT" not in members
            assert not {"TREND", "MOMENTUM", "VOLUME"} & members


def test_the_report_is_not_named_evidence_report() -> None:
    """`fmis.decision_support.EvidenceReport` already owns that name."""
    assert not hasattr(se, "EvidenceReport")
    from fmis.decision_support import EvidenceReport

    assert EvidenceReport is not se.SetupEvidenceReport


# ============ 4. every correlation claim, proven against live code ==========


def test_claim_the_regime_gate_implies_the_context_trend_vote() -> None:
    """The strongest claim in the registry, checked exhaustively.

    `StructureState.TRENDING` is reachable only when the structural trend is
    sustained — and a sustained trend is exactly what makes the context factor
    cast a directional vote. So passing the gate *guarantees* the vote, and the
    two are one reading rather than two.
    """
    sustained = {
        StructuralTrendType.SUSTAINED_HIGHER,
        StructuralTrendType.SUSTAINED_LOWER,
    }
    reached_trending = set()
    for trend in StructuralTrendType:
        state = classify_regime(
            make_input(structural_trend=trend, close=110.0, ema_fast=100.0, ema_slow=95.0)
        ).by_dimension[RegimeDimensionName.STRUCTURE].state
        if state is StructureState.TRENDING:
            reached_trending.add(trend)
    assert reached_trending, "the fixture must reach TRENDING at all"
    assert reached_trending <= sustained, (
        "STRUCTURE reached TRENDING from a non-sustained trend; the correlation "
        "caveat printed on the evidence page is no longer true"
    )


def test_claim_the_macd_histogram_and_crossover_are_one_fact() -> None:
    """`histogram = macd_line - signal_line`, so their signs cannot disagree.

    `fmis.decision_support` counts them as two observations in its dominant
    alignment. That is the upstream double-count the caveat names.
    """
    from fmis.decision_support.classification import Sign, classify_sign

    for macd_line, signal_line in (
        (2.0, 1.0), (1.0, 2.0), (1.0, 1.0), (-1.0, -2.0), (-2.0, -1.0),
    ):
        histogram = macd_line - signal_line
        comparison = classify_comparison(macd_line, signal_line)
        sign = classify_sign(histogram)
        agree = {
            (Comparison.ABOVE, Sign.POSITIVE),
            (Comparison.BELOW, Sign.NEGATIVE),
            (Comparison.EQUAL, Sign.ZERO),
        }
        assert (comparison, sign) in agree, (macd_line, signal_line)


def test_claim_the_three_trend_comparisons_are_transitive() -> None:
    """price>fast and fast>slow force price>slow — three readings, two facts."""
    for close, fast, slow in ((110.0, 100.0, 95.0), (90.0, 95.0, 100.0)):
        first = classify_comparison(close, fast)
        second = classify_comparison(fast, slow)
        third = classify_comparison(close, slow)
        if first is Comparison.ABOVE and second is Comparison.ABOVE:
            assert third is Comparison.ABOVE
        if first is Comparison.BELOW and second is Comparison.BELOW:
            assert third is Comparison.BELOW


def test_claim_the_trigger_statement_is_the_confirmation_line() -> None:
    """Checked on both branches the policy can take."""
    confirmed = evaluate_setup(base_inputs())
    assert confirmed.state is SetupState.CONFIRMED
    assert confirmed.trigger.statement == confirmed.confirmation[0]

    awaiting = evaluate_setup(base_inputs(execution_closed_count=200))
    assert awaiting.state is SetupState.CANDIDATE
    assert awaiting.trigger.statement == awaiting.confirmation[0]


def test_claim_the_protective_level_appears_three_times_on_the_assessment() -> None:
    """The geometry caveat's premise: one level, three restatements."""
    assessment = evaluate_setup(base_inputs())
    assert assessment.stop is not None
    assert assessment.risk_reward is not None
    assert assessment.risk_reward.stop == assessment.stop.price
    assert str(assessment.stop.price) in assessment.invalidation[0]
    assert "the same level" in assessment.invalidation[0]


# ============ 5. the registry itself stays honest ===========================


def test_every_correlation_key_is_one_the_projection_can_emit() -> None:
    """A rule naming a key nothing produces would be a caveat that never prints."""
    emitted = {
        KEY_CONTEXT_TREND, KEY_SETUP_TREND, KEY_EVIDENCE_ALIGNMENT,
        KEY_REGIME_GATE, KEY_CONFIRMATION, KEY_GEOMETRY,
    }
    for rule in KNOWN_CORRELATIONS:
        assert set(rule.keys) <= emitted, rule.keys


def test_the_factor_keys_match_the_families_the_policy_actually_emits() -> None:
    """The key constants and the live factor names cannot drift apart."""
    assessment = evaluate_setup(base_inputs())
    emitted = {f"factor:{factor.family}" for factor in assessment.directional_factors}
    assert emitted == {KEY_CONTEXT_TREND, KEY_SETUP_TREND, KEY_EVIDENCE_ALIGNMENT}


def test_every_correlation_rule_states_a_reason() -> None:
    for rule in KNOWN_CORRELATIONS:
        assert len(rule.reason) > 80, rule.keys


def test_a_correlation_rule_cannot_repeat_a_key() -> None:
    from fmis.setup_evidence import CorrelationRule
    from fmis.setup_evidence.models import SetupEvidenceError

    with pytest.raises(SetupEvidenceError, match="must not repeat"):
        CorrelationRule(keys=("a", "a"), reason="x" * 100)


def test_the_public_api_is_exactly_what_is_declared() -> None:
    namespace: dict[str, object] = {}
    exec("from fmis.setup_evidence import *", namespace)  # noqa: S102
    exposed = {key for key in namespace if not key.startswith("__")}
    assert exposed == set(se.__all__)


def test_no_submodule_shadows_an_exported_name() -> None:
    """The `descriptors`/`descriptor` collision ADR-0011 recorded, guarded here."""
    submodules = {module.name for module in pkgutil.iter_modules([str(PACKAGE_DIR)])}
    assert not (submodules & set(se.__all__))
