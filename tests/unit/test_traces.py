"""What is kept out of a run, over hand-written sandboxes and session directories on disk.

Every source here is written by the test: a harness sandbox in the layout
docs/claude_code/plugin_eval_reference.md records, and a CoWork session directory in the
layout docs/cowork_desktop.md records. The collector that reads either is the real one.
Nothing here runs a container or a session. See ../README.md.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import BaseModel

from cowork_evals import results, traces
from cowork_evals.cowork import ContentBlock, Message, SessionRecord
from cowork_evals.harness import RESULT_NAME
from cowork_evals.results import Arms, CaseEntry, CoWorkRef, ResultDocument, RunEntry
from cowork_evals.traces import TraceRecord

SANDBOX = "claude-eval-Ab12Cd"
FINAL = "The version is 3.10.12."
CASE_DIR = Path("traces") / "python-version"

# The hand-written document every document here is built from, by replacing its cases and runs.
BASE = ResultDocument.read(Path(__file__).resolve().parent.parent / "data/results/pass.json")
CASE = BASE.cases[0]
RUN = CASE.arms.with_[0]


def said(*blocks: ContentBlock, role: str | None = None) -> Message:
    return Message(role=role, content=list(blocks))


def text(value: str) -> ContentBlock:
    return ContentBlock(type="text", text=value)


THINKING = ContentBlock(type="thinking", thinking="not text")

# A thinking block, one tool call, one assistant text block and the `result` record the harness
# writes last. The result's text differs from the assistant's, so the reader shows which won.
TRACE = [
    TraceRecord(type="system", subtype="init"),
    TraceRecord(type="assistant", message=said(THINKING)),
    TraceRecord(
        type="assistant", message=said(ContentBlock(type="tool_use", name="Bash", input={}))
    ),
    TraceRecord(type="assistant", message=said(text("Python 3.10.12"))),
    TraceRecord(type="result", subtype="success", result=FINAL),
]

# One CoWork session transcript. The record shape is docs/cowork_desktop.md, and it is not
# the harness's: there is no `result` record, and the envelope carries a uuid.
SESSION_TRACE = [
    SessionRecord(type="user", uuid="tu-1", message=Message(role="user", content="Run python3 -V")),
    SessionRecord(
        type="assistant",
        uuid="ta-1",
        message=said(THINKING, text("Python 3.10.12"), role="assistant"),
    ),
]


def jsonl(records: Sequence[BaseModel]) -> str:
    return "".join(r.model_dump_json(by_alias=True, exclude_none=True) + "\n" for r in records)


def write_sandbox(
    root: Path, name: str = SANDBOX, *, trace: list[TraceRecord] = TRACE, workspace: bool = True
) -> Path:
    """One kept sandbox, sealed the way `--keep-temp` leaves it.

    The two trees the plugin under test wrote are under `sealed/` at mode 000 and the
    sandbox itself is read-only, which is what the collector has to undo.
    """
    sandbox = root / name
    (sandbox / traces.SANDBOX_OUT).mkdir(parents=True)
    (sandbox / traces.SANDBOX_OUT / traces.SANDBOX_TRACE).write_text(jsonl(trace), "utf-8")
    cwd = sandbox / traces.SANDBOX_SEALED / traces.SANDBOX_CWD
    cwd.mkdir(parents=True)
    if workspace:
        (cwd / "report.md").write_text("what the agent wrote", encoding="utf-8")
    (sandbox / traces.SANDBOX_SEALED).chmod(0o000)
    sandbox.chmod(0o500)
    return sandbox


def write_trace(directory: Path, records: list[TraceRecord] = TRACE) -> Path:
    """One trace on its own, for the reader. It needs no sandbox around it."""
    directory.mkdir(parents=True, exist_ok=True)
    trace = directory / traces.TRACE_NAME
    trace.write_text(jsonl(records), encoding="utf-8")
    return trace


def write_session(root: Path, *, outputs: bool = True) -> Path:
    """One CoWork session directory: an audit log, a transcript and produced files."""
    session = root / "s-0001"
    transcripts = session / ".claude" / "projects" / "session"
    transcripts.mkdir(parents=True)
    (session / "audit.jsonl").touch()
    (transcripts / "t-0001.jsonl").write_text(jsonl(SESSION_TRACE), encoding="utf-8")
    if outputs:
        (session / "outputs").mkdir()
        (session / "outputs" / "report.md").write_text("what the agent wrote", encoding="utf-8")
    return session


def session_entry(session: Path) -> RunEntry:
    """One CoWork run of the document, as results.py writes it."""
    transcript = session / ".claude" / "projects" / "session" / "t-0001.jsonl"
    return RUN.model_copy(
        update={
            "trace_path": str(transcript),
            "cowork": CoWorkRef(session_dir=str(session), timeout_seconds=1800.0),
        }
    )


def run_entry(passed: bool, name: str = SANDBOX) -> RunEntry:
    """One harness run, with the container-side `tracePath` the harness writes."""
    where = f"/work/logs/{traces.SANDBOX_DIR}/{name}/{traces.SANDBOX_OUT}/{traces.SANDBOX_TRACE}"
    return RUN.model_copy(update={"passed": passed, "trace_path": where})


def case(
    runs: list[RunEntry], without: list[RunEntry] | None = None, name: str = "python-version"
) -> CaseEntry:
    return CASE.model_copy(update={"name": name, "arms": Arms(with_=runs, without=without)})


def write_document(output_dir: Path, *cases: CaseEntry) -> Path:
    """A result document over the given cases."""
    output_dir.mkdir(parents=True, exist_ok=True)
    return results.write(output_dir, BASE.model_copy(update={"cases": list(cases)}))


def collected(output_dir: Path) -> ResultDocument:
    return ResultDocument.read(output_dir / RESULT_NAME)


def first_run(output_dir: Path) -> RunEntry:
    return collected(output_dir).cases[0].arms.with_[0]


# Naming.


def test_the_sandbox_root_is_under_the_plugin_log_directory(tmp_path: Path) -> None:
    assert traces.sandbox_root(tmp_path) == tmp_path / "tmp"


@pytest.mark.parametrize(
    ("name", "index", "occurrence", "arm", "expected"),
    [
        ("python-version", 2, 1, "with", "python-version/run-2"),
        ("acme/mail", 1, 1, "with", "acme-mail/run-1"),
        ("hello", 1, 2, "with", "hello-2/run-1"),
        ("python-version", 1, 1, "without", "python-version/without/run-1"),
    ],
)
def test_a_run_directory_is_named_for_the_case_the_arm_and_the_run_number(
    tmp_path: Path, name: str, index: int, occurrence: int, arm: str, expected: str
) -> None:
    """Nothing makes a case name unique in a plugin, and two skills may each hold `hello`."""
    made = traces.run_dir(tmp_path, name, index, occurrence=occurrence, arm=arm)
    assert made == tmp_path / "traces" / expected


def test_two_cases_of_one_name_do_not_land_on_each_other(tmp_path: Path) -> None:
    root = traces.sandbox_root(tmp_path)
    write_sandbox(root, "claude-eval-One")
    write_sandbox(root, "claude-eval-Two")
    write_document(
        tmp_path,
        case([run_entry(True, "claude-eval-One")], name="hello"),
        case([run_entry(True, "claude-eval-Two")], name="hello"),
    )

    assert traces.collect(tmp_path) == []
    assert (traces.run_dir(tmp_path, "hello", 1) / traces.TRACE_NAME).is_file()
    assert (traces.run_dir(tmp_path, "hello", 1, occurrence=2) / traces.TRACE_NAME).is_file()


def test_both_arms_are_collected_into_one_directory_each(tmp_path: Path) -> None:
    """A failure line about either arm names the directory holding that arm's transcript."""
    root = traces.sandbox_root(tmp_path)
    write_sandbox(root, "claude-eval-With")
    write_sandbox(root, "claude-eval-Without")
    with_run = run_entry(True, "claude-eval-With")
    write_document(tmp_path, case([with_run], [run_entry(False, "claude-eval-Without")]))

    assert traces.collect(tmp_path) == []
    baseline = traces.run_dir(tmp_path, "python-version", 1, arm="without")
    assert (baseline / traces.TRACE_NAME).is_file()
    assert (baseline / traces.LAST_MESSAGE_NAME).is_file()
    assert (baseline / traces.WORKSPACE_NAME).is_dir()
    arms = collected(tmp_path).cases[0].arms
    assert arms.with_[0].trace_path == str(tmp_path / CASE_DIR / "run-1" / "trace.jsonl")
    assert arms.without[0].trace_path == str(
        tmp_path / CASE_DIR / "without" / "run-1" / "trace.jsonl"
    )


