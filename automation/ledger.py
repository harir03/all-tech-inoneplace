"""
OpportunityHub — Verification Ledger & Quarantine Queue (Layer 2 memory)

Both existing gates are amnesiac. Every hourly CI run starts from a fresh
checkout, re-probes the same URLs, re-derives the same verdicts, and throws the
reasoning away. Three concrete problems follow from that:

  * WASTE / RATE-LIMITING  — the same few hundred URLs get hammered 24x a day.
  * SILENT LOSS            — a real opportunity that failed verification once
                             (flaky host, slow CDN) is dropped and never
                             reconsidered, because nothing remembers it existed.
  * NO ACCOUNTABILITY      — you cannot answer "why is this row in my dataset?"
                             or "what did we reject last Tuesday, and why?".

This module supplies the missing memory:

  VerificationLedger — append-only-ish audit record keyed by a stable
                       fingerprint. Provides idempotence (skip re-probing
                       something confirmed recently), a blacklist for
                       permanently disproven records, and a full decision trail.

  QuarantineQueue    — a hold-and-retry buffer. Items that are *unproven* rather
                       than *disproven* wait here instead of being discarded.
                       They are re-injected as candidates on later runs and get
                       promoted the moment evidence or an independent source
                       corroborates them. After a bounded number of failed
                       attempts they are retired for good.

Both files live under `data/` with a leading underscore. That matters: the
website loads an explicit whitelist of category files
(`website/js/app.js`), so underscore-prefixed files never reach the UI, while
`git add data/` in CI still commits them — which is the only way state survives
between stateless workflow runs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("opportunityhub.ledger")

LEDGER_VERSION = 2

# Skip re-probing an item confirmed within this window.
DEFAULT_RECHECK_TTL_HOURS = 72

# Attempts an unproven item gets before permanent retirement.
MAX_QUARANTINE_ATTEMPTS = 4

# Drop ledger rows untouched for this long, to keep the file bounded.
LEDGER_RETENTION_DAYS = 180

# Hard cap on quarantine size so a runaway scraper cannot inflate the repo.
MAX_QUARANTINE_ITEMS = 500

# Keys that are internal bookkeeping and must never reach data/*.json.
INTERNAL_KEYS = (
    "_verification_score", "_verification_warnings", "_rejection_reasons",
    "_adjudication", "_quarantine",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat(timespec="seconds")


def _parse_iso(s: Any) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        txt = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(txt)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _normalize_name(name: Any) -> str:
    clean = re.sub(r"[^\w\s]", "", str(name or "")).lower().strip()
    return re.sub(r"\s+", " ", clean)


def _normalize_link(url: Any) -> str:
    s = str(url or "").strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = s.split("#")[0]
    s = re.sub(r"[?&](utm_[^=]+|ref|fbclid|gclid)=[^&]*", "", s)
    return s.rstrip("/?&")


def fingerprint(item: Dict) -> str:
    """
    Stable identity for an opportunity across runs.

    Name and link are hashed together so that a retitled listing at the same URL
    (or the same event moved to a new URL) is treated as a new observation rather
    than silently inheriting an old verdict.
    """
    basis = f"{_normalize_name(item.get('name'))}|{_normalize_link(item.get('applicationLink') or item.get('website'))}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:20]


def strip_internal(item: Dict) -> Dict:
    """
    Return a copy without internal verification metadata.

    The audit trail belongs in the ledger, not in the published dataset. Keeping
    `_adjudication` blobs out of data/*.json keeps the payload the browser
    downloads small and the diffs reviewable.
    """
    return {k: v for k, v in item.items() if k not in INTERNAL_KEYS}


def _atomic_write_json(path: str, payload: Any) -> None:
    """Write via temp file + replace so a crash can never leave a truncated file."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class VerificationLedger:
    """Persistent, auditable record of every verification decision."""

    def __init__(self, path: str, recheck_ttl_hours: int = DEFAULT_RECHECK_TTL_HOURS):
        self.path = path
        self.recheck_ttl = timedelta(hours=recheck_ttl_hours)
        self.records: Dict[str, Dict] = {}
        self.meta: Dict[str, Any] = {}
        self._dirty = False
        self.load()

    # ── Persistence ────────────────────────────────────────────────────────

    def load(self) -> None:
        if not os.path.exists(self.path):
            logger.info("[Ledger] No ledger at %s — starting fresh", self.path)
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                blob = json.load(f)
            self.records = blob.get("records", {}) or {}
            self.meta = blob.get("meta", {}) or {}
            logger.info("[Ledger] Loaded %d records", len(self.records))
        except (json.JSONDecodeError, IOError, OSError) as e:
            # A corrupt ledger must never take the pipeline down; it is a cache
            # plus an audit log, not the source of truth.
            logger.error("[Ledger] Unreadable (%s) — starting fresh", e)
            self.records, self.meta = {}, {}

    def save(self) -> bool:
        if not self._dirty:
            return False
        self.prune()
        payload = {
            "version": LEDGER_VERSION,
            "meta": {
                **self.meta,
                "updated_at": _iso(),
                "record_count": len(self.records),
            },
            "records": self.records,
        }
        try:
            _atomic_write_json(self.path, payload)
            self._dirty = False
            logger.info("[Ledger] Saved %d records to %s", len(self.records), self.path)
            return True
        except Exception as e:
            logger.error("[Ledger] Save failed: %s", e)
            return False

    # ── Queries ────────────────────────────────────────────────────────────

    def get(self, item: Dict) -> Optional[Dict]:
        return self.records.get(fingerprint(item))

    def is_retired(self, item: Dict) -> bool:
        """
        True if this exact record was already definitively disproven.

        Lets the pipeline skip network work on known-bad records instead of
        rediscovering the same rejection every hour.
        """
        rec = self.get(item)
        if not rec:
            return False
        if rec.get("decision") != "reject":
            return False
        return bool(rec.get("permanent"))

    def should_skip_recheck(self, item: Dict) -> bool:
        """
        True if this item was accepted recently enough to trust without
        re-probing. This is what keeps hourly runs cheap and polite.
        """
        rec = self.get(item)
        if not rec or rec.get("decision") != "accept":
            return False
        last = _parse_iso(rec.get("last_checked"))
        if not last:
            return False
        return (_now() - last) < self.recheck_ttl

    def attempts(self, item: Dict) -> int:
        rec = self.get(item)
        return int(rec.get("attempts", 0)) if rec else 0

    # ── Mutation ───────────────────────────────────────────────────────────

    def record(
        self,
        item: Dict,
        category: str,
        verdict: str,
        *,
        layer: str = "L2",
        reasons: Optional[List[str]] = None,
        evidence_kind: str = "",
        evidence_hash: str = "",
        trust: Optional[float] = None,
        corroboration: Optional[int] = None,
        corrections: Optional[Dict] = None,
        permanent: Optional[bool] = None,
    ) -> Dict:
        """Write (or update) the audit row for one item."""
        fp = fingerprint(item)
        now = _iso()
        rec = self.records.get(fp)

        if rec is None:
            rec = {
                "name": str(item.get("name", ""))[:120],
                "category": category,
                "source": str(item.get("source", ""))[:60],
                "link": str(item.get("applicationLink", ""))[:300],
                "first_seen": now,
                "attempts": 0,
            }
            self.records[fp] = rec

        rec["decision"] = verdict
        rec["layer"] = layer
        rec["last_checked"] = now
        rec["attempts"] = int(rec.get("attempts", 0)) + 1
        rec["reasons"] = (reasons or [])[:5]
        if evidence_kind:
            rec["evidence"] = evidence_kind
        if evidence_hash:
            rec["evidence_hash"] = evidence_hash
        if trust is not None:
            rec["trust"] = round(float(trust), 2)
        if corroboration is not None:
            rec["corroboration"] = int(corroboration)
        if corrections:
            rec["corrections"] = {k: v for k, v in list(corrections.items())[:8]}

        if permanent is None:
            # Disproof is permanent; "unproven" never is.
            permanent = verdict == "reject" and layer != "quarantine-expiry"
        rec["permanent"] = bool(permanent) if verdict == "reject" else False

        self._dirty = True
        return rec

    def prune(self) -> int:
        """Drop rows untouched beyond the retention window."""
        cutoff = _now() - timedelta(days=LEDGER_RETENTION_DAYS)
        stale = [
            fp for fp, rec in self.records.items()
            if (_parse_iso(rec.get("last_checked")) or _now()) < cutoff
        ]
        for fp in stale:
            del self.records[fp]
        if stale:
            self._dirty = True
            logger.info("[Ledger] Pruned %d stale records", len(stale))
        return len(stale)

    def stats(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for rec in self.records.values():
            counts[rec.get("decision", "unknown")] = counts.get(rec.get("decision", "unknown"), 0) + 1
        return {
            "total": len(self.records),
            "by_decision": counts,
            "retired": sum(1 for r in self.records.values() if r.get("permanent")),
        }


class QuarantineQueue:
    """
    Hold-and-retry buffer for unproven items.

    The key design point: `REJECT` and `QUARANTINE` are different outcomes.
    Rejection means we have evidence the item is wrong. Quarantine means we could
    not establish either way — usually a low-trust source with no corroboration,
    or a host that was unreachable. Discarding those loses real opportunities;
    accepting them admits noise. So they wait, get retried with fresh evidence on
    later runs, and are promoted or retired on the strength of what we learn.
    """

    def __init__(self, path: str, max_attempts: int = MAX_QUARANTINE_ATTEMPTS):
        self.path = path
        self.max_attempts = max_attempts
        self.buckets: Dict[str, Dict[str, Dict]] = {}
        self._dirty = False
        self.load()

    # ── Persistence ────────────────────────────────────────────────────────

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                blob = json.load(f)
            self.buckets = blob.get("buckets", {}) or {}
            total = sum(len(b) for b in self.buckets.values())
            if total:
                logger.info("[Quarantine] Loaded %d held items", total)
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.error("[Quarantine] Unreadable (%s) — starting fresh", e)
            self.buckets = {}

    def save(self) -> bool:
        if not self._dirty:
            return False
        self._enforce_cap()
        payload = {
            "version": LEDGER_VERSION,
            "meta": {
                "updated_at": _iso(),
                "held": sum(len(b) for b in self.buckets.values()),
                "note": "Unproven items awaiting corroboration. Not part of the public dataset.",
            },
            "buckets": self.buckets,
        }
        try:
            _atomic_write_json(self.path, payload)
            self._dirty = False
            return True
        except Exception as e:
            logger.error("[Quarantine] Save failed: %s", e)
            return False

    # ── Queue operations ───────────────────────────────────────────────────

    def pending(self, category: str) -> List[Dict]:
        """Items to re-inject as candidates for this category."""
        bucket = self.buckets.get(category, {})
        out = []
        for fp, entry in bucket.items():
            payload = entry.get("item")
            if isinstance(payload, dict) and payload.get("name"):
                item = dict(payload)
                item["_quarantine"] = {"fingerprint": fp, "attempts": entry.get("attempts", 0)}
                out.append(item)
        return out

    def hold(self, category: str, item: Dict, reasons: Optional[List[str]] = None) -> Tuple[bool, int]:
        """
        Park an unproven item.

        Returns (still_held, attempts). `still_held` is False once the item has
        exhausted its retries and should be retired permanently.
        """
        fp = fingerprint(item)
        bucket = self.buckets.setdefault(category, {})
        entry = bucket.get(fp)
        attempts = int(entry.get("attempts", 0)) + 1 if entry else 1

        if attempts > self.max_attempts:
            bucket.pop(fp, None)
            self._dirty = True
            return False, attempts

        bucket[fp] = {
            "attempts": attempts,
            "first_held": (entry or {}).get("first_held") or _iso(),
            "last_seen": _iso(),
            "reasons": (reasons or [])[:3],
            "item": strip_internal(item),
        }
        self._dirty = True
        return True, attempts

    def release(self, category: str, item: Dict) -> bool:
        """Remove an item that has now been proven (promoted into the dataset)."""
        bucket = self.buckets.get(category)
        if not bucket:
            return False
        if bucket.pop(fingerprint(item), None) is not None:
            self._dirty = True
            return True
        return False

    def _enforce_cap(self) -> None:
        """Keep the newest entries if a bucket somehow explodes."""
        for category, bucket in self.buckets.items():
            if len(bucket) <= MAX_QUARANTINE_ITEMS:
                continue
            ordered = sorted(
                bucket.items(),
                key=lambda kv: kv[1].get("last_seen", ""),
                reverse=True,
            )
            self.buckets[category] = dict(ordered[:MAX_QUARANTINE_ITEMS])
            logger.warning(
                "[Quarantine] Bucket %s exceeded cap — trimmed to %d",
                category, MAX_QUARANTINE_ITEMS,
            )

    def stats(self) -> Dict[str, Any]:
        return {
            "held_total": sum(len(b) for b in self.buckets.values()),
            "by_category": {k: len(v) for k, v in self.buckets.items() if v},
        }
