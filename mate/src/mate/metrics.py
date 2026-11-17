"""Scoring of runs: retrieval against evidence groups, answers against values, citations against occurrences.

A retrieved passage is matched to gold spans by *location and anchor*, not by character offsets:
it comes from a message (or from one of its files), and it contains the anchor text. This works
for any chunker, which matters because the experimental arms change the chunking (design
document, decision F-1). Header spans, and image spans of a passage that has no text (a page
returned by a visual retriever), are matched by location alone.
"""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from dataclasses import dataclass, field
from math import comb

from mate.corpus import Corpus
from mate.normalize import contains_value
from mate.schema import Question, Retrieved, RunRecord

_ABSTAIN = re.compile(
    r"\b(not (be )?found|no information|cannot (find|answer|determine)|can't (find|answer)|"
    r"does not (contain|mention|say)|don't know|do not know|no (such|record)|not mentioned|unknown|"
    r"keine (information|angabe|angaben)|nicht (gefunden|enthalten|erwähnt|bekannt|beantworten)|"
    r"weiß (ich )?nicht|kann (ich )?nicht)\b",
    re.I,
)


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


@dataclass
class SpanIndex:
    """Lookups that map a retrieved passage to the spans it contains."""

    by_message: dict[str, list] = field(default_factory=lambda: defaultdict(list))
    by_version: dict[str, list] = field(default_factory=lambda: defaultdict(list))
    rfc_to_msg: dict[str, str] = field(default_factory=dict)
    platform_occ: dict[tuple[str, int], object] = field(default_factory=dict)
    first_occ: dict[str, str] = field(default_factory=dict)
    spans: dict[str, object] = field(default_factory=dict)
    spans_by_fact: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    value_fact: dict[str, str] = field(default_factory=dict)

    @classmethod
    def build(cls, c: Corpus) -> SpanIndex:
        idx = cls()
        occs = c.by_id("occurrences")
        for s in c.spans:
            idx.spans[s.id] = s
            if s.location.kind == "file":
                idx.by_version[s.location.version_id].append(s)
            elif s.location.message_id:
                idx.by_message[s.location.message_id].append(s)
        for fv in c.fact_values:
            idx.value_fact[fv.id] = fv.fact_id
        for s in c.spans:
            if s.fact_value_id:
                idx.spans_by_fact[idx.value_fact[s.fact_value_id]].add(s.id)
        for m in c.messages:
            idx.rfc_to_msg[m.rfc_message_id] = m.id
        index_path = c.root / "rendered" / "index.jsonl"
        if index_path.exists():
            with index_path.open(encoding="utf-8") as fh:
                for line in fh:
                    rec = json.loads(line)
                    for part in rec["parts"]:
                        if part["platform_attachment_index"] is not None and part["occurrence_id"]:
                            key = (rec["message_id"], part["platform_attachment_index"])
                            idx.platform_occ[key] = occs[part["occurrence_id"]]
        idx.first_occ = c.first_occurrence()
        return idx

    def spans_in(self, item: Retrieved) -> set[str]:
        msg = self.rfc_to_msg.get(item.rfc_message_id or "")
        if msg is None:
            return set()
        text = _norm(item.text)
        if item.attachment_order is None:
            out = set()
            for s in self.by_message.get(msg, []):
                if s.location.kind in ("header", "subject") or _norm(s.anchor) in text:
                    out.add(s.id)
            return out
        occ = self.platform_occ.get((msg, item.attachment_order))
        if occ is None:
            return set()
        out = set()
        for s in self.by_version.get(occ.version_id, []):
            if item.page is not None and s.location.page not in (None, item.page):
                continue
            if _norm(s.anchor) in text or (s.location.part == "image" and not text):
                out.add(s.id)
        return out

    def is_resent(self, item: Retrieved) -> bool:
        """Whether a passage comes from a later copy of a file rather than its first sending."""
        msg = self.rfc_to_msg.get(item.rfc_message_id or "")
        occ = self.platform_occ.get((msg, item.attachment_order)) if msg and item.attachment_order is not None else None
        return bool(occ and self.first_occ.get(occ.version_id) != occ.id)


# ----------------------------------------------------------------------- retrieval


