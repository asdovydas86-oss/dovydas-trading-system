"""The repository's import tiers, declared **once**, as a partition.

**Why this module exists.** Milestone CD first tried to guard the research
boundary with tests that derived their own exemption set from the allowlist they
were checking. An independent reviewer defeated that in two lines: adding a
package to the allowlist simultaneously removed it from the guarantee, and the
companion check — that a guard file with the right *name* existed — was satisfied
by an empty file. The demonstration is preserved as an executable regression in
`tests/test_architecture_tiers.py`.

The lesson is not "patch the demonstrated example". It is that four separate
guards were each restating the same invariant in their own terms, and a set that a
test both consults and is checked against can never constrain anything.

**The invariant, stated once.**

> Every package under `src/fmis` is either PRODUCTION or RESEARCH. Production may
> not import research. Research may import research. The only module outside the
> research tier permitted to import into it is the CLI, which is a research
> *surface*.

**What makes it non-circular.** The two sets are a **partition**: their union is
asserted to equal the packages that actually exist on disk, and their intersection
is asserted empty. A new package is therefore not admitted by silence — it must be
classified, and each classification carries a consequence:

* classified PRODUCTION, it may not import research, and the boundary guards fire;
* classified RESEARCH, it must carry an architecture guard of its own that really
  guards — named boundary test, names its own package, walks the source tree, and
  holds real assertions;
* left unclassified, `assert_tier_partition_is_complete` fails.

So the cheapest bypass is no longer an allowlist edit. It is a deliberate,
reviewable reclassification with a test obligation attached, which is what the
guard was always supposed to require.

**These are test fixtures, not production code.** Nothing under `src/` imports
this module, and nothing here is used at run time.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

__all__ = [
    "RESEARCH_PACKAGES",
    "PRODUCTION_PACKAGES",
    "RESEARCH_SURFACE",
    "source_root",
    "packages_under",
    "importers_of",
    "assert_tier_partition_is_complete",
    "guard_file_is_real",
]

#: The research tier. A package here computes, measures or seals a research
#: question and is reachable from the CLI alone. Every member must carry its own
#: `tests/test_<package>_architecture.py`, and `guard_file_is_real` says what
#: "carry" means.
RESEARCH_PACKAGES: frozenset[str] = frozenset(
    {
        "swing_lab",
        "research_design",
        "universe",
        "paired_dependence",
    }
)

#: Everything else: the trading system. Domain, engines, repositories, surfaces.
#: **Not** derived by subtraction — written out, so adding a package to the
#: repository forces a decision rather than defaulting into an exemption.
PRODUCTION_PACKAGES: frozenset[str] = frozenset(
    {
        "accounts", "alignment", "analysis_record", "archive",
        "change_of_character", "daily", "data", "decision_context",
        "decision_support", "evidence", "features", "ingest", "journal",
        "ledger", "level_crossing", "macro", "market_pulse", "market_regime",
        "market_structure", "marks", "money", "operator_dashboard", "paper",
        "persistence", "pipeline", "plan", "portfolio", "portfolio_risk",
        "position_sizing", "positions", "proposal", "provenance", "providers",
        "records", "relative_value", "risk", "risk_policy", "scan_memory",
        "series_context",
        "setup_evidence",
        "setup_observation", "snapshotting", "statistics", "structural_trend",
        "structure_break", "swing_setup", "swing_workspace", "today",
        "trade_capture", "trade_lifecycle", "trading_context", "valuation",
        "versioning", "workspace",
    }
)

#: The one module outside the research tier that may import into it. The CLI is
#: the outermost edge: it composes and prints, and computes nothing.
RESEARCH_SURFACE: frozenset[str] = frozenset({"pipeline/cli.py"})


def source_root() -> Path:
    """`src/fmis`, from this file's own location."""
    return Path(__file__).resolve().parents[1] / "src" / "fmis"


def packages_under(root: Path) -> set[str]:
    """Every package directory that actually exists, ignoring bytecode caches."""
    return {
        path.name
        for path in root.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }


def assert_tier_partition_is_complete(root: Path | None = None) -> None:
    """Every package is classified exactly once. **The non-circular part.**

    Raises:
        AssertionError: a package on disk is in neither tier, a classified
            package does not exist, or a package is in both.
    """
    where = source_root() if root is None else root
    found = packages_under(where)
    classified = RESEARCH_PACKAGES | PRODUCTION_PACKAGES

    overlap = RESEARCH_PACKAGES & PRODUCTION_PACKAGES
    assert not overlap, (
        f"{sorted(overlap)} are declared both research and production; a package "
        "cannot be exempt from a boundary it also defines"
    )
    unclassified = found - classified
    assert not unclassified, (
        f"{sorted(unclassified)} exist under {where} but are in neither "
        "RESEARCH_PACKAGES nor PRODUCTION_PACKAGES. A new package must be "
        "classified deliberately: silence is not a classification, and an "
        "unclassified package would be exempt from every import boundary in this "
        "repository"
    )
    missing = classified - found
    assert not missing, (
        f"{sorted(missing)} are classified but do not exist under {where}; a "
        "stale entry can silently cover a package added later under the same name"
    )


def importers_of(
    package: str, root: Path | None = None, *, exclude: Iterable[str] = ()
) -> set[str]:
    """Every module that imports ``fmis.<package>``, as repo-relative paths.

    Parsed as an **import**, not matched as a substring: a docstring naming a
    package is documentation and is welcome; an `import` is a dependency and is
    not. ``exclude`` names top-level package directories to skip.
    """
    where = source_root() if root is None else root
    skipped = set(exclude)
    found: set[str] = set()
    for path in sorted(where.rglob("*.py")):
        relative = str(path.relative_to(where)).replace("\\", "/")
        if relative.split("/")[0] in skipped:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(item == f"fmis.{package}" or item.startswith(f"fmis.{package}.")
                   for item in names):
                found.add(relative)
    return found


def guard_file_is_real(package: str, guards: Path | None = None) -> None:
    """A research package's architecture guard must guard, not merely exist.

    A file with the right *name* and no content satisfied the first version of
    this check, and a reviewer proved it. The file must now declare a named
    boundary test, name its own package, walk the source tree, and hold real
    assertions.

    Raises:
        AssertionError: the file is absent or is a placeholder.
    """
    where = (Path(__file__).resolve().parent if guards is None else guards)
    path = where / f"test_{package}_architecture.py"
    assert path.exists(), (
        f"{package} is in the research tier but declares no "
        f"test_{package}_architecture.py of its own"
    )
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    named = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    boundary = {
        name
        for name in named
        if "import" in name
        and any(word in name for word in ("production", "unreachable", "only_the_cli"))
    }
    assert boundary, (
        f"test_{package}_architecture.py declares no test asserting who may "
        f"import fmis.{package}; it exists but guards nothing. Its tests are "
        f"{sorted(named)}"
    )
    assert f"fmis.{package}" in source, (
        f"test_{package}_architecture.py never names fmis.{package}"
    )
    assert "rglob" in source or "importers_of" in source, (
        f"test_{package}_architecture.py names a boundary test but never scans "
        "the source tree, so it cannot know who imports what"
    )
    asserts = sum(1 for node in ast.walk(tree) if isinstance(node, ast.Assert))
    assert asserts >= 10, (
        f"test_{package}_architecture.py holds only {asserts} assertion(s); a "
        "file with the right name is not a guard"
    )
