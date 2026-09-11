"""The parser, the refusals and the exit codes.

The parser under test is the real one, built by `build_parser`. `argparse` raises
`SystemExit(2)` from inside `parse_args`, and the rows that reach it assert on that; every
other refusal is a value `main` returns. The surface is docs/cli.md. See ../README.md.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from cowork_evals import cli, logs, preflight, results
from cowork_evals.cases import plugin_name, plugin_roots
from cowork_evals.cli import USAGE, main, parse_args
from cowork_evals.config import Config, EvalSection
from cowork_evals.docker import Docker
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


def test_setup_takes_docker_alone() -> None:
    assert parse("setup", "--docker").backend == "docker"


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
    [("--model", "sonnet"), ("--allow-tools", "Bash"), ("--max-cost-usd", "3")],
)
def test_an_option_the_cowork_backend_refuses_returns_two(option, value, capsys) -> None:
    assert main(["run", "--cowork", "plugin/evals", option, value]) == USAGE
    assert f"{option} is not accepted on --cowork" in capsys.readouterr().err


def test_build_missing_is_refused_on_cowork(capsys) -> None:
    assert main(["run", "--cowork", "plugin/evals", "--build-missing"]) == USAGE
    assert "--build-missing is not accepted on --cowork" in capsys.readouterr().err


@pytest.mark.parametrize("form", ["--keep-traces", "--no-keep-traces"])
def test_either_form_of_the_traces_option_is_accepted_on_both_backends(form) -> None:
    """Both backends keep the same three artefacts, so neither refuses the option."""
    for backend in ("--docker", "--cowork"):
        typed = parse("run", backend, "plugin/evals", form).keep_traces
        assert typed is (form == "--keep-traces")


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
    """Neither result document overwrites the other, and the gate reads both."""
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
    assert printed[1:] == Docker(config).run_argv(
        FIRST / "evals",
        root / logs.run_dir_name("shared") / "shared",
        cli._options(args, config, ()),
    )


def test_the_docker_dry_run_creates_no_run_directory(tmp_path, capsys) -> None:
    args = parse("run", "--docker", str(FIRST / "evals"))
    root = tmp_path / "logs"
    cli._dry_run(args, settings(tmp_path), root, [(FIRST, FIRST / "evals")], ())
    capsys.readouterr()
    assert not root.exists()


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


def test_the_cowork_dry_run_names_every_skip(tmp_path, capsys) -> None:
    log = tmp_path / "runs.jsonl"
    log.write_text("", encoding="utf-8")
    config = settings(tmp_path, f"cowork:\n  run_log: {log}\n")
    tree = Path(__file__).resolve().parent.parent / "data" / "cases" / "tree"
    args = parse("run", "--cowork", str(tree / "evals"))
    cli._dry_run(args, config, tmp_path / "logs", [(tree, tree / "evals")], ())
    printed = capsys.readouterr().out
    assert "  skip: max_turns: no turn cap reaches a CoWork session" in printed
    assert "  skip: context.add_dirs: nothing stages files into the VM" in printed


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
    config = settings(tmp_path, "eval:\n  max_cost_total_usd: 0\n")
    args = parse("run", "--docker", str(MARKETPLACE))
    directory = logs.run_dir(tmp_path / "logs", "all")
    extra = cli._each_plugin(
        args, config, directory, [(FIRST, FIRST), (SECOND, SECOND)], (), image=None
    )
    capsys.readouterr()
    assert len(extra) == 1
    assert "the total cost ceiling stopped the sweep" in extra[0]
    assert "eval.max_cost_total_usd is 0" in extra[0]
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

    `allowed_tools` is honoured by the container backend and not by CoWork, so writing it out
    is what makes the case skipped there and the suite dead. Nothing else differs.
    """
    plugin = root / "one"
    case = plugin / "evals" / "greeter" / "only"
    (case / "graders").mkdir(parents=True)
    (plugin / ".claude-plugin").mkdir()
    (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "one"}')
    (plugin / "skills" / "greeter").mkdir(parents=True)
    (plugin / "skills" / "greeter" / "SKILL.md").write_text("---\nname: greeter\n---\n")
    unhonoured = "" if portable else "allowed_tools: [Skill]\n"
    (case / "prompt.md").write_text(
        f"---\nname: only\ntags: [greeter]\nplugins: ['../../..']\n{unhonoured}---\n\nSay hello.\n"
    )
    (case / "graders" / "said.md").write_text(
        "---\ntype: regex\ntarget: last_message\npattern: 'hello'\n---\n"
    )
    return plugin


def test_a_dry_run_validates_with_no_backend_reachable(tmp_path, capsys) -> None:
    """Nothing behind the preflight is reached by a dry run, so nothing gates it.

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


def test_a_dry_run_fails_when_every_case_is_skipped_on_cowork(tmp_path, capsys) -> None:
    """A suite dead on this backend would fail the gate, so the dry run says so."""
    plugin = _plugin(tmp_path, portable=False)
    config = settings(tmp_path, "cowork:\n  profile: /nowhere-at-all\n")
    assert cli._run(parse("run", "--cowork", str(plugin), "--dry-run"), config) == 1
    printed = capsys.readouterr()
    assert "skip: allowed_tools" in printed.out
    assert "0 submissions planned" in printed.out
    assert "the gate would fail" in printed.err


def test_the_same_dead_suite_is_not_a_failure_on_docker(tmp_path, capsys) -> None:
    """That backend honours the key, and its skips are the harness's own at run time."""
    plugin = _plugin(tmp_path, portable=False)
    config = settings(tmp_path, "cowork:\n  profile: /nowhere-at-all\n")
    assert cli._run(parse("run", "--docker", str(plugin), "--dry-run"), config) == 0
    assert "the gate would fail" not in capsys.readouterr().err


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


def test_prune_with_no_selection_flag_returns_two(capsys) -> None:
    assert main(["prune"]) == USAGE
    assert "prune takes --docker, --logs, or both" in capsys.readouterr().err


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
