"""The check layer over hand-written case trees and hand-written run directories.

The case tree and the collected run are under tests/data/checks/. The run directory is
copied into `tmp_path` before anything runs, because a check writes `scratch/` and the layer
writes `checks.jsonl` beside the three collected names, and a fixture directory is read and
never written. The discovery, the loader and the execution are the real ones, and every
expected value is a literal. No model, and no judge. See ../README.md.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from cowork_evals import checks
from cowork_evals.checks import JudgeCall, Outcome, Run
from cowork_evals.grader import GraderResult
from cowork_evals.harness import RESULT_NAME
from cowork_evals.results import (
    Arms,
    CaseAggregates,
    CaseEntry,
    GraderDefinition,
    PluginRef,
    ResultDocument,
    RunEntry,
    SuiteAggregates,
    SuiteInfo,
    write,
)

DATA = Path(__file__).resolve().parent.parent / "data" / "checks"
PLUGIN = DATA / "plugin"
CASES = PLUGIN / "evals" / "plugin"
NO_CHECKS = Path(__file__).resolve().parent.parent / "data" / "cases" / "tree" / "evals"


@pytest.fixture
def collected(tmp_path: Path) -> Path:
    """One collected run directory, copied out of the fixture tree so it can be written."""
    directory = tmp_path / "traces" / "checked" / "run-1"
    shutil.copytree(DATA / "run", directory)
    return directory


def one_run(collected: Path, case: str = "checked", index: int = 1) -> Run:
    return checks.build_run(collected, CASES / case, index, "haiku")


# Discovery.


def test_a_check_is_named_for_its_file_and_its_function() -> None:
    found = checks.discover(CASES / "checked")
    assert [one.name for one in found] == [
        "assertions.the_file_says_written",
        "assertions.the_sibling_is_importable",
        "assertions.the_last_message_is_read",
        "assertions.the_scratch_is_writable",
    ]


@pytest.mark.parametrize(
    "case_dir", [CASES / "noted", NO_CHECKS / "greeter" / "no-frontmatter"], ids=["helper", "none"]
)
def test_a_case_with_no_decorated_function_yields_nothing(case_dir: Path) -> None:
    """A file with no `@check` is a helper, and a case with no `checks/` has no check."""
    assert checks.discover(case_dir) == ()


def test_the_checks_directory_is_on_sys_path_only_while_the_files_load() -> None:
    before = list(sys.path)
    found = checks.discover(CASES / "checked")
    assert sys.path == before
    assert found  # the sibling import resolved while the directory was on the path


def test_each_case_imports_its_own_helper(collected: Path) -> None:
    """`imported` holds a `helpers.py` of its own, and its check fails if it is handed the
    `helpers` module `checked` loaded first."""
    for case in ("checked", "imported"):
        found = outcomes(case, collected)
        assert [one.passed for one in found.values()] == [True] * len(found)
    assert "helpers" not in sys.modules


# The run a check reads.


def test_the_run_carries_what_the_collector_left(collected: Path) -> None:
    assert not (collected / "scratch").exists()
    run = one_run(collected)
    assert run.workspace == collected / "workspace"
    assert run.trace == collected / "trace.jsonl"
    assert run.last_message == "WRITTEN\n"
    assert run.run_dir == collected
    assert run.case_dir == CASES / "checked"
    assert run.index == 1
    assert run.judge_model == "haiku"
    assert run.scratch == collected / "scratch"
    assert run.scratch.is_dir(), "it exists before the first check"


def test_a_run_with_no_last_message_reads_as_empty(collected: Path) -> None:
    (collected / "last_message.txt").unlink()
    assert one_run(collected).last_message == ""


def test_file_resolves_under_the_workspace(collected: Path) -> None:
    assert one_run(collected).file("written.txt") == collected / "workspace" / "written.txt"


# The judge over paths. Nothing here starts a process: the two refusals return before one.


@pytest.mark.parametrize(
    ("paths", "explanation"),
    [
        ((), "run.judge was called with no path, and it has no default of everything"),
        (("scratch/deck.png",), "scratch/deck.png is not there, so it cannot be judged"),
    ],
)
def test_a_judge_call_with_nothing_to_judge_is_a_failed_check(
    collected: Path, paths: tuple[str, ...], explanation: str
) -> None:
    result = one_run(collected).judge("Every slide carries a title.", *paths)
    assert result.passed is False
    assert result.explanation == explanation


# Execution.


def outcomes(case: str, collected: Path) -> dict[str, Outcome]:
    return {
        one.name.split(".")[-1]: checks.execute(one, one_run(collected, case))
        for one in checks.discover(CASES / case)
    }


def test_every_passing_shape_passes(collected: Path) -> None:
    found = outcomes("checked", collected)
    assert [one.passed for one in found.values()] == [True, True, True, True]
    assert found["the_file_says_written"].explanation == "the check raised nothing"
    assert found["the_sibling_is_importable"].explanation == "the check returned True"
    assert found["the_last_message_is_read"].explanation == "the reply says WRITTEN"


def test_every_failing_shape_fails(collected: Path) -> None:
    found = outcomes("failing", collected)
    assert [one.passed for one in found.values()] == [False] * 7
    assert found["returns_false"].explanation == "the check returned False"
    assert found["returns_a_failed_result"].explanation == "the totals do not add up"
    assert found["raises"].explanation == "ValueError: the workbook has no active sheet"
    assert found["asserts"].explanation == "AssertionError: "
    assert (
        found["names_a_file_that_is_not_there"].explanation == "absent.txt is not in the workspace"
    )
    assert (
        found["leaves_the_workspace"].explanation == "../trace.jsonl resolves outside the workspace"
    )
    assert found["returns_something_else"].explanation == (
        "the check returned int, and a check returns None, a bool or a Result"
    )


def test_a_file_that_will_not_import_is_a_failed_check(collected: Path) -> None:
    (one,) = checks.discover(CASES / "broken")
    outcome = checks.execute(one, one_run(collected, "broken"))
    assert outcome.name == "unimportable", "named for its file"
    assert outcome.passed is False
    assert outcome.explanation == (
        "unimportable.py could not be imported: RuntimeError: openpyxl is not installed"
    )


def test_a_judged_check_keeps_the_whole_exchange_in_its_line() -> None:
    call = JudgeCall(prompt="the whole prompt", replies=["PASS", "FAIL", "PASS"], cost_usd=0.01)
    outcome = Outcome(
        name="assertions.deck_is_readable",
        passed=True,
        explanation="judge votes: PASS FAIL PASS",
        calls=[call],
        cost_usd=0.01,
    )
    assert Outcome.from_line(outcome.document()) == outcome


# The layer: what it appends to the document, and what it writes beside the trace.


def collected_runs(directory: Path, case: str, count: int) -> list[Path]:
    """`count` collected run directories for one case, each a copy of the fixture run."""
    made = []
    for index in range(1, count + 1):
        run_dir = directory / "traces" / case / f"run-{index}"
        shutil.copytree(DATA / "run", run_dir)
        made.append(run_dir)
    return made


def run_entries(runs: list[Path], passed: bool = True) -> list[RunEntry]:
    """One run per directory, its one `file_exists` grader passing or not before any check."""
    wrote = GraderResult(
        name="wrote-it", passed=passed, weight=1, explanation="created written.txt"
    )
    return [
        RunEntry(
            score=float(passed),
            passed=passed,
            turns=1,
            cost_usd=0.01,
            judge_cost_usd=0.002,
            error=None,
            skipped_paid_graders=False,
            trace_path=str(run_dir / "trace.jsonl"),
            graders=[wrote],
        )
        for run_dir in runs
    ]


WROTE_IT = GraderDefinition(name="wrote-it", type="file_exists", weight=1)


def case_entry(
    name: str,
    runs: list[Path],
    *,
    without: list[Path] | None = None,
    aggregates: CaseAggregates | None = None,
    declared_reason: str | None = None,
) -> CaseEntry:
    """One case of a v1 document. A `without` list is a baseline arm whose grader fails."""
    return CaseEntry(
        name=name,
        dir=f"evals/plugin/{name}",
        source="prose",
        prompt_markdown="Write WRITTEN into written.txt.",
        graders=[WROTE_IT],
        arms=Arms(
            with_=run_entries(runs),
            without=None if without is None else run_entries(without, passed=False),
        ),
        aggregates=aggregates or CaseAggregates(score=1.0, pass_rate=1.0),
        declared_unrunnable=declared_reason is not None,
        declared_reason=declared_reason,
    )


def suite(
    tmp_path: Path,
    cases: list[CaseEntry],
    ablation: str = "none",
    mean_delta: float | None = None,
) -> Path:
    """One plugin's output directory, holding the document those cases make up."""
    directory = tmp_path / "smoke"
    directory.mkdir(parents=True, exist_ok=True)
    document = ResultDocument(
        schema_version=1,
        claude_version="2.1.270",
        started_at="2026-09-13T10:00:00+00:00",
        duration_seconds=3.0,
        cost_usd=0.02,
        partial=False,
        suite=SuiteInfo(
            root=str(PLUGIN),
            ablation=ablation,
            threshold=0,
            judge_model="haiku",
            plugins=[PluginRef(name="smoke", path=str(PLUGIN))],
        ),
        cases=cases,
        aggregates=SuiteAggregates(
            cases_total=len(cases),
            cases_passed=len(cases),
            overall_score=1.0,
            overall_pass_rate=1.0,
            mean_delta=mean_delta,
        ),
    )
    write(directory, document)
    return directory


