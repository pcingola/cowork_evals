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
import re
import subprocess
from pathlib import Path

import pytest

from cowork_evals import logs, traces, verdict
from cowork_evals.cli import main
from cowork_evals.docker import CONTAINER_KEEP_FILE, KEEP_FILE, Condition, Docker, probe, remedy
from cowork_evals.docker.parity import EXPECTED_VERSIONS, REQUIREMENTS, ProbeDocument, compare
from cowork_evals.harness import RunOptions
from cowork_evals.requirements import pins
from cowork_evals.results import ResultDocument

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "plugins" / "smoke"

# The harness's own fixture, which `cowork_evals run` refuses because it deliberately does not
# follow this repository's case format. It is the one tree here that carries a skill, a
# `tool_used: Skill` grader and an over-trigger case, so it exercises every shape the baseline
# arm changes. docs/claude_code/eval_smoke/README.md.
EVAL_SMOKE = ROOT / "docs" / "claude_code" / "eval_smoke"

# docs/runtime.md, the core runtime table, read through the one place that records it. A
# patch bump in jammy fails here first, and the fixture's grader is a literal that is updated
# in the same commit.
PYTHON_VERSION = f"Python {EXPECTED_VERSIONS['python3']}"

# docs/docker.md, the enablement self-test. `early access` there means the harness is
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
    document = ProbeDocument.model_validate_json(
        container(
            docker,
            "python3",
            "/tmp/probe.py",
            mounts=("-v", f"{probe.__file__}:/tmp/probe.py:ro"),
        )
    )
    assert document.architecture, "the probe reports the platform it actually ran on"
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
    Can't mount proc on /newroot/proc: Operation not permitted`.
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


# The session environment. `cowork-env` in the image, over a keep file mounted where a run
# mounts it, under an environment polluted with what the harness adds. docs/docker.md, "The
# session environment".


def session(docker: Docker, tmp_path: Path, names: list[str], **environment: str) -> str:
    """What `env` prints through the prefix, with `names` kept and `environment` set."""
    keep = tmp_path / KEEP_FILE
    keep.write_text("".join(f"{name}\n" for name in names))
    variables = [
        value for name, set_to in environment.items() for value in ("--env", f"{name}={set_to}")
    ]
    return container(
        docker,
        "cowork-env",
        "env | sort",
        mounts=(*variables, "-v", f"{keep}:{CONTAINER_KEEP_FILE}:ro"),
    )


def test_the_prefix_keeps_the_listed_names_and_drops_the_rest(docker, tmp_path):
    output = session(
        docker,
        tmp_path,
        ["ACME_KEPT", "PATH"],
        ACME_KEPT="yes",
        ACME_DROPPED="no",
        CLAUDECODE="1",
        CLAUDE_CODE_SESSION_ID="0",
    )
    names = {line.split("=", 1)[0] for line in output.splitlines()}
    assert names == {"ACME_KEPT", "PATH", "PWD", "SHLVL", "_"}, output
    assert "ACME_KEPT=yes" in output.splitlines()


def test_a_listed_name_with_no_value_stays_unset(docker, tmp_path):
    output = session(docker, tmp_path, ["ACME_ABSENT", "ACME_EMPTY"], ACME_EMPTY="")
    assert "ACME_" not in output, output


def test_the_five_derived_names_take_their_session_values(docker, tmp_path):
    output = session(
        docker,
        tmp_path,
        ["HOME", "TMPDIR", "USER", "LOGNAME", "CLAUDE_TMPDIR", "CLAUDE_CODE_TMPDIR", "SHELL"],
        HOME="/x/abc",
        TMPDIR="/x/abc/tmp",
        USER="root",
        CLAUDE_CODE_TMPDIR="/elsewhere",
        SHELL="/bin/bash",
    )
    lines = set(output.splitlines())
    assert {
        "HOME=/x/abc",
        "USER=abc",
        "LOGNAME=abc",
        "TMPDIR=/x/abc/tmp",
        "CLAUDE_TMPDIR=/x/abc/tmp",
        "CLAUDE_CODE_TMPDIR=/x/abc/tmp",
        "SHELL=/bin/sh",
    } <= lines, output


def test_a_line_that_is_no_shell_name_is_skipped(docker, tmp_path):
    output = session(docker, tmp_path, ["ACME-KEY", "PATH"])
    assert "ACME" not in output, output
    assert any(line.startswith("PATH=") for line in output.splitlines()), output


