"""Checks that make the gold trustworthy. Each check has a code; the design document lists them.

Errors make a corpus unusable; warnings are reported and reviewed. ``validate(corpus)`` runs
everything that needs only the tables; ``validate_rendered`` adds the checks that need the
rendered mail (anchors present in the text a system will actually read).
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from mate.corpus import Corpus, sha256_file

_SUBJECT_PREFIX = {
    ("reply", "en"): ("Re:",), ("reply", "de"): ("AW:", "Re:"),
    ("reply_all", "en"): ("Re:",), ("reply_all", "de"): ("AW:", "Re:"),
    ("forward", "en"): ("Fwd:", "FW:"), ("forward", "de"): ("WG:", "Fwd:"),
}
_PLACEHOLDER = re.compile(r"\{\{img:(occ-[a-z0-9-]+)\}\}")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, code: str, msg: str) -> None:
        self.errors.append(f"{code} {msg}")

    def warn(self, code: str, msg: str) -> None:
        self.warnings.append(f"{code} {msg}")

    @property
    def ok(self) -> bool:
        return not self.errors

    def __str__(self) -> str:
        lines = [f"{len(self.errors)} errors, {len(self.warnings)} warnings"]
        lines += [f"  E {e}" for e in self.errors] + [f"  W {w}" for w in self.warnings]
        return "\n".join(lines)


def validate(c: Corpus) -> Report:
    r = Report()
    ids = {name: c.by_id(name) for name in c.tables}

    # V01 unique ids within and across tables
    seen: Counter[str] = Counter(rec.id for recs in c.tables.values() for rec in recs)
    for dup, n in seen.items():
        if n > 1:
            r.error("V01", f"id {dup} used {n} times")

    orgs, people, projects = ids["organisations"], ids["people"], ids["projects"]
    facts, values = ids["facts"], ids["fact_values"]
    arts, vers = ids["artifacts"], ids["versions"]
    threads, msgs, occs, spans = ids["threads"], ids["messages"], ids["occurrences"], ids["spans"]

    def need(code: str, table: dict, key: str | None, what: str) -> None:
        if key is not None and key not in table:
            r.error(code, f"{what} -> unknown {key}")

    # V02 references resolve
    for p in c.people:
        need("V02", orgs, p.org_id, p.id)
        dom = orgs[p.org_id].domain if p.org_id in orgs else None
        if dom and not p.email.endswith("@" + dom):  # V03
            r.error("V03", f"{p.id} email {p.email} is not in its organisation's domain {dom}")
    for f in c.facts:
        need("V02", projects, f.project_id, f.id)
    for fv in c.fact_values:
        need("V02", facts, fv.fact_id, fv.id)
        need("V02", values, fv.supersedes, fv.id)
        need("V02", people, fv.asserted_by, fv.id)
    for a in c.artifacts:
        need("V02", projects, a.project_id, a.id)
        need("V02", people, a.owner, a.id)
    for v in c.versions:
        need("V02", arts, v.artifact_id, v.id)
        need("V02", vers, v.supersedes, v.id)
        need("V02", people, v.author, v.id)
        path = c.root / v.file.path
        if not path.exists():  # V04
            r.error("V04", f"{v.id} file missing: {v.file.path}")
        elif sha256_file(path) != v.file.sha256:
            r.error("V04", f"{v.id} file hash differs from the record: {v.file.path}")
        ext = path.suffix.lower().lstrip(".")
        if ext and ext not in _EXT_FOR.get(v.file.media_type, (ext,)):
            r.warn("V04", f"{v.id} extension .{ext} does not match {v.file.media_type}")
    for t in c.threads:
        need("V02", projects, t.project_id, t.id)
    for m in c.messages:
        need("V02", threads, m.thread_id, m.id)
        need("V02", msgs, m.in_reply_to, m.id)
        need("V02", msgs, m.forward_of, m.id)
        for p in [m.sender, *m.to, *m.cc, *m.bcc]:
            need("V02", people, p, m.id)
        visible = {m.sender, *m.to, *m.cc}
        if visible & set(m.bcc):
            r.error("V05", f"{m.id} lists {sorted(visible & set(m.bcc))} both as Bcc and as sender, To or Cc")
        if m.body.quote:
            need("V02", msgs, m.body.quote.message_id, m.id)
    for o in c.occurrences:
        need("V02", msgs, o.message_id, o.id)
        need("V02", vers, o.version_id, o.id)
    for s in c.spans:
        need("V02", values, s.fact_value_id, s.id)
        need("V02", msgs, s.location.message_id, s.id)
        need("V02", vers, s.location.version_id, s.id)
        need("V02", spans, s.copy_of, s.id)
    if r.errors:
        return r  # the checks below assume references resolve

    # V05 messages: parents earlier and in the same thread; subject prefixes; rfc ids unique
    rfc = Counter(m.rfc_message_id for m in c.messages)
    for x, n in rfc.items():
        if n > 1:
            r.error("V05", f"Message-ID {x} used {n} times")
    for m in c.messages:
        for parent_id in (m.in_reply_to, m.forward_of):
            if parent_id is None:
                continue
            parent = msgs[parent_id]
            if parent.sent_at >= m.sent_at:
                r.error("V05", f"{m.id} is sent before or with its parent {parent_id}")
            if m.in_reply_to == parent_id and parent.thread_id != m.thread_id:
                r.error("V05", f"{m.id} replies to {parent_id} in another thread")
        if m.kind in ("reply", "reply_all") and not m.in_reply_to:
            r.error("V05", f"{m.id} is a {m.kind} without in_reply_to")
        if m.kind == "forward" and not m.forward_of:
            r.error("V05", f"{m.id} is a forward without forward_of")
        if m.body.quote and m.body.quote.message_id not in (m.in_reply_to, m.forward_of):
            r.warn("V05", f"{m.id} quotes {m.body.quote.message_id}, which it neither answers nor forwards")
        prefixes = _SUBJECT_PREFIX.get((m.kind, m.language))
        if prefixes and not m.subject.startswith(prefixes):
            r.warn("V05", f"{m.id} subject {m.subject!r} lacks {'/'.join(prefixes)}")

    # V06 occurrences: no future leak, roles consistent with the body, unique names
    per_msg: dict[str, list] = defaultdict(list)
    for o in c.occurrences:
        per_msg[o.message_id].append(o)
        m, v = msgs[o.message_id], vers[o.version_id]
        if v.created_at > m.sent_at:
            r.error("V06", f"{o.id}: version {v.id} is created after message {m.id} is sent (future leak)")
        placeholder = "{{img:" + o.id + "}}"
        if o.role == "inline":
            if not o.content_id:
                r.error("V06", f"{o.id} is inline without a content_id")
            if placeholder not in m.body.text:
                r.error("V06", f"{o.id} is inline but {m.id}'s body has no {placeholder}")
        elif placeholder in m.body.text:
            r.error("V06", f"{o.id} has a placeholder but role {o.role}")
        if o.role == "inline_decorative" and not m.body.signature:
            r.warn("V06", f"{o.id} is decorative but {m.id} has no signature to carry it")
    for m in c.messages:
        for ph in _PLACEHOLDER.findall(m.body.text):
            if ph not in occs or occs[ph].message_id != m.id:
                r.error("V06", f"{m.id} has a placeholder for {ph}, which is not one of its occurrences")
    for mid, group in per_msg.items():
        names = Counter(o.filename for o in group)
        for name, n in names.items():
            if n > 1:
                r.error("V06", f"{mid} carries {n} files named {name!r}")
        orders = Counter(o.order for o in group)
        if any(n > 1 for n in orders.values()):
            r.error("V06", f"{mid} has occurrences with the same order")

    # V07 versions: supersession inside one artifact, earlier, linear
    successors: Counter[str] = Counter()
    for v in c.versions:
        if v.supersedes:
            old = vers[v.supersedes]
            successors[old.id] += 1
            if old.artifact_id != v.artifact_id:
                r.error("V07", f"{v.id} supersedes {old.id} of another artifact")
            if old.created_at >= v.created_at:
                r.error("V07", f"{v.id} supersedes the later or simultaneous {old.id}")
    for vid, n in successors.items():
        if n > 1:
            r.error("V07", f"{vid} is superseded by {n} versions (branching history)")

    # V08 fact values: supersession closes the old interval; no two valid values overlap
    for fv in c.fact_values:
        if fv.valid_to is not None and fv.valid_to <= fv.valid_from:
            r.error("V08", f"{fv.id} ends before it starts")
        if fv.supersedes:
            old = values[fv.supersedes]
            if old.fact_id != fv.fact_id:
                r.error("V08", f"{fv.id} supersedes a value of another fact")
            if old.valid_to != fv.valid_from:
                r.error("V08", f"{fv.supersedes} should end when {fv.id} starts ({fv.valid_from})")
        for lang, forms in fv.surfaces.items():
            if not forms or any(not f.strip() for f in forms):
                r.error("V08", f"{fv.id} has an empty surface form in {lang}")
    by_fact: dict[str, list] = defaultdict(list)
    for fv in c.fact_values:
        if fv.standing == "valid":
            by_fact[fv.fact_id].append(fv)
    for fid, group in by_fact.items():
        group.sort(key=lambda x: x.valid_from)
        for a, b in zip(group, group[1:]):
            if a.valid_to is None or a.valid_to > b.valid_from:
                r.error("V08", f"{fid}: valid values {a.id} and {b.id} overlap in time")

    # V09 a surface form names one value per project, so a hit is never ambiguous
    owner: dict[tuple[str, str], str] = {}
    for fv in c.fact_values:
        project = facts[fv.fact_id].project_id
        for forms in fv.surfaces.values():
            for form in forms:
                key = (project, _norm(form))
                if key in owner and owner[key] != fv.id:
                    r.error("V09", f"{project}: {form!r} is a surface of both {owner[key]} and {fv.id}")
                owner[key] = fv.id

    # V10 spans: anchors are surface forms; body anchors are in the body; copies point to originals
    for s in c.spans:
        loc = s.location
        if s.fact_value_id:
            forms = [_norm(f) for fs in values[s.fact_value_id].surfaces.values() for f in fs]
            if _norm(s.anchor) not in forms and loc.kind not in ("header", "subject"):
                r.error("V10", f"{s.id} anchor {s.anchor!r} is not a surface form of {s.fact_value_id}")
        elif not any(rel.type == "REFERS_TO" and rel.source.id == s.id for rel in c.relations):
            r.error("V10", f"{s.id} states no value and refers to nothing")
        if loc.kind in ("header", "subject", "body", "quoted_body", "forwarded_body") and not loc.message_id:
            r.error("V10", f"{s.id} ({loc.kind}) has no message_id")
        if loc.kind == "file" and not loc.version_id:
            r.error("V10", f"{s.id} (file) has no version_id")
        if loc.kind == "body" and s.anchor not in msgs[loc.message_id].body.text:
            r.error("V10", f"{s.id} anchor {s.anchor!r} is not in the body of {loc.message_id}")
        if loc.kind == "subject" and s.anchor not in msgs[loc.message_id].subject:
            r.error("V10", f"{s.id} anchor {s.anchor!r} is not in the subject of {loc.message_id}")
        if loc.kind == "file":
            v = vers[loc.version_id]
            if v.text_in_image and loc.part == "image" and s.anchor not in v.text_in_image:
                r.error("V10", f"{s.id} anchor {s.anchor!r} is not listed in {v.id}.text_in_image")
        if s.origin != "original" and s.origin != "restated" and not s.copy_of:
            r.error("V10", f"{s.id} is a {s.origin} copy without copy_of")
        if s.location.message_id and s.location.kind in ("header", "subject", "body"):
            m = msgs[s.location.message_id]
            if s.fact_value_id and values[s.fact_value_id].valid_from > m.sent_at and s.origin == "original":
                r.warn("V10", f"{s.id} states {s.fact_value_id} before it becomes valid")

    # V11 relations: endpoint kinds
    for rel in c.relations:
        kinds = (rel.source.kind, rel.target.kind)
        expected = _REL_KINDS.get(rel.type)
        if expected and kinds not in expected:
            r.error("V11", f"{rel.id} {rel.type} links {kinds}, expected one of {expected}")
        if rel.type == "CONTRADICTS":
            a, b = values.get(rel.source.id), values.get(rel.target.id)
            if a and b and a.fact_id != b.fact_id:
                r.error("V11", f"{rel.id} contrasts values of different facts")

    # V12 questions. A span becomes retrievable when its message is sent, or, inside a file,
    # when a message first carries that file.
    first_sent: dict[str, object] = {}
    for o in c.occurrences:
        when = msgs[o.message_id].sent_at
        if o.version_id not in first_sent or when < first_sent[o.version_id]:
            first_sent[o.version_id] = when
    available = {}
    for s in c.spans:
        if s.location.message_id:
            available[s.id] = msgs[s.location.message_id].sent_at
        elif s.location.version_id:
            available[s.id] = first_sent.get(s.location.version_id)
    for q in c.questions:
        _check_question(c, q, r, msgs, values, spans, occs, facts, available)
    return r


def _check_question(c, q, r, msgs, values, spans, occs, facts, available) -> None:
    need_ids = [s for g in q.gold.groups for s in g.span_ids]
    for sid in need_ids:
        if sid not in spans:
            r.error("V12", f"{q.id} gold span {sid} is unknown")
            return
    for oid in q.gold.required_occurrences:
        if oid not in occs:
            r.error("V12", f"{q.id} required occurrence {oid} is unknown")
            return
    for g in q.gold.groups:
        for sid in g.span_ids:
            if g.fact_value_id and spans[sid].fact_value_id != g.fact_value_id:
                r.error("V12", f"{q.id} group of {g.fact_value_id} lists {sid}, which states another value")
            when = available.get(sid)
            if when is None:
                r.error("V12", f"{q.id} evidence {sid} is in a file that no message carries")
            elif when > q.asked_at:
                r.error("V12", f"{q.id} is asked at {q.asked_at} but its evidence {sid} arrives at {when}")
    if q.type == "unanswerable":
        if q.gold.groups or q.answer.kind != "abstain":
            r.error("V12", f"{q.id} is unanswerable but has gold evidence or a non-abstain answer")
        return
    if not q.gold.groups:
        r.error("V12", f"{q.id} has no gold evidence")
    if q.scope == "as_of" and q.as_of is None:
        r.error("V12", f"{q.id} has scope as_of but no as_of date")
    when = q.as_of if q.scope == "as_of" else q.asked_at
    if q.scope in ("current", "as_of"):
        for fid in q.answer.fact_value_ids:
            fv = values[fid]
            if fv.standing == "erroneous":
                r.error("V12", f"{q.id} answers with the erroneous value {fid}")
            elif fv.valid_from > when or (fv.valid_to is not None and when >= fv.valid_to):
                r.error("V12", f"{q.id} answers with {fid}, which is not valid at {when}")
    for fid in q.answer.fact_value_ids:
        forms = {_norm(f) for fs in values[fid].surfaces.values() for f in fs}
        if q.answer.accepted and not forms & {_norm(a) for a in q.answer.accepted}:
            r.warn("V12", f"{q.id}: no accepted string is a surface form of {fid}")
    clash = {_norm(a) for a in q.answer.accepted} & {_norm(s) for s in q.answer.superseded}
    if clash:
        r.error("V12", f"{q.id}: {sorted(clash)} is both accepted and superseded")
    if q.strata.direction != "none" and not q.gold.required_occurrences:
        r.warn("V12", f"{q.id} tests a coupling direction but names no required occurrence")


def validate_rendered(c: Corpus) -> Report:
    """Checks on the rendered mail: every message rendered, every message-located anchor present."""
    r = Report()
    index_path = c.root / "rendered" / "index.jsonl"
    if not index_path.exists():
        r.error("V20", "no rendered/index.jsonl: render the corpus first")
        return r
    index = {}
    with index_path.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            index[rec["message_id"]] = rec
    for m in c.messages:
        if m.id not in index:
            r.error("V20", f"{m.id} is not rendered")
    for s in c.spans:
        loc = s.location
        if loc.message_id and loc.kind in ("body", "quoted_body", "forwarded_body"):
            text = index.get(loc.message_id, {}).get("text", "")
            if s.anchor not in text:
                r.error("V21", f"{s.id} anchor {s.anchor!r} is not in the rendered text of {loc.message_id}")
    for rec in index.values():
        path = c.root / rec["eml"]
        if not path.exists():
            r.error("V20", f"{rec['eml']} is missing")
    return r


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


_EXT_FOR = {
    "application/pdf": ("pdf",),
    "image/png": ("png",),
    "image/jpeg": ("jpg", "jpeg"),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ("docx",),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ("xlsx",),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ("pptx",),
    "text/plain": ("txt",),
}

_REL_KINDS = {
    "REFERS_TO": {("span", "occurrence")},
    "CONTRADICTS": {("fact_value", "fact_value")},
    "NEAR_COPY_OF": {("message", "message"), ("version", "version")},
    "DERIVED_FROM": {("version", "thread"), ("version", "version"), ("version", "message")},
}


def main(root: str) -> int:
    c = Corpus.load(Path(root))
    rep = validate(c)
    if rep.ok:
        rendered = validate_rendered(c)
        rep.errors += rendered.errors
        rep.warnings += rendered.warnings
    print(rep)
    return 0 if rep.ok else 1