def checked(directory: Path) -> ResultDocument:
    """Run the layer over one plugin's directory, and read back what it wrote."""
    assert checks.run(directory, PLUGIN, judge_model="haiku") == []
    return ResultDocument.read(directory / RESULT_NAME)


def layer(tmp_path: Path, case: str, count: int = 1) -> tuple[Path, ResultDocument]:
    """Run the layer over one case of one plugin, and return the directory and the document."""
    directory = tmp_path / "smoke"
    directory.mkdir(parents=True, exist_ok=True)
    suite(tmp_path, [case_entry(case, collected_runs(directory, case, count))])
    return directory, checked(directory)


def test_each_check_is_appended_and_a_passing_case_keeps_its_score(tmp_path: Path) -> None:
    """No check asked a judge, so neither spend moves."""
    _, document = layer(tmp_path, "checked")
    case = document.cases[0]
    names = [
        "assertions.the_file_says_written",
        "assertions.the_sibling_is_importable",
        "assertions.the_last_message_is_read",
        "assertions.the_scratch_is_writable",
    ]
    assert case.graders == [WROTE_IT] + [
        GraderDefinition(name=name, type="check", weight=1) for name in names
    ]
    run = case.arms.with_[0]
    assert run.graders[1] == GraderResult(
        name="assertions.the_file_says_written",
        passed=True,
        weight=1,
        explanation="the check raised nothing",
    )
    assert (run.score, run.passed) == (1.0, True)
    assert case.aggregates == CaseAggregates(score=1.0, pass_rate=1.0)
    assert (document.cost_usd, run.judge_cost_usd) == (0.02, 0.002)


