"""
PR15 — Navigation Intelligence test suite.

Covers:
- NavigationScore model and final_score computation
- ResearchGroupNavigationDecision (property compat + new fields)
- NavigationPromptBuilder (structured graph repr)
- StubResearchGroupNavigatorProvider (NavigationScore + evidence output)
- LLMResearchGroupNavigatorProvider (fallback, parse, validate)
- ResearchGroupNavigator (path tracking, select, fallback)
- NavigationDebugWriter (record + write)
- Regression: heuristic and LLM-fallback produce same shape output
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from homepage_agent.models import ConfidenceScore, FetchStatus, GraphNode, HomepageGraph

from research_group_agent.debug_writer import NavigationDebugWriter
from research_group_agent.models import (
    GroupPageCandidate,
    GroupPageSelection,
    NavigationScore,
    ResearchGroupGraph,
    ResearchGroupNavigationDecision,
)
from research_group_agent.navigation_prompt_builder import NavigationPromptBuilder
from research_group_agent.navigator import ResearchGroupNavigator
from research_group_agent.providers.llm_navigator import LLMResearchGroupNavigatorProvider
from research_group_agent.providers.navigator_stub import StubResearchGroupNavigatorProvider


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _lab_graph(professor_name: str = "Ada Lovelace") -> HomepageGraph:
    return HomepageGraph(
        professor_name=professor_name,
        homepage_url="https://ada.github.io/",
        fetch_status=FetchStatus.SUCCESS,
        original_homepage="https://www.cs.example.edu/people/profile/ada",
        canonical_homepage="https://ada.github.io/",
        graph_nodes=[
            GraphNode(
                node_type="lab_page",
                url="https://ada.github.io/lab/",
                confidence=ConfidenceScore.from_stub(0.9, 0.85),
                discovery_method="heuristic",
                anchor_text="Lab Members",
            ),
            GraphNode(
                node_type="people_page",
                url="https://ada.github.io/students/",
                confidence=ConfidenceScore.from_stub(0.8, 0.75),
                discovery_method="heuristic",
                anchor_text="PhD Students",
            ),
        ],
    )


def _stub_provider() -> StubResearchGroupNavigatorProvider:
    return StubResearchGroupNavigatorProvider()


# ─────────────────────────────────────────────────────────────────────────────
# NavigationScore
# ─────────────────────────────────────────────────────────────────────────────

class TestNavigationScore(unittest.TestCase):
    def test_final_score_uses_provider_score_when_set(self):
        score = NavigationScore(
            lab_score=0.3,
            member_score=0.5,
            provider_score=0.88,
        )
        self.assertAlmostEqual(score.final_score, 0.88)

    def test_final_score_falls_back_to_category_max_when_no_provider(self):
        score = NavigationScore(
            lab_score=0.7,
            member_score=0.4,
            provider_score=0.0,
        )
        self.assertAlmostEqual(score.final_score, 0.7)

    def test_directory_penalty_reduces_final_score(self):
        score = NavigationScore(
            lab_score=0.8,
            directory_penalty=0.5,
            provider_score=0.0,
        )
        self.assertLess(score.final_score, 0.8)

    def test_final_score_clamped_to_one(self):
        score = NavigationScore(provider_score=1.5)
        self.assertLessEqual(score.final_score, 1.0)

    def test_to_dict_contains_all_fields(self):
        score = NavigationScore(lab_score=0.7, provider_score=0.8)
        d = score.to_dict()
        for key in ("lab_score", "member_score", "research_group_score",
                    "homepage_score", "directory_penalty", "provider_score", "final_score"):
            self.assertIn(key, d)


# ─────────────────────────────────────────────────────────────────────────────
# ResearchGroupNavigationDecision
# ─────────────────────────────────────────────────────────────────────────────

class TestResearchGroupNavigationDecision(unittest.TestCase):
    def _make_decision(self, provider_score: float = 0.75) -> ResearchGroupNavigationDecision:
        return ResearchGroupNavigationDecision(
            candidate_url="https://ada.github.io/lab/",
            candidate_type="lab_page",
            reason="lab page detected",
            navigation_score=NavigationScore(provider_score=provider_score),
            evidence=["node_type:lab_page", "anchor_lab:lab"],
        )

    def test_confidence_property_matches_final_score(self):
        decision = self._make_decision(0.85)
        self.assertAlmostEqual(decision.confidence, 0.85)

    def test_final_confidence_matches_confidence(self):
        decision = self._make_decision(0.72)
        self.assertEqual(decision.confidence, decision.final_confidence)

    def test_evidence_is_list(self):
        decision = self._make_decision()
        self.assertIsInstance(decision.evidence, list)
        self.assertTrue(len(decision.evidence) > 0)

    def test_navigation_path_defaults_to_empty(self):
        decision = self._make_decision()
        self.assertEqual(decision.navigation_path, [])

    def test_to_dict_contains_navigation_score(self):
        decision = self._make_decision()
        d = decision.to_dict()
        self.assertIn("navigation_score", d)
        self.assertIn("final_score", d["navigation_score"])


# ─────────────────────────────────────────────────────────────────────────────
# NavigationPromptBuilder
# ─────────────────────────────────────────────────────────────────────────────

class TestNavigationPromptBuilder(unittest.TestCase):
    def setUp(self):
        self.graph = _lab_graph()
        self.candidates = [
            GroupPageCandidate(
                url="https://ada.github.io/lab/",
                node_type="lab_page",
                anchor_text="Lab Members",
                graph_confidence=0.9,
            )
        ]
        self.builder = NavigationPromptBuilder()

    def test_build_graph_repr_contains_professor(self):
        repr_ = NavigationPromptBuilder.build_graph_repr(
            professor_name="Ada Lovelace",
            canonical_homepage="https://ada.github.io/",
            candidates=self.candidates,
            homepage_graph=self.graph,
        )
        self.assertEqual(repr_["professor"], "Ada Lovelace")

    def test_build_graph_repr_includes_candidate_pages(self):
        repr_ = NavigationPromptBuilder.build_graph_repr(
            professor_name="Ada Lovelace",
            canonical_homepage="https://ada.github.io/",
            candidates=self.candidates,
            homepage_graph=self.graph,
        )
        urls = [c["url"] for c in repr_["candidate_pages"]]
        self.assertIn("https://ada.github.io/lab/", urls)

    def test_build_returns_string_prompt(self):
        prompt = self.builder.build(
            professor_name="Ada Lovelace",
            canonical_homepage="https://ada.github.io/",
            candidates=self.candidates,
            homepage_graph=self.graph,
        )
        self.assertIsInstance(prompt, str)
        self.assertIn("Ada Lovelace", prompt)
        self.assertIn("candidate_pages", prompt)

    def test_prompt_is_json_parseable_in_body(self):
        prompt = self.builder.build(
            professor_name="Ada Lovelace",
            canonical_homepage="https://ada.github.io/",
            candidates=self.candidates,
            homepage_graph=self.graph,
        )
        start = prompt.index("{")
        end = prompt.rindex("}") + 1
        json.loads(prompt[start:end])  # must not raise

    def test_no_raw_html_in_prompt(self):
        prompt = self.builder.build(
            professor_name="Ada Lovelace",
            canonical_homepage="https://ada.github.io/",
            candidates=self.candidates,
            homepage_graph=self.graph,
        )
        self.assertNotIn("<html", prompt.lower())
        self.assertNotIn("<div", prompt.lower())


# ─────────────────────────────────────────────────────────────────────────────
# StubResearchGroupNavigatorProvider
# ─────────────────────────────────────────────────────────────────────────────

class TestStubNavigatorProvider(unittest.TestCase):
    def setUp(self):
        self.graph = _lab_graph()
        self.provider = _stub_provider()
        self.candidates = [
            GroupPageCandidate(
                url="https://ada.github.io/lab/",
                node_type="lab_page",
                anchor_text="Lab Members",
                graph_confidence=0.9,
            ),
            GroupPageCandidate(
                url="https://www.cs.example.edu/faculty/all",
                node_type="people_page",
                anchor_text="Faculty",
                graph_confidence=0.6,
            ),
        ]

    def test_returns_list_of_decisions(self):
        decisions = self.provider.classify_candidates(
            prompt="",
            professor_name="Ada Lovelace",
            canonical_homepage="https://ada.github.io/",
            candidates=self.candidates,
            homepage_graph=self.graph,
        )
        self.assertIsInstance(decisions, list)
        for d in decisions:
            self.assertIsInstance(d, ResearchGroupNavigationDecision)

    def test_decisions_have_navigation_score(self):
        decisions = self.provider.classify_candidates(
            prompt="",
            professor_name="Ada",
            canonical_homepage="https://ada.github.io/",
            candidates=self.candidates,
            homepage_graph=self.graph,
        )
        for d in decisions:
            self.assertIsInstance(d.navigation_score, NavigationScore)

    def test_decisions_have_evidence(self):
        decisions = self.provider.classify_candidates(
            prompt="",
            professor_name="Ada",
            canonical_homepage="https://ada.github.io/",
            candidates=self.candidates,
            homepage_graph=self.graph,
        )
        for d in decisions:
            self.assertIsInstance(d.evidence, list)

    def test_faculty_directory_penalised(self):
        decisions = self.provider.classify_candidates(
            prompt="",
            professor_name="Ada",
            canonical_homepage="https://ada.github.io/",
            candidates=self.candidates,
            homepage_graph=self.graph,
        )
        lab_decision = next(
            (d for d in decisions if "lab/" in d.candidate_url), None
        )
        faculty_decision = next(
            (d for d in decisions if "faculty" in d.candidate_url), None
        )
        if lab_decision and faculty_decision:
            self.assertGreater(lab_decision.confidence, faculty_decision.confidence)

    def test_decisions_sorted_by_confidence_desc(self):
        decisions = self.provider.classify_candidates(
            prompt="",
            professor_name="Ada",
            canonical_homepage="https://ada.github.io/",
            candidates=self.candidates,
            homepage_graph=self.graph,
        )
        if len(decisions) >= 2:
            for i in range(len(decisions) - 1):
                self.assertGreaterEqual(
                    decisions[i].confidence, decisions[i + 1].confidence
                )

    def test_score_node_backward_compat(self):
        node = GraphNode(
            node_type="lab_page",
            url="https://ada.github.io/lab/",
            confidence=ConfidenceScore.from_stub(0.9, 0.85),
            discovery_method="heuristic",
            anchor_text="Lab Members",
        )
        score, reason = StubResearchGroupNavigatorProvider.score_node(node)
        self.assertIsInstance(score, float)
        self.assertGreater(score, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# LLMResearchGroupNavigatorProvider
# ─────────────────────────────────────────────────────────────────────────────

class TestLLMNavigatorProvider(unittest.TestCase):
    def setUp(self):
        self.graph = _lab_graph()
        self.candidates = [
            GroupPageCandidate(
                url="https://ada.github.io/lab/",
                node_type="lab_page",
                anchor_text="Lab Members",
                graph_confidence=0.9,
            )
        ]

    def test_falls_back_to_heuristic_when_invoke_returns_none(self):
        provider = LLMResearchGroupNavigatorProvider()
        decisions = provider.classify_candidates(
            prompt="", professor_name="Ada", canonical_homepage="https://ada.github.io/",
            candidates=self.candidates, homepage_graph=self.graph,
        )
        self.assertTrue(provider.used_fallback)
        self.assertTrue(len(decisions) > 0)

    def test_fallback_decisions_marked_with_hint(self):
        provider = LLMResearchGroupNavigatorProvider()
        decisions = provider.classify_candidates(
            prompt="", professor_name="Ada", canonical_homepage="https://ada.github.io/",
            candidates=self.candidates, homepage_graph=self.graph,
        )
        first = decisions[0]
        self.assertTrue(
            any("[fallback" in e for e in first.evidence),
            msg=f"Expected fallback marker in evidence: {first.evidence}",
        )

    def test_llm_response_parsed_and_validated(self):
        class MockLLMProvider(LLMResearchGroupNavigatorProvider):
            def _invoke_llm(self, prompt, graph_repr):
                return [
                    {
                        "candidate_url": "https://ada.github.io/lab/",
                        "candidate_type": "lab_page",
                        "confidence": 0.93,
                        "reason": "Current Members section found",
                        "evidence": ["Current Members section", "PhD Students listed"],
                        "rejected_candidates": [
                            {"url": "https://dept.edu/faculty", "reason": "faculty directory"}
                        ],
                    }
                ]

        provider = MockLLMProvider()
        decisions = provider.classify_candidates(
            prompt="", professor_name="Ada", canonical_homepage="https://ada.github.io/",
            candidates=self.candidates, homepage_graph=self.graph,
        )
        self.assertFalse(provider.used_fallback)
        self.assertEqual(len(decisions), 1)
        d = decisions[0]
        self.assertAlmostEqual(d.confidence, 0.93)
        self.assertIn("Current Members section", d.evidence)

    def test_invalid_url_in_llm_response_rejected(self):
        class BadURLProvider(LLMResearchGroupNavigatorProvider):
            def _invoke_llm(self, prompt, graph_repr):
                return [
                    {
                        "candidate_url": "https://not-in-candidates.com/",
                        "confidence": 0.95,
                        "reason": "invented url",
                    }
                ]

        provider = BadURLProvider()
        decisions = provider.classify_candidates(
            prompt="", professor_name="Ada", canonical_homepage="https://ada.github.io/",
            candidates=self.candidates, homepage_graph=self.graph,
        )
        self.assertTrue(provider.used_fallback)

    def test_exception_in_invoke_triggers_fallback(self):
        class CrashingProvider(LLMResearchGroupNavigatorProvider):
            def _invoke_llm(self, prompt, graph_repr):
                raise RuntimeError("API down")

        provider = CrashingProvider()
        decisions = provider.classify_candidates(
            prompt="", professor_name="Ada", canonical_homepage="https://ada.github.io/",
            candidates=self.candidates, homepage_graph=self.graph,
        )
        self.assertTrue(provider.used_fallback)
        self.assertTrue(len(decisions) > 0)


# ─────────────────────────────────────────────────────────────────────────────
# ResearchGroupNavigator
# ─────────────────────────────────────────────────────────────────────────────

class TestResearchGroupNavigator(unittest.TestCase):
    def setUp(self):
        self.graph = _lab_graph()
        self.navigator = ResearchGroupNavigator(provider=_stub_provider())

    def test_navigate_returns_decisions_with_navigation_score(self):
        decisions = self.navigator.navigate("Ada Lovelace", self.graph)
        self.assertTrue(len(decisions) > 0)
        for d in decisions:
            self.assertIsInstance(d.navigation_score, NavigationScore)

    def test_select_returns_group_page_selection(self):
        decisions = self.navigator.navigate("Ada Lovelace", self.graph)
        selection = self.navigator.select(decisions, self.graph)
        self.assertIsNotNone(selection)
        self.assertIsInstance(selection, GroupPageSelection)

    def test_select_builds_navigation_path(self):
        decisions = self.navigator.navigate("Ada Lovelace", self.graph)
        selection = self.navigator.select(decisions, self.graph)
        self.assertIsNotNone(selection)
        self.assertIsInstance(selection.navigation_path, list)
        self.assertTrue(len(selection.navigation_path) >= 1)

    def test_navigation_path_includes_original_and_canonical_when_different(self):
        graph = _lab_graph()
        graph.original_homepage = "https://www.cs.example.edu/people/profile/ada"
        graph.canonical_homepage = "https://ada.github.io/"
        decisions = self.navigator.navigate("Ada", graph)
        selection = self.navigator.select(decisions, graph)
        self.assertIsNotNone(selection)
        path = selection.navigation_path
        self.assertIn("https://www.cs.example.edu/people/profile/ada", path)
        self.assertIn("https://ada.github.io/", path)

    def test_navigate_and_select_convenience(self):
        selection = self.navigator.navigate_and_select("Ada Lovelace", self.graph)
        self.assertIsNotNone(selection)
        self.assertEqual(selection.navigation_provider, "heuristic")

    def test_select_returns_none_when_no_eligible_decisions(self):
        selection = self.navigator.select([], self.graph)
        self.assertIsNone(selection)

    def test_select_respects_min_threshold(self):
        low_confidence_decision = ResearchGroupNavigationDecision(
            candidate_url="https://example.com/faculty-directory",
            candidate_type="people_page",
            reason="low score",
            navigation_score=NavigationScore(provider_score=0.1),
        )
        selection = self.navigator.select([low_confidence_decision], self.graph)
        self.assertIsNone(selection)

    def test_selection_carries_evidence(self):
        decisions = self.navigator.navigate("Ada Lovelace", self.graph)
        selection = self.navigator.select(decisions, self.graph)
        self.assertIsNotNone(selection)
        self.assertIsInstance(selection.evidence, list)

    def test_selection_carries_navigation_score(self):
        decisions = self.navigator.navigate("Ada Lovelace", self.graph)
        selection = self.navigator.select(decisions, self.graph)
        self.assertIsNotNone(selection)
        self.assertIsInstance(selection.navigation_score, NavigationScore)


# ─────────────────────────────────────────────────────────────────────────────
# NavigationDebugWriter
# ─────────────────────────────────────────────────────────────────────────────

class TestNavigationDebugWriter(unittest.TestCase):
    def _make_graph(self) -> ResearchGroupGraph:
        return ResearchGroupGraph(
            professor_name="Ada Lovelace",
            professor_homepage="https://ada.github.io/",
            original_homepage="https://www.cs.example.edu/people/profile/ada",
            canonical_homepage="https://ada.github.io/",
            navigation_path=[
                "https://www.cs.example.edu/people/profile/ada",
                "https://ada.github.io/",
                "https://ada.github.io/lab/",
            ],
            navigation_provider="heuristic",
            group_page=GroupPageSelection(
                url="https://ada.github.io/lab/",
                source_node_type="lab_page",
                confidence=0.88,
                reason="lab page detected",
                navigation_path=["https://ada.github.io/"],
                evidence=["node_type:lab_page"],
                navigation_score=NavigationScore(provider_score=0.88),
            ),
            fetch_status="success",
        )

    def test_write_creates_json_file(self):
        graph = self._make_graph()
        with tempfile.TemporaryDirectory() as tmp:
            path = NavigationDebugWriter.from_graphs([graph], output_dir=tmp)
            self.assertTrue(Path(path).exists())

    def test_written_json_is_parseable(self):
        graph = self._make_graph()
        with tempfile.TemporaryDirectory() as tmp:
            path = NavigationDebugWriter.from_graphs([graph], output_dir=tmp)
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertIn("entries", data)
            self.assertEqual(len(data["entries"]), 1)

    def test_entry_contains_required_keys(self):
        graph = self._make_graph()
        with tempfile.TemporaryDirectory() as tmp:
            path = NavigationDebugWriter.from_graphs([graph], output_dir=tmp)
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            entry = data["entries"][0]
            for key in (
                "professor_name",
                "canonical_homepage",
                "original_homepage",
                "navigation_provider",
                "selected",
                "fetch_status",
            ):
                self.assertIn(key, entry, msg=f"Missing key: {key}")

    def test_selected_entry_has_evidence(self):
        graph = self._make_graph()
        with tempfile.TemporaryDirectory() as tmp:
            path = NavigationDebugWriter.from_graphs([graph], output_dir=tmp)
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            selected = data["entries"][0]["selected"]
            self.assertIsNotNone(selected)
            self.assertIn("evidence", selected)


# ─────────────────────────────────────────────────────────────────────────────
# Regression: heuristic vs LLM-fallback produce same decision shape
# ─────────────────────────────────────────────────────────────────────────────

class TestNavigatorRegressionHeuristicVsLLMFallback(unittest.TestCase):
    def setUp(self):
        self.graph = _lab_graph()
        self.candidates = [
            GroupPageCandidate(
                url="https://ada.github.io/lab/",
                node_type="lab_page",
                anchor_text="Lab Members",
                graph_confidence=0.9,
            )
        ]

    def test_both_return_decisions_with_same_fields(self):
        stub = StubResearchGroupNavigatorProvider()
        llm = LLMResearchGroupNavigatorProvider()

        stub_decisions = stub.classify_candidates(
            prompt="", professor_name="Ada", canonical_homepage="https://ada.github.io/",
            candidates=self.candidates, homepage_graph=self.graph,
        )
        llm_decisions = llm.classify_candidates(
            prompt="", professor_name="Ada", canonical_homepage="https://ada.github.io/",
            candidates=self.candidates, homepage_graph=self.graph,
        )

        for decisions in (stub_decisions, llm_decisions):
            for d in decisions:
                self.assertTrue(hasattr(d, "candidate_url"))
                self.assertTrue(hasattr(d, "confidence"))
                self.assertTrue(hasattr(d, "navigation_score"))
                self.assertTrue(hasattr(d, "evidence"))
                self.assertTrue(hasattr(d, "navigation_path"))
                self.assertTrue(hasattr(d, "rejected_candidates"))

    def test_both_select_same_url_for_clear_candidate(self):
        stub_nav = ResearchGroupNavigator(provider=StubResearchGroupNavigatorProvider())
        llm_nav = ResearchGroupNavigator(provider=LLMResearchGroupNavigatorProvider())

        stub_sel = stub_nav.navigate_and_select("Ada Lovelace", self.graph)
        llm_sel = llm_nav.navigate_and_select("Ada Lovelace", self.graph)

        self.assertIsNotNone(stub_sel)
        self.assertIsNotNone(llm_sel)
        self.assertEqual(stub_sel.url, llm_sel.url)

    def test_pipeline_provider_agnostic_group_selection(self):
        """
        Pipeline.group_discoverer.select() returns GroupPageSelection for both
        stub and LLM-fallback navigators without any pipeline changes.
        """
        from research_group_agent.group_discovery import GroupPageDiscoverer

        stub_discoverer = GroupPageDiscoverer(
            navigator=ResearchGroupNavigator(provider=StubResearchGroupNavigatorProvider())
        )
        llm_discoverer = GroupPageDiscoverer(
            navigator=ResearchGroupNavigator(provider=LLMResearchGroupNavigatorProvider())
        )

        stub_sel = stub_discoverer.select(self.graph)
        llm_sel = llm_discoverer.select(self.graph)

        self.assertIsNotNone(stub_sel)
        self.assertIsNotNone(llm_sel)
        self.assertIsInstance(stub_sel, GroupPageSelection)
        self.assertIsInstance(llm_sel, GroupPageSelection)


if __name__ == "__main__":
    unittest.main()
