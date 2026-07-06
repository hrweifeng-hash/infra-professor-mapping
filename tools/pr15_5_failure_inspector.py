#!/usr/bin/env python3
"""
PR15.5 — Failure Inspector

Explains every failed research group page with structured diagnostics.
Reads only existing output artifacts and the local HTML cache; never
re-fetches pages over the network and never modifies pipeline code.

Usage:
    python3.11 tools/pr15_5_failure_inspector.py

Requires Python 3.11+ (same as the rest of the pipeline).

Outputs:
    data/output/FAILED_GROUP_PAGES.json
    data/output/FAILED_GROUP_PAGES.md
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from statistics import mean
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research_group_agent.page_classifier import PageClassifier, PageType
from research_group_agent.parser import MemberPageParser
from research_group_agent.precision_constants import (
    ALUMNI_SECTION_KEYWORDS,
    CURRENT_SECTION_KEYWORDS,
    SKIP_SECTION_KEYWORDS,
)

OUTPUT_DIR = Path("data/output")
CACHE_DIR_RG = Path("data/cache/research_groups")
CACHE_DIR_HP = Path("data/cache/homepages")

GRAPH_FILE = OUTPUT_DIR / "research_group_graph.json"
DEBUG_FILE = OUTPUT_DIR / "NAVIGATION_DEBUG.json"
HOMEPAGE_FILE = OUTPUT_DIR / "homepage_graph.json"

# ─────────────────────────────────────────────────────────────────────────────
# Failure categories (canonical keys → display labels)
# ─────────────────────────────────────────────────────────────────────────────

FAILURE_CATEGORIES: dict[str, str] = {
    "no_homepage": "No Homepage",
    "fetch_failure": "Fetch Failure",
    "department_directory": "Department Directory",
    "landing_page": "Landing Page",
    "dynamic_html": "Dynamic HTML",
    "section_detection_failure": "Section Detection Failure",
    "unsupported_html_structure": "Unsupported HTML Structure",
    "profile_detection_failure": "Profile Detection Failure",
    "no_current_members": "No Current Members",
    "unknown": "Unknown",
}

_ALL_MEMBER_KEYWORDS: frozenset[str] = (
    frozenset(CURRENT_SECTION_KEYWORDS) | frozenset(ALUMNI_SECTION_KEYWORDS)
)

_MEMBER_RELATED_WORDS: frozenset[str] = frozenset({
    "member", "members", "student", "students", "phd", "doctoral",
    "postdoc", "postdoctoral", "researcher", "researchers", "people",
    "team", "personnel", "group", "lab", "collaborator", "collaborators",
    "graduate", "alumni", "advisor", "current",
})

# Plain-text section header patterns (not h1-h4; used as visual separators)
_PLAIN_SECTION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"current\s+(?:ph\.?d\.?|doctoral|graduate|master)?\s*students",
        r"(?:ph\.?d\.?|doctoral|graduate)\s+students\s*(?::|$)",
        r"graduated?\s+(?:ph\.?d\.?|doctoral|students)",
        r"(?:current|lab|group)\s+members\s*(?::|$)",
        r"postdoc(?:toral)?\s+researchers?\s*(?::|$)",
        r"past\s+(?:members|students|postdocs)",
        r"former\s+(?:members|students)",
        r"alumni\s*(?::|$)",
        r"our\s+team\s*(?::|$)",
        r"(?:research\s+)?personnel\s*(?::|$)",
    ]
]


# ─────────────────────────────────────────────────────────────────────────────
# Heading + SPA signal extractor (standalone, no pipeline imports)
# ─────────────────────────────────────────────────────────────────────────────

class _HeadingExtractor(HTMLParser):
    """Extract all h1–h4 headings and detect SPA/dynamic-render patterns."""

    _HEADING_TAGS: frozenset[str] = frozenset({"h1", "h2", "h3", "h4"})

    _SPA_SIGNATURES: dict[str, list[str]] = {
        "React": [
            "data-reactroot", "data-reactid", "__reactfiber",
            "createelement", "reactdom", "_reactroot",
        ],
        "Vue.js": ["__vue__", "v-app", "vue.js", "vuejs", "v-bind"],
        "Angular": ["ng-app", "ng-version", "angular.js", "ng-controller"],
        "Next.js": ["__next_data", "__next_loaded_pages", "_next/static"],
        "Nuxt.js": ["__nuxt", "_nuxt/"],
        "Gatsby": ["___gatsby", "gatsby-focus-wrapper"],
        "Svelte": ["svelte", "__svelte"],
        "Ember": ["ember-application", "ember.js"],
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: list[tuple[str, str]] = []
        self._in_heading = False
        self._current_tag = ""
        self._heading_parts: list[str] = []
        self._in_skip = 0
        self._script_parts: list[str] = []
        self._in_script = False
        self._visible_chars = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._in_skip += 1
            if tag == "script":
                self._in_script = True
            return
        if self._in_skip:
            return
        if tag in self._HEADING_TAGS:
            self._in_heading = True
            self._current_tag = tag
            self._heading_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            if self._in_skip:
                self._in_skip -= 1
            if tag == "script":
                self._in_script = False
            return
        if self._in_skip:
            return
        if tag in self._HEADING_TAGS and self._in_heading and tag == self._current_tag:
            text = " ".join(self._heading_parts).strip()
            if text:
                self.headings.append((tag, text))
            self._in_heading = False
            self._heading_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._script_parts.append(data)
            return
        if self._in_skip:
            return
        stripped = data.strip()
        if stripped:
            self._visible_chars += len(stripped)
        if self._in_heading:
            self._heading_parts.append(data)

    def detect_spa_frameworks(self) -> list[str]:
        script_lower = " ".join(self._script_parts).lower()
        detected = []
        for name, patterns in self._SPA_SIGNATURES.items():
            if any(p in script_lower for p in patterns):
                detected.append(name)
        return detected

    def visible_text_ratio(self, html_bytes: int) -> float:
        if html_bytes == 0:
            return 0.0
        return round(self._visible_chars / html_bytes, 4)


# ─────────────────────────────────────────────────────────────────────────────
# Cache helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_url(url: str) -> str | None:
    url = (url or "").strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _read_cached_html(url: str, cache_dir: Path) -> tuple[str | None, str | None]:
    """Return (html, final_url) from cache, or (None, None) if not cached."""
    normalized = _normalize_url(url)
    if not normalized:
        return None, None
    key = _cache_key(normalized)
    html_path = cache_dir / f"{key}.html"
    meta_path = cache_dir / f"{key}.meta"
    if not html_path.exists():
        return None, None
    html = html_path.read_text(encoding="utf-8", errors="replace")
    final_url = normalized
    if meta_path.exists():
        for line in meta_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("final_url="):
                final_url = line.split("=", 1)[1]
    return html, final_url


# ─────────────────────────────────────────────────────────────────────────────
# Per-page diagnostics
# ─────────────────────────────────────────────────────────────────────────────

def _extract_heading_signals(html: str) -> dict[str, Any]:
    """Run the heading extractor and produce signal dict."""
    extractor = _HeadingExtractor()
    extractor.feed(html)
    extractor.close()

    html_bytes = len(html.encode("utf-8"))
    visible_ratio = extractor.visible_text_ratio(html_bytes)
    spa_frameworks = extractor.detect_spa_frameworks()

    all_headings = [text for _, text in extractor.headings]

    # Headings containing any member-related word (by any word in heading)
    member_adjacent = [
        h for h in all_headings
        if any(w in h.lower() for w in _MEMBER_RELATED_WORDS)
    ]

    # Headings whose normalized form matches a known section keyword
    matched_keywords = [
        h for h in all_headings
        if any(kw in h.lower() for kw in _ALL_MEMBER_KEYWORDS)
    ]

    # Headings that look member-related but don't match any known keyword
    unmatched_member = [h for h in member_adjacent if h not in matched_keywords]

    is_likely_dynamic = (
        (visible_ratio < 0.02 and html_bytes > 5_000)
        or (bool(spa_frameworks) and visible_ratio < 0.05)
    )

    # CSS card/grid/profile pattern detection
    has_card_pattern = bool(re.search(
        r'class=["\'][^"\']*\b(?:card|grid|tile|profile|person-card|people-card|'
        r'team-member|faculty-card|student-card)\b[^"\']*["\']',
        html,
        re.IGNORECASE,
    ))

    has_member_keywords_in_html = any(w in html.lower() for w in _MEMBER_RELATED_WORDS)

    # Plain text section header detection (no h1-h4 elements)
    plain_text_for_sections = re.sub(r"<[^>]+>", " ", html)
    plain_text_for_sections = re.sub(r"\s+", " ", plain_text_for_sections)
    plain_section_matches = []
    for pat in _PLAIN_SECTION_PATTERNS:
        m = pat.search(plain_text_for_sections)
        if m:
            plain_section_matches.append(m.group(0).strip())

    # Heuristic: if there are no headings but there IS plain-text member content
    # AND the HTML uses no heading elements at all → unsupported plain-text structure
    uses_plain_text_sections = bool(plain_section_matches) and len(all_headings) == 0

    return {
        "html_size_bytes": html_bytes,
        "visible_text_ratio": visible_ratio,
        "is_likely_dynamic": is_likely_dynamic,
        "spa_frameworks": spa_frameworks,
        "all_headings": all_headings[:60],
        "member_adjacent_headings": member_adjacent,
        "matched_section_headings": matched_keywords,
        "unmatched_member_headings": unmatched_member,
        "has_member_keywords_in_html": has_member_keywords_in_html,
        "has_card_or_grid_pattern": has_card_pattern,
        "plain_section_matches": plain_section_matches,
        "uses_plain_text_sections": uses_plain_text_sections,
    }


def _run_parser(html: str, base_url: str) -> tuple[dict[str, Any], Any]:
    """Run MemberPageParser; return (diagnostic dict, ParsedMemberPage)."""
    parsed = MemberPageParser().parse(html, base_url=base_url)

    member_sections = [s for s in parsed.sections if s.is_member_section]
    current_sections = [
        s for s in member_sections
        if s.member_status.value == "CURRENT" and s.entry_count > 0
    ]

    section_dicts = [
        {
            "name": s.name,
            "role": s.role.value,
            "is_member_section": s.is_member_section,
            "member_status": s.member_status.value,
            "entry_count": s.entry_count,
        }
        for s in parsed.sections
    ]

    return {
        "page_title": parsed.page_title,
        "total_sections_detected": len(parsed.sections),
        "sections": section_dicts,
        "section_names": [s.name for s in parsed.sections],
        "member_section_count": len(member_sections),
        "current_member_section_count": len(current_sections),
        "member_section_names": [s.name for s in member_sections],
        "total_entries_parsed": len(parsed.entries),
        "total_links_found": len(parsed.all_links),
        "visible_text_length": len(parsed.visible_text),
    }, parsed


def _run_classifier(parsed: Any, base_url: str, page_title: str) -> dict[str, Any]:
    """Run PageClassifier; return diagnostic dict."""
    result = PageClassifier().classify(
        parsed=parsed,
        page_url=base_url,
        page_title=page_title,
    )
    return {
        "page_type": result.page_type.value,
        "confidence": result.confidence,
        "is_acceptable": result.is_acceptable,
        "reason": result.reason,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Failure categorization
# ─────────────────────────────────────────────────────────────────────────────

def _categorize(
    graph: dict,
    signals: dict | None,
    parser_diag: dict | None,
    classifier_diag: dict | None,
    homepage_graph: dict | None,
) -> str:
    fetch_status = graph.get("fetch_status", "unknown")
    errors = " ".join(graph.get("errors", [])).lower()

    # Skipped entirely — no group page candidate in HomepageGraph
    if fetch_status == "skipped":
        if homepage_graph and homepage_graph.get("fetch_status") in (
            "network_error", "timeout", "http_error", "empty_response", "invalid_url"
        ):
            return "fetch_failure"
        return "no_homepage"

    # Hard network/HTTP failure at the group page fetch stage
    if fetch_status in (
        "timeout", "http_error", "network_error", "invalid_url", "empty_response"
    ):
        return "fetch_failure"

    # Page was fetched but rejected by classifier or parser
    if fetch_status == "page_rejected":
        if signals and signals.get("is_likely_dynamic"):
            return "dynamic_html"

        if classifier_diag:
            pt = classifier_diag.get("page_type", "")
            if pt in ("faculty_directory", "department_directory"):
                return "department_directory"
            if pt in ("administrative_page", "course_page"):
                return "landing_page"
            if pt == "generic_homepage":
                return "landing_page"
            if pt in ("project_page", "research_area_page"):
                return "landing_page"

        if parser_diag and parser_diag["member_section_count"] == 0:
            if signals:
                # Plain text structure (no headings but member content exists)
                if signals.get("uses_plain_text_sections"):
                    return "unsupported_html_structure"
                if signals.get("unmatched_member_headings"):
                    return "section_detection_failure"
                if signals.get("has_card_or_grid_pattern") and signals.get(
                    "has_member_keywords_in_html"
                ):
                    return "unsupported_html_structure"
                if signals.get("has_member_keywords_in_html"):
                    return "section_detection_failure"
            return "section_detection_failure"

        return "section_detection_failure"

    # Fetch succeeded but zero members
    if fetch_status == "success" and graph.get("member_count", 0) == 0:
        if "no current members passed precision validation" in errors:
            return "profile_detection_failure"
        if parser_diag:
            if parser_diag["member_section_count"] > 0 and parser_diag["total_entries_parsed"] == 0:
                return "profile_detection_failure"
        return "no_current_members"

    return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Fix suggestions
# ─────────────────────────────────────────────────────────────────────────────

def _suggest_fix(
    category: str,
    signals: dict | None,
    parser_diag: dict | None,
    classifier_diag: dict | None,
    graph: dict,
    homepage_graph: dict | None,
) -> str:
    if category == "no_homepage":
        if homepage_graph:
            hp_nodes = homepage_graph.get("graph_nodes", [])
            node_types = [n.get("node_type") for n in hp_nodes]
            if node_types:
                types_str = ", ".join(node_types)
                return (
                    f"HomepageGraph only contains: [{types_str}]. "
                    "No lab/group/people page link was discovered. "
                    "Possible causes: (1) homepage uses Google Sites / JavaScript navigation "
                    "that the static HP agent cannot crawl; (2) the lab page link text does not "
                    "match GROUP_ANCHOR_POSITIVE keywords; (3) the professor lists students only "
                    "on their personal page without a dedicated lab URL. "
                    "Fix: expand HomepagePipeline anchor scoring for Google Sites or add "
                    "a second navigation hop."
                )
        return (
            "No HomepageGraph data available. "
            "Run tools/homepage_agent_run.py to generate homepage graph first, "
            "then re-run the research group pipeline."
        )

    if category == "fetch_failure":
        if homepage_graph and homepage_graph.get("fetch_status") in (
            "network_error", "timeout", "http_error"
        ):
            err = "; ".join(homepage_graph.get("errors", ["unknown"]))
            return (
                f"Homepage fetch itself failed ({err}). "
                "Group page was never reachable. "
                "Fix: retry with a longer timeout, use a proxy, or skip this professor."
            )
        err = "; ".join(graph.get("errors", ["unknown"]))
        return (
            f"Group page HTTP fetch failed: {err}. "
            "Retry with a higher timeout or verify the URL is still live."
        )

    if category == "dynamic_html":
        fw = signals.get("spa_frameworks", []) if signals else []
        ratio = signals.get("visible_text_ratio", 0.0) if signals else 0.0
        fw_str = f" ({', '.join(fw)})" if fw else ""
        return (
            f"Page is JavaScript-rendered{fw_str} — visible text ratio is only {ratio:.1%}. "
            "The static HTML parser receives near-empty content. "
            "Fix: (1) add a headless-browser fetch path (Playwright/Puppeteer) for SPA pages; "
            "(2) look for a server-side-rendered sitemap or /people.json endpoint; "
            "(3) check if the page has a static fallback URL."
        )

    if category == "department_directory":
        pt = classifier_diag.get("page_type", "unknown") if classifier_diag else "unknown"
        conf = classifier_diag.get("confidence", 0.0) if classifier_diag else 0.0
        group_url = (graph.get("group_page") or {}).get("url", "")
        return (
            f"PageClassifier identified this URL as '{pt}' (confidence={conf:.2f}). "
            f"URL: {group_url}. "
            "This is likely a department-level page, not the professor's personal lab page. "
            "Fix: (1) improve canonical homepage resolution to land on the professor's personal "
            "page first; (2) add stricter URL filtering in GroupPageDiscoverer to reject "
            "department-level URLs."
        )

    if category == "landing_page":
        pt = classifier_diag.get("page_type", "unknown") if classifier_diag else "unknown"
        all_h = (signals.get("all_headings", []) if signals else [])[:5]
        h_str = ", ".join(f'"{h}"' for h in all_h) if all_h else "none found"
        return (
            f"Page classified as '{pt}' — this is a lab landing/research page, "
            "not a member roster. "
            f"Top headings: {h_str}. "
            "Fix: add a second navigation hop from this landing page to find the "
            "members/people sub-page (e.g. /people, /members, /students)."
        )

    if category == "section_detection_failure":
        unmatched = (signals.get("unmatched_member_headings", []) if signals else [])[:8]
        all_h = (signals.get("all_headings", []) if signals else [])[:10]
        wrong_page = (signals or {}).get("wrong_page_detected", False)

        if wrong_page:
            group_url = (graph.get("group_page") or {}).get("url", "")
            pr = parser_diag or {}
            title = pr.get("page_title", "unknown")
            return (
                f"WRONG PAGE NAVIGATED: the selected URL ({group_url}) belongs to a "
                f"different person (page title: '{title}'). "
                "The navigator followed a link on the professor's homepage that points "
                "to a collaborator's or colleague's page rather than the professor's own lab. "
                "Fix: (1) add cross-professor name verification to GroupPageDiscoverer — "
                "reject candidates whose page title does not contain the professor's name "
                "or institution; (2) add the URL pattern to the navigator's denylist."
            )

        if unmatched:
            kw_list = ", ".join(f'"{h}"' for h in unmatched)
            return (
                f"Page has member-related headings not in CURRENT_SECTION_KEYWORDS: {kw_list}. "
                "Fix: add normalized versions of these headings to "
                "CURRENT_SECTION_KEYWORDS in research_group_agent/precision_constants.py. "
                "For example: add the lowercase exact match of the heading text."
            )

        if all_h:
            h_preview = ", ".join(f'"{h}"' for h in all_h)
            return (
                f"Page headings found: {h_preview}. "
                "None of these headings matched CURRENT_SECTION_KEYWORDS or ALUMNI_SECTION_KEYWORDS. "
                "Fix: review these headings and add matching entries to precision_constants.py. "
                "Members may also be organized by CSS class/div without heading elements."
            )

        if signals and signals.get("has_member_keywords_in_html"):
            return (
                "Page contains member-related words in HTML body but no h1–h4 headings "
                "matched section keywords. Members may be listed without standard HTML heading "
                "elements — possibly using bold text, divs, or CSS classes as visual separators. "
                "Fix: extend MemberPageParser to handle div/span-based section boundaries."
            )

        return (
            "Parser found zero headings on the page. "
            "The page may be very minimal, use only CSS styling for structure, "
            "or be a redirected/error page. "
            "Fix: inspect the cached HTML and check if the page rendered correctly."
        )

    if category == "unsupported_html_structure":
        ratio = signals.get("visible_text_ratio", 0.0) if signals else 0.0
        plain_matches = signals.get("plain_section_matches", []) if signals else []
        has_cards = signals.get("has_card_or_grid_pattern", False) if signals else False

        if plain_matches:
            pattern_str = "; ".join(f'"{p}"' for p in plain_matches[:4])
            return (
                f"Page uses plain-text section headers instead of h1–h4 elements. "
                f"Detected patterns: {pattern_str}. "
                "The section-aware parser only recognizes headings inside <h1>–<h4> tags. "
                "Fix: extend _SectionAwareParser to recognize plain-text section delimiters "
                "(lines ending in ':', text before a list, or strong/bold elements as "
                "section markers)."
            )
        if has_cards:
            return (
                f"Page lists members in a CSS grid/card layout (card pattern detected, "
                f"visible text ratio={ratio:.1%}). "
                "The parser relies on h1–h4 headings before member lists. "
                "Fix: add a profile-card container parser to MemberPageParser."
            )
        return (
            f"Page has no h1–h4 headings and uses a non-standard layout "
            f"(visible text ratio={ratio:.1%}). "
            "Members may be in plain text, tables, or CSS-styled containers. "
            "Fix: inspect the cached HTML and add a dedicated parser for this page structure."
        )

    if category == "profile_detection_failure":
        parser_sections = (parser_diag.get("member_section_names", []) if parser_diag else [])
        entries = parser_diag.get("total_entries_parsed", 0) if parser_diag else 0
        s_str = ", ".join(f'"{s}"' for s in parser_sections) if parser_sections else "none"
        return (
            f"Parser found member sections [{s_str}] with {entries} raw entries, "
            "but all were rejected by PersonValidator/precision filters. "
            "Fix: (1) check if extracted names match PERSON_NEGATIVE_NAME_PATTERNS "
            "false-positive patterns; (2) verify the name regex _NAME_PATTERN covers "
            "the names on this page (non-Western names may fail the capitalization check)."
        )

    if category == "no_current_members":
        return (
            "Fetch and classification succeeded, but no current members were found. "
            "The page may list only alumni, or the professor's group may genuinely "
            "have no publicly listed current students. "
            "Fix: check if the page has an 'alumni-only' structure and ensure "
            "ALUMNI_SECTION_KEYWORDS are set correctly."
        )

    return (
        "Unable to determine root cause automatically. "
        "Manual inspection of the cached HTML is required."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Core inspector
# ─────────────────────────────────────────────────────────────────────────────

def _build_debug_index(debug: dict | None) -> dict[str, dict]:
    if not debug:
        return {}
    return {e["professor_name"]: e for e in debug.get("entries", [])}


def _build_homepage_index(homepage_graphs: list[dict]) -> dict[str, dict]:
    return {g["professor_name"]: g for g in homepage_graphs}


def _is_failed(graph: dict) -> bool:
    """A professor is 'failed' if members == 0 or fetch didn't fully succeed."""
    return graph.get("member_count", 0) == 0


