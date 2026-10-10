"""The CoWork backend against the real thing: one provoking run, and one real suite.

Preconditions, all of which fail the test rather than skipping it: a signed-in CoWork, the
desktop application running, the macOS Accessibility grant, `cowork_evals.yaml` naming the
active profile, and `claude` on `PATH`. See ../README.md.

Nothing here asserts over the case reader or over what makes a case unrunnable. Neither needs
a profile or a session, so both are unit tests in tests/unit/test_cowork_backend.py.

Nothing here prints a path, a prompt or an identifier. Public repository rule.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cowork_evals import Config, CoWork, traces
from cowork_evals.cowork import TRANSCRIPTS
from cowork_evals.cowork_backend import run
from cowork_evals.harness import RESULT_NAME
from cowork_evals.results import UNKNOWN_VERSION, CaseAggregates, ResultDocument

SMOKE = Path(__file__).resolve().parent.parent.parent / "plugins" / "smoke"

# The prompt that provokes both measurements at once: a skill has to fire, and a named file
# has to be written where the host can read it.
PROVOKE = (
    "Use any skill you have available, then write a file named measurement.txt "
    "containing the word MEASURED. Reply with the name of the skill you used."
)


@pytest.mark.live
@pytest.mark.timeout(1800)
def test_one_run_fires_a_skill_and_writes_under_outputs(attended: Config) -> None:
    """The two facts docs/cowork_backend.md "What one suite costs" records as measured."""
    document = CoWork(attended.cowork).run(PROVOKE)
    assert document.final_text, "the provoking run produced no assistant text"
    assert any(call.name == "Skill" for call in document.tool_calls)
    assert any(entry.startswith("outputs/") for entry in document.outputs)


@pytest.mark.live
@pytest.mark.timeout(1800)
def test_the_smoke_suite_runs_and_the_case_passes(attended: Config, tmp_path: Path) -> None:
    """One VM boot, one ceiling entry, one permanent session."""
    output = tmp_path / "smoke"
    output.mkdir()
    # One case by name, so this test still costs one VM boot and one ceiling entry.
    written = run(SMOKE, output, config=attended, case_glob="python-version")
    assert written == output / RESULT_NAME

    document = ResultDocument.read(written)
    assert document.schema_version == 1
    assert document.partial is False
    assert document.claude_version != UNKNOWN_VERSION
    assert document.aggregates.cases_total == 1

    case = document.cases[0]
    assert case.name == "python-version"
    assert case.skipped is False, case.skip_reason
    assert len(case.arms.with_) == 1

    entry = case.arms.with_[0]
    assert entry.error is None
    assert entry.passed is True, [grader.explanation for grader in entry.graders]
    assert case.aggregates == CaseAggregates(score=1.0, pass_rate=1.0)

    # The same run, collected the way the command collects it. A real session transcript and
    # a real `outputs/` cannot be reached without one.
    assert entry.cowork is not None
    session = Path(entry.cowork.session_dir)
    assert traces.collect(output) == []

    kept = traces.run_dir(output, "python-version", 1)
    assert (kept / traces.TRACE_NAME).is_file(), f"no trace under {kept}"
    assert "3.10.12" in (kept / traces.LAST_MESSAGE_NAME).read_text(encoding="utf-8")

    # The document points at the copy, and still names the session it came from.
    collected = ResultDocument.read(written).cases[0].arms.with_[0]
    assert Path(collected.trace_path) == kept / traces.TRACE_NAME
    assert collected.cowork.session_dir == str(session)

    # Copied, never moved: the profile is the account's own record.
    assert session.is_dir()
    assert (session / "audit.jsonl").is_file()
    assert list((session / TRANSCRIPTS).glob("*.jsonl")), "the transcript left the session"
