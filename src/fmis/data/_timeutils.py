"""Internal shared timestamp validation for the canonical data models.

Enforces the FMITS canonical-time contract: every timestamp stored in a canonical
model must use a *permanent* UTC / fixed-zero-offset timezone — one that cannot
transition through DST or any other offset. This module validates only; it never
converts or mutates timestamps (no ``astimezone``).

A timestamp's offset being zero at one instant is deliberately NOT sufficient: a
regional DST zone such as ``Europe/London`` is zero-offset in winter but +01:00 in
summer, so accepting it by momentary offset would be inconsistent. The rule
therefore proves permanence structurally rather than by sampling the offset:

  * ``datetime.timezone`` instances are fixed-offset by construction (no DST), so
    one is accepted when — and only when — that fixed offset is zero. This covers
    ``timezone.utc`` and ``timezone(timedelta(0))``.
  * ``zoneinfo.ZoneInfo`` instances are accepted only when their canonical IANA
    ``key`` is a known permanent zero-offset zone (a small conservative
    whitelist). Permanence cannot be proven from the ``tzinfo`` interface alone,
    so a whitelist of stable keys is preferred over sampling the offset.
  * Any other (custom or ambiguous) tzinfo is rejected conservatively.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

_ZERO_OFFSET = timedelta(0)

# Permanent, DST-free, zero-offset IANA zones, identified by ZoneInfo.key.
_CANONICAL_UTC_KEYS = frozenset({"UTC", "Etc/UTC", "Etc/GMT", "GMT"})


def _is_canonical_utc(tz: tzinfo) -> bool:
    """Return True only if `tz` is a permanent UTC / fixed-zero-offset timezone."""
    if isinstance(tz, timezone):
        # Fixed-offset by construction: accept iff the fixed offset is zero.
        return tz.utcoffset(None) == _ZERO_OFFSET
    if isinstance(tz, ZoneInfo):
        # Regional zones may be zero-offset only seasonally; accept only zones
        # whose IANA key is permanently zero-offset.
        return tz.key in _CANONICAL_UTC_KEYS
    return False


def validate_utc_timestamp(ts: datetime, *, label: str = "timestamp") -> None:
    """Raise ``ValueError`` unless ``ts`` uses a canonical permanent-UTC timezone.

    Distinguishes two failure modes with distinct messages:
      * naive timestamp -> message contains ``"timezone-aware"``;
      * timezone-aware but non-canonical-UTC -> message contains
        ``"must represent UTC"``.

    Accepts ``timezone.utc``, ``timezone(timedelta(0))``, and permanent
    zero-offset ``ZoneInfo`` zones (``UTC``, ``Etc/UTC``, ``Etc/GMT``, ``GMT``).
    Rejects naive datetimes, non-zero offsets, and regional DST zones (e.g.
    ``Europe/London``) even when their offset happens to be zero at the supplied
    instant. Does not convert or modify ``ts``; callers must have confirmed
    ``ts`` is a ``datetime``.
    """
    if ts.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    if ts.tzinfo is None or not _is_canonical_utc(ts.tzinfo):
        raise ValueError(
            f"{label} must represent UTC (a permanent zero-offset timezone)"
        )
