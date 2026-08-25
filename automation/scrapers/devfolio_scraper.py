"""
OpportunityHub — Devfolio Scraper
Scrapes upcoming hackathons from devfolio.co/hackathons.
"""

import logging
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class DevfolioScraper(BaseScraper):
    """Scrapes hackathon listings from Devfolio.
    
    Devfolio is a React SSR app. Scrapling's StealthyFetcher handles
    JavaScript rendering to access the dynamic content.
    """

    def __init__(self):
        super().__init__(
            name="Devfolio",
            url="https://devfolio.co/hackathons",
            category="hackathons",
        )

    def scrape(self):
        page = self.fetch_page()
        if not page:
            return []

        opportunities = []

        # Devfolio renders hackathon cards in a list.
        # The exact selectors may change — Scrapling's adaptive tracking helps.
        try:
            cards = page.css("a[href*='/hackathons/']") or []
            logger.info(f"[Devfolio] Found {len(cards)} hackathon card links")

            for card in cards:
                try:
                    name = self._extract_name(card)
                    if not name:
                        continue

                    link = card.attrib.get("href", "")
                    if link and not link.startswith("http"):
                        link = f"https://devfolio.co{link}"

                    opportunity = {
                        "name": name,
                        "organizer": "Via Devfolio",
                        "description": self._extract_text(card, "p") or f"Hackathon listed on Devfolio",
                        "eligibility": "Check hackathon page for details",
                        "mode": "Check hackathon page",
                        "fee": "Check hackathon page",
                        "prize": "Check hackathon page",
                        "deadline": "Check hackathon page",
                        "eventDate": "",
                        "applicationLink": link,
                        "website": link,
                        "tags": ["devfolio", "hackathon"],
                        "status": "open",
                        "source": "devfolio-scraper",
                    }
                    opportunities.append(opportunity)
                except Exception as e:
                    logger.debug(f"[Devfolio] Failed to parse a card: {e}")
                    continue

        except Exception as e:
            logger.error(f"[Devfolio] CSS selector failed: {e}")

        return opportunities

    def _extract_name(self, element):
        """Try to extract the hackathon name from a card element."""
        # Try heading elements first, then fall back to text
        for tag in ["h2", "h3", "h4", "strong"]:
            found = element.css(tag)
            if found:
                text = found[0].text.strip() if hasattr(found[0], 'text') else ""
                if text and len(text) > 3:
                    return text

        # Fall back to the element's own text
        text = element.text.strip() if hasattr(element, 'text') else ""
        if text and len(text) > 3 and len(text) < 100:
            return text
        return None

    def _extract_text(self, element, selector):
        """Safely extract text from a child element."""
        try:
            found = element.css(selector)
            if found:
                return found[0].text.strip() if hasattr(found[0], 'text') else ""
        except Exception:
            pass
        return ""
