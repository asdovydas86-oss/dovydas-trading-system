"""Boundary guards for `fmis.plan` and `fmis.trade_capture`.

These do not exercise behaviour. They assert the rules the milestone rests on, in
the only form that survives a refactor: an executable check over the source tree.

Two of them are the whole reason this milestone is safe to build on. **Nothing
below the composition root reaches disk**, and **nothing writes except through
`TradingStore`** — the second is what keeps the store's hash-chained write journal
a *complete* account of the store rather than a mostly complete one.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path

import pytest

import fmis

PLAN = "fmis.plan"
CAPTURE = "fmis.trade_capture"
SOURCE_ROOT = Path(fmis.__file__).parent

#: Every package that reads a candle. Copied deliberately rather than imported,
#: so adding one is a visible edit in each guard that cares.
MARKET_HALF = frozenset(
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
        "fmis.trading_context",
    }
)


def _modules_of(package_name: str) -> list[str]:
    package = importlib.import_module(package_name)
    return [package_name] + [
        module.name
        for module in pkgutil.iter_modules(package.__path__, prefix=f"{package_name}.")
    ]


def _source_of(module_name: str) -> str:
    return Path(inspect.getfile(importlib.import_module(module_name))).read_text(
        encoding="utf-8"
    )


def _imports_of(module_name: str) -> set[str]:
    tree = ast.parse(_source_of(module_name))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _names_used(module_name: str) -> set[str]:
    """Identifiers and attribute names, so a guard can look for a *call*."""
    tree = ast.parse(_source_of(module_name))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
    return found


# --------------------------------------------------------------------------
# `fmis.plan` is a domain package and stays pure.
# --------------------------------------------------------------------------


def test_the_plan_package_holds_no_path_no_file_and_no_clock() -> None:
    """A record that stamped itself would stop being content-derived."""
    forbidden = (
        "datetime.now(",
        "datetime.utcnow(",
        "time.time(",
        "random.",
        "open(",
        "Path(",
    )
    offenders: dict[str, list[str]] = {}
    for module_name in _modules_of(PLAN):
        source = _source_of(module_name)
        hits = [needle for needle in forbidden if needle in source]
        if hits:
            offenders[module_name] = hits
    assert offenders == {}


def test_the_plan_package_never_imports_the_store() -> None:
    """The direction is one-way: the day it reverses, a `TradePlan` cannot be
    constructed without a store to put it in."""
    for module_name in _modules_of(PLAN):
        reached = {
            name for name in _imports_of(module_name) if name.startswith("fmis.persistence")
        }
        assert reached == set(), f"{module_name} imports {sorted(reached)}"


def test_the_plan_package_never_imports_an_engine() -> None:
    for module_name in _modules_of(PLAN):
        reached = _imports_of(module_name) & MARKET_HALF
        assert reached == set(), f"{module_name} imports {sorted(reached)}"


def test_the_plan_package_never_imports_the_ledger() -> None:
    """A plan is valid with no fill against it, and must describe itself alone.

    §9.1: *"an unproposed, unexecuted plan is equally valid."* A package that
    needed the ledger to say what a plan is would have quietly made that false.
    """
    for module_name in _modules_of(PLAN):
        assert "fmis.ledger" not in _imports_of(module_name), module_name


def test_the_plan_package_reaches_the_archive_only_for_the_frozen_encoder() -> None:
    permitted = {"fmis.archive.json_safe", "fmis.archive.identity"}
    for module_name in _modules_of(PLAN):
        reached = {
            name for name in _imports_of(module_name) if name.startswith("fmis.archive")
        }
        assert reached <= permitted, f"{module_name} reaches {sorted(reached - permitted)}"


def test_the_plan_package_invents_no_threshold() -> None:
    """Every number in a plan is the owner's. The precedent is `fmis.risk`."""
    for module_name in _modules_of(PLAN):
        literals = {
            node.value
            for node in ast.walk(ast.parse(_source_of(module_name)))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        }
        assert literals <= {0, 1}, f"{module_name}: {sorted(literals)}"


def test_the_plan_package_holds_no_float_literal_anywhere() -> None:
    """One float in a price path is a fifty-five-digit digest away from a bug."""
    for module_name in _modules_of(PLAN):
        floats = {
            node.value
            for node in ast.walk(ast.parse(_source_of(module_name)))
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        }
        assert floats == set(), module_name


def test_no_capital_at_risk_figure_is_ever_a_stored_field() -> None:
    from fmis.plan import TradePlan

    fields = set(TradePlan.__dataclass_fields__)
    assert not fields & {"capital_at_risk", "intended_risk", "risk_reward"}


# --------------------------------------------------------------------------
# `fmis.trade_capture` is the composition root, and the only writer.
# --------------------------------------------------------------------------


