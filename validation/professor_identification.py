"""Heuristic professor role classification for validation (PR11).

These are estimates based on affiliation/homepage/publication signals — not
ground-truth labels. Used to assess whether a dedicated Professor
Identification stage is warranted.
"""

from dataclasses import dataclass
from enum import Enum

from models.professor_profile import ProfessorProfile


class ProfessorRole(str, Enum):
    FACULTY = "faculty"
    INDUSTRY = "industry_researcher"
    PHD_STUDENT = "phd_student"
    UNKNOWN = "unknown"


INDUSTRY_AFFILIATION_MARKERS = (
    "google",
    "microsoft",
    "meta",
    "facebook",
    "amazon",
    "apple",
    "nvidia",
    "intel",
    "ibm research",
    "adobe",
    "salesforce",
    "vmware",
    "oracle labs",
    "research lab",
    "corporate research",
)

INDUSTRY_HOMEPAGE_MARKERS = (
    "google.com",
    "microsoft.com",
    "meta.com",
    "amazon.com",
    "nvidia.com",
    "research.google",
    "research.microsoft",
)

FACULTY_HOMEPAGE_MARKERS = (
    "/faculty/",
    "/people/",
    "/directory/",
    "/profiles/",
    "/~",
    ".edu/",
)


@dataclass
class RoleClassification:
    role: ProfessorRole
    confidence: float
    rationale: str


def classify_professor_role(professor: ProfessorProfile) -> RoleClassification:
    affiliation = (
        professor.affiliation or professor.university or ""
    ).lower()
    homepage = (professor.homepage or "").lower()
    intelligence = professor.intelligence

    if _looks_industry(affiliation, homepage):
        return RoleClassification(
            role=ProfessorRole.INDUSTRY,
            confidence=0.85,
            rationale="Industry affiliation or corporate homepage domain",
        )

    if _looks_faculty(professor, affiliation, homepage):
        return RoleClassification(
            role=ProfessorRole.FACULTY,
            confidence=0.8 if professor.university else 0.65,
            rationale=_faculty_rationale(professor, homepage),
        )

    if _looks_phd_student(professor, intelligence.publication_count):
        return RoleClassification(
            role=ProfessorRole.PHD_STUDENT,
            confidence=0.55,
            rationale=(
                "Low publication count in tracked venues with no university "
                "affiliation match"
            ),
        )

    return RoleClassification(
        role=ProfessorRole.UNKNOWN,
        confidence=0.3,
        rationale="Insufficient affiliation or homepage signals",
    )


def _looks_industry(affiliation: str, homepage: str) -> bool:
    if any(marker in affiliation for marker in INDUSTRY_AFFILIATION_MARKERS):
        if "university" not in affiliation:
            return True

    return any(marker in homepage for marker in INDUSTRY_HOMEPAGE_MARKERS)


def _looks_faculty(
    professor: ProfessorProfile,
    affiliation: str,
    homepage: str,
) -> bool:
    if professor.university and professor.is_us:
        if ".edu" in homepage:
            return True
        if any(marker in homepage for marker in FACULTY_HOMEPAGE_MARKERS):
            return True
        if professor.affiliation_confidence >= 0.6:
            return True

    if "university" in affiliation or "institute of technology" in affiliation:
        return True

    return False


def _faculty_rationale(professor: ProfessorProfile, homepage: str) -> str:
    if ".edu" in homepage:
        return "US university match with .edu homepage"
    if professor.university:
        return f"Matched US university: {professor.university}"
    return "University-style affiliation text"


def _looks_phd_student(
    professor: ProfessorProfile,
    publication_count: int,
) -> bool:
    if professor.university:
        return False

    return publication_count <= 4
