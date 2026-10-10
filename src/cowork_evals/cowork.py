"""The CoWork driver: submit one prompt, wait for the run, collect what it produced.

The behaviour is docs/cowork_driver.md, the design is docs/cowork_driver_internals.md, and the
record shapes are docs/cowork_desktop.md. Nothing here writes anywhere under the CoWork profile.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import subprocess
import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import quote, urlencode

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    ValidationError,
    field_serializer,
    model_serializer,
    model_validator,
)

from .config import (
    CONSENT_NONE,
    PROMPT_LIMIT,
    Config,
    CoWorkError,
    CoWorkSection,
    _override,
)

# A session directory is exactly three levels below the sessions root and holds an
# audit.jsonl. docs/cowork_desktop.md.
SESSION_GLOB = "*/*/*"
AUDIT = "audit.jsonl"
TRANSCRIPTS = Path(".claude") / "projects" / "session"
OUTPUTS = "outputs"

# The terminal command_lifecycle state. docs/cowork_desktop.md.
TERMINAL_STATE = "completed"
STARTED_STATE = "started"

# The rate ceiling protects one CoWork account, so its window is fixed and not configurable.
CEILING_WINDOW = timedelta(hours=24)

# The one taxonomy code that means nothing was fired. docs/cowork_driver.md.
REFUSED = 2

# The driver writes here. It never configures the root logger.
LOGGER = logging.getLogger("cowork_evals")
LOG_STEM = "cowork_evals"

# The deep link route and the keystrokes. docs/cowork_desktop.md.
DEEP_LINK = "claude://claude.ai/new"

# What `System Events` calls the CoWork process. Measured, not guessed, and the value is
# beside the bundle id in docs/cowork_desktop.md.
COWORK_PROCESS = "Claude"

# Step 2b. The delay is what lets the activation land before the guard reads the frontmost
# process, which is otherwise still whatever the developer was working in.
ACTIVATE = (
    "osascript",
    "-e",
    'tell application "Claude" to activate',
    "-e",
    "delay 0.8",
)

# The guard's probe. Its own command, because this is the one osascript call whose standard
# output is read.
FRONTMOST = (
    "osascript",
    "-e",
    'tell application "System Events" to get name of first process whose frontmost is true',
)

# Step 2c. Key code 51 is Delete. It runs behind the guard, so the worst field it can reach
# is a CoWork field that is not the composer.
CLEAR = (
    "osascript",
    "-e",
    'tell application "System Events" to keystroke "a" using command down',
    "-e",
    'tell application "System Events" to key code 51',
)

# Step 5. Key code 36 is Return. It carries no activation of its own: step 2b activated and
# step 4a checked, and re-activating here would open a gap after the last check.
RETURN = (
    "osascript",
    "-e",
    'tell application "System Events" to key code 36',
)

# Step 2a. `tell me to activate` is what forces the modal in front of the editor the
# developer is working in. There is no `default button`, so a Return typed into that editor
# mid-sentence dismisses nothing and the developer has to click.
#
# The message states the timeout, because `display dialog` renders no countdown and a modal
# that waits without saying how long reads as one that waits forever.
CONSENT_TITLE = "cowork_evals"
CONSENT_MESSAGE = (
    "cowork_evals is about to drive CoWork. Do not use the keyboard or the "
    "mouse until it finishes."
    "\n\nIt goes ahead on its own in {timeout:g} seconds."
)

# One process, one operator, one keyboard. `CoWorkSection` is frozen and
# `cowork_backend._run_case` builds a new `CoWork` per case, so neither can carry this and
# a 20-case suite would ask 20 times. docs/cowork_driver_internals.md.
_CONSENTED = False

# How often a poll looks at the filesystem. Not configurable: the timeouts are.
POLL_SECONDS = 1.0


# The records the driver reads. Their shapes are docs/cowork_desktop.md. A record carries keys
# nothing here reads, and ignores them. A content block keeps them, because a tool result is
# written into the session document as the transcript holds it.


class ContentBlock(BaseModel):
    """One block of `message.content`, and one block of a `tool_result`'s content.

    It keeps the keys it does not name, and writes none of its fields that is `None`, so a
    tool result reaches `ToolCall.result` with the keys and values the transcript holds.
    """

    model_config = ConfigDict(extra="allow")

    type: str
    text: str | None = None
    thinking: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None
    tool_use_id: str | None = None
    content: str | list[ContentBlock] | None = None

    @model_serializer(mode="wrap")
    def _present(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return {key: value for key, value in handler(self).items() if value is not None}


class Message(BaseModel):
    """The `message` of a transcript or audit record. `content` takes both of its forms."""

    model_config = ConfigDict(extra="ignore")

    role: str | None = None
    content: str | list[ContentBlock]

    def blocks(self) -> list[ContentBlock]:
        """The content as a list of blocks: a string is one text block."""
        if isinstance(self.content, str):
            return [ContentBlock(type="text", text=self.content)]
        return self.content


class SessionRecord(BaseModel):
    """One line of a session transcript."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    type: str
    uuid: str | None = None
    timestamp: str | None = None
    message: Message | None = None
    attribution_mcp_server: str | None = Field(default=None, alias="attributionMcpServer")
    attribution_mcp_tool: str | None = Field(default=None, alias="attributionMcpTool")


