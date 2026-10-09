"""The judge behind the `llm` and `baseline` graders: `claude -p`, a vote count, a majority.

The rubric and the material go to the model as one text on stdin, once per `eval.judge_votes`,
and the grader passes on a majority of `PASS` votes. There is no SDK and no second credential
route: the signed-in `claude` on `PATH` is the one route, and `docs/cli.md` makes it part of the
`--cowork` preflight.

`--json-schema` makes the reply carry a `verdict` and the `reasoning` behind it. A reply carrying
none is read as a bare word, which is what an older CLI leaves.

A judged grader decides the verdict as every grader does, which is the pass and fail table in
docs/running_evals.md. Nothing here raises, because a failure is a grader result. A file the
judge cannot be shown is a failed grader naming it, except an image, which is a grader skip:
the harness shows the judge the image, and one text call cannot.

The check judge is the second caller, and it is this package's own rather than the harness's.
It has its own argument list and its own material rule: it is granted `Read`, `Glob` and
`Grep`, it runs in the run directory, and it is shown paths rather than text. Everything below
those two is shared, the vote count, the majority and the schema included. docs/checks.md.

`CLAUDE_CODE_WALNUT_SPIRE` is not exported here. It enables `claude plugin eval`, and this is
`claude -p`.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cases import Grader
from .config import Config
from .grader import GraderResult, failed, produced_file, resolve_target, skipped

# What the judge is shown, and what is recorded of it. The first is what the harness shows
# a judge; the second is what a result document keeps as `evidence`.
MATERIAL_LIMIT = 100_000
EVIDENCE_LIMIT = 2_000
ELISION = "\n...\n"

# The two words a vote is, and what a reply that is neither is called.
PASS_WORD = "PASS"
FAIL_WORD = "FAIL"
LOST_WORD = "LOST"

# The shape a vote comes back in, enforced by the CLI rather than parsed here. `--json-schema`
# makes `--output-format json` carry a `structured_output` object beside the `result` string.
# Measured on CLI 2.1.273.
VERDICT_KEY = "verdict"
REASONING_KEY = "reasoning"
STRUCTURED_KEY = "structured_output"
VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        REASONING_KEY: {"type": "string"},
        VERDICT_KEY: {"type": "string", "enum": [PASS_WORD, FAIL_WORD]},
    },
    "required": [REASONING_KEY, VERDICT_KEY],
    "additionalProperties": False,
}

# How much of the winning reply's reasoning the printed line carries.
REASONING_HEAD = 400

# The composed text. The rubric first, the material fenced, the instruction last.
MATERIAL_OPEN = "--- MATERIAL ---"
MATERIAL_CLOSE = "--- END MATERIAL ---"
INSTRUCTION = (
    f"Say what in the material decided it, then answer {PASS_WORD} or {FAIL_WORD}. "
    f"The schema carries both: the reason in {REASONING_KEY!r}, the answer in {VERDICT_KEY!r}."
)

# A baseline grader shows the judge two trajectories, and says which is which.
BASELINE_HEADING = "BASELINE TRAJECTORY:"
NEW_HEADING = "NEW TRAJECTORY:"

# The check judge's grant, and what it is shown. It reads files and never writes one, so the
# three read-only tools are the whole grant. docs/checks_layer.md.
CHECK_TOOLS = ("Read", "Glob", "Grep")
FILES_OPEN = "--- FILES ---"
FILES_CLOSE = "--- END FILES ---"
CHECK_INSTRUCTION = (
    "Read each file named above. Take as many turns as the question needs. Then say what you "
    f"found that decided it, and answer {PASS_WORD} or {FAIL_WORD}. The schema carries both: the "
    f"reason in {REASONING_KEY!r}, the answer in {VERDICT_KEY!r}."
)

# Image magic, from the file's bytes and never from its name, as the harness detects it.
IMAGE_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a")
RIFF = b"RIFF"
WEBP = b"WEBP"


@dataclass(frozen=True, slots=True)
class Material:
    """What the judge is to be shown, or why it cannot be.

    `error` is a failed grader carrying the reason. `skip_reason` is a grader skip, which
    is excluded from the run's score instead.
    """

    text: str = ""
    error: str | None = None
    skip_reason: str | None = None


@dataclass(frozen=True, slots=True)
class Reply:
    """One vote, read from one `claude -p --output-format json` document."""

    vote: bool | None = None
    cost_usd: float = 0.0
    error: str | None = None
    reasoning: str = ""

    @property
    def word(self) -> str:
        if self.vote is None:
            return LOST_WORD
        return PASS_WORD if self.vote else FAIL_WORD


@dataclass(frozen=True, slots=True)
class Judged:
    """One judged grader's result, and what asking cost."""

    result: GraderResult
    cost_usd: float = 0.0


