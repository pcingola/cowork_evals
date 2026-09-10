"""The command: the parser, the seven verbs, the dispatch and the exit codes.

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
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import cowork_backend, docker, gate, logs, preflight, resources, results, validate
from .cases import CaseError, discover, plugin_name, plugin_roots
from .config import Config, CoWorkError
from .docker import Docker, DockerError, pytest_image
from .docker.pytest_image import PytestImage
from .harness import RunOptions
from .preflight import COWORK, DOCKER, TEST

# `check --all`, the one selection that is not a backend.
ALL = "all"

# The exit codes. docs/cli.md. `test` is the one verb that returns a code from below
# unchanged, and it returns pytest's.
OK = 0
GATE_FAILED = 1
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
    "--allow-tools": "allow_tools",
    "--max-cost-usd": "max_cost_usd",
    "--build-missing": "build_missing",
}

# What each backend cannot honour. An option here is an operator mistake, so it is a usage
# error. A *case* that needs a field the backend cannot honour is reported skipped and
# fails the gate instead, and the two are never conflated. docs/cli.md.
REFUSED = {
    DOCKER: ("--timeout-seconds",),
    COWORK: ("--model", "--allow-tools", "--max-cost-usd", "--build-missing"),
}

# Why each is refused, so a message says more than that it was.
REFUSAL_REASONS = {
    "--timeout-seconds": "claude plugin eval has no timeout flag to map it onto",
    "--model": "the session decides its model",
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
    _test_parser(verbs)
    _setup_parser(verbs)
    _check_parser(verbs)
    _prune_parser(verbs)
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
    verb = verbs.add_parser("run", help="run a suite and gate what it produced")
    _backend_group(verb, DOCKER, COWORK)
    verb.add_argument("path", help="a case, a skill, an evals/ tree, a plugin root or a sweep")
    verb.add_argument("--runs", type=int, help="how many times each case runs")
    verb.add_argument("--timeout-seconds", type=float, help="each run's timeout, on --cowork")
    verb.add_argument("--model", help="the model under test, on --docker")
    verb.add_argument("--judge-model", help="the model behind llm and baseline graders")
    verb.add_argument("--allow-tools", nargs="+", help="the tool grant, on --docker")
    verb.add_argument("--max-cost-usd", type=float, help="one suite's ceiling, on --docker")
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


def _check_parser(verbs: Any) -> None:
    verb = verbs.add_parser("check", help="report what a backend is missing")
    _backend_group(verb, DOCKER, COWORK, ALL)


def _prune_parser(verbs: Any) -> None:
    """`prune` takes any combination of its selection flags, and requires at least one.

    They are not a mutually exclusive group: pruning images and logs in one invocation is
    ordinary. `argparse` cannot express `at least one`, so the refusal is the verb's and
    returns 2.
    """
    verb = verbs.add_parser("prune", help="delete artefacts this command created")
    verb.add_argument("--docker", action="store_true", help="images this command built")
    verb.add_argument("--logs", action="store_true", help="run directories under the log root")
    verb.add_argument(
        "--older-than", type=int, default=logs.RUN_PRUNE_DAYS, help="restrict every selection"
    )
    verb.add_argument("--out", help="the log root, replacing logs/evals")


def _init_parser(verbs: Any) -> None:
    """`init` takes no backend and no option. It writes three targets and overwrites none."""
    verbs.add_parser("init", help="write the config, the skill and a CLAUDE.md block")


def _docs_parser(verbs: Any) -> None:
    """`docs` takes no backend. It reads the shipped tree and writes nothing."""
    verb = verbs.add_parser("docs", help="print where the shipped documentation is")
    verb.add_argument(
        "name",
        nargs="?",
        help="one document, with or without .md. Omitted, every name is listed",
    )


# The refusals.


def _given(args: argparse.Namespace, attribute: str) -> bool:
    """Whether an option was typed. Every default is `None` or `False`."""
    value = getattr(args, attribute, None)
    return value is not None and value is not False


def refusal(args: argparse.Namespace) -> str | None:
    """The one line naming an option the chosen backend refuses, or `None`."""
    backend = getattr(args, "backend", None)
    for option in REFUSED.get(backend, ()):
        if _given(args, OPTION_ATTRIBUTES[option]):
            return f"{option} is not accepted on --{backend}: {REFUSAL_REASONS[option]}"
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
    if args.verb == "test":
        return _test(args, config)
    if args.verb == "setup":
        return _setup(config)
    if args.verb == "check":
        return _check(args, config)
    if args.verb == "docs":
        return _docs(args)
    if args.verb == "init":
        return _init()
    return _prune(args, config)


# run.


def _run(args: argparse.Namespace, config: Config) -> int:
    """Preflight, validate, count, prune, then run every selected plugin and gate once.

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
    if not _selected(targets, tags, args.case):
        return _usage(f"{args.path} selects no case{_filters(tags, args.case)}")

    root = logs.log_root(args.out)
    for deleted in logs.prune(root, logs.RUN_PRUNE_DAYS):
        print(f"pruned {deleted}")

    if args.dry_run:
        return _dry_run(args, config, root, targets, tags)

    return _sweep(args, config, root, targets, tags)


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

    A dry run reports the exit code the run would reach, so it is not always 0. On `--cowork`
    a suite whose every case is skipped would fail the gate, and this returns the gate's code
    rather than a pass: a dry run wired into CI as a portability check has to go red on a
    suite that is dead on that backend. The container backend's skips are the harness's and
    are decided at run time, so a dry run there cannot know them and reports nothing.
    docs/cli.md.
    """
    dead = False
    for plugin, target in targets:
        name = plugin_name(plugin)
        print(f"# {name}")
        if args.backend == COWORK:
            dead = _dry_run_cowork(args, config, target, tags) or dead
            continue
        would_be = root / logs.run_dir_name(logs.scope_name(target, [plugin])) / logs.slug(name)
        for argument in Docker(config).run_argv(target, would_be, _options(args, config, tags)):
            print(argument)
    if dead:
        return _refuse(
            ["every selected case is skipped on this backend, so the gate would fail"],
            GATE_FAILED,
        )
    return OK


def _dry_run_cowork(args: argparse.Namespace, config: Config, target: Path, tags: tuple) -> bool:
    """One line per case, then the ceiling arithmetic. This backend builds no command line.

    The skips are the point: a skipped case fails the gate, so an operator reads which ones
    before spending a VM boot on the rest.

    It returns whether the suite is dead here, meaning it planned no submission at all
    because every case was skipped. An empty selection is not that: it is refused earlier.
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
        for reason in entry.skips.case:
            print(f"  skip: {reason}")
        for grader, reason in sorted(entry.skips.graders.items()):
            print(f"  grader skip {grader}: {reason}")
    print(prepared.arithmetic)
    return prepared.submissions == 0