def test_a_failed_check_drops_the_run_score_and_every_aggregate(tmp_path: Path) -> None:
    """One passing grader and seven failed checks. `--threshold` is 0, so every case counts
    as passed in `casesPassed` whatever a check said."""
    _, document = layer(tmp_path, "failing")
    run = document.cases[0].arms.with_[0]
    assert (run.score, run.passed) == (1 / 8, False)
    assert document.cases[0].aggregates == CaseAggregates(score=1 / 8, pass_rate=0.0)
    assert document.aggregates == SuiteAggregates(
        cases_total=1, cases_passed=1, overall_score=1 / 8, overall_pass_rate=0.0
    )


def test_an_advisory_failure_keeps_its_verdict_and_moves_no_score(tmp_path: Path) -> None:
    """`b.plain` passes only if it sees what `a.advised` wrote, so the scratch is shared by
    the checks of one run, and the two files run in path order."""
    _, document = layer(tmp_path, "advised")
    case = document.cases[0]
    assert [(one.name, one.type) for one in case.graders[1:]] == [
        ("a.advised", "check-advisory"),
        ("b.plain", "check"),
    ]
    run = case.arms.with_[0]
    appended = run.graders[1:]
    assert [one.passed for one in appended] == [False, True]
    assert [one.scored for one in appended] == [False, True]
    assert appended[0].explanation == "the advice was not followed"
    assert run.score == 1.0


def test_every_run_of_a_case_runs_every_check_again(tmp_path: Path) -> None:
    directory, document = layer(tmp_path, "checked", count=2)
    assert [len(run.graders) for run in document.cases[0].arms.with_] == [5, 5]
    for index in (1, 2):
        scratch = directory / "traces" / "checked" / f"run-{index}" / "scratch"
        assert [path.name for path in scratch.iterdir()] == [f"note-{index}.txt"]


def test_the_checks_file_is_written_beside_the_trace(tmp_path: Path) -> None:
    directory, _ = layer(tmp_path, "failing")
    path = directory / "traces" / "failing" / "run-1" / checks.CHECKS_FILE
    raw = path.read_text(encoding="utf-8").splitlines()
    lines = [Outcome.from_line(line) for line in raw]
    assert [line.name for line in lines] == [
        "failures.returns_false",
        "failures.returns_a_failed_result",
        "failures.raises",
        "failures.asserts",
        "failures.names_a_file_that_is_not_there",
        "failures.leaves_the_workspace",
        "failures.returns_something_else",
    ]
    assert [line.passed for line in lines] == [False] * 7
    assert lines[0].explanation == "the check returned False"
    assert lines[2].traceback is not None, "an exception keeps its traceback"
    assert lines[4].traceback is None, "a CheckError does not"
    assert all('"durationSeconds"' in line for line in raw)
    assert not any('"judge"' in line for line in raw), "no check asked a judge"


