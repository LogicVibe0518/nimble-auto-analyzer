"""BeautifulSoup4 web scraper for Nimble Auto-Analyzer.

Fetches public HTML pages and extracts SEO-relevant content into a
``ScrapeResult``. All failures are represented in-band on the result model.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from core.schemas import ScrapeResult

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15
MIN_USEFUL_WORD_COUNT = 50
TAGS_TO_STRIP = [
    "script",
    "style",
    "nav",
    "footer",
    "header",
    "aside",
    "form",
    "noscript",
    "iframe",
]
MAX_INTERNAL_LINKS = 50
_CONTENT_DIV_KEYWORDS = (
    "content",
    "main",
    "primary",
    "page",
    "post",
    "article",
    "body-content",
    "wrapper",
    "container",
    "site-content",
    "page-content",
)
_SPAM_ATTR_PATTERNS = (
    "comments",
    "comment-list",
    "comment-respond",
    "wp-comments",
    "site-footer",
    "page-footer",
    "cookie-banner",
    "cookie-notice",
    "newsletter-popup",
    "modal-overlay",
    "share-buttons",
    "social-share",
    "advertisement",
    "ad-banner",
    "ad-container",
)
_COMMENT_SPAM_TEXT_KEYWORDS = (
    "casino",
    "betting",
    "bet365",
    "jackpot",
    "spribe",
    "aviator",
)
_MAX_COMMENT_SPAM_TEXT_LEN = 200
_HIDDEN_STYLE_MARKERS = (
    "display:none",
    "display: none",
    "visibility:hidden",
    "visibility: hidden",
)

_REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _status_error_message(status_code: int) -> str:
    if status_code == 403:
        return (
            "Site blocked our request (403 Forbidden). "
            "It may have anti-bot protection."
        )
    if status_code == 404:
        return "Page not found (404). Please check the URL."
    if status_code >= 500:
        return (
            f"Site returned a server error ({status_code}). "
            "It may be temporarily unavailable."
        )
    return f"Site returned unexpected status code: {status_code}"


def _extract_meta_description(soup: BeautifulSoup) -> str | None:
    for attrs in ({"name": "description"}, {"property": "og:description"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            content = str(tag["content"]).strip()
            if content:
                return content
    return None


def _extract_internal_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    page_netloc = urlparse(page_url).netloc
    seen: set[str] = set()
    links: list[str] = []

    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if not href:
            continue

        parsed = urlparse(href)
        is_internal = href.startswith("/") or (
            bool(parsed.netloc) and parsed.netloc == page_netloc
        )
        if not is_internal or href in seen:
            continue

        seen.add(href)
        links.append(href)
        if len(links) >= MAX_INTERNAL_LINKS:
            break

    return links


def _safe_decompose(element: BeautifulSoup) -> None:
    try:
        element.decompose()
    except AttributeError:
        pass


def _has_hidden_inline_style(style: str) -> bool:
    style_lower = style.lower()
    return any(marker in style_lower for marker in _HIDDEN_STYLE_MARKERS)


def _class_matches_spam_pattern(value: str | list[str] | None) -> bool:
    if not value:
        return False
    if isinstance(value, list):
        class_tokens = [token.lower() for token in value]
    else:
        class_tokens = [token.lower() for token in str(value).split()]
    pattern_set = {pattern.lower() for pattern in _SPAM_ATTR_PATTERNS}
    return any(token in pattern_set for token in class_tokens)


def _id_matches_spam_pattern(element_id: str) -> bool:
    normalized_id = element_id.lower()
    pattern_set = {pattern.lower() for pattern in _SPAM_ATTR_PATTERNS}
    if normalized_id in pattern_set:
        return True
    id_tokens = re.split(r"[-_]+", normalized_id)
    return any(token in pattern_set for token in id_tokens)


def _is_comment_spam_paragraph(element: BeautifulSoup) -> bool:
    if element.name not in ("p", "li"):
        return False
    if not element.find("a"):
        return False
    text = element.get_text(strip=True)
    if len(text) >= _MAX_COMMENT_SPAM_TEXT_LEN:
        return False
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in _COMMENT_SPAM_TEXT_KEYWORDS)


def _element_attrs(element: BeautifulSoup) -> dict[str, str] | None:
    attrs = getattr(element, "attrs", None)
    return attrs if isinstance(attrs, dict) else None


def _remove_hidden_and_spam_elements(soup: BeautifulSoup, url: str) -> int:
    removed_count = 0

    def remove(element: BeautifulSoup) -> None:
        nonlocal removed_count
        _safe_decompose(element)
        removed_count += 1

    # Inline CSS hiding (display:none, visibility:hidden, etc.)
    for element in list(soup.find_all(style=True)):
        attrs = _element_attrs(element)
        if not attrs:
            continue
        style = attrs.get("style")
        if isinstance(style, str) and _has_hidden_inline_style(style):
            remove(element)

    # Boilerplate / ads / modals identified by exact class tokens
    for element in list(soup.find_all(True)):
        attrs = _element_attrs(element)
        if not attrs:
            continue
        if _class_matches_spam_pattern(attrs.get("class")):
            remove(element)

    # Same patterns on element id (exact match or complete hyphen/underscore token)
    for element in list(soup.find_all(True)):
        attrs = _element_attrs(element)
        if not attrs:
            continue
        element_id = attrs.get("id")
        if element_id and _id_matches_spam_pattern(str(element_id)):
            remove(element)

    # Short linked paragraphs promoting casino/betting spam (WordPress comment spam)
    for element in list(soup.find_all(["p", "li"])):
        if _is_comment_spam_paragraph(element):
            remove(element)

    print(f"Stripped {removed_count} elements from {url}")
    return removed_count


def _find_main_container(soup: BeautifulSoup) -> BeautifulSoup:
    # Semantic HTML5 main landmark
    if main := soup.find("main"):
        return main

    if article := soup.find("article"):
        return article

    # Div-based layouts: pick the richest matching container (not the first in DOM)
    div_candidates: list[BeautifulSoup] = []
    for div in soup.find_all("div"):
        div_id = div.get("id")
        if div_id and any(
            keyword in str(div_id).lower() for keyword in _CONTENT_DIV_KEYWORDS
        ):
            div_candidates.append(div)
            continue

        class_value = div.get("class")
        if not class_value:
            continue
        if isinstance(class_value, list):
            class_matches = any(
                any(keyword in css_class.lower() for keyword in _CONTENT_DIV_KEYWORDS)
                for css_class in class_value
            )
        else:
            class_matches = any(
                keyword in str(class_value).lower() for keyword in _CONTENT_DIV_KEYWORDS
            )
        if class_matches:
            div_candidates.append(div)

    if div_candidates:
        return max(div_candidates, key=lambda div: len(div.get_text(strip=True)))

    if body := soup.find("body"):
        if body.get_text(strip=True):
            return body

    return soup


def _extract_headings(main_container: BeautifulSoup) -> dict[str, list[str]]:
    headings: dict[str, list[str]] = {}
    for tag in ("h1", "h2", "h3"):
        texts = [
            text
            for element in main_container.find_all(tag)
            if (text := element.get_text(strip=True)) and len(text) >= 3
        ]
        headings[tag] = texts
    return headings


def scrape_url(url: str) -> ScrapeResult:
    """Fetch and parse a single URL into structured scrape data.

    Args:
        url: HTTP(S) URL to scrape (already validated upstream).

    Returns:
        A ``ScrapeResult`` describing success or failure. This function
        never raises; network, HTTP, and parse issues are returned in-band.
    """
    try:
        response = requests.get(
            url,
            headers=_REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
    except requests.exceptions.Timeout:
        return ScrapeResult(
            url=url,
            success=False,
            error_message="Site took too long to respond (timeout after 15s)",
        )
    except requests.exceptions.ConnectionError:
        return ScrapeResult(
            url=url,
            success=False,
            error_message=(
                "Could not connect to the site (it may be down, "
                "or the URL may be incorrect)"
            ),
        )
    except requests.exceptions.TooManyRedirects:
        return ScrapeResult(
            url=url,
            success=False,
            error_message="Site has redirect loop or too many redirects",
        )
    except requests.exceptions.RequestException as exc:
        return ScrapeResult(
            url=url,
            success=False,
            error_message=(
                f"Network error while fetching the site: {type(exc).__name__}"
            ),
        )

    status_code = response.status_code
    if status_code != 200:
        return ScrapeResult(
            url=url,
            success=False,
            status_code=status_code,
            error_message=_status_error_message(status_code),
        )

    soup = BeautifulSoup(response.text, "lxml")

    title = soup.title.get_text(strip=True) if soup.title else None
    meta_description = _extract_meta_description(soup)
    internal_links = _extract_internal_links(soup, url)

    for tag_name in TAGS_TO_STRIP:
        for element in soup.find_all(tag_name):
            _safe_decompose(element)

    _remove_hidden_and_spam_elements(soup, url)

    main_container = _find_main_container(soup)
    headings = _extract_headings(main_container)

    raw_text = main_container.get_text(separator=" ", strip=True)
    body_text = re.sub(r"\s+", " ", raw_text).strip()
    word_count = len(body_text.split()) if body_text else 0

    if word_count < MIN_USEFUL_WORD_COUNT:
        return ScrapeResult(
            url=url,
            success=False,
            status_code=200,
            error_message=(
                f"Site loaded but had very little extractable content "
                f"(only {word_count} words). It may need JavaScript rendering "
                "or has aggressive content protection."
            ),
        )

    return ScrapeResult(
        url=url,
        success=True,
        status_code=200,
        title=title,
        meta_description=meta_description,
        headings=headings,
        body_text=body_text,
        word_count=word_count,
        internal_links=internal_links,
        scraper_used="bs4",
    )
