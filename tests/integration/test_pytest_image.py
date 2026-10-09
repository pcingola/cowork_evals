"""The test image, against a real daemon and the real image.

Preconditions: a running daemon, the eval image already built by `scripts/image.sh`, and
the test image already built by `scripts/cowork_pytest.sh`. A missing precondition fails
these tests and never skips one. Nothing here builds: a test that builds its own subject
reports a build as a pass.

No credential and no model. Every test runs a fixed command and asserts a fixed result,
so none of these is `live` and none of them spends.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from cowork_evals.config import Config, DockerSection
from cowork_evals.docker import Condition, DockerError, remedy
from cowork_evals.docker.parity import EXPECTED_VERSIONS
from cowork_evals.docker.pytest_image import BUILD_REMEDY, REQUIREMENTS_TEST, PytestImage
from cowork_evals.requirements import pins

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "plugins" / "smoke"
RUNTIME = SMOKE / "tests" / "test_runtime.py"
PASSES = SMOKE / "tests" / "test_passes.py"
FAILS = SMOKE / "tests" / "test_fails.py"
NEEDS_311 = SMOKE / "tests" / "test_needs_311.py"

# docs/runtime.md, the core runtime table, read through the one place that records it.
PYTHON_VERSION = f"Python {EXPECTED_VERSIONS['python3']}"

# The three assertions plugins/smoke/tests/test_runtime.py makes, by name.
ASSERTIONS = (
    "test_the_interpreter_is_3_10",
    "test_uno_imports_from_the_libreoffice_program_directory",
    "test_a_pinned_cowork_wheel_imports",
)


@pytest.fixture(scope="session")
def image() -> PytestImage:
    """Both images, asserted once. Nothing here builds either."""
    configured = PytestImage()
    assert configured.docker.daemon_is_reachable(), (
        f"docker daemon is not reachable: {remedy(Condition.DAEMON)}"
    )
    assert configured.docker.image_is_present(), (
        f"base image {configured.docker.tag} is absent: {remedy(Condition.IMAGE)}"
    )
    assert configured.image_is_present(), (
        f"{configured.tag} is absent: {BUILD_REMEDY}, which no test here runs"
    )
    return configured


def output(image: PytestImage, target: Path, *pytest_args: str) -> tuple[int, str]:
    """One real run, through the backend's own argument list, with the output captured.

    `run` inherits the terminal, which is what a caller wants and what a test cannot
    read. Only the capture differs: the argument list is the one `run` uses.
    """
    completed = subprocess.run(
        image.run_argv(target, pytest_args=pytest_args),
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout + completed.stderr


def container(image: PytestImage, *command: str) -> str:
    """That image, one fixed command, no mount. Not the run argument list.

    What this asserts is a property of the image itself, not of the way a suite is run.
    """
    completed = subprocess.run(
        ["docker", "run", "--rm", "--platform", image.platform, image.tag, *command],
        capture_output=True,
        text=True,
    )
    return (completed.stdout + completed.stderr).strip()


def freeze(tag: str, platform: str) -> dict[str, str]:
    completed = subprocess.run(
        ["docker", "run", "--rm", "--platform", platform, tag, "python3", "-m", "pip", "freeze"],
        capture_output=True,
        text=True,
        check=True,
    )
    return pins(completed.stdout)


# The exit code, unchanged.


def test_a_trivial_passing_test_returns_zero(image):
    """A green suite that asserts nothing about the runtime."""
    assert image.run(PASSES) == 0


def test_the_runtime_fixture_returns_zero(image):
    assert image.run(RUNTIME) == 0


def test_the_runtime_fixture_names_its_three_assertions(image):
    """The `-v` is the caller's, forwarded verbatim. Nothing here chose it."""
    code, text = output(image, RUNTIME, "-v")
    assert code == 0
    for name in ASSERTIONS:
        assert name in text
    assert "3 passed" in text


def test_the_failing_fixture_returns_one(image):
    """A red suite is a result, not an error. Nothing raises on it."""
    assert image.run(FAILS) == 1


