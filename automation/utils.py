"""
OpportunityHub — Utility functions
Deduplication, date parsing, JSON merge, and common helpers.
"""

import json
import os
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
    return name.lower().strip().replace("  ", " ")


def is_duplicate(new_item, existing_items):
    """Check if a new item is a duplicate of any existing item.
    
    Matches on normalized name OR application link.
    """
    new_name = normalize_name(new_item.get("name", ""))
    new_link = new_item.get("applicationLink", "").strip().rstrip("/")

    for item in existing_items:
        existing_name = normalize_name(item.get("name", ""))
        existing_link = item.get("applicationLink", "").strip().rstrip("/")

        if new_name and new_name == existing_name:
            return True
        if new_link and existing_link and new_link == existing_link:
            return True

    return False


def merge_opportunities(existing, new_items):
    """Merge new items into existing list, skipping duplicates.
    
    Returns: (merged_list, newly_added_items)
    """
    added = []
    for item in new_items:
        if not is_duplicate(item, existing):
            existing.append(item)
            added.append(item)
    return existing, added


def update_expired_statuses(items):
    """Mark opportunities as 'closed' if their deadline has passed."""
    today = date.today()
    updated_count = 0

    for item in items:
        if item.get("status") == "closed":
            continue

        deadline_str = item.get("deadline", "")
        if not deadline_str:
            continue

        # Skip non-date deadlines like "Rolling", "Various", etc.
        skip_keywords = ["rolling", "various", "check", "tbd", "tba"]
        if any(kw in deadline_str.lower() for kw in skip_keywords):
            continue

        try:
            deadline_date = parse_date(deadline_str).date()
            if deadline_date < today:
                item["status"] = "closed"
                updated_count += 1
        except (ValueError, TypeError):
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
