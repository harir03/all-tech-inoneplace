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


def merge_opportunities(existing, new_items):
    """Merge new items into existing list with O(1) hash set deduplication."""
    existing_names = {normalize_name(it.get("name", "")) for it in existing if it.get("name")}
    existing_links = {it.get("applicationLink", "").strip().rstrip("/") for it in existing if it.get("applicationLink")}

    added = []
    for item in new_items:
        name = normalize_name(item.get("name", ""))
        link = item.get("applicationLink", "").strip().rstrip("/")

        # Check duplicate
        if name and len(name) > 4 and name in existing_names:
            continue
        if link and len(link) > 10 and link in existing_links:
            continue

        existing.append(item)
        added.append(item)
        if name:
            existing_names.add(name)
        if link:
            existing_links.add(link)

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

    # If it's a standard YYYY-MM-DD format, parse directly without splitting
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str.strip()):
        try:
            dt = parse_date(date_str.strip()).date()
            return dt < today
        except Exception:
            return False

    # Split ranges: ' - ', '–', '—', ' to ' (do NOT split single hyphens inside dates)
    parts = re.split(r'\s+[-–—]\s+|\s+to\s+|[–—]', date_str)
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
