"""Pass and fail over the result documents one invocation produced.

It reads `<plugin>/aggregate-result.json`, so one verdict covers every backend and a sweep is
decided once rather than once per plugin. The conditions are the pass and fail table in
docs/running_evals.md.

A failed grader fails the run whatever its class: structural, judged and `check` alike. A
failed advisory check and a with-only indicator that did not fire are printed as notes and
fail nothing. A skip fails the run, so a backend cannot go green by honouring nothing. A case
that declared the backend cannot run it is counted instead, and the summary line says how
many, because that is a fact about the case and not a backend honouring nothing.

A document of two arms is decided on each case's delta as well. What the plugin changed is
the with-arm score minus the without-arm score, the document works it out, and a case below
`eval.delta_threshold` fails. A two-arm case the document says is not comparable fails too:
the invocation asked for a delta and did not get one. Every other condition is unchanged and
reads the with-arm.

It returns what it concluded about each case as well as the lines. That is one conclusion per
case, reached here once, so [panel.py](panel.py) records a word this module decided rather than
deciding a second one over the same document.

Nothing here writes a file or prints. The caller writes `lines` to `verdict.txt` and prints
them, and turns `passed` into an exit code. [cli.py](cli.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from .checks import ADVISORY_TYPE
from .config import ABLATION_WITH_WITHOUT
from .grader import GraderResult
from .harness import RESULT_NAME
from .results import CaseEntry, ResultDocument, RunEntry, WrongSchema

# The two tags every line carries, so a note is never read as the cause of exit 1. A note is a
# failed advisory check or a with-only indicator that did not fire, and nothing else.
FAIL = "FAIL"
NOTE = "NOTE"

# What this module concluded about one case, on the `outcomes` of the verdict. They are the
# three states a case reaches here and nowhere else: it produced no failure line, it produced
# one, or the backend was told it cannot run the case. [panel.py](panel.py) records the word
# rather than deciding one of its own, so no second rule can disagree with this one.
OUTCOME_PASS = "pass"
OUTCOME_FAIL = "fail"
OUTCOME_DECLARED = "declared"

# How a line names where one run's artefacts are. What is in that directory is
# docs/running_evals.md; the container backend fills it through traces.py.
ARTIFACTS = "artifacts"

# What a run carrying each of the two validity fields traces.py writes is told. Both say
# the model never had a tool the case was granted, so the score is not a fact about the
# plugin. docs/running_evals.md.
DENIED_SAYS = "the permission mode refused"
UNOFFERED_SAYS = "the run was never offered"


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    """What one case of one result document came to, and the pair that identifies it.

    `plugin` is the run directory's child name, which is what this module walks, and `dir`
    is the case's own `dir` in that document. The pair is the join key a caller uses to put
    an outcome back beside the case that produced it, because neither alone is unique across
    a sweep. The manifest name of the plugin is in the document and is not always that
    directory name, so it is not repeated here.
    """

    plugin: str
    dir: str
    name: str
    outcome: str


@dataclass(frozen=True, slots=True)
class Verdict:
    """The decision, and every line that explains it. The summary line is the last one."""

    passed: bool
    lines: tuple[str, ...]
    outcomes: tuple[CaseOutcome, ...] = ()

    @property
    def text(self) -> str:
        return "".join(f"{line}\n" for line in self.lines)


def decide(
    run_dir: Path | str,
    *,
    found: int,
    picked: int,
    extra: tuple[str, ...] = (),
    delta_threshold: float = 0,
) -> Verdict:
    """Read every result document one level under the run directory and decide once.

    `extra` is a failure line the caller already holds, which is how a sweep stopped by the
    total cost ceiling reaches the verdict without a second code path.

    `found` and `picked` are the caller's counts over the case tree it read before it ran
    anything: how many cases are there, and how many the filters kept. This module counts the
    other two, and the summary line prints all four. docs/running_evals.md.

    `delta_threshold` is the resolved `eval.delta_threshold`, handed in the way `extra` is.
    Nothing here reads a configuration file, so one invocation resolves every setting once
    and this stays a function of the run directory and its arguments. It binds on a two-arm
    document alone: a one-arm run has no delta and is decided exactly as it was.
    """
    directory = Path(run_dir)
    failures = [f"{FAIL} {line}" for line in extra]
    notes: list[str] = []
    outcomes: list[CaseOutcome] = []
    totals = _Totals(found=found, picked=picked)

    for plugin in sorted(child for child in directory.iterdir() if child.is_dir()):
        document, unreadable = _read(plugin / RESULT_NAME)
        if unreadable is not None:
            failures.append(f"{FAIL} {unreadable}")
            continue
        totals.add(document)
        _judge_document(plugin.name, document, failures, notes, outcomes, totals, delta_threshold)

    return Verdict(
        passed=not failures,
        lines=(*failures, *notes, totals.summary),
        outcomes=tuple(outcomes),
    )


def two_arm(document: ResultDocument) -> bool:
    """Whether the run that wrote this document ran a baseline arm.

    It is the suite's own record of the flag and not a count of the arms a case carries: a
    case of a two-arm run whose baseline arm ran nothing carries one arm and is a failure,
    not a one-arm case. docs/running_evals.md.
    """
    return document.suite.ablation == ABLATION_WITH_WITHOUT


# Reading one document.


def _read(path: Path) -> tuple[ResultDocument, None] | tuple[None, str]:
    """The document, or the one line that says why no verdict can be reached on it.

    The contract is additive-only, so an unknown field is ignored, and a document of another
    `schemaVersion` is reported on its version and never on a field it does not have.
    docs/claude_code/plugin_eval_reference.md.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, f"{path}: no result document"
    try:
        return ResultDocument.model_validate_json(text), None
    except ValidationError as error:
        for detail in error.errors():
            wrong = (detail.get("ctx") or {}).get("error")
            if isinstance(wrong, WrongSchema):
                return None, f"{path}: {wrong}"
        return None, f"{path}: unparsable result document: {error}"


