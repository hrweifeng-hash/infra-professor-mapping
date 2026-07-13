"""External identity resolver interface — plug-in point for OpenAlex, DBLP, etc."""

from __future__ import annotations

from abc import ABC, abstractmethod

from identity_foundation.models import IdentityCandidate, ResolvedIdentity


class IdentityResolver(ABC):
    """
    Resolve an identity candidate to a canonical external identity.

    Future providers (OpenAlex, DBLP, Semantic Scholar, Google Scholar, ORCID)
    should implement this interface.
    """

    @abstractmethod
    def resolve(self, candidate: IdentityCandidate) -> ResolvedIdentity:
        """Attempt to resolve a candidate to an external identity record."""


class StubIdentityResolver(IdentityResolver):
    """No-op resolver — returns unresolved identity for all candidates."""

    @property
    def provider_name(self) -> str:
        return "stub"

    def resolve(self, candidate: IdentityCandidate) -> ResolvedIdentity:
        return ResolvedIdentity(
            candidate_id=candidate.id,
            canonical_name=candidate.name,
            orcid=candidate.orcid,
            scholar_url=candidate.scholar,
            confidence=0.0,
            provider=self.provider_name,
            resolved=False,
        )
