"""The history store, the record, and the panel rendered over the real case tree.

Every history file is a hand-written fixture under tests/data/history/ or a file the real
`append` wrote, every result document is a hand-written one under tests/data/results/, and the
case tree is the real `plugins/smoke`. The reader, the digest, the join and the three renders
are the real ones. The store and the columns are docs/panel.md. See ../README.md.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from cowork_evals import logs, panel
from cowork_evals.cases import discover
from cowork_evals.cases import read as read_case
from cowork_evals.harness import RESULT_NAME
from cowork_evals.panel import HistoryRecord, PanelSnapshot
from cowork_evals.preflight import COWORK, DOCKER
from cowork_evals.results import PluginRef, ResultDocument
from cowork_evals.verdict import CaseOutcome, decide

DATA = Path(__file__).resolve().parent.parent / "data"
HISTORY = DATA / "history"
DOCUMENTS = DATA / "results"
SMOKE = Path(__file__).resolve().parents[2] / "plugins" / "smoke"

# The four cases `plugins/smoke` holds, and the one of them that carries `no-cowork`.
# ../../plugins/README.md.
CASES = ("capped-turns", "checked-file", "python-version", "session-env", "writes-a-file")
DECLARED_CASE = "capped-turns"
CASE_DIR = "evals/plugin/python-version"


def record(name: str, plugin: str = "smoke", case_dir: str = CASE_DIR) -> Path:
    """One fixture file, copied to the path that case's records belong in."""

    def _install(root: Path) -> Path:
        file = panel.path(root, plugin, case_dir)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes((HISTORY / f"{name}.jsonl").read_bytes())
        return file

    return _install


def installed(root: Path, name: str, plugin: str = "smoke", case_dir: str = CASE_DIR) -> Path:
    return record(name, plugin, case_dir)(root)


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


def test_an_ordinary_case_lands_under_its_plugin_and_skill(tmp_path: Path) -> None:
    assert panel.path(tmp_path, "smoke", "evals/plugin/python-version") == (
        tmp_path / "smoke" / "plugin" / "python-version.jsonl"
    )


def test_a_case_directly_under_evals_has_no_skill_component(tmp_path: Path) -> None:
    """It cannot collide with a skill of that name: one is a file, the other a directory."""
    assert panel.path(tmp_path, "smoke", "evals/hello") == tmp_path / "smoke" / "hello.jsonl"


def test_a_case_nested_deeper_keeps_every_component(tmp_path: Path) -> None:
    """Two cases sharing a directory name under two skills stay apart."""
    first = panel.path(tmp_path, "smoke", "evals/greeter/formal/hello")
    second = panel.path(tmp_path, "smoke", "evals/writer/casual/hello")
    assert first == tmp_path / "smoke" / "greeter" / "formal" / "hello.jsonl"
    assert first != second


def test_every_component_goes_through_the_slug(tmp_path: Path) -> None:
    """A plugin named `acme/mail` is one directory, exactly as a run directory is."""
    assert panel.path(tmp_path, "acme/mail", "evals/a skill/a:case") == (
        tmp_path / "acme-mail" / "a-skill" / "a-case.jsonl"
    )


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
    assert len(written) == 3
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


def test_a_file_that_is_not_there_is_no_records_and_no_warning(tmp_path: Path) -> None:
    assert panel.read(tmp_path / "smoke" / "plugin" / "absent.jsonl") == ([], [])


def test_a_record_of_another_schema_version_is_reported_and_not_read(tmp_path: Path) -> None:
    file = tmp_path / "one.jsonl"
    file.write_text('{"schemaVersion": 2, "plugin": "smoke", "dir": "evals/a/b"}\n')
    found, warnings = panel.read(file)
    assert found == []
    assert "schemaVersion is 2" in warnings[0]


# The digest.