def test_a_test_written_for_3_11_grammar_returns_two(image):
    """`except*` does not parse on 3.10, so the file is a collection error.

    This is the failure the whole mechanism exists to produce: a suite written against a
    newer interpreter than a session has fails here, rather than passing on a laptop and
    failing in a session. pytest's code for an interrupted collection is 2, and it reaches
    the caller as 2 and not as 1.
    """
    code, text = output(image, NEEDS_311)
    assert code == 2
    assert "SyntaxError" in text
    assert "1 error during collection" in text


def test_a_path_that_collects_no_test_returns_five(image):
    """pytest's own code for it, not collapsed to 1."""
    assert image.run(SMOKE / "evals") == 5


def test_an_absent_image_raises_before_any_container_starts():
    """A precondition, and the caller turns it into its own exit code."""
    absent = PytestImage(Config(docker=DockerSection(claude_code_version="0.0.0-absent")))
    with pytest.raises(DockerError):
        absent.run(PASSES)


def test_check_reports_an_absent_image_and_never_the_credential(image):
    """`check` reads the daemon and both image tags, so it belongs in this tier.

    There is no login in this path, so no state of this machine can make it ask for one.
    The base tag below names an image no build produced, which is the one unmet condition
    a machine with a reachable daemon and both images can still be shown.
    """
    assert image.check() == [], f"both images are present: {image.tag}"
    absent = PytestImage(Config(docker=DockerSection(claude_code_version="0.0.0-absent")))
    unmet = absent.check()
    assert [line.condition for line in unmet] == [Condition.IMAGE]
    assert absent.docker.tag in unmet[0].message


# What the container is.


def test_python_in_the_container_is_the_version_runtime_md_records(image):
    assert container(image, "python3", "-V") == PYTHON_VERSION


def test_the_test_image_adds_the_pinned_list_and_moves_nothing(image):
    """The assertion the whole mechanism rests on.

    A `pip install pytest` that moved `packaging` or any other inventory pin would leave
    the suite running against a runtime the CoWork image does not have.
    """
    base = freeze(image.docker.tag, image.platform)
    test = freeze(image.tag, image.platform)
    added = set(pins(REQUIREMENTS_TEST.read_text()))
    assert set(test) - set(base) == added
    assert set(base) - set(test) == set()
    assert {name: test[name] for name in base} == base


# What the container writes.


def test_a_test_that_writes_into_the_tree_leaves_the_file_to_the_developer(image, plugin):
    """The container runs as the host uid and gid, so nothing it writes is root's.

    A bind mount on macOS maps ownership itself, so the second assertion is load-bearing
    on Linux and free here. The first is load-bearing everywhere: the mount is read-write,
    unlike a `run --docker`.
    """
    (plugin / "tests" / "test_writes.py").write_text(
        "from pathlib import Path\n"
        "\n"
        "\n"
        "def test_it_writes_beside_itself():\n"
        "    Path(__file__).parent.joinpath('written.txt').write_text('written')\n"
    )
    assert image.run(plugin) == 0
    written = plugin / "tests" / "written.txt"
    assert written.read_text() == "written"
    assert written.stat().st_uid == os.getuid()


def test_the_junitxml_tail_leaves_the_report_in_the_plugin_root(image, plugin):
    """Nothing in this package arranged for it: the tree is writable and the tail is the
    caller's."""
    (plugin / "tests" / "test_one.py").write_text("def test_one():\n    assert True\n")
    assert image.run(plugin, pytest_args=("--junitxml=report.xml",)) == 0
    report = plugin / "report.xml"
    assert "<testsuite" in report.read_text()


def test_pytest_writes_its_cache_into_the_tree_as_it_does_on_a_laptop(image, plugin):
    """A read-only mount would change what a suite does, so the mount is read-write."""
    (plugin / "tests" / "test_one.py").write_text("def test_one():\n    assert True\n")
    assert image.run(plugin) == 0
    assert (plugin / ".pytest_cache").is_dir()
