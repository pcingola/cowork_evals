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

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import yaml

from cowork_evals import Config, checks, logs, panel, preflight, traces, verdict
from cowork_evals.cli import main
from cowork_evals.config import CONFIG_FILENAME
from cowork_evals.docker import Condition, Docker, remedy
from cowork_evals.docker.pytest_image import BUILD_REMEDY, PytestImage
from cowork_evals.harness import RESULT_NAME
from cowork_evals.preflight import COWORK

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "plugins" / "smoke"

# What `run --docker` prints into `run.log` from inside the container. It is the harness's
# own first line, so a line here proves the tee reached a child process.
HARNESS_LINE = "Plugin under test:"


@pytest.fixture(scope="session")
def images() -> PytestImage:
    """Both images and the daemon, asserted once. Nothing here builds either."""
    configured = PytestImage()
    assert configured.docker.daemon_is_reachable(), (
        f"docker daemon is not reachable: {remedy(Condition.DAEMON)}"
    )
    assert configured.docker.image_is_present(), (
        f"{configured.docker.tag} is absent: {remedy(Condition.IMAGE)}, which no test here runs"
    )
    assert configured.image_is_present(), (
        f"{configured.tag} is absent: {BUILD_REMEDY}, which no test here runs"
    )
    return configured


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


def command(*argv: str) -> subprocess.CompletedProcess:
    """The installed executable, which is what a consumer runs."""
    assert EXECUTABLE.is_file(), f"{EXECUTABLE} is absent: run scripts/venv.sh"
    return subprocess.run([str(EXECUTABLE), *argv], capture_output=True, text=True, cwd=ROOT)


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


def test_setup_docker_does_not_touch_the_credential(images, capsys) -> None:
    """It builds, and building is all it does. Both images here are already current.

    A `setup` that also logged in would start an interactive container from this test.
    """
    code = main(["setup", "--docker"])
    printed = capsys.readouterr()
    assert code == 0, printed.err
    assert printed.out.splitlines() == [
        f"{images.docker.tag}: current",
        f"{images.tag}: current",
    ]


# run.


@pytest.mark.live
def test_a_docker_run_writes_the_whole_log_layout_and_passes(credentialled, tmp_path) -> None:
    """One real run, and every assertion this tier can make over it.

    The plugin directory itself, not `evals/` beneath it: the target sets the containment
    root, and the case's `plugins` entry has to resolve inside it.
    """
    root = tmp_path / "logs"
    # One case by name. `plugins/smoke/` holds two, and this test is about the log layout
    # over one run rather than about the suite. See ../../plugins/README.md.
    code = main(
        [
            "run",
            "--docker",
            str(SMOKE),
            "--out",
            str(root),
            "--runs",
            "1",
            "--case",
            "python-version",
        ]
    )
    assert code == 0, (root / logs.LATEST / logs.VERDICT_FILE).read_text()

    run = (root / logs.LATEST).resolve()
    for name in (logs.RUN_LOG, logs.ENV_FILE, logs.VERDICT_FILE):
        assert (run / name).is_file(), f"{name} is absent from {run}"
    for name in (RESULT_NAME, "report.html", "debug.txt"):
        assert (run / "smoke" / name).is_file(), f"smoke/{name} is absent from {run}"

    assert (root / logs.LATEST).is_symlink()
    assert os.readlink(root / logs.LATEST) == run.name

    document = json.loads((run / "smoke" / RESULT_NAME).read_text())
    assert document["aggregates"]["casesTotal"] == 1
    assert document["partial"] is False, document.get("partialReason")

    # The same run, not a second one. The tee is at the descriptor level, so the
    # container's output reaches the file; wrapping `sys.stdout` would leave it empty.
    assert HARNESS_LINE in (run / logs.RUN_LOG).read_text()

    # `env.txt` says which version produced the log, and which image.
    recorded = (run / logs.ENV_FILE).read_text()
    assert "backend: docker\n" in recorded
    assert f"image: {credentialled.tag}\n" in recorded

    # The run's trace, collected out of a sandbox that only existed inside the container.
    # Neither the redirected TMPDIR nor the collection can be reached without a real run.
    kept = traces.run_dir(run / "smoke", "python-version", 1)
    assert (kept / traces.TRACE_NAME).is_file(), f"no trace under {kept}"
    assert (kept / traces.LAST_MESSAGE_NAME).read_text().strip() == "Python 3.10.12"
    assert not traces.sandbox_root(run / "smoke").exists(), "the sandboxes are not left behind"

    # And the document points at where the trace now is, not at a path inside the container.
    trace_path = document["cases"][0]["arms"]["with"][0]["tracePath"]
    assert Path(trace_path) == kept / traces.TRACE_NAME
    assert Path(trace_path).is_file()


# A grant carrying nothing that can create a file. The narrowing is this test's, and the
# default in `cowork_evals.yaml` is untouched. The option replaces the value rather than
# adding to it, so this is the whole grant. `Bash` and `Edit` are dropped with `Write`: the
# snapshot in ../../docs/running_evals.md measured a `Write` call going through under a grant
# that named those two, so leaving either in would grade a run that had a way to write.
WITHOUT_A_WRITER = ["Read", "Glob", "Grep", "Skill"]


