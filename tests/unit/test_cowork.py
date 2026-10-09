"""The driver reads a session as docs/cowork_driver_internals.md says it does.

Every assertion is over a hand-written session directory, under tests/data/cowork/ or under
tmp_path. No test here starts a CoWork session. The tests that read a real profile are in
tests/integration/. See ../README.md.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from cowork_evals import CoWork, CoWorkError, CoWorkSection
from cowork_evals import cowork as driver_module
from cowork_evals.config import CONFIG_FILENAME, CONSENT_DIALOG, CONSENT_NONE
from cowork_evals.cowork import SessionDocument, Turn

ROOT = Path(__file__).resolve().parent.parent / "data" / "cowork" / "sessions"
PROFILE = ROOT / "acct0000" / "prof0000"
REPOSITORY = Path(__file__).resolve().parents[2]

# One row of the failure taxonomy in docs/cowork_driver.md: a code and what it means.
TAXONOMY_ROW = re.compile(r"^\| (\d+) +\| (.+?) +\|$", re.MULTILINE)


@pytest.fixture
def driver() -> CoWork:
    """A driver with no profile, which is what an archived session is read with."""
    return CoWork(CoWorkSection())


@pytest.fixture(autouse=True)
def transcript_ages() -> None:
    """Order the two tool_call transcripts by modification time.

    git does not carry modification times, so the fixture's ordering is set here rather
    than left to checkout order.
    """
    session = PROFILE / "tool_call" / ".claude" / "projects" / "session"
    os.utime(session / "t-0002-old.jsonl", (1_800_000_000, 1_800_000_000))
    os.utime(session / "t-0002-new.jsonl", (1_800_000_100, 1_800_000_100))


def test_sessions_finds_every_session_and_nothing_else(driver: CoWork) -> None:
    found = driver.sessions(ROOT)
    assert [path.name for path in found] == [
        "no_output",
        "no_transcript",
        "one_turn",
        "partial_line",
        "subagent",
        "tool_call",
    ]
    assert all(path.parent.parent.parent == ROOT for path in found)


def test_sessions_on_an_absent_root_is_empty(driver: CoWork, tmp_path: Path) -> None:
    assert driver.sessions(tmp_path / "absent") == []


def test_sessions_defaults_to_the_configured_root() -> None:
    """A driver with no profile refuses at the call that needs one, not at construction."""
    driver = CoWork(CoWorkSection())
    with pytest.raises(CoWorkError) as raised:
        driver.sessions()
    assert raised.value.code == 2


def test_the_session_document_carries_exactly_the_documented_keys(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "one_turn")
    assert SessionDocument.model_validate_json(document.model_dump_json()) == document


def test_the_session_document_is_json_serializable_with_no_profile(driver: CoWork) -> None:
    assert driver.config.profile is None
    text = driver.collect(PROFILE / "one_turn").model_dump_json()
    assert json.loads(text)["final_text"] == "PONG"


def test_a_one_turn_session(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "one_turn")
    assert document.prompt == "Reply with exactly: PONG"
    assert document.audit_prompt == "Reply with exactly: PONG"
    assert document.prompt_sha256 == (
        "0fb5aed1b51b28b04409b7963b2453fe1597d198c3b8396fc8ebd072104511de"
    )
    assert document.submitted_at == "2026-09-08T10:00:00.000Z"
    assert document.lifecycle == ["queued", "started", "completed"]
    assert document.turns == [
        Turn(role="user", text="Reply with exactly: PONG"),
        Turn(role="assistant", text="PONG"),
    ]
    assert document.final_text == "PONG"
    assert document.tool_calls == []
    assert document.tool_names == []
    assert document.outputs == ["outputs/marker.txt"]
    assert document.other_transcripts == []
    assert document.subagent_transcripts == []
    assert document.log_file is None


def test_a_thinking_block_is_not_turn_text(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "one_turn")
    assert "the marker is PONG" not in document.model_dump_json(include={"turns"})


def test_the_main_transcript_is_the_newest_top_level_file(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "tool_call")
    assert Path(document.transcript).name == "t-0002-new.jsonl"
    assert [Path(p).name for p in document.other_transcripts] == ["t-0002-old.jsonl"]
    assert "an earlier run" not in document.model_dump_json(include={"turns"})


def test_a_tool_result_pairs_by_id_and_not_by_position(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "tool_call")
    calls = {call.id: call for call in document.tool_calls}
    assert set(calls) == {"call-a", "call-b"}
    assert calls["call-a"].input == {"command": "cat /etc/os-release"}
    assert calls["call-a"].result == 'NAME="Ubuntu"'
    assert calls["call-b"].input == {"command": "uname -r"}
    assert calls["call-b"].result == "6.8.0-136-generic"
    assert document.tool_names == ["mcp__workspace__bash", "mcp__workspace__bash"]


def test_a_tool_call_carries_its_mcp_attribution(driver: CoWork) -> None:
    call = driver.collect(PROFILE / "tool_call").tool_calls[0]
    assert call.mcp_server == "workspace"
    assert call.mcp_tool == "bash"
    assert call.timestamp == "2026-09-08T11:00:05.000Z"


def test_an_orphan_tool_result_is_dropped(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "tool_call")
    assert "belongs to a subagent" not in document.model_dump_json(include={"tool_calls"})


def test_string_content_is_read_as_turn_text(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "tool_call")
    assert document.final_text == "The guest kernel is 6.8.0-136-generic."


def test_a_subagent_transcript_is_recorded_and_never_merged(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "subagent")
    assert [Path(p).name for p in document.subagent_transcripts] == ["agent-0001.jsonl"]
    assert document.other_transcripts == []
    assert document.final_text == "There are three notes, all about the mirror."
    assert "Read every note" not in document.model_dump_json(include={"turns"})


def test_a_truncated_tail_keeps_the_records_before_it(driver: CoWork) -> None:
    """Both fixture files end mid-record, which is what a file being appended looks like."""
    document = driver.collect(PROFILE / "partial_line")
    assert document.lifecycle == ["queued", "started"]
    assert document.final_text == "Ubuntu 22.04.5 LTS"


def test_a_session_with_no_assistant_output_raises_code_8(driver: CoWork) -> None:
    with pytest.raises(CoWorkError) as raised:
        driver.collect(PROFILE / "no_output")
    assert raised.value.code == 8
    assert raised.value.session_dir == PROFILE / "no_output"


def test_a_session_with_no_transcript_directory_raises_code_8(driver: CoWork) -> None:
    with pytest.raises(CoWorkError) as raised:
        driver.collect(PROFILE / "no_transcript")
    assert raised.value.code == 8


def test_a_known_prompt_beats_the_audit_record(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "one_turn", prompt="what the caller submitted")
    assert document.prompt == "what the caller submitted"
    assert document.audit_prompt == "Reply with exactly: PONG"


def test_a_constructor_override_beats_the_configuration() -> None:
    driver = CoWork(CoWorkSection(profile="Fixture"), max_runs=3)
    assert driver.config.max_runs == 3
    assert driver.config.profile == "Fixture"


def test_an_unknown_constructor_override_raises() -> None:
    with pytest.raises(CoWorkError) as raised:
        CoWork(CoWorkSection(), nonsense=1)
    assert raised.value.code == 2


def test_from_file_reads_the_named_file_and_not_the_working_directory(
    working_directory, tmp_path: Path
) -> None:
    named = tmp_path / "other.yaml"
    named.write_text("cowork:\n  profile: Named\n  max_runs: 7\n", encoding="utf-8")
    (tmp_path / CONFIG_FILENAME).write_text("cowork:\n  profile: Working\n", encoding="utf-8")
    with working_directory(tmp_path):
        driver = CoWork.from_file(named)
    assert driver.config.profile == "Named"
    assert driver.config.max_runs == 7


def test_from_file_takes_the_same_overrides_as_the_constructor(tmp_path: Path) -> None:
    named = tmp_path / "other.yaml"
    named.write_text("cowork:\n  profile: Named\n  max_runs: 7\n", encoding="utf-8")
    driver = CoWork.from_file(named, max_runs=3)
    assert driver.config.profile == "Named"
    assert driver.config.max_runs == 3


def test_from_file_refuses_a_path_that_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(CoWorkError) as raised:
        CoWork.from_file(tmp_path / "absent.yaml")
    assert raised.value.code == 2


# The run log, the rate ceiling and the diagnostic log.


def build(tmp_path: Path, **overrides: object) -> CoWork:
    """A driver over a temporary profile, run log and log directory."""
    profile = tmp_path / "profile"
    (profile / "local-agent-mode-sessions").mkdir(parents=True, exist_ok=True)
    values: dict[str, object] = {
        "profile": str(profile),
        "run_log": str(tmp_path / "runs.jsonl"),
        "log_dir": str(tmp_path / "logs"),
    }
    values.update(overrides)
    return CoWork(CoWorkSection(**values))  # type: ignore[arg-type]


def test_an_unset_profile_is_refused_before_anything_fires(tmp_path: Path) -> None:
    driver = CoWork(CoWorkSection(run_log=tmp_path / "runs.jsonl"))
    with pytest.raises(CoWorkError) as raised:
        driver._check("Reply with exactly: PONG")
    assert raised.value.code == 2
    assert driver.history() == []


def test_an_unreadable_profile_is_refused(tmp_path: Path) -> None:
    driver = CoWork(
        CoWorkSection(profile=str(tmp_path / "absent"), run_log=tmp_path / "runs.jsonl")
    )
    with pytest.raises(CoWorkError) as raised:
        driver._check("Reply with exactly: PONG")
    assert raised.value.code == 2


def test_a_prompt_above_the_cap_is_refused(tmp_path: Path) -> None:
    driver = build(tmp_path)
    with pytest.raises(CoWorkError) as raised:
        driver._check("x" * 14337)
    assert raised.value.code == 2
    assert "14336" in str(raised.value)


def test_a_prompt_at_the_cap_is_allowed(tmp_path: Path) -> None:
    build(tmp_path)._check("x" * 14336)


def test_the_rate_ceiling_is_refused(tmp_path: Path) -> None:
    driver = build(tmp_path, max_runs=3)
    for _ in range(3):
        driver._record("Reply with exactly: PONG", None, "submitted")
    with pytest.raises(CoWorkError) as raised:
        driver._check("Reply with exactly: PONG")
    assert raised.value.code == 2
    assert "rate ceiling" in str(raised.value)


def test_the_ceiling_counts_only_the_trailing_24_hours(tmp_path: Path) -> None:
    driver = build(tmp_path, max_runs=2)
    old = {
        "timestamp": "2020-01-01T00:00:00+00:00",
        "prompt_sha256": "0" * 64,
        "session_dir": None,
        "outcome": "submitted",
    }
    driver.config.run_log.write_text(json.dumps(old) + "\n", encoding="utf-8")
    driver._record("Reply with exactly: PONG", None, "submitted")
    driver._check("Reply with exactly: PONG")


def test_a_failed_submission_leaves_a_line_history_reads_back(tmp_path: Path) -> None:
    driver = build(tmp_path)
    driver._record("first", None, "failed:4")
    driver._record("second", tmp_path / "session", "submitted")
    entries = driver.history()
    assert [entry.outcome for entry in entries] == ["failed:4", "submitted"]
    assert entries[0].session_dir is None
    assert entries[1].session_dir == str(tmp_path / "session")
    assert set(entries[0].model_dump()) == {"timestamp", "prompt_sha256", "session_dir", "outcome"}


def test_history_reads_a_named_run_log(tmp_path: Path) -> None:
    other = tmp_path / "other.jsonl"
    line = '{"timestamp":"2026-09-08T10:00:00+00:00","prompt_sha256":"%s","session_dir":null,'
    other.write_text(line % ("0" * 64) + '"outcome":"submitted"}\n{"outcome":"fail\n', "utf-8")
    assert [entry.outcome for entry in build(tmp_path).history(other)] == ["submitted"]


def test_history_of_an_absent_run_log_is_empty(tmp_path: Path) -> None:
    assert build(tmp_path).history() == []


def test_two_calls_leave_two_log_files_and_no_duplicated_handler(tmp_path: Path) -> None:
    from cowork_evals.cowork import LOGGER

    driver = build(tmp_path)
    before = len(LOGGER.handlers)
    paths = []
    for _ in range(2):
        with driver._diagnostics() as path:
            assert len(LOGGER.handlers) == before + 1
            paths.append(path)
    assert len(LOGGER.handlers) == before
    assert paths[0] != paths[1]
    assert all(path is not None and path.is_file() for path in paths)
    assert sorted(p.name for p in (tmp_path / "logs").iterdir()) == sorted(p.name for p in paths)


def test_the_handler_is_closed_when_the_call_raises(tmp_path: Path) -> None:
    from cowork_evals.cowork import LOGGER

    driver = build(tmp_path)
    before = len(LOGGER.handlers)
    with pytest.raises(RuntimeError), driver._diagnostics():
        raise RuntimeError("the call failed")
    assert len(LOGGER.handlers) == before


def test_log_dir_null_writes_no_file(tmp_path: Path) -> None:
    from cowork_evals.cowork import LOGGER

    driver = build(tmp_path, log_dir=None)
    before = len(LOGGER.handlers)
    with driver._diagnostics() as path:
        assert path is None
        assert len(LOGGER.handlers) == before
    assert not (tmp_path / "logs").exists()


def test_the_session_document_names_the_diagnostic_log(tmp_path: Path) -> None:
    driver = build(tmp_path)
    with driver._diagnostics() as path:
        document = driver.collect(PROFILE / "one_turn")
    assert document.log_file == str(path)
    assert driver.collect(PROFILE / "one_turn").log_file is None


# Submitting. No stand-in for the application: a test writes the session directories the
# application would have written, then calls the step that reads them. The three things
# that cannot be proved that way are proved by the live test at the end of this file.


def write_session(
    root: Path,
    name: str,
    prompt: str | None = "Reply with exactly: PONG",
    states: tuple[str, ...] = ("queued", "started", "completed"),
    final: str | None = "PONG",
) -> Path:
    """One hand-written session directory, three levels below a root."""
    session = root / "acct" / "prof" / name
    session.mkdir(parents=True, exist_ok=True)
    lines: list[dict[str, object]] = []
    if prompt is not None:
        lines.append(
            {
                "type": "user",
                "session_id": name,
                "timestamp": "2026-09-08T16:00:00.000Z",
                "message": {"role": "user", "content": prompt},
            }
        )
    lines += [{"type": "command_lifecycle", "command_uuid": name, "state": s} for s in states]
    (session / "audit.jsonl").write_text(
        "".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8"
    )
    if final is not None:
        transcripts = session / ".claude" / "projects" / "session"
        transcripts.mkdir(parents=True, exist_ok=True)
        (transcripts / f"{name}.jsonl").write_text(
            json.dumps(
                {
                    "type": "assistant",
                    "timestamp": "2026-09-08T16:00:30.000Z",
                    "message": {"role": "assistant", "content": [{"type": "text", "text": final}]},
                }
            )
            + "\n",
            encoding="utf-8",
        )
    return session


def sessions_root(tmp_path: Path) -> Path:
    return tmp_path / "profile" / "local-agent-mode-sessions"


def stepping(tmp_path: Path, **overrides: object) -> CoWork:
    """A driver whose timeouts are zero, so a poll runs one pass and does not sleep."""
    return build(tmp_path, settle_seconds=0, session_timeout=0, idle_seconds=0, **overrides)


def test_deep_link_percent_encodes_the_prompt() -> None:
    driver = CoWork(CoWorkSection())
    assert driver.deep_link("two words\nand a line") == (
        "claude://claude.ai/new?q=two%20words%0Aand%20a%20line&surface=cowork"
    )


def test_deep_link_omits_an_empty_surface() -> None:
    assert CoWork(CoWorkSection(surface="")).deep_link("PING") == "claude://claude.ai/new?q=PING"


def test_no_session_directory_raises_code_4(tmp_path: Path) -> None:
    driver = stepping(tmp_path)
    with pytest.raises(CoWorkError) as raised:
        driver._discover(sessions_root(tmp_path), set())
    assert raised.value.code == 4


def test_one_new_session_directory_is_discovered(tmp_path: Path) -> None:
    root = sessions_root(tmp_path)
    driver = stepping(tmp_path)
    baseline = set(driver.sessions(root))
    session = write_session(root, "s1")
    assert driver._discover(root, baseline) == session


def test_two_new_session_directories_raise_code_5(tmp_path: Path) -> None:
    root = sessions_root(tmp_path)
    driver = stepping(tmp_path)
    baseline = set(driver.sessions(root))
    write_session(root, "s1")
    write_session(root, "s2")
    with pytest.raises(CoWorkError) as raised:
        driver._discover(root, baseline)
    assert raised.value.code == 5


def test_a_session_already_in_the_baseline_is_not_discovered(tmp_path: Path) -> None:
    root = sessions_root(tmp_path)
    driver = stepping(tmp_path)
    write_session(root, "before")
    baseline = set(driver.sessions(root))
    after = write_session(root, "after")
    assert driver._discover(root, baseline) == after


def test_a_matching_audit_prompt_attributes_the_session(tmp_path: Path) -> None:
    session = write_session(sessions_root(tmp_path), "s1")
    stepping(tmp_path)._attribute(session, "Reply with exactly: PONG")


def test_a_mismatched_audit_prompt_raises_code_6(tmp_path: Path) -> None:
    session = write_session(sessions_root(tmp_path), "s1", prompt="someone else's prompt")
    with pytest.raises(CoWorkError) as raised:
        stepping(tmp_path)._attribute(session, "Reply with exactly: PONG")
    assert raised.value.code == 6
    assert raised.value.session_dir == session


def test_a_session_with_no_user_record_raises_code_6(tmp_path: Path) -> None:
    session = write_session(sessions_root(tmp_path), "s1", prompt=None)
    with pytest.raises(CoWorkError) as raised:
        stepping(tmp_path)._attribute(session, "Reply with exactly: PONG")
    assert raised.value.code == 6


def test_wait_returns_on_the_terminal_lifecycle_state(tmp_path: Path) -> None:
    session = write_session(sessions_root(tmp_path), "s1")
    driver = stepping(tmp_path, run_timeout=0)
    assert driver.wait(session) == session


def test_quiescence_does_not_fire_before_the_run_has_started(tmp_path: Path) -> None:
    session = write_session(sessions_root(tmp_path), "s1", states=("queued",), final=None)
    driver = stepping(tmp_path, run_timeout=0)
    with pytest.raises(CoWorkError) as raised:
        driver.wait(session)
    assert raised.value.code == 7
    assert raised.value.session_dir == session


def test_quiescence_fires_once_the_run_has_started(tmp_path: Path) -> None:
    session = write_session(sessions_root(tmp_path), "s1", states=("queued", "started"))
    driver = stepping(tmp_path, run_timeout=5)
    assert driver.wait(session) == session


def test_a_run_timeout_reaches_the_diagnostic_log(tmp_path: Path) -> None:
    """`run` raises code 7 from inside the log it opened, so the log has to name it."""
    session = write_session(sessions_root(tmp_path), "s1", states=("queued",), final=None)
    driver = stepping(tmp_path, run_timeout=0)
    # The raise has to leave the context manager, which is how `run` reaches it.
    with pytest.raises(CoWorkError) as raised, driver._diagnostics() as path:
        log = path
        driver.wait(session)
    assert raised.value.code == 7
    assert log is not None
    assert "the call failed with code 7" in log.read_text(encoding="utf-8")


def test_a_refusal_before_firing_leaves_no_run_log_line(tmp_path: Path) -> None:
    driver = stepping(tmp_path)
    with pytest.raises(CoWorkError) as raised:
        driver.submit("x" * 14337)
    assert raised.value.code == 2
    assert driver.history() == []


# Consent, and the taxonomy the guard added. docs/cowork_driver.md.
#
# Nothing in the unit tier ever grants consent, so the module flag is false throughout it.
# Granting it means showing a modal, and no test here drives the desktop. A test here may
# call `_consented` under `consent: none`, and may never call `run` or `submit` without it:
# the driver asks at step 2a, so a submission under `consent: dialog` opens a real modal.


def test_consent_none_shows_nothing_and_leaves_the_module_flag_alone(tmp_path: Path) -> None:
    """`consent: none` is a configuration value a consumer sets, not an injected answer."""
    driver_module.consent(CoWorkSection(consent=CONSENT_NONE))
    assert driver_module._CONSENTED is False
    build(tmp_path, consent=CONSENT_NONE)._consented()


def test_reading_a_session_never_asks_for_consent(driver: CoWork, tmp_path: Path) -> None:
    """`collect` and `deep_link` fire nothing, so `consent: dialog` does not reach them."""
    assert driver.config.consent == CONSENT_DIALOG
    assert driver.collect(PROFILE / "one_turn").final_text == "PONG"
    assert driver.deep_link("PING") == "claude://claude.ai/new?q=PING&surface=cowork"

    reading = build(tmp_path)
    assert reading.config.consent == CONSENT_DIALOG
    assert reading.sessions() == []
    assert reading.history() == []
    assert reading.recent() == 0


def test_code_9_is_its_own_row_of_the_taxonomy_and_is_not_code_3() -> None:
    """The taxonomy is a table in docs/cowork_driver.md, and a grading layer reads it.

    A refusal to type is not a broken `osascript`. Collapsing the two is what this catches,
    and the table is where a collapse would happen: the driver raises one code per site, and
    a reader above it has only the document to tell them apart.
    """
    text = (REPOSITORY / "docs" / "cowork_driver.md").read_text(encoding="utf-8")
    section = text.split("## Failure taxonomy", 1)[1].split("\n## ", 1)[0]
    rows = dict(TAXONOMY_ROW.findall(section))
    assert sorted(rows) == ["2", "3", "4", "5", "6", "7", "8", "9"]
    assert len(set(rows.values())) == len(rows)
    assert "osascript" in rows["3"]
    assert "frontmost" in rows["9"]


def test_recent_counts_the_trailing_24_hours_of_a_hand_written_run_log(tmp_path: Path) -> None:
    """The CoWork backend calls this rather than re-deriving the window over `history()`."""
    driver = build(tmp_path)
    old = {
        "timestamp": "2020-01-01T00:00:00+00:00",
        "prompt_sha256": "0" * 64,
        "session_dir": None,
        "outcome": "submitted",
    }
    driver.config.run_log.write_text(json.dumps(old) + "\n", encoding="utf-8")
    assert driver.recent() == 0
    driver._record("Reply with exactly: PONG", None, "submitted")
    driver._record("Reply with exactly: PONG", None, "failed:4")
    assert driver.recent() == 2, "a failed submission counts too"
