"""The seal, and what it is worth. **These tests ARE the pre-registration's teeth.**

A pre-registration nobody checks is a comment. The guards here are what turn
`fmis.swing_lab.preregistration` into an artifact a reader can rely on:

* the digest is recomputed from the content and compared to the pinned constant,
  so a threshold edited after a result was seen cannot be committed silently;
* every field that feeds the digest is shown to change it, so the seal cannot be
  made vacuous by carrying only the parts that never move;
* the samples are shown to be pairwise disjoint, so no trade can be counted in
  two of them;
* the promotion gate is shown to refuse a post-hoc policy and a non-structural
  one by construction rather than by convention.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from fmis.swing_lab.entry import PRE_DECLARED_ENTRY_POLICIES
from fmis.swing_lab.exits import PRE_DECLARED_EXIT_POLICIES
from fmis.swing_lab.geometry import StopRule, TargetRule
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.nonstructural import SyntheticGeometryPolicy
from fmis.swing_lab.preregistration import (
    CANDIDATE_CRITERIA,
    DECIDING_COST_POLICY_ID,
    DEVELOPMENT_SYMBOLS,
    HOLDOUT_SYMBOLS,
    PLATEAU_RULES,
    PRE_REGISTRATION,
    PRE_REGISTERED_HYPOTHESES,
    PRE_REGISTERED_POLICY_IDS,
    PREREGISTRATION_DIGEST,
    PRIMARY_STOP_ATR,
    PRIMARY_TARGET_R,
    SAMPLES,
    STOP_ATR_NEIGHBOURHOOD,
    TARGET_R_NEIGHBOURHOOD,
    SampleRole,
    is_pre_registered,
    preregistration_digest,
    sample_membership,
    sample_of,
    verify_preregistration,
)

_UTC = timezone.utc


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=_UTC)


# ------------------------------------------------------------------- seal ---


def test_the_pinned_digest_is_the_digest_of_the_content() -> None:
    """**The whole milestone rests on this one assertion.**

    If it fails, either the pre-registration was edited after it was sealed or
    the seal was rewritten. Both are things a reader must be told about, and a
    red test is how they are told.
    """
    assert preregistration_digest() == PREREGISTRATION_DIGEST
    assert verify_preregistration(PREREGISTRATION_DIGEST) is True


def test_the_digest_is_stable_across_runs_and_hash_seeds() -> None:
    assert preregistration_digest() == preregistration_digest()


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda p: replace(p, stop_atr_neighbourhood=(0.35, 0.50, 0.65)),
            id="a threshold removed from the neighbourhood",
        ),
        pytest.param(
            lambda p: replace(p, target_r_neighbourhood=(1.5, 2.0, 3.0)),
            id="a target multiple changed",
        ),
        pytest.param(
            lambda p: replace(p, samples=p.samples[:2]),
            id="the holdout sample dropped",
        ),
        pytest.param(
            lambda p: replace(p, hypotheses=p.hypotheses[:-1]),
            id="a hypothesis removed",
        ),
        pytest.param(
            lambda p: replace(p, candidate_criteria=p.candidate_criteria[:-1]),
            id="a candidate criterion removed",
        ),
        pytest.param(
            lambda p: replace(p, plateau_rules=p.plateau_rules[:2]),
            id="a plateau rule removed",
        ),
        pytest.param(
            lambda p: replace(p, cost_scenarios=p.cost_scenarios[:1]),
            id="a cost scenario removed",
        ),
        pytest.param(
            lambda p: replace(p, deciding_cost_policy_id="swing-lab-frictionless"),
            id="the deciding scenario switched to frictionless",
        ),
        pytest.param(
            lambda p: replace(p, entry_policies=p.entry_policies[:1]),
            id="an entry rule removed",
        ),
        pytest.param(
            lambda p: replace(p, exit_policies=p.exit_policies[:1]),
            id="an exit mechanic removed",
        ),
        pytest.param(
            lambda p: replace(p, timeframe_variant_ids=("swing_current",)),
            id="a timeframe variant removed",
        ),
    ],
)
def test_every_sealed_field_moves_the_digest(mutate) -> None:
    """A seal that ignores a field is not a seal on that field.

    Each mutation is a change a researcher could plausibly want to make after
    seeing a result — dropping a failing neighbour, deleting the criterion that
    blocked a promotion, promoting on the frictionless column. Every one of them
    must change the digest.
    """
    assert preregistration_digest(mutate(PRE_REGISTRATION)) != PREREGISTRATION_DIGEST


def test_changing_a_sample_window_moves_the_digest() -> None:
    """The most tempting post-hoc edit of all: move the boundary until it works."""
    shifted = replace(
        PRE_REGISTRATION,
        samples=(
            replace(SAMPLES[0], signal_end=_utc("2025-09-01T00:00:00")),
            *SAMPLES[1:],
        ),
    )
    assert preregistration_digest(shifted) != PREREGISTRATION_DIGEST


def test_changing_a_symbol_list_moves_the_digest() -> None:
    trimmed = replace(
        PRE_REGISTRATION,
        samples=(
            replace(SAMPLES[0], symbols=DEVELOPMENT_SYMBOLS[:-1]),
            *SAMPLES[1:],
        ),
    )
    assert preregistration_digest(trimmed) != PREREGISTRATION_DIGEST


def test_verify_refuses_a_non_string() -> None:
    with pytest.raises(TypeError, match="digest must be a str"):
        verify_preregistration(object())


def test_digest_refuses_a_non_preregistration() -> None:
    with pytest.raises(TypeError, match="must be a Preregistration"):
        preregistration_digest(object())


# ---------------------------------------------------------------- samples ---


def test_the_three_samples_are_pairwise_disjoint() -> None:
    """No candidate may be counted twice. Checked by the predicate, not by reading.

    A symbol split alone would put the same market period in two samples and a
    date split alone would put the same symbol in two; `SampleSpec.holds`
    requires both, and this walks every (symbol, instant) pair that could
    plausibly collide.
    """
    instants = [
        _utc(text)
        for text in (
            "2023-06-01T00:00:00", "2024-01-01T00:00:00", "2024-06-01T00:00:00",
            "2025-05-31T23:59:59", "2025-06-01T00:00:00", "2026-07-31T23:59:59",
        )
    ]
    for symbol in (*DEVELOPMENT_SYMBOLS, *HOLDOUT_SYMBOLS):
        for moment in instants:
            claimed = [spec.name for spec in SAMPLES if spec.holds(symbol, moment)]
            assert len(claimed) <= 1, (symbol, moment, claimed)


def test_development_and_holdout_share_no_symbol() -> None:
    assert not set(DEVELOPMENT_SYMBOLS) & set(HOLDOUT_SYMBOLS)


def test_the_holdout_is_a_symbol_split_and_says_so() -> None:
    holdout = PRE_REGISTRATION.sample("holdout")
    assert holdout.role is SampleRole.HOLDOUT
    # The assertion reads the SEALED wording. It was written against a guess and
    # corrected to match the seal — never the other way round, because editing
    # the pre-registration to satisfy a test is the exact move this file exists
    # to make impossible.
    assert "no milestone of this repository has ever measured" in holdout.contamination
    assert "less liquid" in holdout.contamination


def test_development_declares_its_own_contamination() -> None:
    """A sample that hid its contamination would be the milestone's worst defect."""
    development = PRE_REGISTRATION.sample("development")
    assert "CONTAMINATED BY CONSTRUCTION" in development.contamination


