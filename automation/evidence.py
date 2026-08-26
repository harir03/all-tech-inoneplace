"""
OpportunityHub — Evidence Collection (Layer 2 substrate)

Layer 1 (`verification.py`) scores an item using *heuristics about the item itself*.
This module does something categorically different: it goes to the source of truth
(the opportunity's own page) and extracts **independent, structured observations**
that were never touched by the scraper.

That distinction is the whole point of a second layer. Layer 1 asks
"does this record look plausible?". Layer 2 asks "does the internet agree?".

Extraction strategy, strongest signal first:

    1. JSON-LD (schema.org)  — Devpost, MLH, Unstop, Devfolio, most job boards
                               emit `Event` / `JobPosting` blocks with machine
                               readable startDate / endDate / validThrough.
                               This is ground truth: publisher-authored metadata.
    2. OpenGraph / Twitter   — og:title, og:description, og:site_name.
    3. Raw HTML              — <title>, <h1>, visible "registration closed" phrases.

Hard engineering constraints (this runs hourly in CI with a 10 minute cap):

    * Global wall-clock budget      — never blow the CI timeout.
    * Per-URL cache                 — each URL is fetched at most once per run.
    * Byte cap                       — read a bounded prefix, not whole pages.
    * Circuit breaker               — if the network is broadly failing, stop
                                      probing and report NO_EVIDENCE instead of
                                      producing false "contradictions". A
                                      verification layer that rejects everything
                                      when the network hiccups is worse than none.
"""

from __future__ import annotations

import gzip
import hashlib
import html
import json
import logging
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("opportunityhub.evidence")


# ── Tunables ────────────────────────────────────────────────────────────────
FETCH_TIMEOUT = 8               # Per-request socket timeout (seconds)
MAX_BYTES = 262_144             # 256 KB prefix is plenty for <head> + JSON-LD
MAX_EXTRACT_CHARS = 600_000     # Upper bound for regex work during extraction
MAX_VISIBLE_CHARS = 200_000     # How much visible text to scan for status phrases
DEFAULT_TIME_BUDGET = 240.0     # Total seconds Layer 2 may spend on network I/O
BREAKER_MIN_ATTEMPTS = 6        # Don't judge the network before this many tries
BREAKER_FAILURE_RATE = 0.75     # Trip breaker above this hard-failure rate

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36 "
    "OpportunityHub-Adjudicator/1.0 (+https://github.com/opportunityhub)"
)

# schema.org types that describe an opportunity
EVENT_TYPES = {
    "event", "hackathon", "educationevent", "socialevent", "businessevent",
    "festival", "courseinstance",
}
POSTING_TYPES = {"jobposting", "internship"}

# Phrases that indicate the opportunity is no longer accepting entries.
CLOSED_PHRASES = (
    "registration is closed", "registrations are closed", "registration closed",
    "registrations closed", "applications are closed", "applications closed",
    "application closed", "submissions are closed", "submissions closed",
    "this hackathon has ended", "this event has ended", "event has ended",
    "hackathon has ended", "competition has ended", "challenge has ended",
    "no longer accepting", "deadline has passed", "entries are closed",
    "this position is no longer", "job posting has expired",
    "posting is no longer available", "this opportunity has closed",
    "winners announced", "winners have been announced",
)

# Phrases that indicate the page is a dead end / not the opportunity.
ROT_PHRASES = (
    "404", "page not found", "not found", "no longer exists",
    "domain is for sale", "buy this domain", "parked domain",
    "account suspended", "this site can", "coming soon",
    "under construction", "expired domain",
)

# Bot-check / CAPTCHA / rate-limit interstitials.
#
# These are the most dangerous pages we can encounter, because they return
# HTTP 200 with real-looking content. If such a page is accepted as evidence, the
# adjudicator compares the record's true title against something like
# "Security Check - Indeed.com", finds no overlap, and REJECTS a perfectly valid
# opportunity. Observed for real: routing a 401 from indeed.com through Jina
# Reader yields exactly that title.
#
# So an interstitial must be classified as ABSENCE of evidence, never as
# contradicting evidence.
CHALLENGE_TITLE_PATTERNS = (
    "security check", "just a moment", "attention required", "access denied",
    "are you a robot", "are you human", "verify you are human", "captcha",
    "checking your browser", "bot verification", "human verification",
    "unusual traffic", "rate limit", "too many requests", "403 forbidden",
    "cloudflare", "ddos-guard", "please wait", "one more step",
    "enable javascript", "javascript is required", "verifying you are human",
)

