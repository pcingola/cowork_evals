"""The image pytest runs in: the digest, the build and the check.

The design is docs/cowork_test.md. It is one layer over the eval image, and `Dockerfile.pytest`
beside this file is that layer.

One module per image. [`__init__.py`](__init__.py) owns the image the harness runs in and this
owns the image pytest runs in, and each owns its Dockerfile, its digest, its argument lists and
its check. The command that fixes an absent image is therefore written here for this image and
there for that one.

A `PytestImage` holds frozen configuration and does no work at construction, so
`PytestImage().digest` answers on a machine with no daemon. That is `Docker`'s rule and it holds
here.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from ..config import Config
from . import (
    CONTAINER_HOME,
    CONTAINER_PLUGIN,
    DATA,
    DIGEST_LENGTH,
    Condition,
    Docker,
    DockerError,
    Unmet,
    plugin_root,
    remedy,
)

DOCKERFILE = Path(__file__).parent / "Dockerfile.pytest"
REQUIREMENTS_TEST = DATA / "requirements_test.txt"

# The image tag prefix. There is no `latest`, for the reason in docs/docker.md.
REPOSITORY = "cowork-evals-test"

# The one command that builds this image, as `remedy` in `__init__.py` is the one command
# that builds the base. `setup --docker` builds both, in that order. docs/cli.md.
BUILD_REMEDY = "run cowork_evals setup --docker"


def digest_of(*parts: bytes) -> str:
    """Every build input, hashed in order and truncated. `digest` is the one caller.

    Separate from it so a test can vary an input that is a file on disk rather than a
    configuration key, without a patch and without a second implementation of the hash.
    """
    sha = hashlib.sha256()
    for part in parts:
        sha.update(part)
        sha.update(b"\0")
    return sha.hexdigest()[:DIGEST_LENGTH]


class PytestImage:
    """One resolved test image configuration, over one resolved eval image."""

    def __init__(self, config: Config | None = None) -> None:
        """Every setting resolved once, through the `Docker` this image is built over.

        `config` defaults to `cowork_evals.yaml` in the working directory. There is no
        `pytest:` section: this image takes its platform and its base from `docker:`.
        """
        self._config = config if config is not None else Config.load()
        self.docker = Docker(self._config)
        self.platform = self.docker.platform

    # The build arguments, the digest, and the tag over it.

    @property
    def build_args(self) -> dict[str, str]:
        """The one `ARG` the Dockerfile declares, and the only source of its value."""
        return {"BASE_TAG": self.docker.tag}

    @property
    def digest(self) -> str:
        """Every build input, hashed, the base image's digest first.

        A rebuilt base is therefore a different test tag, never a stale hit over an old
        base. The platform is already inside the base digest and is hashed again here, so
        this list is every input on its own terms.
        """
        return digest_of(
            self.docker.digest.encode(),
            DOCKERFILE.read_bytes(),
            REQUIREMENTS_TEST.read_bytes(),
            self.platform.encode(),
        )

    @property
    def tag(self) -> str:
        return f"{REPOSITORY}:{self.digest}"

    # The argument list.

    def build_argv(self, *, no_cache: bool = False) -> list[str]:
        """The build. The context is the package data directory, as the eval image's is.

        No build secret: the base image already carries the extra root CA when the host
        that built it supplied one, and this layer reaches PyPI alone.
        """
        argv = [
            "docker",
            "build",
            "--platform",
            self.platform,
            "-f",
            str(DOCKERFILE),
        ]
        for name, value in self.build_args.items():
            argv += ["--build-arg", f"{name}={value}"]
        argv += ["-t", self.tag]
        if no_cache:
            argv.append("--no-cache")
        argv.append(str(DATA))
        return argv

    def run_argv(self, target: Path | str, *, pytest_args: tuple[str, ...] = ()) -> list[str]:
        """One pytest invocation, as a container. Nothing stands between the two.

        Everything after `python3 -m pytest` is the resolved target and then the caller's
        tail, verbatim and in that order. This package chooses no pytest option: not
        `-p no:cacheprovider`, not `-q`, not a colour flag. Whatever `pytest <path>` does
        on a laptop is what it does here.

        The plugin root goes in read-write, unlike a `run --docker`: pytest writes
        `.pytest_cache` and `__pycache__` beside a suite on a laptop, and a read-only
        mount would change what that suite does. The container runs as the host uid and
        gid, so what it writes into the tree is the developer's and not root's.

        No credential mount, no `--security-opt`, no enablement variable, no `--network`
        flag and no log mount. There is no model call and no `Bash` grant here, so none of
        them has a reason.

        No `PYTHONPATH` either. The image sets its own, for pyuno, and overwriting it
        would remove `import uno` from the runtime this reproduces. The working directory
        is the plugin root, so pytest's rootdir is the plugin root and the consumer's own
        configuration file there is the one that is read.
        """
        root = plugin_root(target)
        relative = Path(target).resolve().relative_to(root)
        container_target = CONTAINER_PLUGIN
        if relative != Path("."):
            container_target = f"{CONTAINER_PLUGIN}/{relative.as_posix()}"
        return [
            "docker",
            "run",
            "--rm",
            "--platform",
            self.platform,
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--env",
            f"HOME={CONTAINER_HOME}",
            *self.docker.extra_ca_env_argv(),
            "-v",
            f"{root}:{CONTAINER_PLUGIN}:rw",
            "-w",
            CONTAINER_PLUGIN,
            self.tag,
            "python3",
            "-m",
            "pytest",
            container_target,
            *pytest_args,
        ]

    # Doing the work.

    def build(self, *, no_cache: bool = False) -> None:
        """Build the image, streaming the output. A non-zero exit raises.

        An absent base image is a failure naming it, never an implicit base build: that
        build takes minutes and belongs to whoever asked for it.
        """
        if not self.docker.image_is_present():
            raise DockerError(f"base image {self.docker.tag} is absent: {remedy(Condition.IMAGE)}")
        completed = subprocess.run(self.build_argv(no_cache=no_cache))
        if completed.returncode != 0:
            raise DockerError(f"docker build failed with exit {completed.returncode}: {self.tag}")

    def image_is_present(self) -> bool:
        completed = subprocess.run(
            ["docker", "image", "inspect", self.tag],
            capture_output=True,
            text=True,
        )
        return completed.returncode == 0

    def run(self, target: Path | str, *, pytest_args: tuple[str, ...] = ()) -> int:
        """Run one container and return the exit code pytest produced, unchanged.

        Not remapped, not collapsed, not interpreted: `5`, no test collected, stays `5`.
        A red suite is a result and not an error, so nothing here raises on an exit code.
        The terminal is inherited, so pytest's output reaches it as pytest wrote it.

        An unreachable daemon or an absent image raises before any container starts. That
        is a precondition, and the caller turns it into its own exit code.
        """
        unmet = self.check()
        if unmet:
            raise DockerError("; ".join(line.message for line in unmet))
        return subprocess.run(self.run_argv(target, pytest_args=pytest_args)).returncode

    def check(self) -> list[Unmet]:
        """The unmet conditions, in order, each with the command that fixes it.

        An empty list means ready. It writes nothing and builds nothing.
        `Condition.CREDENTIAL` is never returned: there is no login in this path.
        """
        unmet: list[Unmet] = []
        if not self.docker.daemon_is_reachable():
            unmet.append(
                Unmet(
                    Condition.DAEMON,
                    f"docker daemon is not reachable: {remedy(Condition.DAEMON)}",
                )
            )
        # Neither image is readable without a daemon. The base is reported before the
        # layer over it, because building the layer needs it.
        elif not self.docker.image_is_present():
            unmet.append(
                Unmet(
                    Condition.IMAGE,
                    f"base image {self.docker.tag} is absent: {remedy(Condition.IMAGE)}",
                )
            )
        elif not self.image_is_present():
            unmet.append(Unmet(Condition.IMAGE, f"image {self.tag} is absent: {BUILD_REMEDY}"))
        return unmet