def resolve_model(judge_model: str | None = None, config: Config | None = None) -> str:
    """The caller's judge model where one was given, and `eval.judge_model` otherwise."""
    if judge_model is not None:
        return judge_model
    return (config if config is not None else Config.load()).eval.judge_model


def resolve_votes(votes: int | None = None, config: Config | None = None) -> int:
    """The caller's vote count where one was given, and `eval.judge_votes` otherwise."""
    if votes is not None:
        return votes
    return (config if config is not None else Config.load()).eval.judge_votes


def judge_argv(model: str) -> list[str]:
    """One vote's command line. The composed text goes on stdin, never in the argument list.

    `--strict-mcp-config` keeps the developer's own MCP servers out of a text vote, and
    `--json-schema` is here so both callers read one shape.
    """
    return [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        "--strict-mcp-config",
        "--json-schema",
        json.dumps(VERDICT_SCHEMA),
    ]


def check_argv(model: str, add_dirs: tuple[str, ...] = ()) -> list[str]:
    """The check judge's command line: the judge's own, plus a grant and the paths it needs.

    `--allowedTools Read,Glob,Grep` alone lets a non-interactive judge read a file: on CLI
    2.1.270 a `claude -p` granted exactly these three read a file in its working directory and
    answered on what it said, with no permission mode and no cap. So neither is written here:
    a cap is a restriction nobody asked for, and the CLI's own default binds the loop.

    `--add-dir` carries each path outside the working directory, which is the run directory.
    A path under it needs none. docs/checks.md.
    """
    argv = [*judge_argv(model), "--allowedTools", ",".join(CHECK_TOOLS)]
    for directory in add_dirs:
        argv += ["--add-dir", directory]
    return argv


def compose_paths(prompt: str, names: tuple[str, ...]) -> str:
    """The one text a check judge's vote is sent: the prompt, the paths, the instruction.

    The material is never inlined. A PDF, an image and a spreadsheet cannot be shown as text,
    and reading a file is what the judge's `Read` tool is for.
    """
    return "\n".join([prompt.strip(), "", FILES_OPEN, *names, FILES_CLOSE, "", CHECK_INSTRUCTION])


def criteria(grader: Grader) -> str:
    """The rubric: the `criteria:` key where one is written, and the body otherwise."""
    written = grader.config.get("criteria")
    if isinstance(written, str) and written.strip():
        return written
    return grader.markdown


def compose(rubric: str, material: str) -> str:
    """The one text every vote is sent, with the material truncated as the harness truncates it."""
    return "\n".join(
        [
            rubric.strip(),
            "",
            MATERIAL_OPEN,
            truncate(material, MATERIAL_LIMIT),
            MATERIAL_CLOSE,
            "",
            INSTRUCTION,
        ]
    )


def truncate(text: str, limit: int) -> str:
    """Head and tail kept, the middle elided. That is what the harness shows a judge."""
    if len(text) <= limit:
        return text
    head = limit // 2
    tail = limit - head
    return text[:head] + ELISION + text[-tail:]


def material(grader: Grader, document: dict[str, Any], case_dir: Path) -> Material:
    """What this grader's judge is shown.

    An `llm` grader reads `focus`; `target` on one is ignored, because the harness ignores
    it. A `baseline` grader reads `baseline_file` beside the case and shows both
    trajectories.
    """
    if grader.type == "baseline":
        return _baseline_material(grader, document, case_dir)

    focus = grader.config.get("focus")
    if isinstance(focus, dict) and focus.get("source") == "file":
        return _file_material(document, focus.get("path"))
    resolved = resolve_target(document, focus)
    if resolved.error is not None:
        return Material(error=resolved.error)
    return Material(text=resolved.text)


def _baseline_material(grader: Grader, document: dict[str, Any], case_dir: Path) -> Material:
    named = grader.config.get("baseline_file")
    if not isinstance(named, str) or not named:
        return Material(error="baseline grader has no baseline_file")
    root = Path(case_dir).resolve()
    path = (root / named).resolve()
    if not path.is_relative_to(root):
        return Material(error=f"{named} resolves outside the case directory")
    try:
        recorded = path.read_bytes()
    except OSError as error:
        return Material(error=f"{named} is unreadable: {error}")
    text = _as_text(recorded)
    if text is None:
        return Material(error=f"{named} is not UTF-8 text")
    trajectory = resolve_target(document, "trace")
    return Material(text="\n".join([BASELINE_HEADING, text, "", NEW_HEADING, trajectory.text]))


def _file_material(document: dict[str, Any], path: Any) -> Material:
    named, error = produced_file(document, path)
    if named is None:
        return Material(error=error)
    try:
        content = named.read_bytes()
    except OSError as error:
        return Material(error=f"{path} is unreadable: {error}")
    if _is_image(content):
        return Material(
            skip_reason=(
                f"{path} is an image, and the harness shows the judge the image itself, "
                "which one text call cannot"
            )
        )
    text = _as_text(content)
    if text is None:
        return Material(error=f"{path} is not UTF-8 text: render it to an image, or write UTF-8")
    return Material(text=text)


