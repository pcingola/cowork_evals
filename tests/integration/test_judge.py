"""The judge against the real `claude -p`. Twelve short calls, no CoWork session.

It proves what a recorded reply document cannot: that the composed text reaches the model
on stdin, and that the reply parses. The check judge is proven the same way, over a real PNG
and a real PDF the test writes, because what it has to establish is that a judge granted
`Read`, `Glob` and `Grep` opens a binary the `llm` grader cannot be shown at all. Deselected
by default; `live` because it spends. It costs no ceiling entry, because nothing here submits
to CoWork. See ../README.md.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from cowork_evals.cases import Grader, LlmGraderConfig
from cowork_evals.checks import build_run
from cowork_evals.cowork import SessionDocument
from cowork_evals.judge import grade, resolve_model

RUBRIC = "PASS if the material is exactly the word PONG. FAIL for anything else."


def rubric_grader() -> Grader:
    return Grader(
        name="is-pong",
        type="llm",
        weight=1,
        config=LlmGraderConfig(focus="last_message"),
        markdown=RUBRIC,
        path=Path("is-pong.md"),
    )


def answering(text: str) -> SessionDocument:
    """A session document whose one read field, for an `llm` grader on `last_message`, is `text`."""
    return SessionDocument(
        prompt=None,
        prompt_sha256=None,
        session_dir="",
        submitted_at=None,
        collected_at="",
        transcript=None,
        other_transcripts=[],
        subagent_transcripts=[],
        audit_prompt=None,
        lifecycle=[],
        turns=[],
        tool_calls=[],
        tool_names=[],
        final_text=text,
        outputs=[],
        log_file=None,
    )


@pytest.mark.integration
@pytest.mark.live
@pytest.mark.timeout(600)
def test_the_judge_passes_a_string_that_satisfies_the_rubric(tmp_path: Path) -> None:
    judged = grade(rubric_grader(), answering("PONG"), tmp_path, model=resolve_model())
    assert judged.result.skipped is False
    assert judged.result.judge_votes is not None, judged.result.explanation
    assert judged.result.passed is True, judged.result.explanation
    assert judged.result.explanation.startswith("judge votes: ")
    assert judged.result.evidence == "PONG"
    assert judged.cost_usd >= 0.0


@pytest.mark.integration
@pytest.mark.live
@pytest.mark.timeout(600)
def test_the_judge_fails_a_string_that_does_not(tmp_path: Path) -> None:
    judged = grade(
        rubric_grader(),
        answering("The kernel is 6.8.0-136-generic."),
        tmp_path,
        model=resolve_model(),
    )
    assert judged.result.judge_votes is not None, judged.result.explanation
    assert judged.result.passed is False, judged.result.explanation


# The check judge, over two binaries. Both are written here, byte by byte, because the point
# is a file the `llm` grader refuses: a PNG is a grader skip there and a PDF is not UTF-8.


def write_png(path: Path) -> None:
    """An 8 by 8 solid red PNG, written from its own bytes."""
    side = 8
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * side for _ in range(side))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", side, side, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def write_pdf(path: Path, word: str) -> None:
    """One page carrying one word in Helvetica, with a real cross-reference table."""
    stream = f"BT /F1 24 Tf 20 40 Td ({word}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n"
    ).encode()
    path.write_bytes(bytes(out))


@pytest.mark.integration
@pytest.mark.live
@pytest.mark.timeout(900)
def test_the_check_judge_reads_a_png_and_a_pdf(tmp_path: Path) -> None:
    directory = tmp_path / "traces" / "checked" / "run-1"
    (directory / "workspace").mkdir(parents=True)
    (directory / "trace.jsonl").write_text("{}\n", encoding="utf-8")
    write_png(directory / "workspace" / "square.png")
    write_pdf(directory / "workspace" / "note.pdf", "PONG")

    run = build_run(directory, tmp_path, 1, resolve_model())
    passed = run.judge(
        "square.png is a solid red square, and note.pdf carries the word PONG.",
        run.file("square.png"),
        run.file("note.pdf"),
    )
    assert passed.passed is True, passed.explanation
    assert passed.explanation.startswith("judge votes: ")

    failed = run.judge(
        "square.png is a solid green square, and note.pdf carries the word PING.",
        run.file("square.png"),
        run.file("note.pdf"),
    )
    assert failed.passed is False, failed.explanation

    assert [len(call.replies) for call in run.calls] == [3, 3]
    assert all("workspace/square.png" in call.prompt for call in run.calls)
    assert all(call.cost_usd >= 0.0 for call in run.calls)
