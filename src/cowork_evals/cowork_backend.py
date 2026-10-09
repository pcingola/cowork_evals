"""The CoWork backend: which case this backend can run, and what running one produces.

The layer above the driver. It reads the case tree `cases.py` produced, submits each case's
prompt through `CoWork`, grades the session document, and writes the same
`aggregate-result.json` v1 document every other backend writes.

What this backend cannot run is docs/eval_format.md: a case asking for something a live session
does not offer carries the `no-cowork` tag, submits nothing here and is counted rather than
failed. It reads the tag and decides no case skip of its own. A key the case left to its default
is not a request, which is why this reads which keys a case wrote and never a merged value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cases import EVAL_DIR, JUDGED, NO_COWORK, Case, CaseError, discover, plugin_roots
from .config import Config, CoWorkError
from .cowork import CoWork
from .grader import grade as grade_structural
from .grader import skipped as skipped_result
from .judge import grade as grade_judged
from .judge import resolve_model
from .results import CaseResult, Run, build, write

# The MCP stand-in directory. Its three layers, suite, group and case, are
# docs/claude_code/plugin_eval_reference.md.
MOCKS_DIR = "mocks"
MOCKS_REASON = "stand-ins are the harness's, and the MCP servers here are real"

# The grader target and focus value that names those stand-ins.
MOCK_CALLS = "mock_calls"

# Case keys this backend cannot honour, each with why. The session decides its own model,
# its own tools and its own system prompt, and no turn cap reaches it.
# docs/approaches.md.
UNHONOURED_CASE_KEYS = {
    "max_turns": "no turn cap reaches a CoWork session",
    "model": "the session decides its model",
    "allowed_tools": "the session decides its tools",
    "append_system_prompt": "the session decides its system prompt",
    "env": "nothing sets an environment variable in the VM",
}

# The `case.yaml` keys, which are all of one shape and share one reason.
CONTEXT_PREFIX = "context."
CONTEXT_REASON = "nothing stages files into the VM"


def unrunnable(case: Case, plugin_root: Path | str) -> tuple[str, ...]:
    """Every reason a live CoWork session cannot run this case, from all three sources.

    Empty for a case this backend runs. It is the one derivation of that fact: the validator
    calls it to enforce the `no-cowork` tag in both directions, and `declared` calls it to
    say what the tag on a case declares. Two derivations could disagree, and a validator that
    passed a case the backend then refused is the state docs/eval_format.md removes.

    `plugin_root` is where the `evals/` tree starts, which is what makes a suite-wide
    `evals/mocks/` reach a case several directories below it.
    """
    reasons = [
        f"{key}: {why}" for key, why in UNHONOURED_CASE_KEYS.items() if key in case.frontmatter_keys
    ]
    reasons += [
        f"{key}: {CONTEXT_REASON}" for key in case.case_yaml_keys if key.startswith(CONTEXT_PREFIX)
    ]
    reasons += [
        f"{directory / MOCKS_DIR}: {MOCKS_REASON}"
        for directory in _mock_layers(case.directory, Path(plugin_root))
    ]
    return tuple(reasons)


def declared(case: Case, plugin_root: Path | str) -> str | None:
    """Why this backend submits nothing for the case, or `None` for a case it runs.

    The tag decides, and `unrunnable` says what the tag declares. The validator is what keeps
    the two in step, so a case reaching this with a source and no tag is one no preflight
    read: it is submitted, and the key it wrote is ignored by the session.
    """
    if not case.no_cowork:
        return None
    reasons = unrunnable(case, plugin_root)
    return f"{NO_COWORK}: {'; '.join(reasons)}" if reasons else NO_COWORK


def grader_skips(case: Case) -> dict[str, str]:
    """The one grader skip that is decided before a run.

    A grader skip runs the case and drops that grader from the score, so a case does not fail
    for a grader that was never asked. It is the only skip this backend decides before a run:
    a case a session cannot run is declared by the case and is not skipped.

    The other grader skip, an `llm` grader whose focus turns out to be an image, is read from
    the file's bytes and so exists only after the run. `judge.py` decides that one.
    """
    skipped = {}
    for grader in case.graders:
        for key in ("target", "focus"):
            if getattr(grader.config, key, None) == MOCK_CALLS:
                skipped[grader.name] = f"{key}: {MOCK_CALLS}, and no stand-in serves a CoWork run"
                break
    return skipped


def _mock_layers(case_dir: Path, plugin_root: Path) -> list[Path]:
    """Every directory from `evals/` down to the case that carries a `mocks/`.

    `evals/mocks/` covers every case in the plugin and a case's own `mocks/` covers that case
    alone, which are the layers the harness adds up.
    """
    case_dir = case_dir.resolve()
    evals = (plugin_root.resolve() / EVAL_DIR).resolve()
    above = [case_dir, *case_dir.parents]
    chain = above[: above.index(evals) + 1] if evals in above else [case_dir]
    return [directory for directory in reversed(chain) if (directory / MOCKS_DIR).is_dir()]


# A case that writes no `runs` key runs once here. docs/running_evals.md.
DEFAULT_RUNS = 1

# The driver failure that is collected rather than discarded: the run timed out, the session
# kept going in the VM, and what it produced up to that point is still graded. That is what
# the harness does. docs/cowork_driver.md.
RUN_TIMEOUT_CODE = 7


@dataclass(frozen=True, slots=True)
class Entry:
    """One case as this backend will run it: whether it runs here, how often, how long.

    `declared` is the reason line a case carrying `no-cowork` puts in the result document,
    and `None` for a case this backend submits. `graders` is the grader skips, which leave
    the case running.
    """

    case: Case
    declared: str | None
    graders: dict[str, str]
    runs: int
    timeout_seconds: float

    @property
    def name(self) -> str:
        return self.case.name

    @property
    def submissions(self) -> int:
        """What this case costs the ceiling. A declared case submits nothing."""
        return 0 if self.declared is not None else self.runs


@dataclass(frozen=True, slots=True)
class Plan:
    """What a suite will do, decided without submitting anything.

    `run` calls this, and so does `--dry-run --cowork`, which prints exactly these and would
    otherwise re-derive them. It carries what each case declares and the grader skips
    `grader_skips` decides, and not the image-focus skip the judge decides after a run.
    """

    root: Path
    entries: tuple[Entry, ...]
    recent: int
    max_runs: int

    @property
    def submissions(self) -> int:
        return sum(entry.submissions for entry in self.entries)

    @property
    def over_ceiling(self) -> bool:
        return self.submissions + self.recent > self.max_runs

    @property
    def arithmetic(self) -> str:
        """The three numbers the ceiling compares. `--dry-run --cowork` prints it."""
        return (
            f"{self.submissions} submissions planned, "
            f"{self.recent} already made in the last 24 hours, max_runs is {self.max_runs}"
        )

    @property
    def refusal(self) -> str:
        return f"the rate ceiling would be exceeded: {self.arithmetic}"


def plan(
    target: Path | str,
    *,
    config: Config | None = None,
    runs: int | None = None,
    timeout_seconds: float | None = None,
    judge_model: str | None = None,
    tags: tuple[str, ...] = (),
    case_glob: str | None = None,
) -> Plan:
    """What `run` would do. It reads files, submits nothing and raises only `CaseError`.

    `judge_model` is accepted here so that one signature covers both calls; it changes
    nothing a plan reports, and reaches the judge and `suite.judgeModel` through `run`.
    """
    del judge_model
    settings = (config if config is not None else Config.load()).cowork
    root = _one_plugin_root(target)
    entries = tuple(
        Entry(
            case=case,
            declared=declared(case, root),
            graders=grader_skips(case),
            runs=_effective_runs(case, runs),
            timeout_seconds=_effective_timeout(case, timeout_seconds, settings.run_timeout),
        )
        for case in discover(target, tags=tags, case_glob=case_glob)
    )
    return Plan(
        root=root,
        entries=entries,
        recent=CoWork(settings).recent(),
        max_runs=settings.max_runs,
    )


def run(
    target: Path | str,
    output_dir: Path | str,
    *,
    config: Config | None = None,
    runs: int | None = None,
    timeout_seconds: float | None = None,
    judge_model: str | None = None,
    tags: tuple[str, ...] = (),
    case_glob: str | None = None,
) -> Path:
    """Run every selected case and return the path of the result document written.

    Cases run in sequence, and the runs of a case run in sequence: there is one desktop
    application and one composer. The caller created `output_dir`, as it does for
    `Docker.run`. Nothing here names a run directory, writes a `latest` symlink, writes an
    `env.txt`, prunes, prints, or decides pass or fail. docs/cli.md.
    """
    resolved = config if config is not None else Config.load()
    prepared = plan(
        target,
        config=resolved,
        runs=runs,
        timeout_seconds=timeout_seconds,
        tags=tags,
        case_glob=case_glob,
    )
    if prepared.over_ceiling:
        raise CoWorkError(2, prepared.refusal)

    model = resolve_model(judge_model, resolved)
    started = datetime.now(timezone.utc)
    results = [_run_case(entry, resolved, model) for entry in prepared.entries]
    document = build(
        root=prepared.root,
        cases=results,
        started_at=started.isoformat(),
        duration_seconds=(datetime.now(timezone.utc) - started).total_seconds(),
        judge_model=model,
        case_filter=case_glob,
        tag_filters=tags,
    )
    return write(output_dir, document)


# One case, and one run of it.


def _run_case(entry: Entry, config: Config, model: str) -> CaseResult:
    """Every run of one case. A declared case submits nothing and leaves `arms.with` empty."""
    if entry.declared is not None:
        return CaseResult(case=entry.case, declared=True, declared_reason=entry.declared)

    # `Config` is frozen, so a differing timeout is a differing `CoWork`. The ceiling and
    # the run log are files, and still count across instances.
    driver = CoWork(config.cowork, run_timeout=entry.timeout_seconds)
    return CaseResult(
        case=entry.case, runs=tuple(_one_run(driver, entry, model) for _ in range(entry.runs))
    )


def _one_run(driver: CoWork, entry: Entry, model: str) -> Run:
    """One submission. A `CoWorkError` becomes this run's error, and the suite continues."""
    try:
        session = driver.run(entry.case.prompt)
    except CoWorkError as error:
        return _after_failure(driver, entry, model, error)
    return _graded(session, entry, model)


