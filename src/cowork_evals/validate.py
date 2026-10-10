"""The case validator, and the skill coverage report.

It reads what [cases.py](cases.py) produced and reports what docs/eval_format.md calls an error.
It writes nothing, runs no case and refuses nothing: a caller decides what a violation costs,
and docs/cli.md says it costs exit 3 inside `run`'s preflight.

Coverage is separate and is not a rule of the format. A skill with no eval directory is always
reported, and `--require-coverage` is what turns that report into a failure.

`cases.py` reads a case tree without refusing anything a case merely got wrong, so every finding
here is over a `Case` it already built. The one exception is a grader file with no `---` block:
the reader drops it exactly as the harness drops it, so this compares the files on disk against
the graders the reader returned rather than deciding again.

A check file is the one thing here that is executed rather than parsed. `checks/*.py` is Python,
and the only way to know it imports is to import it, so the validator imports every check of
every selected plugin root before anything runs. A file that will not import at the preflight
would otherwise fail the run it was written to decide. docs/checks.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cases import (
    CASE_YAML,
    CHECKS_DIR,
    EVAL_DIR,
    GRADER_TYPES,
    GRADERS_DIR,
    NO_COWORK,
    PRUNED,
    Case,
    discover,
)
from .checks import discover as discover_checks
from .checks import duplicate_names
from .cowork_backend import MOCKS_DIR, unrunnable

# The directory a plugin's skills live in. Coverage is one directory here against one
# directory under `evals/`. docs/eval_format.md.
SKILLS_DIR = "skills"

# The two directories under `evals/` that are not a skill name. `MOCKS_DIR` is the CoWork
# backend's, which is the one module that decides what a `mocks/` directory means.
# docs/eval_format.md.
COMPOSITION_DIR = "plugin"
NON_SKILL_DIRS = frozenset({COMPOSITION_DIR, MOCKS_DIR})

# Every key `prompt.md` frontmatter may carry, and nothing else. docs/eval_format.md.
PROMPT_KEYS = frozenset(
    {
        "name",
        "description",
        "tags",
        "plugins",
        "runs",
        "max_turns",
        "timeout_seconds",
        "model",
        "allowed_tools",
        "append_system_prompt",
        "env",
        "schema_version",
        "expected_outcome",
    }
)

# The keys `prompt.md` must carry. docs/eval_format.md.
REQUIRED_PROMPT_KEYS = ("name", "tags", "plugins")

# Every key `case.yaml` may carry, as `cases.py` flattens them, and the two it must carry.
# docs/eval_format.md.
CASE_YAML_KEYS = frozenset(
    {
        "schema_version",
        "name",
        "context.scaffold_script",
        "context.history_file",
        "context.add_dirs",
    }
)
REQUIRED_CASE_YAML_KEYS = ("schema_version", "name")
CASE_YAML_SCHEMA_VERSION = "1.1"

# The key whose entries are paths, and must stay inside the case directory.
ADD_DIRS = "context.add_dirs"

# The caps, each on the key it bounds. docs/eval_format.md.
CAPS = {"runs": 50, "max_turns": 200, "timeout_seconds": 3600}

# The prefix every `env` key carries. That mapping is the case's execution environment for
# the agent under test, and is not this package's configuration. docs/eval_format.md.
ENV_PREFIX = "EVAL_"


@dataclass(frozen=True, slots=True)
class Violation:
    """One finding: the file it is in, the rule it breaks, and what the file says."""

    path: Path
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}: {self.rule}: {self.detail}"


def violations(root: Path | str) -> list[Violation]:
    """Every violation in one plugin root's `evals/` tree, sorted by path.

    An empty list means the tree is valid. The root is a plugin root, so a caller that
    resolved a narrower target validates the whole plugin: a malformed sibling case is
    still a malformed case. docs/cli.md.
    """
    plugin = Path(root).resolve()
    evals = plugin / EVAL_DIR
    found = _layer_violations(plugin, evals)
    for case in discover(evals):
        found += _case_violations(case, plugin, evals)
    return sorted(found, key=lambda violation: (str(violation.path), violation.rule))


def uncovered(root: Path | str) -> list[str]:
    """One line per skill with no eval directory of its own name.

    Never a violation: coverage is not a rule of the format. `--require-coverage` is what
    makes a line here fail a preflight. docs/cli.md.
    """
    plugin = Path(root).resolve()
    evals = plugin / EVAL_DIR
    return [
        f"{plugin / SKILLS_DIR / name}: no eval directory at {evals / name}"
        for name in _skill_names(plugin)
        if not (evals / name).is_dir()
    ]


# The layer directly under `evals/`.


def _skill_names(plugin: Path) -> list[str]:
    """Every directory under `<plugin>/skills/`, sorted. No `skills/` means no skill."""
    skills = plugin / SKILLS_DIR
    if not skills.is_dir():
        return []
    return sorted(child.name for child in skills.iterdir() if child.is_dir())


def _layer_violations(plugin: Path, evals: Path) -> list[Violation]:
    """A directory directly under `evals/` is `plugin`, `mocks`, or a skill name.

    A plugin with no `skills/` directory admits only the first two, so a tree that names a
    skill it does not have is reported rather than run against nothing.
    """
    if not evals.is_dir():
        return []
    allowed = NON_SKILL_DIRS.union(_skill_names(plugin))
    named = ", ".join(sorted(allowed))
    return [
        Violation(
            path=child,
            rule="skill-layer",
            detail=f"a directory under {EVAL_DIR}/ is one of: {named}",
        )
        for child in sorted(evals.iterdir())
        if child.is_dir() and child.name not in PRUNED and child.name not in allowed
    ]


# One case.


def _case_violations(case: Case, plugin: Path, evals: Path) -> list[Violation]:
    skill = _skill_of(case, evals)
    return [
        *_prompt_violations(case, plugin, skill),
        *_runnability_violations(case, plugin),
        *_case_yaml_violations(case),
        *_grader_violations(case),
        *_check_violations(case),
    ]


def _runnability_violations(case: Case, plugin: Path) -> list[Violation]:
    """The reserved tag, checked in both directions. docs/eval_format.md.

    `cowork_backend.unrunnable` is the one derivation of what a CoWork session cannot run,
    and the backend reads the same function, so the validator and the backend cannot
    disagree about one case.

    The second direction is what keeps the tag from becoming a way to switch a case off.
    """
    reasons = unrunnable(case, plugin)
    if reasons and not case.no_cowork:
        return [
            Violation(
                path=case.path,
                rule="no-cowork-missing",
                detail=f"{reason}, and tags does not carry {NO_COWORK}",
            )
            for reason in reasons
        ]
    if case.no_cowork and not reasons:
        return [
            Violation(
                path=case.path,
                rule="no-cowork-unneeded",
                detail=f"tags carries {NO_COWORK}, and a CoWork session can run this case",
            )
        ]
    return []


def _skill_of(case: Case, evals: Path) -> str | None:
    """The `<skill>` directory the case sits under, or `None` for a case outside one."""
    resolved = case.directory.resolve()
    if not resolved.is_relative_to(evals):
        return None
    parts = resolved.relative_to(evals).parts
    return parts[0] if len(parts) > 1 else None


def _prompt_violations(case: Case, plugin: Path, skill: str | None) -> list[Violation]:
    path = case.path
    written = case.frontmatter_keys
    found = [
        Violation(path=path, rule="required-key", detail=f"{key} is required")
        for key in REQUIRED_PROMPT_KEYS
        if key not in written
    ]
    found += [
        Violation(
            path=path,
            rule="unknown-key",
            detail=f"{key} is not a frontmatter key of the format",
        )
        for key in sorted(written)
        if key not in PROMPT_KEYS
    ]
    found += _cap_violations(path, written)
    found += _env_violations(path, written.get("env"))
    if "tags" in written and skill is not None and skill not in case.tags:
        found.append(
            Violation(
                path=path,
                rule="tags",
                detail=f"tags names {list(case.tags)}, and the case sits under {skill}/",
            )
        )
    if "plugins" in written:
        found += _plugins_violations(case, plugin, written["plugins"])
    return found


def _cap_violations(path: Path, written: dict[str, Any]) -> list[Violation]:
    return [
        Violation(
            path=path,
            rule="cap",
            detail=f"{key} is {written[key]}, and the cap is {cap}",
        )
        for key, cap in CAPS.items()
        if isinstance(written.get(key), int | float)
        and not isinstance(written.get(key), bool)
        and written[key] > cap
    ]


def _env_violations(path: Path, env: Any) -> list[Violation]:
    if not isinstance(env, dict):
        return []
    return [
        Violation(
            path=path,
            rule="env-prefix",
            detail=f"env key {key} does not start with {ENV_PREFIX}",
        )
        for key in sorted(env)
        if not str(key).startswith(ENV_PREFIX)
    ]


def _plugins_violations(case: Case, plugin: Path, declared: Any) -> list[Violation]:
    """`plugins` states the plugin root a second time, and the two must agree.

    The harness reads the frontmatter and the CoWork backend resolves the path, so a
    disagreement runs one plugin and grades another. docs/cli.md.
    """
    path = case.path
    if not isinstance(declared, list):
        return [
            Violation(
                path=path,
                rule="plugins",
                detail=f"plugins is {declared!r}, and it is a list of paths",
            )
        ]
    resolved = [(case.directory / str(entry)).resolve() for entry in declared]
    if plugin in resolved:
        return []
    named = ", ".join(str(entry) for entry in resolved) or "nothing"
    return [
        Violation(
            path=path,
            rule="plugins",
            detail=f"plugins resolves to {named}, and the plugin root is {plugin}",
        )
    ]


def _case_yaml_violations(case: Case) -> list[Violation]:
    written = case.case_yaml_keys
    if not written:
        return []
    path = case.directory / CASE_YAML
    found = [
        Violation(path=path, rule="required-key", detail=f"{key} is required")
        for key in REQUIRED_CASE_YAML_KEYS
        if key not in written
    ]
    found += [
        Violation(path=path, rule="unknown-key", detail=f"{key} is not a key of case.yaml")
        for key in sorted(written)
        if key not in CASE_YAML_KEYS
    ]
    version = written.get("schema_version")
    if "schema_version" in written and version != CASE_YAML_SCHEMA_VERSION:
        found.append(
            Violation(
                path=path,
                rule="schema-version",
                detail=f"schema_version is {version!r}, and it is {CASE_YAML_SCHEMA_VERSION!r}",
            )
        )
    found += _add_dirs_violations(case, path, written.get(ADD_DIRS))
    return found


def _add_dirs_violations(case: Case, path: Path, declared: Any) -> list[Violation]:
    """Every staged directory stays inside the case that uses it, and none of them is
    `checks/`. docs/eval_format.md.

    The harness refuses the case's own `graders/` itself. It knows nothing about `checks/`
    and would grant it as a fixture directory, so refusing it is this repository's and is
    not redundant: a case that stages its own assertions into the agent's working directory
    is telling the agent what it is about to be judged on.
    """
    if not isinstance(declared, list):
        return []
    directory = case.directory.resolve()
    checks_dir = (case.directory / CHECKS_DIR).resolve()
    found = []
    for entry in declared:
        resolved = (case.directory / str(entry)).resolve()
        if not resolved.is_relative_to(directory):
            found.append(
                Violation(
                    path=path,
                    rule="add-dirs",
                    detail=f"{entry} resolves to {resolved}, outside {directory}",
                )
            )
        elif resolved.is_relative_to(checks_dir):
            found.append(
                Violation(
                    path=path,
                    rule="add-dirs-checks",
                    detail=f"{entry} resolves to {resolved}, and {CHECKS_DIR}/ is not staged",
                )
            )
    return found


def _grader_violations(case: Case) -> list[Violation]:
    found = [
        Violation(
            path=path,
            rule="grader-frontmatter",
            detail="no --- block, so the harness reads it as a note and ignores it",
        )
        for path in _unread_grader_files(case)
    ]
    for grader in case.graders:
        if grader.type not in GRADER_TYPES:
            found.append(
                Violation(
                    path=grader.path,
                    rule="grader-type",
                    detail=f"type is {grader.type!r}, and it is one of: "
                    f"{', '.join(sorted(GRADER_TYPES))}",
                )
            )
        if not grader.weight > 0:
            found.append(
                Violation(
                    path=grader.path,
                    rule="grader-weight",
                    detail=f"weight is {grader.weight}, and it is above 0",
                )
            )
    return found


def _check_violations(case: Case) -> list[Violation]:
    """Every check file imports, every check has a name of its own, and `checks/` holds one.

    A `checks/` directory holding no check at all asserts nothing while looking as if it
    does. A single file holding none is not a violation: a helper beside a check is a file
    like any other, which is why the rule is over the directory and never over a file.

    A file that fails to import is still a check, named for its file, so it can collide with
    a check of the same name: `x.y.py` and check `y` in `x.py` are both `x.y`. Both rules are
    reported.
    """
    directory = case.directory / CHECKS_DIR
    if not directory.is_dir():
        return []
    found = discover_checks(case.directory)
    if not found:
        return [
            Violation(
                path=directory,
                rule="check-empty",
                detail=f"no file under {CHECKS_DIR}/ carries a function decorated with @check",
            )
        ]
    broken = [
        Violation(path=one.path, rule="check-import", detail=one.error)
        for one in found
        if one.error is not None
    ]
    return broken + [
        Violation(
            path=directory,
            rule="check-duplicate",
            detail=f"{name} is the name of more than one check",
        )
        for name in duplicate_names(found)
    ]


def _unread_grader_files(case: Case) -> list[Path]:
    """Every file under `graders/` the reader dropped, which is every file with no `---`.

    The reader owns that decision, so this subtracts what it returned from what is on disk
    rather than parsing the frontmatter a second time.
    """
    directory = case.directory / GRADERS_DIR
    if not directory.is_dir():
        return []
    read = {grader.path for grader in case.graders}
    return [path for path in sorted(directory.glob("*.md")) if path not in read]
