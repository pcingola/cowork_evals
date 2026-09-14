"""`cowork_evals.yaml`, and the frozen `Config` it produces.

Every setting this package defines is in that file. There is no second route: nothing is read
from the process environment except the variables `docker.env_passthrough` names, whose values
are forwarded into the run container and read as configuration nowhere, and there is no
`.env`. The four sections and the ladder over
them are docs/library.md. The `cowork:` keys and their defaults are docs/cowork_driver.md, the
`eval:` keys docs/running_evals.md, the `docker:` keys docs/docker.md and the `panel:` key
docs/panel.md.

A section is named for the thing that reads it: `cowork:` the driver, `eval:` the `claude plugin
eval` argument list and the CoWork backend's judge, `docker:` the container backend, `panel:`
the eval panel.

`CoWorkError` lives here because configuration is the first thing that fails, and `cowork.py`
imports it rather than the other way round.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, TypeVar

import yaml

CONFIG_FILENAME = "cowork_evals.yaml"

# What `docker.env_passthrough` may name: the shape a shell accepts as a variable name. The
# one exception to the rule that nothing is read from the process environment is
# docs/library.md, and what the container backend does with the names is docs/docker.md.
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# The deep link prompt cap. docs/cowork_desktop.md.
PROMPT_LIMIT = 14336

# What `eval.ablation` may be, and the flag each value becomes. `none` runs one arm, the
# with-arm; `with-without` runs a no-plugin baseline arm beside it and the document then
# carries a per-case delta. They live here rather than in `harness.py` because the converter
# below reads them, and `harness.py` imports this module and not the other way round.
# docs/running_evals.md.
ABLATION_NONE = "none"
ABLATION_WITH_WITHOUT = "with-without"
ABLATION_CHOICES = (ABLATION_NONE, ABLATION_WITH_WITHOUT)

# What `cowork.consent` may be. `dialog` shows the modal once per process, `none` fires
# without asking and is the documented route for an unattended run. docs/cowork_driver.md.
# They live here rather than in `cowork.py` because the converter below reads them, and
# `cowork.py` imports this module and not the other way round.
CONSENT_DIALOG = "dialog"
CONSENT_NONE = "none"
CONSENT_CHOICES = (CONSENT_DIALOG, CONSENT_NONE)

# What `docker.credential` may be, and it decides how the run container authenticates Claude
# Code. `login` mounts the claude.ai login this package owns; `bedrock` forwards the variables
# a Bedrock host already has and mounts nothing. They live here rather than in `docker/` for
# the reason above: the converter below reads them. docs/docker.md.
CREDENTIAL_LOGIN = "login"
CREDENTIAL_BEDROCK = "bedrock"
CREDENTIAL_CHOICES = (CREDENTIAL_LOGIN, CREDENTIAL_BEDROCK)


class CoWorkError(Exception):
    """A driver failure, carrying its taxonomy code from docs/cowork_driver.md."""

    def __init__(self, code: int, message: str, session_dir: Path | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.session_dir = session_dir


# One converter per field. `name` arrives qualified, `<section>.<key>`, so a message names
# the line a reader has to change.


def _absolute(value: Path | str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path.cwd() / path


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise CoWorkError(2, f"{name}: expected a string, got {type(value).__name__}")
    return value


def _optional_text(name: str, value: Any) -> str | None:
    return None if value is None else _text(name, value)


def _seconds(name: str, value: Any) -> float:
    return float(_amount(name, value))


def _amount(name: str, value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CoWorkError(2, f"{name}: expected a number, got {type(value).__name__}")
    if value < 0:
        raise CoWorkError(2, f"{name}: expected a number at or above zero, got {value}")
    return value


def _count(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CoWorkError(2, f"{name}: expected an integer, got {type(value).__name__}")
    if value < 0:
        raise CoWorkError(2, f"{name}: expected an integer at or above zero, got {value}")
    return value


def _path(name: str, value: Any) -> Path:
    if isinstance(value, Path):
        return _absolute(value)
    return _absolute(_text(name, value))


def _optional_path(name: str, value: Any) -> Path | None:
    return None if value is None else _path(name, value)


def _fraction(name: str, value: Any) -> int | float:
    """A number from 0 to 1. A case score is a mean of grader results and is in that range,
    so a delta is in -1 to 1 and a threshold above 1 is one no case can meet."""
    amount = _amount(name, value)
    if amount > 1:
        raise CoWorkError(2, f"{name}: expected a number from 0 to 1, got {value}")
    return amount


def _ablation(name: str, value: Any) -> str:
    if _text(name, value) not in ABLATION_CHOICES:
        raise CoWorkError(2, f"{name}: expected one of {', '.join(ABLATION_CHOICES)}, got {value}")
    return value


def _credential(name: str, value: Any) -> str:
    if _text(name, value) not in CREDENTIAL_CHOICES:
        raise CoWorkError(
            2, f"{name}: expected one of {', '.join(CREDENTIAL_CHOICES)}, got {value}"
        )
    return value


def _consent(name: str, value: Any) -> str:
    if _text(name, value) not in CONSENT_CHOICES:
        raise CoWorkError(2, f"{name}: expected one of {', '.join(CONSENT_CHOICES)}, got {value}")
    return value


def _flag(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise CoWorkError(2, f"{name}: expected true or false, got {type(value).__name__}")
    return value


def _tools(name: str, value: Any) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise CoWorkError(2, f"{name}: expected a list of tool names, got {type(value).__name__}")
    return tuple(_text(name, item) for item in value)


def _env_names(name: str, value: Any) -> tuple[str, ...]:
    """A list of environment variable names, each one a name a shell would accept.

    A value that is not a name is refused at load, with the line named, rather than reaching
    `docker run` as an argument it would take for the start of the image tag.
    """
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise CoWorkError(
            2, f"{name}: expected a list of variable names, got {type(value).__name__}"
        )
    names = tuple(_text(name, item) for item in value)
    for item in names:
        if not ENV_NAME.fullmatch(item):
            raise CoWorkError(2, f"{name}: {item!r} is not an environment variable name")
    return names


def _convert(section: Any) -> None:
    """Run the section's whole table, so a value is converted in exactly one place."""
    for key, convert in section._FIELDS.items():
        object.__setattr__(section, key, convert(f"{section._NAME}.{key}", getattr(section, key)))


