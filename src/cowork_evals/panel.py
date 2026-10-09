"""The history of what each case did, and the panel rendered over it.

The store is one file per case under the history root, one JSON object per line, appended once
per invocation that ran the case. The render joins those lines to the case tree on disk and
prints one row per case: the latest outcome on each backend, how old it is, what it scored, how
long it took, how often it flakes, whether the case files have changed since, and where the
artefacts of that result are.

This module is the only thing that writes or deletes a path under the history root, which
mirrors [logs.py](logs.py) over the run tree. The rule between the two is the rule between the
two trees: what one invocation produced lives in that invocation's run directory and is deleted
with it, and what outlives that deletion lives here.

Nothing here decides pass or fail. `outcome` is the word [verdict.py](verdict.py) reached on
the same document, carried across unchanged. Nothing here prints either: the three renders
return strings and [cli.py](cli.py) writes them. docs/panel.md, docs/case_history.md.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .cases import (
    CASE_YAML,
    EVAL_DIR,
    GRADERS_DIR,
    PROMPT_FILE,
    Case,
    CaseError,
    check_files,
    plugin_name,
)
from .harness import RESULT_NAME
from .logs import distribution_version, slug
from .preflight import BACKENDS, COWORK
from .results import ARM_WITH, moment
from .traces import DENIED, UNOFFERED
from .verdict import OUTCOME_DECLARED, OUTCOME_PASS, CaseOutcome, display

# The record schema. It is this module's own and is not the result document's: the contract is
# additive-only in the same way, so a reader ignores a field it does not know and a line of
# another version is not read. docs/case_history.md.
SCHEMA_VERSION = 1

# One case's file, under the history root.
SUFFIX = ".jsonl"

# What a backend with no record for a case reads as. It is the first question the panel
# answers, so it is a value in the column and never an empty cell.
NEVER = "never run"

# What a cell with no number reads as, so a column is never blank.
NONE = "-"

# What a row whose case is no longer in the tree reads as, in place of its description.
REMOVED = "removed"

# What the artefacts column adds when the directory the record named is not there. The run
# directory it was in is pruned on a retention the operator sets, and the record outlives it.
GONE = "gone"

# The column headings, in order. The two backend columns sit between the case and the
# numbers, so a row reads left to right as: what the case is, what each backend last said,
# and what that says about the case. docs/panel.md.
COLUMNS = (
    "plugin",
    "skill",
    "case",
    "description",
    *BACKENDS,
    "score",
    "duration",
    "flake",
    "stale",
    "artefacts",
)

# How much of a description the text table carries. A description is a sentence, and a table
# that carried every one of them whole would not fit a terminal. `markdown` and `snapshot`
# carry it whole.
DESCRIPTION_WIDTH = 40


@dataclass(frozen=True, slots=True)
class Cell:
    """One backend's latest record for one case: what it said, and how long ago.

    `age_days` is absent when there is no record, and on a case whose `no-cowork` tag makes
    the CoWork column `declared` without one.
    """

    outcome: str
    age_days: int | None = None


@dataclass(frozen=True, slots=True)
class Row:
    """One case, as every render prints it.

    `cells` carries one entry per backend, always both, so a column is never missing. The five
    values after it come from the row's latest record, whichever backend produced it: the
    panel answers what is known about this case now, and that is the most recent measurement
    of it. `flake` is over that same backend's records for this case, and `records` is how many
    they are.
    """

    plugin: str
    skill: str
    case: str
    description: str
    dir: str
    cells: dict[str, Cell] = field(default_factory=dict)
    score: float | None = None
    duration_seconds: float | None = None
    flake: float | None = None
    records: int = 0
    stale: bool = False
    artefacts: str | None = None
    gone: bool = False
    removed: bool = False


# The store.


def path(root: Path | str, plugin: str, case_dir: str) -> Path:
    """The file one case's records live in.

    `case_dir` is the case's `dir` as a record and a result document carry it, relative to the
    plugin root, and the leading `evals/` is dropped. Every component goes through
    `logs.slug`, so a plugin whose manifest names it `acme/mail` is one directory and not two.

    The result is `<root>/<plugin>/<skill>/<case>.jsonl` for the ordinary tree. A case
    directly under `evals/` has no skill and is `<root>/<plugin>/<case>.jsonl`, which cannot
    collide with the first: the one is a file beside a directory of the same stem. A case
    nested deeper carries every component, so two cases sharing a directory name stay apart.
    """
    parts = [part for part in Path(case_dir).parts if part not in ("/", ".")]
    if parts and parts[0] == EVAL_DIR:
        parts = parts[1:]
    if not parts:
        raise ValueError(f"{case_dir!r} names no case directory")
    components = [slug(part) for part in parts]
    return Path(root).joinpath(slug(plugin), *components[:-1], f"{components[-1]}{SUFFIX}")


def append(root: Path | str, records: Sequence[dict[str, Any]]) -> list[Path]:
    """Write each record to the file its case owns, and return the files written.

    Records are grouped by file first, so one file is opened once however many of them it
    takes. Each file is opened `"a"` under an exclusive `flock` and every line it takes is
    written in one call, so a concurrent reader sees whole lines and two invocations that ran
    the same case do not interleave one.
    """
    written: dict[Path, list[str]] = {}
    for record in records:
        file = path(root, str(record["plugin"]), str(record["dir"]))
        written.setdefault(file, []).append(json.dumps(record, sort_keys=True))
    for file, lines in sorted(written.items()):
        file.parent.mkdir(parents=True, exist_ok=True)
        with file.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.write("".join(f"{line}\n" for line in lines))
    return sorted(written)


def read(file: Path | str) -> tuple[list[dict[str, Any]], list[str]]:
    """Every record in one file, oldest first, and one line per record that did not parse.

    Appending is the only write, so file order is the order the records were made in and the
    last record of a backend is that backend's newest.

    A line that does not parse is reported and skipped rather than raising. A record is one
    line, so a truncated last line loses one measurement, and refusing the file for it would
    lose every other measurement of that case.
    """
    file = Path(file)
    try:
        text = file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], []
    except OSError as error:
        return [], [f"{file}: unreadable: {error}"]

    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError as error:
            warnings.append(f"{file}: line {number}: unparsable record: {error}")
            continue
        if not isinstance(record, dict):
            warnings.append(f"{file}: line {number}: expected an object")
            continue
        if record.get("schemaVersion") != SCHEMA_VERSION:
            warnings.append(
                f"{file}: line {number}: schemaVersion is "
                f"{record.get('schemaVersion')!r}, and this module reads {SCHEMA_VERSION}"
            )
            continue
        records.append(record)
    return records, warnings


def digest(case_dir: Path | str) -> str:
    """`sha256` over the files that define one case, as bytes.

    That is `prompt.md`, `case.yaml` when the case has one, each `graders/*.md` in path order
    and then each `checks/*.py`, which is every file that decides what the case asks and how
    it is graded. Nothing else in the case directory counts: a note beside the graders changes
    no measurement.

    A check file counts because editing an assertion would otherwise leave the `stale` column
    green, and the panel would claim a result is current when what it asserted has changed.

    Bytes, so a whitespace edit moves the digest. Each file's name is hashed before its
    content, so a renamed grader moves it too and two files cannot run together into one.
    """
    directory = Path(case_dir)
    running = hashlib.sha256()
    for file in _defining(directory):
        running.update(file.relative_to(directory).as_posix().encode("utf-8"))
        running.update(b"\0")
        running.update(file.read_bytes())
        running.update(b"\0")
    return running.hexdigest()


def _defining(directory: Path) -> list[Path]:
    """The files `digest` covers, in the order it hashes them."""
    files = [directory / PROMPT_FILE, directory / CASE_YAML]
    graders = directory / GRADERS_DIR
    if graders.is_dir():
        files += sorted(graders.glob("*.md"))
    files += check_files(directory)
    return [file for file in files if file.is_file()]


# One invocation's records.


def records(
    run_dir: Path | str,
    outcomes: Sequence[CaseOutcome],
    backend: str,
    image: str | None = None,
    roots: Mapping[str, Path] | None = None,
) -> list[dict[str, Any]]:
    """One record per case of one invocation, from the documents that invocation wrote.

    It re-reads each `<plugin>/aggregate-result.json` rather than taking the documents from
    the verdict, so the verdict keeps its narrow return and nothing is duplicated but the
    walk. It applies no pass or fail rule: `outcome` is what `verdict.decide` decided, joined
    back by the pair that identifies a case, the run directory's child name and the case's
    `dir`.

    `roots` maps a run directory's child name to the plugin root on this host, and it is
    where the case files a digest covers are read from. The document's own `suite.root` is
    not: on the container backend it is the path the plugin was mounted at inside the
    container, `/work/plugin`, which is nothing on the host. A child the caller named no
    root for keeps the document's, which is the CoWork backend's own host path.

    A document that is missing or unreadable produces nothing. The verdict has already failed
    the invocation for it, and a record of a case whose document could not be read would say
    less than no record at all.
    """
    directory = Path(run_dir)
    decided = {(one.plugin, one.dir): one.outcome for one in outcomes}
    built: list[dict[str, Any]] = []
    for child in sorted(item for item in directory.iterdir() if item.is_dir()):
        document = _document(child / RESULT_NAME)
        if document is None:
            continue
        suite = document.get("suite") or {}
        plugins = suite.get("plugins") or [{}]
        root = Path((roots or {}).get(child.name) or str(suite.get("root") or child))
        for case in document.get("cases") or []:
            outcome = decided.get((child.name, str(case.get("dir") or "")))
            if outcome is None:
                continue
            built.append(
                _record(
                    case,
                    outcome=outcome,
                    document=document,
                    plugin=plugins[0] if isinstance(plugins[0], dict) else {},
                    fallback=child.name,
                    root=root,
                    invocation=directory.name,
                    backend=backend,
                    image=image,
                )
            )
    return built


def _document(file: Path) -> dict[str, Any] | None:
    try:
        document = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def _record(
    case: dict[str, Any],
    *,
    outcome: str,
    document: dict[str, Any],
    plugin: dict[str, Any],
    fallback: str,
    root: Path,
    invocation: str,
    backend: str,
    image: str | None,
) -> dict[str, Any]:
    """One case's record. An optional field is absent, never null. docs/panel.md.

    The plugin is the manifest name the document carries, which is not always the run
    directory's child name: two plugins of one manifest name get two run directories and
    share one history directory, because a history path has to be stable across invocations.
    """
    where = str(case.get("dir") or "")
    runs = [run for run in (case.get("arms") or {}).get(ARM_WITH) or [] if isinstance(run, dict)]
    aggregates = case.get("aggregates") or {}

    record: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "invocation": invocation,
        "backend": backend,
        "coworkEvals": distribution_version(),
        "plugin": str(plugin.get("name") or fallback),
        "case": str(case.get("name") or ""),
        "dir": where,
        "outcome": outcome,
        "score": _number(aggregates.get("score")),
        "passRate": _number(aggregates.get("passRate")),
        "runs": len(runs),
        "durationSeconds": sum(_number(run.get("durationSeconds")) or 0.0 for run in runs),
        "costUsd": sum(_number(run.get("judgeCostUsd")) or 0.0 for run in runs),
    }
    # Absent rather than the digest of nothing. A directory holding no file that defines a
    # case is not the case's directory, and a digest over it would read as a real one and
    # then differ from the tree at render time, which is a row that says `stale` about files
    # nobody edited.
    _put(record, "caseDigest", _case_digest(root / where))
    _put(record, "startedAt", document.get("startedAt"))
    _put(record, "claudeVersion", document.get("claudeVersion"))
    _put(record, "image", image)
    _put(record, "pluginVersion", plugin.get("version"))
    _put(record, "skill", _skill(where))
    _put(record, "delta", _number(aggregates.get("delta")))
    _put(record, "failedGraders", _failed(runs))
    _put(record, "error", next((run.get("error") for run in runs if run.get("error")), None))
    _put(record, DENIED, _union(runs, DENIED))
    _put(record, UNOFFERED, _union(runs, UNOFFERED))
    _put(record, "tracePath", _trace(runs))
    return record


def _case_digest(case_dir: Path) -> str | None:
    """The digest of a case directory, or `None` when that directory defines no case."""
    try:
        if not _defining(case_dir):
            return None
        return digest(case_dir)
    except OSError:
        return None


def _put(record: dict[str, Any], key: str, value: Any) -> None:
    """Write a field only when there is one. An optional field is absent, never null."""
    if value not in (None, "", [], ()):
        record[key] = value


def _skill(where: str) -> str | None:
    """The `<skill>` directory the case sits under, or `None` for a case outside one.

    It is `validate._skill_of`'s rule over the same path: the first component under `evals/`
    when there is more than one, and no skill otherwise.
    """
    parts = Path(where).parts
    if parts and parts[0] == EVAL_DIR:
        parts = parts[1:]
    return parts[0] if len(parts) > 1 else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _failed(runs: list[dict[str, Any]]) -> list[str]:
    """Every scored grader that did not pass, over the runs, each named once.

    Scored alone: a grader the harness dropped from the score decided nothing, and a skipped
    one failed the run on its own line rather than on its result.
    """
    names: list[str] = []
    for run in runs:
        for result in run.get("graders") or []:
            if not isinstance(result, dict) or not result.get("scored", True):
                continue
            name = result.get("name")
            if not result.get("passed") and isinstance(name, str) and name not in names:
                names.append(name)
    return names


def _union(runs: list[dict[str, Any]], field_name: str) -> list[str]:
    """One validity field over the runs, each tool named once. traces.py writes both."""
    tools: list[str] = []
    for run in runs:
        for tool in run.get(field_name) or []:
            if str(tool) not in tools:
                tools.append(str(tool))
    return tools


def _trace(runs: list[dict[str, Any]]) -> str | None:
    """Where to look first: the first failing run's trace, and the first run's when none
    failed. A person reading a red row wants the run that went wrong."""
    for run in runs:
        if not run.get("passed") or run.get("error"):
            named = run.get("tracePath")
            if isinstance(named, str) and named:
                return named
    for run in runs:
        named = run.get("tracePath")
        if isinstance(named, str) and named:
            return named
    return None


# The join.


def rows(
    root: Path | str,
    discovered: Sequence[tuple[Path, Sequence[Case]]],
    *,
    removed: bool = False,
) -> tuple[list[Row], list[str]]:
    """One row per case, joined to its newest record per backend, and what did not parse.

    `discovered` is one `(plugin root, cases)` pair per plugin the path selected, which is
    what `cases.discover` returns under the same path the run would have used. The
    definitions come from the tree at render time and are never read back out of a record:
    a second copy of what a case is would drift from the case.

    `removed` adds a row for every history file of a selected plugin whose case is no longer
    in the tree. Those rows are built from the record itself, which is why a record repeats
    the plugin, skill and case its path already says.
    """
    built: list[Row] = []
    warnings: list[str] = []
    for plugin_root, cases in discovered:
        name = plugin_name(plugin_root)
        seen: set[Path] = set()
        for case in cases:
            where = _relative(case.directory, plugin_root)
            file = path(root, name, where)
            seen.add(file)
            found, unparsable = read(file)
            warnings += unparsable
            built.append(_row(name, where, case, found, warnings))
        if removed:
            for file in _retired(root, name, plugin_root, seen):
                found, unparsable = read(file)
                warnings += unparsable
                if found:
                    built.append(_removed_row(found, warnings))
    return built, warnings


def _relative(directory: Path, plugin_root: Path) -> str:
    """The case's `dir`: its directory relative to the plugin root, as the document writes
    it. A case outside the root keeps its absolute path, which no `path` component can be."""
    resolved = Path(directory).resolve()
    root = Path(plugin_root).resolve()
    if resolved.is_relative_to(root):
        return resolved.relative_to(root).as_posix()
    return resolved.as_posix()


def _retired(root: Path | str, plugin: str, plugin_root: Path, seen: set[Path]) -> list[Path]:
    """Every history file of one plugin whose case is not in the tree.

    A file is retired when the directory its newest record names holds no `prompt.md`, not
    when the path argument did not select it: a case that is still there and was not asked
    for is not a case that was removed.
    """
    directory = Path(root) / slug(plugin)
    if not directory.is_dir():
        return []
    retired = []
    for file in sorted(directory.rglob(f"*{SUFFIX}")):
        if file in seen:
            continue
        found, _ = read(file)
        if not found:
            continue
        case_dir = Path(plugin_root) / str(found[-1].get("dir") or "")
        if not (case_dir / PROMPT_FILE).is_file():
            retired.append(file)
    return retired


def _row(
    plugin: str, where: str, case: Case, found: list[dict[str, Any]], warnings: list[str]
) -> Row:
    """One case of the tree, with what each backend last said about it."""
    latest = {backend: _newest(found, backend) for backend in BACKENDS}
    cells = {backend: _cell(backend, latest[backend], case) for backend in BACKENDS}
    record = _most_recent(latest.values())
    backend = str(record.get("backend")) if record else ""
    try:
        description = case.frontmatter.description or ""
    except CaseError as error:
        warnings.append(str(error))
        description = ""
    return Row(
        plugin=plugin,
        skill=_skill(where) or "",
        case=case.name,
        description=description,
        dir=where,
        cells=cells,
        score=_number((record or {}).get("score")),
        duration_seconds=_number((record or {}).get("durationSeconds")),
        flake=_flake(found, backend),
        records=sum(1 for one in found if one.get("backend") == backend),
        stale=_stale(case.directory, record, warnings),
        artefacts=_artefacts(record),
        gone=_gone(record),
    )


def _removed_row(found: list[dict[str, Any]], warnings: list[str]) -> Row:
    """One row for a case that is no longer in the tree, built from its own records.

    Nothing is read from the tree, so the description is the marker and the row is never
    stale: there are no files to compare the digest against.
    """
    latest = {backend: _newest(found, backend) for backend in BACKENDS}
    cells = {backend: _cell(backend, latest[backend], None) for backend in BACKENDS}
    record = _most_recent(latest.values()) or {}
    backend = str(record.get("backend") or "")
    return Row(
        plugin=str(record.get("plugin") or ""),
        skill=str(record.get("skill") or ""),
        case=str(record.get("case") or ""),
        description=REMOVED,
        dir=str(record.get("dir") or ""),
        cells=cells,
        score=_number(record.get("score")),
        duration_seconds=_number(record.get("durationSeconds")),
        flake=_flake(found, backend),
        records=sum(1 for one in found if one.get("backend") == backend),
        artefacts=_artefacts(record),
        gone=_gone(record),
        removed=True,
    )


def _newest(found: list[dict[str, Any]], backend: str) -> dict[str, Any] | None:
    """That backend's last record in the file, which is its newest: appending is the only
    write, so file order is the order the records were made in."""
    for record in reversed(found):
        if record.get("backend") == backend:
            return record
    return None


def _most_recent(latest: Iterable[dict[str, Any] | None]) -> dict[str, Any] | None:
    """The newest of the per-backend newest, by the stamp each carries.

    It is what the row's numbers come from: the panel answers what is known about the case
    now, and that is the most recent measurement of it whichever backend made it.
    """
    records = [record for record in latest if record]
    if not records:
        return None
    return max(records, key=lambda record: (_when(record) or datetime.min).timestamp())


def _cell(backend: str, record: dict[str, Any] | None, case: Case | None) -> Cell:
    """One backend's column for one case.

    A case carrying `no-cowork` reads `declared` in the CoWork column whether or not it has
    ever been submitted there. The tag is in the tree and is the reason no record will ever
    appear on that backend, so `never run` there would report a gap that is a decision.
    """
    if case is not None and case.no_cowork and backend == COWORK:
        return Cell(outcome=OUTCOME_DECLARED, age_days=_age(record))
    if record is None:
        return Cell(outcome=NEVER)
    return Cell(outcome=str(record.get("outcome") or ""), age_days=_age(record))


def _age(record: dict[str, Any] | None) -> int | None:
    """How many days ago the record was made, from its own stamp."""
    when = _when(record)
    if when is None:
        return None
    now = datetime.now(when.tzinfo) if when.tzinfo is not None else datetime.now()
    return max((now - when).days, 0)


def _when(record: dict[str, Any] | None) -> datetime | None:
    started = (record or {}).get("startedAt")
    if not isinstance(started, str) or not started:
        return None
    try:
        return moment(started)
    except ValueError:
        return None


def _flake(found: list[dict[str, Any]], backend: str) -> float | None:
    """How often that backend's records of this case passed.

    A declared record is out of it: the backend was told it could not run the case, and a
    case that never ran did not flake. None when there is nothing to count.
    """
    ran = [
        record
        for record in found
        if record.get("backend") == backend and record.get("outcome") != OUTCOME_DECLARED
    ]
    if not ran:
        return None
    return sum(1 for record in ran if record.get("outcome") == OUTCOME_PASS) / len(ran)


def _stale(directory: Path, record: dict[str, Any] | None, warnings: list[str]) -> bool:
    """Whether the case files have changed since the record was made.

    The digest is recomputed from the tree and compared with the one the record carries. A
    row that is stale is green over files that are not the files there now.
    """
    if not record or not record.get("caseDigest"):
        return False
    try:
        return digest(directory) != record["caseDigest"]
    except OSError as error:
        warnings.append(f"{directory}: unreadable case: {error}")
        return False


def _artefacts(record: dict[str, Any] | None) -> str | None:
    """The directory the record's trace is in, named the way a failure line names it."""
    named = (record or {}).get("tracePath")
    if not isinstance(named, str) or not named:
        return None
    return display(Path(named).parent)


