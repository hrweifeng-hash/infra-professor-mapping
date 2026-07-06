"""Prompt construction for research group providers."""

from __future__ import annotations

from homepage_agent.models import HomepageGraph

from research_group_agent.models import (
    ExtractedMember,
    GroupPageCandidate,
    GroupPageSelection,
)
from research_group_agent.parser import ParsedMemberPage

CANDIDATE_PREVIEW_LIMIT = 20


def build_group_navigation_prompt(
    professor_name: str,
    canonical_homepage: str,
    candidates: list[GroupPageCandidate],
    homepage_graph: HomepageGraph,
) -> str:
    """
    Build the prompt sent to a ResearchGroupNavigatorProvider.

    Separated from provider logic so prompts can be reviewed, versioned, and
    reused across heuristic / LLM backends.
    """
    preview = candidates[:CANDIDATE_PREVIEW_LIMIT]
    candidate_lines = []
    for index, candidate in enumerate(preview, start=1):
        anchor = candidate.anchor_text or "(no anchor text)"
        title = candidate.title or "(no title)"
        candidate_lines.append(
            f"{index}. [{anchor}]({candidate.url}) | type: {candidate.node_type} | "
            f"title: {title} | graph confidence: {candidate.graph_confidence:.2f}"
        )

    node_types = ", ".join(
        sorted({candidate.node_type for candidate in candidates})
    )

    return (
        "You are analyzing a professor homepage graph to find the best research "
        "group page for member discovery.\n"
        "Only choose from candidate links below — do not invent URLs.\n"
        "Prefer lab/students/team pages over department faculty directories.\n\n"
        f"Professor: {professor_name}\n"
        f"Canonical homepage: {canonical_homepage}\n"
        f"Original homepage: {homepage_graph.original_homepage or canonical_homepage}\n"
        f"Homepage graph nodes: {len(homepage_graph.graph_nodes)}\n\n"
        f"Candidate group pages ({len(candidates)} total, showing up to "
        f"{CANDIDATE_PREVIEW_LIMIT}):\n"
        f"{chr(10).join(candidate_lines) if candidate_lines else '- (none)'}\n\n"
        f"Candidate types present: {node_types or '(none)'}\n\n"
        "For each viable candidate return: candidate_url, candidate_type, confidence, "
        "and a short reason.\n"
        "Reject department directories, faculty listings, and unrelated pages.\n"
    )


def build_member_extraction_prompt(
    professor_name: str,
    group_page: GroupPageSelection,
    parsed: ParsedMemberPage,
) -> str:
    preview_entries = parsed.entries[:30]
    entry_lines = []
    for index, entry in enumerate(preview_entries, start=1):
        role = entry.role_hint or "unknown"
        url = entry.profile_url or "(no url)"
        entry_lines.append(f"{index}. {entry.name} | role hint: {role} | {url}")

    return (
        "Extract research group members from this lab/people page.\n"
        "When role is uncertain, use Unknown.\n\n"
        f"Professor (advisor): {professor_name}\n"
        f"Group page: {group_page.url} ({group_page.source_node_type})\n"
        f"Page title: {parsed.page_title or '(unknown)'}\n\n"
        f"Parsed entries ({len(parsed.entries)} total, showing up to 30):\n"
        f"{chr(10).join(entry_lines) if entry_lines else '- (none)'}\n\n"
        "For each member return: name, role, profile_url.\n"
        "Roles: Professor, Postdoc, PhD Student, Master Student, Research Staff, "
        "Visitor, Alumni, Unknown.\n"
    )


def build_identity_resolution_prompt(
    member: ExtractedMember,
    professor_name: str,
) -> str:
    links = member.profile_url or "(none)"
    context = member.context or "(none)"
    return (
        "Resolve public academic identities for this research group member.\n"
        "Do not assume identities exist — only report evidence found.\n\n"
        f"Member: {member.name}\n"
        f"Advisor: {professor_name}\n"
        f"Profile URL: {links}\n"
        f"Context: {context}\n\n"
        "Search for: Homepage, Github, LinkedIn, Google Scholar, DBLP, "
        "OpenReview, Semantic Scholar, ORCID, Personal Blog.\n"
    )
