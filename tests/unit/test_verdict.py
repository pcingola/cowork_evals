"""Pass and fail over hand-written result documents.

Every document is under tests/data/results/, every expected value is a literal, and no run
directory here was produced by a run. The conditions are the pass and fail table in
docs/running_evals.md. See ../README.md.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from cowork_evals.checks import ADVISORY_TYPE
from cowork_evals.harness import RESULT_NAME
from cowork_evals.verdict import Verdict, decide

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


def judge(directory: Path, *, found: int = 1, picked: int = 1, **kwargs) -> Verdict:
    """`decide` with the two counts its caller holds.

    `found` and `picked` are the command's own counts over the case tree, which this module
    writes no case tree for. A test that asserts the summary line passes them itself; every
    other test here is about a document and states the pair that matches it.
    """
    return decide(directory, found=found, picked=picked, **kwargs)


def failures(result: Verdict) -> list[str]:
    return [line for line in result.lines if line.startswith("FAIL ")]


def notes(result: Verdict) -> list[str]:
    return [line for line in result.lines if line.startswith("NOTE ")]


# Passing.


def test_a_passing_document_passes(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="pass"))
    assert result.passed
    assert failures(result) == []


def test_the_summary_is_the_last_line(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="pass"))
    assert result.lines[-1] == (
        "1 found, 1 picked, 1 ran, 1 passed, 0 declared unrunnable, overall score 1.00"
    )


def test_the_text_is_one_line_per_entry(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="pass"))
    assert result.text == (
        "1 found, 1 picked, 1 ran, 1 passed, 0 declared unrunnable, overall score 1.00\n"
    )


def test_an_empty_document_passes(tmp_path: Path) -> None:
    """A --tag sweep matches no case in most plugins, and that is not a failure."""
    result = judge(run_directory(tmp_path, quiet="empty"), found=1, picked=0)
    assert result.passed
    assert result.lines[-1] == (
        "1 found, 0 picked, 0 ran, 0 passed, 0 declared unrunnable, overall score 0.00"
    )


# Structural graders decide the verdict.


def test_every_structural_grader_failure_is_a_failure(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="structural_failures"))
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
    result = judge(run_directory(tmp_path, smoke="judged_failure"))
    assert result.passed
    assert notes(result) == [
        "NOTE smoke/judged: run 1: reads-well: the llm grader failed: 1 of 3 votes",
        "NOTE smoke/judged: run 1: beats-baseline: the baseline grader failed: "
        "the baseline read better",
    ]


def test_a_grader_result_is_joined_to_its_definition_by_name(tmp_path: Path) -> None:
    """A result carries `name`, `passed` and `scored`, never `type`."""
    result = judge(run_directory(tmp_path, smoke="undefined_grader"))
    assert not result.passed
    assert failures(result) == [
        "FAIL smoke/renamed-grader: run 1: says-alexandra: "
        "no grader of that name is defined in the case"
    ]


# A case the backend was told it cannot run.


def test_a_declared_case_is_counted_and_the_suite_passes(tmp_path: Path) -> None:
    """It produces no line of its own, and the summary is where it is visible."""
    result = judge(run_directory(tmp_path, smoke="declared_case"), found=1, picked=1)
    assert result.passed
    assert result.lines == (
        "1 found, 1 picked, 0 ran, 0 passed, 1 declared unrunnable, overall score 0.00",
    )


# Skips.


def test_a_skipped_case_fails_with_its_reason(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="skipped_case"))
    assert not result.passed
    assert failures(result) == [
        "FAIL smoke/needs-a-scaffold: the case was skipped: "
        "context.scaffold_script: nothing stages files into the VM"
    ]


def test_a_skipped_grader_and_an_unscored_one_each_fail(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="unscored_grader"))
    assert not result.passed
    assert failures(result) == [
        "FAIL smoke/one-skipped-grader: run 1: called-the-stand-in: the grader was skipped: "
        "target: mock_calls, and no stand-in serves a CoWork run",
        "FAIL smoke/one-skipped-grader: run 1: unscored: "
        "not scored, and --ablation none drops no grader",
    ]


# The document itself.


def test_partial_fails_whatever_the_reason_says(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="partial"))
    assert not result.passed
    assert failures(result) == ["FAIL smoke: partial results: interrupted"]


def test_a_run_carrying_an_error_fails_under_an_otherwise_passing_document(
    tmp_path: Path,
) -> None:
    result = judge(run_directory(tmp_path, smoke="run_error"))
    assert not result.passed
    assert failures(result) == [
        "FAIL smoke/timed-out: run 1: 7: the run did not finish inside 1800.0 seconds"
    ]


def test_a_missing_document_is_a_failure_naming_the_path(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke=""))
    assert not result.passed
    assert failures(result) == [f"FAIL {tmp_path / 'smoke' / RESULT_NAME}: no result document"]


def test_an_unparsable_document_is_a_failure_naming_the_path(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="unparsable"))
    assert not result.passed
    assert failures(result)[0].startswith(
        f"FAIL {tmp_path / 'smoke' / RESULT_NAME}: unparsable result document: "
    )


def test_a_document_of_another_schema_version_is_a_failure(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="wrong_schema"))
    assert not result.passed
    assert failures(result) == [
        f"FAIL {tmp_path / 'smoke' / RESULT_NAME}: schemaVersion is 2, and this module reads 1"
    ]


def test_an_unknown_field_is_ignored(tmp_path: Path) -> None:
    """The contract is additive-only, so a field this module does not read changes nothing."""
    directory = run_directory(tmp_path, smoke="pass")
    document = directory / "smoke" / RESULT_NAME
    document.write_text(document.read_text().replace('"partial": false', '"invented": 1'))
    assert judge(directory).passed


# The extra line, and a sweep.


def test_an_extra_line_is_a_failure_the_caller_already_had(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="pass"), extra=("the cost ceiling stopped it",))
    assert not result.passed
    assert failures(result) == ["FAIL the cost ceiling stopped it"]


def test_two_plugins_are_gated_once(tmp_path: Path) -> None:
    directory = run_directory(tmp_path, mail="pass", writer="structural_failures")
    result = judge(directory, found=2, picked=2)
    assert not result.passed
    assert len(failures(result)) == 4
    assert result.lines[-1] == (
        "2 found, 2 picked, 2 ran, 1 passed, 0 declared unrunnable, overall score 0.50"
    )


def test_two_passing_plugins_are_one_pass(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, mail="pass", writer="pass"), found=2, picked=2)
    assert result.passed
    assert result.lines[-1] == (
        "2 found, 2 picked, 2 ran, 2 passed, 0 declared unrunnable, overall score 1.00"
    )


# What a failure line says about where to look.


def test_a_structural_failure_names_the_run_artefacts(tmp_path: Path, working_directory) -> None:
    """The whole point of keeping a trace: the line that fails says where the trace is."""
    root = run_directory(tmp_path, smoke="structural_failures")
    with_trace(root / "smoke", collected(root / "smoke"))
    with working_directory(tmp_path):
        result = judge(root)
    assert failures(result)[0].endswith("[artifacts: smoke/traces/every-structural/run-1]"), (
        failures(result)[0]
    )


def test_a_judged_note_names_them_too(tmp_path: Path, working_directory) -> None:
    """A judged grader decides nothing and still has to be investigated."""
    root = run_directory(tmp_path, smoke="judged_failure")
    with_trace(root / "smoke", collected(root / "smoke", "judged"))
    with working_directory(tmp_path):
        result = judge(root)
    assert notes(result)[0].endswith("[artifacts: smoke/traces/judged/run-1]")


def test_an_errored_run_names_them(tmp_path: Path, working_directory) -> None:
    root = run_directory(tmp_path, smoke="run_error")
    with_trace(root / "smoke", collected(root / "smoke", "timed-out"))
    with working_directory(tmp_path):
        result = judge(root)
    assert any("[artifacts: smoke/traces/timed-out/run-1]" in line for line in failures(result))


def test_a_document_whose_trace_was_not_collected_names_nothing(tmp_path: Path) -> None:
    """It never names a path that is not there, so a run with no trace reads as before."""
    root = run_directory(tmp_path, smoke="structural_failures")
    with_trace(root / "smoke", Path("/work/logs/tmp/claude-eval-Ab12Cd/out/trace.jsonl"))
    result = judge(root)
    assert failures(result)[0].endswith("no match for Alex")


def test_a_document_carrying_no_trace_path_names_nothing(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="structural_failures"))
    assert failures(result)[0].endswith("no match for Alex")


# The baseline arm, and the delta it is decided on.


def test_a_one_arm_document_carries_no_delta_on_the_summary_line(tmp_path: Path) -> None:
    """One arm is the default, and a number that is always 0 there would read as a plugin
    that changed nothing."""
    result = judge(run_directory(tmp_path, smoke="pass"))
    assert "delta" not in result.lines[-1]


def test_a_delta_above_the_threshold_passes_and_the_mean_is_on_the_line(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="two_arm"), found=2, picked=2)
    assert result.passed
    assert failures(result) == []
    assert result.lines[-1] == (
        "2 found, 2 picked, 2 ran, 2 passed, 0 declared unrunnable, "
        "overall score 1.00, mean delta +0.50"
    )


def test_a_delta_below_the_threshold_fails_and_the_line_names_both_scores(
    tmp_path: Path,
) -> None:
    """The plugin made the case worse, every grader passed, and the suite is red."""
    result = judge(run_directory(tmp_path, smoke="two_arm_below_threshold"))
    assert not result.passed
    assert failures(result) == [
        "FAIL smoke/writes-a-file: the delta is -0.25, with 0.50 and without 0.75, "
        "and eval.delta_threshold is 0"
    ]


def test_a_delta_at_the_threshold_passes(tmp_path: Path) -> None:
    """Failing is below the threshold, so a plugin that changed nothing under a threshold of
    0 is reported by the mean and not by a failure."""
    result = judge(run_directory(tmp_path, smoke="two_arm"), found=2, picked=2)
    assert result.passed


def test_a_raised_threshold_fails_the_case_that_changed_nothing(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="two_arm"), found=2, picked=2, delta_threshold=0.5)
    assert not result.passed
    assert failures(result) == [
        "FAIL smoke/quiet-case: the delta is +0.00, with 1.00 and without 1.00, "
        "and eval.delta_threshold is 0.5"
    ]


def test_a_two_arm_case_whose_baseline_arm_ran_nothing_fails(tmp_path: Path) -> None:
    """A two-arm run that produced no delta did not do what the invocation asked."""
    result = judge(run_directory(tmp_path, smoke="two_arm_no_baseline"))
    assert not result.passed
    assert failures(result) == [
        "FAIL smoke/fires-and-answers: the arms are not comparable: the baseline arm ran nothing"
    ]
    assert result.lines[-1].endswith("overall score 1.00, mean delta none")


def test_a_two_arm_case_graded_under_different_rules_fails_and_says_so(tmp_path: Path) -> None:
    """The other of the two reasons the document tells apart."""
    result = judge(run_directory(tmp_path, smoke="two_arm_skipped_paid"))
    assert not result.passed
    assert failures(result) == [
        "FAIL smoke/judged: the arms are not comparable: a run skipped its paid graders "
        "at the cost ceiling"
    ]


def test_an_unscored_grader_fails_one_arm_and_is_an_indicator_on_two(tmp_path: Path) -> None:
    """On one arm nothing is dropped from the score, so a grader not scored was not asked.
    On two the harness drops a with-only grader on purpose."""
    one = judge(run_directory(tmp_path / "one", smoke="unscored_grader"))
    assert not one.passed
    assert any("not scored, and --ablation none drops no grader" in line for line in one.lines)

    two = judge(run_directory(tmp_path / "two", smoke="two_arm"), found=2, picked=2)
    assert two.passed
    assert notes(two) == [
        "NOTE smoke/quiet-case: run 1: skill-fired: the with-only indicator did not fire"
    ]


def test_a_case_whose_graders_are_all_with_only_is_scored_normally(tmp_path: Path) -> None:
    """The harness's own exception. The document says `scored: true`, and this reads it
    rather than re-deriving which graders the arm dropped."""
    result = judge(run_directory(tmp_path, smoke="two_arm_all_with_only"))
    assert result.passed
    assert failures(result) == []
    assert notes(result) == []


# A run that never had the tool the case was granted.


def test_a_mode_denial_fails_a_document_whose_graders_all_passed(tmp_path: Path) -> None:
    """Every grader passed, and the model never had `Write`, so the score says nothing."""
    result = judge(run_directory(tmp_path, smoke="mode_denial"))
    assert not result.passed
    assert failures(result) == [
        "FAIL smoke/tool-denied: run 1: the permission mode refused Write, "
        "so the score is not a fact about the plugin"
    ]


def test_a_tool_that_was_never_offered_fails_the_same_way(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="tool_not_offered"))
    assert not result.passed
    assert failures(result) == [
        "FAIL smoke/tool-not-offered: run 1: the run was never offered Bash, "
        "so the score is not a fact about the plugin"
    ]


def test_a_denial_line_names_the_directory_holding_the_trace(
    tmp_path: Path, working_directory
) -> None:
    root = run_directory(tmp_path, smoke="mode_denial")
    with_trace(root / "smoke", collected(root / "smoke", "tool-denied"))
    with working_directory(tmp_path):
        result = judge(root)
    assert failures(result)[0].endswith("[artifacts: smoke/traces/tool-denied/run-1]")


def test_a_document_carrying_neither_field_passes(tmp_path: Path) -> None:
    """Every `--cowork` document is this shape, so one set of rules covers both backends."""
    result = judge(run_directory(tmp_path, smoke="pass"))
    assert result.passed


# The five counts on the last line.


def test_the_last_line_carries_the_five_counts(tmp_path: Path) -> None:
    """Found and picked are the caller's, ran is the harness's, the last two are this
    module's."""
    result = judge(run_directory(tmp_path, smoke="structural_failures"), found=9, picked=4)
    assert result.lines[-1] == (
        "9 found, 4 picked, 1 ran, 0 passed, 0 declared unrunnable, overall score 0.00"
    )