def test_a_case_env_name_is_kept_without_being_listed(docker, tmp_path):
    """The harness restricts a case's `env` keys to `EVAL_[A-Z0-9_]*`. docs/docker.md."""
    output = session(docker, tmp_path, ["PATH"], EVAL_VARIANT="null-body", EVALX="1")
    assert "EVAL_VARIANT=null-body" in output.splitlines(), output
    assert "EVALX" not in output, output


def test_the_image_names_the_prefix_in_managed_settings(docker):
    document = json.loads(container(docker, "cat", "/etc/claude-code/managed-settings.json"))
    assert document["env"]["CLAUDE_CODE_SHELL_PREFIX"] == "/usr/local/bin/cowork-env"


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
    # One case by name: the suite holds two, and this test is about the backend reaching one.
    result = credentialled.run(SMOKE, logs, RunOptions.resolve(runs=1, case="python-version"))
    document = json.loads(result.read_text())

    assert document["schemaVersion"] == 1
    assert document["partial"] is False, document.get("partialReason")
    assert document["aggregates"]["casesTotal"] == 1
    cases = document["cases"]
    assert [case["name"] for case in cases] == ["python-version"]
    runs = cases[0]["arms"]["with"]
    assert runs, "the case produced no run"
    assert all(run["passed"] for run in runs), [run.get("error") for run in runs]


@pytest.mark.live
def test_the_session_env_case_passes_through_the_backend(credentialled, tmp_path):
    """A real `Bash` call sees only the kept names, decided by the case's own checks.

    Through the command and not `Docker.run`, because the checks that read `env.txt` run on
    the host after the backend returns. ../../plugins/README.md.
    """
    root = tmp_path / "logs"
    code = main(
        ["run", "--docker", str(SMOKE), "--out", str(root), "--runs", "1", "--case", "session-env"]
    )
    run = (root / logs.LATEST).resolve()
    decided = (run / logs.VERDICT_FILE).read_text()
    assert code == 0, decided
    assert (run / "smoke" / KEEP_FILE).read_text().split() == list(credentialled.kept)


@pytest.mark.live
def test_a_two_arm_run_is_collected_and_decided_on_its_delta(credentialled, tmp_path):
    """The baseline arm, end to end: six agent runs, two arms collected, one verdict.

    It runs the backend directly rather than the command, because `cowork_evals run` refuses
    this tree: the cases are the harness's own shape and the validator holds every case it is
    given to this repository's format. What is asserted above the backend is still the real
    thing, and `traces.collect` and `verdict.decide` are the ones the command calls.

    What is asserted is the arm and not the scores. Whether sonnet answers a given case well
    is the model's own variance, and a green suite is not what this test is for: the delta is
    worked out, both arms are kept, and the verdict reads the number the document carries.
    """
    directory = tmp_path / "run"
    logs = directory / "eval-smoke"
    logs.mkdir(parents=True)
    options = RunOptions.resolve(ablation="with-without")
    result = credentialled.run(EVAL_SMOKE, logs, options)
    assert traces.collect(logs, granted=options.allow_tools) == []

    document = json.loads(result.read_text())
    assert document["suite"]["ablation"] == "with-without"
    assert verdict.two_arm(ResultDocument.read(result))
    for case in document["cases"]:
        assert case["arms"]["without"], f"{case['name']} ran no baseline arm"
        assert isinstance(case["aggregates"]["delta"], int | float), case["aggregates"]

    # The `tool_used: Skill` grader with no `arm:` is the shape the arm changes: an indicator
    # in the with-arm, and gone from the without-arm.
    france = next(case for case in document["cases"] if case["name"] == "capital-france")
    indicator = next(
        result for result in france["arms"]["with"][0]["graders"] if result["name"] == "skill-fired"
    )
    assert (indicator["withOnly"], indicator["scored"]) == (True, False), indicator
    assert "skill-fired" not in [
        result["name"] for result in france["arms"]["without"][0]["graders"]
    ]

    # The with-arm keeps the layout a one-arm run has, and the baseline arm is under it.
    kept = traces.run_dir(logs, "capital-france", 1)
    baseline = traces.run_dir(logs, "capital-france", 1, arm="without")
    assert (kept / traces.TRACE_NAME).is_file()
    assert (baseline / traces.TRACE_NAME).is_file()
    assert baseline.parent.name == "without"

    decided = verdict.decide(directory, found=3, picked=3)
    assert [line for line in decided.lines if "not comparable" in line] == [], decided.text
    assert re.search(r"mean delta [-+]\d\.\d\d$", decided.lines[-1]), decided.lines[-1]
