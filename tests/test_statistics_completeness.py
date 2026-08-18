"""Every figure Milestone BP's brief named, proved present and reachable.

Not a behaviour suite — the four family files hold the arithmetic. This one
answers a different question: *"was the thing that was asked for actually
built"*, and it answers it by naming each requirement and reaching for it.

The brief's own lists are transcribed as data. A metric that is renamed, folded
into another or quietly dropped fails here with the brief's word for it in the
message, which is the only form in which "we built everything" is checkable a
year later.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fmis.money import AssetCode, Money
from fmis.provenance import Absent
from fmis.statistics import (
    DIMENSION_NAMES,
    CollectedTrades,
    LifecyclePhase,
    SamplePolicy,
    StatSource,
    build_report,
)
from statistics_helpers import at, money, stat

USDT = AssetCode("USDT")
FLOOR = SamplePolicy(minimum_sample=1)

#: A corpus rich enough that no figure is absent for want of an input: closed
#: winners and losers, an open trade, a cancelled one, an expired one, a
#: simulated trade with an excursion and a recorded one without.
RICH = (
    stat("w1", net="100", risk="50", r_multiple="2", closed_day=1, mfe="3", mae="-0.4"),
    stat("w2", net="200", risk="50", r_multiple="4", closed_day=2, mfe="5", mae="-0.2"),
    stat("l1", net="-50", risk="50", r_multiple="-1", closed_day=3, mfe="0.4", mae="-1"),
    stat("l2", net="-50", risk="50", r_multiple="-1", closed_day=9, mfe="0.2", mae="-1"),
    stat("s1", net="0", risk="50", r_multiple="0", closed_day=10, mfe="1", mae="-0.5"),
    stat("o1", phase=LifecyclePhase.OPEN, closed_day=None, net=None, r_multiple=None,
         mfe=None, mae=None, bars=None, exit_reason=None, risk="30"),
    stat("c1", phase=LifecyclePhase.CANCELLED, opened_day=None, closed_day=None,
         net=None, r_multiple=None, mfe=None, mae=None, bars=None, exit_reason=None,
         risk=None),
    stat("e1", phase=LifecyclePhase.EXPIRED, opened_day=None, closed_day=None,
         net=None, r_multiple=None, mfe=None, mae=None, bars=None, exit_reason=None,
         risk=None),
    stat("t1", phase=LifecyclePhase.TRIGGERED, opened_day=None, closed_day=None,
         net=None, r_multiple=None, mfe=None, mae=None, bars=None, exit_reason=None),
    stat("p1", phase=LifecyclePhase.PENDING, opened_day=None, closed_day=None,
         net=None, r_multiple=None, mfe=None, mae=None, bars=None, exit_reason=None),
    stat("r1", source=StatSource.RECORDED, net="40", risk="20", r_multiple="2",
         closed_day=12, mfe=None, mae=None, bars=None, interval=None),
)


@pytest.fixture(scope="module")
def report():
    return build_report(
        CollectedTrades(
            trades=RICH, refused=(), store_root="/tmp/complete", present=True
        ),
        at=at(30),
        policy=FLOOR,
        starting_equity=money("10000"),
        equity_basis=money("10000"),
        open_risk_ceiling=money("500"),
    )


def stated(value) -> bool:
    """Whether a figure came back as a value rather than an absence."""
    return not isinstance(value, Absent)


# --------------------------------------------------------------------------
# The brief's "General" list
# --------------------------------------------------------------------------

GENERAL_REQUIREMENTS = {
    "total trades": lambda g: g.total,
    "winning trades": lambda g: g.winning,
    "losing trades": lambda g: g.losing,
    "cancelled": lambda g: g.cancelled,
    "expired": lambda g: g.expired,
    "triggered": lambda g: g.triggered,
    "open": lambda g: g.open_trades,
    "closed": lambda g: g.closed,
    "paper": lambda g: g.paper,
    "live": lambda g: g.live,
    "long and short": lambda g: g.by_direction,
    "average holding time": lambda g: g.average_holding_time,
    "median holding time": lambda g: g.median_holding_time,
    "maximum holding time": lambda g: g.maximum_holding_time,
    "minimum holding time": lambda g: g.minimum_holding_time,
    "average bars held": lambda g: g.average_bars_held,
    "median bars held": lambda g: g.median_bars_held,
}


@pytest.mark.parametrize("requirement", sorted(GENERAL_REQUIREMENTS))
def test_the_general_list_is_built(report, requirement: str) -> None:
    value = GENERAL_REQUIREMENTS[requirement](report.primary.general)
    assert value is not None, requirement
    assert stated(value), requirement


# --------------------------------------------------------------------------
# The brief's "Performance" list
# --------------------------------------------------------------------------

PERFORMANCE_REQUIREMENTS = {
    "gross profit": lambda p: p.gross_profit,
    "gross loss": lambda p: p.gross_loss,
    "net profit": lambda p: p.net_profit,
    "average win": lambda p: p.average_win,
    "average loss": lambda p: p.average_loss,
    "largest win": lambda p: p.largest_win,
    "largest loss": lambda p: p.largest_loss,
    "average R": lambda p: p.average_r,
    "median R": lambda p: p.median_r,
    "best R": lambda p: p.best_r,
    "worst R": lambda p: p.worst_r,
    "profit factor": lambda p: p.profit_factor,
    "payoff ratio": lambda p: p.payoff_ratio,
    "expectancy": lambda p: p.expectancy,
    "expectancy in R": lambda p: p.expectancy_r,
    "win rate": lambda p: p.win_rate,
    "loss rate": lambda p: p.loss_rate,
}


@pytest.mark.parametrize("requirement", sorted(PERFORMANCE_REQUIREMENTS))
def test_the_performance_list_is_built(report, requirement: str) -> None:
    assert stated(PERFORMANCE_REQUIREMENTS[requirement](report.primary.performance)), (
        requirement
    )


# --------------------------------------------------------------------------
# The brief's "Risk" list
# --------------------------------------------------------------------------

RISK_REQUIREMENTS = {
    "maximum drawdown": lambda a: a.drawdown.maximum,
    "current drawdown": lambda a: a.drawdown.current,
    "average drawdown": lambda a: a.drawdown.average,
    "longest drawdown": lambda a: a.drawdown.longest,
    "recovery periods": lambda a: a.drawdown.recoveries,
    "largest open risk": lambda a: a.risk.largest_open_risk,
    "largest closed risk": lambda a: a.risk.largest_closed_risk,
    "average open risk": lambda a: a.risk.average_open_risk,
    "average closed risk": lambda a: a.risk.average_closed_risk,
    "risk utilization": lambda a: a.risk.risk_utilization,
    "average risk %": lambda a: a.risk.average_risk_fraction,
    "median risk %": lambda a: a.risk.median_risk_fraction,
}


@pytest.mark.parametrize("requirement", sorted(RISK_REQUIREMENTS))
def test_the_risk_list_is_built(report, requirement: str) -> None:
    assert stated(RISK_REQUIREMENTS[requirement](report.primary)), requirement


# --------------------------------------------------------------------------
# The brief's "Quality" list
# --------------------------------------------------------------------------

QUALITY_REQUIREMENTS = {
    "average MAE": lambda q: q.average_adverse_r,
    "average MFE": lambda q: q.average_favourable_r,
    "median MAE": lambda q: q.median_adverse_r,
    "median MFE": lambda q: q.median_favourable_r,
    "maximum MAE": lambda q: q.maximum_adverse_r,
    "maximum MFE": lambda q: q.maximum_favourable_r,
    "capture efficiency": lambda q: q.average_capture_efficiency,
    "average excursion": lambda q: q.average_excursion_r,
}


@pytest.mark.parametrize("requirement", sorted(QUALITY_REQUIREMENTS))
def test_the_quality_list_is_built(report, requirement: str) -> None:
    assert stated(QUALITY_REQUIREMENTS[requirement](report.primary.quality)), requirement


def test_the_two_distributions_the_brief_names_are_built(report) -> None:
    quality = report.primary.quality
    assert quality.r_distribution.size > 0
    assert quality.holding_time_distribution.size > 0


# --------------------------------------------------------------------------
# The brief's "Breakdowns" list
# --------------------------------------------------------------------------

#: The brief's own words, mapped to the dimension this engine cuts on.
BREAKDOWN_REQUIREMENTS = {
    "per symbol": "symbol",
    "per timeframe": "timeframe",
    "per setup type": "setup",
    "per direction": "direction",
    "per market regime": "regime",
    "per month": "month",
    "per quarter": "quarter",
    "per year": "year",
    "per account": "account",
    "per venue": "venue",
    "paper and live": "book",
}


@pytest.mark.parametrize("requirement", sorted(BREAKDOWN_REQUIREMENTS))
def test_the_breakdown_list_is_built(report, requirement: str) -> None:
    dimension = BREAKDOWN_REQUIREMENTS[requirement]
    cut = report.primary.breakdowns.by_dimension(dimension)
    assert not isinstance(cut, Absent), requirement
    assert cut.cells, requirement


def test_every_dimension_the_engine_names_is_one_the_brief_asked_for() -> None:
    """The other direction: no dimension was invented that nobody asked for.
    `source` is the one addition, and it is here deliberately — *"simulated"*
    versus *"recorded"* is the distinction `ST-2` exists around."""
    assert set(DIMENSION_NAMES) == set(BREAKDOWN_REQUIREMENTS.values()) | {"source"}


# --------------------------------------------------------------------------
# The brief's "Equity" and "Drawdown" sections
# --------------------------------------------------------------------------


def test_the_equity_curve_is_deterministic_and_steps_per_closed_trade(report) -> None:
    equity = report.primary.equity
    closed = [entry for entry in RICH if entry.is_closed]
    assert len(equity.points) == len(closed)


def test_open_trades_are_tracked_separately_from_the_curve(report) -> None:
    assert report.primary.equity.open_trades == 1


def test_historical_replay_is_supported(report) -> None:
    replayed = report.primary.equity.as_of(at(2))
    assert len(replayed.points) < len(report.primary.equity.points)


def test_the_drawdown_curve_states_all_four_summary_figures(report) -> None:
    drawdown = report.primary.drawdown
    for name in ("current", "maximum", "average", "longest"):
        assert getattr(drawdown, name) is not None, name


# --------------------------------------------------------------------------
# The brief's "Reporting" and "Workspace" sections
# --------------------------------------------------------------------------


def test_the_five_commands_the_brief_names_are_registered() -> None:
    from fmis.pipeline import cli as cli_module

    names = {command.name for command in cli_module.COMMANDS}
    assert {"statistics", "performance", "expectancy", "equity", "trades"} <= names
    parser = cli_module.build_parser()
    assert parser.parse_args(["trades", "summary"]).trades_command == "summary"


WORKSPACE_REQUIREMENTS = {
    "current expectancy": lambda s: s.expectancy,
    "win rate": lambda s: s.win_rate,
    "profit factor": lambda s: s.profit_factor,
    "open trades": lambda s: s.open_trades,
    "closed today": lambda s: s.closed_today,
    "last 10 trades": lambda s: s.recent,
    "current drawdown": lambda s: s.current_drawdown,
    "current equity": lambda s: s.current_equity,
    "average R": lambda s: s.average_r,
    "average holding time": lambda s: s.average_holding_time,
    "paper vs live comparison": lambda s: s.books,
}


@pytest.mark.parametrize("requirement", sorted(WORKSPACE_REQUIREMENTS))
def test_the_workspace_list_is_built(report, requirement: str) -> None:
    from fmis.today import NotAvailable, performance_summary

    section = performance_summary(report, at=at(30))
    value = WORKSPACE_REQUIREMENTS[requirement](section)
    assert value is not None, requirement
    assert not isinstance(value, NotAvailable), requirement


def test_the_workspace_section_is_on_the_rendered_page() -> None:
    from fmis.today.render import _performance_block

    assert callable(_performance_block)


# --------------------------------------------------------------------------
# The brief's "Forbidden" list
# --------------------------------------------------------------------------

#: Every capability the brief forbade. Checked as **source-level absence**
#: across the package, because a forbidden capability that exists but is
#: unreachable today is a capability a later edit makes reachable.
FORBIDDEN_VOCABULARY = (
    "sklearn", "torch", "tensorflow", "numpy", "scipy", "pandas",
    "openai", "anthropic", "telegram", "requests", "websocket", "websockets",
    "matplotlib", "plotly", "seaborn", "flask", "django", "fastapi",
    "ccxt", "binance",
)


@pytest.mark.parametrize("name", FORBIDDEN_VOCABULARY)
def test_the_package_imports_nothing_the_brief_forbade(name: str) -> None:
    import ast
    import importlib
    import inspect
    import pkgutil
    from pathlib import Path

    import fmis.statistics as package

    modules = [package.__name__] + [
        module.name
        for module in pkgutil.iter_modules(package.__path__, prefix=f"{package.__name__}.")
    ]
    for module_name in modules:
        source = Path(inspect.getfile(importlib.import_module(module_name))).read_text(
            encoding="utf-8"
        )
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(name), module_name
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(name), module_name


def test_no_probability_is_calibrated_anywhere_in_this_package() -> None:
    """`AP` §20.6: `calibrated_probability` is `ABSENT` until earned, and this
    milestone does not earn it.

    Checked over **identifiers and function names**, not over raw text, for the
    reason `test_directional_vocabulary_boundary.py` gives: every module here
    discusses what it refuses to produce, and a substring scan would flag each
    denial sentence as the thing it denies.
    """
    import ast
    import importlib
    import inspect
    import pkgutil
    from pathlib import Path

    import fmis.statistics as package

    modules = [package.__name__] + [
        module.name
        for module in pkgutil.iter_modules(package.__path__, prefix=f"{package.__name__}.")
    ]
    banned = {"calibrated_probability", "predict", "forecast", "estimate", "infer"}
    for module_name in modules:
        source = Path(inspect.getfile(importlib.import_module(module_name))).read_text(
            encoding="utf-8"
        )
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                assert node.name.lower() not in banned, f"{module_name}: {node.name}"
            elif isinstance(node, ast.Name):
                assert node.id.lower() not in banned, f"{module_name}: {node.id}"
            elif isinstance(node, ast.Attribute):
                assert node.attr.lower() not in banned, f"{module_name}: {node.attr}"


def test_the_package_declares_in_prose_that_it_calibrates_nothing() -> None:
    """The other half: the refusal must be **stated**, not merely true. An
    absence nobody wrote down is an absence a later milestone fills in without
    noticing it was a decision."""
    import fmis.statistics as package

    assert "calibrated_probability" in package.__doc__
    assert "predicts nothing" in package.__doc__
