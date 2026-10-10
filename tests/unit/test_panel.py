"""The history store, the record, and the panel rendered over the real case tree.

Every history file is a hand-written fixture under tests/data/history/ or a file the real
`append` wrote, every result document is a hand-written one under tests/data/results/, and the
case tree is the real `plugins/smoke`. The reader, the digest, the join and the three renders
are the real ones. The store and the columns are docs/panel.md. See ../README.md.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from importlib import metadata
from pathlib import Path

import pytest

from cowork_evals import panel, results
from cowork_evals.cases import discover
from cowork_evals.panel import HistoryRecord, PanelSnapshot
from cowork_evals.preflight import COWORK, DOCKER
from cowork_evals.results import PluginRef, ResultDocument
from cowork_evals.verdict import decide

DATA = Path(__file__).resolve().parent.parent / "data"
HISTORY = DATA / "history"
DOCUMENTS = DATA / "results"
SMOKE = Path(__file__).resolve().parents[2] / "plugins" / "smoke"

# The five cases `plugins/smoke` holds, and the one of them that carries `no-cowork`.
# ../../plugins/README.md.
CASES = ("capped-turns", "checked-file", "python-version", "session-env", "writes-a-file")
DECLARED_CASE = "capped-turns"
CASE_DIR = "evals/plugin/python-version"


def installed(root: Path, name: str, plugin: str = "smoke", case_dir: str = CASE_DIR) -> Path:
    """One fixture file, copied to the path that case's records belong in."""
    file = panel.path(root, plugin, case_dir)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes((HISTORY / f"{name}.jsonl").read_bytes())
    return file


def entry(**changes) -> HistoryRecord:
    """One record, with a literal for every required field and `changes` over them."""
    fields = {
        "schema_version": 1,
        "invocation": "20260903-090000-smoke",
        "backend": DOCKER,
        "cowork_evals": "0.4.0",
        "plugin": "smoke",
        "case": "one",
        "dir": "evals/plugin/one",
        "outcome": "pass",
        "score": 1.0,
        "pass_rate": 1.0,
        "runs": 1,
        "duration_seconds": 1.0,
        "cost_usd": 0.0,
    }
    return HistoryRecord(**{**fields, **changes})


def smoke_rows(root: Path, *, removed: bool = False):
    """The panel over the real smoke tree, against the history at `root`."""
    return panel.rows(root, [(SMOKE, discover(SMOKE))], removed=removed)


def by_case(built) -> dict:
    return {row.case: row for row in built}


# Which file a record lands in.


@pytest.mark.parametrize(
    ("plugin", "case_dir", "expected"),
    [
        ("smoke", "evals/plugin/python-version", "smoke/plugin/python-version.jsonl"),
        ("smoke", "evals/hello", "smoke/hello.jsonl"),
        ("smoke", "evals/greeter/formal/hello", "smoke/greeter/formal/hello.jsonl"),
        ("smoke", "evals/writer/casual/hello", "smoke/writer/casual/hello.jsonl"),
        ("acme/mail", "evals/a skill/a:case", "acme-mail/a-skill/a-case.jsonl"),
    ],
)
def test_a_record_lands_in_the_file_its_case_directory_names(
    tmp_path: Path, plugin: str, case_dir: str, expected: str
) -> None:
    """A case directly under `evals/` cannot collide with a skill of that name: one is a file,
    the other a directory. Every component is slugged as a run directory's name is."""
    assert panel.path(tmp_path, plugin, case_dir) == tmp_path / expected


# Appending.


def test_three_cases_in_one_append_land_in_three_files(tmp_path: Path) -> None:
    written = panel.append(
        tmp_path,
        [
            entry(dir="evals/plugin/one"),
            entry(dir="evals/plugin/two"),
            entry(plugin="other", dir="evals/skill/two"),
        ],
    )
    assert sorted(file.relative_to(tmp_path).as_posix() for file in written) == [
        "other/skill/two.jsonl",
        "smoke/plugin/one.jsonl",
        "smoke/plugin/two.jsonl",
    ]
    for file in written:
        assert len(panel.read(file)[0]) == 1


def test_a_second_append_adds_a_line_and_keeps_the_first(tmp_path: Path) -> None:
    panel.append(tmp_path, [entry(invocation="first")])
    panel.append(tmp_path, [entry(invocation="second")])
    found, warnings = panel.read(panel.path(tmp_path, "smoke", "evals/plugin/one"))
    assert [one.invocation for one in found] == ["first", "second"]
    assert warnings == []


# Reading.


def test_an_unparsable_last_line_is_reported_and_the_records_before_it_returned(
    tmp_path: Path,
) -> None:
    """A truncated last line loses one measurement and never the whole case."""
    file = installed(tmp_path, "truncated")
    found, warnings = panel.read(file)
    assert [one.invocation for one in found] == ["20260903-090000-smoke"]
    assert len(warnings) == 1
    assert str(file) in warnings[0]
    assert "line 2" in warnings[0]