@pytest.mark.live
def test_a_run_that_never_got_write_fails_instead_of_scoring(credentialled, tmp_path) -> None:
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
            str(SMOKE),
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

    document = json.loads((run / "smoke" / RESULT_NAME).read_text())
    entry = document["cases"][0]["arms"]["with"][0]
    assert traces.DENIED in entry or traces.UNOFFERED in entry, entry


@pytest.mark.live
def test_a_check_decides_the_run_beside_the_harness_graders(credentialled, tmp_path) -> None:
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
            str(SMOKE),
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

    document = json.loads((run / "smoke" / RESULT_NAME).read_text())
    case = document["cases"][0]
    assert [grader["type"] for grader in case["graders"]] == ["file_exists", "check", "check"]
    entry = case["arms"]["with"][0]
    assert [(result["name"], result["passed"]) for result in entry["graders"]] == [
        ("writes-written-txt", True),
        ("assertions.the_file_says_written", True),
        ("assertions.the_file_is_a_workbook", False),
    ]
    assert entry["score"] == 2 / 3
    assert entry["passed"] is False
    assert case["aggregates"] == {"score": 2 / 3, "passRate": 0.0}

    lines = [json.loads(line) for line in (kept / checks.CHECKS_FILE).read_text().splitlines()]
    assert [line["name"] for line in lines] == [
        "assertions.the_file_says_written",
        "assertions.the_file_is_a_workbook",
    ]
    assert lines[0]["passed"] is True
    assert lines[1]["explanation"] == "written.txt is not a workbook"
    assert (kept / checks.SCRATCH_DIR).is_dir()
    assert (kept / traces.WORKSPACE_NAME / "written.txt").is_file()


# test.


def test_a_passing_suite_returns_zero_through_the_executable(images) -> None:
    """It costs a container and no model call, so it is not `live`.

    What the container itself proves is integration/test_pytest_image.py's. This proves
    that the verb reaches it and returns its code.
    """
    completed = command("test", "--docker", str(SMOKE / "tests" / "test_passes.py"))
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_a_failing_suite_returns_one_through_the_executable(images) -> None:
    completed = command("test", "--docker", str(SMOKE / "tests" / "test_fails.py"))
    assert completed.returncode == 1, completed.stdout + completed.stderr


def test_the_test_verb_writes_nothing_on_the_host(images, tmp_path) -> None:
    """No run directory, no `env.txt`, no `latest`, no pruning and no verdict."""
    before = sorted(ROOT.iterdir())
    completed = command("test", "--docker", str(SMOKE / "tests" / "test_passes.py"))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert sorted(ROOT.iterdir()) == before


# panel.


def elsewhere(tmp_path: Path, section: str) -> Path:
    """This machine's configuration with the given keys merged into it, in a new working
    directory.

    Every other key is this machine's own, so the login and any extra root CA are the ones a
    run here already uses. `docker.login_dir` and `docker.extra_ca_file` are written back as
    the loaded section resolved them, because a relative path in the source file would
    otherwise resolve against this directory instead of the repository.
    """
    source = ROOT / CONFIG_FILENAME
    assert source.is_file(), f"{CONFIG_FILENAME} is not in the repository root"
    document = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    settings = Config.load(source).docker
    docker = document.setdefault("docker", {})
    docker["login_dir"] = str(settings.login_dir)
    if settings.extra_ca_file is not None:
        docker["extra_ca_file"] = str(settings.extra_ca_file)
    for name, values in (yaml.safe_load(section) or {}).items():
        document.setdefault(name, {}).update(values)

    (tmp_path / CONFIG_FILENAME).write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )
    return tmp_path


@pytest.mark.live
def test_a_run_writes_a_record_the_panel_then_shows(credentialled, tmp_path, monkeypatch, capsys):
    """One real run, then the verb over the history it left.

    The history root is named in a configuration file this test writes, which is what a
    consumer writes and not a seam: `--out` does not move the history, so a test left on the
    default would append to the developer's own tree.
    """
    history = tmp_path / "history"
    monkeypatch.chdir(elsewhere(tmp_path, f"panel:\n  root: {history}\n"))
    root = tmp_path / "logs"

    code = main(
        [
            "run",
            "--docker",
            str(SMOKE),
            "--out",
            str(root),
            "--runs",
            "1",
            "--case",
            "python-version",
        ]
    )
    assert code == 0, (root / logs.LATEST / logs.VERDICT_FILE).read_text()
    run = (root / logs.LATEST).resolve()

    file = panel.path(history, "smoke", "evals/plugin/python-version")
    records, warnings = panel.read(file)
    assert warnings == []
    assert len(records) == 1
    entry = records[0]
    assert entry.backend == "docker"
    assert entry.invocation == run.name
    assert entry.image == credentialled.tag
    assert entry.outcome == "pass"
    assert entry.case_digest == panel.digest(SMOKE / "evals" / "plugin" / "python-version")
    assert entry.trace_path is not None and Path(entry.trace_path).is_file()

    capsys.readouterr()
    assert main(["panel", str(SMOKE)]) == 0
    printed = capsys.readouterr()
    assert printed.err == ""
    row = next(line for line in printed.out.splitlines() if "python-version" in line)
    assert "pass 0d" in row
    assert "never run" in row
    assert verdict.display(Path(entry.trace_path).parent) in row
    # The four cases this run did not select have no record and say so. `python-version`
    # has a record on Docker and none on CoWork, so it carries one `never run` of its own.
    assert sum(1 for line in printed.out.splitlines() if "never run" in line) == 5


