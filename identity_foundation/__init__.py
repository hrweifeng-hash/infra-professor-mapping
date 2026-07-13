"""Identity Foundation — preserve parser output for future identity enrichment."""

from identity_foundation.models import (
    IDENTITY_SCHEMA_VERSION,
    IdentityCandidate,
    ResolvedIdentity,
    ValidationState,
)
from identity_foundation.repository import IdentityRepository
from identity_foundation.resolver import IdentityResolver, StubIdentityResolver

__all__ = [
    "IDENTITY_SCHEMA_VERSION",
    "IdentityCandidate",
    "IdentityRepository",
    "IdentityResolver",
    "ResolvedIdentity",
    "StubIdentityResolver",
    "ValidationState",
]
