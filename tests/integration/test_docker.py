"""The container, against a real daemon and the real image.

Preconditions: a running daemon, the image already built by `scripts/image.sh`, and one
credential route. A missing precondition fails these tests and never skips one. Nothing
here builds: a test that builds its own subject reports a build as a pass, and hides a
long build inside a test run.

Every test but the two marked `live` runs a fixed command and asserts a fixed output. No
model is in the loop, because none of those is a question about a model.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from cowork_evals.config import Config, DockerSection
from cowork_evals.docker import Condition, Docker, probe, remedy
from cowork_evals.docker.parity import EXPECTED_VERSIONS, REQUIREMENTS, compare
from cowork_evals.harness import RunOptions
from cowork_evals.requirements import pins

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "plugins" / "smoke"

# docs/runtime.md, the core runtime table, read through the one place that records it. A
# patch bump in jammy fails here first, and the fixture's grader is a literal that is updated
# in the same commit.
PYTHON_VERSION = f"Python {EXPECTED_VERSIONS['python3']}"

# docs/plugin_eval.md, the enablement self-test. `early access` there means the harness is
# not enabled for this credential, which a passing eval run cannot tell from a broken image.
NO_CASES = "No eval cases found"


@pytest.fixture(scope="session")
def docker() -> Docker:
    """The daemon and the image, asserted once. Nothing here builds either."""
    configured = Docker()
    assert configured.daemon_is_reachable(), (
        f"docker daemon is not reachable: {remedy(Condition.DAEMON)}"
    )
    assert configured.image_is_present(), (
        f"{configured.tag} is absent: {remedy(Condition.IMAGE)}, which no test here runs"
    )
    return configured


@pytest.fixture
def credentialled(docker: Docker) -> Docker:
    """The same, for a test that reads the credential. A missing one fails it."""
    assert docker.has_credential(), (
        f"no credential: {remedy(Condition.CREDENTIAL)}. docs/docker.md."
    )
    return docker


def run_argv(docker: Docker, *command: str, mounts: tuple[str, ...] = ()) -> list[str]:
    """The backend's own run preamble, its own mounts, one fixed command in place of the harness.

    Written this way rather than as a second argument list: a preamble copied here would
    let every sandbox test below pass over options the backend no longer passes.
    """
    return [*docker.run_preamble(), *mounts, docker.tag, *command]


def container(docker: Docker, *command: str, mounts: tuple[str, ...] = ()) -> str:
    """That container's combined output. Nothing is built and nothing is published."""
    completed = subprocess.run(
        run_argv(docker, *command, mounts=mounts),
        capture_output=True,
        text=True,
    )
    return (completed.stdout + completed.stderr).strip()


def test_the_daemon_is_reachable_and_the_image_is_present(docker):
    assert docker.daemon_is_reachable()
    assert docker.image_is_present(), f"{docker.tag} is absent: {remedy(Condition.IMAGE)}"


def test_python3_reports_the_recorded_version(docker):
    assert container(docker, "python3", "-V") == PYTHON_VERSION


def test_the_probe_matches_the_inventory(docker):
    """The delta table in docs/docker.md, applied to a real probe of the built image."""
    document = json.loads(
        container(
            docker,
            "python3",
            "/tmp/probe.py",
            mounts=("-v", f"{probe.__file__}:/tmp/probe.py:ro"),
        )
    )
    assert document["architecture"], "the probe reports the platform it actually ran on"
    failures, _ = compare(document, pins(REQUIREMENTS.read_text()))
    assert failures == [], "\n".join(failures)


def test_bwrap_comes_up_under_the_sandbox_options(docker):
    """The Bash sandbox measurement. It needs no harness and no case."""
    output = container(
        docker, "bwrap", "--ro-bind", "/", "/", "--unshare-user", "--unshare-pid", "true"
    )
    assert output == "", output


def test_bwrap_mounts_a_tmpfs_where_the_harness_mounts_one(docker):
    """The bare invocation above passed while every sandboxed command failed.

    The harness mounts a tmpfs on /run/shm, which the base image does not carry. Nothing
    short of that mount reaches the failure, so it is asserted here rather than left to a
    live run to find.
    """
    output = container(
        docker,
        "bwrap",
        "--ro-bind",
        "/",
        "/",
        "--tmpfs",
        "/run/shm",
        "--unshare-user",
        "--unshare-pid",
        "true",
    )
    assert output == "", output


