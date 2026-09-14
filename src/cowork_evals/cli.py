"""The command: the parser, the ten verbs, the dispatch and the exit codes.

The surface is docs/cli.md, and this module is the whole of it. There is no second entry point
and no per-backend executable.

Printing happens here and nowhere else, and `sys.exit` is called in `console_main` alone. `main`
returns a code. The one exit it does not return is `SystemExit(2)`, which `argparse` raises from
inside `parse_args` for an unknown option or a missing path.

The venv backend is not built, so `--venv` is an unknown option on every verb and `argparse`
exits 2. Its design stays in docs/staged_runtime.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import (
    checks,
    cowork,
    cowork_backend,
    docker,
    judge,
    logs,
    panel,
    preflight,
    resources,
    results,
    traces,
    validate,
    verdict,
)
from .cases import CaseError, discover, plugin_name, plugin_roots
from .config import ABLATION_CHOICES, Config, CoWorkError, CoWorkSection, EvalSection, checked
from .cowork import CoWork
from .docker import Condition, Docker, DockerError, pytest_image, remedy
from .docker.pytest_image import PytestImage
from .harness import RunOptions
from .preflight import COWORK, DOCKER, TEST

# `check --all`, the one selection that is not a backend.
ALL = "all"

# The exit codes. docs/cli.md. `test` is the one verb that returns a code from below
# unchanged, and it returns pytest's.
#
# `FAILED` is the verdict on `run` and the driver on `ask`. It is one code because it is one
# thing to an operator: the verb reached its backend and the work did not succeed.
OK = 0
FAILED = 1
USAGE = 2
PREFLIGHT_FAILED = 3
INTERRUPTED = 130

# Each option, and the attribute `argparse` stores it under. The refusal table below names
# options, because that is what an operator typed and what a message has to say back.
OPTION_ATTRIBUTES = {
    "--runs": "runs",
    "--timeout-seconds": "timeout_seconds",
    "--model": "model",
    "--judge-model": "judge_model",
    "--ablation": "ablation",
    "--delta-threshold": "delta_threshold",
    "--allow-tools": "allow_tools",
    "--max-cost-usd": "max_cost_usd",
    "--keep-traces": "keep_traces",
    "--build-missing": "build_missing",
}

# What an option's attribute carries when the option was not typed, wherever that is not
# `None`. `_given` reads it, so a three-state option whose false value is `False` is not
# mistaken for one that was never typed.
UNTYPED = {"--build-missing": False}

# Each option that carries a value, and the setting whose check it takes. An option and the
# file are two rungs of one ladder, so the value is checked the same way whichever rung
# supplied it, and the message names the option because that is what the operator typed.
# `--runs` is not here: its ceiling is the case format's, and `bad_value` reads it there.
# docs/library.md.
OPTION_SETTINGS: dict[str, tuple[type[Any], str]] = {
    "--model": (EvalSection, "model"),
    "--judge-model": (EvalSection, "judge_model"),
    "--ablation": (EvalSection, "ablation"),
    "--delta-threshold": (EvalSection, "delta_threshold"),
    "--allow-tools": (EvalSection, "allow_tools"),
    "--max-cost-usd": (EvalSection, "max_cost_usd"),
    "--keep-traces": (EvalSection, "keep_traces"),
    "--timeout-seconds": (CoWorkSection, "run_timeout"),
}

# What each backend cannot honour. An option here is an operator mistake, so it is a usage
# error. A *case* that needs a field the backend cannot honour declares it with a tag and is
# counted instead, and the two are never conflated. docs/cli.md.
REFUSED = {
    DOCKER: ("--timeout-seconds",),
    COWORK: (
        "--model",
        "--ablation",
        "--delta-threshold",
        "--allow-tools",
        "--max-cost-usd",
        "--build-missing",
    ),
}

# Why each is refused, so a message says more than that it was.
REFUSAL_REASONS = {
    "--timeout-seconds": "claude plugin eval has no timeout flag to map it onto",
    "--model": "the session decides its model",
    "--ablation": (
        "a session gets its skills from the profile the application is running, and "
        "nothing here chooses which profile that is"
    ),
    "--delta-threshold": "that backend runs one arm, so there is no delta to decide on",
    "--allow-tools": "the session decides its tools",
    "--max-cost-usd": "the session is billed to the account and is not observable here",
    "--build-missing": "there is nothing to build on that backend",
}


def build_parser() -> argparse.ArgumentParser:
    """The whole surface. Every option a verb takes is added here and nowhere else."""
    parser = argparse.ArgumentParser(
        prog="cowork_evals",
        description="Run evals for Claude CoWork skills and plugins.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="print the installed cowork_evals version and exit",
    )
    verbs = parser.add_subparsers(dest="verb")

    _run_parser(verbs)
    _ask_parser(verbs)
    _test_parser(verbs)
    _setup_parser(verbs)
    _login_parser(verbs)
    _check_parser(verbs)
    _prune_parser(verbs)
    _panel_parser(verbs)
    _docs_parser(verbs)
    _init_parser(verbs)
    return parser


def _backend_group(
    verb: argparse.ArgumentParser, *backends: str
) -> argparse._MutuallyExclusiveGroup:
    """The backend flag: mutually exclusive, required, and with no default.

    Its members differ per verb, so a backend a verb does not carry is an unknown option
    and `argparse` exits 2. There is no refusal message to write for one.
    """
    group = verb.add_mutually_exclusive_group(required=True)
    for backend in backends:
        group.add_argument(
            f"--{backend}",
            dest="backend",
            action="store_const",
            const=backend,
            help=f"the {backend} backend",
        )
    return group


def _run_parser(verbs: Any) -> None:
    verb = verbs.add_parser("run", help="run a suite and decide pass or fail on what it produced")
    _backend_group(verb, DOCKER, COWORK)
    verb.add_argument("path", help="a case, a skill, an evals/ tree, a plugin root or a sweep")
    verb.add_argument("--runs", type=int, help="how many times each case runs")
    verb.add_argument("--timeout-seconds", type=float, help="each run's timeout, on --cowork")
    verb.add_argument("--model", help="the model under test, on --docker")
    verb.add_argument("--judge-model", help="the model behind llm and baseline graders")
    verb.add_argument(
        "--ablation",
        choices=ABLATION_CHOICES,
        help="with-without runs a no-plugin baseline arm beside the with-arm, on --docker",
    )
    verb.add_argument(
        "--delta-threshold",
        type=float,
        help="what a case's delta must reach under --ablation with-without, on --docker",
    )
    verb.add_argument("--allow-tools", nargs="+", help="the tool grant, on --docker")
    verb.add_argument("--max-cost-usd", type=float, help="one suite's ceiling, on --docker")
    # Three-state, so `--no-keep-traces` beats a file that turned it on and `--keep-traces`
    # beats a file that turned it off. Both forms count as typed. docs/cli.md.
    verb.add_argument(
        "--keep-traces",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="keep each run's trace, final message and workspace under the log directory",
    )
    verb.add_argument("--tag", action="append", help="keep cases carrying this tag, repeatable")
    verb.add_argument("--case", help="a glob over the case name")
    verb.add_argument("--out", help="the log root, replacing logs/evals")
    verb.add_argument(
        "--build-missing", action="store_true", help="build an absent image instead of failing"
    )
    verb.add_argument(
        "--require-coverage",
        action="store_true",
        help="fail the preflight when a skill has no eval directory",
    )
    verb.add_argument(
        "--dry-run", action="store_true", help="print what would run, and the code it would reach"
    )


def _ask_parser(verbs: Any) -> None:
    """`ask` carries a prompt or a session, and the four options in docs/cli.md.

    It runs no eval, so it takes no case option: no `--runs`, no `--tag`, no `--case`, no
    `--out` and no `--require-coverage`. `--cowork` is its only backend, exactly as
    `--docker` is `test`'s, so a second backend is an unknown option and `argparse` exits 2.

    The prompt is optional here rather than required, because `--session` is the other way
    of naming what to print. The four combinations that make no sense are refused by the
    verb, with a message naming what was typed, and `argparse` cannot express any of them.
    """
    verb = verbs.add_parser("ask", help="submit one prompt to a CoWork session and print it")
    _backend_group(verb, COWORK)
    verb.add_argument("prompt", nargs="?", help="the prompt. `-` reads it from standard input")
    verb.add_argument("--session", help="print a session already on disk. Submits nothing")
    verb.add_argument("--timeout-seconds", type=float, help="this run's timeout")
    verb.add_argument("--json", action="store_true", help="print the session document")
    verb.add_argument(
        "--dry-run", action="store_true", help="print the deep link and the ceiling arithmetic"
    )


def _test_parser(verbs: Any) -> None:
    """`test` carries a path, two flags and a pytest tail, and no other option.

    Every option it does not carry configures a harness run, and `test` runs no harness. A
    raw tail is allowed here and forbidden on `run`, because pytest is the only thing
    behind this verb and the harness runs on two backends. docs/cowork_test.md.

    The tail begins at `--`, and `argparse` claims no token after it: `--dry-run` there is
    pytest's argument and never this verb's. It is a plain variadic positional and not
    `argparse.REMAINDER`, which would swallow this verb's own two flags whenever they were
    typed after the path.
    """
    verb = verbs.add_parser("test", help="run a consumer's pytest suite on the CoWork runtime")
    _backend_group(verb, DOCKER)
    verb.add_argument("path", help="a path inside one plugin root")
    verb.add_argument(
        "--build-missing", action="store_true", help="build an absent image instead of failing"
    )
    verb.add_argument("--dry-run", action="store_true", help="print the container argument list")
    verb.add_argument(
        "pytest_args",
        nargs="*",
        metavar="-- PYTEST_ARGS",
        help="everything after -- reaches pytest in order and unmodified",
    )


def _setup_parser(verbs: Any) -> None:
    verb = verbs.add_parser("setup", help="build what a backend needs")
    _backend_group(verb, DOCKER)


def _login_parser(verbs: Any) -> None:
    """`login` makes the one credential a run needs, and builds nothing.

    It is a verb and not a side effect of `setup`, because an image is a build product and a
    credential is not: `_prune_images` already keeps the two apart, and one command that
    makes both cannot be run again for either one alone.

    `--check` reports and writes nothing. `--force` logs in again over a login this package
    already accepts, which is tokens that are present and no longer work, or the wrong
    account. A credentials file carrying no token is not a login, and needs no flag.
    docs/cli.md.
    """
    verb = verbs.add_parser("login", help="log in to Claude Code once, in a container")
    _backend_group(verb, DOCKER)
    group = verb.add_mutually_exclusive_group()
    group.add_argument(
        "--check",
        action="store_true",
        help="report whether a login is present, and write nothing",
    )
    group.add_argument(
        "--force",
        action="store_true",
        help="log in again over a login that is already there",
    )


def _check_parser(verbs: Any) -> None:
    verb = verbs.add_parser("check", help="report what a backend is missing")
    _backend_group(verb, DOCKER, COWORK, ALL)


def _panel_parser(verbs: Any) -> None:
    """`panel` takes a path and three options, and no backend.

    It renders both backend columns and reaches neither, so there is nothing for a backend
    flag to select. There is no `--tag` and no `--case` either: the verb exists to show what
    has never run, and a filter hides exactly those rows. The path is the only selector, and
    it is the one `run` uses.
    """
    verb = verbs.add_parser(
        "panel", help="print every case under a path with its latest result on each backend"
    )
    verb.add_argument("path", help="a case, a skill, an evals/ tree, a plugin root or a sweep")
    verb.add_argument("--markdown", help="write the same rows as a Markdown table to this file")
    verb.add_argument("--json", help="write the same rows as a JSON snapshot to this file")
    verb.add_argument(
        "--removed",
        action="store_true",
        help="add a row for history whose case is no longer in the tree",
    )


def _prune_parser(verbs: Any) -> None:
    """`prune` takes any combination of its selection flags, and requires at least one.

    They are not a mutually exclusive group: pruning images and logs in one invocation is
    ordinary. `argparse` cannot express `at least one`, so the refusal is the verb's and
    returns 2.

    `--out` does not reach `--history`. That option names the log root, and the history root
    is `panel.root`. docs/panel.md.
    """
    verb = verbs.add_parser("prune", help="delete artefacts this command created")
    verb.add_argument("--docker", action="store_true", help="images this command built")
    verb.add_argument("--logs", action="store_true", help="run directories under the log root")
    verb.add_argument(
        "--history", action="store_true", help="records under the panel's history root"
    )
    verb.add_argument(
        "--older-than", type=int, default=logs.RUN_PRUNE_DAYS, help="restrict every selection"
    )
    verb.add_argument("--out", help="the log root, replacing logs/evals")


def _init_parser(verbs: Any) -> None:
    """`init` takes no backend and no option. It writes four targets and overwrites none."""
    verbs.add_parser("init", help="write the config, the skills and a CLAUDE.md block")


def _docs_parser(verbs: Any) -> None:
    """`docs` takes no backend. It reads the shipped tree and writes nothing."""
    verb = verbs.add_parser("docs", help="print where the shipped documentation is")
    verb.add_argument(
        "name",
        nargs="?",
        help="one document, with or without .md. Omitted, every name is listed",
    )


# The refusals.


def _given(args: argparse.Namespace, option: str) -> bool:
    """Whether an option was typed, against what its attribute carries when it was not.

    That is `None` for every option but the `store_true` ones in `UNTYPED`, which carry
    `False`. It is compared by identity, so a three-state option set to `False` is typed.

    A verb that does not carry the option has no attribute for it, and that is not typed
    either: `check` takes a backend and nothing else, and `--build-missing` is `run`'s.
    """
    attribute = OPTION_ATTRIBUTES[option]
    if not hasattr(args, attribute):
        return False
    return getattr(args, attribute) is not UNTYPED.get(option)


def refusal(args: argparse.Namespace) -> str | None:
    """The one line naming an option the chosen backend refuses, or `None`."""
    backend = getattr(args, "backend", None)
    for option in REFUSED.get(backend, ()):
        if _given(args, option):
            return f"{option} is not accepted on --{backend}: {REFUSAL_REASONS[option]}"
    return None


def bad_value(args: argparse.Namespace) -> str | None:
    """The one line naming an option whose value its setting refuses, or `None`.

    An option and the file are two rungs of one ladder, so a value is checked the same way
    whichever rung supplied it: `--delta-threshold 5` is refused exactly as
    `eval.delta_threshold: 5` is. Without this the option is the way around every check the
    file gets. The ladder is docs/library.md.

    `--runs` is the one option whose ceiling is not a setting. It replaces each case's own
    `runs`, so it takes that key's cap from the case format. docs/eval_format.md.
    """
    for option, (section, key) in OPTION_SETTINGS.items():
        if not _given(args, option):
            continue
        try:
            checked(section, key, getattr(args, OPTION_ATTRIBUTES[option]), name=option)
        except CoWorkError as error:
            return str(error)
    if _given(args, "--runs"):
        try:
            runs = checked(CoWorkSection, "max_runs", args.runs, name="--runs")
        except CoWorkError as error:
            return str(error)
        if runs > validate.CAPS["runs"]:
            return f"--runs: expected an integer at or below {validate.CAPS['runs']}, got {runs}"
    return None


# The entry points.


def parse_args(argv: list[str] | None = None) -> Any:
    """The command line, with the tail after `--` handed to the verb that takes one.

    `argparse` only routes a `--` into a variadic positional from Python 3.13, and this
    package runs on 3.10, so the split is done here. It is the same rule on every version:
    the tail begins at the first `--`, `argparse` never sees it, and a verb that declares
    no `pytest_args` refuses one.
    """
    parser = build_parser()
    argv = sys.argv[1:] if argv is None else argv
    cut = argv.index("--") if "--" in argv else len(argv)
    head, tail = argv[:cut], argv[cut + 1 :]
    args = parser.parse_args(head)
    if tail:
        if not hasattr(args, "pytest_args"):
            parser.error(f"{getattr(args, 'verb', None) or 'cowork_evals'} takes no -- tail")
        args.pytest_args = list(args.pytest_args) + tail
    return args


def main(argv: list[str] | None = None) -> int:
    """Parse, refuse, dispatch, and return an exit code. Nothing here calls `sys.exit`."""
    args = parse_args(argv)

    if args.version:
        print(logs.distribution_version())
        return OK
    if args.verb is None:
        build_parser().print_usage(sys.stderr)
        print("cowork_evals: a verb is required", file=sys.stderr)
        return USAGE

    refused = refusal(args)
    if refused is not None:
        print(refused, file=sys.stderr)
        return USAGE

    bad = bad_value(args)
    if bad is not None:
        print(bad, file=sys.stderr)
        return USAGE

    try:
        config = Config.load()
    except CoWorkError as error:
        print(error, file=sys.stderr)
        return PREFLIGHT_FAILED

    try:
        return _dispatch(args, config)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return INTERRUPTED


def _dispatch(args: argparse.Namespace, config: Config) -> int:
    if args.verb == "run":
        return _run(args, config)
    if args.verb == "ask":
        return _ask(args, config)
    if args.verb == "test":
        return _test(args, config)
    if args.verb == "setup":
        return _setup(config)
    if args.verb == "login":
        return _login(args, config)
    if args.verb == "check":
        return _check(args, config)
    if args.verb == "panel":
        return _panel(args, config)
    if args.verb == "docs":
        return _docs(args)
    if args.verb == "init":
        return _init()
    return _prune(args, config)


# run.


def _run(args: argparse.Namespace, config: Config) -> int:
    """Preflight, validate, count, prune, then run every selected plugin and reach a verdict once.

    Every refusal happens before anything is created and before anything is deleted, so
    exit 2 and exit 3 leave the log root exactly as it was.

    `--dry-run` skips the preflight and keeps the validation. Nothing behind the preflight is
    reached by a dry run: the image tag is a hash of local files, `run_argv` builds a list,
    and `cowork_backend.plan` reads the case tree and the configuration. Gating a filesystem
    check on a running daemon is the one thing that stopped a consumer without Docker from
    checking a case at all. The ceiling is part of that preflight, and a dry run on
    `--cowork` prints the same arithmetic instead of refusing on it. docs/cli.md.
    """
    try:
        roots = plugin_roots(args.path)
    except CaseError as error:
        return _usage(str(error))
    if len(roots) > 1 and args.backend == COWORK:
        named = ", ".join(str(root) for root in roots)
        return _usage(f"{args.path} covers more than one plugin root on --cowork: {named}")

    targets = _targets(args.path, roots)
    tags = tuple(args.tag or ())

    if not args.dry_run:
        unmet = _run_preflight(args, config, targets)
        if unmet:
            return _refuse(unmet, PREFLIGHT_FAILED)
    blocked = _validate(roots, require_coverage=args.require_coverage)
    if blocked:
        return _refuse(blocked, PREFLIGHT_FAILED)
    picked = _selected(targets, tags, args.case)
    if not picked:
        return _usage(f"{args.path} selects no case{_filters(tags, args.case)}")
    # What is there before the filters, which is the first of the counts the verdict line
    # prints. The same reader answers both, so the two numbers are comparable.
    found = _selected(targets, (), None)

    root = logs.log_root(args.out)
    for deleted in logs.prune(root, logs.RUN_PRUNE_DAYS):
        print(f"pruned {deleted}")

    if args.dry_run:
        return _dry_run(args, config, root, targets, tags)

    return _sweep(args, config, root, targets, tags, found=found, picked=picked)


def _targets(path: str, roots: list[Path]) -> list[tuple[Path, Path]]:
    """One `(root, target)` pair per plugin the invocation will run.

    A single root runs the path as it was typed, so a case directory runs that case. A
    sweep runs each root whole, because the path itself is above all of them.
    """
    if len(roots) == 1:
        return [(roots[0], Path(path).resolve())]
    return [(root, root) for root in roots]


def _run_preflight(
    args: argparse.Namespace, config: Config, targets: list[tuple[Path, Path]]
) -> list[str]:
    """The backend's unmet conditions, plus the rate ceiling on `--cowork`.

    `--build-missing` builds an absent image here instead of failing. Every other unmet
    condition still fails, the container login included, because that login is interactive.
    """
    if args.backend == DOCKER and args.build_missing:
        image = Docker(config)
        if image.daemon_is_reachable() and not image.image_is_present():
            image.build()
    unmet = preflight.checks(args.backend, config)
    if args.backend == COWORK and not unmet:
        unmet += preflight.cowork_ceiling(
            targets[0][1],
            config=config,
            runs=args.runs,
            timeout_seconds=args.timeout_seconds,
            tags=tuple(args.tag or ()),
            case_glob=args.case,
        )
    return unmet


def _validate(roots: list[Path], *, require_coverage: bool) -> list[str]:
    """Every selected plugin root, whole. A malformed sibling case blocks a single case.

    Coverage is a report and fails nothing on its own, so it is printed here and goes to
    stdout. `--require-coverage` turns it into a preflight condition like any other, and it
    is then returned rather than printed: the caller refuses it on stderr, and printing it
    here as well would put every gap on both streams. docs/cli.md.
    """
    blocked = [str(violation) for root in roots for violation in validate.violations(root)]
    gaps = [line for root in roots for line in validate.uncovered(root)]
    if require_coverage:
        return blocked + gaps
    for line in gaps:
        print(f"uncovered: {line}")
    return blocked


def _selected(targets: list[tuple[Path, Path]], tags: tuple[str, ...], case: str | None) -> int:
    """How many cases the selection matches across every plugin.

    Zero across all of them is a usage error, so a mistyped `--tag` never reads as a pass.
    One plugin of a sweep matching zero is normal under a filter and is not an error.
    """
    return sum(len(discover(target, tags=tags, case_glob=case)) for _, target in targets)


def _filters(tags: tuple[str, ...], case: str | None) -> str:
    named = [f"--tag {tag}" for tag in tags] + ([f"--case {case}"] if case else [])
    return f" under {', '.join(named)}" if named else ""


def _dry_run(
    args: argparse.Namespace,
    config: Config,
    root: Path,
    targets: list[tuple[Path, Path]],
    tags: tuple,
) -> int:
    """What would run, and no run directory. Pruning already happened above.

    It exits 0 on both backends. A case this backend cannot run declares it, is counted
    rather than failed, and a suite of nothing but declared cases is a pass. docs/cli.md.
    """
    for plugin, target in targets:
        name = plugin_name(plugin)
        print(f"# {name}")
        if args.backend == COWORK:
            _dry_run_cowork(args, config, target, tags)
            continue
        would_be = root / logs.run_dir_name(logs.scope_name(target, [plugin])) / logs.slug(name)
        # `redact` replaces each forwarded value, and reads none: a dry run skips the
        # preflight, so it prints every configured name whether or not the host has it set.
        # docs/docker.md.
        printed = Docker(config).run_argv(
            target, would_be, _options(args, config, tags), redact=True
        )
        for argument in printed:
            print(argument)
    return OK


def _dry_run_cowork(args: argparse.Namespace, config: Config, target: Path, tags: tuple) -> None:
    """One line per case, then the ceiling arithmetic. This backend builds no command line.

    What each case declares is the point: a declared case submits nothing, so an operator
    reads which ones before spending a VM boot on the rest.
    """
    prepared = cowork_backend.plan(
        target,
        config=config,
        runs=args.runs,
        timeout_seconds=args.timeout_seconds,
        tags=tags,
        case_glob=args.case,
    )
    for entry in prepared.entries:
        print(f"{entry.name}: runs {entry.runs}, timeout {entry.timeout_seconds}s")
        if entry.declared is not None:
            print(f"  declared: {entry.declared}")
        for grader, reason in sorted(entry.graders.items()):
            print(f"  grader skip {grader}: {reason}")
    print(prepared.arithmetic)


def _options(args: argparse.Namespace, config: Config, tags: tuple) -> RunOptions:
    """The container backend's options, resolved through the one ladder. docs/library.md."""
    return RunOptions.resolve(
        config,
        model=args.model,
        judge_model=args.judge_model,
        ablation=args.ablation,
        max_cost_usd=None if args.max_cost_usd is None else str(args.max_cost_usd),
        allow_tools=None if args.allow_tools is None else tuple(args.allow_tools),
        keep_traces=_keeping(args, config),
        runs=args.runs,
        tags=tags,
        case=args.case,
    )


