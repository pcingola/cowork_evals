"""The parser, the refusals and the exit codes.

The parser under test is the real one, built by `build_parser`. `argparse` raises
`SystemExit(2)` from inside `parse_args`, and the rows that reach it assert on that; every
other refusal is a value `main` returns. The surface is docs/cli.md. See ../README.md.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cowork_evals import cli, logs, panel, preflight, results
from cowork_evals.cases import plugin_name, plugin_roots
from cowork_evals.cli import FAILED, OK, PREFLIGHT_FAILED, USAGE, main, parse_args
from cowork_evals.config import Config, CoWorkError, EvalSection, checked
from cowork_evals.docker import Condition, Docker, remedy
from cowork_evals.docker.pytest_image import PytestImage
from cowork_evals.harness import RESULT_NAME


def parse(*argv: str):
    return parse_args(list(argv))


# Each verb's parse tree.


def test_run_takes_a_backend_a_path_and_every_option() -> None:
    args = parse(
        "run",
        "--docker",
        "plugin/evals",
        "--runs",
        "2",
        "--model",
        "sonnet",
        "--judge-model",
        "haiku",
        "--allow-tools",
        "Bash",
        "Write",
        "--max-cost-usd",
        "3",
        "--tag",
        "greeter",
        "--tag",
        "writer",
        "--case",
        "hello-*",
        "--out",
        "elsewhere",
        "--build-missing",
        "--require-coverage",
        "--dry-run",
    )
    assert args.verb == "run"
    assert args.backend == "docker"
    assert args.path == "plugin/evals"
    assert args.runs == 2
    assert args.model == "sonnet"
    assert args.judge_model == "haiku"
    assert args.allow_tools == ["Bash", "Write"]
    assert args.max_cost_usd == 3.0
    assert args.tag == ["greeter", "writer"]
    assert args.case == "hello-*"
    assert args.out == "elsewhere"
    assert args.build_missing
    assert args.require_coverage
    assert args.dry_run


def test_the_traces_option_is_three_state() -> None:
    """Untyped is `None`, so both forms beat a file and neither is confused with it."""
    assert parse("run", "--docker", "plugin/evals").keep_traces is None
    assert parse("run", "--docker", "plugin/evals", "--keep-traces").keep_traces is True
    assert parse("run", "--docker", "plugin/evals", "--no-keep-traces").keep_traces is False


def test_the_traces_option_reaches_the_harness_options() -> None:
    """An option beats the file, and the file beats the built-in default. docs/library.md."""
    off = Config(eval=EvalSection(keep_traces=False))
    typed = parse("run", "--docker", "plugin/evals", "--keep-traces")
    untyped = parse("run", "--docker", "plugin/evals")
    assert cli._options(typed, off, ()).keep_traces is True
    assert cli._options(untyped, off, ()).keep_traces is False
    assert cli._options(untyped, Config(), ()).keep_traces is True


@pytest.mark.parametrize("backend", ["--docker", "--cowork"])
def test_the_same_ladder_decides_it_on_either_backend(backend) -> None:
    """`_keeping` is the one place the option meets the file, for both backends."""
    off = Config(eval=EvalSection(keep_traces=False))
    assert cli._keeping(parse("run", backend, "plugin/evals"), Config()) is True
    assert cli._keeping(parse("run", backend, "plugin/evals"), off) is False
    assert cli._keeping(parse("run", backend, "plugin/evals", "--keep-traces"), off) is True
    assert (
        cli._keeping(parse("run", backend, "plugin/evals", "--no-keep-traces"), Config()) is False
    )


def test_run_defaults_every_option_to_nothing() -> None:
    args = parse("run", "--cowork", "plugin/evals")
    assert (args.runs, args.timeout_seconds, args.model, args.judge_model) == (
        None,
        None,
        None,
        None,
    )
    assert (args.allow_tools, args.max_cost_usd, args.tag, args.case, args.out) == (
        None,
        None,
        None,
        None,
        None,
    )
    assert not args.build_missing
    assert not args.require_coverage
    assert not args.dry_run
    assert args.keep_traces is None


def test_test_takes_a_path_two_flags_and_a_tail() -> None:
    args = parse("test", "--docker", "plugin/tests", "--build-missing", "--dry-run")
    assert (args.verb, args.backend, args.path) == ("test", "docker", "plugin/tests")
    assert args.build_missing
    assert args.dry_run
    assert args.pytest_args == []


def test_ask_takes_cowork_a_prompt_and_its_four_options() -> None:
    args = parse("ask", "--cowork", "hi", "--timeout-seconds", "60", "--json", "--dry-run")
    assert (args.verb, args.backend, args.prompt) == ("ask", "cowork", "hi")
    assert args.timeout_seconds == 60.0
    assert args.json
    assert args.dry_run
    assert args.session is None


def test_ask_takes_no_case_option() -> None:
    """It runs no eval, so every option that configures one is unknown to it."""
    for option in ("--runs", "--tag", "--case", "--out", "--model"):
        with pytest.raises(SystemExit) as raised:
            parse("ask", "--cowork", "hi", option, "x")
        assert raised.value.code == USAGE


def test_ask_docker_is_a_usage_error() -> None:
    """`--cowork` is its only backend, so the other is not a member of the group."""
    with pytest.raises(SystemExit) as raised:
        parse("ask", "--docker", "hi")
    assert raised.value.code == USAGE


def test_ask_with_no_backend_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as raised:
        parse("ask", "hi")
    assert raised.value.code == USAGE


def test_setup_takes_docker_alone() -> None:
    assert parse("setup", "--docker").backend == "docker"


def test_login_takes_docker_alone_and_its_two_reports_are_exclusive() -> None:
    """`--check` reports and `--force` writes, so asking for both says nothing coherent."""
    assert parse("login", "--docker").backend == "docker"
    assert parse("login", "--docker", "--check").check
    assert parse("login", "--docker", "--force").force
    for argv in (
        ("login",),
        ("login", "--cowork"),
        ("login", "--docker", "--check", "--force"),
    ):
        with pytest.raises(SystemExit) as raised:
            parse(*argv)
        assert raised.value.code == USAGE


def test_login_is_the_verb_a_missing_credential_names() -> None:
    """The preflight sends an operator to the verb that makes a credential, not to `setup`.

    `setup --docker` on a machine holding two current images prints `current` twice and
    returns 0, so a line naming it would be a fix that changes nothing.
    """
    assert remedy(Condition.CREDENTIAL) == "run cowork_evals login --docker"
    assert "login" in remedy(Condition.CREDENTIAL)
    assert "setup" not in remedy(Condition.CREDENTIAL)


def test_login_refuses_under_the_bedrock_route(tmp_path: Path, capsys) -> None:
    """That route reads Claude's own credential from the host, so there is nothing to make.

    Both modes refuse, because `--check` under this route would report a credentials file
    that route never writes. What reports the four host variables is `check --docker`.
    """
    path = tmp_path / "cowork_evals.yaml"
    path.write_text("docker:\n  credential: bedrock\n", encoding="utf-8")
    config = Config.load(path)
    for args in (parse("login", "--docker"), parse("login", "--docker", "--check")):
        assert cli._login(args, config) == PREFLIGHT_FAILED
    printed = capsys.readouterr().err
    assert printed.count("no login to make") == 2
    assert "cowork_evals check --docker" in printed


def test_check_takes_both_backends_and_all() -> None:
    assert parse("check", "--docker").backend == "docker"
    assert parse("check", "--cowork").backend == "cowork"
    assert parse("check", "--all").backend == "all"


def test_prune_takes_any_combination_of_its_selection_flags() -> None:
    args = parse("prune", "--docker", "--logs", "--older-than", "7", "--out", "elsewhere")
    assert args.docker and args.logs
    assert args.older_than == 7
    assert args.out == "elsewhere"


def test_prune_defaults_to_the_same_age_run_prunes_at() -> None:
    assert parse("prune", "--logs").older_than == logs.RUN_PRUNE_DAYS


def test_older_than_is_a_prune_flag_only() -> None:
    with pytest.raises(SystemExit) as raised:
        parse("run", "--docker", "plugin/evals", "--older-than", "7")
    assert raised.value.code == USAGE


def test_out_is_on_run_and_prune_and_nowhere_else() -> None:
    assert parse("run", "--docker", "p", "--out", "x").out == "x"
    assert parse("prune", "--logs", "--out", "x").out == "x"
    with pytest.raises(SystemExit):
        parse("test", "--docker", "p", "--out", "x")


# The pytest tail.


def test_the_tail_begins_at_the_separator_and_survives_token_for_token() -> None:
    args = parse("test", "--docker", "plugin/tests", "--", "-k", "parser", "-v", "--tb=short")
    assert args.pytest_args == ["-k", "parser", "-v", "--tb=short"]


def test_argparse_claims_no_token_after_the_separator() -> None:
    """`--dry-run` after `--` is pytest's argument and never this command's."""
    args = parse("test", "--docker", "plugin/tests", "--", "--dry-run", "--build-missing")
    assert args.pytest_args == ["--dry-run", "--build-missing"]
    assert not args.dry_run
    assert not args.build_missing


def test_run_takes_no_raw_tail() -> None:
    with pytest.raises(SystemExit) as raised:
        parse("run", "--docker", "plugin/evals", "--", "-k", "parser")
    assert raised.value.code == USAGE


# The backend is required, and its members differ per verb.


def test_a_verb_with_no_backend_is_a_usage_error() -> None:
    for argv in (("run", "plugin/evals"), ("test", "plugin/tests"), ("setup",), ("check",)):
        with pytest.raises(SystemExit) as raised:
            parse(*argv)
        assert raised.value.code == USAGE


def test_run_with_no_path_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as raised:
        parse("run", "--docker")
    assert raised.value.code == USAGE


def test_two_backends_at_once_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as raised:
        parse("run", "--docker", "--cowork", "plugin/evals")
    assert raised.value.code == USAGE


def test_run_all_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as raised:
        parse("run", "--all", "plugin/evals")
    assert raised.value.code == USAGE


def test_test_cowork_is_a_usage_error() -> None:
    """That backend is not a member of the group, so there is no refusal message."""
    with pytest.raises(SystemExit) as raised:
        parse("test", "--cowork", "plugin/tests")
    assert raised.value.code == USAGE


def test_setup_cowork_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as raised:
        parse("setup", "--cowork")
    assert raised.value.code == USAGE


def test_venv_is_an_unknown_option_on_every_verb() -> None:
    for argv in (
        ("run", "--venv", "plugin/evals"),
        ("test", "--venv", "plugin/tests"),
        ("setup", "--venv"),
        ("check", "--venv"),
        ("prune", "--venv"),
    ):
        with pytest.raises(SystemExit) as raised:
            parse(*argv)
        assert raised.value.code == USAGE


def test_an_unknown_option_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as raised:
        parse("run", "--docker", "plugin/evals", "--invented")
    assert raised.value.code == USAGE


# The refusals a backend makes, which are values main returns.


def test_the_cowork_backend_accepts_runs_judge_model_and_timeout_seconds() -> None:
    args = parse(
        "run",
        "--cowork",
        "plugin/evals",
        "--runs",
        "2",
        "--judge-model",
        "haiku",
        "--timeout-seconds",
        "900",
    )
    assert (args.runs, args.judge_model, args.timeout_seconds) == (2, "haiku", 900.0)


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--model", "sonnet"),
        ("--allow-tools", "Bash"),
        ("--max-cost-usd", "3"),
        ("--ablation", "with-without"),
        ("--delta-threshold", "0.2"),
    ],
)
def test_an_option_the_cowork_backend_refuses_returns_two(option, value, capsys) -> None:
    assert main(["run", "--cowork", "plugin/evals", option, value]) == USAGE
    assert f"{option} is not accepted on --cowork" in capsys.readouterr().err


def test_the_ablation_options_are_accepted_on_docker(tmp_path) -> None:
    """Both are the container backend's, and neither reaches the CoWork backend."""
    args = parse(
        "run", "--docker", "plugin/evals", "--ablation", "with-without", "--delta-threshold", "0.2"
    )
    assert (args.ablation, args.delta_threshold) == ("with-without", 0.2)


