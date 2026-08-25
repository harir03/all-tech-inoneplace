"""
OpportunityHub — Main Pipeline Orchestrator
Runs ALL registered scrapers + social monitors, deduplicates, updates JSON,
sends email notifications, and auto-commits via GitHub Actions.

How it works (this IS the backend):
1. GitHub Actions triggers this script on a cron schedule (daily)
2. The scraper registry loads all scrapers (Devfolio, Unstop, MLH, 
   Devpost, HackerEarth, Internshala, Codeforces, LeetCode, GSoC, etc.)
3. Each scraper runs independently — if one fails, others continue
4. Social monitors check Reddit for new opportunity posts
5. All results are deduplicated against existing data/*.json files
6. New opportunities are appended, expired ones are marked closed
7. GitHub Actions commits the updated JSON files back to the repo
8. The website auto-reflects new data (it reads from data/*.json)

Usage:
    python -m automation.pipeline              # Dry run (no file changes)
    DRY_RUN=false python -m automation.pipeline # Live run (updates files)

When run via GitHub Actions, DRY_RUN is set to false automatically.
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime

from .config import DATA_FILES, AUTO_COMMIT, DRY_RUN, PROJECT_ROOT
from .utils import load_json, save_json, merge_opportunities, update_expired_statuses
from .scrapers.registry import get_all_scrapers
from .social.social_aggregator import aggregate_social_findings
from .notifications.email_reminder import send_deadline_reminders
from .readme_generator import update_readme

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_scrapers():
    """Run all registered scrapers with error isolation.
    
    Each scraper runs independently. If one crashes, the rest continue.
    
    Returns:
        dict: {category: [scraped_opportunities]}
        dict: {scraper_name: status} for reporting
    """
    results = {}
    report = {}

    scrapers = get_all_scrapers()

    for scraper in scrapers:
        scraper_name = scraper.name
        start = time.time()
        try:
            scraped = scraper.run()
            elapsed = round(time.time() - start, 1)

            # GitHubRepoScraper returns dict {category: [items]}
            # Regular scrapers return list [items]
            if isinstance(scraped, dict):
                total = 0
                for cat, items in scraped.items():
                    results.setdefault(cat, []).extend(items)
                    total += len(items)
                report[scraper_name] = {
                    "status": "✅",
                    "count": total,
                    "time": f"{elapsed}s",
                    "category": "multi",
                }
                logger.info(f"  ✅ {scraper_name}: {total} items across {len(scraped)} categories ({elapsed}s)")
            else:
                category = scraper.category
                results.setdefault(category, []).extend(scraped)
                report[scraper_name] = {
                    "status": "✅",
                    "count": len(scraped),
                    "time": f"{elapsed}s",
                    "category": category,
                }
                logger.info(f"  ✅ {scraper_name}: {len(scraped)} items ({elapsed}s)")
        except Exception as e:
            elapsed = round(time.time() - start, 1)
            report[scraper_name] = {
                "status": "❌",
                "count": 0,
                "time": f"{elapsed}s",
                "error": str(e),
            }
            logger.error(f"  ❌ {scraper_name}: FAILED — {e}")

    return results, report


def run_social_monitors():
    """Run social media monitors with error isolation.
    
    Returns:
        dict: {category: [social_findings]}
    """
    try:
        return aggregate_social_findings()
    except Exception as e:
        logger.error(f"Social monitors failed: {e}")
        return {}


def update_data_files(scraped, social):
    """Merge scraped and social data into existing JSON files.
    
    Returns:
        dict: Summary of changes per category
    """
    summary = {}

    for category, filepath in DATA_FILES.items():
        existing = load_json(filepath)
        new_items = []

        new_items.extend(scraped.get(category, []))
        new_items.extend(social.get(category, []))

        # Deduplicate and merge
        merged, added = merge_opportunities(existing, new_items)

        # Update expired statuses
        expired_count = update_expired_statuses(merged)

        if added or expired_count > 0:
            if not DRY_RUN:
                save_json(filepath, merged)
                logger.info(f"  [{category}] Saved: +{len(added)} new, {expired_count} expired → {len(merged)} total")
            else:
                logger.info(f"  [{category}] DRY RUN: would add {len(added)}, expire {expired_count}")
        else:
            logger.info(f"  [{category}] No changes ({len(merged)} total)")

        summary[category] = {
            "total": len(merged),
            "added": len(added),
            "expired": expired_count,
            "added_items": [item.get("name") for item in added],
        }

    # Re-generate README.md tables dynamically
    if not DRY_RUN:
        all_current_data = {cat: load_json(fp) for cat, fp in DATA_FILES.items()}
        try:
            update_readme(all_current_data, PROJECT_ROOT)
        except Exception as e:
            logger.error(f"[README] Failed to regenerate README: {e}")

    return summary


def send_notifications():
    """Send deadline reminder notifications via email."""
    data = {}
    for category, filepath in DATA_FILES.items():
        data[category] = load_json(filepath)
    send_deadline_reminders(data)


def auto_commit_changes():
    """Auto-commit and push updated data files & README to git."""
    if not AUTO_COMMIT:
        logger.info("[Git] Auto-commit disabled (handled by GitHub Actions step)")
        return

    try:
        os.chdir(PROJECT_ROOT)
        result = subprocess.run(
            ["git", "diff", "--name-only", "data/", "README.md"],
            capture_output=True, text=True
        )
        if not result.stdout.strip():
            logger.info("[Git] No changes to commit")
            return

        subprocess.run(["git", "add", "data/", "README.md"], check=True)
        subprocess.run(
            ["git", "commit", "-m", f"🤖 Auto-update: {datetime.now().strftime('%Y-%m-%d %H:%M')} — live scrape & dynamic README sync"],
            check=True
        )
        subprocess.run(["git", "push"], check=True)
        logger.info("[Git] Changes committed and pushed to GitHub")
    except subprocess.CalledProcessError as e:
        logger.error(f"[Git] Failed: {e}")
    except Exception as e:
        logger.error(f"[Git] Error: {e}")


def generate_run_report(scraper_report, social_count, summary, total_time):
    """Generate a human-readable report of the pipeline run."""
    lines = [
        "",
        "=" * 70,
        f"  OPPORTUNITYHUB PIPELINE REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        "",
        "📡 SCRAPER RESULTS:",
        f"  {'Scraper':<25} {'Status':<5} {'Found':<8} {'Time':<8} {'Category'}",
        f"  {'─'*25} {'─'*5} {'─'*8} {'─'*8} {'─'*15}",
    ]

    for name, info in scraper_report.items():
        lines.append(
            f"  {name:<25} {info['status']:<5} {info['count']:<8} {info['time']:<8} {info.get('category', 'N/A')}"
        )

    total_scraped = sum(info["count"] for info in scraper_report.values())
    lines.extend([
        f"  {'─'*60}",
        f"  Total scraped: {total_scraped} items from {len(scraper_report)} sources",
        "",
        f"📱 SOCIAL MONITOR: {social_count} items from Reddit/Twitter",
        "",
        "💾 DATA FILE UPDATES:",
    ])

    total_added = 0
    total_expired = 0
    for category, stats in summary.items():
        total_added += stats["added"]
        total_expired += stats["expired"]
        marker = f"+{stats['added']}" if stats["added"] else "—"
        lines.append(f"  {category:<25} {stats['total']:>4} total  {marker:>4} new  {stats['expired']:>3} expired")
        for name in stats.get("added_items", []):
            lines.append(f"    ✨ {name}")

    lines.extend([
        "",
        f"  📊 Net: +{total_added} new opportunities, {total_expired} expired",
        f"  ⏱️  Pipeline completed in {total_time:.1f}s",
        "=" * 70,
    ])

    return "\n".join(lines)


def main():
    """Main pipeline entry point."""
    pipeline_start = time.time()

    logger.info("=" * 70)
    logger.info("  OPPORTUNITYHUB PIPELINE — Starting")
    logger.info(f"  Mode: {'DRY RUN (no file changes)' if DRY_RUN else 'LIVE (will update files)'}")
    logger.info(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)

    # Step 1: Scrape ALL websites
    logger.info("\n📡 Step 1/4: Running website scrapers...")
    scraped, scraper_report = run_scrapers()
    total_scraped = sum(len(v) for v in scraped.values())
    logger.info(f"   → {total_scraped} total items from {len(scraper_report)} scrapers")

    # Step 2: Monitor social media
    logger.info("\n📱 Step 2/4: Running social media monitors...")
    social = run_social_monitors()
    total_social = sum(len(v) for v in social.values())
    logger.info(f"   → {total_social} total items from social feeds")

    # Step 3: Merge and deduplicate
    logger.info("\n💾 Step 3/4: Merging and deduplicating data...")
    summary = update_data_files(scraped, social)

    # Step 4: Send notifications
    logger.info("\n🔔 Step 4/4: Checking for deadline reminders...")
    send_notifications()

    # Auto-commit (if not handled by GitHub Actions)
    if not DRY_RUN:
        auto_commit_changes()

    # Final report
    total_time = time.time() - pipeline_start
    report = generate_run_report(scraper_report, total_social, summary, total_time)
    logger.info(report)

    # Save report to file for GitHub Actions artifact
    report_path = os.path.join(PROJECT_ROOT, "automation", "last_run_report.txt")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
    except Exception:
        pass


if __name__ == "__main__":
    main()