def _is_image(content: bytes) -> bool:
    """PNG, JPEG, GIF or WebP, from the bytes and never from the name."""
    if content.startswith(IMAGE_MAGIC):
        return True
    return content[:4] == RIFF and content[8:12] == WEBP


def _as_text(content: bytes) -> str | None:
    if b"\x00" in content:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def read_reply(stdout: str) -> Reply:
    """One vote, its reasoning and its spend, from one `--output-format json` document.

    A document carrying `structured_output` is read from it, and any other from `result` as a bare
    word. A reply that is neither word is a lost vote, and a lost vote is not a `PASS`.
    """
    try:
        payload = json.loads(stdout)
    except ValueError:
        return Reply(error="the judge printed no JSON document")
    if not isinstance(payload, dict):
        return Reply(error="the judge printed no JSON document")
    cost = payload.get("total_cost_usd")
    spent = float(cost) if isinstance(cost, int | float) else 0.0

    structured = payload.get(STRUCTURED_KEY)
    if isinstance(structured, dict):
        verdict = structured.get(VERDICT_KEY)
        reasoning = structured.get(REASONING_KEY)
        said = reasoning.strip() if isinstance(reasoning, str) else ""
        word = verdict.strip().upper() if isinstance(verdict, str) else ""
        if word in (PASS_WORD, FAIL_WORD):
            return Reply(vote=word == PASS_WORD, cost_usd=spent, reasoning=said)
        return Reply(
            cost_usd=spent,
            reasoning=said,
            error=f"the judge's {VERDICT_KEY} was neither word: {str(verdict)[:80]!r}",
        )

    answer = payload.get("result")
    if not isinstance(answer, str):
        return Reply(cost_usd=spent, error="the judge document carries no result")
    word = answer.strip().upper()
    if word == PASS_WORD:
        return Reply(vote=True, cost_usd=spent)
    if word == FAIL_WORD:
        return Reply(vote=False, cost_usd=spent)
    return Reply(cost_usd=spent, error=f"the judge answered neither word: {answer.strip()[:80]!r}")


def tally(grader: Grader, replies: list[Reply], evidence: str) -> Judged:
    """The verdict over the votes cast, and what the winning side said. Every spend counts."""
    cost = sum(reply.cost_usd for reply in replies)
    votes = [reply.vote for reply in replies]
    words = " ".join(reply.word for reply in replies)
    if all(vote is None for vote in votes):
        reasons = sorted({reply.error for reply in replies if reply.error})
        return Judged(failed(grader, f"the judge could not be asked: {'; '.join(reasons)}"), cost)
    # A majority: one vote needs one pass, and three need two.
    passed = sum(1 for vote in votes if vote) >= len(replies) // 2 + 1
    said = next((one.reasoning for one in replies if one.vote is passed and one.reasoning), "")
    return Judged(
        GraderResult(
            name=grader.name,
            passed=passed,
            weight=grader.weight,
            explanation=f"judge votes: {words}" + (f". {said[:REASONING_HEAD]}" if said else ""),
            judge_votes=tuple(bool(vote) for vote in votes),
            evidence=truncate(evidence, EVIDENCE_LIMIT),
        ),
        cost,
    )


def grade(grader: Grader, document: dict[str, Any], case_dir: Path | str, *, model: str) -> Judged:
    """One judged grader: compose once, vote as many times as configured, count."""
    shown = material(grader, document, Path(case_dir))
    if shown.skip_reason is not None:
        return Judged(skipped(grader, shown.skip_reason))
    if shown.error is not None:
        return Judged(failed(grader, shown.error))

    text = compose(criteria(grader), shown.text)
    replies = [_vote(model, text) for _ in range(resolve_votes())]
    return tally(grader, replies, shown.text)


def _vote(model: str, text: str) -> Reply:
    return ask(judge_argv(model), text)


def ask(argv: list[str], text: str, cwd: Path | str | None = None) -> Reply:
    """One `claude -p` call. A process that will not run is a lost vote, never a raise.

    Public because the check judge casts its votes through it, with an argument list and a
    working directory of its own. A tool-using judge answers with the bare word, measured on
    CLI 2.1.270, so `read_reply` reads a check judge's reply exactly as it reads a grader's.
    """
    try:
        completed = subprocess.run(
            argv,
            input=text,
            capture_output=True,
            text=True,
            check=False,
            cwd=None if cwd is None else str(cwd),
        )
    except OSError as error:
        return Reply(error=f"claude could not be run: {error}")
    if completed.returncode != 0:
        return Reply(error=f"claude exited {completed.returncode}")
    return read_reply(completed.stdout)