def _gone(record: dict[str, Any] | None) -> bool:
    named = (record or {}).get("tracePath")
    if not isinstance(named, str) or not named:
        return False
    return not Path(named).parent.is_dir()


# The renders.


def table(built: Sequence[Row]) -> str:
    """The text table: one header line, then one line per row, columns padded to fit.

    The description is cut to `DESCRIPTION_WIDTH` here and nowhere else, because a terminal
    is the one render with a width to fit.
    """
    lines = [[*COLUMNS]] + [_cells(row, width=DESCRIPTION_WIDTH) for row in built]
    widths = [max(len(line[index]) for line in lines) for index in range(len(COLUMNS))]
    return "".join(
        "  ".join(value.ljust(width) for value, width in zip(line, widths, strict=True)).rstrip()
        + "\n"
        for line in lines
    )


def markdown(built: Sequence[Row]) -> str:
    """The same columns as a Markdown table, with every description whole."""
    lines = [list(COLUMNS), ["---"] * len(COLUMNS)]
    lines += [_cells(row) for row in built]
    return "".join(f"| {' | '.join(line)} |\n" for line in lines)


def snapshot(built: Sequence[Row]) -> str:
    """The same rows as JSON, one entry each, every value as the row holds it.

    It is the render a script reads, so nothing is cut, padded or formatted: a number is a
    number and an absent one is absent.
    """
    document = {
        "schemaVersion": SCHEMA_VERSION,
        "rows": [_entry(row) for row in built],
    }
    return json.dumps(document, indent=2) + "\n"


