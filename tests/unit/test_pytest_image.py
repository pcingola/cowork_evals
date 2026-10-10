"""The test image's digest and its argument lists. docs/cowork_test.md.

Nothing here reaches a daemon. Every test builds a `PytestImage` and reads a digest, a tag
or an argument list, and none of them runs a subprocess. `build`, `run`,
`image_is_present` and `check` all shell out to the `docker` CLI, so all four are covered
in tests/integration/test_pytest_image.py and none of them here.
"""

from __future__ import annotations

import os
import re

import pytest

from cowork_evals.config import Config, DockerSection
from cowork_evals.docker import CONTAINER_EXTRA_CA, DATA
from cowork_evals.docker.pytest_image import (
    DOCKERFILE,
    REQUIREMENTS_TEST,
    PytestImage,
    digest_of,
)


def image(**values) -> PytestImage:
    """A test image over one written `docker:` section. There is no other route in."""
    return PytestImage(Config(docker=DockerSection(**values)))


# The digest, and the tag over it.


def test_the_tag_names_a_twelve_hex_digest_in_its_own_repository():
    configured = image()
    assert configured.tag == f"cowork-evals-test:{configured.digest}"
    assert re.fullmatch(r"cowork-evals-test:[0-9a-f]{12}", configured.tag)


@pytest.mark.parametrize(
    "other",
    [
        # The base digest is hashed first, so a rebuilt base is a different test tag.
        {"claude_code_version": "2.1.260"},
        {"platform": "linux/amd64"},
    ],
)
def test_a_changed_input_is_a_different_test_tag(other: dict):
    base = {"platform": "linux/arm64", "claude_code_version": "2.1.259"}
    assert image(**base).digest != image(**{**base, **other}).digest


@pytest.mark.parametrize("position", range(4))
def test_the_digest_hashes_the_base_the_dockerfile_the_pinned_list_and_the_platform(
    position: int,
):
    """The two inputs that are files on disk are unreachable through a `docker:` section."""
    configured = image()
    four = [
        configured.docker.digest.encode(),
        DOCKERFILE.read_bytes(),
        REQUIREMENTS_TEST.read_bytes(),
        configured.platform.encode(),
    ]
    assert configured.digest == digest_of(*four)
    four[position] = b"edited"
    assert configured.digest != digest_of(*four)


# The build argument list.


@pytest.mark.parametrize("no_cache", [False, True])
def test_build_argv_is_the_documented_list(no_cache: bool):
    configured = image()
    assert configured.build_argv(no_cache=no_cache) == [
        "docker",
        "build",
        "--platform",
        "linux/arm64",
        "-f",
        str(DOCKERFILE),
        "--build-arg",
        f"BASE_TAG={configured.docker.tag}",
        "-t",
        configured.tag,
        *(["--no-cache"] if no_cache else []),
        str(DATA),
    ]


def test_the_dockerfile_takes_its_base_from_the_build_argument():
    """A literal base tag here is an image built against a base nothing resolved."""
    text = DOCKERFILE.read_text()
    assert "ARG BASE_TAG" in text
    assert "FROM ${BASE_TAG}" in text
    assert "FROM cowork-evals" not in text


# The run argument list.


def test_run_argv_is_the_documented_list(plugin):
    """The plugin root read-write and the working directory, and nothing else: no credential,
    no sandbox option, no `PYTHONPATH`, no enablement variable and no pytest option."""
    configured = image()
    assert configured.run_argv(plugin) == [
        "docker",
        "run",
        "--rm",
        "--platform",
        "linux/arm64",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        "HOME=/tmp/eval-home",
        "-v",
        f"{plugin.resolve()}:/work/plugin:rw",
        "-w",
        "/work/plugin",
        configured.tag,
        "python3",
        "-m",
        "pytest",
        "/work/plugin",
    ]


@pytest.mark.parametrize(
    ("relative", "tail", "expected"),
    [
        ("", (), ["/work/plugin"]),
        ("tests", (), ["/work/plugin/tests"]),
        (
            "tests",
            ("-k", "runtime", "--junitxml=r.xml"),
            ["/work/plugin/tests", "-k", "runtime", "--junitxml=r.xml"],
        ),
    ],
)
def test_the_target_is_relative_to_the_plugin_root_and_the_tail_is_verbatim_and_last(
    plugin, relative: str, tail: tuple[str, ...], expected: list[str]
):
    configured = image()
    argv = configured.run_argv(plugin / relative, pytest_args=tail)
    assert argv[argv.index(configured.tag) + 1 :] == ["python3", "-m", "pytest", *expected]


def test_run_argv_carries_the_extra_ca_environment_when_one_is_configured(plugin, tmp_path):
    ca = tmp_path / "root_ca.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\n")
    assert f"NODE_EXTRA_CA_CERTS={CONTAINER_EXTRA_CA}" in image(extra_ca_file=ca).run_argv(plugin)
