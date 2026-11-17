"""A corpus in memory: its tables, lookups by id, and what can be derived from them."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from mate.schema import TABLES, Manifest, Model


@dataclass
class Corpus:
    """All tables of one corpus. ``root`` is where its files and rendered mail live."""

    root: Path
    manifest: Manifest | None = None
    tables: dict[str, list[Any]] = field(default_factory=lambda: {name: [] for name in TABLES})

    # ------------------------------------------------------------------ io

    @classmethod
    def load(cls, root: Path | str) -> Corpus:
        root = Path(root)
        corpus = cls(root=root)
        manifest = root / "manifest.json"
        if manifest.exists():
            corpus.manifest = Manifest.model_validate_json(manifest.read_text(encoding="utf-8"))
        for name, model in TABLES.items():
            path = root / f"{name}.jsonl"
            if not path.exists():
                continue
            with path.open(encoding="utf-8") as fh:
                corpus.tables[name] = [model.model_validate_json(line) for line in fh if line.strip()]
        return corpus

    def save(self) -> None:
        """Write every table as JSON Lines (one record per line, stable key order) and the manifest."""
        self.root.mkdir(parents=True, exist_ok=True)
        for name in TABLES:
            path = self.root / f"{name}.jsonl"
            with path.open("w", encoding="utf-8", newline="\n") as fh:
                for record in self.tables[name]:
                    fh.write(record.model_dump_json(exclude_none=True) + "\n")
        if self.manifest is not None:
            (self.root / "manifest.json").write_text(
                self.manifest.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8"
            )

    def add(self, table: str, record: Model) -> Model:
        self.tables[table].append(record)
        return record

    # ------------------------------------------------------------- lookups

    def by_id(self, table: str) -> dict[str, Any]:
        return {r.id: r for r in self.tables[table]}

    def __getattr__(self, name: str) -> list[Any]:
        # corpus.messages, corpus.spans, ...: the table as a list
        tables = self.__dict__.get("tables", {})
        if name in tables:
            return tables[name]
        raise AttributeError(name)

    # ------------------------------------------------------------- derived

    def thread_chain(self, message_id: str) -> list[str]:
        """The messages a message answers or forwards, oldest first: what References lists."""
        msgs = self.by_id("messages")
        chain: list[str] = []
        current = msgs[message_id]
        seen = {message_id}
        while True:
            parent = current.in_reply_to or current.forward_of
            if parent is None or parent in seen:
                break
            chain.append(parent)
            seen.add(parent)
            current = msgs[parent]
        return list(reversed(chain))

    def occurrences_of_message(self, message_id: str) -> list[Any]:
        return sorted((o for o in self.occurrences if o.message_id == message_id), key=lambda o: o.order)

    def first_occurrence(self) -> dict[str, str]:
        """For each version, the occurrence that carried it first; later ones are re-sent copies."""
        msgs = self.by_id("messages")
        first: dict[str, tuple[datetime, str]] = {}
        for occ in self.occurrences:
            when = msgs[occ.message_id].sent_at
            if occ.version_id not in first or when < first[occ.version_id][0]:
                first[occ.version_id] = (when, occ.id)
        return {version: occ for version, (_, occ) in first.items()}

    def spans_by_value(self) -> dict[str, list[Any]]:
        out: dict[str, list[Any]] = defaultdict(list)
        for span in self.spans:
            if span.fact_value_id:
                out[span.fact_value_id].append(span)
        return out

    def value_at(self, fact_id: str, when: datetime) -> list[Any]:
        """The values of a fact that are valid (or contested) at a moment in time."""
        out = []
        for fv in self.fact_values:
            if fv.fact_id != fact_id or fv.standing == "erroneous":
                continue
            if fv.valid_from <= when and (fv.valid_to is None or when < fv.valid_to):
                out.append(fv)
        return out


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
