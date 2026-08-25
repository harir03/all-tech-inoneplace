"""
OpportunityHub — Automated README Table & Reward-Filter Generator
Dynamically regenerates root README.md directly from data/*.json on every pipeline run.
Features dedicated Reward & Prize Pool filter sections (Cash Prizes, Job Tracks, Stipends, Swag/Perks)
and Vercel 1-click deploy badges.
"""

import json
import os
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def generate_badge_markdown(total_counts, updated_time_str):
    """Generate dynamic status badges for the README."""
    total_all = sum(total_counts.values())
    
    return f"""<div align="center">

# 🚀 OpportunityHub — All Tech in One Place

### The Automated, Curated Hub for Hackathons, Internships, Competitions, Open Source & Fellowships

[![Opportunities](https://img.shields.io/badge/Opportunities-{total_all}+%20Active-6c5ce7.svg?style=for-the-badge)](data/)
[![Last Updated](https://img.shields.io/badge/Last%20Updated-{updated_time_str}-00cec9.svg?style=for-the-badge)](https://github.com/harir03/all-tech-inoneplace/commits/main)
[![Auto-Updated](https://img.shields.io/badge/Automated-Hourly%20via%20GitHub%20Actions-0984e3.svg?style=for-the-badge)](.github/workflows/auto-update.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-ffd32a.svg?style=for-the-badge)](LICENSE)

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fharir03%2Fall-tech-inoneplace)

**Never miss an application deadline again.** A real-time, automated aggregation pipeline scraping top student directories, official APIs (Devpost, MLH, Codeforces, LeetCode, GSoC), and GitHub trackers hourly.

[🌐 **Browse Interactive Web App**](https://harir03.github.io/all-tech-inoneplace/) · [➕ **Submit Opportunity**](https://github.com/harir03/all-tech-inoneplace/issues/new?template=add-opportunity.yml) · [🐛 **Report Issue**](https://github.com/harir03/all-tech-inoneplace/issues/new?template=report-issue.yml)

</div>"""