def test_a_one_arm_document_leaves_no_arm_directory(tmp_path: Path) -> None:
    """The layout almost every run produces is the one it had before the baseline arm."""
    write_sandbox(traces.sandbox_root(tmp_path))
    write_document(tmp_path, case([run_entry(True)]))

    assert traces.collect(tmp_path) == []
    assert sorted(child.name for child in (tmp_path / CASE_DIR).iterdir()) == ["run-1"]


# The final message.


def test_the_final_message_is_the_result_record(tmp_path: Path) -> None:
    assert traces.last_message(write_trace(tmp_path)) == FINAL


def test_a_trace_with_no_result_record_falls_back_to_the_last_assistant_text(
    tmp_path: Path,
) -> None:
    """A run that ended before the harness wrote a result still said something."""
    records = [record for record in TRACE if record.type != "result"]
    assert traces.last_message(write_trace(tmp_path, records)) == "Python 3.10.12"


def test_a_thinking_block_is_not_the_final_message(tmp_path: Path) -> None:
    records = [TraceRecord(type="assistant", message=said(THINKING))]
    assert traces.last_message(write_trace(tmp_path, records)) is None


def test_a_half_written_last_line_is_dropped_and_the_rest_is_read(tmp_path: Path) -> None:
    trace = write_trace(tmp_path)
    with trace.open("a", encoding="utf-8") as handle:
        handle.write('{"type": "assis')
    assert traces.last_message(trace) == FINAL


