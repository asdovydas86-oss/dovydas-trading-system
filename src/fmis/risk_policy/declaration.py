"""Reading the owner's declaration from their own file. **Financial values only.**

    declaration_path()            ──►  ~/.fmits/risk_policy.json
    load_declaration(path)        ──►  RiskPolicyDeclaration | Absent(reason)

**A file rather than a stored record, and the reason is idempotence.** The
dashboard re-reads on every refresh and a `GET` must change nothing. A declaration
persisted as a config event would make *"the owner looked at the page"* an append
to the store; read from a file it is a value the owner edits and the system only
ever reads. `fmis.risk.RiskRepository` remains the right home for a versioned
budget lineage the day the owner records one — that is a write path, and this
slice adds none.

**Outside the repository, and outside Git.** The path sits beside the durable
store under `~/.fmits/`, which is `fmis.persistence.layout`'s own convention. A
personal capital figure is not repository content, and nothing here writes into
the working tree.

**Exact keys, and that is the security boundary.** The mapping is validated
against a closed set, so a file carrying an API key, a secret, a passphrase or an
exchange credential is *rejected by name* rather than quietly ignored — a config
loader that skipped unknown keys would make a credential in this file invisible
rather than impossible. Nothing here reads an environment variable, opens a
keyring or reaches a venue, and no value in the declaration is a credential.

**Missing is a value, malformed is an error.** A file that is not there is
`Absent(reason)` — the owner has not declared a policy, which is a true and
common state, and every surface above says so. A file that *is* there and cannot
be read is a raised `RiskPolicyFileError`: silently treating a typo'd capital
figure as *"no declaration"* would size nothing and explain nothing.

**No default anywhere.** Not for equity, not for the fraction, and above all not
for the ceiling: `2 %` is a maximum in `models`, and a file that omits
`per_trade_fraction` produces a declaration with no fraction rather than one at
the ceiling.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fmis.money import AssetCode, Money, parse_decimal
from fmis.provenance import Absent
from fmis.records import TradeDomainError, require_utc
from fmis.risk_policy.models import (
    RISK_POLICY_CONTRACT_VERSION,
    RiskPolicyDeclaration,
    RiskPolicyError,
)

__all__ = [
    "DECLARATION_FILENAME",
    "RiskPolicyFileError",
    "declaration_path",
    "load_declaration",
    "declaration_from_mapping",
    "EXAMPLE_DECLARATION",
]

DECLARATION_FILENAME = "risk_policy.json"

#: Every key the file may carry. A closed set: see the module docstring on why an
#: unknown key is a rejection rather than something skipped.
_REQUIRED_KEYS = frozenset({"contract_version", "equity", "declared_at"})
_OPTIONAL_KEYS = frozenset({"per_trade_fraction", "note"})
_EQUITY_KEYS = frozenset({"amount", "asset"})

#: What the owner writes. Printed by the surfaces when no declaration exists, so
#: the remedy is on the page rather than in a document they have to find.
EXAMPLE_DECLARATION = """{
  "contract_version": 1,
  "equity": {"amount": "10000", "asset": "USDT"},
  "declared_at": "2026-09-06T00:00:00Z",
  "per_trade_fraction": "0.005",
  "note": "planning capital only"
}"""


class RiskPolicyFileError(TradeDomainError):
    """The declaration file exists and cannot be read as one."""


def declaration_path(home: Path | str | None = None) -> Path:
    """Where the declaration lives. `~/.fmits/risk_policy.json`.

    ``home`` is a parameter so a test never touches the owner's real file and a
    caller can point at an isolated directory; it defaults to the same
    `~/.fmits` the durable store already uses.
    """
    base = Path.home() / ".fmits" if home is None else Path(home)
    return base / DECLARATION_FILENAME


def _money_from(raw: Any) -> Money:
    if not isinstance(raw, dict):
        raise RiskPolicyFileError(
            "'equity' must be an object with 'amount' and 'asset', e.g. "
            '{"amount": "10000", "asset": "USDT"}. An amount with no asset is '
            "not a value this domain can hold"
        )
    unknown = set(raw) - _EQUITY_KEYS
    if unknown:
        raise RiskPolicyFileError(
            f"'equity' carries unknown key(s) {sorted(unknown)}; it takes exactly "
            "'amount' and 'asset'"
        )
    missing = _EQUITY_KEYS - set(raw)
    if missing:
        raise RiskPolicyFileError(f"'equity' is missing {sorted(missing)}")
    amount = raw["amount"]
    if isinstance(amount, float):
        raise RiskPolicyFileError(
            f"equity amount {amount!r} is a JSON number, which is binary "
            "floating point and cannot represent every decimal amount exactly. "
            'Quote it as text — {"amount": "10000.50", "asset": "USDT"}'
        )
    try:
        exact = parse_decimal(amount, "equity amount")
    except (TradeDomainError, InvalidOperation, ValueError, TypeError) as error:
        raise RiskPolicyFileError(f"equity amount is not a decimal: {error}") from error
    try:
        asset = AssetCode(raw["asset"])
    except (TradeDomainError, TypeError) as error:
        raise RiskPolicyFileError(f"equity asset is not an asset code: {error}") from error
    return Money(exact, asset)


def _fraction_from(raw: Any) -> Decimal:
    if isinstance(raw, float):
        raise RiskPolicyFileError(
            f"per_trade_fraction {raw!r} is a JSON number, which is binary "
            "floating point. A capital-preservation ceiling decided by "
            'representation error is not a ceiling — quote it as text: "0.005"'
        )
    try:
        return parse_decimal(raw, "per_trade_fraction")
    except (TradeDomainError, InvalidOperation, ValueError, TypeError) as error:
        raise RiskPolicyFileError(
            f"per_trade_fraction is not a decimal: {error}. It is a fraction, not "
            'a percentage — 0.5 % is "0.005"'
        ) from error


def declaration_from_mapping(raw: Any) -> RiskPolicyDeclaration:
    """One parsed mapping as a declaration. **Pure: no filesystem, no clock.**

    Separated from `load_declaration` so every validation rule is testable
    without a file, and so the CLI and the dashboard cannot disagree about what a
    valid declaration is.
    """
    if not isinstance(raw, dict):
        raise RiskPolicyFileError(
            f"a risk policy declaration is a JSON object, got "
            f"{type(raw).__name__}"
        )
    unknown = set(raw) - _REQUIRED_KEYS - _OPTIONAL_KEYS
    if unknown:
        raise RiskPolicyFileError(
            f"unknown key(s) {sorted(unknown)} in the risk policy declaration. "
            f"It takes exactly {sorted(_REQUIRED_KEYS | _OPTIONAL_KEYS)}. This "
            "file holds financial parameters only: it is not a place for an API "
            "key, a secret or any exchange credential, and an unrecognised key "
            "is refused rather than ignored so one cannot sit here unnoticed"
        )
    missing = _REQUIRED_KEYS - set(raw)
    if missing:
        raise RiskPolicyFileError(
            f"the risk policy declaration is missing {sorted(missing)}"
        )
    version = raw["contract_version"]
    if not isinstance(version, int) or isinstance(version, bool):
        raise RiskPolicyFileError(
            f"contract_version must be an integer, got {version!r}"
        )
    if version != RISK_POLICY_CONTRACT_VERSION:
        raise RiskPolicyFileError(
            f"contract_version {version} is not the version this build reads "
            f"({RISK_POLICY_CONTRACT_VERSION}). The contract is versioned so a "
            "figure can always be traced to the policy that produced it"
        )
    declared_raw = raw["declared_at"]
    if not isinstance(declared_raw, str):
        raise RiskPolicyFileError(
            f"declared_at must be an ISO-8601 UTC timestamp string, got "
            f"{declared_raw!r}"
        )
    try:
        from datetime import datetime

        declared_at = require_utc(
            datetime.fromisoformat(declared_raw.replace("Z", "+00:00")), "declared_at"
        )
    except (TradeDomainError, ValueError) as error:
        raise RiskPolicyFileError(
            f"declared_at is not a UTC timestamp: {error}. It dates the capital "
            "figure a size rests on, so a surface can state how old that figure is"
        ) from error
    fraction: Decimal | Absent
    if raw.get("per_trade_fraction") is None:
        fraction = Absent(
            "the declaration states no per_trade_fraction. No fraction is "
            "assumed in its place: the specification states a ceiling and no "
            "default, and sizing at the ceiling would make the ceiling the target"
        )
    else:
        fraction = _fraction_from(raw["per_trade_fraction"])
    note = raw.get("note")
    if note is not None and not isinstance(note, str):
        raise RiskPolicyFileError(f"note must be text, got {type(note).__name__}")
    try:
        return RiskPolicyDeclaration(
            equity=_money_from(raw["equity"]),
            declared_at=declared_at,
            per_trade_fraction=fraction,
            note=Absent("no note") if note is None else note,
            contract_version=version,
        )
    except RiskPolicyError:
        # Raised straight through. The ceiling refusal is the one message the
        # owner most needs to read verbatim, and wrapping it in a file error
        # would bury *"this exceeds the hard ceiling"* under *"could not read
        # your file"*.
        raise


def load_declaration(path: Path | str | None = None) -> RiskPolicyDeclaration | Absent:
    """The owner's declaration, or the stated reason there is none.

    Returns `Absent(reason)` when no file exists — the ordinary state of a system
    whose owner has not declared a policy — and raises `RiskPolicyFileError` when
    a file exists and cannot be read as a declaration. The two are different
    facts with different remedies, and a loader that returned the same value for
    both would answer *"you have not configured this"* to an owner who had, and
    made a typo.
    """
    where = declaration_path() if path is None else Path(path)
    try:
        text = where.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Absent(
            f"no risk policy is declared: {where} does not exist. Nothing is "
            "assumed in its place — no capital, and above all no risk fraction. "
            f"To declare one, write:\n{EXAMPLE_DECLARATION}"
        )
    except OSError as error:
        raise RiskPolicyFileError(
            f"the risk policy declaration at {where} could not be read: {error}"
        ) from error
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise RiskPolicyFileError(
            f"the risk policy declaration at {where} is not valid JSON: {error}"
        ) from error
    return declaration_from_mapping(parsed)
