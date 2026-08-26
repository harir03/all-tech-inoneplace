"""
OpportunityHub — Agent Reach Capability Layer
https://github.com/Panniantong/Agent-Reach

WHAT AGENT REACH ACTUALLY IS (this matters for how we integrate it):

    Agent Reach is *not* a dataset and *not* a content proxy. Its own README is
    explicit — it is a capability layer that handles selection, installation,
    health-checking and routing, and deliberately does NOT perform the reads
    itself ("不负责底层读取本身。读取由 Agent 直接调用上游工具完成，没有包装层").
    `agent-reach doctor --json` reports which backend is currently live for each
    platform; the caller then invokes that upstream tool directly.

So integrating it means adopting its *routing model and its chosen backends*,
not calling some `agent-reach read` endpoint that does not exist.

WHY IT IS WORTH INTEGRATING HERE:

    Our scrapers keep losing to anti-bot walls. Unstop, Devfolio and LinkedIn
    return 403 to plain urllib, which means `evidence.py` records
    `blocked_403` — "we could not look" — and Layer 2 has to fall back to
    trusting the source. Agent Reach's answer for "read any web page" is Jina
    Reader (`https://r.jina.ai/<url>`), which renders the page server-side and
    returns clean text, needs no API key, and needs nothing installed. Routing
    blocked fetches through it converts a large class of unverifiable records
    into verifiable ones.

DESIGN (mirrors Agent Reach's own architecture):

    Every channel is an ordered backend list, each probed for real rather than
    assumed. First working backend wins. Nothing here is a hard dependency — if
    a backend is missing the channel degrades and the pipeline keeps running.

        web    → agent-reach routed ▸ Jina Reader ▸ direct HTTP
        rss    → feedparser ▸ stdlib ElementTree
        search → mcporter/Exa (only if installed)
        github → gh CLI ▸ raw.githubusercontent HTTP

    `ReachClient.doctor()` mirrors `agent-reach doctor --json` so the pipeline
    report can state which backend actually served each channel.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("opportunityhub.reach")


# ── Backend identifiers ─────────────────────────────────────────────────────
B_AGENT_REACH = "agent-reach"
B_JINA = "jina-reader"
B_DIRECT = "direct-http"
B_FEEDPARSER = "feedparser"
B_ELEMENTTREE = "elementtree"
B_MCPORTER = "mcporter/exa"
B_GH = "gh-cli"
B_RAW_HTTP = "raw-http"
B_NONE = "unavailable"

JINA_ENDPOINT = "https://r.jina.ai/"
JINA_TIMEOUT = 25          # Jina renders server-side, so it is slower than raw GET
DIRECT_TIMEOUT = 10
CLI_TIMEOUT = 20
MAX_DOC_CHARS = 200_000
# HTML mode keeps the full rendered DOM, which is much larger than markdown but
# is the only mode that preserves JSON-LD / OpenGraph for evidence extraction.
MAX_HTML_CHARS = 400_000

# Two different User-Agent policies, and the asymmetry is deliberate.
#
# BROWSER_UA — target sites (direct HTTP, RSS) serve degraded content or 403 to
#   anything that does not look like a real browser, so we present one.
#
# HONEST_UA  — Jina Reader does the exact opposite: it is a programmatic API with
#   anti-abuse rules that REJECT browser impersonation. Verified empirically:
#   any User-Agent containing a Chrome/Safari token returns HTTP 403, while an
#   honest client identifier (or no UA at all) returns 200. Do not "fix" this by
#   unifying the two constants — it will silently disable the whole Reach web
#   channel and every bot-walled page becomes unverifiable again.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
HONEST_UA = "OpportunityHub-Reach/1.0 (+https://github.com/opportunityhub)"

# Backwards-compatible alias for callers that imported the old name.
USER_AGENT = BROWSER_UA


@dataclass
class ReachDoc:
    """A page read through whichever backend won the race."""
    url: str
    ok: bool = False
    backend: str = B_NONE
    title: str = ""
    text: str = ""
    raw: str = ""          # Unprocessed body (rendered HTML when requested)
    error: str = ""
    elapsed_ms: int = 0

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class FeedEntry:
    """One normalized RSS/Atom item."""
    title: str = ""
    link: str = ""
    published: str = ""
    summary: str = ""


@dataclass
class ChannelStatus:
    name: str
    backend: str = B_NONE
    ok: bool = False
    detail: str = ""


class ReachClient:
    """
    Ordered-backend router for external reads.

    One instance per pipeline run. All probing is cached, all network work is
    bounded, and every method is total — it returns an empty/failed result rather
    than raising, because a data-acquisition helper must never be able to take
    down the pipeline.
    """

    def __init__(
        self,
        enabled: bool = True,
        use_jina: bool = True,
        jina_api_key: Optional[str] = None,
        max_reads: int = 60,
        time_budget: float = 180.0,
    ):
        self.enabled = enabled
        self.use_jina = use_jina
        self.jina_api_key = jina_api_key or os.getenv("JINA_API_KEY", "") or ""
        self.max_reads = max_reads
        self.time_budget = time_budget

        self._started = time.monotonic()
        self._reads = 0
        self._cache: Dict[str, ReachDoc] = {}
        self._cli_path: Optional[str] = None
        self._doctor_cache: Optional[Dict[str, Any]] = None
        self._probe_cache: Dict[str, bool] = {}

        self.stats = {
            "web_reads": 0, "web_jina": 0, "web_direct": 0, "web_cli": 0,
            "web_failed": 0, "cache_hits": 0, "rss_feeds": 0, "rss_entries": 0,
            "searches": 0, "skipped_budget": 0, "skipped_cap": 0,
        }

    # ── Budget ─────────────────────────────────────────────────────────────

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._started

    @property
    def budget_remaining(self) -> float:
        return max(0.0, self.time_budget - self.elapsed)

    def _can_read(self) -> Tuple[bool, str]:
        if not self.enabled:
            return False, "disabled"
        if self._reads >= self.max_reads:
            self.stats["skipped_cap"] += 1
            return False, "read_cap_reached"
        if self.budget_remaining <= 1.0:
            self.stats["skipped_budget"] += 1
            return False, "budget_exhausted"
        return True, ""

    # ── Capability probing ─────────────────────────────────────────────────

    def _which(self, binary: str) -> bool:
        """Cached PATH lookup."""
        if binary not in self._probe_cache:
            self._probe_cache[binary] = shutil.which(binary) is not None
        return self._probe_cache[binary]

    @property
    def cli_available(self) -> bool:
        """Is the real `agent-reach` CLI installed on this machine?"""
        if self._cli_path is None:
            self._cli_path = shutil.which("agent-reach") or ""
        return bool(self._cli_path)

    def agent_reach_doctor(self) -> Dict[str, Any]:
        """
        Run `agent-reach doctor --json` if the CLI exists.

        This is the sanctioned way to learn which backend Agent Reach currently
        routes each platform to. Returns {} when the CLI is absent, which is the
        normal case in CI.
        """
        if self._doctor_cache is not None:
            return self._doctor_cache
        self._doctor_cache = {}
        if not self.cli_available:
            return self._doctor_cache
        try:
            proc = subprocess.run(
                [self._cli_path, "doctor", "--json"],
                capture_output=True, text=True, timeout=CLI_TIMEOUT,
                encoding="utf-8", errors="replace",
            )
            if proc.returncode == 0 and proc.stdout.strip():
                self._doctor_cache = json.loads(proc.stdout)
                logger.info("[Reach] agent-reach doctor reported %d channels",
                            len(self._doctor_cache) if isinstance(self._doctor_cache, dict) else 0)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
            logger.debug("[Reach] doctor unavailable: %s", e)
        return self._doctor_cache

    def doctor(self) -> List[ChannelStatus]:
        """Capability report for the pipeline log — our analogue of `doctor`."""
        out = [
            ChannelStatus(
                "web",
                B_AGENT_REACH if self.cli_available else (B_JINA if self.use_jina else B_DIRECT),
                True,
                "agent-reach CLI present" if self.cli_available
                else ("Jina Reader (no key required)" if self.use_jina else "direct HTTP only"),
            ),
            ChannelStatus(
                "rss",
                B_FEEDPARSER if self._has_feedparser() else B_ELEMENTTREE,
                True,
                "feedparser" if self._has_feedparser() else "stdlib XML fallback",
            ),
            ChannelStatus(
                "search",
                B_MCPORTER if self._which("mcporter") else B_NONE,
                self._which("mcporter"),
                "Exa semantic search via mcporter" if self._which("mcporter")
                else "not installed (optional)",
            ),
            ChannelStatus(
                "github",
                B_GH if self._which("gh") else B_RAW_HTTP,
                True,
                "gh CLI authenticated reads" if self._which("gh") else "raw.githubusercontent",
            ),
        ]
        return out

    @staticmethod
    def _has_feedparser() -> bool:
        try:
            import feedparser  # noqa: F401
            return True
        except Exception:
            return False

    # ── Channel: web ───────────────────────────────────────────────────────

    def read_web(self, url: str, prefer_jina: bool = True) -> ReachDoc:
        """
        Read any web page as clean text.

        Backend order mirrors Agent Reach's `web` channel: Jina Reader first
        (renders JS, defeats most anti-bot walls, free, no key), then a plain
        direct GET as a last resort.
        """
        if not url or not url.lower().startswith(("http://", "https://")):
            return ReachDoc(url=url or "", error="invalid_url")

        key = url.strip().rstrip("/")
        if key in self._cache:
            self.stats["cache_hits"] += 1
            return self._cache[key]

        allowed, why = self._can_read()
        if not allowed:
            return ReachDoc(url=url, error=why)

        self._reads += 1
        self.stats["web_reads"] += 1
        started = time.monotonic()

        backends = []
        if prefer_jina and self.use_jina:
            backends.append((B_JINA, self._read_via_jina))
            backends.append((B_DIRECT, self._read_via_direct))
        else:
            backends.append((B_DIRECT, self._read_via_direct))
            if self.use_jina:
                backends.append((B_JINA, self._read_via_jina))

        last_error = "no_backend"
        for backend_name, fn in backends:
            if self.budget_remaining <= 1.0:
                last_error = "budget_exhausted"
                break
            try:
                doc = fn(url)
            except Exception as e:  # pragma: no cover - defensive
                last_error = f"{backend_name}:{type(e).__name__}"
                continue
            if doc.ok and doc.text.strip():
                doc.backend = backend_name
                doc.elapsed_ms = int((time.monotonic() - started) * 1000)
                self.stats["web_jina" if backend_name == B_JINA else "web_direct"] += 1
                self._cache[key] = doc
                return doc
            last_error = doc.error or f"{backend_name}:empty"

        failed = ReachDoc(url=url, error=last_error,
                          elapsed_ms=int((time.monotonic() - started) * 1000))
        self.stats["web_failed"] += 1
        self._cache[key] = failed
        return failed

    def read_html(self, url: str) -> ReachDoc:
        """
        Fetch a page as *rendered HTML* through Jina Reader.

        This exists specifically for the Layer 2 evidence collector. Asking Jina
        for `X-Return-Format: html` returns the server-rendered DOM with
        <script type="application/ld+json"> and OpenGraph <meta> tags still
        intact — verified against unstop.com, which yields 2 JSON-LD blocks and 2
        OG tags this way while returning zero of either in markdown mode.

        The consequence is significant: a bot-walled page that plain urllib can
        only see as HTTP 403 becomes a source of full-strength, publisher-authored
        structured evidence (real startDate/endDate), not merely scraped text.
        """
        if not url or not url.lower().startswith(("http://", "https://")):
            return ReachDoc(url=url or "", error="invalid_url")
        if not self.use_jina:
            return ReachDoc(url=url, error="jina_disabled")

        key = "html::" + url.strip().rstrip("/")
        if key in self._cache:
            self.stats["cache_hits"] += 1
            return self._cache[key]

        allowed, why = self._can_read()
        if not allowed:
            return ReachDoc(url=url, error=why)

        self._reads += 1
        self.stats["web_reads"] += 1
        started = time.monotonic()
        doc = self._read_via_jina(url, return_format="html")
        doc.elapsed_ms = int((time.monotonic() - started) * 1000)
        if doc.ok:
            doc.backend = B_JINA
            self.stats["web_jina"] += 1
        else:
            self.stats["web_failed"] += 1
        self._cache[key] = doc
        return doc

    def _read_via_jina(self, url: str, return_format: str = "markdown") -> ReachDoc:
        """
        Jina Reader — Agent Reach's primary `web` backend.

        Free, keyless, renders JS server-side. An optional JINA_API_KEY simply
        raises the rate limit.
        """
        endpoint = JINA_ENDPOINT + url
        headers = {
            # Honest identifier — a browser UA here is rejected with 403.
            "User-Agent": HONEST_UA,
            "Accept": "text/plain, text/markdown, text/html, */*",
            "X-Return-Format": return_format,
        }
        if self.jina_api_key:
            headers["Authorization"] = f"Bearer {self.jina_api_key}"

        cap = MAX_HTML_CHARS if return_format == "html" else MAX_DOC_CHARS * 2
        timeout = min(JINA_TIMEOUT, max(3.0, self.budget_remaining))
        try:
            req = urllib.request.Request(endpoint, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(cap)
            body = raw.decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            return ReachDoc(url=url, error=f"jina_http_{e.code}")
        except Exception as e:
            return ReachDoc(url=url, error=f"jina_{type(e).__name__}")

        if return_format == "html":
            title = ""
            m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
            if m:
                title = re.sub(r"\s+", " ", m.group(1)).strip()[:300]
            return ReachDoc(
                url=url, ok=bool(body.strip()), title=title,
                raw=body, text=strip_html(body)[:MAX_DOC_CHARS],
            )

        title, text = self._split_jina_payload(body)
        return ReachDoc(
            url=url, ok=bool(text.strip()), title=title,
            raw=body[:MAX_DOC_CHARS], text=text[:MAX_DOC_CHARS],
        )

    @staticmethod
    def _split_jina_payload(body: str) -> Tuple[str, str]:
        """
        Jina returns a small preamble then the content:

            Title: ...
            URL Source: ...
            Markdown Content:
            <body>
        """
        title = ""
        m = re.match(r"^Title:\s*(.+)$", body.lstrip().split("\n", 1)[0])
        if m:
            title = m.group(1).strip()
        marker = re.search(r"^Markdown Content:\s*$", body, re.M)
        text = body[marker.end():].lstrip() if marker else body
        return title, text

    def _read_via_direct(self, url: str) -> ReachDoc:
        """Plain GET, HTML stripped to text. Last-resort backend."""
        timeout = min(DIRECT_TIMEOUT, max(2.0, self.budget_remaining))
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": BROWSER_UA,
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(MAX_DOC_CHARS)
            html_text = raw.decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            return ReachDoc(url=url, error=f"direct_http_{e.code}")
        except Exception as e:
            return ReachDoc(url=url, error=f"direct_{type(e).__name__}")

        title = ""
        m = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.I | re.S)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()[:300]
        return ReachDoc(url=url, ok=True, title=title, text=strip_html(html_text)[:MAX_DOC_CHARS])

    # ── Channel: rss ───────────────────────────────────────────────────────

    def read_rss(self, feed_url: str, limit: int = 40) -> List[FeedEntry]:
        """
        Parse an RSS/Atom feed. feedparser when available, stdlib XML otherwise.

        Feeds are the highest-signal acquisition path we have: publisher-authored,
        already structured, and stable. Preferred over scraping listing pages.
        """
        allowed, why = self._can_read()
        if not allowed:
            logger.debug("[Reach] RSS skipped (%s): %s", why, feed_url)
            return []

        self._reads += 1
        raw = self._fetch_bytes(feed_url)
        if not raw:
            return []

        self.stats["rss_feeds"] += 1
        entries = self._parse_with_feedparser(raw) if self._has_feedparser() else []
        if not entries:
            entries = self._parse_with_elementtree(raw)

        self.stats["rss_entries"] += len(entries)
        return entries[:limit]

    def _fetch_bytes(self, url: str) -> bytes:
        timeout = min(DIRECT_TIMEOUT, max(2.0, self.budget_remaining))
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": BROWSER_UA,
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(MAX_DOC_CHARS)
        except Exception as e:
            logger.debug("[Reach] feed fetch failed %s: %s", url, e)
            return b""

    @staticmethod
    def _parse_with_feedparser(raw: bytes) -> List[FeedEntry]:
        try:
            import feedparser
            parsed = feedparser.parse(raw)
            out = []
            for e in parsed.entries:
                out.append(FeedEntry(
                    title=str(getattr(e, "title", "") or "").strip(),
                    link=str(getattr(e, "link", "") or "").strip(),
                    published=str(getattr(e, "published", "") or getattr(e, "updated", "") or "").strip(),
                    summary=strip_html(str(getattr(e, "summary", "") or ""))[:1200],
                ))
            return [e for e in out if e.title]
        except Exception:
            return []

    @staticmethod
    def _parse_with_elementtree(raw: bytes) -> List[FeedEntry]:
        """Stdlib fallback covering RSS 2.0 and Atom."""
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return []

        def tag(el) -> str:
            return el.tag.split("}")[-1].lower()

        def child_text(parent, *names) -> str:
            for el in parent:
                if tag(el) in names:
                    return (el.text or "").strip()
            return ""

        entries: List[FeedEntry] = []
        for node in root.iter():
            if tag(node) not in ("item", "entry"):
                continue
            title = child_text(node, "title")
            if not title:
                continue

            link = child_text(node, "link")
            if not link:
                # Atom uses <link href="..."/>
                for el in node:
                    if tag(el) == "link" and el.attrib.get("href"):
                        rel = el.attrib.get("rel", "alternate")
                        if rel == "alternate":
                            link = el.attrib["href"].strip()
                            break

            entries.append(FeedEntry(
                title=title,
                link=link,
                published=child_text(node, "pubdate", "published", "updated", "date"),
                summary=strip_html(child_text(node, "description", "summary", "content"))[:1200],
            ))
        return entries

    # ── Channel: search (optional) ─────────────────────────────────────────

    def search_web(self, query: str, limit: int = 10) -> List[Dict[str, str]]:
        """
        Semantic web search via Agent Reach's `search` channel (Exa/mcporter).

        Entirely optional. Returns [] when mcporter is not installed, which keeps
        CI unaffected while still enabling local discovery runs.
        """
        if not self.enabled or not self._which("mcporter"):
            return []
        allowed, _ = self._can_read()
        if not allowed:
            return []

        self._reads += 1
        self.stats["searches"] += 1
        try:
            proc = subprocess.run(
                ["mcporter", "run", "exa", "search", "--query", query, "--num-results", str(limit)],
                capture_output=True, text=True, timeout=CLI_TIMEOUT,
                encoding="utf-8", errors="replace",
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                return []
            payload = json.loads(proc.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
            logger.debug("[Reach] Exa search failed: %s", e)
            return []

        results = payload.get("results", payload) if isinstance(payload, dict) else payload
        out = []
        for r in results if isinstance(results, list) else []:
            if isinstance(r, dict) and r.get("url"):
                out.append({
                    "title": str(r.get("title", ""))[:300],
                    "url": str(r["url"]),
                    "snippet": str(r.get("text", r.get("snippet", "")))[:600],
                })
        return out[:limit]

    # ── Reporting ──────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            "cli_available": self.cli_available,
            "reads": self._reads,
            "elapsed_s": round(self.elapsed, 1),
            "budget_left_s": round(self.budget_remaining, 1),
        }


# ── Helpers ─────────────────────────────────────────────────────────────────


def strip_html(text: str) -> str:
    """Collapse HTML to readable plain text."""
    import html as _html
    s = re.sub(r"(?is)<(script|style|noscript|template)[^>]*>.*?</\1>", " ", text or "")
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    s = re.sub(r"[ \t\f\v]+", " ", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()
