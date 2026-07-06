"""Heuristic research group navigator provider — no external API calls."""

from __future__ import annotations

from urllib.parse import urlparse

from homepage_agent.models import GraphNode, HomepageGraph, NodeCategory

from research_group_agent.models import (
    GroupPageCandidate,
    NavigationScore,
    ResearchGroupNavigationDecision,
)
from research_group_agent.precision_constants import (
    DEPARTMENT_URL_PATTERNS,
    GROUP_ANCHOR_NEGATIVE,
    GROUP_ANCHOR_POSITIVE,
    GROUP_URL_PATTERNS,
)
from research_group_agent.providers.navigator_base import ResearchGroupNavigatorProvider

_NODE_TYPE_BASE_WEIGHT: dict[str, float] = {
    NodeCategory.LAB_PAGE.value: 1.0,
    NodeCategory.RESEARCH_GROUP_PAGE.value: 0.95,
    NodeCategory.PEOPLE_PAGE.value: 0.55,
}

_MEMBER_ANCHOR_HINTS = (
    "students", "members", "people", "team", "personnel",
    "current members", "group members",
)
_LAB_ANCHOR_HINTS = ("lab", "our lab", "research lab")
_LAB_URL_HINTS = ("/lab", "research-lab")
_MEMBER_URL_HINTS = ("/students", "/members", "/people", "/team")
_RG_URL_HINTS = ("/group", "/research-group", "/research_group")


