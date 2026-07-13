"""Tests for PR31 Identity Foundation."""

from __future__ import annotations

from research_group_agent.models import (
    MemberExtractionResult,
    MemberRole,
    MemberStatus,
    ExtractedMember,
)
from research_group_agent.parser import MemberPageEntry, ParsedMemberPage

from identity_foundation.collector import IdentityCollector
from identity_foundation.models import IdentityCandidate, ValidationState
from identity_foundation.repository import IdentityRepository
from identity_foundation.resolver import StubIdentityResolver


def _make_entry(
    name: str,
    *,
    section: str = "Current Students",
    profile_url: str | None = None,
    in_member_section: bool = True,
    raw_text: str = "",
) -> MemberPageEntry:
    return MemberPageEntry(
        name=name,
        raw_text=raw_text or name,
        profile_url=profile_url,
        section_name=section,
        section_role=MemberRole.PHD_STUDENT,
        member_status=MemberStatus.CURRENT,
        in_member_section=in_member_section,
    )


def test_identity_candidate_id_is_stable():
    c1 = IdentityCandidate(
        name="Jane Doe",
        source_professor="Prof A",
        source_page="https://lab.edu/team",
    )
    c2 = IdentityCandidate(
        name="Jane Doe",
        source_professor="Prof A",
        source_page="https://lab.edu/team",
    )
    assert c1.id == c2.id
    assert c1.id


def test_collector_preserves_rejected_candidates():
    collector = IdentityCollector()
    parsed = ParsedMemberPage(
        page_title="Team",
        entries=[
            _make_entry("Alice Smith", profile_url="https://alice.github.io"),
            _make_entry("Bob Jones"),
            _make_entry("Navigation Link", in_member_section=False),
        ],
    )
    extraction = MemberExtractionResult(
        members=[
            ExtractedMember(name="Alice Smith", role=MemberRole.PHD_STUDENT),
        ],
        rejected_candidates=[
            {"name": "Bob Jones", "reason": "missing personal profile URL"},
        ],
        page_url="https://lab.edu/team",
    )

    candidates = collector.collect_page(
        professor_name="Prof A",
        source_page="https://lab.edu/team",
        parsed=parsed,
        extraction=extraction,
    )

    assert len(candidates) == 3
    names = {c.name for c in candidates}
    assert names == {"Alice Smith", "Bob Jones", "Navigation Link"}

    alice = next(c for c in candidates if c.name == "Alice Smith")
    bob = next(c for c in candidates if c.name == "Bob Jones")
    assert alice.validation_state == ValidationState.RESOLVABLE
    assert bob.rejection_reason is not None
    assert bob.validation_state in {
        ValidationState.RESOLVABLE,
        ValidationState.PARTIAL,
        ValidationState.INVALID,
    }


def test_repository_deduplicate_merges_evidence():
    repo = IdentityRepository()
    repo.collect(
        IdentityCandidate(
            name="Jane Doe",
            source_professor="Prof A",
            source_page="https://lab.edu/team",
            github="https://github.com/jane",
            validation_state=ValidationState.PARTIAL,
        )
    )
    repo.collect(
        IdentityCandidate(
            name="Jane Doe",
            source_professor="Prof A",
            source_page="https://lab.edu/people",
            email="jane@edu",
            validation_state=ValidationState.RESOLVABLE,
        )
    )

    deduped = repo.deduplicate()
    assert len(deduped) == 1
    assert deduped[0].github == "https://github.com/jane"
    assert deduped[0].email == "jane@edu"
    assert deduped[0].validation_state == ValidationState.RESOLVABLE


def test_repository_mark_verified():
    repo = IdentityRepository()
    repo.collect(
        IdentityCandidate(
            name="Alice Smith",
            source_professor="Prof A",
            source_page="https://lab.edu/team",
            validation_state=ValidationState.PARTIAL,
        )
    )
    repo.register_exported_members("Prof A", ["Alice Smith"])
    repo.mark_verified()

    assert repo.candidates[0].validation_state == ValidationState.VERIFIED


def test_stub_resolver_returns_unresolved():
    candidate = IdentityCandidate(
        name="Alice Smith",
        source_professor="Prof A",
        source_page="https://lab.edu/team",
        orcid="https://orcid.org/0000-0001",
    )
    resolver = StubIdentityResolver()
    result = resolver.resolve(candidate)

    assert result.resolved is False
    assert result.provider == "stub"
    assert result.orcid == "https://orcid.org/0000-0001"
    assert result.candidate_id == candidate.id


def test_repository_export(tmp_path):
    repo = IdentityRepository()
    repo.collect(
        IdentityCandidate(
            name="Alice Smith",
            source_professor="Prof A",
            source_page="https://lab.edu/team",
            validation_state=ValidationState.VERIFIED,
        )
    )
    path = repo.export(output_dir=tmp_path)
    assert path.exists()
    assert path.name == "identity_candidates.json"

    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["pipeline_version"] == "PR31"
    assert payload["total_candidates"] == 1
    assert payload["candidates"][0]["name"] == "Alice Smith"


def test_pipeline_has_identity_repository():
    from research_group_agent.pipeline import ResearchGroupPipeline
    from research_group_agent.providers.stub import StubResearchGroupProvider

    pipeline = ResearchGroupPipeline(provider=StubResearchGroupProvider())
    assert pipeline.identity_repository is not None
    assert pipeline.identity_collector is not None
