"""The gate over hand-written result documents.

Every document is under tests/data/results/, every expected value is a literal, and no run
directory here was produced by a run. The conditions are the gate table in
docs/running_evals.md. See ../README.md.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from cowork_evals.gate import GateResult, gate
from cowork_evals.harness import RESULT_NAME

DOCUMENTS = Path(__file__).resolve().parent.parent / "data" / "results"


def run_directory(root: Path, **plugins: str) -> Path:
    """One run directory holding one named document per plugin directory.

    A plugin whose document is named `None` gets the directory and no document, which is
    what a backend that raised leaves behind.
    """
    root.mkdir(parents=True, exist_ok=True)
    for plugin, document in plugins.items():
        directory = root / plugin
        directory.mkdir()
        if document:
            shutil.copy(DOCUMENTS / f"{document}.json", directory / RESULT_NAME)
    return root


def with_trace(directory: Path, trace: Path) -> None:
    """Point every run of the document in `directory` at one trace on disk.

    The path is the test's own, because a document's `tracePath` is absolute and no file
    under tests/data can name a directory that exists on the machine running it. What is
    asserted is still a literal: the directory the test created.
    """
    path = directory / RESULT_NAME
    document = json.loads(path.read_text(encoding="utf-8"))
    for case in document["cases"]:
        for run in case["arms"]["with"]:
            run["tracePath"] = str(trace)
    path.write_text(json.dumps(document), encoding="utf-8")


def collected(root: Path, case: str = "every-structural", index: int = 1) -> Path:
    """One collected run directory holding a trace, as traces.py leaves it."""
    directory = root / "traces" / case / f"run-{index}"
    directory.mkdir(parents=True)
    (directory / "trace.jsonl").write_text("{}\n", encoding="utf-8")
    return directory / "trace.jsonl"


def failures(result: GateResult) -> list[str]:
    return [line for line in result.lines if line.startswith("FAIL ")]


def notes(result: GateResult) -> list[str]:
    return [line for line in result.lines if line.startswith("NOTE ")]


# Passing.


def test_a_passing_document_passes(tmp_path: Path) -> None:
    result = gate(run_directory(tmp_path, smoke="pass"))
    assert result.passed
    assert failures(result) == []


def test_the_summary_is_the_last_line(tmp_path: Path) -> None:
    result = gate(run_directory(tmp_path, smoke="pass"))
    assert result.lines[-1] == "1 cases, 1 passed, overall score 1.00"


def test_the_text_is_one_line_per_entry(tmp_path: Path) -> None:
    result = gate(run_directory(tmp_path, smoke="pass"))
    assert result.text == "1 cases, 1 passed, overall score 1.00\n"


def test_an_empty_document_passes(tmp_path: Path) -> None:
    """A --tag sweep matches no case in most plugins, and that is not a failure."""
    result = gate(run_directory(tmp_path, quiet="empty"))
    assert result.passed
    assert result.lines[-1] == "0 cases, 0 passed, overall score 0.00"


# Structural graders gate.


def test_every_structural_grader_failure_is_a_failure(tmp_path: Path) -> None:
    result = gate(run_directory(tmp_path, smoke="structural_failures"))
    assert not result.passed
    assert failures(result) == [
        "FAIL smoke/every-structural: run 1: says-alex: the regex grader failed: no match for Alex",
        "FAIL smoke/every-structural: run 1: fired-skill: the tool_used grader failed: "
        "Skill was called 0 times",
        "FAIL smoke/every-structural: run 1: read-then-wrote: the tool_order grader failed: "
        "Write came before Read",
        "FAIL smoke/every-structural: run 1: wrote-deck: the file_exists grader failed: "
        "no file matched deck.pptx",
    ]


# Judged graders are printed only.


def test_a_judged_grader_failure_is_printed_and_gates_nothing(tmp_path: Path) -> None:
    result = gate(run_directory(tmp_path, smoke="judged_failure"))
    assert result.passed
    assert notes(result) == [
        "NOTE smoke/judged: run 1: reads-well: the llm grader failed: 1 of 3 votes",
        "NOTE smoke/judged: run 1: beats-baseline: the baseline grader failed: "
        "the baseline read better",
    ]


def test_a_grader_result_is_joined_to_its_definition_by_name(tmp_path: Path) -> None:
    """A result carries `name`, `passed` and `scored`, never `type`."""
    result = gate(run_directory(tmp_path, smoke="undefined_grader"))
    assert not result.passed
    assert failures(result) == [
        "FAIL smoke/renamed-grader: run 1: says-alexandra: "
        "no grader of that name is defined in the case"
    ]


# Skips.


def test_a_skipped_case_fails_with_its_reason(tmp_path: Path) -> None:
    result = gate(run_directory(tmp_path, smoke="skipped_case"))
    assert not result.passed
    assert failures(result) == [
        "FAIL smoke/needs-a-scaffold: the case was skipped: "
        "context.scaffold_script: nothing stages files into the VM"
    ]


def test_a_skipped_grader_and_an_unscored_one_each_fail(tmp_path: Path) -> None:
    result = gate(run_directory(tmp_path, smoke="unscored_grader"))
    assert not result.passed
    assert failures(result) == [
        "FAIL smoke/one-skipped-grader: run 1: called-the-stand-in: the grader was skipped: "
        "target: mock_calls, and no stand-in serves a CoWork run",
        "FAIL smoke/one-skipped-grader: run 1: unscored: "
        "not scored, and --ablation none drops no grader",
    ]


# The document itself.


def test_partial_fails_whatever_the_reason_says(tmp_path: Path) -> None:
    result = gate(run_directory(tmp_path, smoke="partial"))
    assert not result.passed
    assert failures(result) == ["FAIL smoke: partial results: interrupted"]


def test_a_run_carrying_an_error_fails_under_an_otherwise_passing_document(
    tmp_path: Path,
) -> None:
    result = gate(run_directory(tmp_path, smoke="run_error"))
    assert not result.passed
    assert failures(result) == [
        "FAIL smoke/timed-out: run 1: 7: the run did not finish inside 1800.0 seconds"
    ]


def test_a_missing_document_is_a_failure_naming_the_path(tmp_path: Path) -> None:
    result = gate(run_directory(tmp_path, smoke=""))
    assert not result.passed
    assert failures(result) == [f"FAIL {tmp_path / 'smoke' / RESULT_NAME}: no result document"]


def test_an_unparsable_document_is_a_failure_naming_the_path(tmp_path: Path) -> None:
    result = gate(run_directory(tmp_path, smoke="unparsable"))
    assert not result.passed
    assert failures(result)[0].startswith(
        f"FAIL {tmp_path / 'smoke' / RESULT_NAME}: unparsable result document: "
    )


def test_a_document_of_another_schema_version_is_a_failure(tmp_path: Path) -> None:
    result = gate(run_directory(tmp_path, smoke="wrong_schema"))
    assert not result.passed
    assert failures(result) == [
        f"FAIL {tmp_path / 'smoke' / RESULT_NAME}: schemaVersion is 2, and this gate reads 1"
    ]


def test_an_unknown_field_is_ignored(tmp_path: Path) -> None:
    """The contract is additive-only, so a field this gate does not read changes nothing."""
    directory = run_directory(tmp_path, smoke="pass")
    document = directory / "smoke" / RESULT_NAME
    document.write_text(document.read_text().replace('"partial": false', '"invented": 1'))
    assert gate(directory).passed


# The extra line, and a sweep.


def test_an_extra_line_is_a_failure_the_caller_already_had(tmp_path: Path) -> None:
    result = gate(run_directory(tmp_path, smoke="pass"), extra=("the cost ceiling stopped it",))
    assert not result.passed
    assert failures(result) == ["FAIL the cost ceiling stopped it"]


def test_two_plugins_are_gated_once(tmp_path: Path) -> None:
    result = gate(run_directory(tmp_path, mail="pass", writer="structural_failures"))
    assert not result.passed
    assert len(failures(result)) == 4
    assert result.lines[-1] == "2 cases, 2 passed, overall score 0.50"


def test_two_passing_plugins_are_one_pass(tmp_path: Path) -> None:
    result = gate(run_directory(tmp_path, mail="pass", writer="pass"))
    assert result.passed
    assert result.lines[-1] == "2 cases, 2 passed, overall score 1.00"


# What a failure line says about where to look.


def test_a_structural_failure_names_the_run_artefacts(tmp_path: Path, working_directory) -> None:
    """The whole point of keeping a trace: the line that fails says where the trace is."""
    root = run_directory(tmp_path, smoke="structural_failures")
    with_trace(root / "smoke", collected(root / "smoke"))
    with working_directory(tmp_path):
        result = gate(root)
    assert failures(result)[0].endswith("[artifacts: smoke/traces/every-structural/run-1]"), (
        failures(result)[0]
    )


def test_a_judged_note_names_them_too(tmp_path: Path, working_directory) -> None:
    """A judged grader gates nothing and still has to be investigated."""
    root = run_directory(tmp_path, smoke="judged_failure")
    with_trace(root / "smoke", collected(root / "smoke", "judged"))
    with working_directory(tmp_path):
        result = gate(root)
    assert notes(result)[0].endswith("[artifacts: smoke/traces/judged/run-1]")


def test_an_errored_run_names_them(tmp_path: Path, working_directory) -> None:
    root = run_directory(tmp_path, smoke="run_error")
    with_trace(root / "smoke", collected(root / "smoke", "timed-out"))
    with working_directory(tmp_path):
        result = gate(root)
    assert any("[artifacts: smoke/traces/timed-out/run-1]" in line for line in failures(result))


def test_a_document_whose_trace_was_not_collected_names_nothing(tmp_path: Path) -> None:
    """The gate never names a path that is not there, so a run with no trace reads as before."""
    root = run_directory(tmp_path, smoke="structural_failures")
    with_trace(root / "smoke", Path("/work/logs/tmp/claude-eval-Ab12Cd/out/trace.jsonl"))
    result = gate(root)
    assert failures(result)[0].endswith("no match for Alex")


def test_a_document_carrying_no_trace_path_names_nothing(tmp_path: Path) -> None:
    result = gate(run_directory(tmp_path, smoke="structural_failures"))
    assert failures(result)[0].endswith("no match for Alex")
