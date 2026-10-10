"""The two environments are what docs/environments.md says they are.

`.venv` is read from disk and an unbuilt one fails these. `scripts/init.sh` builds it.

Nothing here requires `.venv_cowork`. The mirror is 604 MB, no module reads it, and only
`scripts/cowork_run.sh` uses it, so it is built on demand by `scripts/cowork_venv.sh` and
that script is what verifies it. A test asserting it exists would make a developer who never
runs `cowork_run.sh` carry it. docs/environments.md.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from cowork_evals.docker.parity import EXPECTED_VERSIONS
from cowork_evals.requirements import pins as read_pins

ROOT = Path(__file__).resolve().parent.parent.parent
VENV = ROOT / ".venv"
DATA = ROOT / "src" / "cowork_evals" / "data"
REQUIREMENTS = DATA / "requirements.txt"
INSTALLABLE = DATA / "requirements_installable.txt"
TEST_ONLY = DATA / "requirements_test.txt"

# The exact interpreter a CoWork session runs, and what both environments are built on.
PINNED = (ROOT / ".python-version").read_text().strip()

# The nine pins that cannot install off the CoWork VM. docs/environments.md.
NOT_INSTALLABLE = {
    "command-not-found",
    "dbus-python",
    "distro-info",
    "pipx",
    "pygobject",
    "pyinotify",
    "python-apt",
    "ufw",
    "unattended-upgrades",
}


def pins(path: Path) -> dict[str, str]:
    """The package's own reader, over a path. scripts/cowork_venv.sh calls the same one."""
    return read_pins(path.read_text())


def test_installable_is_the_freeze_minus_the_nine():
    full = pins(REQUIREMENTS)
    installable = pins(INSTALLABLE)
    assert set(full) - set(installable) == NOT_INSTALLABLE
    # Every shared pin is at the same version. A drift here silently changes the mirror.
    assert {k: full[k] for k in installable} == installable


def test_the_test_layer_adds_packages_and_moves_none():
    """No pin of `requirements_test.txt` is already in the image.

    The test image installs it with `--no-deps`, so a name on both lists would either be
    reinstalled at the wrong version or silently do nothing. docs/environments.md owns
    which of the three files a pin goes in.
    """
    assert set(pins(TEST_ONLY)) & set(pins(REQUIREMENTS)) == set()


def test_the_development_interpreter_is_the_session_interpreter():
    """`.python-version` and `parity.py` are the two homes of one fact, and they agree.

    `.python-version` is what `uv` reads to build either environment, and it is not shipped.
    `EXPECTED_VERSIONS` is the record of the container, and it is. Neither can read the
    other, so this is what keeps them from drifting. docs/environments.md.
    """
    assert EXPECTED_VERSIONS["python3"] == PINNED


def test_tests_run_under_the_repo_venv_on_the_pinned_interpreter():
    """The two environments are the same interpreter, so the prefix is what tells them apart.

    A run under the mirror would carry the CoWork wheel set and not the dev group, so the
    suite would collect against the wrong dependencies. The patch is the point of the
    version: it is what a session runs. docs/environments.md.
    """
    assert Path(sys.prefix).resolve() == VENV.resolve(), f"suite ran under {sys.prefix}"
    assert ".".join(map(str, sys.version_info[:3])) == PINNED


def test_scripts_readme_carries_a_row_for_every_script():
    """The index owns the task list, so a new script cannot be reachable and unlisted."""
    index = (ROOT / "scripts" / "README.md").read_text()
    for script in sorted((ROOT / "scripts").glob("*.sh")):
        assert f"`{script.name}`" in index, f"{script.name} has no row in scripts/README.md"


# Every `*.sh` in the repository, outside a dot directory. `scripts/lint.sh` selects by the
# same rule, so no shell file is checked here and unlinted there. The rule excludes every dot
# directory, `.venv_cowork/` among them when it is built, because that one carries a vendored
# shell file.
SCRIPTS = sorted(
    path
    for path in ROOT.rglob("*.sh")
    if not any(part.startswith(".") for part in path.relative_to(ROOT).parts)
)


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: str(path.relative_to(ROOT)))
def test_every_script_parses(script: Path):
    subprocess.run(["bash", "-n", str(script)], check=True)


# `lib.sh` is sourced, never executed, so it needs no executable bit.
@pytest.mark.parametrize(
    "script",
    [path for path in SCRIPTS if path.name != "lib.sh"],
    ids=lambda path: str(path.relative_to(ROOT)),
)
def test_every_script_is_executable(script: Path):
    assert script.stat().st_mode & 0o111
