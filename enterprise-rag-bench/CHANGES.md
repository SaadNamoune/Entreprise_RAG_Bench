# Changes to EnterpriseRAG-Bench in this repository

This folder is a copy of [onyx-dot-app/EnterpriseRAG-Bench](https://github.com/onyx-dot-app/EnterpriseRAG-Bench)
at commit `d36685e` (7 May 2026), distributed under its original MIT licence (see `LICENSE`,
copyright DanswerAI, Inc.). The upstream `README.md`, `quickstart.md` and `methodology.md` are kept
unchanged and remain the reference for how ERB works.

## What we added

| File | Change | Why |
|---|---|---|
| `src/llm/chat_completions_llm.py` | New file (102 lines): a model back-end for the OpenAI-compatible Chat Completions API | ERB only supports OpenAI's Responses API and the Anthropic API. This back-end lets the unchanged pipeline run on a local Ollama server or any other OpenAI-compatible server |
| `src/llm/factory.py` | Four lines in `get_llm` and four in `get_cheap_llm` register the new back-end as `LLM_PROVIDER=chat` | Selecting the back-end by environment variable, like the two upstream back-ends |

No prompt, step script, validation function or data file was changed. A comparison of every file
with the upstream commit confirms this.

Usage:

```bash
export LLM_PROVIDER=chat
export CHAT_BASE_URL=http://localhost:11434/v1   # Ollama; any OpenAI-compatible server works
export LLM_API_KEY=ollama                        # any non-empty value for Ollama
export LLM_MODEL_NAME=gemma4-16k                 # model name on that server
export CHEAP_LLM_MODEL_NAME=gemma4-16k           # optional; defaults to LLM_MODEL_NAME
export CHAT_TIMEOUT=900                          # optional; seconds per request
```

## What we left out

| Upstream content | Size | How to get it |
|---|---|---|
| `generated_data/sources/**` (the released corpus: about 500,000 documents of the company Redwood Inference) | Too large for this repository | `all_documents.zip` from the upstream releases or from Hugging Face (`onyx-dot-app/EnterpriseRAG-Bench`) |
| `generated_data/uuid_index.json` (map from document id to file) | 51 MB | Rebuilt for whatever documents are present: `python -c "from src.utils.document_index import rebuild_uuid_index; rebuild_uuid_index()"` |

The writing rules of every tool (`generated_data/sources/<tool>/agents.md`) and the company scaffold
(`company_overview.md`, `initiatives.md`, `employee_directory.yaml`, `source_tree.txt`,
`project_list.txt`) are included, so the pipeline can be run on new documents.

Git does not store empty folders. ERB only writes a new document into a folder that exists, so before
running stage 2 or later on an empty checkout, recreate the folder tree from
`generated_data/source_tree.txt`; `experiments/2026-11-14-erb-update-test/run.sh` shows how.
