"""
OpportunityHub — Layer 2: Evidence-Based Adjudication

Layer 1 (`verification.py`) is a *plausibility* filter. It scores an item from
its own fields and averages six heuristics together. That is useful but it has a
structural blind spot: it can never tell you whether a claim is **true**, only
whether it *looks* well-formed. A scraper whose CSS selector drifted one <div>
to the left produces records that are perfectly plausible and completely wrong.

Layer 2 closes that gap with three ideas Layer 1 does not have:

  1. CLAIM vs EVIDENCE RECONCILIATION
     Every field the scraper asserts (title, deadline, event date, status) is
     compared against facts independently extracted from the opportunity's own
     page (`evidence.py`). Disagreement is actionable: we either correct the
     record from the publisher's own metadata, or drop it.

  2. HARD GATES INSTEAD OF A WEIGHTED MEAN
     A weighted average lets a bad record buy its way past the threshold by
     filling in optional fields. Layer 2 uses *necessary conditions*: a
     contradiction backed by strong evidence is fatal no matter how good the
     rest of the record looks.

  3. TRUST-WEIGHTED CORROBORATION + QUARANTINE
     An anonymous Reddit post and MLH's official event feed are not equally
     credible. Low-trust, unproven claims are not silently dropped (which loses
     real opportunities) nor blindly accepted (which admits noise) — they are
     QUARANTINED and re-examined on later runs, and promoted once an independent
     source corroborates them.

Verdicts:
    ACCEPT      — safe to persist (possibly with auto-corrections applied)
    QUARANTINE  — unproven; hold out of the dataset, retry next run
    REJECT      — actively disproven, dead, or already closed

Degradation contract:
    If the network is unavailable (circuit breaker tripped / budget exhausted),
    Layer 2 must never manufacture contradictions. It falls back to
    internal-consistency checks, which need no network and still catch real
    corruption such as `status: closed` on a record whose dates are in the future.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .evidence import EV_JSONLD, EV_OG, Evidence, EvidenceCollector

logger = logging.getLogger("opportunityhub.adjudication")


# ── Verdicts & severities ───────────────────────────────────────────────────
ACCEPT = "accept"
QUARANTINE = "quarantine"
REJECT = "reject"

CONTRADICTION = "contradiction"   # Evidence disproves the claim — fatal
SUSPICION = "suspicion"           # Something is off — accumulates
INFO = "info"                     # Recorded for audit only


# ── Tunables ────────────────────────────────────────────────────────────────
# Distinct-source count at which an unproven claim is believed anyway.
CORROBORATION_QUORUM = 2

# Source trust at/above which an unproven claim is accepted without corroboration.
TRUST_AUTOPASS = 0.75

# Suspicions needed to force a quarantine even with no hard contradiction.
SUSPICION_QUARANTINE_LIMIT = 3

# A claimed deadline more than this many days AFTER the publisher's own end date
# is treated as fabricated rather than as a rounding difference.
DEADLINE_OVERSHOOT_DAYS = 30

# Claimed vs published event-date drift tolerated before calling it a mismatch.
EVENT_DATE_DRIFT_DAYS = 45

# Title similarity below which a strongly-evidenced page is "a different thing".
TITLE_MISMATCH_HARD = 0.15
TITLE_MISMATCH_SOFT = 0.34

# Words too generic to prove a title matches a page.
GENERIC_TOKENS = {
    "hackathon", "hackathons", "challenge", "challenges", "competition",
    "competitions", "internship", "internships", "program", "programme",
    "fellowship", "job", "jobs", "role", "career", "careers", "apply",
    "application", "applications", "online", "virtual", "hybrid", "remote",
    "global", "international", "national", "annual", "season", "edition",
    "summer", "winter", "spring", "fall", "autumn", "the", "and", "for",
    "with", "from", "your", "you", "all", "new", "open", "free", "tech",
    "technology", "software", "engineer", "engineering", "developer", "intern",
    "student", "students", "university", "college", "contest", "event",
    "hiring", "recruit", "recruitment", "official", "site", "home", "page",
    "register", "registration", "grand", "india", "world",
}

# Source trust tiers. Longest matching prefix wins.
#   0.90+ official first-party API / feed
#   0.75  first-party site scrape or named company page
#   0.60  curated third-party aggregation (awesome-lists etc.)
#   0.35  social chatter — must be corroborated
SOURCE_TRUST: Dict[str, float] = {
    "devpost-live-api": 0.95,
    "mlh-live-events": 0.95,
    "codeforces": 0.95,
    "leetcode": 0.90,
    "kontests": 0.85,
    "hackerearth": 0.80,
    "devfolio": 0.80,
    "unstop": 0.80,
    "internshala": 0.75,
    "jobspy": 0.70,
    "company:": 0.80,
    "github-": 0.60,
    "opensource": 0.60,
    "gsoc": 0.85,
    # Agent Reach channels. An RSS feed is publisher-authored and structured, so
    # it earns real trust. Text scraped off a listing page is a heuristic guess
    # and deliberately does not — it must be corroborated or it gets quarantined.
    "reach:rss:": 0.80,
    "reach:news:": 0.45,
    "reach:web:": 0.40,
    "reach:search:": 0.30,
    "reddit:": 0.35,
    "reddit": 0.35,
    "twitter": 0.30,
    "x:": 0.30,
    "reel": 0.25,
    "instagram": 0.25,
}
DEFAULT_TRUST = 0.50

_ISO = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*$")
_NON_DATE_TOKENS = (
    "rolling", "annual", "various", "check", "tbd", "tba", "asap",
    "ongoing", "continuous", "always", "anytime", "quarterly", "monthly",
)


@dataclass
class Finding:
    """A single reconciliation result."""
    code: str
    severity: str
    detail: str
    correction: Optional[Tuple[str, Any]] = None   # (field, new_value)

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass
class Adjudication:
    """Full Layer 2 outcome for one item."""
    verdict: str
    findings: List[Finding] = field(default_factory=list)
    corrections: Dict[str, Any] = field(default_factory=dict)
    trust: float = DEFAULT_TRUST
    corroboration: int = 1
    evidence_kind: str = "none"
    evidence_hash: str = ""
    reasons: List[str] = field(default_factory=list)

    @property
    def contradictions(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == CONTRADICTION]

    @property
    def suspicions(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == SUSPICION]


class Adjudicator:
    """
    Layer 2 gate. Construct once per pipeline run with the full corpus so
    cross-source corroboration can be computed, then call `adjudicate_batch`
    per category.
    """

    def __init__(
        self,
        collector: Optional[EvidenceCollector] = None,
        corroboration_index: Optional[Dict[str, set]] = None,
        today: Optional[date] = None,
    ):
        self.collector = collector or EvidenceCollector()
        self.corroboration_index = corroboration_index or {}
        self.today = today or date.today()
        self.stats = {
            "total": 0, "accepted": 0, "quarantined": 0, "rejected": 0,
            "corrected": 0, "contradictions": 0, "unproven": 0,
        }

    # ── Corroboration index ────────────────────────────────────────────────

    @staticmethod
    def build_corroboration_index(*item_groups: Iterable[Dict]) -> Dict[str, set]:
        """
        Map normalized-title -> set of distinct sources asserting it.

        Built from every candidate in the run PLUS the existing dataset, so an
        item already independently confirmed keeps its corroboration on reruns.
        """
        index: Dict[str, set] = {}
        for group in item_groups:
            for item in group or []:
                key = _title_key(item.get("name", ""))
                if not key:
                    continue
                src = _source_family(item.get("source", "") or "unknown")
                index.setdefault(key, set()).add(src)
        return index

    # ── Public API ─────────────────────────────────────────────────────────

    def adjudicate_batch(
        self, items: List[Dict]
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """
        Returns (accepted, quarantined, rejected).

        Accepted items are mutated in place: auto-corrections are applied and a
        `_provenance` block is attached for auditability.
        """
        accepted: List[Dict] = []
        quarantined: List[Dict] = []
        rejected: List[Dict] = []

        for item in items:
            self.stats["total"] += 1
            result = self.adjudicate(item)

            self._stamp(item, result)

            if result.verdict == REJECT:
                self.stats["rejected"] += 1
                rejected.append(item)
                logger.debug(
                    "[L2] REJECT %s — %s",
                    str(item.get("name", "?"))[:60], "; ".join(result.reasons) or "n/a",
                )
            elif result.verdict == QUARANTINE:
                self.stats["quarantined"] += 1
                quarantined.append(item)
                logger.debug(
                    "[L2] QUARANTINE %s — %s",
                    str(item.get("name", "?"))[:60], "; ".join(result.reasons) or "n/a",
                )
            else:
                self.stats["accepted"] += 1
                accepted.append(item)

        return accepted, quarantined, rejected

    def adjudicate(self, item: Dict) -> Adjudication:
        """Reconcile one item against independent evidence."""
        trust = source_trust(item.get("source", ""))
        corroboration = self._corroboration_for(item)

        url = _primary_url(item)
        evidence = self.collector.collect(url) if url else Evidence(url="", error="no_url")

        findings: List[Finding] = []

        # Checks that need no network — these still run when offline.
        findings += self._check_internal_consistency(item)

        # Checks that reconcile against the publisher's own page.
        if evidence.ok:
            findings += self._check_link_integrity(item, evidence)
            findings += self._check_title_agreement(item, evidence)
            findings += self._check_date_agreement(item, evidence)
            findings += self._check_closure(item, evidence)
        else:
            findings += self._check_unreachable(item, evidence)

        result = Adjudication(
            verdict=ACCEPT,
            findings=findings,
            trust=trust,
            corroboration=corroboration,
            evidence_kind=evidence.kind if evidence.ok else "none",
            evidence_hash=evidence.content_hash,
        )
        self._decide(result, item, evidence)
        return result

    # ── Decision policy (ordered hard gates) ───────────────────────────────

    def _decide(self, result: Adjudication, item: Dict, evidence: Evidence) -> None:
        # Collect corrections from findings.
        for f in result.findings:
            if f.correction:
                result.corrections[f.correction[0]] = f.correction[1]

        contradictions = result.contradictions
        if contradictions:
            self.stats["contradictions"] += len(contradictions)

        # GATE 1 — a contradiction backed by evidence is fatal. No amount of
        # well-formed optional fields can buy past this.
        if contradictions:
            result.verdict = REJECT
            result.reasons = [str(f) for f in contradictions]
            return

        # GATE 2 — never ADD an opportunity that is already over. Correcting the
        # status to "closed" is right for records already in the dataset, but a
        # brand-new dead entry is pure noise.
        if str(result.corrections.get("status", "")) == "closed":
            result.verdict = REJECT
            result.reasons = ["already closed at time of discovery"]
            return

        # GATE 3 — unproven claims are judged by trust and corroboration.
        if not evidence.ok or evidence.kind == "none":
            self.stats["unproven"] += 1
            trusted = result.trust >= TRUST_AUTOPASS
            quorate = result.corroboration >= CORROBORATION_QUORUM
            if trusted or quorate:
                result.verdict = ACCEPT
                result.reasons = [
                    f"unproven but {'trusted source' if trusted else 'corroborated'} "
                    f"(trust={result.trust:.2f}, sources={result.corroboration})"
                ]
            else:
                result.verdict = QUARANTINE
                result.reasons = [
                    f"no evidence ({evidence.error or 'none'}), low trust "
                    f"(trust={result.trust:.2f}, sources={result.corroboration})"
                ]
            return

        # GATE 4 — accumulated soft signals.
        if len(result.suspicions) >= SUSPICION_QUARANTINE_LIMIT:
            result.verdict = QUARANTINE
            result.reasons = [str(f) for f in result.suspicions]
            return

        result.verdict = ACCEPT
        result.reasons = [str(f) for f in result.suspicions] or ["corroborated by publisher metadata"]

    # ── Individual reconciliations ─────────────────────────────────────────

    def _check_internal_consistency(self, item: Dict) -> List[Finding]:
        """
        Self-contradiction checks. No network required.

        Catches real corruption already present in this dataset, e.g. a record
        with a future deadline AND a future event date but `status: "closed"`.
        """
        out: List[Finding] = []
        status = str(item.get("status", "") or "").strip().lower()
        deadline = _parse_claimed_date(item.get("deadline", ""))
        event_date = _parse_claimed_date(item.get("eventDate", ""))

        # Open but the deadline already passed -> correct to closed.
        if status == "open" and deadline and deadline < self.today:
            out.append(Finding(
                "stale_open_status", SUSPICION,
                f"status=open but deadline {deadline.isoformat()} already passed",
                correction=("status", "closed"),
            ))

        # Closed while every date is still in the future -> status is wrong.
        if status == "closed":
            future_dates = [d for d in (deadline, event_date) if d and d > self.today]
            if future_dates and len(future_dates) == len([d for d in (deadline, event_date) if d]):
                out.append(Finding(
                    "contradictory_closed_status", SUSPICION,
                    "status=closed but all dates are in the future "
                    f"({', '.join(d.isoformat() for d in future_dates)})",
                ))

        # Registration deadline long after the event itself.
        if deadline and event_date and deadline > event_date + timedelta(days=DEADLINE_OVERSHOOT_DAYS):
            out.append(Finding(
                "deadline_after_event", SUSPICION,
                f"deadline {deadline.isoformat()} is well after eventDate {event_date.isoformat()}",
            ))

        # Placeholder leakage from a broken parse.
        for fld in ("name", "deadline", "applicationLink"):
            val = str(item.get(fld, "") or "").strip().lower()
            if val in ("n/a", "na", "none", "null", "tbd", "-", "undefined", "nan"):
                out.append(Finding(
                    "placeholder_field", SUSPICION, f"{fld} is a placeholder ({val!r})",
                ))

        # Link/website domain disagreement is worth recording but not acting on.
        a, b = _domain(item.get("applicationLink", "")), _domain(item.get("website", ""))
        if a and b and a != b:
            out.append(Finding(
                "link_domain_split", INFO, f"applicationLink({a}) != website({b})",
            ))

        return out

    def _check_link_integrity(self, item: Dict, ev: Evidence) -> List[Finding]:
        """Is the link still the thing it claims to be?"""
        out: List[Finding] = []

        if ev.rot_signals:
            out.append(Finding(
                "link_rot", CONTRADICTION,
                f"target page looks dead ({', '.join(ev.rot_signals[:2])})",
            ))
            return out

        claimed, final = item.get("applicationLink", "") or "", ev.final_url or ""
        if claimed and final:
            cd, fd = _domain(claimed), _domain(final)
            claimed_depth = len([p for p in _path(claimed).split("/") if p])
            final_depth = len([p for p in _path(final).split("/") if p])

            # A deep link that lands on the site root is the classic signature of
            # a removed listing.
            if cd == fd and claimed_depth >= 2 and final_depth == 0:
                out.append(Finding(
                    "redirect_to_root", SUSPICION,
                    f"deep link redirected to site root ({final})",
                ))
            elif cd and fd and cd != fd:
                out.append(Finding(
                    "cross_domain_redirect", SUSPICION,
                    f"redirected off-domain: {cd} -> {fd}",
                ))
        return out

    def _check_title_agreement(self, item: Dict, ev: Evidence) -> List[Finding]:
        """Does the page actually describe the opportunity we claim it does?"""
        claimed = str(item.get("name", "") or "")
        claim_tokens = _distinctive_tokens(claimed)
        if len(claim_tokens) < 2 or not ev.titles:
            return []

        haystacks = ev.titles + [ev.description, ev.site_name, ev.organizer]
        best = max(
            (_containment(claim_tokens, _distinctive_tokens(h)) for h in haystacks if h),
            default=0.0,
        )

        if best >= TITLE_MISMATCH_SOFT:
            return []

        # Only strong (publisher-authored) evidence may veto a title. HTML-only
        # scrapes are too often JS-rendered shells to be trusted for this.
        if best < TITLE_MISMATCH_HARD and ev.kind in (EV_JSONLD, EV_OG):
            return [Finding(
                "title_mismatch", CONTRADICTION,
                f"page describes something else (overlap={best:.2f}, "
                f"page={ev.titles[0][:60]!r})",
            )]
        return [Finding(
            "weak_title_match", SUSPICION,
            f"low title overlap with page (overlap={best:.2f})",
        )]

    def _check_date_agreement(self, item: Dict, ev: Evidence) -> List[Finding]:
        """Reconcile claimed dates against the publisher's own structured dates."""
        out: List[Finding] = []
        pub_end = ev.effective_end
        claimed_deadline = _parse_claimed_date(item.get("deadline", ""))
        claimed_event = _parse_claimed_date(item.get("eventDate", ""))

        # The publisher says it is over. This overrides any scraper claim.
        if pub_end and pub_end < self.today:
            out.append(Finding(
                "publisher_says_ended", SUSPICION,
                f"publisher end date {pub_end.isoformat()} is in the past",
                correction=("status", "closed"),
            ))

        # Claimed registration deadline sits well past the publisher's end date.
        if pub_end and claimed_deadline and claimed_deadline > pub_end + timedelta(days=DEADLINE_OVERSHOOT_DAYS):
            out.append(Finding(
                "deadline_overshoots_publisher", CONTRADICTION,
                f"claimed deadline {claimed_deadline.isoformat()} is after publisher "
                f"end {pub_end.isoformat()}",
                correction=("deadline", pub_end.isoformat()),
            ))

        # Claimed event date drifted from the published start date.
        if ev.start_date and claimed_event:
            drift = abs((claimed_event - ev.start_date).days)
            if drift > EVENT_DATE_DRIFT_DAYS:
                out.append(Finding(
                    "event_date_drift", CONTRADICTION,
                    f"claimed eventDate {claimed_event.isoformat()} vs published "
                    f"{ev.start_date.isoformat()} ({drift}d drift)",
                    correction=("eventDate", ev.start_date.isoformat()),
                ))

        # Publisher has dates, we have none -> fill them in.
        if ev.start_date and not claimed_event:
            out.append(Finding(
                "event_date_enriched", INFO,
                f"adopted publisher start date {ev.start_date.isoformat()}",
                correction=("eventDate", ev.start_date.isoformat()),
            ))
        if pub_end and not claimed_deadline and not str(item.get("deadline", "")).strip():
            out.append(Finding(
                "deadline_enriched", INFO,
                f"adopted publisher end date {pub_end.isoformat()}",
                correction=("deadline", pub_end.isoformat()),
            ))

        return out

    def _check_closure(self, item: Dict, ev: Evidence) -> List[Finding]:
        """Page explicitly says registration is shut."""
        if not ev.closed_signals:
            return []
        status = str(item.get("status", "") or "").lower()
        if status == "closed":
            return [Finding("closure_confirmed", INFO, "page confirms closed status")]
        return [Finding(
            "closure_detected", SUSPICION,
            f"page states {ev.closed_signals[0]!r} but record says {status or 'unknown'}",
            correction=("status", "closed"),
        )]

    def _check_unreachable(self, item: Dict, ev: Evidence) -> List[Finding]:
        """
        No evidence obtained. Distinguish "we could not look" from "it is gone".
        Only a definitive 404/410 counts against the item; timeouts, bot-walls
        and budget exhaustion must not.
        """
        err = ev.error or "unknown"
        if err in ("http_404", "http_410"):
            return [Finding("dead_link", CONTRADICTION, f"link returns {err.split('_')[1]}")]
        if err.startswith("blocked_"):
            return [Finding("bot_walled", INFO, f"page not readable ({err})")]
        if err.startswith("challenge_page"):
            # A CAPTCHA/bot-check interstitial. We learned nothing about the
            # opportunity, so this must stay INFO. Treating it as a signal would
            # reject valid records for failing to match a security-check title.
            return [Finding("bot_challenge", INFO, f"anti-bot interstitial ({err})")]
        if err in ("network_down", "budget_exhausted", "disabled", "read_cap_reached"):
            return [Finding("not_checked", INFO, f"evidence skipped ({err})")]
        if err == "no_url" or err == "invalid_url":
            return [Finding("no_verifiable_url", SUSPICION, "no usable URL to verify against")]
        if err.startswith("http_5"):
            return [Finding("server_error", SUSPICION, f"publisher server error ({err})")]
        return [Finding("unreachable", SUSPICION, f"could not fetch evidence ({err})")]

    # ── Helpers ────────────────────────────────────────────────────────────

    def _corroboration_for(self, item: Dict) -> int:
        key = _title_key(item.get("name", ""))
        if not key:
            return 1
        return max(1, len(self.corroboration_index.get(key, {"unknown"})))

    def _stamp(self, item: Dict, result: Adjudication) -> None:
        """Apply corrections and attach an audit trail."""
        applied: Dict[str, Any] = {}
        if result.verdict == ACCEPT:
            for fld, val in result.corrections.items():
                old = item.get(fld)
                if old != val:
                    item[fld] = val
                    applied[fld] = {"from": old, "to": val}
            if applied:
                self.stats["corrected"] += 1

        item["_adjudication"] = {
            "verdict": result.verdict,
            "trust": round(result.trust, 2),
            "corroboration": result.corroboration,
            "evidence": result.evidence_kind,
            "evidence_hash": result.evidence_hash,
            "checked_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "findings": [
                {"code": f.code, "severity": f.severity, "detail": f.detail}
                for f in result.findings
            ],
            "corrections": applied,
        }
        if result.verdict != ACCEPT:
            item["_adjudication"]["reasons"] = result.reasons

    def get_stats(self) -> Dict[str, Any]:
        return {**self.stats, "evidence": self.collector.get_stats()}


