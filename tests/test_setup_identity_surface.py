"""`fmits setup` wired to the stable setup identity.

Network-free: every assessment is hand-built and the CLI is driven through its
own runner with the analysis path stubbed, so no candle is ever fetched.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import pytest

import fmis
from fmis.accounts import MarketId, MarketMode, VenueId
from fmis.decision_context import ContextState
from fmis.level_crossing import LevelOrigin, LevelSide, PriceLevel
from fmis.market_structure import StructuralSwingLabel
from fmis.money import AssetCode
from fmis.pipeline import cli
from fmis.provenance import Absent
from fmis.setup_observation import (
    IDENTITY_WIDTH,
    observe_setup_series,
    render_identity_run,
    render_setup_identity,
)
from fmis.swing_setup import (
    Direction,
    Probability,
    ProbabilityStatus,
    RiskReward,
    SetupAssessment,
    SetupState,
    Trigger,
    TriggerKind,
    render_setup,
)
from fmis.swing_setup.compose import SetupRunResult

MARKET = MarketId(VenueId("binance"), AssetCode("BTC"), AssetCode("USDT"), MarketMode.SPOT)
PIVOT = datetime(2026, 6, 1, tzinfo=timezone.utc)
START = datetime(2026, 8, 1, tzinfo=timezone.utc)
NOT_CALIBRATED = Probability(status=ProbabilityStatus.NOT_CALIBRATED, value=None)


def at(bar: int) -> datetime:
    return START + timedelta(hours=bar)


def assessment(
    *,
    bar: int = 0,
    swing_index: int = 5,
    pivot: datetime = PIVOT,
    symbol: str = "BTCUSDT",
    direction: Direction | None = Direction.LONG,
    state: SetupState = SetupState.CANDIDATE,
) -> SetupAssessment:
    common = dict(
        symbol=symbol, as_of=at(bar), objective="swing",
        probability=NOT_CALIBRATED, regime_context=("context: trending",),
        sufficiency=ContextState.SUFFICIENT, limitations=("X-1: none",),
        policy_id="swing-setup-v1", source="fixture",
    )
    if direction is None:
        return SetupAssessment(
            state=SetupState.WAIT, direction=None, thesis=("no candidate",),
            directional_factors=(), confirmation=(), invalidation=(), trigger=None,
            reference_price=None, stop=None, targets=(), risk_reward=None, **common,
        )
    stop = PriceLevel(
        side=LevelSide.LOWER, price=90.0,
        origin=LevelOrigin(index=swing_index, timestamp=pivot,
                           label=StructuralSwingLabel.LOWER_LOW, confirmation_bars=2),
    )
    target = PriceLevel(
        side=LevelSide.UPPER, price=130.0,
        origin=LevelOrigin(index=3, timestamp=pivot,
                           label=StructuralSwingLabel.HIGHER_HIGH, confirmation_bars=2),
    )
    return SetupAssessment(
        state=state, direction=direction, thesis=("trend continuation retest",),
        directional_factors=(), confirmation=("awaiting confirmation",),
        invalidation=("structural invalidation",),
        trigger=Trigger(kind=TriggerKind.AWAITING_STRUCTURE_BREAK, statement="awaiting"),
        reference_price=100.0, stop=stop, targets=(target,),
        risk_reward=RiskReward(entry=100.0, stop=90.0, target=130.0,
                               risk=10.0, reward=30.0, ratio=3.0),
        **common,
    )


def run_of(*assessments: SetupAssessment, gap: int = 0):
    return observe_setup_series(
        list(assessments), market=MARKET, code_version=fmis.__version__,
        occurrence_gap_bars=gap,
    )


# ---------------------------------------------------------------------------
# The block itself
# ---------------------------------------------------------------------------


def test_the_block_prints_the_stable_identity_and_its_measured_anchor() -> None:
    text = render_setup_identity(run_of(assessment()))

    assert "SETUP IDENTITY" in text
    assert "occurrence" in text
    assert "anchor" in text
    assert "binance:BTCUSDT:spot" in text
    assert "swing-setup-v1" in text


def test_the_block_never_prints_the_window_relative_index() -> None:
    """`swing_index` is provenance; printing it beside an identity invites misuse."""
    subject = run_of(assessment(swing_index=417))
    text = render_setup_identity(subject)

    assert "417" not in text
    # …and it is still carried on the observation, unchanged.
    assert subject.observations[0].reading.stop.origin.swing_index == 417


def test_a_wait_reading_states_why_it_has_no_identity() -> None:
    text = render_setup_identity(run_of(assessment(direction=None)))

    assert "—" in text
    assert "MEASURED level origin" in text
    assert "occurrence  " not in text


def test_an_empty_run_says_nothing_was_observed() -> None:
    text = render_setup_identity(run_of())

    assert "no reading was observed" in text


def test_every_line_stays_within_the_page_width() -> None:
    for subject in (
        run_of(assessment()),
        run_of(assessment(direction=None)),
        run_of(),
        run_of(assessment(bar=0), assessment(bar=1), gap=0),
    ):
        for text in (render_setup_identity(subject), render_identity_run(subject)):
            for line in text.splitlines():
                assert len(line) <= IDENTITY_WIDTH, f"{len(line)}: {line!r}"


def test_the_block_rule_matches_the_engine_renderers_rule() -> None:
    """The two blocks are printed together and must read as one page.

    The engine renderer's `_WIDTH` governs its **rule** lines; its content lines
    run longer when a thesis or a limitation does. This block matches the rule
    exactly and additionally keeps every content line inside it, which is a
    stricter choice than the engine makes and is pinned by the test above.
    """
    engine_rules = {
        len(line) for line in render_setup(assessment()).splitlines()
        if set(line) <= {"═"} and line
    }

    assert engine_rules == {IDENTITY_WIDTH}
    identity_rules = {
        len(line) for line in render_setup_identity(run_of(assessment())).splitlines()
        if line.startswith("──")
    }
    assert identity_rules == {IDENTITY_WIDTH}


def test_a_non_run_is_refused_by_both_renderers() -> None:
    for renderer in (render_setup_identity, render_identity_run):
        with pytest.raises(TypeError):
            renderer("a run")


# ---------------------------------------------------------------------------
# Counts — the claim only a series may make
# ---------------------------------------------------------------------------


def test_the_single_reading_block_makes_no_repeat_claim() -> None:
    """One invocation observes one bar and must not imply it has seen more."""
    text = render_setup_identity(run_of(assessment()))

    assert "repeat" not in text
    assert "1×" not in text
    assert "continuity" in text


def test_the_series_block_reports_the_repeat_count() -> None:
    text = render_identity_run(run_of(assessment(bar=0), assessment(bar=1), gap=0))

    assert "2× · repeat of an open idea" in text


def test_the_series_block_reports_a_new_occurrence() -> None:
    text = render_identity_run(run_of(assessment(bar=0)))

    assert "1× · new occurrence" in text


def test_the_repeat_count_increments_deterministically() -> None:
    counts = []
    for length in range(1, 6):
        subject = run_of(*(assessment(bar=b) for b in range(length)), gap=0)
        counts.append(subject.repeated_observation_count)

    assert counts == [1, 2, 3, 4, 5]


def test_a_new_anchor_resets_the_count_and_changes_the_identity() -> None:
    first = run_of(assessment(bar=0), assessment(bar=1), gap=5)
    then = run_of(
        assessment(bar=0), assessment(bar=1),
        assessment(bar=2, pivot=PIVOT + timedelta(days=3)), gap=5,
    )

    assert first.repeated_observation_count == 2
    assert then.repeated_observation_count == 1
    assert then.is_new_occurrence
    assert first.occurrences[0].identity != then.occurrences[-1].identity


def test_the_series_block_states_an_absent_confirmation() -> None:
    text = render_identity_run(run_of(assessment(state=SetupState.CANDIDATE)))

    assert "confirmed   —" in text


def test_the_series_block_prints_a_real_confirmation() -> None:
    text = render_identity_run(run_of(assessment(state=SetupState.CONFIRMED)))

    assert at(0).isoformat() in text


def test_the_series_block_says_when_nothing_directional_was_seen() -> None:
    text = render_identity_run(run_of(assessment(direction=None)))

    assert "observed    —" in text


# ---------------------------------------------------------------------------
# Identity stability — the property the surface exists to expose
# ---------------------------------------------------------------------------


def test_repeated_calls_on_the_same_setup_print_the_same_identity() -> None:
    """What the owner actually compares between two runs of the command."""
    monday = render_setup_identity(run_of(assessment(bar=0, swing_index=40)))
    friday = render_setup_identity(run_of(assessment(bar=96, swing_index=0)))

    monday_line = [ln for ln in monday.splitlines() if "occurrence" in ln][0]
    friday_line = [ln for ln in friday.splitlines() if "occurrence" in ln][0]

    assert monday_line == friday_line


def test_a_new_anchor_prints_a_different_identity() -> None:
    before = render_setup_identity(run_of(assessment(swing_index=5)))
    after = render_setup_identity(
        run_of(assessment(swing_index=5, pivot=PIVOT + timedelta(days=3)))
    )

    assert before != after


def test_no_lookahead_a_prefix_prints_the_prefixs_own_identity() -> None:
    series = [assessment(bar=b, swing_index=9 - b) for b in range(9)]

    for cut in range(1, len(series) + 1):
        partial = run_of(*series[:cut], gap=0)
        assert partial.observations[-1].as_of == at(cut - 1)
        assert partial.repeated_observation_count == cut


# ---------------------------------------------------------------------------
# The command surface
# ---------------------------------------------------------------------------


def _args(**overrides) -> argparse.Namespace:
    values = dict(
        symbols=["BTCUSDT"], limit=None, left_bars=2, right_bars=2,
        context="1w", setup="1d", execution="4h", band=None,
        transition_lookback=None,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


def _stub(monkeypatch, results):
    monkeypatch.setattr(cli, "run_setup_for_symbols", lambda *a, **k: results)


def test_the_command_appends_the_identity_block_to_the_page(monkeypatch, capsys) -> None:
    subject = assessment()
    _stub(monkeypatch, [SetupRunResult("BTCUSDT", assessment=subject)])

    code = cli._run_setup(_args())
    out = capsys.readouterr().out

    assert code == cli.EXIT_OK
    assert "SETUP IDENTITY" in out
    # The engine's own page is byte-identical and comes first.
    assert out.startswith(render_setup(subject))


def test_the_existing_page_is_unchanged_byte_for_byte(monkeypatch, capsys) -> None:
    """Requirement 1: no existing field is altered, reordered or removed."""
    subject = assessment()
    _stub(monkeypatch, [SetupRunResult("BTCUSDT", assessment=subject)])

    cli._run_setup(_args())
    out = capsys.readouterr().out

    engine_page = render_setup(subject)
    identity_block = render_setup_identity(run_of(subject))

    assert out == f"{engine_page}\n{identity_block}\n"


def test_a_symbol_that_cannot_be_split_still_prints_its_analysis(
    monkeypatch, capsys
) -> None:
    """The identity block is suppressed; the assessment is not."""
    subject = assessment(symbol="BTCEUR")
    _stub(monkeypatch, [SetupRunResult("BTCEUR", assessment=subject)])

    code = cli._run_setup(_args(symbols=["BTCEUR"]))
    out = capsys.readouterr().out

    assert code == cli.EXIT_OK
    assert out == f"{render_setup(subject)}\n"
    assert "SETUP IDENTITY" not in out


def test_a_failed_symbol_is_unaffected(monkeypatch, capsys) -> None:
    _stub(monkeypatch, [SetupRunResult("BTCUSDT", failure="no candles")])

    code = cli._run_setup(_args())
    captured = capsys.readouterr()

    assert code == cli.EXIT_FAILURE
    assert captured.out == ""
    assert "no candles" in captured.err


def test_several_symbols_each_get_their_own_block(monkeypatch, capsys) -> None:
    _stub(monkeypatch, [
        SetupRunResult("BTCUSDT", assessment=assessment(symbol="BTCUSDT")),
        SetupRunResult("ETHUSDT", assessment=assessment(symbol="ETHUSDT")),
    ])

    cli._run_setup(_args(symbols=["BTCUSDT", "ETHUSDT"]))
    out = capsys.readouterr().out

    assert out.count("SETUP IDENTITY") == 2
    assert "binance:BTCUSDT:spot" in out
    assert "binance:ETHUSDT:spot" in out


def test_a_wait_symbol_still_prints_a_block(monkeypatch, capsys) -> None:
    _stub(monkeypatch, [SetupRunResult("BTCUSDT", assessment=assessment(direction=None))])

    cli._run_setup(_args())
    out = capsys.readouterr().out

    assert "SETUP IDENTITY" in out
    assert "MEASURED level origin" in out


def test_the_command_writes_nothing_anywhere(monkeypatch, tmp_path, capsys) -> None:
    """Requirement 4 and 5: no store is opened and no projection is persisted."""
    import fmis.persistence.store as store_module

    def refuse(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("fmits setup opened a store")

    for name in dir(store_module):
        attribute = getattr(store_module, name)
        if callable(attribute) and name.startswith("open"):
            monkeypatch.setattr(store_module, name, refuse)

    _stub(monkeypatch, [SetupRunResult("BTCUSDT", assessment=assessment())])
    cli._run_setup(_args())

    assert "SETUP IDENTITY" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_the_projections_remain_unstorable() -> None:
    from fmis.persistence.errors import UnknownRecordKindError
    from fmis.persistence.kinds import SPECS, spec_for_record

    subject = run_of(assessment())

    assert len(SPECS) == 15
    for value in (subject, subject.observations[0], subject.occurrences[0]):
        with pytest.raises(UnknownRecordKindError):
            spec_for_record(value)


# ---------------------------------------------------------------------------
# Gaps found by mutation testing.
# ---------------------------------------------------------------------------


def test_the_identity_line_shows_a_comparable_prefix() -> None:
    """A truncated-to-nothing digest would compare equal for every setup."""
    subject = run_of(assessment())
    line = [
        ln for ln in render_setup_identity(subject).splitlines() if "occurrence" in ln
    ][0]
    shown = line.split("occurrence")[1].strip().rstrip("…")

    assert len(shown) >= 16
    assert subject.observations[0].identity.startswith(shown)


def test_the_anchor_line_states_the_confirmation_window() -> None:
    """ADR-0024: the window is part of what makes the origin the origin."""
    text = render_setup_identity(run_of(assessment()))

    assert "confirmed over 2 bars" in text


def test_the_block_describes_the_latest_reading_not_the_first() -> None:
    subject = run_of(assessment(bar=0), assessment(bar=7), gap=0)
    text = render_setup_identity(subject)

    assert at(7).isoformat() in text
    assert at(0).isoformat() not in text


def test_the_series_block_states_when_the_idea_began() -> None:
    text = render_identity_run(run_of(assessment(bar=0), assessment(bar=1), gap=0))

    assert f"began       {at(0).isoformat()}" in text


def test_the_command_groups_under_a_named_zero_tolerance() -> None:
    """One invocation observes one bar, so no gap can span anything.

    Named rather than inlined so a future series-holding surface must revisit it.
    """
    assert cli.SETUP_IDENTITY_GAP_BARS == 0
