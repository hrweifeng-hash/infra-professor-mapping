"""
LLMResearchGroupNavigatorProvider — provider base for LLM-backed navigation.

Subclass and implement _invoke_llm() to connect any LLM backend (GPT, Claude,
Gemini, Qwen, DeepSeek, local models).  The interface guarantees:

- Structured JSON graph input (not raw HTML).
- Structured ResearchGroupNavigationDecision output.
- Automatic fallback to the heuristic provider on any error or empty response.
- Deterministic behaviour: callers receive the same decision format regardless
  of whether the LLM or the fallback handled the request.

Navigation decisions are never skipped — if the LLM cannot decide, the
heuristic ensures the pipeline always has a result to work with.
"""

from __future__ import annotations

import json
import logging

from homepage_agent.models import HomepageGraph

from research_group_agent.models import (
    GroupPageCandidate,
    NavigationScore,
    ResearchGroupNavigationDecision,
)
from research_group_agent.navigation_prompt_builder import NavigationPromptBuilder
from research_group_agent.providers.navigator_base import ResearchGroupNavigatorProvider
from research_group_agent.providers.navigator_stub import StubResearchGroupNavigatorProvider

logger = logging.getLogger(__name__)

_VALID_CANDIDATE_TYPES = {
    "lab_page",
    "people_page",
    "research_group_page",
    "publications_page",
    "contact_page",
    "homepage",
    "unknown",
}


class LLMResearchGroupNavigatorProvider(ResearchGroupNavigatorProvider):
    """
    LLM-backed navigation provider.

    Subclass and override _invoke_llm() to connect a concrete backend.
    Falls back to StubResearchGroupNavigatorProvider automatically.

    Example subclass::

        class OpenAINavigatorProvider(LLMResearchGroupNavigatorProvider):
            def __init__(self, client, model="gpt-4o-mini"):
                super().__init__()
                self._client = client
                self._model = model

            def _invoke_llm(self, prompt: str, graph_repr: dict) -> list[dict] | None:
                messages = [
                    {"role": "system", "content": "You are a navigation assistant."},
                    {"role": "user", "content": prompt},
                ]
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=0,
                    response_format={"type": "json_object"},
                )
                raw = json.loads(resp.choices[0].message.content)
                return raw.get("decisions", [])
    """

    def __init__(
        self,
        fallback_provider: ResearchGroupNavigatorProvider | None = None,
        prompt_builder: NavigationPromptBuilder | None = None,
    ):
        self._fallback = fallback_provider or StubResearchGroupNavigatorProvider()
        self._prompt_builder = prompt_builder or NavigationPromptBuilder()
        self._last_used_fallback = False

    @property
    def provider_name(self) -> str:
        return "llm"

    @property
    def used_fallback(self) -> bool:
        """True when the most recent classify_candidates() call used the fallback."""
        return self._last_used_fallback

    def classify_candidates(
        self,
        prompt: str,
        professor_name: str,
        canonical_homepage: str,
        candidates: list[GroupPageCandidate],
        homepage_graph: HomepageGraph,
    ) -> list[ResearchGroupNavigationDecision]:
        if not candidates:
            self._last_used_fallback = False
            return []

        graph_repr = NavigationPromptBuilder.build_graph_repr(
            professor_name=professor_name,
            canonical_homepage=canonical_homepage,
            candidates=candidates,
            homepage_graph=homepage_graph,
        )

        try:
            raw = self._invoke_llm(prompt, graph_repr)
            if raw:
                validated = self._parse_and_validate(raw, candidates)
                if validated:
                    self._last_used_fallback = False
                    return validated
        except Exception as exc:
            logger.warning(
                "LLMResearchGroupNavigatorProvider: LLM call failed (%s); "
                "falling back to heuristic",
                exc,
            )

        self._last_used_fallback = True
        fallback_decisions = self._fallback.classify_candidates(
            prompt=prompt,
            professor_name=professor_name,
            canonical_homepage=canonical_homepage,
            candidates=candidates,
            homepage_graph=homepage_graph,
        )
        return self._mark_as_fallback(fallback_decisions)

    def _invoke_llm(
        self,
        prompt: str,
        graph_repr: dict,
    ) -> list[dict] | None:
        """
        Call the LLM and return raw decision dicts.

        Override in concrete implementations.  Return None or an empty list
        to trigger automatic fallback.

        Expected return format::

            [
                {
                    "candidate_url": "https://...",
                    "candidate_type": "lab_page",
                    "confidence": 0.92,
                    "reason": "...",
                    "evidence": ["Current Members section", "PhD Students listed"],
                    "rejected_candidates": [
                        {"url": "...", "reason": "faculty directory"}
                    ]
                },
                ...
            ]
        """
        return None  # default: always fall back to heuristic

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_and_validate(
        raw: list[dict],
        candidates: list[GroupPageCandidate],
    ) -> list[ResearchGroupNavigationDecision]:
        valid_urls = {c.url for c in candidates}
        candidate_map = {c.url: c for c in candidates}
        decisions: list[ResearchGroupNavigationDecision] = []

        for item in raw:
            if not isinstance(item, dict):
                continue
            url = item.get("candidate_url", "")
            if not url or url not in valid_urls:
                continue

            raw_confidence = float(item.get("confidence", 0.0))
            candidate = candidate_map[url]

            nav_score = NavigationScore(
                provider_score=round(min(1.0, max(0.0, raw_confidence)), 3),
                lab_score=float(item.get("lab_score", 0.0)),
                member_score=float(item.get("member_score", 0.0)),
                research_group_score=float(item.get("research_group_score", 0.0)),
                homepage_score=float(item.get("homepage_score", 0.0)),
                directory_penalty=float(item.get("directory_penalty", 0.0)),
            )

            raw_type = item.get("candidate_type", candidate.node_type or "unknown")
            candidate_type = (
                raw_type if raw_type in _VALID_CANDIDATE_TYPES else candidate.node_type
            )

            decisions.append(
                ResearchGroupNavigationDecision(
                    candidate_url=url,
                    candidate_type=candidate_type,
                    reason=str(item.get("reason", "llm decision")),
                    navigation_score=nav_score,
                    anchor_text=candidate.anchor_text,
                    title=candidate.title,
                    evidence=list(item.get("evidence", [])),
                    rejected_candidates=list(item.get("rejected_candidates", [])),
                )
            )

        return sorted(decisions, key=lambda d: d.confidence, reverse=True)

    @staticmethod
    def _mark_as_fallback(
        decisions: list[ResearchGroupNavigationDecision],
    ) -> list[ResearchGroupNavigationDecision]:
        for decision in decisions:
            if not decision.evidence:
                decision.evidence = ["[fallback: heuristic]"]
            else:
                decision.evidence = ["[fallback: heuristic]"] + decision.evidence
        return decisions
