"""The case reader. One case tree in, one list of `Case` out.

It parses what docs/eval_format.md defines, the way `claude plugin eval` parses it, so every
backend sees the same case set. It is backend-neutral: nothing here knows which backend will run
a case, and nothing here decides a skip.

It refuses nothing a case merely got wrong. A `prompt.md` with no frontmatter is read, with its
missing keys left for the case validator, which cannot report what the reader declined to build.
`CaseError` is for a tree that cannot be read at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

import frontmatter
import yaml

# What makes a directory a case, a case's optional second file, and its grader directory.
# docs/eval_format.md.
PROMPT_FILE = "prompt.md"
CASE_YAML = "case.yaml"
GRADERS_DIR = "graders"

# The case's other assertion directory. It holds this package's own checks, which are Python
# and not Markdown, and the harness neither reads it nor knows it is there. docs/checks.md.
CHECKS_DIR = "checks"

# What makes a directory a plugin root. docs/eval_format.md.
PLUGIN_MANIFEST = Path(".claude-plugin") / "plugin.json"

# The eval directory the harness defaults to, and this repository never configures another.
# It is here rather than under a backend because every reader of a case tree needs it.
# docs/eval_format.md.
EVAL_DIR = "evals"

# Directories the harness never descends into during discovery. Matching it is what keeps
# the case set identical on every backend. docs/claude_code/plugin_eval_reference.md.
PRUNED = frozenset({"node_modules", ".git", ".claude", "results"})

# A grader's default weight. docs/eval_format.md.
DEFAULT_WEIGHT = 1

# Every grader type the format defines, split by how it is graded: a structural grader is
# evaluated over the run's document, and a judged grader asks a model. Both decide the
# verdict. docs/eval_format.md, docs/running_evals.md.
STRUCTURAL = ("regex", "tool_used", "tool_order", "file_exists")
JUDGED = ("llm", "baseline")
GRADER_TYPES = frozenset(STRUCTURAL + JUDGED)

# `source` in the v1 result document. A case is discovered by its `prompt.md`, so
# `case_yaml` cannot occur here. docs/claude_code/plugin_eval_reference.md.
PROSE = "prose"
MIXED = "mixed"

# The one key of `case.yaml` whose children are kept separately, so a reader asks for
# `context.add_dirs` and not for the mapping above it.
CONTEXT = "context"

# The one reserved tag value, and the only one. A case carrying it declares that the CoWork
# backend cannot run it, and the validator enforces that in both directions. It is spelled
# here and nowhere else. docs/eval_format.md.
NO_COWORK = "no-cowork"


class CaseError(Exception):
    """A case tree that cannot be read: unparsable YAML, or no plugin root."""


@dataclass(frozen=True, slots=True)
class Grader:
    """One file under `graders/`. Its frontmatter, split into what every grader has."""

    name: str
    type: str
    weight: int | float
    config: dict[str, Any]
    markdown: str
    path: Path


@dataclass(frozen=True, slots=True)
class Case:
    """One directory holding a `prompt.md`.

    `directory` is that directory and `path` is the `prompt.md` inside it. `name` defaults
    to the directory name, which is the harness's rule for a case with no `case.yaml`.

    `checks` is every file under `checks/`, as paths. They are paths and never loaded
    functions: reading a case tree must not execute the author's code, and a `--dry-run`
    reads the same tree. [checks.py](checks.py) is what imports them, when a run is graded.

    `frontmatter_keys` and `case_yaml_keys` are what each file wrote out, mapped to the
    value as authored. They are the keys, not the merged defaults: a backend honours a key
    the case asked for and ignores one it left alone, and the case validator reports a key
    the format does not allow. A `case.yaml` `context:` mapping is flattened, so its keys
    arrive as `context.add_dirs` and the mapping above them is not a key of its own.
    """

    name: str
    directory: Path
    prompt: str
    graders: tuple[Grader, ...]
    tags: tuple[str, ...]
    source: str
    checks: tuple[Path, ...] = ()
    frontmatter_keys: dict[str, Any] = field(default_factory=dict)
    case_yaml_keys: dict[str, Any] = field(default_factory=dict)
    path: Path = Path(PROMPT_FILE)

    @property
    def no_cowork(self) -> bool:
        """Whether the case carries the reserved tag. It is read here and nowhere else."""
        return NO_COWORK in self.tags


def plugin_root(target: Path | str) -> Path:
    """The nearest directory at or above `target` holding `.claude-plugin/plugin.json`."""
    resolved = Path(target).resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / PLUGIN_MANIFEST).is_file():
            return candidate
    raise CaseError(f"no {PLUGIN_MANIFEST} at or above {resolved}")


def plugin_name(root: Path | str) -> str:
    """The manifest's `name`, and the folder basename when the manifest names none.

    Every reader of a plugin root names it this way: the result document, and the scope
    the run directory is named for. docs/eval_format.md.
    """
    resolved = Path(root).resolve()
    try:
        manifest = json.loads((resolved / PLUGIN_MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return resolved.name
    if not isinstance(manifest, dict):
        return resolved.name
    named = manifest.get("name")
    return named if isinstance(named, str) and named else resolved.name


def plugin_roots(target: Path | str) -> list[Path]:
    """Every plugin root the target covers, sorted by path.

    A path at or under one root is that root. A path covering several is every directory
    below it holding `.claude-plugin/plugin.json` with a sibling `evals/`, which is how a
    marketplace repository is swept without a fixed `plugins/*` glob. docs/library.md.
    """
    resolved = Path(target).resolve()
    below = sorted(
        {
            manifest.parent.parent.resolve()
            for manifest in resolved.rglob(str(PLUGIN_MANIFEST))
            if manifest.is_file() and (manifest.parent.parent / EVAL_DIR).is_dir()
        }
    )
    return below if below else [plugin_root(resolved)]


def discover(
    root: Path | str, *, tags: tuple[str, ...] = (), case_glob: str | None = None
) -> list[Case]:
    """Every case at or under `root`, sorted by path.

    Discovery is recursive and a case directory is a leaf: a directory holding a
    `prompt.md` is read as a case and never searched through, and anything else is
    searched through rather than run.

    `tags` keeps a case carrying any of them, and `case_glob` globs the case `name`, which
    is what the harness globs. They are `--tag` and `--case` in docs/cli.md.
    """
    base = Path(root)
    cases = [read(directory) for directory in sorted(_case_directories(base))]
    if tags:
        wanted = set(tags)
        cases = [case for case in cases if wanted.intersection(case.tags)]
    if case_glob is not None:
        cases = [case for case in cases if fnmatchcase(case.name, case_glob)]
    return cases


def read(directory: Path | str) -> Case:
    """One case directory, already known to hold a `prompt.md`."""
    case_dir = Path(directory)
    prompt_path = case_dir / PROMPT_FILE
    post = _post(prompt_path)
    written = dict(post.metadata)

    yaml_path = case_dir / CASE_YAML
    document = _case_yaml(yaml_path) if yaml_path.is_file() else None
    yaml_written = {} if document is None else _flatten(document)

    # The merge order is the harness's: `case.yaml` is the base and the `prompt.md`
    # frontmatter overrides it. docs/claude_code/plugin_eval_reference.md.
    merged = {**yaml_written, **written}
    name = merged.get("name")
    tags = merged.get("tags")

    return Case(
        name=name if isinstance(name, str) and name else case_dir.name,
        directory=case_dir,
        prompt=post.content,
        graders=_graders(case_dir / GRADERS_DIR),
        tags=tuple(str(tag) for tag in tags) if isinstance(tags, list) else (),
        source=PROSE if document is None else MIXED,
        checks=check_files(case_dir),
        frontmatter_keys=written,
        case_yaml_keys=yaml_written,
        path=prompt_path,
    )


def _case_directories(base: Path) -> list[Path]:
    """Recurse, stopping at a case and at the directories the harness prunes."""
    if not base.is_dir():
        return []
    if (base / PROMPT_FILE).is_file():
        return [base]
    found: list[Path] = []
    for child in sorted(base.iterdir()):
        if child.is_dir() and child.name not in PRUNED:
            found += _case_directories(child)
    return found


def check_files(case_dir: Path | str) -> tuple[Path, ...]:
    """Every `checks/*.py` of one case directory, in path order.

    Public because [validate.py](validate.py), [checks.py](checks.py) and
    [panel.py](panel.py) each walk the same list, and one glob is one rule.
    """
    directory = Path(case_dir) / CHECKS_DIR
    if not directory.is_dir():
        return ()
    return tuple(sorted(directory.glob("*.py")))


def _graders(directory: Path) -> tuple[Grader, ...]:
    """Every grader file, alphabetically, as the harness orders them.

    A file whose metadata is empty is a note, not a grader, and is ignored exactly as the
    harness ignores it. That is the first authoring trap in docs/eval_format.md: a file
    with no `---` delimiters leaves the case running with fewer graders than it appears to
    have.
    """
    if not directory.is_dir():
        return ()
    graders = []
    for path in sorted(directory.glob("*.md")):
        post = _post(path)
        if not post.metadata:
            continue
        metadata = dict(post.metadata)
        name = metadata.pop("name", None)
        kind = metadata.pop("type", None)
        weight = metadata.pop("weight", DEFAULT_WEIGHT)
        graders.append(
            Grader(
                name=name if isinstance(name, str) and name else path.stem,
                type=kind if isinstance(kind, str) else "",
                weight=weight if isinstance(weight, int | float) else DEFAULT_WEIGHT,
                config=metadata,
                markdown=post.content,
                path=path,
            )
        )
    return tuple(graders)


def _post(path: Path) -> frontmatter.Post:
    """One Markdown file, split into frontmatter and body.

    An absent `---` block yields empty metadata, which is what makes a `prompt.md` with no
    frontmatter readable and a grader file with none ignorable.
    """
    try:
        return frontmatter.load(str(path))
    except OSError as error:
        raise CaseError(f"{path}: unreadable: {error}") from error
    except yaml.YAMLError as error:
        raise CaseError(f"{path}: unparsable frontmatter: {error}") from error


def _case_yaml(path: Path) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise CaseError(f"{path}: unreadable: {error}") from error
    except yaml.YAMLError as error:
        raise CaseError(f"{path}: unparsable YAML: {error}") from error
    if document is None:
        return {}
    if not isinstance(document, dict):
        raise CaseError(f"{path}: expected a mapping at the top level")
    return document


def _flatten(document: dict[str, Any]) -> dict[str, Any]:
    """Top level keys as authored, with `context:` replaced by its dotted children."""
    flat: dict[str, Any] = {}
    for key, value in document.items():
        if key == CONTEXT and isinstance(value, dict):
            for inner, held in value.items():
                flat[f"{CONTEXT}.{inner}"] = held
            continue
        flat[key] = value
    return flat
