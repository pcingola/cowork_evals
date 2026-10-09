"""The judge, without starting a process.

The reply documents under tests/data/judge/ are what `claude -p --output-format json`
prints, written by hand. The one test that runs the real command is
tests/integration/test_judge.py. See ../README.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cowork_evals.cases import Grader
from cowork_evals.judge import (
    CHECK_INSTRUCTION,
    CHECK_TOOLS,
    EVIDENCE_LIMIT,
    FAIL_WORD,
    FILES_CLOSE,
    FILES_OPEN,
    INSTRUCTION,
    MATERIAL_CLOSE,
    MATERIAL_LIMIT,
    MATERIAL_OPEN,
    PASS_WORD,
    VERDICT_SCHEMA,
    Reply,
    check_argv,
    compose,
    compose_paths,
    criteria,
    judge_argv,
    material,
    read_reply,
    resolve_model,
    tally,
    truncate,
)

DATA = Path(__file__).resolve().parent.parent / "data"
JUDGE = DATA / "judge"
CASE = JUDGE / "case"


def document(name: str) -> dict[str, Any]:
    loaded = json.loads((DATA / "documents" / f"{name}.json").read_text(encoding="utf-8"))
    loaded["session_dir"] = str(DATA / "documents" / loaded["session_dir"])
    return loaded


def recorded(name: str) -> str:
    return (JUDGE / f"{name}.json").read_text(encoding="utf-8")


def grader(kind: str, markdown: str = "", name: str = "j", **config: Any) -> Grader:
    return Grader(
        name=name, type=kind, weight=1, config=config, markdown=markdown, path=CASE / f"{name}.md"
    )


@pytest.fixture
def answered() -> dict[str, Any]:
    return document("answered")


@pytest.fixture
def produced() -> dict[str, Any]:
    return document("produced")


# The command line.


def test_judge_argv_is_claude_p_with_the_model_and_strict_mcp_config() -> None:
    assert judge_argv("haiku") == [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--model",
        "haiku",
        "--strict-mcp-config",
        "--json-schema",
        json.dumps(VERDICT_SCHEMA),
    ]


def test_the_check_judge_argv_adds_the_grant_to_the_judge_argv() -> None:
    assert check_argv("haiku") == [*judge_argv("haiku"), "--allowedTools", "Read,Glob,Grep"]
    assert CHECK_TOOLS == ("Read", "Glob", "Grep")


def test_the_check_judge_argv_carries_one_add_dir_per_path_outside() -> None:
    assert check_argv("haiku", ("/a", "/b")) == [
        *judge_argv("haiku"),
        "--allowedTools",
        "Read,Glob,Grep",
        "--add-dir",
        "/a",
        "--add-dir",
        "/b",
    ]


def test_the_check_judge_argv_writes_no_turn_cap_and_no_permission_mode() -> None:
    """A cap is a restriction nobody asked for, and the grant alone lets the judge read."""
    argv = " ".join(check_argv("haiku", ("/a",)))
    assert "--max-turns" not in argv
    assert "--permission-mode" not in argv


def test_judge_argv_is_untouched_by_the_check_judge() -> None:
    assert "--allowedTools" not in judge_argv("haiku")
    assert "--add-dir" not in judge_argv("haiku")


def test_the_check_judge_is_shown_the_paths_and_never_the_material() -> None:
    assert compose_paths("Every slide carries a title.", ("scratch/deck.png", "/tmp/x.pdf")) == (
        "Every slide carries a title.\n\n"
        f"{FILES_OPEN}\nscratch/deck.png\n/tmp/x.pdf\n{FILES_CLOSE}\n\n{CHECK_INSTRUCTION}"
    )


def test_the_enablement_variable_is_not_exported() -> None:
    """It enables `claude plugin eval`, and this is `claude -p`."""
    import cowork_evals.judge as module

    assert not hasattr(module, "ENABLEMENT_ENV")
    assert "WALNUT" not in " ".join(judge_argv("haiku"))


def test_the_caller_beats_the_configured_judge_model(working_directory, tmp_path: Path) -> None:
    (tmp_path / "cowork_evals.yaml").write_text("eval:\n  judge_model: sonnet\n", encoding="utf-8")
    with working_directory(tmp_path):
        assert resolve_model() == "sonnet"
        assert resolve_model("opus") == "opus"


# The composed text.


def test_the_criteria_is_the_body_when_no_key_is_written() -> None:
    assert criteria(grader("llm", markdown="The reply is warm.")) == "The reply is warm."


def test_a_written_criteria_key_beats_the_body() -> None:
    written = grader("llm", markdown="the body", criteria="the key")
    assert criteria(written) == "the key"


def test_the_composed_text_is_the_rubric_the_material_and_the_instruction() -> None:
    assert compose("The reply is warm.", "Hello Alex.") == (
        f"The reply is warm.\n\n{MATERIAL_OPEN}\nHello Alex.\n{MATERIAL_CLOSE}\n\n{INSTRUCTION}"
    )


def test_the_material_is_truncated_head_and_tail() -> None:
    long = "a" * (MATERIAL_LIMIT + 10)
    kept = truncate(long, MATERIAL_LIMIT)
    assert len(kept) == MATERIAL_LIMIT + len("\n...\n")
    assert kept.startswith("aaa")
    assert kept.endswith("aaa")
    assert "\n...\n" in kept
    assert truncate("short", MATERIAL_LIMIT) == "short"


def test_an_llm_grader_reads_focus_and_ignores_target(answered: dict[str, Any]) -> None:
    shown = material(grader("llm", focus="files", target="last_message"), answered, CASE)
    assert shown.error is None
    assert shown.text == "figures/chart.svg\nreport.md"


def test_an_llm_grader_defaults_to_the_last_message(answered: dict[str, Any]) -> None:
    shown = material(grader("llm"), answered, CASE)
    assert shown.text == "Hello Alex. The report is in report.md."


def test_an_llm_grader_reads_a_produced_file(produced: dict[str, Any]) -> None:
    focus = {"source": "file", "path": "notes.md"}
    assert material(grader("llm", focus=focus), produced, CASE).text == "A plain note.\n"


def test_a_baseline_grader_shows_both_trajectories(answered: dict[str, Any]) -> None:
    shown = material(grader("baseline", baseline_file="gold/trace.jsonl"), answered, CASE)
    assert shown.error is None
    assert "BASELINE TRAJECTORY:" in shown.text
    assert "The report names one option." in shown.text
    assert "NEW TRAJECTORY:" in shown.text
    assert '"Hello Alex. The report is in report.md."' in shown.text


def test_a_baseline_file_outside_the_case_directory_is_refused(answered: dict[str, Any]) -> None:
    shown = material(grader("baseline", baseline_file="../reply_pass.json"), answered, CASE)
    assert shown.error == "../reply_pass.json resolves outside the case directory"


def test_an_absent_baseline_file_is_a_failed_grader(answered: dict[str, Any]) -> None:
    shown = material(grader("baseline", baseline_file="gold/absent.jsonl"), answered, CASE)
    assert shown.error is not None
    assert "absent.jsonl" in shown.error


# What the judge cannot be shown.


def test_an_image_focus_is_a_grader_skip_and_not_a_failure(produced: dict[str, Any]) -> None:
    focus = {"source": "file", "path": "slide.png"}
    shown = material(grader("llm", focus=focus), produced, CASE)
    assert shown.error is None
    assert shown.skip_reason is not None
    assert "slide.png is an image" in shown.skip_reason


def test_another_binary_focus_is_a_failed_grader(produced: dict[str, Any]) -> None:
    focus = {"source": "file", "path": "deck.pptx"}
    shown = material(grader("llm", focus=focus), produced, CASE)
    assert shown.skip_reason is None
    assert shown.error == ("deck.pptx is not UTF-8 text: render it to an image, or write UTF-8")


# Counting votes.


def test_a_pass_reply_is_a_vote_and_a_spend() -> None:
    reply = read_reply(recorded("reply_pass"))
    assert reply.vote is True
    assert reply.cost_usd == 0.0021
    assert reply.error is None


def test_a_fail_reply_is_the_other_vote() -> None:
    assert read_reply(recorded("reply_fail")).vote is False


def test_a_reply_that_is_neither_word_is_a_lost_vote() -> None:
    reply = read_reply(recorded("reply_neither"))
    assert reply.vote is None
    assert reply.error is not None
    assert reply.cost_usd == 0.0021, "a lost vote still cost what it cost"


def test_a_document_with_no_result_is_a_lost_vote() -> None:
    assert read_reply(recorded("reply_no_result")).vote is None


def test_output_that_is_not_json_is_a_lost_vote() -> None:
    reply = read_reply("`plugin eval` is currently in early access\n")
    assert reply.vote is None
    assert reply.cost_usd == 0.0


def test_two_of_three_passes() -> None:
    judged = tally(
        grader("llm"),
        [read_reply(recorded(name)) for name in ("reply_pass", "reply_fail", "reply_pass")],
        "Hello Alex.",
    )
    assert judged.result.passed is True
    assert judged.result.explanation == "judge votes: PASS FAIL PASS"
    assert judged.result.judge_votes == (True, False, True)
    assert judged.result.evidence == "Hello Alex."
    assert judged.cost_usd == pytest.approx(0.0063)


def test_one_of_three_fails() -> None:
    judged = tally(
        grader("llm"),
        [read_reply(recorded(name)) for name in ("reply_pass", "reply_fail", "reply_fail")],
        "Hello.",
    )
    assert judged.result.passed is False
    assert judged.result.explanation == "judge votes: PASS FAIL FAIL"


def test_a_lost_vote_is_not_a_pass() -> None:
    judged = tally(
        grader("llm"),
        [read_reply(recorded(name)) for name in ("reply_pass", "reply_neither", "reply_neither")],
        "Hello.",
    )
    assert judged.result.passed is False
    assert judged.result.explanation == "judge votes: PASS LOST LOST"
    assert judged.result.judge_votes == (True, False, False)


def test_three_lost_votes_are_a_failed_grader_naming_the_reason() -> None:
    judged = tally(grader("llm"), [Reply(error="claude exited 1")] * 3, "Hello.")
    assert judged.result.passed is False
    assert judged.result.judge_votes is None
    assert judged.result.explanation == "the judge could not be asked: claude exited 1"


def test_the_evidence_is_truncated() -> None:
    judged = tally(grader("llm"), [read_reply(recorded("reply_pass"))] * 3, "x" * 5000)
    assert judged.result.evidence is not None
    assert len(judged.result.evidence) == EVIDENCE_LIMIT + len("\n...\n")


# A judge that reasons and still votes. docs/checks.md.


def reasoned(verdict: str, reasoning: str) -> str:
    """One `claude -p --output-format json` document, as `--json-schema` makes the CLI print it."""
    answer = {"verdict": verdict, "reasoning": reasoning}
    return json.dumps(
        {"result": json.dumps(answer), "structured_output": answer, "total_cost_usd": 0.0021}
    )


def test_a_reasoned_reply_votes_and_its_reason_reaches_the_grader() -> None:
    """Under the old rule a reply longer than one word was a lost vote, so this grader failed."""
    replies = [read_reply(reasoned(PASS_WORD, "xlsx.sh dedup ran")) for _ in range(3)]
    judged = tally(grader("llm"), replies, "Hello.")
    assert judged.result.passed is True
    assert judged.result.judge_votes == (True, True, True)
    assert "xlsx.sh dedup ran" in judged.result.explanation
    assert judged.cost_usd == pytest.approx(0.0063)


def test_the_majority_decides_and_carries_the_winning_side_s_reason() -> None:
    replies = [
        read_reply(reasoned(PASS_WORD, "the command ran")),
        read_reply(reasoned(FAIL_WORD, "a script wrote it")),
        read_reply(reasoned(PASS_WORD, "the command is in the trace")),
    ]
    judged = tally(grader("llm"), replies, "Hello.")
    assert judged.result.passed is True
    assert "the command ran" in judged.result.explanation
    assert "a script wrote it" not in judged.result.explanation


def test_a_verdict_outside_the_schema_is_a_lost_vote() -> None:
    replies = [read_reply(reasoned("UNSURE", "the trace is ambiguous")) for _ in range(3)]
    judged = tally(grader("llm"), replies, "Hello.")
    assert judged.result.passed is False
    assert judged.result.judge_votes is None
    assert "UNSURE" in judged.result.explanation


def test_a_bare_word_reply_still_votes() -> None:
    """What a CLI too old for `--json-schema` leaves. It votes, and explains nothing."""
    judged = tally(grader("llm"), [read_reply(recorded("reply_pass"))] * 3, "Hello.")
    assert judged.result.passed is True
    assert judged.result.explanation == "judge votes: PASS PASS PASS"