def test_the_capture_package_reaches_both_the_domain_and_the_store() -> None:
    """That crossing is the point of this package, and it is one package wide."""
    reached: set[str] = set()
    for module_name in _modules_of(CAPTURE):
        reached |= _imports_of(module_name)
    assert any(name.startswith("fmis.persistence") for name in reached)
    assert any(name.startswith("fmis.plan") for name in reached)
    assert any(name.startswith("fmis.ledger") for name in reached)


def test_the_capture_package_imports_no_engine() -> None:
    """A record of what the owner did must never be a function of the analysis."""
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(CAPTURE):
        reached = _imports_of(module_name) & MARKET_HALF
        if reached:
            offenders[module_name] = reached
    assert offenders == {}


def test_no_module_here_reaches_disk_except_through_the_store() -> None:
    """The one write path, asserted. A record that reached disk without a journal
    event would have to have been written by code that does not exist."""
    forbidden = {"atomic_write", "append_lines", "write_text", "write_bytes", "mkdir"}
    offenders: dict[str, set[str]] = {}
    for module_name in _modules_of(CAPTURE):
        hits = _names_used(module_name) & forbidden
        if hits:
            offenders[module_name] = hits
    assert offenders == {}


def test_no_module_here_reads_a_clock() -> None:
    """`fmis.pipeline.cli` is the only place in this repository that takes the time."""
    forbidden = ("datetime.now(", "datetime.utcnow(", "time.time(", "random.")
    offenders: dict[str, list[str]] = {}
    for module_name in _modules_of(CAPTURE):
        source = _source_of(module_name)
        hits = [needle for needle in forbidden if needle in source]
        if hits:
            offenders[module_name] = hits
    assert offenders == {}


def test_the_read_module_writes_nothing() -> None:
    """A `trade show` that repaired something would make the store's contents
    depend on who looked at them."""
    forbidden = {"publish", "revise", "admit", "append_event", "rebuild_index"}
    used = _names_used(f"{CAPTURE}.views")
    assert used & forbidden == set()
    assert "create" not in used


def test_the_renderer_only_renders() -> None:
    """It computes nothing, decides nothing and reaches nothing."""
    reached = _imports_of(f"{CAPTURE}.render")
    assert not any(name.startswith("fmis.persistence") for name in reached)
    assert f"{CAPTURE}.capture" not in reached
    used = _names_used(f"{CAPTURE}.render")
    assert used & {"record_trade", "close_trade", "append_note", "load_trade"} == set()


def test_the_capture_package_declares_what_it_exports() -> None:
    for package_name in (PLAN, CAPTURE):
        package = importlib.import_module(package_name)
        assert getattr(package, "__all__", None), package_name
        for name in package.__all__:
            assert hasattr(package, name), f"{package_name}.{name}"


def test_every_module_in_both_packages_has_a_docstring() -> None:
    for package_name in (PLAN, CAPTURE):
        for module_name in _modules_of(package_name):
            assert importlib.import_module(module_name).__doc__, module_name


def test_neither_package_exports_a_composite_score() -> None:
    for package_name in (PLAN, CAPTURE):
        exported = " ".join(importlib.import_module(package_name).__all__).lower()
        for forbidden in ("score", "grade", "rating", "health", "rank"):
            assert forbidden not in exported, package_name


def test_no_public_name_is_exported_by_two_packages() -> None:
    """The repository's zero-collision invariant, re-asserted after two new packages."""
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


def test_the_capture_package_invents_no_trading_threshold() -> None:
    """The dust policy is exact zero and every limit is the owner's."""
    for module_name in _modules_of(CAPTURE):
        floats = {
            node.value
            for node in ast.walk(ast.parse(_source_of(module_name)))
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        }
        assert floats == set(), module_name


def test_the_dust_policy_configures_no_threshold() -> None:
    """Zero is the only tolerance that is not a policy decision."""
    from fmis.trade_capture import CAPTURE_DUST_POLICY

    assert CAPTURE_DUST_POLICY.thresholds == ()


def test_this_package_defines_no_member_of_an_owner_vocabulary() -> None:
    """Setup types and exit reasons are the owner's words, carried through verbatim."""
    from fmis.trade_capture import (
        EXIT_REASON_VOCABULARY,
        SETUP_TYPE_VOCABULARY,
        WRITE_REASON_VOCABULARY,
    )

    source = _source_of(f"{CAPTURE}.capture")
    assert f'"{SETUP_TYPE_VOCABULARY}"' in source
    assert f'"{EXIT_REASON_VOCABULARY}"' in source
    # The only vocabulary this package mints terms in is its own write-reason set,
    # which describes why the *store* wrote, not what the owner thinks of a trade.
    from fmis.trade_capture import CLOSE_REASON, NOTE_REASON, RECORD_REASON

    for term in (RECORD_REASON, CLOSE_REASON, NOTE_REASON):
        assert term.vocabulary_id == WRITE_REASON_VOCABULARY


