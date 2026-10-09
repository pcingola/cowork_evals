"""What is kept out of a run, over hand-written sandboxes and session directories on disk.

Every source here is written by the test: a harness sandbox in the layout
docs/claude_code/plugin_eval_reference.md records, and a CoWork session directory in the
layout docs/cowork_desktop.md records. The collector that reads either is the real one.
Nothing here runs a container or a session. See ../README.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from cowork_evals import results, traces
from cowork_evals.harness import RESULT_NAME
from cowork_evals.results import (
    Arms,
    CaseAggregates,
    CaseEntry,
    CoWorkRef,
    ResultDocument,
    RunEntry,
    SuiteAggregates,
    SuiteInfo,
)

SANDBOX = "claude-eval-Ab12Cd"

# One assistant text block, one tool call and the `result` record the harness writes last.
TRACE = [
    {"type": "system", "subtype": "init"},
    {
        "type": "assistant",
        "message": {"content": [{"type": "thinking", "thinking": "not text"}]},
    },
    {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]},
    },
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "Python 3.10.12"}]}},
    {"type": "result", "subtype": "success", "result": "Python 3.10.12"},
]


def write_sandbox(
    root: Path, name: str = SANDBOX, *, trace: list[dict] | None = None, workspace: bool = True
) -> Path:
    """One kept sandbox, sealed the way `--keep-temp` leaves it.

    The two trees the plugin under test wrote are under `sealed/` at mode 000 and the
    sandbox itself is read-only, which is what the collector has to undo.
    """
    sandbox = root / name
    (sandbox / traces.SANDBOX_OUT).mkdir(parents=True)
    records = TRACE if trace is None else trace
    (sandbox / traces.SANDBOX_OUT / traces.SANDBOX_TRACE).write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    cwd = sandbox / traces.SANDBOX_SEALED / traces.SANDBOX_CWD
    cwd.mkdir(parents=True)
    if workspace:
        (cwd / "report.md").write_text("what the agent wrote", encoding="utf-8")
    (sandbox / traces.SANDBOX_SEALED).chmod(0o000)
    sandbox.chmod(0o500)
    return sandbox


def write_trace(directory: Path, records: list[dict] | None = None) -> Path:
    """One trace on its own, for the reader. It needs no sandbox around it."""
    directory.mkdir(parents=True, exist_ok=True)
    trace = directory / traces.TRACE_NAME
    trace.write_text(
        "".join(json.dumps(record) + "\n" for record in (TRACE if records is None else records)),
        encoding="utf-8",
    )
    return trace


# One CoWork session transcript. The record shape is docs/cowork_desktop.md, and it is not
# the harness's: there is no `result` record, and the envelope carries a uuid and a session id.
SESSION_TRACE = [
    {"type": "user", "uuid": "tu-1", "message": {"role": "user", "content": "Run python3 -V"}},
    {
        "type": "assistant",
        "uuid": "ta-1",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "not text"},
                {"type": "text", "text": "Python 3.10.12"},
            ],
        },
    },
]


def write_session(root: Path, name: str = "s-0001", *, outputs: bool = True) -> Path:
    """One CoWork session directory: an audit log, a transcript and produced files."""
    session = root / name
    (session / "audit.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (session / "audit.jsonl").write_text('{"state": "completed"}\n', encoding="utf-8")
    transcripts = session / ".claude" / "projects" / "session"
    transcripts.mkdir(parents=True)
    (transcripts / "t-0001.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in SESSION_TRACE), encoding="utf-8"
    )
    if outputs:
        (session / "outputs").mkdir()
        (session / "outputs" / "report.md").write_text("what the agent wrote", encoding="utf-8")
    return session


def bare_run(
    passed: bool,
    *,
    trace_path: str | None = None,
    error: str | None = None,
    cowork: CoWorkRef | None = None,
) -> RunEntry:
    """One run of the document, with nothing graded."""
    return RunEntry(
        score=1.0 if passed else 0.0,
        passed=passed,
        turns=0,
        cost_usd=0.0,
        judge_cost_usd=0.0,
        error=error,
        skipped_paid_graders=False,
        graders=[],
        trace_path=trace_path,
        cowork=cowork,
    )


def session_entry(session: Path, *, passed: bool = True, error: str | None = None) -> RunEntry:
    """One CoWork run of the document, as results.py writes it."""
    return bare_run(
        passed,
        error=error,
        trace_path=str(session / ".claude" / "projects" / "session" / "t-0001.jsonl"),
        cowork=CoWorkRef(session_dir=str(session), timeout_seconds=1800.0),
    )


def write_document(output_dir: Path, *runs: RunEntry) -> Path:
    """A result document naming one case whose runs are the ones given."""
    return write_cases(output_dir, ("python-version", list(runs)))


def case_entry(name: str, runs: list[RunEntry], without: list[RunEntry] | None = None) -> CaseEntry:
    return CaseEntry(
        name=name,
        dir=name,
        source="",
        prompt_markdown="",
        graders=[],
        arms=Arms(with_=runs, without=without),
        aggregates=CaseAggregates(score=0.0, pass_rate=0.0),
    )


def write_entries(output_dir: Path, cases: list[CaseEntry]) -> Path:
    """A result document over the given cases."""
    document = ResultDocument(
        schema_version=1,
        claude_version="",
        started_at="",
        duration_seconds=0.0,
        cost_usd=0.0,
        suite=SuiteInfo(root="", ablation="none", threshold=0, judge_model="", plugins=[]),
        cases=cases,
        aggregates=SuiteAggregates(
            cases_total=len(cases), cases_passed=0, overall_score=0.0, overall_pass_rate=0.0
        ),
    )
    return results.write(output_dir, document)


def write_cases(output_dir: Path, *cases: tuple[str, list[RunEntry]]) -> Path:
    """A result document of several cases, each with its own runs."""
    return write_entries(output_dir, [case_entry(name, runs) for name, runs in cases])


def run_entry(passed: bool, name: str = SANDBOX) -> RunEntry:
    """One run of the document, with the container-side `tracePath` the harness writes."""
    return bare_run(
        passed,
        trace_path=f"/work/logs/{traces.SANDBOX_DIR}/{name}/"
        f"{traces.SANDBOX_OUT}/{traces.SANDBOX_TRACE}",
    )


def write_two_arm(
    output_dir: Path, name: str, *, with_runs: list[RunEntry], without: list[RunEntry]
) -> Path:
    """A two-arm document, as `--ablation with-without` writes one. Both arms carry runs."""
    return write_entries(output_dir, [case_entry(name, with_runs, without)])


def collected(output_dir: Path) -> ResultDocument:
    return ResultDocument.read(output_dir / RESULT_NAME)


# Naming.


def test_the_sandbox_root_is_under_the_plugin_log_directory(tmp_path: Path) -> None:
    assert traces.sandbox_root(tmp_path) == tmp_path / "tmp"


def test_a_run_directory_is_named_for_the_case_and_the_run_number(tmp_path: Path) -> None:
    assert (
        traces.run_dir(tmp_path, "python-version", 2)
        == tmp_path / "traces" / "python-version" / "run-2"
    )


def test_a_case_name_that_is_not_a_safe_directory_name_is_slugged(tmp_path: Path) -> None:
    assert traces.run_dir(tmp_path, "acme/mail", 1).parent.name == "acme-mail"


def test_the_second_case_of_a_name_is_suffixed(tmp_path: Path) -> None:
    """Nothing makes a case name unique in a plugin, and two skills may each hold `hello`."""
    assert traces.run_dir(tmp_path, "hello", 1, occurrence=2).parent.name == "hello-2"


def test_two_cases_of_one_name_do_not_land_on_each_other(tmp_path: Path) -> None:
    root = traces.sandbox_root(tmp_path)
    write_sandbox(root, "claude-eval-One")
    write_sandbox(root, "claude-eval-Two")
    write_cases(
        tmp_path,
        ("hello", [run_entry(True, "claude-eval-One")]),
        ("hello", [run_entry(True, "claude-eval-Two")]),
    )

    assert traces.collect(tmp_path) == []
    assert (traces.run_dir(tmp_path, "hello", 1) / traces.TRACE_NAME).is_file()
    assert (traces.run_dir(tmp_path, "hello", 1, occurrence=2) / traces.TRACE_NAME).is_file()


def test_the_with_arm_names_the_run_directory_and_the_baseline_arm_is_under_it(
    tmp_path: Path,
) -> None:
    """One arm is the default, so its layout is the layout and a second arm is named."""
    assert (
        traces.run_dir(tmp_path, "python-version", 1)
        == tmp_path / "traces" / "python-version" / "run-1"
    )
    assert (
        traces.run_dir(tmp_path, "python-version", 1, arm="without")
        == tmp_path / "traces" / "python-version" / "without" / "run-1"
    )


def test_both_arms_are_collected_into_one_directory_each(tmp_path: Path) -> None:
    root = traces.sandbox_root(tmp_path)
    write_sandbox(root, "claude-eval-With")
    write_sandbox(root, "claude-eval-Without")
    write_two_arm(
        tmp_path,
        "python-version",
        with_runs=[run_entry(True, "claude-eval-With")],
        without=[run_entry(False, "claude-eval-Without")],
    )

    assert traces.collect(tmp_path) == []
    assert (traces.run_dir(tmp_path, "python-version", 1) / traces.TRACE_NAME).is_file()
    baseline = traces.run_dir(tmp_path, "python-version", 1, arm="without")
    assert (baseline / traces.TRACE_NAME).is_file()
    assert (baseline / traces.LAST_MESSAGE_NAME).is_file()
    assert (baseline / traces.WORKSPACE_NAME).is_dir()


def test_each_arm_gets_its_own_trace_path(tmp_path: Path) -> None:
    """A failure line about either arm names the directory holding that arm's transcript."""
    root = traces.sandbox_root(tmp_path)
    write_sandbox(root, "claude-eval-With")
    write_sandbox(root, "claude-eval-Without")
    write_two_arm(
        tmp_path,
        "python-version",
        with_runs=[run_entry(True, "claude-eval-With")],
        without=[run_entry(False, "claude-eval-Without")],
    )
    traces.collect(tmp_path)

    arms = collected(tmp_path).cases[0].arms
    assert Path(arms.with_[0].trace_path) == (
        traces.run_dir(tmp_path, "python-version", 1) / traces.TRACE_NAME
    )
    assert Path(arms.without[0].trace_path) == (
        traces.run_dir(tmp_path, "python-version", 1, arm="without") / traces.TRACE_NAME
    )


