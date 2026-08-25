"""
OpportunityHub — Utility functions
Deduplication, robust date parsing, JSON merge, and auto-expiry engine.
"""

import json
import os
import re
from datetime import datetime, date
from dateutil.parser import parse as parse_date


def load_json(filepath):
    """Load a JSON file, return empty list if missing or invalid."""
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_json(filepath, data):
    """Save data to a JSON file with pretty printing."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def normalize_name(name):
    """Normalize an opportunity name for deduplication comparison."""
    if not name:
        return ""
    # Strip emojis and extra whitespace
    clean = re.sub(r'[^\w\s-]', '', name).lower().strip()
    return re.sub(r'\s+', ' ', clean)


def is_duplicate(new_item, existing_items):
    """Check if a new item is a duplicate of any existing item."""
    new_name = normalize_name(new_item.get("name", ""))
    new_link = new_item.get("applicationLink", "").strip().rstrip("/")

    for item in existing_items:
        existing_name = normalize_name(item.get("name", ""))
        existing_link = item.get("applicationLink", "").strip().rstrip("/")

        if new_name and len(new_name) > 4 and new_name == existing_name:
            return True
        if new_link and len(new_link) > 10 and existing_link and new_link == existing_link:
            return True

    return False


def merge_opportunities(existing, new_items):
    """Merge new items into existing list, updating open listings and skipping duplicates."""
    added = []
    for item in new_items:
        if not is_duplicate(item, existing):
            existing.append(item)
            added.append(item)
    return existing, added


def is_date_in_past(date_str, today=None):
    """Check if a date string, date range, or year indicates an ended event."""
    if not date_str:
        return False

    if today is None:
        today = date.today()

    s = date_str.lower().strip()

    # Never expire rolling/annual keywords
    if any(k in s for k in ["rolling", "annual", "various", "check", "tbd", "tba", "asap"]):
        return False

    # Check for past years explicitly (e.g. 2023, 2024, 2025 if current year is 2026)
    years = [int(y) for y in re.findall(r'\b(202[0-9])\b', s)]
    if years:
        latest_year = max(years)
        if latest_year < today.year:
            return True

    # Check for keywords indicating closed status
    if any(k in s for k in ["ended", "closed", "past", "concluded"]):
        return True

    # Split range like 'Jan 27–Feb 13, 2025' or 'AUG 28 - 30'
    parts = re.split(r'[-–—]', date_str)
    end_part = parts[-1].strip()

    try:
        dt = parse_date(end_part, fuzzy=True)
        # If year was inferred and is in past, or explicitly past
        if dt.year < today.year:
            return True
        if dt.date() < today:
            return True
    except Exception:
        pass

    return False


def update_expired_statuses(items):
    """Mark opportunities as 'closed' if their deadline or event date has passed."""
    today = date.today()
    updated_count = 0

    for item in items:
        if item.get("status") == "closed":
            continue

        deadline_str = item.get("deadline", "")
        event_date_str = item.get("eventDate", "")
        desc_str = item.get("description", "")

        # Check deadline
        if is_date_in_past(deadline_str, today):
            item["status"] = "closed"
            updated_count += 1
            continue

        # Check event date
        if is_date_in_past(event_date_str, today):
            item["status"] = "closed"
            updated_count += 1
            continue

        # Check description
        if any(k in desc_str.lower() for k in ["applications closed", "hackathon ended", "event ended"]):
            item["status"] = "closed"
            updated_count += 1
            continue

    return updated_count


def format_opportunity_summary(items):
    """Create a brief summary of opportunities for notifications."""
    lines = []
    for item in items:
        status_emoji = {"open": "🟢", "closed": "🔴", "coming-soon": "🟡"}.get(
            item.get("status", ""), "⚪"
        )
        deadline = item.get("deadline", "N/A")
        lines.append(f"{status_emoji} {item['name']} — Deadline: {deadline}")
    return "\n".join(lines)
