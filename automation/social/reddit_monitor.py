"""
OpportunityHub — Reddit Community Monitor
Monitors subreddits (r/hackathons, r/Btechtards, r/developersIndia, r/csMajors, etc.)
Uses multi-strategy fetching:
  1. Agent-Reach CLI (if available)
  2. Public API mirrors (PullPush search API with rate limiting)
  3. Direct RSS / JSON feeds with custom headers
Extracts actionable opportunity announcements, deadlines, prize pools, and registration links.
"""

import json
import logging
import re
import subprocess
import time
import urllib.request
import ssl

from ..config import REDDIT_CONFIG

logger = logging.getLogger(__name__)

# Common URL patterns for opportunity links
OPPORTUNITY_URL_PATTERNS = [
    r'https?://(?:www\.)?devfolio\.co/\S+',
    r'https?://(?:www\.)?unstop\.com/\S+',
    r'https?://(?:www\.)?hackerearth\.com/\S+',
    r'https?://(?:www\.)?mlh\.io/\S+',
    r'https?://(?:www\.)?devpost\.com/\S+',
    r'https?://(?:www\.)?lu\.ma/\S+',
    r'https?://forms\.gle/\S+',
    r'https?://(?:www\.)?summerofcode\.withgoogle\.com\S*',
    r'https?://(?:www\.)?mentorship\.lfx\.linuxfoundation\.org\S*',
    r'https?://\S+(?:apply|register|signup|sign-up|careers|jobs|hackathon|internship)\S*',
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
    subreddits = REDDIT_CONFIG.get("subreddits", [
        "hackathons",
        "Btechtards",
        "developersIndia",
        "cscareerquestions",
        "csMajors",
        "internships",
        "Indian_Academia"
    ])

    for subreddit in subreddits:
        try:
            posts = _fetch_subreddit_posts(subreddit)
            relevant = _filter_relevant_posts(posts)
            opportunities = _posts_to_opportunities(relevant, subreddit)
            all_finds.extend(opportunities)
            logger.info(f"[Reddit] r/{subreddit}: {len(posts)} posts → {len(relevant)} relevant → {len(opportunities)} opportunities")
            time.sleep(1.0)  # Gentle rate limiting between subreddits
        except Exception as e:
            logger.warning(f"[Reddit] Error monitoring r/{subreddit}: {e}")

    return all_finds


def _fetch_subreddit_posts(subreddit):
    """Fetch recent posts from a subreddit using tiered fallback strategies."""
    # Strategy 1: Agent-Reach CLI (if installed)
    posts = _try_agent_reach(subreddit)
    if posts:
        return posts

    # Strategy 2: PullPush Mirror Search API
    posts = _try_pullpush(subreddit)
    if posts:
        return posts

    # Strategy 3: Direct curl RSS / JSON
    return _try_curl_reddit(subreddit)


def _try_agent_reach(subreddit):
    """Try using Agent-Reach CLI to fetch Reddit posts."""
    try:
        result = subprocess.run(
            ["agent-reach", "read", "reddit", f"r/{subreddit}", "--limit", str(REDDIT_CONFIG.get("max_posts_per_sub", 15))],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and result.stdout.strip():
            logger.info(f"[Reddit] Agent-Reach CLI succeeded for r/{subreddit}")
            return _parse_agent_reach_output(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"[Reddit] Agent-Reach unavailable: {e}")
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
            current_post.setdefault("body", "")
            current_post["body"] += " " + line

    if current_post.get("title"):
        posts.append(current_post)

    return posts


def _try_pullpush(subreddit):
    """Fetch recent submissions via PullPush public mirror."""
    limit = REDDIT_CONFIG.get("max_posts_per_sub", 15)
    url = f"https://api.pullpush.io/reddit/search/submission/?subreddit={subreddit}&size={limit}"
    
    headers = {
        "User-Agent": "OpportunityHub-RedditMonitor/2.0 (github.com/harir03/all-tech-inoneplace)"
    }
    ctx = ssl._create_unverified_context()

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            children = data.get("data", [])
            posts = []
            for child in children:
                posts.append({
                    "title": child.get("title", ""),
                    "body": child.get("selftext", ""),
                    "url": child.get("url", ""),
                    "permalink": f"https://reddit.com{child.get('permalink', '')}",
                    "score": child.get("score", 0),
                })
            return posts
    except Exception as e:
        logger.debug(f"[Reddit] Pullpush mirror for r/{subreddit} returned: {e}")
        return []


def _try_curl_reddit(subreddit):
    """Fallback: fetch using system curl with browser User-Agent."""
    try:
        url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=15"
        cmd = [
            "curl.exe" if subprocess.os.name == "nt" else "curl",
            "-sL", "-k",
            "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            url
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip().startswith("{"):
            data = json.loads(res.stdout)
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
        logger.debug(f"[Reddit] Curl fallback failed for r/{subreddit}: {e}")
    return []


def _filter_relevant_posts(posts):
    """Filter posts that contain opportunity announcements."""
    keywords = REDDIT_CONFIG.get("keywords", [
        "hackathon", "internship", "fellowship", "open source",
        "hiring", "apply", "stipend", "prize", "cash prize",
        "competition", "gsoc", "mlh", "devfolio", "unstop"
    ])
    relevant = []

    for post in posts:
        text = f"{post.get('title', '')} {post.get('body', '')}".lower()
        if any(kw in text for kw in keywords):
            relevant.append(post)

    return relevant


def _posts_to_opportunities(posts, subreddit):
    """Convert filtered Reddit posts into OpportunityHub opportunity dicts."""
    opportunities = []

    for post in posts:
        title = post.get("title", "").strip()
        body = post.get("body", "").strip()
        full_text = f"{title} {body}"

        # Extract external URL if available
        ext_url = _extract_opportunity_url(post)
        if not ext_url:
            ext_url = post.get("permalink", "https://reddit.com")

        # Determine category
        category = _classify_category(full_text)

        # Extract possible deadline
        deadline = _extract_deadline(full_text)

        # Extract prize or stipend if mentioned
        prize_or_stipend = _extract_rewards(full_text)

        # Create structured opportunity
        post_slug = re.sub(r'[^a-zA-Z0-9]', '', title[:20]).lower()
        opp = {
            "id": f"reddit-{subreddit}-{post_slug}",
            "name": title[:90],
            "organizer": f"r/{subreddit} Community",
            "description": (body[:250] + "...") if len(body) > 250 else (body or title),
            "eligibility": "Open to all (check post)",
            "deadline": deadline or "Check community post",
            "mode": "Online / Hybrid",
            "status": "open",
            "applicationLink": ext_url,
            "website": post.get("permalink", ext_url),
            "source": f"reddit:r/{subreddit}",
            "tags": ["reddit", "community", subreddit, category],
        }

        if category == "hackathons":
            opp["prize"] = prize_or_stipend or "Community Hackathon"
            opp["teamSize"] = "1-4"
        elif category == "internships":
            opp["stipend"] = prize_or_stipend or "Competitive / Check listing"
            opp["location"] = "India / Remote / Global"
        elif category == "competitions":
            opp["prize"] = prize_or_stipend or "Prizes & Recognition"
        elif category == "open-source-programs":
            opp["stipend"] = prize_or_stipend or "Stipend / Mentorship"
            opp["duration"] = "10-12 weeks"

        opportunities.append(opp)

    return opportunities


def _extract_opportunity_url(post):
    """Extract an external registration link from post URL or body."""
    # Check post's primary URL first
    post_url = post.get("url", "")
    if post_url and not ("reddit.com" in post_url or "redd.it" in post_url):
        return post_url

    # Search in post body
    body = post.get("body", "")
    for pattern in OPPORTUNITY_URL_PATTERNS:
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            return match.group(0).rstrip(").,;")

    return None


def _classify_category(text):
    """Classify post into one of OpportunityHub's 5 categories."""
    text_lower = text.lower()
    if any(k in text_lower for k in ["hackathon", "hack ", "hacks", "buildathon", "devpost", "devfolio"]):
        return "hackathons"
    elif any(k in text_lower for k in ["internship", "intern", "hiring", "job", "summer 202", "swe intern"]):
        return "internships"
    elif any(k in text_lower for k in ["gsoc", "lfx", "open source", "outreachy", "github accelerator"]):
        return "open-source-programs"
    elif any(k in text_lower for k in ["fellowship", "grant", "scholarship"]):
        return "fellowships"
    else:
        return "competitions"


def _extract_deadline(text):
    """Extract date strings that look like deadlines."""
    patterns = [
        r'deadline[:\s]+([A-Za-z]+ \d{1,2}(?:st|nd|rd|th)?,? \d{4})',
        r'deadline[:\s]+(\d{4}-\d{2}-\d{2})',
        r'apply by[:\s]+([A-Za-z]+ \d{1,2}(?:st|nd|rd|th)?,? \d{4})',
        r'last date[:\s]+([A-Za-z]+ \d{1,2}(?:st|nd|rd|th)?,? \d{4})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_rewards(text):
    """Extract mention of prize pool or stipend amount."""
    patterns = [
        r'(?:prize|prizes|prize pool)[:\s]+([\$\₹\€\£\w\s,\.\d]+?)(?:\.|\n|$)',
        r'(?:stipend)[:\s]+([\$\₹\€\£\w\s,\.\d]+?)(?:\.|\n|$)',
        r'(\$[\d,]+(?:\s*(?:k|usd|cash))?)',
        r'(₹[\d,]+(?:\s*(?:lakh|k|inr))?)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = match.group(1).strip()
            if len(val) < 40:
                return val
    return None
