"""Reading the owner's declaration file. **Financial values only, no defaults.**

Every test uses an isolated `tmp_path`. Nothing here reads, writes or looks for
the owner's real `~/.fmits/risk_policy.json`, and a test that did would make the
suite's result depend on the machine it ran on.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from risk_policy_helpers import MOMENT

from fmis.provenance import Absent
from fmis.risk_policy import (
    DECLARATION_FILENAME,
    RiskPolicyError,
    RiskPolicyFileError,
    declaration_from_mapping,
    declaration_path,
    load_declaration,
)

VALID = {
    "contract_version": 1,
    "equity": {"amount": "10000", "asset": "USDT"},
    "declared_at": "2026-09-06T12:00:00Z",
    "per_trade_fraction": "0.005",
}


def _write(tmp_path: Path, payload: object) -> Path:
    where = tmp_path / DECLARATION_FILENAME
    where.write_text(
        payload if isinstance(payload, str) else json.dumps(payload),
        encoding="utf-8",
    )
    return where


# ---------------------------------------------------------------------------
# Missing is a value; malformed is an error
# ---------------------------------------------------------------------------


def test_no_file_is_a_stated_absence_and_never_a_failure(tmp_path: Path) -> None:
    """The ordinary state of a system whose owner has declared no policy."""
    result = load_declaration(tmp_path / DECLARATION_FILENAME)
    assert isinstance(result, Absent)
    assert "does not exist" in result.reason


def test_the_absence_carries_the_remedy_rather_than_only_the_problem(
    tmp_path: Path,
) -> None:
    result = load_declaration(tmp_path / DECLARATION_FILENAME)
    assert "per_trade_fraction" in result.reason
    assert "contract_version" in result.reason


def test_a_malformed_file_raises_rather_than_reading_as_unconfigured(
    tmp_path: Path,
) -> None:
    """A typo'd capital figure treated as *"no declaration"* would size nothing
    and explain nothing, and the owner would never learn their file was wrong."""
    where = _write(tmp_path, "{not json")
    with pytest.raises(RiskPolicyFileError, match="not valid JSON"):
        load_declaration(where)


def test_a_valid_file_round_trips(tmp_path: Path) -> None:
    declared = load_declaration(_write(tmp_path, VALID))
    assert declared.equity.text == "10000"
    assert declared.equity.asset.code == "USDT"
    assert declared.per_trade_fraction == Decimal("0.005")
    assert declared.declared_at == MOMENT


def test_the_example_in_the_module_is_itself_a_valid_declaration() -> None:
    """Documentation that does not parse is documentation that misleads."""
    from fmis.risk_policy.declaration import EXAMPLE_DECLARATION

    assert declaration_from_mapping(json.loads(EXAMPLE_DECLARATION))


# ---------------------------------------------------------------------------
# The security boundary: unknown keys are refused, never ignored
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["api_key", "secret", "passphrase", "private_key", "exchange_token", "password"],
)
def test_a_credential_shaped_key_is_refused_by_name(tmp_path: Path, key: str) -> None:
    """A loader that skipped unknown keys would make a credential in this file
    *invisible* rather than impossible. It is refused so one cannot sit here
    unnoticed."""
    payload = dict(VALID)
    payload[key] = "whatever"
    with pytest.raises(RiskPolicyFileError, match="unknown key"):
        load_declaration(_write(tmp_path, payload))


def test_the_refusal_says_this_file_is_not_for_credentials(tmp_path: Path) -> None:
    payload = dict(VALID)
    payload["api_key"] = "x"
    with pytest.raises(RiskPolicyFileError, match="not a place for an API key"):
        load_declaration(_write(tmp_path, payload))


def test_the_loader_reads_no_environment_variable_and_no_other_path() -> None:
    """Asserted over the source: this module opens exactly what it is given."""
    import ast
    import inspect

    import fmis.risk_policy.declaration as module

    tree = ast.parse(inspect.getsource(module))
    names = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    for forbidden in ("environ", "getenv", "keyring", "urlopen", "requests", "socket"):
        assert forbidden not in names, forbidden


def test_the_loader_writes_nothing(tmp_path: Path) -> None:
    """A read path that repaired something would make the file's contents
    depend on who looked at it."""
    where = _write(tmp_path, VALID)
    before = where.read_bytes()
    load_declaration(where)
    load_declaration(where)
    assert where.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == [DECLARATION_FILENAME]


# ---------------------------------------------------------------------------
# No default reaches the declaration through the file
# ---------------------------------------------------------------------------


def test_an_omitted_fraction_stays_omitted(tmp_path: Path) -> None:
    payload = {k: v for k, v in VALID.items() if k != "per_trade_fraction"}
    declared = load_declaration(_write(tmp_path, payload))
    assert isinstance(declared.per_trade_fraction, Absent)
    assert declared.states_a_fraction is False


def test_an_explicit_null_fraction_stays_absent(tmp_path: Path) -> None:
    payload = dict(VALID, per_trade_fraction=None)
    declared = load_declaration(_write(tmp_path, payload))
    assert isinstance(declared.per_trade_fraction, Absent)


def test_a_fraction_above_the_ceiling_is_refused_from_the_file(tmp_path: Path) -> None:
    """The ceiling is not negotiable by configuration, and the file cannot get
    past the check the domain makes at construction."""
    payload = dict(VALID, per_trade_fraction="0.05")
    with pytest.raises(RiskPolicyError, match="exceeds the hard ceiling"):
        load_declaration(_write(tmp_path, payload))


# ---------------------------------------------------------------------------
# Floats never enter
# ---------------------------------------------------------------------------


def test_a_json_number_fraction_is_refused_rather_than_converted(
    tmp_path: Path,
) -> None:
    """JSON numbers are binary floating point. A ceiling decided by
    representation error is not a ceiling."""
    where = _write(tmp_path, '{"contract_version": 1, "equity": {"amount": "1", '
                             '"asset": "USDT"}, "declared_at": '
                             '"2026-09-06T12:00:00Z", "per_trade_fraction": 0.005}')
    with pytest.raises(RiskPolicyFileError, match="binary floating point"):
        load_declaration(where)


def test_a_json_number_equity_is_refused_rather_than_converted(tmp_path: Path) -> None:
    where = _write(tmp_path, '{"contract_version": 1, "equity": {"amount": 10000.5, '
                             '"asset": "USDT"}, "declared_at": '
                             '"2026-09-06T12:00:00Z"}')
    with pytest.raises(RiskPolicyFileError, match="binary floating point"):
        load_declaration(where)


# ---------------------------------------------------------------------------
# Everything else that can be wrong, and is named
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload,match",
    [
        ({"contract_version": 1}, "missing"),
        (dict(VALID, contract_version=2), "not the version this build reads"),
        (dict(VALID, contract_version="1"), "must be an integer"),
        (dict(VALID, declared_at="not-a-time"), "not a UTC timestamp"),
        (dict(VALID, declared_at="2026-09-06T12:00:00"), "not a UTC timestamp"),
        (dict(VALID, equity="10000"), "must be an object"),
        (dict(VALID, equity={"amount": "1"}), "missing"),
        (dict(VALID, equity={"amount": "1", "asset": "usdt"}), "not an asset code"),
        (dict(VALID, equity={"amount": "x", "asset": "USDT"}), "not a decimal"),
        (dict(VALID, note=7), "note must be text"),
        ([1, 2, 3], "is a JSON object"),
    ],
)
def test_each_malformed_declaration_is_refused_by_name(
    tmp_path: Path, payload: object, match: str
) -> None:
    with pytest.raises(RiskPolicyFileError, match=match):
        load_declaration(_write(tmp_path, payload))


def test_the_default_path_sits_beside_the_durable_store() -> None:
    """`~/.fmits/`, the convention `fmis.persistence.layout` already holds. Never
    inside the repository, and never in the working tree."""
    from fmis.persistence import DEFAULT_STORE_ROOT

    assert declaration_path().parent == DEFAULT_STORE_ROOT.parent
    assert declaration_path().name == DECLARATION_FILENAME


def test_the_path_is_overridable_so_no_test_touches_the_owners_file(
    tmp_path: Path,
) -> None:
    assert declaration_path(tmp_path) == tmp_path / DECLARATION_FILENAME
