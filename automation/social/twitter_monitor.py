"""
OpportunityHub — Twitter/X Monitor
Monitors Twitter/X for hackathon/internship announcements.
Uses Agent-Reach CLI (requires auth cookies for Twitter).
"""

import logging
import subprocess

from ..config import TWITTER_CONFIG

logger = logging.getLogger(__name__)


def monitor_twitter():
    """Monitor Twitter/X for opportunity announcements.
    
    Requires Agent-Reach CLI installed with Twitter cookies configured.
    This is disabled by default since it requires manual auth setup.
    
    Returns:
        list[dict]: Potential opportunities found on Twitter/X.
    """
    if not TWITTER_CONFIG.get("enabled", False):
        logger.info("[Twitter] Monitoring disabled in config (requires auth cookies)")
        return []

    all_finds = []

    for hashtag in TWITTER_CONFIG.get("hashtags", []):
        posts = _search_twitter(hashtag)
        opportunities = _tweets_to_opportunities(posts, hashtag)
        all_finds.extend(opportunities)
        logger.info(f"[Twitter] {hashtag}: found {len(opportunities)} opportunities")

    for account in TWITTER_CONFIG.get("accounts", []):
        posts = _read_account(account)
        opportunities = _tweets_to_opportunities(posts, f"@{account}")
        all_finds.extend(opportunities)
        logger.info(f"[Twitter] @{account}: found {len(opportunities)} opportunities")

    return all_finds


def _search_twitter(query):
    """Search Twitter using Agent-Reach CLI."""
    try:
        result = subprocess.run(
            ["agent-reach", "search", "twitter", query, "--limit", "20"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return _parse_output(result.stdout)
    except FileNotFoundError:
        logger.warning("[Twitter] Agent-Reach not installed. Install from: github.com/Panniantong/Agent-Reach")
    except subprocess.TimeoutExpired:
        logger.warning("[Twitter] Agent-Reach timed out")
    except Exception as e:
        logger.error(f"[Twitter] Error: {e}")
    return []


def _read_account(account):
    """Read recent posts from a Twitter account using Agent-Reach."""
    try:
        result = subprocess.run(
            ["agent-reach", "read", "twitter", f"@{account}", "--limit", "10"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return _parse_output(result.stdout)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.error(f"[Twitter] Error reading @{account}: {e}")
    return []


def _parse_output(output):
    """Parse Agent-Reach output into structured tweet dicts."""
    tweets = []
    current = {}

    for line in output.split("\n"):
        line = line.strip()
        if not line:
            if current.get("text"):
                tweets.append(current)
                current = {}
            continue
        if line.startswith("Text:") or line.startswith("Tweet:"):
            current["text"] = line.split(":", 1)[1].strip()
        elif line.startswith("URL:") or line.startswith("Link:"):
            current["url"] = line.split(":", 1)[1].strip()
        elif line.startswith("Author:") or line.startswith("User:"):
            current["author"] = line.split(":", 1)[1].strip()

    if current.get("text"):
        tweets.append(current)
    return tweets


def _tweets_to_opportunities(tweets, source):
    """Convert tweets into opportunity dicts flagged for manual review."""
    opportunities = []
    for tweet in tweets:
        text = tweet.get("text", "")
        if len(text) < 20:
            continue

        opportunities.append({
            "name": text[:80].strip(),
            "organizer": tweet.get("author", f"Found via {source}"),
            "description": text,
            "eligibility": "Check source for details",
            "mode": "Check source for details",
            "fee": "Check source for details",
            "deadline": "Check source for details",
            "applicationLink": tweet.get("url", ""),
            "website": tweet.get("url", ""),
            "tags": ["twitter", "auto-discovered"],
            "status": "open",
            "source": f"twitter-{source}",
            "needsReview": True,
        })
    return opportunities
