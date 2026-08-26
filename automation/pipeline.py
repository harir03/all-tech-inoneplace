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

from .config import (
    DATA_FILES, AUTO_COMMIT, DRY_RUN, PROJECT_ROOT,
    LEDGER_FILE, QUARANTINE_FILE,
    LAYER2_ENABLED, EVIDENCE_TIME_BUDGET, RECHECK_TTL_HOURS,
    SUPPRESS_RETIRED, QUARANTINE_ENABLED,
    COMMIT_GATE_ENABLED, FAIL_RUN_ON_GATE_BLOCK,
    REACH_ENABLED, REACH_USE_JINA, JINA_API_KEY,
    REACH_MAX_READS, REACH_TIME_BUDGET, REACH_EVIDENCE_FALLBACK,
)
from .utils import load_json, save_json, merge_opportunities, update_expired_statuses
from .scrapers.registry import get_all_scrapers
from .social.social_aggregator import aggregate_social_findings
from .notifications.email_reminder import send_deadline_reminders
from .readme_generator import update_readme
from .verification import VerificationGate
from .adjudication import Adjudicator
from .evidence import EvidenceCollector
from .ledger import VerificationLedger, QuarantineQueue, strip_internal
from .commit_gate import CommitGate, format_gate_report
from .reach import ReachClient

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


def build_verification_stack(all_candidates_by_category, existing_by_category):
    """
    Construct the Layer 2 stack for this run.

    Returns (adjudicator, ledger, quarantine, reach) — any of which may be None
    when disabled, so callers must guard.
    """
    ledger = None
    quarantine = None
    adjudicator = None
    reach = None

    if not LAYER2_ENABLED:
        logger.info("   Layer 2 disabled (LAYER2_ENABLED=false) — Layer 1 only")
        return None, None, None, None

    ledger = VerificationLedger(LEDGER_FILE, recheck_ttl_hours=RECHECK_TTL_HOURS)
    if QUARANTINE_ENABLED:
        quarantine = QuarantineQueue(QUARANTINE_FILE)

    if REACH_ENABLED and REACH_EVIDENCE_FALLBACK:
        reach = ReachClient(
            enabled=True,
            use_jina=REACH_USE_JINA,
            jina_api_key=JINA_API_KEY,
            max_reads=REACH_MAX_READS,
            time_budget=REACH_TIME_BUDGET,
        )
        for st in reach.doctor():
            logger.info("   [Reach] %-7s → %-16s %s",
                        st.name, st.backend, st.detail)

    collector = EvidenceCollector(time_budget=EVIDENCE_TIME_BUDGET, reach=reach)

    # Corroboration must be computed across the WHOLE run plus the existing
    # dataset. Doing it per category would miss the common case of the same event
    # being reported by two different sources into the same file.
    groups = list(all_candidates_by_category.values()) + list(existing_by_category.values())
    index = Adjudicator.build_corroboration_index(*groups)

    adjudicator = Adjudicator(collector=collector, corroboration_index=index)
    logger.info("   Layer 2 armed: %d distinct titles in corroboration index", len(index))
    return adjudicator, ledger, quarantine, reach


