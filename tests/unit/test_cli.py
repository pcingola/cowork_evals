"""The parser, the refusals, the verbs and the exit codes.

The parser under test is the real one. `argparse` raises `SystemExit(2)` from inside
`parse_args`, and the rows that reach it assert on that; every other refusal is a value `main`
returns. Nothing here starts a daemon, a container or a CoWork session: where `main` would
preflight a backend first, the verb's own function is called. `init` writes real files into a
`tmp_path`. The surface is docs/cli.md. See ../README.md.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from importlib import metadata
from pathlib import Path

import pytest

from cowork_evals import cli, logs, panel, resources
from cowork_evals.cli import FAILED, OK, PREFLIGHT_FAILED, USAGE, main, parse_args
from cowork_evals.config import Config, CoWorkError, EvalSection
from cowork_evals.cowork import SessionDocument
from cowork_evals.docker import Image

DATA = Path(__file__).resolve().parent.parent / "data"
MARKETPLACE = DATA / "cli" / "marketplace"
VALIDATE = DATA / "validate"
FIRST = MARKETPLACE / "first"
SECOND = MARKETPLACE / "second"
SMOKE = DATA.parent.parent / "plugins" / "smoke"
HISTORY = DATA / "history"
SESSIONS = DATA / "cowork" / "sessions" / "acct0000" / "prof0000"
ONE_TURN = SESSIONS / "one_turn"
TOOL_CALL = SESSIONS / "tool_call"
NO_TRANSCRIPT = SESSIONS / "no_transcript"
UNREADABLE_PROFILE = "cowork:\n  profile: /nowhere-at-all\n"

# A name no machine sets, and a value to prove is never printed. docs/docker.md.
PROBE = "COWORK_EVALS_TEST_PROBE"
PROBE_VALUE = "probe-value-not-a-secret"
FORWARDS = f"docker:\n  env_passthrough: [{PROBE}]\n"


def parse(*argv: str):
    return parse_args(list(argv))


def dry_run(tmp_path: Path, *argv: str):
    """`run --dry-run`, with its log root under `tmp_path` rather than this repository's."""
    return parse("run", *argv, "--dry-run", "--out", str(tmp_path / "logs"))


def settings(tmp_path: Path, text: str = "") -> Config:
    path = tmp_path / "cowork_evals.yaml"
    path.write_text(text, encoding="utf-8")
    return Config.load(path)


# The parse tree.


@pytest.mark.parametrize(
    "argv",
    [
        *[("ask", "--cowork", "hi", option, "x") for option in ("--runs", "--tag", "--case")],
        *[("ask", "--cowork", "hi", option, "x") for option in ("--out", "--model")],
        ("ask", "--docker", "hi"),
        ("ask", "hi"),
        ("login",),
        ("login", "--cowork"),
        ("login", "--docker", "--check", "--force"),
        ("run", "--docker", "plugin/evals", "--older-than", "7"),
        ("test", "--docker", "p", "--out", "x"),
        ("run", "--docker", "plugin/evals", "--", "-k", "parser"),
        ("run", "plugin/evals"),
        ("test", "plugin/tests"),
        ("setup",),
        ("check",),
        ("run", "--docker"),
        ("run", "--docker", "--cowork", "plugin/evals"),
        ("run", "--all", "plugin/evals"),
        ("test", "--cowork", "plugin/tests"),
        ("setup", "--cowork"),
        ("run", "--venv", "plugin/evals"),
        ("test", "--venv", "plugin/tests"),
        ("setup", "--venv"),
        ("check", "--venv"),
        ("prune", "--venv"),
        ("run", "--docker", "plugin/evals", "--invented"),
        ("run", "--docker", "evals", "--ablation", "with-only"),
        ("panel", "--docker", "plugin/evals"),
        ("docs", "--docker"),
        ("init", "--docker"),
    ],
)
def test_an_unknown_option_is_a_usage_error(argv: tuple[str, ...]) -> None:
    with pytest.raises(SystemExit) as raised:
        parse(*argv)
    assert raised.value.code == USAGE