def _keeping(args: argparse.Namespace, config: Config) -> bool:
    """Whether this run keeps its traces. Both backends read it here and nowhere else.

    An option beats the file, and the file beats the built-in default: docs/library.md. It
    reaches the container backend as a `RunOptions` field, because the harness command line
    needs it too, and the CoWork backend through `_each_plugin` alone, because that backend
    builds no command line. `RunOptions.resolve` is handed the answer rather than the
    argument, so the ladder is walked once.
    """
    return args.keep_traces if args.keep_traces is not None else config.eval.keep_traces


def _delta_threshold(args: argparse.Namespace, config: Config) -> float:
    """What a case's delta must reach, resolved through the one ladder. docs/library.md.

    It is read here and handed to the verdict, which reads no configuration file of its own,
    so one invocation resolves every setting once. It never reaches the harness command line:
    `--threshold` stays pinned to 0 so this package decides. docs/running_evals.md.
    """
    if args.delta_threshold is not None:
        return float(args.delta_threshold)
    return float(config.eval.delta_threshold)


@dataclass(frozen=True)
class Swept:
    """What one sweep leaves the verdict and the history.

    `roots` maps a run directory's child name to the plugin root on this host. The result
    document cannot supply it: on the container backend `suite.root` is the path the plugin
    was mounted at inside the container, `/work/plugin`, and the case files a digest covers
    are on the host.
    """

    warnings: tuple[str, ...] = ()
    roots: dict[str, Path] = field(default_factory=dict)


