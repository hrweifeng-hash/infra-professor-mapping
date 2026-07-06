"""HTML parser — extracts title, visible text, and hyperlinks without classification."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from homepage_agent.models import Hyperlink, ParsedPage


_STRIP_TAGS = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


class _LinkExtractingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[Hyperlink] = []

        self._in_title = False
        self._in_script = False
        self._in_style = False
        self._in_noscript = False
        self._skip_depth = 0

        self._current_anchor: list[str] = []
        self._current_href: str | None = None
        self._context_buffer: list[str] = []
        self._base_url: str = ""

    def set_base_url(self, base_url: str) -> None:
        self._base_url = base_url

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: (value or "") for key, value in attrs}

        if tag == "base" and attr_map.get("href"):
            self._base_url = urljoin(self._base_url or "", attr_map["href"])

        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            if tag == "script":
                self._in_script = True
            elif tag == "style":
                self._in_style = True
            elif tag == "noscript":
                self._in_noscript = True
            return

        if self._skip_depth:
            return

        if tag == "title":
            self._in_title = True
            return

        if tag == "a" and attr_map.get("href"):
            self._current_href = attr_map["href"]
            self._current_anchor = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            if tag == "script":
                self._in_script = False
            elif tag == "style":
                self._in_style = False
            elif tag == "noscript":
                self._in_noscript = False
            return

        if self._skip_depth:
            return

        if tag == "title":
            self._in_title = False
            return

        if tag == "a" and self._current_href:
            anchor = _WHITESPACE.sub(" ", "".join(self._current_anchor)).strip()
            absolute = self._resolve_href(self._current_href)
            if absolute and self._is_navigable(absolute):
                context = self._recent_context()
                self.links.append(
                    Hyperlink(
                        anchor_text=anchor,
                        href=self._current_href,
                        absolute_url=absolute,
                        surrounding_context=context or None,
                    )
                )
            self._current_href = None
            self._current_anchor = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if not data.strip():
            return

        if self._in_title:
            self.title_parts.append(data)
            return

        if self._current_href is not None:
            self._current_anchor.append(data)

        self.text_parts.append(data)
        self._context_buffer.append(data.strip())
        if len(self._context_buffer) > 12:
            self._context_buffer.pop(0)

    def _recent_context(self) -> str:
        return _WHITESPACE.sub(" ", " ".join(self._context_buffer[-6:])).strip()

    def _resolve_href(self, href: str) -> str | None:
        href = href.strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            return None
        return urljoin(self._base_url, href)

    @staticmethod
    def _is_navigable(url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class HomepageParser:
    """Convert raw HTML into structured page data — no business logic."""

    def parse(self, html: str, base_url: str) -> ParsedPage:
        parser = _LinkExtractingParser()
        parser.set_base_url(base_url)
        parser.feed(html)
        parser.close()

        title = _WHITESPACE.sub(" ", "".join(parser.title_parts)).strip()
        visible_text = _WHITESPACE.sub(" ", " ".join(parser.text_parts)).strip()

        deduped_links: list[Hyperlink] = []
        seen: set[str] = set()
        for link in parser.links:
            key = (link.absolute_url, link.anchor_text.lower())
            if key in seen:
                continue
            seen.add(key)
            deduped_links.append(link)

        return ParsedPage(
            page_title=title,
            visible_text=visible_text,
            links=deduped_links,
        )
