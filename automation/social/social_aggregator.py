"""
OpportunityHub — Social Aggregator
Collects and deduplicates results from all social media monitors.
"""

import logging
from .reddit_monitor import monitor_reddit
from .twitter_monitor import monitor_twitter

logger = logging.getLogger(__name__)


def aggregate_social_findings():
    """Run all social media monitors and aggregate results.
    
    Returns:
        dict: {category: [opportunities]} grouped by detected category.
    """
    all_finds = []

    # Run monitors
    all_finds.extend(monitor_reddit())
    all_finds.extend(monitor_twitter())

    logger.info(f"[Social] Total raw findings: {len(all_finds)}")

    # Categorize findings based on content keywords
    categorized = {
        "hackathons": [],
        "internships": [],
        "competitions": [],
        "open-source-programs": [],
        "fellowships": [],
    }

    for item in all_finds:
        category = _detect_category(item)
        categorized[category].append(item)

    for cat, items in categorized.items():
        if items:
            logger.info(f"[Social] {cat}: {len(items)} findings")

    return categorized


def _detect_category(item):
    """Guess the category of an opportunity based on its text content."""
    text = f"{item.get('name', '')} {item.get('description', '')}".lower()

    if any(kw in text for kw in ["hackathon", "hack ", "buildathon", "makeathon"]):
        return "hackathons"
    if any(kw in text for kw in ["internship", "intern ", "summer training"]):
        return "internships"
    if any(kw in text for kw in ["fellowship", "fellow "]):
        return "fellowships"
    if any(kw in text for kw in ["gsoc", "open source program", "mentorship program", "outreachy", "lfx"]):
        return "open-source-programs"
    if any(kw in text for kw in ["competition", "contest", "challenge", "competitive programming"]):
        return "competitions"

    # Default to hackathons
    return "hackathons"