def test_the_pass_count_is_not_read_back_from_the_document(tmp_path: Path) -> None:
    """`casesPassed` is 1 in that document, under a threshold of 0. One case failed."""
    document = run_directory(tmp_path, smoke="structural_failures") / "smoke" / RESULT_NAME
    assert json.loads(document.read_text())["aggregates"]["casesPassed"] == 1
    last = judge(document.parent.parent).lines[-1]
    assert last.endswith("0 passed, 0 declared unrunnable, overall score 0.00")


def test_the_last_line_says_when_a_sweep_stopped_early(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="partial"), found=3, picked=3)
    assert result.lines[-1] == (
        "3 found, 3 picked, 1 ran, 1 passed, 0 declared unrunnable, "
        "overall score 1.00, stopped early: interrupted"
    )


def test_picked_and_ran_differing_is_not_a_failure(tmp_path: Path) -> None:
    """This package counts one and the harness counts the other, and neither checks the other."""
    result = judge(run_directory(tmp_path, smoke="pass"), found=4, picked=4)
    assert result.passed
    assert result.lines[-1] == (
        "4 found, 4 picked, 1 ran, 1 passed, 0 declared unrunnable, overall score 1.00"
    )


# The outcome, beside the lines printed for the same document.


def outcomes(result: Verdict) -> list[tuple[str, str]]:
    """Each case's name and what this module concluded about it."""
    return [(one.name, one.outcome) for one in result.outcomes]


