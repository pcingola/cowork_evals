"""The v1 `aggregate-result.json` document, as this backend writes it.

It is the same document the harness writes, so one verdict covers every backend. The contract is
docs/claude_code/plugin_eval_reference.md: canonical camelCase, `schemaVersion: 1`,
additive-only, and an optional field absent rather than null.

Additive-only is what permits the three fields this backend adds and the one it widens:
`declaredUnrunnable` and `declaredReason` on a case, `skipped` and `skipReason` on a grader
result, `cowork` on a run, and `scored`, which is `not skipped` here rather than
`not withOnly`. Every one of them, and the one behavioural departure in the aggregates, is
recorded in docs/cowork_backend.md.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .cases import JUDGED, Case, Grader, plugin_manifest, plugin_name
from .grader import GraderResult
from .harness import RESULT_NAME

SCHEMA_VERSION = 1

# The document's two arm keys, and the order every reader walks them in. `with` loads the
# plugin under test and is the arm every backend runs; `without` is the baseline arm, which
# only a `--ablation with-without` run on the container backend produces. They are here
# because this module writes the document, and [traces.py](traces.py) and
# [verdict.py](verdict.py) read it. docs/running_evals.md.
ARM_WITH = "with"
ARM_WITHOUT = "without"
ARMS = (ARM_WITH, ARM_WITHOUT)

# Pinned for every suite this backend runs. There is no baseline arm, and this package decides
# pass and fail. docs/running_evals.md.
ABLATION = "none"
THRESHOLD = 0

# What `claude --version` says when it cannot be asked. The `--cowork` preflight is what
# keeps that from happening; a suite that ran anyway says so rather than claiming a version.
UNKNOWN_VERSION = "unknown"

# The case keys the document records as declared, and their camelCase names. They are the
# case's own values and never an override: what actually ran is read from `arms.with` and
# from each run's `cowork` object.
DECLARED_KEYS = {
    "model": "model",
    "runs": "runsPerCase",
    "timeout_seconds": "timeoutSeconds",
    "max_turns": "maxTurns",
}

# The two fields a case the backend did not run carries, and this repository's own. They are
# not `skipped`: a skip fails the run, and a case that declared itself unrunnable here is
# counted instead. docs/cowork_backend.md.
DECLARED_UNRUNNABLE = "declaredUnrunnable"
DECLARED_REASON = "declaredReason"


@dataclass(frozen=True, slots=True)
class Run:
    """One submission of one case, already graded.

    `session_dir` and `timeout_seconds` are the `cowork` object: the first is what re-grades
    a stored run without submitting again, and the second is the timeout that run actually
    ran under, which is the one place an effective value is recorded.
    """

    graders: tuple[GraderResult, ...] = ()
    session_dir: str | None = None
    timeout_seconds: float = 0.0
    judge_cost_usd: float = 0.0
    turns: int = 0
    started_at: str | None = None
    duration_seconds: float | None = None
    trace_path: str | None = None
    error: str | None = None

    @classmethod
    def collected(
        cls,
        session: dict[str, Any],
        graders: tuple[GraderResult, ...],
        *,
        timeout_seconds: float,
        judge_cost_usd: float = 0.0,
        error: str | None = None,
    ) -> Run:
        """One run built from the session document the driver returned.

        Two driver fields can be absent: `submitted_at`, when the audit record carries no
        timestamp, and `transcript`, when the session has no transcript directory. `startedAt`
        and `tracePath` are then absent, and `durationSeconds` is absent rather than computed
        against a missing start.
        """
        started = session.get("submitted_at")
        return cls(
            graders=graders,
            session_dir=session.get("session_dir"),
            timeout_seconds=timeout_seconds,
            judge_cost_usd=judge_cost_usd,
            turns=sum(1 for turn in session.get("turns") or [] if turn.get("role") == "assistant"),
            started_at=started if isinstance(started, str) else None,
            duration_seconds=_elapsed(started, session.get("collected_at")),
            trace_path=session.get("transcript"),
            error=error,
        )

    @property
    def scored(self) -> tuple[GraderResult, ...]:
        return tuple(result for result in self.graders if not result.skipped)

    @property
    def score(self) -> float:
        """The weighted fraction of scored graders that passed.

        Zero when there were none to score, which is the reference's rule and covers both a
        case whose graders were all skipped and a case with no grader file at all.
        """
        total = sum(result.weight for result in self.scored)
        if not total:
            return 0.0
        return sum(result.weight for result in self.scored if result.passed) / total

    @property
    def passed(self) -> bool:
        return self.score == 1.0

    def document(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "score": self.score,
            "passed": self.passed,
            "turns": self.turns,
            "costUsd": self.judge_cost_usd,
            "judgeCostUsd": self.judge_cost_usd,
            "error": self.error,
            "skippedPaidGraders": False,
            "cowork": {"sessionDir": self.session_dir, "timeoutSeconds": self.timeout_seconds},
            "graders": [result.model_dump(mode="json", by_alias=True) for result in self.graders],
        }
        if self.started_at is not None:
            entry["startedAt"] = self.started_at
        if self.duration_seconds is not None:
            entry["durationSeconds"] = self.duration_seconds
        if self.trace_path is not None:
            entry["tracePath"] = self.trace_path
        return entry


@dataclass(frozen=True, slots=True)
class CaseResult:
    """One case: what it asked for, every run of it, and why there were none.

    `declared` and `declared_reason` are what the document says. The rule that decides them
    is `cowork_backend.declared`, and nothing here reads it: this module owns the document,
    and that one owns which case this backend runs.
    """

    case: Case
    runs: tuple[Run, ...] = ()
    declared: bool = False
    declared_reason: str | None = None

    @property
    def score(self) -> float:
        if not self.runs:
            return 0.0
        return sum(run.score for run in self.runs) / len(self.runs)

    @property
    def pass_rate(self) -> float:
        """The fraction of runs scoring 1.0. Above `runs: 1` that is the flake rate."""
        if not self.runs:
            return 0.0
        return sum(1 for run in self.runs if run.passed) / len(self.runs)

    def document(self, root: Path) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "name": self.case.name,
            "dir": _relative(self.case.directory, root),
            "source": self.case.source,
            "promptMarkdown": self.case.prompt,
        }
        declared = self.case.frontmatter
        for key, camel in DECLARED_KEYS.items():
            if key in declared.model_fields_set:
                entry[camel] = getattr(declared, key)
        entry["graders"] = [_grader_definition(grader) for grader in self.case.graders]
        entry["arms"] = {ARM_WITH: [run.document() for run in self.runs]}
        entry["aggregates"] = {"score": self.score, "passRate": self.pass_rate}
        if self.declared:
            entry[DECLARED_UNRUNNABLE] = True
            entry[DECLARED_REASON] = self.declared_reason
        return entry


def build(
    *,
    root: Path | str,
    cases: list[CaseResult],
    started_at: str,
    duration_seconds: float,
    judge_model: str,
    claude_version: str | None = None,
    case_filter: str | None = None,
    tag_filters: tuple[str, ...] = (),
) -> dict[str, Any]:
    """The whole document.

    `costUsd` is the judge spend and nothing else. A CoWork run is billed to the account and
    is not observable from the host, and it is never estimated. `claudeVersion` is the host
    `claude` rather than a CLI that ran the suite, because none did. Both are recorded in
    docs/cowork_backend.md.

    `partial` is always false: this backend never stops a suite part way, and the ceiling
    refusal happens before the first submission.
    """
    plugin_root = Path(root).resolve()
    suite: dict[str, Any] = {
        "root": str(plugin_root),
        "ablation": ABLATION,
        "threshold": THRESHOLD,
        "judgeModel": judge_model,
        "plugins": [_plugin(plugin_root)],
    }
    if case_filter is not None:
        suite["caseFilter"] = case_filter
    if tag_filters:
        suite["tagFilters"] = list(tag_filters)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "claudeVersion": claude_version if claude_version is not None else version(),
        "startedAt": started_at,
        "durationSeconds": duration_seconds,
        "costUsd": sum(run.judge_cost_usd for case in cases for run in case.runs),
        "partial": False,
        "suite": suite,
        "cases": [case.document(plugin_root) for case in cases],
        "aggregates": _aggregates(cases),
    }


def write(output_dir: Path | str, document: dict[str, Any]) -> Path:
    """The document, under the name every backend writes it under, into a directory the
    caller already created."""
    path = Path(output_dir) / RESULT_NAME
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def spend(run_dir: Path | str) -> float:
    """`costUsd` summed over every result document one level under a run directory.

    It is what a sweep compares against `eval.max_cost_total_usd` before each plugin. A
    document that is missing or unreadable contributes nothing: the verdict is what reports
    it, and a sweep never stops early because it could not read one.
    """
    total = 0.0
    for plugin in sorted(Path(run_dir).iterdir()):
        try:
            document = json.loads((plugin / RESULT_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(document, dict) and isinstance(document.get("costUsd"), int | float):
            total += float(document["costUsd"])
    return total


def version() -> str:
    """The host `claude --version`, as its first token."""
    try:
        completed = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, check=False
        )
    except OSError:
        return UNKNOWN_VERSION
    if completed.returncode != 0 or not completed.stdout.strip():
        return UNKNOWN_VERSION
    return completed.stdout.split()[0]


# What the document is made of.


def _aggregates(cases: list[CaseResult]) -> dict[str, Any]:
    """The suite's four numbers, over the cases this backend ran. A mean over nothing is 0.

    A declared case is out of all four. `casesPassed` is the reference's rule, a case scoring
    at or above `threshold`, and `threshold` is 0 here, so a declared case left in
    `casesTotal` alone would count as passed and its 0.0 would drag `overallScore` down for a
    case that never ran. A suite of nothing but declared cases reports the same four numbers
    as a suite of no cases at all. docs/run_pipeline.md.
    """
    ran = [case for case in cases if not case.declared]
    total = len(ran)
    return {
        "casesTotal": total,
        "casesPassed": total,
        "overallScore": (sum(case.score for case in ran) / total) if total else 0.0,
        "overallPassRate": (sum(case.pass_rate for case in ran) / total) if total else 0.0,
    }


def _grader_definition(grader: Grader) -> dict[str, Any]:
    definition: dict[str, Any] = {
        "name": grader.name,
        "type": grader.type,
        "weight": grader.weight,
    }
    if grader.type in JUDGED:
        definition["graderMarkdown"] = grader.markdown
    # The typed config carries the defaults the grader applies, so the document says what was
    # actually asserted. A grader with no config writes an empty mapping.
    config = (
        {} if grader.config is None else grader.config.model_dump(mode="json", exclude_none=True)
    )
    if grader.type in JUDGED and "criteria" not in config:
        config["criteria"] = grader.markdown
    definition["config"] = config
    return definition


def _plugin(root: Path) -> dict[str, Any]:
    """The plugin under test, from its manifest. `cases.plugin_name` decides the name."""
    entry: dict[str, Any] = {"name": plugin_name(root), "path": str(root)}
    version = plugin_manifest(root).version
    if version:
        entry["version"] = version
    return entry


def _relative(directory: Path, root: Path) -> str:
    resolved = Path(directory).resolve()
    if resolved.is_relative_to(root):
        return resolved.relative_to(root).as_posix()
    return str(resolved)


def _elapsed(start: Any, end: Any) -> float | None:
    if not isinstance(start, str) or not isinstance(end, str):
        return None
    try:
        return (moment(end) - moment(start)).total_seconds()
    except ValueError:
        return None


def moment(value: str) -> datetime:
    """`datetime.fromisoformat`, with the `Z` suffix the harness writes.

    The harness stamps `...T10:00:00.000Z`. `fromisoformat` accepts `Z` from Python 3.11,
    and this package runs on 3.10, so the suffix is rewritten here. It is public because
    [panel.py](panel.py) reads a document's `startedAt` back and needs the same rewrite.
    """
    return datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
