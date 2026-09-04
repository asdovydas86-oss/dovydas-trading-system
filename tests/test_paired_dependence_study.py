"""Milestone CD end to end: the observer, offline reproduction and no network.

The reproducibility claim is proven by making a fetch **fatal**, not by asserting
that none happened: every market-data entry point is monkeypatched to raise and
the whole study is then run to completion over a synthetic Milestone BZ capture.

The first class is the one that protects Milestone CA. CD reaches CA's paired
records through an additive observer on CA's own loop, and the whole design rests
on that observer changing nothing. It is asserted field for field rather than
argued for.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmis.paired_dependence.models import PairedDependenceError
from fmis.paired_dependence.preregistration import (
    CD_PREREGISTRATION_DIGEST,
    CD_PRIMARY_FAMILY,
    CD_PRIMARY_SAMPLE,
    PRIMARY_BLOCK_BARS,
)
from fmis.paired_dependence.study import study_from_capture, study_from_rows
from fmis.swing_lab.admission_preregistration import PRIMARY_HORIZON
from fmis.swing_lab.admission_study import study_from_capture as ca_study_from_capture
from test_swing_lab_admission_artifact import (  # noqa: F401 - fixtures
    _capture_payload,
    capture,
    samples,
)

RUN_AT = datetime(2026, 9, 3, tzinfo=timezone.utc)
UNIVERSE = {"development": "primary", "validation": "primary", "holdout": "holdout"}


@pytest.fixture(scope="module")
def cd_study(capture, samples):
    return study_from_capture(
        capture, run_at=RUN_AT, universe_for_sample=UNIVERSE, samples=samples
    )


class TestTheObserverChangesNothing:
    """The additive sink Milestone CD attaches to Milestone CA's own loop."""

    def test_a_study_with_an_observer_is_identical_to_one_without(
        self, capture, samples
    ):
        without = ca_study_from_capture(
            capture, universe_for_sample=UNIVERSE, run_at=RUN_AT, samples=samples
        )
        seen = []
        with_observer = ca_study_from_capture(
            capture,
            universe_for_sample=UNIVERSE,
            run_at=RUN_AT,
            samples=samples,
            record_observer=seen.extend,
        )
        assert with_observer.payload() == without.payload()
        assert seen

    def test_the_observer_sees_only_the_primary_seed_s_records(self, capture, samples):
        seen = []
        study = ca_study_from_capture(
            capture,
            universe_for_sample=UNIVERSE,
            run_at=RUN_AT,
            samples=samples,
            record_observer=seen.extend,
        )
        # Development is the only sample CA re-draws under alternate seeds. If
        # those were observed too, the development row count would be a multiple
        # of the matched count rather than equal to it.
        matched = sum(
            item.matched
            for key, item in study.results.items()
            if key[1] == "development"
        )
        development = [item for item in seen if item.sample == "development"]
        assert len(development) == matched

    def test_the_observer_receives_paired_records_with_ca_s_own_difference(
        self, capture, samples
    ):
        seen = []
        ca_study_from_capture(
            capture,
            universe_for_sample=UNIVERSE,
            run_at=RUN_AT,
            samples=samples,
            record_observer=seen.extend,
        )
        record = seen[0]
        assert record.difference(PRIMARY_HORIZON) == pytest.approx(
            record.admission_forward[PRIMARY_HORIZON]
            - record.control_forward[PRIMARY_HORIZON]
        )


class TestNoNetwork:
    def test_the_whole_study_runs_with_every_fetch_made_fatal(
        self, capture, samples, monkeypatch
    ):
        import fmis.providers.binance as provider
        import fmis.swing_setup.backtest_replay as transport

        def explode(*args, **kwargs):  # pragma: no cover - must never be reached
            raise AssertionError("Milestone CD reached the network")

        monkeypatch.setattr(transport, "fetch_raw_klines", explode)
        for name in dir(provider):
            if name.startswith("fetch") or name.startswith("_request"):
                monkeypatch.setattr(provider, name, explode, raising=False)
        study = study_from_capture(
            capture, run_at=RUN_AT, universe_for_sample=UNIVERSE, samples=samples
        )
        assert study.rows

    def test_NON_VACUITY_the_explosion_really_would_fire(self, monkeypatch):
        # A no-network test is worthless if the patched name is never the one
        # that would be called. This asserts the patch target is live.
        import fmis.swing_setup.backtest_replay as transport

        def explode(*args, **kwargs):
            raise AssertionError("boom")

        monkeypatch.setattr(transport, "fetch_raw_klines", explode)
        with pytest.raises(AssertionError, match="boom"):
            transport.fetch_raw_klines("BTCUSDT", "4h")


