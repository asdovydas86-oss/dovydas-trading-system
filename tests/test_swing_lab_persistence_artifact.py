"""The persisted BZ capture. **It must fail closed, and it must never refetch.**

Milestone BZ measured BY's own geometry at +0.1906R where BY reported +0.1995R,
and could not close the gap because BY stored no capture. This module's artifact
exists so that never happens again — which makes its *refusals* as load-bearing
as its round-trip.

Two claims are asserted here above all others:

1. **Offline reproduction is exact.** A study measured from a decoded file equals
   a study measured from the live capture, payload for payload — and it runs with
   the network monkeypatched to raise.
2. **Every corruption is caught.** An edited bar, an edited manifest, a wrong
   schema version, a study artifact handed in by mistake, a candidate whose
   symbol has no bars, an observation past the end of its series — each is
   refused **by name**, and none is quietly completed from the provider.
"""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from fmis.paper.models import PriceBar
from fmis.swing_lab.geometry_replay import (
    GeometryCapture,
    capture_geometry_candidates,
)
from fmis.swing_lab.models import SwingLabError
from fmis.swing_lab.persistence_artifact import (
    BZ_CAPTURE_KIND,
    BZ_CAPTURE_SCHEMA_VERSION,
    capture_digest,
    encode_capture,
    read_persistence_capture,
    verify_capture_digest,
    write_persistence_capture,
)
from fmis.swing_lab.persistence_preregistration import (
    BZ_PRE_REGISTRATION,
    BZ_PREREGISTRATION_DIGEST,
)
from fmis.swing_lab.persistence_replay import TimelineCollector
from fmis.swing_lab.persistence_study import study_from_captures
from fmis.swing_lab.variants import BASELINE_VARIANT

from tests.swing_lab_geometry_fixture import (
    LIMIT,
    SYMBOLS,
    all_rows,
    dataset_for,
    segments_for,
    window_for,
)

_UTC = timezone.utc


def _manifest(**overrides) -> dict:
    base = {
        "preregistration_id": BZ_PRE_REGISTRATION.preregistration_id,
        "preregistration_digest": BZ_PREREGISTRATION_DIGEST,
        "captured_at": datetime(2026, 8, 27, tzinfo=_UTC).isoformat(),
        "evaluation_window_bars": 60,
        "candle_limit": LIMIT,
        "deciding_cost_policy_id": "swing-lab-conservative-10bps",
        "provider": {"transport": "test-fixture"},
    }
    base.update(overrides)
    return base


@pytest.fixture(scope="module")
def captured():
    window = window_for()
    collector = TimelineCollector()
    capture = capture_geometry_candidates(
        SYMBOLS, BASELINE_VARIANT,
        window=window, segments=segments_for(window),
        dataset=dataset_for(all_rows()), limit=LIMIT, observer=collector,
    )
    return capture, collector.timelines()


@pytest.fixture(scope="module")
def payload(captured):
    capture, timelines = captured
    return encode_capture({"primary": (capture, timelines)}, manifest=_manifest())


@pytest.fixture()
def written(tmp_path, payload):
    return write_persistence_capture(payload, tmp_path / "capture.json")