def _judge_document(
    plugin: str,
    document: ResultDocument,
    failures: list[str],
    notes: list[str],
    outcomes: list[CaseOutcome],
    totals: _Totals,
    delta_threshold: float,
) -> None:
    if document.partial:
        reason = document.partial_reason
        failures.append(f"{FAIL} {plugin}: partial results: {reason}")
        totals.stopped(reason)
    arms = two_arm(document)
    totals.arms(document, arms)
    for case in document.cases:
        outcomes.append(_judge_case(plugin, case, failures, notes, totals, arms, delta_threshold))


def _judge_case(
    plugin: str,
    case: CaseEntry,
    failures: list[str],
    notes: list[str],
    totals: _Totals,
    arms: bool = False,
    delta_threshold: float = 0,
) -> CaseOutcome:
    """One case, and whether anything about it failed.

    The pass count is this package's own: a case passed when it produced no failure line.
    `aggregates.casesPassed` is the harness's count under `--threshold 0`, which is every
    case always, so reading it back would print a pass beside a failure line.
    docs/running_evals.md.

    A case the backend declared unrunnable is counted and neither passes nor fails. It is out
    of the backend's own `casesTotal` as well, so it is on the summary line and nowhere else.
    """
    before = len(failures)
    where = f"{plugin}/{case.name}"
    if case.declared_unrunnable:
        totals.declare_one()
        return _outcome(plugin, case, OUTCOME_DECLARED)
    if case.skipped:
        failures.append(f"{FAIL} {where}: the case was skipped: {case.skip_reason}")
        return _outcome(plugin, case, OUTCOME_FAIL)
    definitions = {definition.name: definition.type for definition in case.graders}
    for index, run in enumerate(case.arms.with_, start=1):
        _judge_run(f"{where}: run {index}", run, definitions, failures, notes, arms)
    if arms:
        _judge_delta(where, case, failures, delta_threshold)
    if len(failures) == before:
        totals.pass_one()
        return _outcome(plugin, case, OUTCOME_PASS)
    return _outcome(plugin, case, OUTCOME_FAIL)


def _outcome(plugin: str, case: CaseEntry, outcome: str) -> CaseOutcome:
    """The conclusion above, carrying the pair that identifies the case it is about."""
    return CaseOutcome(plugin=plugin, dir=case.dir, name=case.name, outcome=outcome)