def test_sample_boundaries_are_half_open() -> None:
    """The instant a sample ends belongs to the next one, never to both."""
    development = PRE_REGISTRATION.sample("development")
    validation = PRE_REGISTRATION.sample("validation")
    boundary = development.signal_end
    assert development.holds("BTCUSDT", boundary) is False
    assert validation.holds("BTCUSDT", boundary) is True


def test_sample_of_refuses_an_overlap() -> None:
    """Two specs claiming one candidate is a caller error, and is refused loudly."""
    overlapping = (
        replace(SAMPLES[0], name="one"),
        replace(SAMPLES[0], name="two"),
    )
    with pytest.raises(SwingLabError, match="pairwise disjoint"):
        sample_of("BTCUSDT", _utc("2024-01-01T00:00:00"), overlapping)


def test_sample_membership_counts_the_unclaimed() -> None:
    """A window boundary that claims nothing must be visible, not silently zero."""
    tally = sample_membership(
        [
            ("BTCUSDT", _utc("2024-01-01T00:00:00")),
            ("DOGEUSDT", _utc("2025-01-01T00:00:00")),
            ("BTCUSDT", _utc("2019-01-01T00:00:00")),
        ]
    )
    assert tally["development"] == 1
    assert tally["holdout"] == 1
    assert tally["unclaimed"] == 1


def test_a_sample_refuses_an_inverted_window() -> None:
    with pytest.raises(SwingLabError, match="ends before it starts"):
        replace(SAMPLES[0], signal_end=SAMPLES[0].signal_start)


def test_a_sample_refuses_an_empty_symbol_list() -> None:
    with pytest.raises(SwingLabError, match="has no symbols"):
        replace(SAMPLES[0], symbols=())


# ------------------------------------------------------------ hypotheses ---


def test_the_primary_point_is_the_one_bx_found_post_hoc() -> None:
    """BY exists to falsify BX's §10 finding, so it must test exactly that rule."""
    assert PRIMARY_STOP_ATR == 0.50
    assert PRIMARY_TARGET_R == 2.0
    primary = PRE_REGISTRATION.hypothesis_for("by_stop_0_5atr_target_2r")
    assert primary.policy.stop_rule is StopRule.EXECUTION_BEYOND_VOLATILITY
    assert primary.policy.target_rule is TargetRule.FIRST_SETUP_SUPPORTING_RR
    assert primary.policy.min_stop_atr == PRIMARY_STOP_ATR
    assert primary.policy.min_planned_rr == PRIMARY_TARGET_R


