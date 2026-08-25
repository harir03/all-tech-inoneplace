"""
OpportunityHub — Codeforces Scraper
Scrapes upcoming contests from codeforces.com via their public API.
No Scrapling needed — Codeforces has a clean JSON API.
"""

import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


class CodeforcesScraper:
    """Fetches upcoming Codeforces contests via their public API.
    
    Unlike other scrapers, this uses Codeforces' official API
    (no anti-bot bypass needed).
    """

    def __init__(self):
        self.name = "Codeforces"
        self.url = "https://codeforces.com/api/contest.list"
        self.category = "competitions"

    def run(self):
        logger.info(f"[{self.name}] Fetching contests from API...")
        try:
            return self.scrape()
        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}")
            return []

    def scrape(self):
        resp = requests.get(self.url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "OK":
            logger.warning(f"[Codeforces] API returned status: {data.get('status')}")
            return []

        contests = data.get("result", [])
        # Only upcoming contests (phase == "BEFORE")
        upcoming = [c for c in contests if c.get("phase") == "BEFORE"]
        logger.info(f"[Codeforces] Found {len(upcoming)} upcoming contests")

        opportunities = []
        for contest in upcoming[:15]:  # Limit to 15 most recent
            start_time = contest.get("startTimeSeconds", 0)
            duration_sec = contest.get("durationSeconds", 0)

            start_dt = datetime.utcfromtimestamp(start_time) if start_time else None
            event_date = start_dt.strftime("%Y-%m-%d %H:%M UTC") if start_dt else ""
            deadline = start_dt.strftime("%Y-%m-%d") if start_dt else "Check page"
            duration_hrs = f"{duration_sec // 3600}h {(duration_sec % 3600) // 60}m" if duration_sec else ""

            contest_type = contest.get("type", "").replace("_", " ").title()

            opportunity = {
                "name": contest.get("name", "Codeforces Contest"),
                "organizer": "Codeforces",
                "description": f"Codeforces {contest_type} contest. Duration: {duration_hrs}",
                "eligibility": "Open to all",
                "mode": "Online",
                "fee": "Free",
                "prize": "Rating change + prizes for top performers",
                "deadline": deadline,
                "eventDate": event_date,
                "applicationLink": f"https://codeforces.com/contest/{contest.get('id', '')}",
                "website": f"https://codeforces.com/contest/{contest.get('id', '')}",
                "tags": ["codeforces", "competitive-programming", "contest"],
                "status": "open",
                "source": "codeforces-api",
            }
            opportunities.append(opportunity)

        return opportunities