def checked(section: type[Any], key: str, value: Any, *, name: str) -> Any:
    """One value through the converter its setting uses, refused under `name`.

    A command-line option and a line in the file are two rungs of one ladder, so a value is
    checked the same way whichever rung supplied it. `name` is what the reader has to change,
    which is the option an operator typed rather than the `<section>.<key>` a file carries.
    docs/library.md.
    """
    return section._FIELDS[key](name, value)


@dataclass(frozen=True, slots=True)
class CoWorkSection:
    """What the CoWork driver reads. docs/cowork_driver.md."""

    _NAME: ClassVar[str] = "cowork"

    profile: str | None = None
    surface: str = "cowork"
    settle_seconds: float = 3.0
    session_timeout: float = 120.0
    idle_seconds: float = 20.0
    run_timeout: float = 1800.0
    max_runs: int = 50
    consent: str = CONSENT_DIALOG
    consent_timeout: float = 10.0
    run_log: Path = Path("~/.cowork-runs.jsonl")
    log_dir: Path | None = Path("logs")

    _FIELDS: ClassVar[dict[str, Callable[[str, Any], Any]]] = {
        "profile": _optional_text,
        "surface": _text,
        "settle_seconds": _seconds,
        "session_timeout": _seconds,
        "idle_seconds": _seconds,
        "run_timeout": _seconds,
        "max_runs": _count,
        "consent": _consent,
        "consent_timeout": _seconds,
        "run_log": _path,
        "log_dir": _optional_path,
    }

    def __post_init__(self) -> None:
        _convert(self)

    @property
    def profile_dir(self) -> Path:
        """The profile directory. A bare name resolves under Application Support.

        An absolute path is taken as it stands, which is how a test and a developer point
        the driver at a profile that is not in the default location.

        Raises when `profile` is unset, which is how a missing profile is refused at the
        first call that needs one rather than at construction.
        """
        if not self.profile:
            raise CoWorkError(
                2, f"no CoWork profile configured: set cowork.profile in {CONFIG_FILENAME}"
            )
        named = Path(self.profile).expanduser()
        if named.is_absolute():
            return named
        return Path.home() / "Library" / "Application Support" / self.profile

    @property
    def sessions_root(self) -> Path:
        """Where the application writes sessions. docs/cowork_desktop.md."""
        return self.profile_dir / "local-agent-mode-sessions"


@dataclass(frozen=True, slots=True)
class EvalSection:
    """What the `claude plugin eval` argument list reads. docs/running_evals.md.

    `judge_model` has a second reader: the CoWork backend's judge, which is `claude -p` and
    not that command line. docs/cowork_driver.md.
    """

    _NAME: ClassVar[str] = "eval"

    model: str = "sonnet"
    judge_model: str = "haiku"
    # What a CoWork session can do, named in the container's own tool names. A session
    # grants nothing and acts, so a container run that is denied a tool a session has is
    # measuring this package's configuration and not the plugin. docs/running_evals.md.
    allow_tools: tuple[str, ...] = (
        "Bash",
        "Read",
        "Glob",
        "Grep",
        "Write",
        "Edit",
        "WebFetch",
        "Skill",
    )
    # Off, because the baseline arm runs every case twice and so costs twice as much, and
    # because it stops scoring a `tool_used: Skill` grader in either arm.
    # docs/running_evals.md.
    ablation: str = ABLATION_NONE
    # What a case's delta has to reach under `with-without`. It is read by `verdict.py` and
    # never emitted into the harness command line, which is why `--threshold` stays pinned
    # to 0. docs/running_evals.md.
    delta_threshold: int | float = 0
    max_cost_usd: int | float = 5
    # It bounds a whole invocation rather than a run, so the sweep reads it and not the
    # `claude plugin eval` argument list: `cli.py` checks the spend so far before each
    # plugin, and a stop becomes a failed run. docs/running_evals.md.
    max_cost_total_usd: int | float = 25
    # On, so a failing case can be diagnosed without running the suite again. Both backends
    # honour it: `cli.py` gates the collection on it either way. docs/running_evals.md.
    keep_traces: bool = True

    _FIELDS: ClassVar[dict[str, Callable[[str, Any], Any]]] = {
        "model": _text,
        "judge_model": _text,
        "allow_tools": _tools,
        "ablation": _ablation,
        "delta_threshold": _fraction,
        "max_cost_usd": _amount,
        "max_cost_total_usd": _amount,
        "keep_traces": _flag,
    }

    def __post_init__(self) -> None:
        _convert(self)


