"""
OpportunityHub — Scraper Registry
Auto-registers all scrapers. The pipeline calls get_all_scrapers() to get
every available scraper instance.

To add a new data source: either
  1. Add a new repo to GITHUB_SOURCES in github_repos_scraper.py (easiest)
  2. Create a new scraper file and register it below

Each scraper that fails to import is skipped — one broken scraper won't kill the pipeline.
"""

import logging

logger = logging.getLogger(__name__)


def get_all_scrapers():
    """Return a list of all registered scraper instances.
    
    Ordered by reliability:
    1. GitHub repo scrapers (most reliable — just HTTP GET, structured data)
    2. API-based scrapers (Codeforces, LeetCode — public JSON/GraphQL APIs)
    3. Website scrapers (need Scrapling — may fail if site changes)
    """
    scrapers = []

    # ═══════════════════════════════════════════════════════════════
    # TIER 1: GitHub Repos (MOST RELIABLE — no anti-bot, structured data)
    # This single scraper pulls from 7+ curated GitHub repos at once
    # ═══════════════════════════════════════════════════════════════
    try:
        from .github_repos_scraper import GitHubRepoScraper
        scrapers.append(GitHubRepoScraper())
    except Exception as e:
        logger.warning(f"[Registry] Skipping GitHubRepoScraper: {e}")

    # ═══════════════════════════════════════════════════════════════
    # TIER 2: Public API scrapers (reliable — official JSON/GraphQL APIs)
    # ═══════════════════════════════════════════════════════════════
    try:
        from .codeforces_scraper import CodeforcesScraper
        scrapers.append(CodeforcesScraper())
    except Exception as e:
        logger.warning(f"[Registry] Skipping CodeforcesScraper: {e}")

    try:
        from .leetcode_scraper import LeetCodeScraper
        scrapers.append(LeetCodeScraper())
    except Exception as e:
        logger.warning(f"[Registry] Skipping LeetCodeScraper: {e}")

    try:
        from .opensource_scraper import GSoCScraper
        scrapers.append(GSoCScraper())
    except Exception as e:
        logger.warning(f"[Registry] Skipping GSoCScraper: {e}")

    try:
        from .company_hackathons_scraper import CompanyHackathonsScraper
        scrapers.append(CompanyHackathonsScraper())
    except Exception as e:
        logger.warning(f"[Registry] Skipping CompanyHackathonsScraper: {e}")

    # ═══════════════════════════════════════════════════════════════
    # TIER 3: Website scrapers (need Scrapling — may break if site changes)
    # These are bonus sources. If Scrapling isn't installed, they're skipped.
    # ═══════════════════════════════════════════════════════════════
    try:
        from .devfolio_scraper import DevfolioScraper
        scrapers.append(DevfolioScraper())
    except Exception as e:
        logger.warning(f"[Registry] Skipping DevfolioScraper: {e}")

    try:
        from .unstop_scraper import UnstopScraper
        scrapers.append(UnstopScraper("hackathons"))
        scrapers.append(UnstopScraper("competitions"))
    except Exception as e:
        logger.warning(f"[Registry] Skipping UnstopScraper: {e}")

    try:
        from .mlh_scraper import MLHScraper
        scrapers.append(MLHScraper())
    except Exception as e:
        logger.warning(f"[Registry] Skipping MLHScraper: {e}")

    try:
        from .devpost_scraper import DevpostScraper
        scrapers.append(DevpostScraper())
    except Exception as e:
        logger.warning(f"[Registry] Skipping DevpostScraper: {e}")

    try:
        from .hackerearth_scraper import HackerEarthScraper
        scrapers.append(HackerEarthScraper())
    except Exception as e:
        logger.warning(f"[Registry] Skipping HackerEarthScraper: {e}")

    try:
        from .internshala_scraper import InternshalaScraper
        scrapers.append(InternshalaScraper())
    except Exception as e:
        logger.warning(f"[Registry] Skipping InternshalaScraper: {e}")

    logger.info(f"[Registry] Loaded {len(scrapers)} scrapers: {[s.name for s in scrapers]}")
    return scrapers
