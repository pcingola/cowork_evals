"""Where the shipped documentation and the shipped data files are, in either layout.

The package is read from two layouts and they place `docs/` differently. In an install the
tree sits beside the modules at `cowork_evals/docs/`, put there by the wheel's `force-include`.
In a checkout the package is installed editable, `__file__` points into `src/cowork_evals/`,
and the tree is two levels above at the repository root. The rule is: the installed layout
first, the checkout second, and nothing else is searched.

That is the same edge rule R1 in docs/library.md is about, and it is why no module links to a
document: the relative path differs between the two, so a document is named and this module
resolves the name.

`data/` needs no such rule. It is package data in both layouts and is always beside the
modules.
"""

from __future__ import annotations

from pathlib import Path

from .cases import PLUGIN_MANIFEST

# The package root, in whichever layout this is.
PACKAGE = Path(__file__).resolve().parent

# Package data. Beside the modules in both layouts.
DATA = PACKAGE / "data"
EXAMPLE_CONFIG = DATA / "cowork_evals.example.yaml"

# Every shipped skill, one directory each. `init` installs each of them, so a skill added to
# this tree needs no change here and no change in the verb. docs/library.md.
SKILLS = DATA / "skills"
SKILL_FILE = "SKILL.md"

# What `init` writes into the working directory, and where. docs/cli.md.
CONFIG_NAME = "cowork_evals.yaml"
SKILLS_TARGET = Path(".claude") / "skills"
MEMORY_NAME = "CLAUDE.md"

# The block `init` appends to the consumer's CLAUDE.md, and the marker that says it is
# already there. The marker is the heading, so an edited block is still recognised and is
# never appended twice. docs/cli.md.
MEMORY_MARKER = "## Evals, with cowork_evals"
MEMORY_BLOCK = """
## Evals, with cowork_evals

Evals for the plugins in this repository run through the `cowork_evals` command. Everything
it does goes through that one executable.

- `cowork_evals docs` prints where its documentation is, and `cowork_evals docs <name>`
  prints one document's path. `docs eval_format` is the case format, `docs eval_design` is
  which cases a skill needs, and `docs cli` is the command.
- `cowork_evals run --docker <path>` runs a case tree and decides pass or fail on it.
  `cowork_evals test --docker <path>/tests` runs a plugin's own pytest suite on the CoWork
  runtime, with no model.
- `cowork_evals check --all` reports what each backend still needs.
- `cowork_evals ask --cowork "<prompt>"` submits one prompt to a real CoWork session and
  prints the answer. It runs no eval. Use it when the answer is a fact about the live
  product, and read `cowork_evals docs cli` for what one ask costs.
- The case format, the authoring traps and the interview that decides which cases a skill
  needs are the `cowork-evals` skill in `.claude/skills/cowork-evals/`, and asking a live
  session is `cowork-ask` beside it. Ask what the skill has to get right before writing a
  case. Never ask which eval and which grader are wanted.

A CoWork session is Python 3.10 with a fixed wheel set. Every skill, command, agent and hook
under a path passed to `cowork_evals run` imports only what that image carries. Read
`cowork_evals docs runtime` before adding an import to plugin code.

`cowork_evals.yaml` holds every setting and is the only route: nothing is read from the
process environment except the variables `docker.env_passthrough` names, which are forwarded
into the run container, and there is no `.env`.
"""

# The documentation tree, tried in this order. The first that is a directory wins.
_DOCS_CANDIDATES = (
    PACKAGE / "docs",  # an install: the wheel places the tree beside the modules
    PACKAGE.parent.parent / "docs",  # a checkout: src/cowork_evals -> src -> the root
)

# The extension every document carries. A name may be given with it or without.
SUFFIX = ".md"


def skills() -> list[tuple[Path, Path]]:
    """Every shipped skill, as `(source, target)`, sorted by name.

    The target is `.claude/skills/<directory name>/SKILL.md`, relative to the working
    directory, which is where a Claude Code session picks up a project skill. The directory
    name is the skill name, so the two cannot drift.

    A directory under `skills/` with no `SKILL.md` is not a skill and is not listed.
    """
    if not SKILLS.is_dir():
        return []
    return sorted(
        (directory / SKILL_FILE, SKILLS_TARGET / directory.name / SKILL_FILE)
        for directory in SKILLS.iterdir()
        if (directory / SKILL_FILE).is_file()
    )


def skill(name: str) -> Path:
    """One shipped skill's source path, named. It is not checked for existence here."""
    return SKILLS / name / SKILL_FILE


def docs_dir() -> Path | None:
    """The documentation tree, or `None` when neither layout has one.

    `None` is a package built without the tree. It is not an error here: `docs` reports it,
    and every other verb runs without documentation.
    """
    for candidate in _DOCS_CANDIDATES:
        if candidate.is_dir():
            return candidate
    return None


def _inside_plugin(path: Path, root: Path) -> bool:
    """Whether a plugin root sits at or above `path`, below `root`.

    The tree vendors one worked example as a real plugin, and its `prompt.md` and grader
    files are cases rather than documents. A plugin root is what makes the difference, and
    it is the same marker the case reader uses.
    """
    for parent in path.parents:
        if (parent / PLUGIN_MANIFEST).is_file():
            return True
        if parent == root:
            return False
    return False


def documents() -> list[str]:
    """Every document name, relative to the tree and without its extension, sorted.

    A name is what `docs <name>` takes, so a nested document is `claude_code/README` and not
    a bare basename: two directories hold a `README.md`, and a basename could not tell them
    apart.

    A file inside a vendored plugin root is a case, not a document, and is not listed. The
    plugin still ships: it is a worked example a consumer can run, and `docs claude_code/README`
    says where it is.
    """
    root = docs_dir()
    if root is None:
        return []
    return sorted(
        str(path.relative_to(root).with_suffix(""))
        for path in root.rglob(f"*{SUFFIX}")
        if not _inside_plugin(path, root)
    )


def document(name: str) -> Path | None:
    """One document's path, or `None` when the name is not one of `documents()`.

    The extension is optional, so `cli` and `cli.md` are the same document. The name is
    matched against the list rather than joined onto the root, so nothing outside the tree
    is reachable through it.
    """
    wanted = name[: -len(SUFFIX)] if name.endswith(SUFFIX) else name
    root = docs_dir()
    if root is None or wanted not in documents():
        return None
    return root / f"{wanted}{SUFFIX}"
