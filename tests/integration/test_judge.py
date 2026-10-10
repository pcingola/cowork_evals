"""The judge against the real `claude -p`. Twelve short calls, no CoWork session.

It proves what a recorded reply document cannot: that the composed text reaches the model
on stdin, and that the reply parses. The check judge is proven the same way, over a real PNG
and a real PDF under ../data/judge/, because what it has to establish is that a judge granted
`Read`, `Glob` and `Grep` opens a binary the `llm` grader cannot be shown at all. Deselected
by default; `live` because it spends. It costs no ceiling entry, because nothing here submits
to CoWork. See ../README.md.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cowork_evals.cases import Grader, LlmGraderConfig
from cowork_evals.checks import build_run
from cowork_evals.cowork import SessionDocument
from cowork_evals.judge import LOST_WORD, grade, resolve_model

JUDGE = Path(__file__).resolve().parent.parent / "data" / "judge"

RUBRIC = "PASS if the material is exactly the word PONG. FAIL for anything else."


def rubric_grader() -> Grader:
    return Grader(
        name="is-pong",
        type="llm",
        weight=1,
        config=LlmGraderConfig(focus="last_message"),
        markdown=RUBRIC,
        path=Path("is-pong.md"),
    )


def answering(text: str) -> SessionDocument:
    """A session document whose one read field, for an `llm` grader on `last_message`, is `text`."""
    return SessionDocument(
        prompt=None,
        prompt_sha256=None,
        session_dir="",
        submitted_at=None,
        collected_at="",
        transcript=None,
        other_transcripts=[],
        subagent_transcripts=[],
        audit_prompt=None,
        lifecycle=[],
        turns=[],
        tool_calls=[],
        tool_names=[],
        final_text=text,
        outputs=[],
        log_file=None,
    )


@pytest.mark.live
@pytest.mark.timeout(600)
@pytest.mark.parametrize(
    ("text", "expected"), [("PONG", True), ("The kernel is 6.8.0-136-generic.", False)]
)
def test_the_judge_decides_a_string_against_the_rubric(
    tmp_path: Path, text: str, expected: bool
) -> None:
    """Every vote from the real `claude -p --json-schema` parsed, and the spend was read."""
    judged = grade(rubric_grader(), answering(text), tmp_path, model=resolve_model())
    assert judged.result.judge_votes is not None, judged.result.explanation
    assert LOST_WORD not in judged.result.explanation
    assert judged.result.passed is expected, judged.result.explanation
    assert judged.cost_usd > 0.0


# The check judge, over two binaries checked in under ../data/judge/, because the point is a
# file the `llm` grader refuses: a PNG is a grader skip there and a PDF is not UTF-8.


@pytest.mark.live
@pytest.mark.timeout(900)
def test_the_check_judge_reads_a_png_and_a_pdf(tmp_path: Path) -> None:
    directory = tmp_path / "traces" / "checked" / "run-1"
    (directory / "workspace").mkdir(parents=True)
    for name in ("square.png", "note.pdf"):
        shutil.copy(JUDGE / name, directory / "workspace" / name)

    run = build_run(directory, tmp_path, 1, resolve_model())
    passed = run.judge(
        "square.png is a solid red square, and note.pdf carries the word PONG.",
        run.file("square.png"),
        run.file("note.pdf"),
    )
    assert passed.passed is True, passed.explanation

    failed = run.judge(
        "square.png is a solid green square, and note.pdf carries the word PING.",
        run.file("square.png"),
        run.file("note.pdf"),
    )
    assert failed.passed is False, failed.explanation

    assert [len(call.replies) for call in run.calls] == [3, 3]
    assert all(not reply.startswith(LOST_WORD) for call in run.calls for reply in call.replies)
    assert all("workspace/square.png" in call.prompt for call in run.calls)
    assert all(call.cost_usd > 0.0 for call in run.calls)
