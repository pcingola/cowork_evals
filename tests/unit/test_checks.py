"""The check layer over hand-written case trees and hand-written run directories.

The case tree and the collected run are under tests/data/checks/. The run directory is
copied into `tmp_path` before anything runs, because a check writes `scratch/` and the layer
writes `checks.jsonl` beside the three collected names, and a fixture directory is read and
never written. The discovery, the loader and the execution are the real ones, and every
expected value is a literal. No model, and no judge. See ../README.md.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from cowork_evals import checks
from cowork_evals.cases import read
from cowork_evals.checks import Check, CheckError, Result, Run
from cowork_evals.harness import RESULT_NAME

DATA = Path(__file__).resolve().parent.parent / "data" / "checks"
PLUGIN = DATA / "plugin"
CASES = PLUGIN / "evals" / "plugin"


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


def test_the_order_is_path_order_then_definition_order() -> None:
    found = checks.discover(CASES / "failing")
    assert [one.name.split(".")[1] for one in found] == [
        "returns_false",
        "returns_a_failed_result",
        "raises",
        "asserts",
        "names_a_file_that_is_not_there",
        "leaves_the_workspace",
        "returns_something_else",
    ]


def test_an_undecorated_function_is_not_a_check() -> None:
    assert "assertions.not_a_check" not in {one.name for one in checks.discover(CASES / "checked")}


def test_a_file_with_no_decorated_function_yields_nothing() -> None:
    assert checks.discover(CASES / "noted") == ()


def test_a_case_with_no_checks_directory_yields_nothing() -> None:
    assert checks.discover(DATA) == ()


def test_a_file_that_will_not_import_is_one_failed_check_named_for_the_file() -> None:
    found = checks.discover(CASES / "broken")
    assert len(found) == 1
    assert found[0].name == "unimportable"
    assert found[0].function is None
    assert found[0].error is not None
    assert "unimportable.py could not be imported: RuntimeError" in found[0].error
    assert "openpyxl is not installed" in found[0].error


def test_the_checks_directory_is_on_sys_path_only_while_the_files_load() -> None:
    before = list(sys.path)
    found = checks.discover(CASES / "checked")
    assert sys.path == before
    assert found  # the sibling import resolved while the directory was on the path


def test_a_sibling_a_check_file_imported_is_not_left_in_sys_modules() -> None:
    checks.discover(CASES / "checked")
    assert "helpers" not in sys.modules
    assert not [name for name in sys.modules if name.startswith("cowork_evals_check_")]


def test_two_cases_holding_one_file_name_get_two_module_names() -> None:
    first = checks._module_name(CASES / "checked" / "checks" / "helpers.py")
    second = checks._module_name(CASES / "noted" / "checks" / "helpers.py")
    assert first != second
    assert first.endswith("_helpers") and second.endswith("_helpers")


def test_a_duplicate_name_within_one_case_is_reported() -> None:
    path = CASES / "checked" / "checks" / "assertions.py"
    one = Check(name="assertions.same", path=path, function=lambda run: None)
    assert checks.duplicate_names((one, one)) == ["assertions.same"]
    assert checks.duplicate_names((one,)) == []


def test_the_case_reader_carries_the_check_files_in_path_order() -> None:
    case = read(CASES / "checked")
    assert [path.name for path in case.checks] == ["assertions.py", "helpers.py"]
    assert read(CASES / "broken").checks == (CASES / "broken" / "checks" / "unimportable.py",)


# The run a check reads.


def test_the_run_carries_what_the_collector_left(collected: Path) -> None:
    run = one_run(collected)
    assert run.workspace == collected / "workspace"
    assert run.trace == collected / "trace.jsonl"
    assert run.last_message == "WRITTEN\n"
    assert run.run_dir == collected
    assert run.case_dir == CASES / "checked"
    assert run.index == 1
    assert run.judge_model == "haiku"


def test_the_scratch_is_created_before_the_first_check(collected: Path) -> None:
    assert not (collected / "scratch").exists()
    run = one_run(collected)
    assert run.scratch == collected / "scratch"
    assert run.scratch.is_dir()


def test_the_scratch_is_shared_by_every_check_of_one_run(collected: Path) -> None:
    for one in checks.discover(CASES / "checked"):
        checks.execute(one, one_run(collected))
    assert [path.name for path in sorted((collected / "scratch").iterdir())] == ["note-1.txt"]


def test_a_run_with_no_last_message_reads_as_empty(collected: Path) -> None:
    (collected / "last_message.txt").unlink()
    assert one_run(collected).last_message == ""


def test_file_resolves_under_the_workspace(collected: Path) -> None:
    assert one_run(collected).file("written.txt") == collected / "workspace" / "written.txt"


def test_a_name_that_is_not_there_raises(collected: Path) -> None:
    with pytest.raises(CheckError) as raised:
        one_run(collected).file("absent.txt")
    assert str(raised.value) == "absent.txt is not in the workspace"


def test_a_name_that_leaves_the_workspace_raises(collected: Path) -> None:
    with pytest.raises(CheckError) as raised:
        one_run(collected).file("../trace.jsonl")
    assert str(raised.value) == "../trace.jsonl resolves outside the workspace"


# The judge over paths. Nothing here starts a process: the two refusals return before one.


def test_a_judge_call_naming_no_path_is_a_failed_check(collected: Path) -> None:
    result = one_run(collected).judge("Every slide carries a title.")
    assert result.passed is False
    assert result.explanation == checks.NO_PATHS


def test_a_judge_call_naming_a_path_that_is_not_there_is_a_failed_check(collected: Path) -> None:
    result = one_run(collected).judge("Every slide carries a title.", "scratch/deck.png")
    assert result.passed is False
    assert result.explanation == "scratch/deck.png is not there, so it cannot be judged"


# Execution.


def outcomes(case: str, collected: Path) -> dict[str, Any]:
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
    assert (
        found["names_a_file_that_is_not_there"].explanation == "absent.txt is not in the workspace"
    )
    assert (
        found["leaves_the_workspace"].explanation == "../trace.jsonl resolves outside the workspace"
    )
    assert found["returns_something_else"].explanation == (
        "the check returned int, and a check returns None, a bool or a Result"
    )


def test_an_exception_carries_its_traceback_and_a_check_error_does_not(collected: Path) -> None:
    found = outcomes("failing", collected)
    assert "ValueError: the workbook has no active sheet" in found["raises"].traceback
    assert "failures.py" in found["raises"].traceback
    assert found["names_a_file_that_is_not_there"].traceback is None


def test_a_failed_assert_carries_the_assertion(collected: Path) -> None:
    found = outcomes("failing", collected)
    assert found["asserts"].explanation.startswith("AssertionError")
    assert "assert run.last_message" in found["asserts"].traceback


def test_a_file_that_will_not_import_is_a_failed_check(collected: Path) -> None:
    one = checks.discover(CASES / "broken")[0]
    outcome = checks.execute(one, one_run(collected, "broken"))
    assert outcome.name == "unimportable"
    assert outcome.passed is False
    assert "could not be imported" in outcome.explanation


def test_nothing_raises_out_of_the_module(collected: Path) -> None:
    for case in ("checked", "failing", "broken"):
        for one in checks.discover(CASES / case):
            assert checks.execute(one, one_run(collected, case)).duration_seconds >= 0


def test_a_skip_is_a_failed_unscored_check() -> None:
    one = Check(name="assertions.x", path=Path("x.py"), function=lambda run: None)
    outcome = checks.skipped(one, checks.NO_ARTEFACTS)
    assert outcome.passed is False
    assert outcome.skipped is True
    assert outcome.skip_reason == checks.NO_ARTEFACTS
    assert checks.grader_result(outcome)["scored"] is False


def test_a_result_carries_two_fields_and_nothing_else() -> None:
    assert [field for field in Result.__dataclass_fields__] == ["passed", "explanation"]
    assert Result(passed=True).explanation == ""


def test_the_line_one_check_writes(collected: Path) -> None:
    found = outcomes("failing", collected)
    line = json.loads(json.dumps(found["returns_false"].document()))
    assert line["name"] == "failures.returns_false"
    assert line["passed"] is False
    assert line["explanation"] == "the check returned False"
    assert line["durationSeconds"] >= 0
    assert "traceback" not in line
    assert "judge" not in line


# Advisory checks. docs/checks.md.


def test_an_advisory_failure_keeps_its_verdict_and_moves_no_score(
    tmp_path: Path, collected: Path
) -> None:
    case = tmp_path / "case"
    (case / "checks").mkdir(parents=True)
    (case / "checks" / "a.py").write_text(
        "from cowork_evals.checks import Result, Run, check\n\n"
        "@check\ndef plain(run: Run) -> None:\n    return None\n\n"
        "@check(advisory=True)\ndef advised(run: Run) -> Result:\n"
        "    return Result(passed=False, explanation='the judge said FAIL')\n"
    )
    found = checks.discover(case)
    assert {one.name: one.advisory for one in found} == {"a.plain": False, "a.advised": True}

    results = [
        checks.grader_result(checks.execute(one, checks.build_run(collected, case, 1, "haiku")))
        for one in found
    ]
    assert [entry["passed"] for entry in results] == [True, False]
    assert [entry["scored"] for entry in results] == [True, False]
    assert results[1]["explanation"] == "the judge said FAIL"
    assert checks.score({"graders": results}) == 1.0


# The layer: what it appends to the document, and what it writes beside the trace.


def collected_runs(directory: Path, case: str, count: int) -> list[Path]:
    """`count` collected run directories for one case, each a copy of the fixture run."""
    made = []
    for index in range(1, count + 1):
        run_dir = directory / "traces" / case / f"run-{index}"
        shutil.copytree(DATA / "run", run_dir)
        made.append(run_dir)
    return made


def case_entry(
    name: str, where: str, runs: list[Path], *, passed: bool = True, **extra: Any
) -> dict[str, Any]:
    """One case of a v1 document, its one `file_exists` grader passing or not before any check."""
    return {
        "name": name,
        "dir": where,
        "source": "prose",
        "promptMarkdown": "Write WRITTEN into written.txt.",
        "graders": [{"name": "wrote-it", "type": "file_exists", "weight": 1, "config": {}}],
        "arms": {
            "with": [
                {
                    "score": float(passed),
                    "passed": passed,
                    "turns": 1,
                    "costUsd": 0.01,
                    "judgeCostUsd": 0.002,
                    "error": None,
                    "skippedPaidGraders": False,
                    "tracePath": str(run_dir / "trace.jsonl"),
                    "graders": [
                        {
                            "name": "wrote-it",
                            "passed": passed,
                            "weight": 1,
                            "explanation": "created written.txt",
                            "withOnly": False,
                            "scored": True,
                        }
                    ],
                }
                for run_dir in runs
            ]
        },
        "aggregates": {"score": 1.0, "passRate": 1.0},
        **extra,
    }


def suite(
    tmp_path: Path, cases: list[dict[str, Any]], ablation: str = "none", **aggregates: Any
) -> Path:
    """One plugin's output directory, holding the document those cases make up."""
    directory = tmp_path / "smoke"
    directory.mkdir(parents=True, exist_ok=True)
    document = {
        "schemaVersion": 1,
        "claudeVersion": "2.1.270",
        "startedAt": "2026-09-13T10:00:00+00:00",
        "durationSeconds": 3.0,
        "costUsd": 0.02,
        "partial": False,
        "suite": {
            "root": str(PLUGIN),
            "ablation": ablation,
            "threshold": 0,
            "judgeModel": "haiku",
            "plugins": [{"name": "smoke", "path": str(PLUGIN)}],
        },
        "cases": cases,
        "aggregates": {
            "casesTotal": len(cases),
            "casesPassed": len(cases),
            "overallScore": 1.0,
            "overallPassRate": 1.0,
            **aggregates,
        },
    }
    (directory / RESULT_NAME).write_text(json.dumps(document, indent=2), encoding="utf-8")
    return directory


