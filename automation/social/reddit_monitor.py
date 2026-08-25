"""
OpportunityHub — Reddit Monitor
Monitors subreddits for hackathon/internship/competition announcements.
Uses Agent-Reach CLI when available, falls back to Reddit's public JSON API.
"""

import json
import logging
import re
import subprocess
import requests

from ..config import REDDIT_CONFIG

logger = logging.getLogger(__name__)

# Common URL patterns for opportunity links
OPPORTUNITY_URL_PATTERNS = [
    r'https?://(?:www\.)?devfolio\.co/\S+',
    r'https?://(?:www\.)?unstop\.com/\S+',
    r'https?://(?:www\.)?hackerearth\.com/\S+',
    r'https?://(?:www\.)?mlh\.io/\S+',
    r'https?://(?:www\.)?summerofcode\.withgoogle\.com\S*',
    r'https?://(?:www\.)?mentorship\.lfx\.linuxfoundation\.org\S*',
    r'https?://\S+(?:apply|register|signup|sign-up|careers)\S*',
]


def monitor_reddit():
    """Monitor configured subreddits for opportunity-related posts.
    
    Returns:
        list[dict]: Potential opportunities found on Reddit.
    """
    if not REDDIT_CONFIG.get("enabled", False):
        logger.info("[Reddit] Monitoring disabled in config")
        return []

    all_finds = []

    for subreddit in REDDIT_CONFIG["subreddits"]:
        posts = _fetch_subreddit_posts(subreddit)
        relevant = _filter_relevant_posts(posts)
        opportunities = _posts_to_opportunities(relevant, subreddit)
        all_finds.extend(opportunities)
        logger.info(f"[Reddit] r/{subreddit}: {len(posts)} posts → {len(relevant)} relevant → {len(opportunities)} opportunities")

    return all_finds


def _fetch_subreddit_posts(subreddit):
    """Fetch recent posts from a subreddit.
    
    Tries Agent-Reach CLI first, falls back to Reddit's public JSON API.
    """
    # Try Agent-Reach first
    posts = _try_agent_reach(subreddit)
    if posts is not None:
        return posts

    # Fallback: Reddit's public JSON API (no auth needed, rate limited)
    return _fetch_reddit_json(subreddit)


def _try_agent_reach(subreddit):
    """Try using Agent-Reach CLI to fetch Reddit posts."""
    try:
        result = subprocess.run(
            ["agent-reach", "read", "reddit", f"r/{subreddit}", "--limit", str(REDDIT_CONFIG["max_posts_per_sub"])],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            # Agent-Reach outputs text; parse it into structured posts
            logger.info(f"[Reddit] Agent-Reach succeeded for r/{subreddit}")
            return _parse_agent_reach_output(result.stdout)
    except FileNotFoundError:
        logger.debug("[Reddit] Agent-Reach not installed, using fallback")
    except subprocess.TimeoutExpired:
        logger.debug("[Reddit] Agent-Reach timed out")
    except Exception as e:
        logger.debug(f"[Reddit] Agent-Reach error: {e}")
    return None


def _parse_agent_reach_output(output):
    """Parse Agent-Reach text output into post dicts."""
    posts = []
    current_post = {}

    for line in output.split("\n"):
        line = line.strip()
        if not line:
            if current_post.get("title"):
                posts.append(current_post)
                current_post = {}
            continue

        if line.startswith("Title:"):
            current_post["title"] = line[6:].strip()
        elif line.startswith("URL:") or line.startswith("Link:"):
            current_post["url"] = line.split(":", 1)[1].strip()
        elif line.startswith("Body:") or line.startswith("Text:"):
            current_post["body"] = line.split(":", 1)[1].strip()
        else:
            # Accumulate into body
            current_post.setdefault("body", "")
            current_post["body"] += " " + line

    if current_post.get("title"):
        posts.append(current_post)

    return posts


def _fetch_reddit_json(subreddit):
    """Fetch posts using Reddit's public JSON API (no auth)."""
    url = f"https://www.reddit.com/r/{subreddit}/new.json"
    params = {"limit": REDDIT_CONFIG["max_posts_per_sub"]}
    headers = {"User-Agent": "OpportunityHub/1.0 (github.com/OpportunityHub)"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        posts = []
        for child in data.get("data", {}).get("children", []):
            post_data = child.get("data", {})
            posts.append({
                "title": post_data.get("title", ""),
                "body": post_data.get("selftext", ""),
                "url": post_data.get("url", ""),
                "permalink": f"https://reddit.com{post_data.get('permalink', '')}",
                "score": post_data.get("score", 0),
            })
        return posts

    except Exception as e:
        logger.error(f"[Reddit] Failed to fetch r/{subreddit}: {e}")
        return []


def _filter_relevant_posts(posts):
    """Filter posts that likely contain opportunity announcements."""
    keywords = REDDIT_CONFIG["keywords"]
    relevant = []

    for post in posts:
        text = f"{post.get('title', '')} {post.get('body', '')}".lower()
        if any(kw in text for kw in keywords):
            relevant.append(post)

    return relevant


def _posts_to_opportunities(posts, subreddit):
    """Convert relevant Reddit posts into opportunity dicts."""
    opportunities = []

    for post in posts:
        title = post.get("title", "").strip()
        body = post.get("body", "")
        
        # Try to extract an application link from the post
        app_link = _extract_opportunity_url(f"{body} {post.get('url', '')}")
        if not app_link:
            app_link = post.get("permalink", "")

        opportunity = {
            "name": title,
            "organizer": f"Found on r/{subreddit}",
            "description": body[:200].strip() if body else f"Opportunity posted on r/{subreddit}",
            "eligibility": "Check post for details",
            "mode": "Check post for details",
            "fee": "Check post for details",
            "deadline": "Check post for details",
            "applicationLink": app_link,
            "website": app_link,
            "tags": [f"reddit-{subreddit}", "auto-discovered"],
            "status": "open",
            "source": f"reddit-r/{subreddit}",
            "needsReview": True,  # Flag for manual review
        }
        opportunities.append(opportunity)

    return opportunities


def _extract_opportunity_url(text):
    """Extract the most likely opportunity/application URL from text."""
    for pattern in OPPORTUNITY_URL_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return ""
