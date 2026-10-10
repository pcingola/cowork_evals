"""The shipped documentation and the shipped data, and the two reference rules over them.

`resources` resolves a document name in either layout, and these tests run in the checkout
layout: the package is installed editable, so `docs/` is at the repository root and not
beside the modules. The install layout is proved by `scripts/build.sh` and by the integration
tier, which install a built wheel.

The last two tests enforce R1 and R2 in docs/library.md. They read the repository's own files,
which is the only place either rule can be checked: a violation is a link that resolves in a
checkout and dangles in an install, so nothing at run time can see it. See ../README.md.
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

# The tree.


def test_every_listed_name_resolves_to_a_file() -> None:
    names = resources.documents()
    assert names
    for name in names:
        path = resources.document(name)
        assert path is not None, name
        assert path.is_file(), name


def test_a_nested_document_is_named_by_its_path_and_a_vendored_case_is_not_one() -> None:
    """The smoke plugin ships, and its cases are not listed as documents."""
    names = resources.documents()
    assert "claude_code/plugin_eval_reference" in names
    assert resources.document("claude_code/plugin_eval_reference").is_file()
    assert [name for name in names if "eval_smoke/evals" in name] == []


@pytest.mark.parametrize("escape", ["../README", "/etc/passwd", "../../pyproject"])
def test_a_name_cannot_reach_outside_the_tree(escape: str) -> None:
    """The name is matched against the list, never joined onto the root."""
    assert resources.document(escape) is None


# The two keys the example does not claim a default for: `cowork.profile` has none, and
# `docker.extra_ca_file` shows the shape of a value rather than a default. Its own header
# says so, and every other commented line is a default.
NOT_A_DEFAULT = ("profile:", "extra_ca_file:")


def _uncommented(text: str) -> str:
    """The example with every commented default turned back on.

    A default line is `  # <key>: <value>`; a prose line is `# ...` at the margin or a
    sentence after the hash. The key is what tells them apart, so only a line whose comment
    is `<key>: ...` is uncommented.
    """
    key = re.compile(r"^(\s+)# ([a-z_]+:.*)$")
    lines = []
    for line in text.splitlines():
        found = key.match(line)
        if found is None or any(name in line for name in NOT_A_DEFAULT):
            lines.append(line)
            continue
        lines.append(f"{found.group(1)}{found.group(2)}")
    return "\n".join(lines) + "\n"


def test_every_commented_default_in_the_example_is_the_built_in_default(
    tmp_path: Path,
) -> None:
    """Uncommenting the example changes nothing, which is what its header promises.

    The file ships to a consumer through `init`, so a stale line there is a default a
    consumer adopts by uncommenting it.
    """
    written = tmp_path / "cowork_evals.yaml"
    written.write_text(_uncommented(resources.EXAMPLE_CONFIG.read_text()), encoding="utf-8")

    loaded = Config.load(written)
    defaults = Config()

    assert loaded.eval == defaults.eval
    assert loaded.docker == defaults.docker
    assert loaded.panel == defaults.panel
    assert replace(loaded.cowork, profile=None) == defaults.cowork


def test_every_shipped_skill_is_a_directory_named_for_it() -> None:
    """One directory per skill, and its name is the skill's name. docs/library.md."""
    installed = resources.skills()
    assert installed
    for source, target in installed:
        assert f"name: {target.name}" in (source / resources.SKILL_FILE).read_text(), source


# The skills against the documents. docs/library.md.


def test_no_skill_file_sends_the_reader_to_the_documentation() -> None:
    """A skill names its own references. The documentation verb and `docs/` are for people."""
    offenders = [
        directory.name
        for directory, _ in resources.skills()
        for text in [(directory / resources.SKILL_FILE).read_text()]
        if "cowork_evals docs" in text or "docs/" in text
    ]
    assert offenders == []


# A reference a skill names, as `references/<file>`.
REFERENCE = re.compile(r"`references/([\w.-]+)`")


def test_every_reference_a_skill_names_is_there() -> None:
    """Including the ones a symlink provides, which must resolve to a file."""
    missing = [
        f"{directory.name}: {name}"
        for directory, _ in resources.skills()
        for name in REFERENCE.findall((directory / resources.SKILL_FILE).read_text())
        if not (directory / "references" / name).is_file()
    ]
    assert missing == []


def test_every_reference_a_skill_holds_is_named_by_its_skill_file() -> None:
    """A reference no `SKILL.md` names is never loaded."""
    unnamed = []
    for directory, _ in resources.skills():
        text = (directory / resources.SKILL_FILE).read_text()
        for path in sorted((directory / "references").glob("*")):
            if f"references/{path.name}" not in text:
                unnamed.append(f"{directory.name}: {path.name}")
    assert unnamed == []


def test_a_reference_that_shares_a_document_name_is_a_link_to_it() -> None:
    """A fact has one home. A reference named for a document is that document, never a copy."""
    root = resources.docs_dir()
    assert root is not None
    copies = [
        f"{directory.name}: {path.name}"
        for directory, _ in resources.skills()
        for path in sorted((directory / "references").glob("*"))
        if (root / path.name).exists() and path.resolve() != (root / path.name).resolve()
    ]
    assert copies == []


def test_every_link_in_a_reference_stays_inside_its_skill() -> None:
    """A document a skill links is read from the skill's `references/`, so a sibling link has
    to resolve there as well as in `docs/`."""
    broken = []
    for directory, _ in resources.skills():
        references = directory / "references"
        for path in sorted(references.glob("*.md")):
            for target in _links(path):
                if target.startswith(("http://", "https://", "#")):
                    continue
                if not (references / target.split("#", 1)[0]).is_file():
                    broken.append(f"{directory.name}/{path.name}: {target}")
    assert broken == []


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
    """A module names a document. It never links to one.

    The package sits two levels under the repository root in a checkout and one level above
    the documents in an install, so no relative path is correct in both.
    """
    offenders = [
        f"{path.relative_to(REPOSITORY)}: {target}"
        for path in (REPOSITORY / "src").rglob("*.py")
        for target in _links(path)
        if target.startswith((".", "/"))
    ]
    assert offenders == []


def test_r2_every_document_link_stays_inside_the_tree_and_resolves() -> None:
    """A document links inside `docs/`. A target outside it is named, not linked.

    `docs/` ships and the tree around it does not, so a link that leaves it dangles for
    every consumer.
    """
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
    """The Documentation table in `README.md` names files that ship."""
    readme = (REPOSITORY / "README.md").read_text()
    named = {target for target in LINK.findall(readme) if target.startswith("docs/")}
    assert named
    missing = [target for target in named if not (REPOSITORY / target).is_file()]
    assert missing == []
