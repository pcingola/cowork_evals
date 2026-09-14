"""The run directory, and everything the log layout puts in it.

The layout is docs/running_evals.md, and this module writes all of it, so no backend has to. A
backend takes a case path and an output directory and returns the path of the result document it
wrote; naming that directory, recording the environment, pointing `latest`, pruning and
capturing the terminal are all here.

This module owns every path an invocation writes, and is the only thing that deletes one.
What a backend leaves inside one of those paths is that backend's, and what is lifted out of
a harness sandbox into one is [traces.py](traces.py).

Nothing here reads a case, decides pass or fail or prints. Printing happens in [cli.py](cli.py).
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta
from importlib import metadata
from pathlib import Path
from typing import BinaryIO

from .cases import EVAL_DIR, plugin_name

# The log root under the working directory, which `--out DIR` replaces whole.
# docs/cli.md.
LOG_ROOT = Path("logs") / "evals"

# What one run directory holds, beside one directory per plugin.
# docs/running_evals.md.
RUN_LOG = "run.log"
ENV_FILE = "env.txt"
VERDICT_FILE = "verdict.txt"

# The symlink at the log root, pointing at the newest run directory.
LATEST = "latest"

# The run directory's name: a local-time stamp, then the scope.
STAMP_FORMAT = "%Y%m%d-%H%M%S"
STAMP_PATTERN = re.compile(r"^(\d{8}-\d{6})-")

# The scope name of a path covering more than one plugin root. docs/cli.md.
MULTI_SCOPE = "all"

# Every character a directory name may carry. `slug` replaces the rest.
SAFE = re.compile(r"[^A-Za-z0-9._-]")

# The distribution this package is installed as, for the `cowork_evals` line of `env.txt`.
DISTRIBUTION = "cowork-evals"

# What `run` prunes at, with no option. `prune --older-than DAYS` is the flag.
# docs/cli.md.
RUN_PRUNE_DAYS = 30


# Naming.


def slug(name: str) -> str:
    """One directory name component, safe on every filesystem this runs on.

    Both a scope name and a per-plugin directory name go through it, so a plugin whose
    manifest names it `acme/mail` is one directory and not two.
    """
    return SAFE.sub("-", name)


def scope_name(target: Path | str, roots: Sequence[Path]) -> str:
    """What the run directory is named for, from the path argument and what it selected.

    | The path points at                     | The name                  |
    | -------------------------------------- | ------------------------- |
    | a case directory                       | `<plugin>-<skill>-<case>` |
    | `evals/<skill>/`                       | `<plugin>-<skill>`        |
    | `evals/`                               | `<plugin>`                |
    | more than one plugin root              | `all`                     |
    | anything else inside one plugin root   | `<plugin>`                |

    The last row is the plugin root itself, a `skills/` directory, and any other path
    inside one root: the run is that plugin's, and the name says so.
    """
    if len(roots) != 1:
        return MULTI_SCOPE
    root = Path(roots[0]).resolve()
    name = plugin_name(root)
    resolved = Path(target).resolve()
    evals = root / EVAL_DIR
    if not resolved.is_relative_to(evals):
        return slug(name)
    parts = resolved.relative_to(evals).parts
    if not parts:
        return slug(name)
    if len(parts) == 1:
        return slug(f"{name}-{parts[0]}")
    return slug(f"{name}-{parts[0]}-{parts[-1]}")


def log_root(out: Path | str | None = None) -> Path:
    """`<cwd>/logs/evals`, or the directory `--out` names instead of the whole root."""
    return Path(out).expanduser().resolve() if out is not None else (Path.cwd() / LOG_ROOT)


# Creating.


def run_dir_name(scope: str) -> str:
    """`<yyyymmdd-hhmmss>-<scope>`, local time, because a person reads it.

    Separate from `run_dir` so `--dry-run` can name the directory it would create without
    creating one, and so the name is composed in one place.
    """
    return f"{datetime.now().strftime(STAMP_FORMAT)}-{scope}"


def run_dir(root: Path | str, scope: str) -> Path:
    """`<root>/<yyyymmdd-hhmmss>-<scope>`, created.

    A second invocation inside the same second appends `-2`, then `-3`, so two runs never
    share a directory.
    """
    return _unique(Path(root), run_dir_name(scope))


def plugin_dir(run_directory: Path | str, name: str) -> Path:
    """`<run_dir>/<slug>`, created, with the same `-2` suffix on a collision.

    Two plugins in one sweep whose manifests carry the same `name` therefore get two
    directories, so neither result document overwrites the other and the verdict reads both.
    """
    return _unique(Path(run_directory), slug(name))


def _unique(parent: Path, base: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    candidate = parent / base
    suffix = 1
    while candidate.exists():
        suffix += 1
        candidate = parent / f"{base}-{suffix}"
    candidate.mkdir()
    return candidate


# Recording.


def write_env(
    run_directory: Path | str,
    backend: str,
    image: str | None = None,
    credential: str | None = None,
    env_passthrough: Sequence[str] = (),
) -> Path:
    """`env.txt`: one `name: value` line per row, in a fixed order.

    A command that does not run records the failure on its own line rather than raising: a
    log that says why a version is unknown is worth more than an invocation that stops for
    it. `image` is the container backend's, and is absent on every other.

    `credential` is the container backend's route, `docker.credential`. Two runs of the same
    image on the same host authenticated Claude Code differently under the two routes, and
    the route name is what says which. The route and never a name it forwards: the names
    each route owns are fixed and are in docs/docker.md.

    `env_passthrough` is the container backend's too, and is the names the run forwarded into
    the container. The names and never a value: what each one held is the host's, and it
    reaches the container's environment and no artefact. docs/docker.md.
    """
    rows = [
        ("cowork_evals", distribution_version()),
        ("claude", _command_version(["claude", "--version"])),
        ("python3", _command_version(["python3", "-V"])),
        ("backend", backend),
    ]
    if image is not None:
        rows.append(("image", image))
    if credential is not None:
        rows.append(("credential", credential))
    if env_passthrough:
        rows.append(("env_passthrough", " ".join(env_passthrough)))
    path = Path(run_directory) / ENV_FILE
    path.write_text("".join(f"{name}: {value}\n" for name, value in rows), encoding="utf-8")
    return path


def distribution_version() -> str:
    """The installed distribution's version, which `--version` prints and `env.txt` records.

    A checkout that is not installed says so rather than raising: a log that names the
    reason is worth more than an invocation that stops for it.
    """
    try:
        return metadata.version(DISTRIBUTION)
    except metadata.PackageNotFoundError as error:
        return f"unavailable: {error}"


def _command_version(argv: list[str]) -> str:
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    except OSError as error:
        return f"unavailable: {error}"
    if completed.returncode != 0:
        return f"unavailable: {argv[0]} exited {completed.returncode}"
    return completed.stdout.strip() or f"unavailable: {argv[0]} printed nothing"


def point_latest(root: Path | str, run_directory: Path | str) -> Path:
    """A relative symlink at `<root>/latest`, replaced atomically.

    Written under a temporary name and moved onto the existing link with `os.replace`, so
    `latest` is never absent between two runs and never half-written.
    """
    root = Path(root)
    link = root / LATEST
    temporary = root / f".{LATEST}.new"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(Path(run_directory).name, target_is_directory=True)
    os.replace(temporary, link)
    return link


# Deleting.


def unseal(path: Path | str) -> None:
    """Make a tree readable and writable again, from the top down.

    `claude plugin eval --keep-temp` leaves each kept sandbox read-only, with the two trees
    the plugin under test wrote at mode 000 under `sealed/`. Nothing can be read out of one
    or deleted until the modes are put back, and a directory cannot be listed before it is
    chmodded, so this walks and chmods in the same pass rather than globbing first.

    Directories alone: a file under a kept sandbox is already readable, and the mode of a
    file the agent wrote is worth keeping as it is.

    A path that is not there, and one this process does not own, are both left alone. This
    never raises, because it is a step before an operation that reports its own failure.
    """
    stack = [Path(path)]
    while stack:
        current = stack.pop()
        try:
            current.chmod(0o700)
            entries = list(current.iterdir())
        except OSError:
            continue
        stack += [child for child in entries if child.is_dir() and not child.is_symlink()]


def remove_tree(path: Path | str) -> None:
    """Delete one tree under the log root. Every deletion of one goes through here.

    It unseals first, so a kept harness sandbox is deletable. `shutil.rmtree` on its own
    raises on the mode-000 trees such a sandbox carries, and a run directory holding one is
    then never pruned. See [traces.py](traces.py).
    """
    unseal(path)
    shutil.rmtree(path)


# Pruning.


def prune(root: Path | str, days: int) -> list[Path]:
    """Delete run directories older than `days`, and return what was deleted.

    The age is read from the directory name, never from the modification time: reading a
    log moves that time, and a directory nobody has opened is not younger than one somebody
    has. Nothing else under the root is touched, so a file a developer left there stays.
    """
    root = Path(root)
    if not root.is_dir():
        return []
    cutoff = datetime.now() - timedelta(days=days)
    deleted = []
    for child in sorted(root.iterdir()):
        stamp = _stamp(child)
        if stamp is None or stamp >= cutoff:
            continue
        remove_tree(child)
        deleted.append(child)
    _repoint_latest(root)
    return deleted


def _stamp(child: Path) -> datetime | None:
    """The run directory's own stamp, or `None` for anything that is not one."""
    if not child.is_dir() or child.is_symlink():
        return None
    matched = STAMP_PATTERN.match(child.name)
    if matched is None:
        return None
    try:
        return datetime.strptime(matched.group(1), STAMP_FORMAT)
    except ValueError:
        return None