def test_an_unconfigured_repository_runs_one_arm(working_directory, tmp_path) -> None:
    """Off is the default, because the arm runs every case twice."""
    with working_directory(tmp_path):
        assert Config.load().eval.ablation == "none"
        assert cli._options(parse("run", "--docker", "evals"), Config(), ()).ablation == "none"


def test_the_delta_threshold_option_beats_the_file(tmp_path) -> None:
    configured = Config(eval=EvalSection(delta_threshold=0.5))
    typed = parse("run", "--docker", "evals", "--delta-threshold", "0.1")
    untyped = parse("run", "--docker", "evals")
    assert cli._delta_threshold(typed, configured) == 0.1
    assert cli._delta_threshold(untyped, configured) == 0.5
    assert cli._delta_threshold(untyped, Config()) == 0


def test_an_unknown_ablation_value_is_refused_by_the_parser() -> None:
    with pytest.raises(SystemExit) as raised:
        parse("run", "--docker", "evals", "--ablation", "with-only")
    assert raised.value.code == USAGE


def test_build_missing_is_refused_on_cowork(capsys) -> None:
    assert main(["run", "--cowork", "plugin/evals", "--build-missing"]) == USAGE
    assert "--build-missing is not accepted on --cowork" in capsys.readouterr().err


@pytest.mark.parametrize("form", ["--keep-traces", "--no-keep-traces"])
def test_either_form_of_the_traces_option_is_accepted_on_both_backends(form) -> None:
    """Both backends keep the same three artefacts, so neither refuses the option."""
    for backend in ("--docker", "--cowork"):
        typed = parse("run", backend, "plugin/evals", form).keep_traces
        assert typed is (form == "--keep-traces")