def _entry(row: Row) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "plugin": row.plugin,
        "skill": row.skill,
        "case": row.case,
        "description": row.description,
        "dir": row.dir,
        "backends": {
            backend: _backend_entry(row.cells[backend])
            for backend in BACKENDS
            if backend in row.cells
        },
        "records": row.records,
        "stale": row.stale,
        "removed": row.removed,
    }
    _put(entry, "score", row.score)
    _put(entry, "durationSeconds", row.duration_seconds)
    _put(entry, "flake", row.flake)
    if row.artefacts is not None:
        entry["artefacts"] = row.artefacts
        entry["artefactsGone"] = row.gone
    return entry


def _backend_entry(cell: Cell) -> dict[str, Any]:
    entry: dict[str, Any] = {"outcome": cell.outcome}
    if cell.age_days is not None:
        entry["ageDays"] = cell.age_days
    return entry


def _cells(row: Row, width: int | None = None) -> list[str]:
    """One row as the strings a table prints, in `COLUMNS` order."""
    description = row.description
    if width is not None and len(description) > width:
        description = description[: width - 3] + "..."
    return [
        row.plugin,
        row.skill,
        row.case,
        description,
        *(_cell_text(row.cells.get(backend)) for backend in BACKENDS),
        NONE if row.score is None else f"{row.score:.2f}",
        NONE if row.duration_seconds is None else f"{row.duration_seconds:.1f}s",
        NONE if row.flake is None else f"{row.flake:.2f} of {row.records}",
        "stale" if row.stale else NONE,
        _artefacts_text(row),
    ]


