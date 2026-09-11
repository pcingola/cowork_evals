"""The CoWork driver: submit one prompt, wait for the run, collect what it produced.

The behaviour is docs/cowork_driver.md and the record shapes are docs/cowork_desktop.md. Nothing
here writes anywhere under the CoWork profile.
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
from typing import Any
from urllib.parse import quote, urlencode

from .config import PROMPT_LIMIT, Config, CoWorkError, CoWorkSection, _override

# A session directory is exactly three levels below the sessions root and holds an
# audit.jsonl. docs/cowork_desktop.md.
SESSION_GLOB = "*/*/*"
AUDIT = "audit.jsonl"
TRANSCRIPTS = Path(".claude") / "projects" / "session"
OUTPUTS = "outputs"

# The terminal command_lifecycle state. docs/cowork_desktop.md, snapshot 2026-09-08.
TERMINAL_STATE = "completed"
STARTED_STATE = "started"

# The rate ceiling protects one CoWork account, so its window is fixed and not configurable.
CEILING_WINDOW = timedelta(hours=24)

# The driver writes here. It never configures the root logger.
LOGGER = logging.getLogger("cowork_evals")
LOG_STEM = "cowork_evals"

# The deep link route and the keystroke. docs/cowork_desktop.md.
DEEP_LINK = "claude://claude.ai/new"
OSASCRIPT = (
    "osascript",
    "-e",
    'tell application "Claude" to activate',
    "-e",
    "delay 0.8",
    "-e",
    'tell application "System Events" to key code 36',
)

# How often a poll looks at the filesystem. Not configurable: the timeouts are.
POLL_SECONDS = 1.0


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

    def history(self, run_log: Path | None = None) -> list[dict[str, Any]]:
        """The run log as one dictionary per line, oldest first."""
        path = Path(run_log) if run_log is not None else self._config.run_log
        return _read_jsonl(path)

    def collect(self, session_dir: Path | str, *, prompt: str | None = None) -> dict[str, Any]:
        """Build the session document from one session directory already on disk."""
        directory = Path(session_dir)
        audit = _read_jsonl(directory / AUDIT)
        transcript, other, subagents = _transcripts(directory)
        records = _read_jsonl(transcript) if transcript is not None else []

        turns = _turns(records)
        final_text = _final_text(turns)
        if final_text is None:
            raise CoWorkError(8, f"{directory}: the run produced no assistant text", directory)

        audit_prompt = _audit_prompt(audit)
        submitted = prompt if prompt is not None else audit_prompt
        calls = _tool_calls(records)
        return {
            "prompt": submitted,
            "prompt_sha256": _digest(submitted),
            "session_dir": str(directory),
            "submitted_at": _submitted_at(audit),
            "collected_at": _now(),
            "transcript": None if transcript is None else str(transcript),
            "other_transcripts": [str(path) for path in other],
            "subagent_transcripts": [str(path) for path in subagents],
            "audit_prompt": audit_prompt,
            "lifecycle": _lifecycle(audit),
            "turns": turns,
            "tool_calls": calls,
            "tool_names": [call["name"] for call in calls],
            "final_text": final_text,
            "outputs": _outputs(directory),
            "log_file": None if self._log_file is None else str(self._log_file),
        }

    # Firing. The nine steps and the code each failure produces are in
    # docs/cowork_driver.md.

    def deep_link(self, prompt: str) -> str:
        """The deep link this prompt is submitted through. Pure, and fires nothing."""
        query = {"q": prompt}
        if self._config.surface:
            query["surface"] = self._config.surface
        return f"{DEEP_LINK}?{urlencode(query, quote_via=quote, safe='')}"

    def run(self, prompt: str) -> dict[str, Any]:
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
            self._record(prompt, error.session_dir, f"failed:{error.code}")
            raise
        self._record(prompt, session_dir, "submitted")
        return session_dir

    def _fire_and_attribute(self, prompt: str) -> Path:
        root = self._config.sessions_root
        baseline = set(self.sessions(root))
        link = self.deep_link(prompt)

        LOGGER.info("firing the deep link: %s", link)
        self._fire(["open", link])
        time.sleep(self._config.settle_seconds)
        LOGGER.info("sending the synthetic Return")
        self._fire(list(OSASCRIPT))

        session_dir = self._discover(root, baseline)
        LOGGER.info("discovered the session: %s", session_dir)
        self._attribute(session_dir, prompt)
        LOGGER.info("attributed the session to this submission")
        return session_dir

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
            recorded = _audit_prompt(_read_jsonl(session_dir / AUDIT))
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
            audit = _read_jsonl(session_dir / AUDIT)
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
        count = 0
        for entry in self.history():
            stamp = _parse_timestamp(entry.get("timestamp"))
            if stamp is not None and stamp >= cutoff:
                count += 1
        return count

    def _record(self, prompt: str, session_dir: Path | None, outcome: str) -> None:
        """Append one line to the run log. A failed submission is logged too."""
        entry = {
            "timestamp": _now(),
            "prompt_sha256": _digest(prompt),
            "session_dir": None if session_dir is None else str(session_dir),
            "outcome": outcome,
        }
        path = self._config.run_log
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        LOGGER.info("run log: %s", entry)

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


# Readers. Each takes what it reads, so a test drives it over a fixture directory.


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSON Lines file, dropping a line that does not parse.

    Both audit.jsonl and the transcript are appended while the run is live, and this is
    called on both while a run is in flight, so a read can catch a partial last line. That
    truncated tail is the only unparsable line with a known cause. A line that does not
    parse anywhere else has none, and is dropped rather than trusted.
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
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            records.append(record)
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


def _content_blocks(record: dict[str, Any]) -> list[dict[str, Any]]:
    """The content of a transcript record, always as a list of blocks."""
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    return []


def _text_of(record: dict[str, Any]) -> str:
    """The turn text of a record. A thinking block is not turn text."""
    parts = [
        block.get("text", "")
        for block in _content_blocks(record)
        if block.get("type") == "text" and isinstance(block.get("text"), str)
    ]
    return "\n".join(part for part in parts if part)


def _turns(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Role and text per turn. Only user and assistant records carry a message."""
    turns = []
    for record in records:
        if record.get("type") not in ("user", "assistant"):
            continue
        message = record.get("message")
        role = message.get("role") if isinstance(message, dict) else None
        text = _text_of(record)
        if not text:
            continue
        if not isinstance(role, str):
            role = str(record.get("type"))
        turns.append({"role": role, "text": text})
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
    return _final_text(_turns(_read_jsonl(Path(transcript))))