def update_data_files(scraped, social):
    """
    Merge scraped and social data into the JSON files.

    Full flow per category:

        dedup (O(1) hash)          — cheap, removes known items
          → Layer 1 plausibility   — does the record look well-formed?
          → Layer 2 adjudication   — does independent evidence agree with it?
          → ledger / quarantine    — remember the decision, hold the unproven
          → commit gate            — do dataset-wide invariants still hold?
          → save                   — only if every gate allowed it

    Returns:
        (summary, verify_report)
    """
    summary = {}
    verify_report = {
        "l1_rejected": 0, "l2_accepted": 0, "l2_quarantined": 0,
        "l2_rejected": 0, "corrected": 0, "suppressed": 0,
        "requeued": 0, "retired": 0, "blocked_categories": [],
        "gate_decisions": [],
    }

    # Pre-load everything so corroboration and the gate can see the full picture.
    existing_by_category = {}
    candidates_preview = {}
    for category, filepath in DATA_FILES.items():
        existing_by_category[category] = load_json(filepath)
        incoming = list(scraped.get(category, [])) + list(social.get(category, []))
        candidates_preview[category] = incoming

    adjudicator, ledger, quarantine, reach = build_verification_stack(
        candidates_preview, existing_by_category
    )
    gate = CommitGate() if COMMIT_GATE_ENABLED else None
    gate_decisions = []

    for category, filepath in DATA_FILES.items():
        existing = existing_by_category[category]
        # merge_opportunities appends into `existing`, so snapshot the list first.
        existing_snapshot = list(existing)

        new_items = list(scraped.get(category, [])) + list(social.get(category, []))

        # Re-inject previously quarantined items so they get another chance with
        # fresh evidence. This is what stops a flaky host from permanently
        # costing us a real opportunity.
        if quarantine:
            held = quarantine.pending(category)
            if held:
                new_items.extend(held)
                verify_report["requeued"] += len(held)
                logger.info("  [%s] Re-queued %d quarantined item(s)", category, len(held))

        # ── Step A: cheap deduplication ────────────────────────────────────
        _, candidates = merge_opportunities(existing, new_items)

        # ── Step B: drop items already permanently disproven ───────────────
        if ledger and SUPPRESS_RETIRED and candidates:
            before_n = len(candidates)
            candidates = [c for c in candidates if not ledger.is_retired(c)]
            suppressed = before_n - len(candidates)
            if suppressed:
                verify_report["suppressed"] += suppressed
                logger.info("  [%s] Suppressed %d known-bad item(s) from the ledger",
                            category, suppressed)

        if not candidates:
            final = existing_snapshot
            expired = update_expired_statuses(final)
            summary[category] = _persist(
                category, filepath, existing_snapshot, final, [], expired,
                gate, gate_decisions, verify_report,
            )
            continue

        # ── Step C: Layer 1 — plausibility ─────────────────────────────────
        l1_gate = VerificationGate(existing_items=existing_snapshot)
        l1_pass, l1_rejected = l1_gate.verify_batch(candidates)
        verify_report["l1_rejected"] += len(l1_rejected)

        # ── Step D: Layer 2 — evidence-based adjudication ──────────────────
        if adjudicator:
            accepted, quarantined, l2_rejected = adjudicator.adjudicate_batch(l1_pass)
        else:
            accepted, quarantined, l2_rejected = l1_pass, [], []

        verify_report["l2_accepted"] += len(accepted)
        verify_report["l2_quarantined"] += len(quarantined)
        verify_report["l2_rejected"] += len(l2_rejected)

        if l1_rejected or l2_rejected or quarantined:
            logger.info(
                "  [%s] Verification: %d accepted | L1 rejected %d | "
                "L2 rejected %d | quarantined %d (of %d candidates)",
                category, len(accepted), len(l1_rejected),
                len(l2_rejected), len(quarantined), len(candidates),
            )

        # ── Step E: record decisions and manage the retry queue ────────────
        _record_outcomes(
            category, ledger, quarantine, accepted, quarantined,
            l1_rejected, l2_rejected, verify_report,
        )

        # ── Step F: assemble the proposed file ─────────────────────────────
        # Rebuilt from the snapshot rather than reusing the mutated merge output,
        # so rejected and quarantined items can never leak in via name collisions.
        final = existing_snapshot + [strip_internal(i) for i in accepted]
        expired = update_expired_statuses(final)

        summary[category] = _persist(
            category, filepath, existing_snapshot, final, accepted, expired,
            gate, gate_decisions, verify_report,
        )

    # Persist verification state so the next run inherits this run's memory.
    if not DRY_RUN:
        if ledger:
            ledger.save()
        if quarantine:
            quarantine.save()

    if adjudicator:
        verify_report["corrected"] = adjudicator.stats.get("corrected", 0)
        verify_report["adjudicator_stats"] = adjudicator.get_stats()
    if ledger:
        verify_report["ledger_stats"] = ledger.stats()
    if quarantine:
        verify_report["quarantine_stats"] = quarantine.stats()
    if reach:
        verify_report["reach_stats"] = reach.get_stats()
    verify_report["gate_decisions"] = gate_decisions

    # Re-generate README.md tables dynamically
    if not DRY_RUN:
        all_current_data = {cat: load_json(fp) for cat, fp in DATA_FILES.items()}
        try:
            update_readme(all_current_data, PROJECT_ROOT)
        except Exception as e:
            logger.error(f"[README] Failed to regenerate README: {e}")

    return summary, verify_report