# Only trusted when the page is thin — these words appear in legitimate copy too.
CHALLENGE_BODY_PHRASES = (
    "enable javascript and cookies to continue", "verify you are a human",
    "complete the security check", "your request has been blocked",
    "automated queries", "unusual traffic from your computer",
    "please verify you are a human", "checking if the site connection is secure",
)
CHALLENGE_THIN_PAGE_CHARS = 2_000

# Evidence quality tiers
EV_JSONLD = "jsonld"    # publisher-authored structured data — strongest
EV_OG = "opengraph"     # publisher-authored social metadata — strong
EV_HTML = "html"        # scraped visible text — weak
EV_NONE = "none"        # nothing usable

_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


@dataclass
class Evidence:
    """An independent observation of an opportunity's own page."""

    url: str
    ok: bool = False
    kind: str = EV_NONE
    status: Optional[int] = None
    final_url: str = ""
    error: str = ""

    # Extracted facts
    title: str = ""
    og_title: str = ""
    jsonld_name: str = ""
    description: str = ""
    site_name: str = ""
    organizer: str = ""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    valid_through: Optional[date] = None
    prize_text: str = ""
    closed_signals: List[str] = field(default_factory=list)
    rot_signals: List[str] = field(default_factory=list)
    challenge_signals: List[str] = field(default_factory=list)
    jsonld_types: List[str] = field(default_factory=list)

    # Integrity
    content_hash: str = ""
    fetched_at: str = ""
    elapsed_ms: int = 0
    via: str = "direct"     # Transport that produced this evidence: direct | reach

    # ── Derived helpers ────────────────────────────────────────────────────
    @property
    def has_structured_dates(self) -> bool:
        return any((self.end_date, self.valid_through, self.start_date))

    @property
    def effective_end(self) -> Optional[date]:
        """Best available "this is over after" date."""
        return self.valid_through or self.end_date

    @property
    def titles(self) -> List[str]:
        """All observed titles, strongest first."""
        return [t for t in (self.jsonld_name, self.og_title, self.title) if t]

    @property
    def is_strong(self) -> bool:
        """Strong enough to justify rejecting a scraper's claim."""
        return self.ok and self.kind in (EV_JSONLD, EV_OG)

    def summary(self) -> str:
        if not self.ok:
            return f"no-evidence({self.error or self.status})"
        bits = [self.kind]
        if self.via != "direct":
            bits.append(f"via={self.via}")
        if self.effective_end:
            bits.append(f"ends={self.effective_end.isoformat()}")
        if self.closed_signals:
            bits.append(f"closed:{self.closed_signals[0][:28]}")
        if self.rot_signals:
            bits.append(f"rot:{self.rot_signals[0][:20]}")
        return " ".join(bits)


