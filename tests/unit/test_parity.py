"""The delta table in docs/docker.md, one case per row.

Every input is a recorded probe document under tests/data/docker/. `probe_clean.json` is
a real probe of the built image; each other document is that one with a single delta
introduced. No container starts here, and the comparison is the real one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cowork_evals.docker import probe
from cowork_evals.docker.parity import (
    ABSENT,
    EXPECTED_VERSIONS,
    PRESENT,
    REQUIREMENTS,
    ProbeDocument,
    compare,
    main,
)
from cowork_evals.requirements import pins

DATA = Path(__file__).resolve().parents[1] / "data" / "docker"


def probed(name: str) -> tuple[list[str], list[str]]:
    document = ProbeDocument.model_validate_json((DATA / f"{name}.json").read_text())
    return compare(document, pins(REQUIREMENTS.read_text()))


def test_a_clean_probe_has_no_failures():
    """The font family count is printed and does not fail. ImageMagick's build suffix in its
    line is no version difference, so the clean probe carries no other note."""
    assert probed("probe_clean") == ([], ["font families: 114, expected 118"])


@pytest.mark.parametrize(
    ("name", "failure"),
    [
        ("probe_pin_missing", "pin missing: pypdf==6.18.0"),
        ("probe_pin_moved", "pin moved: pandas==2.0.0, expected 2.3.3"),
        ("probe_npm_missing", "npm package missing: pptxgenjs@4.0.1"),
        ("probe_npm_moved", "npm package moved: docx@9.6.0, expected 9.7.1"),
        (
            "probe_node_path_unset",
            "NODE_PATH: None, expected /usr/local/lib/node_modules_global/lib/node_modules",
        ),
        ("probe_absent_tool_present", "tool recorded as absent is present: exiftool"),
        ("probe_uno_fails", "import uno failed: ModuleNotFoundError: No module named 'uno'"),
    ],
)
def test_a_failing_delta_is_the_one_failure(name: str, failure: str):
    failures, _ = probed(name)
    assert failures == [failure]


@pytest.mark.parametrize(
    ("name", "note"),
    [
        ("probe_extra_package", "extra package: rich==14.0.0"),
        ("probe_tool_version_differs", "tool version differs: pandoc 2.9.2.2, expected 2.9.2.1"),
        ("probe_npm_extra", "extra npm package: left-pad@1.3.0"),
        ("probe_sandbox_tool_absent", "tool absent: bwrap, no version recorded"),
        ("probe_tool_absent", "tool absent: pandoc, expected 2.9.2.1"),
    ],
)
def test_a_printed_delta_is_a_note_and_no_failure(name: str, note: str):
    failures, notes = probed(name)
    assert failures == []
    assert note in notes


def test_every_tool_the_probe_probes_is_in_exactly_one_of_the_three_tables():
    """The row compare() fails on. It is over the package's own tables, not over a document."""
    versions, absent, present = set(EXPECTED_VERSIONS), set(ABSENT), set(PRESENT)
    assert set(probe.VERSION_COMMANDS) == versions | absent | present
    assert not (versions & absent or versions & present or absent & present)


def test_the_platform_the_probe_ran_on_is_reported(capsys):
    """An x86 run is never read as an aarch64 one."""
    assert main([str(DATA / "probe_clean.json")]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith("probed: Ubuntu 22.04.5 LTS aarch64,")


def test_the_exit_code_is_one_on_a_failure(capsys):
    assert main([str(DATA / "probe_pin_missing.json")]) == 1
