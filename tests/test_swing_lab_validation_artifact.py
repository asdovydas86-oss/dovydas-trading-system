"""Persistence, and the two questions an artifact must be able to answer.

1. *Were these numbers edited?* — `verify_result_digest`, recomputed from the
   stored trades rather than read back from the manifest.
2. *Were they judged against the rules that are in the repository now?* —
   `verify_preregistration_seal`, which is a different question and has a
   different answer, and conflating the two would let a result measured under
   one set of criteria be quoted under another.

Plus the rule every artifact module in this repository obeys: **a measurement is
never overwritten**, because replacing one result with another under the same
name makes two different runs indistinguishable afterwards.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.validation_artifact import (
    ValidationArtifact,
    encode_validation_study,
    read_validation_artifact,
    verify_preregistration_seal,
    verify_result_digest,
    write_validation_study,
)
from fmis.swing_lab.validation_study import VALIDATION_SCHEMA_VERSION

from tests.test_swing_lab_validation_study import _study

_UTC = timezone.utc


@pytest.fixture(scope="module")
def study():
    return _study()


@pytest.fixture(scope="module")
def artifact(study, tmp_path_factory) -> ValidationArtifact:
    path = tmp_path_factory.mktemp("artifacts") / "by.json"
    write_validation_study(study, path)
    return read_validation_artifact(path)


# ------------------------------------------------------------- round trip ---


def test_a_study_survives_a_round_trip_with_its_verdicts(study, artifact) -> None:
    assert artifact.experiment_id == study.manifest.experiment_id
    assert artifact.policy_ids == tuple(item.policy_id for item in study.policies)
    for item in study.policies:
        stored = artifact.policy(item.policy_id)
        assert stored["assessment"]["verdict"] == item.assessment.verdict.value


def test_every_criterion_is_stored_not_only_its_conclusion(study, artifact) -> None:
    """A reader must be able to check the verdict rather than trust a summary."""
    for item in study.policies:
        stored = artifact.policy(item.policy_id)["assessment"]["criteria"]
        assert len(stored) == len(item.assessment.criteria)
        assert [row["name"] for row in stored] == [
            criterion.name for criterion in item.assessment.criteria
        ]


def test_the_plateau_points_are_stored_including_the_failing_ones(artifact) -> None:
    with_plateau = [
        artifact.policy(policy_id)
        for policy_id in artifact.policy_ids
        if artifact.policy(policy_id)["assessment"]["plateau"] is not None
    ]
    assert with_plateau
    for stored in with_plateau:
        points = stored["assessment"]["plateau"]["points"]
        assert len(points) >= 3
        assert sum(1 for point in points if point["is_primary"]) == 1


def test_trades_are_stored_once_and_re_priced_on_read(artifact) -> None:
    """Three copies of one path could drift; one path re-priced cannot."""
    policy_id = artifact.policy_ids[0]
    frictionless = artifact.measurement(policy_id, "development", "swing-lab-frictionless")
    costed = artifact.measurement(
        policy_id, "development", artifact.deciding_cost_policy_id
    )
    assert frictionless["trades"]
    assert costed["trades"] == []
    assert costed["metrics"]["measurable_trades"] == frictionless["metrics"][
        "measurable_trades"
    ]


def test_the_walk_forward_and_decompositions_travel_with_the_study(study, artifact) -> None:
    assert len(artifact.payload["walk_forward"]) == len(study.walk_forward)
    assert {item["name"] for item in artifact.payload["decompositions"]} == {
        item.name for item in study.decompositions
    }


def test_the_limitations_travel_with_the_study(study, artifact) -> None:
    assert artifact.manifest["limitations"] == list(study.manifest.limitations)


def test_no_artifact_approves_trading(artifact) -> None:
    assert artifact.is_approved_for_trading is False


# ---------------------------------------------------------------- digests ---


def test_the_result_digest_verifies_on_an_unedited_artifact(artifact) -> None:
    assert verify_result_digest(artifact) is True


def test_an_edited_trade_fails_the_result_digest(study, tmp_path) -> None:
    """**The whole point of storing a digest.** A hand-changed R must not pass."""
    payload = json.loads(json.dumps(encode_validation_study(study)))
    for policy in payload["policies"]:
        for measurement in policy["measurements"]:
            if measurement["trades"]:
                measurement["trades"][0]["net_r"] = "9.9999"
                break
        else:
            continue
        break
    path = tmp_path / "edited.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert verify_result_digest(read_validation_artifact(path)) is False


def test_a_truncated_trade_list_fails_the_result_digest(study, tmp_path) -> None:
    payload = json.loads(json.dumps(encode_validation_study(study)))
    for policy in payload["policies"]:
        for measurement in policy["measurements"]:
            if len(measurement["trades"]) > 1:
                measurement["trades"] = measurement["trades"][:-1]
                break
        else:
            continue
        break
    path = tmp_path / "short.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert verify_result_digest(read_validation_artifact(path)) is False


def test_the_seal_check_is_a_different_question_from_the_digest(study, artifact) -> None:
    """A fixture study's numbers are intact AND its seal does not match. Both true."""
    assert verify_result_digest(artifact) is True
    assert verify_preregistration_seal(artifact) is False


