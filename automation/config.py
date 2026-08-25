"""
OpportunityHub — Configuration
Central config for scraping targets, social monitors, and notification settings.
"""

import os

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
    ],
    "keywords": [
        "hackathon", "internship", "fellowship", "open source program",
        "registration open", "application deadline", "apply now",
        "stipend", "coding competition", "gsoc", "mlh",
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

# ===== Pipeline =====
AUTO_COMMIT = os.getenv("AUTO_COMMIT", "false").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
