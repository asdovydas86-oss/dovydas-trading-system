"""Boundary guards for the trading domain.

These tests do not exercise behaviour. They assert the *rules* the data model
states, in the only form that survives a future refactor: an executable check
over the source tree. Every one of them corresponds to a sentence a later reader
would otherwise have to take on trust.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

import fmis

#: Every package this milestone added. Listed explicitly rather than discovered,
#: so adding a package to the domain is a deliberate edit to this line.
DOMAIN_PACKAGES = (
    "fmis.records",
    "fmis.provenance",
    "fmis.money",
    "fmis.versioning",
    "fmis.accounts",
    "fmis.analysis_record",
    "fmis.snapshotting",
    "fmis.proposal",
    "fmis.ledger",
    "fmis.positions",
    "fmis.portfolio",
    "fmis.risk",
    "fmis.journal",
)

#: The market half, which this milestone did not touch and may not be imported by
#: anything below `fmis.snapshotting`'s composition root.
MARKET_HALF_PACKAGES = frozenset(
    {
        "fmis.data",
        "fmis.ingest",
        "fmis.providers",
        "fmis.features",
        "fmis.alignment",
        "fmis.relative_value",
        "fmis.series_context",
        "fmis.market_structure",
        "fmis.structural_trend",
        "fmis.structure_break",
        "fmis.change_of_character",
        "fmis.level_crossing",
        "fmis.market_regime",
        "fmis.evidence",
        "fmis.decision_support",
        "fmis.decision_context",
        "fmis.swing_setup",
        "fmis.workspace",
        "fmis.daily",
        "fmis.pipeline",
        "fmis.trading_context",
    }
)

SOURCE_ROOT = Path(fmis.__file__).parent


def _modules_of(package_name: str) -> list[str]:
    package = importlib.import_module(package_name)
    return [package_name] + [
        module.name
        for module in pkgutil.iter_modules(
            package.__path__, prefix=f"{package_name}."
        )
    ]


def _imports_of(module_name: str) -> set[str]:
    module = importlib.import_module(module_name)
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


# --------------------------------------------------------------------------
# Law 6 — the trading domain reads the market half and is never read by it.
# --------------------------------------------------------------------------


def test_no_market_half_package_imports_the_trading_domain() -> None:
    """*Or the analysis becomes a function of the position — the oldest bias in trading.*"""
    offenders: dict[str, set[str]] = {}
    domain_roots = set(DOMAIN_PACKAGES)
    for package_name in sorted(MARKET_HALF_PACKAGES):
        for module_name in _modules_of(package_name):
            reached = {
                imported
                for imported in _imports_of(module_name)
                if any(
                    imported == root or imported.startswith(f"{root}.")
                    for root in domain_roots
                )
            }
            if reached:
                offenders[module_name] = reached
    assert offenders == {}


def test_the_snapshotting_package_imports_no_engine() -> None:
    """It holds the *shape* of a frozen bundle; the composition root fills it."""
    for module_name in _modules_of("fmis.snapshotting"):
        reached = _imports_of(module_name) & MARKET_HALF_PACKAGES
        assert reached == set(), f"{module_name} imports {sorted(reached)}"


def test_no_domain_package_imports_an_engine() -> None:
    """No engine is imported anywhere in this milestone.

    The data model permits exactly one read-only edge — `fmis.proposal` reading
    `fmis.swing_setup` — and this milestone does not use it: what a proposal cites
    is the *frozen reading* on a snapshot, which the composition root produces.
    Asserting zero edges now means the day one is added is a deliberate change to
    this test rather than an unnoticed import.
    """
    offenders: dict[str, set[str]] = {}
    for package_name in DOMAIN_PACKAGES:
        for module_name in _modules_of(package_name):
            reached = _imports_of(module_name) & MARKET_HALF_PACKAGES
            if reached:
                offenders[module_name] = reached
    assert offenders == {}


def test_the_domain_reaches_the_archive_only_for_the_frozen_encoder() -> None:
    """Reusing `canonical_dumps` is deliberate; reaching the store is not."""
    permitted = {"fmis.archive.json_safe", "fmis.archive.identity"}
    offenders: dict[str, set[str]] = {}
    for package_name in DOMAIN_PACKAGES:
        for module_name in _modules_of(package_name):
            reached = {
                imported
                for imported in _imports_of(module_name)
                if imported.startswith("fmis.archive")
            }
            if reached - permitted:
                offenders[module_name] = reached - permitted
    assert offenders == {}


# --------------------------------------------------------------------------
# The repository's zero-export-collision invariant.
# --------------------------------------------------------------------------


def test_no_public_name_is_exported_by_two_packages() -> None:
    seen: dict[str, str] = {}
    collisions: dict[str, list[str]] = {}
    for module in pkgutil.walk_packages(fmis.__path__, "fmis."):
        if not module.ispkg:
            continue
        package = importlib.import_module(module.name)
        for name in getattr(package, "__all__", []):
            if name in seen and seen[name] != module.name:
                collisions.setdefault(name, [seen[name]]).append(module.name)
            else:
                seen[name] = module.name
    assert collisions == {}


def test_no_submodule_shares_a_name_with_a_public_object() -> None:
    collisions: dict[str, list[str]] = {}
    for package_name in DOMAIN_PACKAGES:
        package = importlib.import_module(package_name)
        submodules = {module.name for module in pkgutil.iter_modules(package.__path__)}
        clash = sorted(submodules & set(getattr(package, "__all__", [])))
        if clash:
            collisions[package_name] = clash
    assert collisions == {}


def test_every_domain_package_declares_what_it_exports() -> None:
    for package_name in DOMAIN_PACKAGES:
        package = importlib.import_module(package_name)
        assert getattr(package, "__all__", None), package_name
        for name in package.__all__:
            assert hasattr(package, name), f"{package_name}.{name}"


def test_every_domain_package_has_a_module_docstring() -> None:
    for package_name in DOMAIN_PACKAGES:
        for module_name in _modules_of(package_name):
            module = importlib.import_module(module_name)
            assert module.__doc__, module_name


# --------------------------------------------------------------------------
# The error hierarchy.
# --------------------------------------------------------------------------


def test_every_domain_error_derives_from_one_catchable_base() -> None:
    from fmis.records import TradeDomainError

    bases = {
        "fmis.accounts": "AccountsError",
        "fmis.money": "MoneyError",
        "fmis.provenance": "ProvenanceError",
        "fmis.versioning": "VersioningError",
        "fmis.analysis_record": "AnalysisRecordError",
        "fmis.snapshotting": "SnapshotError",
        "fmis.proposal": "ProposalError",
        "fmis.ledger": "LedgerError",
        "fmis.positions": "PositionsError",
        "fmis.portfolio": "PortfolioError",
        "fmis.risk": "RiskError",
        "fmis.journal": "JournalError",
    }
    for package_name, error_name in bases.items():
        package = importlib.import_module(package_name)
        error = getattr(package, error_name)
        assert issubclass(error, TradeDomainError), package_name


def test_every_illegal_transition_error_is_both_a_state_error_and_a_package_error() -> None:
    from fmis.ledger import IllegalTradeTransitionError, LedgerError
    from fmis.positions import IllegalPositionTransitionError, PositionsError
    from fmis.proposal import IllegalTransitionError, ProposalError
    from fmis.records import DomainStateError

    for error, package_error in (
        (IllegalTransitionError, ProposalError),
        (IllegalTradeTransitionError, LedgerError),
        (IllegalPositionTransitionError, PositionsError),
    ):
        assert issubclass(error, DomainStateError)
        assert issubclass(error, package_error)


# --------------------------------------------------------------------------
# Law 7 — AI never writes to a source of truth.
# --------------------------------------------------------------------------


def test_a_model_may_author_exactly_one_record_type_in_this_milestone() -> None:
    """`OpportunityProposal` with `author = MODEL` is the only one.

    Every other record this milestone builds has **no field a model could be the
    author of** — which is a stronger guarantee than a rule saying it must not,
    because there is nothing to set.
    """
    from fmis.journal import JournalEntry
    from fmis.ledger import Correction, Trade
    from fmis.portfolio import PortfolioSnapshot
    from fmis.proposal import OpportunityProposal, ProposalAuthor, ProposalLifecycleEvent
    from fmis.risk import RiskBudget
    from fmis.snapshotting import MarketSnapshot

    assert "MODEL" in ProposalAuthor.__members__
    assert "model" in OpportunityProposal.__dataclass_fields__

    for record in (
        Trade,
        Correction,
        JournalEntry,
        RiskBudget,
        MarketSnapshot,
        PortfolioSnapshot,
        ProposalLifecycleEvent,
    ):
        fields = set(record.__dataclass_fields__)
        assert "model" not in fields, record.__name__
        assert "model_id" not in fields, record.__name__


def test_no_lifecycle_event_kind_can_be_authored_by_a_model() -> None:
    """The sharpest instance of Law 7: a model may never record that the owner
    decided something, and may never record a measured market fact."""
    from fmis.proposal import ProposalLifecycleEvent

    fields = set(ProposalLifecycleEvent.__dataclass_fields__)
    assert "author" not in fields
    assert "model" not in fields
    assert "model_id" not in fields


def test_a_trade_carries_no_model_field_under_any_name() -> None:
    from fmis.ledger import Correction, Trade

    for record in (Trade, Correction):
        names = " ".join(record.__dataclass_fields__)
        assert "model" not in names
        assert "ai" not in names.split()


# --------------------------------------------------------------------------
# No invented thresholds.
# --------------------------------------------------------------------------


_NUMERIC_LITERAL = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")


def test_the_risk_package_invents_no_threshold() -> None:
    """The precedent is `ContextPolicy`, the one policy object in the repository
    carrying no numbers. Every risk value is the owner's."""
    source = (SOURCE_ROOT / "risk" / "models.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    }
    assert literals <= {0, 1}, sorted(literals)


def test_the_position_fold_invents_no_threshold() -> None:
    source = (SOURCE_ROOT / "positions" / "fold.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    }
    assert literals <= {0, 1}, sorted(literals)


# --------------------------------------------------------------------------
# No composite score, no resolution verb, no forbidden vocabulary.
# --------------------------------------------------------------------------


FORBIDDEN_SCORE_NAMES = (
    "health_score",
    "risk_score",
    "portfolio_score",
    "composite_score",
    "health_grade",
    "risk_rating",
)


def test_no_domain_package_exports_a_composite_score() -> None:
    for package_name in DOMAIN_PACKAGES:
        package = importlib.import_module(package_name)
        exported = " ".join(package.__all__).lower()
        for forbidden in FORBIDDEN_SCORE_NAMES:
            assert forbidden not in exported, package_name


def test_the_conflict_type_contains_no_verb_of_resolution() -> None:
    """Conflicts are reported and never resolved."""
    from fmis.snapshotting import ConflictNote

    fields = set(ConflictNote.__dataclass_fields__)
    assert fields == {"kind", "statement"}
    assert not fields & {"resolution", "resolved", "winner", "tiebreak", "severity_rank"}


def test_the_proposal_assessment_never_collapses_the_two_cases() -> None:
    from fmis.proposal import DirectionalAssessment

    fields = set(DirectionalAssessment.__dataclass_fields__)
    assert fields == {"long_case", "short_case"}


# --------------------------------------------------------------------------
# Serialization round-trips, in one sweep.
# --------------------------------------------------------------------------


def test_every_serializable_record_round_trips_to_an_equal_value() -> None:
    """One sweep over every record type that has both halves of the codec.

    A type that gains a field and forgets its decoder fails here rather than in
    whichever surface reads it three milestones later.
    """
    from trade_domain_helpers import (
        AT,
        decision_window,
        lifecycle_event,
        market_snapshot,
        proposal,
        trade,
        version_set,
    )

    from fmis.accounts import AccountId, Book
    from fmis.journal import JournalEntry, JournalKind, JournalLink, LinkKind
    from fmis.money import AssetCode, Money
    from fmis.portfolio import (
        CashBalance,
        ExposureSummary,
        FlowSummary,
        Holding,
        MarkQuote,
        PortfolioSnapshot,
    )
    from fmis.proposal import LifecycleKind
    from fmis.provenance import Absent
    from fmis.records import RecordAudit
    from fmis.risk import (
        LimitPeriod,
        LimitScope,
        LimitSeverity,
        LimitUnit,
        RiskBudget,
        RiskLimit,
    )

    usdt = AssetCode("USDT")
    account = AccountId("binance_spot")
    subject = proposal()
    subjects = [
        version_set(),
        market_snapshot(),
        decision_window(),
        subject,
        trade(),
        lifecycle_event(subject, LifecycleKind.ENTRY_TRIGGERED, 11),
        JournalEntry(
            kind=JournalKind.NOTE,
            recorded_at=AT(9),
            author="owner",
            audit=RecordAudit.frozen_at(AT(9)),
            title="a note",
            links=(JournalLink(LinkKind.ABOUT, "market", "binance:BTCUSDT:spot"),),
        ),
        RiskBudget(
            budget_id="swing_budget",
            risk_policy_version=1,
            effective_from=AT(0),
            limits=(
                RiskLimit(
                    "per_trade_risk",
                    LimitScope.PER_TRADE_RISK,
                    Decimal("0.02"),
                    LimitUnit.PERCENT_OF_EQUITY,
                    LimitPeriod.NONE,
                    LimitSeverity.HARD_BLOCK,
                ),
            ),
            audit=RecordAudit.frozen_at(AT(0)),
        ),
        PortfolioSnapshot(
            portfolio_id="main",
            base_currency=usdt,
            as_of=AT(9),
            books_covered=(Book.SWING,),
            holdings=(
                Holding(
                    AssetCode("BTC"),
                    account,
                    __import__("fmis.money", fromlist=["Quantity"]).Quantity(
                        Decimal("1"), AssetCode("BTC")
                    ),
                    MarkQuote(Decimal("60000"), usdt, "binance", AT(8)),
                ),
            ),
            cash=(
                CashBalance(account, Money(Decimal("10"), usdt), Absent("base currency")),
            ),
            flows=FlowSummary(
                Money(Decimal("0"), usdt), Money(Decimal("0"), usdt), Absent("first")
            ),
            exposure=ExposureSummary(
                Money(Decimal("60000"), usdt),
                Money(Decimal("60000"), usdt),
                Money(Decimal("60000"), usdt),
                Money(Decimal("60010"), usdt),
                Money(Decimal("60000"), usdt),
            ),
            allocations=(),
            open_position_event_ids=(),
            version_set=version_set(),
            audit=RecordAudit.frozen_at(AT(9)),
        ),
    ]
    for subject in subjects:
        payload = subject.to_payload()
        restored = type(subject).from_payload(payload)
        assert restored == subject, type(subject).__name__
        assert restored.to_payload() == payload, type(subject).__name__


def test_every_serialized_payload_is_canonically_encodable() -> None:
    """A record that cannot be written to disk is a record that cannot be kept."""
    from fmis.archive.json_safe import canonical_dumps, canonical_loads
    from trade_domain_helpers import decision_window, market_snapshot, proposal, trade

    for subject in (market_snapshot(), decision_window(), proposal(), trade()):
        payload = subject.to_payload()
        assert canonical_loads(canonical_dumps(payload)) == payload


def test_every_domain_record_is_hashable_and_comparable() -> None:
    """Frozen, slotted dataclasses: equality and hashing come for free, and both
    are load-bearing — deduplication, idempotency and set membership all use them."""
    from trade_domain_helpers import (
        decision_window,
        market_snapshot,
        proposal,
        trade,
        version_set,
    )

    for builder in (version_set, market_snapshot, decision_window, proposal, trade):
        left = builder()
        right = builder()
        assert left == right
        assert hash(left) == hash(right)
        assert len({left, right}) == 1


def test_every_domain_record_refuses_attribute_assignment() -> None:
    from trade_domain_helpers import market_snapshot, proposal, trade

    for subject in (market_snapshot(), proposal(), trade()):
        with pytest.raises((AttributeError, TypeError)):
            subject.schema_version = 99  # type: ignore[misc]


def test_every_record_type_pins_the_schema_versions_it_can_read() -> None:
    supported = {
        "fmis.versioning": "SUPPORTED_VERSION_SET_VERSIONS",
        "fmis.analysis_record": "SUPPORTED_ANALYSIS_RECORD_VERSIONS",
        "fmis.snapshotting": "SUPPORTED_MARKET_SNAPSHOT_VERSIONS",
        "fmis.proposal": "SUPPORTED_PROPOSAL_VERSIONS",
        "fmis.ledger": "SUPPORTED_TRADE_VERSIONS",
        "fmis.portfolio": "SUPPORTED_PORTFOLIO_SNAPSHOT_VERSIONS",
        "fmis.risk": "SUPPORTED_RISK_BUDGET_VERSIONS",
        "fmis.journal": "SUPPORTED_JOURNAL_ENTRY_VERSIONS",
    }
    for package_name, constant in supported.items():
        package = importlib.import_module(package_name)
        versions = getattr(package, constant)
        assert isinstance(versions, frozenset)
        assert versions == frozenset({1})


def test_every_record_type_slug_is_unique_across_the_domain() -> None:
    from fmis.journal import JOURNAL_ENTRY_TYPE_SLUG
    from fmis.ledger import CORRECTION_TYPE_SLUG, TRADE_TYPE_SLUG
    from fmis.portfolio import PORTFOLIO_SNAPSHOT_TYPE_SLUG
    from fmis.proposal import LIFECYCLE_EVENT_TYPE_SLUG, PROPOSAL_TYPE_SLUG
    from fmis.risk import RISK_BUDGET_TYPE_SLUG
    from fmis.snapshotting import DECISION_WINDOW_TYPE_SLUG, MARKET_SNAPSHOT_TYPE_SLUG

    slugs = [
        JOURNAL_ENTRY_TYPE_SLUG,
        CORRECTION_TYPE_SLUG,
        TRADE_TYPE_SLUG,
        PORTFOLIO_SNAPSHOT_TYPE_SLUG,
        LIFECYCLE_EVENT_TYPE_SLUG,
        PROPOSAL_TYPE_SLUG,
        RISK_BUDGET_TYPE_SLUG,
        DECISION_WINDOW_TYPE_SLUG,
        MARKET_SNAPSHOT_TYPE_SLUG,
    ]
    assert len(set(slugs)) == len(slugs)


# --------------------------------------------------------------------------
# Determinism: no clock, no randomness inside the domain.
# --------------------------------------------------------------------------


def test_no_domain_module_reads_a_clock_or_a_random_source() -> None:
    """Every instant in this domain is supplied by the caller.

    A record that stamped itself with `now()` would produce a different digest on
    every construction, and a content-derived id would stop being content-derived.
    """
    forbidden = ("datetime.now(", "datetime.utcnow(", "time.time(", "random.")
    offenders: dict[str, list[str]] = {}
    for package_name in DOMAIN_PACKAGES:
        for module_name in _modules_of(package_name):
            module = importlib.import_module(module_name)
            source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
            hits = [needle for needle in forbidden if needle in source]
            if hits:
                offenders[module_name] = hits
    assert offenders == {}


def test_building_the_same_record_twice_produces_the_same_bytes() -> None:
    from fmis.archive.json_safe import canonical_dumps
    from trade_domain_helpers import market_snapshot, proposal, trade

    for builder in (market_snapshot, proposal, trade):
        assert canonical_dumps(builder().to_payload()) == canonical_dumps(
            builder().to_payload()
        )


def test_the_canonical_amount_form_is_independent_of_the_ambient_context() -> None:
    """A caller who set their own decimal precision cannot change a digest."""
    import decimal

    from fmis.money import canonical_decimal_text

    original = decimal.getcontext().prec
    try:
        decimal.getcontext().prec = 6
        assert canonical_decimal_text(Decimal("1.234567890123456789")) == (
            "1.234567890123456789"
        )
    finally:
        decimal.getcontext().prec = original


def test_no_domain_module_holds_module_level_mutable_state() -> None:
    """A cache would make a fold's answer depend on what was folded before it."""
    for package_name in DOMAIN_PACKAGES:
        for module_name in _modules_of(package_name):
            module = importlib.import_module(module_name)
            for name, value in vars(module).items():
                if name.startswith("__") or inspect.isclass(value):
                    continue
                assert not isinstance(value, (list, set)), f"{module_name}.{name}"
                if isinstance(value, dict):
                    assert name.startswith("_") or name.isupper(), (
                        f"{module_name}.{name}"
                    )
