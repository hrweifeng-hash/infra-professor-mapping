"""Prompt construction for homepage navigation providers."""

from __future__ import annotations

from homepage_agent.models import HomepageDocument, Hyperlink, NodeCategory, ParsedPage

LINK_PREVIEW_LIMIT = 40
TEXT_PREVIEW_LIMIT = 1200


def build_navigation_prompt(
    professor_name: str,
    document: HomepageDocument,
    parsed: ParsedPage,
    links: list[Hyperlink] | None = None,
) -> str:
    """
    Build the prompt sent to a NavigatorProvider.

    Separated from provider logic so prompts can be reviewed, versioned, and
    reused across heuristic / LLM backends.
    """
    link_list = links if links is not None else parsed.links
    preview_links = link_list[:LINK_PREVIEW_LIMIT]

    link_lines = []
    for index, link in enumerate(preview_links, start=1):
        context = f" | context: {link.surrounding_context}" if link.surrounding_context else ""
        anchor = link.anchor_text or "(no anchor text)"
        link_lines.append(
            f"{index}. [{anchor}]({link.absolute_url}){context}"
        )

    visible_excerpt = parsed.visible_text[:TEXT_PREVIEW_LIMIT]
    if len(parsed.visible_text) > TEXT_PREVIEW_LIMIT:
        visible_excerpt += "..."

    categories = ", ".join(
        category.value
        for category in NodeCategory
        if category != NodeCategory.HOMEPAGE
    )

    return (
        "You are analyzing a professor homepage to build a navigation graph.\n"
        "Only use links present on this single page — do not infer URLs.\n\n"
        f"Professor: {professor_name}\n"
        f"Homepage URL: {document.final_url or document.url}\n"
        f"Page title: {parsed.page_title or document.title or '(unknown)'}\n\n"
        "Visible text excerpt:\n"
        f"{visible_excerpt or '(empty)'}\n\n"
        f"Hyperlinks ({len(link_list)} total, showing up to {LINK_PREVIEW_LIMIT}):\n"
        f"{chr(10).join(link_lines) if link_lines else '- (none)'}\n\n"
        "For each navigation slot, pick the best matching link or leave empty:\n"
        f"{categories}\n\n"
        "Also mark links that should be ignored (social media, PDFs, external aggregators).\n"
        "Return structured selections with confidence scores.\n"
    )