def test_a_one_arm_document_leaves_no_arm_directory(tmp_path: Path) -> None:
    """The layout almost every run produces is the one it had before the baseline arm."""
    write_sandbox(traces.sandbox_root(tmp_path))
    write_document(tmp_path, run_entry(True))

    assert traces.collect(tmp_path) == []
    assert sorted(child.name for child in (tmp_path / "traces" / "python-version").iterdir()) == [
        "run-1"
    ]


# The final message.


def test_the_final_message_is_the_result_record(tmp_path: Path) -> None:
    assert traces.last_message(write_trace(tmp_path)) == "Python 3.10.12"


def test_a_trace_with_no_result_record_falls_back_to_the_last_assistant_text(
    tmp_path: Path,
) -> None:
    """A run that ended before the harness wrote a result still said something."""
    records = [record for record in TRACE if record["type"] != "result"]
    assert traces.last_message(write_trace(tmp_path, records)) == "Python 3.10.12"


def test_a_thinking_block_is_not_the_final_message(tmp_path: Path) -> None:
    records = [{"type": "assistant", "message": {"content": [{"type": "thinking", "x": 1}]}}]
    assert traces.last_message(write_trace(tmp_path, records)) is None


def test_a_half_written_last_line_is_dropped_and_the_rest_is_read(tmp_path: Path) -> None:
    trace = write_trace(tmp_path)
    with trace.open("a", encoding="utf-8") as handle:
        handle.write('{"type": "assis')
    assert traces.last_message(trace) == "Python 3.10.12"


