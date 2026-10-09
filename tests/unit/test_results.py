"""The v1 result document, built from hand-written cases and session documents.

Every expected value is a literal, and nothing here runs a case or asks a judge. The
contract is docs/claude_code/plugin_eval_reference.md, and what this backend adds to it is
docs/cowork_backend.md. See ../README.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cowork_evals.cases import Case, Grader, ToolUsedConfig, read
from cowork_evals.grader import GraderResult
from cowork_evals.harness import RESULT_NAME
from cowork_evals.results import CaseResult, Run, build, write

DATA = Path(__file__).resolve().parent.parent / "data"
TREE = DATA / "cases" / "tree"
CASE_DIR = TREE / "evals" / "greeter" / "every-key"

STARTED = "2026-09-09T10:00:00+00:00"
VERSION = "2.1.265"


def session(name: str) -> dict[str, Any]:
    loaded = json.loads((DATA / "documents" / f"{name}.json").read_text(encoding="utf-8"))
    loaded["session_dir"] = str(DATA / "documents" / loaded["session_dir"])
    return loaded


def result(name: str, passed: bool, weight: int | float = 1, **extra: Any) -> GraderResult:
    return GraderResult(
        name=name, passed=passed, weight=weight, explanation=f"{name} {passed}", **extra
    )


def case(name: str, **frontmatter: Any) -> Case:
    return Case(
        name=name,
        directory=TREE / "evals" / "greeter" / name,
        prompt=f"The prompt of {name}.",
        graders=(),
        tags=("greeter",),
        source="prose",
        frontmatter_keys={"name": name, **frontmatter},
        path=TREE / "evals" / "greeter" / name / "prompt.md",
    )


def suite(cases: list[CaseResult], **kwargs: Any) -> dict[str, Any]:
    return build(
        root=TREE,
        cases=cases,
        started_at=STARTED,
        duration_seconds=91.5,
        judge_model="haiku",
        claude_version=VERSION,
        **kwargs,
    )


# The run.


def test_a_run_is_built_from_the_session_document() -> None:
    run = Run.collected(session("answered"), (result("g", True),), timeout_seconds=1800.0)
    entry = run.document()
    assert entry["turns"] == 1, "one assistant turn"
    assert entry["startedAt"] == "2026-09-09T10:00:00.000Z"
    assert entry["durationSeconds"] == 120.0
    assert entry["tracePath"].endswith("t-0001.jsonl")
    assert entry["error"] is None
    assert entry["skippedPaidGraders"] is False
    assert entry["cowork"] == {"sessionDir": run.session_dir, "timeoutSeconds": 1800.0}


def test_a_session_with_no_timestamp_and_no_transcript_omits_three_fields() -> None:
    document = session("quiet")
    document["submitted_at"] = None
    entry = Run.collected(document, (), timeout_seconds=300.0).document()
    assert "startedAt" not in entry
    assert "durationSeconds" not in entry
    assert "tracePath" not in entry
    assert entry["error"] is None, "only error is nullable"


def test_the_score_is_the_weighted_fraction_of_scored_graders() -> None:
    run = Run(graders=(result("a", True, 3), result("b", False, 1)))
    assert run.score == 0.75
    assert run.passed is False
    assert Run(graders=(result("a", True), result("b", True))).passed is True


def test_a_skipped_grader_is_not_scored() -> None:
    run = Run(
        graders=(
            result("a", True),
            result("b", False, skipped=True, skip_reason="no stand-in serves a CoWork run"),
        )
    )
    assert run.score == 1.0
    assert run.passed is True
    entry = run.document()["graders"]
    assert entry[0]["scored"] is True
    assert entry[1] == {
        "name": "b",
        "passed": False,
        "weight": 1,
        "explanation": "b False",
        "withOnly": False,
        "scored": False,
        "skipped": True,
        "skipReason": "no stand-in serves a CoWork run",
    }


def test_a_run_with_nothing_to_score_is_zero() -> None:
    assert Run(graders=()).score == 0.0
    assert Run(graders=()).passed is False


def test_with_only_is_always_false() -> None:
    """`ablation` is `none` here, so nothing is dropped for an arm."""
    entry = Run(graders=(result("a", True),)).document()
    assert entry["graders"][0]["withOnly"] is False


def test_a_judged_grader_result_carries_its_votes_and_evidence() -> None:
    judged = result("tone", True, judge_votes=(True, False, True), evidence="Hello Alex.")
    entry = Run(graders=(judged,)).document()["graders"][0]
    assert entry["judgeVotes"] == [True, False, True]
    assert entry["evidence"] == "Hello Alex."


# The case.


def test_a_case_records_what_it_declared_and_never_an_override() -> None:
    real = read(CASE_DIR)
    entry = CaseResult(case=real, runs=(Run(graders=(result("a", True),), timeout_seconds=60),))
    document = entry.document(TREE.resolve())
    assert document["name"] == "greets-alex"
    assert document["dir"] == "evals/greeter/every-key"
    assert document["source"] == "prose"
    assert document["promptMarkdown"] == "Say hello to Alex."
    assert document["runsPerCase"] == 2
    assert document["timeoutSeconds"] == 600
    assert document["maxTurns"] == 12
    assert document["model"] == "sonnet"
    assert document["arms"]["with"][0]["cowork"]["timeoutSeconds"] == 60
    assert "without" not in document["arms"]


def test_a_case_that_declares_none_of_the_four_omits_them() -> None:
    document = CaseResult(case=case("bare")).document(TREE.resolve())
    for absent in ("model", "runsPerCase", "timeoutSeconds", "maxTurns"):
        assert absent not in document


def test_a_grader_definition_fills_in_the_defaults_the_grader_applies() -> None:
    definitions = CaseResult(case=read(CASE_DIR)).document(TREE.resolve())["graders"]
    by_name = {entry["name"]: entry for entry in definitions}
    assert by_name["mentions-alex"] == {
        "name": "mentions-alex",
        "type": "regex",
        "weight": 2,
        "config": {"target": "last_message", "pattern": "Alex", "flags": "", "match": "contains"},
    }
    assert by_name["tone"]["graderMarkdown"] == "The reply is warm and personal."
    assert by_name["tone"]["config"] == {
        "focus": "last_message",
        "criteria": "The reply is warm and personal.",
    }


def test_case_aggregates_are_the_mean_score_and_the_pass_rate() -> None:
    disagreeing = CaseResult(
        case=case("flaky", runs=2),
        runs=(
            Run(graders=(result("a", True), result("b", True))),
            Run(graders=(result("a", True), result("b", False))),
        ),
    )
    assert disagreeing.score == 0.75
    assert disagreeing.pass_rate == 0.5
    assert disagreeing.document(TREE.resolve())["aggregates"] == {"score": 0.75, "passRate": 0.5}


def test_a_declared_case_submits_nothing_and_carries_its_reason() -> None:
    reason = "no-cowork: max_turns: no turn cap reaches a CoWork session"
    unrunnable = CaseResult(
        case=case("staged", max_turns=12), declared=True, declared_reason=reason
    )
    document = unrunnable.document(TREE.resolve())
    assert document["declaredUnrunnable"] is True
    assert document["declaredReason"] == reason
    assert "skipped" not in document, "a declared case is not a skipped one"
    assert document["arms"]["with"] == []
    assert document["aggregates"] == {"score": 0.0, "passRate": 0.0}
    assert "score" not in document, "a case has no score of its own in v1"
    assert "passed" not in document


def test_a_run_the_driver_raised_on_carries_the_error_and_no_graders() -> None:
    errored = CaseResult(
        case=case("errored"),
        runs=(Run(error="4: no session directory appeared", timeout_seconds=1800.0),),
    )
    entry = errored.document(TREE.resolve())["arms"]["with"][0]
    assert entry["error"] == "4: no session directory appeared"
    assert entry["score"] == 0.0
    assert entry["graders"] == []


# The suite.


def test_the_suite_document(tmp_path: Path) -> None:
    passing = CaseResult(case=case("passes"), runs=(Run(graders=(result("a", True),)),))
    failing = CaseResult(case=case("fails"), runs=(Run(graders=(result("a", False),)),))
    document = suite([passing, failing], case_filter="pass*", tag_filters=("greeter",))

    assert document["schemaVersion"] == 1
    assert document["claudeVersion"] == VERSION
    assert document["startedAt"] == STARTED
    assert document["durationSeconds"] == 91.5
    assert document["partial"] is False
    assert "partialReason" not in document
    assert document["suite"] == {
        "root": str(TREE.resolve()),
        "ablation": "none",
        "threshold": 0,
        "judgeModel": "haiku",
        "plugins": [{"name": "reader-fixture", "path": str(TREE.resolve()), "version": "0.0.1"}],
        "caseFilter": "pass*",
        "tagFilters": ["greeter"],
    }
    assert document["aggregates"] == {
        "casesTotal": 2,
        "casesPassed": 2,
        "overallScore": 0.5,
        "overallPassRate": 0.5,
    }
    assert "meanDelta" not in document["aggregates"]


def test_the_suite_cost_is_the_judge_spend_alone() -> None:
    cases = [
        CaseResult(case=case("one"), runs=(Run(judge_cost_usd=0.004),)),
        CaseResult(case=case("two"), runs=(Run(judge_cost_usd=0.002), Run(judge_cost_usd=0.001))),
    ]
    assert suite(cases)["costUsd"] == pytest.approx(0.007)


def test_a_declared_case_leaves_all_four_aggregates() -> None:
    """It is in `cases`, and out of `casesTotal`, `casesPassed` and both means."""
    cases = [
        CaseResult(case=case("runs"), runs=(Run(graders=(result("a", True),)),)),
        CaseResult(case=case("declared"), declared=True, declared_reason="no-cowork"),
    ]
    document = suite(cases)
    assert len(document["cases"]) == 2
    assert document["aggregates"] == {
        "casesTotal": 1,
        "casesPassed": 1,
        "overallScore": 1.0,
        "overallPassRate": 1.0,
    }


def test_a_suite_of_nothing_but_declared_cases_reports_no_case_at_all() -> None:
    """The same four numbers a suite of no cases reports."""
    only = CaseResult(case=case("declared"), declared=True, declared_reason="no-cowork")
    document = suite([only])
    assert document["aggregates"] == {
        "casesTotal": 0,
        "casesPassed": 0,
        "overallScore": 0.0,
        "overallPassRate": 0.0,
    }


def test_a_selection_that_matched_no_case_divides_by_nothing() -> None:
    document = suite([])
    assert document["cases"] == []
    assert document["aggregates"] == {
        "casesTotal": 0,
        "casesPassed": 0,
        "overallScore": 0.0,
        "overallPassRate": 0.0,
    }


def test_no_filter_omits_both_filter_fields() -> None:
    assert "caseFilter" not in suite([])["suite"]
    assert "tagFilters" not in suite([])["suite"]


def test_the_document_is_written_under_the_one_name(tmp_path: Path) -> None:
    path = write(tmp_path, suite([]))
    assert path == tmp_path / RESULT_NAME
    assert json.loads(path.read_text(encoding="utf-8"))["schemaVersion"] == 1


def test_the_document_is_json_serializable_with_a_real_case() -> None:
    entry = CaseResult(
        case=read(CASE_DIR),
        runs=(Run.collected(session("answered"), (result("a", True),), timeout_seconds=1800.0),),
    )
    json.dumps(suite([entry]))


def test_a_plugin_with_no_readable_manifest_falls_back_to_the_folder_name(
    tmp_path: Path,
) -> None:
    document = build(
        root=tmp_path / "nameless",
        cases=[],
        started_at=STARTED,
        duration_seconds=0.0,
        judge_model="haiku",
        claude_version=VERSION,
    )
    assert document["suite"]["plugins"] == [
        {"name": "nameless", "path": str((tmp_path / "nameless").resolve())}
    ]


def test_a_grader_definition_needs_no_case_on_disk() -> None:
    grader = Grader(
        name="no-web",
        type="tool_used",
        weight=1,
        config=ToolUsedConfig(tool="WebFetch", min=0, max=0),
        markdown="",
        path=Path("no-web.md"),
    )
    entry = Case(
        name="guard",
        directory=TREE / "evals" / "greeter" / "guard",
        prompt="Answer without the web.",
        graders=(grader,),
        tags=(),
        source="prose",
        frontmatter_keys={},
        path=TREE / "evals" / "greeter" / "guard" / "prompt.md",
    )
    definition = CaseResult(case=entry).document(TREE.resolve())["graders"][0]
    assert definition["config"] == {"tool": "WebFetch", "min": 0, "max": 0}
    assert "graderMarkdown" not in definition
