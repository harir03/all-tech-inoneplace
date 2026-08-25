"""
OpportunityHub — Base Scraper
Shared scraping logic using Scrapling's adaptive fetchers.
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Base class for all OpportunityHub scrapers.
    
    Subclasses must implement:
        - scrape() -> list[dict]: Fetch and parse opportunities from the target site.
    
    Each returned dict should follow the JSON schema from data/*.json files.
    """

    def __init__(self, name, url, category):
        self.name = name
        self.url = url
        self.category = category
        self._fetcher = None

    def _get_fetcher(self):
        """Lazily initialize a Scrapling StealthyFetcher (with anti-bot bypass)."""
        if self._fetcher is None:
            try:
                from scrapling import StealthyFetcher
                self._fetcher = StealthyFetcher()
            except ImportError:
                logger.warning(
                    "Scrapling not installed. Install with: "
                    "pip install 'scrapling[fetchers]' && scrapling install"
                )
                raise
        return self._fetcher

    def fetch_page(self, url=None):
        """Fetch a page using Scrapling's stealth fetcher.
        
        Returns a Scrapling Adaptor (parsed page) or None on failure.
        """
        target_url = url or self.url
        logger.info(f"[{self.name}] Fetching: {target_url}")
        try:
            fetcher = self._get_fetcher()
            page = fetcher.fetch(target_url)
            return page
        except Exception as e:
            logger.error(f"[{self.name}] Failed to fetch {target_url}: {e}")
            return None

    @abstractmethod
    def scrape(self):
        """Scrape opportunities from the target website.
        
        Returns:
            list[dict]: List of opportunity dicts matching the JSON schema.
        """
        pass

    def run(self):
        """Run the scraper with error handling and logging."""
        logger.info(f"[{self.name}] Starting scrape of {self.url}")
        try:
            results = self.scrape()
            logger.info(f"[{self.name}] Found {len(results)} opportunities")
            return results
        except Exception as e:
            logger.error(f"[{self.name}] Scrape failed: {e}")
            return []
