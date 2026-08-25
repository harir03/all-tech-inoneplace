"""
OpportunityHub — Multi-Repo GitHub Scraper
Pulls curated opportunities directly from high-quality, independent GitHub repositories.

Supported Source Repositories:
1. SimplifyJobs/Summer2025-Internships (HTML tables — tech internships)
2. SimplifyJobs/New-Grad-Positions (HTML tables — entry-level/new grad tech roles)
3. deepanshu1422/List-Of-Open-Source-Internships-Programs (Markdown tables — GSoC, Outreachy, LFX, etc.)
4. ayush-sleeping/Every-Open-Source-Programs (Markdown tables — month-by-month open source programs)
5. open-sauced/awesome-oss-programs (Markdown lists — OSS fellowships & incubators)
6. dipakkr/A-to-Z-Resources-for-Students (Markdown tables & lists — hackathons, competitions, fellowships)
"""

import logging
import re
import subprocess
import urllib.request
import ssl
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

# List of independent GitHub repositories to scrape
GITHUB_SOURCES = [
    # ── Internships & New Grad ──
    {
        "name": "SimplifyJobs-Internships",
        "url": "https://raw.githubusercontent.com/SimplifyJobs/Summer2025-Internships/dev/README.md",
        "category": "internships",
        "parser": "simplify_html",
        "description": "Curated tech internships from Pitt CSC & Simplify",
    },
    {
        "name": "SimplifyJobs-NewGrad",
        "url": "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md",
        "category": "internships",
        "parser": "simplify_html",
        "description": "Curated new-grad and entry-level tech roles",
    },
    # ── Open Source Programs ──
    {
        "name": "Deepanshu-OSPrograms",
        "url": "https://raw.githubusercontent.com/deepanshu1422/List-Of-Open-Source-Internships-Programs/master/README.md",
        "category": "open-source-programs",
        "parser": "markdown_table",
        "description": "Curated open source mentorships and internships",
    },
    {
        "name": "Ayush-EveryOSS",
        "url": "https://raw.githubusercontent.com/ayush-sleeping/Every-Open-Source-Programs/main/README.md",
        "category": "open-source-programs",
        "parser": "markdown_table",
        "description": "Open source programs with deadlines",
    },
    {
        "name": "OpenSauced-OSS",
        "url": "https://raw.githubusercontent.com/open-sauced/awesome-oss-programs/main/README.md",
        "category": "open-source-programs",
        "parser": "markdown_list",
        "description": "Open source fellowships, accelerators & incubators",
    },
    # ── Multi-Category (Hackathons, Competitions, Fellowships) ──
    {
        "name": "Dipakkr-StudentResources",
        "url": "https://raw.githubusercontent.com/dipakkr/A-to-Z-Resources-for-Students/master/README.md",
        "category": "multi",
        "parser": "dipakkr_multi",
        "description": "A-to-Z student resources: top hackathons, competitions & fellowships",
    },
]


def fetch_url_robust(url, timeout=12):
    """Fetch raw file content with multi-strategy fallback (curl -> urllib)."""
    # Strategy 1: System curl (fastest and most reliable on Windows/Linux/macOS)
    try:
        res = subprocess.run(
            ["curl.exe" if subprocess.os.name == "nt" else "curl", "-sL", "--max-time", str(timeout), url],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        if res.returncode == 0 and len(res.stdout) > 20:
            return res.stdout
    except Exception:
        pass

    # Strategy 2: Standard urllib with SSL context
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OpportunityHub/1.0",
                "Accept": "text/plain, text/markdown, */*",
            },
        )
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        logger.warning(f"Fetch failed for {url}: {e}")

    return None


