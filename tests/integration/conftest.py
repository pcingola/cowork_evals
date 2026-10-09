"""Every test under tests/integration/ is integration, whether or not it says so.

The marker is applied here so it cannot be forgotten on a new file. Selection stays
`-m integration`, which is what pyproject.toml deselects by default.

pytest_collection_modifyitems in a subdirectory conftest still receives every collected
item, so the hook filters by path.

It also asks for the keyboard once per run that takes it, holds the one configuration every
CoWork test that fires reads, and asserts the two images once. See ../README.md.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from cowork_evals import cowork as driver_module
from cowork_evals.config import CONFIG_FILENAME, CONSENT_DIALOG, Config, CoWorkSection
from cowork_evals.docker import Condition, remedy
from cowork_evals.docker.pytest_image import BUILD_REMEDY, PytestImage

HERE = Path(__file__).parent


def pytest_collection_modifyitems(items) -> None:
    for item in items:
        if HERE in Path(str(item.path)).parents:
            item.add_marker("integration")


@pytest.fixture(scope="session")
def keyboard(repository: Path) -> None:
    """Ask for the keyboard once, before the first test that takes it.

    See ../README.md, "The live marker".
    """
    source = repository / CONFIG_FILENAME
    section = Config.load(source).cowork if source.is_file() else CoWorkSection()
    driver_module.consent(dataclasses.replace(section, consent=CONSENT_DIALOG))


@pytest.fixture
def attended(keyboard: None, repository: Path) -> Config:
    """This machine's configuration with `cowork.consent` set to `dialog`.

    See ../README.md, "The live marker".
    """
    source = repository / CONFIG_FILENAME
    assert source.is_file(), f"{CONFIG_FILENAME} is not in the repository root"
    config = Config.load(source)
    assert config.cowork.profile, f"{CONFIG_FILENAME} names no profile"
    return dataclasses.replace(
        config, cowork=dataclasses.replace(config.cowork, consent=CONSENT_DIALOG)
    )


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
