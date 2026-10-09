"""The check layer: a consumer's own Python, over the files one eval run produced.

An eval case is scored by graders, and a grader is one of the six types `claude plugin eval`
defines. That list is closed: the harness is a command this repository does not own. So an
assertion outside the six cannot be written, and the common one that does not fit is an
assertion about the contents of a file the run produced. A `file_exists` grader says
`totals.xlsx` was created and says nothing about the numbers in it.

A check is that assertion, written as a Python function under the case's `checks/` directory.
This module discovers those functions, runs each of them once per run over the files that run
left on the host, and appends each verdict to the same `aggregate-result.json` the graders
wrote into, as a grader result of type `check`. `verdict.py` needs no rule for it: a failed
grader fails the run whatever its type, so a failed check fails the run exactly as a failed
`regex` grader does. An advisory check is the one exception, and `verdict.py` reads it by its
type.

A check runs on the host, in this package's process, after the run is graded and after
`traces.collect` has put the run's files under the run directory. It never enters the container
and never enters the CoWork VM, so nothing about the session binds it: not the interpreter, not
the wheel set, not the image. A check file is the first row of the three kinds of code in
`CLAUDE.md` although it sits under the eval path, and what it imports is the consumer's own
dependency. docs/checks.md.

One check is one decorated function, and it asserts, converts and asks a judge, because all
three are things a Python function does. A conversion that decides nothing needs no mechanism
of its own.

Nothing here raises. A file that will not import, an assertion that fails, an exception out of
a check and a run with no collected files are each a check result carrying the reason.
"""

from __future__ import annotations

import functools
import hashlib
import importlib.util
import json
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import judge as judging
from . import results
from .cases import CHECKS_DIR, Grader, check_files
from .grader import GraderResult
from .harness import RESULT_NAME
from .results import ARM_WITH, ARM_WITHOUT, ARMS, DECLARED_UNRUNNABLE
from .traces import LAST_MESSAGE_NAME, TRACE_NAME, WORKSPACE_NAME

# The attribute `@check` writes, and the grader type a check result carries in the document.
# `verdict._judge_grader` decides a failed check the way it decides any failed grader, with no
# new condition anywhere. docs/checks.md.
# The attribute is there when the function is a check, and it holds whether it is advisory.
MARKER = "__cowork_evals_check__"
CHECK_TYPE = "check"

# The type an advisory check's definition carries, which is how the verdict tells them apart.
ADVISORY_TYPE = "check-advisory"

# Every check weighs the same. There is no weight on `@check` and no way to write one.
WEIGHT = 1

# What a check writes into, and what the layer writes beside it. Both sit in the run
# directory, which is the directory `verdict.artifacts` names on a failure line.
SCRATCH_DIR = "scratch"
CHECKS_FILE = "checks.jsonl"

# The reason a run with no collected artefacts produces. A skip fails the run, which is the
# existing rule, so a suite cannot go green by asserting nothing under `--no-keep-traces`.
NO_ARTEFACTS = (
    "the run kept no artefacts, so there is nothing to check. "
    "--no-keep-traces and eval.keep_traces: false both give up every check"
)

# What `run.judge` says when it was given no path. There is no default of everything: a judge
# shown the whole run directory is judging the transcript as well as the artefact.
NO_PATHS = "run.judge was called with no path, and it has no default of everything"

# The two fields a check judge's spend is added to: one on a run, one on the document.
RUN_SPEND = "judgeCostUsd"
SUITE_SPEND = "costUsd"

# The name `judge.tally` sees. It never leaves `run.judge`, which reads the verdict and the
# spend off the result and carries the check's own name into the outcome.
JUDGE_GRADER = "run.judge"


class CheckError(Exception):
    """What a `Run` method raises when a check asked for something that is not there.

    It is caught like any other exception out of a check, and its message alone is the
    explanation: a traceback through this module says nothing the message does not.
    """


@dataclass(frozen=True, slots=True)
class Result:
    """What a check returns when it decides in words rather than by raising.

    `explanation` is what the run's grader entry and the `FAIL` line both print.
    """

    passed: bool
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class JudgeCall:
    """One `run.judge` call, kept whole for `checks.jsonl`.

    The result document's `evidence` is capped at 2000 characters, and a person reading a
    failed judged check needs the whole exchange. docs/checks.md.
    """

    prompt: str
    replies: tuple[str, ...]
    cost_usd: float

    def document(self) -> dict[str, Any]:
        return {"prompt": self.prompt, "replies": list(self.replies), "costUsd": self.cost_usd}


