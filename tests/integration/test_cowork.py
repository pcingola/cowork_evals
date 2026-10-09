"""The driver against the real thing: a real CoWork profile, and one real run.

Deselected by default. Run with `scripts/test.sh -m integration`. Nothing here is skipped:
an unconfigured profile, a missing profile directory and an empty profile are failures. See
../README.md.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

from cowork_evals import Config, CoWork, CoWorkError, CoWorkSection
from cowork_evals import cowork as driver_module
from cowork_evals.config import CONSENT_DIALOG

# A process that is on every macOS machine and is deterministically not CoWork. Activating
# it is how the guard is put in the state it exists to refuse.
NOT_COWORK = "Finder"

TAXONOMY = {2, 3, 4, 5, 6, 7, 8, 9}


def real_profile() -> CoWorkSection:
    """The configured profile. Fails when this machine has none, and never skips."""
    section = Config.load().cowork
    assert section.profile is not None, "cowork_evals.yaml names no profile"
    readable = section.profile_dir.is_dir()
    assert readable, "the configured profile directory does not exist"
    return section


@pytest.mark.integration
def test_the_reader_handles_every_session_in_a_real_profile(
    session_document_keys: set[str],
) -> None:
    """Nothing here prints a path, a prompt or an identifier. Public repository rule."""
    driver = CoWork(real_profile())
    found = driver.sessions()
    assert found, "the configured profile holds no sessions"

    for session in found:
        try:
            document = driver.collect(session)
        except CoWorkError as error:
            assert error.code in TAXONOMY
            continue
        assert set(document.model_dump()) == session_document_keys
        json.loads(document.model_dump_json())
        assert document.final_text
        assert document.tool_names == [call.name for call in document.tool_calls]


# The focus mechanism: the frontmost guard and the composer clear. docs/cowork_driver.md.
# Neither can be reached without the desktop, because both read and drive it.


@pytest.fixture
def activate(keyboard: None) -> Callable[[str], None]:
    """Bring one application forward and wait for the activation to land.

    A fixture and not a helper, so the one route to `osascript` here asks for the keyboard
    first. ../conftest.py.
    """

    def _activate(application: str) -> None:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'tell application "{application}" to activate',
                "-e",
                "delay 0.8",
            ],
            check=True,
        )

    return _activate


@pytest.mark.integration
def test_focus_frontmost_names_this_machines_frontmost_process(activate) -> None:
    """A missing Accessibility grant raises code 3 here and fails the test. It never skips."""
    activate(NOT_COWORK)
    name = driver_module.frontmost()
    assert name == NOT_COWORK
    assert name == name.strip()


@pytest.mark.integration
def test_focus_the_guard_refuses_with_code_9_when_cowork_is_not_frontmost(activate) -> None:
    """Nothing is typed. The guard runs before every keystroke the driver sends."""
    activate(NOT_COWORK)
    with pytest.raises(CoWorkError) as raised:
        CoWork(CoWorkSection())._guard()
    assert raised.value.code == 9
    assert NOT_COWORK in str(raised.value)
    assert driver_module.COWORK_PROCESS in str(raised.value)


@pytest.mark.integration
@pytest.mark.live
@pytest.mark.timeout(1800)
def test_focus_a_primed_composer_is_cleared_before_the_prompt(attended: Path, activate) -> None:
    """The composer contamination, reproduced and then not reproduced.

    The composer is primed by typing into it, which is what a developer working in another
    window did to it by accident. The clear runs before the deep link, so the audit prompt
    has to be the submitted prompt and nothing else.
    """
    real_profile()
    driver = CoWork.from_file(attended)

    activate(driver_module.COWORK_PROCESS)
    assert driver_module.frontmost() == driver_module.COWORK_PROCESS
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to keystroke "CONTAMINATION"',
        ],
        check=True,
    )

    marker = f"MARKER-{uuid.uuid4().hex[:12].upper()}"
    prompt = f"Reply with exactly: {marker}"
    document = driver.run(prompt)

    assert document.audit_prompt == prompt
    assert "CONTAMINATION" not in document.audit_prompt
    assert marker in document.final_text


# The only test that proves the application end of the contract: that the deep link
# prefills, that the synthetic Return submits, and that `completed` is written. It fires a
# real run, so it costs a VM boot, counts against the rate ceiling and leaves one permanent
# session in the signed-in account. It needs the macOS Accessibility grant, a signed-in
# CoWork and the desktop application already running. `live` selects it alone, so an
# integration run that must not spend is `-m "integration and not live"`.


@pytest.mark.integration
@pytest.mark.live
@pytest.mark.timeout(1800)
def test_a_live_run_returns_the_marker(attended: Path, session_document_keys: set[str]) -> None:
    """It also proves the driver asks for the keyboard rather than refusing.

    `attended` carries `consent: dialog` and this test calls `run` directly, with no caller
    above it to ask first, so the submission succeeding is the assertion. A dialog cannot be
    asserted without a person, and this is its effect.

    It asserts the flag is set afterwards and not that it was clear before: the
    `keyboard` fixture `attended` requests has already asked by then.
    """
    real_profile()
    driver = CoWork.from_file(attended)
    assert driver.config.consent == CONSENT_DIALOG
    marker = f"MARKER-{uuid.uuid4().hex[:12].upper()}"
    before = len(driver.sessions())
    before_log = len(driver.history())

    document = driver.run(f"Reply with exactly: {marker}")

    assert driver_module._CONSENTED is True, "the driver asked, and the ask set the flag"
    assert marker in document.final_text
    assert document.lifecycle[-1] == "completed"
    assert set(document.model_dump()) == session_document_keys
    json.dumps(document)

    assert len(driver.sessions()) == before + 1
    assert Path(document.session_dir) in driver.sessions()

    entries = driver.history()
    assert len(entries) == before_log + 1
    assert entries[-1].outcome == "submitted"
    assert entries[-1].session_dir == document.session_dir

    written = Path(document.log_file).read_text(encoding="utf-8")
    assert "firing the deep link:" in written
    assert "discovered the session:" in written
    assert "the completion signal fired: lifecycle state completed" in written