# Collecting.


def test_nothing_happens_when_no_sandbox_root_is_there(tmp_path: Path) -> None:
    """A run with the traces turned off creates none, and collection is then a no-op."""
    assert traces.collect(tmp_path) == []


def test_a_passing_run_keeps_its_trace_and_its_final_message(tmp_path: Path) -> None:
    write_sandbox(traces.sandbox_root(tmp_path))
    write_document(tmp_path, run_entry(passed=True))

    assert traces.collect(tmp_path) == []
    kept = traces.run_dir(tmp_path, "python-version", 1)
    assert (kept / traces.TRACE_NAME).is_file()
    assert (kept / traces.LAST_MESSAGE_NAME).read_text(encoding="utf-8") == "Python 3.10.12"


def test_a_run_keeps_the_same_three_artefacts_whether_it_passed_or_failed(
    tmp_path: Path,
) -> None:
    """A passing run is what a failing one is read against, so both keep the workspace."""
    root = traces.sandbox_root(tmp_path)
    write_sandbox(root, "claude-eval-One")
    write_sandbox(root, "claude-eval-Two")
    write_document(
        tmp_path, run_entry(True, "claude-eval-One"), run_entry(False, "claude-eval-Two")
    )

    assert traces.collect(tmp_path) == []
    for index in (1, 2):
        kept = traces.run_dir(tmp_path, "python-version", index)
        assert (kept / traces.TRACE_NAME).is_file()
        assert (kept / traces.LAST_MESSAGE_NAME).is_file()
        assert (kept / traces.WORKSPACE_NAME / "report.md").read_text(
            encoding="utf-8"
        ) == "what the agent wrote"