# Collecting.


def _harness_runs(output: Path) -> str | None:
    """A passing and a failing harness run. A harness run names no session directory."""
    root = traces.sandbox_root(output)
    write_sandbox(root, "claude-eval-One")
    write_sandbox(root, "claude-eval-Two")
    write_document(
        output, case([run_entry(True, "claude-eval-One"), run_entry(False, "claude-eval-Two")])
    )
    return None


def _session_runs(output: Path) -> str | None:
    """Two CoWork runs. Returns the session directory they name."""
    session = write_session(output.parent / "profile")
    write_document(output, case([session_entry(session), session_entry(session)]))
    return str(session)


BACKENDS = pytest.mark.parametrize(
    "write", [_harness_runs, _session_runs], ids=["sandbox", "session"]
)


@pytest.mark.parametrize(
    ("write", "final"),
    [(_harness_runs, FINAL), (_session_runs, "Python 3.10.12")],
    ids=["sandbox", "session"],
)
def test_a_run_keeps_the_same_three_artefacts_whether_it_passed_or_failed(
    tmp_path: Path, write, final: str
) -> None:
    """A passing run is what a failing one is read against, so both keep the workspace.

    A session transcript has no `result` record, so its final message is the assistant text.
    """
    output = tmp_path / "logs"
    write(output)

    assert traces.collect(output) == []
    for index in (1, 2):
        kept = traces.run_dir(output, "python-version", index)
        assert (kept / traces.TRACE_NAME).is_file()
        assert (kept / traces.LAST_MESSAGE_NAME).read_text(encoding="utf-8") == final
        assert (kept / traces.WORKSPACE_NAME / "report.md").read_text(
            encoding="utf-8"
        ) == "what the agent wrote"


def test_the_sandboxes_are_removed_however_they_were_sealed(tmp_path: Path) -> None:
    root = traces.sandbox_root(tmp_path)
    write_sandbox(root)
    write_sandbox(root, "claude-eval-Orphan")
    write_document(tmp_path, case([run_entry(passed=True)]))

    traces.collect(tmp_path)
    assert not root.exists(), "an unclaimed sandbox is removed with the rest of the root"


