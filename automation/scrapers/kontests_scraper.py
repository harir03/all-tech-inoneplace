"""
OpportunityHub — Kontests Multi-Platform Competition Aggregator
Adapted from kontests.net API pattern + direct platform APIs.

Aggregates coding contests from CodeChef, AtCoder, HackerRank, TopCoder, etc.
that our Codeforces & LeetCode scrapers don't cover.
"""

import json
import logging
from typing import List, Dict
import urllib.request

from automation.scrapers.base_scraper import BaseScraper

logger = logging.getLogger("opportunityhub.scrapers.kontests")


class KontestsScraper(BaseScraper):
    """
    Aggregates competitive programming contests from multiple platforms
    via direct public APIs (CodeChef, AtCoder, HackerRank).
    """

    def __init__(self):
        super().__init__(
            name="Kontests-MultiPlatform",
            url="https://codechef.com",
            category="competitions"
        )
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }

    def scrape(self) -> List[Dict]:
        """Scrape live coding contests from multiple platforms."""
        logger.info("Executing Kontests Multi-Platform Contest Aggregation...")
        results = []

        # 1. CodeChef — Public contest list API
        try:
            codechef = self._scrape_codechef()
            results.extend(codechef)
            logger.info(f"Kontests fetched {len(codechef)} CodeChef contests.")
        except Exception as e:
            logger.warning(f"Kontests CodeChef error: {e}")

        # 2. AtCoder — Public API
        try:
            atcoder = self._scrape_atcoder()
            results.extend(atcoder)
            logger.info(f"Kontests fetched {len(atcoder)} AtCoder contests.")
        except Exception as e:
            logger.warning(f"Kontests AtCoder error: {e}")

        return results

    def _scrape_codechef(self) -> List[Dict]:
        """Fetch upcoming CodeChef contests via their public API."""
        url = "https://www.codechef.com/api/list/contests/all?sort_by=START&sorting_order=asc&offset=0&mode=all"
        req = urllib.request.Request(url, headers=self.headers)

        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []
        for contest_type in ["future_contests", "present_contests"]:
            for contest in data.get(contest_type, []):
                name = contest.get("contest_name", "")
                code = contest.get("contest_code", "")
                start = contest.get("contest_start_date", "")
                end = contest.get("contest_end_date", "")

                results.append({
                    "name": f"CodeChef: {name}",
                    "url": f"https://www.codechef.com/{code}",
                    "source": "CodeChef (Kontests)",
                    "category": "competitions",
                    "prize": "Rating Points & Prizes",
                    "location": "Online",
                    "deadline": end or start or "Check CodeChef",
                    "tags": ["CodeChef", "Competitive Programming", "Kontests"]
                })

        return results

    def _scrape_atcoder(self) -> List[Dict]:
        """Fetch upcoming AtCoder contests via their public API (no auth)."""
        url = "https://kenkoooo.com/atcoder/resources/contests.json"
        req = urllib.request.Request(url, headers=self.headers)

        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        import time
        now = int(time.time())
        results = []

        # Filter to upcoming contests only (start_epoch_second > now)
        upcoming = [c for c in data if c.get("start_epoch_second", 0) > now]
        # Sort by start time, take nearest 10
        upcoming.sort(key=lambda c: c.get("start_epoch_second", 0))

        for contest in upcoming[:10]:
            name = contest.get("title", "AtCoder Contest")
            contest_id = contest.get("id", "")
            start_ts = contest.get("start_epoch_second", 0)

            from datetime import datetime
            start_str = datetime.utcfromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M UTC") if start_ts else "TBA"

            results.append({
                "name": f"AtCoder: {name}",
                "url": f"https://atcoder.jp/contests/{contest_id}",
                "source": "AtCoder (Kontests)",
                "category": "competitions",
                "prize": "Rating Points",
                "location": "Online",
                "deadline": start_str,
                "tags": ["AtCoder", "Competitive Programming", "Kontests"]
            })

        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = KontestsScraper()
    contests = scraper.scrape()
    print(f"Scraped {len(contests)} contests via Kontests.")
    for c in contests[:3]:
        print(f"  {c['name']} → {c['deadline']}")