# --------------------------------------------------------------------------
# The CLI stays thin.
# --------------------------------------------------------------------------


def test_the_cli_reaches_neither_the_domain_nor_the_store() -> None:
    """Milestone BJ's rule, kept: `fmis.pipeline` is a market-half package.

    Every conversion the capture commands need lives in
    `fmis.trade_capture.inputs`, where it can be tested without a parser.
    """
    permitted_prefixes = (
        "fmis.pipeline",
        "fmis.trade_capture",
        "fmis.today",
        "fmis.workspace",
        "fmis.daily",
        "fmis.archive",
        "fmis.swing_setup",
        "fmis.market_regime",
        "fmis.market_structure",
        "fmis.providers",
        # Widened for Milestone BM. `fmis.valuation` is an application-layer
        # package at the same tier as `fmis.today`, which this list already
        # admits for the identical reason: the CLI is the outermost edge and
        # composes rather than computes. The rule this guard actually protects —
        # that `fmis.pipeline` never reaches `fmis.persistence` — is unaffected
        # and is asserted directly by the test below and by
        # `test_today_architecture.test_the_cli_does_not_import_the_store_directly`.
        "fmis.valuation",
        # Widened for Milestone BN, on the identical footing. `fmis.position_sizing`
        # is an application-layer package at the same tier as `fmis.today` and
        # `fmis.valuation`, and its own text boundary — `position_sizing.inputs`
        # — exists for exactly the reason this guard does: so the CLI parses no
        # price, constructs no `AccountId` and opens no `TradingStore` for
        # `fmits approve`. The two assertions below are unaffected and still
        # prove the store is never reached from here.
        "fmis.position_sizing",
        # Widened for Milestone BO, on the identical footing again.
        # `fmis.paper` is an application-layer package at the same tier as
        # `fmis.today`, `fmis.valuation` and `fmis.position_sizing`, and its own
        # text boundary — `paper.inputs` — exists for exactly the reason this
        # guard does: so the CLI parses no price, builds no `AccountId` and
        # opens no `TradingStore` for `fmits simulate` or for the six new
        # `fmits trade` subcommands. The two assertions below are unaffected and
        # still prove the store is never reached from here.
        "fmis.paper",
        # Widened for Milestone BP, on the identical footing once more.
        # `fmis.statistics` is an application-layer package at the same tier as
        # the four above, and its own text boundary — `statistics.inputs` —
        # exists for exactly the reason this guard does. It is worth recording
        # that the first draft of `fmits statistics` also reached for
        # `fmis.provenance` to build an `Absent` for "no cut requested"; that
        # was this guard doing its job, and the fix was to move the three
        # absences into `statistics.inputs` where every other conversion lives,
        # not to admit a second prefix. The two assertions below are unaffected
        # and still prove the store is never reached from here.
        "fmis.statistics",
        # Widened for Milestone BW, on the identical footing again.
        # `fmis.swing_lab` is the Swing Strategy Laboratory: an
        # application-layer package at the same tier as the six above, reached
        # only by `fmits research` and by `fmits dashboard --lab-artifact`. It
        # is worth recording exactly what this widening does NOT admit. The
        # laboratory's own guard asserts that no engine imports it, so the
        # dependency runs one way only; it opens a file in exactly one module,
        # and that file is a research artifact rather than the trading store;
        # and the CLI decodes that artifact HERE precisely so
        # `fmis.operator_dashboard` can keep its own stronger guarantee of
        # opening nothing at all. The two assertions below are unaffected and
        # still prove the store is never reached from here.
        "fmis.swing_lab",
        # Widened for the BG-D1 surface slice, on the identical footing again.
        # `fmis.setup_observation` is an application-layer package at the same
        # tier as the five above: it is the only place a `SetupAssessment`
        # becomes a `SetupObservation`, and it owns both the conversion and the
        # rendering of the identity block `fmits setup` appends. The CLI names
        # no domain root for it — the one domain value it needs, a `MarketId`,
        # comes from `market_from_symbol` in the already-permitted
        # `fmis.trade_capture`, which is the same discipline the note above
        # records for `fmis.provenance`. Nothing is persisted: the two types the
        # package produces are rebuildable projections the store refuses, and
        # the two assertions below are unaffected and still prove the store is
        # never reached from here.
        "fmis.setup_observation",
        # Widened for Milestone BR, on the identical footing again.
        # `fmis.setup_evidence` is an application-layer package at the same tier
        # as the six above: it projects a `SetupAssessment` the CLI already has
        # into the evidence page `fmits evidence` prints, and computes nothing.
        # It is worth recording that the first draft of `fmits evidence` also
        # reached for `fmis.proposal` — to stamp the setup vocabulary id and
        # identity version onto `SetupIdentityRef` — and that this guard caught
        # it. The fix was to drop the two fields, not to admit a domain root:
        # the identity *string* the page shows comes from the already-permitted
        # `fmis.setup_observation`, and the vocabulary provenance is printed by
        # `fmits setup`, which is the surface that owns it. Nothing is
        # persisted, and the two assertions below are unaffected and still prove
        # the store is never reached from here.
        "fmis.setup_evidence",
        # Widened for Milestone BS, on the identical footing again.
        # `fmis.swing_workspace` is an application-layer package at the same tier
        # as the seven above: it arranges the page `fmits workspace` prints from
        # the run `fmis.today` already assembled, and computes nothing. It is the
        # *second* package to read both halves of FMITS, and it reaches the store
        # exactly as the first one does — through `fmis.today`, never directly —
        # so the two assertions below are unaffected and still prove the store is
        # never reached from here. Nothing is persisted: every type the package
        # produces is a rebuildable projection the store refuses.
        "fmis.swing_workspace",
        # Widened for Milestone BT, on the identical footing again — and this one
        # crosses *less* than any of the eight above. `fmis.market_pulse` is a
        # market-half package: it reads no store, imports no domain root, names
        # no provider and holds no owner state, so the rule this guard actually
        # protects — that `fmis.pipeline` never reaches `fmis.persistence` — is
        # not merely unaffected but unreachable from here. What the CLI does with
        # it is parse benchmark ids, resolve a universe subset and print; the
        # provider terminates in `fmis.pipeline.pulse`, exactly as it terminates
        # in `fmis.pipeline.prices` for a mark.
        #
        # It is worth recording what this guard did *not* have to be widened for.
        # `fmis.market_pulse.universe` documents that its provider label matches
        # the fact-sheet root's, and the first draft named that module by path in
        # a docstring — which tripped `test_structural_facts.py`'s raw-text scan.
        # The fix was to name it in prose, not to widen that guard, following the
        # note `fmis.pipeline.prices` already carries for the same situation.
        "fmis.market_pulse",
        # Widened for Milestone BU, on the same footing as BT and for a package
        # that crosses no further. `fmis.macro` is a market-half package too: it
        # reads no store, imports no domain root, names no provider and holds no
        # owner state, so the rule this guard protects — that `fmis.pipeline`
        # never reaches `fmis.persistence` — remains unreachable from here. What
        # the CLI does with it is render a report it was handed; both providers
        # terminate in `fmis.pipeline.market_data`.
        "fmis.macro",
        # Widened for Milestone BV, on the same footing as BS.
        # `fmis.operator_dashboard` is an application-layer package at the same
        # tier as the ones above: it composes the pages the dashboard serves
        # from `fmis.swing_workspace`, `fmis.market_pulse`, `fmis.macro` and
        # `fmis.statistics`, and computes nothing of its own. It reaches the
        # store exactly as `fmis.today` and `fmis.swing_workspace` do — through
        # them, never directly — so the two assertions below are unaffected and
        # still prove the store is never reached from here.
        #
        # It crosses *less* than the packages above in one respect worth
        # recording: it is strictly read-only, and its own guards assert the
        # absence of every store write verb, every raw filesystem write verb and
        # every execution verb across the whole package. What the CLI does with
        # it is bind a socket and hand it a snapshot holder.
        "fmis.operator_dashboard",
    )
    reached = {
        name
        for name in _imports_of("fmis.pipeline.cli")
        if name.startswith("fmis.") and not name.startswith(permitted_prefixes)
    }
    assert reached == set()


def test_the_cli_opens_no_store_of_its_own() -> None:
    used = _names_used("fmis.pipeline.cli")
    assert "TradingStore" not in used
    assert "default_store_root" not in used


def test_the_trade_command_is_registered_with_a_runner() -> None:
    from fmis.pipeline.cli import COMMANDS

    command = next(entry for entry in COMMANDS if entry.name == "trade")
    assert callable(command.configure)
    assert callable(command.run)


@pytest.mark.parametrize(
    "phrase",
    [
        "places no order",
        "executes nothing",
        "the owner remains the trader",
    ],
)
def test_the_trade_command_states_what_it_does_not_do(phrase: str) -> None:
    from fmis.pipeline.cli import COMMANDS

    command = next(entry for entry in COMMANDS if entry.name == "trade")
    assert phrase in command.description