class AuditRecord(BaseModel):
    """One line of `audit.jsonl`."""

    model_config = ConfigDict(extra="ignore")

    type: str
    uuid: str | None = None
    timestamp: str | None = None
    message: Message | None = None
    state: str | None = None


# What the driver returns. Every key is written, and a field that is `None` is written as null,
# because docs/cowork_driver.md lists every key the session document carries.


class Turn(BaseModel):
    """Role and text of one turn."""

    model_config = ConfigDict(extra="forbid")

    role: str
    text: str


class ToolCall(BaseModel):
    """One `tool_use`, with the content of the `tool_result` paired to it by id."""

    model_config = ConfigDict(extra="forbid")

    id: str | None
    name: str
    input: dict[str, Any]
    mcp_server: str | None
    mcp_tool: str | None
    timestamp: str | None
    result: str | list[ContentBlock] | None


class SessionDocument(BaseModel):
    """What `collect` and `run` return. docs/cowork_driver.md lists every key."""

    model_config = ConfigDict(extra="forbid")

    prompt: str | None
    prompt_sha256: str | None
    session_dir: str
    submitted_at: str | None
    collected_at: str
    transcript: str | None
    other_transcripts: list[str]
    subagent_transcripts: list[str]
    audit_prompt: str | None
    lifecycle: list[str]
    turns: list[Turn]
    tool_calls: list[ToolCall]
    tool_names: list[str]
    final_text: str
    outputs: list[str]
    log_file: str | None

    @model_validator(mode="after")
    def _names(self) -> SessionDocument:
        named = [call.name for call in self.tool_calls]
        if self.tool_names != named:
            raise ValueError(f"tool_names is {self.tool_names}, and tool_calls names {named}")
        return self