def _options(args: argparse.Namespace, config: Config, tags: tuple) -> RunOptions:
    """The container backend's options, resolved through the one ladder. docs/library.md."""
    return RunOptions.resolve(
        config,
        model=args.model,
        judge_model=args.judge_model,
        max_cost_usd=None if args.max_cost_usd is None else str(args.max_cost_usd),
        allow_tools=None if args.allow_tools is None else tuple(args.allow_tools),
        runs=args.runs,
        tags=tags,
        case=args.case,
    )


def _sweep(
    args: argparse.Namespace,
    config: Config,
    root: Path,
    targets: list[tuple[Path, Path]],
    tags: tuple,
) -> int:
    """Every selected plugin in turn, inside one run directory, gated once."""
    image = Docker(config) if args.backend == DOCKER else None
    scope = logs.scope_name(args.path, [plugin for plugin, _ in targets])
    directory = logs.run_dir(root, scope)
    logs.point_latest(root, directory)

    with logs.tee(directory):
        logs.write_env(directory, args.backend, image=None if image is None else image.tag)
        extra = _each_plugin(args, config, directory, targets, tags, image)
        decided = gate.gate(directory, extra=extra)
        (directory / logs.GATE_FILE).write_text(decided.text, encoding="utf-8")
        print(decided.text, end="")
    return OK if decided.passed else GATE_FAILED


def _each_plugin(
    args: argparse.Namespace,
    config: Config,
    directory: Path,
    targets: list[tuple[Path, Path]],
    tags: tuple,
    image: Docker | None,
) -> tuple[str, ...]:
    """Run each plugin, stopping on the total cost ceiling.

    The check runs before the first plugin, so a ceiling of 0 stops the invocation before
    it spends anything. On `--cowork` the sum is the judge spend alone: the session is
    billed to the account and is not observable from the host, so the ceiling that binds
    there is the driver's `max_runs`, in the preflight above. docs/running_evals.md.
    """
    ceiling = config.eval.max_cost_total_usd
    for plugin, target in targets:
        spent = results.spend(directory)
        if spent >= ceiling:
            return (
                f"the total cost ceiling stopped the sweep at {plugin}: "
                f"{spent} spent, eval.max_cost_total_usd is {ceiling}",
            )
        output = logs.plugin_dir(directory, plugin_name(plugin))
        try:
            if image is not None:
                image.run(target, output, _options(args, config, tags))
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
            # The gate reads the missing document and fails, so the sweep goes on.
            print(f"{plugin}: {error}", file=sys.stderr)
    return ()


# test.


def _test(args: argparse.Namespace, config: Config) -> int:
    """A preflight and one call. Nothing between the two interprets what pytest produced.

    The verb writes nothing on the host: no run directory, no `env.txt`, no `latest`, no
    pruning and no gate. It validates no case and reads no `evals/`, so a malformed case
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


# setup, check and prune.


def _setup(config: Config) -> int:
    """Build the two images, then log in. An image already at its digest is `current`.

    The login step belongs to the login route alone. On the environment route there is
    nothing interactive to do, and starting a login there would ask for a credential the run
    will not read. It says which route it took, because a silent skip reads as a build that
    forgot the login. docs/docker.md.
    """
    image = Docker(config)
    test_image = PytestImage(config)
    for artefact in (image, test_image):
        if artefact.image_is_present():
            print(f"{artefact.tag}: current")
        else:
            artefact.build()
    if image.uses_env_auth:
        print(f"docker.auth_env: {', '.join(image.auth_env)}, so there is no login to make")
        return OK
    if image.has_credential():
        print(f"{image.credentials_file}: current")
        return OK
    image.login()
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


def _init() -> int:
    """Write the configuration file, the skill and the `CLAUDE.md` block, into the working
    directory.

    It never overwrites. A target that exists is left exactly as it is and reported, so a
    second run changes nothing and a consumer's own edits survive. Regenerating one means
    deleting it first, which is the operator's act and not this verb's. docs/cli.md.
    """
    written = 0
    for source, target in (
        (resources.EXAMPLE_CONFIG, Path(resources.CONFIG_NAME)),
        (resources.SKILL, resources.SKILL_TARGET),
    ):
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
    """Delete what this command created, and nothing else."""
    if not args.docker and not args.logs:
        return _usage("prune takes --docker, --logs, or both")
    if args.logs:
        for deleted in logs.prune(logs.log_root(args.out), args.older_than):
            print(f"removed {deleted}")
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
