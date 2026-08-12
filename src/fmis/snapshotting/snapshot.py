"""`MarketSnapshot` — one immutable bundle of the market facts a decision rested on.

**BG-D4.** `AP` §25.2 requires five things frozen *at decision*: regime per role,
the decision-context state, the evidence summary and conflicts, the setup
classification, and the market context. Three separate objects each need exactly
that bundle — a proposal, an episode, and a journal entry written from a context.
Three consumers each freezing their own copy is Law 1's violation, three times.
This is `AP` §18's own one-assembler argument applied one layer below the AI
boundary.

Four properties, and each is a rule rather than an aspiration.

1. **It is never built from live data at read time.** The same rule `AP` §14.3
   states for a portfolio snapshot, applied to market facts for the identical
   reason: a bundle recomputed in 2031 against a 2031 view of 2026 facts is a
   *different bundle*, and nothing can say which is right.
2. **Every field is present or `Absent(reason)`.** There is no `None` standing in
   for "we could not compute it".
3. **A later policy change cannot relabel it.** The `VersionSet` travels with the
   snapshot, so a regime policy revised in 2029 produces a *visibly different*
   reading rather than silently rewriting a 2026 decision.
4. **A model may read it and may never write it.** It reaches a model only inside
   an AI context package, and no field on it is authored by one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fmis.accounts import MarketId
from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.provenance import Absent, ValueOrigin, decode_maybe, encode_maybe
from fmis.records import (
    ConsumedSource,
    DomainValidationError,
    PayloadDecodeError,
    RecordAudit,
    build_domain_record_id,
    content_digest_over,
    decode_consumed_sources,
    encode_consumed_sources,
    normalize_consumed_sources,
    require_exact_keys,
    require_mapping,
    require_member,
    require_payload_version,
    require_text,
    require_tuple_of,
    require_unmodified,
    require_utc,
    validate_domain_record_id,
)
from fmis.snapshotting.readings import (
    ROLE_ORDER,
    ConflictNote,
    EvidenceFamilyReading,
    IndependenceDisclosure,
    RoleReading,
    SetupReading,
    SnapshotRole,
    SnapshotTrigger,
    SufficiencyReading,
)
from fmis.versioning import VersionSet

__all__ = [
    "MARKET_SNAPSHOT_SCHEMA_VERSION",
    "SUPPORTED_MARKET_SNAPSHOT_VERSIONS",
    "MARKET_SNAPSHOT_TYPE_SLUG",
    "MARKET_SNAPSHOT_KIND",
    "FIELD_GROUP_ORIGINS",
    "MarketSnapshot",
]

MARKET_SNAPSHOT_SCHEMA_VERSION = 1
SUPPORTED_MARKET_SNAPSHOT_VERSIONS = frozenset({1})
MARKET_SNAPSHOT_TYPE_SLUG = "market_snapshot"
MARKET_SNAPSHOT_KIND = "market_snapshot"

#: Provenance is carried **per field group**, not per record — Law 3. A snapshot
#: whose regime reading is `POLICY_DERIVED` and whose bar counts are `MEASURED`
#: cannot honestly claim one origin, and a surface that renders it as one is
#: overstating the parts that were derived.
FIELD_GROUP_ORIGINS: tuple[tuple[str, ValueOrigin], ...] = (
    ("roles", ValueOrigin.MEASURED),
    ("structure", ValueOrigin.MEASURED),
    ("regime", ValueOrigin.POLICY_DERIVED),
    ("sufficiency", ValueOrigin.POLICY_DERIVED),
    ("evidence", ValueOrigin.POLICY_DERIVED),
    ("conflicts", ValueOrigin.MEASURED),
    ("setup", ValueOrigin.POLICY_DERIVED),
    ("provenance", ValueOrigin.MEASURED),
)


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """The market facts a decision rested on, frozen once and referenced by all.

    Immutable in every field. There is no update path and no code that mutates
    one — a change is a different snapshot with a different id.
    """

    market: MarketId
    built_at: datetime
    trigger: SnapshotTrigger
    roles: tuple[RoleReading, ...]
    sufficiency: SufficiencyReading
    evidence: tuple[EvidenceFamilyReading, ...]
    conflicts: tuple[ConflictNote, ...]
    setup: SetupReading | Absent
    independence: IndependenceDisclosure | Absent
    analysis_record_ids: tuple[str, ...]
    consumed_sources: tuple[ConsumedSource, ...]
    limitations: tuple[str, ...]
    decision_window_id: str | Absent
    version_set: VersionSet
    audit: RecordAudit
    schema_version: int = MARKET_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.market, MarketId):
            raise TypeError(
                f"market must be a MarketId, got {type(self.market).__name__}"
            )
        object.__setattr__(self, "built_at", require_utc(self.built_at, "built_at"))
        require_member(self.trigger, SnapshotTrigger, "trigger")
        require_tuple_of(self.roles, RoleReading, "roles", minimum_length=1)
        roles = [reading.role for reading in self.roles]
        if len(set(roles)) != len(roles):
            raise DomainValidationError(
                "a timeframe role must not be read twice; two answers for one "
                "role would let a reader pick the one they preferred"
            )
        ranks = {role: rank for rank, role in enumerate(ROLE_ORDER)}
        if roles != sorted(roles, key=ranks.__getitem__):
            raise DomainValidationError(
                "roles must follow ROLE_ORDER (context, setup, execution); a "
                "stable order is what makes two snapshots diffable"
            )
        if not isinstance(self.sufficiency, SufficiencyReading):
            raise TypeError("sufficiency must be a SufficiencyReading")
        require_tuple_of(self.evidence, EvidenceFamilyReading, "evidence")
        families = [entry.family for entry in self.evidence]
        if len(set(families)) != len(families):
            raise DomainValidationError("an evidence family must not be reported twice")
        require_tuple_of(self.conflicts, ConflictNote, "conflicts")
        if not isinstance(self.setup, (SetupReading, Absent)):
            raise TypeError("setup must be a SetupReading or Absent")
        if not isinstance(self.independence, (IndependenceDisclosure, Absent)):
            raise TypeError("independence must be an IndependenceDisclosure or Absent")
        require_tuple_of(self.analysis_record_ids, str, "analysis_record_ids")
        object.__setattr__(
            self,
            "analysis_record_ids",
            tuple(
                sorted(
                    {
                        require_text(record_id, "analysis record id")
                        for record_id in self.analysis_record_ids
                    }
                )
            ),
        )
        object.__setattr__(
            self,
            "consumed_sources",
            normalize_consumed_sources(self.consumed_sources),
        )
        require_tuple_of(self.limitations, str, "limitations")
        if not isinstance(self.decision_window_id, Absent):
            validate_domain_record_id(self.decision_window_id)
        if not isinstance(self.version_set, VersionSet):
            raise TypeError("version_set must be a VersionSet")
        require_unmodified(self.audit, "MarketSnapshot")
        if self.audit.created_at != self.built_at:
            raise DomainValidationError(
                f"audit.created_at {self.audit.created_at.isoformat()} must equal "
                f"built_at {self.built_at.isoformat()}; a snapshot is created at "
                "the moment it freezes and at no other"
            )
        if self.schema_version not in SUPPORTED_MARKET_SNAPSHOT_VERSIONS:
            raise DomainValidationError(
                f"market snapshot schema_version {self.schema_version} is not one "
                f"this build writes ({sorted(SUPPORTED_MARKET_SNAPSHOT_VERSIONS)})"
            )
        if isinstance(self.setup, SetupReading):
            if self.setup.as_of > self.built_at:
                raise DomainValidationError(
                    f"the setup reading is dated {self.setup.as_of.isoformat()}, "
                    f"after the snapshot was built at {self.built_at.isoformat()}; "
                    "a frozen bundle cannot contain a reading from its own future"
                )
            anchor = self.setup.anchor
            if not isinstance(anchor, Absent) and anchor.market != self.market:
                raise DomainValidationError(
                    f"the setup anchor names market {anchor.market.value} while "
                    f"the snapshot is about {self.market.value}"
                )
        for reading in self.roles:
            if reading.as_of > self.built_at:
                raise DomainValidationError(
                    f"role {reading.role.value} is dated "
                    f"{reading.as_of.isoformat()}, after the snapshot was built"
                )

    # -- projections, computed and never stored -----------------------------

    def role(self, role: SnapshotRole) -> RoleReading | None:
        """One role's reading, or `None` if that role was not read."""
        require_member(role, SnapshotRole, "role")
        for reading in self.roles:
            if reading.role is role:
                return reading
        return None

    @property
    def has_directional_setup(self) -> bool:
        """Whether the frozen reading came down on a side at all."""
        return isinstance(self.setup, SetupReading) and self.setup.direction.is_directional

    @property
    def unmet_requirements(self) -> tuple[str, ...]:
        return tuple(check.requirement for check in self.sufficiency.unmet)

    def stale_inputs(
        self, superseded: dict[str, str]
    ) -> tuple[ConsumedSource, ...]:
        """Which consumed records have since been corrected — AP-D9's answer.

        `superseded` maps a `record_id` to the digest the resolver now reports.
        The snapshot is **never** rewritten and never recomputed; a surface
        renders *"computed from 1 record that has since been corrected"* from
        what this returns. That is the whole of the adopted option, and it costs
        the one `consumed_sources` field Law 8 already requires.
        """
        if not isinstance(superseded, dict):
            raise TypeError(
                f"superseded must be a dict, got {type(superseded).__name__}"
            )
        return tuple(
            source
            for source in self.consumed_sources
            if source.record_id in superseded
            and superseded[source.record_id] != source.content_digest
        )

    # -- identity and serialization -----------------------------------------

    @property
    def digest_basis(self) -> dict[str, Any]:
        """Exactly the semantic content the snapshot id is derived from.

        `audit` is excluded: it is filing metadata equal to `built_at` by
        construction, and ADR-0027 §3's precedent for `archived_at` is that a
        filing timestamp must never affect whether two identical bundles are
        recognised as one.
        """
        return {
            "schema_version": self.schema_version,
            "market": self.market.to_payload(),
            "built_at": encode_timestamp(self.built_at),
            "trigger": self.trigger.value,
            "roles": [reading.to_payload() for reading in self.roles],
            "sufficiency": self.sufficiency.to_payload(),
            "evidence": [entry.to_payload() for entry in self.evidence],
            "conflicts": [note.to_payload() for note in self.conflicts],
            "setup": encode_maybe(self.setup, SetupReading.to_payload),
            "independence": encode_maybe(
                self.independence, IndependenceDisclosure.to_payload
            ),
            "analysis_record_ids": list(self.analysis_record_ids),
            "consumed_sources": encode_consumed_sources(self.consumed_sources),
            "limitations": list(self.limitations),
            "decision_window_id": encode_maybe(self.decision_window_id, str),
            "version_set": self.version_set.to_payload(),
        }

    @property
    def snapshot_id(self) -> str:
        return build_domain_record_id(
            type_slug=MARKET_SNAPSHOT_TYPE_SLUG,
            subject=self.market.value,
            moment=self.built_at,
            digest=content_digest_over(self.digest_basis),
        )

    @property
    def content_digest(self) -> str:
        return content_digest_over(self.digest_basis)

    def as_consumed_source(self) -> ConsumedSource:
        """This snapshot as a Law 8 entry on an artifact that read it."""
        return ConsumedSource(
            record_id=self.snapshot_id,
            content_digest=self.content_digest,
            kind=MARKET_SNAPSHOT_KIND,
        )

    def to_payload(self) -> dict[str, Any]:
        payload = self.digest_basis
        payload["snapshot_id"] = self.snapshot_id
        payload["audit"] = self.audit.to_payload()
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> MarketSnapshot:
        mapping = require_mapping(raw, "market snapshot")
        version = require_payload_version(
            mapping,
            supported=SUPPORTED_MARKET_SNAPSHOT_VERSIONS,
            entity="market snapshot",
        )
        require_exact_keys(
            mapping,
            {
                "schema_version",
                "snapshot_id",
                "market",
                "built_at",
                "trigger",
                "roles",
                "sufficiency",
                "evidence",
                "conflicts",
                "setup",
                "independence",
                "analysis_record_ids",
                "consumed_sources",
                "limitations",
                "decision_window_id",
                "version_set",
                "audit",
            },
            "market snapshot",
        )
        try:
            trigger = SnapshotTrigger(mapping["trigger"])
        except ValueError as error:
            raise PayloadDecodeError(
                f"snapshot trigger {mapping['trigger']!r} is not a known "
                "SnapshotTrigger; an unknown member is a clean rejection"
            ) from error
        decoded = cls(
            market=MarketId.from_payload(mapping["market"], "snapshot market"),
            built_at=decode_timestamp(mapping["built_at"]),
            trigger=trigger,
            roles=tuple(
                RoleReading.from_payload(item)
                for item in _array(mapping["roles"], "roles")
            ),
            sufficiency=SufficiencyReading.from_payload(mapping["sufficiency"]),
            evidence=tuple(
                EvidenceFamilyReading.from_payload(item)
                for item in _array(mapping["evidence"], "evidence")
            ),
            conflicts=tuple(
                ConflictNote.from_payload(item)
                for item in _array(mapping["conflicts"], "conflicts")
            ),
            setup=decode_maybe(mapping["setup"], SetupReading.from_payload),
            independence=decode_maybe(
                mapping["independence"], IndependenceDisclosure.from_payload
            ),
            analysis_record_ids=tuple(
                str(item) for item in _array(mapping["analysis_record_ids"], "ids")
            ),
            consumed_sources=decode_consumed_sources(mapping["consumed_sources"]),
            limitations=tuple(
                str(item) for item in _array(mapping["limitations"], "limitations")
            ),
            decision_window_id=decode_maybe(mapping["decision_window_id"], str),
            version_set=VersionSet.from_payload(mapping["version_set"]),
            audit=RecordAudit.from_payload(mapping["audit"]),
            schema_version=version,
        )
        if mapping["snapshot_id"] != decoded.snapshot_id:
            raise PayloadDecodeError(
                f"snapshot_id {mapping['snapshot_id']!r} does not match the digest "
                f"of the bundle it claims to identify ({decoded.snapshot_id!r})"
            )
        return decoded


def _array(raw: Any, entity: str) -> list[Any]:
    if not isinstance(raw, list):
        raise PayloadDecodeError(
            f"market snapshot {entity} must be a JSON array, got {type(raw).__name__}"
        )
    return raw