class RunLogEntry(BaseModel):
    """One line of the run log. `session_dir` is written as null when none is known."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    prompt_sha256: str
    session_dir: str | None
    outcome: str

    @field_serializer("timestamp")
    def _iso(self, value: datetime) -> str:
        # `isoformat`, so UTC is written `+00:00` and not pydantic's `Z`.
        return value.isoformat()

    @property
    def utc(self) -> datetime:
        """The timestamp, read as UTC when the line carries no offset."""
        stamp = self.timestamp
        return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)


# What `_read_jsonl` parses one line into.
Record = TypeVar("Record", bound=BaseModel)


class CoWork:
    """The driver. One instance holds one resolved configuration."""

    def __init__(self, config: CoWorkSection | None = None, **overrides: Any) -> None:
        base = Config.load().cowork if config is None else config
        self._config = _override(base, overrides)
        self._log_file: Path | None = None

    @classmethod
    def from_file(cls, path: Path | str, **overrides: Any) -> CoWork:
        """Build from a named configuration file rather than the working directory's."""
        return cls(Config.load(path).cowork, **overrides)

    @property
    def config(self) -> CoWorkSection:
        return self._config

    # Reading. None of these fires anything, and none needs a profile except through
    # the configured sessions root.

    def sessions(self, root: Path | None = None) -> list[Path]:
        """Every session directory under a root, sorted."""
        base = Path(root) if root is not None else self._config.sessions_root
        if not base.is_dir():
            return []
        return sorted(d for d in base.glob(SESSION_GLOB) if d.is_dir() and (d / AUDIT).is_file())

    def history(self, run_log: Path | None = None) -> list[RunLogEntry]:
        """The run log as one `RunLogEntry` per line, oldest first."""
        path = Path(run_log) if run_log is not None else self._config.run_log
        return _read_jsonl(path, RunLogEntry)

    def collect(self, session_dir: Path | str, *, prompt: str | None = None) -> SessionDocument:
        """Build the session document from one session directory already on disk."""
        directory = Path(session_dir)
        audit = _read_jsonl(directory / AUDIT, AuditRecord)
        transcript, other, subagents = _transcripts(directory)
        records = _read_jsonl(transcript, SessionRecord) if transcript is not None else []

        turns = _turns(records)
        final_text = _final_text(turns)
        if final_text is None:
            raise CoWorkError(8, f"{directory}: the run produced no assistant text", directory)

        audit_prompt = _audit_prompt(audit)
        submitted = prompt if prompt is not None else audit_prompt
        calls = _tool_calls(records)
        return SessionDocument(
            prompt=submitted,
            prompt_sha256=_digest(submitted),
            session_dir=str(directory),
            submitted_at=_submitted_at(audit),
            collected_at=_now(),
            transcript=None if transcript is None else str(transcript),
            other_transcripts=[str(path) for path in other],
            subagent_transcripts=[str(path) for path in subagents],
            audit_prompt=audit_prompt,
            lifecycle=_lifecycle(audit),
            turns=turns,
            tool_calls=calls,
            tool_names=[call.name for call in calls],
            final_text=final_text,
            outputs=_outputs(directory),
            log_file=None if self._log_file is None else str(self._log_file),
        )

    # Firing. The nine steps and the code each failure produces are in
    # docs/cowork_driver.md.

    def deep_link(self, prompt: str) -> str:
        """The deep link this prompt is submitted through. Pure, and fires nothing."""
        query = {"q": prompt}
        if self._config.surface:
            query["surface"] = self._config.surface
        return f"{DEEP_LINK}?{urlencode(query, quote_via=quote, safe='')}"

    def run(self, prompt: str) -> SessionDocument:
        """Submit, wait for the run to finish, and collect the session document."""
        with self._diagnostics():
            session_dir = self._submit(prompt)
            self._wait(session_dir)
            return self.collect(session_dir, prompt=prompt)

    def submit(self, prompt: str) -> Path:
        """Steps 1 to 7: refuse, fire, discover and attribute. Returns the session."""
        with self._diagnostics():
            return self._submit(prompt)

    def wait(self, session_dir: Path | str) -> Path:
        """Step 8: block until the completion signal fires."""
        return self._wait(Path(session_dir))

    def _submit(self, prompt: str) -> Path:
        self._check(prompt)
        try:
            session_dir = self._fire_and_attribute(prompt)
        except CoWorkError as error:
            # Code 2 is a refusal, and a refusal has fired nothing. It is not logged and it
            # does not count against the ceiling, which is the rule step 1 already follows.
            if error.code != REFUSED:
                self._record(prompt, error.session_dir, f"failed:{error.code}")
            raise
        self._record(prompt, session_dir, "submitted")
        return session_dir

    def _fire_and_attribute(self, prompt: str) -> Path:
        root = self._config.sessions_root
        baseline = set(self.sessions(root))
        link = self.deep_link(prompt)

        self._consented()
        self._clear()
        LOGGER.info("firing the deep link: %s", link)
        self._fire(["open", link])
        time.sleep(self._config.settle_seconds)
        self._guard()
        LOGGER.info("sending the synthetic Return")
        self._fire(list(RETURN))

        session_dir = self._discover(root, baseline)
        LOGGER.info("discovered the session: %s", session_dir)
        self._attribute(session_dir, prompt)
        LOGGER.info("attributed the session to this submission")
        return session_dir

    def _consented(self) -> None:
        """Step 2a. Ask for the keyboard, and code 2 on Cancel.

        It asks rather than reading a flag a caller was supposed to set. Every route to a
        submission passes through here, so a route that does not ask cannot take the
        keyboard with no warning. `consent` is once per process, so a caller that asked
        before a sweep reaches a no-op here and the developer is asked once, not per case.
        """
        consent(self._config)

    def _clear(self) -> None:
        """Steps 2b and 2c: activate, guard, then select all and delete.

        It runs before the deep link, not after: the deep link is what puts the prompt in
        the composer, so a clear after it deletes the prompt.

        It does not read what it cleared and does not report it. Reading the composer means
        reading the screen, which docs/cowork_desktop.md rules out.
        """
        LOGGER.info("activating CoWork")
        self._fire(list(ACTIVATE))
        self._guard()
        LOGGER.info("clearing the composer")
        self._fire(list(CLEAR))

    def _guard(self) -> None:
        """Code 9 when CoWork is not frontmost. Nothing is typed.

        It narrows the window between the check and the keystroke and does not close it:
        focus can change in between. Attribution stays the backstop, so a keystroke that
        lands elsewhere is still caught as code 6 rather than graded. There is no retry:
        retrying blind is how a keystroke reaches an editor.
        """
        name = frontmost()
        if name != COWORK_PROCESS:
            raise CoWorkError(
                9,
                f"{name} is frontmost, not {COWORK_PROCESS}: nothing was typed",
            )

    def _fire(self, argv: list[str]) -> None:
        """Run one command. A non-zero return is code 3.

        stderr is inherited, so osascript error 1002 reaches the terminal.
        """
        code = subprocess.run(argv, check=False).returncode
        if code != 0:
            raise CoWorkError(3, f"{argv[0]} returned {code}")

    def _discover(self, root: Path, baseline: set[Path]) -> Path:
        """Poll for a session directory that is not in the baseline."""
        deadline = time.monotonic() + self._config.session_timeout
        while True:
            new = sorted(set(self.sessions(root)) - baseline)
            if len(new) > 1:
                raise CoWorkError(
                    5,
                    f"{len(new)} session directories appeared, so this run cannot be "
                    f"attributed: {', '.join(str(path) for path in new)}",
                )
            if new:
                return new[0]
            if time.monotonic() >= deadline:
                raise CoWorkError(
                    4,
                    f"no session directory appeared under {root} within "
                    f"{self._config.session_timeout} seconds",
                )
            time.sleep(POLL_SECONDS)

    def _attribute(self, session_dir: Path, prompt: str) -> None:
        """Compare the recorded prompt with the submitted one.

        A session directory can exist before its user audit record is written, so this
        keeps polling until the record appears or the discovery timeout expires.
        """
        deadline = time.monotonic() + self._config.session_timeout
        while True:
            recorded = _audit_prompt(_read_jsonl(session_dir / AUDIT, AuditRecord))
            if recorded is not None:
                if recorded != prompt:
                    raise CoWorkError(
                        6,
                        f"{session_dir}: the audit prompt does not match the submitted one",
                        session_dir,
                    )
                return
            if time.monotonic() >= deadline:
                raise CoWorkError(
                    6,
                    f"{session_dir}: no user audit record appeared within "
                    f"{self._config.session_timeout} seconds, so the session cannot be "
                    "attributed",
                    session_dir,
                )
            time.sleep(POLL_SECONDS)

    def _wait(self, session_dir: Path) -> Path:
        """Block until the terminal lifecycle state, or until quiescence.

        Quiescence is a heuristic. It counts only after the run has demonstrably started,
        because the idle window would otherwise accrue during VM boot and an empty session
        would be reported as a finished run.
        """
        deadline = time.monotonic() + self._config.run_timeout
        signature: object = None
        idle_since = time.monotonic()
        while True:
            audit = _read_jsonl(session_dir / AUDIT, AuditRecord)
            if TERMINAL_STATE in _lifecycle(audit):
                LOGGER.info("the completion signal fired: lifecycle state %s", TERMINAL_STATE)
                return session_dir

            current = _signature(session_dir)
            if current != signature:
                signature = current
                idle_since = time.monotonic()

            if _started(audit, session_dir) and (
                time.monotonic() - idle_since >= self._config.idle_seconds
            ):
                LOGGER.warning(
                    "the completion signal fired: quiescence, which is a heuristic and can "
                    "fire during a long pause mid-run"
                )
                return session_dir

            if time.monotonic() >= deadline:
                raise CoWorkError(
                    7,
                    f"{session_dir}: the run did not complete within "
                    f"{self._config.run_timeout} seconds",
                    session_dir,
                )
            time.sleep(POLL_SECONDS)

    # Refusal, the run log and the diagnostic log. All of it happens before anything fires.

    def _check(self, prompt: str) -> None:
        """Step 1 of the sequence. Every failure here is code 2, and nothing has fired."""
        directory = self._config.profile_dir
        if not directory.is_dir() or not os.access(directory, os.R_OK):
            raise CoWorkError(2, f"{directory}: the configured CoWork profile is not readable")

        recent = self.recent()
        if recent >= self._config.max_runs:
            raise CoWorkError(
                2,
                f"rate ceiling reached: {recent} submissions in the last 24 hours, "
                f"max_runs is {self._config.max_runs}",
            )

        if len(prompt) > PROMPT_LIMIT:
            raise CoWorkError(
                2,
                f"prompt is {len(prompt)} characters, above the {PROMPT_LIMIT} deep link cap, "
                "and the application would truncate it silently",
            )

    def recent(self) -> int:
        """Submissions in the trailing 24 hours, counted from the run log.

        It owns `CEILING_WINDOW` and the timestamp parsing, so the CoWork backend calls it
        rather than re-deriving the window over `history()`.
        """
        cutoff = datetime.now(timezone.utc) - CEILING_WINDOW
        return sum(1 for entry in self.history() if entry.utc >= cutoff)

    def _record(self, prompt: str, session_dir: Path | None, outcome: str) -> None:
        """Append one line to the run log. A failed submission is logged too."""
        entry = RunLogEntry(
            timestamp=datetime.now(timezone.utc),
            prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            session_dir=None if session_dir is None else str(session_dir),
            outcome=outcome,
        )
        written = entry.model_dump(mode="json")
        path = self._config.run_log
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(written) + "\n")
        LOGGER.info("run log: %s", written)

    @contextlib.contextmanager
    def _diagnostics(self) -> Iterator[Path | None]:
        """Open one diagnostic log for the length of one firing call.

        Every `CoWorkError` that leaves a firing call is logged here and nowhere else, so
        the log names the failure whichever step raised it. `log_dir: null` turns the file
        off, and the logger then carries whatever handler the caller attached. The root
        logger is never touched.
        """
        directory = self._config.log_dir
        level = LOGGER.level
        handler = None
        self._log_file = None
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
            self._log_file = _log_path(directory)
            handler = logging.FileHandler(self._log_file, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            LOGGER.addHandler(handler)
            LOGGER.setLevel(logging.INFO)
        try:
            yield self._log_file
        except CoWorkError as error:
            LOGGER.error("the call failed with code %d: %s", error.code, error)
            raise
        finally:
            self._log_file = None
            if handler is not None:
                LOGGER.removeHandler(handler)
                handler.close()
                LOGGER.setLevel(level)


# The keyboard. Both of these read the desktop, not a session, so they take no
# configuration object and stand beside the class rather than on it.


def consent(section: CoWorkSection) -> None:
    """Ask once per process for the keyboard. Cancel is code 2, and nothing has fired.

    Step 2a calls it, so every submission asks. `cli._ask` and `cli._each_plugin` call it
    first, before they build a driver, so a sweep asks once up front rather than at its
    first submission. A library caller does the same, or sets `cowork.consent: none` in the
    configuration file.

    `consent: none` shows nothing and sets nothing, which is the documented route for an
    unattended run, and the only route that fires without a warning. It is a
    configuration value and not a test seam: a test sets it in a file exactly as a consumer
    would, and no parameter exists to inject an answer.

    The timeout proceeds rather than refuses. An unattended run is the case it exists for.
    """
    global _CONSENTED
    if section.consent == CONSENT_NONE or _CONSENTED:
        return
    argv = [
        "osascript",
        "-e",
        "tell me to activate",
        "-e",
        f'display dialog "{CONSENT_MESSAGE.format(timeout=section.consent_timeout)}" '
        f'with title "{CONSENT_TITLE}" buttons {{"Cancel", "Go"}} '
        f"giving up after {section.consent_timeout:g}",
    ]
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"osascript returned {completed.returncode}"
        raise CoWorkError(2, f"consent was not given: {detail}")
    _CONSENTED = True
    LOGGER.info("consent was given for this process")


def frontmost() -> str:
    """The name of the frontmost process, as `System Events` reports it.

    A non-zero `osascript` is code 3, which is what every other `osascript` failure is. A
    refusal to type is code 9 and is raised by the guard above, so a grading layer tells
    "the driver refused to type into something that was not CoWork" apart from "osascript
    is broken".
    """
    completed = subprocess.run(list(FRONTMOST), capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"osascript returned {completed.returncode}"
        raise CoWorkError(3, f"the frontmost process could not be read: {detail}")
    return completed.stdout.strip()


# Readers. Each takes what it reads, so a test drives it over a fixture directory.


def _read_jsonl(path: Path, model: type[Record]) -> list[Record]:
    """Parse a JSON Lines file into one record per line, dropping a line that does not parse.

    Both audit.jsonl and the transcript are appended while the run is live, and this is
    called on both while a run is in flight, so a read can catch a partial last line. That
    truncated tail is the only unparsable line with a known cause. A line that does not
    parse, or does not validate as the record, has none anywhere else, and is dropped rather
    than trusted.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(model.model_validate_json(line))
        except ValidationError:
            continue
    return records


def _transcripts(session_dir: Path) -> tuple[Path | None, list[Path], list[Path]]:
    """The main transcript, the other top level ones, and the subagent sidechains.

    The main transcript is the newest top level file by modification time. A session
    directory with no transcript directory yet is tolerated.
    """
    root = session_dir / TRANSCRIPTS
    if not root.is_dir():
        return None, [], []
    top = sorted(path for path in root.glob("*.jsonl") if path.is_file())
    subagents = sorted(path for path in root.glob("*/subagents/*.jsonl") if path.is_file())
    if not top:
        return None, [], subagents
    main = max(top, key=lambda path: path.stat().st_mtime)
    return main, [path for path in top if path != main], subagents


def _content_blocks(record: SessionRecord | AuditRecord) -> list[ContentBlock]:
    """The content of a record, always as a list of blocks."""
    return [] if record.message is None else record.message.blocks()


def _text_of(record: SessionRecord | AuditRecord) -> str:
    """The turn text of a record. A thinking block is not turn text."""
    parts = [
        block.text
        for block in _content_blocks(record)
        if block.type == "text" and block.text is not None
    ]
    return "\n".join(part for part in parts if part)


def _turns(records: list[SessionRecord]) -> list[Turn]:
    """Role and text per turn. Only user and assistant records carry a message."""
    turns = []
    for record in records:
        if record.type not in ("user", "assistant"):
            continue
        text = _text_of(record)
        if not text:
            continue
        role = record.message.role if record.message is not None else None
        turns.append(Turn(role=role if role is not None else record.type, text=text))
    return turns


def final_text(transcript: Path | str) -> str | None:
    """The last assistant text in one session transcript, as `collect` reads it.

    It is what a `target: last_message` grader read on this backend, and [traces.py](traces.py)
    writes it beside the transcript it copied. Public because that module needs the value and
    must not parse this format a second time: a session transcript is read here, and the
    harness's `trace.jsonl` is read there.

    `None` when the transcript is absent, unreadable as JSON lines, or carries no assistant
    text. Nothing here writes anywhere under the CoWork profile.
    """
    return _final_text(_turns(_read_jsonl(Path(transcript), SessionRecord)))


def _final_text(turns: list[Turn]) -> str | None:
    for turn in reversed(turns):
        if turn.role == "assistant":
            return turn.text
    return None


def _tool_calls(records: list[SessionRecord]) -> list[ToolCall]:
    """Every tool_use, paired to its tool_result by tool_use_id.

    A result whose call is absent from this transcript belongs to a subagent and is
    dropped. Positional pairing is wrong: results arrive in later records, and parallel
    calls interleave.
    """
    results: dict[str, str | list[ContentBlock] | None] = {}
    for record in records:
        for block in _content_blocks(record):
            if block.type == "tool_result" and block.tool_use_id is not None:
                results[block.tool_use_id] = block.content

    calls = []
    for record in records:
        for block in _content_blocks(record):
            if block.type != "tool_use":
                continue
            calls.append(
                ToolCall(
                    id=block.id,
                    name=block.name or "",
                    input=block.input if block.input is not None else {},
                    mcp_server=record.attribution_mcp_server,
                    mcp_tool=record.attribution_mcp_tool,
                    timestamp=record.timestamp,
                    result=None if block.id is None else results.get(block.id),
                )
            )
    return calls


def _lifecycle(audit: list[AuditRecord]) -> list[str]:
    return [
        record.state
        for record in audit
        if record.type == "command_lifecycle" and record.state is not None
    ]


def _first_user(audit: list[AuditRecord]) -> AuditRecord | None:
    """The `user` audit record of the first submission in this session directory.

    A session directory can hold more than one command. docs/cowork_desktop.md.
    """
    for record in audit:
        if record.type == "user":
            return record
    return None


def _audit_prompt(audit: list[AuditRecord]) -> str | None:
    """The submitted prompt as the application recorded it, verbatim."""
    record = _first_user(audit)
    return (_text_of(record) or None) if record is not None else None


def _submitted_at(audit: list[AuditRecord]) -> str | None:
    """When the prompt reached the application, from that same record."""
    record = _first_user(audit)
    return record.timestamp if record is not None else None


def _outputs(session_dir: Path) -> list[str]:
    root = session_dir / OUTPUTS
    if not root.is_dir():
        return []
    return sorted(str(path.relative_to(session_dir)) for path in root.rglob("*") if path.is_file())


def _digest(prompt: str | None) -> str | None:
    if prompt is None:
        return None
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _started(audit: list[AuditRecord], session_dir: Path) -> bool:
    """Whether the run has demonstrably started: a started state, or a first assistant turn."""
    if STARTED_STATE in _lifecycle(audit):
        return True
    transcript, _, _ = _transcripts(session_dir)
    if transcript is None:
        return False
    return any(turn.role == "assistant" for turn in _turns(_read_jsonl(transcript, SessionRecord)))


def _signature(session_dir: Path) -> tuple[tuple[str, int, float], ...]:
    """What quiescence compares: every file under the session, with its size and mtime."""
    entries = []
    for path in session_dir.rglob("*"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if path.is_file():
            entries.append((str(path), stat.st_size, stat.st_mtime))
    return tuple(sorted(entries))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_path(directory: Path) -> Path:
    """`<log_dir>/<yyyymmdd-hhmmss>-cowork_evals.log`, suffixed when that name is taken.

    Two calls in the same second would otherwise share one file.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = directory / f"{stamp}-{LOG_STEM}.log"
    attempt = 2
    while path.exists():
        path = directory / f"{stamp}-{LOG_STEM}-{attempt}.log"
        attempt += 1
    return path
