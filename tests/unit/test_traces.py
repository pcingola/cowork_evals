"""What is kept out of a run, over hand-written sandboxes and session directories on disk.

Every source here is written by the test: a harness sandbox in the layout
docs/claude_code/plugin_eval_reference.md records, and a CoWork session directory in the
layout docs/cowork_desktop.md records. The collector that reads either is the real one.
Nothing here runs a container or a session. See ../README.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from cowork_evals import traces
from cowork_evals.harness import RESULT_NAME

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


def session_entry(session: Path, *, passed: bool = True, error: str | None = None) -> dict:
    """One CoWork run of the document, as results.py writes it."""
    return {
        "passed": passed,
        "error": error,
        "tracePath": str(session / ".claude" / "projects" / "session" / "t-0001.jsonl"),
        "cowork": {"sessionDir": str(session), "timeoutSeconds": 1800.0},
    }


def write_document(output_dir: Path, *runs: dict) -> Path:
    """A result document naming one case whose runs are the ones given."""
    return write_cases(output_dir, ("python-version", list(runs)))


def write_cases(output_dir: Path, *cases: tuple[str, list[dict]]) -> Path:
    """A result document of several cases, each with its own runs."""
    document = {
        "schemaVersion": 1,
        "cases": [{"name": name, "arms": {"with": runs}} for name, runs in cases],
    }
    path = output_dir / RESULT_NAME
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def run_entry(passed: bool, name: str = SANDBOX) -> dict:
    """One run of the document, with the container-side `tracePath` the harness writes."""
    return {
        "passed": passed,
        "tracePath": f"/work/logs/{traces.SANDBOX_DIR}/{name}/"
        f"{traces.SANDBOX_OUT}/{traces.SANDBOX_TRACE}",
    }


def collected(output_dir: Path) -> dict:
    return json.loads((output_dir / RESULT_NAME).read_text(encoding="utf-8"))


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
    """The one field that named the trace still names it, so the gate can print it."""
    write_sandbox(traces.sandbox_root(tmp_path))
    write_document(tmp_path, run_entry(passed=False))

    traces.collect(tmp_path)
    written = collected(tmp_path)["cases"][0]["arms"]["with"][0]["tracePath"]
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
    write_document(tmp_path, {"passed": False, "tracePath": "a-correlation-id"})

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
    """The gate then prints the same thing whichever backend produced the run."""
    session = write_session(tmp_path / "profile")
    output = tmp_path / "logs"
    output.mkdir()
    write_document(output, session_entry(session))

    traces.collect(output)
    written = collected(output)["cases"][0]["arms"]["with"][0]["tracePath"]
    assert Path(written) == traces.run_dir(output, "python-version", 1) / traces.TRACE_NAME
    assert collected(output)["cases"][0]["arms"]["with"][0]["cowork"]["sessionDir"] == str(
        session
    ), "the session directory is still named"


def test_a_run_that_reached_no_session_and_carries_an_error_says_nothing(tmp_path: Path) -> None:
    """The error already says why there is nothing to collect, and a second line is noise."""
    output = tmp_path / "logs"
    output.mkdir()
    write_document(
        output,
        {
            "passed": False,
            "error": "5: no session directory appeared",
            "cowork": {"sessionDir": None, "timeoutSeconds": 1800.0},
        },
    )
    assert traces.collect(output) == []


def test_a_run_that_reached_no_session_and_carries_no_error_warns(tmp_path: Path) -> None:
    output = tmp_path / "logs"
    output.mkdir()
    write_document(output, {"passed": True, "cowork": {"sessionDir": None}})

    assert traces.collect(output) == ["python-version: run 1: the run reached no session directory"]


def test_the_cowork_key_and_not_its_value_decides_the_backend(tmp_path: Path) -> None:
    """A run the driver could not start carries the key with a null `sessionDir`.

    Read as a harness run it would say its `tracePath` names no sandbox, which is a line
    about the wrong backend.
    """
    output = tmp_path / "logs"
    output.mkdir()
    write_document(output, {"passed": True, "cowork": {"sessionDir": None}})
    assert "sandbox" not in traces.collect(output)[0]