# ── Module-level helpers ────────────────────────────────────────────────────


def source_trust(source: str) -> float:
    """Trust score for a source string, longest matching prefix wins."""
    s = str(source or "").strip().lower()
    if not s:
        return DEFAULT_TRUST
    best_key, best_val = "", None
    for key, val in SOURCE_TRUST.items():
        if s.startswith(key) or key in s:
            if len(key) > len(best_key):
                best_key, best_val = key, val
    return DEFAULT_TRUST if best_val is None else best_val


def _source_family(source: str) -> str:
    """
    Collapse a source string to its independent origin.

    `reddit:r/hackathons` and `reddit:r/Btechtards` are the same origin and must
    not be counted as two independent confirmations.
    """
    s = str(source or "unknown").strip().lower()
    for sep in (":", "/", "-"):
        if sep in s:
            head = s.split(sep, 1)[0]
            if len(head) >= 4:
                return head
    return s


def _title_key(name: str) -> str:
    """Order-independent identity key for corroboration matching."""
    tokens = _distinctive_tokens(name)
    if len(tokens) < 2:
        tokens = set(re.findall(r"[a-z0-9]+", str(name or "").lower()))
    return " ".join(sorted(tokens))


def _distinctive_tokens(text: str) -> set:
    """Content-bearing tokens: drop generic filler and 1-2 char noise."""
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return {w for w in words if len(w) > 2 and w not in GENERIC_TOKENS}