def _sweep(
    args: argparse.Namespace,
    config: Config,
    root: Path,
    targets: list[tuple[Path, Path]],
    tags: tuple,
    *,
    found: int,
    picked: int,
) -> int:
    """Every selected plugin in turn, inside one run directory, decided once.

    `found` and `picked` are counted over the case tree above, before anything ran, and are
    two of the four numbers the verdict line prints. docs/running_evals.md."""
    image = Docker(config) if args.backend == DOCKER else None
    scope = logs.scope_name(args.path, [plugin for plugin, _ in targets])
    directory = logs.run_dir(root, scope)
    logs.point_latest(root, directory)

    with logs.tee(directory):
        logs.write_env(
            directory,
            args.backend,
            image=None if image is None else image.tag,
            credential=None if image is None else image.credential,
            env_passthrough=() if image is None else image.env_passthrough,
        )
        swept = _each_plugin(args, config, directory, targets, tags, image)
        decided = verdict.decide(
            directory,
            found=found,
            picked=picked,
            extra=swept.warnings,
            delta_threshold=_delta_threshold(args, config),
        )
        (directory / logs.VERDICT_FILE).write_text(decided.text, encoding="utf-8")
        print(decided.text, end="")
        _record(args, config, directory, decided, image, swept.roots)
    return OK if decided.passed else FAILED