class TestRoundTrip:
    def test_the_capture_decodes_to_equal_inputs(self, captured, written) -> None:
        capture, timelines = captured
        artifact = read_persistence_capture(written)
        universe = artifact.universe("primary")

        assert universe.capture.candidates == capture.candidates
        assert universe.capture.bars_by_symbol == capture.bars_by_symbol
        assert universe.capture.admission_variant_id == capture.admission_variant_id
        assert universe.capture.admission_policy_id == capture.admission_policy_id
        assert set(universe.timelines) == set(timelines)
        for symbol, timeline in timelines.items():
            assert universe.timelines[symbol].observations == timeline.observations

    def test_the_digest_verifies_after_a_round_trip(self, written) -> None:
        artifact = read_persistence_capture(written)
        assert verify_capture_digest(artifact)

    def test_the_digest_is_stable_across_two_encodings(self, captured) -> None:
        capture, timelines = captured
        first = encode_capture({"primary": (capture, timelines)}, manifest=_manifest())
        second = encode_capture({"primary": (capture, timelines)}, manifest=_manifest())
        assert first["manifest"]["content_digest"] == second["manifest"]["content_digest"]

    def test_the_gzipped_file_is_byte_reproducible(self, tmp_path, payload) -> None:
        """`mtime=0`, or two identical captures would be two different files."""
        a = write_persistence_capture(payload, tmp_path / "a.json")
        b = write_persistence_capture(payload, tmp_path / "b.json")
        assert a.read_bytes() == b.read_bytes()
        assert a.suffix == ".gz"

    def test_an_uncompressed_capture_round_trips_too(self, tmp_path, payload) -> None:
        path = write_persistence_capture(payload, tmp_path / "plain.json", compress=False)
        assert path.read_bytes()[:2] != b"\x1f\x8b"
        assert verify_capture_digest(read_persistence_capture(path))

    def test_prices_survive_as_exact_decimals(self, captured, written) -> None:
        """A float round-trip would move a stop comparison on the 17th decimal."""
        capture, _ = captured
        artifact = read_persistence_capture(written)
        for symbol, bars in capture.bars_by_symbol.items():
            decoded = artifact.universe("primary").capture.bars_by_symbol[symbol]
            for original, back in zip(bars, decoded, strict=True):
                assert isinstance(back.open, Decimal)
                assert (back.open, back.high, back.low, back.close) == (
                    original.open, original.high, original.low, original.close
                )


class TestOfflineReproduction:
    """**The claim the whole module exists to support.**"""

    def test_a_study_from_the_file_equals_a_study_from_memory(
        self, captured, written
    ) -> None:
        capture, timelines = captured
        artifact = read_persistence_capture(written)
        universe = artifact.universe("primary")

        live = study_from_captures(
            primary=capture, primary_timelines=timelines,
            holdout=None, holdout_timelines={}, causal_proven=True,
        )
        offline = study_from_captures(
            primary=universe.capture, primary_timelines=universe.timelines,
            holdout=None, holdout_timelines={}, causal_proven=True,
        )
        assert live.payload() == offline.payload()

    def test_reproduction_works_with_the_network_disabled(
        self, written, monkeypatch
    ) -> None:
        """No refetch, proven by making a fetch fatal rather than by asserting it."""
        import fmis.swing_setup.backtest_replay as replay

        def explode(*args, **kwargs):  # pragma: no cover - must never run
            raise AssertionError("the offline path reached the network")

        monkeypatch.setattr(replay, "fetch_raw_klines", explode)
        artifact = read_persistence_capture(written)
        universe = artifact.universe("primary")
        study = study_from_captures(
            primary=universe.capture, primary_timelines=universe.timelines,
            holdout=None, holdout_timelines={}, causal_proven=True,
        )
        assert study.comparisons

    def test_the_artifact_module_imports_no_transport(self) -> None:
        """Structural, not behavioural: it cannot refetch because it cannot reach."""
        import ast
        import pathlib

        source = pathlib.Path(
            "src/fmis/swing_lab/persistence_artifact.py"
        ).read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        for banned in (
            "fmis.swing_setup.backtest_replay",
            "fmis.swing_setup.research_harness",
            "fmis.swing_lab.validation_study",
            "urllib",
            "urllib.request",
            "http",
            "socket",
            "requests",
        ):
            assert banned not in imported, f"the capture reader imports {banned}"

    def test_candidate_identity_is_deterministic(self, captured, written) -> None:
        capture, _ = captured
        decoded = read_persistence_capture(written).universe("primary").capture
        assert [c.setup_id for c in decoded.candidates] == [
            c.setup_id for c in capture.candidates
        ]
        assert [c.signal_index for c in decoded.candidates] == [
            c.signal_index for c in capture.candidates
        ]


