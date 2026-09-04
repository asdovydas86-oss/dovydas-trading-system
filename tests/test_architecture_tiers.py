"""The import-tier invariant, and the bypass an independent reviewer demonstrated.

Milestone CD shipped four architecture guards that each restated the research
boundary in their own terms, and two of them derived their exemption set from the
allowlist they were checking. A reviewer defeated that in two lines plus an empty
file. This module holds the invariant stated once, and a **hostile regression that
reproduces the bypass on a synthetic tree and proves the corrected guard rejects
it**.

Every hostile test here builds its own throwaway package tree under `tmp_path`.
None touches `src/`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from architecture_tiers import (
    PRODUCTION_PACKAGES,
    RESEARCH_PACKAGES,
    RESEARCH_SURFACE,
    assert_tier_partition_is_complete,
    guard_file_is_real,
    importers_of,
    packages_under,
    source_root,
)


def _tree(root: Path, packages: dict[str, str]) -> Path:
    """A synthetic `fmis` tree: package name → the body of its `__init__.py`."""
    fmis = root / "fmis"
    fmis.mkdir(parents=True, exist_ok=True)
    (fmis / "__init__.py").write_text('"""synthetic."""\n', encoding="utf-8")
    for name, body in packages.items():
        package = fmis / name
        package.mkdir(parents=True, exist_ok=True)
        (package / "__init__.py").write_text(body, encoding="utf-8")
    return fmis


class TestTheRealInvariant:
    """One statement, checked against the repository as it actually is."""

    def test_the_only_non_research_importer_of_research_is_the_cli(self) -> None:
        for package in sorted(RESEARCH_PACKAGES):
            offenders = importers_of(package, exclude=RESEARCH_PACKAGES)
            assert offenders <= set(RESEARCH_SURFACE), (
                f"{sorted(offenders - set(RESEARCH_SURFACE))} import "
                f"fmis.{package} from outside the research tier. A research "
                "policy reachable from an engine is a second trading policy in "
                "waiting"
            )

    def test_no_production_package_is_reachable_the_other_way_round(self) -> None:
        """Research may import production; the CLI composes both. Recorded, not
        forbidden — but the count is pinned so a new dependency is visible."""
        assert "pipeline/cli.py" in RESEARCH_SURFACE
        assert len(RESEARCH_SURFACE) == 1

    def test_the_partition_covers_every_package_on_disk(self) -> None:
        assert_tier_partition_is_complete()

    def test_the_two_tiers_are_disjoint(self) -> None:
        assert not (RESEARCH_PACKAGES & PRODUCTION_PACKAGES)

    def test_every_research_package_carries_a_guard_that_really_guards(self) -> None:
        for package in sorted(RESEARCH_PACKAGES):
            guard_file_is_real(package)

    def test_the_classification_matches_the_repository(self) -> None:
        found = packages_under(source_root())
        assert found == RESEARCH_PACKAGES | PRODUCTION_PACKAGES


class TestReviewerCsBypass:
    """**The demonstrated attack, reproduced — and rejected.**

    Reviewer C added `src/fmis/shadow/__init__.py` importing the laboratory, added
    one line to the allowlist, and wrote `tests/test_shadow_architecture.py`
    containing a single docstring. All three guards passed. Each step is
    reproduced below against the corrected invariant.
    """

    def test_step_1_an_unclassified_package_is_caught_by_the_partition(
        self, tmp_path
    ) -> None:
        """The attacker's first move: a new package nobody classified."""
        fmis = _tree(
            tmp_path,
            {
                "swing_lab": '"""lab."""\n',
                "shadow": "from fmis.swing_lab import thing\n",
            },
        )
        # Neither tier names `shadow`, so the partition must refuse it. This is
        # the step the original guards had no equivalent of at all.
        found = packages_under(fmis)
        assert "shadow" in found
        assert "shadow" not in (RESEARCH_PACKAGES | PRODUCTION_PACKAGES)
        with pytest.raises(AssertionError, match="in neither"):
            assert_tier_partition_is_complete(fmis)

    def test_step_2_classifying_it_PRODUCTION_makes_the_import_the_violation(
        self, tmp_path
    ) -> None:
        """If the attacker classifies honestly, the boundary guard fires."""
        fmis = _tree(
            tmp_path,
            {
                "swing_lab": '"""lab."""\n',
                "shadow": "from fmis.swing_lab.preregistration import SAMPLES\n",
            },
        )
        # `shadow` treated as production: it must not import research.
        offenders = importers_of("swing_lab", fmis, exclude={"swing_lab"})
        assert "shadow/__init__.py" in offenders
        assert not offenders <= set(RESEARCH_SURFACE)

    def test_step_3_an_empty_placeholder_guard_is_rejected(self, tmp_path) -> None:
        """The attacker's third move: a guard file with the right name only."""
        guards = tmp_path / "guards"
        guards.mkdir()
        (guards / "test_shadow_architecture.py").write_text(
            '"""placeholder."""\n', encoding="utf-8"
        )
        with pytest.raises(AssertionError, match="guards nothing"):
            guard_file_is_real("shadow", guards)

    def test_step_3b_a_guard_naming_a_boundary_test_but_scanning_nothing_is_rejected(
        self, tmp_path
    ) -> None:
        """A slightly more determined placeholder: the right names, no substance."""
        guards = tmp_path / "guards"
        guards.mkdir()
        (guards / "test_shadow_architecture.py").write_text(
            '"""probe."""\n'
            "def test_no_production_module_imports_this_package():\n"
            "    assert 'fmis.shadow'\n",
            encoding="utf-8",
        )
        with pytest.raises(AssertionError, match="never scans the source tree"):
            guard_file_is_real("shadow", guards)

    def test_step_3c_a_guard_that_scans_but_barely_asserts_is_rejected(
        self, tmp_path
    ) -> None:
        guards = tmp_path / "guards"
        guards.mkdir()
        (guards / "test_shadow_architecture.py").write_text(
            '"""probe."""\n'
            "def test_no_production_module_imports_this_package():\n"
            "    for path in root.rglob('*.py'):\n"
            "        assert 'fmis.shadow'\n",
            encoding="utf-8",
        )
        with pytest.raises(AssertionError, match="is not a guard"):
            guard_file_is_real("shadow", guards)

    def test_NON_VACUITY_a_real_guard_passes_every_check(self) -> None:
        """The rejections above must not be rejecting everything."""
        for package in sorted(RESEARCH_PACKAGES):
            guard_file_is_real(package)

    def test_the_bypass_required_only_an_allowlist_edit_before_the_fix(self) -> None:
        """What made the original guards circular, pinned as prose-free logic.

        The defeated version computed its exemption set from the allowlist it was
        checking, so `exempt = derive(allowlist)` meant `allowlist` constrained
        nothing. This asserts the corrected sets are **independent**: the research
        tier is not derivable from any allowlist, because it is a partition
        against the filesystem.
        """
        found = packages_under(source_root())
        # RESEARCH_PACKAGES cannot be widened without narrowing PRODUCTION_PACKAGES,
        # because their union is pinned to what exists.
        assert RESEARCH_PACKAGES | PRODUCTION_PACKAGES == found
        assert RESEARCH_PACKAGES < found
        assert PRODUCTION_PACKAGES < found


class TestImportersOfIsParsedNotGrepped:
    def test_a_docstring_naming_a_package_is_not_a_dependency(self, tmp_path) -> None:
        fmis = _tree(
            tmp_path,
            {
                "swing_lab": '"""lab."""\n',
                "notes": '"""This module describes fmis.swing_lab in prose."""\n',
            },
        )
        assert importers_of("swing_lab", fmis, exclude={"swing_lab"}) == set()

    def test_an_import_is(self, tmp_path) -> None:
        fmis = _tree(
            tmp_path,
            {"swing_lab": '"""lab."""\n', "notes": "import fmis.swing_lab\n"},
        )
        assert importers_of("swing_lab", fmis, exclude={"swing_lab"}) == {
            "notes/__init__.py"
        }

    def test_a_prefix_collision_is_not_a_match(self, tmp_path) -> None:
        """`fmis.universe_notes` must not count as importing `fmis.universe`."""
        fmis = _tree(
            tmp_path,
            {
                "universe": '"""u."""\n',
                "universe_notes": '"""n."""\n',
                "notes": "from fmis.universe_notes import thing\n",
            },
        )
        assert importers_of("universe", fmis, exclude={"universe"}) == set()