def _repoint_latest(root: Path) -> None:
    """Point `latest` at the newest run directory left, or remove it when none is."""
    link = root / LATEST
    if not link.is_symlink():
        return
    if link.exists():
        return
    remaining = sorted(child.name for child in root.iterdir() if _stamp(child) is not None)
    if not remaining:
        link.unlink()
        return
    point_latest(root, root / remaining[-1])


# Capturing.


@contextlib.contextmanager
def tee(run_directory: Path | str) -> Iterator[Path]:
    """Everything written to file descriptors 1 and 2 reaches both the terminal and `run.log`.

    At the descriptor level, not by wrapping `sys.stdout`. A child process inherits
    descriptors 1 and 2, so the harness's output and the container's reach the file;
    wrapping the Python object would capture this process alone and leave the log empty
    for every backend that runs a subprocess.

    The copy is bytes and is never decoded, so a progress carriage return survives and a
    partial multi-byte character is not mangled at a chunk boundary.
    """
    path = Path(run_directory) / RUN_LOG
    log = path.open("wb")
    saved_out = os.dup(1)
    saved_err = os.dup(2)
    read_fd, write_fd = os.pipe()
    thread = threading.Thread(target=_pump, args=(read_fd, saved_out, log))
    thread.start()
    try:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(write_fd, 1)
        os.dup2(write_fd, 2)
        os.close(write_fd)
        yield path
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        # Restoring both descriptors drops the last reference to the write end, so the
        # thread's read returns empty and it finishes on its own. It is joined before the
        # saved descriptors are closed, because it writes to one of them and a close under
        # a write in flight is `OSError: Bad file descriptor` on the last chunk.
        os.dup2(saved_out, 1)
        os.dup2(saved_err, 2)
        thread.join()
        os.close(saved_out)
        os.close(saved_err)
        os.close(read_fd)
        log.close()


def _pump(read_fd: int, terminal_fd: int, log: BinaryIO) -> None:
    """Copy bytes to the saved terminal descriptor and to the file, until the pipe closes."""
    while True:
        chunk = os.read(read_fd, 65536)
        if not chunk:
            return
        os.write(terminal_fd, chunk)
        log.write(chunk)
        log.flush()
