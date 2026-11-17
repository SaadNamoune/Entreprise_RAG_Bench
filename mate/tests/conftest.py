import importlib.util
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _seed_module():
    spec = importlib.util.spec_from_file_location("build_seed", ROOT / "examples" / "seed" / "build_seed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def seed_dir(tmp_path_factory) -> Path:
    """The seed corpus, built, rendered and validated once per test session."""
    out = tmp_path_factory.mktemp("seed") / "corpus"
    assert _seed_module().main(out) == 0
    return out


@pytest.fixture
def seed_copy(seed_dir, tmp_path) -> Path:
    """A private copy of the seed for tests that break it on purpose."""
    dst = tmp_path / "corpus"
    shutil.copytree(seed_dir, dst)
    return dst


@pytest.fixture(scope="session")
def build_seed():
    return _seed_module()
