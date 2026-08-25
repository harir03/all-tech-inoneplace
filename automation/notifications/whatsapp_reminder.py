"""
OpportunityHub — WhatsApp Reminder (Experimental)
Sends deadline reminders via WhatsApp using PyWhatKit.

⚠️ WARNING: This automates WhatsApp Web which violates WhatsApp's TOS.
Your phone number may get permanently banned. Use at your own risk.
This only works on a local machine with WhatsApp Web logged in — not in CI/GitHub Actions.
"""

import logging
from datetime import date
from dateutil.parser import parse as parse_date

from ..config import WHATSAPP_CONFIG, REMINDER_DAYS_BEFORE
from ..utils import load_json

logger = logging.getLogger(__name__)

SUBSCRIBERS_FILE = "data/subscribers.json"


def send_whatsapp_reminders(all_data):
    """Send WhatsApp deadline reminders to subscribers who opted in.
    
    ⚠️ Experimental — requires WhatsApp Web logged in on this machine.
    
    Args:
        all_data: dict of {category: [opportunities]}
    """
    if not WHATSAPP_CONFIG.get("enabled", False):
        logger.info("[WhatsApp] Reminders disabled in config (experimental feature)")
        return

    try:
        import pywhatkit
    except ImportError:
        logger.error("[WhatsApp] pywhatkit not installed. pip install pywhatkit")
        return

    subscribers = load_json(SUBSCRIBERS_FILE)
    whatsapp_subs = [s for s in subscribers if s.get("whatsapp")]

    if not whatsapp_subs:
        logger.info("[WhatsApp] No WhatsApp subscribers found")
        return

    today = date.today()
    upcoming = _find_upcoming_deadlines(all_data, today)

    if not upcoming:
        logger.info("[WhatsApp] No upcoming deadlines")
        return

    for subscriber in whatsapp_subs:
        phone = subscriber.get("whatsapp", "").strip()
        categories = subscriber.get("categories", [])
        if not phone:
            continue

        # Ensure phone has country code
        if not phone.startswith("+"):
            phone = f"+91{phone}"  # Default to India

        relevant = [opp for opp in upcoming if opp.get("_category") in categories]
        if not relevant:
            continue

        message = _format_whatsapp_message(relevant)
        _send_whatsapp(pywhatkit, phone, message)


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


def _format_whatsapp_message(opportunities):
    """Format a WhatsApp-friendly reminder message."""
    lines = [
        "🚀 *OpportunityHub Reminder*",
        "",
        f"⏰ {len(opportunities)} deadline(s) approaching!",
        "",
    ]

    for opp in opportunities:
        days = opp.get("_days_until", "?")
        lines.append(f"📌 *{opp['name']}*")
        lines.append(f"   Deadline: {opp.get('deadline', 'N/A')} ({days} day(s) left)")
        lines.append(f"   Apply: {opp.get('applicationLink', 'N/A')}")
        lines.append("")

    lines.append("Good luck! 💪")
    return "\n".join(lines)


def _send_whatsapp(pywhatkit, phone, message):
    """Send a WhatsApp message using PyWhatKit."""
    try:
        # sendwhatmsg_instantly sends without scheduling
        pywhatkit.sendwhatmsg_instantly(phone, message, wait_time=15, tab_close=True)
        logger.info(f"[WhatsApp] Sent reminder to {phone}")
    except Exception as e:
        logger.error(f"[WhatsApp] Failed to send to {phone}: {e}")