def _after_failure(driver: CoWork, entry: Entry, model: str, error: CoWorkError) -> Run:
    """What is still readable after the driver raised.

    A run timeout is collected: the error carries the session directory, the CoWork session
    keeps running in the VM, and the run is graded on what it produced up to that point,
    with `error` recording the timeout. A `collect` that then raises code 8, meaning the
    session wrote no assistant text before the timeout, leaves the run with the timeout as
    its error, score 0 and no graders.
    """
    message = _message(error)
    session_dir = None if error.session_dir is None else str(error.session_dir)
    if error.code == RUN_TIMEOUT_CODE and error.session_dir is not None:
        try:
            session = driver.collect(error.session_dir, prompt=entry.case.prompt)
        except CoWorkError:
            return Run(
                session_dir=session_dir, timeout_seconds=entry.timeout_seconds, error=message
            )
        return _graded(session, entry, model, error=message)
    return Run(session_dir=session_dir, timeout_seconds=entry.timeout_seconds, error=message)


def _graded(session: dict[str, Any], entry: Entry, model: str, *, error: str | None = None) -> Run:
    """Every grader of one case against one session document, structural then judged."""
    results = []
    judge_cost = 0.0
    for grader in entry.case.graders:
        reason = entry.graders.get(grader.name)
        if reason is not None:
            results.append(skipped_result(grader, reason))
        elif grader.type in JUDGED:
            judged = grade_judged(grader, session, entry.case.directory, model=model)
            results.append(judged.result)
            judge_cost += judged.cost_usd
        else:
            results.append(grade_structural(grader, session))
    return Run.collected(
        session,
        tuple(results),
        timeout_seconds=entry.timeout_seconds,
        judge_cost_usd=judge_cost,
        error=error,
    )


def _message(error: CoWorkError) -> str:
    return f"{error.code}: {error}"


# What a target selects, and what a case asked for.


def _one_plugin_root(target: Path | str) -> Path:
    """The one plugin root the target covers.

    A target covering more than one is a usage error in docs/cli.md, and the CLI is what
    exits: there is no sweep on this backend, for the reason in docs/running_evals.md.
    """
    resolved = Path(target).resolve()
    roots = plugin_roots(resolved)
    if len(roots) > 1:
        named = ", ".join(str(root) for root in roots)
        raise CaseError(f"{resolved} covers more than one plugin root: {named}")
    return roots[0]


def _effective_runs(case: Case, override: int | None) -> int:
    if override is not None:
        return override
    declared = case.frontmatter.runs
    return DEFAULT_RUNS if declared is None else declared


def _effective_timeout(case: Case, override: float | None, configured: float) -> float:
    if override is not None:
        return float(override)
    declared = case.frontmatter.timeout_seconds
    return float(configured) if declared is None else declared