def _record(
    args: argparse.Namespace,
    config: Config,
    directory: Path,
    decided: verdict.Verdict,
    image: Docker | None,
    roots: dict[str, Path],
) -> None:
    """Append one record per case to the history, from the documents this invocation wrote.

    It runs after the verdict, once, and the outcome it records is the one the verdict
    reached. A `--dry-run` and every refusal return before the sweep, so neither appends.

    A failure to write is a warning on stderr and leaves the exit code alone. Recording a
    result is not deciding one, and an unwritable history root must not turn a passing run
    red. docs/panel.md.
    """
    try:
        panel.append(
            config.panel.root,
            panel.records(
                directory,
                decided.outcomes,
                args.backend,
                image=None if image is None else image.tag,
                roots=roots,
            ),
        )
    except OSError as error:
        print(f"panel: {error}", file=sys.stderr)


def _each_plugin(
    args: argparse.Namespace,
    config: Config,
    directory: Path,
    targets: list[tuple[Path, Path]],
    tags: tuple,
    image: Docker | None,
) -> Swept:
    """Run each plugin, stopping on the total cost ceiling.

    The check runs before the first plugin, so a ceiling of 0 stops the invocation before
    it spends anything. On `--cowork` the sum is the judge spend alone: the session is
    billed to the account and is not observable from the host, so the ceiling that binds
    there is the driver's `max_runs`, in the preflight above. docs/running_evals.md.
    """
    if image is None:
        try:
            cowork.consent(config.cowork)
        except CoWorkError as error:
            return Swept((str(error),))

    # Built once: it does not vary by plugin, and the grant in it is what the validity
    # checks hold each run's offered tool list against. The CoWork backend builds no
    # options and grants nothing, so those checks find nothing there.
    options = _options(args, config, tags) if image is not None else None
    # The one ladder every other judge call resolves through, so `--judge-model` beats
    # `eval.judge_model` for a check judge too. docs/checks.md.
    judge_model = judge.resolve_model(args.judge_model, config)

    ceiling = config.eval.max_cost_total_usd
    roots: dict[str, Path] = {}
    for plugin, target in targets:
        spent = results.spend(directory)
        if spent >= ceiling:
            return Swept(
                (
                    f"the total cost ceiling stopped the sweep at {plugin}: "
                    f"{spent} spent, eval.max_cost_total_usd is {ceiling}",
                ),
                roots,
            )
        output = logs.plugin_dir(directory, plugin_name(plugin))
        # The run directory's child name against the plugin root on this host. `plugin_dir`
        # owns the name, including the `-2` suffix two plugins of one name get, so it is
        # read back here rather than derived a second time.
        roots[output.name] = Path(plugin)
        try:
            if image is not None and options is not None:
                image.run(target, output, options)
            else:
                cowork_backend.run(
                    target,
                    output,
                    config=config,
                    runs=args.runs,
                    timeout_seconds=args.timeout_seconds,
                    judge_model=args.judge_model,
                    tags=tags,
                    case_glob=args.case,
                )
        except (DockerError, CaseError) as error:
            # The verdict reads the missing document and fails, so the sweep goes on.
            print(f"{plugin}: {error}", file=sys.stderr)
        finally:
            # In a `finally`, because a run that left no result document still left
            # sandboxes, and one kept sandbox is unreadable until it is collected. A
            # collection problem is a warning and never turns a passing run into a failure.
            if _keeping(args, config):
                granted = () if options is None else options.allow_tools
                for warning in traces.collect(output, granted=granted):
                    print(f"trace: {warning}", file=sys.stderr)
            # After the collection, because a check reads the collected run directory. It
            # runs whether or not the traces were kept: with none there is nothing to read,
            # and a case with checks then produces a skip, which fails the run.
            # docs/checks.md.
            for warning in checks.run(output, plugin, judge_model=judge_model):
                print(f"check: {warning}", file=sys.stderr)
    return Swept((), roots)