@dataclass(frozen=True, slots=True)
class Run:
    """One collected run, as a check reads it.

    Every field is what `traces.collect` left under the run directory, so one code path
    serves both backends: they normalise to the same three names there.

    | Field          | Is                                                              |
    | -------------- | --------------------------------------------------------------- |
    | `workspace`    | the agent's working directory, as a path                        |
    | `last_message` | the final assistant message, as text                            |
    | `trace`        | the transcript, as a path. The two backends write two formats   |
    | `case_dir`     | the case directory on this host                                 |
    | `run_dir`      | the collected run directory, and the judge's working directory  |
    | `scratch`      | a directory a check may write into                              |
    | `index`        | which run of the case this is, 1-based, as the verdict prints it |

    There is no created-file list. The v1 run entry carries none, so there would be nothing
    to read one from on the container backend, and walking `workspace` sees more than a
    created-file list does: it counts a file the run modified, which `file_exists` never does.
    """

    workspace: Path
    last_message: str
    trace: Path
    case_dir: Path
    run_dir: Path
    scratch: Path
    index: int
    judge_model: str = ""
    calls: list[JudgeCall] = field(default_factory=list)

    def file(self, name: str) -> Path:
        """One file under `workspace`, by the name the agent wrote it under.

        A name that resolves to nothing, and a name that leaves the workspace, each raise,
        which is a failed check naming it.
        """
        root = self.workspace.resolve()
        named = (root / name).resolve()
        if not named.is_relative_to(root):
            raise CheckError(f"{name} resolves outside the workspace")
        if not named.exists():
            raise CheckError(f"{name} is not in the workspace")
        return named

    def judge(self, prompt: str, *paths: Path | str) -> Result:
        """Ask a judge model about files, in the words of the prompt. Three votes, majority.

        The judge is `claude -p` granted `Read`, `Glob` and `Grep`, running in `run_dir`, and
        it is shown the paths rather than the material: a PDF, an image and a spreadsheet
        cannot be shown as text, and reading a file is what its `Read` tool is for. A path
        outside `run_dir` reaches it as `--add-dir`.

        The whole exchange goes to `checks.jsonl`, because the document's `evidence` is
        capped at 2000 characters and a person reading a failed judged check needs all of it.

        A call naming no path, and a path that is not there, are each a failed check saying
        so. The model is `judge.resolve_model`, so `--judge-model` beats `eval.judge_model`.
        """
        if not paths:
            return Result(passed=False, explanation=NO_PATHS)
        names: list[str] = []
        add_dirs: list[str] = []
        root = self.run_dir.resolve()
        for path in paths:
            named = Path(path)
            resolved = (named if named.is_absolute() else root / named).resolve()
            if not resolved.exists():
                return Result(
                    passed=False, explanation=f"{path} is not there, so it cannot be judged"
                )
            if resolved.is_relative_to(root):
                names.append(resolved.relative_to(root).as_posix())
                continue
            names.append(str(resolved))
            outside = str(resolved if resolved.is_dir() else resolved.parent)
            if outside not in add_dirs:
                add_dirs.append(outside)

        text = judging.compose_paths(prompt, tuple(names))
        argv = judging.check_argv(self.judge_model, tuple(add_dirs))
        replies = [judging.ask(argv, text, cwd=root) for _ in range(judging.resolve_votes())]
        judged = judging.tally(_judge_grader(prompt), replies, "\n".join(names))
        self.calls.append(
            JudgeCall(
                prompt=text,
                replies=tuple(
                    f"{reply.word}: {reply.reasoning}" if reply.reasoning else reply.word
                    for reply in replies
                ),
                cost_usd=judged.cost_usd,
            )
        )
        return Result(passed=judged.result.passed, explanation=judged.result.explanation)


@dataclass(frozen=True, slots=True)
class Check:
    """One decorated function, or one file that would not import.

    `name` is `<file stem>.<function name>`, and is the name the result document, the
    failure line and `checks.jsonl` all carry. A file that would not import has the file
    stem alone, because nothing in it was reached.
    """

    name: str
    path: Path
    function: Callable[[Run], Any] | None = None
    error: str | None = None
    advisory: bool = False