def _record_outcomes(
    category, ledger, quarantine, accepted, quarantined,
    l1_rejected, l2_rejected, verify_report,
):
    """Write every verdict to the ledger and update the quarantine queue."""
    if ledger is None:
        return

    for item in accepted:
        adj = item.get("_adjudication", {}) or {}
        ledger.record(
            item, category, "accept",
            reasons=adj.get("reasons"),
            evidence_kind=adj.get("evidence", ""),
            evidence_hash=adj.get("evidence_hash", ""),
            trust=adj.get("trust"),
            corroboration=adj.get("corroboration"),
            corrections=adj.get("corrections"),
        )
        # An accepted item that was previously held is now promoted.
        if quarantine:
            quarantine.release(category, item)

    for item in l1_rejected:
        ledger.record(
            item, category, "reject", layer="L1",
            reasons=item.get("_rejection_reasons", []),
        )

    for item in l2_rejected:
        adj = item.get("_adjudication", {}) or {}
        ledger.record(
            item, category, "reject", layer="L2",
            reasons=adj.get("reasons"),
            evidence_kind=adj.get("evidence", ""),
            evidence_hash=adj.get("evidence_hash", ""),
            trust=adj.get("trust"),
            corroboration=adj.get("corroboration"),
        )

    for item in quarantined:
        adj = item.get("_adjudication", {}) or {}
        reasons = adj.get("reasons", [])
        if quarantine:
            still_held, attempts = quarantine.hold(category, item, reasons)
            if still_held:
                ledger.record(
                    item, category, "quarantine", layer="L2",
                    reasons=reasons, trust=adj.get("trust"),
                    corroboration=adj.get("corroboration"),
                )
            else:
                # Out of retries — retire it so we stop spending network on it.
                verify_report["retired"] += 1
                ledger.record(
                    item, category, "reject", layer="quarantine-expiry",
                    reasons=[f"unproven after {attempts} attempts"] + reasons,
                    permanent=True,
                )
        else:
            ledger.record(item, category, "quarantine", layer="L2", reasons=reasons)


def _persist(
    category, filepath, before, final, added, expired,
    gate, gate_decisions, verify_report,
):
    """
    Run the commit gate and write the file if it allows.

    The gate's bias is intentional: when an aggregate invariant fails we keep the
    previous file. Stale data is recoverable on the next run; a corrupted or
    emptied dataset is published breakage and, in a git-backed pipeline, is also
    permanent history.
    """
    stats = {
        "total": len(final),
        "added": len(added),
        "expired": expired,
        "added_items": [i.get("name") for i in added],
        "verified": len(added),
        "rejected": 0,
        "blocked": False,
    }

    if gate is not None:
        decision = gate.evaluate(category, before, final, added)
        gate_decisions.append(decision)
        for v in decision.warnings:
            logger.warning("  [%s] gate warning — %s", category, v)
        if not decision.allowed:
            stats["blocked"] = True
            stats["total"] = len(before)
            stats["added"] = 0
            stats["added_items"] = []
            verify_report["blocked_categories"].append(category)
            for v in decision.blockers:
                logger.error("  [%s] COMMIT BLOCKED — %s", category, v)
            logger.error("  [%s] Keeping previous %d records; no write performed.",
                         category, len(before))
            return stats

    if not (added or expired):
        logger.info("  [%s] No changes (%d total)", category, len(final))
        return stats

    if DRY_RUN:
        logger.info("  [%s] DRY RUN: would add %d, expire %d → %d total",
                    category, len(added), expired, len(final))
        return stats

    save_json(filepath, final)
    logger.info("  [%s] Saved: +%d verified, %d expired → %d total",
                category, len(added), expired, len(final))
    return stats


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


