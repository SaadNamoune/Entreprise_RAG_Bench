"""Compare the original Gmail thread with the "near-duplicate" that ERB step 2.4 wrote from it.

The near-duplicate is meant to be a newer version in which "some facts are updated". This script
counts the key commitments of the thread in both documents and prints what ERB recorded about the
pair and the question that step 3.6 wrote for it.

Usage (inside this folder):  python compare.py
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
ORIGINAL = HERE / "inputs" / "20250603-customer-escalation-private-upgrade-rollback-request.json"
NEAR_DUPLICATE = HERE / "outputs" / "near_duplicate.json"

# The commitments made in the original thread, and a pattern that finds each of them.
FACTS = {
    "48 hours of advance notice": r"48[ -]hours?",
    "live bridge during the window": r"live bridge",
    "SRE escalation": r"SRE escalation",
    "restore in tens of minutes": r"tens of minutes",
    "N-1 upgrade path": r"N-1",
}


def main() -> None:
    original = ORIGINAL.read_text(encoding="utf-8")
    near_duplicate = NEAR_DUPLICATE.read_text(encoding="utf-8")

    print(f"{'commitment':<32}{'original':>10}{'near-duplicate':>16}")
    for name, pattern in FACTS.items():
        a = len(re.findall(pattern, original, re.IGNORECASE))
        b = len(re.findall(pattern, near_duplicate, re.IGNORECASE))
        print(f"{name:<32}{a:>10}{b:>16}")
    print(f"{'length in characters':<32}{len(original):>10}{len(near_duplicate):>16}")

    pair = json.loads((HERE / "outputs" / "duplications.json").read_text(encoding="utf-8"))
    print("\nWhat ERB recorded about the pair:", json.dumps(pair["duplications"][0]))

    question = json.loads((HERE / "outputs" / "qst_0501.json").read_text(encoding="utf-8"))
    print("Question written by step 3.6:", question["question_type"], "-", question["question"])
    print("Its gold answer:", question["gold_answer"])


if __name__ == "__main__":
    main()