# One ladder, so an option is checked as the file is. docs/library.md.


@pytest.mark.parametrize(
    ("option", "value", "says"),
    [
        ("--delta-threshold", "5", "expected a number from 0 to 1"),
        ("--delta-threshold", "-1", "expected a number at or above zero"),
        ("--max-cost-usd", "-5", "expected a number at or above zero"),
        ("--runs", "-3", "expected an integer at or above zero"),
        ("--runs", "99", "expected an integer at or below 50"),
    ],
)
def test_a_value_the_file_would_refuse_is_refused_on_the_command_line(
    option, value, says, capsys
) -> None:
    """The option is otherwise the way around every check the file gets."""
    assert main(["run", "--docker", "plugin/evals", option, value]) == USAGE
    printed = capsys.readouterr().err
    assert printed.startswith(f"{option}: ")
    assert says in printed


def test_the_option_and_the_file_refuse_the_same_value_for_the_same_reason() -> None:
    """Both rungs run one converter, so neither can drift from the other."""
    with pytest.raises(CoWorkError) as from_file:
        EvalSection(delta_threshold=5)
    with pytest.raises(CoWorkError) as from_option:
        checked(EvalSection, "delta_threshold", 5, name="--delta-threshold")
    assert str(from_file.value) == "eval.delta_threshold: expected a number from 0 to 1, got 5"
    assert str(from_option.value) == "--delta-threshold: expected a number from 0 to 1, got 5"
    assert from_file.value.code == from_option.value.code == USAGE


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--delta-threshold", "0.4"),
        ("--max-cost-usd", "3"),
        ("--runs", "50"),
        ("--judge-model", "haiku"),
    ],
)
def test_a_value_the_file_accepts_is_accepted_on_the_command_line(option, value) -> None:
    assert cli.bad_value(parse("run", "--docker", "plugin/evals", option, value)) is None


def test_the_cowork_timeout_is_checked_as_its_setting_is(capsys) -> None:
    """`--timeout-seconds` is `cowork.run_timeout`, so it takes that key's check."""
    assert main(["run", "--cowork", "plugin/evals", "--timeout-seconds", "-5"]) == USAGE
    assert "--timeout-seconds: expected a number at or above zero" in capsys.readouterr().err


def test_an_untyped_option_is_not_checked() -> None:
    """Nothing was typed, so the file decides and there is no value to refuse."""
    assert cli.bad_value(parse("run", "--docker", "plugin/evals")) is None
    assert cli.bad_value(parse("check", "--docker")) is None


@pytest.mark.parametrize("backend", ["--docker", "--cowork", "--all"])
def test_a_verb_that_does_not_carry_a_refused_option_refuses_nothing(backend) -> None:
    """`check` takes a backend and nothing else, so an option it never had is not typed."""
    assert cli.refusal(parse("check", backend)) is None


def test_timeout_seconds_is_refused_on_docker(capsys) -> None:
    assert main(["run", "--docker", "plugin/evals", "--timeout-seconds", "900"]) == USAGE
    assert "--timeout-seconds is not accepted on --docker" in capsys.readouterr().err


def test_require_coverage_is_accepted_on_both_backends() -> None:
    """It reads the tree and not a backend, so no backend refuses it."""
    for backend in ("--docker", "--cowork"):
        assert parse("run", backend, "plugin/evals", "--require-coverage").require_coverage


# The version, and no verb at all.


def test_the_version_is_the_installed_distribution_version(capsys) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == logs.distribution_version()


def test_no_verb_at_all_is_a_usage_error(capsys) -> None:
    assert main([]) == USAGE
    assert "a verb is required" in capsys.readouterr().err


# The verbs. Nothing below starts a daemon, a container or a CoWork session: the helpers
# each verb is made of are called directly wherever `main` would preflight a backend first.


MARKETPLACE = Path(__file__).resolve().parent.parent / "data" / "cli" / "marketplace"
VALIDATE = Path(__file__).resolve().parent.parent / "data" / "validate"
FIRST = MARKETPLACE / "first"
SECOND = MARKETPLACE / "second"
SMOKE = Path(__file__).resolve().parent.parent.parent / "plugins" / "smoke"
HISTORY = Path(__file__).resolve().parent.parent / "data" / "history"


def settings(tmp_path: Path, text: str = "") -> Config:
    path = tmp_path / "cowork_evals.yaml"
    path.write_text(text, encoding="utf-8")
    return Config.load(path)


# Scope resolution over a sweep.


def test_a_sweep_finds_every_plugin_root_below_the_path() -> None:
    assert plugin_roots(MARKETPLACE) == [FIRST, SECOND]


def test_a_manifest_with_no_evals_sibling_is_not_a_plugin_root() -> None:
    assert MARKETPLACE / "library" not in plugin_roots(MARKETPLACE)


