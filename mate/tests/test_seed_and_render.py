import email
import json
from email import policy

from mate.corpus import Corpus, sha256_file
from mate.render_eml import render_corpus
from mate.validate import validate, validate_rendered


def _eml(root, mid):
    return email.message_from_bytes((root / "rendered" / "eml" / f"{mid}.eml").read_bytes(), policy=policy.default)


def test_seed_is_valid(seed_dir):
    c = Corpus.load(seed_dir)
    assert validate(c).ok
    assert validate_rendered(c).ok
    assert len(c.questions) == 15
    # 30 spans written by hand; 13 copies made by quoting and forwarding (3 of them of the old price)
    assert sum(1 for s in c.spans if not s.derived) == 30
    assert sum(1 for s in c.spans if s.derived) == 13


def test_rendering_is_deterministic(seed_copy):
    before = {p.name: sha256_file(p) for p in (seed_copy / "rendered" / "eml").glob("*.eml")}
    c = Corpus.load(seed_copy)
    render_corpus(c)
    after = {p.name: sha256_file(p) for p in (seed_copy / "rendered" / "eml").glob("*.eml")}
    assert before == after


def test_thread_headers(seed_dir):
    c = Corpus.load(seed_dir)
    rfc = {m.id: m.rfc_message_id for m in c.messages}
    m3 = _eml(seed_dir, "msg-03")
    assert m3["In-Reply-To"] == rfc["msg-02"]
    assert m3["References"].split() == [rfc["msg-01"], rfc["msg-02"]]
    fwd = _eml(seed_dir, "msg-04")
    assert fwd["In-Reply-To"] is None  # a forward starts a new branch, it does not reply
    assert fwd["References"].split()[-1] == rfc["msg-03"]


def test_bcc_is_in_the_truth_but_not_in_the_delivered_mail(seed_dir):
    c = Corpus.load(seed_dir)
    m1 = next(m for m in c.messages if m.id == "msg-01")
    assert m1.bcc == ["per-amy-shaw"]
    eml = _eml(seed_dir, "msg-01")
    assert eml["Bcc"] is None
    assert "amy.shaw" not in (seed_dir / "rendered" / "eml" / "msg-01.eml").read_text(encoding="utf-8")


def test_inline_image_is_related_and_referenced(seed_dir):
    m = _eml(seed_dir, "msg-05")
    html = m.get_body(preferencelist=("html",)).get_content()
    images = [p for p in m.walk() if p.get_content_type() == "image/png"]
    assert len(images) == 1
    cid = images[0]["Content-ID"].strip("<>")
    assert f"cid:{cid}" in html
    assert images[0].get_content_disposition() == "inline"
    attachments = [p.get_filename() for p in m.iter_attachments()]
    assert "Pruefbericht_P200.docx" in attachments
    plain = m.get_body(preferencelist=("plain",)).get_content()
    assert "[image: Kennlinie_P-200.png]" in plain


def test_quote_styles(seed_dir):
    index = {json.loads(line)["message_id"]: json.loads(line)
             for line in (seed_dir / "rendered" / "index.jsonl").read_text(encoding="utf-8").splitlines()}
    assert "-----Original Message-----" in index["msg-02"]["text"]
    assert "\n> Dear Mr Reed," in index["msg-03"]["text"]
    assert "---------- Weitergeleitete Nachricht ----------" in index["msg-04"]["text"]
    assert "-----Ursprüngliche Nachricht-----" in index["msg-06"]["text"]


def test_platform_attachment_index_skips_inline_parts(seed_dir):
    index = {json.loads(line)["message_id"]: json.loads(line)
             for line in (seed_dir / "rendered" / "index.jsonl").read_text(encoding="utf-8").splitlines()}
    parts = index["msg-04"]["parts"]
    logo = next(p for p in parts if p["role"] == "inline_decorative")
    offer = next(p for p in parts if p["role"] == "appended")
    assert logo["platform_attachment_index"] is None
    assert offer["platform_attachment_index"] == 0


def test_superseded_value_is_copied_into_later_history(seed_dir):
    c = Corpus.load(seed_dir)
    copies = [s for s in c.spans if s.fact_value_id == "fv-price-v1" and s.derived]
    assert {s.location.message_id for s in copies} == {"msg-02", "msg-03", "msg-04"}
    assert all(s.copy_of == "spn-002" for s in copies)