def format_category_table(category_name, items, max_items=12):
    """Format category table for only active/open opportunities."""
    active_items = [it for it in items if it.get("status") in ("open", "coming-soon")]
    
    if not active_items:
        return f"\n*All current {category_name.lower()} have concluded or are undergoing updates. Check back soon or visit the [Interactive Web App](https://harir03.github.io/all-tech-inoneplace/) for full listings.*\n"

    selected = active_items[:max_items]

    status_emojis = {
        "open": "🟢 Open",
        "coming-soon": "🟡 Soon",
    }

    lines = []
    if category_name == "Hackathons":
        lines.append("| Name | Organizer | Location / Mode | Prize / Fee | Timeline / Deadline | Status | Apply |")
        lines.append("|:-----|:----------|:----------------|:------------|:--------------------|:------:|:-----:|")
        for it in selected:
            name = it.get("name", "Hackathon").replace("|", "-")
            org = it.get("organizer", "Organizer").replace("|", "-")
            mode = it.get("mode", "Online").replace("|", "-")
            prize = (it.get("prize") or it.get("fee") or "Free").replace("|", "-")
            deadline = (it.get("deadline") or "Check page").replace("|", "-")
            status = status_emojis.get(it.get("status"), "🟢 Open")
            link = it.get("applicationLink") or it.get("website") or "#"
            lines.append(f"| **{name}** | {org} | {mode} | {prize} | {deadline} | {status} | [Apply →]({link}) |")

    elif category_name in ("Internships", "Jobs"):
        lines.append("| Company & Role | Location | Level / Type | Compensation | Deadline | Status | Apply |")
        lines.append("|:---------------|:---------|:-------------|:-------------|:---------|:------:|:-----:|")
        for it in selected:
            name = it.get("name", "Role").replace("|", "-")
            loc = (it.get("location") or it.get("mode") or "Check listing").replace("|", "-")
            elig = it.get("eligibility", "Graduates / Students").replace("|", "-")
            stipend = (it.get("stipend") or "Competitive / Check listing").replace("|", "-")
            deadline = (it.get("deadline") or "Apply ASAP").replace("|", "-")
            status = status_emojis.get(it.get("status"), "🟢 Open")
            link = it.get("applicationLink") or it.get("website") or "#"
            lines.append(f"| **{name}** | {loc} | {elig} | {stipend} | {deadline} | {status} | [Apply →]({link}) |")

    elif category_name == "Competitions":
        lines.append("| Contest / Challenge | Platform | Mode | Prizes / Rating | Event Date | Status | Register |")
        lines.append("|:--------------------|:---------|:-----|:----------------|:-----------|:------:|:--------:|")
        for it in selected:
            name = it.get("name", "Contest").replace("|", "-")
            org = it.get("organizer", "Platform").replace("|", "-")
            mode = it.get("mode", "Online").replace("|", "-")
            prize = (it.get("prize") or "Rating + Prizes").replace("|", "-")
            event_date = (it.get("eventDate") or it.get("deadline") or "Weekly").replace("|", "-")
            status = status_emojis.get(it.get("status"), "🟢 Open")
            link = it.get("applicationLink") or it.get("website") or "#"
            lines.append(f"| **{name}** | {org} | {mode} | {prize} | {event_date} | {status} | [Register →]({link}) |")

    elif category_name == "Open Source Programs":
        lines.append("| Program | Organization | Stipend / Grant | Duration | Timeline / Deadline | Status | Apply |")
        lines.append("|:--------|:-------------|:----------------|:---------|:--------------------|:------:|:-----:|")
        for it in selected:
            name = it.get("name", "OS Program").replace("|", "-")
            org = it.get("organizer", "Open Source").replace("|", "-")
            stipend = (it.get("stipend") or "Stipend Provided").replace("|", "-")
            duration = (it.get("duration") or "10-12 weeks").replace("|", "-")
            deadline = (it.get("deadline") or "Annual").replace("|", "-")
            status = status_emojis.get(it.get("status"), "🟢 Open")
            link = it.get("applicationLink") or it.get("website") or "#"
            lines.append(f"| **{name}** | {org} | {stipend} | {duration} | {deadline} | {status} | [Apply →]({link}) |")

    elif category_name == "Fellowships":
        lines.append("| Fellowship Name | Organization | Focus / Eligibility | Stipend & Benefits | Timeline | Status | Apply |")
        lines.append("|:----------------|:-------------|:--------------------|:-------------------|:---------|:------:|:-----:|")
        for it in selected:
            name = it.get("name", "Fellowship").replace("|", "-")
            org = it.get("organizer", "Foundation").replace("|", "-")
            elig = (it.get("eligibility") or "Students / Graduates").replace("|", "-")
            stipend = (it.get("stipend") or "Stipend + Mentorship").replace("|", "-")
            deadline = (it.get("deadline") or "Check Portal").replace("|", "-")
            status = status_emojis.get(it.get("status"), "🟢 Open")
            link = it.get("applicationLink") or it.get("website") or "#"
            lines.append(f"| **{name}** | {org} | {elig} | {stipend} | {deadline} | {status} | [Apply →]({link}) |")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  REWARD & PRIZE POOL FILTER TABLES (Cash, Job Offers, Stipends, Swag)
# ═══════════════════════════════════════════════════════════════════