def test_the_tail_begins_at_the_separator_and_argparse_claims_none_of_it() -> None:
    tail = ["-k", "parser", "--dry-run", "--build-missing", "--tb=short"]
    args = parse("test", "--docker", "plugin/tests", "--", *tail)
    assert args.pytest_args == tail
    assert not args.dry_run
    assert not args.build_missing


# The ladder, the accepted surface and the refusals. docs/cli.md, docs/library.md.


@pytest.mark.parametrize(
    ("resolve", "option", "field", "typed", "configured", "default"),
    [
        (cli._keeping, ("--keep-traces",), "keep_traces", True, False, True),
        (cli._keeping, ("--no-keep-traces",), "keep_traces", False, True, True),
        (cli._delta_threshold, ("--delta-threshold", "0.1"), "delta_threshold", 0.1, 0.5, 0),
    ],
)
def test_an_option_beats_the_file_and_the_file_beats_the_default(
    resolve, option, field, typed, configured, default
) -> None:
    file = Config(eval=EvalSection(**{field: configured}))
    assert resolve(parse("run", "--docker", "plugin/evals", *option), file) == typed
    assert resolve(parse("run", "--docker", "plugin/evals"), file) == configured
    assert resolve(parse("run", "--docker", "plugin/evals"), Config()) == default


@pytest.mark.parametrize(
    "argv",
    [
        *[("run", "--docker", "p", *cell) for cell in (("--runs", "50"), ("--model", "sonnet"))],
        ("run", "--docker", "p", "--allow-tools", "Bash"),
        ("run", "--docker", "p", "--max-cost-usd", "3"),
        ("run", "--docker", "p", "--ablation", "with-without", "--delta-threshold", "0.4"),
        ("run", "--docker", "p", "--build-missing"),
        ("run", "--cowork", "p", "--runs", "2", "--timeout-seconds", "900"),
        *[
            ("run", backend, "p", *cell)
            for backend in ("--docker", "--cowork")
            for cell in (
                ("--judge-model", "haiku"),
                ("--keep-traces",),
                ("--no-keep-traces",),
                ("--require-coverage",),
                ("--tag", "t", "--case", "c*", "--out", "o", "--dry-run"),
                (),
            )
        ],
        ("check", "--docker"),
        ("check", "--cowork"),
        ("check", "--all"),
    ],
)
def test_an_option_the_table_marks_yes_is_accepted(argv: tuple[str, ...]) -> None:
    args = parse(*argv)
    assert cli.refusal(args) is None
    assert cli.bad_value(args) is None


@pytest.mark.parametrize(
    ("backend", "option", "value"),
    [
        ("docker", "--timeout-seconds", "900"),
        ("cowork", "--model", "sonnet"),
        ("cowork", "--allow-tools", "Bash"),
        ("cowork", "--max-cost-usd", "3"),
        ("cowork", "--ablation", "with-without"),
        ("cowork", "--delta-threshold", "0.2"),
        ("cowork", "--build-missing", None),
    ],
)
def test_an_option_the_backend_refuses_returns_two(backend, option, value, capsys) -> None:
    typed = [option] if value is None else [option, value]
    assert main(["run", f"--{backend}", "plugin/evals", *typed]) == USAGE
    assert f"{option} is not accepted on --{backend}" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("backend", "option", "value", "says"),
    [
        ("--docker", "--delta-threshold", "5", "expected a number from 0 to 1"),
        ("--docker", "--delta-threshold", "-1", "expected a number at or above zero"),
        ("--docker", "--max-cost-usd", "-5", "expected a number at or above zero"),
        ("--docker", "--runs", "-3", "expected an integer at or above zero"),
        ("--docker", "--runs", "99", "expected an integer at or below 50"),
        ("--cowork", "--timeout-seconds", "-5", "expected a number at or above zero"),
    ],
)
def test_a_value_the_file_would_refuse_is_refused_on_the_command_line(
    backend, option, value, says, capsys
) -> None:
    assert main(["run", backend, "plugin/evals", option, value]) == USAGE
    printed = capsys.readouterr().err
    assert printed.startswith(f"{option}: ")
    assert says in printed