def test_a_passing_case_is_recorded_as_a_pass(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="pass"))
    assert outcomes(result) == [("python-version", "pass")]
    assert failures(result) == []


def test_a_failing_case_is_recorded_as_a_fail_beside_its_lines(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="structural_failures"))
    assert outcomes(result) == [("every-structural", "fail")]
    assert failures(result)


def test_a_declared_case_is_recorded_as_declared(tmp_path: Path) -> None:
    """It neither passes nor fails, and the word is the one the summary line counts."""
    result = judge(run_directory(tmp_path, smoke="declared_case"))
    assert outcomes(result) == [("capped-turns", "declared")]
    assert failures(result) == []


def test_a_judged_failure_alone_is_still_a_pass(tmp_path: Path) -> None:
    """Judged graders decide nothing, so the outcome agrees with the exit code."""
    result = judge(run_directory(tmp_path, smoke="judged_failure"))
    assert outcomes(result) == [("judged", "pass")]
    assert notes(result)


def test_a_two_arm_document_records_one_outcome_per_case(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="two_arm"), found=2, picked=2)
    assert outcomes(result) == [("fires-and-answers", "pass"), ("quiet-case", "pass")]


def test_a_two_arm_case_below_the_threshold_is_recorded_as_a_fail(tmp_path: Path) -> None:
    result = judge(
        run_directory(tmp_path, smoke="two_arm_below_threshold"),
        found=1,
        picked=1,
        delta_threshold=0.5,
    )
    assert outcomes(result) == [("writes-a-file", "fail")]
    assert failures(result)


