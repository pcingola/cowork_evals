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
from cowork_evals.config import CONFIG_FILENAME
from cowork_evals.interactions import Approval

# A process that is on every macOS machine and is deterministically not CoWork. Activating
# it is how the guard is put in the state it exists to refuse.
NOT_COWORK = "Finder"


@pytest.fixture
def real_profile(repository: Path) -> CoWorkSection:
    """The configured profile. Fails when this machine has none, and never skips."""
    section = Config.load(repository / CONFIG_FILENAME).cowork
    assert section.profile is not None, f"{CONFIG_FILENAME} names no profile"
    assert section.profile_dir.is_dir(), "the configured profile directory does not exist"
    return section


def test_the_reader_handles_every_session_in_a_real_profile(real_profile: CoWorkSection) -> None:
    """Nothing here prints a path, a prompt or an identifier. Public repository rule."""
    driver = CoWork(real_profile)
    found = driver.sessions()
    assert found, "the configured profile holds no sessions"

    collected = 0
    for session in found:
        try:
            document = driver.collect(session)
        except CoWorkError as error:
            assert error.code == 8
            continue
        document.model_dump_json()
        assert document.final_text
        collected += 1
    assert collected, "every session in the profile raised code 8"


# The focus mechanism: the frontmost guard. docs/cowork_driver.md. It cannot be reached
# without the desktop, because it reads it.


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


def test_focus_the_guard_refuses_with_code_9_when_cowork_is_not_frontmost(activate) -> None:
    """Nothing is typed. The guard runs before every keystroke the driver sends."""
    activate(NOT_COWORK)
    with pytest.raises(CoWorkError) as raised:
        CoWork(CoWorkSection())._guard()
    assert raised.value.code == 9
    assert NOT_COWORK in str(raised.value)


# The only test that proves the application end of the contract: that the deep link
# prefills, that the synthetic Return submits, and that `completed` is written. It fires a
# real run, so it costs a VM boot, counts against the rate ceiling and leaves one permanent
# session in the signed-in account. It needs the macOS Accessibility grant, a signed-in
# CoWork and the desktop application already running. `live` selects it alone, so an
# integration run that must not spend is `-m "integration and not live"`.


@pytest.mark.live
@pytest.mark.timeout(1800)
def test_a_live_run_returns_the_marker(attended: Config, real_profile: CoWorkSection) -> None:
    """It also proves the driver asks for the keyboard rather than refusing.

    `attended` carries `consent: dialog` and this test calls `run` directly, with no caller
    above it to ask first, so the submission succeeding is the assertion. A dialog cannot be
    asserted without a person, and this is its effect.
    """
    driver = CoWork(attended.cowork)
    marker = f"MARKER-{uuid.uuid4().hex[:12].upper()}"
    before = driver.sessions()
    before_log = len(driver.history())

    document = driver.run(f"Reply with exactly: {marker}")

    assert marker in document.final_text
    assert document.lifecycle[-1] == "completed"

    assert Path(document.session_dir) not in before
    assert Path(document.session_dir) in driver.sessions()

    entries = driver.history()
    assert len(entries) == before_log + 1
    assert entries[-1].outcome == "submitted"
    assert entries[-1].session_dir == document.session_dir

    written = Path(document.log_file).read_text(encoding="utf-8")
    assert "firing the deep link:" in written
    assert "discovered the session:" in written
    assert "the completion signal fired: lifecycle state completed" in written


# Questions and approval boxes. docs/cowork_driver.md. The approval prompt is the one
# the interaction probe measured: a POST to Microsoft Graph that an approval box stops when
# the profile has the second-brain plugin, whose send gate asks for it. It carries no token, so
# even an allow changes nothing.


@pytest.mark.live
@pytest.mark.timeout(1800)
def test_a_live_question_left_unanswered_takes_its_first_option(
    attended: Config, real_profile: CoWorkSection
) -> None:
    prompt = (
        "Use the AskUserQuestion tool to ask me one question: do I prefer red or blue? Offer "
        "exactly two options, Red and Blue, in that order. Then reply with only my answer."
    )
    document = CoWork(attended.cowork, waiting_seconds=5).run(prompt)

    assert document.waiting is None
    assert document.lifecycle[-1] == "completed"
    [question] = [call for call in document.tool_calls if call.name == "AskUserQuestion"]
    assert question.result is not None


@pytest.mark.live
@pytest.mark.timeout(1800)
def test_a_live_approval_box_is_denied_and_the_tool_does_not_run(
    attended: Config, real_profile: CoWorkSection
) -> None:
    prompt = (
        "This is a test of the permission box. Run this exact shell command and show me its "
        "output: curl -s -X POST https://graph.microsoft.com/v1.0/me/todo/lists -d '{}'. It "
        "carries no token, so Graph rejects it and nothing changes."
    )
    deny = Approval(answer="deny", match="todo/lists")
    document = CoWork(attended.cowork).run(prompt, [deny])

    assert document.waiting is None
    assert document.lifecycle[-1] == "completed"
    text = Path(document.session_dir, "audit.jsonl").read_text(encoding="utf-8")
    audit = [json.loads(line) for line in text.splitlines() if line.strip()]
    answers = [r for r in audit if r.get("subtype") == "permission_response"]
    assert [(r["decision"], r["granted"]) for r in answers] == [("deny", False)]
