"""The gate over the result documents one invocation produced.

It reads `<plugin>/aggregate-result.json`, so one gate covers every backend and a sweep is
decided once rather than once per plugin. The conditions are the gate table in
docs/running_evals.md.

Structural graders gate. Judged graders are printed and gate nothing, because a judged grader
over a non-deterministic agent is a flaky gate. A skip gates, so a backend cannot go green by
honouring nothing.

Nothing here writes a file or prints. The caller writes `lines` to `gate.txt` and prints them,
and turns `passed` into an exit code. [cli.py](cli.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cases import JUDGED
from .harness import RESULT_NAME

# The one schema this gate reads. The contract is additive-only, so an unknown field is
# ignored and a different version is a failure.
# docs/claude_code/plugin_eval_reference.md.
SCHEMA_VERSION = 1

# The arm the gate reads. There is no baseline arm on either backend.
# docs/running_evals.md.
ARM = "with"

# The two tags every line carries, so a judged failure is never read as the cause of exit 1.
FAIL = "FAIL"
NOTE = "NOTE"

# How a line names where one run's artefacts are. What is in that directory is
# docs/running_evals.md; the container backend fills it through traces.py.
ARTIFACTS = "artifacts"


@dataclass(frozen=True, slots=True)
class GateResult:
    """The decision, and every line that explains it. The summary line is the last one."""

    passed: bool
    lines: tuple[str, ...]

    @property
    def text(self) -> str:
        return "".join(f"{line}\n" for line in self.lines)


def gate(run_dir: Path | str, *, extra: tuple[str, ...] = ()) -> GateResult:
    """Read every result document one level under the run directory and decide once.

    `extra` is a failure line the caller already holds, which is how a sweep stopped by the
    total cost ceiling reaches the gate without a second code path.
    """
    directory = Path(run_dir)
    failures = [f"{FAIL} {line}" for line in extra]
    notes: list[str] = []
    totals = _Totals()

    for plugin in sorted(child for child in directory.iterdir() if child.is_dir()):
        document, unreadable = _read(plugin / RESULT_NAME)
        if unreadable is not None:
            failures.append(f"{FAIL} {unreadable}")
            continue
        totals.add(document)
        _judge_document(plugin.name, document, failures, notes)

    return GateResult(passed=not failures, lines=(*failures, *notes, totals.summary))


# Reading one document.


def _read(path: Path) -> tuple[dict[str, Any], None] | tuple[dict[str, Any], str]:
    """The document, or the one line that says why it cannot be gated."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return {}, f"{path}: no result document"
    except ValueError as error:
        return {}, f"{path}: unparsable result document: {error}"
    if not isinstance(document, dict):
        return {}, f"{path}: expected a mapping at the top level"
    version = document.get("schemaVersion")
    if version != SCHEMA_VERSION:
        return {}, f"{path}: schemaVersion is {version!r}, and this gate reads {SCHEMA_VERSION}"
    return document, None


def _judge_document(
    plugin: str, document: dict[str, Any], failures: list[str], notes: list[str]
) -> None:
    if document.get("partial"):
        reason = document.get("partialReason")
        failures.append(f"{FAIL} {plugin}: partial results: {reason}")
    for case in document.get("cases") or []:
        _judge_case(plugin, case, failures, notes)


def _judge_case(plugin: str, case: dict[str, Any], failures: list[str], notes: list[str]) -> None:
    where = f"{plugin}/{case.get('name')}"
    if case.get("skipped"):
        failures.append(f"{FAIL} {where}: the case was skipped: {case.get('skipReason')}")
        return
    definitions = {
        definition.get("name"): definition.get("type")
        for definition in case.get("graders") or []
        if isinstance(definition, dict)
    }
    for index, run in enumerate(case.get("arms", {}).get(ARM) or [], start=1):
        _judge_run(f"{where}: run {index}", run, definitions, failures, notes)


def _judge_run(
    where: str,
    run: dict[str, Any],
    definitions: dict[Any, Any],
    failures: list[str],
    notes: list[str],
) -> None:
    """One run of one case. An `error` gates on every backend.

    On CoWork it is a case the driver could not run or collect. On the harness it is a run
    that timed out, hit the turn cap or exited non-zero, each of which is still graded on
    what it produced, so the score alone does not catch it.
    """
    kept = artifacts(run)
    error = run.get("error")
    if error:
        failures.append(f"{FAIL} {where}: {error}{kept}")
    for result in run.get("graders") or []:
        _judge_grader(where, result, definitions, failures, notes, kept)


def _judge_grader(
    where: str,
    result: dict[str, Any],
    definitions: dict[Any, Any],
    failures: list[str],
    notes: list[str],
    kept: str = "",
) -> None:
    """One grader result, joined to its definition by name to learn its class.

    A result carries `name`, `passed` and `scored` and never `type`, so the definition is
    the only route to the class. docs/running_evals.md.

    `kept` is the run's artefact suffix, on every line a person would investigate: a judged
    note needs the transcript as much as a structural failure does. A skip and an undefined
    grader do not carry one, because neither is a verdict about what the model produced.
    """
    name = result.get("name")
    at = f"{where}: {name}"
    if name not in definitions:
        failures.append(f"{FAIL} {at}: no grader of that name is defined in the case")
        return
    if result.get("skipped"):
        failures.append(f"{FAIL} {at}: the grader was skipped: {result.get('skipReason')}")
        return
    if not result.get("scored", True):
        failures.append(f"{FAIL} {at}: not scored, and --ablation none drops no grader")
        return
    if result.get("passed"):
        return
    kind = definitions[name]
    line = f"{at}: the {kind} grader failed: {result.get('explanation')}{kept}"
    if kind in JUDGED:
        notes.append(f"{NOTE} {line}")
    else:
        failures.append(f"{FAIL} {line}")


def artifacts(run: dict[str, Any]) -> str:
    """What one run left on the host, as the suffix a failure line carries.

    `tracePath` is where the trace is, and every other artefact of that run sits beside it,
    so naming its directory names all of them. It is the container backend's collected
    directory once `traces.collect` has rewritten it, and the session's transcript
    directory on CoWork.

    Empty when there is no such directory, which is a run whose trace was not collected and
    a document written before this was built. The gate never names a path that is not there.
    """
    named = run.get("tracePath")
    if not isinstance(named, str) or not named:
        return ""
    directory = Path(named).parent
    if not directory.is_dir():
        return ""
    return f" [{ARTIFACTS}: {_display(directory)}]"


def _display(directory: Path) -> str:
    """The directory as a person types it: relative to the working directory when it is
    under one, and absolute when it is not."""
    try:
        return str(directory.relative_to(Path.cwd()))
    except ValueError:
        return str(directory)


# The summary.


class _Totals:
    """The case counts summed across plugins, and the mean of each document's score.

    A document whose `casesTotal` is 0 is counted and is not a failure. A `--tag` sweep
    matches no case in most plugins, and failing on that would make every filtered sweep
    red. docs/running_evals.md.
    """

    def __init__(self) -> None:
        self.cases = 0
        self.passed = 0
        self.scores: list[float] = []

    def add(self, document: dict[str, Any]) -> None:
        aggregates = document.get("aggregates") or {}
        self.cases += int(aggregates.get("casesTotal") or 0)
        self.passed += int(aggregates.get("casesPassed") or 0)
        self.scores.append(float(aggregates.get("overallScore") or 0.0))

    @property
    def summary(self) -> str:
        mean = sum(self.scores) / len(self.scores) if self.scores else 0.0
        return f"{self.cases} cases, {self.passed} passed, overall score {mean:.2f}"
