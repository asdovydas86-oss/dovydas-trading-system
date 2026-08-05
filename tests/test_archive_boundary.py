"""Import-direction guard: `fmis.archive` is consumed, never a consumer.

Mirrors `tests/test_pipeline_market_analysis.py`'s
`test_no_engine_imports_the_application_layer` exactly (design doc §3.5):
`fmis.archive` sits above `fmis.workspace`/`fmis.daily`, consuming their
finished models, so nothing below it — including every engine, `workspace`,
`daily`, and every `fmis.pipeline` module except `cli.py`, the CLI edge that
composes the archive's command surface — may import it.
"""

from __future__ import annotations

from pathlib import Path

import fmis.archive as archive_module

SRC = Path(archive_module.__file__).resolve().parent.parent

#: Every package that must never depend on `fmis.archive`. `pipeline` is
#: scanned file-by-file below rather than listed here, so `cli.py` — the one
#: permitted importer — can be excluded precisely instead of exempting the
#: whole package.
FORBIDDEN_PACKAGES = (
    "data", "ingest", "providers", "features", "alignment", "relative_value",
    "market_structure", "structural_trend", "series_context", "level_crossing",
    "structure_break", "change_of_character", "evidence", "decision_support",
    "trading_context", "decision_context", "market_regime",
    "workspace", "daily",
)


def test_no_forbidden_package_imports_archive() -> None:
    offenders: list[str] = []
    for package in FORBIDDEN_PACKAGES:
        for py in (SRC / package).rglob("*.py"):
            if "fmis.archive" in py.read_text():
                offenders.append(str(py))
    assert offenders == []


def test_forbidden_packages_actually_exist() -> None:
    # Guards the test above from silently passing if a package is renamed.
    for package in FORBIDDEN_PACKAGES:
        assert (SRC / package / "__init__.py").is_file(), package


def test_no_pipeline_module_except_cli_imports_archive() -> None:
    pipeline_dir = SRC / "pipeline"
    offenders: list[str] = []
    for py in pipeline_dir.glob("*.py"):
        if py.name == "cli.py":
            continue
        if "fmis.archive" in py.read_text():
            offenders.append(str(py))
    assert offenders == []


def test_the_cli_does_import_archive() -> None:
    # The one intended edge: proves the exclusion above is precise, not vacuous.
    cli_text = (SRC / "pipeline" / "cli.py").read_text()
    assert "fmis.archive" in cli_text


def test_archive_imports_no_provider() -> None:
    for py in (SRC / "archive").rglob("*.py"):
        assert "fmis.providers" not in py.read_text(), py


def test_archive_imports_only_the_standard_library_and_its_own_dependencies() -> None:
    import ast

    allowed_fmis_roots = {"fmis.archive", "fmis.workspace", "fmis.daily"}
    for py in (SRC / "archive").rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("fmis"):
                assert any(node.module.startswith(root) for root in allowed_fmis_roots), (
                    py,
                    node.module,
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("fmis"):
                        assert any(alias.name.startswith(root) for root in allowed_fmis_roots), (
                            py,
                            alias.name,
                        )


def test_importing_archive_does_not_load_the_cli(fresh_fmis_imports: None) -> None:
    import sys

    import fmis.archive  # noqa: F401

    # `fmis.archive` reaches `fmis.workspace`/`fmis.daily`, which themselves
    # compose several `fmis.pipeline` submodules (multi_timeframe,
    # structural_facts, market_analysis) — expected, and not what this test
    # guards. Only `fmis.pipeline.cli`, the one permitted importer of
    # `fmis.archive` (§ test_the_cli_does_import_archive above), must never
    # load as a side effect of importing archive itself — that would be a
    # cycle back to the boundary this package sits below.
    assert "fmis.pipeline.cli" not in sys.modules