def test_a_result_measured_under_another_seal_is_flagged_rather_than_hidden(
    study, tmp_path
) -> None:
    payload = json.loads(json.dumps(encode_validation_study(study)))
    payload["manifest"]["preregistration_digest"] = "0" * 64
    path = tmp_path / "reseal.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    artifact = read_validation_artifact(path)
    assert verify_preregistration_seal(artifact) is False
    # The numbers are still readable; only the RULES moved.
    assert artifact.policy_ids


# --------------------------------------------------------------- refusals ---


def test_an_artifact_is_never_overwritten(study, tmp_path) -> None:
    path = tmp_path / "once.json"
    write_validation_study(study, path)
    with pytest.raises(SwingLabError, match="never overwritten"):
        write_validation_study(study, path)


def test_a_different_schema_version_is_refused_and_never_upgraded(tmp_path) -> None:
    path = tmp_path / "old.json"
    path.write_text(
        json.dumps({"schema_version": VALIDATION_SCHEMA_VERSION + 1, "manifest": {}}),
        encoding="utf-8",
    )
    with pytest.raises(SwingLabError, match="not upgraded"):
        read_validation_artifact(path)


def test_a_missing_file_names_itself(tmp_path) -> None:
    with pytest.raises(SwingLabError, match="cannot read"):
        read_validation_artifact(tmp_path / "absent.json")


def test_a_non_json_file_is_refused(tmp_path) -> None:
    path = tmp_path / "junk.json"
    path.write_text("not json at all", encoding="utf-8")
    with pytest.raises(SwingLabError, match="not valid JSON"):
        read_validation_artifact(path)


def test_a_json_array_is_not_an_artifact(tmp_path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(SwingLabError, match="does not hold a validation artifact"):
        read_validation_artifact(path)


def test_an_unknown_policy_id_names_the_alternatives(artifact) -> None:
    with pytest.raises(SwingLabError, match="holds no policy"):
        artifact.policy("invented_later")


def test_an_unknown_measurement_cell_names_what_was_asked_for(artifact) -> None:
    with pytest.raises(SwingLabError, match="holds no measurement"):
        artifact.measurement(artifact.policy_ids[0], "development", "some-other-cost")


def test_encode_refuses_a_non_study() -> None:
    with pytest.raises(TypeError, match="must be a ValidationStudy"):
        encode_validation_study(object())


# --------------------------------------------------------------- chart seam ---
#
# §18: a future instrument page must be able to resolve
# BTCUSDT → historical trade → chart → levels from the artifact alone. A
# `LabTrade` carries prices and an outcome but not WHERE its stop came from, so
# the plan's provenance is carried beside it.


def test_every_trade_has_a_geometry_record_beside_it(artifact) -> None:
    for policy_id in artifact.policy_ids:
        for sample in artifact.sample_names:
            try:
                trades = artifact.trades(policy_id, sample)
            except SwingLabError:
                continue
            assert len(artifact.geometry(policy_id, sample)) == len(trades)


def test_the_geometry_record_aligns_with_its_trade(artifact) -> None:
    """Positional, and asserted — a silent misalignment would look plausible."""
    policy_id = artifact.policy_ids[1]
    trades = artifact.trades(policy_id, "development")
    geometry = artifact.geometry(policy_id, "development")
    assert trades
    for trade, record in zip(trades, geometry, strict=True):
        assert record["setup_id"] == trade.setup_id
        assert record["symbol"] == trade.symbol
        assert record["signal_at"] == trade.signal_at.isoformat()


def test_the_chart_seam_carries_everything_a_chart_needs(artifact) -> None:
    policy_id = artifact.policy_ids[1]
    record = artifact.geometry(policy_id, "development")[0]
    for field in (
        "symbol", "signal_at", "setup_id", "signal_index", "execution_interval",
        "entry", "stop", "target", "stop_provenance", "target_provenance",
        "risk", "reward", "planned_rr", "stop_atr_multiple", "execution_atr",
    ):
        assert field in record, field


def test_a_structural_levels_provenance_names_its_timeframe(artifact) -> None:
    """`4h:lower_low@231` — readable, and not confusable with an invented price."""
    policy_id = artifact.policy_ids[1]
    for record in artifact.geometry(policy_id, "development"):
        assert ":" in record["stop_provenance"]
        assert record["stop_provenance"].split(":")[0] in {"4h", "1d", "1w"}


def test_a_synthetic_levels_provenance_is_unmistakable(artifact) -> None:
    """The non-structural control's levels must never read as market facts."""
    synthetic = [
        policy_id for policy_id in artifact.policy_ids
        if policy_id.startswith("nonstruct_")
    ]
    assert synthetic
    for record in artifact.geometry(synthetic[0], "development"):
        assert record["stop_provenance"].startswith("synthetic:")
        assert record["target_provenance"].startswith("synthetic:")


def test_the_geometry_records_do_not_change_the_result_digest(study, artifact) -> None:
    """The seam is provenance, not a measurement, and must not move the seal."""
    assert verify_result_digest(artifact) is True
    assert artifact.manifest["result_digest"] == study.manifest.result_digest
