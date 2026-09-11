"""The `claude plugin eval` command line. docs/running_evals.md pins every flag here.

Nothing in this file runs the harness. The argument list is the unit under test.
"""

from __future__ import annotations

from cowork_evals.config import Config, EvalSection
from cowork_evals.harness import RunOptions, eval_argv


def options(**overrides) -> RunOptions:
    """A fully explicit RunOptions, so a test reads no configuration it did not write."""
    fixed = {
        "model": "sonnet",
        "judge_model": "haiku",
        "max_cost_usd": "5",
        "allow_tools": ("Bash",),
        "keep_traces": True,
    }
    return RunOptions(**{**fixed, **overrides})


def value_after(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


# Resolving the options.


def test_the_built_in_defaults_apply_when_the_file_carries_no_eval_section():
    assert RunOptions.resolve(Config()) == RunOptions(
        model="sonnet",
        judge_model="haiku",
        max_cost_usd="5",
        allow_tools=("Bash",),
        keep_traces=True,
    )


def test_the_configured_value_beats_the_default():
    config = Config(eval=EvalSection(model="opus", allow_tools=("Bash", "Write")))
    resolved = RunOptions.resolve(config)
    assert resolved.model == "opus"
    assert resolved.allow_tools == ("Bash", "Write")


def test_an_explicit_argument_beats_the_configured_value():
    config = Config(eval=EvalSection(model="opus"))
    assert RunOptions.resolve(config, model="haiku").model == "haiku"


def test_an_omitted_config_is_read_from_the_working_directory(working_directory, tmp_path):
    (tmp_path / "cowork_evals.yaml").write_text("eval:\n  judge_model: opus\n", encoding="utf-8")
    with working_directory(tmp_path):
        assert RunOptions.resolve().judge_model == "opus"


def test_the_traces_are_kept_unless_the_file_turns_them_off():
    assert RunOptions.resolve(Config()).keep_traces is True
    assert RunOptions.resolve(Config(eval=EvalSection(keep_traces=False))).keep_traces is False


def test_either_form_of_the_traces_argument_beats_the_file():
    """It is three-state: `None` is the option not typed, and both booleans beat the file."""
    off = Config(eval=EvalSection(keep_traces=False))
    on = Config(eval=EvalSection(keep_traces=True))
    assert RunOptions.resolve(off, keep_traces=True).keep_traces is True
    assert RunOptions.resolve(on, keep_traces=False).keep_traces is False
    assert RunOptions.resolve(off, keep_traces=None).keep_traces is False


def test_a_whole_cost_is_emitted_without_a_decimal_point():
    """`max_cost_usd` is a number in the file and a string on the command line."""
    assert RunOptions.resolve(Config()).max_cost_usd == "5"
    assert RunOptions.resolve(Config(eval=EvalSection(max_cost_usd=2.5))).max_cost_usd == "2.5"


# The command line.


def test_the_target_comes_before_every_variadic_flag():
    argv = eval_argv("/work/plugin/evals", "/work/logs", options(tags=("skill",)))
    target = argv.index("/work/plugin/evals")
    assert target < argv.index("--allow-tools")
    assert target < argv.index("--tag")


def test_the_debug_file_goes_before_the_subcommand():
    argv = eval_argv("/work/plugin/evals", "/work/logs", options())
    assert argv[:5] == ["claude", "--debug-file", "/work/logs/debug.txt", "plugin", "eval"]
    assert "--debug" not in argv, "a bare --debug swallows the subcommand name as its filter"


def test_every_always_pinned_flag_is_emitted():
    argv = eval_argv("/work/plugin/evals", "/work/logs", options())
    assert value_after(argv, "--model") == "sonnet"
    assert value_after(argv, "--judge-model") == "haiku"
    assert value_after(argv, "--ablation") == "none"
    assert value_after(argv, "--threshold") == "0"
    assert value_after(argv, "--max-cost-usd") == "5"
    assert value_after(argv, "--output-dir") == "/work/logs"
    assert value_after(argv, "--allow-tools") == "Bash"
    for flag in ("--no-publish", "--no-scaffold", "--verbose"):
        assert flag in argv


def test_json_is_never_emitted():
    assert "--json" not in eval_argv("/work/plugin/evals", "/work/logs", options())


def test_the_threshold_and_the_ablation_cannot_be_overridden():
    """Neither is a field of RunOptions, so no caller can reach them."""
    assert not hasattr(options(), "threshold")
    assert not hasattr(options(), "ablation")


def test_nothing_unasked_is_emitted():
    argv = eval_argv("/work/plugin/evals", "/work/logs", options())
    for flag in ("--runs", "--case", "--tag", "--report", "--mocks", "--eval-dir"):
        assert flag not in argv


def test_keep_temp_is_emitted_when_the_run_keeps_its_traces():
    """Without it only an errored run's sandbox is kept, and no passing run leaves a trace."""
    assert "--keep-temp" in eval_argv("/work/plugin/evals", "/work/logs", options())


def test_keep_temp_is_not_emitted_when_the_traces_are_turned_off():
    argv = eval_argv("/work/plugin/evals", "/work/logs", options(keep_traces=False))
    assert "--keep-temp" not in argv


def test_the_optional_flags_are_emitted_when_asked():
    argv = eval_argv(
        "/work/plugin/evals",
        "/work/logs",
        options(runs=1, case="smoke-*", tags=("plugin", "skill")),
    )
    assert value_after(argv, "--runs") == "1"
    assert value_after(argv, "--case") == "smoke-*"
    assert argv[argv.index("--tag") + 1 :] == ["plugin", "skill"]


def test_a_widened_allow_tools_replaces_the_value():
    argv = eval_argv("/work/plugin/evals", "/work/logs", options(allow_tools=("Bash", "Write")))
    assert argv[argv.index("--allow-tools") + 1 :] == ["Bash", "Write"]