def _judge_delta(where: str, case: CaseEntry, failures: list[str], delta_threshold: float) -> None:
    """What the plugin changed, on one case of a two-arm run.

    The delta is `score - scoreWithout` and the document works it out, so this reads it and
    re-derives nothing. A case below the threshold fails: the suite is green because the
    model answered well on its own, which is the whole reason the arm was asked for.

    A case the document says is not comparable fails as well. A two-arm run that produced no
    delta did not do what the invocation asked, and passing it would be the green-on-nothing
    the arm exists to remove.
    """
    aggregates = case.aggregates
    delta = aggregates.delta
    if delta is None:
        failures.append(f"{FAIL} {where}: {_incomparable(case)}")
        return
    if delta < delta_threshold:
        failures.append(
            f"{FAIL} {where}: the delta is {delta:+.2f}, "
            f"with {_number(aggregates.score)} and without {_number(aggregates.score_without)}, "
            f"and eval.delta_threshold is {delta_threshold}"
        )


def _incomparable(case: CaseEntry) -> str:
    """Why a two-arm case carries no delta. The document tells the two reasons apart.

    A baseline arm that ran nothing is one, and a run graded under different rules from the
    arm it is compared with is the other. The failure is the same either way, so the reason
    is what the line says and nothing else turns on it. docs/running_evals.md.
    """
    if not case.arms.without:
        return "the arms are not comparable: the baseline arm ran nothing"
    for run in [*case.arms.with_, *case.arms.without]:
        if run.skipped_paid_graders:
            return "the arms are not comparable: a run skipped its paid graders at the cost ceiling"
    return "the arms are not comparable, and the document does not say why"


def _number(value: float | None) -> str:
    """One of the two scores a delta line names, or what the document carries instead."""
    if value is None:
        return "no score"
    return f"{value:.2f}"


def _judge_run(
    where: str,
    run: RunEntry,
    definitions: dict[str, str],
    failures: list[str],
    notes: list[str],
    arms: bool = False,
) -> None:
    """One run of one case. An `error` fails on every backend, and so does either validity
    field.

    On CoWork an `error` is a case the driver could not run or collect. On the harness it is a
    run that timed out, hit the turn cap or exited non-zero, each of which is still graded on
    what it produced, so the score alone does not catch it.

    The two validity fields are the container backend's, written by traces.py out of the
    kept trace. A run that never had a tool the case was granted is scored on what the model
    wrote without it, so the score is not a fact about the plugin and the run fails instead.
    Neither field appears on a CoWork run or on a run that kept no trace.
    """
    kept = artifacts(run)
    if run.error:
        failures.append(f"{FAIL} {where}: {run.error}{kept}")
    for what, named in ((DENIED_SAYS, run.denied_tools), (UNOFFERED_SAYS, run.unoffered_tools)):
        if named:
            tools = ", ".join(named)
            failures.append(
                f"{FAIL} {where}: {what} {tools}, so the score is not a fact about the plugin{kept}"
            )
    for result in run.graders:
        _judge_grader(where, result, definitions, failures, notes, kept, arms)


def _judge_grader(
    where: str,
    result: GraderResult,
    definitions: dict[str, str],
    failures: list[str],
    notes: list[str],
    kept: str = "",
    arms: bool = False,
) -> None:
    """One grader result, joined to its definition by name to learn its class.

    A result carries `name`, `passed` and `scored` and never `type`, so the definition is
    the only route to the class. docs/run_pipeline.md.

    `kept` is the run's artefact suffix, on every line a person would investigate: a note
    needs the transcript as much as a failure does. A skip and an undefined
    grader do not carry one, because neither is a verdict about what the model produced.

    `arms` splits the `scored: false` condition. On one arm nothing is dropped from the
    score, so a grader that was not scored was not asked, and that is a skip. On two arms
    the harness drops a with-only grader from the score in both arms on purpose, so it is an
    indicator: it fails nothing, and it is printed when it did not fire. A case whose graders
    are all with-only is the harness's own exception and arrives carrying `scored: true`,
    which this reads rather than re-deriving. docs/running_evals.md.
    """
    name = result.name
    at = f"{where}: {name}"
    if name not in definitions:
        failures.append(f"{FAIL} {at}: no grader of that name is defined in the case")
        return
    if result.skipped:
        failures.append(f"{FAIL} {at}: the grader was skipped: {result.skip_reason}")
        return
    if definitions[name] == ADVISORY_TYPE:
        if not result.passed:
            notes.append(f"{NOTE} {at}: the advisory check failed: {result.explanation}{kept}")
        return
    if not result.scored:
        if not arms:
            failures.append(f"{FAIL} {at}: not scored, and --ablation none drops no grader")
        elif not result.passed:
            notes.append(f"{NOTE} {at}: the with-only indicator did not fire{kept}")
        return
    if result.passed:
        return
    kind = definitions[name]
    failures.append(f"{FAIL} {at}: the {kind} grader failed: {result.explanation}{kept}")


