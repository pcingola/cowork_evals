"""The v1 `aggregate-result.json` document, read and written as one model.

It is the same document the harness writes, so one verdict covers every backend. The contract is
docs/claude_code/plugin_eval_reference.md: canonical camelCase, `schemaVersion: 1`,
additive-only, and an optional field absent rather than null.

Additive-only is what permits the three fields this backend adds and the one it widens:
`declaredUnrunnable` and `declaredReason` on a case, `skipped` and `skipReason` on a grader
result, `cowork` on a run, and `scored`, which is `not skipped` here rather than
`not withOnly`. Every one of them, and the one behavioural departure in the aggregates, is
recorded in docs/cowork_backend.md. It is also what makes every model here keep a key it does
not know: a document read and written back carries that key unchanged.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_serializer,
    model_serializer,
    model_validator,
)

from .cases import GRADER_CONFIGS, JUDGED, Case, Grader, GraderConfig, plugin_manifest, plugin_name
from .cowork import SessionDocument
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

# The case keys the document records as declared, mapped to the `CaseEntry` field each one
# fills. They are the case's own values and never an override: what actually ran is read from
# `arms.with` and from each run's `cowork` object.
DECLARED_KEYS = {
    "model": "model",
    "runs": "runs_per_case",
    "timeout_seconds": "timeout_seconds",
    "max_turns": "max_turns",
}

# The key a case the backend did not run carries, and this repository's own. It is not
# `skipped`: a skip fails the run, and a case that declared itself unrunnable here is counted
# instead. docs/cowork_backend.md.
DECLARED_UNRUNNABLE = "declaredUnrunnable"


class _Entry(BaseModel):
    """One part of the document, read with its camelCase keys and written back with them.

    An unknown key is kept and written back unchanged. A declared field that is `None` is
    absent from the written entry unless it is named in `_NULLABLE`, and a field named in
    `_ONLY_TRUE` is written only when it is true.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    _NULLABLE: ClassVar[frozenset[str]] = frozenset()
    _ONLY_TRUE: ClassVar[frozenset[str]] = frozenset()

    @model_serializer(mode="wrap")
    def _absent(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        entry = handler(self)
        for name, info in type(self).model_fields.items():
            value = getattr(self, name)
            if (value is None and name not in self._NULLABLE) or (
                name in self._ONLY_TRUE and not value
            ):
                entry.pop(info.alias or name, None)
                entry.pop(name, None)
        return entry


class CoWorkRef(_Entry):
    """A run's `cowork` object. `sessionDir` is what re-grades a stored run without submitting
    again, and `timeoutSeconds` is the timeout that run actually ran under, which is the one
    place an effective value is recorded. `sessionDir` is null when the driver raised before
    a session directory appeared."""

    _NULLABLE: ClassVar[frozenset[str]] = frozenset({"session_dir"})

    session_dir: str | None = Field(default=None, alias="sessionDir")
    timeout_seconds: float = Field(alias="timeoutSeconds")


class RunEntry(_Entry):
    """One submission of one case, already graded: one entry of an arm.

    `error` is written as null when there is none, as the harness writes it. `cowork` is
    absent on a harness run, and its presence is what says a run came from this backend.
    """

    _NULLABLE: ClassVar[frozenset[str]] = frozenset({"error"})

    score: float
    passed: bool
    turns: int
    cost_usd: float = Field(alias="costUsd")
    judge_cost_usd: float = Field(alias="judgeCostUsd")
    error: str | None
    skipped_paid_graders: bool = Field(alias="skippedPaidGraders")
    cowork: CoWorkRef | None = None
    graders: list[GraderResult]
    started_at: str | None = Field(default=None, alias="startedAt")
    duration_seconds: float | None = Field(default=None, alias="durationSeconds")
    trace_path: str | None = Field(default=None, alias="tracePath")
    denied_tools: list[str] | None = Field(default=None, alias="deniedTools")
    unoffered_tools: list[str] | None = Field(default=None, alias="unofferedTools")

    @classmethod
    def graded(
        cls,
        graders: tuple[GraderResult, ...] = (),
        *,
        session_dir: str | None = None,
        timeout_seconds: float = 0.0,
        judge_cost_usd: float = 0.0,
        turns: int = 0,
        started_at: str | None = None,
        duration_seconds: float | None = None,
        trace_path: str | None = None,
        error: str | None = None,
    ) -> RunEntry:
        """One CoWork run, with `score` and `passed` computed from its graders.

        `costUsd` is the judge spend: a CoWork run is billed to the account and is not
        observable from the host. docs/cowork_backend.md.
        """
        score = _score(graders)
        return cls(
            score=score,
            passed=score == 1.0,
            turns=turns,
            cost_usd=judge_cost_usd,
            judge_cost_usd=judge_cost_usd,
            error=error,
            skipped_paid_graders=False,
            cowork=CoWorkRef(session_dir=session_dir, timeout_seconds=timeout_seconds),
            graders=list(graders),
            started_at=started_at,
            duration_seconds=duration_seconds,
            trace_path=trace_path,
        )

    @classmethod
    def collected(
        cls,
        session: SessionDocument,
        graders: tuple[GraderResult, ...],
        *,
        timeout_seconds: float,
        judge_cost_usd: float = 0.0,
        error: str | None = None,
    ) -> RunEntry:
        """One run built from the session document the driver returned.

        Two driver fields can be absent: `submitted_at`, when the audit record carries no
        timestamp, and `transcript`, when the session has no transcript directory. `startedAt`
        and `tracePath` are then absent, and `durationSeconds` is absent rather than computed
        against a missing start.
        """
        started = session.submitted_at
        return cls.graded(
            graders,
            session_dir=session.session_dir,
            timeout_seconds=timeout_seconds,
            judge_cost_usd=judge_cost_usd,
            turns=sum(1 for turn in session.turns if turn.role == "assistant"),
            started_at=started,
            duration_seconds=_elapsed(started, session.collected_at),
            trace_path=session.transcript,
            error=error,
        )


class Arms(_Entry):
    """A case's runs, by arm. `without` is absent unless the run had a baseline arm."""

    with_: list[RunEntry] = Field(alias=ARM_WITH)
    without: list[RunEntry] | None = None


class CaseAggregates(_Entry):
    """A case's mean score and pass rate, and the baseline arm's when there was one."""

    score: float
    pass_rate: float = Field(alias="passRate")
    score_without: float | None = Field(default=None, alias="scoreWithout")
    pass_rate_without: float | None = Field(default=None, alias="passRateWithout")
    delta: float | None = None


class GraderDefinition(_Entry):
    """One entry of a case's `graders[]`: what the grader was asked.

    `config` is the typed config `type` selects, and `None`, written as `{}`, for a type
    with none: `check`, `check-advisory` and a type this package does not know. It is
    written as it was read, so a key the document did not carry is not added on a rewrite.
    `graderMarkdown` is carried by `llm` and `baseline` only.
    """

    _NULLABLE: ClassVar[frozenset[str]] = frozenset({"config"})

    name: str
    type: str
    weight: int | float
    grader_markdown: str | None = Field(default=None, alias="graderMarkdown")
    config: GraderConfig | None = None

    @model_validator(mode="before")
    @classmethod
    def _typed_config(cls, data: Any) -> Any:
        if not isinstance(data, dict) or isinstance(data.get("config"), BaseModel):
            return data
        model = GRADER_CONFIGS.get(str(data.get("type")))
        config = data.get("config") or {}
        return {**data, "config": None if model is None else model.model_validate(config)}

    @field_serializer("config")
    def _config(self, config: GraderConfig | None) -> dict[str, Any]:
        if config is None:
            return {}
        return config.model_dump(mode="json", exclude_unset=True)

    @classmethod
    def build(cls, grader: Grader) -> GraderDefinition:
        """The definition of one grader of a case.

        The typed config carries the defaults the grader applies, so the document says what
        was actually asserted. A judged grader's `criteria` is its body when it wrote none.
        """
        markdown = grader.markdown if grader.type in JUDGED else None
        config = None
        if grader.config is not None:
            written = grader.config.model_dump(exclude_none=True)
            if grader.type in JUDGED and "criteria" not in written:
                written["criteria"] = grader.markdown
            config = type(grader.config).model_validate(written)
        return cls(
            name=grader.name,
            type=grader.type,
            weight=grader.weight,
            grader_markdown=markdown,
            config=config,
        )


class CaseEntry(_Entry):
    """One case: what it asked for, every run of it, and why there were none.

    `declaredUnrunnable` and `skipped` are written only when true. `declared_reason` is what
    the document says; the rule that decides it is `cowork_backend.declared`, and nothing here
    reads it: this module owns the document, and that one owns which case this backend runs.
    """

    _ONLY_TRUE: ClassVar[frozenset[str]] = frozenset({"declared_unrunnable", "skipped"})

    name: str
    dir: str
    source: str
    prompt_markdown: str = Field(alias="promptMarkdown")
    model: str | None = None
    runs_per_case: int | None = Field(default=None, alias="runsPerCase")
    timeout_seconds: float | None = Field(default=None, alias="timeoutSeconds")
    max_turns: int | None = Field(default=None, alias="maxTurns")
    graders: list[GraderDefinition]
    arms: Arms
    aggregates: CaseAggregates
    declared_unrunnable: bool = Field(default=False, alias=DECLARED_UNRUNNABLE)
    declared_reason: str | None = Field(default=None, alias="declaredReason")
    skipped: bool = False
    skip_reason: str | None = Field(default=None, alias="skipReason")

    @classmethod
    def build(
        cls,
        case: Case,
        root: Path,
        runs: tuple[RunEntry, ...] = (),
        *,
        declared_reason: str | None = None,
    ) -> CaseEntry:
        """One case and its runs. A `declared_reason` is a case this backend did not run."""
        frontmatter = case.frontmatter
        declared = {
            field: getattr(frontmatter, key)
            for key, field in DECLARED_KEYS.items()
            if key in frontmatter.model_fields_set
        }
        count = len(runs)
        return cls(
            name=case.name,
            dir=_relative(case.directory, root),
            source=case.source,
            prompt_markdown=case.prompt,
            **declared,
            graders=[GraderDefinition.build(grader) for grader in case.graders],
            arms=Arms(with_=list(runs)),
            # The pass rate is the fraction of runs scoring 1.0. Above `runs: 1` that is the
            # flake rate.
            aggregates=CaseAggregates(
                score=sum(run.score for run in runs) / count if count else 0.0,
                pass_rate=sum(1 for run in runs if run.passed) / count if count else 0.0,
            ),
            declared_unrunnable=declared_reason is not None,
            declared_reason=declared_reason,
        )


class PluginRef(_Entry):
    """One plugin of `suite.plugins`."""

    name: str
    path: str
    version: str | None = None


class SuiteInfo(_Entry):
    """What the suite ran over, and how it was asked to judge."""

    root: str
    ablation: str
    threshold: float
    judge_model: str = Field(alias="judgeModel")
    plugins: list[PluginRef]
    case_filter: str | None = Field(default=None, alias="caseFilter")
    tag_filters: list[str] | None = Field(default=None, alias="tagFilters")


class SuiteAggregates(_Entry):
    """The suite's four numbers, and the mean delta when there was a baseline arm."""

    cases_total: int = Field(alias="casesTotal")
    cases_passed: int = Field(alias="casesPassed")
    overall_score: float = Field(alias="overallScore")
    overall_pass_rate: float = Field(alias="overallPassRate")
    mean_delta: float | None = Field(default=None, alias="meanDelta")


class WrongSchema(ValueError):
    """A document of another `schemaVersion`. It is raised before any field is validated, so a
    reader can report the version rather than a field the other schema does not have."""


class ResultDocument(_Entry):
    """The whole document.

    `schemaVersion` is checked before anything else is validated, so a document of another
    version fails on its version and never on a field it does not have.
    """

    schema_version: int = Field(alias="schemaVersion")
    claude_version: str = Field(alias="claudeVersion")
    started_at: str = Field(alias="startedAt")
    duration_seconds: float = Field(alias="durationSeconds")
    cost_usd: float = Field(alias="costUsd")
    partial: bool = False
    partial_reason: str | None = Field(default=None, alias="partialReason")
    suite: SuiteInfo
    cases: list[CaseEntry]
    aggregates: SuiteAggregates

    @model_validator(mode="before")
    @classmethod
    def _version(cls, data: Any) -> Any:
        if isinstance(data, dict):
            version = data.get("schemaVersion", data.get("schema_version"))
            if version != SCHEMA_VERSION:
                raise WrongSchema(
                    f"schemaVersion is {version!r}, and this module reads {SCHEMA_VERSION}"
                )
        return data

    @classmethod
    def read(cls, path: Path | str) -> ResultDocument:
        """The document at `path`. It raises `OSError`, or `ValueError` for a document that
        is not JSON or does not validate."""
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


def build(
    *,
    root: Path | str,
    cases: list[CaseEntry],
    started_at: str,
    duration_seconds: float,
    judge_model: str,
    claude_version: str | None = None,
    case_filter: str | None = None,
    tag_filters: tuple[str, ...] = (),
) -> ResultDocument:
    """The whole document.

    `costUsd` is the judge spend and nothing else. A CoWork run is billed to the account and
    is not observable from the host, and it is never estimated. `claudeVersion` is the host
    `claude` rather than a CLI that ran the suite, because none did. Both are recorded in
    docs/cowork_backend.md.

    `partial` is always false: this backend never stops a suite part way, and the ceiling
    refusal happens before the first submission.
    """
    plugin_root = Path(root).resolve()
    return ResultDocument(
        schema_version=SCHEMA_VERSION,
        claude_version=claude_version if claude_version is not None else version(),
        started_at=started_at,
        duration_seconds=duration_seconds,
        cost_usd=sum(run.judge_cost_usd for case in cases for run in case.arms.with_),
        partial=False,
        suite=SuiteInfo(
            root=str(plugin_root),
            ablation=ABLATION,
            threshold=THRESHOLD,
            judge_model=judge_model,
            plugins=[_plugin(plugin_root)],
            case_filter=case_filter,
            tag_filters=list(tag_filters) if tag_filters else None,
        ),
        cases=cases,
        aggregates=_aggregates(cases),
    )


def write(output_dir: Path | str, document: ResultDocument) -> Path:
    """The document, under the name every backend writes it under, into a directory the
    caller already created."""
    path = Path(output_dir) / RESULT_NAME
    written = document.model_dump(mode="json", by_alias=True)
    path.write_text(json.dumps(written, indent=2) + "\n", encoding="utf-8")
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
            document = ResultDocument.read(plugin / RESULT_NAME)
        except (OSError, ValueError):
            continue
        total += document.cost_usd
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


def _score(graders: tuple[GraderResult, ...]) -> float:
    """The weighted fraction of scored graders that passed.

    Zero when there were none to score, which is the reference's rule and covers both a
    case whose graders were all skipped and a case with no grader file at all.
    """
    scored = [result for result in graders if not result.skipped]
    total = sum(result.weight for result in scored)
    if not total:
        return 0.0
    return sum(result.weight for result in scored if result.passed) / total


def _aggregates(cases: list[CaseEntry]) -> SuiteAggregates:
    """The suite's four numbers, over the cases this backend ran. A mean over nothing is 0.

    A declared case is out of all four. `casesPassed` is the reference's rule, a case scoring
    at or above `threshold`, and `threshold` is 0 here, so a declared case left in
    `casesTotal` alone would count as passed and its 0.0 would drag `overallScore` down for a
    case that never ran. A suite of nothing but declared cases reports the same four numbers
    as a suite of no cases at all. docs/run_pipeline.md.
    """
    ran = [case for case in cases if not case.declared_unrunnable]
    total = len(ran)
    return SuiteAggregates(
        cases_total=total,
        cases_passed=total,
        overall_score=(sum(case.aggregates.score for case in ran) / total) if total else 0.0,
        overall_pass_rate=(
            (sum(case.aggregates.pass_rate for case in ran) / total) if total else 0.0
        ),
    )


def _plugin(root: Path) -> PluginRef:
    """The plugin under test, from its manifest. `cases.plugin_name` decides the name."""
    return PluginRef(
        name=plugin_name(root), path=str(root), version=plugin_manifest(root).version or None
    )


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
