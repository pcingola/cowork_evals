"""The v1 result document, built from hand-written cases and session documents.

Every expected value is a literal, and nothing here runs a case or asks a judge. The
contract is docs/claude_code/plugin_eval_reference.md, and what this backend adds to it is
docs/cowork_backend.md. See ../README.md.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from cowork_evals.cases import (
    Case,
    Grader,
    GraderConfig,
    LlmGraderConfig,
    PromptFrontmatter,
    RegexConfig,
    ToolUsedConfig,
    read,
)
from cowork_evals.cowork import SessionDocument
from cowork_evals.grader import GraderResult
from cowork_evals.harness import RESULT_NAME
from cowork_evals.results import (
    CaseAggregates,
    CaseEntry,
    CoWorkRef,
    PluginRef,
    ResultDocument,
    RunEntry,
    SuiteAggregates,
    SuiteInfo,
    build,
    spend,
    write,
)

DATA = Path(__file__).resolve().parent.parent / "data"
TREE = DATA / "cases" / "tree"
ROOT = TREE.resolve()
CASE_DIR = TREE / "evals" / "greeter" / "every-key"

STARTED = "2026-09-09T10:00:00+00:00"
VERSION = "2.1.265"


def result(name: str, passed: bool, weight: int | float = 1, **extra: Any) -> GraderResult:
    return GraderResult(
        name=name, passed=passed, weight=weight, explanation=f"{name} {passed}", **extra
    )


def case(name: str, graders: tuple[Grader, ...] = (), **frontmatter: Any) -> Case:
    declared = PromptFrontmatter(name=name, **frontmatter)
    return Case(
        name=name,
        directory=TREE / "evals" / "greeter" / name,
        prompt=f"The prompt of {name}.",
        graders=graders,
        tags=("greeter",),
        source="prose",
        frontmatter_keys=declared.model_dump(exclude_unset=True),
        path=TREE / "evals" / "greeter" / name / "prompt.md",
    )


def ran(name: str, *graders: GraderResult) -> CaseEntry:
    return CaseEntry.build(case(name), ROOT, (RunEntry.graded(graders),))


def suite(cases: list[CaseEntry], **kwargs: Any) -> ResultDocument:
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


RECORDED = ("2026-09-09T10:00:00.000Z", 120.0, "session/.claude/projects/session/t-0001.jsonl")


@pytest.mark.parametrize(
    ("update", "fields", "absent"),
    [
        ({}, RECORDED, set()),
        (
            {"submitted_at": None, "transcript": None},
            (None, None, None),
            {"startedAt", "durationSeconds", "tracePath"},
        ),
    ],
)
def test_a_run_is_built_from_the_session_document(
    answered: SessionDocument, update: dict[str, None], fields: tuple[Any, ...], absent: set[str]
) -> None:
    """A session with no timestamp and no transcript omits three fields. Only `error` is
    written as null."""
    session = answered.model_copy(update=update)
    run = RunEntry.collected(session, (result("g", True),), timeout_seconds=1800.0)
    assert run.turns == 1, "one assistant turn"
    assert run.error is None
    assert run.skipped_paid_graders is False
    assert run.cowork == CoWorkRef(
        session_dir=str(DATA / "documents" / "session"), timeout_seconds=1800.0
    )
    assert (run.started_at, run.duration_seconds, run.trace_path) == fields
    written = run.model_dump(mode="json", by_alias=True)
    assert written["error"] is None
    assert {"startedAt", "durationSeconds", "tracePath"} - written.keys() == absent


@pytest.mark.parametrize(
    ("graders", "score", "passed"),
    [
        ((result("a", True, 3), result("b", False, 1)), 0.75, False),
        ((result("a", True), result("b", True)), 1.0, True),
        ((result("a", True), result("b", False, skipped=True, skip_reason="none")), 1.0, True),
        ((), 0.0, False),
    ],
)
def test_the_score_is_the_weighted_fraction_of_scored_graders(
    graders: tuple[GraderResult, ...], score: float, passed: bool
) -> None:
    run = RunEntry.graded(graders)
    assert (run.score, run.passed) == (score, passed)


@pytest.mark.parametrize(
    ("grader", "written"),
    [
        (
            result("b", False, skipped=True, skip_reason="no stand-in serves a CoWork run"),
            '{"name":"b","passed":false,"weight":1,"explanation":"b False","withOnly":false,'
            '"scored":false,"skipped":true,"skipReason":"no stand-in serves a CoWork run"}',
        ),
        (
            result("tone", True, judge_votes=[True, False, True], evidence="Hello Alex."),
            '{"name":"tone","passed":true,"weight":1,"explanation":"tone True","withOnly":false,'
            '"scored":true,"judgeVotes":[true,false,true],"evidence":"Hello Alex."}',
        ),
    ],
)
def test_a_grader_result_is_written_with_the_reference_keys(
    grader: GraderResult, written: str
) -> None:
    assert grader.model_dump_json(by_alias=True) == written


# The case.


@pytest.mark.parametrize(
    ("entry", "identity", "four"),
    [
        (
            read(CASE_DIR),
            ("greets-alex", "evals/greeter/every-key", "prose", "Say hello to Alex."),
            ("sonnet", 2, 600, 12),
        ),
        (
            case("bare"),
            ("bare", "evals/greeter/bare", "prose", "The prompt of bare."),
            (None, None, None, None),
        ),
    ],
)
def test_a_case_records_what_it_declared_and_never_an_override(
    entry: Case, identity: tuple[str, ...], four: tuple[Any, ...]
) -> None:
    """What it declared, not what ran: the run's own timeout is in its `cowork` object. A
    key it did not declare is absent from the written entry."""
    runs = (RunEntry.graded((result("a", True),), timeout_seconds=60),)
    built = CaseEntry.build(entry, ROOT, runs)
    assert (built.name, built.dir, built.source, built.prompt_markdown) == identity
    assert (built.model, built.runs_per_case, built.timeout_seconds, built.max_turns) == four
    assert built.arms.with_[0].cowork == CoWorkRef(timeout_seconds=60)
    assert built.arms.without is None
    written = built.model_dump(by_alias=True).keys()
    keys = ("model", "runsPerCase", "timeoutSeconds", "maxTurns")
    assert [key in written for key in keys] == [value is not None for value in four]


@pytest.mark.parametrize(
    ("name", "weight", "markdown", "config"),
    [
        (
            "mentions-alex",
            2,
            None,
            RegexConfig(target="last_message", pattern="Alex", flags="", match="contains"),
        ),
        (
            "tone",
            1,
            "The reply is warm and personal.",
            LlmGraderConfig(focus="last_message", criteria="The reply is warm and personal."),
        ),
        ("no-web", 1, None, ToolUsedConfig(tool="WebFetch", min=0, max=0)),
    ],
)
def test_a_grader_definition_fills_in_the_defaults_the_grader_applies(
    grader: Callable[..., Grader],
    name: str,
    weight: int,
    markdown: str | None,
    config: GraderConfig,
) -> None:
    """`no-web` is a case built in memory: a definition needs no case on disk, and only
    `llm` and `baseline` carry `graderMarkdown`."""
    no_web = grader("tool_used", ToolUsedConfig(tool="WebFetch", min=0, max=0), name="no-web")
    cases = [read(CASE_DIR), case("guard", graders=(no_web,))]
    definitions = [d for entry in cases for d in CaseEntry.build(entry, ROOT).graders]
    (definition,) = [d for d in definitions if d.name == name]
    assert (definition.weight, definition.grader_markdown, definition.config) == (
        weight,
        markdown,
        config,
    )


def test_case_aggregates_are_the_mean_score_and_the_pass_rate() -> None:
    disagreeing = CaseEntry.build(
        case("flaky", runs=2),
        ROOT,
        (
            RunEntry.graded((result("a", True), result("b", True))),
            RunEntry.graded((result("a", True), result("b", False))),
        ),
    )
    assert disagreeing.aggregates == CaseAggregates(score=0.75, pass_rate=0.5)


def test_a_declared_case_submits_nothing_and_carries_its_reason() -> None:
    reason = "no-cowork: max_turns: no turn cap reaches a CoWork session"
    unrunnable = CaseEntry.build(case("staged", max_turns=12), ROOT, declared_reason=reason)
    assert unrunnable.declared_unrunnable is True
    assert unrunnable.declared_reason == reason
    assert unrunnable.skipped is False, "a declared case is not a skipped one"
    assert unrunnable.arms.with_ == []
    assert unrunnable.aggregates == CaseAggregates(score=0.0, pass_rate=0.0)


def test_a_run_the_driver_raised_on_carries_the_error_and_no_graders() -> None:
    run = RunEntry.graded(error="4: no session directory appeared", timeout_seconds=1800.0)
    assert run.error == "4: no session directory appeared"
    assert run.score == 0.0
    assert run.graders == []


# The suite.


@pytest.mark.parametrize(("case_filter", "tags"), [("pass*", ("greeter",)), (None, ())])
def test_the_suite_document(case_filter: str | None, tags: tuple[str, ...]) -> None:
    """Both filter fields are written when given, and absent when not."""
    cases = [ran("passes", result("a", True)), ran("fails", result("a", False))]
    document = suite(cases, case_filter=case_filter, tag_filters=tags)
    assert document.schema_version == 1
    assert document.claude_version == VERSION
    assert document.started_at == STARTED
    assert document.duration_seconds == 91.5
    assert document.partial is False
    assert document.partial_reason is None
    assert document.suite == SuiteInfo(
        root=str(ROOT),
        ablation="none",
        threshold=0,
        judge_model="haiku",
        plugins=[PluginRef(name="reader-fixture", path=str(ROOT), version="0.0.1")],
        case_filter=case_filter,
        tag_filters=list(tags) or None,
    )
    written = document.suite.model_dump(by_alias=True)
    assert ("caseFilter" in written, "tagFilters" in written) == (bool(tags), bool(tags))


def test_the_suite_cost_is_the_judge_spend_alone() -> None:
    cases = [
        CaseEntry.build(case("one"), ROOT, (RunEntry.graded(judge_cost_usd=0.004),)),
        CaseEntry.build(
            case("two"),
            ROOT,
            (RunEntry.graded(judge_cost_usd=0.002), RunEntry.graded(judge_cost_usd=0.001)),
        ),
    ]
    assert suite(cases).cost_usd == pytest.approx(0.007)


NOTHING = SuiteAggregates(cases_total=0, cases_passed=0, overall_score=0.0, overall_pass_rate=0.0)


@pytest.mark.parametrize(
    ("names", "aggregates"),
    [
        (
            ("runs", "declared"),
            SuiteAggregates(
                cases_total=1, cases_passed=1, overall_score=1.0, overall_pass_rate=1.0
            ),
        ),
        (("declared",), NOTHING),
        ((), NOTHING),
    ],
)
def test_a_declared_case_leaves_all_four_aggregates(
    names: tuple[str, ...], aggregates: SuiteAggregates
) -> None:
    """It is in `cases`, and out of `casesTotal`, `casesPassed` and both means. A suite of
    nothing but declared cases reports the same four numbers as a suite of no cases, and a
    mean over nothing is 0."""
    cases = [
        CaseEntry.build(case(name), ROOT, declared_reason="no-cowork")
        if name == "declared"
        else ran(name, result("a", True))
        for name in names
    ]
    document = suite(cases)
    assert [entry.name for entry in document.cases] == list(names)
    assert document.aggregates == aggregates


def test_the_document_is_written_under_the_one_name_and_read_back(
    tmp_path: Path, answered: SessionDocument
) -> None:
    run = RunEntry.collected(answered, (result("a", True),), timeout_seconds=1800.0)
    document = suite([CaseEntry.build(read(CASE_DIR), ROOT, (run,))])
    path = write(tmp_path, document)
    assert path == tmp_path / RESULT_NAME
    assert ResultDocument.read(path) == document


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
    assert document.suite.plugins == [
        PluginRef(name="nameless", path=str((tmp_path / "nameless").resolve()))
    ]


@pytest.mark.parametrize(("costs", "total"), [((0.25, 0.5), 0.75), ((), 0.0)])
def test_the_spend_is_summed_over_the_documents_written_so_far(
    tmp_path: Path, costs: tuple[float, ...], total: float
) -> None:
    """`mail/` holds no document, and contributes nothing."""
    passed = ResultDocument.read(DATA / "results" / "pass.json")
    (tmp_path / "mail").mkdir()
    for index, cost in enumerate(costs):
        (tmp_path / f"plugin-{index}").mkdir()
        write(tmp_path / f"plugin-{index}", passed.model_copy(update={"cost_usd": cost}))
    assert spend(tmp_path) == pytest.approx(total)
