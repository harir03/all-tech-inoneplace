"""
OpportunityHub — LeetCode Contest Scraper
Fetches upcoming LeetCode contests via their GraphQL API.
"""

import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)


class LeetCodeScraper:
    """Fetches upcoming LeetCode contests via GraphQL.
    
    LeetCode has weekly and biweekly contests.
    Uses their public GraphQL endpoint (no auth needed).
    """

    def __init__(self):
        self.name = "LeetCode"
        self.url = "https://leetcode.com/graphql"
        self.category = "competitions"

    def run(self):
        logger.info(f"[{self.name}] Fetching contests from GraphQL API...")
        try:
            return self.scrape()
        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}")
            return []

    def scrape(self):
        query = """
        {
            allContests {
                title
                titleSlug
                startTime
                duration
                originStartTime
            }
        }
        """

        headers = {
            "Content-Type": "application/json",
            "Referer": "https://leetcode.com/contest/",
        }

        try:
            resp = requests.post(
                self.url,
                json={"query": query},
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"[LeetCode] API request failed: {e}")
            return []

        contests = data.get("data", {}).get("allContests", [])
        now = datetime.utcnow().timestamp()

        # Filter to upcoming contests only
        upcoming = [c for c in contests if c.get("startTime", 0) > now]
        upcoming.sort(key=lambda c: c.get("startTime", 0))
        upcoming = upcoming[:10]  # Next 10 contests

        logger.info(f"[LeetCode] Found {len(upcoming)} upcoming contests")

        opportunities = []
        for contest in upcoming:
            start_time = contest.get("startTime", 0)
            duration = contest.get("duration", 0)
            start_dt = datetime.utcfromtimestamp(start_time) if start_time else None

            event_date = start_dt.strftime("%Y-%m-%d %H:%M UTC") if start_dt else ""
            deadline = start_dt.strftime("%Y-%m-%d") if start_dt else "Check page"
            duration_str = f"{duration // 60} minutes" if duration else ""
            slug = contest.get("titleSlug", "")

            opportunity = {
                "name": contest.get("title", "LeetCode Contest"),
                "organizer": "LeetCode",
                "description": f"LeetCode competitive programming contest. Duration: {duration_str}",
                "eligibility": "Open to all — free LeetCode account",
                "mode": "Online",
                "fee": "Free",
                "prize": "Rating change + badges",
                "deadline": deadline,
                "eventDate": event_date,
                "applicationLink": f"https://leetcode.com/contest/{slug}/" if slug else "https://leetcode.com/contest/",
                "website": f"https://leetcode.com/contest/{slug}/" if slug else "https://leetcode.com/contest/",
                "tags": ["leetcode", "competitive-programming", "contest"],
                "status": "open",
                "source": "leetcode-api",
            }
            opportunities.append(opportunity)

        return opportunities
