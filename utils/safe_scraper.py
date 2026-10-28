"""Bounded, DNS-pinned single-page fetcher for untrusted URLs.

Designed for the local Nimble analyser. Unlike requests.get(..., redirects=True),
DNS is resolved and vetted before connecting, and the connection uses that IP.
Each redirect repeats the entire validation. No system proxies are used.
"""
from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import certifi
from bs4 import BeautifulSoup
from core.schemas import ScrapeResult

USER_AGENT = "NimbleAutoAnalyzer/1.0 (+local SEO research; respectful bounded fetch)"
MAX_BYTES = 1_500_000
MAX_REDIRECTS = 4
TIMEOUT = 12

class FetchError(Exception):
    pass

@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int
    html: str


def _validate_destination(url: str) -> tuple[str, int, str, str]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise FetchError("Only HTTP(S) URLs with hostnames are supported")
    if parsed.username or parsed.password or parsed.fragment:
        raise FetchError("Credentials and fragments are not allowed in target URLs")
    host = parsed.hostname.rstrip(".").lower()
    if (not host or host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".test"))):
        raise FetchError("Local and internal hostnames are blocked")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise FetchError("Invalid port") from exc
    if port != (443 if parsed.scheme == "https" else 80):
        raise FetchError("Nonstandard HTTP(S) ports are blocked")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    return host, port, path, parsed.scheme


def _public_ips(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError("DNS lookup failed") from exc
    candidates: list[str] = []
    for info in infos:
        ip = info[4][0]
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if not address.is_global:
            # Fail closed when ANY DNS answer is private or otherwise non-global.
            raise FetchError("Target resolves to a restricted IP address")
        if ip not in candidates:
            candidates.append(ip)
    if not candidates:
        raise FetchError("No public IP addresses found")
    return candidates


def fetch_url(url: str, *, allow_text: bool = False, check_robots: bool = False) -> FetchResult:
    """Fetch one untrusted URL with redirect, response-size and network bounds."""
    seen: set[str] = set()
    for _ in range(MAX_REDIRECTS + 1):
        if url in seen:
            raise FetchError("Redirect loop")
        seen.add(url)
        host, port, path, scheme = _validate_destination(url)
        if check_robots and not _allowed_by_robots(url):
            raise FetchError("robots.txt disallows this URL")
        ip = _public_ips(host, port)[0]
        host_header = f"[{host}]" if ":" in host else host
        if scheme == "https":
            conn = http.client.HTTPSConnection(host, port, timeout=TIMEOUT, context=ssl.create_default_context(cafile=certifi.where()))
        else:
            conn = http.client.HTTPConnection(host, port, timeout=TIMEOUT)
        # Preserve hostname for TLS SNI and certificate verification while pinning
        # the actual TCP destination to the vetted address (DNS rebinding defence).
        conn._create_connection = lambda _address, timeout=TIMEOUT, source_address=None, _ip=ip, _port=port: socket.create_connection((_ip, _port), timeout=timeout, source_address=source_address)
        try:
            conn.request("GET", path, headers={
                "Host": host_header,
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Encoding": "identity",
                "Connection": "close",
            })
            response = conn.getresponse()
            status = response.status
            if status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise FetchError("Redirect response omitted its destination")
                url = urljoin(url, location)
                continue
            content_type = (response.getheader("Content-Type") or "").lower()
            if status == 200 and not any(t in content_type for t in (("text/html", "application/xhtml+xml", "text/plain") if allow_text else ("text/html", "application/xhtml+xml"))):
                raise FetchError("Target did not return an HTML document")
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise FetchError("Page exceeds 1.5 MB download limit")
            charset_match = re.search(r"charset\s*=\s*['\"]?([\w-]+)", content_type)
            charset = charset_match.group(1) if charset_match else "utf-8"
            try:
                decoded = raw.decode(charset, errors="replace")
            except LookupError:
                decoded = raw.decode("utf-8", errors="replace")
            return FetchResult(url=url, status=status, html=decoded)
        except ssl.SSLCertVerificationError as exc:
            raise FetchError("HTTPS certificate verification failed") from exc
        except (OSError, http.client.HTTPException, TimeoutError, ssl.SSLError) as exc:
            raise FetchError(f"Network request failed: {type(exc).__name__}") from exc
        finally:
            conn.close()
    raise FetchError("Too many redirects")


def _allowed_by_robots(url: str) -> bool:
    parsed = urlsplit(url)
    robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    try:
        result = fetch_url(robots_url, allow_text=True)
    except FetchError as exc:
        # Retain the bounded diagnostic while failing closed on an unknown policy.
        raise FetchError(f"Unable to verify robots.txt ({exc}); crawl skipped") from exc
    if result.status == 404:
        return True
    if result.status in (401, 403):
        return False
    if result.status != 200:
        raise FetchError(f"robots.txt returned HTTP {result.status}")
    parser = RobotFileParser()
    parser.parse(result.html.splitlines())
    return parser.can_fetch(USER_AGENT, url)


def parse_html(url: str, html: str, status: int = 200) -> ScrapeResult:
    """Pure HTML-to-data function, suitable for offline fixtures and tests."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    meta = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    description = str(meta.get("content", "")).strip() or None if meta else None
    base = urlsplit(url)
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        link = urljoin(url, str(anchor["href"]))
        lp = urlsplit(link)
        if lp.scheme in {"http", "https"} and lp.hostname == base.hostname and link not in links:
            links.append(link)
        if len(links) >= 50:
            break
    for element in soup.find_all(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe", "form"]):
        element.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    headings = {name: [h.get_text(" ", strip=True) for h in root.find_all(name) if h.get_text(" ", strip=True)] for name in ("h1", "h2", "h3")}
    text = re.sub(r"\s+", " ", root.get_text(" ", strip=True)).strip()
    words = len(text.split())
    if words < 50:
        return ScrapeResult(url=url, success=False, status_code=status, error_message=f"Insufficient extractable content ({words} words)")
    return ScrapeResult(url=url, success=True, status_code=status, title=title, meta_description=description, headings=headings, body_text=text, word_count=words, internal_links=links, scraper_used="safe-http")


def scrape_url_safe(url: str) -> ScrapeResult:
    try:
        _validate_destination(url)
        result = fetch_url(url, check_robots=True)
        if result.status != 200:
            raise FetchError(f"Website returned HTTP {result.status}")
        return parse_html(result.url, result.html, result.status)
    except FetchError as exc:
        return ScrapeResult(url=url, success=False, error_message=str(exc), scraper_used="safe-http")
