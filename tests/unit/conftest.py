"""The builders and recorded documents more than one unit test file reads.

importlib import mode makes a conftest unimportable, so each helper is a fixture, and a
builder is a fixture that returns the function.
"""

from __future__ import annotations

import textwrap
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cowork_evals.cases import GRADER_CONFIGS, Grader, GraderConfig
from cowork_evals.cowork import RunLogEntry, SessionDocument
from cowork_evals.harness import RunOptions

DOCUMENTS = Path(__file__).resolve().parent.parent / "data" / "documents"

MANIFEST = '{"name": "skips-fixture", "description": "A fixture.", "version": "0.0.1"}\n'


def _document(name: str) -> SessionDocument:
    """One recorded session document, with its session directory resolved for this machine.

    An absolute path cannot be committed, so the file names the directory beside it and
    this is the one line that resolves it.
    """
    path = DOCUMENTS / f"{name}.json"
    loaded = SessionDocument.model_validate_json(path.read_text(encoding="utf-8"))
    return loaded.model_copy(update={"session_dir": str(path.parent / loaded.session_dir)})


@pytest.fixture
def answered() -> SessionDocument:
    return _document("answered")


@pytest.fixture
def quiet() -> SessionDocument:
    return _document("quiet")


@pytest.fixture
def produced() -> SessionDocument:
    return _document("produced")


def _grader(
    kind: str,
    config: GraderConfig | None = None,
    *,
    name: str = "g",
    weight: int | float = 1,
    markdown: str = "",
    path: Path | None = None,
) -> Grader:
    """One grader of type `kind`. No `config` is the config a file with no keys gives."""
    known = GRADER_CONFIGS.get(kind)
    if config is None and known is not None:
        config = known()  # type: ignore[assignment]
    return Grader(
        name=name,
        type=kind,
        weight=weight,
        config=config,
        markdown=markdown,
        path=path or Path(f"{name}.md"),
    )


@pytest.fixture
def grader() -> Callable[..., Grader]:
    return _grader


@pytest.fixture
def run_options() -> RunOptions:
    """Every option written out, so a test reads no configuration it did not write."""
    return RunOptions(
        model="sonnet",
        judge_model="haiku",
        ablation="none",
        max_cost_usd="5",
        allow_tools=("Bash",),
    )


def _write_run_log(
    path: Path,
    count: int = 1,
    *,
    at: datetime | None = None,
    outcome: str = "submitted",
) -> None:
    """Append `count` run log lines stamped `at`, now by default."""
    entry = RunLogEntry(
        timestamp=at or datetime.now(timezone.utc),
        prompt_sha256="0" * 64,
        session_dir=None,
        outcome=outcome,
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write((entry.model_dump_json() + "\n") * count)


@pytest.fixture
def run_log() -> Callable[..., None]:
    return _write_run_log


def _case_tree(
    directory: Path,
    *,
    frontmatter: str = "",
    case_yaml: str | None = None,
    graders: dict[str, str] | None = None,
    mocks_at: tuple[str, ...] = (),
    tags: str = "[skill]",
) -> tuple[Path, Path]:
    """One plugin root under `directory`, holding `skills/skill/` and the one case
    `evals/skill/case/`. Returns the root and the case directory.

    The case is valid when it writes nothing that stops CoWork. `mocks_at` names each
    directory, relative to the root, that gets a `mocks/` layer.
    """
    root = directory / "plugin"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(MANIFEST, encoding="utf-8")
    (root / "skills" / "skill").mkdir(parents=True)

    case_dir = root / "evals" / "skill" / "case"
    case_dir.mkdir(parents=True)
    block = textwrap.dedent(frontmatter).strip("\n")
    (case_dir / "prompt.md").write_text(
        f'---\nname: one-case\ntags: {tags}\nplugins: ["../../.."]\n{block}\n---\n\n'
        "Reply with exactly: PONG\n",
        encoding="utf-8",
    )
    if case_yaml is not None:
        (case_dir / "case.yaml").write_text(textwrap.dedent(case_yaml).lstrip("\n"), "utf-8")
    for name, body in (graders or {}).items():
        (case_dir / "graders").mkdir(exist_ok=True)
        (case_dir / "graders" / f"{name}.md").write_text(
            textwrap.dedent(body).lstrip("\n"), "utf-8"
        )
    for relative in mocks_at:
        (root / relative / "mocks" / "mailer").mkdir(parents=True)
        (root / relative / "mocks" / "mailer" / "send.md").write_text("---\ntool: send\n---\n")
    return root, case_dir


@pytest.fixture
def case_tree() -> Callable[..., tuple[Path, Path]]:
    return _case_tree