def test_a_path_inside_one_root_is_that_root() -> None:
    assert plugin_roots(FIRST / "evals" / "greeter" / "hello") == [FIRST]


def test_one_root_runs_the_path_as_it_was_typed() -> None:
    case = FIRST / "evals" / "greeter" / "hello"
    assert cli._targets(str(case), [FIRST]) == [(FIRST, case)]


def test_a_sweep_runs_each_root_whole() -> None:
    assert cli._targets(str(MARKETPLACE), [FIRST, SECOND]) == [(FIRST, FIRST), (SECOND, SECOND)]


def test_a_sweep_is_scoped_all_and_a_single_plugin_is_named() -> None:
    assert logs.scope_name(MARKETPLACE, [FIRST, SECOND]) == "all"
    assert logs.scope_name(FIRST / "evals", [FIRST]) == "shared"


def test_two_plugins_sharing_a_manifest_name_get_two_directories(tmp_path: Path) -> None:
    """Neither result document overwrites the other, and the verdict reads both."""
    run = logs.run_dir(tmp_path, "all")
    made = [logs.plugin_dir(run, plugin_name(root)) for root in (FIRST, SECOND)]
    assert [directory.name for directory in made] == ["shared", "shared-2"]


def test_a_multi_plugin_path_is_refused_on_cowork(capsys) -> None:
    assert main(["run", "--cowork", str(MARKETPLACE)]) == USAGE
    assert "covers more than one plugin root on --cowork" in capsys.readouterr().err


def test_a_multi_plugin_path_is_refused_on_test(capsys) -> None:
    """pytest takes one rootdir."""
    assert main(["test", "--docker", str(MARKETPLACE)]) == USAGE
    assert "pytest takes one" in capsys.readouterr().err


def test_a_path_with_no_plugin_root_above_it_is_a_usage_error(tmp_path: Path, capsys) -> None:
    assert main(["run", "--docker", str(tmp_path)]) == USAGE
    assert "no .claude-plugin/plugin.json" in capsys.readouterr().err


# The selection.


def test_a_selection_matching_nothing_anywhere_is_counted_as_zero() -> None:
    targets = cli._targets(str(MARKETPLACE), [FIRST, SECOND])
    assert cli._selected(targets, ("nope",), None) == 0


def test_one_root_of_a_sweep_matching_nothing_is_not_zero() -> None:
    """`writer` is a tag no case carries, and `plugin` is carried in the second root only."""
    targets = cli._targets(str(MARKETPLACE), [FIRST, SECOND])
    assert cli._selected(targets, ("plugin",), None) == 1


def test_the_refusal_names_the_filters_that_matched_nothing() -> None:
    assert cli._filters(("greeter", "writer"), "hello-*") == (
        " under --tag greeter, --tag writer, --case hello-*"
    )
    assert cli._filters((), None) == ""


# Coverage.


def test_an_uncovered_skill_is_printed_and_fails_nothing(capsys) -> None:
    assert cli._validate([FIRST, SECOND], require_coverage=False) == []
    assert "uncovered:" in capsys.readouterr().out


def test_require_coverage_turns_the_same_tree_into_a_refusal() -> None:
    blocked = cli._validate([FIRST, SECOND], require_coverage=True)
    assert len(blocked) == 1
    assert str(SECOND / "skills" / "writer") in blocked[0]


def test_a_violation_blocks_whatever_the_coverage_flag_says() -> None:
    broken = Path(__file__).resolve().parent.parent / "data" / "validate" / "broken"
    assert cli._validate([broken], require_coverage=False)


# The three dry runs.


def test_the_docker_dry_run_prints_the_container_argument_list(tmp_path, capsys) -> None:
    args = parse("run", "--docker", str(FIRST / "evals"))
    root = tmp_path / "logs"
    config = settings(tmp_path)
    assert cli._dry_run(args, config, root, [(FIRST, FIRST / "evals")], ()) == 0
    printed = capsys.readouterr().out.splitlines()
    assert printed[0] == "# shared"
    # The directory name carries the second it was composed in, so read the printed one back
    # rather than compose a second name. The two differ whenever the test straddles a second.
    logs_dir = next(Path(arg.split(":", 1)[0]) for arg in printed if arg.endswith(":/work/logs:rw"))
    assert logs_dir.name == "shared"
    assert logs_dir.parent.parent == root
    assert logs_dir.parent.name.endswith("-shared")
    assert printed[1:] == Docker(config).run_argv(
        FIRST / "evals",
        logs_dir,
        cli._options(args, config, ()),
    )


def test_the_docker_dry_run_creates_no_run_directory(tmp_path, capsys) -> None:
    args = parse("run", "--docker", str(FIRST / "evals"))
    root = tmp_path / "logs"
    cli._dry_run(args, settings(tmp_path), root, [(FIRST, FIRST / "evals")], ())
    capsys.readouterr()
    assert not root.exists()


# A name no machine sets, and a value to prove is never printed. `monkeypatch.setenv` sets a
# real variable in this process, which is the environment the backend reads. docs/docker.md.
PROBE = "COWORK_EVALS_TEST_PROBE"
PROBE_VALUE = "probe-value-not-a-secret"
FORWARDS = f"docker:\n  env_passthrough: [{PROBE}]\n"


def test_the_docker_dry_run_prints_the_forwarded_name_and_not_its_value(
    tmp_path, capsys, monkeypatch
) -> None:
    monkeypatch.setenv(PROBE, PROBE_VALUE)
    args = parse("run", "--docker", str(FIRST / "evals"))
    config = settings(tmp_path, FORWARDS)
    assert cli._dry_run(args, config, tmp_path / "logs", [(FIRST, FIRST / "evals")], ()) == 0
    printed = capsys.readouterr().out
    assert f"{PROBE}=<not shown>" in printed.splitlines()
    assert PROBE_VALUE not in printed


def test_a_dry_run_names_a_configured_variable_the_host_has_not_set(
    tmp_path, capsys, monkeypatch
) -> None:
    """It skips the preflight, so it reads no value and prints what is configured."""
    monkeypatch.delenv(PROBE, raising=False)
    config = settings(tmp_path, FORWARDS)
    assert cli._run(parse("run", "--docker", str(FIRST / "evals"), "--dry-run"), config) == 0
    printed = capsys.readouterr()
    assert f"{PROBE}=<not shown>" in printed.out.splitlines()
    assert PROBE not in printed.err


