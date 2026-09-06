"""What `fmis.risk_policy` may not do, asserted over its own source.

Five boundaries, each of which would be invisible in a passing feature test:

1. **Risk is not confidence.** No evidence count, probability, family, state or
   direction reaches a value here.
2. **The package computes no money arithmetic.** Every quotient is
   `fmis.position_sizing`'s and `fmis.portfolio_risk`'s.
3. **One number, and it is the specification's.** `2 %` appears once.
4. **Nothing executes, and nothing writes.**
5. **The dependency direction holds.** Nothing below imports this package, and
   this package imports no surface.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pathlib
import pkgutil

import pytest

import fmis.risk_policy

PACKAGE = "fmis.risk_policy"

#: The application-layer packages this one may compose. Written out one by one:
#: a package appearing here later is a deliberate act with a justification.
PERMITTED = (
    "fmis.accounts",
    "fmis.money",
    "fmis.position_sizing",
    "fmis.provenance",
    "fmis.records",
    "fmis.risk",
    "fmis.risk_policy",
)


def _modules() -> list[str]:
    return [PACKAGE] + [
        module.name
        for module in pkgutil.iter_modules(
            fmis.risk_policy.__path__, prefix=f"{PACKAGE}."
        )
    ]


def _source(module_name: str) -> str:
    module = importlib.import_module(module_name)
    return pathlib.Path(inspect.getfile(module)).read_text(encoding="utf-8")


def _tree(module_name: str) -> ast.Module:
    return ast.parse(_source(module_name))


def _code_only(module_name: str) -> str:
    """The module with every docstring removed.

    A vocabulary check over raw source would fire on the prose that *explains*
    why a word is forbidden, which would make the guard impossible to document.
    """
    tree = _tree(module_name)
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


def _imports(module_name: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(_tree(module_name)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


# ---------------------------------------------------------------------------
# 1. Risk is not confidence
# ---------------------------------------------------------------------------

#: Every word that would mean market conviction had reached a size. `AP` §15.4
#: and `SPEC` §8.1: the risk budget is the owner's, never the setup's.
_CONFIDENCE_VOCABULARY = (
    "confidence",
    "probability",
    "conviction",
    "score",
    "strength",
    "quality",
    "supporting",
    "conflicting",
    "independence",
    "evidence",
    "readiness",
    "confirmed",
    "candidate",
    "setupstate",
    "win_rate",
    "expectancy",
)


@pytest.mark.parametrize("module_name", _modules())
def test_no_confidence_vocabulary_appears_in_the_code(module_name: str) -> None:
    """**The structural form of §33.** A size that moved with evidence count
    would be indistinguishable from one that did not, in every feature test that
    fixes the evidence; this asserts the words cannot be reached at all."""
    code = _code_only(module_name).lower()
    found = [word for word in _CONFIDENCE_VOCABULARY if word in code]
    assert found == [], found


@pytest.mark.parametrize("module_name", _modules())
def test_the_package_imports_no_evidence_or_setup_engine(module_name: str) -> None:
    """Duck-typed over the assessment, deliberately: a package that imported the
    setup engine could compare a state, and a size that depended on a state
    would be a size that depended on conviction."""
    for reached in _imports(module_name):
        assert not reached.startswith("fmis.swing_setup"), reached
        assert not reached.startswith("fmis.setup_evidence"), reached
        assert not reached.startswith("fmis.decision_support"), reached


# ---------------------------------------------------------------------------
# 2. No arithmetic of its own
# ---------------------------------------------------------------------------


def test_the_planning_module_takes_no_quotient_of_its_own() -> None:
    """The sizing division is written in exactly one place in the repository —
    `fmis.portfolio_risk.geometry.maximum_quantity_for_risk` — and a second one
    here would be a second place it could be wrong."""
    for node in ast.walk(_tree(f"{PACKAGE}.planning")):
        if isinstance(node, ast.BinOp):
            assert not isinstance(
                node.op, (ast.Div, ast.Mult, ast.FloorDiv)
            ), ast.unparse(node)


#: Every `Money`/`Quantity` construction in the package, and why each is not a
#: calculation. Asserted as an exact set: a third one appearing is a number this
#: package produced, and it has to be justified here before it can pass.
_PERMITTED_MONEY_CONSTRUCTIONS = {
    # The owner's declared capital, parsed from the text of their own file. A
    # value read, never derived.
    "Money(exact, asset)",
    # The risk distance the proposal already computed, re-denominated in the
    # market's quote asset. A subtraction that happened in
    # `fmis.position_sizing`, given the asset it was always in.
    "Money(risk_distance, quote)",
}


def test_the_package_constructs_money_only_where_it_is_not_computing_one() -> None:
    """Two constructions, both named, neither an arithmetic result."""
    calls = {
        ast.unparse(node)
        for module_name in _modules()
        for node in ast.walk(_tree(module_name))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"Money", "Quantity"}
    }
    assert calls == _PERMITTED_MONEY_CONSTRUCTIONS, calls


# ---------------------------------------------------------------------------
# 3. One number, and it is the specification's
# ---------------------------------------------------------------------------


def test_the_only_threshold_in_the_package_is_the_specifications_ceiling() -> None:
    """`fmis.risk` and `fmis.position_sizing` are guarded to hold no literal
    beyond `0` and `1`. This package holds exactly one more, it is `SPEC` §8.1's,
    and it is bound to a name that says so."""
    numbers: set[object] = set()
    for module_name in _modules():
        for node in ast.walk(_tree(module_name)):
            if isinstance(node, ast.Constant) and isinstance(
                node.value, (int, float)
            ):
                if isinstance(node.value, bool):
                    continue
                numbers.add(node.value)
    assert numbers <= {0, 1}, sorted(numbers - {0, 1})


def test_the_ceiling_is_written_as_decimal_text_exactly_once() -> None:
    """`Decimal("0.02")`, once, in `models`. Two spellings of one ceiling is how
    the two drift apart."""
    occurrences = [
        module_name
        for module_name in _modules()
        if 'Decimal("0.02")' in _source(module_name)
    ]
    assert occurrences == [f"{PACKAGE}.models"], occurrences


def test_the_ceiling_is_spelled_in_exactly_one_place_in_the_whole_source_tree() -> None:
    """Repo-wide, not merely package-wide. **Two spellings of one ceiling is how
    the two drift apart**, and the second one would not have to be in this
    package to do it — it could be a constant in a surface, a default argument in
    a composition root, or a comparison in a future engine.

    Docstrings are stripped before the scan: `fmis.portfolio_risk.constraints`
    legitimately *mentions* `Decimal("0.02")` in prose while explaining that a
    percent limit is a fraction, and a guard that fired on documentation would be
    a guard whose only fix is to delete the explanation.
    """
    import fmis

    root = pathlib.Path(fmis.__file__).resolve().parent
    holders = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                body = node.body
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    node.body = body[1:] or [ast.Pass()]
        # Matched on the **AST shape**, not on text: `ast.unparse` normalizes
        # `Decimal("0.02")` to single quotes, so a substring search over the
        # unparsed source silently finds nothing and the guard passes vacuously.
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Decimal"
                and len(node.args) == 1
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "0.02"
            ):
                holders.append(str(path.relative_to(root)))
                break
    assert holders == ["risk_policy/models.py"], holders


def test_no_float_literal_appears_anywhere_in_the_package() -> None:
    floats = [
        node.value
        for module_name in _modules()
        for node in ast.walk(_tree(module_name))
        if isinstance(node, ast.Constant) and isinstance(node.value, float)
    ]
    assert floats == []


# ---------------------------------------------------------------------------
# 4. Nothing executes, and nothing writes
# ---------------------------------------------------------------------------

_FORBIDDEN = (
    "order",
    "execute",
    "broker",
    "exchange_api",
    "binance",
    "tradingview",
    "withdraw",
    "leverage",
    "buy",
    "sell",
)


def _identifiers(module_name: str) -> set[str]:
    """Every name the code *uses*, with string literals deliberately excluded.

    The distinction matters here more than anywhere: this package's prose
    constants say *"not an order price"* and *"leverage magnifies a loss and
    never makes one inside a ceiling that it is outside of"* — sentences printed
    on the page precisely to rule those things out. A guard that searched raw
    text would fire on its own warnings, and the only way to pass it would be to
    delete them.
    """
    found: set[str] = set()
    for node in ast.walk(_tree(module_name)):
        if isinstance(node, ast.Name):
            found.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            found.add(node.attr.lower())
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name.lower())
        elif isinstance(node, ast.arg):
            found.add(node.arg.lower())
        elif isinstance(node, ast.keyword) and node.arg:
            found.add(node.arg.lower())
    return found


@pytest.mark.parametrize("module_name", _modules())
def test_the_package_names_no_execution_concept(module_name: str) -> None:
    """No identifier here can hold, place, price or leverage an order."""
    identifiers = _identifiers(module_name)
    found = sorted(
        word
        for word in _FORBIDDEN
        if any(word in identifier for identifier in identifiers)
    )
    assert found == [], found


def test_the_prose_that_rules_out_execution_and_leverage_is_still_present() -> None:
    """The counterpart to the guard above: those words *must* appear in the
    package's own text, because the page has to say them. A refactor that
    silenced the warnings would pass the identifier guard and fail this."""
    text = " ".join(_source(name) for name in _modules()).lower()
    for phrase in ("not an order price", "leverage"):
        assert phrase in text, phrase


@pytest.mark.parametrize("module_name", _modules())
def test_the_package_opens_no_store_and_reaches_no_network(module_name: str) -> None:
    for reached in _imports(module_name):
        assert not reached.startswith("fmis.persistence"), reached
        assert not reached.startswith("fmis.providers"), reached
        assert reached not in {"socket", "urllib", "http", "requests"}, reached


def test_only_the_declaration_module_touches_a_filesystem() -> None:
    """`models` and `planning` are pure: the same inputs produce the same result
    with no file, no clock and no network, which is what makes every arithmetic
    test in this suite deterministic."""
    for module_name in (f"{PACKAGE}.models", f"{PACKAGE}.planning"):
        assert "pathlib" not in _imports(module_name)
        assert "json" not in _imports(module_name)


@pytest.mark.parametrize("module_name", _modules())
def test_no_module_reads_a_clock(module_name: str) -> None:
    """A financial result that changed with wall-clock time would not be
    reproducible, and could not be re-derived for an archived decision."""
    code = _code_only(module_name)
    for forbidden in ("datetime.now", "datetime.utcnow", "time.time", "date.today"):
        assert forbidden not in code, forbidden


# ---------------------------------------------------------------------------
# 5. Dependency direction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", _modules())
def test_every_package_this_one_imports_is_on_the_permitted_list(
    module_name: str,
) -> None:
    reached = {
        name
        for name in _imports(module_name)
        if name.startswith("fmis") and name != "fmis"
    }
    unexpected = {name for name in reached if not name.startswith(PERMITTED)}
    assert unexpected == set(), unexpected


def test_no_surface_package_is_imported_by_this_one() -> None:
    """Risk is composed *by* the product, and never imports it. The reverse
    would be a cycle, and would let a rendering concern reach a size."""
    for module_name in _modules():
        for reached in _imports(module_name):
            for surface in (
                "fmis.operator_dashboard",
                "fmis.swing_workspace",
                "fmis.today",
                "fmis.pipeline",
            ):
                assert not reached.startswith(surface), (module_name, reached)