def _final_text(turns: list[dict[str, str]]) -> str | None:
    for turn in reversed(turns):
        if turn["role"] == "assistant":
            return turn["text"]
    return None


def _tool_calls(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every tool_use, paired to its tool_result by tool_use_id.

    A result whose call is absent from this transcript belongs to a subagent and is
    dropped. Positional pairing is wrong: results arrive in later records, and parallel
    calls interleave.
    """
    calls: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}
    for record in records:
        for block in _content_blocks(record):
            if block.get("type") != "tool_use":
                continue
            call = {
                "id": block.get("id"),
                "name": block.get("name"),
                "input": block.get("input"),
                "mcp_server": record.get("attributionMcpServer"),
                "mcp_tool": record.get("attributionMcpTool"),
                "timestamp": record.get("timestamp"),
                "result": None,
            }
            calls.append(call)
            if isinstance(block.get("id"), str):
                index[block["id"]] = call

    for record in records:
        for block in _content_blocks(record):
            if block.get("type") != "tool_result":
                continue
            call = index.get(block.get("tool_use_id"))
            if call is not None:
                call["result"] = block.get("content")
    return calls


def _lifecycle(audit: list[dict[str, Any]]) -> list[str]:
    return [
        record["state"]
        for record in audit
        if record.get("type") == "command_lifecycle" and isinstance(record.get("state"), str)
    ]


def _first_user(audit: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The `user` audit record of the first submission in this session directory.

    A session directory can hold more than one command. docs/cowork_desktop.md.
    """
    for record in audit:
        if record.get("type") == "user":
            return record
    return None


def _audit_prompt(audit: list[dict[str, Any]]) -> str | None:
    """The submitted prompt as the application recorded it, verbatim."""
    record = _first_user(audit)
    return (_text_of(record) or None) if record is not None else None


def _submitted_at(audit: list[dict[str, Any]]) -> str | None:
    """When the prompt reached the application, from that same record."""
    record = _first_user(audit)
    stamp = record.get("timestamp") if record is not None else None
    return stamp if isinstance(stamp, str) else None


def _outputs(session_dir: Path) -> list[str]:
    root = session_dir / OUTPUTS
    if not root.is_dir():
        return []
    return sorted(str(path.relative_to(session_dir)) for path in root.rglob("*") if path.is_file())


def _digest(prompt: str | None) -> str | None:
    if prompt is None:
        return None
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _started(audit: list[dict[str, Any]], session_dir: Path) -> bool:
    """Whether the run has demonstrably started: a started state, or a first assistant turn."""
    if STARTED_STATE in _lifecycle(audit):
        return True
    transcript, _, _ = _transcripts(session_dir)
    if transcript is None:
        return False
    return any(turn["role"] == "assistant" for turn in _turns(_read_jsonl(transcript)))


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


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        # `fromisoformat` accepts a `Z` suffix from Python 3.11. This package runs on 3.10.
        stamp = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None
    return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)


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
