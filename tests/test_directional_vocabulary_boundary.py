"""ADR-0028 §5 — directional vocabulary exists only where direction is legitimate.

**Widened for Milestone BH (Trade Domain Foundation), and the widening is the
point rather than a concession.** ADR-0028 §5 was written when the only half of
FMITS that existed was the *analysis* half, and the rule it protects is that an
engine reading candles must never emit a side. The trading domain is the *owner*
half: a ledger that cannot say a fill was a buy, and a position that cannot say
it is long, cannot record what happened to real money. Direction there is an
**owner assertion about their own money**, not an engine's opinion about a market.

So the guard is no longer "one package"; it is now **two named halves**, and the
market half's ban is unchanged and separately asserted below. Five trading-domain
packages are exempt and no others:

* `fmis.snapshotting` — `TradeDirection`, the side a *frozen reading* came down on
* `fmis.proposal` — the side a suggestion came down on, with both cases kept apart
* `fmis.plan` — the side the owner **committed** to, and which side of the entry
  their stop must therefore sit on. Added by Milestone BK. It is the same class
  of value `fmis.proposal` already holds: a suggestion says which side it came
  down on, and a plan says which side the owner acted on. Validating a stop's
  placement is impossible without it — *"below the entry on a long"* has no
  expression in a package that may not name the word
* `fmis.ledger` — `TradeSide`, which way the base asset actually moved
* `fmis.positions` — `PositionDirection`, which way exposure currently points
* `fmis.portfolio_risk` — which way the *portfolio* points. Added by Milestone
  BL. It is the aggregate of the side `fmis.positions` already holds: long
  exposure, short exposure, directional net and directional concentration are
  four of the figures the milestone exists to produce, and none of them has any
  expression in a package that may not name the word. It also carries the sign
  rule capital at risk depends on — *"`entry − stop` on a long, `stop − entry`
  on a short"* — which is the same value class `fmis.plan` was exempted for.
  It reads no candle and imports no engine, asserted twice: by
  `test_the_market_half_still_holds_no_directional_vocabulary_at_all` below and
  by `tests/test_portfolio_risk_architecture.py`, which pins its entire
  dependency surface as a set

**`fmis.trade_capture` is exempt as a surface, not as a domain package**, on the
identical footing `fmis/pipeline/cli.py` has held since ADR-0028: it is where the
owner states a side and where that statement is turned into a `TradeSide`, and a
capture command that cannot spell the direction the owner is trading cannot
capture the trade. It computes no market reading and imports no engine, which is
what the original rule protects and what
`test_the_market_half_still_holds_no_directional_vocabulary_at_all` still asserts
directly.

**This crossing is an architectural decision and is recorded as one.** ADR-0028's
own text scopes its rule to the analysis engines; extending that text to say so
explicitly is an ADR amendment the owner has not authorized, so this test states
the boundary and `docs/design/DIRECTIONAL_VOCABULARY_BOUNDARY_NOTE_BH.md` records
what needs deciding. Every engine below L7 remains covered exactly as before —
see `test_the_market_half_still_holds_no_directional_vocabulary_at_all`, which is
the assertion that actually protects the original rule.

---

Original note, unchanged:

ADR-0028 §5 — directional vocabulary exists only in `fmis.swing_setup`.

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

#: The trading-domain packages where direction is an owner assertion about their
#: own money rather than an engine's reading of a market. Named one by one, so a
#: seventh appearing anywhere fails this test and has to justify itself.
_TRADE_DOMAIN_PERMITTED_DIRS = frozenset(
    {
        SRC / "snapshotting",
        SRC / "proposal",
        SRC / "plan",
        SRC / "ledger",
        SRC / "positions",
        SRC / "portfolio_risk",
    }
)

#: The owner-half **surfaces**: where the owner states a side and where that
#: statement becomes a record. `pipeline/cli.py` has held this exemption since
#: ADR-0028; `trade_capture` is the composition root behind `fmits trade` and is
#: the same case. Kept as its own set rather than folded into the domain one, so
#: that "a package that stores direction" and "a package that asks the owner for
#: it" stay two different justifications.
_OWNER_SURFACE_DIRS = frozenset({SRC / "trade_capture"})

#: Every package that reads candles. The original rule, still absolute.
_MARKET_HALF_DIRS = frozenset(
    SRC / name
    for name in (
        "data",
        "ingest",
        "providers",
        "features",
        "alignment",
        "relative_value",
        "series_context",
        "market_structure",
        "structural_trend",
        "structure_break",
        "change_of_character",
        "level_crossing",
        "market_regime",
        "evidence",
        "decision_support",
        "decision_context",
        "workspace",
        "daily",
        "archive",
        "trading_context",
    )
)


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
        if path.parent in _TRADE_DOMAIN_PERMITTED_DIRS:
            continue
        if path.parent in _OWNER_SURFACE_DIRS:
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


def test_the_market_half_still_holds_no_directional_vocabulary_at_all() -> None:
    """The rule ADR-0028 actually protects, asserted directly.

    The exemption above widened *which* packages are scanned; it did not weaken
    what is being protected. Every package that reads a candle is checked here by
    name, so a `LONG` appearing in the market-structure engine fails whatever the
    trading domain is permitted to hold.
    """
    offenders = []
    for directory in sorted(_MARKET_HALF_DIRS):
        for path in sorted(directory.glob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            for token in _identifiers_and_string_values(tree):
                if token.lower() in _BANNED:
                    offenders.append((str(path.relative_to(SRC.parent.parent)), token))
    assert offenders == []


def test_the_trade_domain_exemption_is_bounded_to_six_named_packages() -> None:
    """Pins the widening, so a seventh exempt package is a deliberate edit here."""
    assert {path.name for path in _TRADE_DOMAIN_PERMITTED_DIRS} == {
        "snapshotting",
        "proposal",
        "plan",
        "ledger",
        "positions",
        "portfolio_risk",
    }
    for path in _TRADE_DOMAIN_PERMITTED_DIRS:
        assert path.is_dir(), path


def test_the_exempt_domain_packages_import_no_engine() -> None:
    """The exemption widens who may spell a side, never who may read a candle.

    The owner-surface exemption has carried this assertion since BK; BL applies
    it to the domain set too, because `fmis.portfolio_risk` is the first exempt
    domain package that reads the *store* rather than only holding values, and a
    package that both names a side and reached an engine would be the exact
    crossing ADR-0028 exists to prevent.
    """
    market_half = {f"fmis.{directory.name}" for directory in _MARKET_HALF_DIRS}
    #: The two archive modules the whole trading domain legitimately reaches: the
    #: canonical JSON encoder and the record-id validator. Both are pure
    #: infrastructure that read no candle, and `fmis.plan`'s own guard has
    #: permitted exactly this pair since BK.
    permitted = {"fmis.archive.json_safe", "fmis.archive.identity"}
    offenders: dict[str, set[str]] = {}
    for directory in sorted(_TRADE_DOMAIN_PERMITTED_DIRS):
        for path in sorted(directory.glob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            reached: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    reached.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    reached.add(node.module)
            crossing = {
                name
                for name in reached
                if name.split(".")[0] == "fmis"
                and ".".join(name.split(".")[:2]) in market_half
                and name not in permitted
            }
            if crossing:
                offenders[str(path.relative_to(SRC.parent.parent))] = crossing
    assert offenders == {}


def test_the_owner_surface_exemption_is_bounded_to_one_named_package() -> None:
    """`trade_capture` is the only directory exempt as a surface rather than a store.

    Pinned separately from the domain set so the two justifications cannot be
    confused: a domain package is exempt because it *holds* a side, and this one
    is exempt because it *asks the owner for* one.
    """
    assert {path.name for path in _OWNER_SURFACE_DIRS} == {"trade_capture"}
    for path in _OWNER_SURFACE_DIRS:
        assert path.is_dir(), path


def test_the_owner_surface_imports_no_engine() -> None:
    """The exemption widens who may spell a side, never who may read a candle.

    `fmis.trade_capture` is exempt from the vocabulary ban and must remain
    subject to the rule that ban exists to protect: no package that records what
    the owner did may reach a package that reads the market, or the record
    becomes a function of the analysis.
    """
    offenders: dict[str, set[str]] = {}
    for directory in sorted(_OWNER_SURFACE_DIRS):
        for path in sorted(directory.glob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            reached = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    root = ".".join(node.module.split(".")[:2])
                    if SRC / root.split(".")[-1] in _MARKET_HALF_DIRS:
                        reached.add(node.module)
            if reached:
                offenders[str(path.name)] = reached
    assert offenders == {}


def test_the_exempt_trade_domain_packages_do_use_the_vocabulary() -> None:
    """Sanity check that each exemption is real rather than precautionary.

    An exemption granted to a package that turns out not to need it is an
    exemption nobody would notice becoming wrong.
    """
    for directory in _TRADE_DOMAIN_PERMITTED_DIRS:
        found = set()
        for path in directory.glob("*.py"):
            tree = ast.parse(path.read_text())
            for token in _identifiers_and_string_values(tree):
                if token.lower() in _BANNED:
                    found.add(token.lower())
        assert found, directory.name


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