# ask.

# The driver code that is configuration or the rate ceiling. It is the preflight class, so it
# leaves this verb with the preflight's code. docs/cowork_driver.md.
REFUSED_BEFORE_SUBMISSION = 2

# The prompt that is read from standard input instead of from the command line.
STDIN = "-"


def _ask(args: argparse.Namespace, config: Config) -> int:
    """One prompt to a CoWork session, or one session already on disk.

    It is not an eval. There is no case tree, no grader, no result document, no verdict and no
    run directory, and it writes nothing on the host: the session directory in the profile is
    the permanent record, and the run log is the driver's. `test` is the precedent.
    docs/cli.md.

    The rate ceiling is the driver's, in `CoWork._check`, and is not re-derived here. A second
    ceiling in this verb would be a second source for one number.

    `--session` skips the preflight because it reads a directory: no macOS, no profile and no
    Accessibility grant. `--dry-run` skips it for the reason `run --dry-run` does, which is
    that nothing behind the preflight is reached: the deep link is built from the prompt and
    the ceiling arithmetic is read from the run log.

    The keyboard is asked for once, after the preflight and before the submission, which is
    where `_each_plugin` asks for it too. Cancel is the driver's code 2 and reaches the
    preflight's exit code, and nothing has fired at that point. docs/cowork_driver.md.
    """
    refused = _ask_refusal(args)
    if refused is not None:
        return _usage(refused)

    if args.session is not None:
        return _ask_session(args, CoWork(config.cowork))

    prompt = sys.stdin.read() if args.prompt == STDIN else args.prompt
    overrides = {} if args.timeout_seconds is None else {"run_timeout": args.timeout_seconds}
    try:
        driver = CoWork(config.cowork, **overrides)
        if args.dry_run:
            return _ask_dry_run(driver, prompt)
        unmet = preflight.checks(COWORK, config)
        if unmet:
            return _refuse(unmet, PREFLIGHT_FAILED)
        cowork.consent(config.cowork)
        return _ask_print(driver.run(prompt), args)
    except CoWorkError as error:
        return _ask_failure(args, config, prompt, error)


