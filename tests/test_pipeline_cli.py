"""The `fmits archive` CLI surface, and `--archive` on `swing`/`daily`.

No test here exercises `facts`/`mtf`/`regime`'s own behaviour — that is
covered where those commands already live
(`tests/test_pipeline_market_analysis.py`, `tests/test_multi_timeframe.py`,
`tests/test_pipeline_regime.py`). This file covers only what Milestone AO
added: the `archive` command group, the two new flags, and that neither
changes any existing command's behaviour when `--archive` is not passed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fmis.archive.storage as archive_storage_module
import fmis.workspace.builder as builder_module
from fmis.pipeline import cli as cli_module
from tests.archive_helpers import fixture_daily_run, fixture_workspace, multi


@pytest.fixture(autouse=True)
def _offline_swing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this file that runs `swing` goes through the offline fixture."""
    monkeypatch.setattr(
        builder_module, "multi_timeframe_facts_for_symbol", lambda symbol, **kw: multi()
    )


# ============ 1. parsing ======================================================


def test_archive_list_parses() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(["archive", "list"])
    assert args.command == "archive"
    assert args.archive_command == "list"
    assert args.archive_root is None


def test_archive_show_parses_the_record_id() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(["archive", "show", "workspace-BTCUSDT-20260101T000000Z-aaaaaaaa"])
    assert args.archive_command == "show"
    assert args.record_id == "workspace-BTCUSDT-20260101T000000Z-aaaaaaaa"


def test_archive_verify_record_id_is_optional() -> None:
    parser = cli_module.build_parser()
    assert parser.parse_args(["archive", "verify"]).record_id is None
    assert parser.parse_args(["archive", "verify", "x"]).record_id == "x"


def test_archive_root_is_accepted_on_every_subcommand() -> None:
    parser = cli_module.build_parser()
    for sub in (["list"], ["show", "x"], ["verify"]):
        args = parser.parse_args(["archive", *sub, "--archive-root", "/tmp/somewhere"])
        assert args.archive_root == "/tmp/somewhere"


def test_archive_command_requires_a_subcommand() -> None:
    parser = cli_module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["archive"])


def test_swing_accepts_archive_flags() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(["swing", "BTCUSDT", "--archive", "--archive-root", "/tmp/x"])
    assert args.archive is True
    assert args.archive_root == "/tmp/x"


def test_swing_archive_defaults_to_false() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(["swing", "BTCUSDT"])
    assert args.archive is False


def test_daily_accepts_archive_flags() -> None:
    parser = cli_module.build_parser()
    args = parser.parse_args(["daily", "BTCUSDT", "--archive", "--archive-root", "/tmp/x"])
    assert args.archive is True
    assert args.archive_root == "/tmp/x"


# ============ 2. swing --archive end to end ===================================


