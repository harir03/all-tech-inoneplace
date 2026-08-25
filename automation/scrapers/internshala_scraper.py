"""
OpportunityHub — Internshala Scraper
Scrapes internships from internshala.com (India's biggest internship platform).
"""

import logging
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class InternshalaScraper(BaseScraper):
    """Scrapes Internshala for tech internships.
    
    Filters for CS/IT/software internships relevant to the target audience.
    """

    def __init__(self):
        super().__init__(
            name="Internshala",
            url="https://internshala.com/internships/computer-science-internship/",
            category="internships",
        )

    def scrape(self):
        page = self.fetch_page()
        if not page:
            return []

        opportunities = []
        try:
            cards = page.css(".internship_meta, .individual_internship, [class*='internship']") or []
            logger.info(f"[Internshala] Found {len(cards)} internship listings")

            for card in cards:
                try:
                    name = self._extract_text(card, "h3, .company_and_premium a, [class*='heading'], .profile a")
                    if not name or len(name) < 3:
                        continue

                    company = self._extract_text(card, ".company_name, [class*='company'], h4")
                    link_el = card.css("a[href*='/internship/']") or card.css("a[href]")
                    link = ""
                    if link_el:
                        link = link_el[0].attrib.get("href", "")
                        if link and not link.startswith("http"):
                            link = f"https://internshala.com{link}"

                    stipend = self._extract_text(card, ".stipend, [class*='stipend'], [class*='salary']")
                    duration = self._extract_text(card, ".duration, [class*='duration']")
                    location = self._extract_text(card, ".locations, [class*='location']")

                    mode = "Check listing"
                    if location:
                        if "work from home" in location.lower() or "remote" in location.lower():
                            mode = "Remote / Work From Home"
                        else:
                            mode = location

                    opportunity = {
                        "name": name,
                        "organizer": company or "Via Internshala",
                        "description": f"Internship at {company or 'company'} via Internshala",
                        "eligibility": "Check listing page for details",
                        "mode": mode,
                        "fee": "Free",
                        "stipend": stipend or "Check listing page",
                        "duration": duration or "Check listing page",
                        "deadline": "Apply ASAP — rolling",
                        "applicationLink": link or self.url,
                        "website": link or self.url,
                        "tags": ["internshala", "internship", "india"],
                        "status": "open",
                        "source": "internshala-scraper",
                    }
                    opportunities.append(opportunity)
                except Exception as e:
                    logger.debug(f"[Internshala] Parse error: {e}")
                    continue
        except Exception as e:
            logger.error(f"[Internshala] Failed: {e}")

        return opportunities

    def _extract_text(self, element, selector):
        try:
            found = element.css(selector)
            if found:
                return found[0].text.strip() if hasattr(found[0], 'text') else ""
        except Exception:
            pass
        return ""