def build_cash_prizes_table(all_data):
    """Filter for top cash prize hackathons and competitions."""
    cash_items = []
    
    # Check hackathons and competitions
    for cat in ["hackathons", "competitions"]:
        for it in all_data.get(cat, []):
            if it.get("status") not in ("open", "coming-soon"):
                continue
            prize = (it.get("prize") or "").strip()
            # Match currency symbols or big numbers
            if re.search(r'(\$|₹|USD|INR|cash|\b[0-9]{2,3},[0-9]{3}\b|\b[0-9]{5,}\b)', prize, re.IGNORECASE):
                cash_items.append(it)

    if not cash_items:
        return "*Check live category tables below.*"

    # Sort items by prize presence
    lines = [
        "| Event Name | Type | Prize Pool / Rewards | Mode / Location | Deadline | Apply |",
        "|:-----------|:-----|:---------------------|:----------------|:---------|:-----:|",
    ]
    for it in cash_items[:10]:
        name = it.get("name", "Event").replace("|", "-")
        typ = ("🏆 Hackathon" if "hackathon" in it.get("tags", []) else "⚔️ Contest").replace("|", "-")
        prize = (it.get("prize") or "Cash Prize").replace("|", "-")
        mode = (it.get("mode") or "Online").replace("|", "-")
        deadline = (it.get("deadline") or "Check page").replace("|", "-")
        link = it.get("applicationLink") or it.get("website") or "#"
        lines.append(f"| **{name}** | {typ} | **{prize}** | {mode} | {deadline} | [Apply →]({link}) |")

    return "\n".join(lines)


def build_stipends_table(all_data):
    """Filter for paid open-source mentorships and research fellowships."""
    stipend_items = []
    
    for cat in ["open-source-programs", "fellowships"]:
        for it in all_data.get(cat, []):
            if it.get("status") not in ("open", "coming-soon"):
                continue
            stipend = (it.get("stipend") or "").strip()
            if re.search(r'(\$|₹|CAD|EUR|stipend|grant|month|salary)', stipend, re.IGNORECASE):
                stipend_items.append(it)

    if not stipend_items:
        return "*Check live category tables below.*"

    lines = [
        "| Program Name | Organization | Stipend & Benefits | Duration | Eligibility | Apply |",
        "|:-------------|:-------------|:-------------------|:---------|:------------|:-----:|",
    ]
    for it in stipend_items[:10]:
        name = it.get("name", "Program").replace("|", "-")
        org = (it.get("organizer") or "Open Source").replace("|", "-")
        stipend = (it.get("stipend") or "Stipend Provided").replace("|", "-")
        dur = (it.get("duration") or "10-12 weeks").replace("|", "-")
        elig = (it.get("eligibility") or "Students & Developers").replace("|", "-")
        link = it.get("applicationLink") or it.get("website") or "#"
        lines.append(f"| **{name}** | {org} | **{stipend}** | {dur} | {elig} | [Apply →]({link}) |")

    return "\n".join(lines)


def build_job_tracks_table(all_data):
    """Filter for top tech internships offering direct full-time / PPO conversion."""
    intern_items = []
    
    for it in all_data.get("internships", []):
        if it.get("status") not in ("open", "coming-soon"):
            continue
        name = it.get("name", "")
        # Highlight top brands or high-demand engineering roles
        if any(b in name.lower() for b in ["google", "microsoft", "amd", "goldman", "datadog", "isro", "mitacs", "bny", "sage", "springs", "westinghouse"]):
            intern_items.append(it)

    if not intern_items:
        intern_items = [it for it in all_data.get("internships", []) if it.get("status") in ("open", "coming-soon")]

    lines = [
        "| Company & Role | Location | Career Level | Compensation | Application Link |",
        "|:---------------|:---------|:-------------|:-------------|:----------------:|",
    ]
    for it in intern_items[:10]:
        name = it.get("name", "Internship").replace("|", "-")
        loc = (it.get("location") or it.get("mode") or "Various").replace("|", "-")
        elig = (it.get("eligibility") or "Students / New Grads").replace("|", "-")
        stipend = (it.get("stipend") or "Competitive").replace("|", "-")
        link = it.get("applicationLink") or it.get("website") or "#"
        lines.append(f"| **{name}** | {loc} | {elig} | {stipend} | [Apply Now →]({link}) |")

    return "\n".join(lines)


