"""The CoWork backend over hand-written case trees. Nothing here starts a session.

What makes a case unrunnable here is docs/eval_format.md, one assertion per source of it, and
what a declared case produces is docs/cowork_backend.md. See ../README.md.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from cowork_evals.cases import CaseError, read
from cowork_evals.config import Config, CoWorkError, CoWorkSection
from cowork_evals.cowork_backend import declared, grader_skips, plan, run, unrunnable
from cowork_evals.harness import RESULT_NAME

MANIFEST = '{"name": "skips-fixture", "description": "A fixture.", "version": "0.0.1"}\n'


def reasons_of(root: Path, case_dir: Path) -> tuple[str, ...]:
    return unrunnable(read(case_dir), root)


def declared_of(root: Path, case_dir: Path) -> str | None:
    return declared(read(case_dir), root)


def graders_of(case_dir: Path) -> dict[str, str]:
    return grader_skips(read(case_dir))


# What a session runs.


def test_a_written_out_runs_key_is_runnable(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    assert reasons_of(*case_tree(tmp_path, frontmatter="runs: 3")) == ()


def test_a_written_out_timeout_seconds_is_runnable(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    assert reasons_of(*case_tree(tmp_path, frontmatter="timeout_seconds: 600")) == ()


def test_a_case_writing_no_optional_key_is_runnable(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    assert reasons_of(*case_tree(tmp_path)) == ()
    assert graders_of(case_tree(tmp_path / "graders")[1]) == {}
    assert declared_of(*case_tree(tmp_path / "declared")) is None


def test_an_arm_on_a_grader_is_honoured(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    """One arm runs, it is the with-arm, and every grader is scored in it."""
    graders = {
        "with-only": "---\ntype: regex\npattern: PONG\narm: with-only\n---\n",
        "both": "---\ntype: regex\npattern: PONG\narm: both\n---\n",
    }
    assert reasons_of(*case_tree(tmp_path, graders=graders)) == ()
    assert graders_of(case_tree(tmp_path / "graders", graders=graders)[1]) == {}


# The three sources that make a case unrunnable here.


def test_a_written_out_max_turns_is_a_reason(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    assert reasons_of(*case_tree(tmp_path, frontmatter="max_turns: 12")) == (
        "max_turns: no turn cap reaches a CoWork session",
    )


def test_each_execution_key_is_a_reason(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    for key, written in (
        ("model", "model: sonnet"),
        ("allowed_tools", "allowed_tools: [Read]"),
        ("append_system_prompt", "append_system_prompt: Be brief."),
        ("env", "env:\n  EVAL_ONE: two"),
    ):
        reasons = reasons_of(*case_tree(tmp_path / key, frontmatter=written))
        assert len(reasons) == 1
        assert reasons[0].startswith(f"{key}: ")


def test_a_context_key_in_case_yaml_is_a_reason(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    assert reasons_of(
        *case_tree(
            tmp_path,
            case_yaml="""
        schema_version: "1.1"
        name: one-case
        context:
          add_dirs: [resources]
        """,
        )
    ) == ("context.add_dirs: nothing stages files into the VM",)


def test_a_suite_wide_mocks_directory_is_a_reason(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    reasons = reasons_of(*case_tree(tmp_path, mocks_at=("evals",)))
    assert len(reasons) == 1
    assert reasons[0].startswith(str(tmp_path / "plugin" / "evals" / "mocks"))


def test_a_group_mocks_directory_is_a_reason(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    reasons = reasons_of(*case_tree(tmp_path, mocks_at=("evals/skill",)))
    assert len(reasons) == 1
    assert "evals/skill/mocks" in reasons[0]


def test_a_case_mocks_directory_is_a_reason_for_that_case_alone(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    reasons = reasons_of(*case_tree(tmp_path, mocks_at=("evals/skill/case",)))
    assert len(reasons) == 1
    assert "evals/skill/case/mocks" in reasons[0]


def test_every_mocks_layer_is_reported(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    assert (
        len(reasons_of(*case_tree(tmp_path, mocks_at=("evals", "evals/skill", "evals/skill/case"))))
        == 3
    )


def test_a_mocks_directory_beside_the_plugin_root_is_not_a_layer(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    """The layers run from `evals/` down. Nothing above it is one."""
    root, case_dir = case_tree(tmp_path)
    (root / "mocks").mkdir()
    assert unrunnable(read(case_dir), root) == ()


# What the tag declares.


def test_the_tag_carries_every_reason_into_one_line(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    line = declared_of(*case_tree(tmp_path, frontmatter="max_turns: 12", tags="[skill, no-cowork]"))
    assert line == "no-cowork: max_turns: no turn cap reaches a CoWork session"


def test_a_case_carrying_the_tag_and_no_reason_still_declares_itself(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    """The validator refuses that case. The backend reads the tag and submits nothing."""
    assert declared_of(*case_tree(tmp_path, tags="[skill, no-cowork]")) == "no-cowork"


def test_a_case_with_a_reason_and_no_tag_is_not_declared(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    """The tag decides here, and the validator is what keeps the two in step."""
    assert declared_of(*case_tree(tmp_path, frontmatter="max_turns: 12")) is None


# The one grader skip decided before a run.


def test_a_grader_reading_mock_calls_is_skipped_and_the_case_still_runs(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    graders = {
        "asked-the-server": "---\ntype: regex\ntarget: mock_calls\npattern: posted\n---\n",
        "answered": "---\ntype: regex\ntarget: last_message\npattern: PONG\n---\n",
    }
    assert reasons_of(*case_tree(tmp_path, graders=graders)) == ()
    skipped = graders_of(case_tree(tmp_path / "graders", graders=graders)[1])
    assert list(skipped) == ["asked-the-server"]
    assert "mock_calls" in skipped["asked-the-server"]


def test_a_judged_grader_focusing_mock_calls_is_skipped(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    graders = {"judged": "---\ntype: llm\nfocus: mock_calls\n---\n\nThe server was asked.\n"}
    assert reasons_of(*case_tree(tmp_path, graders=graders)) == ()
    assert list(graders_of(case_tree(tmp_path / "graders", graders=graders)[1])) == ["judged"]


# The plan. Nothing below starts a session, and none of it needs a profile.


SMOKE = Path(__file__).resolve().parent.parent.parent / "plugins" / "smoke"
TREE = Path(__file__).resolve().parent.parent / "data" / "cases" / "tree"


def settings(tmp_path: Path, **overrides: object) -> Config:
    """A configuration whose run log is a file this test owns."""
    values: dict[str, object] = {"run_log": str(tmp_path / "runs.jsonl"), "log_dir": None}
    values.update(overrides)
    return Config(cowork=CoWorkSection(**values))  # type: ignore[arg-type]


def test_the_smoke_fixture_is_found_and_four_of_its_cases_are_submitted(tmp_path: Path) -> None:
    """Five cases, one of which declares that a session cannot run it."""
    prepared = plan(SMOKE, config=settings(tmp_path))
    assert prepared.root == SMOKE.resolve()
    assert sorted(entry.name for entry in prepared.entries) == [
        "capped-turns",
        "checked-file",
        "python-version",
        "session-env",
        "writes-a-file",
    ]
    for entry in prepared.entries:
        assert entry.graders == {}, entry.name
        assert entry.runs == 1, "each case writes runs: 1"
    declared_here = {entry.name: entry.declared for entry in prepared.entries}
    assert declared_here["python-version"] is None
    assert declared_here["writes-a-file"] is None
    assert declared_here["checked-file"] is None, "a check runs on the host, not in a session"
    assert declared_here["session-env"] is None, "a session has only session_env names"
    assert declared_here["capped-turns"] == (
        "no-cowork: max_turns: no turn cap reaches a CoWork session"
    )
    assert prepared.submissions == 4


def test_a_case_that_writes_no_runs_key_runs_once(tmp_path: Path) -> None:
    prepared = plan(TREE / "evals" / "greeter" / "no-frontmatter", config=settings(tmp_path))
    assert prepared.entries[0].runs == 1


def test_a_declared_runs_key_is_the_run_count(tmp_path: Path) -> None:
    prepared = plan(TREE / "evals" / "greeter" / "every-key", config=settings(tmp_path))
    assert prepared.entries[0].runs == 2
    assert prepared.entries[0].timeout_seconds == 600.0


def test_an_override_replaces_what_the_case_declared_and_never_multiplies_it(
    tmp_path: Path,
) -> None:
    prepared = plan(
        TREE / "evals" / "greeter" / "every-key",
        config=settings(tmp_path),
        runs=3,
        timeout_seconds=120,
    )
    assert prepared.entries[0].runs == 3
    assert prepared.entries[0].timeout_seconds == 120.0


def test_a_case_declaring_no_timeout_runs_under_the_configured_one(tmp_path: Path) -> None:
    prepared = plan(SMOKE, config=settings(tmp_path, run_timeout=900))
    assert prepared.entries[0].timeout_seconds == 900.0


def test_a_declared_case_costs_no_ceiling_entry(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    root, _ = case_tree(tmp_path, frontmatter="max_turns: 12\nruns: 4", tags="[skill, no-cowork]")
    prepared = plan(root, config=settings(tmp_path))
    assert prepared.entries[0].declared is not None
    assert prepared.entries[0].runs == 4
    assert prepared.entries[0].submissions == 0
    assert prepared.submissions == 0


def test_the_ceiling_arithmetic_is_the_plan_plus_the_run_log(
    tmp_path: Path, run_log: Callable[..., None]
) -> None:
    """One case of the two, so the arithmetic is read off one number and not off the suite."""
    config = settings(tmp_path, max_runs=3)
    run_log(tmp_path / "runs.jsonl", 2)
    prepared = plan(SMOKE, config=config, runs=1, case_glob="python-version")
    assert prepared.recent == 2
    assert prepared.max_runs == 3
    assert prepared.submissions == 1
    assert prepared.over_ceiling is False

    prepared = plan(SMOKE, config=config, runs=2, case_glob="python-version")
    assert prepared.over_ceiling is True
    assert "max_runs is 3" in prepared.refusal


def test_run_refuses_above_the_ceiling_before_submitting_anything(
    tmp_path: Path, run_log: Callable[..., None]
) -> None:
    run_log(tmp_path / "runs.jsonl", 5)
    output = tmp_path / "out"
    output.mkdir()
    with pytest.raises(CoWorkError) as raised:
        run(SMOKE, output, config=settings(tmp_path, max_runs=3), runs=1)
    assert raised.value.code == 2
    assert list(output.iterdir()) == [], "nothing was written"


def test_a_tag_filter_and_a_case_glob_reach_discovery(tmp_path: Path) -> None:
    config = settings(tmp_path)
    assert plan(TREE, config=config, tags=("greeter",)).entries[0].name == "greets-alex"
    assert plan(TREE, config=config, case_glob="inner-*").entries[0].name == "inner-case"
    assert plan(TREE, config=config, case_glob="no-such-case").entries == ()


# What the target selects.


def test_a_target_covering_two_plugin_roots_raises(tmp_path: Path) -> None:
    for name in ("one", "two"):
        root = tmp_path / "marketplace" / name
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin" / "plugin.json").write_text(MANIFEST, encoding="utf-8")
        # A plugin is a manifest with a sibling `evals/`, and never a manifest alone.
        # docs/library.md.
        (root / "evals").mkdir()
    with pytest.raises(CaseError) as raised:
        plan(tmp_path / "marketplace", config=settings(tmp_path))
    assert "more than one plugin root" in str(raised.value)


def test_a_target_under_no_plugin_root_raises(tmp_path: Path) -> None:
    (tmp_path / "loose").mkdir()
    with pytest.raises(CaseError):
        plan(tmp_path / "loose", config=settings(tmp_path))


# The document a suite of skipped cases produces.


def test_a_suite_of_declared_cases_writes_a_document_and_submits_nothing(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    root, _ = case_tree(tmp_path, frontmatter="model: sonnet", tags="[skill, no-cowork]")
    output = tmp_path / "out"
    output.mkdir()
    written = run(root, output, config=settings(tmp_path))
    assert written == output / RESULT_NAME

    document = json.loads(written.read_text(encoding="utf-8"))
    assert document["schemaVersion"] == 1
    assert document["partial"] is False
    assert document["costUsd"] == 0.0
    assert document["suite"]["root"] == str(root.resolve())
    assert document["suite"]["judgeModel"] == "haiku"
    assert document["aggregates"] == {
        "casesTotal": 0,
        "casesPassed": 0,
        "overallScore": 0.0,
        "overallPassRate": 0.0,
    }, "a declared case is out of all four"
    entry = document["cases"][0]
    assert entry["declaredUnrunnable"] is True
    assert entry["declaredReason"] == "no-cowork: model: the session decides its model"
    assert "skipped" not in entry
    assert entry["arms"]["with"] == []
    assert driver_log_is_empty(tmp_path), "the driver was never called"


def test_the_judge_model_override_reaches_the_suite(
    tmp_path: Path, case_tree: Callable[..., tuple[Path, Path]]
) -> None:
    root, _ = case_tree(tmp_path, frontmatter="model: sonnet", tags="[skill, no-cowork]")
    output = tmp_path / "out"
    output.mkdir()
    written = run(root, output, config=settings(tmp_path), judge_model="opus")
    assert json.loads(written.read_text(encoding="utf-8"))["suite"]["judgeModel"] == "opus"


def driver_log_is_empty(tmp_path: Path) -> bool:
    """No submission was made, so the driver's run log was never written."""
    return not (tmp_path / "runs.jsonl").exists()