def test_a_record_of_another_schema_version_is_reported_and_not_read(tmp_path: Path) -> None:
    found, warnings = panel.read(installed(tmp_path, "other_schema"))
    assert found == []
    assert "schemaVersion is 2" in warnings[0]


# The digest.


def case_tree(directory: Path) -> Path:
    """One case directory holding every kind of file the digest covers, and a note."""
    (directory / "graders").mkdir(parents=True)
    (directory / "checks").mkdir()
    (directory / "prompt.md").write_text("---\nname: one\n---\n\nSay hello.\n")
    (directory / "case.yaml").write_text("runs: 1\n")
    (directory / "graders" / "said.md").write_text("---\ntype: regex\npattern: hello\n---\n")
    (directory / "checks" / "assertions.py").write_text("from cowork_evals.checks import check\n")
    (directory / "NOTES.md").write_text("A note, not a grader.\n")
    return directory


def _write(relative: str, text: str) -> Callable[[Path], object]:
    return lambda case: (case / relative).write_text(text)


@pytest.mark.parametrize(
    ("edit", "moves"),
    [
        (_write("prompt.md", "---\nname: one\n---\n\nSay hello. \n"), True),
        (_write("case.yaml", "runs: 2\n"), True),
        (_write("graders/said.md", "---\ntype: regex\npattern: goodbye\n---\n"), True),
        (lambda case: (case / "graders" / "said.md").rename(case / "graders" / "a.md"), True),
        (_write("graders/answered.md", "---\ntype: regex\npattern: hi\n---\n"), True),
        (_write("checks/second.py", "x = 1\n"), True),
        (_write("checks/assertions.py", "from cowork_evals.checks import check  # e\n"), True),
        (_write("NOTES.md", "A longer note, still not a grader.\n"), False),
        (_write("graders/notes.txt", "Not a markdown grader.\n"), False),
    ],
    ids=[
        "prompt",
        "case-yaml",
        "grader-edited",
        "grader-renamed",
        "grader-added",
        "check-added",
        "check-edited",
        "note",
        "grader-directory-text",
    ],
)
def test_the_digest_moves_with_a_defining_file_and_holds_with_any_other(
    tmp_path: Path, edit: Callable[[Path], object], moves: bool
) -> None:
    """A note beside the graders changes no measurement, so it changes no digest. Editing an
    assertion has to move it, or `stale` stays green over it."""
    case = case_tree(tmp_path / "one")
    before = panel.digest(case)
    edit(case)
    assert (panel.digest(case) != before) is moves


# Pruning.


def aged(dir_name: str, days: float) -> HistoryRecord:
    started = datetime.now(timezone.utc) - timedelta(days=days)
    return entry(dir=f"evals/{dir_name}", started_at=started.isoformat())


def test_prune_drops_a_record_by_age_then_an_emptied_file_and_directory(tmp_path: Path) -> None:
    old_and_young = [aged("plugin/one", 40), aged("plugin/one", 1)]
    panel.append(tmp_path, [*old_and_young, aged("old/two", 40), aged("young/three", 1)])
    one = panel.path(tmp_path, "smoke", "evals/plugin/one")
    two = panel.path(tmp_path, "smoke", "evals/old/two")
    assert panel.prune(tmp_path, 30) == [two, one]
    assert len(panel.read(one)[0]) == 1
    assert not (tmp_path / "smoke" / "old").exists()
    assert panel.path(tmp_path, "smoke", "evals/young/three").is_file()


def test_prune_cuts_at_an_exact_moment_days_before_now(tmp_path: Path) -> None:
    """A floor on whole days would keep an hour-old record a day longer than the run
    directory it names."""
    panel.append(tmp_path, [aged("plugin/one", 1 / 24)])
    file = panel.path(tmp_path, "smoke", "evals/plugin/one")
    assert panel.prune(tmp_path, 0) == [file]
    assert not file.exists()


def test_prune_keeps_a_record_with_no_stamp_and_a_line_that_does_not_parse(
    tmp_path: Path,
) -> None:
    """Nothing undatable is dropped: it would be a deletion on the age of nothing."""
    panel.append(tmp_path, [entry()])
    truncated = installed(tmp_path, "truncated")
    assert panel.prune(tmp_path, 30) == [truncated]
    assert len(panel.read(panel.path(tmp_path, "smoke", "evals/plugin/one"))[0]) == 1
    assert truncated.read_text() == (
        '{"schemaVersion": 1, "invocation": "20260904-090000-smoke", "backend": "docker", '
        '"plugin": "smo\n'
    )


# The record, field by field.


