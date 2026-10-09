"""What each backend needs before it runs, and what is missing.

One function per backend, each returning the unmet conditions in order, each line naming the
command that fixes it. It writes nothing, builds nothing and submits nothing, so a failed
preflight leaves the machine exactly as it was. The conditions are the preflight table in
docs/cli.md.

`check` prints what this returns. `run` prints it and exits 3. The one condition `run` adds and
`check` does not is the CoWork rate ceiling, which needs a target and is `cowork_ceiling` below.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import cowork_backend
from .config import Config, CoWorkError
from .docker import Docker
from .docker.pytest_image import PytestImage

# The two backends, and the `test` verb's own preflight. `test` is not a backend: it runs
# no eval and produces no result document. It has a preflight of its own because it starts
# a container, and it is selected here the way a backend is. docs/cowork_test.md.
DOCKER = "docker"
COWORK = "cowork"
TEST = "test"
BACKENDS = (DOCKER, COWORK)

# The one platform the CoWork desktop application runs on. docs/cowork_desktop.md.
DARWIN = "darwin"

# The CLI the judge and `claudeVersion` both need on the CoWork backend. docs/cli.md.
CLAUDE = "claude"

# The Accessibility probe. It reads the process list, submits nothing and starts no
# session. Without the grant `osascript` refuses with error 1002. docs/cowork_desktop.md.
ACCESSIBILITY_ARGV = [
    "osascript",
    "-e",
    'tell application "System Events" to get the name of the first process',
]
ACCESSIBILITY_ERROR = "1002"


def checks(backend: str, config: Config) -> list[str]:
    """The unmet conditions of one backend, in order. An empty list means ready.

    `config` is the one `Config` the invocation loaded, so every verb and every backend
    reads the same `cowork_evals.yaml`.
    """
    if backend == DOCKER:
        return [line.message for line in Docker(config).check()]
    if backend == TEST:
        return [line.message for line in PytestImage(config).check()]
    if backend == COWORK:
        return _cowork(config)
    raise ValueError(f"no preflight for {backend}")


def checks_all(config: Config) -> list[str]:
    """Every backend's unmet conditions, in the order the backends are listed."""
    return [line for backend in BACKENDS for line in checks(backend, config)]


def report_all(config: Config) -> list[tuple[str, list[str]]]:
    """One entry per backend, in order, each with its unmet conditions.

    `checks_all` flattens the same probe and loses which backend a line came from, and loses
    a ready backend entirely: it contributes no line, so its output cannot be told from a
    backend that was never reached. `check --all` prints this instead. The exit code still
    comes from `checks_all`, so the two never disagree about pass and fail.
    """
    return [(backend, checks(backend, config)) for backend in BACKENDS]


def _cowork(config: Config) -> list[str]:
    """macOS, `claude`, a configured profile, a readable sessions root, and the grant.

    The desktop application itself is not probed. What the backend reads is the profile
    directory the application writes sessions into, and an unreadable one is the condition
    that matters. docs/cowork_desktop.md.
    """
    unmet: list[str] = []
    if sys.platform != DARWIN:
        unmet.append(
            f"the platform is {sys.platform}: the CoWork backend drives a macOS application"
        )
    if shutil.which(CLAUDE) is None:
        unmet.append(f"{CLAUDE} is not on PATH: install the Claude Code CLI")
    unmet += _profile(config)
    if not _accessibility_granted():
        unmet.append(
            "no macOS Accessibility grant: grant it to the terminal application in "
            "System Settings, Privacy and Security, Accessibility"
        )
    return unmet


def _profile(config: Config) -> list[str]:
    """The configured profile, and the sessions root under it.

    Constructing a `Config` validates the file alone. A missing `profile` is refused by the
    first property that needs one, which is `profile_dir` under `sessions_root`, so the
    property is read here rather than trusted and its `CoWorkError` becomes one line.
    """
    try:
        sessions = config.cowork.sessions_root
    except CoWorkError as error:
        return [str(error)]
    if not sessions.is_dir() or not os.access(sessions, os.R_OK):
        return [
            f"{sessions}: no readable sessions root: check cowork.profile in the "
            "configuration file, and open CoWork once on this profile"
        ]
    return []


def _accessibility_granted() -> bool:
    """Whether `osascript` may drive System Events on this machine."""
    try:
        completed = subprocess.run(ACCESSIBILITY_ARGV, capture_output=True, text=True, check=False)
    except OSError:
        return False
    return completed.returncode == 0 and ACCESSIBILITY_ERROR not in completed.stderr


def cowork_ceiling(target: Path | str, **overrides) -> list[str]:
    """The rate ceiling, over the suite a target selects. It submits nothing.

    `run` calls it and `check` does not: it needs a target, and `check` takes none. The
    arithmetic is `cowork_backend.plan`'s, and this compares the three numbers it reports.
    `cowork_backend.run` raises on the same condition, which is that backend's own guard
    and is unreachable behind this check.
    """
    prepared = cowork_backend.plan(target, **overrides)
    return [prepared.refusal] if prepared.over_ceiling else []
