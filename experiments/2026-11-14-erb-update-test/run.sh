#!/usr/bin/env bash
# Repeats the experiment of 14 November 2026: ERB stage 2 step 4 (near-duplicate) and stage 3
# step 6 (conflicting-information question) on the two released Gmail threads in inputs/, with a
# model reached through our Chat Completions adapter (by default a local Ollama server).
#
# Requirements
#   - ERB's Python dependencies:  pip install -r ../../enterprise-rag-bench/requirements.txt
#   - an OpenAI-compatible server; we used Ollama with Gemma 4 E4B and a 16,384-token context,
#     created locally under the name "gemma4-16k" (ERB prompts reach about 8,000 tokens)
#
# The run works on a scratch copy of ERB in ./work, so the repository itself is never modified.
# Every variable below can be overridden from the environment, e.g. LLM_MODEL_NAME=qwen3:8b.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$HERE/work"

rm -rf "$WORK"
cp -r "$HERE/../../enterprise-rag-bench" "$WORK"
# Step 2.4 picks its source document at random. The original run picked the escalation thread, so
# only that thread is offered here; set BOTH_THREADS=1 to offer the ClearWave thread as well.
mkdir -p "$WORK/generated_data/sources/gmail/aditya_rao"
cp "$HERE/inputs/20250603-customer-escalation-private-upgrade-rollback-request.json" "$WORK/generated_data/sources/gmail/"
if [ "${BOTH_THREADS:-0}" = "1" ]; then
  cp "$HERE/inputs/20240624-clearwave-renewal-burst-bridge-request.json" "$WORK/generated_data/sources/gmail/aditya_rao/"
fi
cd "$WORK"

# ERB only places a new document in a folder that exists on disk. Git does not store empty
# folders, so recreate the company's folder tree from generated_data/source_tree.txt.
python - <<'PY'
import os
# Each level of the tree is indented by four characters, then "├── " or "└── " (the file
# uses non-breaking spaces in the indentation, so the depth is read from the marker's position).
stack = []
with open("generated_data/source_tree.txt", encoding="utf-8") as fh:
    for line in fh:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        i = max(line.find("├── "), line.find("└── "))
        if i < 0:  # the root line, "sources"
            stack = [line.strip().rstrip("/")]
            continue
        depth = i // 4 + 1
        stack = stack[:depth] + [line[i + 4:].strip().rstrip("/")]
        os.makedirs(os.path.join("generated_data", *stack), exist_ok=True)
PY

# ERB finds documents through generated_data/uuid_index.json; build it for the two local threads.
python -c "from src.utils.document_index import rebuild_uuid_index; rebuild_uuid_index()"

export LLM_PROVIDER=chat
export CHAT_BASE_URL="${CHAT_BASE_URL:-http://localhost:11434/v1}"
export LLM_API_KEY="${LLM_API_KEY:-ollama}"
export LLM_MODEL_NAME="${LLM_MODEL_NAME:-gemma4-16k}"
export CHEAP_LLM_MODEL_NAME="${CHEAP_LLM_MODEL_NAME:-$LLM_MODEL_NAME}"
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8

t0=$(date +%s)
python -m src.scripts.data_gen_stage_2_add_noise.step_4_generate_near_duplicates --count 1 > step4.log 2>&1
echo "step 2.4 finished in $(( $(date +%s) - t0 )) s: $(grep -E '^(Successfully created|Failed):' step4.log | tr '\n' ' ')"
t1=$(date +%s)
python -m src.scripts.data_gen_stage_3_generate_questions.step_6_generate_conflicting_questions --count 1 --quiet > step6.log 2>&1
echo "step 3.6 finished in $(( $(date +%s) - t1 )) s: $(grep -E '^(Successfully generated|Failed):' step6.log | tr '\n' ' ')"

echo "Outputs in $WORK: generation_cache/duplications.json, the new file under generated_data/sources/,"
echo "and the new question at the end of questions.jsonl. Logs: step4.log, step6.log."
