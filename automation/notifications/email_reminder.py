"""
OpportunityHub — Email Reminder
Sends deadline reminder emails to subscribers.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, timedelta
from dateutil.parser import parse as parse_date

from ..config import EMAIL_CONFIG, REMINDER_DAYS_BEFORE
from ..utils import load_json

logger = logging.getLogger(__name__)

SUBSCRIBERS_FILE = "data/subscribers.json"


def send_deadline_reminders(all_data):
    """Check for upcoming deadlines and send email reminders.
    
    Args:
        all_data: dict of {category: [opportunities]}
    """
    if not EMAIL_CONFIG.get("enabled", False):
        logger.info("[Email] Reminders disabled in config")
        return

    if not EMAIL_CONFIG.get("sender_email") or not EMAIL_CONFIG.get("sender_password"):
        logger.warning("[Email] SMTP credentials not configured")
        return

    subscribers = load_json(SUBSCRIBERS_FILE)
    if not subscribers:
        logger.info("[Email] No subscribers found")
        return

    today = date.today()
    upcoming = _find_upcoming_deadlines(all_data, today)

    if not upcoming:
        logger.info("[Email] No upcoming deadlines to notify about")
        return

    logger.info(f"[Email] Found {len(upcoming)} upcoming deadlines, {len(subscribers)} subscribers")

    for subscriber in subscribers:
        email = subscriber.get("email")
        categories = subscriber.get("categories", [])
        if not email:
            continue

        # Filter to subscriber's chosen categories
        relevant = [opp for opp in upcoming if opp.get("_category") in categories]
        if not relevant:
            continue

        _send_reminder_email(email, relevant)


def _find_upcoming_deadlines(all_data, today):
    """Find opportunities with deadlines within REMINDER_DAYS_BEFORE."""
    upcoming = []
    skip_keywords = ["rolling", "various", "check", "tbd", "tba"]

    for category, items in all_data.items():
        for item in items:
            if item.get("status") == "closed":
                continue

            deadline_str = item.get("deadline", "")
            if not deadline_str or any(kw in deadline_str.lower() for kw in skip_keywords):
                continue

            try:
                deadline_date = parse_date(deadline_str).date()
                days_until = (deadline_date - today).days

                if days_until in REMINDER_DAYS_BEFORE:
                    item_copy = dict(item)
                    item_copy["_category"] = category
                    item_copy["_days_until"] = days_until
                    upcoming.append(item_copy)
            except (ValueError, TypeError):
                continue

    return upcoming


def _send_reminder_email(recipient, opportunities):
    """Send a deadline reminder email."""
    subject = f"🔔 OpportunityHub: {len(opportunities)} deadline(s) approaching!"

    body_lines = [
        "Hi there! 👋",
        "",
        "Here are upcoming deadlines you don't want to miss:",
        "",
    ]

    for opp in opportunities:
        days = opp.get("_days_until", "?")
        body_lines.append(f"⏰ {opp['name']}")
        body_lines.append(f"   Deadline: {opp.get('deadline', 'N/A')} ({days} day(s) left)")
        body_lines.append(f"   Apply: {opp.get('applicationLink', 'N/A')}")
        body_lines.append("")

    body_lines.extend([
        "---",
        "Good luck! 🚀",
        "— OpportunityHub (github.com/OpportunityHub)",
        "",
        "Unsubscribe by removing your entry from data/subscribers.json",
    ])

    body = "\n".join(body_lines)

    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_CONFIG["sender_email"]
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"]) as server:
            server.starttls()
            server.login(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_password"])
            server.sendmail(EMAIL_CONFIG["sender_email"], recipient, msg.as_string())

        logger.info(f"[Email] Sent reminder to {recipient}")
    except Exception as e:
        logger.error(f"[Email] Failed to send to {recipient}: {e}")