@dataclass(frozen=True, slots=True)
class Outcome:
    """One check, run. It is what a grader result and a `checks.jsonl` line are built from."""

    name: str
    passed: bool
    explanation: str
    duration_seconds: float = 0.0
    skipped: bool = False
    skip_reason: str | None = None
    traceback: str | None = None
    calls: tuple[JudgeCall, ...] = ()
    cost_usd: float = 0.0
    advisory: bool = False

    def document(self) -> dict[str, Any]:
        """One `checks.jsonl` line."""
        entry: dict[str, Any] = {
            "name": self.name,
            "passed": self.passed,
            "explanation": self.explanation,
            "durationSeconds": self.duration_seconds,
        }
        if self.skipped:
            entry["skipped"] = True
            entry["skipReason"] = self.skip_reason
        if self.traceback is not None:
            entry["traceback"] = self.traceback
        if self.calls:
            entry["judge"] = [call.document() for call in self.calls]
        if self.cost_usd:
            entry["costUsd"] = self.cost_usd
        return entry


def _judge_grader(prompt: str) -> Grader:
    """The `Grader` `judge.tally` counts votes against. It is never written to a document."""
    return Grader(
        name=JUDGE_GRADER,
        type=CHECK_TYPE,
        weight=WEIGHT,
        config=None,
        markdown=prompt,
        path=Path(CHECKS_DIR),
    )


def check(
    function: Callable[[Run], Any] | None = None, *, advisory: bool = False
) -> Callable[[Run], Any] | Callable[[Callable[[Run], Any]], Callable[[Run], Any]]:
    """Mark one function as a check. `@check` and `@check(advisory=True)` are the two forms.

    A name parameter and a weight parameter are features nobody asked for: the name is the
    file stem and the function name, and every check weighs 1.

    An advisory check runs, its verdict is recorded, and a failure prints as a note: it is out
    of the score and out of the exit code. docs/checks.md.
    """
    if function is None:
        return functools.partial(check, advisory=advisory)  # type: ignore[return-value]
    setattr(function, MARKER, advisory)
    return function


# Discovery.


def discover(case_dir: Path | str) -> tuple[Check, ...]:
    """Every check of one case, in path order and then in definition order.

    A file is loaded under a module name unique to its case, so two cases each holding
    `checks/assertions.py` do not collide in `sys.modules`. The case's `checks/` directory
    is on `sys.path` while its files are loaded, so a check may import a sibling beside it,
    and is off it again afterwards. A sibling a file imported that way is removed from
    `sys.modules` with them, so the next case's `helpers.py` is that case's own.

    A decorated function is discovered in the file that defines it, and once. A file that
    imports one from a sibling gets the name it already has, not a second name of its own.

    A file that will not import yields one `Check` carrying the reason, named for the file.
    The validator reports the same failure before anything runs, so a run reaching this is a
    file that broke between the preflight and the run.
    """
    directory = Path(case_dir) / CHECKS_DIR
    files = check_files(Path(case_dir))
    if not files:
        return ()
    entry = str(directory)
    sys.path.insert(0, entry)
    loaded = set(sys.modules)
    found: list[Check] = []
    try:
        for path in files:
            found += _load(path)
    finally:
        if sys.path and sys.path[0] == entry:
            sys.path.pop(0)
        _purge(loaded, directory)
    return tuple(found)


def duplicate_names(checks: tuple[Check, ...]) -> list[str]:
    """Every name two checks of one case share, sorted. Empty when each name is its own."""
    seen: dict[str, int] = {}
    for one in checks:
        seen[one.name] = seen.get(one.name, 0) + 1
    return sorted(name for name, count in seen.items() if count > 1)


def _load(path: Path) -> list[Check]:
    try:
        module = _import(path)
    except Exception as error:  # the author's own file, and anything it raises at import
        return [Check(name=path.stem, path=path, error=_reason(path, error))]
    return [
        Check(name=f"{path.stem}.{name}", path=path, function=held, advisory=getattr(held, MARKER))
        for name, held in vars(module).items()
        if callable(held)
        and hasattr(held, MARKER)
        and getattr(held, "__module__", None) == module.__name__
    ]


