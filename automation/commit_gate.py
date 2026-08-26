"""
OpportunityHub — Commit Gate (dataset-level invariants)

Layer 1 and Layer 2 both judge *individual records*. Neither can see the shape of
the dataset as a whole, and that leaves the most damaging failure mode wide open.

Consider what actually happens today when a scraper breaks. `merge_opportunities`
appends whatever it is handed, `save_json` overwrites the file, and the CI job
runs `git add data/ && git commit && git push`. There is no step between "a
scraper returned nonsense" and "nonsense is the published dataset on main".
Concretely, all of the following would sail straight through:

  * A selector change makes a scraper emit 4,000 junk rows in one run.
  * A site returns an empty listing, an upstream `[]` propagates, and a category
    file loses 90% of its records.
  * A refactor renames `applicationLink`, so every record silently loses its link.
  * Two scrapers begin emitting the same event under slightly different titles,
    doubling the file.

Per-record verification cannot catch any of these, because each individual record
may look perfectly fine. These are *aggregate* properties.

The Commit Gate is the last checkpoint before persistence. It compares the
proposed file contents against the previous contents and refuses the write when an
invariant is violated. Its bias is deliberate and important: when something looks
structurally wrong, KEEPING THE OLD DATA IS ALWAYS SAFER THAN PUBLISHING THE NEW.
A stale dataset is a minor problem; a corrupted or emptied one is a visible
outage, and in a git-backed pipeline it is also committed history.

Severities:
    BLOCK — abort the write for this category, keep the previous file.
    WARN  — allow the write, surface it in the run report.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger("opportunityhub.commit_gate")

BLOCK = "block"
WARN = "warn"


# ── Tunables ────────────────────────────────────────────────────────────────

# Fraction of the previous record count that must survive a write.
MIN_RETENTION = 0.90

# A single run may add at most max(ABS_SURGE_LIMIT, REL_SURGE_LIMIT * previous).
ABS_SURGE_LIMIT = 150
REL_SURGE_LIMIT = 0.40

# Below this many existing records a category is "bootstrapping": retention and
# surge limits do not apply, because growing from 0 to 300 is legitimate exactly
# once and would otherwise be indistinguishable from a flood.
BOOTSTRAP_THRESHOLD = 10

# Share of records allowed to lack a usable link before it looks like a
# field-rename regression rather than incomplete data.
MAX_MISSING_LINK_RATIO = 0.35

# Duplicate tolerance. Some legitimate near-duplicates exist across sources.
MAX_DUPLICATE_RATIO = 0.12

VALID_STATUSES = {"open", "closed", "coming-soon", "upcoming", "ongoing", "", None}

REQUIRED_FIELDS = ("name",)
EXPECTED_LINK_FIELDS = ("applicationLink", "url", "website", "link")

# Internal bookkeeping that must never be published.
FORBIDDEN_KEYS = (
    "_adjudication", "_verification_score", "_verification_warnings",
    "_rejection_reasons", "_quarantine", "_location_reject", "_research",
)


@dataclass
class Violation:
    code: str
    severity: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.code}: {self.detail}"


@dataclass
class GateDecision:
    category: str
    allowed: bool = True
    violations: List[Violation] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def blockers(self) -> List[Violation]:
        return [v for v in self.violations if v.severity == BLOCK]

    @property
    def warnings(self) -> List[Violation]:
        return [v for v in self.violations if v.severity == WARN]

    def summary(self) -> str:
        if self.allowed and not self.violations:
            return f"{self.category}: OK"
        if self.allowed:
            return f"{self.category}: OK with {len(self.warnings)} warning(s)"
        return f"{self.category}: BLOCKED — {'; '.join(v.code for v in self.blockers)}"


class CommitGate:
    """
    Validates a proposed dataset write against aggregate invariants.

    Stateless and side-effect free — it only inspects and reports. The caller
    decides what to do, which keeps the policy testable.
    """

    def __init__(
        self,
        min_retention: float = MIN_RETENTION,
        abs_surge_limit: int = ABS_SURGE_LIMIT,
        rel_surge_limit: float = REL_SURGE_LIMIT,
    ):
        self.min_retention = min_retention
        self.abs_surge_limit = abs_surge_limit
        self.rel_surge_limit = rel_surge_limit

    # ── Public API ─────────────────────────────────────────────────────────

    def evaluate(
        self,
        category: str,
        before: Sequence[Dict],
        after: Sequence[Dict],
        added: Optional[Sequence[Dict]] = None,
    ) -> GateDecision:
        """Decide whether `after` may replace `before` on disk."""
        before = list(before or [])
        after = list(after or [])
        added = list(added or [])
        decision = GateDecision(category=category)

        bootstrap = len(before) < BOOTSTRAP_THRESHOLD
        decision.metrics = {
            "before": len(before),
            "after": len(after),
            "added": len(added),
            "delta": len(after) - len(before),
            "bootstrap": bootstrap,
        }

        # Structural checks always apply.
        self._check_container(decision, after)
        if decision.blockers:
            # Nothing below can be trusted if the container itself is wrong.
            decision.allowed = False
            return decision

        self._check_schema(decision, after)
        self._check_links(decision, after)
        self._check_statuses(decision, after)
        self._check_duplicates(decision, after)
        self._check_forbidden_keys(decision, after)
        self._check_serializable(decision, after)

        # Volume checks are meaningless while bootstrapping.
        if not bootstrap:
            self._check_retention(decision, before, after)
            self._check_surge(decision, before, added)
            self._check_link_loss(decision, before, after)

        decision.allowed = not decision.blockers
        return decision

    # ── Structural invariants ──────────────────────────────────────────────

    def _check_container(self, d: GateDecision, after: List[Dict]) -> None:
        if not isinstance(after, list):
            d.violations.append(Violation("not_a_list", BLOCK, f"payload is {type(after).__name__}"))
            return
        non_dict = sum(1 for r in after if not isinstance(r, dict))
        if non_dict:
            d.violations.append(Violation(
                "non_dict_records", BLOCK, f"{non_dict} record(s) are not objects",
            ))
        # An empty result where there was data is handled by retention, but an
        # empty payload with no previous data is still suspicious enough to warn.
        if not after:
            d.violations.append(Violation("empty_payload", WARN, "resulting dataset is empty"))

    def _check_schema(self, d: GateDecision, after: List[Dict]) -> None:
        missing: Dict[str, int] = {}
        blank_names = 0
        for rec in after:
            if not isinstance(rec, dict):
                continue
            for fld in REQUIRED_FIELDS:
                val = rec.get(fld)
                if not isinstance(val, str) or not val.strip():
                    missing[fld] = missing.get(fld, 0) + 1
                    if fld == "name":
                        blank_names += 1
            tags = rec.get("tags")
            if tags is not None and not isinstance(tags, (list, tuple)):
                missing["tags:wrong_type"] = missing.get("tags:wrong_type", 0) + 1

        total = max(1, len(after))
        if blank_names:
            ratio = blank_names / total
            # A few malformed rows are tolerable; a systemic failure is not.
            sev = BLOCK if ratio > 0.02 else WARN
            d.violations.append(Violation(
                "missing_name", sev,
                f"{blank_names}/{total} records ({ratio:.1%}) have no usable name",
            ))
        for key, count in missing.items():
            if key.endswith(":wrong_type"):
                d.violations.append(Violation(
                    "field_wrong_type", WARN, f"{count} records have malformed {key.split(':')[0]}",
                ))

    def _check_links(self, d: GateDecision, after: List[Dict]) -> None:
        if not after:
            return
        no_link = 0
        for rec in after:
            if not isinstance(rec, dict):
                continue
            if not any(
                isinstance(rec.get(f), str) and rec.get(f, "").strip().startswith("http")
                for f in EXPECTED_LINK_FIELDS
            ):
                no_link += 1
        ratio = no_link / len(after)
        if ratio > MAX_MISSING_LINK_RATIO:
            # Almost always a renamed/dropped field rather than genuinely
            # link-less opportunities.
            d.violations.append(Violation(
                "widespread_missing_links", BLOCK,
                f"{no_link}/{len(after)} records ({ratio:.1%}) have no http link "
                f"— looks like a field rename or parse regression",
            ))
        elif no_link:
            d.violations.append(Violation(
                "some_missing_links", WARN, f"{no_link} records have no http link",
            ))

    def _check_statuses(self, d: GateDecision, after: List[Dict]) -> None:
        bad = {}
        for rec in after:
            if not isinstance(rec, dict):
                continue
            st = rec.get("status")
            if st not in VALID_STATUSES:
                bad[str(st)] = bad.get(str(st), 0) + 1
        if bad:
            d.violations.append(Violation(
                "unknown_status", WARN,
                f"unexpected status values: {dict(list(bad.items())[:5])}",
            ))

    def _check_duplicates(self, d: GateDecision, after: List[Dict]) -> None:
        if not after:
            return
        names: Dict[str, int] = {}
        links: Dict[str, int] = {}
        for rec in after:
            if not isinstance(rec, dict):
                continue
            n = _norm_name(rec.get("name", ""))
            if n and len(n) > 4:
                names[n] = names.get(n, 0) + 1
            l = _norm_link(rec.get("applicationLink", ""))
            if l and len(l) > 10:
                links[l] = links.get(l, 0) + 1

        dup_names = sum(c - 1 for c in names.values() if c > 1)
        dup_links = sum(c - 1 for c in links.values() if c > 1)
        worst = max(dup_names, dup_links)
        ratio = worst / len(after)
        if ratio > MAX_DUPLICATE_RATIO:
            d.violations.append(Violation(
                "duplicate_flood", BLOCK,
                f"{dup_names} duplicate names / {dup_links} duplicate links "
                f"({ratio:.1%} of {len(after)}) — dedup appears broken",
            ))
        elif worst:
            d.violations.append(Violation(
                "duplicates_present", WARN,
                f"{dup_names} duplicate names, {dup_links} duplicate links",
            ))

    def _check_forbidden_keys(self, d: GateDecision, after: List[Dict]) -> None:
        leaked: Dict[str, int] = {}
        for rec in after:
            if not isinstance(rec, dict):
                continue
            for key in FORBIDDEN_KEYS:
                if key in rec:
                    leaked[key] = leaked.get(key, 0) + 1
        if leaked:
            # Not corrupt, but it bloats what the browser downloads and makes
            # diffs unreadable, so it should be visible and fixed.
            d.violations.append(Violation(
                "internal_metadata_leak", WARN,
                f"internal keys present in published records: {leaked}",
            ))

    def _check_serializable(self, d: GateDecision, after: List[Dict]) -> None:
        try:
            json.dumps(after, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            d.violations.append(Violation(
                "not_serializable", BLOCK, f"payload cannot be written as JSON: {e}",
            ))

    # ── Volume invariants ──────────────────────────────────────────────────

    def _check_retention(self, d: GateDecision, before: List[Dict], after: List[Dict]) -> None:
        floor = int(len(before) * self.min_retention)
        if len(after) < floor:
            lost = len(before) - len(after)
            d.violations.append(Violation(
                "mass_deletion", BLOCK,
                f"would drop {lost} of {len(before)} records "
                f"({lost / max(1, len(before)):.1%}), below the "
                f"{self.min_retention:.0%} retention floor",
            ))

    def _check_surge(self, d: GateDecision, before: List[Dict], added: List[Dict]) -> None:
        if not added:
            return
        limit = max(self.abs_surge_limit, int(len(before) * self.rel_surge_limit))
        if len(added) > limit:
            d.violations.append(Violation(
                "insertion_surge", BLOCK,
                f"{len(added)} new records in one run exceeds the limit of {limit} "
                f"(base {len(before)}) — likely a scraper malfunction",
            ))

    def _check_link_loss(self, d: GateDecision, before: List[Dict], after: List[Dict]) -> None:
        """Catch a field rename that empties links without changing record count."""
        def with_links(recs: List[Dict]) -> int:
            return sum(
                1 for r in recs
                if isinstance(r, dict) and any(
                    isinstance(r.get(f), str) and r.get(f, "").strip().startswith("http")
                    for f in EXPECTED_LINK_FIELDS
                )
            )

        b, a = with_links(before), with_links(after)
        if b >= 20 and a < b * 0.75:
            d.violations.append(Violation(
                "link_coverage_collapse", BLOCK,
                f"records with links fell from {b} to {a} — schema regression",
            ))


# ── Helpers ─────────────────────────────────────────────────────────────────


def _norm_name(name: Any) -> str:
    clean = re.sub(r"[^\w\s]", "", str(name or "")).lower().strip()
    return re.sub(r"\s+", " ", clean)


def _norm_link(url: Any) -> str:
    s = str(url or "").strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    return s.split("#")[0].rstrip("/")


def format_gate_report(decisions: Iterable[GateDecision]) -> str:
    """Render gate outcomes for the pipeline run report."""
    lines = ["", "🚦 COMMIT GATE:"]
    any_blocked = False
    for d in decisions:
        icon = "✅" if d.allowed and not d.violations else ("⚠️" if d.allowed else "⛔")
        m = d.metrics
        lines.append(
            f"  {icon} {d.category:<22} {m.get('before', 0):>5} → {m.get('after', 0):<5} "
            f"(+{m.get('added', 0)})"
        )
        for v in d.violations:
            lines.append(f"       {v}")
        if not d.allowed:
            any_blocked = True
    if any_blocked:
        lines.append("  ⛔ One or more categories were BLOCKED — previous data retained.")
    return "\n".join(lines)
