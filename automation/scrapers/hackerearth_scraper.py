"""
OpportunityHub — HackerEarth Scraper
Scrapes hackathons and challenges from hackerearth.com.
"""

import logging
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class HackerEarthScraper(BaseScraper):
    """Scrapes HackerEarth for hackathons and coding challenges."""

    def __init__(self):
        super().__init__(
            name="HackerEarth",
            url="https://www.hackerearth.com/challenges/",
            category="hackathons",
        )

    def scrape(self):
        page = self.fetch_page()
        if not page:
            return []

        opportunities = []
        try:
            cards = page.css(".challenge-card, .challenge-list-item, [class*='challenge']") or []
            logger.info(f"[HackerEarth] Found {len(cards)} challenge elements")

            for card in cards:
                try:
                    name = self._extract_text(card, "h3, h4, .challenge-name, [class*='title']")
                    if not name or len(name) < 3:
                        continue

                    link_el = card.css("a[href]")
                    link = ""
                    if link_el:
                        link = link_el[0].attrib.get("href", "")
                        if link and not link.startswith("http"):
                            link = f"https://www.hackerearth.com{link}"

                    # Determine if it's a hackathon or competition
                    text_lower = name.lower()
                    is_hackathon = any(kw in text_lower for kw in ["hackathon", "hack", "buildathon"])

                    opportunity = {
                        "name": name,
                        "organizer": "Via HackerEarth",
                        "description": self._extract_text(card, "p, .desc, [class*='desc']") or f"Challenge on HackerEarth",
                        "eligibility": "Open — check listing page",
                        "mode": "Online",
                        "fee": "Free",
                        "prize": self._extract_text(card, "[class*='prize']") or "Check listing page",
                        "deadline": self._extract_text(card, "[class*='date'], time, [class*='end']") or "Check page",
                        "eventDate": "",
                        "applicationLink": link or self.url,
                        "website": link or self.url,
                        "tags": ["hackerearth", "hackathon" if is_hackathon else "competition"],
                        "status": "open",
                        "source": "hackerearth-scraper",
                    }
                    opportunities.append(opportunity)
                except Exception as e:
                    logger.debug(f"[HackerEarth] Parse error: {e}")
                    continue
        except Exception as e:
            logger.error(f"[HackerEarth] Failed: {e}")

        return opportunities

    def _extract_text(self, element, selector):
        try:
            found = element.css(selector)
            if found:
                return found[0].text.strip() if hasattr(found[0], 'text') else ""
        except Exception:
            pass
        return ""
