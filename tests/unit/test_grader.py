"""The four structural graders over hand-written session documents.

The documents are under tests/data/documents/, and the produced files they name are real
files beside them. Every expected value is a literal. Nothing here submits anything. The
semantics are docs/claude_code/plugin_eval_reference.md. See ../README.md.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from cowork_evals.cases import (
    FileExistsConfig,
    FileTarget,
    Grader,
    RegexConfig,
    ToolOrderConfig,
    ToolUsedConfig,
)
from cowork_evals.cowork import SessionDocument
from cowork_evals.grader import _full_match, created, grade, resolve_target

# The targets.


def test_the_outputs_prefix_is_stripped_once(answered: SessionDocument) -> None:
    assert answered.outputs == ["outputs/figures/chart.svg", "outputs/report.md"]
    assert created(answered) == ["figures/chart.svg", "report.md"]


def test_last_message_is_the_final_text(answered: SessionDocument) -> None:
    assert resolve_target(answered, None).text == "Hello Alex. The report is in report.md."
    assert resolve_target(answered, "last_message").text == resolve_target(answered, None).text


def test_trace_is_one_json_object_per_line(answered: SessionDocument) -> None:
    lines = resolve_target(answered, "trace").text.splitlines()
    assert len(lines) == 5, "two turns, then three tool calls"
    assert json.loads(lines[0]) == answered.turns[0].model_dump()
    assert json.loads(lines[2]) == answered.tool_calls[0].model_dump()


def test_files_is_the_stripped_list_newline_separated(answered: SessionDocument) -> None:
    assert resolve_target(answered, "files").text == "figures/chart.svg\nreport.md"


def test_a_file_target_reads_under_outputs(answered: SessionDocument) -> None:
    target = resolve_target(answered, FileTarget(source="file", path="report.md"))
    assert target.error is None
    assert target.text == "# Report\n\n- One bullet about the migration.\n"


def test_an_unreadable_file_is_a_reason_and_never_a_raise(answered: SessionDocument) -> None:
    target = resolve_target(answered, FileTarget(source="file", path="absent.md"))
    assert target.error is not None
    assert "absent.md" in target.error


def test_a_path_escaping_outputs_is_refused(answered: SessionDocument) -> None:
    target = resolve_target(answered, FileTarget(source="file", path="../audit.jsonl"))
    assert target.error == "../audit.jsonl resolves outside outputs/"


# regex.


def test_regex_contains_is_the_default_match(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    result = grade(grader("regex", RegexConfig(pattern="Alex")), answered)
    assert result.passed is True
    assert result.explanation == "matched Alex"
    assert result.skipped is False


def test_regex_contains_that_finds_nothing_fails(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    result = grade(grader("regex", RegexConfig(pattern="Robin")), answered)
    assert result.passed is False
    assert result.explanation == "no match for Robin"


def test_regex_not_contains(answered: SessionDocument, grader: Callable[..., Grader]) -> None:
    assert (
        grade(grader("regex", RegexConfig(pattern="Robin", match="not_contains")), answered).passed
        is True
    )
    failing = grade(grader("regex", RegexConfig(pattern="Alex", match="not_contains")), answered)
    assert failing.passed is False
    assert failing.explanation == "matched Alex"


def test_regex_count_requires_exactly_that_many(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    def counting(wanted: str) -> Grader:
        return grader("regex", RegexConfig(target="files", pattern=r"^\w", flags="m", match=wanted))

    exact = grade(counting("count:2"), answered)
    assert exact.passed is True
    assert exact.explanation == r"matched ^\w 2x (expected exactly 2)"
    assert grade(counting("count:1"), answered).passed is False


def test_regex_flags_map_onto_the_python_engine(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    assert grade(grader("regex", RegexConfig(pattern="alex", flags="i")), answered).passed is True
    assert grade(grader("regex", RegexConfig(pattern="alex")), answered).passed is False


def test_a_pattern_that_does_not_compile_is_a_failed_grader(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    result = grade(grader("regex", RegexConfig(pattern="(unclosed")), answered)
    assert result.passed is False
    assert result.explanation.startswith("pattern does not compile: ")


def test_a_regex_over_an_unreadable_file_carries_the_reason(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    target = {"source": "file", "path": "absent.md"}
    result = grade(grader("regex", RegexConfig(target=target, pattern="anything")), answered)
    assert result.passed is False
    assert "absent.md" in result.explanation


# tool_used.


def test_tool_used_counts_calls_of_that_tool(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    result = grade(grader("tool_used", ToolUsedConfig(tool="Read")), answered)
    assert result.passed is True
    assert result.explanation == "Read called 1x (expected 1 or more)"


def test_tool_used_matches_the_json_encoded_input(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    fired = grader(
        "tool_used", ToolUsedConfig(tool="Skill", input_match=r'"skill"\s*:\s*"(?:[\w-]+:)?greet"')
    )
    assert grade(fired, answered).passed is True
    other = grader(
        "tool_used", ToolUsedConfig(tool="Skill", input_match=r'"skill"\s*:\s*"(?:[\w-]+:)?report"')
    )
    assert grade(other, answered).passed is False


def test_min_zero_max_zero_passes_on_no_call(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    """The must-not-call idiom. `max: 0` alone can never pass, because `min` stays 1."""
    never = grade(grader("tool_used", ToolUsedConfig(tool="WebFetch", min=0, max=0)), answered)
    assert never.passed is True
    assert never.explanation == "WebFetch called 0x (expected exactly 0)"
    assert (
        grade(grader("tool_used", ToolUsedConfig(tool="Read", min=0, max=0)), answered).passed
        is False
    )
    assert (
        grade(grader("tool_used", ToolUsedConfig(tool="WebFetch", max=0)), answered).passed is False
    )


def test_tool_used_reports_a_range(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    result = grade(grader("tool_used", ToolUsedConfig(tool="Read", min=1, max=3)), answered)
    assert result.explanation == "Read called 1x (expected 1 to 3)"


def test_an_input_match_that_does_not_compile_is_a_failed_grader(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    result = grade(
        grader("tool_used", ToolUsedConfig(tool="Skill", input_match="(unclosed")), answered
    )
    assert result.passed is False
    assert result.explanation.startswith("input_match does not compile: ")


# tool_order.


def test_tool_order_on_two_tool_names(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    result = grade(grader("tool_order", ToolOrderConfig(before="Read", after="Write")), answered)
    assert result.passed is True
    assert result.explanation == "Read preceded Write"
    wrong = grade(grader("tool_order", ToolOrderConfig(before="Write", after="Read")), answered)
    assert wrong.passed is False
    assert wrong.explanation == "Write did not precede Read"


def test_tool_order_takes_the_object_form(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    result = grade(
        grader(
            "tool_order",
            ToolOrderConfig(before="Read", after={"tool": "Write", "input_match": "report"}),
        ),
        answered,
    )
    assert result.passed is True


def test_tool_order_needs_both_ends_to_have_been_called(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    result = grade(grader("tool_order", ToolOrderConfig(before="Read", after="WebFetch")), answered)
    assert result.passed is False
    assert result.explanation == "WebFetch was never called"


# file_exists.


def test_file_exists_matches_a_bare_name_because_the_prefix_is_stripped(
    answered: SessionDocument,
    grader: Callable[..., Grader],
) -> None:
    result = grade(grader("file_exists", FileExistsConfig(path="report.md")), answered)
    assert result.passed is True
    assert result.explanation == "created report.md"


def test_file_exists_matches_a_glob_at_any_depth(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    assert grade(grader("file_exists", FileExistsConfig(path="**/*.svg")), answered).passed is True
    assert grade(grader("file_exists", FileExistsConfig(path="*.svg")), answered).passed is False


def test_file_exists_false_asserts_no_created_file_matches(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    absent = grade(
        grader("file_exists", FileExistsConfig(path="**/*.pptx", exists=False)), answered
    )
    assert absent.passed is True
    assert absent.explanation == "no created file matches **/*.pptx"
    present = grade(
        grader("file_exists", FileExistsConfig(path="report.md", exists=False)), answered
    )
    assert present.passed is False
    assert present.explanation == "created report.md"


def test_file_exists_over_a_session_that_wrote_nothing(
    quiet: SessionDocument, grader: Callable[..., Grader]
) -> None:
    assert created(quiet) == []
    assert grade(grader("file_exists", FileExistsConfig(path="report.md")), quiet).passed is False


# What nothing knows.


def test_an_unknown_grader_type_is_a_failed_grader_naming_it(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    result = grade(grader("no_such_type"), answered)
    assert result.passed is False
    assert result.explanation == "unknown grader type: no_such_type"


def test_a_grader_file_with_no_type_names_that(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    result = grade(grader(""), answered)
    assert result.explanation == "unknown grader type: (none)"


def test_a_grader_result_carries_its_weight(
    answered: SessionDocument, grader: Callable[..., Grader]
) -> None:
    assert grade(grader("regex", RegexConfig(pattern="Alex"), weight=2), answered).weight == 2


# The glob translation.
#
# `PurePath.full_match` is Python 3.13 and this package runs on 3.10, so `_full_match`
# translates the glob itself. These rows are the reference behaviour, captured from
# `PurePath.full_match` on 3.14 over the cross product of these patterns and paths.
# docs/library.md.


@pytest.mark.parametrize(
    ("glob", "path", "matches"),
    [
        ("*.pptx", "report.pptx", True),
        ("*.pptx", "a/report.pptx", False),
        ("**/*.pptx", "report.pptx", True),
        ("**/*.pptx", "a/report.pptx", True),
        ("**/*.pptx", "a/b/report.pptx", True),
        ("**/*.pptx", "a/b.txt", False),
        ("report.pptx", "report.pptx", True),
        ("a/**/b.txt", "a/b.txt", True),
        ("a/**/b.txt", "a/x/b.txt", True),
        ("a/**/b.txt", "b.txt", False),
        ("a/**", "a/b", True),
        ("a/**", "a/b/c", True),
        ("a/**", "a", False),
        ("**", "a", True),
        ("**", "a/b/c", True),
        ("**/a/*.md", "q/a/n.md", True),
        ("**/a/*.md", "notes.md", False),
        ("?.txt", "x.txt", True),
        ("?.txt", "ab/b", False),
        ("[ab].txt", "b.txt", True),
        ("[ab].txt", "c.txt", False),
        ("[!ab].txt", "c.txt", True),
        ("[!ab].txt", "b.txt", False),
        ("a*/b", "ab/b", True),
        ("out/**/*.csv", "out/x/y/z.csv", True),
        ("out/**/*.csv", "out/z.csv", True),
        ("*/*.txt", "a/x.txt", True),
        ("*/*.txt", "x.txt", False),
    ],
)
def test_the_glob_translation_is_full_match(glob: str, path: str, matches: bool) -> None:
    assert _full_match(path, glob) is matches
