"""
OpportunityHub — One-time geographic backfill & purge

The ingestion pipeline now classifies every incoming record and filters out
anything requiring physical presence outside the home country, but that only
governs NEW records. The existing files were accumulated before the filter
existed and are dominated by US listings:

    internships   1,499 records — 1,231 US, 104 UK, 74 CA,  4 IN
    jobs            939 records —   743 US,  64 UK, 57 CA,  1 IN

This script handles that backlog in two separable steps:

    1. ANNOTATE (always, safe)
       Adds `locationMode`, `locationLabel` and `country` to every record in
       every category. Purely additive, so the website can offer a location
       filter without anything being deleted.

    2. PURGE (only with --purge)
       Removes records that require presence outside the home country, in the
       configured categories only.

Why this is a separate script and not part of the pipeline
---------------------------------------------------------
Deleting ~2,277 records is exactly the shape of catastrophe `commit_gate.py`
exists to prevent: it trips both the 90% retention floor and the link-coverage
check. That guard is correct and should NOT be weakened. A deliberate,
operator-initiated migration is a different thing from a scraper malfunction, so
it gets its own explicit, reviewable entry point that reports precisely what it
will do and writes nothing unless asked.

Usage
-----
    python -m automation.tools.apply_location_policy              # dry run
    python -m automation.tools.apply_location_policy --annotate   # write tags only
    python -m automation.tools.apply_location_policy --purge      # tags + delete
    python -m automation.tools.apply_location_policy --purge --categories internships
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from automation import location as geo
from automation.config import (
    DATA_FILES, LOCATION_FILTERED_CATEGORIES, LOCATION_HOME_COUNTRY, LOCATION_POLICY,
)
from automation.utils import load_json, save_json


def analyze(records: List[Dict]) -> Tuple[List[Dict], List[Dict], Counter, Counter]:
    """Annotate in place; return (keep, drop, mode_counts, country_counts)."""
    keep, drop = [], []
    modes, countries = Counter(), Counter()
    for rec in records:
        if not isinstance(rec, dict):
            continue
        info = geo.annotate(rec)
        modes[info.mode] += 1
        countries[info.country or "(unknown)"] += 1
        ok, _ = geo.should_include(info, LOCATION_POLICY, LOCATION_HOME_COUNTRY)
        (keep if ok else drop).append(rec)
    return keep, drop, modes, countries


def backup(path: str, stamp: str) -> str:
    dest = f"{path}.pre-location-{stamp}.bak"
    shutil.copy2(path, dest)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill location fields and optionally purge out-of-country records.")
    ap.add_argument("--annotate", action="store_true", help="write location fields (no deletions)")
    ap.add_argument("--purge", action="store_true", help="write location fields AND delete out-of-country records")
    ap.add_argument("--categories", default=",".join(LOCATION_FILTERED_CATEGORIES),
                    help="comma-separated categories eligible for purging")
    ap.add_argument("--no-backup", action="store_true", help="skip .bak files")
    args = ap.parse_args()

    purge_categories = {c.strip() for c in args.categories.split(",") if c.strip()}
    write = args.annotate or args.purge
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    print("=" * 92)
    print(f"  GEOGRAPHIC BACKFILL{' + PURGE' if args.purge else ''}"
          f"   home={LOCATION_HOME_COUNTRY}   mode={'WRITE' if write else 'DRY RUN'}")
    print("=" * 92)
    print(f"  policy          : {LOCATION_POLICY}")
    print(f"  purgeable cats  : {sorted(purge_categories)}")
    print()

    grand_before = grand_after = grand_dropped = 0

    for category, path in DATA_FILES.items():
        records = load_json(path)
        if not records:
            print(f"  {category:<24} (empty or missing)")
            continue

        keep, drop, modes, countries = analyze(records)
        purgeable = category in purge_categories and args.purge
        final = keep if purgeable else records

        grand_before += len(records)
        grand_after += len(final)
        if purgeable:
            grand_dropped += len(drop)

        arrow = f"{len(records)} -> {len(final)}"
        note = "" if purgeable else ("  (annotate only)" if drop else "")
        print(f"  {category:<24} {arrow:<16} drop_eligible={len(drop):<5}{note}")
        print(f"  {'':<24} modes={dict(modes)}")
        top = [f"{k}={v}" for k, v in countries.most_common(5)]
        print(f"  {'':<24} countries={', '.join(top)}")

        if write:
            if not args.no_backup:
                b = backup(path, stamp)
                print(f"  {'':<24} backup -> {os.path.basename(b)}")
            save_json(path, final)
            print(f"  {'':<24} WROTE {len(final)} records")
        print()

    print("=" * 92)
    print(f"  TOTAL {grand_before} -> {grand_after}"
          f"   ({grand_dropped} purged)" if args.purge else f"  TOTAL {grand_before} records analyzed")
    if not write:
        print("  DRY RUN — nothing written. Re-run with --annotate or --purge.")
    print("=" * 92)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