class TestItFailsClosed:
    @staticmethod
    def _rewrite(path, mutate):
        payload = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
        mutate(payload)
        with open(path, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
                stream.write(
                    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
                )
        return path

    def test_an_edited_bar_breaks_the_digest(self, written) -> None:
        """The edit keeps the bar VALID, so the digest is what catches it.

        An edit that made the bar impossible would be refused by `PriceBar`
        before the digest was ever consulted — a different guard, tested below.
        """
        def mutate(payload):
            symbol = sorted(payload["universes"]["primary"]["bars"])[0]
            row = payload["universes"]["primary"]["bars"][symbol][0]
            payload["universes"]["primary"]["bars"][symbol][0] = [
                row[0], "1", "4", "0.5", "2",
            ]

        artifact = read_persistence_capture(self._rewrite(written, mutate))
        assert not verify_capture_digest(artifact)

    def test_an_impossible_bar_is_refused_before_the_digest(self, written) -> None:
        """Defence in depth: the bar model refuses it at decode time."""
        from fmis.paper.models import PaperRefusedError

        def mutate(payload):
            symbol = sorted(payload["universes"]["primary"]["bars"])[0]
            row = payload["universes"]["primary"]["bars"][symbol][0]
            payload["universes"]["primary"]["bars"][symbol][0] = [
                row[0], row[1], row[2], row[3], "999999",
            ]

        with pytest.raises(PaperRefusedError):
            read_persistence_capture(self._rewrite(written, mutate))

    def test_an_edited_manifest_field_breaks_the_digest(self, written) -> None:
        def mutate(payload):
            payload["manifest"]["evaluation_window_bars"] = 61

        artifact = read_persistence_capture(self._rewrite(written, mutate))
        assert not verify_capture_digest(artifact)

    def test_an_edited_observation_breaks_the_digest(self, written) -> None:
        def mutate(payload):
            timeline = payload["universes"]["primary"]["timeline"]
            symbol = sorted(timeline)[0]
            timeline[symbol][0]["setup_structural_trend"] = "sustained_lower"

        artifact = read_persistence_capture(self._rewrite(written, mutate))
        assert not verify_capture_digest(artifact)

    def test_a_swapped_digest_is_caught(self, written) -> None:
        def mutate(payload):
            payload["manifest"]["content_digest"] = "0" * 64

        artifact = read_persistence_capture(self._rewrite(written, mutate))
        assert not verify_capture_digest(artifact)

    def test_a_future_schema_version_is_refused_not_upgraded(self, written) -> None:
        def mutate(payload):
            payload["schema_version"] = BZ_CAPTURE_SCHEMA_VERSION + 1

        with pytest.raises(SwingLabError, match="NOT upgraded silently"):
            read_persistence_capture(self._rewrite(written, mutate))

    def test_an_older_schema_version_is_refused_too(self, written) -> None:
        def mutate(payload):
            payload["schema_version"] = 0

        with pytest.raises(SwingLabError, match="NOT upgraded silently"):
            read_persistence_capture(self._rewrite(written, mutate))

    def test_a_study_artifact_is_refused_by_kind(self, written) -> None:
        def mutate(payload):
            payload["kind"] = "by-validation-study"

        with pytest.raises(SwingLabError, match="not 'bz-persistence-capture'"):
            read_persistence_capture(self._rewrite(written, mutate))

    @pytest.mark.parametrize(
        "field",
        [
            "preregistration_id", "preregistration_digest", "captured_at",
            "evaluation_window_bars", "deciding_cost_policy_id", "content_digest",
        ],
    )
    def test_a_missing_manifest_field_is_refused(self, written, field) -> None:
        def mutate(payload):
            payload["manifest"].pop(field)

        with pytest.raises(SwingLabError, match=f"no '{field}'"):
            read_persistence_capture(self._rewrite(written, mutate))

    def test_a_missing_section_is_refused(self, written) -> None:
        def mutate(payload):
            payload.pop("universes")

        with pytest.raises(SwingLabError, match="no 'universes' section"):
            read_persistence_capture(self._rewrite(written, mutate))

    def test_a_candidate_without_bars_is_refused_never_refetched(
        self, written
    ) -> None:
        """**The rule that keeps an offline run offline.**"""
        def mutate(payload):
            block = payload["universes"]["primary"]
            missing = block["candidates"][0]["symbol"]
            block["bars"].pop(missing)

        with pytest.raises(SwingLabError, match="refused rather than completed"):
            read_persistence_capture(self._rewrite(written, mutate))

    def test_a_candidate_past_the_end_of_its_series_is_refused(self, written) -> None:
        def mutate(payload):
            payload["universes"]["primary"]["candidates"][0]["signal_index"] = 10**9

        with pytest.raises(SwingLabError, match="but only .* bars were captured"):
            read_persistence_capture(self._rewrite(written, mutate))

    def test_a_candidate_whose_bar_moved_is_refused(self, written) -> None:
        """The index and the timestamp must agree, or the capture is inconsistent."""
        def mutate(payload):
            payload["universes"]["primary"]["candidates"][0]["signal_at"] = (
                datetime(1999, 1, 1, tzinfo=_UTC).isoformat()
            )

        with pytest.raises(SwingLabError, match="but the captured bar opens"):
            read_persistence_capture(self._rewrite(written, mutate))

    def test_a_timeline_for_an_unknown_symbol_is_refused(self, written) -> None:
        def mutate(payload):
            block = payload["universes"]["primary"]
            block["timeline"]["NOPEUSDT"] = []

        with pytest.raises(SwingLabError, match="no NOPEUSDT bars"):
            read_persistence_capture(self._rewrite(written, mutate))

    def test_an_observation_past_the_end_is_refused(self, written) -> None:
        def mutate(payload):
            timeline = payload["universes"]["primary"]["timeline"]
            symbol = sorted(timeline)[0]
            timeline[symbol][0]["bar_index"] = 10**9

        with pytest.raises(SwingLabError, match="but only .* bars were captured"):
            read_persistence_capture(self._rewrite(written, mutate))

    def test_a_truncated_gzip_is_refused(self, written) -> None:
        written.write_bytes(written.read_bytes()[: len(written.read_bytes()) // 2])
        with pytest.raises(SwingLabError, match="truncated or corrupt"):
            read_persistence_capture(written)

    def test_a_non_json_file_is_refused(self, tmp_path) -> None:
        path = tmp_path / "junk.json"
        path.write_bytes(b"not json at all")
        with pytest.raises(SwingLabError, match="not valid JSON"):
            read_persistence_capture(path)

    def test_a_json_array_is_refused(self, tmp_path) -> None:
        path = tmp_path / "arr.json"
        path.write_bytes(b"[1,2,3]")
        with pytest.raises(SwingLabError, match="not a JSON object"):
            read_persistence_capture(path)

    def test_a_missing_file_is_refused(self, tmp_path) -> None:
        with pytest.raises(SwingLabError, match="cannot read capture"):
            read_persistence_capture(tmp_path / "absent.json")

    def test_a_malformed_bar_row_is_refused(self, written) -> None:
        def mutate(payload):
            block = payload["universes"]["primary"]["bars"]
            symbol = sorted(block)[0]
            block[symbol][0] = ["2026-01-01T00:00:00+00:00", "1", "2"]

        with pytest.raises(SwingLabError, match="expected 5"):
            read_persistence_capture(self._rewrite(written, mutate))

    def test_an_unknown_level_side_is_refused(self, written) -> None:
        def mutate(payload):
            candidate = payload["universes"]["primary"]["candidates"][0]
            if candidate["execution_stop_levels"]:
                candidate["execution_stop_levels"][0][1] = "sideways"
            else:  # pragma: no cover - the fixture always produces one
                pytest.skip("no level to corrupt")

        with pytest.raises(SwingLabError, match="unknown level side"):
            read_persistence_capture(self._rewrite(written, mutate))

    def test_an_unknown_universe_is_named_not_guessed(self, written) -> None:
        artifact = read_persistence_capture(written)
        with pytest.raises(SwingLabError, match="holds no universe"):
            artifact.universe("invented")

    def test_an_empty_capture_is_refused_at_encode_time(self) -> None:
        with pytest.raises(SwingLabError, match="at least one universe"):
            encode_capture({}, manifest=_manifest())

    def test_verify_rejects_a_non_artifact(self) -> None:
        with pytest.raises(TypeError, match="PersistenceCaptureArtifact"):
            verify_capture_digest(object())  # type: ignore[arg-type]


class TestProvenance:
    def test_the_manifest_carries_what_an_audit_needs(self, written) -> None:
        manifest = read_persistence_capture(written).manifest
        for field in (
            "preregistration_id", "preregistration_digest", "captured_at",
            "evaluation_window_bars", "candle_limit", "deciding_cost_policy_id",
            "provider", "content_digest",
        ):
            assert field in manifest

    def test_the_seal_travels_inside_the_capture(self, written) -> None:
        artifact = read_persistence_capture(written)
        assert artifact.preregistration_digest == BZ_PREREGISTRATION_DIGEST

    def test_a_capture_taken_under_another_seal_is_still_readable(
        self, captured, tmp_path
    ) -> None:
        """Intact-but-different is a SEPARATE failure from corrupt, and both are stated.

        A capture from another pre-registration decodes fine — its digest is
        valid — and the caller compares the seal itself. Merging the two checks
        would report a foreign experiment as a corrupt file.
        """
        capture, timelines = captured
        foreign = encode_capture(
            {"primary": (capture, timelines)},
            manifest=_manifest(preregistration_digest="f" * 64),
        )
        path = write_persistence_capture(foreign, tmp_path / "foreign.json")
        artifact = read_persistence_capture(path)
        assert verify_capture_digest(artifact)
        assert artifact.preregistration_digest != BZ_PREREGISTRATION_DIGEST

    def test_the_counts_are_reportable(self, written) -> None:
        universe = read_persistence_capture(written).universe("primary")
        assert universe.candidates > 0
        assert universe.observations > universe.candidates
        assert universe.bars > universe.observations

    def test_the_kind_is_declared(self, payload) -> None:
        assert payload["kind"] == BZ_CAPTURE_KIND
        assert payload["schema_version"] == BZ_CAPTURE_SCHEMA_VERSION


class TestPrecisionIsExactNotApproximate:
    """`artifact:prices-decode-as-floats`.

    The fixture's prices survive a float round-trip by luck — ten significant
    digits fit — so a mutant that decoded through `float` was invisible to every
    other test here. A real instrument does not offer that luck: an eighteen-digit
    price loses its tail, and a stop comparison then moves on the digit that
    decides whether a level was reached.

    The bar below is chosen so `Decimal(str(float(x))) != Decimal(x)` for every
    one of its four prices, and the assertion is **textual**, not numeric —
    `Decimal("100") == Decimal("100.0")` is true and would have hidden this.
    """

    #: Eighteen significant digits: more than an IEEE double carries.
    PRECISE = {
        "open": "1234567890.12345678",
        "high": "1234567890.12345679",
        "low": "1234567890.12345677",
        "close": "1234567890.12345678",
    }

    def test_the_chosen_prices_really_do_break_under_float(self) -> None:
        """Non-vacuity: if float round-tripped these, the test below proves nothing."""
        for text in self.PRECISE.values():
            assert Decimal(str(float(text))) != Decimal(text), text

    def _capture(self):
        bars = tuple(
            PriceBar(
                symbol="PRECUSDT", interval="4h",
                open_time=datetime(2026, 1, 1, tzinfo=_UTC) + timedelta(hours=4 * i),
                open=Decimal(self.PRECISE["open"]),
                high=Decimal(self.PRECISE["high"]),
                low=Decimal(self.PRECISE["low"]),
                close=Decimal(self.PRECISE["close"]),
            )
            for i in range(3)
        )
        return GeometryCapture(
            admission_variant_id="v", admission_policy_id="p",
            candidates=(), bars_by_symbol={"PRECUSDT": bars},
        )

    def test_every_price_survives_the_round_trip_exactly(self, tmp_path) -> None:
        capture = self._capture()
        payload = encode_capture({"primary": (capture, {})}, manifest=_manifest())
        path = write_persistence_capture(payload, tmp_path / "precise.json")
        decoded = read_persistence_capture(path).universe("primary").capture

        original = capture.bars_by_symbol["PRECUSDT"]
        back = decoded.bars_by_symbol["PRECUSDT"]
        for left, right in zip(original, back, strict=True):
            # Textual, not numeric: Decimal("100") == Decimal("100.0") is True.
            assert str(right.open) == str(left.open)
            assert str(right.high) == str(left.high)
            assert str(right.low) == str(left.low)
            assert str(right.close) == str(left.close)

    def test_the_digest_is_stable_for_high_precision_prices(self, tmp_path) -> None:
        capture = self._capture()
        first = encode_capture({"primary": (capture, {})}, manifest=_manifest())
        path = write_persistence_capture(first, tmp_path / "p.json")
        decoded = read_persistence_capture(path)
        assert verify_capture_digest(decoded)
