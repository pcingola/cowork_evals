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

# What a document name is checked against. Every document this repository holds is one of
# these, and a new one that is neither is a new kind of file and not a silent addition.
EXPECTED_DOCUMENTS = {
    "README",
    "cli",
    "eval_format",
    "eval_design",
    "library",
    "runtime",
    "approaches",
}

# The grader types the format defines. Every file that names a grader names one of these.
GRADER_TYPES = ("regex", "tool_used", "tool_order", "file_exists", "llm", "baseline")


# The tree.


def test_the_documentation_tree_is_found() -> None:
    root = resources.docs_dir()
    assert root is not None
    assert root.is_dir()
    assert (root / "eval_format.md").is_file()


def test_every_listed_name_resolves_to_a_file() -> None:
    names = resources.documents()
    assert names
    for name in names:
        path = resources.document(name)
        assert path is not None, name
        assert path.is_file(), name


def test_the_expected_documents_are_all_listed() -> None:
    assert set(resources.documents()) >= EXPECTED_DOCUMENTS


def test_a_name_takes_the_extension_or_leaves_it() -> None:
    assert resources.document("cli") == resources.document("cli.md")


def test_a_nested_document_is_named_by_its_path() -> None:
    path = resources.document("claude_code/plugin_eval_reference")
    assert path is not None
    assert path.is_file()


def test_an_unknown_name_resolves_to_nothing() -> None:
    assert resources.document("no-such-document") is None


@pytest.mark.parametrize("escape", ["../README", "/etc/passwd", "../../pyproject"])
def test_a_name_cannot_reach_outside_the_tree(escape: str) -> None:
    """The name is matched against the list, never joined onto the root."""
    assert resources.document(escape) is None


def test_a_vendored_plugin_case_is_not_a_document() -> None:
    """The smoke plugin ships, and its cases are not listed as documents."""
    names = resources.documents()
    assert not [name for name in names if "eval_smoke/evals" in name]
    assert "claude_code/README" in names


# The package data.


def test_the_example_configuration_ships_beside_the_modules() -> None:
    assert resources.EXAMPLE_CONFIG.is_file()
    assert "cowork:" in resources.EXAMPLE_CONFIG.read_text()


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
    consumer adopts by uncommenting it. Nothing else compares the two, which is how
    `allow_tools` sat at the superseded `[Bash]` after the grant became the session mirror.
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
    assert [target.parent.name for _, target in installed] == ["cowork-ask", "cowork-evals"]
    for source, target in installed:
        text = source.read_text()
        assert text.startswith("---\n"), source
        assert f"name: {target.parent.name}" in text, source
        assert "TRIGGER" in text, source


def test_a_skill_installs_where_claude_code_reads_a_project_skill() -> None:
    assert resources.skills()[0][1] == Path(".claude") / "skills" / "cowork-ask" / "SKILL.md"


def test_the_ask_skill_carries_the_measurement_rule() -> None:
    """The one rule that makes an ask worth its VM boot. docs/cowork_desktop.md."""
    text = resources.skill("cowork-ask").read_text()
    assert "is not evidence" in text
    assert "cowork_evals ask --cowork" in text


def test_the_memory_block_carries_its_own_marker() -> None:
    assert resources.MEMORY_MARKER in resources.MEMORY_BLOCK


# The skill against the documents it condenses. docs/library.md.


def _traps(text: str, start: str, end: str | None) -> list[str]:
    body = text[text.index(start) :]
    if end is not None:
        body = body[: body.index(end)]
    return [line for line in body.splitlines() if line.startswith("- ")]


def _document(name: str) -> str:
    root = resources.docs_dir()
    assert root is not None
    return (root / name).read_text()


def _dimensions(design: str) -> list[str]:
    """The first cell of every row in the design file's dimension table.

    Derived from the document, so no dimension is spelled in this file: a dimension added
    there is asserted here on the next run.
    """
    body = design[design.index("## The coverage dimensions") :]
    body = body[: body.index("### What the table does not decide")]
    cells = [line.split("|")[1].strip() for line in body.splitlines() if line.startswith("| ")]
    return [cell for cell in cells if cell and cell != "Dimension" and set(cell) != {"-"}]


