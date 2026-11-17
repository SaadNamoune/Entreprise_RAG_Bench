from datetime import timedelta

from mate.corpus import Corpus
from mate.validate import validate


def _codes(report):
    return {e.split()[0] for e in report.errors}


def test_future_leak_is_caught(seed_copy):
    c = Corpus.load(seed_copy)
    v = next(v for v in c.versions if v.id == "ver-offer-v1")
    v.created_at = v.created_at + timedelta(days=30)  # the file now exists only after it is sent
    assert "V06" in _codes(validate(c))


def test_bcc_cannot_also_be_a_visible_recipient(seed_copy):
    c = Corpus.load(seed_copy)
    m = next(m for m in c.messages if m.id == "msg-01")
    m.bcc.append("per-lena-vogt")  # Lena is already in To
    assert "V05" in _codes(validate(c))


def test_missing_anchor_is_caught(seed_copy):
    c = Corpus.load(seed_copy)
    m = next(m for m in c.messages if m.id == "msg-01")
    m.body.text = m.body.text.replace("€48,370", "the price in the PDF")
    assert "V10" in _codes(validate(c))


def test_overlapping_valid_values_are_caught(seed_copy):
    c = Corpus.load(seed_copy)
    old = next(v for v in c.fact_values if v.id == "fv-price-v1")
    old.valid_to = None  # v1 no longer ends when v2 starts
    codes = _codes(validate(c))
    assert {"V08"} <= codes


def test_ambiguous_surface_form_is_caught(seed_copy):
    c = Corpus.load(seed_copy)
    budget = next(v for v in c.fact_values if v.id == "fv-budget")
    budget.surfaces["en"].append("€47,950")  # now names two values in one project
    assert "V09" in _codes(validate(c))


def test_question_asked_before_its_evidence_is_caught(seed_copy):
    c = Corpus.load(seed_copy)
    q = next(q for q in c.questions if q.id == "q-008")
    q.asked_at = q.asked_at - timedelta(days=10)  # before the delivery note was sent
    assert "V12" in _codes(validate(c))


def test_answer_must_be_valid_at_the_question_date(seed_copy):
    c = Corpus.load(seed_copy)
    q = next(q for q in c.questions if q.id == "q-001")
    q.answer.fact_value_ids = ["fv-price-v1"]  # a superseded value given as the current answer
    assert "V12" in _codes(validate(c))