def build_swag_perks_table(all_data):
    """Filter for events offering free swag kits, certificates, hardware labs & GPU credits."""
    swag_items = [
        {
            "name": "MLH Global Hack Week",
            "org": "Major League Hacking (MLH)",
            "perks": "🎁 Free Official Swag Kits, T-Shirts, Stickers, Discord Badges & MLH Season Points",
            "mode": "Online (Worldwide)",
            "link": "https://ghw.mlh.io"
        },
        {
            "name": "Hacktoberfest",
            "org": "DigitalOcean & Cloudflare",
            "perks": "🌳 Official Contributor Digital Badge, Swag Packs & Tree Planting in your name",
            "mode": "Online",
            "link": "https://hacktoberfest.com"
        },
        {
            "name": "NVIDIA OpenHackathons",
            "org": "NVIDIA / OpenACC",
            "perks": "⚡ Free GPU Cluster Compute Access, Mentorship from NVIDIA AI Engineers, Certificate",
            "mode": "Online / Hybrid",
            "link": "https://www.openhackathons.org/"
        },
        {
            "name": "GitHub Student Developer Pack",
            "org": "GitHub Education",
            "perks": "🎒 $200k+ in Free Cloud Credits (AWS, Azure, DigitalOcean), Domain names, GitHub Copilot",
            "mode": "Online",
            "link": "https://education.github.com/pack"
        },
        {
            "name": "Midnight Virtual Hackathons",
            "org": "Major League Hacking",
            "perks": "🛠️ Hardware Lab Access, API Credits, Swag, Resume Drop to Sponsors",
            "mode": "Online",
            "link": "https://events.mlh.com/"
        }
    ]

    lines = [
        "| Event / Initiative | Provider | Perks, Goodies & Free Credits | Access | Claim / Register |",
        "|:-------------------|:---------|:------------------------------|:-------|:----------------:|",
    ]
    for it in swag_items:
        lines.append(f"| **{it['name']}** | {it['org']} | {it['perks']} | {it['mode']} | [Claim / Register →]({it['link']}) |")

    return "\n".join(lines)