def test_the_cowork_dry_run_prints_a_case_its_skips_and_the_arithmetic(tmp_path, capsys) -> None:
    """That backend builds no command line, so it prints what it would submit instead."""
    log = tmp_path / "runs.jsonl"
    log.write_text("", encoding="utf-8")
    config = settings(tmp_path, f"cowork:\n  max_runs: 50\n  run_log: {log}\n")
    args = parse("run", "--cowork", str(SECOND / "evals"))
    assert cli._dry_run(args, config, tmp_path / "logs", [(SECOND, SECOND / "evals")], ()) == 0
    printed = capsys.readouterr().out.splitlines()
    assert printed == [
        "# shared",
        "second-hello: runs 1, timeout 1800.0s",
        "second-compose: runs 1, timeout 1800.0s",
        "2 submissions planned, 0 already made in the last 24 hours, max_runs is 50",
    ]


def test_the_cowork_dry_run_names_what_each_declared_case_declares(tmp_path, capsys) -> None:
    log = tmp_path / "runs.jsonl"
    log.write_text("", encoding="utf-8")
    config = settings(tmp_path, f"cowork:\n  run_log: {log}\n")
    tree = Path(__file__).resolve().parent.parent / "data" / "cases" / "tree"
    args = parse("run", "--cowork", str(tree / "evals"))
    cli._dry_run(args, config, tmp_path / "logs", [(tree, tree / "evals")], ())
    printed = capsys.readouterr().out
    assert "  declared: no-cowork: max_turns: no turn cap reaches a CoWork session" in printed
    assert "  declared: no-cowork: context.add_dirs: nothing stages files into the VM" in printed


def test_the_test_dry_run_prints_the_pytest_container_and_starts_none(capsys) -> None:
    """The list is asserted field by field in test_pytest_image.py. This is the verb.

    `Config.load()` is what `main` reads, so the comparison is against the same
    configuration and not against the built-in defaults.
    """
    assert main(["test", "--docker", str(SMOKE / "tests"), "--dry-run", "--", "-q"]) == 0
    assert capsys.readouterr().out.splitlines() == PytestImage(Config.load()).run_argv(
        SMOKE / "tests", pytest_args=("-q",)
    )


# The cost ceiling.


def test_the_spend_is_summed_over_the_documents_written_so_far(tmp_path: Path) -> None:
    directory = tmp_path / "run"
    documents = Path(__file__).resolve().parent.parent / "data" / "results"
    for name in ("mail", "writer"):
        (directory / name).mkdir(parents=True)
        (directory / name / RESULT_NAME).write_text(
            (documents / "pass.json").read_text(), encoding="utf-8"
        )
    assert results.spend(directory) == pytest.approx(0.114)


def test_a_directory_with_no_document_has_spent_nothing(tmp_path: Path) -> None:
    (tmp_path / "mail").mkdir()
    assert results.spend(tmp_path) == 0.0


def test_a_ceiling_of_zero_stops_the_sweep_before_the_first_plugin(tmp_path, capsys) -> None:
    """`image=None` is the CoWork backend, so the backend flag and the configuration say so.

    `consent: none` is what an unattended run sets, and it is why no modal appears here. It
    is a configuration value and not a test seam: nothing is injected. ../README.md.
    """
    config = settings(tmp_path, "eval:\n  max_cost_total_usd: 0\ncowork:\n  consent: none\n")
    args = parse("run", "--cowork", str(MARKETPLACE))
    directory = logs.run_dir(tmp_path / "logs", "all")
    swept = cli._each_plugin(
        args, config, directory, [(FIRST, FIRST), (SECOND, SECOND)], (), image=None
    )
    capsys.readouterr()
    assert len(swept.warnings) == 1
    assert "the total cost ceiling stopped the sweep" in swept.warnings[0]
    assert "eval.max_cost_total_usd is 0" in swept.warnings[0]
    assert swept.roots == {}
    assert not list(directory.iterdir())


# setup, check and prune.


def test_check_returns_three_and_names_every_unmet_condition(tmp_path, capsys) -> None:
    """Returning 0 on a ready machine is the integration tier's, in integration/test_cli.py.

    Nothing in the unit tier can make a backend ready, and no `if` here decides whether to
    assert. See ../README.md.
    """
    config = settings(tmp_path, "cowork:\n  profile: /nowhere-at-all\n")
    args = parse("check", "--cowork")
    assert cli._check(args, config) == 3
    assert "no readable sessions root" in capsys.readouterr().err


def _plugin(root: Path, *, portable: bool) -> Path:
    """One plugin, one skill, one case, one grader. `portable` decides one frontmatter key.

    `allowed_tools` is honoured by the container backend and not by CoWork, so a case writing
    it out carries `no-cowork` and is not submitted there. Nothing else differs.
    """
    plugin = root / "one"
    case = plugin / "evals" / "greeter" / "only"
    (case / "graders").mkdir(parents=True)
    (plugin / ".claude-plugin").mkdir()
    (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "one"}')
    (plugin / "skills" / "greeter").mkdir(parents=True)
    (plugin / "skills" / "greeter" / "SKILL.md").write_text("---\nname: greeter\n---\n")
    unhonoured = "" if portable else "allowed_tools: [Skill]\n"
    tags = "[greeter]" if portable else "[greeter, no-cowork]"
    (case / "prompt.md").write_text(
        f"---\nname: only\ntags: {tags}\nplugins: ['../../..']\n{unhonoured}---\n\nSay hello.\n"
    )
    (case / "graders" / "said.md").write_text(
        "---\ntype: regex\ntarget: last_message\npattern: 'hello'\n---\n"
    )
    return plugin


def test_a_dry_run_validates_with_no_backend_reachable(tmp_path, capsys) -> None:
    """Nothing behind the preflight is reached by a dry run, so nothing blocks it.

    The profile names a directory that is not there, which is what an unconfigured consumer
    has. The case still validates and the dry run still reports what would run.
    """
    plugin = _plugin(tmp_path, portable=True)
    config = settings(tmp_path, "cowork:\n  profile: /nowhere-at-all\n")
    assert cli._run(parse("run", "--cowork", str(plugin), "--dry-run"), config) == 0
    printed = capsys.readouterr()
    assert "1 submissions planned" in printed.out
    assert "no readable sessions root" not in printed.err