def _cell_text(cell: Cell | None) -> str:
    if cell is None:
        return NEVER
    if cell.age_days is None:
        return cell.outcome
    return f"{cell.outcome} {cell.age_days}d"


def _artefacts_text(row: Row) -> str:
    if row.artefacts is None:
        return NONE
    return f"{row.artefacts} ({GONE})" if row.gone else row.artefacts


# Pruning.


def prune(root: Path | str, days: int) -> list[Path]:
    """Drop records older than `days`, and return every file one was dropped from.

    The age is the record's own stamp, never the file's modification time: reading a file
    moves that time, and a case nobody has looked at is not younger than one somebody has.

    A file left with no record is deleted, and every directory that leaves empty is deleted
    after it, up to the history root, which stays. A record with no stamp and a line that did
    not parse are both kept: neither can be dated, and dropping what cannot be dated would
    delete a measurement on the age of nothing.
    """
    root = Path(root)
    if not root.is_dir():
        return []
    cutoff = datetime.now()
    touched = []
    for file in sorted(root.rglob(f"*{SUFFIX}")):
        lines = _lines(file)
        kept = [line for line in lines if not _older(line, cutoff, days)]
        if len(kept) == len(lines):
            continue
        touched.append(file)
        if kept:
            file.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")
            continue
        file.unlink()
        _empty(file.parent, root)
    return touched


def _lines(file: Path) -> list[str]:
    try:
        return [line for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return []


def _older(line: str, now: datetime, days: int) -> bool:
    """Whether one line is a record older than `days`. Anything undatable is kept.

    The arithmetic is `logs.prune`'s, because `--older-than DAYS` is one flag over both
    trees: an exact cutoff at `days` before now, not a floor on whole days. A floor keeps a
    record for a day longer than the run directory it names.
    """
    try:
        record = json.loads(line)
    except ValueError:
        return False
    if not isinstance(record, dict):
        return False
    when = _when(record)
    if when is None:
        return False
    moment_now = datetime.now(when.tzinfo) if when.tzinfo is not None else now
    return when < moment_now - timedelta(days=days)


def _empty(directory: Path, root: Path) -> None:
    """Delete `directory` and each empty parent above it, stopping at the history root."""
    current = directory
    while current != root and current.is_dir() and not any(current.iterdir()):
        current.rmdir()
        current = current.parent
