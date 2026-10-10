"""The `claude plugin eval` command line. docs/run_pipeline.md pins every flag here.

Nothing in this file runs the harness. The argument list is the unit under test.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from cowork_evals.config import CONFIG_FILENAME, Config, EvalSection
from cowork_evals.harness import RunOptions, eval_argv

TARGET = "/work/plugin/evals"
LOGS = "/work/logs"


def value_after(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


# Resolving the options. docs/library.md "The precedence ladder".


@pytest.mark.parametrize(
    ("name", "default", "written", "from_file", "argument"),
    [
        ("model", "sonnet", "opus", "opus", "haiku"),
        ("judge_model", "haiku", "opus", "opus", "sonnet"),
        ("ablation", "none", "with-without", "with-without", "none"),
        ("max_cost_usd", "5", 2.5, "2.5", "1"),
        (
            "allow_tools",
            ("Bash", "Read", "Glob", "Grep", "Write", "Edit", "WebFetch", "Skill"),
            ("Bash", "Write"),
            ("Bash", "Write"),
            ("Read",),
        ),
        ("keep_traces", True, False, False, True),
        ("keep_traces", True, True, True, False),
    ],
)
def test_each_option_resolves_argument_over_file_over_default(
    working_directory,
    tmp_path: Path,
    name: str,
    default: Any,
    written: Any,
    from_file: Any,
    argument: Any,
) -> None:
    assert getattr(RunOptions.resolve(Config()), name) == default
    configured = Config(eval=replace(EvalSection(), **{name: written}))
    configured.dump(tmp_path / CONFIG_FILENAME)
    with working_directory(tmp_path):
        assert getattr(RunOptions.resolve(), name) == from_file
        assert getattr(RunOptions.resolve(**{name: argument}), name) == argument


# The command line.


def test_the_target_comes_before_every_variadic_flag(run_options: RunOptions) -> None:
    argv = eval_argv(TARGET, LOGS, replace(run_options, tags=("skill",)))
    target = argv.index(TARGET)
    assert target < argv.index("--allow-tools")
    assert target < argv.index("--tag")


def test_the_debug_file_goes_before_the_subcommand(run_options: RunOptions) -> None:
    argv = eval_argv(TARGET, LOGS, run_options)
    assert argv[:5] == ["claude", "--debug-file", "/work/logs/debug.txt", "plugin", "eval"]
    assert "--debug" not in argv, "a bare --debug swallows the subcommand name as its filter"


def test_every_always_pinned_flag_is_emitted() -> None:
    options = RunOptions(
        model="opus",
        judge_model="sonnet",
        ablation="with-without",
        max_cost_usd="2.5",
        allow_tools=("Bash", "Write"),
    )
    argv = eval_argv(TARGET, LOGS, options)
    assert value_after(argv, "--model") == "opus"
    assert value_after(argv, "--judge-model") == "sonnet"
    assert value_after(argv, "--ablation") == "with-without"
    assert value_after(argv, "--threshold") == "0"
    assert value_after(argv, "--max-cost-usd") == "2.5"
    assert value_after(argv, "--output-dir") == LOGS
    assert argv[argv.index("--allow-tools") + 1 :] == ["Bash", "Write"]
    for flag in ("--no-publish", "--no-scaffold", "--verbose"):
        assert flag in argv


def test_nothing_unasked_is_emitted(run_options: RunOptions) -> None:
    argv = eval_argv(TARGET, LOGS, run_options)
    for flag in ("--runs", "--case", "--tag", "--report", "--mocks", "--eval-dir", "--json"):
        assert flag not in argv


@pytest.mark.parametrize("keep_traces", [True, False])
def test_keep_temp_is_emitted_when_the_run_keeps_its_traces(
    run_options: RunOptions, keep_traces: bool
) -> None:
    """Without it only an errored run's sandbox is kept, and no passing run leaves a trace."""
    argv = eval_argv(TARGET, LOGS, replace(run_options, keep_traces=keep_traces))
    assert ("--keep-temp" in argv) is keep_traces


def test_the_optional_flags_are_emitted_when_asked(run_options: RunOptions) -> None:
    argv = eval_argv(
        TARGET, LOGS, replace(run_options, runs=1, case="smoke-*", tags=("plugin", "skill"))
    )
    assert value_after(argv, "--runs") == "1"
    assert value_after(argv, "--case") == "smoke-*"
    assert argv[argv.index("--tag") + 1 :] == ["plugin", "skill"]
