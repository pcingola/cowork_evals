"""`cowork_evals.yaml` loads as docs/library.md says it does.

One file, four sections, and no other route. Every test writes a real file and reads it
back through the real loader.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cowork_evals.config import (
    CONFIG_FILENAME,
    CONSENT_NONE,
    CREDENTIAL_BEDROCK,
    Config,
    CoWorkError,
    CoWorkSection,
    DockerSection,
    EvalSection,
    PanelSection,
)

# The variable table in docs/runtime.md, "What the host provides": the complete environment
# of a CoWork session shell, and the one record `docker.session_env` defaults to.
RUNTIME = Path(__file__).resolve().parents[2] / "docs" / "runtime.md"
RUNTIME_VARIABLES = tuple(
    re.findall(
        r"^\| `([A-Z_]+)` +\|",
        RUNTIME.read_text(encoding="utf-8").split("| Variable ", 1)[1].split("\n\n", 1)[0],
        re.MULTILINE,
    )
)


def write(directory: Path, body: str, name: str = CONFIG_FILENAME) -> Path:
    file = directory / name
    file.write_text(body, encoding="utf-8")
    return file


def test_missing_file_yields_the_documented_defaults(working_directory, tmp_path: Path) -> None:
    with working_directory(tmp_path):
        config = Config.load()
    assert config == Config(
        cowork=CoWorkSection(
            profile=None,
            surface="cowork",
            settle_seconds=3.0,
            session_timeout=120.0,
            idle_seconds=20.0,
            run_timeout=1800.0,
            max_runs=50,
            consent="dialog",
            consent_timeout=10.0,
            run_log=Path.home() / ".cowork-runs.jsonl",
            log_dir=tmp_path / "logs",
        ),
        eval=EvalSection(
            model="sonnet",
            judge_model="haiku",
            judge_votes=3,
            # The session mirror, in the container's tool names. docs/running_evals.md.
            allow_tools=("Bash", "Read", "Glob", "Grep", "Write", "Edit", "WebFetch", "Skill"),
            ablation="none",
            delta_threshold=0,
            max_cost_usd=5,
            max_cost_total_usd=25,
            keep_traces=True,
        ),
        docker=DockerSection(
            platform="linux/arm64",
            claude_code_version="2.1.265",
            credential="login",
            login_dir=Path.home() / ".cache" / "cowork_evals" / "claude",
            extra_ca_file=None,
            env_passthrough=(),
            session_env=RUNTIME_VARIABLES,
            keep_env=(
                "NODE_EXTRA_CA_CERTS",
                "CLAUDE_PLUGIN_ROOT",
                "CLAUDE_PLUGIN_DATA",
                "CLAUDE_PROJECT_DIR",
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "NO_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
                "no_proxy",
            ),
        ),
        # The history sits under the log root, not under `--out`. docs/panel.md.
        panel=PanelSection(root=tmp_path / "logs" / "evals" / "history"),
    )


def test_every_section_is_read_from_one_file(tmp_path: Path) -> None:
    file = write(
        tmp_path,
        "cowork:\n"
        "  profile: Fixture\n"
        "eval:\n"
        "  model: opus\n"
        "  allow_tools: [Bash, Write]\n"
        "docker:\n"
        "  platform: linux/amd64\n"
        "panel:\n"
        "  root: /elsewhere/history\n",
    )
    config = Config.load(file)
    assert config.cowork.profile == "Fixture"
    assert config.eval.model == "opus"
    assert config.eval.allow_tools == ("Bash", "Write")
    assert config.docker.platform == "linux/amd64"
    assert config.panel.root == Path("/elsewhere/history")


@pytest.mark.parametrize(
    "config",
    [
        Config(),
        Config(cowork=CoWorkSection(profile="Fixture", consent=CONSENT_NONE, log_dir=None)),
        Config(eval=EvalSection(model="opus", allow_tools=("Bash", "Write"))),
        Config(eval=EvalSection(keep_traces=False, max_cost_usd=2.5, ablation="with-without")),
        Config(
            docker=DockerSection(
                credential=CREDENTIAL_BEDROCK,
                extra_ca_file=Path("/etc/ca.pem"),
                env_passthrough=("ACME_API_KEY",),
            )
        ),
        Config(panel=PanelSection(root=Path("/elsewhere/history"))),
    ],
)
def test_a_dumped_configuration_loads_back_equal(tmp_path: Path, config: Config) -> None:
    file = tmp_path / CONFIG_FILENAME
    config.dump(file)
    assert Config.load(file) == config


@pytest.mark.parametrize(
    ("body", "profile"),
    [("", None), ("cowork:\n", None), ("cowork:\n  profile: Fixture\n", "Fixture")],
)
def test_a_section_the_file_omits_is_the_default(
    tmp_path: Path, body: str, profile: str | None
) -> None:
    assert Config.load(write(tmp_path, body)) == Config(cowork=CoWorkSection(profile=profile))


@pytest.mark.parametrize(
    ("key", "name"),
    [("env_passthrough", "1ACME"), ("session_env", "acme-key"), ("keep_env", "ACME=1")],
)
def test_a_name_no_shell_would_accept_is_refused_at_load(
    tmp_path: Path, key: str, name: str
) -> None:
    file = write(tmp_path, f"docker:\n  {key}: ['{name}']\n")
    with pytest.raises(CoWorkError) as raised:
        Config.load(file)
    assert raised.value.code == 2
    assert f"docker.{key}" in str(raised.value)


@pytest.mark.parametrize(
    ("body", "first", "second"),
    [
        ("  keep_env: [HOME]\n", "session_env", "keep_env"),
        ("  env_passthrough: [PATH]\n", "session_env", "env_passthrough"),
        ("  env_passthrough: [ACME]\n  keep_env: [ACME]\n", "env_passthrough", "keep_env"),
    ],
)
def test_a_name_in_two_lists_is_refused_naming_both(
    tmp_path: Path, body: str, first: str, second: str
) -> None:
    file = write(tmp_path, "docker:\n" + body)
    with pytest.raises(CoWorkError) as raised:
        Config.load(file)
    assert raised.value.code == 2
    assert f"docker.{first}" in str(raised.value)
    assert f"docker.{second}" in str(raised.value)


def test_unknown_top_level_section_is_ignored(tmp_path: Path) -> None:
    file = write(tmp_path, "venv:\n  anything: 1\ncowork:\n  profile: Fixture\n")
    assert Config.load(file).cowork.profile == "Fixture"


def test_a_named_file_that_is_absent_raises(tmp_path: Path) -> None:
    with pytest.raises(CoWorkError) as raised:
        Config.load(tmp_path / "absent.yaml")
    assert raised.value.code == 2


@pytest.mark.parametrize(
    ("body", "typo"),
    [
        ("cowork:\n  profil: Fixture\n", "profil"),
        ("eval:\n  modle: opus\n", "modle"),
        ("docker:\n  platfrom: linux/amd64\n", "platfrom"),
        ("panel:\n  rot: x\n", "rot"),
    ],
)
def test_an_unknown_key_inside_a_known_section_raises(tmp_path: Path, body: str, typo: str) -> None:
    file = write(tmp_path, body)
    with pytest.raises(CoWorkError) as raised:
        Config.load(file)
    assert raised.value.code == 2
    assert typo in str(raised.value)


# One case per converter in config.py.
@pytest.mark.parametrize(
    ("body", "key"),
    [
        ("cowork:\n  max_runs: many\n", "cowork.max_runs"),
        ("cowork:\n  consent_timeout: soon\n", "cowork.consent_timeout"),
        ("eval:\n  max_cost_usd: five\n", "eval.max_cost_usd"),
        ("eval:\n  delta_threshold: -1\n", "eval.delta_threshold"),
        ("eval:\n  delta_threshold: 2\n", "eval.delta_threshold"),
        ("eval:\n  judge_votes: 0\n", "eval.judge_votes"),
        ("docker:\n  platform: 3\n", "docker.platform"),
        ("cowork:\n  run_log: 3\n", "cowork.run_log"),
        ("eval:\n  ablation: with-only\n", "eval.ablation"),
        ("docker:\n  credential: token\n", "docker.credential"),
        ("cowork:\n  consent: yes-please\n", "cowork.consent"),
        ("eval:\n  keep_traces: 'no'\n", "eval.keep_traces"),
        ("eval:\n  allow_tools: Bash Write\n", "eval.allow_tools"),
        ("docker:\n  env_passthrough: ACME_KEY\n", "docker.env_passthrough"),
        ("eval:\n  - model\n", "eval"),
    ],
)
def test_a_wrongly_typed_value_raises(tmp_path: Path, body: str, key: str) -> None:
    file = write(tmp_path, body)
    with pytest.raises(CoWorkError) as raised:
        Config.load(file)
    assert raised.value.code == 2
    assert key in str(raised.value)


def test_a_wrongly_typed_field_raises_however_the_section_was_built() -> None:
    """Conversion is `__post_init__`, so a direct build is checked like a loaded one."""
    with pytest.raises(CoWorkError) as raised:
        CoWorkSection(max_runs="many")  # type: ignore[arg-type]
    assert raised.value.code == 2


def test_a_path_expands_tilde_and_resolves_against_the_working_directory(
    working_directory, tmp_path: Path
) -> None:
    file = write(
        tmp_path,
        "cowork:\n  run_log: ~/somewhere/runs.jsonl\n  log_dir: build/logs\n"
        "docker:\n  login_dir: build/login\npanel:\n  root: build/history\n",
    )
    with working_directory(tmp_path):
        config = Config.load(file)
    assert config.cowork.run_log == Path.home() / "somewhere" / "runs.jsonl"
    assert config.cowork.log_dir == tmp_path / "build" / "logs"
    assert config.docker.login_dir == tmp_path / "build" / "login"
    assert config.panel.root == tmp_path / "build" / "history"


@pytest.mark.parametrize("absolute", [False, True])
def test_sessions_root_is_derived_from_the_profile(tmp_path: Path, absolute: bool) -> None:
    """A bare name resolves under Application Support, an absolute path stands as it is."""
    profile = tmp_path / "profile" if absolute else None
    root = CoWorkSection(profile=str(profile) if profile else "Fixture").sessions_root
    base = profile or Path.home() / "Library" / "Application Support" / "Fixture"
    assert root == base / "local-agent-mode-sessions"
