"""The run directory, `env.txt`, `latest`, pruning and the tee.

Every run directory is built under `tmp_path`, the scope shapes are read from the
hand-written plugin roots under tests/data/, and the tee is proven against a real child
process. The layout is docs/running_evals.md. See ../README.md.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from cowork_evals import logs
from cowork_evals.cases import PluginManifest

DATA = Path(__file__).resolve().parent.parent / "data"
TREE = DATA / "cases" / "tree"
CLEAN = DATA / "validate" / "clean"


def stamped(root: Path, age_days: float, scope: str = "plugin") -> Path:
    """One run directory whose name carries a stamp `age_days` old."""
    stamp = (datetime.now() - timedelta(days=age_days)).strftime(logs.STAMP_FORMAT)
    directory = root / f"{stamp}-{scope}"
    directory.mkdir(parents=True)
    return directory


# The scope name.


@pytest.mark.parametrize(
    ("target", "roots", "expected"),
    [
        (TREE / "evals" / "greeter" / "every-key", [TREE], "reader-fixture-greeter-every-key"),
        (TREE / "evals" / "greeter", [TREE], "reader-fixture-greeter"),
        (TREE / "evals", [TREE], "reader-fixture"),
        (DATA / "cases", [TREE, CLEAN], "all"),
        (TREE, [TREE], "reader-fixture"),
        (CLEAN / "skills" / "greeter", [CLEAN], "clean"),
    ],
)
def test_the_path_names_the_scope(target: Path, roots: list[Path], expected: str) -> None:
    """`tests/data/cases/tree/` is a folder named `tree` holding a plugin named otherwise."""
    assert logs.scope_name(target, roots) == expected


def _manifest(root: Path, name: str | None) -> None:
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(
        PluginManifest(name=name).model_dump_json(exclude_none=True)
    )


def test_a_manifest_naming_nothing_falls_back_to_the_folder(tmp_path: Path) -> None:
    _manifest(tmp_path / "acme", None)
    assert logs.scope_name(tmp_path / "acme", [tmp_path / "acme"]) == "acme"


def test_a_scope_name_goes_through_the_slug(tmp_path: Path) -> None:
    """Each character outside `[A-Za-z0-9._-]` becomes `-`, and every one inside is kept."""
    _manifest(tmp_path, "acme/mail v2.x_y")
    (tmp_path / "evals" / "greeter").mkdir(parents=True)
    target = tmp_path / "evals" / "greeter"
    assert logs.scope_name(target, [tmp_path]) == "acme-mail-v2.x_y-greeter"


# The run directory and the plugin directory.


def test_a_run_directory_is_the_stamp_then_the_scope(tmp_path: Path) -> None:
    created = logs.run_dir(tmp_path, "plugin")
    assert created.parent == tmp_path
    assert created.is_dir()
    assert re.match(r"^\d{8}-\d{6}-plugin$", created.name)


def test_two_plugins_sharing_a_name_get_two_directories(tmp_path: Path) -> None:
    run = logs.run_dir(tmp_path, "all")
    first = logs.plugin_dir(run, "mail")
    second = logs.plugin_dir(run, "mail")
    assert first.name == "mail"
    assert second.name == "mail-2"
    assert first != second


def test_a_plugin_directory_name_goes_through_the_slug(tmp_path: Path) -> None:
    run = logs.run_dir(tmp_path, "all")
    assert logs.plugin_dir(run, "acme/mail").name == "acme-mail"


# The log root.


def test_the_log_root_is_logs_evals_under_the_working_directory(
    tmp_path, working_directory
) -> None:
    with working_directory(tmp_path):
        assert logs.log_root() == Path(tmp_path).resolve() / "logs" / "evals"


def test_out_replaces_the_whole_root(tmp_path: Path) -> None:
    assert logs.log_root(tmp_path / "elsewhere") == (tmp_path / "elsewhere").resolve()


# env.txt.

DOCKER = ("cowork-evals:0123456789ab", ["ACME_API_KEY", "ACME_REGION"], ["HOME", "PATH"], ["X"])


@pytest.mark.parametrize(
    ("backend", "image", "passthrough", "session", "keep", "written"),
    [
        ("docker", *DOCKER, {"image", "env_passthrough", "session_env", "keep_env"}),
        ("cowork", None, [], [], [], set()),
    ],
)
def test_env_txt_carries_one_line_per_field_it_has(
    tmp_path: Path,
    backend: str,
    image: str | None,
    passthrough: list[str],
    session: list[str],
    keep: list[str],
    written: set[str],
) -> None:
    """The forwarded names and never a value: what each held is the host's. docs/docker.md."""
    path = logs.write_env(tmp_path, backend, image, passthrough, session, keep)
    read = logs.RunEnvironment.read(path)
    assert read.model_fields_set == {"cowork_evals", "claude", "python3", "backend"} | written
    assert (read.backend, read.image) == (backend, image)
    assert (read.env_passthrough, read.session_env, read.keep_env) == (passthrough, session, keep)


