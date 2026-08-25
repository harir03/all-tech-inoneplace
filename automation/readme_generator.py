"""
OpportunityHub — Automated README Table Generator
Dynamically regenerates the root README.md tables directly from data/*.json on every pipeline run.
Ensures that the GitHub repository README is never stale or outdated.
"""

import json
import os
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

**Never miss an application deadline again.** A real-time, automated aggregation pipeline scraping top student directories, official APIs (Devpost, MLH, Codeforces, LeetCode, GSoC), and GitHub trackers hourly.

[🌐 **Browse Interactive Web App**](https://harir03.github.io/all-tech-inoneplace/) · [➕ **Submit Opportunity**](https://github.com/harir03/all-tech-inoneplace/issues/new?template=add-opportunity.yml) · [🐛 **Report Issue**](https://github.com/harir03/all-tech-inoneplace/issues/new?template=report-issue.yml)

</div>"""


def format_table(category_name, items, max_items=15):
    """Format a list of opportunity dicts into a clean Markdown table."""
    # Filter ONLY active, open, and coming-soon items
    active_items = [it for it in items if it.get("status") in ("open", "coming-soon")]
    
    if not active_items:
        return f"\n*All current {category_name.lower()} have concluded or are undergoing updates. Check back soon or visit the [Interactive Web App](https://harir03.github.io/all-tech-inoneplace/) for historical listings.*\n"

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

    elif category_name == "Internships":
        lines.append("| Company & Role | Location | Level / Type | Compensation | Deadline | Status | Apply |")
        lines.append("|:---------------|:---------|:-------------|:-------------|:---------|:------:|:-----:|")
        for it in selected:
            name = it.get("name", "Internship").replace("|", "-")
            loc = (it.get("location") or it.get("mode") or "Check listing").replace("|", "-")
            elig = it.get("eligibility", "Students").replace("|", "-")
            stipend = (it.get("stipend") or "Competitive").replace("|", "-")
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


def update_readme(data_dict, project_root):
    """Regenerate README.md using the latest data."""
    readme_path = os.path.join(project_root, "README.md")
    
    counts = {k: len(v) for k, v in data_dict.items()}
    now_utc = datetime.utcnow().strftime("%Y--%m--%d%%20%H:%M%%20UTC")
    
    header = generate_badge_markdown(counts, now_utc)

    hackathons_table = format_table("Hackathons", data_dict.get("hackathons", []), max_items=15)
    internships_table = format_table("Internships", data_dict.get("internships", []), max_items=15)
    competitions_table = format_table("Competitions", data_dict.get("competitions", []), max_items=10)
    opensource_table = format_table("Open Source Programs", data_dict.get("open-source-programs", []), max_items=15)
    fellowships_table = format_table("Fellowships", data_dict.get("fellowships", []), max_items=10)

    readme_content = f"""{header}

---

## 📋 Table of Contents

- [🏆 Live Hackathons ({counts.get('hackathons', 0)})](#-live-hackathons)
- [💼 Featured Tech Internships ({counts.get('internships', 0)})](#-featured-tech-internships)
- [⚔️ Live Competitions & Contests ({counts.get('competitions', 0)})](#️-live-competitions--contests)
- [🌍 Open Source Programs & Mentorships ({counts.get('open-source-programs', 0)})](#-open-source-programs--mentorships)
- [🎓 Fellowships & Grants ({counts.get('fellowships', 0)})](#-fellowships--grants)
- [🌐 Interactive Website & Filters](#-interactive-website--filters)
- [🤖 Automated Production Pipeline](#-automated-production-pipeline)
- [🤝 How to Contribute](#-how-to-contribute)
- [📜 License](#-license)

---

## 🏆 Live Hackathons

> Showing top active & upcoming hackathons. Browse all **{counts.get('hackathons', 0)} hackathons** on the [🌐 Interactive Web App](https://harir03.github.io/all-tech-inoneplace/).

{hackathons_table}

---

## 💼 Featured Tech Internships

> Showing sample openings. Browse all **{counts.get('internships', 0):,} internships & new grad positions** on the [🌐 Interactive Web App](https://harir03.github.io/all-tech-inoneplace/) with role, domain & location filters!

{internships_table}

---

## ⚔️ Live Competitions & Contests

> Real-time contests fetched directly from Codeforces, LeetCode, ACM-ICPC, and platforms.

{competitions_table}

---

## 🌍 Open Source Programs & Mentorships

> Mentorship programs offering stipends, contributor tracks, and real-world OSS experience.

{opensource_table}

---

## 🎓 Fellowships & Grants

{fellowships_table}

---

## 🌐 Interactive Website & Filters

OpportunityHub comes with a companion web app offering:
- **💻 Role & Domain Filters**: Software Engineering, AI/ML, Data Science, Cloud/DevOps, Security, Mobile, Hardware/FPGA, Quant, Product.
- **📍 Location Filters**: Remote (WFH), India (Bangalore, NCR, Pune, Hyd), US, Canada, Europe, Global.
- **⚡ 1-Click Quick Apply**: Store your profile locally in your browser and autofill applications with 1 click.
- **🔔 Deadline Reminders**: Get notified before deadlines close.

👉 **Launch the Web App:** [**https://harir03.github.io/all-tech-inoneplace/**](https://harir03.github.io/all-tech-inoneplace/)

---

## 🤖 Automated Production Pipeline

OpportunityHub is powered by a GitHub Actions automation engine that runs **every hour**:

```mermaid
graph TD
    A[GitHub Actions Cron: Hourly] --> B[Multi-Tier Scraping Pipeline]
    B --> C1[Tier 1: GitHub Curated Repos]
    B --> C2[Tier 2: Official Public APIs: Devpost, MLH, Codeforces, LeetCode, GSoC]
    B --> C3[Tier 3: Web Scrapers with Scrapling]
    C1 --> D[Deduplication & Validation Engine]
    C2 --> D
    C3 --> D
    D --> E[Update data/*.json datasets]
    E --> F[Auto-Regenerate README.md tables]
    F --> G[Auto-Commit & Deploy to GitHub Pages]
```

---

## 🤝 How to Contribute

We love community contributions!
- ➕ **[Submit an Opportunity](https://github.com/harir03/all-tech-inoneplace/issues/new?template=add-opportunity.yml)** via our structured form.
- 🐛 **[Report Dead Links or Outdated Info](https://github.com/harir03/all-tech-inoneplace/issues/new?template=report-issue.yml)**.
- 💻 **Open a PR**: Edit `data/*.json` directly and submit a Pull Request.

---

## 📜 License

Distributed under the [MIT License](LICENSE). Data aggregated from open-source community trackers and public APIs.
"""

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    
    logger.info(f"✅ README.md successfully regenerated with latest live data ({sum(counts.values())} total items)")
