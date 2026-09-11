"""`cowork_evals.yaml` loads as docs/library.md says it does.

One file, three sections, and no other route. Every test writes a real file and reads it
back through the real loader.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cowork_evals.config import (
    CONFIG_FILENAME,
    Config,
    CoWorkError,
    CoWorkSection,
    DockerSection,
    EvalSection,
)


def write(directory: Path, body: str, name: str = CONFIG_FILENAME) -> Path:
    file = directory / name
    file.write_text(body, encoding="utf-8")
    return file


# The defaults, section by section.


def test_missing_file_yields_the_cowork_defaults(working_directory, tmp_path: Path) -> None:
    with working_directory(tmp_path):
        section = Config.load().cowork
    assert section.profile is None
    assert section.surface == "cowork"
    assert section.settle_seconds == 3.0
    assert section.session_timeout == 120.0
    assert section.idle_seconds == 20.0
    assert section.run_timeout == 1800.0
    assert section.max_runs == 50
    assert section.run_log == Path.home() / ".cowork-runs.jsonl"
    assert section.log_dir == tmp_path / "logs"


def test_missing_file_yields_the_eval_defaults(working_directory, tmp_path: Path) -> None:
    with working_directory(tmp_path):
        section = Config.load().eval
    assert section.model == "sonnet"
    assert section.judge_model == "haiku"
    assert section.allow_tools == ("Bash",)
    assert section.max_cost_usd == 5
    assert section.max_cost_total_usd == 25
    assert section.keep_traces is True


def test_missing_file_yields_the_docker_defaults(working_directory, tmp_path: Path) -> None:
    with working_directory(tmp_path):
        section = Config.load().docker
    assert section.platform == "linux/arm64"
    assert section.claude_code_version == "2.1.265"
    assert section.login_dir == Path.home() / ".cache" / "cowork_evals" / "claude"
    assert section.extra_ca_file is None
    assert section.auth_env == ()


def test_auth_env_is_read_as_a_tuple_of_names(tmp_path: Path) -> None:
    file = write(tmp_path, "docker:\n  auth_env: [CLAUDE_CODE_USE_BEDROCK, AWS_REGION]\n")
    assert Config.load(file).docker.auth_env == ("CLAUDE_CODE_USE_BEDROCK", "AWS_REGION")


def test_an_empty_auth_env_list_is_the_login_route(tmp_path: Path) -> None:
    file = write(tmp_path, "docker:\n  auth_env: []\n")
    assert Config.load(file).docker.auth_env == ()


# The file over the defaults.


def test_every_section_is_read_from_one_file(tmp_path: Path) -> None:
    file = write(
        tmp_path,
        "cowork:\n"
        "  profile: Fixture\n"
        "eval:\n"
        "  model: opus\n"
        "  allow_tools: [Bash, Write]\n"
        "docker:\n"
        "  platform: linux/amd64\n",
    )
    config = Config.load(file)
    assert config.cowork.profile == "Fixture"
    assert config.eval.model == "opus"
    assert config.eval.allow_tools == ("Bash", "Write")
    assert config.docker.platform == "linux/amd64"


def test_a_section_the_file_omits_is_the_default(tmp_path: Path) -> None:
    file = write(tmp_path, "cowork:\n  profile: Fixture\n")
    assert Config.load(file).eval == EvalSection()
    assert Config.load(file).docker == DockerSection()


def test_a_widened_allow_tools_replaces_the_default(tmp_path: Path) -> None:
    file = write(tmp_path, "eval:\n  allow_tools: [Write]\n")
    assert Config.load(file).eval.allow_tools == ("Write",)


def test_unknown_top_level_section_is_ignored(tmp_path: Path) -> None:
    file = write(tmp_path, "venv:\n  anything: 1\ncowork:\n  profile: Fixture\n")
    assert Config.load(file).cowork.profile == "Fixture"


def test_empty_file_yields_defaults(tmp_path: Path) -> None:
    file = write(tmp_path, "")
    assert Config.load(file) == Config.load(write(tmp_path, "cowork:\n", "other.yaml"))


def test_a_named_file_that_is_absent_raises(tmp_path: Path) -> None:
    with pytest.raises(CoWorkError) as raised:
        Config.load(tmp_path / "absent.yaml")
    assert raised.value.code == 2


# An unknown key, in each section.


@pytest.mark.parametrize(
    ("body", "typo"),
    [
        ("cowork:\n  profil: Fixture\n", "profil"),
        ("eval:\n  modle: opus\n", "modle"),
        ("docker:\n  platfrom: linux/amd64\n", "platfrom"),
    ],
)
def test_an_unknown_key_inside_a_known_section_raises(tmp_path: Path, body: str, typo: str) -> None:
    file = write(tmp_path, body)
    with pytest.raises(CoWorkError) as raised:
        Config.load(file)
    assert raised.value.code == 2
    assert typo in str(raised.value)


# A wrongly typed value, in each section.


@pytest.mark.parametrize(
    ("body", "key"),
    [
        ("cowork:\n  max_runs: many\n", "cowork.max_runs"),
        ("eval:\n  max_cost_usd: five\n", "eval.max_cost_usd"),
        ("eval:\n  allow_tools: Bash Write\n", "eval.allow_tools"),
        ("docker:\n  platform: 3\n", "docker.platform"),
        ("docker:\n  auth_env: AWS_REGION\n", "docker.auth_env"),
    ],
)
def test_a_wrongly_typed_value_raises(tmp_path: Path, body: str, key: str) -> None:
    file = write(tmp_path, body)
    with pytest.raises(CoWorkError) as raised:
        Config.load(file)
    assert raised.value.code == 2
    assert key in str(raised.value)


def test_a_section_that_is_not_a_mapping_raises(tmp_path: Path) -> None:
    file = write(tmp_path, "eval:\n  - model\n")
    with pytest.raises(CoWorkError) as raised:
        Config.load(file)
    assert raised.value.code == 2


def test_a_wrongly_typed_field_raises_however_the_section_was_built() -> None:
    """Conversion is `__post_init__`, so a direct build is checked like a loaded one."""
    with pytest.raises(CoWorkError) as raised:
        CoWorkSection(max_runs="many")  # type: ignore[arg-type]
    assert raised.value.code == 2


# The path convention, which every path key follows.


def test_tilde_is_expanded(tmp_path: Path) -> None:
    file = write(tmp_path, "cowork:\n  run_log: ~/somewhere/runs.jsonl\n")
    config = Config.load(file)
    assert config.cowork.run_log == Path.home() / "somewhere" / "runs.jsonl"
    assert "~" not in str(config.cowork.run_log)


def test_a_relative_path_resolves_against_the_working_directory(
    working_directory, tmp_path: Path
) -> None:
    file = write(tmp_path, "cowork:\n  log_dir: build/logs\ndocker:\n  login_dir: build/login\n")
    with working_directory(tmp_path):
        config = Config.load(file)
    assert config.cowork.log_dir == tmp_path / "build" / "logs"
    assert config.docker.login_dir == tmp_path / "build" / "login"


def test_log_dir_null_turns_the_file_off(tmp_path: Path) -> None:
    file = write(tmp_path, "cowork:\n  log_dir: null\n")
    assert Config.load(file).cowork.log_dir is None


# The profile, which has no default.


def test_sessions_root_is_derived_from_the_profile() -> None:
    root = CoWorkSection(profile="Fixture").sessions_root
    assert root == (
        Path.home() / "Library" / "Application Support" / "Fixture" / "local-agent-mode-sessions"
    )


def test_sessions_root_without_a_profile_raises() -> None:
    with pytest.raises(CoWorkError) as raised:
        _ = CoWorkSection().sessions_root
    assert raised.value.code == 2


def test_every_section_is_frozen() -> None:
    config = Config()
    for section, key in ((config.cowork, "profile"), (config.eval, "model")):
        with pytest.raises((AttributeError, TypeError)):
            setattr(section, key, "Other")


def test_the_traces_key_reads_a_boolean_and_refuses_anything_else(tmp_path: Path) -> None:
    """It is the one `eval:` key that is a flag, and `keep_traces: "no"` is not false."""
    written = tmp_path / "cowork_evals.yaml"
    written.write_text("eval:\n  keep_traces: false\n", encoding="utf-8")
    assert Config.load(written).eval.keep_traces is False

    written.write_text("eval:\n  keep_traces: 'no'\n", encoding="utf-8")
    with pytest.raises(CoWorkError) as raised:
        Config.load(written)
    assert "eval.keep_traces: expected true or false, got str" in str(raised.value)
