"""What one run left behind, lifted into the log directory. One layout for both backends.

Every run of either backend leaves the same three names, so a case is read the same way
whichever backend produced it. What differs is only where they are read from, and that is
`_source` below. docs/running_evals.md, docs/run_pipeline.md.

| Backend    | The artefacts are in                       | And are |
| ---------- | ------------------------------------------ | ------- |
| `--docker` | the sandbox `--keep-temp` kept, on the host | moved   |
| `--cowork` | the CoWork session directory                | copied  |

The container backend points the harness's `TMPDIR` at the run's log mount, so the sandbox
lands on the host rather than inside a container started with `--rm`. It is a throwaway
directory and is emptied here. A CoWork session directory is the account's own permanent
record: it is read and never written, never moved from and never removed.

The split against [logs.py](logs.py): that module owns every path an invocation writes and is
the only thing that deletes one, this module owns what is put into one of them. The two
transcript formats are each parsed where that format is already parsed: the harness's
`trace.jsonl` here, and a session transcript by `cowork.final_text`. Neither is read twice.

A kept harness trace is also read for the two things that say the run could not have passed:
a tool the permission mode refused, and a granted tool the run never offered the model. Both
are written into that run's entry in the result document, so pass and fail still read only
that file. Neither runs on CoWork, and neither runs when the traces are off, because both
read a kept trace. docs/running_evals.md.

Nothing here raises. A source that is not there, a trace that will not read and a document
that will not parse are each a warning line the caller prints, because a collection problem is
not a failed run. Nothing here prints, and nothing here decides pass or fail.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import logs
from .cowork import OUTPUTS as SESSION_OUTPUTS
from .cowork import final_text
from .harness import RESULT_NAME
from .results import ARM_WITH, ARMS

# The harness's `TMPDIR` inside the log directory, and so the parent of every kept sandbox.
# Short, because a socket path inside it is bounded. It is removed once collection is done,
# so nothing under this name survives an invocation.
SANDBOX_DIR = "tmp"

# What one kept sandbox holds, from docs/claude_code/plugin_eval_reference.md. `home/` and
# `tmp/` are moved under `sealed/` when the plugin under test wrote to either, and stay where
# they are when it wrote to neither, so the workspace is looked for under both names.
SANDBOX_OUT = "out"
SANDBOX_TRACE = "trace.jsonl"
SANDBOX_SEALED = "sealed"
SANDBOX_CWD = Path("home") / "cwd"

# What this module writes, one directory per run. docs/running_evals.md.
TRACES_DIR = "traces"
RUN_PREFIX = "run-"
TRACE_NAME = "trace.jsonl"
LAST_MESSAGE_NAME = "last_message.txt"
WORKSPACE_NAME = "workspace"


# The result document field that says a run came from the CoWork backend. It is this
# repository's own added field, and the harness writes no such key.
# docs/cowork_backend.md.
COWORK = "cowork"
SESSION_DIR = "sessionDir"

# The two fields the checks below add to a run's entry, read by [verdict.py](verdict.py).
# They are this repository's own, like `cowork` above, and the contract is additive-only.
# docs/running_evals.md.
DENIED = "deniedTools"
UNOFFERED = "unofferedTools"

# The two records the checks read, from docs/claude_code/plugin_eval_reference.md and the
# facts in docs/run_pipeline.md.
SYSTEM = "system"
INIT = "init"
PERMISSION_DENIED = "permission_denied"

# The one denial reason that invalidates a run. A session has no permission mode and is never
# refused a tool by one, so a `mode` denial is the container failing to behave like a session.
# A denial from the plugin's own hook carries another reason and is the plugin's behaviour,
# which a case testing a hook is asserting over. docs/running_evals.md.
MODE = "mode"


@dataclass(frozen=True, slots=True)
class Source:
    """Where one run's artefacts are before they are collected.

    `session` is which backend produced the run, and it decides two things and nothing else:
    whether the artefacts are moved or copied, and which reader answers for the transcript
    format. A missing workspace is also read differently, for the reason in `_keep_workspace`.
    """

    trace: Path
    workspace: Path
    session: bool


def sandbox_root(output_dir: Path | str) -> Path:
    """Where the harness puts its sandboxes when this run is keeping them.

    The container backend creates this before the run and passes the container-side name of
    it as `TMPDIR`; `collect` empties it afterwards.
    """
    return Path(output_dir) / SANDBOX_DIR


def run_dir(
    output_dir: Path | str,
    case: str,
    index: int,
    *,
    occurrence: int = 1,
    arm: str = ARM_WITH,
) -> Path:
    """`<plugin log dir>/traces/<case>/run-<n>`, the directory one run's artefacts go in.

    `index` is 1-based, and is the same number the verdict line prints as `run N`, so a failure line
    and a directory name name the same run.

    Nothing makes a case name unique inside a plugin: two skills may each hold a case named
    `hello`. `occurrence` is which of them this is, and the second gets `-2`, exactly as
    `logs.plugin_dir` suffixes the second plugin of a name. Without it the second case's runs
    would land on the first's, and a failure line would name a directory holding the wrong run.

    The with-arm's path is the path, and every other arm goes in a directory of its own named
    for the arm, between the case and the run. A one-arm run is therefore laid out exactly as
    it was before the baseline arm existed, which is what almost every run produces, and
    `traces/<case>/run-*` still selects the with-arm alone in a two-arm run.
    docs/running_evals.md.
    """
    name = logs.slug(case)
    if occurrence > 1:
        name = f"{name}-{occurrence}"
    directory = Path(output_dir) / TRACES_DIR / name
    if arm != ARM_WITH:
        directory = directory / logs.slug(arm)
    return directory / f"{RUN_PREFIX}{index}"


def collect(output_dir: Path | str, *, granted: tuple[str, ...] = ()) -> list[str]:
    """Keep each run's trace, then remove the sandboxes. Returns the warnings to print.

    Every run keeps the same three artefacts, whether it passed or failed and whichever
    backend produced it: its trace, its final assistant message and its workspace. A passing
    run is what a failing one is read against, so keeping less for one than for the other
    would drop half of every comparison. docs/running_evals.md.

    `tracePath` in the result document is rewritten to the host path of the trace this kept,
    so the one field that named the trace still names it and the verdict line prints the same thing
    on both backends. A CoWork run's session directory is still in `cowork.sessionDir`.

    The caller calls this only when the run was keeping its traces. Off, the harness kept no
    sandbox and there is nothing here to find. An empty list means there was nothing to
    collect or everything was collected.

    `granted` is what the run was given, from the backend's `RunOptions`, and is what the
    offered tool list is held against. The CoWork backend has none and passes none: it runs
    no command line, offers no list and has no permission mode, so both checks find nothing
    there. An empty grant is not a failure condition, it is nothing to compare.
    """
    output_dir = Path(output_dir)
    root = sandbox_root(output_dir)
    document, unreadable = _document(output_dir)

    if unreadable is not None:
        # No document and no sandboxes is a backend that produced nothing at all. The verdict
        # reports the missing document, and there is nothing here to add.
        warnings = [unreadable] if root.is_dir() else []
    else:
        warnings = _each_run(output_dir, root, document, granted) + _rewrite(output_dir, document)
    if root.is_dir():
        warnings += _remove(root)
    return warnings


def last_message(trace: Path | str) -> str | None:
    """The final assistant message of one harness `trace.jsonl`.

    It is what a `target: last_message` grader read. The trace's `result` record carries it
    verbatim, which is why that record is preferred. A run that ended before one was written
    falls back to the last assistant text block, and a run with neither has no final message
    at all.

    This reads the harness's format alone. A CoWork session transcript is a different format
    and is read by `cowork.final_text`, which is the function the driver already reads it
    with.
    """
    return _final(_records(trace))


def denied_tools(records: list[dict[str, Any]]) -> list[str]:
    """Check one: every tool the permission mode refused this run, in the order refused.

    A `permission_denied` record carries the tool and why it was refused. Only `mode` is read.
    A session has no permission mode, so a mode denial is the container failing to behave like
    one; a denial the plugin's own hook wrote is the plugin's behaviour and is what a case
    testing that hook asserts over. The match is on the reason and never on the tool name,
    because narrowing it to the tools a grader names would miss every denial that broke a run
    through a tool no grader mentions. docs/running_evals.md.
    """
    found: list[str] = []
    for record in records:
        if record.get("type") != SYSTEM or record.get("subtype") != PERMISSION_DENIED:
            continue
        if record.get("decision_reason_type") != MODE:
            continue
        tool = record.get("tool_name")
        if isinstance(tool, str) and tool and tool not in found:
            found.append(tool)
    return found


def unoffered_tools(records: list[dict[str, Any]], granted: tuple[str, ...]) -> list[str]:
    """Check two: every granted tool the run never offered the model, in the grant's order.

    The `init` record lists what the run offered. A trace with no such record says nothing
    about what the run had, and yields nothing rather than every granted name.

    A granted name and an offered name are compared on the part before any `(`. A grant may
    be written `WebFetch(domain:example.com)`, and the reference records that a bare `Read`,
    `Glob` or `Grep` reaches the child path-scoped, so a literal comparison would report a run
    as missing a tool it had. Every granted name arrives in the list bare, which
    docs/run_pipeline.md records, so no name needs excluding from the comparison.
    """
    offered = _offered(records)
    if offered is None:
        return []
    missing: list[str] = []
    for name in granted:
        bare = _bare(name)
        if bare and bare not in offered and bare not in missing:
            missing.append(bare)
    return missing


def _note_validity(
    run: dict[str, Any], records: list[dict[str, Any]], granted: tuple[str, ...]
) -> None:
    """Write what the two checks found into this run's entry, and nothing when they found
    nothing, so a healthy document is unchanged."""
    denied = denied_tools(records)
    if denied:
        run[DENIED] = denied
    unoffered = unoffered_tools(records, granted)
    if unoffered:
        run[UNOFFERED] = unoffered


def _offered(records: list[dict[str, Any]]) -> set[str] | None:
    """The tool names the `init` record listed, or `None` when the run wrote no list."""
    for record in records:
        if record.get("type") != SYSTEM or record.get("subtype") != INIT:
            continue
        tools = record.get("tools")
        if isinstance(tools, list):
            return {_bare(tool) for tool in tools if isinstance(tool, str)}
    return None


def _bare(name: str) -> str:
    """A tool name without the pattern a grant or a scoped offer may carry."""
    return name.split("(", 1)[0].strip()


# One run.


def _each_run(
    output_dir: Path, root: Path, document: dict[str, Any], granted: tuple[str, ...]
) -> list[str]:
    """Every run of every arm of every case, in the order the document lists them.

    `seen` counts the cases carrying each name, which is what `run_dir` suffixes on.

    Both arms are collected, so a failing delta is read as two transcripts rather than one.
    A one-arm document carries no `without` key and this walks the same runs it always did.
    """
    warnings = []
    seen: dict[str, int] = {}
    for case in document.get("cases") or []:
        if not isinstance(case, dict):
            continue
        name = str(case.get("name"))
        seen[name] = seen.get(name, 0) + 1
        arms = case.get("arms") or {}
        for arm in ARMS:
            for index, run in enumerate(arms.get(arm) or [], start=1):
                if isinstance(run, dict):
                    warnings += _one_run(
                        output_dir, root, name, index, run, seen[name], granted, arm
                    )
    return warnings


def _one_run(
    output_dir: Path,
    root: Path,
    case: str,
    index: int,
    run: dict[str, Any],
    occurrence: int,
    granted: tuple[str, ...],
    arm: str = ARM_WITH,
) -> list[str]:
    """One run's artefacts, and `tracePath` pointed at where the trace now is.

    The kept trace is read once. A harness trace answers the final message and both validity
    checks out of the same records; a session transcript is another format and is read by
    `cowork.final_text`, which parses it for the one thing it is asked.

    `arm` reaches the destination directory and the warning line. Every arm's `tracePath` is
    rewritten, so the `[artifacts: ...]` suffix on a line about either names the right
    directory.
    """
    where = f"{case}: run {index}" if arm == ARM_WITH else f"{case}: {arm}-arm run {index}"
    source, missing = _source(root, run)
    if source is None:
        # A run that already carries an error says why there is nothing to collect, and a
        # second line saying it again is noise. The verdict line prints the error either way.
        return [] if run.get("error") else [f"{where}: {missing}"]

    if not source.session:
        logs.unseal(source.trace.parent.parent)
    destination = run_dir(output_dir, case, index, occurrence=occurrence, arm=arm)
    try:
        destination.mkdir(parents=True, exist_ok=True)
        trace = _keep_trace(source, destination)
    except OSError as error:
        return [f"{where}: the trace could not be collected: {error}"]

    run["tracePath"] = str(trace)
    try:
        records = None if source.session else _records(trace)
    except OSError as error:
        return [f"{where}: {trace} is unreadable: {error}"]
    if records is not None:
        _note_validity(run, records, granted)
    return _keep_last_message(source, trace, records, destination, where) + _keep_workspace(
        source, destination, where
    )


def _source(root: Path, run: dict[str, Any]) -> tuple[Source | None, str | None]:
    """Where one run's artefacts are, or the reason there are none.

    The rule that decides which backend produced the run is the `cowork` key: this
    repository adds it to every CoWork run and the harness writes no such key.
    docs/cowork_backend.md. It is the key and never its value, because a run the driver
    could not start carries the key with a null `sessionDir`.
    """
    if COWORK in run:
        return _session_source(run)
    return _sandbox_source(root, run)


def _session_source(run: dict[str, Any]) -> tuple[Source | None, str | None]:
    """A CoWork run: the transcript the driver found, and the session's produced files.

    `outputs/` is the workspace on this backend, which is the same rule `grader.py` applies
    to a `file_exists` grader and to a `{source: file}` target.
    """
    session = (run.get(COWORK) or {}).get(SESSION_DIR)
    if not isinstance(session, str) or not session:
        return None, "the run reached no session directory"
    transcript = run.get("tracePath")
    if not isinstance(transcript, str) or not transcript:
        return None, "the session wrote no transcript"
    return Source(
        trace=Path(transcript),
        workspace=Path(session) / SESSION_OUTPUTS,
        session=True,
    ), None


def _sandbox_source(root: Path, run: dict[str, Any]) -> tuple[Source | None, str | None]:
    """A harness run: the kept sandbox its `tracePath` names, on the host.

    The document's path is the container's, `<TMPDIR>/claude-eval-XXXXXX/out/trace.jsonl`,
    and only its sandbox component is read: the host half of the same mount is `root`.
    """
    named = run.get("tracePath")
    if not isinstance(named, str) or not named:
        return None, f"tracePath names no kept sandbox: {named!r}"
    path = Path(named)
    if path.name != SANDBOX_TRACE or path.parent.name != SANDBOX_OUT:
        return None, f"tracePath names no kept sandbox: {named!r}"
    sandbox = root / path.parent.parent.name
    if not sandbox.is_dir():
        return None, f"{sandbox} was not kept, so there is no trace to collect"
    return Source(
        trace=sandbox / SANDBOX_OUT / SANDBOX_TRACE,
        workspace=sandbox / SANDBOX_SEALED / SANDBOX_CWD,
        session=False,
    ), None


def _keep_trace(source: Source, destination: Path) -> Path:
    """Put the trace under the run directory, and return where it now is."""
    trace = destination / TRACE_NAME
    _take(source, source.trace, trace)
    return trace


def _keep_last_message(
    source: Source,
    trace: Path,
    records: list[dict[str, Any]] | None,
    destination: Path,
    where: str,
) -> list[str]:
    """Write the final assistant message beside the trace it was read from.

    It is read from the collected copy rather than from the original, so what is written is
    what the file under the run directory says. `records` is the harness trace already read;
    a session transcript arrives as `None` and `cowork.final_text` reads it.
    """
    try:
        message = final_text(trace) if records is None else _final(records)
    except OSError as error:
        return [f"{where}: {trace} is unreadable: {error}"]
    if message is None:
        return [f"{where}: the trace carries no assistant message"]
    try:
        (destination / LAST_MESSAGE_NAME).write_text(message, encoding="utf-8")
    except OSError as error:
        return [f"{where}: the final message could not be written: {error}"]
    return []


def _keep_workspace(source: Source, destination: Path, where: str) -> list[str]:
    """The run's workspace: the agent's working directory, or the session's produced files.

    An absent one is a warning on the harness and silence on CoWork, and the two differ
    because the directory does. A kept sandbox always holds `home/cwd`, so its absence means
    the sandbox layout changed and is worth a line. A session holds `outputs/` only once the
    run has produced a file, so a session without one produced nothing and there is nothing
    to say.
    """
    for candidate in _workspaces(source):
        if candidate.is_dir():
            try:
                _take(source, candidate, destination / WORKSPACE_NAME)
            except OSError as error:
                return [f"{where}: the workspace could not be collected: {error}"]
            return []
    if source.session:
        return []
    return [f"{where}: {source.workspace} is not there, so there is no workspace to collect"]


def _workspaces(source: Source) -> tuple[Path, ...]:
    """Where the workspace may be. The harness has two names for it and CoWork has one.

    `home/` and `tmp/` are moved under `sealed/` only when the plugin under test wrote to
    either, and stay where they are when it wrote to neither.
    """
    if source.session:
        return (source.workspace,)
    sandbox = source.trace.parent.parent
    return (source.workspace, sandbox / SANDBOX_CWD)


def _take(source: Source, origin: Path, destination: Path) -> None:
    """Move it, or copy it when the origin is not this package's to empty.

    A kept sandbox is a throwaway directory and moving out of it is what empties it. A CoWork
    session directory is the account's own permanent record, and nothing in this package
    writes anywhere under the profile. docs/cowork_driver.md.
    """
    if not source.session:
        shutil.move(str(origin), str(destination))
    elif origin.is_dir():
        shutil.copytree(origin, destination, dirs_exist_ok=True)
    else:
        shutil.copy2(origin, destination)


# The document, and the sandboxes afterwards.


def _document(output_dir: Path) -> tuple[dict[str, Any], str | None]:
    """The result document, or the one line saying why the sandboxes cannot be mapped."""
    path = output_dir / RESULT_NAME
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {}, f"{path}: no result document to map the kept sandboxes onto: {error}"
    if not isinstance(document, dict):
        return {}, f"{path}: expected a mapping at the top level"
    return document, None


def _rewrite(output_dir: Path, document: dict[str, Any]) -> list[str]:
    try:
        written = json.dumps(document, indent=2) + "\n"
        (output_dir / RESULT_NAME).write_text(written, encoding="utf-8")
    except OSError as error:
        return [f"{output_dir / RESULT_NAME}: the collected paths could not be written: {error}"]
    return []


def _remove(root: Path) -> list[str]:
    try:
        logs.remove_tree(root)
    except OSError as error:
        return [f"{root}: the kept sandboxes could not be removed: {error}"]
    return []


# Reading a trace.


def _records(trace: Path | str) -> list[dict[str, Any]]:
    """Every JSON object in the trace, in order. An unparsable line is skipped.

    The harness writes one object per line and the file is read whole, so a line a
    truncated trace left half written is dropped rather than stopping the read.
    """
    text = Path(trace).read_text(encoding="utf-8", errors="replace")
    found = []
    for line in text.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            found.append(record)
    return found


def _final(records: list[dict[str, Any]]) -> str | None:
    """The final assistant message of an already-read harness trace. `last_message` over
    records, so one read answers the message and both checks."""
    final = None
    fallback = None
    for record in records:
        kind = record.get("type")
        if kind == "result" and isinstance(record.get("result"), str):
            final = record["result"]
        elif kind == "assistant":
            text = _assistant_text(record)
            if text:
                fallback = text
    return final if final is not None else fallback


def _assistant_text(record: dict[str, Any]) -> str:
    """The text blocks of one assistant record, joined. A thinking block is not text."""
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(
        block["text"]
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    )