# latest.


def test_latest_names_the_newest_run_directory(tmp_path: Path) -> None:
    first = logs.run_dir(tmp_path, "plugin")
    logs.point_latest(tmp_path, first)
    second = logs.run_dir(tmp_path, "plugin")
    link = logs.point_latest(tmp_path, second)
    assert link.is_symlink()
    assert link.resolve() == second.resolve()


# Pruning.


def test_pruning_reads_the_stamp_from_the_name_and_not_the_modification_time(
    tmp_path: Path,
) -> None:
    old = stamped(tmp_path, 40)
    young = stamped(tmp_path, 1, scope="young")
    # The modification times contradict the names in both directions.
    os.utime(old, (datetime.now().timestamp(), datetime.now().timestamp()))
    ancient = (datetime.now() - timedelta(days=400)).timestamp()
    os.utime(young, (ancient, ancient))
    assert logs.prune(tmp_path, 30) == [old]
    assert not old.exists()
    assert young.is_dir()
    # The cutoff is an exact moment, not a floor on whole days.
    hour = stamped(tmp_path, 1 / 24, scope="hour")
    assert logs.prune(tmp_path, 0) == [young, hour]


def test_nothing_else_under_the_root_is_touched(tmp_path: Path) -> None:
    stamped(tmp_path, 40)
    note = tmp_path / "notes.txt"
    note.write_text("kept")
    other = tmp_path / "not-a-run"
    other.mkdir()
    logs.prune(tmp_path, 30)
    assert note.is_file()
    assert other.is_dir()


@pytest.mark.parametrize(
    ("ages", "latest"),
    [((40, 1), 1), ((40,), None), ((1,), 1)],
    ids=["old-and-young", "old-only", "young-only"],
)
def test_after_pruning_latest_names_the_newest_remaining(
    tmp_path: Path, ages: tuple[int, ...], latest: int | None
) -> None:
    made = {age: stamped(tmp_path, age, scope=f"age{age}") for age in ages}
    logs.point_latest(tmp_path, made[ages[0]])
    logs.prune(tmp_path, 30)
    link = tmp_path / logs.LATEST
    named = link.resolve() if link.is_symlink() else None
    assert named == (None if latest is None else made[latest].resolve())


def test_pruning_an_absent_root_is_empty(tmp_path: Path) -> None:
    assert logs.prune(tmp_path / "absent", 30) == []


# The tee.


def test_a_child_process_output_reaches_the_log_and_the_terminal(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """A real child, because a child inherits descriptors 1 and 2 and not `sys.stdout`.

    This process writes to descriptor 1 directly rather than through `print`. Under pytest
    `sys.stdout` is pytest's own capture object and does not reach descriptor 1 at all,
    while `print` on a terminal writes exactly these bytes to it.
    """
    run = logs.run_dir(tmp_path, "plugin")
    with logs.tee(run) as path:
        os.write(1, b"from this process\n")
        subprocess.run([sys.executable, "-c", "print('from the child')"], check=True)
        subprocess.run(
            [sys.executable, "-c", "import sys; sys.stderr.write('from stderr\\n')"], check=True
        )
    terminal = capfd.readouterr().out
    for line in ("from this process", "from the child", "from stderr"):
        assert line in path.read_text()
        assert line in terminal


# Deleting a tree the harness left unreadable.


def test_pruning_removes_a_run_directory_holding_a_sealed_tree(tmp_path: Path) -> None:
    old = tmp_path / "20260101-000000-smoke"
    (old / "smoke" / "tmp" / "claude-eval-Ab12Cd" / "sealed").mkdir(parents=True)
    (old / "smoke" / "tmp" / "claude-eval-Ab12Cd" / "sealed").chmod(0o000)
    (old / "smoke" / "tmp" / "claude-eval-Ab12Cd").chmod(0o500)

    assert logs.prune(tmp_path, days=1) == [old]
    assert not old.exists()
