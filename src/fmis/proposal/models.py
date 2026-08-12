"""`OpportunityProposal` — what was suggested, by whom, on what evidence.

The brief calls this *Opportunity*. The data model is explicit that there is no
separate `Opportunity` object and states why in one line: **an opportunity that
was never proposed left no trace, and an opportunity that was proposed *is* a
proposal.** One object, three possible authors — a deterministic policy, the
owner, or a model — so all three are directly comparable, which is the only way
*"did the AI improve my decisions?"* is ever answerable.

**Everything on this record is immutable, and there is no code path that mutates
one.** Everything that "changes" is an appended lifecycle event (`lifecycle.py`).
A withdrawn proposal is `WITHDRAWN_BY_AUTHOR`; a corrected one is a *new*
proposal citing `supersedes`.

**Rejected proposals are never deleted.** Discarding them makes AI value
unmeasurable and conditions the corpus on acceptance, which makes every statistic
about proposal quality circular.

The four creation rules, each enforced in `__post_init__` rather than documented:

1. **Both directions are always assessed.** `direction` records which side it came
   down on; the case for each side is kept *separately* and never collapsed into
   one score. `NO_TRADE` is a valid direction.
2. **`supporting_evidence` and `opposing_evidence` are both required and both
   non-empty.** A proposal with no case against it is not a proposal; it is an
   advertisement.
3. **No fabricated price.** Stop, invalidation and every target are real,
   already-detected levels reused by reference, or explicitly `Absent`.
   Risk/reward is a pair, not a stored quotient. Probability is `UNCALIBRATED_PROBABILITY`
   until a resolved-episode cohort earns otherwise.
4. **One live proposal per anchor** — implemented in `lifecycle.admit`, keyed on
   the `MEASURED` anchor rather than on any policy-derived grouping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from fmis.accounts import Book, MarketId
from fmis.archive.json_safe import decode_timestamp, encode_timestamp
from fmis.provenance import Absent, ValueOrigin, decode_maybe, encode_maybe
from fmis.records import (
    ConsumedSource,
    DomainValidationError,
    PayloadDecodeError,
    RecordAudit,
    TradeDomainError,
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
from fmis.snapshotting import (
    Anchor,
    LevelReading,
    RiskRewardReading,
    TradeDirection,
)
from fmis.versioning import VersionSet

__all__ = [
    "ProposalError",
    "PROPOSAL_SCHEMA_VERSION",
    "SUPPORTED_PROPOSAL_VERSIONS",
    "PROPOSAL_TYPE_SLUG",
    "PROPOSAL_KIND",
    "UNCALIBRATED_PROBABILITY",
    "ProposalAuthor",
    "StatedConfidence",
    "ModelAttribution",
    "DirectionalCase",
    "DirectionalAssessment",
    "EvidenceCitation",
    "OpportunityProposal",
]

PROPOSAL_SCHEMA_VERSION = 1
SUPPORTED_PROPOSAL_VERSIONS = frozenset({1})
PROPOSAL_TYPE_SLUG = "proposal"
PROPOSAL_KIND = "opportunity_proposal"

#: The only value `probability` may hold on a proposal. A calibrated probability
#: is earned from a resolved-episode cohort or it does not exist, and back-filling
#: one onto a past proposal would be a retro-fitted field that changes what the
#: record says the author believed.
UNCALIBRATED_PROBABILITY = "UNCALIBRATED_PROBABILITY"

_NUMERIC_LOOKING = re.compile(r"^[\s+\-]?[0-9][0-9\s.,%]*$")


class ProposalError(TradeDomainError):
    """Base class for every proposal failure."""


class ProposalAuthor(Enum):
    """Who suggested it. The same record for all three, so all three compare."""

    DETERMINISTIC_POLICY = "deterministic_policy"
    OWNER = "owner"
    MODEL = "model"


#: What each author's output *is*, as a `ValueOrigin`. A model's proposal is
#: `INTERPRETED` and is never an input to a computation; the owner's is `ASSERTED`
#: and can simply be wrong; a policy's is `POLICY_DERIVED` and is wrong only if the
#: policy is.
AUTHOR_ORIGINS: dict[ProposalAuthor, ValueOrigin] = {
    ProposalAuthor.DETERMINISTIC_POLICY: ValueOrigin.POLICY_DERIVED,
    ProposalAuthor.OWNER: ValueOrigin.ASSERTED,
    ProposalAuthor.MODEL: ValueOrigin.INTERPRETED,
}


@dataclass(frozen=True, slots=True)
class StatedConfidence:
    """The author's own word for how sure they are — **and it is not a probability**.

    Kept as a label from the owner's vocabulary rather than a number, and a
    numeric-looking label is *rejected at construction*. `AP` §20.6 names
    confidence-mistaken-for-probability as *"the most likely way this system would
    produce false authority"*, and a free-text field accepting `"0.7"` is exactly
    how that happens: the string looks like a judgement, sorts like a number, and
    ends up averaged.

    The calibrated probability is a separate field with a different type on the
    proposal, `Absent` until earned. Two fields, two types, so they cannot be
    confused.
    """

    label: str

    def __post_init__(self) -> None:
        text = require_text(self.label, "stated confidence")
        if _NUMERIC_LOOKING.fullmatch(text):
            raise DomainValidationError(
                f"stated confidence {text!r} looks like a number. Stated "
                "confidence is the author's own word and is not a probability; "
                "a calibrated probability is a separate field, Absent until a "
                "resolved-episode cohort earns it"
            )
        object.__setattr__(self, "label", text)

    def __str__(self) -> str:
        return self.label


@dataclass(frozen=True, slots=True)
class ModelAttribution:
    """Everything needed to reproduce the *conditions* of a model's proposal.

    The output itself is not reproducible and this domain does not claim it is.
    What is reproducible is the exact input (`context_package_id` +
    `context_digest`), the model and template identity, and the build — which is
    what makes *"is the 2029 model better than the 2027 one, on my markets, in my
    regimes?"* a cohort query rather than an opinion.
    """

    model_id: str
    model_version: str
    template_id: str
    template_version: str
    context_package_id: str
    context_digest: str

    def __post_init__(self) -> None:
        for name in (
            "model_id",
            "model_version",
            "template_id",
            "template_version",
            "context_package_id",
            "context_digest",
        ):
            object.__setattr__(self, name, require_text(getattr(self, name), name))
        if not self.context_digest.startswith("sha256:"):
            raise DomainValidationError(
                "context_digest must be a 'sha256:<hex>' string; a model's input "
                "is checkable or the attribution is decoration"
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "template_id": self.template_id,
            "template_version": self.template_version,
            "context_package_id": self.context_package_id,
            "context_digest": self.context_digest,
        }

    @classmethod
    def from_payload(cls, raw: Any) -> ModelAttribution:
        mapping = require_mapping(raw, "model attribution")
        require_exact_keys(
            mapping,
            {
                "model_id",
                "model_version",
                "template_id",
                "template_version",
                "context_package_id",
                "context_digest",
            },
            "model attribution",
        )
        return cls(**{key: str(value) for key, value in mapping.items()})


@dataclass(frozen=True, slots=True)
class DirectionalCase:
    """The case for one side, on its own terms.

    Never a score. `factors` are the named reasons; `statement` is the plain
    reading. Two of these live on every proposal and they are never combined,
    because a single net number is precisely what hides that the case against was
    strong.
    """

    direction: TradeDirection
    factors: tuple[str, ...]
    statement: str

    def __post_init__(self) -> None:
        require_member(self.direction, TradeDirection, "direction")
        if not self.direction.is_directional:
            raise DomainValidationError(
                "a directional case is made for LONG or SHORT; NO_TRADE is the "
                "conclusion, not a side to argue"
            )
        require_tuple_of(self.factors, str, "factors")
        object.__setattr__(
            self,
            "factors",
            tuple(require_text(factor, "factor") for factor in self.factors),
        )
        object.__setattr__(self, "statement", require_text(self.statement, "statement"))

    def to_payload(self) -> dict[str, Any]:
        return {
            "direction": self.direction.value,
            "factors": list(self.factors),
            "statement": self.statement,
        }

    @classmethod
    def from_payload(cls, raw: Any) -> DirectionalCase:
        mapping = require_mapping(raw, "directional case")
        require_exact_keys(mapping, {"direction", "factors", "statement"}, "case")
        factors = mapping["factors"]
        if not isinstance(factors, list):
            raise PayloadDecodeError("directional case factors must be a JSON array")
        return cls(
            direction=_member(TradeDirection, mapping["direction"], "case direction"),
            factors=tuple(str(item) for item in factors),
            statement=str(mapping["statement"]),
        )


@dataclass(frozen=True, slots=True)
class DirectionalAssessment:
    """Both sides, kept apart.

    `SPEC` §7's strongest-opposing-case obligation, moved from review time to
    **proposal** time. There is no `net`, no `score` and no `winner` field here —
    the winner is `OpportunityProposal.direction`, stated once, beside the two
    cases that produced it rather than instead of them.
    """

    long_case: DirectionalCase
    short_case: DirectionalCase

    def __post_init__(self) -> None:
        for name, expected in (
            ("long_case", TradeDirection.LONG),
            ("short_case", TradeDirection.SHORT),
        ):
            value = getattr(self, name)
            if not isinstance(value, DirectionalCase):
                raise TypeError(f"{name} must be a DirectionalCase")
            if value.direction is not expected:
                raise DomainValidationError(
                    f"{name} argues the {value.direction.value} side; both sides "
                    "are assessed and neither may stand in for the other"
                )

    def case_for(self, direction: TradeDirection) -> DirectionalCase | None:
        require_member(direction, TradeDirection, "direction")
        if direction is TradeDirection.LONG:
            return self.long_case
        if direction is TradeDirection.SHORT:
            return self.short_case
        return None

    def to_payload(self) -> dict[str, Any]:
        return {
            "long_case": self.long_case.to_payload(),
            "short_case": self.short_case.to_payload(),
        }

    @classmethod
    def from_payload(cls, raw: Any) -> DirectionalAssessment:
        mapping = require_mapping(raw, "directional assessment")
        require_exact_keys(mapping, {"long_case", "short_case"}, "assessment")
        return cls(
            long_case=DirectionalCase.from_payload(mapping["long_case"]),
            short_case=DirectionalCase.from_payload(mapping["short_case"]),
        )


@dataclass(frozen=True, slots=True, order=True)
class EvidenceCitation:
    """One piece of evidence, named with the layer that produced it."""

    family: str
    statement: str
    source: str

    def __post_init__(self) -> None:
        for name in ("family", "statement", "source"):
            object.__setattr__(self, name, require_text(getattr(self, name), name))

    def to_payload(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "statement": self.statement,
            "source": self.source,
        }

    @classmethod
    def from_payload(cls, raw: Any) -> EvidenceCitation:
        mapping = require_mapping(raw, "evidence citation")
        require_exact_keys(mapping, {"family", "statement", "source"}, "citation")
        return cls(
            family=str(mapping["family"]),
            statement=str(mapping["statement"]),
            source=str(mapping["source"]),
        )


@dataclass(frozen=True, slots=True)
class OpportunityProposal:
    """One suggestion, scoreable whether or not it was taken."""

    created_at: datetime
    valid_until: datetime
    author: ProposalAuthor
    market: MarketId
    book: Book
    direction: TradeDirection
    directional_assessment: DirectionalAssessment
    entry_conditions: tuple[str, ...]
    invalidation: LevelReading | Absent
    stop: LevelReading | Absent
    take_profit_structure: tuple[LevelReading, ...]
    risk_reward: RiskRewardReading | Absent
    stated_confidence: StatedConfidence
    supporting_evidence: tuple[EvidenceCitation, ...]
    opposing_evidence: tuple[EvidenceCitation, ...]
    unavailable_evidence: tuple[str, ...]
    market_snapshot_id: str
    anchor: Anchor | Absent
    counterfactual_assumption_version: str
    version_set: VersionSet
    audit: RecordAudit
    consumed_sources: tuple[ConsumedSource, ...] = ()
    policy_id: str | Absent = field(default_factory=lambda: Absent("not policy-authored"))
    model: ModelAttribution | Absent = field(
        default_factory=lambda: Absent("not model-authored")
    )
    supersedes: str | Absent = field(default_factory=lambda: Absent("supersedes nothing"))
    calibrated_probability: Absent = field(
        default_factory=lambda: Absent(
            "no resolved-episode cohort has earned a calibrated probability"
        )
    )
    probability: str = UNCALIBRATED_PROBABILITY
    schema_version: int = PROPOSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))
        object.__setattr__(
            self, "valid_until", require_utc(self.valid_until, "valid_until")
        )
        if self.valid_until <= self.created_at:
            raise DomainValidationError(
                f"valid_until {self.valid_until.isoformat()} is not after "
                f"created_at {self.created_at.isoformat()}; a suggestion that "
                "expires before it exists cannot be acted on or scored"
            )
        require_member(self.author, ProposalAuthor, "author")
        if not isinstance(self.market, MarketId):
            raise TypeError("market must be a MarketId")
        require_member(self.book, Book, "book")
        require_member(self.direction, TradeDirection, "direction")
        if not isinstance(self.directional_assessment, DirectionalAssessment):
            raise TypeError("directional_assessment must be a DirectionalAssessment")
        require_tuple_of(self.entry_conditions, str, "entry_conditions")
        for name in ("invalidation", "stop"):
            value = getattr(self, name)
            if not isinstance(value, (LevelReading, Absent)):
                raise TypeError(f"{name} must be a LevelReading or Absent")
        require_tuple_of(self.take_profit_structure, LevelReading, "take_profit_structure")
        if not isinstance(self.risk_reward, (RiskRewardReading, Absent)):
            raise TypeError("risk_reward must be a RiskRewardReading or Absent")
        if not isinstance(self.stated_confidence, StatedConfidence):
            raise TypeError("stated_confidence must be a StatedConfidence")
        require_tuple_of(
            self.supporting_evidence, EvidenceCitation, "supporting_evidence"
        )
        require_tuple_of(self.opposing_evidence, EvidenceCitation, "opposing_evidence")
        require_tuple_of(self.unavailable_evidence, str, "unavailable_evidence")
        validate_domain_record_id(self.market_snapshot_id)
        if not isinstance(self.anchor, (Anchor, Absent)):
            raise TypeError("anchor must be an Anchor or Absent")
        object.__setattr__(
            self,
            "counterfactual_assumption_version",
            require_text(
                self.counterfactual_assumption_version,
                "counterfactual_assumption_version",
            ),
        )
        if not isinstance(self.version_set, VersionSet):
            raise TypeError("version_set must be a VersionSet")
        require_unmodified(self.audit, "OpportunityProposal")
        if self.audit.created_at != self.created_at:
            raise DomainValidationError(
                "audit.created_at must equal created_at; a proposal is created at "
                "the moment it is authored and at no other"
            )
        object.__setattr__(
            self, "consumed_sources", normalize_consumed_sources(self.consumed_sources)
        )
        if not isinstance(self.policy_id, Absent):
            object.__setattr__(self, "policy_id", require_text(self.policy_id, "policy_id"))
        if not isinstance(self.model, (ModelAttribution, Absent)):
            raise TypeError("model must be a ModelAttribution or Absent")
        if not isinstance(self.supersedes, Absent):
            validate_domain_record_id(self.supersedes)
        if not isinstance(self.calibrated_probability, Absent):
            raise DomainValidationError(
                "calibrated_probability is Absent at creation and stays Absent on "
                "this record forever. A later calibration produces a statistic "
                "*about* a cohort, never a retro-fitted field on a past proposal"
            )
        if self.probability != UNCALIBRATED_PROBABILITY:
            raise DomainValidationError(
                f"probability must be {UNCALIBRATED_PROBABILITY!r}, got {self.probability!r}"
            )
        if self.schema_version not in SUPPORTED_PROPOSAL_VERSIONS:
            raise DomainValidationError(
                f"proposal schema_version {self.schema_version} is not one this "
                f"build writes ({sorted(SUPPORTED_PROPOSAL_VERSIONS)})"
            )
        self._validate_author()
        self._validate_creation_rules()

    def _validate_author(self) -> None:
        if self.author is ProposalAuthor.MODEL:
            if isinstance(self.model, Absent):
                raise DomainValidationError(
                    "a model-authored proposal must name the model, the template, "
                    "the context package and its digest; an INTERPRETED record "
                    "whose conditions were not captured cannot be reviewed later"
                )
            if not isinstance(self.policy_id, Absent):
                raise DomainValidationError(
                    "a model-authored proposal does not carry a policy_id; the "
                    "deterministic policy did not produce it"
                )
        else:
            if not isinstance(self.model, Absent):
                raise DomainValidationError(
                    f"a {self.author.value} proposal carries no model attribution; "
                    "attributing a human or policy decision to a model would "
                    "corrupt every author cohort"
                )
        if self.author is ProposalAuthor.DETERMINISTIC_POLICY and isinstance(
            self.policy_id, Absent
        ):
            raise DomainValidationError(
                "a policy-authored proposal must name the policy that produced it"
            )
        if self.author is ProposalAuthor.OWNER and not isinstance(
            self.policy_id, Absent
        ):
            raise DomainValidationError(
                "an owner-authored proposal carries no policy_id; the owner is not "
                "a policy version"
            )

    def _validate_creation_rules(self) -> None:
        # Rule 2 — both cases required, and both non-empty.
        if not self.supporting_evidence:
            raise DomainValidationError(
                "supporting_evidence is required and must be non-empty"
            )
        if not self.opposing_evidence:
            raise DomainValidationError(
                "opposing_evidence is required and must be non-empty. A proposal "
                "with no case against it is not a proposal; it is an advertisement"
            )
        # Rule 3 — risk/reward needs a stop, and a stop needs an invalidation.
        if isinstance(self.stop, Absent) and not isinstance(self.risk_reward, Absent):
            raise DomainValidationError(
                "a proposal with no stop cannot state a risk/reward; without a "
                "stop there is no risk denominator"
            )
        # Rule 1 and rule 4 — direction, anchor and invalidation agree.
        if self.direction.is_directional:
            if isinstance(self.invalidation, Absent):
                raise DomainValidationError(
                    "a directional proposal states its invalidation; a suggestion "
                    "that cannot be proved wrong cannot be scored"
                )
            if isinstance(self.anchor, Absent):
                raise DomainValidationError(
                    "a directional proposal carries an anchor; without one, the "
                    "same idea becomes a new proposal on every re-run"
                )
            if self.anchor.direction is not self.direction:
                raise DomainValidationError(
                    f"anchor direction {self.anchor.direction.value} disagrees "
                    f"with the proposal's own {self.direction.value}"
                )
            if self.anchor.market != self.market:
                raise DomainValidationError(
                    f"anchor names market {self.anchor.market.value} while the "
                    f"proposal is about {self.market.value}"
                )
            if self.anchor.book is not self.book:
                raise DomainValidationError(
                    f"anchor names book {self.anchor.book.value} while the "
                    f"proposal is in {self.book.value}"
                )
            if self.anchor.invalidation_origin != self.invalidation.origin:
                raise DomainValidationError(
                    "the anchor's invalidation origin is not the origin of the "
                    "proposal's own invalidation level; the anchor must be the "
                    "MEASURED fact the proposal actually rests on"
                )
        else:
            if not isinstance(self.anchor, Absent):
                raise DomainValidationError(
                    "a NO_TRADE proposal carries no anchor; there is no "
                    "invalidation level to anchor on, and a no-trade decision is "
                    "never deduplicated against a directional one"
                )

    # -- projections ---------------------------------------------------------

    @property
    def origin(self) -> ValueOrigin:
        """What this record *is*, given who wrote it."""
        return AUTHOR_ORIGINS[self.author]

    @property
    def is_model_authored(self) -> bool:
        return self.author is ProposalAuthor.MODEL

    def is_expired_at(self, moment: datetime) -> bool:
        """Whether `valid_until` has passed — a comparison, never a stored flag."""
        return require_utc(moment, "moment") >= self.valid_until

    # -- identity and serialization -----------------------------------------

    @property
    def digest_basis(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": encode_timestamp(self.created_at),
            "valid_until": encode_timestamp(self.valid_until),
            "author": self.author.value,
            "market": self.market.to_payload(),
            "book": self.book.value,
            "direction": self.direction.value,
            "directional_assessment": self.directional_assessment.to_payload(),
            "entry_conditions": list(self.entry_conditions),
            "invalidation": encode_maybe(self.invalidation, LevelReading.to_payload),
            "stop": encode_maybe(self.stop, LevelReading.to_payload),
            "take_profit_structure": [
                level.to_payload() for level in self.take_profit_structure
            ],
            "risk_reward": encode_maybe(self.risk_reward, RiskRewardReading.to_payload),
            "stated_confidence": self.stated_confidence.label,
            "supporting_evidence": [c.to_payload() for c in self.supporting_evidence],
            "opposing_evidence": [c.to_payload() for c in self.opposing_evidence],
            "unavailable_evidence": list(self.unavailable_evidence),
            "market_snapshot_id": self.market_snapshot_id,
            "anchor": encode_maybe(self.anchor, Anchor.to_payload),
            "counterfactual_assumption_version": self.counterfactual_assumption_version,
            "version_set": self.version_set.to_payload(),
            "consumed_sources": encode_consumed_sources(self.consumed_sources),
            "policy_id": encode_maybe(self.policy_id, str),
            "model": encode_maybe(self.model, ModelAttribution.to_payload),
            "supersedes": encode_maybe(self.supersedes, str),
            "calibrated_probability": {"absent": self.calibrated_probability.to_payload()},
            "probability": self.probability,
        }

    @property
    def proposal_id(self) -> str:
        return build_domain_record_id(
            type_slug=PROPOSAL_TYPE_SLUG,
            subject=self.market.value,
            moment=self.created_at,
            digest=content_digest_over(self.digest_basis),
        )

    @property
    def content_digest(self) -> str:
        return content_digest_over(self.digest_basis)

    def as_consumed_source(self) -> ConsumedSource:
        return ConsumedSource(
            record_id=self.proposal_id,
            content_digest=self.content_digest,
            kind=PROPOSAL_KIND,
        )

    def to_payload(self) -> dict[str, Any]:
        payload = self.digest_basis
        payload["proposal_id"] = self.proposal_id
        payload["audit"] = self.audit.to_payload()
        return payload

    @classmethod
    def from_payload(cls, raw: Any) -> OpportunityProposal:
        mapping = require_mapping(raw, "proposal")
        version = require_payload_version(
            mapping, supported=SUPPORTED_PROPOSAL_VERSIONS, entity="proposal"
        )
        require_exact_keys(
            mapping,
            {
                "schema_version",
                "proposal_id",
                "created_at",
                "valid_until",
                "author",
                "market",
                "book",
                "direction",
                "directional_assessment",
                "entry_conditions",
                "invalidation",
                "stop",
                "take_profit_structure",
                "risk_reward",
                "stated_confidence",
                "supporting_evidence",
                "opposing_evidence",
                "unavailable_evidence",
                "market_snapshot_id",
                "anchor",
                "counterfactual_assumption_version",
                "version_set",
                "consumed_sources",
                "policy_id",
                "model",
                "supersedes",
                "calibrated_probability",
                "probability",
                "audit",
            },
            "proposal",
        )
        absent_probability = mapping["calibrated_probability"]
        if not isinstance(absent_probability, dict) or set(absent_probability) != {
            "absent"
        }:
            raise PayloadDecodeError(
                "calibrated_probability must be an absence; a proposal that "
                "carries a probability value was not written by this domain"
            )
        decoded = cls(
            created_at=decode_timestamp(mapping["created_at"]),
            valid_until=decode_timestamp(mapping["valid_until"]),
            author=_member(ProposalAuthor, mapping["author"], "author"),
            market=MarketId.from_payload(mapping["market"], "proposal market"),
            book=_member(Book, mapping["book"], "book"),
            direction=_member(TradeDirection, mapping["direction"], "direction"),
            directional_assessment=DirectionalAssessment.from_payload(
                mapping["directional_assessment"]
            ),
            entry_conditions=tuple(
                str(item) for item in _array(mapping["entry_conditions"], "entry")
            ),
            invalidation=decode_maybe(
                mapping["invalidation"], LevelReading.from_payload
            ),
            stop=decode_maybe(mapping["stop"], LevelReading.from_payload),
            take_profit_structure=tuple(
                LevelReading.from_payload(item)
                for item in _array(mapping["take_profit_structure"], "targets")
            ),
            risk_reward=decode_maybe(
                mapping["risk_reward"], RiskRewardReading.from_payload
            ),
            stated_confidence=StatedConfidence(str(mapping["stated_confidence"])),
            supporting_evidence=tuple(
                EvidenceCitation.from_payload(item)
                for item in _array(mapping["supporting_evidence"], "supporting")
            ),
            opposing_evidence=tuple(
                EvidenceCitation.from_payload(item)
                for item in _array(mapping["opposing_evidence"], "opposing")
            ),
            unavailable_evidence=tuple(
                str(item) for item in _array(mapping["unavailable_evidence"], "unavail")
            ),
            market_snapshot_id=str(mapping["market_snapshot_id"]),
            anchor=decode_maybe(mapping["anchor"], Anchor.from_payload),
            counterfactual_assumption_version=str(
                mapping["counterfactual_assumption_version"]
            ),
            version_set=VersionSet.from_payload(mapping["version_set"]),
            audit=RecordAudit.from_payload(mapping["audit"]),
            consumed_sources=decode_consumed_sources(mapping["consumed_sources"]),
            policy_id=decode_maybe(mapping["policy_id"], str),
            model=decode_maybe(mapping["model"], ModelAttribution.from_payload),
            supersedes=decode_maybe(mapping["supersedes"], str),
            calibrated_probability=Absent.from_payload(absent_probability["absent"]),
            probability=str(mapping["probability"]),
            schema_version=version,
        )
        if mapping["proposal_id"] != decoded.proposal_id:
            raise PayloadDecodeError(
                f"proposal_id {mapping['proposal_id']!r} does not match the digest "
                f"of the proposal it claims to identify ({decoded.proposal_id!r})"
            )
        return decoded


def _array(raw: Any, entity: str) -> list[Any]:
    if not isinstance(raw, list):
        raise PayloadDecodeError(
            f"proposal {entity} must be a JSON array, got {type(raw).__name__}"
        )
    return raw


def _member(enum_type: Any, value: Any, entity: str) -> Any:
    try:
        return enum_type(value)
    except ValueError as error:
        raise PayloadDecodeError(
            f"{entity} {value!r} is not a known {enum_type.__name__}; an unknown "
            "member is a clean rejection, never a default"
        ) from error