def test_every_run_of_a_case_gets_its_own_directory(tmp_path: Path) -> None:
    root = traces.sandbox_root(tmp_path)
    write_sandbox(root, "claude-eval-One")
    write_sandbox(root, "claude-eval-Two")
    write_document(
        tmp_path, run_entry(True, "claude-eval-One"), run_entry(False, "claude-eval-Two")
    )

    assert traces.collect(tmp_path) == []
    assert (traces.run_dir(tmp_path, "python-version", 1) / traces.TRACE_NAME).is_file()
    assert (traces.run_dir(tmp_path, "python-version", 2) / traces.TRACE_NAME).is_file()


def test_the_sandboxes_are_removed_however_they_were_sealed(tmp_path: Path) -> None:
    root = traces.sandbox_root(tmp_path)
    write_sandbox(root)
    write_sandbox(root, "claude-eval-Orphan")
    write_document(tmp_path, run_entry(passed=True))

    traces.collect(tmp_path)
    assert not root.exists(), "an unclaimed sandbox is removed with the rest of the root"


def test_the_trace_path_is_rewritten_to_where_the_trace_now_is(tmp_path: Path) -> None:
    """The one field that named the trace still names it, so the run can print it."""
    write_sandbox(traces.sandbox_root(tmp_path))
    write_document(tmp_path, run_entry(passed=False))

    traces.collect(tmp_path)
    written = collected(tmp_path).cases[0].arms.with_[0].trace_path
    assert Path(written) == traces.run_dir(tmp_path, "python-version", 1) / traces.TRACE_NAME
    assert Path(written).is_file()


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


def test_a_run_naming_no_sandbox_is_a_warning(tmp_path: Path) -> None:
    traces.sandbox_root(tmp_path).mkdir(parents=True)
    write_document(tmp_path, bare_run(False, trace_path="a-correlation-id"))

    warnings = traces.collect(tmp_path)
    assert warnings == [
        "python-version: run 1: tracePath names no kept sandbox: 'a-correlation-id'"
    ]


def test_a_sandbox_that_was_not_kept_is_a_warning(tmp_path: Path) -> None:
    traces.sandbox_root(tmp_path).mkdir(parents=True)
    write_document(tmp_path, run_entry(passed=True))

    warnings = traces.collect(tmp_path)
    assert len(warnings) == 1
    assert "was not kept" in warnings[0]


def test_a_sandbox_holding_no_workspace_is_a_warning(tmp_path: Path) -> None:
    """The trace is still kept: one artefact that is not there does not lose the others."""
    sandbox = write_sandbox(traces.sandbox_root(tmp_path))
    sandbox.chmod(0o700)
    (sandbox / traces.SANDBOX_SEALED).chmod(0o700)
    for child in (sandbox / traces.SANDBOX_SEALED / traces.SANDBOX_CWD).iterdir():
        child.unlink()
    (sandbox / traces.SANDBOX_SEALED / traces.SANDBOX_CWD).rmdir()
    write_document(tmp_path, run_entry(passed=True))

    warnings = traces.collect(tmp_path)
    assert len(warnings) == 1
    assert "no workspace to collect" in warnings[0]
    assert (traces.run_dir(tmp_path, "python-version", 1) / traces.TRACE_NAME).is_file()


# The CoWork backend. The same three names, out of a session directory instead of a sandbox.