# ask.

# A prompt the session answers from itself. It calls no tool, so the run is the floor a
# session costs and the marker is unambiguous in the printed answer.
MARKER = "ASKED"
ASK_PROMPT = f"Reply with the single word: {MARKER}"


@pytest.fixture
def cowork_ready() -> None:
    """The CoWork preflight, asserted before a test spends a VM boot on it.

    It fails the test rather than skipping it, and its lines name the fix, which is the whole
    point of the preflight.
    """
    unmet = preflight.checks(COWORK, Config.load(ROOT / "cowork_evals.yaml"))
    assert unmet == [], "\n".join(unmet)


@pytest.mark.live
def test_one_ask_prints_a_non_empty_answer_and_names_a_session_that_exists(
    cowork_ready, attended: Path, monkeypatch, capsys
) -> None:
    """One submission, one printed answer, and no run directory anywhere.

    It calls `main` rather than the executable, so the footer is read off the two streams
    this command wrote rather than out of a subprocess's buffers. `main` reads the
    configuration file in the working directory, so the working directory is the one the
    `attended` fixture wrote its file into, exactly as a consumer runs the command from a
    directory holding one. The `keyboard` fixture has already asked, so this submission
    shows nothing.
    """
    monkeypatch.chdir(attended.parent)
    before = sorted(ROOT.iterdir())
    assert main(["ask", "--cowork", ASK_PROMPT]) == 0
    printed = capsys.readouterr()

    assert MARKER in printed.out
    named = [line for line in printed.err.splitlines() if line.startswith("session: ")]
    assert len(named) == 1
    assert Path(named[0].removeprefix("session: ")).is_dir()
    assert sorted(ROOT.iterdir()) == before


# Environment passthrough. docs/docker.md.

# A name no machine sets, and a token that is in no other file on this host. The variable is
# set in this process, which is the environment the backend reads: it is a real variable and
# not a seam. Nothing here prints the token.
PROBE = "COWORK_EVALS_INTEGRATION_PROBE"


def forwarding(tmp_path: Path) -> Path:
    """This machine's configuration with `PROBE` forwarded, in a new working directory."""
    return elsewhere(tmp_path, f"docker:\n  env_passthrough: [{PROBE}]\n")


@pytest.mark.live
def test_a_forwarded_variable_reaches_a_run_and_its_value_reaches_no_artefact(
    credentialled, tmp_path, monkeypatch
) -> None:
    """One case, with one variable forwarded, and the token grepped for after.

    The grep is over every file the run left, not the named artefacts alone, so a kept trace
    or a report is covered by the same assertion. What the container prints reaches `run.log`
    and this case prints nothing of it; that limit is in ../../docs/docker.md.

    One case by name, as every test here that fires one: `checked-file` always exits 1, and
    this test is about what the forwarded value did not reach. See ../../plugins/README.md.
    """
    token = uuid.uuid4().hex
    monkeypatch.setenv(PROBE, token)
    monkeypatch.chdir(forwarding(tmp_path))
    root = tmp_path / "logs"

    code = main(
        [
            "run",
            "--docker",
            str(SMOKE),
            "--out",
            str(root),
            "--runs",
            "1",
            "--case",
            "writes-a-file",
        ]
    )
    assert code == 0, (root / logs.LATEST / logs.VERDICT_FILE).read_text()

    run = (root / logs.LATEST).resolve()
    assert f"env_passthrough: {PROBE}\n" in (run / logs.ENV_FILE).read_text()
    carrying = [
        path.relative_to(run)
        for path in sorted(run.rglob("*"))
        if path.is_file() and not path.is_symlink() and token.encode() in path.read_bytes()
    ]
    assert carrying == []


def test_a_forwarded_variable_the_host_has_not_set_refuses_before_anything_is_created(
    credentialled, tmp_path, monkeypatch, capsys
) -> None:
    """Exit 3, the variable named, no value, and no log root. It spends nothing."""
    monkeypatch.delenv(PROBE, raising=False)
    monkeypatch.chdir(forwarding(tmp_path))
    root = tmp_path / "logs"

    assert main(["run", "--docker", str(SMOKE), "--out", str(root)]) == 3
    printed = capsys.readouterr()
    assert [line for line in printed.err.splitlines() if PROBE in line]
    assert not root.exists()
