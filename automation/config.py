"""
OpportunityHub — Configuration
Central config for scraping targets, social monitors, and notification settings.
"""

import os


def _flag(name: str, default: bool) -> bool:
    """Read a boolean env var. Defined early because config reads flags below."""
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# ===== Paths =====
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

DATA_FILES = {
    "hackathons": os.path.join(DATA_DIR, "hackathons.json"),
    "internships": os.path.join(DATA_DIR, "internships.json"),
    "jobs": os.path.join(DATA_DIR, "jobs.json"),
    "competitions": os.path.join(DATA_DIR, "competitions.json"),
    "open-source-programs": os.path.join(DATA_DIR, "open-source-programs.json"),
    "fellowships": os.path.join(DATA_DIR, "fellowships.json"),
}

# Verification state files.
#
# These live inside data/ on purpose. GitHub Actions checks out a fresh copy of
# the repo on every run, so the only way verification memory survives between
# runs is for it to be committed — and the workflow already does `git add data/`.
# The leading underscore keeps them out of the website, which loads an explicit
# whitelist of category files (see website/js/app.js), not a directory glob.
LEDGER_FILE = os.path.join(DATA_DIR, "_verification_ledger.json")
QUARANTINE_FILE = os.path.join(DATA_DIR, "_quarantine.json")

# ===== Scraping Targets =====
SCRAPE_TARGETS = {
    "devfolio": {
        "url": "https://devfolio.co/hackathons",
        "category": "hackathons",
        "enabled": True,
    },
    "unstop_hackathons": {
        "url": "https://unstop.com/hackathons",
        "category": "hackathons",
        "enabled": True,
    },
    "unstop_competitions": {
        "url": "https://unstop.com/competitions",
        "category": "competitions",
        "enabled": True,
    },
    "mlh": {
        "url": "https://mlh.io/seasons/2026/events",
        "category": "hackathons",
        "enabled": True,
    },
}

# ===== Social Media Monitoring =====
REDDIT_CONFIG = {
    "subreddits": [
        "hackathons",
        "developersIndia",
        "cscareerquestions",
        "Indian_Academia",
        "Btechtards",
        "csMajors",
        "newgrad",
        "remotework",
        "webdev",
        "learnprogramming",
    ],
    "keywords": [
        "hackathon", "internship", "fellowship", "open source program",
        "registration open", "application deadline", "apply now",
        "stipend", "coding competition", "gsoc", "mlh",
        "prize pool", "cash prize", "hiring", "new grad",
        "buildathon", "bounty", "challenge", "designathon",
    ],
    "max_posts_per_sub": 25,
    "enabled": True,
}

TWITTER_CONFIG = {
    "accounts": [
        # Add relevant Twitter/X accounts to monitor
        # e.g., "devaborad", "mlaborad", "unstaborad"
    ],
    "hashtags": [
        "#hackathon", "#internship2026", "#codingcompetition",
        "#opensourceprogram", "#fellowship",
    ],
    "enabled": False,  # Disabled by default — requires auth cookies
}

# ===== Notifications =====
REMINDER_DAYS_BEFORE = [7, 3, 1]  # Send reminders this many days before deadline

EMAIL_CONFIG = {
    "enabled": False,  # Enable when SMTP is configured
    "smtp_server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
    "smtp_port": int(os.getenv("SMTP_PORT", "587")),
    "sender_email": os.getenv("SENDER_EMAIL", ""),
    "sender_password": os.getenv("SENDER_PASSWORD", ""),  # Gmail App Password
}

# ═══════════════════════════════════════════════════════════════════════════
# Geographic policy (automation/location.py)
#
# This board serves Indian students, but the upstream SimplifyJobs repos are
# US-centric: 1,231 of 1,499 internship records were US-based and only 4 were
# Indian. Every record is now classified into a location mode and country, and
# anything requiring physical presence outside the home country is filtered out
# at ingestion.
#
# Rules per mode:
#   "any"  → keep regardless of country (globally remote work)
#   "home" → keep only when in LOCATION_HOME_COUNTRY, or country unknown
#   "keep" → always keep
#   "drop" → always drop
#
# `unknown` defaults to "keep" on purpose. Dropping records we merely failed to
# parse would convert a gazetteer gap into invisible data loss.
# ═══════════════════════════════════════════════════════════════════════════

LOCATION_FILTER_ENABLED = _flag("LOCATION_FILTER_ENABLED", True)
LOCATION_HOME_COUNTRY = os.getenv("LOCATION_HOME_COUNTRY", "IN")

LOCATION_POLICY = {
    "remote": "any",        # Work from anywhere — useful to an Indian student
    "remote_geo": "home",   # "Remote (US)" still requires US authorization
    "hybrid": "home",       # Splits time with an office, so presence is required
    "onsite": "home",       # Full physical presence
    "unknown": "keep",
}

# Categories the geographic filter applies to. Hackathons, competitions,
# fellowships and OSS programs are overwhelmingly online/global already, and
# filtering them adds risk without benefit.
LOCATION_FILTERED_CATEGORIES = tuple(
    (os.getenv("LOCATION_FILTERED_CATEGORIES") or "internships,jobs").split(",")
)


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline
# ═══════════════════════════════════════════════════════════════════════════
AUTO_COMMIT = os.getenv("AUTO_COMMIT", "false").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"