def rerun(directory: Path) -> dict[str, Any]:
    return json.loads((directory / RESULT_NAME).read_text(encoding="utf-8"))


def layer(tmp_path: Path, case: str, count: int = 1, **extra: Any) -> tuple[Path, dict[str, Any]]:
    """Run the layer over one case of one plugin, and return the directory and the document."""
    directory = tmp_path / "smoke"
    directory.mkdir(parents=True, exist_ok=True)
    runs = collected_runs(directory, case, count)
    suite(tmp_path, [case_entry(case, f"evals/plugin/{case}", runs, **extra)])
    assert checks.run(directory, PLUGIN, judge_model="haiku") == []
    return directory, rerun(directory)


def one(document: dict[str, Any], index: int = 0) -> dict[str, Any]:
    return document["cases"][0]["arms"]["with"][index]


def test_each_definition_is_appended_to_the_case_with_type_check(tmp_path: Path) -> None:
    _, document = layer(tmp_path, "checked")
    assert document["cases"][0]["graders"] == [
        {"name": "wrote-it", "type": "file_exists", "weight": 1, "config": {}},
        {"name": "assertions.the_file_says_written", "type": "check", "weight": 1, "config": {}},
        {
            "name": "assertions.the_sibling_is_importable",
            "type": "check",
            "weight": 1,
            "config": {},
        },
        {"name": "assertions.the_last_message_is_read", "type": "check", "weight": 1, "config": {}},
        {"name": "assertions.the_scratch_is_writable", "type": "check", "weight": 1, "config": {}},
    ]


