import json

from jsonschema import Draft202012Validator

from mate.cli import export_schema
from mate.schema import TABLES


def test_exported_schemas_are_valid_and_accept_the_seed(seed_dir, tmp_path):
    paths = {p.stem.removesuffix(".schema"): p for p in export_schema(tmp_path)}
    assert set(TABLES) | {"manifest", "run_record"} == set(paths)
    for name, path in paths.items():
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        if name not in TABLES:
            continue
        validator = Draft202012Validator(schema)
        table = seed_dir / f"{name}.jsonl"
        for line in table.read_text(encoding="utf-8").splitlines():
            errors = list(validator.iter_errors(json.loads(line)))
            assert not errors, f"{name}: {errors[0].message}"
