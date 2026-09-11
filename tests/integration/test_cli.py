"""The command, through the real executable and against real backends.

Preconditions: a running daemon, the eval image already built by `scripts/image.sh`, the
test image already built by `scripts/cowork_pytest.sh`, and one credential route. A missing
precondition fails these tests and never skips one. Nothing here builds: a test that builds
its own subject reports a build as a pass.

No CoWork profile is needed. There is no live CoWork run here, for the reason in
../../plans/plan_cli.md: everything this plan built above a backend is backend-neutral and
is proven on `--docker` below, and the option mapping is proven with `--dry-run --cowork`
in the unit tier.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cowork_evals import logs, traces
from cowork_evals.cli import main
from cowork_evals.docker import Condition, Docker, remedy
from cowork_evals.docker.pytest_image import BUILD_REMEDY, PytestImage
from cowork_evals.harness import RESULT_NAME

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


# run.


@pytest.mark.live
def test_a_docker_run_writes_the_whole_log_layout_and_passes(credentialled, tmp_path) -> None:
    """One real run, and every assertion this tier can make over it.

    The plugin directory itself, not `evals/` beneath it: the target sets the containment
    root, and the case's `plugins` entry has to resolve inside it.
    """
    root = tmp_path / "logs"
    code = main(["run", "--docker", str(SMOKE), "--out", str(root), "--runs", "1"])
    assert code == 0, (root / logs.LATEST / logs.GATE_FILE).read_text()

    run = (root / logs.LATEST).resolve()
    for name in (logs.RUN_LOG, logs.ENV_FILE, logs.GATE_FILE):
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
    """No run directory, no `env.txt`, no `latest`, no pruning and no gate."""
    before = sorted(ROOT.iterdir())
    completed = command("test", "--docker", str(SMOKE / "tests" / "test_passes.py"))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert sorted(ROOT.iterdir()) == before