@BACKENDS
def test_the_trace_path_is_rewritten_to_where_the_trace_now_is(tmp_path: Path, write) -> None:
    """The one field that named the trace still names it, so the run prints the same thing
    whichever backend produced it. A CoWork run still names its session directory."""
    output = tmp_path / "logs"
    session = write(output)

    traces.collect(output)
    run = first_run(output)
    assert run.trace_path == str(output / CASE_DIR / "run-1" / "trace.jsonl")
    assert Path(run.trace_path).is_file()
    assert (run.cowork.session_dir if run.cowork else None) == session


# When collection cannot be done. Every one of these is a warning and nothing else.


def test_a_missing_result_document_is_a_warning_and_the_sandboxes_still_go(
    tmp_path: Path,
) -> None:
    root = traces.sandbox_root(tmp_path)
    write_sandbox(root)

    warnings = traces.collect(tmp_path)
    assert len(warnings) == 1
    assert RESULT_NAME in warnings[0]
    assert not root.exists()


@pytest.mark.parametrize(
    ("run", "expected"),
    [
        (
            RUN.model_copy(update={"passed": False, "trace_path": "a-correlation-id"}),
            "tracePath names no kept sandbox: 'a-correlation-id'",
        ),
        (run_entry(True), "{root}/" + SANDBOX + " was not kept, so there is no trace to collect"),
    ],
    ids=["no-sandbox-named", "not-kept"],
)
def test_a_run_whose_sandbox_is_not_there_is_a_warning(
    tmp_path: Path, run: RunEntry, expected: str
) -> None:
    root = traces.sandbox_root(tmp_path)
    root.mkdir(parents=True)
    write_document(tmp_path, case([run]))

    assert traces.collect(tmp_path) == [f"python-version: run 1: {expected.format(root=root)}"]


def test_a_sandbox_holding_no_workspace_is_a_warning(tmp_path: Path) -> None:
    """The trace is still kept: one artefact that is not there does not lose the others."""
    sandbox = write_sandbox(traces.sandbox_root(tmp_path))
    sandbox.chmod(0o700)
    (sandbox / traces.SANDBOX_SEALED).chmod(0o700)
    for child in (sandbox / traces.SANDBOX_SEALED / traces.SANDBOX_CWD).iterdir():
        child.unlink()
    (sandbox / traces.SANDBOX_SEALED / traces.SANDBOX_CWD).rmdir()
    write_document(tmp_path, case([run_entry(passed=True)]))

    warnings = traces.collect(tmp_path)
    assert len(warnings) == 1
    assert "no workspace to collect" in warnings[0]
    assert (traces.run_dir(tmp_path, "python-version", 1) / traces.TRACE_NAME).is_file()


# The CoWork backend. The same three names, out of a session directory instead of a sandbox.


def test_the_session_directory_is_copied_and_never_emptied(tmp_path: Path) -> None:
    """It is the account's own permanent record, and nothing here writes under the profile."""
    session = write_session(tmp_path / "profile")
    output = tmp_path / "logs"
    write_document(output, case([session_entry(session)]))

    traces.collect(output)
    transcript = session / ".claude" / "projects" / "session" / "t-0001.jsonl"
    assert transcript.is_file(), "the transcript was moved out of the session"
    assert (session / "outputs" / "report.md").is_file(), "the produced files were moved"
    assert (session / "audit.jsonl").is_file()


def test_a_session_that_produced_no_file_is_not_a_warning(tmp_path: Path) -> None:
    """A session holds `outputs/` only once the run produced one, unlike a kept sandbox."""
    session = write_session(tmp_path / "profile", outputs=False)
    output = tmp_path / "logs"
    write_document(output, case([session_entry(session)]))

    assert traces.collect(output) == []
    kept = traces.run_dir(output, "python-version", 1)
    assert (kept / traces.TRACE_NAME).is_file()
    assert not (kept / traces.WORKSPACE_NAME).exists()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("5: no session directory appeared", []),
        (None, ["python-version: run 1: the run reached no session directory"]),
    ],
)
def test_a_run_that_reached_no_session_warns_only_without_an_error(
    tmp_path: Path, error: str | None, expected: list[str]
) -> None:
    """The error already says why there is nothing to collect, and a second line is noise."""
    nothing = CoWorkRef(session_dir=None, timeout_seconds=1800.0)
    run = RUN.model_copy(update={"passed": False, "error": error, "cowork": nothing})
    write_document(tmp_path / "logs", case([run]))
    assert traces.collect(tmp_path / "logs") == expected


