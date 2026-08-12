"""`SearchCriteria` — the one filter shape every repository's `search` accepts.

One object rather than a dozen keyword arguments per repository, because the axes
are the same everywhere and nine slightly different signatures would be nine
places to forget one.

**Two time axes, and conflating them is the mistake this shape exists to prevent.**
`since`/`until` filter on `occurred_at` — when the thing happened. `known_since`/
`known_until` filter on `written_at` — when FMITS learned of it. A trade backfilled
today for a fill in 2024 answers *yes* to "happened in 2024" and *no* to "was known
in 2024", and a report that cannot tell those apart will describe a portfolio the
owner never actually had.

Every field is optional and an empty `SearchCriteria()` matches everything. That is
deliberate: a filter object whose default excludes rows is a filter object that
silently truncates the first listing anybody writes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from fmis.records import require_int, require_optional_text, require_optional_utc

from fmis.persistence.errors import PersistenceError
from fmis.persistence.index import IndexEntry
from fmis.persistence.kinds import RecordKind

__all__ = ["SearchCriteria"]


@dataclass(frozen=True, slots=True)
class SearchCriteria:
    """What to include. Everything not stated is not filtered on."""

    kinds: tuple[RecordKind, ...] = ()
    book: str | None = None
    market: str | None = None
    account: str | None = None
    lineage_key: str | None = None
    #: On `occurred_at` — the instant the record describes.
    since: datetime | None = None
    until: datetime | None = None
    #: On `written_at` — the instant FMITS filed it.
    known_since: datetime | None = None
    known_until: datetime | None = None
    #: `None` includes both; `False` keeps only records nothing supersedes.
    superseded: bool | None = None
    limit: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kinds, tuple):
            raise TypeError("kinds must be a tuple of RecordKind")
        for kind in self.kinds:
            if not isinstance(kind, RecordKind):
                raise TypeError("kinds must be a tuple of RecordKind")
        if len(set(self.kinds)) != len(self.kinds):
            raise PersistenceError("a kind must not be listed twice")
        for name in ("book", "market", "account", "lineage_key"):
            object.__setattr__(
                self, name, require_optional_text(getattr(self, name), name)
            )
        for name in ("since", "until", "known_since", "known_until"):
            object.__setattr__(
                self, name, require_optional_utc(getattr(self, name), name)
            )
        for lower, upper in (("since", "until"), ("known_since", "known_until")):
            low = getattr(self, lower)
            high = getattr(self, upper)
            if low is not None and high is not None and high < low:
                raise PersistenceError(
                    f"{upper} {high.isoformat()} precedes {lower} {low.isoformat()}"
                )
        if self.superseded is not None and not isinstance(self.superseded, bool):
            raise TypeError("superseded must be a bool or None")
        if self.limit is not None:
            require_int(self.limit, "limit", minimum=1)

    def narrowed(self, **overrides: object) -> SearchCriteria:
        """This criteria with some axes replaced, every other axis carried through.

        A field-by-field copy was the first implementation, and a mutation sweep
        showed why it was the wrong one: eleven of its twelve lines could be
        deleted without any test noticing, because *forgetting to forward an axis*
        looks exactly like *the caller not setting it*. `dataclasses.replace`
        cannot forget a field.
        """
        return replace(
            self, **{name: value for name, value in overrides.items() if value is not None}
        )

    @property
    def filters_supersession(self) -> bool:
        """Whether applying this needs the store's successor map.

        Read by `search` so the common case never pays for a lineage walk.
        """
        return self.superseded is not None

    def matches(self, entry: IndexEntry) -> bool:
        """Every axis except supersession, which needs more than one row to decide."""
        if self.kinds and entry.kind not in self.kinds:
            return False
        for wanted, actual in (
            (self.book, entry.book),
            (self.market, entry.market),
            (self.account, entry.account),
        ):
            if wanted is not None and actual != wanted:
                return False
        if self.lineage_key is not None and entry.lineage_key != self.lineage_key:
            return False
        if self.since is not None and entry.occurred_at < self.since:
            return False
        if self.until is not None and entry.occurred_at > self.until:
            return False
        if self.known_since is not None and entry.written_at < self.known_since:
            return False
        if self.known_until is not None and entry.written_at > self.known_until:
            return False
        return True
