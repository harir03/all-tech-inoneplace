"""
OpportunityHub — MLH Scraper
Scrapes hackathon events from Major League Hacking (mlh.io).
"""

import logging
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class MLHScraper(BaseScraper):
    """Scrapes the MLH Events page for upcoming hackathons.
    
    MLH's event listing is relatively well-structured HTML,
    making it one of the more reliable scraping targets.
    """

    def __init__(self):
        super().__init__(
            name="MLH",
            url="https://mlh.io/seasons/2026/events",
            category="hackathons",
        )

    def scrape(self):
        page = self.fetch_page()
        if not page:
            return []

        opportunities = []

        try:
            # MLH uses .event cards with structured data
            cards = page.css(".event, .event-wrapper, [class*='event']") or []
            logger.info(f"[MLH] Found {len(cards)} event elements")

            for card in cards:
                try:
                    name = self._extract_text(card, "h3, h4, .event-name, [class*='name']")
                    if not name or len(name) < 3:
                        continue

                    # Extract event link
                    link_el = card.css("a[href]")
                    link = ""
                    if link_el:
                        link = link_el[0].attrib.get("href", "")
                        if link and not link.startswith("http"):
                            link = f"https://mlh.io{link}"

                    # Extract date
                    date_text = self._extract_text(card, ".event-date, [class*='date'], time")

                    # Extract location
                    location = self._extract_text(card, ".event-location, [class*='location']")

                    # Determine mode from location text
                    mode = "In-Person"
                    if location:
                        loc_lower = location.lower()
                        if "digital" in loc_lower or "online" in loc_lower or "virtual" in loc_lower:
                            mode = "Online"
                        elif "hybrid" in loc_lower:
                            mode = "Hybrid"

                    opportunity = {
                        "name": name,
                        "organizer": "MLH (Major League Hacking)",
                        "description": f"MLH hackathon event. {location or ''}".strip(),
                        "eligibility": "Students (18+, global)",
                        "mode": mode,
                        "fee": "Free",
                        "prize": "Varies — swag, prizes, and MLH points",
                        "deadline": date_text or "Check MLH page",
                        "eventDate": date_text or "",
                        "applicationLink": link or self.url,
                        "website": link or self.url,
                        "tags": ["mlh", "hackathon", "student"],
                        "status": "open",
                        "source": "mlh-scraper",
                    }
                    opportunities.append(opportunity)
                except Exception as e:
                    logger.debug(f"[MLH] Failed to parse an event: {e}")
                    continue

        except Exception as e:
            logger.error(f"[MLH] Parsing failed: {e}")

        return opportunities

    def _extract_text(self, element, selector):
        """Safely extract text from a child element."""
        try:
            found = element.css(selector)
            if found:
                return found[0].text.strip() if hasattr(found[0], 'text') else ""
        except Exception:
            pass
        return ""