def test_a_cowork_run_keeps_the_same_three_artefacts(tmp_path: Path) -> None:
    session = write_session(tmp_path / "profile")
    output = tmp_path / "logs"
    output.mkdir()
    write_document(output, session_entry(session))

    assert traces.collect(output) == []
    kept = traces.run_dir(output, "python-version", 1)
    assert (kept / traces.TRACE_NAME).is_file()
    assert (kept / traces.LAST_MESSAGE_NAME).read_text(encoding="utf-8") == "Python 3.10.12"
    assert (kept / traces.WORKSPACE_NAME / "report.md").read_text(
        encoding="utf-8"
    ) == "what the agent wrote"


def test_the_session_directory_is_copied_and_never_emptied(tmp_path: Path) -> None:
    """It is the account's own permanent record, and nothing here writes under the profile."""
    session = write_session(tmp_path / "profile")
    output = tmp_path / "logs"
    output.mkdir()
    write_document(output, session_entry(session))

    traces.collect(output)
    transcript = session / ".claude" / "projects" / "session" / "t-0001.jsonl"
    assert transcript.is_file(), "the transcript was moved out of the session"
    assert (session / "outputs" / "report.md").is_file(), "the produced files were moved"
    assert (session / "audit.jsonl").is_file()


def test_a_session_that_produced_no_file_is_not_a_warning(tmp_path: Path) -> None:
    """A session holds `outputs/` only once the run produced one, unlike a kept sandbox."""
    session = write_session(tmp_path / "profile", outputs=False)
    output = tmp_path / "logs"
    output.mkdir()
    write_document(output, session_entry(session))

    assert traces.collect(output) == []
    kept = traces.run_dir(output, "python-version", 1)
    assert (kept / traces.TRACE_NAME).is_file()
    assert not (kept / traces.WORKSPACE_NAME).exists()


def test_a_cowork_trace_path_is_rewritten_like_a_harness_one(tmp_path: Path) -> None:
    """The verdict then prints the same thing whichever backend produced the run."""
    session = write_session(tmp_path / "profile")
    output = tmp_path / "logs"
    output.mkdir()
    write_document(output, session_entry(session))

    traces.collect(output)
    written = collected(output).cases[0].arms.with_[0].trace_path
    assert Path(written) == traces.run_dir(output, "python-version", 1) / traces.TRACE_NAME
    assert collected(output).cases[0].arms.with_[0].cowork.session_dir == str(session), (
        "the session directory is still named"
    )


def test_a_run_that_reached_no_session_and_carries_an_error_says_nothing(tmp_path: Path) -> None:
    """The error already says why there is nothing to collect, and a second line is noise."""
    output = tmp_path / "logs"
    output.mkdir()
    write_document(
        output,
        bare_run(
            False,
            error="5: no session directory appeared",
            cowork=CoWorkRef(session_dir=None, timeout_seconds=1800.0),
        ),
    )
    assert traces.collect(output) == []


def test_a_run_that_reached_no_session_and_carries_no_error_warns(tmp_path: Path) -> None:
    output = tmp_path / "logs"
    output.mkdir()
    write_document(output, bare_run(True, cowork=CoWorkRef(timeout_seconds=1800.0)))

    assert traces.collect(output) == ["python-version: run 1: the run reached no session directory"]


def test_the_cowork_key_and_not_its_value_decides_the_backend(tmp_path: Path) -> None:
    """A run the driver could not start carries the key with a null `sessionDir`.

    Read as a harness run it would say its `tracePath` names no sandbox, which is a line
    about the wrong backend.
    """
    output = tmp_path / "logs"
    output.mkdir()
    write_document(output, bare_run(True, cowork=CoWorkRef(timeout_seconds=1800.0)))
    assert "sandbox" not in traces.collect(output)[0]


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


def init(tools: list[str] | None = None) -> dict:
    return {"type": "system", "subtype": "init", "tools": OFFERED if tools is None else tools}


def denial(tool: str, reason: str = "mode") -> dict:
    return {
        "type": "system",
        "subtype": "permission_denied",
        "tool_name": tool,
        "decision_reason_type": reason,
    }


def validity_run(tmp_path: Path, records: list[dict], granted: tuple[str, ...] = GRANT) -> RunEntry:
    """Collect one harness run over the given trace, and return its entry in the document."""
    output = tmp_path / "logs"
    output.mkdir()
    write_sandbox(traces.sandbox_root(output), trace=records)
    write_document(output, run_entry(True))

    assert traces.collect(output, granted=granted) == []
    return collected(output).cases[0].arms.with_[0]