def test_the_version_is_the_installed_distribution_version(capsys) -> None:
    assert main(["--version"]) == OK
    assert capsys.readouterr().out.strip() == metadata.version("cowork-evals")


def test_no_verb_at_all_is_a_usage_error(capsys) -> None:
    assert main([]) == USAGE
    assert "a verb is required" in capsys.readouterr().err


# The path is the scope, and the selection.


@pytest.mark.parametrize(
    ("path", "roots", "expected"),
    [
        (
            FIRST / "evals" / "greeter" / "hello",
            [FIRST],
            [(FIRST, FIRST / "evals" / "greeter" / "hello")],
        ),
        (MARKETPLACE, [FIRST, SECOND], [(FIRST, FIRST), (SECOND, SECOND)]),
    ],
)
def test_one_root_runs_the_path_as_typed_and_a_sweep_runs_each_root_whole(
    path, roots, expected
) -> None:
    assert cli._targets(str(path), roots) == expected


@pytest.mark.parametrize(
    ("argv", "says"),
    [
        (("run", "--cowork", str(MARKETPLACE)), "covers more than one plugin root on --cowork"),
        (("test", "--docker", str(MARKETPLACE)), "pytest takes one"),
        (("run", "--docker", "{tmp}"), "no .claude-plugin/plugin.json"),
    ],
)
def test_a_path_the_verb_cannot_scope_is_a_usage_error(argv, says, tmp_path, capsys) -> None:
    assert main([arg.format(tmp=tmp_path) for arg in argv]) == USAGE
    assert says in capsys.readouterr().err


@pytest.mark.parametrize(("tag", "code"), [("nope", USAGE), ("plugin", OK)])
def test_a_selection_matching_nothing_anywhere_is_refused(tag, code, tmp_path, capsys) -> None:
    """`plugin` is carried in the second root only, and one root matching nothing is normal."""
    args = dry_run(tmp_path, "--docker", str(MARKETPLACE), "--tag", tag)
    assert cli._run(args, settings(tmp_path)) == code
    assert ("selects no case under --tag nope" in capsys.readouterr().err) is (code == USAGE)


# The dry runs. docs/cli.md "Dry run".


