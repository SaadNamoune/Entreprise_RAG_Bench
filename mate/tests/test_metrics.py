import pytest

from mate.corpus import Corpus
from mate.metrics import (SpanIndex, citation_scores, grade_answer, holm, mcnemar_exact, paired_bootstrap,
                          retrieval_scores)
from mate.normalize import contains_value, extract_values, parse_number
from mate.schema import Retrieved, RunRecord


@pytest.fixture(scope="module")
def ctx(seed_dir):
    c = Corpus.load(seed_dir)
    return c, SpanIndex.build(c), {q.id: q for q in c.questions}, {m.id: m.rfc_message_id for m in c.messages}


def item(rank, rfc, text, order=None):
    return Retrieved(rank=rank, rfc_message_id=rfc, text=text, attachment_order=order)


def test_current_value_found_in_body(ctx):
    c, idx, qs, rfc = ctx
    items = [item(1, rfc["msg-03"], "delivery is now 9 weeks after order, and we reduced the unit price to €47,950.")]
    s = retrieval_scores(qs["q-001"], items, idx, k=5)
    assert s["tca@5"] == 1.0 and s["stale_only@5"] == 0.0 and s["hit@5"] == 1.0


def test_only_the_superseded_value_is_stale(ctx):
    c, idx, qs, rfc = ctx
    items = [item(1, rfc["msg-01"], "The unit price is €48,370 and the delivery time is 14 weeks after order."),
             item(2, rfc["msg-11"], "Kreiselpumpen kosten derzeit zwischen 41.000 € und 52.000 €.")]
    s = retrieval_scores(qs["q-001"], items, idx, k=5)
    assert s["any_version@5"] == 1.0 and s["tca@5"] == 0.0 and s["stale_only@5"] == 1.0
    assert s["hit@5"] == 0.0


def test_attachment_passage_maps_through_the_platform_index(ctx):
    c, idx, qs, rfc = ctx
    items = [item(1, rfc["msg-03"], "P-200 centrifugal pump 2 €47,950", order=0)]
    assert retrieval_scores(qs["q-001"], items, idx, k=1)["hit@1"] == 1.0
    # The same chunk text from the wrong message's file does not count.
    items = [item(1, rfc["msg-01"], "P-200 centrifugal pump 2 €47,950", order=0)]
    assert retrieval_scores(qs["q-001"], items, idx, k=1)["hit@1"] == 0.0


def test_coverage_and_perfrecall_need_every_group(ctx):
    c, idx, qs, rfc = ctx
    q = qs["q-003"]  # needs both delivery times
    one = [item(1, rfc["msg-03"], "delivery is now 9 weeks after order")]
    both = one + [item(2, rfc["msg-01"], "the delivery time is 14 weeks after order")]
    s1, s2 = retrieval_scores(q, one, idx, 5), retrieval_scores(q, both, idx, 5)
    assert (s1["coverage@5"], s1["perfrecall@5"]) == (0.5, 0.0)
    assert (s2["coverage@5"], s2["perfrecall@5"]) == (1.0, 1.0)


def test_copies_waste_slots(ctx):
    c, idx, qs, rfc = ctx
    q = qs["q-013"]  # 30 April 2027: one original and two quoted copies
    items = [item(1, rfc["msg-02"], "on site by 30 April 2027"), item(2, rfc["msg-03"], "> on site by 30 April 2027"),
             item(3, rfc["msg-04"], "> on site by 30 April 2027")]
    s = retrieval_scores(q, items, idx, 3)
    assert s["perfrecall@3"] == 1.0
    assert s["wasted_slots@3"] == pytest.approx(2 / 3)
    assert s["original_recall@3"] == 1.0
    assert s["span_recall@3"] == 1.0


def test_image_page_without_text_matches_by_location(ctx):
    c, idx, qs, rfc = ctx
    page = [Retrieved(rank=1, rfc_message_id=rfc["msg-10"], attachment_order=0, page=1, text="")]
    assert retrieval_scores(qs["q-008"], page, idx, 1)["hit@1"] == 1.0
    wrong_text = [Retrieved(rank=1, rfc_message_id=rfc["msg-10"], attachment_order=0, text="Hydrova Pumps Ltd")]
    assert retrieval_scores(qs["q-008"], wrong_text, idx, 1)["hit@1"] == 0.0


def test_grading_against_the_closed_pool(ctx):
    c, idx, qs, rfc = ctx
    q1 = qs["q-001"]
    assert grade_answer(q1, "The current unit price is 47.950 € per pump.") == "correct"
    assert grade_answer(q1, "It costs EUR 48,370.00 per pump.") == "superseded"
    assert grade_answer(q1, "First €48,370, then €47,950.") == "partial"
    assert grade_answer(q1, "I cannot find this in the documents.") == "abstain"
    assert grade_answer(qs["q-012"], "There is no information about a version 3.") == "correct"
    assert grade_answer(qs["q-012"], "Version 3 had a 5 % discount.") == "wrong"
    q9 = qs["q-009"]
    assert grade_answer(q9, "The offer says 36 months, but Tom's email says 24 months.") == "correct"
    assert grade_answer(q9, "36 months.") == "partial"
    assert grade_answer(qs["q-010"], "Hydrova sent 2 versions (January 2027).") == "correct"
    assert grade_answer(qs["q-010"], "Three versions arrived in 2027.") == "wrong"
    assert grade_answer(qs["q-015"], "anything") == "judge"


def test_citation_policies(ctx):
    c, idx, qs, rfc = ctx
    q = qs["q-001"]
    forwarded = item(1, rfc["msg-04"], "we reduced the unit price to €47,950.")
    resent_file = item(2, rfc["msg-04"], "P-200 centrifugal pump 2 €47,950", order=0)
    original = item(3, rfc["msg-03"], "we reduced the unit price to €47,950.")
    rec = RunRecord(question_id="q-001", system="t", arm="t", retrieved=[forwarded, resent_file, original],
                    cited_ranks=[1, 2])
    s = citation_scores(q, rec, idx)
    assert s["citation_recall"] == 1.0 and s["citation_recall_original"] == 0.0
    rec.cited_ranks = [3]
    assert citation_scores(q, rec, idx)["citation_recall_original"] == 1.0


def test_number_and_date_normalisation():
    assert parse_number("47.950,00") == 47950.0
    assert parse_number("47,950.00") == 47950.0
    assert parse_number("1,5") == 1.5
    assert parse_number("1.234.567") == 1234567.0
    assert extract_values("Lieferung am 1. März 2027") == {"date:2027-03-01"}
    assert "date:2027-03-01" in extract_values("delivered on March 1, 2027")
    assert "date:2027-03-01" in extract_values("Datum: 01.03.2027")
    assert "qty:9 week" in extract_values("jetzt 9 Wochen")
    assert contains_value("Es sind 47.950 € pro Pumpe.", "€47,950")
    assert not contains_value("im Jahr 2027", "2")


def test_statistics():
    a = [0, 0, 1, 0, 1, 0, 0, 1, 0, 0] * 10
    b = [1, 0, 1, 1, 1, 0, 1, 1, 0, 1] * 10
    mean, lo, hi = paired_bootstrap(a, b, n=2000, seed=1)
    assert mean == pytest.approx(0.4) and lo > 0
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(2, 20) < 0.001
    adj = holm({"A1": 0.01, "A2": 0.04, "A3": 0.03})
    assert adj["A1"] == pytest.approx(0.03) and adj["A2"] == pytest.approx(0.06)