def test_each_result_is_appended_to_the_run(tmp_path: Path) -> None:
    _, document = layer(tmp_path, "checked")
    assert one(document)["graders"][1] == {
        "name": "assertions.the_file_says_written",
        "passed": True,
        "weight": 1,
        "explanation": "the check raised nothing",
        "withOnly": False,
        "scored": True,
    }


def test_a_passing_case_keeps_its_score(tmp_path: Path) -> None:
    _, document = layer(tmp_path, "checked")
    assert one(document)["score"] == 1.0
    assert one(document)["passed"] is True
    assert document["cases"][0]["aggregates"] == {"score": 1.0, "passRate": 1.0}


def test_a_failed_check_drops_the_run_score_and_the_case_aggregates(tmp_path: Path) -> None:
    _, document = layer(tmp_path, "failing")
    # One passing grader and seven failed checks.
    assert one(document)["score"] == 1 / 8
    assert one(document)["passed"] is False
    assert document["cases"][0]["aggregates"] == {"score": 1 / 8, "passRate": 0.0}


def test_the_pass_rate_is_over_the_runs_of_the_case(tmp_path: Path) -> None:
    _, document = layer(tmp_path, "checked", count=3)
    assert [entry["passed"] for entry in document["cases"][0]["arms"]["with"]] == [True] * 3
    assert document["cases"][0]["aggregates"]["passRate"] == 1.0


