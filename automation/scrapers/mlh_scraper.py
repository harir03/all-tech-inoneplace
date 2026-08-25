"""
OpportunityHub — Major League Hacking (MLH) Live Scraper
Scrapes all upcoming MLH hackathons and Global Hack Weeks directly from mlh.io/events.
"""

import logging
import urllib.request
import ssl
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class MLHScraper:
    """Scrapes live upcoming student hackathons from MLH."""

    def __init__(self):
        self.name = "MLH"
        self.url = "https://mlh.io/events"
        self.category = "hackathons"

    def run(self):
        logger.info(f"[{self.name}] Fetching live events from MLH...")
        try:
            return self.scrape()
        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}")
            return []

    def scrape(self):
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            self.url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
        )

        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
                html = response.read().decode("utf-8", errors="ignore")
        except Exception as e:
            logger.error(f"[MLH] Request failed: {e}")
            return []

        soup = BeautifulSoup(html, "html.parser")
        h4_tags = soup.find_all("h4")
        logger.info(f"[MLH] Found {len(h4_tags)} potential event headings")

        opportunities = []
        for h in h4_tags:
            name = h.text.strip()
            if not name or len(name) < 3 or name.lower() in ("mlh", "major league hacking", "menu", "events"):
                continue

            container = h.find_parent("a") or h.find_parent("div", class_=lambda c: c and "rounded" in c) or h.parent.parent.parent
            if not container:
                continue

            # Extract application URL
            link = ""
            if container.name == "a" and container.get("href"):
                link = container.get("href")
            else:
                a_tag = container.find("a", href=True)
                if a_tag:
                    link = a_tag["href"]

            if not link or not link.startswith("http"):
                link = "https://mlh.io/events"

            all_texts = list(container.stripped_strings)
            
            # Find date strings like 'SEP 18 - 20' or 'AUG 28 - 30'
            date_str = ""
            location_str = "Global"
            mode = "Online"

            for t in all_texts:
                if any(m in t.upper() for m in ["JAN ", "FEB ", "MAR ", "APR ", "MAY ", "JUN ", "JUL ", "AUG ", "SEP ", "OCT ", "NOV ", "DEC "]):
                    date_str = t
                if "In-Person" in t:
                    mode = "In-Person"
                elif "Digital" in t or "Online" in t or "Everywhere" in t:
                    mode = "Online"

            # Filter location from text list
            loc_candidates = [t for t in all_texts if t != name and t != date_str and t not in ("In-Person", "Digital", "DIVERSITY", ",")]
            if loc_candidates:
                location_str = " ".join(loc_candidates[:2]).replace(" ,", ",").strip()

            opportunity = {
                "name": name,
                "organizer": "Major League Hacking (MLH)",
                "description": f"Official MLH Member Hackathon. Location: {location_str}.",
                "eligibility": "Students worldwide (High School & University 18+)",
                "mode": mode,
                "fee": "Free",
                "prize": "Prizes, Swag, Hardware Labs, Mentorship",
                "deadline": date_str or "Check event page",
                "eventDate": date_str or "",
                "applicationLink": link,
                "website": link,
                "tags": ["mlh", "hackathon", "student", "global"],
                "status": "open",
                "source": "mlh-live-events",
            }
            opportunities.append(opportunity)

        logger.info(f"[MLH] Successfully parsed {len(opportunities)} live hackathons")
        return opportunities
