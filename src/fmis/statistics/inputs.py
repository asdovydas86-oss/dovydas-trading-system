"""The text boundary: what the CLI hands over, and what it may catch.

Argument strings become domain values here and nowhere else, so `pipeline/cli.py`
stays a parser and a printer. The same separation `fmis.trade_capture.inputs`
and `fmis.paper.inputs` already draw, followed rather than reinvented.

**A refusal is a message, not a traceback.** Every parse failure raises
something in `STATISTICS_ERRORS`, and the CLI catches exactly that tuple. A
caller who mistypes an amount gets a sentence; a caller who hits a genuine defect
gets the traceback, because those two are different and a blanket `except` would
make them the same.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fmis.money import AssetCode, Money
from fmis.persistence import DEFAULT_STORE_ROOT
from fmis.provenance import Absent
from fmis.records import DomainValidationError
from fmis.statistics.models import SamplePolicy, StatisticsError

__all__ = [
    "DEFAULT_STATISTICS_STORE_ROOT",
    "STATISTICS_ERRORS",
    "statistics_store_root",
    "policy_from_text",
    "equity_from_text",
    "as_of_from_text",
    "baseline_from_text",
    "NO_STARTING_EQUITY",
    "NO_EQUITY_BASIS",
    "NO_POINT_IN_TIME_CUT",
]

#: The three absences a statistics run can begin with, worded **once**. The CLI
#: used to build these itself, which put a domain reason in the layer that is
#: supposed to parse strings — and put the same sentence in two files, where
#: they drift. `fmis.trade_capture.inputs`'s own rule, followed.
NO_STARTING_EQUITY = Absent(
    "no starting equity was supplied, and this system records the owner's "
    "opening capital nowhere"
)
NO_EQUITY_BASIS = Absent("no equity basis was supplied for risk percentages")
NO_POINT_IN_TIME_CUT = Absent("no point-in-time cut was requested")

#: Where the store lives when no `--store-root` is given. The persistence
#: package's own default, imported rather than restated — a second constant here
#: would be a second place the store could be looked for.
DEFAULT_STATISTICS_STORE_ROOT = DEFAULT_STORE_ROOT

#: What the CLI may catch from this package. Anything else is a defect.
STATISTICS_ERRORS: tuple[type[Exception], ...] = (
    StatisticsError,
    DomainValidationError,
    ValueError,
    TypeError,
)


def statistics_store_root(raw: str | None) -> Path:
    """The store root a command should read, from a flag or from the default."""
    if raw is None:
        return Path(DEFAULT_STATISTICS_STORE_ROOT).expanduser()
    text = raw.strip()
    if not text:
        raise ValueError("--store-root was given with no path")
    return Path(text).expanduser()


def policy_from_text(raw: str | None) -> SamplePolicy:
    """The sample floor, from a flag or from the stated default.

    A floor of zero is refused rather than accepted as *"no floor"*: an owner
    who wants every rate rendered at any `n` is asking for the guard to be off,
    and turning it off by passing a number that reads as a threshold would hide
    that decision inside what looks like configuration.
    """
    if raw is None:
        return SamplePolicy()
    text = raw.strip()
    try:
        minimum = int(text)
    except ValueError as error:
        raise ValueError(
            f"--minimum-sample must be a whole number, got {raw!r}"
        ) from error
    if minimum < 1:
        raise ValueError(
            "--minimum-sample must be at least 1. A floor of zero is not a "
            "smaller floor, it is no floor at all, and every rate would render "
            "over a single trade"
        )
    return SamplePolicy(minimum_sample=minimum)


def equity_from_text(raw: str | None, *, asset: str, flag: str) -> Money | None:
    """An amount of money from a command line, or `None` when none was given.

    `None` rather than an `Absent` here on purpose: this layer reports whether
    the **owner supplied** a figure, and the composition root turns "they did
    not" into the absence carrying the reason. Two layers each inventing the
    wording would produce two reasons for one gap.
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        raise ValueError(f"{flag} was given with no amount")
    try:
        amount = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"{flag} must be a number, got {raw!r}") from error
    if amount <= 0:
        raise ValueError(
            f"{flag} must be positive; an account that began with nothing has no "
            "baseline to measure a percentage against"
        )
    return Money(amount, AssetCode(asset))


def as_of_from_text(raw: str | None) -> datetime | Absent:
    """A point-in-time cut, or the absence that says none was asked for.

    Timezone-aware or refused. A naive instant here would silently be read as
    the machine's local time, and a statistics page cut at "midnight" would
    then mean a different moment on two laptops.
    """
    if raw is None:
        return NO_POINT_IN_TIME_CUT
    text = raw.strip()
    if not text:
        raise ValueError("--as-of was given with no instant")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(
            "--as-of must be timezone-aware, e.g. 2026-08-01T09:00:00+00:00"
        )
    return parsed


def baseline_from_text(
    raw: str | None, *, asset: str, flag: str, absent: Absent
) -> Money | Absent:
    """An amount, or the stated absence for the baseline it would have been.

    The pair `equity_from_text` and this differ by one thing: that one reports
    whether the owner supplied a figure, and this one turns "they did not" into
    the reason a page prints. Keeping both means the parse and the wording stay
    testable apart.
    """
    amount = equity_from_text(raw, asset=asset, flag=flag)
    return absent if amount is None else amount