def test_a_dry_run_still_refuses_a_malformed_case(tmp_path, capsys) -> None:
    """Dropping the preflight drops no validation. A bad case is exit 3 either way."""
    config = settings(tmp_path, "cowork:\n  profile: /nowhere-at-all\n")
    args = parse("run", "--cowork", str(VALIDATE / "broken"), "--dry-run")
    assert cli._run(args, config) == 3
    assert capsys.readouterr().err.strip()


def test_a_dry_run_of_a_suite_that_declares_every_case_passes(tmp_path, capsys) -> None:
    """A declared case is counted rather than failed, so the suite plans nothing and passes."""
    plugin = _plugin(tmp_path, portable=False)
    config = settings(tmp_path, "cowork:\n  profile: /nowhere-at-all\n")
    assert cli._run(parse("run", "--cowork", str(plugin), "--dry-run"), config) == 0
    printed = capsys.readouterr()
    assert "declared: no-cowork: allowed_tools" in printed.out
    assert "0 submissions planned" in printed.out
    assert printed.err == ""


def test_the_same_suite_is_a_pass_on_docker_too(tmp_path, capsys) -> None:
    """That backend honours the key, and the tag is a tag there."""
    plugin = _plugin(tmp_path, portable=False)
    config = settings(tmp_path, "cowork:\n  profile: /nowhere-at-all\n")
    assert cli._run(parse("run", "--docker", str(plugin), "--dry-run"), config) == 0
    assert capsys.readouterr().err == ""


def test_an_uncovered_skill_prints_once_and_on_one_stream(tmp_path, capsys) -> None:
    """Coverage is a report, so it is stdout and fails nothing."""
    config = settings(tmp_path, "cowork:\n  profile: /nowhere-at-all\n")
    args = parse("run", "--cowork", str(VALIDATE / "uncovered"), "--dry-run")
    assert cli._run(args, config) == 0
    printed = capsys.readouterr()
    assert printed.out.count("uncovered: ") == printed.out.count("no eval directory")
    assert "no eval directory" not in printed.err


def test_require_coverage_refuses_once_and_not_on_both_streams(tmp_path, capsys) -> None:
    """Under the flag a gap is a refusal, so it is stderr alone and never printed twice."""
    config = settings(tmp_path, "cowork:\n  profile: /nowhere-at-all\n")
    args = parse("run", "--cowork", str(VALIDATE / "uncovered"), "--dry-run", "--require-coverage")
    assert cli._run(args, config) == 3
    printed = capsys.readouterr()
    assert "no eval directory" in printed.err
    assert "no eval directory" not in printed.out


def test_check_all_names_every_backend_and_states_a_ready_one(tmp_path, capsys) -> None:
    """A ready backend is stated. Silence is what made a report indistinguishable from a
    backend that was never reached.

    The whole report goes to stdout in backend order, so it cannot interleave. Which backend
    is ready on the machine running this is not asserted: that is the integration tier's.
    """
    config = settings(tmp_path, "cowork:\n  profile: /nowhere-at-all\n")
    args = parse("check", "--all")
    code = cli._check(args, config)
    printed = capsys.readouterr()
    assert code == 3
    for backend in preflight.BACKENDS:
        assert f"{backend}: " in printed.out
    assert "no readable sessions root" in printed.out
    assert printed.err == ""


def test_a_named_backend_keeps_its_unmet_lines_on_stderr(tmp_path, capsys) -> None:
    """One backend is a refusal, not a report, and neither names a backend in its output."""
    config = settings(tmp_path, "cowork:\n  profile: /nowhere-at-all\n")
    assert cli._check(parse("check", "--cowork"), config) == 3
    printed = capsys.readouterr()
    assert "no readable sessions root" in printed.err
    assert printed.out == ""


# panel.


def test_panel_takes_a_path_and_its_three_options() -> None:
    args = parse("panel", "plugin/evals", "--markdown", "p.md", "--json", "p.json", "--removed")
    assert args.verb == "panel"
    assert args.path == "plugin/evals"
    assert args.markdown == "p.md"
    assert args.json == "p.json"
    assert args.removed


def test_panel_takes_no_backend() -> None:
    """It renders both columns and reaches neither, so a backend flag is unknown."""
    with pytest.raises(SystemExit) as raised:
        parse("panel", "--docker", "plugin/evals")
    assert raised.value.code == USAGE


def test_panel_prints_one_row_per_case_under_the_path(tmp_path, capsys) -> None:
    config = settings(tmp_path, f"panel:\n  root: {tmp_path / 'history'}\n")
    assert cli._panel(parse("panel", str(SMOKE)), config) == OK
    printed = capsys.readouterr()
    lines = printed.out.splitlines()
    assert lines[0].split() == list(panel.COLUMNS)
    assert len(lines) == 5
    assert printed.err == ""


def test_panel_writes_the_two_files_it_is_given(tmp_path, capsys) -> None:
    config = settings(tmp_path, f"panel:\n  root: {tmp_path / 'history'}\n")
    markdown = tmp_path / "panel.md"
    snapshot = tmp_path / "panel.json"
    args = parse("panel", str(SMOKE), "--markdown", str(markdown), "--json", str(snapshot))
    assert cli._panel(args, config) == OK
    capsys.readouterr()
    assert markdown.read_text().count("| smoke |") == 4
    assert len(json.loads(snapshot.read_text())["rows"]) == 4


def test_a_panel_path_selecting_no_case_returns_two(tmp_path, capsys) -> None:
    """The same refusal `run` makes, so a mistyped path never reads as an empty repository."""
    config = settings(tmp_path, f"panel:\n  root: {tmp_path / 'history'}\n")
    assert cli._panel(parse("panel", str(MARKETPLACE / "library")), config) == USAGE
    assert "selects no case" in capsys.readouterr().err


def test_an_unparsable_history_line_warns_and_leaves_the_exit_code_at_zero(
    tmp_path, capsys
) -> None:
    """A record is one line, so one truncated line loses one measurement and no row."""
    history = tmp_path / "history"
    file = panel.path(history, "smoke", "evals/plugin/python-version")
    file.parent.mkdir(parents=True)
    file.write_bytes((HISTORY / "truncated.jsonl").read_bytes())
    config = settings(tmp_path, f"panel:\n  root: {history}\n")
    assert cli._panel(parse("panel", str(SMOKE)), config) == OK
    printed = capsys.readouterr()
    assert printed.err.startswith("panel: ")
    assert "pass" in printed.out


