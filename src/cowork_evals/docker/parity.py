"""Compare a probe document against the image inventory. Runs on the host.

The delta table in docs/docker.md is applied exactly, and six things fail: a pin that is
missing or at another version, the same for a package of the second global npm tree, a
`NODE_PATH` that does not name that tree, one of the five tools recorded as absent turning up
present, `import uno`, because unoserver and headless conversion are the capability the
container exists to prove, and a tool probe.py probes that no table here records, whose result
would otherwise be read by nothing.

No file under `docs/` is parsed. The pins come from the shipped `requirements.txt`, read by
cowork_evals.requirements, and the expected non-Python versions are the table below, which cites
docs/runtime.md.

    python3 -m cowork_evals.docker.parity probe.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..requirements import pins
from . import probe

REQUIREMENTS = Path(__file__).parent.parent / "data" / "requirements.txt"

# Every tool probe.py probes is in exactly one of the three tables below, and compare()
# fails when one is in none of them. Which table a new tool goes in is decided by what is
# recorded for it: a version, presence alone, or absence.

# The five docs/runtime.md records as not present. A skill can call one here and not in a
# session, so finding one is a failure.
ABSENT = ("wkhtmltopdf", "weasyprint", "exiftool", "docker", "sqlite3")

# Recorded present with no version to compare. docs/runtime.md lists `ssh`, `bwrap`, `socat`
# and `xvfb-run` without one. The harness needs `bwrap` and `socat` to start a granted `Bash`
# tool.
PRESENT = ("ssh", "bwrap", "socat", "xvfb-run")

# What docs/runtime.md records for each tool, for the report. A difference is printed and
# does not fail: a jammy point release moves a patch version and must not block.
EXPECTED_VERSIONS = {
    "python3": "3.10.12",
    "pip": "25.3",
    "uv": "0.12.3",
    "node": "22.23.2",
    "npm": "10.9.8",
    "java": "11.0.32",
    "git": "2.34.1",
    "soffice": "26.2.5.2",
    "unoserver": "3.7",
    "pandoc": "2.9.2.1",
    "pdftoppm": "22.02.0",
    "gs": "9.55.0",
    "qpdf": "10.6.3",
    "tesseract": "4.1.1",
    "convert": "6.9.11-60",
    "ffmpeg": "4.4.2",
    "curl": "7.81.0",
    "wget": "1.21.2",
    "jq": "1.6",
    "dot": "2.43.0",
    "pdflatex": "3.141592653",
    "xelatex": "3.141592653",
    "latexmk": "4.76",
    "rg": "13.0.0",
    "zip": "3.0",
    "unzip": "6.00",
    "rsync": "3.2.7",
    "bc": "1.07.1",
    "file": "5.41",
    "xmllint": "20913",
}

# docs/runtime.md, the second global npm tree. A missing or moved package fails, as a pin
# does: it changes what a skill can `require()`.
NPM_GLOBALS = {
    "@anthropic-ai/sandbox-runtime": "0.0.76",
    "docx": "9.7.1",
    "graphviz": "0.0.9",
    "markdown-toc": "1.2.0",
    "marked": "18.0.12",
    "pdf-lib": "1.17.1",
    "pdfjs-dist": "6.3.289",
    "pptxgenjs": "4.0.1",
    "sharp": "0.35.4",
    "ts-node": "10.9.2",
    "tsx": "4.23.13",
    "typescript": "7.0.2",
}
NODE_PATH = "/usr/local/lib/node_modules_global/lib/node_modules"

# docs/runtime.md, the fonts section. Printed, never failed.
EXPECTED_FONT_FAMILIES = 118
EXPECTED_OS_ID = "ubuntu"
EXPECTED_OS_VERSION_ID = "22.04"
EXPECTED_ARCHITECTURE = "aarch64"


class Platform(BaseModel):
    """`platform.system()` and `platform.release()` inside the container."""

    model_config = ConfigDict(extra="forbid")

    system: str
    release: str


class OsRelease(BaseModel):
    """`/etc/os-release`, as far as this module reads it. probe.py writes `{}` when unreadable."""

    model_config = ConfigDict(extra="ignore")

    ID: str | None = None
    VERSION_ID: str | None = None
    PRETTY_NAME: str | None = None


class ToolProbe(BaseModel):
    """One tool: whether it ran, its first output line, and the version parsed out of it."""

    model_config = ConfigDict(extra="forbid")

    present: bool
    version: str | None = None
    output: str | None = None


class UnoProbe(BaseModel):
    """Whether `import uno` succeeded, and what it printed when it did not."""

    model_config = ConfigDict(extra="forbid")

    imports: bool
    error: str | None = None


class ProbeDocument(BaseModel):
    """The document probe.py writes. probe.py is its only writer and stays standard library."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # `schema` shadows a `BaseModel` attribute, so the field carries the key as an alias.
    schema_: int = Field(alias="schema")
    platform: Platform
    architecture: str
    os_release: OsRelease
    tools: dict[str, ToolProbe]
    uno: UnoProbe
    font_families: int | None
    pip_freeze: list[str]
    npm_globals: dict[str, str | None]
    node_path: str | None = None