@dataclass(frozen=True, slots=True)
class DockerSection:
    """What the container backend reads. docs/docker.md."""

    _NAME: ClassVar[str] = "docker"

    platform: str = "linux/arm64"
    claude_code_version: str = "2.1.265"
    # How the run container authenticates Claude Code itself. `login` is the default, and
    # `login_dir` is read only under it. docs/docker.md.
    credential: str = CREDENTIAL_LOGIN
    login_dir: Path = Path("~/.cache/cowork_evals/claude")
    extra_ca_file: Path | None = None
    # The one route from the process environment into a run, for a credential the skill under
    # test reads. Empty by default, so a repository that names none is unaffected. It is not
    # the route for Claude's own credential, which is `credential` above. docs/docker.md.
    env_passthrough: tuple[str, ...] = ()

    _FIELDS: ClassVar[dict[str, Callable[[str, Any], Any]]] = {
        "platform": _text,
        "claude_code_version": _text,
        "credential": _credential,
        "login_dir": _path,
        "extra_ca_file": _optional_path,
        "env_passthrough": _env_names,
    }

    def __post_init__(self) -> None:
        _convert(self)


@dataclass(frozen=True, slots=True)
class PanelSection:
    """What the eval panel reads. docs/panel.md.

    `root` is the history tree, and it is not under `--out`: that option relocates what one
    invocation produced, and a record outlives the invocation that wrote it.
    """

    _NAME: ClassVar[str] = "panel"

    root: Path = Path("logs") / "evals" / "history"

    _FIELDS: ClassVar[dict[str, Callable[[str, Any], Any]]] = {
        "root": _path,
    }

    def __post_init__(self) -> None:
        _convert(self)


@dataclass(frozen=True, slots=True)
class Config:
    """The whole file. One frozen section per reader, and never reassigned."""

    cowork: CoWorkSection = field(default_factory=CoWorkSection)
    eval: EvalSection = field(default_factory=EvalSection)
    docker: DockerSection = field(default_factory=DockerSection)
    panel: PanelSection = field(default_factory=PanelSection)

    @classmethod
    def load(cls, path: Path | str | None = None) -> Config:
        """Read the configuration file and freeze the result.

        `path` defaults to `cowork_evals.yaml` in the working directory, and a missing
        default file is not an error. A file named explicitly must exist, so a mistyped
        path is never a silent set of defaults.
        """
        document, source = _read(path)
        return cls(
            cowork=_section(document, source, CoWorkSection),
            eval=_section(document, source, EvalSection),
            docker=_section(document, source, DockerSection),
            panel=_section(document, source, PanelSection),
        )


# A section field of `Config` is named for its section key, so a new section is one
# dataclass and one line in `Config`.
_Sections = CoWorkSection | EvalSection | DockerSection | PanelSection
_S = TypeVar("_S", bound=_Sections)


def _read(path: Path | str | None) -> tuple[dict[str, Any], str]:
    named = path is not None
    file = Path(path).expanduser() if named else Path.cwd() / CONFIG_FILENAME
    if not file.is_file():
        if named:
            raise CoWorkError(2, f"{file}: no such configuration file")
        return {}, str(file)

    try:
        document = yaml.safe_load(file.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise CoWorkError(2, f"{file}: unreadable configuration: {error}") from error

    if document is None:
        return {}, str(file)
    if not isinstance(document, dict):
        raise CoWorkError(2, f"{file}: expected a mapping at the top level")
    return document, str(file)


def _section(document: dict[str, Any], source: str, kind: type[_S]) -> _S:
    """One section of the document. An unknown top level section is ignored, not read."""
    values = document.get(kind._NAME)
    if values is None:
        return kind()
    if not isinstance(values, dict):
        raise CoWorkError(2, f"{source}: expected a mapping under {kind._NAME}:")
    return kind(**_checked(values, source, kind))


def _override(section: _S, overrides: dict[str, Any]) -> _S:
    """Apply constructor overrides to an already-resolved section."""
    if not overrides:
        return section
    return dataclasses.replace(section, **_checked(overrides, "override", type(section)))


def _checked(values: dict[str, Any], source: str, kind: type[_Sections]) -> dict[str, Any]:
    """Refuse an unknown key. The values themselves are converted by `__post_init__`."""
    unknown = sorted(set(values) - set(kind._FIELDS))
    if unknown:
        raise CoWorkError(2, f"{source}: unknown {kind._NAME} key {', '.join(unknown)}")
    return values