@pytest.mark.parametrize("probe_set", [True, False])
def test_the_docker_dry_run_prints_the_container_and_creates_nothing(probe_set, tmp_path) -> None:
    """The real executable, with the variable in the environment it hands the child or not.

    A dry run skips the preflight, so it reads no value and prints the configured name.
    """
    (tmp_path / "cowork_evals.yaml").write_text(FORWARDS, encoding="utf-8")
    env = {name: value for name, value in os.environ.items() if name != PROBE}
    if probe_set:
        env[PROBE] = PROBE_VALUE
    root = tmp_path / "logs"
    completed = subprocess.run(
        [sys.executable, "-c", "from cowork_evals.cli import console_main; console_main()"]
        + ["run", "--docker", str(FIRST / "evals"), "--dry-run", "--out", str(root)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == OK, completed.stderr
    printed = completed.stdout.splitlines()
    assert printed[0] == "# shared"
    mounted = [Path(line.split(":", 1)[0]) for line in printed if line.endswith(":/work/logs:rw")]
    assert len(mounted) == 1
    assert mounted[0].resolve().is_relative_to(root.resolve())
    assert f"{PROBE}=<not shown>" in printed
    assert PROBE_VALUE not in completed.stdout
    assert PROBE not in completed.stderr
    assert not root.exists()


def test_the_cowork_dry_run_prints_each_case_and_the_arithmetic(tmp_path, capsys) -> None:
    """That backend builds no command line, so it prints what it would submit instead."""
    log = tmp_path / "runs.jsonl"
    log.write_text("", encoding="utf-8")
    config = settings(tmp_path, f"cowork:\n  max_runs: 50\n  run_log: {log}\n")
    args = dry_run(tmp_path, "--cowork", str(SECOND / "evals"))
    assert cli._run(args, config) == OK
    assert capsys.readouterr().out.splitlines() == [
        "# shared",
        "second-hello: runs 1, timeout 1800.0s",
        "second-compose: runs 1, timeout 1800.0s",
        "2 submissions planned, 0 already made in the last 24 hours, max_runs is 50",
    ]


def test_the_test_dry_run_prints_the_pytest_container_and_starts_none(capsys) -> None:
    assert main(["test", "--docker", str(SMOKE / "tests"), "--dry-run", "--", "-q"]) == OK
    printed = capsys.readouterr().out.splitlines()
    assert printed[0] == "docker"
    assert any(line.startswith(f"{SMOKE}:") for line in printed)
    assert printed[-1] == "-q"


@pytest.mark.parametrize(
    ("backend", "tree", "expected"),
    [
        ("--cowork", "portable", ["1 submissions planned"]),
        ("--cowork", "declared", ["declared: no-cowork: allowed_tools", "0 submissions planned"]),
        ("--docker", "declared", []),
    ],
)
def test_a_dry_run_validates_with_no_backend_reachable(
    backend, tree, expected, tmp_path, capsys
) -> None:
    """A declared case is counted rather than failed, so a suite of them plans nothing and
    passes. The profile names a directory that is not there, as an unconfigured consumer has."""
    args = dry_run(tmp_path, backend, str(DATA / "cli" / tree / "one"))
    assert cli._run(args, settings(tmp_path, UNREADABLE_PROFILE)) == OK
    printed = capsys.readouterr()
    for line in expected:
        assert line in printed.out
    assert printed.err == ""


def test_a_dry_run_still_refuses_a_malformed_case(tmp_path, capsys) -> None:
    args = dry_run(tmp_path, "--cowork", str(VALIDATE / "broken"))
    assert cli._run(args, settings(tmp_path, UNREADABLE_PROFILE)) == PREFLIGHT_FAILED
    assert (
        f"{VALIDATE}/broken/evals/greeter/bad-case-yaml/case.yaml: required-key: name is required"
        in capsys.readouterr().err.splitlines()
    )


@pytest.mark.parametrize(
    ("flag", "code", "stream"),
    [((), OK, "out"), (("--require-coverage",), PREFLIGHT_FAILED, "err")],
)
def test_an_uncovered_skill_is_printed_once_on_one_stream(
    flag, code, stream, tmp_path, capsys
) -> None:
    """Coverage is a report on stdout. Under the flag a gap is a refusal, on stderr alone."""
    args = dry_run(tmp_path, "--cowork", str(VALIDATE / "uncovered"), *flag)
    assert cli._run(args, settings(tmp_path, UNREADABLE_PROFILE)) == code
    printed = capsys.readouterr()
    other = printed.err if stream == "out" else printed.out
    assert "no eval directory" in getattr(printed, stream)
    assert "no eval directory" not in other


def test_a_forwarded_variable_the_host_has_not_set_refuses_before_anything_is_created(
    tmp_path, capsys, monkeypatch
) -> None:
    monkeypatch.delenv(PROBE, raising=False)
    args = parse("run", "--docker", str(FIRST / "evals"), "--out", str(tmp_path / "logs"))
    assert cli._run(args, settings(tmp_path, FORWARDS)) == PREFLIGHT_FAILED
    assert any(PROBE in line for line in capsys.readouterr().err.splitlines())
    assert not (tmp_path / "logs").exists()


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


# check. Returning 0 on a ready machine is the integration tier's.


def test_a_named_backend_returns_three_with_its_unmet_lines_on_stderr(tmp_path, capsys) -> None:
    assert cli._check(parse("check", "--cowork"), settings(tmp_path, UNREADABLE_PROFILE)) == 3
    printed = capsys.readouterr()
    assert "no readable sessions root" in printed.err
    assert printed.out == ""


def test_check_all_names_every_backend_on_stdout(tmp_path, capsys) -> None:
    """Which backend is ready on the machine running this is the integration tier's."""
    assert cli._check(parse("check", "--all"), settings(tmp_path, UNREADABLE_PROFILE)) == 3
    printed = capsys.readouterr()
    for backend in ("docker", "cowork"):
        assert f"{backend}: " in printed.out
    assert "no readable sessions root" in printed.out
    assert printed.err == ""


# panel.


def test_panel_prints_one_row_per_case_under_the_path(tmp_path, capsys) -> None:
    config = settings(tmp_path, f"panel:\n  root: {tmp_path / 'history'}\n")
    assert cli._panel(parse("panel", str(SMOKE)), config) == OK
    printed = capsys.readouterr()
    lines = printed.out.splitlines()
    assert lines[0].split() == [
        *("plugin", "skill", "case", "description", "docker", "cowork"),
        *("score", "duration", "flake", "stale", "artefacts"),
    ]
    assert [line.split()[2] for line in lines[1:]] == [
        *("capped-turns", "checked-file", "python-version", "session-env", "writes-a-file"),
    ]
    assert printed.err == ""


def test_panel_writes_the_two_files_it_is_given(tmp_path, capsys) -> None:
    config = settings(tmp_path, f"panel:\n  root: {tmp_path / 'history'}\n")
    markdown = tmp_path / "panel.md"
    snapshot = tmp_path / "panel.json"
    args = parse("panel", str(SMOKE), "--markdown", str(markdown), "--json", str(snapshot))
    assert cli._panel(args, config) == OK
    capsys.readouterr()
    assert markdown.read_text().count("| smoke |") == 5
    assert len(panel.PanelSnapshot.model_validate_json(snapshot.read_text()).rows) == 5


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


def test_prune_history_deletes_a_record_under_the_panel_root(tmp_path, capsys) -> None:
    """`--out` names the log root, and the history root is `panel.root`. docs/panel.md."""
    history = tmp_path / "history"
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    record = panel.HistoryRecord(
        schema_version=1,
        invocation="20260903-090000-smoke",
        backend="docker",
        cowork_evals="0.4.0",
        plugin="smoke",
        case="one",
        dir="evals/plugin/one",
        outcome="pass",
        score=1.0,
        pass_rate=1.0,
        runs=1,
        duration_seconds=1.0,
        cost_usd=0.0,
        started_at=old,
    )
    panel.append(history, [record])
    config = settings(tmp_path, f"panel:\n  root: {history}\n")
    args = parse("prune", "--history", "--out", str(tmp_path / "elsewhere"))
    assert cli._prune(args, config) == OK
    assert "pruned " in capsys.readouterr().out
    assert not (history / "smoke").exists()


@pytest.mark.parametrize(
    ("days", "older_than", "removed"),
    [
        (31, (), True),
        (29, (), False),
        (2, ("--older-than", "1"), True),
        (0, ("--older-than", "1"), False),
    ],
)
def test_prune_logs_deletes_under_the_resolved_root(
    days, older_than, removed, tmp_path, capsys
) -> None:
    """The default age is 30 days."""
    root = tmp_path / "elsewhere"
    run = root / f"{(datetime.now() - timedelta(days=days)).strftime(logs.STAMP_FORMAT)}-shared"
    run.mkdir(parents=True)
    assert main(["prune", "--logs", *older_than, "--out", str(root)]) == OK
    assert (f"removed {run}" in capsys.readouterr().out) is removed
    assert run.is_dir() is not removed


OLD = datetime(2026, 1, 1)


@pytest.mark.parametrize(
    ("inventory", "current", "expected"),
    [
        (
            [
                Image("cowork-evals:current00000", OLD),
                Image("cowork-evals-test:current0", OLD),
                Image("cowork-evals:stale0000000", OLD),
            ],
            {"cowork-evals:current00000", "cowork-evals-test:current0"},
            ["cowork-evals:stale0000000"],
        ),
        (
            [
                Image("cowork-evals:young000000", datetime(2026, 9, 9, 0, 0, 1)),
                Image("cowork-evals:old00000000", datetime(2026, 9, 8, 23, 59, 59)),
            ],
            set(),
            ["cowork-evals:old00000000"],
        ),
        ([], set(), []),
    ],
)
def test_a_prune_removes_an_old_image_that_is_not_current(inventory, current, expected) -> None:
    assert cli._stale(inventory, current, datetime(2026, 9, 9)) == expected


# ask. Nothing here submits anything. The live submission is integration/test_cli.py's.


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


@pytest.mark.parametrize(
    ("session", "out", "present", "absent"),
    [
        (
            ONE_TURN,
            "PONG\n",
            [f"session: {ONE_TURN}", "assistant turns: 1", "outputs: outputs/marker.txt"],
            ["tools:", "log:"],
        ),
        (
            TOOL_CALL,
            "The guest kernel is 6.8.0-136-generic.\n",
            ["tools: mcp__workspace__bash, mcp__workspace__bash"],
            [],
        ),
    ],
)
def test_a_session_on_disk_prints_the_answer_on_stdout_and_the_footer_on_stderr(
    session, out, present, absent, tmp_path, capsys
) -> None:
    """The split is what makes `ask ... > answer.txt` hold the answer and nothing else."""
    args = parse("ask", "--cowork", "--session", str(session))
    assert cli._ask(args, ask_settings(tmp_path)) == OK
    printed = capsys.readouterr()
    assert printed.out == out
    for line in present:
        assert line in printed.err
    for line in absent:
        assert line not in printed.err


def test_json_prints_the_session_document_and_nothing_on_stderr(tmp_path: Path, capsys) -> None:
    args = parse("ask", "--cowork", "--session", str(ONE_TURN), "--json")
    assert cli._ask(args, ask_settings(tmp_path)) == OK
    printed = capsys.readouterr()
    document = SessionDocument.model_validate_json(printed.out)
    assert document.session_dir == str(ONE_TURN)
    assert document.final_text == "PONG"
    assert printed.err == ""


@pytest.mark.parametrize(
    ("name", "says"),
    [("no-such-session", ": no such session directory"), (str(NO_TRANSCRIPT), "8: ")],
)
def test_a_session_that_cannot_be_read_fails_and_says_so(name, says, tmp_path, capsys) -> None:
    """Code 8 is the driver's, and the verb carries it into the message."""
    directory = tmp_path / name
    args = parse("ask", "--cowork", "--session", str(directory))
    assert cli._ask(args, ask_settings(tmp_path)) == FAILED
    assert says in capsys.readouterr().err


def test_a_dry_run_prints_the_deep_link_and_needs_no_profile_and_writes_no_log(
    tmp_path: Path, capsys
) -> None:
    """Nothing behind the preflight is reached: a URL is built and a run log is read."""
    log = tmp_path / "runs.jsonl"
    config = settings(tmp_path, f"{UNREADABLE_PROFILE}  run_log: {log}\n")
    assert cli._ask(parse("ask", "--cowork", "--dry-run", "say hello & wait"), config) == OK
    printed = capsys.readouterr()
    assert printed.out == "claude://claude.ai/new?q=say%20hello%20%26%20wait&surface=cowork\n"
    assert "1 submission planned, 0 already made in the last 24 hours" in printed.err
    assert "no readable sessions root" not in printed.err
    assert not log.exists()


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


@pytest.mark.parametrize(
    ("code", "message", "session", "exit_code", "out", "says"),
    [
        (2, "max_runs is 0", None, PREFLIGHT_FAILED, "", ["2: max_runs is 0"]),
        (6, "the deep link did not open", None, FAILED, "", ["6: the deep link did not open"]),
        (7, "the run timed out", ONE_TURN, FAILED, "PONG\n", ["7: ", f"session: {ONE_TURN}"]),
        (7, "the run timed out", NO_TRANSCRIPT, FAILED, "", ["7: ", "8: "]),
        (7, "the run timed out", None, FAILED, "", ["7: the run timed out"]),
    ],
)
def test_a_raised_driver_code_becomes_the_verbs_exit_code(
    code, message, session, exit_code, out, says, tmp_path, capsys
) -> None:
    """Code 2 is the preflight class. A timed-out session keeps running in the VM, so what it
    produced by then is printed, and the verb still fails. docs/ask.md."""
    error = CoWorkError(code, message, session_dir=session)
    args = parse("ask", "--cowork", "hi")
    assert cli._ask_failure(args, ask_settings(tmp_path), "hi", error) == exit_code
    printed = capsys.readouterr()
    assert printed.out == out
    for line in says:
        assert line in printed.err


# docs. docs/cli_design.md "docs".


def test_docs_lists_the_directory_then_every_name(capsys) -> None:
    assert main(["docs"]) == OK
    printed = capsys.readouterr().out.splitlines()
    directory = Path(printed[0])
    assert directory.is_absolute() and directory.is_dir()
    assert printed[1:] == sorted(printed[1:])
    assert {"cli", "eval_format", "claude_code/README"} <= set(printed[1:])
    for name in printed[1:]:
        assert (directory / f"{name}.md").is_file(), name


def test_docs_prints_one_absolute_path(capsys) -> None:
    assert main(["docs", "eval_format"]) == OK
    printed = capsys.readouterr().out.strip()
    assert Path(printed).is_absolute()
    assert Path(printed).is_file()
    assert Path(printed).name == "eval_format.md"


def test_docs_takes_the_extension_or_leaves_it(capsys) -> None:
    assert main(["docs", "cli"]) == OK
    with_out = capsys.readouterr().out
    assert main(["docs", "cli.md"]) == OK
    assert capsys.readouterr().out == with_out


def test_an_unknown_name_is_a_usage_error_and_lists_the_names(capsys) -> None:
    assert main(["docs", "no-such-document"]) == USAGE
    printed = capsys.readouterr().err
    assert "no-such-document" in printed
    for name in ("cli", "eval_format", "claude_code/README"):
        assert name in printed


# init. docs/cli.md "init".

SKILLS = {"cowork-ask", "cowork-evals", "cowork-skill-author"}


def _init_in(path: Path, working_directory: Callable) -> int:
    with working_directory(path):
        return main(["init"])


def _tree(root: Path) -> dict[Path, bytes]:
    """Every file under a skill directory, bytecode excepted, which `init` does not copy."""
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


def test_init_writes_the_config_the_memory_block_and_every_skill(
    tmp_path: Path, working_directory: Callable
) -> None:
    assert _init_in(tmp_path, working_directory) == OK
    config = (tmp_path / "cowork_evals.yaml").read_bytes()
    assert config == resources.EXAMPLE_CONFIG.read_bytes()
    assert resources.MEMORY_MARKER in (tmp_path / "CLAUDE.md").read_text()
    skills = tmp_path / ".claude" / "skills"
    assert {child.name for child in skills.iterdir()} == SKILLS
    for name in SKILLS:
        assert _tree(skills / name) == _tree(resources.SKILLS / name)


def test_a_skill_directory_is_installed_with_every_file_but_bytecode(tmp_path: Path) -> None:
    """No shipped skill holds bytecode, so the exclusion is reached through `_install`."""
    source = tmp_path / "source" / "greeter"
    (source / "references").mkdir(parents=True)
    (source / "scripts" / "__pycache__").mkdir(parents=True)
    (source / "SKILL.md").write_text("---\nname: greeter\n---\n")
    (source / "references" / "format.md").write_text("# Format\n")
    (source / "scripts" / "run.py").write_text("print('hi')\n")
    (source / "scripts" / "__pycache__" / "run.cpython-310.pyc").write_bytes(b"bytecode")
    target = tmp_path / "consumer" / ".claude" / "skills" / "greeter"
    cli._install(source, target)
    assert {path.relative_to(target) for path in target.rglob("*") if path.is_file()} == {
        Path("SKILL.md"),
        Path("references/format.md"),
        Path("scripts/run.py"),
    }


def test_a_second_run_keeps_the_config_and_the_block_and_replaces_every_skill(
    tmp_path: Path, working_directory: Callable, capsys
) -> None:
    _init_in(tmp_path, working_directory)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    capsys.readouterr()
    assert _init_in(tmp_path, working_directory) == OK
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    assert capsys.readouterr().out.splitlines() == [
        "kept cowork_evals.yaml",
        "replaced .claude/skills/cowork-ask",
        "replaced .claude/skills/cowork-evals",
        "replaced .claude/skills/cowork-skill-author",
        "kept CLAUDE.md: it already carries the block",
    ]


def test_an_upgrade_replaces_a_stale_skill_whole(
    tmp_path: Path, working_directory: Callable
) -> None:
    """A skill written by an older version, edited, and carrying a file the package no longer
    ships, is the shipped skill byte for byte after `init`."""
    _init_in(tmp_path, working_directory)
    for _, target in resources.skills():
        written = tmp_path / target
        (written / resources.SKILL_FILE).write_text("---\nname: stale\n---\n")
        (written / "retired.md").write_text("# Gone from the package\n")
    _init_in(tmp_path, working_directory)
    for source, target in resources.skills():
        assert _tree(tmp_path / target) == _tree(source)


def test_a_skill_target_that_is_a_link_is_replaced_by_the_copy(
    tmp_path: Path, working_directory: Callable
) -> None:
    """The link goes, and what it pointed at is untouched."""
    pointed = tmp_path / "elsewhere"
    pointed.mkdir()
    (pointed / "mine.md").write_text("# Mine\n")
    source, target = resources.skills()[0]
    (tmp_path / target).parent.mkdir(parents=True)
    (tmp_path / target).symlink_to(pointed, target_is_directory=True)
    _init_in(tmp_path, working_directory)
    assert not (tmp_path / target).is_symlink()
    assert _tree(tmp_path / target) == _tree(source)
    assert (pointed / "mine.md").read_text() == "# Mine\n"


def test_an_existing_memory_file_is_appended_to(
    tmp_path: Path, working_directory: Callable
) -> None:
    memory = tmp_path / resources.MEMORY_NAME
    memory.write_text("# My repository\n\nMy own rules.\n")
    _init_in(tmp_path, working_directory)
    written = memory.read_text()
    assert written.startswith("# My repository")
    assert "My own rules." in written
    assert resources.MEMORY_MARKER in written


def test_an_edited_block_is_still_recognised(tmp_path: Path, working_directory: Callable) -> None:
    """The heading is the marker, so what a consumer wrote under it survives."""
    memory = tmp_path / resources.MEMORY_NAME
    _init_in(tmp_path, working_directory)
    memory.write_text(f"{resources.MEMORY_MARKER}\n\nMy own words.\n")
    _init_in(tmp_path, working_directory)
    assert memory.read_text() == f"{resources.MEMORY_MARKER}\n\nMy own words.\n"


def test_an_existing_config_is_left_exactly_as_it_is(
    tmp_path: Path, working_directory: Callable
) -> None:
    config = tmp_path / resources.CONFIG_NAME
    config.write_text("eval:\n  model: opus\n")
    _init_in(tmp_path, working_directory)
    assert config.read_text() == "eval:\n  model: opus\n"
