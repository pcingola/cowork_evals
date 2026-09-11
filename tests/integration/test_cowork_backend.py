"""The CoWork backend against the real thing: a real profile, and one real suite.

Preconditions, all of which fail the test rather than skipping it: a signed-in CoWork, the
desktop application running, the macOS Accessibility grant, `cowork_evals.yaml` naming the
active profile, and `claude` on `PATH`. See ../README.md.

Nothing here asserts over the case reader or the skip rule. Neither needs a profile or a
session, so both are unit tests in tests/unit/test_cowork_backend.py.

Nothing here prints a path, a prompt or an identifier. Public repository rule.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from cowork_evals import Config, CoWork, CoWorkError, CoWorkSection, traces
from cowork_evals.cowork import TRANSCRIPTS
from cowork_evals.cowork_backend import run
from cowork_evals.harness import RESULT_NAME

SMOKE = Path(__file__).resolve().parent.parent.parent / "plugins" / "smoke"

# The prompt that provokes both measurements at once when the profile shows neither: a
# skill has to fire, and a named file has to be written where the host can read it.
PROVOKE = (
    "Use any skill you have available, then write a file named measurement.txt "
    "containing the word MEASURED. Reply with the name of the skill you used."
)

# What a fired skill looks like in a transcript, and where a produced file lands.
SKILL_TOOL = "Skill"
OUTPUTS_PREFIX = "outputs/"

# The driver codes the walk steps over. A session with no assistant text raises code 8.
TAXONOMY = {2, 3, 4, 5, 6, 7, 8}


@dataclass(frozen=True, slots=True)
class Facts:
    """The two facts about the grader mapping that cannot be read from a file."""

    skill_tool_use: bool = False
    outputs_written: bool = False

    def with_session(self, document: dict[str, Any]) -> Facts:
        return Facts(
            skill_tool_use=self.skill_tool_use or _fired_a_skill(document),
            outputs_written=self.outputs_written or _wrote_under_outputs(document),
        )

    @property
    def both(self) -> bool:
        return self.skill_tool_use and self.outputs_written


def _fired_a_skill(document: dict[str, Any]) -> bool:
    return any(call.get("name") == SKILL_TOOL for call in document["tool_calls"])


def _wrote_under_outputs(document: dict[str, Any]) -> bool:
    return any(entry.startswith(OUTPUTS_PREFIX) for entry in document["outputs"])


def real_profile() -> CoWorkSection:
    """The configured profile. Fails when this machine has none, and never skips."""
    section = Config.load().cowork
    assert section.profile is not None, "cowork_evals.yaml names no profile"
    assert section.profile_dir.is_dir(), "the configured profile directory does not exist"
    return section


def walk(driver: CoWork) -> Facts:
    """Every session already in the profile, through `collect`. It submits nothing.

    A session with no assistant text raises code 8, which is stepped over, as
    test_cowork.py's walk already does.
    """
    facts = Facts()
    for session in driver.sessions():
        try:
            document = driver.collect(session)
        except CoWorkError as error:
            assert error.code in TAXONOMY
            continue
        facts = facts.with_session(document)
    return facts


@pytest.mark.integration
def test_claude_is_reachable_for_the_judge_and_the_recorded_version() -> None:
    """`claudeVersion` and every judged grader need it. docs/cli.md makes it a preflight."""
    try:
        completed = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, check=False
        )
    except OSError as error:
        pytest.fail(f"claude is not on PATH: {error}")
    assert completed.returncode == 0, f"claude --version exited {completed.returncode}"
    assert completed.stdout.strip(), "claude --version printed nothing"


@pytest.mark.integration
def test_the_profile_is_walked_and_both_facts_are_measured() -> None:
    """The cheap half of the measurement: what the sessions already there show."""
    driver = CoWork(real_profile())
    assert driver.sessions(), "the configured profile holds no sessions"
    facts = walk(driver)
    print(f"\nmeasured from the profile: {facts}")
    assert isinstance(facts.skill_tool_use, bool)
    assert isinstance(facts.outputs_written, bool)


@pytest.mark.integration
@pytest.mark.live
@pytest.mark.timeout(1800)
def test_one_run_provokes_whichever_fact_the_profile_does_not_show() -> None:
    """One prompt that asks for both. A profile already showing both costs nothing here.

    The two facts are recorded in docs/cowork_backend.md. A false one is not a failure: it
    means that grader cannot be used on this backend, and that file drops the row.
    """
    driver = CoWork(real_profile())
    facts = walk(driver)
    if not facts.both:
        document = driver.run(PROVOKE)
        assert document["final_text"], "the provoking run produced no assistant text"
        facts = facts.with_session(document)
    print(f"\nmeasured after provoking: {facts}")
    assert isinstance(facts.both, bool)


@pytest.mark.integration
@pytest.mark.live
@pytest.mark.timeout(1800)
def test_the_smoke_suite_runs_and_the_case_passes(tmp_path: Path) -> None:
    """One VM boot, one ceiling entry, one permanent session."""
    output = tmp_path / "smoke"
    output.mkdir()
    written = run(SMOKE, output, config=Config.load())
    assert written == output / RESULT_NAME

    document = json.loads(written.read_text(encoding="utf-8"))
    assert document["schemaVersion"] == 1
    assert document["partial"] is False
    assert document["aggregates"]["casesTotal"] == 1

    case = document["cases"][0]
    assert case["name"] == "python-version"
    assert "skipped" not in case, case.get("skipReason")
    assert len(case["arms"]["with"]) == 1

    entry = case["arms"]["with"][0]
    print(
        f"\nsmoke case: durationSeconds={entry.get('durationSeconds')} "
        f"turns={entry['turns']} costUsd={document['costUsd']}"
    )
    assert entry["error"] is None
    assert entry["passed"] is True, [grader["explanation"] for grader in entry["graders"]]
    assert case["aggregates"] == {"score": 1.0, "passRate": 1.0}

    # The same run, collected the way the command collects it. A real session transcript and
    # a real `outputs/` cannot be reached without one.
    session = Path(entry["cowork"]["sessionDir"])
    assert traces.collect(output) == []

    kept = traces.run_dir(output, "python-version", 1)
    assert (kept / traces.TRACE_NAME).is_file(), f"no trace under {kept}"
    assert "3.10.12" in (kept / traces.LAST_MESSAGE_NAME).read_text(encoding="utf-8")

    # The document points at the copy, and still names the session it came from.
    written_again = json.loads(written.read_text(encoding="utf-8"))
    collected = written_again["cases"][0]["arms"]["with"][0]
    assert Path(collected["tracePath"]) == kept / traces.TRACE_NAME
    assert collected["cowork"]["sessionDir"] == str(session)

    # Copied, never moved: the profile is the account's own record.
    assert session.is_dir()
    assert (session / "audit.jsonl").is_file()
    assert list((session / TRANSCRIPTS).glob("*.jsonl")), "the transcript left the session"
