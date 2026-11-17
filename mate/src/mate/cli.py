"""Command line: ``mate validate <corpus>``, ``mate render <corpus>``, ``mate schema <out dir>``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mate.corpus import Corpus
from mate.render_eml import render_corpus
from mate.schema import TABLES, Manifest, RunRecord
from mate.validate import validate, validate_rendered


def export_schema(out: Path) -> list[Path]:
    """One JSON Schema (draft 2020-12) per table, plus the manifest and the run record."""
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in [*TABLES.items(), ("manifest", Manifest), ("run_record", RunRecord)]:
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"https://mate.example/schema/{name}.schema.json"
        path = out / f"{name}.schema.json"
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for cmd in ("validate", "render"):
        p = sub.add_parser(cmd)
        p.add_argument("corpus", type=Path)
    p = sub.add_parser("schema")
    p.add_argument("out", type=Path)
    args = parser.parse_args(argv)

    if args.cmd == "schema":
        for path in export_schema(args.out):
            print(path)
        return 0
    corpus = Corpus.load(args.corpus)
    if args.cmd == "render":
        render_corpus(corpus)
        corpus.save()
        print(f"rendered {len(corpus.messages)} messages")
        return 0
    report = validate(corpus)
    if report.ok:
        rendered = validate_rendered(corpus)
        report.errors += rendered.errors
        report.warnings += rendered.warnings
    print(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