def _containment(claim: set, page: set) -> float:
    """
    Fraction of the claim's distinctive tokens present on the page.

    Containment, not Jaccard: a page legitimately contains far more text than a
    title, so symmetric similarity would punish correct matches.
    """
    if not claim or not page:
        return 0.0
    return len(claim & page) / len(claim)


def _primary_url(item: Dict) -> str:
    for key in ("applicationLink", "url", "website", "link"):
        val = str(item.get(key, "") or "").strip()
        if val.lower().startswith(("http://", "https://")):
            return val
    return ""


def _domain(url: str) -> str:
    m = re.match(r"^https?://([^/?#]+)", str(url or "").strip(), re.I)
    if not m:
        return ""
    host = m.group(1).lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _path(url: str) -> str:
    m = re.match(r"^https?://[^/?#]+(/[^?#]*)", str(url or "").strip(), re.I)
    return m.group(1) if m else "/"


def _parse_claimed_date(value: Any) -> Optional[date]:
    """
    Parse a scraper-claimed date. Returns None for non-dates ("Rolling", "TBD")
    so callers can distinguish "no date" from "bad date".
    """
    s = str(value or "").strip()
    if not s:
        return None
    low = s.lower()
    if any(tok in low for tok in _NON_DATE_TOKENS):
        return None

    m = _ISO.match(s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    # Ranges: take the end. Do not split single hyphens inside ISO dates.
    parts = re.split(r"\s+[-–—]\s+|\s+to\s+|[–—]", s)
    tail = parts[-1].strip()
    for candidate in (tail, s):
        if not candidate:
            continue
        try:
            from dateutil.parser import parse as parse_date
            return parse_date(candidate, fuzzy=True).date()
        except Exception:
            continue
    return None
