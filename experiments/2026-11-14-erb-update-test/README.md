# Experiment: can EnterpriseRAG-Bench produce a controlled update and a correct answer for it?

**Date.** 14 November 2026; repeated on 17 November 2026 with `run.sh`.
**Question.** Our first research question concerns outdated versions: when a value is replaced
(an offer at €48,370 becomes €47,950), does the system answer with the current value? A test corpus
for this needs, for every update, the old value, the new value, the date of the change, and a
question whose correct answer is the new value. In ERB, exactly two steps produce such material:

- **stage 2, step 4 (near-duplicates)** writes a newer version of an existing document, in which
  "some facts are updated";
- **stage 3, step 6 (conflicting information)** writes a question and its gold answer from such a
  pair.

The experiment checks whether these two steps can be relied on to build the test material of the
first research question.

## Set-up

| Item | Value |
|---|---|
| ERB | commit `d36685e`, unchanged except for our Chat Completions back-end (`../../enterprise-rag-bench/CHANGES.md`) |
| Model | Gemma 4 E4B served by Ollama on a laptop GPU (NVIDIA RTX 3060 Laptop, 6 GB), context 16,384 tokens, about 51 generated tokens per second |
| Input | two Gmail threads of ERB's released company, in `inputs/` |
| Commands | `--count 1` for each step, i.e. one near-duplicate and one question |

## Files

| Path | Content |
|---|---|
| `inputs/` | the two released Gmail threads given to ERB |
| `logs/` | the console output of both steps on 14 November, and `timing.txt` |
| `outputs/near_duplicate.json` | the "newer version" written by step 2.4 |
| `outputs/duplications.json` | everything ERB recorded about the pair |
| `outputs/qst_0501.json` | the question written by step 3.6 |
| `rerun-2026-11-17/` | the same files from the repetition with `run.sh` |
| `compare.py` | counts the key commitments of the thread in the original and in the near-duplicate |
| `run.sh` | repeats the experiment on a scratch copy of ERB |
| [`../../docs/figures/fig-run-erb.png`](../../docs/figures/fig-run-erb.png) | the figure of the 14 November run |

## Procedure and observations (14 November)

1. **Step 2.4** chose the thread *"Escalation: rollback guarantees + upgrade support coverage"*,
   asked the model for a new location (it chose a Confluence folder, which ERB allows), a file name,
   and the new content. The first content was rejected by ERB's own check
   `validate_no_nested_dicts` (nested objects in three keys); the second was accepted. The pair was
   stored in `duplications.json`. Duration: 120 s.
2. **Step 3.6** first stopped after 2 s, before any model call, because the document index of our
   download was truncated; after rebuilding it with ERB's `rebuild_uuid_index()`, it wrote question
   `qst_0501` of type `conflicting_info` in 23 s.
3. **Comparison** (`python compare.py`):

   | Commitment in the thread | Original | Near-duplicate |
   |---|---:|---:|
   | 48 hours of advance notice | 2 | 1 |
   | live bridge during the window | 2 | 1 |
   | SRE escalation | 2 | 1 |
   | restore in tens of minutes | 2 | 1 |
   | N-1 upgrade path | 4 | 1 |
   | length in characters | 12,696 | 2,709 |

   The near-duplicate is a shorter guidance page ("version 1.1", a newer date) that states the same
   commitments. No fact was changed. ERB recorded only
   `{"document_old": "dsid_c6a6…", "document_new": "dsid_660b…"}`. The question asks *"What support
   coverage is committed for Redwood Private upgrades?"* and its gold answer restates the values
   common to both documents, although the question is labelled as a conflict.

## Repetition (17 November)

`run.sh` repeated the procedure from this repository. Step 2.4 took 152 s; the first content was
again rejected for nested objects. Step 3.6 took 38 s and again produced a `conflicting_info`
question. This time the model did change one detail: the original thread *offers* a rollback drill
("If you'd like, we can also run a rollback drill in a non-production environment"), while the new
version makes it "a mandatory prerequisite for support commitment". ERB again recorded only the two
document identifiers, so this change can only be found by reading both documents, and nothing says
whether it was the intended update.

A first attempt of the repetition, with both threads offered, picked the ClearWave thread and failed
after five attempts because the model proposed folders that do not exist in the company
(`finance-and-legal/...`); `run.sh` therefore offers only the escalation thread by default.

## Interpretation

- The Chat Completions back-end works with ERB's real steps, including tool calls, JSON validation
  and retries.
- The small local model broke ERB's format rule at the first attempt of both runs and, in one
  attempt, invented folders; the corpus needs a stronger model.
- Independently of the model, step 2.4 leaves the change to the model and records only the pair of
  identifiers, and step 3.6 lets a model write the gold answer. Neither the old value, the new value
  nor the date of a change is recorded, so a question about the current value cannot be checked
  automatically. This is why our pipeline plans each change in tables before any text is written and
  reads the gold answers from those tables.

## Limits

Two runs on one document with one small model. The experiment shows how the two steps work and
where they can fail; it does not estimate how often they fail.
