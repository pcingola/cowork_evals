"""The case reader over hand-written case trees.

Every tree is under tests/data/cases/, every expected value is a literal, and nothing here
runs a case. The format is docs/eval_format.md. See ../README.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cowork_evals.cases import (
    Case,
    CaseError,
    LlmGraderConfig,
    RegexConfig,
    discover,
    plugin_root,
    read,
)

ROOT = Path(__file__).resolve().parent.parent / "data" / "cases"
TREE = ROOT / "tree"
EVALS = TREE / "evals"


def by_name(cases: list[Case]) -> dict[str, Case]:
    return {case.name: case for case in cases}


# Discovery.


def test_discovery_finds_every_case_and_nothing_else() -> None:
    cases = discover(EVALS)
    assert [case.name for case in cases] == [
        "greets-alex",
        "no-frontmatter",
        "inner-case",
        "staged",
    ]


def test_discovery_is_sorted_by_path() -> None:
    cases = discover(EVALS)
    assert [str(case.directory) for case in cases] == sorted(str(c.directory) for c in cases)


def test_a_grouping_directory_is_searched_through_and_is_not_a_case() -> None:
    found = {case.directory for case in discover(EVALS)}
    assert EVALS / "plugin" / "group" not in found
    assert EVALS / "plugin" / "group" / "inner" in found


def test_a_pruned_directory_is_never_descended_into() -> None:
    """`results/` is where the harness writes, and it is not searched for cases."""
    assert not [case for case in discover(EVALS) if "results" in str(case.directory)]


def test_discovery_of_an_absent_root_is_empty(tmp_path: Path) -> None:
    assert discover(tmp_path / "absent") == []


def test_a_tag_filter_keeps_a_case_carrying_any_of_them() -> None:
    assert [case.name for case in discover(EVALS, tags=("greeter",))] == ["greets-alex"]
    assert [case.name for case in discover(EVALS, tags=("plugin",))] == ["inner-case", "staged"]
    assert discover(EVALS, tags=("absent",)) == []


def test_a_case_carrying_the_reserved_tag_is_still_selected_by_its_skill_tag() -> None:
    """`no-cowork` is one more tag, so a case carrying it and `greeter` answers to either.

    `every-key` writes the keys a CoWork session cannot honour, which is why it carries the
    tag. docs/eval_format.md.
    """
    selected = by_name(discover(EVALS, tags=("greeter",)))
    assert list(selected) == ["greets-alex"]
    assert selected["greets-alex"].no_cowork is True
    assert by_name(discover(EVALS))["inner-case"].no_cowork is False


def test_a_case_glob_matches_the_case_name_and_not_the_directory_name() -> None:
    """`greets-alex` lives in `every-key/`, so the two selectors differ here."""
    assert [case.name for case in discover(EVALS, case_glob="greets-*")] == ["greets-alex"]
    assert discover(EVALS, case_glob="every-key") == []


# One case, read.


def test_every_frontmatter_key_is_kept_as_authored() -> None:
    case = read(EVALS / "greeter" / "every-key")
    assert case.frontmatter_keys == {
        "schema_version": "1.1",
        "name": "greets-alex",
        "description": "Every key the format allows, written out.",
        "tags": ["greeter", "smoke", "no-cowork"],
        "plugins": ["../../.."],
        "runs": 2,
        "max_turns": 12,
        "timeout_seconds": 600,
        "model": "sonnet",
        "allowed_tools": ["Read", "Skill"],
        "append_system_prompt": "Answer in one sentence.",
        "env": {"EVAL_FIXTURE": "one"},
        "expected_outcome": "The reply names Alex.",
    }
    assert case.name == "greets-alex"
    assert case.tags == ("greeter", "smoke", "no-cowork")
    assert case.prompt == "Say hello to Alex."
    assert case.source == "prose"
    assert case.case_yaml_keys == {}
    assert case.directory == EVALS / "greeter" / "every-key"
    assert case.path == EVALS / "greeter" / "every-key" / "prompt.md"


def test_a_prompt_with_no_frontmatter_is_read_and_not_refused() -> None:
    case = read(EVALS / "greeter" / "no-frontmatter")
    assert case.frontmatter_keys == {}
    assert case.name == "no-frontmatter", "the directory name is the harness's default"
    assert case.tags == ()
    assert case.graders == ()
    assert case.prompt == "Run `python3 -V` and reply with its output and nothing else."


def test_a_grader_carries_its_split_frontmatter_and_its_body() -> None:
    graders = {grader.name: grader for grader in read(EVALS / "greeter" / "every-key").graders}
    assert sorted(graders) == ["mentions-alex", "tone"]

    regex = graders["mentions-alex"]
    assert regex.type == "regex"
    assert regex.weight == 2
    assert regex.config == RegexConfig(target="last_message", pattern="Alex", match="contains")
    assert regex.markdown == ""
    assert regex.path.name == "mentions-alex.md"

    judged = graders["tone"]
    assert judged.type == "llm"
    assert judged.weight == 1, "the default weight"
    assert judged.config == LlmGraderConfig(focus="last_message")
    assert judged.markdown == "The reply is warm and personal."


def test_graders_are_ordered_by_filename_and_a_name_defaults_to_it() -> None:
    """`friendly-tone.md` names itself `tone`, so the order is the file's, not the name's."""
    graders = read(EVALS / "greeter" / "every-key").graders
    assert [grader.path.name for grader in graders] == [
        "friendly-tone.md",
        "mentions-alex.md",
    ]
    assert graders[1].name == "mentions-alex", "the filename, since the file names none"


def test_a_grader_file_with_no_frontmatter_is_ignored() -> None:
    """The first authoring trap: a note under graders/ is not a grader."""
    names = [grader.name for grader in read(EVALS / "greeter" / "every-key").graders]
    assert "notes" not in names


def test_a_case_yaml_is_read_and_its_context_keys_are_kept() -> None:
    case = read(EVALS / "plugin" / "staged")
    assert case.case_yaml_keys == {
        "schema_version": "1.1",
        "name": "staged",
        "context.add_dirs": ["resources"],
        "context.scaffold_script": "fixture.sh",
    }
    assert "context" not in case.case_yaml_keys
    assert case.source == "mixed"
    assert case.name == "staged", "the case.yaml name, since the frontmatter writes none"
    assert case.tags == ("plugin", "no-cowork"), "the frontmatter overrides the case.yaml"
    assert case.frontmatter_keys == {"tags": ["plugin", "no-cowork"]}


# The plugin root.


def test_the_plugin_root_is_the_nearest_manifest_above_the_case() -> None:
    case = EVALS / "greeter" / "every-key"
    assert plugin_root(case) == TREE.resolve()
    assert plugin_root(TREE) == TREE.resolve(), "the root itself is a target the CLI accepts"


def test_a_target_under_no_plugin_raises() -> None:
    with pytest.raises(CaseError):
        plugin_root(ROOT / "orphan" / "evals" / "skill" / "case")


# What cannot be read at all.


def test_an_unparsable_case_yaml_raises() -> None:
    with pytest.raises(CaseError):
        read(ROOT / "broken" / "evals" / "plugin" / "bad-yaml")