# A tool the document does not name was not found.
NOT_PROBED = ToolProbe(present=False)


def compare(document: ProbeDocument, expected: dict[str, str]) -> tuple[list[str], list[str]]:
    """The failures and the notes, in the order docs/docker.md's delta table lists them."""
    failures: list[str] = []
    notes: list[str] = []

    found = pins("\n".join(document.pip_freeze))
    for name, version in sorted(expected.items()):
        if name not in found:
            failures.append(f"pin missing: {name}=={version}")
        elif found[name] != version:
            failures.append(f"pin moved: {name}=={found[name]}, expected {version}")
    for name in sorted(set(found) - set(expected)):
        notes.append(f"extra package: {name}=={found[name]}")

    modules = document.npm_globals
    for name, version in sorted(NPM_GLOBALS.items()):
        if name not in modules:
            failures.append(f"npm package missing: {name}@{version}")
        elif modules[name] != version:
            failures.append(f"npm package moved: {name}@{modules[name]}, expected {version}")
    for name in sorted(set(modules) - set(NPM_GLOBALS)):
        notes.append(f"extra npm package: {name}@{modules[name]}")
    if document.node_path != NODE_PATH:
        failures.append(f"NODE_PATH: {document.node_path}, expected {NODE_PATH}")

    tools = document.tools
    unlisted = sorted(
        set(probe.VERSION_COMMANDS) - set(EXPECTED_VERSIONS) - set(ABSENT) - set(PRESENT)
    )
    if unlisted:
        failures.append(f"tool probed and never compared: {', '.join(unlisted)}")
    for name in ABSENT:
        if tools.get(name, NOT_PROBED).present:
            failures.append(f"tool recorded as absent is present: {name}")

    uno = document.uno
    if not uno.imports:
        failures.append(f"import uno failed: {uno.error or 'no detail reported'}")

    for name, version in sorted(EXPECTED_VERSIONS.items()):
        reported = tools.get(name, NOT_PROBED)
        if not reported.present:
            notes.append(f"tool absent: {name}, expected {version}")
        # The probe parses a dotted version out of the tool's own line. A build suffix
        # such as ImageMagick's `-60` is in that line and not in the parsed version, so
        # the line is the second place to look before calling it a difference.
        elif reported.version != version and version not in (reported.output or ""):
            notes.append(f"tool version differs: {name} {reported.version}, expected {version}")

    for name in PRESENT:
        if not tools.get(name, NOT_PROBED).present:
            notes.append(f"tool absent: {name}, no version recorded")

    families = document.font_families
    if families != EXPECTED_FONT_FAMILIES:
        notes.append(f"font families: {families}, expected {EXPECTED_FONT_FAMILIES}")

    release = document.os_release
    if release.ID != EXPECTED_OS_ID or release.VERSION_ID != EXPECTED_OS_VERSION_ID:
        notes.append(
            f"OS: {release.ID} {release.VERSION_ID}, "
            f"expected {EXPECTED_OS_ID} {EXPECTED_OS_VERSION_ID}"
        )
    if document.architecture != EXPECTED_ARCHITECTURE:
        notes.append(f"architecture: {document.architecture}, expected {EXPECTED_ARCHITECTURE}")

    return failures, notes


def report(document: ProbeDocument, failures: list[str], notes: list[str]) -> None:
    """The platform the probe actually ran on comes first.

    An x86 run is never read as an aarch64 one.
    """
    print(
        f"probed: {document.os_release.PRETTY_NAME or 'unknown OS'} "
        f"{document.architecture or 'unknown architecture'}, "
        f"{len(document.pip_freeze)} packages, "
        f"{document.font_families} font families"
    )
    for note in notes:
        print(f"note: {note}")
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    print(f"{len(failures)} failures, {len(notes)} notes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("probe", type=Path, help="the JSON document docker/probe.py wrote")
    arguments = parser.parse_args(argv)

    document = ProbeDocument.model_validate_json(arguments.probe.read_text())
    expected = pins(REQUIREMENTS.read_text())
    failures, notes = compare(document, expected)
    report(document, failures, notes)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