def inspect_one(
    graph: dict,
    debug_entry: dict | None,
    homepage_graph: dict | None,
) -> dict[str, Any]:
    """Produce a complete failure record for one professor."""
    name = graph["professor_name"]
    group_page = graph.get("group_page")
    group_url = group_page["url"] if group_page else None
    fetch_status = graph.get("fetch_status", "unknown")

    # Attempt to load cached HTML for pages that were fetched
    html: str | None = None
    final_url: str | None = None

    if group_url and fetch_status in ("page_rejected", "success"):
        html, final_url = _read_cached_html(group_url, CACHE_DIR_RG)
        # Fallback: try homepage cache if not in rg cache
        if html is None:
            html, final_url = _read_cached_html(group_url, CACHE_DIR_HP)

    # Run diagnostics on HTML when available
    signals: dict | None = None
    parser_diag: dict | None = None
    classifier_diag: dict | None = None

    if html:
        base_url = final_url or group_url or ""
        signals = _extract_heading_signals(html)
        parser_diag, parsed_obj = _run_parser(html, base_url)
        classifier_diag = _run_classifier(
            parsed_obj,
            base_url,
            parser_diag.get("page_title", ""),
        )
    elif fetch_status not in ("skipped",) and group_url:
        # Fetched but not in cache (fetch failure stored in graph errors)
        signals = None
        parser_diag = None
        classifier_diag = None

    # Navigation data
    nav_path = graph.get("navigation_path", [])
    nav_score: dict | None = None
    nav_evidence: list[str] = []
    if group_page:
        nav_score = group_page.get("navigation_score")
        nav_evidence = group_page.get("evidence", [])

    # Debug entry navigation score (more complete)
    if debug_entry and debug_entry.get("selected"):
        sel = debug_entry["selected"]
        nav_score = nav_score or sel.get("navigation_score")
        nav_evidence = nav_evidence or sel.get("evidence", [])

    # ── Wrong-page detection ────────────────────────────────────────────────
    # Detect if the fetched page title looks like a DIFFERENT person's name.
    # Only fires for personal-name-style titles (e.g. "Owolabi Legunsen"),
    # NOT for lab names (e.g. "SAIL@Princeton", "Berkeley NetSys Lab").
    _LAB_TITLE_WORDS: frozenset[str] = frozenset({
        "lab", "laboratory", "systems", "system", "network", "networking",
        "research", "group", "institute", "center", "university", "home",
        "computing", "computer", "science", "engineering", "technology",
        "department", "distributed", "netsys", "sail", "dsl", "symbiotic",
        "homepage", "page", "website", "portal",
    })
    _lab_word_re = re.compile(
        r"\b(" + "|".join(re.escape(w) for w in sorted(_LAB_TITLE_WORDS, key=len, reverse=True)) + r")\b",
        re.IGNORECASE,
    )

    def _is_personal_name_title(title: str) -> bool:
        if not title or len(title) > 60:
            return False
        if any(c in title for c in ("@", "|", "–", "—", "#", "/", ".", ":", "!")):
            return False
        if _lab_word_re.search(title):
            return False
        parts = title.strip().split()
        if not (2 <= len(parts) <= 4):
            return False
        return all(p and p[0].isupper() and p.replace("-", "").isalpha() for p in parts)

    wrong_page_signal: bool | None = None  # None = no HTML available
    if html:
        page_title_from_parser = (parser_diag or {}).get("page_title", "") or ""
        page_title_lower = page_title_from_parser.lower()
        wrong_page_signal = False
        if page_title_lower and _is_personal_name_title(page_title_from_parser):
            name_tokens = [t.lower() for t in name.split() if len(t) > 2]
            name_tokens = [t for t in name_tokens if t not in ("0001", "0002", "0003")]
            if name_tokens:
                wrong_page_signal = not any(t in page_title_lower for t in name_tokens)

    # Inject wrong_page_signal into raw signals so _suggest_fix can use it
    if signals is not None:
        signals["wrong_page_detected"] = wrong_page_signal

    # Categorize
    category = _categorize(graph, signals, parser_diag, classifier_diag, homepage_graph)
    category_label = FAILURE_CATEGORIES.get(category, "Unknown")

    # Suggest fix
    fix = _suggest_fix(category, signals, parser_diag, classifier_diag, graph, homepage_graph)

    # ── Visible signals summary (JSON output) ───────────────────────────────
    visible_signals_summary: dict[str, Any] = {}
    if signals:
        visible_signals_summary = {
            "html_size_bytes": signals["html_size_bytes"],
            "visible_text_ratio": signals["visible_text_ratio"],
            "is_likely_dynamic": signals["is_likely_dynamic"],
            "spa_frameworks": signals["spa_frameworks"],
            "has_member_keywords_in_html": signals["has_member_keywords_in_html"],
            "has_card_or_grid_pattern": signals["has_card_or_grid_pattern"],
            "uses_plain_text_sections": signals.get("uses_plain_text_sections", False),
            "plain_section_matches": signals.get("plain_section_matches", []),
            "wrong_page_detected": wrong_page_signal,
        }

    # Homepage graph context
    hp_context: dict[str, Any] = {}
    if homepage_graph:
        hp_nodes = homepage_graph.get("graph_nodes", [])
        hp_context = {
            "hp_fetch_status": homepage_graph.get("fetch_status"),
            "hp_node_types": [n.get("node_type") for n in hp_nodes],
            "hp_url": homepage_graph.get("homepage_url"),
        }

    return {
        "professor": name,
        "original_homepage": graph.get("original_homepage") or graph.get("professor_homepage"),
        "canonical_homepage": graph.get("canonical_homepage") or graph.get("professor_homepage"),
        "research_group_url": group_url,
        "fetch_status": fetch_status,
        "classifier_result": classifier_diag,
        "parser_result": {
            k: v for k, v in (parser_diag or {}).items()
        },
        "navigation_path": nav_path,
        "navigation_score": nav_score,
        "navigation_evidence": nav_evidence,
        "visible_signals": visible_signals_summary,
        "section_headings": (signals.get("all_headings", []) if signals else []),
        "detected_member_sections": (
            parser_diag.get("member_section_names", []) if parser_diag else []
        ),
        "unmatched_member_headings": (
            signals.get("unmatched_member_headings", []) if signals else []
        ),
        "rejected_reason": "; ".join(graph.get("errors", ["unknown"])),
        "failure_category": category,
        "failure_category_label": category_label,
        "suggested_fix": fix,
        "_homepage_context": hp_context,
        "_html_available": html is not None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────────────────────────────────────

def compute_statistics(records: list[dict], all_graphs: list[dict]) -> dict[str, Any]:
    total = len(all_graphs)
    failed = len(records)
    succeeded = sum(1 for g in all_graphs if g.get("member_count", 0) > 0)

    # Failure distribution
    category_counts: Counter[str] = Counter(r["failure_category"] for r in records)

    # Top raw rejection reasons
    reason_counts: Counter[str] = Counter()
    for r in records:
        reason = r.get("rejected_reason", "unknown")
        key = reason.split(":")[0].strip() if reason else "unknown"
        reason_counts[key] += 1

    # Most common section headings (from pages with HTML)
    all_headings: list[str] = []
    for r in records:
        all_headings.extend(r.get("section_headings", []))
    heading_counts: Counter[str] = Counter(all_headings)

    # Most common unmatched member headings (near-misses)
    unmatched: list[str] = []
    for r in records:
        unmatched.extend(r.get("unmatched_member_headings", []))
    unmatched_counts: Counter[str] = Counter(unmatched)

    # Unsupported layout patterns
    layout_issues: Counter[str] = Counter()
    wrong_page_count = 0
    for r in records:
        sigs = r.get("visible_signals", {})
        if sigs.get("is_likely_dynamic"):
            layout_issues["dynamic_spa"] += 1
        if sigs.get("has_card_or_grid_pattern"):
            layout_issues["css_card_grid"] += 1
        if sigs.get("uses_plain_text_sections"):
            layout_issues["plain_text_section_headers"] += 1
        if sigs.get("wrong_page_detected"):
            wrong_page_count += 1
            layout_issues["wrong_page_navigated"] += 1
        if (
            not sigs.get("is_likely_dynamic")
            and not sigs.get("has_card_or_grid_pattern")
            and not sigs.get("uses_plain_text_sections")
            and not r.get("section_headings")
            and r.get("_html_available")
        ):
            layout_issues["no_headings_found"] += 1

    # Most common rejection rules (classifier page types)
    classifier_types: Counter[str] = Counter()
    for r in records:
        cr = r.get("classifier_result") or {}
        if cr.get("page_type"):
            classifier_types[cr["page_type"]] += 1

    # Pages with HTML vs without
    with_html = sum(1 for r in records if r.get("_html_available"))
    without_html = failed - with_html

    # Navigation success but post-nav failure
    nav_success_post_fail = sum(
        1 for r in records
        if r.get("research_group_url") and r["failure_category"] not in (
            "no_homepage", "fetch_failure"
        )
    )

    return {
        "overview": {
            "total_professors": total,
            "succeeded_with_members": succeeded,
            "failed": failed,
            "success_rate": round(succeeded / (total or 1), 3),
            "failure_rate": round(failed / (total or 1), 3),
            "wrong_page_navigated": wrong_page_count,
        },
        "failure_distribution": {
            FAILURE_CATEGORIES.get(k, k): v
            for k, v in category_counts.most_common()
        },
        "failure_distribution_raw_keys": dict(category_counts.most_common()),
        "top_rejection_reasons": dict(reason_counts.most_common(15)),
        "most_common_section_headings": dict(heading_counts.most_common(20)),
        "unmatched_member_headings": dict(unmatched_counts.most_common(15)),
        "unsupported_layout_patterns": dict(layout_issues.most_common()),
        "classifier_page_type_distribution": dict(classifier_types.most_common()),
        "html_availability": {
            "records_with_cached_html": with_html,
            "records_without_html": without_html,
        },
        "post_navigation_failures": nav_success_post_fail,
        "post_navigation_failure_rate": round(
            nav_success_post_fail / max(
                sum(1 for g in all_graphs if g.get("group_page")), 1
            ),
            3,
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Markdown renderer
# ─────────────────────────────────────────────────────────────────────────────

def _pct(v: float) -> str:
    return f"{v:.0%}"


def _url(u: str | None) -> str:
    return f"`{u}`" if u else "—"


def render_markdown(records: list[dict], stats: dict, generated_at: str) -> str:
    lines: list[str] = []

    lines += [
        "# Failed Research Group Pages — Diagnostics Report",
        "",
        f"Generated: {generated_at}",
        f"Pipeline: **PR15** | Inspector: **PR15.5**",
        "",
        "> **Purpose:** Explain every failed research group page to guide future",
        "> parser and classifier improvements. Do not guess — use real failures.",
        "",
    ]

    # ── Executive Summary ────────────────────────────────────────────────────
    ov = stats["overview"]
    lines += [
        "## Executive Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total professors analyzed | **{ov['total_professors']}** |",
        f"| Succeeded with members | **{ov['succeeded_with_members']}** ({_pct(ov['success_rate'])}) |",
        f"| Failed (0 members) | **{ov['failed']}** ({_pct(ov['failure_rate'])}) |",
        f"| Post-navigation failures | **{stats['post_navigation_failures']}** ({_pct(stats['post_navigation_failure_rate'])}) |",
        f"| Wrong page navigated | **{ov.get('wrong_page_navigated', 0)}** |",
        f"| Records with cached HTML | **{stats['html_availability']['records_with_cached_html']}** |",
        "",
    ]

    # ── Failure Distribution ─────────────────────────────────────────────────
    lines += [
        "## Failure Distribution",
        "",
        "| Category | Count | Share |",
        "|----------|-------|-------|",
    ]
    total_failed = ov["failed"] or 1
    for label, count in stats["failure_distribution"].items():
        lines.append(f"| {label} | {count} | {_pct(count / total_failed)} |")
    lines.append("")

    # ── Top Rejection Reasons ────────────────────────────────────────────────
    lines += [
        "## Top Rejection Reasons",
        "",
        "| Reason | Count |",
        "|--------|-------|",
    ]
    for reason, count in list(stats["top_rejection_reasons"].items())[:10]:
        lines.append(f"| {reason} | {count} |")
    lines.append("")

    # ── Most Common Section Headings ─────────────────────────────────────────
    lines += [
        "## Most Common Section Headings (from failed pages)",
        "",
        "_These headings were found on failed pages. Member-adjacent headings that_",
        "_don't match CURRENT_SECTION_KEYWORDS are the primary fix candidates._",
        "",
        "| Heading | Count |",
        "|---------|-------|",
    ]
    for heading, count in list(stats["most_common_section_headings"].items())[:15]:
        lines.append(f"| `{heading}` | {count} |")
    lines.append("")

    # ── Unmatched Member Headings ────────────────────────────────────────────
    if stats["unmatched_member_headings"]:
        lines += [
            "## Unmatched Member Headings (Near-Miss Keywords)",
            "",
            "_These headings contain member-related words but are NOT in CURRENT_SECTION_KEYWORDS._",
            "_Adding them to precision_constants.py would immediately fix those pages._",
            "",
            "| Heading (as found on page) | Count | Suggested Keyword to Add |",
            "|----------------------------|-------|--------------------------|",
        ]
        for heading, count in list(stats["unmatched_member_headings"].items())[:15]:
            suggested = heading.lower().strip()
            lines.append(f"| `{heading}` | {count} | `\"{suggested}\"` |")
        lines.append("")

    # ── Unsupported Layout Patterns ──────────────────────────────────────────
    if stats["unsupported_layout_patterns"]:
        lines += [
            "## Unsupported Layout Patterns",
            "",
            "| Pattern | Count |",
            "|---------|-------|",
        ]
        for pattern, count in stats["unsupported_layout_patterns"].items():
            lines.append(f"| {pattern.replace('_', ' ').title()} | {count} |")
        lines.append("")

    # ── Classifier Page Type Distribution ────────────────────────────────────
    if stats["classifier_page_type_distribution"]:
        lines += [
            "## PageClassifier Type Distribution (failed pages)",
            "",
            "| Page Type | Count |",
            "|-----------|-------|",
        ]
        for pt, count in stats["classifier_page_type_distribution"].items():
            lines.append(f"| `{pt}` | {count} |")
        lines.append("")

    # ── Per-Professor Detail ─────────────────────────────────────────────────
    lines += [
        "## Per-Professor Failure Details",
        "",
        "_Each entry below is a fully diagnosed failure with root cause and suggested fix._",
        "",
    ]

    for i, r in enumerate(records, 1):
        outcome_icon = "✗"
        category_label = r["failure_category_label"]
        lines += [
            f"### {i}. {r['professor']} {outcome_icon}",
            "",
            "| Field | Value |",
            "|-------|-------|",
            f"| **Failure Category** | **{category_label}** |",
            f"| Professor | {r['professor']} |",
            f"| Original Homepage | {_url(r.get('original_homepage'))} |",
            f"| Canonical Homepage | {_url(r.get('canonical_homepage'))} |",
            f"| Research Group URL | {_url(r.get('research_group_url'))} |",
            f"| Fetch Status | `{r['fetch_status']}` |",
        ]

        cr = r.get("classifier_result") or {}
        if cr:
            lines += [
                f"| Classifier Page Type | `{cr.get('page_type', '—')}` |",
                f"| Classifier Confidence | {cr.get('confidence', 0.0):.3f} |",
                f"| Classifier Acceptable | {'Yes' if cr.get('is_acceptable') else 'No'} |",
            ]

        pr = r.get("parser_result") or {}
        if pr:
            lines += [
                f"| Parser: Sections Detected | {pr.get('total_sections_detected', 0)} |",
                f"| Parser: Member Sections | {pr.get('member_section_count', 0)} |",
                f"| Parser: Entries Parsed | {pr.get('total_entries_parsed', 0)} |",
            ]

        sigs = r.get("visible_signals") or {}
        if sigs:
            dyn = "Yes" if sigs.get("is_likely_dynamic") else "No"
            fw = ", ".join(sigs.get("spa_frameworks", [])) or "—"
            wrong = "**Yes ⚠️**" if sigs.get("wrong_page_detected") else "No"
            plain = "Yes" if sigs.get("uses_plain_text_sections") else "No"
            plain_matches = sigs.get("plain_section_matches", [])
            plain_str = (", ".join(f'`{m}`' for m in plain_matches[:3])) if plain_matches else "—"
            lines += [
                f"| Wrong Page Detected | {wrong} |",
                f"| Dynamic / SPA | {dyn} |",
                f"| SPA Frameworks Detected | {fw} |",
                f"| HTML Size | {sigs.get('html_size_bytes', 0):,} bytes |",
                f"| Visible Text Ratio | {sigs.get('visible_text_ratio', 0.0):.1%} |",
                f"| Member Keywords in HTML | {'Yes' if sigs.get('has_member_keywords_in_html') else 'No'} |",
                f"| Plain-Text Section Headers | {plain} |",
                f"| Plain-Text Patterns Found | {plain_str} |",
                f"| Card/Grid Pattern | {'Yes' if sigs.get('has_card_or_grid_pattern') else 'No'} |",
            ]

        lines.append("")

        if r.get("navigation_path"):
            path_str = " → ".join(f"`{p}`" for p in r["navigation_path"])
            lines += [f"**Navigation Path:** {path_str}", ""]

        nav_score = r.get("navigation_score") or {}
        if nav_score:
            lines += [
                "**Navigation Score:**",
                "",
                "| Component | Score |",
                "|-----------|-------|",
            ]
            for k, v in nav_score.items():
                if isinstance(v, float):
                    lines.append(f"| {k.replace('_', ' ').title()} | {v:.3f} |")
            lines.append("")

        if r.get("navigation_evidence"):
            ev_str = ", ".join(f"`{e}`" for e in r["navigation_evidence"])
            lines += [f"**Navigation Evidence:** {ev_str}", ""]

        headings = r.get("section_headings", [])
        if headings:
            h_preview = headings[:15]
            h_str = ", ".join(f"`{h}`" for h in h_preview)
            if len(headings) > 15:
                h_str += f" … (+{len(headings) - 15} more)"
            lines += [f"**All Headings Found:** {h_str}", ""]

        unmatched = r.get("unmatched_member_headings", [])
        if unmatched:
            um_str = ", ".join(f"`{h}`" for h in unmatched)
            lines += [
                f"**Unmatched Member Headings (near-miss):** {um_str}",
                "",
            ]

        detected = r.get("detected_member_sections", [])
        if detected:
            d_str = ", ".join(f"`{s}`" for s in detected)
            lines += [f"**Parser-Detected Member Sections:** {d_str}", ""]
        else:
            lines += ["**Parser-Detected Member Sections:** _none_", ""]

        reason = r.get("rejected_reason", "unknown")
        lines += [
            f"**Rejected Reason:** `{reason}`",
            "",
            f"**Suggested Fix:**",
            "",
            f"> {r['suggested_fix']}",
            "",
            "---",
            "",
        ]

    # ── Recommendations ──────────────────────────────────────────────────────
    lines += [
        "## Prioritized Recommendations",
        "",
        "_Ranked by number of professors affected._",
        "",
    ]

    rec_index = 1
    fd = stats["failure_distribution"]
    fdraw = stats["failure_distribution_raw_keys"]

    if fdraw.get("section_detection_failure", 0) > 0:
        count = fdraw["section_detection_failure"]
        unmatched_top = list(stats["unmatched_member_headings"].keys())[:5]
        u_str = (
            ", ".join(f'"{h}"' for h in unmatched_top)
            if unmatched_top
            else "see headings table above"
        )
        lines += [
            f"### R{rec_index}. Expand CURRENT_SECTION_KEYWORDS ({count} professors affected)",
            "",
            f"The most common failure. Pages have member-related headings that don't "
            f"match any keyword. Near-miss headings: {u_str}.",
            "",
            "**File:** `research_group_agent/precision_constants.py`",
            "**Action:** Add normalized versions of unmatched headings to CURRENT_SECTION_KEYWORDS.",
            "",
        ]
        rec_index += 1

    if fdraw.get("unsupported_html_structure", 0) > 0:
        count = fdraw["unsupported_html_structure"]
        lines += [
            f"### R{rec_index}. Add CSS Card/Grid Layout Parser ({count} professors affected)",
            "",
            "Some pages list members in card/grid layouts without h1–h4 section headings. "
            "The parser only supports heading-delimited sections.",
            "",
            "**File:** `research_group_agent/parser.py`",
            "**Action:** Add a secondary parser path for repeated profile-card containers.",
            "",
        ]
        rec_index += 1

    if fdraw.get("dynamic_html", 0) > 0:
        count = fdraw["dynamic_html"]
        lines += [
            f"### R{rec_index}. Add Headless Browser Fetch for SPA Pages ({count} professors affected)",
            "",
            "JavaScript-rendered pages return near-empty HTML to the static fetcher.",
            "",
            "**File:** `research_group_agent/fetcher.py`",
            "**Action:** Add a Playwright/Puppeteer-based fetch option as a fallback.",
            "",
        ]
        rec_index += 1

    if fdraw.get("no_homepage", 0) > 0:
        count = fdraw["no_homepage"]
        lines += [
            f"### R{rec_index}. Improve HomepageGraph Group Page Discovery ({count} professors affected)",
            "",
            "For some professors the HP agent didn't discover any lab/people/group page. "
            "This may be due to Google Sites JS navigation or unusual anchor text.",
            "",
            "**File:** `homepage_agent/navigator.py` + `research_group_agent/precision_constants.py`",
            "**Action:** Broaden GROUP_ANCHOR_POSITIVE keywords and add a Google Sites-aware "
            "crawl strategy.",
            "",
        ]
        rec_index += 1

    if fdraw.get("profile_detection_failure", 0) > 0:
        count = fdraw["profile_detection_failure"]
        lines += [
            f"### R{rec_index}. Relax PersonValidator Precision Filters ({count} professors affected)",
            "",
            "Members are found by parser but rejected by precision filters. "
            "The name regex or negative keyword lists may be too strict.",
            "",
            "**File:** `research_group_agent/person_validator.py` + `precision_constants.py`",
            "**Action:** Review PERSON_NEGATIVE_NAME_PATTERNS for false positives.",
            "",
        ]
        rec_index += 1

    if fdraw.get("fetch_failure", 0) > 0:
        count = fdraw["fetch_failure"]
        lines += [
            f"### R{rec_index}. Investigate Network Fetch Failures ({count} professors affected)",
            "",
            "Some pages couldn't be fetched at all (network error, timeout, or proxy block). "
            "Retry with different network configuration.",
            "",
            "**Action:** Retry affected URLs with increased timeout or direct network access.",
            "",
        ]
        rec_index += 1

    if fdraw.get("landing_page", 0) > 0:
        count = fdraw["landing_page"]
        lines += [
            f"### R{rec_index}. Add Second Navigation Hop for Lab Landing Pages ({count} professors affected)",
            "",
            "Some lab pages are landing pages that link to a /members or /people sub-page. "
            "The current navigator selects the landing page and stops.",
            "",
            "**File:** `research_group_agent/navigator.py`",
            "**Action:** After selecting a group page, check if it has a /members or /people "
            "sub-link and navigate one additional hop.",
            "",
        ]
        rec_index += 1

    lines += [
        "---",
        "",
        "_This report was generated by `tools/pr15_5_failure_inspector.py` (PR15.5)._",
        "_All findings are evidence-based from cached HTML and existing pipeline artifacts._",
        "_Do not modify parser heuristics without evidence from this report._",
        "",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def _load(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    print("[PR15.5 Failure Inspector] Loading artifacts…")

    graphs_raw = _load(GRAPH_FILE) or []
    debug_raw = _load(DEBUG_FILE)
    homepage_raw = _load(HOMEPAGE_FILE) or []

    if not graphs_raw:
        print("ERROR: research_group_graph.json not found or empty.")
        print("       Run tools/research_group_agent_run.py first.")
        return 1

    print(f"  Loaded {len(graphs_raw)} professor graphs")
    print(f"  Navigation debug: {'available' if debug_raw else 'missing'}")
    print(f"  Homepage graphs: {len(homepage_raw)}")

    debug_index = _build_debug_index(debug_raw)
    homepage_index = _build_homepage_index(homepage_raw)

    # Inspect all failed professors
    all_records: list[dict] = []
    for graph in graphs_raw:
        if not _is_failed(graph):
            print(f"  [PASS] {graph['professor_name']} — {graph['member_count']} members")
            continue

        name = graph["professor_name"]
        debug_entry = debug_index.get(name)
        homepage_graph = homepage_index.get(name)

        print(f"  [FAIL] {graph['professor_name']} — {graph.get('fetch_status')}")
        record = inspect_one(graph, debug_entry, homepage_graph)
        all_records.append(record)

    print(f"\n[PR15.5 Failure Inspector] {len(all_records)} failures analyzed")

    # Compute statistics
    stats = compute_statistics(all_records, graphs_raw)

    generated_at = datetime.now(timezone.utc).isoformat()

    # Assemble JSON output (strip internal keys)
    output_records = []
    for r in all_records:
        cleaned = {k: v for k, v in r.items() if not k.startswith("_")}
        output_records.append(cleaned)

    json_payload = {
        "generated_at": generated_at,
        "pipeline_version": "PR15",
        "inspector_version": "PR15.5",
        "total_professors": len(graphs_raw),
        "total_failures": len(all_records),
        "statistics": stats,
        "failures": output_records,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "FAILED_GROUP_PAGES.json"
    md_path = OUTPUT_DIR / "FAILED_GROUP_PAGES.md"

    json_path.write_text(
        json.dumps(json_payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    md_text = render_markdown(all_records, stats, generated_at)
    md_path.write_text(md_text, encoding="utf-8")

    print(f"\n[PR15.5 Failure Inspector] JSON   → {json_path}")
    print(f"[PR15.5 Failure Inspector] Report → {md_path}")

    # Summary
    print("\n── Failure Distribution ──────────────────────────────")
    for label, count in stats["failure_distribution"].items():
        bar = "█" * count
        print(f"  {label:<35} {count}  {bar}")

    print("\n── Top Unmatched Member Headings (fix candidates) ────")
    for heading, count in list(stats["unmatched_member_headings"].items())[:8]:
        print(f'  "{heading}" × {count}')

    print("\n── Post-Navigation Failure Rate ──────────────────────")
    print(f"  {stats['post_navigation_failures']} of "
          f"{sum(1 for g in graphs_raw if g.get('group_page'))} navigated pages "
          f"failed AFTER navigation ({stats['post_navigation_failure_rate']:.0%})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
