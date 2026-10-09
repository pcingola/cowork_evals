"""The case reader over hand-written case trees.

Every tree is under tests/data/, every expected value is a literal, and nothing here runs a
case. The format is docs/eval_format.md. See ../README.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cowork_evals.cases import (
    CaseError,
    LlmGraderConfig,
    RegexConfig,
    discover,
    plugin_root,
    plugin_roots,
    read,
)

DATA = Path(__file__).resolve().parent.parent / "data"
ROOT = DATA / "cases"
TREE = ROOT / "tree"
EVALS = TREE / "evals"
CHECKED = DATA / "checks" / "plugin" / "evals" / "plugin"
MARKETPLACE = DATA / "cli" / "marketplace"


# Discovery.


def test_discovery_finds_every_case_and_nothing_else() -> None:
    """`plugin/group` is searched through and is not a case, and `results/` is pruned."""
    cases = discover(EVALS)
    assert [case.directory.relative_to(EVALS).as_posix() for case in cases] == [
        "greeter/every-key",
        "greeter/no-frontmatter",
        "plugin/group/inner",
        "plugin/staged",
    ]
    assert [case.name for case in cases] == [
        "greets-alex",
        "no-frontmatter",
        "inner-case",
        "staged",
    ]


@pytest.mark.parametrize(
    ("tags", "names"),
    [
        (("greeter",), ["greets-alex"]),
        (("plugin",), ["inner-case", "staged"]),
        (("absent",), []),
        (("greeter", "plugin"), ["greets-alex", "inner-case", "staged"]),
    ],
)
def test_a_tag_filter_keeps_a_case_carrying_any_of_them(
    tags: tuple[str, ...], names: list[str]
) -> None:
    assert [case.name for case in discover(EVALS, tags=tags)] == names


def test_no_cowork_is_read_from_tags() -> None:
    assert read(EVALS / "greeter" / "every-key").no_cowork is True
    assert read(EVALS / "plugin" / "group" / "inner").no_cowork is False


def test_a_case_glob_matches_the_case_name_and_not_the_directory_name() -> None:
    """`greets-alex` lives in `every-key/`, so the two selectors differ here."""
    assert [case.name for case in discover(EVALS, case_glob="greets-*")] == ["greets-alex"]
    assert discover(EVALS, case_glob="every-key") == []


# One case, read.


def test_a_prose_case_is_read() -> None:
    case = read(EVALS / "greeter" / "every-key")
    assert case.name == "greets-alex"
    assert case.tags == ("greeter", "smoke", "no-cowork")
    assert case.prompt == "Say hello to Alex."
    assert case.source == "prose"
    assert case.path == EVALS / "greeter" / "every-key" / "prompt.md"


def test_a_prompt_with_no_frontmatter_is_read_and_not_refused() -> None:
    case = read(EVALS / "greeter" / "no-frontmatter")
    assert case.name == "no-frontmatter", "the directory name is the harness's default"
    assert case.tags == ()
    assert case.graders == ()
    assert case.prompt == "Run `python3 -V` and reply with its output and nothing else."


def test_a_grader_carries_its_split_frontmatter_and_its_body() -> None:
    """File order, not name order: `friendly-tone.md` names itself `tone`. `mentions-alex`
    is the filename, since the file names none. `notes.md` has no frontmatter and is not a
    grader."""
    judged, regex = read(EVALS / "greeter" / "every-key").graders
    assert [judged.name, regex.name] == ["tone", "mentions-alex"]

    assert regex.type == "regex"
    assert regex.weight == 2
    assert isinstance(regex.config, RegexConfig)
    assert (regex.config.target, regex.config.pattern, regex.config.match) == (
        "last_message",
        "Alex",
        "contains",
    )
    assert regex.markdown == ""

    assert judged.type == "llm"
    assert judged.weight == 1, "the default weight"
    assert isinstance(judged.config, LlmGraderConfig)
    assert (judged.config.focus, judged.config.criteria) == ("last_message", None)
    assert judged.markdown == "The reply is warm and personal."


def test_case_yaml_is_the_base_and_prompt_md_overrides_it() -> None:
    staged = read(EVALS / "plugin" / "staged")
    assert staged.source == "mixed"
    assert staged.name == "staged", "the case.yaml name, since the frontmatter writes none"
    assert read(ROOT / "merge" / "evals" / "plugin" / "override").name == "from-prompt-md"


def test_the_case_reader_carries_the_check_files_in_path_order() -> None:
    case = read(CHECKED / "checked")
    assert [path.name for path in case.checks] == ["assertions.py", "helpers.py"]
    assert read(CHECKED / "broken").checks == (CHECKED / "broken" / "checks" / "unimportable.py",)


# The plugin root.


def test_the_plugin_root_is_the_nearest_manifest_above_the_case() -> None:
    case = EVALS / "greeter" / "every-key"
    assert plugin_root(case) == TREE.resolve()
    assert plugin_root(TREE) == TREE.resolve(), "the root itself is a target the CLI accepts"


def test_a_target_under_no_plugin_raises() -> None:
    with pytest.raises(CaseError):
        plugin_root(ROOT / "orphan" / "evals" / "skill" / "case")


@pytest.mark.parametrize(
    ("target", "roots"),
    [
        (MARKETPLACE, ["first", "second"]),
        (MARKETPLACE / "first" / "evals" / "greeter" / "hello", ["first"]),
    ],
)
def test_plugin_roots_finds_each_root_with_an_evals_sibling(target: Path, roots: list[str]) -> None:
    """`library/` holds a manifest and no `evals/`, so it is not a root."""
    assert plugin_roots(target) == [(MARKETPLACE / name).resolve() for name in roots]
