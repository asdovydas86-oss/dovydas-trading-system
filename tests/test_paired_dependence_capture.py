"""The Milestone BZ capture runner — the file that had never been written down.

**The fetch path is deliberately not exercised here.** It reaches a provider, and
a test that mocked the transport deeply enough to run it would be testing the
mock. What IS tested is everything a fetch cannot hide: that the windows are
*read* from Milestone BY's seal rather than chosen, that they are identical to
the ones `run_persistence_experiment` derives, and that every refusal fires
before a single byte is requested.

The coverage gap this leaves is stated in report 0040 §31 rather than papered
over.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fmis.paired_dependence.capture import (
    CA_UNIVERSE_FOR_SAMPLE,
    capture_ca_sources,
    capture_windows,
)
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.preregistration import SAMPLES


class TestTheWindowsAreReadNotChosen:
    def test_both_universes_are_present(self):
        windows = capture_windows()
        assert set(windows) == {"primary", "holdout"}

    def test_primary_is_development_union_validation(self):
        by_name = {item.name: item for item in SAMPLES}
        symbols, start, end = capture_windows()["primary"]
        assert symbols == by_name["development"].symbols
        assert start == min(
            by_name["development"].signal_start, by_name["validation"].signal_start
        )
        assert end == max(
            by_name["development"].signal_end, by_name["validation"].signal_end
        )

    def test_holdout_is_its_own_symbols_over_its_own_window(self):
        by_name = {item.name: item for item in SAMPLES}
        symbols, start, end = capture_windows()["holdout"]
        assert symbols == by_name["holdout"].symbols
        assert start == by_name["holdout"].signal_start
        assert end == by_name["holdout"].signal_end

    def test_they_match_milestone_bz_s_own_derivation(self):
        """The property that makes this a reconstruction and not a new design.

        `run_persistence_experiment` derives the same two windows from the same
        seal. If this module ever drifted from it, CD would be replaying a
        different experiment under BZ's pre-registration digest.
        """
        by_name = {item.name: item for item in SAMPLES}
        development, validation, holdout = (
            by_name["development"], by_name["validation"], by_name["holdout"]
        )
        expected = {
            "primary": (
                development.symbols,
                min(development.signal_start, validation.signal_start),
                max(development.signal_end, validation.signal_end),
            ),
            "holdout": (holdout.symbols, holdout.signal_start, holdout.signal_end),
        }
        assert capture_windows() == expected

    def test_no_symbol_is_added_or_removed(self):
        windows = capture_windows()
        assert len(windows["primary"][0]) == 15
        assert len(windows["holdout"][0]) == 21

    def test_the_sample_to_universe_mapping_is_the_cli_s_own(self):
        assert CA_UNIVERSE_FOR_SAMPLE == {
            "development": "primary",
            "validation": "primary",
            "holdout": "holdout",
        }


class TestRefusalsFireBeforeAnyFetch:
    def test_a_naive_run_at_is_refused(self):
        with pytest.raises(SwingLabError, match="timezone-aware"):
            capture_ca_sources(run_at=datetime(2026, 9, 3))

    def test_a_non_datetime_run_at_is_refused(self):
        with pytest.raises(SwingLabError, match="timezone-aware"):
            capture_ca_sources(run_at="2026-09-03")

    def test_an_unknown_universe_is_refused_by_name(self):
        with pytest.raises(SwingLabError, match="no universe named"):
            capture_ca_sources(
                run_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
                universes=("primary", "sideways"),
            )

    def test_the_refusal_names_what_it_does_know(self):
        with pytest.raises(SwingLabError, match="holdout, primary"):
            capture_ca_sources(
                run_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
                universes=("nonsense",),
            )

    def test_no_transport_is_constructed_before_the_refusal(self, monkeypatch):
        """Non-vacuity: the refusals above must fire BEFORE a fetch is attempted."""
        import fmis.swing_lab.validation_study as study

        def explode(*args, **kwargs):  # pragma: no cover - must not be reached
            raise AssertionError("a refusal let a fetch through")

        monkeypatch.setattr(study, "capture_for_window", explode)
        with pytest.raises(SwingLabError):
            capture_ca_sources(
                run_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
                universes=("nope",),
            )
