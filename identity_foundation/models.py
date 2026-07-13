"""Identity Foundation data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlparse
import hashlib


IDENTITY_SCHEMA_VERSION = "1.0"
IDENTITY_PIPELINE_VERSION = "PR31"


class ValidationState(str, Enum):
    """Metadata classification — does not affect production export."""

    VERIFIED = "VERIFIED"
    RESOLVABLE = "RESOLVABLE"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"


_STATE_PRIORITY = {
    ValidationState.VERIFIED: 4,
    ValidationState.RESOLVABLE: 3,
    ValidationState.PARTIAL: 2,
    ValidationState.INVALID: 1,
}


def _higher_state(a: ValidationState, b: ValidationState) -> ValidationState:
    return a if _STATE_PRIORITY[a] >= _STATE_PRIORITY[b] else b


@dataclass
class IdentityCandidate:
    """Preserved identity evidence from parser output."""

    name: str
    source_professor: str
    source_page: str
    role: str = "Unknown"
    section: str | None = None
    status: str = "CURRENT"
    source_domain: str = ""
    email: str | None = None
    homepage: str | None = None
    github: str | None = None
    scholar: str | None = None
    linkedin: str | None = None
    orcid: str | None = None
    affiliation: str | None = None
    confidence: float = 0.0
    validation_state: ValidationState = ValidationState.PARTIAL
    rejection_reason: str | None = None
    id: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self) -> None:
        if not self.id:
            self.id = self._make_id()
        if not self.source_domain and self.source_page:
            self.source_domain = urlparse(self.source_page).netloc

    def _make_id(self) -> str:
        key = (
            f"{self.source_professor}|{self.name}|{self.source_page}"
        ).lower().strip()
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def merge_with(self, other: IdentityCandidate) -> IdentityCandidate:
        """Merge evidence from a duplicate candidate (same professor + name)."""
        return IdentityCandidate(
            id=self.id,
            name=self.name,
            source_professor=self.source_professor,
            source_page=self.source_page,
            role=other.role if other.role != "Unknown" else self.role,
            section=other.section or self.section,
            status=other.status if other.status != "CURRENT" else self.status,
            source_domain=self.source_domain or other.source_domain,
            email=other.email or self.email,
            homepage=other.homepage or self.homepage,
            github=other.github or self.github,
            scholar=other.scholar or self.scholar,
            linkedin=other.linkedin or self.linkedin,
            orcid=other.orcid or self.orcid,
            affiliation=other.affiliation or self.affiliation,
            confidence=max(self.confidence, other.confidence),
            validation_state=_higher_state(self.validation_state, other.validation_state),
            rejection_reason=other.rejection_reason or self.rejection_reason,
            created_at=min(self.created_at, other.created_at),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "section": self.section,
            "status": self.status,
            "source_professor": self.source_professor,
            "source_page": self.source_page,
            "source_domain": self.source_domain,
            "email": self.email,
            "homepage": self.homepage,
            "github": self.github,
            "scholar": self.scholar,
            "linkedin": self.linkedin,
            "orcid": self.orcid,
            "affiliation": self.affiliation,
            "confidence": round(self.confidence, 3),
            "validation_state": self.validation_state.value,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IdentityCandidate:
        state = data.get("validation_state", ValidationState.PARTIAL.value)
        if isinstance(state, str):
            state = ValidationState(state)
        return cls(
            id=data.get("id", ""),
            name=data["name"],
            role=data.get("role", "Unknown"),
            section=data.get("section"),
            status=data.get("status", "CURRENT"),
            source_professor=data["source_professor"],
            source_page=data["source_page"],
            source_domain=data.get("source_domain", ""),
            email=data.get("email"),
            homepage=data.get("homepage"),
            github=data.get("github"),
            scholar=data.get("scholar"),
            linkedin=data.get("linkedin"),
            orcid=data.get("orcid"),
            affiliation=data.get("affiliation"),
            confidence=float(data.get("confidence", 0.0)),
            validation_state=state,
            rejection_reason=data.get("rejection_reason"),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class ResolvedIdentity:
    """Output of an external identity resolver (OpenAlex, DBLP, etc.)."""

    candidate_id: str
    canonical_name: str | None = None
    openalex_id: str | None = None
    dblp_id: str | None = None
    orcid: str | None = None
    scholar_url: str | None = None
    confidence: float = 0.0
    provider: str = "stub"
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "canonical_name": self.canonical_name,
            "openalex_id": self.openalex_id,
            "dblp_id": self.dblp_id,
            "orcid": self.orcid,
            "scholar_url": self.scholar_url,
            "confidence": round(self.confidence, 3),
            "provider": self.provider,
            "resolved": self.resolved,
        }