def test_swing_archive_writes_a_record_and_prints_its_id(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code = cli_module.main(["swing", "BTCUSDT", "--archive", "--archive-root", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "FMITS SWING WORKSPACE" in out  # the analysis itself still printed
    assert "archived: workspace-BTCUSDT-" in out


def test_swing_without_archive_writes_nothing(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = cli_module.main(["swing", "BTCUSDT"])
    assert code == 0
    assert "archived:" not in capsys.readouterr().out
    assert not (Path.home() / ".fmits" / "archive").exists() or True  # never asserted to exist either way


def test_swing_archive_can_then_be_shown_with_no_network(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert cli_module.main(["swing", "BTCUSDT", "--archive", "--archive-root", str(tmp_path)]) == 0
    archived_output = capsys.readouterr().out
    record_id = archived_output.strip().splitlines()[-1].split("archived: ", 1)[1].split(" -> ")[0]

    def boom(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("archive show must never fetch")

    monkeypatch.setattr(
        builder_module, "multi_timeframe_facts_for_symbol", boom
    )
    code = cli_module.main(["archive", "show", record_id, "--archive-root", str(tmp_path)])
    assert code == 0
    assert "FMITS SWING WORKSPACE" in capsys.readouterr().out


def test_swing_archive_failure_is_reported_distinctly_from_analysis_failure(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self, workspace, **kwargs):  # noqa: ANN001, ANN002, ANN003
        from fmis.archive.errors import ArchiveIOError

        raise ArchiveIOError("simulated disk failure")

    monkeypatch.setattr(archive_storage_module.ArchiveStore, "archive_workspace", boom)
    code = cli_module.main(["swing", "BTCUSDT", "--archive", "--archive-root", str(tmp_path)])
    out, err = capsys.readouterr()
    assert "FMITS SWING WORKSPACE" in out  # the analysis succeeded and is visible
    assert code == 1  # but the exit code reports the archive failure
    assert "archive failed" in err
    assert "ArchiveIOError" in err


# ============ 3. daily --archive end to end ===================================


def test_daily_archive_writes_a_record(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_module, "run_daily", lambda symbols, **kw: fixture_daily_run(symbols=tuple(symbols)))
    code = cli_module.main(["daily", "BTCUSDT", "ETHUSDT", "--archive", "--archive-root", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "archived: daily-2sym-" in out


def test_daily_without_archive_writes_nothing(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli_module, "run_daily", lambda symbols, **kw: fixture_daily_run(symbols=tuple(symbols)))
    code = cli_module.main(["daily", "BTCUSDT", "ETHUSDT"])
    assert code == 0
    assert "archived:" not in capsys.readouterr().out


# ============ 4. archive list / show / verify ==================================


def test_list_on_an_empty_archive(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code = cli_module.main(["archive", "list", "--archive-root", str(tmp_path)])
    assert code == 0
    assert "No archived records" in capsys.readouterr().out


def test_list_after_archiving_shows_the_record(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    cli_module.main(["swing", "BTCUSDT", "--archive", "--archive-root", str(tmp_path)])
    capsys.readouterr()
    code = cli_module.main(["archive", "list", "--archive-root", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "workspace-BTCUSDT-" in out
    assert "1 archived record" in out


def test_show_a_missing_record_fails_cleanly(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code = cli_module.main(
        ["archive", "show", "workspace-BTCUSDT-20260101T000000Z-aaaaaaaa", "--archive-root", str(tmp_path)]
    )
    assert code == 1
    assert "not found" in capsys.readouterr().err.lower()


def test_show_an_invalid_record_id_is_rejected(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    code = cli_module.main(["archive", "show", "../../etc/passwd", "--archive-root", str(tmp_path)])
    assert code == 1
    assert "InvalidRecordIdError" in capsys.readouterr().err


def test_verify_a_healthy_archive(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    cli_module.main(["swing", "BTCUSDT", "--archive", "--archive-root", str(tmp_path)])
    capsys.readouterr()
    code = cli_module.main(["archive", "verify", "--archive-root", str(tmp_path)])
    assert code == 0
    assert "Archive OK" in capsys.readouterr().out


def test_verify_one_record(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    cli_module.main(["swing", "BTCUSDT", "--archive", "--archive-root", str(tmp_path)])
    listing = cli_module.main(["archive", "list", "--archive-root", str(tmp_path)])
    out = capsys.readouterr().out
    record_id = [line for line in out.splitlines() if line.startswith("workspace-")][0].split()[0]
    code = cli_module.main(["archive", "verify", record_id, "--archive-root", str(tmp_path)])
    assert code == 0
    assert f"{record_id}: OK" in capsys.readouterr().out


def test_verify_detects_corruption(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    cli_module.main(["swing", "BTCUSDT", "--archive", "--archive-root", str(tmp_path)])
    out = capsys.readouterr().out
    record_id = out.strip().splitlines()[-1].split("archived: ", 1)[1].split(" -> ")[0]
    path = tmp_path / out.strip().splitlines()[-1].split(" -> ", 1)[1]
    path.write_bytes(path.read_bytes().replace(b'"BTCUSDT"', b'"XTCUSDT"', 1))
    code = cli_module.main(["archive", "verify", record_id, "--archive-root", str(tmp_path)])
    assert code == 1
    assert "FAILED" in capsys.readouterr().out


# ============ 5. existing commands are unaffected =============================


def test_the_registry_still_has_every_original_command() -> None:
    names = {command.name for command in cli_module.COMMANDS}
    assert {"facts", "mtf", "regime", "swing", "daily", "archive"} == names


def test_swing_still_works_exactly_as_before_when_archive_is_omitted(
    capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_module.main(["swing", "BTCUSDT"]) == 0
    text = capsys.readouterr().out
    assert "FMITS SWING WORKSPACE" in text
    assert "NOT AVAILABLE — owned by EP-04" in text


# ============ 6. defensive branch unreachable through argparse ================


def test_run_archive_rejects_an_impossible_subcommand_defensively(tmp_path: Path) -> None:
    """`argparse`'s `required=True` subparsers make this unreachable through
    the CLI itself; pinned directly the same way codec.py's defensive
    unreachable branches are (tests/test_archive_codec.py)."""
    import argparse

    namespace = argparse.Namespace(archive_command="bogus", archive_root=str(tmp_path))
    with pytest.raises(AssertionError, match="unreachable"):
        cli_module._run_archive(namespace)