def generate_run_report(scraper_report, social_count, summary, total_time, verify_report=None):
    """Generate a human-readable report of the pipeline run."""
    verify_report = verify_report or {}
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
        flag = "  ⛔ BLOCKED" if stats.get("blocked") else ""
        lines.append(
            f"  {category:<25} {stats['total']:>4} total  {marker:>4} new  "
            f"{stats['expired']:>3} expired{flag}"
        )
        for name in stats.get("added_items", []):
            lines.append(f"    ✨ {name}")

    # ── Verification stack ──────────────────────────────────────────────
    lines.extend([
        "",
        "🛡️  VERIFICATION STACK:",
        f"  Layer 1 (plausibility)   rejected {verify_report.get('l1_rejected', 0)}",
        f"  Layer 2 (evidence)       accepted {verify_report.get('l2_accepted', 0)}  "
        f"quarantined {verify_report.get('l2_quarantined', 0)}  "
        f"rejected {verify_report.get('l2_rejected', 0)}",
        f"  Auto-corrections applied {verify_report.get('corrected', 0)}",
        f"  Suppressed (known bad)   {verify_report.get('suppressed', 0)}",
        f"  Re-queued from hold      {verify_report.get('requeued', 0)}",
        f"  Retired (out of retries) {verify_report.get('retired', 0)}",
    ])

    adj = verify_report.get("adjudicator_stats", {})
    ev = adj.get("evidence", {}) if isinstance(adj, dict) else {}
    if ev:
        lines.append(
            f"  Evidence probes          {ev.get('fetched', 0)} fetched, "
            f"{ev.get('jsonld', 0)} json-ld, {ev.get('opengraph', 0)} opengraph, "
            f"{ev.get('challenge_pages', 0)} bot-walls, "
            f"{ev.get('reach_rescued', 0)}/{ev.get('reach_attempts', 0)} reach-rescued"
        )
        if ev.get("breaker_tripped"):
            lines.append("  ⚠️  Evidence circuit breaker tripped — verdicts downgraded to 'unproven'")

    q = verify_report.get("quarantine_stats", {})
    if q.get("held_total"):
        lines.append(f"  Quarantine holding       {q['held_total']} {q.get('by_category', {})}")

    led = verify_report.get("ledger_stats", {})
    if led:
        lines.append(f"  Ledger                   {led.get('total', 0)} records {led.get('by_decision', {})}")

    reach_stats = verify_report.get("reach_stats", {})
    if reach_stats and reach_stats.get("web_reads"):
        lines.append(
            f"  Agent Reach              {reach_stats.get('web_reads', 0)} reads "
            f"({reach_stats.get('web_jina', 0)} jina, {reach_stats.get('web_direct', 0)} direct), "
            f"cli={reach_stats.get('cli_available')}"
        )

    gate_decisions = verify_report.get("gate_decisions") or []
    if gate_decisions:
        lines.append(format_gate_report(gate_decisions))

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

    # Step 3: Dedup → Layer 1 → Layer 2 → ledger/quarantine → commit gate → save
    logger.info("\n🛡️ Step 3/4: Dedup + Layer 1 + Layer 2 + Commit Gate...")
    summary, verify_report = update_data_files(scraped, social)
    logger.info(
        "   → L1 rejected %d | L2 accepted %d, quarantined %d, rejected %d | "
        "corrections %d | suppressed %d",
        verify_report.get("l1_rejected", 0),
        verify_report.get("l2_accepted", 0),
        verify_report.get("l2_quarantined", 0),
        verify_report.get("l2_rejected", 0),
        verify_report.get("corrected", 0),
        verify_report.get("suppressed", 0),
    )

    # Step 4: Send notifications
    logger.info("\n🔔 Step 4/4: Checking for deadline reminders...")
    send_notifications()

    # Auto-commit (if not handled by GitHub Actions)
    if not DRY_RUN:
        auto_commit_changes()

    # Final report
    total_time = time.time() - pipeline_start
    report = generate_run_report(
        scraper_report, total_social, summary, total_time, verify_report
    )
    logger.info(report)

    # Save report to file for GitHub Actions artifact
    report_path = os.path.join(PROJECT_ROOT, "automation", "last_run_report.txt")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
    except Exception:
        pass

    # Surface a blocked write as a build failure. Silently publishing nothing is
    # how a broken scraper stays broken for weeks.
    blocked = verify_report.get("blocked_categories") or []
    if blocked and FAIL_RUN_ON_GATE_BLOCK:
        logger.error(
            "Commit gate blocked %d category file(s): %s. "
            "Previous data was retained — investigate before the next run.",
            len(blocked), ", ".join(blocked),
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
