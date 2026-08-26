"""
OpportunityHub — Data Verification Gate
Production-grade second-layer validation that sits between scraping and persistence.

Architecture:
    Scrapers → raw items → VerificationGate.verify_batch() → verified items → merge → save

Each incoming item passes through independent verification checks:
    1. Schema Validation      — required fields present, well-formed
    2. URL Liveness           — HEAD probe confirms link responds (not 404/5xx/dead domain)
    3. Date Sanity            — deadline not in the past, not >2 years out, parseable
    4. Content Cross-Check    — fetches target page, confirms it mentions the opportunity
    5. Spam/Scam Detection    — flags crypto scams, MLM, "guaranteed income" patterns
    6. Fuzzy Duplicate Guard  — catches near-duplicate titles that exact dedup misses

Items get a composite verification_score (0.0 - 1.0).
Items below REJECT_THRESHOLD are dropped with a logged reason.
Items between REJECT and WARN thresholds are accepted but flagged.
"""

import logging
import re
import urllib.request
import urllib.parse
from typing import List, Dict, Tuple, Optional
from datetime import date, datetime, timedelta

logger = logging.getLogger("opportunityhub.verification")

# ── Thresholds ──────────────────────────────────────────────────────────────
REJECT_THRESHOLD = 0.30   # Below this → item is dropped
WARN_THRESHOLD = 0.60     # Below this → item is accepted but flagged
URL_TIMEOUT = 5           # Seconds for HEAD/GET probes
MAX_URLS_TO_PROBE = 20    # Cap live URL checks per gate instance to keep pipeline fast


# ── Check Weights (must sum to 1.0) ────────────────────────────────────────
WEIGHTS = {
    "schema":       0.25,
    "url":          0.20,
    "date":         0.15,
    "content":      0.15,
    "spam":         0.15,
    "fuzzy_dedup":  0.10,
}