def test_bwrap_mounts_proc_where_the_harness_mounts_one(docker):
    """`seccomp=unconfined` alone is not enough, and the two tests above do not show it.

    The harness mounts a fresh procfs in the sandbox. Docker's default profile masks
    entries under `/proc`, and the kernel refuses a new procfs mount to a process whose
    own `/proc` is covered that way, so every sandboxed command exits 1 with `bwrap:
    Can't mount proc on /newroot/proc: Operation not permitted`. Measured 2026-09-08.
    `systempaths=unconfined` removes the masks. docs/docker.md.
    """
    output = container(
        docker,
        "bwrap",
        "--ro-bind",
        "/",
        "/",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-ipc",
        "true",
    )
    assert output == "", output


def test_the_cli_runs_under_a_uid_with_no_passwd_entry(docker):
    """The uid mapping measurement. Node's os.userInfo() is what would raise."""
    output = container(docker, "claude", "--version")
    assert docker.claude_code_version in output, output


def test_the_plugin_mount_refuses_a_write_and_the_log_mount_accepts_one(docker, tmp_path):
    plugin = tmp_path / "plugin"
    logs = tmp_path / "logs"
    plugin.mkdir()
    logs.mkdir()
    mounts = ("-v", f"{plugin}:/work/plugin:ro", "-v", f"{logs}:/work/logs:rw")

    refused = container(docker, "touch", "/work/plugin/written", mounts=mounts)
    assert "Read-only file system" in refused, refused
    assert not (plugin / "written").exists()

    accepted = container(docker, "touch", "/work/logs/written", mounts=mounts)
    assert accepted == "", accepted
    written = logs / "written"
    assert written.is_file()

    # Against a file the host makes in the same directory, not against the host uid and
    # gid directly: a new file inherits the directory's gid, so a bare os.getgid()
    # comparison reads a property of the directory as a property of the container.
    reference = logs / "written-by-the-host"
    reference.touch()
    assert written.stat().st_uid == reference.stat().st_uid == os.getuid()
    assert written.stat().st_gid == reference.stat().st_gid


def test_the_environment_route_reports_no_credential_condition(docker, tmp_path):
    """A machine that never logged in is ready on that route. docs/docker.md.

    The daemon and the image are the real ones, and `login_dir` names a directory holding no
    login, so `has_credential` is false and `check` still returns nothing unmet. `auth_env` is
    not a build input, so the tag is the one the session fixture already asserted is present.
    """
    configured = Docker(
        Config(
            docker=DockerSection(
                platform=docker.platform,
                claude_code_version=docker.claude_code_version,
                login_dir=tmp_path / "no-login",
                auth_env=("CLAUDE_CODE_USE_BEDROCK", "AWS_REGION"),
            )
        )
    )
    assert configured.tag == docker.tag
    assert configured.has_credential() is False
    assert [condition for condition, _ in configured.check()] == []


def test_the_harness_is_enabled_for_this_credential(credentialled, tmp_path):
    """It reads the credential and the enablement variable, runs no case and spends nothing."""
    docker = credentialled
    empty = tmp_path / "empty"
    empty.mkdir()
    output = container(
        docker,
        "claude",
        "plugin",
        "eval",
        "/work/empty",
        mounts=("-v", f"{empty}:/work/empty:ro"),
    )
    assert "early access" not in output, output
    assert NO_CASES in output, output


# The two that put a model in the loop, and the only two that spend. Two rather than one,
# because a single failing end-to-end run cannot say whether the credential, the model, the
# mounts or the harness is at fault.


@pytest.mark.live
def test_the_cli_answers_in_the_container(credentialled):
    """The minimal proof that Claude Code runs there and the credential is accepted.

    No plugin, no harness, no mounts. It costs one short reply.
    """
    output = container(
        credentialled, "claude", "-p", "Reply with the single word ORANGE and nothing else."
    )
    assert "ORANGE" in output.upper(), output


@pytest.mark.live
def test_the_smoke_case_passes_through_the_backend(credentialled, tmp_path):
    """Everything the test above does not cover: the harness, the two mounts,
    --output-dir, the Bash grant and the result document.
    """
    logs = tmp_path / "logs"
    logs.mkdir()
    # The plugin directory itself, not evals/ beneath it: the target sets the containment
    # root, and the case's `plugins` entry has to resolve inside it. Naming the plugin is
    # what consents to loading it.
    result = credentialled.run(SMOKE, logs, RunOptions.resolve(runs=1))
    document = json.loads(result.read_text())

    assert document["schemaVersion"] == 1
    assert document["partial"] is False, document.get("partialReason")
    assert document["aggregates"]["casesTotal"] == 1
    cases = document["cases"]
    assert [case["name"] for case in cases] == ["python-version"]
    runs = cases[0]["arms"]["with"]
    assert runs, "the case produced no run"
    assert all(run["passed"] for run in runs), [run.get("error") for run in runs]