class StubResearchGroupNavigatorProvider(ResearchGroupNavigatorProvider):
    """
    Heuristic group-page classifier using URL paths and anchor text scoring.

    Serves as the default navigator provider until an LLM backend is configured.
    Returns ResearchGroupNavigationDecision objects with a full NavigationScore
    breakdown and structured evidence list.
    """

    MIN_DECISION_CONFIDENCE = 0.35

    @property
    def provider_name(self) -> str:
        return "heuristic"

    def classify_candidates(
        self,
        prompt: str,
        professor_name: str,
        canonical_homepage: str,
        candidates: list[GroupPageCandidate],
        homepage_graph: HomepageGraph,
    ) -> list[ResearchGroupNavigationDecision]:
        all_urls = {c.url for c in candidates}
        accepted: list[ResearchGroupNavigationDecision] = []
        rejected: list[dict] = []

        for candidate in candidates:
            score, evidence = self._score_candidate(candidate)
            if score.final_score < self.MIN_DECISION_CONFIDENCE:
                rejected.append({
                    "url": candidate.url,
                    "reason": f"score too low ({score.final_score:.2f})",
                    "score": score.to_dict(),
                })
                continue

            accepted.append(
                ResearchGroupNavigationDecision(
                    candidate_url=candidate.url,
                    candidate_type=candidate.node_type,
                    reason="; ".join(evidence) if evidence else "heuristic scoring",
                    navigation_score=score,
                    anchor_text=candidate.anchor_text,
                    title=candidate.title,
                    evidence=evidence,
                    rejected_candidates=rejected,
                )
            )

        return sorted(accepted, key=lambda item: item.confidence, reverse=True)

    @classmethod
    def score_node(cls, node: GraphNode) -> tuple[float, str]:
        """Public scoring for tests and GroupPageDiscoverer backward compat."""
        candidate = GroupPageCandidate(
            url=node.url,
            node_type=node.node_type,
            anchor_text=node.anchor_text,
            title=node.title,
            graph_confidence=node.confidence_value,
        )
        score, evidence = cls._score_candidate(candidate)
        return score.final_score, "; ".join(evidence)

    @classmethod
    def score_candidate(cls, candidate: GroupPageCandidate) -> tuple[float, str]:
        """Public scoring wrapper (returns flat score + reason for compat)."""
        score, evidence = cls._score_candidate(candidate)
        return score.final_score, "; ".join(evidence)

    @classmethod
    def _score_candidate(
        cls, candidate: GroupPageCandidate
    ) -> tuple[NavigationScore, list[str]]:
        url_lower = candidate.url.lower()
        anchor_lower = (candidate.anchor_text or "").lower()
        path_lower = urlparse(candidate.url).path.lower()
        evidence: list[str] = []

        # ── Base scores from node type × graph confidence ────────────────
        base_weight = _NODE_TYPE_BASE_WEIGHT.get(candidate.node_type, 0.3)
        base = base_weight * candidate.graph_confidence

        lab_score = base if candidate.node_type == NodeCategory.LAB_PAGE.value else 0.0
        member_score = (
            base if candidate.node_type == NodeCategory.PEOPLE_PAGE.value else 0.0
        )
        rg_score = (
            base
            if candidate.node_type == NodeCategory.RESEARCH_GROUP_PAGE.value
            else 0.0
        )
        homepage_score = candidate.graph_confidence * 0.4

        if candidate.node_type in _NODE_TYPE_BASE_WEIGHT:
            evidence.append(f"node_type:{candidate.node_type}")

        # ── URL pattern bonuses ──────────────────────────────────────────
        for hint in _LAB_URL_HINTS:
            if hint in url_lower or hint in path_lower:
                lab_score = min(1.0, lab_score + 0.18)
                evidence.append(f"url_lab:{hint}")
                break

        for hint in _MEMBER_URL_HINTS:
            if hint in path_lower:
                member_score = min(1.0, member_score + 0.18)
                evidence.append(f"url_member:{hint}")
                break

        for hint in _RG_URL_HINTS:
            if hint in url_lower or hint in path_lower:
                rg_score = min(1.0, rg_score + 0.15)
                evidence.append(f"url_rg:{hint}")
                break

        for pattern in GROUP_URL_PATTERNS:
            if pattern in url_lower or pattern in path_lower:
                best = max(lab_score, member_score, rg_score)
                lab_score = min(1.0, lab_score + 0.1) if lab_score == best else lab_score
                member_score = (
                    min(1.0, member_score + 0.1)
                    if member_score == best
                    else member_score
                )
                evidence.append(f"group_pattern:{pattern}")
                break

        # ── Anchor text bonuses ──────────────────────────────────────────
        for hint in _MEMBER_ANCHOR_HINTS:
            if hint in anchor_lower:
                member_score = min(1.0, member_score + 0.15)
                evidence.append(f"anchor_member:{hint}")
                break

        for hint in _LAB_ANCHOR_HINTS:
            if hint in anchor_lower:
                lab_score = min(1.0, lab_score + 0.12)
                evidence.append(f"anchor_lab:{hint}")
                break

        for hint in GROUP_ANCHOR_POSITIVE:
            if hint in anchor_lower:
                best = max(lab_score, member_score, rg_score)
                if best == member_score:
                    member_score = min(1.0, member_score + 0.1)
                else:
                    lab_score = min(1.0, lab_score + 0.1)
                evidence.append(f"anchor_group+:{hint}")
                break

        # ── Directory / faculty penalties ────────────────────────────────
        directory_penalty = 0.0

        for pattern in DEPARTMENT_URL_PATTERNS:
            if pattern in url_lower:
                directory_penalty = max(directory_penalty, 0.5)
                evidence.append(f"dept_penalty:{pattern}")

        if (
            "faculty" in url_lower
            and "member" not in url_lower
            and "student" not in url_lower
        ):
            directory_penalty = max(directory_penalty, 0.4)
            evidence.append("faculty_directory_penalty")

        for hint in GROUP_ANCHOR_NEGATIVE:
            if hint in anchor_lower:
                directory_penalty = max(directory_penalty, 0.25)
                evidence.append(f"anchor_neg:{hint}")

        # ── Assemble NavigationScore ─────────────────────────────────────
        # provider_score = best category weighted by penalty
        category_max = max(lab_score, member_score, rg_score, homepage_score)
        provider_score = round(
            min(1.0, max(0.0, category_max * max(0.0, 1.0 - directory_penalty * 0.6))),
            3,
        )

        nav_score = NavigationScore(
            lab_score=round(lab_score, 3),
            member_score=round(member_score, 3),
            research_group_score=round(rg_score, 3),
            homepage_score=round(homepage_score, 3),
            directory_penalty=round(directory_penalty, 3),
            provider_score=provider_score,
        )

        return nav_score, evidence