def _ask_refusal(args: argparse.Namespace) -> str | None:
    """The one line naming what was typed, or `None`. Every one of them returns 2.

    `argparse` can express none of these: a prompt and `--session` are two ways of naming
    what to print, and the two options below are only meaningful for a submission.
    """
    if args.prompt is None and args.session is None:
        return "ask takes a prompt or --session: there is nothing to print"
    if args.prompt is not None and args.session is not None:
        return "ask takes a prompt or --session, not both: a session is either new or on disk"
    if args.session is not None and args.timeout_seconds is not None:
        return "--timeout-seconds is not accepted with --session: nothing waits"
    if args.session is not None and args.dry_run:
        return "--dry-run is not accepted with --session: nothing would be submitted"
    return None


def _ask_session(args: argparse.Namespace, driver: CoWork) -> int:
    """One session already on disk. It submits nothing, costs nothing and spends no ceiling."""
    directory = Path(args.session).expanduser()
    if not directory.is_dir():
        return _refuse([f"{directory}: no such session directory"], FAILED)
    try:
        return _ask_print(driver.collect(directory), args)
    except CoWorkError as error:
        return _refuse([f"{error.code}: {error}"], FAILED)


def _ask_dry_run(driver: CoWork, prompt: str) -> int:
    """The deep link, and the ceiling the submission would count against. It fires nothing.

    The link is stdout and the arithmetic is stderr, so the link alone is what a redirect
    captures.
    """
    print(driver.deep_link(prompt))
    recent = driver.recent()
    print(
        f"1 submission planned, {recent} already made in the last 24 hours, "
        f"max_runs is {driver.config.max_runs}",
        file=sys.stderr,
    )
    return OK


def _ask_failure(args: argparse.Namespace, config: Config, prompt: str, error: CoWorkError) -> int:
    """What a raised driver code becomes.

    A run timeout carries a session directory, the session keeps running in the VM, and what
    it produced up to that point is still worth reading, so the verb collects and prints it
    and still fails. That is what the CoWork backend does with the same code, and the code
    itself is that backend's constant rather than a second copy here.
    """
    message = f"{error.code}: {error}"
    if error.code == REFUSED_BEFORE_SUBMISSION:
        return _refuse([message], PREFLIGHT_FAILED)
    if error.code == cowork_backend.RUN_TIMEOUT_CODE and error.session_dir is not None:
        print(message, file=sys.stderr)
        try:
            _ask_print(CoWork(config.cowork).collect(error.session_dir, prompt=prompt), args)
        except CoWorkError as collected:
            print(f"{collected.code}: {collected}", file=sys.stderr)
        return FAILED
    return _refuse([message], FAILED)