def case_tree(directory: Path) -> Path:
    """One case directory holding all three kinds of file the digest covers, and a note."""
    directory.mkdir(parents=True)
    (directory / "prompt.md").write_text("---\nname: one\n---\n\nSay hello.\n")
    (directory / "case.yaml").write_text("runs: 1\n")
    (directory / "graders").mkdir()
    (directory / "graders" / "said.md").write_text("---\ntype: regex\npattern: hello\n---\n")
    (directory / "NOTES.md").write_text("A note, not a grader.\n")
    return directory


def test_the_digest_moves_when_the_prompt_moves(tmp_path: Path) -> None:
    case = case_tree(tmp_path / "one")
    before = panel.digest(case)
    (case / "prompt.md").write_text("---\nname: one\n---\n\nSay hello. \n")
    assert panel.digest(case) != before


def test_the_digest_moves_when_the_case_yaml_moves(tmp_path: Path) -> None:
    case = case_tree(tmp_path / "one")
    before = panel.digest(case)
    (case / "case.yaml").write_text("runs: 2\n")
    assert panel.digest(case) != before


def test_the_digest_moves_when_a_grader_moves(tmp_path: Path) -> None:
    case = case_tree(tmp_path / "one")
    before = panel.digest(case)
    (case / "graders" / "said.md").write_text("---\ntype: regex\npattern: goodbye\n---\n")
    assert panel.digest(case) != before


def test_the_digest_moves_when_a_grader_is_added_or_renamed(tmp_path: Path) -> None:
    case = case_tree(tmp_path / "one")
    before = panel.digest(case)
    (case / "graders" / "said.md").rename(case / "graders" / "answered.md")
    assert panel.digest(case) != before


def test_the_digest_holds_when_any_other_file_in_the_case_directory_moves(tmp_path: Path) -> None:
    """A note beside the graders changes no measurement, so it changes no digest."""
    case = case_tree(tmp_path / "one")
    before = panel.digest(case)
    (case / "NOTES.md").write_text("A longer note, still not a grader.\n")
    (case / "graders" / "notes.txt").write_text("Not a markdown grader.\n")
    assert panel.digest(case) == before


# Pruning.