class EvidenceCollector:
    """
    Bounded, cached, circuit-broken page-fact collector.

    One instance per pipeline run. Safe to call with thousands of items — it will
    simply stop doing network I/O once the time budget is spent and report
    NO_EVIDENCE from then on (which the adjudicator treats as "unproven",
    never as "disproven").
    """

    def __init__(
        self,
        time_budget: float = DEFAULT_TIME_BUDGET,
        enabled: bool = True,
        reach: Optional[Any] = None,
    ):
        """
        Args:
            time_budget: Total seconds of network I/O allowed for this run.
            enabled:     Master switch; when False every probe reports NO_EVIDENCE.
            reach:       Optional `ReachClient`. When supplied, pages that block
                         direct access (401/403/429) or return no usable metadata
                         are retried through Agent Reach's `web` channel (Jina
                         Reader), which renders server-side and preserves JSON-LD.
                         Without it, bot-walled sites stay permanently unverifiable.
        """
        self.enabled = enabled
        self.time_budget = time_budget
        self.reach = reach
        self._started = time.monotonic()
        self._cache: Dict[str, Evidence] = {}
        self._attempts = 0
        self._hard_failures = 0
        self._breaker_tripped = False
        self.stats = {
            "fetched": 0, "cache_hits": 0, "jsonld": 0, "opengraph": 0,
            "html_only": 0, "failed": 0, "skipped_budget": 0, "skipped_breaker": 0,
            "reach_attempts": 0, "reach_rescued": 0, "challenge_pages": 0,
        }

    # ── Budget / breaker ───────────────────────────────────────────────────

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._started

    @property
    def budget_remaining(self) -> float:
        return max(0.0, self.time_budget - self.elapsed)

    @property
    def network_healthy(self) -> bool:
        """False once the breaker trips — callers must downgrade, not reject."""
        return not self._breaker_tripped

    def _maybe_trip_breaker(self) -> None:
        if self._breaker_tripped or self._attempts < BREAKER_MIN_ATTEMPTS:
            return
        rate = self._hard_failures / max(1, self._attempts)
        if rate >= BREAKER_FAILURE_RATE:
            self._breaker_tripped = True
            logger.warning(
                "[Evidence] Circuit breaker TRIPPED — %d/%d probes hard-failed (%.0f%%). "
                "Layer 2 will downgrade to 'unproven' instead of rejecting.",
                self._hard_failures, self._attempts, rate * 100,
            )

    # ── Public API ─────────────────────────────────────────────────────────

    def collect(self, url: str) -> Evidence:
        """Fetch `url` once and extract structured facts. Never raises."""
        if not url or not url.lower().startswith(("http://", "https://")):
            return Evidence(url=url or "", ok=False, error="invalid_url")

        key = self._cache_key(url)
        if key in self._cache:
            self.stats["cache_hits"] += 1
            return self._cache[key]

        if not self.enabled:
            return Evidence(url=url, ok=False, error="disabled")
        if self._breaker_tripped:
            self.stats["skipped_breaker"] += 1
            return Evidence(url=url, ok=False, error="network_down")
        if self.budget_remaining <= 0:
            self.stats["skipped_budget"] += 1
            return Evidence(url=url, ok=False, error="budget_exhausted")

        ev = self._fetch_and_extract(url)

        # Agent Reach fallback. Two situations make a direct probe useless:
        #   1. The host bot-walled us (401/403/429) or 5xx'd — no facts at all.
        #   2. We got a page but it carried no usable metadata (JS shell).
        # In both cases Jina Reader may still render it, so retry once through
        # the Reach web channel before declaring the item unverifiable.
        if self._should_try_reach(ev):
            rescued = self._collect_via_reach(url, ev)
            if rescued is not None:
                ev = rescued

        self._cache[key] = ev
        return ev

    # ── Reach fallback ─────────────────────────────────────────────────────

    def _should_try_reach(self, ev: Evidence) -> bool:
        if self.reach is None or self.budget_remaining <= 2.0:
            return False
        # A definitive 404/410 is a real answer; do not waste a Reach read on it.
        if ev.rot_signals:
            return False
        if not ev.ok:
            return ev.error.startswith(("blocked_", "http_5", "network:", "unexpected:"))
        # Fetched, but nothing worth reconciling against.
        return ev.kind == EV_NONE or not (ev.titles or ev.has_structured_dates)

    def _collect_via_reach(self, url: str, previous: Evidence) -> Optional[Evidence]:
        """Re-probe via Agent Reach's web channel, returning richer evidence or None."""
        self.stats["reach_attempts"] += 1
        try:
            doc = self.reach.read_html(url)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("[Evidence] Reach fallback errored for %s: %s", url, e)
            return None

        if not getattr(doc, "ok", False) or not getattr(doc, "raw", ""):
            return None

        ev = Evidence(url=url, ok=True, via="reach")
        ev.status = previous.status
        ev.final_url = previous.final_url or url
        ev.content_hash = hashlib.sha256(doc.raw.encode("utf-8", "ignore")).hexdigest()[:16]
        ev.fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        ev.elapsed_ms = getattr(doc, "elapsed_ms", 0)

        # Jina's HTML mode preserves JSON-LD and OG tags, so the standard
        # extractor works unchanged and can still reach EV_JSONLD strength.
        self._extract(ev, doc.raw)

        if ev.kind == EV_NONE and not ev.titles:
            return None

        self.stats["reach_rescued"] += 1
        logger.debug(
            "[Evidence] Reach rescued %s (was %s, now %s)",
            url, previous.error or "no-metadata", ev.kind,
        )
        return ev

    # ── Fetch ──────────────────────────────────────────────────────────────

    def _fetch_and_extract(self, url: str) -> Evidence:
        ev = Evidence(url=url)
        started = time.monotonic()
        self._attempts += 1

        timeout = min(FETCH_TIMEOUT, max(2.0, self.budget_remaining))

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ev.status = getattr(resp, "status", None) or resp.getcode()
                ev.final_url = resp.geturl() or url
                raw = resp.read(MAX_BYTES)
                raw = self._decompress(raw, resp.headers.get("Content-Encoding", ""))
                charset = self._charset(resp.headers.get("Content-Type", ""))
                text = raw.decode(charset, errors="ignore")

            self.stats["fetched"] += 1
            ev.ok = True
            ev.content_hash = hashlib.sha256(raw).hexdigest()[:16]
            ev.fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            self._extract(ev, text)

        except urllib.error.HTTPError as e:
            # An HTTP error is a *real answer* from a *reachable* server, so it
            # does not count toward the circuit breaker.
            ev.status = e.code
            ev.final_url = getattr(e, "url", url) or url
            ev.error = f"http_{e.code}"
            self.stats["failed"] += 1
            if e.code in (401, 403, 429):
                # Bot-walled or rate-limited: the page exists, we just can't read
                # it. Explicitly *not* evidence of a dead link.
                ev.error = f"blocked_{e.code}"
            elif e.code in (404, 410):
                ev.rot_signals.append(f"http_{e.code}")

        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            ev.error = f"network:{type(e).__name__}"
            self._hard_failures += 1
            self.stats["failed"] += 1
            self._maybe_trip_breaker()

        except Exception as e:  # pragma: no cover - defensive
            ev.error = f"unexpected:{type(e).__name__}"
            self._hard_failures += 1
            self.stats["failed"] += 1
            self._maybe_trip_breaker()

        ev.elapsed_ms = int((time.monotonic() - started) * 1000)
        return ev

    @staticmethod
    def _decompress(raw: bytes, encoding: str) -> bytes:
        enc = (encoding or "").lower()
        try:
            if "gzip" in enc:
                return gzip.decompress(raw)
            if "deflate" in enc:
                return zlib.decompress(raw, -zlib.MAX_WBITS)
        except Exception:
            # Truncated stream (expected — we only read a prefix). Salvage what
            # we can with a streaming decompressor.
            try:
                d = zlib.decompressobj(16 + zlib.MAX_WBITS if "gzip" in enc else -zlib.MAX_WBITS)
                return d.decompress(raw)
            except Exception:
                return raw
        return raw

    @staticmethod
    def _charset(content_type: str) -> str:
        m = re.search(r"charset=([\w\-]+)", content_type or "", re.I)
        if m:
            try:
                "x".encode(m.group(1))
                return m.group(1)
            except Exception:
                pass
        return "utf-8"

    @staticmethod
    def _cache_key(url: str) -> str:
        """Normalize URL so trivial variants share a cache slot."""
        try:
            p = urllib.parse.urlsplit(url.strip())
            netloc = p.netloc.lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]
            path = (p.path or "/").rstrip("/") or "/"
            # Drop tracking params
            q = [
                (k, v) for k, v in urllib.parse.parse_qsl(p.query)
                if not k.lower().startswith(("utm_", "ref", "fbclid", "gclid"))
            ]
            query = urllib.parse.urlencode(sorted(q))
            return urllib.parse.urlunsplit(("https", netloc, path, query, ""))
        except Exception:
            return url.strip().lower().rstrip("/")

    # ── Extraction ─────────────────────────────────────────────────────────

    def _extract(self, ev: Evidence, text: str) -> None:
        # Do NOT re-truncate here. The caller already bounded the payload, and
        # clipping again would silently discard structured data: Jina's HTML mode
        # returns up to 400 KB and sites such as unstop.com emit their JSON-LD
        # well past the 256 KB direct-fetch cap. Clipping cost us those blocks.
        head = text[:MAX_EXTRACT_CHARS]
        lowered = head.lower()

        # --- <title> and <h1> ---
        m = re.search(r"<title[^>]*>(.*?)</title>", head, re.I | re.S)
        if m:
            ev.title = self._clean(m.group(1))
        if not ev.title:
            m = re.search(r"<h1[^>]*>(.*?)</h1>", head, re.I | re.S)
            if m:
                ev.title = self._clean(re.sub(r"<[^>]+>", " ", m.group(1)))

        # --- meta tags (OpenGraph / Twitter / standard) ---
        metas = self._meta_tags(head)
        ev.og_title = self._clean(
            metas.get("og:title") or metas.get("twitter:title") or ""
        )
        ev.description = self._clean(
            metas.get("og:description")
            or metas.get("twitter:description")
            or metas.get("description")
            or ""
        )
        ev.site_name = self._clean(metas.get("og:site_name") or "")

        # --- Interstitial / bot-check gate (runs FIRST) ---
        # Must precede JSON-LD parsing and quality-tier accounting: a CAPTCHA
        # page is an absence of evidence, and counting it as `opengraph` would
        # both corrupt the stats and hand the adjudicator a title that
        # contradicts every legitimate record.
        visible = self._visible_text(head)
        vlow = visible.lower()
        title_low = (ev.title or "").lower()
        og_low = (ev.og_title or "").lower()

        for pat in CHALLENGE_TITLE_PATTERNS:
            if pat in title_low or pat in og_low:
                ev.challenge_signals.append(pat)
        if len(visible.strip()) < CHALLENGE_THIN_PAGE_CHARS:
            for pat in CHALLENGE_BODY_PHRASES:
                if pat in vlow:
                    ev.challenge_signals.append(pat)

        if ev.challenge_signals:
            ev.ok = False
            ev.kind = EV_NONE
            ev.error = f"challenge_page:{ev.challenge_signals[0][:24]}"
            ev.title = ev.og_title = ev.jsonld_name = ""
            ev.description = ev.site_name = ""
            ev.start_date = ev.end_date = ev.valid_through = None
            ev.closed_signals = []
            ev.rot_signals = []
            self.stats["challenge_pages"] += 1
            return

        # --- JSON-LD (strongest) ---
        self._extract_jsonld(ev, head)

        # --- Quality tier ---
        if ev.jsonld_name or ev.has_structured_dates:
            ev.kind = EV_JSONLD
            self.stats["jsonld"] += 1
        elif ev.og_title or ev.description:
            ev.kind = EV_OG
            self.stats["opengraph"] += 1
        elif ev.title:
            ev.kind = EV_HTML
            self.stats["html_only"] += 1
        else:
            ev.kind = EV_NONE

        # --- Closure / rot detection ---
        ev.closed_signals = [p for p in CLOSED_PHRASES if p in vlow][:4]

        # Rot detection is deliberately conservative: only trust it when the
        # signal appears in the <title>, since "404" and "not found" show up
        # inside legitimate pages' scripts and error-handling copy all the time.
        ev.rot_signals += [p for p in ROT_PHRASES if p in title_low][:3]

    @staticmethod
    def _meta_tags(head: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for tag in re.findall(r"<meta\s[^>]*>", head, re.I):
            key = re.search(r'(?:property|name)\s*=\s*["\']([^"\']+)["\']', tag, re.I)
            val = re.search(r'content\s*=\s*["\']([^"\']*)["\']', tag, re.I)
            if key and val:
                out.setdefault(key.group(1).strip().lower(), val.group(1))
        return out

    def _extract_jsonld(self, ev: Evidence, head: str) -> None:
        blocks = re.findall(
            r'<script[^>]+type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            head, re.I | re.S,
        )
        for block in blocks[:12]:
            payload = self._parse_json_lenient(block)
            if payload is None:
                continue
            for node in self._walk_jsonld(payload):
                types = self._node_types(node)
                if not types:
                    continue
                ev.jsonld_types.extend(types)
                if types & EVENT_TYPES:
                    self._absorb_event(ev, node)
                elif types & POSTING_TYPES:
                    self._absorb_posting(ev, node)

    @staticmethod
    def _parse_json_lenient(block: str) -> Optional[Any]:
        raw = html.unescape(block).strip()
        raw = re.sub(r"^<!\[CDATA\[|\]\]>$", "", raw).strip()
        try:
            return json.loads(raw)
        except Exception:
            # Truncated by our byte cap — try the largest balanced prefix.
            for end in range(len(raw), max(0, len(raw) - 4000), -1):
                if raw[end - 1] in "}]":
                    try:
                        return json.loads(raw[:end])
                    except Exception:
                        continue
            return None

    @classmethod
    def _walk_jsonld(cls, node: Any, depth: int = 0) -> Iterable[dict]:
        """Yield every dict in a JSON-LD payload, including @graph children."""
        if depth > 6:
            return
        if isinstance(node, list):
            for item in node:
                yield from cls._walk_jsonld(item, depth + 1)
        elif isinstance(node, dict):
            yield node
            for key in ("@graph", "subEvent", "subEvents", "itemListElement", "mainEntity"):
                if key in node:
                    yield from cls._walk_jsonld(node[key], depth + 1)

    @staticmethod
    def _node_types(node: dict) -> set:
        t = node.get("@type") or node.get("type") or []
        if isinstance(t, str):
            t = [t]
        if not isinstance(t, list):
            return set()
        return {str(x).split("/")[-1].strip().lower() for x in t}

    def _absorb_event(self, ev: Evidence, node: dict) -> None:
        if not ev.jsonld_name:
            ev.jsonld_name = self._clean(str(node.get("name") or ""))
        ev.start_date = ev.start_date or self._parse_date(node.get("startDate"))
        ev.end_date = ev.end_date or self._parse_date(node.get("endDate"))
        if not ev.organizer:
            ev.organizer = self._entity_name(node.get("organizer") or node.get("author"))
        if not ev.prize_text:
            ev.prize_text = self._offer_text(node.get("offers"))
        status = str(node.get("eventStatus") or "").lower()
        if "cancel" in status or "postpone" in status:
            ev.closed_signals.append(f"eventStatus={status.split('/')[-1]}")

    def _absorb_posting(self, ev: Evidence, node: dict) -> None:
        if not ev.jsonld_name:
            ev.jsonld_name = self._clean(str(node.get("title") or node.get("name") or ""))
        ev.valid_through = ev.valid_through or self._parse_date(node.get("validThrough"))
        ev.start_date = ev.start_date or self._parse_date(node.get("datePosted"))
        if not ev.organizer:
            ev.organizer = self._entity_name(node.get("hiringOrganization"))

    @staticmethod
    def _entity_name(val: Any) -> str:
        if isinstance(val, dict):
            return str(val.get("name") or "").strip()[:160]
        if isinstance(val, str):
            return val.strip()[:160]
        if isinstance(val, list) and val:
            return EvidenceCollector._entity_name(val[0])
        return ""

    @staticmethod
    def _offer_text(val: Any) -> str:
        if isinstance(val, list) and val:
            val = val[0]
        if isinstance(val, dict):
            price = val.get("price") or val.get("highPrice") or ""
            cur = val.get("priceCurrency") or ""
            if price:
                return f"{cur} {price}".strip()[:120]
        return ""

    @staticmethod
    def _parse_date(val: Any) -> Optional[date]:
        """Parse a schema.org date/datetime. Returns None on anything unusable."""
        if not val:
            return None
        if isinstance(val, list):
            val = val[0] if val else None
        if not isinstance(val, str):
            return None
        s = val.strip()
        if not s:
            return None
        m = _ISO_DATE.match(s)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
        try:
            from dateutil.parser import parse as parse_date
            return parse_date(s, fuzzy=False).date()
        except Exception:
            return None

    @staticmethod
    def _clean(s: str) -> str:
        s = html.unescape(s or "")
        s = re.sub(r"\s+", " ", s).strip()
        return s[:300]

    @staticmethod
    def _visible_text(head: str) -> str:
        body = re.sub(r"(?is)<(script|style|noscript|template)[^>]*>.*?</\1>", " ", head)
        body = re.sub(r"<[^>]+>", " ", body)
        body = html.unescape(body)
        return re.sub(r"\s+", " ", body)[:MAX_VISIBLE_CHARS]

    # ── Reporting ──────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            "unique_urls": len(self._cache),
            "attempts": self._attempts,
            "hard_failures": self._hard_failures,
            "breaker_tripped": self._breaker_tripped,
            "elapsed_s": round(self.elapsed, 1),
            "budget_left_s": round(self.budget_remaining, 1),
        }