def _ask_print(session: dict[str, Any], args: argparse.Namespace) -> int:
    """The answer on stdout, and what produced it on stderr.

    The split is so that `cowork_evals ask --cowork "..." > answer.txt` holds the answer and
    nothing else. `--json` prints the whole session document instead, and then stdout is the
    document and stderr is empty: a caller that asked for the document has every footer value
    in it already. docs/cli.md.
    """
    if args.json:
        print(json.dumps(session, indent=2))
        return OK

    print(session["final_text"])
    assistant = sum(1 for turn in session["turns"] if turn["role"] == "assistant")
    for label, value in (
        ("session", session["session_dir"]),
        ("assistant turns", assistant),
        ("tools", ", ".join(session["tool_names"])),
        ("outputs", ", ".join(session["outputs"])),
        ("log", session["log_file"]),
    ):
        if value:
            print(f"{label}: {value}", file=sys.stderr)
    return OK


# test.


def _test(args: argparse.Namespace, config: Config) -> int:
    """A preflight and one call. Nothing between the two interprets what pytest produced.

    The verb writes nothing on the host: no run directory, no `env.txt`, no `latest`, no
    pruning and no verdict. It validates no case and reads no `evals/`, so a malformed case
    never blocks a test run. docs/cowork_test.md.
    """
    try:
        roots = plugin_roots(args.path)
    except CaseError as error:
        return _usage(str(error))
    if len(roots) > 1:
        named = ", ".join(str(root) for root in roots)
        return _usage(f"{args.path} covers more than one plugin root: {named}. pytest takes one")

    image = PytestImage(config)
    tail = tuple(args.pytest_args)
    if args.dry_run:
        # Before the preflight, unlike `run --dry-run`, which prunes the log root and so
        # must not act behind a failed one. This prints an argument list and does nothing
        # else, so there is nothing for a preflight to guard. docs/cli.md.
        for argument in image.run_argv(args.path, pytest_args=tail):
            print(argument)
        return OK
    if args.build_missing:
        if not image.docker.image_is_present():
            image.docker.build()
        if not image.image_is_present():
            image.build()
    unmet = preflight.checks(TEST, config)
    if unmet:
        return _refuse(unmet, PREFLIGHT_FAILED)

    return image.run(args.path, pytest_args=tail)


# setup, login, check, prune and panel.


def _setup(config: Config) -> int:
    """Build the two images. An image already at its digest is `current`.

    It does not log in. Building an image and obtaining a credential are two things, and
    `login` is the verb that does the second: a machine whose login was revoked needs that
    one act and not a second pass over two images that are already current. docs/cli.md.
    """
    image = Docker(config)
    test_image = PytestImage(config)
    for artefact in (image, test_image):
        if artefact.image_is_present():
            print(f"{artefact.tag}: current")
        else:
            artefact.build()
    return OK


def _login(args: argparse.Namespace, config: Config) -> int:
    """Make the container login, report it, or replace it. It builds nothing.

    The daemon and the image are the two conditions the login container itself needs, and
    they are the two this reads from `Docker.check`: the credential is what it is about to
    make, and `docker.env_passthrough` reaches a run and not this container.

    There is no login under `docker.credential: bedrock`. That route reads Claude's own
    credential from the host, so this verb has nothing to make, in either mode, and
    `check --docker` is what reports a name it is missing. docs/docker.md.

    There is no headless login. The CLI opens a browser and reads a code back in its own
    prompt, so a stdin that is not a terminal is refused here rather than left to `docker
    run -it`, whose message says nothing about what the operator has to do.
    """
    image = Docker(config)
    if not image.uses_login:
        return _refuse(
            [
                f"docker.credential is {image.credential}, so there is no login to make: "
                "the host variables are the credential, and cowork_evals check --docker "
                "reports one that is unset"
            ],
            PREFLIGHT_FAILED,
        )
    if args.check:
        if image.has_credential():
            print(f"{image.credentials_file}: current")
            return OK
        return _refuse([f"no credential: {remedy(Condition.CREDENTIAL)}"], PREFLIGHT_FAILED)

    if image.has_credential() and not args.force:
        print(f"{image.credentials_file}: current")
        return OK

    blocking = [
        message
        for condition, message in image.check()
        if condition in (Condition.DAEMON, Condition.IMAGE)
    ]
    if blocking:
        return _refuse(blocking, PREFLIGHT_FAILED)
    if not sys.stdin.isatty():
        return _refuse(
            [
                "no terminal: the login opens a browser and reads a code back, so run "
                "cowork_evals login --docker from a shell, not from a pipe or an agent"
            ],
            PREFLIGHT_FAILED,
        )

    try:
        image.login()
    except DockerError as error:
        return _refuse([str(error)], FAILED)
    print(f"{image.credentials_file}: logged in")
    return OK


def _check(args: argparse.Namespace, config: Config) -> int:
    """Report what each named backend is missing. It writes nothing and never builds.

    One backend prints `ready`, or its unmet lines on stderr. There the operator named the
    backend, nothing needs disambiguating, and an unmet condition is a refusal.

    `--all` is a report and goes to stdout whole, in backend order: a ready backend is stated
    rather than silent, and every line says which backend it belongs to. Splitting it across
    two streams would interleave it out of order.

    The exit code is the same in both: 0 when nothing is unmet, 3 otherwise. docs/cli.md.
    """
    if args.backend != ALL:
        unmet = preflight.checks(args.backend, config)
        if not unmet:
            print("ready")
            return OK
        return _refuse(unmet, PREFLIGHT_FAILED)

    failed = False
    for backend, unmet in preflight.report_all(config):
        print(f"{backend}: {'not ready' if unmet else 'ready'}")
        for line in unmet:
            print(f"  {line}")
        failed = failed or bool(unmet)
    return PREFLIGHT_FAILED if failed else OK


