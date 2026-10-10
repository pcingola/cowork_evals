"""The case validator and the coverage report over hand-written trees.

Every tree is under tests/data/validate/, every expected value is a literal, and nothing
here runs a case. The rules are docs/eval_format.md. See ../README.md.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from cowork_evals.validate import uncovered, violations

ROOT = Path(__file__).resolve().parent.parent / "data" / "validate"
CLEAN = ROOT / "clean"
BROKEN = ROOT / "broken"
UNCOVERED = ROOT / "uncovered"
EVALS = BROKEN / "evals" / "greeter"

CaseTree = Callable[..., tuple[Path, Path]]


# The clean tree.


def test_a_clean_tree_has_no_violation() -> None:
    assert violations(CLEAN) == []


def test_a_clean_tree_covers_every_skill() -> None:
    assert uncovered(CLEAN) == []


# The broken tree, whole.


def test_the_broken_tree_breaks_each_rule_in_path_order() -> None:
    """One case per rule, and no rule fires that the case was not written to break."""
    found = [(one.path.relative_to(BROKEN).as_posix(), one.rule) for one in violations(BROKEN)]
    greeter = "evals/greeter"
    assert found == [
        (f"{greeter}/bad-case-yaml/case.yaml", "required-key"),
        (f"{greeter}/bad-case-yaml/case.yaml", "schema-version"),
        (f"{greeter}/bad-case-yaml/case.yaml", "unknown-key"),
        (f"{greeter}/bad-checks/checks/unimportable.py", "check-import"),
        (f"{greeter}/bad-graders/graders/note.md", "grader-frontmatter"),
        (f"{greeter}/bad-graders/graders/unknown-type.md", "grader-type"),
        (f"{greeter}/bad-graders/graders/zero-weight.md", "grader-weight"),
        (f"{greeter}/duplicate-checks/checks", "check-duplicate"),
        (f"{greeter}/duplicate-checks/checks/x.y.py", "check-import"),
        (f"{greeter}/empty-checks/checks", "check-empty"),
        (f"{greeter}/escaping/case.yaml", "add-dirs"),
        (f"{greeter}/missing-keys/prompt.md", "required-key"),
        (f"{greeter}/missing-keys/prompt.md", "required-key"),
        (f"{greeter}/missing-keys/prompt.md", "required-key"),
        (f"{greeter}/over-caps/prompt.md", "cap"),
        (f"{greeter}/over-caps/prompt.md", "cap"),
        (f"{greeter}/over-caps/prompt.md", "cap"),
        (f"{greeter}/over-caps/prompt.md", "env-prefix"),
        (f"{greeter}/staged-checks/case.yaml", "add-dirs-checks"),
        (f"{greeter}/unknown-key/prompt.md", "unknown-key"),
        (f"{greeter}/unknown-key/prompt.md", "unknown-key"),
        (f"{greeter}/wrong-plugins/prompt.md", "plugins"),
        (f"{greeter}/wrong-tag/prompt.md", "tags"),
        ("evals/not-a-skill", "skill-layer"),
    ]


# The layer directly under evals/.


def test_the_skill_layer_names_the_directories_it_admits() -> None:
    only = [
        violation
        for violation in violations(BROKEN)
        if violation.path == BROKEN / "evals" / "not-a-skill"
    ]
    assert only[0].detail == "a directory under evals/ is one of: greeter, mocks, plugin"


def test_a_plugin_with_no_skills_directory_admits_plugin_and_mocks_only(tmp_path: Path) -> None:
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text('{"name": "bare"}')
    for name in ("plugin", "mocks", "greeter"):
        (tmp_path / "evals" / name).mkdir(parents=True)
    found = violations(tmp_path)
    assert [violation.path for violation in found] == [tmp_path / "evals" / "greeter"]
    assert uncovered(tmp_path) == [], "no skill, so no coverage gap"


# prompt.md.


def test_a_missing_required_key_is_reported_once_per_key() -> None:
    path = EVALS / "missing-keys" / "prompt.md"
    found = [violation for violation in violations(BROKEN) if violation.path == path]
    assert sorted(violation.detail for violation in found) == [
        "name is required",
        "plugins is required",
        "tags is required",
    ]


def test_a_key_outside_the_format_is_a_violation_including_context() -> None:
    path = EVALS / "unknown-key" / "prompt.md"
    found = [
        violation
        for violation in violations(BROKEN)
        if violation.path == path and violation.rule == "unknown-key"
    ]
    assert [violation.detail for violation in found] == [
        "colour is not a frontmatter key of the format",
        "context.add_dirs is not a frontmatter key of the format",
    ]


def test_every_cap_is_checked_and_an_env_key_carries_its_prefix() -> None:
    path = EVALS / "over-caps" / "prompt.md"
    found = [violation for violation in violations(BROKEN) if violation.path == path]
    assert sorted(violation.detail for violation in found) == [
        "env key NOT_PREFIXED does not start with EVAL_",
        "max_turns is 201, and the cap is 200",
        "runs is 51, and the cap is 50",
        "timeout_seconds is 3601, and the cap is 3600",
    ]


def test_a_value_at_the_cap_is_not_a_violation(tmp_path: Path, case_tree: CaseTree) -> None:
    root, _ = case_tree(
        tmp_path,
        frontmatter="runs: 50\nmax_turns: 200\ntimeout_seconds: 3600",
        tags="[skill, no-cowork]",
    )
    assert violations(root) == []


# case.yaml.


def test_case_yaml_requires_its_two_keys_and_refuses_a_third() -> None:
    path = EVALS / "bad-case-yaml" / "case.yaml"
    found = [violation for violation in violations(BROKEN) if violation.path == path]
    assert sorted(violation.detail for violation in found) == [
        "expected_outcome is not a key of case.yaml",
        "name is required",
        "schema_version is '1.0', and it is '1.1'",
    ]


# The reserved tag, in both directions.


def test_an_unhonoured_key_with_no_tag_is_a_violation_naming_the_key(
    tmp_path: Path, case_tree: CaseTree
) -> None:
    root, _ = case_tree(tmp_path, frontmatter="max_turns: 10")
    found = violations(root)
    assert [violation.rule for violation in found] == ["no-cowork-missing"]
    assert found[0].detail.endswith("and tags does not carry no-cowork")


def test_the_tag_on_a_case_nothing_stops_is_a_violation(
    tmp_path: Path, case_tree: CaseTree
) -> None:
    """The second direction, which is what keeps the tag from switching a case off."""
    root, _ = case_tree(tmp_path, tags="[skill, no-cowork]")
    found = violations(root)
    assert [violation.rule for violation in found] == ["no-cowork-unneeded"]
    assert found[0].detail == "tags carries no-cowork, and a CoWork session can run this case"


# Coverage.


def test_a_skill_with_no_eval_directory_is_reported_and_is_not_a_violation() -> None:
    assert violations(UNCOVERED) == []
    assert uncovered(UNCOVERED) == [
        f"{UNCOVERED / 'skills' / 'writer'}: no eval directory at {UNCOVERED / 'evals' / 'writer'}"
    ]
