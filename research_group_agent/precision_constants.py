"""Shared precision constants for research group extraction."""

from __future__ import annotations

from research_group_agent.models import MemberRole, MemberStatus

# CURRENT member sections — primary recruiting targets.
# Note: "lab" is intentionally absent as a standalone keyword — it matches
# lab proper names like "Berkeley NetSys Lab" or "Distributed Systems Laboratory".
# Use "lab members" or compound keywords instead.
CURRENT_SECTION_KEYWORDS: dict[str, MemberRole] = {
    "current members": MemberRole.UNKNOWN,
    "current students": MemberRole.PHD_STUDENT,
    "current phd students": MemberRole.PHD_STUDENT,
    "current ph.d. students": MemberRole.PHD_STUDENT,
    "current researchers": MemberRole.UNKNOWN,
    "lab members": MemberRole.UNKNOWN,
    "group members": MemberRole.UNKNOWN,
    "team members": MemberRole.UNKNOWN,
    "students": MemberRole.PHD_STUDENT,
    "phd students": MemberRole.PHD_STUDENT,
    "ph.d. students": MemberRole.PHD_STUDENT,
    "doctoral students": MemberRole.PHD_STUDENT,
    "graduate students": MemberRole.PHD_STUDENT,
    "master students": MemberRole.MASTER_STUDENT,
    "ms students": MemberRole.MASTER_STUDENT,
    "postdocs": MemberRole.POSTDOC,
    "postdoctoral": MemberRole.POSTDOC,
    "post-docs": MemberRole.POSTDOC,
    "postdoctoral researchers": MemberRole.POSTDOC,
    "postdoctoral fellows": MemberRole.POSTDOC,
    "research staff": MemberRole.RESEARCH_STAFF,
    "research scientists": MemberRole.RESEARCH_STAFF,
    "our team": MemberRole.UNKNOWN,
    "team": MemberRole.UNKNOWN,
    "personnel": MemberRole.UNKNOWN,
    "researchers": MemberRole.UNKNOWN,
    "people": MemberRole.UNKNOWN,
    "collaborators": MemberRole.UNKNOWN,
    "faculty": MemberRole.PROFESSOR,
    "our lab": MemberRole.UNKNOWN,
    "the lab": MemberRole.UNKNOWN,
}

# ALUMNI sections — extracted internally but excluded from default export.
ALUMNI_SECTION_KEYWORDS: dict[str, MemberRole] = {
    "alumni": MemberRole.ALUMNI,
    "former members": MemberRole.ALUMNI,
    "graduated students": MemberRole.ALUMNI,
    "graduated phd students": MemberRole.ALUMNI,
    "graduated ph.d. students": MemberRole.ALUMNI,
    "past members": MemberRole.ALUMNI,
    "previous members": MemberRole.ALUMNI,
    "former students": MemberRole.ALUMNI,
    "past students": MemberRole.ALUMNI,
    "past researchers": MemberRole.ALUMNI,
    "visitors (past)": MemberRole.VISITOR,
    "ph.d. alumni": MemberRole.ALUMNI,
    "phd alumni": MemberRole.ALUMNI,
}

MEMBER_SECTION_KEYWORDS: dict[str, MemberRole] = {
    **CURRENT_SECTION_KEYWORDS,
    **ALUMNI_SECTION_KEYWORDS,
}

# Sections and containers to skip entirely.
SKIP_SECTION_KEYWORDS: tuple[str, ...] = (
    "navigation",
    "footer",
    "header",
    "menu",
    "sidebar",
    "publications",
    "projects",
    "research areas",
    "research area",
    "news",
    "events",
    "admissions",
    "academics",
    "courses",
    "teaching",
    "resources",
    "software",
    "datasets",
    "contact",
    "open positions",
    "faculty positions",
    "donate",
    "sponsors",
    "funding",
)

SKIP_CONTAINER_TAGS: frozenset[str] = frozenset({"nav", "header", "footer", "aside"})

# Words that appear at the END of a lab's proper name (e.g. "Berkeley NetSys Lab",
# "Distributed Systems Laboratory"). A heading ending with one of these words AND
# having at least 2 prior words is treated as a lab title, not a member section header.
# Exception: if a member-override word is also present, it IS a member section.
LAB_NAME_SUFFIX_WORDS: frozenset[str] = frozenset({
    "lab", "laboratory", "laboratories",
    "systems", "system",
    "network", "networks",
    "institute", "institution",
    "center", "centre",
    "project", "initiative",
})

# Words that override lab-name detection — if present, the heading IS a member section.
MEMBER_OVERRIDE_WORDS: frozenset[str] = frozenset({
    "members", "students", "people", "staff",
    "researchers", "personnel", "postdocs",
})

# URL substrings that indicate a department/admin page (not a research group).
DEPARTMENT_URL_PATTERNS: tuple[str, ...] = (
    "/faculty?",
    "facultytype=",
    "/people/faculty",
    "/academics",
    "/admissions",
    "/ugrad/",
    "/grad/admissions",
    "/undergraduate",
    "/graduate-program",
    "/courses/",
    "/news",
    "/events",
    "/resources",
)

# URL substrings that indicate a lab/group member page.
GROUP_URL_PATTERNS: tuple[str, ...] = (
    "/lab",
    "/group",
    "/members",
    "/students",
    "/team",
    "/people.html",
    "/people/",
    "/people",
    "/~",
    ".github.io",
)

# Anchor text hints for group page discovery scoring.
GROUP_ANCHOR_POSITIVE: tuple[str, ...] = (
    "member",
    "student",
    "team",
    "lab",
    "group",
    "personnel",
    "researcher",
)

GROUP_ANCHOR_NEGATIVE: tuple[str, ...] = (
    "faculty",
    "directory",
    "academics",
    "admissions",
    "people",
    "course",
)

# Strong negative signals for person validation.
PERSON_NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "research area",
    "publications",
    "publication",
    "projects",
    "project",
    "software",
    "dataset",
    "news",
    "events",
    "admissions",
    "faculty positions",
    "open positions",
    "donate",
    "contact",
    "resources",
    "undergraduate program",
    "graduate program",
    "graduate admissions",
    "academics",
    "toggle",
    "course",
    "courses",
    "schedule",
    "directory",
    "department",
    "research topics",
    "areas of research",
)

PERSON_NEGATIVE_NAME_PATTERNS: tuple[str, ...] = (
    "program",
    "toggle",
    "admissions",
    "academics",
    "undergraduate",
    "graduate",
    "department",
    "publications",
    "resources",
    "directory",
    "faculty positions",
    "open positions",
    "research area",
    "contact us",
    "news",
    "events",
    "courses",
    "schedule",
)

PERSON_NEGATIVE_URL_PATTERNS: tuple[str, ...] = (
    "/academics",
    "/admissions",
    "/ugrad/",
    "/grad/",
    "/publications",
    "/projects",
    "/news",
    "/events",
    "/courses",
    "/resources",
    "/contact",
    "/faculty?",
    "facultytype=",
)

# Healthy member count range for manual review flagging.
HEALTHY_MEMBER_MIN = 5
HEALTHY_MEMBER_MAX = 20