def _docs(args: argparse.Namespace) -> int:
    """Print where the shipped documentation is, or the path of one document.

    It reads nothing but the filesystem, writes nothing, and needs no configuration and no
    backend. A consumer's Claude Code session runs it to find the authoring contract, so
    what it prints is paths and names and never prose. docs/cli.md.
    """
    names = resources.documents()
    if not names:
        return _refuse(["no documentation in this installation"], PREFLIGHT_FAILED)

    if args.name is None:
        print(resources.docs_dir())
        for name in names:
            print(name)
        return OK

    path = resources.document(args.name)
    if path is None:
        return _refuse(
            [f"no document named {args.name!r}", "the names are:", *names],
            USAGE,
        )
    print(path)
    return OK


def _panel(args: argparse.Namespace, config: Config) -> int:
    """Every case under the path, joined to what each backend last said about it.

    The path is resolved exactly as `run` resolves it, so the same argument shows what would
    run and what running it last produced. It reaches no backend, spends nothing and writes
    nothing under the history root.

    A path selecting no case is exit 2, as on `run`. A history line that does not parse is a
    warning on stderr and leaves the exit code at 0: the row is rendered from the records
    that did parse, which is how a failed append behaves on `run`.
    """
    try:
        roots = plugin_roots(args.path)
    except CaseError as error:
        return _usage(str(error))

    discovered = [(plugin, discover(target)) for plugin, target in _targets(args.path, roots)]
    if not sum(len(cases) for _, cases in discovered):
        return _usage(f"{args.path} selects no case")

    built, warnings = panel.rows(config.panel.root, discovered, removed=args.removed)
    for warning in warnings:
        print(f"panel: {warning}", file=sys.stderr)
    print(panel.table(built), end="")

    for option, render in (("markdown", panel.markdown), ("json", panel.snapshot)):
        named = getattr(args, option)
        if named is not None:
            Path(named).write_text(render(built), encoding="utf-8")
            print(f"wrote {named}")
    return OK


def _init() -> int:
    """Write the configuration file, every shipped skill and the `CLAUDE.md` block, into the
    working directory.

    The skills are whatever `src/cowork_evals/data/skills/` holds, one directory each, so
    adding one is adding a directory and is no change here. docs/library.md.

    It never overwrites. A target that exists is left exactly as it is and reported, so a
    second run changes nothing and a consumer's own edits survive. Regenerating one means
    deleting it first, which is the operator's act and not this verb's. docs/cli.md.
    """
    targets = [(resources.EXAMPLE_CONFIG, Path(resources.CONFIG_NAME)), *resources.skills()]
    if len(targets) == 1:
        return _refuse(["no skill in this installation"], PREFLIGHT_FAILED)

    written = 0
    for source, target in targets:
        if target.exists():
            print(f"kept {target}")
            continue
        if not source.is_file():
            return _refuse([f"{source.name} is missing from this installation"], PREFLIGHT_FAILED)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text())
        print(f"wrote {target}")
        written += 1

    written += _init_memory()
    if written == 0:
        print("nothing to do: every target was already there")
    return OK


def _init_memory() -> int:
    """Append the pointer block to `CLAUDE.md`, creating the file when it is absent.

    The marker is the block's own heading. A file already carrying it is left alone, whatever
    the block below the heading has since been edited to say.
    """
    target = Path(resources.MEMORY_NAME)
    if target.is_file():
        existing = target.read_text()
        if resources.MEMORY_MARKER in existing:
            print(f"kept {target}: it already carries the block")
            return 0
        separator = "" if existing.endswith("\n") else "\n"
        target.write_text(existing + separator + resources.MEMORY_BLOCK)
        print(f"appended to {target}")
        return 1
    target.write_text(resources.MEMORY_BLOCK.lstrip("\n"))
    print(f"wrote {target}")
    return 1


def _prune(args: argparse.Namespace, config: Config) -> int:
    """Delete what this command created, and nothing else.

    `--history` reads `panel.root` and ignores `--out`: that option names the log root, and a
    record outlives the run directory it was made in. docs/panel.md.
    """
    if not args.docker and not args.logs and not args.history:
        return _usage("prune takes --docker, --logs, --history, or any combination of them")
    if args.logs:
        for deleted in logs.prune(logs.log_root(args.out), args.older_than):
            print(f"removed {deleted}")
    if args.history:
        for pruned in panel.prune(config.panel.root, args.older_than):
            print(f"pruned {pruned}")
    if args.docker:
        _prune_images(config, args.older_than)
    return OK


def _stale(
    inventory: list[tuple[datetime, str]] | list[tuple[str, datetime]],
    current: set[str],
    cutoff: datetime,
) -> list[str]:
    """Which tags a prune removes: neither current digest, and built before the cutoff.

    Separate from `_prune_images` so the rule is asserted against a hand-written inventory
    rather than against whatever images a machine happens to hold.
    """
    return [tag for tag, created in inventory if tag not in current and created < cutoff]


def _prune_images(config: Config, days: int) -> None:
    """Every tag of both repositories except the current digest of each.

    The container login is left alone: it is a credential, not a build product, and
    deleting it forces an interactive login. docs/cli.md.
    """
    current = {Docker(config).tag, PytestImage(config).tag}
    cutoff = datetime.now().astimezone() - timedelta(days=days)
    inventory = docker.images(docker.REPOSITORY, pytest_image.REPOSITORY)
    for tag in _stale(inventory, current, cutoff):
        docker.remove_image(tag)
        print(f"removed {tag}")


# Printing, and the two refusals every verb shares.


def _usage(message: str) -> int:
    print(message, file=sys.stderr)
    return USAGE


def _refuse(lines: list[str], code: int) -> int:
    for line in lines:
        print(line, file=sys.stderr)
    return code


def console_main() -> None:
    """The `[project.scripts]` entry point, and the one place `sys.exit` is called."""
    sys.exit(main())