# prune.


def test_prune_with_no_selection_flag_returns_two(capsys) -> None:
    assert main(["prune"]) == USAGE
    assert "prune takes --docker, --logs, --history" in capsys.readouterr().err


def test_prune_takes_history_beside_the_other_two(tmp_path: Path) -> None:
    args = parse("prune", "--logs", "--history", "--docker", "--older-than", "7")
    assert args.logs and args.history and args.docker
    assert args.older_than == 7


def test_prune_history_deletes_a_record_under_the_panel_root(tmp_path, capsys) -> None:
    """`--out` names the log root, and the history root is `panel.root`. docs/panel.md."""
    history = tmp_path / "history"
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    panel.append(
        history,
        [
            {
                "schemaVersion": 1,
                "plugin": "smoke",
                "dir": "evals/plugin/one",
                "backend": "docker",
                "startedAt": old,
                "outcome": "pass",
            }
        ],
    )
    config = settings(tmp_path, f"panel:\n  root: {history}\n")
    args = parse("prune", "--history", "--out", str(tmp_path / "elsewhere"))
    assert cli._prune(args, config) == 0
    assert "pruned " in capsys.readouterr().out
    assert not (history / "smoke").exists()


def test_prune_logs_deletes_under_the_resolved_root(tmp_path, capsys) -> None:
    root = tmp_path / "elsewhere"
    stamp = (datetime.now() - timedelta(days=40)).strftime(logs.STAMP_FORMAT)
    old = root / f"{stamp}-shared"
    old.mkdir(parents=True)
    assert main(["prune", "--logs", "--out", str(root)]) == 0
    assert f"removed {old}" in capsys.readouterr().out
    assert not old.exists()


def test_prune_logs_keeps_a_run_inside_the_age(tmp_path) -> None:
    root = tmp_path / "elsewhere"
    stamp = datetime.now().strftime(logs.STAMP_FORMAT)
    young = root / f"{stamp}-shared"
    young.mkdir(parents=True)
    assert main(["prune", "--logs", "--older-than", "1", "--out", str(root)]) == 0
    assert young.is_dir()


def test_a_prune_keeps_the_current_digest_of_each_image() -> None:
    """The two images a `setup --docker` just built are never removed, at any age."""
    cutoff = datetime(2026, 9, 9)
    old = datetime(2026, 1, 1)
    inventory = [
        ("cowork-evals:current00000", old),
        ("cowork-evals-test:current0", old),
        ("cowork-evals:stale0000000", old),
    ]
    current = {"cowork-evals:current00000", "cowork-evals-test:current0"}
    assert cli._stale(inventory, current, cutoff) == ["cowork-evals:stale0000000"]


def test_a_prune_keeps_an_image_built_after_the_cutoff() -> None:
    cutoff = datetime(2026, 9, 9)
    inventory = [
        ("cowork-evals:young000000", datetime(2026, 9, 9, 0, 0, 1)),
        ("cowork-evals:old00000000", datetime(2026, 9, 8, 23, 59, 59)),
    ]
    assert cli._stale(inventory, current=set(), cutoff=cutoff) == ["cowork-evals:old00000000"]


def test_a_prune_of_nothing_removes_nothing() -> None:
    assert cli._stale([], set(), datetime(2026, 9, 9)) == []


# ask. Nothing below submits anything: the four refusals return before the driver is built,
# `--session` reads a session directory written by hand, and `--dry-run` builds a URL and
# reads a run log. The live submission is the integration tier's, in integration/test_cli.py.

SESSIONS = Path(__file__).resolve().parent.parent / "data" / "cowork" / "sessions"
ONE_TURN = SESSIONS / "acct0000" / "prof0000" / "one_turn"
TOOL_CALL = SESSIONS / "acct0000" / "prof0000" / "tool_call"


def ask_settings(tmp_path: Path) -> Config:
    """A configuration whose run log is this test's own, so no ceiling and no log is shared."""
    return settings(tmp_path, f"cowork:\n  run_log: {tmp_path / 'runs.jsonl'}\n")


@pytest.mark.parametrize(
    ("argv", "says"),
    [
        (("ask", "--cowork"), "there is nothing to print"),
        (("ask", "--cowork", "hi", "--session", "x"), "not both"),
        (("ask", "--cowork", "--session", "x", "--timeout-seconds", "60"), "nothing waits"),
        (("ask", "--cowork", "--session", "x", "--dry-run"), "nothing would be submitted"),
    ],
)
def test_each_ask_refusal_returns_two_and_names_what_was_typed(argv, says, capsys) -> None:
    assert main(list(argv)) == USAGE
    assert says in capsys.readouterr().err


def test_a_session_on_disk_prints_the_answer_on_stdout_and_the_footer_on_stderr(
    tmp_path: Path, capsys
) -> None:
    """The split is what makes `ask ... > answer.txt` hold the answer and nothing else."""
    args = parse("ask", "--cowork", "--session", str(ONE_TURN))
    assert cli._ask(args, ask_settings(tmp_path)) == OK
    printed = capsys.readouterr()
    assert printed.out == "PONG\n"
    assert f"session: {ONE_TURN}" in printed.err
    assert "assistant turns: 1" in printed.err
    assert "outputs: outputs/marker.txt" in printed.err


def test_a_footer_line_with_no_value_is_not_printed(tmp_path: Path, capsys) -> None:
    """That session called no tool and wrote no diagnostic log, so neither line is there."""
    args = parse("ask", "--cowork", "--session", str(ONE_TURN))
    cli._ask(args, ask_settings(tmp_path))
    printed = capsys.readouterr().err
    assert "tools:" not in printed
    assert "log:" not in printed


def test_the_footer_names_every_tool_the_session_called(tmp_path: Path, capsys) -> None:
    args = parse("ask", "--cowork", "--session", str(TOOL_CALL))
    assert cli._ask(args, ask_settings(tmp_path)) == OK
    assert "tools: mcp__workspace__bash, mcp__workspace__bash" in capsys.readouterr().err


