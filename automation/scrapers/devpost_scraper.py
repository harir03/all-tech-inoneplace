"""
OpportunityHub — Devpost Scraper
Scrapes hackathons from devpost.com (huge global hackathon directory).
"""

import logging
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class DevpostScraper(BaseScraper):
    """Scrapes Devpost for upcoming hackathons.
    
    Devpost is one of the largest hackathon directories globally.
    Their listing page is server-rendered, making it scrapable.
    """

    def __init__(self):
        super().__init__(
            name="Devpost",
            url="https://devpost.com/hackathons?status[]=upcoming&status[]=open",
            category="hackathons",
        )

    def scrape(self):
        page = self.fetch_page()
        if not page:
            return []

        opportunities = []
        try:
            cards = page.css(".hackathon-tile, .hackathon-listing, [data-hackathon-tile]") or []
            logger.info(f"[Devpost] Found {len(cards)} hackathon tiles")

            for card in cards:
                try:
                    name = self._extract_text(card, "h2, h3, .title, [class*='title']")
                    if not name or len(name) < 3:
                        continue

                    link_el = card.css("a[href*='devpost.com']") or card.css("a[href]")
                    link = ""
                    if link_el:
                        link = link_el[0].attrib.get("href", "")
                        if link and not link.startswith("http"):
                            link = f"https://devpost.com{link}"

                    prize_text = self._extract_text(card, "[class*='prize'], [class*='money']")
                    date_text = self._extract_text(card, "[class*='date'], [class*='submission'], time")
                    location = self._extract_text(card, "[class*='location']")

                    mode = "Online"
                    if location:
                        loc_lower = location.lower()
                        if any(kw in loc_lower for kw in ["in-person", "onsite", "city", "university"]):
                            mode = "In-Person"
                        elif "hybrid" in loc_lower:
                            mode = "Hybrid"

                    opportunity = {
                        "name": name,
                        "organizer": "Via Devpost",
                        "description": self._extract_text(card, "p, .tagline, [class*='tagline']") or f"Hackathon on Devpost",
                        "eligibility": "Open — check listing page",
                        "mode": mode,
                        "fee": "Free",
                        "prize": prize_text or "Check listing page",
                        "deadline": date_text or "Check listing page",
                        "eventDate": date_text or "",
                        "applicationLink": link or self.url,
                        "website": link or self.url,
                        "tags": ["devpost", "hackathon"],
                        "status": "open",
                        "source": "devpost-scraper",
                    }
                    opportunities.append(opportunity)
                except Exception as e:
                    logger.debug(f"[Devpost] Parse error: {e}")
                    continue
        except Exception as e:
            logger.error(f"[Devpost] Failed: {e}")

        return opportunities

    def _extract_text(self, element, selector):
        try:
            found = element.css(selector)
            if found:
                return found[0].text.strip() if hasattr(found[0], 'text') else ""
        except Exception:
            pass
        return ""