def strip_markdown_links(text):
    """Convert [text](url) or **[text](url)** to just text."""
    if not text:
        return ""
    text = re.sub(r'[*_~`]', '', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    return text.strip()


def extract_url(text):
    """Extract first URL from Markdown link [text](url) or plaintext URL."""
    if not text:
        return ""
    match = re.search(r'\]\((https?://[^)]+)\)', text)
    if match:
        return match.group(1).strip()
    match = re.search(r'https?://[^\s)\]"\'>]+', text)
    if match:
        return match.group(0).strip()
    return ""


# ═══════════════════════════════════════════════════════════════════
#  HTML TABLE PARSER (for SimplifyJobs)
# ═══════════════════════════════════════════════════════════════════

class SimplifyHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self._current_row = []
        self._current_cell = ""
        self._in_td = False
        self._cell_links = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._current_row = []
        elif tag in ("td", "th"):
            self._in_td = True
            self._current_cell = ""
            self._cell_links = []
        elif tag == "a" and self._in_td:
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            if href and href.startswith("http"):
                self._cell_links.append(href)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._in_td:
            self._in_td = False
            self._current_row.append({
                "text": self._current_cell.strip(),
                "links": list(self._cell_links),
            })
        elif tag == "tr":
            if len(self._current_row) >= 3:
                self.rows.append(self._current_row)

    def handle_data(self, data):
        if self._in_td:
            self._current_cell += data


def parse_simplify_html(content, source_name):
    """Parse SimplifyJobs HTML tables into opportunity objects."""
    parser = SimplifyHTMLParser()
    try:
        parser.feed(content)
    except Exception as e:
        logger.debug(f"HTML parse error: {e}")

    opportunities = []
    for row in parser.rows:
        if len(row) < 3:
            continue

        company_cell = row[0]
        role_cell = row[1] if len(row) > 1 else {"text": "", "links": []}
        loc_cell = row[2] if len(row) > 2 else {"text": "", "links": []}
        app_cell = row[3] if len(row) > 3 else {"text": "", "links": []}

        company = company_cell["text"].strip()
        role = role_cell["text"].strip()
        location = loc_cell["text"].strip()

        # Skip headers or empty rows
        if not company or company.lower() in ("company", "name", "organization") or not role:
            continue
        # Skip closed listings
        if "🔒" in company or "🔒" in role or "🔒" in location:
            continue

        # Extract links
        app_link = ""
        if app_cell["links"]:
            app_link = app_cell["links"][0]
        elif company_cell["links"]:
            app_link = company_cell["links"][0]
        elif role_cell["links"]:
            app_link = role_cell["links"][0]

        mode = "Remote" if any(k in location.lower() for k in ["remote", "work from home", "wfh"]) else (location or "Check listing")

        opportunity = {
            "name": f"{company} — {role}",
            "organizer": company,
            "description": f"{role} position at {company}. Location: {location or 'Various'}.",
            "eligibility": "Students / New Grads (check listing)",
            "mode": mode,
            "fee": "Free",
            "stipend": "Competitive / Check listing",
            "deadline": "Apply ASAP (Rolling)",
            "applicationLink": app_link or "https://simplify.jobs",
            "website": app_link or "https://simplify.jobs",
            "tags": ["internship", "simplifyjobs", "software-engineering"],
            "status": "open",
            "source": f"github-{source_name}",
        }
        opportunities.append(opportunity)

    return opportunities


# ═══════════════════════════════════════════════════════════════════
#  MARKDOWN TABLE PARSER
# ═══════════════════════════════════════════════════════════════════

def parse_markdown_table_rows(content):
    """Parse Markdown tables into list of dicts with headers."""
    rows = []
    headers = None
    in_table = False

    for line in content.split("\n"):
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            if in_table:
                in_table = False
                headers = None
            continue

        cells = [c.strip() for c in line.split("|")[1:-1]]
        if not cells:
            continue

        # Separator row
        if all(re.match(r'^[-:\s]+$', c) for c in cells):
            in_table = True
            continue

        if not in_table or headers is None:
            headers = [strip_markdown_links(c).lower() for c in cells]
            in_table = True
            continue

        if headers and len(cells) >= 2:
            row = {}
            for i, header in enumerate(headers):
                row[header] = cells[i] if i < len(cells) else ""
            row["_raw_line"] = line
            rows.append(row)

    return rows


def parse_generic_markdown_table(content, source):
    """Convert parsed markdown table rows to opportunity objects."""
    raw_rows = parse_markdown_table_rows(content)
    opportunities = []

    for row in raw_rows:
        name_raw = (
            row.get("name")
            or row.get("event")
            or row.get("program")
            or row.get("company")
            or row.get("organisation")
            or row.get("organization")
            or ""
        )
        name = strip_markdown_links(name_raw)
        
        # Filter out badge headers, image links, section dividers
        if not name or len(name) < 2:
            continue
        if name.startswith("!") or name.lower() in ("name", "event", "program", "company", "---", "month", "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"):
            continue
        if "badge" in name.lower() or "shields.io" in name.lower() or "img.shields" in name.lower():
            continue

        # Clean emojis like ⭐
        name = re.sub(r'^[⭐\s*]+', '', name).strip()
        if not name or len(name) < 2:
            continue

        link = extract_url(name_raw) or extract_url(row.get("application process", "")) or extract_url(row.get("application", "")) or extract_url(row.get("link", "")) or extract_url(row.get("_raw_line", ""))

        stipend = strip_markdown_links(row.get("stipend") or row.get("awards") or row.get("rewards") or "")
        timeline = strip_markdown_links(row.get("timeline") or row.get("deadline") or row.get("deadline (approx.)") or row.get("status 2025") or "")
        eligibility = strip_markdown_links(row.get("eligibility") or row.get("requirements") or row.get("type") or "Open to all")
        location = strip_markdown_links(row.get("location") or row.get("mode") or "Online / Remote")

        opportunity = {
            "name": name,
            "organizer": f"Via {source['name']}",
            "description": f"Open source program / mentorship: {name}",
            "eligibility": eligibility or "Open to students & developers",
            "mode": location or "Online / Remote",
            "fee": "Free",
            "stipend": stipend or "Check program page",
            "deadline": timeline or "Annual / Check page",
            "applicationLink": link or "https://github.com",
            "website": link or "https://github.com",
            "tags": ["open-source", source["category"]],
            "status": "open",
            "source": f"github-{source['name']}",
        }
        opportunities.append(opportunity)

    return opportunities


# ═══════════════════════════════════════════════════════════════════
#  MARKDOWN LIST PARSER (for OpenSauced)
# ═══════════════════════════════════════════════════════════════════

def parse_markdown_list(content, source):
    """Parse Markdown list items like '- [Name](url) - Description' or '1. [Name](url)'."""
    opportunities = []
    pattern = re.compile(r'^(?:[*-]|\d+\.)\s+\[([^\]]+)\]\((https?://[^)]*|)\)\s*(?:[-–—:]\s*(.*))?', re.MULTILINE)

    for match in pattern.finditer(content):
        name = match.group(1).strip()
        link = match.group(2).strip()
        desc = (match.group(3) or "").strip()

        if not name or len(name) < 2 or "badge" in name.lower() or "awesome" in name.lower():
            continue

        opportunity = {
            "name": name,
            "organizer": "Student / Research Organization",
            "description": desc or f"{name} fellowship / student program",
            "eligibility": "Students / Graduates (check program details)",
            "mode": "Check listing",
            "fee": "Free",
            "stipend": "Stipend / Mentorship provided",
            "deadline": "Annual / Check portal",
            "applicationLink": link or "https://github.com",
            "website": link or "https://github.com",
            "tags": ["fellowship", "student"],
            "status": "open",
            "source": f"github-{source['name']}",
        }
        opportunities.append(opportunity)

    return opportunities


# ═══════════════════════════════════════════════════════════════════
#  DIPAKKR MULTI-CATEGORY PARSER
# ═══════════════════════════════════════════════════════════════════

def parse_dipakkr_multi(content, source):
    """Parse Dipakkr's massive student resources repo into hackathons, competitions, and fellowships."""
    results = {
        "hackathons": [],
        "competitions": [],
        "fellowships": [],
    }

    # 1. Hackathons Section
    hack_match = re.search(r'# Hackathons & Competitions.*?(?=##\s*2\.2\s*Competitions|\Z)', content, re.DOTALL)
    if hack_match:
        hack_rows = parse_markdown_table_rows(hack_match.group(0))
        for row in hack_rows:
            event_raw = row.get("event") or row.get("name") or ""
            name = strip_markdown_links(event_raw)
            if not name or name.lower() in ("event", "name", "#"):
                continue
            link = extract_url(event_raw) or extract_url(row.get("_raw_line", ""))
            loc = strip_markdown_links(row.get("location") or "Online")
            dates = strip_markdown_links(row.get("event dates") or row.get("status") or "")
            results["hackathons"].append({
                "name": name,
                "organizer": "Global / Student",
                "description": f"Hackathon: {name}. Dates: {dates or 'Check listing'}",
                "eligibility": "Students & Developers",
                "mode": loc or "Online",
                "fee": "Free",
                "prize": "Prizes / Swag / Grants",
                "deadline": dates or "Check event page",
                "applicationLink": link or "https://mlh.io",
                "website": link or "https://mlh.io",
                "tags": ["hackathon", "global"],
                "status": "open",
                "source": "github-dipakkr-hackathons",
            })

    # 2. Competitions Section
    comp_match = re.search(r'##\s*2\.2\s*Competitions.*?(?=##|\n#\s|\Z)', content, re.DOTALL)
    if comp_match:
        comp_rows = parse_markdown_table_rows(comp_match.group(0))
        for row in comp_rows:
            name_raw = row.get("name") or ""
            name = strip_markdown_links(name_raw)
            if not name or name.lower() in ("name", "id", "#"):
                continue
            link = extract_url(name_raw) or extract_url(row.get("_raw_line", ""))
            loc = strip_markdown_links(row.get("location") or "Online")
            status_desc = strip_markdown_links(row.get("status 2025") or "")
            results["competitions"].append({
                "name": name,
                "organizer": "Global Competition Organizers",
                "description": f"Competitive challenge: {name}. {status_desc}",
                "eligibility": "Students & Professionals",
                "mode": loc or "Online",
                "fee": "Free",
                "prize": "Awards / Cash / Recognition",
                "deadline": "Check competition portal",
                "applicationLink": link or "https://unstop.com",
                "website": link or "https://unstop.com",
                "tags": ["competition", "coding-challenge"],
                "status": "open",
                "source": "github-dipakkr-competitions",
            })

    # 3. Student Fellowships Section
    fel_match = re.search(r'##\s*Student Fellowship Programs.*?(?=##|\n#\s|\Z)', content, re.DOTALL)
    if fel_match:
        list_items = parse_markdown_list(fel_match.group(0), source)
        for item in list_items:
            item["tags"] = ["fellowship", "student"]
            item["source"] = "github-dipakkr-fellowships"
            results["fellowships"].append(item)

    return results


# ═══════════════════════════════════════════════════════════════════
#  MAIN SCRAPER CLASS
# ═══════════════════════════════════════════════════════════════════

class GitHubRepoScraper:
    """Scrapes multiple independent curated GitHub repos in a single unified run."""

    def __init__(self):
        self.name = "GitHubRepos"
        self.category = "multi"

    def run(self):
        """Fetch and parse all configured GitHub repositories."""
        results = {}

        for source in GITHUB_SOURCES:
            source_name = source["name"]
            logger.info(f"[GitHubRepos] Fetching {source_name}...")
            content = fetch_url_robust(source["url"])

            if not content:
                logger.warning(f"[GitHubRepos] Could not fetch {source_name}, skipping")
                continue

            parser_type = source.get("parser")
            if parser_type == "simplify_html":
                opps = parse_simplify_html(content, source_name)
                cat = source["category"]
                results.setdefault(cat, []).extend(opps)
                logger.info(f"[GitHubRepos] {source_name}: parsed {len(opps)} items → {cat}")

            elif parser_type == "markdown_table":
                opps = parse_generic_markdown_table(content, source)
                cat = source["category"]
                results.setdefault(cat, []).extend(opps)
                logger.info(f"[GitHubRepos] {source_name}: parsed {len(opps)} items → {cat}")

            elif parser_type == "markdown_list":
                opps = parse_markdown_list(content, source)
                cat = source["category"]
                results.setdefault(cat, []).extend(opps)
                logger.info(f"[GitHubRepos] {source_name}: parsed {len(opps)} items → {cat}")

            elif parser_type == "dipakkr_multi":
                multi_res = parse_dipakkr_multi(content, source)
                for cat, items in multi_res.items():
                    results.setdefault(cat, []).extend(items)
                    logger.info(f"[GitHubRepos] {source_name}: parsed {len(items)} items → {cat}")

        total = sum(len(v) for v in results.values())
        logger.info(f"[GitHubRepos] ✅ Total opportunities parsed across all repos: {total}")
        return results