def test_json_prints_the_session_document_and_nothing_on_stderr(tmp_path: Path, capsys) -> None:
    args = parse("ask", "--cowork", "--session", str(ONE_TURN), "--json")
    assert cli._ask(args, ask_settings(tmp_path)) == OK
    printed = capsys.readouterr()
    document = json.loads(printed.out)
    assert document["session_dir"] == str(ONE_TURN)
    assert document["final_text"] == "PONG"
    assert printed.err == ""


def test_a_session_directory_that_is_not_there_fails_and_says_so(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "no-such-session"
    args = parse("ask", "--cowork", "--session", str(missing))
    assert cli._ask(args, ask_settings(tmp_path)) == FAILED
    assert f"{missing}: no such session directory" in capsys.readouterr().err


def test_a_session_that_produced_no_assistant_text_fails_with_the_drivers_code(
    tmp_path: Path, capsys
) -> None:
    """Code 8 is the driver's, and the verb carries it into the message rather than losing it."""
    empty = SESSIONS / "acct0000" / "prof0000" / "no_transcript"
    args = parse("ask", "--cowork", "--session", str(empty))
    assert cli._ask(args, ask_settings(tmp_path)) == FAILED
    assert "8: " in capsys.readouterr().err


def test_a_dry_run_prints_the_deep_link_carrying_the_encoded_prompt(tmp_path: Path, capsys) -> None:
    args = parse("ask", "--cowork", "--dry-run", "say hello & wait")
    assert cli._ask(args, ask_settings(tmp_path)) == OK
    printed = capsys.readouterr()
    assert printed.out.strip() == (
        "claude://claude.ai/new?q=say%20hello%20%26%20wait&surface=cowork"
    )
    assert "1 submission planned, 0 already made in the last 24 hours" in printed.err


def test_a_dry_run_writes_no_run_log_entry(tmp_path: Path, capsys) -> None:
    """It fires nothing, so it costs nothing and the ceiling does not move."""
    args = parse("ask", "--cowork", "--dry-run", "hello")
    assert cli._ask(args, ask_settings(tmp_path)) == OK
    capsys.readouterr()
    assert not (tmp_path / "runs.jsonl").exists()


def test_a_dry_run_needs_no_profile_and_no_backend(tmp_path: Path, capsys) -> None:
    """Nothing behind the preflight is reached: a URL is built and a run log is read.

    That is the same rule `run --dry-run` follows, and it is what lets a dry run be checked
    on a machine with no CoWork at all.
    """
    config = settings(
        tmp_path,
        f"cowork:\n  profile: /nowhere-at-all\n  run_log: {tmp_path / 'runs.jsonl'}\n",
    )
    assert cli._ask(parse("ask", "--cowork", "--dry-run", "hello"), config) == OK
    assert "no readable sessions root" not in capsys.readouterr().err


def test_a_prompt_of_one_dash_is_read_from_standard_input(tmp_path: Path) -> None:
    """The real executable, because standard input is a descriptor and not a Python name.

    A dry run, so nothing is submitted: what is asserted is that the prompt the deep link
    carries came off the pipe rather than off the command line.
    """
    (tmp_path / "cowork_evals.yaml").write_text(
        f"cowork:\n  run_log: {tmp_path / 'runs.jsonl'}\n", encoding="utf-8"
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from cowork_evals.cli import console_main; console_main()",
            "ask",
            "--cowork",
            "--dry-run",
            cli.STDIN,
        ],
        input="from the pipe",
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == OK, completed.stderr
    assert completed.stdout.strip() == ("claude://claude.ai/new?q=from%20the%20pipe&surface=cowork")


# What a raised driver code becomes. The error objects below are the driver's own, built
# with the codes docs/cowork_driver.md gives them, and the collection behind code 7 reads
# the session fixture on disk with the real reader.


def test_a_driver_refusal_reaches_the_preflight_code(tmp_path: Path, capsys) -> None:
    """Code 2 is configuration or the rate ceiling, which is the preflight class."""
    args = parse("ask", "--cowork", "hi")
    error = CoWorkError(2, "max_runs is 0")
    assert cli._ask_failure(args, ask_settings(tmp_path), "hi", error) == PREFLIGHT_FAILED
    assert "2: max_runs is 0" in capsys.readouterr().err


def test_every_other_driver_code_fails_and_prints_no_session_document(
    tmp_path: Path, capsys
) -> None:
    args = parse("ask", "--cowork", "hi")
    error = CoWorkError(6, "the deep link did not open")
    assert cli._ask_failure(args, ask_settings(tmp_path), "hi", error) == FAILED
    printed = capsys.readouterr()
    assert printed.out == ""
    assert "6: the deep link did not open" in printed.err


def test_a_run_timeout_prints_what_the_session_produced_and_still_fails(
    tmp_path: Path, capsys
) -> None:
    """The session keeps running in the VM, so what it produced by then is worth reading."""
    error = CoWorkError(7, "the run timed out", session_dir=ONE_TURN)
    args = parse("ask", "--cowork", "hi")
    assert cli._ask_failure(args, ask_settings(tmp_path), "hi", error) == FAILED
    printed = capsys.readouterr()
    assert printed.out == "PONG\n"
    assert "7: the run timed out" in printed.err
    assert f"session: {ONE_TURN}" in printed.err


def test_a_run_timeout_that_produced_no_text_prints_the_collection_failure(
    tmp_path: Path, capsys
) -> None:
    """Code 8 from the collection, and the timeout is still what the verb exits on."""
    empty = SESSIONS / "acct0000" / "prof0000" / "no_transcript"
    error = CoWorkError(7, "the run timed out", session_dir=empty)
    args = parse("ask", "--cowork", "hi")
    assert cli._ask_failure(args, ask_settings(tmp_path), "hi", error) == FAILED
    printed = capsys.readouterr()
    assert printed.out == ""
    assert "8: " in printed.err


def test_a_run_timeout_with_no_session_directory_is_a_plain_failure(tmp_path: Path, capsys) -> None:
    """Nothing was discovered, so there is nothing to collect and nothing to print."""
    args = parse("ask", "--cowork", "hi")
    error = CoWorkError(7, "the run timed out")
    assert cli._ask_failure(args, ask_settings(tmp_path), "hi", error) == FAILED
    assert capsys.readouterr().out == ""
