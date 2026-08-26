"""
OpportunityHub — Agent Reach Acquisition Source
https://github.com/Panniantong/Agent-Reach

Adds Agent Reach as a data-acquisition path in the scraper pipeline.

Agent Reach is a capability layer, not a dataset — it selects and health-checks
the best backend per platform and leaves the reading to the caller. This scraper
therefore consumes its *chosen backends* through `automation/reach.py`:

    rss    → publisher feeds (feedparser ▸ stdlib XML)
    web    → arbitrary listing pages as clean text (Jina Reader ▸ direct HTTP)
    search → Exa semantic discovery (optional, local only)

Deliberate design choices:

  * FEEDS ARE PREFERRED OVER SCRAPING. A feed is publisher-authored and already
    structured, so it survives site redesigns that break CSS selectors. Feeds are
    enabled by default; page scraping is opt-in.

  * WE DO NOT INVENT FIELDS. A feed gives a title, a link and a publish date —
    and a publish date is *not* a deadline. Writing one in would be fabricating
    exactly the kind of claim the verification stack exists to catch. Unknown
    fields are left empty for Layer 2 to enrich from the target page's own
    structured data.

  * OUTPUT IS TAGGED BY PROVENANCE. `reach:rss:*` carries real trust (0.80);
    `reach:web:*` is a heuristic guess (0.40) and will be quarantined by Layer 2
    until an independent source corroborates it. The acquisition layer does not
    get to declare its own reliability.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlsplit

from automation.scrapers.base_scraper import BaseScraper

logger = logging.getLogger("opportunityhub.scrapers.reach")


# Titles shorter than this are almost never real opportunity names.
MIN_TITLE_CHARS = 8
MAX_TITLE_CHARS = 180

# Words that suggest a link is an opportunity rather than site furniture.
# Used for LISTING pages and search results, where everything on the page is
# already opportunity-shaped and recall matters more than precision.
OPPORTUNITY_HINTS = (
    "hackathon", "hack", "buildathon", "codefest", "datathon", "ideathon",
    "designathon", "challenge", "competition", "contest", "sprint", "jam",
    "fellowship", "internship", "scholarship", "grant", "bounty", "summit",
    "conference", "olympiad", "quiz", "case study", "innovation",
)

# ── News-feed filtering ─────────────────────────────────────────────────────
# A general dev blog is ~98% irrelevant, so recall-oriented matching is wrong
# there. Observed failure: "Take our I/O 2026 quiz, vibe coded in Google AI
# Studio" matched on "quiz" and became a "hackathon". Precision wins here.
#
# STRONG terms are opportunity nouns that are essentially never used loosely.
STRONG_HINTS = (
    "hackathon", "hack-a-thon", "buildathon", "codefest", "datathon",
    "ideathon", "designathon", "summer of code", "fellowship", "internship",
    "scholarship", "olympiad", "capture the flag",
)

# WEAK terms are ambiguous in prose ("the challenge of scaling", "agile sprint",
# "developer summit"), so they only count alongside an explicit call to apply.
WEAK_HINTS = (
    "challenge", "competition", "contest", "grant", "bounty",
    "sprint", "jam", "award", "prize",
)

APPLICATION_SIGNALS = (
    "applications are open", "applications open", "application is open",
    "apply now", "apply by", "apply before", "now accepting",
    "registration is open", "registrations are open", "registration open",
    "register now", "submissions are open", "submissions open",
    "call for", "nominations are open", "nominations open",
    "sign-ups are open", "signups are open", "enter by", "deadline",
    "eligible students", "cash prize", "prize pool",
)


def _matches_opportunity_news(title: str, summary: str) -> bool:
    """
    Decide whether a general news/blog entry actually announces an opportunity.

    A strong noun is sufficient on its own. A weak noun needs a companion phrase
    that indicates people can actually apply, which is what separates
    "our developer challenge is now open" from "the challenge of low latency".
    """
    hay = f"{title} {summary}".lower()
    if any(term in hay for term in STRONG_HINTS):
        return True
    if any(term in hay for term in WEAK_HINTS):
        return any(sig in hay for sig in APPLICATION_SIGNALS)
    return False

# Navigation / boilerplate link text to discard when parsing listing pages.
NAV_NOISE = {
    "home", "login", "log in", "sign in", "sign up", "register", "about",
    "contact", "privacy", "terms", "blog", "careers", "help", "support",
    "faq", "pricing", "docs", "documentation", "next", "previous", "more",
    "read more", "learn more", "view all", "see all", "back", "menu",
    "search", "filter", "sort", "share", "download", "apply", "apply now",
    "cookie policy", "sitemap", "advertise", "press", "team", "features",
}


class AgentReachScraper(BaseScraper):
    """
    Multi-channel acquisition via Agent Reach's backends.

    Returns a dict of {category: [items]}, which the registry and pipeline
    already support (see GitHubRepoScraper).
    """

    def __init__(self, client=None):
        super().__init__(
            name="AgentReach-MultiChannel",
            url="https://github.com/Panniantong/Agent-Reach",
            category="hackathons",
        )
        self._client = client

    # ── Lazy client ────────────────────────────────────────────────────────

    def _get_client(self):
        if self._client is None:
            from automation.config import (
                REACH_ENABLED, REACH_USE_JINA, JINA_API_KEY,
                REACH_MAX_READS, REACH_TIME_BUDGET,
            )
            from automation.reach import ReachClient
            self._client = ReachClient(
                enabled=REACH_ENABLED,
                use_jina=REACH_USE_JINA,
                jina_api_key=JINA_API_KEY,
                max_reads=REACH_MAX_READS,
                time_budget=REACH_TIME_BUDGET,
            )
        return self._client

    # ── Entry point ────────────────────────────────────────────────────────

    def scrape(self) -> Dict[str, List[Dict]]:
        from automation.config import (
            REACH_ENABLED, REACH_FEEDS, REACH_WEB_TARGETS,
            REACH_SEARCH_ENABLED, REACH_SEARCH_QUERIES,
        )

        if not REACH_ENABLED:
            logger.info("[Reach] Disabled via REACH_ENABLED — skipping")
            return {}

        client = self._get_client()
        for st in client.doctor():
            logger.info("[Reach] %-7s → %-16s %s", st.name, st.backend, st.detail)

        results: Dict[str, List[Dict]] = {}

        # 1. RSS feeds — highest signal.
        for feed in REACH_FEEDS or []:
            if not feed.get("enabled", True):
                continue
            try:
                items = self._from_feed(client, feed)
                if items:
                    results.setdefault(feed["category"], []).extend(items)
                    logger.info("[Reach] rss %s → %d item(s)", feed["source"], len(items))
            except Exception as e:
                logger.warning("[Reach] feed %s failed: %s", feed.get("url"), e)

        # 2. Listing pages — opt-in, low trust.
        for target in REACH_WEB_TARGETS or []:
            if not target.get("enabled", False):
                continue
            try:
                items = self._from_web(client, target)
                if items:
                    results.setdefault(target["category"], []).extend(items)
                    logger.info("[Reach] web %s → %d item(s)", target["source"], len(items))
            except Exception as e:
                logger.warning("[Reach] web target %s failed: %s", target.get("url"), e)

        # 3. Semantic discovery — optional, local only.
        if REACH_SEARCH_ENABLED:
            for query in REACH_SEARCH_QUERIES or []:
                try:
                    items = self._from_search(client, query)
                    if items:
                        results.setdefault("hackathons", []).extend(items)
                        logger.info("[Reach] search %r → %d item(s)", query[:40], len(items))
                except Exception as e:
                    logger.warning("[Reach] search %r failed: %s", query[:40], e)

        for category in list(results):
            results[category] = self._dedupe(results[category])

        total = sum(len(v) for v in results.values())
        logger.info("[Reach] %d item(s) across %d category(ies) | %s",
                    total, len(results), client.get_stats())
        return results

    # ── Channel: rss ───────────────────────────────────────────────────────

    def _from_feed(self, client, feed: Dict) -> List[Dict]:
        entries = client.read_rss(feed["url"], limit=int(feed.get("limit", 40)))
        keyword_filtered = feed.get("filter") == "keywords"
        out = []
        kept = 0
        for e in entries:
            title = _clean_title(e.title)
            if not _plausible_title(title):
                continue
            link = (e.link or "").strip()
            if not link.startswith("http"):
                continue

            # General news feeds carry mostly irrelevant posts. Without this a
            # single dev-blog feed would inject 20 articles as "hackathons".
            if keyword_filtered and not _matches_opportunity_news(title, e.summary or ""):
                continue

            kept += 1
            out.append(self._record(
                name=title,
                link=link,
                source=feed["source"],
                description=(e.summary or "").strip()[:600],
                # NOTE: e.published is the feed's publish timestamp, not a
                # deadline. Leaving `deadline` empty lets Layer 2 enrich it from
                # the target page's own metadata instead of asserting a guess.
            ))
        if entries:
            logger.debug("[Reach] feed %s: %d entries → %d kept%s",
                         feed["source"], len(entries), kept,
                         " (keyword filtered)" if keyword_filtered else "")
        return out

    # ── Channel: web ───────────────────────────────────────────────────────

    def _from_web(self, client, target: Dict) -> List[Dict]:
        """
        Extract candidate opportunities from a listing page's clean text.

        This is unavoidably heuristic, which is exactly why the emitted records
        carry a low-trust `reach:web:*` source. Layer 2 holds them in quarantine
        until something independent confirms them.
        """
        doc = client.read_web(target["url"])
        if not doc.ok:
            logger.info("[Reach] web %s unavailable (%s)", target["url"], doc.error)
            return []

        base = target["url"]
        host = urlsplit(base).netloc.lower()
        seen = set()
        out = []

        # Markdown links are what Jina Reader emits: [text](href)
        for text, href in re.findall(r"\[([^\]\n]{3,200})\]\(([^)\s]+)\)", doc.text):
            title = _clean_title(text)
            if not _plausible_title(title):
                continue
            if title.lower() in NAV_NOISE:
                continue
            if not any(h in title.lower() for h in OPPORTUNITY_HINTS):
                continue

            url = urljoin(base, href.strip())
            if not url.startswith("http"):
                continue
            # Stay on the target site and require a detail-page-looking path.
            if urlsplit(url).netloc.lower() != host:
                continue
            if len([p for p in urlsplit(url).path.split("/") if p]) < 2:
                continue

            key = url.rstrip("/")
            if key in seen:
                continue
            seen.add(key)

            out.append(self._record(
                name=title,
                link=url,
                source=target["source"],
                description="",
            ))
            if len(out) >= int(target.get("limit", 40)):
                break
        return out

    # ── Channel: search ────────────────────────────────────────────────────

    def _from_search(self, client, query: str) -> List[Dict]:
        hits = client.search_web(query, limit=10)
        out = []
        for h in hits:
            title = _clean_title(h.get("title", ""))
            if not _plausible_title(title) or not any(
                k in title.lower() for k in OPPORTUNITY_HINTS
            ):
                continue
            out.append(self._record(
                name=title,
                link=h.get("url", ""),
                source="reach:search:exa",
                description=(h.get("snippet") or "")[:600],
            ))
        return out

    # ── Shared record shape ────────────────────────────────────────────────

    @staticmethod
    def _record(name: str, link: str, source: str, description: str = "") -> Dict:
        """
        Build a record in the project schema.

        Every field we cannot actually observe is left empty on purpose. An empty
        deadline is honest and gets enriched downstream; a fabricated one would
        be indistinguishable from the scraper drift this whole stack exists to
        detect.
        """
        return {
            "name": name,
            "organizer": "",
            "description": description,
            "eligibility": "",
            "mode": "",
            "fee": "",
            "prize": "",
            "deadline": "",
            "applicationLink": link,
            "website": link,
            "tags": ["agent-reach"],
            "status": "open",
            "source": source,
        }

    @staticmethod
    def _dedupe(items: List[Dict]) -> List[Dict]:
        seen_links, seen_names, out = set(), set(), []
        for it in items:
            link = (it.get("applicationLink") or "").rstrip("/").lower()
            name = re.sub(r"\W+", " ", (it.get("name") or "").lower()).strip()
            if link and link in seen_links:
                continue
            if name and name in seen_names:
                continue
            seen_links.add(link)
            seen_names.add(name)
            out.append(it)
        return out


# ── Helpers ─────────────────────────────────────────────────────────────────


def _clean_title(text: str) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    s = re.sub(r"^[#*\-•\d.\s]+", "", s)          # markdown bullets / numbering
    s = re.sub(r"[|·–—]\s*$", "", s).strip()
    return s[:MAX_TITLE_CHARS]


def _plausible_title(title: str) -> bool:
    if not title or len(title) < MIN_TITLE_CHARS:
        return False
    if title.lower() in NAV_NOISE:
        return False
    if not re.search(r"[A-Za-z]{3}", title):
        return False
    # Reject things that are obviously URLs or image alt junk.
    if title.lower().startswith(("http", "www.", "data:")):
        return False
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    scraper = AgentReachScraper()
    data = scraper.scrape()
    for cat, items in data.items():
        print(f"\n=== {cat}: {len(items)} ===")
        for it in items[:10]:
            print(f"  {it['source']:<26} {it['name'][:64]}")
            print(f"  {'':<26} {it['applicationLink'][:88]}")
