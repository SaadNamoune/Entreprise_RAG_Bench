"""Render the messages of a corpus as real email: RFC 5322 / MIME files and one journal mbox.

The structured tables are the ground truth; the rendered mail is what a system under test
ingests, the same way it ingests a mailbox (design document, decision A-2). Rendering is
deterministic: fixed MIME boundaries, no clock, no random ids, so a file's hash is stable.

Rendering also produces the copies that quoting and forwarding create: every span of a quoted
or forwarded message whose anchor appears in the history under the new text becomes a derived
span of the new message (origin ``quoted`` or ``forwarded``), so the gold evidence of a
question always lists every place the value can be retrieved from.
"""

from __future__ import annotations

import html
import json
import mailbox
import re
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from email.message import EmailMessage
from email.utils import format_datetime, formataddr
from pathlib import Path
from typing import Any

from mate.corpus import Corpus
from mate.schema import LocKind, Span, SpanOrigin

_PLACEHOLDER = re.compile(r"\{\{img:(occ-[a-z0-9-]+)\}\}")

_MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
           "September", "Oktober", "November", "Dezember"],
}
_DAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
}
_LABELS = {
    "en": {"original": "-----Original Message-----", "from": "From", "sent": "Sent", "to": "To",
           "cc": "Cc", "subject": "Subject", "forwarded": "---------- Forwarded message ---------",
           "date": "Date", "wrote": "{date}, {who} wrote:", "on": "On"},
    "de": {"original": "-----Ursprüngliche Nachricht-----", "from": "Von", "sent": "Gesendet",
           "to": "An", "cc": "Cc", "subject": "Betreff",
           "forwarded": "---------- Weitergeleitete Nachricht ----------", "date": "Datum",
           "wrote": "{date} schrieb {who}:", "on": "Am"},
}
_LANGUAGE_TAG = {"de": "de-DE", "en": "en-GB"}


def client_date(when: datetime, lang: str) -> str:
    """A date as a mail client writes it in a quote header."""
    day = _DAYS[lang][when.weekday()]
    month = _MONTHS[lang][when.month - 1]
    if lang == "de":
        return f"{day}, {when.day}. {month} {when.year} {when:%H:%M}"
    return f"{day}, {when.day} {month} {when.year} {when:%H:%M}"


@dataclass
class Rendered:
    message_id: str
    rfc_message_id: str
    eml: str
    text: str  # the text/plain part, as a system that reads the plain part sees it
    parts: list[dict[str, Any]] = field(default_factory=list)


