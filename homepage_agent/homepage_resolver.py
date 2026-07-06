"""Canonical homepage resolution — upgrade university profiles to personal homepages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

from homepage_agent.fetcher import HomepageFetcher
from homepage_agent.models import FetchStatus, HomepageGraph, NodeCategory
from homepage_agent.parser import HomepageParser
from homepage_agent.pipeline import HomepagePipeline


class HomepagePageType(str, Enum):
    UNIVERSITY_FACULTY = "university_faculty"
    DEPARTMENT_PROFILE = "department_profile"
    PERSONAL_HOMEPAGE = "personal_homepage"
    RESEARCH_GROUP_HOMEPAGE = "research_group_homepage"
    UNKNOWN = "unknown"


# Priority-ordered anchor text for personal homepage links on official profiles.
_PERSONAL_LINK_ANCHORS: tuple[tuple[str, float], ...] = (
    ("personal website", 0.98),
    ("personal homepage", 0.98),
    ("personal home page", 0.98),
    ("visit my website", 0.95),
    ("my website", 0.92),
    ("my homepage", 0.92),
    ("research homepage", 0.9),
    ("lab homepage", 0.88),
    ("homepage", 0.75),
    ("home page", 0.75),
    ("website", 0.65),
)

_UNIVERSITY_PROFILE_PATTERNS: tuple[str, ...] = (
    "/people/profile/",
    "/people/faculty",
    "/faculty/",
    "/~",  # actually personal - handle separately
)

_SOCIAL_AND_CORPORATE_HOSTS: tuple[str, ...] = (
    "facebook.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "instagram.com",
    "youtube.com",
    "nvidia.com",
    "google.com",
    "microsoft.com",
    "amazon.com",
    "apple.com",
)

_PERSONAL_HOST_SUFFIXES: tuple[str, ...] = (
    ".github.io",
    ".gitlab.io",
    ".wordpress.com",
    ".wixsite.com",
    ".squarespace.com",
)

_DEPARTMENT_NAV_PATTERNS: tuple[str, ...] = (
    "/courses/",
    "/schedule",
    "/admissions",
    "/news/",
    "/events/",
    "/academics/",
)

_NEGATIVE_ANCHOR_KEYWORDS: tuple[str, ...] = (
    "courses",
    "course schedule",
    "faculty list",
    "faculty directory",
    "all faculty",
    "department",
    "admissions",
    "news",
    "events",
    "papers",
    "publications",
    "facebook",
    "nvidia",
    "twitter",
    "linkedin",
)


@dataclass
class CanonicalHomepageResolution:
    original_homepage: str
    canonical_homepage: str
    page_type: HomepagePageType
    method: str
    confidence: float
    upgraded: bool


class CanonicalHomepageResolver:
    """
    Resolve a professor's canonical personal homepage from an official profile.

    Uses at most one additional fetch when upgrading from a university page.
    Rebuilds HomepageGraph navigation from the canonical page when upgraded.
    """

    MIN_UPGRADE_CONFIDENCE = 0.65

    def __init__(
        self,
        homepage_pipeline: HomepagePipeline | None = None,
        fetcher: HomepageFetcher | None = None,
        parser: HomepageParser | None = None,
    ):
        self.fetcher = fetcher or HomepageFetcher()
        self.parser = parser or HomepageParser()
        self.homepage_pipeline = homepage_pipeline

    def resolve(self, graph: HomepageGraph) -> HomepageGraph:
        original = graph.homepage_url
        if not original:
            return self._apply_resolution(
                graph,
                CanonicalHomepageResolution(
                    original_homepage="",
                    canonical_homepage="",
                    page_type=HomepagePageType.UNKNOWN,
                    method="missing_homepage",
                    confidence=0.0,
                    upgraded=False,
                ),
            )

        page_type = self.classify_url(original)
        if page_type == HomepagePageType.PERSONAL_HOMEPAGE:
            return self._apply_resolution(
                graph,
                CanonicalHomepageResolution(
                    original_homepage=original,
                    canonical_homepage=original,
                    page_type=page_type,
                    method="already_personal",
                    confidence=1.0,
                    upgraded=False,
                ),
            )

        personal_url, link_confidence, anchor = self._find_personal_link(graph, original)
        if (
            personal_url
            and personal_url.rstrip("/") != original.rstrip("/")
            and link_confidence >= self.MIN_UPGRADE_CONFIDENCE
        ):
            if self.homepage_pipeline is None:
                from homepage_agent.providers.stub import StubNavigatorProvider

                self.homepage_pipeline = HomepagePipeline(provider=StubNavigatorProvider())

            canonical_graph = self.homepage_pipeline.analyze_url(
                professor_name=graph.professor_name,
                homepage_url=personal_url,
            )
            if canonical_graph.fetch_status == FetchStatus.SUCCESS:
                resolution = CanonicalHomepageResolution(
                    original_homepage=original,
                    canonical_homepage=personal_url,
                    page_type=HomepagePageType.PERSONAL_HOMEPAGE,
                    method=f"link_upgrade:{anchor or 'personal_link'}",
                    confidence=link_confidence,
                    upgraded=True,
                )
                return self._apply_resolution(canonical_graph, resolution)

        return self._apply_resolution(
            graph,
            CanonicalHomepageResolution(
                original_homepage=original,
                canonical_homepage=original,
                page_type=page_type,
                method="no_personal_link_found",
                confidence=0.5,
                upgraded=False,
            ),
        )

    def resolve_many(self, graphs: list[HomepageGraph]) -> list[HomepageGraph]:
        return [self.resolve(graph) for graph in graphs]

    @classmethod
    def classify_url(cls, url: str) -> HomepagePageType:
        lower = url.lower()
        parsed = urlparse(lower)
        path = parsed.path

        if cls._is_personal_url(lower):
            return HomepagePageType.PERSONAL_HOMEPAGE

        if any(pattern in lower for pattern in ("/lab", "/group", ".github.io")):
            if "/people/profile" not in lower:
                return HomepagePageType.RESEARCH_GROUP_HOMEPAGE

        if "/people/profile/" in lower or "facultytype=" in lower:
            return HomepagePageType.UNIVERSITY_FACULTY

        if "/people/faculty" in lower or "/faculty/" in lower:
            return HomepagePageType.DEPARTMENT_PROFILE

        if parsed.netloc.endswith(".edu") and "/people/" in path:
            return HomepagePageType.UNIVERSITY_FACULTY

        return HomepagePageType.UNKNOWN

    def _find_personal_link(
        self,
        graph: HomepageGraph,
        original_url: str,
    ) -> tuple[str | None, float, str | None]:
        best_url: str | None = None
        best_score = 0.0
        best_anchor: str | None = None

        for node in graph.graph_nodes:
            if node.node_type == NodeCategory.HOMEPAGE.value:
                continue
            anchor = (node.anchor_text or "").lower()
            url = node.url
            score = self._score_personal_link(anchor, url, original_url)
            if score > best_score:
                best_score = score
                best_url = url
                best_anchor = node.anchor_text

        if best_score >= self.MIN_UPGRADE_CONFIDENCE:
            return best_url, best_score, best_anchor

        document = self.fetcher.fetch(original_url)
        if document.fetch_status != FetchStatus.SUCCESS:
            return None, 0.0, None

        parsed = self.parser.parse(document.html, base_url=document.final_url or original_url)
        for link in parsed.links:
            score = self._score_personal_link(link.anchor_text.lower(), link.absolute_url, original_url)
            if score > best_score:
                best_score = score
                best_url = link.absolute_url
                best_anchor = link.anchor_text

        return best_url, best_score, best_anchor

    @staticmethod
    def _score_personal_link(anchor: str, url: str, original_url: str) -> float:
        if not url or url.rstrip("/") == original_url.rstrip("/"):
            return 0.0

        url_lower = url.lower()
        if CanonicalHomepageResolver._is_department_navigation_url(url_lower):
            return 0.0

        if any(bad in url_lower for bad in ("/faculty", "facultytype=", "/admissions")):
            return 0.0

        anchor_lower = anchor.lower().strip()
        if any(bad in anchor_lower for bad in _NEGATIVE_ANCHOR_KEYWORDS):
            return 0.0

        for pattern, score in _PERSONAL_LINK_ANCHORS:
            if pattern in anchor_lower:
                if CanonicalHomepageResolver._is_personal_url(url_lower):
                    return score
                if CanonicalHomepageResolver._is_research_group_url(url_lower):
                    return min(score, 0.88)
                return 0.0

        if CanonicalHomepageResolver._is_anchorless_personal_url(url_lower):
            return 0.85

        return 0.0

    @staticmethod
    def _is_department_navigation_url(url: str) -> bool:
        lower = url.lower()
        if "/people/profile/" in lower:
            return False
        if "/people/" in lower or "/people" == urlparse(lower).path.rstrip("/").split("/")[-1]:
            return True
        return any(pattern in lower for pattern in _DEPARTMENT_NAV_PATTERNS)

    @staticmethod
    def _is_research_group_url(url: str) -> bool:
        lower = url.lower()
        parsed = urlparse(lower)
        path = parsed.path.lower()
        host = parsed.netloc.lower()

        if any(token in path for token in ("/lab", "/group", "/research-group")):
            return True
        if host.startswith(("lab.", "dsl.", "syslab.", "plasma.")):
            return True
        return False

    @staticmethod
    def _normalize_host(url: str) -> str:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            return host[4:]
        return host

    @staticmethod
    def _is_blocked_host(url: str) -> bool:
        host = CanonicalHomepageResolver._normalize_host(url)
        return any(
            host == blocked or host.endswith(f".{blocked}")
            for blocked in _SOCIAL_AND_CORPORATE_HOSTS
        )

    @staticmethod
    def _is_custom_personal_domain(url: str) -> bool:
        if CanonicalHomepageResolver._is_blocked_host(url):
            return False
        host = CanonicalHomepageResolver._normalize_host(url)
        if host.endswith(".edu"):
            return False
        if any(host.endswith(suffix) for suffix in _PERSONAL_HOST_SUFFIXES):
            return True
        if host.startswith("sites."):
            return False
        parts = host.split(".")
        if len(parts) == 2:
            return True
        if len(parts) == 3 and parts[0] in {"www", "blog"}:
            return True
        return False

    @staticmethod
    def _is_strong_personal_url(url: str) -> bool:
        if CanonicalHomepageResolver._is_blocked_host(url):
            return False

        parsed = urlparse(url)
        path = parsed.path.lower()
        host = parsed.netloc.lower()

        if any(host.endswith(suffix) for suffix in _PERSONAL_HOST_SUFFIXES):
            return True
        if "/~" in path or path.startswith("~/"):
            return True
        if "/homes/" in path or "/users/" in path:
            return True
        return CanonicalHomepageResolver._is_custom_personal_domain(url)

    @staticmethod
    def _is_anchorless_personal_url(url: str) -> bool:
        """URLs safe to upgrade without matching anchor text."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        host = parsed.netloc.lower()

        if CanonicalHomepageResolver._is_blocked_host(url):
            return False
        if any(host.endswith(suffix) for suffix in _PERSONAL_HOST_SUFFIXES):
            return True
        if "/~" in path or "/homes/" in path or "/users/" in path:
            return True
        return False

    @staticmethod
    def _is_personal_url(url: str) -> bool:
        if CanonicalHomepageResolver._is_department_navigation_url(url):
            return False
        if CanonicalHomepageResolver._is_research_group_url(url):
            return False
        return CanonicalHomepageResolver._is_strong_personal_url(url)

    @staticmethod
    def _apply_resolution(
        graph: HomepageGraph,
        resolution: CanonicalHomepageResolution,
    ) -> HomepageGraph:
        graph.original_homepage = resolution.original_homepage
        graph.canonical_homepage = resolution.canonical_homepage
        graph.homepage_resolution_method = resolution.method
        graph.homepage_resolution_confidence = resolution.confidence
        graph.homepage_url = resolution.canonical_homepage
        return graph
