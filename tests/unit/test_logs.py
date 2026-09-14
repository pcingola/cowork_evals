"""The run directory, `env.txt`, `latest`, pruning and the tee.

Every run directory is built under `tmp_path`, the scope shapes are read from the
hand-written plugin roots under tests/data/, and the tee is proven against a real child
process. The layout is docs/running_evals.md. See ../README.md.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from cowork_evals import logs

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


def test_a_case_directory_names_the_plugin_the_skill_and_the_case() -> None:
    target = TREE / "evals" / "greeter" / "every-key"
    assert logs.scope_name(target, [TREE]) == "reader-fixture-greeter-every-key"


def test_a_skill_directory_names_the_plugin_and_the_skill() -> None:
    assert logs.scope_name(TREE / "evals" / "greeter", [TREE]) == "reader-fixture-greeter"


def test_an_evals_directory_names_the_plugin() -> None:
    assert logs.scope_name(TREE / "evals", [TREE]) == "reader-fixture"


def test_more_than_one_plugin_root_is_named_all() -> None:
    assert logs.scope_name(DATA / "cases", [TREE, CLEAN]) == "all"


def test_any_other_path_inside_one_root_names_the_plugin() -> None:
    assert logs.scope_name(TREE, [TREE]) == "reader-fixture"
    assert logs.scope_name(CLEAN / "skills" / "greeter", [CLEAN]) == "clean"


def test_the_plugin_name_is_the_manifest_name_and_not_the_folder() -> None:
    """`tests/data/cases/tree/` is a folder named `tree` and a plugin named otherwise."""
    assert TREE.name == "tree"
    assert logs.scope_name(TREE / "evals", [TREE]) == "reader-fixture"


def test_a_manifest_naming_nothing_falls_back_to_the_folder(tmp_path: Path) -> None:
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text("{}")
    assert logs.scope_name(tmp_path, [tmp_path]) == logs.slug(tmp_path.name)


# The slug.


def test_every_character_outside_the_safe_set_becomes_a_dash() -> None:
    assert logs.slug("acme/mail v2") == "acme-mail-v2"
    assert logs.slug("keep.this-one_ok") == "keep.this-one_ok"


def test_a_scope_name_goes_through_the_slug(tmp_path: Path) -> None:
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text('{"name": "acme/mail"}')
    (tmp_path / "evals" / "greeter").mkdir(parents=True)
    assert logs.scope_name(tmp_path / "evals" / "greeter", [tmp_path]) == "acme-mail-greeter"


# The run directory and the plugin directory.


def test_a_run_directory_is_the_stamp_then_the_scope(tmp_path: Path) -> None:
    created = logs.run_dir(tmp_path, "plugin")
    assert created.parent == tmp_path
    assert created.is_dir()
    assert logs.STAMP_PATTERN.match(created.name)
    assert created.name.endswith("-plugin")


def test_a_second_run_inside_the_same_second_appends_a_suffix(tmp_path: Path) -> None:
    first = logs.run_dir(tmp_path, "plugin")
    second = tmp_path / f"{first.name}-2"
    second.mkdir()
    third = tmp_path / f"{first.name}-3"
    third.mkdir()
    # The next name after both is -4, so the suffix counts and never reuses.
    assert logs._unique(tmp_path, first.name).name == f"{first.name}-4"


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


def test_env_txt_carries_one_line_per_row(tmp_path: Path) -> None:
    written = logs.write_env(
        tmp_path, "docker", image="cowork-evals:0123456789ab", credential="login"
    )
    names = [line.split(":", 1)[0] for line in written.read_text().splitlines()]
    assert names == ["cowork_evals", "claude", "python3", "backend", "image", "credential"]


def test_the_credential_line_is_the_route_and_no_name(tmp_path: Path) -> None:
    """The route says which credential a run used. The names it forwards are fixed.
    docs/docker.md."""
    written = logs.write_env(tmp_path, "docker", credential="bedrock").read_text()
    assert "credential: bedrock\n" in written
    assert "AWS_BEARER_TOKEN_BEDROCK" not in written


def test_the_credential_line_is_absent_without_a_route(tmp_path: Path) -> None:
    assert "credential" not in logs.write_env(tmp_path, "cowork").read_text()


def test_the_image_line_is_absent_without_one(tmp_path: Path) -> None:
    written = logs.write_env(tmp_path, "cowork")
    assert "image:" not in written.read_text()
    assert "backend: cowork\n" in written.read_text()


def test_the_forwarded_names_are_one_line_and_no_value(tmp_path: Path) -> None:
    """What each name held is the host's, and reaches the container and no artefact.
    docs/docker.md."""
    written = logs.write_env(tmp_path, "docker", env_passthrough=("ACME_API_KEY", "ACME_REGION"))
    assert "env_passthrough: ACME_API_KEY ACME_REGION\n" in written.read_text()


def test_the_forwarded_line_is_absent_when_none_is_forwarded(tmp_path: Path) -> None:
    assert "env_passthrough" not in logs.write_env(tmp_path, "docker").read_text()


def test_the_python_line_records_the_interpreter(tmp_path: Path) -> None:
    written = logs.write_env(tmp_path, "docker")
    assert f"python3: Python {sys.version_info.major}.{sys.version_info.minor}" in (
        written.read_text()
    )


def test_a_command_that_does_not_run_records_the_failure_on_its_line() -> None:
    assert _command_failure().startswith("unavailable: ")


def _command_failure() -> str:
    return logs._command_version(["cowork-evals-no-such-command"])


# latest.


def test_latest_is_a_relative_symlink_to_the_run_directory(tmp_path: Path) -> None:
    run = logs.run_dir(tmp_path, "plugin")
    link = logs.point_latest(tmp_path, run)
    assert link.is_symlink()
    assert os.readlink(link) == run.name
    assert link.resolve() == run.resolve()


def test_latest_is_replaced_and_never_absent_between_two_runs(tmp_path: Path) -> None:
    first = logs.run_dir(tmp_path, "plugin")
    logs.point_latest(tmp_path, first)
    second = tmp_path / f"{first.name}-2"
    second.mkdir()
    logs.point_latest(tmp_path, second)
    assert os.readlink(tmp_path / logs.LATEST) == second.name
    assert not (tmp_path / f".{logs.LATEST}.new").exists()


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


def test_nothing_else_under_the_root_is_touched(tmp_path: Path) -> None:
    stamped(tmp_path, 40)
    note = tmp_path / "notes.txt"
    note.write_text("kept")
    other = tmp_path / "not-a-run"
    other.mkdir()
    logs.prune(tmp_path, 30)
    assert note.is_file()
    assert other.is_dir()


def test_a_dangling_latest_is_repointed_at_the_newest_remaining(tmp_path: Path) -> None:
    old = stamped(tmp_path, 40)
    young = stamped(tmp_path, 1, scope="young")
    logs.point_latest(tmp_path, old)
    logs.prune(tmp_path, 30)
    assert os.readlink(tmp_path / logs.LATEST) == young.name


def test_a_dangling_latest_with_nothing_left_is_removed(tmp_path: Path) -> None:
    old = stamped(tmp_path, 40)
    logs.point_latest(tmp_path, old)
    logs.prune(tmp_path, 30)
    assert not (tmp_path / logs.LATEST).is_symlink()


def test_a_latest_that_still_points_somewhere_is_left_alone(tmp_path: Path) -> None:
    young = stamped(tmp_path, 1)
    logs.point_latest(tmp_path, young)
    logs.prune(tmp_path, 30)
    assert os.readlink(tmp_path / logs.LATEST) == young.name


def test_pruning_an_absent_root_is_empty(tmp_path: Path) -> None:
    assert logs.prune(tmp_path / "absent", 30) == []


# The tee.


def test_a_child_process_output_reaches_the_log_and_the_terminal(tmp_path: Path) -> None:
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
    written = path.read_text()
    assert "from this process" in written
    assert "from the child" in written
    assert "from stderr" in written


def test_the_copy_is_bytes_so_a_carriage_return_survives(tmp_path: Path) -> None:
    run = logs.run_dir(tmp_path, "plugin")
    with logs.tee(run) as path:
        subprocess.run(
            [sys.executable, "-c", r"import sys; sys.stdout.write('50%\r100%\n')"], check=True
        )
    assert path.read_bytes().endswith(b"50%\r100%\n")


def test_both_descriptors_are_restored_on_the_way_out(tmp_path: Path) -> None:
    run = logs.run_dir(tmp_path, "plugin")
    before = (os.fstat(1).st_ino, os.fstat(2).st_ino)
    with logs.tee(run):
        pass
    assert (os.fstat(1).st_ino, os.fstat(2).st_ino) == before


def test_the_descriptors_are_restored_after_a_raise(tmp_path: Path) -> None:
    run = logs.run_dir(tmp_path, "plugin")
    before = (os.fstat(1).st_ino, os.fstat(2).st_ino)
    try:
        with logs.tee(run):
            raise RuntimeError("the invocation failed")
    except RuntimeError:
        pass
    assert (os.fstat(1).st_ino, os.fstat(2).st_ino) == before


# Deleting a tree the harness left unreadable.


def test_a_sealed_tree_is_unsealed_and_removed(tmp_path: Path) -> None:
    """`--keep-temp` leaves the sandbox read-only and its `sealed/` at mode 000.

    A plain `rmtree` raises on that, and a run directory holding one would never be pruned.
    """
    sealed = tmp_path / "sandbox" / "sealed" / "home"
    sealed.mkdir(parents=True)
    (sealed / "note.txt").write_text("written by the plugin under test", encoding="utf-8")
    (tmp_path / "sandbox" / "sealed").chmod(0o000)
    (tmp_path / "sandbox").chmod(0o500)

    logs.remove_tree(tmp_path / "sandbox")
    assert not (tmp_path / "sandbox").exists()


def test_pruning_removes_a_run_directory_holding_a_sealed_tree(tmp_path: Path) -> None:
    old = tmp_path / "20260101-000000-smoke"
    (old / "smoke" / "tmp" / "claude-eval-Ab12Cd" / "sealed").mkdir(parents=True)
    (old / "smoke" / "tmp" / "claude-eval-Ab12Cd" / "sealed").chmod(0o000)
    (old / "smoke" / "tmp" / "claude-eval-Ab12Cd").chmod(0o500)

    assert logs.prune(tmp_path, days=1) == [old]
    assert not old.exists()
