"""The judge, without starting a process.

The reply documents under tests/data/judge/ are what `claude -p --output-format json`
prints, written by hand. The one test that runs the real command is
tests/integration/test_judge.py. See ../README.md.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from cowork_evals.cases import BaselineGraderConfig, FileTarget, Grader, LlmGraderConfig
from cowork_evals.config import CONFIG_FILENAME, Config, EvalSection
from cowork_evals.cowork import SessionDocument
from cowork_evals.judge import (
    Material,
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
)

JUDGE = Path(__file__).resolve().parent.parent / "data" / "judge"
CASE = JUDGE / "case"

GraderFactory = Callable[..., Grader]


def recorded(name: str) -> str:
    return (JUDGE / f"{name}.json").read_text(encoding="utf-8")


# The command line.

JUDGE_ARGV = [
    "claude",
    "-p",
    "--output-format",
    "json",
    "--model",
    "haiku",
    "--strict-mcp-config",
    "--json-schema",
    '{"type": "object", "properties": {"reasoning": {"type": "string"}, '
    '"verdict": {"type": "string", "enum": ["PASS", "FAIL"]}}, '
    '"required": ["reasoning", "verdict"], "additionalProperties": false}',
]


def test_judge_argv_is_claude_p_with_the_model_strict_mcp_config_and_the_schema() -> None:
    assert judge_argv("haiku") == JUDGE_ARGV


@pytest.mark.parametrize(
    ("outside", "add_dirs"),
    [((), []), (("/a", "/b"), ["--add-dir", "/a", "--add-dir", "/b"])],
)
def test_the_check_judge_argv_adds_the_grant_and_one_add_dir_per_path_outside(
    outside: tuple[str, ...], add_dirs: list[str]
) -> None:
    assert check_argv("haiku", outside) == [
        *JUDGE_ARGV,
        "--allowedTools",
        "Read,Glob,Grep",
        *add_dirs,
    ]


def test_the_check_judge_is_shown_the_paths_after_the_prompt() -> None:
    text = compose_paths("Every slide carries a title.", ("scratch/deck.png", "/x.pdf"))
    lines = text.split("\n")
    assert lines[0] == "Every slide carries a title."
    assert lines.index("scratch/deck.png") + 1 == lines.index("/x.pdf")


def test_the_caller_beats_the_configured_judge_model(working_directory, tmp_path: Path) -> None:
    Config(eval=EvalSection(judge_model="sonnet")).dump(tmp_path / CONFIG_FILENAME)
    with working_directory(tmp_path):
        assert resolve_model() == "sonnet"
        assert resolve_model("opus") == "opus"


# The composed text.


@pytest.mark.parametrize(
    ("config", "rubric"),
    [(LlmGraderConfig(), "the body"), (LlmGraderConfig(criteria="the key"), "the key")],
)
def test_the_criteria_is_the_key_where_one_is_written_and_the_body_otherwise(
    grader: GraderFactory, config: LlmGraderConfig, rubric: str
) -> None:
    assert criteria(grader("llm", config, markdown="the body")) == rubric


def test_the_composed_text_is_the_rubric_then_the_material_truncated_head_and_tail() -> None:
    long = "h" + "m" * 100_008 + "t"
    text = compose("The reply is warm.", long)
    assert text.startswith("The reply is warm.\n")
    assert "\nh" + "m" * 49_000 in text
    assert "m" * 49_000 + "t\n" in text
    assert "m" * 100_000 not in text
    assert "\n...\n" in text


@pytest.mark.parametrize(
    ("config", "shown"),
    [
        (LlmGraderConfig(focus="files", target="last_message"), "figures/chart.svg\nreport.md"),
        (LlmGraderConfig(), "Hello Alex. The report is in report.md."),
    ],
)
def test_an_llm_grader_reads_focus_and_ignores_target(
    answered: SessionDocument, grader: GraderFactory, config: LlmGraderConfig, shown: str
) -> None:
    assert material(grader("llm", config), answered, CASE) == Material(text=shown)


@pytest.mark.parametrize(
    ("path", "shown"),
    [
        ("notes.md", Material(text="A plain note.\n")),
        (
            "slide.png",
            Material(
                skip_reason="slide.png is an image, and the harness shows the judge the image "
                "itself, which one text call cannot"
            ),
        ),
        (
            "deck.pptx",
            Material(error="deck.pptx is not UTF-8 text: render it to an image, or write UTF-8"),
        ),
    ],
)
def test_a_produced_file_is_text_an_image_skip_or_a_failed_grader(
    produced: SessionDocument, grader: GraderFactory, path: str, shown: Material
) -> None:
    config = LlmGraderConfig(focus=FileTarget(source="file", path=path))
    assert material(grader("llm", config), produced, CASE) == shown


def test_a_baseline_grader_shows_both_trajectories(
    answered: SessionDocument, grader: GraderFactory
) -> None:
    shown = material(
        grader("baseline", BaselineGraderConfig(baseline_file="gold/trace.jsonl")), answered, CASE
    )
    assert shown.error is None
    assert "BASELINE TRAJECTORY:" in shown.text
    assert "The report names one option." in shown.text
    assert "NEW TRAJECTORY:" in shown.text
    assert '"Hello Alex. The report is in report.md."' in shown.text


@pytest.mark.parametrize(
    ("baseline_file", "error"),
    [
        ("../reply_pass.json", "../reply_pass.json resolves outside the case directory"),
        ("gold/absent.jsonl", "gold/absent.jsonl is unreadable: "),
    ],
)
def test_a_baseline_file_outside_the_case_or_absent_is_a_failed_grader(
    answered: SessionDocument, grader: GraderFactory, baseline_file: str, error: str
) -> None:
    config = BaselineGraderConfig(baseline_file=baseline_file)
    shown = material(grader("baseline", config), answered, CASE)
    assert (shown.error or "").startswith(error)


# Counting votes.


@pytest.mark.parametrize(
    ("stdout", "reply"),
    [
        (recorded("reply_pass"), Reply(vote=True, cost_usd=0.0021)),
        (recorded("reply_fail"), Reply(vote=False, cost_usd=0.0021)),
        (
            recorded("reply_neither"),
            Reply(
                cost_usd=0.0021,
                error="the judge answered neither word: 'I would rate this a 7 out of 10.'",
            ),
        ),
        (
            recorded("reply_no_result"),
            Reply(cost_usd=0.0004, error="the judge document carries no result"),
        ),
        ("`plugin eval` is in early access\n", Reply(error="the judge printed no JSON document")),
        (
            recorded("reply_reasoned_unsure"),
            Reply(
                cost_usd=0.0021,
                error="the judge's verdict was neither word: 'UNSURE'",
                reasoning="the trace is ambiguous",
            ),
        ),
    ],
)
def test_a_reply_is_a_vote_or_a_lost_vote_and_always_a_spend(stdout: str, reply: Reply) -> None:
    assert read_reply(stdout) == reply


@pytest.mark.parametrize(
    ("names", "passed", "explanation", "votes"),
    [
        (("reply_pass", "reply_fail", "reply_pass"), True, "PASS FAIL PASS", [True, False, True]),
        (("reply_pass", "reply_fail", "reply_fail"), False, "PASS FAIL FAIL", [True, False, False]),
        (
            ("reply_pass", "reply_neither", "reply_neither"),
            False,
            "PASS LOST LOST",
            [True, False, False],
        ),
    ],
)
def test_the_majority_of_three_decides(
    grader: GraderFactory,
    names: tuple[str, ...],
    passed: bool,
    explanation: str,
    votes: list[bool],
) -> None:
    judged = tally(grader("llm"), [read_reply(recorded(name)) for name in names], "Hello.")
    assert judged.result.passed is passed
    assert judged.result.explanation == f"judge votes: {explanation}"
    assert judged.result.judge_votes == votes


def test_the_evidence_and_every_spend_reach_the_result(grader: GraderFactory) -> None:
    judged = tally(grader("llm"), [read_reply(recorded("reply_pass"))] * 3, "Hello Alex.")
    assert judged.result.evidence == "Hello Alex."
    assert judged.cost_usd == pytest.approx(0.0063)


def test_three_lost_votes_are_a_failed_grader_naming_the_reason(
    grader: GraderFactory,
) -> None:
    judged = tally(grader("llm"), [Reply(error="claude exited 1")] * 3, "Hello.")
    assert judged.result.passed is False
    assert judged.result.judge_votes is None
    assert judged.result.explanation == "the judge could not be asked: claude exited 1"


def test_the_evidence_is_capped_at_2000_characters(grader: GraderFactory) -> None:
    long = "h" * 1000 + "m" * 3000 + "t" * 1000
    judged = tally(grader("llm"), [read_reply(recorded("reply_pass"))] * 3, long)
    evidence = judged.result.evidence or ""
    assert len(evidence) == 2000
    assert evidence.startswith("h" * 997)
    assert evidence.endswith("t" * 998)
    assert "\n...\n" in evidence


def test_the_winning_side_s_reason_reaches_the_explanation(grader: GraderFactory) -> None:
    names = ("reply_reasoned_pass", "reply_reasoned_fail", "reply_reasoned_pass")
    judged = tally(grader("llm"), [read_reply(recorded(name)) for name in names], "Hello.")
    assert judged.result.passed is True
    assert "the command ran" in judged.result.explanation
    assert "a script wrote it" not in judged.result.explanation
