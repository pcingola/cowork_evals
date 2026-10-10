"""The four structural graders over hand-written session documents.

The documents are under tests/data/documents/, and the produced files they name are real
files beside them. Every expected value is a literal. Nothing here submits anything. The
semantics are docs/claude_code/plugin_eval_reference.md. See ../README.md.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from cowork_evals.cases import (
    FileExistsConfig,
    FileTarget,
    Grader,
    GraderConfig,
    RegexConfig,
    ToolOrderConfig,
    ToolSpec,
    ToolUsedConfig,
)
from cowork_evals.cowork import SessionDocument
from cowork_evals.grader import _full_match, grade, resolve_target

GraderFactory = Callable[..., Grader]

# The targets.


GREETING = r"^Hello Alex\. The report is in report\.md\.$"


@pytest.mark.parametrize(
    "config", [RegexConfig(pattern=GREETING), RegexConfig(pattern=GREETING, target="last_message")]
)
def test_last_message_is_the_default_target(
    answered: SessionDocument, grader: GraderFactory, config: RegexConfig
) -> None:
    result = grade(grader("regex", config), answered)
    assert (result.passed, result.explanation) == (True, f"matched {GREETING}")


def test_trace_is_one_json_object_per_line(answered: SessionDocument) -> None:
    """Every turn, then every tool call."""
    tool = '"mcp_server": null, "mcp_tool": null, "timestamp": "2026-09-09T10:0'
    assert resolve_target(answered, "trace").text.splitlines() == [
        '{"role": "user", "text": "Say hello to Alex and write the report."}',
        '{"role": "assistant", "text": "Hello Alex. The report is in report.md."}',
        '{"id": "call-a", "name": "Skill", "input": {"skill": "greeter:greet"}, '
        f'{tool}0:05.000Z", "result": "greeting"}}',
        '{"id": "call-b", "name": "Read", "input": {"file_path": "notes.md"}, '
        f'{tool}0:20.000Z", "result": "three notes"}}',
        '{"id": "call-c", "name": "Write", "input": {"file_path": "report.md"}, '
        f'{tool}1:00.000Z", "result": "written"}}',
    ]


def test_files_is_the_stripped_list_newline_separated(answered: SessionDocument) -> None:
    assert resolve_target(answered, "files").text == "figures/chart.svg\nreport.md"


def test_a_file_target_reads_under_outputs(answered: SessionDocument) -> None:
    target = resolve_target(answered, FileTarget(source="file", path="report.md"))
    assert target.error is None
    assert target.text == "# Report\n\n- One bullet about the migration.\n"


def test_a_path_escaping_outputs_is_a_failed_grader(
    answered: SessionDocument, grader: GraderFactory
) -> None:
    target = FileTarget(source="file", path="../audit.jsonl")
    result = grade(grader("regex", RegexConfig(target=target, pattern="queued")), answered)
    assert result.passed is False
    assert result.explanation == "../audit.jsonl resolves outside outputs/"


def test_a_regex_over_an_unreadable_file_carries_the_reason(
    answered: SessionDocument, grader: GraderFactory
) -> None:
    target = FileTarget(source="file", path="absent.md")
    result = grade(grader("regex", RegexConfig(target=target, pattern="anything")), answered)
    assert result.passed is False
    assert result.explanation.startswith("absent.md is unreadable: ")


# regex.


@pytest.mark.parametrize(
    ("config", "passed", "explanation"),
    [
        (RegexConfig(pattern="Alex"), True, "matched Alex"),
        (RegexConfig(pattern="Robin"), False, "no match for Robin"),
        (RegexConfig(pattern="Robin", match="not_contains"), True, "no match for Robin"),
        (RegexConfig(pattern="Alex", match="not_contains"), False, "matched Alex"),
        (
            RegexConfig(target="files", pattern=r"^\w", flags="m", match="count:2"),
            True,
            r"matched ^\w 2x (expected exactly 2)",
        ),
        (
            RegexConfig(target="files", pattern=r"^\w", flags="m", match="count:1"),
            False,
            r"matched ^\w 2x (expected exactly 1)",
        ),
    ],
)
def test_regex_match_modes(
    answered: SessionDocument,
    grader: GraderFactory,
    config: RegexConfig,
    passed: bool,
    explanation: str,
) -> None:
    result = grade(grader("regex", config), answered)
    assert (result.passed, result.explanation) == (passed, explanation)


def test_regex_flags_map_onto_the_python_engine(
    answered: SessionDocument, grader: GraderFactory
) -> None:
    assert grade(grader("regex", RegexConfig(pattern="alex", flags="i")), answered).passed is True
    assert grade(grader("regex", RegexConfig(pattern="alex")), answered).passed is False


@pytest.mark.parametrize(
    ("kind", "config", "prefix"),
    [
        ("regex", RegexConfig(pattern="(unclosed"), "pattern does not compile: "),
        (
            "tool_used",
            ToolUsedConfig(tool="Skill", input_match="(unclosed"),
            "input_match does not compile: ",
        ),
    ],
)
def test_a_pattern_that_does_not_compile_is_a_failed_grader(
    answered: SessionDocument, grader: GraderFactory, kind: str, config: GraderConfig, prefix: str
) -> None:
    result = grade(grader(kind, config), answered)
    assert result.passed is False
    assert result.explanation.startswith(prefix)


# tool_used. `max: 0` alone can never pass, because `min` stays 1.


@pytest.mark.parametrize(
    ("config", "passed", "explanation"),
    [
        (ToolUsedConfig(tool="Read"), True, "Read called 1x (expected 1 or more)"),
        (ToolUsedConfig(tool="Read", min=1, max=3), True, "Read called 1x (expected 1 to 3)"),
        (
            ToolUsedConfig(tool="WebFetch", min=0, max=0),
            True,
            "WebFetch called 0x (expected exactly 0)",
        ),
        (ToolUsedConfig(tool="Read", min=0, max=0), False, "Read called 1x (expected exactly 0)"),
        (ToolUsedConfig(tool="WebFetch", max=0), False, "WebFetch called 0x (expected 1 to 0)"),
    ],
)
def test_tool_used_counts_calls_of_that_tool(
    answered: SessionDocument,
    grader: GraderFactory,
    config: ToolUsedConfig,
    passed: bool,
    explanation: str,
) -> None:
    result = grade(grader("tool_used", config), answered)
    assert (result.passed, result.explanation) == (passed, explanation)


def test_tool_used_matches_the_json_encoded_input(
    answered: SessionDocument, grader: GraderFactory
) -> None:
    fired = grader(
        "tool_used", ToolUsedConfig(tool="Skill", input_match=r'"skill"\s*:\s*"(?:[\w-]+:)?greet"')
    )
    assert grade(fired, answered).passed is True
    other = grader(
        "tool_used", ToolUsedConfig(tool="Skill", input_match=r'"skill"\s*:\s*"(?:[\w-]+:)?report"')
    )
    assert grade(other, answered).passed is False


# tool_order.


@pytest.mark.parametrize(
    ("config", "passed", "explanation"),
    [
        (ToolOrderConfig(before="Read", after="Write"), True, "Read preceded Write"),
        (ToolOrderConfig(before="Write", after="Read"), False, "Write did not precede Read"),
        (ToolOrderConfig(before="Read", after="WebFetch"), False, "WebFetch was never called"),
        (
            ToolOrderConfig(before="Read", after=ToolSpec(tool="Write", input_match="report")),
            True,
            "Read preceded Write",
        ),
        (
            ToolOrderConfig(before="Read", after=ToolSpec(tool="Write", input_match="slides")),
            False,
            "Write was never called",
        ),
    ],
)
def test_tool_order(
    answered: SessionDocument,
    grader: GraderFactory,
    config: ToolOrderConfig,
    passed: bool,
    explanation: str,
) -> None:
    result = grade(grader("tool_order", config), answered)
    assert (result.passed, result.explanation) == (passed, explanation)


# file_exists. The `outputs/` prefix is stripped, so a bare name matches.


@pytest.mark.parametrize(
    ("document", "config", "passed", "explanation"),
    [
        ("answered", FileExistsConfig(path="report.md"), True, "created report.md"),
        ("answered", FileExistsConfig(path="**/*.svg"), True, "created figures/chart.svg"),
        ("answered", FileExistsConfig(path="*.svg"), False, "no created file matches *.svg"),
        (
            "answered",
            FileExistsConfig(path="**/*.pptx", exists=False),
            True,
            "no created file matches **/*.pptx",
        ),
        ("answered", FileExistsConfig(path="report.md", exists=False), False, "created report.md"),
        ("quiet", FileExistsConfig(path="report.md"), False, "no created file matches report.md"),
    ],
)
def test_file_exists(
    request: pytest.FixtureRequest,
    grader: GraderFactory,
    document: str,
    config: FileExistsConfig,
    passed: bool,
    explanation: str,
) -> None:
    result = grade(grader("file_exists", config), request.getfixturevalue(document))
    assert (result.passed, result.explanation) == (passed, explanation)


# What nothing knows.


@pytest.mark.parametrize(("kind", "named"), [("no_such_type", "no_such_type"), ("", "(none)")])
def test_an_unknown_grader_type_is_a_failed_grader_naming_it(
    answered: SessionDocument, grader: GraderFactory, kind: str, named: str
) -> None:
    result = grade(grader(kind), answered)
    assert (result.passed, result.explanation) == (False, f"unknown grader type: {named}")


def test_a_grader_result_carries_its_weight(
    answered: SessionDocument, grader: GraderFactory
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