class VerificationGate:
    """
    Stateless verification engine. Instantiate once per pipeline run,
    call verify_batch() with scraped items, get back only verified items.
    """

    def __init__(self, existing_items: Optional[List[Dict]] = None):
        """
        Args:
            existing_items: Items already in the data file, used for fuzzy dedup.
        """
        self.existing_titles = set()
        if existing_items:
            for item in existing_items:
                normalized = self._normalize_for_fuzzy(item.get("name", ""))
                if normalized:
                    self.existing_titles.add(normalized)

        self._url_probe_count = 0
        self._stats = {"total": 0, "accepted": 0, "warned": 0, "rejected": 0}

    # ── Public API ──────────────────────────────────────────────────────────

    def verify_batch(self, items: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        Verify a batch of scraped items.

        Returns:
            (accepted_items, rejected_items)
        """
        accepted = []
        rejected = []

        for item in items:
            self._stats["total"] += 1
            score, reasons = self._verify_single(item)

            item["_verification_score"] = round(score, 3)

            if score < REJECT_THRESHOLD:
                item["_rejection_reasons"] = reasons
                rejected.append(item)
                self._stats["rejected"] += 1
                logger.debug(
                    f"[Verify] REJECTED ({score:.2f}): {item.get('name', '?')[:60]} — {', '.join(reasons)}"
                )
            else:
                if score < WARN_THRESHOLD:
                    item["_verification_warnings"] = reasons
                    self._stats["warned"] += 1
                    logger.debug(
                        f"[Verify] WARNING ({score:.2f}): {item.get('name', '?')[:60]} — {', '.join(reasons)}"
                    )
                accepted.append(item)
                self._stats["accepted"] += 1

                # Track title for intra-batch fuzzy dedup
                normalized = self._normalize_for_fuzzy(item.get("name", ""))
                if normalized:
                    self.existing_titles.add(normalized)

        if self._stats["rejected"] > 0:
            logger.info(
                f"[Verify] Gate results: {self._stats['accepted']} accepted, "
                f"{self._stats['warned']} warned, {self._stats['rejected']} rejected "
                f"out of {self._stats['total']} total"
            )

        return accepted, rejected

    # ── Individual Checks ───────────────────────────────────────────────────

    def _verify_single(self, item: Dict) -> Tuple[float, List[str]]:
        """Run all checks on a single item, return (score, failure_reasons)."""
        scores = {}
        reasons = []

        # 1. Schema validation
        s, r = self._check_schema(item)
        scores["schema"] = s
        if r:
            reasons.append(r)

        # 2. URL liveness (capped per batch)
        s, r = self._check_url(item)
        scores["url"] = s
        if r:
            reasons.append(r)

        # 3. Date sanity
        s, r = self._check_date(item)
        scores["date"] = s
        if r:
            reasons.append(r)

        # 4. Content cross-check (only for items that passed URL check)
        if scores["url"] >= 0.5:
            s, r = self._check_content(item)
        else:
            s = 0.5  # Neutral if we can't fetch
        scores["content"] = s
        if r:
            reasons.append(r)

        # 5. Spam/scam detection
        s, r = self._check_spam(item)
        scores["spam"] = s
        if r:
            reasons.append(r)

        # 6. Fuzzy duplicate guard
        s, r = self._check_fuzzy_dedup(item)
        scores["fuzzy_dedup"] = s
        if r:
            reasons.append(r)

        # Weighted composite score
        composite = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)

        # Hard vetoes: certain checks override the composite when they're certain
        # Spam score of 0.0 means hard spam patterns detected — force reject
        if scores["spam"] == 0.0:
            composite = min(composite, 0.15)
        # Fuzzy dedup score of 0.0 means near-exact duplicate — force reject
        if scores["fuzzy_dedup"] == 0.0:
            composite = min(composite, 0.10)
        # Past deadline with certainty — force reject
        if scores["date"] == 0.0:
            composite = min(composite, 0.20)

        return composite, reasons

    def _check_schema(self, item: Dict) -> Tuple[float, Optional[str]]:
        """Verify required fields are present and well-formed."""
        required = ["name"]
        preferred = ["applicationLink", "deadline", "source"]
        bonus = ["prize", "organizer", "description", "tags"]

        score = 0.0
        missing = []

        # Required fields (binary pass/fail)
        for field in required:
            val = item.get(field, "")
            if val and isinstance(val, str) and len(val.strip()) >= 3:
                score += 0.4
            else:
                missing.append(field)

        # Preferred fields
        for field in preferred:
            val = item.get(field, "")
            if val and isinstance(val, str) and len(val.strip()) >= 3:
                score += 0.15

        # Bonus fields
        for field in bonus:
            val = item.get(field)
            if val and ((isinstance(val, str) and len(val.strip()) >= 2) or isinstance(val, list)):
                score += 0.025

        score = min(1.0, score)
        reason = f"missing required fields: {missing}" if missing else None
        return score, reason

    def _check_url(self, item: Dict) -> Tuple[float, Optional[str]]:
        """HEAD-probe the application link to verify it's live."""
        url = item.get("applicationLink", "") or item.get("url", "") or item.get("website", "")
        if not url or not url.startswith("http"):
            return 0.3, "no valid URL"

        # Cap total URL probes to keep pipeline fast
        if self._url_probe_count >= MAX_URLS_TO_PROBE:
            return 0.7, None  # Assume OK after cap

        self._url_probe_count += 1

        try:
            req = urllib.request.Request(
                url,
                method="HEAD",
                headers={"User-Agent": "Mozilla/5.0 (compatible; OpportunityHub-Verify/2.0)"}
            )
            with urllib.request.urlopen(req, timeout=URL_TIMEOUT) as resp:
                if resp.status < 400:
                    return 1.0, None
                else:
                    return 0.2, f"URL returned HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            if e.code == 405:
                # HEAD not allowed — try GET
                try:
                    req2 = urllib.request.Request(
                        url,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; OpportunityHub-Verify/2.0)"}
                    )
                    with urllib.request.urlopen(req2, timeout=URL_TIMEOUT) as resp:
                        return (1.0, None) if resp.status < 400 else (0.2, f"URL returned HTTP {resp.status}")
                except Exception:
                    return 0.4, "URL reachable but returned error"
            elif e.code in (403, 401):
                # Auth-gated — URL exists, just protected
                return 0.7, None
            else:
                return 0.2, f"URL returned HTTP {e.code}"
        except Exception as e:
            return 0.2, f"URL unreachable: {type(e).__name__}"

    def _check_date(self, item: Dict) -> Tuple[float, Optional[str]]:
        """Verify deadlines are sane — not in the past, not absurdly far out."""
        deadline_str = item.get("deadline", "")
        if not deadline_str:
            return 0.5, None  # Neutral if no deadline

        s = deadline_str.lower().strip()
        today = date.today()

        # Non-date strings get a neutral pass
        if any(k in s for k in ["rolling", "annual", "check", "tbd", "tba", "various", "open", "ongoing"]):
            return 0.8, None

        # Try to parse a real date
        try:
            # Handle date ranges — take the end date
            parts = re.split(r'\s+[-–—]\s+|\s+to\s+|[–—]', deadline_str)
            end_part = parts[-1].strip()

            # Try ISO format first
            if re.match(r'^\d{4}-\d{2}-\d{2}$', end_part):
                from dateutil.parser import parse as parse_date
                dt = parse_date(end_part).date()
            else:
                from dateutil.parser import parse as parse_date
                dt = parse_date(end_part, fuzzy=True).date()

            if dt < today:
                return 0.0, f"deadline is in the past ({dt.isoformat()})"
            elif dt > today + timedelta(days=730):
                return 0.3, f"deadline is >2 years out ({dt.isoformat()})"
            else:
                return 1.0, None
        except Exception:
            # Unparseable — check for past years
            years = [int(y) for y in re.findall(r'\b(20[0-9]{2})\b', deadline_str)]
            if years and max(years) < today.year:
                return 0.1, f"deadline mentions past year ({max(years)})"
            return 0.5, None  # Neutral if we can't parse

    def _check_content(self, item: Dict) -> Tuple[float, Optional[str]]:
        """Lightweight content cross-check: does the target page mention the opportunity?"""
        url = item.get("applicationLink", "") or item.get("url", "")
        name = item.get("name", "")

        if not url or not name or not url.startswith("http"):
            return 0.5, None

        # Only cross-check a subset to keep pipeline fast
        if self._url_probe_count >= MAX_URLS_TO_PROBE:
            return 0.7, None

        # Extract key terms from the name for matching
        name_words = set(re.findall(r'\b[a-zA-Z]{4,}\b', name.lower()))
        # Remove generic words
        name_words -= {"hackathon", "challenge", "competition", "internship", "program",
                       "summer", "winter", "online", "virtual", "free", "open", "tech",
                       "software", "engineer", "intern", "https", "http", "with", "from"}

        if len(name_words) < 2:
            return 0.6, None  # Not enough unique words to cross-check

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=URL_TIMEOUT) as resp:
                # Read only first 10KB to stay fast
                page_text = resp.read(10240).decode("utf-8", errors="ignore").lower()

            # Check if at least 1 distinctive word from the title appears on the page
            hits = sum(1 for w in name_words if w in page_text)
            if hits >= 1:
                return 1.0, None
            else:
                return 0.3, f"target page doesn't mention key terms from title"
        except Exception:
            return 0.5, None  # Neutral on network failure

    def _check_spam(self, item: Dict) -> Tuple[float, Optional[str]]:
        """Detect spam, scam, and low-quality patterns."""
        text = f"{item.get('name', '')} {item.get('description', '')} {item.get('prize', '')}".lower()

        # Hard spam/scam signals → immediate reject
        hard_spam = [
            "guaranteed income", "guaranteed earning", "earn from home",
            "network marketing", "mlm", "pyramid scheme",
            "crypto airdrop", "free bitcoin", "nft drop", "web3 airdrop",
            "whatsapp group", "telegram group join",
            "click here to claim", "you have been selected",
            "no experience needed earn", "work from home earn",
        ]
        if any(s in text for s in hard_spam):
            return 0.0, "spam/scam pattern detected"

        # Soft spam signals → score penalty
        soft_spam = [
            "💰💰💰", "🔥🔥🔥", "!!!!", "earn money fast",
            "too good to be true", "limited spots act now",
            "referral bonus", "refer and earn",
        ]
        penalties = sum(0.15 for s in soft_spam if s in text)
        score = max(0.0, 1.0 - penalties)

        # Title quality: all caps or too short
        name = item.get("name", "")
        if name and name == name.upper() and len(name) > 10:
            score -= 0.2
        if name and len(name.strip()) < 5:
            score -= 0.3

        score = max(0.0, min(1.0, score))
        reason = "soft spam signals" if score < 0.7 else None
        return score, reason

    def _check_fuzzy_dedup(self, item: Dict) -> Tuple[float, Optional[str]]:
        """Catch near-duplicate titles using token overlap similarity."""
        name = item.get("name", "")
        normalized = self._normalize_for_fuzzy(name)
        if not normalized or len(normalized) < 5:
            return 0.5, None

        # Check against existing titles
        for existing in self.existing_titles:
            similarity = self._token_similarity(normalized, existing)
            if similarity >= 0.85:
                return 0.0, f"fuzzy duplicate of existing item (similarity={similarity:.2f})"

        return 1.0, None

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_for_fuzzy(text: str) -> str:
        """Normalize text for fuzzy comparison."""
        if not text:
            return ""
        # Strip emojis, special chars, extra whitespace, lowercase
        clean = re.sub(r'[^\w\s]', '', text).lower().strip()
        return re.sub(r'\s+', ' ', clean)

    @staticmethod
    def _token_similarity(a: str, b: str) -> float:
        """Token-level Jaccard similarity between two normalized strings."""
        tokens_a = set(a.split())
        tokens_b = set(b.split())
        # Remove very common words that inflate similarity
        stopwords = {"the", "a", "an", "of", "for", "and", "in", "to", "is", "on", "at", "by"}
        tokens_a -= stopwords
        tokens_b -= stopwords
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b
        return len(intersection) / len(union)

    def get_stats(self) -> Dict:
        """Return verification statistics for the pipeline report."""
        return dict(self._stats)
