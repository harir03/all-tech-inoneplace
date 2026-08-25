"""
OpportunityHub — Devpost Live Scraper
Fetches real-time, currently open and upcoming hackathons via Devpost's official JSON API.
"""

import logging
import re
import urllib.request
import json
import ssl

logger = logging.getLogger(__name__)


class DevpostScraper:
    """Scrapes active hackathons directly from Devpost's live API."""

    def __init__(self):
        self.name = "Devpost"
        self.url = "https://devpost.com/api/hackathons"
        self.category = "hackathons"

    def run(self):
        logger.info(f"[{self.name}] Fetching live hackathons from Devpost API...")
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
                "Accept": "application/json, text/javascript, */*",
            },
        )

        try:
            with urllib.request.urlopen(req, context=ctx, timeout=12) as response:
                raw_data = response.read().decode("utf-8", errors="ignore")
                data = json.loads(raw_data)
        except Exception as e:
            logger.error(f"[Devpost] API request failed: {e}")
            return []

        hackathons = data.get("hackathons", [])
        logger.info(f"[Devpost] Found {len(hackathons)} live hackathons")

        opportunities = []
        for h in hackathons:
            title = h.get("title", "").strip()
            if not title:
                continue

            link = h.get("url", "").strip()
            time_str = h.get("submission_period_dates", "").strip()
            prize_raw = h.get("prize_amount", "")
            
            # Clean prize html tag like $<span data-currency-value>740,000</span>
            prize_clean = re.sub(r'<[^>]+>', '', prize_raw).strip() if prize_raw else "Check listing page"
            
            themes = [t.get("name") for t in h.get("themes", []) if t.get("name")]
            displayed_location = h.get("displayed_location", {})
            location_name = displayed_location.get("location", "Online") if displayed_location else "Online"

            mode = "Online"
            if "in-person" in location_name.lower() or "onsite" in location_name.lower():
                mode = "In-Person"
            elif location_name and location_name.lower() != "online":
                mode = location_name

            open_state = h.get("open_state", "open")
            status = "open" if open_state == "open" else ("coming-soon" if open_state == "upcoming" else "closed")

            opportunity = {
                "name": title,
                "organizer": "Via Devpost",
                "description": f"Live Hackathon on Devpost. Themes: {', '.join(themes) if themes else 'General'}.",
                "eligibility": "Open to all developers & students (check listing)",
                "mode": mode,
                "fee": "Free",
                "prize": prize_clean or "Check listing page",
                "deadline": time_str or "Check event page",
                "eventDate": time_str,
                "applicationLink": link or "https://devpost.com/hackathons",
                "website": link or "https://devpost.com/hackathons",
                "tags": ["devpost", "hackathon"] + [t.lower() for t in themes[:3]],
                "status": status,
                "source": "devpost-live-api",
            }
            opportunities.append(opportunity)

        return opportunities
