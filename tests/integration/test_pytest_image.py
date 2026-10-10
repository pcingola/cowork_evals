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
from cowork_evals.docker import Condition, DockerError
from cowork_evals.docker.pytest_image import REQUIREMENTS_TEST, PytestImage
from cowork_evals.requirements import pins


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


def freeze(tag: str, platform: str) -> dict[str, str]:
    completed = subprocess.run(
        ["docker", "run", "--rm", "--platform", platform, tag, "python3", "-m", "pip", "freeze"],
        capture_output=True,
        text=True,
        check=True,
    )
    return pins(completed.stdout)


# The exit code, unchanged.


def test_the_runtime_fixture_passes_its_three_assertions(images, repository):
    """Code 0 does not tell three passes from two passes and a skip, so the count is read."""
    code, text = output(images, repository / "plugins" / "smoke" / "tests" / "test_runtime.py")
    assert code == 0
    assert "3 passed" in text


@pytest.mark.parametrize(
    ("target", "code"),
    [
        # `except*` does not parse on 3.10, so the file is a collection error, pytest's 2.
        ("tests/test_needs_311.py", 2),
        # pytest's own code for no test collected, not collapsed to 1.
        ("evals", 5),
    ],
)
def test_pytest_s_exit_code_reaches_the_caller_unchanged(
    images, repository, target: str, code: int
):
    assert output(images, repository / "plugins" / "smoke" / target)[0] == code


def test_an_absent_image_is_reported_and_raised_and_the_credential_never_is(
    images, repository, tmp_path
):
    """`check` reads the daemon and both image tags, so it belongs in this tier.

    There is no login in this path. The login directory below is empty, so the eval image's
    own check names the credential, and the test image's check still does not.
    """
    absent = PytestImage(
        Config(
            docker=DockerSection(claude_code_version="0.0.0-absent", login_dir=tmp_path / "login")
        )
    )
    assert Condition.CREDENTIAL in [line.condition for line in absent.docker.check()]
    unmet = absent.check()
    assert [line.condition for line in unmet] == [Condition.IMAGE]
    assert absent.docker.tag in unmet[0].message
    with pytest.raises(DockerError) as raised:
        absent.run(repository / "plugins" / "smoke" / "tests" / "test_passes.py")
    assert absent.docker.tag in str(raised.value)
    assert str(raised.value).endswith("is absent: run cowork_evals setup --docker")


# What the container is.


def test_the_test_image_adds_the_pinned_list_and_moves_nothing(images):
    """The assertion the whole mechanism rests on.

    A `pip install pytest` that moved `packaging` or any other inventory pin would leave
    the suite running against a runtime the CoWork image does not have.
    """
    base = freeze(images.docker.tag, images.platform)
    test = freeze(images.tag, images.platform)
    added = set(pins(REQUIREMENTS_TEST.read_text()))
    assert set(test) - set(base) == added
    assert set(base) - set(test) == set()
    assert {name: test[name] for name in base} == base


# What the container writes.


def test_what_the_container_writes_into_the_tree_is_the_developer_s(images, plugin):
    """The mount is read-write and the container runs as the host uid and gid.

    A bind mount on macOS maps ownership itself, so the uid assertion is load-bearing on
    Linux and free here. The working directory is the plugin root, so the caller's
    `--junitxml` report lands there, and pytest writes its cache as it does on a laptop.
    """
    (plugin / "tests" / "test_writes.py").write_text(
        "from pathlib import Path\n"
        "\n"
        "\n"
        "def test_it_writes_beside_itself():\n"
        "    Path(__file__).parent.joinpath('written.txt').write_text('written')\n"
    )
    assert images.run(plugin, pytest_args=("--junitxml=report.xml",)) == 0
    written = plugin / "tests" / "written.txt"
    assert written.read_text() == "written"
    assert written.stat().st_uid == os.getuid()
    assert (plugin / "report.xml").is_file()
    assert (plugin / ".pytest_cache").is_dir()