class TestTheStudy:
    def test_it_carries_the_seal_it_was_measured_under(self, cd_study):
        assert cd_study.manifest["preregistration_digest"] == CD_PREREGISTRATION_DIGEST
        assert cd_study.manifest["primary_horizon"] == PRIMARY_HORIZON
        assert cd_study.manifest["primary_block_bars"] == PRIMARY_BLOCK_BARS

    def test_it_carries_the_source_capture_s_identity(self, cd_study, capture):
        assert cd_study.manifest["capture_content_digest"] == capture.content_digest

    def test_every_row_names_the_capture_it_came_from(self, cd_study, capture):
        assert {row.capture_content_digest for row in cd_study.rows} == {
            capture.content_digest
        }

    def test_the_headline_is_the_pre_registered_family_and_sample(self, cd_study):
        assert cd_study.headline.family_id == CD_PRIMARY_FAMILY
        assert cd_study.headline.sample == CD_PRIMARY_SAMPLE

    def test_no_panel_pools_two_samples_or_two_families(self, cd_study):
        keys = [(item.family_id, item.sample) for item in cd_study.panels]
        assert len(keys) == len(set(keys))
        for panel in cd_study.panels:
            assert panel.coverage["samples"] == [panel.sample]
            assert panel.coverage["families"] == 1

    def test_an_absent_panel_is_refused_by_name(self, cd_study):
        with pytest.raises(PairedDependenceError, match="no panel"):
            cd_study.panel("ca_null_matched_timing", "production")

    def test_the_whole_sealed_sensitivity_grid_is_reported(self, cd_study):
        from fmis.paired_dependence.preregistration import (
            BLOCK_BARS_GRID,
            CELL_REDUCTIONS,
            WEIGHTINGS,
        )

        cells = cd_study.headline.sensitivity
        assert len(cells) == len(BLOCK_BARS_GRID) * len(CELL_REDUCTIONS) * len(WEIGHTINGS)
        assert {cell.block_bars for cell in cells} == set(BLOCK_BARS_GRID)

    def test_the_verdict_approves_nothing(self, cd_study):
        assert cd_study.assessment.verdict.is_approved_for_trading is False
        assert cd_study.assessment.verdict.earns_forward_test is False

    def test_the_cc_comparison_preserves_cc_s_verdict(self, cd_study):
        assert cd_study.cc_comparison["cc_verdict_preserved"] == "infeasible"

    def test_the_reconstruction_states_it_is_not_ca_s_dataset(self, cd_study):
        assert "re-captured" in cd_study.reconstruction["note"]

    def test_the_payload_carries_the_pre_registration_in_full(self, cd_study):
        payload = cd_study.payload()
        assert payload["preregistration"]["preregistration_id"] == (
            "cd-paired-effect-dependence-v1"
        )


class TestOfflineReproduction:
    def test_re_measuring_from_the_rows_reproduces_every_figure(self, cd_study):
        reproduced = study_from_rows(
            cd_study.rows,
            manifest=cd_study.manifest,
            reconstruction=cd_study.reconstruction,
        )
        original = cd_study.payload()
        again = reproduced.payload()
        # The source marker is the ONE field that legitimately differs: a study
        # re-derived from an artifact must be able to say so.
        assert again["manifest"]["source"] == "artifact"
        del original["manifest"]["source"], again["manifest"]["source"]
        assert again == original

    def test_reproduction_needs_no_capture_at_all(self, cd_study, monkeypatch):
        import fmis.swing_lab.admission_study as ca

        monkeypatch.setattr(
            ca,
            "study_from_capture",
            lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("reproduction replayed the capture")
            ),
        )
        assert study_from_rows(
            cd_study.rows,
            manifest=cd_study.manifest,
            reconstruction=cd_study.reconstruction,
        ).rows

    def test_an_empty_row_set_is_refused_as_a_corrupt_artifact(self):
        with pytest.raises(PairedDependenceError, match="corrupt artifact"):
            study_from_rows([], manifest={}, reconstruction={})


class TestTheDefaultSamplesAreTheSealedOnes:
    def test_the_parameter_cannot_become_a_way_to_re_cut_a_sample(self):
        import inspect

        from fmis.paired_dependence.observations import observations_from_capture

        signature = inspect.signature(observations_from_capture)
        assert signature.parameters["samples"].default is None
        # None means BY's sealed set, asserted by reading what the function reaches
        # for rather than by trusting the docstring.
        source = inspect.getsource(observations_from_capture)
        assert "SAMPLES if samples is None else samples" in source
