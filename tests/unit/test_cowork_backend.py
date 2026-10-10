"""The CoWork backend over hand-written case trees. Nothing here starts a session.

What makes a case unrunnable here is docs/eval_format.md, one assertion per source of it, and
what a declared case produces is docs/cowork_backend.md. See ../README.md.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path

import pytest

from cowork_evals.cases import CaseError, read
from cowork_evals.config import Config, CoWorkError, CoWorkSection
from cowork_evals.cowork_backend import declared, grader_skips, plan, run, unrunnable
from cowork_evals.harness import RESULT_NAME
from cowork_evals.results import ResultDocument

CaseTree = Callable[..., tuple[Path, Path]]


def reasons_of(tree: tuple[Path, Path]) -> tuple[str, ...]:
    root, case_dir = tree
    return unrunnable(read(case_dir), root)


def declared_of(tree: tuple[Path, Path]) -> str | None:
    root, case_dir = tree
    return declared(read(case_dir), root)


def graders_of(case_dir: Path) -> dict[str, str]:
    return grader_skips(read(case_dir))


# What a session runs, and what makes a case unrunnable here.


@pytest.mark.parametrize(
    ("frontmatter", "graders"),
    [
        pytest.param("", None, id="no-optional-key"),
        pytest.param("runs: 3", None, id="runs"),
        pytest.param("timeout_seconds: 600", None, id="timeout_seconds"),
        pytest.param(
            "",
            {
                "with-only": "---\ntype: regex\npattern: PONG\narm: with-only\n---\n",
                "both": "---\ntype: regex\npattern: PONG\narm: both\n---\n",
            },
            id="arm",
        ),
    ],
)
def test_a_key_a_session_honours_is_no_reason(
    tmp_path: Path, case_tree: CaseTree, frontmatter: str, graders: dict[str, str] | None
) -> None:
    tree = case_tree(tmp_path, frontmatter=frontmatter, graders=graders)
    assert reasons_of(tree) == ()
    assert graders_of(tree[1]) == {}


@pytest.mark.parametrize(
    ("written", "reason"),
    [
        ("max_turns: 12", "max_turns: no turn cap reaches a CoWork session"),
        ("model: sonnet", "model: the session decides its model"),
        ("allowed_tools: [Read]", "allowed_tools: the session decides its tools"),
        (
            "append_system_prompt: Be brief.",
            "append_system_prompt: the session decides its system prompt",
        ),
        ("env:\n  EVAL_ONE: two", "env: nothing sets an environment variable in the VM"),
    ],
)
def test_each_unhonoured_key_is_one_reason(
    tmp_path: Path, case_tree: CaseTree, written: str, reason: str
) -> None:
    assert reasons_of(case_tree(tmp_path, frontmatter=written)) == (reason,)


def test_a_context_key_in_case_yaml_is_a_reason(tmp_path: Path, case_tree: CaseTree) -> None:
    case_yaml = """
        schema_version: "1.1"
        name: one-case
        context:
          add_dirs: [resources]
        """
    assert reasons_of(case_tree(tmp_path, case_yaml=case_yaml)) == (
        "context.add_dirs: nothing stages files into the VM",
    )


@pytest.mark.parametrize(
    "layers",
    [
        ("evals",),
        ("evals/skill",),
        ("evals/skill/case",),
        ("evals", "evals/skill", "evals/skill/case"),
    ],
)
def test_each_mocks_layer_is_a_reason(
    tmp_path: Path, case_tree: CaseTree, layers: tuple[str, ...]
) -> None:
    root, case_dir = case_tree(tmp_path, mocks_at=layers)
    assert reasons_of((root, case_dir)) == tuple(
        f"{root}/{layer}/mocks: stand-ins are the harness's, and the MCP servers here are real"
        for layer in layers
    )


def test_a_mocks_directory_beside_the_plugin_root_is_not_a_layer(
    tmp_path: Path, case_tree: CaseTree
) -> None:
    """The layers run from `evals/` down. Nothing above it is one."""
    root, case_dir = case_tree(tmp_path)
    (root / "mocks").mkdir()
    assert unrunnable(read(case_dir), root) == ()


@pytest.mark.parametrize(
    ("frontmatter", "tags", "line"),
    [
        (
            "max_turns: 12",
            "[skill, no-cowork]",
            "no-cowork: max_turns: no turn cap reaches a CoWork session",
        ),
        (
            "max_turns: 12\nmodel: sonnet",
            "[skill, no-cowork]",
            "no-cowork: max_turns: no turn cap reaches a CoWork session; "
            "model: the session decides its model",
        ),
        pytest.param("", "[skill, no-cowork]", "no-cowork", id="tag-and-no-reason"),
        pytest.param("max_turns: 12", "[skill]", None, id="reason-and-no-tag"),
    ],
)
def test_the_tag_declares_every_reason_in_one_line(
    tmp_path: Path, case_tree: CaseTree, frontmatter: str, tags: str, line: str | None
) -> None:
    """The backend reads the tag and decides nothing. The validator keeps the two in step."""
    assert declared_of(case_tree(tmp_path, frontmatter=frontmatter, tags=tags)) == line


@pytest.mark.parametrize(
    ("graders", "skipped"),
    [
        pytest.param(
            {
                "asked-the-server": "---\ntype: regex\ntarget: mock_calls\npattern: posted\n---\n",
                "answered": "---\ntype: regex\ntarget: last_message\npattern: PONG\n---\n",
            },
            {"asked-the-server": "target: mock_calls, and no stand-in serves a CoWork run"},
            id="target",
        ),
        pytest.param(
            {"judged": "---\ntype: llm\nfocus: mock_calls\n---\n\nThe server was asked.\n"},
            {"judged": "focus: mock_calls, and no stand-in serves a CoWork run"},
            id="focus",
        ),
    ],
)
def test_a_grader_reading_mock_calls_is_skipped_and_the_case_still_runs(
    tmp_path: Path, case_tree: CaseTree, graders: dict[str, str], skipped: dict[str, str]
) -> None:
    tree = case_tree(tmp_path, graders=graders)
    assert reasons_of(tree) == ()
    assert graders_of(tree[1]) == skipped


# The plan. Nothing below starts a session, and none of it needs a profile.


SMOKE = Path(__file__).resolve().parent.parent.parent / "plugins" / "smoke"
TREE = Path(__file__).resolve().parent.parent / "data" / "cases" / "tree"
MARKETPLACE = Path(__file__).resolve().parent.parent / "data" / "cli" / "marketplace"


def settings(tmp_path: Path) -> Config:
    """A configuration whose run log is a file this test owns."""
    return Config(cowork=CoWorkSection(run_log=tmp_path / "runs.jsonl", log_dir=None))


def capped(tmp_path: Path, max_runs: int) -> Config:
    config = settings(tmp_path)
    return dataclasses.replace(config, cowork=dataclasses.replace(config.cowork, max_runs=max_runs))


@pytest.mark.parametrize(
    ("case", "runs", "timeout_seconds", "expected"),
    [
        ("no-frontmatter", None, None, (1, 900.0)),
        ("every-key", None, None, (2, 600.0)),
        ("every-key", 3, 120, (3, 120.0)),
    ],
)
def test_the_run_count_and_timeout_resolve_in_order(
    tmp_path: Path,
    case: str,
    runs: int | None,
    timeout_seconds: int | None,
    expected: tuple[int, float],
) -> None:
    """An override replaces what the case declared and never multiplies it."""
    config = settings(tmp_path)
    config = dataclasses.replace(config, cowork=dataclasses.replace(config.cowork, run_timeout=900))
    prepared = plan(
        TREE / "evals" / "greeter" / case,
        config=config,
        runs=runs,
        timeout_seconds=timeout_seconds,
    )
    (entry,) = prepared.entries
    assert (entry.runs, entry.timeout_seconds) == expected


def test_a_declared_case_costs_no_ceiling_entry(tmp_path: Path, case_tree: CaseTree) -> None:
    root, _ = case_tree(tmp_path, frontmatter="max_turns: 12\nruns: 4", tags="[skill, no-cowork]")
    prepared = plan(root, config=settings(tmp_path))
    assert prepared.entries[0].declared is not None
    assert prepared.entries[0].runs == 4
    assert prepared.entries[0].submissions == 0
    assert prepared.submissions == 0


def test_the_ceiling_arithmetic_is_the_plan_plus_the_run_log(
    tmp_path: Path, run_log: Callable[..., None]
) -> None:
    """One case of the suite, so the arithmetic is read off one number."""
    config = capped(tmp_path, 3)
    run_log(tmp_path / "runs.jsonl", 2)
    assert not plan(SMOKE, config=config, runs=1, case_glob="python-version").over_ceiling
    assert plan(SMOKE, config=config, runs=2, case_glob="python-version").over_ceiling


def test_run_refuses_above_the_ceiling_before_submitting_anything(
    tmp_path: Path, run_log: Callable[..., None]
) -> None:
    run_log(tmp_path / "runs.jsonl", 5)
    output = tmp_path / "out"
    output.mkdir()
    with pytest.raises(CoWorkError) as raised:
        run(SMOKE, output, config=capped(tmp_path, 3), runs=1)
    assert raised.value.code == 2
    assert list(output.iterdir()) == [], "nothing was written"


def test_a_target_covering_two_plugin_roots_raises(tmp_path: Path) -> None:
    with pytest.raises(CaseError) as raised:
        plan(MARKETPLACE, config=settings(tmp_path))
    assert "more than one plugin root" in str(raised.value)


# The document a suite of declared cases produces.


@pytest.mark.parametrize(("judge_model", "written"), [(None, "haiku"), ("opus", "opus")])
def test_a_suite_of_declared_cases_writes_a_document_and_submits_nothing(
    tmp_path: Path, case_tree: CaseTree, judge_model: str | None, written: str
) -> None:
    root, _ = case_tree(tmp_path, frontmatter="model: sonnet", tags="[skill, no-cowork]")
    output = tmp_path / "out"
    output.mkdir()
    path = run(root, output, config=settings(tmp_path), judge_model=judge_model)
    assert path == output / RESULT_NAME
    document = ResultDocument.read(path)
    assert document.cost_usd == 0
    assert document.suite.judge_model == written
    assert document.cases[0].declared_reason == "no-cowork: model: the session decides its model"
    assert not (tmp_path / "runs.jsonl").exists(), "the driver was never called"