def test_every_run_of_a_case_runs_every_check_again(tmp_path: Path) -> None:
    directory, document = layer(tmp_path, "checked", count=2)
    for index in (0, 1):
        assert len(one(document, index)["graders"]) == 5
    for index in (1, 2):
        scratch = directory / "traces" / "checked" / f"run-{index}" / "scratch"
        assert [path.name for path in scratch.iterdir()] == [f"note-{index}.txt"]


def test_the_checks_file_is_written_beside_the_trace(tmp_path: Path) -> None:
    directory, _ = layer(tmp_path, "failing")
    path = directory / "traces" / "failing" / "run-1" / checks.CHECKS_FILE
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [line["name"] for line in lines] == [
        "failures.returns_false",
        "failures.returns_a_failed_result",
        "failures.raises",
        "failures.asserts",
        "failures.names_a_file_that_is_not_there",
        "failures.leaves_the_workspace",
        "failures.returns_something_else",
    ]
    assert all(line["passed"] is False for line in lines)
    assert "traceback" in lines[2]
    assert "traceback" not in lines[4]


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


def test_a_case_with_no_checks_is_untouched(tmp_path: Path) -> None:
    _, document = layer(tmp_path, "noted")
    assert document["cases"][0]["graders"] == [
        {"name": "wrote-it", "type": "file_exists", "weight": 1, "config": {}}
    ]
    assert len(one(document)["graders"]) == 1
    assert document["costUsd"] == 0.02