# The two validity checks, over traces written by the test.

# The two records the checks read, in the shape docs/run_pipeline.md records. A hook denial
# is the same record with another reason, which is the plugin's own behaviour and not the
# container failing to behave like a session.
GRANT = ("Bash", "Read", "Glob", "Grep", "Write", "Edit", "WebFetch", "Skill")
OFFERED = [
    "Task",
    "Bash",
    "Edit",
    "Glob",
    "Grep",
    "NotebookEdit",
    "Read",
    "Skill",
    "WebFetch",
    "WebSearch",
    "Write",
]


def init(tools: list[str] = OFFERED) -> TraceRecord:
    return TraceRecord(type="system", subtype="init", tools=tools)


def denial(tool: str, reason: str = "mode") -> TraceRecord:
    return TraceRecord(
        type="system",
        subtype="permission_denied",
        tool_name=tool,
        decision_reason_type=reason,
        message=f"Permission to use {tool} has been denied.",
    )


def validity_run(
    tmp_path: Path, records: list[TraceRecord], granted: tuple[str, ...] = GRANT
) -> RunEntry:
    """Collect one harness run over the given trace, and return its entry in the document."""
    output = tmp_path / "logs"
    write_sandbox(traces.sandbox_root(output), trace=records)
    write_document(output, case([run_entry(True)]))

    assert traces.collect(output, granted=granted) == []
    return first_run(output)


@pytest.mark.parametrize(
    ("denials", "expected"),
    [
        ([denial("Write")], ["Write"]),
        ([denial("Write"), denial("Edit"), denial("Write")], ["Write", "Edit"]),
        ([denial("Write", "hook")], None),
    ],
    ids=["mode", "repeated", "hook"],
)
def test_a_mode_denial_names_its_tool_and_a_hook_denial_names_none(
    tmp_path: Path, denials: list[TraceRecord], expected: list[str] | None
) -> None:
    """A session has no permission mode, so a mode denial is the container being unlike one.
    A hook denial is the plugin's own behaviour, which a case testing a hook asserts over."""
    entry = validity_run(tmp_path, [init(), *denials, *TRACE[1:]])
    assert entry.denied_tools == expected


@pytest.mark.parametrize(
    ("records", "granted", "expected"),
    [
        ([init([t for t in OFFERED if t != "Bash"]), *TRACE[1:]], GRANT, ["Bash"]),
        (
            [init(["WebFetch", "Read(//home/**)", "Skill"]), *TRACE[1:]],
            ("WebFetch(domain:example.com)", "Read", "Skill"),
            None,
        ),
        ([record for record in TRACE if record.type != "system"], GRANT, None),
        ([init(), *TRACE[1:]], (), None),
        ([init(), *TRACE[1:]], GRANT, None),
    ],
    ids=["missing", "before-the-bracket", "no-init", "empty-grant", "healthy"],
)
def test_a_granted_tool_missing_from_the_offered_list_is_named(
    tmp_path: Path,
    records: list[TraceRecord],
    granted: tuple[str, ...],
    expected: list[str] | None,
) -> None:
    """A grant may carry a pattern, and a read reaches the child path-scoped. A run that wrote
    no tool list, or a grant of nothing, says nothing about what it had."""
    entry = validity_run(tmp_path, records, granted)
    assert entry.unoffered_tools == expected
    assert entry.denied_tools is None


def test_a_cowork_run_carries_neither_field(tmp_path: Path) -> None:
    """A session has no permission mode and writes no tool list, so neither check applies."""
    session = write_session(tmp_path / "profile")
    output = tmp_path / "logs"
    write_document(output, case([session_entry(session)]))

    assert traces.collect(output, granted=GRANT) == []
    entry = first_run(output)
    assert entry.denied_tools is None
    assert entry.unoffered_tools is None