def test_the_skill_carries_every_grader_type_the_format_defines() -> None:
    """The skill states no fact of its own, so a type in one is a type in the other."""
    skill = resources.skill("cowork-evals").read_text()
    fmt = _document("eval_format.md")
    for grader in GRADER_TYPES:
        assert f"`{grader}`" in skill, grader
        assert f"`{grader}`" in fmt, grader


def test_the_design_names_every_grader_type_the_format_defines() -> None:
    """The design file places every type in a dimension. A seventh type has to land somewhere."""
    design = _document("eval_design.md")
    for grader in GRADER_TYPES:
        assert f"`{grader}`" in design, grader


def test_the_skill_carries_every_coverage_dimension_the_design_defines() -> None:
    """A dimension the document names and the skill does not is a dimension no session reads."""
    skill = resources.skill("cowork-evals").read_text()
    dimensions = _dimensions(_document("eval_design.md"))
    assert dimensions
    for dimension in dimensions:
        assert dimension in skill, dimension


def test_the_skill_carries_the_interview_default() -> None:
    """The default and its one exception. Without both, a session invents a suite again."""
    skill = resources.skill("cowork-evals").read_text()
    design = _document("eval_design.md")
    for sentence in ("Claude Code does not invent a suite.", "The signal is the reply."):
        assert sentence in skill, sentence
        assert sentence in design, sentence


def test_the_grader_class_preference_is_in_the_design_file() -> None:
    """The split: which class to prefer depends on the skill, so the format does not say.

    docs/README.md holds the question that decides the side. This pins the one statement that
    moved, so a later edit cannot quietly put it back.
    """
    assert "Prefer a" not in _document("eval_format.md")
    assert "Prefer a structural grader." in _document("eval_design.md")


def test_the_skill_carries_as_many_traps_as_the_format() -> None:
    """A trap added to one and not the other is the drift this rule exists to stop."""
    skill = resources.skill("cowork-evals").read_text()
    fmt = (resources.docs_dir() / "eval_format.md").read_text()
    assert len(_traps(skill, "## Traps", "## The exit codes")) == len(
        _traps(fmt, "## Authoring traps", None)
    )


def test_the_skill_sends_the_reader_to_the_docs_verb() -> None:
    """Everything it does not carry is one command away, and it has to say which."""
    skill = resources.skill("cowork-evals").read_text()
    assert "cowork_evals docs" in skill
    for name in ("eval_format", "eval_design", "cli", "runtime"):
        assert f"docs {name}" in skill, name


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


def test_r2_no_document_links_out_of_the_tree() -> None:
    """A document links inside `docs/`. A target outside it is named, not linked.

    `docs/` ships and the tree around it does not, so a link that leaves it dangles for
    every consumer.
    """
    root = resources.docs_dir()
    assert root is not None
    offenders = []
    for path in root.rglob("*.md"):
        for target in _links(path):
            if target.startswith(("http://", "https://", "#")):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.is_relative_to(root):
                offenders.append(f"{path.relative_to(root)}: {target}")
    assert offenders == []


def test_r2_every_link_inside_the_tree_resolves() -> None:
    """A link that stays inside `docs/` points at something that is there."""
    root = resources.docs_dir()
    assert root is not None
    broken = []
    for path in root.rglob("*.md"):
        for target in _links(path):
            if target.startswith(("http://", "https://", "#")):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            if not resolved.exists():
                broken.append(f"{path.relative_to(root)}: {target}")
    assert broken == []


def test_every_document_the_readme_names_exists() -> None:
    """The Documentation table in `README.md` names files that ship."""
    readme = (REPOSITORY / "README.md").read_text()
    named = {target for target in LINK.findall(readme) if target.startswith("docs/")}
    assert named
    missing = [target for target in named if not (REPOSITORY / target).is_file()]
    assert missing == []