def update_readme(data_dict, project_root):
    """Regenerate README.md using the latest data with reward-based filters."""
    readme_path = os.path.join(project_root, "README.md")
    
    counts = {k: len(v) for k, v in data_dict.items()}
    now_utc = datetime.utcnow().strftime("%Y--%m--%d%%20%H:%M%%20UTC")
    
    header = generate_badge_markdown(counts, now_utc)

    # Reward Filter Tables
    cash_table = build_cash_prizes_table(data_dict)
    stipends_table = build_stipends_table(data_dict)
    job_tracks_table = build_job_tracks_table(data_dict)
    swag_table = build_swag_perks_table(data_dict)

    # Category Tables
    hackathons_table = format_category_table("Hackathons", data_dict.get("hackathons", []), max_items=12)
    internships_table = format_category_table("Internships", data_dict.get("internships", []), max_items=12)
    jobs_table = format_category_table("Jobs", data_dict.get("jobs", []), max_items=12)
    competitions_table = format_category_table("Competitions", data_dict.get("competitions", []), max_items=8)
    opensource_table = format_category_table("Open Source Programs", data_dict.get("open-source-programs", []), max_items=12)
    fellowships_table = format_category_table("Fellowships", data_dict.get("fellowships", []), max_items=8)

    readme_content = f"""{header}

---

## 🎯 Quick Jump: Browse by Reward & Prize Type

| 💰 [Mega Cash Prizes](#-top-mega-cash-prizes) | 💼 [Job & Internship Tracks](#-direct-internship--job-referral-tracks) | 🌍 [Paid OS Stipends](#-stipend-backed-open-source-mentorships) | 🎁 [Swag, Goodies & Free GPU Credits](#-swag-goodies-hardware-labs--cloud-credits) |
|:---:|:---:|:---:|:---:|

---

## 💰 Top Mega Cash Prizes ($10,000 to $740,000+ / ₹1,00,000+)

> Live hackathons and coding competitions offering major cash prize pools and bounties.

{cash_table}

---

## 💼 Direct Internship & Job Referral Tracks

> Featured technical roles offering full-time internships, co-ops, and Pre-Placement Offers (PPOs).

{job_tracks_table}

---

## 🌍 Stipend-Backed Open Source Mentorships ($1,500 – $7,000)

> Prestigious open source programs where contributors get paired with senior mentors and receive milestone stipends.

{stipends_table}

---

## 🎁 Swag, Goodies, Hardware Labs & Cloud Credits

> Free student benefits, verified contributor swag boxes, hardware labs, and developer packs.

{swag_table}

---

## 📋 Full Directory by Category

- [🏆 Live Hackathons ({counts.get('hackathons', 0)})](#-live-hackathons)
- [💼 Tech Internships ({counts.get('internships', 0)})](#-tech-internships)
- [🏢 Full-Time Jobs & New Grad ({counts.get('jobs', 0)})](#-full-time-jobs--new-grad)
- [⚔️ Competitions & Contests ({counts.get('competitions', 0)})](#️-competitions--contests)
- [🌍 Open Source Programs ({counts.get('open-source-programs', 0)})](#-open-source-programs)
- [🎓 Fellowships & Grants ({counts.get('fellowships', 0)})](#-fellowships--grants)

---

## 🏆 Live Hackathons

> Showing featured active & upcoming hackathons. Browse all **{counts.get('hackathons', 0)} hackathons** on the [🌐 Interactive Web App](https://harir03.github.io/all-tech-inoneplace/).

{hackathons_table}

---

## 💼 Tech Internships

> Showing featured openings. Filter all **{counts.get('internships', 0):,} internships** by domain (AI/ML, SWE, Cloud, Security) on the [🌐 Interactive Web App](https://harir03.github.io/all-tech-inoneplace/).

{internships_table}

---

## 🏢 Full-Time Jobs & New Grad

> Showing entry-level & new grad engineering positions. Filter all **{counts.get('jobs', 0):,} full-time jobs** on the [🌐 Interactive Web App](https://harir03.github.io/all-tech-inoneplace/).

{jobs_table}

---

## ⚔️ Competitions & Contests

> Real-time contests from Codeforces, LeetCode, ICPC, and competitive programming platforms.

{competitions_table}

---

## 🌍 Open Source Programs

{opensource_table}

---

## 🎓 Fellowships & Grants

{fellowships_table}

---

## 🌐 Deploy to Vercel (1-Click Deployment)

You can host this entire platform on Vercel with zero configuration:

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fharir03%2Fall-tech-inoneplace)

### Manual Vercel Deployment:
1. Import `harir03/all-tech-inoneplace` in your [Vercel Dashboard](https://vercel.com/new).
2. Framework Preset: **Other** (Root directory: `./`).
3. Click **Deploy** — [`vercel.json`](vercel.json) will automatically handle clean routing and `/data/` endpoints!

---

## 🤖 Automated Hourly Pipeline Architecture

```mermaid
graph TD
    A[GitHub Actions Cron: Hourly] --> B[automation/pipeline.py]
    B --> C1[Devpost Live JSON API]
    B --> C2[MLH Live Events API]
    B --> C3[Codeforces & LeetCode APIs]
    B --> C4[SimplifyJobs Daily Repos: 12k Stars]
    B --> C5[GSoC & Deepanshu OS Trackers]
    C1 & C2 & C3 & C4 & C5 --> D[Intelligent Date Expiry & Deduplication Engine]
    D --> E[Update data/*.json datasets: 1,700+ opportunities]
    E --> F[Dynamically Rebuild README.md with Reward Filters]
    F --> G[Auto-Commit to GitHub & Deploy to Vercel / GitHub Pages]
```

---

## 🤝 How to Contribute

- ➕ **[Submit an Opportunity](https://github.com/harir03/all-tech-inoneplace/issues/new?template=add-opportunity.yml)** via our issue form.
- 🐛 **[Report Outdated Info / Dead Links](https://github.com/harir03/all-tech-inoneplace/issues/new?template=report-issue.yml)**.
- 💻 **Open a Pull Request**: Edit `data/*.json` directly.

---

## 📜 License

Distributed under the [MIT License](LICENSE).
"""

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    logger.info(f"✅ README.md successfully regenerated with reward filters ({sum(counts.values())} total items)")