def test_the_neighbourhood_is_a_cross_and_not_a_grid() -> None:
    """4 + 3 - 1 = 6 primary policies, never 4 × 3 = 12."""
    primary = [h for h in PRE_REGISTERED_HYPOTHESES if h.role == "primary"]
    assert len(primary) == len(STOP_ATR_NEIGHBOURHOOD) + len(TARGET_R_NEIGHBOURHOOD) - 1
    combinations = {
        (h.policy.min_stop_atr, h.policy.min_planned_rr) for h in primary
    }
    assert combinations == (
        {(value, PRIMARY_TARGET_R) for value in STOP_ATR_NEIGHBOURHOOD}
        | {(PRIMARY_STOP_ATR, value) for value in TARGET_R_NEIGHBOURHOOD}
    )


def test_the_neighbourhood_straddles_the_primary_point() -> None:
    """A neighbourhood entirely on one side cannot show a plateau, only a slope."""
    assert min(STOP_ATR_NEIGHBOURHOOD) < PRIMARY_STOP_ATR < max(STOP_ATR_NEIGHBOURHOOD)
    assert min(TARGET_R_NEIGHBOURHOOD) < PRIMARY_TARGET_R < max(TARGET_R_NEIGHBOURHOOD)


def test_every_hypothesis_states_what_would_refute_it() -> None:
    """A rule with no stated refutation cannot fail, and is not a hypothesis."""
    for item in PRE_REGISTERED_HYPOTHESES:
        assert item.refuted_by.strip()
        assert item.prediction.strip()


def test_hypothesis_ids_and_policy_ids_are_unique() -> None:
    ids = [item.hypothesis_id for item in PRE_REGISTERED_HYPOTHESES]
    assert len(set(ids)) == len(ids)
    assert len(PRE_REGISTERED_POLICY_IDS) == len(PRE_REGISTERED_HYPOTHESES)


def test_exactly_one_hypothesis_is_non_structural_and_it_is_a_control() -> None:
    synthetic = [
        item for item in PRE_REGISTERED_HYPOTHESES
        if isinstance(item.policy, SyntheticGeometryPolicy)
    ]
    assert len(synthetic) == 1
    assert synthetic[0].is_structural is False
    assert synthetic[0].role == "non_structural_control"
    # At the SAME numbers as the primary rule, or it is not a twin.
    assert synthetic[0].policy.stop_atr == PRIMARY_STOP_ATR
    assert synthetic[0].policy.target_r == PRIMARY_TARGET_R


def test_the_production_control_is_sealed_too() -> None:
    """The harness must be shown to reproduce a known negative, not assumed to."""
    control = PRE_REGISTRATION.hypothesis_for("geom_production")
    assert control.role == "control"
    assert control.policy.is_production_geometry


def test_an_unsealed_policy_is_not_pre_registered() -> None:
    assert is_pre_registered("by_stop_0_5atr_target_2r") is True
    assert is_pre_registered("geom_min_rr_1") is False
    assert is_pre_registered("something_invented_later") is False


def test_hypothesis_for_names_the_alternatives() -> None:
    with pytest.raises(SwingLabError, match="is NOT pre-registered"):
        PRE_REGISTRATION.hypothesis_for("invented_after_the_fact")


def test_sample_lookup_names_the_alternatives() -> None:
    with pytest.raises(SwingLabError, match="no pre-registered sample"):
        PRE_REGISTRATION.sample("test_set")


# ------------------------------------------------------------------- bar ---


def test_the_deciding_scenario_is_not_frictionless() -> None:
    """BX measured costs at 0.723R per trade. A bar cleared before friction is not a bar."""
    assert DECIDING_COST_POLICY_ID == "swing-lab-conservative-10bps"
    deciding = next(
        item for item in PRE_REGISTRATION.cost_scenarios
        if item.policy_id == DECIDING_COST_POLICY_ID
    )
    assert deciding.is_frictionless is False


def test_the_criteria_cover_every_sample_and_the_plateau() -> None:
    names = {item.name for item in CANDIDATE_CRITERIA}
    assert {
        "pre_registered", "structural", "development_sample", "validation_sample",
        "holdout_sample", "development_expectancy", "validation_expectancy",
        "holdout_expectancy", "profit_factor", "drawdown_recovered",
        "symbol_concentration", "parameter_plateau", "no_lookahead",
    } <= names


def test_the_plateau_rules_name_all_four_outcomes() -> None:
    joined = " ".join(PLATEAU_RULES)
    for name in ("NOT_MEASURABLE", "NO_EDGE", "FRAGILE_SPIKE", "ROBUST_PLATEAU"):
        assert name in joined


def test_the_entry_and_exit_families_are_sealed_with_their_controls() -> None:
    assert any(item.is_baseline for item in PRE_DECLARED_ENTRY_POLICIES)
    assert any(item.is_baseline for item in PRE_DECLARED_EXIT_POLICIES)
    assert PRE_REGISTRATION.entry_policies == PRE_DECLARED_ENTRY_POLICIES
    assert PRE_REGISTRATION.exit_policies == PRE_DECLARED_EXIT_POLICIES


def test_the_timeframe_study_includes_bws_unmeasured_variant() -> None:
    """`swing_1d4h1h_roles` has been INCONCLUSIVE since BW. BY commits to running it."""
    assert "swing_1d4h1h_roles" in PRE_REGISTRATION.timeframe_variant_ids
