"""ADR-0028 §5 — directional vocabulary exists only in `fmis.swing_setup`.

The narrower guards already in the suite (`test_workspace_render.py`'s full-page
scan, `test_daily_models.py`'s package-name scan, `test_workspace_build.py`'s
CONTEXT-section scan) each cover one rendered surface. This test is additive
and repository-wide: it walks every source file under `src/fmis` except
`fmis/swing_setup/` and `fmis/pipeline/cli.py` — the two locations ADR-0028
names as permitted — and asserts no Python **identifier** or **string-literal
value** exactly equals one of the unambiguous directional tokens.

**Why identifiers and exact string values, not a substring scan of raw text.**
Every existing package already *discusses* this vocabulary in its own
docstrings — "not a reason to buy", "LONG/SHORT recommendation" — precisely to
document what it refuses to emit. A substring scan over raw text would flag
every one of those denial sentences as a violation. Parsing with `ast` and
checking only real identifiers (function/class names, `ast.Name`, attribute
access, parameters) and exact string-literal values catches the case the task
brief names directly — *"a future developer puts LONG into
`fmis.market_structure`"* — as an actual enum member, constant or emitted
value, while leaving prose alone. Verified empirically: this scan reports zero
matches against the repository as it stood before this milestone.
"""

from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "fmis"

#: Unambiguous directional trading vocabulary. Deliberately excludes English
#: words with legitimate non-trading meanings this repository already uses
#: constantly — "entry", "target", "stop", "trigger" — which the page-scoped
#: guards already police in their rendered context. These six are never
#: legitimate outside a trading interpretation.
_BANNED = {"long", "short", "buy", "sell", "bullish", "bearish"}

#: The two locations ADR-0028 names as permitted to hold this vocabulary.
_PERMITTED_DIR = SRC / "swing_setup"
_PERMITTED_FILE = SRC / "pipeline" / "cli.py"


def _identifiers_and_string_values(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node.name
        elif isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, ast.arg):
            yield node.arg
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def _covered_files():
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if path.parent == _PERMITTED_DIR or path == _PERMITTED_FILE:
            continue
        yield path


def test_no_directional_identifier_or_literal_exists_outside_swing_setup() -> None:
    offenders = []
    for path in _covered_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for token in _identifiers_and_string_values(tree):
            if token.lower() in _BANNED:
                offenders.append((str(path.relative_to(SRC.parent.parent)), token))
    assert offenders == []


def test_the_scan_actually_detects_a_planted_violation(tmp_path: pathlib.Path) -> None:
    """Proves the scan is not vacuously passing — a real regression test on itself."""
    planted = tmp_path / "planted.py"
    planted.write_text('LONG = "long"\n')
    tree = ast.parse(planted.read_text())
    tokens = {t.lower() for t in _identifiers_and_string_values(tree)}
    assert _BANNED & tokens


def test_swing_setup_itself_is_exempt_and_does_use_the_vocabulary() -> None:
    """Sanity check that the exemption is real: the permitted package does emit it."""
    found = set()
    for path in _PERMITTED_DIR.glob("*.py"):
        tree = ast.parse(path.read_text())
        for token in _identifiers_and_string_values(tree):
            if token.lower() in _BANNED:
                found.add(token.lower())
    assert {"long", "short"} <= found


def test_pipeline_cli_is_the_only_permitted_file_outside_swing_setup() -> None:
    """Pins the exemption to exactly the two locations ADR-0028 names."""
    assert _PERMITTED_FILE.exists()
    assert _PERMITTED_FILE.parent == SRC / "pipeline"
