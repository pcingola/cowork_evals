"""The delta table in docs/docker.md, one test per row.

Every input is a recorded probe document under tests/data/docker/. `probe_clean.json` is
a real probe of the built image; each other document is that one with a single delta
introduced. No container starts here, and the comparison is the real one.
"""

from __future__ import annotations

from pathlib import Path

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
    failures, _ = probed("probe_clean")
    assert failures == []


def test_a_missing_pin_fails():
    failures, _ = probed("probe_pin_missing")
    assert failures == ["pin missing: pypdf==6.18.0"]


def test_a_moved_pin_fails():
    failures, _ = probed("probe_pin_moved")
    assert failures == ["pin moved: pandas==2.0.0, expected 2.3.3"]


def test_an_extra_package_is_printed_and_does_not_fail():
    failures, notes = probed("probe_extra_package")
    assert failures == []
    assert "extra package: rich==14.0.0" in notes


def test_a_differing_tool_version_is_printed_and_does_not_fail():
    failures, notes = probed("probe_tool_version_differs")
    assert failures == []
    assert "tool version differs: pandoc 2.9.2.2, expected 2.9.2.1" in notes


def test_a_missing_npm_package_fails():
    failures, _ = probed("probe_npm_missing")
    assert failures == ["npm package missing: pptxgenjs@4.0.1"]


def test_a_moved_npm_package_fails():
    failures, _ = probed("probe_npm_moved")
    assert failures == ["npm package moved: docx@9.6.0, expected 9.7.1"]


def test_an_extra_npm_package_is_printed_and_does_not_fail():
    failures, notes = probed("probe_npm_extra")
    assert failures == []
    assert "extra npm package: left-pad@1.3.0" in notes


def test_a_node_path_that_does_not_name_the_tree_fails():
    failures, _ = probed("probe_node_path_unset")
    assert failures == [
        "NODE_PATH: None, expected /usr/local/lib/node_modules_global/lib/node_modules"
    ]


def test_a_tool_recorded_as_absent_being_present_fails():
    failures, _ = probed("probe_absent_tool_present")
    assert failures == ["tool recorded as absent is present: exiftool"]


def test_every_tool_the_probe_probes_is_in_one_of_the_three_tables():
    """The row compare() fails on. It is over the package's own tables, not over a document."""
    assert set(probe.VERSION_COMMANDS) == set(EXPECTED_VERSIONS) | set(ABSENT) | set(PRESENT)


def test_a_tool_with_no_recorded_version_is_printed_when_it_is_absent():
    """bwrap, socat and ssh have no version in the tables. compare() still reads them."""
    failures, notes = probed("probe_sandbox_tool_absent")
    assert failures == []
    assert "tool absent: bwrap, no version recorded" in notes


def test_import_uno_failing_fails():
    failures, _ = probed("probe_uno_fails")
    assert failures == ["import uno failed: ModuleNotFoundError: No module named 'uno'"]


def test_a_build_suffix_in_the_tool_line_is_not_a_difference():
    """ImageMagick reports 6.9.11-60 in its line and 6.9.11 as the parsed version."""
    _, notes = probed("probe_clean")
    assert not [note for note in notes if note.startswith("tool version differs: convert")]


def test_the_platform_the_probe_ran_on_is_reported(capsys):
    """An x86 run is never read as an aarch64 one."""
    assert main([str(DATA / "probe_clean.json")]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith("probed: Ubuntu 22.04.5 LTS aarch64,")


def test_the_exit_code_is_one_on_a_failure(capsys):
    assert main([str(DATA / "probe_pin_missing.json")]) == 1