def test_a_run_with_no_collected_artefacts_is_one_skip_per_check(tmp_path: Path) -> None:
    directory = tmp_path / "smoke"
    directory.mkdir(parents=True)
    entry = case_entry("checked", "evals/plugin/checked", [tmp_path / "gone"])
    suite(tmp_path, [entry])
    assert checks.run(directory, PLUGIN, judge_model="haiku") == []
    document = rerun(directory)
    appended = one(document)["graders"][1:]
    assert len(appended) == 4
    assert all(result["skipped"] is True for result in appended)
    assert all(result["scored"] is False for result in appended)
    assert appended[0]["skipReason"] == checks.NO_ARTEFACTS
    # A skip fails the run: it is out of the score, and the verdict fails on the skip itself.
    assert one(document)["score"] == 1.0


def test_a_declared_case_produces_no_check_result(tmp_path: Path) -> None:
    directory = tmp_path / "smoke"
    directory.mkdir(parents=True)
    entry = case_entry("checked", "evals/plugin/checked", [])
    entry["arms"] = {"with": []}
    entry["declaredUnrunnable"] = True
    entry["declaredReason"] = "max_turns"
    suite(tmp_path, [entry])
    assert checks.run(directory, PLUGIN, judge_model="haiku") == []
    document = rerun(directory)
    assert document["cases"][0]["graders"] == [
        {"name": "wrote-it", "type": "file_exists", "weight": 1, "config": {}}
    ]
    assert document["cases"][0]["arms"]["with"] == []


def test_every_arm_is_walked(tmp_path: Path) -> None:
    """The baseline arm's runs are collected like any other, so the checks reach them too."""
    directory = tmp_path / "smoke"
    directory.mkdir(parents=True)
    runs = collected_runs(directory, "checked", 1)
    without = collected_runs(directory, "checked-without", 1)
    entry = case_entry("checked", "evals/plugin/checked", runs)
    entry["arms"]["without"] = case_entry("checked", "evals/plugin/checked", without)["arms"][
        "with"
    ]
    suite(tmp_path, [entry])
    assert checks.run(directory, PLUGIN, judge_model="haiku") == []
    document = rerun(directory)
    assert len(one(document)["graders"]) == 5
    assert len(document["cases"][0]["arms"]["without"][0]["graders"]) == 5
    assert (directory / "traces" / "checked-without" / "run-1" / checks.CHECKS_FILE).is_file()


def two_arms(tmp_path: Path, aggregates: dict[str, Any], **suite_aggregates: Any) -> dict[str, Any]:
    """One case on both arms, its baseline failing the harness grader, after the layer ran."""
    directory = tmp_path / "smoke"
    directory.mkdir(parents=True)
    where = "evals/plugin/checked"
    without = collected_runs(directory, "checked-without", 1)
    entry = case_entry(
        "checked", where, collected_runs(directory, "checked", 1), aggregates=aggregates
    )
    entry["arms"]["without"] = case_entry("checked", where, without, passed=False)["arms"]["with"]
    suite(tmp_path, [entry], "with-without", **suite_aggregates)
    assert checks.run(directory, PLUGIN, judge_model="haiku") == []
    return rerun(directory)