def artifacts(run: RunEntry) -> str:
    """What one run left on the host, as the suffix a failure line carries.

    `tracePath` is where the trace is, and every other artefact of that run sits beside it,
    so naming its directory names all of them: the final message, the workspace, and the
    `scratch/` and `checks.jsonl` a check leaves. `traces._one_run` rewrites the field to the
    collected copy on both backends, so the directory is `traces/<case>/run-N` either way.

    Empty when there is no such directory, which is a run whose trace was not collected and
    a document written before this was built. It never names a path that is not there.
    """
    if not run.trace_path:
        return ""
    directory = Path(run.trace_path).parent
    if not directory.is_dir():
        return ""
    return f" [{ARTIFACTS}: {display(directory)}]"


def display(directory: Path) -> str:
    """The directory as a person types it: relative to the working directory when it is
    under one, and absolute when it is not.

    Public because [panel.py](panel.py) names the same directory in a row.
    """
    try:
        return str(directory.relative_to(Path.cwd()))
    except ValueError:
        return str(directory)


# The summary.


class _Totals:
    """The five counts on the last line, and the mean of each document's score.

    | Count      | Is                                              | Counted by       |
    | ---------- | ----------------------------------------------- | ---------------- |
    | `found`    | The cases under the path, before any filter     | the caller       |
    | `picked`   | The cases `--tag` and `--case` kept             | the caller       |
    | `ran`      | The cases a backend reported running            | `casesTotal`     |
    | `passed`   | The cases that produced no failure line         | this module      |
    | `declared` | The cases a backend was told it cannot run      | this module      |

    A declared case is why `ran` can be below `picked` on a suite where nothing went wrong,
    which is what putting it on the line rather than leaving it absent says.

    Picked and ran are two counts of two things, the second of which is the harness's. They
    differ when a plugin failed to run, when the sweep stopped early, or when the harness
    picked differently. Both are printed and neither is checked against the other.

    A document whose `casesTotal` is 0 is counted and is not a failure. A `--tag` sweep
    matches no case in most plugins, and failing on that would make every filtered sweep
    red. docs/running_evals.md.

    A two-arm run adds the mean delta to the same line, and a one-arm run does not: there is
    no delta on one arm, and a number that is always 0 there would read as a plugin that
    changed nothing.
    """

    def __init__(self, *, found: int, picked: int) -> None:
        self.found = found
        self.picked = picked
        self.ran = 0
        self.passed = 0
        self.declared = 0
        self.scores: list[float] = []
        self.deltas: list[float] = []
        self.two_arm = False
        self.reasons: list[str] = []

    def add(self, document: ResultDocument) -> None:
        self.ran += document.aggregates.cases_total
        self.scores.append(document.aggregates.overall_score)

    def arms(self, document: ResultDocument, two: bool) -> None:
        """What the document says about the baseline arm, and the mean delta it carries.

        `meanDelta` is the document's own mean of the case deltas that are defined, and is
        omitted when none is. A sweep's number is the mean of the documents that carried
        one, exactly as the score is.
        """
        self.two_arm = self.two_arm or two
        mean = document.aggregates.mean_delta
        if mean is not None:
            self.deltas.append(mean)

    def pass_one(self) -> None:
        self.passed += 1

    def declare_one(self) -> None:
        self.declared += 1

    def stopped(self, reason: str | None) -> None:
        """Why a document says the sweep stopped early, once per distinct reason."""
        said = str(reason)
        if said not in self.reasons:
            self.reasons.append(said)

    @property
    def summary(self) -> str:
        mean = sum(self.scores) / len(self.scores) if self.scores else 0.0
        line = (
            f"{self.found} found, {self.picked} picked, {self.ran} ran, "
            f"{self.passed} passed, {self.declared} declared unrunnable, "
            f"overall score {mean:.2f}"
        )
        if self.two_arm:
            line += f", mean delta {self._mean_delta}"
        if self.reasons:
            line += f", stopped early: {'; '.join(self.reasons)}"
        return line

    @property
    def _mean_delta(self) -> str:
        """The mean of the documents that carried one, or that none did.

        A two-arm run every one of whose cases was incomparable carries no delta anywhere,
        and each of those cases has already failed on its own line.
        """
        if not self.deltas:
            return "none"
        return f"{sum(self.deltas) / len(self.deltas):+.2f}"
