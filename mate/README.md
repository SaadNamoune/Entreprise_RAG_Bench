# MATE: Messages, Attachments, Threads and Evidence (working name)

The corpus format, renderer, checks and scoring of the PFE "Multimodal RAG for Enterprise Email and
Attachments" (ESI Algiers × TH Deggendorf). Its role in the generation pipeline, and the reason for
every choice, are explained in the [repository README](../README.md).

## What is here

| Path | Content |
|---|---|
| `src/mate/schema.py` | the data model: world, facts over time, artifacts/versions/occurrences, messages, evidence spans, questions, run records |
| `src/mate/corpus.py` | JSON Lines tables in and out, lookups, derived data |
| `src/mate/validate.py` | invariants V01–V21 |
| `src/mate/render_eml.py` | deterministic RFC 5322 / MIME rendering, journal mbox, copy spans |
| `src/mate/filebuilders.py` | reproducible PDF, DOCX, XLSX, charts, logos, scanned PDFs |
| `src/mate/normalize.py`, `src/mate/metrics.py` | grading and retrieval metrics, statistics |
| `schema/` | JSON Schemas (draft 2020-12) exported from the models |
| `examples/seed/` | a hand-written scenario that exercises every part of the schema (11 messages, 15 questions) |
| `tests/` | pytest suite |

## Use

```
pip install -e ".[files,dev]"        # or: pip install pydantic jsonschema reportlab python-docx openpyxl matplotlib pillow pytest
python examples/seed/build_seed.py   # build, render and validate the seed corpus
python -m pytest -q                  # run the tests
mate validate examples/seed/corpus   # validate a corpus
mate schema schema                   # re-export the JSON Schemas
```

All generated people, companies and addresses are fictional; every address uses the reserved
`.example` domain (RFC 2606). Proposed licences: code MIT, data CC BY 4.0 (to confirm).