def test_a_mode_denial_yields_the_tool_it_named(tmp_path: Path) -> None:
    """A session has no permission mode, so a mode denial is the container being unlike one."""
    entry = validity_run(tmp_path, [init(), denial("Write"), *TRACE[1:]])
    assert entry.denied_tools == ["Write"]


def test_two_mode_denials_yield_both_tools_once_each(tmp_path: Path) -> None:
    records = [init(), denial("Write"), denial("Edit"), denial("Write"), *TRACE[1:]]
    assert validity_run(tmp_path, records).denied_tools == ["Write", "Edit"]


def test_a_hook_denial_yields_nothing(tmp_path: Path) -> None:
    """A hook denial is the plugin's own behaviour, which a case testing a hook asserts over."""
    entry = validity_run(tmp_path, [init(), denial("Write", "hook"), *TRACE[1:]])
    assert entry.denied_tools is None


def test_the_denial_reason_and_never_the_tool_name_decides(tmp_path: Path) -> None:
    """A tool no grader names still broke the run, so the rule cannot narrow to named tools."""
    records = [init(), denial("mcp__plugin_acme_jira__create_issue"), *TRACE[1:]]
    assert validity_run(tmp_path, records).denied_tools == ["mcp__plugin_acme_jira__create_issue"]


def test_a_granted_tool_missing_from_the_offered_list_is_named(tmp_path: Path) -> None:
    offered = [tool for tool in OFFERED if tool != "Bash"]
    entry = validity_run(tmp_path, [init(offered), *TRACE[1:]])
    assert entry.unoffered_tools == ["Bash"]


def test_an_offered_list_carrying_every_granted_tool_yields_nothing(tmp_path: Path) -> None:
    assert validity_run(tmp_path, [init(), *TRACE[1:]]).unoffered_tools is None


def test_a_grant_and_an_offer_are_compared_before_the_bracket(tmp_path: Path) -> None:
    """A grant may carry a pattern, and a read reaches the child path-scoped."""
    offered = ["WebFetch", "Read(//home/**)", "Skill"]
    granted = ("WebFetch(domain:example.com)", "Read", "Skill")
    entry = validity_run(tmp_path, [init(offered), *TRACE[1:]], granted)
    assert entry.unoffered_tools is None


def test_a_trace_with_no_init_record_yields_nothing(tmp_path: Path) -> None:
    """A run that wrote no tool list says nothing about what it had."""
    entry = validity_run(tmp_path, [record for record in TRACE if record["type"] != "system"])
    assert entry.unoffered_tools is None


def test_an_empty_grant_names_nothing(tmp_path: Path) -> None:
    """The CoWork backend passes none, and nothing to compare is not a failure."""
    assert validity_run(tmp_path, [init(), *TRACE[1:]], ()).unoffered_tools is None


def test_a_healthy_run_carries_neither_field(tmp_path: Path) -> None:
    entry = validity_run(tmp_path, [init(), *TRACE[1:]])
    assert entry.denied_tools is None
    assert entry.unoffered_tools is None


def test_a_cowork_run_carries_neither_field(tmp_path: Path) -> None:
    """A session has no permission mode and writes no tool list, so neither check applies."""
    session = write_session(tmp_path / "profile")
    output = tmp_path / "logs"
    output.mkdir()
    write_document(output, session_entry(session))

    assert traces.collect(output, granted=GRANT) == []
    entry = collected(output).cases[0].arms.with_[0]
    assert entry.denied_tools is None
    assert entry.unoffered_tools is None


def test_the_final_message_is_still_written_beside_the_checks(tmp_path: Path) -> None:
    """One read answers the message and both checks, so neither costs the other."""
    output = tmp_path / "logs"
    output.mkdir()
    write_sandbox(traces.sandbox_root(output), trace=[init(), denial("Write"), *TRACE[1:]])
    write_document(output, run_entry(True))

    assert traces.collect(output, granted=GRANT) == []
    kept = traces.run_dir(output, "python-version", 1)
    assert (kept / traces.LAST_MESSAGE_NAME).read_text(encoding="utf-8") == "Python 3.10.12"
