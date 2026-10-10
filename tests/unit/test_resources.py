"""The shipped documentation and data, and the reference rules over them.

These tests run in the checkout layout. R1 and R2 in docs/library.md are checked over the
repository's own files.
"""

from __future__ import annotations

import os
import re
from dataclasses import replace
from pathlib import Path

import pytest

from cowork_evals import resources
from cowork_evals.config import Config

REPOSITORY = Path(__file__).resolve().parents[2]

# A markdown link, capturing its target. The target is everything up to the closing bracket,
# so a link carrying a title would be caught too; this repository writes none.
LINK = re.compile(r"\]\(([^)]+)\)")


def test_every_listed_name_resolves_to_a_file() -> None:
    names = resources.documents()
    assert names
    for name in names:
        path = resources.document(name)
        assert path is not None, name
        assert path.is_file(), name


def test_a_nested_document_is_named_by_its_path_and_a_vendored_case_is_not_one() -> None:
    names = resources.documents()
    assert "claude_code/plugin_eval_reference" in names
    assert resources.document("claude_code/plugin_eval_reference").is_file()
    assert [name for name in names if "eval_smoke/evals" in name] == []


@pytest.mark.parametrize("escape", ["../README", "/etc/passwd", "../../pyproject"])
def test_a_name_cannot_reach_outside_the_tree(escape: str) -> None:
    assert resources.document(escape) is None


# A commented default, `  # <key>: <value>`. A prose comment has no key. The two keys the
# example does not claim a default for are excluded: `cowork.profile` has none, and
# `docker.extra_ca_file` shows the shape of a value rather than a default.
DEFAULT_LINE = re.compile(r"^(\s+)# (?!(?:profile|extra_ca_file):)([a-z_]+:.*)$", re.MULTILINE)


def test_every_commented_default_in_the_example_is_the_built_in_default(
    tmp_path: Path,
) -> None:
    """Uncommenting the example changes nothing, which is what its header promises."""
    written = tmp_path / "cowork_evals.yaml"
    uncommented = DEFAULT_LINE.sub(r"\1\2", resources.EXAMPLE_CONFIG.read_text())
    written.write_text(uncommented, encoding="utf-8")

    loaded = Config.load(written)
    defaults = Config()

    assert loaded.eval == defaults.eval
    assert loaded.docker == defaults.docker
    assert loaded.panel == defaults.panel
    assert replace(loaded.cowork, profile=None) == defaults.cowork


# A reference a skill names, as `references/<file>`.
REFERENCE = re.compile(r"`references/([\w.-]+)`")


def test_every_shipped_skill_holds_to_the_skill_rules() -> None:
    """docs/library.md, "The skills". Each rule collects its own offenders."""
    root = resources.docs_dir()
    assert root is not None
    installed = resources.skills()
    assert installed
    rules: dict[str, list[str]] = {
        "name differs from directory": [],
        "sends to docs/": [],
        "names a missing reference": [],
        "holds an unnamed reference": [],
        "holds a copy of a document": [],
        "links outside references/": [],
    }
    for directory, target in installed:
        text = (directory / resources.SKILL_FILE).read_text()
        references = directory / "references"
        if f"name: {target.name}" not in text:
            rules["name differs from directory"].append(directory.name)
        if "cowork_evals docs" in text or "docs/" in text:
            rules["sends to docs/"].append(directory.name)
        for name in REFERENCE.findall(text):
            if not (references / name).is_file():
                rules["names a missing reference"].append(f"{directory.name}: {name}")
        for path in sorted(references.glob("*")):
            where = f"{directory.name}: {path.name}"
            if f"references/{path.name}" not in text:
                rules["holds an unnamed reference"].append(where)
            document = root / path.name
            if document.exists() and path.resolve() != document.resolve():
                rules["holds a copy of a document"].append(where)
            if path.suffix != ".md":
                continue
            for link in _links(path):
                if link.startswith(("http://", "https://", "#")):
                    continue
                if not (references / link.split("#", 1)[0]).is_file():
                    rules["links outside references/"].append(f"{where}: {link}")
    assert rules == {rule: [] for rule in rules}


# R1 and R2. docs/library.md.


# A fenced block, and an inline code span. Both are stripped before links are matched: a
# file that documents the link syntax writes it inside one, and that is prose about a link
# rather than a link.
FENCE = re.compile(r"```.*?```", re.DOTALL)
CODE_SPAN = re.compile(r"`[^`\n]*`")


def _links(path: Path) -> list[str]:
    text = CODE_SPAN.sub("", FENCE.sub("", path.read_text()))
    return LINK.findall(text)


def test_r1_no_module_links_out_of_the_package() -> None:
    """A module names a document. It never links to one."""
    offenders = [
        f"{path.relative_to(REPOSITORY)}: {target}"
        for path in (REPOSITORY / "src").rglob("*.py")
        for target in _links(path)
        if target.startswith((".", "/"))
    ]
    assert offenders == []


def test_r2_every_document_link_stays_inside_the_tree_and_resolves() -> None:
    """A document links inside `docs/`. A target outside it is named, not linked."""
    root = resources.docs_dir()
    assert root is not None
    outside, broken = [], []
    for path in root.rglob("*.md"):
        for target in _links(path):
            if target.startswith(("http://", "https://", "#")):
                continue
            where = f"{path.relative_to(root)}: {target}"
            # Lexical, not `resolve()`: a file in the tree may be a link to package data, and
            # the wheel ships it as a file inside the tree.
            if not Path(os.path.normpath(path.parent / target)).is_relative_to(root):
                outside.append(where)
            if not (path.parent / target.split("#", 1)[0]).resolve().exists():
                broken.append(where)
    assert (outside, broken) == ([], [])


def test_every_document_the_readme_names_exists() -> None:
    readme = (REPOSITORY / "README.md").read_text()
    named = {target for target in LINK.findall(readme) if target.startswith("docs/")}
    assert named
    missing = [target for target in named if not (REPOSITORY / target).is_file()]
    assert missing == []