def test_the_scratch_sits_beside_the_trace(tmp_path: Path) -> None:
    directory, _ = layer(tmp_path, "checked")
    run_dir = directory / "traces" / "checked" / "run-1"
    assert sorted(path.name for path in run_dir.iterdir()) == [
        "checks.jsonl",
        "last_message.txt",
        "scratch",
        "trace.jsonl",
        "workspace",
    ]


def test_a_run_with_no_collected_artefacts_is_one_skip_per_check(tmp_path: Path) -> None:
    directory = suite(tmp_path, [case_entry("checked", [tmp_path / "gone"])])
    run = checked(directory).cases[0].arms.with_[0]
    appended = run.graders[1:]
    assert [(one.skipped, one.scored) for one in appended] == [(True, False)] * 4
    assert appended[0].skip_reason == (
        "the run kept no artefacts, so there is nothing to check. "
        "--no-keep-traces and eval.keep_traces: false both give up every check"
    )
    # A skip fails the run: it is out of the score, and the verdict fails on the skip itself.
    assert run.score == 1.0


def test_a_declared_case_produces_no_check_result(tmp_path: Path) -> None:
    directory = suite(tmp_path, [case_entry("checked", [], declared_reason="max_turns")])
    case = checked(directory).cases[0]
    assert case.graders == [WROTE_IT]
    assert case.arms.with_ == []


def two_arms(tmp_path: Path, aggregates: CaseAggregates, mean_delta: float | None) -> Path:
    """One case on both arms, its baseline failing the harness grader."""
    directory = tmp_path / "smoke"
    directory.mkdir(parents=True)
    entry = case_entry(
        "checked",
        collected_runs(directory, "checked", 1),
        without=collected_runs(directory, "checked-without", 1),
        aggregates=aggregates,
    )
    return suite(tmp_path, [entry], "with-without", mean_delta)


def test_every_arm_is_walked_and_the_delta_is_recomputed(tmp_path: Path) -> None:
    """The baseline run fails its grader and passes the four checks, so it scores 0.8."""
    harness = CaseAggregates(
        score=1.0, pass_rate=1.0, score_without=0.0, pass_rate_without=0.0, delta=1.0
    )
    directory = two_arms(tmp_path, harness, mean_delta=1.0)
    document = checked(directory)
    case = document.cases[0]
    assert case.arms.without is not None
    assert len(case.arms.without[0].graders) == 5
    assert (directory / "traces" / "checked-without" / "run-1" / checks.CHECKS_FILE).is_file()
    assert case.aggregates.score == 1.0
    assert case.aggregates.score_without == pytest.approx(0.8)
    assert case.aggregates.delta == pytest.approx(0.2)
    assert document.aggregates.mean_delta == pytest.approx(0.2)


def test_a_delta_the_harness_omitted_stays_omitted(tmp_path: Path) -> None:
    harness = CaseAggregates(score=1.0, pass_rate=1.0, pass_rate_without=0.0)
    directory = two_arms(tmp_path, harness, mean_delta=None)
    document = checked(directory)
    aggregates = document.cases[0].aggregates
    assert (aggregates.score_without, aggregates.delta) == (None, None)
    assert document.aggregates.mean_delta is None
    text = (directory / RESULT_NAME).read_text(encoding="utf-8")
    assert not [key for key in ('"scoreWithout"', '"delta"', '"meanDelta"') if key in text]


def test_a_document_that_cannot_be_read_is_silent(tmp_path: Path) -> None:
    directory = tmp_path / "smoke"
    directory.mkdir(parents=True)
    assert checks.run(directory, PLUGIN, judge_model="haiku") == []
    (directory / RESULT_NAME).write_text("not json", encoding="utf-8")
    assert checks.run(directory, PLUGIN, judge_model="haiku") == []


def test_a_judge_spend_is_added_to_the_run_and_to_the_document(tmp_path: Path) -> None:
    entry = run_entries([tmp_path])[0].model_copy(update={"cost_usd": 0.061})
    checks.add_spend(entry, 0.01)
    assert entry.cost_usd == 0.061
    assert entry.judge_cost_usd == pytest.approx(0.012)

    document = ResultDocument.read(suite(tmp_path, []) / RESULT_NAME)
    document.cost_usd = 0.061
    checks.add_spend(document, 0.01)
    assert document.cost_usd == pytest.approx(0.071)


def test_a_suite_with_no_check_anywhere_is_left_exactly_as_the_backend_wrote_it(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "smoke"
    directory.mkdir(parents=True)
    suite(tmp_path, [case_entry("noted", collected_runs(directory, "noted", 1))])
    before = (directory / RESULT_NAME).read_bytes()
    assert checks.run(directory, PLUGIN, judge_model="haiku") == []
    assert (directory / RESULT_NAME).read_bytes() == before