def test_an_outcome_carries_the_pair_that_identifies_the_case(tmp_path: Path) -> None:
    """The run directory's child name and the case's `dir`: neither alone is unique."""
    one = judge(run_directory(tmp_path, smoke="pass")).outcomes[0]
    assert one.plugin == "smoke"
    assert one.dir == "evals/plugin/python-version"


def test_a_document_that_cannot_be_read_records_no_outcome(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke=None))
    assert result.outcomes == ()
    assert failures(result)


# A check. It is this package's own grader type, and the verdict needs no condition for it.


def test_a_failed_check_fails_the_run_like_a_structural_grader(tmp_path: Path) -> None:
    result = judge(run_directory(tmp_path, smoke="check_failure"))
    assert result.passed is False
    assert failures(result) == [
        "FAIL smoke/checked-file: run 1: assertions.the_file_says_written: "
        "the check grader failed: AssertionError: written.txt says NOTHING"
    ]
    assert notes(result) == []


def test_a_failed_advisory_check_is_a_note_and_fails_nothing(tmp_path: Path) -> None:
    """The same failing check, marked advisory by its definition. docs/checks.md."""
    directory = run_directory(tmp_path, smoke="check_failure")
    document = json.loads((directory / "smoke" / RESULT_NAME).read_text())
    for definition in document["cases"][0]["graders"]:
        if definition["type"] == "check":
            definition["type"] = ADVISORY_TYPE
    (directory / "smoke" / RESULT_NAME).write_text(json.dumps(document))

    result = judge(directory)
    assert result.passed is True
    assert failures(result) == []
    assert notes(result) == [
        "NOTE smoke/checked-file: run 1: assertions.the_file_says_written: "
        "the advisory check failed: AssertionError: written.txt says NOTHING"
    ]


def test_a_failed_check_names_the_directory_holding_its_scratch(tmp_path: Path) -> None:
    """`verdict.artifacts` names the parent of `tracePath`, and both sit beside it."""
    directory = run_directory(tmp_path, smoke="check_failure")
    trace = collected(directory / "smoke", case="checked-file")
    (trace.parent / "scratch").mkdir()
    (trace.parent / "checks.jsonl").write_text("{}\n", encoding="utf-8")
    with_trace(directory / "smoke", trace)

    line = failures(judge(directory))[0]
    assert line.endswith(f"[artifacts: {trace.parent}]")
    assert (trace.parent / "scratch").is_dir()
    assert (trace.parent / "checks.jsonl").is_file()
