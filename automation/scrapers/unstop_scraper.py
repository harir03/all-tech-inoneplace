"""
OpportunityHub — Unstop Scraper
Scrapes hackathons and competitions from unstop.com.
"""

import logging
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class UnstopScraper(BaseScraper):
    """Scrapes listings from Unstop (formerly Dare2Compete).
    
    Targets both /hackathons and /competitions pages.
    Unstop uses dynamic rendering — StealthyFetcher handles JS.
    """

    def __init__(self, target="hackathons"):
        url_map = {
            "hackathons": "https://unstop.com/hackathons",
            "competitions": "https://unstop.com/competitions",
        }
        category_map = {
            "hackathons": "hackathons",
            "competitions": "competitions",
        }
        super().__init__(
            name=f"Unstop-{target}",
            url=url_map.get(target, url_map["hackathons"]),
            category=category_map.get(target, "hackathons"),
        )
        self.target = target

    def scrape(self):
        page = self.fetch_page()
        if not page:
            return []

        opportunities = []

        try:
            # Unstop renders opportunity cards in a listing format.
            # Look for common card patterns.
            cards = page.css(".single_listing, .opportunity-card, [class*='listing']") or []
            logger.info(f"[{self.name}] Found {len(cards)} listing elements")

            for card in cards:
                try:
                    name = self._extract_text(card, "h2, h3, h4, .title, [class*='title']")
                    if not name or len(name) < 3:
                        continue

                    link_el = card.css("a[href]")
                    link = ""
                    if link_el:
                        link = link_el[0].attrib.get("href", "")
                        if link and not link.startswith("http"):
                            link = f"https://unstop.com{link}"

                    organizer = self._extract_text(card, ".organiser, .organization, [class*='organiz']") or "Via Unstop"

                    opportunity = {
                        "name": name,
                        "organizer": organizer,
                        "description": self._extract_text(card, "p, .description, [class*='desc']") or f"{self.target.title()} on Unstop",
                        "eligibility": "Check listing page for details",
                        "mode": "Check listing page",
                        "fee": "Check listing page",
                        "prize": self._extract_text(card, "[class*='prize'], [class*='reward']") or "Check listing page",
                        "deadline": self._extract_text(card, "[class*='date'], [class*='deadline'], time") or "Check listing page",
                        "eventDate": "",
                        "applicationLink": link or self.url,
                        "website": link or self.url,
                        "tags": ["unstop", self.target],
                        "status": "open",
                        "source": "unstop-scraper",
                    }
                    opportunities.append(opportunity)
                except Exception as e:
                    logger.debug(f"[{self.name}] Failed to parse a card: {e}")
                    continue

        except Exception as e:
            logger.error(f"[{self.name}] Parsing failed: {e}")

        return opportunities

    def _extract_text(self, element, selector):
        """Safely extract text from a child element using CSS selector."""
        try:
            found = element.css(selector)
            if found:
                return found[0].text.strip() if hasattr(found[0], 'text') else ""
        except Exception:
            pass
        return ""
