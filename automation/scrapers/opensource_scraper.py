"""
OpportunityHub — GSoC / Open Source Programs Scraper
Scrapes Google Summer of Code organizations and other OS program listings.
"""

import logging
import requests
from .base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class GSoCScraper:
    """Fetches GSoC participating organizations.
    
    Uses Google's public GSoC API to get current/upcoming program info.
    """

    def __init__(self):
        self.name = "GSoC"
        self.url = "https://summerofcode.withgoogle.com"
        self.category = "open-source-programs"

    def run(self):
        logger.info(f"[{self.name}] Checking GSoC program status...")
        try:
            return self.scrape()
        except Exception as e:
            logger.error(f"[{self.name}] Failed: {e}")
            return []

    def scrape(self):
        # GSoC has a JSON API for organizations
        api_url = "https://summerofcode.withgoogle.com/api/program/current"

        try:
            resp = requests.get(api_url, timeout=15, headers={
                "User-Agent": "OpportunityHub/1.0"
            })
            if resp.status_code == 200:
                program = resp.json()
                return [self._program_to_opportunity(program)]
            else:
                logger.info(f"[GSoC] No current program data (status {resp.status_code})")
                return []
        except Exception as e:
            logger.debug(f"[GSoC] API unavailable: {e}")
            return []

    def _program_to_opportunity(self, program):
        name = program.get("name", "Google Summer of Code")
        return {
            "name": name,
            "organizer": "Google",
            "description": "Google Summer of Code — contribute to open source projects with mentorship and a stipend.",
            "eligibility": "Open to anyone 18+ (students and non-students)",
            "mode": "Online / Remote",
            "fee": "Free",
            "stipend": "Varies by country ($1500-$6600)",
            "deadline": "Check timeline at summerofcode.withgoogle.com",
            "applicationLink": self.url,
            "website": self.url,
            "tags": ["gsoc", "google", "open-source", "stipend"],
            "status": "open",
            "source": "gsoc-api",
        }


class OpenSourceProgramsScraper(BaseScraper):
    """Scrapes the 'Every Open Source Programs' GitHub repo for program listings.
    
    This is a community-maintained list that covers GSoC, LFX, Outreachy, etc.
    Uses GitHub's raw content API to fetch the README.
    """

    def __init__(self):
        super().__init__(
            name="EveryOSProgram",
            url="https://raw.githubusercontent.com/Every-Open-Source-Programs/Every-Open-Source-Programs/main/README.md",
            category="open-source-programs",
        )

    def scrape(self):
        try:
            resp = requests.get(self.url, timeout=15, headers={
                "User-Agent": "OpportunityHub/1.0"
            })
            resp.raise_for_status()
            content = resp.text
        except Exception as e:
            logger.error(f"[EveryOSProgram] Failed to fetch README: {e}")
            return []

        return self._parse_markdown_table(content)

    def _parse_markdown_table(self, content):
        """Extract programs from markdown table rows."""
        opportunities = []
        in_table = False

        for line in content.split("\n"):
            line = line.strip()

            # Detect table rows (pipes at start and end)
            if line.startswith("|") and line.endswith("|"):
                cells = [c.strip() for c in line.split("|")[1:-1]]

                # Skip header and separator rows
                if len(cells) < 2:
                    continue
                if all(c.replace("-", "").replace(":", "") == "" for c in cells):
                    in_table = True
                    continue
                if not in_table:
                    in_table = True
                    continue

                name = self._strip_markdown_link_text(cells[0]) if len(cells) > 0 else ""
                if not name or len(name) < 3:
                    continue

                link = self._extract_markdown_link_url(cells[0]) if len(cells) > 0 else ""

                opportunity = {
                    "name": name,
                    "organizer": "Open Source Community",
                    "description": cells[1] if len(cells) > 1 else f"Open source program: {name}",
                    "eligibility": cells[2] if len(cells) > 2 else "Check program page",
                    "mode": "Remote / Online",
                    "fee": "Free",
                    "deadline": cells[3] if len(cells) > 3 else "Check program page",
                    "applicationLink": link or "Check program page",
                    "website": link or "",
                    "tags": ["open-source"],
                    "status": "open",
                    "source": "every-os-programs-github",
                }
                opportunities.append(opportunity)
            else:
                if in_table:
                    in_table = False  # End of table

        logger.info(f"[EveryOSProgram] Parsed {len(opportunities)} programs from README")
        return opportunities

    def _strip_markdown_link_text(self, text):
        """Extract display text from [text](url) format."""
        import re
        match = re.match(r'\[([^\]]+)\]', text)
        return match.group(1) if match else text

    def _extract_markdown_link_url(self, text):
        """Extract URL from [text](url) format."""
        import re
        match = re.search(r'\]\(([^)]+)\)', text)
        return match.group(1) if match else ""