CONTAINER_ROOT = "/work/plugin"


def written_document(
    tmp_path: Path, name: str, root: Path | str, plugin_path: Path | str | None = None
) -> Path:
    """One hand-written result document in a run directory, pointed at a real case tree."""
    run = tmp_path / "20260913-101010-smoke"
    (run / "smoke").mkdir(parents=True)
    document = ResultDocument.read(DOCUMENTS / f"{name}.json")
    plugin = PluginRef(name="smoke", path=str(plugin_path or root), version="0.1.0")
    suite = document.suite.model_copy(update={"root": str(root), "plugins": [plugin]})
    results.write(run / "smoke", document.model_copy(update={"suite": suite}))
    return run


def recorded(
    tmp_path: Path, name: str, root: Path | str = SMOKE, backend: str = DOCKER, **options
) -> list[HistoryRecord]:
    """The records `records` builds over one hand-written document."""
    run = written_document(tmp_path, name, root, options.pop("plugin_path", None))
    return panel.records(run, decide(run, found=1, picked=1).outcomes, backend, **options)


def test_a_record_carries_no_digest_rather_than_the_digest_of_nothing(tmp_path: Path) -> None:
    """A root naming no case directory produces an absent field, never a hash of no bytes.

    `sha256` over nothing is a valid-looking digest that differs from every real one, so a
    record carrying it would read `stale` forever over files nobody edited.
    """
    assert recorded(tmp_path, "pass", CONTAINER_ROOT, plugin_path=SMOKE)[0].case_digest is None


def test_every_field_of_a_record_comes_from_the_document_it_was_built_from(
    tmp_path: Path,
) -> None:
    """`pass.json` is one case, one run, one passing structural grader and one judged one.
    The digest is asserted by the stale tests below."""
    records = recorded(tmp_path, "pass", image="cowork-evals:abc")
    assert [one.model_copy(update={"case_digest": None}) for one in records] == [
        HistoryRecord(
            schema_version=1,
            invocation="20260913-101010-smoke",
            backend=DOCKER,
            image="cowork-evals:abc",
            cowork_evals=metadata.version("cowork-evals"),
            plugin="smoke",
            plugin_version="0.1.0",
            skill="plugin",
            case="python-version",
            dir=CASE_DIR,
            outcome="pass",
            score=1.0,
            pass_rate=1.0,
            runs=1,
            duration_seconds=0.0,
            cost_usd=0.004,
            started_at="2026-09-09T10:00:00+00:00",
            claude_version="2.1.265",
        )
    ]


def test_an_optional_field_is_absent_rather_than_null(tmp_path: Path) -> None:
    """The document carries no delta, no error and no trace, so the record carries none."""
    line = panel.append(tmp_path / "history", recorded(tmp_path, "pass"))[0].read_text()
    for absent in ("delta", "error", "failedGraders", "tracePath", "image", "deniedTools"):
        assert f'"{absent}"' not in line
    assert "null" not in line


@pytest.mark.parametrize(
    ("document", "backend", "field", "expected"),
    [
        ("structural_failures", DOCKER, "outcome", "fail"),
        (
            "structural_failures",
            DOCKER,
            "failed_graders",
            ["says-alex", "fired-skill", "read-then-wrote", "wrote-deck"],
        ),
        ("run_error", DOCKER, "error", "7: the run did not finish inside 1800.0 seconds"),
        ("mode_denial", DOCKER, "denied_tools", ["Write"]),
        ("declared_case", COWORK, "outcome", "declared"),
        ("declared_case", COWORK, "runs", 0),
        ("declared_case", COWORK, "duration_seconds", 0.0),
    ],
)
def test_a_record_field_carries_what_the_document_and_the_verdict_say(
    tmp_path: Path, document: str, backend: str, field: str, expected: object
) -> None:
    """`failedGraders` is every scored grader that failed, `error` the first run's, and
    `outcome` the word the verdict reached."""
    assert getattr(recorded(tmp_path, document, backend=backend)[0], field) == expected


def test_a_two_arm_record_carries_the_delta_the_document_worked_out(tmp_path: Path) -> None:
    records = recorded(tmp_path, "two_arm")
    assert [(one.case, one.delta, one.runs) for one in records] == [
        ("fires-and-answers", 1.0, 1),
        ("quiet-case", 0.0, 1),
    ]


# The join to the case tree.


def test_a_tree_with_no_history_reads_never_run_and_a_no_cowork_case_declared(
    tmp_path: Path,
) -> None:
    """The tag is in the tree and is the reason no record will ever appear there."""
    rows, warnings = smoke_rows(tmp_path)
    assert warnings == []
    never = (panel.NEVER, panel.NEVER)
    assert {row.case: (row.cells[DOCKER].outcome, row.cells[COWORK].outcome) for row in rows} == {
        "capped-turns": (panel.NEVER, "declared"),
        "checked-file": never,
        "python-version": never,
        "session-env": never,
        "writes-a-file": never,
    }
    assert {(row.score, row.flake, row.records, row.artefacts) for row in rows} == {
        (None, None, 0, None)
    }
    assert by_case(rows)[DECLARED_CASE].cells[COWORK].age_days is None