def retrieval_scores(q: Question, items: list[Retrieved], idx: SpanIndex, k: int) -> dict[str, float | None]:
    groups = [g for g in q.gold.groups if g.required]
    if not groups:
        return {}
    top = sorted(items, key=lambda x: x.rank)[:k]
    hits = [idx.spans_in(it) for it in top]
    group_spans = [set(g.span_ids) for g in groups]
    covered = [any(h & gs for h in hits) for gs in group_spans]
    gold_all = set().union(*group_spans)
    originals = {s for s in gold_all if idx.spans[s].origin == "original"}
    hit_all = set().union(*hits) if hits else set()

    first = next((i + 1 for i, h in enumerate(hits) if any(h & gs for gs in group_spans)), None)
    seen: set[int] = set()
    wasted = 0
    for h in hits:
        g_hit = {i for i, gs in enumerate(group_spans) if h & gs}
        if g_hit and g_hit <= seen:
            wasted += 1
        seen |= g_hit
    out: dict[str, float | None] = {
        f"hit@{k}": float(any(covered)),
        f"coverage@{k}": sum(covered) / len(covered),
        f"perfrecall@{k}": float(all(covered)),
        f"span_recall@{k}": len(hit_all & gold_all) / len(gold_all),
        f"original_recall@{k}": (len(hit_all & originals) / len(originals)) if originals else None,
        "mrr": 1.0 / first if first else 0.0,
        f"wasted_slots@{k}": wasted / max(len(top), 1),
    }
    # Version-aware scores: is the valid value there, or only outdated ones of the same fact?
    if q.scope in ("current", "as_of") and q.answer.fact_value_ids:
        facts = {idx.value_fact[v] for v in q.answer.fact_value_ids}
        valid = {s for v in q.answer.fact_value_ids for s in group_spans_of(idx, v)}
        same_fact = set().union(*(idx.spans_by_fact[f] for f in facts))
        any_version = bool(hit_all & same_fact)
        tca = bool(hit_all & valid)
        stale_items = sum(1 for h in hits if (h & same_fact) and not (h & valid))
        out.update({
            f"tca@{k}": float(tca),
            f"any_version@{k}": float(any_version),
            f"stale_only@{k}": float(any_version and not tca),
            f"stale_share@{k}": stale_items / max(len(top), 1),
        })
    return out


def group_spans_of(idx: SpanIndex, fact_value_id: str) -> set[str]:
    return {sid for sid, s in idx.spans.items() if s.fact_value_id == fact_value_id}


# ------------------------------------------------------------------------- answers


def grade_answer(q: Question, answer: str) -> str:
    """'correct', 'superseded', 'partial', 'abstain', 'wrong' (value answers) or 'judge' (needs a judge).

    Value questions are graded against a closed pool: a valid value, a superseded value of the
    same fact, or neither (StateMem's current / superseded / other grading).
    """
    kind = q.answer.kind
    if kind == "abstain":
        return "correct" if _ABSTAIN.search(answer) else "wrong"
    if kind in ("summary",):
        return "judge"
    found = [a for a in q.answer.accepted if contains_value(answer, a)]
    stale = [s for s in q.answer.superseded if contains_value(answer, s)]
    if kind in ("contested", "values"):
        if len(found) == len(q.answer.accepted) and q.answer.accepted:
            return "correct"
        return "partial" if found else ("abstain" if _ABSTAIN.search(answer) else "wrong")
    if found and not stale:
        return "correct"
    if stale and not found:
        return "superseded"
    if found and stale:
        return "partial"  # both values given: hedged, right only if it says which is current
    return "abstain" if _ABSTAIN.search(answer) else "wrong"


def citation_scores(q: Question, rec: RunRecord, idx: SpanIndex) -> dict[str, float | None]:
    groups = [set(g.span_ids) for g in q.gold.groups if g.required]
    if not groups or not rec.cited_ranks:
        return {"citation_recall": 0.0 if groups else None, "citation_precision": None,
                "citation_recall_original": 0.0 if groups else None}
    by_rank = {it.rank: it for it in rec.retrieved}
    cited = [by_rank[r] for r in rec.cited_ranks if r in by_rank]
    hits = [idx.spans_in(it) for it in cited]
    gold_all = set().union(*groups)
    lenient = sum(1 for gs in groups if any(h & gs for h in hits)) / len(groups)
    # Strict policy: only the original statement counts, not a quote, a forward or a re-sent file.
    originals = [{s for s in gs if idx.spans[s].origin == "original"} for gs in groups]
    first_hits = [h for h, it in zip(hits, cited) if not idx.is_resent(it)]
    strict = sum(1 for gs in originals if gs and any(h & gs for h in first_hits)) / len(groups)
    precision = sum(1 for h in hits if h & gold_all) / len(cited) if cited else None
    return {"citation_recall": lenient, "citation_recall_original": strict, "citation_precision": precision}


# ---------------------------------------------------------------------- statistics


def paired_bootstrap(a: list[float], b: list[float], n: int = 10_000, seed: int = 0) -> tuple[float, float, float]:
    """Mean of b - a over paired questions, with a 95 % percentile bootstrap interval."""
    if len(a) != len(b) or not a:
        raise ValueError("paired samples of equal, non-zero length are needed")
    diffs = [y - x for x, y in zip(a, b)]
    rng = random.Random(seed)
    m = len(diffs)
    means = sorted(sum(diffs[rng.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return sum(diffs) / m, means[int(0.025 * n)], means[int(0.975 * n) - 1]


def mcnemar_exact(only_a: int, only_b: int) -> float:
    """Two-sided exact McNemar test on the discordant pairs (a right, b wrong; a wrong, b right)."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(0, min(only_a, only_b) + 1)) / 2**n
    return min(1.0, 2 * tail)


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values, for several arms compared with one baseline."""
    order = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(order)
    adjusted: dict[str, float] = {}
    running = 0.0
    for i, (name, p) in enumerate(order):
        running = max(running, min(1.0, (m - i) * p))
        adjusted[name] = running
    return adjusted