def dated(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def aged(dir_name: str, days: int) -> HistoryRecord:
    return entry(dir=f"evals/{dir_name}", started_at=dated(days))


def test_prune_drops_a_record_by_age_and_keeps_the_rest(tmp_path: Path) -> None:
    panel.append(tmp_path, [aged("plugin/one", 40), aged("plugin/one", 1)])
    file = panel.path(tmp_path, "smoke", "evals/plugin/one")
    assert panel.prune(tmp_path, 30) == [file]
    found, _ = panel.read(file)
    assert len(found) == 1


def test_prune_deletes_an_emptied_file_and_then_an_emptied_directory(tmp_path: Path) -> None:
    panel.append(tmp_path, [aged("plugin/one", 40), aged("other/two", 1)])
    panel.prune(tmp_path, 30)
    assert not (tmp_path / "smoke" / "plugin").exists()
    assert (tmp_path / "smoke" / "other" / "two.jsonl").is_file()


def test_prune_reads_the_retention_the_way_the_log_prune_does(tmp_path: Path) -> None:
    """`--older-than DAYS` is one flag over both trees, so it cuts at one moment in both.

    An hour-old record at `--older-than 0` goes, exactly as `logs.prune` deletes an hour-old
    run directory at the same retention. A floor on whole days would keep it for a day longer
    than the run directory it names.
    """
    hour = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    panel.append(tmp_path, [entry(started_at=hour)])
    file = panel.path(tmp_path, "smoke", "evals/plugin/one")

    directory = tmp_path / "runs" / f"{datetime.now() - timedelta(hours=1):%Y%m%d-%H%M%S}-smoke"
    directory.mkdir(parents=True)

    assert logs.prune(directory.parent, 0) == [directory]
    assert panel.prune(tmp_path, 0) == [file]
    assert not file.exists()


def test_prune_keeps_a_record_with_no_stamp(tmp_path: Path) -> None:
    """Nothing undatable is dropped: it would be a deletion on the age of nothing."""
    panel.append(tmp_path, [entry()])
    assert panel.prune(tmp_path, 30) == []
    assert len(panel.read(panel.path(tmp_path, "smoke", "evals/plugin/one"))[0]) == 1


# The record, field by field.


def written_document(
    tmp_path: Path, name: str, root: Path | str, plugin_path: Path | str | None = None
) -> Path:
    """One hand-written result document in a run directory, pointed at a real case tree."""
    run = tmp_path / "20260913-101010-smoke"
    (run / "smoke").mkdir(parents=True)
    document = ResultDocument.read(DOCUMENTS / f"{name}.json")
    plugin = PluginRef(name="smoke", path=str(plugin_path or root), version="0.1.0")
    suite = document.suite.model_copy(update={"root": str(root), "plugins": [plugin]})
    written = document.model_copy(update={"suite": suite})
    (run / "smoke" / RESULT_NAME).write_text(written.model_dump_json(by_alias=True))
    return run


CONTAINER_ROOT = "/work/plugin"


def test_the_digest_is_read_from_this_hosts_tree_and_not_from_the_documents_root(
    tmp_path: Path,
) -> None:
    """A container document names a path that is nothing on this host.

    `claude plugin eval` runs inside the container and writes `suite.root` as the path the
    plugin was mounted at, `/work/plugin`. The case files the digest covers never move, so
    the sweep hands `records` the root it ran, and the digest is the tree's own.
    """
    run = written_document(tmp_path, "pass", CONTAINER_ROOT)
    decided = decide(run, found=3, picked=1)

    built = panel.records(run, decided.outcomes, DOCKER, roots={"smoke": SMOKE})
    assert built[0].case_digest == panel.digest(SMOKE / "evals" / "plugin" / "python-version")


def test_a_record_carries_no_digest_rather_than_the_digest_of_nothing(tmp_path: Path) -> None:
    """A root naming no case directory produces an absent field, never a hash of no bytes.

    `sha256` over nothing is a valid-looking digest that differs from every real one, so a
    record carrying it would read `stale` forever over files nobody edited.
    """
    run = written_document(tmp_path, "pass", CONTAINER_ROOT, plugin_path=SMOKE)
    decided = decide(run, found=3, picked=1)

    built = panel.records(run, decided.outcomes, DOCKER)
    assert built[0].case_digest is None
    assert panel.digest(Path(CONTAINER_ROOT)) == panel.digest(tmp_path / "nothing-here")


def test_every_field_of_a_record_comes_from_the_document_it_was_built_from(
    tmp_path: Path,
) -> None:
    """`pass.json` is one case, one run, one passing structural grader and one judged one."""
    run = written_document(tmp_path, "pass", SMOKE)
    decided = decide(run, found=3, picked=1)
    built = panel.records(run, decided.outcomes, DOCKER, image="cowork-evals:abc")

    assert len(built) == 1
    record = built[0]
    assert record.schema_version == 1
    assert record.invocation == "20260913-101010-smoke"
    assert record.backend == DOCKER
    assert record.image == "cowork-evals:abc"
    assert record.plugin == "smoke"
    assert record.plugin_version == "0.1.0"
    assert record.skill == "plugin"
    assert record.case == "python-version"
    assert record.dir == CASE_DIR
    assert record.outcome == "pass"
    assert record.score == 1.0
    assert record.pass_rate == 1.0
    assert record.runs == 1
    assert record.cost_usd == 0.004
    assert record.started_at == "2026-09-09T10:00:00+00:00"
    assert record.claude_version == "2.1.265"
    # The digest is of the directory the suite root names, and what it covers is asserted
    # against a case tree above.
    assert record.case_digest == panel.digest(SMOKE / CASE_DIR)


def test_an_optional_field_is_absent_rather_than_null(tmp_path: Path) -> None:
    """The document carries no delta, no error and no trace, so the record carries none."""
    run = written_document(tmp_path, "pass", SMOKE)
    record = panel.records(run, decide(run, found=1, picked=1).outcomes, DOCKER)[0]
    line = panel.append(tmp_path / "history", [record])[0].read_text()
    for absent in ("delta", "error", "failedGraders", "tracePath", "image", "deniedTools"):
        assert f'"{absent}"' not in line
    assert "null" not in line


def test_a_failing_record_names_every_scored_grader_that_failed(tmp_path: Path) -> None:
    run = written_document(tmp_path, "structural_failures", SMOKE)
    record = panel.records(run, decide(run, found=1, picked=1).outcomes, DOCKER)[0]
    assert record.outcome == "fail"
    assert record.failed_graders == [
        "says-alex",
        "fired-skill",
        "read-then-wrote",
        "wrote-deck",
    ]


def test_a_record_carries_the_first_run_error(tmp_path: Path) -> None:
    run = written_document(tmp_path, "run_error", SMOKE)
    record = panel.records(run, decide(run, found=1, picked=1).outcomes, DOCKER)[0]
    assert record.outcome == "fail"
    assert record.error


def test_a_record_carries_the_validity_fields_traces_wrote(tmp_path: Path) -> None:
    run = written_document(tmp_path, "mode_denial", SMOKE)
    record = panel.records(run, decide(run, found=1, picked=1).outcomes, DOCKER)[0]
    assert record.denied_tools


def test_a_declared_case_records_the_word_the_verdict_reached(tmp_path: Path) -> None:
    run = written_document(tmp_path, "declared_case", SMOKE)
    record = panel.records(run, decide(run, found=1, picked=1).outcomes, COWORK)[0]
    assert record.outcome == "declared"
    assert record.runs == 0
    assert record.duration_seconds == 0.0


def test_a_two_arm_record_carries_the_delta_the_document_worked_out(tmp_path: Path) -> None:
    run = written_document(tmp_path, "two_arm", SMOKE)
    decided = decide(run, found=2, picked=2)
    built = panel.records(run, decided.outcomes, DOCKER)
    assert [record.case for record in built] == ["fires-and-answers", "quiet-case"]
    assert built[0].delta == 1.0
    assert built[0].runs == 1
    assert built[1].delta == 0.0


def test_a_case_the_verdict_never_reached_produces_no_record(tmp_path: Path) -> None:
    """The join is the pair the verdict holds, and a case outside it is not recorded."""
    run = written_document(tmp_path, "pass", SMOKE)
    assert panel.records(run, (), DOCKER) == []
    other = (CaseOutcome(plugin="elsewhere", dir=CASE_DIR, name="x", outcome="pass"),)
    assert panel.records(run, other, DOCKER) == []


def test_a_missing_document_produces_no_record(tmp_path: Path) -> None:
    run = tmp_path / "20260913-101010-smoke"
    (run / "smoke").mkdir(parents=True)
    assert panel.records(run, (), DOCKER) == []


# The join to the case tree.


def test_a_tree_with_no_history_reads_never_run_on_both_backends(tmp_path: Path) -> None:
    built, warnings = smoke_rows(tmp_path)
    assert warnings == []
    assert [row.case for row in built] == list(CASES)
    for row in built:
        if row.case != DECLARED_CASE:
            assert row.cells[DOCKER].outcome == panel.NEVER
            assert row.cells[COWORK].outcome == panel.NEVER
        assert row.score is None
        assert row.flake is None
        assert row.records == 0
        assert row.artefacts is None


def test_a_no_cowork_case_reads_declared_from_its_tag_alone(tmp_path: Path) -> None:
    """The tag is in the tree and is the reason no record will ever appear there."""
    declared = by_case(smoke_rows(tmp_path)[0])[DECLARED_CASE]
    assert declared.cells[COWORK].outcome == "declared"
    assert declared.cells[COWORK].age_days is None
    assert declared.cells[DOCKER].outcome == panel.NEVER


def test_the_description_comes_from_the_tree(tmp_path: Path) -> None:
    row = by_case(smoke_rows(tmp_path)[0])["python-version"]
    assert row.description == read_case(SMOKE / CASE_DIR).frontmatter_keys["description"]


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
    """The record is written by the real `records` over the real tree, then read back."""
    run = written_document(tmp_path / "run", "pass", SMOKE)
    history = tmp_path / "history"
    panel.append(history, panel.records(run, decide(run, found=1, picked=1).outcomes, DOCKER))
    assert by_case(smoke_rows(history)[0])["python-version"].stale is False


def test_a_row_whose_trace_directory_is_gone_says_so(tmp_path: Path) -> None:
    installed(tmp_path, "stale")
    row = by_case(smoke_rows(tmp_path)[0])["python-version"]
    assert row.artefacts == "/nowhere-at-all/traces/python-version/run-1"
    assert row.gone is True


def test_a_row_whose_trace_directory_is_there_is_not_gone(tmp_path: Path) -> None:
    kept = tmp_path / "traces" / "python-version" / "run-1"
    kept.mkdir(parents=True)
    file = installed(tmp_path / "history", "stale")
    found, _ = panel.read(file)
    file.unlink()
    moved = found[0].model_copy(update={"trace_path": str(kept / "trace.jsonl")})
    panel.append(tmp_path / "history", [moved])
    row = by_case(smoke_rows(tmp_path / "history")[0])["python-version"]
    assert row.gone is False


def test_an_unparsable_history_line_is_warned_about_and_the_row_still_renders(
    tmp_path: Path,
) -> None:
    installed(tmp_path, "truncated")
    built, warnings = smoke_rows(tmp_path)
    assert len(warnings) == 1
    assert by_case(built)["python-version"].cells[DOCKER].outcome == "pass"


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
    """The one assertion the renders need: every render is over the same rows."""
    installed(tmp_path, "two_backends")
    built, _ = smoke_rows(tmp_path)
    document = PanelSnapshot.model_validate_json(panel.snapshot(built))

    assert document.schema_version == 1
    assert document.rows == built


def test_the_text_table_and_the_markdown_carry_one_line_per_row(tmp_path: Path) -> None:
    built, _ = smoke_rows(tmp_path)
    assert len(panel.table(built).splitlines()) == len(built) + 1
    assert len(panel.markdown(built).splitlines()) == len(built) + 2


def test_the_text_table_cuts_a_description_the_markdown_carries_whole(tmp_path: Path) -> None:
    built, _ = smoke_rows(tmp_path)
    longest = max((row.description for row in built), key=len)
    assert longest in panel.markdown(built)
    assert longest not in panel.table(built)


def test_the_digest_covers_every_check_file(tmp_path: Path) -> None:
    """Editing an assertion has to move the digest, or `stale` stays green over it."""
    case = tmp_path / "hello"
    (case / "checks").mkdir(parents=True)
    (case / "prompt.md").write_text("---\nname: hello\n---\n\nSay hello.\n", encoding="utf-8")
    before = panel.digest(case)

    path = case / "checks" / "assertions.py"
    path.write_text("from cowork_evals.checks import check\n", encoding="utf-8")
    with_check = panel.digest(case)
    assert with_check != before

    path.write_text("from cowork_evals.checks import check  # edited\n", encoding="utf-8")
    assert panel.digest(case) != with_check


def test_the_digest_hashes_the_checks_after_the_graders(tmp_path: Path) -> None:
    case = tmp_path / "hello"
    (case / "graders").mkdir(parents=True)
    (case / "checks").mkdir()
    (case / "prompt.md").write_text("---\nname: hello\n---\n\nSay hello.\n", encoding="utf-8")
    (case / "graders" / "a.md").write_text("---\ntype: regex\n---\n", encoding="utf-8")
    (case / "checks" / "b.py").write_text("x = 1\n", encoding="utf-8")
    assert [path.name for path in panel._defining(case)] == ["prompt.md", "a.md", "b.py"]
