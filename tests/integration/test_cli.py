"""The command, through the real executable and against real backends.

Preconditions: a running daemon, the eval image already built by `scripts/image.sh`, the
test image already built by `scripts/cowork_pytest.sh`, and one credential route. A missing
precondition fails these tests and never skips one. Nothing here builds: a test that builds
its own subject reports a build as a pass.

Every test but one needs no CoWork profile. Everything the command builds above a backend is
backend-neutral and is proven on `--docker` below, and the option mapping is proven with
`--dry-run --cowork` in the unit tier.

The one that does is `ask`, which reaches a live session and cannot be proven any other way.
It needs a signed-in CoWork, the desktop application running, the macOS Accessibility grant
and `cowork_evals.yaml` naming the active profile. A missing precondition fails it and never
skips it, and it carries `live`: it costs a VM boot, one entry against the driver's rate
ceiling, and a permanent session in the account.

Nothing here prints a path, a prompt or an identifier. Public repository rule.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from cowork_evals import Config, checks, logs, panel, preflight, traces
from cowork_evals.checks import Outcome
from cowork_evals.cli import main
from cowork_evals.config import CONFIG_FILENAME
from cowork_evals.docker import Condition, Docker, remedy
from cowork_evals.docker.pytest_image import PytestImage
from cowork_evals.harness import RESULT_NAME
from cowork_evals.preflight import COWORK
from cowork_evals.results import ResultDocument

# What `run --docker` prints into `run.log` from inside the container. It is the harness's
# own first line, so a line here proves the tee reached a child process.
HARNESS_LINE = "Plugin under test:"


@pytest.fixture
def credentialled(images: PytestImage) -> Docker:
    """The eval image plus the container login, for the one test that spends."""
    assert images.docker.has_credential(), (
        f"no credential: {remedy(Condition.CREDENTIAL)}. docs/docker.md."
    )
    return images.docker


# The `[project.scripts]` entry point, beside the interpreter running these tests. An
# absent one is a distribution that was never installed, and it fails a test here.
EXECUTABLE = Path(sys.executable).parent / "cowork_evals"


def command(
    *argv: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    """The installed executable, which is what a consumer runs, in `cwd` and under `env`."""
    assert EXECUTABLE.is_file(), f"{EXECUTABLE} is absent: run scripts/venv.sh"
    return subprocess.run(
        [str(EXECUTABLE), *argv], capture_output=True, text=True, cwd=cwd, env=env
    )


def elsewhere(
    tmp_path: Path,
    repository: Path,
    *,
    forwarded: tuple[str, ...] | None = None,
    history: Path | None = None,
) -> Path:
    """This machine's configuration, with the forwarded names and the history root replaced
    where given, written into a new working directory.

    Every other key is this machine's own, so the login and any extra root CA are the ones a
    run here already uses. `Config.load` resolves `docker.login_dir` and
    `docker.extra_ca_file`, so they are written as the paths they resolve to here.
    """
    source = repository / CONFIG_FILENAME
    assert source.is_file(), f"{CONFIG_FILENAME} is not in the repository root"
    config = Config.load(source)
    if forwarded is not None:
        docker = dataclasses.replace(config.docker, env_passthrough=forwarded)
        config = dataclasses.replace(config, docker=docker)
    if history is not None:
        config = dataclasses.replace(config, panel=dataclasses.replace(config.panel, root=history))
    config.dump(tmp_path / CONFIG_FILENAME)
    return tmp_path


# check.


def test_check_docker_returns_zero_on_a_ready_machine(images, capsys) -> None:
    """And its lines name the fix when it does not, which is what the message says."""
    code = main(["check", "--docker"])
    printed = capsys.readouterr()
    assert code == 0, printed.err
    assert printed.out.strip() == "ready"


# login.


def test_login_check_reports_the_credential_this_machine_holds(credentialled, capsys) -> None:
    """It reads the real credential, starts no container and writes nothing.

    The interactive half cannot be asserted without a person at a browser, so what is
    asserted here is the half that is decidable: the report, against the real login the rest
    of this tier needs anyway.
    """
    code = main(["login", "--docker", "--check"])
    printed = capsys.readouterr()
    assert code == 0, printed.err
    assert printed.out.strip() == f"{credentialled.credentials_file}: current"


def test_setup_docker_does_not_touch_the_credential(images, credentialled, capsys) -> None:
    """It builds, and building is all it does. Both images here are already current.

    A `setup` that also logged in would start an interactive container from this test.
    """
    credential = credentialled.credentials_file
    before = (credential.read_bytes(), credential.stat().st_mtime_ns)
    code = main(["setup", "--docker"])
    printed = capsys.readouterr()
    assert code == 0, printed.err
    assert printed.out.splitlines() == [
        f"{images.docker.tag}: current",
        f"{images.tag}: current",
    ]
    assert (credential.read_bytes(), credential.stat().st_mtime_ns) == before


# run.


# A name no machine sets, and a token that is in no other file on this host. The variable is
# set in the environment of the executable this test runs, which is the environment the
# backend reads. Nothing here prints the token.
PROBE = "COWORK_EVALS_INTEGRATION_PROBE"


@pytest.mark.live
def test_a_docker_run_writes_the_whole_log_layout_and_passes(
    credentialled, repository: Path, tmp_path: Path
) -> None:
    """One real run, and every assertion this tier can make over it: the log layout, the
    panel record and its row, and a forwarded value that reaches no artefact.

    The plugin directory itself, not `evals/` beneath it: the target sets the containment
    root, and the case's `plugins` entry has to resolve inside it. The history root is named
    in the configuration file this test writes, because `--out` does not move the history.
    One case by name; see ../../plugins/README.md.
    """
    smoke = repository / "plugins" / "smoke"
    history = tmp_path / "history"
    elsewhere(tmp_path, repository, forwarded=(PROBE,), history=history)
    root = tmp_path / "logs"
    token = uuid.uuid4().hex
    completed = command(
        "run",
        "--docker",
        str(smoke),
        "--out",
        str(root),
        "--runs",
        "1",
        "--case",
        "python-version",
        cwd=tmp_path,
        env={**os.environ, PROBE: token},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    run = (root / logs.LATEST).resolve()
    for name in (logs.RUN_LOG, logs.ENV_FILE, logs.VERDICT_FILE):
        assert (run / name).is_file(), f"{name} is absent from {run}"
    for name in (RESULT_NAME, "report.html", "debug.txt"):
        assert (run / "smoke" / name).is_file(), f"smoke/{name} is absent from {run}"

    document = ResultDocument.model_validate_json((run / "smoke" / RESULT_NAME).read_text())
    assert document.aggregates.cases_total == 1
    assert document.partial is False, document.partial_reason

    # The tee is at the descriptor level, so the container's output reaches the file;
    # wrapping `sys.stdout` would leave it empty.
    assert HARNESS_LINE in (run / logs.RUN_LOG).read_text()

    # The run's trace, collected out of a sandbox that only existed inside the container.
    # Neither the redirected TMPDIR nor the collection can be reached without a real run.
    kept = traces.run_dir(run / "smoke", "python-version", 1)
    assert (kept / traces.TRACE_NAME).is_file(), f"no trace under {kept}"
    assert (kept / traces.LAST_MESSAGE_NAME).read_text().strip() == "Python 3.10.12"
    assert not traces.sandbox_root(run / "smoke").exists(), "the sandboxes are not left behind"

    # And the document points at where the trace now is, not at a path inside the container.
    trace_path = document.cases[0].arms.with_[0].trace_path
    assert trace_path is not None and Path(trace_path) == kept / traces.TRACE_NAME

    # The forwarded name is recorded, and its value is in no file the run left. What the
    # container prints reaches `run.log` and this case prints nothing of it; that limit is in
    # ../../docs/docker.md.
    assert f"env_passthrough: {PROBE}\n" in (run / logs.ENV_FILE).read_text()
    carrying = [
        path.relative_to(run)
        for path in sorted(run.rglob("*"))
        if path.is_file() and not path.is_symlink() and token.encode() in path.read_bytes()
    ]
    assert carrying == []

    # The record the run appended, and the panel row over it.
    records, warnings = panel.read(panel.path(history, "smoke", "evals/plugin/python-version"))
    assert warnings == []
    assert len(records) == 1
    entry = records[0]
    assert entry.backend == "docker"
    assert entry.invocation == run.name
    assert entry.image == credentialled.tag
    assert entry.outcome == "pass"
    assert entry.case_digest is not None
    assert entry.trace_path is not None and Path(entry.trace_path).is_file()

    shown = command("panel", str(smoke), cwd=tmp_path)
    assert shown.returncode == 0, shown.stderr
    assert shown.stderr == ""
    row = next(line for line in shown.stdout.splitlines() if "python-version" in line)
    assert "pass 0d" in row
    assert "never run" in row
    assert str(Path(entry.trace_path).parent.relative_to(tmp_path)) in row


# A grant carrying nothing that can create a file. The narrowing is this test's, and the
# default in `cowork_evals.yaml` is untouched. The option replaces the value rather than
# adding to it, so this is the whole grant. `Bash` and `Edit` are dropped with `Write`: the
# snapshot in ../../docs/running_evals.md measured a `Write` call going through under a grant
# that named those two, so leaving either in would grade a run that had a way to write.
WITHOUT_A_WRITER = ["Read", "Glob", "Grep", "Skill"]


@pytest.mark.live
def test_a_run_that_never_got_write_fails_instead_of_scoring(
    credentialled, repository: Path, tmp_path: Path
) -> None:
    """The case asks for a `Write` call and the grant carries no tool that can create a file.

    Whether the trace answers with a denial record or with an `init` list missing the name
    is the harness's, and the verdict fails the run either way. What cannot be reached
    without a real run is that one of the two is written at all.
    """
    root = tmp_path / "logs"
    code = main(
        [
            "run",
            "--docker",
            str(repository / "plugins" / "smoke"),
            "--out",
            str(root),
            "--runs",
            "1",
            "--case",
            "writes-a-file",
            "--allow-tools",
            *WITHOUT_A_WRITER,
        ]
    )
    run = (root / logs.LATEST).resolve()
    verdict = (run / logs.VERDICT_FILE).read_text()
    assert code == 1, verdict
    named = [line for line in verdict.splitlines() if line.startswith("FAIL ") and "Write" in line]
    assert named, verdict

    document = ResultDocument.model_validate_json((run / "smoke" / RESULT_NAME).read_text())
    entry = document.cases[0].arms.with_[0]
    assert entry.denied_tools is not None or entry.unoffered_tools is not None, entry


@pytest.mark.live
def test_a_check_decides_the_run_beside_the_harness_graders(
    credentialled, repository: Path, tmp_path: Path
) -> None:
    """One real run of the case that carries two checks, one of which fails on purpose.

    What cannot be reached without a real run is that the layer finds the collected run
    directory the container backend produced, that an author's own Python decides a case the
    harness had already graded, and that the `FAIL` line names where its artefacts are. See
    ../../plugins/README.md and ../../docs/checks.md.
    """
    root = tmp_path / "logs"
    code = main(
        [
            "run",
            "--docker",
            str(repository / "plugins" / "smoke"),
            "--out",
            str(root),
            "--runs",
            "1",
            "--case",
            "checked-file",
        ]
    )
    run = (root / logs.LATEST).resolve()
    decided = (run / logs.VERDICT_FILE).read_text()
    assert code == 1, decided

    kept = traces.run_dir(run / "smoke", "checked-file", 1)
    assert [line for line in decided.splitlines() if line.startswith("FAIL ")] == [
        f"FAIL smoke/checked-file: run 1: assertions.the_file_is_a_workbook: "
        f"the check grader failed: written.txt is not a workbook [artifacts: {kept}]"
    ]

    written = (kept / checks.CHECKS_FILE).read_text().splitlines()
    assert [Outcome.from_line(line).name for line in written] == [
        "assertions.the_file_says_written",
        "assertions.the_file_is_a_workbook",
    ]
    assert (kept / checks.SCRATCH_DIR).is_dir()
    assert (kept / traces.WORKSPACE_NAME / "written.txt").is_file()


# test.


@pytest.mark.parametrize(("suite", "expected"), [("test_passes.py", 0), ("test_fails.py", 1)])
def test_the_test_verb_returns_the_suite_code_and_writes_nothing_on_the_host(
    images, repository: Path, tmp_path: Path, suite: str, expected: int
) -> None:
    """It costs a container and no model call, so it is not `live`.

    What the container itself proves is integration/test_pytest_image.py's. This proves that
    the verb reaches it, returns its code, and leaves no run directory, no `env.txt`, no
    `latest` and no verdict in the directory it ran from. The configuration is this
    machine's, so the image tags are the built ones.
    """
    elsewhere(tmp_path, repository)
    target = repository / "plugins" / "smoke" / "tests" / suite
    completed = command("test", "--docker", str(target), cwd=tmp_path)
    assert completed.returncode == expected, completed.stdout + completed.stderr
    assert [path.name for path in tmp_path.iterdir()] == [CONFIG_FILENAME]


# ask.

# A prompt the session answers from itself. It calls no tool, so the run is the floor a
# session costs and the marker is unambiguous in the printed answer.
MARKER = "ASKED"
ASK_PROMPT = f"Reply with the single word: {MARKER}"


@pytest.fixture
def cowork_ready(repository: Path) -> None:
    """The CoWork preflight, asserted before a test spends a VM boot on it.

    It fails the test rather than skipping it, and its lines name the fix, which is the whole
    point of the preflight.
    """
    unmet = preflight.checks(COWORK, Config.load(repository / CONFIG_FILENAME))
    assert unmet == [], "\n".join(unmet)


@pytest.mark.live
def test_one_ask_prints_a_non_empty_answer_and_names_a_session_that_exists(
    cowork_ready, attended: Config, working_directory, tmp_path: Path, capsys
) -> None:
    """One submission, one printed answer, and no run directory anywhere.

    It calls `main` rather than the executable, so the footer is read off the two streams
    this command wrote rather than out of a subprocess's buffers. `main` reads the
    configuration file in the working directory, so the `attended` configuration is written
    into a new one, exactly as a consumer runs the command from a directory holding one. The
    `keyboard` fixture has already asked, so this submission shows nothing.
    """
    attended.dump(tmp_path / CONFIG_FILENAME)
    with working_directory(tmp_path):
        assert main(["ask", "--cowork", ASK_PROMPT]) == 0
    printed = capsys.readouterr()

    assert MARKER in printed.out
    named = [line for line in printed.err.splitlines() if line.startswith("session: ")]
    assert len(named) == 1
    assert Path(named[0].removeprefix("session: ")).is_dir()
    assert sorted(path.name for path in tmp_path.iterdir()) == [CONFIG_FILENAME]
