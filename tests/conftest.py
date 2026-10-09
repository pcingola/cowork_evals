"""The fixtures both tiers use: the repository root, the working directory, and a plugin root."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repository() -> Path:
    """The root of this repository."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def working_directory() -> Callable[[Path], contextlib.AbstractContextManager[None]]:
    """Run a block in another working directory, and return to this one after.

    `cowork_evals.yaml` and `logs/` resolve from the working directory, so a test of that
    rule moves there. `contextlib.chdir` is Python 3.11.
    """

    @contextlib.contextmanager
    def _chdir(path: Path) -> Iterator[None]:
        previous = os.getcwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(previous)

    return _chdir


@pytest.fixture
def plugin(tmp_path: Path) -> Path:
    """A plugin root with a `tests/` directory, outside this repository, so a test may write
    into its tree."""
    root = tmp_path / "consumer"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text('{"name": "consumer"}')
    (root / "tests").mkdir()
    return root
