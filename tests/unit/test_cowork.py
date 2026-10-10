"""The driver reads a session as docs/cowork_driver_internals.md says it does.

Every assertion is over a hand-written session directory, under tests/data/cowork/ or under
tmp_path. No test here starts a CoWork session. The tests that read a real profile are in
tests/integration/. See ../README.md.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cowork_evals import CoWork, CoWorkError, CoWorkSection
from cowork_evals.config import CONFIG_FILENAME, CONSENT_DIALOG, CONSENT_NONE
from cowork_evals.cowork import LOGGER, RunLogEntry, SessionDocument, ToolCall, Turn, consent

ROOT = Path(__file__).resolve().parent.parent / "data" / "cowork" / "sessions"
PROFILE = ROOT / "acct0000" / "prof0000"
PONG = "Reply with exactly: PONG"


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
        "mismatched_prompt",
        "no_output",
        "no_transcript",
        "no_user_record",
        "one_turn",
        "partial_line",
        "subagent",
        "tool_call",
    ]
    assert all(path.parent.parent.parent == ROOT for path in found)


def test_the_session_document_survives_its_own_json(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "one_turn")
    assert SessionDocument.model_validate_json(document.model_dump_json()) == document


def test_a_one_turn_session(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "one_turn")
    assert document.prompt == PONG
    assert document.audit_prompt == PONG
    assert document.prompt_sha256 == (
        "0fb5aed1b51b28b04409b7963b2453fe1597d198c3b8396fc8ebd072104511de"
    )
    assert document.submitted_at == "2026-09-08T10:00:00.000Z"
    assert document.lifecycle == ["queued", "started", "completed"]
    assert document.turns == [Turn(role="user", text=PONG), Turn(role="assistant", text="PONG")]
    assert document.final_text == "PONG"
    assert document.tool_calls == []
    assert document.tool_names == []
    assert document.outputs == ["outputs/marker.txt"]
    assert document.other_transcripts == []
    assert document.subagent_transcripts == []
    assert document.log_file is None


def test_the_main_transcript_is_the_newest_top_level_file(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "tool_call")
    assert Path(document.transcript or "").name == "t-0002-new.jsonl"
    assert [Path(p).name for p in document.other_transcripts] == ["t-0002-old.jsonl"]
    assert document.turns == [
        Turn(role="user", text="Report the guest kernel version"),
        Turn(role="assistant", text="The guest kernel is 6.8.0-136-generic."),
    ]


def test_a_tool_result_pairs_by_id_and_an_orphan_is_dropped(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "tool_call")
    bash = {"name": "mcp__workspace__bash", "mcp_server": "workspace", "mcp_tool": "bash"}
    stamp = "2026-09-08T11:00:05.000Z"
    assert document.tool_calls == [
        ToolCall(
            id="call-b",
            input={"command": "uname -r"},
            timestamp=stamp,
            result="6.8.0-136-generic",
            **bash,
        ),
        ToolCall(
            id="call-a",
            input={"command": "cat /etc/os-release"},
            timestamp=stamp,
            result='NAME="Ubuntu"',
            **bash,
        ),
    ]
    assert document.tool_names == ["mcp__workspace__bash", "mcp__workspace__bash"]


def test_string_content_is_read_as_turn_text(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "tool_call")
    assert document.final_text == "The guest kernel is 6.8.0-136-generic."


def test_a_subagent_transcript_is_recorded_and_never_merged(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "subagent")
    assert [Path(p).name for p in document.subagent_transcripts] == ["agent-0001.jsonl"]
    assert document.other_transcripts == []
    assert document.turns == [
        Turn(role="user", text="Summarize the notes"),
        Turn(role="assistant", text="There are three notes, all about the mirror."),
    ]


def test_a_truncated_tail_keeps_the_records_before_it(driver: CoWork) -> None:
    """Both fixture files end mid-record, which is what a file being appended looks like."""
    document = driver.collect(PROFILE / "partial_line")
    assert document.lifecycle == ["queued", "started"]
    assert document.final_text == "Ubuntu 22.04.5 LTS"


@pytest.mark.parametrize("name", ["no_output", "no_transcript"])
def test_a_session_with_no_assistant_output_raises_code_8(driver: CoWork, name: str) -> None:
    with pytest.raises(CoWorkError) as raised:
        driver.collect(PROFILE / name)
    assert raised.value.code == 8
    assert raised.value.session_dir == PROFILE / name


def test_a_known_prompt_beats_the_audit_record(driver: CoWork) -> None:
    document = driver.collect(PROFILE / "one_turn", prompt="what the caller submitted")
    assert document.prompt == "what the caller submitted"
    assert document.prompt_sha256 == (
        "e4fd7516014befa66f4f223be49167c5ee1923cc968b9a5846fdb93eb589c30e"
    )
    assert document.audit_prompt == PONG


def test_an_unknown_constructor_override_raises() -> None:
    with pytest.raises(CoWorkError) as raised:
        CoWork(CoWorkSection(), nonsense=1)
    assert raised.value.code == 2


def test_from_file_reads_the_named_file_and_an_override_beats_it(
    working_directory, tmp_path: Path
) -> None:
    named = tmp_path / "other.yaml"
    named.write_text("cowork:\n  profile: Named\n  max_runs: 7\n", encoding="utf-8")
    (tmp_path / CONFIG_FILENAME).write_text("cowork:\n  profile: Working\n", encoding="utf-8")
    with working_directory(tmp_path):
        driver = CoWork.from_file(named, max_runs=3)
    assert driver.config.profile == "Named"
    assert driver.config.max_runs == 3


# The run log, the rate ceiling and the diagnostic log.


def build(tmp_path: Path, **overrides: object) -> CoWork:
    """A driver over a temporary profile, run log and log directory.

    `consent: none`, because a unit test never calls `submit` without it. See ../README.md.
    """
    profile = tmp_path / "profile"
    (profile / "local-agent-mode-sessions").mkdir(parents=True, exist_ok=True)
    section = CoWorkSection(
        profile=str(profile),
        run_log=tmp_path / "runs.jsonl",
        log_dir=tmp_path / "logs",
        consent=CONSENT_NONE,
    )
    return CoWork(dataclasses.replace(section, **overrides))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("profile", "prompt", "logged"),
    [
        pytest.param(None, PONG, 0, id="unset-profile"),
        pytest.param("absent", PONG, 0, id="unreadable-profile"),
        pytest.param("profile", "x" * 14337, 0, id="over-the-cap"),
        pytest.param("profile", PONG, 3, id="ceiling-reached"),
    ],
)
def test_a_refusal_fires_nothing_and_leaves_no_run_log_line(
    tmp_path: Path,
    run_log: Callable[..., None],
    profile: str | None,
    prompt: str,
    logged: int,
) -> None:
    named = None if profile is None else str(tmp_path / profile)
    driver = build(tmp_path, profile=named, max_runs=3)
    run_log(driver.config.run_log, logged)
    before = driver.history()
    with pytest.raises(CoWorkError) as raised:
        driver.submit(prompt)
    assert raised.value.code == 2
    assert driver.history() == before


def test_a_prompt_at_the_cap_is_allowed(tmp_path: Path) -> None:
    build(tmp_path)._check("x" * 14336)


def test_the_run_log_line_carries_the_documented_fields(tmp_path: Path) -> None:
    driver = build(tmp_path)
    start = datetime.now(timezone.utc)
    driver._record("first", None, "failed:4")
    driver._record("second", tmp_path / "session", "submitted")
    end = datetime.now(timezone.utc)
    entries = driver.history()
    assert [(e.prompt_sha256, e.session_dir, e.outcome) for e in entries] == [
        ("a7937b64b8caa58f03721bb6bacf5c78cb235febe0e70b1b84cd99541461a08e", None, "failed:4"),
        (
            "16367aacb67a4a017c8da8ab95682ccb390863780f7114dda0a0e0c55644c7c4",
            str(tmp_path / "session"),
            "submitted",
        ),
    ]
    assert all(start <= entry.timestamp <= end for entry in entries)


def test_history_reads_a_named_run_log(tmp_path: Path, run_log: Callable[..., None]) -> None:
    other = tmp_path / "other.jsonl"
    at = datetime(2026, 9, 8, 10, tzinfo=timezone.utc)
    run_log(other, at=at)
    assert build(tmp_path).history(other) == [
        RunLogEntry(timestamp=at, prompt_sha256="0" * 64, session_dir=None, outcome="submitted")
    ]


def test_recent_counts_the_trailing_24_hours_of_a_run_log(
    tmp_path: Path, run_log: Callable[..., None]
) -> None:
    """A failed submission counts too. The ceiling and the CoWork backend both read this."""
    driver = build(tmp_path)
    run_log(driver.config.run_log, at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    run_log(driver.config.run_log)
    run_log(driver.config.run_log, outcome="failed:4")
    assert driver.recent() == 2


def test_two_calls_leave_two_log_files_and_no_handler_behind(tmp_path: Path) -> None:
    driver = build(tmp_path)
    handlers = list(LOGGER.handlers)
    for _ in range(2):
        with pytest.raises(CoWorkError):
            driver.submit("x" * 14337)
    assert LOGGER.handlers == handlers
    logs = list((tmp_path / "logs").iterdir())
    assert len(logs) == 2
    assert all("the call failed with code 2" in log.read_text("utf-8") for log in logs)


def test_log_dir_null_writes_no_file(tmp_path: Path) -> None:
    with pytest.raises(CoWorkError):
        build(tmp_path, log_dir=None).submit("x" * 14337)
    assert not (tmp_path / "logs").exists()


# Submitting. No mock of the application: a test reads the session directories the
# application would have written, then calls the step that reads them. What cannot be proved
# that way is proved by tests/integration/test_cowork.py.


def stepping(tmp_path: Path, **overrides: object) -> CoWork:
    """A driver whose timeouts are zero, so a poll runs one pass and does not sleep."""
    zero = {"settle_seconds": 0, "session_timeout": 0, "idle_seconds": 0, "run_timeout": 0}
    return build(tmp_path, **{**zero, **overrides})


@pytest.mark.parametrize(
    ("surface", "link"),
    [
        ("cowork", "claude://claude.ai/new?q=two%20words%0Aand%20a%20line&surface=cowork"),
        ("", "claude://claude.ai/new?q=two%20words%0Aand%20a%20line"),
    ],
)
def test_deep_link_percent_encodes_the_prompt(surface: str, link: str) -> None:
    assert CoWork(CoWorkSection(surface=surface)).deep_link("two words\nand a line") == link


def attempt(call: Callable[[], object]) -> tuple[object, int | None, Path | None]:
    """What `call` returns, or the code and session of the `CoWorkError` it raises."""
    try:
        return call(), None, None
    except CoWorkError as error:
        return None, error.code, error.session_dir


@pytest.mark.parametrize(
    ("before", "after", "found", "code"),
    [
        pytest.param((), (), None, 4, id="nothing-new"),
        pytest.param(("one_turn",), ("subagent",), "subagent", None, id="one-new"),
        pytest.param((), ("one_turn", "subagent"), None, 5, id="two-new"),
    ],
)
def test_discovery_finds_exactly_one_new_session(
    tmp_path: Path,
    before: tuple[str, ...],
    after: tuple[str, ...],
    found: str | None,
    code: int | None,
) -> None:
    driver = stepping(tmp_path)
    account = driver.config.sessions_root / "acct" / "prof"
    for name in before:
        shutil.copytree(PROFILE / name, account / name)
    baseline = set(driver.sessions())
    for name in after:
        shutil.copytree(PROFILE / name, account / name)
    expected = None if found is None else account / found
    discovered = attempt(lambda: driver._discover(driver.config.sessions_root, baseline))
    assert discovered == (expected, code, None)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("one_turn", (None, None, None)),
        ("mismatched_prompt", (None, 6, PROFILE / "mismatched_prompt")),
        ("no_user_record", (None, 6, PROFILE / "no_user_record")),
    ],
)
def test_attribution_compares_the_audit_prompt(
    tmp_path: Path, name: str, expected: tuple[object, int | None, Path | None]
) -> None:
    assert attempt(lambda: stepping(tmp_path)._attribute(PROFILE / name, PONG)) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param("one_turn", (PROFILE / "one_turn", None, None), id="completed"),
        pytest.param("no_transcript", (None, 7, PROFILE / "no_transcript"), id="queued-only"),
        pytest.param("no_output", (PROFILE / "no_output", None, None), id="started-then-quiet"),
    ],
)
def test_wait_returns_on_completion_or_quiescence_after_start(
    tmp_path: Path, name: str, expected: tuple[object, int | None, Path | None]
) -> None:
    assert attempt(lambda: stepping(tmp_path).wait(PROFILE / name)) == expected


# Consent. docs/cowork_driver.md "Taking the keyboard".
#
# Nothing in the unit tier ever grants consent. Granting it means showing a modal, and no test
# here drives the desktop. A test here never calls `run` or `submit` without `consent: none`:
# the driver asks at step 2a, so a submission under `consent: dialog` opens a real modal.


def test_consent_none_returns_without_asking() -> None:
    consent(CoWorkSection(consent=CONSENT_NONE))


def test_reading_a_session_never_asks_for_consent(driver: CoWork, tmp_path: Path) -> None:
    """`collect`, `sessions`, `history`, `recent` and `deep_link` fire nothing."""
    assert driver.collect(PROFILE / "one_turn").session_dir == str(PROFILE / "one_turn")
    driver.deep_link("PING")

    reading = build(tmp_path, consent=CONSENT_DIALOG)
    assert reading.sessions() == []
    assert reading.history() == []
    assert reading.recent() == 0
