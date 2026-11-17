"""Build the seed corpus: one small project that exercises every part of the schema.

Run from the ``mate`` folder:  python examples/seed/build_seed.py

The scenario (design document, appendix A): Donaumetall GmbH, a German manufacturer, buys two
P-200 pumps from Hydrova Pumps Ltd for the project "Pumpstation Nord".

- An offer is sent (v1), the buyer asks for a shorter delivery time, a revised offer (v2)
  supersedes v1 and is then forwarded with its file to an engineer (a re-sent copy).
- The engineer answers with an inline chart (the value is only in the pixels) and a DOCX test
  report; an out-of-office auto-reply follows.
- Controlling sends the budget as an XLSX; the supplier's e-mail states a warranty that
  contradicts the offer (never resolved); logistics sends a scanned delivery note (no text layer).
- A newsletter with pump prices is the background noise.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from mate import filebuilders as fb  # noqa: E402
from mate.corpus import Corpus, sha256_file  # noqa: E402
from mate.render_eml import render_corpus  # noqa: E402
from mate.schema import (  # noqa: E402
    Artifact, ArtifactVersion, Degradation, Fact, FactValue, FileRef, Manifest, Message, Occurrence,
    Organisation, Person, Project, Question, Relation, Span, Thread, Injection, QTYPE_FAMILY,
)
from mate.validate import validate, validate_rendered  # noqa: E402

CET = timezone(timedelta(hours=1))
OUT = HERE / "corpus"


def t(month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2027, month, day, hour, minute, tzinfo=CET)


class Builder:
    def __init__(self, root: Path):
        self.c = Corpus(root=root)
        self.n_span = 0

    def add(self, table: str, record):
        return self.c.add(table, record)

    def span(self, anchor: str, kind: str, fv: str | None = None, *, msg: str | None = None,
             ver: str | None = None, page: int | None = None, part: str | None = None,
             region: str | None = None, origin: str = "original") -> str:
        self.n_span += 1
        sid = f"spn-{self.n_span:03d}"
        self.add("spans", Span(id=sid, fact_value_id=fv, anchor=anchor, origin=origin,
                               location={"kind": kind, "message_id": msg, "version_id": ver,
                                         "page": page, "part": part, "region": region}))
        return sid

    def version(self, vid: str, artifact: str, label: str, created: datetime, author: str,
                modality: str, rel_path: str, media_type: str, pages: int | None = None, **extra):
        path = self.c.root / rel_path
        self.add("versions", ArtifactVersion(
            id=vid, artifact_id=artifact, label=label, created_at=created, author=author,
            modality=modality, file=FileRef(path=rel_path, media_type=media_type,
                                            sha256=sha256_file(path), bytes=path.stat().st_size,
                                            pages=pages), **extra))


PDF = "application/pdf"
PNG = "image/png"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def build(out: Path = OUT) -> Corpus:
    if out.exists():
        for p in sorted(out.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
    b = Builder(out)
    add = b.add

    # ------------------------------------------------------------------ world
    add("organisations", Organisation(
        id="org-donaumetall", name="Donaumetall GmbH", domain="donaumetall.example", kind="internal",
        language="de",
        disclaimer="Donaumetall GmbH · Sitz: Deggendorf · Registergericht Deggendorf HRB 0000\n"
                   "Diese E-Mail kann vertrauliche Informationen enthalten. Wenn Sie nicht der richtige "
                   "Adressat sind, informieren Sie bitte den Absender und löschen Sie diese E-Mail."))
    add("organisations", Organisation(
        id="org-hydrova", name="Hydrova Pumps Ltd", domain="hydrova.example", kind="supplier", language="en",
        disclaimer="Hydrova Pumps Ltd · Registered in England and Wales No. 00000000\n"
                   "This email and any attachments are confidential and intended solely for the addressee."))
    add("organisations", Organisation(
        id="org-ipr", name="Industrie-Pumpen-Report", domain="industrie-report.example", kind="service",
        language="de"))

    people = [
        ("per-lena-vogt", "Lena Vogt", "lena.vogt@donaumetall.example", "org-donaumetall",
         "Einkauf", 2, ["de", "en"], "Lena Vogt\nEinkauf | Donaumetall GmbH\nTel. +49 991 0000-214"),
        ("per-jonas-becker", "Jonas Becker", "jonas.becker@donaumetall.example", "org-donaumetall",
         "Technik / Anlagenbau", 2, ["de", "en"], None),
        ("per-marco-huber", "Marco Huber", "marco.huber@donaumetall.example", "org-donaumetall",
         "Controlling", 3, ["de"], None),
        ("per-tom-reed", "Tom Reed", "tom.reed@hydrova.example", "org-hydrova", "Sales Manager", 2, ["en"],
         "Tom Reed | Sales Manager\nHydrova Pumps Ltd\n+44 0000 000 112"),
        ("per-amy-shaw", "Amy Shaw", "amy.shaw@hydrova.example", "org-hydrova", "Logistics Coordinator", 1,
         ["en"], None),
        ("per-ipr-redaktion", "Redaktion Industrie-Pumpen-Report", "newsletter@industrie-report.example",
         "org-ipr", "Redaktion", 0, ["de"], None),
    ]
    for pid, name, email, org, title, auth, langs, sig in people:
        add("people", Person(id=pid, name=name, email=email, org_id=org, title=title, authority=auth,
                             languages=langs, signature=sig))

    add("projects", Project(
        id="prj-pumpstation-nord", name="Pumpstation Nord – Erneuerung der Förderpumpen", codename="PSN",
        owner_org_id="org-donaumetall", language="de", start=date(2027, 1, 4),
        description="Replacement of the two feed pumps of the northern pumping station."))

    # -------------------------------------------------------------- knowledge
    P = "prj-pumpstation-nord"
    facts = [
        ("fct-unit-price", "Hydrova offer HP-2041", "unit price per P-200 pump", "money", "EUR"),
        ("fct-delivery-time", "Hydrova offer HP-2041", "delivery time after order", "duration", None),
        ("fct-offer-number", "Hydrova offer", "offer number", "identifier", None),
        ("fct-required-date", "P-200 pumps", "date by which both pumps must be on site", "date", None),
        ("fct-head", "P-200 pump", "head at rated flow", "quantity", "m"),
        ("fct-test-pressure", "P-200 pump", "test pressure", "quantity", "bar"),
        ("fct-budget", "P-200 pumps", "approved budget", "money", "EUR"),
        ("fct-warranty", "P-200 pumps", "warranty period", "duration", None),
        ("fct-dn-number", "delivery of the P-200 pumps", "delivery note number", "identifier", None),
        ("fct-delivery-date", "delivery of the P-200 pumps", "delivery date", "date", None),
        ("fct-dn-sent", "delivery note", "date Hydrova sent the delivery note", "date", None),
        ("fct-forwarder", "revised offer HP-2041", "who forwarded it for technical review", "person", None),
        ("fct-reviewer", "revised offer HP-2041", "who received it for technical review", "person", None),
    ]
    for fid, subject, attribute, vtype, unit in facts:
        add("facts", Fact(id=fid, project_id=P, subject=subject, attribute=attribute, value_type=vtype, unit=unit))

    def fv(vid, fact, value, en, de, start, end=None, supersedes=None, standing="valid", by=None):
        add("fact_values", FactValue(id=vid, fact_id=fact, value=value, surfaces={"en": en, "de": de},
                                     valid_from=start, valid_to=end, supersedes=supersedes,
                                     standing=standing, asserted_by=by))

    m01, m03 = t(1, 11, 9, 12), t(1, 18, 10, 5)
    fv("fv-price-v1", "fct-unit-price", "48370.00 EUR", ["€48,370"], ["48.370 €"], m01, m03, by="per-tom-reed")
    fv("fv-price-v2", "fct-unit-price", "47950.00 EUR", ["€47,950"], ["47.950 €"], m03, None, "fv-price-v1",
       by="per-tom-reed")
    fv("fv-deliv-v1", "fct-delivery-time", "14 weeks", ["14 weeks"], ["14 Wochen"], m01, m03, by="per-tom-reed")
    fv("fv-deliv-v2", "fct-delivery-time", "9 weeks", ["9 weeks"], ["9 Wochen"], m03, None, "fv-deliv-v1",
       by="per-tom-reed")
    fv("fv-offer-no", "fct-offer-number", "HP-2041", ["HP-2041"], ["HP-2041"], m01)
    fv("fv-required-date", "fct-required-date", "2027-04-30", ["30 April 2027"], ["30. April 2027"],
       t(1, 13, 14, 30), by="per-lena-vogt")
    fv("fv-head", "fct-head", "62 m", ["62 m"], ["62 m"], t(1, 20, 16, 40), by="per-jonas-becker")
    fv("fv-test-pressure", "fct-test-pressure", "16 bar", ["16 bar"], ["16 bar"], t(1, 20, 16, 40))
    fv("fv-budget", "fct-budget", "95000.00 EUR", ["€95,000"], ["95.000 €"], t(1, 25, 10), by="per-marco-huber")
    fv("fv-warranty-offer", "fct-warranty", "36 months", ["36 months"], ["36 Monate"], m01,
       standing="contested", by="per-tom-reed")
    fv("fv-warranty-mail", "fct-warranty", "24 months", ["24 months"], ["24 Monate"], t(2, 26, 13),
       standing="contested", by="per-tom-reed")
    fv("fv-dn-number", "fct-dn-number", "LS-77815", ["LS-77815"], ["LS-77815"], t(3, 1, 8))
    fv("fv-delivery-date", "fct-delivery-date", "2027-03-01", ["1 March 2027"], ["1. März 2027", "01.03.2027"],
       t(3, 1, 8))
    fv("fv-dn-sent", "fct-dn-sent", "2027-03-02", ["2 March 2027"], ["2. März 2027"], t(3, 2, 9, 30))
    fv("fv-forwarder", "fct-forwarder", "Lena Vogt", ["Lena Vogt"], ["Lena Vogt"], t(1, 18, 11, 20))
    fv("fv-reviewer", "fct-reviewer", "Jonas Becker", ["Jonas Becker"], ["Jonas Becker"], t(1, 18, 11, 20))

    # ---------------------------------------------------------------- files
    root = b.c.root
    offer_rows_v1 = [["Item", "Quantity", "Unit price"], ["P-200 centrifugal pump", "2", "€48,370"],
                     ["Delivery time", "14 weeks after order", ""], ["Warranty", "36 months", ""]]
    offer_rows_v2 = [["Item", "Quantity", "Unit price"], ["P-200 centrifugal pump", "2", "€47,950"],
                     ["Delivery time", "9 weeks after order", ""], ["Warranty", "36 months", ""]]
    p1 = fb.build_pdf(root / "files/ver-offer-v1.pdf", [
        fb.Block("title", "OFFER HP-2041"),
        fb.Block("paragraph", "Customer: Donaumetall GmbH, project Pumpstation Nord. Date: 11 January 2027."),
        fb.Block("table", rows=offer_rows_v1),
        fb.Block("paragraph", "Prices excluding VAT, ex works. Valid for 30 days."),
    ], header="Hydrova Pumps Ltd")
    p2 = fb.build_pdf(root / "files/ver-offer-v2.pdf", [
        fb.Block("title", "OFFER HP-2041 - Revision 1"),
        fb.Block("paragraph", "Customer: Donaumetall GmbH, project Pumpstation Nord. Date: 18 January 2027. "
                              "This revision replaces the offer of 11 January 2027."),
        fb.Block("table", rows=offer_rows_v2),
        fb.Block("paragraph", "Prices excluding VAT, ex works. Valid for 30 days."),
    ], header="Hydrova Pumps Ltd")
    flow = [0, 20, 40, 60, 80, 100, 120]
    fb.build_chart_png(root / "files/ver-chart-v1.png", "Kennlinie P-200", flow,
                       [78, 76, 72, 66, 62, 55, 46], "Förderstrom [m³/h]", "Förderhöhe [m]",
                       (80, 62), "Förderhöhe bei Nennförderstrom: 62 m")
    fb.build_docx(root / "files/ver-report-v1.docx", [
        fb.Block("title", "Prüfbericht P-200"),
        fb.Block("paragraph", "Projekt: Pumpstation Nord (PSN). Prüfer: Jonas Becker. Datum: 20.01.2027."),
        fb.Block("table", rows=[["Prüfung", "Wert", "Ergebnis"], ["Druckprüfung", "Prüfdruck 16 bar", "bestanden"],
                                ["Dichtheit", "keine Leckage", "bestanden"]]),
        fb.Block("paragraph", "Ergebnis: Die Pumpe erfüllt die Anforderungen. Freigabe zur Bestellung."),
    ], when=datetime(2027, 1, 20, 15, 0), author="Jonas Becker")
    fb.build_xlsx(root / "files/ver-budget-v1.xlsx", "Budget Q1 2027", [
        ["Position", "Projekt", "Betrag", "Status"], ["Pumpen P-200", "PSN", "95.000 €", "freigegeben"],
        ["Elektrik", "PSN", "18.400 €", "geplant"], ["Montage", "PSN", "12.750 €", "geplant"],
    ], author="Marco Huber")
    dn_lines = ["Hydrova Pumps Ltd", "LIEFERSCHEIN / DELIVERY NOTE", "Nr. LS-77815", "Datum: 01.03.2027",
                "Empfänger: Donaumetall GmbH, Pumpstation Nord",
                "2 x P-200 Kreiselpumpe, SN 55210-A, SN 55210-B"]
    fb.build_scan_pdf(root / "files/ver-dn-v1.pdf", dn_lines, dpi=150, noise=0.08, skew_degrees=1.2,
                      jpeg_quality=70, seed=7)
    fb.build_logo_png(root / "files/ver-logo-v1.png", "DONAUMETALL")

    # ------------------------------------------------------------ artifacts
    for aid, kind, title, owner in [
        ("art-offer-hp2041", "offer", "Offer HP-2041 for two P-200 pumps", "per-tom-reed"),
        ("art-pump-curve", "chart", "Kennlinie P-200", "per-jonas-becker"),
        ("art-test-report", "test_report", "Prüfbericht P-200", "per-jonas-becker"),
        ("art-budget", "spreadsheet", "Budget Q1 2027", "per-marco-huber"),
        ("art-delivery-note", "delivery_note", "Lieferschein LS-77815", "per-amy-shaw"),
        ("art-logo", "logo", "Donaumetall logo", "per-lena-vogt"),
    ]:
        add("artifacts", Artifact(id=aid, project_id=None if kind == "logo" else P, kind=kind, title=title,
                                  owner=owner))
    b.version("ver-offer-v1", "art-offer-hp2041", "v1", t(1, 11, 8, 40), "per-tom-reed", "text_document",
              "files/ver-offer-v1.pdf", PDF, p1)
    b.version("ver-offer-v2", "art-offer-hp2041", "Revision 1", t(1, 18, 9, 50), "per-tom-reed", "text_document",
              "files/ver-offer-v2.pdf", PDF, p2, supersedes="ver-offer-v1",
              change_note="delivery time 14 -> 9 weeks, unit price reduced")
    b.version("ver-chart-v1", "art-pump-curve", "v1", t(1, 20, 15, 0), "per-jonas-becker", "chart_image",
              "files/ver-chart-v1.png", PNG,
              text_in_image=["Kennlinie P-200", "Förderhöhe bei Nennförderstrom: 62 m", "62 m"])
    b.version("ver-report-v1", "art-test-report", "v1", t(1, 20, 15, 0), "per-jonas-becker", "text_document",
              "files/ver-report-v1.docx", DOCX)
    b.version("ver-budget-v1", "art-budget", "v1", t(1, 24, 17, 0), "per-marco-huber", "spreadsheet",
              "files/ver-budget-v1.xlsx", XLSX)
    b.version("ver-dn-v1", "art-delivery-note", "v1", t(3, 1, 8, 0), "per-amy-shaw", "scanned_document",
              "files/ver-dn-v1.pdf", PDF, 1, text_in_image=dn_lines + ["LS-77815", "01.03.2027"],
              degradation=Degradation(dpi=150, noise=0.08, skew_degrees=1.2, jpeg_quality=70))
    b.version("ver-logo-v1", "art-logo", "v1", t(1, 4, 8, 0), "per-lena-vogt", "decorative_image",
              "files/ver-logo-v1.png", PNG)

    # ------------------------------------------------------------- threads
    for tid, subject, lang, kind, proj in [
        ("thr-offer", "Offer HP-2041 – 2 × P-200 pumps", "en", "project", P),
        ("thr-pruefung", "Technische Prüfung P-200 abgeschlossen", "de", "project", P),
        ("thr-budget", "Budget Pumpstation Nord 2027", "de", "project", P),
        ("thr-delivery", "P-200 order – warranty and delivery", "en", "project", P),
        ("thr-dn", "Delivery note – order P-200", "en", "project", P),
        ("thr-newsletter", "Industrie-Pumpen-Report 02/2027", "de", "newsletter", None),
    ]:
        add("threads", Thread(id=tid, subject=subject, language=lang, kind=kind, project_id=proj))

    def msg(mid, thread, kind, sender, to, when, subject, lang, text, cc=(), bcc=(), reply=None, fwd=None,
            quote=None, signature=True, disclaimer=True, html=True):
        add("messages", Message(
            id=mid, rfc_message_id=f"<{mid}.{when:%Y%m%d%H%M}@{_domain(b.c, sender)}>", thread_id=thread,
            kind=kind, in_reply_to=reply, forward_of=fwd, sender=sender, to=list(to), cc=list(cc), bcc=list(bcc),
            sent_at=when, subject=subject, language=lang,
            body={"text": text, "signature": signature, "disclaimer": disclaimer, "html": html,
                  "quote": quote}))

    def occ(oid, mid, ver, role, filename, order, cid=None):
        add("occurrences", Occurrence(id=oid, message_id=mid, version_id=ver, role=role, filename=filename,
                                      order=order, content_id=cid))

    LOGO = ("ver-logo-v1", "inline_decorative", "image001.png")
    lena, jonas, marco, tom, amy = ("per-lena-vogt", "per-jonas-becker", "per-marco-huber", "per-tom-reed",
                                    "per-amy-shaw")

    msg("msg-01", "thr-offer", "new", tom, [lena], m01, "Offer HP-2041 – 2 × P-200 pumps", "en",
        "Dear Ms Vogt,\n\nthank you for your enquiry. Please find attached our offer HP-2041 for two P-200 pumps "
        "for the Pumpstation Nord project.\n\nThe unit price is €48,370 and the delivery time is 14 weeks after "
        "order.\n\nKind regards,\nTom", bcc=[amy])
    occ("occ-01", "msg-01", "ver-offer-v1", "appended", "Offer_HP-2041.pdf", 0)

    msg("msg-02", "thr-offer", "reply", lena, [tom], t(1, 13, 14, 30), "Re: Offer HP-2041 – 2 × P-200 pumps",
        "en", "Dear Mr Reed,\n\nthank you for the offer. Can you shorten the delivery time? We need both pumps "
        "on site by 30 April 2027.\n\nBest regards", reply="msg-01",
        quote={"message_id": "msg-01", "style": "outlook_header"})
    occ("occ-02", "msg-02", *LOGO[:2], LOGO[2], 0, cid="logo.lv.0113@donaumetall.example")

    msg("msg-03", "thr-offer", "reply", tom, [lena], m03, "Re: Offer HP-2041 – 2 × P-200 pumps", "en",
        "Dear Ms Vogt,\n\nwe can do better on the delivery time. Please see the revised offer attached: delivery "
        "is now 9 weeks after order, and we reduced the unit price to €47,950.\n\nKind regards,\nTom",
        reply="msg-02", quote={"message_id": "msg-02", "style": "prefix_gt"})
    occ("occ-03", "msg-03", "ver-offer-v2", "appended", "Offer_HP-2041_rev1.pdf", 0)

    msg("msg-04", "thr-offer", "forward", lena, [jonas], t(1, 18, 11, 20),
        "WG: Re: Offer HP-2041 – 2 × P-200 pumps", "de",
        "Hallo Jonas,\n\nbitte prüf das überarbeitete Angebot von Hydrova im Anhang technisch. Die Lieferzeit "
        "beträgt jetzt 9 Wochen.\n\nDanke und Gruß", fwd="msg-03",
        quote={"message_id": "msg-03", "style": "outlook_header"})
    occ("occ-04", "msg-04", *LOGO[:2], LOGO[2], 0, cid="logo.lv.0118@donaumetall.example")
    occ("occ-05", "msg-04", "ver-offer-v2", "appended", "Offer_HP-2041_rev1.pdf", 1)

    msg("msg-05", "thr-pruefung", "new", jonas, [lena], t(1, 20, 16, 40), "Technische Prüfung P-200 abgeschlossen",
        "de", "Hallo Lena,\n\ndie technische Prüfung der P-200 ist abgeschlossen. Die Förderhöhe passt laut "
        "Kennlinie:\n\n{{img:occ-06}}\n\nDen Prüfbericht hänge ich an. Aus meiner Sicht können wir bestellen."
        "\n\nGruß\nJonas", cc=[marco])
    occ("occ-06", "msg-05", "ver-chart-v1", "inline", "Kennlinie_P-200.png", 0, cid="kennlinie.p200@donaumetall.example")
    occ("occ-07", "msg-05", "ver-report-v1", "appended", "Pruefbericht_P200.docx", 1)

    msg("msg-06", "thr-pruefung", "reply_all", lena, [jonas], t(1, 21, 8, 15),
        "AW: Technische Prüfung P-200 abgeschlossen", "de",
        "Danke, Jonas! Ich bestelle auf Basis des Angebots HP-2041 in der Revision vom 18.01.", cc=[marco],
        reply="msg-05", quote={"message_id": "msg-05", "style": "outlook_header"})
    occ("occ-08", "msg-06", *LOGO[:2], LOGO[2], 0, cid="logo.lv.0121@donaumetall.example")

    msg("msg-07", "thr-pruefung", "auto_reply", jonas, [lena], t(1, 21, 8, 16),
        "Automatische Antwort: AW: Technische Prüfung P-200 abgeschlossen", "de",
        "Vielen Dank für Ihre Nachricht. Ich bin bis einschließlich 29.01.2027 nicht im Büro. In dringenden "
        "Fällen wenden Sie sich bitte an technik@donaumetall.example.", reply="msg-06", signature=False,
        html=False)

    msg("msg-08", "thr-budget", "new", marco, [lena], t(1, 25, 10, 0), "Budget Pumpstation Nord 2027", "de",
        "Hallo Frau Vogt,\n\nfür die zwei P-200 sind laut Budgetplan 95.000 € freigegeben, siehe Tabelle im "
        "Anhang.\n\nViele Grüße\nMarco Huber")
    occ("occ-09", "msg-08", "ver-budget-v1", "appended", "Budget_2027_Q1.xlsx", 0)

    msg("msg-09", "thr-delivery", "new", tom, [lena], t(2, 26, 13, 0), "P-200 order – warranty and delivery", "en",
        "Dear Ms Vogt,\n\nthank you for your order. As agreed, the pumps come with a warranty of 24 months. We "
        "will deliver next week.\n\nKind regards,\nTom")

    msg("msg-10", "thr-dn", "new", amy, [lena], t(3, 2, 9, 30), "Delivery note – order P-200", "en",
        "Dear Ms Vogt,\n\nplease find attached the delivery note for your two P-200 pumps.\n\nBest regards,\nAmy "
        "Shaw", cc=[tom])
    occ("occ-10", "msg-10", "ver-dn-v1", "appended", "Lieferschein_LS-77815.pdf", 0)

    msg("msg-11", "thr-newsletter", "newsletter", "per-ipr-redaktion", [lena], t(2, 3, 7, 0),
        "Industrie-Pumpen-Report 02/2027", "de",
        "Marktüberblick Februar: Kreiselpumpen der 50-kW-Klasse kosten derzeit zwischen 41.000 € und 52.000 €. "
        "Die Lieferzeiten sind auf 10 bis 16 Wochen gestiegen. Mehr im Heft.", signature=False, disclaimer=False)

    # ---------------------------------------------------------------- spans
    s = b.span
    s("HP-2041", "body", "fv-offer-no", msg="msg-01")
    s("€48,370", "body", "fv-price-v1", msg="msg-01")
    s("14 weeks", "body", "fv-deliv-v1", msg="msg-01")
    s("30 April 2027", "body", "fv-required-date", msg="msg-02")
    s("9 weeks", "body", "fv-deliv-v2", msg="msg-03")
    s("€47,950", "body", "fv-price-v2", msg="msg-03")
    ref_offer = s("the revised offer attached", "body", None, msg="msg-03")
    s("9 Wochen", "body", "fv-deliv-v2", msg="msg-04", origin="restated")
    s("Lena Vogt", "header", "fv-forwarder", msg="msg-04", region="From")
    s("Jonas Becker", "header", "fv-reviewer", msg="msg-04", region="To")
    ref_curve = s("laut Kennlinie", "body", None, msg="msg-05")
    ref_report = s("Den Prüfbericht hänge ich an", "body", None, msg="msg-05")
    s("HP-2041", "body", "fv-offer-no", msg="msg-06", origin="restated")
    s("95.000 €", "body", "fv-budget", msg="msg-08")
    s("24 months", "body", "fv-warranty-mail", msg="msg-09")
    ref_dn = s("the delivery note", "body", None, msg="msg-10")
    s("2 March 2027", "header", "fv-dn-sent", msg="msg-10", region="Date")
    for ver, price, deliv in (("ver-offer-v1", ("€48,370", "fv-price-v1"), ("14 weeks", "fv-deliv-v1")),
                              ("ver-offer-v2", ("€47,950", "fv-price-v2"), ("9 weeks", "fv-deliv-v2"))):
        s("HP-2041", "file", "fv-offer-no", ver=ver, page=1, part="text", region="title")
        s(price[0], "file", price[1], ver=ver, page=1, part="table", region="row P-200")
        s(deliv[0], "file", deliv[1], ver=ver, page=1, part="table", region="row Delivery time")
        s("36 months", "file", "fv-warranty-offer", ver=ver, page=1, part="table", region="row Warranty")
    s("62 m", "file", "fv-head", ver="ver-chart-v1", part="image", region="annotation at rated flow")
    s("16 bar", "file", "fv-test-pressure", ver="ver-report-v1", part="table", region="row Druckprüfung")
    s("95.000 €", "file", "fv-budget", ver="ver-budget-v1", part="table", region="B2:C2")
    s("LS-77815", "file", "fv-dn-number", ver="ver-dn-v1", page=1, part="image", region="header")
    s("01.03.2027", "file", "fv-delivery-date", ver="ver-dn-v1", page=1, part="image", region="header")

    # ------------------------------------------------------- relations, log
    for i, (span_id, occ_id, deixis) in enumerate([(ref_offer, "occ-03", "local"), (ref_curve, "occ-06", "local"),
                                                   (ref_report, "occ-07", "local"), (ref_dn, "occ-10", "local")], 1):
        add("relations", Relation(id=f"rel-{i:03d}", type="REFERS_TO", source={"kind": "span", "id": span_id},
                                  target={"kind": "occurrence", "id": occ_id}, attrs={"deixis": deixis}))
    add("relations", Relation(id="rel-005", type="CONTRADICTS", source={"kind": "fact_value", "id": "fv-warranty-mail"},
                              target={"kind": "fact_value", "id": "fv-warranty-offer"}, attrs={"resolved": False}))
    for i, (kind, targets, note) in enumerate([
        ("supersession", [("version", "ver-offer-v2"), ("fact_value", "fv-price-v2"), ("fact_value", "fv-deliv-v2")],
         "revised offer replaces v1"),
        ("forward_copy", [("message", "msg-04"), ("occurrence", "occ-05")], "forward re-sends offer v2"),
        ("contradiction", [("fact_value", "fv-warranty-mail")], "e-mail warranty contradicts the offer"),
        ("auto_reply", [("message", "msg-07")], "out-of-office reply"),
        ("newsletter", [("message", "msg-11")], "market prices as distractors"),
        ("boilerplate", [("message", "msg-02"), ("message", "msg-04"), ("message", "msg-06")],
         "logo image and legal disclaimer in every Donaumetall message"),
    ], 1):
        add("injections", Injection(id=f"inj-{i:03d}", kind=kind,
                                    targets=[{"kind": k, "id": v} for k, v in targets], note=note))
    return b.c


def _domain(c: Corpus, person_id: str) -> str:
    return next(p.email.split("@")[1] for p in c.people if p.id == person_id)


def questions(c: Corpus) -> None:
    """Questions are written after rendering, so their gold lists the copies rendering created."""
    by_value = c.spans_by_value()
    occs = c.by_id("occurrences")

    def group(fv_id: str, where: set[str] | None = None) -> dict:
        spans = [sp.id for sp in by_value[fv_id]
                 if where is None or sp.location.version_id in where or sp.location.message_id in where]
        return {"fact_value_id": fv_id, "span_ids": spans}

    asked = t(3, 5, 10)
    qs = [
        dict(id="q-001", language="en", type="current_value", scope="current",
             text="What is the current unit price of a P-200 pump in Hydrova's offer HP-2041?",
             variants=[{"style": "indirect", "text": "Did Hydrova's price for the P-200 stay where it started?"}],
             answer={"kind": "value", "reference_text": "€47,950 per pump (revision of 18 January 2027).",
                     "accepted": ["€47,950", "47.950 €"], "superseded": ["€48,370", "48.370 €"],
                     "fact_value_ids": ["fv-price-v2"]},
             gold={"groups": [group("fv-price-v2")]},
             strata={"evidence_location": "mixed", "role": "appended", "modality": "text_document",
                     "version_state": "current_of_n", "n_versions": 2}),
        dict(id="q-002", language="de", type="as_of_value", scope="as_of", as_of=t(1, 15, 12),
             text="Welche Lieferzeit stand in Hydrovas Angebot HP-2041, das am 15. Januar 2027 gültig war?",
             answer={"kind": "value", "reference_text": "14 Wochen nach Bestellung (Angebot vom 11. Januar 2027).",
                     "accepted": ["14 Wochen", "14 weeks"], "superseded": ["9 Wochen", "9 weeks"],
                     "fact_value_ids": ["fv-deliv-v1"]},
             gold={"groups": [group("fv-deliv-v1")]},
             strata={"evidence_location": "mixed", "role": "appended", "modality": "text_document",
                     "version_state": "historical_of_n", "n_versions": 2}),
        dict(id="q-003", language="en", type="value_history", scope="history",
             text="How did the delivery time in Hydrova's offer HP-2041 change, and when?",
             answer={"kind": "values", "reference_text": "From 14 weeks (11 January 2027) to 9 weeks (revision of "
                                                         "18 January 2027).",
                     "accepted": ["14 weeks", "9 weeks"], "fact_value_ids": ["fv-deliv-v1", "fv-deliv-v2"]},
             gold={"groups": [group("fv-deliv-v1"), group("fv-deliv-v2")]},
             strata={"evidence_location": "mixed", "role": "appended", "modality": "text_document",
                     "version_state": "current_of_n", "n_versions": 2, "hops": 2}),
        dict(id="q-004", language="en", type="msg_to_attachment", scope="none",
             text="In the revised offer Tom Reed sent on 18 January 2027, how long is the warranty?",
             answer={"kind": "value", "reference_text": "36 months.", "accepted": ["36 months", "36 Monate"],
                     "fact_value_ids": ["fv-warranty-offer"]},
             gold={"groups": [group("fv-warranty-offer", {"ver-offer-v2"})], "required_occurrences": ["occ-03"]},
             strata={"evidence_location": "attachment", "role": "appended", "modality": "text_document",
                     "version_state": "current_of_n", "n_versions": 2, "direction": "m2a", "hops": 2}),
        dict(id="q-005", language="de", type="attachment_to_msg", scope="none",
             text="Wer hat das überarbeitete Hydrova-Angebot zur technischen Prüfung weitergeleitet, und an wen?",
             answer={"kind": "values", "reference_text": "Lena Vogt hat es am 18. Januar 2027 an Jonas Becker "
                                                         "weitergeleitet.",
                     "accepted": ["Lena Vogt", "Jonas Becker"], "fact_value_ids": ["fv-forwarder", "fv-reviewer"]},
             gold={"groups": [group("fv-forwarder"), group("fv-reviewer")], "required_occurrences": ["occ-05"]},
             strata={"evidence_location": "header", "role": "appended", "direction": "a2m", "hops": 2}),
        dict(id="q-006", language="de", type="fact_image", scope="none",
             text="Welche Förderhöhe hat die P-200 laut der Kennlinie, die Jonas geschickt hat?",
             answer={"kind": "value", "reference_text": "62 m bei Nennförderstrom.", "accepted": ["62 m"],
                     "fact_value_ids": ["fv-head"]},
             gold={"groups": [group("fv-head")], "required_occurrences": ["occ-06"]},
             strata={"evidence_location": "image", "role": "inline", "modality": "chart_image"}),
        dict(id="q-007", language="de", type="fact_attachment", scope="none",
             text="Mit welchem Prüfdruck wurde die P-200 geprüft?",
             answer={"kind": "value", "reference_text": "16 bar.", "accepted": ["16 bar"],
                     "fact_value_ids": ["fv-test-pressure"]},
             gold={"groups": [group("fv-test-pressure")], "required_occurrences": ["occ-07"]},
             strata={"evidence_location": "attachment", "role": "appended", "modality": "text_document"}),
        dict(id="q-008", language="en", type="fact_image", scope="none",
             text="What is the number of the delivery note for the P-200 pumps?",
             variants=[{"style": "keyword", "text": "P-200 delivery note number"}],
             answer={"kind": "value", "reference_text": "LS-77815.", "accepted": ["LS-77815"],
                     "fact_value_ids": ["fv-dn-number"]},
             gold={"groups": [group("fv-dn-number")], "required_occurrences": ["occ-10"]},
             strata={"evidence_location": "image", "role": "appended", "modality": "scanned_document"}),
        dict(id="q-009", language="en", type="contested", scope="current",
             text="How long is the warranty on the P-200 pumps?",
             answer={"kind": "contested", "reference_text": "The sources disagree: offer HP-2041 (both versions) "
                                                            "says 36 months, Tom Reed's e-mail of 26 February 2027 "
                                                            "says 24 months.",
                     "accepted": ["36 months", "24 months"], "fact_value_ids": ["fv-warranty-offer", "fv-warranty-mail"]},
             gold={"groups": [group("fv-warranty-offer"), group("fv-warranty-mail")]},
             strata={"evidence_location": "mixed", "role": "appended", "modality": "text_document", "hops": 2}),
        dict(id="q-010", language="en", type="count_distinct", scope="none",
             text="How many versions of offer HP-2041 did Hydrova send?",
             answer={"kind": "count", "reference_text": "Two: the offer of 11 January 2027 and its revision of "
                                                        "18 January 2027 (which was later forwarded internally, "
                                                        "not a third version).", "accepted": ["2", "two", "zwei"]},
             gold={"groups": [group("fv-offer-no", {"ver-offer-v1"}), group("fv-offer-no", {"ver-offer-v2"})]},
             strata={"evidence_location": "attachment", "role": "appended", "modality": "text_document",
                     "version_state": "current_of_n", "n_versions": 2, "hops": 2}),
        dict(id="q-011", language="en", type="metadata", scope="none",
             text="When did Hydrova send the delivery note?",
             answer={"kind": "date", "reference_text": "On 2 March 2027 (Amy Shaw, 09:30).",
                     "accepted": ["2 March 2027", "2. März 2027"], "fact_value_ids": ["fv-dn-sent"]},
             gold={"groups": [group("fv-dn-sent")]},
             strata={"evidence_location": "header"}),
        dict(id="q-012", language="en", type="unanswerable", scope="none",
             text="What discount did Hydrova grant in version 3 of offer HP-2041?",
             answer={"kind": "abstain", "reference_text": "There is no version 3: Hydrova sent two versions "
                                                          "(11 and 18 January 2027)."},
             gold={"groups": []}, strata={"evidence_location": "none"}, template="false_premise"),
        dict(id="q-013", language="de", type="fact_body", scope="none",
             text="Bis wann müssen beide Pumpen vor Ort sein?",
             answer={"kind": "date", "reference_text": "Bis zum 30. April 2027.",
                     "accepted": ["30. April 2027", "30 April 2027"], "fact_value_ids": ["fv-required-date"]},
             gold={"groups": [group("fv-required-date")]},
             strata={"evidence_location": "body"}),
        dict(id="q-014", language="de", type="fact_body", scope="current",
             text="Wie hoch ist das freigegebene Budget für die zwei P-200?",
             answer={"kind": "value", "reference_text": "95.000 € (Budgetplan Q1 2027).",
                     "accepted": ["95.000 €", "€95,000"], "fact_value_ids": ["fv-budget"]},
             gold={"groups": [group("fv-budget")], "required_occurrences": []},
             strata={"evidence_location": "mixed", "role": "appended", "modality": "spreadsheet"}),
        dict(id="q-015", language="en", type="thread_summary", scope="history",
             text="Summarise how offer HP-2041 was negotiated between Hydrova and Donaumetall.",
             answer={"kind": "summary", "reference_text": "Hydrova offered two P-200 pumps on 11 January 2027 at "
                     "€48,370 each with 14 weeks delivery; Donaumetall asked for delivery by 30 April 2027; on "
                     "18 January Hydrova revised the offer to €47,950 and 9 weeks; the revision was forwarded "
                     "for technical review.",
                     "accepted": ["€48,370", "14 weeks", "30 April 2027", "€47,950", "9 weeks"]},
             gold={"groups": [group(v) for v in ("fv-price-v1", "fv-deliv-v1", "fv-required-date", "fv-price-v2",
                                                 "fv-deliv-v2")], "min_coverage": 0.8},
             strata={"evidence_location": "mixed", "role": "appended", "version_state": "current_of_n",
                     "n_versions": 2, "hops": 5}),
    ]
    c.tables["questions"] = []
    for q in qs:
        q.setdefault("asked_at", asked)
        q["project_id"] = "prj-pumpstation-nord"
        groups = q["gold"]["groups"]
        q["strata"].setdefault("n_copies", max((len(g["span_ids"]) - 1 for g in groups), default=0))
        q["checks"] = [{"by": "auto", "check": "validator V12", "passed": True}]
        c.add("questions", Question.model_validate(q))
    assert all(q.type in QTYPE_FAMILY for q in c.questions)
    assert all(o in occs for q in c.questions for o in q.gold.required_occurrences)


def main(out: Path = OUT) -> int:
    c = build(out)
    c.save()
    render_corpus(c)
    questions(c)
    counts = {name: len(rows) for name, rows in c.tables.items()}
    files = {p.relative_to(out).as_posix(): sha256_file(p)
             for p in sorted((out / "rendered" / "eml").glob("*.eml"))}
    c.manifest = Manifest(name="MATE seed", corpus_version="0.1.0", created_at=t(3, 5, 12), seed=7,
                          generator="examples/seed/build_seed.py (hand-written scenario)",
                          languages=["de", "en"], licence="CC-BY-4.0 (proposed)", counts=counts,
                          splits={"dev": ["prj-pumpstation-nord"]}, files_sha256=files)
    c.save()
    report = validate(Corpus.load(out))
    rendered = validate_rendered(Corpus.load(out))
    print("counts:", counts)
    print("tables:", report)
    print("rendered:", rendered)
    return 0 if report.ok and rendered.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