def test_the_baseline_numbers_and_the_delta_are_recomputed(tmp_path: Path) -> None:
    harness = {"score": 1.0, "passRate": 1.0, "scoreWithout": 0.0, "passRateWithout": 0.0}
    document = two_arms(tmp_path, {**harness, "delta": 1.0}, meanDelta=1.0)
    case = document["cases"][0]
    aggregates = case["aggregates"]
    without = case["arms"]["without"][0]
    assert len(without["graders"]) == len(case["arms"]["with"][0]["graders"])
    assert aggregates["scoreWithout"] == without["score"]
    assert aggregates["delta"] == aggregates["score"] - aggregates["scoreWithout"]
    assert document["aggregates"]["meanDelta"] == aggregates["delta"]


def test_a_delta_the_harness_omitted_stays_omitted(tmp_path: Path) -> None:
    document = two_arms(tmp_path, {"score": 1.0, "passRate": 1.0, "passRateWithout": 0.0})
    aggregates = document["cases"][0]["aggregates"]
    assert "scoreWithout" not in aggregates
    assert "delta" not in aggregates
    assert "meanDelta" not in document["aggregates"]


def test_a_document_that_cannot_be_read_is_silent(tmp_path: Path) -> None:
    directory = tmp_path / "smoke"
    directory.mkdir(parents=True)
    assert checks.run(directory, PLUGIN, judge_model="haiku") == []
    (directory / RESULT_NAME).write_text("not json", encoding="utf-8")
    assert checks.run(directory, PLUGIN, judge_model="haiku") == []


def test_the_spend_of_a_case_with_no_judge_call_is_nothing(tmp_path: Path) -> None:
    _, document = layer(tmp_path, "checked")
    assert document["costUsd"] == 0.02
    assert one(document)["judgeCostUsd"] == 0.002


def test_a_judge_spend_is_added_to_the_run_and_to_the_document() -> None:
    entry = {"costUsd": 0.061, "judgeCostUsd": 0.002}
    checks.add_spend(entry, 0.01)
    assert entry == {"costUsd": 0.061, "judgeCostUsd": 0.012}

    document = {"costUsd": 0.061}
    checks.add_spend(document, 0.01, checks.SUITE_SPEND)
    assert document == {"costUsd": 0.071}


def test_a_check_that_asked_no_judge_adds_nothing() -> None:
    entry = {"judgeCostUsd": 0.002}
    checks.add_spend(entry, 0.0)
    assert entry == {"judgeCostUsd": 0.002}


def test_a_judged_check_keeps_the_whole_exchange_in_its_line() -> None:
    call = checks.JudgeCall(
        prompt="the whole prompt", replies=("PASS", "FAIL", "PASS"), cost_usd=0.01
    )
    outcome = checks.Outcome(
        name="assertions.deck_is_readable",
        passed=True,
        explanation="judge votes: PASS FAIL PASS",
        calls=(call,),
        cost_usd=0.01,
    )
    line = outcome.document()
    assert line["judge"] == [
        {"prompt": "the whole prompt", "replies": ["PASS", "FAIL", "PASS"], "costUsd": 0.01}
    ]
    assert line["costUsd"] == 0.01


def test_the_suite_means_are_recomputed_over_the_case_aggregates(tmp_path: Path) -> None:
    _, document = layer(tmp_path, "failing")
    assert document["aggregates"]["overallScore"] == 1 / 8
    assert document["aggregates"]["overallPassRate"] == 0.0
    # `--threshold` is 0, so every case counts as passed there whatever a check said.
    assert document["aggregates"]["casesTotal"] == 1
    assert document["aggregates"]["casesPassed"] == 1


def test_a_suite_with_no_check_anywhere_is_left_exactly_as_the_backend_wrote_it(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "smoke"
    directory.mkdir(parents=True)
    runs = collected_runs(directory, "noted", 1)
    suite(tmp_path, [case_entry("noted", "evals/plugin/noted", runs)])
    before = (directory / RESULT_NAME).read_bytes()
    assert checks.run(directory, PLUGIN, judge_model="haiku") == []
    assert (directory / RESULT_NAME).read_bytes() == before
