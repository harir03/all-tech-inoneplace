"""
OpportunityHub — Location Classification & Geographic Policy

Why this module exists
----------------------
The dataset is India-focused, but 1,495 of 1,499 internship records carried no
`location` field at all. `github_repos_scraper.py` parsed the location column and
then wrote it into `description` and `mode` instead of emitting it, so the
structured field was silently lost. The visible symptom was a board full of
"New York, NY" roles with nothing to filter on.

Fixing the plumbing is not enough on its own, because "location" in job listings
is genuinely messy and two distinctions are easy to get wrong:

1. `IN` is Indiana, not India.
   "Indianapolis, IN" and "Bengaluru, IN" both end in the same two letters.
   Substring matching on "in"/"IN" produces confident nonsense, so state codes
   are only read in the `City, ST` positional pattern and India is matched on
   explicit names and a city gazetteer.

2. "Remote" is not one thing.
   "Remote" means work from anywhere and is useful to an Indian student.
   "Remote (US)" means you must have US work authorization and is useless.
   Collapsing both into `remote` would silently re-admit exactly the records this
   filter exists to remove, so geo-restricted remote is a distinct mode.

Modes
-----
    remote        — location-independent, no country restriction
    remote_geo    — remote but restricted to a specific country
    hybrid        — split between home and an office (physical presence required)
    onsite        — full physical presence required
    unknown       — not classifiable

Policy
------
`should_include()` applies a per-mode rule. The default policy keeps globally
remote work from anywhere, restricts anything requiring physical presence to the
home country, and KEEPS unknowns. That last choice is deliberate: silently
dropping every record we failed to parse would turn a classifier bug into
invisible data loss. Unknowns are kept and flagged so they show up in the report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# ── Modes ───────────────────────────────────────────────────────────────────
REMOTE = "remote"
REMOTE_GEO = "remote_geo"
HYBRID = "hybrid"
ONSITE = "onsite"
UNKNOWN = "unknown"

HOME_COUNTRY = "IN"

# ── Default policy ──────────────────────────────────────────────────────────
# "any"   → keep regardless of country
# "home"  → keep only when the country is the home country (or unspecified)
# "keep"  → always keep
# "drop"  → always drop
DEFAULT_POLICY: Dict[str, str] = {
    REMOTE: "any",
    REMOTE_GEO: "home",
    HYBRID: "home",
    ONSITE: "home",
    UNKNOWN: "keep",
}


# ── Vocabulary ──────────────────────────────────────────────────────────────

REMOTE_TERMS = (
    "remote", "work from home", "work-from-home", "wfh", "telecommute",
    "telework", "virtual", "anywhere", "distributed", "fully remote",
    "100% remote", "location independent", "online",
)

HYBRID_TERMS = (
    "hybrid", "partially remote", "partly remote", "flexible location",
    "remote-friendly", "remote friendly", "some remote", "blended",
)

ONSITE_TERMS = (
    "on-site", "onsite", "on site", "in-person", "in person", "in-office",
    "in office", "office-based", "office based", "at our office",
)

# Indian cities and metros, including common alternate spellings.
INDIA_CITIES: Set[str] = {
    "bangalore", "bengaluru", "blr", "hyderabad", "hyd", "secunderabad",
    "mumbai", "bombay", "navi mumbai", "thane", "pune", "pimpri",
    "delhi", "new delhi", "ncr", "noida", "greater noida", "gurgaon",
    "gurugram", "faridabad", "ghaziabad", "chennai", "madras",
    "kolkata", "calcutta", "ahmedabad", "gandhinagar", "surat", "vadodara",
    "baroda", "rajkot", "jaipur", "udaipur", "jodhpur", "kota",
    "lucknow", "kanpur", "varanasi", "prayagraj", "allahabad", "agra",
    "indore", "bhopal", "gwalior", "jabalpur", "raipur",
    "nagpur", "nashik", "aurangabad", "kolhapur", "solapur",
    "kochi", "cochin", "ernakulam", "trivandrum", "thiruvananthapuram",
    "kozhikode", "calicut", "thrissur", "kollam",
    "coimbatore", "madurai", "trichy", "tiruchirappalli", "salem",
    "vellore", "erode", "tirupur", "thanjavur",
    "visakhapatnam", "vizag", "vijayawada", "guntur", "tirupati", "nellore",
    "mysore", "mysuru", "mangalore", "mangaluru", "hubli", "belgaum",
    "chandigarh", "mohali", "ludhiana", "amritsar", "jalandhar", "patiala",
    "dehradun", "haridwar", "roorkee", "shimla",
    "bhubaneswar", "cuttack", "rourkela", "puri",
    "patna", "ranchi", "jamshedpur", "dhanbad", "bokaro",
    "guwahati", "shillong", "imphal", "agartala", "aizawl",
    "goa", "panaji", "vasco", "margao",
    "jammu", "srinagar", "leh",
    "warangal", "karimnagar", "nizamabad",
    "pilani", "kharagpur", "kanpur nagar", "manipal", "vellore institute",
}

# Indian states and union territories.
INDIA_REGIONS: Set[str] = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya",
    "mizoram", "nagaland", "odisha", "orissa", "punjab", "rajasthan",
    "sikkim", "tamil nadu", "tamilnadu", "telangana", "tripura",
    "uttar pradesh", "uttarakhand", "west bengal", "delhi ncr",
    "andaman", "nicobar", "chandigarh", "dadra", "nagar haveli", "daman",
    "diu", "lakshadweep", "puducherry", "pondicherry", "ladakh",
    "jammu and kashmir", "jammu & kashmir",
}

INDIA_NAMES = ("india", "indian", "bharat", "hindustan")

# US state codes. `IN` (Indiana) is the collision that makes naive matching fail.
US_STATE_CODES: Set[str] = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC", "PR",
}

US_STATE_NAMES: Set[str] = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
    "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia", "puerto rico",
}

US_CITIES: Set[str] = {
    "new york", "nyc", "brooklyn", "manhattan", "san francisco", "sf",
    "bay area", "palo alto", "mountain view", "sunnyvale", "san jose",
    "santa clara", "cupertino", "menlo park", "redwood city", "oakland",
    "seattle", "bellevue", "redmond", "portland", "los angeles", "la",
    "san diego", "irvine", "santa monica", "austin", "dallas", "houston",
    "san antonio", "chicago", "boston", "cambridge", "atlanta", "denver",
    "boulder", "phoenix", "tempe", "scottsdale", "miami", "orlando", "tampa",
    "philadelphia", "pittsburgh", "detroit", "ann arbor", "minneapolis",
    "st louis", "kansas city", "columbus", "cleveland", "cincinnati",
    "indianapolis", "nashville", "charlotte", "raleigh", "durham",
    "washington dc", "arlington", "mclean", "reston", "baltimore",
    "salt lake city", "las vegas", "sacramento", "fremont", "pleasanton",
    "hoboken", "jersey city", "newark", "princeton", "stamford",
}

# Other countries we may encounter. Presence of any of these implies non-India.
# Demonyms are included on purpose: listings say "Various Canadian Universities"
# far more often than they say "Canada", and matching only the noun let a
# Canada-only program through the filter unclassified.
OTHER_COUNTRIES: Dict[str, Tuple[str, ...]] = {
    "US": ("united states", "usa", "u.s.", "u.s.a", "america", "american"),
    "CA": ("canada", "canadian", "toronto", "vancouver", "montreal", "ottawa",
           "waterloo", "calgary", "edmonton", "ontario", "quebec",
           "british columbia"),
    "GB": ("united kingdom", "uk", "england", "english university", "british",
           "london", "manchester", "birmingham", "edinburgh", "glasgow",
           "cambridge uk", "oxford", "bristol", "leeds", "scotland", "wales"),
    "DE": ("germany", "german", "berlin", "munich", "münchen", "hamburg",
           "frankfurt", "stuttgart", "cologne", "deutschland"),
    "FR": ("france", "french", "paris", "lyon", "toulouse", "marseille"),
    "NL": ("netherlands", "dutch", "amsterdam", "rotterdam", "eindhoven",
           "utrecht"),
    "IE": ("ireland", "irish", "dublin", "cork", "galway"),
    "CH": ("switzerland", "swiss", "zurich", "zürich", "geneva", "lausanne"),
    "SE": ("sweden", "swedish", "stockholm", "gothenburg"),
    "PL": ("poland", "polish", "warsaw", "krakow", "kraków", "wroclaw"),
    "ES": ("spain", "spanish", "madrid", "barcelona", "valencia"),
    "IT": ("italy", "italian", "milan", "rome", "turin"),
    "SG": ("singapore", "singaporean"),
    "AE": ("dubai", "abu dhabi", "united arab emirates", "uae", "sharjah",
           "emirati"),
    "AU": ("australia", "australian", "sydney", "melbourne", "brisbane",
           "perth", "canberra"),
    "NZ": ("new zealand", "auckland", "wellington"),
    "JP": ("japan", "japanese", "tokyo", "osaka", "kyoto"),
    "KR": ("south korea", "korean", "seoul", "korea"),
    "CN": ("china", "chinese", "beijing", "shanghai", "shenzhen", "hangzhou",
           "guangzhou"),
    "HK": ("hong kong",),
    "TW": ("taiwan", "taiwanese", "taipei"),
    "IL": ("israel", "israeli", "tel aviv", "haifa", "jerusalem"),
    "BR": ("brazil", "brazilian", "sao paulo", "são paulo", "rio de janeiro"),
    "MX": ("mexico", "mexican", "mexico city", "guadalajara", "monterrey"),
    "AR": ("argentina", "argentinian", "buenos aires"),
    "ZA": ("south africa", "south african", "cape town", "johannesburg"),
    "NG": ("nigeria", "nigerian", "lagos", "abuja"),
    "KE": ("kenya", "kenyan", "nairobi"),
    "EG": ("egypt", "egyptian", "cairo"),
    "PK": ("pakistan", "pakistani", "karachi", "lahore", "islamabad"),
    "BD": ("bangladesh", "bangladeshi", "dhaka"),
    "LK": ("sri lanka", "sri lankan", "colombo"),
    "NP": ("nepal", "nepali", "kathmandu"),
    "PH": ("philippines", "filipino", "manila", "cebu"),
    "ID": ("indonesia", "indonesian", "jakarta", "bandung"),
    "MY": ("malaysia", "malaysian", "kuala lumpur", "penang"),
    "TH": ("thailand", "thai", "bangkok"),
    "VN": ("vietnam", "vietnamese", "hanoi", "ho chi minh"),
    "TR": ("turkey", "turkish", "istanbul", "ankara"),
    "RU": ("russia", "russian", "moscow", "st petersburg"),
    "UA": ("ukraine", "ukrainian", "kyiv", "kiev", "lviv"),
    "CZ": ("czech", "prague", "brno"),
    "RO": ("romania", "romanian", "bucharest", "cluj"),
    "PT": ("portugal", "portuguese", "lisbon", "porto"),
    "AT": ("austria", "austrian", "vienna"),
    "BE": ("belgium", "belgian", "brussels", "leuven"),
    "DK": ("denmark", "danish", "copenhagen"),
    "NO": ("norway", "norwegian", "oslo"),
    "FI": ("finland", "finnish", "helsinki"),
    "GR": ("greece", "greek", "athens"),
    "HU": ("hungary", "hungarian", "budapest"),
    "CL": ("chile", "chilean", "santiago"),
    "CO": ("colombia", "colombian", "bogota", "bogotá", "medellin"),
    "PE": ("peru", "peruvian", "lima"),
    "SA": ("saudi arabia", "saudi", "riyadh", "jeddah"),
    "QA": ("qatar", "qatari", "doha"),
    "CR": ("costa rica", "costa rican"),
}

# Phrases that indicate a work-authorization restriction even without a city.
AUTH_RESTRICTIONS = (
    ("US", ("us only", "u.s. only", "usa only", "us-based", "us based",
            "must be authorized to work in the united states",
            "us work authorization", "requires us citizenship",
            "green card", "eligible to work in the us", "us residents")),
    ("CA", ("canada only", "canadian residents", "must reside in canada")),
    ("GB", ("uk only", "uk-based", "uk based", "right to work in the uk")),
    ("EU", ("eu only", "eu-based", "eea", "right to work in the eu")),
)

# Multi-country / global phrasing that should NOT count as geo-restricted.
GLOBAL_TERMS = (
    "worldwide", "global", "international", "any country", "anywhere in the world",
    "no location restriction", "location agnostic", "open to all countries",
)

# Bare uppercase country codes as they appear in listing strings: "Remote (US)",
# "Remote - UK", "Hybrid | SG". Matched case-sensitively against the ORIGINAL
# text so the English pronoun "us" can never be read as the United States.
# `IN` is deliberately excluded: it is handled by the City, ST logic and the
# India gazetteer, where the Indiana ambiguity is resolved explicitly.
BARE_COUNTRY_CODES: Dict[str, str] = {
    "US": "US", "USA": "US", "U.S.": "US", "U.S.A.": "US",
    "UK": "GB", "GB": "GB", "CA": "CA", "EU": "EU", "AU": "AU", "NZ": "NZ",
    "DE": "DE", "FR": "FR", "NL": "NL", "IE": "IE", "CH": "CH", "SE": "SE",
    "PL": "PL", "ES": "ES", "IT": "IT", "PT": "PT", "AT": "AT", "BE": "BE",
    "DK": "DK", "NO": "NO", "FI": "FI", "CZ": "CZ", "RO": "RO", "HU": "HU",
    "SG": "SG", "JP": "JP", "KR": "KR", "CN": "CN", "HK": "HK", "TW": "TW",
    "AE": "AE", "SA": "SA", "QA": "QA", "IL": "IL", "TR": "TR",
    "BR": "BR", "MX": "MX", "AR": "AR", "CL": "CL", "CO": "CO", "PE": "PE",
    "ZA": "ZA", "NG": "NG", "KE": "KE", "EG": "EG",
    "PK": "PK", "BD": "BD", "LK": "LK", "NP": "NP", "PH": "PH", "ID": "ID",
    "MY": "MY", "TH": "TH", "VN": "VN", "RU": "RU", "UA": "UA",
}

# Bare codes are only trusted in a delimited position, never mid-word.
_BARE_CODE = re.compile(
    r"(?:^|[(\[\|,\-–—/]\s*|\s)(" + "|".join(
        re.escape(c) for c in sorted(BARE_COUNTRY_CODES, key=len, reverse=True)
    ) + r")(?=$|[)\]\|,\-–—/]|\s|\b)"
)

_NOISE = re.compile(r"[\u2013\u2014\u2192\u21b3>\|/\\]+")
_CITY_STATE = re.compile(r",\s*([A-Z]{2})\b")


@dataclass
class LocationInfo:
    """Structured result of classifying a free-text location."""
    raw: str = ""
    mode: str = UNKNOWN
    country: str = ""          # ISO-ish code, "" when unknown
    city: str = ""
    is_home: bool = False      # Matches HOME_COUNTRY
    is_global: bool = False    # Explicitly worldwide
    signals: List[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        """Short human-facing label, e.g. 'Remote' or 'Onsite · IN'."""
        pretty = {
            REMOTE: "Remote", REMOTE_GEO: "Remote", HYBRID: "Hybrid",
            ONSITE: "In-person", UNKNOWN: "Unspecified",
        }[self.mode]
        return f"{pretty} · {self.country}" if self.country else pretty

    def to_fields(self) -> Dict[str, str]:
        """Fields to merge onto an opportunity record."""
        out = {
            "locationMode": self.mode,
            "locationLabel": self.label,
        }
        if self.raw:
            out["location"] = self.raw
        if self.country:
            out["country"] = self.country
        return out


def classify(raw: object, extra: object = "") -> LocationInfo:
    """
    Classify a free-text location string.

    `extra` lets callers pass supporting text (title, description, eligibility)
    so a listing whose location cell is empty can still be classified from
    phrases like "Remote (US only)" appearing elsewhere.
    """
    raw_text = _clean(raw)
    extra_text = _clean(extra)

    # Two separate haystacks, and the split is load-bearing.
    #
    # geo_hay (location text only) decides WHERE the role is. Widening it to the
    # description attributes countries from prose: Mitacs Globalink says
    # "eligible countries including India" while being a Canada-only program, and
    # scanning that text marked it as Indian and exempted it from the filter.
    #
    # mode_hay (everything) decides HOW the role is worked. Remote/hybrid wording
    # and work-authorization restrictions legitimately appear outside the
    # location cell, so mode detection wants the wider text.
    geo_hay = raw_text.lower()
    mode_hay = f"{raw_text} {extra_text}".strip().lower()

    info = LocationInfo(raw=raw_text)

    if not mode_hay:
        return info

    # ── Country / city detection (location text only) ──────────────────────
    india_hit = _detect_india(geo_hay, raw_text)
    other_country, other_signal = _detect_other_country(geo_hay, raw_text)

    # "Explicitly worldwide" is likewise only meaningful about the LOCATION.
    if any(t in geo_hay for t in GLOBAL_TERMS):
        info.is_global = True
        info.signals.append("global")

    if india_hit:
        info.country = "IN"
        info.city = india_hit
        info.is_home = True
        info.signals.append(f"india:{india_hit}")
    elif other_country:
        info.country = other_country
        info.signals.append(f"country:{other_country}:{other_signal}")

    # ── Mode detection (wider text) ────────────────────────────────────────
    # Hybrid is checked before remote: "remote-friendly hybrid" is hybrid, and
    # hybrid strings very often also contain the word "remote".
    has_hybrid = any(t in mode_hay for t in HYBRID_TERMS)
    has_remote = _has_word_term(mode_hay, REMOTE_TERMS)
    has_onsite = any(t in mode_hay for t in ONSITE_TERMS)

    if has_hybrid:
        info.mode = HYBRID
        info.signals.append("hybrid")
    elif has_remote and not has_onsite:
        # A remote role tied to a specific country still requires living there.
        restricted = _detect_auth_restriction(mode_hay)
        country = restricted or (other_country if not india_hit else "")
        if info.is_global:
            info.mode = REMOTE
        elif country:
            info.mode = REMOTE_GEO
            info.country = info.country or country
            info.signals.append(f"remote_restricted:{country}")
        else:
            info.mode = REMOTE
        info.signals.append("remote")
    elif has_onsite or info.country:
        # A concrete place with no remote wording means physical presence.
        info.mode = ONSITE
        info.signals.append("onsite")
    else:
        restricted = _detect_auth_restriction(mode_hay)
        if restricted:
            info.mode = REMOTE_GEO
            info.country = info.country or restricted
            info.signals.append(f"auth:{restricted}")

    return info


def should_include(
    info: LocationInfo,
    policy: Optional[Dict[str, str]] = None,
    home_country: str = HOME_COUNTRY,
) -> Tuple[bool, str]:
    """
    Apply the geographic policy.

    Returns (keep, reason).
    """
    rules = policy or DEFAULT_POLICY
    rule = rules.get(info.mode, "keep")

    if rule == "keep":
        return True, f"{info.mode}: kept by policy"
    if rule == "drop":
        return False, f"{info.mode}: dropped by policy"
    if rule == "any":
        return True, f"{info.mode}: no geographic restriction"
    if rule == "home":
        if info.is_global:
            return True, f"{info.mode}: explicitly worldwide"
        if not info.country:
            # Requires presence somewhere but we could not tell where. Keeping it
            # is the safer error: a missing gazetteer entry should not delete a
            # legitimate local listing.
            return True, f"{info.mode}: country unknown, kept"
        if info.country == home_country:
            return True, f"{info.mode}: in {home_country}"
        return False, f"{info.mode} in {info.country}, outside {home_country}"
    return True, "no rule matched"


def classify_record(record: Dict) -> LocationInfo:
    """Classify an opportunity record using every field that may carry location."""
    raw = ""
    for key in ("location", "Location", "city"):
        val = record.get(key)
        if isinstance(val, str) and val.strip():
            raw = val.strip()
            break

    # `mode` historically held the raw location string for scraped records, so it
    # is a location source as well as a mode source.
    mode_val = record.get("mode")
    if not raw and isinstance(mode_val, str) and mode_val.strip():
        raw = mode_val.strip()

    extra_parts = [
        str(record.get("mode") or ""),
        str(record.get("eligibility") or ""),
        str(record.get("description") or ""),
        str(record.get("name") or ""),
    ]
    return classify(raw, " ".join(extra_parts))


def annotate(record: Dict) -> LocationInfo:
    """Classify and write structured location fields onto the record in place."""
    info = classify_record(record)
    record.update(info.to_fields())
    return info


# ── Internals ───────────────────────────────────────────────────────────────


def _clean(value: object) -> str:
    s = str(value or "")
    s = _NOISE.sub(" ", s)
    # Markdown table cells sometimes concatenate several locations with no
    # separator at all, e.g. "San FranciscoNew YorkLondon". Word-boundary
    # matching cannot see "new york" inside "FranciscoNew York", so split on
    # lowercase->uppercase transitions first. Harmless for real place names.
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _has_word_term(hay: str, terms: Tuple[str, ...]) -> bool:
    """Match terms on word boundaries so 'online' does not match 'onlinemart'."""
    for t in terms:
        if " " in t:
            if t in hay:
                return True
        elif re.search(rf"\b{re.escape(t)}\b", hay):
            return True
    return False


def _detect_india(hay: str, raw: str) -> str:
    """Return the matched Indian city/region/name, or ''."""
    for name in INDIA_NAMES:
        if re.search(rf"\b{name}\b", hay):
            return name
    for city in INDIA_CITIES:
        if re.search(rf"\b{re.escape(city)}\b", hay):
            return city
    for region in INDIA_REGIONS:
        if re.search(rf"\b{re.escape(region)}\b", hay):
            return region
    return ""


def _detect_other_country(hay: str, raw: str) -> Tuple[str, str]:
    """
    Return (country_code, matched_signal) for a non-India location.

    US state codes are only honoured inside the positional `City, ST` pattern.
    Reading them anywhere would turn "Bengaluru, IN" into Indiana.
    """
    for code in _CITY_STATE.findall(raw):
        if code not in US_STATE_CODES:
            continue
        if code == "IN":
            # "Bengaluru, IN" (India) vs "Fort Wayne, IN" (Indiana). Decide on
            # the city, and default to Indiana: a US-style "City, ST" string is
            # overwhelmingly more likely to be Indiana than an Indian city
            # abbreviated to its ISO code.
            city = raw.lower().split(",")[0].strip()
            if city in INDIA_CITIES or any(n in city for n in INDIA_NAMES):
                continue
            return "US", f"city_state:{city}, IN"
        return "US", f"city_state:{code}"

    for state in US_STATE_NAMES:
        if re.search(rf"\b{re.escape(state)}\b", hay):
            return "US", f"state:{state}"
    for city in US_CITIES:
        if re.search(rf"\b{re.escape(city)}\b", hay):
            return "US", f"city:{city}"

    for code, terms in OTHER_COUNTRIES.items():
        for t in terms:
            if re.search(rf"\b{re.escape(t)}\b", hay):
                return code, t

    # Bare uppercase codes, e.g. "Remote (US)" / "Hybrid - UK".
    for match in _BARE_CODE.findall(raw):
        mapped = BARE_COUNTRY_CODES.get(match)
        if mapped:
            return mapped, f"bare_code:{match}"
    return "", ""


def _detect_auth_restriction(hay: str) -> str:
    for code, phrases in AUTH_RESTRICTIONS:
        for p in phrases:
            if p in hay:
                return code
    return ""


def summarize(infos: List[LocationInfo]) -> Dict[str, int]:
    """Counts by mode, for the pipeline report."""
    out: Dict[str, int] = {}
    for i in infos:
        out[i.mode] = out.get(i.mode, 0) + 1
    return out