def test_the_description_comes_from_the_tree(tmp_path: Path) -> None:
    row = by_case(smoke_rows(tmp_path)[0])["python-version"]
    assert row.description == (
        "A case reaches a running command, on the interpreter the backend put there."
    )


def test_two_backends_for_one_case_each_show_their_own_newest(tmp_path: Path) -> None:
    installed(tmp_path, "two_backends")
    row = by_case(smoke_rows(tmp_path)[0])["python-version"]
    assert row.cells[DOCKER].outcome == "pass"
    assert row.cells[COWORK].outcome == "pass"
    # The newest of the whole row is the docker one, which is the last line of the file.
    assert row.duration_seconds == 9.5
    # One of the two docker records failed.
    assert row.flake == 0.5
    assert row.records == 2


def test_a_row_whose_digest_moved_reads_stale(tmp_path: Path) -> None:
    installed(tmp_path, "stale")
    row = by_case(smoke_rows(tmp_path)[0])["python-version"]
    assert row.stale is True


def test_a_row_whose_digest_matches_does_not(tmp_path: Path) -> None:
    """A container document names a path that is nothing on this host, so the sweep hands
    `records` the root it ran, and the digest is the tree's own. A record with no digest is
    never stale, so the record must carry one for the row to say anything."""
    records = recorded(tmp_path / "run", "pass", CONTAINER_ROOT, roots={"smoke": SMOKE})
    assert records[0].case_digest is not None
    panel.append(tmp_path / "history", records)
    assert by_case(smoke_rows(tmp_path / "history")[0])["python-version"].stale is False


@pytest.mark.parametrize("there", [False, True])
def test_a_row_says_whether_its_trace_directory_is_gone(tmp_path: Path, there: bool) -> None:
    kept = tmp_path / "traces" / "python-version" / "run-1"
    if there:
        kept.mkdir(parents=True)
    record = entry(case="python-version", dir=CASE_DIR, trace_path=str(kept / "trace.jsonl"))
    panel.append(tmp_path / "history", [record])
    row = by_case(smoke_rows(tmp_path / "history")[0])["python-version"]
    assert row.artefacts == str(kept)
    assert row.gone is not there


# A case that is no longer in the tree.


def test_a_removed_case_is_hidden_by_default(tmp_path: Path) -> None:
    installed(tmp_path, "retired", case_dir="evals/plugin/retired-case")
    assert [row.case for row in smoke_rows(tmp_path)[0]] == list(CASES)


def test_a_removed_case_is_shown_under_the_option_and_says_so(tmp_path: Path) -> None:
    installed(tmp_path, "retired", case_dir="evals/plugin/retired-case")
    built, _ = smoke_rows(tmp_path, removed=True)
    retired = by_case(built)["retired-case"]
    assert retired.removed is True
    assert retired.description == panel.REMOVED
    assert retired.plugin == "smoke"
    assert retired.skill == "plugin"
    assert retired.cells[DOCKER].outcome == "pass"


def test_a_case_that_is_still_in_the_tree_is_never_a_removed_row(tmp_path: Path) -> None:
    """It is the tree that decides, not the path argument: a case that was not selected is
    not a case that was removed."""
    installed(tmp_path, "two_backends")
    built, _ = smoke_rows(tmp_path, removed=True)
    assert [row.case for row in built] == list(CASES)


# The renders.


def test_the_snapshot_carries_one_entry_per_row_with_the_rows_values(tmp_path: Path) -> None:
    """`ageDays` is not asserted: it counts days from the fixture's stamp to today."""
    installed(tmp_path, "two_backends")
    document = PanelSnapshot.model_validate_json(panel.snapshot(smoke_rows(tmp_path)[0]))
    assert document.schema_version == 1
    assert [row.case for row in document.rows] == list(CASES)
    measured = by_case(document.rows)["python-version"]
    assert (measured.score, measured.duration_seconds, measured.flake, measured.records) == (
        1.0,
        9.5,
        0.5,
        2,
    )
    assert measured.cells[DOCKER].outcome == measured.cells[COWORK].outcome == "pass"
    assert by_case(document.rows)["writes-a-file"].score is None


def test_the_text_table_cuts_a_description_the_markdown_carries_whole(tmp_path: Path) -> None:
    built, _ = smoke_rows(tmp_path)
    longest = max((row.description for row in built), key=len)
    assert longest in panel.markdown(built)
    assert longest not in panel.table(built)