def _import(path: Path) -> Any:
    """One file, executed under a module name unique to the case directory it sits in."""
    name = _module_name(path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise CheckError(f"{path} is not an importable Python file")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _module_name(path: Path) -> str:
    """`<stem>` under a digest of the case directory, so two cases cannot collide."""
    case = path.resolve().parent.parent
    digest = hashlib.sha256(str(case).encode("utf-8")).hexdigest()[:12]
    return f"cowork_evals_check_{digest}_{path.stem}"


def _purge(before: set[str], directory: Path) -> None:
    """Drop every module this case put in `sys.modules`, its siblings' entries included.

    A check function keeps its module alive through its own globals, so nothing here is
    needed after the load, and leaving `helpers` behind would hand the next case the wrong
    file.
    """
    root = directory.resolve()
    for name in set(sys.modules) - before:
        module = sys.modules.get(name)
        file = getattr(module, "__file__", None)
        if isinstance(file, str) and Path(file).resolve().is_relative_to(root):
            sys.modules.pop(name, None)


def _reason(path: Path, error: BaseException) -> str:
    return f"{path.name} could not be imported: {type(error).__name__}: {error}"


# Execution.


def execute(one: Check, run: Run) -> Outcome:
    """One check over one run. `None` or `True` passes, `False` fails, a `Result` decides.

    Any exception is a failed check carrying its message, and its traceback goes to
    `checks.jsonl`. A `CheckError` carries its message alone: a traceback through this
    module says nothing the message does not.
    """
    started = time.monotonic()
    if one.function is None:
        return Outcome(
            name=one.name,
            passed=False,
            explanation=one.error or "the check was not loaded",
            duration_seconds=time.monotonic() - started,
        )
    try:
        returned = one.function(run)
    except CheckError as error:
        return Outcome(
            name=one.name,
            passed=False,
            explanation=str(error),
            duration_seconds=time.monotonic() - started,
            calls=tuple(run.calls),
            cost_usd=sum(call.cost_usd for call in run.calls),
            advisory=one.advisory,
        )
    except Exception as error:  # the author's own code, and any exception it raises
        return Outcome(
            name=one.name,
            passed=False,
            explanation=f"{type(error).__name__}: {error}",
            duration_seconds=time.monotonic() - started,
            traceback=traceback.format_exc(),
            calls=tuple(run.calls),
            cost_usd=sum(call.cost_usd for call in run.calls),
            advisory=one.advisory,
        )
    passed, explanation = _verdict(returned)
    return Outcome(
        name=one.name,
        passed=passed,
        explanation=explanation,
        duration_seconds=time.monotonic() - started,
        calls=tuple(run.calls),
        cost_usd=sum(call.cost_usd for call in run.calls),
        advisory=one.advisory,
    )


def _verdict(returned: Any) -> tuple[bool, str]:
    if returned is None:
        return True, "the check raised nothing"
    if isinstance(returned, Result):
        return returned.passed, returned.explanation
    if returned is True:
        return True, "the check returned True"
    if returned is False:
        return False, "the check returned False"
    return (
        False,
        f"the check returned {type(returned).__name__}, "
        "and a check returns None, a bool or a Result",
    )


def skipped(one: Check, reason: str) -> Outcome:
    """A check that could not be run. A skip fails the run, which is the existing rule."""
    return Outcome(
        name=one.name, passed=False, explanation=reason, skipped=True, skip_reason=reason
    )


# The run directory, and the document.


def collected(run: dict[str, Any]) -> Path | None:
    """The collected run directory of one run entry, or `None` when there is none.

    It is the parent of `tracePath`, which `traces.collect` rewrote to the collected copy on
    both backends, so it is the same directory `verdict.artifacts` names on a failure line
    and `scratch/` and `checks.jsonl` sit beside the three collected names.
    """
    named = run.get("tracePath")
    if not isinstance(named, str) or not named:
        return None
    directory = Path(named).parent
    if not directory.is_dir() or not (directory / TRACE_NAME).is_file():
        return None
    return directory


def build_run(directory: Path, case_dir: Path, index: int, judge_model: str) -> Run:
    """One `Run` over one collected run directory. `scratch/` is created here, once."""
    scratch = directory / SCRATCH_DIR
    scratch.mkdir(parents=True, exist_ok=True)
    message = directory / LAST_MESSAGE_NAME
    return Run(
        workspace=directory / WORKSPACE_NAME,
        last_message=message.read_text(encoding="utf-8") if message.is_file() else "",
        trace=directory / TRACE_NAME,
        case_dir=case_dir,
        run_dir=directory,
        scratch=scratch,
        index=index,
        judge_model=judge_model,
    )


def definition(name: str, advisory: bool = False) -> dict[str, Any]:
    """One check's entry in the case's `graders[]`, so the verdict can join a result to it."""
    kind = ADVISORY_TYPE if advisory else CHECK_TYPE
    return {"name": name, "type": kind, "weight": WEIGHT, "config": {}}


def grader_result(outcome: Outcome) -> dict[str, Any]:
    """One check's entry in the run's `graders[]`, in the shape every grader result has."""
    return GraderResult(
        name=outcome.name,
        passed=outcome.passed,
        weight=WEIGHT,
        explanation=outcome.explanation,
        scored=not outcome.skipped and not outcome.advisory,
        skipped=outcome.skipped,
        skip_reason=outcome.skip_reason if outcome.skipped else None,
    ).model_dump(mode="json", by_alias=True)


def add_spend(entry: dict[str, Any], spent: float, key: str = RUN_SPEND) -> None:
    """Add a check judge's spend to one field of one entry, and nothing when it is 0.

    The two fields it is added to are a run's `judgeCostUsd` and the document's `costUsd`,
    which are what the panel and `eval.max_cost_total_usd` read. A healthy document with no
    judged check is unchanged. docs/checks_layer.md.
    """
    if not spent:
        return
    entry[key] = _number(entry.get(key)) + spent


def score(run: dict[str, Any]) -> float:
    """The weighted fraction of scored grader results that passed. Zero when there are none.

    It is `results.Run.score` over the document rather than over the dataclass, because what
    is scored here is a document the harness may have written.
    """
    scored = [
        result
        for result in run.get("graders") or []
        if isinstance(result, dict) and result.get("scored", True)
    ]
    total = sum(_weight(result) for result in scored)
    if not total:
        return 0.0
    return sum(_weight(result) for result in scored if result.get("passed")) / total


def _weight(result: dict[str, Any]) -> float:
    held = result.get("weight", WEIGHT)
    return float(held) if isinstance(held, int | float) and not isinstance(held, bool) else WEIGHT


# The layer.


def run(output_dir: Path | str, root: Path | str, *, judge_model: str) -> list[str]:
    """Every check of every case of one plugin's result document. Returns the warnings.

    It runs after `traces.collect`, over the collected run directories, and it rewrites the
    document in place: each check result into that run's `graders[]`, each definition into
    the case's, and the run's score, the case's aggregates and the spend recomputed after.

    Every arm a case carries is walked, so a check reads what the baseline produced too and the
    two arms are compared on the same assertions. docs/checks_layer.md.

    A case carrying `declaredUnrunnable` has no run and produces no check result. It is
    counted, exactly as it is today.
    """
    directory = Path(output_dir)
    path = directory / RESULT_NAME
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # The verdict already fails the invocation for a document it cannot read, and a
        # second line saying it again is noise.
        return []
    if not isinstance(document, dict):
        return []

    plugin = Path(root)
    warnings: list[str] = []
    spent = 0.0
    checked = False
    for case in document.get("cases") or []:
        if not isinstance(case, dict):
            continue
        if case.get(DECLARED_UNRUNNABLE):
            # No run, so nothing to check. The case is counted, exactly as it is today.
            continue
        checks = discover(plugin / str(case.get("dir") or ""))
        if not checks:
            continue
        checked = True
        spent += _each_case(case, checks, plugin, judge_model, warnings)
    if not checked:
        # A suite with no check anywhere leaves the document exactly as the backend wrote it.
        return warnings
    add_spend(document, spent, SUITE_SPEND)
    _recount(document)
    try:
        results.write(directory, document)
    except OSError as error:
        return [*warnings, f"{path}: the check results could not be written: {error}"]
    return warnings


def _recount(document: dict[str, Any]) -> None:
    """The suite's means, over the case aggregates the checks just moved.

    `overallScore` is the mean case score and `overallPassRate` the mean case pass rate,
    which is the reference's rule and `results._aggregates`'s. `meanDelta` is the mean of the
    case deltas that are defined. `casesTotal` and `casesPassed` are untouched: `--threshold`
    is pinned to 0, so every case counts as passed there whatever a check said, and this
    package decides pass and fail. docs/checks_layer.md.
    """
    counted = [
        case
        for case in document.get("cases") or []
        if isinstance(case, dict) and not case.get(DECLARED_UNRUNNABLE)
    ]
    if not counted:
        return
    aggregates = document.get("aggregates")
    if not isinstance(aggregates, dict):
        return
    scores = [_number((case.get("aggregates") or {}).get("score")) for case in counted]
    rates = [_number((case.get("aggregates") or {}).get("passRate")) for case in counted]
    aggregates["overallScore"] = sum(scores) / len(counted)
    aggregates["overallPassRate"] = sum(rates) / len(counted)

    if "meanDelta" not in aggregates:
        # The harness writes it only for a two-arm document whose arms are comparable.
        return
    deltas = [(case.get("aggregates") or {}).get("delta") for case in counted]
    defined = [one for one in deltas if isinstance(one, int | float) and not isinstance(one, bool)]
    if defined:
        aggregates["meanDelta"] = sum(defined) / len(defined)


def _each_case(
    case: dict[str, Any],
    checks: tuple[Check, ...],
    plugin: Path,
    judge_model: str,
    warnings: list[str],
) -> float:
    """One case: every run of every arm it carries, then the case's numbers for each arm."""
    case_dir = plugin / str(case.get("dir") or "")
    definitions = case.setdefault("graders", [])
    if isinstance(definitions, list):
        definitions += [definition(one.name, one.advisory) for one in checks]

    spent = 0.0
    arms = case.get("arms") or {}
    walked: dict[str, list[dict[str, Any]]] = {}
    for name in ARMS:
        runs = [entry for entry in arms.get(name) or [] if isinstance(entry, dict)]
        for index, entry in enumerate(runs, start=1):
            spent += _each_run(entry, checks, case_dir, index, judge_model, warnings)
        if runs:
            walked[name] = runs

    aggregates = dict(case.get("aggregates") or {})
    with_runs = walked.get(ARM_WITH)
    without_runs = walked.get(ARM_WITHOUT)
    if with_runs:
        aggregates["score"] = sum(score(entry) for entry in with_runs) / len(with_runs)
        aggregates["passRate"] = sum(1 for entry in with_runs if entry.get("passed")) / len(
            with_runs
        )
    if without_runs:
        # Only where the harness already wrote one. It omits `scoreWithout` and `delta`
        # together when the two arms were graded under different rules, and this layer
        # introduces neither. docs/running_evals.md.
        if "scoreWithout" in aggregates:
            aggregates["scoreWithout"] = sum(score(entry) for entry in without_runs) / len(
                without_runs
            )
        if "passRateWithout" in aggregates:
            aggregates["passRateWithout"] = sum(
                1 for entry in without_runs if entry.get("passed")
            ) / len(without_runs)
    if with_runs and without_runs and "delta" in aggregates and "scoreWithout" in aggregates:
        aggregates["delta"] = aggregates["score"] - aggregates["scoreWithout"]
    if aggregates:
        case["aggregates"] = aggregates
    return spent


def _each_run(
    entry: dict[str, Any],
    checks: tuple[Check, ...],
    case_dir: Path,
    index: int,
    judge_model: str,
    warnings: list[str],
) -> float:
    """One run: every check over it, then that run's score and spend."""
    directory = collected(entry)
    if directory is None:
        outcomes = [skipped(one, NO_ARTEFACTS) for one in checks]
    else:
        outcomes = []
        for one in checks:
            outcomes.append(execute(one, build_run(directory, case_dir, index, judge_model)))
        warnings += _write(directory, outcomes)

    graded = entry.setdefault("graders", [])
    if isinstance(graded, list):
        graded += [grader_result(outcome) for outcome in outcomes]
    entry["score"] = score(entry)
    entry["passed"] = entry["score"] == 1.0

    spent = sum(outcome.cost_usd for outcome in outcomes)
    add_spend(entry, spent)
    return spent


def _write(directory: Path, outcomes: list[Outcome]) -> list[str]:
    """`checks.jsonl` beside the three collected names, one line per check."""
    lines = "".join(json.dumps(outcome.document()) + "\n" for outcome in outcomes)
    try:
        (directory / CHECKS_FILE).write_text(lines, encoding="utf-8")
    except OSError as error:
        return [f"{directory / CHECKS_FILE} could not be written: {error}"]
    return []


def _number(value: Any) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return 0.0