# ═══════════════════════════════════════════════════════════════════════════
# Verification stack
#
#   Layer 1  (verification.py)  — per-item plausibility heuristics
#   Layer 2  (adjudication.py)  — claim-vs-evidence reconciliation
#   Ledger   (ledger.py)        — persistent decisions + quarantine retry queue
#   Gate     (commit_gate.py)   — dataset-wide invariants, last stop before write
# ═══════════════════════════════════════════════════════════════════════════

# Master switch for Layer 2. Turning this off reverts to Layer 1 only.
LAYER2_ENABLED = _flag("LAYER2_ENABLED", True)

# Seconds of network I/O Layer 2 may spend gathering evidence per run.
# The CI job has a 10 minute cap, so this stays well inside it.
EVIDENCE_TIME_BUDGET = float(os.getenv("EVIDENCE_TIME_BUDGET", "240"))

# Hours an accepted item is trusted before its evidence is re-probed.
RECHECK_TTL_HOURS = int(os.getenv("RECHECK_TTL_HOURS", "72"))

# Skip network work on items already permanently disproven.
SUPPRESS_RETIRED = _flag("SUPPRESS_RETIRED", True)

# Hold unproven items for retry instead of discarding them.
QUARANTINE_ENABLED = _flag("QUARANTINE_ENABLED", True)

# Dataset-level invariant checks before any file is written.
COMMIT_GATE_ENABLED = _flag("COMMIT_GATE_ENABLED", True)

# Exit non-zero when the gate blocks a write, so CI surfaces it loudly
# instead of silently publishing nothing.
FAIL_RUN_ON_GATE_BLOCK = _flag("FAIL_RUN_ON_GATE_BLOCK", True)


# ═══════════════════════════════════════════════════════════════════════════
# Agent Reach integration — https://github.com/Panniantong/Agent-Reach
#
# Agent Reach is a capability layer, not a dataset: it selects, installs and
# health-checks the best available backend per platform, and explicitly does not
# proxy the reads itself. We therefore adopt its routing model and its chosen
# backends rather than calling it as a service.
#
# The backend that matters most here is its `web` choice, Jina Reader
# (https://r.jina.ai/<url>) — free, keyless, renders server-side, and needs
# nothing installed, so it works unchanged inside GitHub Actions. It gives us:
#   * a second acquisition path for listing pages and RSS feeds, and
#   * an evidence fallback for pages that refuse direct access, where Jina's
#     HTML mode still returns JSON-LD and OpenGraph metadata intact.
# ═══════════════════════════════════════════════════════════════════════════

REACH_ENABLED = _flag("REACH_ENABLED", True)

# Use Jina Reader as the primary `web` backend (Agent Reach's own choice).
REACH_USE_JINA = _flag("REACH_USE_JINA", True)

# Optional — only raises the rate limit; the keyless tier works fine.
JINA_API_KEY = os.getenv("JINA_API_KEY", "")

# Hard caps so a slow backend can never threaten the CI timeout.
REACH_MAX_READS = int(os.getenv("REACH_MAX_READS", "60"))
REACH_TIME_BUDGET = float(os.getenv("REACH_TIME_BUDGET", "180"))

# Let Layer 2 retry blocked pages through the Reach web channel.
REACH_EVIDENCE_FALLBACK = _flag("REACH_EVIDENCE_FALLBACK", True)

# Feeds read through the Reach `rss` channel. Feeds beat scraping: they are
# publisher-authored, already structured, and survive site redesigns.
#
# Two kinds, and the distinction matters:
#   filter=None       — a dedicated opportunity feed; every entry is an item.
#   filter="keywords" — a general news/blog feed that occasionally announces an
#                       opportunity. Entries must match an opportunity keyword or
#                       they are discarded, and the source is tagged `reach:news:`
#                       (trust 0.45) rather than `reach:rss:` (trust 0.80).
#
# Verified reachable at time of writing. Devpost's RSS/Atom endpoints now return
# 403/406 and its JSON API is already covered by devpost_scraper.py, so it is
# intentionally absent here rather than left in as a silently-broken entry.
REACH_FEEDS = [
    {
        "url": "https://blog.google/technology/developers/rss/",
        "category": "hackathons",
        "source": "reach:news:google-developers",
        "filter": "keywords",
        "limit": 30,
        "enabled": True,
    },
    {
        "url": "https://developers.googleblog.com/feeds/posts/default",
        "category": "hackathons",
        "source": "reach:news:google-devblog",
        "filter": "keywords",
        "limit": 30,
        "enabled": True,
    },
    {
        "url": "https://github.blog/feed/",
        "category": "open-source-programs",
        "source": "reach:news:github-blog",
        "filter": "keywords",
        "limit": 20,
        "enabled": True,
    },
]

# Listing pages read as clean text through the Reach `web` channel. These are
# deliberately tagged low-trust: Layer 2 quarantines anything derived from them
# until an independent source corroborates it.
REACH_WEB_TARGETS = [
    {
        "url": "https://unstop.com/hackathons",
        "category": "hackathons",
        "source": "reach:web:unstop",
        "enabled": False,
    },
    {
        "url": "https://devfolio.co/hackathons",
        "category": "hackathons",
        "source": "reach:web:devfolio",
        "enabled": False,
    },
]

# Optional semantic discovery via Exa (needs mcporter installed locally).
# Off by default because it is unavailable in CI and produces unproven leads.
REACH_SEARCH_ENABLED = _flag("REACH_SEARCH_ENABLED", False)
REACH_SEARCH_QUERIES = [
    "student hackathon 2026 registration open India",
    "paid software engineering internship 2026 applications open",
]