class Renderer:
    def __init__(self, corpus: Corpus):
        self.c = corpus
        self.people = corpus.by_id("people")
        self.orgs = corpus.by_id("organisations")
        self.versions = corpus.by_id("versions")
        self.messages = corpus.by_id("messages")
        self.texts: dict[str, str] = {}

    # -------------------------------------------------------------- text

    def _who(self, person_id: str) -> str:
        p = self.people[person_id]
        return f"{p.name} <{p.email}>"

    def _signature(self, person_id: str) -> str:
        p = self.people[person_id]
        return p.signature or f"{p.name}\n{p.title}\n{self.orgs[p.org_id].name}"

    def _new_text(self, msg) -> str:
        occs = {o.id: o for o in self.c.occurrences_of_message(msg.id)}
        return _PLACEHOLDER.sub(lambda m: f"[image: {occs[m.group(1)].filename}]", msg.body.text).strip()

    def _history(self, msg) -> str:
        """The block under the new text: quoted reply history or forwarded message."""
        quote = msg.body.quote
        if quote is None or quote.style == "none":
            return ""
        src = self.messages[quote.message_id]
        src_text = self.texts[src.id]
        lab = _LABELS[msg.language]
        if msg.kind == "forward":
            lines = [lab["forwarded"], f"{lab['from']}: {self._who(src.sender)}",
                     f"{lab['date']}: {client_date(src.sent_at, msg.language)}",
                     f"{lab['subject']}: {src.subject}",
                     f"{lab['to']}: {', '.join(self._who(p) for p in src.to)}"]
            if src.cc:
                lines.append(f"{lab['cc']}: {', '.join(self._who(p) for p in src.cc)}")
            return "\n".join(lines) + "\n\n" + src_text
        if quote.style == "outlook_header":
            lines = [lab["original"], f"{lab['from']}: {self._who(src.sender)}",
                     f"{lab['sent']}: {client_date(src.sent_at, msg.language)}",
                     f"{lab['to']}: {'; '.join(self._who(p) for p in src.to)}"]
            if src.cc:
                lines.append(f"{lab['cc']}: {'; '.join(self._who(p) for p in src.cc)}")
            lines.append(f"{lab['subject']}: {src.subject}")
            return "\n".join(lines) + "\n\n" + src_text
        # prefix_gt
        head = f"{lab['on']} " + lab["wrote"].format(
            date=client_date(src.sent_at, msg.language), who=self._who(src.sender))
        quoted = "\n".join(f"> {line}" if line else ">" for line in src_text.splitlines())
        return head + "\n" + quoted

    def plain_text(self, msg) -> str:
        parts = [self._new_text(msg)]
        if msg.body.signature:
            parts.append(self._signature(msg.sender))
        org = self.orgs[self.people[msg.sender].org_id]
        if msg.body.disclaimer and org.disclaimer:
            parts.append(org.disclaimer)
        history = self._history(msg)
        if history:
            parts.append(history)
        return "\n\n".join(p for p in parts if p) + "\n"

    def html_text(self, msg) -> str:
        occs = {o.id: o for o in self.c.occurrences_of_message(msg.id)}

        def para(block: str) -> str:
            out = []
            pos = 0
            for m in _PLACEHOLDER.finditer(block):
                out.append(html.escape(block[pos:m.start()]).replace("\n", "<br>"))
                occ = occs[m.group(1)]
                out.append(f'<img src="cid:{occ.content_id}" alt="{html.escape(occ.filename)}">')
                pos = m.end()
            out.append(html.escape(block[pos:]).replace("\n", "<br>"))
            return f"<p>{''.join(out)}</p>"

        body = [para(b) for b in msg.body.text.strip().split("\n\n")]
        if msg.body.signature:
            sig = html.escape(self._signature(msg.sender)).replace("\n", "<br>")
            logos = "".join(f'<br><img src="cid:{o.content_id}" alt="{html.escape(o.filename)}">'
                            for o in occs.values() if o.role == "inline_decorative")
            body.append(f'<p class="signature">{sig}{logos}</p>')
        org = self.orgs[self.people[msg.sender].org_id]
        if msg.body.disclaimer and org.disclaimer:
            body.append(f'<p class="disclaimer"><small>{html.escape(org.disclaimer)}</small></p>')
        history = self._history(msg)
        if history:
            body.append("<blockquote>" + html.escape(history).replace("\n", "<br>") + "</blockquote>")
        lang = _LANGUAGE_TAG[msg.language]
        return f'<html lang="{lang}"><body>{"".join(body)}</body></html>\n'

    # -------------------------------------------------------------- mime

    def mime(self, msg) -> tuple[EmailMessage, list[dict[str, Any]]]:
        sender = self.people[msg.sender]
        m = EmailMessage(policy=policy.SMTP)
        m["From"] = formataddr((sender.name, sender.email))
        m["To"] = ", ".join(formataddr((self.people[p].name, self.people[p].email)) for p in msg.to)
        if msg.cc:
            m["Cc"] = ", ".join(formataddr((self.people[p].name, self.people[p].email)) for p in msg.cc)
        m["Subject"] = msg.subject
        m["Date"] = format_datetime(msg.sent_at)
        m["Message-ID"] = msg.rfc_message_id
        parent = msg.in_reply_to or msg.forward_of
        if parent:
            chain = [self.messages[x].rfc_message_id for x in self.c.thread_chain(msg.id)]
            if msg.in_reply_to:
                m["In-Reply-To"] = self.messages[parent].rfc_message_id
            m["References"] = " ".join(chain)
        m["Content-Language"] = _LANGUAGE_TAG[msg.language]
        m.set_content(self.texts[msg.id], charset="utf-8")

        occs = self.c.occurrences_of_message(msg.id)
        inline = [o for o in occs if o.role in ("inline", "inline_decorative")]
        appended = [o for o in occs if o.role == "appended"]
        if any(o.role == "forwarded_embedded" for o in occs):
            raise NotImplementedError(f"{msg.id}: forwarded_embedded occurrences are not rendered yet")

        if msg.body.html or inline:
            m.add_alternative(self.html_text(msg), subtype="html", charset="utf-8")
            html_part = m.get_payload()[1]
            for o in inline:
                data, main, sub = self._file(o)
                html_part.add_related(data, main, sub, cid=f"<{o.content_id}>", filename=o.filename,
                                      disposition="inline")
        for o in appended:
            data, main, sub = self._file(o)
            m.add_attachment(data, maintype=main, subtype=sub, filename=o.filename)

        # Fixed boundaries: the same corpus always gives the same bytes.
        for i, part in enumerate(p for p in m.walk() if p.is_multipart()):
            part.set_boundary(f"=_mate_{msg.id}_{i}")

        parts: list[dict[str, Any]] = []
        position = 0
        platform_index = 0
        by_cid = {o.content_id: o for o in inline}
        by_name = {o.filename: o for o in appended}
        for part in m.walk():
            if part.is_multipart() or part.get_content_maintype() == "text" and not part.get_filename():
                continue
            cid = (part.get("Content-ID") or "").strip("<>")
            occ = by_cid.get(cid) if cid else by_name.get(part.get_filename())
            entry = {"occurrence_id": occ.id if occ else None, "role": occ.role if occ else None,
                     "filename": part.get_filename(), "content_id": cid or None,
                     "mime_position": position, "platform_attachment_index": None}
            if not cid:
                # A system that, like the platform, counts only parts the body does not show.
                entry["platform_attachment_index"] = platform_index
                platform_index += 1
            parts.append(entry)
            position += 1
        return m, parts

    def _file(self, occ) -> tuple[bytes, str, str]:
        version = self.versions[occ.version_id]
        data = (self.c.root / version.file.path).read_bytes()
        main, sub = version.file.media_type.split("/", 1)
        return data, main, sub

    # -------------------------------------------------------------- spans

    def _copy_spans(self, msg, text: str) -> list[Span]:
        """Spans of the quoted or forwarded message that the history repeats, as copies."""
        quote = msg.body.quote
        if quote is None or quote.style == "none":
            return []
        kind = LocKind.forwarded_body if msg.kind == "forward" else LocKind.quoted_body
        origin = SpanOrigin.forwarded if msg.kind == "forward" else SpanOrigin.quoted
        history_start = text.find(self._history(msg).splitlines()[0])
        history = text[history_start:] if history_start >= 0 else ""
        out = []
        for span in self.c.spans:
            loc = span.location
            if loc.message_id != quote.message_id or loc.kind == "file" or span.fact_value_id is None:
                continue  # reference sentences point at their own message's file, not at copies
            if span.anchor not in history:
                continue
            suffix = msg.id.removeprefix("msg-")
            out.append(Span(
                id=f"{span.id}-in-{suffix}",
                fact_value_id=span.fact_value_id,
                location={"kind": kind, "message_id": msg.id},
                anchor=span.anchor,
                origin=origin,
                copy_of=span.copy_of or span.id,
                derived=True,
            ))
        return out

    # -------------------------------------------------------------- run

    def render(self, out_dir: Path | None = None) -> list[Rendered]:
        out_dir = out_dir or self.c.root / "rendered"
        eml_dir = out_dir / "eml"
        eml_dir.mkdir(parents=True, exist_ok=True)
        # Derived spans are rebuilt from scratch on every render.
        self.c.tables["spans"] = [s for s in self.c.spans if not s.derived]
        results: list[Rendered] = []
        journal_path = out_dir / "journal.mbox"
        journal_path.unlink(missing_ok=True)
        journal = mailbox.mbox(journal_path, create=True)
        try:
            for msg in sorted(self.c.messages, key=lambda x: (x.sent_at, x.id)):
                text = self.plain_text(msg)
                self.texts[msg.id] = text
                # Copies are added before later messages quote this one, so history nests.
                self.c.tables["spans"].extend(self._copy_spans(msg, text))
                mime, parts = self.mime(msg)
                path = eml_dir / f"{msg.id}.eml"
                path.write_bytes(mime.as_bytes(policy=policy.SMTP))
                journal.add(mime)
                results.append(Rendered(msg.id, msg.rfc_message_id,
                                        path.relative_to(self.c.root).as_posix(), text, parts))
        finally:
            journal.close()
        with (out_dir / "index.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
            for r in results:
                fh.write(json.dumps(r.__dict__, ensure_ascii=False) + "\n")
        return results


def render_corpus(corpus: Corpus, out_dir: Path | None = None) -> list[Rendered]:
    return Renderer(corpus).render(out_dir)
